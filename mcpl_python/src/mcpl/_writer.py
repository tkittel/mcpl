
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
from ._statsum import (
    _parse_statsum,
    _parse_statsum_comment,
    _statsum_syntax_error,
    encode_stat_sum,
)


def _outfile_name(filename):
    """The name which MCPLOutFile gives a file: the filename with ".mcpl"
    appended unless it already ends with ".mcpl" (like in the C API)"""
    return filename if filename.endswith('.mcpl') else filename + '.mcpl'

class MCPLOutFile:
    """Python-only class for writing MCPL files, using numpy to process blocks of
    particles efficiently. The produced files are identical to those written by
    the C library (MCPL format version 3).

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
    with add_particle(..). The file must be closed with close() or
    closeandgzip(), which happens automatically (with close()) at the end of
    a with-statement:

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
                  blocklength = 10000, pick = None, edit = None,
                  userdata_layout = None, _dry_run = False ):
        """Create new file (overwriting any existing file). Like in the C API,
        ".mcpl" is appended to the filename if it does not already end with
        it. The keyword arguments correspond to calling the methods
        hdr_set_srcname, hdr_add_comment (for each comment), hdr_add_data (for
        each key,value in blobs), hdr_add_stat_sum (for each key,value in
        stat_sum), enable_userflags, enable_polarisation, enable_doubleprec
        (if opt_singleprec is False), enable_universal_pdgcode,
        enable_universal_weight and enable_userdata (with the given
        userdata_layout). The blocklength parameter controls how many
        particles added with add_particle(..) are buffered before being
        written.

        If pick (an expression or a ParticleFilter) is given, only the
        picked particles are written, and if edit (an expression or a
        ParticleEdit) is given, it is applied to all particles before they are
        written. For instance, MCPLOutFile("out.mcpl",pick="pdgcode ==
        neutron",edit="z += 1m").
        Note that stat:sum entries are not modified, so they should for
        instance be scaled with hdr_scale_stat_sums(-1) when particle weights
        are edited (see the guidelines for stat:sum entries).
        """
        self._fh = None
        #(in dry-run mode, used by the dry_run options of the file operations
        #and mcpltool, everything is done except writing):
        self._dry_run = bool(_dry_run)
        #(only importing the expressions module when needed):
        self._flt = self._edt = None
        if pick is not None or edit is not None:
            from ._expressions import _as_edit, _as_filter
            self._flt = None if pick is None else _as_filter(pick)
            self._edt = None if edit is None else _as_edit(edit)
        if hasattr(filename,'__fspath__'):
            filename = os.fspath(filename)
        if isinstance(filename,bytes):
            filename = filename.decode()
        if not isinstance(filename,str):
            raise MCPLError('Unsupported type of filename object'
                            ' (should be path-like, a string or similar)')
        if not filename:
            raise MCPLError('MCPLOutFile called with empty string.')
        if len(filename) > 4096:
            raise MCPLError('MCPLOutFile called with too long string.')
        lastdot = filename.rfind('.')
        if lastdot == 0 and len(filename) == 5:
            raise MCPLError('MCPLOutFile called with string with no'
                            ' basename part (".mcpl").')
        self._filename = _outfile_name(filename)
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
        self._nparticles = 0
        self._statsuminfo = {}#key -> [position of comment data in file, value]
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
        """Name of file being written to (might have had .mcpl appended)"""
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
        float32 and float64. Names must start with a lowercase letter followed
        by lowercase letters, digits or underscores (names are required, also
        for plain bytes like "data:uint8[27]", to avoid mixing up different
        data with the same types when merging files). The names of the fields
        of particles (x, ekin, userflags, ...) and position, direction,
        polarisation and wavelength can not be used. At most 65535 bytes per
        particle are allowed. The userdata of the particles is given with the
        userdata argument of add_particles and add_particle, which is required
        for files with userdata (userdata = {} gives userdata with all bytes
        zero). Files with userdata are written in MCPL
        format version 4 (which older MCPL releases can not read)."""
        from ._userdata import userdata_dtype
        userdata_dtype(layout)#validate
        if self._udlayout is not None:
            if self._udlayout != layout:
                raise MCPLError('enable_userdata called multiple times with'
                                ' different layouts')
            return
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

    def _check_hdr_entry(self, nbytes):
        #Check that a header entry with the given number of bytes can be added.
        #The sizes of comments and blobs are only accepted up to a smaller
        #limit, with a margin for the other parts of the header (the fixed
        #part, and the source name and userdata layout strings), so the header
        #never becomes too large:
        from ._reader import _max_header_entries, _max_header_size
        if len(self._comments) + len(self._blobs) + 1 > _max_header_entries:
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
        file)."""
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
        if key in self._blobs:
            raise MCPLError('hdr_add_data got duplicate key')
        data = bytes(data)
        if len(data) >= 4294967295:
            raise MCPLError('hdr_add_data got too large data')
        self._check_hdr_entry(8 + len(key) + len(data))
        self._blobkeys.append(key)
        self._blobs[key] = data
        self._hdr_entries_size += 8 + len(key) + len(data)

    def enable_userflags(self):
        """Write the userflags info"""
        if self._opt_userflags:
            return
        self._check_hdr_notwritten('enable_userflags')
        self._opt_userflags = True

    def enable_polarisation(self):
        """Write the polarisation info"""
        if self._opt_polarisation:
            return
        self._check_hdr_notwritten('enable_polarisation')
        self._opt_polarisation = True

    def enable_doubleprec(self):
        """Use double precision floating point numbers in storage"""
        if not self._opt_singleprec:
            return
        self._check_hdr_notwritten('enable_doubleprec')
        self._opt_singleprec = False

    def enable_universal_pdgcode(self, pdgcode):
        """All particles are of the same type"""
        pdgcode = int(pdgcode)
        if pdgcode == 0:
            raise MCPLError('enable_universal_pdgcode must be called with'
                            ' non-zero pdgcode.')
        if not ( -2147483648 <= pdgcode <= 2147483647 ):
            raise MCPLError('enable_universal_pdgcode must be called with'
                            ' a 32 bit integer.')
        if self._opt_universalpdgcode:
            if self._opt_universalpdgcode != pdgcode:
                raise MCPLError('enable_universal_pdgcode called multiple times')
            return
        self._check_hdr_notwritten('enable_universal_pdgcode')
        self._opt_universalpdgcode = pdgcode

    def enable_universal_weight(self, weight):
        """All particles have the same weight"""
        import math
        weight = float(weight)
        if weight <= 0.0 or math.isinf(weight) or math.isnan(weight):
            raise MCPLError('enable_universal_weight must be called with'
                            ' positive but finite weight.')
        if self._opt_universalweight:
            if self._opt_universalweight != weight:
                raise MCPLError('enable_universal_weight called multiple times')
            return
        self._check_hdr_notwritten('enable_universal_weight')
        self._opt_universalweight = weight

    def hdr_add_stat_sum(self, key, value):
        """Add or update named statistics "sum", encoded in a special comment
        (see the C API for details). Use value=-1 (or None) to register a
        value which will be updated later (at the latest before closing the
        file)."""
        self._check_open()
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
        self._update_statsum_on_disk(key,comment,value)

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

    def transfer_metadata(self, source):
        """Transfer all settings, blobs and comments from an MCPLFile object (or
        the file with the given name). Note that if splitting files rather
        than filtering them, hdr_scale_stat_sums should be called afterwards
        (see the C API for details)."""
        if not isinstance(source,MCPLFile):
            with MCPLFile(source) as f:
                return self.transfer_metadata(f)
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
            pos = add_buffer(c)
            if c.startswith(b'stat:sum:'):
                key, value = _parse_statsum_comment(c)[1]
                statsuminfo[key] = [pos,-1.0 if value is None else value]
        for k in self._blobkeys:
            add_buffer(k)
        for k in self._blobkeys:
            add_buffer(self._blobs[k])
        self._fh.write(out)
        self._fh.flush()
        self._statsuminfo = statsuminfo
        self._hdr_notwritten = False
        self._fmt()

    def _update_statsum_on_disk(self, key, comment, value):
        pos = self._statsuminfo[key][0]
        self._fh.flush()
        savedpos = self._fh.tell()
        self._fh.seek(pos)
        self._fh.write(comment)
        self._fh.seek(savedpos)
        self._statsuminfo[key][1] = value

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
            if self._flt is None and self._edt is None:
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
            #(picks and edits use the userdata given, if any):
            def view( b ):
                return b if udarr is None else _UserdataView(b,udarr,self._udlayout)
            if self._flt is not None:
                keep = self._flt(view(b))
                b = b[keep]
                if udarr is not None:
                    udarr = udarr[keep]
            if self._edt is not None and len(b):
                b = _EditedParticleBlock(b,self._edt(view(b)))
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
        if self._flt is not None or self._edt is not None:
            defaults = { 'pdgcode' : self._opt_universalpdgcode,
                         'weight' : self._opt_universalweight }
            blk = _ArrayBlock(cols,n,defaults,udarr,self._udlayout)
            if self._flt is not None:
                keep = np.flatnonzero(self._flt(blk))
                if not len(keep):
                    return
                n = len(keep)
                if udarr is not None:
                    udarr = udarr[keep]
                blk = _ArrayBlock({ f : getattr(blk,f)[keep] for f in _block_fields },
                                  n,defaults,udarr,self._udlayout)
            cols = { f : getattr(blk,f) for f in _block_fields if f in cols }
            if self._edt is not None:
                cols.update(self._edt(blk))
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
        if ( self._flt is not None or self._edt is not None ) and particle is None:
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
        header)."""
        if self._fh is None:
            return
        try:
            self._flush_pending()
            if self._hdr_notwritten:
                self._write_header()
            if self._nparticles:
                import struct
                self._fh.seek(8)
                self._fh.write(struct.pack('=Q',self._nparticles))
        finally:
            fh, self._fh = self._fh, None
            fh.close()

    def closeandgzip(self):
        """Close the file and gzip it (which will append .gz to the filename).
        Returns True if gzipping was successful."""
        self.close()
        return True if self._dry_run else gzip_file(self._filename)

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
    name (like mcpl_gzip_file in the C API). Returns True if successful."""
    import gzip
    import pathlib
    import shutil
    f = pathlib.Path(filename)
    bn = f.name
    _info(f'Compressing file {bn}')
    try:
        with f.open('rb') as fi, gzip.open(f.parent / (bn + '.gz'),'wb') as fo:
            shutil.copyfileobj(fi, fo)
        f.unlink()
    except OSError:
        _error(f'Problems encountered while compressing file {bn}.')
        return False
    _info(f'Compressed file into {bn}.gz')
    return True

def _broadcast_userdata( udarr, n ):
    if len(udarr) == n:
        return udarr
    if len(udarr) != 1:
        raise MCPLError('Inconsistent lengths of userdata and particle field arrays')
    return np.broadcast_to(udarr,(n,))

def _decode( b ):
    """Decode bytes from the header like MCPLFile does"""
    return b.decode('utf-8','replace')

