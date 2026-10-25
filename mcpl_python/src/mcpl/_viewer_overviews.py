
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
    coefficient of the mirrored pair (see Moments), as (cells, kinds), see
    Overview. The axes are logarithmic if suitable for the values (with
    logx=auto)."""
    n = len(exprs)
    cells, kinds = [], []
    for i in range(n):
        for j in range(n):
            a, b = ( j, i ) if j <= i else ( i, j )
            cells.append( f'{exprs[i]};logx=auto' if i == j
                          else f'{exprs[a]} : {exprs[b]};logx=auto;logy=auto' )
            kinds.append( 'plot' if j <= i else 'r' )
    return cells, kinds

class Moments:
    """The weighted sums of the fields, of their logarithms and of their
    products, by particle type (from the blocks given to add), from which
    follow the weighted correlation coefficients of all pairs of the fields
    (see coefficients), on the axes of corner plots: logarithmic for fields
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

def overview_figure( figures, overview, coefficients = None ):
    """The figure of the overview, from the figures of its plots (as far as they
    are available, with empty panels for the others, and None for empty
    cells), with the correlation coefficients of corner plots (as {(field,
    field) : r}, see Moments), or None if no plot is available. The title says what the plots are
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
            from ._histstring import _hist_parts
            a, b = ( e.strip() for e in _hist_parts(p)[0].split(':') )
            r = coefficients or {}
            panels.append(Panel( items = [ Correlation(r.get(( a, b ),r.get(( b, a )))) ] ))
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
