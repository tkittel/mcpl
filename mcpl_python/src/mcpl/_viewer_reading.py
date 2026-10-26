
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
thread, computing the figures of its plots, and what it finds in the file
(see _Computation.found)."""

__all__ = []

import threading

from ._common import MCPLError
from ._viewer_ui import default_cache_limit, used_particles

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

    def _reading_settings( self ):
        """The settings which are read (a copy, with the range of the particles
        used by the plots, see cache_info)"""
        s = self._s.copy()
        info = self.cache_info()
        if not info['fits']:
            s.limit = info['nused']
        return s

    @property
    def error( self ):
        """The error of the reading (e.g. "no particles picked"), or None"""
        with self._lock:
            return self._error

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
            self._job = ( self._generation, self._reading_settings() )
            self._wake.notify_all()

    def _worker( self ):
        from ._reader import MCPLFile
        with MCPLFile(self.filename) as f:
            #(the particles are kept in memory up to the cache limit, so
            #those are only read, and decompressed, once):
            f = _Cache(f,self)
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

    #The particles kept in memory (see _Cache):

    @property
    def cache_limit( self ):
        """The memory (in bytes) for the particles kept in memory, or None
        for no cache"""
        return getattr(self,'_cache_limit',_cache_limit)

    def set_cache_limit( self, nbytes ):
        """Set the memory (in bytes) for the particles kept in memory, or None
        for no cache. The plots use the particles of the range which fit (and
        the others are not read), and without a cache all particles of the
        range, which are read from the file again for each change."""
        self._cache_limit = None if nbytes is None else max( 0.0, float(nbytes) )
        self._restart()

    def cache_info( self ):
        """The particles of the range in memory, as a dict: the number of
        particles in the range (nrange), the bytes per particle in memory
        (size), the bytes they need (needed), the cache limit (limit, None for
        no cache), whether all particles of the range are used (fits: they
        fit, or there is no cache), the number of particles of the range
        used by the plots (nused), and the bytes kept in memory (cached)"""
        if getattr(self,'_particle_nbytes',None) is None:
            from ._reader import MCPLFile
            with MCPLFile(self.filename) as f:
                b = f.read_block()
                self._particle_nbytes = ( _block_nbytes(b[:]) / len(b) if b is not None
                                          else f.particlesize )
        size, limit = self._particle_nbytes, self.cache_limit
        first, end = self._range(self._s.skip,self._s.limit)
        n = end - first
        fits = limit is None or n * size <= limit
        nused = used_particles(n,size,limit)
        return { 'nrange' : n, 'size' : size, 'needed' : n * size, 'limit' : limit,
                 'fits' : fits, 'nused' : nused,
                 'cached' : 0 if limit is None else nused * size }

    def _blocks( self, f, settings, gen, progress ):
        """Blocks of the range of particles, picked and edited, with the
        counts of all particles in the range (and their weights), see
        _range_blocks"""
        self._range_counts = [ 0, 0.0 ]
        yield from _range_blocks(f,settings,progress,self._range_counts,
                                 lambda : self._cancelled(gen),
                                 blocks = f.blocks(*self._range(settings.skip,settings.limit)))

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
                self._publish(gen,figures=known,constants=done[2]['constants'],progress='',
                              counts=done[3])
                self._on_found(done[2])
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
        figs, found = figures(comp.figures()), comp.found()
        self._publish(gen,figures=figs,constants=found['constants'],progress='',counts=counts)
        with self._lock:
            current = gen == self._generation
            if current:
                self._done = ( key, figs, found, counts )
        if current:
            self._on_found(found)

    def _on_found( self, found ):
        """Called after a reading with what it found (see _Computation.found)"""

class _Cancelled(Exception):
    pass

#The cache limit (in bytes) unless changed (see _Reading.set_cache_limit, and
#the limits offered by the viewers in _viewer_ui.cache_presets):
_cache_limit = default_cache_limit

def _block_nbytes( b ):
    """The memory used by a particle block"""
    from ._numpy import np
    return sum( v.nbytes for v in vars(b).values() if isinstance(v,np.ndarray) )

class _Cache:
    """An MCPLFile whose particle blocks are kept in memory once they were read
    (as copies, since the file reuses its block objects): those from the start
    of the range read (see blocks) which fit in the cache limit of the viewer,
    so only the particles after them are read from the file again"""
    def __init__( self, f, viewer ):
        self._f, self._viewer = f, viewer
        #(the blocks kept, from the particle start to the end, and their bytes):
        self._blocks, self._start, self._end, self._nbytes = [], 0, 0, 0

    def __getattr__( self, name ):
        return getattr(self._f,name)

    def blocks( self, first, end ):
        """The blocks of the file with the particles from first to end"""
        f, limit = self._f, self._viewer.cache_limit
        #(the blocks kept start at the block of the first particle):
        start = first - first % f.blocklength
        if start != self._start or limit is None:
            self._blocks, self._start, self._end, self._nbytes = [], start, start, 0
        while self._blocks and self._nbytes > limit:#(after lowering the limit)
            b = self._blocks.pop()
            self._end -= len(b)
            self._nbytes -= _block_nbytes(b)
        for b in list(self._blocks):
            if b.file_offset >= end:
                return
            yield b
        if self._end >= end:
            return
        #(the blocks after those kept, which are kept while they fit):
        f.rewind()
        if self._end:
            f.skip_forward(self._end - 1)#(so the next block starts at the end)
        while True:
            b = f.read_block()
            if b is None or b.file_offset >= end:
                return
            b = b[:]
            nb = _block_nbytes(b)
            if ( limit is not None and b.file_offset == self._end
                 and self._nbytes + nb <= limit ):
                self._blocks.append(b)
                self._end += len(b)
                self._nbytes += nb
            yield b

def _make_filler( text, settings = None ):
    """Histogram filler of a plot (a histogram string), of the particles picked
    and edited with the settings (if given, for the title)"""
    from ._histogram import _filler_for
    from ._histstring import _parse_hist
    o = _parse_hist(text)
    if o['print']:
        raise MCPLError('The histogram option print can not be used in the viewer')
    h = _filler_for(o)
    if settings is not None:
        h._selection = tuple( None if e is None else e.expression
                              for e in ( settings.pick, settings.edit ) )
    return h

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
            h = self._guard(p,_make_filler,p,settings)
            self._plots.append( ( p, h ) )
        self._lims = { f : [ None, None ] for f in _const_fields }
        self._types = {}#(pdgcode -> sum of weights)
        #(the sums giving the correlation coefficients of the fields of the
        #correlation plots):
        from ._stdviews import _groups
        from ._viewer_overviews import Moments
        self._moments = Moments(dict.fromkeys( v for g in _groups.values()
                                               for v in g[3].get('variables',()) ))

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
        pdg, idx = np.unique(np.broadcast_to(b.pdgcode,(len(b),)),return_inverse=True)
        sums = np.bincount(idx.ravel(),weights=np.broadcast_to(b.weight,(len(b),)),
                           minlength=len(pdg))
        for k, w in zip(pdg.tolist(),sums.tolist()):
            self._types[k] = self._types.get(k,0.0) + w
        self._moments.add(b)

    def constants( self ):
        """The fields where all particles have the same value, with the value
        (as text, with its unit)"""
        from ._exprcore import _expr_field_dims, _expr_unit_hints
        res = {}
        for field, ( lo, hi ) in self._lims.items():
            if lo is not None and lo == hi:
                unit = _expr_unit_hints.get(_expr_field_dims.get(field))
                res[field] = f'{lo:g}' + ( f' {unit}' if unit else '' )
        return res

    def found( self ):
        """What was found: the fields with one value (see constants), the
        particle types as (pdgcode, sum of weights), the largest first, and
        the correlation coefficients of the fields of correlation plots (see
        Moments.coefficients)"""
        types = sorted( self._types.items(), key = lambda t : ( -t[1], t[0] ) )
        return { 'constants' : self.constants(), 'types' : types,
                 'correlations' : self._moments.coefficients() }

    def figures( self ):
        """The figures of the plots (with the pick and edit expressions as
        titles, as for mcpltool -H, see _histogram._selection_title)"""
        from ._histogram import _selection_title
        from .plotting import Figure, Panel, Text
        s = self._settings
        title = _selection_title(*( None if e is None else e.expression
                                    for e in ( s.pick, s.edit ) ))
        res = {}
        for p, h in self._plots:
            hist = self._guard(p,h.result) if h is not None else None
            if hist is None:
                res[f'plot:{p}'] = Figure( title = title, panels = [ Panel( xlabel = p,
                                           items = [ Text(self._errors[p]) ] ) ] )
                continue
            res[f'plot:{p}'] = hist.figure()
        return res

def _range_blocks( f, settings, progress = None, counts = None, cancelled = None,
                   blocks = None ):
    """Blocks of the range of particles of the file f (see settings), picked
    and edited, from its blocks (or those given). progress (if given) is called
    with the fraction of the range read, counts (if given) gets the number of
    particles in the range and the sum of their weights, and cancelled (if
    given) tells when to stop (with _Cancelled)."""
    from ._blocks import _EditedParticleBlock
    from ._reader import _blocks_in_range, _particle_range
    skip, end = _particle_range(f.nparticles,settings.skip,settings.limit or None)
    if counts is not None:
        counts[:] = [ end - skip, 0.0 ]
    for b in _blocks_in_range(f.particle_blocks if blocks is None else blocks,skip,end):
        if cancelled is not None and cancelled():
            raise _Cancelled()
        if counts is not None:
            counts[1] += float(b.weight.sum())
        if progress is not None:
            progress( ( b.file_offset + len(b) - skip ) / max( 1, end - skip ) )
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
