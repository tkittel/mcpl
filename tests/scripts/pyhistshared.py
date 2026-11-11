
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

# Test the sharing of the distinct values of display_by between the fillers
# filling from the same block (see _histfill._SharedKeys): the histograms are
# the same as when filled without sharing (for all kinds of fillers, block
# sizes, and two files), and the parts are tested directly (the cache of
# _SharedKeys, and _DisplayByValue.block_keys against np.unique of the values
# of the particles kept, also with NaN values, masks keeping some or none of
# the particles, and too many distinct values).

import shutil

import mcpldev as mcpl
import numpy as np
from mcpldev._common import MCPLError
from mcpldev._histfill import _DisplayByValue, _filler_for, _SharedKeys
from mcpldev._histstring import _parse_hist
from MCPLTestUtils.dirs import test_data_dir

shutil.copy(test_data_dir.joinpath('example.mcpl'),'example.mcpl')

def blocks( fn, blocklength ):
    """Independent copies of the blocks of the file (the blocks of an MCPLFile
    are only valid until the next one is read)"""
    with mcpl.MCPLFile(fn,blocklength=blocklength) as f:
        return [ b[np.arange(len(b))] for b in f.particle_blocks ]

def flat( o ):
    """All data of a result, as a structure which can be compared"""
    if isinstance(o,np.ndarray):
        return ( o.dtype.str, o.shape, o.tobytes() )
    if isinstance(o,dict):
        return tuple(sorted( ( repr(k), flat(x) ) for k, x in o.items() ))
    if isinstance(o,( list, tuple )):
        return tuple( flat(x) for x in o )
    if hasattr(o,'__dict__'):
        return ( type(o).__name__, flat(vars(o)) )
    return repr(o)

def fill( plots, files, shared ):
    """The results of the plots, filled from the blocks of the files (label,
    blocks), all plots from each block (sharing if shared is set)"""
    labels = [ lbl for lbl, _ in files ] if len(files) > 1 else None
    fillers = [ _filler_for(_parse_hist(p),**( { 'labels' : labels } if labels else {} ))
                for p in plots ]
    flabel = ( lambda lbl : lbl ) if labels else ( lambda lbl : None )
    for lbl, bl in files:
        for b in bl:
            for h in fillers:
                if h.needs_range:
                    h.add_range(flabel(lbl),b)
    for h in fillers:
        if h.needs_range:
            h.start_fill()
    for lbl, bl in files:
        for b in bl:
            s = _SharedKeys() if shared else None
            for h in fillers:
                h.add(flabel(lbl),b,s)
    return [ h.result() for h in fillers ]

print('Histograms filled with and without sharing:')
plots = [ 'ekin;display_by=pdgcode;logx',
          'ekin/MeV;display_by=pdgcode;lethargy',
          #(only defined for some particles, so with fewer types in some blocks):
          'wavelength;display_by=pdgcode',
          #(a condition, and the same plot twice):
          'time;display_by=uz>0', 'time;display_by=uz>0',
          #(another expression of display_by, and a range):
          'x;display_by=userflags;range=-10cm:10cm',
          #(edited particles, which do not share):
          'ekin;display_by=pdgcode;display_edit=pdgcode==gamma',
          #(plots without display_by, and other kinds of fillers):
          'ekin', 'pdgcode', 'x:y', 'x:y:z;display_by=pdgcode' ]
for blocklength in ( 1, 7, 50, 10000 ):
    files = [ ( None, blocks('example.mcpl',blocklength) ) ]
    a, b = fill(plots,files,True), fill(plots,files,False)
    same = [ flat(x) == flat(y) for x, y in zip(a,b) ]
    print(f'  blocks of {blocklength} particles: {sum(same)} of {len(same)} the same')
    assert all(same)
#(the same file twice, with other blocks):
files = [ ( 'a', blocks('example.mcpl',100) ), ( 'b', blocks('example.mcpl',3) ) ]
a, b = fill(plots,files,True), fill(plots,files,False)
same = [ flat(x) == flat(y) for x, y in zip(a,b) ]
print(f'  two files: {sum(same)} of {len(same)} the same')
assert all(same)

print('The distinct values are found once per block and expression:')
bl = blocks('example.mcpl',100)
d1, d2, d3 = _DisplayByValue('pdgcode'), _DisplayByValue('pdgcode'), _DisplayByValue('uz>0')
s = _SharedKeys()
k1 = s.distinct(d1,bl[0])
print('  same expression, same block: reused', s.distinct(d2,bl[0]) is k1)
print('  other expression: not reused', s.distinct(d3,bl[0]) is not k1)
print('  other block: not reused', s.distinct(d1,bl[1]) is not k1)
assert s.distinct(d2,bl[0]) is k1 and s.distinct(d3,bl[0]) is not k1

class Values(_DisplayByValue):
    """display_by with given values (the same for any block)"""
    def __init__( self, values ):
        super().__init__('pdgcode')
        self._values = np.asarray(values,dtype=float)
    def __call__( self, block ):
        return self._values

print('block_keys with sharing is keys() of the values kept:')
rng = np.random.default_rng(1)
cases = [ ( 'three values', rng.choice([22.0,2112.0,11.0],50) ),
          ( 'one value', np.full(50,2112.0) ),
          ( 'with NaN', np.where(rng.random(50) < 0.3,np.nan,rng.choice([1.0,2.0],50)) ),
          ( 'conditions', rng.choice([0.0,1.0],50) ) ]
masks = [ ( 'all', lambda n : np.ones(n,dtype=bool) ),
          ( 'none', lambda n : np.zeros(n,dtype=bool) ),
          ( 'some', lambda n : rng.random(n) < 0.5 ),
          ( 'first', lambda n : np.arange(n) == 0 ) ]
b = bl[0][np.arange(50)]
for name, values in cases:
    for mname, mask in masks:
        defined = mask(50)
        d_shared, d_plain = Values(values), Values(values)
        ks, ixs = d_shared.block_keys(b,defined,_SharedKeys())
        kp, ixp = d_plain.keys(values[defined])
        ok = ( ks.tobytes() == kp.tobytes() and np.array_equal(ixs,ixp)
               and d_shared._is_bool == d_plain._is_bool )
        print(f'  {name}, mask {mname}: {"same" if ok else "DIFFERENT"}'
              f' ({len(ks)} values, all 0 or 1: {d_shared._is_bool})')
        assert ok

print('Too many distinct values:')
values = np.arange(1500,dtype=float)
for what, fct in ( ( 'shared', lambda d : d.block_keys(bl[0][np.zeros(1500,dtype=int)],
                                                        np.ones(1500,dtype=bool),_SharedKeys()) ),
                   ( 'not shared', lambda d : d.keys(values) ) ):
    try:
        fct(Values(values))
        raise SystemExit('expected an error')
    except MCPLError as e:
        print(f'  {what}: {e}')
#(but not when the plot keeps at most 1000 of them):
keys, _ = Values(values).block_keys(bl[0][np.zeros(1500,dtype=int)],np.arange(1500) < 1000,_SharedKeys())
print(f'  shared, 1000 kept: {len(keys)} values')
