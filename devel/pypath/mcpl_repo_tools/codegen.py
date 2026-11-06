
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

"""Test of the C and C++ code generated for picks and edits (see
mcpl._expr_ast2c and mcpl._expr_ast2cpp): MCPL is built and installed with
CMake, the generated programs are built with CMake against it, and run on
reference files, and their output files must have the same particles as
those of mcpltool --extract with the same picks and edits (or both must
fail)."""

import os
import pathlib
import random
import subprocess
import sys

from .dirs import pyroot, testroot

#The reference files:
_files = { 'misc' : testroot / 'data/ref/miscphys.mcpl.gz',
           'udscalars' : testroot / 'data/reffmt4/reffile_ud_scalars.mcpl',
           'udarrays' : testroot / 'data/reffmt4/reffile_ud_arrays.mcpl.gz' }

#The picks and edits (file, pick, edit), with all kinds of expressions:
_cases = [
    ( 'misc', 'pdgcode == neutron', None ),
    ( 'misc', 'pdgcode in (neutron,gamma) and ekin > 5keV', None ),
    ( 'misc', 'pdgcode not in (11,-11) or ekin < 25meV', None ),
    ( 'misc', 'ekin < 25meV or abs(x) > 2cm', None ),
    ( 'misc', 'mod(fileidx,3) == 0', None ),
    ( 'misc', 'r = hypot(x,y); r < 5cm', None ),
    ( 'misc', 'd = pos - (0,0,1m); abs(d) < 1.2m and d.z < 0cm', None ),
    ( 'misc', 'angle(dir,(0,0,1)) < 30deg', None ),
    ( 'misc', 'angle((x,y),(1,1)) < 1rad', None ),
    ( 'misc', 'through_sphere((0,0,1m),20cm)', None ),
    ( 'misc', 'pdgcode == neutron and wavelength > 1Aa', None ),
    ( 'misc', 'userflags & 0x1 == 0 and userflags | 2 > 0', None ),
    ( 'misc', '-pdgcode < 0 and abs(pdgcode) in (11,22)', None ),
    ( 'misc', 'dot(pos,dir) > -1cm and cross(pos,dir).z > 0cm', None ),
    ( 'misc', 'round(x/mm) > 3 or floor(ekin/MeV) == 2 or ceil(time/ms) == 1', None ),
    ( 'misc', 'max(abs(x),abs(y)) < 30cm and min(x,y,z) > -10cm and clamp(ux,0,0.5) < 0.5', None ),
    ( 'misc', 'sqrt(ekin/MeV) > 0.5 and exp(-ux) > 1 and log10(ekin/eV) > 3 and atan2(uy,ux) > 0', None ),
    ( 'misc', 'pdgcode//1000 + 0 == 2 or 7 // 2 == 3', None ),
    ( 'misc', 'pos^2 < 1m^2 and (x/cm)^2 < 100', None ),
    ( 'misc', '0cm < z < 1m and not x > 0cm', None ),
    ( 'misc', 'pdgcode * 1000000000 > 0', None ),
    ( 'misc', 'userflags - 1 > 0', None ),
    ( 'misc', 'x/(x-x) > 0', None ),
    ( 'misc', 'wavelength > 0Aa', None ),
    ( 'misc', None, 'x += 1cm; weight *= 0.5' ),
    ( 'misc', 'pdgcode == gamma', 'ekin = 2*ekin; pdgcode = neutron' ),
    ( 'misc', None, 'rotate_z(90deg)' ),
    ( 'misc', None, 'rotate_y(30deg); z -= 1mm' ),
    ( 'misc', None, 'rotate_x(-45deg); rotate_z(180deg)' ),
    ( 'misc', None, 'rotate_around((1,1,0),30deg)' ),
    ( 'misc', None, 'rotate_around(dir,90deg)' ),
    ( 'misc', None, 'rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))' ),
    ( 'misc', 'pdgcode in (neutron,gamma)', 'wavelength = 1.8Aa' ),
    ( 'misc', None, 'pos += (0,0,1m); dir = (0,0,1)' ),
    ( 'misc', None, 'pos = 2*pos - (1cm,1cm,1cm)' ),
    ( 'misc', None, 'tmp = x; x = y; y = tmp' ),
    ( 'misc', None, 'swap(x,y); swap(polx,polz)' ),
    ( 'misc', None, 'userflags = userflags | 0x10; pdgcode = -pdgcode' ),
    ( 'misc', None, 'userflags = mod(fileidx,7); time += hypot(x,y,z)/(2200m/s)' ),
    ( 'misc', None, 'ekin = max(ekin,1keV); weight = clamp(weight,0.2,0.8)' ),
    ( 'misc', None, 'x = round(x/mm)*1mm; z = floor(z/cm)*1cm + ceil(ux)*1mm' ),
    ( 'misc', None, 'pdgcode = pdgcode*2' ),
    ( 'misc', None, 'pdgcode = 2.5' ),
    ( 'misc', None, 'wavelength = 1Aa' ),
    ( 'udscalars', 'userdata.i8 + userdata.u8 > 0 and userdata.i64 - 1 < userdata.i32', None ),
    ( 'udscalars', 'userdata.temp > 300K and userdata.len < 1m', None ),
    ( 'udscalars', 'userdata.ang < 45deg', 'ekin = userdata.e; time = userdata.t' ),
    ( 'udscalars', 'userdata.u64 + 1 > 5', None ),
    ( 'udscalars', 'userdata.u32 < 7 and userdata.flux > 0cm^-2*MeV', None ),
    ( 'udarrays', 'userdata.ids.at(1) > -5 and userdata.tags.at(4) < 200', None ),
    ( 'udarrays', 'userdata.origin.at(2) > 0cm', 'x = userdata.origin.at(0)' ),
    ( 'udarrays', None, 'time = userdata.dirs.at(1)*1ms; userflags = userdata.flag' ),
    #(files with universal values, which edits can not change):
    ( 'udarrays', None, 'weight = userdata.dirs.at(1)' ),
    ( 'universal', None, 'weight = 0.5; pdgcode = neutron; x += 1cm' ),
    ( 'universal', None, 'weight *= 2' ),
    ( 'universal', None, 'pdgcode = gamma' ),
    ( 'universal', 'ekin > 1keV', 'swap(x,y)' ),
    #(ranges of particles, as given by mcpltool -s and -l):
    ( 'misc', 'mod(fileidx,3) == 0', None, 10, 50 ),
    ( 'misc', None, 'x = fileidx*1cm', 150, None ),
    ( 'misc', 'pdgcode == gamma', 'weight *= 2', 0, 7 ),
    ( 'udarrays', 'userdata.flag > 0', None, 3, 5 ),
]

def _option_arg( text ):
    """The pick or edit as the argument of -p or -E, with its first expression
    in parentheses if it starts with "-", which would else be taken as an
    option (as in the commands which mcpltool generates)"""
    if not text.startswith('-'):
        return text
    first, sep, rest = text.partition(';')
    return f'({first})' + sep + rest

def _write_universal( fn ):
    """A file with the neutrons of miscphys, with universal pdgcode and weight"""
    sys.path.insert(0,str(pyroot/'src'))
    import mcpl
    with ( mcpl.MCPLFile(_files['misc'],pick = 'pdgcode == neutron') as f,
           mcpl.MCPLOutFile(fn,opt_universalpdgcode = 2112,opt_universalweight = 0.5) as o ):
        for b in f.particle_blocks:
            o.add_particles(b,weight = 0.5)

def _random_picks( n, seed = 123 ):
    """Random picks, of values and functions of many kinds"""
    rng = random.Random(seed)
    plain = [ 'ux', 'uz', '(x/cm)', '(ekin/MeV)', 'weight', '2', '3.5', '1e3', '0x10', 'pdgcode',
              'userflags', '(4cm^2/cm^2)', '(25meV/eV)', '(2cm^(-1)*x)', '(sqrt(ekin)/sqrt(eV))',
              '(2^(ux)MeV/MeV)', '(-2meV/eV)', '(5000eV/keV)', '(neutron/2)', 'fileidx' ]
    def val( d ):
        if d <= 0 or rng.random() < 0.25:
            return rng.choice(plain)
        k = rng.random()
        if k < 0.45:
            return val(d-1) + rng.choice(['+','-','*','/']) + val(d-1)
        if k < 0.6:
            return rng.choice(['-','+']) + val(d-1)
        if k < 0.75:
            return f'({val(d-1)})^' + rng.choice(['2','-1','0.5'])
        if k < 0.85:
            return rng.choice(['abs','cos','atan2','hypot','max','min']) + f'({val(d-1)},{val(d-1)})'
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
    return [ cond(3) for _ in range(n) ]

def _cmake_project( programs ):
    """CMakeLists.txt building the programs (name, source file)"""
    lines = [ 'cmake_minimum_required(VERSION 3.21...4.4)',
              'project( MCPLGeneratedCode LANGUAGES C CXX )',
              'find_package( MCPL REQUIRED )',
              'set( CMAKE_C_STANDARD 99 )', 'set( CMAKE_CXX_STANDARD 17 )',
              'if ( NOT MSVC )',
              '  add_compile_options( -Wall -Wextra -pedantic -Werror )',
              'endif()' ]
    for name, src in programs:
        lines += [ f'add_executable( {name} {src} )',
                   f'target_link_libraries( {name} MCPL::MCPL )' ]
        if src.endswith('.c'):
            #(the math library of C):
            lines += [ 'if ( NOT WIN32 )', f'  target_link_libraries( {name} m )', 'endif()' ]
    return '\n'.join(lines) + '\n'

def _particles( fn ):
    import numpy as np
    sys.path.insert(0,str(pyroot/'src'))
    import mcpl
    names = ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'polx', 'poly', 'polz', 'ekin', 'time', 'weight',
              'pdgcode', 'userflags' )
    with mcpl.MCPLFile(fn) as f:
        blocks = list(f.particle_blocks)
        res = { n : np.concatenate([ getattr(b,n) for b in blocks ]) if blocks else np.zeros(0)
                for n in names }
        if f.userdata_layout:
            res['userdata'] = np.concatenate([ b.userdata for b in blocks ]) if blocks else None
    return res

def _same( a, b ):
    """Whether the particles are the same: 'exact', 'close' (floating point
    numbers within 1e-13, e.g. on platforms which fuse multiplications and
    additions), or None"""
    import numpy as np
    if a.keys() != b.keys() or len(a['x']) != len(b['x']):
        return None
    exact = True
    for n in a:
        if a[n] is None or np.array_equal(a[n],b[n],equal_nan = a[n].dtype.kind == 'f'):
            continue
        if a[n].dtype.kind != 'f' or not np.allclose(a[n],b[n],rtol = 1e-13,atol = 0,equal_nan = True):
            return None
        exact = False
    return 'exact' if exact else 'close'

def run( nprocs, nrandom = 200 ):
    """Build MCPL and the generated programs, run them, and compare (in the
    current directory)"""
    from .cmake import CMakeRunner
    sys.path.insert(0,str(pyroot/'src'))
    import mcpl
    from mcpl._expr_ast2c import _expr_ast2c
    from mcpl._expr_ast2cpp import _expr_ast2cpp
    cwd = pathlib.Path('.').absolute()
    c = CMakeRunner( blddir = cwd/'bld', instdir = cwd/'inst', mode = 'install',
                     nprocs = nprocs )
    c.do_cfg()
    c.do_build()
    c.do_install()
    _files['universal'] = cwd/'universal.mcpl'
    _write_universal(_files['universal'])
    cases = _cases + [ ( 'misc', p, None ) for p in _random_picks(nrandom) ]
    gen = cwd/'gen'
    gen.mkdir()
    programs, runs = [], []
    for i, ( fkey, pick, edit, *rng ) in enumerate(cases):
        skip, limit = rng or ( 0, None )
        with mcpl.MCPLFile(_files[fkey]) as f:
            layout = f.userdata_layout
        try:
            mcpl.ParticleFilter(pick) if pick else None
            mcpl.ParticleEdit(edit) if edit else None
        except mcpl.MCPLError:
            continue#(only valid expressions, see the tests of expressions)
        for lang, fct, ext in ( ( 'c', _expr_ast2c, 'c' ), ( 'cpp', _expr_ast2cpp, 'cc' ) ):
            name = f'{lang}{i}'
            ( gen / f'{name}.{ext}' ).write_text(fct(pick,edit,layout,skip = skip,limit = limit))
            programs.append( ( name, f'{name}.{ext}' ) )
            runs.append( ( name, fkey, pick, edit, skip, limit ) )
    ( gen / 'CMakeLists.txt' ).write_text(_cmake_project(programs))
    cmakedir = subprocess.run([ str(cwd/'inst/bin/mcpl-config'), '--show', 'cmakedir' ],
                              capture_output = True, text = True, check = True).stdout.strip()
    subprocess.run([ 'cmake', '-S', str(gen), '-B', str(gen/'bld'), f'-DMCPL_DIR={cmakedir}',
                     '-DCMAKE_BUILD_TYPE=Release' ],check = True)
    subprocess.run([ 'cmake', '--build', str(gen/'bld'), '--parallel', str(nprocs) ],check = True)
    env = { **os.environ, 'PYTHONPATH' : str(pyroot/'src') }
    counts = { 'exact' : 0, 'close' : 0, 'errors' : 0, 'bad' : 0 }
    for name, fkey, pick, edit, skip, limit in runs:
        d = cwd / 'out' / name
        d.mkdir(parents = True)
        args = [ sys.executable, '-m', 'mcpl', '--extract' ]
        args += [ '-p', _option_arg(pick) ] if pick else []
        args += [ '-E', _option_arg(edit) ] if edit else []
        args += [ f'-s{skip}' ] if skip else []
        args += [ f'-l{limit}' ] if limit else []
        rp = subprocess.run(args + [ str(_files[fkey]), str(d/'py.mcpl') ],env = env,
                            capture_output = True, text = True, check = False)
        exe = next( p for p in ( gen/'bld'/name, gen/'bld'/'Release'/f'{name}.exe', gen/'bld'/f'{name}.exe' )
                    if p.exists() )
        rg = subprocess.run([ str(exe), str(_files[fkey]), str(d/'gen.mcpl') ],
                            capture_output = True, text = True, check = False)
        what = f'{name} (pick {pick!r}, edit {edit!r}, skip {skip}, limit {limit})'
        if rp.returncode or rg.returncode:
            ok = bool(rp.returncode) == bool(rg.returncode)
            counts['errors' if ok else 'bad'] += 1
            if not ok:
                print(f'MISMATCH of errors for {what}: {rp.stdout[-300:]}{rp.stderr[-300:]}'
                      f' | {rg.stdout[-300:]}{rg.stderr[-300:]}')
            continue
        res = _same(_particles(d/'py.mcpl'),_particles(d/'gen.mcpl'))
        counts[res or 'bad'] += 1
        if res is None:
            print(f'MISMATCH of particles for {what}')
    print(f'\nGenerated programs: {counts["exact"]} gave exactly the same particles,'
          f' {counts["close"]} the same within 1e-13, {counts["errors"]} the same errors,'
          f' and {counts["bad"]} different results')
    if counts['bad']:
        raise SystemExit('ERROR: The generated code gave different results')
