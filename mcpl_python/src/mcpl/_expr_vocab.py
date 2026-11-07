
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

from ._expr_ast import Assign, Call, Name, _walk
from ._exprunits import _dim_E, _dim_K, _dim_L, _dim_T
from ._particles import _wavelength_pdgcodes
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
_expr_functions = frozenset(( 'sqrt', 'atan2', 'mod', *_functions_vector, *_functions_flight,
                              *_functions_nodim, *_functions_toint, *_functions_samedim ))
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

def _is_condition( st ):
    """Whether a parsed statement of an edit expression is a condition (not
    an assignment, swap(..), or a rotation)"""
    return not ( isinstance(st,Assign) or ( isinstance(st,Call) and st.name in _edit_statements ) )

def _modified_fields( statements ):
    """The fields which the parsed statements of an edit expression can change
    (ekin for assignments of the wavelength)"""
    res = set()
    for st in statements:
        if _is_condition(st):
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
