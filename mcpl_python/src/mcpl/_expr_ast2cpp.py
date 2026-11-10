
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

"""C++ code doing what edit expressions do (see _expressions), with the C++
API of MCPL (mcplcpp.h): complete programs reading an MCPL file and writing
the particles kept, with their changes, to a new file. Interface:
_expr_ast2cpp(tree, layout), as _expr_ast2c, whose translation of expressions
it uses (so the C and C++ code compute the same), with errors as
exceptions."""

__all__ = []

from ._expr_ast2c import _Program, _Translator
from ._expr_vocab import _expr_vector_names
from ._userdata import _types as _userdata_types
from ._userdata import userdata_fields

#The userdata types, as types of C++:
_cpp_ud_types = { t : { 'float32' : 'float', 'float64' : 'double' }.get(t,f'std::{t}_t')
                  for t in _userdata_types }

class _CppTranslator(_Translator):
    """The translation to C++, with the userdata fields of mcpl::MCPLFile"""
    uses_p = False
    def userdata_get( self, name, ftype, index ):
        self.uses_p = True
        return f'ud_{name}( p )' if index is None else f'ud_{name}( p, {index} )'

class _CppProgram(_Program):
    """The C++ program (see _Program)"""
    comment_marks = ( '// ', '//       ' )
    indent = '    '#(in the try block)
    main_void = 'int main()'
    add_comment = 'fout.add_comment( '
    inline_comment_marks = ( '// ', '// ' )
    def __init__( self, tree, layout, *args ):
        #(the userdata fields, which changes copy):
        self.fields = userdata_fields(layout) if layout else []
        super().__init__(tree,layout,*args)
    def scale_line( self, scale ):
        return f'fout.scale_stat_sums( {scale} );'
    def statsum_range_lines( self ):
        lines = [ 'const std::uint64_t ntotal = fin.nparticles();' ]
        rest = 'ntotal'
        if self.skip:
            lines.append(f'const std::uint64_t nskip = std::min<std::uint64_t>( ntotal, {self.skip} );')
            rest = 'ntotal - nskip'
        nrange = rest if self.limit is None else f'std::min<std::uint64_t>( {rest}, {self.limit} )'
        return lines + [ f'const std::uint64_t nrange = {nrange};', 'if ( nrange < ntotal )',
                         '  ' + self.scale_line('nrange ? double(nrange) / ntotal : -1.0') ]

    def translator( self ):
        return _CppTranslator('cpp',self.field_getter('p'),self.layout)
    def field_getter( self, obj ):
        def get( n ):
            if n == 'fileidx':
                return n
            self.tr.uses_p = self.tr.uses_p or obj == 'p'
            return f'{obj}.{n}()'
        return get
    def copy_lines( self ):
        if not self.changes:
            return []
        lines = [ f'out.set_{v}( p.{v}() );' for v in ( *_expr_vector_names.values(), 'ekin', 'time',
                                                        'weight', 'pdgcode', 'userflags' ) ]
        return lines + [ f'out.set_userdata( out_{name}, ud_{name}( p ) );'
                         for name, _, _ in self.fields ]
    def changed_field( self, n ):
        return self.field_getter('out')(n)
    def set_field( self, n, code ):
        return f'out.set_{n}( {code} );'
    def changed_value( self, f ):
        return f'out.{f}()'
    def add_line( self ):
        return 'fout.add( out );'
    def transfer_line( self ):
        return 'fout.transfer_last_read_particle( fin );'
    def includes( self ):
        #(mcplcpp.h has the integer types and std::runtime_error):
        return [ '#include "mcplcpp.h"', *( [ '#include <cmath>' ] if self.tr.math else [] ),
                 '#include <iostream>' ]
    def usage_line( self ):
        return '    std::cout << "Usage: " << argv[0] << " INPUT.mcpl OUTPUT.mcpl" << std::endl;'
    def begin_lines( self ):
        return [ '  try {' ]
    def open_lines( self, names ):
        return [ f'mcpl::MCPLFile fin( {names[0]} );', f'mcpl::MCPLOutFile fout( {names[1]} );',
                 'fout.transfer_metadata( fin );' ]
    def seek_line( self ):
        return f'fin.seek( {self.skip} );'
    def userdata_lines( self ):
        #(the userdata fields used, and for changes all of them, to copy them):
        lines = []
        for name, ftype, count in self.fields:
            if name in self.tr.userdata or self.changes:
                targs = _cpp_ud_types[ftype] + ( f',{count}' if count is not None else '' )
                lines.append(f'auto ud_{name} = fin.userdata_field<{targs}>( "{name}" );')
                if self.changes:
                    lines.append(f'auto out_{name} = fout.userdata_field<{targs}>( "{name}" );')
        return lines
    def universal_line( self, f ):
        return f'const {self.universal_type(f)} universal_{f} = fin.universal_{f}();'
    def loop_lines( self ):
        lines = [ 'auto out = fout.new_particle();' ] if self.changes else []
        counted = self.limit is not None or self.tr.uses_fileidx
        if counted:
            #(the particles are counted, from the first one of the range):
            lines.append('std::uint64_t n = 0;')
        #(the particles are not used when kept only by fileidx):
        unused = '' if self.tr.uses_p or self.changes else '[[maybe_unused]] '
        lines.append(f'for ( {unused}auto p : fin ) {{')
        if self.limit is not None:
            lines += [ f'  if ( n == {self.limit} )', '    break;' ]
        if self.tr.uses_fileidx:
            start = f'{self.skip} + ' if self.skip else ''
            lines.append(f'  const std::int64_t fileidx = static_cast<std::int64_t>( {start}n );')
        if counted:
            lines.append('  ++n;')
        return lines + [ f'  {line}' for line in self.body ] + [ '}' ]
    def end_lines( self ):
        return [ '    fout.close();', '    fin.close();', '  } catch ( const std::runtime_error& e ) {',
                 '    std::cerr << "ERROR: " << e.what() << std::endl;', '    return 1;', '  }',
                 '  return 0;', '}' ]

def _expr_ast2cpp( tree = None, layout = None, *, filenames = None, skip = 0,
                   limit = None, statsums = None, comment = None ):
    """A C++ program which writes the particles of an MCPL file which an edit
    keeps, with its changes, to a new file (see _expr_ast2c)"""
    return _CppProgram(tree,layout,filenames,skip,limit,statsums,comment).code()
