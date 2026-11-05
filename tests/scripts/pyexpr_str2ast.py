
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

# Tests of the parser of expressions alone (_exprsyntax): the trees of valid
# expressions and statements (by precedence, units, vectors, userdata, in,
# numbers), that writing and parsing them again gives the same trees, the
# errors of invalid ones, and random expressions and random input. The output
# is the same with all Python versions.

import ast
import random

from mcpldev._common import MCPLError
from mcpldev._exprsyntax import _expr_parse, _expr_unparse, _Unit

#(units for the tests of the parser, which gets the names of the units):
units = ( 'cm', 'mm', 'm', 'MeV', 'meV', 'eV', 'ms', 'deg', 'K' )

_symbols = { ast.Add : '+', ast.Sub : '-', ast.Mult : '*', ast.Div : '/',
             ast.FloorDiv : '//', ast.Pow : '^', ast.BitOr : '|', ast.BitAnd : '&',
             ast.USub : 'neg', ast.UAdd : 'pos', ast.Not : 'not', ast.And : 'and',
             ast.Or : 'or', ast.Eq : '==', ast.NotEq : '!=', ast.Lt : '<',
             ast.LtE : '<=', ast.Gt : '>', ast.GtE : '>=', ast.In : 'in',
             ast.NotIn : 'not in' }

def show( node ):
    """Compact text of a tree (in prefix notation), for all the kinds of nodes
    which the parser gives (and an error for others)"""
    t = type(node)
    if t in ( ast.Expression, ast.Expr ):
        return show(node.value if t is ast.Expr else node.body)
    if t is ast.Module:
        return '{' + '; '.join( show(s) for s in node.body ) + '}'
    if t is ast.Assign:
        return f'(= {node.targets[0].id} {show(node.value)})'
    if t is ast.AugAssign:
        return f'({_symbols[type(node.op)]}= {node.target.id} {show(node.value)})'
    if t is ast.BinOp:
        return f'({_symbols[type(node.op)]} {show(node.left)} {show(node.right)})'
    if t is ast.UnaryOp:
        return f'({_symbols[type(node.op)]} {show(node.operand)})'
    if t is ast.BoolOp:
        return f'({_symbols[type(node.op)]} ' + ' '.join( show(v) for v in node.values ) + ')'
    if t is ast.Compare:
        parts = [ show(node.left) ]
        for op, c in zip(node.ops,node.comparators):
            parts += [ _symbols[type(op)], show(c) ]
        return '(cmp ' + ' '.join(parts) + ')'
    if t is ast.Call:
        return f'{node.func.id}(' + ', '.join( show(a) for a in node.args ) + ')'
    if t is ast.Tuple:
        return '[' + ', '.join( show(e) for e in node.elts ) + ']'
    if t is ast.Subscript:
        return f'(at {show(node.value)} {node.slice.value})'
    if t is ast.Name:
        return node.id
    if t is ast.Constant:
        return repr(node.value)
    if t is _Unit:
        return f'<{node.unit}>' if node.power == 1 else f'<{node.unit}^{node.power}>'
    raise AssertionError(f'Unexpected node {t.__name__}')

def parse( text, mode = 'eval' ):
    return _expr_parse(text,mode,units = units)

def check( text, mode = 'eval' ):
    """Parse, show the tree and the written text, and check that writing and
    parsing again gives the same tree (and the same text)"""
    tree = parse(text,mode)
    out = _expr_unparse(tree)
    again = parse(out,mode)
    assert show(again) == show(tree), ( text, out, show(tree), show(again) )
    assert _expr_unparse(again) == out, ( text, out, _expr_unparse(again) )
    print(f'  {text!r:34} -> {show(tree)}   written: {out!r}')

def error( text, mode = 'eval' ):
    try:
        tree = parse(text,mode)
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
            '1/cm^2', 'x > 0', 'x > 2cm - 1mm', 'ekin/MeV ^ 2', 'deg' ),
        'Vectors and their values' : (
            '(a,b)', '(a,b,c)', '(0,0,1m)', 'pos.x', 'pos.y.z', 'pos.at(2)',
            '(x,y,z).y', 'dir.x ^ 2', '-pos.x', 'f(a,b)', 'f()', 'abs((0,0,1m))',
            'dot(dir,(0,0,1))', 'f(g(a))' ),
        'Userdata fields' : ( 'userdata.temp', 'userdata.d.at(1)', 'userdata.temp > 300K',
                              '-userdata.n ^ 2' ),
        'In and not in' : ( 'pdgcode in (neutron,gamma)', 'x not in (1,2)', 'a in (b)',
                            'not a in (1,2)', 'a + 1 in (2,3) and b' ),
        'Numbers (decimal and hexadecimal, as in C)' : (
            '0', '7', '0.5', '.5', '5.', '1e-3', '1E3', '1.e3', '0x10', '0X1F', '0.0', '007.5', '1eV' ),
    }
    for title, texts in groups.items():
        print(f'{title}:')
        for text in texts:
            check(text)
    print('Statements of edits:')
    for text in ( 'x = 1cm', 'x += 2', 'x -= y', 'x *= 2', 'x /= 2', 'x //= 2',
                  'x ^= 2', 'x **= 2', 'x &= 3', 'x |= 4', 'tmp = x + y',
                  'swap(x,y)', 'rotate_z(90deg)', 'pos += (0,0,1m)', 'x > 0' ):
        check(text,'exec')

def test_errors():
    print('Errors:')
    for text in ( '', ' ', 'x +', '(x', 'x)', '((x)', 'x y', '1 2', 'x = 1',
                  'a in (1) < 2', 'a < b in (1)', 'a in 1', 'a in ()', '(1,2,3,4)', '()',
                  'pos.w', 'pos.at(x)', 'pos.at(-1)', 'pos.at(1.5)', 'pos.', 'userdata.',
                  'userdata.d.x', 'userdata.d.at()', '090', '007', '00', '1_000', '1_0.5',
                  '0x_10', '0o17', '0b101', '0x', '0xg', '1.2.3', '1e', '1e+', 'x && y', 'x || y',
                  '!x', 'x % 2', '~x', '"a"', "'a'", 'x[0]', 'lambda: 1',
                  'x if y else z', '[1]', '{1}', 'f(x=1)', 'cm^x', 'cm^(1/0)', 'cm^0.3',
                  'cm^', 'and', 'x and', 'not', '@', '$', 'x # comment', '\u03b1',
                  'a,b', '1j', 'x == = 1', 'x =< 1' ):
        error(text)
    print('Errors of statements:')
    for text in ( 'x =', '= 1', 'userdata.t = 1', 'userdata.t.at(0) += 1', 'x = y = 1',
                  'x += ', '1 = x', 'x, y = 1, 2' ):
        error(text,'exec')

def random_tree( rnd, depth ):
    """Random expression text from the grammar"""
    if depth == 0 or rnd.random() < 0.25:
        return rnd.choice(( 'x', 'y', 'ekin', '2', '0.5', '1e3', '7cm', 'MeV', 'cm^2',
                            'pos.x', 'userdata.t', 'userdata.a.at(1)', '(0,0,1m)' ))
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
        return f'{sub()} {rnd.choice(("in","not in"))} ({sub()},{sub()})'
    if kind == 7:
        return f'({sub()}){rnd.choice(("cm","MeV","m^-1"))}'
    return f'({sub()},{sub()}).{rnd.choice(("x","y","at(0)"))}'

def test_random():
    rnd = random.Random(12345)
    ok = errors = 0
    for _ in range(2000):
        text = random_tree(rnd,4)
        try:
            tree = parse(text)
        except MCPLError:
            errors += 1#(e.g. "in" in a chain of comparisons)
            continue
        out = _expr_unparse(tree)
        assert show(parse(out)) == show(tree), ( text, out )
        assert _expr_unparse(parse(out)) == out, ( text, out )
        ok += 1
    print(f'Random expressions: {ok} written and parsed again to the same trees, {errors} errors')
    tokens = ( 'x', 'cm', '2', '0.5', '(', ')', ',', '.', 'at', '+', '-', '*', '/', '//',
               '^', '**', '&', '|', '<', '==', 'and', 'or', 'not', 'in', '=', '+=', ';',
               'userdata', 'f', ' ', '!', '%', '"', '[', '090', 'e', '1e' )
    results = { 'trees' : 0, 'errors' : 0 }
    for _ in range(5000):
        text = ''.join( rnd.choice(tokens) for _ in range(rnd.randrange(1,9)) )
        for mode in ( 'eval', 'exec' ):
            try:
                parse(text,mode)
                results['trees'] += 1
            except MCPLError:
                results['errors'] += 1
    print(f'Random input: only trees or MCPLError (in total {results["trees"]} trees'
          f' and {results["errors"]} errors)')

if __name__ == '__main__':
    test_valid()
    test_errors()
    test_random()
