
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
from ._figures import (
    Bars,
    Correlation,
    Hist2D,
    NewPlot,
    Scatter3D,
    StepHist,
    Text,
    _item_color,
    _line_style,
)
from ._numpy import np
from ._plotbackend import PlotBackend, numbered_filenames


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
            print("ERROR: This is rather unusual, and is perhaps related to issues with your chosen")
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

    def _draw( self, figure, saving = False ):
        #(saved figures are not managed by pyplot, so saving works without a
        #display, whatever the backend of matplotlib):
        return draw_figure(figure,None if saving else self._plt)

def draw_figure( figure, plt = None, logo = True ):
    """The figure (see mcpl.plotting) drawn as a matplotlib figure: one of
    pyplot (plt), or else one which pyplot does not manage (for saving it),
    with the MCPL logo if logo is set"""
    big = figure.nrows * figure.ncols > 1
    figsize = (15,8.5) if big else (8,6)
    if plt is None:
        from matplotlib.figure import Figure
        fig = Figure(figsize=figsize)
        axs = fig.subplots(figure.nrows,figure.ncols,squeeze=False)
    else:
        fig, axs = plt.subplots(figure.nrows,figure.ncols,squeeze=False,figsize=figsize)
    _draw_axes(fig,list(axs.flat),figure)
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

def _draw_axes( fig, axlist, figure ):
    """Draw the panels of the figure on the axes (of the matplotlib figure
    fig), hiding the axes which are not needed"""
    import matplotlib.ticker
    #(the plots of a correlation plot share their axes, see _correlation_axes):
    correlation_plot = figure._correlation_plot
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
            _draw_panel(fig,ax,panel,compact=correlation_plot,
                             several=len(figure.panels) > 1)
    if correlation_plot:
        _correlation_axes(axlist,figure.nrows,figure.ncols)
    for ax in axlist[len(figure.panels):]:
        ax.set_visible(False)
    for ax in axlist:
        #Avoid overlapping labels on log axes spanning less than a decade:
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())

def _draw_panel( fig, ax, panel, compact = False, several = False ):
    """Draw the panel on the axes ax (without colour bars and legends if
    compact, and with fewer labels on colour bars if one of several)"""
    import matplotlib.colors
    import matplotlib.ticker
    has_legend = False
    for i,item in enumerate(panel.items):
        if isinstance(item,StepHist):
            c, style = _line_style(_item_color(item,i))
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
                    bar = fig.colorbar(im,ax=ax)
                    bar.ax._mcpl_colour_bar = True#(see FigurePane.on_colour_bar)
                    if several and item.logz and _has_decade(im.norm.vmin,im.norm.vmax):
                        #(only the powers of 10 are labelled, as on the
                        #axes, see _draw_axes, since the labels of the
                        #others collide in the small plots of overviews):
                        bar.ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        elif isinstance(item,Bars):
            pos = list(range(len(item.values)))
            colors = [ f'C{_line_style(c)[0]}' for c in item.colors ] if item.colors else None
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
            c, _ = _line_style(_item_color(item,i))
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
        #(light grey for 0, towards blue or red with the size of the value):
        rgb = matplotlib.colormaps['coolwarm'](0.5 + 0.5 * item.value)
        ax.set_facecolor(rgb)
        ax.text(0.5,0.5,item.text,ha='center',va='center',transform=ax.transAxes,
                fontsize='large',fontweight='bold' if abs(item.value) >= 0.5 else 'normal')
    ax.set_xticks([])
    ax.set_yticks([])
    ax._mcpl_no_grid = True#(see _draw_panel)

def _has_decade( lo, hi ):
    """Whether there is a power of 10 between lo and hi (lo > 0)"""
    import math
    return math.floor(math.log10(hi)) >= math.ceil(math.log10(lo))

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

def _correlation_axes( axlist, nrows, ncols ):
    """The axes of a correlation plot (see _viewer_overviews.correlation_cells): the labels
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
        #(the expression of the row, as the labels of the y axes of the left
        #column, also for the histogram at the top left):
        expression = ax.get_xlabel()
        if r < nrows - 1:
            ax.set_xlabel('')
            ax.tick_params(labelbottom=False)
        if r == c:
            ax.set_ylabel('' if c > 0 else expression)
            ax.set_yticks([])
        elif c > 0:
            ax.set_ylabel('')
            ax.tick_params(labelleft=False)

_logo_inches = 0.4#(height of the logo, in inches)
_logo_margin = 0.06#(margin around the logo, in inches)

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
    """Add the MCPL logo at the top right (or left) of the matplotlib
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
