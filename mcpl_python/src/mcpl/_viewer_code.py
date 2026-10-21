
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
particles of the range of the file (skip and limit), but the expressions (of
picks, edits and histograms) are not translated to C++ and C, which comments
say."""

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
    available if mark_statsums is set)"""
    def __init__( self, filename, skip, limit, pick, edit, plots, out,
                  mark_statsums ):
        self.filename, self.skip, self.limit = filename, skip or 0, limit or None
        self.pick, self.edit = pick, edit
        self.plots, self.out, self.mark_statsums = plots, out, mark_statsums

def code( job, progname ):
    """The command and the code of the job, as a dict with the keys of
    kinds"""
    return { 'command' : _command(job,progname), 'python' : _python(job),
             'cpp' : _cpp(job), 'c' : _c(job) }

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

def _untranslated( job, comment, indent ):
    """Comment lines (with the comment marker, e.g. '//') about the
    expressions which are not translated (empty if there are none)"""
    what = [ f'the {name} {e}' for name, e in ( ('pick',job.pick), ('edit',job.edit) )
             if e is not None ]
    if job.plots is not None:
        what += [ f'the histogram of {p}' for p in job.plots ]
    if not what:
        return []
    lines = [ 'Not yet translated (expressions are available in Python and mcpltool):' ]
    lines += [ f'  {w}' for w in what ]
    if comment == '/*':
        return ( [ f'{indent}/* {lines[0]}' ] + [ f'{indent}   {line}' for line in lines[1:-1] ]
                 + [ f'{indent}   {lines[-1]} */' ] )
    return [ f'{indent}// {line}' for line in lines ]

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

def _cpp( job ):
    fn = _c_string(job.filename)
    lines = [ '#include "mcplcpp.h"', '#include <cstdint>', '', 'int main()', '{' ]
    if job.plots is not None:
        lines.append(f'  mcpl::MCPLFile f( {fn} );')
        if job.skip:
            lines.append(f'  f.seek( {job.skip} );')
        lines += _loop_head(job,'f','cpp') + _untranslated(job,'//','    ')
        lines += [ '    (void)p;', '  }', '}' ]
        return '\n'.join(lines)
    out, gz = _gz(job.out)
    lines += [ f'  mcpl::MCPLFile fin( {fn} );',
               f'  mcpl::MCPLOutFile fout( {_c_string(out)} );',
               '  fout.transfer_metadata( fin );  // copy the header' ]
    if job.mark_statsums:
        lines.append('  fout.scale_stat_sums( -1.0 );  // stat:sum entries not available')
    if job.skip:
        lines.append(f'  fin.seek( {job.skip} );')
    lines += _loop_head(job,'fin','cpp') + _untranslated(job,'//','    ')
    if job.edit is not None:
        lines += [ '    mcpl_particle_t q = p.c_struct();', '    fout.add( q );' ]
    else:
        lines += [ '    (void)p;', '    fout.transfer_last_read_particle( fin );' ]
    lines += [ '  }', f'  fout.{"close_and_gzip" if gz else "close"}();', '}' ]
    return '\n'.join(lines)

def _c( job ):
    fn = _c_string(job.filename)
    lines = [ '#include "mcpl.h"', '#include <stdint.h>', '', 'int main( void )', '{' ]
    if job.plots is not None:
        lines.append(f'  mcpl_file_t f = mcpl_open_file( {fn} );')
        if job.skip:
            lines.append(f'  mcpl_seek( f, {job.skip} );')
        lines += _loop_head(job,'f','c') + _untranslated(job,'/*','    ')
        lines += [ '    (void)p;', '  }', '  mcpl_close_file( f );', '  return 0;', '}' ]
        return '\n'.join(lines)
    out, gz = _gz(job.out)
    lines += [ f'  mcpl_file_t fin = mcpl_open_file( {fn} );',
               f'  mcpl_outfile_t fout = mcpl_create_outfile( {_c_string(out)} );',
               '  mcpl_transfer_metadata( fin, fout );  /* copy the header */' ]
    if job.mark_statsums:
        lines.append('  mcpl_hdr_scale_stat_sums( fout, -1.0 );  /* stat:sum entries not available */')
    if job.skip:
        lines.append(f'  mcpl_seek( fin, {job.skip} );')
    lines += _loop_head(job,'fin','c') + _untranslated(job,'/*','    ')
    if job.edit is not None:
        lines += [ '    mcpl_particle_t q = *p;', '    mcpl_add_particle( fout, &q );' ]
    else:
        lines += [ '    (void)p;', '    mcpl_transfer_last_read_particle( fin, fout );' ]
    lines += [ '  }', f'  mcpl_close{"andgzip" if gz else ""}_outfile( fout );',
               '  mcpl_close_file( fin );', '  return 0;', '}' ]
    return '\n'.join(lines)
