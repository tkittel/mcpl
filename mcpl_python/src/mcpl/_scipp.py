
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

"""Conversion of particles to scipp data arrays (see MCPLFile.to_scipp and
MCPLParticleBlock.to_scipp). Only imported when used, and scipp is only
imported by the functions here."""

__all__ = []

from ._common import MCPLError
from ._messages import _warning
from ._numpy import np

_scipp_min_version = (26,9)
_default_limit = 100_000_000

def _import_scipp():
    try:
        import scipp
    except ImportError:
        raise MCPLError('Conversion to scipp requires the scipp package'
                        ' (e.g. pip install "mcpl-python[scipp]")') from None
    v = tuple( int(e) for e in scipp.__version__.split('.')[:2] )
    if v < _scipp_min_version:
        raise MCPLError(f'Conversion to scipp requires scipp version'
                        f' {".".join(str(e) for e in _scipp_min_version)}'
                        f' or later (found {scipp.__version__})')
    return scipp

def _int_coord_values( a, name ):
    """Values for a scipp coordinate of an integer field (scipp has no unsigned
    types, so unsigned values are converted to signed ones, which must be
    large enough)."""
    a = np.asarray(a)
    if a.dtype.kind == 'u':
        if a.dtype.itemsize >= 8:
            if len(a) and a.max() > np.iinfo(np.int64).max:
                raise MCPLError(f'Values of "{name}" are too large for scipp'
                                ' (which has no unsigned integers)')
            return a.astype(np.int64)
        return a.astype(np.int32 if a.dtype.itemsize < 4 else np.int64)
    if a.dtype.kind == 'i' and a.dtype.itemsize < 4:
        return a.astype(np.int32)
    return a

def _scipp_unit( sc, unit ):
    """The scipp unit of a unit of a userdata field (e.g. "cm^2.MeV"), or None"""
    return None if unit is None else sc.Unit(unit.replace('.','*').replace('^','**'))

def _unit_of_dim( sc, d ):
    """scipp unit of a quantity with dimension d (powers of length, energy and
    time, in which the values are in the units of MCPL: cm, MeV and ms)."""
    u = sc.Unit('dimensionless')
    if d is not None:
        for name, e in zip(('cm','MeV','ms'),d):
            if e:
                u = u * sc.Unit(name)**e
    return u

class _Columns:
    """The columns of a data array, collected block by block. Extra
    coordinates are given as a dictionary of names and functions returning
    the values for a block and their dimension (see
    _expressions._quantity_functions)."""

    def __init__( self, coord_functions, vectors, variances, dim,
                  warned = None ):
        self._exprs = dict(coord_functions or {})
        #Names of renamed userdata fields which were already warned about:
        self._warned = warned if warned is not None else set()
        self._vectors, self._variances, self._dim = vectors, variances, dim
        self._cols = {}
        self._dims = {}
        self._udunits = {}#(the units of the userdata fields, see userdata_units)

    def add_block( self, b ):
        cols = self._cols
        def add( name, values ):
            #(copied, since blocks can be views of buffers reused by later
            #reads):
            cols.setdefault(name,[]).append(np.array(values))
        add('weight',b.weight)
        if self._vectors:
            add('position',b.position)
            add('direction',b.direction)
        else:
            for n in ('x','y','z','ux','uy','uz'):
                add(n,getattr(b,n))
        add('ekin',b.ekin)
        add('time',b.time)
        add('pdgcode',b.pdgcode)
        if self._haspol(b):
            if self._vectors:
                add('polarisation',b.polarisation)
            else:
                for n in ('polx','poly','polz'):
                    add(n,getattr(b,n))
        if self._hasuf(b):
            add('userflags',b.userflags)
        ud = b.userdata
        if ud is not None and not self._udunits:
            from ._userdata import userdata_units
            self._udunits = userdata_units(b._udinfo[0])
        if ud is not None:
            for field in ud.dtype.names:
                v = ud[field]
                if v.ndim == 1:
                    add(f'userdata:{field}',v)
                else:
                    for i in range(v.shape[1]):
                        add(f'userdata:{field}:{i}',v[:,i])
        for name, fct in self._exprs.items():
            v, self._dims[name] = fct(b)
            add(f'expr:{name}',v)

    @staticmethod
    def _haspol( b ):
        #Whether the file has polarisation (otherwise all values are 0):
        return b._polx[0]

    @staticmethod
    def _hasuf( b ):
        #Whether the file has userflags (otherwise all values are 0):
        return b._uf[0]

    def data_array( self, sc ):
        dim = self._dim
        cols = { k : ( np.concatenate(v) if len(v) > 1 else v[0] )
                 for k, v in self._cols.items() }
        w = cols.pop('weight').astype(float)
        data = sc.array( dims = [dim], values = w, unit = 'dimensionless',
                         variances = ( w * w if self._variances else None ) )
        coords = {}
        def addcoord( name, var ):
            if name in coords:
                raise MCPLError(f'Coordinate name "{name}" is used more than'
                                ' once')
            coords[name] = var
        units = { 'x':'cm','y':'cm','z':'cm','ekin':'MeV','time':'ms',
                  'position':'cm' }
        for k, v in cols.items():
            if k.startswith('userdata:'):
                parts = k.split(':')
                name = parts[1] if len(parts) == 2 else f'{parts[1]}_{parts[2]}'
                if name in cols:
                    newname = f'userdata_{name}'
                    if name not in self._warned:
                        self._warned.add(name)
                        _warning(f'The userdata field "{name}" has the same'
                                 ' name as a standard coordinate, so it is'
                                 f' converted to the coordinate "{newname}"')
                    name = newname
                if v.dtype.kind in 'iub':
                    v = _int_coord_values(v,name)
                #(with the unit of the field in the layout, if any):
                unit = self._udunits.get(parts[1])
                addcoord( name, sc.array( dims = [dim], values = v,
                                          unit = _scipp_unit(sc,unit) ) )
            elif k.startswith('expr:'):
                name = k[5:]
                addcoord( name, sc.array( dims = [dim], values = v,
                                          unit = _unit_of_dim(sc,self._dims[name]) ) )
            elif k in ('position','direction','polarisation'):
                addcoord( k, sc.vectors( dims = [dim], values = v,
                                         unit = units.get(k,'dimensionless') ) )
            elif k in ('pdgcode','userflags'):
                addcoord( k, sc.array( dims = [dim],
                                       values = _int_coord_values(v,k),
                                       unit = None ) )
            else:
                addcoord( k, sc.array( dims = [dim], values = v,
                                       unit = units.get(k,'dimensionless') ) )
        return sc.DataArray( data, coords = coords )

def file_scipp_blocks( mcplfile, flt = None, coord_functions = None,
                       vectors = False, variances = True, dim = 'particle' ):
    """See MCPLFile.scipp_blocks (flt is a ParticleFilter or None, and
    coord_functions are as for _Columns)."""
    sc = _import_scipp()#(here, so a missing scipp is reported immediately)
    def blocks():
        warned = set()
        for b in mcplfile.particle_blocks:
            if flt is not None:
                b = b[flt(b)]
            if not len(b):
                continue
            c = _Columns(coord_functions,vectors,variances,dim,warned)
            c.add_block(b)
            yield c.data_array(sc)
    return blocks()

def file_to_scipp( mcplfile, skip = 0, limit = None, flt = None,
                   coord_functions = None, vectors = False, variances = True,
                   dim = 'particle' ):
    """See MCPLFile.to_scipp (flt is a ParticleFilter or None, and
    coord_functions are as for _Columns)."""
    sc = _import_scipp()
    skip = int(skip)
    if skip < 0:
        raise MCPLError('skip must not be negative')
    warn_if_limited = limit is None
    if limit is None:
        limit = _default_limit
    limit = int(limit)
    if limit < 0:
        raise MCPLError('limit must not be negative')
    c = _Columns(coord_functions,vectors,variances,dim)
    nleft = limit if limit else None
    dropped = False
    for b in mcplfile.particle_blocks:
        if flt is not None:
            b = b[flt(b)]
        if not len(b):
            continue
        if skip:
            if skip >= len(b):
                skip -= len(b)
                continue
            b = b[skip:]
            skip = 0
        if nleft is not None:
            if nleft == 0:
                dropped = True#there are more particles
                break
            if len(b) > nleft:
                b = b[:nleft]
                dropped = True
            nleft -= len(b)
        c.add_block(b)
        if dropped:
            break
    if dropped and warn_if_limited:
        _warning(f'Only the first {limit} particles were converted to scipp'
                 ' (use the limit parameter to change this)')
    if not c._cols:
        #No particles: an empty block gives the columns:
        c.add_block(mcplfile._currentblock[:0])
    return c.data_array(sc)
