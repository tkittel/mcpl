
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

"""The plots of the viewer in its window (see _viewer_tk), drawn with matplotlib
(see _plotbackend_mpl): the overview or plot shown, keeping its zoom, and
the keys and events of matplotlib."""

__all__ = []

from ._plotbackend_mpl import _draw_axes


def draw_in( fig, subplotspec, figure ):
    """Draw the figure in a part of a matplotlib figure (a SubplotSpec, as
    for the viewer). Returns all axes added to fig (also those of colour
    bars)."""
    before = set(fig.axes)
    space = 0.08 if figure._correlation_plot else None
    gs = subplotspec.subgridspec(figure.nrows,figure.ncols,hspace=space or 0.55,
                                 wspace=space or 0.35)
    axlist = [ fig.add_subplot(gs[i,j]) for i in range(figure.nrows)
               for j in range(figure.ncols) ]
    _draw_axes(fig,axlist,figure)
    new = [ ax for ax in fig.axes if ax not in before ]
    for ax in new:
        ax._mcpl_home = _axes_view(ax)
    return new

def _axes_view( ax ):
    return ( ax.get_xlim(), ax.get_ylim(), ax.get_xscale(), ax.get_yscale() )

def keep_zoom( old_axes, new_axes ):
    """Give the new axes (from draw_in, for the same view) the limits and
    scales of the old ones, where they were changed (e.g. zoomed) since they
    were drawn"""
    if len(old_axes) != len(new_axes):
        return
    for old, new in zip(old_axes,new_axes):
        home = getattr(old,'_mcpl_home',None)
        cur = _axes_view(old)
        if home is None or cur == home:
            continue
        xlim, ylim, xscale, yscale = cur
        new.set_xscale(xscale)
        new.set_yscale(yscale)
        new.set_xlim(xlim)
        new.set_ylim(ylim)

def draw_in_box( fig, figure, left, right, bottom, top, fontsize = None ):
    """Draw the figure in a box of a matplotlib figure (in figure
    coordinates), with the font size if given. Returns the new axes, as
    draw_in."""
    import matplotlib
    from matplotlib.gridspec import GridSpec
    gs = GridSpec(1,1,figure=fig,left=left,right=right,bottom=bottom,top=top)
    rc = {} if fontsize is None else { 'font.size' : fontsize }
    with matplotlib.rc_context(rc):
        return draw_in(fig,gs[0,0],figure)

#The names of keys of matplotlib in the viewers (see _viewer_ui.key_action):
_key_names = { 'up' : 'Up', 'down' : 'Down', 'left' : 'Left', 'right' : 'Right',
               'home' : 'Home', 'end' : 'End', 'backspace' : 'Backspace',
               'delete' : 'Delete', 'enter' : 'Enter', 'escape' : 'Esc',
               'tab' : 'Tab', 'f1' : 'F1', 'pageup' : 'PageUp',
               'pagedown' : 'PageDown' }

def key_name( key ):
    """The name in the viewers (see _viewer_ui.key_action) of a key of
    matplotlib (event.key): Up and Down with any modifiers (e.g. shift+up,
    ctrl+up or super+up) are MoveUp and MoveDown, shift+x is X"""
    k = _key_names.get(key,key)
    for arrow, name in ( ( '+up', 'MoveUp' ), ( '+down', 'MoveDown' ) ):
        if k.endswith(arrow):
            return name
    if k.startswith('shift+') and len(k) == 7:
        return k[-1].upper()
    return k

def after_event( canvas, fct, *args ):
    """Call fct(*args) after the event being handled (e.g. a click which
    changes the plots, which could otherwise remove 3D plots which still get
    the event), with a timer of the canvas (or at once, for canvases without
    timers, e.g. those of files)"""
    from matplotlib.backend_bases import TimerBase
    canvas._mcpl_timer = None#(the timer, kept until it is done)
    timer = canvas.new_timer(interval = 1)
    if type(timer) is TimerBase:
        fct(*args)
        return
    timer.single_shot = True
    timer.add_callback(fct,*args)
    timer.start()
    canvas._mcpl_timer = timer

def _remove_axes( ax ):
    """Remove the axes from their figure, with the event handlers which 3D axes
    connect to the canvas (which they do not disconnect themselves, so they
    would fail on the next mouse events)"""
    if ax.name == '3d' and ax.figure is not None:
        reg = ax.figure.canvas.callbacks
        for refs in list(reg.callbacks.values()):
            for cid, ref in list(refs.items()):
                if getattr(ref(),'__self__',None) is ax:
                    reg.disconnect(cid)
    ax.remove()

class FigurePane:
    """The plot of a view of a viewer (see mcpl._viewer.Viewer) in a box of a
    matplotlib figure, for the viewer in a window (see _viewer_widgets and
    _viewer_tk). It is only drawn again when the figure of the view changed,
    keeps the zoom when the same view is drawn again, and knows the plots of
    the overview (which can be clicked). The box
    is (left, right, bottom, top) in figure coordinates, with title_space less
    at the top for plots with a title, which is drawn at title_y. The fonts
    are those of matplotlib, with scale_fonts smaller in small boxes (see
    _font_scale)."""
    def __init__( self, fig, box, title_space = 0.05, title_y = None,
                  scale_fonts = False ):
        self.fig, self._box = fig, box
        self._title_space, self._title_y = title_space, title_y
        self.axes = []#(all axes of the plot, also those of colour bars)
        self._title = None
        self._key = self._figure = None#(the view and figure drawn)
        self._scale = None#(of the fonts, when drawn)
        self._scale_fonts = scale_fonts
        self._panels = []#(axes, view key) of the plots of the overview

    def _font_scale( self ):
        """The factor of the font sizes: 1 for boxes of at least 9 x 4.5 inches
        (e.g. in a large window), and less in smaller boxes (down to 0.6), so
        the texts of the plots do not collide (rounded, so the plots are only
        drawn again for larger changes of the size). In inches, as the font
        sizes (in points), and not in pixels, which are smaller on screens with
        a high resolution (e.g. Retina displays, where the dpi is doubled)."""
        if not self._scale_fonts:
            return 1.0
        left, right, bottom, top = self._box
        w = self.fig.get_figwidth() * ( right - left )
        h = self.fig.get_figheight() * ( top - bottom )
        return round( max( 0.6, min( 1.0, w / 9, h / 4.5 ) ), 1 )

    def show( self, viewer, key = None ):
        """Draw the figure of the view with the key (default the shown one) if
        it changed since it was drawn. Returns whether it was drawn."""
        key = viewer.current_key if key is None else key
        figure = viewer.figure(key = key)
        if figure is None:
            #(the drawn figure of the view is kept while the view has none,
            #e.g. while the file is read again, and another view is shown
            #without a figure until it has one):
            if key == self._key:
                return False
            self.clear()
            self._key = key
            return True
        scale = self._font_scale()
        if key == self._key and figure is self._figure and scale == self._scale:
            return False
        old_axes, old_key = self.axes, self._key
        self.clear()
        self._scale = scale
        left, right, bottom, top = self._box
        if figure.title:
            top -= self._title_space
        import matplotlib
        size = matplotlib.rcParams['font.size']
        self.axes = draw_in_box(self.fig,figure,left,right,bottom,top,fontsize = size * scale)
        if key == old_key:
            keep_zoom(old_axes,self.axes)
        if figure.title:
            y = self._title_y if self._title_y is not None else self._box[3]
            #(long titles are wrapped, within narrow windows):
            self._title = self.fig.text(0.5*(left+right),y,figure.title,ha='center',
                                        va='top',size=10 * scale,wrap=True)
        #(the first axes are those of the plots, in order, see draw_in):
        self._panels = ( [ ( ax, k ) for ax, k in zip(self.axes,viewer.overview_keys(key))
                           if k is not None ] if key.startswith('overview:') else [] )
        self._key, self._figure = key, figure
        return True

    def show_message( self, text, left = False ):
        """Show the text instead of a plot (until the next show or clear), in
        the middle, or as a block of lines aligned at the left (if left is
        set)"""
        if left:
            self._title = self.fig.text(0.06,0.5,text,ha='left',va='center',color='0.35',
                                        linespacing=1.6)
        else:
            self._title = self.fig.text(0.5,0.5,text,ha='center',va='center',color='0.5')

    def clear( self ):
        """Remove the plot (so the next show() draws it again)"""
        for ax in self.axes:
            _remove_axes(ax)
        if self._title is not None:
            self._title.remove()
        self.axes, self._title, self._panels = [], None, []
        self._key = self._figure = None

    def on_colour_bar( self, event ):
        """Whether the mouse (of a matplotlib mouse event) is over the colour
        bar of a plot shown on its own"""
        return ( not self._panels and event.inaxes is not None
                 and getattr(event.inaxes,'_mcpl_colour_bar',False) )

    def view_at( self, event ):
        """The key of the view of the plot of the overview under the mouse (of
        a matplotlib mouse event), or None"""
        for ax, key in self._panels:
            if event.inaxes is ax:
                return key
        return None
