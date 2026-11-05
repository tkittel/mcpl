
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

# Test that blocks without particles behave like other blocks, however they
# were obtained (e.g. selecting or slicing blocks which are already empty):
# all fields are arrays of length 0 and they can be written to files.

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir

example_file = test_data_dir.joinpath('example.mcpl')
miscphys_file = test_data_dir.joinpath('ref','miscphys.mcpl.gz')

fields1d = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz',
             'ekin', 'time', 'weight', 'pdgcode', 'userflags', 'fileidx' )
fields3d = ( 'position', 'direction', 'polarisation' )

def check_empty( b, what ):
    assert len(b) == 0, what
    for f in fields1d:
        v = getattr(b,f)
        assert isinstance(v,np.ndarray) and v.shape == (0,), (what,f,v)
    for f in fields3d:
        v = getattr(b,f)
        assert isinstance(v,np.ndarray) and v.shape == (0,3), (what,f,v)
    assert b[0] is None, what
    assert list(b.particles) == [], what
    if b.userdata is not None:
        assert b.userdata.shape == (0,), what
    print(f"  {what}: OK")

def empty_variants( b ):
    """Empty blocks obtained in different ways from block b"""
    e = b[b.x > 1e30]
    yield 'mask', e
    yield 'slice', b[len(b):]
    yield 'index array', b[np.zeros(0,dtype=int)]
    yield 'slice of selection', e[:]
    yield 'selection of selection', e[e.x > 0]
    yield 'index array of selection', e[np.zeros(0,dtype=int)]
    yield 'slice of slice of selection', e[:][:]

def test_file( filename, **kwargs ):
    print(f"Empty blocks from {filename.name} {kwargs or ''}:")
    with mcpl.MCPLFile(filename,**kwargs) as f:
        b = f.read_block()
        for what, e in empty_variants(b):
            check_empty(e,what)
            with mcpl.MCPLOutFile('out.mcpl', allow_overwrite = True) as o:
                o.transfer_metadata(f)
                o.add_particles(e)
                o.add_particles(b[:2])
                o.add_particles(e)
            with mcpl.MCPLFile('out.mcpl') as fo:
                assert fo.nparticles == 2

def test_userdata():
    with mcpl.MCPLOutFile('ud.mcpl') as o:
        o.enable_userdata('temp:float32,tags:uint8[3]')
        for i in range(3):
            o.add_particle( ekin = 1.0, direction = (0,0,1),
                            userdata = { 'temp' : i, 'tags' : [i,i,i] } )
    print("Empty blocks with userdata:")
    with mcpl.MCPLFile('ud.mcpl') as f:
        b = f.read_block()
        for what, e in empty_variants(b):
            check_empty(e,what)
            assert e.userdata.dtype == b.userdata.dtype

def test_no_selected_particles():
    #A selection which matches nothing gives no blocks at all:
    with mcpl.MCPLFile(example_file,edit='x > 1e30cm') as f:
        assert list(f.particle_blocks) == []
    print("No blocks for empty selections: OK")

def main():
    test_file(example_file)
    test_file(miscphys_file)
    test_file(example_file,edit='x += 1cm')
    test_file(example_file,edit='ekin > 0MeV',blocklength=7)
    test_userdata()
    test_no_selected_particles()

if __name__ == '__main__':
    main()
