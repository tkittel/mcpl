
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
layout: a grid of plots, or a correlation plot of variables (their histograms on
the diagonal, the 2D histograms of each pair below it, and the correlation
coefficients of the pairs above it)."""

__all__ = []

import copy
import math

#The layouts of overviews (see Overview):
layouts = ( 'grid', 'correlation' )

class Overview:
    """An overview: its title (and the description of its plots, if any), and
    its cells in a grid of nrows x ncols, row by row: the plots (histogram
    strings, None for empty cells), and how each is shown (kinds: 'plot', 'r'
    for the correlation coefficient of the 2D histogram of the plot, or 'new'
    for the place of a new plot, after the plots with add_cell).
    With the layout 'grid', the cells are the plots, and with 'correlation', they
    are made from the variables (expressions, see correlation_cells). With
    display_only and display_by, the plots get those options (of histogram
    strings): display_only for all, and display_by for those which can show
    several curves and do not have it."""
    def __init__( self, title, plots = (), description = None, layout = 'grid',
                  variables = (), display_only = None, display_by = None,
                  add_cell = False ):
        assert layout in layouts
        self.title, self.description, self.layout = title, description, layout
        self.variables, self.display_only = list(variables), display_only
        if layout == 'correlation':
            self.cells, self.kinds = correlation_cells(self.variables)
            self.ncols = max( 1, len(self.variables) )
        else:
            self.cells, self.kinds = list(plots), [ 'plot' ] * len(plots)
            if add_cell:
                self.cells.append(None)
                self.kinds.append('new')
            self.ncols = grid_columns(len(self.cells))
        self.cells = [ None if c is None else _with_display(c,display_only,display_by)
                       for c in self.cells ]
        self.nrows = max( 1, math.ceil( len(self.cells) / self.ncols ) )

    @property
    def correlation_plot( self ):
        """Whether it is a correlation plot (drawn with shared axes)"""
        return self.layout == 'correlation'

    @property
    def plots( self ):
        """The plots of the overview, in the order of its cells (each once)"""
        return list(dict.fromkeys( p for p in self.cells if p is not None ))

def _with_display( plot, display_only, display_by ):
    """The plot (histogram string) with the options display_only (if given)
    and display_by (if given, and the plot does not have it, and can show
    several curves, unless it is their default, see _histstring._display_by)"""
    from ._histstring import _display_by, _hist_set_option, _parse_hist
    if display_only:
        plot = _hist_set_option(plot,'display_only',display_only)
    if display_by:
        o = _parse_hist(plot)
        if o['display_by'] is None and _display_by(o) not in ( None, display_by ):
            plot = _hist_set_option(plot,'display_by',display_by)
    return plot

def grid_columns( n ):
    """Columns of a grid of n plots: 3 for 6 plots (in 2 rows), and more for
    more plots, so they fill a wide window"""
    return max( 1, min( n, math.ceil( math.sqrt( 1.5 * n ) ) ) )

def correlation_cells( exprs ):
    """The cells of a correlation plot of the expressions, with the expression of the
    column on the x axis below the diagonal, and above it the correlation
    coefficient of the mirrored pair (see Moments), as (cells, kinds), see
    Overview. The axes are logarithmic if suitable for the values (with
    logx=auto)."""
    n = len(exprs)
    cells, kinds = [], []
    for i in range(n):
        for j in range(n):
            a, b = ( j, i ) if j <= i else ( i, j )
            #(the histograms on the diagonal with one curve, as the plots are
            #small, without legends):
            cells.append( f'{exprs[i]};logx=auto;display_by=single' if i == j
                          else f'{exprs[a]} : {exprs[b]};logx=auto;logy=auto' )
            kinds.append( 'plot' if j <= i else 'r' )
    return cells, kinds

class Moments:
    """The weighted sums of the fields, of their logarithms and of their
    products, by particle type (from the blocks given to add), from which
    follow the weighted correlation coefficients of all pairs of the fields
    (see coefficients), on the axes of correlation plots: logarithmic for fields
    whose values are positive and span more than two decades (as with
    logx=auto, see _histstring._auto_logx)"""
    def __init__( self, fields ):
        self.fields = list(fields)
        self._sums = {}#(pdgcode -> [ sum of weights, sums, sums of products, min, max ])
        self._shift = None#(subtracted from the values, against rounding errors)

    def add( self, b ):
        from ._numpy import np
        n = len(b)
        if not n:
            return
        x = np.stack([ np.broadcast_to(np.asarray(getattr(b,f),dtype=float),(n,))
                       for f in self.fields ],axis=1)
        w = np.broadcast_to(np.asarray(b.weight,dtype=float),(n,))
        pdg = np.broadcast_to(np.asarray(b.pdgcode),(n,))
        ok = np.isfinite(x).all(axis=1) & np.isfinite(w)
        x, w, pdg = x[ok], w[ok], pdg[ok]
        if not len(x):
            return
        with np.errstate(divide='ignore',invalid='ignore'):
            lx = np.where(x > 0,np.log(np.where(x > 0,x,1.0)),0.0)
        z = np.concatenate([ x, lx ],axis=1)
        if self._shift is None:
            self._shift = z.mean(axis=0)
        z = z - self._shift
        for k in np.unique(pdg).tolist():
            m = pdg == k
            zk, wk, xk = z[m], w[m], x[m]
            add = [ wk.sum(), wk @ zk, zk.T @ ( wk[:,None] * zk ), xk.min(axis=0), xk.max(axis=0) ]
            old = self._sums.get(k)
            if old is None:
                self._sums[k] = add
            else:
                self._sums[k] = [ *( o + a for o, a in zip(old[:3],add[:3]) ),
                                  np.minimum(old[3],add[3]), np.maximum(old[4],add[4]) ]

    def coefficients( self ):
        """The correlation coefficients, as {pdgcode : {(field, field) : r}},
        with the key None for all particles (r is None if not defined, e.g.
        for fields with one value)"""
        from ._histstring import _auto_logx
        from ._numpy import np
        if not self._sums:
            return {}
        sums = dict(self._sums)
        all_types = list(sums.values())
        sums[None] = [ *( sum( s[i] for s in all_types ) for i in range(3) ),
                       np.min([ s[3] for s in all_types ],axis=0),
                       np.max([ s[4] for s in all_types ],axis=0) ]
        n, res = len(self.fields), {}
        for k, ( sw, s, ss, lo, hi ) in sums.items():
            if not sw > 0:
                continue
            mean = s / sw
            cov = ss / sw - np.outer(mean,mean)
            var = np.diag(cov)
            #(values which are all the same, up to rounding errors, have no
            #correlations):
            varies = var > 1e-12 * np.diag(ss) / sw
            cols = [ n + i if _auto_logx(lo[i],hi[i]) else i for i in range(n) ]
            res[k] = r = {}
            for i in range(n):
                for j in range(i + 1,n):
                    a, b = cols[i], cols[j]
                    c = cov[a,b] / np.sqrt(var[a] * var[b]) if varies[a] and varies[b] else None
                    r[( self.fields[i], self.fields[j] )] = ( None if c is None
                                                             else float(np.clip(c,-1.0,1.0)) )
        return res

def _without_label( item ):
    """The item of a panel without its label (a copy, if it has one)"""
    if getattr(item,'label',None) is None:
        return item
    item = copy.copy(item)
    item.label = None
    return item

def overview_figure( figures, overview, coefficients = None ):
    """The figure of the overview, from the figures of its plots (as far as they
    are available, with empty panels for the others, and None for empty
    cells), with the correlation coefficients of correlation plots (as {(field,
    field) : r}, see Moments), or None if no plot is available. The title
    says what the plots are (as "Fields plots: a plot of each particle field"),
    followed by the title of the plots in parentheses, if any."""

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
            from ._histstring import _hist_exprs
            a, b = _hist_exprs(p)
            r = coefficients or {}
            panels.append(Panel( items = [ Correlation(r.get(( a, b ),r.get(( b, a )))) ] ))
            continue
        panel = copy.copy(f.panels[0]) if f is not None else Panel( items = [ Text('') ] )
        panel.title = None#(the title of the plots is that of the overview)
        if len(overview.cells) > 6 and not overview.correlation_plot:
            panel.ylabel = None#(as "weights per bin" of each plot meets its neighbours)
            #(and without legends, which would cover the small plots, as the
            #colours of the particle types are the same in all of them):
            panel.items = [ _without_label(it) for it in panel.items ]
        panels.append(panel)
    title = next( ( f.title for f in figs.values() if f is not None ), None )
    if overview.description:
        what = f'{overview.title} plots: {overview.description}'
        if overview.display_only:
            what += f' (only: {overview.display_only})'
        title = what if not title else f'{what} ({title})'
    fig = Figure( title = title, nrows = overview.nrows, ncols = overview.ncols,
                  panels = panels )
    fig._correlation_plot = overview.correlation_plot#(drawn with shared axes, see _plotbackend_mpl)
    return fig
