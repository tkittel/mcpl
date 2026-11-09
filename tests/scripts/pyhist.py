
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

# Test histograms: mcpl.histogram (its read-only results), the histograms with
# all their details and options (made as by mcpl.histogram and mcpltool, see
# _histfill), and mcpltool -H and -t, using the plotting backend for tests
# (which prints descriptions of the figures), and that plot_stats is no longer
# available.

import collections.abc
import contextlib
import io
import operator
import pathlib
import shutil

import matplotlib
import mcpldev as mcpl
import numpy as np
from mcpldev import _plotting
from mcpldev._plotregistry import _forced_backend
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.plots import (
    hist_figure,
    hist_panel,
    internal_histogram,
    internal_histogram2d,
)

#(no windows, also where there is a display, so plots which would be shown
#are drawn in the terminal instead):
matplotlib.use('agg')

#Use local copies of the files, for printouts without full paths:
shutil.copy(test_data_dir.joinpath('example.mcpl'),'example.mcpl')
shutil.copy(test_data_dir.joinpath('ref','reffile_1.mcpl'),'reffile_1.mcpl')
example_file = pathlib.Path('example.mcpl')
ref1 = pathlib.Path('reffile_1.mcpl')
#(the histograms with all their details, and the options also as keyword
#arguments, see internal_histogram):
def ihist( *args, **kwargs ):
    return internal_histogram(mcpl,*args,**kwargs)

def ihist2d( *args, **kwargs ):
    return internal_histogram2d(mcpl,*args,**kwargs)

def show(obj):
    figs = obj if isinstance(obj,list) else [ hist_figure(mcpl,obj) ]
    _plotting.show(figs)

def test_histograms():
    with mcpl.MCPLFile(example_file) as f:
        b = f.read_block()
    h = ihist(example_file, 'ekin/MeV', logx=True, display_by='pdgcode')
    show(h)
    assert np.isclose(sum(c.sum() for c in h.contents.values()), b.weight.sum())
    h = ihist(example_file, 'ekin/eV', edit='pdgcode == neutron',
                       lethargy=True, bins=20, display_by='single')
    show(h)
    ref = np.histogram(b.ekin[b.pdgcode==2112]*1e6, bins=h.edges)[0]
    assert np.allclose(h.contents[None], ref)
    assert np.allclose(h.values(), ref/np.log(h.edges[1:]/h.edges[:-1]))
    print(h.to_text())
    h = ihist(example_file, 'acos(uz)/deg', range=(0,90), bins=9,
                       display_by='x > 0cm', unweighted=True)
    show(h)
    print(h.to_text())
    h = ihist([example_file, ref1], 'x/cm', range=(-20,20), bins=8)
    show(h)
    print('underflow:', h.underflow, 'overflow:', h.overflow)
    #(at most 8 curves, the others combined into one):
    h = ihist(example_file, 'pdgcode', display_by='mod(fileidx,10)',
                       range=(-300,2300), bins=26)
    show(h)
    h = ihist2d(example_file, 'x/cm', 'y/cm', bins=10,
                         edit=mcpl.ParticleEdit('pdgcode == gamma'))
    show(h)
    assert np.isclose(h.contents.sum(), np.count_nonzero(b.pdgcode==22))
    #No selected particles, but a range (so an empty histogram), with splits:
    for split in ('pdgcode', 'x > 0cm'):
        h = ihist(example_file, 'ekin/MeV', edit='x > 1km',
                           range=(0,10), bins=2, display_by=split)
        print(f'empty histogram with display_by={split!r}:', h.to_text())
    for args, kwargs in ( (('ekin',),{}), (('ekin/MeV',),{'edit':'x > 1km'}),
                          (('x/cm',),{'logx':True,'range':(-1,1)}),
                          (('wavelength',),{}), (('x/cm',),{'display_by':'x'}),
                          #(the arguments bins and range):
                          (('x/cm',),{'bins':0}), (('x/cm',),{'bins':-3}), (('x/cm',),{'bins':2.5}),
                          (('x/cm',),{'bins':'x'}), (('x/cm',),{'bins':True}),
                          (('x/cm',),{'range':(5,1)}), (('x/cm',),{'range':(1,1)}),
                          (('x/cm',),{'range':(0,float('inf'))}), (('x/cm',),{'range':'a'}),
                          (('x/cm',),{'range':(1,2,3)}) ):
        try:
            ihist(example_file, *args, **kwargs)
            print(f'histogram{args} {kwargs}: no error')
        except mcpl.MCPLError as e:
            print(f'histogram{args} {kwargs}: {e}')
    for kwargs in ( {'bins':(5,0)}, {'bins':[3]}, {'xrange':(1,0)}, {'yrange':'a'} ):
        try:
            ihist2d(example_file, 'x/cm', 'y/cm', **kwargs)
            print(f'histogram2d {kwargs}: no error')
        except mcpl.MCPLError as e:
            print(f'histogram2d {kwargs}: {e}')
    h = ihist(example_file, 'x/cm', bins=np.int64(4), range=[-1,1])
    print('bins as a numpy integer, and range as a list:', len(h.edges)-1, h.edges[[0,-1]].tolist())

def test_plot_stats():
    try:
        mcpl.plot_stats(mcpl.collect_stats(example_file))
    except mcpl.MCPLError as e:
        print(f'plot_stats: {e}')

def test_public_api():
    #The results of mcpl.histogram: their data (in the units the expressions
    #give, else in those of MCPL), read-only, and plots without options:
    ex = str(example_file)
    with mcpl.MCPLFile(ex) as f:
        b = f.read_block()
    w = np.broadcast_to(b.weight,(len(b),))
    h = mcpl.histogram(ex, 'x/cm;range=-10:10;bins=4')
    ref = np.histogram(b.x, bins=h.edges, weights=w)[0]
    print(type(h).__name__, repr(h.expression), h.edges.tolist(), h.contents.tolist(),
          'as numpy:', np.allclose(h.contents, ref))
    for e in ( 'x;range=-0.1m:0.1m;bins=2', 'ekin;bins=2', 'ekin/keV;bins=2' ):
        print(f'edges of {e!r}:', mcpl.histogram(ex, e).edges.tolist())
    with mcpl.MCPLFile(ex, edit='x > 0cm') as f:
        h = mcpl.histogram(f, 'ekin/MeV;bins=5;display_by=pdgcode')
    print('contents of all curves, with an edit:', np.isclose(h.contents.sum(), w[b.x > 0].sum()),
          '| title:', repr(h._d.title))
    h2 = mcpl.histogram(ex, 'x/cm : y/cm;bins=3,2')
    print(type(h2).__name__, h2.expressions, h2.xedges.tolist(), h2.yedges.tolist(),
          h2.contents.shape, np.isclose(h2.contents.sum(), w.sum()))
    hd = mcpl.histogram(ex, 'pdgcode;bar=2')
    print(type(hd).__name__, repr(hd.expression), hd.values.tolist(), hd.contents.tolist())
    p3 = mcpl.histogram(ex, 'x/cm : y/cm : z/cm;maxpoints=10')
    print(type(p3).__name__, p3.expressions, p3.points.shape, p3.nparticles)
    from mcpldev._plotbackend_test import describe
    print(describe([ hist_figure(mcpl,p3) ]).splitlines()[1])
    print(describe([ hist_figure(mcpl,mcpl.histogram(ex, 'x : y : z')) ]).splitlines()[1])
    #(the particles chosen depend only on the particles, so those which remain
    #after a stricter condition stay chosen):
    full = mcpl.histogram(ex, 'x/cm : y/cm : z/cm;maxpoints=50')
    with mcpl.MCPLFile(ex, edit='x > 0cm') as f:
        sub = mcpl.histogram(f, 'x/cm : y/cm : z/cm;maxpoints=50')
    kept = { tuple(p) for p in full.points.tolist() if p[0] > 0 }
    print(f'{len(kept)} of the points have x > 0, and all are chosen with the edit x > 0:',
          kept <= { tuple(p) for p in sub.points.tolist() })
    for r in ( h, hd, h2, p3 ):
        print(type(r).__name__, [ a for a in dir(r) if not a.startswith('_') ],
              'isinstance:', isinstance(r,getattr(mcpl,type(r).__name__)))
    try:
        mcpl.Hist1D()
    except TypeError as e:
        print(f'Hist1D(): TypeError: {e}')
    for what, change in ( ( 'edges', lambda : operator.setitem(h.edges,0,1.0) ),
                          ( 'contents', lambda : operator.setitem(h.contents,0,1.0) ),
                          ( '2D contents', lambda : operator.setitem(h2.contents,(0,0),1.0) ),
                          ( 'points', lambda : operator.setitem(p3.points,(0,0),1.0) ),
                          ( 'attribute', lambda : setattr(h,'edges',None) ),
                          ( 'new attribute', lambda : setattr(h,'logy',True) ),
                          ( 'plot option', lambda : h.plot(logy=True) ),
                          ( 'histogram option', lambda : mcpl.histogram(ex,'x',bins=3) ) ):
        try:
            change()
            print(f'{what}: changed!')
        except ( ValueError, TypeError, AttributeError ) as e:
            print(f'{what}: {type(e).__name__}')
    for args in ( ( [ ex, ex ], 'x' ), ( ex, 3 ), ( ex, 'x;print' ) ):
        try:
            mcpl.histogram(*args)
            print(f'histogram{args}: no error')
        except mcpl.MCPLError as e:
            print(f'histogram{args}: {e}')
    h.plot()
    print(f'plot created {h.plot("plot.txt")}')
    try:
        h.plot('plot.txt')
    except mcpl.MCPLError as e:
        print(f'plot to an existing file: {e}')

def test_autobins():
    #Without bins, the number of bins follows from the number of entries
    #(square root, clamped to [10,400]), after histogramming with many bins
    #which are then merged exactly:
    from mcpldev._histfill import _auto_nbins, _nice_nbins
    print('nice numbers of bins:',[ (m,_nice_nbins(m)) for m in (1200,400,239,83,37,15,8) ])
    for n in (1, 100, 1000, 1e4, 1e5, 1e6):
        print(f'n={n:g}: bins of 1080 -> {_auto_nbins(n,1080)},'
              f' of 216 -> {_auto_nbins(n,216)}, 2D of 216 -> {_auto_nbins(n,216,2)}')
    #Sanity of the choices for all plot widths and a range of statistics: the
    #bins merge exactly, few columns are unused, and the number of bins is
    #close to the target unless the plot is too narrow for it:
    import math
    stats, nbad = [], 0
    for ncols in [None] + list(range(29,240)):
        nb = _nice_nbins(1200 if ncols is None else ncols)
        for nentries in (1,3,10,30,100,300,1e3,3e3,1e4,3e4,1e5,1e6,1e8):
            n = _auto_nbins(nentries,nb)
            target = max(10,min(400,round(math.sqrt(nentries))))
            unused = 0.0 if ncols is None else ( ncols - nb ) / ncols
            capped = ( n == nb )#(every column used, narrow plot)
            ratio = n / target
            ok = ( nb % n == 0 and ( ncols is None or nb <= ncols ) and unused <= 0.15
                   and ( capped or 0.6 <= ratio <= 1.5 ) )
            nbad += ( not ok )
            stats.append((ratio,unused,capped))
    print(f'{len(stats)} (ncols,nentries) cases, {nbad} bad, ratio to target'
          f' {min(r for r,_,c in stats if not c):.2f}..{max(r for r,_,c in stats if not c):.2f}'
          f' when not capped, {sum(c for _,_,c in stats)} capped by narrow plots,'
          f' at most {100*max(u for _,u,_ in stats):.0f}% unused columns')
    h = ihist(example_file, 'x/cm')
    hf = ihist(example_file, 'x/cm', bins=1080)
    v, vf = h.values(), hf.values()
    print(f'auto: {len(h.edges)-1} bins, sum {v.sum():g} (1080 bins: {vf.sum():g}),'
          f' merged exactly: {np.allclose(v,vf.reshape(len(v),-1).sum(axis=1))},'
          f' same edges: {np.allclose(h.edges,hf.edges[::1080//len(v)])},'
          f' for display: {h._display_bins}')
    h = ihist(example_file, 'x/cm', edit='pdgcode == 2212')
    print(f'auto with few particles: {len(h.edges)-1} bins, sum {h.values().sum():g}')
    h = ihist(example_file, 'x/cm', _maxbins=83)
    print(f'auto with at most 83 bins: {len(h.edges)-1} bins, for display: {h._display_bins}')
    h = ihist2d(example_file, 'x/cm', 'y/cm')
    print(f'auto 2D: {h.contents.shape} bins, sum {h.contents.sum():g},'
          f' for display: {h._display_bins}')
    h = ihist2d(example_file, 'x/cm', 'y/cm', _maxbins=(69,15))
    print(f'auto 2D with at most (69,15) bins: {h.contents.shape} bins,'
          f' sum {h.contents.sum():g}, for display: {h._display_bins}')
    h = ihist2d(example_file, 'x/cm', 'y/cm', bins=(8,4))
    print(f'2D with bins=(8,4): {h.contents.shape} bins, for display: {h._display_bins}')
    #(the same number of bins when a few particles have most of the weight, as
    #the bins show where the particles are; particles with weight 0 do not
    #count):
    rng = np.random.default_rng(1)
    nb = 100000
    x, y = rng.normal(0,1,nb), rng.normal(0,1,nb)
    for name, w in ( ( 'equal weights', np.ones(nb) ),
                     ( 'weights spread over 8 decades', 10**rng.uniform(-4,4,nb) ),
                     ( 'half of the weights 0', np.where(np.arange(nb)%2,1.0,0.0) ) ):
        with mcpl.MCPLOutFile('weighted.mcpl', allow_overwrite = True) as o:
            o.add_particles( pdgcode = 2112, ekin = 1.0, x = x, y = y, uz = 1.0, weight = w )
        h1, h2 = ihist('weighted.mcpl', 'x/cm'), ihist2d('weighted.mcpl', 'x/cm', 'y/cm')
        print(f'auto with {name}: {len(h1.edges)-1} bins, 2D {h2.contents.shape} bins')

def tool(*args):
    out = io.StringIO()
    rc = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            mcpl.app_mcpltool(['mcpltool',*args])
        except SystemExit as e:
            rc = e.code
        except mcpl.MCPLError as e:
            #(as the mcpltool command):
            print(f'mcpltool: {e!s}')
            rc = 1
    print(f'mcpltool {" ".join(args)}: exit code {rc}')
    for line in out.getvalue().splitlines():
        print(f'   | {line}')

def test_cmdline():
    ex = str(example_file)
    tool('-H','ekin/MeV;logx=1;display_by=pdgcode',ex)
    tool('-t','-H','ekin/eV;lethargy=1;bins=5;print=1','-e','pdgcode == neutron',ex)
    tool('--hist','x/cm : y/cm;bins=4;print=1','-e','pdgcode == gamma',ex)
    tool('--terminal','--hist=x/cm:y/cm;bins=2;xrange=-10:10;yrange=0:5;print=1',ex)
    tool('-H','x/cm : y/cm;bins=2;xrange=-10:10;print=1',ex)
    tool('-H','x/cm : y/cm;bins=3,2;print=1',ex)
    tool('-H','x/cm;range=-10:10;bins=4',ex,str(ref1))
    tool('-H','time/ms;logx=1;logy=1;unweighted=1',ex)
    tool('-t','-H','ekin/MeV : time/ms;logx=1;logy=auto',ex)
    tool('-H','ekin/MeV;display_by=pdgcode;range=0:10;bins=2;print=1',
         '-e','x > 1km',ex)
    #-l, -s, and -e (where conditions after changes see the changed values):
    tool('-H','z/cm;bins=2;range=0:100;print=1','-s1000',ex)
    #(numbers like 1e3 for -l and -s):
    tool('-H','z/cm;bins=2;range=0:100;print=1','-s1e3','-l2.5e1',ex)
    tool('-H','z/cm;bins=2;range=0:100;print=1','-l3','-e','z += 50cm',ex)
    tool('-H','z/cm;bins=2;range=0:100;print=1','--edit=z < 25cm; z += 50cm',ex)
    tool('-H','z/cm;bins=2;range=0:100;print=1','--edit=z += 50cm; z < 75cm',ex)
    #(abbreviated long options):
    tool('--hist=ekin/MeV;print=1;bins=2','--ed','pdgcode==22',ex)
    for bad in ( ['-H','ekin',ex], ['-H','ekin/MeV;bins=0',ex],
                 ['-H','ekin/MeV;range=1',ex], ['-H','ekin/MeV;range=2:1',ex],
                 ['-H','ekin/MeV;range=1:2,3:4',ex], ['-H','ekin/MeV;xrange=1:2',ex],
                 ['-H','x/cm : y/cm;range=1:2',ex],
                 ['-H','x/cm : y/cm;logx=1;equal',ex], ['-H','x/cm : y/cm : z/cm',ex], ['-H','x : y : z : x',ex], ['-H','x : y : z;bins=5',ex],
                 ['-H','x/cm;bins',ex], ['-H','x/cm;logx',ex], ['-H','x/cm;logx=true',ex],
                 ['-H','x/cm;logy=yes',ex], ['-H','x/cm;logx=2',ex], ['-H','x/cm;logy=auto',ex],
                 ['-H','x/cm;logx=1;logx=1',ex], ['-H','x/cm;foo',ex],
                 ['--logx',ex], ['--bins','10',ex],
                 ['-o','a.pdf',ex], ['-H','x/cm','-x',ex,'out.mcpl'],
                 ['-H','x/cm'], ['-H','x/cm;print=1','-o','a.png',ex],
                 #(logx=auto: logarithmic for positive values over more than
                 #two decades, else linear):
                 ['-H','ekin/MeV;logx=auto;bins=3;print=1',ex], ['-H','x/cm;logx=auto;bins=3;print=1',ex],
                 ['-H','ekin/MeV;logx=auto;range=1:10;bins=3;print=1',ex],
                 ['-H','x/cm','-o','a.txt',ex], ['-t','-H','x/cm','-o','a.png',ex] ):
        tool(*bad)

def test_cmdline_more():
    #Statistics, saving a file with the test backend (which describes the
    #figures), and argument errors (also of the forms of -t):
    ex = str(example_file)
    tool('-S','-o','stats.txt','-e','pdgcode == gamma',ex)
    tool('-S','-s1000','-e','x = 1cm',ex)
    tool('-t','-H','x/cm;bins=3','-o','hist.txt',ex)
    #(the errors as without the test backend):
    with _forced_backend(None):
        for bad in ( ['-p','neutron',ex], ['-p2112',ex], ['-p',' gamma ',ex],
                     ['-p'], ['-lX',ex], ['-l',ex], ['-l1,000',ex], ['-l1.5',ex],
                     ['-s1e-3',ex], ['-l2\u00b2',ex], ['-l99999999999999999999',ex],
                     #(a directory, as file):
                     ['..'], ['-S','..'], ['-t','-H','x/cm','..'],
                     ['-e','x > 0','-e','x < 1cm',ex], ['--pdf',ex], ['--gui',ex],
                     ['--select','x > 0',ex], ['-S','-t','-H','x',ex],
                     ['-S','-H','x/cm',ex], [ex,ex,ex],
                     ['-H','x/cm;bins=2;print','-H','pdgcode;bar=2;print',ex],
                     ['--text',ex], ['--text',ex,'hist.txt'],
                     ['-t',ex], ['-t',ex,ex],
                     ['-H','x/cm',ex], ['-B','test',ex], ['--te','x',ex],
                     ['-j','-H','x/cm',ex], ['--no-comment','-S',ex],
                     ['-H','x/cm : y/cm;display_by=pdgcode',ex],
                     ['-H','x/cm','-o','hist',ex], ['-H','x/cm','-o','hist.jpg',ex],
                     ['-H','x/cm','-o','hist.png','-d',ex],
                     ['-e','x > "1"',ex], ['-e','z = 1cm, x = 0',ex], ['-E','x > 0',ex] ):
            tool(*bad)

def test_help_topics():
    #Only the start of each topic (the rest are tables of all names):
    for args in ( ['-e','help'], ['--edit=help'], ['--hist-help'] ):
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
    for what, args in ( ( 'x, 0.3m', ((1,0,0,0),-30,30) ), ( 'x, 2.5m', ((1,0,0,0),0,250) ),
                        ( 'x, 5mm', ((1,0,0,0),0,0.5) ), ( 'ekin, 9.7GeV', ((0,1,0,0),0.0014,9725) ),
                        ( 'ekin, log axis', ((0,1,0,0),1e-9,10,True) ), ( 'time, log axis', ((0,0,1,0),1e-6,1e-3,True) ),
                        ( 'x^2', ((2,0,0),0,1e4) ), ( 'sqrt(ekin)', ((0,0.5,0),0,1e-3) ),
                        ( 'x*ekin', ((1,1,0),0,10) ), ( '1/x', ((-1,0,0),0,0.5) ),
                        ( 'wavelength, 1.8Aa', ((1,0,0,0),1e-8,1.8e-8,False,True) ),
                        ( 'wavelength, log axis 1e-3 to 100Aa', ((1,0,0,0),1e-11,1e-6,True,True) ),
                        ( 'wavelength, up to 1mm', ((1,0,0,0),0,0.1,False,True) ), ( 'no units', (None,0,1) ) ):
        print(f'unit of {what}: {_plot_unit(*args)}')
    for e, kw in ( ( 'x', {} ), ( 'ekin;logx=auto', {} ), ( 'wavelength', { 'edit' : 'pdgcode == neutron' } ),
                   ( 'x;range=-10cm:10cm;bins=2', {} ), ( 'x;range=0:1m;bins=2', {} ), ( 'x/cm;bins=2', {} ),
                   ( 'hypot(x,y)', {} ) ):
        h = ihist(ex,e,**kw)
        print(f'histogram({e!r}): label {h.label!r}, edges from {h.edges[0]:.4g} to {h.edges[-1]:.4g}')
    h = ihist2d(ex,'x','ekin/MeV',bins=2)
    print('histogram2d(x, ekin/MeV):', h.to_text().splitlines()[0])
    for e in ( 'x;range=-10:10', 'x/cm;range=-10cm:10cm', 'ekin;range=0cm:1cm', 'x;range=1cm', 'x;range=y:1cm' ):
        try:
            ihist(ex,e)
        except mcpl.MCPLError as err:
            print(f'histogram({e!r}): {err}')

def test_bars_groups_domains():
    ex = 'example.mcpl'
    #Bars of distinct values, split groups, and expressions which are only
    #defined for some particles (wavelengths):
    for e, kw in ( ( 'pdgcode;bar=auto', {} ), ( 'pdgcode;bar=3', {} ),
                   ( 'mod(abs(pdgcode),7);bar=auto;unweighted=1', {} ), ( 'pdgcode', { 'bar' : 2 } ),
                   ( 'pdgcode;bar=auto', { 'edit' : 'pdgcode != neutron' } ),
                   ( 'round(x/10cm);bar=4;logy=1', {} ), ( 'mod(floor(ekin/MeV),3);bar=auto;logy=0', {} ) ):
        h = ihist(ex,e,**kw)
        print(f'histogram({e!r},{kw}):')
        print(h.to_text())
        show(h)
    h = ihist(ex,'ekin/MeV',display_by='mod(fileidx,10)',bins=3)
    print('split in at most 8 curves:', list(h.contents), h.colors)
    for e, kw in ( ( 'wavelength;bins=3', {} ), ( 'wavelength;bins=3', { 'edit' : 'pdgcode == neutron' } ),
                   ( 'wavelength;display_by=pdgcode;bins=3', {} ), ( 'round(1000*wavelength/Aa);bar=auto', { 'edit' : 'ekin > 1GeV' } ) ):
        h = ihist(ex,e,**kw)
        print(f'histogram({e!r},{kw}): label {h.label!r}, contents {[ float(np.sum(c)) for c in h.contents.values() ]}')
    h = ihist2d(ex,'wavelength','x',bins=2)
    print('histogram2d(wavelength,x):', h.xlabel, '|', h.ylabel, '|', h.contents.sum())
    for e, kw in ( ( 'x;bar=auto', {} ), ( 'pdgcode;bar=1', {} ), ( 'pdgcode;bar=on', {} ),
                   ( 'pdgcode;bar=auto;logx=1', {} ), ( 'pdgcode;bar=auto;display_by=pdgcode', {} ),
                   ( 'x:y;bar=auto', {} ), ( 'ekin/MeV;groups=3', {} ),
                   ( 'pdgcode', { 'bar' : 1 } ), ( 'pdgcode', { 'bar' : 'auto' } ),
                   ( 'pdgcode;bar=auto', { 'bar' : 4 } ), ( 'pdgcode', { 'bar' : True, 'logx' : True } ),
                   ( 'ekin/MeV;bar=auto', {} ), ( 'round(x);bar=auto', {} ),
                   ( 'round(1e300*x/cm);bar=auto', {} ) ):
        try:
            ihist(ex,e,**kw)
            print(f'histogram({e!r},{kw}): no error')
        except mcpl.MCPLError as err:
            print(f'histogram({e!r},{kw}): {err}')

def test_ranges_colors():
    from mcpldev._figures import _line_style
    from mcpldev._histfill import _nice_range, _value_colors
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
    #colours (cyan first, and never those of n, gamma, e-, and p), and then
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
    h = ihist(ex,'x : y : z;maxpoints=100;display_by=single')
    print('3D:', type(h).__name__, { k : v.shape for k, v in h.groups.items() }, h.labels,
          h.nparticles)
    same = ihist(ex,'x : y : z;maxpoints=100;display_by=single')
    print('same sample:', np.array_equal(h.groups[None],same.groups[None]))
    h = ihist(ex,'ux : uy : uz;display_by=mod(fileidx,10)',edit='ekin > 1keV')
    print('split:', { k : len(v) for k, v in h.groups.items() }, h.colors)
    print(describe([ hist_figure(mcpl,h) ]))
    print(h.to_text().splitlines()[:4])
    h = ihist(ex,'x : y : z;unweighted;maxpoints=5000;display_by=single')
    print('more points than particles:', len(h.groups[None]), 'of', h.nparticles)

def test_logz():
    #The colour scale of 2D histograms is logarithmic unless logz=0, which
    #makes another plot (logz and logz=1 make the same as without logz):
    ex = str(example_file)
    for text in ( 'x : y', 'x : y;logz', 'x : y;logz=0' ):
        h = ihist(ex,text)
        print(f'{text!r}: logz {h.logz}, panel {hist_panel(mcpl,h).items[0].logz}')
    for bad in ( 'x;logz=0', 'x : y : z;logz', 'x : y;logz=2' ):
        try:
            ihist(ex,bad)
        except mcpl.MCPLError as e:
            print(f'{bad!r}: {e}')

def test_equal():
    #Equal scales of the axes of 2D histograms with the same units, also when
    #they are shown in different units (as cm and mm):
    from mcpldev._plotbackend_test import describe
    ex = str(example_file)
    for text in ( 'x : y;equal', 'x : 0.02*y;equal', 'ux : uy;equal', 'x : y' ):
        h = ihist(ex,text)
        print(f'{text!r}: aspect {h.aspect} ({h.xunit}, {h.yunit}), panel {hist_panel(mcpl,h).aspect}')
    print(describe([ hist_figure(mcpl,ihist(ex,'x : y;equal')) ]).splitlines()[1])
    #(3D plots: the same unit on all axes, from all values):
    for text in ( 'x : y : z;equal', 'x : y : 1000*z;equal', 'x : y : 1000*z' ):
        h = ihist(ex,text)
        print(f'{text!r}: units {h.units}, equal {h.equal}, panel aspect {hist_panel(mcpl,h).aspect}')
    #(with equal scales, the axes are linear by default, also for values
    #spanning many decades):
    p = hist_panel(mcpl,ihist(ex,'ekin : ekin;equal'))
    print(f"'ekin : ekin;equal': logx {p.logx}, logy {p.logy}")
    for bad in ( 'x : ekin;equal', 'x;equal', 'x : y : ekin;equal', 'ekin : ekin;equal;logy' ):
        try:
            ihist(ex,bad)
        except mcpl.MCPLError as e:
            print(f'{bad!r}: {e}')

def test_option_kinds():
    #Which options can be used for which kinds of plots (with any value, also
    #values which turn them off):
    import importlib
    parse = importlib.import_module(f'{mcpl.__name__}._histstring')._parse_hist
    kinds = { '1D' : 'x/cm', 'bars' : 'pdgcode;bar=3', '2D' : 'x/cm : y/cm',
              '3D' : 'x/cm : y/cm : z/cm' }
    for option in ( 'bins=5', 'range=0:1', 'xrange=0:1', 'yrange=0:1', 'logx=0', 'logy=0',
                    'logz=0', 'lethargy=0', 'display_by=single', 'bar=0', 'unweighted=0',
                    'print=0', 'maxpoints=10', 'equal=0', 'display_edit=x > 0cm' ):
        ok = []
        for kind, text in kinds.items():
            if kind == 'bars' and option.startswith('bar='):
                ok.append(kind)#(the option bar is what makes bar charts)
                continue
            try:
                parse(f'{text};{option}')
                ok.append(kind)
            except mcpl.MCPLError:
                pass
        print(f'{option}: {", ".join(ok)}')
    try:
        parse('x/cm : y/cm : z/cm;logy=0')
    except mcpl.MCPLError as e:
        print(e)

def test_display_edit():
    #The option display_edit edits the particles of a plot (after the edit of
    #the file), the same as editing them, in all kinds of histograms:
    import numpy as np
    ex = str(example_file)
    def contents( h ):
        c = h.contents
        return ( np.concatenate([ np.ravel(v) for v in c.values() ])
                 if isinstance(c,collections.abc.Mapping) else np.ravel(c) )
    for text, cond, edit in ( ( 'ekin/MeV;bins=20', 'ekin < 1MeV', None ),
                              ( 'x/cm : y/cm;bins=8', 'pdgcode == neutron', None ),
                              ( 'pdgcode;bar', 'ekin > 1MeV', None ),
                              ( 'ekin/MeV;bins=20;display_by=pdgcode', 'ekin < 1MeV', 'x > 0' ),
                              ( 'x : y : z;maxpoints=50', 'ekin < 1MeV', None ),
                              ( 'x/cm;bins=10', 'rotate_z(90deg); x > 0cm', 'ekin < 1MeV' ) ):
        h = ihist(ex,f'{text};display_edit={cond}',edit = edit)
        both = cond if edit is None else f'{edit}; {cond}'
        ref = ihist(ex,text,edit = both)
        same = ( h.nparticles == ref.nparticles if hasattr(h,'nparticles')
                 else np.array_equal(contents(h),contents(ref)) )
        print(f'{text};display_edit={cond} (edit {edit}): as editing them: {same} | title {h.title!r}')
    for bad in ( 'x;display_edit', 'x;display_edit=r = x', 'x;display_edit=foo > 1',
                 'x;display_edit=1cm', 'x;display_edit=x > 0cm;logy' ):
        try:
            ihist(ex,bad)
        except mcpl.MCPLError as e:
            print(f'{bad!r}: {e}')

#(the plots are described by the test backend):
with _forced_backend('test'):
    test_display_edit()
    test_option_kinds()
    test_logz()
    test_equal()
    test_3d()
    test_ranges_colors()
    test_units()
    test_bars_groups_domains()
    test_histograms()
    test_plot_stats()
    test_public_api()
    test_cmdline()
    test_cmdline_more()
    test_help_topics()
    test_autobins()
