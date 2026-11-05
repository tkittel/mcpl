
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

# NEEDS: numpy

# Tests of the parser of expressions alone (_expr_str2ast): the trees of valid
# values, picks, and edits (by precedence, units, vectors, userdata, in,
# numbers, and particles), that writing and parsing them again gives the same
# trees, the errors of invalid ones, and random expressions and random input.
# The output is the same with all Python versions.

import random

from mcpldev._common import MCPLError
from mcpldev._expr_ast import (
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
    Pick,
    Quantity,
    Unary,
    Unit,
    Userdata,
    Value,
    Vector,
)
from mcpldev._expr_ast2str import _expr_ast2str
from mcpldev._expr_str2ast import _expr_str2ast

_unary = { '-' : 'neg', '+' : 'pos', 'not' : 'not' }

def show( node ):
    """Compact text of a tree (in prefix notation), for all the kinds of nodes
    which the parser gives (and an error for others)"""
    t = type(node)
    if t is Value:
        return show(node.expr)
    if t is Edit:
        return '{' + '; '.join( show(s) for s in node.statements ) + '}'
    if t is Pick:
        return '{' + '; '.join( show(s) for s in ( *node.statements, node.condition ) ) + '}'
    if t is Assign:
        return f'({node.op or ""}= {node.target} {show(node.value)})'
    if t is Binary:
        return f'({node.op} {show(node.left)} {show(node.right)})'
    if t is Unary:
        return f'({_unary[node.op]} {show(node.operand)})'
    if t is Logical:
        return f'({node.op} ' + ' '.join( show(v) for v in node.values ) + ')'
    if t is Compare:
        parts = [ show(node.first) ]
        for op, v in zip(node.ops,node.values):
            parts += [ op, show(v) ]
        return '(cmp ' + ' '.join(parts) + ')'
    if t is In:
        values = ', '.join( show(v) for v in node.values )
        return f'({"not in" if node.negated else "in"} {show(node.value)} [{values}])'
    if t is Call:
        return f'{node.name}(' + ', '.join( show(a) for a in node.args ) + ')'
    if t is Vector:
        return '[' + ', '.join( show(c) for c in node.components ) + ']'
    if t is Part:
        return f'(at {show(node.vector)} {node.index})'
    if t is Name:
        return node.id
    if t is Particle:
        return f'p:{node.name}'
    if t is Userdata:
        return node.text
    if t is Int:
        return f'hex:{node.value}' if node.hex else repr(node.value)
    if t is Float:
        return repr(node.value)
    if t is Quantity:
        return f'{show(node.number)}{show(Unit(node.unit,node.power))}'
    if t is Unit:
        return f'<{node.unit}>' if node.power == 1 else f'<{node.unit}^{node.power}>'
    raise AssertionError(f'Unexpected node {t.__name__}')

def check( text, kind = 'value' ):
    """Parse, show the tree and the written text, and check that writing and
    parsing again gives the same tree (and the same text)"""
    tree = _expr_str2ast(text,kind)
    out = _expr_ast2str(tree)
    again = _expr_str2ast(out,kind)
    assert again == tree, ( text, out, show(tree), show(again) )
    assert _expr_ast2str(again) == out, ( text, out, _expr_ast2str(again) )
    print(f'  {text!r:34} -> {show(tree)}   written: {out!r}')

def error( text, kind = 'value' ):
    try:
        tree = _expr_str2ast(text,kind)
    except MCPLError as e:
        print(f'  {text!r:24} -> {e}')
        return
    raise AssertionError(f'No error for {text!r}: {show(tree)}')

def test_valid():
    groups = {
        'Precedence and associativity' : (
            'a or b and c', 'a and b or c', 'not a and b', 'not a == b', 'not not a',
            'a | b & c', 'a & b | c', 'a & 1 == 0', 'a | b == c',
            'a + b * c', 'a * b + c', 'a - b - c', 'a - (b - c)', 'a / b / c',
            'a // b * c', 'a * b // c', '-a ^ 2', '(-a) ^ 2', 'a ^ b ^ c', '(a ^ b) ^ c',
            'a ^ -b', '2 ^ -x ^ 2', 'a ** b', '-(a + b)', '+a', '- - a', '-a * b',
            'a < b < c', 'a == b != c', 'a <= b >= c', '(a < b) == c', 'a < b and b < c' ),
        'Units' : (
            '25meV', '25 meV', '1e3cm', '0.5m', 'x/cm', 'MeV', '4cm^2', '2cm^-1 * x',
            'cm^(1/2)', 'cm^-0.5', 'cm^2.5', 'cm^+2', 'cm^--2', '2^(x)MeV', '(a + b)cm',
            '1/cm^2', 'x > 0', 'x > 2cm - 1mm', 'ekin/MeV ^ 2', 'deg', '2*MeV', '(2)MeV',
            '-2MeV', '2^3MeV', '0x10 mm', '0x10*mm', '1e-9cm' ),
        'Vectors and their values' : (
            '(a,b)', '(a,b,c)', '(0,0,1m)', 'pos.x', 'pos.y.z', 'pos.at(2)',
            '(x,y,z).y', 'dir.x ^ 2', '-pos.x', 'f(a,b)', 'f()', 'abs((0,0,1m))',
            'dot(dir,(0,0,1))', 'f(g(a))' ),
        'Userdata fields' : ( 'userdata.temp', 'userdata.d.at(1)', 'userdata.temp > 300K',
                              '-userdata.n ^ 2' ),
        'In and not in (of integers and particles)' : (
            'pdgcode in (neutron,gamma)', 'x not in (1,2)', 'a in (1)', 'not a in (1,2)',
            'a + 1 in (2,3) and b', 'p in (-11, +0x1f, -0x10, positron, 0)' ),
        'Numbers (decimal and hexadecimal, as in C)' : (
            '0', '7', '0.5', '.5', '5.', '1e-3', '1E3', '1.e3', '0x10', '0X1F', '0x0', '0.0',
            '007.5', '1eV' ),
        'Particles (but not functions or variables with their names)' : (
            'neutron', 'pdgcode == positron', 'neutron(1)', 'abs(antielectron)' ),
    }
    for title, texts in groups.items():
        print(f'{title}:')
        for text in texts:
            check(text)
    print('Statements of edits:')
    for text in ( 'x = 1cm', 'x += 2', 'x -= y', 'x *= 2', 'x /= 2', 'x //= 2',
                  'x ^= 2', 'x **= 2', 'x &= 3', 'x |= 4', 'tmp = x + y',
                  'swap(x,y)', 'rotate_z(90deg)', 'pos += (0,0,1m)', 'x > 0',
                  'z += 1cm; weight *= 0.5', ' x = 1 ;; y = 2 ; ' ):
        check(text,'edit')
    print('Picks (statements and a condition):')
    for text in ( 'x > 0', 'r = hypot(x,y); r > 2cm', 'pdgcode == neutron;', 'a = 1; b = a; b > 0',
                  'x > 0; y > 0' ):
        check(text,'pick')

def test_errors():
    print('Errors:')
    for text in ( '', ' ', 'x +', '(x', 'x)', '((x)', 'x y', '1 2', 'x = 1',
                  'a in (1) < 2', 'a < b in (1)', 'a in 1', 'a in ()', 'a in (b)', 'a in (1cm)',
                  'a in (1.5)', 'a in (-neutron)', 'a in (1,)', 'a in (--1)', 'a in ((1))', '(1,2,3,4)', '()',
                  'pos.w', 'pos.at(x)', 'pos.at(-1)', 'pos.at(1.5)', 'pos.', 'userdata.',
                  'userdata.d.x', 'userdata.d.at()', '090', '007', '00', '1_000', '1_0.5',
                  '0x_10', '0o17', '0b101', '0x', '0xg', '1.2.3', '1e', '1e+', 'x && y', 'x || y',
                  '!x', 'x % 2', '~x', '"a"', "'a'", 'x[0]', 'lambda: 1',
                  'x if y else z', '[1]', '{1}', 'f(x=1)', 'cm^x', 'cm^(1/0)', 'cm^0.3',
                  'cm^', 'and', 'x and', 'not', '@', '$', 'x # comment', '\u03b1',
                  'a,b', '1j', 'x == = 1', 'x =< 1', 'x; y', 'x > 0;', 0, None ):
        error(text)
    print('Errors of statements:')
    for text in ( 'x =', '= 1', 'userdata.t = 1', 'userdata.t.at(0) += 1', 'x = y = 1',
                  'x += ', '1 = x', 'x, y = 1, 2', '', ' ; ; ', 'x = 1; y +', 'x = (1;y = 2)', 'rotate_x(90deg;x=1cm)' ):
        error(text,'edit')
    print('Errors of picks:')
    for text in ( 'r = hypot(x,y); r = 1', 'r = hypot(x,y); r >', '', ';', 'r = 1, r > 0',
                  'x = 1' ):
        error(text,'pick')

def random_tree( rnd, depth ):
    """Random expression text from the grammar"""
    if depth == 0 or rnd.random() < 0.25:
        return rnd.choice(( 'x', 'y', 'ekin', '2', '0.5', '1e3', '7cm', 'MeV', 'cm^2', '0x1f',
                            'pos.x', 'userdata.t', 'userdata.a.at(1)', '(0,0,1m)', 'neutron' ))
    def sub():
        return random_tree(rnd,depth-1)
    kind = rnd.randrange(9)
    if kind == 0:
        return f'{sub()} {rnd.choice(("+","-","*","/","//","|","&","^"))} {sub()}'
    if kind == 1:
        return f'{rnd.choice(("-","+","not "))}{sub()}'
    if kind == 2:
        return f'{sub()} {rnd.choice(("and","or"))} {sub()}'
    if kind == 3:
        return f'{sub()} {rnd.choice(("<","<=","==","!=",">",">="))} {sub()}'
    if kind == 4:
        return f'({sub()})'
    if kind == 5:
        return f'f({sub()},{sub()})'
    if kind == 6:
        values = ','.join( rnd.choice(( '1', '-2', '0x1f', 'neutron', '+3' )) for _ in range(rnd.randrange(1,4)) )
        return f'{sub()} {rnd.choice(("in","not in"))} ({values})'
    if kind == 7:
        return f'({sub()}){rnd.choice(("cm","MeV","m^-1"))}'
    return f'({sub()},{sub()}).{rnd.choice(("x","y","at(0)"))}'

def test_random():
    rnd = random.Random(12345)
    ok = errors = 0
    for _ in range(2000):
        text = random_tree(rnd,4)
        try:
            tree = _expr_str2ast(text)
        except MCPLError:
            errors += 1#(e.g. "in" in a chain of comparisons)
            continue
        out = _expr_ast2str(tree)
        assert _expr_str2ast(out) == tree, ( text, out )
        assert _expr_ast2str(_expr_str2ast(out)) == out, ( text, out )
        ok += 1
    print(f'Random expressions: {ok} written and parsed again to the same trees, {errors} errors')
    tokens = ( 'x', 'cm', '2', '0.5', '(', ')', ',', '.', 'at', '+', '-', '*', '/', '//',
               '^', '**', '&', '|', '<', '==', 'and', 'or', 'not', 'in', '=', '+=', ';',
               'userdata', 'f', ' ', '!', '%', '"', '[', '090', 'e', '1e', '0x1', 'neutron' )
    results = { 'trees' : 0, 'errors' : 0 }
    for _ in range(5000):
        text = ''.join( rnd.choice(tokens) for _ in range(rnd.randrange(1,9)) )
        for kind in ( 'value', 'pick', 'edit' ):
            try:
                tree = _expr_str2ast(text,kind)
            except MCPLError:
                results['errors'] += 1
                continue
            assert _expr_str2ast(_expr_ast2str(tree),kind) == tree, ( text, kind )
            results['trees'] += 1
    print(f'Random input: only trees or MCPLError, and the trees are written and parsed again'
          f' to the same trees (in total {results["trees"]} trees and {results["errors"]} errors)')

if __name__ == '__main__':
    test_valid()
    test_errors()
    test_random()
