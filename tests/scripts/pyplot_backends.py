
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


# NEEDS: numpy

# Test the choice of the plotting backend: matplotlib for windows, unicode (or
# else ascii) for the terminal with terminal=True, and ascii with
# terminal='ascii', and by the extension for files; with the errors when plots
# can not be shown in a window, and the -t and -o options of mcpltool.

import os
import subprocess
import sys

import mcpldev as mcpl
from mcpldev import _plotting
from mcpldev._figures import Figure, Panel, Text
from mcpldev._plotregistry import _backend_class, _save_backend, _show_backend
from MCPLTestUtils.dirs import test_data_dir

example_file = test_data_dir.joinpath('example.mcpl')
fig = Figure( title = 'A figure', panels = [ Panel( items = [ Text('Hello') ] ) ] )

def expect_error( title, fct ):
    try:
        fct()
        print(f'{title}: no error')
    except mcpl.MCPLError as e:
        print(f'{title}: MCPLError: {e}')

def test_choice():
    #(the tests run with UTF-8 output, so plots in the terminal are drawn
    #with unicode):
    for terminal in ( True, 'ascii' ):
        print(f'terminal={terminal!r}: {_show_backend(terminal).name}')
    for fn in ( 'auto.txt', 'auto.pdf', 'auto.png', 'auto.svg' ):
        print(f'saving {fn}: {_save_backend(fn).name}')
    for fn in ( 'auto.txt', 'auto.pdf' ):
        print(f'save(fig, {fn!r}) created {_plotting.save(fig, fn)}')
    for fn in ( 'auto.html', 'auto', 'auto.jpg' ):
        expect_error(f'save(fig, {fn!r})', lambda fn = fn : _plotting.save(fig, fn))

def test_window_errors():
    #Plots are only shown in a window when matplotlib can do it (with an
    #error saying how to show them in the terminal):
    cls = _backend_class('matplotlib')
    saved = cls.__dict__['is_available']
    try:
        cls.is_available = classmethod(lambda c : False)
        expect_error('show(fig) without matplotlib', lambda : _plotting.show(fig))
        expect_error("save(fig, 'x.png') without matplotlib",
                     lambda : _plotting.save(fig, 'x.png'))
    finally:
        cls.is_available = saved
    code = f'import mcpldev; mcpldev.histogram({str(example_file)!r},"ekin/MeV;bins=3").plot()'
    rv = subprocess.run([sys.executable, '-c', code],
                        capture_output=True, encoding='utf-8', check=False,
                        env=dict(os.environ, MPLBACKEND='agg'))
    err = [ e for e in rv.stderr.splitlines() if e.startswith('mcpldev._common.MCPLError') ]
    print(f'plot() with MPLBACKEND=agg: exit code {rv.returncode}')
    print('\n'.join(err))

def test_tool_backends():
    #-w shows the histogram with matplotlib, and -t in the terminal, and -o
    #saves it (as .png, .pdf, or .svg with -w and .txt with -t):
    h = 'ekin/MeV;bins=3;display_by=single'
    for args, env in ( ( ['-t'], {} ), ( ['-t','-o','tool1.txt'], {} ),
                       ( ['-w','-o','tool2.svg'], {} ), ( ['-w','-o','tool3.txt'], {} ),
                       ( ['-t','-o','tool4.svg'], {} ),
                       #(matplotlib can not show the plot without a display):
                       ( ['-w'], { 'MPLBACKEND' : 'agg' } ) ):
        sys.stdout.flush()
        #(with UTF-8 output, also on Windows, so the plots in the terminal are
        #drawn with the unicode backend):
        #(with the errors, from standard error, in the output):
        rv = subprocess.run([sys.executable, '-m', 'mcpldev', args[0], '-H', h,
                             *args[1:], str(example_file)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding='utf-8', check=False,
                            env=dict(os.environ, PYTHONIOENCODING='utf-8', **env))
        print(f'==> mcpltool {args[0]} -H {h} {" ".join(args[1:])}'
              f'{" with "+str(env) if env else ""}: exit code {rv.returncode}')
        for line in rv.stdout.splitlines()[:4]:
            print(f'   | {line}')

def test_can_show():
    #Whether the matplotlib backend can show plots, also on systems where
    #matplotlib picks a window backend without a display (like FreeBSD), with a
    #stand-in for matplotlib (so this works without it):
    import types

    from mcpldev._plotbackend_mpl import Backend as MplBackend
    saved = { k : sys.modules.get(k) for k in ( 'matplotlib', 'matplotlib.rcsetup',
                                                'matplotlib.backends' ) }
    saved_env = { k : os.environ.get(k) for k in ( 'DISPLAY', 'WAYLAND_DISPLAY' ) }
    saved_platform = sys.platform
    try:
        for platform, display, name in ( ('freebsd15','','tkagg'), ('freebsd15',':0','tkagg'),
                                         ('linux','','tkagg'), ('darwin','','macosx'),
                                         ('freebsd15','','agg'), ('freebsd15','','webagg'),
                                         ('freebsd15','','module://matplotlib_inline.backend_inline') ):
            fake = types.ModuleType('matplotlib')
            fake.get_backend = lambda n=name : n
            fake.rcsetup = types.ModuleType('matplotlib.rcsetup')
            fake.rcsetup.non_interactive_bk = [ 'agg', 'pdf', 'svg' ]
            sys.modules['matplotlib'], sys.modules['matplotlib.rcsetup'] = fake, fake.rcsetup
            sys.modules['matplotlib.backends'] = None#(as not available)
            sys.platform = platform
            for k in saved_env:
                os.environ.pop(k,None)
            if display:
                os.environ['DISPLAY'] = display
            print(f'can show plots on {platform} with display {display!r} and backend'
                  f' {name}: {MplBackend.can_show()}')
    finally:
        sys.platform = saved_platform
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k,None)
            else:
                sys.modules[k] = v
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k,None)
            else:
                os.environ[k] = v

if __name__ == '__main__':
    test_choice()
    test_window_errors()
    test_tool_backends()
    test_can_show()
