
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

"""The checks of parsed particle expressions (see _expr_ast) which do not need
particles: that the names, functions, statements, and variables exist and are
used as they can be. Interface: _expr_astcheck(tree, text). The units and
types of the values are checked when they are evaluated (see _expr_eval)."""

__all__ = []

import math

from ._common import MCPLError
from ._expr_ast import (
    Call,
    Float,
    Int,
    Logical,
    Name,
    Particle,
    Quantity,
    Unary,
    Userdata,
    Value,
    _names,
    _walk,
)
from ._expr_ast2str import _expr_ast2str
from ._expr_vocab import (
    _assignable,
    _edit_statements,
    _expr_constants,
    _expr_fields,
    _expr_functions,
    _expr_vectors,
    _is_condition,
    _rotation_matrix_args,
    _rotation_matrix_usage,
)
from ._exprunits import _expr_units
from ._particles import _particle_names


def _expr_astcheck( tree, text, unused_ok = False ):
    """Check the tree of a value or an edit expression (see _expr_str2ast),
    where text is the expression (for messages), and variables may be unused
    with unused_ok. Raises MCPLError for problems."""
    if isinstance(tree,Value):
        _check_names(tree.expr,text)
        return
    variables, used = set(), set()
    for st in tree.statements:
        _check_statement(st,text,variables,used)
    unused = sorted(variables - used)
    if unused and not unused_ok:
        raise MCPLError(f'Variable "{unused[0]}" is assigned but never used'
                        f' in "{text}" (fields which can be assigned are: '
                        + ', '.join(_assignable) + ')')

def _check_names( node, text, variables = () ):
    """Check that the names and functions in the expression exist (variables
    are those assigned before it), and that the constants are finite"""
    for n in _walk(node):
        if isinstance(n,Float) and not math.isfinite(n.value):
            #(like 1e400):
            raise MCPLError(f'A constant has NaN or infinite values in expression "{text}"')
        if isinstance(n,Call) and n.name not in _expr_functions:
            raise MCPLError(f'Unsupported function call in expression "{text}"'
                            ' (available functions are: '
                            + ', '.join(sorted(_expr_functions)) + ')')
        if isinstance(n,Name) and not ( n.id in _expr_fields or n.id in _expr_vectors
                                        or n.id in variables or n.id in _expr_constants ):
            if n.id == 'userdata':
                raise MCPLError(f'Fields of the userdata are written as userdata.NAME,'
                                f' in expression "{text}"')
            raise MCPLError(f'Unknown name "{n.id}" in expression "{text}"'
                            ' (particle fields are: ' + ', '.join(_expr_fields) + ')')

def _check_condition( node, text ):
    """Raise MCPLError where a PDG code is used as a condition (or as a part
    of one combined with and, or, and not), as
    in "neutron" or "pdgcode and x > 0cm", which would be true for all
    particles (other integers can be conditions, as in userflags & 0x10)"""
    if isinstance(node,Logical):
        for v in node.values:
            _check_condition(v,text)
        return
    if isinstance(node,Unary) and node.op == 'not':
        _check_condition(node.operand,text)
        return
    if isinstance(node,Call) and node.name == 'abs' and len(node.args) == 1:
        node = node.args[0]
    if isinstance(node,Particle):
        raise MCPLError(f'{node.name} is a PDG code ({_particle_names[node.name]}), not a'
                        f' condition (e.g. pdgcode == {node.name}), in expression "{text}"')
    if isinstance(node,Name) and node.id == 'pdgcode':
        raise MCPLError(f'pdgcode is not a condition (e.g. pdgcode == neutron), in'
                        f' expression "{text}"')

def _check_statement( st, text, variables, used ):
    """Check a statement, adding the variables it assigns and uses"""
    if _is_condition(st):
        _check_names(st,text,variables)
        used.update( _names(st) & variables )
        _check_condition(st,text)
        return
    if isinstance(st,Call):
        _check_call(st,text,variables,used)
        return
    name = st.target
    if name not in _assignable:
        _check_variable(name,text)
        if st.op is not None and name not in variables:
            raise MCPLError(f'Variable "{name}" used before it is assigned in "{text}"')
    _check_names(st.value,text,variables)
    used.update( _names(st.value) & variables )
    if st.op is not None and name in variables:
        used.add(name)#(as in d *= 2)
    if name not in _assignable:
        variables.add(name)

def _check_variable( name, text ):
    """Check that a variable can have the name"""
    if name in _expr_fields:
        raise MCPLError(f'{name} (the position of the particles in the'
                        f' file) can not be changed, in "{text}"')
    if not ( name.isidentifier() and name == name.lower() ) or (
            name in _expr_constants or name in _particle_names or name in _expr_units
            or name in _expr_functions or name in _edit_statements or name == 'inactive' ):
        raise MCPLError(f'Can not assign to "{name}" in "{text}" (fields which can'
                        ' be assigned are: ' + ', '.join(_assignable) + ', and other'
                        ' lowercase names which are not names of fields, units,'
                        ' constants, or functions can be used for variables)')

def _check_call( call, text, variables, used ):
    """Check a statement calling swap(..) or a rotation"""
    fname, args = call.name, call.args
    if fname == 'swap':
        #(the names of the fields or variables, also of userdata fields and
        #particles, for the messages):
        names = [ a.id if isinstance(a,Name) else a.text if isinstance(a,Userdata)
                  else a.name if isinstance(a,Particle) else None for a in args ]
        if len(names) != 2 or None in names:
            raise MCPLError('swap(..) takes two fields (or variables)'
                            f' as arguments, as in swap(x,y), in "{text}"')
        for n in names:
            if n == 'fileidx':
                raise MCPLError('fileidx (the position of the particles in'
                                f' the file) can not be changed, in "{text}"')
            if n.startswith('userdata.'):
                raise MCPLError(f'Fields of the userdata ({n}) can not be'
                                f' changed, in "{text}"')
            if n == 'wavelength':
                raise MCPLError('swap(..) can not be used with wavelength (which'
                                ' is computed from ekin; set it with'
                                f' "wavelength = ..." instead), in "{text}"')
            if n not in _assignable and n not in variables:
                raise MCPLError(f'Can not swap "{n}" in "{text}"'
                                ' (it is not a field or variable)')
        used.update( n for n in names if n in variables )
        return
    nargs = _rotation_matrix_args.get(fname,1)
    _nargs_words = { 1 : 'one argument', 2 : 'two arguments', 4 : 'four arguments' }
    if len(args) != nargs:
        what = { 'rotate_around' : 'an axis and an angle, as in rotate_around((0,0,1),90deg)',
                 'rotate_frame' : 'the vectors v, vout, u and uout, as in'
                 ' rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))' }.get(fname,'an angle')
        raise MCPLError(f'{fname}(..) takes {_nargs_words[nargs]}'
                        f' ({what}) in "{text}"')
    if fname != 'rotate_frame':
        _check_angle(fname,args[-1],text)
    for a in args:
        _check_names(a,text,variables)
        used.update( _names(a) & variables )

def _check_angle( fname, node, text ):
    """Plain numbers (other than 0) as angles of rotations are refused, as
    they are easily meant as degrees (rotate_x(90) instead of 90deg)"""
    signed = isinstance(node,Unary) and node.op in ( '-', '+' )
    v = node.operand if signed else node
    if isinstance(v,(Int,Float)) and v.value != 0:
        def with_unit( unit ):
            q = Quantity(v,unit)
            return _expr_ast2str(Unary(node.op,q) if signed else q)
        raise MCPLError(f'The angle of {fname}(..) must have a unit, as in {with_unit("deg")}'
                        f' or {with_unit("rad")} (not {_expr_ast2str(node)}), in "{text}"')
