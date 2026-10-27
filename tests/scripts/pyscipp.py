
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


# NEEDS: numpy scipp

# Test conversion of particles to scipp data arrays (MCPLFile.to_scipp and
# MCPLFile.scipp_blocks). The scipp package needs Python 3.12 or later.

import contextlib
import io

import mcpldev as mcpl
import mcpldev._scipp
import numpy as np
import scipp as sc
from MCPLTestUtils.dirs import test_data_dir

example_file = test_data_dir.joinpath('example.mcpl')
miscphys_file = test_data_dir.joinpath('ref','miscphys.mcpl.gz')
empty_file = test_data_dir.joinpath('ref','reffile_empty.mcpl')

def all_blocks( filename, **kwargs ):
    with mcpl.MCPLFile(filename,**kwargs) as f:
        return [ b[:] for b in f.particle_blocks ]

def concat( blocks, field ):
    return np.concatenate([ np.asarray(getattr(b,field)) for b in blocks ])

def check_values( da, blocks, vectors = False ):
    """Compare the data array with the fields of the blocks"""
    n = sum(len(b) for b in blocks)
    assert da.sizes == { 'particle' : n }, da.sizes
    w = concat(blocks,'weight')
    assert np.array_equal(da.values,w)
    assert np.array_equal(da.variances,w*w)
    assert da.unit == sc.units.dimensionless
    fields = [ 'ekin', 'time', 'pdgcode' ]
    if vectors:
        for vname, fname in [('position','position'),('direction','direction')]:
            assert np.array_equal(da.coords[vname].values,
                                  np.concatenate([b.__getattribute__(fname)
                                                  for b in blocks]))
    else:
        fields += [ 'x', 'y', 'z', 'ux', 'uy', 'uz' ]
    for k in fields:
        assert np.array_equal(da.coords[k].values,concat(blocks,k)), k
    units = { 'x' : 'cm', 'ekin' : 'MeV', 'time' : 'ms' }
    for k, u in units.items():
        if k in da.coords:
            assert da.coords[k].unit == sc.Unit(u), (k,da.coords[k].unit)
    assert da.coords['pdgcode'].unit is None

def test_basic():
    blocks = all_blocks(example_file)
    with mcpl.MCPLFile(example_file,blocklength=7) as f:
        da = f.to_scipp()
        check_values(da,blocks)
        assert set(da.coords) == { 'x','y','z','ux','uy','uz','ekin','time',
                                   'pdgcode' }, set(da.coords)
        check_values(f.to_scipp(vectors=True),blocks,vectors=True)
        da2 = f.to_scipp(variances=False,dim='event')
        assert da2.variances is None and da2.dims == ('event',)
    #The blocks put together give the same:
    with mcpl.MCPLFile(example_file,blocklength=7) as f:
        das = list(f.scipp_blocks())
        blocks7 = all_blocks(example_file,blocklength=7)
        assert len(das) == len(blocks7) and len(das) > 3
        for d, b in zip(das,blocks7):
            check_values(d,[b])
        assert sc.identical(sc.concat(das,'particle'),da)
        sel = list(f.scipp_blocks(pick='pdgcode == neutron',
                                  coords={'r':'hypot(x,y)'},vectors=True))
        dsel = f.to_scipp(pick='pdgcode == neutron',
                          coords={'r':'hypot(x,y)'},vectors=True)
        assert sc.identical(sc.concat(sel,'particle'),dsel)
    #scipp can then do the rest:
    h = da.hist(ekin=10)
    assert np.isclose(h.sum().value,da.sum().value)
    print("Basic conversion OK")

def test_options_of_file():
    #Polarisation and userflags (in the file):
    blocks = all_blocks(miscphys_file)
    da = mcpl.MCPLFile(miscphys_file).to_scipp()
    check_values(da,blocks)
    for k in ('polx','poly','polz'):
        assert np.array_equal(da.coords[k].values,concat(blocks,k))
    uf = concat(blocks,'userflags')
    assert da.coords['userflags'].dtype == sc.DType.int64
    assert np.array_equal(da.coords['userflags'].values,uf.astype(np.int64))
    dav = mcpl.MCPLFile(miscphys_file).to_scipp(vectors=True)
    assert 'polx' not in dav.coords
    assert np.array_equal(dav.coords['polarisation'].values,
                          np.stack([concat(blocks,k) for k in ('polx','poly','polz')],axis=1))
    #Empty file:
    da = mcpl.MCPLFile(empty_file).to_scipp()
    assert da.sizes == { 'particle' : 0 } and 'polx' in da.coords
    print("Polarisation, userflags and empty files OK")

def test_userdata():
    with mcpl.MCPLOutFile('ud.mcpl') as o:
        o.enable_userdata('temp:float32:K,tags:uint8[3],big:uint64,id:int16,p:float64:cm,'
                          'dir:float32[2]:deg,q:float64:cm^-1.MeV')
        for i in range(5):
            o.add_particle( pdgcode = 2112, ekin = 1e-9*(i+1),
                            position = (i,0,0), direction = (0,0,1),
                            userdata = { 'temp' : 300+i, 'tags' : [i,i+1,i+2],
                                         'big' : 2**40+i, 'id' : -i,
                                         'p' : 0.5*i, 'dir' : [i,-i], 'q' : 2.0*i } )
    da = mcpl.MCPLFile('ud.mcpl').to_scipp()
    c = da.coords
    #(with the units of the fields, if any):
    assert c['temp'].dtype == sc.DType.float32 and c['temp'].unit == sc.Unit('K')
    assert c['tags_0'].unit is None and c['p'].unit == sc.Unit('cm')
    assert c['dir_1'].unit == sc.Unit('deg') and list(c['dir_1'].values) == [ -i for i in range(5) ]
    assert c['q'].unit == sc.Unit('MeV') / sc.Unit('cm')
    assert list(c['temp'].values) == [300,301,302,303,304]
    for j in range(3):
        assert list(c[f'tags_{j}'].values) == [ i+j for i in range(5) ]
    assert list(c['big'].values) == [ 2**40+i for i in range(5) ]
    assert list(c['id'].values) == [ -i for i in range(5) ]
    assert list(c['p'].values) == [ 0.5*i for i in range(5) ]
    assert list(c['x'].values) == [ float(i) for i in range(5) ]
    print("Userdata OK")

def test_select_skip_limit():
    blocks = all_blocks(example_file)
    sel = 'pdgcode == neutron and ekin > 1keV'
    flt = mcpl.ParticleFilter(sel)
    selected = [ b[flt(b)] for b in blocks ]
    allsel = { k : concat(selected,k) for k in ('ekin','x') }
    nsel = len(allsel['ekin'])
    assert nsel > 10
    with mcpl.MCPLFile(example_file,blocklength=3) as f:
        for skip, limit in [ (0,0), (2,0), (2,5), (0,1), (nsel-1,0),
                             (nsel,0), (nsel+5,3) ]:
            da = f.to_scipp(pick=sel,skip=skip,limit=limit)
            end = nsel if not limit else min(nsel,skip+limit)
            assert np.array_equal(da.coords['ekin'].values,allsel['ekin'][skip:end]),(skip,limit)
            assert np.array_equal(da.coords['x'].values,allsel['x'][skip:end]),(skip,limit)
        #skip and limit without selection:
        n = f.nparticles
        allx = concat(blocks,'x')
        da = f.to_scipp(skip=n-4,limit=2)
        assert np.array_equal(da.coords['x'].values,allx[n-4:n-2])
    #Selection and edit given when opening the file are applied first:
    with mcpl.MCPLFile(example_file,pick='pdgcode == neutron',edit='x += 1m') as f:
        da = f.to_scipp()
        nb = all_blocks(example_file,pick='pdgcode == neutron',edit='x += 1m')
        assert np.array_equal(da.coords['x'].values,concat(nb,'x'))
        assert np.all(da.coords['pdgcode'].values == 2112)
    print("Selection, skip and limit OK")

def test_default_limit():
    #The default limit (lowered here) gives a warning when particles are left
    #out, an explicit limit does not:
    mcpldev._scipp._default_limit = 5
    try:
        for kwargs, expect_warning, n in [ ({},True,5), ({'limit':5},False,5),
                                            ({'limit':0},False,None) ]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                da = mcpl.MCPLFile(example_file).to_scipp(**kwargs)
            assert ( 'Only the first 5 particles' in out.getvalue() ) == expect_warning, out.getvalue()
            assert n is None or da.sizes['particle'] == n
        assert da.sizes['particle'] == mcpl.MCPLFile(example_file).nparticles
        #No warning if there are no more particles:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mcpl.MCPLFile(example_file).to_scipp(pick='x > 1e30cm')
        assert not out.getvalue()
    finally:
        mcpldev._scipp._default_limit = 100_000_000
    print("Default limit OK")

def test_coords():
    blocks = all_blocks(example_file)
    x, y = concat(blocks,'x'), concat(blocks,'y')
    da = mcpl.MCPLFile(example_file).to_scipp(
        coords = { 'r' : 'hypot(x,y)', 'ex' : 'ekin*x', 'cosz' : 'uz',
                   'isn' : 'pdgcode == neutron', 'r_mm' : 'hypot(x,y)/mm' },
        pick = 'pdgcode == neutron or pdgcode == gamma' )
    sel = np.isin(concat(blocks,'pdgcode'),(2112,22))
    assert da.coords['r'].unit == sc.Unit('cm')
    assert np.allclose(da.coords['r'].values,np.hypot(x,y)[sel])
    assert np.allclose(da.coords['r'].to(unit='m').values,0.01*np.hypot(x,y)[sel])
    assert da.coords['ex'].unit == sc.Unit('MeV')*sc.Unit('cm')
    assert da.coords['cosz'].unit == sc.units.dimensionless
    assert np.all(da.coords['isn'].values == (concat(blocks,'pdgcode')[sel] == 2112))
    assert da.coords['r_mm'].unit == sc.units.dimensionless
    assert np.allclose(da.coords['r_mm'].values,10*np.hypot(x,y)[sel])
    #Wavelengths (calculated in cm, but scipp converts them):
    wl = mcpl.MCPLFile(example_file).to_scipp( coords = { 'wl' : 'wavelength' },
                                               pick = 'pdgcode == neutron' )
    nb = all_blocks(example_file,pick='pdgcode == neutron')
    assert np.allclose(wl.coords['wl'].to(unit='angstrom').values,
                       np.concatenate([b.wavelength for b in nb]))
    print("Extra coordinates OK")

def test_errors():
    f = mcpl.MCPLFile(example_file)
    for kwargs in [ {'skip':-1}, {'limit':-1}, {'coords':'r'},
                    {'coords':{'':'x'}}, {'coords':{'r':'nosuchfield'}},
                    {'coords':{'x':'x'}}, {'pick':'x >'} ]:
        try:
            f.to_scipp(**kwargs)
        except mcpl.MCPLError as e:
            print(f"Expected error for {kwargs}: {e}")
        else:
            raise SystemExit(f'No error for {kwargs}')

def main():
    test_basic()
    test_options_of_file()
    test_userdata()
    test_select_skip_limit()
    test_default_limit()
    test_coords()
    test_errors()

if __name__ == '__main__':
    main()
