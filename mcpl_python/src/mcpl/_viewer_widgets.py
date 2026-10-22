
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

"""The common part of the viewers with the widgets of a GUI toolkit (Tk, see
_viewer_tk): what happens when the fields, the views and the actions are
used, independent of the toolkit. The plot is a matplotlib figure, embedded
in the window by the toolkit."""

__all__ = []

from . import _viewer_ui as ui
from ._common import MCPLError

#The look of the viewers with windows (for toolkits with colours): the
#colours of the line of messages and of the marks of the checks, of the
#highlighted code (see _viewer_code.highlight), of the cards of the views (see
#cards), and of the parts below the plot (that of the shown plot in the colour
#of its selected card, and that of the pick and edit):
colors = { 'normal' : 'black', 'dim' : '#777777', 'ok' : '#2ca02c', 'error' : '#d62728' }
code_styles = { 'comment' : { 'foreground' : '#6a737d' },
                'string' : { 'foreground' : '#067d17' },
                'keyword' : { 'foreground' : '#0033b3' },
                'number' : { 'foreground' : '#1750eb' },
                'preprocessor' : { 'foreground' : '#9e5b00' },
                'option' : { 'foreground' : '#871094' } }
card_colors = { 'bg' : '#eef1f5', 'card' : '#ffffff', 'selected' : '#e2ebf6',
                'border' : '#d5dbe3', 'accent' : '#2f5f8f', 'text' : '#1d2733',
                'dim' : '#7a8594', 'badge' : '#dfe7f1' }
part_colors = { 'Plot' : card_colors['selected'], 'Particles' : card_colors['bg'] }

def _split_axes( x, y ):
    """The expressions of the x and y axes, with "x : y" written in one of them
    (while the other is empty) split onto both"""
    x, y = x.strip(), y.strip()
    if ':' in ( x or y ) and not ( x and y ):
        x, _, y = ( e.strip() for e in ( x or y ).partition(':') )
    return x, y

class Card:
    """A card of the list of views of the viewers with windows (see
    WidgetViewer.cards), which the front ends show as far as they can: the
    name, the group (if grouped, else it is not in a group, as the
    overview), the badges of the options of the plot, a short status for
    compact cards (e.g. "all 0" for fields with one value, or "not in this
    file"), the problem of a plot which failed, and whether it has an image
    (see WidgetViewer.thumbnail), can be selected (shown), dragged (moved)
    and removed (see WidgetViewer.on_remove, with remove_text saying what
    that does, if not just removing the card), and whether it is shown also
    when its group is folded (pinned). The key is that of the view, or starts
    with info: for cards which are not views."""
    __slots__ = (
        'badges',
        'draggable',
        'group',
        'grouped',
        'image',
        'key',
        'name',
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
                  pinned = False, remove_text = None ):
        self.key, self.name, self.title, self.plot = key, name, title, plot
        self.pinned, self.remove_text = pinned, remove_text
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

class WidgetViewer:
    """The viewer in a window with the widgets of a GUI toolkit. A subclass
    for the toolkit creates the widgets (the list of views, the status, the
    plot, a text field for each field of _viewer_ui.fields, chosen from a menu
    for those of _viewer_ui.menu_fields, a field for the text of the shown
    plot, a line for the check of the field being edited or a message, and
    buttons for _viewer_ui.actions), implements the methods marked as such
    below, and calls the on_* methods when they are used. The viewer core is
    v, and fig is the matplotlib figure of the plot."""

    def __init__( self, viewer, fig ):
        from ._plotbackend_mpl import FigurePane
        self.v, self.fig = viewer, fig
        viewer.multi_overview = True#(the overview with all its plots)
        self.pane = FigurePane(fig,( 0.08, 0.98, 0.11, 0.93 ),title_space=0.05,
                               title_y=0.98)
        self._histories = {}#field -> ui.History, while it is edited
        self._thumbnails = {}#view key -> (figure, PNG data, time)
        self._removed = set()#(the cards removed which are not views, see cards)
        self._new_plot = None#(the title of a new plot, while it has no axes, see on_new_plot)
        self._empty = None#(the view and message shown instead of its plot, see refresh)
        #(when the plot was drawn, how long it took, and whether a newer figure
        #is not drawn yet, see on_timer):
        self._drawn_at, self._draw_time, self._plot_pending = 0.0, 0.0, False
        self.closed = False

    #To implement for the toolkit:

    def show_views( self, cards, current ):
        """Show the views as cards (see cards()), with the one shown (the
        index current) selected"""
        raise NotImplementedError

    def show_status( self, first, second ):
        """Show the two status lines (see Viewer.status_lines)"""
        raise NotImplementedError

    def show_field( self, field, text ):
        """Set the text of the field (without calling on_field_edited)"""
        raise NotImplementedError

    def show_plot_field( self, text, title, axes ):
        """Set the texts of the fields of the shown plot: its histogram string,
        its title and the expressions of its axes (x, y), or disable them if
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

    def show_title( self, filename ):
        """Show the name of the file (e.g. in the title of the window)"""

    def show_enabled( self, action, enabled ):
        """Show the button of the action as enabled or not (if the toolkit has
        such buttons)"""

    def show_check( self, field, ok ):
        """Mark the text of the field being edited as valid or not (ok is None
        for no mark)"""
        raise NotImplementedError

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
        """Show ui.help_text"""
        raise NotImplementedError

    def close_window( self ):
        """Close the window (on_close is then called)"""
        raise NotImplementedError

    #Called by the toolkit:

    def start( self ):
        self.v.start()
        for field, *_ in ui.fields:
            self.show_field(field,self.v.field_text(field))
        self.refresh()

    def on_timer( self ):
        """To be called regularly (e.g. every 0.2 s), while the file is read.
        While it is read, the plot is only drawn again when some time passed
        (at least 3 times as long as drawing it took), so the window stays
        responsive."""
        import time
        if self.closed:
            return
        changed = self.v.poll()
        if not ( changed or self._plot_pending ):
            return
        reading = self.v.reading
        wait = max( 0.5, 3 * self._draw_time )
        late = time.monotonic() - self._drawn_at >= wait
        self.refresh(plot = late or not reading)
        self._plot_pending = reading and not late

    def on_close( self ):
        if not self.closed:
            self.closed = True
            self.v.stop()

    def on_select( self, index ):
        self._new_plot = None#(a new plot without axes is given up)
        self.v.select(index)
        self.refresh()

    def on_select_key( self, key ):
        self._new_plot = None
        self.v.select_key(key)
        self.refresh()

    def on_move( self, delta ):
        if self.v.move(delta):
            self.refresh()

    def on_click( self, event ):
        """A click in the figure (a matplotlib event): on a plot of the overview,
        it is shown on its own"""
        key = self.pane.view_at(event)
        if key is not None:
            self.v.select_key(key)
            self.refresh()

    def on_title( self, text ):
        """The title of the shown plot is set (an empty text removes it)"""
        if self._new_plot is not None:
            self._new_plot = text#(for when it is added)
            self.refresh(plot = False)
            return
        key = self._shown_key()
        if key is not None:
            ok, msg = self.v.set_title(key,text)
            self.show_line(msg,'normal' if ok else 'error')
            self.refresh(plot = False)

    def on_show_group( self, key, shown = True ):
        """Show (or hide) the standard group of plots with the key (see
        Viewer.show_group)"""
        if self.v.show_group(key,shown):
            title = { k : t for k, t, _, _ in self.v.group_list() }[key]
            self.show_line(f'{"Shown" if shown else "Hidden"}: the group {title}','normal')
            if shown:
                self.v.select_key(f'overview:{key}')
        self.refresh()

    def group_key( self, title ):
        """The key of the standard group with the title, or None"""
        return next( ( k for k, t, _, _ in self.v.group_list() if t == title ), None )

    def on_drop( self, key, target ):
        """A card was dragged onto the card of the view with the key target
        (None: before the first custom plot): the custom plot of the view with
        the key is moved there (only custom plots are reordered)"""
        plots = [ k for k, _ in self.v.views if k.startswith('custom:') ]
        if key in plots and ( target is None or target in plots ):
            self.v.move_to(key[7:],0 if target is None else plots.index(target))
        else:
            self.show_line('Only the custom plots are reordered','error')
        self.refresh(plot = False)

    #The settings of the shown plot, and the plots added with settings:

    def plot_controls( self, plot = None ):
        """The settings of the plot (default the shown one) as (kind, controls),
        where controls are (option, label, the texts of its choices, or None for
        a text field, the shown text, and the text shown greyed in an empty
        text field: what is used, e.g. the numbers of bins), see
        _viewer_ui.plot_controls, or None if the shown view is not a plot"""
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
            v = given.get(name,False)
            #(the option given without a value, or with 1, is True, and 0 is
            #as if not given):
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
        fig = self.v.figure(key = f'plot:{plot}')#(the same for custom plots)
        items = fig.panels[0].items if fig is not None and len(fig.panels) == 1 else ()
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
        choices = next( ( c for n, _, c in sum( ui.plot_controls.values(), () ) if n == name ), None )
        text = shown.strip()
        if choices is not None:
            value = dict(choices).get(text,text or None)
        else:
            #(an empty number of bars is the default number):
            value = text or ( True if name == 'bar' else None )
        return _hist_set_option(plot,name,value)

    def on_control( self, name, shown ):
        """A setting of the shown plot was changed (to the shown text)"""
        plot = self._shown_plot()
        if plot is None:
            return
        done, msg, replot = ui.apply_text(self.v,'plot',self._option(plot,name,shown),
                                          replaces = self._shown_key())
        self.show_line(msg,'normal' if done else 'error')
        self.refresh(plot = replot)

    def compose( self, x, y = '', settings = () ):
        """A plot string from the quantities x and y (names of
        _viewer_ui.quantities or expressions, y empty for a 1D histogram) and
        the settings, as (option, shown text) of the controls. The expressions
        of the quantities come with their options (as their names)."""
        from ._histstring import _hist_parts
        q = dict(ui.quantities)
        for _, p in reversed(ui.quantities):
            q[p.split(';')[0]] = p
        def parts( t ):
            return _hist_parts(q.get(t.strip(),t.strip()))
        ( ex, ox ), ( ey, _ ) = parts(x), parts(y)
        #(the options of a quantity are kept only for 1D histograms):
        plot = f'{ex} : {ey}' if ey else ';'.join( [ ex ] + [ n if v is None else f'{n}={v}'
                                                             for n, v in ox ] )
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
        self.show_line(msg,'normal' if ok else 'error')
        self.refresh()
        return ok

    #The axes of the shown plot, and new plots:

    @property
    def shown_key( self ):
        """The key of the card shown: that of the view, or info:new while a new
        plot is made (see on_new_plot)"""
        return 'info:new' if self._new_plot is not None else self.v.current_key

    def axis_texts( self ):
        """The expressions of the x and y axes of the shown plot (y empty for
        1D histograms), as texts"""
        from ._histstring import _hist_parts
        plot = self._shown_plot()
        if plot is None:
            return '', ''
        x, _, y = _hist_parts(plot)[0].partition(':')
        return x.strip(), y.strip()

    def on_new_plot( self ):
        """Start a new plot, which is added when what to plot is chosen (see
        on_axes), and given up when another view is shown"""
        self._new_plot = ''#(its title, see on_title)
        self.refresh()
        self.focus_field('x_axis')
        self.show_line('Choose or type what to plot on the X axis (and on the Y axis for 2D'
                       ' histograms)','dim')

    def on_axes( self, x, y = '' ):
        """The expressions of the x and y axes of the shown plot (or of a new
        plot) are given (names of _viewer_ui.quantities, or expressions, y
        empty for 1D histograms; "x : y" in either is split, see _split_axes). The options
        of the plot are kept if they can be used for the new axes. Returns
        whether the plot was changed (or added)."""
        from ._histstring import _hist_parts
        x, y = _split_axes(x,y)
        if not x:
            self.show_line('Choose or type what to plot on the X axis','error')
            return False
        if self._new_plot is not None:
            title, self._new_plot = self._new_plot, None
            return self.on_add_plot(self.compose(x,y),title)
        plot = self._shown_plot()
        if plot is None:
            return False
        q = dict(ui.quantities)
        exprs = ' : '.join( _hist_parts(q.get(e,e))[0] for e in ( x, y ) if e )
        opts = [ n if v is None else f'{n}={v}' for n, v in _hist_parts(plot)[1] ]
        new = ';'.join( [ exprs ] + opts )
        if not self.v.check('plot',new)[0] and self.v.check('plot',exprs)[0]:
            new = exprs#(options which can not be used for the new axes, e.g. logx in 2D)
        done, msg, replot = ui.apply_text(self.v,'plot',new,replaces = self._shown_key())
        self.show_line(msg,'normal' if done else 'error')
        self.refresh(plot = replot)
        return done

    def on_axes_edited( self, x, y = '' ):
        """The expressions of the axes are edited (see on_axes): they are
        checked (as the field 'axes')"""
        x, y = _split_axes(x,y)
        if not x:
            self.show_check('axes',None)
            self.show_line('Choose or type what to plot on the X axis (and on the Y axis for 2D'
                           ' histograms), and press Enter','dim')
            return
        ok, msg = self.v.check('plot',self.compose(x,y))
        self.show_check('axes',ok)
        self.show_line(msg if not ok else 'Enter: show this   Esc: cancel',
                       'error' if not ok else 'dim')

    def plot_code( self ):
        """The command and Python code of the shown plot (or of the plots of
        the overview), see Viewer.code"""
        plot = self._shown_plot()
        plots = [ plot ] if plot else [ ui.plot_of(k) for k in self.v.overview_keys(self.v.current_key) if k ]
        return self.v.code(plots)

    def cards( self ):
        """The views as cards (see Card), in their order, and in the default
        collection, for files without userdata, a card for it after the other
        fields (which is not a view), as a reminder that MCPL files can have
        userdata, and the card of a new plot while it is made (see
        on_new_plot)"""
        from .plotting import Text
        res = []
        for key, _ in self.v.views:
            info = self.v.plot_info(key)
            if ui.plot_of(key) is None:
                #(the overview of a group, see Viewer.overviews, which is shown
                #also when the group is folded, and hides the group):
                custom = key == 'overview:custom'
                res.append(Card(key,info['name'],group=info['group'],grouped=True,
                                badges=info['badges'],image=True,pinned=True,
                                removable=not custom,remove_text='Hide this group'))
                continue
            fig = self.v.figure(key = key)
            items = fig.panels[0].items if fig is not None and len(fig.panels) == 1 else []
            problem = items[0].text if len(items) == 1 and isinstance(items[0],Text) else None
            status = ( 'not in this file' if info['absent'] else
                       f'all {info["constant"]}' if info['constant'] is not None else None )
            #(only custom plots are moved and removed, see Viewer.change_plot):
            custom = self.v.is_custom(info['plot'])
            res.append(Card(key,info['name'],title=info['title'],plot=info['plot'],
                            group=info['group'],grouped=True,badges=info['badges'],
                            status=status,problem=problem,image=status is None,
                            draggable=custom,removable=custom))
        if ( 'fields' in self.v.groups and not self.v.has_userdata
             and 'info:userdata' not in self._removed ):
            i = 1 + max( ( i for i, c in enumerate(res) if c.group == 'Fields' ),
                         default = len(res) - 1 )
            res.insert(i,Card('info:userdata','Userdata',group='Fields',grouped=True,
                              status='not in this file',selectable=False,removable=True))
        if self._new_plot is not None:
            res.append(Card('info:new',self._new_plot or 'New plot',group='Custom',grouped=True,
                            badges=( 'choose what to plot', ),selectable=False,removable=True))
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
            hint = None if field in ui.menu_fields else self.v.hint(field,text)
        self.show_check(field,ok)
        if not ok and msg:
            self.show_line(msg,'error')
        elif hint:
            self.show_line('hint: ' + hint,'dim')
        elif field == 'shown_plot' and not text.strip():
            self.show_line('Enter: remove this plot   Esc: cancel','dim')
        else:
            self.show_line(ui.field_hint('plot' if field == 'shown_plot' else field),'dim')

    def on_field_apply( self, field, text ):
        """The text of the field is applied (Enter, or chosen in a menu).
        Returns whether it was applied."""
        if field == 'shown_plot' and self._new_plot is not None:
            title, self._new_plot = self._new_plot, None
            if not self.on_add_plot(text,title):
                self._new_plot = title#(still to be made)
                self.refresh(plot = False)
                return False
            self.show_check(field,None)
            return True
        if field == 'shown_plot':
            done, msg, replot = ui.apply_text(self.v,'plot',text,replaces = self._shown_key())
        else:
            done, msg, replot = ui.apply_text(self.v,field,text)
        if done:
            self._histories.pop(field,None)
            self.show_check(field,None)
            if field != 'shown_plot':
                #(the added plot is shown, so the field is emptied):
                self.show_field(field,'' if field == 'plot' else self.v.field_text(field))
        self.show_line(msg,'normal' if done else 'error')
        self.refresh(plot = replot)
        return done

    def on_field_cancel( self, field ):
        """The editing of the field is cancelled (Esc): its text is restored"""
        self._histories.pop(field,None)
        self.show_check(field,None)
        self.show_line('','normal')
        if field == 'shown_plot':
            self.refresh(plot = False)
        else:
            self.show_field(field,'' if field == 'plot' else self.v.field_text(field))

    def on_history( self, field, delta ):
        """The text after moving delta in the earlier texts of the field (Up and
        Down), or None"""
        name = 'plot' if field == 'shown_plot' else field
        h = self._histories.setdefault(field,ui.History(self.v,name))
        return h.step(delta)

    def on_complete( self, field, text, cursor ):
        """Tab completion in the field (see ui.complete_text)"""
        return ui.complete_text(self.v,'plot' if field == 'shown_plot' else field,text,cursor)

    def menu_choices( self, field ):
        """The values of a field of ui.menu_fields, as (value, description)"""
        return self.v.complete(field,'')[1]

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
                self.focus_field('shown_plot')
        elif action == 'plot':
            self.on_new_plot()
        elif action == 'write' and not self.v.changes_particles:
            self.show_line(self.v.nothing_to_write,'error')
        elif action in ui.file_prompts:
            self.ask_file(action)
        elif action == 'help':
            self.show_help()
        elif action == 'quit':
            self.close_window()
        else:
            self.focus_field(action)

    def on_open_file( self, filename, particles = True ):
        """Show another file (with the same plots, and the same pick and edit
        if particles is set, see Viewer.for_file). Returns whether it was
        opened."""
        try:
            new, msg = self.v.for_file(filename,particles)
        except MCPLError as e:
            self.show_line(f'Not opened: {e}','error')
            return False
        self.v.stop()
        self.v = new
        new.multi_overview = True
        self._thumbnails = {}
        self._plot_pending = False
        self.pane.clear()
        self.show_title(new.filename)
        self.start()
        self.show_line(msg,'error' if msg else 'normal')
        return True

    def on_remove( self, key = None ):
        """Remove the plot (the view with the key, default the shown one)"""
        key = key or self.shown_key
        if key == 'info:new':
            self._new_plot = None#(given up, see on_new_plot)
            self.refresh()
            return
        if key.startswith('overview:'):
            #(the overview of a group hides the group):
            if key == 'overview:custom':
                self.show_line('The custom plots are removed one by one','error')
                return
            self.on_show_group(key[9:],False)
            return
        if key.startswith('info:'):
            self._removed.add(key)#(a card which is not a view, see cards)
            self.refresh(plot = False)
            return
        if ui.plot_of(key) is None:
            self.show_line('Choose a plot to remove it','error')
            return
        name = self.v.plot_info(key)['name']
        ok, msg = self.v.change_plot(key,'')
        self.show_line(f'Removed the plot "{name}"' if ok else msg,'normal' if ok else 'error')
        self.refresh()

    def on_scale_key( self, key, view = None ):
        """A key toggling a log scale (see ui.scale_keys) of the shown plot, or
        of the view with the key view (e.g. a plot of the overview under the
        mouse)"""
        ok, msg = self.v.toggle_scale(ui.scale_keys[key.lower()],view)
        self.show_line(msg,'normal' if ok else 'error')
        self.refresh()

    def on_action( self, action ):
        """A button of ui.actions was pressed"""
        self.on_key(next( a[2][0] for a in ui.actions if a[0] == action ))

    def on_file( self, action, filename ):
        """The file name asked for by ask_file (None if cancelled)"""
        if filename:
            done, msg, _ = ui.apply_text(self.v,action,filename)
            self.show_line(msg,'normal' if done else 'error')
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
        key = None if self._new_plot is not None else self.v.current_key
        return key if ui.plot_of(key) is not None else None

    def refresh( self, plot = True ):
        """Show the views, the status and (if plot is set) the plot"""
        v = self.v
        self.show_views(self.cards(),v.current)
        self.show_status(*v.status_lines())
        shown = self._shown_plot()
        if self._new_plot is not None:
            self.show_plot_field('',self._new_plot,( '', '' ))
        else:
            self.show_plot_field(shown,v.plot_info(self._shown_key())['title'] if shown else None,
                                 self.axis_texts())
        self.show_controls(self.plot_controls())
        self.show_enabled('write',self.v.changes_particles)
        if plot and self._new_plot is not None:
            self.pane.clear()
            self.pane.show_message('Choose or type what to plot below (X axis)')
            self.draw_plot()
        elif plot and v.figure() is None and not v.reading:
            #(nothing to show, e.g. when no particles are picked: said in the
            #plot, instead of keeping the plot drawn before):
            message = ( v.error or 'nothing to show' ).capitalize()
            if self._empty != ( v.current_key, message ):
                self._empty = ( v.current_key, message )
                self.pane.clear()
                self.pane.show_message(message)
                self.draw_plot()
        elif plot:
            import time
            self._empty = None
            t = time.monotonic()
            if self.pane.show(v):
                self.draw_plot()
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
