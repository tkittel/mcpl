
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
    'tk' : ( 'Window with Tk (mcpltool -w)', [ '-w' ], ( 'tkinter', ) ),
    'term' : ( 'Terminal (mcpltool -t)', [ '-t' ], ( 'curses', ) ),
    'term-nocol' : ( 'Terminal without colours (mcpltool -t --color=never)',
                       [ '-t', '--color=never' ], ( 'curses', ) ),
    'term-ascii' : ( 'Terminal, ASCII only (mcpltool -t, drawing with ASCII characters)',
                     [ '-t' ], ( 'curses', ) ),
    'term-ascii-nocol' : ( 'Terminal, ASCII, no colours (... --color=never)',
                             [ '-t', '--color=never' ], ( 'curses', ) ),
    'term-8col' : ( 'Terminal with 8 colours (mcpltool -t, with TERM=xterm)',
                      [ '-t' ], ( 'curses', ) ),
}

def short_description():
    return 'Open an MCPL file in the viewer (mcpltool -w or -t, mcpl.view) of this repository'

def main( parser ):
    import argparse
    modes = '\n'.join( f'  {m:<19} {d}' for m, (d, _, _) in _modes.items() )
    parser.init( f'{short_description()}.\n\nThe modes are:\n{modes}',
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
        parser.error(f'Not a file: {args.FILE}' if f.exists()
                     else f'File not found: {args.FILE}')
    _, how, needed = _modes[args.MODE]
    needed = [ *needed, 'numpy' ] + ( [] if args.MODE.startswith('term') else [ 'matplotlib' ] )
    missing = [ m for m in needed if importlib.util.find_spec(m) is None ]
    if 'curses' in missing and sys.platform != 'win32':
        raise SystemExit( 'Error: this Python was built without the curses module,'
                          f' which the viewer mode {args.MODE} needs.' )
    if missing:
        pipnames = [ 'windows-curses' if m == 'curses' else m for m in missing ]
        raise SystemExit( f'Error: missing Python packages for the viewer mode {args.MODE}.'
                          ' Install them with:\n\n'
                          f'  {sys.executable} -m pip install {" ".join(pipnames)}\n' )
    pysrc = reporoot / 'mcpl_python' / 'src'
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join( [ str(pysrc) ]
                                         + ( [ env['PYTHONPATH'] ] if env.get('PYTHONPATH') else [] ) )
    if args.MODE == 'term-8col':
        #(a terminal type with 8 colours, for curses):
        env['TERM'] = 'xterm'
    #(the viewer in the terminal with the drawing of the plots of the mode, see
    #_term_code):
    cmd = ( [ sys.executable, '-c', _term_code( args.MODE.startswith('term-ascii') ) ]
            if args.MODE.startswith('term') else [ sys.executable, '-m', 'mcpl' ] )
    #(the file as given, run here, so the commands printed by the viewer are
    #those the user would type):
    rv = _run_child( [ *cmd, *how, args.FILE ], env = env )
    if rv:
        raise SystemExit(rv)

def _term_code( ascii ):
    """Code running mcpltool as python -m mcpl does, with the plots drawn with
    ASCII characters (as for terminals which can not show Unicode) if ascii is
    set, and otherwise with Unicode characters, which the terminal must be
    able to show (so the modes never fall back to another drawing)"""
    check = '' if ascii else (
        'from mcpl._plotbackend_text import UnicodeBackend\n'
        'if not UnicodeBackend.can_show():\n'
        '    sys.exit("Error: this terminal can not show the Unicode characters of the"\n'
        '             " viewer (the mode term-ascii draws with ASCII characters)")\n' )
    return ( 'import sys\n' + check
             + 'from mcpl import app_mcpltool\n'
             + 'from mcpl._plotregistry import _forced_backend\n'
             + f'with _forced_backend({"ascii" if ascii else "unicode"!r}):\n'
             + "    app_mcpltool(['__main__.py'] + sys.argv[1:])\n" )

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
