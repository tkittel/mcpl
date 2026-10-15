
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


# Configuration file for the Sphinx documentation builder. For the full list
# of configuration values, see:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import pathlib
import subprocess
import sys

_docsrc = pathlib.Path(__file__).parent.absolute()
_reporoot = _docsrc.parent.parent
_blddir = _docsrc.parent / 'build'
_autogendir = _blddir / 'autogen'
assert ( _reporoot / 'mcpl_python' / 'src' / 'mcpl' / '__init__.py' ).is_file()

#The Python API is documented directly from the sources in the repository:
_pysrc = _reporoot / 'mcpl_python' / 'src'
sys.path.insert(0,str(_pysrc))
#As are the developer tools (for running Doxygen):
sys.path.insert(0,str(_reporoot / 'devel' / 'pypath'))
os.environ['PYTHONUNBUFFERED'] = '1'

# -- Project information -------------------------------------------------------

project = 'MCPL'
copyright = '2015-2026, MCPL developers'
author = 'MCPL developers'
version = ( _reporoot / 'VERSION' ).read_text().strip()
release = version

# -- General configuration -----------------------------------------------------

nitpicky = True
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx_toolbox.sidebar_links',
    'sphinx_toolbox.github',
    'sphinx_toolbox.collapse',
    'breathe',
]

templates_path = ['_templates']
exclude_patterns = []

#For sphinx_toolbox.sidebar_links and sphinx_toolbox.github:
github_username = 'mctools'
github_repository = 'mcpl'

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
}

#Python API:
autodoc_member_order = 'bysource'
autodoc_default_options = { 'members': True, 'undoc-members': False }

#C++ API: not linking to the file (which is not documented on its own):
breathe_show_include = False

#Types which are not (yet) documented on the website: the C types (the C API
#reference is still missing), and the internals of the C++ API:
nitpick_ignore = [ ('cpp:identifier', n) for n in ( 'mcpl_particle_t',
                                                     'mcpl_file_t',
                                                     'mcpl_outfile_t',
                                                     'detail',
                                                     'detail::FilenameArg',
                                                     'iterator' ) ]
#(mcpl.plotting.Backend is an alias of this class):
nitpick_ignore += [ ('py:class','mcpl._plotbackend.PlotBackend') ]

def _plaintext_docstring( app, what, name, obj, options, lines ):
    """The docstrings of the Python API are plain text (as shown by help()),
    not reST. Indented blocks after lines ending with a colon are code
    examples, which become literal blocks (unless they are lists, with items
    starting with "* "), and characters with special meaning in reST are
    escaped elsewhere."""
    import re
    def indent( line ):
        return len(line) - len(line.lstrip())
    def is_item( line ):
        return line.lstrip().startswith('* ')
    out, in_literal, literal_indent = [], False, 0
    list_indent = None#indentation of the items of the current list
    for i, line in enumerate(lines):
        if in_literal:
            if line.strip() and indent(line) <= literal_indent:
                in_literal = False
            else:
                out.append(line)
                continue
        nxt = next( ( e for e in lines[i+1:] if e.strip() ), None )
        starts_block = ( line.rstrip().endswith(':')
                         and nxt is not None
                         and indent(nxt) > indent(line)
                         and not is_item(nxt) )
        item = is_item(line)
        if ( list_indent is not None and line.strip()
             and not item and indent(line) <= list_indent ):
            list_indent = None#text after the list
        if item:
            #(lists must be separated from preceding text by an empty line):
            if list_indent is None and out and out[-1].strip():
                out.append('')
            list_indent = indent(line)
            prefix, text = line[:list_indent+2], line[list_indent+2:]
        else:
            prefix, text = '', line
        text = re.sub( r'([*`|\\])', r'\\\1', text )
        text = re.sub( r'(\w)_(?=\W|$)', r'\1\\_', text )
        line = prefix + text
        if starts_block:
            line = line.rstrip()[:-1] + '::'
            in_literal, literal_indent = True, indent(line)
            if i + 1 < len(lines) and lines[i+1].strip():
                line += '\n'
        out.append(line)
    lines[:] = '\n'.join(out).splitlines()

def setup( app ):
    app.connect( 'autodoc-process-docstring', _plaintext_docstring )

# -- Generated content ---------------------------------------------------------

def _run_doxygen():
    """XML of the C++ API (mcplcpp.h), for Breathe. Only rerun when the header
    changed."""
    from mcpl_repo_tools.cppapidoc import header_file, run_doxygen
    xmldir = _autogendir / 'doxygen_xml'
    stamp = xmldir / 'index.xml'
    if ( not stamp.is_file()
         or stamp.stat().st_mtime < header_file().stat().st_mtime ):
        warnings = run_doxygen( xmldir )
        for w in warnings:
            print(f'Doxygen warning: {w}')
    return xmldir

def _cmd_output( name, cmd ):
    """Write the output of a command to a file in the autogen directory (to be
    included in the pages with literalinclude)."""
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(_pysrc)]
                                        + [ e for e in [env.get('PYTHONPATH')]
                                            if e ])
    p = subprocess.run( cmd, capture_output = True, env = env, check = False )
    if p.returncode != 0 or p.stderr:
        raise RuntimeError(f'Command failed: {cmd}\n{p.stderr.decode()}')
    out = _autogendir / name
    txt = p.stdout.decode()
    if not out.is_file() or out.read_text() != txt:
        out.write_text(txt)

_autogendir.mkdir(parents=True,exist_ok=True)
breathe_projects = { 'mcplcpp': str(_run_doxygen()) }
breathe_default_project = 'mcplcpp'
breathe_domain_by_extension = { 'h' : 'cpp' }
_cmd_output( 'pymcpltool_help.txt',
             [ sys.executable, '-m', 'mcpl', '--help' ] )

def _latest_news( n = 4 ):
    """The first n items of the news page, for the front page"""
    items, cur = [], None
    for line in ( _docsrc / 'news.rst' ).read_text().splitlines():
        if line.startswith('* '):
            if cur:
                items.append(cur)
            cur = [line]
        elif cur is not None and line.startswith('  '):
            cur.append(line)
        elif cur is not None and not line.strip():
            items.append(cur)
            cur = None
    if cur:
        items.append(cur)
    txt = '\n\n'.join( '\n'.join(e) for e in items[:n] ) + '\n'
    out = _autogendir / 'news_latest.rst'
    if not out.is_file() or out.read_text() != txt:
        out.write_text(txt)

def _stats_figure():
    """Overview of the particles in the example file (as made by pymcpltool
    --stats), shown on the front page."""
    out = _autogendir / 'stats_overview.png'
    example = _reporoot / 'examples' / 'example.mcpl'
    if out.is_file() and out.stat().st_mtime > example.stat().st_mtime:
        return
    code = ( 'import mcpl, mcpl.plotting;'
             f'st = mcpl.collect_stats({str(example)!r});'
             'mcpl.plotting.save(mcpl.stats_figures(st)[:1],'
             f' {str(out)!r}, backend="matplotlib")' )
    _cmd_output( 'stats_overview.log', [ sys.executable, '-c', code ] )

_latest_news()
_stats_figure()

# -- Options for HTML output ---------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_css_files = ['custom.css']
html_theme_options = {
    'logo_only': False,
    'collapse_navigation' : False,
    'sticky_navigation': True,#sidebar stays in place while contents scrolls
    'navigation_with_keys': True,#navigate with left/right arrow keys
    'navigation_depth': 4,
}
