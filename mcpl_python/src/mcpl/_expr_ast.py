
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

"""The trees of parsed particle expressions (see _expressions): immutable
nodes, which compare equal when they have the same contents, and the
operators with their precedences, for the parser (_expr_str2ast) and the
writer (_expr_ast2str)."""

__all__ = []

import collections
import dataclasses
import typing

_frozen = dataclasses.dataclass(frozen=True)

#Values:

@_frozen
class Int:
    """An integer constant (hex if written in hexadecimal, like 0x1f)"""
    value: int
    hex: bool = False

@_frozen
class Float:
    """A floating point constant"""
    value: float

@_frozen
class Quantity:
    """A number with a unit, like 25meV or 4cm^2"""
    number: typing.Any#(an Int or a Float)
    unit: str
    power: float = 1#(an int, or a float for half powers)

@_frozen
class Unit:
    """A unit with a power, standing for its value (MeV is 1MeV)"""
    unit: str
    power: float = 1#(an int, or a float for half powers)

@_frozen
class Name:
    """A name: a field (like x), a vector (like pos), a constant (pi), or a
    variable"""
    id: str

@_frozen
class Particle:
    """The name of a particle, like neutron, standing for its PDG code"""
    name: str

@_frozen
class Userdata:
    """A field of the userdata, userdata.NAME, or userdata.NAME.at(INDEX) for
    a value of an array (counting from 0)"""
    field: str
    index: typing.Any = None#(an int, or None)

    @property
    def text( self ):
        return f'userdata.{self.field}' + ( '' if self.index is None else f'.at({self.index})' )

@_frozen
class Vector:
    """A vector of two or three values, like (0,0,1m)"""
    components: tuple

    def __post_init__( self ):
        if len(self.components) not in ( 2, 3 ):
            raise ValueError('Vectors have two or three values')

    @property
    def dimension( self ):
        return len(self.components)

@_frozen
class Part:
    """A value of a vector, as in pos.x or pos.at(0) (index 0)"""
    vector: typing.Any
    index: int

#Operations:

@_frozen
class Unary:
    """-, +, or not"""
    op: str
    operand: typing.Any

@_frozen
class Binary:
    """An operator of _binary_ops, or ^"""
    op: str
    left: typing.Any
    right: typing.Any

@_frozen
class Logical:
    """and or or, of two or more values"""
    op: str
    values: tuple

@_frozen
class Compare:
    """Comparisons, which can be chained (as in 0 < x < 2cm): first, then the
    operators with the values they compare with"""
    first: typing.Any
    ops: tuple
    values: tuple

@_frozen
class In:
    """value in (values), or value not in (values) if negated, where the
    values are integers (Int) or particles (Particle)"""
    value: typing.Any
    negated: bool
    values: tuple

@_frozen
class Call:
    """A call of a function, or a statement like rotate_z(90deg) in edits"""
    name: str
    args: tuple

#Statements, and the expressions they are part of:

@_frozen
class Assign:
    """target = value, or target op= value (as in x += 1cm, op '+')"""
    target: str
    op: typing.Any#(a str, or None)
    value: typing.Any

@_frozen
class Value:
    """An expression of a value"""
    expr: typing.Any

@_frozen
class Pick:
    """The statements (assignments of variables) and the condition of a pick"""
    statements: tuple
    condition: typing.Any

@_frozen
class Edit:
    """The statements of an edit (assignments, and calls like swap(x,y))"""
    statements: tuple

def _children( node ):
    """The nodes directly in the node"""
    for f in dataclasses.fields(node):
        v = getattr(node,f.name)
        for c in ( v if isinstance(v,tuple) else ( v, ) ):
            if dataclasses.is_dataclass(c):
                yield c

def _walk( node ):
    """The node and all nodes in it (breadth first, so checks report the
    outermost problem first)"""
    todo = collections.deque([ node ])
    while todo:
        n = todo.popleft()
        todo.extend(_children(n))
        yield n

def _names( node ):
    """All names used in the node: of fields, vectors, constants, variables,
    particles, functions, and userdata fields (as userdata.NAME or
    userdata.NAME.at(INDEX))"""
    res = set()
    for n in _walk(node):
        if isinstance(n,Name):
            res.add(n.id)
        elif isinstance(n,(Particle,Call)):
            res.add(n.name)
        elif isinstance(n,Userdata):
            res.add(n.text)
    return frozenset(res)

#The operators and their precedences (higher binds tighter):
_prec_or, _prec_and, _prec_not, _prec_cmp = 1, 2, 3, 4
_prec_unary, _prec_implied, _prec_power, _prec_atom = 10, 10.5, 11, 12
#(and and or):
_logical_ops = { 'or' : _prec_or, 'and' : _prec_and }
#(left-associative):
_binary_ops = { '|' : 5, '&' : 6, '+' : 8, '-' : 8, '*' : 9, '/' : 9, '//' : 9 }
#(right-associative, written as ^, also as ** when parsed):
_power_ops = ( '^', '**' )
_compare_ops = ( '==', '!=', '<', '<=', '>', '>=' )
_unary_ops = ( '-', '+' )
#(the assignments, as op= with the operator, or None for =):
_assign_ops = { '=' : None, **{ f'{s}=' : s for s in _binary_ops },
                **{ f'{s}=' : '^' for s in _power_ops } }
#The names of the values of vectors (as in pos.x):
_vector_parts = ( 'x', 'y', 'z' )
