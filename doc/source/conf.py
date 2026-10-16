
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

#Role for marking freely available publications (styled in custom.css), as in
#:openaccess:`open access`, and substitutions for non-ASCII letters (like
#|auml|, as the sources only have ASCII characters):
rst_prolog = """
.. role:: openaccess
.. include:: <isolat1.txt>
"""
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

# -- Persistent URLs -----------------------------------------------------------
#
# The URL of a page is given by its name (the "key" of the page, as in
# https://.../usage_cmdline/), and the URLs of sections by explicit labels
# (".. _<page>-<key>:" before the section, as in .../usage_cmdline/#usage...).
# This way, URLs do not change when titles are edited or the website is
# reorganised. The build fails if a page is added, removed or renamed without
# updating the list below, or if a section has no such label.

_page_keys = [ 'index', 'get', 'get_source', 'news', 'file_contents', 'usage',
               'usage_cmdline', 'usage_c', 'usage_cpp', 'usage_python',
               'usage_python_advanced', 'usage_expressions', 'hooks',
               'hooks_geant4', 'hooks_mcstas', 'hooks_mcxtrace',
               'hooks_mcnp', 'hooks_phits', 'hooks_others', 'format',
               'format_statsum', 'cmdline', 'c_api', 'python_api', 'cpp_api',
               'about',
               'contact', 'license' ]
#Files which are only included in other pages:
_included_files = [ 'cite' ]

def _check_page_keys( app ):
    found = { f.stem for f in _docsrc.glob('*.rst') } - set(_included_files)
    if found != set(_page_keys):
        from sphinx.errors import ConfigError
        raise ConfigError(
            'The pages in doc/source do not match _page_keys in conf.py'
            f' (new: {sorted(found-set(_page_keys))}, missing:'
            f' {sorted(set(_page_keys)-found)}). The names of pages are part'
            ' of their URLs, so they should only change deliberately (then'
            ' update _page_keys).' )

def _check_section_labels( app, docname, source ):
    """All sections (except the title of the page) must have an explicit
    label <docname>-<key> right before them."""
    import re
    lines = source[0].splitlines()
    under = re.compile(r'^([=\-~^"*+#`\'])\1{2,}$')
    headings = []
    for i in range( 1, len(lines) ):
        if ( under.match(lines[i]) and lines[i-1].strip()
             and not under.match(lines[i-1])
             and len(lines[i]) >= len(lines[i-1].rstrip())
             and not lines[i-1].startswith((' ','..')) ):
            #(skip overlined titles: the line before the heading text):
            overlined = i >= 2 and under.match(lines[i-2])
            headings.append( ( i-1, overlined ) )
    bad = []
    for n, (i, overlined) in enumerate(headings):
        if n == 0:
            continue#the title of the page
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        m = re.match(r'^\.\. _([a-z0-9_]+)-([a-z0-9_-]+):$', lines[j]) if j >= 0 else None
        if not m or m.group(1) != docname:
            bad.append( lines[i].strip() )
    if bad:
        from sphinx.errors import ExtensionError
        raise ExtensionError(
            f'Sections in {docname}.rst without a label like ".. _{docname}-key:"'
            ' (which gives them a persistent URL): ' + '; '.join(bad) )

def _labels_as_section_ids( app, doctree ):
    """Make the label of each section its primary id (used in the URLs of the
    menu, the table of contents and the links to the section), keeping the id
    made from the title as a secondary id. Docutils adds the id of the label
    (referred to by the target node of the label) after the one from the
    title."""
    from docutils import nodes
    label_ids = { t['refid'] for t in doctree.findall(nodes.target)
                  if t.get('refid') }
    for section in doctree.findall(nodes.section):
        labels = [ i for i in section['ids'] if i in label_ids ]
        if labels:
            section['ids'] = labels + [ i for i in section['ids']
                                        if i not in labels ]

def setup( app ):
    app.connect( 'autodoc-process-docstring', _plaintext_docstring )
    #(before Sphinx records the ids for the menu and references):
    app.connect( 'doctree-read', _labels_as_section_ids, priority = 100 )
    app.connect( 'builder-inited', _check_page_keys )
    app.connect( 'source-read', _check_section_labels )
    app.connect( 'builder-inited', lambda app : _run_doxygen() )

# -- Generated content ---------------------------------------------------------

def _run_doxygen():
    """XML of the C++ API (mcplcpp.h), for Breathe. Only rerun when the header
    changed."""
    import shutil

    from mcpl_repo_tools.cppapidoc import doxygen_missing_msg, header_file, run_doxygen
    if not shutil.which('doxygen'):
        from sphinx.errors import ConfigError
        raise ConfigError(doxygen_missing_msg)
    xmldir = _autogendir / 'doxygen_xml'
    stamp = xmldir / 'index.xml'
    if ( not stamp.is_file()
         or stamp.stat().st_mtime < header_file().stat().st_mtime ):
        warnings = run_doxygen( xmldir )
        for w in warnings:
            print(f'Doxygen warning: {w}')
    return xmldir

def _cmd_output( name, cmd, cwd = None ):
    """Write the output of a command to a file in the autogen directory (to be
    included in the pages with literalinclude)."""
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(_pysrc)]
                                        + [ e for e in [env.get('PYTHONPATH')]
                                            if e ])
    p = subprocess.run( cmd, capture_output = True, env = env, check = False,
                        cwd = cwd )
    if p.returncode != 0 or p.stderr:
        raise RuntimeError(f'Command failed: {cmd}\n{p.stderr.decode()}')
    out = _autogendir / name
    txt = p.stdout.decode()
    if not out.is_file() or out.read_text() != txt:
        out.write_text(txt)

_autogendir.mkdir(parents=True,exist_ok=True)
#(Doxygen is run when the build starts, see setup):
breathe_projects = { 'mcplcpp': str(_autogendir / 'doxygen_xml') }
breathe_default_project = 'mcplcpp'
breathe_domain_by_extension = { 'h' : 'cpp' }
#(with the program name of the installed command, not "python -m mcpl"):
_cmd_output( 'mcpltool_help.txt',
             [ sys.executable, '-c',
               'import mcpl;mcpl.app_mcpltool(["mcpltool","--help"])' ] )

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

def _stats_outputs():
    """Output of mcpltool --stats for the example file of the repository:
    the text summary, the PDF made with --pdf, the overview figure (shown on
    the front page) and a few of the other figures (like the ones shown with
    --gui). Only regenerated when the example file changed."""
    import shutil
    example = _reporoot / 'examples' / 'example.mcpl'
    workdir = _autogendir / 'stats'
    stamp = workdir / 'done.txt'
    if stamp.is_file() and stamp.stat().st_mtime > example.stat().st_mtime:
        return
    workdir.mkdir(exist_ok=True)
    shutil.copy( example, workdir / 'example.mcpl' )
    tool = [ sys.executable, '-m', 'mcpl' ]
    _cmd_output( 'stats_example.txt', tool + [ '--stats', 'example.mcpl' ],
                 cwd = workdir )
    _cmd_output( 'stats_pdf.log', tool + [ '--stats', '--pdf', 'example.mcpl' ],
                 cwd = workdir )
    ( workdir / 'mcpl.pdf' ).replace( _autogendir / 'mcpltool_stats.pdf' )
    code = ( 'import mcpl, mcpl.plotting as p;'
             'figs = mcpl.stats_figures(mcpl.collect_stats("example.mcpl"));'
             'save = lambda i, fn: p.save([figs[i]], fn, backend="matplotlib");'
             f'save(0, {str(_autogendir/"stats_overview.png")!r});'
             f'save(1, {str(_autogendir/"stats_pdgcode.png")!r});'
             f'save(4, {str(_autogendir/"stats_x.png")!r});'
             f'save(9, {str(_autogendir/"stats_uz.png")!r})' )
    _cmd_output( 'stats_figures.log', [ sys.executable, '-c', code ],
                 cwd = workdir )
    stamp.write_text('done\n')

_latest_news()
#The "Building from source" page, from the same source as INSTALL.md:
def _get_source_page():
    from mcpl_repo_tools.installdoc import produce_get_source_rst
    _autogendir.mkdir( parents = True, exist_ok = True )
    out = _autogendir / 'get_source_body.rst'
    content = produce_get_source_rst()
    if not out.is_file() or out.read_text() != content:
        out.write_text( content )
_get_source_page()

#The C API reference, from the declarations and comments in mcpl.h:
def _c_api_page():
    from mcpl_repo_tools.capidoc import produce_c_api_rst
    _autogendir.mkdir( parents = True, exist_ok = True )
    out = _autogendir / 'c_api_body.rst'
    content = produce_c_api_rst()
    if not out.is_file() or out.read_text() != content:
        out.write_text( content )
_c_api_page()
#(the macro in front of all functions in mcpl.h):
c_id_attributes = [ 'MCPL_API' ]
#(standard C types, which are not documented here):
nitpick_ignore += [ ( 'c:identifier', t )
                   for t in ( 'int8_t', 'uint8_t', 'int16_t', 'uint16_t',
                              'int32_t', 'uint32_t', 'int64_t', 'uint64_t',
                              'size_t', 'wchar_t' ) ]
_stats_outputs()

#The examples on the usage_cmdline page: each command is run (in a scratch
#directory with a copy of the example file), and the command and its output
#are shown, so the page is always up to date with the actual tool:
_cmdline_examples = [
    #(name, command, and whether it is hidden; in the order they are run):
    ( 'inspect', 'mcpltool example.mcpl', False ),
    ( 'extract_p',
      'mcpltool --extract -p2112 example.mcpl justneutrons.mcpl', False ),
    ( 'extract_ls',
      'mcpltool --extract -l1 -s123 example.mcpl selected.mcpl', False ),
    ( 'setup1',
      'mcpltool --extract --no-comment -l300 example.mcpl file1.mcpl', True ),
    ( 'setup2', ( 'mcpltool --extract --no-comment -s300 -l300'
                  ' example.mcpl file2.mcpl' ), True ),
    ( 'setup3',
      'mcpltool --extract --no-comment -s600 example.mcpl file3.mcpl', True ),
    ( 'merge', ( 'mcpltool --merge newfile.mcpl'
                 ' file1.mcpl file2.mcpl file3.mcpl' ), False ),
    ( 'dryrun', ( 'mcpltool --extract -d --select "ekin < 1MeV"'
                  ' example.mcpl slow.mcpl' ), False ),
    ( 'select_edit', ( 'mcpltool --extract example.mcpl slow.mcpl -pneutron'
                       ' --select "ekin < 1MeV && hypot(x,y) < 10cm"'
                       ' --edit "z = 0cm, wavelength = 1.8Aa"' ), False ),
    ( 'forcemerge',
      'mcpltool --forcemerge newfile2.mcpl example.mcpl slow.mcpl', False ),
    ( 'hist', ( 'mcpltool --hist "ekin/MeV" --logx --split pdgcode'
                ' --output cmdline_hist.png example.mcpl' ), True ),
    ( 'text', 'mcpltool --text example.mcpl out.txt', False ),
]

def _cmdline_examples_outputs():
    """Run the commands of _cmdline_examples, and write each (non-hidden)
    command and its output to cmdline_<name>.txt in the autogen directory.
    Only rerun when the example file, this file or the mcpl Python sources
    changed."""
    import re
    import shlex
    import shutil
    def shown( cmd ):
        #The command, broken into lines (before options) of at most 78 chars:
        #(quoted arguments are kept together with the option before them):
        units = []
        for w in re.findall( r'"[^"]*"|\S+', cmd ):
            if w.startswith('"') and units:
                units[-1] += ' ' + w
            else:
                units.append( w )
        lines = [ '$' ]
        for u in units:
            if len(lines[-1]) + 1 + len(u) > 76 and u.startswith('-'):
                lines[-1] += ' \\'
                lines.append( '   ' )
            lines[-1] += ' ' + u
        return '\n'.join( lines ) + '\n'
    example = _reporoot / 'examples' / 'example.mcpl'
    workdir = _autogendir / 'cmdline'
    stamp = workdir / 'done.txt'
    sources = [ example, pathlib.Path(__file__) ] + list(_pysrc.rglob('*.py'))
    if ( stamp.is_file() and stamp.stat().st_mtime
         > max( f.stat().st_mtime for f in sources ) ):
        return
    shutil.rmtree( workdir, ignore_errors = True )
    workdir.mkdir( parents = True )
    shutil.copy( example, workdir / 'example.mcpl' )
    #(run like the installed mcpltool command, with that program name):
    code = 'import sys;sys.argv[0]="mcpltool";from mcpl._cli import main;main()'
    tool = [ sys.executable, '-c', code ]
    for name, cmd, hidden in _cmdline_examples:
        args = shlex.split(cmd)
        assert args[0] == 'mcpltool'
        _cmd_output( f'cmdline_{name}.out', tool + args[1:], cwd = workdir )
        out = _autogendir / f'cmdline_{name}.out'
        if not hidden:
            txt = shown( cmd ) + out.read_text()
            dest = _autogendir / f'cmdline_{name}.txt'
            if not dest.is_file() or dest.read_text() != txt:
                dest.write_text( txt )
        out.unlink()
    ( workdir / 'cmdline_hist.png' ).replace( _autogendir / 'cmdline_hist.png' )
    lines = ( workdir / 'out.txt' ).read_text().splitlines()
    ( _autogendir / 'cmdline_text_head.txt' ).write_text(
        '\n'.join( lines[:10] ) + '\n' )
    stamp.write_text('done\n')

_cmdline_examples_outputs()

# -- Options for HTML output ---------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_css_files = ['custom.css']
#(collapsible entries on the API reference pages):
html_js_files = ['apitoggle.js']
#The MCPL logo (from https://github.com/mctools/mcpl-logo), in the variant for
#dark backgrounds, since it is on the dark background of the sidebar:
html_logo = '_static/mcpl-logo-dark.svg'
html_favicon = '_static/favicon.svg'
html_theme_options = {
    'logo_only': True,#(the logo has the name)
    'collapse_navigation' : False,
    'sticky_navigation': False,#(the menu does not scroll along with the page)
    'navigation_with_keys': True,#navigate with left/right arrow keys
    'navigation_depth': 4,
}
