
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
together in a grid. A collection of plots (see _stdviews) gives its overviews
as specifications, dicts with the title and one of: first (the number of
first plots of the viewer), group (the plots of a group of the viewer, in
their order), plots (histogram strings, or None for empty cells, with ncols
columns) or pairs (expressions, for a correlation plot: their histograms on the
diagonal, the 2D histograms of each pair below it, and empty cells above)."""

__all__ = []

import math

#(the overview of collections which do not give their overviews):
default_specs = ( { 'title' : 'Overview', 'first' : 6 }, )

class Overview:
    """An overview: its title, and the plots (histogram strings) of the cells
    of its grid of nrows x ncols, row by row (None for empty cells)"""
    def __init__( self, title, cells, ncols, correlation_plot = False ):
        self.title, self.cells, self.ncols = title, list(cells), ncols
        self.correlation_plot = correlation_plot#(a correlation plot, see pair_cells)
        self.nrows = max( 1, math.ceil( len(self.cells) / ncols ) )

    @property
    def plots( self ):
        """The plots of the overview, in the order of its cells"""
        return [ p for p in self.cells if p is not None ]

_forms = ( 'first', 'group', 'plots', 'pairs' )

def check_spec( spec ):
    """Check a specification of an overview (see the module), as given in the
    state of the viewer: TypeError or ValueError if it is not valid"""
    if not isinstance(spec,dict):
        raise TypeError('an overview must be a JSON object with its title and one of'
                        f' {", ".join(_forms)}')
    for k in spec:
        if k not in ( 'title', 'ncols', *_forms ):
            raise ValueError(f'unknown entry "{k}" of an overview (the entries are: title,'
                             f' ncols, {", ".join(_forms)})')
    if not isinstance(spec.get('title'),str) or not spec['title'].strip():
        raise ValueError('an overview must have a "title" (a text)')
    forms = [ f for f in _forms if f in spec ]
    if len(forms) != 1:
        raise ValueError(f'the overview "{spec["title"]}" must have exactly one of'
                         f' {", ".join(_forms)}')
    v = spec[forms[0]]
    ok = ( isinstance(v,int) and v > 0 if forms[0] == 'first' else
           isinstance(v,str) if forms[0] == 'group' else
           isinstance(v,list) and bool(v) and all( isinstance(e,str) or ( e is None and
                                                   forms[0] == 'plots' ) for e in v ) )
    if not ok or not isinstance(spec.get('ncols',1),int) or spec.get('ncols',1) < 1:
        raise ValueError(f'the {forms[0]} of the overview "{spec["title"]}" is not valid'
                         ' (first is a number, group a text, plots a list of histogram'
                         ' strings or null, and pairs a list of expressions)')

def _ncols( n ):
    """Columns of a grid of n plots: 3 for 6 plots (in 2 rows), and more for
    more plots, so they fill a wide window"""
    return max( 1, min( n, math.ceil( math.sqrt( 1.5 * n ) ) ) )

def pair_cells( exprs ):
    """The cells of a correlation plot of the expressions (see the module), with the
    expression of the column on the x axis"""
    n = len(exprs)
    return [ exprs[i] if i == j else f'{exprs[j]} : {exprs[i]}' if j < i else None
             for i in range(n) for j in range(n) ]

def resolve( spec, plots, groups ):
    """The Overview of a specification (see the module), with the plots of the
    viewer (histogram strings, in order) and their groups (plot -> group), or
    None if it has no plots (e.g. a group which is not there)"""
    if 'pairs' in spec:
        cells, ncols = pair_cells(list(spec['pairs'])), len(spec['pairs'])
    else:
        if 'plots' in spec:
            cells = list(spec['plots'])
        elif 'group' in spec:
            cells = [ p for p in plots if groups.get(p) == spec['group'] ]
        else:
            cells = list(plots[:spec['first']])
        ncols = spec.get('ncols') or _ncols(len(cells))
    if not any( c is not None for c in cells ):
        return None
    return Overview(spec['title'],cells,ncols,correlation_plot = 'pairs' in spec)

def overview_figure( figures, overview ):
    """The figure of the overview, from the figures of its plots (as far as they
    are available, with empty panels for the others, and None for empty
    cells), or None if none is available. The title is that of the plots (the
    pick and edit)."""
    import copy

    from .plotting import Figure, Panel, Text
    figs = { p : figures.get(f'plot:{p}') for p in overview.plots }
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
        if len(overview.cells) > 6 and not overview.correlation_plot:
            panel.ylabel = None#(as "weights per bin" of each plot meets its neighbours)
        panels.append(panel)
    title = next( ( f.title for f in figs.values() if f is not None ), None )
    fig = Figure( title = title, nrows = overview.nrows, ncols = overview.ncols,
                  panels = panels )
    fig._correlation_plot = overview.correlation_plot#(drawn with shared axes, see _plotbackend_mpl)
    return fig
