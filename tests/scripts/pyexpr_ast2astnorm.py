
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

# Tests of the normalisation of parsed expressions alone (_expr_ast2astnorm):
# numbers with units in all units and powers (exact, and only where the values
# stay exactly the same), particle names and PDG codes, the values of in, and
# that normalising twice changes nothing. Trees are parsed (_expr_str2ast) and
# written (_expr_ast2str) to show them, and some are built by hand.

from mcpldev._expr_ast import (
    Binary,
    Compare,
    Float,
    In,
    Int,
    Name,
    Particle,
    Quantity,
    Unary,
    Value,
)
from mcpldev._expr_ast2astnorm import _expr_ast2astnorm
from mcpldev._expr_ast2str import _expr_ast2str
from mcpldev._expr_str2ast import _expr_str2ast
from mcpldev._exprunits import _expr_units, _quantity_value


def norm( text, kind = 'value' ):
    tree = _expr_str2ast(text,kind)
    n = _expr_ast2astnorm(tree)
    assert _expr_ast2astnorm(n) == n, text
    assert _expr_str2ast(_expr_ast2str(n),kind) == n, text
    return _expr_ast2str(n)

def show( texts, kind = 'value' ):
    for text in texts:
        print(f'  {text!r} -> {norm(text,kind)!r}')

def test_quantities():
    print('Numbers with units:')
    show(( '5000eV', '5keV', '0.005MeV', '0.5keV', '1500eV', '1e-12MeV', '2.5e6TeV', '0keV', '0.0MeV',
           '10mm', '0.5mm', '0.02m', '1.8Aa', '20Aa', '0.3nm', '1e5um', '2000us', '0.002s', '5e-4ns',
           '4cm^2', '40000mm^2', '0.04m^2', '2cm^-1', '0.02mm^-1', '1e6m^-2', '0cm^2', '0m^-1',
           '1cm^3', '1e-3m^3', '0x10 mm', '5.0keV', '90.0deg', '1.5rad', '0rad', '0deg', '2.5mm^0.5',
           '0cm^0.5', '300K', '0.0K', '1e30eV', '1e-30MeV', '1.5e20eV', '123456789012345678901234567890Aa',
           '-2.5mm', '-0.0m', '25meV', '0.025eV', '1.1mm', '12345.678km' ))
    #(all units, and the same values as before):
    for unit in _expr_units:
        for number in ( 0, 1, 7, 1000, 0.5, 2.5e-3, 123.456, 1e9, 3e-7 ):
            for power in ( 1, 2, -1, 0.5 ):
                q = Quantity(Int(number) if isinstance(number,int) else Float(number),unit,power)
                n = _expr_ast2astnorm(q)
                assert _quantity_value(n.number.value,n.unit,n.power) == _quantity_value(number,unit,power), q
                assert _expr_ast2astnorm(n) == n, q
    print('All units: the same values, and normalising twice changes nothing')

def test_particles():
    print('Particles and PDG codes:')
    show(( 'pdgcode == 2112', 'pdgcode == neutron', 'pdgcode != -11', 'pdgcode == antielectron',
           'positron == pdgcode', 'pdgcode == 12345', 'pdgcode == 0x16', 'x > neutron', 'x > -positron',
           'abs(pdgcode) == 11', 'abs(pdgcode) == electron', 'pdgcode + 0 == 2112', '0 < pdgcode == 22',
           'pdgcode == photon or pdgcode == gamma', 'pdgcode in (22, neutron, 2112, -11, 12345)',
           'pdgcode not in (antielectron, -11)', 'abs(pdgcode) in (positron, 11, electron)',
           'userflags in (0x10, 1, 16, 0x1)', 'userflags in (16, 0x10)', 'pdgcode == neutron and x > 0cm' ),'edit')
    show(( 'pdgcode = 2112', 'pdgcode = -11', 'pdgcode = antielectron', 'pdgcode += 1', 'pdgcode = 12345',
           'x = neutron*1cm' ),'edit')

def test_others():
    print('Other expressions (only numbers with units and particles change):')
    show(( 'r = hypot(x,y); r > 0.02m and r < 50mm', 'ekin / MeV', '(x**2 + y^2) / cm^2', '2*MeV',
           '0x1F', '2.0', '2e0', 'not (x > 0cm)', 'mod(userflags,2) == 0' ),'edit')
    show(( 'x += 10mm; ekin = 0.025eV; pdgcode = 2112', 'rotate_z(90.0deg); pos += (0,0,1e3mm)' ),'edit')
    #Trees built by hand:
    for tree in ( Value(Quantity(Float(2000.0),'eV',1)),
                  Value(Compare(Name('pdgcode'),( '==', ),( Unary('-',Int(11)), ))),
                  Value(In(Name('pdgcode'),False,( Int(22), Particle('photon'), Int(-11) ))),
                  Value(Binary('*',Particle('neutron'),Quantity(Int(0),'mm',2))) ):
        print(f'  {tree}\n    -> {_expr_ast2astnorm(tree)}')

if __name__ == '__main__':
    test_quantities()
    test_particles()
    test_others()
