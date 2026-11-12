
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

"""C code doing what edit expressions do (see _expr_ast2code): the language
provider of C (_CCode), with the C API of MCPL (mcpl.h). Interface:
_expr_ast2c(tree, layout), see _expr_ast2code.

Integers work as in the expressions: with the integer types of C, and with
the operations which can fail (overflow, division by zero, and negative
values where they can not be used) done by small helper functions, which stop
the program with an error. Values with units are in the units of MCPL, with
the units of constants in comments."""

__all__ = []

from ._expr_ast2code import _expr_ast2code
from ._expr_clike import _CLikeCode, _ctypes
from ._expr_vocab import _expr_vector_names, _expr_vectors
from ._userdata import _types as _userdata_types

#The fields, as members of mcpl_particle_t:
_c_members = { **{ c : f'{_expr_vector_names[v]}[{i}]' for v, comps in _expr_vectors.items()
                   for i, c in enumerate(comps) },
               **{ f : f for f in ( 'ekin', 'time', 'weight', 'pdgcode', 'userflags' ) } }

#The sizes of the userdata types, in bytes:
_ud_sizes = { t : int(code[1:]) for t, code in _userdata_types.items() }

class _CCode(_CLikeCode):
    """The language provider of C (see _CLikeCode)"""
    math_prefix = ''

    @staticmethod
    def ctype( t ):
        return _ctypes[t]

    @staticmethod
    def cast( code, t ):
        return f'({_ctypes[t]})( {code} )'

    @staticmethod
    def int64_constant( v, t ):
        #(the smallest int64 as (-INT64_C(...)-1), as INT64_C only takes literals):
        if v == -2**63:
            return f'(-INT64_C( {2**63-1} )-1)'
        return f'{"INT64_C" if t == "i64" else "UINT64_C"}( {v} )'

    def error( self, msg ):
        """The statement stopping the program with the message"""
        return '\n'.join(self.string_call('fprintf( stderr, ',f'ERROR: {msg}\n',' );',10) + [ 'exit( 1 );' ])

    def field_code( self, n ):
        """The code reading a field of the particle (of the copy which is
        changed, for changes)"""
        if n == 'fileidx':
            return n
        return f'p.{_c_members[n]}' if self.changes else f'p_in->{_c_members[n]}'

    @staticmethod
    def set_field_code( n, code ):
        return f'p.{_c_members[n]} = {code};'

    @staticmethod
    def userdata_get( name, ftype, index ):
        """The code getting a value of a userdata field (see userdata_lines)"""
        off = f'offset_{name}'
        if index is not None:
            off = f'{off} + {index} * {_ud_sizes[ftype]}'
        return f'mcpl_userdata_get_{ftype}( ud, {off} )'

    #The parts of the program (see _CLikeCode.program):

    comment_marks = ( '/* ', ' *       ', ' */' )
    inline_comment_marks = ( '/* ', '   ', ' */' )
    indent = '  '#(of the statements in main)
    main_void = 'int main( void )'
    add_comment = 'mcpl_hdr_add_comment( fo, '

    @staticmethod
    def copy_lines():
        return [ 'mcpl_particle_t p = *p_in;' ]
    def add_line( self ):
        return ( 'mcpl_add_particle_with_userdata( fo, &p, ud );' if self.layout
                 else 'mcpl_add_particle( fo, &p );' )
    @staticmethod
    def transfer_line():
        return 'mcpl_transfer_last_read_particle( fi, fo );'
    def includes( self ):
        return [ '#include "mcpl.h"', *( [ '#include <math.h>' ] if self.math else [] ),
                 '#include <stdio.h>', '#include <stdlib.h>' ]
    @staticmethod
    def usage_line():
        return '    printf( "Usage: %s INPUT.mcpl OUTPUT.mcpl\\n", argv[0] );'
    @staticmethod
    def begin_lines():
        return []
    @staticmethod
    def open_lines( names ):
        return [ f'mcpl_file_t fi = mcpl_open_file( {names[0]} );',
                 f'mcpl_outfile_t fo = mcpl_create_outfile( {names[1]} );',
                 'mcpl_transfer_metadata( fi, fo );' ]
    @staticmethod
    def scale_line( scale ):
        return f'mcpl_hdr_scale_stat_sums( fo, {scale} );'
    def statsum_range_lines( self ):
        lines = [ 'const uint64_t ntotal = mcpl_hdr_nparticles( fi );' ]
        rest = 'ntotal'
        if self.skip:
            lines.append(f'const uint64_t nskip = ntotal < {self.skip} ? ntotal : {self.skip};')
            rest = 'ntotal - nskip'
        nrange = rest if self.limit is None else f'{rest} < {self.limit} ? {rest} : {self.limit}'
        return lines + [ f'const uint64_t nrange = {nrange};', 'if ( nrange < ntotal )',
                         '  ' + self.scale_line('nrange ? (double)nrange / ntotal : -1.0') ]
    def seek_line( self ):
        return f'mcpl_seek( fi, {self.skip} );'
    def userdata_lines( self ):
        lines = []
        if self.userdata:
            lines.append('const char * layout = mcpl_hdr_userdata_layout( fi );')
            for name, ( ftype, count ) in self.userdata.items():
                t = ftype + ( f'[{count}]' if count is not None else '' )
                lines.append(f'const uint32_t offset_{name} = mcpl_userdata_offset( layout, "{name}", "{t}" );')
        return lines
    def universal_line( self, f ):
        return f'const {self.universal_type(f)} universal_{f} = mcpl_hdr_universal_{f}( fi );'
    def loop_lines( self, body ):
        lines = [ 'const mcpl_particle_t * p_in;' ]
        if self.layout:
            lines.append('const uint8_t * ud;')
        read = 'mcpl_read_with_userdata( fi, &ud )' if self.layout else 'mcpl_read( fi )'
        if self.limit is not None or self.uses_fileidx:
            #(the particles are counted, from the first one of the range):
            cond = '' if self.limit is None else f'n < {self.limit} && '
            lines.append(f'for ( uint64_t n = 0; {cond}( p_in = {read} ); ++n ) {{')
            if self.uses_fileidx:
                start = f'{self.skip} + ' if self.skip else ''
                body = [ f'const int64_t fileidx = (int64_t)( {start}n );', *body ]
        else:
            lines.append(f'while ( ( p_in = {read} ) ) {{')
        return lines + [ f'  {line}' for line in body ] + [ '}' ]
    @staticmethod
    def end_lines():
        return [ '  mcpl_close_outfile( fo );', '  mcpl_close_file( fi );', '  return 0;', '}' ]

def _expr_ast2c( tree = None, layout = None, **options ):
    """A C program doing what the edit does (see _expr_ast2code for the
    arguments)"""
    return _expr_ast2code(_CCode,tree,layout,**options)
