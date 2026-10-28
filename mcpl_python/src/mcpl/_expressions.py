
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

"""Particle expressions (picks and edits), which are evaluated with numpy
on blocks of particles."""

__all__ = [ 'ParticleEdit', 'ParticleFilter', 'ParticleValue' ]

import ast
import math
import re

from ._common import MCPLError
from ._numpy import np
from ._physics import _particle_names, ekin_from_wavelength, wavelength_from_ekin

_expr_fields = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz',
                 'ekin', 'time', 'weight', 'pdgcode', 'userflags',
                 'wavelength', 'fileidx' )
_expr_constants = { 'pi' : math.pi, **_particle_names }
#Dimensions (length,energy,time,temperature) and units of quantities in
#expressions. Values are internally in the units of MCPL (cm, MeV, ms), also
#for wavelengths, and temperatures (of userdata fields) in K:
_dim_none = (0,0,0,0)
_dim_L, _dim_E, _dim_T, _dim_K = (1,0,0,0), (0,1,0,0), (0,0,1,0), (0,0,0,1)
#(the dimension of userdata fields when expressions are checked without a
#file, since their units are given by the layouts of files: everything
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
_expr_field_dims = { 'x' : _dim_L, 'y' : _dim_L, 'z' : _dim_L,
                     'ekin' : _dim_E, 'time' : _dim_T,
                     'wavelength' : _dim_L }
_expr_wl_unit = 1e-8#wavelengths are in Aa in the Python API
#Example units to suggest in error messages:
_expr_unit_hints = { _dim_L : 'cm', _dim_E : 'MeV', _dim_T : 'ms', _dim_K : 'K' }
#Functions requiring dimensionless arguments:
_expr_functions_nodim = { 'exp' : np.exp, 'log' : np.log, 'log10' : np.log10,
                          'sin' : np.sin, 'cos' : np.cos, 'tan' : np.tan,
                          'asin' : np.arcsin, 'acos' : np.arccos,
                          'atan' : np.arctan }
#Functions keeping the units of the argument(s):
_expr_functions_samedim = { 'abs' : np.abs, 'floor' : np.floor,
                            'ceil' : np.ceil, 'min' : np.minimum,
                            'max' : np.maximum, 'hypot' : np.hypot,
                            'clamp' : np.clip }
#Functions used as statements in edits:
_edit_statements = ( 'swap', 'rotate_x', 'rotate_y', 'rotate_z' )
#Components of position, direction and polarisation changed by rotations:
_rotation_planes = { 'rotate_x' : ( ('y','z'), ('uy','uz'), ('poly','polz') ),
                     'rotate_y' : ( ('z','x'), ('uz','ux'), ('polz','polx') ),
                     'rotate_z' : ( ('x','y'), ('ux','uy'), ('polx','poly') ) }
_expr_functions = dict( sqrt = np.sqrt, atan2 = np.arctan2, angle_to = None,
                        mod = np.mod,
                        **_expr_functions_nodim, **_expr_functions_samedim )

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

#Characters which can not be used in expressions (nor in the histogram strings
#of mcpltool -H), although they are printable ASCII characters:
_forbidden_chars = '"\'{}[]#$`\\'

def _check_chars( text, what = 'expression' ):
    """Check that the text only has printable ASCII characters (and ASCII
    whitespace, including newlines), and none of the forbidden characters."""
    for c in text:
        if c in _forbidden_chars:
            raise MCPLError(f'The character {c} can not be used in {what}s'
                            f' (in "{_ascii_repr(text)}")')
        if not ( ' ' <= c <= '~' or c in '\t\n\r\f\v' ):
            raise MCPLError(f'Only printable ASCII characters can be used in'
                            f' {what}s (not U+{ord(c):04X}, in'
                            f' "{_ascii_repr(text)}")')

def _ascii_repr( text ):
    return text.encode('ascii','backslashreplace').decode('ascii')

def _expr_normalise( expr ):
    """Expression with all whitespace (including newlines, e.g. in long
    expressions written over several lines) normalised to single spaces."""
    if not isinstance(expr,str):
        raise MCPLError(f'Expressions must be strings (got {type(expr).__name__})')
    _check_chars(expr)
    return ' '.join(expr.split())

#C-style operators, which give errors saying what to use instead:
_expr_unsupported_ops = ( ( '&&', 'and', 'x > 0 and y > 0' ),
                          ( '||', 'or', 'x > 0 or y > 0' ),
                          ( '!', 'not', 'not (x > 0)' ),
                          ( '%', 'mod(a,b)', 'mod(userflags,4) == 1' ) )

def _expr_check_ops( expr ):
    #NB: Do not add support for these: ! and % break command lines in some
    #shells (bash history expansion, Windows batch files).
    if '~' in expr:
        raise MCPLError('The operator ~ is not supported in expressions (e.g.'
                        ' "(userflags & 0x10) == 0" tests that a bit is not set),'
                        f' in expression "{expr}"')
    for op, alt, example in _expr_unsupported_ops:
        found = ( re.search(r'!(?!=)',expr) if op == '!' else op in expr )
        if found:
            raise MCPLError(f'Use "{alt}" instead of "{op}" in expressions (e.g.'
                            f' "{example}"), in expression "{expr}"')

def _expr_preprocess( expr ):
    """Translate ^ to ** (powers), and numbers with units (e.g. 25meV) to
    multiplications."""
    _expr_check_ops(expr)
    e = expr.replace('^','**')
    units = '|'.join(sorted(_expr_units,key=len,reverse=True))
    #(a power directly after a unit only applies to the unit, e.g. 4cm^2):
    e = re.sub(r'(?<![\w.])((?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(' + units
               + r')\b(\s*\*\*\s*\d+)?',
               lambda m : f'({m.group(1)}*{m.group(2)}{m.group(3) or ""})', e)
    return e

def _expr_check( node, expr, variables = () ):
    """Check that only supported constructs are used in parsed expression
    (variables are names of variables defined in edits)"""
    ok_nodes = ( ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp,
                 ast.Not, ast.USub, ast.UAdd, ast.BinOp, ast.Add,
                 ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow,
                 ast.BitAnd, ast.BitOr, ast.Compare, ast.Eq, ast.NotEq,
                 ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Name, ast.Load,
                 ast.Constant, ast.Call )
    #TODO: Consider supporting conditional expressions ("a if cond else b",
    #e.g. evaluated with _ExprEvaluator._with_active for each branch, like the
    #right side of and/or), which were removed since nothing used them.
    for n in ast.walk(node):
        if not isinstance( n, ok_nodes ):
            raise MCPLError(f'Unsupported syntax in expression "{expr}"')
        if isinstance(n,ast.Constant) and not isinstance(n.value,(int,float)):
            raise MCPLError(f'Unsupported value in expression "{expr}"')
        if isinstance(n,ast.Call) and ( n.keywords or not (
                isinstance(n.func,ast.Name) and n.func.id in _expr_functions ) ):
            raise MCPLError(f'Unsupported function call in expression "{expr}"'
                            ' (available functions are: '
                            + ', '.join(sorted(_expr_functions)) + ')')
        if isinstance(n,ast.Name) and not ( n.id in _expr_fields
                                            or n.id.startswith('userdata.')
                                            or n.id in variables
                                            or n.id in _expr_constants
                                            or n.id in _expr_units
                                            or n.id in _expr_functions ):
            raise MCPLError(f'Unknown name "{n.id}" in expression "{expr}"'
                            ' (particle fields are: '
                            + ', '.join(_expr_fields) + ')')

def _expr_parse( expr, mode = 'eval' ):
    try:
        tree = ast.parse( _expr_preprocess(expr).strip(), mode = mode )
    except SyntaxError:
        hint = ' (use == for comparisons)' if mode == 'eval' and '=' in expr else ''
        raise MCPLError(f'Syntax error in expression "{expr}"{hint}')
    return _UserdataNames(expr).visit(tree)

class _UserdataNames(ast.NodeTransformer):
    """Replaces fields of the userdata, userdata.NAME and
    userdata.NAME.at(INDEX) (for values of arrays), by single names (like
    "userdata.NAME.at(2)")."""
    def __init__( self, expr ):
        self._expr = expr
    def _error( self, msg ):
        raise MCPLError(f'{msg} in expression "{self._expr}"')
    @staticmethod
    def _field( node ):
        """The NAME of userdata.NAME, or None"""
        if ( isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name)
             and node.value.id == 'userdata' ):
            return node.attr
        return None
    def visit_Call( self, node ):
        f = node.func
        field = self._field(f.value) if isinstance(f,ast.Attribute) else None
        if field is None:
            return self.generic_visit(node)
        if f.attr != 'at':
            self._error(f'Unknown function userdata.{field}.{f.attr}(..) (values of'
                        f' arrays in the userdata are written as userdata.{field}.at(INDEX))')
        a = node.args[0] if len(node.args) == 1 and not node.keywords else None
        if not ( isinstance(a,ast.Constant) and type(a.value) is int ):
            self._error(f'The index in userdata.{field}.at(INDEX) must be a'
                        f' non-negative integer, like userdata.{field}.at(0)')
        return ast.copy_location(ast.Name( id = f'userdata.{field}.at({a.value})',
                                           ctx = node.func.ctx ), node)
    def visit_Attribute( self, node ):
        field = self._field(node)
        if field is not None:
            return ast.copy_location(ast.Name( id = f'userdata.{field}',
                                               ctx = node.ctx ), node)
        inner = node.value
        if isinstance(inner,ast.Attribute) and self._field(inner) is not None:
            self._error(f'Values of arrays in the userdata are written as'
                        f' userdata.{inner.attr}.at(INDEX), not'
                        f' userdata.{inner.attr}.{node.attr}')
        return self.generic_visit(node)
    def visit_Name( self, node ):
        if node.id == 'userdata':
            self._error('Fields of the userdata are written as userdata.NAME')
        return node

class _Q:
    """Value with dimension (length,energy,time,temperature) in an expression.
    Values without units (like plain numbers, or ux) have dimension None. A
    plain 0 (zero is the same in all units) is marked with zero=True, and can
    be used with any units. Integers are numpy arrays with the integer types of
    C after its integer promotions (int32, uint32, int64 or uint64)."""
    __slots__ = ('d','v','zero')
    def __init__( self, v, d = None, zero = False ):
        self.v, self.d = v, ( None if d == _dim_none else d )
        self.zero = zero

#Integers in expressions work like in C (with its integer promotions and usual
#arithmetic conversions), but results which do not fit their type are errors
#instead of wrapping around, and so are unsigned values combined with negative
#values (e.g. in comparisons, which are therefore exact):
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

class _ExprEvaluator:
    """Evaluates parsed expression on a block of particles with numpy"""
    def __init__( self, block, expr, state = None ):
        self._block = block
        self._expr = expr
        self._cache = {}
        #Values of variables and modified fields (in edits):
        self.state = state if state is not None else {}
        #Particles for which the current part of the expression is used (None
        #for all), e.g. only those for which the left side of and is true:
        self.active = None
    def error( self, msg ):
        raise MCPLError(f'{msg} in expression "{self._expr}"')
    def name( self, n ):
        if n == 'wavelength':
            self._check_wavelength()
            q = self._wavelength()
            v = np.asarray(q.v)
            bad = ~np.isfinite(v)
            if self.active is not None:
                bad = bad & self.active
            if np.any(bad):
                self.error('The wavelength is infinite for particles with zero'
                           ' kinetic energy')
            return q
        if n in self.state:
            return self.state[n]
        if n in _expr_constants:
            v = _expr_constants[n]
            return _Q(_int_constant(v) if isinstance(v,int) else v)
        if n in _expr_units:
            v, d = _expr_units[n]
            return _Q(v,d)
        if n not in self._cache:
            if n.startswith('userdata.'):
                field, _, index = n[9:].partition('.at(')
                q = self._userdata(field,int(index[:-1]) if index else None)
            else:
                q = _Q(getattr(self._block,n),_expr_field_dims.get(n))
            v = np.asarray(q.v)
            if v.dtype.kind in 'iub':
                v = v.astype(_ctype(v.dtype),copy=False)
            elif v.dtype != np.float64:
                v = v.astype(np.float64)#(e.g. float32 userdata)
            self._cache[n] = _Q(v,q.d)
        #(checked for each use, for the particles in use there):
        what = ( f'The userdata field {n[9:].partition(".at(")[0]} has'
                 if n.startswith('userdata.') else f'The particle field {n} has' )
        return self.finite(self._cache[n],what)
    def _userdata( self, field, index = None ):
        """The values of the field of the userdata (with the unit of the field
        in the layout, if any), or of the value with the index (from 0) of a
        field with an array of values"""
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
        n = v.shape[1] if v.ndim == 2 else None
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
            v = v * factor#(e.g. mm in cm, or deg in radians)
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
        v = np.asarray(q.v)
        if v.dtype.kind in 'fc':
            bad = ~np.isfinite(v)
            if self.active is not None:
                bad = bad & self.active
            if np.any(bad):
                self.error(f'{what} NaN or infinite values')
        return q
    def _check_wavelength( self ):
        pdg = np.asarray(self.name('pdgcode').v)
        bad = ~np.isin(pdg,(2112,22))
        if self.active is not None:
            bad &= self.active
        if np.any(bad):
            raise MCPLError('The wavelength is only defined for neutrons and gammas,'
                            ' so pick those before using it, e.g. "pdgcode =='
                            f' neutron and wavelength > 1.8Aa" (in expression "{self._expr}")')
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
        ev = self
        if isinstance(node,ast.Expression):
            return ev(node.body)
        if isinstance(node,ast.Constant):
            v = node.value
            if type(v) is int:
                c = _int_constant(v)
                if c is None:
                    self.error(f'The integer {v} is too large (integers must fit'
                               ' in 64 bits)')
                return _Q(c,zero=(v==0))
            return self.finite(_Q(v,zero=(v==0)),'A constant has')
        if isinstance(node,ast.Name):
            return self.name(node.id)
        if isinstance(node,ast.BoolOp):
            #The right side of and (or) is only used for particles
            #where the left side is true (false):
            is_and = isinstance(node.op,ast.And)
            fct = np.logical_and if is_and else np.logical_or
            res = self.boolval(ev(node.values[0]))
            for v in node.values[1:]:
                b = self.boolval(self._with_active(res if is_and else ~np.asarray(res,dtype=bool),v))
                res = fct(res,b)
            return _Q(res)
        if isinstance(node,ast.UnaryOp):
            c = node.operand
            if ( isinstance(node.op,ast.USub) and isinstance(c,ast.Constant)
                 and type(c.value) is int ):
                #(negative integer constants, like -2147483648):
                return ev(ast.Constant(-c.value))
            q = ev(c)
            if isinstance(node.op,ast.Not):
                return _Q(np.logical_not(self.boolval(q)))
            if isinstance(node.op,ast.USub):
                if _is_int(q.v):
                    return _Q(self.int_negate(q.v,'Negation'),q.d,zero=q.zero)
                return _Q(-q.v,q.d,zero=q.zero)
            return q
        if isinstance(node,ast.BinOp):
            what = { ast.Add : 'Addition', ast.Sub : 'Subtraction',
                     ast.Mult : 'Multiplication', ast.Div : 'Division',
                     ast.FloorDiv : 'Integer division',
                     ast.Pow : 'Raising to a power' }.get(type(node.op),'An operation')
            return self.finite(self.binop(node.op,ev(node.left),ev(node.right)),
                               f'{what} gives')
        if isinstance(node,ast.Compare):
            fcts = { ast.Eq : np.equal, ast.NotEq : np.not_equal,
                     ast.Lt : np.less, ast.LtE : np.less_equal,
                     ast.Gt : np.greater, ast.GtE : np.greater_equal }
            left, res = ev(node.left), True
            for op, c in zip(node.ops,node.comparators):
                right = ev(c)
                a, b, _ = self.same(left,right,'comparison')
                res = np.logical_and(res,self.compare(fcts[type(op)],a,b))
                left = right
            return _Q(res)
        if isinstance(node,ast.Call):
            return self.finite(self.call(node.func.id,[ev(a) for a in node.args]),
                               f'{node.func.id}(..) gives')
        raise MCPLError('Unsupported expression')#should not happen
    def binop( self, op, a, b ):
        if isinstance(op,(ast.BitAnd,ast.BitOr)):
            return self.bitwise(op,a,b)
        what = { ast.Add : 'Addition', ast.Sub : 'Subtraction',
                 ast.Mult : 'Multiplication', ast.FloorDiv : 'Integer division',
                 ast.Pow : 'Raising to a power' }.get(type(op),'Division')
        if isinstance(op,ast.FloorDiv):
            if not ( _is_int(a.v) and _is_int(b.v) ):
                self.error('The operator // can only be used with integers (/ divides'
                           ' as floating point numbers)')
            return self.int_arith(op,a,b,what)
        if ( isinstance(op,(ast.Add,ast.Sub,ast.Mult)) and np.asarray(a.v).dtype.kind in 'iub'
             and np.asarray(b.v).dtype.kind in 'iub' ):
            return self.int_arith(op,a,b,what)
        #(otherwise integers are used as doubles, like in C, and / always
        #divides as floating point numbers):
        a, b = self.as_float(a), self.as_float(b)
        with np.errstate(divide='ignore',invalid='ignore'):
            if isinstance(op,(ast.Add,ast.Sub)):
                x, y, d = self.same(a,b,'arithmetic')
                return _Q(np.add(x,y) if isinstance(op,ast.Add) else np.subtract(x,y),d)
            if isinstance(op,(ast.Mult,ast.Div)):
                if isinstance(op,ast.Mult):
                    v, sign = a.v * b.v, 1
                else:
                    v, sign = np.true_divide(a.v,b.v), -1
                return _Q(v,self.muldim(a.d,b.d,sign))
            #Power:
            if b.d not in ( None, _dim_unknown ):
                self.error(f'Exponent with units ({_dimstr(b.d)})')
            if a.d in ( None, _dim_unknown ):
                return _Q(np.power(a.v,b.v),a.d)
            e = np.asarray(b.v)
            if e.ndim or float(e) != round(float(e)):
                self.error('Values with units can only be raised to integer powers')
            e = round(float(e))
            return _Q(np.power(a.v,e),tuple( i * e for i in a.d ))
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
        """+, -, * and // of integers, like in C, but with errors instead of
        wrapping around (// only divides non-negative integers, where Python
        and C agree)"""
        if isinstance(op,(ast.Add,ast.Sub)):
            _, _, d = self.same(a,b,'arithmetic')
        else:
            d = self.muldim(a.d,b.d,1 if isinstance(op,ast.Mult) else -1)
        rt, ( x, y ) = self.int_operands((a.v,b.v),what)
        info = np.iinfo(rt)
        if isinstance(op,ast.FloorDiv):
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
            if isinstance(op,ast.Sub) and rt.kind == 'u':
                x, y = x.astype(np.int64), y.astype(np.int64)
            v = self._int_op(op,x,y)
            self.int_overflow( ( v < info.min ) | ( v > info.max ),rt,what)
            return _Q(v.astype(rt),d)
        with np.errstate(over='ignore'):
            v = self._int_op(op,x,y)
            if isinstance(op,ast.Add):
                bad = ( v < x ) if rt.kind == 'u' else ( ( ( x ^ v ) & ( y ^ v ) ) < 0 )
            elif isinstance(op,ast.Sub):
                bad = ( x < y ) if rt.kind == 'u' else ( ( ( x ^ y ) & ( x ^ v ) ) < 0 )
            elif isinstance(op,ast.Mult):
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
        if isinstance(op,ast.Add):
            return x + y
        if isinstance(op,ast.Sub):
            return x - y
        if isinstance(op,ast.Mult):
            return x * y
        #Integer division (of non-negative integers, see int_arith):
        return np.floor_divide(x,y)
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
        sym = '&' if isinstance(op,ast.BitAnd) else '|'
        for q in (a,b):
            if not _is_int(q.v):
                self.error(f'The bitwise operator {sym} can only be used with integers'
                           ' (use "and" and "or" for logical and/or)')
        _, ( x, y ) = self.int_operands((a.v,b.v),f'the operation {sym}')
        return _Q(np.bitwise_and(x,y) if sym == '&' else np.bitwise_or(x,y))
    def call( self, fname, args ):
        fct = _expr_functions[fname]
        what = f'{fname}(..)'
        if fname in ('mod','abs','floor','ceil','min','max','clamp') and all(
                np.asarray(q.v).dtype.kind in 'iub' for q in args ):
            return self.int_call(fname,args,what)
        #(otherwise integers are used as doubles, like in C):
        args = [ self.as_float(q) for q in args ]
        with np.errstate(divide='ignore',invalid='ignore'):
            if fname in _expr_functions_nodim:
                return _Q(fct(*[self.nodim(q,f'{fname}(..)') for q in args]))
            if fname == 'sqrt':
                if len(args) != 1:
                    self.error('sqrt(..) takes one argument')
                q = args[0]
                if q.d in ( None, _dim_unknown ):
                    return _Q(np.sqrt(q.v))
                if any( i % 2 for i in q.d ):
                    self.error(f'sqrt(..) of value with {_dimstr(q.d)}')
                return _Q(np.sqrt(q.v),tuple( i // 2 for i in q.d ))
            if fname == 'atan2':
                if len(args) != 2:
                    self.error('atan2(..) takes two arguments')
                y, x, _ = self.same(args[0],args[1],'atan2(..)')
                return _Q(np.arctan2(y,x))
            if fname == 'angle_to':
                #Angle between the direction of the particles and a vector:
                if len(args) != 3:
                    self.error('angle_to(x,y,z) takes three arguments')
                vx, vy, _ = self.same(args[0],args[1],'angle_to(..)')
                _, vz, _ = self.same(args[0],args[2],'angle_to(..)')
                u = tuple( self.name(c).v for c in ('ux','uy','uz') )
                return _Q(_angle_highres(u,(vx,vy,vz)))
            if fname == 'mod':
                self.error('mod(a,b) requires integers without units'
                           ' (like userflags or pdgcode)')
            #Functions keeping units:
            if fname == 'hypot':
                if len(args) < 2:
                    self.error('hypot(..) takes two or more arguments')
                d = args[0].d
                for q in args[1:]:
                    self.same(args[0],q,'hypot(..)')
                return _Q(np.sqrt(sum( np.square(q.v) for q in args )),d)
            if len(args) == 1 and fname in ('abs','floor','ceil'):
                return _Q(fct(args[0].v),args[0].d)
            if fname == 'clamp':
                if len(args) != 3:
                    self.error('clamp(value,low,high) takes three arguments')
                v, lo, d = self.same(args[0],args[1],'clamp(..)')
                _, hi, _ = self.same(args[0],args[2],'clamp(..)')
                return _Q(np.minimum(np.maximum(v,lo),hi),d)
            if len(args) < 2 or fname not in ('min','max'):
                self.error(f'Wrong number of arguments for {fname}(..)')
            res, d = args[0].v, args[0].d
            for q in args[1:]:
                _, y, d2 = self.same(args[0],q,f'{fname}(..)')
                d = d or d2
                res = fct(res,y)
            return _Q(res,d)
    def int_call( self, fname, args, what ):
        """mod, abs, floor, ceil, min, max and clamp of integers"""
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
        if fname in ('abs','floor','ceil'):
            if len(args) != 1:
                self.error(f'{what} takes one argument')
            q = args[0]
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
    @staticmethod
    def boolval( q ):
        return np.asarray(q.v).astype(bool) if np.asarray(q.v).dtype != bool else q.v

class _EmptyBlock:
    """Block without particles, for checking expressions before use"""
    def __len__( self ):
        return 0
    def __getattr__( self, name ):
        dtypes = { 'pdgcode' : np.int32, 'userflags' : np.uint32,
                   'fileidx' : np.int64 }
        return np.zeros(0,dtype = dtypes.get(name,float))

class ParticleFilter:
    """Picks particles with an expression, which is evaluated with numpy on
    blocks of particles (this is also what the pick arguments of MCPLFile,
    MCPLOutFile, histogram, collect_stats, etc. do, and mcpltool -p). For
    instance:

       flt = ParticleFilter("pdgcode == neutron"
                            " and ekin < 25meV"
                            " and abs(x) <= 2mm")
       for block in mcplfile.particle_blocks:
           picked = block[ flt(block) ]

    Whitespace (including newlines) is only used to separate the parts of
    expressions, so long expressions can be written over several lines. The
    expression syntax is like in Python: particle fields (x, y, z, ux, uy,
    uz, polx, poly, polz, ekin, time, weight, pdgcode, userflags, and
    wavelength), fileidx (the position of the particles in the file,
    counting from 0, e.g. "mod(fileidx,10) == 0" for every tenth particle),
    fields of the userdata (userdata.NAME, and userdata.NAME.at(INDEX) for
    the values of arrays, counting from 0, with the units of the fields in
    the userdata layout, e.g. "userdata.temp > 300K"),
    numbers, arithmetic (+, -, *, /, // for the division of non-negative
    integers, and ^ or ** for powers),
    comparisons (which can be chained, as in "0 < x < 2cm"), logical operations
    (and, or, not), bitwise & and | on integers (e.g. on userflags, as in
    "userflags & 0x10", where integers which are not 0 are true), functions
    (sqrt, abs, floor, ceil, exp, log, log10, sin, cos, tan, asin, acos,
    atan, atan2, hypot, min, max, clamp, mod(a,b) for the remainder of the
    division of non-negative integers, and angle_to(x,y,z) for the angle
    between the direction of the particles and the vector (x,y,z), which is
    precise also for small angles), the constant
    pi, and the names neutron, antineutron, proton, antiproton, electron,
    positron (or antielectron), muon, antimuon, and gamma (or photon), which
    can be used for pdgcode values. The wavelength is only defined for
    neutrons and gammas, so it is an error to use it for other particles, and
    expressions must pick neutrons or gammas before using it, as in
    "pdgcode == neutron and wavelength > 1.8Aa" (the right side of and is
    only evaluated for particles where the left side is true, and the right
    side of or only for particles where the left side is false).

    Values with units must always be given with units (except for a plain 0,
    as in "x > 0"): meV, eV, keV, MeV,
    GeV, TeV (energy), ns, us, ms, s (time), Aa, nm, um, mm, cm, m, km
    (length, also for wavelengths), K (temperature, for userdata fields), as
    in "ekin < 25meV", "wavelength > 0.18nm" or "x^2 + y^2 < 4cm^2". The
    units deg and rad can be used for angles (which are otherwise in
    radians), as in "acos(uz) < 10deg". Expressions with missing or
    inconsistent units, like "x < 2" or "x < 1meV", are rejected.

    Integers (like pdgcode, userflags, and integer userdata) work essentially
    as in C, but with more protection against problems like overflow, which
    gives an error, as does combining unsigned integers (like userflags) with
    negative values. The operator / always divides as floating point numbers
    (e.g. 1/2 is 0.5), and // divides non-negative integers (e.g. 7//2 is 3).
    """
    def __init__( self, expression ):
        expression = _expr_normalise(expression)
        self._expr = expression
        self._tree = _expr_parse(expression)
        _expr_check(self._tree, expression)
        self(_EmptyBlock())#check units etc.
        #(for marking stat:sum entries as not available when particles are
        #picked by their positions in the file):
        self._uses_fileidx = any( isinstance(n,ast.Name) and n.id == 'fileidx'
                                  for n in ast.walk(self._tree) )
    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """Return boolean array picking particles in the block"""
        res = np.asarray(_ExprEvaluator(block,self._expr)(self._tree).v)
        if res.dtype.kind in 'iu':
            res = res != 0#like in C, e.g. for "userflags & 0x10"
        if res.dtype != bool:
            raise MCPLError(f'Expression "{self._expr}" is not a condition'
                            ' (e.g. a comparison)')
        return np.broadcast_to(res,(len(block),))
    def __repr__( self ):
        return f'ParticleFilter({self._expr!r})'

class ParticleValue:
    """Numerical value calculated from particle fields with an expression
    (with the syntax of ParticleFilter), for instance for histograms. The
    expression must not have units, so values with units must be divided by
    a unit, as in "ekin/MeV" or "hypot(x,y)/mm". Boolean expressions (like
    "x > 0cm") give 1 for true and 0 for false. For instance:

       val = ParticleValue("ekin/meV")
       for block in mcplfile.particle_blocks:
           print( val(block) )
    """
    def __init__( self, expression ):
        expression = _expr_normalise(expression)
        self._expr = expression
        self._tree = _expr_parse(expression)
        _expr_check(self._tree, expression)
        self(_EmptyBlock())#check units etc.
    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """Return array with the values for the particles in the block"""
        q = _ExprEvaluator(block,self._expr)(self._tree)
        if q.d not in ( None, _dim_unknown ):
            u = _expr_unit_hints.get(q.d)
            if u == 'cm' and 'wavelength' in self._expr:
                u = 'Aa'
            e = self._expr.strip()
            e = e if re.fullmatch(r'\w+|userdata\.\w+(\.at\(\d+\))?',e) else f'({e})'
            hint = f', e.g. {e}/{u}' if u else ''
            raise MCPLError(f'Expression "{self._expr}" has units'
                            f' ({_dimstr(q.d)}), so divide it by a unit{hint}')
        v = np.asarray(q.v)
        if v.dtype == bool:
            v = v.astype(float)
        return np.broadcast_to(v,(len(block),))
    def __repr__( self ):
        return f'ParticleValue({self._expr!r})'

class ParticleEdit:
    """Modification of particle fields given by an expression with statements
    separated by ";", which are evaluated with numpy on blocks of particles.
    For instance:

       edit = ParticleEdit("rotate_z(90deg); z += 10cm;"
                           " wavelength = 1.8Aa")
       for block in mcplfile.particle_blocks:
           outfile.add_particles( block, **edit(block) )

    The statements are executed in order, so each statement sees the results
    of the previous ones. The statements are:

      * Assignments to fields, like "x = 2m*ux" or "z += 1cm" (also -=, *=,
        and /=), where the right hand sides use the syntax of ParticleFilter.
        The values must have the units of the field (e.g. a length for x).
        Assigning wavelength changes the kinetic energy of neutrons and gammas.
      * Assignments to variables (lowercase names which are not names of
        fields, units, constants or functions), which can be used in later
        statements, for instance to keep original values: "tmp = x; x = y;
        y = tmp". Variables keep the units of their values.
      * swap(a,b), which exchanges the values of two fields (or variables)
        with the same units, e.g. "swap(x,y)".
      * rotate_x(angle), rotate_y(angle), rotate_z(angle), which rotate the
        position, direction and polarisation of the particles around the
        given axis (through the origin), e.g. "rotate_y(90deg)". The rotation
        is counter-clockwise when looking from the positive axis towards the
        origin. Rotations by multiples of 90 degrees are exact (e.g.
        "rotate_z(90deg)" changes (x,y) to exactly (-y,x)), and rotations never
        give negative zeros (-0.0).
    """
    _assignable = tuple( f for f in _expr_fields if f != 'fileidx' )
    def __init__( self, expression ):
        expression = _expr_normalise(expression)
        self._expr = expression
        self._statements = []
        variables, used = set(), set()
        def check_var( name ):
            if name.startswith('userdata.'):
                raise MCPLError(f'Fields of the userdata ({name}) can not be'
                                f' changed, in "{expression}"')
            if name in _expr_fields:
                raise MCPLError(f'{name} (the position of the particles in the'
                                f' file) can not be changed, in "{expression}"')
            if not ( name.isidentifier() and name == name.lower() ) or (
                    name in _expr_constants or name in _expr_units
                    or name in _expr_functions or name in _edit_statements ):
                raise MCPLError(f'Can not assign to "{name}" in "{expression}"'
                                ' (fields which can be assigned are: '
                                + ', '.join(self._assignable) + ', and other'
                                ' lowercase names can be used for variables)')
        for part in self._split(expression):
            tree = _expr_parse(part, mode = 'exec')
            stmt = tree.body[0] if len(tree.body) == 1 else None
            if ( isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Call)
                 and isinstance(stmt.value.func,ast.Name)
                 and stmt.value.func.id in _edit_statements ):
                self._statements.append(self._parse_call(stmt.value,part,variables))
                continue
            if not isinstance(stmt,(ast.Assign,ast.AugAssign)):
                raise MCPLError(f'Expected assignments like "x = 2*y" (or'
                                ' swap(..) or rotate_x/y/z(..)) in'
                                f' "{expression}"')
            target = stmt.targets if isinstance(stmt,ast.Assign) else [stmt.target]
            if len(target) != 1 or not isinstance(target[0],ast.Name):
                raise MCPLError(f'Unsupported assignment "{part}" in "{expression}"')
            name = target[0].id
            if name not in self._assignable:
                check_var(name)
                if isinstance(stmt,ast.AugAssign) and name not in variables:
                    raise MCPLError(f'Variable "{name}" used before it is'
                                    f' assigned in "{expression}"')
            if isinstance(stmt,ast.AugAssign):
                value = ast.BinOp(left = ast.Name(id = name, ctx = ast.Load()),
                                  op = stmt.op, right = stmt.value)
            else:
                value = stmt.value
            value = ast.Expression(body = value)
            _expr_check(value, expression, variables)
            used.update( n.id for n in ast.walk(value)
                         if isinstance(n,ast.Name) and n.id in variables )
            if name not in self._assignable:
                variables.add(name)
            self._statements.append( ('assign', name, value) )
        for st in self._statements:
            if st[0] == 'swap':
                used.update( n for n in st[1:] if n in variables )
        used.update(getattr(self,'_used_in_angles',()))
        mod = set()
        for st in self._statements:
            if st[0] == 'assign' and st[1] in self._assignable:
                mod.add( 'ekin' if st[1] == 'wavelength' else st[1] )
            elif st[0] == 'swap':
                mod.update( n for n in st[1:] if n in self._assignable )
            elif st[0] in _rotation_planes:
                for plane in _rotation_planes[st[0]]:
                    mod.update(plane)
        self._modified = frozenset(mod)
        unused = sorted(variables - used)
        if unused:
            raise MCPLError(f'Variable "{unused[0]}" is assigned but never used'
                            f' in "{expression}" (fields which can be assigned'
                            ' are: ' + ', '.join(self._assignable) + ')')
        self(_EmptyBlock())#check units etc.

    def _parse_call( self, call, part, variables ):
        fname = call.func.id
        if call.keywords:
            raise MCPLError(f'Unsupported syntax "{part}" in "{self._expr}"')
        if fname == 'swap':
            if len(call.args) != 2 or not all( isinstance(a,ast.Name)
                                               for a in call.args ):
                raise MCPLError(f'swap(..) takes two fields (or variables)'
                                f' as arguments, as in swap(x,y), in "{self._expr}"')
            names = [ a.id for a in call.args ]
            for n in names:
                if n == 'fileidx':
                    raise MCPLError('fileidx (the position of the particles in'
                                    ' the file) can not be changed, in'
                                    f' "{self._expr}"')
                if n.startswith('userdata.'):
                    raise MCPLError(f'Fields of the userdata ({n}) can not be'
                                    f' changed, in "{self._expr}"')
                if n not in self._assignable and n not in variables:
                    raise MCPLError(f'Can not swap "{n}" in "{self._expr}"'
                                    ' (it is not a field or variable)')
            return ( 'swap', names[0], names[1] )
        if len(call.args) != 1:
            raise MCPLError(f'{fname}(..) takes one argument (an angle) in'
                            f' "{self._expr}"')
        angle = ast.Expression(body = call.args[0])
        _expr_check(angle, self._expr, variables)
        self._used_in_angles = getattr(self,'_used_in_angles',set())
        self._used_in_angles.update( n.id for n in ast.walk(angle)
                                     if isinstance(n,ast.Name) and n.id in variables )
        return ( fname, angle )

    @staticmethod
    def _split( expr ):
        parts, depth, cur = [], 0, ''
        for c in expr:
            if c in '([':
                depth += 1
            elif c in ')]':
                depth -= 1
            if c == ',' and depth == 0:
                raise MCPLError('Separate the statements of edits with ";"'
                                f' (not ",") in "{expr}"')
            if c == ';' and depth == 0:
                parts.append(cur)
                cur = ''
            else:
                cur += c
        parts.append(cur)
        parts = [ p.strip() for p in parts if p.strip() ]
        if not parts:
            raise MCPLError('Empty edit expression')
        return parts

    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr

    @property
    def modified_fields( self ):
        """Names of the fields which the edit can modify (ekin for edits of
        the wavelength)."""
        return self._modified

    def __call__( self, block ):
        """Return dictionary with new values of the modified fields, which can
        be passed as keyword arguments to MCPLOutFile.add_particles together
        with the block."""
        ev = _ExprEvaluator(block,self._expr)
        state = ev.state
        modified = set()
        n = len(block)
        for st in self._statements:
            if st[0] == 'assign':
                _, name, value = st
                q = ev(value)
                if name in self._assignable:
                    d = _expr_field_dims.get(name)
                    if q.d != d and not q.zero and q.d != _dim_unknown:
                        what = _dimstr(q.d) if q.d is None else f'value with {_dimstr(q.d)}'
                        dname = 'unitless' if d is None else f'a {_dimstr(d)}'
                        dname = dname.replace('a energy','an energy')
                        hint = _unit_hint(d) if q.d is None else ''
                        raise MCPLError(f'Can not assign {what} to {name}, which is'
                                        f' {dname}{hint}, in expression "{self._expr}"')
                    v = np.broadcast_to(np.asarray(q.v,dtype=( float if name not in
                                                               ('pdgcode','userflags')
                                                               else None )),(n,))
                    if name == 'wavelength':
                        self._set_wavelength(ev,v,modified)
                        continue
                    if name in ('pdgcode','userflags'):
                        v = self._int_field_values(name,v)
                    q = _Q(v,d)
                    modified.add(name)
                state[name] = q
            elif st[0] == 'swap':
                _, a, b = st
                qa, qb = ev.name(a), ev.name(b)
                ev.same(qa,qb,'swap(..)')
                state[a], state[b] = qb, qa
                modified.update( e for e in (a,b) if e in self._assignable )
            else:
                fname, angle = st
                qa = ev(angle)
                if qa.d not in ( None, _dim_unknown ):
                    ev.error(f'{fname}(..) requires an angle (e.g. 90deg), not'
                             f' {_dimstr(qa.d)}')
                c, s = np.cos(qa.v), np.sin(qa.v)
                #Rotations by multiples of 90 degrees are done exactly, by
                #swapping and negating values, since the cos and sin of such
                #angles in radians are not exactly 0 and +-1 (e.g. rotate_z(90deg)
                #gives exactly (x,y) -> (-y,x)). Adding 0.0 to the results
                #avoids negative zeros (-0.0 + 0.0 is 0.0):
                q = np.asarray(qa.v,dtype=float) / ( 0.5 * np.pi )
                k = np.round(q)
                quarter = ( np.abs( q - k ) <= 8 * np.finfo(float).eps
                            * np.maximum( 1.0, np.abs(k) ) )
                kq = np.mod(k,4).astype(int)
                for a, b in _rotation_planes[fname]:
                    va, vb = ev.name(a), ev.name(b)
                    ra, rb = c * va.v - s * vb.v, s * va.v + c * vb.v
                    if np.any(quarter):
                        A, B = np.asarray(va.v), np.asarray(vb.v)
                        ra = np.where(quarter, np.choose(kq,(A,-B,-A,B)), ra)
                        rb = np.where(quarter, np.choose(kq,(B,A,-B,-A)), rb)
                    state[a] = _Q(ra + 0.0, va.d)
                    state[b] = _Q(rb + 0.0, vb.d)
                    modified.update((a,b))
        res = {}
        for name in sorted(modified):
            v = np.asarray(state[name].v)
            if name in ('pdgcode','userflags'):
                v = self._int_field_values(name,v)#(e.g. after swap(..))
            res[name] = np.broadcast_to(v,(n,))
        return res

    def _int_field_values( self, name, v ):
        """Values for pdgcode or userflags, which must be integers in the range
        of their types (int32 and uint32)"""
        v = np.asarray(v)
        if v.dtype.kind not in 'iub' and not np.all( np.round(v) == v ):
            raise MCPLError(f'Non-integer values assigned to {name} in'
                            f' expression "{self._expr}"')
        info = np.iinfo(np.int32 if name == 'pdgcode' else np.uint32)
        if np.any( ( v < info.min ) | ( v > info.max ) ):
            raise MCPLError(f'Values assigned to {name} must be integers from'
                            f' {info.min} to {info.max}, in expression "{self._expr}"')
        return v.astype(info.dtype)

    def _set_wavelength( self, ev, wl, modified ):
        """Set kinetic energy from wavelength (given in cm)"""
        pdg = np.asarray(ev.name('pdgcode').v)
        if not np.all( np.isin( pdg, (2112,22) ) ):
            raise MCPLError('wavelength can only be assigned to neutrons'
                            ' (pdgcode 2112) and gammas (pdgcode 22)'
                            f' in expression "{self._expr}"')
        if np.any( np.asarray(wl) <= 0.0 ):
            raise MCPLError('wavelength must be assigned positive values'
                            f' in expression "{self._expr}"')
        ev.state['ekin'] = _Q(np.broadcast_to(ekin_from_wavelength(wl/_expr_wl_unit,pdg),
                                              wl.shape),_dim_E)
        modified.add('ekin')

    def __repr__( self ):
        return f'ParticleEdit({self._expr!r})'

def _quantity_functions( coords ):
    """Functions calculating the values of expressions for a block, given as a
    dictionary of names and expressions. Each function returns the values (an
    array) and their dimension (powers of length, energy and time, in which
    the values are in the units of MCPL: cm, MeV and ms, or None for values
    without units)."""
    if isinstance(coords,str) or not hasattr(coords,'items'):
        raise MCPLError('The coords parameter must be a dictionary of'
                        ' coordinate names and expressions')
    res = {}
    for name, expr in coords.items():
        if not isinstance(name,str) or not name:
            raise MCPLError('Coordinate names must be non-empty strings')
        expr = _expr_normalise(expr)
        tree = _expr_parse(expr)
        _expr_check(tree,expr)
        def fct( block, expr = expr, tree = tree ):
            q = _ExprEvaluator(block,expr)(tree)
            v = np.asarray(q.v)
            if v.dtype == bool:
                v = v.astype(float)
            return np.broadcast_to(v,(len(block),)), q.d
        fct(_EmptyBlock())#check units etc.
        res[name] = fct
    return res

def _as_filter(pick):
    if isinstance(pick,str):
        return ParticleFilter(pick)
    return pick

def _as_edit(edit):
    if isinstance(edit,str):
        return ParticleEdit(edit)
    return edit
