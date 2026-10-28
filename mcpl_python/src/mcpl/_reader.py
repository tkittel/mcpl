
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

"""Reading of MCPL files."""

__all__ = ['MCPLFile']

import os

from ._blocks import (
    MCPLParticleBlock,
    _concat_blocks,
    _EditedParticleBlock,
    _nonfinite_masks,
    _surely_finite,
    record_dtype,
)
from ._common import MCPLError, _output_bytearray_raw
from ._messages import _warning
from ._numpy import np
from ._statsum import _parse_statsum, _parse_statsum_comment, encode_stat_sum

#The MCPL format allows implementations to refuse headers larger than 1.9GB,
#or with more than 1000000 comments and blobs (together), and headers are
#limited to that here (as in the C library):
_max_header_size = 1900000000
_max_header_entries = 1000000
_header_too_large_msg = 'File header is too large (more than 1.9GB)'
_header_too_many_msg = ( 'File header has too many comments and blobs (more'
                         ' than 1000000)' )

def blobkey_problem( key ):
    """Problem with a blob key (bytes), or None if it is valid: keys must be
    non-empty, ASCII, no non-printable characters, whitespace, backslash, or
    quotation marks (including backtick). This is required in format version
    4, and when adding keys to new files."""
    if not key:
        return 'empty keys are not allowed'
    if any( c > 127 for c in key ):
        return 'non-ASCII characters are not allowed'
    if b' ' in key:
        return 'whitespace is not allowed'
    if any( c < 32 or c == 127 for c in key ):
        return 'non-printable characters are not allowed'
    if any( c in key for c in ( b'"', b"'", b'\\', b'`' ) ):
        return 'quotation marks, backslash and backtick are not allowed'
    return None

class MCPLFile:
    """Python-only class for reading MCPL files, using numpy and internal caches to
    ensure good efficiency. File access is read-only, and the particles can only
    be read in consecutive and forward order, providing either single particles or
    blocks of particles as requested."""

    def __del__(self):
        #(also for objects whose __init__ failed before the file was opened):
        getattr(self,'_fileclose',lambda : None)()
        self._fileclose = lambda : None

    def __init__(self,filename,*,blocklength = 10000, raw_strings = False,
                 pick = None, edit = None, skip = 0, limit = None,
                 _recover = True):
        """Open indicated mcpl file, which can either be uncompressed (.mcpl) or
        compressed (.mcpl.gz). The other arguments must be given by name. The
        blocklength parameter can be used to control
        the number of particles read by each call to read_block(). The parameter
        raw_strings will prevent UTF-8 decoding of string data loaded from the
        file.

        If pick (an expression or a ParticleFilter) is given, only the
        picked particles are returned by read(), read_block(), and the
        particles and particle_blocks properties, and if edit (an expression or
        a ParticleEdit) is given, it is applied to the particles before they are
        returned. For instance:

           f = MCPLFile("in.mcpl", pick="pdgcode == neutron", edit="z += 1m")
           for block in f.particle_blocks:
               ...

        With skip and limit, only the particles in a range of the file are
        returned (and then picked and edited): without the first skip
        particles of the file, and at most limit particles (all if limit is
        None), like the -s and -l options of mcpltool:

           f = MCPLFile("in.mcpl", skip=1000, limit=500, pick="ekin > 1MeV")

        The picked particles are returned in blocks of about blocklength
        particles (small picks from several blocks in the file are
        merged). The nparticles attribute is still the number of particles in
        the file, and the fileidx of the particles their position in the
        file. Picked particles (and those of a range) can not be skipped with
        skip_forward(). Edited
        particles can be passed to MCPLOutFile.add_particles like any other
        particles, in which case their unmodified fields are transferred
        exactly.
        """
        #(set first, so cleaning up after errors below always works):
        self._fileclose = lambda : None
        if int(blocklength) < 1:
            raise MCPLError('blocklength must be at least 1')
        #(only importing the expressions module when needed):
        self._flt = self._edt = None
        if pick is not None or edit is not None:
            from ._expressions import _as_edit, _as_filter
            self._flt = None if pick is None else _as_filter(pick)
            self._edt = None if edit is None else _as_edit(edit)
        for name, value in ( ('skip',skip), ('limit',limit) ):
            if value is not None and ( not isinstance(value,(int,float,np.integer))
                                       or isinstance(value,bool) or int(value) != value
                                       or value < 0 ):
                raise MCPLError(f'{name} must be a number of particles (not {value!r})')
        self._skip, self._limit = int(skip or 0), None if limit is None else int(limit)
        self._fblocks, self._fparts = None, None
        #NaN or infinite values are not allowed, but files might have them, so
        #we warn when reading the first such particle (unless the check is
        #disabled for raw copying of particle data, like in merges):
        self._check_nonfinite = True
        self._warned_nonfinite = False
        self._nonfinite_mask = None

        self._str_decode = (not raw_strings)

        if hasattr(filename,'__fspath__'):
            #work with all pathlike objects:
            filename = os.fspath(filename)
        else:
            if not isinstance(filename,bytes) and not isinstance(filename,str):
                raise MCPLError('Unsupported type of filename object'
                                ' (should be path-like, a string or similar)')
        if isinstance(filename,bytes):
            filename = os.fsdecode(filename)

        self._filename = filename
        #prepare file i/o (opens file):
        self._open_file(filename)
        #load info from mcpl header:
        self._loadhdr()
        #Check if empty files are actually broken (like in mcpl.c):
        if self.nparticles==0 and _recover:
            if filename.endswith('.gz'):
                #compressed - can only detect and raise error
                try:
                    test_read=self._fileread(dtype='u1',count=1)
                except ValueError:
                    test_read=[]
                if len(test_read)>0:
                    raise MCPLError("Input file appears to not have been closed properly"
                                    +" and data recovery is disabled for gzipped files.")
            else:
                #not compressed - can use file size to recover file
                ndata = int(os.stat(filename).st_size)-self.headersize
                np_rec = ndata // self.particlesize
                if np_rec or ndata % self.particlesize:
                    self._np = np_rec
                    self._hdr['nparticles'] = np_rec
                    _warning("Input file appears to not have been closed"
                             f" properly. Recovered {np_rec} particles.")

                    comments = ( self._hdr.get('comments_raw')
                                 or self._hdr['comments'] )[:]
                    for ic in range(len(comments)):
                        c = comments[ic]
                        if not c.startswith(b'stat:sum:'):
                            continue
                        ok, (key,val) = _parse_statsum_comment( c)
                        if not ok:
                            raise MCPLError('Unexpected problems decoding'
                                            'stat:sum: comment second time')
                        if val != -1.0:
                            newc = encode_stat_sum( key, -1.0 ).encode('ascii')
                            if len(c) != len(newc):
                                raise MCPLError("Unexpected statsum encoding"
                                                " length")
                            comments[ic] = newc
                            _warning(f"Marking stat:sum:{key} "
                                     "entry as not available (-1) since file"
                                     " not closed properly.")
                    if 'comments_raw' in self._hdr:
                        self._hdr['comments_raw'] = comments
                        self._hdr['comments'] = [c.decode('utf-8','replace')
                                                 for c in comments]
                    else:
                        self._hdr['comments'] = comments
                    #Invalidate any already loaded stat sum dict:
                    if 'stat_sum' in self._hdr:
                        del self._hdr['stat_sum']
        elif _recover and not filename.endswith('.gz'):
            #Uncompressed files with particles must have exactly the size
            #given by their header (like in mcpl.c):
            size = int(os.stat(filename).st_size)
            expected = self.headersize + self.nparticles * self.particlesize
            if size < expected:
                raise MCPLError('Input file is truncated (it has fewer'
                                ' particles than given in its header)')
            if size > expected:
                raise MCPLError('Input file has unexpected data after its'
                                ' particles')

        #prepare dtype for reading 1 particle:
        udinfo, uddtype = None, None
        if self.userdata_layout is not None:
            #(userdata is a structured field, which is not unpacked until used):
            from ._userdata import userdata_dtype
            uddtype = userdata_dtype(self.userdata_layout)
            udinfo = ( self.userdata_layout, uddtype.newbyteorder(self.endianness) )
        self._pdt = record_dtype(self.opt_singleprec,self.opt_polarisation,
                                 self.opt_universalweight,self.opt_universalpdgcode,
                                 self.opt_userflags,uddtype).newbyteorder(self.endianness)

        #Init position and caches (don't read first block yet):
        self._ipos = 0
        self._blocklength = int(blocklength)
        self._iblock = 0
        self._nblocks = self.nparticles // self._blocklength + (1 if self.nparticles%self._blocklength else 0)
        #reuse same block object for whole file (to reuse fixed columns and internal caches)
        self._currentblock = MCPLParticleBlock(self.opt_polarisation,self.opt_userflags,
                                               self.opt_universalweight,self.opt_universalpdgcode,self.version,
                                               udinfo,self._pdt)

    @property
    def blocklength(self):
        """Number of particles read by each call to read_block()"""
        return self._blocklength

    def _open_file(self,filename):
        assert isinstance(filename,(bytes,str))

        self._fileclose()
        self._fileclose = lambda : None

        #Try to mimic checks and capabilities of mcpl.c as closely as possible
        #here (including the ability of gzopen to open uncompressed files),
        #which is why the slightly odd order of some checks below.

        try:
            fh = open(filename,'rb')  # noqa: SIM115
        except OSError as e:
            if e.errno == 2:
                fh = None#file not found
            else:
                raise
        if not fh:
            raise MCPLError('Unable to open file!')

        self._fileclose()
        self._fileclose = lambda : fh.close()

        is_gz = False
        if filename.endswith('.gz'):
            is_gz = True
            try:
                import gzip
            except ImportError:
                raise MCPLError('can not open compressed files since gzip module is absent')
            try:
                if (fh.read(4)==b'MCPL'):
                    #This is actually not a gzipped file, mimic gzopen in mcpl.c by
                    #magically being able to open .mcpl files that are mistakenly named
                    #as .mcpl.gz
                    is_gz = False
            except (OSError, EOFError):
                pass
            fh.seek(0)

        self._is_gz = is_gz
        if is_gz:
            raw, fh = fh, gzip.GzipFile(fileobj=fh)
            if not fh:
                raise MCPLError('failed to open compressed file')
            #(closing the GzipFile does not close the file given to it):
            def close():
                fh.close()
                raw.close()
            self._fileclose = close

        if not is_gz:
            #not gzipped input - read bytes by passing filehandle to np.fromfile
            self._fileread = lambda dtype,count : np.fromfile(fh,dtype=np.dtype(dtype),count=np.squeeze(count))
        else:
            #gzipped input - read bytes via filehandle and use np.frombuffer to decode

            #list of exception types that might indicate read errors (TypeError
            #and struct.error are in the list due to bugs in the python 3.3 gzip
            #module):
            read_errors=[ IOError, OSError, EOFError, TypeError]
            import struct
            if hasattr(struct,'error'):
                read_errors += [struct.error]
            read_errors = tuple(read_errors)
            def fread_via_buffer(dtype,count):
                dtype,count=np.dtype(dtype),np.squeeze(count)
                assert count>0
                n = dtype.itemsize * count
                try:
                    x = fh.read( n )
                except read_errors:
                    x = ()
                if len(x)==n:
                    return np.frombuffer(x,dtype=dtype, count=count)
                else:
                    return np.ndarray(dtype=dtype,shape=0)#incomplete read => return empty array
            self._fileread = fread_via_buffer
        self._fileseek = lambda pos : fh.seek(pos)

    #two methods needed for usage in with-statements:

    def __enter__(self):
        return self

    def __exit__(self, ttype, value, traceback):
        self._fileclose()
        self._fileclose = lambda : None

    @property
    def pick(self):
        """ParticleFilter picking the particles when reading (None if not
        given)"""
        return self._flt

    @property
    def edit(self):
        """Edit (ParticleEdit) applied when reading (None if no edits)"""
        return self._edt

    def read_block(self):
        """Read and return next block of particles (None when EOF). Similar to read(),
        but returned \"particle\" object actually represents a whole block of
        particles, and the fields on it are thus (numpy) arrays of numbers
        rather than single numbers.  See also the particle_blocks property for
        an iterator-based access to blocks."""
        if not self._filtered:
            b = self._read_raw_block()
            if self._nonfinite_mask is not None:
                self._warn_nonfinite()
            return b
        if self._fblocks is None:
            self._fblocks = self._picked_blocks()
        return next(self._fblocks,None)

    @property
    def _filtered(self):
        """Whether the particles are picked, edited or in a range"""
        return not ( self._flt is None and self._edt is None
                     and not self._skip and self._limit is None )

    def _picked_blocks(self):
        """Blocks of picked and edited particles (in the range of skip and
        limit), merging small picks"""
        start, end = _particle_range(self.nparticles,self._skip,self._limit)
        #(the blocks before the range are not read):
        first = start // self._blocklength
        if first and self._iblock == 0:
            self._iblock, self._ipos = first, first * self._blocklength
            self._fileseek(self.headersize+first*self._blocklength*self.particlesize)
        pending, npending = [], 0
        def finish():
            b = _concat_blocks(pending)
            if self._edt is not None:
                b = _EditedParticleBlock(b,self._edt(b))
            return b
        raw = iter(self._read_raw_block,None) if start < end else ()
        for b in _blocks_in_range(raw,start,end):
            if self._nonfinite_mask is not None:
                self._warn_nonfinite()
            if self._flt is not None:
                b = b[self._flt(b)]
            if len(b):
                pending.append(b)
                npending += len(b)
            if npending >= self._blocklength:
                yield finish()
                pending, npending = [], 0
        if pending:
            yield finish()

    def _read_raw_block(self):
        if self._iblock>=self._nblocks:
            return None
        #read next block:
        to_read = self._blocklength
        if self._iblock+1==self._nblocks and self._np%self._blocklength:
            to_read = self.nparticles%self._blocklength#last block is shorter
        x = self._fileread(dtype=self._pdt,count=to_read)
        if len(x)!=to_read:
            raise MCPLError('Errors encountered while attempting to read particle data.')
        self._currentblock._set_data(x,self._iblock*self._blocklength)
        self._iblock += 1
        self._nonfinite_mask = None
        if ( self._check_nonfinite and not self._warned_nonfinite
             and not _surely_finite(self._currentblock) ):
            masks = _nonfinite_masks(self._currentblock,self.opt_polarisation)
            if masks:
                self._nonfinite_mask = np.logical_or.reduce(list(masks.values()))
        return self._currentblock

    def _warn_if_nonfinite(self, block):
        """Warn (once per file) if block (from this file) has NaN or infinite
        values"""
        if self._warned_nonfinite:
            return
        masks = _nonfinite_masks(block,self.opt_polarisation)
        if masks:
            self._warned_nonfinite = True
            i = min( int(np.argmax(m)) for m in masks.values() )
            _warning('File contains particles with NaN or infinite values (first'
                     f' one found at index {block.fileidx[i]}).'
                     ' They can not be added to other MCPL files.')

    def _warn_nonfinite(self, local_idx = None):
        """Warn (once per file) if the current block (or the particle in it at
        local_idx) has NaN or infinite values."""
        m = self._nonfinite_mask
        if m is None or ( local_idx is not None and not m[local_idx] ):
            return
        i = int(np.argmax(m)) if local_idx is None else local_idx
        self._nonfinite_mask = None
        self._warned_nonfinite = True
        _warning('File contains particles with NaN or infinite values (first'
                 f' one found at index {self._currentblock.file_offset + i}).'
                 ' They can not be added to other MCPL files.')

    def read(self):
        """Read and return next particle in file (None when EOF) as a particle object,
        with particle state information available on fields as seen in the following
        example:

          p = mcplfile.read()
          if p is not None:
               print(p.x,p.y,p.z)
               print(p.ux,p.uy,p.uz)
               print(p.polx,p.poly,p.polz)
               print(p.ekin,p.time,p.weight,p.userflags)

        See also the particles property for an iterator-based access to
        particles. Furthermore, note that the read_blocks() function and
        the particle_blocks property provides block-based access, which can
        improve performance dramatically."""
        if self._filtered:
            if self._fparts is None:
                self._fparts = self._picked_particles()
            return next(self._fparts,None)
        if self._ipos >= self._np:
            return None#end of file
        p = self._currentblock.get_by_global(self._ipos)
        if p is None:
            self._read_raw_block()
            p = self._currentblock.get_by_global(self._ipos)
        self._ipos += 1
        if self._nonfinite_mask is not None:#(the check is cheaper than the call)
            self._warn_nonfinite(p._i)
        return p

    def _picked_particles(self):
        while True:
            b = self.read_block()
            if b is None:
                return
            for i in range(len(b)):
                yield b[i]

    def skip_forward(self,n):

        """skip n positions forward in file. (returns False when there is no
           particle at the new position, otherwise True)"""
        if self._filtered:
            raise MCPLError('skip_forward can not be used with files opened'
                            ' with pick, edit, skip or limit')
        inew = self._ipos + int(n)
        if inew <= self._ipos:
            if inew == self._ipos:
                return self._ipos < self._np
            raise MCPLError("Requested skip is not in the forward direction")
        if self._currentblock.contains_ipos(inew):
            #handle case of small skip within currently loaded block first:
            self._ipos = inew
            return True
        if inew >= self._np:
            self._ipos = self.nparticles
            self._iblock = self._nblocks
            return False#EOF
        #skip to a given block:
        self._iblock = inew // self._blocklength
        assert self._iblock < self._nblocks#should not be eof
        blockstart = self.headersize+self._iblock*self._blocklength*self.particlesize
        assert blockstart > self._ipos#seek should be *forward*
        self._fileseek(blockstart)
        self._ipos = inew
        if not self._read_raw_block():
            raise MCPLError('Unexpected failure to load particle block')
        return True

    @property
    def particles(self):
        """Use to iterate over all particles in file:

           for p in thefile.particles:
               print(p.x,p.y,p.z)
        """
        self.rewind()
        while True:
            p=self.read()
            if p is None:
                break
            yield p

    @property
    def particle_blocks(self):
        """Use to iterate over all particles in file, returning a block of
        particles each time for efficiency:

           for p in thefile.particle_blocks:
               #(NB: the "values" here are actually arrays)
               print(p.x,p.y,p.z)
        """
        self.rewind()
        while True:
            p=self.read_block()
            if p is None:
                break
            yield p

    def rewind(self):
        """Rewind file, causing next calls to read() and read_blocks() to start again at
        the beginning of the file."""
        self._fileseek(self.headersize)
        self._ipos = 0
        self._iblock = 0
        self._currentblock._set_data(None,None)
        self._fblocks, self._fparts = None, None

    @property
    def version(self):
        """MCPL format version of the file"""
        return self._hdr['version']
    @property
    def nparticles(self):
        """Number of particles in file"""
        return self._hdr['nparticles']
    @property
    def particlesize(self):
        """Uncompressed per-particle storage size in file [bytes]"""
        return self._hdr['particlesize']
    @property
    def headersize(self):
        """Uncompressed size of the file header [bytes]"""
        return self._hdr['headersize']
    @property
    def endianness(self):
        """Endianness of numbers in file"""
        return self._hdr['endianness']
    @property
    def opt_userflags(self):
        """Whether or not userflags are enabled in file"""
        return self._hdr['opt_userflags']
    @property
    def userdata_layout(self):
        """Layout of the per-particle userdata in the file (e.g.
        "temp:float32,origin:int32"), or None if the file has no userdata"""
        return self._hdr['userdata_layout']
    @property
    def userdata_size(self):
        """Bytes of userdata per particle (0 if the file has no userdata)"""
        return self._hdr['userdata_size']
    @property
    def opt_universalpdgcode(self):
        """Global PDG code for all particles in file (a value of 0 means that
        PDG codes are stored per-particle)"""
        return self._hdr['opt_universalpdgcode']
    @property
    def opt_polarisation(self):
        """Whether or not polarisation info is enabled in file"""
        return self._hdr['opt_polarisation']
    @property
    def opt_singleprec(self):
        """Whether or not floating point numbers in particle data are stored in
        single-precision (32bit) rather than double-precision (64bit)"""
        return self._hdr['opt_singleprec']
    @property
    def opt_universalweight(self):
        """Global weight for all particles in file (a value of 0.0 means that
        weights are stored per-particle)"""
        return self._hdr['opt_universalweight']
    @property
    def sourcename(self):
        """Name of application that wrote the MCPL file"""
        return self._hdr['sourcename']
    @property
    def comments(self):
        """List of custom comments (strings) embedded in the file header"""
        return self._hdr['comments']
    @property
    def blobs(self):
        """Dictionary of custom binary blobs (byte-arrays) embedded in the file
        header. Each such blob is associated with a key, which is also the key
        in the dictionary"""
        return self._hdr['blobs']
    @property
    def blob_storage_order(self):
        """In-file storage order of binary blobs (as list of keys)."""
        return self._hdr['blobkeys']

    @property
    def stat_sum(self):
        """Access "stat:sum:..." data from file comments as a convenient
        key->value dictionary. Note that any key present with a value of -1 in
        the file will get the value None here in the Python interface.
        """
        h = self._hdr
        d = h.get('stat_sum')
        if d is not None:
            return d
        from types import MappingProxyType  # read-only view of dict
        d = MappingProxyType(
            _parse_statsum( h.get('comments_raw',None) or h.get('comments') )
        )
        h['stat_sum'] = d
        return d

    def _loadhdr(self):
        self._hdr={}
        h=self._hdr
        x=self._fileread(dtype='u1',count=8)
        if len(x)>=4 and not all(x[0:4]==(77,67,80,76)):
            raise MCPLError('File is not an MCPL file!')
        if len(x)!=8:
            raise MCPLError('Error while reading first bytes of file!')
        x=list(map(chr,x[4:]))
        if not all( c in '0123456789' for c in x[0:3] ):
            raise MCPLError('File is in an unsupported MCPL version!')
        version = int(''.join(x[0:3]))
        if version not in (2,3,4):
            raise MCPLError('File is in an unsupported MCPL version!')
        h['version']=version
        endianness = x[3]
        if endianness not in ('L','B'):
            raise MCPLError('Unexpected value in endianness field!')
        h['endianness']=endianness
        dt= np.dtype("u8,5u4,i4,2u4").newbyteorder(endianness)
        y = self._fileread(dtype=dt,count=1)
        if len(y)!=1:
            raise MCPLError('Errors encountered while attempting to read header')
        (nparticles,(ncomments,nblobs,opt_userflags,opt_polarisation,opt_singleprec),
         opt_universalpdgcode,(particlesize,_tmp)) = y[0]
        #convert all int types to python 'int' (which is 64bit), to avoid
        #conversions like int+np.uint64->float, and flags to bool:
        nparticles = int(nparticles)
        self._np = nparticles#needs frequent access
        if int(ncomments) + int(nblobs) > _max_header_entries:
            raise MCPLError(_header_too_many_msg)
        particlesize = int(particlesize)
        opt_universalpdgcode = int(opt_universalpdgcode)
        #The flags in the header must have exactly the values of the format:
        #0x1 or 0x0 (for userflags, polarisation, single precision and
        #universal weight). In format version 4, the userflags field also holds
        #0x2 if the particles have userdata (and the header has a userdata
        #layout), so files in version 4 without userdata are identical to
        #files in version 3 except for the version number:
        if opt_userflags > ( 3 if version >= 4 else 1 ):
            raise MCPLError('unexpected value of userflags field')
        if opt_polarisation > 1:
            raise MCPLError('unexpected value of polarisation field')
        if opt_singleprec > 1:
            raise MCPLError('unexpected value of precision field')
        if _tmp > 1:
            raise MCPLError('unexpected value of universal weight field')
        has_userdata = bool( opt_userflags & 0x2 )
        opt_userflags = bool( opt_userflags & 0x1 )
        opt_polarisation = bool(opt_polarisation)
        opt_singleprec = bool(opt_singleprec)
        opt_universalweight = 0.0
        if _tmp:
            uw = self._fileread(dtype=np.dtype('f8').newbyteorder(endianness),count=1)
            if len(uw) != 1:
                raise MCPLError('Errors encountered while attempting to read header')
            opt_universalweight = float(uw[0])
        if _tmp and not ( 0.0 < opt_universalweight < float('inf') ):
            #(must be positive and finite, as when writing files)
            raise MCPLError('invalid universal weight')
        h['nparticles']=nparticles
        h['particlesize']=particlesize
        h['opt_universalpdgcode']=opt_universalpdgcode
        h['opt_userflags'] = opt_userflags
        h['opt_polarisation'] = opt_polarisation
        h['opt_singleprec'] = opt_singleprec
        h['opt_universalweight'] = opt_universalweight
        h['userdata_layout'] = None
        h['userdata_size'] = 0

        #The size of the header read so far (to refuse too large headers before
        #reading them):
        hdrpos = [ 48 + ( 8 if _tmp else 0 ) ]

        def readarr():
            ll = self._fileread(dtype=np.dtype('u4').newbyteorder(endianness),
                               count=1)
            if len(ll)!=1:
                raise MCPLError('Errors encountered while attempting to read header')
            hdrpos[0] += 4 + int(ll[0])
            if hdrpos[0] > _max_header_size:
                raise MCPLError(_header_too_large_msg)
            if ll==0:
                return b''
            cont = self._fileread(dtype='u1',count=ll)
            if len(cont)!=ll:
                raise MCPLError('Errors encountered while attempting to read header')
            return cont.tobytes() if hasattr(cont,'tobytes') else cont.tostring()

        def readstr():
            #(strings must not contain null characters)
            res = readarr()
            if b'\0' in res:
                raise MCPLError('encountered unexpected null-byte in string'
                                ' read from file')
            return res

        if has_userdata:
            #Userdata layout (only in version 4, and only with userdata):
            from ._userdata import userdata_dtype
            layout = readstr().decode('ascii','replace')
            udsize = userdata_dtype(layout).itemsize
            h['userdata_layout'] = layout
            h['userdata_size'] = udsize
        #The particle size in the header must be consistent with the size of
        #the fields:
        fp = 4 if opt_singleprec else 8
        expected = ( 7*fp + ( 3*fp if opt_polarisation else 0 )
                     + ( 0 if opt_universalpdgcode else 4 )
                     + ( 0 if _tmp else fp )
                     + ( 4 if opt_userflags else 0 ) + h['userdata_size'] )
        if particlesize != expected:
            raise MCPLError('unexpected particle size')
        sourcename = readstr()
        comments=[]
        for i in range(ncomments):
            comments += [readstr()]
        blobs={}
        #blobs_user={}
        blobkeys = []#to keep order available to dump_hdr
        for i in range(nblobs):
            blobkeys += [readstr()]
            problem = blobkey_problem(blobkeys[-1]) if version >= 4 else None
            if problem:
                raise MCPLError(f'File has an invalid blob key ({problem}).')
        for i,bk in enumerate(blobkeys):
            blobs[bk] = readarr()
        headersize = ( 48 + 4 + len(sourcename)
                       + (8 if opt_universalweight else 0)
                       + ( 4 + len(h['userdata_layout'])
                           if h['userdata_layout'] is not None else 0 )
                       + sum(4+len(c) for c in comments)
                       + sum(8+len(bk)+len(bv) for bk,bv in blobs.items()) )
        h['headersize'] = headersize

        saw_any_statsum = False
        saw_any_unsupportedstat = False
        for c in comments:
            if not c.startswith(b'stat:'):
                continue
            if c.startswith(b'stat:sum:'):
                saw_any_statsum = True
            else:
                saw_any_unsupportedstat = True

        if self._str_decode:
            #attributes return python strings since raw_strings was not set, so
            #we must decode these before returning to the user. But for output
            #compatibility with mcpltool-c, dump_hdr() will use original
            #ones above.
            h['sourcename_raw'] = sourcename
            h['comments_raw'] = comments
            h['blobs_raw'] = blobs
            h['blobkeys_raw'] = blobkeys
            h['sourcename'] = sourcename.decode('utf-8','replace')
            h['comments'] = [c.decode('utf-8','replace') for c in comments]
            h['blobkeys'] = [bk.decode('utf-8','replace') for bk in blobkeys]
            h['blobs'] = {k.decode('utf-8','replace'): v for k,v in blobs.items()}
        else:
            #raw bytes all the way
            h['sourcename'] = sourcename
            h['comments'] = comments
            h['blobs'] = blobs
            h['blobkeys'] = blobkeys

        if saw_any_statsum:
            #Trigger loading of stat:sum:'s already, to emit errors in case of
            #detected issues.
            _ = self.stat_sum
        if saw_any_unsupportedstat:
            _warning("Opened file with unknown \"stat:...\" "
                     "syntax in comments. The present installation only has"
                     " special support for \"stat:sum:...\" comments. It"
                     " might be a sign that your installation of MCPL is"
                     " too old.")

    def dump_hdr(self):
        """Dump file header to stdout (like the mcpltool command)"""
        h=self._hdr
        def print_datastring(prefix,s,postfix):
            print(prefix,end='')
            _output_bytearray_raw(s)
            print(postfix)
        print("\n  Basic info")
        print(f"    Format             : MCPL-{h['version']}")
        print(f"    No. of particles   : {h['nparticles']}")
        print(f"    Header storage     : {h['headersize']} bytes")
        print(f"    Data storage       : {h['nparticles']*h['particlesize']} bytes")
        print("\n  Custom meta data")
        print_datastring('    Source             : "',
                         h.get('sourcename_raw',None) or h.get('sourcename'),
                         '"')
        comments = h.get('comments_raw',None) or h.get('comments')
        print(f"    Number of comments : {len(comments)}")
        for i,c in enumerate(comments):
            print_datastring(f'          -> comment {i} : "',c,'"')
        blobs = h.get('blobs_raw',None) or h.get('blobs')
        blobkeys = h.get('blobkeys_raw',None) or h.get('blobkeys')
        print(f"    Number of blobs    : {len(h['blobs'])}")
        for bk in blobkeys:
            print_datastring(f'          -> {len(blobs[bk])} bytes of data with key "',bk,'"')
        print("\n  Particle data format")
        print("    User flags         : %s"%("yes" if h['opt_userflags'] else "no"))
        print("    Polarisation info  : %s"%("yes" if h['opt_polarisation'] else "no"))
        if h['userdata_layout'] is not None:
            print(f"    User data          : {h['userdata_size']} bytes"
                  f" (layout \"{h['userdata_layout']}\")")
        s = "    Fixed part. type   : "
        if h['opt_universalpdgcode']:
            s += f"yes (pdgcode {h['opt_universalpdgcode']})"
        else:
            s += "no"
        print(s)
        s = "    Fixed part. weight : "
        if h['opt_universalweight']:
            s += "yes (weight {:g})".format(h['opt_universalweight'])
        else:
            s += "no"
        print(s)
        print("    FP precision       : %s"%("single" if h['opt_singleprec'] else "double"))
        print("    Endianness         : {}".format({'L':'little','B':'big'}[h['endianness']]))
        print(f"    Storage            : {h['particlesize']} bytes/particle")
        print()

    def dump_particles(self,limit=10,skip=0,pick=None,_view=None):
        """Dump a list of particles to stdout (like the mcpltool command). The
        limit and skip parameters can be used to respectively limit the
        number of particles printed and to skip past the first particles
        (after any skip, limit and pick given when opening the file). Use limit=0 to disable the limit. If pick is given (an
        expression or a ParticleFilter), only the picked particles are shown,
        and limit and skip apply to those."""

        #1) update position
        self.rewind()
        if _view is not None:
            #(the particles of a _FileView of this file, for mcpltool):
            particles = _picked_particles(_view,pick,skip)
        elif pick is None and not self._filtered:
            self.skip_forward(skip)
            particles = iter(self.read,None)
        else:
            particles = _picked_particles(self,pick,skip)

        #2) print column titles:
        opt_pol,opt_uf,opt_uw = self.opt_polarisation,self.opt_userflags,self.opt_universalweight
        s = "index     pdgcode   ekin[MeV]       x[cm]       y[cm]       z[cm]          ux          uy          uz    time[ms]"
        if not opt_uw:
            s += "      weight"
        if opt_pol:
            s += "       pol-x       pol-y       pol-z"
        if opt_uf:
            s += "  userflags"
        udsize = self.userdata_size
        if udsize:
            s += "  userdata"
        print(s)

        #3) loop and print
        fmt1 = "%5i %11i %11.5g %11.5g %11.5g %11.5g %11.5g %11.5g %11.5g %11.5g"
        fmt2 = " %11.5g %11.5g %11.5g"
        for i in range(limit if limit!=0 else self.nparticles):
            p = next(particles,None)
            if p is None:
                break
            s = fmt1%( p.fileidx,p.pdgcode,p.ekin,p.x,p.y,p.z,
                       p.ux,p.uy,p.uz,p.time )
            if not opt_uw:
                s += f" {p.weight:11.5g}"
            if opt_pol:
                s+=fmt2%( p.polx, p.poly, p.polz )
            if opt_uf:
                s+=f" 0x{p.userflags:08x}"
            if udsize:
                #Bytes in hex (at most the first 16):
                raw = p.userdata.tobytes()
                s += '  ' + raw[:16].hex() + ( '...' if udsize > 16 else '' )
            print(s)

    def to_scipp(self, *, skip = 0, limit = None, pick = None, coords = None,
                 vectors = False, variances = True, dim = 'particle'):
        """Particles of the file as a scipp DataArray. The particles are read
        from the start of the file (after any skip, limit, pick and edit given
        when opening the file), skipping the first skip of them, and picking
        only those matching pick if given (an expression or a
        ParticleFilter, in which case skip applies to the picked
        particles). At most limit particles are converted: by default at most
        100 million, with a warning if particles are left out, and limit=0
        converts all of them. See also scipp_blocks, which converts the
        particles block by block.

        The result has one entry per particle, along the dimension dim. Its
        data are the weights (with variances weight^2, unless variances is
        False), and its coordinates are x, y, z [cm], ux, uy, uz, ekin [MeV],
        time [ms] and pdgcode, plus polx, poly, polz (if the file has
        polarisation), userflags (if the file has userflags) and the fields
        of the userdata (if any, with array fields split into one coordinate
        per element, e.g. tags_0, tags_1, ..., and a warning and the prefix
        "userdata_" for fields named like one of the other coordinates). With
        vectors=True, the positions, directions and polarisations are instead
        3-vectors named position, direction and polarisation.

        Extra coordinates can be calculated with expressions (see
        ParticleFilter), given as a dictionary of names and expressions. The
        units of the values follow from the expressions (in combinations of
        cm, MeV and ms, which scipp can convert), for instance:

           da = f.to_scipp( coords = { 'wavelength' : 'wavelength',
                                       'r' : 'hypot(x,y)' } )
           da.coords['wavelength'] = da.coords['wavelength'].to(unit='angstrom')
           da.hist( wavelength = 100 ).plot()

        This requires the scipp package (pip install "mcpl-python[scipp]")."""
        flt, fcts = self._scipp_args(pick,coords)
        from ._scipp import file_to_scipp
        return file_to_scipp( self, skip = skip, limit = limit, flt = flt,
                              coord_functions = fcts, vectors = vectors,
                              variances = variances, dim = dim )

    def scipp_blocks(self, *, pick = None, coords = None, vectors = False,
                     variances = True, dim = 'particle'):
        """Iterate over the particles of the file as scipp DataArrays, one for
        each block of particles (see the particle_blocks property), with the
        same contents and parameters as for to_scipp. For instance:

           for da in f.scipp_blocks( pick = 'pdgcode == neutron' ):
               print( da.sum().value )

        This requires the scipp package (pip install "mcpl-python[scipp]")."""
        flt, fcts = self._scipp_args(pick,coords)
        from ._scipp import file_scipp_blocks
        return file_scipp_blocks( self, flt = flt, coord_functions = fcts,
                                  vectors = vectors, variances = variances,
                                  dim = dim )

    def _scipp_args(self, pick, coords):
        flt, fcts = None, None
        if pick is not None or coords is not None:
            from ._expressions import _as_filter, _quantity_functions
            flt = _as_filter(pick) if pick is not None else None
            fcts = _quantity_functions(coords) if coords is not None else None
        return flt, fcts

def _picked_particles(mcplfile,pick,skip=0):
    """Iterate over picked particles in file, skipping the first skip of
    them."""
    flt = None
    if pick is not None:
        from ._expressions import _as_filter
        flt = _as_filter(pick)
    for b in mcplfile.particle_blocks:
        for i in ( np.flatnonzero(flt(b)) if flt is not None else range(len(b)) ):
            if skip > 0:
                skip -= 1
                continue
            yield b[int(i)]



def _particle_range( n, skip, limit ):
    """The range of particles (first, end) of a file of n particles, without
    the first skip of them and with at most limit (all if limit is None; the
    -l option of mcpltool, where 0 means all, is given as limit or None)"""
    first = min( skip or 0, n )
    return first, n if limit is None else min( n, first + limit )

def _blocks_in_range( blocks, first, end ):
    """The parts of the blocks (of a file, in their order) with the particles
    from first to end (see _particle_range), as new blocks, since the blocks of
    files are reused by the next read"""
    for b in blocks:
        off = b.file_offset
        if off + len(b) <= first:
            continue
        if off >= end:
            break
        yield b[max(0,first-off):min(len(b),end-off)]

class _FileView:
    """Read-only view of the particles of an MCPLFile, for the -s, -l, -p and
    -E options of mcpltool: in a range of the file (without the first skip
    particles, and with at most limit particles, all if limit is None or 0),
    then picked with pick (a ParticleFilter, or None), then edited with edit
    (a ParticleEdit, or None)."""
    def __init__(self, mcplfile, skip = 0, limit = None, pick = None,
                 edit = None):
        self._f = mcplfile
        self._skip, self._end = _particle_range(mcplfile.nparticles,skip,limit or None)
        self.pick, self.edit = pick, edit
        self._n = None if pick is not None else self._end - self._skip
    def __getattr__(self, name):
        return getattr(self._f, name)
    def __enter__(self):
        return self
    def __exit__(self, ttype, value, traceback):
        self._f.__exit__(ttype,value,traceback)
    @property
    def nparticles(self):
        if self._n is None:
            self._n = sum( len(b) for b in self.particle_blocks )
        return self._n
    @property
    def particle_blocks(self):
        for b in _blocks_in_range(self._f.particle_blocks,self._skip,self._end):
            if self.pick is not None:
                b = b[self.pick(b)]
            if self.edit is not None:
                b = _EditedParticleBlock(b,self.edit(b))
            yield b

