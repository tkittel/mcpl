
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

from .dirs import reporoot

toml_files =  { 'core': 'mcpl_core/pyproject.toml',
                'coreempty': 'mcpl_core/empty_pypkg/pyproject.toml',
                'py': 'mcpl_python/pyproject.toml',
                'meta': 'mcpl_metapkg/pyproject.toml',
                'extra': 'mcpl_extra/pyproject.toml',
               }

_data_cache = {}
def load_data( key ):
    if key not in _data_cache:
        _data_cache[key] = _actual_load_data( toml_files[key] )
    return _data_cache[key]

def _actual_load_data(subpath):
    from .toml import parse_toml

    #if not can_parse_toml():
    #    #Acceptable simplification to simply abort, since already we mostly have
    #    #python >=3.11 in dev envs, and CI certainly will catch it with python
    #    #>=3.11 somewhere.
    #    print("Silent abort: tomli not present and python < 3.11")
    #    raise SystemExit(0)

    d = parse_toml(reporoot / subpath)
    #sneak in the source location:
    assert '__file__' not in d
    d['__srcloc__'] = subpath
    print(f"  Loaded: {describe(d)}")
    return d

def describe( data ):
    return '<root>/{}'.format(data['__srcloc__'])

def cmp_common_entries( keypath, dict1, dict2, allow_diff = () ):
    d1, d2 = dict1, dict2
    for k in keypath.split('.'):
        d1, d2 = d1[k], d2[k]

    keys = set(d1.keys()).intersection(set(d2.keys())) - set(allow_diff)
    ok = True
    for k in keys:
        if d1[k] != d2[k]:
            print()
            print(f'Inconsistency found in key "{keypath}.{k}:"')
            print()
            print(f'   {describe(dict1)} has value: {d1[k]!r}')
            print()
            print(f'   {describe(dict2)} has value: {d2[k]!r}')
            print()
            ok = False
    if not ok:
        raise SystemExit(1)

def check_metadata():
    #Check that there is consistency between the three pyproject.toml files,
    #except where expected.

    #data_monolith = load_data( 'monolith' )
    data_core = load_data( 'core' )
    data_coreempty = load_data( 'coreempty' )
    data_py = load_data( 'py' )
    data_meta = load_data( 'meta' )
    data_extra = load_data( 'extra' )

    #Check that there are no unexpected sections:
    toplvlkeys_notool = {'build-system','project','__srcloc__'}
    toplvlkeys = toplvlkeys_notool.union( {'tool'} )
    #assert toplvlkeys == set( data_monolith.keys() )
    assert toplvlkeys == set( data_core.keys() )
    assert toplvlkeys == set( data_extra.keys() )
    assert toplvlkeys_notool == set( data_coreempty.keys() )
    assert toplvlkeys == set( data_py.keys() )
    assert toplvlkeys_notool == set( data_meta.keys() )

    #Check 'project' section
    version = data_core['project']['version']
    assert data_coreempty['project']['version']==version
    assert data_extra['project']['version']==version
    #assert data_monolith['project']['version']==version
    assert data_meta['project']['version']==version
    #projkeys_monolith = set( data_monolith['project'].keys() )
    projkeys_core = set( data_core['project'].keys() )
    projkeys_coreempty = set( data_coreempty['project'].keys() )
    projkeys_py = set( data_py['project'].keys() )
    projkeys_meta = set( data_meta['project'].keys() )
    projkeys_extra = set( data_extra['project'].keys() )
    #assert 'dependencies' in projkeys_monolith
    assert 'dependencies' not in projkeys_core
    assert 'dependencies' not in projkeys_coreempty
    assert 'dependencies' in projkeys_py
    assert 'dependencies' in projkeys_meta
    assert 'dependencies' in projkeys_extra

    #(the dependencies themselves are checked against
    #devel/dependency_database.yml in _check_deps.py)
    #assert ( projkeys_monolith - projkeys_core ) == set(['dependencies'])
    #assert ( projkeys_core - projkeys_monolith ) == set([])
    assert ( projkeys_core - projkeys_meta ) == {'scripts'}
    assert ( projkeys_meta - projkeys_core ) == {'dependencies',
                                                 'optional-dependencies'}
    assert ( projkeys_extra - projkeys_meta ) == {'scripts'}
    assert ( projkeys_meta - projkeys_extra ) == {'optional-dependencies'}

    #The metapackage must forward all extras of mcpl-python (and has the
    #devel extra in addition):
    extras_py = data_py['project'].get('optional-dependencies',{})
    extras_meta = data_meta['project']['optional-dependencies']
    assert set(extras_py) | {'devel'} == set(extras_meta)
    for k in extras_py:
        assert extras_meta[k] == [f'mcpl-python[{k}]'], (k,extras_meta[k])
    #assert ( projkeys_py - projkeys_monolith ) == set(['dynamic'])
    #assert ( projkeys_monolith - projkeys_py ) == set(['version'])
    assert ( projkeys_core - projkeys_meta ) == {'scripts'}
    assert ( projkeys_coreempty - projkeys_core ) == set()
    assert ( projkeys_core - projkeys_coreempty ) == {'scripts'}

    cmp_common_entries( 'project', data_coreempty, data_core )
    cmp_common_entries( 'build-system', data_coreempty, data_py )

    cmp_common_entries( 'build-system', data_core, data_extra,
                        allow_diff=['requires'])

    assert ( data_coreempty['build-system'] == data_py['build-system'] )

    cmp_common_entries( 'project', data_coreempty, data_core,
                        allow_diff = [] )

    cmp_common_entries( 'project', data_meta, data_core,
                        allow_diff = ['name'] )
    cmp_common_entries( 'project', data_extra, data_core,
                        allow_diff = ['name','description','scripts'] )
    #cmp_common_entries( 'project', data_monolith, data_core,
    #                    allow_diff = ['name','scripts','description'] )
    #cmp_common_entries( 'project', data_monolith, data_py,
    #                    allow_diff = ['name','scripts','description'] )
    #NB: projects.scripts checked elsewhere in more detail!

    #Check 'build-system' section
    #cmp_common_entries( 'build-system', data_monolith, data_core,
    #                    allow_diff = [] )
    cmp_common_entries( 'build-system', data_py, data_meta,
                        allow_diff = [] )

    #Check 'tool' section
    assert set( data_core['tool'].keys() ) == {'scikit-build',
                                               'cibuildwheel'}
    #assert set( data_monolith['tool'].keys() ) == set(['scikit-build'])
    #cmp_common_entries( 'tool.scikit-build', data_monolith, data_core,
    #                    allow_diff = ['sdist','wheel'] )
    #cmp_common_entries( 'tool.scikit-build.sdist', data_monolith, data_core,
    #                    allow_diff = ['include'] )
    #cmp_common_entries( 'tool.scikit-build.wheel', data_monolith, data_core,
    #                    allow_diff = ['packages'] )


def check_all_project_scripts():
    #data_monolith = load_data( 'monolith' )
    data_core = load_data( 'core' )
    data_py = load_data( 'py' )
    data_meta = load_data( 'meta' )
    data_extra = load_data( 'extra' )

    #extra_mono = [
    #    ('mcpl-config',
    #     "_mcpl_core_monolithic.info:_mcpl_config_cli_wrapper"),
    #]
    extra_core = [
        ('mcpl-config','_mcpl_core.info:_mcpl_config_cli_wrapper'),
    ]
    extra_py = [
        ('mcpltool','mcpl._cli:main'),
        ('pymcpltool','mcpl._cli:_main_pymcpltool'),
    ]
    extra_extra = [
        ('mcpl2ssw','_mcpl_extra.cli:cli_wrapper_mcpl2ssw'),
        ('ssw2mcpl','_mcpl_extra.cli:cli_wrapper_ssw2mcpl'),
        ('mcpl2phits','_mcpl_extra.cli:cli_wrapper_mcpl2phits'),
        ('phits2mcpl','_mcpl_extra.cli:cli_wrapper_phits2mcpl'),
    ]

    ok = True
    if not _check_project_scripts_impl( data_py,
                                        extra=extra_py ):
        ok = False
    #if not _check_project_scripts_impl( data_monolith,
    #                                    cli_scripts = True,
    #                                    extra = extra_mono ):
    #    ok = False
    if not _check_project_scripts_impl( data_core,
                                        extra = extra_core ):
        ok = False
    if not _check_project_scripts_impl( data_meta,
                                        extra = [] ):
        ok = False
    if not _check_project_scripts_impl( data_extra,
                                        extra = extra_extra ):
        ok = False
    if not ok:
        raise SystemExit('Failures detected in project.scripts')


def _check_project_scripts_impl( data, *, extra ):
    #We already check project.scripts consistency between the three
    #pyproject.toml files in check_metadata().
    from_toml = data['project'].get('scripts',{})
    expected = dict( e for e in extra )
    if expected == from_toml:
        return True#all ok
    descr = describe( data )
    for k,v in expected.items():
        fmt = f'{k} = "{v}"'
        v_toml = from_toml.get(k)
        if v != v_toml:
            print(f"ERROR: Missing line in {descr}:\n\n   {fmt}\n")
            if v_toml is not None:
                print(f'Got instead:\n\n   {k} = "{v_toml}"\n')
    for k,v in from_toml.items():
        if k not in expected:
            print(f'ERROR: Unexpected line in {descr}:\n\n   {k}="{v}"\n')
    return False

def check_all_toml_parsing():
    from .dirs import reporoot
    from .srciter import all_files_iter
    from .toml import parse_toml
    for f in all_files_iter('toml'):
        print(f"  Trying to simply load {f.relative_to(reporoot)}")
        parse_toml(f)
    print('  -> all parsed ok')

def check_buildsys():
    version = reporoot.joinpath('VERSION').read_text().strip()
    for k in sorted(toml_files.keys()):
        d = load_data(k)
        fname = describe(d)
        b = d['build-system']
        backend = b['build-backend']
        if backend == 'scikit_build_core.build':
            if not d.get('tool',{}).get('scikit-build'):
                raise SystemExit(f'Missing tool.scikit-build section: {fname}')
            requires = {"scikit-build-core>=0.11.0"}
            if k == 'extra':
                requires.add(f'mcpl-core=={version}')
        elif backend == 'setuptools.build_meta':
            requires = {"setuptools>=77.0.1"}
        else:
            raise SystemExit(f'Unexpected backend in {fname}')
        r = set(b.get('requires',[]))
        if r != requires:
            raise SystemExit(f'Bad build-system.requires in {fname}: '
                             f'Expected {requires}, got {r}')


def main():
    check_all_toml_parsing()
    check_all_project_scripts()
    check_metadata()
    check_buildsys()
    print("All OK!")

if __name__=='__main__':
    main()
