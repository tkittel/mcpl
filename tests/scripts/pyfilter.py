
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
              ('angle_to(0,0,1) < 30deg', np.degrees(np.arccos(np.clip(b.uz,-1,1))) < 30),
              #(the angle to -z is above 150 degrees when the angle to +z is below 30):
              ('angle_to(0,0,-2cm) > 150deg', np.degrees(np.arccos(np.clip(b.uz,-1,1))) < 30),
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
                'hypot(x,ekin) > 1cm', 'abs(y) > 1cm + 1',
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

def test_angle_to():
    #angle_to(x,y,z) is the angle between the direction and the vector (x,y,z),
    #precise also for small angles (unlike acos of a dot product):
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    v = mcpl.ParticleValue('angle_to(0,0,1)/deg')(b)
    assert np.allclose(v, np.degrees(np.arccos(np.clip(b.uz,-1,1))), rtol=0, atol=1e-9)
    #Angle to the position vector (with units, which must be the same):
    v = mcpl.ParticleValue('angle_to(x,y,z)')(b)
    #(compared with another formula which is precise for all angles):
    pos, d = np.stack((b.x,b.y,b.z),axis=1), b.direction
    ref = np.arctan2(np.linalg.norm(np.cross(pos,d),axis=1), np.sum(pos*d,axis=1))
    assert np.allclose(v, ref, rtol=0, atol=1e-12)
    print(f'angle_to(x,y,z)/deg of the first particles: {np.round(np.degrees(v[:3]),6)}')
    #Small angles, where acos(dot product) gives 0:
    from mcpldev._expressions import _angle_highres
    for eps in (1e-6, 1e-9, 1e-12):
        a = _angle_highres((np.array([1.0]),np.array([eps]),np.array([0.0])),(1.0,0.0,0.0))
        print(f'angle between (1,{eps:g},0) and (1,0,0): {a[0]:.6g}'
              f' (acos of dot product: {np.arccos(1/np.sqrt(1+eps**2)):.6g})')
        assert abs(a[0]-np.arctan(eps)) <= 1e-15*eps
    for bad in ( 'angle_to(0,0) > 0', 'angle_to(x,y,1) > 0', 'angle_to(0,0,0) > 1deg',
                 'angle_to(0,0,1cm) > 1cm' ):
        try:
            mcpl.ParticleFilter(bad)(b)
        except mcpl.MCPLError as e:
            print(f'{bad}: {e}')

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
    test_angle_to()
    test_exact_rotations()
    test_whitespace()
    test_expressions()
    test_nonfinite()
    test_examples()
    test_dump_and_stats()
