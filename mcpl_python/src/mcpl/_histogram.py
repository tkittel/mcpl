
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

"""Histograms of values calculated with expressions from the particles in MCPL
files, and plots of them."""

#(the classes of the histograms are not public, see Histogram):
__all__ = [ 'histogram', 'histogram2d', 'plot_histograms' ]

import math
import os

from ._common import MCPLError
from ._exprcore import _dimstr
from ._expressions import ParticleFilter, ParticleValue, _as_expression
from ._exprplot import _plot_unit, _PlotValue
from ._exprsyntax import _dim_unknown
from ._histstring import (
    _as_range,
    _auto_logx,
    _bins_arg,
    _check_range,
    _display_by,
    _display_only_condition,
    _hist_defaults,
    _hist_with_args,
)
from ._numpy import np
from ._particles import _pdg_colors
from ._reader import MCPLFile


def _is_file( s ):
    """Whether s is an opened file (an MCPLFile, or a view of one)"""
    return hasattr(s,'particle_blocks') and hasattr(s,'_filename')

def _as_files( sources ):
    """List of (label,source) for a file or a list of files"""
    if isinstance(sources,(str,bytes,os.PathLike)) or _is_file(sources):
        sources = [ sources ]
    res = []
    for s in sources:
        name = s._filename if _is_file(s) else s
        res.append( (os.path.basename(os.fsdecode(name)),s) )
    if not res:
        raise MCPLError('No files given')
    return res

def _blocks( source, flt ):
    """Iterate over (picked) particle blocks in a file (an MCPLFile, or the
    name of a file, which is then closed when done)"""
    if not _is_file(source):
        with MCPLFile(source) as f:
            yield from _blocks(f,flt)
        return
    for b in source.particle_blocks:
        yield b[flt(b)] if flt is not None else b

class _DisplayByValue:
    """Values of the expression of display_by, which give the curves of the
    particles"""
    def __init__( self, expr ):
        self._v = _as_expression(ParticleValue,expr)
        self.expression = self._v.expression
        self.field = self._v._e.field
        self._is_bool = None
    def __call__( self, block ):
        return self._v(block)
    def keys( self, values ):
        """The distinct values (at most 1000), and the index of each value in
        them"""
        if self._is_bool is None and len(values):
            self._is_bool = bool(np.all((values==0)|(values==1)))
        keys, index = np.unique(values,return_inverse=True)
        if len(keys) > 1000:
            raise MCPLError(f'The expression "{self.expression}" of display_by has too many'
                            ' different values (more than 1000)')
        return keys, index.ravel()

def _display_by_label( display_by, key, unicode = False ):
    """Label of the curve of a value of the expression of display_by (with
    symbols for plots if unicode is set, see _pdg_symbols)"""
    if display_by is None or key is None:
        #No display_by, or no particles (so no values of its expression):
        return None
    name = display_by._v._e.value_label(key,unicode)
    if name is not None:
        return name
    if key in (0.0,1.0) and display_by._is_bool:
        return display_by.expression if key else f'not ({display_by.expression})'
    return f'{display_by.expression} = {key:g}'

class _Plot:
    """Common basis of Histogram, BarHistogram, Histogram2D and Points3D: the
    title (the pick, for instance), whether the values are sums of weights,
    and the plots and text tables"""
    _panel_options = ()#(keyword arguments of panel(), also for figure() and plot())
    def __init__( self, weighted, title ):
        self.weighted = weighted
        self.title = title
        self._display_bins = None#(columns needed to draw the bins exactly, see mcpltool)
        #Labels of curves or bars and notes for plots, where they differ from
        #those of texts (with symbols, see _pdg_symbols):
        self._plot_labels = {}
        self._plot_notes = {}

    def _plot_label( self, label ):
        return self._plot_labels.get(label,label)

    def _add_label( self, label, plot_label, color = None ):
        """Note the label of a curve or bar in plots (if it differs) and its
        colour (if any, see the colors of the subclasses)"""
        if plot_label != label:
            self._plot_labels[label] = plot_label
        if color is not None:
            self.colors[label] = color

    @property
    def _what( self ):
        return 'weights' if self.weighted else 'particles'

    def figure( self, **kwargs ):
        """Figure (see mcpl.plotting) with the plot (keyword arguments as for
        panel())."""
        from .plotting import Figure
        return Figure( panels = [ self.panel(**kwargs) ] )

    def plot( self, filename = None, backend = None, terminal = False, **options ):
        """Show the plot (or save it in a file if filename is given) with the
        plotting backend (name or Backend object, default is chosen as described
        in mcpl.plotting, in the terminal if terminal is True). Keyword
        arguments of panel() (like logy) are used for the plot, and others are
        options for the backend (e.g. matplotlib_backend='agg'). Returns the
        list of created files when saving."""
        kw = { k : options.pop(k) for k in self._panel_options if k in options }
        return _show_or_save([self.figure(**kw)],filename,backend,options,terminal)

    def _text_header( self, what, values, columns ):
        lines = [ f'# {what}' ] + [ f'# {t}' for t in ( self.title or '' ).splitlines() ]
        return lines + [ f'# values: {values}', '# ' + ' | '.join(columns) ]

class Histogram(_Plot):
    """1D histogram of the values of an expression, created by the histogram()
    function. The bin edges are in edges (in the unit, a text like "cm", for
    expressions with units), and the contents (sums of weights, or numbers of
    particles if unweighted) in the dictionary contents, with one entry per
    curve (keyed by label, None for a single curve, see display_by). The sums
    of squared weights are in sumw2, and the sums of weights below and above
    the edges are in underflow and overflow (with the same keys).

    Objects of this class are made by histogram(), and the class itself is not part
    of the public API (it is not made directly)."""
    _panel_options = ( 'logy', )
    def __init__( self, expression, edges, *, logx, weighted, lethargy, title, unit = None ):
        super().__init__(weighted,title)
        self.expression = expression
        self.unit = unit
        self.edges = edges
        self.logx = logx
        self.lethargy = lethargy
        self.logy = False
        self.note = None
        self.colors = {}
        self.contents = {}
        self.sumw2 = {}
        self.underflow = {}
        self.overflow = {}

    @property
    def label( self ):
        """The expression, with the unit (as in "x [cm]") and note (as in
        "(neutrons and gammas only)" for wavelengths)"""
        return _with_unit(self.expression,self.unit,self.note)

    def values( self, label = None ):
        """Values to plot: the contents (of the curve with the label, or of all
        curves together without a label), or for lethargy plots the contents
        divided by the bin widths in lethargy (ln(E2/E1))."""
        c = self.contents[label] if label in self.contents else (
            sum(self.contents.values()) if label is None and self.contents
            else self.contents[label] )
        if self.lethargy:
            return c / np.log(self.edges[1:]/self.edges[:-1])
        return c

    @property
    def ylabel( self ):
        """Label of the values (e.g. "weights per bin")"""
        return f'{self._what} per {"unit lethargy" if self.lethargy else "bin"}'

    def panel( self, logy = None ):
        """Panel (see mcpl.plotting) with the histogram, with a logarithmic y
        axis if logy is True (or 'auto', if suitable for the values; default is
        the logy option of the histogram string, see histogram())."""
        from .plotting import Panel, StepHist
        labels = list(self.contents)
        values = [ self.values(lbl) for lbl in labels ]
        logy = self.logy if logy is None else logy
        p = Panel( title = self.title, xlabel = _xlabel([ self ]), ylabel = self.ylabel,
                   logx = self.logx, logy = _log_scale(logy,values),
                   xlim = ( self.edges[0], self.edges[-1] ) )
        for i, ( label, v ) in enumerate(zip(labels,values)):
            p.add(StepHist(self.edges,v,label = self._plot_label(label) if len(labels) > 1 else None,
                           color = self.colors.get(label,i)))
        return p

    def to_text( self ):
        """Text table with the histogram contents."""
        labels = list(self.contents)
        lines = self._text_header(f'histogram of: {self.label}',self.ylabel,
                                  [ 'lower edge', 'upper edge' ]
                                  + [ 'value' if lbl is None else str(lbl) for lbl in labels ])
        vals = [ self.values(lbl) for lbl in labels ]
        for i in range(len(self.edges)-1):
            lines.append(' '.join( f'{x:.8g}' for x in [ self.edges[i], self.edges[i+1] ]
                                   + [ v[i] for v in vals ] ))
        return '\n'.join(lines)

class BarHistogram(_Plot):
    """Bar chart of the values of an expression with whole numbers, created by
    the histogram() function with bar. The contents are the sums of weights (or
    numbers of particles if unweighted) of the bars, by their labels (the
    values, or names like "n (2112)" for pdgcode values).

    Objects of this class are made by histogram() with bar, and the class itself is not part
    of the public API (it is not made directly)."""
    _panel_options = ( 'logy', )
    def __init__( self, expression, *, weighted, title ):
        super().__init__(weighted,title)
        self.expression = expression
        self.logy = False
        self.note = None
        self.colors = {}
        self.contents = {}

    @property
    def label( self ):
        """The expression, with its note (see Histogram.label)"""
        return _with_unit(self.expression,None,self.note)

    def panel( self, logy = None ):
        """Panel (see mcpl.plotting) with the bars, with a logarithmic scale of
        the bars if logy is True (or 'auto', if suitable for the values; default
        is the logy option of the histogram string, see histogram())."""
        labels = list(self.contents)
        return _bars_panel([ self._plot_label(lbl) for lbl in labels ],
                           [ self.contents[lbl] for lbl in labels ],
                           [ self.colors.get(lbl,0) for lbl in labels ],
                           self.logy if logy is None else logy, title = self.title,
                           xlabel = self._what,
                           ylabel = _with_unit(self.expression,None,
                                               self._plot_notes.get('x',self.note)))

    def to_text( self ):
        """Text table with the contents."""
        lines = self._text_header(f'bars of: {self.label}',self._what,[ 'bar', 'value' ])
        return '\n'.join( lines + [ f'{lbl} | {v:.8g}' for lbl, v in self.contents.items() ] )

class Histogram2D(_Plot):
    """2D histogram of the values of two expressions, created by the
    histogram2d() function. The contents (with shape (len(xedges)-1,
    len(yedges)-1)) are sums of weights, or numbers of particles if
    unweighted. For expressions with units, the edges are in the units xunit
    and yunit (texts like "cm", else None).

    Objects of this class are made by histogram2d(), and the class itself is not part
    of the public API (it is not made directly)."""
    _panel_options = ( 'logz', )
    def __init__( self, xexpression, yexpression, xedges, yedges, *, weighted, title,
                  xunit = None, yunit = None, logx = False, logy = False ):
        super().__init__(weighted,title)
        self.logx, self.logy = logx, logy#(logarithmic bins and axes)
        self.xexpression, self.yexpression = xexpression, yexpression
        self.xunit, self.yunit = xunit, yunit
        self.xnote, self.ynote = None, None
        self.xedges, self.yedges = xedges, yedges
        self.contents = np.zeros((len(xedges)-1,len(yedges)-1))
        self.logz = True#(the colour scale of the plot, see panel)
        #(the length per unit of the y axis relative to the x axis of the
        #plot, for equal scales of axes with the same units, or None):
        self.aspect = None

    @property
    def xlabel( self ):
        """The x expression, with its unit and note (see Histogram.label)"""
        return _with_unit(self.xexpression,self.xunit,self.xnote)

    @property
    def ylabel( self ):
        """The y expression, with its unit and note (see Histogram.label)"""
        return _with_unit(self.yexpression,self.yunit,self.ynote)

    def panel( self, logz = None ):
        """Panel (see mcpl.plotting) with the histogram, with a logarithmic
        colour scale if logz is True (default: the logz attribute, which is
        True unless the histogram string had logz=0)."""
        logz = self.logz if logz is None else logz
        from .plotting import Hist2D, Panel
        notes = self._plot_notes
        p = Panel( title = self.title,
                   xlabel = _with_unit(self.xexpression,self.xunit,notes.get('x',self.xnote)),
                   ylabel = _with_unit(self.yexpression,self.yunit,notes.get('y',self.ynote)),
                   aspect = self.aspect, logx = self.logx, logy = self.logy )
        p.add(Hist2D(self.xedges,self.yedges,self.contents,logz = logz))
        return p

    def to_text( self ):
        """Text table with the histogram contents."""
        lines = self._text_header(f'2D histogram of: {self.xlabel} : {self.ylabel}',
                                  f'{self._what} per bin',
                                  [ 'x lower edge', 'x upper edge', 'y lower edge',
                                    'y upper edge', 'value' ])
        xe, ye = self.xedges, self.yedges
        for i in range(len(xe)-1):
            for j in range(len(ye)-1):
                lines.append(' '.join( f'{x:.8g}' for x in
                                       ( xe[i], xe[i+1], ye[j], ye[j+1], self.contents[i,j] ) ))
        return '\n'.join(lines)

class Points3D(_Plot):
    """3D plot of the values of three expressions for a sample of the particles
    (as many as points, chosen at random with their weights, unless
    unweighted, so they are distributed as the particles), in groups (label
    -> array of shape (n,3), with the label None for one group, see display_by). For
    expressions with units, the values are in the units (texts like "cm",
    else None). The sample is the same for the same particles.

    Objects of this class are made by histogram() for histogram strings of
    three expressions, and the class itself is not part of the public API (it
    is not made directly)."""
    def __init__( self, expressions, *, weighted, title, units, nparticles ):
        super().__init__(weighted,title)
        self.expressions, self.units = list(expressions), list(units)
        self.notes = [ None ] * 3
        self.nparticles = nparticles#(of which the points are a sample)
        self.groups = {}
        self.colors = {}#(label -> colour index, see StepHist)

    @property
    def labels( self ):
        """The labels of the axes, with their units and notes (see
        Histogram.label)"""
        return [ _with_unit(e,u,n) for e, u, n in zip(self.expressions,self.units,self.notes) ]

    def panel( self ):
        """Panel (see mcpl.plotting) with the points"""
        from .plotting import Panel, Scatter3D
        x, y, z = self.labels
        p = Panel( title = self.title, xlabel = x, ylabel = y, zlabel = z )
        for i, ( label, pts ) in enumerate(self.groups.items()):
            p.add(Scatter3D(pts[:,0],pts[:,1],pts[:,2],label = self._plot_label(label),
                            color = self.colors.get(label,i)))
        return p

    def to_text( self ):
        """Text table with the points."""
        n = sum( len(p) for p in self.groups.values() )
        lines = self._text_header(f'3D plot of: {" : ".join(self.labels)}',
                                  f'{n} points (of {self.nparticles} particles)',
                                  [ 'x', 'y', 'z', 'group' ])
        for label, pts in self.groups.items():
            lines += [ ' '.join( f'{v:.8g}' for v in pt ) + f' {label or ""}'.rstrip()
                       for pt in pts ]
        return '\n'.join(lines)

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

def _with_unit( expression, unit, note = None ):
    """Axis label of an expression, with its unit and note (see _DomainNote)"""
    label = f'{expression} [{unit}]' if unit else expression
    return f'{label} {note}' if note else label

#Fixed colours of the values of some fields, so particle types have the same
#colours in all plots (see _particles), and those of them which other values
#never get with solid lines, so these are never confused (n, gamma, e- and p):
_fixed_colors = { 'pdgcode' : _pdg_colors }
_reserved_colors = { 'pdgcode' : { _pdg_colors[c] for c in ( 2112, 22, 11, 2212 ) } }

def _value_colors( field, keys ):
    """Colours of the values (keys) of the field, if it has fixed colours (as
    {key : colour index}, see plotting.StepHist): the other values get the
    colours which are not used in the plot (cyan first, and not the reserved
    ones), and then those of the next cycles (with dashed or dotted lines)"""
    fixed = _fixed_colors.get(field)
    if fixed is None:
        return {}
    reserved = _reserved_colors.get(field,set())
    used = { fixed[k] for k in keys if k in fixed }
    free = [ c for c in ( 9, *range(9) ) if c not in used and c not in reserved ]
    others = [ k for k in keys if k not in fixed ]
    res = { k : free[i] if i < len(free) else 10 + i - len(free)
            for i, k in enumerate(others) }
    res.update( ( k, fixed[k] ) for k in keys if k in fixed )
    return res

def _top_keys( sums, limit ):
    """The keys of the dict of sums with the limit largest sums (in order), and
    the others, which are combined into one shown as 'other' (if there are
    more than limit keys, the shown ones are then the limit-1 largest)"""
    keys = sorted( sums, key = lambda k : ( -sums[k], str(k) ) )
    if len(keys) <= limit:
        return keys, []
    return keys[:limit-1], keys[limit-1:]

def _log_scale( flag, arrays ):
    """Whether values (the arrays) get a logarithmic scale with the flag (of
    the option logy): if it is on, or with 'auto', if their positive values
    span more than two decades"""
    if flag != 'auto':
        return bool(flag)
    v = np.concatenate([ np.ravel(a) for a in arrays ]) if len(arrays) else np.zeros(0)
    v = v[v>0]
    return bool(len(v)) and _auto_logx(v.min(),v.max())

def _bars_panel( labels, values, colors, logy, title = None, xlabel = None, ylabel = None ):
    """Panel with horizontal bars, whose labels show their fractions of the
    total, with a logarithmic scale of the bars if logy is True (or 'auto', if
    suitable for the values)"""
    from .plotting import Bars, Panel
    total = float(sum(values))
    if total > 0:
        labels = [ f'{lab} ({100.0*v/total:.2f}%)' for lab, v in zip(labels,values) ]
    p = Panel( title = title, xlabel = xlabel, ylabel = ylabel,
               logx = _log_scale(logy,[ values ]) )
    p.add(Bars(labels,list(values),horizontal = True,colors = colors))
    return p

class _DomainNote:
    """Collects for which particles the values of a _PlotValue were defined
    (for expressions defined only for some, like wavelengths), for the note in
    the axis label, like "(neutrons and gammas only)", if any particles were
    left out"""
    def __init__( self, value ):
        self._v, self._seen, self._left_out = value, {}, False
    def add( self, b ):
        seen = self._v.domain_values(b)
        if not seen:
            return
        for field, vals in seen.items():
            self._seen.setdefault(field,set()).update(vals)
        self._left_out = self._left_out or not self._v._e.domain_mask(b).all()
    def note( self, unicode = False ):
        return self._v.domain_note(self._seen,unicode) if self._left_out else None

def _show_or_save( figures, filename, backend, options, terminal = False ):
    from .plotting import save, show
    if filename:
        return save(figures,filename,backend=backend,**options)
    show(figures,backend=backend,terminal=terminal,**options)
    return None

def _bin_index( v, edges, log ):
    """The bins of the values v, which are within the edges (as for
    np.histogram, the last bin includes the upper edge): from the even
    spacing of the edges (in log for logarithmic bins), corrected with the
    edges (so the rounding of the calculation does not matter)"""
    n = len(edges) - 1
    lo, hi = ( np.log(edges[0]), np.log(edges[-1]) ) if log else ( edges[0], edges[-1] )
    x = np.log(v) if log else v
    i = np.floor( ( x - lo ) * ( n / ( hi - lo ) ) ).astype(np.intp)
    np.clip(i,0,n-1,out=i)
    i -= v < edges[i]
    i += ( v >= edges[i+1] ) & ( i < n - 1 )
    return i

#The most which _nice_range adds to a range (as a fraction of it) by rounding:
_nice_waste = 0.075

def _nice_range( lo, hi ):
    """The range from lo to hi (lo < hi) of values on a linear axis, extended
    to 0 if all values have the same sign and the one closest to 0 is within
    a quarter of the range from 0 (e.g. from 0.3 to 20.5 becomes 0 to 20.5),
    and then outwards to multiples of the largest round step (1, 2, 2.5 or 5
    times a power of 10) which adds at most _nice_waste of the range (so 0 to
    20.5 becomes 0 to 21)"""
    if 0 <= lo < hi / 4:
        lo = 0.0
    elif lo / 4 < hi <= 0:
        hi = 0.0
    span = hi - lo
    e0 = math.floor(math.log10(span))
    for e in range( e0, e0 - 3, -1 ):
        for m in ( 5, 2.5, 2, 1 ):
            step = m * 10.0**e
            #(with a tolerance for rounding errors, and the edges written as
            #in decimal, e.g. 0.3 rather than 3*0.1, but always including the
            #values):
            klo, khi = math.floor( lo / step + 1e-9 ), math.ceil( hi / step - 1e-9 )
            nlo, nhi = ( float(f'{k*m:.12g}e{e}') for k in ( klo, khi ) )
            if ( nhi - nlo ) - span <= _nice_waste * span:
                return min( nlo, lo ), max( nhi, hi )
    return lo, hi

def _make_edges( rng, bins, logx ):
    lo, hi = rng
    if logx:
        if not lo > 0:
            raise MCPLError('Logarithmic binning requires a positive range')
        return np.geomspace(lo,hi,bins+1)
    return np.linspace(lo,hi,bins+1)

def _nice_nbins( maxbins ):
    """A number of bins which is at most maxbins and has many divisors (the
    largest number of divisors among the numbers of the form 2^a*3^b*5^c
    between 85% of maxbins and maxbins), so a histogram with that many bins
    can later be merged into fewer bins in many ways. Below 10 bins, maxbins
    itself is returned."""
    maxbins = int(maxbins)
    if maxbins < 10:
        return max(1,maxbins)
    best = None
    for a in _range(0,8):
        for b in _range(0,6):
            for c in _range(0,5):
                n = 2**a * 3**b * 5**c
                if 0.85 * maxbins < n <= maxbins:
                    ndiv = (a+1)*(b+1)*(c+1)
                    if best is None or (ndiv,n) > best:
                        best = (ndiv,n)
    return best[1] if best else maxbins

def _auto_nbins( neff, nbins, ndim = 1 ):
    """Number of bins (per axis) for showing a histogram made with nbins bins
    of data with an effective number of entries neff: neff^(1/(ndim+1)), which
    is the square-root rule for ndim=1, and for ndim=2 gives bins with as many
    entries on average as there are bins per axis (as for the square-root
    rule), clamped to [10,400], and then the closest divisor of nbins (in log
    distance, so the bins can be merged exactly)."""
    target = max( 1.0, neff ) ** ( 1.0 / ( ndim + 1 ) )
    target = max( 10, min( 400, round(target) ) )
    divs = [ d for d in _range(1,nbins+1) if nbins % d == 0 ]
    return min( divs, key = lambda d : abs(math.log(d/target)) )

def _neff( sumw, sumw2 ):
    """Effective number of entries (sum of weights squared over sum of squared
    weights, which is the number of entries for unit weights)"""
    return sumw * sumw / sumw2 if sumw2 > 0.0 else 0.0

_range = range#(the name range is shadowed by arguments below)

def _bins_arg( bins, ndims ):
    """The bins argument of histogram() (ndims=1) or histogram2d() (ndims=2):
    "auto", a positive number of bins, or for 2D histograms also two as
    (nx,ny)"""
    if isinstance(bins,str) and bins == 'auto':
        return bins
    def nbins( n ):
        return ( isinstance(n,(int,np.integer)) and not isinstance(n,bool)
                 and n > 0 )
    if nbins(bins):
        return int(bins)
    if ( ndims == 2 and isinstance(bins,(tuple,list)) and len(bins) == 2
         and all( nbins(n) for n in bins ) ):
        return tuple( int(n) for n in bins )
    two = ' (or two, as (nx,ny))' if ndims == 2 else ''
    raise MCPLError(f'The histogram argument bins must be "auto" or a positive'
                    f' number of bins{two}, not {bins!r}')

def histogram( files, expression, *, pick = None, bins = 'auto', range = None,
               logx = False, unweighted = False, display_by = None,
               display_only = None, lethargy = False, max_curves = None, bar = False,
               _maxbins = None ):
    """Histogram of the values of an expression (see ParticleValue) for the
    particles in one or more files (picked with pick, see ParticleFilter),
    for instance:

       h = mcpl.histogram( "myfile.mcpl", "ekin/eV",
                           pick = "pdgcode == neutron",
                           logx = True, lethargy = True )
       h.plot()

    Values with units are shown in a suitable unit, unless divided by one (as
    in "ekin/eV"), and ranges (low,high) are given with units, e.g.
    range=("1meV","10MeV"). Without a range, all values are covered, and
    without a number of bins, it is chosen from the number of particles. The
    bins are logarithmic with logx (or with logx='auto', if suitable for the
    values), and with lethargy (which implies logx), the values are divided
    by the bin widths in lethargy, ln(E2/E1). The contents are sums of
    weights, or numbers of particles if unweighted is True.

    There is a curve for each value of the expression display_by, by default
    pdgcode (a curve for each particle type), e.g. display_by="x > 0cm", or
    "single" for one curve, for at most max_curves values (by default 8),
    the others are combined into one. With several files, there is a curve for each
    file (and of each value of display_by in each file, if it is given), and
    the 2D histograms and 3D plots of histogram strings combine the files.
    With display_only (a condition, or a particle type like "neutron"), only
    those of the picked particles are used. With bar (True, or the number of bars), the result is a bar
    chart of the values (whole numbers, as of pdgcode), see BarHistogram.

    The options can also be given in the expression, as in the histogram
    strings of mcpltool -H (see mcpltool -H help), e.g.
    "ekin/eV;logx;lethargy;bins=50;logy", which can also have two
    expressions for a 2D histogram (see histogram2d()), or three for a 3D plot
    of a sample of the particles.
    """
    bins = _bins_arg(bins,1)
    given = { 'bins' : None if bins == 'auto' else bins, 'range' : range,
              'logx' : logx, 'unweighted' : unweighted, 'display_by' : display_by,
              'display_only' : display_only,
              'lethargy' : lethargy, 'groups' : max_curves,
              'bar' : bar }
    o = _hist_with_args(expression,given)
    if o['print']:
        raise MCPLError('The histogram option print is only for the mcpltool'
                        ' command (use the to_text() method of the histogram'
                        ' instead)')
    return _histogram(files,o,pick = pick,_maxbins = _maxbins)

def histogram2d( files, xexpression, yexpression, *, pick = None, bins = 'auto',
                 xrange = None, yrange = None, unweighted = False,
                 logx = False, logy = False, _maxbins = None ):
    """2D histogram of the values of two expressions (see histogram()) for the
    particles in one or more files, for instance:

       h = mcpl.histogram2d( "myfile.mcpl",
                             "x/cm", "y/cm" )
       h.plot()

    The number of bins can be given for both axes, or as a tuple (nx,ny), and
    is otherwise chosen from the effective number of entries N (the cube root
    of N per axis, between 10 and 400). The ranges of the axes can be
    given as tuples (low,high) with xrange and yrange, otherwise they cover
    all values. The bins of the axes are logarithmic with logx and logy (or
    with 'auto', if suitable for the values). The histogram contains the sum
    of weights in each bin, or the number of particles if unweighted is
    True.
    """
    bins = _bins_arg(bins,2)
    o = _hist_defaults([ xexpression, yexpression ])
    o.update( bins = _bins_arg(None if bins == 'auto' else bins,2),
              xrange = _as_range(xrange,'xrange'),
              yrange = _as_range(yrange,'yrange'), unweighted = unweighted,
              logx = logx, logy = logy )
    return _histogram(files,o,pick = pick,_maxbins = _maxbins)

def _selection_title( pick = None, edit = None, display_only = None ):
    """The title of a plot of the particles picked and edited with these
    expressions (as texts, or None), and of those shown (display_only): one
    line each, or None"""
    return '\n'.join( f'{what}: {e}' for what, e in ( ('pick',pick), ('edit',edit),
                                                      ('display_only',display_only) )
                      if e is not None ) or None

def _histogram( files, o, pick = None, _maxbins = None, selection = ( None, None ) ):
    """The histogram of the particles in the files, with the options o (see
    _parse_hist), with the selection (the expressions of the pick and edit
    applied to the particles of the files, for the title)"""
    files = _as_files(files)
    filler = _filler_for(o,pick = pick,labels = [ fl for fl,_ in files ],_maxbins = _maxbins)
    filler._selection = selection
    flt = filler.pick
    if filler.needs_range:
        for flabel,src in files:
            for b in _blocks(src,flt):
                filler.add_range(flabel,b)
        filler.start_fill()
    for flabel,src in files:
        for b in _blocks(src,flt):
            filler.add(flabel,b)
    return filler.result()

def _filler_for( o, pick = None, labels = ( None, ), _maxbins = None ):
    """The filler of a histogram with the options o (see _parse_hist): blocks of
    (picked) particles of the files with the labels are given to it as in
    _histogram, and its result() is the histogram of the blocks so far."""
    bins = o['bins'] or 'auto'
    #(with several files, 1D histograms have a curve for each file, unless
    #display_by is given, instead of one for each particle type in each file,
    #while 2D histograms and 3D plots combine the files):
    by_file = len(labels) > 1 and o['display_by'] is None and len(o['exprs']) == 1
    display_by = None if by_file else _display_by(o)
    display_only = ( _display_only_condition(o['display_only'])
                     if o['display_only'] is not None else None )
    if len(o['exprs']) == 3:
        return _Points3DFiller(o['exprs'],pick = pick,points = o['points'],
                               unweighted = o['unweighted'],display_by = display_by,
                               max_curves = o['groups'] or 8,
                               display_only = display_only)
    if len(o['exprs']) == 2:
        return _Hist2DFiller(o['exprs'][0],o['exprs'][1],pick = pick,bins = bins,
                             xrange = o['xrange'],yrange = o['yrange'],
                             unweighted = o['unweighted'],_maxbins = _maxbins,
                             logz = o['logz'] is not False,equal = o['equal'],
                             display_only = display_only,logx = o['logx'],
                             logy = o['logy'] or False)
    if o['bar'] is not False:
        return _BarFiller(o['exprs'][0],pick = pick,
                          limit = 10 if o['bar'] is True else o['bar'],
                          unweighted = o['unweighted'],logy = o['logy'],labels = labels,
                          display_only = display_only)
    return _Hist1DFiller(o['exprs'][0],pick = pick,bins = bins,range = o['range'],
                         logx = o['logx'],unweighted = o['unweighted'],display_by = display_by,
                         lethargy = o['lethargy'],max_curves = o['groups'] or 8,
                         logy = o['logy'] or False,labels = labels,_maxbins = _maxbins,
                         display_only = display_only)

class _Filler:
    """Common basis of the fillers, which make histograms from blocks of (picked)
    particles of files: if needs_range, the blocks are first given to
    add_range (to find the ranges of the values), and then, after start_fill,
    to add. The labels are those of the files, and result() is the histogram
    of the blocks given to add so far. With display_only (a pick, see
    ParticleFilter, the option display_only of histogram strings), only those
    particles of the blocks are used."""
    needs_range = False
    def __init__( self, expressions, pick, unweighted, labels, display_only = None ):
        self.pick = _as_expression(ParticleFilter,pick)
        self._only = _as_expression(ParticleFilter,display_only)
        self._vals = [ _PlotValue(e) for e in expressions ]
        #(ranges whose units are checked when the units of the expressions are
        #known, see _range_of):
        self._unchecked = []
        self._notes = [ _DomainNote(v) for v in self._vals ]
        self._weighted = not unweighted
        self._labels = list(labels)
        #(the ranges of the values found by add_range, in the units of MCPL):
        self._lims = [ [ np.inf, -np.inf ] for _ in expressions ]
        self._positive = [ False for _ in expressions ]

    #(the pick and edit applied to the particles before they are given to the
    #filler, as expressions, for the title, see _selection_title):
    _selection = ( None, None )

    @property
    def _title( self ):
        pick, edit = self._selection
        return _selection_title(pick or ( self.pick and self.pick.expression ),edit,
                                self._only and self._only.expression)

    def _curves( self, sums, limit, field, name, flabel = None ):
        """The curves (or bars) of the values with the sums (a dict by key):
        those of the limit largest sums, and one of the others (if any), as
        (keys, label, plot label, colour index or None), with labels from
        name(key, unicode) (see _Plot._plot_labels), or 'other', and the
        colours of the values of the field (if any), or with the label flabel
        of the file before the labels (of several files, without colours)"""
        shown, rest = _top_keys(sums,limit)
        entries = [ ( [ k ], k ) for k in shown ] + ( [ ( rest, 'other' ) ] if rest else [] )
        colors = ( {} if field is None or flabel is not None
                   else _value_colors(field,[ k for _, k in entries ]) )
        res = []
        for keys, k in entries:
            lbl, plbl = ( 'other' if k == 'other' else name(k,u) for u in ( False, True ) )
            if flabel is not None:
                lbl, plbl = ( flabel if x is None else f'{flabel}: {x}' for x in ( lbl, plbl ) )
            res.append( ( keys, lbl, plbl, colors.get(k) ) )
        return res

    def _display_by_values( self, dby, b, defined ):
        """The values of the expression of display_by (see _DisplayByValue) of
        the particles of the block b with defined values (see _values)"""
        return np.asarray(dby(b),dtype=float)[defined]

    def _used( self, b ):
        """The mask of the particles of the block which are used (see
        display_only), or None for all"""
        return None if self._only is None else np.asarray(self._only(b),dtype=bool)

    def _values( self, b ):
        """The values of the expressions, and the weights, of the particles of
        the block which are used and for which the expressions are defined (and
        the mask of those)"""
        used = self._used(b)
        for n in self._notes:
            n.add(b if used is None else b[used])
        vals = [ np.asarray(v(b),dtype=float) for v in self._vals ]
        for check in self._unchecked:#(now that the units are known)
            check()
        self._unchecked = []
        w = np.broadcast_to(b.weight if self._weighted else 1.0,(len(b),))
        #(values are NaN where the expressions are not defined):
        defined = ~np.any([ np.isnan(v) for v in vals ],axis=0)
        if used is not None:
            defined &= used
        if not defined.all():
            vals, w = [ v[defined] for v in vals ], w[defined]
        return vals, w, defined

    def add_range( self, flabel, b ):
        used = self._used(b)
        for lim, v, positive in zip(self._lims,self._vals,self._positive):
            x = np.asarray(v(b),dtype=float)
            if used is not None:
                x = x[used]
            x = x[np.isfinite(x)&(x>0)] if positive else x[np.isfinite(x)]
            if len(x):
                lim[0], lim[1] = min(lim[0],x.min()), max(lim[1],x.max())

    def _found_range( self, i, log = False, nice = True ):
        """The range of the values of expression i found by add_range (for
        linear axes extended to round values, unless nice is False, see
        _nice_range)"""
        lo, hi = self._lims[i]
        if not lo <= hi:
            only = ( f', or none with display_only={self._only.expression}'
                     if self._only is not None else '' )
            raise MCPLError(f'No values to histogram (no particles picked{only}?)')
        if lo == hi:
            return ( lo/2, lo*2 ) if log else ( lo - 1.0, hi + 1.0 )
        return ( lo, hi ) if log or not nice else _nice_range(lo,hi)

    def _range_of( self, rng, i, name ):
        """The given range (see _as_range) of expression i, in the units of MCPL"""
        rng = _as_range(rng,name)
        _check_range(rng,self._vals[i],name)
        if rng is not None and self._vals[i].dim == _dim_unknown:
            #(e.g. of userdata, see _values):
            self._unchecked.append( lambda : _check_range(rng,self._vals[i],name) )
        return ( rng.lo, rng.hi ) if rng is not None else None

class _Hist1DFiller(_Filler):
    """Makes the histogram of histogram() (see _Filler)"""
    def __init__( self, expression, pick = None, bins = 'auto', range = None,
                  logx = False, unweighted = False, display_by = None,
                  lethargy = False, max_curves = 8, logy = False,
                  labels = ( None, ), _maxbins = None, display_only = None ):
        super().__init__([ expression ],pick,unweighted,labels,display_only)
        self._dby = _DisplayByValue(display_by) if display_by is not None else None
        #(with logx='auto', it is decided from the range, see _auto_logx):
        self._logx = True if lethargy else logx
        self._positive[0] = self._logx is True
        self._lethargy, self._logy = lethargy, logy
        self._bins, self._maxbins, self._max_curves = bins, _maxbins, max_curves
        self._range = self._range_of(range,0,'range')
        self.needs_range = self._range is None
        if not self.needs_range:
            self._setup()

    def start_fill( self ):
        if self._logx == 'auto':
            self._logx = _auto_logx(*self._found_range(0,nice=False))
        self._range = self._found_range(0,self._logx)
        self._setup()

    def _setup( self ):
        if self._logx == 'auto':#(with a given range)
            self._logx = _auto_logx(*self._range)
        self._auto = ( self._bins == 'auto' )
        self._nbins = _nice_nbins(self._maxbins or 1200) if self._auto else int(self._bins)
        self._edges = _make_edges(self._range,self._nbins,self._logx)
        self._acc = {}#(file label,display_by key) -> [contents,sumw2,underflow,overflow]

    def add( self, flabel, b ):
        edges, dby = self._edges, self._dby
        n = len(edges) - 1
        ( v, ), w, defined = self._values(b)
        if dby is not None:
            keys, kidx = dby.keys(self._display_by_values(dby,b,defined))
        else:
            keys, kidx = [ None ], np.zeros(len(v),dtype=np.intp)
        #(all curves at once: the sums by curve and bin, below and above):
        nk = len(keys)
        inside = ( v >= edges[0] ) & ( v <= edges[-1] )
        flat = kidx[inside] * n + _bin_index(v[inside],edges,self._logx)
        wi = w[inside]
        sums = np.bincount(flat,weights=wi,minlength=nk*n).reshape(nk,n)
        sums2 = np.bincount(flat,weights=wi*wi,minlength=nk*n).reshape(nk,n)
        under, over = ( np.bincount(kidx[m],weights=w[m],minlength=nk)
                        for m in ( v < edges[0], v > edges[-1] ) )
        for j, k in enumerate(keys):
            a = self._acc.setdefault((flabel,k),[ np.zeros(n), np.zeros(n), 0.0, 0.0 ])
            a[0] += sums[j]
            a[1] += sums2[j]
            a[2] += float(under[j])
            a[3] += float(over[j])

    def result( self ):
        edges, nbins, dby = self._edges, self._nbins, self._dby
        acc = { k : list(a) for k, a in self._acc.items() }
        #With automatic binning, merge the bins according to the effective number
        #of entries:
        if self._auto:
            sumw = sum( a[0].sum() for a in acc.values() )
            sumw2 = sum( a[1].sum() for a in acc.values() )
            k = nbins // _auto_nbins(_neff(sumw,sumw2),nbins)
            if k > 1:
                edges = edges[::k]
                for a in acc.values():
                    a[0] = a[0].reshape(-1,k).sum(axis=1)
                    a[1] = a[1].reshape(-1,k).sum(axis=1)
        #(the unit of the axis, for expressions with units, which for userdata
        #are known when particles were read):
        v = self._vals[0]
        unit, scale = _plot_unit(v.dim,*self._range,self._logx,v.wavelength)
        h = Histogram(self._vals[0].expression,edges/scale,logx=self._logx,
                      weighted=self._weighted,lethargy=self._lethargy,title=self._title,
                      unit=unit)
        h.logy = self._logy
        h.note, h._plot_notes['x'] = ( self._notes[0].note(u) for u in ( False, True ) )
        h._display_bins = nbins if self._auto else None
        #The curves, by total weight (per file), with the smallest ones combined:
        multifile = len(self._labels) > 1
        empty = [ np.zeros(len(edges)-1), np.zeros(len(edges)-1), 0.0, 0.0 ]
        for flabel in self._labels:
            sums = { k : a[0].sum() for (fl,k), a in acc.items() if fl == flabel }
            for keys, lbl, plbl, color in self._curves(sums or { None : 0.0 },self._max_curves,
                                                       dby and dby.field,
                                                       lambda k, u : _display_by_label(dby,k,u),
                                                       flabel if multifile else None):
                parts = [ acc.get((flabel,k),empty) for k in keys ]
                a = [ sum( p[i] for p in parts ) for i in range(4) ]
                h.contents[lbl], h.sumw2[lbl] = a[0], a[1]
                h.underflow[lbl], h.overflow[lbl] = a[2], a[3]
                h._add_label(lbl,plbl,color)
        return h

class _BarFiller(_Filler):
    """Makes the bar charts of histogram() with bar (see _Filler; no range is
    needed)"""
    def __init__( self, expression, pick = None, limit = 10, unweighted = False,
                  logy = None, labels = ( None, ), display_only = None ):
        super().__init__([ expression ],pick,unweighted,labels,display_only)
        #(the units of fields of the userdata are checked with the values):
        if self._vals[0].dim not in ( None, _dim_unknown ):
            self._not_whole()
        self._limit, self._logy = limit, logy
        self._sums = { fl : {} for fl in self._labels }

    def _not_whole( self ):
        raise MCPLError('Bar charts are of whole numbers without units, like pdgcode'
                        f' or round(x/cm), not of "{self._vals[0].expression}"')

    def add( self, flabel, b ):
        ( v, ), w, _ = self._values(b)
        if self._vals[0].dim is not None or not np.all( v == np.floor(v) ):
            self._not_whole()
        keys, idx = np.unique(v,return_inverse=True)
        sums = self._sums[flabel]
        for k, s in zip(keys.tolist(),np.bincount(idx,weights=w,minlength=len(keys))):
            sums[int(k)] = sums.get(int(k),0.0) + float(s)
        if len(sums) > 1000:
            raise MCPLError(f'Bar chart of "{self._vals[0].expression}" has too many'
                            ' different values (more than 1000)')

    def result( self ):
        e = self._vals[0]
        h = BarHistogram(e.expression,weighted=self._weighted,title=self._title)
        if self._logy is not None:
            h.logy = self._logy
        h.note, h._plot_notes['x'] = ( self._notes[0].note(u) for u in ( False, True ) )
        multifile = len(self._labels) > 1
        for flabel, sums in self._sums.items():
            for keys, lbl, plbl, color in self._curves(sums,self._limit,e._e.field,
                                                       lambda k, u : e._e.value_label(k,u) or str(k),
                                                       flabel if multifile else None):
                h.contents[lbl] = sum( sums[k] for k in keys )
                h._add_label(lbl,plbl,color)
        return h

class _Hist2DFiller(_Filler):
    """Makes the histogram of histogram2d() (see _Filler; the files are
    combined)"""
    def __init__( self, xexpression, yexpression, pick = None, bins = 'auto',
                  xrange = None, yrange = None, unweighted = False,
                  _maxbins = None, logz = True, equal = False, display_only = None,
                  logx = False, logy = False ):
        super().__init__([ xexpression, yexpression ],pick,unweighted,( None, ),
                         display_only)
        self._bins, self._maxbins, self._logz, self._equal = bins, _maxbins, logz, equal
        #(logarithmic axes, or 'auto' to decide from the ranges, see _auto_logx):
        self._log = [ logx, logy ]
        self._positive = [ lg is True for lg in self._log ]
        if equal:
            #(checked when the units are known, e.g. of userdata, see _values):
            if _dim_unknown in ( self._vals[0].dim, self._vals[1].dim ):
                self._unchecked.append(self._check_equal)
            else:
                self._check_equal()
        self._ranges = [ self._range_of(xrange,0,'xrange'), self._range_of(yrange,1,'yrange') ]
        self.needs_range = None in self._ranges
        if not self.needs_range:
            self._setup()

    def _check_equal( self ):
        if self._vals[0].dim != self._vals[1].dim:
            raise MCPLError('Equal scales of the axes (the histogram option "equal")'
                            ' need expressions with the same units, not'
                            f' {_dimstr(self._vals[0].dim)} and {_dimstr(self._vals[1].dim)}'
                            f' (of {self._vals[0].expression} and {self._vals[1].expression})')

    def start_fill( self ):
        for i, r in enumerate(self._ranges):
            if r is None and self._log[i] == 'auto':
                self._log[i] = _auto_logx(*self._found_range(i,nice=False))
        self._ranges = [ r or self._found_range(i,self._log[i])
                         for i, r in enumerate(self._ranges) ]
        self._setup()

    def _setup( self ):
        #(with given ranges, 'auto' is decided from them):
        self._log = [ _auto_logx(*r) if lg == 'auto' else bool(lg)
                      for lg, r in zip(self._log,self._ranges) ]
        bins = self._bins
        self._auto = ( isinstance(bins,str) and bins == 'auto' )
        if self._auto:
            mx, my = self._maxbins if self._maxbins else ( 400, 400 )
            bx, by = _nice_nbins(mx), _nice_nbins(my)
        else:
            bx, by = bins if isinstance(bins,(tuple,list)) else ( bins, bins )
            bx, by = int(bx), int(by)
        self._bx, self._by = bx, by
        self._xe, self._ye = ( _make_edges(r,n,lg) for r, n, lg in
                               zip(self._ranges,(bx,by),self._log) )
        self._contents = np.zeros((bx,by))
        self._sumw, self._sumw2 = 0.0, 0.0

    def add( self, flabel, b ):
        xe, ye = self._xe, self._ye
        ( x, y ), w, _ = self._values(b)
        inside = ( x >= xe[0] ) & ( x <= xe[-1] ) & ( y >= ye[0] ) & ( y <= ye[-1] )
        #(as np.histogram2d, but much faster, see _bin_index):
        flat = ( _bin_index(x[inside],xe,self._log[0]) * self._by
                 + _bin_index(y[inside],ye,self._log[1]) )
        wi = w[inside]
        self._contents += np.bincount(flat,weights=wi,
                                      minlength=self._bx*self._by).reshape(self._bx,self._by)
        self._sumw += float(wi.sum())
        self._sumw2 += float((wi*wi).sum())

    def result( self ):
        xe, ye, contents, bx, by = self._xe, self._ye, self._contents, self._bx, self._by
        if self._auto:
            neff = _neff(self._sumw,self._sumw2)
            kx, ky = bx // _auto_nbins(neff,bx,2), by // _auto_nbins(neff,by,2)
            if kx > 1 or ky > 1:
                xe, ye = xe[::kx], ye[::ky]
                contents = contents.reshape(bx//kx,kx,by//ky,ky).sum(axis=(1,3))
        #(the units of the axes, for expressions with units, see
        #_Hist1DFiller.result):
        ( xunit, xscale ), ( yunit, yscale ) = ( _plot_unit(v.dim,*r,lg,v.wavelength) for v, r, lg
                                                 in zip(self._vals,self._ranges,self._log) )
        h = Histogram2D(self._vals[0].expression,self._vals[1].expression,xe/xscale,
                        ye/yscale,weighted=self._weighted,title=self._title,xunit=xunit,
                        yunit=yunit,logx=self._log[0],logy=self._log[1])
        h.xnote, h.ynote = ( n.note() for n in self._notes )
        h._plot_notes['x'], h._plot_notes['y'] = ( n.note(True) for n in self._notes )
        h.contents += contents
        h._display_bins = ( bx, by ) if self._auto else None
        h.logz = self._logz
        if self._equal:
            #(the axes are in the units of the scales xscale and yscale):
            h.aspect = yscale / xscale
        return h

class _Points3DFiller(_Filler):
    """The filler of 3D plots (see Points3D): a random sample of the points
    (weighted, with the method of Efraimidis and Spirakis: the points with the
    largest u^(1/w), for random u in [0,1)), which needs no ranges"""
    def __init__( self, expressions, pick = None, points = None, unweighted = False,
                  display_by = None, max_curves = 8, display_only = None ):
        super().__init__(list(expressions),pick,unweighted,( None, ),display_only)
        self._npoints = points or 5000
        self._dby = _DisplayByValue(display_by) if display_by is not None else None
        self._max_curves = max_curves
        #(a fixed seed, so the same particles give the same sample):
        self._rng = np.random.default_rng(12345)
        self._keys, self._pts, self._sv = np.zeros(0), np.zeros((0,3)), np.zeros(0)
        self._n = 0

    def add( self, flabel, b ):
        vals, w, defined = self._values(b)
        pts = np.column_stack(vals)
        sv = ( self._display_by_values(self._dby,b,defined) if self._dby is not None
               else np.zeros(len(pts)) )
        ok = np.isfinite(pts).all(axis=1) & ( w > 0 )
        pts, w, sv = pts[ok], w[ok], sv[ok]
        self._n += len(pts)
        keys = self._rng.random(len(pts)) ** ( 1.0 / w )
        keys, pts, sv = ( np.concatenate(( a, b )) for a, b in ( ( self._keys, keys ),
                                                                ( self._pts, pts ),
                                                                ( self._sv, sv ) ) )
        if len(keys) > self._npoints:
            keep = np.argpartition(keys,-self._npoints)[-self._npoints:]
            keys, pts, sv = keys[keep], pts[keep], sv[keep]
        self._keys, self._pts, self._sv = keys, pts, sv

    def result( self ):
        pts, dby = self._pts, self._dby
        units = []
        for i, v in enumerate(self._vals):
            lo, hi = ( pts[:,i].min(), pts[:,i].max() ) if len(pts) else ( 0.0, 1.0 )
            units.append(_plot_unit(v.dim,lo,hi,False,v.wavelength))
        res = Points3D([ v.expression for v in self._vals ],weighted = self._weighted,
                       title = self._title,units = [ u for u, _ in units ],
                       nparticles = self._n)
        res.notes = [ n.note() for n in self._notes ]
        scaled = pts / np.array([ s for _, s in units ]) if len(pts) else pts
        if dby is None:
            res.groups[None] = scaled
            return res
        #(keys() also notes whether the values are true/false, for the labels):
        keys, kidx = dby.keys(self._sv)
        counts = dict(zip(keys,np.bincount(kidx,minlength=len(keys)).tolist()))
        for keys, lbl, plbl, color in self._curves(counts or { None : 0 },self._max_curves,
                                                   dby.field,
                                                   lambda k, u : _display_by_label(dby,k,u)):
            res.groups[lbl] = scaled[np.isin(self._sv,keys)]
            res._add_label(lbl,plbl,color)
        return res

def plot_histograms( histograms, filename = None, backend = None, logy = None,
                     overlay = False, labels = None, **options ):
    """Show histograms (or save them in a file if filename is given) with the
    plotting backend and options (see Histogram.plot, logy is by default that of
    each histogram, see histogram()). Each histogram is
    shown in a separate figure (e.g. on separate pages of a PDF file), or
    with overlay=True, all the (1D) histograms are drawn in the same plot
    with a legend, for instance to compare histograms of the same expression
    from different simulations. The legend shows the labels if given, and otherwise the titles (picks) or
    expressions of the histograms. Returns the list of created files when
    saving."""
    from .plotting import Figure, Panel, StepHist
    histograms = list(histograms)
    if not overlay:
        figs = [ h.figure(**( {} if logy is None or 'logy' not in h._panel_options
                              else { 'logy' : logy } )) for h in histograms ]
        return _show_or_save(figs,filename,backend,options)
    if not histograms:
        raise MCPLError('No histograms to plot')
    if not all( isinstance(h,Histogram) for h in histograms ):
        raise MCPLError('Only 1D histograms can be overlaid')
    if labels is not None and len(labels) != len(histograms):
        raise MCPLError('The number of labels must be the number of histograms')
    first = histograms[0]
    logy = first.logy if logy is None else logy
    p = Panel( xlabel = _xlabel(histograms), ylabel = first.ylabel, logx = first.logx,
               logy = _log_scale(logy,[ h.values(c) for h in histograms for c in h.contents ]),
               xlim = ( min( h.edges[0] for h in histograms ),
                        max( h.edges[-1] for h in histograms ) ) )
    #(all curves with their own colour, as those of several histograms can be
    #of the same particle type):
    color = 0
    for i,h in enumerate(histograms):
        name = labels[i] if labels is not None else ( h.title or h.expression )
        for curve in h.contents:
            #(the curve of a histogram with one curve, e.g. of one particle
            #type, is named as the histogram):
            label = ( name if curve is None or len(h.contents) == 1
                      else f'{name}: {h._plot_label(curve)}' )
            p.add(StepHist(h.edges,h.values(curve),label = label,color = color))
            color += 1
    return _show_or_save([Figure(panels = [p])],filename,backend,options)
