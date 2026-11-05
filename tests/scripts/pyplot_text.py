
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
from mcpldev import _plotting
from mcpldev._figures import Figure, Panel, StepHist, Text
from mcpldev._plotregistry import _forced_backend, _resolution
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.plots import (
    example_figures,
    hist_figure,
    internal_histogram,
    internal_histogram2d,
)

example_file = test_data_dir.joinpath('example.mcpl')

def show(figs, backend, width=72, height=8):
    #(terminal=True draws with unicode in these tests, and 'ascii' with ascii):
    print(f'==> {backend} backend, width {width}, height {height}:')
    _plotting.show(figs, terminal = True if backend == 'unicode' else 'ascii',
                       terminal_width=width, terminal_height=height)

def test_histograms():
    h = internal_histogram(mcpl, example_file, 'ekin/MeV', logx=True, bins=50, display_by='single')
    for backend in ('unicode','ascii'):
        show(hist_figure(mcpl,h), backend)
    #Several curves (markers and legend), and a logarithmic y axis:
    h = internal_histogram(mcpl, example_file, 'ekin/MeV;logy', logx=True, bins=50,
                       display_by='pdgcode')
    show(hist_figure(mcpl,h), 'unicode', height=10)
    h = internal_histogram(mcpl, example_file, 'acos(uz)/deg', range=(0,180), bins=36,
                       display_by='x > 0cm')
    show(hist_figure(mcpl,h), 'ascii')
    #2D histogram:
    h = internal_histogram2d(mcpl, example_file, 'x/cm', 'y/cm', bins=30,
                         edit='pdgcode == neutron')
    for backend in ('unicode','ascii'):
        show(hist_figure(mcpl,h), backend, height=12)

def test_overview():
    figs = example_figures(mcpl,example_file)
    show(figs[0], 'ascii')
    show(figs[1:3], 'unicode', height=6)
    show(Figure( title='Empty', panels=[ Panel( title='No data here',
                                               items=[ Text('No data') ] ) ] ), 'unicode')

def test_files_and_options():
    figs = example_figures(mcpl,example_file)[:2]
    #(.txt files are drawn with unicode, and here also with ascii):
    for backend in ('unicode','ascii'):
        with _forced_backend(backend):
            files = _plotting.save(figs, f'stats_{backend}.txt', terminal_width=60)
        data = pathlib.Path(files[0]).read_bytes()
        widths = { len(line) for line in data.decode('utf-8').splitlines() }
        print(f'{backend}: saved {files}, {len(data.splitlines())} lines, max width'
              f' {max(widths)}, ascii only: {data.isascii()}')
    h = mcpl.histogram(example_file, 'ekin/MeV;bins=10')
    #(plots of histograms have no other options):
    for args, kw in ( ( "'x.txt',terminal=True", { 'filename' : 'x.txt', 'terminal' : True } ),
                      ( "'x.txt',terminal_color='always'",
                        { 'filename' : 'x.txt', 'terminal_color' : 'always' } ),
                      ( 'terminal=True,logz=True', { 'terminal' : True, 'logz' : True } ) ):
        try:
            h.plot(**kw)
        except mcpl.MCPLError as e:
            print(f'plot({args}): MCPLError: {e}')
        except TypeError:
            print(f'plot({args}): TypeError')
    #In terminals which can not show its characters, plots in the terminal
    #are drawn with ascii characters:
    env = dict(os.environ, PYTHONIOENCODING='ascii',
               PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    for args in ( 'terminal=True,terminal_width=40,terminal_height=5', ):
        code = ( 'import mcpldev, mcpldev._plotting; from MCPLTestUtils.plots import hist_figure;'
                 f' h = mcpldev.histogram({str(example_file)!r},"ekin/MeV;bins=10;display_by=single");'
                 f' mcpldev._plotting.show(hist_figure(mcpldev,h),{args})' )
        rv = subprocess.run([sys.executable,'-c',code], capture_output=True,
                            env=env, check=False)
        print(f'show({args}) with PYTHONIOENCODING=ascii: exit code {rv.returncode},'
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
    print('resolution unicode (width 60):',_resolution(True,60))
    print('resolution ascii (width 50, height 6):',_resolution('ascii',50,6))
    with _forced_backend('test'):
        print('resolution test backend:',_resolution())
    #A histogram with one bin per column is drawn without any resampling: a
    #single filled bin fills exactly its column, in all rows:
    ncols, nrows = _resolution(True,60,5)
    for ibin in (0, 17, ncols-1):
        values = np.zeros(ncols)
        values[ibin] = 1.0
        fig = Figure(panels=[Panel(items=[StepHist(np.linspace(-3.0,7.0,ncols+1),values)])])
        lines = UnicodeBackend(width=60,height=5).draw(fig)
        lines = lines.splitlines() if isinstance(lines,str) else lines
        filled = [ (i,j) for i,line in enumerate(lines[:nrows])
                   for j,ch in enumerate(line) if ch == '\u2588' ]
        cols = { j for _,j in filled }
        print(f'bin {ibin} of {ncols}: filled in {len(filled)} rows,'
              f' {len(cols)} column(s)')

def test_tool():
    #(with the ascii backend, as in terminals which can not show Unicode):
    out = io.StringIO()
    with _forced_backend('ascii'), contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
        mcpl.app_mcpltool(['mcpltool','-t','time/ms;logx=1;bins=20;display_by=single',
                           str(example_file)])
    lines = out.getvalue().splitlines()
    print(f'mcpltool -t with ascii: {len(lines)} lines, first and last:')
    print(lines[0])
    print(lines[-1])
    #Without --bins, the histogram is made at the resolution of the terminal
    #(here 83 columns, so a plot with 72 columns, and 36 bins of 2 columns for
    #the 1006 particles in the file):
    env = { 'COLUMNS' : '83', 'LINES' : '24' }
    old = { k : os.environ.get(k) for k in env }
    os.environ.update(env)
    try:
        for args in ( ['-t','x/cm;display_by=single'], ['-t','x/cm : y/cm'] ):
            out = io.StringIO()
            with _forced_backend('ascii'), contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
                mcpl.app_mcpltool(['mcpltool',*args,str(example_file)])
            print(f'mcpltool {" ".join(args)} with ascii and 83 columns:')
            print(out.getvalue())
    finally:
        for k,v in old.items():
            if v is None:
                del os.environ[k]
            else:
                os.environ[k] = v

test_histograms()
test_overview()
test_files_and_options()
test_tool()
test_resolution()
