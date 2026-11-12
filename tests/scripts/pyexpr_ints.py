
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
# Tests of the integers of expressions (_expr_ints): every operation, for
# every pair of integer types, with values at the limits of the types,
# compared with the exact integers of Python. A result must be exact when it
# fits the type of the result (the type of C, see _common_int_type), and an
# error otherwise, as must unsigned integers combined with negative values.

import itertools

from mcpldev._expr_ints import (
    _ctype,
    _int_abs,
    _int_arith,
    _int_array,
    _int_bitwise,
    _int_field_values,
    _int_mod,
    _int_negate,
    _int_operands,
    _int_type,
    _is_int,
    _np_types,
)
from mcpldev._expr_vocab import _common_int_type, _int_range
from mcpldev._numpy import np


class Failed(Exception):
    pass

def fail( bad, msg ):
    if np.any(bad):
        raise Failed(msg)

def edge_values( t ):
    lo, hi = _int_range(t)
    values = { lo, lo + 1, -1, 0, 1, 2, 3, hi // 2, hi - 1, hi, -( hi // 2 ) }
    return sorted( v for v in values if lo <= v <= hi )

def expected( op, a, b, rt ):
    """The exact result, or the kind of error"""
    lo, hi = _int_range(rt)
    if rt[0] == 'u' and ( a < 0 or ( b is not None and b < 0 ) ):
        return 'negative unsigned'
    if op in ( '//', 'mod' ):
        if a < 0 or b < 0:
            return 'negative'
        if b == 0:
            return 'division by zero'
    v = { '+' : lambda : a + b, '-' : lambda : a - b, '*' : lambda : a * b,
          '//' : lambda : a // b, 'mod' : lambda : a % b, 'neg' : lambda : -a,
          'abs' : lambda : abs(a), '&' : lambda : a & b, '|' : lambda : a | b }[op]()
    if op in ( '&', '|' ) and rt[0] == 'u':
        v &= hi
    if not lo <= v <= hi:
        return 'unsigned negative' if rt[0] == 'u' and op == 'neg' else 'overflow'
    return v

def kind( msg ):
    """The kind of error of a message"""
    if 'combined with negative' in msg:
        return 'negative unsigned'
    if 'gives negative values' in msg:
        return 'unsigned negative'
    if 'can not be used with negative' in msg:
        return 'negative'
    if 'Division by zero' in msg:
        return 'division by zero'
    if 'outside the range' in msg:
        return 'overflow'
    return msg

def run( op, a, b, ta, tb ):
    x = np.asarray([ a ],dtype=_np_types[ta])
    y = None if b is None else np.asarray([ b ],dtype=_np_types[tb])
    try:
        if op in ( '+', '-', '*', '//' ):
            v = _int_arith(fail,op,x,y,'Test')
        elif op == 'mod':
            v = _int_mod(fail,x,y,'mod(..)')
        elif op in ( '&', '|' ):
            v = _int_bitwise(fail,op,x,y)
        elif op == 'neg':
            v = _int_negate(fail,x,'Negation')
        else:
            v = _int_abs(fail,x,'abs(..)')
    except Failed as e:
        return kind(str(e)), None
    return int(v[0]), v.dtype

def test_operations():
    print('Operations, with the values at the limits of the types:')
    types = list(_np_types)
    for op in ( '+', '-', '*', '//', 'mod', '&', '|' ):
        counts, bad = {}, []
        for ta, tb in itertools.product(types,types):
            rt = _common_int_type(ta,tb)
            for a, b in itertools.product(edge_values(ta),edge_values(tb)):
                want = expected(op,a,b,rt)
                got, dtype = run(op,a,b,ta,tb)
                key = 'exact' if isinstance(want,int) else want
                counts[key] = counts.get(key,0) + 1
                if got != want or ( dtype is not None and dtype != np.dtype(_np_types[rt]) ):
                    bad.append(f'{a} {op} {b} ({ta}, {tb}): {got} ({dtype}), not {want}')
        print(f'  {op}: ' + ', '.join( f'{n} {k}' for k, n in sorted(counts.items()) )
              + ( '' if not bad else f'; {len(bad)} WRONG, like ' + '; '.join(bad[:3]) ))
    for op in ( 'neg', 'abs' ):
        counts, bad = {}, []
        for t in types:
            for a in edge_values(t):
                want = expected(op,a,None,t)
                if op == 'abs' and t[0] == 'u':
                    want = a
                got, _ = run(op,a,None,t,None)
                key = 'exact' if isinstance(want,int) else want
                counts[key] = counts.get(key,0) + 1
                if got != want:
                    bad.append(f'{op} {a} ({t}): {got}, not {want}')
        print(f'  {op}: ' + ', '.join( f'{n} {k}' for k, n in sorted(counts.items()) )
              + ( '' if not bad else f'; {len(bad)} WRONG, like ' + '; '.join(bad[:3]) ))

def test_comparisons():
    #(exact also for values of different types, and errors for unsigned
    #integers compared with negative values):
    print('Comparisons:')
    types = list(_np_types)
    counts, bad = { 'exact' : 0, 'negative unsigned' : 0 }, []
    for ta, tb in itertools.product(types,types):
        rt = _common_int_type(ta,tb)
        for a, b in itertools.product(edge_values(ta),edge_values(tb)):
            x, y = np.asarray([ a ],dtype=_np_types[ta]), np.asarray([ b ],dtype=_np_types[tb])
            try:
                _, ( x, y ) = _int_operands(fail,(x,y),'a comparison')
            except Failed as e:
                counts[kind(str(e))] += 1
                if not ( rt[0] == 'u' and min(a,b) < 0 ):
                    bad.append(f'{a} vs {b} ({ta}, {tb}): {e}')
                continue
            counts['exact'] += 1
            if [ bool(x[0] < y[0]), bool(x[0] == y[0]) ] != [ a < b, a == b ]:
                bad.append(f'{a} vs {b} ({ta}, {tb})')
    print('  ' + ', '.join( f'{n} {k}' for k, n in counts.items() )
          + ( '' if not bad else f'; {len(bad)} WRONG, like ' + '; '.join(bad[:3]) ))

def test_types():
    #(the integer promotions of the numpy types, as in C, and the types of
    #integer constants):
    print('Types:')
    for dt in ( bool, np.int8, np.uint8, np.int16, np.uint16, np.int32, np.uint32, np.int64, np.uint64 ):
        print(f'  {np.dtype(dt).name} -> {_int_type(dt)} ({_ctype(dt).name})')
    #(integers, not booleans or floating point numbers):
    print('  integers: ' + ', '.join( f'{np.dtype(dt).name} {_is_int(np.zeros(1,dtype=dt))}'
                                      for dt in ( np.int8, np.uint64, bool, np.float64 ) ))
    for v in ( 0, 2147483647, 2147483648, -2147483648, -2147483649, 9223372036854775807,
               9223372036854775808, 18446744073709551615, 18446744073709551616,
               -9223372036854775808, -9223372036854775809 ):
        c = _int_array(v)
        print(f'  {v}: ' + ( 'too large' if c is None else c.dtype.name ))

def test_field_values():
    #(values for pdgcode and userflags: integers in the range of their types):
    print('Values for fields:')
    for name, values in ( ( 'pdgcode', [ 2112, -2147483648, 2147483647, 2147483648, 2.0, 2.5,
                                         float('nan'), float('inf') ] ),
                          ( 'userflags', [ 0, 4294967295, -1, 4294967296, 7.0 ] ) ):
        for v in values:
            x = np.asarray([ v ],dtype=float if isinstance(v,float) else np.int64 if v < 2**63 else np.uint64)
            try:
                r = _int_field_values(fail,name,x)
                print(f'  {name} = {v!r}: {int(r[0])} ({r.dtype.name})')
            except Failed as e:
                print(f'  {name} = {v!r}: {e}')

def test_used_values():
    #(only the values which are used count: fail gets the bad values, and
    #ignores the others, here those of a mask):
    print('Only used values:')
    used = np.asarray([ True, False ])
    def fail_used( bad, msg ):
        if np.any(np.asarray(bad) & used):
            raise Failed(msg)
    x = np.asarray([ 1, 2147483647 ],dtype=np.int32)
    v = _int_arith(fail_used,'+',x,np.asarray([ 1, 1 ],dtype=np.int32),'Addition')
    print(f'  [1, 2147483647] + 1, using the first: {int(v[0])}')
    try:
        _int_arith(fail,'+',x,np.asarray([ 1, 1 ],dtype=np.int32),'Addition')
    except Failed as e:
        print(f'  using both: {e}')

if __name__ == '__main__':
    test_operations()
    test_comparisons()
    test_types()
    test_field_values()
    test_used_values()
