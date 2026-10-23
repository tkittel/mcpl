
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

"""The core of the particle expressions (see _expressions): the names
which can be used in them, their checks, and their evaluation"""

__all__ = []

import ast
import functools
import math

from ._common import MCPLError
from ._exprsyntax import (
    _dim_E,
    _dim_L,
    _dim_none,
    _dim_T,
    _expr_parse,
    _expr_units,
    _expr_unparse,
    _Unit,
)
from ._numpy import np
from ._particles import _particle_names, _wavelength_pdgcodes
from ._physics import (
    _pdg_label,
    _pdg_name,
    wavelength_from_ekin,
)

_expr_fields = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz',
                 'ekin', 'time', 'weight', 'pdgcode', 'userflags',
                 'wavelength', 'fileidx' )
#The vectors of the particles, and their values (e.g. x is pos.x):
_expr_vectors = { 'pos' : ( 'x', 'y', 'z' ), 'dir' : ( 'ux', 'uy', 'uz' ),
                  'pol' : ( 'polx', 'poly', 'polz' ) }
_expr_constants = { 'pi' : math.pi, **_particle_names }
_expr_field_dims = { 'x' : _dim_L, 'y' : _dim_L, 'z' : _dim_L,
                     'ekin' : _dim_E, 'time' : _dim_T,
                     'wavelength' : _dim_L }
_expr_wl_unit = 1e-8#wavelengths are in Aa in the Python API
#Fields which are only defined for some particles: the field and the values
#for which they are defined:
_expr_field_domains = { 'wavelength' : ( 'pdgcode', _wavelength_pdgcodes ) }
#Labels and short names of the values of fields (for labels in plots and
#tables, with symbols for plots if unicode is set, see _pdg_symbols):
_expr_value_names = { 'pdgcode' : ( _pdg_label, _pdg_name ) }
#Example units to suggest in error messages:
_expr_unit_hints = { _dim_L : 'cm', _dim_E : 'MeV', _dim_T : 'ms' }
#Functions requiring dimensionless arguments:
_expr_functions_nodim = { 'exp' : np.exp, 'log' : np.log, 'log10' : np.log10,
                          'sin' : np.sin, 'cos' : np.cos, 'tan' : np.tan,
                          'asin' : np.arcsin, 'acos' : np.arccos,
                          'atan' : np.arctan }
#Functions giving integers, of values without units:
_expr_functions_toint = { 'round' : np.rint, 'floor' : np.floor, 'ceil' : np.ceil }
#Functions keeping the units of the argument(s):
_expr_functions_samedim = { 'abs' : np.abs, 'min' : np.minimum,
                            'max' : np.maximum, 'hypot' : np.hypot,
                            'clamp' : np.clip }
#Functions used as statements in edits:
_edit_statements = ( 'swap', 'rotate_x', 'rotate_y', 'rotate_z', 'rotate_around',
                     'rotate_frame' )
#Components of position, direction and polarisation changed by rotations:
_rotation_planes = { 'rotate_x' : ( ('y','z'), ('uy','uz'), ('poly','polz') ),
                     'rotate_y' : ( ('z','x'), ('uz','ux'), ('polz','polx') ),
                     'rotate_z' : ( ('x','y'), ('ux','uy'), ('polx','poly') ) }
#The rotations given by a matrix, with the numbers of their arguments (an
#axis and an angle, or the vectors v, vout, u, uout), and the vectors they
#rotate:
_rotation_matrix_args = { 'rotate_around' : 2, 'rotate_frame' : 4 }
_rotated_vectors = ( ('x','y','z'), ('ux','uy','uz'), ('polx','poly','polz') )
#Functions of vectors (abs also gives the lengths of vectors):
_expr_functions_vector = ( 'dot', 'cross', 'angle' )
_expr_functions = dict( sqrt = np.sqrt, atan2 = np.arctan2, mod = np.mod,
                        **dict.fromkeys(_expr_functions_vector),
                        **_expr_functions_nodim, **_expr_functions_toint,
                        **_expr_functions_samedim )

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


def _expr_check( node, expr, variables = () ):
    """Check that only supported constructs are used in parsed expression
    (variables are names of variables defined in edits)"""
    ok_nodes = ( ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp,
                 ast.Not, ast.USub, ast.UAdd, ast.Invert, ast.BinOp, ast.Add,
                 ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.FloorDiv,
                 ast.BitAnd, ast.BitOr, ast.Compare, ast.Eq, ast.NotEq,
                 ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Tuple,
                 ast.Subscript, ast.Name, ast.Load, ast.Constant, ast.Call, _Unit )
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
                                            or n.id in _expr_vectors
                                            or n.id in variables
                                            or n.id in _expr_constants
                                            or n.id in _expr_functions
                                            or n.id.startswith('userdata.') ):
            if n.id == 'userdata':
                raise MCPLError(f'Fields of the userdata are written as userdata.NAME,'
                                f' in expression "{expr}"')
            raise MCPLError(f'Unknown name "{n.id}" in expression "{expr}"'
                            ' (particle fields are: '
                            + ', '.join(_expr_fields) + ')')

class _Expr:
    """A parsed (and checked) expression of a value or condition: the common
    basis of ParticleFilter, ParticleValue and the values in ParticleEdit,
    with the properties derived from its tree, and its evaluation. The tree
    is given for parts of other expressions (like the values assigned in
    edits, with their variables), and the text is then used in messages."""
    def __init__( self, text, tree = None, variables = () ):
        self.text = _expr_normalise(text)
        self.tree = _expr_parse(self.text) if tree is None else ast.Expression(body = tree)
        _expr_check(self.tree, self.text, variables)

    @functools.cached_property
    def canonical( self ):
        """The normalised text, generated from the tree (see _expr_canonical)"""
        return _expr_unparse(self.tree)

    @functools.cached_property
    def names( self ):
        """All names used (fields, variables, constants and functions)"""
        return frozenset( n.id for n in ast.walk(self.tree) if isinstance(n,ast.Name) )

    @property
    def fields( self ):
        """The particle fields used (including fileidx, and those of the
        vectors used, as x for pos)"""
        vectors = [ _expr_vectors[n] for n in self.names if n in _expr_vectors ]
        return ( self.names & frozenset(_expr_fields) ).union(*vectors)

    @property
    def field( self ):
        """The field if the expression is just a field (as "pdgcode"), else None"""
        body = self.tree.body
        return body.id if isinstance(body,ast.Name) and body.id in _expr_fields else None

    @property
    def domains( self ):
        """Where the expression is defined, if only for some particles (as for
        wavelengths): a list of (field, values) which must all hold (see
        _expr_field_domains)"""
        return [ _expr_field_domains[f] for f in sorted(self.fields) if f in _expr_field_domains ]

    def value_label( self, value, unicode = False ):
        """Label of a value of the expression if it is a field whose values have
        names (as "n (2112)" for pdgcode, see _expr_value_names), else None"""
        names = _expr_value_names.get(self.field)
        return names[0](value,unicode) if names else None

    def domain_mask( self, block ):
        """Mask of the particles of the block for which the expression is
        defined"""
        mask = np.ones(len(block),dtype=bool)
        for field, values in self.domains:
            mask &= np.isin(np.broadcast_to(getattr(block,field),(len(block),)),list(values))
        return mask

    def evaluate( self, block, active = None ):
        """The value (a _Q) for the particles of the block (for those of the mask
        active, if given)"""
        ev = _ExprEvaluator(block,self.text)
        ev.active = active
        return ev.scalar(ev(self.tree),'the value of an expression')

class _Q:
    """Value with dimension (length,energy,time) in an expression. Values
    without units (like plain numbers, or ux) have dimension None. A plain 0
    (zero is the same in all units) is marked with zero=True, and can be used
    with any units."""
    __slots__ = ('d','v','zero')
    def __init__( self, v, d = None, zero = False ):
        self.v, self.d = v, ( None if d == _dim_none else d )
        self.zero = zero

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
    for n, e in zip(('length','energy','time'),d):
        if e:
            res.append( n if e == 1 else f'{n}^{e}' )
    return '*'.join(res)

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
        if n.startswith('userdata.'):
            field, _, index = n[9:].partition('.at(')
            return self._userdata(field,int(index[:-1]) if index else None)
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
        if n in _expr_vectors:
            return _V( self.name(c) for c in _expr_vectors[n] )
        if n in _expr_constants:
            return _Q(_expr_constants[n])
        if n not in self._cache:
            q = _Q(getattr(self._block,n),_expr_field_dims.get(n))
            self._cache[n] = self.finite(q,f'The particle field {n} has')
        return self._cache[n]
    def _userdata( self, field, index = None ):
        """The values of the field of the userdata (without units), or of the
        value with the index (from 0) of a field with an array of values"""
        if isinstance(self._block,_EmptyBlock):
            return _Q(np.zeros(0))#(all fields, when checked without a file)
        ud = self._block.userdata
        name = f'userdata.{field}' + ( '' if index is None else f'.at({index})' )
        if ud is None:
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
        return _Q(v.astype(float) if v.dtype.kind in 'iub' else v)

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
        if v.dtype.kind in 'fc':
            bad = ~np.isfinite(v)
            if self.active is not None:
                bad = bad & self.active
            if np.any(bad):
                self.error(f'{what} NaN or infinite values')
        return q
    def _check_wavelength( self ):
        pdg = np.asarray(self.name('pdgcode').v)
        bad = ~np.isin(pdg,_wavelength_pdgcodes)
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
        if a.d != b.d and ( a.zero or b.zero ):
            return a.v, b.v, ( a.d or b.d )
        if a.d != b.d:
            hint = _unit_hint(a.d or b.d) if None in (a.d,b.d) else ''
            self.error(f'Incompatible units in {what}: {_dimstr(a.d)} and'
                       f' {_dimstr(b.d)}{hint}')
        return a.v, b.v, a.d
    def nodim( self, q, what ):
        if q.d is not None:
            self.error(f'{what} requires a value without units, not {_dimstr(q.d)}')
        return q.v
    def __call__( self, node ):
        ev = self
        if isinstance(node,ast.Expression):
            return ev(node.body)
        if isinstance(node,ast.Constant):
            return self.finite(_Q(node.value,zero=(node.value==0)),'A constant has')
        if isinstance(node,ast.Name):
            return self.name(node.id)
        if isinstance(node,ast.Tuple):
            return self.vector([ ev(e) for e in node.elts ])
        if isinstance(node,ast.Subscript):
            v, i = ev(node.value), node.slice.value
            if not isinstance(v,_V):
                self.error('Only vectors have values like .x or .at(INDEX)')
            if i >= len(v.c):
                self.error(f'The index {i} is too large for {v.describe()}'
                           ' (the values are counted from 0)')
            return v.c[i]
        if isinstance(node,_Unit):
            v, d = _expr_units[node.unit]
            return _Q(v ** node.power,self.dimpow(d,node.power,f'The unit {node.unit}'))
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
            q = ev(node.operand)
            if isinstance(q,_V):
                if not isinstance(node.op,(ast.USub,ast.UAdd)):
                    self.error(f'{"not" if isinstance(node.op,ast.Not) else "~"} can not'
                               f' be used for vectors (here {q.describe()})')
                return _V( _Q(-c.v,c.d,zero=c.zero) for c in q.c ) if isinstance(node.op,ast.USub) else q
            if isinstance(node.op,ast.Not):
                return _Q(np.logical_not(self.boolval(q)))
            if isinstance(node.op,ast.USub):
                return _Q(-q.v,q.d,zero=q.zero)
            if isinstance(node.op,ast.Invert):
                return _Q(np.invert(self._int(q,'~')))
            return q
        if isinstance(node,ast.BinOp):
            what = { ast.Add : 'Addition', ast.Sub : 'Subtraction',
                     ast.Mult : 'Multiplication', ast.Div : 'Division',
                     ast.FloorDiv : 'Floor division',
                     ast.Pow : 'Raising to a power' }.get(type(node.op),'An operation')
            a, b = ev(node.left), ev(node.right)
            res = ( self.vbinop(node.op,a,b) if isinstance(a,_V) or isinstance(b,_V)
                    else self.binop(node.op,a,b) )
            return self.finite(res,f'{what} gives')
        if isinstance(node,ast.Compare):
            fcts = { ast.Eq : np.equal, ast.NotEq : np.not_equal,
                     ast.Lt : np.less, ast.LtE : np.less_equal,
                     ast.Gt : np.greater, ast.GtE : np.greater_equal }
            if isinstance(node.ops[0],(ast.In,ast.NotIn)):
                #(equal to any of the values, see _ExprParser._comparison):
                left, res = self.scalar(ev(node.left),'compared'), False
                for c in node.comparators[0].elts:
                    a, b, _ = self.same(left,ev(c),'comparison with "in"')
                    res = np.logical_or(res,np.equal(a,b))
                return _Q(np.logical_not(res) if isinstance(node.ops[0],ast.NotIn) else res)
            left, res = self.scalar(ev(node.left),'compared'), True
            for op, c in zip(node.ops,node.comparators):
                right = self.scalar(ev(c),'compared')
                a, b, _ = self.same(left,right,'comparison')
                res = np.logical_and(res,fcts[type(op)](a,b))
                left = right
            return _Q(res)
        if isinstance(node,ast.Call):
            return self.finite(self.call(node.func.id,[ev(a) for a in node.args]),
                               f'{node.func.id}(..) gives')
        raise MCPLError('Unsupported expression')#should not happen
    def binop( self, op, a, b ):
        if isinstance(op,(ast.BitAnd,ast.BitOr)):
            sym = '&' if isinstance(op,ast.BitAnd) else '|'
            fct = np.bitwise_and if sym == '&' else np.bitwise_or
            return _Q(fct(self._int(a,sym),self._int(b,sym)))
        with np.errstate(divide='ignore',invalid='ignore'):
            if isinstance(op,(ast.Add,ast.Sub,ast.FloorDiv)):
                x, y, d = self.same(a,b,'arithmetic')
                fct = { ast.Add : np.add, ast.Sub : np.subtract,
                        ast.FloorDiv : np.floor_divide }[type(op)]
                return _Q(fct(x,y),d)
            if isinstance(op,(ast.Mult,ast.Div)):
                if isinstance(op,ast.Mult):
                    v, sign = a.v * b.v, 1
                else:
                    v, sign = np.true_divide(a.v,b.v), -1
                da, db = a.d or _dim_none, b.d or _dim_none
                d = tuple( i + sign * j for i,j in zip(da,db) )
                return _Q(v,d)
            #Power:
            if b.d is not None:
                self.error(f'Exponent with units ({_dimstr(b.d)})')
            if a.d is None:
                return _Q(np.power(np.asarray(a.v,dtype=float),b.v))
            e = np.asarray(b.v)
            if e.ndim:
                self.error('Values with units can only be raised to constant powers')
            e = float(e)
            return _Q(np.power(np.asarray(a.v,dtype=float),e),
                      self.dimpow(a.d,e,'Raising to a power'))
    def dimpow( self, d, e, what ):
        """The dimension d to the power e, which must give whole or half powers
        of the units (as in sqrt(ekin))"""
        if d is None:
            return None
        res = []
        for i in d:
            p = i * e
            if 2 * p != round(2 * p):
                self.error(f'{what} gives units with powers which are not whole or'
                           f' half numbers ({_dimstr(d)} to the power {e:g})')
            res.append( int(p) if float(p).is_integer() else float(p) )
        return tuple(res)
    def call( self, fname, args ):
        fct = _expr_functions[fname]
        if fname in _expr_functions_vector or ( fname == 'abs' and len(args) == 1
                                                and isinstance(args[0],_V) ):
            with np.errstate(divide='ignore',invalid='ignore'):
                return self.vcall(fname,args)
        for q in args:
            self.scalar(q,f'used in {fname}(..)')
        with np.errstate(divide='ignore',invalid='ignore'):
            if fname in _expr_functions_nodim:
                if len(args) != 1:
                    self.error(f'{fname}(..) takes one argument')
                return _Q(fct(self.nodim(args[0],f'{fname}(..)')))
            if fname in _expr_functions_toint:
                if len(args) != 1:
                    self.error(f'{fname}(..) takes one argument')
                v = np.asarray(fct(self.nodim(args[0],f'{fname}(..)')))
                if v.dtype.kind in 'iub':
                    return _Q(v)
                big = ~( np.abs(v) < 2.0**62 )
                if self.active is not None:
                    big &= self.active
                if np.any(big):
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
                if len(args) != 2:
                    self.error('mod(a,b) takes two arguments')
                for q in args:
                    if np.asarray(q.v).dtype.kind not in 'iu' or q.d is not None:
                        self.error('mod(a,b) requires integers without units'
                                   ' (like userflags or pdgcode)')
                a, b = ( np.asarray(q.v) for q in args )
                if np.any( b == 0 ):
                    self.error('Division by zero in mod(a,b)')
                return _Q(np.mod(a,b))
            #Functions keeping units:
            if fname == 'hypot':
                if len(args) < 2:
                    self.error('hypot(..) takes two or more arguments')
                d = args[0].d
                for q in args[1:]:
                    self.same(args[0],q,'hypot(..)')
                return _Q(np.sqrt(sum( np.square(q.v) for q in args )),d)
            if len(args) == 1 and fname == 'abs':
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
        if isinstance(op,(ast.Add,ast.Sub)):
            if not ( va and vb ) or len(a.c) != len(b.c):
                self.error('Vectors can only be added to or subtracted from vectors of'
                           ' the same size (not '
                           f'{a.describe() if va else "a number"} and'
                           f' {b.describe() if vb else "a number"})')
            return _V( self.binop(op,x,y) for x, y in zip(a.c,b.c) )
        if isinstance(op,ast.Mult) and not ( va and vb ):
            return ( _V( self.binop(op,x,b) for x in a.c ) if va
                     else _V( self.binop(op,a,y) for y in b.c ) )
        if isinstance(op,ast.Div) and va and not vb:
            return _V( self.binop(op,x,b) for x in a.c )
        if isinstance(op,ast.Pow) and va and not vb and np.ndim(b.v) == 0 and b.v == 2:
            return self.call('dot',[a,a])
        self.error('Vectors can be added and subtracted, multiplied and divided by numbers,'
                   ' and v^2 gives their lengths squared (dot(v,w) and cross(v,w) give'
                   ' their dot and cross products)')
    def vcall( self, fname, args ):
        """The functions of vectors: dot, cross, angle and abs (the length)"""
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
        mult = lambda x, y : self.binop(ast.Mult(),x,y)
        if fname == 'dot':
            res = mult(v.c[0],w.c[0])
            for x, y in zip(v.c[1:],w.c[1:]):
                res = self.binop(ast.Add(),res,mult(x,y))
            return res
        sub = lambda i, j : self.binop(ast.Sub(),mult(v.c[i],w.c[j]),mult(v.c[j],w.c[i]))
        return _V([ sub(1,2), sub(2,0), sub(0,1) ])
    def boolval( self, q ):
        q = self.scalar(q,'a condition')
        return np.asarray(q.v).astype(bool) if np.asarray(q.v).dtype != bool else q.v
    @staticmethod
    def _int( q, op ):
        a = np.asarray(q.v)
        if a.dtype.kind not in 'iub':
            hint = ( 'use "not" for logical not' if op == '~'
                     else 'use "and" and "or" for logical and/or' )
            raise MCPLError(f'The bitwise operator {op} requires integer operands'
                            f' ({hint})')
        return a

class _EmptyBlock:
    """Block without particles, for checking expressions before use"""
    def __len__( self ):
        return 0
    def __getattr__( self, name ):
        return np.zeros(0,dtype = int if name in ('pdgcode','userflags','fileidx')
                        else float)
