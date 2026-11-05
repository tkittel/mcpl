
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

"""Figures for tests of the plotting backends, with the kinds of plots of
mcpl: curves (also several in one plot), a 2D map, and bars."""

_plots = ( 'ekin;logx=auto;logy;display_by=pdgcode', 'angle(dir,(0,0,1))/deg;logy;display_by=pdgcode',
           'x : y', 'time;logx=auto;logy;display_by=single', 'pdgcode;bar;logy=auto',
           'x;display_by=single' )

def _module( mcpl, name ):
    import importlib
    return importlib.import_module(f'{mcpl.__name__}.{name}')

def plotting( mcpl ):
    """The (internal) module showing and saving plots (mcpl is the mcpl module)"""
    return _module(mcpl,'_plotting')

def internal_histogram( mcpl, files, expression, *, edit = None, bins = None, range = None,
                        logx = False, unweighted = False, display_by = None,
                        display_edit = None, lethargy = False, bar = False, _maxbins = None ):
    """The histogram (of _histfill, with all its details) of the expression for
    the particles in the files, with the options of histogram strings also as
    keyword arguments (mcpl is the mcpl module)"""
    hs = _module(mcpl,'_histstring')
    given = { 'bins' : bins, 'range' : range, 'logx' : logx, 'unweighted' : unweighted,
              'display_by' : display_by, 'display_edit' : display_edit,
              'lethargy' : lethargy, 'bar' : bar }
    return _module(mcpl,'_histfill')._fill(files,hs._hist_with_args(expression,given),
                                           edit = edit,_maxbins = _maxbins)

def internal_histogram2d( mcpl, files, xexpression, yexpression, *, edit = None, bins = None,
                          xrange = None, yrange = None, unweighted = False, logx = False,
                          logy = False, _maxbins = None ):
    """The 2D histogram (see internal_histogram) of the two expressions"""
    hs = _module(mcpl,'_histstring')
    o = hs._hist_defaults([ xexpression, yexpression ])
    o.update( bins = hs._bins_arg(bins,2), xrange = hs._as_range(xrange,'xrange'),
              yrange = hs._as_range(yrange,'yrange'), unweighted = unweighted,
              logx = logx, logy = logy )
    return _module(mcpl,'_histfill')._fill(files,o,edit = edit,_maxbins = _maxbins)

def hist_panel( mcpl, h ):
    """The panel of the plot of a histogram (of mcpl.histogram, or of
    internal_histogram), as made by its plot() (mcpl is the mcpl module)"""
    return _module(mcpl,'_histfigures').panel(getattr(h,'_d',h))

def hist_figure( mcpl, h ):
    """The figure of the plot of a histogram (see hist_panel)"""
    return _module(mcpl,'_figures').Figure( panels = [ hist_panel(mcpl,h) ] )

def example_figures( mcpl, filename ):
    """An overview of 6 plots of the file (2 rows of 3, with the title of the
    file), followed by each of them on its own (mcpl is the mcpl module)"""
    import pathlib
    hists = [ internal_histogram(mcpl,filename,p) for p in _plots ]
    overview = _module(mcpl,'_figures').Figure( title = f'Overview of {pathlib.Path(filename).name}', nrows = 2,
                                     ncols = 3, panels = [ hist_panel(mcpl,h) for h in hists ] )
    return [ overview ] + [ hist_figure(mcpl,h) for h in hists ]

def items_figure( mcpl ):
    """A figure with all kinds of items and panels (mcpl is the mcpl module): a
    3D scatter plot, an empty cell, a 2D map with the same scale on both axes,
    bars with colours, and 25 curves (more than the 10 colours, so also dashed
    and dotted), one with the symbol of the gamma in its label"""
    import numpy as np
    P = _module(mcpl,'_figures')
    Bars, Figure, Hist2D, Panel = P.Bars, P.Figure, P.Hist2D, P.Panel
    Scatter3D, StepHist = P.Scatter3D, P.StepHist
    import importlib
    gamma = importlib.import_module(f'{mcpl.__name__}._particles')._pdg_symbols['gamma']
    t = np.linspace(0.0,6.0,50)
    scatter = Panel( title = '3D', xlabel = 'x', ylabel = 'y', zlabel = 'z',
                     items = [ Scatter3D(np.cos(t),np.sin(t),t,label='helix') ] )
    edges = np.linspace(0.0,4.0,5)
    square = Panel( title = 'Same scales', aspect = 1.0,
                    items = [ Hist2D(edges,edges,np.arange(16.0).reshape(4,4)) ] )
    bars = Panel( title = 'Coloured bars',
                  items = [ Bars(['a','b','c'],[1.0,3.0,2.0],colors=[0,1,12]) ] )
    curves = Panel( title = 'Curves', xlabel = 'x' )
    x = np.linspace(0.0,10.0,11)
    for k in range(25):
        curves.add(StepHist(x,np.full(10,k+1.0),label=gamma if k == 1 else f'c{k}'))
    return Figure( title = 'All items', nrows = 2, ncols = 3,
                   panels = [ scatter, None, square, bars, curves ] )
