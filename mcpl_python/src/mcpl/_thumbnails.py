
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

"""Small images of figures (see mcpl.plotting) for the cards of the plots in
the viewers with windows, drawn directly into pixels with numpy (much faster
than with matplotlib), without texts, ticks, legends and colour bars."""

__all__ = []

import functools

from ._numpy import np


@functools.cache
def _colors():
    """The colours of curves (of the colour cycle of matplotlib, see
    plotting._line_style), and of maps (viridis), as RGB arrays (0 to 255)"""
    import matplotlib
    import matplotlib.colors
    cycle = np.array([ matplotlib.colors.to_rgb(f'C{i}') for i in range(10) ]) * 255
    lut = matplotlib.colormaps['viridis'](np.linspace(0,1,256))[:,:3] * 255
    return cycle.astype(np.uint8), lut.astype(np.uint8)

def thumbnail_png( figure, width, height ):
    """The figure as a PNG image of width x height pixels"""
    img = np.full((height,width,3),255,dtype=np.uint8)
    nr, nc = figure.nrows, figure.ncols
    gap = 2
    pw, ph = ( width - gap * ( nc + 1 ) ) // nc, ( height - gap * ( nr + 1 ) ) // nr
    for i, panel in enumerate(figure.panels[:nr*nc]):
        if panel is None:#(an empty cell of the grid)
            continue
        r, c = divmod(i,nc)
        x0, y0 = gap + c * ( pw + gap ), gap + r * ( ph + gap )
        _panel(img[y0:y0+ph,x0:x0+pw],panel)
        #(a frame, as the axes):
        img[y0,x0:x0+pw] = img[y0+ph-1,x0:x0+pw] = 80
        img[y0:y0+ph,x0] = img[y0:y0+ph,x0+pw-1] = 80
    return _png(img)

def _scaled( v, log, lo, hi ):
    """The values v (in the range lo to hi, log10 if log is set) as fractions
    of the range (NaN for values which can not be shown on a log scale)"""
    v = np.asarray(v,dtype=float)
    if log:
        with np.errstate(divide='ignore',invalid='ignore'):
            v = np.where(v > 0,np.log10(np.where(v > 0,v,1)),np.nan)
        lo, hi = np.log10(lo), np.log10(hi)
    return ( v - lo ) / ( hi - lo ) if hi > lo else np.zeros_like(v)

def _range( values, log, lim ):
    """The range of the axis of the values (of the limits, if given)"""
    if lim:
        return lim
    v = np.concatenate([ np.ravel(x) for x in values ]) if values else np.zeros(0)
    v = v[np.isfinite(v)]
    if log:
        v = v[v > 0]
    if not len(v):
        return ( 1.0, 10.0 ) if log else ( 0.0, 1.0 )
    lo, hi = float(v.min()), float(v.max())
    return ( lo, hi ) if hi > lo else ( ( lo / 2, lo * 2 ) if log else ( lo - 0.5, hi + 0.5 ) )

def _panel( img, panel ):
    from .plotting import Bars, Hist2D, Scatter3D, StepHist, _line_style
    cycle, lut = _colors()
    h, w = img.shape[:2]
    curves = [ ( i, it ) for i, it in enumerate(panel.items) if isinstance(it,StepHist) ]
    if curves:
        xlo, xhi = _range([ it.edges for _, it in curves ],panel.logx,panel.xlim)
        vals = [ it.values for _, it in curves ]
        ylo, yhi = _range(vals,panel.logy,panel.ylim)
        if not panel.logy and not panel.ylim:
            ylo = min( ylo, 0.0 )
        #(the edges of the pixel columns, on the scale of the axis):
        cols = np.linspace(0,1,w + 1)
        for i, it in curves:
            fx = _scaled(it.edges,panel.logx,xlo,xhi)
            values = np.asarray(it.values,dtype=float)
            #(each column shows the largest value of the bins in it, so narrow
            #peaks are not lost):
            first = np.searchsorted(fx,cols[:-1],side='right') - 1
            last = np.searchsorted(fx,cols[1:],side='left') - 1
            inside = ( last >= 0 ) & ( first < len(values) )
            first, last = np.clip(first,0,len(values) - 1), np.clip(last,0,len(values) - 1)
            top = np.array([ values[a:max(a,b)+1].max() for a, b in zip(first,last) ])
            y = np.where(inside,_scaled(top,panel.logy,ylo,yhi),np.nan)
            rows = np.where(np.isfinite(y),np.clip(( h - 2 ) * ( 1 - y ),0,h - 1),h - 1).round().astype(int)
            rows[~inside] = -1
            color = cycle[_line_style(it.color if it.color is not None else i)[0]]
            prev = None
            for x, row in enumerate(rows):
                if row < 0:
                    prev = None
                    continue
                a, b = ( row, row ) if prev is None else ( min( row, prev ), max( row, prev ) )
                #(2 pixels wide, as the lines of the plots):
                img[max(0,a-1):b+1,x] = color
                if x + 1 < w:
                    img[max(0,row-1):row+1,x+1] = color
                prev = row
    #(3D points in an oblique projection, with y going into the picture):
    points = [ ( i, it ) for i, it in enumerate(panel.items) if isinstance(it,Scatter3D) ]
    if points:
        xyz = [ np.concatenate([ np.asarray(getattr(it,c),dtype=float) for _, it in points ])
                for c in 'xyz' ]
        lims = [ ( v.min(), v.max() ) if len(v) else ( 0.0, 1.0 ) for v in xyz ]
        for i, it in points:
            fx, fy, fz = ( _scaled(np.asarray(getattr(it,c),dtype=float),False,*lim)
                           for c, lim in zip('xyz',lims) )
            u, v = 0.7 * fx + 0.3 * fy, 0.7 * fz + 0.3 * fy
            cols = np.clip(( u * ( w - 1 ) ).round(),0,w - 1).astype(int)
            rows = np.clip(( ( 1 - v ) * ( h - 1 ) ).round(),0,h - 1).astype(int)
            ok = np.isfinite(u) & np.isfinite(v)
            img[rows[ok],cols[ok]] = cycle[_line_style(it.color if it.color is not None else i)[0]]
    for it in panel.items:
        if isinstance(it,Hist2D):
            v = np.asarray(it.values,dtype=float)
            fx = _scaled(it.xedges,False,it.xedges[0],it.xedges[-1])
            fy = _scaled(it.yedges,False,it.yedges[0],it.yedges[-1])
            ix = np.clip(np.searchsorted(fx,np.linspace(0,1,w,endpoint=False) + 0.5 / w,side='right') - 1,
                         0,v.shape[0] - 1)
            iy = np.clip(np.searchsorted(fy,np.linspace(1,0,h,endpoint=False) - 0.5 / h,side='right') - 1,
                         0,v.shape[1] - 1)
            m = v[np.ix_(ix,iy)].T
            lo, hi = _range([ m ],it.logz,None)
            f = _scaled(m,it.logz,lo,hi)
            if not it.logz:
                f = np.where(m > 0,f,np.nan)#(empty bins are not coloured)
            ok = np.isfinite(f)
            img[ok] = lut[np.clip(( f[ok] * 255 ).round().astype(int),0,255)]
        elif isinstance(it,Bars) and len(it.values):
            n = len(it.values)
            lo, hi = _range([ it.values ],panel.logx if it.horizontal else panel.logy,None)
            lo = lo / 10 if ( panel.logx if it.horizontal else panel.logy ) else 0.0
            f = np.nan_to_num(np.clip(_scaled(it.values,panel.logx if it.horizontal else panel.logy,
                                              lo,hi),0,1))
            size = ( h if it.horizontal else w ) / n
            for k, ( fk, c ) in enumerate(zip(f,it.colors or [ 0 ] * n)):
                a, b = int(k * size + 0.2 * size), max( int(k * size + 0.2 * size) + 1, int(( k + 0.8 ) * size) )
                if it.horizontal:
                    img[a:b,:round(fk * w)] = cycle[c % 10]
                else:
                    img[h - round(fk * h):,a:b] = cycle[c % 10]

def _png( img ):
    """The RGB image (an array of shape (height,width,3)) as PNG data"""
    import struct
    import zlib
    h, w = img.shape[:2]
    raw = b''.join( b'\x00' + img[r].tobytes() for r in range(h) )
    def chunk( kind, data ):
        return struct.pack('>I',len(data)) + kind + data + struct.pack('>I',zlib.crc32(kind + data))
    return ( b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))
             + chunk(b'IDAT',zlib.compress(raw,6)) + chunk(b'IEND',b'') )
