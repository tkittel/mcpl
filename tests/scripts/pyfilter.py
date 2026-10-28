
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

# Test selection and editing of particles with expressions in the Python API:
# ParticleFilter and ParticleEdit, dump_file and collect_stats with a
# selection, and the python examples using them.

import pathlib
import sys

import mcpldev as mcpl
import numpy as np
from mcpldev._physics import wavelength_from_ekin
from MCPLTestUtils.dirs import test_data_dir

example_file = test_data_dir.joinpath('example.mcpl')

def test_expressions():
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    #Wavelengths, NaN for particles other than neutrons and gammas:
    wl = wavelength_from_ekin(b.ekin,b.pdgcode)
    cases = [ ('ekin > 25keV and x <= 2cm + y and pdgcode != 22',
               (b.ekin>0.025)&(b.x<=2.0+b.y)&(b.pdgcode!=22)),
              ('pdgcode == neutron and ekin < 500keV', (b.pdgcode==2112)&(b.ekin<0.5)),
              ('mod(fileidx,10) == 0', np.mod(b.fileidx,10) == 0),
              ('fileidx >= 3 and pdgcode == gamma', (b.fileidx>=3)&(b.pdgcode==22)),
              ('not (pdgcode == gamma) or ekin > 1GeV', ~(b.pdgcode==22)|(b.ekin>1000)),
              ('0cm < x < 10mm and not(abs(y) >= 1cm)', (0<b.x)&(b.x<1.0)&~(np.abs(b.y)>=1)),
              ('sqrt(x**2+y**2) < 5cm', np.hypot(b.x,b.y)<5),
              ('sqrt(x^2+y^2) < 5cm', np.hypot(b.x,b.y)<5),
              ('hypot(x,y) < 0.05m', np.hypot(b.x,b.y)<5),
              ('hypot(x,y,z) < 25cm', np.sqrt(b.x**2+b.y**2+b.z**2)<25),
              #(a plain 0 has the units of the other values):
              ('hypot(0,x) < 2cm', np.abs(b.x)<2),
              ('max(0,x) > 1cm', b.x>1), ('clamp(0,x,y) < 0cm', np.clip(0,b.x,b.y)<0),
              ('x^2 + y^2 < 4cm^2', b.x**2+b.y**2 < 4),
              ('x^2 + y^2 < 400 mm^2', b.x**2+b.y**2 < 4),
              ('(pdgcode == neutron or pdgcode == gamma) and wavelength > 0.005Aa', wl > 0.005),
              ('(pdgcode == neutron or pdgcode == gamma) and wavelength > 0.0005nm', wl > 0.005),
              ('(pdgcode == neutron or pdgcode == gamma) and wavelength > 5e-13m', wl > 0.005),
              ('pdgcode == proton or (pdgcode == gamma and wavelength > 0.5Aa)', (wl > 0.5)|(b.pdgcode==2212)),
              ('pdgcode == neutron and wavelength > 0.005Aa', (b.pdgcode==2112)&(wl > 0.005)),
              ('pdgcode != neutron or wavelength > 0.005Aa', (b.pdgcode!=2112)|(wl > 0.005)),
              ('pdgcode == gamma and 0 < 2*wavelength < x', (b.pdgcode==22)&(wl*2e-8 < b.x)),
              ('uz > cos(10*pi/180)', b.uz > np.cos(np.radians(10))),
              ('acos(uz) < 10deg', np.arccos(b.uz) < np.radians(10)),
              ('time < 10us', b.time < 0.01),
              ('(userflags & 1) == 0 and weight == 1', np.ones(len(b),dtype=bool)),
              ('mod(userflags,4) == 0', np.mod(b.userflags,4) == 0),
              ('mod(abs(pdgcode),2) == 0', np.mod(np.abs(b.pdgcode),2) == 0),
              ('max(abs(x),abs(y)) < 3cm', np.maximum(np.abs(b.x),np.abs(b.y)) < 3),
              ('ekin/keV > 500', b.ekin/1e-3 > 500),
              ('abs(x) < 1cm + 2mm', np.abs(b.x) < 1.2),
              ('1 < 2', np.ones(len(b),dtype=bool)),
              ('x > 0 and y <= -0', (b.x>0)&(b.y<=0)),
              ('0 < x < 2cm', (b.x>0)&(b.x<2)),
              ('ekin > 0 and time > 0 or z == 0', ((b.ekin>0)&(b.time>0))|(b.z==0)),
              ('userflags & 0x10', (b.userflags & 0x10) != 0),
              ('(userflags & 0xff) != 0xff', (b.userflags & 0xff) != 0xff),
              ('pdgcode == -2111-1', b.pdgcode == -2112),
              ('atan2(uy,ux) > 90deg', np.arctan2(b.uy,b.ux) > np.pi/2),
              ('angle(dir,(0,0,1)) < 30deg', np.degrees(np.arccos(np.clip(b.uz,-1,1))) < 30),
              ('not (userflags & 1) and pdgcode != 0b0', ((b.userflags & 1) == 0)&(b.pdgcode!=0)),
              ('pdgcode == electron or pdgcode == positron', np.isin(b.pdgcode,(11,-11))),
              ('pdgcode == antielectron or pdgcode == photon', np.isin(b.pdgcode,(-11,22))),
              ('pdgcode == muon or pdgcode == antimuon or pdgcode == antiproton or pdgcode == antineutron',
               np.isin(b.pdgcode,(13,-13,-2212,-2112))) ]
    for expr, ref in cases:
        flt = mcpl.ParticleFilter(expr)
        sel = flt(b)
        print(f'{flt!r}: selects {np.sum(sel)}')
        assert sel.dtype == bool and np.array_equal(sel, ref), expr
    edit = mcpl.ParticleEdit('tmp = x; x = -y; y = tmp + 2cm; z *= 2; weight = weight*0.5; time += 1ms; pdgcode = neutron')
    r = edit(b)
    ok = ( np.allclose(r['x'],-b.y) and np.allclose(r['y'],b.x+2) and np.allclose(r['z'],2*b.z)
           and np.allclose(r['weight'],0.5*b.weight) and np.allclose(r['time'],b.time+1)
           and np.all(r['pdgcode']==2112) and r['pdgcode'].dtype.kind == 'i' )
    print(f'{edit!r}: fields {sorted(r)}, as expected: {ok}')
    assert ok
    n = b[b.pdgcode==2112]
    for ed, ref in ( ('wavelength = 1.8Aa', 1.8), ('wavelength = 0.18nm', 1.8),
                     ('wavelength = 1.8Aa + wavelength', 1.8+n.wavelength),
                     ('wavelength *= 2', 2*n.wavelength) ):
        r = mcpl.ParticleEdit(ed)(n)
        wl = wavelength_from_ekin(r['ekin'],n.pdgcode)
        print(f'ParticleEdit({ed!r}) as expected: {np.allclose(wl,ref)}')
        assert sorted(r) == ['ekin'] and np.allclose(wl,ref)
    r = mcpl.ParticleEdit('z = 0; x = -0; time = 0')(b)
    assert np.all(r['z']==0) and np.all(r['x']==0) and np.all(r['time']==0)
    #Statements are executed in order:
    for ed, checks in (
            ('x = -y; y = x', lambda r : np.allclose(r['x'],-b.y) and np.allclose(r['y'],-b.y)),
            ('x = 1cm; x += 1cm', lambda r : np.all(r['x']==2)),
            ('tmp = x; x = 2m; z = 2*tmp', lambda r : sorted(r) == ['x','z'] and np.allclose(r['z'],2*b.x)),
            ('a = ekin; ekin = 1MeV; ekin += a', lambda r : np.allclose(r['ekin'],1+b.ekin)),
            ('ekin *= 2; weight = ekin/MeV', lambda r : np.allclose(r['weight'],2*b.ekin)),
            ('swap(x,y)', lambda r : np.allclose(r['x'],b.y) and np.allclose(r['y'],b.x)),
            ('tmp = x; swap(tmp,y); x = tmp', lambda r : sorted(r) == ['x','y'] and np.allclose(r['x'],b.y)),
            ('rotate_z(90deg)', lambda r : ( sorted(r) == ['polx','poly','ux','uy','x','y']
                                             and np.allclose(r['x'],-b.y) and np.allclose(r['y'],b.x)
                                             and np.allclose(r['ux'],-b.uy) and np.allclose(r['uy'],b.ux) )),
            ('rotate_x(90deg)', lambda r : np.allclose(r['y'],-b.z) and np.allclose(r['z'],b.y)),
            ('rotate_y(90deg); x += 10cm', lambda r : np.allclose(r['x'],b.z+10) and np.allclose(r['z'],-b.x)),
            ('x += 10cm; rotate_y(pi/2)', lambda r : np.allclose(r['x'],b.z) and np.allclose(r['z'],-(b.x+10))),
            ('x = clamp(x, -1cm, 1cm); y = min(y, 1cm, 2mm); z = max(z, 0, 25cm)',
             lambda r : ( np.allclose(r['x'],np.clip(b.x,-1,1)) and np.allclose(r['y'],np.minimum(b.y,0.2))
                          and np.allclose(r['z'],np.maximum(b.z,25)) )) ):
        ok = checks(mcpl.ParticleEdit(ed)(b))
        print(f'ParticleEdit({ed!r}) as expected: {ok}')
        assert ok
    r = mcpl.ParticleEdit('wavelength = 1.8Aa; weight = wavelength/Aa; time = 0')(n)
    assert sorted(r) == ['ekin','time','weight'] and np.allclose(r['weight'],1.8)
    r = mcpl.ParticleEdit('ekin = 1MeV; wavelength = 2Aa')(n)
    assert np.allclose(wavelength_from_ekin(r['ekin']),2)
    r = mcpl.ParticleEdit('z += 1mm; time = time + 2us; ekin = 25meV')(b)
    assert np.allclose(r['z'],b.z+0.1) and np.allclose(r['time'],b.time+0.002) and np.allclose(r['ekin'],25e-9)
    r = mcpl.ParticleEdit('x = 2m*ux; y = uy*1m; ux = min(ux, 0.5); weight = 2')(b)
    assert ( np.allclose(r['x'], 200*b.ux) and np.allclose(r['y'], 100*b.uy)
             and np.allclose(r['ux'], np.minimum(b.ux,0.5)) and np.all(r['weight']==2) )
    for bad in ('wavelength > 1.8Aa', 'x > 0 and wavelength > 1.8Aa', 'pdgcode == proton or wavelength > 1Aa',
                'x < 2', 'x > 0.0001', 'x > 2 - 2', 'ekin > 0.025', 'wavelength > 1.8', 'x^2 + y^2 < 4',
                'x < 1meV', 'ekin > 2cm', 'sin(x) > 0', 'x^0.5 > 1cm', 'sqrt(x) < 2',
                'x + time > 0cm', 'ekin^x > 1', 'atan2(x, ekin) > 0', 'hypot(x) > 1cm',
                'hypot(x,ekin) > 1cm', 'abs(y) > 1cm + 1', 'hypot(0,x,ekin) > 1cm',
                'min(0,x,ekin) > 1cm', 'clamp(0,x,ekin) > 1cm',
                'wl > 1Aa', 'dirx > 0', 't < 1ms', 'is_neutron', 'neutron_wl > 1Aa',
                'degrees(acos(uz)) < 10',
                'ekin = 1MeV', 'ekin > 1MeV & x < 2cm', 'foo > 1',
                "__import__('os').system('ls')", 'ekin', 'lambda: 1',
                'sin(x, y=1) > 0', 'x.real > 0', '[x][0] > 0', "x > 'a'", '',
                'sqrt(x/cm) > 1', '1/(x/cm - x/cm) > 1', 'log(ekin/MeV - ekin/MeV) > 0',
                'mod(pdgcode,0) == 1', 'mod(x,2cm) > 0', 'mod(ekin/MeV,2) > 0',
                'mod(pdgcode,2.5) > 0', 'mod(pdgcode) > 0',
                'x > 0 && y > 0', 'x > 0 || y > 0', '!(x > 0)', 'x/cm % 2 > 1',
                'fileidx > 1cm', 'mod(fileidx,2.0) == 0', '1e999 > x/cm', '(-1)^(x/cm) > 0',
                'x != x and 1/(x/cm - x/cm) > 1', '~x > 0cm', '~uz > 0',
                'x > 0cm if ux > 0 else x < 0cm'):
        try:
            mcpl.ParticleFilter(bad)(b)
            print(f'ParticleFilter({bad!r}): no error')
        except mcpl.MCPLError as e:
            print(f'ParticleFilter({bad!r}): {e}')
    for bad in ('x = 2*ux', 'x = 2', 'ekin = 0.025', 'wavelength = 1.8', 'z += 1',
                'x = 1meV', 'wavelength = 1keV', 'time = 2*x', 'weight = 1cm',
                'x', 'foo = 1', 'wl = 1.8Aa', 'tmp = x; x = y', 'Tmp = 1', 'tmp += 1cm', 'x = tmp', 'clamp = 1',
                'swap(x,ekin)', 'swap(x)', 'swap(x,2)', 'rotate_z(1cm)', 'rotate_q(1)',
                'rotate_z(1,2)', 'x = clamp(x,1cm)', 'x = min(x)',
                'rotate_around((0,0,1))', 'rotate_around((0,0,0),10deg)', 'rotate_around((0,0,1),1cm)',
                'rotate_around((1cm,0,1),10deg)', 'rotate_around(0,0,1,10deg)', 'rotate_around((0,1),10deg)',
                'rotate_around(1,10deg)', 'rotate_frame((0,0,1),(0,1,0))',
                'rotate_x(90)', 'rotate_z(-45)', 'rotate_around((0,0,1),30)', 'rotate_x(090deg)',
                'rotate_frame(0,0,1,1,0,0,0,1,0,0,1,0)',
                'rotate_frame((0,0,1),(1,0,0),(0,0,2),(0,1,0))', 'rotate_frame((0,0,1),(1,0,0),(0,1,0),(1,1,0))',
                'pos = (1cm,2cm)', 'pos = 1cm', 'dir = (0,0,1cm)', 'x = pos', 'pos += 1cm',
                'pos = (0,0,1)', 'swap(pos,dir)', 'rotate_z(dir)', 'v = dir; swap(v,dir)',
                'x == 1cm', 'pi = 3', 'wl = 1Aa', 'x = 1cm, y = 1cm',
                'fileidx = 2', 'fileidx += 1', 'swap(fileidx,pdgcode)',
                'x = y = 1cm', 'x, y = y, x', '', 'pdgcode = 1.5',
                'x = sqrt(x/cm)*1cm', 'weight = 1/(x/cm - x/cm)'):
        try:
            mcpl.ParticleEdit(bad)(b)
            print(f'ParticleEdit({bad!r}): no error')
        except mcpl.MCPLError as e:
            print(f'ParticleEdit({bad!r}): {e}')

def test_nonfinite():
    #Errors instead of NaN or infinite values (for the particles which an
    #expression is used for):
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    n = b[b.pdgcode==2112]
    for bad in ('wavelength = 0', 'wavelength = -1Aa', 'wavelength = wavelength - wavelength'):
        try:
            mcpl.ParticleEdit(bad)(n)
            print(f'ParticleEdit({bad!r}) on neutrons: no error')
        except mcpl.MCPLError as e:
            print(f'ParticleEdit({bad!r}) on neutrons: {e}')
    with mcpl.MCPLOutFile('zero_ekin.mcpl') as o:
        o.add_particles( direction = (0,0,1), ekin = [0.0, 1e-6, 0.0],
                         pdgcode = [2112, 2112, 11] )
    with mcpl.MCPLFile('zero_ekin.mcpl') as f:
        z = f.read_block()
    for expr in ( 'pdgcode == neutron and wavelength > 1Aa',
                  'pdgcode == neutron and ekin > 0 and wavelength > 1Aa',
                  'ekin > 0 and 1/(ekin/MeV) > 1',
                  '1/(ekin/MeV) > 1' ):
        try:
            print(f'ParticleFilter({expr!r}) with zero ekin: selects'
                  f' {np.sum(mcpl.ParticleFilter(expr)(z))}')
        except mcpl.MCPLError as e:
            print(f'ParticleFilter({expr!r}) with zero ekin: {e}')

def run_example(name, *args):
    f = test_data_dir.joinpath('pyexamples',name)
    code = f.read_text().replace('\nimport mcpl\n','\nimport mcpldev as mcpl\n')
    assert 'import mcpldev as mcpl' in code
    sys.argv = [ str(f), *args ]
    exec(compile(code,str(f),'exec'),{'__name__':'__main__'})  # noqa: S102

def test_examples():
    run_example('pyexample_filtermcpl', str(example_file), 'filtered.mcpl')
    with mcpl.MCPLFile('filtered.mcpl') as f:
        b = f.read_block()
        print(f'pyexample_filtermcpl wrote {f.nparticles} particles with comments {f.comments}')
        assert np.all(b.pdgcode==2112) and np.all(b.ekin<0.1)
    run_example('pyexample_editmcpl', str(example_file))
    for fn in ('neutrons.mcpl','gammas.mcpl'):
        assert pathlib.Path(fn).is_file()

def test_dump_and_stats():
    mcpl.dump_file(example_file, header=False, limit=4, skip=1,
                   pick='pdgcode == gamma and ekin > 1MeV')
    mcpl.dump_stats(mcpl.collect_stats(example_file, pick='pdgcode == neutron and ekin < 1MeV',
                                       bin_data=False))
    s = mcpl.collect_stats(example_file, pick=mcpl.ParticleFilter('x > 1km'))
    print(f'stats for no selected particles: {s}')

def test_exact_rotations():
    #Rotations by multiples of 90 degrees must be exact, i.e. give the same
    #bits as swapping and negating the values (but without negative zeros):
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    b = b[:50]
    def bits(a):
        #(adding 0.0 to the reference values, to change -0.0 to 0.0)
        return np.ascontiguousarray(np.asarray(a,dtype=float)+0.0).view(np.uint64)
    x, y, ux, uy = b.x, b.y, b.ux, b.uy
    zero = np.zeros(len(b))
    for angle, (xx, yy) in ( ('90deg', (-y, x)), ('180deg', (-x, -y)),
                             ('270deg', (y, -x)), ('-90deg', (y, -x)),
                             ('450deg', (-y, x)), ('0deg', (x, y)),
                             ('pi/2', (-y, x)), ('-pi', (-x, -y)) ):
        r = mcpl.ParticleEdit(f'rotate_z({angle})')(b)
        assert np.array_equal(bits(r['x']), bits(xx)), angle
        assert np.array_equal(bits(r['y']), bits(yy)), angle
        print(f'rotate_z({angle}) is exact')
    #No negative zeros, for any angle:
    def raw_bits(a):
        return np.ascontiguousarray(a,dtype=float).view(np.uint64)
    for angle in ('90deg','180deg','270deg','-0deg','0deg','30deg','pi'):
        r = mcpl.ParticleEdit(f'x = 0cm; y = 0cm; rotate_z({angle})')(b)
        assert all( np.array_equal(raw_bits(r[k]),raw_bits(zero))
                    for k in ('x','y') ), angle
    print('rotations of zeros give 0.0 (not -0.0)')
    r = mcpl.ParticleEdit('rotate_x(90deg)')(b)
    assert np.array_equal(bits(r['y']), bits(-b.z))
    assert np.array_equal(bits(r['z']), bits(b.y))
    r = mcpl.ParticleEdit('rotate_y(-90deg)')(b)
    assert np.array_equal(bits(r['z']), bits(b.x))
    assert np.array_equal(bits(r['ux']), bits(-b.uz))
    #Angles differing per particle (exact only where they are multiples of
    #90 degrees):
    r = mcpl.ParticleEdit('rotate_z( (ux > 0) * 90deg + (ux <= 0) * 30deg )')(b)
    q = ux > 0
    assert np.array_equal(bits(r['ux'][q]), bits(-uy[q]))
    c, s = np.cos(np.pi/6), np.sin(np.pi/6)
    assert np.allclose(r['ux'][~q], c*ux[~q] - s*uy[~q])
    #Other angles use cos and sin:
    r = mcpl.ParticleEdit('rotate_z(45deg)')(b)
    c = np.cos(np.pi/4)
    assert np.allclose(r['x'], c*x - c*y) and np.allclose(r['y'], c*x + c*y)
    print('rotations with other angles use cos and sin')
    #rotate_around and rotate_frame (exact like rotate_x/y/z for the axes and
    #multiples of 90 degrees):
    for a, b2 in ( ('rotate_around((0,0,1),90deg)','rotate_z(90deg)'),
                   ('rotate_around((0,0,7),-90deg)','rotate_z(-90deg)'),
                   ('rotate_around((1,0,0),180deg)','rotate_x(180deg)'),
                   ('rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))','rotate_y(90deg)') ):
        ra, rb = mcpl.ParticleEdit(a)(b), mcpl.ParticleEdit(b2)(b)
        assert all( np.array_equal(raw_bits(ra[k]),raw_bits(rb.get(k,getattr(b,k)))) for k in ra ), a
        print(f'{a} is exactly {b2}')
    #(other axes and angles, as with the formula of Rodrigues):
    k = np.array([1.0,2.0,3.0]) / np.sqrt(14.0)
    t = np.radians(37.0)
    K = np.array([[0,-k[2],k[1]],[k[2],0,-k[0]],[-k[1],k[0],0]])
    R = np.eye(3) + np.sin(t) * K + ( 1 - np.cos(t) ) * K @ K
    r = mcpl.ParticleEdit('rotate_around((1,2,3),37deg)')(b)
    ref = np.stack([x,y,b.z],-1) @ R.T
    assert np.allclose(r['x'],ref[:,0]) and np.allclose(r['y'],ref[:,1]) and np.allclose(r['z'],ref[:,2])
    print('rotate_around((1,2,3),37deg) as with the formula of Rodrigues')
    #(rotate_frame turns v into vout and u into uout):
    frame = 'rotate_frame((0,0,1),(1,1,0),(0,1,0),(0,0,1))'
    for before, after in ( ('dir = (0,0,1)',(1/np.sqrt(2),1/np.sqrt(2),0)),
                           ('dir = (0,1,0)',(0,0,1)) ):
        r = mcpl.ParticleEdit(f'{before}; {frame}')(b)
        assert all( np.allclose(r[c],v) for c, v in zip(('ux','uy','uz'),after) ), before
    print(f'{frame} turns (0,0,1) into (1,1,0)/sqrt(2) and (0,1,0) into (0,0,1)')
    #(axes per particle: rotating around the direction keeps it):
    r = mcpl.ParticleEdit('rotate_around(dir,33deg)')(b)
    assert np.allclose(r['ux'],ux) and np.allclose(r['uy'],uy)
    print('rotate_around(dir,33deg) keeps the directions')
    #All rotations are proper rotations (never reflections), also when
    #rotate_frame is given the mirror image of a rotated pair of vectors, and
    #nearly parallel vectors give errors instead of NaN:
    from mcpldev._exprrotation import _rotation_matrix
    rng = np.random.default_rng(123)
    n = 10000
    q = _rotation_matrix('rotate_around',[ *rng.normal(size=(3,n)), rng.uniform(-10,10,n) ])
    v, u = rng.normal(size=(3,n)), rng.normal(size=(3,n))
    vo, uo = np.einsum('nij,jn->in',q,v), np.einsum('nij,jn->in',q,u)
    for name, args in ( ('rotate_around',[ *rng.normal(size=(3,n)), rng.uniform(-10,10,n) ]),
                        ('rotate_frame',[ *v, *vo, *u, *uo ]),
                        ('rotate_frame (mirrored vout and uout)',[ *v, -vo[0], *vo[1:], *u, -uo[0], *uo[1:] ]) ):
        m = _rotation_matrix(name.split()[0],args)
        ok = ( np.allclose(np.linalg.det(m),1.0)
               and np.allclose(m @ np.swapaxes(m,1,2),np.eye(3)) )
        print(f'{name}: {n} random rotations are proper rotations: {ok}')
    print('nearly parallel:',_rotation_matrix('rotate_frame',[0,0,1,0,0,1,1.01e-6,0,1,0,0,1]))

def test_whitespace():
    #Whitespace, including newlines, is normalised to single spaces:
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    flt = mcpl.ParticleFilter("""pdgcode == neutron
                                 and \tekin < 1MeV
                                 and hypot(x,y) < 10 cm  """)
    print(f'normalised selection: {flt.expression!r}')
    ref = mcpl.ParticleFilter('pdgcode == neutron and ekin < 1MeV and hypot(x,y) < 10cm')
    assert np.array_equal(flt(b), ref(b))
    edit = mcpl.ParticleEdit('z = 0cm;\n  wavelength = 1.8Aa\n')
    print(f'normalised edit: {edit.expression!r}')
    val = mcpl.ParticleValue('  ekin /\n eV ')
    print(f'normalised value: {val.expression!r}')
    assert np.allclose(val(b), b.ekin*1e6)
    for bad in ( 42, None ):
        try:
            mcpl.ParticleFilter(bad)
        except mcpl.MCPLError as e:
            print(f'ParticleFilter({bad!r}): {e}')

def test_vectors():
    #Vectors: pos, dir and pol, (a,b,c), their values (x is pos.x and
    #pos.at(0)), arithmetic, abs, v^2, dot, cross and angle:
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    pos, d = np.stack((b.x,b.y,b.z),axis=1), b.direction
    cases = [ ('pos.x/cm', b.x), ('pos.at(1)/cm', b.y), ('dir.z', b.uz), ('dir.at(2)', b.uz),
              ('pol.y', b.poly), ('abs(pos)/cm', np.linalg.norm(pos,axis=1)),
              ('pos^2/cm^2', np.sum(pos*pos,axis=1)),
              ('abs(pos-(0,0,1m))/cm', np.linalg.norm(pos-[0,0,100],axis=1)),
              ('dot(pos,dir)/cm', np.sum(pos*d,axis=1)),
              ('cross(pos,dir).at(2)/cm', np.cross(pos,d)[:,2]),
              ('abs((x,y))/cm', np.hypot(b.x,b.y)), ('(-pos/2+pos*2).z/cm', 1.5*b.z),
              ('dot((1,2),(3,4))', 11.0), ('(2*dir).y', 2*b.uy), ('(dir*2).y', 2*b.uy),
              ('angle(dir,(0,0,1))/deg', np.degrees(np.arccos(np.clip(b.uz,-1,1)))),
              ('angle(dir,(0,0,-2cm))/deg', 180-np.degrees(np.arccos(np.clip(b.uz,-1,1)))),
              ('angle((1,0),(0,1))/deg', 90.0) ]
    for expr, ref in cases:
        v = mcpl.ParticleValue(expr)(b)
        assert np.allclose(v, ref, rtol=1e-12, atol=1e-9), expr
        print(f'{expr} as with numpy')
    #Angle to the position vector (with units, which must be the same):
    v = mcpl.ParticleValue('angle(pos,dir)')(b)
    #(compared with another formula which is precise for all angles):
    ref = np.arctan2(np.linalg.norm(np.cross(pos,d),axis=1), np.sum(pos*d,axis=1))
    assert np.allclose(v, ref, rtol=0, atol=1e-12)
    print(f'angle(pos,dir)/deg of the first particles: {np.round(np.degrees(v[:3]),6)}')
    #Small angles, where acos(dot product) gives 0:
    from mcpldev._exprcore import _angle_highres
    for eps in (1e-6, 1e-9, 1e-12):
        a = _angle_highres((np.array([1.0]),np.array([eps]),np.array([0.0])),(1.0,0.0,0.0))
        print(f'angle between (1,{eps:g},0) and (1,0,0): {a[0]:.6g}'
              f' (acos of dot product: {np.arccos(1/np.sqrt(1+eps**2)):.6g})')
        assert abs(a[0]-np.arctan(eps)) <= 1e-15*eps
    a = mcpl.ParticleValue('angle((1,1e-9,0),(1,0,0))')(b)
    assert np.all( np.abs(a-1e-9) <= 1e-24 )
    #Picks and edits with vectors (and vector variables):
    for pick, ref in ( ('d = pos - (0,0,1m); abs(d) < 100.5cm', np.linalg.norm(pos-[0,0,100],axis=1) < 100.5),
                       ('angle(dir,(0,0,1)) < 30deg', np.degrees(np.arccos(np.clip(b.uz,-1,1))) < 30) ):
        assert np.array_equal(mcpl.ParticleFilter(pick)(b),ref), pick
        print(f'pick {pick!r} as with numpy')
    for edit, ref in ( ('pos += (0,0,1m)', {'x': b.x, 'y': b.y, 'z': b.z+100}),
                       ('pos += 50cm*dir', {'x': b.x+50*b.ux, 'y': b.y+50*b.uy, 'z': b.z+50*b.uz}),
                       ('x += 1cm; pos = pos/2', {'x': (b.x+1)/2, 'y': b.y/2, 'z': b.z/2}),
                       ('dir = -dir', {'ux': -b.ux, 'uy': -b.uy, 'uz': -b.uz}),
                       ('v = cross(dir,(0,0,1)); x = v.x*1cm', {'x': b.uy}),
                       ('pol = (0,0,1)', {'polx': 0.0, 'poly': 0.0, 'polz': 1.0}) ):
        r = mcpl.ParticleEdit(edit)(b)
        assert sorted(r) == sorted(ref) and all( np.allclose(r[k],ref[k]) for k in ref ), edit
        print(f'edit {edit!r} changes {sorted(r)} as with numpy')
    #Errors (vectors are not values, their values have the same units, and
    #angle_to was replaced by angle):
    for bad in ( 'pos < 1cm', 'pos + 1cm', '(x,ux) == 0', 'pos.at(3) > 0', 'pos.w > 0',
                 'cross((1,0),(0,1)).x > 0', 'dir.x.y > 0', 'sin(dir) > 0', 'pos and 1',
                 'not dir', 'angle(pos) > 0', 'angle(pos,(1,0)) > 0', 'dot(pos,1cm) > 0',
                 '(pos,pos) == 0', 'dir*dir > 0', 'dir^3 > 0', '(1,2,3,4) == 0', 'x.at(0) > 0',
                 'pos.at(x) > 0', 'angle_to(0,0,1) < 1deg', 'pos' ):
        try:
            mcpl.ParticleFilter(bad)(b)
            print(f'{bad}: no error')
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')
    try:
        mcpl.ParticleValue('dir')(b)
    except mcpl.MCPLError as e:
        print(f'ParticleValue of a vector: {e}')

def test_canonical():
    #Normalised forms of expressions (from their parsed forms), which must be
    #valid expressions giving the same values, and their own normalised forms:
    from mcpldev._expressions import _expr_canonical
    from mcpldev._histstring import _hist_key
    with mcpl.MCPLFile(example_file) as f:
        b = next(iter(f.particle_blocks))
    for e in ( 'ekin/MeV', '(ekin) / MeV', '(x**2+y^2)/cm^2', '2.5e-3MeV*ekin/MeV^2',
               '-(x/cm)^2', '2^-1*x/cm', '(-2)^2*ux', 'ekin/(2*MeV)', '1e30*ekin/MeV',
               'angle( dir, ( 0, 0, 1 ) )/deg', '( pos - ( 0, 0, 1m ) ).at( 2 )/cm' ):
        k = _expr_canonical(e)
        same = np.allclose(mcpl.ParticleValue(e)(b),mcpl.ParticleValue(k)(b),equal_nan=True)
        print(f'value {e!r}: {k!r}')
        assert same and _expr_canonical(k) == k
    #Units are values (MeV is 1MeV), a number or closing parenthesis directly
    #before a unit multiplies it (binding less tightly than ^ and more tightly
    #than * and /), and a power directly after a unit applies to the unit:
    for a, c in ( ( '2^(ekin/TeV)MeV/MeV', '(2^(ekin/TeV))*(1*MeV)/MeV' ), ( 'ekin/2MeV', 'ekin/(2*MeV)' ),
                  ( '-2MeV/MeV', '-(2*MeV)/MeV' ), ( '2cm^-1*x', '2*(cm^-1)*x' ), ( '2cm^(-1)*x', '2*(cm^-1)*x' ),
                  ( 'sqrt(ekin)/sqrt(eV)', 'sqrt(ekin/eV)' ), ( 'abs(x)^1.5/cm^1.5', '(abs(x)/cm)^1.5' ),
                  ( 'cm^(1/2)*cm^0.5/cm', '1' ), ( '2^3MeV/MeV', '8' ), ( '(x)cm/cm^2', 'x/cm' ) ):
        same = np.allclose(mcpl.ParticleValue(a)(b),mcpl.ParticleValue(c)(b))
        print(f'{a!r} is {c!r}: {same}, normalised {_expr_canonical(a)!r}')
        assert same
    for bad in ( 'cm^0.25 > 1', 'ekin^0.25 > 1', 'sqrt(sqrt(ekin)) > 1', '2cm^x > 1', 'x cm > 1', 'cm^2MeV > 1' ):
        try:
            mcpl.ParticleFilter(bad)
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')
    #Syntax errors say where the problem is (also in edits, in the whole edit):
    for bad in ( 'x > 1cm and', 'x > > 1cm', '(x > 1cm', 'ekin < 1MeV)', 'sqrt(x',
                 'x > 1cm and and y < 1cm', 'f(1,)', 'not', 'x ? 1',
                 'hypot(x,y) > 3cm or (ekin < 25meV and pdgcode == neutron and time >' ):
        try:
            mcpl.ParticleFilter(bad)
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')
    for bad in ( 'z += 1cm; x = ', 'x = 2cm;  y + ;z=1cm', 'rotate_x(90deg;x=1cm' ):
        try:
            mcpl.ParticleEdit(bad)
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')
    for e in ( 'pdgcode==neutron and (ekin<1MeV)', 'not (x > 1cm) or y<0',
               '(x>0 or y>0) and z>0', 'ekin < 4cm^2*1MeV/cm^2' ):
        k = _expr_canonical(e)
        print(f'pick {e!r}: {k!r}')
        assert ( mcpl.ParticleFilter(e)(b) == mcpl.ParticleFilter(k)(b) ).all()
        assert _expr_canonical(k) == k
    for e in ( 'z += 1cm;weight *= 0.5', 'rotate_z(90deg) ; z+=10 cm' ):
        print(f'edit {e!r}: {_expr_canonical(e,edit=True)!r}')
    #The parsed expressions, with what they use:
    from mcpldev._exprcore import _Expr
    for e in ( 'pdgcode == neutron and wavelength > 1.8Aa', 'hypot(x,y)/cm', 'mod(fileidx,10) == 0' ):
        x = _Expr(e)
        print(f'parsed {e!r}: fields {sorted(x.fields)}, names {sorted(x.names)},'
              f' canonical {x.canonical!r}')
    #Random expressions (from a grammar of values and conditions), whose
    #normalised forms must give exactly the same values:
    import random
    rng = random.Random(12345)
    plain = [ 'ux', 'uz', '(x/cm)', '(ekin/MeV)', 'weight', '2', '3.5', '1e3', '(4cm^2/cm^2)', '(25meV/eV)',
              '(x/2cm)', '(2cm^(-1)*x)', '(sqrt(ekin)/sqrt(eV))', '(2^(ux)MeV/MeV)', '(sqrt(2)cm/cm)', '(-2meV/eV)' ]
    def val( d ):
        if d <= 0 or rng.random() < 0.25:
            return rng.choice(plain)
        k = rng.random()
        if k < 0.45:
            return val(d-1) + rng.choice(['+','-','*','/']) + val(d-1)
        if k < 0.6:
            return rng.choice(['-','+']) + val(d-1)
        if k < 0.75:
            return f'({val(d-1)})^' + rng.choice(['2','-1','0.5','(1/2)'])
        if k < 0.85:
            return rng.choice(['abs','cos','atan2','hypot','max']) + f'({val(d-1)},{val(d-1)})'
        return f'({val(d-1)})'
    def cond( d ):
        k = rng.random()
        if d <= 0 or k < 0.4:
            return val(2) + rng.choice(['<','>=','==','!=']) + val(2)
        if k < 0.7:
            return cond(d-1) + rng.choice([' and ',' or ']) + cond(d-1)
        if k < 0.85:
            return 'not ' + cond(d-1)
        return f'({cond(d-1)})'
    nok = nchecked = 0
    for e in [ val(4) for _ in range(300) ] + [ cond(3) for _ in range(300) ]:
        cls = mcpl.ParticleFilter if any( c in e for c in '<>=' ) else mcpl.ParticleValue
        try:
            orig = cls(e)(b)
        except mcpl.MCPLError:
            continue#(e.g. wrong numbers of arguments, or NaN values)
        k = _expr_canonical(e)
        nchecked += 1
        nok += ( np.array_equal(orig,cls(k)(b),equal_nan=True) and _expr_canonical(k) == k )
    print(f'random expressions: {nok} of {nchecked} valid ones have equivalent normalised forms')
    assert nok == nchecked
    for bad in ( 'exp(2,3)', 'cos(ux,2)' ):
        try:
            mcpl.ParticleValue(bad)
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')
    for h in ( 'ekin/MeV;logx=1;bins=50', 'ekin / MeV ; bins=50 ;logx=1', '(ekin)/MeV;bins=50;logx=1',
               'x/cm : y/cm;xrange=-1:1', 'x/cm:y/cm;xrange=-1.0:1', 'ekin/MeV;display_by=pdgcode==22',
               'ekin;logy', 'ekin;logy=1', 'ekin;logy=0', 'pdgcode;bar', 'pdgcode;bar=auto',
               'x;lethargy;unweighted', 'x;bins', 'x;display_by',
               'x;display_by=single', 'x : y;display_by=1' ):
        try:
            print(f'histogram {h!r}: {_hist_key(h)!r}')
        except mcpl.MCPLError as e:
            print(f'histogram {h!r}: {e}')

def test_in_and_userdata():
    #Comparisons with "in" and "not in" a list of values:
    from mcpldev._expressions import _expr_canonical
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    p = b.pdgcode
    for e, ref in ( ( 'pdgcode in (neutron,gamma)', np.isin(p,[2112,22]) ),
                    ( 'pdgcode not in ( neutron, gamma )', ~np.isin(p,[2112,22]) ),
                    ( 'abs(pdgcode) in (11)', np.abs(p) == 11 ),
                    ( 'not ekin in (1MeV,2MeV) and pdgcode in (22,2112)',
                      ~np.isin(b.ekin,[1,2]) & np.isin(p,[22,2112]) ) ):
        k = _expr_canonical(e)
        ok = ( np.array_equal(mcpl.ParticleFilter(e)(b),ref)
               and np.array_equal(mcpl.ParticleFilter(k)(b),ref) and _expr_canonical(k) == k )
        print(f'{e!r}: {int(ref.sum())} particles, normalised {k!r}, as expected: {ok}')
        assert ok
    #PDG codes are not conditions (they would be true for all particles), but
    #other integers are (as bits of userflags):
    for e in ( 'neutron', 'pdgcode', 'neutron or gamma', 'x > 0cm and not antineutron',
               'abs(pdgcode)', 'userflags & 0x10', 'not userflags' ):
        try:
            mcpl.ParticleFilter(e)
            print(f'{e!r}: a condition')
        except mcpl.MCPLError as x:
            print(f'{e!r}: {x}')
    #(abs of integers gives integers):
    print('abs(pdgcode):', mcpl.ParticleValue('abs(pdgcode)')(b).dtype.kind)
    for bad in ( 'pdgcode in neutron', 'pdgcode in ()', 'pdgcode in (1cm)', '0 < pdgcode in (1,2)',
                 'pdgcode in (1,2) < 3' ):
        try:
            mcpl.ParticleFilter(bad)
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')
    #Fields of the userdata, as userdata.NAME, and values of arrays as
    #userdata.NAME.at(INDEX) (counting from 0):
    fn = 'ud_expressions.mcpl'
    with mcpl.MCPLOutFile(fn,userdata_layout='nscat:uint8,temp:float32,dir:float32[3]') as o:
        o.add_particles( x = [1.0,2.0,3.0,4.0], uz = 1.0, ekin = 1.0, pdgcode = 2112, weight = 1.0,
                         userdata = { 'nscat' : [0,1,2,3], 'temp' : [10.0,20.0,30.0,40.0],
                                      'dir' : [[0,0,1],[0,1,0],[1,0,0],[0.6,0.8,0]] } )
    with mcpl.MCPLFile(fn) as f:
        u = f.read_block()
        for e in ( 'userdata.nscat >= 2', 'userdata.temp < 25 or userdata.nscat == 3',
                   'userdata.nscat in (0,3)', 'userdata.dir.at(0) > 0.5', 'userdata.dir.at( 2 ) == 1',
                   'hypot(userdata.dir.at(0),userdata.dir.at(1)) > 0.9' ):
            print(f'{e!r}: {mcpl.ParticleFilter(e)(u).tolist()}, normalised {_expr_canonical(e)!r}')
        print('value userdata.temp*2:', mcpl.ParticleValue('userdata.temp*2')(u).tolist())
        print('value userdata.dir.at(1):', mcpl.ParticleValue('userdata.dir.at(1)')(u).tolist())
        for bad in ( 'userdata.nope > 1', 'userdata.dir > 1', 'userdata.dir.at(3) > 0',
                     'userdata.nscat.at(0) > 0', 'userdata.dir.at(x) > 0', 'userdata.dir.at(1.5) > 0',
                     'userdata.dir.get(1) > 0', 'x.y > 1', 'userdata > 1', 'userdata. > 1' ):
            try:
                mcpl.ParticleFilter(bad)(u)
            except mcpl.MCPLError as e:
                print(f'{bad}: {e}')
    with mcpl.MCPLFile(fn,edit='x = userdata.temp*1cm;y = userdata.dir.at(1)*1m') as f:
        b2 = f.read_block()
    print('edited with userdata values:', b2.x.tolist(), b2.y.tolist())
    for bad in ( 'userdata.nscat += 1', 'userdata.dir.at(1) = 2' ):
        try:
            mcpl.ParticleEdit(bad)
        except mcpl.MCPLError as e:
            print(f'changing userdata: {e}')
    try:
        mcpl.ParticleFilter('userdata.nscat > 1')(b)
    except mcpl.MCPLError as e:
        print(f'without userdata: {e}')
    h = mcpl.histogram(fn,'userdata.nscat;bar')
    print('bar chart of userdata.nscat:', type(h).__name__)
    pathlib.Path(fn).unlink()

def test_pick_statements():
    from mcpldev._expressions import _expr_canonical
    #Picks can have statements assigning variables before their condition (the
    #same statements as in edits), giving the same as without them:
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    for pick, inline in (
            ( 'r = hypot(x,y); r > 2cm and r < 5cm', 'hypot(x,y) > 2cm and hypot(x,y) < 5cm' ),
            ( 'e = ekin/MeV; e2 = e*e; e2 > 0.25', '(ekin/MeV)^2 > 0.25' ),
            ( 'd = x - 1cm; d *= 2; abs(d) < 3cm', 'abs(2*(x - 1cm)) < 3cm' ),
            ( 'n = pdgcode == neutron; n and ekin < 1MeV', 'pdgcode == neutron and ekin < 1MeV' ),
            ( 't = time; mod(fileidx,2) == 0 and t > 0ms', 'mod(fileidx,2) == 0 and time > 0ms' ),
            ( 'pdgcode == neutron;', 'pdgcode == neutron' ),
            ( ' r = hypot(x, y) ;\n  r < 1cm ', 'hypot(x,y) < 1cm' ) ):
        flt, ref = mcpl.ParticleFilter(pick), mcpl.ParticleFilter(inline)
        same = np.array_equal(flt(b),ref(b))
        print(f'pick {flt.expression!r}: same as {inline!r}: {same} ({int(flt(b).sum())} picked),'
              f' fileidx: {flt._uses_fileidx}, canonical: {_expr_canonical(pick)!r}')
        assert same
    #(the same in files, histograms and the C/C++ code, which leaves it to the users):
    pick = 'r = hypot(x,y); r > 2cm'
    with mcpl.MCPLFile(example_file,pick = pick) as f:
        n = sum( len(blk) for blk in f.particle_blocks )
    h = mcpl.histogram(str(example_file),'x;bins=5;display_by=single',pick = pick)
    from mcpldev._viewer_code import _c_condition, _CTranslator
    print(f'file and histogram with {pick!r}: {n} {int(sum(h.contents[None]))},'
          f' C condition: {_c_condition(pick,_CTranslator("c","p","c"))}')
    for bad in ( 'x = 1cm; x > 0cm', 'r = hypot(x,y); x > 0cm', 'swap(x,y); x > 0cm',
                 'rotate_z(90deg); x > 0cm', 'x > 0cm; y > 0cm', 'r = hypot(x,y);',
                 'r = hypot(x,y); r', 'r += 1cm; r > 0cm', 'r = 1meV; r > 1cm', 'pi = 3; x > 0cm',
                 'r = hypot(x,y), r > 1cm', ';', 'ekin = 1MeV' ):
        try:
            mcpl.ParticleFilter(bad)(b)
            print(f'ParticleFilter({bad!r}): no error')
        except mcpl.MCPLError as e:
            print(f'ParticleFilter({bad!r}): {e}')

def test_help_examples():
    #The examples of the help texts (and the viewers) are valid, and work on
    #files (with the userdata fields of the examples):
    from mcpldev._exprhelp import example_rows
    fn = 'help_examples.mcpl'
    with ( mcpl.MCPLOutFile(fn,userdata_layout='nscat:uint8,origdir:float32[3]') as o,
           mcpl.MCPLFile(example_file) as f ):
        b = f.read_block()
        o.add_particles(b,userdata={ 'nscat' : np.arange(len(b)) % 4,
                                     'origdir' : np.tile([0.0,0.0,1.0],(len(b),1)) })
    with mcpl.MCPLFile(fn) as f:
        b = f.read_block()
        for expr, _ in example_rows('pick'):
            print(f'pick example {expr!r}: {int(mcpl.ParticleFilter(expr)(b).sum())} particles')
        #(for neutrons, which have wavelengths):
        neutrons = b[b.pdgcode == 2112]
        for expr, _ in example_rows('edit'):
            mcpl.ParticleEdit(expr)(neutrons)
            print(f'edit example {expr!r}: ok')
    for expr, _ in example_rows('hist'):
        h = mcpl.histogram(fn,expr)
        print(f'histogram example {expr!r}: {type(h).__name__}')
    pathlib.Path(fn).unlink()

def test_integers():
    #Integers work essentially as in C, but results which do not fit in their
    #type (like in C) are errors instead of wrapping around, and so are
    #unsigned integers combined with negative values. The operator / divides as
    #floating point numbers, and // divides non-negative integers:
    print('Integers:')
    with mcpl.MCPLOutFile('ints.mcpl', opt_userflags = True) as o:
        o.add_particles( ekin = 1.0, uz = 1.0, weight = 1.0,
                         pdgcode = [2112,2212,-2212],
                         userflags = [0,1,0xFFFFFFFF] )
    with mcpl.MCPLFile('ints.mcpl') as f:
        b = f.read_block()
    for e in ( 'userflags > 0', 'userflags & 0x80000000', '(userflags & 0xff) == 0xff',
               'userflags | 0x10 == 0x11', 'userflags + 1 > 1',
               'userflags * 2 > 1', 'userflags/2 == 0.5', '7/2 == 3.5', '1/2 == 0.5',
               'userflags//2 == 0', 'abs(pdgcode)//1000 == 2', '7//2 == 3',
               'pdgcode/1000 < -2', 'pdgcode * 1000000 > 0',
               'mod(abs(pdgcode),2) == 0', 'abs(pdgcode) == 2212', '-pdgcode < 0',
               'min(pdgcode,0) < 0', 'clamp(pdgcode,0,2200) == 2200',
               'userflags == 4294967295', 'pdgcode/1000.0 < 0',
               '2^31 > 2147483647', 'pdgcode == -2147483648 + 2147481436',
               '-(pdgcode > 0) == -1', '-(1 > 0) * 2 == -2',
               #Errors:
               'userflags - 1 > 0', 'userflags + 4294967295 > 0',
               'pdgcode * 1000000000 > 0', 'userflags > -1', 'userflags & -1',
               'userflags / 0 > 0', 'userflags // 0 > 0', 'pdgcode // 1000 == 2',
               '7 // -2 == -3', 'x // cm > 0', '7.0 // 2 == 3', 'mod(pdgcode,3) == 1', 'mod(userflags,0) == 0',
               '-userflags < 0', 'userflags & 2^3', '(x > 0) & (y > 0)',
               '~userflags == 0',
               '18446744073709551616 > 0' ):
        try:
            print(f'  {e}: {mcpl.ParticleFilter(e)(b).tolist()}')
        except mcpl.MCPLError as err:
            print(f'  {e}: MCPLError: {err}')
    #Errors only for the particles in use:
    print('  userflags > 0 and userflags - 1 == 0:',
          mcpl.ParticleFilter('userflags > 0 and userflags - 1 == 0')(b).tolist())
    #Values assigned to pdgcode and userflags must fit:
    for e in ( 'userflags = userflags + 1', 'userflags = userflags / 2',
               'userflags = userflags // 2',
               'pdgcode = pdgcode * 1.0', 'pdgcode = 2.5',
               'pdgcode = 4294967295', 'swap(pdgcode,userflags)' ):
        try:
            res = mcpl.ParticleEdit(e)(b)
            print(f'  edit {e}: { {k:v.tolist() for k,v in res.items()} }')
        except mcpl.MCPLError as err:
            print(f'  edit {e}: MCPLError: {err}')

if __name__ == '__main__':
    test_integers()
    test_pick_statements()
    test_help_examples()
    test_in_and_userdata()
    test_canonical()
    test_vectors()
    test_exact_rotations()
    test_whitespace()
    test_expressions()
    test_nonfinite()
    test_examples()
    test_dump_and_stats()
