
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

"""Plotting backend using matplotlib."""

__all__ = []

import functools
from typing import ClassVar

from ._common import _determine_version
from ._numpy import np
from ._plotbackend import PlotBackend, numbered_filenames
from .plotting import (
    Bars,
    Correlation,
    Hist2D,
    NewPlot,
    Scatter3D,
    StepHist,
    Text,
    _line_style,
)


class Backend(PlotBackend):
    """Plotting with matplotlib. The matplotlib_backend option can be used to
    select a backend of matplotlib (e.g. 'agg' for saving files without a
    display)."""
    name = 'matplotlib'
    kind = 'window'
    priority = 100
    formats: ClassVar[dict] = { 'pdf' : 100, 'png' : 100, 'svg' : 100 }
    requirement = 'matplotlib'
    batch_options: ClassVar[dict] = { 'matplotlib_backend' : 'agg' }
    viewer_module = '_plotbackend_mpl_gui'

    @classmethod
    def is_available( cls ):
        import importlib.util
        return importlib.util.find_spec('matplotlib') is not None

    @classmethod
    def can_show( cls ):
        #Whether matplotlib picks (or was configured with) an interactive
        #backend, which it does not do when there is no display:
        import matplotlib
        name = matplotlib.get_backend().lower()
        if name.startswith('module://'):
            return True#(e.g. the inline backend of Jupyter)
        try:
            from matplotlib.backends import BackendFilter, backend_registry
            noninteractive = backend_registry.list_builtin(BackendFilter.NON_INTERACTIVE)
        except ImportError:
            from matplotlib.rcsetup import non_interactive_bk as noninteractive
        if name in [ e.lower() for e in noninteractive ]:
            return False
        #(matplotlib only checks for a display on Linux, so not e.g. on
        #FreeBSD, where it picks a window backend also without one):
        import os
        import sys
        if ( name not in ( 'nbagg', 'webagg' ) and sys.platform not in ( 'win32', 'darwin' )
             and not ( os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY') ) ):
            return False
        return True

    def __init__( self, matplotlib_backend = None ):
        import matplotlib
        if matplotlib_backend:
            matplotlib.use(matplotlib_backend)
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print()
            print("ERROR: importing matplotlib succeeded, but importing matplotlib.pyplot failed.")
            print("ERROR: This is rather unusual, an is perhaps related to issues with your chosen")
            print("ERROR: matplotlib backend, which you might have set globally in a matplotlib")
            print("ERROR: configuration file.")
            print()
            raise
        self._plt = plt

    def show( self, figures ):
        for f in figures:
            self._draw(f)
        self._plt.show()

    def save( self, figures, filename ):
        ext = self.check_format(filename)
        if ext == 'pdf':
            from matplotlib.backends.backend_pdf import PdfPages

            with PdfPages(filename) as pdf:
                for f in figures:
                    pdf.savefig(self._draw(f,saving=True))
                d = pdf.infodict()
                d['Title'] = ( 'Plots made with the mcpl Python package version'
                               f' {_determine_version()}' )
                d['Author'] = f'mcpl Python package v{_determine_version()}'
                d['Subject'] = 'mcpl plots'
                d['Keywords'] = 'mcpl'
            return [ filename ]
        fns = numbered_filenames(filename,len(figures))
        for f, fn in zip(figures,fns):
            self._draw(f,saving=True).savefig(fn)
        return fns

    def _draw( self, figure, saving = False, logo = True ):
        big = figure.nrows * figure.ncols > 1
        figsize = (15,8.5) if big else (8,6)
        if saving:
            #(figures which are not managed by pyplot, so saving them works
            #without a display, whatever the backend of matplotlib):
            from matplotlib.figure import Figure
            fig = Figure(figsize=figsize)
            axs = fig.subplots(figure.nrows,figure.ncols,squeeze=False)
        else:
            fig, axs = self._plt.subplots(figure.nrows,figure.ncols,squeeze=False,
                                          figsize=figsize)
        self._draw_axes(fig,list(axs.flat),figure)
        #The title and the logo are in a strip at the top:
        nlines = figure.title.count('\n') + 1 if figure.title else 0
        strip = max( logo_height(fig) if logo else 0.0,
                     ( nlines * 1.25 * 12 / 72 + 2 * _logo_margin ) / fig.get_figheight() )
        fig.tight_layout(rect=(0,0,1,1-strip))
        if figure.title:
            fig.suptitle(figure.title,y=1-0.5*strip,va='center',size=12)
        if logo:
            add_logo(fig)
        return fig

    def _draw_axes( self, fig, axlist, figure ):
        """Draw the panels of the figure on the axes (of the matplotlib figure
        fig), hiding the axes which are not needed"""
        import matplotlib.ticker
        #(the plots of a corner plot share their axes, see _corner_axes):
        corner = getattr(figure,'_corner',False)
        for i, panel in enumerate(figure.panels[:len(axlist)]):
            #(3D plots need axes with a 3D projection, instead of those made):
            if panel is not None and any( isinstance(it,Scatter3D) for it in panel.items ):
                spec = axlist[i].get_subplotspec()
                axlist[i].remove()
                axlist[i] = fig.add_subplot(spec,projection='3d')
        for ax, panel in zip(axlist,figure.panels):
            if panel is None:#(an empty cell of the grid)
                ax.set_visible(False)
            else:
                self._draw_panel(fig,ax,panel,compact=corner)
        if corner:
            _corner_axes(axlist,figure.nrows,figure.ncols)
        for ax in axlist[len(figure.panels):]:
            ax.set_visible(False)
        for ax in axlist:
            #Avoid overlapping labels on log axes spanning less than a decade:
            ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
            ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    def draw_in( self, fig, subplotspec, figure ):
        """Draw the figure in a part of a matplotlib figure (a SubplotSpec, as
        for the viewer). Returns all axes added to fig (also those of colour
        bars)."""
        before = set(fig.axes)
        space = 0.08 if getattr(figure,'_corner',False) else None
        gs = subplotspec.subgridspec(figure.nrows,figure.ncols,hspace=space or 0.55,
                                     wspace=space or 0.35)
        axlist = [ fig.add_subplot(gs[i,j]) for i in range(figure.nrows)
                   for j in range(figure.ncols) ]
        self._draw_axes(fig,axlist,figure)
        new = [ ax for ax in fig.axes if ax not in before ]
        for ax in new:
            ax._mcpl_home = _axes_view(ax)
        return new

    def _draw_panel( self, fig, ax, panel, compact = False ):
        """Draw the panel on the axes ax (without colour bars and legends if
        compact)"""
        import matplotlib.colors
        has_legend = False
        for i,item in enumerate(panel.items):
            if isinstance(item,StepHist):
                c, style = _line_style( item.color if item.color is not None else i )
                #(drawn as a line along the steps, with the ends down to 0 as
                #with stairs, since matplotlib finds the limits of lines much
                #faster than those of the patches of stairs):
                x = np.repeat(item.edges,2)
                y = np.concatenate(( [ 0.0 ], np.repeat(item.values,2), [ 0.0 ] ))
                ax.plot(x,y,label=item.label,linewidth=1.5,color=f'C{c}',linestyle=style)
                has_legend |= item.label is not None
            elif isinstance(item,Hist2D):
                #(empty bins are not coloured, also on a linear scale, where the
                #lowest colour would look like a few particles):
                v = np.asarray(item.values,dtype=float)
                v = np.where(v>0,v,np.nan) if item.logz else np.where(v!=0,v,np.nan)
                if np.isfinite(v).any():
                    im = ax.pcolormesh(item.xedges,item.yedges,np.asarray(v).T,
                                       norm=( matplotlib.colors.LogNorm()
                                              if item.logz else None ))
                    if not compact:
                        #(marked, see Pane.on_colour_bar):
                        fig.colorbar(im,ax=ax).ax._mcpl_colour_bar = True
            elif isinstance(item,Bars):
                pos = list(range(len(item.values)))
                colors = [ f'C{c%10}' for c in item.colors ] if item.colors else None
                if item.horizontal:
                    #(each label above its bar, inside the plot, so long labels
                    #do not need a margin, and never cover a bar):
                    import matplotlib.transforms
                    ax.barh([ p + 0.2 for p in pos ],item.values,height=0.5,color=colors)
                    tr = matplotlib.transforms.blended_transform_factory(ax.transAxes,ax.transData)
                    for p, label in zip(pos,item.labels):
                        ax.text(0.01,p - 0.25,label,transform=tr,ha='left',va='center',
                                fontsize='small',clip_on=True)
                    ax.set_yticks([])
                    ax.set_ylim(len(pos) - 0.4,-0.6)
                else:
                    ax.bar(pos,item.values,width=0.7,linewidth=0,color=colors)
                    ax.set_xticks(pos)
                    ax.set_xticklabels(item.labels,fontsize='small')
            elif isinstance(item,Scatter3D):
                c, _ = _line_style( item.color if item.color is not None else i )
                ax.scatter(item.x,item.y,item.z,s=2,alpha=0.6,color=f'C{c}',label=item.label,
                           depthshade=False)
                has_legend |= item.label is not None
            elif isinstance(item,Text):
                ax.text(0.5,0.5,item.text,ha='center',va='center',
                        transform=ax.transAxes)
            elif isinstance(item,Correlation):
                _draw_correlation(ax,item)
            elif isinstance(item,NewPlot):
                _draw_new_plot(ax,item)
        import warnings
        with warnings.catch_warnings():
            #(plots without positive values, e.g. when no particles are picked,
            #are just empty, which matplotlib warns about):
            warnings.filterwarnings('ignore',message='Data has no positive values')
            #(only with positive values, which matplotlib can not draw without,
            #e.g. for bar charts without bars):
            if panel.logx and _positive(ax.dataLim.intervalx):
                ax.set_xscale('log')
            if panel.logy and _positive(ax.dataLim.intervaly):
                ax.set_yscale('log')
        if panel.xlim:
            ax.set_xlim(*panel.xlim)
        if panel.ylim:
            ax.set_ylim(*panel.ylim)
        if getattr(panel,'aspect',None):
            ax.set_aspect(panel.aspect,adjustable='box')
        if panel.title:
            ax.set_title(panel.title)
        if panel.xlabel:
            ax.set_xlabel(panel.xlabel,fontsize='small')
        if panel.ylabel:
            ax.set_ylabel(panel.ylabel)
        if getattr(panel,'zlabel',None) and hasattr(ax,'set_zlabel'):
            ax.set_zlabel(panel.zlabel)
        if has_legend and not compact:
            #(with larger points in the legend than in 3D plots):
            ax.legend(fontsize='small',markerscale=4 if hasattr(ax,'set_zlabel') else 1)
        if not getattr(ax,'_mcpl_no_grid',False):
            ax.grid(alpha=0.3)

def _positive( interval ):
    """Whether the interval of the data (lo, hi) has positive values"""
    return bool( np.isfinite(interval[1]) and interval[1] > 0 )

def _draw_correlation( ax, item ):
    """Draw the correlation coefficient on the axes, which are only its cell"""
    import matplotlib
    if item.value is not None:
        #(tinted from white, towards blue or red with the size of the value):
        rgb = matplotlib.colormaps['coolwarm'](0.5 + 0.5 * item.value)
        ax.set_facecolor(rgb)
        ax.text(0.5,0.5,item.text,ha='center',va='center',transform=ax.transAxes,
                fontsize='large',fontweight='bold' if abs(item.value) >= 0.5 else 'normal')
    ax.set_xticks([])
    ax.set_yticks([])
    ax._mcpl_no_grid = True#(see _draw_panel)

def _inner_decades( lo, hi, n = 2 ):
    """At most n powers of 10 (every k-th) between lo and hi (lo > 0), away
    from the ends (as MaxNLocator with prune for linear axes)"""
    import math
    a, b = math.log10(lo), math.log10(hi)
    margin = 0.1 * ( b - a )
    decades = list(range( math.ceil( a + margin ), math.floor( b - margin ) + 1 ))
    step = max( 1, math.ceil( len(decades) / n ) )
    return [ 10.0**d for d in decades[::step] ]

def _draw_new_plot( ax, item ):
    """Draw the place of a new plot on the axes: a big "+" with the text, in a
    dashed frame"""
    ax.text(0.5,0.55,'+',ha='center',va='center',transform=ax.transAxes,fontsize=60,
            color='C0')
    ax.text(0.5,0.25,item.text,ha='center',va='center',transform=ax.transAxes,
            fontsize='large',color='C0')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_linestyle('--')
        spine.set_color('C0')
    ax._mcpl_no_grid = True#(see _draw_panel)

def _corner_axes( axlist, nrows, ncols ):
    """The axes of a corner plot (see _viewer_overviews.corner_cells): the labels
    of the x axes only in the bottom row, and of the y axes only in the left
    column, with the histograms on the diagonal without their y axes (the x
    axes of each column are those of the same expression)"""
    import matplotlib.ticker
    for i, ax in enumerate(axlist[:nrows*ncols]):
        r, c = divmod(i,ncols)
        if getattr(ax,'_mcpl_no_grid',False):
            continue#(the cells of correlation coefficients, without axes)
        #(without the ticks at the ends, whose labels would meet those of the
        #neighbouring plots):
        for axis, lim in ( ( ax.xaxis, ax.get_xlim() ), ( ax.yaxis, ax.get_ylim() ) ):
            if axis.get_scale() == 'linear':
                axis.set_major_locator(matplotlib.ticker.MaxNLocator(3,prune='both'))
            else:
                axis.set_major_locator(matplotlib.ticker.FixedLocator(_inner_decades(*lim)))
                axis.set_minor_locator(matplotlib.ticker.NullLocator())
        if r < nrows - 1:
            ax.set_xlabel('')
            ax.tick_params(labelbottom=False)
        if r == c:
            ax.set_ylabel('')
            ax.set_yticks([])
        elif c > 0:
            ax.set_ylabel('')
            ax.tick_params(labelleft=False)

_logo_inches = 0.4#(height of the logo, and its margin)
_logo_margin = 0.06

def logo_height( fig ):
    """The height of the logo with its margins, as a fraction of the height of
    the matplotlib figure"""
    return ( _logo_inches + 2 * _logo_margin ) / fig.get_figheight()

@functools.cache
def _logo_image():
    """The MCPL logo as an image for matplotlib (decoded once, read-only)"""
    import io

    import matplotlib.image

    from ._logo import logo_png
    img = matplotlib.image.imread(io.BytesIO(logo_png()))
    img.flags.writeable = False
    return img

def add_logo( fig, left = False ):
    """Add the MCPL logo to the top right (or left) corner of the matplotlib
    figure"""
    img = _logo_image()
    fw, fh = fig.get_figwidth(), fig.get_figheight()
    w = _logo_inches * img.shape[1] / img.shape[0]
    x = _logo_margin / fw if left else 1 - ( w + _logo_margin ) / fw
    ax = fig.add_axes(( x, 1 - ( _logo_inches + _logo_margin ) / fh, w / fw, _logo_inches / fh ))
    ax.imshow(img)
    ax.set_axis_off()
    ax.set_navigate(False)
    return ax

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
        return Backend.__new__(Backend).draw_in(fig,gs[0,0],figure)

def figure_png( figure, width, height ):
    """The figure drawn as a PNG image of width x height pixels (with smaller
    fonts, for previews of plots)"""
    import io

    import matplotlib
    from matplotlib.figure import Figure
    dpi = 80
    fig = Figure(figsize=( width / dpi, height / dpi ),dpi=dpi)
    with matplotlib.rc_context({ 'font.size' : 7 }):
        axs = fig.subplots(figure.nrows,figure.ncols,squeeze=False)
        Backend.__new__(Backend)._draw_axes(fig,list(axs.flat),figure)
        fig.tight_layout()
    out = io.BytesIO()
    fig.savefig(out,format='png',dpi=dpi)
    return out.getvalue()

def after_event( canvas, fct, *args ):
    """Call fct(*args) after the event being handled (e.g. a click which
    changes the plots, which could otherwise remove 3D plots which still get
    the event), with a timer of the canvas (or at once, for canvases without
    timers, e.g. those of files)"""
    from matplotlib.backend_bases import TimerBase
    timer = canvas.new_timer(interval = 1)
    if type(timer) is TimerBase:
        fct(*args)
        return
    timer.single_shot = True
    timer.add_callback(fct,*args)
    canvas._mcpl_timer = timer#(kept until it is done)
    timer.start()

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
    matplotlib figure, for the viewers with matplotlib figures (in a window,
    in Jupyter with ipympl, and with Tk). It is only drawn again when the
    figure of the view changed, keeps the zoom when the same view is drawn
    again, and knows the plots of the overview (which can be clicked). The box
    is (left, right, bottom, top) in figure coordinates, with title_space less
    at the top for plots with a title, which is drawn at title_y. The font size
    of the plots is fontsize (or overview_fontsize for several plots), if
    given."""
    def __init__( self, fig, box, title_space = 0.05, title_y = None,
                  title_size = 10, fontsize = None, overview_fontsize = None ):
        self.fig, self._box = fig, box
        self._title_space, self._title_y = title_space, title_y
        self._title_size = title_size
        self._fontsize, self._overview_fontsize = fontsize, overview_fontsize
        self.axes = []#(all axes of the plot, also those of colour bars)
        self._title = None
        self._key = self._figure = None#(the view and figure drawn)
        self._panels = []#(axes, view key) of the plots of the overview

    def show( self, viewer, key = None ):
        """Draw the figure of the view with the key (default the shown one) if
        it changed since it was drawn. Returns whether it was drawn."""
        key = viewer.current_key if key is None else key
        figure = viewer.figure(key = key)
        if figure is None:
            if key == self._key:
                return False
            self.clear()
            return True
        if key == self._key and figure is self._figure:
            return False
        old_axes, old_key = self.axes, self._key
        self.clear()
        left, right, bottom, top = self._box
        if figure.title:
            top -= self._title_space
        several = len(figure.panels) > 1
        self.axes = draw_in_box(self.fig,figure,left,right,bottom,top,
                                fontsize = ( self._overview_fontsize if several
                                             and self._overview_fontsize else self._fontsize ))
        if key == old_key:
            keep_zoom(old_axes,self.axes)
        if figure.title:
            y = self._title_y if self._title_y is not None else self._box[3]
            #(long titles are wrapped, within narrow windows):
            self._title = self.fig.text(0.5*(left+right),y,figure.title,ha='center',
                                        va='top',size=self._title_size,wrap=True)
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

def widget_figure( widget_class ):
    """A matplotlib figure for a panel of ipywidgets (for the viewer in
    Jupyter), if the backend of matplotlib (ipympl) gives figures which are
    widgets of the class (else None)"""
    import sys
    if 'matplotlib' not in sys.modules:
        return None
    import matplotlib.pyplot as plt
    #(the backend has several names, e.g. widget or ipympl, so the canvas of a
    #new figure is checked):
    with plt.ioff():
        fig = plt.figure(figsize=(8,5.5))
    if not isinstance(fig.canvas,widget_class):
        plt.close(fig)
        return None
    fig.canvas.header_visible = False
    fig.canvas.layout.width = '100%'
    return fig
