
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

"""Particles and blocks of particles read from MCPL files."""

__all__ = ['MCPLParticle', 'MCPLParticleBlock']

from ._common import MCPLError
from ._numpy import np, np_fma
from ._physics import wavelength_checked


class MCPLParticle:
    """Object representing a single particle"""

    def __init__(self,block,idx):
        """For internal use only - users should not normally create MCPLParticle objects themselves"""
        self._b = block#can we make it a weak ref, to make sure multiple blocks are not kept around?
        self._i = idx
    @property
    def position(self):
        """position as 3-dimensional array [cm]"""
        return self._b.position[self._i]
    @property
    def direction(self):
        """normalised momentum direction as 3-dimensional array"""
        return self._b.direction[self._i]
    @property
    def polarisation(self):
        """polarisation vector as 3-dimensional array"""
        return self._b.polarisation[self._i]
    @property
    def x(self):
        """x-coordinate of position [cm]"""
        return self._b.x[self._i]
    @property
    def y(self):
        """y-coordinate of position [cm]"""
        return self._b.y[self._i]
    @property
    def z(self):
        """z-coordinate of position [cm]"""
        return self._b.z[self._i]
    @property
    def ux(self):
        """x-coordinate of normalised momentum direction"""
        return self._b.ux[self._i]
    @property
    def uy(self):
        """y-coordinate of normalised momentum direction"""
        return self._b.uy[self._i]
    @property
    def uz(self):
        """z-coordinate of normalised momentum direction"""
        return self._b.uz[self._i]
    @property
    def polx(self):
        """x-coordinate of polarisation vector"""
        return self._b.polx[self._i]
    @property
    def poly(self):
        """y-coordinate of polarisation vector"""
        return self._b.poly[self._i]
    @property
    def polz(self):
        """z-coordinate of polarisation vector"""
        return self._b.polz[self._i]
    @property
    def ekin(self):
        """kinetic energy [MeV]"""
        return self._b.ekin[self._i]
    @property
    def time(self):
        """time-stamp [millisecond]"""
        return self._b.time[self._i]
    @property
    def weight(self):
        """weight or intensity"""
        return self._b.weight[self._i]
    @property
    def userflags(self):
        """custom per-particle flags"""
        return self._b.userflags[self._i]
    @property
    def userdata(self):
        """custom per-particle data (numpy record with the fields of the
        userdata layout of the file, e.g. p.userdata['temp']), or None if the
        file has no userdata"""
        ud = self._b.userdata
        return None if ud is None else ud[self._i]
    @property
    def wavelength(self):
        """wavelength [Aa] (only for neutrons and gammas with non-zero kinetic
        energy, otherwise MCPLError is raised)"""
        return wavelength_checked(self.ekin, self.pdgcode)
    @property
    def pdgcode(self):
        """MC particle number from the Particle Data Group (2112=neutron, 22=gamma, ...)"""
        return self._b.pdgcode[self._i]
    @property
    def fileidx(self):
        """Particle position in file (counting from 0)"""
        if self._b._indices is not None:
            return int(self._b._indices[self._i])
        return self._b._offset + self._i
    @property
    def file_index(self):
        """Deprecated name of fileidx"""
        import warnings
        warnings.warn('MCPLParticle.file_index is deprecated, use fileidx'
                      ' instead', DeprecationWarning, stacklevel=2)
        return self.fileidx

class MCPLParticleBlock:
    """Object representing a block of particle. Fields are arrays rather than single
    numbers, but otherwise have the same meaning as on the MCPLParticle class."""

    def __init__(self,opt_polarisation,opt_userflags,opt_globalw,opt_globalpdg,fmtversion,
                 udinfo = None, pdt = None):
        """For internal use only - users should not normally create MCPLParticle objects themselves"""
        self._ctor_args = (opt_polarisation,opt_userflags,opt_globalw,opt_globalpdg,fmtversion,
                           udinfo,pdt)
        #(numpy dtype of the particle data in the file):
        self._pdt = pdt
        #(userdata layout and dtype, or None):
        self._udinfo = udinfo
        #empty block (set offset to max int to ensure d<0 in contains_ipos and get_by_global:
        self._offset = 9223372036854775807
        #non-constant columns (never the same in all blocks), empty until set:
        self._data = self._empty_data()
        #potentially constant columns (first entry says whether non-constant, second is cache):
        self._polx = [opt_polarisation,None]
        self._poly = [opt_polarisation,None]
        self._polz = [opt_polarisation,None]
        self._uf = [bool(opt_userflags),None]
        self._w = [not opt_globalw,None]
        self._pdg = [not opt_globalpdg,None]
        self._opt_globalw = opt_globalw
        self._opt_globalpdg = opt_globalpdg
        self._fmtversion = fmtversion
        self._view_pos = None
        self._view_pol = None
        self._view_dir = None
        self._pos_cache,self._pol_cache = None,None#extra ndarrays for numpy 1.14 issue
        #positions in file of the particles, for selected particles (otherwise
        #given by the offset):
        self._indices = None
        #initialise the caches:
        self._set_data(None,None)

    def _set_data(self,data,file_offset):
        #always present, but must unpack:
        self._ux,self._uy,self._uz,self._ekin = None,None,None,None
        self._f64 = {}
        self._view_dir = None

        #reset non-constant columns:
        for ncc in [self._polx,self._poly,self._polz,self._uf,self._w,self._pdg]:
            if ncc[0]:
                ncc[1]=None
        self._view_pos = None
        if self._polx[0]:
            self._view_pol = None

        if data is None:
            self._offset = 9223372036854775807
            self._data = self._empty_data()
        else:
            self._data = data
            self._offset = file_offset

    def _empty_data(self):
        #Particle data without particles, so all fields are arrays of length 0
        #(an empty tuple if the dtype is not known):
        return np.zeros(0,dtype=self._pdt) if self._pdt is not None else ()

    def contains_ipos(self,ipos):
        """Whether the particle at position ipos in the file is in the block"""
        d=ipos-self._offset
        return d>=0 and d<len(self._data)

    def __getitem__(self,ipos):
        """Access single particle in block by local position in block (not
        global position in file). Alternatively, select a subset of the
        particles with a slice, an array of indices, or a boolean mask (e.g.
        block[block.ekin<1e-6]), which returns a new MCPLParticleBlock with
        those particles. Such blocks can be passed to MCPLOutFile.add_particles
        like any other block."""
        if isinstance(ipos,(int,np.integer)):
            if ipos>=0 and ipos<len(self._data):
                return MCPLParticle(self,ipos)
            return None
        res = MCPLParticleBlock(*self._ctor_args)
        data = self._data[ipos]
        offset = 9223372036854775807#no well defined position in file
        if isinstance(ipos,slice):
            start,_,step = ipos.indices(len(self._data))
            if step == 1 and self._indices is None:
                offset = self._offset + start
        res._set_data(data,offset)
        res._indices = self.fileidx[ipos]
        return res

    def get_by_global(self,ipos):
        """Access single particle in block by global position in file"""
        d = ipos - self._offset
        if d>=0 and d<len(self._data):
            return MCPLParticle(self,d)
        return None

    @property
    def particles(self):
        """Use to iterate over all particles in block:

           for p in theblock.particles:
               print(p.x,p.y,p.z)
        """
        for i in range(len(self._data)):
            yield self[i]

    def __len__(self):
        return len(self._data)

    @property
    def wavelength(self):
        """wavelength [Aa] (only for blocks with just neutrons and gammas, with
        non-zero kinetic energy, otherwise MCPLError is raised)"""
        return wavelength_checked(self.ekin, self.pdgcode)

    @property
    def file_offset(self):
        """Particle position in file of first particle in block (counting from 0)"""
        return self._offset

    @property
    def fileidx(self):
        """Array with the positions in the file of the particles in the block
        (counting from 0), also for blocks with picked particles."""
        if self._indices is not None:
            return self._indices
        return np.arange(self._offset,self._offset+len(self._data),dtype=np.int64)

    @property
    def polx(self):
        """X-coordinate of polarisation vector of each particle (array)"""
        x = self._polx
        if x[0]:
            if x[1] is None:
                x[1] = self._data['polx'].astype(float)
            return x[1]
        if x[1] is None or len(x[1]) != len(self._data):
            x[1] = np.zeros(len(self._data),dtype=float)
        return x[1]

    @property
    def poly(self):
        """Y-coordinate of polarisation vector of each particle (array)"""
        x = self._poly
        if x[0]:
            if x[1] is None:
                x[1] = self._data['poly'].astype(float)
            return x[1]
        if x[1] is None or len(x[1]) != len(self._data):
            x[1] = np.zeros(len(self._data),dtype=float)
        return x[1]

    @property
    def polz(self):
        """Z-coordinate of polarisation vector of each particle (array)"""
        x = self._polz
        if x[0]:
            if x[1] is None:
                x[1] = self._data['polz'].astype(float)
            return x[1]
        if x[1] is None or len(x[1]) != len(self._data):
            x[1] = np.zeros(len(self._data),dtype=float)
        return x[1]

    @property
    def pdgcode(self):
        """MC particle number from the Particle Data Group (2112=neutron, 22=gamma, ...) of each particle (array)"""
        x = self._pdg
        if x[0]:
            if x[1] is None:
                x[1] = self._data['pdg']
            return x[1]
        if x[1] is None or len(x[1]) != len(self._data):
            x[1] = self._opt_globalpdg * np.ones(len(self._data),dtype=int)
        return x[1]

    @property
    def weight(self):
        """Weight or intensity of each particle (array)"""
        x = self._w
        if x[0]:
            if x[1] is None:
                x[1] = self._data['w'].astype(float)
            return x[1]
        if x[1] is None or len(x[1]) != len(self._data):
            x[1] = self._opt_globalw * np.ones(len(self._data),dtype=float)
        return x[1]

    @property
    def userdata(self):
        """Custom per-particle data of each particle (numpy structured array
        with the fields of the userdata layout of the file, e.g.
        block.userdata['temp']), or None if the file has no userdata. This is
        a view of the data read from the file, which is not unpacked or copied
        until used."""
        if self._udinfo is None:
            return None
        if not len(self._data):
            return np.zeros(0,dtype=self._udinfo[1])
        return self._data['ud']

    @property
    def userflags(self):
        """Custom per-particle flags of each particle (array)"""
        x = self._uf
        if x[0]:
            if x[1] is None:
                x[1] = self._data['uf']
            return x[1]
        if x[1] is None or len(x[1]) != len(self._data):
            x[1] = np.zeros(len(self._data),dtype=np.uint32)
        return x[1]

    @property
    def position(self):
        """Positions [cm] as array with shape (N,3)"""
        if self._view_pos is None:
            self._view_pos = np.stack((self.x,self.y,self.z),axis=1)
        return self._view_pos

    @property
    def polarisation(self):
        """Polarisation vectors as array with shape (N,3)"""
        if self._view_pol is None or len(self._view_pol) != len(self._data):
            self._view_pol = np.stack((self.polx,self.poly,self.polz),axis=1)
        return self._view_pol

    @property
    def direction(self):
        """Normalised momentum directions as array with shape (N,3)"""
        if self._view_dir is None:
            if self._ux is None:
                self._unpack()
            self._view_dir = np.stack((self._ux,self._uy,self._uz),axis=1)
        return self._view_dir

    @property
    def x(self):
        """X-coordinate of position [cm] of each particle (array)"""
        return self._double('x')
    @property
    def y(self):
        """Y-coordinate of position [cm] of each particle (array)"""
        return self._double('y')
    @property
    def z(self):
        """Z-coordinate of position [cm] of each particle (array)"""
        return self._double('z')
    @property
    def time(self):
        """Time-stamp [millisecond] of each particle (array)"""
        return self._double('t')
    @property
    def ux(self):
        """X-coordinate of normalised momentum direction of each particle (array)"""
        if self._ux is None:
            self._unpack()
        return self._ux
    @property
    def uy(self):
        """Y-coordinate of normalised momentum direction of each particle (array)"""
        if self._uy is None:
            self._unpack()
        return self._uy
    @property
    def uz(self):
        """Z-coordinate of normalised momentum direction of each particle (array)"""
        if self._uz is None:
            self._unpack()
        return self._uz
    @property
    def ekin(self):
        """Kinetic energy [MeV] of each particle (array)"""
        if self._ekin is None:
           self._ekin = abs(self._data['uve3']).astype(float)
        return self._ekin

    def _double( self, field ):
        """Values of a field of the packed data as native double precision
        numbers (like in the C API, also for files storing single precision
        numbers), cached for the block"""
        v = self._f64.get(field)
        if v is None:
            v = self._f64[field] = np.asarray(self._data[field],dtype=np.float64)
        return v

    def _unpack(self):
        #On demand unpacking of unit vector. We have to make a version of
        #mcpl.c's mcpl_unitvect_unpack_adaptproj which can be efficiently
        #delegated to the compiled numpy library:
        if self._fmtversion==2:
            return self._unpack_legacy()#old packing scheme
        in0 = self._data['uve1'].astype(float)
        in1 = self._data['uve2'].astype(float)
        #NB: numpy 1.3 does not have copysign fct, only signbit:
        in2 = np.where(np.signbit(self._data['uve3']),-1.0,1.0)
        #reciprocals without zero division (fallback value will never be used):
        in0inv = 1.0/np.where(in0!=0.0,in0,1.0)
        in1inv = 1.0/np.where(in1!=0.0,in1,1.0)
        conda = (np.abs(in0)>1.0)
        condb = np.logical_and(np.logical_not(conda),(np.abs(in1)>1.0))
        #nb, reuse intermediate results below:
        in0sq = np.square(in0)
        in1sq = np.square(in1)
        self._ux = np.where(conda,
                            in2 * np.sqrt(np.clip(1.0-(in1sq+np.square(in0inv)),0.0,1.0)),
                            in0)
        self._uy = np.where(condb,
                            in2 * np.sqrt(np.clip(1.0-(in0sq+np.square(in1inv)),0.0,1.0)),
                            in1)
        self._uz = np.where(conda,
                            in0inv,
                            np.where(condb,
                                     in1inv,
                                     in2 * np.sqrt(np.clip(1.0-(in0sq+in1sq),0.0,1.0))))

    def _unpack_legacy(self):
        in0 = self._data['uve1'].astype(float)
        in1 = self._data['uve2'].astype(float)
        abs_in0 = np.abs(in0)
        abs_in1 = np.abs(in1)
        self._uz = (1.0 - abs_in0) - abs_in1
        zneg = ( self._uz < 0.0 )
        not_zneg = np.logical_not(zneg)
        self._ux = not_zneg * in0 + zneg * ( 1.0 - abs_in1 ) * np.where(in0 >= 0.0,1.0,-1.0)
        self._uy = not_zneg * in1 + zneg * ( 1.0 - abs_in0 ) * np.where(in1 >= 0.0,1.0,-1.0)
        #Like mcpl_unitvect_unpack_oct in C, which uses fma() to get identical
        #results on all platforms:
        n = 1.0 / np.sqrt(np_fma(self._uz,self._uz,
                                 np_fma(self._uy,self._uy,np.square(self._ux))))
        self._ux *= n
        self._uy *= n
        self._uz *= n
        self._uz = np.where(np.signbit(self._data['uve3']),0.0,self._uz)

_block_fields = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz',
                  'ekin', 'time', 'weight', 'pdgcode', 'userflags' )
class _EditedParticleBlock(MCPLParticleBlock):
    """Block of particles where some fields have new values (from a
    ParticleEdit). The other fields come from the packed particle data, which
    is still transferred exactly by MCPLOutFile.add_particles."""
    def __init__(self, base, edits):
        super().__init__(*base._ctor_args)
        self._set_data(base._data,base._offset)
        self._indices = base._indices
        n = len(base)
        self._edits = dict(getattr(base,'_edits',{}))
        self._edits.update( (k,np.broadcast_to(np.asarray(v),(n,))) for k,v in edits.items() )
    def __getitem__(self,ipos):
        if isinstance(ipos,(int,np.integer)):
            return super().__getitem__(ipos)
        base = super().__getitem__(ipos)
        return _EditedParticleBlock(base,{ k : v[ipos] for k,v in self._edits.items() })
    @property
    def position(self):
        return np.stack((self.x,self.y,self.z),axis=1)
    @property
    def direction(self):
        return np.stack((self.ux,self.uy,self.uz),axis=1)
    @property
    def polarisation(self):
        return np.stack((self.polx,self.poly,self.polz),axis=1)

def _edited_field(name):
    def get(self):
        if name in self._edits:
            return self._edits[name]
        return getattr(MCPLParticleBlock,name).fget(self)
    return property(get,doc=getattr(MCPLParticleBlock,name).__doc__)
for _f in _block_fields:
    setattr(_EditedParticleBlock,_f,_edited_field(_f))
del _f

def _concat_blocks(blocks):
    """Merge blocks (without edits) of particles from the same file"""
    if len(blocks) == 1:
        return blocks[0]
    res = MCPLParticleBlock(*blocks[0]._ctor_args)
    res._set_data(np.concatenate([ b._data for b in blocks ]),9223372036854775807)
    res._indices = np.concatenate([ b.fileidx for b in blocks ])
    return res

class _ArrayBlock:
    """Block-like object with particle fields given as arrays (for selecting
    and editing particles added to MCPLOutFile as arrays)."""
    def __init__(self, cols, n, defaults):
        self._n = n
        for f in _block_fields:
            v = cols.get(f)
            if v is None:
                v = defaults.get(f,0)
            setattr(self,f,np.broadcast_to(np.asarray(v),(n,)))
    def __len__(self):
        return self._n
    @property
    def fileidx(self):
        raise MCPLError('fileidx can only be used for particles read from files')
    @property
    def wavelength(self):
        return wavelength_checked(self.ekin,self.pdgcode)

def record_dtype( singleprec, polarisation, universalweight, universalpdgcode,
                  userflags, userdata = None ):
    """The numpy dtype of the particle records of files with these options (in
    native byte order), with userdata the dtype of the userdata (or None)"""
    fp = 'f4' if singleprec else 'f8'
    fields = []
    if polarisation:
        fields += [('polx',fp),('poly',fp),('polz',fp)]
    fields += [('x',fp),('y',fp),('z',fp),
               ('uve1',fp),('uve2',fp),('uve3',fp),#packed unit vector and ekin
               ('t',fp)]
    if not universalweight:
        fields += [('w',fp)]
    if not universalpdgcode:
        fields += [('pdg','i4')]
    if userflags:
        fields += [('uf','u4')]
    if userdata is not None:
        fields += [('ud',userdata)]
    return np.dtype(fields)

def _surely_finite( b ):
    """Quick check that the raw data of a block read from a file has no NaN or
    infinite values (False means that it might have some, which must then be
    checked with _nonfinite_masks, which is much slower). This never triggers
    floating point exceptions (unlike e.g. summing the values)."""
    d = b._data
    return all( np.isfinite(d[n]).all() for n in d.dtype.names
                if d.dtype[n].kind == 'f' )

def _nonfinite_masks( b, check_polarisation = True, check_weight = True ):
    """Masks of the particles in block b with NaN or infinite values, for each
    field (named as in error messages, in the order checked by the C library),
    for the fields which have any."""
    res = {}
    def add( name, *arrays ):
        mask = np.zeros(len(b),dtype=bool)
        for a in arrays:
            mask |= ~np.isfinite(np.broadcast_to(a,(len(b),)))
        if mask.any():
            res[name] = mask
    add('position',b.x,b.y,b.z)
    if type(b) is MCPLParticleBlock and len(b):
        #Only unpack directions which might be non-finite (packed values
        #can be infinite for valid directions):
        mask = np.zeros(len(b),dtype=bool)
        cand = ~( np.isfinite(b._data['uve1']) & np.isfinite(b._data['uve2']) )
        if cand.any():
            mask[cand] = ~np.all(np.isfinite(b[cand].direction),axis=1)
        if mask.any():
            res['direction'] = mask
    else:
        add('direction',b.ux,b.uy,b.uz)
    if check_polarisation:
        add('polarisation',b.polx,b.poly,b.polz)
    add('kinetic energy',b.ekin)
    add('time',b.time)
    if check_weight:
        add('weight',b.weight)
    return res
