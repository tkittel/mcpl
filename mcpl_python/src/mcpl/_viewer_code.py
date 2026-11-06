
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

"""The command (of mcpltool) and the code (in Python, C++, and C) doing the
same as the viewer: histograms of plots, or writing the edited particles to
a new file (see Viewer.code). The C++ and C code is generated
from the expressions (see _expr_ast2c and _expr_ast2cpp)."""

__all__ = []

#The kinds of code, as (key, label):
kinds = ( ( 'command', 'Command line' ), ( 'python', 'Python' ), ( 'cpp', 'C++' ),
          ( 'c', 'C' ) )

def _options( job ):
    """The options of mcpltool for the range and edit of the job"""
    from ._extract import _range_options
    return _range_options(job.skip,job.limit,job.edit)

class _Job:
    """What the code does: the particles (in the file filename, in the range
    of skip and limit, edited with the expression edit, or None), and then
    the histograms of the plots (if plots is not None), or else writing them
    to the file out (with the comment in its header, if any, and its stat:sum
    entries scaled to the range or not available, as given by statsums, see
    _expr_ast2code), for files with the userdata layout (or None)"""
    def __init__( self, filename, skip, limit, edit, plots, out,
                  statsums, layout = None, comment = None ):
        self.filename, self.skip, self.limit = filename, skip or 0, limit
        self.edit = edit
        self.plots, self.out, self.statsums = plots, out, statsums
        self.layout, self.comment = layout, comment

def code( job, progname ):
    """The command and the code of the job, as a dict with the keys of kinds
    (without C++ and C for histograms, which C++ and C can not make)"""
    res = { 'command' : _command(job,progname), 'python' : _python(job) }
    if job.plots is None:
        res.update( { 'cpp' : _cpp(job), 'c' : _c(job) } )
    return res

def _command( job, prog ):
    from ._extract import _shell_path
    fn, opts = _shell_path(job.filename), _options(job)
    if job.plots is not None:
        #(a command for each plot, as mcpltool shows one histogram):
        from ._extract import _option_arg
        return '\n'.join( ' '.join( [ prog, '-H', _option_arg(p,hist = True) ] + opts + [ fn ] )
                          for p in job.plots )
    out = _shell_path(job.out)
    return ' '.join( [ prog, '-x' ] + opts + [ fn, out ] )

def _python( job ):
    args = [ repr(job.filename) ]
    for name, value in ( ('skip',job.skip or None), ('limit',job.limit),
                         ('edit',job.edit) ):
        if value is not None:
            args.append(f'{name} = {value!r}')
    lines = [ 'import mcpl' ]
    if job.plots is not None:
        lines.append(f'f = mcpl.MCPLFile( {", ".join(args)} )')
        if len(job.plots) == 1:
            return '\n'.join( lines + [ f'h = mcpl.histogram( f, {job.plots[0]!r} )', 'h.plot()' ] )
        lines += [ 'hs = [ mcpl.histogram( f, p ) for p in (' ]
        lines += [ f'    {p!r},' for p in job.plots ]
        return '\n'.join( lines + [ ') ]', 'for h in hs:', '    h.plot()' ] )
    lines += [ f'fin = mcpl.MCPLFile( {", ".join(args)} )',
               f'with mcpl.MCPLOutFile( {job.out!r} ) as fout:',
               '    fout.transfer_metadata( fin )  # copy the header' ]
    if job.statsums:
        lines += [ '    for key, value in fin.stat_sum_sliced.items():  # (as mcpltool -x)',
                   '        fout.hdr_add_stat_sum( key, value )' ]
    lines += [ '    for block in fin.particle_blocks:',
               '        fout.add_particles( block )' ]
    return '\n'.join(lines)

def _generated( job, lang ):
    """The C++ or C code (lang 'cpp' or 'c') of the job"""
    from ._expressions import _edit_code
    return _edit_code(lang,job.edit,job.layout,filenames = ( job.filename, job.out ),
                      skip = job.skip,limit = job.limit,statsums = job.statsums,
                      comment = job.comment)

def _cpp( job ):
    return _generated(job,'cpp')

def _c( job ):
    return _generated(job,'c')

#Syntax highlighting of the code (which is written above, so the simple
#patterns of each kind of code are enough), as styles of ranges of the text:

_keywords = {
    'python' : ( 'import', 'for', 'in', 'with', 'as' ),
    'cpp' : ( 'int', 'auto', 'for', 'if', 'continue', 'break', 'return', 'const',
              'double' ),
    'c' : ( 'int', 'void', 'for', 'while', 'if', 'continue', 'break', 'return',
            'const', 'double' ),
}

def highlight( text, kind ):
    """The ranges of the text (code of the kind, see kinds) to show in a
    style: a list of (start, end, style), with the styles 'comment',
    'string', 'keyword', 'number', 'preprocessor', and 'option' (of
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
