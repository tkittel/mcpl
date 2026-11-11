
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

"""The histograms of values calculated with expressions from the particles in
MCPL files, as plain data: the fillers, which make them from blocks of
particles, and the classes of their results. Plots of them are made by
_histfigures, and the public API (mcpl.histogram) wraps the results, see
_histogram. This module does not use the plotting module (so it can be used
where plots are never shown, like in background threads)."""

__all__ = []

import math
import os

from ._common import MCPLError
from ._expr_eval import _dimstr
from ._expressions import ParticleValue, _as_edit, _as_expression, _expr_of
from ._exprplot import _plot_unit, _PlotValue
from ._exprunits import _dim_unknown
from ._histstring import (
    _as_range,
    _auto_logx,
    _check_range,
    _default_maxpoints,
    _display_by,
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

def _blocks( source ):
    """Iterate over the particle blocks of a file (an MCPLFile, or the name of
    a file, which is then closed when done)"""
    if not _is_file(source):
        with MCPLFile(source) as f:
            yield from f.particle_blocks
        return
    yield from source.particle_blocks

class _DisplayByValue:
    """Values of the expression of display_by, which give the curves of the
    particles"""
    def __init__( self, expr ):
        self._v = _as_expression(ParticleValue,expr)
        self.expr = _expr_of(self._v)
        self.expression = self._v.expression
        self.field = self.expr.field
        self._is_bool = None
    def __call__( self, block ):
        return self._v(block)
    def keys( self, values ):
        """The distinct values (at most 1000), and the index of each value in
        them"""
        keys, index = _distinct(values)
        return self._checked(keys), index
    def block_keys( self, b, defined, shared = None ):
        """keys() of the values of the particles of the block b with the mask
        defined, with the distinct values of all particles of the block found
        only once for all fillers given the same shared (see _SharedKeys)"""
        if shared is None:
            return self.keys(np.asarray(self(b),dtype=float)[defined])
        keys, index = shared.distinct(self,b)
        index = index[defined]
        present = np.bincount(index,minlength=len(keys)) > 0
        if not present.all():
            keys, index = keys[present], ( np.cumsum(present) - 1 )[index]
        return self._checked(keys), index
    def _checked( self, keys ):
        """The distinct values keys, after checking that there are at most
        1000, and noting whether they are all 0 or 1"""
        if len(keys):
            #(labels as a condition only if all values, in all blocks, are 0 or 1):
            b01 = bool(np.all((keys==0)|(keys==1)))
            self._is_bool = b01 if self._is_bool is None else self._is_bool and b01
        if len(keys) > 1000:
            raise MCPLError(f'The expression "{self._v.expression_original}" of display_by has too many'
                            ' different values (more than 1000)')
        return keys

def _distinct( values ):
    """The distinct values of the array (sorted), and the index of each value
    in them (as np.unique(values,return_inverse=True), but faster)"""
    keys = np.unique(values)
    return keys, np.searchsorted(keys,values).ravel()

class _SharedKeys:
    """The distinct values of the display_by expressions of the particles of
    one block, found once for all fillers filling from it (see
    _DisplayByValue.block_keys): a new one is given with each block to the
    add methods of the fillers"""
    def __init__( self ):
        self._found = {}#(block, expression) -> (keys, index)
    def distinct( self, dby, b ):
        """The distinct values of the display_by expression dby (a
        _DisplayByValue) of the particles of the block b, and the index of the
        value of each particle in them"""
        key = ( id(b), dby.expression )
        if key not in self._found:
            self._found[key] = _distinct(np.asarray(dby(b),dtype=float))
        return self._found[key]

def _display_by_label( display_by, key, unicode = False ):
    """Label of the curve of a value of the expression of display_by (with
    symbols for plots if unicode is set, see _pdg_symbols)"""
    if display_by is None or key is None:
        #No display_by, or no particles (so no values of its expression):
        return None
    name = display_by.expr.value_label(key,unicode)
    if name is not None:
        return name
    if key in (0.0,1.0) and display_by._is_bool:
        return display_by.expression if key else f'not ({display_by.expression})'
    return f'{display_by.expression} = {key:g}'

class _HistData:
    """Common basis of the results of the fillers (_Hist1DData, _HistDiscreteData,
    _Hist2DData, and _PointSet3DData): the title (the edit, for instance),
    whether the values are sums of weights, what their plots show (see
    _histfigures), and the text tables"""
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

    def _text_header( self, what, values, columns ):
        lines = [ f'# {what}' ] + [ f'# {t}' for t in ( self.title or '' ).splitlines() ]
        return lines + [ f'# values: {values}', '# ' + ' | '.join(columns) ]

class _Hist1DData(_HistData):
    """1D histogram of the values of an expression (the result of
    _Hist1DFiller). The bin edges are in edges (in the unit, a text like "cm",
    for expressions with units), and the contents (sums of weights, or numbers
    of particles if unweighted) in the dictionary contents, with one entry per
    curve (keyed by label, None for a single curve, see display_by). The sums
    of squared weights are in sumw2, and the sums of weights below and above
    the edges are in underflow and overflow (with the same keys)."""
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

class _HistDiscreteData(_HistData):
    """Histogram of the values of an expression with whole numbers (the result
    of _HistDiscreteFiller), plotted as bars. The contents are the sums of weights
    (or numbers of particles if unweighted) of the bars, by their labels (the
    values, or names like "n (2112)" for pdgcode values), and _value_sums
    those of all values."""
    def __init__( self, expression, *, weighted, title ):
        super().__init__(weighted,title)
        self.expression = expression
        self.logy = False
        self.note = None
        self.colors = {}
        self.contents = {}

    @property
    def label( self ):
        """The expression, with its note (see _Hist1DData.label)"""
        return _with_unit(self.expression,None,self.note)

    def to_text( self ):
        """Text table with the contents."""
        lines = self._text_header(f'bars of: {self.label}',self._what,[ 'bar', 'value' ])
        return '\n'.join( lines + [ f'{lbl} | {v:.8g}' for lbl, v in self.contents.items() ] )

class _Hist2DData(_HistData):
    """2D histogram of the values of two expressions (the result of
    _Hist2DFiller). The contents (with shape (len(xedges)-1, len(yedges)-1))
    are sums of weights, or numbers of particles if unweighted. For
    expressions with units, the edges are in the units xunit and yunit (texts
    like "cm", else None)."""
    def __init__( self, xexpression, yexpression, xedges, yedges, *, weighted, title,
                  xunit = None, yunit = None, logx = False, logy = False ):
        super().__init__(weighted,title)
        self.logx, self.logy = logx, logy#(logarithmic bins and axes)
        self.xexpression, self.yexpression = xexpression, yexpression
        self.xunit, self.yunit = xunit, yunit
        self.xnote, self.ynote = None, None
        self.xedges, self.yedges = xedges, yedges
        self.contents = np.zeros((len(xedges)-1,len(yedges)-1))
        self.logz = True#(the colour scale of the plot)
        #(the length per unit of the y axis relative to the x axis of the
        #plot, for equal scales of axes with the same units, or None):
        self.aspect = None

    @property
    def xlabel( self ):
        """The x expression, with its unit and note (see _Hist1DData.label)"""
        return _with_unit(self.xexpression,self.xunit,self.xnote)

    @property
    def ylabel( self ):
        """The y expression, with its unit and note (see _Hist1DData.label)"""
        return _with_unit(self.yexpression,self.yunit,self.ynote)

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

class _PointSet3DData(_HistData):
    """The values of three expressions for randomly sampled particles (the
    result of _PointSet3DFiller: at most maxpoints, sampled according to weights,
    unless unweighted, so they are distributed as the particles), in
    groups (label -> array of shape (n,3), with the label None for one group,
    see display_by). For expressions with units, the values are in the units
    (texts like "cm", else None). The same particles are always chosen for the
    same particles of a file (see _index_random)."""
    def __init__( self, expressions, *, weighted, title, units, nparticles ):
        super().__init__(weighted,title)
        self.expressions, self.units = list(expressions), list(units)
        self.notes = [ None ] * 3
        self.nparticles = nparticles#(of which the points were chosen)
        self.equal = False#(the same scale on all axes)
        self.groups = {}
        self.colors = {}#(label -> colour index, see _figures.StepHist)

    @property
    def labels( self ):
        """The labels of the axes, with their units and notes (see
        _Hist1DData.label)"""
        return [ _with_unit(e,u,n) for e, u, n in zip(self.expressions,self.units,self.notes) ]

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

def _with_unit( expression, unit, note = None ):
    """Axis label of an expression, with its unit and note (see _DomainNote)"""
    label = f'{expression} [{unit}]' if unit else expression
    return f'{label} {note}' if note else label

#Fixed colours of the values of some fields, so particle types have the same
#colours in all plots (see _particles), and those of them which other values
#never get with solid lines, so these are never confused (n, gamma, e-, and p):
_fixed_colors = { 'pdgcode' : _pdg_colors }
_reserved_colors = { 'pdgcode' : { _pdg_colors[c] for c in ( 2112, 22, 11, 2212 ) } }

def _value_colors( field, keys ):
    """Colours of the values (keys) of the field, if it has fixed colours (as
    {key : colour index}, see _figures.StepHist): the other values get the
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

class _DomainNote:
    """Collects for which particles the values of a _PlotValue were defined
    (for expressions defined only for some, like wavelengths), for the note in
    the axis label, like "(neutrons and gammas only)", if any particles were
    left out"""
    def __init__( self, value ):
        self._v, self._seen, self._left_out = value, {}, False
    def add( self, b ):
        seen, all_defined = self._v.domain_values(b)
        for field, vals in seen.items():
            self._seen.setdefault(field,set()).update(vals)
        self._left_out = self._left_out or not all_defined
    def note( self, unicode = False ):
        return self._v.domain_note(self._seen,unicode) if self._left_out else None

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

def _auto_nbins( nentries, nbins, ndim = 1 ):
    """Number of bins (per axis) for showing a histogram made with nbins bins
    of nentries particles (with non-zero weights, as the bins show where the
    particles are, also when a few of them have most of the weight):
    nentries^(1/(ndim+1)), which is the square-root rule for ndim=1, and for
    ndim=2 gives bins with as many entries on average as there are bins per
    axis (as for the square-root rule), clamped to [10,400], and then the
    closest divisor of nbins (in log distance, so the bins can be merged
    exactly)."""
    target = max( 1.0, nentries ) ** ( 1.0 / ( ndim + 1 ) )
    target = max( 10, min( 400, round(target) ) )
    divs = [ d for d in _range(1,nbins+1) if nbins % d == 0 ]
    return min( divs, key = lambda d : abs(math.log(d/target)) )

_range = range#(the name range is shadowed by arguments below)

def _selection_title( edit = None, display_edit = None ):
    """The title of a plot of the particles of an edit and a display_edit
    (as texts, or None): one line each, or None"""
    return '\n'.join( f'{what}: {e}' for what, e in ( ('edit',edit),
                                                      ('display_edit',display_edit) )
                      if e is not None ) or None

def _fill( files, o, _maxbins = None ):
    """The histogram of the particles in the files (names, or MCPLFiles, whose
    skip, limit, and edit apply), with the options o (see _parse_hist). The
    title has the edit of the files, if they all have the same."""
    files = _as_files(files)
    filler = _filler_for(o,labels = [ fl for fl,_ in files ],_maxbins = _maxbins)
    edits = { src.edit.expression if isinstance(src,MCPLFile) and src.edit is not None else None
              for _,src in files }
    filler._selection = edits.pop() if len(edits) == 1 else None
    if filler.needs_range:
        for flabel,src in files:
            for b in _blocks(src):
                filler.add_range(flabel,b)
        filler.start_fill()
    for flabel,src in files:
        for b in _blocks(src):
            filler.add(flabel,b)
    return filler.result()

def _filler_for( o, labels = ( None, ), _maxbins = None ):
    """The filler of a histogram with the options o (see _parse_hist): blocks of
    particles of the files with the labels are given to it as in _fill, and
    its result() is the histogram of the blocks so far."""
    bins = o['bins'] or 'auto'
    #(with several files, 1D histograms have a curve for each file, unless
    #display_by is given, instead of one for each particle type in each file,
    #while 2D histograms and 3D plots combine the files):
    by_file = len(labels) > 1 and o['display_by'] is None and len(o['exprs']) == 1
    display_by = None if by_file else _display_by(o)
    if len(o['exprs']) == 3:
        return _PointSet3DFiller(o['exprs'],maxpoints = o['maxpoints'],
                                 unweighted = o['unweighted'],display_by = display_by,
                                 equal = o['equal'],display_edit = o['display_edit'])
    if len(o['exprs']) == 2:
        return _Hist2DFiller(o['exprs'][0],o['exprs'][1],bins = bins,
                             xrange = o['xrange'],yrange = o['yrange'],
                             unweighted = o['unweighted'],_maxbins = _maxbins,
                             logz = o['logz'] is not False,equal = o['equal'],
                             display_edit = o['display_edit'],logx = o['logx'],
                             logy = o['logy'] or False)
    if o['bar'] is not False:
        return _HistDiscreteFiller(o['exprs'][0],
                                   limit = 10 if o['bar'] is True else o['bar'],
                                   unweighted = o['unweighted'],logy = o['logy'],
                                   labels = labels,display_edit = o['display_edit'])
    return _Hist1DFiller(o['exprs'][0],bins = bins,range = o['range'],
                         logx = o['logx'],unweighted = o['unweighted'],display_by = display_by,
                         lethargy = o['lethargy'],
                         logy = o['logy'] or False,labels = labels,_maxbins = _maxbins,
                         display_edit = o['display_edit'])

class _Filler:
    """Common basis of the fillers, which make histograms from blocks of
    particles of files: if needs_range, the blocks are first given to
    add_range (to find the ranges of the values), and then, after start_fill,
    to add (which subclasses implement as _add). The labels are those of the
    files, and result() is the histogram of the blocks given to add so far.
    With display_edit (the option of histogram strings), the blocks are
    edited with it first."""
    needs_range = False
    def __init__( self, expressions, unweighted, labels, display_edit = None ):
        self._display = _as_edit(display_edit)
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

    #(the expression of the edit applied to the particles before they are
    #given to the filler, for the title, see _selection_title):
    _selection = None

    def _need_equal( self ):
        """Check that the values have the same units, for equal scales of the
        axes (when the units are known, e.g. of userdata, see _values)"""
        if _dim_unknown in ( v.dim for v in self._vals ):
            self._unchecked.append(self._check_equal)
        else:
            self._check_equal()
    def _check_equal( self ):
        dims = [ v.dim for v in self._vals ]
        if any( d != dims[0] for d in dims ):
            raise MCPLError('Equal scales of the axes (the histogram option "equal")'
                            ' need expressions with the same units, not'
                            f' {_listed(_dimstr(d) for d in dims)} (of'
                            f' {_listed(v.expression_original for v in self._vals)})')

    @property
    def _title( self ):
        return _selection_title(self._selection,self._display and self._display.expression)

    def add( self, flabel, b, shared = None ):
        """Add the particles of the block b, of the file with the label
        flabel. Fillers given the same block together can share the values
        found from it (shared, see _SharedKeys)."""
        #(an edited block is not the one the values were shared for):
        self._add(flabel,self._shown(b),shared if self._display is None else None)

    def _shown( self, b ):
        """The particles of the block which are shown (see display_edit)"""
        return b if self._display is None else self._display(b)

    def _curves( self, sums, limit, field, name, flabel = None ):
        """The curves (or bars) of the values with the sums (a dict by key):
        those of the limit largest sums, and one of the others (if any), as
        (keys, label, plot label, colour index or None), with labels from
        name(key, unicode) (see _HistData._plot_labels), or 'other', and the
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

    def _values( self, b ):
        """The values of the expressions, and the weights, of the particles of
        the block for which the expressions are defined (and the mask of
        those)"""
        for n in self._notes:
            n.add(b)
        vals = [ np.asarray(v(b),dtype=float) for v in self._vals ]
        for check in self._unchecked:#(now that the units are known)
            check()
        self._unchecked = []
        w = np.broadcast_to(b.weight if self._weighted else 1.0,(len(b),))
        #(values are NaN where the expressions are not defined):
        defined = ~np.any([ np.isnan(v) for v in vals ],axis=0)
        if not defined.all():
            vals, w = [ v[defined] for v in vals ], w[defined]
        return vals, w, defined

    def add_range( self, flabel, b ):
        b = self._shown(b)
        for lim, v, positive in zip(self._lims,self._vals,self._positive):
            x = np.asarray(v(b),dtype=float)
            x = x[np.isfinite(x)&(x>0)] if positive else x[np.isfinite(x)]
            if len(x):
                lim[0], lim[1] = min(lim[0],x.min()), max(lim[1],x.max())

    def _found_range( self, i, log = False, nice = True ):
        """The range of the values of expression i found by add_range (for
        linear axes extended to round values, unless nice is False, see
        _nice_range)"""
        lo, hi = self._lims[i]
        if not lo <= hi:
            raise MCPLError('No values to histogram (no particles kept?)')
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
    def __init__( self, expression, bins = 'auto', range = None,
                  logx = False, unweighted = False, display_by = None,
                  lethargy = False, max_curves = 8, logy = False,
                  labels = ( None, ), _maxbins = None, display_edit = None ):
        super().__init__([ expression ],unweighted,labels,display_edit)
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
        self._nentries = 0#(in the range, with non-zero weights, see _auto_nbins)

    def _add( self, flabel, b, shared ):
        edges, dby = self._edges, self._dby
        n = len(edges) - 1
        ( v, ), w, defined = self._values(b)
        if dby is not None:
            keys, kidx = dby.block_keys(b,defined,shared)
        else:
            keys, kidx = [ None ], np.zeros(len(v),dtype=np.intp)
        #(all curves at once: the sums by curve and bin, below and above):
        nk = len(keys)
        inside = ( v >= edges[0] ) & ( v <= edges[-1] )
        flat = kidx[inside] * n + _bin_index(v[inside],edges,self._logx)
        wi = w[inside]
        self._nentries += int(np.count_nonzero(wi))
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
        #With automatic binning, merge the bins according to the number of
        #entries:
        if self._auto:
            k = nbins // _auto_nbins(self._nentries,nbins)
            if k > 1:
                edges = edges[::k]
                for a in acc.values():
                    a[0] = a[0].reshape(-1,k).sum(axis=1)
                    a[1] = a[1].reshape(-1,k).sum(axis=1)
        #(the unit of the axis, for expressions with units, which for userdata
        #are known when particles were read):
        v = self._vals[0]
        unit, scale = _plot_unit(v.dim,*self._range,self._logx,v.wavelength)
        h = _Hist1DData(self._vals[0].expression,edges/scale,logx=self._logx,
                      weighted=self._weighted,lethargy=self._lethargy,title=self._title,
                      unit=unit)
        h.logy = self._logy
        h.note, h._plot_notes['x'] = ( self._notes[0].note(u) for u in ( False, True ) )
        h._display_bins = nbins if self._auto else None
        h._scale = scale#(the edges are in units of the scale, see _plot_unit)
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

class _HistDiscreteFiller(_Filler):
    """Makes the histograms of whole numbers of the histogram strings with the
    option bar (see _Filler; no range is needed)"""
    def __init__( self, expression, limit = 10, unweighted = False,
                  logy = 'auto', labels = ( None, ), display_edit = None ):
        super().__init__([ expression ],unweighted,labels,display_edit)
        #(the units of fields of the userdata are checked with the values):
        if self._vals[0].dim not in ( None, _dim_unknown ):
            self._not_whole()
        self._limit, self._logy = limit, logy
        self._sums = { fl : {} for fl in self._labels }

    def _not_whole( self ):
        raise MCPLError('Bar charts are of whole numbers without units, like pdgcode'
                        f' or round(x/cm), not of "{self._vals[0].expression_original}"')

    def _add( self, flabel, b, shared ):
        ( v, ), w, _ = self._values(b)
        if self._vals[0].dim is not None or not np.all( v == np.floor(v) ):
            self._not_whole()
        keys, idx = np.unique(v,return_inverse=True)
        sums = self._sums[flabel]
        for k, s in zip(keys.tolist(),np.bincount(idx,weights=w,minlength=len(keys))):
            sums[int(k)] = sums.get(int(k),0.0) + float(s)
        if len(sums) > 1000:
            raise MCPLError(f'Bar chart of "{self._vals[0].expression_original}" has too many'
                            ' different values (more than 1000)')

    def result( self ):
        e = self._vals[0]
        h = _HistDiscreteData(e.expression,weighted=self._weighted,title=self._title)
        if self._logy is not None:
            h.logy = self._logy
        h.note, h._plot_notes['x'] = ( self._notes[0].note(u) for u in ( False, True ) )
        #(the sums of all values, of all files):
        h._value_sums = {}
        for sums in self._sums.values():
            for k, v in sums.items():
                h._value_sums[k] = h._value_sums.get(k,0.0) + v
        multifile = len(self._labels) > 1
        for flabel, sums in self._sums.items():
            for keys, lbl, plbl, color in self._curves(sums,self._limit,e.expr.field,
                                                       lambda k, u : e.expr.value_label(k,u) or str(k),
                                                       flabel if multifile else None):
                h.contents[lbl] = sum( sums[k] for k in keys )
                h._add_label(lbl,plbl,color)
        return h

class _Hist2DFiller(_Filler):
    """Makes 2D histograms (see _Filler; the files are combined)"""
    def __init__( self, xexpression, yexpression, bins = 'auto',
                  xrange = None, yrange = None, unweighted = False,
                  _maxbins = None, logz = 'auto', equal = False, display_edit = None,
                  logx = 'auto', logy = 'auto' ):
        super().__init__([ xexpression, yexpression ],unweighted,( None, ),display_edit)
        self._bins, self._maxbins, self._logz, self._equal = bins, _maxbins, logz, equal
        #(logarithmic axes, or 'auto' to decide from the ranges, see _auto_logx):
        self._log = [ logx, logy ]
        self._positive = [ lg is True for lg in self._log ]
        if equal:
            self._need_equal()
        self._ranges = [ self._range_of(xrange,0,'xrange'), self._range_of(yrange,1,'yrange') ]
        self.needs_range = None in self._ranges
        if not self.needs_range:
            self._setup()

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
        self._nentries = 0#(see _auto_nbins)

    def _add( self, flabel, b, shared ):
        xe, ye = self._xe, self._ye
        ( x, y ), w, _ = self._values(b)
        inside = ( x >= xe[0] ) & ( x <= xe[-1] ) & ( y >= ye[0] ) & ( y <= ye[-1] )
        #(as np.histogram2d, but much faster, see _bin_index):
        flat = ( _bin_index(x[inside],xe,self._log[0]) * self._by
                 + _bin_index(y[inside],ye,self._log[1]) )
        wi = w[inside]
        self._contents += np.bincount(flat,weights=wi,
                                      minlength=self._bx*self._by).reshape(self._bx,self._by)
        self._nentries += int(np.count_nonzero(wi))

    def result( self ):
        xe, ye, contents, bx, by = self._xe, self._ye, self._contents, self._bx, self._by
        if self._auto:
            n = self._nentries
            kx, ky = bx // _auto_nbins(n,bx,2), by // _auto_nbins(n,by,2)
            if kx > 1 or ky > 1:
                xe, ye = xe[::kx], ye[::ky]
                contents = contents.reshape(bx//kx,kx,by//ky,ky).sum(axis=(1,3))
        #(the units of the axes, for expressions with units, see
        #_Hist1DFiller.result):
        ( xunit, xscale ), ( yunit, yscale ) = ( _plot_unit(v.dim,*r,lg,v.wavelength) for v, r, lg
                                                 in zip(self._vals,self._ranges,self._log) )
        h = _Hist2DData(self._vals[0].expression,self._vals[1].expression,xe/xscale,
                        ye/yscale,weighted=self._weighted,title=self._title,xunit=xunit,
                        yunit=yunit,logx=self._log[0],logy=self._log[1])
        h.xnote, h.ynote = ( n.note() for n in self._notes )
        h._plot_notes['x'], h._plot_notes['y'] = ( n.note(True) for n in self._notes )
        h.contents += contents
        h._display_bins = ( bx, by ) if self._auto else None
        h._scales = ( xscale, yscale )#(see _Hist1DFiller.result)
        h.logz = self._logz
        if self._equal:
            #(the axes are in the units of the scales xscale and yscale):
            h.aspect = yscale / xscale
        return h

def _index_random( fileidx ):
    """Random numbers in (0,1) for the particles at these positions in the file
    (a fixed hash of the positions, splitmix64), so a particle always gets the
    same number, whatever else is read or kept"""
    with np.errstate(over='ignore'):
        x = np.asarray(fileidx,dtype=np.uint64) + np.uint64(0x9E3779B97F4A7C15)
        x = ( x ^ ( x >> np.uint64(30) ) ) * np.uint64(0xBF58476D1CE4E5B9)
        x = ( x ^ ( x >> np.uint64(27) ) ) * np.uint64(0x94D049BB133111EB)
        x = x ^ ( x >> np.uint64(31) )
    return ( ( x >> np.uint64(11) ).astype(np.float64) + 0.5 ) / 9007199254740992.0

class _PointSet3DFiller(_Filler):
    """The filler of 3D plots (see _PointSet3DData): particles randomly sampled
    according to weights (the method of Efraimidis and Spirakis: those with the
    largest u^(1/w), with u from the positions of the particles in the file, see
    _index_random), which needs no ranges"""
    def __init__( self, expressions, maxpoints = None, unweighted = False,
                  display_by = None, max_curves = 8, equal = False, display_edit = None ):
        super().__init__(list(expressions),unweighted,( None, ),display_edit)
        self._npoints = maxpoints or _default_maxpoints
        self._equal = equal
        if equal:
            self._need_equal()
        self._dby = _DisplayByValue(display_by) if display_by is not None else None
        self._max_curves = max_curves
        self._keys, self._pts, self._sv = np.zeros(0), np.zeros((0,3)), np.zeros(0)
        self._n = 0

    def _add( self, flabel, b, shared ):
        vals, w, defined = self._values(b)
        pts = np.column_stack(vals)
        sv = ( self._display_by_values(self._dby,b,defined) if self._dby is not None
               else np.zeros(len(pts)) )
        ok = np.isfinite(pts).all(axis=1) & ( w > 0 )
        pts, w, sv = pts[ok], w[ok], sv[ok]
        self._n += len(pts)
        keys = _index_random(b.fileidx[defined][ok]) ** ( 1.0 / w )
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
            #(with equal scales, the same unit for all axes, from all values):
            col = pts if self._equal else pts[:,i]
            lo, hi = ( col.min(), col.max() ) if len(pts) else ( 0.0, 1.0 )
            units.append(_plot_unit(v.dim,lo,hi,False,v.wavelength))
        res = _PointSet3DData([ v.expression for v in self._vals ],weighted = self._weighted,
                       title = self._title,units = [ u for u, _ in units ],
                       nparticles = self._n)
        res.notes = [ n.note() for n in self._notes ]
        res.equal = self._equal
        res._points = pts#(all points, in the units of the values, see _histogram)
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
