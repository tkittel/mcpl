
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

"""The viewer in Jupyter, as a panel of ipywidgets: the views, the plot, the
fields (applied with Enter), and buttons moving plots, deactivating groups,
writing the particles, saving the state and showing help. With the ipympl
backend of matplotlib (%matplotlib widget), the plot is an interactive
matplotlib figure, otherwise an image."""

__all__ = []

import html
import threading

from . import _viewer_ui as ui
from ._common import MCPLError


def _exclusive( method ):
    """The handler of a widget, run while no other thread refreshes the widgets
    (the polling thread of JupyterViewer), which could otherwise see the viewer
    while it is changed"""
    import functools
    @functools.wraps(method)
    def handler( self, *args ):
        with self._refreshing:
            return method(self,*args)
    return handler

#The help of the viewer in Jupyter (the first topic of help_topics), with the
#introduction of the viewers with windows:
_help_blocks = ( ui.help_blocks[0], ( 'gap', ), ( 'text', '''Click a view in the list to show it (or an inactive group, in grey, to
activate it), and Deactivate group hides the group of the shown view. Move up
and Move down move the shown custom plot. The fields are applied with Enter:
Skip, Limit, Pick and Edit (like -s, -l, -p and -E), Add plot adds a plot of a
histogram string (like -H), and This plot changes the shown plot (an empty
text removes a custom plot). Write file writes the picked and edited particles
to a new file, and Save viewer state saves the settings and plots in a file,
which view=FILE.json of mcpl.view opens again. Names shows the names to use in
the expressions.''' ) )

def _help_topics():
    """The topics of the help, as (label, blocks, see _helptext): those of the
    viewers with windows (see WidgetViewer.help_topics, which this module can
    not import), with the viewer in Jupyter"""
    from ._exprhelp import _help_blocks as expr_blocks
    return [ ( 'The viewer', _help_blocks ),
             ( 'Picks (filtering particles)', expr_blocks('pick') ),
             ( 'Edits (modifying particles)', expr_blocks('edit') ),
             ( 'Plot expressions', expr_blocks('hist') ),
             ( 'About data caching', ui.cache_blocks ),
             ( 'About MCPL', ui.about_blocks() ) ]

#(the items of the list of views are left aligned, which needs a style):
_list_style = ( '<style>.mcpl-viewer-item { justify-content: flex-start !important;'
                ' text-align: left !important; }</style>' )

class _ViewList:
    """The views as a column of items which can be scrolled, as the cards of
    the viewers in windows: the overviews of the groups (tinted), their plots,
    and the inactive standard groups in their places (in grey, activated with
    a click), with the shown view selected. A click on an item calls
    on_click(key) with its key (info:group:KEY for inactive groups)."""
    def __init__( self, w, on_click ):
        self._w, self._on_click = w, on_click
        self.box = w.VBox(layout=w.Layout(width='190px',height='420px',overflow_y='auto',
                                          align_items='stretch'))
        self._entries, self._buttons, self.current = None, {}, None

    @property
    def keys( self ):
        return [ k for k, _, _ in self._entries or () ]

    def click( self, key ):
        self._on_click(key)

    def show( self, entries, current ):
        """Show the entries, as (key, label, kind), with kind 'overview',
        'plot' or 'inactive', and the view with the key current selected"""
        w = self._w
        if entries != self._entries:
            self._entries, self._buttons = entries, {}
            items = [ w.HTML(_list_style) ]
            for key, label, kind in entries:
                b = w.Button(description=label,tooltip=label,
                             layout=w.Layout(width='auto',height='auto',min_height='26px'))
                b.add_class('mcpl-viewer-item')
                b.on_click(lambda _, k=key : self._on_click(k))
                self._buttons[key] = ( b, kind )
                items.append(b)
            self.box.children = items
            self.current = None
        for key, ( b, kind ) in self._buttons.items():
            if self.current is not None and key not in ( current, self.current ):
                continue#(only the selection changed)
            selected = key == current
            b.style.button_color = ( ui.card_colors['accent'] if selected else
                                     ui.card_colors['overview'] if kind == 'overview' else
                                     ui.card_colors['bg'] if kind == 'inactive' else ui.card_colors['card'] )
            b.style.text_color = ( 'white' if selected else
                                   ui.card_colors['dim'] if kind == 'inactive' else ui.card_colors['text'] )
            b.style.font_weight = 'bold' if kind == 'overview' else 'normal'
            b.style.font_style = 'italic' if kind == 'inactive' else 'normal'
        self.current = current

class JupyterViewer:
    """The viewer as an ipywidgets panel (the widget attribute)"""
    def __init__( self, viewer ):
        try:
            import ipywidgets as w
        except ImportError:
            raise MCPLError('The viewer in Jupyter needs the ipywidgets Python'
                            ' package (pip install "mcpl-python[jupyter]")')
        self.v, self._w = viewer, w
        viewer.multi_overview = True#(the overview with all its plots)
        self._views = _ViewList(w,self._on_view)
        self._status = w.HTML()
        #(the cache, at the right of the status, see ui.cache_menu):
        self._cache = w.Dropdown(description='Memory:',tooltip=ui.cache_menu_title,
                                 style={'description_width':'50px'},
                                 layout=w.Layout(width='auto'))
        self._cache.observe(self._on_cache,'index')
        self._cache_text = w.HTML()
        self._image = w.Image(format='png',layout=w.Layout(width='100%'))
        #The overviews as grids of their plots (without ipympl, see _sync_grid):
        self._panels_key, self._panels, self._cells = None, [], []
        self._grid = w.GridBox([],layout=w.Layout(width='100%'))
        #The interactive figure, with ipympl:
        from ._plotbackend_mpl import FigurePane, widget_figure
        self._mplfig = widget_figure(w.DOMWidget)
        #(the plots are below the title, with smaller fonts than in a window,
        #more so for several plots, as the overview):
        self._pane = None if self._mplfig is None else FigurePane(
            self._mplfig,( 0.08, 0.98, 0.08, 0.92 ),title_space=0.06,title_y=0.98,
            title_size=9,fontsize=9,overview_fontsize=7)
        self._warning = w.HTML()
        if self._mplfig is not None:
            self._mplfig.canvas.mpl_connect('button_press_event',self._on_click)
        else:
            self._warning.value = ( '<div style="border:1px solid #c90;'
                                    'background:#fff8e0;padding:4px 8px">'
                                    f'{html.escape(ui.no_widget_text)}</div>' )
        self._fields = {}
        rows = []
        fieldinfo = { f[0] : f for f in ui.fields }
        #(the groups of plots are chosen in the list of views, see _ViewList):
        field_rows = [ r for r in ( tuple( f for f in row if f not in ui.menu_fields )
                                    for row in ui.field_rows ) if r ]
        for field in ( f for row in field_rows for f in row ):
            _, label, _key, _kpos, empty = fieldinfo[field]
            row = next( r for r in field_rows if field in r )
            common = { 'value' : viewer.field_text(field), 'description' : label + ':',
                       'style' : {'description_width':'70px'},
                       'layout' : w.Layout(width=f'{95 // len(row)}%') }
            t = w.Text(placeholder=empty,continuous_update=False,**common)
            t.observe(lambda change, field=field : self._on_field(field,change),'value')
            self._fields[field] = t
            if field == row[-1]:
                rows.append( t if len(row) == 1 else
                             w.HBox([ self._fields[f] for f in row ],layout=w.Layout(width='100%')) )
        #(the text of the shown plot, which can be changed (a plot of a standard
        #group is then copied into the custom group), or emptied to remove a
        #custom plot; shown only for plots):
        self._change = w.Text(placeholder='empty: remove the plot',continuous_update=False,
                              description='This plot:',style={'description_width':'70px'},
                              layout=w.Layout(width='95%',display='none'))
        self._change.observe(self._on_change,'value')
        rows.append(self._change)
        self._message = w.HTML()
        self._commands = w.HTML()
        self._filename = w.Text(value=viewer.suggested_filename(),
                                description='Write to:',
                                style={'description_width':'70px'})
        write = w.Button(description='Write file')
        write.on_click(self._on_write)
        deactivate = w.Button(description='Deactivate group',layout=w.Layout(width='190px'))
        deactivate.on_click(self._on_deactivate)
        self._statefile = w.Text(value=viewer.suggested_state_filename(),
                                 description='Save to:',
                                 style={'description_width':'70px'})
        save = w.Button(description='Save viewer state')
        save.on_click(self._on_save_state)
        moves = []
        for label, delta in ( ('Move up',-1), ('Move down',1) ):
            b = w.Button(description=label,layout=w.Layout(width='93px'))
            b.on_click(lambda _, delta=delta : self._on_move(delta))
            moves.append(b)
        names = w.Button(description='Names')
        names.on_click(self._on_names)
        helpb = w.Button(description='Help')
        helpb.on_click(self._on_help)
        #(the topics of the help, in a menu shown with it, see _show_extra):
        self._topics = _help_topics()
        self._topic = w.Dropdown(options=[ t[0] for t in self._topics ],description='Topic:',
                                 style={'description_width':'70px'},
                                 layout=w.Layout(display='none'))
        self._topic.observe(self._on_topic,'index')
        self._extra, self._extra_shown = w.HTML(), None
        top = w.HBox([ self._status, w.HBox([ self._cache_text, self._cache ]) ],
                     layout=w.Layout(width='100%',justify_content='space-between'))
        self._right = right = w.VBox([ top, self._image ],layout=w.Layout(width='100%'))
        from ._logo import logo_png
        logo = w.Image(value=logo_png(),format='png',layout=w.Layout(width='190px'))
        self.widget = w.VBox([ self._warning, w.HBox([ w.VBox([ logo, self._views.box,
                                                                  w.HBox(moves), deactivate ]),
                                                         right ]),
                               *rows,
                               self._message, self._commands,
                               w.HBox([ self._filename, write, names, helpb ]),
                               w.HBox([ self._statefile, save ]),
                               self._topic, self._extra ])
        self._stop = threading.Event()
        self._thread = None
        #(whether the widgets are being changed by the viewer, not the user, per
        #thread, as the handlers of a change run in the thread changing the
        #widget, which can be the polling thread while the user types):
        self._local = threading.local()
        self._shown = {}#image -> (view key, figure) shown in it
        #(only one thread at a time draws with matplotlib, or changes the viewer
        #with the handlers of the widgets, see _exclusive):
        self._refreshing = threading.RLock()

    def start( self ):
        self.v.start()
        self.refresh()
        self._thread = threading.Thread(target=self._poll,daemon=True)
        self._thread.start()

    def close( self ):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self.v.stop()

    def _poll( self ):
        #(updates of the widgets from this thread are sent by the kernel):
        while not self._stop.wait(0.3):
            if self.v.poll():
                self.refresh()

    @_exclusive
    def _on_view( self, key ):
        if key.startswith('info:group:'):#(an inactive group, which is activated)
            key = key[11:]
            self.v.show_group(key)
            key = f'overview:{key}'
        self.v.select_key(key)
        self._sync_views()
        self.refresh()

    def _on_click( self, event ):
        from ._plotbackend_mpl import after_event
        key = self._pane.view_at(event)
        if key is not None:
            after_event(event.canvas,self._on_panel,key)

    @_exclusive
    def _on_move( self, delta ):
        if self.v.move(delta):
            self._sync_views()
            self.refresh()

    @_exclusive
    def _on_panel( self, key ):
        self.v.select_key(key)
        self._sync_views()
        self.refresh()

    @_exclusive
    def _on_field( self, field, change ):
        if self._syncing:
            return
        ok, msg, _ = ui.apply_text(self.v,field,change['new'])
        self._show_result(ok,msg)
        if ok and field == 'plot':
            self._set_quietly(self._fields['plot'],'')

    @_exclusive
    def _on_change( self, change ):
        key = self.v.current_key
        if self._syncing or ui.plot_of(key) is None:
            return
        self._show_result(*ui.apply_text(self.v,'plot',change['new'],replaces = key)[:2])

    def _show_result( self, ok, msg ):
        self._message.value = '' if ok else _error_html(msg)
        self._sync_views()
        self.refresh()

    @property
    def _syncing( self ):
        return getattr(self._local,'syncing',False)

    @_syncing.setter
    def _syncing( self, value ):
        self._local.syncing = value

    def _set_quietly( self, widget, value ):
        #(without the handlers of the change):
        self._syncing = True
        try:
            widget.value = value
        finally:
            self._syncing = False

    @_exclusive
    def _on_cache( self, change ):
        if self._syncing or change['new'] is None:
            return
        self.v.set_cache_limit(ui.cache_menu(self.v.cache_info())[change['new']][1])
        self._message.value = html.escape(ui.cache_line(self.v.cache_info()))
        self.refresh()

    def _sync_cache( self ):
        """The text of the cache, in green when the plots use all particles
        (else red), and the choices"""
        info = self.v.cache_info()
        text, used = ui.cache_text(info)
        color = ui.colors['ok' if used else 'error']
        self._cache_text.value = f'<span style="color:{color}">{html.escape(text)}</span>'
        entries = ui.cache_menu(info)
        self._syncing = True#(changing the options also changes the index)
        try:
            labels = [ e[0] for e in entries ]
            if list(self._cache.options) != labels:
                self._cache.options = labels
            self._cache.index = next( ( i for i, e in enumerate(entries) if e[2] ), None )
        finally:
            self._syncing = False

    def _sync_views( self ):
        self._views.show(self._list_entries(),self.v.current_key)

    def _list_entries( self ):
        """The entries of the list of views (see _ViewList): the views of each
        group after its overview, and the inactive groups, in the order of the
        groups"""
        segments, overview = {}, None
        for key, label in self.v.views:
            if key.startswith('overview:'):
                overview = key
            kind = 'overview' if key == overview else 'plot'
            segments.setdefault(overview,[]).append( ( key, label, kind ) )
        res = []
        for k, title, active in self.v.group_list():
            if active:
                res += segments.pop(f'overview:{k}',[])
            else:
                res.append( ( f'info:group:{k}', f'{title} (click to activate)', 'inactive' ) )
        return res + [ e for entries in segments.values() for e in entries ]

    @_exclusive
    def _on_deactivate( self, _ ):
        """Deactivate the standard group of the shown view (its overview, or
        the group of its plot)"""
        key = self.v.current_key
        group = ui.group_of(key)
        if group is None and key is not None:
            title = self.v.plot_info(key)['group']
            group = next( ( k for k, t, _ in self.v.group_list() if t == title ), None )
        if group is None or group not in self.v.groups:
            self._message.value = _error_html('The custom plots are removed one by one')
            return
        try:
            self.v.show_group(group,False)
        except MCPLError as e:
            self._message.value = _error_html(str(e))
            return
        title = { k : t for k, t, _ in self.v.group_list() }[group]
        self._show_result(True,'')
        self._message.value = html.escape(f'Deactivated: the group {title}')

    @_exclusive
    def _on_write( self, _ ):
        if not self.v.changes_particles:
            self._message.value = _error_html(self.v.nothing_to_write)
            return
        self._write_or_save('write',self._filename,self.v.suggested_filename)

    @_exclusive
    def _on_save_state( self, _ ):
        self._write_or_save('state',self._statefile,self.v.suggested_state_filename)

    def _write_or_save( self, action, field, suggested ):
        done, msg, _ = ui.apply_text(self.v,action,field.value)
        if done:
            self._message.value = html.escape(msg)
            field.value = suggested()
            self.refresh()#(the command shown has the next file name)
        else:
            self._message.value = _error_html(msg)

    def _show_extra( self, what ):
        """Show the help ('help', of the topic chosen in its menu), the names
        of the expressions ('names'), or nothing (None) below the buttons"""
        from ._helptext import plain_text
        self._extra_shown = what
        self._topic.layout.display = None if what == 'help' else 'none'
        if what == 'help':
            text = plain_text(self._topics[self._topic.index or 0][1])
        elif what == 'names':
            from ._exprhelp import _help_text
            text = _help_text('pick')
        self._extra.value = f'<pre>{html.escape(text)}</pre>' if what else ''

    @_exclusive
    def _on_help( self, _ ):
        #(the buttons show the help or the names, or hide them again):
        self._show_extra(None if self._extra_shown == 'help' else 'help')

    @_exclusive
    def _on_names( self, _ ):
        self._show_extra(None if self._extra_shown == 'names' else 'names')

    @_exclusive
    def _on_topic( self, _ ):
        if self._extra_shown == 'help':
            self._show_extra('help')

    def refresh( self ):
        with self._refreshing:
            self._refresh()

    def _show( self, image, key ):
        #(the figure itself is kept, so a new one is always noticed):
        fig = self.v.figure(key = key)
        old = self._shown.get(image)
        if fig is not None and ( old is None or old[0] != key or old[1] is not fig ):
            image.value = _png(fig)
            self._shown[image] = ( key, fig )

    def _refresh( self ):
        self._sync_cache()
        self._sync_views()#(e.g. with the constant fields, as the file is read)
        first, second = self.v.status_lines()
        self._status.value = ( f'<b>{html.escape(first)}</b><br>'
                               f'<span style="color:#555">{html.escape(second)}</span>' )
        c = self.v.commands()
        self._commands.value = f'<code style="color:#555">$ {html.escape(c["extract"])}</code>'
        #(with the views and the key of the shown one taken once, as the user
        #can change them while this runs in the polling thread):
        labels = dict(self.v.views)
        key = self.v.current_key
        plot = ui.plot_of(key)
        self._change.layout.display = None if plot is not None else 'none'
        if plot is not None and self._change.value != plot:
            self._set_quietly(self._change,plot)
        if self._mplfig is not None:
            if self._pane.show(self.v,key):
                self._mplfig.canvas.draw_idle()
            shown = self._mplfig.canvas
        elif self._sync_grid(key):
            for ( img, b ), k in zip(self._panels,self.v.overview_keys(key)):
                b.description = labels.get(k,ui.plot_of(k))
                self._show(img,k)
            shown = self._grid
        else:
            self._show(self._image,key)
            shown = self._image
        if self._right.children[1] is not shown:
            self._right.children = ( self._right.children[0], shown )

    def _sync_grid( self, key ):
        """Whether the view with the key is an overview shown as the grid of
        its plots (not a correlation plot): the grid then has a cell for each,
        with a button showing it on its own (images in ipywidgets can not be
        clicked), by position (see Viewer.overview_keys)"""
        w = self._w
        ov = dict(self.v.overviews()).get(key)
        if ov is None or ov.correlation_plot:
            return False
        n = len(self.v.overview_keys(key))
        while len(self._panels) < n:
            i = len(self._panels)
            img = w.Image(format='png',layout=w.Layout(width='100%'))
            b = w.Button(layout=w.Layout(width='auto'))
            b.on_click(lambda _, i=i : self._on_panel(self.v.overview_keys(self._panels_key)[i]))
            self._panels.append( ( img, b ) )
            self._cells.append(w.VBox([ img, b ]))
        self._panels_key = key
        if len(self._grid.children) != n:
            self._grid.children = self._cells[:n]
        self._grid.layout.grid_template_columns = f'repeat({ov.ncols},1fr)'
        return True

def _error_html( msg ):
    """The message as HTML, in the colour of errors"""
    return f'<span style="color:{ui.colors["error"]}">{html.escape(msg)}</span>'

def _png( figure ):
    """The figure drawn with matplotlib, as PNG data (without the logo, which is
    above the views)"""
    from ._plotbackend_mpl import figure_png
    return figure_png(figure)

def run_viewer( viewer ):
    """Show the viewer in Jupyter (returns the JupyterViewer)"""
    from IPython.display import display
    jv = JupyterViewer(viewer)
    display(jv.widget)
    jv.start()
    return jv
