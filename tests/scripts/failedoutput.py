
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

# Failed --merge, --forcemerge, and --extract operations of mcpltool must
# not leave output files behind. They fail here because the
# input file has a comment starting with "stat:" which is not "stat:sum:"
# (which is refused when writing files).

import gzip
import pathlib
import subprocess
import sys

from MCPLTestUtils import clib
from MCPLTestUtils.dirs import test_data_dir


def run( args ):
    code = ( 'import sys; import mcpldev._cli as c;'
             ' sys.argv[0] = "mcpltool"; c.main()' )
    rv = subprocess.run( [ sys.executable, '-c', code ] + [ str(a) for a in args ],
                         capture_output = True, check = False )
    return rv.returncode, ( rv.stdout + rv.stderr ).decode()

def main():
    src = test_data_dir / 'ref' / 'ref_statunsupported.mcpl.gz'
    for fn in ( 'a.mcpl', 'b.mcpl' ):
        pathlib.Path(fn).write_bytes( gzip.decompress( src.read_bytes() ) )
    for args in ( [ '--merge', 'out.mcpl', 'a.mcpl', 'b.mcpl' ],
                  [ '--merge', 'out', 'a.mcpl', 'b.mcpl' ],
                  [ '--merge', 'out.mcpl.gz', 'a.mcpl', 'b.mcpl' ],
                  [ '--forcemerge', 'out.mcpl', 'a.mcpl', 'b.mcpl' ],
                  [ '--extract', 'a.mcpl', 'out.mcpl' ],
                  [ '--extract', '-e', 'pdgcode == 2112', 'a.mcpl', 'out' ],
                  [ '--extract', 'a.mcpl', 'out.mcpl.gz' ] ):
        rc, output = run( args )
        assert rc != 0, (args, output)
        assert 'reserved for future usage' in output, (args, output)
        left = sorted( str(f) for f in pathlib.Path('.').glob('out*') )
        assert not left, (args, left)
        print(f'mcpltool: failed {" ".join(args)} leaves no output file')
    #The merges of the C library itself fail the same way, but leave the
    #output file unfinished (it is only removed by mcpltool):
    for out, force in ( ( 'out.mcpl', 0 ), ( 'out', 0 ), ( 'out.mcpl.gz', 0 ),
                        ( 'out.mcpl', 1 ) ):
        res = clib.lib().mcpltest_merge(out,'a.mcpl\nb.mcpl',force,0)
        assert 'reserved for future usage' in res, (out, force, res)
        left = sorted( pathlib.Path('.').glob('out*') )
        assert [ f.name for f in left ] == [ 'out.mcpl' ], (out, force, left)
        print(f'C library: failed {"forced " if force else ""}merge to {out}'
              f' leaves {", ".join(f.name for f in left) or "no output file"}')
        for f in left:
            f.unlink()
    #While successful operations of course do:
    ex = test_data_dir / 'ref' / 'reffile_1.mcpl'
    for args, out in ( ( [ '--merge', 'ok.mcpl', ex, 'b0.mcpl' ],
                         'ok.mcpl' ),
                       ( [ '--extract', '-e', 'pdgcode == 2112', ex, 'okx.mcpl.gz' ],
                         'okx.mcpl.gz' ) ):
        pathlib.Path('b0.mcpl').write_bytes( ex.read_bytes() )
        rc, output = run( args )
        assert rc == 0, (args, output)
        assert pathlib.Path(out).is_file()
        pathlib.Path(out).unlink()
        print(f'mcpltool: successful {args[0]} gives an output file')

if __name__ == '__main__':
    main()
