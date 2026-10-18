
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

"""The core of the viewer of mcpltool -w (and mcpl.view), shared by all its
front ends: the settings (Skip, Limit, Pick, Edit and the added plots) with
checking, history and completion, the views (the overview, a plot for each
field and the added plots) and their figures, which are computed by reading
the file in a background thread, the equivalent commands, and writing the
picked and edited particles to a new file."""

__all__ = ['view']

import copy
import pathlib
import re
import threading

from ._common import MCPLError

#Numbers of particles read after which the figures are updated (and then every
#further _update_step particles):
_update_counts = ( 20000, 200000, 1000000, 2000000 )
_update_step = 2000000
#Particles kept in memory during the first pass (to show provisional figures
#before the ranges of the plots are known):
_preview_max = 200000

_fields = ( 'skip', 'limit', 'pick', 'edit', 'plot' )

def _update_points():
    """Particle counts at which figures are updated: 20k, 200k, 1M, 2M, 4M, ..."""
    yield from _update_counts
    n = _update_counts[-1]
    while True:
        n += _update_step
        yield n

class _Settings:
    """What is shown: a range of particles in the file, picked and edited, and
    the added plots (histogram strings)"""
    def __init__( self, skip = 0, limit = None, pick = None, edit = None, plots = () ):
        self.skip, self.limit = skip, limit
        self.pick, self.edit = pick, edit#(ParticleFilter, ParticleEdit or None)
        self.plots = list(plots)
    def copy( self ):
        return _Settings(self.skip,self.limit,self.pick,self.edit,self.plots)

class Viewer:
    """State of the viewer for a file. The front ends show the views (see
    views and figure()), the status (status_lines()) and the fields
    (field_text(), check(), set(), complete(), hint(), history()), and call
    poll() regularly to find out if the figures were updated by the reading
    in the background (started by start())."""

    def __init__( self, filename, skip = 0, limit = None, pick = None, edit = None,
                  plots = (), view = None, dry_run = False, progname = 'mcpltool' ):
        from ._reader import MCPLFile
        self.filename = str(filename)
        with MCPLFile(self.filename) as f:
            self._ntotal = f.nparticles
        self._dry_run = dry_run
        self._progname = progname
        self._texts = { 'skip' : '', 'limit' : '', 'pick' : '', 'edit' : '',
                        'plot' : '' }
        self._history = { f : [] for f in _fields }
        self._s = _Settings()
        for field, value in ( ('skip',skip), ('limit',limit), ('pick',pick),
                              ('edit',edit) ):
            if value not in ( None, '', 0 ):
                ok, msg = self.set(field, str(value), restart = False)
                if not ok:
                    raise MCPLError(msg)
        for p in plots:
            ok, msg = self.set('plot', p, restart = False)
            if not ok:
                raise MCPLError(msg)
        self._lock = threading.Lock()
        self._figures = {}#view key -> Figure
        self._constants = {}#field -> text of the value all particles have
        self._progress = ''
        self._counts = None
        self._error = None
        self._generation = 0#(incremented for every new reading)
        self._seen_gen = 0#(the last reading which is done)
        self._seen = -1
        self._updates = 0
        self._job = None
        self._wake = threading.Condition(self._lock)
        self._thread = None
        self._stopping = False
        #(the front ends which can show several plots at once set
        #multi_overview, see views):
        self.multi_overview = False
        self._current = None#(key of the view shown, None for the first)
        if view is not None:
            keys = [ k for k, _ in self.views ] + [ 'overview', 'overview:multi' ]
            if view not in keys:
                raise MCPLError(f'Unknown view "{view}" (the views are: '
                                + ', '.join(keys[:-1]) + ')')
            self._current = view

    #Fields:

    def field_text( self, field ):
        """Current text of a field (as last set)"""
        return self._texts[field] if field != 'plot' else ''

    def check( self, field, text ):
        """Whether the text is valid for the field: (ok, message), where the
        message describes the problem (empty if ok)"""
        try:
            self._parse(field,text)
        except MCPLError as e:
            return False, str(e)
        return True, ''

    def _parse( self, field, text ):
        text = text.strip()
        if field in ('skip','limit'):
            if not text or ( field == 'limit' and text == 'all' ):
                return 0 if field == 'skip' else None
            v = _parse_count(text) if field == 'limit' else ( int(text) if text.isdigit() else None )
            if v is None or v < 0:
                raise MCPLError(f'{field.capitalize()} must be a number of particles'
                                + ( ' (or all)' if field == 'limit' else '' ))
            return None if field == 'limit' and v == 0 else v
        if field == 'pick':
            if not text:
                return None
            from ._expressions import ParticleFilter
            return ParticleFilter(text)
        if field == 'edit':
            if not text:
                return None
            from ._expressions import ParticleEdit
            return ParticleEdit(text)
        if field == 'plot':
            if not text:
                raise MCPLError('Give an expression to plot, e.g. ekin/MeV')
            _make_filler(text,None)#(checks the expressions and options)
            return text
        raise MCPLError(f'Unknown field "{field}"')

    def set( self, field, text, restart = True ):
        """Apply the text of a field (restarting the reading, unless it was an
        added plot): (ok, message)"""
        try:
            value = self._parse(field,text)
        except MCPLError as e:
            return False, str(e)
        text = text.strip()
        h = self._history[field]
        if text and ( not h or h[-1] != text ):
            h.append(text)
        if field == 'plot':
            #(the same plot written differently is not added again):
            same = self._same_plot(text)
            if same is None:
                self._s.plots.append(text)
            self._current = f'plot:{same or text}'
        else:
            #(the reading is not restarted for the same value, e.g. an
            #expression written differently):
            old = self._texts[field]
            self._texts[field] = text
            if field in ( 'pick', 'edit' ):
                from ._expressions import _expr_canonical
                same = ( ( _expr_canonical(text,field == 'edit')
                           == _expr_canonical(old,field == 'edit') )
                         if text and old else text == old )
            else:
                same = getattr(self._s,field) == value
            if same:
                return True, ''
            setattr(self._s,field,value)
        if restart:
            self._restart()
        return True, ''

    def change_plot( self, old, text ):
        """Replace the added plot old (its histogram string) by the text, in its
        place among the views, or remove it if the text is empty (restarting
        the reading): (ok, message)"""
        text = text.strip()
        plots = self._s.plots
        if old not in plots:
            return False, f'No added plot "{old}"'
        i = plots.index(old)
        if not text:
            #(showing the view before it):
            keys = [ k for k, _ in self.views ]
            self._current = keys[ keys.index(f'plot:{old}') - 1 ]
            plots.pop(i)
            self._restart()
            return True, ''
        try:
            self._parse('plot',text)
        except MCPLError as e:
            return False, str(e)
        if self._same_plot(text,[old]) == old:
            self._current = f'plot:{old}'#(unchanged)
            return True, ''
        same = self._same_plot(text,[ p for p in plots if p != old ])
        h = self._history['plot']
        if not h or h[-1] != text:
            h.append(text)
        if same is not None:
            plots.pop(i)#(the plot is already there)
        else:
            plots[i] = text
        self._current = f'plot:{same or text}'
        self._restart()
        return True, ''

    def _same_plot( self, text, plots = None ):
        """The added plot (of plots, default all) giving the same histogram as
        the text, or None"""
        from ._histogram import _hist_key
        key = _hist_key(text)
        return next( ( p for p in ( self._s.plots if plots is None else plots )
                       if _hist_key(p) == key ), None )

    def history( self, field ):
        """Earlier texts of the field (oldest first)"""
        return list(self._history[field])

    def complete( self, field, text, cursor = None ):
        """Completions of the name before the cursor: (start, candidates),
        where start is the position where the name starts, and candidates a
        list of (text to insert, short description)."""
        from ._exprhelp import _hints
        cursor = len(text) if cursor is None else cursor
        m = re.search(r'[A-Za-z_][A-Za-z0-9_]*$', text[:cursor])
        start = m.start() if m else cursor
        prefix = m.group(0) if m else ''
        if field not in ( 'pick', 'edit', 'plot' ):
            return start, []
        options = field == 'plot' and ';' in text[:start]
        #(names of histogram options only after the first ";" of plots, and
        #the statements only in edits):
        groups = ( {'histoptions'} if options else
                   {'fields','constants','particles','units','functions'}
                   | ( {'statements'} if field == 'edit' else set() ) )
        res = []
        for group, name, short, _ in _hints:
            if group not in groups:
                continue
            base = re.match(r'[A-Za-z_][A-Za-z0-9_]*', name).group(0)
            if not base.startswith(prefix):
                continue
            insert = base + ( '(' if '(' in name else ( '=' if '=' in name else '' ) )
            if insert not in [ r[0] for r in res ]:
                res.append( ( insert, short ) )
        return start, res

    def hint( self, field, text, cursor = None ):
        """Short description of the name at the cursor, as "name  description",
        or None"""
        from ._exprhelp import _short_hint
        cursor = len(text) if cursor is None else cursor
        m = re.search(r'[A-Za-z_][A-Za-z0-9_]*$', text[:cursor])
        if not m:
            return None
        rest = re.match(r'[A-Za-z0-9_]*', text[cursor:]).group(0)
        name = m.group(0) + rest
        short = _short_hint(name)
        return f'{name}  {short}' if short else None

    #Views:

    @property
    def views( self ):
        """The views, as a list of (key, label): the overview with all its plots
        (only with multi_overview), each plot of the overview, a plot of each
        field, and the added plots"""
        res = [ ( 'overview:multi', 'overview' ) ] if self.multi_overview else []
        res += [ ( f'overview:{k}', f'overview:{k}' ) for k in _overview_keys ]
        with self._lock:
            constants = self._constants
        #(fields where all particles have the same value are marked):
        res += [ ( f, f'{f} (all {constants[f]})' if f in constants else f )
                 for f in _view_fields(self.filename) ]
        res += [ ( f'plot:{p}', p ) for p in self._s.plots ]
        return res

    @property
    def current( self ):
        """Index of the view shown"""
        keys = [ k for k, _ in self.views ]
        key = self._current
        if key in ( 'overview', 'overview:multi' ) and not self.multi_overview:
            key = keys[0]
        if key == 'overview':
            key = 'overview:multi'
        return keys.index(key) if key in keys else 0

    def select( self, index ):
        views = self.views
        self._current = views[ max( 0, min( len(views) - 1, int(index) ) ) ][0]

    def select_key( self, key ):
        """Show the view with the key"""
        if key in [ k for k, _ in self.views ]:
            self._current = key

    def figure( self, index = None ):
        """Figure of a view (default the current one), or None if not yet
        available"""
        key = self.views[self.current if index is None else index][0]
        with self._lock:
            return self._figures.get(key)

    def status_lines( self, weights = '\u03a3w' ):
        """The two status lines: the file, the numbers of particles and the sum
        of their weights (named weights), and the progress of the reading (or
        an error)"""
        with self._lock:
            counts, progress, error = self._counts, self._progress, self._error
        name = pathlib.Path(self.filename).name
        if counts is None:
            first = f'{name}: {self._ntotal} particles'
        else:
            n, ntot, w, wtot = counts
            pct = f'{100.0*n/ntot:.1f}%' if ntot else '-'
            wpct = f'{100.0*w/wtot:.1f}%' if wtot else '-'
            first = f'{name}: {n}/{ntot} particles ({pct}), {weights} = {w:g} ({wpct})'
        return first, ( f'error: {error}' if error else progress )

    #Commands:

    def _options( self ):
        s = self._s
        from ._extract import _shell_arg
        opts = []
        if s.skip:
            opts.append(f'-s{s.skip}')
        if s.limit:
            opts.append(f'-l{s.limit}')
        for opt, e in ( ('-p',s.pick), ('-E',s.edit) ):
            if e is not None:
                opts += [ opt, _shell_arg(e.expression) ]
        return opts

    def commands( self ):
        """Commands doing the same as the viewer: 'view' (opening the viewer in
        the same state) and 'extract' (writing the picked and edited
        particles to a new file)"""
        from ._extract import _shell_arg
        prog, fn = self._progname, _shell_arg(self.filename) if ' ' in self.filename else self.filename
        opts = self._options()
        key = self.views[self.current][0]
        hists = []
        for p in self._s.plots:
            hists += [ '-H', _shell_arg(p) ]
        first = self.views[0][0]
        view = '-w' if key == first or key.startswith('plot:') else f'--view={key}'
        return { 'view' : ' '.join([ prog, view ] + opts + hists + [ fn ]),
                 'extract' : ' '.join([ prog, '-e' ] + opts + [ fn, self.suggested_filename() ]) }

    #Writing:

    def suggested_filename( self ):
        """<input>_selected.mcpl.gz, or <input>_selected2.mcpl.gz, ... if that
        (or the same without .gz) exists"""
        p = pathlib.Path(self.filename)
        stem = p.name
        for ext in ( '.gz', '.mcpl' ):
            stem = stem.removesuffix(ext)
        i = 1
        while True:
            name = f'{stem}_selected{i if i > 1 else ""}'
            cands = [ p.with_name(name + '.mcpl.gz'), p.with_name(name + '.mcpl') ]
            if not any( c.exists() for c in cands ):
                return str(cands[0]) if p.parent != pathlib.Path('.') else cands[0].name
            i += 1

    def try_write( self, filename = None ):
        """As write, but returning (ok, message): the last line of the output,
        or the problem"""
        try:
            out = self.write(filename)
        except MCPLError as e:
            return False, str(e)
        lines = ( out or '' ).splitlines()
        return True, lines[-1] if lines else ''

    def write( self, filename = None ):
        """Write the picked and edited particles to a new file (never
        overwriting existing files, and without writing in a dry run).
        Returns the messages (as for mcpltool -e)."""
        import contextlib
        import io

        from ._extract import _mcpltool_extract
        filename = filename or self.suggested_filename()
        if pathlib.Path(filename).exists() or pathlib.Path(filename + '.gz').exists():
            raise MCPLError(f'The file {filename} already exists')
        s = self._s
        out = io.StringIO()
        def bad( msg ):
            raise MCPLError(msg)
        with contextlib.redirect_stdout(out):
            _mcpltool_extract([self.filename,filename],s.limit,s.skip,s.pick,
                              s.edit,False,False,self._dry_run,bad)
        return out.getvalue().strip()

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

    def wait( self ):
        """Wait until the current reading is done (for tests and scripts)"""
        import time
        while True:
            with self._lock:
                if self._job is None and self._seen_gen == self._generation:
                    return
            time.sleep(0.01)

    def poll( self ):
        """Whether the figures or status changed since the last call"""
        with self._lock:
            changed = self._updates != self._seen
            self._seen = self._updates
        return changed

    def _restart( self ):
        if not hasattr(self,'_lock'):
            return
        with self._lock:
            self._generation += 1
            self._job = ( self._generation, self._s.copy() )
            self._wake.notify_all()

    def _worker( self ):
        from ._reader import MCPLFile
        with MCPLFile(self.filename) as f:
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
        counts of all particles in the range (and their weights). progress is
        called with the fraction of the range read."""
        from ._blocks import _EditedParticleBlock
        n = f.nparticles
        skip = min( settings.skip or 0, n )
        end = n if not settings.limit else min( n, skip + settings.limit )
        self._range_counts = [ end - skip, 0.0 ]
        for b in f.particle_blocks:
            if self._cancelled(gen):
                raise _Cancelled()
            off = b.file_offset
            if off + len(b) <= skip:
                continue
            if off >= end:
                break
            b = b[max(0,skip-off):min(len(b),end-off)]
            self._range_counts[1] += float(b.weight.sum())
            progress( ( max(off,skip) + len(b) - skip ) / max( 1, end - skip ) )
            if settings.pick is not None:
                b = b[settings.pick(b)]
            if not len(b):
                continue#(no particles picked in this block)
            if settings.edit is not None:
                b = _EditedParticleBlock(b,settings.edit(b))
            yield b

    def _read( self, f, gen, settings ):
        """Read the file twice (for the ranges, and to fill the histograms),
        publishing figures at the update points"""
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
        self._publish(gen,figures={},progress='reading: finding ranges',counts=None)
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
                self._publish(gen,figures=figs,
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
                self._publish(gen,figures=comp.figures(),constants=comp.constants(),
                              progress=f'reading: {100*frac[0]:.0f}% of particles')
        self._publish(gen,figures=comp.figures(),constants=comp.constants(),progress='',
                      counts=counts)

class _Cancelled(Exception):
    pass

from ._viewer_ui import overview_keys as _overview_keys


def _view_fields( filename ):
    """Names of the fields with a view (those of the per-field plots of
    stats_figures, in the same order)"""
    from ._stats import _possible_freq_stats, _possible_std_stats
    return list(_possible_freq_stats) + list(_possible_std_stats)

def _make_filler( text, pick ):
    """Histogram filler of an added plot (a histogram string)"""
    from ._histogram import _filler_for, _parse_hist
    o = _parse_hist(text)
    if o['print']:
        raise MCPLError('The histogram option print can not be used in the viewer')
    return _filler_for(o,pick = pick)

class _Computation:
    """The statistics and added plots for the views, from the blocks given to
    add1 (first pass) and add2 (second pass, after start2)"""
    def __init__( self, f, settings ):
        from ._stats import _StatsAccumulator
        self._settings = settings
        self._f = _HeaderView(f,settings)
        self._stats = _StatsAccumulator(self._f)
        self._plots = [ ( p, _make_filler(p,None) ) for p in settings.plots ]
    def add1( self, b ):
        if self._stats.needs_pass1:
            self._stats.add1(b)
        for _, h in self._plots:
            if h.needs_range:
                h.add_range(None,b)
    def start2( self, n ):
        self._stats.start2(n)
        for _, h in self._plots:
            if h.needs_range:
                h.start_fill()
    def add2( self, b ):
        self._stats.add2(b)
        for _, h in self._plots:
            h.add(None,b)
    def constants( self ):
        """The fields where all particles have the same value, with the value
        (as text, with its unit)"""
        res = {}
        for field, st in self._stats.result().items():
            if not isinstance(st,dict):
                continue
            if 'unique_values' in st:
                if len(st['unique_values']) == 1:
                    res[field] = f'{int(st["unique_values"][0])}'
            elif st.get('min') is not None and st.get('min') == st.get('max'):
                unit = st.get('unit')
                res[field] = f'{st["min"]:g}' + ( f' {unit}' if unit else '' )
        return res

    def figures( self ):
        from ._statsplot import stats_figures
        stats = copy.deepcopy(self._stats.result())
        figs = stats_figures(stats)
        res = {}
        keys = ( ['overview:multi'] if 'overview' in stats else [] ) + [
            k for k in _view_fields(None) if k in stats ]
        #(all with the titles of mcpltool -H, the pick and edit expressions,
        #since the file and the numbers are in the status lines):
        s = self._settings
        title = '\n'.join( f'{what}: {e.expression}' for what, e in
                           (('pick',s.pick),('edit',s.edit)) if e is not None )
        for k, fig in zip(keys,figs):
            fig.title = title or None
            res[k] = fig
        #(and each plot of the overview on its own):
        from .plotting import Figure
        ov = res.get('overview:multi')
        for k, panel in zip(_overview_keys,ov.panels if ov else []):
            res[f'overview:{k}'] = Figure( title = ov.title, panels = [ panel ] )
        for p, h in self._plots:
            hist = copy.deepcopy(h.result())
            hist.title = title or None
            res[f'plot:{p}'] = hist.figure()
        return res

class _HeaderView:
    """The header information of the file, with the pick and edit of the
    settings (for the titles of the overview, as for mcpltool -S)"""
    _viewer = True
    def __init__( self, f, settings ):
        self._f = f
        self.pick = settings.pick.expression if settings.pick else ''
        self.edit = settings.edit.expression if settings.edit else None
    def __getattr__( self, name ):
        return getattr(self._f,name)

def _preview( f, settings, blocks ):
    """Figures from the blocks kept in memory (both passes over them)"""
    comp = _Computation(f,settings)
    for b in blocks:
        comp.add1(b)
    comp.start2(sum( len(b) for b in blocks ))
    for b in blocks:
        comp.add2(b)
    return comp.figures()

def _parse_count( text ):
    """The integer of a text like 1000 or 1e6 (or None if it is not one)"""
    try:
        return int(text)
    except ValueError:
        pass
    try:
        f = float(text)
        i = int(f)
    except ( ValueError, OverflowError ):
        return None
    return i if i == f else None

def view( filename, pick = None, edit = None, skip = 0, limit = None,
          plots = (), view = None, backend = None, terminal = False ):
    """Show the particles of a file in the viewer: an overview, a plot of each
    field, and the plots (histogram strings, as for mcpltool -H, e.g.
    "hypot(x,y)/cm;logy=1"), for the particles in a range of the file (after
    skipping skip particles, at most limit particles), picked with pick and
    then edited with edit (expressions, or ParticleFilter and ParticleEdit
    objects), which can all be changed in the viewer. view is the view shown
    first (e.g. 'ekin'). In Jupyter, the viewer is a panel of ipywidgets
    (which is returned), and otherwise it is shown in a window with
    matplotlib, or in the terminal (always with terminal=True, or with the
    given plotting backend), until it is closed."""
    from ._plotbackend import _create, _viewer_backend
    def text( e ):
        return e if e is None or isinstance(e,str) else e.expression
    v = Viewer(filename,skip=skip,limit=limit,pick=text(pick),edit=text(edit),
               plots=plots,view=view)
    if backend is None and not terminal and _in_jupyter():
        from ._viewer_jupyter import run_viewer
        return run_viewer(v)
    _create(_viewer_backend(backend,terminal)).run_viewer(v)
    return None

def _in_jupyter():
    import sys
    if 'ipykernel' not in sys.modules:
        return False
    try:
        from IPython import get_ipython
    except ImportError:
        return False
    shell = get_ipython()
    return shell is not None and shell.__class__.__name__ == 'ZMQInteractiveShell'
