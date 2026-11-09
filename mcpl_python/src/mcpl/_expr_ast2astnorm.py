
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

"""The normalisation of parsed particle expressions (see _expr_ast), so that
different ways of writing the same expression give the same tree, and thus
the same text (see _expr_ast2str). Interface: _expr_ast2astnorm(tree), for
checked trees (see _expr_astcheck). The normalised trees give exactly the
same values (and errors) as the trees they come from:

* Numbers with units are written in the unit in which their magnitude is at
  least 1 and as small as possible (5000eV as 5keV, 0.5mm as 500um, and
  40000mm^2 as 400cm^2), and zero in eV, m, s, or K (as 0eV). Whole
  numbers with units have no decimals (5.0keV as 5keV). Angles and half
  powers keep their units.
* Particle names are used where a value is compared with pdgcode (with ==,
  !=, in, or not in) or assigned to it, with the first name of each particle
  (2112 as neutron, antielectron as positron), and PDG codes elsewhere (x >
  neutron as x > 2112).
* The values after in and not in are sorted, without duplicates."""

__all__ = []

import dataclasses
import decimal
import math

from ._expr_ast import Assign, Compare, Float, In, Int, Name, Particle, Quantity, Unary
from ._exprunits import _base_units_si, _expr_units, _quantity_value, _unit_exponents
from ._particles import _particle_name, _particle_names


def _expr_ast2astnorm( node ):
    """The normalised tree (or node, or tuple of nodes)"""
    if isinstance(node,tuple):
        return tuple( _expr_ast2astnorm(n) for n in node )
    if not dataclasses.is_dataclass(node):
        return node
    if isinstance(node,Quantity):
        return _norm_quantity(node)
    if isinstance(node,Particle):
        return _code_node(_particle_names[node.name])
    if isinstance(node,In):
        return _norm_in(node)
    if isinstance(node,Compare) and _is_pdgcode_comparison(node):
        first, value = node.first, node.values[0]
        if first == Name('pdgcode'):
            return Compare(first,node.ops,( _pdg_node(value), ))
        return Compare(_pdg_node(first),node.ops,node.values)
    if ( isinstance(node,Assign) and node.target == 'pdgcode' and node.op is None
         and _code_of(node.value) is not None ):
        return Assign(node.target,None,_pdg_node(node.value))
    return dataclasses.replace(node,**{ f.name : _expr_ast2astnorm(getattr(node,f.name))
                                        for f in dataclasses.fields(node) })

#Particles:

def _code_of( node ):
    """The PDG code of a single number or particle name (as in pdgcode == -11
    or pdgcode == positron), else None"""
    if isinstance(node,Particle):
        return _particle_names[node.name]
    if isinstance(node,Int):
        return node.value
    if isinstance(node,Unary) and node.op in ( '-', '+' ) and isinstance(node.operand,Int):
        return -node.operand.value if node.op == '-' else node.operand.value
    return None

def _code_node( code ):
    """The number of a PDG code (as Unary for negative numbers, which the
    parser reads as such)"""
    return Int(code) if code >= 0 else Unary('-',Int(-code))

def _pdg_node( node ):
    """A single number or particle name compared with (or assigned to)
    pdgcode: the first name of the particle, or else the number"""
    name = _particle_name(_code_of(node))
    return Particle(name) if name in _particle_names else _expr_ast2astnorm(node)

def _is_pdgcode_comparison( node ):
    return ( len(node.ops) == 1 and node.ops[0] in ( '==', '!=' )
             and Name('pdgcode') in ( node.first, node.values[0] )
             and _code_of(node.values[0] if node.first == Name('pdgcode') else node.first)
             is not None )

def _norm_in( node ):
    """The values after in, sorted (with particle names for pdgcode), without
    duplicates"""
    pdg = node.value == Name('pdgcode')
    values = {}
    for v in sorted(node.values,key=lambda v : ( _code_of(v), not getattr(v,'hex',False) )):
        code = _code_of(v)
        if code in values:
            continue
        name = _particle_name(code)
        if pdg and name in _particle_names:
            values[code] = Particle(name)
        else:
            values[code] = v if isinstance(v,Int) else Int(code)
    return In(_expr_ast2astnorm(node.value),node.negated,tuple(values.values()))

#Numbers with units:

#The units of zero values:
_zero_units = _base_units_si
#Whole numbers from this size on are written as floating point numbers (like
#1e+20):
_max_whole = 10**15

def _number( d ):
    """The node of a number with a unit, given as a Decimal: an Int for whole
    numbers (which are not too large), else a Float"""
    if d == d.to_integral_value() and abs(d) < _max_whole:
        return Int(int(d))
    return Float(float(d))

def _decimal( number ):
    """The value of a number node as a Decimal, with the digits of its text
    (as written by _expr_ast2str)"""
    return decimal.Decimal(number.value if isinstance(number,Int) else repr(number.value))

def _norm_quantity( q ):
    """The number with the unit in the unit in which its magnitude is at least
    1 and as small as possible, as long as this gives exactly the same value
    (else only the number is normalised, or nothing)"""
    if not math.isfinite(q.number.value):
        return q
    candidates = [ Quantity(_number(_decimal(q.number)),q.unit,q.power) ]
    n = _unit_exponents.get(q.unit)
    if n is not None and q.power and float(q.power).is_integer():
        dim = _expr_units[q.unit][1]
        family = sorted(( ( m, u ) for u, m in _unit_exponents.items()
                          if _expr_units[u][1] == dim ),reverse = True)
        d = _decimal(q.number)
        with decimal.localcontext() as ctx:
            ctx.prec = len(d.as_tuple().digits) + 2#(scaleb is exact)
            if d == 0:
                si = next( ( u for _, u in family if u in _zero_units ), q.unit )
                candidates.insert(0,Quantity(Int(0),si,q.power))
            else:
                #(the smallest magnitude of at least 1, or else the largest):
                try:
                    values = [ ( d.scaleb(( n - m ) * int(q.power)), u ) for m, u in family ]
                except decimal.InvalidOperation:
                    return candidates[0]#(for huge powers of the unit)
                large = [ e for e in values if abs(e[0]) >= 1 ]
                v, u = ( min(large,key=lambda e : abs(e[0])) if large
                         else max(values,key=lambda e : abs(e[0])) )
                candidates.insert(0,Quantity(_number(v),u,q.power))
    value = _quantity_value(q.number.value,q.unit,q.power)
    for c in candidates:
        if _quantity_value(c.number.value,c.unit,c.power) == value:
            return c
    return q
