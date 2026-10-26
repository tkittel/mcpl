
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

"""The viewer in a window: with Tk if possible (see _viewer_tk), or else in a
matplotlib window (MplViewer), which shows the views on the left, the status
and the plot on the right, and the fields and actions at the bottom, all
handled with the keys and the mouse as in the terminal (see _viewer_ui)."""

__all__ = []

from . import _viewer_ui as ui

#Matplotlib key names, as names of _viewer_ui:
_colors = { **ui.colors, 'key' : 'tab:blue', 'bold' : 'black' }

class MplViewer(ui.KeyViewer):
    """The viewer on a matplotlib figure (fig, from pyplot, or any figure
    with a canvas, e.g. in tests)"""
    #Layout (in figure coordinates):
    _left = 0.17
    _top = 0.92#(below the logo)
    _bottom = 0.24
    _nlines = 8#(lines of the bottom panel)

    def __init__( self, viewer, fig ):
        from ._plotbackend_mpl import FigurePane
        super().__init__(viewer)
        self.fig = fig
        viewer.multi_overview = True#(the overview with all its plots, see _on_click)
        self._pane = FigurePane(fig,( self._left + 0.07, 0.98, self._bottom + 0.06, 0.9 ),
                                title_space=0.04,title_y=0.935)
        self._artists = []#(texts of the views and the bottom panel)
        self._targets = []#(text, what) of the clickable texts
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
        from ._plotbackend_mpl import key_name
        if self.key(key_name(k)) == 'quit':
            import matplotlib.pyplot as plt
            plt.close(self.fig)
            self._on_close(None)

    def _scale_key( self, event ):
        """The keys of log scales (l and k, see ui.scale_keys) toggle the
        scale of the plot, or of the plot of the overview under the mouse
        (except while editing). Returns whether the key was one of them."""
        if ( event.key.lower() not in ui.scale_keys or self.editor is not None
             or self.show_help ):
            return False
        self.scale_key(event.key,self._pane.view_at(event))
        self.refresh(plot=True)
        return True

    def key( self, k ):
        """Handle a key (with the names of _viewer_ui)"""
        if self.show_help:
            self.show_help = False
            self.refresh(plot=True)
            return None
        if self.editor is not None:
            self.refresh(plot=self.editor_key(k))
            return None
        res = self.do(ui.key_action(k))
        self.refresh(plot=True)
        return 'quit' if res == 'quit' else None

    def _target( self, event ):
        key = self._pane.view_at(event)
        if key is not None:
            return ( 'panel', key )
        for t, what in self._targets:
            if t.get_visible() and t.contains(event)[0]:
                return what
        return None

    def _on_click( self, event ):
        from ._plotbackend_mpl import after_event
        after_event(event.canvas,self._on_click_after,event)

    def _on_click_after( self, event ):
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
        elif self.do(what) == 'quit':
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
        if self.show_help:
            self._pane.clear()
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
            self._pane.show(v)
        #The bottom panel, in lines of monospace text:
        #(each line a list of groups of segments, which can be clicked):
        lines = []
        fieldinfo = { f[0] : f for f in ui.fields }
        popup = None#(line and column of the name completed, if any)
        for row in ui.field_rows:
            groups, column = [], 0
            for field in row:
                _, label, _key, kpos, empty = fieldinfo[field]
                ed = self.editor if self.editor is not None and self.editor.field == field else None
                a, b, c = ui.labelled(label,kpos)
                if ed:
                    t = ed.text
                    #(with the cursor, except in menus, see ui.LineEditor):
                    txt = t if ed.menu else t[:ed.cursor] + '\u2502' + t[ed.cursor:]
                    mark = ( ' \u2713', 'ok' ) if ed.ok else ( ' \u2717', 'error' )
                    segs = [ (a,'normal'), (b,'key'), (c + ': ','normal'), ('[' + txt + ']','bold'), mark ]
                    popup = ( len(lines), column + len(label) + 3 + ed.choice_start )
                else:
                    t = v.field_text(field)
                    segs = [ (a,'normal'), (b,'key'), (c + ': ','normal'),
                             ('[' + ( t or empty ) + ']','normal' if t else 'dim') ]
                segs.append( ( '   ', 'normal' ) )
                column += sum( len(text) for text, _ in segs )
                groups.append( ( segs, field ) )
            lines.append( ( groups, 'groups' ) )
        ed = self.editor
        hint = ui.hint_line(ed,popup=True)
        lines.append( ( [ hint ], None ) )
        #(the commands doing the same are printed when the window is closed)
        if ed is not None and ed.field in ui.file_prompts:
            lines.append( ( [ (ui.file_prompts[ed.field],'bold'), ('[' + ed.text + ']','bold') ], None ) )
        else:
            groups = []
            for action, label, keys, kpos in ui.actions:
                a, b, c = ui.labelled(label,kpos)
                groups.append( ( [ ( '[' + a, 'normal' ), ( b, 'key' ), ( c + ']  ', 'normal' ) ], action ) )
            lines.append( ( groups, 'groups' ) )
        hover = self.hover
        if isinstance(hover,tuple):
            hover = 'panel'
        elif hover is not None and not isinstance(hover,str):
            hover = 'views'
        status = self.message or ( ui.shortcut_text(hover) if hover is not None else '' )
        lines.append( ( [ ( status, self.message_style ) ], None ) )
        self._draw_lines(lines)
        if ed is not None and ed.choices and popup is not None:
            self._draw_popup(*popup)
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
        style), with the clickable lines given by what, or (if what is
        'groups') a list of groups of segments, each with what is clicked"""
        fig = self.fig
        size = 9
        #(width of a character of the monospace font, in figure coordinates):
        cw = 0.6 * size / 72.0 * fig.dpi / ( fig.get_figwidth() * fig.dpi )
        lh = ( self._bottom - 0.02 ) / self._nlines
        y = self._bottom - 0.01
        for segs, what in lines:
            x = 0.01
            if what == 'groups':
                for parts, target in segs:
                    x0 = x
                    for text, style in parts:
                        self._text(x,y,text,family='monospace',size=size,va='top',
                                   color=_colors[style],
                                   weight='bold' if style in ('key','bold') else 'normal')
                        x += len(text) * cw
                    hit = self._text(x0,y,' ' * len(''.join(p[0] for p in parts)),
                                     family='monospace',size=size,va='top')
                    self._targets.append( ( hit, target ) )
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
    """Run the viewer in a window: with Tk if it can show windows here (see
    _viewer_tk), or else in a matplotlib window (see MplViewer)"""
    from . import _viewer_tk
    root = _viewer_tk._root()
    if root is not None:
        _viewer_tk.run_viewer(viewer,root)
    else:
        run_mpl_viewer(viewer)

def run_mpl_viewer( viewer ):
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
    from ._viewer_widgets import run_with_ctrl_c
    def run():
        gui.start()
        plt.show()
    try:
        run_with_ctrl_c(run,lambda : plt.close(fig))
    finally:
        gui._on_close(None)
