
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

# Tests of the checks of parsed expressions alone (_expr_astcheck): the trees
# of values, picks, and edits which pass, and the messages of those which do
# not (unknown names and functions, PDG codes as conditions, statements which
# picks or edits can not have, variables, swap, and rotations).

from mcpldev._common import MCPLError
from mcpldev._expr_ast import Call, Edit, Name, Value
from mcpldev._expr_astcheck import _expr_astcheck
from mcpldev._expr_str2ast import _expr_str2ast


def check( text, kind = 'value' ):
    """The message for the text, or 'ok'"""
    try:
        _expr_astcheck(_expr_str2ast(text,kind),text)
    except MCPLError as e:
        return str(e)
    return 'ok'

def show( texts, kind ):
    for text in texts:
        print(f'  {text!r}: {check(text,kind)}')

def test_values():
    print('Values:')
    show(( 'ekin/MeV', 'hypot(x,y)/cm', 'abs(pos)/m', 'pi*2', 'neutron', 'userdata.temp/K',
           'userdata.d.at(2)', 'through_sphere((0,0,1m),5cm)', 'mod(fileidx,10)',
           'foo', 'r + 1', 'userdata', 'sqrt', 'neutron + sqrt', 'foo(x)', 'rotate_x(90deg)',
           'swap(x,y)', 'sqrt(foo(bar))', '(a + b) * c', 'f(1) + g', '1e400', 'x < 1e400cm', '-1e999' ),'value')

def test_picks():
    print('Picks (PDG codes and pdgcode are not conditions):')
    show(( 'pdgcode == neutron', 'neutron', 'pdgcode', 'abs(pdgcode)', 'not antineutron',
           'neutron or gamma', 'x > 0cm and pdgcode', 'userflags & 0x10', 'not userflags',
           'abs(neutron) + 1', 'r = hypot(x,y); r > 2cm', 'r = 1; q = 2; r > 0', 's = 1; s > 0',
           'r = 1; r *= 2; x > 0', 'r += 1; r > 0', 'x = 1cm; x > 0', 'swap(x,y); x > 0',
           'rotate_z(90deg); x > 0', 'x > 1; y > 2', 'R = 1; R > 0', 'cm = 1; cm > 0',
           'pi = 3; pi > 0', 'neutron = 1; neutron > 0', 'sqrt = 1; sqrt > 0',
           'swap = 1; swap > 0', 'fileidx = 1; x > 0', 'r = foo; r > 0', 'r = 1; foo > r' ),'pick')

def test_edits():
    print('Edits:')
    show(( 'x = 1cm', 'x += 1cm; weight *= 0.5', 'pos += (0,0,1m)', 'tmp = x; x = y; y = tmp',
           'tmp = x', 'n *= 2', 'x > 0', 'sqrt(x)', 'fileidx = 1', 'x = foo', 'x = sqrt',
           'swap(x,y)', 'tmp = x; swap(tmp,y)', 'swap(x)', 'swap(x,1)', 'swap(x,y+1)',
           'swap(fileidx,x)', 'swap(userdata.t,x)', 'swap(wavelength,x)', 'swap(neutron,x)',
           'swap(foo,x)', 'rotate_x(90deg)', 'rotate_x(90)', 'rotate_x(-90)', 'rotate_x(1.5)',
           'rotate_x(0x10)', 'rotate_x(0)', 'rotate_x(a)', 'rotate_x(90deg,1)',
           'rotate_around((0,0,1),30deg)', 'rotate_around((0,0,1),30)', 'rotate_around((0,0,1))',
           'rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))', 'rotate_frame((0,0,1))',
           'a = 1; rotate_x(a*deg)', 'rotate_x(foo)' ),'edit')

def test_trees():
    #Trees built by hand (as the checks only need trees, not texts):
    print('Trees built by hand:')
    for tree in ( Value(Name('x')), Value(Name('foo')), Value(Call('cos',( Name('ux'), ))),
                  Edit(( Call('swap',( Name('x'), Name('y') )), )), Edit(( Name('x'), )) ):
        try:
            _expr_astcheck(tree,'TEXT')
            print(f'  {tree}: ok')
        except MCPLError as e:
            print(f'  {tree}: {e}')

if __name__ == '__main__':
    test_values()
    test_picks()
    test_edits()
    test_trees()
