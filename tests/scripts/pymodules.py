
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

# Checks the structure of the modules in the mcpl package. Changing the
# structure requires updating the tables below, which makes it a deliberate
# decision:
#
# * The table "dependencies" gives for each module exactly the modules of the
#   package it imports (also inside functions, and by name, like the names of
#   the package which are only imported when used). This graph must have no
#   cycles, and no module may import the public entry points (__init__,
#   __main__ and the deprecated mcpl.mcpl).
# * Only _numpy imports numpy, and only the listed modules import the optional
#   dependencies.
# * Each module has an __all__. For private modules, it lists the public names
#   they provide, which must all be re-exported by the mcpl package. The
#   __all__ of the package contains exactly those names, plus the public
#   submodules.

import ast
import pathlib

from MCPLTestUtils.pymoddeps import package_imports

dependencies = {
    '_ascii'             : ( '_reader', ),
    '_blocks'            : ( '_common', '_numpy', '_physics' ),
    '_cli'               : ( '_ascii', '_clistats', '_common', '_examples', '_expressions', '_exprhelp', '_extract', '_fileops', '_histogram', '_histstring', '_messages', '_particles', '_plotregistry', '_reader', '_stdviews', '_viewer', '_viewer_ui' ),
    '_clistats'          : ( '_common', '_histogram', '_histstring', '_plotbackend', '_plotregistry', '_reader', '_stats', 'plotting' ),
    '_common'            : (  ),
    'constants'          : (  ),
    '_examples'          : ( '_common', '_messages', '_numpy', '_writer' ),
    '_exprcore'          : ( '_common', '_exprsyntax', '_exprunits', '_numpy', '_particles', '_physics', '_userdata' ),
    '_expressions'       : ( '_common', '_exprcore', '_exprrotation', '_exprsyntax', '_exprunits', '_numpy', '_particles', '_physics' ),
    '_exprhelp'          : ( '_helptext', '_particles' ),
    '_exprplot'          : ( '_common', '_exprcore', '_expressions', '_exprunits', '_numpy' ),
    '_exprrotation'      : ( '_numpy', ),
    '_exprsyntax'        : ( '_common', ),
    '_exprunits'         : (  ),
    '_extract'           : ( '_messages', '_reader', '_writer' ),
    '_figures'           : (  ),
    '_fileops'           : ( '_common', '_messages', '_reader', '_statsum', '_writer' ),
    '_helptext'          : (  ),
    '_histogram'         : ( '_common', '_exprcore', '_expressions', '_exprplot', '_exprunits', '_histstring', '_numpy', '_particles', '_reader', 'plotting' ),
    '_histstring'        : ( '_common', '_exprcore', '_expressions', '_exprplot', '_exprunits', '_numpy', '_particles' ),
    '_logo'              : (  ),
    '_messages'          : (  ),
    '_numpy'             : (  ),
    '_particles'         : (  ),
    '_physics'           : ( '_common', '_numpy', '_particles', 'constants' ),
    '_plotbackend'       : ( '_common', ),
    '_plotbackend_mpl'   : ( '_common', '_figures', '_logo', '_numpy', '_plotbackend' ),
    '_plotbackend_test'  : ( '_figures', '_numpy', '_plotbackend' ),
    '_plotbackend_text'  : ( '_figures', '_numpy', '_particles', '_physics', '_plotbackend', '_termcolor' ),
    '_plotregistry'      : ( '_common', '_messages', '_plotbackend', '_plotbackend_mpl', '_plotbackend_test', '_plotbackend_text' ),
    'plotting'           : ( '_figures', '_plotbackend', '_plotregistry' ),
    '_reader'            : ( '_blocks', '_common', '_expressions', '_messages', '_numpy', '_scipp', '_statsum', '_userdata' ),
    '_records'           : ( '_blocks', '_common', '_numpy', '_particles', '_physics' ),
    '_scipp'             : ( '_common', '_messages', '_numpy', '_userdata' ),
    '_stats'             : ( '_common', '_expressions', '_messages', '_numpy', '_physics', '_reader' ),
    '_statsum'           : ( '_common', ),
    '_stdviews'          : (  ),
    '_termcolor'         : ( '_common', ),
    '_thumbnails'        : ( '_figures', '_numpy' ),
    '_userdata'          : ( '_common', '_numpy' ),
    '_viewer'            : ( '_common', '_exprcore', '_expressions', '_exprhelp', '_exprsyntax', '_histstring', '_messages', '_plotregistry', '_reader', '_stdviews', '_userdata', '_viewer_curses', '_viewer_groups', '_viewer_output', '_viewer_overviews', '_viewer_reading', '_viewer_tk', '_viewer_ui' ),
    '_viewer_align'      : ( '_common', '_exprrotation', '_exprunits', '_numpy', '_particles' ),
    '_viewer_code'       : ( '_exprcore', '_expressions', '_exprrotation', '_exprsyntax', '_exprunits', '_extract' ),
    '_viewer_curses'     : ( '_common', '_plotbackend_text', '_plotregistry', '_termcolor', '_viewer_ui' ),
    '_viewer_figure'     : ( '_plotbackend_mpl', ),
    '_viewer_groups'     : ( '_exprcore', '_histstring', '_particles', '_stdviews', '_viewer_overviews' ),
    '_viewer_output'     : ( '_common', '_extract', '_messages', '_reader', '_stdviews', '_viewer_code', '_viewer_groups', '_viewer_ui' ),
    '_viewer_overviews'  : ( '_figures', '_histstring', '_numpy' ),
    '_viewer_reading'    : ( '_blocks', '_common', '_exprcore', '_histogram', '_histstring', '_numpy', '_reader', '_stdviews', '_viewer_overviews', '_viewer_ui', 'plotting' ),
    '_viewer_tk'         : ( '_common', '_logo', '_messages', '_viewer_figure', '_viewer_tkbase', '_viewer_tkcards', '_viewer_tkcontrols', '_viewer_tkwindows', '_viewer_ui', '_viewer_widgets' ),
    '_viewer_tkbase'     : ( '_viewer_ui', ),
    '_viewer_tkcards'    : ( '_stdviews', '_viewer_tkbase', '_viewer_ui' ),
    '_viewer_tkcontrols' : ( '_viewer_tkbase', '_viewer_ui' ),
    '_viewer_tkwindows'  : ( '_common', '_exprhelp', '_viewer_align', '_viewer_code', '_viewer_tkbase', '_viewer_ui' ),
    '_viewer_ui'         : ( '_common', '_helptext', '_stdviews' ),
    '_viewer_widgets'    : ( '_common', '_exprhelp', '_histstring', '_particles', '_stdviews', '_thumbnails', '_viewer_figure', '_viewer_ui', 'plotting' ),
    '_writer'            : ( '_blocks', '_common', '_expressions', '_messages', '_numpy', '_reader', '_records', '_statsum', '_userdata' ),
    '__init__'           : ( '_ascii', '_blocks', '_cli', '_common', '_expressions', '_fileops', '_histogram', '_messages', '_reader', '_stats', '_statsum', '_viewer', '_writer', 'constants', 'plotting' ),
    '__main__'           : ( '_cli', ),
    'mcpl'               : ( '_ascii', '_blocks', '_cli', '_common', '_reader', '_stats', '_statsum' ),
}

entry_points = ( '__init__', '__main__', 'mcpl' )

public_submodules = ['constants', 'plotting']

allowed_external_imports = {
    'numpy' : ['_numpy'],
    'matplotlib' : ['_plotbackend_mpl', '_thumbnails', '_viewer_figure', '_viewer_tk'],
    'tkinter' : ['_viewer_tk', '_viewer_tkbase'],
    'scipp' : ['_scipp'],
    'curses' : ['_viewer_curses'],
}

def find_cycle( graph ):
    """A cycle of the graph (as a list of names), or None"""
    state = {}
    def visit( n, path ):
        state[n] = 'active'
        for d in sorted(graph[n]):
            if state.get(d) == 'active':
                return path[path.index(d):] + [d]
            if d not in state:
                c = visit(d, path + [d])
                if c:
                    return c
        state[n] = 'done'
        return None
    for n in sorted(graph):
        if n not in state:
            c = visit(n, [n])
            if c:
                return c
    return None

#External modules which are slow to import, and which must therefore only be
#imported inside functions (i.e. on demand, when plots are made):
on_demand_external_imports = ['matplotlib', 'scipp', 'curses']

def import_time_externals( path ):
    """External top level modules imported when the file is imported (i.e.
    outside of functions)."""
    external = set()
    def visit( node ):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Import):
                external.update(a.name.split('.')[0] for a in child.names)
            elif isinstance(child, ast.ImportFrom) and child.level == 0:
                external.add(child.module.split('.')[0])
            visit(child)
    visit(ast.parse(path.read_text()))
    return external

def literal_all( path ):
    for node in ast.parse(path.read_text()).body:
        if ( isinstance(node, ast.Assign)
             and any(getattr(t,'id',None) == '__all__' for t in node.targets) ):
            return ast.literal_eval(node.value)
    return None

def main():
    import importlib

    import mcpldev
    pkgdir = pathlib.Path(mcpldev.__file__).parent
    files = { f.stem: f for f in pkgdir.glob('*.py') }
    assert set(files) == set(dependencies), ( 'Modules not in table: '
                                              f'{sorted(set(files)-set(dependencies))}, '
                                              'modules in table but missing: '
                                              f'{sorted(set(dependencies)-set(files))}' )

    print('Modules of the mcpl package and their imports from the package (in'
          ' parentheses: only inside functions, in brackets: by name):')
    external_users = {}
    imports = package_imports(pkgdir)
    for name in sorted(dependencies):
        internal, infunc, byname, external = imports[name]
        for e in external:
            external_users.setdefault(e,set()).add(name)
        actual, expected = internal | infunc | byname, set(dependencies[name])
        assert actual == expected, ( f'{name} imports modules not in the table:'
                                     f' {sorted(actual-expected)}, and does not'
                                     f' import modules in the table:'
                                     f' {sorted(expected-actual)}' )
        bad = actual & set(entry_points)
        assert not bad, f'{name} imports the entry points {sorted(bad)}'
        listed = ( sorted(internal) + [ f'({n})' for n in sorted(infunc) ]
                   + [ f'[{n}]' for n in sorted(byname) ] )
        print(f'  {name:<20} <- {", ".join(listed) or "-"}')
    cycle = find_cycle({ n : set(d) for n, d in dependencies.items() })
    assert cycle is None, f'Import cycle: {" -> ".join(cycle or [])}'
    print('The imports have no cycles.')

    for ext, allowed in allowed_external_imports.items():
        users = external_users.get(ext,set())
        assert users <= set(allowed), f'{ext} imported by {sorted(users-set(allowed))}'
        print(f'{ext} is imported by: {", ".join(sorted(users)) or "-"}')

    for name in sorted(dependencies):
        early = import_time_externals(files[name]) & set(on_demand_external_imports)
        assert not early, f'{name} imports {sorted(early)} outside of functions'
    print(f'{", ".join(on_demand_external_imports)} are only imported inside functions')

    public_names = {}
    for name in dependencies:
        a = literal_all(files[name])
        if name == '__main__':
            continue
        assert a is not None, f'{name} has no __all__'
        assert len(set(a)) == len(a), f'duplicate names in __all__ of {name}'
        if name.startswith('_') and name != '__init__':
            mod = importlib.import_module(f'mcpldev.{name}')
            for n in a:
                assert n not in public_names, f'{n} in __all__ of both {name} and {public_names[n]}'
                public_names[n] = name
                assert hasattr(mod, n), f'{name}.{n} in __all__ but missing'
                assert getattr(mcpldev, n, None) is getattr(mod, n), f'{name}.{n} not re-exported by mcpl'
    expected = set(public_names) | set(public_submodules)
    assert set(mcpldev.__all__) == expected, ( 'Names in mcpl.__all__ which no module provides: '
                                               f'{sorted(set(mcpldev.__all__)-expected)}, '
                                               'missing names: '
                                               f'{sorted(expected-set(mcpldev.__all__))}' )
    print(f'mcpl.__all__ has {len(mcpldev.__all__)} names, provided by:')
    for name in sorted(set(public_names.values())):
        print(f'  {name:<20} : {", ".join(sorted(n for n,m in public_names.items() if m == name))}')

if __name__ == '__main__':
    main()
