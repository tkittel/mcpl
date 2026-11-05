
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

# Tests of the units of expressions (_exprunits): their sizes, which are exact
# for powers of ten (also with whole powers, like mm^2), and the exact values
# of numbers with units, with the decimal digits of the numbers. Also tests
# that they are used when evaluating expressions.

import math

import mcpldev as mcpl
import numpy as np
from mcpldev._expr_eval import _EmptyBlock
from mcpldev._expressions import _Expr
from mcpldev._exprunits import _expr_units, _quantity_value, _unit_size


def test_sizes():
    print('Sizes of units (exact for powers of ten, also with whole powers):')
    for unit, power in ( ( 'mm', 1 ), ( 'mm', 2 ), ( 'mm', 3 ), ( 'um', -2 ), ( 'nm', 2 ), ( 'Aa', -1 ),
                         ( 'm', 0.5 ), ( 'mm', 0.5 ), ( 'eV', -0.5 ), ( 'deg', 1 ), ( 'deg', 2 ),
                         ( 'rad', 1 ), ( 'K', 2 ), ( 'km', -3 ) ):
        #(the naive values, the powers of the sizes, depend on the platform):
        print(f'  {unit}^{power}: {_unit_size(unit,power)!r}')
    for unit in _expr_units:
        assert _unit_size(unit) == _expr_units[unit][0]

def test_quantities():
    print('Numbers with units (exact, with the decimal digits of the numbers):')
    for number, unit, power in ( ( 5000, 'eV', 1 ), ( 5, 'keV', 1 ), ( 0.005, 'MeV', 1 ),
                                 ( 0.1, 'keV', 1 ), ( 0.3, 'nm', 1 ), ( 3, 'Aa', 1 ), ( 25, 'meV', 1 ),
                                 ( 0.07, 'm', 1 ), ( 7, 'cm', 1 ), ( 40000, 'mm', 2 ), ( 400, 'cm', 2 ),
                                 ( 2, 'cm', -1 ), ( 1e-30, 'MeV', 1 ), ( 10**30, 'eV', 1 ),
                                 ( 123456789012345678901234567890, 'Aa', 1 ), ( 2.5, 'mm', 0.5 ),
                                 ( 90, 'deg', 1 ), ( 0, 'm', 1 ), ( -0.0, 'm', 1 ), ( -1.5, 'us', 1 ),
                                 ( 1e308, 'km', 1 ), ( math.inf, 'cm', 1 ) ):
        print(f'  {number!r} {unit}^{power}: {_quantity_value(number,unit,power)!r}')
    #(the same values for all ways of writing them):
    for group in ( ( ( 5000, 'eV' ), ( 5, 'keV' ), ( 0.005, 'MeV' ), ( 5e-6, 'GeV' ) ),
                   ( ( 0.3, 'nm' ), ( 3, 'Aa' ), ( 3e-4, 'um' ), ( 3e-8, 'cm' ) ),
                   ( ( 0.07, 'm' ), ( 7, 'cm' ), ( 70, 'mm' ), ( 7e4, 'um' ) ),
                   ( ( 2000, 'us' ), ( 2, 'ms' ), ( 0.002, 's' ), ( 2e6, 'ns' ) ) ):
        assert len({ _quantity_value(n,u) for n, u in group }) == 1, group
    print('The same values for all ways of writing them: ok')

def test_expressions():
    #(as used when expressions are evaluated):
    print('Constant expressions:')
    for e in ( '5000eV == 5keV', '0.07m == 7cm', '40000mm^2 == 400cm^2', '0.1keV', 'mm^2',
               '1/um^2', '90deg', '1e308km' ):
        try:
            print(f'  {e!r}: {np.asarray(_Expr(e).evaluate(_EmptyBlock()).v).tolist()!r}')
        except mcpl.MCPLError as x:
            print(f'  {e!r}: MCPLError: {x}')

if __name__ == '__main__':
    test_sizes()
    test_quantities()
    test_expressions()
