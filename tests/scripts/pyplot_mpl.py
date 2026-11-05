
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
# plotting backend, as PDF and PNG files (also with mcpltool -w).

import pathlib

import mcpldev as mcpl
from mcpldev import _plotting
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.plots import example_figures, items_figure

example_file = test_data_dir.joinpath('example.mcpl')

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
        _plotting.save(example_figures(mcpl,f)[:1], pdf)
        assert pathlib.Path(pdf).stat().st_size > 1000
        print(f'plots ok for {f.name}')

def test_png():
    figs = example_figures(mcpl,example_file)[:3]
    files = _plotting.save(figs, 'stats.png')
    for f in files:
        assert pathlib.Path(f).read_bytes()[:4] == b'\x89PNG'
    print(f'Created {files}')
    #mcpltool (saving files with matplotlib):
    rc = 0
    try:
        mcpl.app_mcpltool(['mcpltool','-H','x : y','-o','tool.png',
                           str(example_file)])
    except SystemExit as e:
        rc = e.code
    created = sorted(f.name for f in pathlib.Path('.').glob('tool*.png'))
    assert rc == 0 and created == ['tool.png'] and all(
        pathlib.Path(f).read_bytes()[:4] == b'\x89PNG' for f in created )
    print(f'mcpltool -w with -o tool.png created {created}')

def test_items():
    #All kinds of items (a 3D plot, an empty cell, same scales, coloured
    #bars and dashed curves), with the logo:
    files = _plotting.save(items_figure(mcpl), 'items.png')
    assert pathlib.Path(files[0]).read_bytes()[:4] == b'\x89PNG'
    print(f'Created {files} with all kinds of items')

test_plots()
test_png()
test_items()
