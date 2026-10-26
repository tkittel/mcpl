
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
# * Each module only imports modules of the package in lower layers (no import
#   cycles), also inside functions. The modules at the top layer are the public
#   entry points and only import private modules.
# * Only _numpy imports numpy, and only the listed modules import the optional
#   dependencies.
# * Each module has an __all__. For private modules, it lists the public names
#   they provide, which must all be re-exported by the mcpl package. The
#   __all__ of the package contains exactly those names, plus the public
#   submodules.

import ast
import pathlib

top = 99
layers = {
    'constants' : 0,
    '_numpy' : 0,
    '_common' : 0,
    '_messages' : 0,
    '_particles' : 0,
    '_stdviews' : 0,
    '_helptext' : 0,
    '_viewer_ui' : 1,
    '_logo' : 0,
    '_exprhelp' : 1,
    '_physics' : 1,
    '_statsum' : 1,
    '_userdata' : 1,
    '_scipp' : 1,
    '_termcolor' : 1,
    '_blocks' : 2,
    '_exprsyntax' : 1,
    '_exprcore' : 2,
    '_expressions' : 3,
    '_exprrotation' : 1,
    '_exprplot' : 4,
    '_records' : 4,
    '_histstring' : 5,
    '_reader' : 4,
    '_writer' : 5,
    '_fileops' : 6,
    '_examples' : 6,
    '_extract' : 6,
    '_viewer_code' : 7,
    '_plotbackend' : 7,
    'plotting' : 8,
    '_plotbackend_mpl' : 9,
    '_plotbackend_test' : 9,
    '_plotbackend_text' : 9,
    '_stats' : 7,
    '_histogram' : 9,
    '_plotbackend_mpl_gui' : 14,
    '_plotbackend_text_gui' : 10,
    '_viewer_jupyter' : 10,
    '_viewer_widgets' : 10,
    '_viewer_tkbase' : 11,
    '_viewer_tkcards' : 12,
    '_viewer_tkcontrols' : 12,
    '_viewer_tkwindows' : 12,
    '_viewer_tk' : 13,
    '_viewer_reading' : 10,
    '_viewer_overviews' : 9,
    '_viewer_groups' : 10,
    '_thumbnails' : 9,
    '_viewer' : 11,
    '_clistats' : 11,
    '_cli' : 12,
    '__init__' : top,
    '__main__' : top,
    'mcpl' : top,
}

public_submodules = ['constants', 'plotting']

allowed_external_imports = {
    'numpy' : ['_numpy'],
    'matplotlib' : ['_plotbackend_mpl', '_plotbackend_mpl_gui', '_thumbnails', '_viewer_tk'],
    'tkinter' : ['_viewer_tk', '_viewer_tkbase'],
    'scipp' : ['_scipp'],
    'ipywidgets' : ['_viewer_jupyter'],
    'IPython' : ['_viewer', '_viewer_jupyter'],
    'curses' : ['_plotbackend_text_gui'],
}

def imports_of( path ):
    """Returns (modules of the package, external top level modules) imported
    anywhere in the file."""
    internal, external = set(), set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.startswith('mcpl'), f'{path.name}: absolute import of {a.name}'
                external.add(a.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert not node.module.startswith('mcpl'), f'{path.name}: absolute import of {node.module}'
                external.add(node.module.split('.')[0])
                continue
            assert node.level == 1, f'{path.name}: import from parent package'
            if node.module:
                internal.add(node.module)
            else:
                internal.update(a.name for a in node.names)
    return internal, external

#External modules which are slow to import, and which must therefore only be
#imported inside functions (i.e. on demand, when plots are made):
on_demand_external_imports = ['matplotlib', 'scipp', 'ipywidgets', 'IPython', 'curses']

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
    assert set(files) == set(layers), ( 'Modules not in table: '
                                        f'{sorted(set(files)-set(layers))}, '
                                        'modules in table but missing: '
                                        f'{sorted(set(layers)-set(files))}' )

    def layername(n):
        return 'top' if layers[n] == top else str(layers[n])
    print('Modules of the mcpl package and their imports from the package:')
    external_users = {}
    for name in sorted(layers, key=lambda n: (layers[n], n)):
        internal, external = imports_of(files[name])
        for e in external:
            external_users.setdefault(e,set()).add(name)
        for i in internal:
            assert i in layers, f'{name} imports unknown module {i}'
            if layers[name] == top:
                assert layers[i] != top, f'{name} imports {i} at the same top layer'
            else:
                assert layers[i] < layers[name], ( f'{name} (layer {layers[name]})'
                                                   f' imports {i} (layer {layers[i]})' )
        print(f'  layer {layername(name):>3} : {name:<20} <- {", ".join(sorted(internal)) or "-"}')

    for ext, allowed in allowed_external_imports.items():
        users = external_users.get(ext,set())
        assert users <= set(allowed), f'{ext} imported by {sorted(users-set(allowed))}'
        print(f'{ext} is imported by: {", ".join(sorted(users)) or "-"}')

    for name in sorted(layers):
        early = import_time_externals(files[name]) & set(on_demand_external_imports)
        assert not early, f'{name} imports {sorted(early)} outside of functions'
    print(f'{", ".join(on_demand_external_imports)} are only imported inside functions')

    public_names = {}
    for name in layers:
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
    for name in sorted(set(public_names.values()), key=lambda n: (layers[n], n)):
        print(f'  {name:<20} : {", ".join(sorted(n for n,m in public_names.items() if m == name))}')

if __name__ == '__main__':
    main()
