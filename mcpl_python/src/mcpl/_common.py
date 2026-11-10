
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

"""MCPLError, the version, and small helpers used by the other modules."""

__all__ = ['MCPLError']

__version__ = '2.2.9'

import os
import sys


def _checkpyversion():
    pyversion = sys.version_info[0:3]
    _minpyv=(3,9,0)
    if pyversion < _minpyv:
        a = '.'.join(str(i) for i in pyversion)
        b = '.'.join(str(i) for i in _minpyv)
        raise ImportError('MCPL Error: Unsupported python version'
                          f' {a} detected (needs {b} or later).')
_checkpyversion()


#For raw output of byte-array contents to stdout, without any troubles depending
#on encoding or python versions:
def _output_bytearray_raw(b):
    sys.stdout.flush()
    getattr(sys.stdout,'buffer',sys.stdout).write(b)
    sys.stdout.flush()


class MCPLError(Exception):
    """Common exception class for all exceptions raised by module"""

def _native_endianness():
    return 'L' if sys.byteorder == 'little' else 'B'

def _parse_count( text ):
    """The whole number which the text gives, as digits (like 1000) or as a
    decimal number which is a whole number (like 1e8 or 2.5e3), or None if it
    gives none (also for texts like 1,000)"""
    import re
    #(not more than 64 bits, as in C):
    if re.fullmatch(r'[0-9]+',text):
        return int(text) if int(text) < 2**64 else None
    if not re.fullmatch(r'([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?',text):
        return None
    from decimal import Decimal
    d = Decimal(text)
    #(which also keeps exponents like 1e999999 cheap):
    if d >= 2**64 or d != d.to_integral_value():
        return None
    return int(d)

def _as_limit( value ):
    """The number of particles which a limit argument allows, or None for all
    (a limit of None or 0). Raises MCPLError for other values than
    non-negative whole numbers."""
    return None if value is None else ( _as_count(value,'limit') or None )

def _as_skip( value ):
    """The number of particles which a skip argument skips (0 for None).
    Raises MCPLError for other values than non-negative whole numbers."""
    return 0 if value is None else _as_count(value,'skip')

def _as_count( value, what ):
    try:
        ok = not isinstance(value,(bool,str)) and int(value) == value and value >= 0
    except (TypeError,ValueError):
        ok = False
    if not ok:
        raise MCPLError(f'{what} must be a number of particles (not {value!r})')
    return int(value)

def _listed( words, conjunction = 'and' ):
    """The words joined as in "a and b" or "a, b, and c" (with the conjunction)"""
    words = list(words)
    if len(words) < 3:
        return f' {conjunction} '.join(words)
    return ', '.join(words[:-1]) + f', {conjunction} ' + words[-1]

def _particle_range( n, skip, limit ):
    """The range of particles (first, end) of a file of n particles, without
    the first skip of them and with at most limit (all if limit is None, see
    _as_limit)"""
    first = min( skip or 0, n )
    return first, n if limit is None else min( n, first + limit )

def _determine_version():
    if os.environ.get('PYMCPLTOOL_FAKE_PYVERSION','').strip():
        return '99.99.99'
    else:
        return __version__
