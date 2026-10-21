
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

"""Plotting backends drawing figures as text, with ASCII characters or with
Unicode characters (block elements and box drawing, which give smoother
plots), for showing plots in a terminal (in colour, if the terminal supports
it) or saving them in text files."""

__all__ = []

import math
import pathlib
import re
import shutil
import sys
import unicodedata
from typing import ClassVar

from ._numpy import np
from ._particles import _pdg_symbols
from ._physics import _ascii_symbols
from ._plotbackend import PlotBackend
from ._termcolor import _check_setting, _curve_rgb, _map_rgb, _ncolors, _paint
from .plotting import Bars, Hist2D, Scatter3D, StepHist, Text, _line_style, _map_texts


class _Chars:
    """Characters used for drawing"""
    def __init__( self, fill, hfill, shades, markers, vline, hline, corner,
                  ytick, xtick ):
        self.fill = fill#vertical fill: "" (empty), partial levels..., full
        self.hfill = hfill#horizontal fill (for bars): "", partial..., full
        self.shades = shades#for 2D maps, from empty to full
        self.markers = markers#for curves of 1D histograms with several curves
        self.vline, self.hline, self.corner = vline, hline, corner
        self.ytick, self.xtick = ytick, xtick

_ascii = _Chars( fill = ' #', hfill = ' #', shades = ' .:-=+*#%@',
                 markers = '*o+x@%&=', vline = '|', hline = '-', corner = '+',
                 ytick = '+', xtick = '+' )
#Unicode characters (written as escape sequences, to keep the code ASCII):
_unicode = _Chars(
    #lower one eighth block ... full block:
    fill = ' \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588',
    #left one eighth block ... full block:
    hfill = ' \u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588',
    #middle dot, light, medium and dark shade, full block:
    shades = ' \u00b7\u2591\u2592\u2593\u2588',
    #black and white circles, diamonds, squares and triangles:
    markers = '\u25cf\u25cb\u25c6\u25c7\u25a0\u25a1\u25b2\u25b3',
    #box drawing: light vertical, horizontal, up and right, vertical and
    #left, down and horizontal:
    vline = '\u2502', hline = '\u2500', corner = '\u2514', ytick = '\u2524',
    xtick = '\u252c' )

#Bits of the dots of braille characters (U+2800 + bits), for the left and
#right columns of dots, from the top:
_braille_bits = ( ( 0x01, 0x02, 0x04, 0x40 ), ( 0x08, 0x10, 0x20, 0x80 ) )
#Characters between the markers along curves of braille dots without colour:
_marker_step = 8

_ansi_re = re.compile('\x1b\\[[0-9;]*m')

def _significant( v ):
    """Mask of the positive values of the array, ignoring the tiny ones left by
    rounding errors when bins are resampled to the characters"""
    v = np.asarray(v,dtype=float)
    vmax = v.max() if v.size else 0.0
    return v > ( 1e-10 * vmax if vmax > 0 else 0.0 )

def _legend_columns( entries, width ):
    """Lines of the legend entries ((text, visible width) pairs), in as many
    aligned columns as fit in the width"""
    colw = max( w for _, w in entries ) + 3
    ncol = max( 1, min( len(entries), ( width + 3 ) // colw ) )
    lines = []
    for i in range(0,len(entries),ncol):
        row = entries[i:i+ncol]
        lines.append( ''.join( t + ' ' * ( colw - w ) for t, w in row[:-1] )
                      + row[-1][0] )
    return lines

def _fmt( v ):
    return f'{v:.4g}'

#Width of the labels of the y axis (fixed, so the width of the plot area is
#known before the data, see resolution()):
_ylw = 8

def _fmt_y( v ):
    s = _fmt(v)
    return s if len(s) <= _ylw else f'{v:.2g}'

def _width( text ):
    """Width of the text in the terminal (the bars of antiparticle symbols, like
    those of _particles, are combining characters, which take no space)"""
    return sum( 1 for ch in _ansi_re.sub('',text) if not unicodedata.combining(ch) )

def _center( text, width ):
    #(as str.center, with the width in the terminal):
    pad = max( 0, width - _width(text) )
    return ( ' ' * ( pad // 2 + ( pad & width & 1 ) ) + text ).rstrip()

def _stdout_encoding():
    return getattr(sys.stdout,'encoding',None) or 'ascii'

def _can_encode( c ):
    """Whether all the characters can be written to standard output"""
    enc = _stdout_encoding()
    try:
        ( c.fill + c.hfill + c.shades + c.markers + c.vline + c.hline
          + c.corner + c.ytick + c.xtick ).encode(enc)
    except (UnicodeEncodeError,LookupError):
        return False
    return True

class _TextBackend(PlotBackend):
    """Draws figures as text (with the characters in self._chars)"""
    kind = 'terminal'
    _chars = None
    encoding = 'utf-8'
    #Whether several curves in colour are drawn as lines of braille dots:
    _braille = False
    #Whether 2D maps in colour are drawn with half blocks (two cells per
    #character, with foreground and background colours):
    _halfblocks = False

    def __init__( self, width = None, height = None, color = 'auto' ):
        if width is None:
            width = min( 250, shutil.get_terminal_size((80,24)).columns )
        self._width = max( 40, int(width) )
        self._height = max( 5, int(height or 15) )
        self._when = _check_setting(color)
        self._nc = 0#number of colours while drawing (0: no colours)

    def _p( self, text, fg = None, bg = None ):
        return _paint(text,self._nc,fg,bg)

    def _curve_color( self, item, k ):
        return _curve_rgb( item.color if item.color is not None else k )

    @staticmethod
    def _curve_style( item, k ):
        """Line style of a curve (see _line_style)"""
        return _line_style( item.color if item.color is not None else k )[1]

    def resolution( self ):
        return ( self._width - _ylw - 3, self._height )

    def _fit_resolution( self, bins ):
        """Reduce the size of the plots so histograms with the given number of
        bins (or (nx,ny) for 2D histograms) are drawn with a whole number of
        columns (and rows) per bin."""
        ncols, nrows = self.resolution()
        nx, ny = bins if isinstance(bins,(tuple,list)) else ( bins, None )
        if nx and nx <= ncols:
            self._width = ( ncols - ncols % nx ) + _ylw + 3
        if ny and ny <= nrows:
            self._height = nrows - nrows % ny

    def show( self, figures ):
        #(in colour, depending on the colour setting and the terminal):
        self._nc = _ncolors(self._when)
        try:
            print('\n\n'.join( self.draw(f) for f in figures ))
        finally:
            self._nc = 0

    def save( self, figures, filename ):
        self.check_format(filename)
        pathlib.Path(filename).write_text( '\n\n'.join( self.draw(f,self.encoding) for f in figures )
                                           + '\n', encoding = self.encoding )
        return [ filename ]

    def draw( self, figure, encoding = None ):
        """Text representation of the figure, for the encoding (default: that of
        standard output). The symbols of particles in labels (see _pdg_symbols)
        are replaced by their names if they can not be written."""
        enc = 'ascii' if self.encoding == 'ascii' else ( encoding or _stdout_encoding() )
        try:
            ''.join(_pdg_symbols.values()).encode(enc)
        except (UnicodeEncodeError,LookupError):
            figure = _map_texts(figure,_ascii_symbols)
        out = []
        if figure.title:
            out += [ _center(line,self._width) for line in figure.title.split('\n') ]
            out.append('')
        for panel in figure.panels:
            if panel is not None:#(not the empty cells of grids)
                out += self._draw_panel(panel)
                out.append('')
        return '\n'.join(out).rstrip('\n')

    def _draw_panel( self, panel ):
        out = []
        if panel.title:
            out += [ _center(line,self._width) for line in panel.title.split('\n') ]
        steps = [ i for i in panel.items if isinstance(i,StepHist) ]
        if steps:
            out += self._draw_stephists(panel,steps)
        for item in panel.items:
            if isinstance(item,Hist2D):
                out += self._draw_hist2d(panel,item)
            elif isinstance(item,Bars):
                if panel.ylabel:
                    out.append(f'({panel.ylabel})')
                out += self._draw_bars(item)
            elif isinstance(item,Text):
                out += [ _center(line,self._width) for line in item.text.split('\n') ]
        if any( isinstance(i,Scatter3D) for i in panel.items ):
            out.append(_center('(3D plots are not shown in the terminal, only in windows)',
                               self._width))
            return out
        if panel.xlabel and not steps and not any( isinstance(i,Hist2D) for i in panel.items ):
            out += [ _center(line,self._width) for line in panel.xlabel.split('\n') ]
        return out

    #Coordinates:

    @staticmethod
    def _to_display( v, log ):
        v = np.asarray(v,dtype=float)
        if not log:
            return v
        with np.errstate(divide='ignore',invalid='ignore'):
            return np.where( v > 0, np.log10(np.where(v > 0, v, 1.0)), -np.inf )

    def _xrange( self, panel, edges ):
        lo, hi = panel.xlim if panel.xlim else ( edges[0], edges[-1] )
        if panel.logx:
            pos = [ e for e in edges if e > 0 ]
            lo = lo if lo > 0 else ( pos[0] if pos else 1.0 )
            hi = hi if hi > lo else lo * 10
        elif not hi > lo:
            lo, hi = lo - 1.0, hi + 1.0
        return lo, hi

    @staticmethod
    def _overlap_matrix( edges, lo, hi, n ):
        """Matrix (n x nbins) with the fraction of each of the n equal cells
        between lo and hi which is covered by each bin. Multiplied with the
        bin values, it gives the average of the values over each cell, i.e.
        the step function of the histogram resampled to the cells (assuming
        the contents of each bin to be uniformly distributed inside it). The
        rows sum to the fraction of the cell covered by any bin (at most 1).
        Bins can extend to +-infinity (e.g. in log scale)."""
        edges = np.asarray(edges,dtype=float)
        cellwidth = ( hi - lo ) / n
        bounds = lo + np.arange(n+1) * cellwidth
        with np.errstate(invalid='ignore'):
            overlap = ( np.minimum( edges[None,1:], bounds[1:,None] )
                        - np.maximum( edges[None,:-1], bounds[:-1,None] ) )
            ok = ( edges[1:] > edges[:-1] )
            frac = np.where( ok[None,:], overlap / cellwidth, 0.0 )
        return np.clip( np.nan_to_num(frac,nan=0.0), 0.0, 1.0 )

    def _columns( self, edges, values, lo, hi, log, ncols ):
        """Values of the columns, i.e. the average of the bin values over each
        column (NaN for columns outside the range of the bins)"""
        d = self._to_display(edges,log)
        dlo, dhi = self._to_display([lo,hi],log)
        m = self._overlap_matrix(d,dlo,dhi,ncols)
        res = m @ np.asarray(values,dtype=float)
        res[ m.sum(axis=1) <= 0.0 ] = np.nan
        return res

    def _yscale( self, panel, allvals ):
        """Function mapping values to heights (in rows, from 0 to height), and
        the labels of the y axis (top, bottom)"""
        h = self._height
        v = np.asarray(allvals,dtype=float)
        v = v[np.isfinite(v)]
        if panel.logy:
            pos = v[_significant(v)]
            if not len(pos):
                return ( lambda x : np.zeros_like(np.asarray(x,dtype=float)) ), ( '1', '1' )
            vmin, vmax = ( panel.ylim if panel.ylim else ( pos.min(), pos.max() ) )
            vmin = vmin if vmin > 0 else pos.min()
            lmin, lmax = math.log10(vmin), math.log10(vmax)
            if not lmax > lmin:
                lmin, lmax = lmin - 1, lmax + 1
            def height( x ):
                x = np.asarray(x,dtype=float)
                with np.errstate(divide='ignore',invalid='ignore'):
                    lx = np.log10(np.where(x > 0, x, vmin))
                return np.where( x > 0, np.clip( ( lx - lmin ) / ( lmax - lmin ) * h, 0, h ), 0.0 )
            return height, ( _fmt_y(10**lmax), _fmt_y(10**lmin) )
        vmin, vmax = panel.ylim if panel.ylim else ( min(0.0,v.min()) if len(v) else 0.0,
                                                     v.max() if len(v) else 1.0 )
        if not vmax > vmin:
            vmax = vmin + 1.0
        def height( x ):
            return np.clip( ( np.asarray(x,dtype=float) - vmin ) / ( vmax - vmin ) * h, 0, h )
        return height, ( _fmt_y(vmax), _fmt_y(vmin) )

    #Drawing:

    def _frame( self, rows, ylabels, ncols, lo, hi, logx, xlabel ):
        """Add y axis (with labels at top and bottom), x axis with tick labels
        at the ends and the middle, and the x label, to the rows of the plot
        area (top row first)"""
        c = self._chars
        top, bottom = ylabels
        lw = _ylw
        out = []
        for i,r in enumerate(rows):
            label = top if i == 0 else ( bottom if i == len(rows) - 1 else '' )
            tick = c.ytick if label else c.vline
            out.append( f'{label:>{lw}} {tick}{r}'.rstrip() )
        out.append( ' ' * lw + ' ' + c.corner + c.xtick + c.hline * ( ncols - 2 ) + c.xtick )
        mid = math.sqrt(lo*hi) if logx else 0.5 * ( lo + hi )
        a, m, b = _fmt(lo), _fmt(mid), _fmt(hi)
        axis = [' '] * ( ncols + 2 )
        def put( text, pos ):
            pos = max( 0, min( len(axis) - len(text), pos ) )
            axis[pos:pos+len(text)] = list(text)
        put(a,0)
        put(b,ncols+1-len(b))
        if ncols > len(a) + len(b) + len(m) + 4:
            put(m,( ncols + 1 ) // 2 - len(m) // 2)
        out.append( ' ' * ( lw + 1 ) + ''.join(axis).rstrip() )
        if xlabel:
            out += [ ' ' * ( lw + 2 ) + _center(line,ncols) for line in xlabel.split('\n') ]
        return out

    def _draw_stephists( self, panel, steps ):
        c = self._chars
        lo, hi = self._xrange(panel, [ e for s in steps for e in ( s.edges[0], s.edges[-1] ) ])
        ncols = self.resolution()[0]
        cols = [ self._columns(s.edges,s.values,lo,hi,panel.logx,ncols) for s in steps ]
        #(the vertical scale is for the values of the columns):
        allvals = np.concatenate(cols)
        height, ylabels = self._yscale(panel,allvals[np.isfinite(allvals)])
        h = self._height
        grid = [ [' '] * ncols for _ in range(h) ]
        if len(steps) == 1:
            #Filled columns, with partial characters for fractions of rows:
            nlev = len(c.fill) - 1
            rgb = self._curve_color(steps[0],0)
            for j,v in enumerate(cols[0]):
                if not np.isfinite(v):
                    continue
                units = round( float(height(v)) * nlev )
                for row in range(h):
                    k = min( nlev, max( 0, units - row * nlev ) )
                    if k:
                        grid[h-1-row][j] = self._p(c.fill[k],rgb)
        elif self._use_braille(steps):
            #The curves are drawn as lines with braille characters (of 2x4
            #dots), in colour, or else with different line styles:
            self._draw_braille(panel,steps,lo,hi,ncols,height,grid)
        else:
            #A marker symbol for each curve (for bins with contents, drawing
            #the first curves last, so they are on top):
            for k in reversed(range(len(cols))):
                sym = self._p(self._marker(steps[k],k),self._curve_color(steps[k],k))
                for j,v in enumerate(cols[k]):
                    if not ( np.isfinite(v) and v > 0 ):
                        continue
                    row = min( h - 1, int(float(height(v))) )
                    grid[h-1-row][j] = sym
        out = self._frame([ ''.join(r) for r in grid ], ylabels, ncols, lo, hi,
                          panel.logx, panel.xlabel)
        if panel.ylabel:
            out.insert( 0, f'({panel.ylabel})' )
        labels = [ s.label for s in steps ]
        if any( lab is not None for lab in labels ):
            if len(steps) == 1:
                out.append( f'{self._p(c.fill[-1],self._curve_color(steps[0],0))}'
                            f' {labels[0]}' )
            else:
                braille = self._use_braille(steps)
                entries = []#(text, visible width)
                for k,s in enumerate(steps):
                    if s.label is not None:
                        sym = self._line_sample(s,k) if braille else self._marker(s,k)
                        entries.append( ( f'{self._p(sym,self._curve_color(s,k))} {s.label}',
                                          _width(sym) + 1 + _width(s.label) ) )
                width = max( _width(ln) for ln in out )
                out += _legend_columns(entries,width)
        return out

    def _use_braille( self, steps ):
        """Whether several curves are drawn as lines of braille dots"""
        return self._braille

    def _line_sample( self, s, k ):
        """The legend symbol of the k'th curve drawn with braille dots: a piece
        of line (with its marker, without colour)"""
        if self._nc:
            return { 'solid' : '\u2501\u2501', 'dashed' : '\u2501 \u2501',
                     'dotted' : '\u2505\u2505' }[self._curve_style(s,k)]
        return f'\u2812{self._marker(s,k)}\u2812'

    def _draw_braille( self, panel, steps, lo, hi, ncols, height, grid ):
        """Draw the curves on the grid as lines of braille dots (2 by 4 per
        character). Characters with dots of several curves get the average of
        their colours, and without colour, the curves have their markers along
        them (every _marker_step characters, staggered, so the markers of the
        curves are not on the same columns)."""
        h = self._height
        nx, ny = 2 * ncols, 4 * h
        cells = {}#(row,col) -> [dot bits, indices of the curves]
        def dot( k, x, y ):
            e = cells.setdefault( ( h - 1 - y // 4, x // 2 ), [ 0, set() ] )
            e[0] |= _braille_bits[x % 2][3 - y % 4]
            e[1].add(k)
        markers = []#(row, column, symbol) of the markers along the curves
        for k, s in enumerate(steps):
            v = self._columns(s.edges,s.values,lo,hi,panel.logx,nx)
            ok = np.isfinite(v) & ( v > 0 )
            #(zero values only where they connect to non-zero ones, so the
            #curves do not all overlap at the bottom):
            near = ok.copy()
            near[1:] |= ok[:-1]
            near[:-1] |= ok[1:]
            draw = near & np.isfinite(v) & ( v >= 0 ) if not panel.logy else ok
            #(gaps of dashed and dotted lines, in columns of dots):
            style = self._curve_style(s,k)
            gap = ( ( lambda x : ( x // 4 ) % 2 ) if style == 'dashed' else
                    ( lambda x : x % 2 ) if style == 'dotted' else ( lambda x : False ) )
            prev = None
            for x in range(nx):
                if not draw[x]:
                    prev = None
                    continue
                y = min( ny - 1, int( float(height(v[x])) * 4 ) )
                if not gap(x):
                    for yy in ( range(min(prev,y),max(prev,y)+1) if prev is not None else ( y, ) ):
                        dot(k,x,yy)
                prev = y
                offset = ( 2 + 3 * k ) % _marker_step
                if not self._nc and x % 2 == 0 and ( x // 2 ) % _marker_step == offset:
                    markers.append( ( h - 1 - y // 4, x // 2, self._marker(s,k) ) )
        for (r,c), (bits, ks) in cells.items():
            rgbs = [ self._curve_color(steps[k],k) for k in sorted(ks) ]
            rgb = tuple( round( sum( x[i] for x in rgbs ) / len(rgbs) ) for i in range(3) )
            grid[r][c] = self._p(chr(0x2800 + bits),rgb)
        for r, c, sym in markers:
            grid[r][c] = sym

    def _marker( self, item, k ):
        """Marker symbol of the k'th StepHist of a panel (by position, so the
        curves of a panel have different markers also with fixed colours)"""
        m = self._chars.markers
        return m[ k % len(m) ]

    def _draw_bars( self, item ):
        c = self._chars
        labels = [ ' '.join(str(lab).split()) for lab in item.labels ]
        values = [ float(v) for v in item.values ]
        lw = max( ( _width(lab) for lab in labels ), default = 0 )
        vtexts = [ _fmt(v) for v in values ]
        vw = max( ( len(t) for t in vtexts ), default = 0 )
        nmax = max( 1, self._width - lw - vw - 4 )
        vmax = max( [ v for v in values if v > 0 ], default = 1.0 )
        nlev = len(c.hfill) - 1
        out = []
        colors = item.colors or [ 0 ] * len(values)
        for lab, v, t, col in zip(labels,values,vtexts,colors):
            units = round( max(0.0,v) / vmax * nmax * nlev )
            if v > 0:
                units = max( 1, units )#non-zero values are always visible
            bar = c.hfill[-1] * ( units // nlev ) + ( c.hfill[units % nlev] if units % nlev else '' )
            out.append( f'{" " * ( lw - _width(lab) )}{lab} {c.vline}{self._p(bar,_curve_rgb(col))} {t}' )
        return out

    def _draw_hist2d( self, panel, item ):
        c = self._chars
        xlo, xhi = self._xrange(panel,item.xedges)
        ylo, yhi = ( panel.ylim if panel.ylim else ( item.yedges[0], item.yedges[-1] ) )
        if not yhi > ylo:
            ylo, yhi = ylo - 1.0, yhi + 1.0
        ylabels = ( _fmt_y(yhi), _fmt_y(ylo) )
        ncols, nrows = self.resolution()
        #In colour with half blocks, each character shows two cells:
        half = bool( self._nc and self._halfblocks )
        ncells = 2 * nrows if half else nrows
        v = np.asarray(item.values,dtype=float)
        cells = ( self._overlap_matrix(item.xedges,xlo,xhi,ncols) @ v
                  @ self._overlap_matrix(item.yedges,ylo,yhi,ncells).T )
        cells = np.where(_significant(cells),cells,0.0)
        pos = cells[cells>0]
        nlev = len(c.shades) - 1
        grid = [ [' '] * ncols for _ in range(nrows) ]
        if len(pos):
            vmin, vmax = pos.min(), pos.max()
            def frac( val ):
                if item.logz and vmax > vmin:
                    return ( math.log(val) - math.log(vmin) ) / ( math.log(vmax) - math.log(vmin) )
                return val / vmax
            for i in range(ncols):
                for j in range(nrows):
                    if half:
                        bottom, top = cells[i,2*j], cells[i,2*j+1]
                        if top > 0:
                            grid[nrows-1-j][i] = self._p( '\u2580', _map_rgb(frac(top)),
                                                          _map_rgb(frac(bottom))
                                                          if bottom > 0 else None )
                        elif bottom > 0:
                            grid[nrows-1-j][i] = self._p( '\u2584', _map_rgb(frac(bottom)) )
                        continue
                    val = cells[i,j]
                    if not val > 0:
                        continue
                    f = frac(val)
                    grid[nrows-1-j][i] = self._p( c.shades[ max( 1, math.ceil( f * nlev ) ) ],
                                                  _map_rgb(f) if self._nc else None )
        out = self._frame([ ''.join(r) for r in grid ], ylabels, ncols, xlo, xhi,
                          False, panel.xlabel)
        if panel.ylabel:
            out.insert( 0, f'(y: {panel.ylabel})' )
        if len(pos):
            #The scale, with the value in its middle (the values are those of
            #the characters, from the bins resampled to them):
            #(on a linear scale, the colours start at 0):
            log = ' (log scale)' if item.logz else ''
            vlo = vmin if item.logz else 0.0
            vmid = ( math.sqrt( vmin * vmax ) if item.logz else 0.5 * vmax )
            if half:
                bar = [ self._p( c.shades[-1], _map_rgb( k / 19 ) ) for k in range(20) ]
                scale = f'{"".join(bar[:10])} {_fmt(vmid)} {"".join(bar[10:])}'
                out.append( f'per cell: {_fmt(vlo)} {scale} {_fmt(vmax)}{log}' )
            else:
                mid = math.ceil( 0.5 * nlev )
                lo_c, mid_c, hi_c = ( self._p(c.shades[k],_map_rgb(f) if self._nc else None)
                                      for k, f in ( (1,0.0), (mid,0.5), (nlev,1.0) ) )
                out.append( f'per cell: {lo_c} = {_fmt(vlo)} ... {mid_c} = {_fmt(vmid)}'
                            f' ... {hi_c} = {_fmt(vmax)}{log}' )
        return out

class UnicodeBackend(_TextBackend):
    """Plots drawn as text with Unicode characters (block elements and box
    drawing), for terminals which can show these characters (files are
    always written as UTF-8). The unicode_width and unicode_height options set
    the size of the plots in characters (default is the width of the
    terminal, up to 250, and a height of 15). The unicode_color option
    ('auto', 'always' or 'never') sets whether plots are shown in colour
    (default 'auto': in terminals, unless the NO_COLOR environment variable
    is set, or always if FORCE_COLOR is set). Files are written without
    colours."""
    name = 'unicode'
    priority = 100
    formats: ClassVar[dict] = { 'txt' : 100 }
    _chars = _unicode
    _halfblocks = True
    _braille = True
    viewer_module = '_plotbackend_text_gui'

    @classmethod
    def can_show( cls ):
        #Only in terminals which can show the characters:
        return _can_encode(cls._chars)

    def __init__( self, unicode_width = None, unicode_height = None,
                  unicode_color = 'auto' ):
        super().__init__(unicode_width,unicode_height,unicode_color)

class AsciiBackend(_TextBackend):
    """Plots drawn as text with ASCII characters only, for any terminal. The
    ascii_width and ascii_height options set the size of the plots in
    characters (default is the width of the terminal, up to 250, and a height
    of 15), and the ascii_color option whether they are shown in colour (as
    unicode_color for the unicode backend)."""
    name = 'ascii'
    priority = 10
    formats: ClassVar[dict] = { 'txt' : 10 }
    _chars = _ascii
    encoding = 'ascii'
    viewer_module = '_plotbackend_text_gui'

    def __init__( self, ascii_width = None, ascii_height = None,
                  ascii_color = 'auto' ):
        super().__init__(ascii_width,ascii_height,ascii_color)
