
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
from .plotting import Bars, Hist2D, StepHist, Text


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
        return name not in [ e.lower() for e in noninteractive ]

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
        for ax, panel in zip(axlist,figure.panels):
            self._draw_panel(fig,ax,panel)
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
        gs = subplotspec.subgridspec(figure.nrows,figure.ncols,hspace=0.55,
                                     wspace=0.35)
        axlist = [ fig.add_subplot(gs[i,j]) for i in range(figure.nrows)
                   for j in range(figure.ncols) ]
        self._draw_axes(fig,axlist,figure)
        new = [ ax for ax in fig.axes if ax not in before ]
        for ax in new:
            ax._mcpl_home = _axes_view(ax)
        return new

    def _draw_panel( self, fig, ax, panel ):
        import matplotlib.colors
        has_legend = False
        for i,item in enumerate(panel.items):
            if isinstance(item,StepHist):
                c = item.color if item.color is not None else i
                ax.stairs(item.values,item.edges,label=item.label,
                          linewidth=1.5,color=f'C{c%10}')
                has_legend |= item.label is not None
            elif isinstance(item,Hist2D):
                v = np.where(item.values>0,item.values,np.nan) if item.logz else item.values
                if np.isfinite(v).any():
                    im = ax.pcolormesh(item.xedges,item.yedges,np.asarray(v).T,
                                       norm=( matplotlib.colors.LogNorm()
                                              if item.logz else None ))
                    fig.colorbar(im,ax=ax)
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
            elif isinstance(item,Text):
                ax.text(0.5,0.5,item.text,ha='center',va='center',
                        transform=ax.transAxes)
        if panel.logx:
            ax.set_xscale('log')
        if panel.logy:
            ax.set_yscale('log')
        if panel.xlim:
            ax.set_xlim(*panel.xlim)
        if panel.ylim:
            ax.set_ylim(*panel.ylim)
        if panel.title:
            ax.set_title(panel.title)
        if panel.xlabel:
            ax.set_xlabel(panel.xlabel,fontsize='small')
        if panel.ylabel:
            ax.set_ylabel(panel.ylabel)
        if has_legend:
            ax.legend(fontsize='small')
        ax.grid(alpha=0.3)

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
