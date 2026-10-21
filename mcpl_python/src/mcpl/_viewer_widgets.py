
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
        self.pane = FigurePane(fig,( 0.08, 0.98, 0.09, 0.93 ),title_space=0.05,
                               title_y=0.98)
        self._histories = {}#field -> ui.History, while it is edited
        self._thumbnails = {}#view key -> (figure, PNG data, time)
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

    def show_plot_field( self, text, title ):
        """Set the texts of the fields of the shown plot (its histogram string
        and its title), or disable them if text is None (the shown view is
        not a plot)"""
        raise NotImplementedError

    def show_line( self, text, style ):
        """Show the line below the fields, with the style 'normal', 'dim',
        'ok' or 'error' (see _viewer_ui.hint_line)"""
        raise NotImplementedError

    def show_controls( self, controls ):
        """Show the settings of the shown plot (see plot_controls), or none
        (if controls is None)"""
        raise NotImplementedError

    def show_check( self, field, ok ):
        """Mark the text of the field being edited as valid or not (ok is None
        for no mark)"""
        raise NotImplementedError

    def draw_plot( self ):
        """Redraw the canvas of the figure (it changed)"""
        raise NotImplementedError

    def focus_field( self, field ):
        """Move the keyboard focus to the text field (field is 'shown_plot' for
        the field of the shown plot)"""
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
        """To be called regularly (e.g. every 0.2 s), while the file is read"""
        if not self.closed and self.v.poll():
            self.refresh()

    def on_close( self ):
        if not self.closed:
            self.closed = True
            self.v.stop()

    def on_select( self, index ):
        self.v.select(index)
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
        plot = self._shown_plot()
        if plot is not None:
            ok, msg = self.v.set_title(plot,text)
            self.show_line(msg,'normal' if ok else 'error')
            self.refresh(plot = False)

    def on_drop( self, key, index, group ):
        """A card was dragged: its plot (of the view with the key) is moved to
        the index in the list of plots, and into the group (None for none)"""
        plot = key[5:]
        self.v.move_to(plot,index)
        self.v.set_group(plot,group or '')
        self.refresh(plot = False)

    #The settings of the shown plot, and the plots added with settings:

    def plot_controls( self, plot = None ):
        """The settings of the plot (default the shown one) as (kind, controls),
        where controls are (option, label, the texts of its choices, or None for
        a text field, and the shown text), see _viewer_ui.plot_controls, or
        None if the shown view is not a plot"""
        from ._histstring import _hist_parts, _parse_hist
        plot = plot or self._shown_plot()
        if plot is None:
            return None
        try:
            o = _parse_hist(plot)
        except MCPLError:#(e.g. while it is composed, see compose)
            return None
        kind = '2d' if len(o['exprs']) == 2 else 'bar' if o['bar'] else '1d'
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
            res.append( ( name, label, [ t for t, _ in choices ] if choices else None, shown ) )
        return kind, res

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
                                          replaces = plot)
        self.show_line(msg,'normal' if done else 'error')
        self.refresh(plot = replot)

    def compose( self, x, y = '', settings = () ):
        """A plot string from the quantities x and y (names of
        _viewer_ui.quantities or expressions, y empty for a 1D histogram) and
        the settings, as (option, shown text) of the controls"""
        from ._histstring import _hist_parts
        q = dict(ui.quantities)
        def parts( t ):
            return _hist_parts(q.get(t.strip(),t.strip()))
        ( ex, ox ), ( ey, _ ) = parts(x), parts(y)
        #(the options of a quantity are kept only for 1D histograms):
        plot = f'{ex} : {ey}' if ey else ';'.join( [ ex ] + [ n if v is None else f'{n}={v}'
                                                             for n, v in ox ] )
        for name, shown in settings:
            plot = self._option(plot,name,shown)
        return plot

    def preview_png( self, plot, width, height ):
        """A preview of the plot, as (PNG data, None), or (None, the problem)"""
        from ._plotbackend_mpl import figure_png
        ok, msg = self.v.check('plot',plot)
        if not ok:
            return None, msg
        figure = self.v.preview(plot)
        if figure is None:
            return None, 'No particles to show'
        return figure_png(figure,width,height), None

    def on_add_plot( self, plot, title = '' ):
        """A plot (with its title) is added from the builder. Returns whether
        it was added (or shown, if it was there already, keeping its title)."""
        new = len(self.v.views)
        ok, msg = self.v.set('plot',plot)
        if ok and title.strip() and len(self.v.views) > new:
            self.v.set_title(self.v.current_key[5:],title)
        self.show_line(msg,'normal' if ok else 'error')
        self.refresh()
        return ok

    def plot_code( self ):
        """The command and Python code of the shown plot (or of the plots of
        the overview), see Viewer.code"""
        plot = self._shown_plot()
        plots = [ plot ] if plot else [ k[5:] for k in self.v.overview_keys() ]
        return self.v.code(plots)

    def cards( self ):
        """The views as cards: the plot_info of the viewer (see
        Viewer.plot_info), with the key of the view"""
        return [ { 'key' : key, **self.v.plot_info(key) } for key, _ in self.v.views ]

    def thumbnail( self, key, width, height ):
        """A small image of the plot of the view, as PNG data (or None if
        there is no plot yet). While the file is read, it is drawn again at
        most every 2 seconds."""
        import time

        from ._plotbackend_mpl import thumbnail_png
        figure = self.v.figure(key = key)
        old = self._thumbnails.get(key)
        if figure is None:
            return old[1] if old else None
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
            ok, msg = ui.check_text(self.v,'plot',text,replaces = self._shown_plot())
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
        if field == 'shown_plot':
            done, msg, replot = ui.apply_text(self.v,'plot',text,replaces = self._shown_plot())
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
        elif action in ui.file_prompts:
            self.ask_file(action)
        elif action == 'help':
            self.show_help()
        elif action == 'quit':
            self.close_window()
        else:
            self.focus_field(action)

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
        """The plot string of the shown view, if it is a plot (else None)"""
        key = self.v.current_key
        return key[5:] if key.startswith('plot:') else None

    def refresh( self, plot = True ):
        """Show the views, the status and (if plot is set) the plot"""
        v = self.v
        self.show_views(self.cards(),v.current)
        self.show_status(*v.status_lines())
        shown = self._shown_plot()
        self.show_plot_field(shown,v.plot_info(f'plot:{shown}')['title'] if shown else None)
        self.show_controls(self.plot_controls())
        if plot and self.pane.show(v):
            self.draw_plot()

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
