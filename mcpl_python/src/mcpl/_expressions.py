
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
import functools
import math

from ._common import MCPLError
from ._exprrotation import _rotation_matrix
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
    ekin_from_wavelength,
    wavelength_from_ekin,
)

_expr_fields = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz',
                 'ekin', 'time', 'weight', 'pdgcode', 'userflags',
                 'wavelength', 'fileidx' )
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
_rotation_matrix_args = { 'rotate_around' : 4, 'rotate_frame' : 12 }
_rotated_vectors = ( ('x','y','z'), ('ux','uy','uz'), ('polx','poly','polz') )
_expr_functions = dict( sqrt = np.sqrt, atan2 = np.arctan2, angle_to = None,
                        mod = np.mod,
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
                 ast.Name, ast.Load, ast.Constant, ast.Call, _Unit )
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

def _expr_canonical( expr, edit = False ):
    """The normalised form of an expression (or of the statements of an edit,
    or of a pick with statements), generated from its parsed form: the same
    for all ways of writing it which are parsed the same, e.g. "ekin/MeV" and
    "(ekin) / MeV", or "25meV" and "25.0 meV". Raises MCPLError for invalid
    syntax."""
    expr = _expr_normalise(expr)
    parts = _split_statements(expr,positions = True)
    if not edit and len(parts) == 1:
        return _Expr(parts[0][0]).canonical
    return ';'.join( _expr_unparse(_expr_parse(part, mode = 'exec', context = ( expr, pos )))
                     for part, pos in parts )

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
        """The particle fields used (including fileidx)"""
        return self.names & frozenset(_expr_fields)

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
        return ev(self.tree)

class _Q:
    """Value with dimension (length,energy,time) in an expression. Values
    without units (like plain numbers, or ux) have dimension None. A plain 0
    (zero is the same in all units) is marked with zero=True, and can be used
    with any units."""
    __slots__ = ('d','v','zero')
    def __init__( self, v, d = None, zero = False ):
        self.v, self.d = v, ( None if d == _dim_none else d )
        self.zero = zero

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
            return self.finite(self.binop(node.op,ev(node.left),ev(node.right)),
                               f'{what} gives')
        if isinstance(node,ast.Compare):
            fcts = { ast.Eq : np.equal, ast.NotEq : np.not_equal,
                     ast.Lt : np.less, ast.LtE : np.less_equal,
                     ast.Gt : np.greater, ast.GtE : np.greater_equal }
            if isinstance(node.ops[0],(ast.In,ast.NotIn)):
                #(equal to any of the values, see _ExprParser._comparison):
                left, res = ev(node.left), False
                for c in node.comparators[0].elts:
                    a, b, _ = self.same(left,ev(c),'comparison with "in"')
                    res = np.logical_or(res,np.equal(a,b))
                return _Q(np.logical_not(res) if isinstance(node.ops[0],ast.NotIn) else res)
            left, res = ev(node.left), True
            for op, c in zip(node.ops,node.comparators):
                right = ev(c)
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
            if fname == 'angle_to':
                #Angle between the direction of the particles and a vector:
                if len(args) != 3:
                    self.error('angle_to(x,y,z) takes three arguments')
                vx, vy, _ = self.same(args[0],args[1],'angle_to(..)')
                _, vz, _ = self.same(args[0],args[2],'angle_to(..)')
                u = tuple( self.name(c).v for c in ('ux','uy','uz') )
                return _Q(_angle_highres(u,(vx,vy,vz)))
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
    @staticmethod
    def boolval( q ):
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

def _check_conditions( node, expr ):
    """Raise MCPLError where a PDG code is used as a condition (in the
    expression of a pick, or a part of it combined with and, or and not), as
    in "neutron" or "pdgcode and x > 0cm", which would be true for all
    particles (other integers can be conditions, as in userflags & 0x10)"""
    if isinstance(node,ast.BoolOp):
        for v in node.values:
            _check_conditions(v,expr)
        return
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):
        _check_conditions(node.operand,expr)
        return
    if ( isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
         and node.func.id == 'abs' and len(node.args) == 1 ):
        node = node.args[0]
    if isinstance(node,ast.Name) and node.id in _particle_names:
        raise MCPLError(f'{node.id} is a PDG code ({_particle_names[node.id]}), not a condition'
                        f' (e.g. pdgcode == {node.id}), in expression "{expr}"')
    if isinstance(node,ast.Name) and node.id == 'pdgcode':
        raise MCPLError(f'pdgcode is not a condition (e.g. pdgcode == neutron), in'
                        f' expression "{expr}"')

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
    numbers, arithmetic (+, -, *, /, and ^ or ** for powers),
    comparisons (which can be chained, as in "0 < x < 2cm"), logical operations
    (and, or, not), bitwise &, | and ~ on integers (e.g. on userflags, as in
    "userflags & 0x10", where integers which are not 0 are true), functions
    (sqrt, abs, floor, ceil, exp, log, log10, sin, cos, tan, asin, acos,
    atan, atan2, hypot, min, max, clamp, mod(a,b) for the remainder of the
    division of integers, and angle_to(x,y,z) for the angle between the
    direction of the particles and the vector (x,y,z), which is precise also
    for small angles), the constant
    pi, and the names neutron, antineutron, proton, antiproton, electron,
    positron (or antielectron), muon, antimuon, and gamma (or photon), which
    can be used for pdgcode values. The wavelength is only defined for
    neutrons and gammas, so it is an error to use it for other particles, and
    expressions must pick neutrons or gammas before using it, as in
    "pdgcode == neutron and wavelength > 1.8Aa" (the right side of and is
    only evaluated for particles where the left side is true, and the right
    side of or only for particles where the left side is false).

    Variables can be assigned before the condition, separated by ";" as the
    statements of edits (see ParticleEdit), as in "r = hypot(x,y); r > 2cm
    and r < 5cm", but the fields of the particles can not be changed.

    Values with units must always be given with units (except for a plain 0,
    as in "x > 0"): meV, eV, keV, MeV,
    GeV, TeV (energy), ns, us, ms, s (time), Aa, nm, um, mm, cm, m, km
    (length, also for wavelengths), as in "ekin < 25meV", "wavelength >
    0.18nm" or "x^2 + y^2 < 4cm^2" (a power directly after a unit only
    applies to the unit, and units can also have half powers, as in
    "sqrt(ekin)/sqrt(eV)"). The units deg and rad can be used for
    angles (which are otherwise in radians), as in "acos(uz) < 10deg".
    Expressions with missing or inconsistent units, like "x < 2" or "x <
    1meV", are rejected.
    """
    def __init__( self, expression ):
        #(statements before the condition, as in "r = hypot(x,y); r > 2cm"):
        self._statements_of = _Statements(expression,pick = True)
        self._e = self._statements_of.condition
        self._expr = self._statements_of.text
        _check_conditions(self._e.tree.body,self._expr)
        self(_EmptyBlock())#check units etc.
        #(for marking stat:sum entries as not available when particles are
        #picked by their positions in the file):
        self._uses_fileidx = 'fileidx' in self._statements_of.fields
    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """Return boolean array picking particles in the block"""
        ev = _ExprEvaluator(block,self._expr)
        self._statements_of.run(ev,set())
        res = np.asarray(ev(self._e.tree).v)
        if res.dtype.kind in 'iu':
            res = res != 0#like in C, e.g. for "userflags & 0x10"
        if res.dtype != bool:
            raise MCPLError(f'Expression "{self._expr}" is not a condition'
                            ' (e.g. a comparison)')
        return np.broadcast_to(res,(len(block),))
    def __repr__( self ):
        return f'ParticleFilter({self._expr!r})'

def _values( q, block ):
    """The values of an evaluated expression (a _Q) for each particle of the
    block (with 1 and 0 for true and false)"""
    v = np.asarray(q.v)
    if v.dtype == bool:
        v = v.astype(float)
    return np.broadcast_to(v,(len(block),))

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
        self._e = _Expr(expression)
        self._expr = self._e.text
        self(_EmptyBlock())#check units etc.
    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """Return array with the values for the particles in the block"""
        q = self._e.evaluate(block)
        if q.d is not None:
            u = _expr_unit_hints.get(q.d)
            if u == 'cm' and 'wavelength' in self._expr:
                u = 'Aa'
            e = self._expr.strip()
            e = e if e.isidentifier() else f'({e})'
            hint = f', e.g. {e}/{u}' if u else ''
            raise MCPLError(f'Expression "{self._expr}" has units'
                            f' ({_dimstr(q.d)}), so divide it by a unit{hint}')
        return _values(q,block)
    def __repr__( self ):
        return f'ParticleValue({self._expr!r})'

def _assignable_fields():
    return tuple( f for f in _expr_fields if f != 'fileidx' )

class _Statements:
    """Statements separated by ";", which edits are made of (see ParticleEdit),
    and which picks can have before their condition (see ParticleFilter), as
    in "r = hypot(x,y); r > 2cm", where they can only assign variables. They
    are parsed once, and run on blocks of particles by run()."""
    _assignable = _assignable_fields()

    def __init__( self, expression, pick = False ):
        self.text = _expr_normalise(expression)
        self.statements = []
        self.variables, self._used = set(), set()
        parts = _split_statements(self.text,positions = True)
        if pick:
            parts, ( last, lastpos ) = parts[:-1], parts[-1]
        for part, pos in parts:
            self._parse(part,pos,pick)
        #(the condition of a pick, the last part):
        self.condition = None
        if pick:
            try:
                tree = _expr_parse(last, context = ( self.text, lastpos ))
            except MCPLError:
                if ';' in self.text and self._is_assignment(last):
                    raise MCPLError('A pick ends with its condition, as in'
                                    f' "r = hypot(x,y); r > 2cm", in "{self.text}"') from None
                raise
            self.condition = _Expr(self.text, tree = tree.body, variables = self.variables)
            self._used.update( self.condition.names & self.variables )
        unused = sorted(self.variables - self._used)
        if unused:
            fields = ( '' if pick else ' (fields which can be assigned are: '
                       + ', '.join(self._assignable) + ')' )
            raise MCPLError(f'Variable "{unused[0]}" is assigned but never used'
                            f' in "{self.text}"{fields}')

    @staticmethod
    def _is_assignment( part ):
        """Whether the text is an assignment (as of a variable)"""
        try:
            stmt = _expr_parse(part, mode = 'exec').body
        except MCPLError:
            return False
        return len(stmt) == 1 and isinstance(stmt[0],( ast.Assign, ast.AugAssign ))

    def _check_var( self, name, pick ):
        """Check that a variable can have the name"""
        if name in _expr_fields:
            raise MCPLError(f'{name} (the position of the particles in the'
                            f' file) can not be changed, in "{self.text}"')
        if not ( name.isidentifier() and name == name.lower() ) or (
                name in _expr_constants or name in _expr_units
                or name in _expr_functions or name in _edit_statements ):
            fields = ( '' if pick else 'fields which can be assigned are: '
                       + ', '.join(self._assignable) + ', and other ' )
            raise MCPLError(f'Can not assign to "{name}" in "{self.text}" ({fields}'
                            'lowercase names which are not names of fields, units,'
                            ' constants or functions can be used for variables)')

    def _parse( self, part, pos, pick ):
        """Parse a statement (in a pick, only assignments of variables)"""
        variables = self.variables
        tree = _expr_parse(part, mode = 'exec', context = ( self.text, pos ))
        stmt = tree.body[0] if len(tree.body) == 1 else None
        if ( isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Call)
             and isinstance(stmt.value.func,ast.Name)
             and stmt.value.func.id in _edit_statements ):
            if pick:
                raise MCPLError(f'{stmt.value.func.id}(..) changes the particles, which'
                                f' picks can not do (edits can), in "{self.text}"')
            self.statements.append(self._parse_call(stmt.value,part,variables))
            return
        if not isinstance(stmt,(ast.Assign,ast.AugAssign)):
            if pick:
                raise MCPLError('Only assignments of variables, like "r = hypot(x,y)",'
                                ' can come before the condition of a pick (separated'
                                f' by ";"), in "{self.text}"')
            raise MCPLError(f'Expected assignments like "x = 2*y" (or'
                            ' swap(..) or rotations like rotate_z(..)) in'
                            f' "{self.text}"')
        target = stmt.targets if isinstance(stmt,ast.Assign) else [stmt.target]
        if len(target) != 1 or not isinstance(target[0],ast.Name):
            raise MCPLError(f'Unsupported assignment "{part}" in "{self.text}"')
        name = target[0].id
        if name in self._assignable and pick:
            raise MCPLError(f'Picks can not change the particles (here {name}), only'
                            ' variables, like "r = hypot(x,y)" (edits can change the'
                            f' particles), in "{self.text}"')
        if name not in self._assignable:
            self._check_var(name,pick)
            if isinstance(stmt,ast.AugAssign) and name not in variables:
                raise MCPLError(f'Variable "{name}" used before it is'
                                f' assigned in "{self.text}"')
        if isinstance(stmt,ast.AugAssign):
            value = ast.BinOp(left = ast.Name(id = name, ctx = ast.Load()),
                              op = stmt.op, right = stmt.value)
        else:
            value = stmt.value
        value = _Expr(self.text, tree = value, variables = variables)
        self._used.update( value.names & variables )
        if name not in self._assignable:
            variables.add(name)
        self.statements.append( ('assign', name, value) )

    def _parse_call( self, call, part, variables ):
        fname = call.func.id
        if call.keywords:
            raise MCPLError(f'Unsupported syntax "{part}" in "{self.text}"')
        if fname == 'swap':
            if len(call.args) != 2 or not all( isinstance(a,ast.Name)
                                               for a in call.args ):
                raise MCPLError(f'swap(..) takes two fields (or variables)'
                                f' as arguments, as in swap(x,y), in "{self.text}"')
            names = [ a.id for a in call.args ]
            for n in names:
                if n == 'fileidx':
                    raise MCPLError('fileidx (the position of the particles in'
                                    ' the file) can not be changed, in'
                                    f' "{self.text}"')
                if n not in self._assignable and n not in variables:
                    raise MCPLError(f'Can not swap "{n}" in "{self.text}"'
                                    ' (it is not a field or variable)')
            self._used.update( n for n in names if n in variables )
            return ( 'swap', names[0], names[1] )
        if fname in _rotation_matrix_args:
            nargs = _rotation_matrix_args[fname]
            if len(call.args) != nargs:
                what = ( 'an axis and an angle, as in rotate_around(0,0,1,90deg)'
                         if fname == 'rotate_around' else 'the components of the vectors'
                         ' v, vout, u and uout, as in rotate_frame(0,0,1,1,0,0,0,1,0,0,1,0)' )
                raise MCPLError(f'{fname}(..) takes {nargs} arguments ({what}) in'
                                f' "{self.text}"')
            args = tuple( _Expr(self.text, tree = a, variables = variables)
                          for a in call.args )
            for a in args:
                self._used.update( a.names & variables )
            return ( fname, args )
        if len(call.args) != 1:
            raise MCPLError(f'{fname}(..) takes one argument (an angle) in'
                            f' "{self.text}"')
        angle = _Expr(self.text, tree = call.args[0], variables = variables)
        self._used.update( angle.names & variables )
        return ( fname, angle )

    @functools.cached_property
    def fields( self ):
        """The particle fields used (including fileidx)"""
        exprs, names = [ self.condition ] if self.condition is not None else [], set()
        for st in self.statements:
            for v in st[1:]:
                if isinstance(v,_Expr):
                    exprs.append(v)
                elif isinstance(v,tuple):
                    exprs += v
                elif v in _expr_fields:
                    names.add(v)#(of swap)
        return frozenset(names).union(*( e.fields for e in exprs ))

    @functools.cached_property
    def modified( self ):
        """Names of the fields which the statements can modify (ekin for
        assignments of the wavelength)"""
        mod = set()
        for st in self.statements:
            if st[0] == 'assign' and st[1] in self._assignable:
                mod.add( 'ekin' if st[1] == 'wavelength' else st[1] )
            elif st[0] == 'swap':
                mod.update( n for n in st[1:] if n in self._assignable )
            elif st[0] in _rotation_planes:
                for plane in _rotation_planes[st[0]]:
                    mod.update(plane)
            elif st[0] in _rotation_matrix_args:
                for vector in _rotated_vectors:
                    mod.update(vector)
        return frozenset(mod)

    def run( self, ev, modified ):
        """Run the statements with the evaluator ev (of a block), which gets
        the values of the variables and of the changed fields in its state,
        adding the names of the changed fields to the set modified"""
        state = ev.state
        n = len(ev._block)
        for st in self.statements:
            if st[0] == 'assign':
                _, name, value = st
                q = ev(value.tree)
                if name in self._assignable:
                    d = _expr_field_dims.get(name)
                    if q.d != d and not q.zero:
                        what = _dimstr(q.d) if q.d is None else f'value with {_dimstr(q.d)}'
                        dname = 'unitless' if d is None else f'a {_dimstr(d)}'
                        dname = dname.replace('a energy','an energy')
                        hint = _unit_hint(d) if q.d is None else ''
                        raise MCPLError(f'Can not assign {what} to {name}, which is'
                                        f' {dname}{hint}, in expression "{self.text}"')
                    v = np.broadcast_to(np.asarray(q.v,dtype=( float if name not in
                                                               ('pdgcode','userflags')
                                                               else None )),(n,))
                    if name == 'wavelength':
                        self._set_wavelength(ev,v,modified)
                        continue
                    q = _Q(v,d)
                    modified.add(name)
                state[name] = q
            elif st[0] == 'swap':
                _, a, b = st
                qa, qb = ev.name(a), ev.name(b)
                ev.same(qa,qb,'swap(..)')
                state[a], state[b] = qb, qa
                modified.update( e for e in (a,b) if e in self._assignable )
            elif st[0] in _rotation_matrix_args:
                self._rotate_by_matrix(ev,st[0],st[1],modified)
            else:
                fname, angle = st
                qa = ev(angle.tree)
                if qa.d is not None:
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
    def _rotate_by_matrix( self, ev, fname, args, modified ):
        """Rotate the positions, directions and polarisations with the matrix
        of rotate_around or rotate_frame (see _rotation_matrix)"""
        qs = [ ev(a.tree) for a in args ]
        #(vectors whose components have the same units, and an angle):
        for i in range(0,len(qs) - len(qs) % 3,3):
            ev.same(qs[i],qs[i+1],f'{fname}(..)')
            ev.same(qs[i],qs[i+2],f'{fname}(..)')
        if fname == 'rotate_around' and qs[3].d is not None:
            ev.error(f'{fname}(..) requires an angle (e.g. 90deg) as its last'
                     f' argument, not {_dimstr(qs[3].d)}')
        R = _rotation_matrix(fname,[ q.v for q in qs ])
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

    def _set_wavelength( self, ev, wl, modified ):
        """Set kinetic energy from wavelength (given in cm)"""
        pdg = np.asarray(ev.name('pdgcode').v)
        if not np.all( np.isin( pdg, _wavelength_pdgcodes ) ):
            raise MCPLError('wavelength can only be assigned to neutrons'
                            ' (pdgcode 2112) and gammas (pdgcode 22)'
                            f' in expression "{self.text}"')
        if np.any( np.asarray(wl) <= 0.0 ):
            raise MCPLError('wavelength must be assigned positive values'
                            f' in expression "{self.text}"')
        ev.state['ekin'] = _Q(np.broadcast_to(ekin_from_wavelength(wl/_expr_wl_unit,pdg),
                                              wl.shape),_dim_E)
        modified.add('ekin')

def _split_statements( expr, positions = False ):
    """The statements separated by ";" (outside parentheses) of an edit or a
    pick (with their positions in it, if positions is set)"""
    parts, depth, start = [], 0, 0
    for i, c in enumerate(expr):
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        if c == ',' and depth == 0:
            raise MCPLError('Separate statements with ";"'
                            f' (not ",") in "{expr}"')
        if c == ';' and depth == 0:
            parts.append( ( expr[start:i], start ) )
            start = i + 1
    parts.append( ( expr[start:], start ) )
    parts = [ ( p.strip(), pos + len(p) - len(p.lstrip()) ) for p, pos in parts if p.strip() ]
    if not parts:
        raise MCPLError('Empty expression')
    return parts if positions else [ p for p, _ in parts ]


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
      * rotate_around(ax,ay,az,angle), which rotates them around the axis
        (ax,ay,az) through the origin (which need not be a unit vector),
        counter-clockwise when looking from the axis towards the origin, e.g.
        "rotate_around(1,1,0,30deg)".
      * rotate_frame(vx,vy,vz,vox,voy,voz,ux,uy,uz,uox,uoy,uoz), the rotation
        which turns the direction of the vector v into that of vout, and u
        into uout (as RotMatrix of NCrystal) (e.g. a beam direction and an "up" direction of one frame
        into those of another). The angle between v and u must be that
        between vout and uout, and v and u must not be parallel.
    """
    _assignable = _assignable_fields()
    def __init__( self, expression ):
        self._statements_of = _Statements(expression)
        self._expr = self._statements_of.text
        self._statements = self._statements_of.statements
        self._modified = self._statements_of.modified
        self(_EmptyBlock())#check units etc.

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
        modified = set()
        self._statements_of.run(ev,modified)
        state, n = ev.state, len(block)
        res = {}
        for name in sorted(modified):
            v = np.asarray(state[name].v)
            if name in ('pdgcode','userflags') and v.dtype.kind not in 'iub':
                vi = np.round(v).astype(np.int64)
                if not np.all( vi == v ):
                    raise MCPLError(f'Non-integer values assigned to {name}')
                v = vi
            res[name] = np.broadcast_to(v,(n,))
        return res

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
        e = _Expr(expr)
        def fct( block, e = e ):
            q = e.evaluate(block)
            return _values(q,block), q.d
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
