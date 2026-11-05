
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

"""C++ code doing what picks and edits do (see _expressions), with the C++
API of MCPL (mcplcpp.h): complete programs reading an MCPL file and writing
the picked and edited particles to a new file. Interface: _expr_ast2cpp(pick,
edit, layout), as _expr_ast2c, whose translation of expressions it uses (so
the C and C++ code compute the same), with errors as exceptions."""

__all__ = []

from ._expr_ast2c import _c_string, _program_header, _Statements, _Translator

#The userdata types, as types of C++:
_cpp_ud_types = { 'int8' : 'std::int8_t', 'uint8' : 'std::uint8_t', 'int16' : 'std::int16_t',
                  'uint16' : 'std::uint16_t', 'int32' : 'std::int32_t', 'uint32' : 'std::uint32_t',
                  'int64' : 'std::int64_t', 'uint64' : 'std::uint64_t', 'float32' : 'float',
                  'float64' : 'double' }
#(the fields with their setters, of mcpl::OutParticle):
_vector_setters = { 'position' : ( 'x', 'y', 'z' ), 'direction' : ( 'ux', 'uy', 'uz' ),
                    'polarisation' : ( 'polx', 'poly', 'polz' ) }

class _CppTranslator(_Translator):
    """The translation to C++, with the userdata fields of mcpl::MCPLFile"""
    uses_p = False
    def userdata_get( self, name, ftype, index ):
        self.uses_p = True
        return f'ud_{name}( p )' if index is None else f'ud_{name}( p, {index} )'

def _expr_ast2cpp( pick = None, edit = None, layout = None, *, filenames = None, skip = 0,
                   limit = None, mark_statsums = False, comment = None ):
    """A C++ program which writes the particles of an MCPL file which the pick
    picks, edited by the edit, to a new file (see _expr_ast2c)"""
    from ._expressions import _as_edit, _as_filter
    from ._userdata import userdata_fields
    pick, edit = _as_filter(pick), _as_edit(edit)
    def field( obj ):
        def get( n ):
            if n == 'fileidx':
                return n
            tr.uses_p = tr.uses_p or obj == 'p'
            return f'{obj}.{n}()'
        return get
    tr = _CppTranslator('cpp',field('p'),layout)
    body = []
    if pick is not None:
        body.append(f'// Pick: {pick.expression}')
        body += _Statements(tr,None)(pick._tree.statements)
        body += [ f'if ( !( {tr.condition(pick._tree.condition)} ) )', '  continue;' ]
    fields = userdata_fields(layout) if layout else []
    if edit is not None:
        body.append(f'// Edit: {edit.expression}')
        body += [ f'out.set_{v}( p.{v}() );' for v in ( *_vector_setters, 'ekin', 'time', 'weight',
                                                       'pdgcode', 'userflags' ) ]
        body += [ f'out.set_userdata( out_{name}, ud_{name}( p ) );' for name, _, _ in fields ]
        tr.field = field('out')
        def set_field( n, code, op = '' ):
            return f'out.set_{n}( {f"out.{n}() {op} " if op else ""}{code} );'
        body += _Statements(tr,set_field)(edit._tree.statements)
        body.append('fout.add( out );')
    else:
        body.append('fout.transfer_last_read_particle( fin );')
    out = [ f'// {line}' for line in _program_header(pick,edit) ]
    out += [ '', '#include "mcplcpp.h"' ]
    #(mcplcpp.h has the integer types and std::runtime_error):
    if tr.math:
        out.append('#include <cmath>')
    out.append('#include <iostream>')
    for code in tr.helpers.values():
        out += [ '', *code.split('\n') ]
    if filenames is None:
        out += [ '', 'int main( int argc, char ** argv )', '{',
                 '  if ( argc != 3 ) {',
                 '    std::cout << "Usage: " << argv[0] << " INPUT.mcpl OUTPUT.mcpl" << std::endl;',
                 '    return 1;', '  }' ]
        names = ( 'argv[1]', 'argv[2]' )
    else:
        out += [ '', 'int main()', '{' ]
        names = tuple( _c_string(str(f)) for f in filenames )
    out += [ '  try {',
             f'    mcpl::MCPLFile fin( {names[0]} );',
             f'    mcpl::MCPLOutFile fout( {names[1]} );',
             '    fout.transfer_metadata( fin );' ]
    if comment is not None:
        out.append(f'    fout.add_comment( {_c_string(comment)} );')
    if mark_statsums:
        out.append('    fout.scale_stat_sums( -1.0 );  // stat:sum entries not available')
    if skip:
        out.append(f'    fin.seek( {skip} );')
    #(the userdata fields used, and for edits all of them, to copy them):
    used = { name for name in tr.userdata }
    for name, ftype, count in fields:
        if name in used or edit is not None:
            targs = _cpp_ud_types[ftype] + ( f',{count}' if count is not None else '' )
            out.append(f'    auto ud_{name} = fin.userdata_field<{targs}>( "{name}" );')
            if edit is not None:
                out.append(f'    auto out_{name} = fout.userdata_field<{targs}>( "{name}" );')
    if edit is not None:
        out.append('    auto out = fout.new_particle();')
    counted = limit or tr.uses_fileidx
    if counted:
        #(the particles are counted, from the first one of the range):
        out.append('    std::uint64_t n = 0;')
    #(the particles are not used when picked only by fileidx):
    unused = '' if tr.uses_p or edit is not None else '[[maybe_unused]] '
    out.append(f'    for ( {unused}auto p : fin ) {{')
    if limit:
        out += [ f'      if ( n == {limit} )', '        break;' ]
    if tr.uses_fileidx:
        out.append(f'      const std::int64_t fileidx = static_cast<std::int64_t>( {f"{skip} + " if skip else ""}n );')
    if counted:
        out.append('      ++n;')
    out += [ f'      {line}' for line in body ]
    out += [ '    }', '    fout.close();', '    fin.close();', '  } catch ( const std::runtime_error& e ) {',
             '    std::cout << "ERROR: " << e.what() << std::endl;', '    return 1;', '  }',
             '  return 0;', '}' ]
    return '\n'.join(out) + '\n'
