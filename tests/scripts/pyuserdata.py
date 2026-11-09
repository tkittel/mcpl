
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

# Tests of reading per-particle userdata (MCPL format version 4) with the
# Python API, and of mcpltool and the C library for such files. The files are
# written with the C API.

import contextlib
import pathlib
import shutil
import subprocess
import sys

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils import clib
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.loadlib import getlib
from MCPLTestUtils.plots import hist_panel

lib = getlib('userdata')
input_dir = pathlib.Path('inputs').absolute()

def cprint(fct, *args):
    #(for output of the C test module, in order with the Python output; paths
    #are given with forward slashes, so the output is the same on Windows):
    print(flush=True,end='')
    fct(*args)
    print(flush=True,end='')

def make_inputs():
    input_dir.mkdir()
    def w(name, layout, n, options = 0):
        lib.mcpltest_ud_write(str(input_dir/name), layout, n, options)
    w('std.mcpl','<STD>',3)
    w('std2.mcpl','<STD>',2)
    w('stddp.mcpl','<STD>',3,3)#double precision and polarisation
    w('raw.mcpl','data:uint8[27]',4,4)#odd particles with zero userdata
    w('raw33.mcpl','data:uint8[33]',2)#same size as the standard layout
    w('none.mcpl','<NONE>',2)
    w('empty.mcpl','p:int8',0)
    w('big.mcpl','p:uint8[65535]',2)
    #truncated file:
    data = (input_dir/'raw.mcpl').read_bytes()
    (input_dir/'trunc.mcpl').write_bytes(data[:-20])

def run(cmd, cwd):
    #(with the errors, from standard error, in the output):
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       check=False)
    return r.returncode, r.stdout.decode().replace('\r\n','\n'), ''

def fresh(d):
    if pathlib.Path(d).exists():
        shutil.rmtree(d)
    shutil.copytree(input_dir, d)

def dir_contents(d):
    return { f.name : f.read_bytes() for f in sorted(pathlib.Path(d).iterdir()) }

def tool(*args):
    """Run mcpltool on copies of the inputs, show its output, and read the MCPL
    files it creates or changes with the C API"""
    fresh('py')
    rc, out, err = run([sys.executable, '-m', 'mcpldev', *args], 'py')
    print(f'mcpltool {" ".join(args)}: exit code {rc}')
    for line in out.splitlines():
        print(f'   | {line}')
    if err:
        print(f'   PROBLEM: mcpltool stderr: {err!r}')
    for name, data in dir_contents('py').items():
        orig = input_dir/name
        if ( name.endswith('.mcpl') and args[0] != '--repair'
             and ( not orig.exists() or orig.read_bytes() != data ) ):
            cprint(lib.mcpltest_ud_read,pathlib.Path('py',name).as_posix())
    return not err

def test_mcpltool():
    print('=== mcpltool')
    cases = [
        ['std.mcpl'],
        ['-l0','raw.mcpl'],
        ['-n','stddp.mcpl'],
        ['-j','big.mcpl'],
        ['-l1','big.mcpl'],
        ['empty.mcpl'],
        ['--merge','out.mcpl','std.mcpl','std2.mcpl'],
        ['--merge','out.mcpl','std.mcpl','raw33.mcpl'],
        ['--merge','out.mcpl','std.mcpl','none.mcpl'],
        ['--merge','--inplace','std2.mcpl','std.mcpl'],
        ['--merge','--inplace','std2.mcpl','raw33.mcpl'],
        ['--forcemerge','out.mcpl','std.mcpl','stddp.mcpl'],
        ['--forcemerge','out.mcpl','std.mcpl','raw33.mcpl'],
        ['--forcemerge','out.mcpl','none.mcpl','std.mcpl'],
        ['--forcemerge','out.mcpl','empty.mcpl','raw.mcpl'],
        ['--extract','std.mcpl','out.mcpl'],
        ['--extract','-l2','-s1','stddp.mcpl','out.mcpl'],
        ['--extract','--no-comment','-e','pdgcode == 2112','raw.mcpl','out.mcpl'],
        ['--text','std.mcpl','out.txt'],
        ['--repair','trunc.mcpl'],
    ]
    ok = True
    for args in cases:
        ok &= tool(*args)
    return ok

def test_text():
    #The text files of mcpltool --text:
    print('=== Text export')
    fresh('py')
    for fn in ('std.mcpl','raw.mcpl'):
        rc, _, err = run([sys.executable, '-m', 'mcpldev', '--text', fn, fn+'.txt'], 'py')
        assert rc == 0 and not err, (rc, err)
        print(pathlib.Path('py',fn+'.txt').read_text(),end='')

def test_compare_with_c_library():
    #The C library itself gives the same dumps (mcpltool shows the first 10
    #particles, unless given with -l), and the same files from merges:
    print('=== Comparison with the C library')
    def py( *args ):
        fresh('py')
        return run([sys.executable, '-m', 'mcpldev', *args], 'py')
    ok = True
    for args, parts, limit in ( ( ['std.mcpl'], 0, 10 ), ( ['-l0','raw.mcpl'], 0, 0 ),
                                ( ['-n','stddp.mcpl'], 2, 10 ), ( ['-j','big.mcpl'], 1, 0 ),
                                ( ['-l1','big.mcpl'], 0, 1 ), ( ['empty.mcpl'], 0, 10 ) ):
        fn = args[-1]
        c = clib.dump(input_dir/fn,parts,0,limit).decode().replace('\r\n','\n')
        same = py(*args)[1] == c
        ok &= same
        print(f'dump {" ".join(args)}: same as the C library: {same}')
    fresh('clib')
    for name, args, cfct in (
            ( 'merge', ['--merge','out.mcpl','std.mcpl','std2.mcpl'],
              lambda : clib.merge('clib/out.mcpl','clib/std.mcpl','clib/std2.mcpl') ),
            ( 'merge in place', ['--merge','--inplace','std2.mcpl','std.mcpl'],
              lambda : clib.lib().mcpltest_merge_inplace('clib/std2.mcpl','clib/std.mcpl') ),
            ( 'forced merge', ['--forcemerge','out_forced.mcpl','std.mcpl','stddp.mcpl'],
              lambda : clib.lib().mcpltest_merge('clib/out_forced.mcpl',
                                                 'clib/std.mcpl\nclib/stddp.mcpl',1,0) ),
            ( 'forced merge, other layouts', ['--forcemerge','out_forced2.mcpl','std.mcpl','raw33.mcpl'],
              lambda : clib.lib().mcpltest_merge('clib/out_forced2.mcpl',
                                                 'clib/std.mcpl\nclib/raw33.mcpl',1,0) ) ):
        rc = py(*args)[0]
        res = cfct()
        out = args[2] if args[1] == '--inplace' else args[1]
        same = ( rc == 0 and res == 'ok'
                 and pathlib.Path('py',out).read_bytes() == pathlib.Path('clib',out).read_bytes() )
        ok &= same
        print(f'{name}: same file as the C library: {same}' + ( '' if res == 'ok' else f' ({res})' ))
    return ok

def test_python_api():
    print('=== Python API')
    fresh('api')
    d = pathlib.Path('api')
    with mcpl.MCPLFile(d/'std.mcpl') as f:
        print(f'version={f.version} layout={f.userdata_layout!r}'
              f' size={f.userdata_size} particlesize={f.particlesize}')
        b = f.read_block()
        ud = b.userdata
        print('dtype:',ud.dtype.descr)
        for name in ud.dtype.names:
            print(f'  {name}: {ud[name].tolist()}')
        p = b[2]
        print('particle 2:',p.userdata['temp'],p.userdata['tags'].tolist())
        sel = b[b.userdata['origin'] < 0]
        print('selected with origin<0:',sel.userdata['id'].tolist(),sel.fileidx.tolist())
        print('empty selection:',b[b.x > 100].userdata.dtype.names,len(b[b.x > 100].userdata))
    with mcpl.MCPLFile(d/'none.mcpl') as f:
        b = f.read_block()
        print('no userdata:',f.userdata_layout,f.userdata_size,b.userdata,b[0].userdata)
    with mcpl.MCPLFile(d/'raw.mcpl',blocklength=3) as f:
        print('raw blocks:',[ b.userdata['data'][:,:4].tolist() for b in f.particle_blocks ])
    with mcpl.MCPLFile(d/'big.mcpl') as f:
        b = f.read_block()
        print('big:',b.userdata['p'].shape,b.userdata['p'][1,:5].tolist(),
              int(b.userdata['p'][1,-1]))

    #Writing files from files with userdata (transfer_metadata, and the
    #userdata of the particles):
    with mcpl.MCPLFile(d/'stddp.mcpl') as f, mcpl.MCPLOutFile(d/'w1.mcpl') as o:
        o.transfer_metadata(f)
        print('out:',o.userdata_layout,o.userdata_size,o.particlesize)
        for b in f.particle_blocks:
            o.add_particles(b[::-1])
    cprint(lib.mcpltest_ud_read,(d/'w1.mcpl').as_posix())
    #...into single precision without polarisation (repacking particles):
    with mcpl.MCPLFile(d/'stddp.mcpl') as f, mcpl.MCPLOutFile(d/'w2.mcpl') as o:
        o.transfer_metadata(f)
        o.enable_universal_weight(1.0)
        o2 = mcpl.MCPLOutFile(d/'w3.mcpl')
        o2.add_particles(f.read_block())#(no userdata: discarded)
        o2.close()
        f.rewind()
        b = f.read_block()
        o.add_particles(b,z=5.0)#edited fields
        o.add_particle(b[1])#single particle
        o.add_particle(x=1.0,uz=1.0,ekin=1.0,pdgcode=22,userdata={})#zeros
    cprint(lib.mcpltest_ud_read,(d/'w2.mcpl').as_posix())
    cprint(lib.mcpltest_ud_read,(d/'w3.mcpl').as_posix())
    #Edits when extracting:
    rc = subprocess.run([sys.executable,'-m','mcpldev','--extract','--edit',
                         'x > 1.5cm; z += 1cm',str(d/'std.mcpl'),
                         str(d/'w4.mcpl')],capture_output=True,check=False).returncode
    print('mcpltool --extract --edit:',rc)
    cprint(lib.mcpltest_ud_read,(d/'w4.mcpl').as_posix())
    #Different layouts:
    try:
        with mcpl.MCPLFile(d/'std.mcpl') as f, mcpl.MCPLFile(d/'raw33.mcpl') as f2:
            o = mcpl.MCPLOutFile(d/'w5.mcpl')
            o.transfer_metadata(f)
            o.add_particles(f2.read_block())
    except mcpl.MCPLError as e:
        print('MCPLError:',e)
        o._abort()

stdlayout = 'temp:float32,origin:int32,tags:uint8[3],big:float64,id:uint64,s:int16'
stdvalues = { 'temp' : [293.15,294.15,295.15], 'origin' : [0,-1000,-2000],
              'tags' : [[0,1,2],[10,11,12],[20,21,22]],
              'big' : [1e300,2e300,3e300], 'id' : [2**64-1,2**64-2,2**64-3],
              's' : [-32768,-32767,-32766] }

def test_python_writing():
    print('=== Writing userdata with the Python API')
    d = pathlib.Path('pywrite')
    d.mkdir()
    #Same particles as written with the C API must give identical files, with
    #userdata given as dict or as structured array (and for single particles):
    def write(fn, how):
        with mcpl.MCPLOutFile(d/fn,sourcename='mcpltest_ud_write',
                              userdata_layout=stdlayout) as o:
            kw = { 'x' : [1.0,2.0,3.0], 'uz' : 1.0, 'ekin' : [0.5,1.0,1.5],
                   'pdgcode' : 2112, 'weight' : 1.0 }
            if how == 'dict':
                o.add_particles(userdata=stdvalues,**kw)
            elif how == 'array':
                with mcpl.MCPLFile(input_dir/'std.mcpl') as f:
                    o.add_particles(userdata=f.read_block().userdata,**kw)
            else:
                for i in range(3):
                    o.add_particle( x = kw['x'][i], uz = 1.0, ekin = kw['ekin'][i],
                                    pdgcode = 2112, weight = 1.0,
                                    userdata = { k : v[i] for k,v in stdvalues.items() } )
        same = (d/fn).read_bytes() == (input_dir/'std.mcpl').read_bytes()
        print(f'userdata as {how}: identical to file from C API: {same}')
    write('dict.mcpl','dict')
    write('array.mcpl','array')
    write('single.mcpl','single')

    #Missing fields give zeros (also all of them, with userdata={}), and
    #values for a single particle apply to all:
    with mcpl.MCPLOutFile(d/'mixed.mcpl') as o:
        o.enable_userdata(stdlayout)
        o.add_particle(x=4.0,uz=1.0,ekin=2.0,pdgcode=22,weight=1.0,
                       userdata={'temp':300.0,'tags':[7,8,9]})
        o.add_particle(x=5.0,uz=1.0,ekin=2.5,pdgcode=22,weight=1.0,userdata={})
        o.add_particles(x=[6.0,7.0],uz=1.0,ekin=1.0,pdgcode=11,weight=1.0,
                        userdata={'s':5})
    cprint(lib.mcpltest_ud_read,(d/'mixed.mcpl').as_posix())

    #Replacing the userdata of particles read from a file, with selections and
    #edits (of particles given as blocks and as arrays):
    with mcpl.MCPLFile(input_dir/'std.mcpl') as f:
        b = f.read_block()
    ud = b.userdata.copy()
    ud['temp'] += 100
    with mcpl.MCPLOutFile(d/'sel1.mcpl',userdata_layout=stdlayout,
                          edit='x > 1.5cm; z += 1cm') as o:
        o.add_particles(b,userdata=ud)
        o.add_particles(x=b.x,uz=1.0,ekin=1.0,pdgcode=22,weight=1.0,userdata=ud)
    cprint(lib.mcpltest_ud_read,(d/'sel1.mcpl').as_posix())
    with mcpl.MCPLOutFile(d/'sel2.mcpl') as o:
        o.transfer_metadata(input_dir/'std.mcpl')
        o.add_particles(b[1:],userdata={'origin':[7,8]},weight=2.0)
        o.add_particle(b[0],userdata={'origin':9})
    cprint(lib.mcpltest_ud_read,(d/'sel2.mcpl').as_posix())

    #Errors:
    def expect_error(title, fct):
        try:
            fct()
        except mcpl.MCPLError as e:
            print(f'{title}: MCPLError: {e}')
        else:
            print(f'{title}: no error!')
    def add(layout = stdlayout, single = False, **kw):
        def fct():
            o = mcpl.MCPLOutFile(d/'bad.mcpl',allow_overwrite=True,userdata_layout=layout)
            try:
                (o.add_particle if single else o.add_particles)(uz=1.0,ekin=1.0,**kw)
            finally:
                o.close()
        return fct
    expect_error('unknown field',add(userdata={'nosuch':1}))
    expect_error('non-integer',add(userdata={'origin':1.5}))
    expect_error('wrong shape',add(userdata={'tags':[1,2]}))
    expect_error('out of range',add(userdata={'s':40000}))
    expect_error('negative unsigned',add(userdata={'id':-1}))
    expect_error('not numbers',add(userdata={'temp':'hot'}))
    expect_error('not a dict',add(userdata=[1,2,3]))
    expect_error('inconsistent lengths',add(x=[1,2],userdata={'temp':[1,2,3]}))
    expect_error('no userdata in file',add(layout=None,userdata={'a':1}))
    expect_error('several for add_particle',add(single=True,userdata={'s':[1,2]}))
    expect_error('add_particles without userdata',add())
    expect_error('add_particle without userdata',add(single=True))
    def transfer_none():
        with mcpl.MCPLFile(input_dir/'none.mcpl') as f:
            o = mcpl.MCPLOutFile(d/'bad.mcpl',allow_overwrite=True,userdata_layout=stdlayout)
            try:
                o.add_particles(f.read_block())
            finally:
                o.close()
    expect_error('transfer without userdata',transfer_none)
    expect_error('invalid layout',add(layout='uint8[27]'))
    def twice():
        with mcpl.MCPLOutFile(d/'bad.mcpl',allow_overwrite=True,userdata_layout='a:int8') as o:
            o.enable_userdata('a:int16')
    expect_error('different layouts',twice)
    def late():
        with mcpl.MCPLOutFile(d/'bad.mcpl',allow_overwrite=True) as o:
            o.add_particle(uz=1.0,ekin=1.0)
            o.enable_userdata('a:int8')
    expect_error('enable too late',late)
    #64 bit integers given as plain Python integers are stored exactly (not via
    #floating point numbers), up to the limits of the types:
    for layout, values in ( ('c:uint64', [2**64-1, 2**63+1, 0]),
                            ('c:int64', [-2**63, 2**63-1, -2**53-1]) ):
        for single in ( False, True ):
            with mcpl.MCPLOutFile(d/'ints.mcpl',allow_overwrite=True,userdata_layout=layout) as o:
                if single:
                    for v in values:
                        o.add_particle(uz=1.0, ekin=1.0, userdata={'c':v})
                else:
                    o.add_particles(uz=1.0, ekin=1.0, userdata={'c':values})
            got = [ int(x) for b in mcpl.MCPLFile(d/'ints.mcpl').particle_blocks
                    for x in b.userdata['c'] ]
            assert got == values, (layout, single, got)
            print(f'{layout} values {values} stored exactly'
                  f' (add_particle{"" if single else "s"})')
    expect_error('above uint64',add(layout='c:uint64',userdata={'c':[2**64,1]}))
    expect_error('above int64',add(layout='c:int64',userdata={'c':2**63}))
    expect_error('below int64',add(layout='c:int64',userdata={'c':[-2**63-1]}))

def test_example():
    print('=== pyexample_userdatamcpl')
    #Run the example with the mcpl module being tested, and check the file it
    #wrote with the C API:
    f = test_data_dir.joinpath('pyexamples','pyexample_userdatamcpl')
    code = f.read_text().replace('\nimport mcpl\n','\nimport mcpldev as mcpl\n')
    assert 'import mcpldev as mcpl' in code
    sys.argv = [ str(f), 'pyexample.mcpl' ]
    print(flush=True,end='')
    exec(compile(code,str(f),'exec'),{'__name__':'__main__'})  # noqa: S102
    print(flush=True,end='')
    cprint(lib.mcpltest_ud_read,'pyexample.mcpl')

def test_layouts():
    print('=== Invalid layouts (same errors as in the C API)')
    from mcpldev._userdata import userdata_dtype
    for layout in [ 'data:uint8[27]', 'a:int8,b:float64[2]', '', 'uint8[27]',
                    'p:', ':int8', 'X:int8', 'p-q:int8', 'p:int9', 'p:int8,',
                    'p:int8,p:int16', 'p:int8[0]', 'p:int8[03]', 'p:int8[3',
                    'p:uint8[65536]', 'p:uint8[65535],q:int8', 'p :int8',
                    'a'*65+':int8', 'p:float64[8192]',
                    #(reserved names, and similar names which are not):
                    'x:float32', 'a:int8,ekin:float64', 'position:float32[3]',
                    'wavelength:float32', 'userflags:uint32', 'class:int8',
                    'a:int8,from:float64',
                    'xx:float32,ekin2:float32,pos:int8',
                    #(units, as in the test of the C API, app_errstate):
                    'a:float32:cm', 'a:float64:MeV,b:float32:ms,c:float32:K,d:float32:deg',
                    'a:float32[3]:cm', 'a:float64:cm^2.MeV', 'a:float64:MeV^-1',
                    'a:float64:cm.ms^-1', 'a:float64:cm^-9.MeV^9.ms.K^2.deg^-1', 'a:int32:K',
                    'a:float32:', 'a:float32:m', 'a:float32:CM', 'a:float32:cm.cm',
                    'a:float32:MeV.cm', 'a:float32:cm^1', 'a:float32:cm^0', 'a:float32:cm^-0',
                    'a:float32:cm^10', 'a:float32:cm^', 'a:float32:cm^-', 'a:float32:cm.',
                    'a:float32:.cm', 'a:float32:cm..MeV', 'a:float32:cm*MeV', 'a:float32:cm/ms',
                    'a:float32:cm:MeV', 'a:float32[3:cm', 'a:float32:cm[3]',
                    #(division, parentheses, and "*", with hints):
                    'a:float32:MeV/cm', 'a:float32:1/cm', 'a:float32:(cm.MeV)^-1',
                    'a:float32:cm^(-1)', 'a:float32:cm^-1/ms' ]:
        try:
            dt = userdata_dtype(layout)
            print(f'{layout!r}: size {dt.itemsize}')
        except mcpl.MCPLError as e:
            print(f'{layout!r}: MCPLError: {e}')
    from mcpldev._userdata import userdata_units
    print('units:', userdata_units('temp:float32:K,n:int32,dir:float32[3]:cm,q:float64:cm^-1'))

def test_expressions():
    print('Userdata fields in expressions:')
    layout = 'temp:float32:K,nscat:uint8,d:float32[3]:cm,theta:float64:deg,big:uint64'
    with mcpl.MCPLOutFile('udexpr.mcpl', userdata_layout = layout) as o:
        o.add_particles( ekin = [1.0,2.0,3.0], uz = 1.0, pdgcode = 2112,
                         weight = 1.0,
                         userdata = { 'temp' : [290,300,310], 'nscat' : [0,1,255],
                                      'd' : [[1,2,3],[4,5,6],[7,8,9]],
                                      'theta' : [0,90,180],
                                      'big' : [0,2**63+5,2**64-1] } )
    with mcpl.MCPLFile('udexpr.mcpl') as f:
        b = f.read_block()
    def show( cls, expr ):
        #(the mask of the particles kept, or the values, or the changes):
        try:
            if cls is mcpl.ParticleEdit:
                kept, res = cls(expr)._apply(b)
                res = res or np.isin(np.arange(len(b)),np.arange(len(b)) if kept is None else kept)
            else:
                res = cls(expr)(b)
            print(f'  {expr}: {res.tolist() if hasattr(res,"tolist") else res}')
        except mcpl.MCPLError as e:
            print(f'  {expr}: MCPLError: {e}')
    for e in ( 'userdata.temp > 295K', 'userdata.nscat >= 1',
               'userdata.d.at(2) > 5cm', 'userdata.theta > 45deg',
               'sin(userdata.theta) > 0.5', 'userdata.nscat - 1 < 0',
               'userdata.temp > 299.99999K', 'userdata.temp == 300.00001K',
               'userdata.big >= 0x8000000000000000',
               'userdata.big == 0xFFFFFFFFFFFFFFFF', 'userdata.big & 1 == 1',
               'userdata.big > 0 and userdata.big - 1 >= 0x8000000000000004',
               #Errors:
               'userdata.temp > 295', 'userdata.d > 1cm', 'userdata.d.at(3) > 0cm',
               'userdata.nope > 0', 'userdata > 0', 'userdata.d.x > 0',
               'userdata.d.at(x) > 0', 'userdata.big + 1 > 0',
               'userdata.big > -1', 'userdata.big - 1 > 0' ):
        show(mcpl.ParticleEdit,e)
    for e in ( 'userdata.temp/K', 'userdata.d.at(0)/mm', 'userdata.nscat',
               'userdata.temp' ):
        show(mcpl.ParticleValue,e)
    for e in ( 'x = userdata.d.at(0)', 'ekin = userdata.temp*1MeV/K',
               'userdata.temp = 3K', 'swap(userdata.temp,x)' ):
        show(mcpl.ParticleEdit,e)
    #Without userdata:
    with mcpl.MCPLFile(test_data_dir.joinpath('example.mcpl')) as f:
        b = f.read_block()
        show(mcpl.ParticleEdit,'userdata.temp > 0K')
    #Filters on particles added as arrays to output files:
    with mcpl.MCPLOutFile('udexpr2.mcpl', userdata_layout = layout,
                          edit = 'userdata.temp > 295K') as o:
        o.add_particles( ekin = [1.0,2.0,3.0], uz = 1.0, pdgcode = 2112,
                         weight = 1.0,
                         userdata = { 'temp' : [290,300,310] } )
    with mcpl.MCPLFile('udexpr2.mcpl') as f:
        print('  kept from arrays added to MCPLOutFile:',
              f.read_block().userdata['temp'].tolist())
    #Filters on blocks added with other userdata use that userdata:
    with mcpl.MCPLFile('udexpr.mcpl') as f, mcpl.MCPLOutFile(
            'udexpr3.mcpl', userdata_layout = layout,
            edit = 'userdata.temp > 295K') as o:
        o.add_particles( f.read_block(),
                         userdata = { 'temp' : [300,10,320] } )
    with mcpl.MCPLFile('udexpr3.mcpl') as f:
        print('  kept from a block added with other userdata:',
              f.read_block().userdata['temp'].tolist())
    #mcpltool:
    for args in ( [ '-e', 'userdata.temp > 295K', '-n', 'udexpr.mcpl' ],
                  [ '-t', '-H', 'userdata.temp/K;print;bins=3', 'udexpr.mcpl' ] ):
        print(f'  mcpltool {" ".join(args)}:',flush=True)
        try:
            with contextlib.redirect_stderr(sys.stdout):
                mcpl.app_mcpltool(['mcpltool']+args)
        except SystemExit as e:
            print(f'  exit: {e}')
        sys.stdout.flush()

def test_units():
    print('=== Units of userdata fields in expressions and plots')
    layout = 'temp:float32:K,theta:float32:deg,d:float64:cm,q:float64:cm^-1,n:int32'
    with mcpl.MCPLOutFile('units.mcpl',userdata_layout=layout) as o:
        for i in range(4):
            o.add_particle(pdgcode=2112,ekin=1.0,position=(i,0,0),direction=(0,0,1),
                           userdata={'temp':290+2*i,'theta':30*i,'d':10*i,'q':0.5*i,'n':i})
    f = mcpl.MCPLFile('units.mcpl')
    b = next(iter(f.particle_blocks))
    for e in ( 'userdata.temp/K', 'userdata.theta/deg', 'userdata.d/mm', '(userdata.d + x)/cm',
               'userdata.q*cm', 'userdata.n' ):
        print(f'{e}:', [ round(float(v),4) for v in mcpl.ParticleValue(e)(b) ])
    print('userdata.temp > 293K:', mcpl.ParticleEdit('userdata.temp > 293K')(b).userdata['temp'].tolist())
    for e in ( 'userdata.temp + x', 'userdata.temp > 293', 'userdata.q + userdata.d',
               'userdata.temp' ):
        try:
            v = mcpl.ParticleEdit(e)(b).userdata['temp'] if '>' in e else mcpl.ParticleValue(e)(b)
            print(f'{e}: {list(v)}')
        except mcpl.MCPLError as err:
            print(f'{e}: MCPLError: {err}')
    for p in ( 'userdata.temp', 'userdata.d : userdata.temp', 'userdata.d;range=0cm:20cm',
               'userdata.d;range=0:20', 'userdata.temp;range=0cm:2cm', 'userdata.n;bar',
               'userdata.d;bar' ):
        try:
            panel = hist_panel(mcpl,mcpl.histogram(f,p))
            print(f'plot {p}: {panel.xlabel} | {panel.ylabel}')
        except mcpl.MCPLError as err:
            print(f'plot {p}: MCPLError: {err}')

def main():
    make_inputs()
    ok = test_mcpltool()
    test_text()
    ok &= test_compare_with_c_library()
    test_python_api()
    test_python_writing()
    test_example()
    test_layouts()
    test_expressions()
    test_units()
    if not ok:
        raise SystemExit('Problems found')

if __name__ == '__main__':
    main()
