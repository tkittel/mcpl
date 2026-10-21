
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
front ends: the settings (Skip, Limit, Pick, Edit and the plots) with
checking, history and completion, the views (the overview with the first
plots, and each plot) and their figures, which are computed by reading the
file in a background thread, the state of the viewer (see state()), the
equivalent commands, and writing the picked and edited particles to a new
file."""

__all__ = ['view']

import copy
import pathlib
import re
import threading

from ._common import MCPLError
from ._stdviews import _collections, _default_collection, _item, _plot_item

#Numbers of particles read after which the figures are updated (and then every
#further _update_step particles):
_update_counts = ( 20000, 200000, 1000000, 2000000 )
_update_step = 2000000
#Particles kept in memory during the first pass (to show provisional figures
#before the ranges of the plots are known):
_preview_max = 200000

_fields = ( 'skip', 'limit', 'pick', 'edit', 'collection', 'plot' )

#(the plots of the viewer start as those of a collection, see _stdviews, of
#which the first _noverview are shown together in the overview):
_noverview = 6

def _update_points():
    """Particle counts at which figures are updated: 20k, 200k, 1M, 2M, 4M, ..."""
    yield from _update_counts
    n = _update_counts[-1]
    while True:
        n += _update_step
        yield n

class _Settings:
    """What is shown: a range of particles in the file, picked and edited, and
    the plots (histogram strings)"""
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
        self._origins = {}
        self._meta = {}#histogram string -> (title, group) of the plots with them
        self._use_collection(_default_collection)
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
        self._overview = None#(the overview figure, with what it was made from)
        #The view argument is the name of a collection of plots, a view, or a
        #state (see state()), which is applied before the other arguments (so
        #these can change it):
        if isinstance(view,str) and view in _collections:
            view = { 'collection' : view }
        state = _as_state(view)
        if state is not None:
            self._apply_state(state)
            view = state.get('view')
        for field, value in ( ('skip',skip), ('limit',limit), ('pick',pick),
                              ('edit',edit) ):
            if value not in ( None, '', 0 ):
                self._set_or_raise(field,str(value))
        for p in plots:
            self._set_or_raise('plot',p)
        self._current = self._view_key(view) if view else None

    def _use_collection( self, name ):
        """Start from the plots of the collection (keeping the plots which were
        added, but not the changes of the plots of the previous collection)"""
        added = [ p for p in self._s.plots if p not in self._origins ]
        items = [ _plot_item(i) for i in _collections[name][1] ]
        self._collection = name
        self._base = [ p for p, _, _ in items ]
        self._base_meta = { p : ( t, g ) for p, t, g in items if ( t, g ) != ( None, None ) }
        #(the plot of the collection each plot comes from, if any, for state()):
        self._origins = { p : p for p in self._base }
        added = [ p for p in added if p not in self._origins ]
        self._meta = { **{ p : self._meta[p] for p in added if p in self._meta },
                       **self._base_meta }
        self._s.plots = list(self._base) + added

    def _set_or_raise( self, field, text ):
        ok, msg = self.set(field, text, restart = False)
        if not ok:
            raise MCPLError(msg)

    def _view_key( self, view ):
        """The key of a view given as overview or as a plot (histogram string)"""
        if view in ( 'overview', 'overview:multi' ):
            return 'overview'
        try:
            same = self._same_plot(view)
        except MCPLError:
            same = None
        if same is None:
            raise MCPLError(f'Unknown view "{view}" (the views are the overview and'
                            ' the plots, given as overview or as the histogram'
                            ' string of a plot, e.g. ekin)')
        return f'plot:{same}'

    #Fields:

    def field_text( self, field ):
        """Current text of a field (as last set)"""
        if field == 'collection':
            return self._collection
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
        if field == 'collection':
            text = text or _default_collection
            if text not in _collections:
                raise MCPLError(f'Unknown collection of plots "{text}" (the collections'
                                f' are: {", ".join(_collections)})')
            return text
        raise MCPLError(f'Unknown field "{field}"')

    def set( self, field, text, restart = True ):
        """Apply the text of a field (restarting the reading): (ok, message). For
        the plot field, the plot is added at the end (unless it is there)."""
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
        elif field == 'collection':
            if value == self._collection:
                return True, ''
            self._use_collection(value)
            self._current = None
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
        """Replace the plot old (its histogram string) by the text, in its place
        among the views, or remove it if the text is empty (restarting the
        reading): (ok, message)"""
        text = text.strip()
        plots = self._s.plots
        if old not in plots:
            return False, f'No plot "{old}"'
        i = plots.index(old)
        if not text:
            #(showing the view before it, or the next for the first):
            keys = [ k for k, _ in self.views ]
            k = keys.index(f'plot:{old}')
            self._current = keys[ k - 1 if k > 0 else min( 1, len(keys) - 1 ) ]
            plots.pop(i)
            self._origins.pop(old,None)
            self._meta.pop(old,None)
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
        origin = self._origins.pop(old,None)
        meta = self._meta.pop(old,None)#(the title and group stay with the plot)
        if same is not None:
            plots.pop(i)#(the plot is already there)
            if meta is not None and same not in self._meta:
                self._meta[same] = meta
        else:
            plots[i] = text
            if origin is not None:
                self._origins[text] = origin
            if meta is not None:
                self._meta[text] = meta
        self._current = f'plot:{same or text}'
        self._restart()
        return True, ''

    def move( self, delta ):
        """Move the shown plot up (delta -1) or down (delta 1) in the list of
        plots, whose first ones are shown in the overview: whether it moved"""
        key = self.views[self.current][0]
        plots = self._s.plots
        if not key.startswith('plot:'):
            return False
        i = plots.index(key[5:])
        j = i + delta
        if not 0 <= j < len(plots):
            return False
        plots[i], plots[j] = plots[j], plots[i]
        with self._lock:
            self._updates += 1#(the figures are the same, in another order)
        return True

    def move_to( self, plot, index ):
        """Move the plot (its histogram string) to the index in the list of
        plots: whether it moved"""
        plots = self._s.plots
        if plot not in plots:
            return False
        i = plots.index(plot)
        index = max( 0, min( len(plots) - 1, index ) )
        if index == i:
            return False
        plots.insert(index,plots.pop(i))
        with self._lock:
            self._updates += 1#(the figures are the same, in another order)
        return True

    def set_title( self, plot, title ):
        """Set the title of the plot (its histogram string), shown instead of it
        in the viewers with windows, or remove it (an empty title): (ok,
        message)"""
        return self._set_meta(plot,0,title,'title')

    def set_group( self, plot, group ):
        """Set the group of the plot (where it is listed in the viewers with
        windows), or remove it (an empty group): (ok, message)"""
        return self._set_meta(plot,1,group,'group')

    def _set_meta( self, plot, i, text, what ):
        if plot not in self._s.plots:
            return False, f'No plot "{plot}"'
        text = text.strip()
        if text and not text.isprintable():
            return False, f'The {what} must be a text on one line'
        meta = list(self._meta.get(plot,( None, None )))
        meta[i] = text or None
        if meta == [ None, None ]:
            self._meta.pop(plot,None)
        else:
            self._meta[plot] = tuple(meta)
        with self._lock:
            self._updates += 1#(the figures are the same)
        return True, ''

    def plot_info( self, key ):
        """What the viewers with windows show of the view with the key (see
        views), as a dict: the title (if given), the name shown (the title, or
        else its expressions), the histogram string, the group (or None), the
        badges (short texts for its options) and the value all particles have
        (for a plot of a field where they all have the same value, else
        None)"""
        from ._histstring import _parse_hist
        if not key.startswith('plot:'):
            return { 'title' : None, 'name' : 'Overview', 'plot' : None, 'group' : None,
                     'badges' : [ f'{len(self.overview_keys())} plots' ], 'constant' : None }
        p = key[5:]
        title, group = self._meta.get(p,( None, None ))
        o = _parse_hist(p)
        with self._lock:
            figure = self._figures.get(key)
            constants = self._constants
        #(the log scales chosen with auto are known when the plot is made):
        panel = figure.panels[0] if figure is not None and figure.panels else None
        logx = panel.logx if panel is not None else o['logx'] is True
        logy = panel.logy if panel is not None else o['logy'] is True
        badges = []
        if len(o['exprs']) == 2:
            badges.append('2D')
        if o['bar']:
            #(the bars are horizontal, with their log scale on x):
            badges.append('bars')
            if logx:
                badges.append('log')
        elif logx or logy:
            badges.append( 'log' if logx and logy else 'log x' if logx else 'log y' )
        if o['lethargy']:
            badges.append('lethargy')
        if o['split']:
            badges.append( 'by particle' if o['split'] == 'pdgcode' else f'by {o["split"]}' )
        if o['unweighted']:
            badges.append('counts')
        if o['range'] or o['xrange'] or o['yrange']:
            badges.append('range')
        field = _plot_field(p)
        return { 'title' : title, 'name' : title or ' : '.join(o['exprs']), 'plot' : p,
                 'group' : group, 'badges' : badges,
                 'constant' : constants.get(field) if field else None }

    def _same_plot( self, text, plots = None ):
        """The plot (of plots, default all) giving the same histogram as the
        text, or None"""
        from ._histstring import _hist_key
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
        if field == 'collection':
            return 0, [ ( name, descr ) for name, ( descr, _ ) in _collections.items()
                        if name.startswith(text[:cursor].strip()) ]
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
        if field == 'collection':
            name = text.strip()
            return f'{name}  {_collections[name][0]}' if name in _collections else None
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
        """The views, as a list of (key, label): the overview with its plots
        (only with multi_overview, see overview_keys), and each plot (with its
        histogram string as label)"""
        res = [ ( 'overview:multi', 'overview' ) ] if self.multi_overview else []
        with self._lock:
            constants = self._constants
        #(plots of a field where all particles have the same value are marked):
        for p in self._s.plots:
            field = _plot_field(p)
            res.append( ( f'plot:{p}', f'{p} (all {constants[field]})'
                          if field in constants else p ) )
        return res

    def overview_keys( self ):
        """The keys of the views of the plots shown in the overview (in the
        order of its panels)"""
        return [ f'plot:{p}' for p in self._s.plots[:_noverview] ]

    @property
    def current( self ):
        """Index of the view shown"""
        return self._current_of([ k for k, _ in self.views ])

    @property
    def current_key( self ):
        """Key of the view shown"""
        keys = [ k for k, _ in self.views ]
        return keys[self._current_of(keys)]

    def _current_of( self, keys ):
        """Index of the view shown among the views with the keys"""
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

    def figure( self, index = None, key = None ):
        """Figure of a view (with the index or key, default the current one),
        or None if not yet available"""
        if key is None:
            key = self.views[self.current if index is None else index][0]
        with self._lock:
            if key == 'overview:multi':
                return self._overview_figure()
            return self._figures.get(key)

    def _overview_figure( self ):
        """The overview: the first plots together (made again only when the
        figures or the plots changed, so the same figure is returned until
        then)"""
        keys = self.overview_keys()
        made_from = ( self._figures, tuple(keys) )
        if self._overview is None or self._overview[0] != made_from:
            self._overview = ( made_from, _overview(self._figures,keys) )
        return self._overview[1]

    def status_lines( self, weights = '\u03a3w' ):
        """The two status lines: the file, the numbers of particles and the sum
        of their weights (named weights), and the progress of the reading (or
        an error)"""
        with self._lock:
            counts, progress, error = self._counts, self._progress, self._error
        name = pathlib.Path(self.filename).name
        if counts is None:
            first = f'{name}: {self._ntotal} particles'
        elif self._s.pick is None:
            #(all particles of the range are used, so only the numbers):
            n, _, w, _ = counts
            first = f'{name}: {n} particles, {weights} = {w:g}'
        else:
            n, ntot, w, wtot = counts
            pct = f'{100.0*n/ntot:.1f}%' if ntot else '-'
            wpct = f'{100.0*w/wtot:.1f}%' if wtot else '-'
            first = f'{name}: {n}/{ntot} particles ({pct}), {weights} = {w:g} ({wpct})'
        return first, ( f'error: {error}' if error else progress )

    #The state:

    def state( self, full = True ):
        """The state of the viewer, as a dict with what differs from the start:
        skip, limit, pick and edit (unless full is False), the collection of
        plots (see _stdviews, if not the default one), the plots (with the
        changes of the plots of the collection: change, remove, add and order,
        which are lists of histogram strings, except change, which maps plots
        of the collection to their new ones), and the view shown (if not the
        first). It is given as the view argument to open the viewer in the
        same state."""
        res = {}
        if self._collection != _default_collection:
            res['collection'] = self._collection
        if full:
            for k in ( 'skip', 'limit' ):
                if getattr(self._s,k):
                    res[k] = getattr(self._s,k)
            for k in ( 'pick', 'edit' ):
                if self._texts[k]:
                    res[k] = self._texts[k]
        plots, origins = self._s.plots, self._origins
        meta = lambda p : self._meta.get(p,( None, None ))
        diff = {}
        #(changes of plots, or of their titles or groups, as plot items with
        #all their titles and groups, see _stdviews):
        change = { o : _item(p,*meta(p)) for p, o in origins.items()
                   if p != o or meta(p) != self._base_meta.get(o,( None, None )) }
        remove = [ d for d in self._base if d not in origins.values() ]
        add = [ p for p in plots if p not in origins ]
        #(the order is only given if it is not that of the defaults, followed
        #by the added plots):
        kept = { o : p for p, o in origins.items() }
        expected = [ kept[d] for d in self._base if d in kept ] + add
        for k, v in ( ('change',change), ('remove',remove),
                      ('add',[ _item(p,*meta(p)) for p in add ]),
                      ('order',list(plots) if plots != expected else []) ):
            if v:
                diff[k] = v
        if diff:
            res['plots'] = diff
        key = self.views[self.current][0]
        if key != self.views[0][0]:
            res['view'] = 'overview' if key == 'overview:multi' else key[5:]
        return res

    def _apply_state( self, state ):
        """Apply the state (from _as_state) to the start (see state())"""
        if state.get('collection'):
            self._set_or_raise('collection',state['collection'])
        for k in ( 'skip', 'limit', 'pick', 'edit' ):
            if state.get(k):
                self._set_or_raise(k,str(state[k]))
        plots = state.get('plots',{})
        def find( text, what ):
            try:
                same = self._same_plot(text)
            except MCPLError:
                same = None
            if same is None:
                raise MCPLError(f'The viewer state {what} the plot "{text}", which is'
                                ' not one of the plots')
            return same
        def set_meta( plot, title, group ):
            #(the title and group of the plot are those of its item):
            p = self._same_plot(plot)
            if ( title, group ) == ( None, None ):
                self._meta.pop(p,None)
            else:
                self._meta[p] = ( title, group )
        for old, item in plots.get('change',{}).items():
            new, title, group = _plot_item(item)
            if not self.change_plot(find(old,'changes'),new)[0]:
                self._set_or_raise('plot',new)#(for the message of the problem)
            set_meta(new,title,group)
        for old in plots.get('remove',[]):
            self.change_plot(find(old,'removes'),'')
        for item in plots.get('add',[]):
            p, title, group = _plot_item(item)
            self._set_or_raise('plot',p)
            set_meta(p,title,group)
        order = [ find(p,'orders') for p in plots.get('order',[]) ]
        if order:
            #(the plots in the given order, followed by any others):
            self._s.plots[:] = order + [ p for p in self._s.plots if p not in order ]
        self._current = None

    def suggested_state_filename( self ):
        """<input>_viewer.json, or <input>_viewer2.json, ... if that exists"""
        return _free_filename(self.filename,'_viewer','.json')

    def try_save_state( self, filename ):
        """Save the state (see state()) as JSON in a new file (never overwriting
        existing files, and without writing in a dry run): (ok, message)"""
        import json
        if pathlib.Path(filename).exists():
            return False, f'The file {filename} already exists'
        if self._dry_run:
            return True, f'Dry run: the viewer state was not saved in {filename}'
        try:
            pathlib.Path(filename).write_text(json.dumps(self.state(),indent=1) + '\n')
        except OSError as e:
            return False, f'Can not write {filename} ({e})'
        return True, f'Saved the viewer state in {filename}'

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
        import json

        from ._extract import _shell_arg
        prog, fn = self._progname, _shell_arg(self.filename) if ' ' in self.filename else self.filename
        opts = self._options()
        #The state beyond the options, as --view=VIEW, or as JSON with the
        #strings in single quotes (see _as_state), in double quotes (which
        #work in all shells, as the texts contain none of the characters which
        #are special in some of them):
        state = self.state(full = False)
        if not state:
            view = '-w'
        elif list(state) == [ 'view' ]:
            view = f'--view="{state["view"]}"'
        elif list(state) == [ 'collection' ]:
            view = f'-w{state["collection"]}'
        else:
            text = json.dumps(state,separators=(',',':')).replace('"',"'")
            view = f'--view="{text}"'
        return { 'view' : ' '.join([ prog, view ] + opts + [ fn ]),
                 'extract' : ' '.join([ prog, '-e' ] + opts + [ fn, self.suggested_filename() ]) }

    #Writing:

    def suggested_filename( self ):
        """<input>_selected.mcpl.gz, or <input>_selected2.mcpl.gz, ... if that
        (or the same without .gz) exists"""
        return _free_filename(self.filename,'_selected','.mcpl.gz','.mcpl')

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

def _free_filename( filename, suffix, ext, *other_exts ):
    """The name <input><suffix><ext> next to the file (without its extensions
    .mcpl and .gz), or with 2, 3, ... after the suffix if that (or the same
    with one of the other extensions) exists"""
    p = pathlib.Path(filename)
    stem = p.name
    for e in ( '.gz', '.mcpl' ):
        stem = stem.removesuffix(e)
    i = 1
    while True:
        name = f'{stem}{suffix}{i if i > 1 else ""}'
        cands = [ p.with_name(name + e) for e in ( ext, ) + other_exts ]
        if not any( c.exists() for c in cands ):
            return str(cands[0]) if p.parent != pathlib.Path('.') else cands[0].name
        i += 1

class _Cancelled(Exception):
    pass

#The entries of the state (see Viewer.state), and of its changes of the plots:
_state_keys = ( 'skip', 'limit', 'pick', 'edit', 'collection', 'plots', 'view' )
_state_plot_keys = ( 'change', 'remove', 'add', 'order' )

def _as_state( view ):
    """The state given as the view argument of the viewer (a dict, its JSON
    text, or the name of a .json file with it), or None if it is a view"""
    import json
    if view is None:
        return None
    if isinstance(view,dict):
        state, where = view, 'The viewer state'
    elif view.lstrip().startswith('{'):
        #(as JSON, or with the strings in single quotes, which is easier on
        #command lines, see Viewer.commands; the texts of the state can
        #contain neither kind of quote):
        text = view if '"' in view else view.replace("'",'"')
        where = f'The viewer state "{view}"'
        try:
            state = json.loads(text)
        except ValueError as e:
            raise MCPLError(f'{where} is not valid JSON ({e})')
    elif view.endswith('.json'):
        where = f'The viewer state in {view}'
        try:
            state = json.loads(pathlib.Path(view).read_text())
        except OSError as e:
            raise MCPLError(f'Can not read the viewer state from {view} ({e})')
        except ValueError as e:
            raise MCPLError(f'{where} is not valid JSON ({e})')
    else:
        return None
    def check( ok, what ):
        if not ok:
            raise MCPLError(f'{where} is not valid: {what}')
    check(isinstance(state,dict),'it must be a JSON object, like {"pick":"pdgcode == neutron"}')
    for k in state:
        check(k in _state_keys,f'unknown entry "{k}" (the entries are: {", ".join(_state_keys)})')
    for k in ( 'skip', 'limit' ):
        check(isinstance(state.get(k,0),int),f'{k} must be a number')
    for k in ( 'pick', 'edit', 'collection', 'view' ):
        check(isinstance(state.get(k,''),str),f'{k} must be a text')
    plots = state.get('plots',{})
    check(isinstance(plots,dict),'plots must be a JSON object')
    for k, v in plots.items():
        check(k in _state_plot_keys,f'unknown entry "{k}" of plots (the entries are:'
              f' {", ".join(_state_plot_keys)})')
        if k == 'change':
            check(isinstance(v,dict),'the change of plots must be a JSON object')
            items = list(v.values())
        else:
            check(isinstance(v,list),f'the {k} of plots must be a list')
            items = v
        if k in ( 'change', 'add' ):
            #(plot items, see _stdviews):
            for item in items:
                try:
                    _plot_item(item)
                except ( TypeError, ValueError ) as e:
                    check(False,f'in the {k} of plots, {e}')
        else:
            check(all( isinstance(x,str) for x in items ),f'the {k} of plots must be a list of texts')
    return state

def _make_filler( text, pick ):
    """Histogram filler of a plot (a histogram string)"""
    from ._histogram import _filler_for
    from ._histstring import _parse_hist
    o = _parse_hist(text)
    if o['print']:
        raise MCPLError('The histogram option print can not be used in the viewer')
    return _filler_for(o,pick = pick)

def _plot_field( text ):
    """The field if the plot (a histogram string) is of exactly one field
    (e.g. "z" or "weight;unweighted"), else None"""
    from ._expressions import _Expr
    from ._histstring import _parse_hist
    exprs = _parse_hist(text)['exprs']
    return _Expr(exprs[0]).field if len(exprs) == 1 else None

#Fields for which it is noted when all particles have the same value:
_const_fields = ( 'pdgcode', 'userflags', 'ekin', 'x', 'y', 'z', 'ux', 'uy', 'uz',
                  'time', 'weight', 'polx', 'poly', 'polz' )

def _overview( figures, keys ):
    """The overview: the plots of the views with the keys together (as far as
    they are available), with the title of the plots"""
    from .plotting import Figure, Panel, Text
    figs = [ figures.get(k) for k in keys ]
    if all( f is None for f in figs ):
        return None
    panels = []
    for f in figs:
        panel = copy.copy(f.panels[0]) if f is not None else Panel( items = [ Text('') ] )
        panel.title = None#(the title of the plots is that of the overview)
        panels.append(panel)
    title = next( ( f.title for f in figs if f is not None ), None )
    return Figure( title = title, nrows = 2, ncols = 3, panels = panels )

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
    """Show the particles of a file in the viewer: an overview and plots
    (histograms as for mcpltool -H, to which the plots, histogram strings like
    "hypot(x,y)/cm;logy", are added), for the particles in a range of the
    file (after skipping skip particles, at most limit particles), picked with
    pick and then edited with edit (expressions, or ParticleFilter and
    ParticleEdit objects), which can all be changed in the viewer. view is the
    name of a collection of plots to start from (e.g. 'beamz', see mcpltool
    --full-help), the view shown first ('overview', or a plot, e.g. 'ekin'),
    or a state of the viewer (as saved in the viewer, a .json file, or a
    dict). In Jupyter, the viewer is a panel of ipywidgets
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
