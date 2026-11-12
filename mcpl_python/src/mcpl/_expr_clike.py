
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

"""What the language providers of C (_CCode in _expr_ast2c) and C++ (_CppCode
in _expr_ast2cpp) share (see _expr_ast2code): the code of the operations,
which C and C++ write alike (with the helper functions of _expr_chelpers),
the code of the statements, and the outline of the programs. What differs
is in the methods which each of them has (see _CLikeCode)."""

__all__ = []

from ._expr_ast2code import _Code, _term
from ._expr_chelpers import _CHelpers
from ._expr_codelayout import (
    _ARGSEP,
    _BRK,
    _BRK2,
    _BRK3,
    _comment_lines,
    _layout,
    _string_call,
    _Syntax,
)
from ._expr_vocab import (
    _int_field_types,
    _rotated_vectors,
    _rotation_planes,
    _value_type,
)

_syntax = _Syntax('/*','*/','"',( ', ', '&& ', '|| ' ))

#The types of C of the types of numbers of the expressions:
_ctypes = { 'i32' : 'int32_t', 'u32' : 'uint32_t', 'i64' : 'int64_t', 'u64' : 'uint64_t',
            'f64' : 'double' }

#The fields which can have universal values in files (which edits can not
#change):
_universal_fields = ( 'pdgcode', 'weight' )

def _c_string( text ):
    """The text as a string of C and C++"""
    return '"' + text.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n') + '"'

class _CLikeCode:
    """The code of C and C++ for the operations of _Translator (in
    _expr_ast2code), for files with the userdata layout, and for edits which
    change fields (changes) or not. The language providers give:
    ctype(t), cast(code, t), int64_constant(v, t), math_prefix, error(msg),
    field_code(name), set_field_code(name, code), userdata_get(name, ftype,
    index), and the parts of the program (see program)."""

    def __init__( self, layout, changes ):
        self.layout, self.changes = layout, changes
        #(what the program needs: the helper functions, the math library,
        #fileidx, and the userdata fields used):
        self.helpers = _CHelpers(self)
        self.math = self.uses_fileidx = False
        self.userdata = {}
        self._names = set()

    def new_name( self, base ):
        """A new name for a variable"""
        name, i = base, 1
        while name in self._names:
            i += 1
            name = f'{base}_{i}'
        self._names.add(name)
        return name

    def fct( self, name, *args ):
        """A call of a function of the math library"""
        self.math = True
        return f'{self.math_prefix}{name}( {_BRK3}{_ARGSEP.join(args)} )'

    def string_call( self, start, text, end, indent = 0 ):
        return _string_call(start,text,end,_c_string,indent)

    def fail( self, cond, msg, indent = '  ' ):
        """Lines stopping the program with the message if cond is true"""
        lines = self.error(msg).split('\n')
        if len(lines) == 1:
            return f'{indent}if ( {cond} )\n{indent}  {lines[0]}\n'
        return ( f'{indent}if ( {cond} ) {{\n' + ''.join( f'{indent}  {l}\n' for l in lines )
                 + f'{indent}}}\n' )

    @staticmethod
    def paren( x ):
        """The code of the number x in parentheses, unless it is a single
        term (see _Code)"""
        return x[0] if x.atom else f'( {x[0]} )'

    #Values:

    def int_constant( self, v, t, comment = None ):
        if t == 'i32':
            code = f'({v+1}-1)' if v == -2**31 else str(v)
        else:
            code = self.int64_constant(v,t)
        return _term(code if comment is None else f'{code}/*{comment}*/',t)

    @staticmethod
    def float_constant( v, comment = None ):
        text = repr(float(v))
        return _term(text if comment is None else f'{text}/*{comment}*/','f64')

    def field( self, n ):
        """The value of a field of the particle"""
        if n == 'fileidx':
            self.uses_fileidx = True
        return _term(self.field_code(n),_int_field_types.get(n,'f64'))

    def wavelength( self ):
        self.helpers.wavelength()
        return _term(f'wavelength( {self.field_code("ekin")}, {self.field_code("pdgcode")} )','f64')

    def userdata_value( self, name, ftype, count, index ):
        self.userdata[name] = ( ftype, count )
        return _term(self.userdata_get(name,ftype,index),_value_type(ftype))

    @staticmethod
    def scaled( x, factor ):
        """The value x multiplied by the constant factor"""
        return _Code(f'{x[0]} * {factor[0]}','f64')

    def to_float( self, x ):
        return _term(self.cast(x[0],'f64'),'f64')

    #Conditions:

    @staticmethod
    def logical( op, conditions ):
        """The conditions (functions translating them) joined by and or or,
        each translated where the conditions before it leave the result open"""
        op = ' && ' if op == 'and' else ' || '
        return _term('( ' + ( op + _BRK ).join( c()[0] for c in conditions ) + ' )','i32')

    def logical_not( self, x ):
        return _term(f'!{self.paren(x)}','i32')

    def compare( self, op, a, b ):
        return _Code(f'{self.paren(a)} {op} {self.paren(b)}','i32')

    #Operations:

    def negate( self, x ):
        return _term(f'-{self.paren(x)}','f64')

    def float_op( self, op, a, b ):
        """The result of a floating point operation (+, -, *, or /), unchecked"""
        return _Code(f'{self.paren(a)} {op} {_BRK2}{self.paren(b)}','f64')

    def check_finite( self, x ):
        """The floating point number x, checked to be finite (as in the
        expressions)"""
        name = self.helpers.check_finite()
        return _Code(f'{name}( {_BRK3}{x[0]} )','f64',checked = True,atom = True)

    def math_call( self, fname, *args ):
        """A function of the math library, of floating point numbers"""
        return _term(self.fct(fname,*( a[0] for a in args )),'f64')

    @staticmethod
    def int_exact( op, t, a, b ):
        """An operation of integers of the type t which can not fail: & or |,
        and div (as //) or mod of unsigned integers by positive constants"""
        sym = { 'div' : '/', 'mod' : '%' }.get(op,op)
        return _term(f'( {a[0]} {sym} {b[0]} )',t)

    def int_op( self, op, t, *args ):
        """The checked operation op on integers of the type t (see
        _CHelpers.int_op)"""
        name = self.helpers.int_op(op,t)
        sep = ', ' + _BRK2 if op in ( 'add', 'sub', 'mul' ) else ', '
        return _term(f'{name}( {sep.join( a[0] for a in args )} )',t)

    def toint( self, fname, x ):
        """round, floor, or ceil of a floating point number, as an integer"""
        self.helpers.toint()
        return _term(f'toint( {self.fct("rint" if fname == "round" else fname,x[0])} )','i64')

    def min_max( self, which, t, a, b ):
        name = self.helpers.min_max(which,t)
        return _term(f'{name}( {a[0]}, {_BRK2}{b[0]} )',t)

    def angle( self, a, b ):
        """The angle between the vectors a and b, of three floating point numbers"""
        self.helpers.angle()
        return _term(f'angle( {_ARGSEP.join( c[0] for c in ( *a, *b ) )} )','f64')

    def through_sphere( self, to_center, d, radius ):
        name = self.helpers.sphere()
        return _term(f'{name}( {_ARGSEP.join( c[0] for c in ( *to_center, *d, radius ) )} )','i32')

    def through_box( self, to_center, d, half ):
        name = self.helpers.box()
        return _term(f'{name}( {_ARGSEP.join( c[0] for c in ( *to_center, *d, *half ) )} )','i32')

    #Statements:

    @staticmethod
    def filter( cond ):
        """Lines skipping the particles for which the condition is false"""
        return [ f'if ( !( {cond[0]} ) )', '  continue;' ]

    def variable( self, name, value ):
        """Lines declaring a new variable (or three, for vectors) for the value
        of a variable of the expression, and the value of the new variable"""
        #(the names start with v_, so they are never names of the program,
        #like p, or of C and C++, like double):
        if isinstance(value,list):
            names = [ self.new_name(f'v_{name}_{"xyz"[i]}') for i in range(len(value)) ]
            return ( [ f'{self.ctype(t)} {n} = {c};' for n, ( c, t ) in zip(names,value) ],
                     [ _term(n,t) for n, ( _, t ) in zip(names,value) ] )
        line, value = self.temporary(f'v_{name}',value)
        return [ line ], value

    def temporary( self, base, value ):
        """A line declaring a new variable for the value, and its value"""
        n = self.new_name(base)
        return f'{self.ctype(value[1])} {n} = {value[0]};', _term(n,value[1])

    def set_field( self, name, value ):
        return [ self.set_field_code(name,value[0]) ]

    def set_fields( self, names, values ):
        """Lines setting the fields to the values (all values first, as they
        can use the fields)"""
        tmp = [ self.new_name(f'new_{n}') for n in names ]
        return ( [ f'double {t} = {v[0]};' for t, v in zip(tmp,values) ]
                 + [ self.set_field_code(n,t) for n, t in zip(names,tmp) ] )

    def set_wavelength( self, value ):
        self.helpers.ekin()
        return self.set_field('ekin',_Code(f'ekin_of_wavelength( {value[0]}, {self.field_code("pdgcode")} )','f64'))

    def to_int_field( self, name, t, lo, hi, value ):
        """The floating point value as an integer for pdgcode or userflags, of
        the type t, checked to be an integer from lo to hi"""
        fname = self.helpers.to_int_field(name,t,lo,hi)
        return _term(f'{fname}( {value[0]} )',t)

    def rotate_plane( self, fname, angle, value ):
        """Lines doing rotate_x, rotate_y, or rotate_z by the angle (the function
        translating it), where value(name) is the value of a field"""
        self.helpers.exact_cos_sin()
        c, s = self.new_name('c'), self.new_name('s')
        lines = [ f'double {c}, {s};', f'exact_cos_sin( {angle()[0]}, &{c}, &{s} );' ]
        for a, b in _rotation_planes[fname]:
            va, vb = value(a)[0], value(b)[0]
            ta, tb = self.new_name(f'old_{a}'), self.new_name(f'old_{b}')
            lines += [ f'double {ta} = {va}, {tb} = {vb};',
                       self.set_field_code(a,f'{c} * {ta} - {s} * {tb} + 0.0'),
                       self.set_field_code(b,f'{s} * {ta} + {c} * {tb} + 0.0') ]
        return lines

    def rotate_matrix( self, fname, args, value ):
        """Lines doing rotate_around or rotate_frame with the arguments (the
        function translating them), where value(name) is the value of a field"""
        self.helpers.rotation_matrix(fname)
        R = self.new_name('R')
        lines, names = [ f'double {R}[9];' ], []
        for i, a in enumerate(args()):
            if isinstance(a,list):
                n = self.new_name(f'arg{i}')
                lines.append(f'double {n}[3] = {{ {", ".join( c[0] for c in a )} }};')
                names.append(n)
            else:
                names.append(a[0])
        lines.append(f'{fname}( {", ".join(names)}, {R} );')
        for comps in _rotated_vectors:
            old = [ self.new_name(f'old_{c}') for c in comps ]
            lines.append('double ' + ', '.join( f'{o} = {value(c)[0]}' for o, c in zip(old,comps) ) + ';')
            for i, c in enumerate(comps):
                terms = ' + '.join( f'{R}[{3*i+j}] * {old[j]}' for j in range(3) )
                lines.append(self.set_field_code(c,f'{terms} + 0.0'))
        return lines

    #The program:

    def program( self, header, body, modified, *, filenames, skip, limit, statsums, comment ):
        """The program, with the comment lines of the header, and the lines of
        the body of the loop over the particles (see _expr_ast2code), for an
        edit which modifies the fields modified"""
        self.skip, self.limit, self.statsums = skip, limit, statsums
        if self.changes:
            body = [ *self.copy_lines(), *body, *self.universal_checks(modified), self.add_line() ]
        else:
            body = [ *body, self.transfer_line() ]
        out = [ c for line in header for c in _comment_lines(line,*self.comment_marks) ]
        out += [ '', *self.includes() ]
        for code in self.helpers.code.values():
            out += [ '', *code.split('\n') ]
        if filenames is None:
            out += [ '', 'int main( int argc, char ** argv )', '{', '  if ( argc != 3 ) {',
                     self.usage_line(), '    return 1;', '  }' ]
            names = ( 'argv[1]', 'argv[2]' )
        else:
            out += [ '', self.main_void, '{' ]
            names = tuple( _c_string(str(f)) for f in filenames )
        ind = self.indent
        out += self.begin_lines()
        out += [ ind + line for line in self.open_lines(names) ]
        if comment is not None:
            out += self.string_call(ind + self.add_comment,comment,' );')
        lines = self.statsum_lines()
        if skip:
            lines.append(self.seek_line())
        lines += self.userdata_lines()
        lines += [ self.universal_line(f) for f in _universal_fields if f in modified ]
        lines += self.loop_lines(body)
        out += [ ind + line for line in lines ]
        out += self.end_lines()
        return '\n'.join(_layout(out,_syntax)) + '\n'

    def universal_checks( self, modified ):
        """Lines checking that an edit changing the fields modified does not
        change fields with universal values, which the edits refuse, as files
        only store the universal values"""
        lines = []
        for f in _universal_fields:
            if f in modified:
                lines += self.fail(f'universal_{f} && {self.field_code(f)} != universal_{f}',
                                   f'The {f} can not be changed in files with a universal {f}',
                                   indent = '').rstrip('\n').split('\n')
        return lines

    def universal_type( self, f ):
        """The type of the universal value of the field (pdgcode or weight)"""
        return self.ctype(_int_field_types.get(f,'f64'))

    def statsum_lines( self ):
        """The lines setting the stat:sum values of the output file (see
        _statsum_scale)"""
        if self.statsums == 'unavailable':
            return [ *_comment_lines('stat:sum values not available, as the filter depends'
                                     ' on the positions of the particles in the input file:',
                                     *self.inline_comment_marks),
                     self.scale_line('-1.0') ]
        if self.statsums == 'scaled':
            return [ *_comment_lines('stat:sum values scaled by the fraction of the particles'
                                     ' of the input file in the range used (mcpltool -s and -l):',
                                     *self.inline_comment_marks),
                     *self.statsum_range_lines() ]
        return []
