
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

"""Code doing what edit expressions do (see _expressions), in other languages:
complete programs reading an MCPL file and writing the particles kept, with
their changes, to a new file. The translator (_Translator) decides what is
computed, with which types and checks, as the expressions do (see
_ExprEvaluator), and a language provider writes the code: _CCode (in
_expr_ast2c) for C, and _CppCode (in _expr_ast2cpp) for C++, which share
_CLikeCode (in _expr_clike). Interface: _expr_ast2code(lang, tree, layout),
with the class of the language provider.

The providers get operations, never code of other languages: like checked
integer additions of a type, or conditions evaluated only where the
conditions before them leave it open (as and and or do). So a provider can
also write code working on blocks of particles, with conditions as
selections of the particles of the block."""

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
    Vector,
)
from ._expr_ast2str import _expr_ast2str
from ._expr_vocab import (
    _assignable,
    _common_int_type,
    _expr_constants,
    _expr_vectors,
    _functions_nodim,
    _functions_toint,
    _int_constant,
    _int_constant_type,
    _int_field_types,
    _int_range,
    _is_filter,
    _is_square,
    _modified_fields,
    _rotation_planes,
    _userdata_field,
)
from ._exprunits import _quantity_value, _unit_size
from ._particles import _particle_names


class _Code(tuple):
    """A translated number: (code, type), with what is known about it: the
    value of an integer constant of the expression (const, see
    _int_constant), whether the code checks that it is finite (checked), and
    whether the code is a single term, which needs no parentheses in other
    expressions (atom)"""
    def __new__( cls, code, t, *, const = None, checked = False, atom = False ):
        self = super().__new__(cls,( code, t ))
        self.const, self.checked, self.atom = const, checked, atom
        return self

    def with_const( self, const ):
        return _Code(*self,const = const,checked = self.checked,atom = self.atom)

def _term( code, t ):
    """A translated number whose code is a single term (see _Code)"""
    return _Code(code,t,atom = True)

class _Translator:
    """Translates checked and normalised trees of edit expressions (see
    _expr_ast2astnorm) with the language provider lang. The values are numbers
    (see _Code), or lists of them for vectors. What the checks of the trees
    ensure (like integers where they are needed) is only asserted."""

    def __init__( self, lang ):
        self.lang = lang
        #(the values of the variables):
        self.variables = {}

    #Expressions:

    def __call__( self, node ):
        """The value of the node"""
        res = self._value(node)
        c = _int_constant(node)
        return res if c is None or isinstance(res,list) else res.with_const(c)

    def _value( self, node ):
        lang = self.lang
        if isinstance(node,Int):
            return self.int_constant(node.value)
        if isinstance(node,Float):
            return lang.float_constant(node.value)
        if isinstance(node,Quantity):
            return lang.float_constant(_quantity_value(node.number.value,node.unit,node.power),
                                       _expr_ast2str(node))
        if isinstance(node,Unit):
            return lang.float_constant(_unit_size(node.unit,node.power),_expr_ast2str(node))
        if isinstance(node,Particle):
            return self.int_constant(_particle_names[node.name],node.name)
        if isinstance(node,Name):
            return self.name(node.id)
        if isinstance(node,Userdata):
            return self.userdata_value(node)
        if isinstance(node,Vector):
            return [ self.scalar(self(c)) for c in node.components ]
        if isinstance(node,Part):
            v = self(node.vector)
            assert isinstance(v,list) and node.index < len(v)
            return v[node.index]
        if isinstance(node,Logical):
            return lang.logical(node.op,[ self.condition(v) for v in node.values ])
        if isinstance(node,Unary):
            return self.unary(node)
        if isinstance(node,Binary):
            left = self(node.left)
            if node.op == '^' and isinstance(left,list) and _is_square(node.right):
                return self.dot(left,left)
            return self.binary(node.op,left,self(node.right))
        if isinstance(node,Compare):
            return self.compare_chain(node)
        if isinstance(node,In):
            v = self.scalar(self(node.value))
            res = lang.logical('or',[ self.known(self.compare('==',v,self(c))) for c in node.values ])
            return lang.logical_not(res) if node.negated else res
        assert isinstance(node,Call)
        return self.call(node.name,[ self(a) for a in node.args ])

    def compare_chain( self, node ):
        """Comparisons, chained like a < b < c (as a < b and b < c, where each
        value is only needed where the comparisons before it are true)"""
        left = [ self.scalar(self(node.first)) ]
        def term( op, v ):
            def translate():
                right = self.scalar(self(v))
                res = self.compare(op,left[0],right)
                left[0] = right
                return res
            return translate
        terms = [ term(op,v) for op, v in zip(node.ops,node.values) ]
        return terms[0]() if len(terms) == 1 else self.lang.logical('and',terms)

    def condition( self, node ):
        """The condition of the node, as the function translating it, which
        the language provider calls only where the value is needed (see
        _expr_ast2code)"""
        return lambda : self.scalar(self(node))

    @staticmethod
    def known( value ):
        """A value already translated, as a condition (see condition)"""
        return lambda : value

    @staticmethod
    def scalar( x ):
        assert not isinstance(x,list)
        return x

    def int_constant( self, v, comment = None ):
        """An integer constant, typed like in the expressions (see
        _int_constant_type)"""
        t = _int_constant_type(v)
        assert t is not None
        return self.lang.int_constant(v,t,comment)

    def name( self, n ):
        lang = self.lang
        if n in self.variables:
            return self.variables[n]
        if n in _expr_vectors:
            return [ self.name(c) for c in _expr_vectors[n] ]
        if n in _expr_constants:
            return lang.float_constant(_expr_constants[n],n)
        if n == 'wavelength':
            return lang.wavelength()
        if n in _int_field_types:
            return lang.field(n)
        #(checked for each use, as in the expressions):
        return lang.check_finite(lang.field(n))

    def userdata_value( self, node ):
        from ._userdata import userdata_units
        name = node.field
        ftype, count, factor, _ = _userdata_field(self.lang.layout,name,node.index)
        value = self.lang.userdata_value(name,ftype,count,node.index)
        if factor != 1.0:
            #(in the units of MCPL, exactly as in the expressions):
            unit = userdata_units(self.lang.layout)[name]
            return self.lang.scaled(value,self.lang.float_constant(factor,unit))
        return value

    def unary( self, node ):
        if node.op == 'not':
            return self.lang.logical_not(self.scalar(self(node.operand)))
        x = self(node.operand)
        if node.op == '+':
            return x
        if isinstance(node.operand,Int):
            #(negative integer constants, like -2147483648):
            return self.int_constant(-node.operand.value)
        if isinstance(x,list):
            return [ self.negate(c) for c in x ]
        return self.negate(x)

    def negate( self, x ):
        if x[1] == 'f64':
            return self.lang.negate(x)
        return self.lang.int_op('neg',x[1],x)

    def nonneg( self, x, t ):
        """The integer x as the unsigned type t (checking that it is not
        negative, unless it is unsigned or a constant which is not negative)"""
        if x[1][0] == 'u' or ( x.const is not None and x.const >= 0 ):
            return x
        return self.lang.int_op('as',t,x)

    def int_values( self, a, b ):
        """The common type of integers, and their values in it"""
        t = _common_int_type(a[1],b[1])
        if t[0] == 'u':
            return t, self.nonneg(a,t), self.nonneg(b,t)
        return t, a, b

    def as_float( self, x ):
        return x if x[1] == 'f64' else self.lang.to_float(x)

    def binary( self, op, a, b ):
        if isinstance(a,list) or isinstance(b,list):
            return self.vector_binary(op,a,b)
        lang = self.lang
        ints = a[1] != 'f64' and b[1] != 'f64'
        if op in ( '&', '|' ):
            assert ints
            return lang.int_exact(op,*self.int_values(a,b))
        if op == '//':
            assert ints
            return self.div_mod('div',a,b)
        if op in ( '+', '-', '*' ) and ints:
            return lang.int_op({ '+' : 'add', '-' : 'sub', '*' : 'mul' }[op],*self.int_values(a,b))
        a, b = self.as_float(a), self.as_float(b)
        #(all results checked, as in the expressions):
        if op == '^':
            return lang.check_finite(lang.math_call('pow',a,b))
        return lang.check_finite(lang.float_op(op,a,b))

    def vector_binary( self, op, a, b ):
        va, vb = isinstance(a,list), isinstance(b,list)
        if op in ( '+', '-' ) and va and vb and len(a) == len(b):
            return [ self.binary(op,x,y) for x, y in zip(a,b) ]
        if op == '*' and va != vb:
            return [ self.binary(op,x,b) for x in a ] if va else [ self.binary(op,a,y) for y in b ]
        assert op == '/' and va and not vb
        return [ self.binary(op,x,b) for x in a ]

    def div_mod( self, op, a, b ):
        """a // b or mod(a,b), of integers"""
        t, x, y = self.int_values(a,b)
        if t[0] == 'u' and b.const is not None and b.const > 0:
            #(unsigned values divided by a positive constant can not fail):
            return self.lang.int_exact(op,t,x,y)
        return self.lang.int_op(op,t,x,y)

    def compare( self, op, a, b ):
        a, b = self.scalar(a), self.scalar(b)
        if a[1] != 'f64' and b[1] != 'f64':
            _, a, b = self.int_values(a,b)
        return self.lang.compare(op,a,b)

    def dot( self, v, w ):
        res = self.binary('*',v[0],w[0])
        for x, y in zip(v[1:],w[1:]):
            res = self.binary('+',res,self.binary('*',x,y))
        return res

    def call( self, fname, args ):
        """The value of a call of a function (results which are floating point
        numbers are checked, as in the expressions)"""
        res = self._call(fname,args)
        if ( isinstance(res,list) or res[1] != 'f64' or res.checked
             or fname in ( 'through_sphere', 'through_box' ) ):
            return res
        return self.lang.check_finite(res)

    def _call( self, fname, args ):
        lang = self.lang
        if fname == 'abs' and len(args) == 1 and isinstance(args[0],list):
            #(the length, of floating point numbers also for integers):
            v = [ self.as_float(c) for c in args[0] ]
            return lang.math_call('sqrt',self.dot(v,v))
        if fname in ( 'dot', 'cross', 'angle' ):
            v, w = args
            if fname == 'dot':
                return self.dot(v,w)
            if fname == 'cross':
                sub = lambda i, j : self.binary('-',self.binary('*',v[i],w[j]),self.binary('*',v[j],w[i]))
                return [ sub(1,2), sub(2,0), sub(0,1) ]
            pad = [ lang.float_constant(0.0) ] * ( 3 - len(v) )
            return lang.angle([ self.as_float(c) for c in ( *v, *pad ) ],
                              [ self.as_float(c) for c in ( *w, *pad ) ])
        if fname in ( 'through_sphere', 'through_box' ):
            #(the vector from the position to the center, and the direction):
            center, size = args
            pos, d = self.name('pos'), self.name('dir')
            to_center = [ self.as_float(self.binary('-',c,p)) for c, p in zip(center,pos) ]
            d = [ self.as_float(c) for c in d ]
            if fname == 'through_sphere':
                return lang.through_sphere(to_center,d,self.as_float(size))
            return lang.through_box(to_center,d,[ self.as_float(h) for h in size ])
        ints = all( a[1] != 'f64' for a in args )
        if fname == 'mod':
            if not ints:
                raise MCPLError('mod(a,b) requires integers without units (like userflags or pdgcode)')
            return self.div_mod('mod',*args)
        if fname == 'abs':
            x = args[0]
            if x[1] == 'f64':
                return lang.math_call('fabs',x)
            return lang.int_op('abs',x[1],x) if x[1][0] == 'i' else x
        if fname in _functions_toint:
            x = args[0]
            return x if x[1] != 'f64' else lang.toint(fname,x)
        if fname in ( 'min', 'max', 'clamp' ):
            def pick( a, b, which ):
                if ints:
                    t, x, y = self.int_values(a,b)
                else:
                    ( x, y ), t = ( self.as_float(a), self.as_float(b) ), 'f64'
                return lang.min_max(which,t,x,y)
            if fname == 'clamp':
                v, lo, hi = args
                return pick(pick(v,lo,'max'),hi,'min')
            res = args[0]
            for a in args[1:]:
                res = pick(res,a,fname)
            return res
        if fname == 'hypot':
            #(as in the expressions, the square root of the sum of the squares):
            terms = [ self.binary('*',self.as_float(a),self.as_float(a)) for a in args ]
            res = terms[0]
            for t in terms[1:]:
                res = self.binary('+',res,t)
            return lang.math_call('sqrt',res)
        assert fname == 'sqrt' or fname in _functions_nodim or fname == 'atan2'
        return lang.math_call(fname,*( self.as_float(a) for a in args ))

    #Statements:

    def statements( self, statements ):
        """The lines of code doing what the statements do, for each particle"""
        lines = []
        for st in statements:
            if isinstance(st,Assign):
                value = self(st.value if st.op is None else Binary(st.op,Name(st.target),st.value))
                lines += self.store(st.target,value)
            elif _is_filter(st):
                lines += self.lang.filter(self.scalar(self(st)))
            elif st.name == 'swap':
                lines += self.swap(*( a.id for a in st.args ))
            elif st.name in _rotation_planes:
                angle = lambda node = st.args[0] : self.as_float(self(node))
                lines += self.lang.rotate_plane(st.name,angle,self.name)
            else:
                args = lambda st = st : self.rotation_args(st)
                lines += self.lang.rotate_matrix(st.name,args,self.name)
        return lines

    def rotation_args( self, st ):
        """The arguments of rotate_around and rotate_frame: floating point
        numbers, and lists of three for vectors"""
        res = []
        for a in ( self(a) for a in st.args ):
            assert not isinstance(a,list) or len(a) == 3
            res.append([ self.as_float(c) for c in a ] if isinstance(a,list) else self.as_float(a))
        return res

    def store( self, name, value ):
        """Lines setting the field or variable to the value"""
        lang = self.lang
        if not lang.changes or name not in _assignable:
            lines, self.variables[name] = lang.variable(name,value)
            return lines
        if name in _expr_vectors:
            return lang.set_fields(_expr_vectors[name],[ self.as_float(v) for v in value ])
        if name == 'wavelength':
            return lang.set_wavelength(self.as_float(value))
        if name in _int_field_types:
            return lang.set_field(name,self.int_field(name,value))
        return lang.set_field(name,self.as_float(value))

    def int_field( self, name, value ):
        """The value for pdgcode or userflags, which must be an integer in the
        range of their types"""
        t = _int_field_types[name]
        lo, hi = _int_range(t)
        if value[1] != 'f64' and value.const is not None and lo <= value.const <= hi:
            return value#(constants which fit, like neutron)
        return self.lang.to_int_field(name,t,lo,hi,self.as_float(value))

    def swap( self, a, b ):
        va, vb = self.name(a), self.name(b)
        line, tmp = self.lang.temporary('tmp',va)
        return [ line, *self.store(a,vb), *self.store(b,tmp) ]

def _program_header( tree ):
    """The first comment lines of the generated code"""
    if tree is None:
        return [ 'Code generated by MCPL' ]
    return [ f'Edit: {_expr_ast2str(tree)}', 'Code generated by MCPL from the edit expression above' ]

def _expr_ast2code( lang, tree = None, layout = None, *, filenames = None, skip = 0,
                    limit = None, statsums = None, comment = None ):
    """A program in the language of the provider class lang which writes the
    particles of an MCPL file which an edit keeps, with its changes, to a new
    file (tree is the checked and normalised tree of the edit expression, see
    _expressions, or None), for files with the userdata layout (or None for
    files without userdata). The files are given as arguments of the program,
    or else as filenames (input and output). Only the particles of the range of
    skip and limit (None for all, see _as_limit) are used, the stat:sum
    entries of the output are scaled by the fraction of the particles in the
    range if statsums is 'scaled', or set to -1 (not available) if it is
    'unavailable' (see _statsum_scale), and the comment (if any) is added to
    its header."""
    statements = () if tree is None else tree.statements
    modified = _modified_fields(statements)
    lang = lang(layout,bool(modified))
    body = _Translator(lang).statements(statements)
    return lang.program(_program_header(tree),body,modified,filenames = filenames,skip = skip,
                        limit = limit,statsums = statsums,comment = comment)
