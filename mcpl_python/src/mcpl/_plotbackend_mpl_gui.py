
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

"""The viewer in a matplotlib window. The window shows the views on the left,
the status and the plot on the right, and the fields and actions at the
bottom, all handled with the keys and the mouse as in the terminal (see
_viewer_ui)."""

__all__ = []

from . import _viewer_ui as ui

#Matplotlib key names, as names of _viewer_ui:
_keymap = { 'up' : 'Up', 'down' : 'Down', 'left' : 'Left', 'right' : 'Right',
            'home' : 'Home', 'end' : 'End', 'backspace' : 'Backspace',
            'delete' : 'Delete', 'enter' : 'Enter', 'escape' : 'Esc',
            'tab' : 'Tab', 'f1' : 'F1', 'pageup' : 'PageUp',
            'pagedown' : 'PageDown', ' ' : ' ' }

_colors = { 'normal' : 'black', 'dim' : '0.5', 'key' : 'tab:blue',
            'ok' : 'tab:green', 'error' : 'tab:red', 'bold' : 'black' }

class MplViewer:
    """The viewer on a matplotlib figure (fig, from pyplot, or any figure
    with a canvas, e.g. in tests)"""
    #Layout (in figure coordinates):
    _left = 0.17
    _top = 0.92#(below the logo)
    _bottom = 0.30
    _nlines = 10#(lines of the bottom panel)

    def __init__( self, viewer, fig ):
        from ._plotbackend_mpl import Backend
        self.v, self.fig = viewer, fig
        viewer.multi_overview = True#(the overview with all its plots, see _on_click)
        self._panel_axes = []#(axes of the overview, with the keys of their views)
        self._bk = Backend.__new__(Backend)#(only for draw_in)
        self.editor = None
        self.message = ''
        self.hover = None
        self.show_help = False
        self._artists = []#(texts of the views and the bottom panel)
        self._targets = []#(text, what) of the clickable texts
        self._plot_axes = []
        self._plot_key = None#(view key of the plot axes)
        self.closed = False
        canvas = fig.canvas
        mgr = getattr(canvas,'manager',None)
        if mgr is not None and getattr(mgr,'key_press_handler_id',None) is not None:
            #(the default keys of matplotlib, like s and p, are those of the
            #viewer, but its keys for log scales are passed on in _on_key):
            canvas.mpl_disconnect(mgr.key_press_handler_id)
        canvas.mpl_connect('key_press_event',self._on_key)
        canvas.mpl_connect('button_press_event',self._on_click)
        canvas.mpl_connect('motion_notify_event',self._on_move)
        canvas.mpl_connect('close_event',self._on_close)
        self._timer = canvas.new_timer(interval=200)
        self._timer.add_callback(self._on_timer)

    def start( self ):
        self.v.start()
        self._timer.start()
        self.refresh(plot=True)

    def _on_close( self, event ):
        self.closed = True
        self._timer.stop()
        self.v.stop()

    def _on_timer( self ):
        if self.v.poll():
            self.refresh(plot=True)

    #Keys and mouse:

    def _on_key( self, event ):
        k = event.key
        if k is None:
            return
        if self._scale_key(event):
            return
        k = _keymap.get(k,k)
        if k.startswith('shift+') and len(k) == 7:
            k = k[-1].upper()
        if self.key(k) == 'quit':
            import matplotlib.pyplot as plt
            plt.close(self.fig)
            self._on_close(None)

    def _scale_key( self, event ):
        """Pass the keys of matplotlib for log scales (l and k by default) to
        matplotlib, for the plot under the mouse (except while editing)"""
        import matplotlib
        from matplotlib.backend_bases import key_press_handler
        keys = ( matplotlib.rcParams['keymap.xscale']
                 + matplotlib.rcParams['keymap.yscale'] )
        if ( event.key not in keys or self.editor is not None or self.show_help
             or event.inaxes not in self._plot_axes ):
            return False
        key_press_handler(event,self.fig.canvas)
        return True

    def key( self, k ):
        """Handle a key (with the names of _viewer_ui)"""
        plot = False
        if self.show_help:
            self.show_help = False
            self.refresh(plot=True)
            return None
        if self.editor is not None:
            r = self.editor.key(k)
            if r == 'cancel':
                self.editor = None
            elif r == 'apply':
                plot = self._apply()
            self.refresh(plot=plot)
            return None
        res = self._do(ui.key_action(k))
        self.refresh(plot=True)
        return res

    def _do( self, action ):
        v = self.v
        self.message = ''
        if action == 'previous':
            v.select(v.current - 1)
        elif action == 'next':
            v.select(v.current + 1)
        elif action in ( 'skip', 'limit', 'pick', 'edit', 'plot', 'write', 'change' ):
            self.editor = ui.editor_for(v,action)
        elif action == 'help':
            self.show_help = True
        elif action == 'quit':
            return 'quit'
        return None

    def _apply( self ):
        done, self.message, replot = ui.apply_editor(self.v,self.editor)
        if done:
            self.editor = None
        return replot

    def _target( self, event ):
        for ax, key in self._panel_axes:
            if event.inaxes is ax:
                return ( 'panel', key )
        for t, what in self._targets:
            if t.get_visible() and t.contains(event)[0]:
                return what
        return None

    def _on_click( self, event ):
        what = self._target(event)
        if what is None:
            return
        if isinstance(what,tuple):
            self.editor = None
            self.hover = None
            self.v.select_key(what[1])
            self.refresh(plot=True)
        elif isinstance(what,int):
            self.editor = None
            self.v.select(what)
            self.refresh(plot=True)
        elif self._do(what) == 'quit':
            import matplotlib.pyplot as plt
            plt.close(self.fig)
            self._on_close(None)
        else:
            self.refresh(plot=True)

    def _on_move( self, event ):
        what = self._target(event)
        if what != self.hover:
            self.hover = what
            self.refresh(plot=False)

    #Drawing:

    def refresh( self, plot = True ):
        """Redraw the texts (and the plot, if plot is True)"""
        fig, v = self.fig, self.v
        for a in self._artists:
            a.remove()
        self._artists, self._targets = [], []
        old_axes, old_key = [], None
        if plot or self.show_help:
            for ax in self._plot_axes:
                ax.remove()
            old_axes, old_key = self._plot_axes, self._plot_key
            self._plot_axes = []
            self._panel_axes = []
            self._plot_key = None
        if self.show_help:
            self._text(0.02,self._top,ui.help_text,va='top',family='monospace',size=9)
            self._text(0.02,0.02,'(press any key)',color='0.5')
            fig.canvas.draw_idle()
            return
        #The views:
        views = v.views
        y = self._top
        dy = min( 0.03, 0.6 / max( 1, len(views) ) )
        for i, (_, label) in enumerate(views):
            sel = i == v.current
            t = self._text(0.01,y,( '\u25b8 ' if sel else '  ' ) + label,
                           weight='bold' if sel else 'normal',size=9,va='top')
            self._targets.append( ( t, i ) )
            y -= dy
        #The status and the plot:
        first, second = v.status_lines()
        self._text(self._left,0.985,first,weight='bold',va='top',size=10)
        self._text(self._left,0.955,second,va='top',size=9,color='0.3')
        if plot:
            figure = v.figure()
            if figure is not None:
                from matplotlib.gridspec import GridSpec
                gs = GridSpec(1,1,figure=fig,left=self._left+0.07,right=0.98,
                              top=0.86 if figure.title else 0.9,
                              bottom=self._bottom+0.06)
                self._plot_axes = self._bk.draw_in(fig,gs[0,0],figure)
                self._plot_key = v.views[v.current][0]
                if self._plot_key == old_key:
                    from ._plotbackend_mpl import keep_zoom
                    keep_zoom(old_axes,self._plot_axes)
                self._panel_axes = []
                if v.views[v.current][0] == 'overview:multi':
                    #(the plots of the overview can be clicked):
                    self._panel_axes = list(zip(self._plot_axes,
                                                [ f'overview:{k}' for k in ui.overview_keys ]))
        figure = v.figure()
        if figure is not None and figure.title:
            self._text(0.5*(self._left+1.0),0.935,figure.title,ha='center',
                       va='top',size=10)
        #The bottom panel, in lines of monospace text:
        lines = []
        for field, label, key, kpos, empty in ui.fields:
            ed = self.editor if self.editor is not None and self.editor.field == field else None
            a, b, c = ui.labelled(label,kpos)
            if ed:
                t = ed.text
                txt = t[:ed.cursor] + '\u2502' + t[ed.cursor:]
                mark = ( ' \u2713', 'ok' ) if ed.ok else ( ' \u2717', 'error' )
                segs = [ (a,'normal'), (b,'key'), (c + ': ','normal'), ('[' + txt + ']','bold'), mark ]
            else:
                t = v.field_text(field)
                segs = [ (a,'normal'), (b,'key'), (c + ': ','normal'),
                         ('[' + ( t or empty ) + ']','normal' if t else 'dim') ]
            lines.append( ( segs, field ) )
        ed = self.editor
        hint = ui.hint_line(ed,popup=True)
        lines.append( ( [ hint ], None ) )
        #(the commands doing the same are printed when the window is closed)
        if ed is not None and ed.field == 'write':
            lines.append( ( [ ('Write to: ','bold'), ('[' + ed.text + ']','bold') ], None ) )
        else:
            segs = []
            for action, label, keys, kpos in ui.actions:
                a, b, c = ui.labelled(label,kpos)
                segs.append( ( ( '[' + a, 'normal' ), ( b, 'key' ), ( c + ']  ', 'normal' ), action ) )
            lines.append( ( segs, 'actions' ) )
        hover = self.hover
        if isinstance(hover,tuple):
            hover = 'panel'
        elif hover is not None and not isinstance(hover,str):
            hover = 'views'
        status = self.message or ( ui.shortcut_text(hover) if hover is not None else '' )
        lines.append( ( [ ( status, 'error' if self.message.startswith('Not') else 'normal' ) ], None ) )
        self._draw_lines(lines)
        if ed is not None and ed.choices:
            row = next( i for i, f in enumerate(ui.fields) if f[0] == ed.field )
            label = ui.fields[row][1]
            self._draw_popup(row,len(label) + 3 + ed.choice_start)
        fig.canvas.draw_idle()

    def _draw_popup( self, row, column ):
        """The completions in a box above the line row of the bottom panel,
        from the column (in characters)"""
        from matplotlib.patches import Rectangle
        fig, ed = self.fig, self.editor
        size = 9
        cw = 0.6 * size / 72.0 / fig.get_figwidth()
        rh = 1.45 * size / 72.0 / fig.get_figheight()
        first, rows = ui.popup_rows(ed,12)
        n = len(ed.choices)
        nw = max( len(name) for name, _ in ed.choices )
        texts = [ name.ljust(nw) + '  ' + ( descr or '' ) for name, descr in ed.choices[first:first+rows] ]
        if rows < n:
            texts.append( f'{ed.selected+1}/{n}' )
        width = ( max( len(t) for t in texts ) + 2 ) * cw
        x = min( 0.01 + column * cw, 0.99 - width )
        bottom = self._bottom - 0.01 - row * ( self._bottom - 0.02 ) / self._nlines + 0.005
        top = bottom + len(texts) * rh + 0.01
        box = Rectangle( (x,bottom), width, top - bottom, transform=fig.transFigure,
                         facecolor='white', edgecolor='0.5', zorder=10 )
        fig.add_artist(box)
        self._artists.append(box)
        for i, t in enumerate(texts):
            chosen = first + i == ed.selected
            self._text(x+cw,top-0.005-i*rh,t,family='monospace',size=size,va='top',zorder=11,
                       color='0.5' if i == rows else 'black',weight='bold' if chosen else 'normal',
                       backgroundcolor='#cde' if chosen else 'white')

    def _text( self, x, y, s, **kw ):
        t = self.fig.text(x,y,s,**kw)
        self._artists.append(t)
        return t

    def _draw_lines( self, lines ):
        """The lines of the bottom panel, each a list of segments (text,
        style), with the clickable lines given by what"""
        fig = self.fig
        size = 9
        #(width of a character of the monospace font, in figure coordinates):
        cw = 0.6 * size / 72.0 * fig.dpi / ( fig.get_figwidth() * fig.dpi )
        lh = ( self._bottom - 0.02 ) / self._nlines
        y = self._bottom - 0.01
        for segs, what in lines:
            x = 0.01
            if what == 'actions':
                for parts in segs:
                    x0 = x
                    for text, style in parts[:3]:
                        self._text(x,y,text,family='monospace',size=size,va='top',
                                   color=_colors[style],
                                   weight='bold' if style in ('key','bold') else 'normal')
                        x += len(text) * cw
                    hit = self._text(x0,y,' ' * len(''.join(p[0] for p in parts[:3])),
                                     family='monospace',size=size,va='top')
                    self._targets.append( ( hit, parts[3] ) )
            else:
                full = ''
                for text, style in segs:
                    self._text(x,y,text,family='monospace',size=size,va='top',
                               color=_colors[style],
                               weight='bold' if style in ('key','bold') else 'normal')
                    x += len(text) * cw
                    full += text
                if what is not None:
                    hit = self._text(0.01,y,full,family='monospace',size=size,
                                     va='top',alpha=0.0)
                    self._targets.append( ( hit, what ) )
            y -= lh

def run_viewer( viewer, backend = None ):
    """Run the viewer in a matplotlib window"""
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(14,9))
    from ._plotbackend_mpl import add_logo
    add_logo(fig,left=True)
    try:
        fig.canvas.manager.set_window_title(f'MCPL viewer: {viewer.filename}')
    except AttributeError:
        pass
    gui = MplViewer(viewer,fig)
    #Ctrl-C in the terminal quits, like q. It is handled with a handler of
    #SIGINT closing the window, since a KeyboardInterrupt in a callback of
    #the GUI toolkit is only reported by some (e.g. Tk). The handler runs when
    #Python code runs, at the latest with the timer of the viewer.
    import signal
    import threading
    def on_sigint( *args ):
        plt.close(fig)
    main = threading.current_thread() is threading.main_thread()
    old = signal.signal(signal.SIGINT,on_sigint) if main else None
    try:
        gui.start()
        plt.show()
    except KeyboardInterrupt:
        plt.close(fig)
    finally:
        if main:
            signal.signal(signal.SIGINT,old)
        gui._on_close(None)
