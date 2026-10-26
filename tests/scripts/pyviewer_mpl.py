
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

# NEEDS: numpy matplotlib

# Test the viewer in a matplotlib window (with the agg backend of matplotlib,
# and simulated keys and clicks).

import shutil
import signal

import matplotlib

matplotlib.use('agg')
import matplotlib.pyplot as plt
import mcpldev._viewer_tk
from matplotlib.backend_bases import KeyEvent, MouseEvent
from mcpldev._plotbackend_mpl_gui import MplViewer, run_viewer
from mcpldev._viewer import Viewer
from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

def texts( fig ):
    return [ t.get_text() for t in fig.texts if t.get_text().strip() and t.get_alpha() != 0.0 ]

v = Viewer('example.mcpl')
fig = plt.figure(figsize=(14,9))
g = MplViewer(v,fig)
g.start()
v.wait()
g.refresh()
fig.canvas.draw()
print('axes of the overview:', len(fig.axes))
print('status:', texts(fig)[len(v.views):len(v.views)+1])
#Keys, as matplotlib gives them to the viewer:
def key( k ):
    fig.canvas.callbacks.process('key_press_event',KeyEvent('key_press_event',fig.canvas,k))
for k in ['p'] + list('pdgcode == neu') + ['tab']:
    key(k)
print('pick being edited:', repr(g.editor.text), g.editor.ok, g.editor.hint)
key('enter')
v.wait()
g.refresh()
print('status after the pick:', v.status_lines()[0])
key('down')
key('down')
key('down')
v.wait()
g.refresh()
fig.canvas.draw()
print('view:', v.views[v.current][0], 'axes:', len(fig.axes))
for k in ['a'] + list('x/cm : y/cm') + ['enter']:
    key(k)
v.wait()
g.refresh()
fig.canvas.draw()
print('view:', v.views[v.current][0], 'axes (with the colour bar):', len(fig.axes))
key('up')
key('up')#(before the overview of the custom plots)
v.wait()
g.refresh()
fig.canvas.draw()
print('view:', v.views[v.current][0], 'axes (colour bar removed):', len(fig.axes))
#The default keys of matplotlib (like s and p) are those of the viewer:
key('i')
print('i edits the limit:', g.editor is not None and g.editor.field == 'limit')
key('l')
print('l while editing is text:', repr(g.editor.text))
key('escape')
#(but its keys for log scales, l and k, are used for the plot under the mouse):
def key_at( k, ax ):
    x, y = ax.transAxes.transform((0.5,0.5))
    fig.canvas.callbacks.process('key_press_event',KeyEvent('key_press_event',fig.canvas,k,x,y))
v.select_key('plot:x')
v.wait()
g.refresh()
ax = g._pane.axes[0]
key_at('l',ax)
key_at('k',ax)
#(which change the options logy and logx of the plot, see Viewer.toggle_scale):
print('plot after l and k over it:', v.current_key, 'editing:', g.editor is not None,
      '| message:', repr(g.message))
v.wait()
g.refresh()
ax = g._pane.axes[0]
print('scales after l and k over the plot:', ax.get_yscale(), ax.get_xscale())
key_at('l',ax)
print('plot after l again:', v.current_key, '| message:', repr(g.message))
key_at('k',ax)
key('h')
print('help shown:', g.show_help)
key('x')
print('help closed by a key:', not g.show_help)
#Clicking on a view (the text of the view "ekin"):
fig.canvas.draw()
target = next( t for t, what in g._targets if what == 3 )
bbox = target.get_window_extent()
ev = MouseEvent('button_press_event',fig.canvas,bbox.x0+2,(bbox.y0+bbox.y1)/2,button=1)
fig.canvas.callbacks.process('button_press_event',ev)
print('view after clicking on it:', v.views[v.current][0])
#The plots of the overview (with all its plots) can be clicked:
v.select(0)
g.refresh()
fig.canvas.draw()
print('view:', v.views[v.current][0], 'clickable plots:', [ k for _, k in g._pane._panels ])
ax = g._pane._panels[3][0]
bb = ax.get_window_extent()
ev = MouseEvent('button_press_event',fig.canvas,(bb.x0+bb.x1)/2,(bb.y0+bb.y1)/2,button=1)
fig.canvas.callbacks.process('button_press_event',ev)
print('view after clicking on a plot of the overview:', v.views[v.current][0])
#Completions in a popup, chosen with Down and inserted with Enter:
for k in ['a','e','tab','down','down']:
    key(k)
popup = [ t for t in texts(fig) if 'kinetic energy' in t or 'PDG code 11' in t or 'energy unit' in t ]
print('popup:', len(popup), 'lines, box:', any( type(a).__name__ == 'Rectangle' for a in fig.artists ),
      '| hint:', [ t for t in texts(fig) if t.startswith('Up/Down') ])
key('enter')
print('inserted:', repr(g.editor.text), 'popup closed:', not any( 'kinetic energy' in t for t in texts(fig) ))
key('escape')
#Enter on an added plot changes it:
for k in ['a'] + list('ekin/MeV') + ['enter']:
    key(k)
v.wait()
for k in ['enter'] + ['backspace'] * 3 + list('keV') + ['enter']:
    key(k)
v.wait()
print('added plot changed with Enter:', [ k for k, _ in v.views ][-1], 'current:', v.views[v.current][0])
key('q')
print('closed:', g.closed)
#Ctrl-C in the terminal while the window is shown (plt.show raises
#KeyboardInterrupt) quits like q:
def interrupted_show( *a, **kw ):
    raise KeyboardInterrupt
plt.show = interrupted_show
#(the matplotlib window, as where Tk can not show windows, also where there is
#a display):
mcpldev._viewer_tk._root = lambda : None
v = Viewer('example.mcpl')
run_viewer(v)
print('Ctrl-C while the window is shown: viewer stopped:',
      v._thread is None or not v._thread.is_alive(), 'windows left:', len(plt.get_fignums()))
#(and Ctrl-C, as a SIGINT signal, closes the window):
def signalled_show( *a, **kw ):
    signal.raise_signal(signal.SIGINT)
    print('   window closed by Ctrl-C:', len(plt.get_fignums()) == 0)
plt.show = signalled_show
v = Viewer('example.mcpl')
run_viewer(v)
print('SIGINT while the window is shown: viewer stopped:',
      v._thread is None or not v._thread.is_alive(), '| SIGINT handler restored:',
      signal.getsignal(signal.SIGINT) is signal.default_int_handler)
#Log scales of plots without positive values (e.g. bar charts without bars,
#when no particles are picked) are not used, as matplotlib can not draw them:
from mcpldev._plotbackend_mpl import draw_in
from mcpldev.plotting import Bars, Panel, StepHist
from mcpldev.plotting import Figure as PlotFigure

fig = plt.figure()
axes = draw_in(fig,fig.add_gridspec(1,1)[0],PlotFigure(nrows=1,ncols=2,panels=[
    Panel(logx=True,items=[Bars([],[],horizontal=True)]),
    Panel(logy=True,items=[StepHist([0,1,2],[0,0])]) ]))
fig.canvas.draw()
print('empty plots with log scales drawn, scales:', [ ( a.get_xscale(), a.get_yscale() ) for a in axes ])
