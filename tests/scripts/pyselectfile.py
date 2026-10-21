
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

# Test the pick and edit arguments of MCPLFile and MCPLOutFile, and the
# blocks of edited particles.

import pathlib
import shutil

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir

shutil.copy(test_data_dir.joinpath('example.mcpl'),'example.mcpl')
ex = 'example.mcpl'

def same_file(f1, f2):
    return pathlib.Path(f1).read_bytes() == pathlib.Path(f2).read_bytes()

def test_read():
    ref = mcpl.MCPLFile(ex).read_block()
    isn = ref.pdgcode == 2112
    f = mcpl.MCPLFile(ex, blocklength=100, pick='pdgcode == neutron')
    print(f'pick={f.pick!r} edit={f.edit!r} nparticles={f.nparticles}')
    lens = [ len(b) for b in f.particle_blocks ]
    print(f'block lengths with blocklength=100: {lens}')
    assert sum(lens) == isn.sum()
    idx = np.concatenate([ b.fileidx for b in f.particle_blocks ])
    assert np.array_equal(idx, np.flatnonzero(isn))
    ps = list(f.particles)
    assert [ p.fileidx for p in ps ] == list(np.flatnonzero(isn))
    assert all( p.ekin == ref.ekin[p.fileidx] for p in ps[:20] )
    f.rewind()
    print(f'first particle after rewind: {f.read().fileidx}')
    try:
        f.skip_forward(5)
    except mcpl.MCPLError as e:
        print(f'skip_forward: {e}')
    g = mcpl.MCPLFile(ex, pick='pdgcode == neutron', edit='z += 1m; rotate_z(90deg)')
    b = g.read_block()
    n = ref[isn]
    ok = ( np.allclose(b.z, n.z+100) and np.allclose(b.x, -n.y) and np.allclose(b.ux, -n.uy)
           and np.allclose(b.position[:,0], -n.y) and np.allclose(b.direction[:,1], n.ux)
           and np.allclose(b.polarisation, 0) and np.array_equal(b.ekin, n.ekin) )
    print(f'edited block ({type(b).__name__}) as expected: {ok}')
    assert ok
    sub = b[b.ekin < 0.1]
    ok = ( np.allclose(sub.z, n.z[n.ekin<0.1]+100)
           and np.array_equal(sub.fileidx, np.flatnonzero(isn)[n.ekin<0.1]) )
    print(f'selection from edited block: {len(sub)} particles, as expected: {ok}')
    assert ok
    p = sub[2]
    print(f'particle {p.fileidx}: z={p.z:g} x={p.x:.6g} y={p.y:.6g}')
    mcpl.dump_file(ex, header=False, limit=3, pick='pdgcode == gamma', edit='x = 0')
    mcpl.dump_stats(mcpl.collect_stats(mcpl.MCPLFile(ex, pick='pdgcode == neutron',
                                                     edit='z += 1m'),
                                       bin_data=False, pick='ekin < 1MeV'))

def test_write():
    with mcpl.MCPLOutFile('a.mcpl') as o:
        for blk in mcpl.MCPLFile(ex, pick='pdgcode == neutron', edit='z += 1m').particle_blocks:
            o.add_particles(blk)
    with mcpl.MCPLOutFile('b.mcpl') as o:
        for blk in mcpl.MCPLFile(ex).particle_blocks:
            s = blk[blk.pdgcode == 2112]
            o.add_particles(s, z = s.z + 100)
    with mcpl.MCPLOutFile('c.mcpl', pick='pdgcode == neutron', edit='z += 1m') as o:
        for blk in mcpl.MCPLFile(ex).particle_blocks:
            o.add_particles(blk)
    with mcpl.MCPLOutFile('d.mcpl', pick='pdgcode == neutron', edit='z += 1m') as o:
        for p in mcpl.MCPLFile(ex).particles:
            o.add_particle(p)
    print('edited blocks written like explicit field values:', same_file('a.mcpl','b.mcpl'))
    print('MCPLOutFile with pick and edit gives the same:', same_file('a.mcpl','c.mcpl'),
          same_file('a.mcpl','d.mcpl'))
    assert same_file('a.mcpl','b.mcpl') and same_file('a.mcpl','c.mcpl') and same_file('a.mcpl','d.mcpl')
    #Fields given with add_particles are applied before the selection and edit:
    with mcpl.MCPLOutFile('e.mcpl', pick='z > 50cm', edit='weight *= 2') as o:
        for blk in mcpl.MCPLFile(ex).particle_blocks:
            o.add_particles(blk, z = np.where(blk.pdgcode == 22, 100.0, 0.0))
    e = mcpl.MCPLFile('e.mcpl').read_block()
    print(f'fields then selection and edit: {len(e)} particles, weights {set(e.weight.tolist())},'
          f' pdgcodes {set(e.pdgcode.tolist())}')
    #Particles given as arrays:
    with mcpl.MCPLOutFile('r.mcpl', pick='ekin > 1MeV', edit='weight *= 2; x = 2cm') as o:
        o.add_particles(direction=(0,0,1), ekin=[0.5,1.5,2.5], weight=1.0, pdgcode=2112)
        o.add_particle(direction=(0,0,1), ekin=3.0, weight=1.0, pdgcode=22)
        o.add_particle(direction=(0,0,1), ekin=0.1, weight=1.0, pdgcode=22)
    r = mcpl.MCPLFile('r.mcpl').read_block()
    print(f'arrays: ekin={r.ekin} weight={r.weight} x={r.x} pdgcode={r.pdgcode}')
    for kw in ( {'pick':'x > 2'}, {'edit':'x = 2'}, {'pick':'wavelength > 1Aa'} ):
        try:
            with mcpl.MCPLOutFile('err.mcpl', **kw) as o:
                for blk in mcpl.MCPLFile(ex).particle_blocks:
                    o.add_particles(blk)
            print(f'MCPLOutFile({kw}): no error')
        except mcpl.MCPLError as err:
            print(f'MCPLOutFile({kw}): {err}')
    #fileidx is the position in the file the particles are read from, so it
    #can not be used for particles given as arrays:
    with mcpl.MCPLOutFile('fidx.mcpl', pick='mod(fileidx,100) == 0') as o:
        for blk in mcpl.MCPLFile(ex).particle_blocks:
            o.add_particles(blk)
    with mcpl.MCPLFile('fidx.mcpl') as f:
        print('MCPLOutFile with pick using fileidx:',f.nparticles,'particles')
    try:
        with mcpl.MCPLOutFile('fidx2.mcpl', pick='fileidx > 2') as o:
            o.add_particles(x=[1.0,2.0],ekin=1.0,pdgcode=2112,weight=1.0)
        print('fileidx with arrays: no error')
    except mcpl.MCPLError as err:
        print(f'fileidx with arrays: {err}')

def test_range():
    #skip and limit choose a range of the file, before pick and edit (as -s
    #and -l of mcpltool), for all block lengths:
    ref = mcpl.MCPLFile(ex).read_block()
    for skip, limit, pick in ( (5,None,None), (0,13,None), (250,300,'pdgcode == neutron'),
                               (999,50,None), (2000,None,None), (10,0,None) ):
        n = min( len(ref), skip + ( len(ref) if limit is None else limit ) )
        idx = np.arange(min(skip,len(ref)),n)
        if pick is not None:
            idx = idx[ref.pdgcode[idx] == 2112]
        ok = True
        for blocklength in ( 7, 100, 10000 ):
            f = mcpl.MCPLFile(ex, blocklength=blocklength, skip=skip, limit=limit,
                              pick=pick, edit='z += 1m')
            got = [ b.fileidx for b in f.particle_blocks ]
            got = np.concatenate(got) if got else np.zeros(0,dtype=int)
            ok = ok and np.array_equal(got, idx) and [ p.fileidx for p in f.particles ] == list(idx)
            ok = ok and np.allclose(np.concatenate([ b.z for b in f.particle_blocks ] or [[]]),
                                    ref.z[idx] + 100)
        print(f'skip={skip} limit={limit} pick={pick!r}: {len(idx)} particles, as expected: {ok}')
        assert ok
    for bad in ( {'skip':-1}, {'limit':2.5}, {'skip':True} ):
        try:
            mcpl.MCPLFile(ex, **bad)
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')
    try:
        mcpl.MCPLFile(ex, skip=3).skip_forward(1)
    except mcpl.MCPLError as e:
        print(f'skip_forward: {e}')

test_read()
test_range()
test_write()
