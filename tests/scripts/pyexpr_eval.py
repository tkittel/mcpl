
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

# Tests of the evaluation of parsed expressions alone (_expr_eval), on a small
# block of particles made here: the values, units, and types (with the integer
# types of C) of all kinds of nodes, the errors found when evaluating, the
# right sides of and/or evaluated only where needed, blocks without particles
# (which check the units), and the statements of edits.

import numpy as np
from mcpldev._common import MCPLError
from mcpldev._expr_ast import Binary, Float, Int, Name, Quantity, Unit, Value
from mcpldev._expr_eval import _EmptyBlock, _ExprEvaluator, _run_statements
from mcpldev._expr_str2ast import _expr_str2ast


class Block:
    """Three particles: a neutron, a gamma, and an electron (with zero
    kinetic energy)"""
    def __init__( self ):
        self.x, self.y, self.z = np.array([1.0,-2.0,0.5]), np.array([0.0,3.0,-1.0]), np.array([2.0,2.0,2.0])
        self.ux, self.uy, self.uz = np.array([0.0,0.6,1.0]), np.array([0.0,0.8,0.0]), np.array([1.0,0.0,0.0])
        self.polx = self.poly = self.polz = np.zeros(3)
        self.ekin = np.array([2.5e-8,1.0,0.0])
        self.time, self.weight = np.array([1.0,2.0,3.0]), np.array([1.0,0.5,2.0])
        self.pdgcode = np.array([2112,22,11],dtype=np.int32)
        self.userflags = np.array([0,0x10,0xffffffff],dtype=np.uint32)
        self.fileidx = np.arange(3,dtype=np.int64)
    def __len__( self ):
        return 3

def value( text, block = None ):
    """The values, units, and type of the value of the text, or the error"""
    try:
        q = _ExprEvaluator(Block() if block is None else block,text)(_expr_str2ast(text))
    except MCPLError as e:
        return f'MCPLError: {e}'
    v = np.asarray(getattr(q,'v',None))
    if hasattr(q,'c'):
        return f'vector {[ np.asarray(c.v).tolist() for c in q.c ]} dim {q.d}'
    v = np.round(v,9) if v.dtype.kind == 'f' else v
    return f'{v.tolist()} dim {q.d} type {v.dtype}' + ( ' (a plain zero)' if q.zero else '' )

def test_values():
    print('Values:')
    for text in ( '1', '-2147483648', '2147483648', '-9223372036854775808', '18446744073709551615',
                  '18446744073709551616', '0', '0.0', '2.5', '0x10', '1e400', 'pi', 'neutron', 'positron',
                  '25meV', '4cm^2', 'cm^-1', '0.5m', '1e308km', 'MeV', 'x', 'pdgcode', 'userflags',
                  'fileidx', 'pos', 'dir.y', 'pos.at(2)', '(x,y)', '(1cm,0,2m)', 'wavelength',
                  'ekin/MeV', 'x + 1cm', 'x * ekin', 'sqrt(ekin)', 'x^2', '2^x', 'pdgcode + 1',
                  'pdgcode * 1000000', 'userflags + 1', 'userflags - 1', 'userflags // 16', '7 // 2',
                  'mod(userflags,16)', 'userflags & 0x10', 'userflags | 1', '-pdgcode', '-userflags',
                  'abs(-x)', 'abs(pdgcode)', 'round(x/cm)', 'floor(-2.5)', 'max(x,y)', 'min(1,2,3)',
                  'clamp(x,0,1cm)', 'hypot(x,y)', 'atan2(y,x)', 'cos(90deg)', 'exp(1)', 'abs(pos)',
                  'dot(pos,dir)', 'cross(pos,dir)', 'angle(dir,(0,0,1))', 'pos + (1cm,0,0)', 'pos*2',
                  'pos/2', 'pos^2', 'through_sphere((0,0,2cm),1.5cm)',
                  'through_box((0,0,2cm),(1cm,1cm,0.5cm))', 'through_box((1cm,0,0),(0,0,0))', 'x > 0', 'x > 0 and y >= 0',
                  'not x > 0', 'x < y < z', 'pdgcode in (neutron,gamma)', 'pdgcode not in (11)',
                  'x == 0', '-(x > 0)' ):
        print(f'  {text!r}: {value(text)}')

def test_errors():
    print('Errors when evaluating:')
    for text in ( 'x + 1', 'x + ekin', 'x > 1MeV', 'cos(x)', 'x^y', 'x^(1/3)', 'sqrt(sqrt(ekin))',
                  'mod(x,2)', 'mod(pdgcode,3)', 'mod(userflags,0)', 'x // 2', '7 // -2', 'userflags > -1',
                  'userflags & -1', 'x & 1', '-userflags', 'userflags + 1', 'pdgcode * 1000000000',
                  'x / 0', 'log(0)', 'pos + 1', 'pos * pos', 'cross((1,0),(0,1))', 'dot(pos,x)',
                  'abs(pos) + pos', 'pos > 0', 'x.x', 'pos.at(3)', 'through_sphere((0,0,1),1)',
                  'through_box((0,0,1),(1,1,1))', 'through_box((0,0,1cm),1cm)', 'through_box((0,0,0),(1cm,-1cm,1cm))',
                  'round(1e30)', 'wavelength', 'pdgcode == gamma and wavelength > 0', 'not pos', '(x,ekin)' ):
        print(f'  {text!r}: {value(text)}')

def test_active():
    #The right side of "and" is only evaluated where the left side is true
    #(here only for neutrons and gammas, which have wavelengths), and that of
    #"or" where the left side is false:
    print('Only where needed:')
    for text in ( 'pdgcode == neutron and wavelength > 1Aa', 'pdgcode == electron or wavelength > 1Aa',
                  'pdgcode != electron and ekin/ekin > 0', 'ekin > 0 and 1/ekin > 1/MeV' ):
        print(f'  {text!r}: {value(text)}')

def test_empty():
    print('Without particles (checking units and types):')
    for text in ( 'x/cm', 'x + 1', 'userdata.t + x', 'userdata.t + 1', 'pdgcode + 1', 'ekin/MeV > 1' ):
        print(f'  {text!r}: {value(text,_EmptyBlock())}')

def test_trees():
    #Trees built by hand:
    print('Trees built by hand:')
    for tree in ( Value(Quantity(Float(2.5),'keV')), Value(Binary('*',Int(2),Unit('cm',2))),
                  Value(Binary('/',Name('ekin'),Unit('eV'))) ):
        q = _ExprEvaluator(Block(),'TEXT')(tree)
        print(f'  {tree}: {np.asarray(q.v).tolist()} dim {q.d}')

def test_statements():
    print('Statements:')
    for text in ( 'x = 1cm', 'x += 1cm; weight *= 2', 'tmp = x; x = y; y = tmp', 'swap(x,z)',
                  'rotate_z(90deg)', 'rotate_x(180deg)', 'rotate_around((0,0,1),90deg)',
                  'pos = (0,0,1m)', 'pdgcode = neutron', 'userflags = 7', 'x = 1MeV', 'pos = (1,2,3)',
                  'pdgcode = 2.5', 'pdgcode = 4294967295', 'wavelength = 1.8Aa', 'rotate_x(1cm)',
                  'rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,0,1))' ):
        ev, modified = _ExprEvaluator(Block(),text), set()
        try:
            _run_statements(ev,_expr_str2ast(text,'edit').statements,text,modified)
        except MCPLError as e:
            print(f'  {text!r}: MCPLError: {e}')
            continue
        res = { n : np.round(np.asarray(ev.state[n].v,dtype=float),9).tolist() for n in sorted(modified) }
        print(f'  {text!r}: {res}')

if __name__ == '__main__':
    test_values()
    test_errors()
    test_active()
    test_empty()
    test_trees()
    test_statements()
