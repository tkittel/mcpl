
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


# NEEDS: numpy matplotlib

# Test that plots of all reference files can be saved with the matplotlib
# plotting backend, as PDF and PNG files (also with mcpltool -H).

import pathlib

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.plots import example_figures

example_file = test_data_dir.joinpath('example.mcpl')

def check_stats(fn, pick=None):
    #The histograms of the fields collected with the statistics:
    s = mcpl.collect_stats(fn, pick=pick)
    integral = s['file']['integral']
    print(f'{pathlib.Path(fn).name} (pick: {pick}): {s["file"]["nparticles"]} particles')
    for v in ('ekin','x','time'):
        h, _ = s[v]['hist'], s[v]['hist_bins']
        out = s[v]['hist_outside']
        print(f'   {v} hist sum {h.sum():g}, weight outside plot range: {out:g}')
        assert np.isclose(h.sum() + out, integral)
    return s

def test_plots():
    import matplotlib
    matplotlib.use('agg')
    files = sorted( f for f in test_data_dir.joinpath('ref').glob('*.mcpl*')
                    if not any(e in f.name for e in ('bad','crash','truncated',
                                                      'statunsupported')) )
    files.append(example_file)
    for i, f in enumerate(files):
        with mcpl.MCPLFile(f) as mf:
            if not mf.nparticles:
                continue
        pdf = f'plots_{i}.pdf'
        figs = [ mcpl.histogram(f,p).figure() for p in ( 'ekin;logy;display_by=pdgcode',
                                                         'x : y', 'pdgcode;bar' ) ]
        mcpl.plotting.save(figs, pdf, backend='matplotlib', matplotlib_backend='agg')
        assert pathlib.Path(pdf).stat().st_size > 1000
        print(f'plots ok for {f.name}')

def test_png():
    figs = example_figures(mcpl,example_file)[:3]
    files = mcpl.plotting.save(figs, 'stats.png', backend='matplotlib', matplotlib_backend='agg')
    for f in files:
        assert pathlib.Path(f).read_bytes()[:4] == b'\x89PNG'
    print(f'Created {files}')
    #mcpltool with the default backend (matplotlib, which then uses its agg
    #backend for saving files):
    rc = 0
    try:
        mcpl.app_mcpltool(['mcpltool','-H','ekin;logy','-H','x : y','-o','tool.png',
                           str(example_file)])
    except SystemExit as e:
        rc = e.code
    created = sorted(f.name for f in pathlib.Path('.').glob('tool*.png'))
    assert rc == 0 and created == ['tool_1.png','tool_2.png'] and all(
        pathlib.Path(f).read_bytes()[:4] == b'\x89PNG' for f in created )
    print(f'mcpltool with two -H and -o tool.png created {created}')

check_stats(example_file)
check_stats(example_file, 'pdgcode == neutron and ekin < 1MeV')
check_stats(example_file, 'pdgcode == gamma')
check_stats(test_data_dir.joinpath('ref','reffile_1.mcpl'))
test_plots()
test_png()
