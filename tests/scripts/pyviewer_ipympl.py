
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

# NEEDS: numpy matplotlib ipywidgets ipympl

# Test the viewer in Jupyter with the ipympl backend of matplotlib (as after
# %matplotlib widget), where the plot is an interactive matplotlib figure, and
# that zooms are kept when plots are updated (also in the matplotlib window).

import shutil

import matplotlib
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from mcpldev._plotbackend_mpl_gui import MplViewer
from mcpldev._viewer import Viewer
from mcpldev._viewer_jupyter import JupyterViewer
from MCPLTestUtils.dirs import test_data_dir

#(as %matplotlib widget does):
matplotlib.use('widget')

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

def click( fig, ax ):
    x, y = ax.transAxes.transform((0.5,0.5))
    MouseEvent('button_press_event',fig.canvas,x,y,1)._process()

v = Viewer('example.mcpl')
j = JupyterViewer(v)
j.start()
v.wait()
j.refresh()
print('interactive figure shown:', j._right.children[1] is j._mplfig.canvas,
      'warning:', repr(j._warning.value))
print('axes of the overview:', len(j._pane.axes), 'clickable:', len(j._pane._panels))
click(j._mplfig,j._pane.axes[3])
print('view after clicking the 4th plot:', v.views[v.current][0],
      'selected in the list:', j._views.index == v.current)
j._pane.axes[0].set_xlim(-50,50)#(a zoom)
j._fields['pick'].value = 'pdgcode == neutron'
v.wait()
j.refresh()
print('x range after the pick, zoom kept:', j._pane.axes[0].get_xlim())
j._views.index = [ k for k, _ in v.views ].index('plot:ekin')
print('x range of another view, not zoomed:', j._pane.axes[0].get_xlim() != (-50,50))
j.close()

#The matplotlib window (on a figure without a window):
fig = Figure()
FigureCanvasAgg(fig)
v = Viewer('example.mcpl',view='x')
m = MplViewer(v,fig)
m.start()
v.wait()
m.refresh(plot=True)
m._pane.axes[0].set_xscale('log')#(as changed by the user)
m._pane.axes[0].set_xlim(1,100)
v.set('limit','500')
v.wait()
m.refresh(plot=True)
print('window, after changing the limit:', m._pane.axes[0].get_xscale(),
      m._pane.axes[0].get_xlim())
m._on_close(None)
