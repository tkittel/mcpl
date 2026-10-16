
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
    return 'Build the Sphinx-based website locally'

def main( parser ):
    parser.init( """Build the Sphinx-based website (from the sources in doc/)
    in doc/build/html, or rebuild and serve it whenever the sources change
    (with --serve). This needs the Python packages in
    devel/reqs/requirements_doc.txt and Doxygen.""" )
    parser.add_argument( '--strict', action='store_true',
                         help="""Turn warnings into errors (as when building
                         the website in CI).""" )
    parser.add_argument( '--clean', action='store_true',
                         help="""Remove previous build results first
                         (including generated content, like the output of
                         Doxygen).""" )
    parser.add_argument( '--linkcheck', action='store_true',
                         help="""Check external links instead of building
                         the website.""" )
    parser.add_argument( '--serve', action='store_true',
                         help="""Serve the website with sphinx-autobuild,
                         rebuilding it whenever the sources change.""" )
    parser.add_argument( '--host', default='127.0.0.1',
                         help="""Host for --serve (default: %(default)s,
                         use 0.0.0.0 to make it reachable from other
                         machines).""" )
    parser.add_argument( '--port', type=int, default=8000,
                         help='Port for --serve (default: %(default)s).' )
    args = parser.parse_args()
    if args.serve and args.linkcheck:
        parser.error('--serve and --linkcheck can not be combined')

    import shutil
    import subprocess
    import sys

    from .dirs import reporoot
    _check_doxygen()
    docdir = reporoot / 'doc'
    srcdir, blddir = docdir / 'source', docdir / 'build'
    if args.clean and blddir.exists():
        print(f'Removing {blddir}')
        shutil.rmtree(blddir)
    opts = [ '-W', '--keep-going' ] if args.strict else []
    if args.serve:
        exe = shutil.which('sphinx-autobuild')
        if not exe:
            raise SystemExit('Error: sphinx-autobuild not found (see'
                             ' devel/reqs/requirements_doc.txt)')
        #(the generated content in build/autogen must not trigger rebuilds):
        cmd = [ exe, '-b', 'dirhtml', str(srcdir), str(blddir/'html'),
                '--host', args.host,
                '--port', str(args.port), '--ignore', str(blddir) ] + opts
    else:
        #(dirhtml gives URLs like .../usage_cmdline/ as on the Jekyll website):
        builder = 'linkcheck' if args.linkcheck else 'dirhtml'
        outdir = blddir / ( 'linkcheck' if args.linkcheck else 'html' )
        cmd = [ sys.executable, '-m', 'sphinx', '-b', builder, str(srcdir),
                str(outdir) ] + opts
    print('Running:', ' '.join(cmd))
    rv = subprocess.run( cmd, check = False )
    if rv.returncode:
        raise SystemExit(rv.returncode)
    if not args.serve and not args.linkcheck:
        print(f'Website built in {blddir/"html"} (open index.html in a browser)')

def _check_doxygen():
    #Clear error if Doxygen is missing (which Sphinx would otherwise report as
    #a crash):
    import shutil
    if not shutil.which('doxygen'):
        from .cppapidoc import doxygen_missing_msg
        raise SystemExit('Error: '+doxygen_missing_msg)
