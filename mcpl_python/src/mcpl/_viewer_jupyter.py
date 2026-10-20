
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
fields (applied with Enter) and the actions of _viewer_ui. With the ipympl
backend of matplotlib (%matplotlib widget), the plot is an interactive
matplotlib figure, otherwise an image."""

__all__ = []

import html
import threading

from . import _viewer_ui as ui
from ._common import MCPLError


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
        self._views = w.Select(options=[ label for _, label in viewer.views ],
                               index=viewer.current,rows=18,
                               layout=w.Layout(width='190px'))
        self._views.observe(self._on_view,'index')
        self._status = w.HTML()
        self._image = w.Image(format='png',layout=w.Layout(width='100%'))
        #The overview as a grid of its plots, each with a button showing it on
        #its own (images in ipywidgets can not be clicked), by position (the
        #plots of the overview are the first ones, see Viewer.overview_keys):
        self._panels = []
        cells = []
        for i in range(len(viewer.overview_keys())):
            img = w.Image(format='png',layout=w.Layout(width='100%'))
            b = w.Button(layout=w.Layout(width='auto'))
            b.on_click(lambda _, i=i : self._on_panel(self.v.overview_keys()[i]))
            self._panels.append( ( img, b ) )
            cells.append(w.VBox([ img, b ]))
        self._grid = w.GridBox(cells,layout=w.Layout(
            width='100%',grid_template_columns='repeat(3,1fr)'))
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
        for field in ( f for row in ui.field_rows for f in row ):
            _, label, _key, _kpos, empty = fieldinfo[field]
            row = next( r for r in ui.field_rows if field in r )
            common = { 'value' : viewer.field_text(field), 'description' : label + ':',
                       'style' : {'description_width':'70px'},
                       'layout' : w.Layout(width=f'{95 // len(row)}%') }
            if field in ui.menu_fields:
                t = w.Dropdown(options=[ ( f'{name}: {descr}', name )
                                         for name, descr in viewer.complete(field,'')[1] ],
                               **common)
            else:
                t = w.Text(placeholder=empty,continuous_update=False,**common)
            t.observe(lambda change, field=field : self._on_field(field,change),'value')
            self._fields[field] = t
            if field == row[-1]:
                rows.append( t if len(row) == 1 else
                             w.HBox([ self._fields[f] for f in row ],layout=w.Layout(width='100%')) )
        #(the text of the shown added plot, which can be changed, or emptied to
        #remove it; shown only for added plots):
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
        self._extra = w.HTML()
        self._right = right = w.VBox([ self._status, self._image ],
                                     layout=w.Layout(width='100%'))
        from ._logo import logo_png
        logo = w.Image(value=logo_png(),format='png',layout=w.Layout(width='190px'))
        self.widget = w.VBox([ self._warning, w.HBox([ w.VBox([ logo, self._views,
                                                                  w.HBox(moves) ]), right ]),
                               *rows,
                               self._message, self._commands,
                               w.HBox([ self._filename, write, names, helpb ]),
                               w.HBox([ self._statefile, save ]),
                               self._extra ])
        self._stop = threading.Event()
        self._thread = None
        #(whether the widgets are being changed by the viewer, not the user, per
        #thread, as the handlers of a change run in the thread changing the
        #widget, which can be the polling thread while the user types):
        self._local = threading.local()
        self._shown = {}#image -> (view key, figure) shown in it
        #(only one thread at a time draws with matplotlib):
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

    def _on_view( self, change ):
        if change['new'] is not None and not self._syncing:
            self.v.select(change['new'])
            self.refresh()

    def _on_click( self, event ):
        key = self._pane.view_at(event)
        if key is not None:
            self._on_panel(key)

    def _on_move( self, delta ):
        if self.v.move(delta):
            self._sync_views()
            self.refresh()

    def _on_panel( self, key ):
        self.v.select_key(key)
        self._sync_views()
        self.refresh()

    def _on_field( self, field, change ):
        if self._syncing:
            return
        ok, msg = self.v.set(field,change['new'])
        self._show_result(ok,msg)
        if ok and field == 'plot':
            self._set_quietly(self._fields['plot'],'')

    def _on_change( self, change ):
        key = self.v.current_key
        if self._syncing or not key.startswith('plot:'):
            return
        self._show_result(*self.v.change_plot(key[5:],change['new']))

    def _show_result( self, ok, msg ):
        self._message.value = '' if ok else f'<span style="color:#c00">{html.escape(msg)}</span>'
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

    def _sync_views( self ):
        labels = [ label for _, label in self.v.views ]
        current = self.v.current
        self._syncing = True#(changing the options also changes the index)
        try:
            if list(self._views.options) != labels:
                self._views.options = labels
            self._views.index = current
        finally:
            self._syncing = False

    def _on_write( self, _ ):
        self._write_or_save('write',self._filename,self.v.suggested_filename)

    def _on_save_state( self, _ ):
        self._write_or_save('state',self._statefile,self.v.suggested_state_filename)

    def _write_or_save( self, action, field, suggested ):
        done, msg, _ = ui.apply_text(self.v,action,field.value)
        if done:
            self._message.value = html.escape(msg)
            field.value = suggested()
            self.refresh()#(the command shown has the next file name)
        else:
            self._message.value = f'<span style="color:#c00">{html.escape(msg)}</span>'

    def _on_help( self, _ ):
        self._extra.value = ( '' if self._extra.value.startswith('<pre>The viewer')
                              else f'<pre>{html.escape(ui.help_text)}</pre>' )

    def _on_names( self, _ ):
        from ._exprhelp import _help_text
        self._extra.value = f'<pre>{html.escape(_help_text("pick"))}</pre>'

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
        first, second = self.v.status_lines()
        self._status.value = ( f'<b>{html.escape(first)}</b><br>'
                               f'<span style="color:#555">{html.escape(second)}</span>' )
        c = self.v.commands()
        self._commands.value = f'<code style="color:#555">$ {html.escape(c["extract"])}</code>'
        #(with the views and the key of the shown one taken once, as the user
        #can change them while this runs in the polling thread):
        labels = dict(self.v.views)
        key = self.v.current_key
        self._change.layout.display = None if key.startswith('plot:') else 'none'
        if key.startswith('plot:') and self._change.value != key[5:]:
            self._set_quietly(self._change,key[5:])
        if self._mplfig is not None:
            if self._pane.show(self.v,key):
                self._mplfig.canvas.draw_idle()
            shown = self._mplfig.canvas
        elif key == 'overview:multi':
            for ( img, b ), k in zip(self._panels,self.v.overview_keys()):
                b.description = labels.get(k,k[5:])
                self._show(img,k)
            shown = self._grid
        else:
            self._show(self._image,key)
            shown = self._image
        if self._right.children[1] is not shown:
            self._right.children = ( self._status, shown )

def _png( figure ):
    """The figure drawn with matplotlib, as PNG data"""
    import io

    from ._plotbackend_mpl import Backend
    bk = Backend.__new__(Backend)#(no pyplot needed for drawing figures to files)
    f = bk._draw(figure,saving=True,logo=False)#(the logo is above the views)
    out = io.BytesIO()
    f.savefig(out,format='png',dpi=80)
    return out.getvalue()

def run_viewer( viewer, backend = None ):
    """Show the viewer in Jupyter (returns the JupyterViewer)"""
    from IPython.display import display
    jv = JupyterViewer(viewer)
    display(jv.widget)
    jv.start()
    return jv
