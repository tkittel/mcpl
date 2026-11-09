
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
new file. Interface: _expr_ast2c(tree, layout), where tree is the checked
and normalised tree of an edit expression (see _edit_code in _expressions)
and layout is the userdata layout of the files the program is for (or
None). The translation of the trees of expressions (_Translator) is also
used for C++ (see _expr_ast2cpp).

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
    _common_int_type,
    _expr_constants,
    _expr_vector_names,
    _expr_vectors,
    _expr_wl_unit,
    _functions_nodim,
    _functions_toint,
    _int_bits,
    _int_constant_type,
    _int_field_types,
    _int_range,
    _is_filter,
    _is_square,
    _modified_fields,
    _rotated_vectors,
    _rotation_planes,
    _userdata_field,
    _value_type,
)
from ._exprunits import _quantity_value, _unit_size
from ._particles import _particle_names
from ._userdata import _types as _userdata_types

#The fields, as members of mcpl_particle_t, and their C types:
_c_members = { **{ c : f'{_expr_vector_names[v]}[{i}]' for v, comps in _expr_vectors.items()
                   for i, c in enumerate(comps) },
               **{ f : f for f in ( 'ekin', 'time', 'weight', 'pdgcode', 'userflags' ) } }
_ctypes = { 'i32' : 'int32_t', 'u32' : 'uint32_t', 'i64' : 'int64_t', 'u64' : 'uint64_t',
            'f64' : 'double' }

#The generated code stays within _width columns where it can: long lines are
#broken after the operators && and || (marked with _BRK, one operand per
#line), then where still needed after other operators and commas (marked
#with _BRK2), and last after the opening parentheses of calls (_BRK3), see
#_layout; long comments and strings are split at spaces:
_width = 100
_BRK, _BRK2, _BRK3 = '\x00', '\x01', '\x02'
_ARGSEP = ', ' + _BRK2

def _unmarked( line ):
    return line.replace(_BRK,'').replace(_BRK2,'').replace(_BRK3,'')

def _marked( line ):
    """The line, with the places after commas, &&, and || (outside of strings
    and comments) also marked with _BRK2"""
    res, quoted, i = [], False, 0
    while i < len(line):
        if not quoted and line.startswith('/*',i):
            end = line.find('*/',i) + 2
            res.append(line[i:end])
            i = end
            continue
        ch = line[i]
        quoted = quoted != ( ch == '"' and line[i-1:i] != '\\' )
        res.append(ch)
        i += 1
        if ( not quoted and line[i:i+1] not in ( _BRK, _BRK2, _BRK3 )
             and any( line.startswith(s,i-len(s)) for s in ( ', ', '&& ', '|| ' ) ) ):
            res.append(_BRK2)
    return ''.join(res)

def _fill( line, marks, indent ):
    """The line, broken where needed at the places marked with the first of
    the marks (as many parts on each line as fit), and parts which are still
    too long at those of the next marks"""
    if len(_unmarked(line)) <= _width or not marks:
        return [ _unmarked(line) ]
    lines, cur = [], ''
    for piece in line.split(marks[0]):
        if cur.strip() and len(_unmarked(cur + piece.rstrip())) > _width:
            lines.append(cur.rstrip())
            cur = indent + piece
        else:
            cur += piece
    lines.append(cur.rstrip())
    return [ done for part in lines for done in _fill(part,marks[1:],indent) ]

def _layout( lines ):
    """The lines of code, with those longer than _width columns broken at the
    places marked with _BRK (one part on each line), and then where still
    needed at those marked with _BRK2 and _BRK3 (the continuation lines
    indented 4 columns more), and the marks removed. Long lines are also
    marked after commas, &&, and || (see _marked)."""
    res = []
    for line in lines:
        if len(_unmarked(line)) <= _width:
            res.append(_unmarked(line))
            continue
        line = _marked(line)
        indent = ' ' * ( len(line) - len(line.lstrip()) + 4 )
        first, *more = line.split(_BRK)
        for part in [ first ] + [ indent + p for p in more ]:
            res += _fill(part,( _BRK2, _BRK3 ),indent)
    return res

def _split_text( text, width, anywhere = False ):
    """The text in parts of at most width characters (where possible, or
    always with anywhere), split after spaces and semicolons (or anywhere in
    longer words, with anywhere), so they join to the text"""
    parts, cur = [], ''
    for word in re.split(r'(?<=[ ;])',text):
        if cur and len(cur) + len(word.rstrip()) > width and not ( anywhere and len(word) > width ):
            parts.append(cur)
            cur = ''
        cur += word
        while anywhere and len(cur) > width:
            parts.append(cur[:width])
            cur = cur[width:]
    return parts + [ cur ]

def _comment_lines( text, first, more, end = '' ):
    """Comment lines with the text, after first on the first line, and more
    on the others (as /* and *, or //), split at spaces and semicolons"""
    parts = [ p.rstrip() for p in _split_text(text,_width - len(more) - len(end)) ]
    lines = [ first + parts[0] ] + [ more + p for p in parts[1:] ]
    lines[-1] += end
    return lines

def _string_call( start, text, end, indent = 0 ):
    """The line(s) of a call with a string argument (start ends with the
    opening parenthesis), split in adjacent C strings if long (see
    _split_text), for lines indented by indent more columns"""
    width = _width - indent
    line = f'{start}{_c_string(text)}{end}'
    if len(line) <= width:
        return [ line ]
    pad = ' ' * len(start)
    parts = [ _c_string(p) for p in _split_text(text,width - len(start) - len(end) - 4,True) ]
    return ( [ start + parts[0] ] + [ pad + p for p in parts[1:-1] ] + [ pad + parts[-1] + end ] )

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
        return f'{"std::" if self.lang == "cpp" else ""}{name}( {_BRK3}{_ARGSEP.join(args)} )'

    def error( self, msg ):
        """The statement stopping the program with the message"""
        if self.lang == 'cpp':
            return '\n'.join(_string_call('throw std::runtime_error( ',msg,' );',10))
        return '\n'.join(_string_call('fprintf( stderr, ',f'ERROR: {msg}\n',' );',10) + [ 'exit( 1 );' ])

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
        """An integer constant, typed like in the expressions (see
        _int_constant_type)"""
        t = _int_constant_type(v)
        if t is None:
            raise MCPLError(f'The integer {v} is too large (integers must fit in 64 bits)')
        if t == 'i32':
            return ( f'({v+1}-1)' if v == -2**31 else str(v) ), t
        if self.lang == 'cpp':
            text = f'({v+1}-1)' if v == -2**63 else f'{v}u' if t == 'u64' else str(v)
            return f'std::{_ctypes[t]}( {text} )', t
        #(the smallest int64 as (-INT64_C(...)-1), as INT64_C only takes literals):
        if v == -2**63:
            return f'(-INT64_C( {2**63-1} )-1)', t
        return f'{"INT64_C" if t == "i64" else "UINT64_C"}( {v} )', t

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
            return '( ' + ( op + _BRK ).join( self.condition(v) for v in node.values ) + ' )', 'i32'
        if isinstance(node,Unary):
            return self.unary(node)
        if isinstance(node,Binary):
            left = self(node.left)
            if node.op == '^' and isinstance(left,list) and _is_square(node.right):
                return self.dot(left,left)
            return self.binary(node.op,left,self(node.right))
        if isinstance(node,Compare):
            terms, left = [], self.scalar(self(node.first))
            for op, v in zip(node.ops,node.values):
                right = self.scalar(self(v))
                terms.append(self.compare(op,left,right))
                left = right
            return ( terms[0] if len(terms) == 1 else '( ' + f' && {_BRK}'.join(terms) + ' )' ), 'i32'
        if isinstance(node,In):
            v = self.scalar(self(node.value))
            terms = [ self.compare('==',v,self(c)) for c in node.values ]
            res = '( ' + f' || {_BRK}'.join(terms) + ' )'
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
        if n in _int_field_types:
            return self.field(n), _int_field_types[n]
        #(checked for each use, as in the expressions):
        return self.finite(self.field(n)), 'f64'

    def userdata_value( self, node ):
        from ._userdata import userdata_units
        name = node.field
        ftype, count, factor, _ = _userdata_field(self.layout,name,node.index)
        self.userdata[name] = ( ftype, count )
        get = self.userdata_get(name,ftype,node.index)
        if factor != 1.0:
            #(the unit of the field, in the units of MCPL):
            unit = userdata_units(self.layout)[name]
            return f'{get} * {self.float_constant(factor,unit)[0]}', 'f64'
        return get, _value_type(ftype)

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
        """The code in parentheses, unless it is one term already (without
        spaces outside of parentheses, like x, f( a, b ), 2.0/*2cm*/, or
        ( a + b ); comments have no spaces)"""
        depth = 0
        for ch in _unmarked(code):
            depth += { '(' : 1, ')' : -1 }.get(ch,0)
            if ch == ' ' and depth == 0:
                return f'( {code} )'
        return code

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
        t = _common_int_type(a[1],b[1])
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
            return f'{self.int_helper({"+" : "add", "-" : "sub", "*" : "mul"}[op],t)}( {x}, {_BRK2}{y} )', t
        a, b = self.as_float(a), self.as_float(b)
        if op == '^':
            return self.finite(self.fct('pow',a[0],b[0])), 'f64'
        #(all results checked, as in the expressions):
        return self.finite(f'{self.paren(a[0])} {op} {_BRK2}{self.paren(b[0])}'), 'f64'

    def vector_binary( self, op, a, b ):
        va, vb = isinstance(a,list), isinstance(b,list)
        if op in ( '+', '-' ) and va and vb and len(a) == len(b):
            return [ self.binary(op,x,y) for x, y in zip(a,b) ]
        if op == '*' and va != vb:
            return [ self.binary(op,x,b) for x in a ] if va else [ self.binary(op,a,y) for y in b ]
        if op == '/' and va and not vb:
            return [ self.binary(op,x,b) for x in a ]
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
            return f'{self.paren(x)} {op} {self.paren(y)}'
        return f'{self.paren(a[0])} {op} {self.paren(b[0])}'

    def dot( self, v, w ):
        res = self.binary('*',v[0],w[0])
        for x, y in zip(v[1:],w[1:]):
            res = self.binary('+',res,self.binary('*',x,y))
        return res

    def call( self, fname, args ):
        """The value of a call of a function (results which are floating point
        numbers are checked, as in the expressions)"""
        res = self._call(fname,args)
        if isinstance(res,list) or res[1] != 'f64' or fname in ( 'through_sphere', 'through_box' ):
            return res
        return ( res[0] if res[0].startswith('check_finite(') else self.finite(res[0]) ), 'f64'

    def _call( self, fname, args ):
        vector_args = [ isinstance(a,list) for a in args ]
        if fname == 'abs' and len(args) == 1 and vector_args[0]:
            #(the length, of floating point numbers also for integers):
            v = [ self.as_float(c) for c in args[0] ]
            return self.fct('sqrt',self.dot(v,v)[0]), 'f64'
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
            return f'angle( {_ARGSEP.join(comps)} )', 'f64'
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
        if fname in _functions_toint:
            code, t = args[0]
            if t != 'f64':
                return code, t
            self.toint_code()
            return f'toint( {self.fct("rint" if fname == "round" else fname,code)} )', 'i64'
        if fname in ( 'min', 'max', 'clamp' ):
            def pick( a, b, which ):
                if ints:
                    t, x, y = self.int_operands(a,b)
                else:
                    ( x, t ), ( y, _ ) = self.as_float(a), self.as_float(b)
                return f'{self.min_max_code(which,t)}( {x}, {_BRK2}{y} )', t
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
            return self.fct('sqrt',res[0]), 'f64'
        if fname == 'sqrt' or fname in _functions_nodim or fname == 'atan2':
            return self.fct(fname,*( self.as_float(a)[0] for a in args )), 'f64'
        raise MCPLError(f'Unsupported function {fname}')

    def through_sphere( self, center, radius ):
        """Whether the line of flight passes through the sphere (see
        _ExprEvaluator.through_sphere)"""
        pos, d = self.name('pos'), self.name('dir')
        to_center = [ self.as_float(self.binary('-',c,p))[0] for c, p in zip(center,pos) ]
        args = [ *to_center, *( self.as_float(c)[0] for c in d ), self.as_float(radius)[0] ]
        return f'{self.sphere_code()}( {_ARGSEP.join(args)} )', 'i32'

    def through_box( self, center, half ):
        """Whether the line of flight passes through the box (see
        _ExprEvaluator.through_box)"""
        pos, d = self.name('pos'), self.name('dir')
        to_center = [ self.as_float(self.binary('-',c,p))[0] for c, p in zip(center,pos) ]
        args = [ *to_center, *( self.as_float(c)[0] for c in d ),
                 *( self.as_float(h)[0] for h in half ) ]
        return f'{self.box_code()}( {_ARGSEP.join(args)} )', 'i32'

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
                                 self.fail('a < 0','Negative integer value') + f'  return {self.cast("a",t)};\n')
        if op == 'neg':
            if signed:
                body = self.fail(f'a == {mn}','Integer overflow') + '  return -a;\n'
            else:
                body = self.fail('a != 0','Negative integer value') + '  return 0;\n'
            return self.function(name,f'{T} {one}',body)
        if op == 'abs':
            return self.function(name,f'{T} {one}',self.fail(f'a == {mn}','Integer overflow')
                                 + '  return a < 0 ? -a : a;\n')
        if op in ( 'div', 'mod' ):
            body = self.fail('a < 0 || b < 0','Negative integer value') if signed else ''
            body += self.fail('b == 0','Division by zero')
            return self.function(name,f'{T} {two}',body + f'  return a {"/" if op == "div" else "%"} b;\n')
        sym = { 'add' : '+', 'sub' : '-', 'mul' : '*' }[op]
        if bits == 32:
            #(computed in 64 bits, where the results fit):
            wide = 'i64' if signed or op == 'sub' else 'u64'
            check = ( f'r < {mn} || r > {mx}' if signed else 'r < 0' if op == 'sub' else f'r > {umx}' )
            body = ( f'  {self.ctype(wide)} r = {self.cast("a",wide)} {sym} b;\n'
                     + self.fail(check,'Integer overflow') + f'  return {self.cast("r",t)};\n' )
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
        return self.function(name,f'{T} {two}',self.fail(check,'Integer overflow') + f'  return a {sym} b;\n')

    def finite( self, code ):
        """The code of a floating point number, checked to be finite (as in
        the expressions)"""
        name = self.function('check_finite','double {name}( double v )',
                             self.fail(f'!{self.fct("isfinite","v")}','NaN or infinite value')
                             + '  return v;\n')
        return f'{name}( {_BRK3}{code} )'

    def min_max_code( self, which, t ):
        """The function giving the smaller (which is 'min') or larger ('max')
        of two numbers of the type t"""
        T = self.ctype(t)
        return self.function(f'{which}_{t}',f'{T} {{name}}( {T} a, {T} b )',
                             f'  return a {"<" if which == "min" else ">"} b ? a : b;\n')

    def toint_code( self ):
        return self.function('toint',f'{self.ctype("i64")} {{name}}( double v )',
                             self.fail(f'!( {self.fct("fabs","v")} < 4611686018427387904.0 )',
                                       'Value too large for integers')
                             + f'  return {self.cast("v","i64")};\n')

    def sphere_code( self ):
        """The function of through_sphere, of the vector r from the position to
        the center, the direction d, and the radius: whether the distance of
        the center from the line (the length of the cross product of r and d,
        as d is a unit vector) is at most the radius"""
        return self.function('through_sphere','int {name}( double rx, double ry, double rz,\n'
                             '                           double dx, double dy, double dz,\n'
                             '                           double radius )',
                             self.fail('radius < 0.0','Negative radius')
                             + '  double cx = ry * dz - rz * dy, cy = rz * dx - rx * dz,'
                             ' cz = rx * dy - ry * dx;\n'
                             '  return cx * cx + cy * cy + cz * cz <= radius * radius;\n')

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
                             '  /* Precise also for small angles */\n'
                             f'  double na = {sq("ax*ax + ay*ay + az*az")}, nb = {sq("bx*bx + by*by + bz*bz")};\n'
                             '  double dx = ax/na - bx/nb, dy = ay/na - by/nb, dz = az/na - bz/nb;\n'
                             '  double sx = ax/na + bx/nb, sy = ay/na + by/nb, sz = az/na + bz/nb;\n'
                             f'  return 2.0 * {self.fct("atan2",sq("dx*dx + dy*dy + dz*dz"),sq("sx*sx + sy*sy + sz*sz"))};\n')

    def wavelength_code( self ):
        from .constants import hc_eV_Aa, neutron_mass_energy
        return self.function('wavelength',f'double {{name}}( double ekin, {self.ctype("i32")} pdgcode )',
                             '  /* Wavelength in cm, of neutrons and gammas */\n'
                             + self.fail('pdgcode != 2112 && pdgcode != 22',
                                         'The wavelength is only defined for neutrons and gammas')
                             + self.fail('!( ekin > 0.0 )','The wavelength is infinite for zero kinetic energy')
                             + '  double pc = pdgcode == 22 ? ekin : '
                             + self.fct('sqrt',f'ekin * ( ekin + 2 * {neutron_mass_energy!r} )') + ';\n'
                             + f'  return {hc_eV_Aa!r} * 1e-6 / pc * {_expr_wl_unit!r};\n')

    def ekin_code( self ):
        from .constants import hc_eV_Aa, neutron_mass_energy
        mc2 = repr(neutron_mass_energy)
        return self.function('ekin_of_wavelength',
                             f'double {{name}}( double wl, {self.ctype("i32")} pdgcode )',
                             '  /* Kinetic energy of a wavelength in cm, of neutrons and gammas */\n'
                             + self.fail('pdgcode != 2112 && pdgcode != 22',
                                         'The wavelength can only be set for neutrons and gammas,'
                                         ' so keep only those first')
                             + self.fail('!( wl > 0.0 )','The wavelength must be positive')
                             + f'  double pc = {hc_eV_Aa!r} * 1e-6 / ( wl / {_expr_wl_unit!r} );\n'
                             + '  if ( pdgcode == 22 )\n    return pc;\n'
                             + f'  return pc * pc / ( {self.fct("sqrt",f"pc * pc + {mc2}*{mc2}")} + {mc2} );\n')

    def exact_cos_sin_code( self ):
        f = self.fct
        return self.function('exact_cos_sin','void {name}( double a, double * c, double * s )',
                             '  /* Exact for multiples of 90 degrees */\n'
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
        #(the difference of the cosines of the angles, v-u and vout-uout):
        angle_diff = ( f'( v[0]*u[0] + v[1]*u[1] + v[2]*u[2] ) - {_BRK2}'
                       '( vo[0]*uo[0] + vo[1]*uo[1] + vo[2]*uo[2] )' )
        self.function('unit_vector','int {name}( const double * v, double * u )',
                      f'  double n = {sq("v[0]*v[0] + v[1]*v[1] + v[2]*v[2]")};\n'
                      '  if ( !( n > 0.0 && n <= 1.7976931348623157e308 ) )\n    return 0;\n'
                      '  u[0] = v[0] / n;\n  u[1] = v[1] / n;\n  u[2] = v[2] / n;\n  return 1;\n')
        self.function('exact_matrix','void {name}( double * R )',
                      '  /* Elements within 1e-15 of 0 or +-1 are exact */\n'
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
                      '  /* The columns e1, e2, and e1 x e2 */\n'
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
                             + self.fail(f'{f("fabs",angle_diff)} > 1e-6',
                                         'In rotate_frame(..), the angle between v and u must be that between vout and uout')
                             + '  frame( v, u, E );\n  frame( vo, uo, F );\n'
                             '  /* R = F E^T */\n'
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

#(the sizes of the userdata types, in bytes):
_ud_sizes = { t : int(code[1:]) for t, code in _userdata_types.items() }

class _Statements:
    """Translates the statements of edit expressions to C or C++ (with the
    translator tr), where set_field(name, code) sets a field (None if no
    fields are changed), and filter conditions skip the particles for which they
    are false"""

    def __init__( self, tr, set_field ):
        self.tr, self.set_field = tr, set_field

    def __call__( self, statements ):
        lines = []
        for st in statements:
            if isinstance(st,Assign):
                lines += self.assign(st)
            elif _is_filter(st):
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
        #(the C names start with v_, so they are never names of the program,
        #like p, or of C and C++, like double):
        if isinstance(value,list):
            names = [ tr.new_name(f'v_{name}_{"xyz"[i]}') for i in range(len(value)) ]
            tr.variables[name] = [ ( n, t ) for n, ( _, t ) in zip(names,value) ]
            return [ f'{tr.ctype(t)} {n} = {c};' for n, ( c, t ) in zip(names,value) ]
        n = tr.new_name(f'v_{name}')
        tr.variables[name] = ( n, value[1] )
        return [ f'{tr.ctype(value[1])} {n} = {value[0]};' ]

    def assign( self, st ):
        tr, name = self.tr, st.target
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
        if name in _int_field_types:
            return [ self.set_field(name,self.int_field(name,value)) ]
        return [ self.set_field(name,tr.as_float(value)[0]) ]

    def int_field( self, name, value ):
        """The code of a value for pdgcode or userflags, which must be an
        integer in the range of their types"""
        tr = self.tr
        t = _int_field_types[name]
        T = tr.ctype(t)
        lo, hi = ( f'{v}.0' for v in _int_range(t) )
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

def _universal_checks( tr, modified, value ):
    """Lines checking that an edit changing the fields modified does not
    change fields with universal values (value(field) is the code of the
    edited value), which the edits refuse, as files only store the universal
    values"""
    lines = []
    for f in _universal_fields:
        if f in modified:
            lines += tr.fail(f'universal_{f} && {value(f)} != universal_{f}',
                             f'The {f} can not be changed in files with a universal {f}',
                             indent = '').rstrip('\n').split('\n')
    return lines

def _program_header( tree ):
    """The first comment lines of the generated code"""
    if tree is None:
        return [ 'Code generated by MCPL' ]
    return [ f'Edit: {_expr_ast2str(tree)}', 'Code generated by MCPL from the edit expression above' ]

def _c_string( text ):
    """The text as a string of C and C++"""
    return '"' + text.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n') + '"'

class _Program:
    """A C program doing what an edit does (see _expr_ast2c), built from
    parts which _CppProgram (in _expr_ast2cpp) gives for C++"""
    comment_marks = ( '/* ', ' *       ', ' */' )
    indent = '  '#(of the statements in main)
    main_void = 'int main( void )'

    def __init__( self, tree, layout, filenames, skip, limit, mark_statsums, comment ):
        self.tree, self.layout, self.filenames = tree, layout, filenames
        self.skip, self.limit = skip, limit
        self.mark_statsums, self.comment = mark_statsums, comment
        statements = () if tree is None else tree.statements
        self.modified = _modified_fields(statements)
        self.changes = bool(self.modified)
        #(the body of the loop over the particles, which sets what the
        #translator tr needs, like helpers and userdata fields):
        self.tr = self.translator()
        body, set_field = self.copy_lines(), None
        if self.changes:
            self.tr.field = self.changed_field
            set_field = self.set_field
        body += _Statements(self.tr,set_field)(statements)
        if self.changes:
            body += _universal_checks(self.tr,self.modified,self.changed_value)
            body.append(self.add_line())
        else:
            body.append(self.transfer_line())
        self.body = body

    def translator( self ):
        pin = lambda n : 'fileidx' if n == 'fileidx' else f'p_in->{_c_members[n]}'
        return _Translator('c',pin,self.layout)
    def copy_lines( self ):
        return [ 'mcpl_particle_t p = *p_in;' ] if self.changes else []
    def changed_field( self, n ):
        return 'fileidx' if n == 'fileidx' else f'p.{_c_members[n]}'
    def set_field( self, n, code ):
        return f'p.{_c_members[n]} = {code};'
    def changed_value( self, f ):
        return f'p.{_c_members[f]}'
    def add_line( self ):
        return ( 'mcpl_add_particle_with_userdata( fo, &p, ud );' if self.layout
                 else 'mcpl_add_particle( fo, &p );' )
    def transfer_line( self ):
        return 'mcpl_transfer_last_read_particle( fi, fo );'
    def includes( self ):
        return [ '#include "mcpl.h"', *( [ '#include <math.h>' ] if self.tr.math else [] ),
                 '#include <stdio.h>', '#include <stdlib.h>' ]
    def usage_line( self ):
        return '    printf( "Usage: %s INPUT.mcpl OUTPUT.mcpl\\n", argv[0] );'
    def open_lines( self, names ):
        return [ f'mcpl_file_t fi = mcpl_open_file( {names[0]} );',
                 f'mcpl_outfile_t fo = mcpl_create_outfile( {names[1]} );',
                 'mcpl_transfer_metadata( fi, fo );' ]
    add_comment = 'mcpl_hdr_add_comment( fo, '
    mark_line = 'mcpl_hdr_scale_stat_sums( fo, -1.0 );  /* stat:sum entries not available */'
    def seek_line( self ):
        return f'mcpl_seek( fi, {self.skip} );'
    def userdata_lines( self ):
        lines = []
        if self.tr.userdata:
            lines.append('const char * layout = mcpl_hdr_userdata_layout( fi );')
            for name, ( ftype, count ) in self.tr.userdata.items():
                t = ftype + ( f'[{count}]' if count is not None else '' )
                lines.append(f'const uint32_t offset_{name} = mcpl_userdata_offset( layout, "{name}", "{t}" );')
        return lines
    def universal_line( self, f ):
        return f'const {self.universal_type(f)} universal_{f} = mcpl_hdr_universal_{f}( fi );'
    def universal_type( self, f ):
        """The C type of the universal value of the field (pdgcode or weight)"""
        return self.tr.ctype(_int_field_types.get(f,'f64'))
    def loop_lines( self ):
        body = self.body
        lines = [ 'const mcpl_particle_t * p_in;' ]
        if self.layout:
            lines.append('const uint8_t * ud;')
        read = 'mcpl_read_with_userdata( fi, &ud )' if self.layout else 'mcpl_read( fi )'
        if self.limit is not None or self.tr.uses_fileidx:
            #(the particles are counted, from the first one of the range):
            cond = '' if self.limit is None else f'n < {self.limit} && '
            lines.append(f'for ( uint64_t n = 0; {cond}( p_in = {read} ); ++n ) {{')
            if self.tr.uses_fileidx:
                start = f'{self.skip} + ' if self.skip else ''
                body = [ f'const int64_t fileidx = (int64_t)( {start}n );', *body ]
        else:
            lines.append(f'while ( ( p_in = {read} ) ) {{')
        return lines + [ f'  {line}' for line in body ] + [ '}' ]
    def end_lines( self ):
        return [ '  mcpl_close_outfile( fo );', '  mcpl_close_file( fi );', '  return 0;', '}' ]
    def begin_lines( self ):
        return []

    def code( self ):
        """The program"""
        out = [ c for line in _program_header(self.tree)
                for c in _comment_lines(line,*self.comment_marks) ]
        out += [ '', *self.includes() ]
        for code in self.tr.helpers.values():
            out += [ '', *code.split('\n') ]
        if self.filenames is None:
            out += [ '', 'int main( int argc, char ** argv )', '{', '  if ( argc != 3 ) {',
                     self.usage_line(), '    return 1;', '  }' ]
            names = ( 'argv[1]', 'argv[2]' )
        else:
            out += [ '', self.main_void, '{' ]
            names = tuple( _c_string(str(f)) for f in self.filenames )
        ind = self.indent
        out += self.begin_lines()
        lines = self.open_lines(names)
        out += [ ind + line for line in lines ]
        if self.comment is not None:
            out += _string_call(ind + self.add_comment,self.comment,' );')
        lines = []
        if self.mark_statsums:
            lines.append(self.mark_line)
        if self.skip:
            lines.append(self.seek_line())
        lines += self.userdata_lines()
        lines += [ self.universal_line(f) for f in _universal_fields if f in self.modified ]
        lines += self.loop_lines()
        out += [ ind + line for line in lines ]
        out += self.end_lines()
        return '\n'.join(_layout(out)) + '\n'

def _expr_ast2c( tree = None, layout = None, *, filenames = None, skip = 0,
                 limit = None, mark_statsums = False, comment = None ):
    """A C program which writes the particles of an MCPL file which an edit
    keeps, with its changes, to a new file (tree is the checked and
    normalised tree of the edit expression, see _expressions, or None), for
    files with the userdata layout (or None for files without userdata).
    The files are given as arguments of the program, or else as filenames
    (input and output). Only the particles of the range of skip and limit
    (None for all, see _as_limit) are used, the stat:sum entries of the output
    are marked as not available if mark_statsums is set, and the comment (if
    any) is added to its header."""
    return _Program(tree,layout,filenames,skip,limit,mark_statsums,comment).code()
