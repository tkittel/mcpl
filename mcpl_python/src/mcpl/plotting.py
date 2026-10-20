
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

"""Backend-independent description of plots, and functions to show or save
them. Plots are described with the Figure, Panel and item classes below (which
hold numbers, not graphics objects), and are drawn by one of the plotting
backends: matplotlib (see available_backends()), unicode or ascii (which
draw the plots as text, in the terminal or in .txt files), or a custom
backend (see Backend and register_backend()).

Unless a backend is specified when plotting (or set with
set_default_backend()), plots are shown with the preferred available backend
which can show them: in a window with matplotlib, or else in the terminal
(with unicode, or else ascii, characters), or always in the terminal with
terminal=True. Plots are saved with the backend which can create files of the
format given by the extension of the file name.

For instance:

   from mcpl.plotting import Figure, Panel, StepHist
   from mcpl.plotting import save
   hist = StepHist(edges,values)
   panel = Panel( title = 'My histogram',
                  xlabel = 'x [cm]',
                  items = [ hist ] )
   save( Figure( panels = [ panel ] ), 'myplot.pdf' )
"""

__all__ = [ 'Backend', 'Bars', 'Figure', 'Hist2D', 'Panel', 'StepHist', 'Text',
            'available_backends', 'formats', 'register_backend', 'resolution',
            'save', 'set_default_backend', 'show' ]

from ._plotbackend import (
    PlotBackend,
    _available_backends,
    _create,
    _formats,
    _register_backend,
    _save_backend,
    _set_default_backend,
    _show_backend,
)

Backend = PlotBackend


def _line_style( color ):
    """The colour (0 to 9, in the colour cycle of the backend) and line style
    ('solid', 'dashed' or 'dotted') of a curve with the colour index color (see
    StepHist): 10 colours with solid lines, then dashed, then dotted"""
    return color % 10, ( 'solid', 'dashed', 'dotted' )[ ( color // 10 ) % 3 ]

class StepHist:
    """1D histogram drawn as a step line. The bin edges have one more entry
    than the values. The color is an index into the colour cycle of the
    backend, which has 10 colours drawn with solid lines, then dashed, then
    dotted (see _line_style), by default the position of the item in the
    panel."""
    def __init__( self, edges, values, label = None, color = None ):
        self.edges, self.values, self.label = edges, values, label
        self.color = color

class Hist2D:
    """2D histogram drawn as a coloured map (with logarithmic colour scale if
    logz is set). The values have shape (len(xedges)-1,len(yedges)-1)."""
    def __init__( self, xedges, yedges, values, logz = True ):
        self.xedges, self.yedges, self.values = xedges, yedges, values
        self.logz = logz

class Bars:
    """Bar chart with a bar for each label (horizontal if horizontal is set).
    The colors are indices into the colour cycle of the backend, one for each
    bar (by default all bars have the first colour)."""
    def __init__( self, labels, values, horizontal = False, colors = None ):
        self.labels, self.values, self.horizontal = labels, values, horizontal
        self.colors = colors

class Text:
    """Message shown in the middle of a panel (e.g. "No data")."""
    def __init__( self, text ):
        self.text = text

class Panel:
    """One plot (a set of axes) with items like StepHist objects. Items with
    labels are shown in a legend."""
    def __init__( self, title = None, xlabel = None, ylabel = None,
                  logx = False, logy = False, xlim = None, ylim = None,
                  items = None ):
        self.title, self.xlabel, self.ylabel = title, xlabel, ylabel
        self.logx, self.logy, self.xlim, self.ylim = logx, logy, xlim, ylim
        self.items = list(items or [])
    def add( self, item ):
        """Add an item (e.g. a StepHist) to the panel, and return it"""
        self.items.append(item)
        return item

def _map_texts( figure, fct ):
    """Copy of the figure with the function applied to all its texts (titles,
    labels and texts)"""
    import copy
    fig = copy.deepcopy(figure)
    def f( t ):
        return fct(t) if isinstance(t,str) else t
    fig.title = f(fig.title)
    for p in fig.panels:
        p.title, p.xlabel, p.ylabel = f(p.title), f(p.xlabel), f(p.ylabel)
        for item in p.items:
            if isinstance(item,StepHist):
                item.label = f(item.label)
            elif isinstance(item,Bars):
                item.labels = [ f(lbl) for lbl in item.labels ]
            elif isinstance(item,Text):
                item.text = f(item.text)
    return fig

class Figure:
    """Figure (page) with panels arranged in a grid of nrows x ncols."""
    def __init__( self, title = None, panels = None, nrows = 1, ncols = 1 ):
        self.title = title
        self.panels = list(panels or [])
        self.nrows, self.ncols = nrows, ncols
    def add( self, panel ):
        """Add a panel to the figure, and return it"""
        self.panels.append(panel)
        return panel

def available_backends():
    """Names of the plotting backends which can be used (i.e. for which the
    required Python packages are installed), in order of preference for
    showing plots."""
    return _available_backends()

def register_backend( backend_class ):
    """Register a custom plotting backend, a subclass of Backend, which can
    then be selected by its name (and is also used when no backend is
    specified, according to its kind, priority and formats, see Backend)."""
    _register_backend(backend_class)

def set_default_backend( backend ):
    """Set the plotting backend to use when no backend is specified: the name
    of a backend, or a Backend object. If that backend is not available when
    plotting, an error is raised. Use None to go back to choosing the backend
    automatically."""
    _set_default_backend(backend)

def formats( backend = None ):
    """File extensions of the formats which the backend (name or Backend
    object) can save in this installation, or which any of the available
    backends can save if no backend is given (and no default is set)."""
    return list(_formats(backend))

def resolution( backend = None, terminal = False, **options ):
    """Number of bins which histograms should have to match the resolution of
    the plots of the backend (name or Backend object, default is the one which
    show() would use), as a tuple (nx,ny), or None if the backend has no
    preference. The text backends have a resolution (their numbers of columns
    and rows), so e.g. mcpl.histogram(..., bins =
    mcpl.plotting.resolution("unicode")[0]) makes a histogram which is shown
    without any resampling. Further keyword arguments are options for the
    backend (see show())."""
    return _create(_show_backend(backend,terminal),**options).resolution()

def _as_list( figures ):
    return [ figures ] if isinstance(figures,Figure) else list(figures)

def show( figures, backend = None, terminal = False, **options ):
    """Show a Figure (or a list of figures) interactively, with the plotting
    backend of the given name (or a Backend object), or else with the
    preferred available backend which can show plots here (in a window, or
    else in the terminal), or with the preferred backend for
    the terminal if terminal is True. Further keyword arguments are options
    for the backend, named with the backend name as prefix (e.g.
    matplotlib_backend='qtagg' or unicode_width=100)."""
    _create(_show_backend(backend,terminal),**options).show(_as_list(figures))

def save( figures, filename, backend = None, **options ):
    """Save a Figure (or a list of figures) in a file, with the plotting
    backend of the given name (or a Backend object), or else with the backend
    which can create files of the format given by the extension of the
    filename: .pdf, .png or .svg with matplotlib, and .txt with unicode. If
    the format can only hold one figure, and there are more figures, the
    files get numbered names (e.g. plot_1.png, plot_2.png).
    Returns the list of created files. Further keyword arguments are options
    for the backend (see show())."""
    return _create(_save_backend(filename,backend),**options).save(_as_list(figures),filename)
