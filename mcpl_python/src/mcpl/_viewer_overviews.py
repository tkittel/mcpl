
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
together in a grid, as the overviews of the groups of plots (see
_viewer_groups): a grid of plots, or a corner plot of expressions (their
histograms on the diagonal, and the 2D histograms of each pair below it)."""

__all__ = []

import math


class Overview:
    """An overview: its title (and the description of its plots, if any), and
    the plots (histogram strings) of the cells of its grid of nrows x ncols,
    row by row (None for empty cells)"""
    def __init__( self, title, cells, ncols, corner = False, description = None ):
        self.title, self.cells, self.ncols = title, list(cells), ncols
        self.description = description
        self.corner = corner#(a corner plot, see pair_cells)
        self.nrows = max( 1, math.ceil( len(self.cells) / ncols ) )

    @property
    def plots( self ):
        """The plots of the overview, in the order of its cells"""
        return [ p for p in self.cells if p is not None ]

def grid_columns( n ):
    """Columns of a grid of n plots: 3 for 6 plots (in 2 rows), and more for
    more plots, so they fill a wide window"""
    return max( 1, min( n, math.ceil( math.sqrt( 1.5 * n ) ) ) )

def pair_cells( exprs ):
    """The cells of a corner plot of the expressions (see the module), with the
    expression of the column on the x axis"""
    n = len(exprs)
    return [ exprs[i] if i == j else f'{exprs[j]} : {exprs[i]}' if j < i else None
             for i in range(n) for j in range(n) ]

def overview_figure( figures, overview ):
    """The figure of the overview, from the figures of its plots (as far as they
    are available, with empty panels for the others, and None for empty
    cells), or None if none is available. The title says what the plots are
    (as "Fields plots: the fields of the particles"), followed by that of the
    plots, if any."""
    import copy

    from .plotting import Figure, Panel, Text
    figs = { p : figures.get(f'plot:{p}') for p in overview.plots }#(see _viewer_reading)
    if all( f is None for f in figs.values() ):
        return None
    panels = []
    for p in overview.cells:
        f = figs.get(p) if p is not None else None
        if p is None:
            panels.append(None)
            continue
        panel = copy.copy(f.panels[0]) if f is not None else Panel( items = [ Text('') ] )
        panel.title = None#(the title of the plots is that of the overview)
        if len(overview.cells) > 6 and not overview.corner:
            panel.ylabel = None#(as "weights per bin" of each plot meets its neighbours)
        panels.append(panel)
    title = next( ( f.title for f in figs.values() if f is not None ), None )
    if overview.description:
        what = f'{overview.title} plots: {overview.description}'
        title = what if not title else f'{what} ({title})'
    fig = Figure( title = title, nrows = overview.nrows, ncols = overview.ncols,
                  panels = panels )
    fig._corner = overview.corner#(drawn with shared axes, see _plotbackend_mpl)
    return fig
