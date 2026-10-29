
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
"""

   The imports between the modules of a package, found in their code (used by
   the pymodules test and by "mcpldevtool graph").

"""

import ast


def imports_of( path ):
    """Returns (modules of the package imported outside of functions, those
    only imported inside functions, external top level modules) imported
    anywhere in the file."""
    internal, infunc, external = set(), set(), set()
    def visit( node, in_function ):
        for child in ast.iter_child_nodes(node):
            f = in_function or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                  ast.Lambda))
            if isinstance(child, ast.Import):
                for a in child.names:
                    assert not a.name.startswith('mcpl'), f'{path.name}: absolute import of {a.name}'
                    external.add(a.name.split('.')[0])
            elif isinstance(child, ast.ImportFrom):
                if child.level == 0:
                    assert not child.module.startswith('mcpl'), f'{path.name}: absolute import of {child.module}'
                    external.add(child.module.split('.')[0])
                else:
                    assert child.level == 1, f'{path.name}: import from parent package'
                    names = ( [child.module] if child.module
                              else [ a.name for a in child.names ] )
                    ( infunc if f else internal ).update(names)
            visit(child, f)
    visit(ast.parse(path.read_text()), False)
    return internal, infunc - internal, external

#Modules imported by name (with importlib), from the tables of these variables
#(the values are names of modules, optionally followed by ":" and a name):
imports_by_name = { '__init__' : ( '_on_demand', ),
                    '_viewer' : ( '_frontends', ),
                    '_plotregistry' : ( '_registry', '_hidden' ) }

def imported_by_name( path, variables ):
    """Names of the modules in the dictionaries assigned to the variables"""
    res = set()
    for node in ast.parse(path.read_text()).body:
        if ( isinstance(node, ast.Assign) and len(node.targets) == 1
             and getattr(node.targets[0], 'id', None) in variables ):
            res.update( v.split(':')[0] for v in ast.literal_eval(node.value).values() )
    return res

def package_imports( pkgdir ):
    """For each module (.py file) of the package in the directory, returns
    (modules of the package imported outside of functions, those only imported
    inside functions, those only imported by name, external top level
    modules)."""
    res = {}
    for f in sorted(pkgdir.glob('*.py')):
        internal, infunc, external = imports_of(f)
        byname = imported_by_name(f, imports_by_name.get(f.stem, ())) - internal - infunc
        res[f.stem] = ( internal, infunc, byname, external )
    return res

def import_graph( pkgdir ):
    """The imports of package_imports as {module: {imported module: kind}},
    with kind 0 for imports outside of functions, 1 for those only inside
    functions, and 2 for those only by name"""
    return { name : { d : kind for kind, mods in enumerate(imps[:3]) for d in mods }
             for name, imps in package_imports(pkgdir).items() }
