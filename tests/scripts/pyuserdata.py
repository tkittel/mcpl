
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
# Python API, and of mcpltool giving the same results and printouts as
# mcpltool-c for such files. The files are written with the C API.

import pathlib
import shutil
import subprocess
import sys

import mcpldev as mcpl
from MCPLTestUtils.dirs import mcpltool_cmd, test_data_dir
from MCPLTestUtils.loadlib import getlib

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
    w('empty.mcpl','x:int8',0)
    w('big.mcpl','x:uint8[65535]',2)
    #truncated file:
    data = (input_dir/'raw.mcpl').read_bytes()
    (input_dir/'trunc.mcpl').write_bytes(data[:-20])

def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, check=False)
    return r.returncode, r.stdout.decode().replace('\r\n','\n'), r.stderr.decode()

def fresh(d):
    if pathlib.Path(d).exists():
        shutil.rmtree(d)
    shutil.copytree(input_dir, d)

def dir_contents(d):
    return { f.name : f.read_bytes() for f in sorted(pathlib.Path(d).iterdir()) }

def py_args( args ):
    """Arguments for mcpltool corresponding to those of mcpltool-c: -pPDGCODE
    is -p "pdgcode == PDGCODE" for mcpltool"""
    res = []
    for a in args:
        a = str(a)
        if a.startswith('-p') and len(a) > 2:
            res += [ '-p', f'pdgcode == {a[2:]}' ]
        else:
            res.append(a)
    return res

def compare(*args):
    fresh('c')
    fresh('py')
    c = run([str(mcpltool_cmd), *args], 'c')
    #the Python API has no mcpl_ prefix on function names, and transfers
    #particles with add_particles:
    c = ( c[0], c[1].replace('mcpl_','').replace('transfer_last_read_particle',
                                                 'add_particles'), c[2] )
    p = run([sys.executable, '-m', 'mcpldev', *py_args(args)], 'py')
    problems = []
    if c[0] != p[0]:
        problems.append(f'exit codes differ: C: {c[0]} Py: {p[0]}')
    if c[1] != p[1]:
        problems.append(f'printouts differ:\n      C: {c[1]!r}\n     Py: {p[1]!r}')
    if p[2]:
        problems.append(f'mcpltool stderr: {p[2]!r}')
    dc, dp = dir_contents('c'), dir_contents('py')
    if set(dc) != set(dp):
        problems.append(f'different files: C: {sorted(dc)} Py: {sorted(dp)}')
    else:
        problems += [ f'file {k} differs' for k in dc if dc[k] != dp[k] ]
    print(f'mcpltool-c {" ".join(args)}: exit code {c[0]}')
    for line in c[1].splitlines():
        print(f'   | {line}')
    for problem in problems:
        print(f'   PROBLEM: {problem}')
    #New or modified MCPL files, read with the C API:
    for name, data in dc.items():
        orig = input_dir/name
        if ( name.endswith('.mcpl') and args[0] != '--repair'
             and ( not orig.exists() or orig.read_bytes() != data ) ):
            cprint(lib.mcpltest_ud_read,pathlib.Path('c',name).as_posix())
    return not problems

def test_compare_with_mcpltool():
    print('=== Comparison with mcpltool-c')
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
        ['--extract','--no-comment','-p2112','raw.mcpl','out.mcpl'],
        ['--text','std.mcpl','out.txt'],
        ['--repair','trunc.mcpl'],
    ]
    ok = True
    for args in cases:
        ok &= compare(*args)
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
        print('big:',b.userdata['x'].shape,b.userdata['x'][1,:5].tolist(),
              int(b.userdata['x'][1,-1]))

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
    #Edits and selections when extracting:
    rc = subprocess.run([sys.executable,'-m','mcpldev','--extract','--pick',
                         'x > 1.5cm','--edit','z += 1cm',str(d/'std.mcpl'),
                         str(d/'w4.mcpl')],capture_output=True,check=False).returncode
    print('mcpltool --extract --pick --edit:',rc)
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
                          pick='x > 1.5cm',edit='z += 1cm') as o:
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
            o = mcpl.MCPLOutFile(d/'bad.mcpl',userdata_layout=layout)
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
            o = mcpl.MCPLOutFile(d/'bad.mcpl',userdata_layout=stdlayout)
            try:
                o.add_particles(f.read_block())
            finally:
                o.close()
    expect_error('transfer without userdata',transfer_none)
    expect_error('invalid layout',add(layout='uint8[27]'))
    def twice():
        with mcpl.MCPLOutFile(d/'bad.mcpl',userdata_layout='a:int8') as o:
            o.enable_userdata('a:int16')
    expect_error('different layouts',twice)
    def late():
        with mcpl.MCPLOutFile(d/'bad.mcpl') as o:
            o.add_particle(uz=1.0,ekin=1.0)
            o.enable_userdata('a:int8')
    expect_error('enable too late',late)

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
                    'x:', ':int8', 'X:int8', 'x-y:int8', 'x:int9', 'x:int8,',
                    'x:int8,x:int16', 'x:int8[0]', 'x:int8[03]', 'x:int8[3',
                    'x:uint8[65536]', 'x:uint8[65535],y:int8', 'x :int8',
                    'a'*65+':int8', 'x:float64[8192]',
                    #(units, as in the test of the C API, app_errstate):
                    'a:float32:cm', 'a:float64:MeV,b:float32:ms,c:float32:K,d:float32:deg',
                    'a:float32[3]:cm', 'a:float64:cm^2.MeV', 'a:float64:MeV^-1',
                    'a:float64:cm.ms^-1', 'a:float64:cm^-9.MeV^9.ms.K^2.deg^-1', 'a:int32:K',
                    'a:float32:', 'a:float32:m', 'a:float32:CM', 'a:float32:cm.cm',
                    'a:float32:MeV.cm', 'a:float32:cm^1', 'a:float32:cm^0', 'a:float32:cm^-0',
                    'a:float32:cm^10', 'a:float32:cm^', 'a:float32:cm^-', 'a:float32:cm.',
                    'a:float32:.cm', 'a:float32:cm..MeV', 'a:float32:cm*MeV', 'a:float32:cm/ms',
                    'a:float32:cm:MeV', 'a:float32[3:cm', 'a:float32:cm[3]',
                    #(division, parentheses and "*", with hints):
                    'a:float32:MeV/cm', 'a:float32:1/cm', 'a:float32:(cm.MeV)^-1',
                    'a:float32:cm^(-1)', 'a:float32:cm^-1/ms' ]:
        try:
            dt = userdata_dtype(layout)
            print(f'{layout!r}: size {dt.itemsize}')
        except mcpl.MCPLError as e:
            print(f'{layout!r}: MCPLError: {e}')
    from mcpldev._userdata import userdata_units
    print('units:', userdata_units('temp:float32:K,n:int32,dir:float32[3]:cm,q:float64:cm^-1'))

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
    print('userdata.temp > 293K:', [ bool(v) for v in mcpl.ParticleFilter('userdata.temp > 293K')(b) ])
    for e in ( 'userdata.temp + x', 'userdata.temp > 293', 'userdata.q + userdata.d',
               'userdata.temp' ):
        try:
            v = ( mcpl.ParticleFilter if '>' in e else mcpl.ParticleValue )(e)(b)
            print(f'{e}: {list(v)}')
        except mcpl.MCPLError as err:
            print(f'{e}: MCPLError: {err}')
    for p in ( 'userdata.temp', 'userdata.d : userdata.temp', 'userdata.d;range=0cm:20cm',
               'userdata.d;range=0:20', 'userdata.temp;range=0cm:2cm', 'userdata.n;bar',
               'userdata.d;bar' ):
        try:
            panel = mcpl.histogram(f,p).figure().panels[0]
            print(f'plot {p}: {panel.xlabel} | {panel.ylabel}')
        except mcpl.MCPLError as err:
            print(f'plot {p}: MCPLError: {err}')

def main():
    make_inputs()
    ok = test_compare_with_mcpltool()
    test_python_api()
    test_python_writing()
    test_example()
    test_layouts()
    test_units()
    if not ok:
        raise SystemExit('Problems found')

if __name__ == '__main__':
    main()
