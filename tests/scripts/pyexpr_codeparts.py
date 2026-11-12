
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
# Tests of the parts of the C and C++ code generators (pyexpr_codegen tests
# whole programs, and mcpldevtool codegen compiles and runs them): the
# operations which the translator asks the language providers for (with a
# provider which only records them, so the interface is tested without the
# code of any language), the code of C and C++ for single statements, the
# helper functions, and the layout of long lines.

from mcpldev._expr_ast2c import _CCode
from mcpldev._expr_ast2code import _Code, _Translator
from mcpldev._expr_ast2cpp import _CppCode
from mcpldev._expr_codelayout import (
    _BRK,
    _BRK2,
    _BRK3,
    _comment_lines,
    _layout,
    _split_text,
    _string_call,
    _Syntax,
    _unmarked,
)
from mcpldev._expr_vocab import (
    _int_field_types,
    _modified_fields,
    _rotation_planes,
    _value_type,
)
from mcpldev._expressions import _as_edit


class Recorder:
    """A language provider which writes the operations as text, like
    add_i32(a, b), and records when conditions are translated"""

    def __init__( self, layout, changes ):
        self.layout, self.changes = layout, changes
        self.events = []

    @staticmethod
    def num( code, t, **kw ):
        return _Code(code,t,atom = True,**kw)

    #Values:
    def int_constant( self, v, t, comment ):
        return self.num(f'{v}' + ( f'[{comment}]' if comment else '' ),t)
    def float_constant( self, v, comment = None ):
        return self.num(f'{v!r}' + ( f'[{comment}]' if comment else '' ),'f64')
    def field( self, n ):
        self.events.append(f'field {n}')
        return self.num(n,_int_field_types.get(n,'f64'))
    def wavelength( self ):
        return self.num('wavelength','f64')
    def userdata_value( self, name, ftype, count, index ):
        return self.num(f'ud.{name}' + ( '' if index is None else f'[{index}]' ),_value_type(ftype))
    def scaled( self, x, factor ):
        return self.num(f'{x[0]}*{factor[0]}','f64')
    def to_float( self, x ):
        return self.num(f'float({x[0]})','f64')

    #Conditions:
    def logical( self, op, conditions ):
        codes = []
        for i, c in enumerate(conditions):
            self.events.append(f'{op}: condition {i+1}')
            codes.append(c()[0])
        return self.num(f'{op}({", ".join(codes)})','i32')
    def logical_not( self, x ):
        return self.num(f'not({x[0]})','i32')
    def compare( self, op, a, b ):
        return self.num(f'({a[0]} {op} {b[0]})','i32')

    #Operations:
    def negate( self, x ):
        return self.num(f'-{x[0]}','f64')
    def float_op( self, op, a, b ):
        return self.num(f'({a[0]} {op} {b[0]})','f64')
    def check_finite( self, x ):
        return self.num(f'finite({x[0]})','f64',checked = True)
    def math_call( self, fname, *args ):
        self.events.append(f'math {fname}')
        return self.num(f'{fname}({", ".join( a[0] for a in args )})','f64')
    def int_exact( self, op, t, a, b ):
        return self.num(f'exact_{op}_{t}({a[0]}, {b[0]})',t)
    def int_op( self, op, t, *args ):
        return self.num(f'{op}_{t}({", ".join( a[0] for a in args )})',t)
    def toint( self, fname, x ):
        return self.num(f'toint_{fname}({x[0]})','i64')
    def min_max( self, which, t, a, b ):
        return self.num(f'{which}_{t}({a[0]}, {b[0]})',t)
    def angle( self, a, b ):
        return self.num(f'angle({", ".join( c[0] for c in ( *a, *b ) )})','f64')
    def through_sphere( self, to_center, d, radius ):
        return self.num(f'sphere({", ".join( c[0] for c in ( *to_center, *d, radius ) )})','i32')
    def through_box( self, to_center, d, half ):
        return self.num(f'box({", ".join( c[0] for c in ( *to_center, *d, *half ) )})','i32')

    #Statements:
    def filter( self, cond ):
        return [ f'keep if {cond[0]}' ]
    def variable( self, name, value ):
        if isinstance(value,list):
            return ( [ f'{name} = ({", ".join( v[0] for v in value )})' ],
                     [ self.num(f'{name}.{i}',v[1]) for i, v in enumerate(value) ] )
        line, value = self.temporary(name,value)
        return [ line ], value
    def temporary( self, base, value ):
        return f'{base} = {value[0]} ({value[1]})', self.num(base,value[1])
    def set_field( self, name, value ):
        return [ f'set {name} = {value[0]}' ]
    def set_fields( self, names, values ):
        return [ f'set {", ".join(names)} = {", ".join( v[0] for v in values )}' ]
    def set_wavelength( self, value ):
        return [ f'set wavelength = {value[0]}' ]
    def to_int_field( self, name, t, lo, hi, value ):
        return self.num(f'to_{name}({value[0]}, {lo}..{hi})',t)
    def rotate_plane( self, fname, angle, value ):
        self.events.append(f'{fname}: angle')
        a = angle()[0]
        return [ f'{fname}({a}) of ' + ', '.join( f'{value(x)[0]},{value(y)[0]}'
                                                  for x, y in _rotation_planes[fname] ) ]
    def rotate_matrix( self, fname, args, value ):
        self.events.append(f'{fname}: arguments')
        texts = [ f'({", ".join( c[0] for c in a )})' if isinstance(a,list) else a[0] for a in args() ]
        return [ f'{fname}({", ".join(texts)}) of {value("x")[0]}, ...' ]

def statements( edit, lang, layout = None ):
    """The lines of the statements of the edit, and the language provider"""
    statements = _as_edit(edit)._tree.statements
    lang = lang(layout,bool(_modified_fields(statements)))
    return _Translator(lang).statements(statements), lang

def test_operations():
    #(what the translator asks for, for each kind of expression):
    print('Operations of the translator:')
    for edit, layout in (
            ( 'pdgcode == neutron and pdgcode in (11,22) and pdgcode not in (-11)', None ),
            ( 'not x > 0cm or +x > 0cm or -x < 0cm or (1,2,3).z > 0', None ),
            ( 'x > pi*cm and -2147483648 < pdgcode and fileidx > 3', None ),
            ( 'mod(userflags,4) == 0 and mod(fileidx,3) == 0 and userflags // 2 > 0', None ),
            ( 'userflags & 3 == 1 and userflags | 1 > 0', None ),
            ( 'userflags + 1 > 0 and userflags + pdgcode > 0 and userflags > -1', None ),
            ( 'abs(x) > 1cm and abs(pdgcode) > 0 and abs(userflags) > 0', None ),
            ( 'round(x/cm) > 0 and floor(userflags) > 0 and ceil(ux) > 0', None ),
            ( 'min(userflags,3) > 1 and max(x,y,z) > 0cm and clamp(x,0cm,1cm) > 0cm', None ),
            ( 'hypot(x,y) > 1cm and sqrt(ekin/MeV) > 1 and atan2(x,y) > 0', None ),
            ( 'sin(ux) > 0 and x^3 > 1cm^3 and x*y/z > 1cm', None ),
            ( 'pos^2 > 1cm^2 and dot(pos,dir) > 0cm and cross(pos,dir).z > 0cm', None ),
            ( 'angle((x,y),(1,1)) < 1rad and angle(dir,(0,0,1)) < 1deg', None ),
            ( 'through_sphere((0,0,1m),5cm) and through_box((0,0,1m),(1cm,2cm,3cm))', None ),
            ( 'pdgcode == neutron and wavelength > 1Aa', None ),
            ( 'userdata.a > 10deg and userdata.n > 1 and userdata.v.at(2) > 0', 'a:float32:deg,n:int32,v:uint8[3]' ),
            ( 'r = (x,y,0cm); abs(r) > 1cm and r.y > 0cm', None ),
            ( 'r = x; r > 0cm', None ),
            ( 'x = 1cm; r = 2cm; y = r; weight *= 2', None ),
            ( 'pos = pos + dir*1cm; dir = -dir; pol = pol/2', None ),
            ( 'wavelength = 2Aa', None ),
            ( 'pdgcode = neutron; userflags = 7', None ),
            ( 'pdgcode = 2.5; userflags = pdgcode', None ),
            ( 'pdgcode = 2147483648', None ),
            ( 'swap(x,y); swap(pdgcode,userflags)', None ),
            ( 'rotate_z(90deg); rotate_x(ux*1rad)', None ),
            ( 'rotate_around((1,1,0),30deg); rotate_frame(dir,(0,0,1),pos,(1,0,0))', None ) ):
        lines, _ = statements(edit,Recorder,layout)
        print(f'  {edit!r}:')
        for line in lines:
            print(f'    {line}')

def test_when_needed():
    #Conditions are translated in order, each when the provider needs it, so
    #a provider working on blocks of particles can translate them for the
    #particles which the conditions before them leave open (log is only
    #needed for the particles with x > 0cm):
    print('Conditions translated when needed:')
    for edit in ( 'x > 0cm and log(x/cm) > 1', '0cm < x < log(y/cm)*1cm < 1m',
                  'x > 0cm or ux > 0 and sqrt(uy) > 0', 'rotate_z(atan2(uy,ux)*1rad)',
                  'rotate_around((ux,uy,0),sqrt(uz)*1rad)' ):
        _, rec = statements(edit,Recorder)
        print(f'  {edit!r}: {"; ".join(rec.events)}')

def test_values():
    #(what is known about values: constants, and checked values):
    print('Values:')
    tr = _Translator(Recorder(None,False))
    for text in ( '7', '-7', 'neutron', 'x', 'x/y', 'sqrt(x/cm)', 'abs(x)' ):
        v = tr(_as_edit(f'{text} == {text}')._tree.statements[0].first)
        print(f'  {text}: {v[0]} ({v[1]}), const {v.const}, checked {v.checked}')

def test_code():
    #(the code of C and C++ for statements, with integer constants at the
    #limits of their types, userdata, and the helper functions they use):
    print('Code of statements:')
    for edit, layout in (
            ( 'fileidx > -9223372036854775808 and fileidx < 9223372036854775807', None ),
            ( 'userdata.u > 18446744073709551615 - 1 and pdgcode > -2147483648', 'u:uint64' ),
            ( 'userdata.v.at(2) > 1 and userdata.a > 10deg', 'v:int16[3],a:float64:deg' ),
            ( 'r = x; not r > 0cm or min(r,y) > 0cm', None ),
            ( 'userflags = mod(userflags,4) + pdgcode', None ),
            ( 'x = 1cm; pos = pos + dir*1cm; pos = -pos', None ),
            ( 'wavelength = 2Aa; pdgcode = neutron', None ),
            ( 'swap(x,y); swap(pdgcode,userflags); r = (x,y,0cm); y = r.x', None ),
            ( 'rotate_x(30deg)', None ),
            ( 'rotate_around(dir,30deg)', None ) ):
        for name, lang in ( ( 'C', _CCode ), ( 'C++', _CppCode ) ):
            lines, code = statements(edit,lang,layout)
            print(f'  {name} for {edit!r}' + ( f', layout {layout!r}' if layout else '' ) + ':')
            for line in lines:
                print(f'    {_unmarked(line)}')
            print(f'    (helpers: {", ".join(code.helpers.code) or "none"})')

def test_helpers():
    #(the checked integer operations of each type, each helper function
    #written once however often it is used, and the helpers which others
    #need, before them):
    print('Helper functions:')
    for t in ( 'i32', 'u32', 'i64', 'u64' ):
        h = _CCode(None,False).helpers
        ops = [ 'add', 'sub', 'mul', 'div', 'mod', 'neg' ] + ( [ 'abs' ] if t[0] == 'i' else [ 'as' ] )
        for op in ops:
            h.int_op(op,t)
        for code in h.code.values():
            print(f'  {code.split(chr(10))[0]}')
    h = _CCode(None,False).helpers
    names = [ h.check_finite(), h.check_finite(), h.toint(), h.min_max('min','u64'),
              h.rotation_matrix('rotate_around'), h.rotation_matrix('rotate_frame'),
              h.rotation_matrix('rotate_around'), h.to_int_field('pdgcode','i32',-2147483648,2147483647) ]
    print(f'  returned: {", ".join(names)}')
    print(f'  written: {", ".join(h.code)}')
    for name, lang in ( ( 'C', _CCode ), ( 'C++', _CppCode ) ):
        h = lang(None,False).helpers
        h.int_op('as','u64')
        h.wavelength()
        print(f'  {name}:')
        for code in h.code.values():
            print('    ' + _unmarked(code).replace('\n','\n    '))

def test_layout():
    #(long lines broken first at the places marked with _BRK, one part on
    #each line, then where still needed after other operators and commas,
    #and last after the opening parentheses of calls, never in strings or
    #comments; long comments and strings split at spaces):
    print('Layout:')
    syntax = _Syntax('/*','*/','"',( ', ', '&& ', '|| ' ))
    words = [ f'value_{i}' for i in range(14) ]
    lines = [ 'short( a, b );',
              '  if ( ' + f' && {_BRK}'.join(words) + ' )',
              '  x = ' + f' + {_BRK2}'.join(words) + ';',
              '  y = ' + ', '.join(words) + ';',
              '  z = f( ' + _BRK3 + 'g( ' + _BRK3 + ', '.join(words[:6]) + ' ) ) + ' + 'h' * 60 + ';',
              '  s = "' + ', '.join(words) + '";',
              '  c = 1; /* ' + ' && '.join(words) + ' */',
              '  ' + 'w' * 110 + ';' ]
    for line in _layout(lines,syntax):
        print(f'  |{line}')
    text = 'one two three; four ' + 'x' * 30 + ' five'
    print(f'  split at 12: {_split_text(text,12)}')
    print(f'  split anywhere at 12: {_split_text(text,12,True)}')
    for line in _comment_lines('a comment ' * 15,'/* ',' * ',' */'):
        print(f'  |{line}')
    quote = lambda t : f'"{t}"'
    for line in _string_call('puts( ','short',' );',quote) + _string_call('puts( ','a long text ' * 12,' );',quote,10):
        print(f'  |{line}')

def test_programs():
    #(parts of the programs which only some options or files use: the
    #userdata fields of the file which C++ programs need, and the particles
    #read which are unused when kept only by fileidx):
    from mcpldev._expressions import _edit_code
    print('Program parts:')
    for edit in ( 'userdata.a > 1', 'mod(fileidx,2) == 0', 'x += 1cm' ):
        code = _edit_code('cpp',edit,'a:int32,b:float64')
        lines = [ line.strip() for line in code.splitlines() if 'userdata_field' in line or 'auto p :' in line ]
        print(f'  C++ for {edit!r}: {" | ".join(lines)}')

if __name__ == '__main__':
    test_operations()
    test_when_needed()
    test_values()
    test_code()
    test_helpers()
    test_layout()
    test_programs()
