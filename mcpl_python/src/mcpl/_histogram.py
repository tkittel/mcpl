
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

__all__ = [ 'BarHistogram', 'Histogram', 'Histogram2D', 'histogram', 'histogram2d',
            'plot_histograms' ]

import os

from ._common import MCPLError
from ._expressions import (
    ParticleFilter,
    ParticleValue,
    _plot_unit,
    _PlotValue,
)
from ._histstring import (
    _as_range,
    _check_range,
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
    """Iterate over (picked) particle blocks in a file"""
    f = source if _is_file(source) else MCPLFile(source)
    for b in f.particle_blocks:
        yield b[flt(b)] if flt is not None else b

def _auto_logx( lo, hi ):
    """Whether values from lo to hi get a logarithmic axis with logx='auto':
    if they are positive and span more than two decades (as in the overview
    of collect_stats)"""
    return bool( lo > 0 and hi > 100 * lo )

def _as( cls, expr ):
    if expr is None or isinstance(expr,cls):
        return expr
    return cls(expr)

class _SplitValue:
    """Values used to split particles into separate curves"""
    def __init__( self, expr ):
        self._v = _as(ParticleValue,expr)
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
            raise MCPLError(f'Split expression "{self.expression}" has too many'
                            ' different values (more than 1000)')
        return keys, index.ravel()

def _split_label( split, key, unicode = False ):
    """Label of the curve of a value of the split expression (with symbols for
    plots if unicode is set, see _pdg_symbols)"""
    if split is None or key is None:
        #No split, or no particles (so no values of the split expression):
        return None
    name = split._v._e.value_label(key,unicode)
    if name is not None:
        return name
    if key in (0.0,1.0) and split._is_bool:
        return split.expression if key else f'not ({split.expression})'
    return f'{split.expression} = {key:g}'

class _Plot:
    """Common basis of Histogram, BarHistogram and Histogram2D: the title (the
    pick, for instance), whether the values are sums of weights, and the plots
    and text tables"""
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
    curve (keyed by label, None for a single curve). The sums of squared
    weights are in sumw2, and the sums of weights below and above the edges
    are in underflow and overflow (with the same keys)."""
    _panel_options = ( 'logy', )
    def __init__( self, expression, edges, logx, weighted, lethargy, title, unit = None ):
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
        """Values to plot: the contents, or for lethargy plots the contents
        divided by the bin widths in lethargy (ln(E2/E1))."""
        c = self.contents[label]
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
        p = Panel( title = self.title,
                   xlabel = _with_unit(self.expression,self.unit,self._plot_notes.get('x',self.note)),
                   ylabel = self.ylabel,
                   logx = self.logx, logy = _auto_log(values) if logy == 'auto' else bool(logy),
                   xlim = ( self.edges[0], self.edges[-1] ) )
        for i, ( label, v ) in enumerate(zip(labels,values)):
            p.add(StepHist(self.edges,v,label = self._plot_label(label) if len(labels) > 1 else None,
                           color = self.colors.get(label,i)))
        outside = sum(self.underflow.values()) + sum(self.overflow.values())
        total = outside + sum( c.sum() for c in self.contents.values() )
        if outside and total:
            p.xlabel += f'\n({100.0*outside/total:.3g}% of {self._what} outside plot range)'
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
    values, or names like "n (2112)" for pdgcode values)."""
    _panel_options = ( 'logy', )
    def __init__( self, expression, weighted, title ):
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
    and yunit (texts like "cm", else None)."""
    _panel_options = ( 'logz', )
    def __init__( self, xexpression, yexpression, xedges, yedges, weighted, title,
                  xunit = None, yunit = None ):
        super().__init__(weighted,title)
        self.xexpression, self.yexpression = xexpression, yexpression
        self.xunit, self.yunit = xunit, yunit
        self.xnote, self.ynote = None, None
        self.xedges, self.yedges = xedges, yedges
        self.contents = np.zeros((len(xedges)-1,len(yedges)-1))

    @property
    def xlabel( self ):
        """The x expression, with its unit and note (see Histogram.label)"""
        return _with_unit(self.xexpression,self.xunit,self.xnote)

    @property
    def ylabel( self ):
        """The y expression, with its unit and note (see Histogram.label)"""
        return _with_unit(self.yexpression,self.yunit,self.ynote)

    def panel( self, logz = True ):
        """Panel (see mcpl.plotting) with the histogram, with a logarithmic
        colour scale if logz is True."""
        from .plotting import Hist2D, Panel
        notes = self._plot_notes
        p = Panel( title = self.title,
                   xlabel = _with_unit(self.xexpression,self.xunit,notes.get('x',self.xnote)),
                   ylabel = _with_unit(self.yexpression,self.yunit,notes.get('y',self.ynote)) )
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

def _with_unit( expression, unit, note = None ):
    """Axis label of an expression, with its unit and note (see _DomainNote)"""
    label = f'{expression} [{unit}]' if unit else expression
    return f'{label} {note}' if note else label

#Fixed colours of the values of some fields, so particle types have the same
#colours in all plots (see _particles):
_fixed_colors = { 'pdgcode' : _pdg_colors }
#(colours of other values):
_other_colors = ( 9, )

def _value_colors( field, keys ):
    """Colours of the values (keys) of the field, if it has fixed colours (as
    {key : colour})"""
    fixed = _fixed_colors.get(field)
    if fixed is None:
        return {}
    others = [ k for k in keys if k not in fixed ]
    res = { k : _other_colors[i % len(_other_colors)] for i, k in enumerate(others) }
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

def _auto_log( arrays ):
    """Whether values get a logarithmic scale with logy='auto': if their
    positive values span more than two decades"""
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
               logx = _auto_log([ values ]) if logy == 'auto' else bool(logy) )
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
    """Number of bins for showing a histogram made with nbins bins of data with
    an effective number of entries neff: the square-root rule (per axis for
    ndim=2), clamped to [10,400], and then the closest divisor of nbins (in
    log distance, so the bins can be merged exactly)."""
    import math
    target = max( 1.0, neff ) ** ( 0.5 / ndim )
    target = max( 10, min( 400, round(target) ) )
    divs = [ d for d in _range(1,nbins+1) if nbins % d == 0 ]
    return min( divs, key = lambda d : abs(math.log(d/target)) )

def _neff( sumw, sumw2 ):
    """Effective number of entries (sum of weights squared over sum of squared
    weights, which is the number of entries for unit weights)"""
    return sumw * sumw / sumw2 if sumw2 > 0.0 else 0.0

_range = range#(the name range is shadowed by arguments below)

def histogram( files, expression, pick = None, bins = 'auto', range = None,
               logx = False, unweighted = False, split = None, lethargy = False,
               max_curves = 8, bar = False, _maxbins = None ):
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

    With split, there is a curve for each value of that expression (for at
    most max_curves values, the others are combined into one), e.g.
    split="pdgcode" or split="x > 0cm", and with several files, a curve for
    each file. With bar (True, or the number of bars), the result is a bar
    chart of the values (whole numbers, as of pdgcode), see BarHistogram.

    The options can also be given in the expression, as in the histogram
    strings of mcpltool -H (see mcpltool -H help), e.g.
    "ekin/eV;logx;lethargy;bins=50;logy", which can also have two
    expressions for a 2D histogram (see histogram2d()).
    """
    given = { 'bins' : None if bins == 'auto' else bins, 'range' : range,
              'logx' : logx, 'unweighted' : unweighted, 'split' : split,
              'lethargy' : lethargy, 'groups' : None if max_curves == 8 else max_curves,
              'bar' : bar }
    o = _hist_with_args(expression,given)
    if o['print']:
        raise MCPLError('The histogram option print is only for the mcpltool'
                        ' command (use the to_text() method of the histogram'
                        ' instead)')
    return _histogram(files,o,pick = pick,_maxbins = _maxbins)

def histogram2d( files, xexpression, yexpression, pick = None, bins = 'auto',
                 xrange = None, yrange = None, unweighted = False,
                 _maxbins = None ):
    """2D histogram of the values of two expressions (see histogram()) for the
    particles in one or more files, for instance:

       h = mcpl.histogram2d( "myfile.mcpl",
                             "x/cm", "y/cm" )
       h.plot()

    The number of bins can be given for both axes, or as a tuple (nx,ny), and
    is otherwise chosen from the effective number of entries N (the fourth
    root of N per axis, between 10 and 400). The ranges of the axes can be
    given as tuples (low,high) with xrange and yrange, otherwise they cover
    all values. The histogram contains the sum of weights in each bin, or the
    number of particles if unweighted is True.
    """
    o = _hist_defaults([ xexpression, yexpression ])
    o.update( bins = None if bins == 'auto' else bins, xrange = _as_range(xrange,'xrange'),
              yrange = _as_range(yrange,'yrange'), unweighted = unweighted )
    return _histogram(files,o,pick = pick,_maxbins = _maxbins)

def _histogram( files, o, pick = None, _maxbins = None ):
    """The histogram of the particles in the files, with the options o (see
    _parse_hist)"""
    files = _as_files(files)
    filler = _filler_for(o,pick = pick,labels = [ fl for fl,_ in files ],_maxbins = _maxbins)
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
    if len(o['exprs']) == 2:
        return _Hist2DFiller(o['exprs'][0],o['exprs'][1],pick = pick,bins = bins,
                             xrange = o['xrange'],yrange = o['yrange'],
                             unweighted = o['unweighted'],_maxbins = _maxbins)
    if o['bar'] is not False:
        return _BarFiller(o['exprs'][0],pick = pick,
                          limit = 10 if o['bar'] is True else o['bar'],
                          unweighted = o['unweighted'],logy = o['logy'],labels = labels)
    return _Hist1DFiller(o['exprs'][0],pick = pick,bins = bins,range = o['range'],
                         logx = o['logx'],unweighted = o['unweighted'],split = o['split'],
                         lethargy = o['lethargy'],max_curves = o['groups'] or 8,
                         logy = o['logy'] or False,labels = labels,_maxbins = _maxbins)

class _Filler:
    """Common basis of the fillers, which make histograms from blocks of (picked)
    particles of files: if needs_range, the blocks are first given to
    add_range (to find the ranges of the values), and then, after start_fill,
    to add. The labels are those of the files, and result() is the histogram
    of the blocks given to add so far."""
    needs_range = False
    def __init__( self, expressions, pick, unweighted, labels ):
        self.pick = _as(ParticleFilter,pick)
        self._vals = [ _PlotValue(e) for e in expressions ]
        self._notes = [ _DomainNote(v) for v in self._vals ]
        self._weighted = not unweighted
        self._labels = list(labels)
        #(the ranges of the values found by add_range, in the units of MCPL):
        self._lims = [ [ np.inf, -np.inf ] for _ in expressions ]
        self._positive = [ False for _ in expressions ]

    @property
    def _title( self ):
        return f'pick: {self.pick.expression}' if self.pick is not None else None

    def _values( self, b ):
        """The values of the expressions, and the weights, of the particles of
        the block for which the expressions are defined (and the mask of those)"""
        for n in self._notes:
            n.add(b)
        vals = [ np.asarray(v(b),dtype=float) for v in self._vals ]
        w = np.broadcast_to(b.weight if self._weighted else 1.0,(len(b),))
        #(values are NaN where the expressions are not defined):
        defined = ~np.any([ np.isnan(v) for v in vals ],axis=0)
        if not defined.all():
            vals, w = [ v[defined] for v in vals ], w[defined]
        return vals, w, defined

    def add_range( self, flabel, b ):
        for lim, v, positive in zip(self._lims,self._vals,self._positive):
            x = np.asarray(v(b),dtype=float)
            x = x[np.isfinite(x)&(x>0)] if positive else x[np.isfinite(x)]
            if len(x):
                lim[0], lim[1] = min(lim[0],x.min()), max(lim[1],x.max())

    def _found_range( self, i, log = False ):
        """The range of the values of expression i found by add_range"""
        lo, hi = self._lims[i]
        if not lo <= hi:
            raise MCPLError('No values to histogram (no particles picked?)')
        if lo == hi:
            return ( lo/2, lo*2 ) if log else ( lo - 1.0, hi + 1.0 )
        return lo, hi

    def _range_of( self, rng, i, name ):
        """The given range (see _as_range) of expression i, in the units of MCPL"""
        rng = _as_range(rng,name)
        _check_range(rng,self._vals[i],name)
        return ( rng.lo, rng.hi ) if rng is not None else None

class _Hist1DFiller(_Filler):
    """Makes the histogram of histogram() (see _Filler)"""
    def __init__( self, expression, pick = None, bins = 'auto', range = None,
                  logx = False, unweighted = False, split = None,
                  lethargy = False, max_curves = 8, logy = False,
                  labels = ( None, ), _maxbins = None ):
        super().__init__([ expression ],pick,unweighted,labels)
        self._spl = _SplitValue(split) if split is not None else None
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
            self._logx = _auto_logx(*self._found_range(0))
        self._range = self._found_range(0,self._logx)
        self._setup()

    def _setup( self ):
        if self._logx == 'auto':#(with a given range)
            self._logx = _auto_logx(*self._range)
        self._auto = ( self._bins == 'auto' )
        self._nbins = _nice_nbins(self._maxbins or 1200) if self._auto else int(self._bins)
        self._edges = _make_edges(self._range,self._nbins,self._logx)
        #(the unit of the axis, for expressions with units):
        v = self._vals[0]
        self._unit = _plot_unit(v.dim,*self._range,self._logx,v.wavelength)
        self._acc = {}#(file label,split key) -> [contents,sumw2,underflow,overflow]

    def add( self, flabel, b ):
        edges, spl = self._edges, self._spl
        n = len(edges) - 1
        ( v, ), w, defined = self._values(b)
        if spl is not None:
            keys, kidx = spl.keys(np.asarray(spl(b),dtype=float)[defined])
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
        edges, nbins, spl = self._edges, self._nbins, self._spl
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
        unit, scale = self._unit or ( None, 1.0 )
        h = Histogram(self._vals[0].expression,edges/scale,self._logx,self._weighted,
                      self._lethargy,self._title,unit=unit)
        h.logy = self._logy
        h.note, h._plot_notes['x'] = ( self._notes[0].note(u) for u in ( False, True ) )
        h._display_bins = nbins if self._auto else None
        #The curves, by total weight (per file), with the smallest ones combined:
        multifile = len(self._labels) > 1
        empty = [ np.zeros(len(edges)-1), np.zeros(len(edges)-1), 0.0, 0.0 ]
        for flabel in self._labels:
            sums = { k : a[0].sum() for (fl,k), a in acc.items() if fl == flabel }
            shown, rest = _top_keys(sums or { None : 0.0 },self._max_curves)
            curves = [ ( k, acc.get((flabel,k),empty) ) for k in shown ]
            if rest:
                parts = [ acc[(flabel,r)] for r in rest ]
                curves.append( ( 'other', [ sum( p[i] for p in parts ) for i in range(4) ] ) )
            colors = _value_colors(spl.field,[ k for k,_ in curves ]) if spl and not multifile else {}
            for k, a in curves:
                lbl, plbl = ( 'other' if k == 'other' else _split_label(spl,k,u)
                              for u in ( False, True ) )
                if multifile:
                    lbl, plbl = ( flabel if x is None else f'{flabel}: {x}' for x in ( lbl, plbl ) )
                if plbl != lbl:
                    h._plot_labels[lbl] = plbl
                h.contents[lbl], h.sumw2[lbl] = a[0], a[1]
                h.underflow[lbl], h.overflow[lbl] = a[2], a[3]
                if k in colors:
                    h.colors[lbl] = colors[k]
        return h

class _BarFiller(_Filler):
    """Makes the bar charts of histogram() with bar (see _Filler; no range is
    needed)"""
    def __init__( self, expression, pick = None, limit = 10, unweighted = False,
                  logy = None, labels = ( None, ) ):
        super().__init__([ expression ],pick,unweighted,labels)
        if self._vals[0].dim is not None:
            self._not_whole()
        self._limit, self._logy = limit, logy
        self._sums = { fl : {} for fl in self._labels }

    def _not_whole( self ):
        raise MCPLError('Bar charts are of whole numbers without units, like pdgcode'
                        f' or round(x/cm), not of "{self._vals[0].expression}"')

    def add( self, flabel, b ):
        ( v, ), w, _ = self._values(b)
        if not np.all( v == np.floor(v) ):
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
        h = BarHistogram(e.expression,self._weighted,self._title)
        if self._logy is not None:
            h.logy = self._logy
        h.note, h._plot_notes['x'] = ( self._notes[0].note(u) for u in ( False, True ) )
        multifile = len(self._labels) > 1
        for flabel, sums in self._sums.items():
            shown, rest = _top_keys(sums,self._limit)
            bars = [ ( k, sums[k] ) for k in shown ]
            bars += [ ( 'other', sum( sums[k] for k in rest ) ) ] if rest else []
            colors = {} if multifile else _value_colors(e._e.field,[ k for k,_ in bars ])
            for k, v in bars:
                lbl, plbl = ( 'other' if k == 'other' else ( e._e.value_label(k,u) or str(k) )
                              for u in ( False, True ) )
                if multifile:
                    lbl, plbl = f'{flabel}: {lbl}', f'{flabel}: {plbl}'
                if plbl != lbl:
                    h._plot_labels[lbl] = plbl
                h.contents[lbl] = v
                if k in colors:
                    h.colors[lbl] = colors[k]
        return h

class _Hist2DFiller(_Filler):
    """Makes the histogram of histogram2d() (see _Filler; the files are
    combined)"""
    def __init__( self, xexpression, yexpression, pick = None, bins = 'auto',
                  xrange = None, yrange = None, unweighted = False,
                  _maxbins = None ):
        super().__init__([ xexpression, yexpression ],pick,unweighted,( None, ))
        self._bins, self._maxbins = bins, _maxbins
        self._ranges = [ self._range_of(xrange,0,'xrange'), self._range_of(yrange,1,'yrange') ]
        self.needs_range = None in self._ranges
        if not self.needs_range:
            self._setup()

    def start_fill( self ):
        self._ranges = [ r or self._found_range(i) for i, r in enumerate(self._ranges) ]
        self._setup()

    def _setup( self ):
        bins = self._bins
        self._auto = ( isinstance(bins,str) and bins == 'auto' )
        if self._auto:
            mx, my = self._maxbins if self._maxbins else ( 400, 400 )
            bx, by = _nice_nbins(mx), _nice_nbins(my)
        else:
            bx, by = bins if isinstance(bins,(tuple,list)) else ( bins, bins )
            bx, by = int(bx), int(by)
        self._bx, self._by = bx, by
        self._xe, self._ye = ( _make_edges(r,n,False) for r, n in zip(self._ranges,(bx,by)) )
        #(the units of the axes, for expressions with units):
        self._units = [ _plot_unit(v.dim,*r,False,v.wavelength) or ( None, 1.0 )
                        for v, r in zip(self._vals,self._ranges) ]
        self._contents = np.zeros((bx,by))
        self._sumw, self._sumw2 = 0.0, 0.0

    def add( self, flabel, b ):
        xe, ye = self._xe, self._ye
        ( x, y ), w, _ = self._values(b)
        self._contents += np.histogram2d(x,y,bins=(xe,ye),weights=w)[0]
        wi = w[ ( x >= xe[0] ) & ( x <= xe[-1] ) & ( y >= ye[0] ) & ( y <= ye[-1] ) ]
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
        ( xunit, xscale ), ( yunit, yscale ) = self._units
        h = Histogram2D(self._vals[0].expression,self._vals[1].expression,xe/xscale,
                        ye/yscale,self._weighted,self._title,xunit=xunit,yunit=yunit)
        h.xnote, h.ynote = ( n.note() for n in self._notes )
        h._plot_notes['x'], h._plot_notes['y'] = ( n.note(True) for n in self._notes )
        h.contents += contents
        h._display_bins = ( bx, by ) if self._auto else None
        return h

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
    exprs = sorted({ h.expression for h in histograms })
    logy = first.logy if logy is None else logy
    if logy == 'auto':
        logy = _auto_log([ h.values(c) for h in histograms for c in h.contents ])
    p = Panel( xlabel = ', '.join(exprs), ylabel = first.ylabel,
               logx = first.logx, logy = bool(logy),
               xlim = ( min( h.edges[0] for h in histograms ),
                        max( h.edges[-1] for h in histograms ) ) )
    color = 0
    for i,h in enumerate(histograms):
        name = labels[i] if labels is not None else ( h.title or h.expression )
        for curve in h.contents:
            label = name if curve is None else f'{name}: {curve}'
            p.add(StepHist(h.edges,h.values(curve),label = label,color = color))
            color += 1
    return _show_or_save([Figure(panels = [p])],filename,backend,options)
