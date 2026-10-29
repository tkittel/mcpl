
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

"""The description of figures which the plotting backends draw (see
plotting.py, which provides these classes)."""

__all__ = []

def _line_style( color ):
    """The colour (0 to 9, in the colour cycle of the backend) and line style
    ('solid', 'dashed' or 'dotted') of a curve with the colour index color (see
    StepHist): 10 colours with solid lines, then dashed, then dotted"""
    return color % 10, ( 'solid', 'dashed', 'dotted' )[ ( color // 10 ) % 3 ]

def _item_color( item, k ):
    """The colour index of the item (a curve, points or bars) which is the k-th
    of its panel: its color, by default k"""
    return item.color if item.color is not None else k

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

class Scatter3D:
    """Points in three dimensions, drawn as a 3D scatter plot by the backends
    which can (others show a message instead), with a label for the legend
    and a colour (an index into the colour cycle of the backend, as for
    StepHist) if given. The coordinates x, y and z are arrays of the same
    length, and the panel gives the label of the z axis (zlabel)."""
    def __init__( self, x, y, z, label = None, color = None ):
        self.x, self.y, self.z, self.label, self.color = x, y, z, label, color

class Text:
    """Message shown in the middle of a panel (e.g. "No data")."""
    def __init__( self, text ):
        self.text = text

class Correlation:
    """A correlation coefficient (from -1 to 1, or None if not known) shown in
    a panel, as in the correlation plots of the viewer: the number, on a
    background tinted from blue (-1) to red (1)."""
    def __init__( self, value ):
        self.value = value

    @property
    def text( self ):
        if self.value is None:
            return ''
        v = round(self.value,2)
        return f'{v:+.2f}' if v else '0.00'#(not -0.00)

class NewPlot:
    """The place of a new plot in the overview of the custom plots of the
    viewer (a big "+" with the text), which starts a new plot when clicked"""
    text = 'Add new plot'

class Panel:
    """One plot (a set of axes) with items like StepHist objects. Items with
    labels are shown in a legend. The zlabel is that of the z axis of 3D
    plots (see Scatter3D). With aspect, the y axis is drawn aspect times as
    long per unit as the x axis (e.g. 1 for the same scale on both axes)."""
    def __init__( self, title = None, xlabel = None, ylabel = None,
                  logx = False, logy = False, xlim = None, ylim = None,
                  items = None, zlabel = None, aspect = None ):
        self.title, self.xlabel, self.ylabel = title, xlabel, ylabel
        self.zlabel, self.aspect = zlabel, aspect
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
        if p is None:#(an empty cell of the grid)
            continue
        p.title, p.xlabel, p.ylabel = f(p.title), f(p.xlabel), f(p.ylabel)
        p.zlabel = f(getattr(p,'zlabel',None))
        for item in p.items:
            if isinstance(item,( StepHist, Scatter3D )):
                item.label = f(item.label)
            elif isinstance(item,Bars):
                item.labels = [ f(lbl) for lbl in item.labels ]
            elif isinstance(item,Text):
                item.text = f(item.text)
    return fig

class Figure:
    """Figure (page) with panels arranged in a grid of nrows x ncols (row by
    row, with None for empty cells of the grid)."""
    def __init__( self, title = None, panels = None, nrows = 1, ncols = 1 ):
        self.title = title
        self.panels = list(panels or [])
        self.nrows, self.ncols = nrows, ncols
        #(internal: whether it is a correlation plot of the viewer, whose
        #panels share their axes, see _viewer_overviews.overview_figure):
        self._correlation_plot = False
    def add( self, panel ):
        """Add a panel to the figure, and return it"""
        self.panels.append(panel)
        return panel
