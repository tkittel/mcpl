
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

# Test exactly which modules of the mcpl package are imported by "import mcpl"
# and by each use of the Python API or of mcpltool (the scenarios of
# MCPLTestUtils.pyscenarios), so that parts like the expressions, statistics,
# histograms, plotting, and the mcpltool command are only imported when they are
# used, and packages like matplotlib not at all (unless plots are shown). Each
# scenario runs in a new Python process, which reports all modules it imported.
#
# The imports must also agree with the imports found in the code
# (MCPLTestUtils.pymoddeps): each module of the package is imported by a module
# whose code has that import, and all imports outside of functions of the
# imported modules are imported too.

import importlib.util
import pathlib
import sys

from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.pymoddeps import import_graph
from MCPLTestUtils.pyscenarios import prepare_files, run_scenario, scenarios

#Packages which must not be imported unless plots are shown:
plot_modules = { 'matplotlib', 'PIL', 'tkinter', 'curses', 'scipp', 'IPython',
                 'ipywidgets' }

#All modules of the mcpl package imported by "import mcpl" (the expected
#modules of the scenarios are those imported in addition to these):
core_modules = '_blocks _common _messages _numpy _reader'

_expr = '_expr_ast _expr_ast2astnorm _expr_ast2str _expr_astcheck _expr_eval _expr_ints _expr_str2ast _expr_vocab _expressions _exprrotation _exprunits _particles _physics constants'
_plot_tool = '_exprplot _figures _histfigures _histfill _histstring _plotbackend _plotbackend_text _plotregistry _termcolor'
_plot = f'{_plot_tool} _histogram _plotting'

expected = {
    #Core functionality, which must not import any other modules:
    'import' : '',
    'header' : '',
    'read' : '',
    'read_gz' : '',
    'read_statsum' : '_statsum',
    'wavelength' : '_particles _physics constants',
    'write' : '_records _writer',
    'copy' : '_records _writer',
    'merge' : '_fileops _statsum _records _writer',
    'text' : '_ascii',
    'repair' : '_fileops _statsum _records _writer',
    #Optional functionality, which must only import what it needs:
    'edit' : _expr,
    'stats' : '_particles _physics _stats _statsum constants',
    'stats_edit' : f'{_expr} _stats _statsum',
    'hist' : f'{_expr} _exprplot _histfill _histogram _histstring',
    'tool' : '_cli',
    'tool_edit' : f'_cli {_expr}',
    'tool_stats' : '_cli _clistats _particles _physics _stats _statsum constants',
    'tool_hist' : f'_cli _clistats {_expr} _exprplot _histfill _histstring',
    'tool_extract' : '_cli _extract _statsum _records _writer',
    'tool_extract_edit' : f'_cli _extract {_expr} _statsum _records _writer',
    'tool_merge' : '_cli _extract _fileops _statsum _records _writer',
    'tool_repair' : '_cli _fileops _statsum _records _writer',
    'tool_text' : '_ascii _cli',
    #Plots saved as text load only the text backend:
    'plot' : f'{_expr} {_plot}',
    'tool_plot' : f'_cli _clistats {_expr} {_plot_tool}',
}

def check_static( graph, got, imports ):
    """Checks that the imports agree with the static import graph"""
    for a, b in imports:
        assert b in graph.get(a,{}), f'{a} imported {b}, which is not an import in its code'
    assert { b for _, b in imports } == got - { '__init__' }
    for m in sorted(got):
        eager = { d for d, kind in graph[m].items() if kind == 0 }
        assert eager <= got, f'{m} imports {sorted(eager-got)}, which were not imported'

def main():
    assert sorted(expected) == sorted(key for key, _, _ in scenarios)
    pythonpath = [ p for p in sys.path if p ]
    graph = import_graph(pathlib.Path(importlib.util.find_spec('mcpldev').origin).parent)
    prepare_files(test_data_dir)
    core = set(core_modules.split())
    for key, title, code in scenarios:
        got, others, imports = run_scenario(code, 'mcpldev', pythonpath)
        #Plotting packages must not be imported at all, and exactly the
        #expected modules of the mcpl package:
        assert not ( others & plot_modules ), sorted(others & plot_modules)
        check_static( graph, got, imports )
        missing = sorted( core - got )
        extra = sorted( got - core - { '__init__' } )
        print(f'{title:<40}: {" ".join(extra) or "no other modules"}'
              + ( f' (but not {" ".join(missing)})' if missing else '' ))
        assert not missing and extra == sorted(expected[key].split()), (title, missing, extra)
    print('The imports agree with the imports in the code.')

if __name__ == '__main__':
    main()
