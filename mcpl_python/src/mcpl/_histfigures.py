
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

"""The plots of the histograms of _histfill, as figures (see _figures, which
the plotting module shows and saves). This module does not use the plotting
module (so it can be used where plots are never shown, like in background
threads)."""

__all__ = []

from ._figures import Bars, Figure, Hist2D, Panel, Scatter3D, StepHist
from ._histfill import (
    _Hist1DData,
    _Hist2DData,
    _HistDiscreteData,
    _PointSet3DData,
    _with_unit,
)
from ._histstring import _auto_logx
from ._numpy import np


def figure( h ):
    """Figure with the plot of the histogram h (of _histfill)"""
    return Figure( panels = [ panel(h) ] )

def panel( h ):
    """Panel with the plot of the histogram h (of _histfill), with the
    logarithmic scales of its options (see the histogram strings)"""
    for cls, fct in ( ( _Hist1DData, _hist1d_panel ), ( _HistDiscreteData, _bars_of ),
                      ( _Hist2DData, _hist2d_panel ), ( _PointSet3DData, _points3d_panel ) ):
        if isinstance(h,cls):
            return fct(h)
    raise TypeError(f'Not a histogram: {h!r}')

def _hist1d_panel( h ):
    labels = list(h.contents)
    values = [ h.values(lbl) for lbl in labels ]
    p = Panel( title = h.title, xlabel = _xlabel([ h ]), ylabel = h.ylabel,
               logx = h.logx, logy = _log_scale(h.logy,values),
               xlim = ( h.edges[0], h.edges[-1] ) )
    for i, ( label, v ) in enumerate(zip(labels,values)):
        p.add(StepHist(h.edges,v,label = h._plot_label(label) if len(labels) > 1 else None,
                       color = h.colors.get(label,i)))
    return p

def _bars_of( h ):
    labels = list(h.contents)
    return _bars_panel([ h._plot_label(lbl) for lbl in labels ],
                       [ h.contents[lbl] for lbl in labels ],
                       [ h.colors.get(lbl,0) for lbl in labels ],
                       h.logy, title = h.title, xlabel = h._what,
                       ylabel = _with_unit(h.expression,None,h._plot_notes.get('x',h.note)))

def _hist2d_panel( h ):
    notes = h._plot_notes
    p = Panel( title = h.title,
               xlabel = _with_unit(h.xexpression,h.xunit,notes.get('x',h.xnote)),
               ylabel = _with_unit(h.yexpression,h.yunit,notes.get('y',h.ynote)),
               aspect = h.aspect, logx = h.logx, logy = h.logy )
    p.add(Hist2D(h.xedges,h.yedges,h.contents,logz = _log_scale(h.logz,[ h.contents ])))
    return p

def _points3d_panel( h ):
    x, y, z = h.labels
    p = Panel( title = '\n'.join( t for t in ( h.title, points_note(h) ) if t ),
               xlabel = x, ylabel = y, zlabel = z, aspect = 1 if h.equal else None )
    for i, ( label, pts ) in enumerate(h.groups.items()):
        p.add(Scatter3D(pts[:,0],pts[:,1],pts[:,2],label = h._plot_label(label),
                        color = h.colors.get(label,i)))
    return p

def points_note( h ):
    """What the points of a 3D plot (the result of _PointSet3DFiller) are: all
    particles, or which of them"""
    n = sum( len(p) for p in h.groups.values() )
    if n >= h.nparticles:
        return f'all {h.nparticles:,} particles shown'
    how = 'according to weights' if h.weighted else 'all equally likely'
    return f'{n:,} of {h.nparticles:,} particles, randomly sampled {how}'

def _xlabel( histograms ):
    """The label of the x axis of a plot of the (1D) histograms: their
    expression with its unit and note (see _DomainNote), or those of each
    one if they differ, and the part of the weights (or particles) outside
    the plot range, if any"""
    labels = dict.fromkeys( _with_unit(h.expression,h.unit,h._plot_notes.get('x',h.note))
                            for h in histograms )
    label = ', '.join(labels)
    outside = sum( sum(h.underflow.values()) + sum(h.overflow.values()) for h in histograms )
    total = outside + sum( c.sum() for h in histograms for c in h.contents.values() )
    if outside and total:
        label += f'\n({100.0*outside/total:.3g}% of {histograms[0]._what} outside plot range)'
    return label

def _log_scale( flag, arrays ):
    """Whether values (the arrays) get a logarithmic scale with the flag (of
    the option logy or logz): if it is on, or with 'auto', if their positive
    values span more than two decades"""
    if flag != 'auto':
        return bool(flag)
    v = np.concatenate([ np.ravel(a) for a in arrays ]) if len(arrays) else np.zeros(0)
    v = v[v>0]
    return bool(len(v)) and _auto_logx(v.min(),v.max())

def _bars_panel( labels, values, colors, logy, title = None, xlabel = None, ylabel = None ):
    """Panel with horizontal bars, whose labels show their fractions of the
    total, with a logarithmic scale of the bars if logy is True (or 'auto', if
    suitable for the values)"""
    total = float(sum(values))
    if total > 0:
        labels = [ f'{lab} ({100.0*v/total:.2f}%)' for lab, v in zip(labels,values) ]
    p = Panel( title = title, xlabel = xlabel, ylabel = ylabel,
               logx = _log_scale(logy,[ values ]) )
    p.add(Bars(labels,list(values),horizontal = True,colors = colors))
    return p
