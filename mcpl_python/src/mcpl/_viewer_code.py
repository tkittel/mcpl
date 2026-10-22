
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

"""The command (of mcpltool) and the code (in Python, C++ and C) doing the
same as the viewer: histograms of plots, or writing the picked and edited
particles to a new file (see Viewer.code). The C++ and C code reads the
particles of the range of the file (skip and limit), with simple picks and
edits translated (see _CTranslator), and comments where custom code is needed
for the others (C and C++ have no expressions)."""

__all__ = []

#The kinds of code, as (key, label):
kinds = ( ( 'command', 'Command line' ), ( 'python', 'Python' ), ( 'cpp', 'C++' ),
          ( 'c', 'C' ) )

def _shell( text ):
    from ._extract import _shell_arg
    return _shell_arg(text)

def _c_string( text ):
    """The text as a string of C and C++ (the texts are ASCII)"""
    return '"' + text.replace('\\','\\\\').replace('"','\\"') + '"'

class _Job:
    """What the code does: the particles (in the file filename, in the range
    of skip and limit, picked and edited with the expressions pick and edit,
    or None), and then the histograms of the plots (if plots is not None), or
    else writing them to the file out (marking its stat:sum entries as not
    available if mark_statsums is set, and keeping the userdata of the
    particles if userdata is set, for files with userdata)"""
    def __init__( self, filename, skip, limit, pick, edit, plots, out,
                  mark_statsums, userdata = False ):
        self.filename, self.skip, self.limit = filename, skip or 0, limit or None
        self.pick, self.edit = pick, edit
        self.plots, self.out, self.mark_statsums = plots, out, mark_statsums
        self.userdata = userdata

def code( job, progname ):
    """The command and the code of the job, as a dict with the keys of kinds
    (without C++ and C for histograms, which C++ and C can not make)"""
    res = { 'command' : _command(job,progname), 'python' : _python(job) }
    if job.plots is None:
        res.update( { 'cpp' : _cpp(job), 'c' : _c(job) } )
    return res

def _command( job, prog ):
    fn = _shell(job.filename) if ' ' in job.filename else job.filename
    opts = ( [ f'-s{job.skip}' ] if job.skip else [] ) + ( [ f'-l{job.limit}' ] if job.limit else [] )
    for opt, e in ( ('-p',job.pick), ('-E',job.edit) ):
        if e is not None:
            opts += [ opt, _shell(e) ]
    if job.plots is not None:
        hists = []
        for p in job.plots:
            hists += [ '-H', _shell(p) ]
        return ' '.join( [ prog ] + opts + hists + [ fn ] )
    out = _shell(job.out) if ' ' in job.out else job.out
    return ' '.join( [ prog, '-e' ] + opts + [ fn, out ] )

def _python( job ):
    args = [ repr(job.filename) ]
    for name, value in ( ('skip',job.skip or None), ('limit',job.limit),
                         ('pick',job.pick), ('edit',job.edit) ):
        if value is not None:
            args.append(f'{name} = {value!r}')
    lines = [ 'import mcpl' ]
    if job.plots is not None:
        lines.append(f'f = mcpl.MCPLFile( {", ".join(args)} )')
        if len(job.plots) == 1:
            return '\n'.join( lines + [ f'h = mcpl.histogram( f, {job.plots[0]!r} )', 'h.plot()' ] )
        lines += [ 'hs = [ mcpl.histogram( f, p ) for p in (' ]
        lines += [ f'    {p!r},' for p in job.plots ]
        return '\n'.join( lines + [ ') ]', 'mcpl.plot_histograms( hs )' ] )
    lines += [ f'fin = mcpl.MCPLFile( {", ".join(args)} )',
               f'with mcpl.MCPLOutFile( {job.out!r} ) as fout:',
               '    fout.transfer_metadata( fin )  # copy the header' ]
    if job.mark_statsums:
        lines.append('    fout.hdr_scale_stat_sums( -1.0 )  # stat:sum entries not available')
    lines += [ '    for block in fin.particle_blocks:',
               '        fout.add_particles( block )' ]
    return '\n'.join(lines)

#Translation of simple expressions to C and C++ (fields, numbers, units, names
#of particles, arithmetic, comparisons, "in", and, or, not, and some functions),
#None for others (which are then left to the users):

#(the fields, as members of mcpl_particle_t, also for C++):
_c_fields = { 'x' : 'position[0]', 'y' : 'position[1]', 'z' : 'position[2]',
              'ux' : 'direction[0]', 'uy' : 'direction[1]', 'uz' : 'direction[2]',
              'polx' : 'polarisation[0]', 'poly' : 'polarisation[1]',
              'polz' : 'polarisation[2]', 'ekin' : 'ekin', 'time' : 'time',
              'weight' : 'weight', 'pdgcode' : 'pdgcode', 'userflags' : 'userflags' }
_c_int_fields = ( 'pdgcode', 'userflags' )
#(the fields which edits can change in the code, the direction and
#polarisation are not, since they are normalised by edits):
_c_assignable = ( 'x', 'y', 'z', 'ekin', 'time', 'weight', 'pdgcode', 'userflags' )
#(functions of one or two values, with their names in C, and in C++ in std::):
_c_math = { 'sqrt' : 1, 'exp' : 1, 'log' : 1, 'log10' : 1, 'sin' : 1, 'cos' : 1,
            'tan' : 1, 'asin' : 1, 'acos' : 1, 'atan' : 1, 'floor' : 1, 'ceil' : 1,
            'round' : 1, 'atan2' : 2, 'hypot' : 2 }

#(the precedences of C and C++, from the lowest; & and | are below the
#comparisons, unlike in the expressions):
_prec_or, _prec_and, _prec_bitor, _prec_bitand, _prec_cmp, _prec_add, _prec_mul, \
    _prec_unary, _prec_atom = range(9)

class _CTranslator:
    """Translates parsed expressions to C or C++ (lang 'c' or 'cpp'), with the
    particle named particle, which is a pointer to mcpl_particle_t (pointer
    'c'), the struct (pointer 'struct'), or an mcpl::Particle (pointer
    'cpp', with its methods). Notes the headers needed (in headers)."""
    def __init__( self, lang, particle, kind ):
        self.lang, self.particle, self.kind = lang, particle, kind
        self.headers = set()

    def field( self, name ):
        if self.kind == 'cpp':
            return f'{self.particle}.{name}()'
        return f'{self.particle}{"->" if self.kind == "c" else "."}{_c_fields[name]}'

    def __call__( self, node ):
        """The code of the node, or None: (code, whether it is an integer,
        precedence, value if constant)"""
        import ast

        from ._expressions import _expr_constants
        from ._exprsyntax import _expr_units, _Unit
        def const( v ):
            if isinstance(v,int):
                text = repr(v)
            else:
                #(without rounding noise, e.g. of 25meV, as a value of type double):
                text = f'{v:.15g}'
                text = text if ( '.' in text or 'e' in text or 'n' in text ) else text + '.0'
            return text, isinstance(v,int), _prec_atom if v >= 0 else _prec_unary, v
        if isinstance(node,ast.Expression):
            return self(node.body)
        if isinstance(node,ast.Constant):
            return const(node.value)
        if isinstance(node,_Unit):
            return const(float(_expr_units[node.unit][0] ** node.power))
        if isinstance(node,ast.Name):
            if node.id in _c_fields:
                return self.field(node.id), node.id in _c_int_fields, _prec_atom, None
            if node.id in _expr_constants:
                return const(_expr_constants[node.id])
            return None
        #(the translated parts of the node):
        if isinstance(node,ast.BoolOp):
            parts = node.values
        elif isinstance(node,ast.UnaryOp):
            parts = [ node.operand ]
        elif isinstance(node,ast.BinOp):
            parts = [ node.left, node.right ]
        elif isinstance(node,ast.Compare):
            parts = [ node.left ] + ( list(node.comparators[0].elts)
                                      if isinstance(node.ops[0],(ast.In,ast.NotIn))
                                      else node.comparators )
        elif isinstance(node,ast.Call):
            parts = node.args
        else:
            return None
        sub = [ self(n) for n in parts ]
        if any( x is None for x in sub ):
            return None
        def at( x, prec ):
            """The code of x, in parentheses if its precedence is below prec"""
            return x[0] if x[2] >= prec else f'( {x[0]} )'
        if isinstance(node,ast.BoolOp):
            prec, op = ( _prec_and, ' && ' ) if isinstance(node.op,ast.And) else ( _prec_or, ' || ' )
            #(also with parentheses around && in ||, as compilers suggest):
            return op.join( at(x,prec+2) for x in sub ), True, prec, None
        if isinstance(node,ast.UnaryOp):
            x, = sub
            if isinstance(node.op,ast.UAdd):
                return x
            if isinstance(node.op,ast.USub) and x[3] is not None:
                return const(-x[3])
            if isinstance(node.op,ast.Invert) and not x[1]:
                return None
            op = { ast.Not : '!', ast.USub : '-', ast.Invert : '~' }[type(node.op)]
            return f'{op}{at(x,_prec_unary)}', x[1] or op == '!', _prec_unary, None
        if isinstance(node,ast.BinOp):
            a, b = sub
            ops = { ast.Add : ( '+', _prec_add ), ast.Sub : ( '-', _prec_add ),
                    ast.Mult : ( '*', _prec_mul ), ast.Div : ( '/', _prec_mul ),
                    ast.BitAnd : ( '&', _prec_bitand ), ast.BitOr : ( '|', _prec_bitor ) }
            if isinstance(node.op,ast.Pow):
                if a[3] is not None and b[3] is not None:
                    return const(float(a[3]) ** b[3])
                return self._math('pow',[ a[0], b[0] ]), False, _prec_atom, None
            if type(node.op) not in ops:
                return None
            op, prec = ops[type(node.op)]
            if op in '&|' and not ( a[1] and b[1] ):
                return None
            if a[3] is not None and b[3] is not None and op in '+-*/':
                #(constants, as from units, e.g. 25meV):
                v = { '+' : a[3] + b[3], '-' : a[3] - b[3], '*' : a[3] * b[3],
                      '/' : a[3] / b[3] if b[3] else None }[op]
                if v is not None:
                    return const(v)
            if op in '*/' and b[3] == 1:
                return a#(e.g. ekin/MeV)
            if op == '*' and a[3] == 1:
                return b#(e.g. 1ms*x)
            left = at(a,prec)
            if op == '/' and a[1] and b[1]:
                #(integers divided as values, as in the expressions):
                left = f'(double){left}' if self.lang == 'c' else f'static_cast<double>({a[0]})'
            return ( f'{left} {op} {at(b,prec+1)}', a[1] and b[1] and op != '/', prec, None )
        if isinstance(node,ast.Compare):
            ops = { ast.Eq : '==', ast.NotEq : '!=', ast.Lt : '<', ast.LtE : '<=',
                    ast.Gt : '>', ast.GtE : '>=' }
            if isinstance(node.ops[0],(ast.In,ast.NotIn)):
                left = at(sub[0],_prec_cmp+1)
                isin = isinstance(node.ops[0],ast.In)
                terms = [ f'{left} {"==" if isin else "!="} {at(v,_prec_cmp+1)}' for v in sub[1:] ]
                if len(terms) == 1:
                    return terms[0], True, _prec_cmp, None
                return ( ' || ' if isin else ' && ' ).join(terms), True, _prec_or if isin else _prec_and, None
            terms = [ f'{at(sub[i],_prec_cmp+1)} {ops[type(op)]} {at(sub[i+1],_prec_cmp+1)}'
                      for i, op in enumerate(node.ops) ]
            if len(terms) == 1:
                return terms[0], True, _prec_cmp, None
            return ' && '.join(terms), True, _prec_and, None
        if isinstance(node,ast.Call):
            name, args = node.func.id, [ x[0] for x in sub ]
            if name == 'abs' and len(sub) == 1:
                i = sub[0][1]
                if self.lang == 'cpp':
                    self.headers.add('cstdlib' if i else 'cmath')
                    return f'std::abs( {args[0]} )', i, _prec_atom, None
                self.headers.add('stdlib.h' if i else 'math.h')
                return f'{"abs" if i else "fabs"}( {args[0]} )', i, _prec_atom, None
            if _c_math.get(name) == len(args):
                return self._math(name,args), False, _prec_atom, None
            if name in ( 'min', 'max' ) and len(args) == 2:
                return self._math(f'f{name}',args), False, _prec_atom, None
        return None

    def _math( self, name, args ):
        self.headers.add('cmath' if self.lang == 'cpp' else 'math.h')
        return f'{"std::" if self.lang == "cpp" else ""}{name}( {", ".join(args)} )'

def _c_condition( pick, tr ):
    """The C or C++ condition of the pick (an expression), or None"""
    from ._expressions import _Expr
    res = tr(_Expr(pick).tree)
    return None if res is None else res[0]

def _c_edit( edit, tr, indent ):
    """The C or C++ statements of the edit (of the struct of tr), or None"""
    from ._expressions import ParticleEdit, _rotation_matrix_args, _rotation_planes
    lines = []
    for st in ParticleEdit(edit)._statements:
        if st[0] == 'swap':
            res = _c_swap(st[1],st[2],tr,indent)
        elif st[0] in _rotation_planes:
            res = _c_rotation(st[0],st[1],tr,indent)
        elif st[0] in _rotation_matrix_args:
            res = _c_rotation_matrix(st[0],st[1],tr,indent)
        else:
            res = _c_assignment(st,tr,indent)
        if res is None:
            return None
        lines += res
    return lines

def _c_swap( a, b, tr, indent ):
    """The C or C++ code of swap(a,b), for fields of the same type"""
    if a not in _c_fields or b not in _c_fields:
        return None#(variables)
    types = [ 'int32_t' if n == 'pdgcode' else 'uint32_t' if n == 'userflags' else 'double'
              for n in ( a, b ) ]
    if types[0] != types[1]:
        return None
    t = types[0] if tr.lang == 'c' or types[0] == 'double' else f'std::{types[0]}'
    A, B = tr.field(a), tr.field(b)
    return _c_block(indent,f'{t} tmp = {A};',f'{A} = {B};',f'{B} = tmp;')

def _c_rotation( fname, angle, tr, indent ):
    """The C or C++ code of a rotation (rotate_x, rotate_y or rotate_z) by a
    constant angle, as done by the edits: exactly for multiples of 90 degrees
    (by swapping and negating values), else with the cos and sin of the
    angle"""
    import math

    from ._expressions import _rotation_planes
    value = tr(angle.tree)
    if value is None or value[3] is None:
        return None#(angles which are not constants)
    a = float(value[3])
    q = a / ( 0.5 * math.pi )
    k = round(q)
    lines = []
    if abs( q - k ) <= 8 * 2.220446049250313e-16 * max( 1.0, abs(k) ):
        #(A,B) -> (-B,A), (-A,-B) or (B,-A), with 0.0 - v for -v (to avoid
        #negative zeros, as the edits do):
        for pa, pb in _rotation_planes[fname]:
            A, B = tr.field(pa), tr.field(pb)
            lines += { 0 : [],
                       1 : _c_block(indent,f'double tmp = {A};',f'{A} = 0.0 - {B};',f'{B} = tmp;'),
                       2 : [ f'{indent}{A} = 0.0 - {A};', f'{indent}{B} = 0.0 - {B};' ],
                       3 : _c_block(indent,f'double tmp = {A};',f'{A} = {B};',f'{B} = 0.0 - tmp;') }[k % 4]
        return lines
    c, s = math.cos(a), math.sin(a)
    for pa, pb in _rotation_planes[fname]:
        A, B = tr.field(pa), tr.field(pb)
        lines += _c_block(indent,f'double tmp = {A};',f'{A} = {c!r} * tmp - {s!r} * {B};',
                          f'{B} = {s!r} * tmp + {c!r} * {B};')
    return lines

def _c_rotation_matrix( fname, args, tr, indent ):
    """The C or C++ code of rotate_around or rotate_frame with constant
    arguments: the rotation matrix (as for the edits) applied to the position,
    direction and polarisation, without its zero elements (so the rotations
    around the axes by multiples of 90 degrees are exact)"""
    from ._expressions import _rotated_vectors, _rotation_matrix
    values = []
    for a in args:
        value = tr(a.tree)
        if value is None or value[3] is None:
            return None#(arguments which are not constants)
        values.append(float(value[3]))
    R = _rotation_matrix(fname,values)
    if isinstance(R,str):
        return None
    lines = []
    for names in _rotated_vectors:
        F = [ tr.field(c) for c in names ]
        rows = []
        for i in range(3):
            terms = []
            for j in range(3):
                r = float(R[0,i,j])
                if r != 0.0:
                    terms.append( ( '-' if r < 0 else '+',
                                    f't{j}' if abs(r) == 1.0 else f'{abs(r)!r} * t{j}' ) )
            expr = ' '.join( f'{sign} {t}' for sign, t in terms ).lstrip('+ ')
            #(0.0 - v and + 0.0 for -v, to avoid negative zeros, as the edits do):
            expr = '0.0' if not terms else f'0.0 {expr}' if terms[0][0] == '-' else f'{expr} + 0.0'
            rows.append(f'{F[i]} = {expr};')
        lines += _c_block(indent,f'double t0 = {F[0]}, t1 = {F[1]}, t2 = {F[2]};',*rows)
    return lines

def _c_block( indent, *statements ):
    """The statements in a block (for the variables in it)"""
    return [ f'{indent}{{' ] + [ f'{indent}  {st}' for st in statements ] + [ f'{indent}}}' ]

def _c_assignment( st, tr, indent ):
    """The C or C++ code of an assignment of an edit (to a field), or None"""
    import ast
    if st[0] != 'assign' or st[1] not in _c_assignable:
        return None
    node = st[2].tree.body
    ops = { ast.Add : '+=', ast.Sub : '-=', ast.Mult : '*=', ast.Div : '/=' }
    if ( isinstance(node,ast.BinOp) and type(node.op) in ops
         and isinstance(node.left,ast.Name) and node.left.id == st[1] ):
        #(as x += ..):
        value, op = tr(node.right), ops[type(node.op)]
    else:
        value, op = tr(node), '='
    return None if value is None else [ f'{indent}{tr.field(st[1])} {op} {value[0]};' ]

def _custom( lang, what, text, indent ):
    """A comment saying where to add code for something which is not
    translated"""
    comment = f'Insert custom {"C++" if lang == "cpp" else "C"} logic here to mimic the {what}: "{text}"'
    return f'{indent}// {comment}' if lang == 'cpp' else f'{indent}/* {comment} */'

def _c_body( job, lang, particle, pointer, indent ):
    """The lines in the loop over the particles: the pick (as an if
    statement, if translated), and the edit (of the copy q, if translated),
    with comments where custom code is needed, and the headers which the code
    needs"""
    tr = _CTranslator(lang,particle,'c' if pointer else 'cpp')
    lines = []
    if job.pick is not None:
        cond = _c_condition(job.pick,tr)
        if cond is None:
            lines.append(_custom(lang,'pick',job.pick,indent))
        else:
            lines += [ f'{indent}{"//" if lang == "cpp" else "/*"} the pick: "{job.pick}"{"" if lang == "cpp" else " */"}',
                       f'{indent}if ( !( {cond} ) )', f'{indent}  continue;' ]
    if job.edit is not None:
        tr_q = _CTranslator(lang,'q','struct')
        edited = _c_edit(job.edit,tr_q,indent)
        tr.headers |= tr_q.headers
        if lang == 'cpp' and job.userdata:
            #(a particle of the output file, which has room for the userdata):
            tr.headers.add('algorithm')
            lines += [ f'{indent}auto out = fout.new_particle();',
                       f'{indent}out.c_struct() = p.c_struct();',
                       f'{indent}std::copy( p.raw_userdata(), p.raw_userdata() + p.userdata_size(),',
                       f'{indent}           out.raw_userdata() );  // (the userdata)',
                       f'{indent}mcpl_particle_t & q = out.c_struct();' ]
        else:
            lines.append(f'{indent}mcpl_particle_t q = {"*p" if pointer else "p.c_struct()"};')
        if edited is None:
            lines.append(_custom(lang,'edit',job.edit,indent))
        else:
            lines += [ f'{indent}{"//" if lang == "cpp" else "/*"} the edit: "{job.edit}"{"" if lang == "cpp" else " */"}' ] + edited
    return lines, tr.headers

def _loop_head( job, read, lang ):
    """The start of the loop over the particles of the range, with the
    particle p (after a seek to the first one)"""
    if lang == 'cpp':
        if job.limit:
            return [ '  std::uint64_t n = 0;',
                     f'  for ( auto p : {read} ) {{',
                     f'    if ( n++ == {job.limit} )',
                     '      break;' ]
        return [ f'  for ( auto p : {read} ) {{' ]
    if job.limit:
        return [ '  const mcpl_particle_t * p;',
                 f'  for ( uint64_t n = 0; n < {job.limit} && ( p = mcpl_read( {read} ) ); ++n ) {{' ]
    return [ '  const mcpl_particle_t * p;', f'  while ( ( p = mcpl_read( {read} ) ) ) {{' ]

def _gz( out ):
    """The name of the output file to create, and whether to gzip it"""
    return ( out[:-3], True ) if out.endswith('.gz') else ( out, False )

def _includes( lang, headers ):
    """The includes (the MCPL header, which includes stdint.h or cstdint, and
    the headers of the functions used)"""
    return [ f'#include "{"mcplcpp.h" if lang == "cpp" else "mcpl.h"}"' ] + [
        f'#include <{h}>' + ( '  /* (link with -lm) */' if h == 'math.h' else '' )
        for h in sorted(headers) ]

def _cpp( job ):
    fn = _c_string(job.filename)
    body, headers = _c_body(job,'cpp','p',False,'    ')
    out, gz = _gz(job.out)
    lines = [ f'  mcpl::MCPLFile fin( {fn} );',
              f'  mcpl::MCPLOutFile fout( {_c_string(out)} );',
              '  fout.transfer_metadata( fin );  // copy the header' ]
    if job.mark_statsums:
        lines.append('  fout.scale_stat_sums( -1.0 );  // stat:sum entries not available')
    if job.skip:
        lines.append(f'  fin.seek( {job.skip} );')
    lines += _loop_head(job,'fin','cpp') + body
    lines += ( [ f'    fout.add( {"out" if job.userdata else "q"} );' ] if job.edit is not None
               else [ '    fout.transfer_last_read_particle( fin );' ] )
    lines += [ '  }', f'  fout.{"close_and_gzip" if gz else "close"}();' ]
    return '\n'.join( _includes('cpp',headers) + [ '', 'int main()', '{' ] + lines + [ '}' ] )

def _c( job ):
    fn = _c_string(job.filename)
    body, headers = _c_body(job,'c','p',True,'    ')
    out, gz = _gz(job.out)
    lines = [ f'  mcpl_file_t fin = mcpl_open_file( {fn} );',
              f'  mcpl_outfile_t fout = mcpl_create_outfile( {_c_string(out)} );',
              '  mcpl_transfer_metadata( fin, fout );  /* copy the header */' ]
    if job.mark_statsums:
        lines.append('  mcpl_hdr_scale_stat_sums( fout, -1.0 );  /* stat:sum entries not available */')
    if job.skip:
        lines.append(f'  mcpl_seek( fin, {job.skip} );')
    lines += _loop_head(job,'fin','c') + body
    add = ( [ '    mcpl_add_particle_with_userdata( fout, &q, mcpl_last_read_userdata( fin ) );' ]
            if job.userdata else [ '    mcpl_add_particle( fout, &q );' ] )
    lines += ( add if job.edit is not None
               else [ '    mcpl_transfer_last_read_particle( fin, fout );' ] )
    lines += [ '  }', f'  mcpl_close{"andgzip" if gz else ""}_outfile( fout );',
               '  mcpl_close_file( fin );' ]
    return '\n'.join( _includes('c',headers) + [ '', 'int main( void )', '{' ] + lines
                      + [ '  return 0;', '}' ] )

#Syntax highlighting of the code (which is written above, so the simple
#patterns of each kind of code are enough), as styles of ranges of the text:

_keywords = {
    'python' : ( 'import', 'for', 'in', 'with', 'as' ),
    'cpp' : ( 'int', 'auto', 'for', 'if', 'continue', 'break', 'return', 'const',
              'double', 'static_cast' ),
    'c' : ( 'int', 'void', 'for', 'while', 'if', 'continue', 'break', 'return',
            'const', 'double' ),
}

def highlight( text, kind ):
    """The ranges of the text (code of the kind, see kinds) to show in a
    style: a list of (start, end, style), with the styles 'comment',
    'string', 'keyword', 'number', 'preprocessor' and 'option' (of
    commands)"""
    import re
    if kind == 'command':
        pattern = r'(?P<string>"[^"]*")|(?<!\S)(?P<option>--?[A-Za-z][^\s"]*)'
    else:
        comment = r'#[^\n]*' if kind == 'python' else r'//[^\n]*|/\*.*?\*/'
        strings = r'\'[^\'\n]*\'|"[^"\n]*"' if kind == 'python' else r'"[^"\n]*"|<[a-z.]+>(?=\s|$)'
        pre = r'(?P<preprocessor>^#include)|' if kind != 'python' else ''
        pattern = ( pre + rf'(?P<comment>{comment})|(?P<string>{strings})'
                    r'|(?P<keyword>\b(?:' + '|'.join(_keywords[kind]) + r')\b)'
                    r'|(?P<number>(?<![\w.])\d+(?:\.\d*)?(?:e[-+]?\d+)?\b)' )
    return [ ( m.start(), m.end(), m.lastgroup ) for m in
             re.finditer(pattern,text,flags = re.MULTILINE | re.DOTALL) ]
