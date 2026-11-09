
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

"""The writer of the texts of parsed particle expressions (see _expr_ast),
which the parser (_expr_str2ast) reads back as the same trees. Interface:
_expr_ast2str(node)."""

__all__ = []

from ._expr_ast import (
    Assign,
    Binary,
    Call,
    Compare,
    Edit,
    Float,
    In,
    Int,
    Logical,
    Name,
    Part,
    Particle,
    Quantity,
    Unary,
    Unit,
    Userdata,
    Value,
    Vector,
    _binary_ops,
    _logical_ops,
    _prec_atom,
    _prec_cmp,
    _prec_implied,
    _prec_not,
    _prec_power,
    _prec_unary,
    _vector_parts,
)


def _expr_ast2str( node ):
    """The text of a tree (of an expression, a statement, a value, or an
    edit), without spaces except around the words and, or, not, and in, and
    with parentheses only where they are needed. Statements are separated by
    ";". Multiplications by units are written as implied multiplications
    where possible (as in 25meV)."""
    if isinstance(node,Value):
        return _expr_ast2str(node.expr)
    if isinstance(node,Edit):
        return ';'.join( _expr_ast2str(n) for n in node.statements )
    if isinstance(node,Assign):
        return f'{node.target}{node.op or ""}={_expr_ast2str(node.value)}'
    return _write(node)[0]

def _sub( node, minprec ):
    t, prec = _write(node)
    return t if prec >= minprec else f'({t})'

def _number( node ):
    if isinstance(node,Int) and node.hex:
        #(negative only in the values of In):
        return f'{"-" if node.value < 0 else ""}0x{abs(node.value):x}'
    return repr(node.value)

def _unit( unit, power ):
    return unit + ( '' if power == 1 else f'^{power!r}' )

def _write( node ):
    """(text, precedence)"""
    if isinstance(node,(Int,Float)):
        return _number(node), _prec_atom
    if isinstance(node,Quantity):
        #(with a space after hexadecimal numbers, which would otherwise take in
        #the unit, as in 0x1f eV):
        space = ' ' if isinstance(node.number,Int) and node.number.hex else ''
        return _number(node.number) + space + _unit(node.unit,node.power), _prec_implied
    if isinstance(node,Unit):
        return _unit(node.unit,node.power), _prec_atom
    if isinstance(node,Name):
        return node.id, _prec_atom
    if isinstance(node,Particle):
        return node.name, _prec_atom
    if isinstance(node,Userdata):
        return node.text, _prec_atom
    if isinstance(node,Call):
        return f'{node.name}(' + ','.join( _sub(a,0) for a in node.args ) + ')', _prec_atom
    if isinstance(node,Vector):
        return '(' + ','.join( _sub(c,0) for c in node.components ) + ')', _prec_atom
    if isinstance(node,Part):
        i = node.index
        part = _vector_parts[i] if i < len(_vector_parts) else f'at({i})'
        return f'{_sub(node.vector,_prec_atom)}.{part}', _prec_atom
    if isinstance(node,Logical):
        prec = _logical_ops[node.op]
        #(with parentheses around and in and, and or in or, which are parsed
        #as one Logical without them):
        return f' {node.op} '.join( _sub(v,prec+1 if isinstance(v,Logical) else prec)
                                    for v in node.values ), prec
    if isinstance(node,Unary):
        if node.op == 'not':
            return 'not ' + _sub(node.operand,_prec_not), _prec_not
        return node.op + _sub(node.operand,_prec_unary), _prec_unary
    if isinstance(node,In):
        values = ','.join( _sub(v,0) for v in node.values )
        op = ' not in ' if node.negated else ' in '
        return _sub(node.value,_prec_cmp+1) + f'{op}({values})', _prec_cmp
    if isinstance(node,Compare):
        t = _sub(node.first,_prec_cmp+1)
        for op, v in zip(node.ops,node.values):
            t += op + _sub(v,_prec_cmp+1)
        return t, _prec_cmp
    if isinstance(node,Binary):
        if node.op == '^':
            #(right-associative, and with parentheses around units, as cm^2 is
            #parsed as a unit with a power):
            left = _sub(node.left,_prec_atom)
            left = f'({left})' if isinstance(node.left,Unit) else left
            return left + '^' + _exponent(node.right), _prec_power
        implied = _implied(node)
        if implied is not None:
            return implied, _prec_implied
        prec = _binary_ops[node.op]
        return _sub(node.left,prec) + node.op + _sub(node.right,prec+1), prec
    raise TypeError(f'Can not write {type(node).__name__}')

def _exponent( node ):
    #(unary operators are allowed in exponents, but not multiplications by
    #units, which bind less tightly than ^):
    if isinstance(node,Unary) and node.op != 'not':
        return node.op + _exponent(node.operand)
    return _sub(node,_prec_power)

def _implied( node ):
    """Text of a multiplication by a unit written as an implied
    multiplication (as in 2^(ekin/MeV)MeV), if it can be (after ")" or a
    number), else None"""
    if not ( node.op == '*' and isinstance(node.right,Unit) ):
        return None
    if isinstance(node.left,(Int,Float)):
        return None#(2*MeV, as 2MeV is a Quantity)
    if isinstance(node.left,(Unit,Quantity)) or ( isinstance(node.left,Binary)
                                                  and isinstance(node.left.right,Unit) ):
        return None#(e.g. 2cm^-1*cm, not (2cm^-1)cm)
    left = _sub(node.left,_prec_power)
    last = node.left
    while not left.endswith(')') and isinstance(last,(Binary,Unary)):
        #(the last token of the left side):
        last = last.right if isinstance(last,Binary) else last.operand
    if not ( left.endswith(')') or isinstance(last,(Int,Float)) ):
        return None
    #(with a space after hexadecimal numbers, as for quantities):
    space = ' ' if isinstance(last,Int) and last.hex and not left.endswith(')') else ''
    return left + space + _write(node.right)[0]
