
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
front ends: the settings (Skip, Limit, Edit, and the plots) with
checking, history, and completion, the views (each plot, and for the front
ends which show several plots at once, the overview of each group of plots)
and their figures, which are computed by reading the
file in a background thread, the state of the viewer (see state()), the
equivalent commands, and writing the edited particles to a new file."""

__all__ = ['view']

import functools
import pathlib
import re

from ._common import MCPLError, _parse_count
from ._histstring import _canonical_hist, _display_by_choice
from ._stdviews import _default_groups, _field_titles, _groups, custom_key
from ._viewer_groups import PlotGroups, group_names, parse_groups, title_of
from ._viewer_output import _as_state, _Output
from ._viewer_overviews import overview_figure
from ._viewer_reading import _make_filler, _Reading, _ReadingState
from ._viewer_ui import count_text, field_names, number_text, plot_of


class _Settings:
    """What is shown: a range of particles in the file, edited, and the plots
    (histogram strings)"""
    def __init__( self, skip = 0, limit = None, edit = None, plots = () ):
        self.skip, self.limit = skip, limit
        self.edit = edit#(a ParticleEdit or None)
        self.plots = list(plots)
    def copy( self ):
        return _Settings(self.skip,self.limit,self.edit,self.plots)
    @property
    def expression( self ):
        """The expression of the edit (None if none)"""
        return self.edit and self.edit.expression

class Viewer(_Output,_Reading):
    """State of the viewer for a file. The front ends show the views (see
    views and figure()), the status (status_lines()), and the fields
    (field_text(), check(), set(), complete(), hint(), history()), and call
    poll() regularly to find out if the figures were updated by the reading
    in the background (started by start())."""

    def __init__( self, filename, skip = 0, limit = None, edit = None,
                  state = None, dry_run = False, progname = 'mcpltool' ):
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
        self._texts = { 'skip' : '', 'limit' : '', 'edit' : '', 'plot' : '' }
        #(the statements of the edit, as (text, active), where the inactive
        #ones are switched off in the Compose window, see edit_lines):
        self._edit_lines = []
        self._history = { f : [] for f in field_names }
        self._s = _Settings()
        #(the plots, in groups, with those of the fields of the userdata in the
        #group of the fields, see _viewer_groups):
        self._groups = PlotGroups({ 'fields' : self._userdata_items() })
        self._sync()
        #(what the reading thread shares with the viewer, whose lock also
        #guards the groups, see _viewer_reading):
        self._rs = _ReadingState()
        self._lock = self._rs.lock
        #(the last change of toggle_scale, which the same key undoes: the
        #option, the view key after the change, the plot before, the view key
        #before, and whether a plot of a standard group was copied):
        self._scale_undo = None
        self._seen, self._status_seen, self.plot_changed = -1, 0, True
        self._thread = None
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
        #The state (see state()) is applied before the other arguments (so
        #these can change it):
        view = None
        if state is not None:
            state = _as_state(state)
            self._loading = True
            try:
                self._apply_state(state)
            finally:
                self._loading = False
            view = state.get('view')
        for field, value in ( ('skip',skip), ('limit',limit), ('edit',edit) ):
            if value not in ( None, '', 0 ):
                self._set_or_raise(field,str(value))
        self._current = self._view_key(view) if view else None

    def _sync( self ):
        """The plots of the settings (shown as views) from the groups"""
        self._s.plots = [ p for p, _, _ in self._groups.cards() ]

    def _on_found( self, found ):
        """After a reading (in the thread of the front end, see
        _apply_found): the defaults of the settings of the groups depend on
        what it found (see PlotGroups.setting), so their plots are read if
        they changed"""
        if found == self._groups.found:
            return
        before = self._reading_settings().plots
        with self._lock:
            self._groups.found = found
            self._sync()
            self._rs.updates += 1#(e.g. the correlation coefficients are new)
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
            raise MCPLError(f'Unknown view "{view}" (the views are: overview,'
                            f' overview:GROUP with the groups {", ".join(_groups)},'
                            ' or a plot, e.g. ekin)')
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

    def check_start( self, text ):
        """As check for the edit, of its first statements (the variables of
        which may be unused)"""
        from ._expressions import _EditStart
        try:
            self._check_userdata(text.strip())
            _EditStart(text)
        except MCPLError as e:
            return False, str(e)
        return True, ''

    def _parse( self, field, text ):
        text = text.strip()
        if field == 'edit' or ( field == 'plot' and not self._loading ):
            self._check_userdata(text)
        if field in ('skip','limit'):
            if not text or ( field == 'limit' and text == 'all' ):
                return 0 if field == 'skip' else None
            v = _parse_count(text)
            if v is None or v < 0:
                raise MCPLError(f'{field.capitalize()} must be a number of particles'
                                + ( ' (or all)' if field == 'limit' else '' ))
            return None if field == 'limit' and v == 0 else v
        if field == 'edit':
            if not text:
                return None
            from ._expressions import ParticleEdit
            e = ParticleEdit(text)
            return e if e.expression else None#(None with only inactive statements)
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
            #(new plots are custom plots, see _viewer_groups, in their
            #canonical forms, and the same custom plot written differently is
            #not added again):
            same = self._same_plot(text,self._groups.custom)
            if same is None:
                same = _canonical_hist(text)
                self._groups.add(same)
                self._sync()
            self._current = f'custom:{same}'
        elif field == 'groups':
            self._groups.use(value)
            self._sync()
            self._current = None
        else:
            #(the reading is not restarted for the same value, e.g. an
            #expression written differently):
            if field == 'edit':
                self._texts[field] = self._set_edit_lines(text)
                same = ( value and value.expression ) == self._s.expression
            else:
                self._texts[field] = text
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

    def _set_edit_lines( self, text ):
        """Set the statements of the edit (see edit_lines) from the text, which
        has inactive statements when it comes from a saved state; else those
        of the edit before are kept at their places. Returns the text of the
        active statements."""
        from ._expr_str2ast import _expr_statements
        lines = _expr_statements(text) if text.strip() else []
        if all( active for _, active in lines ):
            for i, ( st, active ) in enumerate(self._edit_lines):
                if not active:
                    lines.insert(min(i,len(lines)),( st, False ))
            self._edit_lines = lines
            return text
        self._edit_lines = lines
        return '; '.join( st for st, active in lines if active )

    @property
    def edit_lines( self ):
        """The lines of the edit, as (text, active), where a line has one or
        more statements, and the inactive ones are those switched off in the
        Compose window"""
        return list(self._edit_lines)

    def set_edit_lines( self, lines ):
        """Apply the lines of the edit (as (text, active), see edit_lines):
        (ok, message)"""
        lines = [ ( text.strip(), active ) for text, active in lines if text.strip() ]
        old, self._edit_lines = self._edit_lines, []
        res = self.set('edit','; '.join( st for st, active in lines if active ))
        self._edit_lines = list(lines) if res[0] else old
        return res

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
        if plot_of(old) is None:
            #(a custom plot also when written differently, see set):
            try:
                old = self._same_plot(old,groups.custom) or old
            except MCPLError:
                pass#(invalid, so not a plot, see below)
            key = self._key_of(old,groups.is_custom(old))
        else:
            key = old
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
        if same is None:
            #(changed in its place, or copied after the last custom plot):
            same = _canonical_hist(text)
            groups.add(same,after = old if custom else None)
        if custom:
            groups.remove(old)
        self._sync()
        self._current = f'custom:{same}'
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
            self._rs.updates += 1#(the figures are the same, in another order)
        return True

    def _card_of( self, key ):
        """The title of the plot of the view with the key (given, not from its
        expression, or None) and the key of its group (or None)"""
        custom, plot = key.startswith('custom:'), plot_of(key)
        return next( ( ( t, g ) for p, t, g in self._groups.cards()
                       if p == plot and ( g == custom_key ) == custom ), ( None, None ) )

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
            figure = self._rs.figures.get(f'plot:{p}')
            constants = self._rs.constants
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
        list of (text to insert, short description): the names starting with
        it, followed by those with a later part (after a "_") starting with it
        (e.g. through_sphere for "sph")."""
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
        if field not in ( 'edit', 'plot' ):
            return start, []
        options = field == 'plot' and ';' in text[:start]
        #(names of histogram options only after the first ";" of plots, and
        #the statements only in edits):
        groups = ( {'histoptions'} if options else
                   {'fields','vectors','constants','particles','units','functions'}
                   | ( {'statements'} if field == 'edit' else set() ) )
        res, later = [], []
        for group, name, short, _ in _hints:
            if group not in groups or name.startswith('userdata.'):#(see below)
                continue
            base = re.match(r'[A-Za-z_][A-Za-z0-9_]*', name).group(0)
            if base.startswith(prefix):
                found = res
            elif prefix and any( p.startswith(prefix) for p in base.split('_')[1:] ):
                found = later
            else:
                continue
            insert = base + ( '(' if '(' in name else ( '=' if '=' in name else '' ) )
            if insert not in [ r[0] for r in res + later ]:
                found.append( ( insert, short ) )
        res += later
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
        or else of the function whose arguments are written there, with its
        parameters (as "f(a,b)  description"), or None"""
        from ._exprhelp import _call_hint, _short_hint
        if field == 'groups':
            cursor = len(text) if cursor is None else cursor
            name = text[text.rfind(',',0,cursor) + 1:].split(',')[0].strip()
            descr = dict(group_names()).get(name)
            return f'{name}  {descr}' if descr else None
        cursor = len(text) if cursor is None else cursor
        if not self._ud_fields and re.search(r'\buserdata\.[A-Za-z0-9_]*$', text[:cursor]):
            return 'userdata.  there are no userdata fields in this file'
        m = re.search(r'[A-Za-z_][A-Za-z0-9_]*$', text[:cursor])
        if m:
            rest = re.match(r'[A-Za-z0-9_]*', text[cursor:]).group(0)
            name = m.group(0) + rest
            short = _short_hint(name)
            if short:
                return f'{name}  {short}'
        return _call_hint(text[:cursor]) if field in ( 'edit', 'plot' ) else None

    #Views:

    @property
    def views( self ):
        """The views, as a list of (key, label): the plots (with their
        histogram strings as labels), in their groups, each after the overview
        of its group (only with multi_overview, see overviews)"""
        with self._lock:
            constants = self._rs.constants
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
            return self._rs.figures.get(f'plot:{plot_of(key)}')

    def _overview_figure( self, key, ov ):
        """The figure of the overview (made again only when the figures or its
        plots changed, so the same figure is returned until then)"""
        #(those of the particles in the figures, also while they are read):
        coefficients = self._groups.coefficients(key[9:],self._rs.correlations)
        made_from = ( self._rs.figures, tuple(ov.cells), tuple(ov.kinds), ov.ncols, coefficients )
        old = self._overviews.get(key)
        if old is None or old[0] != made_from:
            self._overviews[key] = old = ( made_from, overview_figure(self._rs.figures,ov,
                                                                     coefficients) )
        return old[1]

    def status_lines( self, weights = '\u03a3w' ):
        """The two status lines: the file, the numbers of particles and the sum
        of their weights (named weights, see counts_text), and the progress of
        the reading (or an error)"""
        with self._lock:
            progress, error = self._rs.progress, self._rs.error
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
        """The counts of the particles used and of those in the range, the
        sums of their weights, and the counts after each statement of the edit,
        as (n, ntot, w, wtot, exact, statements), or None while they are not
        known. When the plots use only the first particles of the
        range (see cache_info), they are estimated for all particles of the
        range (not exact), with the same fractions."""
        with self._lock:
            counts = self._rs.counts
        if counts is None:
            return None
        n, ntot, w, wtot, stcounts = counts
        nrange = self.cache_info()['nrange']
        if not ntot or nrange <= ntot:
            return n, ntot, w, wtot, True, stcounts
        scale = nrange / ntot
        return ( round( n * scale ), nrange, _estimate( w * scale ), _estimate( wtot * scale ),
                 False, tuple( round( c * scale ) for c in stcounts ) )

    def edit_line_counts( self ):
        """The numbers of particles left after the lines of the edit (see
        edit_lines) as texts (see nused_text), None for inactive lines, or None
        while not known"""
        from ._expr_str2ast import _split_statements
        c = self._counts_estimated()
        if c is None:
            return None
        sizes = [ len(_split_statements(text)) if active else 0 for text, active in self._edit_lines ]
        if sum(sizes) != len(c[5]):
            return None
        mark = '' if c[4] else '\u2248'
        res, end = [], 0
        for n in sizes:
            end += n
            res.append( mark + count_text(c[5][end-1]) if n else None )
        return res

    @property
    def nused( self ):
        """The number of particles used (kept by the edit), which are written
        to new files (estimated if the plots use only the first particles of the
        range, see cache_info), or None while not known"""
        c = self._counts_estimated()
        return None if c is None else c[0]

    def nused_text( self ):
        """The number of particles used (see nused) as a text (see count_text),
        with \u2248 if it is an estimate, or None while not known"""
        c = self._counts_estimated()
        return None if c is None else ( '' if c[4] else '\u2248' ) + count_text(c[0])

    def counts_text( self, weights = '\u03a3w' ):
        """The numbers of particles used (of those in the range, when the edit
        has conditions)
        and the sum of their weights (named weights), as a text, or None while
        they are not known, with the estimates for all particles of the range
        marked with \u2248 (see _counts_estimated)."""
        c = self._counts_estimated()
        if c is None:
            return None
        n, ntot, w, wtot, exact, _ = c
        eq = '=' if exact else '\u2248'
        if self._s.edit is None or not self._s.edit._has_conditions:
            #(all particles of the range are used, so only the numbers):
            return f'{count_text(ntot)} particles, {weights} {eq} {number_text(w)}'
        pct = f'{100.0*n/ntot:.1f}%' if ntot else '-'
        wpct = f'{100.0*w/wtot:.1f}%' if wtot else '-'
        return ( f'{self.nused_text()}/{count_text(ntot)} particles ({pct}),'
                 f' {weights} {eq} {number_text(w)} ({wpct})' )

@functools.lru_cache(maxsize = 4096)
def _auto_title( plot ):
    """The title of a plot (histogram string) from its expression, if it is a
    single field, maybe divided by a unit (e.g. Energy for ekin/MeV, and Energy
    per lethargy with the option lethargy), or a field of the userdata, else
    None"""
    from ._expr_ast import Binary, Name, Unit, Userdata
    from ._expressions import _Expr
    from ._histstring import _hist_exprs
    exprs = _hist_exprs(plot)
    if len(exprs) != 1:
        return None
    try:
        node = _Expr(exprs[0]).tree.expr
    except MCPLError:#(e.g. while a plot is written, see WindowLogic.compose)
        return None
    if isinstance(node,Binary) and node.op == '/' and isinstance(node.right,Unit):
        node = node.left
    if isinstance(node,Userdata) and node.index is None:
        return f'Userdata {node.field}'
    if not isinstance(node,Name):
        return None
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
    from ._expressions import _Expr
    exprs = _parsed_plot(text)['exprs']
    return _Expr(exprs[0]).field if len(exprs) == 1 else None

def _estimate( x ):
    """An estimated value, rounded to a whole number if it is large, else to 3
    significant digits"""
    return float(round(x)) if abs(x) >= 100 else float(f'{x:.3g}')

def view( filename, *, edit = None, skip = 0, limit = None,
          state = None, terminal = False ):
    """Show the particles of a file in the viewer: an overview and plots of
    the particles in a range of the file (after skipping skip particles, at
    most limit particles), after the edit (an edit expression or a
    ParticleEdit), which can all be changed in the viewer. The viewer starts in the state if given (as
    saved in the viewer: a .json file, its JSON text, or a dict). It is shown
    in a window (with Tk, the plots drawn with matplotlib), or in the terminal
    with terminal=True (with curses, the plots drawn as text), until it is
    closed."""
    def text( e ):
        return e if e is None or isinstance(e,str) else e.expression
    v = Viewer(filename,skip=skip,limit=limit,edit=text(edit),
               state=state)
    _run_viewer(v,terminal)

def _run_viewer( viewer, terminal = False, color = None,
                 hint = 'Use terminal=True for the viewer in the terminal.' ):
    """Run the viewer until it is closed: in a window (with Tk), or in the
    terminal if terminal is True (with the plots drawn with unicode, or else
    ascii, characters, in colour as set by color, see _plotting.show).
    When no window can be opened, the error message ends with the hint."""
    if terminal:
        from ._plotregistry import _show_backend
        from ._viewer_curses import run_viewer
        run_viewer(viewer,_show_backend(True,color=color))
        return
    from ._viewer_tk import _root, run_viewer
    root = _root()
    if root is None:
        raise MCPLError('The viewer can not open a window here (it needs tkinter and a'
                        f' display). {hint}')
    run_viewer(viewer,root)
