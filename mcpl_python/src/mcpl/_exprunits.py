
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

"""The dimensions and units of the quantities in particle expressions (see
_expressions), and their exact sizes (see _unit_size and _quantity_value)."""

__all__ = []

import decimal
import functools
import math

#Dimensions (length,energy,time,temperature) and units of quantities in
#expressions. Values are internally in the units of MCPL (cm, MeV, ms), also for
#wavelengths, and temperatures (of userdata) in K:
_dim_none = (0,0,0,0)
_dim_L, _dim_E, _dim_T, _dim_K = (1,0,0,0), (0,1,0,0), (0,0,1,0), (0,0,0,1)
#(the dimension of fields of the userdata when expressions are checked
#without a file, which have units only in the layouts of files: everything
#computed from them has unknown units, which are never refused):
_dim_unknown = 'unknown'
_expr_units = { 'meV' : (1e-9,_dim_E), 'eV' : (1e-6,_dim_E),
                'keV' : (1e-3,_dim_E), 'MeV' : (1.0,_dim_E),
                'GeV' : (1e3,_dim_E), 'TeV' : (1e6,_dim_E),
                'ns' : (1e-6,_dim_T), 'us' : (1e-3,_dim_T),
                'ms' : (1.0,_dim_T), 's' : (1e3,_dim_T),
                'Aa' : (1e-8,_dim_L), 'nm' : (1e-7,_dim_L),
                'um' : (1e-4,_dim_L), 'mm' : (0.1,_dim_L),
                'cm' : (1.0,_dim_L), 'm' : (100.0,_dim_L),
                'km' : (1e5,_dim_L), 'K' : (1.0,_dim_K),
                'deg' : (math.pi/180,None), 'rad' : (1.0,None) }

def _decimal_exponent( size ):
    """n if the size is 10^n, else None"""
    d = decimal.Decimal(repr(size))
    n = d.adjusted()
    return n if d == decimal.Decimal(1).scaleb(n) else None

#The units which are powers of ten of the units of MCPL, with their exponents
#(all but deg):
_unit_exponents = { u : n for u, ( size, _ ) in _expr_units.items()
                    if ( n := _decimal_exponent(size) ) is not None }

@functools.lru_cache
def _unit_size( unit, power = 1 ):
    """The size of the unit to the power, in the units of MCPL. Whole powers
    of ten are exact (as the nearest floating point numbers, e.g. mm^2 is
    0.01, not 0.1^2)."""
    n = _unit_exponents.get(unit)
    if n is not None and float(n * power).is_integer():
        return float(f'1e{int(n * power)}')
    return _expr_units[unit][0] ** power

def _quantity_value( number, unit, power = 1 ):
    """The number (an int or float) times the unit to the power, in the units
    of MCPL. For units which are powers of ten (with whole exponents), this is
    exact, with the decimal digits of the number (e.g. 5000eV and 5keV are
    the same, and 0.1keV is the nearest floating point number to 0.0001)."""
    #(cached by the text of the number, which also tells -0.0 from 0.0, as
    #constants are evaluated for each block of particles):
    return _quantity_value_of(repr(number),unit,power)

@functools.lru_cache
def _quantity_value_of( text, unit, power ):
    n = _unit_exponents.get(unit)
    if n is None or not float(n * power).is_integer() or not math.isfinite(float(text)):
        return float(text) * _unit_size(unit,power)
    d = decimal.Decimal(text)
    with decimal.localcontext() as ctx:
        ctx.prec = len(d.as_tuple().digits)#(so scaleb is exact)
        return float(d.scaleb(int(n * power)))
