
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
    return 'Test the C and C++ code generated for edit expressions'

def main( parser ):
    parser.init( """Build and install MCPL with CMake, generate C and C++ code
    for many edit expressions (as mcpl._expr_ast2c and mcpl._expr_ast2cpp do),
    build it with CMake against MCPL, run it on reference files, and check that
    it gives the same particles (or errors) as mcpltool --extract. Requires
    numpy, and C and C++ compilers.""" )
    parser.add_argument( '-j',type=int,default=0,
                         help="""Use this many processes (default: auto detect).""" )
    parser.add_argument( '-n','--nrandom',type=int,default=200,
                         help="""Number of random edits to test (default: 200).""" )
    parser.add_argument( '-d','--dir', metavar='DIR',
                         help="""Work in DIR (which must not exist), and keep it,
                         instead of in a temporary directory.""" )
    args = parser.parse_args()
    from .codegen import run
    from .util import get_nprocs
    nprocs = args.j or get_nprocs()
    if args.dir:
        import os
        import pathlib
        d = pathlib.Path(args.dir)
        d.mkdir(parents=True)
        os.chdir(d)
        run(nprocs,args.nrandom)
    else:
        from .util import work_in_tmpdir
        with work_in_tmpdir():
            run(nprocs,args.nrandom)
