
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

# Test the MCPLOutFile class by comparing the files it writes with files
# written by the C library, and test its API.

import gzip
import itertools
import os
import pathlib

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.loadlib import getlib

lib = getlib('pywriter')

def same_file(f1, f2):
    return pathlib.Path(f1).read_bytes() == pathlib.Path(f2).read_bytes()

def reference_files():
    for f in sorted(itertools.chain(test_data_dir.joinpath('ref').glob('*.mcpl*'),
                                    test_data_dir.joinpath('reffmt2').glob('*.mcpl*'))):
        if not any(s in f.name for s in ('bad','crash','truncated','statunsupported')):
            yield f

def test_reference_files():
    for f in reference_files():
        name = '/'.join(f.parts[-2:])
        orig = f.read_bytes()
        if not orig.startswith(b'MCPL'):
            orig = gzip.decompress(orig)
        with mcpl.MCPLFile(f, raw_strings=True, blocklength=7) as src:
            with mcpl.MCPLOutFile('xfer.mcpl', allow_overwrite=True) as o:
                o.transfer_metadata(src)
                for b in src.particle_blocks:
                    o.add_particles(b)
            exact = ( pathlib.Path('xfer.mcpl').read_bytes() == orig )
            src.rewind()
            with mcpl.MCPLOutFile('repack_py.mcpl', allow_overwrite=True) as o:
                o.transfer_metadata(src)
                for b in src.particle_blocks:
                    o.add_particles(position=b.position, direction=b.direction,
                                    polarisation=b.polarisation, ekin=b.ekin,
                                    time=b.time, weight=b.weight,
                                    pdgcode=b.pdgcode, userflags=b.userflags)
            version = src.version
        lib.mcpltest_repack(str(f),'repack_c.mcpl')
        repack_same = same_file('repack_py.mcpl','repack_c.mcpl')
        print(f'{name} (MCPL-{version}): exact transfer reproduces file: {exact},'
              f' repacking identical to C: {repack_same}')
        assert repack_same
        assert exact == (version == 3)

def raw_particles(n):
    rng = np.random.default_rng(1)
    d = rng.normal(size=(n,3))
    d /= np.linalg.norm(d,axis=1)[:,None]
    edge = np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1],
                     [0.0,-0.0,1],[-0.0,0,-1],[0,1,-0.0],[0,-1,0.0],
                     [1/np.sqrt(3)]*3,[-1/np.sqrt(2),1/np.sqrt(2),0],
                     [0.6,0.8,0],[0.8,0,-0.6],[0,0.6,-0.8]],float)
    d[:len(edge)] = edge
    rec = np.zeros(n, dtype=[('v','f8',(12,)),('pdg','i4'),('uf','u4')])
    v = rec['v']
    v[:,0:3] = rng.normal(size=(n,3)) * 10.0**rng.integers(-30,30,size=(n,1))
    v[:,3:6] = d
    v[:,6:9] = rng.normal(size=(n,3))
    v[:,9] = np.abs(rng.normal(size=n)) * 10.0**rng.integers(-12,6,size=n)
    v[:20,9] = 0.0
    v[:,10] = rng.random(n) * 1e3
    v[:,11] = rng.random(n) * 5
    rec['pdg'] = rng.choice([2112,22,-11,11,-2147483648,2147483647,1000922350],size=n)
    rec['uf'] = rng.integers(0,2**32,size=n,dtype=np.uint64).astype(np.uint32)
    rec.tofile('raw.bin')
    return { 'x': v[:,0], 'y': v[:,1], 'z': v[:,2], 'direction': v[:,3:6],
             'polarisation': v[:,6:9], 'ekin': v[:,9], 'time': v[:,10],
             'weight': v[:,11], 'pdgcode': rec['pdg'], 'userflags': rec['uf'] }

all_opts = ['', 'd', 'p', 'u', 'P', 'W', 'dpu', 'dPW', 'puPW', 'dpuPW']

def opts_kwargs(opts):
    return { 'opt_singleprec': 'd' not in opts,
             'opt_polarisation': 'p' in opts,
             'opt_userflags': 'u' in opts,
             'opt_universalpdgcode': 2112 if 'P' in opts else 0,
             'opt_universalweight': 2.5 if 'W' in opts else 0 }

def test_raw_values():
    n = 3000
    fields = raw_particles(n)
    for opts in all_opts:
        lib.mcpltest_writefromraw('raw.bin','raw_c.mcpl',opts or '-')
        kw = dict( sourcename='writefromraw', comments=['a comment'],
                   stat_sum={'nsim':-1}, blobs={'blobkey':b'abc\0d'},
                   **opts_kwargs(opts) )
        with mcpl.MCPLOutFile('raw_py_blocks.mcpl', allow_overwrite=True, **kw) as o:
            o.add_particles(**{k:v[:1000] for k,v in fields.items()})
            o.add_particles(**{k:v[1000:] for k,v in fields.items()})
            o.hdr_add_stat_sum('nsim', 12345.0)
        with mcpl.MCPLOutFile('raw_py_single.mcpl', allow_overwrite=True, blocklength=100, **kw) as o:
            for i in range(n):
                o.add_particle(**{k:v[i] for k,v in fields.items()})
            o.hdr_add_stat_sum('nsim', 12345.0)
        same_blocks = same_file('raw_py_blocks.mcpl','raw_c.mcpl')
        same_single = same_file('raw_py_single.mcpl','raw_c.mcpl')
        print(f'Options "{opts}": identical to C with add_particles: {same_blocks},'
              f' with add_particle: {same_single}')
        assert same_blocks and same_single

def test_transfers():
    #Transfer particles into files with other settings, compared with
    #mcpl_transfer_last_read_particle in C:
    fields = raw_particles(500)
    for src_opts in ['', 'dpu']:
        lib.mcpltest_writefromraw('raw.bin','src.mcpl',src_opts or '-')
        for opts in all_opts:
            if 'P' in opts or 'W' in opts:
                continue#universal pdgcode/weight do not match source
            lib.mcpltest_transfer('src.mcpl','xfer_c.mcpl',opts or '-')
            with mcpl.MCPLFile('src.mcpl', blocklength=77) as src:  # noqa: SIM117
                with mcpl.MCPLOutFile('xfer_py.mcpl', allow_overwrite=True, **opts_kwargs(opts)) as o:
                    for b in src.particle_blocks:
                        o.add_particles(b)
            same = same_file('xfer_py.mcpl','xfer_c.mcpl')
            print(f'Transfer from "{src_opts}" to "{opts}": identical to C: {same}')
            assert same
    #Double to single precision: packed direction+ekin are narrowed:
    lib.mcpltest_writefromraw('raw.bin','src.mcpl','dpu')
    with mcpl.MCPLFile('src.mcpl') as src, mcpl.MCPLOutFile('xfer_py.mcpl', allow_overwrite=True) as o:
        for b in src.particle_blocks:
            o.add_particles(b)
    with mcpl.MCPLFile('src.mcpl') as src, mcpl.MCPLFile('xfer_py.mcpl') as res:
        b, r = src.read_block(), res.read_block()
        assert np.array_equal(r.ekin, b.ekin.astype(np.float32))
        assert np.allclose(r.direction, b.direction, atol=1e-6)
        assert np.array_equal(r.x, b.x.astype(np.float32))
        assert np.array_equal(r.pdgcode, fields['pdgcode'])
        print('Transfer from double to single precision gives expected values')
    #Single particles from MCPLFile.read(), including into a file with universal
    #pdgcode where only particles with that pdgcode are accepted:
    with mcpl.MCPLFile('src.mcpl') as src:  # noqa: SIM117
        with mcpl.MCPLOutFile('filtered.mcpl', allow_overwrite=True, opt_universalpdgcode=2112) as o:
            while ( p := src.read() ) is not None:
                if p.pdgcode == 2112:
                    o.add_particle(p)
    with mcpl.MCPLFile('filtered.mcpl') as f:
        print(f'Filtered {f.nparticles} neutrons with universal pdgcode {f.opt_universalpdgcode}')
        assert f.nparticles == int(np.sum(fields['pdgcode'] == 2112))

def expect_error(fct, *a, **kw):
    try:
        fct(*a, **kw)
    except mcpl.MCPLError as e:
        print(f'  Got expected error: {e}')
        return
    raise AssertionError('No error raised')

def test_api():
    #Mix keyword arguments and method calls:
    with mcpl.MCPLOutFile('api', sourcename='MySim', comments=['first comment'],
                          stat_sum={'nsim':-1}, opt_polarisation=True) as o:
        print(f'Writing to {o.filename}')
        o.hdr_add_comment('second comment')
        o.hdr_add_data('cfg', b'\x00\x01binary')
        o.enable_universal_weight(1.5)
        o.enable_polarisation()#already enabled, ignored like in C
        o.add_particle(position=(1,2,3), direction=(0,0,1), ekin=0.025,
                       pdgcode=2112, polarisation=(0,1,0))
        o.add_particles(direction=[[1,0,0],[0,1,0]], ekin=[1.0,2.0], pdgcode=22)
        print(f'  nparticles={o.nparticles} particlesize={o.particlesize}')
        expect_error(o.hdr_add_comment,'too late')
        expect_error(o.enable_userflags)
        expect_error(o.hdr_add_stat_sum,'other',1.0)
        o.hdr_add_stat_sum('nsim', 1000)
        print(f'  stat_sum={dict(o.stat_sum)}')
    with mcpl.MCPLFile('api.mcpl') as f:
        f.dump_hdr()
        f.dump_particles(limit=0)
        print(f'blobs={f.blobs} stat_sum={dict(f.stat_sum)}')
    #Errors:
    print('Errors:')
    with mcpl.MCPLOutFile('err.mcpl', allow_overwrite=True) as o:
        expect_error(o.add_particles, direction=(1,1,0))
        expect_error(o.add_particles, direction=(1,0,0), ekin=-1.0)
        expect_error(o.add_particle, direction=(0,0.5,0))
        expect_error(o.add_particles, direction=[[1,0,0]]*3, ekin=[1.0,2.0])
        expect_error(o.add_particles, position=(0,0,0), x=1.0, direction=(1,0,0))
        expect_error(o.add_particles, direction=(1,0,0), pdgcode=2**31)
    with mcpl.MCPLOutFile('err.mcpl', allow_overwrite=True) as o:
        expect_error(o.hdr_add_comment,'stat:something')
        expect_error(o.hdr_add_comment,'stat:sum:bad')
        expect_error(o.hdr_add_stat_sum,'bad key',1.0)
        expect_error(o.hdr_add_stat_sum,'key',-2.0)
        o.hdr_add_data('k',b'x')
        expect_error(o.hdr_add_data,'k',b'y')
        expect_error(o.enable_universal_pdgcode,0)
        expect_error(o.enable_universal_weight,-1.0)
        o.enable_universal_pdgcode(22)
        expect_error(o.enable_universal_pdgcode,2112)
        o.hdr_add_stat_sum('a',1.0)
        expect_error(o.hdr_add_comment,'stat:sum:a:' + ' '*23 + '2')
        o.hdr_scale_stat_sums(2.0)
        print(f'  stat_sum after scaling={dict(o.stat_sum)}')
        expect_error(o.hdr_scale_stat_sums,0.0)
    expect_error(mcpl.MCPLOutFile,'.mcpl')
    #Gzipped output:
    with mcpl.MCPLOutFile('gz') as o:
        o.add_particles(direction=(0,0,1), ekin=np.linspace(1,2,5))
    o = mcpl.MCPLOutFile('gz2.mcpl.gz', opt_singleprec=False)
    o.add_particles(direction=(0,0,1), ekin=np.linspace(1,2,5))
    o.close()
    with mcpl.MCPLFile('gz2.mcpl.gz') as f:
        print(f'gz2.mcpl.gz: {f.nparticles} particles, ekin={f.read_block().ekin}')
    assert not pathlib.Path('gz2.mcpl').exists()

def test_api_more():
    #Properties describing the header and settings:
    with mcpl.MCPLOutFile(pathlib.Path('props'), sourcename='MySim',
                          comments=['c1','c2'], blobs={'k':b'v'},
                          opt_userflags=True, opt_singleprec=False,
                          opt_universalpdgcode=22, opt_universalweight=2.0) as o:
        print(f'Properties of {o.filename}: sourcename={o.sourcename!r}'
              f' comments={o.comments} blobs={o.blobs}'
              f' opt_userflags={o.opt_userflags}'
              f' opt_polarisation={o.opt_polarisation}'
              f' opt_singleprec={o.opt_singleprec}'
              f' opt_universalpdgcode={o.opt_universalpdgcode}'
              f' opt_universalweight={o.opt_universalweight}')
        #Single particles given by wavelength (gammas, from the universal
        #pdgcode):
        o.add_particle(direction=(0,0,1), wavelength=1.0, userflags=7)
        expect_error(o.add_particle, direction=(0,0,1), wavelength=1.0, ekin=1.0)
        expect_error(o.add_particle, direction=(0,0,1), userflags=-1)
    with mcpl.MCPLFile('props.mcpl') as f:
        p = f.read()
        print(f'  gamma with wavelength 1Aa: ekin={p.ekin:.6g} MeV,'
              f' wavelength={p.wavelength:.6g} Aa, userflags={p.userflags}')
    with mcpl.MCPLOutFile(b'bytesname') as o:
        print(f'Filename given as bytes: {o.filename}')
        expect_error(o.hdr_set_srcname, 'with\0null')
        o.add_particle(direction=(0,0,1), pdgcode=2112, wavelength=1.8)
        expect_error(o.add_particle, direction=(0,0,1), pdgcode=2212, wavelength=1.8)
        expect_error(o.add_particle, direction=(0,0,1), pdgcode=2**31)
        expect_error(o.add_particle, direction=(0,0,1,0))
        expect_error(o.add_particle, direction=(0,0,1), ux=1.0)
        expect_error(o.add_particle, mcpl.MCPLFile('props.mcpl').read(), ekin=1.0)
        try:
            o.add_particle(direction=(0,0,1), energy=1.0)
        except TypeError as e:
            print(f'  Got expected TypeError: {e}')
        expect_error(o.add_particles, direction=(0,0,1), pdgcode=2112.5)
        expect_error(o.add_particles, direction=(0,0,1), ekin=[[1.0,2.0]])
        expect_error(o.add_particles, direction=[[[0,0,1]]])
        expect_error(o.add_particles, 'not a block')
    expect_error(o.add_particle, direction=(0,0,1))#closed
    expect_error(mcpl.MCPLOutFile, 42)
    expect_error(mcpl.MCPLOutFile, 'x'*5000)
    expect_error(mcpl.MCPLOutFile, 'blocks', blocklength=0)
    with mcpl.MCPLOutFile('upc') as o:
        expect_error(o.enable_universal_pdgcode, 2**31)
    #Errors of the MPI helper functions:
    for args in ( ('mpi', 0, 0), ('mpi', 2, 2), ('mpi', 0, 10**9) ):
        expect_error(mcpl.create_outfile_mpi, *args)
    for args in ( ('mpi', 0), ('mpi', 10**9), ('missing', 1), ('missing', 2) ):
        try:
            mcpl.merge_outfiles_mpi(*args)
        except mcpl.MCPLError as e:
            #(without the directory of the test, which differs between runs and
            #platforms, as does the path separator):
            msg = str(e).replace(str(pathlib.Path.cwd())+os.sep,'<cwd>/')
            print(f'  Got expected error: {msg}')
        else:
            raise AssertionError('No error raised')

def test_statsum_syntax():
    #Error messages for comments starting with "stat:sum:" which do not follow
    #the syntax of stat:sum entries (values must have 24 characters):
    v = ' '*23 + '1'
    with mcpl.MCPLOutFile('statsum') as o:
        for c in ( f'stat:sum::{v}', f'stat:sum:{"a"*65}:{v}', f'stat:sum:1abc:{v}',
                   'stat:sum:k:' + ' '*24, 'stat:sum:k:' + ' '*21 + 'abc',
                   'stat:sum:k:' + ' '*21 + '1-+', 'stat:sum:k:' + ' '*22 + '-2',
                   'stat:sum:k:' + ' '*19 + '1e999', 'stat:sum:k:12', 'stat:sum:k' ):
            expect_error(o.hdr_add_comment, c)

def test_single_vs_blocks():
    #add_particle validates single particles without numpy (for speed), so
    #check that it gives the same errors (or files) as add_particles:
    big, huge = 3.4028234663852886e+38, float.fromhex('0x1.ffffffp+127')
    specials = [ 0.0, -0.0, 1.0, -1.0, float('nan'), float('inf'), -float('inf'),
                 big, huge, -huge, 1e300 ]
    fieldvals = []
    for f in ('x','ekin','time','weight','polx'):
        fieldvals += [ ( f, v ) for v in specials ]
    fieldvals += [ ( 'direction', d ) for d in ( (0,0,1), (0,0,-1), (0.6,0.8,0),
                                                 (0,0,1.00001), (0,0,1.0000049),
                                                 (float('nan'),0,1), (0,0,0) ) ]
    fieldvals += [ ( 'pdgcode', v ) for v in ( 22, -11, 2112.0, 2112.5, 2**31, -2**31 ) ]
    fieldvals += [ ( 'userflags', v ) for v in ( 0, 7, -1, 2**32, 3.0, 3.5 ) ]
    settings = [ {}, {'opt_singleprec':False}, {'opt_polarisation':True},
                 {'opt_universalweight':2.0}, {'opt_userflags':True} ]
    n_same = 0
    for sett in settings:
        for field, value in fieldvals:
            res = []
            for single in (True, False):
                fn = f'sb_{int(single)}'
                fields = { 'direction' : (0,0,1), 'ekin' : 1.0, 'weight' : 1.0 }
                if 'opt_universalweight' in sett:
                    del fields['weight']
                fields[field] = value
                try:
                    with mcpl.MCPLOutFile(fn, allow_overwrite=True, **sett) as o:
                        if single:
                            o.add_particle(**fields)
                        else:
                            o.add_particles(**{ k : [v]
                                                for k,v in fields.items() })
                    res.append( pathlib.Path(fn+'.mcpl').read_bytes() )
                except mcpl.MCPLError as e:
                    res.append( f'MCPLError: {e}' )
                pathlib.Path(fn+'.mcpl').unlink(missing_ok=True)
            assert res[0] == res[1], (sett, field, value, res)
            n_same += 1
    print(f'add_particle and add_particles gave the same results for {n_same} cases')
    with mcpl.MCPLOutFile('sb') as o:
        expect_error(o.add_particle, direction=(0,0,1), pdgcode=2112.5)

def test_example():
    #Run examples/pyexample_writemcpl with the mcpl module being tested:
    import sys
    f = test_data_dir.joinpath('pyexamples','pyexample_writemcpl')
    code = f.read_text().replace('\nimport mcpl\n','\nimport mcpldev as mcpl\n')
    assert 'import mcpldev as mcpl' in code
    sys.argv = [ str(f), 'example_output.mcpl.gz' ]
    exec(compile(code,str(f),'exec'),{'__name__':'__main__'})  # noqa: S102
    with mcpl.MCPLFile('example_output.mcpl.gz') as f:
        print(f'pyexample_writemcpl wrote {f.nparticles} particles from'
              f' "{f.sourcename}" with comments {f.comments}')

def test_invalid_arguments():
    print('Invalid arguments of MCPLOutFile leave no file behind:')
    for kw in ( { 'opt_universalweight' : -1.0 },
                { 'userdata_layout' : 'x:float32' },
                { 'blobs' : { 'bad key' : b'data' } },
                { 'stat_sum' : { '1bad' : 1.0 } },
                { 'blocklength' : 0 } ):
        expect_error(mcpl.MCPLOutFile,'invalid_args',**kw)
        assert not pathlib.Path('invalid_args.mcpl').exists(), kw
    print('Invalid arguments of MCPLFile:')
    with mcpl.MCPLOutFile('valid.mcpl') as o:
        o.add_particle(pdgcode=2112,ekin=1.0,uz=1.0)
    expect_error(mcpl.MCPLFile,'valid.mcpl',blocklength=0)

def statsums_on_disk(fn):
    """The stat:sum entries as they are in the bytes of a file (not as read by
    MCPL)"""
    data = pathlib.Path(fn).read_bytes()
    res, i = [], data.find(b'stat:sum:')
    while i >= 0:
        j = data.index(b':',i+9)
        res.append( data[i:j+25].decode() )
        i = data.find(b'stat:sum:',j)
    return res

def test_statsums_until_closed():
    """The stat:sum values are -1 in the file until it is closed (also those
    added as comments, and those changed after particles were added), so
    unfinished files never have values"""
    o = mcpl.MCPLOutFile('statsums.mcpl', stat_sum = { 'nevents' : 5.0 } )
    o.hdr_add_comment('stat:sum:fromcomment:                       7')
    for _ in range(3):
        o.add_particle(pdgcode=2112,ekin=1.0,uz=1.0)
    o.hdr_add_stat_sum('nevents',6.0)
    o._flush_pending()
    o._fh.flush()
    print('Unfinished file:',statsums_on_disk('statsums.mcpl'))
    o.close()
    print('Closed file:',statsums_on_disk('statsums.mcpl'))

def test_exception_in_with():
    """An exception inside the with-statement leaves the file unfinished (with
    its particles, but without their number and the stat:sum values), so it
    can be recognised and repaired"""
    try:
        with mcpl.MCPLOutFile('unfinished.mcpl', stat_sum = { 'nevents' : 5.0 } ) as o:
            for _ in range(3):
                o.add_particle(pdgcode=2112,ekin=1.0,uz=1.0)
            raise RuntimeError('stopped')
    except RuntimeError as e:
        print(f'Exception in the with-statement: {e}')
    print('Unfinished file:',statsums_on_disk('unfinished.mcpl'))
    with mcpl.MCPLFile('unfinished.mcpl') as f:
        print(f'  read with {f.nparticles} particles, stat_sum {dict(f.stat_sum)}')
    mcpl.repair('unfinished.mcpl')
    with mcpl.MCPLFile('unfinished.mcpl') as f:
        print(f'  after repair: {f.nparticles} particles, stat_sum {dict(f.stat_sum)}')

test_reference_files()
test_raw_values()
test_statsums_until_closed()
test_exception_in_with()
test_transfers()
test_api()
test_api_more()
test_statsum_syntax()
test_single_vs_blocks()
test_invalid_arguments()
test_example()
