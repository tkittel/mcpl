
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

#Tests of per-particle userdata in the C API (MCPL format version 4).

import pathlib

import mcpldev as mcpl
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.loadlib import getlib

lib = getlib('userdata')

#(functions are given by name, since functions expected to fail are run in a
#subprocess, with arguments which must be picklable):

def call(fctname,*args):
    return getattr(lib,'mcpltest_ud_'+fctname)(*args)

def run(fctname,*args):
    print(flush=True,end='')
    call(fctname,*args)
    print(flush=True,end='')

def fail(fctname,*args):
    print(flush=True,end='')
    lib.run_fct_expected_to_fail(call,fctname,*args)
    print(flush=True,end='')

def test_layouts():
    print('=== Layouts')
    for layout in [ 'data:uint8[27]', 'a:int8', 'temp:float32,origin:int32',
                    'p:uint8[65535]', 'v:float64[3]', 'a_1:int16,b2:uint16[2]',
                    'p:int64,q:uint64,r:float32[1],w:uint32' ]:
        run('layout',layout)
    for layout in [ '', 'uint8', 'uint8[27]', 'float64[3]', 'p', 'p:', ':int8', 'X:int8', '1x:int8',
                    'p-q:int8', 'p:int9', 'p:int8,', ',p:int8',
                    'p:int8,,q:int8', 'p:int8,p:int16', 'p:int8,uint8',
                    'uint8,p:int8', 'p:int8[0]', 'p:int8[03]', 'p:int8[]',
                    'p:int8[3', 'p:int8[a]', 'p:int8[3]q', 'p:uint8[65536]',
                    'p:uint8[65535],q:int8', 'p:float64[8192]',
                    'p :int8', 'p:int8, q:int8', 'a'*65 + ':int8',
                    'x:float32', 'a:int8,ekin:float64', 'position:float32[3]',
                    'wavelength:float32', 'userflags:uint32' ]:
        fail('layout',layout)
    run('layout','xx:float32,ekin2:float32,pos:int8')

def test_offsets():
    print('=== Offsets')
    lo = 'temp:float32,origin:int32,tags:uint8[3],big:float64'
    for name,tpe in [('temp','float32'),('origin','int32'),
                     ('tags','uint8[3]'),('big','float64')]:
        run('offset',lo,name,tpe)
    run('offset','data:uint8[27]','data','uint8[27]')
    for name,tpe in [('temp','float64'),('tags','uint8'),('tags','uint8[4]'),
                     ('nosuch','int8'),('<NULL>','float32')]:
        fail('offset',lo,name,tpe)
    fail('offset','data:uint8[27]','p','uint8[27]')
    fail('offset','p:int9','p','int9')

def test_write_read():
    print('=== Writing and reading')
    run('write','std.mcpl','<STD>',3,0)
    run('read','std.mcpl')
    run('write','stddp.mcpl','<STD>',3,3)
    run('read','stddp.mcpl')
    run('write','raw.mcpl','data:uint8[27]',4,4)#odd ones with zeros
    run('read','raw.mcpl')
    run('write','none.mcpl','<NONE>',2,0)
    run('read','none.mcpl')
    run('write','empty.mcpl','p:int8',0,0)
    run('read','empty.mcpl')
    run('write','big.mcpl','p:uint8[65535]',2,0)
    run('read','big.mcpl')
    #Same layouts but particle data written via raw bytes must be identical:
    run('dump','std.mcpl')
    run('dump','raw.mcpl')
    run('dump','big.mcpl')
    #(reading with the Python module is tested in pyuserdata.py):
    with mcpl.MCPLFile('std.mcpl') as f:
        print('Python module:',f.version,f.userdata_layout)

def test_text():
    print('=== Text export')
    for fn in ('std.mcpl','raw.mcpl'):
        run('text',fn,fn+'.txt')
        print(pathlib.Path(fn+'.txt').read_text(),end='')

def test_transfer():
    print('=== Transfers')
    run('transfer','std.mcpl','t1.mcpl','<META>',0)
    run('read','t1.mcpl')
    #with changed precision and polarisation (not just copying bytes):
    run('transfer','std.mcpl','t2.mcpl','<META>',3)
    run('read','t2.mcpl')
    run('transfer','stddp.mcpl','t3.mcpl','<STD>',0)
    run('read','t3.mcpl')
    #dropping the userdata:
    run('transfer','std.mcpl','t4.mcpl','<NONE>',0)
    run('read','t4.mcpl')
    #sources without userdata (or with different layouts) are errors for
    #targets with userdata:
    fail('transfer','none.mcpl','t5.mcpl','p:int16[2]',0)
    fail('transfer','std.mcpl','t6.mcpl','data:uint8[27]',0)
    #The header of an MCPL-3 file with blob keys which are not allowed in
    #MCPL-4 can be copied, but not to files with userdata (MCPL-4):
    enc = str(test_data_dir / 'ref' / 'reffile_encodings.mcpl.gz')
    run('transfer',enc,'t7.mcpl','<META>',0)
    print('Copied header with invalid blob keys from MCPL-3 file')
    run('transfer_meta_with_userdata','none.mcpl','t8.mcpl','p:int8')
    fail('transfer_meta_with_userdata',enc,'t9.mcpl','p:int8')

def test_merge():
    print('=== Merging')
    run('write','std2.mcpl','<STD>',2,0)
    run('write','raw27.mcpl','p:uint8[27]',2,0)
    #(same size as the standard layout):
    run('write','raw33.mcpl','data:uint8[33]',2,0)
    for f1,f2 in [('std.mcpl','std2.mcpl'),('std.mcpl','raw.mcpl'),
                  ('std.mcpl','raw33.mcpl'),('raw.mcpl','raw27.mcpl'),
                  ('std.mcpl','none.mcpl')]:
        print(f'can_merge({f1},{f2}) = {lib.mcpltest_ud_can_merge(f1,f2)}')
    run('merge','m1.mcpl','std.mcpl','std2.mcpl')
    run('read','m1.mcpl')
    fail('merge','m2.mcpl','std.mcpl','raw33.mcpl')
    run('merge_inplace','std2.mcpl','std.mcpl')
    run('read','std2.mcpl')
    fail('merge_inplace','std2.mcpl','raw33.mcpl')
    print('=== Forced merging')
    #same layouts but different precision (userdata kept):
    run('forcemerge','fm1.mcpl','std.mcpl','stddp.mcpl')
    run('read','fm1.mcpl')
    #different layouts with same size, or no userdata (userdata dropped):
    run('forcemerge','fm2.mcpl','std.mcpl','raw33.mcpl')
    run('read','fm2.mcpl')
    run('forcemerge','fm3.mcpl','none.mcpl','std.mcpl')
    run('read','fm3.mcpl')
    #empty files do not count:
    run('forcemerge','fm4.mcpl','empty.mcpl','raw.mcpl')
    run('read','fm4.mcpl')

def test_misuse():
    print('=== Misuse')
    for icase in range(5):
        fail('misuse',icase)
    run('misuse',5)

if __name__ == '__main__':
    test_layouts()
    test_offsets()
    test_write_read()
    test_text()
    test_transfer()
    test_merge()
    test_misuse()
