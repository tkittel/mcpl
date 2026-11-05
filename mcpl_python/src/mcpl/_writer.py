
################################################################################
##                                                                            ##
##  This file is part of MCPL (see https://mctools.github.io/mcpl/)           ##
##                                                                            ##
##  Copyright 2015-2026 MCPL developers.                                      ##
##                                                                            ##
##  Licensed under the Apache License, Version 2.0 (the "License");           ##
##  you may not use this file except in compliance with the License.          ##
##  You may obtain a copy of the License at                                   ##
##                                                                            ##
##      http://www.apache.org/licenses/LICENSE-2.0                            ##
##                                                                            ##
##  Unless required by applicable law or agreed to in writing, software       ##
##  distributed under the License is distributed on an "AS IS" BASIS,         ##
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  ##
##  See the License for the specific language governing permissions and       ##
##  limitations under the License.                                            ##
##                                                                            ##
################################################################################


"""Writing of MCPL files."""

__all__ = ['MCPLOutFile', 'gzip_file']

import os
import pathlib

from ._blocks import (
    MCPLParticle,
    MCPLParticleBlock,
    _ArrayBlock,
    _block_fields,
    _EditedParticleBlock,
    _nonfinite_masks,
    _UserdataView,
)
from ._common import MCPLError, _native_endianness
from ._messages import _error, _info, _warning
from ._numpy import np
from ._reader import MCPLFile
from ._records import (
    _Columns,
    _fields_all,
    _fields_vector,
    _int_field,
    _raise_first_failure,
    _RecordFormat,
    collect_fields,
)


def _outfile_name(filename):
    """The name of the file which MCPLOutFile writes for a filename, and whether
    it is gzipped when closed (like in the C API): the filename with ".mcpl"
    appended unless it already ends with ".mcpl", or for names ending with
    ".mcpl.gz" the name without ".gz". Other names ending with ".gz" are
    refused."""
    if filename.endswith('.mcpl.gz'):
        return filename[:-3], True
    if filename.endswith('.gz'):
        raise MCPLError('Output file names ending with .gz must end with'
                        f' .mcpl.gz (not "{filename}")')
    return ( filename if filename.endswith('.mcpl') else filename + '.mcpl' ), False

def _check_new_output( fn, gzip, allow_overwrite ):
    """Error if an output file written as fn (and gzipped into fn.gz when gzip
    is set) would overwrite an existing file, unless allowed (like in the C
    API)"""
    import os
    if allow_overwrite:
        return
    if gzip and os.path.lexists(fn + '.gz'):
        raise MCPLError(f'The output file "{fn}.gz" already exists')
    if gzip and os.path.lexists(fn):
        raise MCPLError(f'The output file "{fn}.gz" can not be written, since'
                        f' "{fn}" (which it is compressed from) already exists')
    if os.path.lexists(fn):
        raise MCPLError(f'The output file "{fn}" already exists')

def _check_merge_output( file_output, files, allow_overwrite ):
    """Error unless the output file of a merge can be created (like in the C
    API): an output file which is (or is written via) one of the input files
    is always refused, and existing files unless allow_overwrite"""
    fn, gzip = _outfile_name(file_output)
    for f in files:
        if _is_same_file(fn, f) or ( gzip and _is_same_file(fn + '.gz', f) ):
            raise MCPLError(f'The output file "{fn + ".gz" if gzip else fn}"'
                            ' is also one of the input files')
    _check_new_output( fn, gzip, allow_overwrite )

def _is_same_file(f1, f2):
    try:
        return pathlib.Path(f1).samefile(f2)
    except OSError:
        return False

class MCPLOutFile:
    """Python-only class for writing MCPL files, using numpy to process blocks of
    particles efficiently. The produced files are identical to those written by
    the C library (in MCPL format version 3, or 4 for files with userdata).

    The header is configured with methods named like the corresponding
    functions in the C API (hdr_set_srcname, hdr_add_comment, hdr_add_data,
    hdr_add_stat_sum, enable_userflags, enable_polarisation,
    enable_doubleprec, enable_universal_pdgcode, enable_universal_weight),
    and/or by passing keyword arguments to the constructor, named like the
    corresponding attributes of MCPLFile (sourcename, comments, blobs,
    stat_sum, opt_userflags, opt_polarisation, opt_singleprec,
    opt_universalpdgcode, opt_universalweight). The two can be mixed freely,
    since the keyword arguments are simply passed on to the methods. As in
    the C API, the header must be completely configured before the first
    particle is added, except for stat:sum values which can be updated until
    the file is closed (if a value was registered before the first particle,
    for instance the special value -1).

    Particles are added in blocks with add_particles(..), or one at a time
    with add_particle(..). The file must be closed with close(), which happens
    automatically at the end of a with-statement (files with names ending
    with .mcpl.gz are gzipped when closed):

       with MCPLOutFile('myfile.mcpl',
                        sourcename='MySimulation',
                        opt_universalpdgcode=2112) as f:
           f.hdr_add_comment('Some comment')
           f.add_particles( position = pos,
                            direction = dirs,
                            ekin = ekin, time = t,
                            weight = w )

    Particles read from an existing file with MCPLFile (blocks or single
    particles) can be passed directly to add_particles(..) and
    add_particle(..), in which case the packed particle data is transferred
    exactly when possible (like mcpl_transfer_last_read_particle in the C
    API). The header settings of an existing file can be copied with
    transfer_metadata(..).
    """

    def __init__( self, filename, *, sourcename = None, comments = None,
                  blobs = None, stat_sum = None, opt_userflags = False,
                  opt_polarisation = False, opt_singleprec = True,
                  opt_universalpdgcode = 0, opt_universalweight = 0.0,
                  blocklength = 10000, edit = None,
                  userdata_layout = None, allow_overwrite = False,
                  _dry_run = False ):
        """Create new file. Like in the C API, ".mcpl" is appended to the
        filename if it does not already end with it, and files with names
        ending with ".mcpl.gz" are written without ".gz" and gzipped when
        closed (other names ending with ".gz" are not allowed). It is an error
        if the file (or one of these two files) already exists, unless
        allow_overwrite is True. The other keyword arguments correspond to calling the methods
        hdr_set_srcname, hdr_add_comment (for each comment), hdr_add_data (for
        each key,value in blobs), hdr_add_stat_sum (for each key,value in
        stat_sum), enable_userflags, enable_polarisation, enable_doubleprec
        (if opt_singleprec is False), enable_universal_pdgcode,
        enable_universal_weight and enable_userdata (with the given
        userdata_layout). The blocklength parameter controls how many
        particles added with add_particle(..) are buffered before being
        written.

        If edit (an edit expression or a ParticleEdit) is given, only the
        particles it keeps are written, with its changes. For instance,
        MCPLOutFile("out.mcpl",edit="pdgcode == neutron; z += 1m").
        Note that stat:sum entries are not modified, so they should for
        instance be scaled with hdr_scale_stat_sums(-1) when particle weights
        are edited (see the guidelines for stat:sum entries).
        """
        self._fh = None
        #(in dry-run mode, used by the dry_run options of the file operations
        #and mcpltool, everything is done except writing):
        self._dry_run = bool(_dry_run)
        #(only importing the expressions module when needed):
        self._edt = None
        if edit is not None:
            from ._expressions import _as_edit
            self._edt = _as_edit(edit)
        if hasattr(filename,'__fspath__'):
            filename = os.fspath(filename)
        if isinstance(filename,bytes):
            filename = filename.decode()
        if not isinstance(filename,str):
            raise MCPLError('Unsupported type of filename object'
                            ' (should be path-like, a string, or similar)')
        if not filename:
            raise MCPLError('MCPLOutFile called with empty string.')
        if len(filename) > 4096:
            raise MCPLError('MCPLOutFile called with too long string.')
        lastdot = filename.rfind('.')
        if lastdot == 0 and len(filename) == 5:
            raise MCPLError('MCPLOutFile called with string with no'
                            ' basename part (".mcpl").')
        self._filename, self._gzip_at_close = _outfile_name(filename)
        self._allow_overwrite = bool(allow_overwrite)
        _check_new_output( self._filename, self._gzip_at_close,
                           self._allow_overwrite )
        self._blocklength = int(blocklength)
        if self._blocklength < 1:
            raise MCPLError('blocklength must be at least 1')
        self._hdr_notwritten = True
        self._srcname = None
        self._comments = []
        self._blobkeys = []
        self._blobs = {}
        self._hdr_entries_size = 0#size of the comments and blobs in the header
        self._opt_userflags = False
        self._opt_polarisation = False
        self._opt_singleprec = True
        self._opt_universalpdgcode = 0
        self._opt_universalweight = 0.0
        self._udlayout = None
        self._editable = False#(see transfer_metadata)
        self._nparticles = 0
        #(key -> [position of comment data in file, value, comment written
        #when the file is closed, which has -1 until then]):
        self._statsuminfo = {}
        self._pending = []
        self._format = None#(see _fmt)
        self._fh = _DryRunHandle() if self._dry_run else open(self._filename,'wb')  # noqa: SIM115
        #(invalid arguments must not leave a file behind):
        try:
            if sourcename is not None:
                self.hdr_set_srcname(sourcename)
            for c in (comments or []):
                self.hdr_add_comment(c)
            for k,v in (blobs.items() if hasattr(blobs,'items') else (blobs or [])):
                self.hdr_add_data(k,v)
            for k,v in (stat_sum or {}).items():
                self.hdr_add_stat_sum(k,v)
            if opt_userflags:
                self.enable_userflags()
            if opt_polarisation:
                self.enable_polarisation()
            if not opt_singleprec:
                self.enable_doubleprec()
            if opt_universalpdgcode:
                self.enable_universal_pdgcode(opt_universalpdgcode)
            if opt_universalweight:
                self.enable_universal_weight(opt_universalweight)
            if userdata_layout is not None:
                self.enable_userdata(userdata_layout)
        except BaseException:
            self._abort()
            raise

    def __enter__(self):
        return self

    def __exit__(self, ttype, value, traceback):
        if self._fh is not None:
            self.close()

    def __del__(self):
        if getattr(self,'_fh',None) is not None:
            self.close()

    @property
    def filename(self):
        """Name of file being written to (might have had .mcpl appended, or .gz
        removed)"""
        return self._filename

    @property
    def nparticles(self):
        """Number of particles added so far"""
        return self._nparticles + len(self._pending)

    @property
    def sourcename(self):
        """Name of the generating application (None if not set). Like the other
        header properties, it is decoded like by MCPLFile."""
        return None if self._srcname is None else _decode(self._srcname)

    @property
    def comments(self):
        """List of comments added so far (strings)"""
        return [ _decode(c) for c in self._comments ]

    @property
    def blobs(self):
        """Dictionary of binary blobs added so far (with strings as keys)"""
        return { _decode(k) : v for k,v in self._blobs.items() }

    @property
    def stat_sum(self):
        """Dictionary of stat:sum entries, like MCPLFile.stat_sum"""
        if self._hdr_notwritten:
            from ._statsum import _parse_statsum
            return _parse_statsum(self._comments)
        return { k : (None if v[1]==-1.0 else v[1])
                 for k,v in self._statsuminfo.items() }

    @property
    def opt_userflags(self):
        """Whether userflags are stored for each particle"""
        return self._opt_userflags

    @property
    def opt_polarisation(self):
        """Whether polarisation vectors are stored for each particle"""
        return self._opt_polarisation

    @property
    def opt_singleprec(self):
        """Whether floating point numbers are stored in single precision
        (rather than double precision)"""
        return self._opt_singleprec

    @property
    def opt_universalpdgcode(self):
        """Universal pdgcode (0 if not set)"""
        return self._opt_universalpdgcode

    @property
    def opt_universalweight(self):
        """Universal weight (0.0 if not set)"""
        return self._opt_universalweight

    @property
    def userdata_layout(self):
        """Layout of the per-particle userdata (None if the file has no
        userdata), see enable_userdata."""
        return self._udlayout

    @property
    def userdata_size(self):
        """Bytes of userdata per particle (0 if the file has no userdata)"""
        return self._userdata_dtype().itemsize if self._udlayout else 0

    def _userdata_dtype(self):
        from ._userdata import userdata_dtype
        return userdata_dtype(self._udlayout)

    def _check_userdata_given(self, fctname):
        if self._udlayout is not None:
            raise MCPLError(f'{fctname} called without userdata for a file with'
                            ' userdata (use userdata = {} for userdata with all'
                            ' bytes zero)')

    def _userdata_arg(self, value, fctname):
        """Userdata given to add_particles or add_particle, as a structured
        array (and the number of particles)"""
        if self._udlayout is None:
            raise MCPLError(f'{fctname} called with userdata for a file without'
                            ' userdata (see enable_userdata)')
        from ._userdata import userdata_array
        return userdata_array(value,self._udlayout)

    def enable_userdata(self, layout):
        """Enable per-particle userdata with the given layout, which is a
        comma-separated list of fields "name:type" or "name:type[n]" (arrays
        of n values), like "temp:float32,origin:int32,tags:uint8[3]". The
        types are int8, uint8, int16, uint16, int32, uint32, int64, uint64,
        float32, and float64. Names must start with a lowercase letter followed
        by lowercase letters, digits, or underscores (names are required, also
        for plain bytes like "data:uint8[27]", to avoid mixing up different
        data with the same types when merging files). The names of the fields
        of particles (x, ekin, userflags, ...) and position, direction,
        polarisation, and wavelength can not be used. At most 65535 bytes per
        particle are allowed. The userdata of the particles is given with the
        userdata argument of add_particles and add_particle, which is required
        for files with userdata (userdata = {} gives userdata with all bytes
        zero). Files with userdata are written in MCPL
        format version 4 (which older MCPL releases can not read). After
        transfer_metadata(..., editable=True), and before the first particle
        is added, another layout replaces the layout, and None removes the
        userdata."""
        if layout is not None:
            from ._userdata import userdata_dtype
            userdata_dtype(layout)#validate
        if layout == self._udlayout:
            return
        if layout is None:
            self._check_editable('enable_userdata(None)')
        elif self._udlayout is not None:
            self._check_editable('enable_userdata','called multiple times with'
                                 ' different layouts')
        self._check_hdr_notwritten('enable_userdata')
        self._udlayout = layout

    @property
    def particlesize(self):
        """Bytes per particle in the file"""
        fp = 4 if self._opt_singleprec else 8
        n = 7 * fp
        if self._opt_polarisation:
            n += 3 * fp
        if not self._opt_universalpdgcode:
            n += 4
        if not self._opt_universalweight:
            n += fp
        if self._opt_userflags:
            n += 4
        return n + self.userdata_size

    @staticmethod
    def _to_bytes(s, what):
        if isinstance(s,str):
            s = s.encode('utf-8')
        else:
            s = bytes(s)
        if b'\0' in s:
            raise MCPLError(f'{what} must not contain null characters.')
        return s

    def _check_open(self):
        if self._fh is None:
            raise MCPLError('Output file has already been closed.')

    def _check_hdr_notwritten(self,fctname):
        self._check_open()
        if not self._hdr_notwritten:
            raise MCPLError(f'{fctname} called too late.')

    def hdr_set_srcname(self, srcname):
        """Name of the generating application"""
        self._check_hdr_notwritten('hdr_set_srcname')
        self._srcname = self._to_bytes(srcname,'Source name')

    def hdr_add_comment(self, comment):
        """Add human-readable comment (headers are limited to 1.9GB and
        1000000 comments and blobs together)"""
        self._check_hdr_notwritten('hdr_add_comment')
        comment = self._to_bytes(comment,'Comments')
        if comment.startswith(b'stat:sum:'):
            from ._statsum import (
                _parse_statsum,
                _parse_statsum_comment,
                _statsum_syntax_error,
            )
            ok, (key, _) = _parse_statsum_comment(comment)
            if not ok:
                raise MCPLError(_statsum_syntax_error(comment))
            if key in _parse_statsum(self._comments):
                raise MCPLError(f'Duplicate stat:sum: key. The key "{key}"'
                                ' appears more than once.')
        elif comment.startswith(b'stat:'):
            raise MCPLError('Refusing to create file with comments starting'
                            ' with "stat:" unless starting with "stat:sum:",'
                            ' as such syntax is reserved for future usage.')
        self._check_hdr_entry(4 + len(comment))
        self._comments.append(comment)
        self._hdr_entries_size += 4 + len(comment)

    def hdr_set_comments(self, comments):
        """Replace all comments with the comments given (a list), e.g. to
        change, remove, or reorder comments copied with transfer_metadata
        (before the first particle is added). stat:sum entries are comments
        too (see hdr_remove_stat_sum to remove one)."""
        self._check_hdr_notwritten('hdr_set_comments')
        old = self._comments, self._hdr_entries_size
        self._hdr_entries_size -= sum( 4 + len(c) for c in self._comments )
        self._comments = []
        try:
            for c in comments:
                self.hdr_add_comment(c)
        except BaseException:
            self._comments, self._hdr_entries_size = old
            raise

    def hdr_remove_stat_sum(self, key):
        """Remove the stat:sum entry with the key (before the first particle
        is added), e.g. one copied with transfer_metadata"""
        self._check_hdr_notwritten('hdr_remove_stat_sum')
        from ._statsum import _parse_statsum_comment
        key = key.decode('ascii') if hasattr(key,'decode') else key
        for i, c in enumerate(self._comments):
            if c.startswith(b'stat:sum:') and _parse_statsum_comment(c)[1][0] == key:
                del self._comments[i]
                self._hdr_entries_size -= 4 + len(c)
                return
        raise MCPLError(f'hdr_remove_stat_sum: no stat:sum entry with the key "{key}"')

    def _check_hdr_entry(self, nbytes, new_entry = True):
        #Check that a header entry with the given number of bytes can be added
        #(or that nbytes more can be added to an entry, without new_entry).
        #The sizes of comments and blobs are only accepted up to a smaller
        #limit, with a margin for the other parts of the header (the fixed
        #part, and the source name and userdata layout strings), so the header
        #never becomes too large:
        from ._reader import _max_header_entries, _max_header_size
        if new_entry and len(self._comments) + len(self._blobs) + 1 > _max_header_entries:
            raise MCPLError('File header would get too many comments and blobs'
                            ' (more than 1000000)')
        if self._hdr_entries_size + nbytes > _max_header_size - 200000:
            raise MCPLError('File header would become too large (more than'
                            ' 1.9GB)')

    def hdr_add_data(self, key, data):
        """Add binary blob (bytes-like object) by key (unique, non-empty,
        ASCII, no non-printable characters, whitespace, backslash, or
        quotation marks). Blobs are stored byte for byte, so binary numbers in
        them are in the byte order chosen by the application, unlike all
        other numbers in MCPL files (which are in the byte order of the
        file). After transfer_metadata(..., editable=True), and before the
        first particle is added, the data replaces a blob with the same
        key."""
        self._hdr_add_data(key, data, lenient = False)

    def _hdr_add_data(self, key, data, lenient):
        #With lenient, the rules for blob keys are not applied (for keys copied
        #from files in format versions before 4, where they did not apply):
        self._check_hdr_notwritten('hdr_add_data')
        key = self._to_bytes(key,'Blob keys')
        from ._reader import blobkey_problem
        problem = None if lenient else blobkey_problem(key)
        if problem:
            raise MCPLError(f'hdr_add_data got invalid key ({problem}).')
        old = self._blobs.get(key)
        if old is not None and not self._editable:
            raise MCPLError('hdr_add_data got duplicate key')
        data = bytes(data)
        if len(data) >= 4294967295:
            raise MCPLError('hdr_add_data got too large data')
        if old is not None:
            #(replaced, keeping its place among the blobs):
            self._check_hdr_entry(len(data) - len(old), new_entry = False)
            self._blobs[key] = data
            self._hdr_entries_size += len(data) - len(old)
            return
        self._check_hdr_entry(8 + len(key) + len(data))
        self._blobkeys.append(key)
        self._blobs[key] = data
        self._hdr_entries_size += 8 + len(key) + len(data)

    def hdr_remove_data(self, key):
        """Remove the binary blob with the key (before the first particle is
        added), e.g. one copied with transfer_metadata."""
        self._check_hdr_notwritten('hdr_remove_data')
        key = self._to_bytes(key,'Blob keys')
        if key not in self._blobs:
            raise MCPLError(f'hdr_remove_data: no blob with the key "{_decode(key)}"')
        self._hdr_entries_size -= 8 + len(key) + len(self._blobs.pop(key))
        self._blobkeys.remove(key)

    def enable_userflags(self, enable = True):
        """Write the userflags of the particles (or not, with enable=False,
        after transfer_metadata(..., editable=True), before the first
        particle is added)"""
        if self._opt_userflags == bool(enable):
            return
        if not enable:
            self._check_editable('enable_userflags(False)')
        self._check_hdr_notwritten('enable_userflags')
        self._opt_userflags = bool(enable)

    def enable_polarisation(self, enable = True):
        """Write the polarisation vectors of the particles (or not, with
        enable=False, after transfer_metadata(..., editable=True), before the
        first particle is added)"""
        if self._opt_polarisation == bool(enable):
            return
        if not enable:
            self._check_editable('enable_polarisation(False)')
        self._check_hdr_notwritten('enable_polarisation')
        self._opt_polarisation = bool(enable)

    def enable_doubleprec(self, enable = True):
        """Use double precision floating point numbers in storage (or single
        precision, with enable=False, after transfer_metadata(...,
        editable=True), before the first particle is added: the values are
        then rounded)"""
        if self._opt_singleprec == ( not enable ):
            return
        if not enable:
            self._check_editable('enable_doubleprec(False)')
        self._check_hdr_notwritten('enable_doubleprec')
        self._opt_singleprec = not enable

    def _check_editable(self, what, problem = None):
        """Raise MCPLError unless the header was copied with
        transfer_metadata(..., editable=True), so its settings may change"""
        if not self._editable:
            raise MCPLError(f'{what} {problem}' if problem else
                            f'{what} can only be used after'
                            ' transfer_metadata(..., editable=True)')

    def enable_universal_pdgcode(self, pdgcode):
        """All particles are of the same type. After
        transfer_metadata(..., editable=True), and before the first particle
        is added, another value replaces the value, and None stores the type
        of each particle again."""
        if pdgcode is not None:
            pdgcode = int(pdgcode)
            if pdgcode == 0:
                raise MCPLError('enable_universal_pdgcode must be called with'
                                ' non-zero pdgcode.')
            if not ( -2147483648 <= pdgcode <= 2147483647 ):
                raise MCPLError('enable_universal_pdgcode must be called with'
                                ' a 32 bit integer.')
        if ( pdgcode or 0 ) == self._opt_universalpdgcode:
            return
        if pdgcode is None:
            self._check_editable('enable_universal_pdgcode(None)')
        elif self._opt_universalpdgcode:
            self._check_editable('enable_universal_pdgcode','called multiple times')
        self._check_hdr_notwritten('enable_universal_pdgcode')
        self._opt_universalpdgcode = pdgcode or 0

    def enable_universal_weight(self, weight):
        """All particles have the same weight. After
        transfer_metadata(..., editable=True), and before the first particle
        is added, another value replaces the value, and None stores the weight
        of each particle again."""
        if weight is not None:
            import math
            weight = float(weight)
            if weight <= 0.0 or math.isinf(weight) or math.isnan(weight):
                raise MCPLError('enable_universal_weight must be called with'
                                ' positive but finite weight.')
        if ( weight or 0.0 ) == self._opt_universalweight:
            return
        if weight is None:
            self._check_editable('enable_universal_weight(None)')
        elif self._opt_universalweight:
            self._check_editable('enable_universal_weight','called multiple times')
        self._check_hdr_notwritten('enable_universal_weight')
        self._opt_universalweight = weight or 0.0

    def hdr_add_stat_sum(self, key, value):
        """Add or update named statistics "sum", encoded in a special comment
        (see the C API for details). Use value=-1 (or None) to register a
        value which will be updated later (at the latest before closing the
        file)."""
        self._check_open()
        from ._statsum import _parse_statsum_comment, encode_stat_sum
        comment = encode_stat_sum(key,value).encode('ascii')
        if hasattr(key,'decode'):
            key = key.decode('ascii')
        value = -1.0 if value is None else float(value)
        if self._hdr_notwritten:
            for i,c in enumerate(self._comments):
                if c.startswith(b'stat:sum:') and _parse_statsum_comment(c)[1][0] == key:
                    self._comments[i] = comment
                    return
            self.hdr_add_comment(comment)
            return
        if key not in self._statsuminfo:
            raise MCPLError('hdr_add_stat_sum called after first particle was'
                            ' added to file, but without first registering a'
                            ' value for the same key earlier (the special'
                            ' value -1 can be used for this)')
        #(written when the file is closed):
        self._statsuminfo[key][1:] = [ value, comment ]

    def hdr_scale_stat_sums(self, scale):
        """Scale all stat:sum values with a given factor which must be a finite
        number >0.0 or -1 (see the C API for details)."""
        import math
        scale = float(scale)
        if math.isnan(scale):
            raise MCPLError('hdr_scale_stat_sums called with NaN (not-a-number) scale')
        if scale < 0.0 and scale != -1.0:
            raise MCPLError('hdr_scale_stat_sums called with negative scale')
        if math.isinf(scale):
            raise MCPLError('hdr_scale_stat_sums called with infinite scale')
        if scale == 0.0:
            raise MCPLError('hdr_scale_stat_sums called with zero scale')
        self._check_open()
        if self._hdr_notwritten:
            from ._statsum import _parse_statsum
            items = [ (k,(-1.0 if v is None else v))
                      for k,v in _parse_statsum(self._comments).items() ]
        else:
            items = [ (k,v[1]) for k,v in self._statsuminfo.items() ]
        any_inf = False
        for key, value in items:
            new_value = -1.0 if ( scale == -1.0 or value == -1.0 ) else value * scale
            if math.isinf(new_value):
                any_inf = True
                new_value = -1.0
            if new_value != value:
                self.hdr_add_stat_sum(key,new_value)
        if any_inf:
            _warning('The call to hdr_scale_stat_sums resulted in'
                     ' one or more stat:sum: entries overflowing floating point'
                     ' range and producing infinity. Reverting value to -1'
                     ' to indicate that a precise result is not available.')

    def transfer_metadata(self, source, *, editable = False):
        """Transfer all settings, blobs, and comments from an MCPLFile object (or
        the file with the given name). Note that if splitting files rather
        than filtering them, hdr_scale_stat_sums should be called afterwards
        (see the C API for details). With editable=True, the settings copied
        may then be changed before the first particle is added: with the
        enable_ methods, e.g. enable_doubleprec(False) for single precision
        or enable_universal_weight(None), and hdr_add_data may replace blobs.
        The comments, blobs, and stat:sum entries can also be changed without
        editable=True (see hdr_set_comments, hdr_remove_data, and
        hdr_remove_stat_sum)."""
        if not isinstance(source,MCPLFile):
            with MCPLFile(source) as f:
                return self.transfer_metadata(f,editable=editable)
        h = source._hdr
        if source.endianness != _native_endianness():
            raise MCPLError('transfer_metadata can only work on files with'
                            ' same endianness as current platform.')
        self.hdr_set_srcname(h.get('sourcename_raw',h['sourcename']))
        for c in h.get('comments_raw',h['comments']):
            self.hdr_add_comment(c)
        blobs = h.get('blobs_raw',h['blobs'])
        for k in h.get('blobkeys_raw',h['blobkeys']):
            #(keys from files in format versions before 4 are copied even if
            #they do not follow the rules of version 4, as long as the new
            #file does not have userdata):
            self._hdr_add_data(k,blobs[k],lenient=(source.version < 4))
        if source.opt_userflags:
            self.enable_userflags()
        if source.opt_polarisation:
            self.enable_polarisation()
        if not source.opt_singleprec:
            self.enable_doubleprec()
        if source.opt_universalpdgcode:
            self.enable_universal_pdgcode(source.opt_universalpdgcode)
        if source.opt_universalweight:
            self.enable_universal_weight(source.opt_universalweight)
        if source.userdata_layout is not None:
            self.enable_userdata(source.userdata_layout)
        if editable:
            self._editable = True

    def _fmt(self):
        """The format of the particle records (fixed when the header is
        written)"""
        if self._format is not None:
            return self._format
        fmt = _RecordFormat(self._opt_singleprec,self._opt_polarisation,
                            self._opt_universalweight,self._opt_universalpdgcode,
                            self._opt_userflags,
                            self._userdata_dtype() if self._udlayout is not None else None)
        assert fmt.dtype.itemsize == self.particlesize
        if not self._hdr_notwritten:
            self._format = fmt
        return fmt

    def _write_header(self):
        import struct
        assert self._hdr_notwritten
        #Files with userdata are in format version 4, where all blob keys must
        #follow the rules (they might not, when copied from older files):
        from ._reader import blobkey_problem
        for k in ( self._blobkeys if self._udlayout is not None else [] ):
            problem = blobkey_problem(k)
            if problem:
                raise MCPLError('The output file would have an invalid blob'
                                ' key copied from an input file'
                                f' ({problem}).')
        out = bytearray()
        #(files with userdata are in format version 4, others still in 3):
        version = b'004' if self._udlayout is not None else b'003'
        out += b'MCPL' + version + _native_endianness().encode('ascii')
        out += struct.pack('=Q',0)
        out += struct.pack('=8I',
                           len(self._comments),
                           len(self._blobkeys),
                           ( ( 0x1 if self._opt_userflags else 0 )
                             | ( 0x2 if self._udlayout is not None else 0 ) ),
                           int(self._opt_polarisation),
                           int(self._opt_singleprec),
                           self._opt_universalpdgcode & 0xFFFFFFFF,
                           self.particlesize,
                           1 if self._opt_universalweight else 0)
        if self._opt_universalweight:
            out += struct.pack('=d',self._opt_universalweight)
        def add_buffer(b):
            nonlocal out
            out += struct.pack('=I',len(b))
            pos = len(out)
            out += b
            return pos
        if self._udlayout is not None:
            add_buffer(self._udlayout.encode('ascii'))
        add_buffer(self._srcname if self._srcname is not None else b'unknown')
        statsuminfo = {}
        for c in self._comments:
            if not c.startswith(b'stat:sum:'):
                add_buffer(c)
                continue
            #(the file has -1 until the values are written when it is closed,
            #so unfinished files never have values; the length is the same, as
            #the value field has a fixed width):
            from ._statsum import _parse_statsum_comment, encode_stat_sum
            key, value = _parse_statsum_comment(c)[1]
            pos = add_buffer(encode_stat_sum(key,-1).encode('ascii'))
            statsuminfo[key] = [pos,-1.0 if value is None else value,c]
        for k in self._blobkeys:
            add_buffer(k)
        for k in self._blobkeys:
            add_buffer(self._blobs[k])
        self._fh.write(out)
        self._fh.flush()
        self._statsuminfo = statsuminfo
        self._hdr_notwritten = False
        self._fmt()

    def _write_records(self, arr):
        if self._hdr_notwritten:
            self._write_header()
        if len(arr):
            if not self._dry_run:
                self._fh.write(arr.tobytes())
            self._nparticles += len(arr)

    def _flush_pending(self):
        if not self._pending:
            return
        pending, self._pending = self._pending, []
        cols = list(zip(*pending))
        self._write_records( self._fmt().pack( len(pending),
                                         dict(zip(self._pending_keys,cols)),
                                         validate = False ) )

    _pending_keys = ('x','y','z','ux','uy','uz','polx','poly','polz',
                     'ekin','time','weight','pdgcode','userflags')

    def add_particles(self, particles = None, **fields):
        """Add block of particles. Particle data is specified with keyword
        arguments using the field names of MCPLParticleBlock: position (as
        array with shape (N,3)) or x, y, z; direction or ux, uy, uz;
        polarisation or polx, poly, polz; ekin, time, weight, pdgcode,
        userflags. Values can be numpy arrays of length N or scalars (which
        apply to all particles), and missing fields default to 0. Like in the
        C API, fields not enabled in the file are ignored (e.g. polarisation
        unless enable_polarisation() was called) as are the weight and
        pdgcode fields in files with universal weight or pdgcode.

        Instead of ekin, the wavelength [Aa] can be specified for neutrons and
        gammas.

        In files with userdata (see enable_userdata), the userdata of the
        particles is given with the userdata argument, as a dict of values for
        the fields of the layout (e.g. userdata = { 'temp' : temps, 'tags' :
        tags }, with temps of shape (N,) and tags of shape (N,3) for the layout
        "temp:float32,tags:uint8[3]"), or as a numpy structured array with
        those fields (e.g. the userdata of a block read from another file).
        Missing fields are zero (so userdata = {} gives userdata with all bytes
        zero), and values for a single particle apply to all particles.
        Integer fields must be given integers within the range of their type.
        In files with userdata, the userdata argument is required, unless the
        particles are passed as a block from a file with the same userdata
        layout (whose userdata is then used).

        Alternatively, an MCPLParticleBlock (or an MCPLParticle) read with
        MCPLFile can be passed, in which case its packed data is transferred
        exactly whenever possible. Combined with keyword arguments, the given
        fields replace those of the passed particles (e.g. to edit positions
        or weights), for instance: f.add_particles( block, weight = 2 *
        block.weight ).
        """
        self._check_open()
        udarr = None
        if 'userdata' in fields:
            fields = dict(fields)
            udarr, _ = self._userdata_arg(fields.pop('userdata'),'add_particles')
        if particles is not None:
            if isinstance(particles,MCPLParticle):
                b, sel = particles._b, slice(particles._i,particles._i+1)
            elif isinstance(particles,MCPLParticleBlock):
                b, sel = particles, slice(None)
            else:
                raise MCPLError('Unsupported type of particles object (should'
                                ' be MCPLParticleBlock or MCPLParticle)')
            if self._edt is None:
                if udarr is not None:
                    fields = dict(fields, userdata = udarr)
                self._transfer(b,sel,fields)
                return
            b = b[sel]
            if udarr is not None:
                udarr = _broadcast_userdata(udarr,len(b))
            if fields:
                ocols, _ = collect_fields(fields)
                self._fmt().resolve_wavelength(ocols, ocols.get('pdgcode', b.pdgcode))
                b = _EditedParticleBlock(b,ocols)
            #(the edit uses the userdata given, if any):
            kept, efields = self._edt._apply( b if udarr is None else
                                              _UserdataView(b,udarr,self._udlayout) )
            if kept is not None:
                b = b[kept]
                if udarr is not None:
                    udarr = udarr[kept]
            if efields:
                b = _EditedParticleBlock(b,efields)
            self._transfer(b,slice(None),
                           None if udarr is None else { 'userdata' : udarr })
            return
        if udarr is None:
            self._check_userdata_given('add_particles')
        cols, n = collect_fields(fields)
        if udarr is not None:
            if n == 1:
                n = len(udarr)
            udarr = _broadcast_userdata(udarr,n)
        self._fmt().resolve_wavelength(cols, cols.get('pdgcode'))
        if self._edt is not None:
            defaults = { 'pdgcode' : self._opt_universalpdgcode,
                         'weight' : self._opt_universalweight }
            blk = _ArrayBlock(cols,n,defaults,udarr,self._udlayout)
            kept, efields = self._edt._apply(blk)
            cols = { f : getattr(blk,f) for f in _block_fields if f in cols }
            if kept is not None:
                if not len(kept):
                    return
                cols = { k : np.broadcast_to(v,(n,))[kept] for k, v in cols.items() }
                n = len(kept)
                if udarr is not None:
                    udarr = udarr[kept]
            cols.update(efields)
            self._fmt().resolve_wavelength(cols, cols.get('pdgcode'))
        if udarr is not None:
            cols['userdata'] = udarr
        if self._hdr_notwritten:
            self._write_header()
        arr = self._fmt().pack(n,cols)
        self._flush_pending()
        self._write_records(arr)

    def add_particle(self, particle = None, **fields):
        """Add single particle. Takes the same arguments as add_particles(..),
        but with scalar values (or vectors of length 3), or a single
        MCPLParticle read with MCPLFile. Particles are internally buffered and
        written in blocks for efficiency. Userdata (see add_particles) is given
        for the single particle, e.g. userdata = { 'temp' : 293.0, 'tags' :
        [1,2,3] }."""
        self._check_open()
        if 'userdata' in fields:
            #(particles with userdata are added via add_particles):
            fields = dict(fields)
            udarr, nud = self._userdata_arg(fields.pop('userdata'),'add_particle')
            if nud != 1:
                raise MCPLError('add_particle must be called with userdata for'
                                ' a single particle')
            if particle is not None:
                if fields:
                    raise MCPLError('Do not specify particle fields together'
                                    ' with a particle object')
                self.add_particles(particle,userdata=udarr)
                return
            vecs = ('position','direction','polarisation')
            self.add_particles(userdata=udarr,
                               **{ k : ( [v] if k in vecs else np.atleast_1d(v) )
                                   for k,v in fields.items() })
            return
        if particle is None:
            self._check_userdata_given('add_particle')
        if self._edt is not None and particle is None:
            vecs = ('position','direction','polarisation')
            self.add_particles(**{ k : ( [v] if k in vecs else np.atleast_1d(v) )
                                   for k,v in fields.items() })
            return
        if particle is not None:
            if fields:
                raise MCPLError('Do not specify particle fields together with'
                                ' a particle object')
            if not isinstance(particle,MCPLParticle):
                raise MCPLError('Unsupported type of particle object (should'
                                ' be MCPLParticle)')
            self.add_particles(particle)
            return
        if self._hdr_notwritten:
            self._write_header()
        unknown = set(fields) - _fields_all
        if unknown:
            raise TypeError('Unknown particle field(s): '
                            + ', '.join(sorted(unknown)))
        vals = []
        for vecname, compnames in _fields_vector:
            if vecname in fields:
                if any( c in fields for c in compnames ):
                    raise MCPLError(f'Do not specify both {vecname} and any'
                                    ' of ' + ', '.join(compnames))
                v = fields[vecname]
                if len(v) != 3:
                    raise MCPLError(f'{vecname} must have length 3')
                vals += [ float(v[0]), float(v[1]), float(v[2]) ]
            else:
                vals += [ float(fields.get(c,0.0)) for c in compnames ]
        pdgcode = _int_field('pdgcode',fields.get('pdgcode',0),-2147483648,2147483647)
        userflags = _int_field('userflags',fields.get('userflags',0),0,4294967295)
        if 'wavelength' in fields:
            cols = { 'wavelength' : float(fields['wavelength']) }
            if 'ekin' in fields:
                cols['ekin'] = fields['ekin']
            self._fmt().resolve_wavelength(cols, pdgcode if 'pdgcode' in fields else None)
            ekin = float(cols['ekin'])
        else:
            ekin = float(fields.get('ekin',0.0))
        time, weight = float(fields.get('time',0.0)), float(fields.get('weight',0.0))
        self._fmt().validate_one(vals,ekin,time,weight)
        vals += [ ekin, time, weight, pdgcode, userflags ]
        self._pending.append(vals)
        if len(self._pending) >= self._blocklength:
            self._flush_pending()

    def _transfer(self, block, sel, overrides = None):
        udarr = None
        if overrides and 'userdata' in overrides:
            overrides = dict(overrides)
            udarr = overrides.pop('userdata')
            if not isinstance(udarr,np.ndarray) or udarr.dtype != self._userdata_dtype():
                udarr, _ = self._userdata_arg(udarr,'add_particles')
        edits = getattr(block,'_edits',None)
        if edits:
            #Edited block: transfer packed data, with edited fields as overrides
            ov = { k : v[sel] for k,v in edits.items() }
            ov.update(overrides or {})
            overrides = ov
        data = block._data[sel]
        n = len(data)
        if not n:
            return
        #Userdata is transferred if the layouts are the same and discarded if
        #the target has no userdata (other cases are errors, unless the
        #userdata is given):
        src_udlayout = block._udinfo[0] if block._udinfo else None
        if udarr is not None:
            udarr = _broadcast_userdata(udarr,n)
        elif self._udlayout is not None and src_udlayout is None:
            raise MCPLError('add_particles asked to transfer particles without'
                            ' userdata into a file with userdata (use userdata'
                            ' = {} for userdata with all bytes zero)')
        elif ( self._udlayout is not None and src_udlayout is not None
               and src_udlayout != self._udlayout ):
            raise MCPLError('add_particles asked to transfer particles into a'
                            ' file with a different userdata layout')
        ocols = {}
        if overrides:
            ocols, no = collect_fields(overrides)
            if no not in (1,n):
                raise MCPLError('Inconsistent lengths of particle field arrays')
            ocols = { k : np.broadcast_to(v,(n,)) for k,v in ocols.items() }
        if udarr is not None:
            ocols['userdata'] = udarr
        if self._hdr_notwritten:
            self._write_header()
        pdgcode = ocols['pdgcode'] if 'pdgcode' in ocols else block.pdgcode[sel]
        weight = ocols['weight'] if 'weight' in ocols else block.weight[sel]
        self._fmt().resolve_wavelength(ocols, pdgcode)
        #Checks like in mcpl_transfer_last_read_particle (for the first
        #particle failing any of them):
        checks = []
        if self._opt_universalpdgcode:
            m = np.asarray( pdgcode != self._opt_universalpdgcode )
            checks.append( ( m, lambda i : 'add_particles asked to transfer particle'
                             f' with pdgcode {pdgcode[i]} into a file with universal'
                             f' pdgcode of {self._opt_universalpdgcode}' ) )
        if self._opt_universalweight:
            m = np.asarray( weight != self._opt_universalweight )
            checks.append( ( m, lambda i : 'add_particles asked to transfer particle'
                             f' with weight {weight[i]:g} into a file with universal'
                             f' weight of {self._opt_universalweight:g}' ) )
        if ocols:
            src = _Columns(n,lambda name : ( ocols[name] if name in ocols
                                             else getattr(block,name)[sel] ))
        else:
            src = block[sel]
        for name, m in _nonfinite_masks(src,self._opt_polarisation,
                                        not self._opt_universalweight).items():
            checks.append( ( m, ( 'add_particles asked to transfer particle with'
                                  f' NaN or infinite {name}' ) ) )
        _raise_first_failure(checks)
        src_singleprec = ( data.dtype['x'].itemsize == 4 )
        if not ocols and block._fmtversion != 2 and data.dtype == self._fmt().dtype:
            #Particle data is encoded in exactly the same manner in source and
            #target, so simply transfer the bytes:
            arr = data
        else:
            cols = { 'x' : block.x[sel], 'y' : block.y[sel], 'z' : block.z[sel],
                     'ux' : block.ux[sel], 'uy' : block.uy[sel], 'uz' : block.uz[sel],
                     'polx' : block.polx[sel], 'poly' : block.poly[sel],
                     'polz' : block.polz[sel], 'ekin' : block.ekin[sel],
                     'time' : block.time[sel], 'weight' : weight,
                     'pdgcode' : pdgcode, 'userflags' : block.userflags[sel] }
            if ( self._udlayout is not None and src_udlayout is not None
                 and udarr is None ):
                cols['userdata'] = data['ud']
            cols.update(ocols)
            packed = None
            if ( block._fmtversion != 2 and ( self._opt_singleprec or not src_singleprec )
                 and not set(ocols).intersection(('ux','uy','uz','ekin')) ):
                #Reuse packed ekin+direction from the source, to avoid
                #potentially lossy unpacking+packing:
                packed = ( data['uve1'], data['uve2'], data['uve3'] )
            arr = self._fmt().pack(n,cols,packed_ekindir = packed)
        self._flush_pending()
        self._write_records(arr)

    def _abort(self):
        """Close and remove the (unfinished) file, after an error"""
        if self._fh is not None:
            fh, self._fh = self._fh, None
            fh.close()
        if not self._dry_run:
            pathlib.Path(self._filename).unlink(missing_ok=True)

    def close(self):
        """Close the file (writing all pending particles and updating the
        header), and gzip it for names ending with ".mcpl.gz"."""
        self._close()

    def _close( self, gzip_errors = True ):
        """Close the file. For names ending with .mcpl.gz, problems compressing
        the file are errors if gzip_errors is True, and are otherwise printed
        (returning False)."""
        if self._fh is None:
            return True
        try:
            self._flush_pending()
            if self._hdr_notwritten:
                self._write_header()
            #The stat:sum values (the file has -1 until now), before nparticles:
            self._fh.flush()
            for pos, _, comment in self._statsuminfo.values():
                self._fh.seek(pos)
                self._fh.write(comment)
            if self._nparticles:
                import struct
                self._fh.seek(8)
                self._fh.write(struct.pack('=Q',self._nparticles))
        finally:
            fh, self._fh = self._fh, None
            fh.close()
        if not self._gzip_at_close or self._dry_run:
            return True
        problem = _gzip( self._filename, self._allow_overwrite )
        if problem is None:
            return True
        if not gzip_errors:
            _error(problem + '.')
            return False
        raise MCPLError(problem + ' (the uncompressed file was closed'
                        ' properly)')

class _DryRunHandle:
    """Stands in for the file handle of an MCPLOutFile in dry-run mode,
    discarding everything written to it."""
    def write(self, data):
        pass
    def flush(self):
        pass
    def seek(self, pos):
        pass
    def tell(self):
        return 0
    def close(self):
        pass

def gzip_file(filename):
    """Compress file with gzip, replacing it with a file with .gz appended to its
    name (like mcpl_gzip_file in the C API). Returns True if successful. It
    fails if the file with .gz appended already exists."""
    problem = _gzip( filename, False )
    if problem is not None:
        _error(problem + '.')
    return problem is None

def _gzip( filename, allow_overwrite ):
    """Compress the file like gzip_file, returning a description of the problem
    (or None if successful). An existing file with .gz appended is only
    overwritten if allow_overwrite is True."""
    import gzip
    import pathlib
    import shutil
    f = pathlib.Path(filename)
    bn = f.name
    fout = f.parent / (bn + '.gz')
    _info(f'Compressing file {bn}')
    if not allow_overwrite and os.path.lexists(fout):
        return f'Unable to compress file {bn}, since {bn}.gz already exists'
    try:
        #(compression level 1, as in C):
        with f.open('rb') as fi, gzip.open(fout,'wb',compresslevel = 1) as fo:
            shutil.copyfileobj(fi, fo)
        f.unlink()
    except OSError:
        fout.unlink(missing_ok=True)
        return f'Problems encountered while compressing file {bn}'
    _info(f'Compressed file into {bn}.gz')
    return None

def _broadcast_userdata( udarr, n ):
    if len(udarr) == n:
        return udarr
    if len(udarr) != 1:
        raise MCPLError('Inconsistent lengths of userdata and particle field arrays')
    return np.broadcast_to(udarr,(n,))

def _decode( b ):
    """Decode bytes from the header like MCPLFile does"""
    return b.decode('utf-8','replace')

