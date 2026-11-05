
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

"""The evaluation of checked particle expressions (see _expr_astcheck) with
numpy, on blocks of particles: _ExprEvaluator(block, text) evaluates
expressions, and _run_statements runs the statements of edit expressions. The
units and types of the values are checked here, also for blocks without
particles (_EmptyBlock), which is how expressions are checked before use."""

__all__ = []

from ._common import MCPLError
from ._expr_ast import (
    Assign,
    Binary,
    Call,
    Compare,
    Float,
    In,
    Int,
    Logical,
    Name,
    Part,
    Particle,
    Quantity,
    Unary,
    Unit,
    Userdata,
    Value,
    Vector,
)
from ._expr_ast2str import _expr_ast2str
from ._expr_vocab import (
    _assignable,
    _expr_constants,
    _expr_field_dims,
    _expr_unit_hints,
    _expr_vectors,
    _expr_wl_unit,
    _functions_nodim,
    _functions_toint,
    _functions_vector,
    _is_condition,
    _rotated_vectors,
    _rotation_matrix_args,
    _rotation_planes,
)
from ._exprrotation import _exact_cos_sin, _rotation_matrix
from ._exprunits import _dim_E, _dim_L, _dim_none, _dim_unknown, _expr_units
from ._numpy import np
from ._particles import _particle_names, _wavelength_pdgcodes
from ._physics import ekin_from_wavelength, wavelength_from_ekin

#The numpy functions of the functions of _expr_vocab:
_np_functions = { 'exp' : np.exp, 'log' : np.log, 'log10' : np.log10,
                  'sin' : np.sin, 'cos' : np.cos, 'tan' : np.tan,
                  'asin' : np.arcsin, 'acos' : np.arccos, 'atan' : np.arctan,
                  'round' : np.rint, 'floor' : np.floor, 'ceil' : np.ceil,
                  'abs' : np.abs, 'min' : np.minimum, 'max' : np.maximum }

def _angle_highres( a, b ):
    """Angles between the vectors a and b (given as tuples of components),
    precise also for small angles (unlike acos of the dot product of the
    normalised vectors). Based on the formula on page 47 of "How Futile are
    Mindless Assessments of Roundoff in Floating-Point Computation?" by W.
    Kahan (2006), like NCrystal::Vector::angle_highres."""
    a = [ np.asarray(c,dtype=np.float64) for c in a ]
    b = [ np.asarray(c,dtype=np.float64) for c in b ]
    na = np.sqrt( a[0]*a[0] + a[1]*a[1] + a[2]*a[2] )
    nb = np.sqrt( b[0]*b[0] + b[1]*b[1] + b[2]*b[2] )
    ua = [ c / na for c in a ]
    ub = [ c / nb for c in b ]
    dmag = np.sqrt( sum( ( x - y )**2 for x, y in zip(ua,ub) ) )
    smag = np.sqrt( sum( ( x + y )**2 for x, y in zip(ua,ub) ) )
    return 2.0 * np.arctan2(dmag,smag)

class _Q:
    """Value with dimension (length,energy,time,temperature) in an expression.
    Values without units (like plain numbers, or ux) have dimension None. A
    plain 0 (zero is the same in all units) is marked with zero=True, and can
    be used with any units. Integers are numpy arrays with the integer types of
    C after its integer promotions (int32, uint32, int64, or uint64)."""
    __slots__ = ('d','v','zero')
    def __init__( self, v, d = None, zero = False ):
        self.v, self.d = v, ( None if d == _dim_none else d )
        self.zero = zero

#Integers in expressions work like in C (with its integer promotions and usual
#arithmetic conversions), but results which do not fit their type are errors
#instead of wrapping around, and so are unsigned integers combined with
#negative values (e.g. in comparisons, which are therefore exact):
_int_types = { (4,False) : np.int32, (4,True) : np.uint32,
               (8,False) : np.int64, (8,True) : np.uint64 }

def _is_int( v ):
    return np.asarray(v).dtype.kind in 'iu'

def _ctype( dtype ):
    """The type of integers (or booleans) after the integer promotions of C"""
    dt = np.dtype(dtype)
    if dt.kind == 'b' or dt.itemsize < 4:
        return np.dtype(np.int32)
    return np.dtype(_int_types[(dt.itemsize,dt.kind == 'u')])

def _common_ctype( *dtypes ):
    """The type of results of integers with these types (the usual arithmetic
    conversions of C)"""
    res = None
    for dt in dtypes:
        dt = _ctype(dt)
        if res is None or dt == res:
            res = dt
            continue
        u = [ t for t in (res,dt) if t.kind == 'u' ]
        si = [ t for t in (res,dt) if t.kind == 'i' ]
        if len(u) == 2 or len(si) == 2:
            res = max(res,dt,key=lambda t : t.itemsize)
        else:
            res = u[0] if u[0].itemsize >= si[0].itemsize else si[0]
    return res

def _int_constant( v ):
    """Integer constants typed like in C (as int if they fit, then as int64,
    then as uint64), or None if they are too large"""
    for t in ( np.int32, np.int64, np.uint64 ):
        info = np.iinfo(t)
        if info.min <= v <= info.max:
            return np.asarray(v,dtype=t)
    return None

class _V:
    """A vector in an expression: its values (_Q, two or three, with the same
    units, except that plain zeros fit any units)"""
    __slots__ = ('c',)
    def __init__( self, c ):
        self.c = list(c)
    @property
    def d( self ):
        """The units (of the values which are not plain zeros)"""
        return next( ( q.d for q in self.c if not q.zero ), None )
    def describe( self ):
        return f'a {len(self.c)}D vector' + ( f' of {_dimstr(self.d)}s' if self.d else '' )

def _dimstr( d ):
    if d is None:
        return 'value without units'
    res = []
    for n, e in zip(('length','energy','time','temperature'),d):
        if e:
            res.append( n if e == 1 else f'{n}^{e}' )
    return '*'.join(res)

def _userdata_unit( layout, field ):
    """The size (in the units of expressions) and dimension of the unit of the
    field of the userdata layout, as (1.0, None) for fields without a unit"""
    from ._userdata import userdata_units
    unit = userdata_units(layout).get(field)
    factor, dim = 1.0, [ 0, 0, 0, 0 ]
    for part in ( unit.split('.') if unit else () ):
        name, _, power = part.partition('^')
        size, d = _expr_units[name]
        e = int(power) if power else 1
        factor *= size ** e
        if d is not None:
            dim = [ a + b * e for a, b in zip(dim,d) ]
    return factor, ( tuple(dim) if any(dim) else None )

def _unit_hint( d ):
    u = _expr_unit_hints.get(d)
    return f' (add units, e.g. 2{u})' if u else ''

#The descriptions of the binary operators, for messages:
_op_what = { '+' : 'Addition', '-' : 'Subtraction', '*' : 'Multiplication',
             '/' : 'Division', '//' : 'Integer division', '^' : 'Raising to a power' }
_compare_fcts = { '==' : np.equal, '!=' : np.not_equal, '<' : np.less,
                  '<=' : np.less_equal, '>' : np.greater, '>=' : np.greater_equal }

class _ExprEvaluator:
    """Evaluates parsed expressions on a block of particles with numpy"""
    def __init__( self, block, expr, state = None ):
        self._block = block
        self._expr = expr
        self._cache = {}
        #Values of variables and modified fields (in edits):
        self.state = state if state is not None else {}
        #Particles for which the current part of the expression is used (None
        #for all), e.g. only those for which the left side of and is true:
        self.active = None
        #The positions in the block of the particles kept by the conditions of
        #edit expressions (None for all, see keep):
        self.kept = None
    def keep( self, mask ):
        """Keep only the particles of the mask, for the rest of the statements
        (their positions in the block are in kept)"""
        idx = np.flatnonzero(mask)
        n = len(self._block)
        self.kept = idx if self.kept is None else self.kept[idx]
        self._block = _Kept(self._block,idx)
        self._cache = { k : _kept_value(q,idx,n) for k, q in self._cache.items() }
        self.state = { k : _kept_value(q,idx,n) for k, q in self.state.items() }
    def error( self, msg ):
        raise MCPLError(f'{msg} in expression "{self._expr}"')
    def name( self, n ):
        if n == 'wavelength':
            self._check_wavelength()
            q = self._wavelength()
            v = np.asarray(q.v)
            if self._any_active(~np.isfinite(v)):
                self.error('The wavelength is infinite for particles with zero'
                           ' kinetic energy')
            return q
        if n in self.state:
            return self.state[n]
        if n in _expr_vectors:
            return _V( self.name(c) for c in _expr_vectors[n] )
        if n in _expr_constants:
            return _Q(_expr_constants[n])
        if n not in self._cache:
            self._cache[n] = self._typed(_Q(getattr(self._block,n),_expr_field_dims.get(n)))
        #(checked for each use, for the particles in use there):
        return self.finite(self._cache[n],f'The particle field {n} has')
    @staticmethod
    def _typed( q ):
        """q with the integer types of C (see _Q), or as float64 (e.g. for
        float32 userdata)"""
        v = np.asarray(q.v)
        if v.dtype.kind in 'iub':
            v = v.astype(_ctype(v.dtype),copy=False)
        elif v.dtype != np.float64:
            v = v.astype(np.float64)
        return _Q(v,q.d)
    def userdata( self, node ):
        """The values of the field of the userdata (with the unit of the field
        in the layout, if any), or of the value with the index (from 0) of a
        field with an array of values"""
        key = node.text
        if key not in self._cache:
            self._cache[key] = self._typed(self._userdata(node.field,node.index))
        return self.finite(self._cache[key],f'The userdata field {node.field} has')
    def _userdata( self, field, index ):
        if isinstance(self._block,_EmptyBlock):
            #(all fields, when checked without a file, with unknown units, and
            #as integers, which can be used in all places):
            return _Q(np.zeros(0,dtype=np.int64),_dim_unknown)
        ud = getattr(self._block,'userdata',None)
        udinfo = getattr(self._block,'_udinfo',None)
        name = f'userdata.{field}' + ( '' if index is None else f'.at({index})' )
        if ud is None or udinfo is None:
            self.error(f'The particles have no userdata (for {name})')
        names = ud.dtype.names
        if field not in names:
            self.error(f'No userdata field "{field}" (the fields are: {", ".join(names)})')
        v = ud[field]
        n = v.shape[1] if v.ndim > 1 else None
        if n is None and index is not None:
            self.error(f'The userdata field "{field}" has one value per particle'
                       f' (use userdata.{field} without .at({index}))')
        if n is not None and index is None:
            self.error(f'The userdata field "{field}" has {n} values per particle'
                       f' (use userdata.{field}.at(0) to userdata.{field}.at({n-1}))')
        if index is not None:
            if index >= n:
                self.error(f'The index {index} is too large for the userdata field "{field}",'
                           f' which has {n} values per particle (from .at(0) to .at({n-1}))')
            v = v[:,index]
        factor, dim = _userdata_unit(udinfo[0],field)
        if factor != 1.0:
            #(e.g. deg in radians, in float64 also for float32 fields):
            v = ( v.astype(np.float64) if v.dtype.kind == 'f' else v ) * factor
        return _Q(v,dim)

    def _wavelength( self ):
        #Wavelengths (NaN for particles other than neutrons and gammas, for
        #which they are not used), also of modified particles in edits:
        if 'wavelength' in self.state:
            return self.state['wavelength']
        if 'ekin' in self.state or 'pdgcode' in self.state or 'wavelength' not in self._cache:
            q = _Q(wavelength_from_ekin(self.name('ekin').v,
                                        self.name('pdgcode').v) * _expr_wl_unit,
                   _dim_L)
            if 'ekin' in self.state or 'pdgcode' in self.state:
                return q
            self._cache['wavelength'] = q
        return self._cache['wavelength']
    def finite( self, q, what ):
        """Raise MCPLError if q has NaN or infinite values (for the active
        particles)"""
        if isinstance(q,_V):
            for c in q.c:
                self.finite(c,what)
            return q
        v = np.asarray(q.v)
        if v.dtype.kind in 'fc' and self._any_active(~np.isfinite(v)):
            self.error(f'{what} NaN or infinite values')
        return q
    def _check_wavelength( self ):
        pdg = np.asarray(self.name('pdgcode').v)
        if self._any_active(~np.isin(pdg,_wavelength_pdgcodes)):
            raise MCPLError('The wavelength is only defined for neutrons and gammas,'
                            ' so keep only those before using it, e.g. "pdgcode =='
                            f' neutron; wavelength > 1.8Aa" (in expression "{self._expr}")')
    def _any_active( self, mask ):
        """Whether the mask is true for any of the active particles (see
        _with_active)"""
        return bool(np.any( mask if self.active is None else mask & self.active ))
    def _with_active( self, mask, node ):
        """Evaluate node, for the particles where mask is true (and which are
        currently active)"""
        prev = self.active
        mask = np.asarray(mask,dtype=bool)
        self.active = mask if prev is None else ( prev & mask )
        try:
            return self(node)
        finally:
            self.active = prev
    def common( self, args, what ):
        """Check that the values have the same dimension (where a plain 0 has
        any, see _Q), and return their values and the dimension"""
        ref = next( ( q for q in args if not q.zero ), args[0] )
        res = [ self.same(ref,q,what) for q in args ]
        d = _dim_unknown if any( r[2] == _dim_unknown for r in res ) else ref.d
        return [ r[1] for r in res ], d
    def same( self, a, b, what ):
        """Check that a and b have the same dimension (for +, -, comparisons,
        etc.) and return their values and the dimension."""
        if _dim_unknown in ( a.d, b.d ):
            return a.v, b.v, _dim_unknown
        if a.d != b.d and ( a.zero or b.zero ):
            return a.v, b.v, ( a.d or b.d )
        if a.d != b.d:
            hint = _unit_hint(a.d or b.d) if None in (a.d,b.d) else ''
            self.error(f'Incompatible units in {what}: {_dimstr(a.d)} and'
                       f' {_dimstr(b.d)}{hint}')
        return a.v, b.v, a.d
    def nodim( self, q, what ):
        if q.d not in ( None, _dim_unknown ):
            self.error(f'{what} requires a value without units, not {_dimstr(q.d)}')
        return q.v
    def __call__( self, node ):
        return _dispatch[type(node)](self,node)
    def _value( self, node ):
        return self(node.expr)
    def _int( self, node ):
        v = node.value
        c = _int_constant(v)
        if c is None:
            self.error(f'The integer {v} is too large (integers must fit in 64 bits)')
        return _Q(c,zero=(v==0))
    def _float( self, node ):
        v = node.value
        return self.finite(_Q(v,zero=(v==0)),'A constant has')
    def _quantity( self, node ):
        #(the number multiplied by the unit):
        q = self.binop('*',self(node.number),self(Unit(node.unit,node.power)))
        return self.finite(q,'Multiplication gives')
    def _unit( self, node ):
        v, d = _expr_units[node.unit]
        return _Q(v ** node.power,self.dimpow(d,node.power,f'The unit {node.unit}'))
    def _name( self, node ):
        return self.name(node.id)
    def _particle( self, node ):
        return _Q(_int_constant(_particle_names[node.name]))
    def _vector( self, node ):
        return self.vector([ self(c) for c in node.components ])
    def _part( self, node ):
        v, i = self(node.vector), node.index
        if not isinstance(v,_V):
            self.error('Only vectors have values like .x or .at(INDEX)')
        if i >= len(v.c):
            self.error(f'The index {i} is too large for {v.describe()}'
                       ' (the values are counted from 0)')
        return v.c[i]
    def _logical( self, node ):
        #The right side of and (or) is only used for particles
        #where the left side is true (false):
        is_and = node.op == 'and'
        fct = np.logical_and if is_and else np.logical_or
        res = self.boolval(self(node.values[0]))
        for v in node.values[1:]:
            b = self.boolval(self._with_active(res if is_and else ~np.asarray(res,dtype=bool),v))
            res = fct(res,b)
        return _Q(res)
    def _unary( self, node ):
        c = node.operand
        if node.op == '-' and isinstance(c,Int):
            #(negative integer constants, like -2147483648):
            return self(Int(-c.value))
        q = self(c)
        if isinstance(q,_V):
            if node.op == 'not':
                self.error(f'not can not be used for vectors (here {q.describe()})')
            return _V( self.negate(c) for c in q.c ) if node.op == '-' else q
        if node.op == 'not':
            return _Q(np.logical_not(self.boolval(q)))
        if node.op == '-':
            return self.negate(q)
        return q
    def _binary( self, node ):
        a, b = self(node.left), self(node.right)
        res = ( self.vbinop(node.op,a,b) if isinstance(a,_V) or isinstance(b,_V)
                else self.binop(node.op,a,b) )
        return self.finite(res,f'{_op_what.get(node.op,"An operation")} gives')
    def _in( self, node ):
        #(equal to any of the values):
        left, res = self.scalar(self(node.value),'compared'), False
        for c in node.values:
            a, b, _ = self.same(left,self(c),'comparison with "in"')
            res = np.logical_or(res,self.compare(np.equal,a,b))
        return _Q(np.logical_not(res) if node.negated else res)
    def _compare( self, node ):
        left, res = self.scalar(self(node.first),'compared'), True
        for op, c in zip(node.ops,node.values):
            right = self.scalar(self(c),'compared')
            a, b, _ = self.same(left,right,'comparison')
            res = np.logical_and(res,self.compare(_compare_fcts[op],a,b))
            left = right
        return _Q(res)
    def _call( self, node ):
        return self.finite(self.call(node.name,[ self(a) for a in node.args ]),
                           f'{node.name}(..) gives')
    def binop( self, op, a, b ):
        if op in ( '&', '|' ):
            return self.bitwise(op,a,b)
        what = _op_what[op]
        if op == '//':
            if not ( _is_int(a.v) and _is_int(b.v) ):
                self.error('The operator // can only be used with integers (/ divides'
                           ' as floating point numbers)')
            return self.int_arith(op,a,b,what)
        if ( op in ( '+', '-', '*' ) and np.asarray(a.v).dtype.kind in 'iub'
             and np.asarray(b.v).dtype.kind in 'iub' ):
            return self.int_arith(op,a,b,what)
        #(otherwise integers are used as doubles, like in C, and / always
        #divides as floating point numbers):
        a, b = self.as_float(a), self.as_float(b)
        with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
            if op in ( '+', '-' ):
                x, y, d = self.same(a,b,'arithmetic')
                return _Q(np.add(x,y) if op == '+' else np.subtract(x,y),d)
            if op == '*':
                return _Q(a.v * b.v,self.muldim(a.d,b.d,1))
            if op == '/':
                return _Q(np.true_divide(a.v,b.v),self.muldim(a.d,b.d,-1))
            #Power:
            if b.d not in ( None, _dim_unknown ):
                self.error(f'Exponent with units ({_dimstr(b.d)})')
            if a.d in ( None, _dim_unknown ):
                return _Q(np.power(a.v,b.v),a.d)
            e = np.asarray(b.v)
            if e.ndim:
                self.error('Values with units can only be raised to constant powers')
            e = float(e)
            return _Q(np.power(a.v,e),self.dimpow(a.d,e,'Raising to a power'))
    @staticmethod
    def as_float( q ):
        v = np.asarray(q.v)
        return _Q(v.astype(np.float64),q.d,zero=q.zero) if v.dtype.kind in 'iub' else q
    @staticmethod
    def muldim( da, db, sign ):
        """Dimension of products (sign=1) and quotients (sign=-1)"""
        if _dim_unknown in ( da, db ):
            return _dim_unknown
        da, db = da or _dim_none, db or _dim_none
        return tuple( i + sign * j for i,j in zip(da,db) )
    def masked( self, bad ):
        """The values of bad for the particles in use"""
        return bad if self.active is None else ( bad & self.active )
    def int_operands( self, values, what ):
        """The type of the result of integers (like in C) and the values in
        that type, which must not be negative for unsigned types"""
        values = [ np.asarray(v) for v in values ]
        rt = _common_ctype(*( v.dtype for v in values ))
        if rt.kind == 'u':
            for v in values:
                if v.dtype.kind != 'u' and np.any(self.masked( v < 0 )):
                    self.error(f'Unsigned integers (like userflags) can not be'
                               f' combined with negative values (in {what.lower()})')
        with np.errstate(invalid='ignore'):
            return rt, [ v.astype(rt,copy=False) for v in values ]
    def int_overflow( self, bad, rt, what ):
        if np.any(self.masked(bad)):
            desc = ( f'{"unsigned " if rt.kind == "u" else ""}'
                     f'{8*rt.itemsize}-bit integers' )
            self.error(f'{what} of integers gives values outside the range of'
                       f' the result ({desc})')
    def int_arith( self, op, a, b, what ):
        """+, -, *, and // of integers, like in C, but with errors instead of
        wrapping around (// only divides non-negative integers, where Python
        and C agree)"""
        if op in ( '+', '-' ):
            _, _, d = self.same(a,b,'arithmetic')
        else:
            d = self.muldim(a.d,b.d,1 if op == '*' else -1)
        rt, ( x, y ) = self.int_operands((a.v,b.v),what)
        info = np.iinfo(rt)
        if op == '//':
            if np.any(self.masked( ( x < 0 ) | ( y < 0 ) )):
                self.error('The operator // can not be used with negative values')
            zero = y == 0
            if np.any(self.masked(zero)):
                self.error('Division by zero (of integers)')
            y = np.where(zero,np.ones_like(y),y)
        if rt.itemsize == 4:
            #(computed in 64 bits, where the results of 32-bit integers fit):
            wide = np.uint64 if rt.kind == 'u' else np.int64
            x, y = x.astype(wide), y.astype(wide)
            if op == '-' and rt.kind == 'u':
                x, y = x.astype(np.int64), y.astype(np.int64)
            v = self._int_op(op,x,y)
            self.int_overflow( ( v < info.min ) | ( v > info.max ),rt,what)
            return _Q(v.astype(rt),d)
        with np.errstate(over='ignore'):
            v = self._int_op(op,x,y)
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
        self.int_overflow(bad,rt,what)
        return _Q(v,d)
    @staticmethod
    def _int_op( op, x, y ):
        if op == '+':
            return x + y
        if op == '-':
            return x - y
        if op == '*':
            return x * y
        #Integer division (of non-negative integers, see int_arith):
        return np.floor_divide(x,y)
    def negate( self, q ):
        """-q (of integers like in C, but with errors instead of wrapping around)"""
        if np.asarray(q.v).dtype.kind not in 'iub':
            return _Q(-q.v,q.d,zero=q.zero)
        #(conditions are 32-bit integers, as in C, so -(x > 0cm) is -1 or 0):
        return _Q(self.int_negate(q.v,'Negation'),q.d,zero=q.zero)
    def int_negate( self, v, what ):
        rt, ( v, ) = self.int_operands((v,),what)
        if rt.kind == 'u':
            if np.any(self.masked( v != 0 )):
                self.error(f'{what} of unsigned integers (like userflags) gives'
                           ' negative values, which they can not have')
            return v
        self.int_overflow( v == np.iinfo(rt).min,rt,what)
        return -v
    def compare( self, fct, a, b ):
        """Comparisons, of integers like in C, but where unsigned integers can
        not be compared with negative values"""
        if np.asarray(a).dtype.kind in 'iub' and np.asarray(b).dtype.kind in 'iub':
            _, ( a, b ) = self.int_operands((a,b),'a comparison')
        return fct(a,b)
    def bitwise( self, op, a, b ):
        """& and | of integers, like in C"""
        for q in (a,b):
            if not _is_int(q.v):
                self.error(f'The bitwise operator {op} can only be used with integers'
                           ' (use "and" and "or" for logical and/or)')
        _, ( x, y ) = self.int_operands((a.v,b.v),f'the operation {op}')
        return _Q(np.bitwise_and(x,y) if op == '&' else np.bitwise_or(x,y))
    def dimpow( self, d, e, what ):
        """The dimension d to the power e, which must give whole or half powers
        of the units (as in sqrt(ekin))"""
        if d is None or d == _dim_unknown:
            return d
        res = []
        for i in d:
            p = i * e
            if 2 * p != round(2 * p):
                self.error(f'{what} gives units with powers which are not whole or'
                           f' half numbers ({_dimstr(d)} to the power {e:g})')
            res.append( int(p) if float(p).is_integer() else float(p) )
        return tuple(res)
    def call( self, fname, args ):
        if fname == 'through_sphere':
            return self.through_sphere(args)
        if fname in _functions_vector or ( fname == 'abs' and len(args) == 1
                                           and isinstance(args[0],_V) ):
            with np.errstate(divide='ignore',invalid='ignore'):
                return self.vcall(fname,args)
        for q in args:
            self.scalar(q,f'used in {fname}(..)')
        if fname in ('mod','abs','round','floor','ceil','min','max','clamp') and all(
                np.asarray(q.v).dtype.kind in 'iub' for q in args ):
            return self.int_call(fname,args,f'{fname}(..)')
        fct = _np_functions.get(fname)
        #(otherwise integers are used as doubles, like in C):
        args = [ self.as_float(q) for q in args ]
        with np.errstate(divide='ignore',invalid='ignore'):
            if fname in _functions_nodim:
                if len(args) != 1:
                    self.error(f'{fname}(..) takes one argument')
                return _Q(fct(self.nodim(args[0],f'{fname}(..)')))
            if fname in _functions_toint:
                if len(args) != 1:
                    self.error(f'{fname}(..) takes one argument')
                v = np.asarray(fct(self.nodim(args[0],f'{fname}(..)')))
                big = ~( np.abs(v) < 2.0**62 )
                if self._any_active(big):
                    self.error(f'{fname}(..) of values too large for integers')
                return _Q(np.where(big,0,v).astype(np.int64))
            if fname == 'sqrt':
                if len(args) != 1:
                    self.error('sqrt(..) takes one argument')
                q = args[0]
                if q.d is None:
                    return _Q(np.sqrt(q.v))
                return _Q(np.sqrt(q.v),self.dimpow(q.d,0.5,'sqrt(..)'))
            if fname == 'atan2':
                if len(args) != 2:
                    self.error('atan2(..) takes two arguments')
                y, x, _ = self.same(args[0],args[1],'atan2(..)')
                return _Q(np.arctan2(y,x))
            if fname == 'mod':
                self.error('mod(a,b) requires integers without units'
                           ' (like userflags or pdgcode)')
            #Functions keeping units:
            if fname == 'hypot':
                if len(args) < 2:
                    self.error('hypot(..) takes two or more arguments')
                values, d = self.common(args,'hypot(..)')
                return _Q(np.sqrt(sum( np.square(v) for v in values )),d)
            if len(args) == 1 and fname == 'abs':
                return _Q(fct(args[0].v),args[0].d)
            if fname == 'clamp':
                if len(args) != 3:
                    self.error('clamp(value,low,high) takes three arguments')
                ( v, lo, hi ), d = self.common(args,'clamp(..)')
                return _Q(np.minimum(np.maximum(v,lo),hi),d)
            if len(args) < 2 or fname not in ('min','max'):
                self.error(f'Wrong number of arguments for {fname}(..)')
            values, d = self.common(args,f'{fname}(..)')
            res = values[0]
            for y in values[1:]:
                res = fct(res,y)
            return _Q(res,d)
    def scalar( self, q, what ):
        """q, if it is not a vector"""
        if isinstance(q,_V):
            self.error(f'A vector can not be {what} (here {q.describe()}; abs(v) is its'
                       ' length, and v.x or v.at(0) its first value)')
        return q
    def vector( self, values ):
        """The vector of the values (two or three, with the same units)"""
        for q in values:
            self.scalar(q,'a value of a vector')
        for q in values[1:]:
            self.same(values[0],q,'a vector')
        return _V(values)
    def vbinop( self, op, a, b ):
        """Arithmetic with vectors: sums and differences of vectors (of the
        same size and units), vectors multiplied or divided by numbers, and v^2
        (the length squared)"""
        va, vb = isinstance(a,_V), isinstance(b,_V)
        if op in ( '+', '-' ):
            if not ( va and vb ) or len(a.c) != len(b.c):
                self.error('Vectors can only be added to or subtracted from vectors of'
                           ' the same size (not '
                           f'{a.describe() if va else "a number"} and'
                           f' {b.describe() if vb else "a number"})')
            return _V( self.binop(op,x,y) for x, y in zip(a.c,b.c) )
        if op == '*' and not ( va and vb ):
            return ( _V( self.binop(op,x,b) for x in a.c ) if va
                     else _V( self.binop(op,a,y) for y in b.c ) )
        if op == '/' and va and not vb:
            return _V( self.binop(op,x,b) for x in a.c )
        if op == '^' and va and not vb and np.ndim(b.v) == 0 and b.v == 2:
            return self.call('dot',[a,a])
        self.error('Vectors can be added and subtracted, multiplied and divided by numbers,'
                   ' and v^2 gives their lengths squared (dot(v,w) and cross(v,w) give'
                   ' their dot and cross products)')
    def vcall( self, fname, args ):
        """The functions of vectors: dot, cross, angle, and abs (the length)"""
        if fname == 'abs':
            v = args[0]
            return _Q(np.sqrt(sum( np.square(c.v) for c in v.c )),v.d)
        if len(args) != 2 or not all( isinstance(q,_V) for q in args ):
            self.error(f'{fname}(v,w) takes two vectors')
        v, w = args
        if len(v.c) != len(w.c) or ( fname == 'cross' and len(v.c) != 3 ):
            self.error(f'{fname}(v,w) takes two vectors of the same size'
                       + ( ' (3D)' if fname == 'cross' else '' ))
        if fname == 'angle':
            #(precise also for small angles, and of 2D vectors as in 3D):
            pad = [ 0.0 ] * ( 3 - len(v.c) )
            return _Q(_angle_highres([ c.v for c in v.c ] + pad,[ c.v for c in w.c ] + pad))
        mult = lambda x, y : self.binop('*',x,y)
        if fname == 'dot':
            res = mult(v.c[0],w.c[0])
            for x, y in zip(v.c[1:],w.c[1:]):
                res = self.binop('+',res,mult(x,y))
            return res
        sub = lambda i, j : self.binop('-',mult(v.c[i],w.c[j]),mult(v.c[j],w.c[i]))
        return _V([ sub(1,2), sub(2,0), sub(0,1) ])
    def through_sphere( self, args ):
        """Whether the line of flight of the particles (through their
        positions, along their directions, in both directions) passes through
        the sphere with the center and radius"""
        what = ( 'through_sphere(center,radius) takes the center (a 3D vector) and the'
                 ' radius of the sphere, as in through_sphere((0,0,1m),5cm)' )
        if ( len(args) != 2 or not isinstance(args[0],_V) or len(args[0].c) != 3
             or isinstance(args[1],_V) ):
            self.error(what)
        center, radius = args
        x = self.name('x')
        for q in ( *center.c, radius ):
            self.same(q,x,'the center and radius of through_sphere(center,radius), which'
                      ' must be lengths')
        if np.any(self.masked( np.asarray(radius.v) < 0 )):
            self.error('The radius of through_sphere(center,radius) can not be negative')
        #(the distance of the center from the line is the length of the cross
        #product of the direction, a unit vector, and the vector to the center):
        to_center = _V( self.binop('-',c,p) for c, p in zip(center.c,self.name('pos').c) )
        d = self.vcall('cross',[to_center,self.name('dir')])
        return _Q(np.less_equal(self.vcall('dot',[d,d]).v,np.square(self.as_float(radius).v)))
    def int_call( self, fname, args, what ):
        """mod, abs, round, floor, ceil, min, max, and clamp of integers"""
        if fname == 'mod':
            if len(args) != 2:
                self.error('mod(a,b) takes two arguments')
            if any( q.d not in ( None, _dim_unknown ) for q in args ):
                self.error('mod(a,b) requires integers without units'
                           ' (like userflags or pdgcode)')
            _, ( a, b ) = self.int_operands((args[0].v,args[1].v),what)
            if np.any(self.masked( ( a < 0 ) | ( b < 0 ) )):
                self.error('mod(a,b) can not be used with negative values')
            zero = b == 0
            if np.any(self.masked(zero)):
                self.error('Division by zero in mod(a,b)')
            return _Q(np.mod(a,np.where(zero,np.ones_like(b),b)))
        if fname in ('abs','round','floor','ceil'):
            if len(args) != 1:
                self.error(f'{what} takes one argument')
            q = args[0]
            if fname != 'abs':
                self.nodim(q,what)
            rt, ( v, ) = self.int_operands((q.v,),what)
            if fname == 'abs' and rt.kind == 'i':
                neg = v < 0
                v = np.where(neg,self.int_negate(np.where(neg,v,0),what),v)
            return _Q(v,q.d,zero=q.zero)
        if fname == 'clamp' and len(args) != 3:
            self.error('clamp(value,low,high) takes three arguments')
        if fname != 'clamp' and len(args) < 2:
            self.error(f'Wrong number of arguments for {what}')
        d = args[0].d
        for q in args[1:]:
            _, _, d2 = self.same(args[0],q,what)
            d = d or d2
        _, vals = self.int_operands([ q.v for q in args ],what)
        if fname == 'clamp':
            return _Q(np.minimum(np.maximum(vals[0],vals[1]),vals[2]),d)
        fct = np.minimum if fname == 'min' else np.maximum
        res = vals[0]
        for v in vals[1:]:
            res = fct(res,v)
        return _Q(res,d)
    def boolval( self, q ):
        q = self.scalar(q,'a condition')
        return np.asarray(q.v).astype(bool) if np.asarray(q.v).dtype != bool else q.v

#(the methods of _ExprEvaluator evaluating the nodes):
_dispatch = { Value : _ExprEvaluator._value, Int : _ExprEvaluator._int,
              Float : _ExprEvaluator._float, Quantity : _ExprEvaluator._quantity,
              Unit : _ExprEvaluator._unit, Name : _ExprEvaluator._name,
              Particle : _ExprEvaluator._particle, Userdata : _ExprEvaluator.userdata,
              Vector : _ExprEvaluator._vector, Part : _ExprEvaluator._part,
              Logical : _ExprEvaluator._logical, Unary : _ExprEvaluator._unary,
              Binary : _ExprEvaluator._binary, In : _ExprEvaluator._in,
              Compare : _ExprEvaluator._compare, Call : _ExprEvaluator._call }

class _EmptyBlock:
    """Block without particles, for checking expressions before use"""
    def __len__( self ):
        return 0
    def __getattr__( self, name ):
        dtypes = { 'pdgcode' : np.int32, 'userflags' : np.uint32,
                   'fileidx' : np.int64 }
        return np.zeros(0,dtype = dtypes.get(name,float))

#The statements of edit expressions:

def _run_statements( ev, statements, text, modified, counts = None ):
    """Run the checked statements (see _expr_astcheck) of an edit expression,
    with the evaluator ev (of a block), which gets the values of the variables
    and of the changed fields in its state, adding the names of the changed
    fields to the set modified (text is the expression, for messages). The
    conditions remove the particles for which they are false (see
    _ExprEvaluator.keep). counts (if given) gets the number of particles left
    after each statement added."""
    for i, st in enumerate(statements):
        state = ev.state
        if _is_condition(st):
            keep = np.broadcast_to(_condition(ev,st,text),(len(ev._block),))
            if not keep.all():
                ev.keep(keep)
        elif isinstance(st,Assign):
            name = st.target
            value = st.value if st.op is None else Binary(st.op,Name(name),st.value)
            q = ev(value)
            if name in _expr_vectors:
                comps = _expr_vectors[name]
                d = _expr_field_dims.get(comps[0])
                if not ( isinstance(q,_V) and len(q.c) == 3
                         and ( q.d in ( d, _dim_unknown ) or all( c.zero for c in q.c ) ) ):
                    what = q.describe() if isinstance(q,_V) else 'a number'
                    dname = f' of {_dimstr(d)}s' if d else ' without units'
                    raise MCPLError(f'Can not assign {what} to {name}, which is a'
                                    f' 3D vector{dname}, in expression "{text}"')
                for c, qc in zip(comps,q.c):
                    _assign_field(ev,c,qc,text,modified)
            elif name in _assignable:
                _assign_field(ev,name,ev.scalar(q,f'assigned to {name}'),text,modified)
            else:
                state[name] = q
        elif st.name == 'swap':
            a, b = ( n.id for n in st.args )
            qa, qb = ( ev.scalar(ev.name(c),'swapped') for c in (a,b) )
            ev.same(qa,qb,'swap(..)')
            state[a], state[b] = qb, qa
            modified.update( e for e in (a,b) if e in _assignable )
        elif st.name in _rotation_matrix_args:
            _rotate_by_matrix(ev,st,modified)
        else:
            _rotate(ev,st,modified)
        if counts is not None:
            counts[i] += len(ev._block)

class _Kept:
    """The particles at the positions idx of a block (of any kind, see
    _ExprEvaluator)"""
    def __init__( self, block, idx ):
        self._block, self._idx = block, idx
    def __len__( self ):
        return len(self._idx)
    def __getattr__( self, name ):
        v = getattr(self._block,name)
        return v if name == '_udinfo' else _kept_value(v,self._idx,len(self._block))

def _kept_value( v, idx, n ):
    """The values (an array, a _Q, or a _V) of the particles at the positions
    idx, of n particles (values which are the same for all are kept)"""
    if isinstance(v,_V):
        return _V( _kept_value(c,idx,n) for c in v.c )
    if isinstance(v,_Q):
        return _Q(_kept_value(v.v,idx,n),v.d,v.zero)
    if v is None or np.ndim(v) == 0 or len(v) != n:
        return v
    return v[idx]

def _condition( ev, node, text ):
    """The values of a condition (true for integers which are not 0)"""
    v = np.asarray(ev.scalar(ev(node),'a condition').v)
    if v.dtype.kind in 'iu':
        v = v != 0#like in C, e.g. for "userflags & 0x10"
    if v.dtype != bool:
        raise MCPLError(f'"{_expr_ast2str(node)}" is neither a condition (e.g. a comparison)'
                        f' nor a change of the particles (e.g. x = 2*y), in "{text}"')
    return v

def _rotate( ev, call, modified ):
    """rotate_x(angle), rotate_y(angle), or rotate_z(angle)"""
    fname = call.name
    qa = ev.scalar(ev(call.args[0]),f'an angle in {fname}(..)')
    if qa.d not in ( None, _dim_unknown ):
        ev.error(f'{fname}(..) requires an angle (e.g. 90deg), not {_dimstr(qa.d)}')
    #Rotations by multiples of 90 degrees are exact, with cos and sin
    #exactly 0 and +-1 (e.g. rotate_z(90deg) gives exactly (x,y) ->
    #(-y,x), as the values are finite). Adding 0.0 to the results
    #avoids negative zeros (-0.0 + 0.0 is 0.0):
    c, s = _exact_cos_sin(qa.v)
    for a, b in _rotation_planes[fname]:
        va, vb = ev.name(a), ev.name(b)
        ra, rb = c * va.v - s * vb.v, s * va.v + c * vb.v
        ev.state[a] = _Q(ra + 0.0, va.d)
        ev.state[b] = _Q(rb + 0.0, vb.d)
        modified.update((a,b))

def _assign_field( ev, name, q, text, modified ):
    """Assign the value q to the field"""
    d = _expr_field_dims.get(name)
    if q.d not in ( d, _dim_unknown ) and not q.zero:
        what = _dimstr(q.d) if q.d is None else f'value with {_dimstr(q.d)}'
        dname = 'unitless' if d is None else f'a {_dimstr(d)}'
        dname = dname.replace('a energy','an energy')
        hint = _unit_hint(d) if q.d is None else ''
        raise MCPLError(f'Can not assign {what} to {name}, which is'
                        f' {dname}{hint}, in expression "{text}"')
    v = np.broadcast_to(np.asarray(q.v,dtype=( float if name not in
                                               ('pdgcode','userflags')
                                               else None )),(len(ev._block),))
    if name == 'wavelength':
        _set_wavelength(ev,v,text,modified)
        return
    if name in ('pdgcode','userflags'):
        v = _int_field_values(name,v,text)
    ev.state[name] = _Q(v,d)
    modified.add(name)

def _int_field_values( name, v, text ):
    """Values for pdgcode or userflags, which must be integers in the range
    of their types (int32 and uint32)"""
    v = np.asarray(v)
    if v.dtype.kind not in 'iub' and not np.all( np.round(v) == v ):
        raise MCPLError(f'Non-integer values assigned to {name} in'
                        f' expression "{text}"')
    info = np.iinfo(np.int32 if name == 'pdgcode' else np.uint32)
    if np.any( ( v < info.min ) | ( v > info.max ) ):
        raise MCPLError(f'Values assigned to {name} must be integers from'
                        f' {info.min} to {info.max}, in expression "{text}"')
    return v.astype(info.dtype)

def _rotate_by_matrix( ev, call, modified ):
    """Rotate the positions, directions, and polarisations with the matrix
    of rotate_around or rotate_frame (see _rotation_matrix)"""
    fname = call.name
    qs = [ ev(a) for a in call.args ]
    #(3D vectors, and the angle of rotate_around):
    values = []
    for i, q in enumerate(qs):
        if fname == 'rotate_around' and i == 1:
            q = ev.scalar(q,f'the angle in {fname}(..)')
            if q.d not in ( None, _dim_unknown ):
                ev.error(f'{fname}(..) requires an angle (e.g. 90deg) as its last'
                         f' argument, not {_dimstr(q.d)}')
            values.append(q.v)
        elif not ( isinstance(q,_V) and len(q.c) == 3 ):
            what = ( 'a 3D vector (the axis) and an angle, as in rotate_around((0,0,1),90deg)'
                     if fname == 'rotate_around' else 'four 3D vectors, as in'
                     ' rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))' )
            ev.error(f'{fname}(..) takes {what}')
        else:
            values += [ c.v for c in q.c ]
    R = _rotation_matrix(fname,values)
    if isinstance(R,str):
        ev.error(f'In {fname}(..), {R}')
    state, n = ev.state, len(ev._block)
    for names in _rotated_vectors:
        qv = [ ev.name(c) for c in names ]
        V = np.stack([ np.broadcast_to(np.asarray(q.v,dtype=float),(n,)) for q in qv ],
                     axis=-1)
        res = np.einsum('...ij,...j->...i',R,V) + 0.0#(no negative zeros)
        for i, c in enumerate(names):
            state[c] = _Q(res[:,i],qv[i].d)
            modified.add(c)

def _set_wavelength( ev, wl, text, modified ):
    """Set kinetic energy from wavelength (given in cm)"""
    pdg = np.asarray(ev.name('pdgcode').v)
    if not np.all( np.isin( pdg, _wavelength_pdgcodes ) ):
        raise MCPLError('wavelength can only be assigned to neutrons'
                        ' (pdgcode 2112) and gammas (pdgcode 22)'
                        f' in expression "{text}"')
    if np.any( np.asarray(wl) <= 0.0 ):
        raise MCPLError('wavelength must be assigned positive values'
                        f' in expression "{text}"')
    ev.state['ekin'] = _Q(np.broadcast_to(ekin_from_wavelength(wl/_expr_wl_unit,pdg),
                                          wl.shape),_dim_E)
    modified.add('ekin')
