
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

"""Per-particle userdata (MCPL format version 4): parsing of layouts like
"temp:float32:K,origin:int32,tags:uint8[3]" (with the same rules and error
messages as the C library), the corresponding numpy dtypes, and the units of
the fields."""

__all__ = []

from ._common import MCPLError
from ._numpy import np

_maxsize = 65535
_maxnamelength = 64
#The names of the fields of particles in MCPL files, and of their derived
#properties in the APIs, which userdata fields can not have (so they can never
#be confused with them):
_reserved_names = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz',
                    'ekin', 'time', 'weight', 'pdgcode', 'userflags',
                    'position', 'direction', 'polarisation', 'wavelength' )
_types = { 'int8' : 'i1', 'uint8' : 'u1', 'int16' : 'i2', 'uint16' : 'u2',
           'int32' : 'i4', 'uint32' : 'u4', 'int64' : 'i8', 'uint64' : 'u8',
           'float32' : 'f4', 'float64' : 'f8' }
_cache = {}
#The units of fields (in this order, each at most once, separated by dots,
#with powers like cm^2 or MeV^-1):
_units = ( 'cm', 'MeV', 'ms', 'K', 'deg' )
_unit_list = 'the units are cm, MeV, ms, K and deg, like cm^2.MeV'
_power_error = ( 'invalid power (powers are single digits from 2 to 9 or -1 to'
                 ' -9, like cm^2 or MeV^-1)' )

def _unit_error( unit ):
    """Reason for a unit of a field being invalid (or None if it is valid)"""
    #(common ways of writing units, which are not used here):
    if '(' in unit or ')' in unit:
        return ( 'parentheses are not allowed in units (give each unit its own'
                 ' power, like cm^-2.MeV^-1 for 1/(cm^2*MeV))' )
    if '/' in unit:
        return ( 'division is not allowed in units (use negative powers, like'
                 ' MeV.cm^-1 for MeV/cm)' )
    if '*' in unit:
        return 'units are separated by dots, like cm.MeV for cm*MeV'
    last = -1
    for factor in unit.split('.'):
        name, caret, power = factor.partition('^')
        if not name:
            return f'empty unit ({_unit_list})'
        if name not in _units:
            return f'unknown unit ({_unit_list})'
        i = _units.index(name)
        if i == last:
            return 'each unit can appear only once'
        if i < last:
            return f'the units must be in the order {", ".join(_units)}'
        last = i
        if caret:
            digit = power.removeprefix('-')
            if ( len(digit) != 1 or not '1' <= digit <= '9'
                 or ( digit == '1' and not power.startswith('-') ) ):
                return _power_error
    return None

def _parse_error( layout ):
    """Reason for a layout being invalid (or None if it is valid)"""
    if not layout:
        return 'empty layout'
    names = set()
    size = 0
    for fld in layout.split(','):
        if not fld:
            return 'empty field'
        name, colon, typespec = fld.partition(':')
        if not colon:
            return 'fields must be given as name:type'
        if not name:
            return 'empty field name'
        if len(name) > _maxnamelength:
            return 'too long field name'
        if not ( 'a' <= name[0] <= 'z' ):
            return 'field names must start with a lowercase letter'
        if not all( c == '_' or 'a' <= c <= 'z' or '0' <= c <= '9'
                    for c in name[1:] ):
            return ( 'field names must only contain lowercase letters,'
                     ' digits and underscores' )
        if name in _reserved_names:
            return ( 'reserved field name (the names of particle fields, like x,'
                     ' ekin, position or wavelength, can not be used)' )
        typespec, colon2, unit = typespec.partition(':')
        tname, bracket, arr = typespec.partition('[')
        if tname not in _types:
            return ( 'unknown type (must be one of int8, uint8, int16, uint16,'
                     ' int32, uint32, int64, uint64, float32, float64)' )
        count = 1
        if bracket:
            digits = arr[:-1]
            if ( not arr.endswith(']') or not digits or digits[0] == '0'
                 or not all( '0' <= c <= '9' for c in digits ) ):
                return 'invalid array size (must be like [3])'
            count = int(digits)
            if count > _maxsize:
                return 'too large userdata (at most 65535 bytes are allowed)'
        if colon2:
            err = _unit_error(unit)
            if err:
                return err
        if name in names:
            return 'duplicate field name'
        names.add(name)
        size += count * int(_types[tname][1])
        if size > _maxsize:
            return 'too large userdata (at most 65535 bytes are allowed)'
    return None

def userdata_fields( layout ):
    """The fields of a (valid) userdata layout, as (name, type, number of
    values, or None for fields of one value)"""
    res = []
    for fld in layout.split(','):
        name, _, typespec = fld.partition(':')
        tname, bracket, arr = typespec.partition(':')[0].partition('[')
        res.append( ( name, tname, int(arr[:-1]) if bracket else None ) )
    return res

def userdata_dtype( layout ):
    """Numpy dtype (in native byte order) for the userdata of one particle,
    with a field for each field of the layout. An MCPLError is raised for
    invalid layouts."""
    dt = _cache.get(layout)
    if dt is None:
        err = _parse_error( layout ) if isinstance(layout,str) else 'not a string'
        if err:
            s = layout if isinstance(layout,str) else repr(layout)
            raise MCPLError(f'Invalid userdata layout "{s[:200]}'
                            f'{"..." if len(s) > 200 else ""}": {err}')
        dt = _cache[layout] = np.dtype([ ( name, _types[t] ) if n is None else
                                         ( name, _types[t], ( n, ) )
                                         for name, t, n in userdata_fields(layout) ])
    return dt

def userdata_units( layout ):
    """The units of the fields of the layout, as {name : unit}, with None for
    fields without a unit (e.g. {'temp': 'K', 'n': None})"""
    userdata_dtype(layout)#(checks the layout)
    res = {}
    for fld in layout.split(','):
        name, _, typespec = fld.partition(':')
        res[name] = typespec.partition(':')[2] or None
    return res

def userdata_array( value, layout, what = 'userdata' ):
    """Convert userdata given as a dict of field values (e.g. {'temp':temps})
    or a numpy structured array (or record) with fields of the layout into a
    structured array of the dtype of the layout, with missing fields being
    zero. Values can be given for all particles (arrays with the particles
    as first dimension), or for a single one (which then applies to all
    particles). Returns the array and the number of particles (1 if all
    values are for a single particle)."""
    dt = userdata_dtype(layout)
    if isinstance(value,(np.ndarray,np.void)) and value.dtype.names:
        fields = { k : value[k] for k in value.dtype.names }
    elif hasattr(value,'items'):
        fields = dict(value.items())
    else:
        raise MCPLError(f'{what} must be a dict of field values or a numpy'
                        ' structured array')
    unknown = set(fields) - set(dt.names)
    if unknown:
        raise MCPLError(f'Unknown {what} field(s): ' + ', '.join(sorted(unknown))
                        + f' (the userdata layout is "{layout}")')
    conv, lengths = {}, set()
    for name, v in fields.items():
        sub, base = dt[name].shape, dt[name].base
        v = np.asarray(v)
        if v.dtype.kind not in 'biuf':
            raise MCPLError(f'{what} field {name} must be numbers')
        if v.shape == sub:
            v = v.reshape((1,)+sub)
        elif v.ndim != 1+len(sub) or v.shape[1:] != sub:
            shape = '(N,)' if not sub else f'(N,{sub[0]})'
            single = 'a single number' if not sub else f'shape {sub}'
            raise MCPLError(f'{what} field {name} must have {single}'
                            f' or shape {shape}')
        if base.kind in 'iu':
            if v.dtype.kind == 'f' and ( not np.all(np.isfinite(v))
                                         or not np.array_equal(np.floor(v),v) ):
                raise MCPLError(f'{what} field {name} must be integers')
            info = np.iinfo(base)
            if v.size and ( int(v.min()) < info.min or int(v.max()) > info.max ):
                raise MCPLError(f'{what} field {name} out of range for'
                                f' {dt[name].base.name}')
        conv[name] = v
        lengths.add(len(v))
    lengths.discard(1)
    if len(lengths) > 1:
        raise MCPLError(f'Inconsistent lengths of {what} field arrays')
    n = lengths.pop() if lengths else 1
    arr = np.zeros(n,dtype=dt)
    for name, v in conv.items():
        arr[name] = v
    return arr, n
