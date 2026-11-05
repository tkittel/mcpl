
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

import hashlib
import itertools
import os
import pathlib
import sys

import mcpldev as mcpl
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.stdout_redirect import RedirectStdout


def fix_print_str(s):
    if isinstance(s,bytes):
        s = s.replace(str(test_data_dir).encode(),b'<TESTDATADIR>')
        if b'<TESTDATADIR>' in s:
            s = s.replace(b'\\',b'/')
    else:
        s = s.replace(str(test_data_dir),'<TESTDATADIR>')
        if '<TESTDATADIR>' in s:
            s = s.replace('\\','/')
    return s

def run_mcpltool(*args, expect_failure):
    cmdargs =[str(e) for e in args]
    fullcmd = [ sys.executable, '-m', 'mcpldev', *cmdargs ]
    print( '\n\n\n\n\nRUNNING: mcpltool {}'.format(fix_print_str(' '.join(cmdargs))),
           flush=True )
    print( 'Expect failure: %s'%('yes' if expect_failure else 'no'),
           flush=True )

    import subprocess
    #(with the errors, from standard error, in the output):
    rv = subprocess.run( fullcmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         check=False,
                         env = { **os.environ, 'PYMCPLTOOL_FAKE_PYVERSION' : '1' } )
    print(fix_print_str(rv.stdout
                        .replace(b'\r\n',b'\n')
                        .replace((f'MCPL v{mcpl.__version__}').encode('ascii'),
                                 b'MCPL v<current>' )
                        .decode()))
    print("Ended in failure: %s"%('yes' if rv.returncode!=0 else 'no'))
    if (rv.returncode != 0) != expect_failure:
        raise SystemExit('Did not end in failure as expected!'
                         if expect_failure else
                         'Should not have ended in failure!')

def do_test(folder):

    files=[ 'miscphys.mcpl.gz',
            'gammas_uw.mcpl.gz',
            'reffile_3.mcpl',
            'reffile_10.mcpl',
            'reffile_13.mcpl',
            'reffile_14.mcpl',
            'difficult_unitvector.mcpl.gz',
            'reffile_crash.mcpl',
            'reffile_empty.mcpl.gz',
            'reffile_userflags_is_pos.mcpl.gz',
            'reffile_uw.mcpl.gz',
            'reffile_14.mcpl' ]
    def find_file( filename ):
        f = test_data_dir.joinpath(folder,filename)
        assert f.is_file()
        return f
    #files = ['$SBLD_DATA_DIR/MCPLTests/%s'%f for f in files]
    #files += ['$SBLD_DATA_DIR/MCPLTests/reffile_14.mcpl']

    filecombinations = list(
        itertools.chain(
            #all 2 input files combinations:
            itertools.combinations( files, 2 ),
            #Every 17th combination with 3 input files:
            itertools.islice( itertools.combinations( files, 3 ), 0, None, 17 ),
            #duplicated input (triggers WARNING + non-forced merge):
            iter([(files[0], files[0]),(files[1], files[1]),(files[2], files[2])]),
        )
    )

    for i,filelist in enumerate(filecombinations):
        keepuf = bool(i%3==0)
        #Decode info about input files:
        inputcounts = []
        expected_uf = False
        expected_pol = False
        expected_dp = False
        input_univpdg = []
        input_univw = []

        expect_failure = any( find_file(f1).samefile(find_file(f2))
                              for ( f1, f2 )
                              in itertools.combinations( filelist, 2 ) )
        for f in filelist:
            with mcpl.MCPLFile(find_file(f)) as m:
                inputcounts += [m.nparticles]
                if m.nparticles>0:
                    input_univpdg += [m.opt_universalpdgcode]
                    input_univw += [m.opt_universalweight]
                    if m.opt_polarisation:
                        expected_pol = True
                    if not m.opt_singleprec:
                        expected_dp = True
                    #userflags are kept when --keepuserflags is set or input files are compatible;
                    if m.opt_userflags and (keepuf or len(set(filelist))==1):
                        expected_uf = True
        expected_univpdg = input_univpdg[0] if len(set(input_univpdg))==1 else 0
        expected_univw = input_univw[0] if len(set(input_univw))==1 else 0.0

        if pathlib.Path('tmp.mcpl').is_file():
            pathlib.Path('tmp.mcpl').unlink()
        mcpltool_args = ['--forcemerge','tmp.mcpl']
        mcpltool_args += [find_file(f) for f in filelist]
        if keepuf:
            mcpltool_args.append('--keepuserflags')

        run_mcpltool(*mcpltool_args,expect_failure = expect_failure)
        if expect_failure:
            assert not pathlib.Path('tmp.mcpl').is_file()
            continue
        with mcpl.MCPLFile('tmp.mcpl') as res:
            #(the dumps are given as checksums, so the log stays small):
            with RedirectStdout('dump.txt'):
                res.dump_hdr()
                if sum(inputcounts)<30:
                    res.dump_particles(limit=0)
                else:
                    for skip in [0]+inputcounts[:-1]:
                        res.dump_particles(limit=10,skip=max(0,skip-5))
            #(with \n line endings, also on Windows):
            dump = pathlib.Path('dump.txt').read_bytes().replace(b'\r\n',b'\n')
            print('dump with checksum',hashlib.md5(dump).hexdigest())
            assert res.opt_userflags==expected_uf,"unexpected user flags setting"
            assert res.opt_polarisation==expected_pol,"unexpected polarisation setting"
            assert res.opt_singleprec==(not expected_dp),"unexpected singleprec setting"
            assert res.opt_universalpdgcode==expected_univpdg,"unexpected universalpdgcode setting"
            assert res.opt_universalweight==expected_univw,"unexpected universalweight setting"

def main():
    do_test('ref')

if __name__ == '__main__':
    main()

