
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

"""C++ code doing what edit expressions do (see _expr_ast2code): the language
provider of C++ (_CppCode), with the C++ API of MCPL (mcplcpp.h), and errors
as exceptions. Interface: _expr_ast2cpp(tree, layout), see _expr_ast2code."""

__all__ = []

from ._expr_ast2code import _expr_ast2code
from ._expr_clike import _CLikeCode, _ctypes
from ._expr_vocab import _expr_vector_names
from ._userdata import _types as _userdata_types
from ._userdata import userdata_fields

#The userdata types, as types of C++:
_cpp_ud_types = { t : { 'float32' : 'float', 'float64' : 'double' }.get(t,f'std::{t}_t')
                  for t in _userdata_types }

class _CppCode(_CLikeCode):
    """The language provider of C++ (see _CLikeCode)"""
    math_prefix = 'std::'

    def __init__( self, layout, changes ):
        super().__init__(layout,changes)
        #(the userdata fields, which changes copy, and whether the particles
        #read are used):
        self.fields = userdata_fields(layout) if layout else []
        self.uses_p = False

    @staticmethod
    def ctype( t ):
        return _ctypes[t] if t == 'f64' else f'std::{_ctypes[t]}'

    def cast( self, code, t ):
        return f'static_cast<{self.ctype(t)}>( {code} )'

    @staticmethod
    def int64_constant( v, t ):
        text = f'({v+1}-1)' if v == -2**63 else f'{v}u' if t == 'u64' else str(v)
        return f'std::{_ctypes[t]}( {text} )'

    def error( self, msg ):
        """The statement stopping the program with the message"""
        return '\n'.join(self.string_call('throw std::runtime_error( ',msg,' );',10))

    def field_code( self, n ):
        """The code reading a field of the particle (of the copy which is
        changed, for changes)"""
        if n == 'fileidx':
            return n
        if self.changes:
            return f'out.{n}()'
        self.uses_p = True
        return f'p.{n}()'

    @staticmethod
    def set_field_code( n, code ):
        return f'out.set_{n}( {code} );'

    def userdata_get( self, name, ftype, index ):
        self.uses_p = True
        return f'ud_{name}( p )' if index is None else f'ud_{name}( p, {index} )'

    #The parts of the program (see _CLikeCode.program):

    comment_marks = ( '// ', '//       ' )
    inline_comment_marks = ( '// ', '// ' )
    indent = '    '#(in the try block)
    main_void = 'int main()'
    add_comment = 'fout.add_comment( '

    def copy_lines( self ):
        lines = [ f'out.set_{v}( p.{v}() );' for v in ( *_expr_vector_names.values(), 'ekin', 'time',
                                                        'weight', 'pdgcode', 'userflags' ) ]
        return lines + [ f'out.set_userdata( out_{name}, ud_{name}( p ) );'
                         for name, _, _ in self.fields ]
    @staticmethod
    def add_line():
        return 'fout.add( out );'
    @staticmethod
    def transfer_line():
        return 'fout.transfer_last_read_particle( fin );'
    def includes( self ):
        #(mcplcpp.h has the integer types and std::runtime_error):
        return [ '#include "mcplcpp.h"', *( [ '#include <cmath>' ] if self.math else [] ),
                 '#include <iostream>' ]
    @staticmethod
    def usage_line():
        return '    std::cout << "Usage: " << argv[0] << " INPUT.mcpl OUTPUT.mcpl" << std::endl;'
    @staticmethod
    def begin_lines():
        return [ '  try {' ]
    @staticmethod
    def open_lines( names ):
        return [ f'mcpl::MCPLFile fin( {names[0]} );', f'mcpl::MCPLOutFile fout( {names[1]} );',
                 'fout.transfer_metadata( fin );' ]
    @staticmethod
    def scale_line( scale ):
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
    def seek_line( self ):
        return f'fin.seek( {self.skip} );'
    def userdata_lines( self ):
        #(the userdata fields used, and for changes all of them, to copy them):
        lines = []
        for name, ftype, count in self.fields:
            if name in self.userdata or self.changes:
                targs = _cpp_ud_types[ftype] + ( f',{count}' if count is not None else '' )
                lines.append(f'auto ud_{name} = fin.userdata_field<{targs}>( "{name}" );')
                if self.changes:
                    lines.append(f'auto out_{name} = fout.userdata_field<{targs}>( "{name}" );')
        return lines
    def universal_line( self, f ):
        return f'const {self.universal_type(f)} universal_{f} = fin.universal_{f}();'
    def loop_lines( self, body ):
        lines = [ 'auto out = fout.new_particle();' ] if self.changes else []
        counted = self.limit is not None or self.uses_fileidx
        if counted:
            #(the particles are counted, from the first one of the range):
            lines.append('std::uint64_t n = 0;')
        #(the particles are not used when kept only by fileidx):
        unused = '' if self.uses_p or self.changes else '[[maybe_unused]] '
        lines.append(f'for ( {unused}auto p : fin ) {{')
        if self.limit is not None:
            lines += [ f'  if ( n == {self.limit} )', '    break;' ]
        if self.uses_fileidx:
            start = f'{self.skip} + ' if self.skip else ''
            lines.append(f'  const std::int64_t fileidx = static_cast<std::int64_t>( {start}n );')
        if counted:
            lines.append('  ++n;')
        return lines + [ f'  {line}' for line in body ] + [ '}' ]
    @staticmethod
    def end_lines():
        return [ '    fout.close();', '    fin.close();', '  } catch ( const std::runtime_error& e ) {',
                 '    std::cerr << "ERROR: " << e.what() << std::endl;', '    return 1;', '  }',
                 '  return 0;', '}' ]

def _expr_ast2cpp( tree = None, layout = None, **options ):
    """A C++ program doing what the edit does (see _expr_ast2code for the
    arguments)"""
    return _expr_ast2code(_CppCode,tree,layout,**options)
