
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

"""The overviews of the viewer (see _viewer.Viewer): several plots shown
together, as the overviews of the groups of plots (see _viewer_groups), in a
layout: a grid of plots, or a corner plot of variables (their histograms on
the diagonal, the 2D histograms of each pair below it, and the correlation
coefficients of the pairs above it)."""

__all__ = []

import math

#The layouts of overviews (see Overview):
layouts = ( 'grid', 'corner' )

class Overview:
    """An overview: its title (and the description of its plots, if any), and
    its cells in a grid of nrows x ncols, row by row: the plots (histogram
    strings, None for empty cells), and how each is shown (kinds: 'plot', 'r'
    for the correlation coefficient of the 2D histogram of the plot, or 'new'
    for the place of a new plot, after the plots with add_cell).
    With the layout 'grid', the cells are the plots, and with 'corner', they
    are made from the variables (expressions, see corner_cells). With only (a
    condition), the plots use only those particles (the option only of
    histogram strings)."""
    def __init__( self, title, plots = (), description = None, layout = 'grid',
                  variables = (), only = None, add_cell = False ):
        assert layout in layouts
        self.title, self.description, self.layout = title, description, layout
        self.variables, self.only = list(variables), only
        if layout == 'corner':
            self.cells, self.kinds = corner_cells(self.variables)
            self.ncols = max( 1, len(self.variables) )
        else:
            self.cells, self.kinds = list(plots), [ 'plot' ] * len(plots)
            if add_cell:
                self.cells.append(None)
                self.kinds.append('new')
            self.ncols = grid_columns(len(self.cells))
        if only:
            from ._histstring import _hist_set_option
            self.cells = [ None if c is None else _hist_set_option(c,'only',only)
                           for c in self.cells ]
        self.nrows = max( 1, math.ceil( len(self.cells) / self.ncols ) )

    @property
    def corner( self ):
        """Whether it is a corner plot (drawn with shared axes)"""
        return self.layout == 'corner'

    @property
    def plots( self ):
        """The plots of the overview, in the order of its cells (each once)"""
        return list(dict.fromkeys( p for p in self.cells if p is not None ))

def grid_columns( n ):
    """Columns of a grid of n plots: 3 for 6 plots (in 2 rows), and more for
    more plots, so they fill a wide window"""
    return max( 1, min( n, math.ceil( math.sqrt( 1.5 * n ) ) ) )

def corner_cells( exprs ):
    """The cells of a corner plot of the expressions, with the expression of the
    column on the x axis below the diagonal, and above it the correlation
    coefficient of the mirrored pair, as (cells, kinds), see Overview. The
    axes are logarithmic if suitable for the values (with logx=auto)."""
    n = len(exprs)
    cells, kinds = [], []
    for i in range(n):
        for j in range(n):
            a, b = ( j, i ) if j <= i else ( i, j )
            cells.append( f'{exprs[i]};logx=auto' if i == j
                          else f'{exprs[a]} : {exprs[b]};logx=auto;logy=auto' )
            kinds.append( 'plot' if j <= i else 'r' )
    return cells, kinds

def _centres( edges, log ):
    """The centres of the bins (of the logarithms, if log)"""
    from ._numpy import np
    e = np.log(np.asarray(edges,dtype=float)) if log else np.asarray(edges,dtype=float)
    return 0.5 * ( e[:-1] + e[1:] )

def correlation( figure ):
    """The weighted correlation coefficient of the values of the 2D histogram
    of the figure (from the contents of its bins, on its axes, so of the
    logarithms of the values of logarithmic axes), or None"""
    from ._numpy import np
    from .plotting import Hist2D
    hist = next( ( it for it in ( figure.panels[0].items if figure is not None
                                  and figure.panels else () ) if isinstance(it,Hist2D) ), None )
    if hist is None:
        return None
    w = np.nan_to_num(np.asarray(hist.values,dtype=float))
    total = w.sum()
    if not total > 0:
        return None
    #(of the values on the axes, so in log for logarithmic axes):
    panel = figure.panels[0]
    xc, yc = ( _centres(e,log) for e, log in ( ( hist.xedges, panel.logx ),
                                              ( hist.yedges, panel.logy ) ) )
    wx, wy = w.sum(axis=1), w.sum(axis=0)
    mx, my = ( wx * xc ).sum() / total, ( wy * yc ).sum() / total
    vx, vy = ( wx * ( xc - mx )**2 ).sum() / total, ( wy * ( yc - my )**2 ).sum() / total
    if not ( vx > 0 and vy > 0 ):
        return None
    cov = ( w * np.outer(xc - mx,yc - my) ).sum() / total
    return float( max( -1.0, min( 1.0, cov / math.sqrt( vx * vy ) ) ) )

def overview_figure( figures, overview ):
    """The figure of the overview, from the figures of its plots (as far as they
    are available, with empty panels for the others, and None for empty
    cells), or None if none is available. The title says what the plots are
    (as "Fields plots: the fields of the particles"), followed by that of the
    plots, if any."""
    import copy

    from .plotting import Correlation, Figure, NewPlot, Panel, Text
    figs = { p : figures.get(f'plot:{p}') for p in overview.plots }#(see _viewer_reading)
    if all( f is None for f in figs.values() ):
        return None
    panels = []
    for p, kind in zip(overview.cells,overview.kinds):
        f = figs.get(p) if p is not None else None
        if kind == 'new':
            panels.append(Panel( items = [ NewPlot() ] ))
            continue
        if p is None:
            panels.append(None)
            continue
        if kind == 'r':
            panels.append(Panel( items = [ Correlation(correlation(f)) ] ))
            continue
        panel = copy.copy(f.panels[0]) if f is not None else Panel( items = [ Text('') ] )
        panel.title = None#(the title of the plots is that of the overview)
        if len(overview.cells) > 6 and not overview.corner:
            panel.ylabel = None#(as "weights per bin" of each plot meets its neighbours)
        panels.append(panel)
    title = next( ( f.title for f in figs.values() if f is not None ), None )
    if overview.description:
        what = f'{overview.title} plots: {overview.description}'
        if overview.only:
            what += f' (only: {overview.only})'
        title = what if not title else f'{what} ({title})'
    fig = Figure( title = title, nrows = overview.nrows, ncols = overview.ncols,
                  panels = panels )
    fig._corner = overview.corner#(drawn with shared axes, see _plotbackend_mpl)
    return fig
