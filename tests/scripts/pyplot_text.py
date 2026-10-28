
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

# Test the plotting backends drawing figures as text (unicode and ascii), with
# fixed sizes so the output does not depend on the terminal.

import contextlib
import io
import os
import pathlib
import subprocess
import sys

import mcpldev as mcpl
import numpy as np
from mcpldev.plotting import Figure, Panel, StepHist, Text, resolution
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.plots import example_figures

example_file = test_data_dir.joinpath('example.mcpl')

def show(figs, backend, width=72, height=8):
    opts = { f'{backend}_width' : width, f'{backend}_height' : height }
    print(f'==> {backend} backend, width {width}, height {height}:')
    mcpl.plotting.show(figs, backend=backend, **opts)

def test_histograms():
    h = mcpl.histogram(example_file, 'ekin/MeV', logx=True, bins=50, display_by='single')
    for backend in ('unicode','ascii'):
        show(h.figure(), backend)
    #Several curves (markers and legend), and a logarithmic y axis:
    h = mcpl.histogram(example_file, 'ekin/MeV', logx=True, bins=50,
                       display_by='pdgcode')
    show(h.figure(logy=True), 'unicode', height=10)
    h = mcpl.histogram(example_file, 'acos(uz)/deg', range=(0,180), bins=36,
                       display_by='x > 0cm')
    show(h.figure(), 'ascii')
    #2D histogram:
    h = mcpl.histogram2d(example_file, 'x/cm', 'y/cm', bins=30,
                         pick='pdgcode == neutron')
    for backend in ('unicode','ascii'):
        show(h.figure(), backend, height=12)

def test_stats():
    figs = example_figures(mcpl,example_file)
    show(figs[0], 'ascii')
    show(figs[1:3], 'unicode', height=6)
    show(Figure( title='Empty', panels=[ Panel( title='No data here',
                                               items=[ Text('No data') ] ) ] ), 'unicode')

def test_files_and_options():
    figs = example_figures(mcpl,example_file)[:2]
    for backend in ('unicode','ascii'):
        files = mcpl.plotting.save(figs, f'stats_{backend}.txt', backend=backend,
                                   **{ f'{backend}_width' : 60 })
        data = pathlib.Path(files[0]).read_bytes()
        widths = { len(line) for line in data.decode('utf-8').splitlines() }
        print(f'{backend}: saved {files}, {len(data.splitlines())} lines, max width'
              f' {max(widths)}, ascii only: {data.isascii()}')
    for bad in ( { 'backend' : 'ascii', 'unicode_width' : 50 },
                 { 'backend' : 'unicode', 'filename' : 'x.pdf' } ):
        try:
            fn = bad.pop('filename', None)
            if fn:
                mcpl.plotting.save(figs, fn, **bad)
            else:
                mcpl.plotting.show(figs, **bad)
        except mcpl.MCPLError as e:
            print(f'{bad}: MCPLError: {e}')
    #(the other backends depend on the installed packages):
    avail = mcpl.plotting.available_backends()
    print(f'unicode and ascii backends always available, as the last ones:'
          f' {avail[-2:] == ["unicode","ascii"]}')
    #In terminals which can not show its characters, the unicode backend can
    #not show plots, so plots for the terminal are shown with the ascii
    #backend, while explicitly requesting the unicode backend is an error:
    env = dict(os.environ, PYTHONIOENCODING='ascii',
               PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    for args in ( 'terminal=True,ascii_width=40,ascii_height=5',
                  'backend="unicode",unicode_width=40,unicode_height=5' ):
        code = ( f'import mcpldev; mcpldev.histogram({str(example_file)!r},"ekin/MeV",'
                 f'bins=10,display_by="single").plot({args})' )
        rv = subprocess.run([sys.executable,'-c',code], capture_output=True,
                            env=env, check=False)
        print(f'plot({args}) with PYTHONIOENCODING=ascii: exit code {rv.returncode},'
              f' output only ASCII: {(rv.stdout + rv.stderr).isascii()}')
        #(splitlines, since the output has \r\n line endings on Windows):
        out = rv.stdout.decode().splitlines()
        err = [ e for e in rv.stderr.decode().splitlines()
                if e.startswith('mcpldev._common.MCPLError') ]
        print('\n'.join(out + err).rstrip())

def test_resolution():
    #The text backends know their resolution (number of columns and rows)
    #before seeing any data, so histograms can be made to match it:
    from mcpldev._plotbackend_text import UnicodeBackend
    print('resolution unicode (width 60):',resolution('unicode',unicode_width=60))
    print('resolution ascii (width 50, height 6):',
          resolution('ascii',ascii_width=50,ascii_height=6))
    print('resolution test backend:',resolution('test'))
    #A histogram with one bin per column is drawn without any resampling: a
    #single filled bin fills exactly its column, in all rows:
    ncols, nrows = resolution('unicode',unicode_width=60,unicode_height=5)
    for ibin in (0, 17, ncols-1):
        values = np.zeros(ncols)
        values[ibin] = 1.0
        fig = Figure(panels=[Panel(items=[StepHist(np.linspace(-3.0,7.0,ncols+1),values)])])
        lines = UnicodeBackend(unicode_width=60,unicode_height=5).draw(fig)
        lines = lines.splitlines() if isinstance(lines,str) else lines
        filled = [ (i,j) for i,line in enumerate(lines[:nrows])
                   for j,ch in enumerate(line) if ch == '\u2588' ]
        cols = { j for _,j in filled }
        print(f'bin {ibin} of {ncols}: filled in {len(filled)} rows,'
              f' {len(cols)} column(s)')

def test_tool():
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
        mcpl.app_mcpltool(['mcpltool','--hist','time/ms;logx=1;bins=20;display_by=single',
                             '--backend','ascii',str(example_file)])
    lines = out.getvalue().splitlines()
    print(f'mcpltool --hist --backend ascii: {len(lines)} lines, first and last:')
    print(lines[0])
    print(lines[-1])
    #Without --bins, the histogram is made at the resolution of the terminal
    #(here 83 columns, so a plot with 72 columns, and 36 bins of 2 columns for
    #the 1006 particles in the file):
    env = { 'COLUMNS' : '83', 'LINES' : '24' }
    old = { k : os.environ.get(k) for k in env }
    os.environ.update(env)
    try:
        for args in ( ['--hist','x/cm;display_by=single'], ['--hist','x/cm : y/cm'] ):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
                mcpl.app_mcpltool(['mcpltool',*args,'--backend','ascii',
                                     str(example_file)])
            print(f'mcpltool {" ".join(args)} --backend ascii with 83 columns:')
            print(out.getvalue())
    finally:
        for k,v in old.items():
            if v is None:
                del os.environ[k]
            else:
                os.environ[k] = v

test_histograms()
test_stats()
test_files_and_options()
test_tool()
test_resolution()
