
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

# Test indexing of particle blocks, and MCPLOutFile.add_particles with blocks
# and new values of some of their fields.

import warnings

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir

example_file = test_data_dir.joinpath('example.mcpl')

def raw(fn):
    with mcpl.MCPLFile(fn) as f:
        return f.headersize, np.concatenate([ b._data for b in f.particle_blocks ])

def test_block_indexing():
    with mcpl.MCPLFile(example_file, blocklength=300) as f:
        f.read_block()
        b = f.read_block()
        print(f'second block: {len(b)} particles at offset {b.file_offset}')
        for sel, desc in [ (slice(10,20), '[10:20]'),
                           (slice(None,None,2), '[::2]'),
                           (np.array([5,3,5]), '[[5,3,5]]'),
                           (b.pdgcode == 22, '[pdgcode==22]'),
                           (slice(0,0), '[0:0]') ]:
            s = b[sel]
            assert isinstance(s, mcpl.MCPLParticleBlock)
            assert np.array_equal(s.ekin, b.ekin[sel]) and np.array_equal(s.position, b.position[sel])
            print(f'  block{desc}: {len(s)} particles, offset {s.file_offset}, '
                  f'pdgcodes {sorted(set(s.pdgcode.tolist()))}')
        s = b[b.ekin < 0.1][2:4]
        print(f'  nested selection: {len(s)} particles, ekin={np.array2string(s.ekin,precision=5)}')
        p = b[10:20][3]
        assert p.ekin == b[13].ekin
        print(f'  single particle of selection: ekin={p.ekin:.6g}')

def test_transfer_and_edit():
    #Transfer of selected blocks must keep the packed data unchanged:
    with mcpl.MCPLFile(example_file, blocklength=128) as f, mcpl.MCPLOutFile('sel.mcpl') as o:
        o.transfer_metadata(f)
        for b in f.particle_blocks:
            o.add_particles( b[b.pdgcode==2112] )
    _, d = raw('sel.mcpl')
    _, dref = raw(example_file)
    with mcpl.MCPLFile(example_file) as f:
        isn = f.read_block().pdgcode == 2112
    print(f'transferred {len(d)} neutrons, packed data identical: {np.array_equal(d, dref[isn])}')
    assert np.array_equal(d, dref[isn])
    #Edits of some fields keep the packed values of the others unchanged:
    with mcpl.MCPLFile(example_file) as f, mcpl.MCPLOutFile('edit.mcpl') as o:
        o.transfer_metadata(f)
        for b in f.particle_blocks:
            o.add_particles( b, x = -b.y, y = b.x, weight = 2.0 )
    _, d = raw('edit.mcpl')
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    same = [ k for k in d.dtype.names if np.array_equal(d[k], dref[k]) ]
    print(f'edit of x, y, weight: unchanged packed fields: {same}')
    with mcpl.MCPLFile('edit.mcpl') as f:
        e = f.read_block()
    assert np.array_equal(e.x, (-b.y).astype(np.float32)) and np.array_equal(e.y, b.x)
    assert np.all(e.weight == 2.0)
    #Edits of the direction and ekin:
    with mcpl.MCPLFile(example_file) as f, mcpl.MCPLOutFile('edit2.mcpl') as o:
        for b in f.particle_blocks:
            n = b[b.pdgcode==2112]
            o.add_particles( n, ux = -n.uy, uy = n.ux, wavelength = 4.0 )
    with mcpl.MCPLFile('edit2.mcpl') as f:
        e = f.read_block()
    n = b[b.pdgcode==2112]
    ok = ( np.allclose(e.ux, -n.uy, atol=1e-6) and np.allclose(e.uy, n.ux, atol=1e-6)
           and np.allclose(e.uz, n.uz, atol=1e-6) and np.allclose(e.wavelength, 4.0, rtol=1e-6) )
    print(f'edit of direction and wavelength: {len(e)} particles, as expected: {ok}')
    assert ok
    #Errors:
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    o = mcpl.MCPLOutFile('err.mcpl')
    for kw in [ { 'wavelength': 1.8 },
                { 'wavelength': 1.8, 'ekin': 1.0 },
                { 'x': np.zeros(3) },
                { 'foo': 1.0 } ]:
        try:
            o.add_particles( b, **kw )
            print(f'add_particles(block,{sorted(kw)}): no error')
        except (mcpl.MCPLError, TypeError) as e:
            print(f'add_particles(block,{sorted(kw)}): {type(e).__name__}: {e}')
    o.close()

def test_fileidx():
    with mcpl.MCPLFile(example_file, blocklength=300) as f:
        f.read_block()
        b = f.read_block()
        s = b[b.pdgcode == 22][1:3]
        print(f'fileidx of selection: {s.fileidx}, of particles:'
              f' {[p.fileidx for p in s.particles]}')
        assert np.array_equal(s.fileidx, b.fileidx[b.pdgcode == 22][1:3])
        #The name used in 2.2.8 and earlier still works, with a warning:
        with warnings.catch_warnings(record=True) as wlist:
            warnings.simplefilter('always')
            old = s[0].file_index
        print(f'deprecated file_index: {old}, warnings:'
              f' {[ f"{w.category.__name__}: {w.message}" for w in wlist ]}')

def test_double_precision():
    #Like in the C API, all floating point fields are double precision numbers
    #(native float64), also in files storing single precision numbers:
    fields = ( 'x','y','z','ux','uy','uz','polx','poly','polz','ekin','time',
               'weight','position','direction','polarisation' )
    #(the numbered reference files, not the deliberately broken ones):
    files = [ f for f in test_data_dir.joinpath('ref').glob('reffile_*.mcpl')
              if f.stem.split('_')[1].isdigit() ]
    for fn in sorted(files):
        with mcpl.MCPLFile(fn) as f:
            b = f.read_block()
            if b is None:
                continue
            bad = [ fl for fl in fields if np.asarray(getattr(b,fl)).dtype != np.float64 ]
            p = b.particles.__next__() if len(b) else None
            bad += [ f'particle.{fl}' for fl in fields[:12]
                     if p is not None and not isinstance(getattr(p,fl),float) ]
            print(f'{fn.name}: singleprec={f.opt_singleprec}, all fields double: {not bad}')
            assert not bad, (fn.name,bad)

def test_mixed_reading():
    #read() and read_block() continue where the other stopped, without
    #skipping or repeating particles: read_block() after read() gives the rest
    #of the block of the particle which read() returned (also when particles
    #are edited, or skipped with skip_forward):
    with mcpl.MCPLOutFile('mixed.mcpl') as o:
        o.add_particles( x = np.arange(25.0), uz = 1.0, ekin = 1.0,
                         pdgcode = 2112, weight = 1.0 )
    def pos(v):
        if v is None:
            return None
        return round(float(v.x)) if isinstance(v,mcpl.MCPLParticle) else [ round(float(x)) for x in v.x ]
    calls = 'BPBPPBBP'
    for kw in ( {}, { 'edit' : 'x != 3cm' }, { 'skip' : 2, 'limit' : 21 },
                { 'edit' : 'x += 100cm' } ):
        with mcpl.MCPLFile('mixed.mcpl', blocklength = 10, **kw) as f:
            res = [ pos( f.read_block() if c == 'B' else f.read() ) for c in calls ]
        print(f'{calls} with {kw}:')
        for c, r in zip(calls,res):
            print(f'  {"read_block" if c == "B" else "read"}: {r}')
        seen = [ x for r in res if r is not None for x in ( r if isinstance(r,list) else [r] ) ]
        assert seen == sorted(set(seen))
        #read() after the loop over the blocks, and the reverse:
        with mcpl.MCPLFile('mixed.mcpl', blocklength = 10, **kw) as f:
            for b in f.particle_blocks:
                pass
            after = f.read()
            n = sum( 1 for p in f.particles )
            f.rewind()
            f.read()
            rest = f.read_block()
        print(f'  read after the blocks: {after}, particles: {n},'
              f' first block after read: {pos(rest)}')
        assert after is None
    with mcpl.MCPLFile('mixed.mcpl', blocklength = 10) as f:
        f.skip_forward(5)
        b = f.read_block()
        print(f'skip_forward(5): read_block: {pos(b)} (file offset {b.file_offset}),'
              f' read: {pos(f.read())}')

if __name__ == '__main__':
    test_double_precision()
    test_block_indexing()
    test_fileidx()
    test_transfer_and_edit()
    test_mixed_reading()
