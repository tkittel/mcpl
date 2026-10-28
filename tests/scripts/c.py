
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

# NEEDS: matplotlib numpy

"""unit test which aims to cover as much code as possible in the mcpl Python
package (as per coverage.py)"""

#coverage recipe:
#
#  coverage2 run --source=MCPL `which sb_mcplpytests_testpyc`
#
#or:
#
#  coverage3 run --source=MCPL `which sb_mcplpytests_testpyc`
#
#then get nice html results with:
#
#coverage html -d somedir/
#

import contextlib
import os
import shutil
import sys

from MCPLTestUtils.common import flush
from MCPLTestUtils.dirs import test_data_dir

os.environ['PYMCPLTOOL_FAKE_PYVERSION']='1'

_fmt = '%.8g'
def _fmtitems(items):
    return '  '.join(_fmt%f for f in items)

def format_numpy_1darray_asfloat(a,edgeitems=3,threshold=1000):
    if not hasattr(a,'shape') or len(a.shape)!=1:
        return str(a)
    if len(a)>threshold:
        return f'[ {_fmtitems(a[0:edgeitems])} ... {_fmtitems(a[-edgeitems:])} ]'
    else:
        return f'[ {_fmtitems(a)} ]'
npfmt = format_numpy_1darray_asfloat

os.mkdir('./fakepypath')
with open('./fakepypath/numpy.py','tw') as f:
    f.write('raise ImportError("fake error")\n')
    f.close()
oldsyspath=sys.path
sys.path=[os.path.abspath('./fakepypath')]+sys.path
try:
    import mcpldev as mcpl
except ImportError as e:
    print(f"Caught expected error: {e!s}")
    mcpl = None
shutil.rmtree('./fakepypath')
sys.path = oldsyspath

if mcpl is None:
    import mcpldev as mcpl #noqa E402

file1 = test_data_dir.joinpath('ref','reffile_12.mcpl')
file2 = test_data_dir.joinpath('ref','reffile_1.mcpl')

file3 = test_data_dir.joinpath('ref','miscphys.mcpl.gz')
file4 = test_data_dir.joinpath('reffmt2','reffile_8.mcpl')
filecrash = test_data_dir.joinpath('ref','reffile_crash.mcpl')

badfiles = sorted(test_data_dir.joinpath('ref').glob('reffile_bad*.mcpl*'))

assert len(badfiles)==9

def testtool(args,testnone=False):
    flush()
    try:
        mcpl.app_mcpltool(['mcpltool']+[str(e) for e in args]
                            if not testnone
                            else None)
    except mcpl.MCPLError as e:
        flush()
        print(f"===> mcpltool ended with MCPLError exception: {e!s}")
    except SystemExit as e:
        flush()
        print(f"===> mcpltool ended with exit code {e!s}")
    flush()

testtool([])
testtool(['-l3'])
testtool([file1,'-nl3'])
testtool([file1,'-jn'])
testtool([file1,'-jl1'])
testtool([file1,'-jl1','-l2'])
testtool([file1,'-js1'])
testtool([file1,'-js1','-s2'])
testtool([file1,'--help'])
testtool(['-v'])
testtool(['-vy'])
testtool(['-v',file1])
testtool(['-h'])
testtool([file1,file2])
testtool(['-vj'])
testtool(['-j',file1,'-bLala'])
testtool([file1,'-b'])
testtool([file1,'-bLala','-bbla'])
testtool(['--lala'])
testtool([],testnone=True)
testtool([file1,'-j'])
testtool([filecrash])
testtool([file3])
testtool([file4])


testtool([test_data_dir.joinpath('ref','reffile_uw.mcpl.gz')])
testtool([test_data_dir.joinpath('ref','reffile_empty.mcpl.gz')])
testtool([test_data_dir.joinpath('ref','reffile_empty.mcpl')])
testtool([test_data_dir.joinpath('ref','reffile_truncated.mcpl')])
testtool([test_data_dir.joinpath('ref','reffile_truncated.mcpl.gz')])
testtool([test_data_dir.joinpath('ref','reffile_encodings.mcpl.gz'),'-basciidata'])
testtool([test_data_dir.joinpath('ref','reffile_encodings.mcpl.gz'),'-butf8data'])

@contextlib.contextmanager
def stdout_buffer_write_hexvalues():
    #Hack needed to prevent the nasty stuff inside the "binarydata" blob cause
    #test irreproducibilities (seen in a particular github workflow).
    import sys
    _orig_buffer_write = sys.stdout.buffer.write
    def bufwrite( b ):
        b = b.replace(b'\r\n',b'\n')#dos2unix
        res = b''
        for e in b:
            res += hex(e).encode('ascii')
        _orig_buffer_write(res)
    try:
        flush()
        sys.stdout.buffer.flush()
        sys.stdout.buffer.write = bufwrite
        yield
    finally:
        sys.stdout.buffer.write = _orig_buffer_write
        sys.stdout.buffer.flush()
        flush()

with stdout_buffer_write_hexvalues():
    testtool([test_data_dir.joinpath('ref','reffile_encodings.mcpl.gz'),
              '-bbinarydata'])

testtool([test_data_dir.joinpath('ref','reffile_empty.mcpl'),'--stats'])
testtool([test_data_dir.joinpath('ref','reffile_uw.mcpl.gz'),'--stats'])
testtool([file1,'--stats'])
testtool([file3,'--stats'])

def loadbad(fn):
    try:
        mcpl.MCPLFile(fn)
    except mcpl.MCPLError as e:
        print(f'MCPL ERROR: {e!s}')
    except OSError as e:
        print(e)
loadbad('notfound.mcpl')
loadbad('bla.txt')
loadbad(123)
loadbad(None)
for bf in badfiles:
    loadbad(bf)

from numpy import asarray as np_asarray # noqa E402

for fn in (file1,file2,file3):
    print ("---> testing array access")
    with mcpl.MCPLFile(fn,blocklength=2) as f:
        for p in f.particles:
            assert (p.position==np_asarray((p.x,p.y,p.z))).all()
            assert (p.direction==np_asarray((p.ux,p.uy,p.uz))).all()
            assert (p.polarisation==np_asarray((p.polx,p.poly,p.polz))).all()
            print('position: ({:g}, {:g}, {:g}), {}, {}, ({:g}, {:g}, {:g})'.format(p.x,p.y,p.z,npfmt(p.position),
                   str(type(p.position)).replace('class','type'),p.position[0],p.position[1],p.position[2]))
            print('polarisation: ({:g}, {:g}, {:g}), {}, {}, ({:g}, {:g}, {:g})'.format(p.polx,p.poly,p.polz,npfmt(p.polarisation),
                   str(type(p.polarisation)).replace('class','type'),p.polarisation[0],p.polarisation[1],p.polarisation[2]))
            print('direction: ({:g}, {:g}, {:g}), {}, {}, ({:g}, {:g}, {:g})'.format(p.ux,p.uy,p.uz,npfmt(p.direction),
                   str(type(p.direction)).replace('class','type'),p.direction[0],p.direction[1],p.direction[2]))

with mcpl.MCPLFile(file1,blocklength=3) as f:
    print(f.sourcename)
    print(f.blocklength)
    for i,c in enumerate(f.comments):
        print(f"comment #{i}: {c}")
    assert set(f.blobs.keys()) == set(f.blob_storage_order)
    print(','.join(f'{k}[{len(f.blobs[k])}]' for k in f.blob_storage_order))

    print('indices in file: {}'.format(','.join(str(p.fileidx) for p in f.particles)))
    for ib,pb in enumerate(f.particle_blocks):
        pb.uy if ib%2 else pb.uz
        assert pb[len(pb)] is None
        print(f'indices in block starting at {pb.file_offset} a:',
              ','.join( str(pb[i].fileidx) for i in range(len(pb)) ))
        print(f'indices in block starting at {pb.file_offset} b:',
              ','.join( str(p.fileidx) for p in pb.particles ))
    f.rewind()
    p=f.read()
    assert p.fileidx==0
    f.skip_forward(1)
    p=f.read()
    assert p.fileidx==2
    f.skip_forward(1)
    p=f.read()
    assert p.fileidx==4
    f.rewind()
    f.skip_forward(4)
    p=f.read()
    assert p.fileidx==4
    try:
        f.skip_forward(-1)
        p=f.read()
    except mcpl.MCPLError as e:
        print(str(e))
    f.skip_forward(999999)
    p=f.read()
    assert p is None

def tostr(a):
    """convert bytes/unicode to str in both py2 or py3 (assuming ascii chars
    only). Other objects are simply converted via str(..)."""
    #the amount of bullshit we have to deal with in order to support both py2
    #and py3 is rather wild...
    if isinstance(a,str):
        return a#bytes in py2, unicode in py3
    elif isinstance(a,bytes):
        return a.decode('ascii')#got bytes in py3
    elif str==bytes and isinstance(a,unicode): #noqa F821 ("unicode" not in py3)
        return a.encode('ascii')#got unicode in py2
    else:
        return str(a)#neither str/bytes/unicode

def test_stats(*args,**kwargs):
    def fmtkw(k,v):
        return f'{tostr(k)}={[tostr(e) for e in v] if isinstance(v,list) else tostr(v)}'
    print('======================> Test stats({})'.format(','.join([tostr(a) for a in ['MCPLFILE' if isinstance(args[0],mcpl.MCPLFile) else os.path.basename(args[0])]
                    +list(args[1:])]+[fmtkw(k,v) for k,v in sorted(kwargs.items())])))
    try:
        stats=mcpl.collect_stats(*args,**kwargs)
        if stats!={}:
            mcpl.dump_stats(stats)
    except mcpl.MCPLError as e:
        print(f'MCPL ERROR: {e}')
        return {}
    return {}

test_stats(file1,stats='all',bin_data=True)
test_stats(mcpl.MCPLFile(file1,blocklength=1),stats='all',bin_data=False)



fewstats=test_stats(test_data_dir.joinpath('ref','reffile_userflags_is_pos.mcpl.gz'),
                    stats=['polx','userflags'],bin_data=True)
test_stats(file1,stats=['userflags'],bin_data=True)

test_stats(test_data_dir.joinpath('ref','reffile_empty.mcpl'),
           stats=['x','y'],bin_data=True)

try:
    mcpl.plot_stats(fewstats,filename='lala.pdf')
except mcpl.MCPLError as e:
    print(f'plot_stats: {e}')
test_stats(test_data_dir.joinpath('ref','reffile_uw.mcpl.gz'))
test_stats(file1,stats=[])
test_stats(file1,stats=['blabla'])
test_stats(test_data_dir.joinpath('ref','miscphys.mcpl.gz'))
