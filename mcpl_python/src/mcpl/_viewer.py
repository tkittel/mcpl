
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

import functools
import pathlib
import re
import threading

from ._common import MCPLError
from ._stdviews import (
    _collections,
    _default_collection,
    _field_titles,
    _item,
    _plot_item,
)
from ._viewer_overviews import check_spec, default_specs, overview_figure, resolve
from ._viewer_reading import _make_filler, _Reading

_fields = ( 'skip', 'limit', 'pick', 'edit', 'collection', 'plot' )

class _Settings:
    """What is shown: a range of particles in the file, picked and edited, and
    the plots (histogram strings)"""
    def __init__( self, skip = 0, limit = None, pick = None, edit = None, plots = () ):
        self.skip, self.limit = skip, limit
        self.pick, self.edit = pick, edit#(ParticleFilter, ParticleEdit or None)
        self.plots = list(plots)
    def copy( self ):
        return _Settings(self.skip,self.limit,self.pick,self.edit,self.plots)

class Viewer(_Reading):
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
            #(the userdata fields, as (name, type, number of values or None for
            #fields of one value), for completions and checks):
            self._ud_fields = []
            for e in ( f.userdata_layout or '' ).split(','):
                if ':' in e:
                    name, kind = e.split(':',1)
                    kind, _, n = kind.partition('[')
                    self._ud_fields.append( ( name, kind, int(n[:-1]) if n else None ) )
            #(the fields which the file does not have, which are 0):
            self._absent = ( set() if f.opt_userflags else { 'userflags' } ) | (
                set() if f.opt_polarisation else { 'polx', 'poly', 'polz' } )
        #(set while a state is applied, when the plots are not checked against
        #the fields of the userdata, so the plots of another file are kept, see
        #for_file, and show the problem instead):
        self._loading = False
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
        #(the figures of the last reading which was done, for its particles,
        #which are kept for plots which do not change, see _read):
        self._done = None#(particles key, {view key: figure}, constants, counts)
        #(the last change of toggle_scale, which the same key undoes: the
        #option, the plot after the change, and before):
        self._scale_undo = None
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
        self._overviews = {}#view key -> (what its figure was made from, figure)
        #The view argument is the name of a collection of plots, a view, or a
        #state (see state()), which is applied before the other arguments (so
        #these can change it):
        if isinstance(view,str) and view in _collections:
            view = { 'collection' : view }
        state = _as_state(view)
        if state is not None:
            self._loading = True
            try:
                self._apply_state(state)
            finally:
                self._loading = False
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
        if name == _default_collection:
            #(the overview of all particle fields also has those of the
            #userdata, at the end):
            items += self._userdata_items()
        self._collection = name
        #(the overviews of the collection, see _viewer_overviews, and the
        #indices of those which were removed):
        #(and those added, which are kept, see add_overview):
        self._added_overviews = getattr(self,'_added_overviews',[])
        self._overview_specs = list( _collections[name][2] if len(_collections[name]) > 2
                                     else default_specs ) + self._added_overviews
        self._removed_overviews = set()
        self._base = [ p for p, _, _ in items ]
        self._base_meta = { p : ( t, g ) for p, t, g in items if ( t, g ) != ( None, None ) }
        #(the plot of the collection each plot comes from, if any, for state()):
        self._origins = { p : p for p in self._base }
        added = [ p for p in added if p not in self._origins ]
        self._meta = { **{ p : self._meta[p] for p in added if p in self._meta },
                       **self._base_meta }
        self._s.plots = list(self._base) + added

    def _userdata_items( self ):
        """Plot items of the fields of the userdata (of each value, for arrays)"""
        items = []
        for name, _, n in self._ud_fields:
            if n is None:
                items.append( ( f'userdata.{name}', None, 'Fields' ) )
            else:
                items += [ ( f'userdata.{name}.at({i})', None, 'Fields' ) for i in range(n) ]
        return items

    def _set_or_raise( self, field, text ):
        ok, msg = self.set(field, text, restart = False)
        if not ok:
            raise MCPLError(msg)

    def _view_key( self, view ):
        """The key of a view given as overview (or overview:TITLE, for the
        overviews after the first) or as a plot (histogram string)"""
        if view in ( 'overview', 'overview:multi' ):
            return 'overview'
        if view.startswith('overview:'):
            key = self._overview_key_of(view[9:])
            if key is not None:
                return key
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
        if field in ( 'pick', 'edit' ) or ( field == 'plot' and not self._loading ):
            self._check_userdata(text)
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

    def _check_userdata( self, text ):
        """Check that the userdata fields used in the text (an expression, or a
        histogram string) are fields of the file (before the particles are
        read)"""
        fields = { name : n for name, _, n in self._ud_fields }
        if not fields and re.search(r'\buserdata\b',text):
            raise MCPLError(f'There are no userdata fields in this file, in "{text}"')
        for m in re.finditer(r'\buserdata\.([A-Za-z0-9_]+)(\.at\( *([0-9]+) *\))?',text):
            name, index = m.group(1), m.group(3)
            if name not in fields:
                raise MCPLError(f'No userdata field "{name}" (the fields are:'
                                f' {", ".join(fields)}), in "{text}"')
            n = fields[name]
            if ( n is None ) != ( index is None ) or ( index is not None and int(index) >= n ):
                use = ( f'userdata.{name}' if n is None else
                        f'userdata.{name}.at(0) to userdata.{name}.at({n-1})' )
                raise MCPLError(f'The userdata field "{name}" has {n or "one"} value'
                                f'{"s" if n else ""} per particle (use {use}), in "{text}"')

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
                #(the same collection only gives back its removed overviews):
                if self._removed_overviews:
                    self._removed_overviews = set()
                    with self._lock:
                        self._updates += 1
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
                #(skip and limit are the same if they give the same particles,
                #e.g. limits beyond the end of the file):
                new = ( value, self._s.limit ) if field == 'skip' else ( self._s.skip, value )
                same = self._range(*new) == self._range(self._s.skip,self._s.limit)
            #(the value is kept, also when it gives the same particles):
            setattr(self._s,field,value)
            if same:
                return True, ''
        if restart:
            self._restart()
        return True, ''

    def _range( self, skip, limit ):
        """The range of particles of the file (first, end) for skip and limit"""
        n = self._ntotal
        first = min( skip or 0, n )
        return first, n if not limit else min( n, first + limit )

    def toggle_scale( self, option, key = None ):
        """Toggle the option logx or logy of a plot (the view with the key,
        default the shown one) between log and linear, from the scale which is
        shown (also when it was decided for the values, with auto), changing
        its histogram string: (ok, message). Toggling the same option of the
        plot again undoes it (also giving back auto), unless the plot was
        changed otherwise in between."""
        from ._histstring import _hist_set_option, _parse_hist
        key = key or self.current_key
        axis = option[-1]
        if not key.startswith('plot:'):
            return False, f'Choose a plot to change its {axis} axis'
        plot = key[5:]
        undo = self._scale_undo
        if undo is not None and undo[:2] == ( option, plot ):
            ok, msg = self.change_plot(plot,undo[2])
            self._scale_undo = None
            return ( True, f'{axis} axis as before' ) if ok else ( ok, msg )
        o = _parse_hist(plot)
        if len(o['exprs']) > 1:
            return False, f'{len(o["exprs"])}D plots have no log {axis} option'
        if option == 'logx' and o['bar']:
            return False, 'Bar charts have no log x option'
        if option == 'logx' and o['lethargy']:
            return False, 'Plots with lethargy always have a log x axis'
        fig = self.figure(key = key)
        if o[option] == 'auto' and ( fig is None or not fig.panels ):
            return False, 'The plot is not drawn yet (try again when it is)'
        if o[option] != 'auto':
            shown = o[option] is True
        else:
            #(as decided for the values; the bars of bar charts are horizontal,
            #with the values along the x axis of the panel):
            panel = fig.panels[0]
            shown = bool( panel.logx or panel.logy ) if o['bar'] else bool(getattr(panel,option))
        new = _hist_set_option(plot,option,None if shown else True)
        ok, msg = self.change_plot(plot,new)
        if not ok:
            return ok, msg
        self._scale_undo = ( option, new, plot )
        return True, f'{"linear" if shown else "log"} {axis}' + ( ' (was auto)' if o[option] == 'auto' else '' )

    def change_plot( self, old, text ):
        """Replace the plot old (its histogram string) by the text, in its place
        among the views, or remove it if the text is empty (restarting the
        reading): (ok, message)"""
        self._scale_undo = None#(see toggle_scale, which sets it again)
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
        meta = _doubtful_title(meta,old,text)
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
        if not key.startswith('plot:'):
            ov = dict(self.overviews()).get(key)
            return { 'title' : None, 'name' : ov.title if ov else 'Overview', 'plot' : None,
                     'group' : None, 'badges' : [ f'{len(ov.plots) if ov else 0} plots' ],
                     'constant' : None, 'absent' : False }
        p = key[5:]
        title, group = self._meta.get(p,( None, None ))
        o = _parsed_plot(p)#(cached, for the cards, which are shown often)
        with self._lock:
            figure = self._figures.get(key)
            constants = self._constants
        #(the log scales chosen with auto are known when the plot is made):
        panel = figure.panels[0] if figure is not None and figure.panels else None
        logx = panel.logx if panel is not None else o['logx'] is True
        logy = panel.logy if panel is not None else o['logy'] is True
        badges = []
        if len(o['exprs']) > 1:
            badges.append(f'{len(o["exprs"])}D')
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
        return { 'title' : title, 'name' : title or _auto_title(p) or ' : '.join(o['exprs']), 'plot' : p,
                 'group' : group, 'badges' : badges,
                 'constant' : ( '0' if field in self._absent else
                                constants.get(field) if field else None ),
                 'absent' : field in self._absent }

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
            return 0, [ ( name, c[0] ) for name, c in _collections.items()
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
            if group not in groups or name.startswith('userdata.'):#(see below)
                continue
            base = re.match(r'[A-Za-z_][A-Za-z0-9_]*', name).group(0)
            if not base.startswith(prefix):
                continue
            insert = base + ( '(' if '(' in name else ( '=' if '=' in name else '' ) )
            if insert not in [ r[0] for r in res ]:
                res.append( ( insert, short ) )
        if not options:
            #(the userdata fields of the file, as userdata.NAME, and only those
            #after "userdata."):
            m = re.search(r'\buserdata\.([A-Za-z0-9_]*)$', text[:cursor])
            if m:
                start, prefix, base, res = m.start(1), m.group(1), '', []
            else:
                base = 'userdata.'
            for name, kind, n in self._ud_fields:
                insert = base + name + ( '' if n is None else '.at(' )
                if insert.startswith(prefix) and ( m or prefix ):
                    res.append( ( insert, f'userdata field ({kind})' if n is None else
                                  f'userdata field ({n} values of {kind}, at(0) to at({n-1}))' ) )
        return start, res

    def hint( self, field, text, cursor = None ):
        """Short description of the name at the cursor, as "name  description",
        or None"""
        from ._exprhelp import _short_hint
        if field == 'collection':
            name = text.strip()
            return f'{name}  {_collections[name][0]}' if name in _collections else None
        cursor = len(text) if cursor is None else cursor
        if not self._ud_fields and re.search(r'\buserdata\.[A-Za-z0-9_]*$', text[:cursor]):
            return 'userdata.  there are no userdata fields in this file'
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
        (only with multi_overview, see overviews), and each plot (with its
        histogram string as label)"""
        res = [ ( k, 'overview' if k == 'overview:multi' else f'overview: {ov.title}' )
                for k, ov in self.overviews() ]
        with self._lock:
            constants = self._constants
        #(plots of a field where all particles have the same value are marked):
        for p in self._s.plots:
            field = _plot_field(p)
            res.append( ( f'plot:{p}', f'{p} (all {constants[field]})'
                          if field in constants else p ) )
        return res

    def overviews( self ):
        """The overviews shown (only with multi_overview, see views), as (view
        key, Overview): those of the collection which were not removed and
        have plots (see _viewer_overviews). The key of the first of the
        collection is overview:multi, and of the others overview:N (N its
        position in the collection)."""
        return [ ( k, ov ) for i, k, ov in self._all_overviews()
                 if i not in self._removed_overviews ]

    def _all_overviews( self ):
        """The overviews of the collection which have plots, also those which
        were removed, as (position in the collection, view key, Overview)"""
        if not self.multi_overview:
            return []
        groups = { p : g for p, ( _, g ) in self._meta.items() }
        res = []
        for i, spec in enumerate(self._overview_specs):
            ov = resolve(spec,self._s.plots,groups)
            if ov is not None:
                res.append( ( i, 'overview:multi' if i == 0 else f'overview:{i}', ov ) )
        return res

    def _overview_key_of( self, title ):
        """The key of the overview with the title (also before multi_overview is
        set, see overviews), or None"""
        return next( ( 'overview:multi' if i == 0 else f'overview:{i}'
                       for i, spec in enumerate(self._overview_specs)
                       if spec['title'] == title and i not in self._removed_overviews ), None )

    def overview_keys( self, key = 'overview:multi' ):
        """The keys of the views of the plots of the cells of the overview with
        the key (in the order of its panels, None for empty cells)"""
        ov = dict(self.overviews()).get(key)
        return [] if ov is None else [ None if p is None else f'plot:{p}' for p in ov.cells ]

    def add_overview( self, spec ):
        """Add an overview (a specification, see _viewer_overviews, e.g.
        {"title":"Spectra","plots":["ekin","wavelength"]}): (ok, message)"""
        try:
            check_spec(spec)
        except ( TypeError, ValueError ) as e:
            return False, str(e)[:1].upper() + str(e)[1:]
        groups = { p : g for p, ( _, g ) in self._meta.items() }
        ov = resolve(spec,self._s.plots,groups)
        for p in ( ov.plots if ov is not None else () ):
            ok, msg = self.check('plot',p)
            if not ok:
                return False, f'The overview "{spec["title"]}" has the plot "{p}": {msg}'
        self._added_overviews.append(dict(spec))
        self._overview_specs.append(dict(spec))
        self._restart()#(its plots are read too)
        return True, ''

    def remove_overview( self, key ):
        """Remove the overview with the key (see overviews): whether it was
        removed (choosing the collection again gives it back)"""
        if key not in dict(self.overviews()):
            return False
        self._removed_overviews.add( 0 if key == 'overview:multi' else int(key[9:]) )
        if self._current == key or ( key == 'overview:multi' and self._current == 'overview' ):
            self._current = None
        with self._lock:
            self._updates += 1
        return True

    def _reading_settings( self ):
        """What is read: the settings, with the plots of the overviews too (also
        of those which were removed, which choosing the collection again gives
        back)"""
        s = self._s.copy()
        s.plots += [ p for _, _, ov in self._all_overviews() for p in ov.plots ]
        s.plots = list(dict.fromkeys(s.plots))
        return s

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
        if key.startswith('overview:'):
            ov = dict(self.overviews()).get(key)
            with self._lock:
                return None if ov is None else self._overview_figure(key,ov)
        with self._lock:
            return self._figures.get(key)

    def _overview_figure( self, key, ov ):
        """The figure of the overview (made again only when the figures or its
        plots changed, so the same figure is returned until then)"""
        made_from = ( self._figures, tuple(ov.cells), ov.ncols )
        old = self._overviews.get(key)
        if old is None or old[0] != made_from:
            self._overviews[key] = old = ( made_from, overview_figure(self._figures,ov) )
        return old[1]

    def status_lines( self, weights = '\u03a3w' ):
        """The two status lines: the file, the numbers of particles and the sum
        of their weights (named weights, see counts_text), and the progress of
        the reading (or an error)"""
        with self._lock:
            progress, error = self._progress, self._error
        counts = self.counts_text(weights)
        first = self.file_text() if counts is None else f'{self._name}: {counts}'
        return first, ( f'error: {error}' if error else progress )

    @property
    def _name( self ):
        return pathlib.Path(self.filename).name

    def file_text( self ):
        """The name of the file, with its number of particles"""
        return f'{self._name}: {self._ntotal} particles'

    @property
    def nused( self ):
        """The number of particles used (picked), or None while not known"""
        with self._lock:
            return None if self._counts is None else self._counts[0]

    def counts_text( self, weights = '\u03a3w' ):
        """The numbers of particles used (of those in the range, when picked)
        and the sum of their weights (named weights), as a text, or None while
        they are not known"""
        with self._lock:
            counts = self._counts
        if counts is None:
            return None
        if self._s.pick is None:
            #(all particles of the range are used, so only the numbers):
            n, _, w, _ = counts
            return f'{n} particles, {weights} = {w:g}'
        n, ntot, w, wtot = counts
        pct = f'{100.0*n/ntot:.1f}%' if ntot else '-'
        wpct = f'{100.0*w/wtot:.1f}%' if wtot else '-'
        return f'{n}/{ntot} particles ({pct}), {weights} = {w:g} ({wpct})'

    #The state:

    def state( self, full = True ):
        """The state of the viewer, as a dict with what differs from the start:
        skip, limit, pick and edit (unless full is False), the collection of
        plots (see _stdviews, if not the default one), the plots (with the
        changes of the plots of the collection: change, remove, add and order,
        which are lists of histogram strings, except change, which maps plots
        of the collection to their new ones), the overviews added (see
        add_overview) and removed (by their titles), and the view shown (if
        not the first). It is given as the view argument to open the viewer in the
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
        nbase = len(self._overview_specs) - len(self._added_overviews)
        added = [ s for i, s in enumerate(self._overview_specs)
                  if i >= nbase and i not in self._removed_overviews ]
        removed = [ self._overview_specs[i]['title'] for i in sorted(self._removed_overviews)
                    if i < nbase ]
        if added:
            res['add_overviews'] = added
        if removed:
            res['remove_overviews'] = removed
        key = self.views[self.current][0]
        if key != self.views[0][0]:
            ov = dict(self.overviews()).get(key)
            res['view'] = ( 'overview' if key == 'overview:multi' else
                            f'overview:{ov.title}' if ov is not None else key[5:] )
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
        for spec in state.get('add_overviews',[]):
            ok, msg = self.add_overview(spec)
            if not ok:
                raise MCPLError(f'The viewer state adds an overview which is not valid: {msg}')
        titles = [ s['title'] for s in self._overview_specs ]
        for title in state.get('remove_overviews',[]):
            if title not in titles:
                raise MCPLError(f'The viewer state removes the overview "{title}", which is'
                                ' not one of the overviews')
            self._removed_overviews.add(titles.index(title))
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

    def code( self, plots = None, filename = None ):
        """The command (of mcpltool) and the code doing the same as the viewer,
        as a dict with the keys of _viewer_code.kinds: histograms of the plots
        (a list of histogram strings), or else writing the picked and edited
        particles to the file filename (default suggested_filename())"""
        from ._reader import MCPLFile
        from ._viewer_code import _Job, code
        s = self._s
        expr = lambda e : None if e is None else e.expression
        mark = False
        if plots is None:
            n = self._ntotal
            with MCPLFile(self.filename) as f:
                has_statsums = any( v is not None for v in f.stat_sum.values() )
            #(stat:sum entries are marked as not available as by mcpltool -e,
            #see _mcpltool_extract):
            mark = has_statsums and bool( s.skip or 0 < ( s.limit or 0 ) < n
                         or ( s.pick is not None and s.pick._uses_fileidx )
                         or ( s.edit is not None and 'weight' in s.edit.modified_fields ) )
        job = _Job(self.filename,s.skip,s.limit,expr(s.pick),expr(s.edit),plots,
                   filename or self.suggested_filename(),mark)
        return code(job,self._progname)

    #Writing:

    @property
    def has_userdata( self ):
        """Whether the particles of the file have userdata"""
        return bool(self._ud_fields)

    @property
    def collection( self ):
        """The name of the collection of plots the plots started from"""
        return self._collection

    def for_file( self, filename, particles = True ):
        """A viewer of another file, in the same state, but without skip and
        limit (which are of this file), and without the pick and edit unless
        particles is set (not for a file written with them): (viewer, message),
        with the message saying what could not be kept (e.g. a pick with fields
        of the userdata which the other file does not have), or empty"""
        drop = ( 'skip', 'limit' ) + ( () if particles else ( 'pick', 'edit' ) )
        state = { k : v for k, v in self.state().items() if k not in drop }
        kw = { 'dry_run' : self._dry_run, 'progname' : self._progname }
        try:
            return Viewer(filename,view=state,**kw), ''
        except MCPLError as e:
            problem = e
        for drop, what in ( ( ( 'pick', 'edit' ), 'the pick and edit' ),
                            ( ( 'pick', 'edit', 'plots', 'view' ), 'the pick, edit and plots' ) ):
            try:
                return ( Viewer(filename,view={ k : v for k, v in state.items() if k not in drop },**kw),
                         f'Not kept for this file: {what} ({problem})' )
            except MCPLError:
                pass
        return Viewer(filename,**kw), f'Not kept for this file: the state of the viewer ({problem})'

    @property
    def changes_particles( self ):
        """Whether the particles shown are not just those of the file (with
        skip, limit, pick or edit), so writing them gives a new file"""
        s = self._s
        return bool( s.skip or s.limit or s.pick is not None or s.edit is not None )

    #(the reason why writing is not possible, see changes_particles):
    nothing_to_write = 'Pick, edit or choose a range of particles first, to write them to a new file'

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

def _doubtful_title( meta, old, new ):
    """The title and group (meta) of a plot changed from old to new (histogram
    strings), with " (??)" after the title if the expressions changed (not
    just the options, or the unit of a field), since the title might no longer
    fit. Plots without a title of their own get the new title from their
    expression (see _auto_title)."""
    from ._expressions import _expr_canonical
    from ._histstring import _hist_parts
    if meta is None or meta[0] is None or meta[0].endswith('(??)'):
        return meta
    def exprs( text ):
        return [ _expr_canonical(e) for e in _hist_parts(text)[0].split(':') ]
    #(the same field in other units, e.g. ekin/MeV for ekin, is the same):
    same_field = _auto_title(old) is not None and _auto_title(old) == _auto_title(new)
    return meta if exprs(old) == exprs(new) or same_field else ( meta[0] + ' (??)', meta[1] )

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

#The entries of the state (see Viewer.state), and of its changes of the plots:
_state_keys = ( 'skip', 'limit', 'pick', 'edit', 'collection', 'plots', 'add_overviews',
                'remove_overviews', 'view' )
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
    removed = state.get('remove_overviews',[])
    check(isinstance(removed,list) and all( isinstance(x,str) for x in removed ),
          'remove_overviews must be a list of the titles of overviews')
    added = state.get('add_overviews',[])
    check(isinstance(added,list),'add_overviews must be a list of overviews')
    for spec in added:
        try:
            check_spec(spec)
        except ( TypeError, ValueError ) as e:
            check(False,f'in add_overviews, {e}')
    return state

@functools.lru_cache(maxsize = 4096)
def _auto_title( plot ):
    """The title of a plot (histogram string) from its expression, if it is a
    single field, maybe divided by a unit (e.g. Energy for ekin/MeV), or a
    field of the userdata, else None"""
    import ast

    from ._common import MCPLError
    from ._expressions import _Expr
    from ._exprsyntax import _Unit
    from ._histstring import _hist_parts
    exprs = _hist_parts(plot)[0].split(':')
    if len(exprs) != 1:
        return None
    try:
        node = _Expr(exprs[0]).tree.body
    except MCPLError:#(e.g. while a plot is written, see WidgetViewer.compose)
        return None
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div) and isinstance(node.right,_Unit):
        node = node.left
    if not isinstance(node,ast.Name):
        return None
    if node.id.startswith('userdata.'):
        return f'Userdata {node.id[9:]}'
    return _field_titles.get(node.id)

@functools.lru_cache(maxsize = 4096)
def _parsed_plot( text ):
    """The parsed plot (see _parse_hist, which must not be changed)"""
    from ._histstring import _parse_hist
    return _parse_hist(text)

@functools.lru_cache(maxsize = 4096)
def _plot_field( text ):
    """The field if the plot (a histogram string) is of exactly one field
    (e.g. "z" or "weight;unweighted"), else None"""
    from ._expressions import _Expr
    from ._histstring import _parse_hist
    exprs = _parse_hist(text)['exprs']
    return _Expr(exprs[0]).field if len(exprs) == 1 else None

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

def view( filename, *, pick = None, edit = None, skip = 0, limit = None,
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
