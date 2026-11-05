
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

# Test mcpltool --create-examples[=N]: the three example files are created
# with the requested number of particles, with sensible values, and with the
# expected header contents. Existing files are never overwritten, a dry run
# writes nothing, and invalid arguments give errors.

import contextlib
import pathlib
import sys

import mcpldev as mcpl
from mcpldev._numpy import np


def run(*args):
    print(f'--> mcpltool {" ".join(args)}',flush=True)
    try:
        with contextlib.redirect_stderr(sys.stdout):
            mcpl.app_mcpltool(['mcpltool',*args])
    except SystemExit as e:
        print(f'    exit code {e.code}',flush=True)
    except mcpl.MCPLError as e:
        #(as the mcpltool command):
        print(f'    mcpltool: {e!s}\n    exit code 1',flush=True)

def files():
    return sorted( f.name for f in pathlib.Path('.').iterdir()
                   if f.name.startswith('mcplexample') )

def check(fn, n):
    with mcpl.MCPLFile(fn) as f:
        assert f.nparticles == n
        print(f'{fn}: {f.nparticles} particles, comments {f.comments!r},'
              f' polarisation: {f.opt_polarisation},'
              f' userdata: {f.userdata_layout or None}')
        for b in f.particle_blocks:
            assert np.all(b.ekin > 0.0)
            assert np.all(b.weight > 0.0)
            assert np.all(np.isfinite(b.position))
            assert np.all(np.isfinite(b.time))
            assert np.allclose(np.linalg.norm(b.direction,axis=1),1.0,atol=1e-5)
            if f.opt_polarisation:
                assert np.all(np.linalg.norm(b.polarisation,axis=1) <= 1.0+1e-6)

def main():
    run('--create-examples=500','--dry-run')
    run('--create-examples=2.5e3','--dry-run')
    assert not files()
    run('--create-examples=2500')
    print('Created:',', '.join(files()))
    for fn in files():
        check(fn,2500)
    print('Existing files are not overwritten:')
    run('--create-examples=10')
    for bad in ('--create-examples=0','--create-examples=abc',
                '--create-examples=-5','--create-examples=1,000',
                '--create-examples=1.5','--create-examples=1e-3'):
        run(bad)
    run('--create-examples','-j','foo.mcpl')
    print('A second run gives the same particles (fixed random seed):')
    first = { fn : particles(fn) for fn in files() }
    for fn in files():
        pathlib.Path(fn).unlink()
    run('--create-examples=2500')
    for fn in files():
        print(f'{fn}: same particles: {np.array_equal(first[fn],particles(fn))}')

def particles(fn):
    with mcpl.MCPLFile(fn,blocklength=1000000) as f:
        b = next(iter(f.particle_blocks))
        return np.concatenate([ b.position.ravel(), b.direction.ravel(),
                                b.ekin, b.time, b.weight ])

if __name__ == '__main__':
    main()
