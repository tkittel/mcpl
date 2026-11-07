
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

# Tests of the nodes of parsed expressions (_expr_ast): equality, hashing,
# immutability, vectors of two or three values, the walk through trees and the
# names used, and of what the vocabulary (_expr_vocab) finds in trees: the
# fields used, and those which edits change.

import dataclasses

from mcpldev._expr_ast import (
    Binary,
    Int,
    Name,
    Quantity,
    Userdata,
    Vector,
    _names,
    _walk,
)
from mcpldev._expr_str2ast import _expr_str2ast
from mcpldev._expr_vocab import _fields_used, _modified_fields


def test_nodes():
    a = Binary('+',Name('x'),Quantity(Int(1),'cm'))
    b = Binary('+',Name('x'),Quantity(Int(1),'cm'))
    print('Equal trees are equal, and have the same hash:', a == b and hash(a) == hash(b))
    assert a == b and hash(a) == hash(b) and len({ a, b }) == 1
    print('Different trees are not equal:', a != Binary('-',Name('x'),Quantity(Int(1),'cm')),
          Int(16) != Int(16,hex = True))
    try:
        a.op = '-'
    except dataclasses.FrozenInstanceError as e:
        print(f'Nodes can not be changed: {type(e).__name__}')
    for n in ( 1, 2, 3, 4 ):
        try:
            v = Vector(( Int(0), ) * n)
            print(f'Vector of {n} values: dimension {v.dimension}')
        except ValueError as e:
            print(f'Vector of {n} values: ValueError: {e}')
    print('Userdata:', Userdata('temp').text, Userdata('d',2).text)

def test_walk():
    tree = _expr_str2ast('(a + b) * c > sqrt(d)')
    print('Walk (breadth first):', ' '.join( type(n).__name__ + ( f':{n.id}' if isinstance(n,Name) else '' )
                                             for n in _walk(tree) ))
    for text, kind in ( ( 'hypot(x,y) < 2cm and pdgcode == neutron', 'edit' ),
                        ( 'r = userdata.temp/K; r > pi', 'edit' ),
                        ( 'userdata.d.at(1) + abs(pos)/cm', 'value' ),
                        ( 'tmp = x; swap(y,tmp); rotate_z(90deg)', 'edit' ) ):
        print(f'Names in {text!r}: {sorted(_names(_expr_str2ast(text,kind)))}')

def test_vocab():
    for text, kind in ( ( 'ekin/MeV', 'value' ), ( 'abs(pos)/cm', 'value' ),
                        ( 'through_sphere((0,0,1m),5cm)', 'edit' ),
                        ( 'through_box((0,0,1m),(5cm,5cm,1mm))', 'edit' ), ( 'mod(fileidx,2) == 0', 'edit' ),
                        ( 'wavelength/Aa', 'value' ), ( 'r = hypot(x,y); r > 2cm', 'edit' ),
                        ( 'x = 1cm', 'edit' ), ( 'x += 1cm; weight *= ux', 'edit' ),
                        ( 'swap(time,ekin)', 'edit' ), ( 'dir = (0,0,1)', 'edit' ), ( 'pi + 1', 'value' ) ):
        print(f'Fields used by {text!r}: {sorted(_fields_used(_expr_str2ast(text,kind)))}')
    for text in ( 'x = 1cm', 'x += 1cm; weight *= ux', 'pos += (0,0,1m)', 'wavelength = 1.8Aa',
                  'tmp = x; x = y; y = tmp', 'swap(x,tmp)', 'swap(time,ekin)', 'rotate_x(90deg)',
                  'rotate_z(90deg)', 'rotate_around((0,0,1),30deg)', 'pdgcode = neutron' ):
        print(f'Fields changed by {text!r}: {sorted(_modified_fields(_expr_str2ast(text,"edit").statements))}')

if __name__ == '__main__':
    test_nodes()
    test_walk()
    test_vocab()
