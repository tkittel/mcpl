
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

# Test the --dry-run (-d) option of mcpltool and the dry_run argument of the
# file operations in the Python API: a dry run must print what the real run
# prints (except that it says "Would ..." and ends with a note), give the same
# exit code, and leave all files untouched (contents and modification times).
# Commands which do not write files must ignore --dry-run.

import pathlib
import shutil
import subprocess
import sys

import mcpldev as mcpl
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.loadlib import getlib

input_dir = pathlib.Path('inputs').absolute()

def make_inputs():
    input_dir.mkdir()
    lib = getlib('pywriter')
    def w(name, *lines):
        lib.mcpltest_script(str(input_dir/name), '\n'.join(lines))
    def parts(n, pdgs=(2112,22,11)):
        res = []
        for i in range(n):
            ux = 0.6 if i%2 else -0.8
            uz = (1.0-ux*ux)**0.5
            res.append(f'particle {1.5*i} {-2.0*i} {0.1*i} {ux} 0 {uz} 0 0 0'
                       f' {0.001*(i+1)} {0.01*i} {1.0+0.5*i} {pdgs[i%len(pdgs)]} {i}')
        return res
    hdr = ('srcname MySim', 'comment a comment', 'blob key1 some data')
    w('a1', *hdr, 'statsum nsim 1000', *parts(30), 'close')
    w('a2', *hdr, 'statsum nsim 2000', *parts(20), 'close')
    w('a3', *hdr, 'statsum nsim -1', *parts(5), 'closegz')
    w('b_dp', 'srcname Other', 'dp', 'userflags', *parts(12), 'close')
    w('b_pol', 'srcname Other', 'pol', *parts(7), 'close')
    shutil.copy(test_data_dir.joinpath('ref','reffile_crash.mcpl'), input_dir/'crash.mcpl')
    data = (input_dir/'a1.mcpl').read_bytes()
    (input_dir/'trunc.mcpl').write_bytes(data[:-20])

def dir_contents(d):
    return { f.name : f.read_bytes() for f in sorted(pathlib.Path(d).iterdir()) }

def dir_mtimes(d):
    return { f.name : f.stat().st_mtime_ns for f in sorted(pathlib.Path(d).iterdir()) }

def run(args, cwd):
    r = subprocess.run([sys.executable, '-m', 'mcpldev', *args], cwd=cwd,
                       capture_output=True, check=False)
    return r.returncode, r.stdout.decode().replace('\r\n','\n'), r.stderr.decode()

def fresh(d):
    if pathlib.Path(d).exists():
        shutil.rmtree(d)
    shutil.copytree(input_dir, d)

note = 'MCPL: dry run, nothing was written\n'

def compare(*args, writes = True):
    """Run the command for real and as a dry run, in fresh copies of the input
    directory, and check that the dry run is consistent with the real run.
    Commands which do not write files (writes=False) must ignore --dry-run."""
    fresh('real')
    fresh('dry')
    real = run(args, 'real')
    mtimes = dir_mtimes('dry')
    dry = run(['--dry-run', *args], 'dry')
    problems = []
    if real[0] != dry[0]:
        problems.append(f'exit codes differ: real {real[0]}, dry {dry[0]}')
    if dry[2]:
        problems.append(f'dry run stderr: {dry[2]!r}')
    #Expected dry-run printout: the real one with "Would ..." wording, without
    #the messages about gzipping, and with the note at the end if the command
    #did not fail:
    expected = ''.join( line for line in real[1].splitlines(keepends=True)
                        if not line.startswith(('MCPL: Compressing file ',
                                                'MCPL: Compressed file into ')) )
    expected = ( expected.replace('Successfully extracted','Would extract')
                 .replace('Successfully repaired','Would repair')
                 .replace('Transferred a total of','Would transfer a total of') )
    if real[0] == 0 and writes:
        expected += note
    if dry[1] != expected:
        problems.append(f'printouts differ:\n   real: {real[1]!r}\n    dry: {dry[1]!r}')
    #The dry run must leave the directory untouched, while the real run
    #normally changes it:
    changed_dry = dir_contents('dry') != dir_contents(input_dir)
    if changed_dry:
        problems.append('dry run changed files!')
    #(modification times must be unchanged as well, but we can not rely on
    #this check on Windows):
    if dir_mtimes('dry') != mtimes and not sys.platform.startswith('win'):
        problems.append('dry run changed modification times!')
    changed_real = dir_contents('real') != dir_contents(input_dir)
    print(f'mcpltool --dry-run {" ".join(args)}: exit code {dry[0]},'
          f' real run {"changed" if changed_real else "did not change"} files')
    for line in dry[1].splitlines():
        print(f'   | {line}')
    for problem in problems:
        print(f'   PROBLEM: {problem}')
    return not problems

def test_tool():
    print('=== mcpltool --dry-run')
    cases = [
        ['--extract','a1.mcpl','out.mcpl'],
        ['--extract','a1.mcpl','out.mcpl.gz'],
        ['--extract','-l5','-s3','a1.mcpl','out.mcpl'],
        ['--extract','-p','pdgcode == 2112 and ekin > 5keV','a3.mcpl.gz','out.mcpl'],
        ['--extract','--edit','weight *= 2','a1.mcpl','out.mcpl'],
        ['--extract','--edit','weight *= 2','--keep-statsum','a1.mcpl','out.mcpl'],
        ['--extract','--pick','ekin < 1 meV +','a1.mcpl','out.mcpl'],
        ['--extract','a1.mcpl','a2.mcpl'],
        ['--extract','nosuch.mcpl','out.mcpl'],
        ['--merge','out.mcpl','a1.mcpl','a2.mcpl','a3.mcpl.gz'],
        ['--merge','out.mcpl.gz','a1.mcpl','a2.mcpl'],
        ['--merge','out.mcpl','a1.mcpl','b_dp.mcpl'],
        ['--merge','a2.mcpl','a1.mcpl','a3.mcpl.gz'],
        ['--merge','--inplace','a1.mcpl','a2.mcpl','a3.mcpl.gz'],
        ['--merge','--inplace','a3.mcpl.gz','a1.mcpl'],
        ['--forcemerge','out.mcpl','a1.mcpl','b_dp.mcpl','b_pol.mcpl'],
        ['--forcemerge','--keepuserflags','out.mcpl.gz','b_dp.mcpl','b_pol.mcpl'],
        ['--forcemerge','out.mcpl','a1.mcpl','a2.mcpl'],
        ['--repair','trunc.mcpl'],
        ['--repair','crash.mcpl'],
        ['--repair','a1.mcpl'],
        ['--repair','a3.mcpl.gz'],
        ['--text','a1.mcpl','out.txt'],
        ['--text','a1.mcpl','a2.mcpl'],
    ]
    ok = True
    for args in cases:
        ok &= compare(*args)
    #Commands which do not write files ignore --dry-run:
    for args in ( ['a1.mcpl'], ['-j','a1.mcpl'], ['-n','-l3','-s2','a1.mcpl'],
                  ['--stats','a1.mcpl'], ['--hist','ekin/MeV;print=1;display_by=single','a1.mcpl'],
                  ['--version'], ['--bkey1','a1.mcpl'] ):
        ok &= compare(*args, writes = False)
    #The short form, and misuse:
    for args in ( ['-d','--extract','-l2','a1.mcpl','out.mcpl'],
                  ['-jd','a1.mcpl'],
                  ['-d','--stats','-o','s.pdf','a1.mcpl'],
                  ['--dry-run','--hist','ekin/MeV','--output','h.txt','a1.mcpl'] ):
        fresh('dry')
        rc, out, err = run(args, 'dry')
        print(f'mcpltool {" ".join(args)}: exit code {rc}')
        for line in out.splitlines():
            print(f'   | {line}')
        if err or dir_contents('dry') != dir_contents(input_dir):
            print(f'   PROBLEM: stderr {err!r} or changed files')
            ok = False
    return ok

def test_api():
    print('=== Python API dry_run')
    fresh('api')
    d = pathlib.Path('api')
    before = dir_contents(d)
    #(paths as strings with forward slashes, since they are echoed in messages
    #and the output must be the same on Windows):
    def fn(name):
        return (d/name).as_posix()
    inputs = [ fn('a1.mcpl'), fn('a2.mcpl') ]
    print('merge_files:', mcpl.merge_files(fn('out.mcpl'), inputs, dry_run=True))
    print('forcemerge_files:', mcpl.forcemerge_files(fn('out.mcpl'),
                                                     [*inputs, fn('b_dp.mcpl')],
                                                     dry_run=True))
    print('merge_inplace:', mcpl.merge_inplace(d/'a1.mcpl', d/'a2.mcpl', dry_run=True))
    print('repair:', mcpl.repair(d/'trunc.mcpl', dry_run=True))
    for fct, args in [ (mcpl.merge_files, (fn('out.mcpl'), [*inputs, fn('b_dp.mcpl')])),
                       (mcpl.merge_inplace, (d/'a3.mcpl.gz', d/'a1.mcpl')),
                       (mcpl.repair, (d/'a1.mcpl',)) ]:
        try:
            fct(*args, dry_run=True)
        except mcpl.MCPLError as e:
            print(f'{fct.__name__}: MCPLError: {e}')
    print('files unchanged:', dir_contents(d) == before)

def main():
    make_inputs()
    ok = test_tool()
    test_api()
    if not ok:
        raise SystemExit('Problems found')

if __name__ == '__main__':
    main()
