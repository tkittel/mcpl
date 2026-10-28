
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


"""The conversion of particle fields to the records of MCPL files (with their
checks), when writing."""

__all__ = []

import math

from ._blocks import _nonfinite_masks, record_dtype
from ._common import MCPLError
from ._numpy import np
from ._particles import _wavelength_pdgcodes
from ._physics import ekin_from_wavelength

#The particle fields which can be given when writing particles:
_fields_vector = ( ('position', ('x','y','z')),
                   ('direction', ('ux','uy','uz')),
                   ('polarisation', ('polx','poly','polz')) )
_fields_scalar = ('ekin','wavelength','time','weight','pdgcode','userflags')
_fields_all = frozenset( [ v for v,_ in _fields_vector ]
                         + [ c for _,cs in _fields_vector for c in cs ]
                         + list(_fields_scalar) )


class _RecordFormat:
    """The particle records of a file being written: its options (the universal
    pdgcode and weight, 0 if not used, and the dtype of the userdata, or None),
    the dtype of the records, and the packing and checks of particles"""
    def __init__( self, singleprec, polarisation, universalweight, universalpdgcode,
                  userflags, userdata ):
        self.singleprec, self.polarisation = singleprec, polarisation
        self.universalweight, self.universalpdgcode = universalweight, universalpdgcode
        self.userflags, self.userdata = userflags, userdata
        self.dtype = record_dtype(singleprec,polarisation,universalweight,
                                  universalpdgcode,userflags,userdata)

    def pack(self, n, cols, validate = True, packed_ekindir = None):
        """Serialise particle data (dictionary of scalars or arrays of length n)
        into structured array, exactly like the C library. The particles are
        checked first if validate is True, and packed_ekindir gives the packed
        kinetic energies and directions (uve1, uve2, uve3) to use as they are,
        e.g. those of another file."""
        def col(name,default=0.0):
            v = cols.get(name)
            if v is None:
                return np.full(n,default)
            return np.broadcast_to(np.asarray(v,dtype=float),(n,))
        ux, uy, uz = col('ux'), col('uy'), col('uz')
        ekin = col('ekin')
        if validate:
            self.validate(n,col)
        arr = np.empty(n,dtype=self.dtype)
        if packed_ekindir is not None:
            arr['uve1'], arr['uve2'], arr['uve3'] = packed_ekindir
        else:
            #Adaptive Projection Packing (see mcpl_unitvect_pack_adaptproj):
            absx, absy = np.abs(ux), np.abs(uy)
            project = np.abs(uz) < np.fmax(absx,absy)
            with np.errstate(divide='ignore'):
                invz = np.where(uz != 0.0, 1.0 / np.where(uz != 0.0, uz, 1.0), np.inf)
            proj_x = project & (absx >= absy)
            proj_y = project & ~(absx >= absy)
            arr['uve1'] = np.where(proj_x, invz, ux)
            arr['uve2'] = np.where(proj_y, invz, uy)
            arr['uve3'] = np.copysign( ekin,
                                       np.where(proj_x, ux,
                                                np.where(proj_y, uy, uz)) )
        if self.polarisation:
            arr['polx'], arr['poly'], arr['polz'] = col('polx'), col('poly'), col('polz')
        arr['x'], arr['y'], arr['z'] = col('x'), col('y'), col('z')
        arr['t'] = col('time')
        if not self.universalweight:
            arr['w'] = col('weight')
        if not self.universalpdgcode:
            v = cols.get('pdgcode')
            arr['pdg'] = 0 if v is None else np.broadcast_to(v,(n,))
        if self.userflags:
            v = cols.get('userflags')
            arr['uf'] = 0 if v is None else np.broadcast_to(v,(n,))
        if self.userdata is not None:
            #(the callers give the userdata for files with userdata, so the
            #zeros are only a fallback):
            v = cols.get('userdata')
            arr['ud'] = ( np.zeros(n,dtype=self.userdata)
                          if v is None else v )
        return arr

    def validate(self, n, col):
        """Raise MCPLError for the first invalid particle (and its first failed
        check), like the C library does. The particle fields are given as
        col(name) arrays of length n."""
        cols = _Columns(n,col)
        checks = [ ( m, f'attempting to add particle with NaN or infinite {name}' )
                   for name, m in _nonfinite_masks(cols,self.polarisation,
                                                   not self.universalweight).items() ]
        ux, uy, uz, ekin = col('ux'), col('uy'), col('uz'), col('ekin')
        with np.errstate(invalid='ignore'):
            checks.append( ( np.abs( ux * ux + uy * uy + uz * uz - 1.0 ) > 1.0e-5,
                             'attempting to add particle with non-unit direction vector' ) )
            checks.append( ( ekin < 0.0,
                             'attempting to add particle with negative kinetic energy' ) )
        if self.singleprec:
            fields = [ ('position',('x','y','z')) ]
            if self.polarisation:
                fields.append( ('polarisation',('polx','poly','polz')) )
            fields += [ ('kinetic energy',('ekin',)), ('time',('time',)) ]
            if not self.universalweight:
                fields.append( ('weight',('weight',)) )
            for name, cs in fields:
                with np.errstate(over='ignore',invalid='ignore'):
                    m = np.logical_or.reduce([ np.isfinite(col(c))
                                               & ~np.isfinite(col(c).astype(np.float32))
                                               for c in cs ])
                checks.append( ( m, ( f'attempting to add particle with {name} too'
                                      ' large for single precision storage' ) ) )
        _raise_first_failure(checks)

    def validate_one(self, v, ekin, time, weight):
        """Like validate, for a single particle with values given as Python
        floats (v being the position, direction and polarisation), which is
        much faster than numpy for single values."""
        x, y, z, ux, uy, uz, polx, poly, polz = v
        groups = [ ('position',(x,y,z)), ('direction',(ux,uy,uz)) ]
        if self.polarisation:
            groups.append( ('polarisation',(polx,poly,polz)) )
        groups += [ ('kinetic energy',(ekin,)), ('time',(time,)) ]
        if not self.universalweight:
            groups.append( ('weight',(weight,)) )
        for name, vals in groups:
            if not all( math.isfinite(e) for e in vals ):
                raise MCPLError(f'attempting to add particle with NaN or infinite {name}')
        if abs( ux * ux + uy * uy + uz * uz - 1.0 ) > 1.0e-5:
            raise MCPLError('attempting to add particle with non-unit direction vector')
        if ekin < 0.0:
            raise MCPLError('attempting to add particle with negative kinetic energy')
        if self.singleprec:
            for name, vals in groups:
                if name != 'direction' and any( abs(e) >= _float32_overflow for e in vals ):
                    raise MCPLError(f'attempting to add particle with {name} too'
                                    ' large for single precision storage')

    def resolve_wavelength(self, cols, pdgcode):
        if 'wavelength' not in cols:
            return
        if 'ekin' in cols:
            raise MCPLError('Do not specify both ekin and wavelength')
        if pdgcode is None:
            pdgcode = self.universalpdgcode
        if not np.all( np.isin( pdgcode, _wavelength_pdgcodes ) ):
            raise MCPLError('wavelength can only be specified for neutrons'
                            ' (pdgcode 2112) and gammas (pdgcode 22)')
        cols['ekin'] = ekin_from_wavelength( cols.pop('wavelength'), pdgcode )

def collect_fields( fields ):
    """The particle fields given as keyword arguments (see
    MCPLOutFile.add_particles), as a dictionary of arrays of the components,
    with their common length"""
    unknown = set(fields) - _fields_all
    if unknown:
        raise TypeError('Unknown particle field(s): '
                        + ', '.join(sorted(unknown)))
    cols = {}
    for vecname, compnames in _fields_vector:
        if vecname in fields:
            if any( c in fields for c in compnames ):
                raise MCPLError(f'Do not specify both {vecname} and any'
                                ' of ' + ', '.join(compnames))
            v = np.asarray(fields[vecname],dtype=float)
            if v.shape[-1:] != (3,) or v.ndim > 2:
                raise MCPLError(f'{vecname} must have shape (3,) or (N,3)')
            for i,c in enumerate(compnames):
                cols[c] = v[...,i]
        else:
            for c in compnames:
                if c in fields:
                    cols[c] = np.asarray(fields[c],dtype=float)
    for c in ('ekin','wavelength','time','weight'):
        if c in fields:
            cols[c] = np.asarray(fields[c],dtype=float)
    for c,lo,hi in (('pdgcode',-2147483648,2147483647),
                    ('userflags',0,4294967295)):
        if c in fields:
            v = np.asarray(fields[c])
            if v.dtype.kind not in 'iub':
                vi = v.astype(np.int64)
                if not np.array_equal(vi,v):
                    raise MCPLError(f'{c} must be integers')
                v = vi
            if v.size and ( v.min() < lo or v.max() > hi ):
                raise MCPLError(f'{c} out of range')
            cols[c] = v.astype(np.int64)
    for c,v in cols.items():
        if v.ndim > 1:
            raise MCPLError(f'{c} must be a scalar or a 1D array')
    lengths = { len(v) for v in cols.values() if v.ndim == 1 }
    lengths.discard(1)
    if len(lengths) > 1:
        raise MCPLError('Inconsistent lengths of particle field arrays')
    return cols, (lengths.pop() if lengths else 1)


class _Columns:
    """Block-like view of particle fields given by col(name)"""
    def __init__( self, n, col ):
        self._n, self._col = n, col
    def __len__( self ):
        return self._n
    def __getattr__( self, name ):
        return self._col(name)

#Doubles which become infinite when converted to single precision (they round
#up to 2^128, since the largest single precision number has an odd mantissa):
_float32_overflow = float.fromhex('0x1.ffffffp+127')

def _int_field( name, v, lo, hi ):
    """Integer value of a single particle field (like the checks of integer
    arrays in collect_fields)."""
    if not isinstance(v,(int,np.integer)):
        f = float(v)
        if not f.is_integer():
            raise MCPLError(f'{name} must be integers')
        v = f
    v = int(v)
    if not ( lo <= v <= hi ):
        raise MCPLError(f'{name} out of range')
    return v

def _raise_first_failure( checks ):
    """Raise MCPLError for the first particle failing any of the checks (masks
    and messages, which can also be functions of the particle index), with the
    message of the first check it fails."""
    checks = [ ( np.asarray(m,dtype=bool), msg ) for m, msg in checks ]
    failing = [ int(np.argmax(m)) for m, _ in checks if m.any() ]
    if not failing:
        return
    i = min(failing)
    msg = next( msg for m, msg in checks if m.ndim and m[i] or not m.ndim and m )
    raise MCPLError( msg(i) if callable(msg) else msg )
