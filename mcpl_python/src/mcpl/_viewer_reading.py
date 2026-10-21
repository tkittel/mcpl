
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

"""The reading of the file of the viewer (see _viewer.Viewer) in a background
thread, computing the figures of its plots, and the fields where all particles
have the same value."""

__all__ = []

import copy
import threading

from ._common import MCPLError

#Numbers of particles read after which the figures are updated (and then every
#further _update_step particles):
_update_counts = ( 20000, 200000, 1000000, 2000000 )
_update_step = 2000000
#Particles kept in memory during the first pass (to show provisional figures
#before the ranges of the plots are known):
_preview_max = 200000

def _update_points():
    """Particle counts at which figures are updated: 20k, 200k, 1M, 2M, 4M, ..."""
    yield from _update_counts
    n = _update_counts[-1]
    while True:
        n += _update_step
        yield n

class _Reading:
    """The reading of the file of the viewer in the background (the part of
    _viewer.Viewer which computes the figures)"""

    #Reading in the background:

    def start( self ):
        """Start reading the file in the background"""
        if self._thread is None:
            self._thread = threading.Thread(target=self._worker,daemon=True)
            self._thread.start()
        self._restart()

    def stop( self ):
        with self._lock:
            self._stopping = True
            self._wake.notify_all()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    @property
    def reading( self ):
        """Whether the file is being read (for the current settings)"""
        with self._lock:
            return not ( self._job is None and self._seen_gen == self._generation )

    def wait( self ):
        """Wait until the current reading is done (for tests and scripts)"""
        import time
        while self.reading:
            time.sleep(0.01)

    def poll( self ):
        """Whether the figures or status changed since the last call"""
        with self._lock:
            changed = self._updates != self._seen
            self._seen = self._updates
        return changed

    def _restart( self ):
        with self._lock:
            self._generation += 1
            self._job = ( self._generation, self._s.copy() )
            self._wake.notify_all()

    def _worker( self ):
        from ._reader import MCPLFile
        with MCPLFile(self.filename) as f:
            #(small files are kept in memory, so they are only read, and
            #decompressed, once):
            if f.nparticles * f.particlesize <= _memory_limit:
                f = _InMemory(f)
            while True:
                with self._lock:
                    while self._job is None and not self._stopping:
                        self._wake.wait()
                    if self._stopping:
                        return
                    gen, settings = self._job
                    self._job = None
                try:
                    self._read(f,gen,settings)
                except _Cancelled:
                    pass
                except MCPLError as e:
                    self._publish(gen,error=str(e))
                except ( ValueError, TypeError, ArithmeticError, IndexError,
                         KeyError, OSError ) as e:#(shown, so the viewer stays usable)
                    self._publish(gen,error=f'{type(e).__name__}: {e}')
                with self._lock:
                    if self._job is None:
                        self._seen_gen = gen

    def _cancelled( self, gen ):
        with self._lock:
            return gen != self._generation or self._stopping

    def _publish( self, gen, figures = None, progress = None, counts = None,
                  error = None, constants = None ):
        with self._lock:
            if gen != self._generation:
                return
            if figures is not None:
                self._figures = figures
                #(the fields with one value are only known from the
                #computation of the second pass):
                self._constants = constants or {}
            if progress is not None:
                self._progress = progress
            if counts is not None:
                self._counts = counts
            self._error = error
            self._updates += 1

    def _blocks( self, f, settings, gen, progress ):
        """Blocks of the range of particles, picked and edited, with the
        counts of all particles in the range (and their weights), see
        _range_blocks"""
        self._range_counts = [ 0, 0.0 ]
        yield from _range_blocks(f,settings,progress,self._range_counts,
                                 lambda : self._cancelled(gen))

    def preview( self, plot, nparticles = 20000 ):
        """The figure of the plot (a histogram string) for the first nparticles
        particles of the range of the file (then picked and edited), for
        previews of plots before they are added, or None if there are no
        values. The plot must be valid (see check)."""
        from ._reader import MCPLFile
        s = self._s.copy()
        s.plots = [ plot ]
        s.limit = min( s.limit, nparticles ) if s.limit else nparticles
        with MCPLFile(self.filename) as f:
            blocks = list(_range_blocks(f,s))
            if not blocks:
                return None
            return _preview(f,s,blocks)[f'plot:{plot}']

    def _read( self, f, gen, settings ):
        """Read the file twice (for the ranges, and to fill the histograms),
        publishing figures at the update points. The figures of the plots of the
        last reading which was done are kept if the particles are the same (the
        same skip, limit, pick and edit), so only new plots are filled."""
        key = ( settings.skip, settings.limit,
                *( None if e is None else e.expression for e in ( settings.pick, settings.edit ) ) )
        done = self._done if self._done is not None and self._done[0] == key else None
        known = {}
        if done is not None:
            known = { k : fig for k, fig in done[1].items() if k[5:] in settings.plots }
            settings = settings.copy()
            settings.plots = [ p for p in settings.plots if f'plot:{p}' not in known ]
            if not settings.plots:
                self._publish(gen,figures=known,constants=done[2],progress='',counts=done[3])
                return
        def figures( figs ):
            return None if figs is None else { **known, **figs }
        frac = [0.0]
        def progress( x ):
            frac[0] = min( 1.0, x )
        def make():
            return _Computation(f,settings)
        #Pass 1: ranges, and provisional figures from the first particles:
        comp = make()
        kept, nkept, n, w = [], 0, 0, 0.0
        points = _update_points()
        nextpoint = next(points)
        self._publish(gen,figures=figures({}),progress='reading: finding ranges',counts=None)
        for b in self._blocks(f,settings,gen,progress):
            comp.add1(b)
            n += len(b)
            w += float(b.weight.sum())
            if nkept < _preview_max:
                kept.append(b)
                nkept += len(b)
            if n >= nextpoint:
                while n >= nextpoint:
                    nextpoint = next(points)
                if nkept <= _preview_max:
                    figs = _preview(f,settings,kept)
                else:
                    figs = None
                self._publish(gen,figures=figures(figs),
                              progress=f'reading: finding ranges ({100*frac[0]:.0f}%)')
        counts = ( n, self._range_counts[0], w, self._range_counts[1] )
        if n == 0:
            self._publish(gen,figures={},progress='',counts=counts,
                          error='no particles picked' if settings.pick else 'no particles')
            return
        del kept
        comp.start2(n)
        points = _update_points()
        nextpoint = next(points)
        m = 0
        self._publish(gen,progress='reading: 0% of particles',counts=counts)
        for b in self._blocks(f,settings,gen,progress):
            comp.add2(b)
            m += len(b)
            if m >= nextpoint and m < n:
                while m >= nextpoint:
                    nextpoint = next(points)
                self._publish(gen,figures=figures(comp.figures()),constants=comp.constants(),
                              progress=f'reading: {100*frac[0]:.0f}% of particles')
        figs, constants = figures(comp.figures()), comp.constants()
        self._publish(gen,figures=figs,constants=constants,progress='',counts=counts)
        with self._lock:
            if gen == self._generation:
                self._done = ( key, figs, constants, counts )

class _Cancelled(Exception):
    pass

#The largest particle data (in bytes) of files kept in memory by the viewer:
_memory_limit = 500e6

class _InMemory:
    """An MCPLFile whose particle blocks are kept in memory when they were all
    read once (as copies, since the file reuses its block objects)"""
    def __init__( self, f ):
        self._f = f
        self._blocks = None

    def __getattr__( self, name ):
        return getattr(self._f,name)

    @property
    def particle_blocks( self ):
        if self._blocks is not None:
            yield from self._blocks
            return
        blocks = []
        for b in self._f.particle_blocks:
            b = b[:]
            blocks.append(b)
            yield b
        #(only when all were read, not after a reading which stopped early):
        self._blocks = blocks

def _make_filler( text, pick ):
    """Histogram filler of a plot (a histogram string)"""
    from ._histogram import _filler_for
    from ._histstring import _parse_hist
    o = _parse_hist(text)
    if o['print']:
        raise MCPLError('The histogram option print can not be used in the viewer')
    return _filler_for(o,pick = pick)

#Fields for which it is noted when all particles have the same value:
_const_fields = ( 'pdgcode', 'userflags', 'ekin', 'x', 'y', 'z', 'ux', 'uy', 'uz',
                  'time', 'weight', 'polx', 'poly', 'polz' )

class _Computation:
    """The plots for the views, and the fields where all particles have the
    same value, from the blocks given to add1 (first pass) and add2 (second
    pass, after start2). A plot which fails (e.g. one without values) shows
    the problem, without stopping the others."""
    def __init__( self, f, settings ):
        self._settings = settings
        self._errors = {}#(plot -> the problem)
        self._plots = []
        for p in settings.plots:
            h = self._guard(p,_make_filler,p,None)
            self._plots.append( ( p, h ) )
        self._lims = { f : [ None, None ] for f in _const_fields }

    def _guard( self, p, fct, *args ):
        """fct(*args), or None if the plot p failed (noting the problem)"""
        if p in self._errors:
            return None
        try:
            return fct(*args)
        except MCPLError as e:
            self._errors[p] = str(e)
            return None

    def add1( self, b ):
        for p, h in self._plots:
            if h is not None and h.needs_range:
                self._guard(p,h.add_range,None,b)

    def start2( self, n ):
        for p, h in self._plots:
            if h is not None and h.needs_range:
                self._guard(p,h.start_fill)

    def add2( self, b ):
        from ._numpy import np
        for p, h in self._plots:
            if h is not None:
                self._guard(p,h.add,None,b)
        for field, lim in self._lims.items():
            v = np.asarray(getattr(b,field))
            lo, hi = float(v.min()), float(v.max())
            lim[0] = lo if lim[0] is None else min( lim[0], lo )
            lim[1] = hi if lim[1] is None else max( lim[1], hi )

    def constants( self ):
        """The fields where all particles have the same value, with the value
        (as text, with its unit)"""
        from ._expressions import _expr_field_dims, _expr_unit_hints
        res = {}
        for field, ( lo, hi ) in self._lims.items():
            if lo is not None and lo == hi:
                unit = _expr_unit_hints.get(_expr_field_dims.get(field))
                res[field] = f'{lo:g}' + ( f' {unit}' if unit else '' )
        return res

    def figures( self ):
        """The figures of the plots (with the pick and edit expressions as
        titles, as for mcpltool -H)"""
        from .plotting import Figure, Panel, Text
        s = self._settings
        title = '\n'.join( f'{what}: {e.expression}' for what, e in
                           (('pick',s.pick),('edit',s.edit)) if e is not None ) or None
        res = {}
        for p, h in self._plots:
            hist = self._guard(p,h.result) if h is not None else None
            if hist is None:
                res[f'plot:{p}'] = Figure( title = title, panels = [ Panel( xlabel = p,
                                           items = [ Text(self._errors[p]) ] ) ] )
                continue
            hist = copy.deepcopy(hist)
            hist.title = title
            res[f'plot:{p}'] = hist.figure()
        return res

def _range_blocks( f, settings, progress = None, counts = None, cancelled = None ):
    """Blocks of the range of particles of the file f (see settings), picked
    and edited. progress (if given) is called with the fraction of the range
    read, counts (if given) gets the number of particles in the range and the
    sum of their weights, and cancelled (if given) tells when to stop (with
    _Cancelled)."""
    from ._blocks import _EditedParticleBlock
    n = f.nparticles
    skip = min( settings.skip or 0, n )
    end = n if not settings.limit else min( n, skip + settings.limit )
    if counts is not None:
        counts[:] = [ end - skip, 0.0 ]
    for b in f.particle_blocks:
        if cancelled is not None and cancelled():
            raise _Cancelled()
        off = b.file_offset
        if off + len(b) <= skip:
            continue
        if off >= end:
            break
        b = b[max(0,skip-off):min(len(b),end-off)]
        if counts is not None:
            counts[1] += float(b.weight.sum())
        if progress is not None:
            progress( ( max(off,skip) + len(b) - skip ) / max( 1, end - skip ) )
        if settings.pick is not None:
            b = b[settings.pick(b)]
        if not len(b):
            continue#(no particles picked in this block)
        if settings.edit is not None:
            b = _EditedParticleBlock(b,settings.edit(b))
        yield b

def _preview( f, settings, blocks ):
    """Figures from the blocks kept in memory (both passes over them)"""
    comp = _Computation(f,settings)
    for b in blocks:
        comp.add1(b)
    comp.start2(sum( len(b) for b in blocks ))
    for b in blocks:
        comp.add2(b)
    return comp.figures()
