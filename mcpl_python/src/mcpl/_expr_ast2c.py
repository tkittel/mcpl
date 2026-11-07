
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

"""C code doing what edit expressions do (see _expressions): complete programs
reading an MCPL file and writing the particles kept, with their changes, to a
new file. Interface: _expr_ast2c(edit, layout), where layout is the userdata layout
of the files the program is for (or None). The translation of the trees of
expressions (_Translator) is also used for C++ (see _expr_ast2cpp).

Integers work as in the expressions: with the integer types of C, and with
the operations which can fail (overflow, division by zero, and negative
values where they can not be used) done by small helper functions, which stop
the program with an error. Values with units are in the units of MCPL, with
the units of constants in comments."""

__all__ = []

import re

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
    _expr_constants,
    _expr_vectors,
    _functions_nodim,
    _is_condition,
    _rotated_vectors,
    _rotation_planes,
)
from ._exprunits import _quantity_value, _unit_size
from ._particles import _particle_names

#The fields, as members of mcpl_particle_t, and their C types:
_c_members = { 'x' : 'position[0]', 'y' : 'position[1]', 'z' : 'position[2]',
               'ux' : 'direction[0]', 'uy' : 'direction[1]', 'uz' : 'direction[2]',
               'polx' : 'polarisation[0]', 'poly' : 'polarisation[1]',
               'polz' : 'polarisation[2]', 'ekin' : 'ekin', 'time' : 'time',
               'weight' : 'weight', 'pdgcode' : 'pdgcode', 'userflags' : 'userflags' }
_field_types = { 'pdgcode' : 'i32', 'userflags' : 'u32', 'fileidx' : 'i64' }
_ctypes = { 'i32' : 'int32_t', 'u32' : 'uint32_t', 'i64' : 'int64_t', 'u64' : 'uint64_t',
            'f64' : 'double' }
_int_bits = { 'i32' : 32, 'u32' : 32, 'i64' : 64, 'u64' : 64 }
#(the userdata types, after the integer promotions of C):
_ud_types = { 'int8' : 'i32', 'uint8' : 'i32', 'int16' : 'i32', 'uint16' : 'i32',
              'int32' : 'i32', 'uint32' : 'u32', 'int64' : 'i64', 'uint64' : 'u64',
              'float32' : 'f64', 'float64' : 'f64' }
#(the constants of the wavelengths, see _physics):
_wl_unit = 1e-8

def _common_type( a, b ):
    """The type of the result of integers of the types a and b (the usual
    arithmetic conversions of C)"""
    if a == b:
        return a
    ua, ub = a[0] == 'u', b[0] == 'u'
    if ua == ub:
        return a if _int_bits[a] >= _int_bits[b] else b
    u, s = ( a, b ) if ua else ( b, a )
    return u if _int_bits[u] >= _int_bits[s] else s

class _Translator:
    """Translates checked and normalised trees of expressions (see
    _expr_ast2astnorm) to C (lang 'c') or C++ (lang 'cpp'), where field(name)
    gives the code reading a field of the particle. The values are (code,
    type) for numbers, and lists of them for vectors. The helper functions
    used are collected in helpers (by name, in the order they are needed)."""

    def __init__( self, lang, field, layout ):
        self.lang, self.field, self.layout = lang, field, layout
        self.helpers = {}
        self.math = self.uses_fileidx = False
        #(the C names of the variables, and the userdata fields used):
        self.variables, self.userdata = {}, {}
        self._names = set()

    #Code:

    def ctype( self, t ):
        return f'std::{_ctypes[t]}' if self.lang == 'cpp' and t != 'f64' else _ctypes[t]

    def cast( self, code, t ):
        return f'static_cast<{self.ctype(t)}>( {code} )' if self.lang == 'cpp' else f'({_ctypes[t]})( {code} )'

    def fct( self, name, *args ):
        """A call of a function of the math library"""
        self.math = True
        return f'{"std::" if self.lang == "cpp" else ""}{name}( {", ".join(args)} )'

    def error( self, msg ):
        """The statement stopping the program with the message"""
        if self.lang == 'cpp':
            return f'throw std::runtime_error( "{msg}" );'
        return f'fprintf( stderr, "ERROR: {msg}\\n" );\nexit( 1 );'

    def fail( self, cond, msg, indent = '  ' ):
        """Lines stopping the program with the message if cond is true"""
        lines = self.error(msg).split('\n')
        if len(lines) == 1:
            return f'{indent}if ( {cond} )\n{indent}  {lines[0]}\n'
        return ( f'{indent}if ( {cond} ) {{\n' + ''.join( f'{indent}  {l}\n' for l in lines )
                 + f'{indent}}}\n' )

    def helper( self, name, code ):
        """Use the helper function (with the code for the name)"""
        if name not in self.helpers:
            self.helpers[name] = code
        return name

    def new_name( self, base ):
        """A new name for a C variable"""
        name, i = base, 1
        while name in self._names:
            i += 1
            name = f'{base}_{i}'
        self._names.add(name)
        return name

    #Numbers:

    def int_constant( self, v ):
        """An integer constant, typed like in the expressions (int32, then
        int64, then uint64)"""
        if -2**31 <= v < 2**31:
            return ( f'({v+1}-1)' if v == -2**31 else str(v) ), 'i32'
        if -2**63 <= v < 2**63:
            text = f'({v+1}-1)' if v == -2**63 else str(v)
            return ( f'std::int64_t( {text} )' if self.lang == 'cpp' else f'INT64_C( {text} )' ), 'i64'
        if v < 2**64:
            return ( f'std::uint64_t( {v}u )' if self.lang == 'cpp' else f'UINT64_C( {v} )' ), 'u64'
        raise MCPLError(f'The integer {v} is too large (integers must fit in 64 bits)')

    @staticmethod
    def float_constant( v, comment = None ):
        text = repr(float(v))
        return ( text if comment is None else f'{text}/*{comment}*/' ), 'f64'

    def as_float( self, x ):
        return x if x[1] == 'f64' else ( self.cast(x[0],'f64'), 'f64' )

    #Expressions:

    def __call__( self, node ):
        """The value of the node: (code, type), or a list of them for vectors"""
        if isinstance(node,Int):
            return self.int_constant(node.value)
        if isinstance(node,Float):
            return self.float_constant(node.value)
        if isinstance(node,Quantity):
            return self.float_constant(_quantity_value(node.number.value,node.unit,node.power),
                                       _expr_ast2str(node))
        if isinstance(node,Unit):
            return self.float_constant(_unit_size(node.unit,node.power),_expr_ast2str(node))
        if isinstance(node,Particle):
            code, t = self.int_constant(_particle_names[node.name])
            return f'{code}/*{node.name}*/', t
        if isinstance(node,Name):
            return self.name(node.id)
        if isinstance(node,Userdata):
            return self.userdata_value(node)
        if isinstance(node,Vector):
            return [ self.scalar(self(c)) for c in node.components ]
        if isinstance(node,Part):
            v = self(node.vector)
            if not isinstance(v,list) or node.index >= len(v):
                raise MCPLError(f'Not a value of a vector: {_expr_ast2str(node)}')
            return v[node.index]
        if isinstance(node,Logical):
            op = ' && ' if node.op == 'and' else ' || '
            return '( ' + op.join( self.condition(v) for v in node.values ) + ' )', 'i32'
        if isinstance(node,Unary):
            return self.unary(node)
        if isinstance(node,Binary):
            return self.binary(node.op,self(node.left),self(node.right))
        if isinstance(node,Compare):
            terms, left = [], self.scalar(self(node.first))
            for op, v in zip(node.ops,node.values):
                right = self.scalar(self(v))
                terms.append(self.compare(op,left,right))
                left = right
            return ( terms[0] if len(terms) == 1 else '( ' + ' && '.join(terms) + ' )' ), 'i32'
        if isinstance(node,In):
            v = self.scalar(self(node.value))
            terms = [ self.compare('==',v,self(c)) for c in node.values ]
            res = '( ' + ' || '.join(terms) + ' )'
            return ( f'!{res}' if node.negated else res ), 'i32'
        if isinstance(node,Call):
            return self.call(node.name,[ self(a) for a in node.args ])
        raise MCPLError(f'Can not translate {type(node).__name__}')

    @staticmethod
    def scalar( x ):
        if isinstance(x,list):
            raise MCPLError('A vector can not be used here')
        return x

    def condition( self, node ):
        return self.scalar(self(node))[0]

    def name( self, n ):
        if n in self.variables:
            return self.variables[n]
        if n in _expr_vectors:
            return [ self.name(c) for c in _expr_vectors[n] ]
        if n in _expr_constants:
            return self.float_constant(_expr_constants[n],n)
        if n == 'fileidx':
            self.uses_fileidx = True
        if n == 'wavelength':
            self.wavelength_code()
            return f'wavelength( {self.field("ekin")}, {self.field("pdgcode")} )', 'f64'
        return self.field(n), _field_types.get(n,'f64')

    def userdata_value( self, node ):
        from ._expr_eval import _userdata_unit
        from ._userdata import userdata_fields, userdata_units
        fields = { f[0] : f for f in userdata_fields(self.layout) } if self.layout else {}
        if node.field not in fields:
            raise MCPLError(f'No userdata field "{node.field}"'
                            + ( f' (in the layout "{self.layout}")' if self.layout
                                else ' (the particles have no userdata)' ))
        name, ftype, count = fields[node.field]
        if ( node.index is None ) != ( count is None ):
            raise MCPLError(f'The userdata field "{name}" has {count or 1} values per particle')
        if node.index is not None and node.index >= count:
            raise MCPLError(f'The index {node.index} is too large for the userdata field "{name}"')
        self.userdata[name] = ( ftype, count )
        get = self.userdata_get(name,ftype,node.index)
        factor = _userdata_unit(self.layout,name)[0]
        if factor != 1.0:
            #(the unit of the field, in the units of MCPL):
            unit = userdata_units(self.layout)[name]
            return f'{get} * {self.float_constant(factor,unit)[0]}', 'f64'
        return get, _ud_types[ftype]

    def unary( self, node ):
        if node.op == 'not':
            return f'!{self.paren(self.condition(node.operand))}', 'i32'
        x = self(node.operand)
        if node.op == '+':
            return x
        if isinstance(node.operand,Int):
            #(negative integer constants, like -2147483648):
            return self.int_constant(-node.operand.value)
        if isinstance(x,list):
            return [ self.negate(c) for c in x ]
        return self.negate(x)

    @staticmethod
    def paren( code ):
        """The code in parentheses, unless it is a name, a member, or a number"""
        return code if re.fullmatch(r'[\w.]+(\[\d+\])?|\w+->[\w.]+(\[\d+\])?',code) else f'( {code} )'

    def negate( self, x ):
        code, t = x
        if t == 'f64':
            return f'-{self.paren(code)}', t
        return f'{self.int_helper("neg",t)}( {code} )', t

    def nonneg( self, x, t ):
        """The integer x converted to the unsigned type t (checking that it is
        not negative)"""
        if x[1][0] == 'u' or x[0].isdigit():
            return x[0]
        return f'{self.int_helper("as",t)}( {x[0]} )'

    def int_operands( self, a, b ):
        """The common type of integers, and their codes in it"""
        t = _common_type(a[1],b[1])
        if t[0] == 'u':
            return t, self.nonneg(a,t), self.nonneg(b,t)
        return t, a[0], b[0]

    def binary( self, op, a, b ):
        va, vb = isinstance(a,list), isinstance(b,list)
        if va or vb:
            return self.vector_binary(op,a,b)
        ints = a[1] != 'f64' and b[1] != 'f64'
        if op in ( '&', '|' ):
            if not ints:
                raise MCPLError(f'The bitwise operator {op} can only be used with integers')
            t, x, y = self.int_operands(a,b)
            return f'( {x} {op} {y} )', t
        if op == '//':
            if not ints:
                raise MCPLError('The operator // can only be used with integers')
            return self.div_mod('div',a,b)
        if op in ( '+', '-', '*' ) and ints:
            t, x, y = self.int_operands(a,b)
            return f'{self.int_helper({"+" : "add", "-" : "sub", "*" : "mul"}[op],t)}( {x}, {y} )', t
        a, b = self.as_float(a), self.as_float(b)
        if op == '^':
            return self.finite(self.fct('pow',a[0],b[0])), 'f64'
        if op == '/':
            m = re.fullmatch(r'([0-9.e+-]+)(/\*.*\*/)?',b[0])
            if not ( m and float(m.group(1)) != 0.0 ):
                #(divisions which can give NaN or infinite values):
                return self.finite(f'{a[0]} / {b[0]}'), 'f64'
        return f'( {a[0]} {op} {b[0]} )', 'f64'

    def vector_binary( self, op, a, b ):
        va, vb = isinstance(a,list), isinstance(b,list)
        if op in ( '+', '-' ) and va and vb and len(a) == len(b):
            return [ self.binary(op,x,y) for x, y in zip(a,b) ]
        if op == '*' and va != vb:
            return [ self.binary(op,x,b) for x in a ] if va else [ self.binary(op,a,y) for y in b ]
        if op == '/' and va and not vb:
            return [ self.binary(op,x,b) for x in a ]
        if op == '^' and va and not vb and b[0] == '2':
            return self.dot(a,a)
        raise MCPLError(f'Unsupported operation {op} of vectors')

    def div_mod( self, op, a, b ):
        """a // b or mod(a,b), of integers"""
        t, x, y = self.int_operands(a,b)
        if t[0] == 'u' and y.isdigit() and int(y) > 0:
            #(unsigned values divided by a positive constant can not fail):
            return f'( {x} {"/" if op == "div" else "%"} {y} )', t
        return f'{self.int_helper(op,t)}( {x}, {y} )', t

    def compare( self, op, a, b ):
        a, b = self.scalar(a), self.scalar(b)
        if a[1] != 'f64' and b[1] != 'f64':
            _, x, y = self.int_operands(a,b)
            return f'{x} {op} {y}'
        return f'{a[0]} {op} {b[0]}'

    def dot( self, v, w ):
        res = self.binary('*',v[0],w[0])
        for x, y in zip(v[1:],w[1:]):
            res = self.binary('+',res,self.binary('*',x,y))
        return res

    def call( self, fname, args ):
        vector_args = [ isinstance(a,list) for a in args ]
        if fname == 'abs' and len(args) == 1 and vector_args[0]:
            return self.fct('sqrt',self.dot(args[0],args[0])[0]), 'f64'
        if fname in ( 'dot', 'cross', 'angle' ):
            v, w = args
            if fname == 'dot':
                return self.dot(v,w)
            if fname == 'cross':
                sub = lambda i, j : self.binary('-',self.binary('*',v[i],w[j]),self.binary('*',v[j],w[i]))
                return [ sub(1,2), sub(2,0), sub(0,1) ]
            pad = [ ( '0.0', 'f64' ) ] * ( 3 - len(v) )
            self.angle_code()
            comps = [ self.as_float(c)[0] for c in ( *v, *pad, *w, *pad ) ]
            #(NaN for vectors of length zero):
            return self.finite(f'angle( {", ".join(comps)} )'), 'f64'
        if fname == 'through_sphere':
            return self.through_sphere(*args)
        if fname == 'through_box':
            return self.through_box(*args)
        ints = all( a[1] != 'f64' for a in args )
        if fname == 'mod':
            if not ints:
                raise MCPLError('mod(a,b) requires integers without units (like userflags or pdgcode)')
            return self.div_mod('mod',*args)
        if fname == 'abs':
            code, t = args[0]
            if t == 'f64':
                return self.fct('fabs',code), t
            return ( f'{self.int_helper("abs",t)}( {code} )' if t[0] == 'i' else code ), t
        if fname in ( 'round', 'floor', 'ceil' ):
            code, t = args[0]
            if t != 'f64':
                return code, t
            self.toint_code()
            return f'toint( {self.fct("rint" if fname == "round" else fname,code)} )', 'i64'
        if fname in ( 'min', 'max', 'clamp' ):
            def pick( a, b, op ):
                if ints:
                    t, x, y = self.int_operands(a,b)
                    return f'( {x} {op} {y} ? {x} : {y} )', t
                a, b = self.as_float(a), self.as_float(b)
                return f'( {a[0]} {op} {b[0]} ? {a[0]} : {b[0]} )', 'f64'
            if fname == 'clamp':
                v, lo, hi = args
                return pick(pick(v,lo,'>'),hi,'<')
            res = args[0]
            for a in args[1:]:
                res = pick(res,a,'<' if fname == 'min' else '>')
            return res
        if fname == 'hypot':
            #(as in the expressions, the square root of the sum of the squares):
            terms = [ self.binary('*',self.as_float(a),self.as_float(a)) for a in args ]
            res = terms[0]
            for t in terms[1:]:
                res = self.binary('+',res,t)
            return self.fct('sqrt',res[0]), 'f64'
        if fname == 'sqrt' or fname in _functions_nodim or fname == 'atan2':
            res = self.fct(fname,*( self.as_float(a)[0] for a in args ))
            #(functions which can give NaN or infinite values of finite ones):
            return ( self.finite(res) if fname in _risky_functions else res ), 'f64'
        raise MCPLError(f'Unsupported function {fname}')

    def through_sphere( self, center, radius ):
        """Whether the line of flight passes through the sphere (see
        _ExprEvaluator.through_sphere)"""
        pos, d = self.name('pos'), self.name('dir')
        to_center = [ self.binary('-',c,p) for c, p in zip(center,pos) ]
        sub = lambda i, j : self.binary('-',self.binary('*',to_center[i],d[j]),
                                        self.binary('*',to_center[j],d[i]))
        cr = [ sub(1,2), sub(2,0), sub(0,1) ]
        r = self.as_float(radius)
        self.radius_code()
        return f'( {self.dot(cr,cr)[0]} <= radius( {r[0]} ) * radius( {r[0]} ) )', 'i32'

    def through_box( self, center, half ):
        """Whether the line of flight passes through the box (see
        _ExprEvaluator.through_box)"""
        pos, d = self.name('pos'), self.name('dir')
        to_center = [ self.as_float(self.binary('-',c,p))[0] for c, p in zip(center,pos) ]
        args = [ *to_center, *( self.as_float(c)[0] for c in d ),
                 *( self.as_float(h)[0] for h in half ) ]
        return f'{self.box_code()}( {", ".join(args)} )', 'i32'

    #Helper functions (stopping the program with an error, see fail):

    def function( self, name, signature, body ):
        """Use the helper function with the signature (with the name in it,
        as {name}) and the lines of the body"""
        return self.helper(name,f'static {signature.format(name=name)}\n{{\n{body}}}')

    def int_helper( self, op, t ):
        """The checked operation op on integers of type t: add, sub, mul, div
        (as //), mod, neg, abs, or as (a signed integer as the unsigned type
        t, if not negative)"""
        name = f'{op}_{t}'
        T = self.ctype(t)
        bits, signed = _int_bits[t], t[0] == 'i'
        mx, mn, umx = f'INT{bits}_MAX', f'INT{bits}_MIN', f'UINT{bits}_MAX'
        one, two = f'{{name}}( {T} a )', f'{{name}}( {T} a, {T} b )'
        if op == 'as':
            return self.function(f'as_{t}',f'{T} {{name}}( {self.ctype("i64")} a )',
                                 self.fail('a < 0','Negative value') + f'  return {self.cast("a",t)};\n')
        if op == 'neg':
            if signed:
                body = self.fail(f'a == {mn}','Overflow') + '  return -a;\n'
            else:
                body = self.fail('a != 0','Negative value') + '  return 0;\n'
            return self.function(name,f'{T} {one}',body)
        if op == 'abs':
            return self.function(name,f'{T} {one}',self.fail(f'a == {mn}','Overflow')
                                 + '  return a < 0 ? -a : a;\n')
        if op in ( 'div', 'mod' ):
            body = self.fail('a < 0 || b < 0','Negative value') if signed else ''
            body += self.fail('b == 0','Division by zero')
            return self.function(name,f'{T} {two}',body + f'  return a {"/" if op == "div" else "%"} b;\n')
        sym = { 'add' : '+', 'sub' : '-', 'mul' : '*' }[op]
        if bits == 32:
            #(computed in 64 bits, where the results fit):
            wide = 'i64' if signed or op == 'sub' else 'u64'
            check = ( f'r < {mn} || r > {mx}' if signed else 'r < 0' if op == 'sub' else f'r > {umx}' )
            body = ( f'  {self.ctype(wide)} r = {self.cast("a",wide)} {sym} b;\n'
                     + self.fail(check,'Overflow') + f'  return {self.cast("r",t)};\n' )
            return self.function(name,f'{T} {two}',body)
        if op == 'add':
            check = ( f'( b > 0 && a > {mx} - b ) || ( b < 0 && a < {mn} - b )' if signed
                      else f'a > {umx} - b' )
        elif op == 'sub':
            check = ( f'( b < 0 && a > {mx} + b ) || ( b > 0 && a < {mn} + b )' if signed
                      else 'a < b' )
        else:
            check = ( f'a > 0 ? ( b > 0 ? a > {mx} / b : b < {mn} / a )'
                      f' : ( b > 0 ? a < {mn} / b : ( a != 0 && b < {mx} / a ) )' if signed
                      else f'a != 0 && b > {umx} / a' )
        return self.function(name,f'{T} {two}',self.fail(check,'Overflow') + f'  return a {sym} b;\n')

    def finite( self, code ):
        """The code of a floating point number, checked to be finite (as in
        the expressions)"""
        name = self.function('check_finite','double {name}( double v )',
                             self.fail(f'!{self.fct("isfinite","v")}','NaN or infinite value')
                             + '  return v;\n')
        return f'{name}( {code} )'

    def toint_code( self ):
        return self.function('toint',f'{self.ctype("i64")} {{name}}( double v )',
                             self.fail(f'!( {self.fct("fabs","v")} < 4611686018427387904.0 )',
                                       'Value too large for integers')
                             + f'  return {self.cast("v","i64")};\n')

    def radius_code( self ):
        return self.function('radius','double {name}( double r )',
                             self.fail('r < 0.0','Negative radius') + '  return r;\n')

    def box_code( self ):
        """The function of through_box, of the vector r from the position to the
        center, the direction d, and the half dimensions h: whether the parts of
        the line between the two planes of the box along x, y, and z overlap"""
        fabs = self.fct('fabs','r[i]')
        return self.function('through_box','int {name}( double rx, double ry, double rz,\n'
                             '                        double dx, double dy, double dz,\n'
                             '                        double hx, double hy, double hz )',
                             self.fail('hx < 0.0 || hy < 0.0 || hz < 0.0','Negative half dimension')
                             + '  double r[3] = { rx, ry, rz }, d[3] = { dx, dy, dz }, h[3] = { hx, hy, hz };\n'
                             '  double lo = 0.0, hi = 0.0;\n'
                             '  int any = 0;\n'
                             '  for ( int i = 0; i < 3; ++i ) {\n'
                             '    if ( d[i] == 0.0 ) {\n'
                             f'      if ( {fabs} > h[i] )\n'
                             '        return 0;\n'
                             '      continue;\n'
                             '    }\n'
                             '    double t1 = ( r[i] - h[i] ) / d[i], t2 = ( r[i] + h[i] ) / d[i];\n'
                             '    if ( t1 > t2 ) { double t = t1; t1 = t2; t2 = t; }\n'
                             '    if ( !any || t1 > lo ) lo = t1;\n'
                             '    if ( !any || t2 < hi ) hi = t2;\n'
                             '    any = 1;\n'
                             '  }\n'
                             '  return !any || lo <= hi;\n')

    def angle_code( self ):
        sq = lambda e : self.fct('sqrt',e)
        return self.function('angle','double {name}( double ax, double ay, double az,\n'
                             '                     double bx, double by, double bz )',
                             '  /* (precise also for small angles, as in the expressions) */\n'
                             f'  double na = {sq("ax*ax + ay*ay + az*az")}, nb = {sq("bx*bx + by*by + bz*bz")};\n'
                             '  double dx = ax/na - bx/nb, dy = ay/na - by/nb, dz = az/na - bz/nb;\n'
                             '  double sx = ax/na + bx/nb, sy = ay/na + by/nb, sz = az/na + bz/nb;\n'
                             f'  return 2.0 * {self.fct("atan2",sq("dx*dx + dy*dy + dz*dz"),sq("sx*sx + sy*sy + sz*sz"))};\n')

    def wavelength_code( self ):
        from .constants import hc_eV_Aa, neutron_mass_energy
        return self.function('wavelength',f'double {{name}}( double ekin, {self.ctype("i32")} pdgcode )',
                             '  /* (in cm, of neutrons and gammas) */\n'
                             + self.fail('pdgcode != 2112 && pdgcode != 22',
                                         'The wavelength is only defined for neutrons and gammas')
                             + self.fail('!( ekin > 0.0 )','The wavelength is infinite for zero kinetic energy')
                             + '  double pc = pdgcode == 22 ? ekin : '
                             + self.fct('sqrt',f'ekin * ( ekin + 2 * {neutron_mass_energy!r} )') + ';\n'
                             + f'  return {hc_eV_Aa!r} * 1e-6 / pc * {_wl_unit!r};\n')

    def ekin_code( self ):
        from .constants import hc_eV_Aa, neutron_mass_energy
        mc2 = repr(neutron_mass_energy)
        return self.function('ekin_of_wavelength',
                             f'double {{name}}( double wl, {self.ctype("i32")} pdgcode )',
                             '  /* (of a wavelength in cm, for neutrons and gammas) */\n'
                             + self.fail('pdgcode != 2112 && pdgcode != 22',
                                         'The wavelength can only be set for neutrons and gammas')
                             + self.fail('!( wl > 0.0 )','The wavelength must be positive')
                             + f'  double pc = {hc_eV_Aa!r} * 1e-6 / ( wl / {_wl_unit!r} );\n'
                             + '  if ( pdgcode == 22 )\n    return pc;\n'
                             + f'  return pc * pc / ( {self.fct("sqrt",f"pc * pc + {mc2}*{mc2}")} + {mc2} );\n')

    def exact_cos_sin_code( self ):
        f = self.fct
        return self.function('exact_cos_sin','void {name}( double a, double * c, double * s )',
                             '  /* (exact for multiples of 90 degrees, as in the expressions) */\n'
                             '  double q = a / ( 0.5 * 3.141592653589793 );\n'
                             f'  double k = {f("rint","q")};\n'
                             f'  if ( {f("fabs","q - k")} <= 8 * 2.220446049250313e-16 * ( {f("fabs","k")} > 1.0 ? {f("fabs","k")} : 1.0 ) ) {{\n'
                             f'    int kq = {self.cast(f("fmod","k","4.0"),"i32")};\n'
                             '    if ( kq < 0 )\n      kq += 4;\n'
                             '    *c = kq == 0 ? 1.0 : ( kq == 2 ? -1.0 : 0.0 );\n'
                             '    *s = kq == 1 ? 1.0 : ( kq == 3 ? -1.0 : 0.0 );\n'
                             '  } else {\n'
                             f'    *c = {f("cos","a")};\n    *s = {f("sin","a")};\n  }}\n')

    def rotation_matrix_code( self, fname ):
        """The helpers of rotate_around or rotate_frame (see _rotation_matrix)"""
        f, sq = self.fct, lambda e : self.fct('sqrt',e)
        self.function('unit_vector','int {name}( const double * v, double * u )',
                      f'  double n = {sq("v[0]*v[0] + v[1]*v[1] + v[2]*v[2]")};\n'
                      '  if ( !( n > 0.0 && n <= 1.7976931348623157e308 ) )\n    return 0;\n'
                      '  u[0] = v[0] / n;\n  u[1] = v[1] / n;\n  u[2] = v[2] / n;\n  return 1;\n')
        self.function('exact_matrix','void {name}( double * R )',
                      '  /* (elements within 1e-15 of 0 or +-1 are exact) */\n'
                      '  for ( int i = 0; i < 9; ++i ) {\n'
                      f'    if ( {f("fabs","R[i]")} <= 1e-15 )\n      R[i] = 0.0;\n'
                      f'    if ( {f("fabs","R[i] - 1.0")} <= 1e-15 )\n      R[i] = 1.0;\n'
                      f'    if ( {f("fabs","R[i] + 1.0")} <= 1e-15 )\n      R[i] = -1.0;\n  }}\n')
        if fname == 'rotate_around':
            self.exact_cos_sin_code()
            return self.function('rotate_around','void {name}( const double * axis, double angle, double * R )',
                                 '  double k[3], c, s;\n'
                                 + self.fail('!unit_vector( axis, k )','In rotate_around(..), the axis must not be zero')
                                 + '  exact_cos_sin( angle, &c, &s );\n'
                                 '  double cr[9] = { 0.0, -k[2], k[1], k[2], 0.0, -k[0], -k[1], k[0], 0.0 };\n'
                                 '  for ( int i = 0; i < 3; ++i )\n'
                                 '    for ( int j = 0; j < 3; ++j )\n'
                                 '      R[3*i+j] = c * ( i == j ? 1.0 : 0.0 ) + s * cr[3*i+j] + ( 1.0 - c ) * k[i] * k[j];\n'
                                 '  exact_matrix( R );\n')
        self.function('frame','void {name}( const double * e1, const double * w, double * E )',
                      '  /* (the columns e1, e2, and e1 x e2) */\n'
                      '  double d = w[0]*e1[0] + w[1]*e1[1] + w[2]*e1[2];\n'
                      '  double e2[3] = { w[0] - d * e1[0], w[1] - d * e1[1], w[2] - d * e1[2] };\n'
                      f'  double n = {sq("e2[0]*e2[0] + e2[1]*e2[1] + e2[2]*e2[2]")};\n'
                      '  e2[0] /= n;\n  e2[1] /= n;\n  e2[2] /= n;\n'
                      '  double e3[3] = { e1[1]*e2[2] - e1[2]*e2[1], e1[2]*e2[0] - e1[0]*e2[2],\n'
                      '                   e1[0]*e2[1] - e1[1]*e2[0] };\n'
                      '  for ( int i = 0; i < 3; ++i ) {\n'
                      '    E[3*i] = e1[i];\n    E[3*i+1] = e2[i];\n    E[3*i+2] = e3[i];\n  }\n')
        self.function('cross_norm','double {name}( const double * a, const double * b )',
                      '  double c0 = a[1]*b[2] - a[2]*b[1], c1 = a[2]*b[0] - a[0]*b[2], c2 = a[0]*b[1] - a[1]*b[0];\n'
                      f'  return {sq("c0*c0 + c1*c1 + c2*c2")};\n')
        return self.function('rotate_frame','void {name}( const double * v0, const double * vo0,\n'
                             '                          const double * u0, const double * uo0, double * R )',
                             '  double v[3], vo[3], u[3], uo[3], E[9], F[9];\n'
                             + self.fail('!unit_vector( v0, v ) || !unit_vector( vo0, vo ) || !unit_vector( u0, u )'
                                         ' || !unit_vector( uo0, uo )','In rotate_frame(..), the vectors must not be zero')
                             + self.fail('cross_norm( v, u ) <= 1e-6','In rotate_frame(..), v and u must not be parallel')
                             + self.fail('cross_norm( vo, uo ) <= 1e-6',
                                         'In rotate_frame(..), vout and uout must not be parallel')
                             + self.fail(f'{f("fabs","( v[0]*u[0] + v[1]*u[1] + v[2]*u[2] ) - ( vo[0]*uo[0] + vo[1]*uo[1] + vo[2]*uo[2] )")} > 1e-6',
                                         'In rotate_frame(..), the angle between v and u must be that between vout and uout')
                             + '  frame( v, u, E );\n  frame( vo, uo, F );\n'
                             '  /* (R = F E^T) */\n'
                             '  for ( int i = 0; i < 3; ++i )\n'
                             '    for ( int j = 0; j < 3; ++j )\n'
                             '      R[3*i+j] = F[3*i]*E[3*j] + F[3*i+1]*E[3*j+1] + F[3*i+2]*E[3*j+2];\n'
                             '  exact_matrix( R );\n')

    #Userdata:

    def userdata_get( self, name, ftype, index ):
        """The code getting a value of a userdata field (see the program
        writers)"""
        off = f'offset_{name}'
        if index is not None:
            off = f'{off} + {index} * {_ud_sizes[ftype]}'
        return f'mcpl_userdata_get_{ftype}( ud, {off} )'

#(the functions which can give NaN or infinite values of finite values):
_risky_functions = ( 'sqrt', 'exp', 'log', 'log10', 'asin', 'acos' )
#(the sizes of the userdata types, in bytes):
_ud_sizes = { 'int8' : 1, 'uint8' : 1, 'int16' : 2, 'uint16' : 2, 'int32' : 4, 'uint32' : 4,
              'int64' : 8, 'uint64' : 8, 'float32' : 4, 'float64' : 8 }

class _Statements:
    """The C or C++ statements of the statements of edit expressions (with
    the translator tr, of particles whose fields are set by set_field(name,
    code, op = ''), with op for op=, or None if no fields are changed), where
    a condition skips the particles for which it is false"""

    def __init__( self, tr, set_field ):
        self.tr, self.set_field = tr, set_field

    def __call__( self, statements ):
        lines = []
        for st in statements:
            if isinstance(st,Assign):
                lines += self.assign(st)
            elif _is_condition(st):
                lines += [ f'if ( !( {self.tr.condition(st)} ) )', '  continue;' ]
            elif st.name == 'swap':
                lines += self.swap(*( a.id for a in st.args ))
            else:
                lines += self.rotate(st)
        return lines

    def variable( self, name, value ):
        """Lines declaring a new C variable (or three, for vectors) for the
        value of the variable"""
        tr = self.tr
        if isinstance(value,list):
            names = [ tr.new_name(f'{name}_{"xyz"[i]}') for i in range(len(value)) ]
            tr.variables[name] = [ ( n, t ) for n, ( _, t ) in zip(names,value) ]
            return [ f'{tr.ctype(t)} {n} = {c};' for n, ( c, t ) in zip(names,value) ]
        n = tr.new_name(name)
        tr.variables[name] = ( n, value[1] )
        return [ f'{tr.ctype(value[1])} {n} = {value[0]};' ]

    def assign( self, st ):
        tr, name = self.tr, st.target
        if ( self.set_field is not None and st.op in ( '+', '-', '*', '/' )
             and name in _c_members and name not in _field_types ):
            #(as in x += 1cm, for the fields of floating point numbers):
            value = tr.scalar(tr(st.value))
            return [ self.set_field(name,tr.as_float(value)[0],st.op) ]
        value = tr(st.value if st.op is None else Binary(st.op,Name(name),st.value))
        return self.store(name,value)

    def store( self, name, value ):
        """Lines setting the field or variable to the value (code, type)"""
        tr = self.tr
        if self.set_field is None or name not in ( *_c_members, 'wavelength', *_expr_vectors ):
            return self.variable(name,value)
        if name in _expr_vectors:
            #(all values first, as they can use the vector):
            comps = _expr_vectors[name]
            tmp = [ tr.new_name(f'new_{c}') for c in comps ]
            return ( [ f'double {n} = {tr.as_float(v)[0]};' for n, v in zip(tmp,value) ]
                     + [ self.set_field(c,n) for c, n in zip(comps,tmp) ] )
        if name == 'wavelength':
            tr.ekin_code()
            return [ self.set_field('ekin',f'ekin_of_wavelength( {tr.as_float(value)[0]},'
                                    f' {tr.field("pdgcode")} )') ]
        if name in _field_types:
            return [ self.set_field(name,self.int_field(name,value)) ]
        return [ self.set_field(name,tr.as_float(value)[0]) ]

    def int_field( self, name, value ):
        """The code of a value for pdgcode or userflags, which must be an
        integer in the range of their types"""
        tr = self.tr
        t = _field_types[name]
        T = tr.ctype(t)
        lo, hi = ( '-2147483648.0', '2147483647.0' ) if t == 'i32' else ( '0.0', '4294967295.0' )
        m = re.fullmatch(r'(-?\d+)(/\*\w+\*/)?',value[0])
        if value[1] != 'f64' and m and float(lo) <= int(m.group(1)) <= float(hi):
            return value[0]#(constants which fit, like neutron)
        fname = tr.function(f'to_{name}',f'{T} {{name}}( double v )',
                            tr.fail(f'!( v >= {lo} && v <= {hi} ) || v != {tr.fct("floor","v")}',
                                    f'Values of {name} must be integers from {lo[:-2]} to {hi[:-2]}')
                            + f'  return {tr.cast("v",t)};\n')
        return f'{fname}( {tr.as_float(value)[0]} )'

    def swap( self, a, b ):
        tr = self.tr
        va, vb = tr.name(a), tr.name(b)
        tmp = tr.new_name('tmp')
        return ( [ f'{tr.ctype(va[1])} {tmp} = {va[0]};' ] + self.store(a,vb)
                 + self.store(b,( tmp, va[1] )) )

    def rotate( self, st ):
        tr = self.tr
        if st.name in _rotation_planes:
            tr.exact_cos_sin_code()
            c, s = tr.new_name('c'), tr.new_name('s')
            lines = [ f'double {c}, {s};', f'exact_cos_sin( {tr.as_float(tr(st.args[0]))[0]}, &{c}, &{s} );' ]
            for a, b in _rotation_planes[st.name]:
                va, vb = tr.name(a)[0], tr.name(b)[0]
                ta, tb = tr.new_name(f'old_{a}'), tr.new_name(f'old_{b}')
                lines += [ f'double {ta} = {va}, {tb} = {vb};',
                           self.set_field(a,f'{c} * {ta} - {s} * {tb} + 0.0'),
                           self.set_field(b,f'{s} * {ta} + {c} * {tb} + 0.0') ]
            return lines
        tr.rotation_matrix_code(st.name)
        R = tr.new_name('R')
        args = [ tr(a) for a in st.args ]
        lines = [ f'double {R}[9];' ]
        names = []
        for i, a in enumerate(args):
            if isinstance(a,list):
                if len(a) != 3:
                    raise MCPLError(f'{st.name}(..) takes 3D vectors')
                n = tr.new_name(f'arg{i}')
                lines.append(f'double {n}[3] = {{ {", ".join( tr.as_float(c)[0] for c in a )} }};')
                names.append(n)
            else:
                names.append(tr.as_float(a)[0])
        lines.append(f'{st.name}( {", ".join(names)}, {R} );')
        for comps in _rotated_vectors:
            old = [ tr.new_name(f'old_{c}') for c in comps ]
            lines.append('double ' + ', '.join( f'{o} = {tr.name(c)[0]}' for o, c in zip(old,comps) ) + ';')
            for i, c in enumerate(comps):
                terms = ' + '.join( f'{R}[{3*i+j}] * {old[j]}' for j in range(3) )
                lines.append(self.set_field(c,f'{terms} + 0.0'))
        return lines

#The fields which can have universal values in files (which edits can not
#change):
_universal_fields = ( 'pdgcode', 'weight' )

def _universal_checks( tr, edit, value ):
    """Lines checking that the edit does not change fields with universal
    values (value(field) is the code of the edited value), which the edits
    refuse, as files only store the universal values"""
    lines = []
    for f in _universal_fields:
        if f in edit.modified_fields:
            lines += tr.fail(f'universal_{f} && {value(f)} != universal_{f}',
                             f'The {f} can not be changed in files with a universal {f}',
                             indent = '').rstrip('\n').split('\n')
    return lines

def _program_header( edit ):
    """The first comment lines of the generated code"""
    return ( [] if edit is None else [ f'Edit: {edit.expression}' ] ) + [
        'Code auto-generated by MCPL from above expression' ]

def _c_string( text ):
    """The text as a string of C and C++"""
    return '"' + text.replace('\\','\\\\').replace('"','\\"') + '"'

def _expr_ast2c( edit = None, layout = None, *, filenames = None, skip = 0,
                 limit = None, mark_statsums = False, comment = None ):
    """A C program which writes the particles of an MCPL file which the edit
    keeps, with its changes, to a new file (the edit is a ParticleEdit or a
    text, or None), for files with the userdata layout (or None for files
    without userdata). The
    files are given as arguments of the program, or else as filenames (input
    and output). Only the particles of the range of skip and limit (as in
    mcpltool -s and -l) are used, the stat:sum entries of the output are
    marked as not available if mark_statsums is set, and the comment (if
    any) is added to its header."""
    from ._expressions import _as_edit
    edit = _as_edit(edit)
    changes = edit is not None and bool(edit.modified_fields)
    pin = lambda n : 'fileidx' if n == 'fileidx' else f'p_in->{_c_members[n]}'
    tr = _Translator('c',pin,layout)
    body, set_field = [], None
    if changes:
        body.append('mcpl_particle_t p = *p_in;')
        tr.field = lambda n : 'fileidx' if n == 'fileidx' else f'p.{_c_members[n]}'
        set_field = lambda n, code, op = '' : f'p.{_c_members[n]} {op}= {code};'
    if edit is not None:
        body += _Statements(tr,set_field)(edit._tree.statements)
    if changes:
        body += _universal_checks(tr,edit,lambda f : f'p.{_c_members[f]}')
        body.append('mcpl_add_particle_with_userdata( fo, &p, ud );' if layout
                    else 'mcpl_add_particle( fo, &p );')
    else:
        body.append('mcpl_transfer_last_read_particle( fi, fo );')
    out = [ f'/* {line} */' for line in _program_header(edit) ]
    out += [ '', '#include "mcpl.h"' ]
    if tr.math:
        out.append('#include <math.h>')
    out += [ '#include <stdio.h>', '#include <stdlib.h>' ]
    for code in tr.helpers.values():
        out += [ '', *code.split('\n') ]
    if filenames is None:
        out += [ '', 'int main( int argc, char ** argv )', '{',
                 '  if ( argc != 3 ) {',
                 '    printf( "Usage: %s INPUT.mcpl OUTPUT.mcpl\\n", argv[0] );',
                 '    return 1;', '  }' ]
        names = ( 'argv[1]', 'argv[2]' )
    else:
        out += [ '', 'int main( void )', '{' ]
        names = tuple( _c_string(str(f)) for f in filenames )
    out += [ f'  mcpl_file_t fi = mcpl_open_file( {names[0]} );',
             f'  mcpl_outfile_t fo = mcpl_create_outfile( {names[1]} );',
             '  mcpl_transfer_metadata( fi, fo );' ]
    if comment is not None:
        out.append(f'  mcpl_hdr_add_comment( fo, {_c_string(comment)} );')
    if mark_statsums:
        out.append('  mcpl_hdr_scale_stat_sums( fo, -1.0 );  /* stat:sum entries not available */')
    if skip:
        out.append(f'  mcpl_seek( fi, {skip} );')
    if tr.userdata:
        out.append('  const char * layout = mcpl_hdr_userdata_layout( fi );')
        for name, ( ftype, count ) in tr.userdata.items():
            t = ftype + ( f'[{count}]' if count is not None else '' )
            out.append(f'  const uint32_t offset_{name} = mcpl_userdata_offset( layout, "{name}", "{t}" );')
    for f in _universal_fields:
        if changes and f in edit.modified_fields:
            t = 'int32_t' if f == 'pdgcode' else 'double'
            out.append(f'  const {t} universal_{f} = mcpl_hdr_universal_{f}( fi );')
    out.append('  const mcpl_particle_t * p_in;')
    if layout:
        out.append('  const uint8_t * ud;')
    read = 'mcpl_read_with_userdata( fi, &ud )' if layout else 'mcpl_read( fi )'
    if limit or tr.uses_fileidx:
        #(the particles are counted, from the first one of the range):
        cond = f'n < {limit} && ' if limit else ''
        out.append(f'  for ( uint64_t n = 0; {cond}( p_in = {read} ); ++n ) {{')
        if tr.uses_fileidx:
            body.insert(0,f'const int64_t fileidx = (int64_t)( {f"{skip} + " if skip else ""}n );')
    else:
        out.append(f'  while ( ( p_in = {read} ) ) {{')
    out += [ f'    {line}' for line in body ]
    out += [ '  }', '  mcpl_close_outfile( fo );', '  mcpl_close_file( fi );', '  return 0;', '}' ]
    return '\n'.join(out) + '\n'
