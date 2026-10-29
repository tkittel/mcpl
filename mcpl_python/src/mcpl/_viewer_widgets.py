
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

"""The viewer in a window, independent of the GUI toolkit (Tk, see _viewer_tk):
what happens when the fields, the views and the actions are used
(WindowLogic), and what the toolkit must show (WindowFrontend). The logic is
tested without a display, with a front end which prints what it is asked to
show (see the test pyviewer_widgets). The plot is a matplotlib figure,
embedded in the window by the toolkit."""

__all__ = []

from . import _viewer_ui as ui
from ._common import MCPLError
from ._stdviews import _groups, custom_key, custom_title


def _axes_problem( axes ):
    """What is wrong with the expressions of the axes (x, y, z), or None: each
    field has one expression ("x : y" is written in the plot expression), and
    a z axis needs a y axis"""
    if any( ':' in a for a in axes ):
        return ( 'Each axis has one expression: use the fields of the Y and Z axes for 2D'
                 ' histograms and 3D plots (or "Advanced" for the plot expression)' )
    if axes[2] and not axes[1]:
        return 'Choose the Y axis too for a 3D plot (or empty the Z axis)'
    return None


class Card:
    """A card of the list of views of the viewer in a window (see
    WindowLogic.cards), which the front end shows: the name, the group (if grouped, else it is shown without a group header),
    the badges of the options of the plot, a short status for
    compact cards (e.g. "all 0" for fields with one value, or "not in this
    file"), the problem of a plot which failed, and whether it has an image
    (see WindowLogic.thumbnail), can be selected (shown), dragged (moved)
    and removed (see WindowLogic.on_remove, with remove_text saying what
    that does, if not just removing the card), whether it is shown also
    when its group is folded (pinned), whether it is the overview of its
    group (overview, shown differently from the plots), and whether it is the
    card of an inactive group (inactive, see WindowLogic.cards). The key is
    that of the view, or starts with info: for cards which are not views.
    The title (if given) and the plot (histogram string) of plots are not
    used by the front end, but by tests."""
    __slots__ = (
        'badges',
        'draggable',
        'group',
        'grouped',
        'image',
        'inactive',
        'key',
        'name',
        'overview',
        'pinned',
        'plot',
        'problem',
        'removable',
        'remove_text',
        'selectable',
        'status',
        'title' )

    def __init__( self, key, name, *, title = None, plot = None, group = None,
                  grouped = False, badges = (), status = None, problem = None,
                  image = False, selectable = True, draggable = False, removable = False,
                  pinned = False, remove_text = None, inactive = False, overview = False ):
        self.key, self.name, self.title, self.plot = key, name, title, plot
        self.pinned, self.remove_text, self.inactive = pinned, remove_text, inactive
        self.overview = overview
        self.group, self.grouped, self.badges = group, grouped, list(badges)
        self.status, self.problem, self.image = status, problem, image
        self.selectable, self.draggable, self.removable = selectable, draggable, removable

    @property
    def compact( self ):
        """Whether the card only shows its name and status"""
        return self.status is not None

    def _values( self ):
        return tuple( getattr(self,n) if n != 'badges' else tuple(self.badges)
                      for n in self.__slots__ )

    def __eq__( self, other ):
        return isinstance(other,Card) and self._values() == other._values()

    def __hash__( self ):
        return hash(self._values())

    def __repr__( self ):
        return f'Card({self.key!r}, {self.name!r})'

class WindowFrontend:
    """The front end of the viewer in a window (with the widgets of a GUI
    toolkit, see _viewer_tk), which shows what WindowLogic asks it to with
    these methods, and calls the on_* methods of WindowLogic when its widgets
    are used. The methods without a default must be implemented."""

    def show_views( self, cards ):
        """Show the views as cards (see cards()), with the one shown (see
        shown_key and shown_group) selected"""
        raise NotImplementedError

    def show_status( self, first, second ):
        """Show the two status lines (see Viewer.status_lines)"""
        raise NotImplementedError

    def show_field( self, field, text ):
        """Set the text of the field (without calling on_field_edited)"""
        raise NotImplementedError

    def show_plot_field( self, text, title, axes ):
        """Set the texts of the fields of the shown plot: its histogram string,
        its title and the expressions of its axes (x, y, z), or disable them if
        text is None (the shown view is not a plot). For a new plot (see
        on_new_plot), they are empty but for the title."""
        raise NotImplementedError

    def show_line( self, text, style ):
        """Show the line below the fields, with the style 'normal', 'dim',
        'ok' or 'error' (see _viewer_ui.hint_line)"""
        raise NotImplementedError

    def show_controls( self, controls ):
        """Show the settings of the shown plot (see plot_controls), or none
        (if controls is None)"""
        raise NotImplementedError

    def show_overview_controls( self, controls ):
        """Show the settings of the shown overview (see overview_controls), or
        none (if controls is None)"""

    def show_title( self, filename ):
        """Show the name of the file (e.g. in the title of the window)"""

    def show_enabled( self, action, enabled ):
        """Show the button of the action as enabled or not (if the toolkit has
        such buttons)"""

    def show_check( self, field, ok ):
        """Mark the text of the field being edited as valid or not (ok is None
        for no mark)"""
        raise NotImplementedError

    def show_colour_bar_menu( self, entries ):
        """Show the menu of the colour bar (see colour_bar_menu), where choosing
        an entry calls on_control('logz',shown) with its shown text (if the
        toolkit has menus)"""

    def show_pending( self, field, pending ):
        """Show whether the field has a text which is not applied yet (e.g.
        with a button applying it, if the toolkit has such buttons)"""

    def draw_plot( self ):
        """Redraw the canvas of the figure (it changed)"""
        raise NotImplementedError

    def focus_field( self, field ):
        """Move the keyboard focus to the text field (field is 'shown_plot' for
        the field of the shown plot, and 'x_axis' for its x axis)"""
        raise NotImplementedError

    def ask_file( self, action ):
        """Ask for the name of the file to write ('write') or to save the state
        of the viewer in ('state'), and call on_file with it"""
        raise NotImplementedError

    def show_help( self ):
        """Show the help of the viewer (ui.help_blocks)"""
        raise NotImplementedError

    def close_window( self ):
        """Close the window (on_close is then called)"""
        raise NotImplementedError

class WindowLogic:
    """The logic of the viewer in a window, for the viewer core v: the front
    end (see WindowFrontend) creates the widgets (the cards of the views, the
    status, the plot, the fields of the shown plot: title, axes, settings and
    plot expression, the settings of overviews, the fields of skip, limit,
    pick and edit, a line for messages, and the actions), shows what this
    asks it to, and calls the on_* methods when its widgets are used. fig is
    the matplotlib figure of the plot."""

    def __init__( self, viewer, frontend, fig ):
        from ._viewer_figure import FigurePane
        self.frontend = frontend
        self.fig = fig
        self._attach(viewer)
        #(with smaller fonts in small windows, e.g. on laptops):
        self.pane = FigurePane(fig,( 0.08, 0.98, 0.11, 0.93 ),title_space=0.05,
                               title_y=0.98,scale_fonts=True)
        self._histories = {}#field -> ui.History, while it is edited
        self._thumbnails = {}#view key -> (figure, PNG data, time)
        self._removed = set()#(the cards removed which are not views, see cards)
        self._new_plot = None#(the title of a new plot, while it has no axes, see on_new_plot)
        self._empty = None#(the view and message shown instead of its plot, see refresh)
        #(when the plot was drawn, how long it took, and whether a newer figure
        #is not drawn yet, see on_timer):
        self._drawn_at, self._draw_time, self._plot_pending = 0.0, 0.0, False
        self.closed = False
        #(whether the group of the shown view is expanded, see folded_groups;
        #not at the start, when all groups are folded):
        self._expanded = False
        self._browsed = None#(the title of the group of the card chosen last)

    def help_topics( self ):
        """The topics of the help menu of the viewers with windows, as (label,
        title, blocks, see _helptext): the viewer, the expressions of picks, edits and plots (as
        mcpltool -p help, -E help and -H help), the cache, and MCPL itself"""
        from ._exprhelp import _help_blocks
        return [ ( 'The viewer', 'The viewer', ui.help_blocks ),
                 ( 'Picks (filtering particles)', 'Picks', _help_blocks('pick') ),
                 ( 'Edits (modifying particles)', 'Edits', _help_blocks('edit') ),
                 ( 'Plot expressions', 'Plot expressions', _help_blocks('hist') ),
                 ( 'About data caching', 'Data caching', ui.cache_blocks ),
                 ( 'About MCPL', 'About MCPL', ui.about_blocks() ) ]

    #Called by the toolkit:

    def start( self ):
        self.v.start()
        for field, *_ in ui.fields:
            self.frontend.show_field(field,self.v.field_text(field))
        self.refresh()

    def on_timer( self ):
        """To be called regularly (e.g. every 0.2 s), while the file is read.
        While it is read, the plot is only drawn again when some time passed
        (0.5 s, or 3 times as long as drawing it took, if longer), so the
        window stays responsive."""
        import time
        if self.closed:
            return
        changed = self.v.poll()
        if not ( changed or self._plot_pending ):
            return
        #(updates of only the progress do not draw the plot again):
        new = self.v.plot_changed or self._plot_pending
        reading = self.v.reading
        wait = max( 0.5, 3 * self._draw_time )
        late = time.monotonic() - self._drawn_at >= wait
        self.refresh(plot = new and ( late or not reading ))
        self._plot_pending = new and reading and not late

    def on_close( self ):
        if not self.closed:
            self.closed = True
            self.v.stop()

    def on_select( self, index ):
        self._new_plot = None#(a new plot without axes is given up)
        self._expanded = True
        self.v.select(index)
        self.refresh()

    def on_select_key( self, key, group = None ):
        """The view with the key was chosen, from its card in the group (with
        the title) if given (a plot can have cards in several groups, see
        cards)"""
        if key.startswith('info:group:'):
            #(the card of an inactive group activates it, see cards):
            self.on_show_group(key[11:])
            return
        #(choosing a view expands its group, and choosing the overview of the
        #expanded group again folds it):
        self._expanded = not ( key.startswith('overview:') and key == self.shown_key
                               and self._expanded )
        self._new_plot = None
        self._browsed = group
        self.v.select_key(key)
        self.refresh()

    def on_group_header( self, title ):
        """The header of a group was clicked: its overview is shown (which
        expands the group, or folds it if it was expanded, see on_select_key)"""
        key = next( ( k for k, ov in self.v.overviews() if ov.title == title ), None )
        if key is not None:
            self.on_select_key(key)

    def folded_groups( self, cards = None ):
        """The titles of the groups which are folded (showing only their
        overview): the standard groups except that of the shown view (see
        shown_group, of the cards, default cards()), if it is expanded (see
        on_select_key; the custom plots are never folded)"""
        shown = ( self.shown_group(self.cards() if cards is None else cards)
                  if self.shown_key and self._expanded else None )
        return { t for k, t, active in self.v.group_list() if active and t != shown }

    def shown_group( self, cards ):
        """The title of the group whose card of the shown view is selected (of
        the cards, see cards): that of the group of the card chosen last, if
        the view has a card there, else of its first card"""
        groups = [ c.group for c in cards if c.key == self.shown_key ]
        return self._browsed if self._browsed in groups else next(iter(groups),None)

    def on_move( self, delta ):
        if self.v.move(delta):
            self.refresh()

    def on_click( self, event ):
        """A click in the figure (a matplotlib event): on a plot of the overview,
        it is shown on its own, and on the colour bar of a 2D histogram, a menu
        of its colour scales is shown (see colour_bar_menu)"""
        key = self.pane.view_at(event)
        if key == 'info:new':#(the place of a new plot in the custom overview)
            self.on_new_plot()
        elif key is not None:
            #(the plot is shown in the group of the overview):
            self._browsed = self.v.plot_info(self.shown_key)['group'] if self.shown_key else None
            self._expanded = True
            self.v.select_key(key)
            self.refresh()
        elif self.pane.on_colour_bar(event) and self.colour_bar_menu():
            self.frontend.show_colour_bar_menu(self.colour_bar_menu())

    #The particles kept in memory (see Viewer.cache_info and the texts in
    #_viewer_ui):

    def on_cache_limit( self, limit ):
        """Set the cache limit (bytes, or None for no cache, see ui.cache_menu)"""
        self.v.set_cache_limit(limit)
        self.frontend.show_line(ui.cache_line(self.v.cache_info()),'normal')
        self.refresh(plot = False)

    def colour_bar_menu( self ):
        """The entries of the menu of the colour bar of the shown 2D histogram,
        as (label, whether it is used, the shown text of the setting, see
        on_control), or an empty list for other views"""
        controls = self.plot_controls()
        if controls is None or controls[0] != '2d':
            return []
        _, _, choices, shown, _ = next( c for c in controls[1] if c[0] == 'logz' )
        labels = { 'log' : 'Logarithmic colour scale', 'linear' : 'Linear colour scale' }
        return [ ( labels.get(c,c), c == shown, c ) for c in choices ]

    def on_title( self, text ):
        """The title of the shown plot is set (an empty text removes it)"""
        if self._new_plot is not None:
            self._new_plot = text#(for when it is added)
            self.refresh(plot = False)
            return
        key = self._shown_key()
        if key is not None:
            ok, msg = self.v.set_title(key,text)
            self.frontend.show_line(msg,'normal' if ok else 'error')
            self.refresh(plot = False)

    def on_show_group( self, key, shown = True ):
        """Show (or hide) the standard group of plots with the key (see
        Viewer.show_group)"""
        try:
            changed = self.v.show_group(key,shown)
        except MCPLError as e:
            self.frontend.show_line(str(e),'error')
            return
        if changed:
            title = { k : t for k, t, _ in self.v.group_list() }[key]
            self.frontend.show_line(f'{"Activated" if shown else "Deactivated"}: the group {title}','normal')
            if shown:
                self._expanded = True#(the group shown is expanded, see folded_groups)
                self.v.select_key(f'overview:{key}')
        self.refresh()

    def group_key( self, title ):
        """The key of the standard group with the title, or None"""
        return next( ( k for k, t, _ in self.v.group_list() if t == title ), None )

    def on_drop( self, key, target ):
        """A card was dragged onto the card of the view with the key target
        (None: before the first custom plot): the custom plot of the view with
        the key is moved there (only custom plots are reordered)"""
        plots = [ k for k, _ in self.v.views if k.startswith('custom:') ]
        if key in plots and ( target is None or target in plots ):
            self.v.move_to(key[7:],0 if target is None else plots.index(target))
        else:
            self.frontend.show_line('Only the custom plots are reordered','error')
        self.refresh(plot = False)

    #The settings of the shown plot and of overviews:

    def plot_controls( self, plot = None ):
        """The settings of the plot (default the shown one) as (kind, controls),
        where controls are (option, label, the texts of its choices, or None for
        a text field, the shown text, and the text shown greyed in an empty
        text field: what is used, e.g. the numbers of bins), see
        _viewer_ui.plot_controls, or None if the shown view is not a plot
        (another plot is given only by tests)"""
        from ._histstring import _hist_parts, _parse_hist
        plot = plot or self._shown_plot()
        if plot is None:
            return None
        try:
            o = _parse_hist(plot)
        except MCPLError:#(e.g. while it is composed, see compose)
            return None
        kind = { 2 : '2d', 3 : '3d' }.get(len(o['exprs']),'bar' if o['bar'] else '1d')
        given = dict(_hist_parts(plot)[1])
        res = []
        for name, label, choices in ui.plot_controls[kind]:
            choices = self._choices(choices)
            v = given.get(name,False)
            #(the option given without a value, or with 1, is True, and 0 is
            #as if not given, except for those which are on by default):
            if name in ui.on_by_default:
                value = '0' if v == '0' else None
            else:
                value = None if v is False or v == '0' else True if v in ( None, '1' ) else v
            if choices is None:
                shown = '' if value in ( None, True ) else value
            else:
                shown = next( ( t for t, cv in choices if cv == value ), value )
            res.append( ( name, label, [ t for t, _ in choices ] if choices else None, shown,
                          self._used(plot,name) ) )
        return kind, res

    def _used( self, plot, name ):
        """What the drawn plot uses for the option (if it is not given): the
        numbers of bins ("40", or "40,30" for 2D histograms) or of the points
        of 3D plots, as a text, or an empty text (also while it is not
        drawn)"""
        items = self._plot_items(f'plot:{plot}')#(the same for custom plots)
        if name == 'points':
            n = sum( len(item.x) for item in items if hasattr(item,'z') )
            return str(n) if n else ''
        for item in ( items if name == 'bins' else () ):
            if hasattr(item,'xedges'):
                return f'{len(item.xedges)-1},{len(item.yedges)-1}'
            if hasattr(item,'edges'):
                return str(len(item.edges)-1)
        return ''

    def _option( self, plot, name, shown ):
        """The plot with the option set from the shown text of its control"""
        from ._histstring import _hist_set_option
        choices = self._choices(next( ( c for n, _, c in sum( ui.plot_controls.values(), () )
                                        if n == name ), None ))
        text = shown.strip()
        if choices is not None:
            value = dict(choices).get(text,text or None)
        else:
            #(an empty number of bars is the default number):
            value = text or ( True if name == 'bar' else None )
        return _hist_set_option(plot,name,value)

    def _choices( self, choices ):
        """The choices of a setting of plots (see _viewer_ui.plot_controls), as
        (shown text, value), with those of the particle types"""
        from ._particles import _particle_display_only
        if choices != 'types':
            return choices
        return [ ( t, _particle_display_only(pdg) ) for t, pdg in self.type_choices() ]

    def type_choices( self ):
        """The choices of particle types (see Viewer.found), as (shown text,
        PDG code), the first for all (None)"""
        from ._particles import _particle_text
        types = self.v.found['types']
        total = sum( w for _, w in types ) or 1.0
        return [ ( ui.particle_type_text(None,1.0), None ) ] + [
            ( ui.particle_type_text(_particle_text(pdg),w / total), pdg ) for pdg, w in types ]

    def overview_controls( self ):
        """The settings of the shown overview, if it is that of a standard group
        (else None), as a list of (name, label, choices, shown): for a menu
        (the particle type, and what the plots show a curve of each value
        of), the texts of its choices and the chosen one, for
        toggles (the variables of correlation plots), the texts of the toggles and
        those which are on, and for the button choosing the most correlated
        variables (or all again, if they are shown), its text"""
        key = self._shown_group()
        if key is None or not self.v.group_settings(key):#(e.g. of custom plots)
            return None
        found = self.v.found
        res = []
        for name, value, choices in self.v.group_settings(key):
            if name == 'display_only':
                types = { pdg : t for t, pdg in self.type_choices() }
                texts = [ types.get(c,str(c)) for c in choices ]
                shown = types.get(value,str(value))
            elif name == 'display_by':
                by = { v or 'pdgcode' : t for t, v in ui.display_by_choices }
                texts, shown = [ by[c] for c in choices ], by[value]
            else:
                texts = [ ui.variable_text(c,found['constants'].get(c)) for c in choices ]
                shown = [ t for t, c in zip(texts,choices) if c in value ]
            res.append( ( name, ui.overview_controls[name], texts, shown ) )
            if name == 'variables':
                most = value == self.v.most_correlated(key)
                text = ui.all_variables if most else ui.most_correlated
                res.append( ( 'most', None, [ text ], text ) )
        return res

    def on_overview_control( self, name, shown ):
        """A setting of the shown overview was changed: a menu (to its shown
        text), or a variable (the text of its toggle) was
        turned on or off, or the button (name most) choosing the variables
        with the strongest correlations, or all again, was clicked"""
        key = self._shown_group()
        if key is None:
            return
        if name == 'most':
            value = self.v.most_correlated(key) if shown == ui.most_correlated else None
            if value is None and shown == ui.most_correlated:
                self.frontend.show_line('The correlations are known when the file is read','error')
            elif value is not None and len(value) < 2:
                self.frontend.show_line('Fewer than two of the variables have more than one value','error')
            else:
                try:
                    self.v.set_group_setting(key,'variables',value)
                    self.frontend.show_line(f'Variables: {", ".join(self.v.group_setting(key,"variables"))}',
                                   'normal')
                except MCPLError as e:#(e.g. when only one of them varies)
                    self.frontend.show_line(str(e),'error')
            self.refresh()
            return
        controls = { n : ( texts, now ) for n, _, texts, now in self.overview_controls() }
        texts, now = controls[name]
        choices = { n : c for n, _, c in self.v.group_settings(key) }[name]
        if name in ( 'display_only', 'display_by' ):
            value = choices[texts.index(shown)]
        else:
            on = set(now) ^ { shown }
            value = [ c for t, c in zip(texts,choices) if t in on ]
        try:
            self.v.set_group_setting(key,name,value)
        except MCPLError as e:
            self.frontend.show_line(str(e),'error')
        self.refresh()

    def _shown_group( self ):
        """The key of the group whose overview is shown, if any"""
        return ui.group_of(self._selected_key())

    def on_control( self, name, shown ):
        """A setting of the shown plot was changed (to the shown text)"""
        plot = self._shown_plot()
        if plot is None:
            return
        done, msg, replot = ui.apply_text(self.v,'plot',self._option(plot,name,shown),
                                          replaces = self._shown_key())
        self.frontend.show_line(msg,'normal' if done else 'error')
        self.refresh(plot = replot)

    def on_control_edited( self, name, text ):
        """The expression written in a setting of the shown plot (one of
        ui.written_options) was changed: it is checked as the plot with it,
        with hints as in its field"""
        plot = self._shown_plot()
        if plot is None:
            return
        _, hint, field = ui.written_options[name]
        text = text.strip()
        if not text:
            self.frontend.show_line(hint,'dim')
            return
        try:
            ok, msg = ui.check_text(self.v,'plot',self._option(plot,name,text),
                                    replaces = self._shown_key())
        except MCPLError as e:
            ok, msg = False, str(e)
        if not ok:
            #(the problem of the expression itself, if any, as in its field):
            ok_field, msg_field = self.v.check(field,text)
            msg = msg if ok_field else msg_field
        hint = self.v.hint(field,text)
        if not ok and msg:
            self.frontend.show_line(msg,'error')
        elif hint:
            self.frontend.show_line('hint: ' + hint,'dim')
        else:
            self.frontend.show_line('Enter: apply   Esc: cancel','dim')

    def compose( self, x, y = '', z = '', settings = () ):
        """A plot string from the quantities x, y and z (names of
        _viewer_ui.quantities or expressions, y empty for a 1D histogram, z
        empty unless it is a 3D plot) and the settings, as (option, shown text)
        of the controls (given only by tests). The expressions of the
        quantities come with their options (as their names)."""
        from ._histstring import _hist_join, _hist_parts
        ( ex, ox ), ( ey, _ ), ( ez, _ ) = ( _hist_parts(ui.quantity_plot(t)) for t in ( x, y, z ) )
        #(the options of a quantity are kept only for 1D histograms):
        plot = ' : '.join( e for e in ( ex, ey, ez ) if e ) if ey else _hist_join(ex,ox)
        for name, shown in settings:
            plot = self._option(plot,name,shown)
        return plot

    def on_add_plot( self, plot, title = '' ):
        """A plot (with its title) is added. Returns whether it was added (or
        shown, if it was there already, keeping its title)."""
        new = len(self.v.views)
        ok, msg = self.v.set('plot',plot)
        if ok and title.strip() and len(self.v.views) > new:
            self.v.set_title(self.v.current_key,title)
        self.frontend.show_line(msg,'normal' if ok else 'error')
        self.refresh()
        return ok

    #The axes of the shown plot, and new plots:

    @property
    def shown_key( self ):
        """The key of the card shown: that of the view, or info:new while a new
        plot is made (see on_new_plot)"""
        return 'info:new' if self._new_plot is not None else self.v.current_key

    def axis_texts( self ):
        """The expressions of the x, y and z axes of the shown plot (y empty for
        1D histograms, z unless it is a 3D plot), as texts"""
        from ._histstring import _hist_exprs
        plot = self._shown_plot()
        if plot is None:
            return '', '', ''
        exprs = _hist_exprs(plot)
        return tuple( exprs + [ '' ] * ( 3 - len(exprs) ) )

    def on_new_plot( self ):
        """Start a new plot, which is added when what to plot is chosen (see
        on_axes), and given up when another view is shown"""
        self._new_plot = ''#(its title, see on_title)
        self.refresh()
        self.frontend.focus_field('x_axis')
        self.frontend.show_line('Choose or type what to plot on the X axis (and on the Y and Z axes for'
                       ' 2D histograms and 3D plots)','dim')

    def on_axes( self, x, y = '', z = '' ):
        """The expressions of the x, y and z axes of the shown plot (or of a new
        plot) are given (names of _viewer_ui.quantities, or expressions, y
        empty for 1D histograms, z unless it is a 3D plot, see _axes_problem).
        The options of the plot are kept if they can be used for the new axes.
        Returns whether the plot was changed (or added)."""
        from ._histstring import _hist_join, _hist_parts
        x, y, z = ( a.strip() for a in ( x, y, z ) )
        if not x:
            self.frontend.show_line('Choose or type what to plot on the X axis','error')
            return False
        problem = _axes_problem(( x, y, z ))
        if problem:
            self.frontend.show_line(problem,'error')
            return False
        self.frontend.show_pending('axes',False)
        if self._new_plot is not None:
            title, self._new_plot = self._new_plot, None
            return self.on_add_plot(self.compose(x,y,z),title)
        plot = self._shown_plot()
        if plot is None:
            return False
        exprs = ' : '.join( _hist_parts(ui.quantity_plot(e))[0] for e in ( x, y, z ) if e )
        new = _hist_join(exprs,_hist_parts(plot)[1])
        if not self.v.check('plot',new)[0] and self.v.check('plot',exprs)[0]:
            new = exprs#(options which can not be used for the new axes, e.g. logx in 2D)
        done, msg, replot = ui.apply_text(self.v,'plot',new,replaces = self._shown_key())
        self.frontend.show_line(msg,'normal' if done else 'error')
        self.refresh(plot = replot)
        return done

    def on_axes_edited( self, x, y = '', z = '' ):
        """The expressions of the axes are edited (see on_axes): they are
        checked (as the field 'axes'), with the Apply button of the axes
        enabled while they differ from those of the shown plot (or for a new
        plot)"""
        x, y, z = ( a.strip() for a in ( x, y, z ) )
        self.frontend.show_pending('axes',bool(x) and ( self._new_plot is not None
                                               or ( x, y, z ) != self.axis_texts() ))
        if not x:
            self.frontend.show_check('axes',None)
            self.frontend.show_line('Choose or type what to plot on the X axis (and on the Y and Z axes'
                           ' for 2D histograms and 3D plots), and press Enter','dim')
            return
        problem = _axes_problem(( x, y, z ))
        if problem:
            self.frontend.show_check('axes',False)
            self.frontend.show_line(problem,'error')
            return
        ok, msg = self.v.check('plot',self.compose(x,y,z))
        self.frontend.show_check('axes',ok)
        self.frontend.show_line(msg if not ok else 'Enter: show this   Esc: cancel',
                       'error' if not ok else 'dim')

    def plot_code( self ):
        """The command and Python code of the shown plot (or of the plots of
        the overview), see Viewer.code"""
        plot = self._shown_plot()
        plots = [ plot ] if plot else [ p for p in map(ui.plot_of,self.v.overview_keys(self.v.current_key))
                                         if p ]
        return self.v.code(plots)

    def cards( self ):
        """The views as cards (see Card), in their order, and for files without
        userdata, a card for it after the fields (which is not a view), as a
        reminder that MCPL files can have userdata, the card of a new plot
        while it is made (see on_new_plot), and the inactive groups in their
        places. A plot of several standard groups has a card in each (as the
        same view)."""
        from .plotting import Text
        res = []
        for key, _ in self.v.views:
            info = self.v.plot_info(key)
            if ui.plot_of(key) is None:
                #(the overview of a group, see Viewer.overviews, named after the
                #group, which is shown also when the group is folded, and
                #deactivates the group):
                custom = ui.group_of(key) == custom_key
                res.append(Card(key,info['group'],group=info['group'],grouped=True,
                                badges=[ f'overview \u00b7 {b}' for b in info['badges'] ],
                                image=True,pinned=True,overview=True,
                                removable=not custom,remove_text='Deactivate this group'))
                continue
            items = self._plot_items(key)
            problem = items[0].text if len(items) == 1 and isinstance(items[0],Text) else None
            #(fields which the file does not have are 0, which is said, as their
            #plots show it):
            status = ( f'all {info["constant"]}' + ( ' (absent)' if info['absent'] else '' )
                       if info['constant'] is not None else None )
            #(only custom plots are moved and removed, see Viewer.change_plot):
            custom = self.v.is_custom(info['plot'])
            res.append(Card(key,info['name'],title=info['title'],plot=info['plot'],
                            group=info['group'],grouped=True,badges=info['badges'],
                            status=status,problem=problem,image=status is None,
                            draggable=custom,removable=custom,
                            remove_text='Remove this plot' if custom else None))
        res = self._cards_in_all_groups(res)
        if ( 'fields' in self.v.groups and not self.v.has_userdata
             and 'info:userdata' not in self._removed ):
            fields = _groups['fields'][0]
            i = 1 + max( ( i for i, c in enumerate(res) if c.group == fields ),
                         default = len(res) - 1 )
            res.insert(i,Card('info:userdata','Userdata',group=fields,grouped=True,
                              status='not in this file',selectable=False,removable=True))
        if self._new_plot is not None:
            res.append(Card('info:new',self._new_plot or 'New plot',group=custom_title,grouped=True,
                            badges=( 'choose what to plot', ),selectable=False,removable=True))
        #(the inactive standard groups, in their places in the order of the
        #groups, without headers, which are activated by a click, see
        #on_select_key):
        #(each before the cards of the groups after it, and of the custom one):
        later = { custom_title }
        for key, title, active in reversed(self.v.group_list()):
            if not active:
                i = next( ( i for i, c in enumerate(res) if c.group in later ), len(res) )
                res.insert(i,Card(f'info:group:{key}',title,group=title,status='click to activate',
                                  inactive=True))
            later.add(title)
        return res

    def _cards_in_all_groups( self, cards ):
        """The cards (one per view, in the first group with it), with the cards
        of each standard group in the order of its plots, also of those whose
        views have their cards in groups before it (as copies, which are not
        moved or removed)"""
        import copy
        first = {}
        for c in cards:
            first.setdefault(c.key,c)
        res, made = [], set()
        for c in cards:
            if c.grouped and not c.overview and c.group in made:
                continue#(made from the overview of its group, below)
            res.append(c)
            group = ui.group_of(c.key) if c.overview else None
            if group is None or group == custom_key:
                continue
            made.add(c.group)
            for p, name in dict(self.v.group_items(group)).items():
                card = first.get(f'plot:{p}')
                if card is not None and card.group != c.group:
                    card = copy.copy(card)
                    card.group, card.draggable, card.removable = c.group, False, False
                    card.name = name
                if card is not None:
                    res.append(card)
        return res

    def thumbnail( self, key, width, height ):
        """A small image of the plot of the view, as PNG data (or None if
        there is no plot yet). While the file is read, it is drawn again at
        most every 2 seconds."""
        import time

        from ._thumbnails import thumbnail_png
        if key.startswith('info:'):
            return None#(not a view, see cards)
        figure = self.v.figure(key = key)
        old = self._thumbnails.get(key)
        if figure is None:
            #(the image of the plot before is kept while the file is read):
            return old[1] if old and self.v.reading else None
        if old is not None and ( old[0] is figure
                                 or ( time.monotonic() - old[2] < 2 and self.v.reading ) ):
            return old[1]
        png = thumbnail_png(figure,width,height)
        self._thumbnails[key] = ( figure, png, time.monotonic() )
        return png

    def on_field_edited( self, field, text ):
        """The text of the field was changed by the user (field is
        'shown_plot' for the field of the shown plot): it is checked"""
        if field == 'shown_plot':
            ok, msg = ui.check_text(self.v,'plot',text,replaces = self._shown_key())
            hint = self.v.hint('plot',text) if text.strip() else None
        else:
            ok, msg = ui.check_text(self.v,field,text)
            hint = self.v.hint(field,text)
        self.frontend.show_check(field,ok)
        self.frontend.show_pending(field,self._is_pending(field,text))
        if not ok and msg:
            self.frontend.show_line(msg,'error')
        elif hint:
            self.frontend.show_line('hint: ' + hint,'dim')
        elif field == 'shown_plot' and not text.strip():
            self.frontend.show_line('Enter: remove this plot   Esc: cancel','dim')
        else:
            self.frontend.show_line(ui.field_hint('plot' if field == 'shown_plot' else field,self.v),'dim')

    def _is_pending( self, field, text ):
        """Whether the text of the field differs from what was applied"""
        if field == 'shown_plot':
            return text.strip() != ( '' if self._new_plot is not None
                                     else self._shown_plot() or '' )
        return text.strip() != ( self.v.field_text(field) or '' ).strip()

    def on_field_unfocused( self, field, text ):
        """The keyboard focus left the field (to another part of the window):
        a changed text is applied if it is valid, except an empty text of the
        shown plot (which would remove it)"""
        if not self._is_pending(field,text) or ( field == 'shown_plot' and not text.strip() ):
            return
        name = 'plot' if field == 'shown_plot' else field
        if not ui.check_text(self.v,name,text,
                             replaces = self._shown_key() if field == 'shown_plot' else None)[0]:
            return#(it keeps its mark and its error, see on_field_edited)
        self.on_field_apply(field,text)

    def on_field_apply( self, field, text ):
        """The text of the field is applied (Enter, or chosen in a menu).
        Returns whether it was applied."""
        if field == 'shown_plot' and self._new_plot is not None:
            title, self._new_plot = self._new_plot, None
            if not self.on_add_plot(text,title):
                self._new_plot = title#(still to be made)
                self.refresh(plot = False)
                return False
            self.frontend.show_check(field,None)
            self.frontend.show_pending(field,False)
            return True
        if field == 'shown_plot':
            done, msg, replot = ui.apply_text(self.v,'plot',text,replaces = self._shown_key())
        else:
            done, msg, replot = ui.apply_text(self.v,field,text)
        if done:
            self._histories.pop(field,None)
            self.frontend.show_check(field,None)
            self.frontend.show_pending(field,False)
            if field != 'shown_plot':
                #(the added plot is shown, so the field is emptied):
                self.frontend.show_field(field,'' if field == 'plot' else self.v.field_text(field))
        self.frontend.show_line(msg,'normal' if done else 'error')
        self.refresh(plot = replot)
        return done

    def on_field_cancel( self, field ):
        """The editing of the field is cancelled (Esc): its text is restored"""
        self._histories.pop(field,None)
        self.frontend.show_check(field,None)
        self.frontend.show_pending(field,False)
        self.frontend.show_line('','normal')
        if field == 'shown_plot':
            self.refresh(plot = False)
        else:
            self.frontend.show_field(field,'' if field == 'plot' else self.v.field_text(field))

    def on_history( self, field, delta ):
        """The text after moving delta in the earlier texts of the field (Up and
        Down), or None"""
        name = 'plot' if field == 'shown_plot' else field
        h = self._histories.setdefault(field,ui.History(self.v,name))
        return h.step(delta)

    def on_complete( self, field, text, cursor ):
        """Tab completion in the field (see ui.complete_text), in the
        expression of an axis (field 'axis'), or in one written in a setting of
        the shown plot (see ui.written_options)"""
        if field in ui.written_options:
            field = ui.written_options[field][2]
        return ui.complete_text(self.v,'plot' if field in ( 'shown_plot', 'axis' ) else field,
                                text,cursor)

    def on_key( self, key ):
        """A key pressed outside the text fields (with the names of
        _viewer_ui, e.g. 'Up', 'MoveDown' or 'p')"""
        if key.lower() in ui.scale_keys:
            self.on_scale_key(key)
            return
        if key == 'Delete':
            self.on_remove()
            return
        action = ui.key_action(key)
        if action is None:
            return
        if action in ( 'previous', 'next' ):
            self.on_select(self.v.current + ( -1 if action == 'previous' else 1 ))
        elif action in ( 'move_up', 'move_down' ):
            self.on_move( -1 if action == 'move_up' else 1 )
        elif action == 'change':
            if self._shown_plot() is not None:
                self.frontend.focus_field('shown_plot')
        elif action == 'plot':
            self.on_new_plot()
        elif action == 'write' and not self.v.changes_particles:
            self.frontend.show_line(self.v.nothing_to_write,'error')
        elif action in ui.file_prompts:
            self.frontend.ask_file(action)
        elif action == 'help':
            self.frontend.show_help()
        elif action == 'quit':
            self.frontend.close_window()
        else:
            self.frontend.focus_field(action)

    def hover_text( self, name ):
        """The text of the status line while the mouse is over the field or
        action with the name"""
        if name == 'write' and not self.v.changes_particles:
            return self.v.nothing_to_write
        return ui.shortcut_text(name)

    def _attach( self, viewer ):
        """Show the viewer (core), with the overviews of all groups (with all
        their plots), and the custom one with the place of a new plot (see
        on_click)"""
        self.v = viewer
        viewer.multi_overview = True
        viewer.new_plot_cell = True

    def on_open_file( self, filename, particles = True ):
        """Show another file (with the same plots, and the same pick and edit
        if particles is set, see Viewer.for_file). Returns whether it was
        opened."""
        try:
            new, msg = self.v.for_file(filename,particles)
        except MCPLError as e:
            self.frontend.show_line(f'Not opened: {e}','error')
            return False
        self.v.stop()
        self._attach(new)
        self._thumbnails = {}
        self._plot_pending = False
        self.pane.clear()
        self.frontend.show_title(new.filename)
        self.start()
        self.frontend.show_line(msg,'error' if msg else 'normal')
        return True

    def on_remove( self, key = None ):
        """Remove the plot (the view with the key, default the shown one), the
        card (for cards which are not views), or for the overview of a
        standard group, deactivate the group"""
        key = key or self.shown_key
        if key == 'info:new':
            self._new_plot = None#(given up, see on_new_plot)
            self.refresh()
            return
        if ui.group_of(key) is not None:
            #(the overview of a group hides the group):
            if ui.group_of(key) == custom_key:
                self.frontend.show_line('The custom plots are removed one by one','error')
                return
            self.on_show_group(ui.group_of(key),False)
            return
        if key.startswith('info:'):
            self._removed.add(key)#(a card which is not a view, see cards)
            self.refresh(plot = False)
            return
        if ui.plot_of(key) is None:
            self.frontend.show_line('Choose a plot to remove it','error')
            return
        name = self.v.plot_info(key)['name']
        ok, msg = self.v.change_plot(key,'')
        self.frontend.show_line(f'Removed the plot "{name}"' if ok else msg,'normal' if ok else 'error')
        self.refresh()

    def on_scale_key( self, key, view = None ):
        """A key toggling a log scale (see ui.scale_keys) of the shown plot, or
        of the view with the key view (e.g. a plot of the overview under the
        mouse)"""
        ok, msg = self.v.toggle_scale(ui.scale_keys[key.lower()],view)
        self.frontend.show_line(msg,'normal' if ok else 'error')
        self.refresh()

    def on_action( self, action ):
        """A button of ui.actions was pressed"""
        self.on_key(next( a[2][0] for a in ui.actions if a[0] == action ))

    def on_file( self, action, filename ):
        """The file name asked for by ask_file (None if cancelled)"""
        if filename:
            done, msg, _ = ui.apply_text(self.v,action,filename)
            self.frontend.show_line(msg,'normal' if done else 'error')
            self.refresh(plot = False)

    def suggested_filename( self, action ):
        return ( self.v.suggested_filename() if action == 'write'
                 else self.v.suggested_state_filename() )

    #The common part:

    def _shown_plot( self ):
        """The plot string of the shown view, if it is a plot (else None, also
        while a new plot is made)"""
        if self._new_plot is not None:
            return None
        return ui.plot_of(self._shown_key())

    def _shown_key( self ):
        """The key of the shown view, if it is a plot (else None, also while a
        new plot is made)"""
        key = self._selected_key()
        return key if ui.plot_of(key) is not None else None

    def _selected_key( self ):
        """The key of the shown view (None while a new plot is made)"""
        return None if self._new_plot is not None else self.v.current_key

    def _plot_items( self, key ):
        """The items of the plot of the view with the key (none while it is
        not drawn)"""
        fig = self.v.figure(key = key)
        return fig.panels[0].items if fig is not None and len(fig.panels) == 1 else []

    def refresh( self, plot = True ):
        """Show the views, the status and (if plot is set) the plot"""
        v = self.v
        self.frontend.show_views(self.cards())
        self.frontend.show_status(*v.status_lines())
        shown = self._shown_plot()
        if self._new_plot is not None:
            self.frontend.show_plot_field('',self._new_plot,( '', '', '' ))
        else:
            self.frontend.show_plot_field(shown,v.plot_info(self._shown_key())['title'] if shown else None,
                                 self.axis_texts())
        self.frontend.show_controls(self.plot_controls())
        self.frontend.show_overview_controls(self.overview_controls())
        self.frontend.show_enabled('write',self.v.changes_particles)
        if plot and self._new_plot is not None:
            self.pane.clear()
            self.pane.show_message(ui.new_plot_hints,left = True)
            self.frontend.draw_plot()
        elif plot and v.figure() is None and not v.reading:
            #(nothing to show, e.g. when no particles are picked: said in the
            #plot, instead of keeping the plot drawn before):
            message = ( v.error or 'nothing to show' ).capitalize()
            if self._empty != ( v.current_key, message ):
                self._empty = ( v.current_key, message )
                self.pane.clear()
                self.pane.show_message(message)
                self.frontend.draw_plot()
        elif plot:
            import time
            self._empty = None
            t = time.monotonic()
            if self.pane.show(v):
                self.frontend.draw_plot()
                self._drawn_at = time.monotonic()
                self._draw_time = self._drawn_at - t

def run_with_ctrl_c( run, close ):
    """Run the GUI (run() returns when the window is closed), with Ctrl-C in the
    terminal closing the window (close()). This uses a handler of SIGINT,
    since a KeyboardInterrupt in a callback of the GUI toolkit is only
    reported by some (e.g. Tk). The handler runs when Python code runs (with
    the timer of the viewer, at the latest)."""
    import signal
    import threading
    main = threading.current_thread() is threading.main_thread()
    old = signal.signal(signal.SIGINT,lambda *args : close()) if main else None
    try:
        run()
    except KeyboardInterrupt:
        close()
    finally:
        if main:
            signal.signal(signal.SIGINT,old)
