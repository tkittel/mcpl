
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

"""Integers of expressions (see _expr_eval), on numpy arrays: they work like
in C (see _common_int_type), but results which do not fit their type are
errors instead of wrapping around, and so are unsigned integers combined with
negative values (e.g. in comparisons, which are therefore exact). The
generated C and C++ code does the same (see _expr_chelpers).

The operations get fail(bad, message), which stops with the message if bad
(an array of booleans, or a boolean) is true for a value which is used, so
they know nothing about which particles are used, or about expressions."""

__all__ = []

from ._expr_vocab import (
    _common_int_type,
    _int_constant_type,
    _int_field_types,
    _promoted_type,
)
from ._numpy import np

#The numpy types of the integer types:
_np_types = { 'i32' : np.int32, 'u32' : np.uint32, 'i64' : np.int64, 'u64' : np.uint64 }

def _is_int( v ):
    return np.asarray(v).dtype.kind in 'iu'

def _int_type( dtype ):
    """The type of integers (or booleans) of the numpy type after the integer
    promotions"""
    dt = np.dtype(dtype)
    return _promoted_type(8 * dt.itemsize,dt.kind == 'u')

def _ctype( dtype ):
    """The numpy type of integers (or booleans) after the integer promotions"""
    return np.dtype(_np_types[_int_type(dtype)])

def _common_ctype( *dtypes ):
    """The numpy type of results of integers with these types"""
    return np.dtype(_np_types[_common_int_type(*map(_int_type,dtypes))])

def _int_array( v ):
    """The integer constant v typed like in C (see _int_constant_type), or None
    if it is too large"""
    t = _int_constant_type(v)
    return None if t is None else np.asarray(v,dtype=_np_types[t])

def _int_operands( fail, values, what ):
    """The type of the result of integers (like in C) and the values in that
    type, which must not be negative for unsigned types"""
    values = [ np.asarray(v) for v in values ]
    rt = _common_ctype(*( v.dtype for v in values ))
    if rt.kind == 'u':
        for v in values:
            if v.dtype.kind != 'u':
                fail(v < 0,'Unsigned integers (like userflags) can not be'
                     f' combined with negative values (in {what.lower()})')
    with np.errstate(invalid='ignore'):
        return rt, [ v.astype(rt,copy=False) for v in values ]

def _int_overflow( fail, bad, rt, what ):
    desc = f'{"unsigned " if rt.kind == "u" else ""}{8*rt.itemsize}-bit integers'
    fail(bad,f'{what} of integers gives values outside the range of {desc}')

def _int_divisor( fail, x, y, negative, zero ):
    """The divisor y of the non-negative integers x, with 1 where y is 0
    (with the messages for negative values and for division by zero)"""
    fail(( x < 0 ) | ( y < 0 ),negative)
    is_zero = y == 0
    fail(is_zero,zero)
    return np.where(is_zero,np.ones_like(y),y)

def _int_arith( fail, op, a, b, what ):
    """a + b, a - b, a * b, or a // b of integers, like in C, but with errors
    instead of wrapping around (// only divides non-negative integers, where
    Python and C agree)"""
    rt, ( x, y ) = _int_operands(fail,(a,b),what)
    info = np.iinfo(rt)
    if op == '//':
        y = _int_divisor(fail,x,y,'The operator // can not be used with negative values',
                         'Division by zero (of integers)')
    if rt.itemsize == 4:
        #(computed in 64 bits, where the results of 32-bit integers fit):
        wide = np.uint64 if rt.kind == 'u' else np.int64
        x, y = x.astype(wide), y.astype(wide)
        if op == '-' and rt.kind == 'u':
            x, y = x.astype(np.int64), y.astype(np.int64)
        v = _arith(op,x,y)
        _int_overflow(fail,( v < info.min ) | ( v > info.max ),rt,what)
        return v.astype(rt)
    with np.errstate(over='ignore'):
        v = _arith(op,x,y)
        if op == '+':
            bad = ( v < x ) if rt.kind == 'u' else ( ( ( x ^ v ) & ( y ^ v ) ) < 0 )
        elif op == '-':
            bad = ( x < y ) if rt.kind == 'u' else ( ( ( x ^ y ) & ( x ^ v ) ) < 0 )
        elif op == '*':
            nz = x != 0
            bad = nz & ( v // np.where(nz,x,np.ones_like(x)) != y )
            if rt.kind == 'i':
                bad |= ( ( x == -1 ) & ( y == info.min ) ) | ( ( y == -1 ) & ( x == info.min ) )
        else:
            bad = False#(no overflow, since the values are not negative)
    _int_overflow(fail,bad,rt,what)
    return v

def _arith( op, x, y ):
    if op == '+':
        return x + y
    if op == '-':
        return x - y
    if op == '*':
        return x * y
    #Integer division (of non-negative integers, see _int_arith):
    return np.floor_divide(x,y)

def _int_mod( fail, a, b, what ):
    """mod(a,b) of integers, which must not be negative"""
    _, ( x, y ) = _int_operands(fail,(a,b),what)
    y = _int_divisor(fail,x,y,'mod(a,b) can not be used with negative values',
                     'Division by zero in mod(a,b)')
    return np.mod(x,y)

def _int_negate( fail, v, what ):
    """-v of integers, like in C, but with errors instead of wrapping around,
    and for unsigned integers which are not 0"""
    rt, ( v, ) = _int_operands(fail,(v,),what)
    if rt.kind == 'u':
        fail(v != 0,f'{what} of unsigned integers (like userflags) gives negative'
             ' values, which they can not have')
        return v
    _int_overflow(fail,v == np.iinfo(rt).min,rt,what)
    return -v

def _int_abs( fail, v, what ):
    """abs(v) of integers (see _int_negate)"""
    rt, ( v, ) = _int_operands(fail,(v,),what)
    if rt.kind == 'u':
        return v
    neg = v < 0
    return np.where(neg,_int_negate(fail,np.where(neg,v,0),what),v)

def _int_bitwise( fail, op, a, b ):
    """a & b or a | b of integers, like in C"""
    _, ( x, y ) = _int_operands(fail,(a,b),f'the operation {op}')
    return np.bitwise_and(x,y) if op == '&' else np.bitwise_or(x,y)

def _int_field_values( fail, name, v ):
    """Values for pdgcode or userflags, which must be integers in the range
    of their types (see _int_field_types)"""
    v = np.asarray(v)
    if v.dtype.kind not in 'iub':
        fail(np.round(v) != v,f'Non-integer values assigned to {name}')
    info = np.iinfo(_np_types[_int_field_types[name]])
    fail(( v < info.min ) | ( v > info.max ),
         f'Values assigned to {name} must be integers from {info.min} to {info.max}')
    return v.astype(info.dtype)
