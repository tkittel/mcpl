
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


#The modes: (description, how the viewer is started, Python packages needed)
_modes = {
    'jup-ipympl' : ( 'JupyterLab, after %matplotlib widget (interactive plots)',
                     'jupyter', ( 'jupyterlab', 'ipywidgets', 'ipympl' ) ),
    'jup-basic' : ( 'JupyterLab, without ipympl (plots as images)',
                    'jupyter', ( 'jupyterlab', 'ipywidgets' ) ),
    'nb-ipympl' : ( 'Classic Jupyter Notebook, after %matplotlib widget',
                    'jupyter', ( 'notebook', 'ipywidgets', 'ipympl' ) ),
    'nb-basic' : ( 'Classic Jupyter Notebook, without ipympl',
                   'jupyter', ( 'notebook', 'ipywidgets' ) ),
    'mpl' : ( 'Matplotlib window (mcpltool -w -B matplotlib)',
              [ '-w', '-B', 'matplotlib' ], () ),
    'term' : ( 'Terminal (mcpltool -w -t)', [ '-w', '-t' ], ( 'curses', ) ),
    'term-nocol' : ( 'Terminal without colours (mcpltool -w -t --color=never)',
                       [ '-w', '-t', '--color=never' ], ( 'curses', ) ),
    'term-ascii' : ( 'Terminal, ASCII only (mcpltool -w -t -B ascii)',
                     [ '-w', '-t', '-B', 'ascii' ], ( 'curses', ) ),
    'term-ascii-nocol' : ( 'Terminal, ASCII, no colours (... -B ascii --color=never)',
                             [ '-w', '-t', '-B', 'ascii', '--color=never' ], ( 'curses', ) ),
    'term-8col' : ( 'Terminal with 8 colours (mcpltool -w -t, with TERM=xterm)',
                      [ '-w', '-t' ], ( 'curses', ) ),
}

def short_description():
    return 'Open an MCPL file in the viewer (mcpltool -w, mcpl.view) of this repository'

def main( parser ):
    import argparse
    modes = '\n'.join( f'  {m:<19} {d}' for m, (d, _, _) in _modes.items() )
    parser.init( f'{short_description()}.\n\nThe modes are:\n{modes}\n\n'
                 'In Jupyter, the notebook is in a temporary directory (with a\n'
                 'link to the file), which is removed when Jupyter is stopped.',
                 formatter_class = argparse.RawDescriptionHelpFormatter )
    parser.add_argument( 'MODE', choices = list(_modes), metavar = 'MODE',
                         help = 'How the viewer is shown (see above)' )
    parser.add_argument( 'FILE', help = 'The MCPL file to view' )
    if not parser.has_args():
        parser.print_help()
        return
    args = parser.parse_args()
    import importlib.util
    import os
    import pathlib
    import sys

    from .dirs import reporoot
    f = pathlib.Path(args.FILE).absolute()
    if not f.is_file():
        parser.error(f'File not found: {args.FILE}')
    _, how, needed = _modes[args.MODE]
    needed = [ *needed, 'matplotlib', 'numpy' ]
    missing = [ m for m in needed if importlib.util.find_spec(m) is None ]
    if missing:
        pipnames = [ 'windows-curses' if m == 'curses' else m for m in missing ]
        raise SystemExit( f'Error: missing Python packages for the viewer mode {args.MODE}.'
                          ' Install them with:\n\n'
                          f'  {sys.executable} -m pip install {" ".join(pipnames)}\n' )
    pysrc = reporoot / 'mcpl_python' / 'src'
    if how == 'jupyter':
        _run_jupyter( f, pysrc, app = 'lab' if args.MODE.startswith('jup') else 'notebook',
                      widget = args.MODE.endswith('ipympl') )
        return
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join( [ str(pysrc) ]
                                         + ( [ env['PYTHONPATH'] ] if env.get('PYTHONPATH') else [] ) )
    if args.MODE == 'term-8col':
        #(a terminal type with 8 colours, for curses):
        env['TERM'] = 'xterm'
    #(the file as given, run here, so the commands printed by the viewer are
    #those the user would type):
    rv = _run_child( [ sys.executable, '-m', 'mcpl', *how, args.FILE ], env = env )
    if rv:
        raise SystemExit(rv)

def _run_child( cmd, **kwargs ):
    """Run the command and return its exit code. Ctrl-C (SIGINT, which goes to
    all processes of the terminal) is left to the command, e.g. so the viewer
    can quit and print its commands: subprocess.run would kill it."""
    import signal
    import subprocess
    #(a handler doing nothing, not SIG_IGN, which the command would inherit):
    old = signal.signal( signal.SIGINT, lambda *args : None )
    try:
        return subprocess.run( cmd, check = False, **kwargs ).returncode
    finally:
        signal.signal( signal.SIGINT, old )

def _run_jupyter( f, pysrc, app, widget ):
    import json
    import pathlib
    import sys
    import tempfile
    cells = [ ( 'markdown', ( f'Viewer of `{f.name}` (from `{f}`), with the'
                              f' mcpl package in `{pysrc}`.' ) ),
              ( 'code', ( 'import sys\n'
                          f'sys.path.insert(0,{str(pysrc)!r})\n'
                          'import mcpl\n'
                          'print(mcpl.__file__)' ) ),
              *( [ ( 'code', '%matplotlib widget' ) ] if widget else [] ),
              ( 'code', f'v = mcpl.view({f.name!r})' ) ]
    nb = { 'nbformat' : 4, 'nbformat_minor' : 5,
           'metadata' : { 'kernelspec' : { 'name' : 'python3',
                                           'display_name' : 'Python 3',
                                           'language' : 'python' } },
           'cells' : [ { 'cell_type' : t, 'metadata' : {}, 'id' : f'cell{i}',
                         'source' : src, **( { 'outputs' : [],
                                               'execution_count' : None }
                                             if t == 'code' else {} ) }
                       for i, (t, src) in enumerate(cells) ] }
    with tempfile.TemporaryDirectory( prefix = 'mcpl_viewer_' ) as tmpdir:
        d = pathlib.Path(tmpdir)
        ( d / f.name ).symlink_to(f)
        ( d / 'viewer.ipynb' ).write_text( json.dumps(nb,indent=1) + '\n' )
        print(f'Notebook in {d} (removed when Jupyter is stopped with Ctrl-C)',
              flush = True)
        _run_child( [ sys.executable, '-m', 'jupyter', app, 'viewer.ipynb' ], cwd = d )
