
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
checking, history and completion, the views (each plot, and for the front
ends which show several plots at once, the overview of each group of plots)
and their figures, which are computed by reading the
file in a background thread, the state of the viewer (see state()), the
equivalent commands, and writing the picked and edited particles to a new
file."""

__all__ = ['view']

import functools
import pathlib
import re
import threading

from ._common import MCPLError
from ._histstring import _display_by_choice
from ._stdviews import _default_groups, _field_titles, _groups, custom_key
from ._viewer_groups import PlotGroups, group_names, parse_groups, title_of
from ._viewer_output import _as_state, _Output
from ._viewer_overviews import overview_figure
from ._viewer_reading import _make_filler, _Reading
from ._viewer_ui import count_text, field_names, number_text, plot_of


class _Settings:
    """What is shown: a range of particles in the file, picked and edited, and
    the plots (histogram strings)"""
    def __init__( self, skip = 0, limit = None, pick = None, edit = None, plots = () ):
        self.skip, self.limit = skip, limit
        self.pick, self.edit = pick, edit#(ParticleFilter, ParticleEdit or None)
        self.plots = list(plots)
    def copy( self ):
        return _Settings(self.skip,self.limit,self.pick,self.edit,self.plots)

class Viewer(_Output,_Reading):
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
            from ._userdata import userdata_fields
            self._ud_fields = userdata_fields(f.userdata_layout) if f.userdata_layout else []
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
        self._history = { f : [] for f in field_names }
        self._s = _Settings()
        #(the plots, in groups, with those of the fields of the userdata in the
        #group of the fields, see _viewer_groups):
        self._groups = PlotGroups({ 'fields' : self._userdata_items() })
        self._sync()
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
        self._done = None#(particles key, {view key: figure}, found, counts)
        #(the last change of toggle_scale, which the same key undoes: the
        #option, the view key after the change, the plot before, the view key
        #before, and whether a plot of a standard group was copied):
        self._scale_undo = None
        self._seen = -1
        self._status_updates, self._status_seen, self.plot_changed = 0, 0, True
        self._updates = 0
        self._job = None
        self._wake = threading.Condition(self._lock)
        self._thread = None
        self._stopping = False
        #(the front ends which can show several plots at once set
        #multi_overview, see views):
        self.multi_overview = False
        #(the front ends which start a new plot when its place in the overview
        #of the custom plots is clicked set new_plot_cell, see overview_keys):
        self.new_plot_cell = False
        #(whether Tab completion was used, after which the hints of the fields
        #no longer mention it, see _viewer_ui.field_hint):
        self.tab_used = False
        self._current = None#(key of the view shown, None for the first)
        self._overviews = {}#view key -> (what its figure was made from, figure)
        #The view argument is the keys of groups of plots (separated by
        #commas), a view, or a state (see state()), which is applied before the
        #other arguments (so these can change it):
        if isinstance(view,str) and parse_groups(view):
            view = { 'groups' : parse_groups(view) }
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

    def _sync( self ):
        """The plots of the settings (shown as views) from the groups"""
        self._s.plots = [ p for p, _, _ in self._groups.cards() ]

    def _on_found( self, found ):
        """After a reading: the defaults of the settings of the groups depend on
        what it found (see PlotGroups.setting), so their plots are read if
        they changed"""
        if found == self._groups.found:
            return
        before = self._reading_settings().plots
        with self._lock:
            self._groups.found = found
            self._sync()
            self._updates += 1#(e.g. the correlation coefficients are new)
        if self._reading_settings().plots != before:
            self._restart()

    #The settings of the groups of plots (see PlotGroups.setting):

    @property
    def found( self ):
        """What the last reading found (see _viewer_reading._Computation.found):
        the fields where all particles have the same value ('constants'), the
        particle types as (pdgcode, sum of weights), the largest first
        ('types'), and the correlation coefficients of the fields of
        correlation plots ('correlations')"""
        return self._groups.found

    def group_setting( self, key, name ):
        """The value of the setting of the standard group with the key"""
        return self._groups.setting(key,name)

    def group_settings( self, key ):
        """The names of the settings of the group (with the key), with their
        possible values, as (name, value, choices)"""
        g = self._groups
        return [ ( n, g.setting(key,n), g.setting_choices(key,n) ) for n in g.setting_names(key) ]

    def most_correlated( self, key ):
        """The variables of the correlation plot of the group with the strongest
        correlations (see PlotGroups.most_correlated), or None if not yet
        known"""
        return self._groups.most_correlated(key)

    def set_group_setting( self, key, name, value ):
        """Set the setting of the standard group with the key (see
        PlotGroups.setting: the particle type as a PDG code or None for all,
        display_by as pdgcode or single, or the variables of a correlation plot
        as a list of expressions, or None for the default): whether it
        changed"""
        if name == 'variables' and value is not None and len(value) < 2:
            raise MCPLError('The correlation plot needs at least two variables')
        with self._lock:
            changed = self._groups.set_setting(key,name,value)
            if changed:
                self._sync()
        if changed:
            self._restart()
        return changed

    def _userdata_items( self ):
        """Plots of the fields of the userdata (of each value, for arrays)"""
        items = []
        for name, _, n in self._ud_fields:
            if n is None:
                items.append(f'userdata.{name}')
            else:
                items += [ f'userdata.{name}.at({i})' for i in range(n) ]
        return items

    def _set_or_raise( self, field, text ):
        ok, msg = self.set(field, text, restart = False)
        if not ok:
            raise MCPLError(msg)

    def _view_key( self, view ):
        """The key of a view given as overview (the first), overview:GROUP (the
        overview of a group, by its key), as a plot (histogram string, of a
        standard group if one has it, else a custom one, or only expressions,
        e.g. ekin, for the first plot of them) or as custom:PLOT (a custom
        plot)"""
        if view == 'overview':
            return 'overview'
        if view.startswith('overview:') and ( view[9:] in _groups or view[9:] == custom_key ):
            return view
        if view.startswith('custom:'):
            same = self._same_plot(view[7:],self._groups.custom)
            if same is not None:
                return f'custom:{same}'
        try:
            same = self._same_plot(view) or self._plot_of_exprs(view)
        except MCPLError:
            same = None
        if same is None:
            raise MCPLError(f'Unknown groups of plots or view "{view}" (groups:'
                            f' {", ".join(_groups)}, separated by commas; views: overview,'
                            ' overview:GROUP or a plot, e.g. ekin)')
        return self._key_of(same)

    def _key_of( self, plot, custom = False ):
        """The key of the view of the plot: of the custom plot if custom is set
        (or if no standard group has it), else of the plot of a standard
        group"""
        standard = any( p == plot and g != custom_key for p, _, g in self._groups.cards() )
        return f'custom:{plot}' if custom or not standard else f'plot:{plot}'

    #Fields:

    def field_text( self, field ):
        """Current text of a field (as last set)"""
        if field == 'groups':
            return ','.join(self._groups.shown)
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
            v = _parse_count(text)
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
            _make_filler(text)#(checks the expressions and options)
            return text
        if field == 'groups':
            keys = parse_groups(text) if text.strip() else list(_default_groups)
            if keys is None:
                raise MCPLError(f'Unknown groups of plots "{text}" (give groups separated by'
                                f' commas: {", ".join(_groups)})')
            return keys
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
        """Apply the text of a field (restarting the reading): (ok, message).
        For the plot field, the plot is added at the end (unless it is
        there)."""
        try:
            value = self._parse(field,text)
        except MCPLError as e:
            return False, str(e)
        text = text.strip()
        h = self._history[field]
        if text and ( not h or h[-1] != text ):
            h.append(text)
        if field == 'plot':
            #(new plots are custom plots, see _viewer_groups, and the same
            #custom plot written differently is not added again):
            same = self._same_plot(text,self._groups.custom)
            if same is None:
                self._groups.add(text)
                self._sync()
            self._current = f'custom:{same or text}'
        elif field == 'groups':
            self._groups.use(value)
            self._sync()
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
        from ._reader import _particle_range
        return _particle_range(self._ntotal,skip,limit or None)

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
        plot = plot_of(key)
        if plot is None:
            return False, f'Choose a plot to change its {axis} axis'
        undo = self._scale_undo
        if undo is not None and undo[:2] == ( option, key ):
            #(back to the plot before, which for a plot of a standard group is
            #the plot itself, instead of the copy made of it):
            before, before_key, copied = undo[2:]
            if before_key.startswith('plot:'):
                ok, msg = self.change_plot(key,'') if copied else ( True, '' )
                self._current = before_key
            else:
                ok, msg = self.change_plot(key,before)
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
        n = len(self._groups.custom)
        ok, msg = self.change_plot(key,new)
        if not ok:
            return ok, msg
        self._scale_undo = ( option, self.current_key, plot, key, len(self._groups.custom) > n )
        return True, f'{"linear" if shown else "log"} {axis}' + ( ' (was auto)' if o[option] == 'auto' else '' )

    def change_plot( self, old, text ):
        """Replace the plot old (the key of its view, or its histogram string:
        of the custom plot if there is one, else of the plot of a standard
        group) by the text, or remove it if the text is empty (restarting the
        reading): (ok, message). Custom plots are changed in their place, and
        the plots of the standard groups are copied into the custom group,
        changed (see _viewer_groups)."""
        self._scale_undo = None#(see toggle_scale, which sets it again)
        text = text.strip()
        groups = self._groups
        key = old if plot_of(old) is not None else self._key_of(old,groups.is_custom(old))
        old = plot_of(key)
        custom = key.startswith('custom:')
        if key not in dict(self.views) and not ( custom and groups.is_custom(old) ):
            return False, f'No plot "{old}"'
        if not text:
            if not custom:
                return False, ( 'The plots of the standard groups are not removed (the groups'
                                ' are shown or hidden as a whole, see the groups of plots)' )
            if not groups.shown and groups.custom == [ old ]:
                return False, ( 'The last plot can not be removed, when no group of plots'
                                ' is shown' )
            #(showing the plot before it, or the next for the first):
            keys = [ k for k, _ in self.views if plot_of(k) is not None ]
            k = keys.index(key) if key in keys else 0
            self._current = keys[k-1] if k > 0 else keys[1] if len(keys) > 1 else None
            groups.remove(old)
            self._sync()
            self._restart()
            return True, ''
        try:
            self._parse('plot',text)
        except MCPLError as e:
            return False, str(e)
        if self._same_plot(text,[old]) == old:
            self._current = key#(unchanged)
            return True, ''
        #(the same plot is not there twice among the custom plots):
        same = self._same_plot(text,[ p for p in groups.custom if p != old ])
        h = self._history['plot']
        if not h or h[-1] != text:
            h.append(text)
        title = _doubtful_title(self._title_of(key),old,text)
        if same is None:
            #(changed in its place, or copied after the last custom plot):
            groups.add(text,title,after = old if custom else None)
        if custom:
            groups.remove(old)
        self._sync()
        self._current = f'custom:{same or text}'
        self._restart()
        return True, ''

    def move( self, delta ):
        """Move the shown plot up (delta -1) or down (delta 1) among the custom
        plots (the plots of the standard groups have their places): whether it
        moved"""
        key = self.views[self.current][0]
        if not key.startswith('custom:'):
            return False
        return self.move_to(key[7:],self._groups.custom.index(key[7:]) + delta)

    def move_to( self, plot, index ):
        """Move the custom plot (its histogram string) to the index among the
        custom plots: whether it moved"""
        if not self._groups.is_custom(plot) or not self._groups.move_to(plot,index):
            return False
        self._sync()
        with self._lock:
            self._updates += 1#(the figures are the same, in another order)
        return True

    def set_title( self, plot, title ):
        """Set the title of the custom plot (its histogram string, or the key
        of its view), shown instead of it in the viewers with windows, or
        remove it (an empty title): (ok, message)"""
        plot = plot.removeprefix('custom:')
        if plot.startswith('plot:') or not self._groups.is_custom(plot):
            return False, ( 'The plots of the standard groups keep their titles (a changed'
                            ' plot is copied into the custom group, with its own title)' )
        title = title.strip()
        if title and not title.isprintable():
            return False, 'The title must be a text on one line'
        self._groups.set_title(plot,title)
        with self._lock:
            self._updates += 1#(the figures are the same)
        return True, ''

    def _card_of( self, key ):
        """The title of the plot of the view with the key (given, not from its
        expression, or None) and the key of its group (or None)"""
        custom, plot = key.startswith('custom:'), plot_of(key)
        return next( ( ( t, g ) for p, t, g in self._groups.cards()
                       if p == plot and ( g == custom_key ) == custom ), ( None, None ) )

    def _title_of( self, key ):
        """The title of the plot of the view with the key (see _card_of)"""
        return self._card_of(key)[0]

    def _constant_of( self, plot, constants ):
        """The value of the field of the plot (a histogram string) if all
        particles have the same value (as a text, see the constants of what
        the reading found, and 0 for the fields which the file does not have),
        else None"""
        field = _plot_field(plot)
        return '0' if field in self._absent else constants.get(field) if field else None

    def show_group( self, key, shown = True ):
        """Show (or hide) the standard group with the key: whether it changed
        (an MCPLError is raised for hiding the last group when there are no
        custom plots, as there would be nothing left to show)"""
        groups = self._groups
        if not shown and groups.shown == [ key ] and not groups.custom:
            raise MCPLError('The last group of plots can not be deactivated, when there'
                            ' are no custom plots')
        if not groups.show(key,shown):
            return False
        self._sync()
        if not shown and self._current is not None and self._current not in [ k for k, _ in self.views ]:
            self._current = None
        self._restart()
        return True

    @property
    def groups( self ):
        """The keys of the standard groups shown"""
        return list(self._groups.shown)

    def group_list( self ):
        """The standard groups, as (key, title, whether shown)"""
        return [ ( k, g[0], k in self._groups.shown ) for k, g in _groups.items() ]

    def is_custom( self, plot ):
        """Whether the plot (histogram string) is one of the custom plots"""
        return self._groups.is_custom(plot)

    def plot_info( self, key ):
        """What the viewers with windows show of the view with the key (see
        views), as a dict: the title (if given), the name shown (the title, or
        else its expressions), the histogram string, the group (or None), the
        badges (short texts for its options), the value all particles have
        (for a plot of a field where they all have the same value, else None)
        and whether the field of the plot is absent from the file (see
        _absent)"""
        if plot_of(key) is None:
            ov = dict(self.overviews()).get(key)
            n = len(ov.plots) if ov else 0
            return { 'title' : None, 'name' : 'Overview', 'plot' : None,
                     'group' : ov.title if ov else None,
                     'badges' : [ f'{n} plot{"s" if n != 1 else ""}' ],
                     'constant' : None, 'absent' : False }
        p = plot_of(key)
        title, group = self._card_of(key)
        group = group and title_of(group)
        o = _parsed_plot(p)#(cached, for the cards, which are shown often)
        with self._lock:
            figure = self._figures.get(f'plot:{p}')
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
        #(curves by particle type by default, so only other expressions are
        #noted):
        if _display_by_choice(o) not in ( None, 'single' ):
            badges.append(f'by {o["display_by"]}')
        if o['unweighted']:
            badges.append('counts')
        if o['range'] or o['xrange'] or o['yrange']:
            badges.append('range')
        return { 'title' : title, 'name' : _plot_name(p,title), 'plot' : p,
                 'group' : group, 'badges' : badges,
                 'constant' : self._constant_of(p,constants),
                 'absent' : _plot_field(p) in self._absent }

    def _same_plot( self, text, plots = None ):
        """The plot (of plots, default all) giving the same histogram as the
        text, or None"""
        from ._histstring import _hist_key
        key = _hist_key(text)
        return next( ( p for p in ( self._s.plots if plots is None else plots )
                       if _hist_key(p) == key ), None )

    def _plot_of_exprs( self, text ):
        """The first plot of the expressions of the text, if it has no options,
        or None"""
        from ._expressions import _expr_canonical
        from ._histstring import _hist_exprs
        if ';' in text:
            return None
        exprs = [ _expr_canonical(e) for e in _hist_exprs(text) ]
        return next( ( p for p in self._s.plots
                       if [ _expr_canonical(e) for e in _hist_exprs(p) ] == exprs ), None )

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
        if field == 'groups':
            #(the key of a group after the last comma):
            start = text.rfind(',',0,cursor) + 1
            start += len(text[start:cursor]) - len(text[start:cursor].lstrip())
            return start, [ ( name, d ) for name, d in group_names()
                            if name.startswith(text[start:cursor]) ]
        if field not in ( 'pick', 'edit', 'plot' ):
            return start, []
        options = field == 'plot' and ';' in text[:start]
        #(names of histogram options only after the first ";" of plots, and
        #the statements only in edits):
        groups = ( {'histoptions'} if options else
                   {'fields','vectors','constants','particles','units','functions'}
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
        if field == 'groups':
            cursor = len(text) if cursor is None else cursor
            name = text[text.rfind(',',0,cursor) + 1:].split(',')[0].strip()
            descr = dict(group_names()).get(name)
            return f'{name}  {descr}' if descr else None
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
        """The views, as a list of (key, label): the plots (with their
        histogram strings as labels), in their groups, each after the overview
        of its group (only with multi_overview, see overviews)"""
        with self._lock:
            constants = self._constants
        overviews = dict(self.overviews())
        res = []
        group = None
        for p, _, g in self._groups.cards():
            if g != group:
                group = g
                if f'overview:{g}' in overviews:
                    res.append( ( f'overview:{g}', f'overview: {title_of(g)}' ) )
            #(plots of a field where all particles have the same value are marked):
            c = self._constant_of(p,constants)
            absent = ', absent' if _plot_field(p) in self._absent else ''
            res.append( ( f'{"custom" if g == custom_key else "plot"}:{p}',
                          p if c is None else f'{p} (all {c}{absent})' ) )
        return res

    def overviews( self ):
        """The overviews of the groups shown (only with multi_overview, see
        views), as (view key, Overview), with the keys overview:GROUP"""
        if not self.multi_overview:
            return []
        return [ ( f'overview:{k}', ov ) for k, ov in self._groups.overviews(self.new_plot_cell) ]

    def group_items( self, key ):
        """The plots of the group with the key (histogram strings), with the
        names of their cards in it (their titles in the group, or else from
        their expressions, see plot_info)"""
        with self._lock:
            return [ ( p, _plot_name(p,t) ) for p, t in self._groups.items(key) ]

    def overview_keys( self, key ):
        """The keys of the views of the plots of the cells of the overview with
        the key (in the order of its panels, None for empty cells, and
        info:new for the place of a new plot, see new_plot_cell)"""
        ov = dict(self.overviews()).get(key)
        kind = 'custom' if key == f'overview:{custom_key}' else 'plot'
        return [] if ov is None else [ 'info:new' if k == 'new' else None if p is None
                                       else f'{kind}:{p}' for p, k in zip(ov.cells,ov.kinds) ]

    def _reading_settings( self ):
        """What is read: the settings (see _Reading), with the plots of the
        overviews too"""
        s = super()._reading_settings()
        s.plots = list(dict.fromkeys( s.plots + [ p for _, ov in self._groups.overviews()
                                                  for p in ov.plots ] ))
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
        if key == 'overview':#(the first)
            key = keys[0]
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
            #(the figures are of the plots, see _viewer_reading):
            return self._figures.get(f'plot:{plot_of(key)}')

    def _overview_figure( self, key, ov ):
        """The figure of the overview (made again only when the figures or its
        plots changed, so the same figure is returned until then)"""
        coefficients = self._groups.coefficients(key[9:])
        made_from = ( self._figures, tuple(ov.cells), tuple(ov.kinds), ov.ncols, coefficients )
        old = self._overviews.get(key)
        if old is None or old[0] != made_from:
            self._overviews[key] = old = ( made_from, overview_figure(self._figures,ov,
                                                                     coefficients) )
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
        return f'{self._name}: {count_text(self._ntotal)} particles'

    def _counts_estimated( self ):
        """The counts of the particles used and of those in the range, and the
        sums of their weights, as (n, ntot, w, wtot, exact), or None while they
        are not known. When the plots use only the first particles of the
        range (see cache_info), they are estimated for all particles of the
        range (not exact), with the same fractions."""
        with self._lock:
            counts = self._counts
        if counts is None:
            return None
        n, ntot, w, wtot = counts
        nrange = self.cache_info()['nrange']
        if not ntot or nrange <= ntot:
            return n, ntot, w, wtot, True
        scale = nrange / ntot
        return ( round( n * scale ), nrange, _estimate( w * scale ), _estimate( wtot * scale ),
                 False )

    @property
    def nused( self ):
        """The number of particles used (picked), which are written to new
        files (estimated if the plots use only the first particles of the
        range, see cache_info), or None while not known"""
        c = self._counts_estimated()
        return None if c is None else c[0]

    def nused_text( self, compact = False ):
        """The number of particles used (see nused) as a text (see count_text),
        with \u2248 if it is an estimate, or None while not known"""
        c = self._counts_estimated()
        return None if c is None else ( '' if c[4] else '\u2248' ) + count_text(c[0],compact)

    def counts_text( self, weights = '\u03a3w' ):
        """The numbers of particles used (of those in the range, when picked)
        and the sum of their weights (named weights), as a text, or None while
        they are not known, with the estimates for all particles of the range
        marked with \u2248 (see _counts_estimated)."""
        c = self._counts_estimated()
        if c is None:
            return None
        n, ntot, w, wtot, exact = c
        eq = '=' if exact else '\u2248'
        if self._s.pick is None:
            #(all particles of the range are used, so only the numbers):
            return f'{count_text(ntot)} particles, {weights} {eq} {number_text(w)}'
        pct = f'{100.0*n/ntot:.1f}%' if ntot else '-'
        wpct = f'{100.0*w/wtot:.1f}%' if wtot else '-'
        return ( f'{self.nused_text()}/{count_text(ntot)} particles ({pct}),'
                 f' {weights} {eq} {number_text(w)} ({wpct})' )

def _doubtful_title( title, old, new ):
    """The title of a plot changed from old to new (histogram strings), with
    " (??)" after it if the expressions changed (not just the options, or the
    unit of a field), since the title might no longer fit. Plots without a
    title of their own get the new title from their expression (see
    _auto_title)."""
    from ._expressions import _expr_canonical
    from ._histstring import _hist_exprs
    if title is None or title.endswith('(??)'):
        return title
    def exprs( text ):
        return [ _expr_canonical(e) for e in _hist_exprs(text) ]
    #(the same field in other units, e.g. ekin/MeV for ekin, is the same):
    same_field = _auto_title(old) is not None and _auto_title(old) == _auto_title(new)
    return title if exprs(old) == exprs(new) or same_field else title + ' (??)'

@functools.lru_cache(maxsize = 4096)
def _auto_title( plot ):
    """The title of a plot (histogram string) from its expression, if it is a
    single field, maybe divided by a unit (e.g. Energy for ekin/MeV, and Energy
    per lethargy with the option lethargy), or a field of the userdata, else
    None"""
    import ast

    from ._exprcore import _Expr
    from ._exprsyntax import _Unit
    from ._histstring import _hist_exprs
    exprs = _hist_exprs(plot)
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
    title = _field_titles.get(node.id)
    try:
        lethargy = _parsed_plot(plot)['lethargy']
    except MCPLError:
        lethargy = False
    return f'{title} per lethargy' if title and lethargy else title

@functools.lru_cache(maxsize = 4096)
def _plot_name( plot, title ):
    """The name of the card of the plot: its title, or else from its
    expressions"""
    return title or _auto_title(plot) or ' : '.join(_parsed_plot(plot)['exprs'])

@functools.lru_cache(maxsize = 4096)
def _parsed_plot( text ):
    """The parsed plot (see _parse_hist), cached (so it must not be changed)"""
    from ._histstring import _parse_hist
    return _parse_hist(text)

@functools.lru_cache(maxsize = 4096)
def _plot_field( text ):
    """The field if the plot (a histogram string) is of exactly one field
    (e.g. "z" or "weight;unweighted"), else None"""
    from ._exprcore import _Expr
    exprs = _parsed_plot(text)['exprs']
    return _Expr(exprs[0]).field if len(exprs) == 1 else None

def _estimate( x ):
    """An estimated value, rounded to a whole number if it is large, else to 3
    significant digits"""
    return float(round(x)) if abs(x) >= 100 else float(f'{x:.3g}')

def _parse_count( text ):
    """The integer of a text like 1000, 1,000 or 1e6 (or None if it is not one)"""
    if re.fullmatch(r'[0-9]{1,3}(,[0-9]{3})+',text):
        text = text.replace(',','')
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
    groups of plots to show, separated by commas (e.g. 'spectra,beamz', see
    mcpltool --full-help), the view shown first ('overview', or a plot, e.g.
    'ekin'), or a state of the viewer (as saved in the viewer, a .json file,
    or a dict). In Jupyter the viewer is a panel of widgets, otherwise a
    window, or the terminal with terminal=True (backend chooses the plotting
    backend, e.g. unicode for the terminal); it is shown until closed."""
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
