
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


def short_description():
    from .depdb import dbfilerelpath
    return f'Extract information about dependencies from {dbfilerelpath}'

def load():
    from .depdb import load_depdb
    return load_depdb()

def gathertestdeps():
    from .dirs import testroot
    needs = set()
    for s in sorted(testroot.glob('**/scripts/*.py')):
        if '#' in s.name or '~' in s.name:
            continue
        with s.open('rt') as fh:
            for line in fh:
                if line.startswith('# NEEDS:'):
                    deps = line[len('# NEEDS:'):].split('#')[0]
                    needs.update(set(deps.split()))
    return needs

def fixreqfiles():
    from ._check_deps import check_env_files
    from .depdb import load_depdb
    db = load_depdb()
    check_env_files( db, fix = True )

def main( parser ):
    parser.init( short_description() )

    parser.add_argument(
        '-m','--mode', type = str, choices = ('fixreqfiles',
                                              'testdeps2json',
                                              'minversions',
                                              'freebsdpkgs',
                                              'freebsdpips',
                                              'json',
                                              'pprint'),
        default = 'pprint',
        help="""Mode (default: pprint). The "minversions" mode prints the
        minimum versions of the dependencies of all packages which can be
        installed in the current environment, in the requirements.txt format
        (like "numpy==1.22.*"), "freebsdpkgs" the FreeBSD packages of the
        all_and_devel requirements (for the Python flavour given with
        --pyflavour), and "freebsdpips" the requirements which are instead
        installed with pip on FreeBSD (those without FreeBSD packages)."""
    )
    parser.add_argument(
        '--pyflavour', type = str, default = 'py312',
        help="""Python flavour of FreeBSD packages (default: py312)."""
    )

    args = parser.parse_args()

    if args.mode == 'fixreqfiles':
        fixreqfiles()
        return

    if args.mode=='testdeps2json':
        import json
        print( json.dumps(sorted(gathertestdeps())) )
        return

    if args.mode=='minversions':
        from .depdb import minversion_reqs
        for r in minversion_reqs( load() ):
            print(r)
        return

    if args.mode in ('freebsdpkgs','freebsdpips'):
        import re
        if not re.fullmatch('py3[0-9]+',args.pyflavour):
            parser.error(f'Invalid Python flavour: {args.pyflavour}')
        from .depdb import freebsd_pkgnames
        print(' '.join( freebsd_pkgnames( load(), 'all_and_devel',
                                          args.pyflavour,
                                          pip = args.mode == 'freebsdpips' ) ))
        return

    if args.mode=='pprint':
        import pprint
        pprint.pprint( load() )
        return

    if args.mode=='json':
        import json
        print( json.dumps( load() ) )
        return

    parser.error('No mode selected')
