
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

# Test histograms (mcpl.histogram, mcpl.histogram2d, mcpl.plot_histograms)
# and mcpltool --hist, using the plotting backend
# for tests (which prints descriptions of the figures).

import contextlib
import io
import pathlib
import shutil

import mcpldev as mcpl
import numpy as np
from MCPLTestUtils.dirs import test_data_dir

#Use local copies of the files, for printouts without full paths:
shutil.copy(test_data_dir.joinpath('example.mcpl'),'example.mcpl')
shutil.copy(test_data_dir.joinpath('ref','reffile_1.mcpl'),'reffile_1.mcpl')
example_file = pathlib.Path('example.mcpl')
ref1 = pathlib.Path('reffile_1.mcpl')
def show(obj):
    figs = obj if isinstance(obj,list) else [ obj.figure() ]
    mcpl.plotting.show(figs, backend='test')

def test_histograms():
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    h = mcpl.histogram(example_file, 'ekin/MeV', logx=True, split='pdgcode')
    show(h)
    assert np.isclose(sum(c.sum() for c in h.contents.values()), b.weight.sum())
    h = mcpl.histogram(example_file, 'ekin/eV', pick='pdgcode == neutron',
                       lethargy=True, bins=20)
    show(h)
    ref = np.histogram(b.ekin[b.pdgcode==2112]*1e6, bins=h.edges)[0]
    assert np.allclose(h.contents[None], ref)
    assert np.allclose(h.values(), ref/np.log(h.edges[1:]/h.edges[:-1]))
    print(h.to_text())
    h = mcpl.histogram(example_file, 'acos(uz)/deg', range=(0,90), bins=9,
                       split='x > 0cm', unweighted=True)
    show(h)
    print(h.to_text())
    h = mcpl.histogram([example_file, ref1], 'x/cm', range=(-20,20), bins=8)
    show(h)
    print('underflow:', h.underflow, 'overflow:', h.overflow)
    h = mcpl.histogram(example_file, 'pdgcode', split='pdgcode', max_curves=3,
                       range=(-300,2300), bins=26)
    show(h)
    h = mcpl.histogram2d(example_file, 'x/cm', 'y/cm', bins=10,
                         pick=mcpl.ParticleFilter('pdgcode == gamma'))
    show(h)
    assert np.isclose(h.contents.sum(), np.count_nonzero(b.pdgcode==22))
    #No selected particles, but a range (so an empty histogram), with splits:
    for split in ('pdgcode', 'x > 0cm'):
        h = mcpl.histogram(example_file, 'ekin/MeV', pick='x > 1km',
                           range=(0,10), bins=2, split=split)
        print(f'empty histogram with split={split!r}:', h.to_text())
    for args, kwargs in ( (('ekin',),{}), (('ekin/MeV',),{'pick':'x > 1km'}),
                          (('x/cm',),{'logx':True,'range':(-1,1)}),
                          (('wavelength',),{}), (('x/cm',),{'split':'x'}) ):
        try:
            mcpl.histogram(example_file, *args, **kwargs)
            print(f'histogram{args} {kwargs}: no error')
        except mcpl.MCPLError as e:
            print(f'histogram{args} {kwargs}: {e}')

def test_overlay():
    hn = mcpl.histogram(example_file, 'ekin/MeV', pick='pdgcode == neutron',
                        logx=True, bins=10)
    hg = mcpl.histogram(example_file, 'ekin/MeV', pick='pdgcode == gamma',
                        logx=True, bins=10)
    mcpl.plot_histograms([hn,hg], overlay=True, backend='test', logy=True)
    mcpl.plot_histograms([hn,hg], overlay=True, labels=['n','g'], backend='test')
    files = mcpl.plot_histograms([hn,hg], filename='hists.txt', backend='test')
    print(f'plot_histograms without overlay created {files}')
    h2 = mcpl.histogram([example_file, ref1], 'x/cm', range=(-20,20), bins=4)
    mcpl.plot_histograms([h2,hn], overlay=True, backend='test')
    for args, kwargs in ( ( [], {} ),
                          ( [hn, mcpl.histogram2d(example_file,'x/cm','y/cm')], {} ),
                          ( [hn, hg], {'labels':['a']} ) ):
        try:
            mcpl.plot_histograms(args, overlay=True, backend='test', **kwargs)
        except mcpl.MCPLError as e:
            print(f'plot_histograms(overlay=True) with {len(args)} histograms {kwargs}: {e}')

def test_autobins():
    #Without bins, the number of bins follows from the effective number of
    #entries (square root, clamped to [10,400]), after histogramming with many
    #bins which are then merged exactly:
    from mcpldev._histogram import _auto_nbins, _nice_nbins
    print('nice numbers of bins:',[ (m,_nice_nbins(m)) for m in (1200,400,239,83,37,15,8) ])
    for neff in (1, 100, 1000, 1e4, 1e5, 1e6):
        print(f'neff={neff:g}: bins of 1080 -> {_auto_nbins(neff,1080)},'
              f' of 216 -> {_auto_nbins(neff,216)}, 2D of 216 -> {_auto_nbins(neff,216,2)}')
    #Sanity of the choices for all plot widths and a range of statistics: the
    #bins merge exactly, few columns are unused, and the number of bins is
    #close to the target unless the plot is too narrow for it:
    import math
    stats, nbad = [], 0
    for ncols in [None] + list(range(29,240)):
        nb = _nice_nbins(1200 if ncols is None else ncols)
        for neff in (1,3,10,30,100,300,1e3,3e3,1e4,3e4,1e5,1e6,1e8):
            n = _auto_nbins(neff,nb)
            target = max(10,min(400,round(math.sqrt(neff))))
            unused = 0.0 if ncols is None else ( ncols - nb ) / ncols
            capped = ( n == nb )#(every column used, narrow plot)
            ratio = n / target
            ok = ( nb % n == 0 and ( ncols is None or nb <= ncols ) and unused <= 0.15
                   and ( capped or 0.6 <= ratio <= 1.5 ) )
            nbad += ( not ok )
            stats.append((ratio,unused,capped))
    print(f'{len(stats)} (ncols,neff) cases, {nbad} bad, ratio to target'
          f' {min(r for r,_,c in stats if not c):.2f}..{max(r for r,_,c in stats if not c):.2f}'
          f' when not capped, {sum(c for _,_,c in stats)} capped by narrow plots,'
          f' at most {100*max(u for _,u,_ in stats):.0f}% unused columns')
    h = mcpl.histogram(example_file, 'x/cm')
    hf = mcpl.histogram(example_file, 'x/cm', bins=1080)
    v, vf = h.values(), hf.values()
    print(f'auto: {len(h.edges)-1} bins, sum {v.sum():g} (1080 bins: {vf.sum():g}),'
          f' merged exactly: {np.allclose(v,vf.reshape(len(v),-1).sum(axis=1))},'
          f' same edges: {np.allclose(h.edges,hf.edges[::1080//len(v)])},'
          f' for display: {h._display_bins}')
    h = mcpl.histogram(example_file, 'x/cm', pick='pdgcode == 2212')
    print(f'auto with few particles: {len(h.edges)-1} bins, sum {h.values().sum():g}')
    h = mcpl.histogram(example_file, 'x/cm', _maxbins=83)
    print(f'auto with at most 83 bins: {len(h.edges)-1} bins, for display: {h._display_bins}')
    h = mcpl.histogram2d(example_file, 'x/cm', 'y/cm')
    print(f'auto 2D: {h.contents.shape} bins, sum {h.contents.sum():g},'
          f' for display: {h._display_bins}')
    h = mcpl.histogram2d(example_file, 'x/cm', 'y/cm', _maxbins=(69,15))
    print(f'auto 2D with at most (69,15) bins: {h.contents.shape} bins,'
          f' sum {h.contents.sum():g}, for display: {h._display_bins}')
    h = mcpl.histogram2d(example_file, 'x/cm', 'y/cm', bins=(8,4))
    print(f'2D with bins=(8,4): {h.contents.shape} bins, for display: {h._display_bins}')

def tool(*args):
    out = io.StringIO()
    rc = 0
    with contextlib.redirect_stdout(out):
        try:
            mcpl.app_mcpltool(['mcpltool',*args])
        except SystemExit as e:
            rc = e.code
    print(f'mcpltool {" ".join(args)}: exit code {rc}')
    for line in out.getvalue().splitlines():
        print(f'   | {line}')

def test_cmdline():
    ex = str(example_file)
    tool('-H','ekin/MeV;logx=1;split=pdgcode','-B','test',ex)
    tool('-H','ekin/eV;lethargy=1;bins=5;print=1','-p','pdgcode == neutron',ex)
    tool('-H','x/cm : y/cm;bins=4;print=1','-p','pdgcode == gamma',ex)
    tool('-H','x/cm:y/cm;bins=2;xrange=-10:10;yrange=0:5;print=1',ex)
    tool('-H','x/cm : y/cm;bins=2;xrange=-10:10;print=1',ex)
    tool('-H','x/cm : y/cm;bins=3,2;print=1',ex)
    tool('-H','x/cm;range=-10:10;bins=4','-B','test',ex,str(ref1))
    tool('-H','time/ms;logx=1;logy=1;unweighted=1','-B','test',ex)
    tool('-H','ekin/MeV;split=pdgcode;range=0:10;bins=2;print=1',
         '-p','x > 1km',ex)
    #-l, -s and -E (the particles are picked before they are edited):
    tool('-H','z/cm;bins=2;range=0:100;print=1','-s1000',ex)
    tool('-H','z/cm;bins=2;range=0:100;print=1','-l3','-E','z += 50cm',ex)
    tool('-H','z/cm;bins=2;range=0:100;print=1','--pick=z < 25cm',
         '--edit=z += 50cm',ex)
    tool('-Hekin/MeV;print=1;bins=2','-ppdgcode==22',ex)
    for bad in ( ['-H','ekin',ex], ['-H','ekin/MeV;bins=0',ex],
                 ['-H','ekin/MeV;range=1',ex], ['-H','ekin/MeV;range=2:1',ex],
                 ['-H','ekin/MeV;range=1:2,3:4',ex], ['-H','ekin/MeV;xrange=1:2',ex],
                 ['-H','x/cm : y/cm;range=1:2',ex],
                 ['-H','x/cm : y/cm;logx=1',ex], ['-H','x/cm : y/cm : z/cm',ex], ['-H','x : y : z : x',ex], ['-H','x : y : z;bins=5',ex],
                 ['-H','x/cm;bins',ex], ['-H','x/cm;logx',ex], ['-H','x/cm;logx=true',ex],
                 ['-H','x/cm;logy=yes',ex], ['-H','x/cm;logx=2',ex], ['-H','x/cm;logy=auto',ex],
                 ['-H','x/cm;logx=1;logx=1',ex], ['-H','x/cm;foo',ex],
                 ['-H','x/cm','-B','foo',ex], ['--logx',ex], ['--bins','10',ex],
                 ['-o','a.pdf',ex], ['-H','x/cm','-e',ex,'out.mcpl'],
                 ['-H','x/cm'], ['-H','x/cm;print=1','-t',ex],
                 #(logx=auto: logarithmic for positive values over more than
                 #two decades, else linear):
                 ['-H','ekin/MeV;logx=auto;bins=3;print=1',ex], ['-H','x/cm;logx=auto;bins=3;print=1',ex],
                 ['-H','ekin/MeV;logx=auto;range=1:10;bins=3;print=1',ex],
                 ['-H','x/cm','-t','-o','a.txt',ex] ):
        tool(*bad)

def test_cmdline_more():
    #Statistics, saving files with the test backend (which describes the
    #figures), several histograms, and argument errors:
    ex = str(example_file)
    tool('-S','-o','stats.txt','-B','test','-p','pdgcode == gamma',ex)
    tool('-S','-s1000','-E','x = 1cm',ex)
    tool('-H','x/cm;bins=3','-o','hist.txt','-B','test',ex)
    tool('-H','x/cm;bins=2;print','-H','pdgcode;bar=2;print',ex)
    tool('-H','x/cm;bins=3','-H','pdgcode;bar','-o','twohists.txt','-B','test',ex)
    for bad in ( ['-p','neutron',ex], ['-p2112',ex], ['-p',' gamma ',ex],
                 ['-p'], ['-lX',ex], ['-l',ex],
                 ['-p','x > 0','-p','x < 1cm',ex], ['--pdf',ex], ['--gui',ex],
                 ['--select','x > 0',ex], ['-S','-B','test',ex], ['-S','-t',ex],
                 ['-S','-H','x/cm',ex], [ex,ex,ex],
                 ['--text',ex], ['--text',ex,'hist.txt'],
                 ['-t',ex], ['-j','-H','x/cm',ex], ['--no-comment','-S',ex],
                 ['-H','x/cm : y/cm;split=pdgcode',ex],
                 ['-H','x/cm','-o','hist.txt','-B','test',ex],
                 ['-H','x/cm','-o','hist',ex], ['-H','x/cm','-o','hist.jpg',ex],
                 ['-H','x/cm','-o','hist.png','-d',ex],
                 ['-p','x = 1cm; x > 0',ex], ['-p','x > "1"',ex], ['-E','z = 1cm, x = 0',ex] ):
        tool(*bad)

def test_help_topics():
    #Only the start of each topic (the rest are tables of all names):
    for args in ( ['-p','help'], ['--edit=help'], ['-H','help',str(example_file)] ):
        out = io.StringIO()
        rc = 0
        with contextlib.redirect_stdout(out):
            try:
                mcpl.app_mcpltool(['mcpltool',*args])
            except SystemExit as e:
                rc = e.code
        lines = out.getvalue().splitlines()
        print(f'mcpltool {" ".join(args)}: exit code {rc}, {len(lines)} lines,'
              ' starting with:')
        for line in lines[:3]:
            print(f'   | {line}')

def test_units():
    ex = 'example.mcpl'
    #Expressions with units get a unit chosen for their axes (see _plot_unit):
    from mcpldev._exprplot import _plot_unit
    for what, args in ( ( 'x, 0.3m', ((1,0,0),-30,30) ), ( 'x, 2.5m', ((1,0,0),0,250) ),
                        ( 'x, 5mm', ((1,0,0),0,0.5) ), ( 'ekin, 9.7GeV', ((0,1,0),0.0014,9725) ),
                        ( 'ekin, log axis', ((0,1,0),1e-9,10,True) ), ( 'time, log axis', ((0,0,1),1e-6,1e-3,True) ),
                        ( 'x^2', ((2,0,0),0,1e4) ), ( 'sqrt(ekin)', ((0,0.5,0),0,1e-3) ),
                        ( 'x*ekin', ((1,1,0),0,10) ), ( '1/x', ((-1,0,0),0,0.5) ),
                        ( 'wavelength, 1.8Aa', ((1,0,0),1e-8,1.8e-8,False,True) ),
                        ( 'wavelength, log axis 1e-3 to 100Aa', ((1,0,0),1e-11,1e-6,True,True) ),
                        ( 'wavelength, up to 1mm', ((1,0,0),0,0.1,False,True) ), ( 'no units', (None,0,1) ) ):
        print(f'unit of {what}: {_plot_unit(*args)}')
    for e, kw in ( ( 'x', {} ), ( 'ekin;logx=auto', {} ), ( 'wavelength', { 'pick' : 'pdgcode == neutron' } ),
                   ( 'x;range=-10cm:10cm;bins=2', {} ), ( 'x;range=0:1m;bins=2', {} ), ( 'x/cm;bins=2', {} ),
                   ( 'hypot(x,y)', {} ) ):
        h = mcpl.histogram(ex,e,**kw)
        print(f'histogram({e!r}): label {h.label!r}, edges from {h.edges[0]:.4g} to {h.edges[-1]:.4g}')
    h = mcpl.histogram2d(ex,'x','ekin/MeV',bins=2)
    print('histogram2d(x, ekin/MeV):', h.to_text().splitlines()[0])
    for e in ( 'x;range=-10:10', 'x/cm;range=-10cm:10cm', 'ekin;range=0cm:1cm', 'x;range=1cm', 'x;range=y:1cm' ):
        try:
            mcpl.histogram(ex,e)
        except mcpl.MCPLError as err:
            print(f'histogram({e!r}): {err}')

def test_bars_groups_domains():
    ex = 'example.mcpl'
    #Bars of distinct values, split groups, and expressions which are only
    #defined for some particles (wavelengths):
    for e, kw in ( ( 'pdgcode;bar=auto', {} ), ( 'pdgcode;bar=3', {} ),
                   ( 'mod(pdgcode,7);bar=auto;unweighted=1', {} ), ( 'pdgcode', { 'bar' : 2 } ),
                   ( 'pdgcode;bar=auto', { 'pick' : 'pdgcode != neutron' } ),
                   ( 'round(x/10cm);bar=4;logy=1', {} ), ( 'mod(floor(ekin/MeV),3);bar=auto;logy=0', {} ) ):
        h = mcpl.histogram(ex,e,**kw)
        print(f'histogram({e!r},{kw}):')
        print(h.to_text())
        show(h)
    h = mcpl.histogram(ex,'ekin/MeV;split=pdgcode;groups=3;bins=3')
    print('split with groups=3:', list(h.contents), h.colors)
    h = mcpl.histogram(ex,'ekin/MeV',split='pdgcode',max_curves=4,bins=3)
    print('split with max_curves=4:', list(h.contents), h.colors)
    for e, kw in ( ( 'wavelength;bins=3', {} ), ( 'wavelength;bins=3', { 'pick' : 'pdgcode == neutron' } ),
                   ( 'wavelength;split=pdgcode;bins=3', {} ), ( 'round(1000*wavelength/Aa);bar=auto', { 'pick' : 'ekin > 1GeV' } ) ):
        h = mcpl.histogram(ex,e,**kw)
        print(f'histogram({e!r},{kw}): label {h.label!r}, contents {[ float(np.sum(c)) for c in h.contents.values() ]}')
    h = mcpl.histogram2d(ex,'wavelength','x',bins=2)
    print('histogram2d(wavelength,x):', h.xlabel, '|', h.ylabel, '|', h.contents.sum())
    for e, kw in ( ( 'x;bar=auto', {} ), ( 'pdgcode;bar=1', {} ), ( 'pdgcode;bar=on', {} ),
                   ( 'pdgcode;bar=auto;logx=1', {} ), ( 'pdgcode;bar=auto;split=pdgcode', {} ),
                   ( 'x:y;bar=auto', {} ), ( 'ekin/MeV;groups=3', {} ), ( 'ekin/MeV;split=pdgcode;groups=1', {} ),
                   ( 'pdgcode', { 'bar' : 1 } ), ( 'pdgcode', { 'bar' : 'auto' } ),
                   ( 'pdgcode;bar=auto', { 'bar' : 4 } ), ( 'pdgcode', { 'bar' : True, 'logx' : True } ),
                   ( 'ekin/MeV;bar=auto', {} ), ( 'round(x);bar=auto', {} ),
                   ( 'round(1e300*x/cm);bar=auto', {} ) ):
        try:
            mcpl.histogram(ex,e,**kw)
            print(f'histogram({e!r},{kw}): no error')
        except mcpl.MCPLError as err:
            print(f'histogram({e!r},{kw}): {err}')

def test_ranges_colors():
    from mcpldev._histogram import _nice_range, _value_colors
    from mcpldev.plotting import _line_style
    #Automatic ranges of linear axes: from 0 if the values are close enough
    #to it, and to round values (adding at most 7.5% to the range):
    for lo, hi in ( (0.3,20.5), (-20.5,-0.3), (-9.83,10.21), (1012.3,1077.9),
                    (0.001234,0.0098), (3,4), (-0.99,0.999), (1e-9,3.3e-7),
                    (0.1,0.30000000000000004), (2.2,7.7), (123456.7,123499.1) ):
        nlo, nhi = _nice_range(lo,hi)
        assert nlo <= lo and nhi >= hi
        assert ( nhi - nlo ) <= 1.075 * ( max(hi,0) - min(lo,0) )
        print(f'range of values from {lo:g} to {hi:g}: {nlo:g} to {nhi:g}')
    #Colours of particle types: fixed ones, and the others get the unused
    #colours (cyan first, and never those of n, gamma, e- and p), and then
    #those of the next cycles (with dashed lines):
    keys = [ 2112, 22, 12, 14, 'other' ]
    print('colours of', keys, _value_colors('pdgcode',keys))
    keys = [ 2112, 22, 11, -11, 2212, 211, -211, 13, -13, 12, 14, 16, 321, 'other' ]
    cols = _value_colors('pdgcode',keys)
    print('colours of', keys, cols, [ _line_style(cols[k]) for k in keys ][-5:])
    print('line styles:', [ _line_style(c) for c in ( 0, 9, 10, 19, 20, 30 ) ])

def test_3d():
    #3D plots of a sample of the particles (the same for the same particles):
    from mcpldev._plotbackend_test import describe
    ex = str(example_file)
    h = mcpl.histogram(ex,'x : y : z;points=100')
    print('3D:', type(h).__name__, { k : v.shape for k, v in h.groups.items() }, h.labels,
          h.nparticles)
    same = mcpl.histogram(ex,'x : y : z;points=100')
    print('same sample:', np.array_equal(h.groups[None],same.groups[None]))
    h = mcpl.histogram(ex,'ux : uy : uz;split=pdgcode;groups=3',pick='ekin > 1keV')
    print('split:', { k : len(v) for k, v in h.groups.items() }, h.colors)
    print(describe([ h.figure() ]))
    print(h.to_text().splitlines()[:4])
    h = mcpl.histogram(ex,'x : y : z;unweighted;points=5000')
    print('more points than particles:', len(h.groups[None]), 'of', h.nparticles)

def test_logz():
    #The colour scale of 2D histograms is logarithmic unless logz=0, which
    #makes another plot (logz and logz=1 make the same as without logz):
    from mcpldev._histstring import _hist_key
    ex = str(example_file)
    for text in ( 'x : y', 'x : y;logz', 'x : y;logz=0' ):
        h = mcpl.histogram(ex,text)
        print(f'{text!r}: logz {h.logz}, panel {h.panel().items[0].logz},'
              f' key {_hist_key(text)!r}')
    print('panel(logz=False) of the default:', mcpl.histogram(ex,'x : y').panel(logz = False).items[0].logz)
    for bad in ( 'x;logz=0', 'x : y : z;logz', 'x : y;logz=2' ):
        try:
            mcpl.histogram(ex,bad)
        except mcpl.MCPLError as e:
            print(f'{bad!r}: {e}')

def test_equal():
    #Equal scales of the axes of 2D histograms with the same units, also when
    #they are shown in different units (as cm and mm):
    from mcpldev._plotbackend_test import describe
    ex = str(example_file)
    for text in ( 'x : y;equal', 'x : 0.02*y;equal', 'ux : uy;equal', 'x : y' ):
        h = mcpl.histogram(ex,text)
        print(f'{text!r}: aspect {h.aspect} ({h.xunit}, {h.yunit}), panel {h.panel().aspect}')
    print(describe([ mcpl.histogram(ex,'x : y;equal').figure() ]).splitlines()[1])
    for bad in ( 'x : ekin;equal', 'x;equal', 'x : y : z;equal' ):
        try:
            mcpl.histogram(ex,bad)
        except mcpl.MCPLError as e:
            print(f'{bad!r}: {e}')

test_logz()
test_equal()
test_3d()
test_ranges_colors()
test_units()
test_bars_groups_domains()
test_histograms()
test_overlay()
test_cmdline()
test_cmdline_more()
test_help_topics()
test_autobins()
