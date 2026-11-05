
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

# Test the handling of NaN and infinite values in particle data, which are not
# allowed: files with such values can still be read (with a warning, once per
# file), but such particles can not be written. The C and Python APIs are
# compared in pyc_equiv.py and pytool_equiv.py, this tests the rest of the
# Python API.

import pathlib

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.mcplpatch import set_values


def make_files():
    with mcpl.MCPLOutFile('ok.mcpl', opt_polarisation = True) as o:
        o.add_particles( direction = (0,0,1), ekin = np.linspace(1,2,25),
                         x = np.arange(25.0), pdgcode = 2112 )
    set_values('ok.mcpl','nan.mcpl',7,{'x':float('nan')})
    set_values('nan.mcpl','nan2.mcpl',20,{'polz':float('inf')})

def test_reading():
    for title, fct in (
            ('read() of all particles', lambda f : [ f.read() for _ in range(25) ]),
            ('read() of the first 7 particles', lambda f : [ f.read() for _ in range(7) ]),
            ('skip past particle 7, then read()', lambda f : ( f.skip_forward(8),
                                                              [ f.read() for _ in range(5) ] )),
            ('read_block() with blocklength 10', lambda f : [ f.read_block() for _ in range(3) ]),
            ('particle_blocks', lambda f : list(f.particle_blocks)),
            ('particles twice', lambda f : ( list(f.particles), list(f.particles) )) ):
        for fn in ('nan.mcpl','nan2.mcpl'):
            print(f'==> {title} of {fn}:')
            with mcpl.MCPLFile(fn,blocklength=10) as f:
                fct(f)
    print('==> condition (with blocklength 10):')
    with mcpl.MCPLFile('nan.mcpl',blocklength=10,edit='ekin > 1.5MeV') as f:
        print(f'   selected {sum(len(b) for b in f.particle_blocks)} particles')

def test_errors():
    with mcpl.MCPLFile('nan.mcpl') as f:
        b = f.read_block()
    def expect_error(title, fct):
        try:
            fct()
            print(f'{title}: no error')
        except mcpl.MCPLError as e:
            print(f'{title}: MCPLError: {e}')
    expect_error('collect_stats', lambda : mcpl.collect_stats('nan.mcpl'))
    expect_error('ParticleEdit("x > 10cm")', lambda : mcpl.ParticleEdit('x > 10cm')(b))
    print('ParticleEdit("ekin > 1.2MeV") keeps'
          f' {len(mcpl.ParticleEdit("ekin > 1.2MeV")(b))}')
    with mcpl.MCPLOutFile('out.mcpl') as o:
        expect_error('add_particles(block)', lambda : o.add_particles(b))
        expect_error('add_particles(block of finite particles)',
                     lambda : o.add_particles(b[np.isfinite(b.x)]))
        expect_error('add_particles(block,x=...) replacing the NaN',
                     lambda : o.add_particles(b,x=np.zeros(len(b))))
        expect_error('add_particles(block,time=...) with NaN',
                     lambda : o.add_particles(b[:3],time=[0.0,float('nan'),0.0]))
        expect_error('add_particle(x=inf)',
                     lambda : o.add_particle(x=float('inf'),direction=(0,0,1)))
        print(f'   out.mcpl has {o.nparticles} particles')
    #A failing forcemerge does not leave the unfinished file behind:
    pathlib.Path('ok_dp.mcpl').unlink(missing_ok=True)
    with mcpl.MCPLFile('ok.mcpl') as f, mcpl.MCPLOutFile('ok_dp.mcpl',opt_singleprec=False) as o:
        for b in f.particle_blocks:
            o.add_particles(b)
    expect_error('forcemerge_files', lambda : mcpl.forcemerge_files('merged.mcpl',
                                                                    ['ok_dp.mcpl','nan.mcpl']))
    print(f'   merged.mcpl exists: {pathlib.Path("merged.mcpl").exists()}')

def test_directions():
    #Directions with NaN or -0.0 values are unpacked like in the C library:
    #computed components which would be NaN are 0, and the sign of -0.0 is
    #kept (in MCPL-2 files, which pack directions differently). Values found
    #with the C library:
    set_values('ok.mcpl','dirnan.mcpl',4,{'uve1':float('nan')})
    with mcpl.MCPLFile('dirnan.mcpl') as f:
        b = f.read_block()
        assert np.isnan(b.ux[4]) and b.uy[4] == 0.0 and b.uz[4] == 0.0, b.direction[4]
    print('==> NaN in packed direction: ux=nan, uy=0, uz=0 (as in C)')
    fmt2 = test_data_dir.joinpath('reffmt2','reffile_1.mcpl')
    set_values(fmt2,'fmt2_negzero.mcpl',1,{'uve1':-0.0})
    set_values('fmt2_negzero.mcpl','fmt2.mcpl',2,{'uve1':float('nan')})
    with mcpl.MCPLFile('fmt2.mcpl') as f:
        b = f.read_block()
        assert b.ux[1] == 0.0 and np.signbit(b.ux[1]), b.direction[1]
    print('==> MCPL-2 direction with -0.0: ux=-0.0 (as in C)')
    #Reading MCPL-2 files with NaN values also works without math.fma (Python
    #versions before 3.13), where they are handled in Python:
    import math
    fma = getattr(math,'fma',None)
    if fma is not None:
        del math.fma
    try:
        with mcpl.MCPLFile('fmt2.mcpl') as f:
            b = f.read_block()
        assert np.isnan(b.ux[2]), b.direction[2]
    finally:
        if fma is not None:
            math.fma = fma
    print('==> MCPL-2 file with NaN in directions read without math.fma')

if __name__ == '__main__':
    make_files()
    test_reading()
    test_errors()
    test_directions()
