
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

"""Values of expressions for plots and coordinates, and their units"""

__all__ = []

from ._common import MCPLError
from ._expressions import ParticleValue, _EmptyBlock, _Expr, _expr_value_names, _values
from ._exprsyntax import _dim_E, _dim_L, _dim_T, _expr_units
from ._numpy import np


class _PlotValue:
    """Values of an expression for plots, which can have units (the axes of the
    plots show the units, see _plot_unit): the values are in the units of
    MCPL (cm, MeV and ms, also for wavelengths), with the dimension dim (None
    for values without units)."""
    def __init__( self, expression ):
        if isinstance(expression,(ParticleValue,_PlotValue)):
            expression = expression.expression
        self._e = _Expr(expression)
        self.expression = self._e.text
        q = self._e.evaluate(_EmptyBlock())#(also checks the units)
        self.dim = q.d
        self.wavelength = 'wavelength' in self._e.fields
    def __call__( self, block ):
        """The values for the particles of the block (NaN where the expression
        is not defined, see _Expr.domains)"""
        if not self._e.domains:
            return _values(self._e.evaluate(block),block)
        mask = self._e.domain_mask(block)
        v = np.array(_values(self._e.evaluate(block,active=mask),block),dtype=float)
        v[~mask] = np.nan
        return v

    def domain_values( self, block ):
        """The values of the fields deciding where the expression is defined,
        for the particles of the block where it is (as {field : set})"""
        if not self._e.domains:
            return {}
        mask = self._e.domain_mask(block)
        return { field : set( np.unique(np.broadcast_to(getattr(block,field),(len(block),))[mask]).tolist() )
                 for field, _ in self._e.domains }

    def domain_note( self, seen, unicode = False ):
        """Note for labels on the particles for which the values are defined,
        like "(n/gamma only)", given the values of domain_values seen (or None if
        defined for all particles, see _expr_value_names for unicode)"""
        return _domain_note([ ( field, [ v for v in values if v in seen.get(field,()) ] )
                              for field, values in self._e.domains ],unicode)

def _domain_note( domains, unicode = False ):
    """Note for labels on the values of fields for which values are defined
    (a list of (field, values)), like "(n/gamma only)", or None"""
    names = [ _expr_value_names[field][1](v,unicode) for field, values in domains
              for v in values ]
    return f'({"/".join(names)} only)' if names else None

#Units of the base dimensions for plots (see _plot_unit), by increasing size,
#and the standard ones for logarithmic axes:
_plot_units = [ [ u for u, ( _, d ) in sorted(_expr_units.items(),key=lambda e : e[1][0])
                  if d == base ] for base in ( _dim_L, _dim_E, _dim_T ) ]
_plot_units_log = ( 'm', 'eV', 's' )
_plot_units_mcpl = ( 'cm', 'MeV', 'ms' )
#Wavelengths in this range (in Aa) are shown in Aa:
_plot_wl_range = ( 0.5e-3, 5e3 )

def _plot_unit( dim, lo, hi, log = False, wavelength = False ):
    """The unit for showing values with the dimension dim from lo to hi (in the
    units of MCPL), as (text, scale), where scale is the size of the unit in the
    units of MCPL (values are divided by it), or None for values without units.
    For a single base dimension (with a power, as for x^2 or sqrt(ekin)):
    wavelengths from 0.5e-3 to 5e3 Aa are in Aa, logarithmic axes are in m, eV
    or s, and linear axes in the largest unit in which the largest absolute
    value is at least 1. Other dimensions are in the units of MCPL."""
    if dim is None:
        return None
    powers = [ ( i, e ) for i, e in enumerate(dim) if e ]
    def text( units ):
        return '*'.join( units[i] + ( '' if e == 1 else f'^{e!r}' ) for i, e in powers )
    if len(powers) != 1:
        return text(_plot_units_mcpl), 1.0
    i, e = powers[0]
    amax = max(abs(lo),abs(hi))
    #(the size of the values in the base dimension, e.g. a length for x^2):
    size = amax ** ( 1.0 / e ) if amax > 0 else 0.0
    wl_lo, wl_hi = ( v * _expr_units['Aa'][0] for v in _plot_wl_range )
    if wavelength and dim == _dim_L and lo >= wl_lo and hi <= wl_hi:
        unit = 'Aa'
    elif log:
        unit = _plot_units_log[i]
    elif size > 0:
        fits = [ u for u in _plot_units[i] if size / _expr_units[u][0] >= 1 ]
        unit = fits[-1] if fits else _plot_units[i][0]
    else:
        unit = _plot_units_mcpl[i]
    units = list(_plot_units_mcpl)
    units[i] = unit
    return text(units), _expr_units[unit][0] ** e

def _range_value( text ):
    """The value (in the units of MCPL) and dimension of a constant in the range
    of a histogram, like 10cm or -2.5"""
    e = _Expr(text)
    if e.fields:
        raise MCPLError(f'Ranges of histograms must be constants (not "{text}")')
    q = e.evaluate(_EmptyBlock())
    return float(np.asarray(q.v)), q.d
