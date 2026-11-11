
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

"""numpy (with a helpful error message if it is missing), and a few numpy
utilities."""

__all__ = []

try:
    import numpy as np
except ImportError:
    print()
    print("ERROR: For reasons of efficiency, this MCPL python module requires numpy (www.numpy.org)")
    print("ERROR: to be installed. You can perhaps install it using using your software manager and")
    print("ERROR: searching for \"numpy\" or \"python-numpy\", or it might come bundled with software")
    print("ERROR: such as scientific python or anaconda, depending on your platform. Alternatively,")
    print("ERROR: if you are using the pip package manager, you should be able to install it with")
    print("ERROR: the command \"pip install numpy\".")
    print()
    raise

#The minimum version, as in pyproject.toml:
if np.lib.NumpyVersion(np.__version__) < '1.22.0':
    print(f"MCPL WARNING: Unsupported numpy version ({np.__version__!s}) detected")

def _fma_exact( a, b, c ):
    #Correctly rounded a*b+c with exact rational arithmetic (which is only
    #possible for finite values, otherwise the result is NaN or infinite, like
    #a*b+c):
    import math
    if not ( math.isfinite(a) and math.isfinite(b) and math.isfinite(c) ):
        return a * b + c
    from fractions import Fraction
    return float( Fraction(a) * Fraction(b) + Fraction(c) )

def np_fma( a, b, c ):
    """Fused multiply-add, a*b+c with a single rounding (like fma() in C), for
    numpy arrays. Uses math.fma (Python 3.13+), or slower exact rational
    arithmetic for older Python versions."""
    import math
    fct = getattr(math,'fma',_fma_exact)
    return np.frompyfunc(fct,3,1)(a,b,c).astype(float)

def np_isin_few( values, choices ):
    """np.isin(values,choices) for a few choices (with one comparison for each,
    which is much faster than np.isin then)"""
    values = np.asarray(values)
    res = np.zeros(values.shape,dtype=bool)
    for c in choices:
        res |= ( values == c )
    return res
