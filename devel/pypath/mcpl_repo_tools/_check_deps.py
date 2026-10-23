
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


#Check that the dependencies in the devel/dependency_database.yml are actually
#applied correctly in the various pyproject.toml, devel/reqs, etc. files.

def check_deps_in_toml_files(db):
    from .depdb import load_part2deplist_from_pyproject_toml, split_pkg_extra
    from .dirs import reporoot
    version = reporoot.joinpath('VERSION').read_text().strip()

    def deplist_to_pyprojtoml_fmt( deplist ):
        res = []
        for e in deplist:
            if split_pkg_extra(e)[1] is not None:
                res.append( e )#(version fixed by the BASE dependencies)
            elif e in db['packages']:
                res.append( f'{e}=={version}' )
            elif db['dependencies'][e]['py_spec']:#(not for those without pip packages)
                res.append( db['dependencies'][e]['py_spec'] )
        return res
    for pkgname, info in sorted(db['packages'].items()):
        for frel in info['tomlfiles']:
            f = reporoot.joinpath(*frel.split('/'))
            current_part2deplist = load_part2deplist_from_pyproject_toml(f)
            tgt_part2deplist = { k : deplist_to_pyprojtoml_fmt(v)
                                 for k,v in info['deps'].items() }
            cp = set(current_part2deplist.keys())
            tp = set(tgt_part2deplist.keys())
            if cp - tp:
                raise SystemExit(f'Excess dependency groups in {frel}: {cp-tp}')
            if tp - cp:
                raise SystemExit(f'Missing dependency groups in {frel}: {tp-cp}')
            for part in cp:
                current_list = current_part2deplist[part]
                tgt_list = tgt_part2deplist[part]
                if ( set(current_list) != set(tgt_list) ):
                    n = 'dependencies' if part=='BASE' else part
                    print()
                    print(f'Problematic dependency list ("{part}") in {frel}')
                    print()
                    print(f'Should be:\n\n{n} = {sorted(tgt_list)}')
                    print(f'\n.. but is:\n\n{n} = {sorted(current_list)}')
                    raise SystemExit(1)

def check_env_files(db, *, fix = False):
    from .depdb import (
        produce_expected_conda_yml_files,
        produce_expected_requirements_txt_files,
        produce_expected_testdeps_cmake,
        testdeps_cmake_relpath,
    )
    from .dirs import reporoot
    expected = produce_expected_requirements_txt_files(db)
    expected.update( produce_expected_conda_yml_files(db) )
    reqsdir_rel = 'devel/reqs'
    reqsdir = reporoot.joinpath(*reqsdir_rel.split('/'))
    files = ( list( reqsdir.glob('requirements_*.txt'))
              + list( reqsdir.glob('conda_*.yml')) )
    actual = { f.name for f in files }
    tgt =    set( expected.keys() )
    def error( msg ):
        print()
        print(f"ERROR: Problems with files in {reqsdir_rel}: {msg} ")
        print()
        print( "You might be able to fix them with:"
               " mcpldevtool depdb --mode=fixreqfiles" )
        print()
        raise SystemExit(1)
    if actual-tgt:
        if not fix:
            error(f'Excess files in {reqsdir_rel}: {actual-tgt}')
        for fn in actual-tgt:
            print(f"Removing {reqsdir_rel}/{fn}")
            reqsdir.joinpath(fn).unlink()
    if tgt-actual:
        if not fix:
            error(f'Missing files in {reqsdir_rel}: {tgt-actual}')
        for fn in tgt-actual:
            print(f"Creating {reqsdir_rel}/{fn}")
            reqsdir.joinpath(fn).write_text(expected[fn])

    ok = True
    for f in sorted(files):
        if f.name not in expected:
            continue#(removed above)
        if f.read_text() != expected[f.name]:
            if not fix:
                print(f'Content of {reqsdir_rel}/{f.name} needs updating!')
                ok = False
            else:
                print(f"Updating contents of {reqsdir_rel}/{f.name}")
                reqsdir.joinpath(f.name).write_text(expected[f.name])

    #The file read by mctools_testutils.cmake:
    f = reporoot.joinpath(*testdeps_cmake_relpath.split('/'))
    content = produce_expected_testdeps_cmake(db)
    if not f.is_file() or f.read_text() != content:
        if not fix:
            print(f'Content of {testdeps_cmake_relpath} needs updating!')
            ok = False
        else:
            print(f"Updating contents of {testdeps_cmake_relpath}")
            f.write_text(content)

    if not ok:
        error('some files needs to be updated')

def main():
    from .depdb import load_depdb
    db = load_depdb()
    check_deps_in_toml_files( db )
    check_env_files( db )

if __name__=='__main__':
    main()
