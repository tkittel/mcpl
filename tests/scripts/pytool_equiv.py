
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

# Tests of the operations of mcpltool on files (merging, extracting,
# repairing, and dumping), including errors, and of its --edit, and
# --keep-statsum options.

import gzip
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.loadlib import getlib
from MCPLTestUtils.mcplpatch import set_values

input_dir = pathlib.Path('inputs').absolute()

def make_inputs():
    input_dir.mkdir()
    lib = getlib('pywriter')
    def w(name, *lines):
        lib.mcpltest_script(str(input_dir/name), '\n'.join(lines))
    def parts(n, pdgs=(2112,22,11), dp=False):
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
    w('c_nostat', 'srcname MySim', *parts(9), 'close')
    shutil.copy(test_data_dir.joinpath('ref','reffile_crash.mcpl'), input_dir/'crash.mcpl')
    shutil.copy(test_data_dir.joinpath('ref','reffile_1.mcpl'), input_dir/'ref1.mcpl')
    #Files with NaN or infinite values (see pyc_equiv.py):
    set_values(input_dir/'a1.mcpl', input_dir/'nan.mcpl', 12, {'x':float('nan')})
    set_values(input_dir/'a1.mcpl', input_dir/'inf.mcpl', 3, {'uve3':float('inf'),
                                                             't':float('-inf')})

def dir_contents(d):
    res = {}
    for f in sorted(pathlib.Path(d).iterdir()):
        data = f.read_bytes()
        if f.name.endswith('.gz') and data[:2] == b'\x1f\x8b':
            data = gzip.decompress(data)
        res[f.name] = data
    return res

def run(cmd, cwd):
    #(with the errors, from standard error, in the output):
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       check=False, env = { **os.environ, 'PYMCPLTOOL_FAKE_PYVERSION' : '1' })
    return r.returncode, r.stdout.decode().replace('\r\n','\n'), ''

def fresh(d):
    if pathlib.Path(d).exists():
        shutil.rmtree(d)
    shutil.copytree(input_dir, d)

def tool(*args):
    """Run mcpltool on copies of the inputs, and show its output, and the
    checksums of the files it creates or changes (uncompressed)"""
    fresh('py')
    rc, out, err = run([sys.executable, '-m', 'mcpldev', *args], 'py')
    print(f'mcpltool {" ".join(args)}: exit code {rc}')
    for line in out.splitlines():
        print(f'   | {line}')
    if err:
        print(f'   PROBLEM: mcpltool stderr: {err!r}')
    before = dir_contents(input_dir)
    for name, data in dir_contents('py').items():
        if before.get(name) != data:
            #(with \n line endings in text files, also on Windows, like those
            #of --text, so all are converted):
            data = data.replace(b'\r\n',b'\n')
            print(f'   file {name}: md5 {hashlib.md5(data).hexdigest()}')
    return not err

def test_mcpltool():
    ok = True
    cases = [
        ['--merge','out.mcpl','a1.mcpl','a2.mcpl'],
        ['-m','out.mcpl.gz','a1.mcpl','a2.mcpl','a3.mcpl.gz'],
        ['--merge','out','a1.mcpl'],
        ['--merge','--inplace','a1.mcpl','a2.mcpl','a3.mcpl.gz'],
        ['-m','--inplace','a3.mcpl.gz','a1.mcpl'],
        ['--merge','out.mcpl','a1.mcpl','b_dp.mcpl'],
        ['--merge','out.mcpl','a1.mcpl'],
        ['--merge','a2.mcpl','a1.mcpl','a1.mcpl'],
        ['--merge','out.gz','a1.mcpl','a2.mcpl'],
        ['--merge','out.mcpl','a1.mcpl','a1.mcpl'],
        ['--forcemerge','out.mcpl','a1.mcpl','b_dp.mcpl','b_pol.mcpl'],
        ['--forcemerge','--keepuserflags','out.mcpl.gz','b_dp.mcpl','b_pol.mcpl'],
        ['--forcemerge','out.mcpl','a1.mcpl','a2.mcpl'],
        ['--forcemerge','out.mcpl'],
        ['--extract','a1.mcpl','out.mcpl'],
        ['-x','a1.mcpl','out.mcpl.gz'],
        ['--extract','-l5','a1.mcpl','out.mcpl'],
        ['--extract','-s25','a1.mcpl','out'],
        ['--extract','-l3','-s4','a3.mcpl.gz','out.mcpl'],
        ['--extract','-l100','-s0','a1.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == 22','a1.mcpl','out.mcpl'],
        ['-x','-e','pdgcode == -11','b_dp.mcpl','out.mcpl'],
        ['-x','-e','pdgcode == 11','-l10','-s3','a1.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == 2112','c_nostat.mcpl','out.mcpl'],
        ['--extract','-s5','c_nostat.mcpl','out.mcpl'],
        ['--extract','crash.mcpl','out.mcpl'],
        ['--extract','ref1.mcpl','out.mcpl'],
        ['--extract','a1.mcpl','a2.mcpl'],
        ['--extract','a1.mcpl','out.gz'],
        ['--extract','a1.mcpl'],
        ['--extract','a1.mcpl','x.mcpl','y.mcpl'],
        ['--extract','--no-comment','-e','pdgcode == 22','-l5','a1.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == 11','-l3','-s4','a1.mcpl','out.mcpl'],
        ['--no-comment','a1.mcpl'],
        ['--extract','-e','pdgcode == gamma','a1.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == photon','-l10','a1.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == antielectron','b_dp.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == neutron','c_nostat.mcpl','out.mcpl'],
        ['--inplace','a1.mcpl','a2.mcpl'],
        ['--keepuserflags','a1.mcpl'],
        ['--merge','--forcemerge','out.mcpl','a1.mcpl','a2.mcpl'],
        ['--merge','--extract','a1.mcpl','out.mcpl'],
        ['-j','--extract','a1.mcpl','out.mcpl'],
        ['--repair','crash.mcpl'],
        ['--repair','a1.mcpl'],
        ['--repair','a3.mcpl.gz'],
        ['-r','a1.mcpl','a2.mcpl'],
        ['-l3','a1.mcpl'],
        ['-j','b_dp.mcpl'],
        ['--justhead','a1.mcpl'],
        ['--nohead','-l2','a1.mcpl'],
        ['-bnosuchkey','a1.mcpl'],
        ['nan.mcpl'],
        ['nosuchfile.mcpl'],
        ['..'],
        ['-x','..','out.mcpl'],
        ['-l3','..'],
        ['-n','-l0','nan.mcpl'],
        ['-s10','-l5','nan.mcpl'],
        ['-s13','nan.mcpl'],
        ['-n','-l0','inf.mcpl'],
        ['-j','nan.mcpl'],
        ['--extract','nan.mcpl','out.mcpl'],
        ['--extract','-l12','nan.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == 22','nan.mcpl','out.mcpl'],
        ['--extract','-e','pdgcode == 2112','inf.mcpl','out.mcpl'],
        ['--merge','out.mcpl','a1.mcpl','nan.mcpl','inf.mcpl'],
        ['--merge','--inplace','a2.mcpl','nan.mcpl'],
        ['--forcemerge','out.mcpl','b_dp.mcpl','nan.mcpl'],
        ['--repair','nan.mcpl'],
        #Existing output files and --allow-overwrite:
        ['--merge','b_dp.mcpl','a1.mcpl','a2.mcpl'],
        ['--merge','--allow-overwrite','b_dp.mcpl','a1.mcpl','a2.mcpl'],
        ['-m','a3.mcpl.gz','a1.mcpl'],
        ['-m','--allow-overwrite','a3.mcpl.gz','a1.mcpl'],
        ['-m','b_pol.mcpl.gz','a1.mcpl'],
        ['-m','--allow-overwrite','b_pol.mcpl.gz','a1.mcpl'],
        ['-m','--allow-overwrite','a2.mcpl','a1.mcpl','a2.mcpl'],
        ['--forcemerge','b_dp.mcpl','a1.mcpl','b_pol.mcpl'],
        ['--forcemerge','--allow-overwrite','b_dp.mcpl','a1.mcpl','b_pol.mcpl'],
        ['--extract','--allow-overwrite','-l3','a1.mcpl','a2.mcpl'],
        ['--extract','--allow-overwrite','a1.mcpl','a1.mcpl'],
        ['--text','a1.mcpl','a2.mcpl'],
        ['--text','--allow-overwrite','a1.mcpl','a2.mcpl'],
        ['--text','--allow-overwrite','a1.mcpl','a1.mcpl'],
        ['--allow','--merge','b_dp.mcpl','a1.mcpl'],
        ['--allow-overwrite','a1.mcpl'],
        ['--merge','--inplace','--allow-overwrite','a1.mcpl','a2.mcpl'],
    ]
    for args in cases:
        ok &= tool(*args)
    return ok

def py_extract(infile, outfile, edit = None):
    """Do the same as mcpltool --extract --edit with the API"""
    edt = mcpl.ParticleEdit(edit) if edit else None
    with mcpl.MCPLFile(infile) as fi, mcpl.MCPLOutFile(outfile) as fo:
        fo.transfer_metadata(fi)
        #(the comment gives the option as it can be used in shells, with the
        #expression in double quotes):
        fo.hdr_add_comment('mcpltool: extracted particles'
                           + ( f' with -e "{edt.expression}"' if edt else '' ))
        if edt and 'weight' in edt.modified_fields:
            fo.hdr_scale_stat_sums(-1.0)
        for b in fi.particle_blocks:
            fo.add_particles(edt(b) if edt else b)

def test_edit():
    ok = True
    cases = [ 'pdgcode == neutron',
              'ekin > 5keV and ekin <= 20keV and x <= 2cm + abs(y)',
              'not (pdgcode == gamma) or uz > 0.7',
              '(userflags & 1) == 1 and z < 1.5mm',
              'x = -y; y = x; z += 1cm',
              'tmp = x; x = y; y = tmp; swap(ux,uy); rotate_x(30deg)',
              'weight *= 0.5; time = time + 1us',
              'pdgcode == 2112; wavelength = 1.8Aa',
              'pdgcode == gamma; wavelength = wavelength*2',
              'pdgcode != 11; ux = -ux; uz = -uz; pdgcode = 2112',
              'rotate_y(90deg); x > 0cm; weight *= 2',
              'x > 10m' ]
    for edit in cases:
        fresh('py')
        args = ['--extract','a1.mcpl','out.mcpl',f'--edit={edit}']
        rc, out, err = run([sys.executable, '-m', 'mcpldev', *args], 'py')
        py_extract('py/a1.mcpl', 'py/ref.mcpl', edit)
        same = ( rc == 0 and not err
                 and pathlib.Path('py/out.mcpl').read_bytes() == pathlib.Path('py/ref.mcpl').read_bytes() )
        with mcpl.MCPLFile('py/out.mcpl') as f:
            n = f.nparticles
        print(f'mcpltool {" ".join(args)}: {out.strip()}')
        print(f'   same as with the Python API: {same}')
        ok &= same
    #Check some of the results directly:
    with mcpl.MCPLFile('inputs/a1.mcpl') as f:
        b = f.read_block()
    fresh('py')
    run([sys.executable, '-m', 'mcpldev', '--extract', 'a1.mcpl', 'out.mcpl',
         '--edit', 'pdgcode == neutron; rotate_z(90deg); wavelength = 1.8Aa'], 'py')
    with mcpl.MCPLFile('py/out.mcpl') as f:
        e = f.read_block()
    n = b[b.pdgcode==2112]
    checks = [ np.allclose(e.x, -n.y), np.allclose(e.y, n.x), np.allclose(e.z, n.z),
               np.allclose(e.wavelength, 1.8, rtol=1e-6), np.all(e.pdgcode==2112) ]
    print(f'Results of the edit as expected: {all(checks)}')
    ok &= all(checks)
    #Errors:
    for args in ( ['--extract','a1.mcpl','out.mcpl','--edit','ekin'],
                  ['--extract','a1.mcpl','out.mcpl','--edit','foo>1'],
                  ['--extract','a1.mcpl','out.mcpl','--edit','x>1'],
                  ['--extract','a1.mcpl','out.mcpl','--edit','x=2*ux'],
                  ['--extract','a1.mcpl','out.mcpl','--edit'],
                  ['--extract','a1.mcpl','out.mcpl','--edit','x>1cm','--edit','y>1cm'],
                  ['--extract','a1.mcpl','out.mcpl','--edit','wavelength=1.8Aa'],
                  ['--edit','x>1cm','-j','a1.mcpl'],
                  ['--edit','x>1cm','-ba','a1.mcpl'],
                  ['--edit','x>1meV','a1.mcpl'],
                  ['--stats','--edit','x>1km','a1.mcpl'],
                  ['--stats','-pantimuon','a1.mcpl'],
                  ['-pfoo','a1.mcpl'],
                  ['-pgamma','-j','a1.mcpl'],
                  ['--repair','--edit','x>1cm','a1.mcpl'],
                  ['--repair','-pgamma','a1.mcpl'],
                  ['-p22','--merge','out.mcpl','a1.mcpl','a2.mcpl'],
                  ['--extract','-p0','a1.mcpl','out.mcpl'],
                  ['--extract','-pabc','a1.mcpl','out.mcpl'],
                  ['--extract','-pNeutron','a1.mcpl','out.mcpl'],
                  ['--extract','-pfoo','a1.mcpl','out.mcpl'],
                  ['--keep-statsum','a1.mcpl'],
                  ['--stats','--keep-statsum','a1.mcpl'] ):
        fresh('py')
        rc, out, err = run([sys.executable, '-m', 'mcpldev', *args], 'py')
        print(f'mcpltool {" ".join(args)}: exit code {rc}')
        for line in out.splitlines():
            print(f'   | {line}')
        ok &= ( rc != 0 and not err and not pathlib.Path('py/out.mcpl').exists() )
    return ok

def test_statsum():
    #stat:sum entries are kept when selecting particles by their properties or
    #editing other fields than weights, and marked as not available (-1) when
    #selecting based on positions in the file or editing weights:
    ok = True
    for args, expected in ( (['--edit','pdgcode == neutron'], 1000.0),
                            (['--edit','z += 1cm; rotate_z(10deg)'], 1000.0),
                            (['--edit','pdgcode == gamma; wavelength = 1Aa'], 1000.0),
                            (['--edit','weight *= 2'], None),
                            (['--edit','tmp = weight; weight = 2*tmp'], None),
                            (['--edit','weight *= 2','--keep-statsum'], 1000.0),
                            (['--edit','x > 0; weight = 1','--keep-statsum'], 1000.0),
                            (['-l5','--edit','weight *= 2','--keep-statsum'], None),
                            (['-l5'], None),
                            (['-s1','--edit','x > 0'], None),
                            (['--edit','mod(fileidx,2) == 0'], None),
                            (['--edit','n = fileidx; n > 5'], None),
                            (['-e','x = 1cm*fileidx'], 1000.0) ):
        fresh('py')
        rc, out, err = run([sys.executable, '-m', 'mcpldev', '--extract', 'a1.mcpl',
                            'out.mcpl', *args], 'py')
        with mcpl.MCPLFile('py/out.mcpl') as f:
            v = f.stat_sum['nsim']
        print(f'mcpltool --extract {" ".join(args)}: stat:sum:nsim = {v}')
        for line in out.splitlines():
            print(f'   | {line}')
        ok &= ( rc == 0 and not err and v == expected )
    return ok

def main():
    make_inputs()
    results = [ test_mcpltool(), test_edit(), test_statsum() ]
    assert all(results), 'Problems found'

if __name__ == '__main__':
    main()
