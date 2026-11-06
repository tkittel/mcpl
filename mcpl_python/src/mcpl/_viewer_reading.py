
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

class _ReadingState:
    """What the reading thread (see _read_file) and the viewer (see _Reading)
    share, guarded by lock: the reading to do (job: the generation, settings,
    and range of the particles), and what the readings gave (the figures by
    view key, the fields with one value, the progress, the counts of the
    particles, an error, and the numbers of updates of the figures and of the
    status). The thread only gets this object (and the name of the file), not
    the viewer."""
    def __init__( self ):
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.figures = {}#view key -> Figure
        self.constants = {}#field -> text of the value all particles have
        #(the correlation coefficients of the particles in the figures, while
        #they are read, see Moments.coefficients):
        self.correlations = None
        self.progress = ''
        self.counts = None
        self.error = None
        self.generation = 0#(incremented for every new reading)
        self.seen_gen = 0#(the last reading which is done)
        #(the figures of the last reading which was done, for its particles,
        #which are kept for plots which do not change, see _read):
        self.done = None#(particles key, {view key: figure}, found, counts)
        self.found_pending = None#(what a reading found, see _Reading._apply_found)
        self.updates, self.status_updates = 0, 0
        self.job = None
        self.stopping = False
        #(the memory for the particles kept, and whether more of them are
        #being put there, see _Cache):
        self.cache_limit = _cache_limit
        self.cache_filling = False

    def cancelled( self, gen ):
        with self.lock:
            return gen != self.generation or self.stopping

    def publish( self, gen, figures = None, progress = None, counts = None,
                 error = None, constants = None, correlations = None ):
        with self.lock:
            if gen != self.generation:
                return
            if figures is not None:
                self.figures = figures
                #(the fields with one value, and the correlation coefficients,
                #are only known from the computation of the second pass, and
                #shown with the figures, which they are of):
                self.constants = constants or {}
                self.correlations = correlations
            if progress is not None:
                self.progress = progress
            if figures is None and counts is None and error is None and constants is None:
                self.status_updates += 1#(only the progress)
                return
            if counts is not None:
                self.counts = counts
            self.error = error
            self.updates += 1

class _Reading:
    """The reading of the file of the viewer in a background thread (the part
    of _viewer.Viewer which starts and polls it, see _read_file)"""

    def start( self ):
        """Start reading the file in the background"""
        if self._thread is None:
            from ._viewer_threads import start
            self._thread = start(_read_file,self.filename,self._rs)
        self._restart()

    def stop( self ):
        rs = self._rs
        with rs.lock:
            rs.stopping = True
            rs.wake.notify_all()
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
        """The error of the reading (e.g. "no particles kept"), or None"""
        with self._rs.lock:
            return self._rs.error

    @property
    def reading( self ):
        """Whether the file is being read (for the current settings)"""
        rs = self._rs
        with rs.lock:
            return not ( rs.job is None and rs.seen_gen == rs.generation
                         and rs.found_pending is None )

    def wait( self ):
        """Wait until the current reading is done (for tests and scripts)"""
        import time
        while self.reading:
            self._apply_found()
            time.sleep(0.01)

    def poll( self ):
        """Whether the figures or status changed since the last call (and
        plot_changed whether the figures did, not only the progress). The
        front ends call it regularly, in their own thread."""
        self._apply_found()
        rs = self._rs
        with rs.lock:
            self.plot_changed = rs.updates != self._seen
            changed = self.plot_changed or rs.status_updates != self._status_seen
            self._seen, self._status_seen = rs.updates, rs.status_updates
        return changed

    def _restart( self ):
        settings = self._reading_settings()
        rng = self._range(settings.skip,settings.limit)
        rs = self._rs
        with rs.lock:
            rs.generation += 1
            rs.job = ( rs.generation, settings, rng )
            rs.wake.notify_all()

    #The particles kept in memory (see _Cache):

    @property
    def cache_limit( self ):
        """The memory (in bytes) for the particles kept in memory, or None
        for no cache"""
        return self._rs.cache_limit

    def set_cache_limit( self, nbytes ):
        """Set the memory (in bytes) for the particles kept in memory, or None
        for no cache. The plots use the particles of the range which fit (and
        the others are not read), and without a cache all particles of the
        range, which are read from the file again for each change."""
        self._rs.cache_limit = None if nbytes is None else max( 0.0, float(nbytes) )
        self._restart()

    def cache_info( self ):
        """The particles of the range in memory, as a dict: the number of
        particles in the range (nrange), the bytes per particle in memory
        (size), the bytes they need (needed), the cache limit (limit, None for
        no cache), whether all particles of the range are used (fits: they
        fit, or there is no cache), the number of particles of the range
        used by the plots (nused), the bytes kept in memory (cached), and
        whether the particles are still being put there (filling)"""
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
        with self._rs.lock:
            filling = self._rs.cache_filling
        return { 'nrange' : n, 'size' : size, 'needed' : n * size, 'limit' : limit,
                 'fits' : fits, 'nused' : nused,
                 'cached' : 0 if limit is None else nused * size,
                 'filling' : filling and self.reading }

    def _apply_found( self ):
        """Apply what the last reading found (see _on_found), if not done yet"""
        with self._rs.lock:
            found, self._rs.found_pending = self._rs.found_pending, None
        if found is not None:
            self._on_found(found)

    def _on_found( self, found ):
        """Called (by poll or wait, see _apply_found) with what a reading found
        (see _Computation.found)"""

def _read_file( filename, rs ):
    """The reading thread (see _viewer_threads): reads the file for each job of
    the state rs (see _ReadingState), until it is stopped"""
    from ._reader import MCPLFile
    with MCPLFile(filename) as f:
        #(the particles are kept in memory up to the cache limit, so those are
        #only read, and decompressed, once):
        f = _Cache(f,rs)
        while True:
            with rs.lock:
                while rs.job is None and not rs.stopping:
                    rs.wake.wait()
                if rs.stopping:
                    return
                gen, settings, rng = rs.job
                rs.job = None
            try:
                _read(f,rs,gen,settings,rng)
            except _Cancelled:
                pass
            except MCPLError as e:
                rs.publish(gen,error=str(e))
            except ( ValueError, TypeError, ArithmeticError, IndexError,
                     KeyError, OSError ) as e:#(shown, so the viewer stays usable)
                rs.publish(gen,error=f'{type(e).__name__}: {e}')
            with rs.lock:
                if rs.job is None:
                    rs.seen_gen = gen

def _read( f, rs, gen, settings, rng ):
    """Read the particles of the range rng (first, end) of the file f twice
    (for the ranges, and to fill the histograms), publishing figures at the
    update points (see _ReadingState.publish). The figures of the plots of the
    last reading which was done are kept if the particles are the same (the
    same skip, limit, and edit), so only new plots are filled."""
    key = ( settings.skip, settings.limit, settings.expression )
    done = rs.done if rs.done is not None and rs.done[0] == key else None
    known = {}
    if done is not None:
        known = { k : fig for k, fig in done[1].items() if k[5:] in settings.plots }
        settings = settings.copy()
        settings.plots = [ p for p in settings.plots if f'plot:{p}' not in known ]
        if not settings.plots:
            rs.publish(gen,figures=known,constants=done[2]['constants'],
                       correlations=done[2]['correlations'],progress='',counts=done[3])
            with rs.lock:
                if gen == rs.generation:
                    rs.found_pending = done[2]#(see the end of a reading)
            return
    import time
    def figures( figs ):
        return None if figs is None else { **known, **figs }
    frac = [0.0]
    def progress( x ):
        frac[0] = min( 1.0, x )
    #(the blocks of the range, edited, with the counts of all
    #particles in the range, their weights, and those left after each
    #statement of the edit, see _range_blocks):
    range_counts = [ 0, 0.0, [] ]
    def blocks():
        yield from _range_blocks(f,f.blocks(*rng),settings,progress,range_counts,
                                 lambda : rs.cancelled(gen))
    #Pass 1: ranges, and provisional figures from the first particles:
    comp = _Computation(settings)
    kept, nkept, npreview, n, w = [], 0, 0, 0, 0.0
    points = _update_points()
    nextpoint = next(points)
    shown = time.monotonic()
    #(with the correlation coefficients of the same particles, if known):
    rs.publish(gen,figures=figures({}),correlations=done[2]['correlations'] if done else None,
               progress='reading: finding ranges',counts=None)
    for b in blocks():
        comp.add1(b)
        n += len(b)
        w += float(b.weight.sum())
        if nkept < _preview_max:
            kept.append(b)
            nkept += len(b)
        if n >= nextpoint:
            while n >= nextpoint:
                nextpoint = next(points)
            #(made again only when more blocks were kept):
            figs, corr = _preview(settings,kept) if nkept > npreview else ( None, None )
            npreview = nkept
            rs.publish(gen,figures=figures(figs),correlations=corr,
                       progress=f'reading: finding ranges ({100*frac[0]:.0f}%)')
            shown = time.monotonic()
        elif time.monotonic() - shown > 0.25:
            rs.publish(gen,progress=f'reading: finding ranges ({100*frac[0]:.0f}%)')
            shown = time.monotonic()
    counts = ( n, range_counts[0], w, range_counts[1], tuple(range_counts[2]) )
    if n == 0:
        rs.publish(gen,figures={},progress='',counts=counts,
                   error='no particles kept' if settings.edit else 'no particles')
        return
    del kept
    comp.start2()
    points = _update_points()
    nextpoint = next(points)
    #(the progress of the second pass is that of the particles, which can come
    #from the cache, not the file):
    m = 0
    stage = lambda : f'reading: filling the plots ({100*m/n:.0f}% of particles)'
    rs.publish(gen,progress=stage(),counts=counts)
    for b in blocks():
        comp.add2(b)
        m += len(b)
        if m >= nextpoint and m < n:
            while m >= nextpoint:
                nextpoint = next(points)
            rs.publish(gen,figures=figures(comp.figures()),constants=comp.constants(),
                       correlations=comp.correlations(),progress=stage())
            shown = time.monotonic()
        elif time.monotonic() - shown > 0.25:
            rs.publish(gen,progress=stage())
            shown = time.monotonic()
    figs, found = figures(comp.figures()), comp.found()
    rs.publish(gen,figures=figs,constants=found['constants'],
               correlations=found['correlations'],progress='',counts=counts)
    with rs.lock:
        if gen == rs.generation:
            rs.done = ( key, figs, found, counts )
            #(applied by poll or wait, in the thread of the front end, so the
            #groups do not change while it shows them):
            rs.found_pending = found

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
    of the range read (see blocks) which fit in the cache limit (of the
    state rs, see _ReadingState), so only the particles after them are read
    from the file again"""
    def __init__( self, f, rs ):
        self._f, self._rs = f, rs
        #(the blocks kept, from the particle start to the end, and their bytes):
        self._blocks, self._start, self._end, self._nbytes = [], 0, 0, 0

    def __getattr__( self, name ):
        return getattr(self._f,name)

    def blocks( self, first, end ):
        """The blocks of the file with the particles from first to end"""
        f, limit = self._f, self._rs.cache_limit
        #(the blocks kept start at the block of the first particle):
        start = first - first % f.blocklength
        if start != self._start or limit is None:
            self._blocks, self._start, self._end, self._nbytes = [], start, start, 0
        while self._blocks and self._nbytes > limit:#(after lowering the limit)
            b = self._blocks.pop()
            self._end -= len(b)
            self._nbytes -= _block_nbytes(b)
        self._filling(False)
        for b in list(self._blocks):
            if b.file_offset >= end:
                return
            yield b
        if self._end >= end:
            return
        #(the blocks after those kept, which are kept while they fit):
        f.rewind()
        f.skip_forward(self._end)#(the next block then starts at the end)
        self._filling(limit is not None)
        try:
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
                elif limit is not None:
                    self._filling(False)#(full)
                yield b
        finally:
            self._filling(False)

    def _filling( self, filling ):
        with self._rs.lock:
            self._rs.cache_filling = filling

def _make_filler( text, settings = None ):
    """Histogram filler of a plot (a histogram string), of the particles
    edited with the settings (if given, for the title)"""
    from ._histfill import _filler_for
    from ._histstring import _parse_hist
    o = _parse_hist(text)
    if o['print']:
        raise MCPLError('The histogram option print can not be used in the viewer')
    h = _filler_for(o)
    if settings is not None:
        h._selection = settings.expression
    return h

#Fields for which it is noted when all particles have the same value:
_const_fields = ( 'pdgcode', 'userflags', 'ekin', 'x', 'y', 'z', 'ux', 'uy', 'uz',
                  'time', 'weight', 'polx', 'poly', 'polz' )

class _Computation:
    """The plots for the views, and the fields where all particles have the
    same value, from the blocks given to add1 (first pass) and add2 (second
    pass, after start2). A plot which fails (e.g. one without values) shows
    the problem, without stopping the others."""
    def __init__( self, settings ):
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
                                               for v in g[2].get('variables',()) ))

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

    def start2( self ):
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
        from ._expr_vocab import _expr_field_dims, _expr_unit_hints
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
                 'correlations' : self.correlations() }

    def correlations( self ):
        """The correlation coefficients of the particles so far (see
        Moments.coefficients)"""
        return self._moments.coefficients()

    def figures( self ):
        """The figures of the plots (with the edit expression as titles, as for
        mcpltool -H, see _histfill._selection_title)"""
        from ._figures import Figure, Panel, Text
        from ._histfigures import figure
        from ._histfill import _selection_title
        s = self._settings
        title = _selection_title(s.expression)
        res = {}
        for p, h in self._plots:
            hist = self._guard(p,h.result) if h is not None else None
            if hist is None:
                res[f'plot:{p}'] = Figure( title = title, panels = [ Panel( xlabel = p,
                                           items = [ Text(self._errors[p]) ] ) ] )
                continue
            res[f'plot:{p}'] = figure(hist)
        return res

def _range_blocks( f, blocks, settings, progress, counts, cancelled ):
    """Blocks of the range of particles of the file f (see settings), edited,
    from the blocks of the file given. progress is called with the
    fraction of the range read, counts gets the number of particles in the
    range, the sum of their weights, and the numbers left after each statement
    of the edit, and cancelled tells when to stop (with _Cancelled)."""
    from ._reader import _blocks_in_range, _particle_range
    skip, end = _particle_range(f.nparticles,settings.skip,settings.limit or None)
    edit = settings.edit
    counts[:] = [ end - skip, 0.0, [ 0 ] * ( edit and len(edit._tree.statements) or 0 ) ]
    #(the progress is counted, as blocks from the cache do not know their
    #position in the file, see _Cache):
    nread = 0
    for b in _blocks_in_range(blocks,skip,end):
        if cancelled():
            raise _Cancelled()
        counts[1] += float(b.weight.sum())
        nread += len(b)
        progress( nread / max( 1, end - skip ) )
        if edit is not None:
            b = edit._edited(b,counts[2])
        if len(b):
            yield b

def _preview( settings, blocks ):
    """Figures from the blocks kept in memory (both passes over them), and the
    correlation coefficients of their particles"""
    comp = _Computation(settings)
    for b in blocks:
        comp.add1(b)
    comp.start2()
    for b in blocks:
        comp.add2(b)
    return comp.figures(), comp.correlations()
