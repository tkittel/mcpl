
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


#Loading of devel/dependency_database.yml, and creation of the files which are
#derived from it (ported from NCrystal, with the addition of extras of other
#packages like "mcpl-python[plot]" and of dependencies which can not be
#installed everywhere).

dbfilerelpath = 'devel/dependency_database.yml'
testdeps_cmake_relpath = 'tests/cmake/mctools_testdeps.cmake'

def load_depdb():
    import yaml

    from .dirs import reporoot
    with reporoot.joinpath(dbfilerelpath).open() as fh:
        data = yaml.safe_load(fh)
    errmsg, data = _prepare_data_and_check_errors( data )
    if errmsg:
        raise SystemExit(f'ERROR invalid data in {dbfilerelpath} : {errmsg}')
    return data

def load_part2deplist_from_pyproject_toml( tomlfile ):
    from .toml import parse_toml
    t = parse_toml(tomlfile)
    part2deplist = {}
    part2deplist['BASE'] = t['project'].get('dependencies',[])
    for part,deplist in t['project'].get('optional-dependencies',{}).items():
        part2deplist[ part ] = deplist
    return part2deplist

def _handle_ADD( pkgname, part2deplist ):
    def has_add( deplist ):
        return any( d.startswith('ADD') for d in deplist )
    ready = { k : v for k,v in part2deplist.items() if not has_add(v) }
    pending = { k : v for k,v in part2deplist.items() if has_add(v) }
    i = 0
    while pending:
        i+=1
        if i==1000:
            return f'recursive ADD statements involving {pending.keys()}'
        for partname,deplist in pending.items():
            for i in range(len(deplist)):
                if deplist[i].startswith('ADD'):
                    needed_part = deplist[i][len('ADD'):].strip()
                    if needed_part == partname:
                        raise SystemExit('ERROR: Self referencing ADD '
                                         f'statement involving {partname}')
                    if needed_part in ready:
                        deplist[i] = ''#to be removed later
                        deplist += ready[needed_part]
            if not has_add(deplist):
                #transfer copy to 'ready'
                ready[partname] = deplist[:]
                del deplist[:]#clear in place
        for partname in list(pending.keys()):
            if partname in ready:
                assert len(pending[partname]) == 0
                del pending[partname]
    assert set(part2deplist.keys()) == set(ready.keys())
    for k,v in ready.items():
        part2deplist[k] = v

_cmdcache=[{}]
def _handle_CMD( pkgname, part2deplist ):
    import json
    import subprocess
    import sys

    from .dirs import reporoot
    for part,deplist in sorted(part2deplist.items()):
        for i in range(len(deplist)):
            if not deplist[i].startswith('CMD'):
                continue
            cmd = []
            for e in deplist[i][len('CMD'):].split():
                if e=='<python>':
                    e = sys.executable
                elif e.startswith('<reporoot>/'):
                    e = str(reporoot.joinpath(*(e.split('/')[1:])))
                cmd.append(e)
            cmd = tuple(str(e) for e in cmd)
            if cmd not in _cmdcache[0]:
                rv = subprocess.run(cmd,capture_output=True,check=False)
                if rv.stderr or rv.returncode != 0:
                    import shlex
                    raise SystemExit(f'CMD failed: {shlex.join(cmd)}')
                _cmdcache[0][cmd] = json.loads(rv.stdout.decode())
            deplist[i]=''#clear previous
            deplist += _cmdcache[0][cmd]

def split_pkg_extra( dep ):
    """'mcpl-python[plot]' -> ('mcpl-python','plot'), others -> (dep,None)"""
    if dep.endswith(']') and '[' in dep:
        p, e = dep[:-1].split('[',1)
        return p, e
    return dep, None

def append_version_var( s, val, operator, sep='' ):
    if not val:
        return s
    return s + sep + ( val if operator in val else f'{operator}={val}' )

def markers( info ):
    """Environment markers of a dependency (list of strings)"""
    res = []
    pystd = info.get('in_pystdlib_from')
    if pystd:
        res.append( f'python_version < "{pystd}"' )
    minpy = info.get('min_python')
    if minpy:
        res.append( f'python_version >= "{minpy}"' )
    for system in info.get('unavailable_on',[]):
        res.append( f'platform_system != "{system}"' )
    only = info.get('only_on',[])
    if only:
        m = ' or '.join( f'platform_system == "{system}"' for system in only )
        res.append( f'( {m} )' if len(only) > 1 else m )
    return res

def create_py_spec(info):
    pn = info['pypi_pkgname']
    if pn is None:
        return None#(only available from conda-forge)
    min_v = info.get('min_version')
    max_v = info.get('max_version')
    assert not (min_v and max_v)
    s = append_version_var( pn, min_v, '>' )
    s = append_version_var( s, max_v, '<' )
    m = markers(info)
    if m:
        s += '; ' + ' and '.join(m)
    return s

def create_conda_spec(info):
    #(no markers: conda-forge packages exist on all platforms which conda
    #supports, and a conda environment can have a recent Python)
    pn = info['conda_pkgname']
    min_v = info.get('min_version')
    max_v = info.get('max_version')
    assert not (min_v and max_v)
    s = append_version_var( pn, min_v, '>', ' ' )
    s = append_version_var( s, max_v, '<', ' ' )
    return s

def install_needed( info, pyversion = None, system = None ):
    """Whether a dependency should be installed with the given Python version
    (a tuple, default: the current one) on the given system (as in
    platform.system(), default: the current one): false if it can not be
    installed there, or if it is part of the standard library."""
    import platform
    import sys
    pyversion = tuple(pyversion or sys.version_info[0:2])
    system = system or platform.system()
    def vtuple( s ):
        return tuple( int(e) for e in s.split('.') )
    minpy = info.get('min_python')
    if minpy and pyversion < vtuple(minpy):
        return False
    pystd = info.get('in_pystdlib_from')
    if pystd and pyversion >= vtuple(pystd):
        return False#(not needed)
    if info.get('only_on') and system not in info['only_on']:
        return False
    return system not in info.get('unavailable_on',[])

def _prepare_data_and_check_errors( rawdata ):
    from .dirs import reporoot

    assert set(rawdata.keys())<={'packages','dependencies','conda_env_tools','environments'}
    assert 'conda_env_tools' in rawdata
    rawdata.setdefault('environments',{})
    #First pkg_deps:

    pkgdata = rawdata['packages']
    for pkgname,info in sorted(pkgdata.items()):
        if not info.get('deps'):
            info['deps'] = {}
        if not info['deps'].get('BASE'):
            info['deps']['BASE'] = []
        assert set(info.keys())=={'tomlfiles','deps'}
        assert len(info['tomlfiles'])>=1
        part2deplist = info['deps']
        errmsg = ( _handle_CMD(pkgname,part2deplist)
                   or _handle_ADD(pkgname,part2deplist) )
        if errmsg:
            return errmsg, None
        for tf in info['tomlfiles']:
            if not reporoot.joinpath(*tf.split('/')).is_file():
                raise SystemExit(f'File not found: {tf}')

    def check_name_ok(p):
        if not ( isinstance(p,str)
                 and p
                 and p.replace('-','_').isidentifier() ):
            raise SystemExit(f'Invalid name : {p}')

    all_deps_used = set()

    for pkgname,info in pkgdata.items():
        part2deplist = info['deps']
        check_name_ok(pkgname)
        for part in list(part2deplist.keys()):
            check_name_ok(part)
            assert part.isidentifier()
            part2deplist[part] = sorted({e for e in part2deplist[part] if e})
            for dep in part2deplist[part]:
                p, extra = split_pkg_extra(dep)
                if extra is not None:
                    if p not in pkgdata or extra not in pkgdata[p].get('deps',{}):
                        raise SystemExit(f'{pkgname}.{part} uses "{dep}" which'
                                         ' is not an extra of a package')
                    continue
                all_deps_used.add(dep)
                check_name_ok(dep)
                if ( dep not in rawdata['dependencies']
                     and dep not in pkgdata ):
                    raise SystemExit(f'{pkgname}.{part} uses dependency'
                                     f' "{dep}" which is not defined in'
                                     ' dependencies: section and which is not'
                                     ' itself a package name.')

    for envname, deplist in rawdata['environments'].items():
        check_name_ok(envname)
        if envname in pkgdata['mcpl-metapkg']['deps']:
            raise SystemExit(f'environment "{envname}" has the name of an'
                             ' extra of the mcpl package')
        for dep in deplist:
            p, extra = split_pkg_extra(dep)
            if p in pkgdata:
                if extra is not None and extra not in pkgdata[p]['deps']:
                    raise SystemExit(f'environment {envname} uses "{dep}"'
                                     ' which is not an extra of a package')
                continue
            if dep not in rawdata['dependencies']:
                raise SystemExit(f'environment {envname} uses dependency'
                                 f' "{dep}" which is not defined in'
                                 ' dependencies: section')
            all_deps_used.add(dep)

    #Then dependencies:
    known_keys = { 'min_version', 'max_version', 'import_check', 'cmd_check',
                   'pypi_pkgname', 'conda_pkgname', 'in_pystdlib_from',
                   'min_python', 'unavailable_on', 'only_on',
                   'freebsd_pkgname', 'freebsd_pip', 'check_code' }
    for depname,info in rawdata['dependencies'].items():
        check_name_ok(depname)
        if depname not in all_deps_used:
            raise SystemExit('dependencies: section lists '
                             f'unused dependency "{depname}"')
        if set(info) - known_keys:
            raise SystemExit(f'dependencies: unknown fields for "{depname}":'
                             f' {sorted(set(info)-known_keys)}')
        for k in ['import_check','pypi_pkgname','conda_pkgname']:
            if k not in info:
                info[k] = depname
        #(conda_pkgname null: not available on conda-forge, so it is left out
        #of the conda environment files; pypi_pkgname null: no pip package, like
        #parts of Python which not all installations have, so it is left out
        #of pyproject.toml and requirements files)
        if 'min_version' in info and 'max_version' in info:
            raise SystemExit('dependencies: both min and max versions '
                             f'specified for "{depname}" (this is currently'
                             ' not supported by our infrastructure)')
        for k in ('unavailable_on','only_on'):
            if not isinstance(info.get(k,[]),list):
                raise SystemExit(f'dependencies: {k} of "{depname}" must be a list')

    #add derived info:
    for depname,info in rawdata['dependencies'].items():
        info['py_spec'] = create_py_spec(info)
        info['conda_spec'] = create_conda_spec(info) if info['conda_pkgname'] else None

    return '',rawdata

def expand_deps( db, deplist ):
    """The external dependencies of a list of dependencies, with mcpl packages
    and their extras replaced by their external dependencies."""
    out = set()
    for dep in deplist:
        p, extra = split_pkg_extra(dep)
        if extra is not None:
            out.update( expand_deps( db, db['packages'][p]['deps'][extra] ) )
        elif dep in db['packages']:
            out.update( expand_deps( db, db['packages'][dep]['deps']['BASE'] ) )
        else:
            out.add(dep)
    return out

def _produce_expected_deplists_for_env_files(db):
    out = {}
    db_metapkgdeps = db['packages']['mcpl-metapkg']['deps']
    def add(name,deplist):
        #(always with the dependencies of the mcpl packages, like numpy)
        assert name not in out
        out[name] = expand_deps(db,deplist+db_metapkgdeps['BASE'])
    for part,deplist in sorted(db_metapkgdeps.items()):
        if part!='BASE':
            add( part, deplist )

    add( 'all_and_devel',
         db_metapkgdeps['all'] + db_metapkgdeps['devel'] )
    for envname, deplist in sorted(db['environments'].items()):
        add( envname, deplist )
    return out

def produce_expected_requirements_txt_files(db):
    def content( deplist ):
        lines = [ db['dependencies'][dep]['py_spec'] for dep in set(deplist)
                  if db['dependencies'][dep]['py_spec'] is not None ]
        return '\n'.join(sorted(lines)+[''])
    name2deplist = _produce_expected_deplists_for_env_files(db)
    return { f'requirements_{n}.txt' : content(d)
             for n,d in name2deplist.items() }

_conda_yml_init = """name: mcpl_<<NAME>>
channels:
  - nodefaults
  - conda-forge
dependencies:
"""

def produce_expected_conda_yml_files(db):
    #For conda we always add whatever is needed for a development environment,
    #since people might wish to build from source, or whatnot (the
    #conda_env_tools of the database, as conda specifications):
    tools = sorted(db['conda_env_tools'])
    def content( name, deplist ):
        lines = tools[:]
        #(without the tools, which are already there):
        names = { t.split()[0] for t in tools }
        for dep in sorted(set( deplist ) - names ):
            if db['dependencies'][dep]['conda_spec']:
                lines.append(db['dependencies'][dep]['conda_spec'])
        res = _conda_yml_init.replace('<<NAME>>',name)
        for line in lines:
            res += f'  - {line}\n'
        return res

    name2deplist = _produce_expected_deplists_for_env_files(db)
    return { f'conda_{n}.yml' : content(n,d)
             for n,d in name2deplist.items() }

def produce_expected_testdeps_cmake(db):
    """Content of the file with the conditions of dependencies of the Python
    tests, read by mctools_testutils.cmake."""
    import pathlib
    #(same license blurb as in this file):
    blurb = pathlib.Path(__file__).read_text().splitlines()[0:21]
    lines = blurb + [
        '# Generated from devel/dependency_database.yml with "mcpldevtool depdb',
        '# --mode fixreqfiles" (do not edit). Information about the',
        '# dependencies of the Python tests (see mctools_testutils.cmake).',
        '' ]
    #(the devel extra of the mcpl package has all dependencies of the tests)
    testdeps = expand_deps( db, db['packages']['mcpl-metapkg']['deps']['devel'] )
    for depname, info in sorted(db['dependencies'].items()):
        if depname not in testdeps:
            continue
        if info.get('in_pystdlib_from'):
            pass#(mctools_testutils.cmake knows how to check for these)
        elif info.get('check_code'):
            lines.append( f'set( MCTOOLS_TESTDEP_{depname}_PYCODE'
                          f' "{info["check_code"]}" )' )
        elif info.get('import_check'):
            lines.append( f'set( MCTOOLS_TESTDEP_{depname}_IMPORT'
                          f' "{info["import_check"]}" )' )
        elif info.get('cmd_check'):
            lines.append( f'set( MCTOOLS_TESTDEP_{depname}_CMD'
                          f' "{info["cmd_check"]}" )' )
        minpy = info.get('min_python')
        systems = info.get('unavailable_on',[])
        if info.get('only_on'):
            systems = sorted( set(systems) | ( { 'Linux', 'Darwin', 'FreeBSD',
                                                 'Windows' } - set(info['only_on']) ) )
        if minpy:
            lines.append( f'set( MCTOOLS_TESTDEP_{depname}_MINPYTHON "{minpy}" )' )
        if systems:
            lines.append( f'set( MCTOOLS_TESTDEP_{depname}_UNAVAILABLE_ON'
                          f' "{";".join(systems)}" )' )
    return '\n'.join(lines) + '\n'

def minversion_reqs( db ):
    """Requirements with the minimum versions (like "numpy==1.22.*") of the
    dependencies of all packages (including their extras, but not the
    development dependencies), skipping those which are not needed or can not
    be installed in the current environment."""
    deps = set()
    for info in db['packages'].values():
        for part, deplist in info['deps'].items():
            if part != 'devel':
                deps.update( expand_deps( db, deplist ) )
    res = []
    for dep in sorted(deps):
        info = db['dependencies'][dep]
        if not install_needed(info) or info['pypi_pkgname'] is None:
            continue
        assert info.get('min_version'), f'no min_version for {dep}'
        res.append( f'{info["pypi_pkgname"]}=={info["min_version"]}.*' )
    return res

def freebsd_pkgnames( db, group, pyflavour, pip = False ):
    """Names of the FreeBSD packages needed for the given group of the
    metapackage (like "all_and_devel"), skipping dependencies which are not
    available there or not needed with the Python version of pyflavour (like
    "py312"). With pip set, the requirements (like "ipympl>=0.9") of those
    installed with pip instead (the dependencies with freebsd_pip)."""
    deplist = _produce_expected_deplists_for_env_files(db)[group]
    pyversion = ( int(pyflavour[2]), int(pyflavour[3:]) )
    res = []
    for dep in sorted(deplist):
        info = db['dependencies'][dep]
        if not install_needed(info, pyversion = pyversion, system = 'FreeBSD'):
            continue
        if bool(info.get('freebsd_pip')) != pip:
            continue
        if pip:
            res.append( info['py_spec'] )
            continue
        if not info.get('freebsd_pkgname'):
            raise SystemExit(f'No freebsd_pkgname for "{dep}" in {dbfilerelpath}')
        res.append( info['freebsd_pkgname'].replace('{py}',pyflavour) )
    return res
