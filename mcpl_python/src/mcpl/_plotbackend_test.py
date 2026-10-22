
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

"""Plotting backend for unit tests, which prints a description of the figures
instead of drawing them."""

__all__ = []

from typing import ClassVar

from ._numpy import np
from ._plotbackend import PlotBackend
from .plotting import Bars, Hist2D, Scatter3D, StepHist, Text


def _fmt( x ):
    return f'{float(x):.6g}'

def _describe_item( item ):
    if isinstance(item,StepHist):
        v = np.asarray(item.values,dtype=float)
        nz = np.flatnonzero(v)
        return ( f'StepHist label={item.label!r} color={item.color} bins={len(v)}'
                 f' edges=[{_fmt(item.edges[0])},{_fmt(item.edges[-1])}]'
                 f' sum={_fmt(v.sum())} max={_fmt(v.max() if len(v) else 0)}'
                 f' nonzero_bins={len(nz)}' )
    if isinstance(item,Hist2D):
        v = np.asarray(item.values,dtype=float)
        return ( f'Hist2D shape={v.shape} x=[{_fmt(item.xedges[0])},{_fmt(item.xedges[-1])}]'
                 f' y=[{_fmt(item.yedges[0])},{_fmt(item.yedges[-1])}]'
                 f' sum={_fmt(v.sum())} logz={item.logz}' )
    if isinstance(item,Bars):
        return ( 'Bars ' + ', '.join(f'{lbl!r}={_fmt(v)}' for lbl,v in
                                     zip(item.labels,item.values))
                 + ( ' (horizontal)' if item.horizontal else '' ) )
    if isinstance(item,Scatter3D):
        return ( f'Scatter3D label={item.label!r} color={item.color} points={len(item.x)}'
                 + ''.join( f' {n}=[{_fmt(min(v))},{_fmt(max(v))}]' for n, v in
                            ( ('x',item.x), ('y',item.y), ('z',item.z) ) if len(v) ) )
    assert isinstance(item,Text)
    return f'Text {item.text!r}'

def describe( figures ):
    lines = []
    for i,f in enumerate(figures):
        lines.append(f'Figure {i+1} ({f.nrows}x{f.ncols}): {f.title!r}')
        for p in f.panels:
            if p is None:
                lines.append('  (empty cell)')
                continue
            opts = [ o for o,v in (('logx',p.logx),('logy',p.logy)) if v ]
            if p.xlim:
                opts.append(f'xlim=[{_fmt(p.xlim[0])},{_fmt(p.xlim[1])}]')
            if getattr(p,'aspect',None):
                opts.append(f'aspect={_fmt(p.aspect)}')
            lines.append(f'  Panel {p.title!r} xlabel={p.xlabel!r} ylabel={p.ylabel!r} '
                         + ' '.join(opts))
            for item in p.items:
                lines.append('    ' + _describe_item(item))
    return '\n'.join(lines)

class Backend(PlotBackend):
    """Prints a description of figures (show) or writes it to a file
    (save)."""
    name = 'test'
    formats: ClassVar[dict] = { 'txt' : 0, 'pdf' : 0, 'png' : 0 }

    def show( self, figures ):
        print(describe(figures))

    def save( self, figures, filename ):
        import pathlib
        self.check_format(filename)
        pathlib.Path(filename).write_text(describe(figures)+'\n',encoding='utf-8')
        return [ filename ]
