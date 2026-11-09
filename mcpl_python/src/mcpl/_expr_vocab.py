
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

"""The vocabulary of particle expressions (see _expressions): the fields,
vectors, constants, functions, and statements which can be used in them, and
which of them a parsed expression uses or changes."""

__all__ = []

import functools
import math

from ._common import MCPLError
from ._expr_ast import (
    Assign,
    Call,
    Float,
    Int,
    Name,
    Particle,
    Unary,
    _vector_parts,
    _walk,
)
from ._exprunits import (
    _base_dims,
    _base_units_mcpl,
    _dim_E,
    _dim_L,
    _dim_T,
    _expr_units,
    _unit_size,
)
from ._particles import _particle_names, _wavelength_pdgcodes
from ._physics import _pdg_label, _pdg_name

_expr_fields = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz',
                 'ekin', 'time', 'weight', 'pdgcode', 'userflags',
                 'wavelength', 'fileidx' )
#The vectors of the particles, and their values (e.g. x is pos.x):
_expr_vectors = { 'pos' : _vector_parts, 'dir' : ( 'ux', 'uy', 'uz' ),
                  'pol' : ( 'polx', 'poly', 'polz' ) }
#(their names in MCPL, as in mcpl_particle_t and MCPLParticleBlock):
_expr_vector_names = { 'pos' : 'position', 'dir' : 'direction', 'pol' : 'polarisation' }
#(the names of particles, like neutron, are constants too, see _particles):
_expr_constants = { 'pi' : math.pi }
_expr_field_dims = { 'x' : _dim_L, 'y' : _dim_L, 'z' : _dim_L,
                     'ekin' : _dim_E, 'time' : _dim_T,
                     'wavelength' : _dim_L }
_expr_wl_unit = _expr_units['Aa'][0]#(wavelength_from_ekin and ekin_from_wavelength use Aa)
#Fields which are only defined for some particles: the field and the values
#for which they are defined:
_expr_field_domains = { 'wavelength' : ( 'pdgcode', _wavelength_pdgcodes ) }
#Labels and short names of the values of fields (for labels in plots and
#tables, with symbols for plots if unicode is set, see _pdg_symbols):
_expr_value_names = { 'pdgcode' : ( _pdg_label, _pdg_name ) }
#Example units to suggest in error messages:
_expr_unit_hints = dict(zip(_base_dims,_base_units_mcpl))
#Functions requiring dimensionless arguments:
_functions_nodim = ( 'exp', 'log', 'log10', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan' )
#Functions giving integers, of values without units:
_functions_toint = ( 'round', 'floor', 'ceil' )
#Functions computed with integers when all their arguments are integers:
_functions_int = ( 'mod', 'abs', *_functions_toint, 'min', 'max', 'clamp' )
#Functions of vectors (abs also gives the lengths of vectors):
_functions_vector = ( 'dot', 'cross', 'angle' )
#(functions using the position and direction of the particles):
_functions_flight = { 'through_sphere' : ( 'pos', 'dir' ), 'through_box' : ( 'pos', 'dir' ) }
#The arguments of the functions (as in the help):
_function_args = { **{ f : ( 'a', ) for f in ( *_functions_nodim, *_functions_toint, 'sqrt', 'abs' ) },
                   'atan2' : ( 'y', 'x' ), 'mod' : ( 'a', 'b' ), 'clamp' : ( 'v', 'low', 'high' ),
                   **{ f : ( 'a', 'b', '...' ) for f in ( 'hypot', 'min', 'max' ) },
                   **{ f : ( 'v', 'w' ) for f in _functions_vector },
                   'through_sphere' : ( 'c', 'r' ), 'through_box' : ( 'c', 'h' ) }
_expr_functions = frozenset(_function_args)
#Integers work like in C, with its integer promotions and usual arithmetic
#conversions (but results which do not fit their types are errors), with the
#types 'i32', 'u32', 'i64', and 'u64' (and 'f64' for floating point numbers):
_int_bits = { 'i32' : 32, 'u32' : 32, 'i64' : 64, 'u64' : 64 }
#(the types of the integer fields):
_int_field_types = { 'pdgcode' : 'i32', 'userflags' : 'u32', 'fileidx' : 'i64' }

def _int_range( t ):
    """The smallest and largest values of the integer type t"""
    bits = _int_bits[t]
    return ( 0, 2**bits - 1 ) if t[0] == 'u' else ( -2**(bits-1), 2**(bits-1) - 1 )

def _promoted_type( bits, unsigned ):
    """The type of integers of the size (in bits) after the integer promotions"""
    return 'i32' if bits < 32 else f'{"u" if unsigned else "i"}{bits}'

def _value_type( ftype ):
    """The type of the values of a userdata field of the type ftype (like
    'uint16' or 'float32')"""
    if ftype.startswith('float'):
        return 'f64'
    return _promoted_type(int(ftype.removeprefix('u').removeprefix('int')),ftype[0] == 'u')

def _common_int_type( *types ):
    """The type of results of integers of the types (the usual arithmetic
    conversions)"""
    res = types[0]
    for t in types[1:]:
        if t == res:
            continue
        if ( t[0] == 'u' ) == ( res[0] == 'u' ):
            res = res if _int_bits[res] >= _int_bits[t] else t
        else:
            u, s = ( res, t ) if res[0] == 'u' else ( t, res )
            res = u if _int_bits[u] >= _int_bits[s] else s
    return res

def _int_constant_type( v ):
    """The type of an integer constant (int32 if it fits, then int64, then
    uint64), or None if it is too large"""
    for t, lo, hi in ( ( 'i32', -2**31, 2**31 ), ( 'i64', -2**63, 2**63 ), ( 'u64', 0, 2**64 ) ):
        if lo <= v < hi:
            return t
    return None

def _userdata_unit( layout, field ):
    """The size (in the units of expressions) and dimension of the unit of the
    field of the userdata layout, as (1.0, None) for fields without a unit"""
    from ._userdata import userdata_units
    unit = userdata_units(layout).get(field)
    factor, dim = 1.0, [ 0, 0, 0, 0 ]
    for part in ( unit.split('.') if unit else () ):
        name, _, power = part.partition('^')
        d = _expr_units[name][1]
        e = int(power) if power else 1
        factor *= _unit_size(name,e)
        if d is not None:
            dim = [ a + b * e for a, b in zip(dim,d) ]
    return factor, ( tuple(dim) if any(dim) else None )

#(cached, as fields are looked up for each block of particles; errors are not
#cached):
@functools.lru_cache
def _userdata_field( layout, field, index ):
    """The type, the number of values (None for fields of one value), and the
    size and dimension of the unit (see _userdata_unit) of the field of the
    userdata layout (None for particles without userdata), used as
    userdata.FIELD, or userdata.FIELD.at(index). Raises MCPLError if there
    is no such field, or if the index does not fit it."""
    from ._userdata import userdata_fields
    if not layout:
        name = f'userdata.{field}' + ( '' if index is None else f'.at({index})' )
        raise MCPLError(f'The particles have no userdata (for {name})')
    fields = { f[0] : f[1:] for f in userdata_fields(layout) }
    if field not in fields:
        raise MCPLError(f'No userdata field "{field}" (the fields are: {", ".join(fields)})')
    ftype, n = fields[field]
    if n is None and index is not None:
        raise MCPLError(f'The userdata field "{field}" has one value per particle'
                        f' (use userdata.{field} without .at({index}))')
    if n is not None and index is None:
        raise MCPLError(f'The userdata field "{field}" has {n} values per particle'
                        f' (use userdata.{field}.at(0) to userdata.{field}.at({n-1}))')
    if index is not None and index >= n:
        raise MCPLError(f'The index {index} is too large for the userdata field "{field}",'
                        f' which has {n} values per particle (from .at(0) to .at({n-1}))')
    return ( ftype, n, *_userdata_unit(layout,field) )

#Functions used as statements in edits:
_edit_statements = ( 'swap', 'rotate_x', 'rotate_y', 'rotate_z', 'rotate_around',
                     'rotate_frame' )
#(the vectors which rotations rotate):
_rotated_vectors = tuple(_expr_vectors.values())
#Components of position, direction, and polarisation changed by rotations:
_rotation_planes = { f'rotate_{axis}' : tuple( ( v[a], v[b] ) for v in _rotated_vectors )
                     for axis, a, b in ( ( 'x', 1, 2 ), ( 'y', 2, 0 ), ( 'z', 0, 1 ) ) }
#The rotations given by a matrix, with the numbers of their arguments (an
#axis and an angle, or the vectors v, vout, u, and uout):
_rotation_matrix_args = { 'rotate_around' : 2, 'rotate_frame' : 4 }
#(and their arguments, for messages):
_rotation_matrix_usage = { 'rotate_around' : 'an axis and an angle, as in rotate_around((0,0,1),90deg)',
                           'rotate_frame' : 'the vectors v, vout, u, and uout, as in'
                                            ' rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))' }
#The fields (and vectors, like pos) which edits can assign:
_assignable = tuple( f for f in _expr_fields if f != 'fileidx' ) + tuple(_expr_vectors)

def _int_constant( node ):
    """The value of the node if it is an integer constant (an integer, a
    particle name, or a negated integer), else None"""
    if isinstance(node,Int):
        return node.value
    if isinstance(node,Particle):
        return _particle_names[node.name]
    if isinstance(node,Unary) and node.op == '-' and isinstance(node.operand,Int):
        return -node.operand.value
    return None

def _assigned_fields( target ):
    """The fields which an assignment to the target (a field, vector, or
    variable) sets: ekin for wavelength, and the values of vectors"""
    return _expr_vectors.get(target,( 'ekin' if target == 'wavelength' else target, ))

def _fields_used( node ):
    """The particle fields which a parsed expression (or statement, or edit
    expression) uses, including fileidx, and those of the vectors used (as x for
    pos)"""
    res = set()
    for n in _walk(node):
        names = []
        if isinstance(n,Name):
            names.append(n.id)
        elif isinstance(n,Assign) and n.op is not None:
            names.append(n.target)#(as in x += 1cm)
        elif isinstance(n,Call) and n.name in _functions_flight:
            names += _functions_flight[n.name]
        for name in names:
            if name in _expr_vectors:
                res.update(_expr_vectors[name])
            elif name in _expr_fields:
                res.add(name)
    return frozenset(res)

def _is_square( power ):
    """Whether the power (the tree of an exponent) is the constant 2, the only
    power of vectors (v^2 is their length squared)"""
    return isinstance(power,( Int, Float )) and power.value == 2

def _is_filter( st ):
    """Whether a parsed statement of an edit expression is a filter condition (not
    an assignment, swap(..), or a rotation)"""
    return not ( isinstance(st,Assign) or ( isinstance(st,Call) and st.name in _edit_statements ) )

def _modified_fields( statements ):
    """The fields which the parsed statements of an edit expression can change
    (ekin for assignments of the wavelength)"""
    res = set()
    for st in statements:
        if _is_filter(st):
            continue
        if isinstance(st,Assign):
            if st.target in _assignable:
                res.update(_assigned_fields(st.target))
        elif st.name == 'swap':
            res.update( a.id for a in st.args if a.id in _assignable )
        elif st.name in _rotation_planes:
            for plane in _rotation_planes[st.name]:
                res.update(plane)
        else:
            for vector in _rotated_vectors:
                res.update(vector)
    return frozenset(res)

def _depends_on( node ):
    """The fields (as with _fields_used, with ekin and pdgcode for
    wavelength) and variables which the values in a parsed node depend on"""
    res = set()
    for f in _fields_used(node):
        res.update( ( 'ekin', _expr_field_domains[f][0] ) if f == 'wavelength' else ( f, ) )
    res.update( n.id for n in _walk(node) if isinstance(n,Name) )
    return res

def _filters_on_fileidx( statements ):
    """Whether the particles which the parsed statements of an edit
    expression filter out can depend on their positions in the file
    (fileidx), also through fields and variables assigned from it"""
    dep = { 'fileidx' }#(the fields and variables depending on fileidx)
    if not any( 'fileidx' in _fields_used(st) for st in statements ):
        return False
    for st in statements:
        uses = bool( _depends_on(st) & dep )
        if _is_filter(st):
            if uses:
                return True
        elif isinstance(st,Assign):
            targets = _assigned_fields(st.target)
            if uses or ( st.op is not None and dep.intersection(targets) ):
                dep.update(targets)
            elif st.op is None:
                dep.difference_update(targets)#(the old values are replaced)
        elif st.name == 'swap':
            a, b = ( _assigned_fields(a.id)[0] for a in st.args )
            if ( a in dep ) != ( b in dep ):
                dep ^= { a, b }
        else:
            #(rotations: the components of each vector rotated depend on
            #each other, and on the arguments):
            planes = _rotation_planes.get(st.name,_rotated_vectors)
            for plane in planes:
                if uses or dep.intersection(plane):
                    dep.update(plane)
    return False
