
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

# Test the common part of the viewers with the widgets of a GUI toolkit
# (_viewer_widgets.WidgetViewer, used by Tk), with a fake toolkit which prints
# what it is asked to show.

import pathlib
import shutil

from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from mcpldev._viewer import Viewer
from mcpldev._viewer_widgets import WidgetViewer
from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

class FakeToolkit(WidgetViewer):
    """Prints what the toolkit is asked to show: the views, the status and the
    plot (which depend on the reading of the file) only when shown() is
    called (after the reading), the rest when it happens"""
    def __init__( self, viewer ):
        fig = Figure(figsize=(10,6))
        FigureCanvasAgg(fig)
        super().__init__(viewer,fig)
        self.state = {}

    def show_views( self, labels, current ):
        self.state['views'] = f'{len(labels)} views, shown: {labels[current]!r}'

    def show_status( self, first, second ):
        self.state['status'] = first

    def show_plot_field( self, text ):
        self.state['shown plot field'] = text

    def draw_plot( self ):
        self.state['plot'] = f'{len(self.pane.axes)} axes'

    def shown( self ):
        """Wait for the reading, and print the views, status and plot"""
        self.v.wait()
        self.on_timer()
        for k, value in self.state.items():
            print(f'   {k}: {value}')

    def show_field( self, field, text ):
        print(f'   field {field}: {text!r}')

    def show_line( self, text, style ):
        print(f'   line ({style}): {text}')

    def show_check( self, field, ok ):
        print(f'   check of {field}: {ok}')

    def focus_field( self, field ):
        print(f'   focus: {field}')

    def ask_file( self, action ):
        print(f'   asked for a file to {action}, suggested: {self.suggested_filename(action)}')

    def show_help( self ):
        print(f'   help shown: {ui_help_lines()} lines')

    def close_window( self ):
        print('   window closed')
        self.on_close()

def ui_help_lines():
    from mcpldev import _viewer_ui as ui
    return len(ui.help_text.splitlines())

def step( what ):
    print(f'==> {what}')

v = Viewer('example.mcpl')
t = FakeToolkit(v)
step('start, and the end of the reading')
t.start()
t.shown()
step('typing in the pick field: invalid, then valid with a hint')
t.on_field_edited('pick','pdgcode == neu')
t.on_field_edited('pick','pdgcode == neutron')
step('applying an invalid pick, then a valid one')
t.on_field_apply('pick','pdgcode = 1')
t.on_field_apply('pick','pdgcode == neutron')
t.shown()
step('Esc in the edit field restores its text')
t.on_field_edited('edit','x += ')
t.on_field_cancel('edit')
step('earlier texts of the pick field (Up and Down)')
print('   up:', repr(t.on_history('pick',-1)), '| down:', repr(t.on_history('pick',1)))
step('Tab completion')
print('  ', t.on_complete('pick','ekin < 1MeV and e',len('ekin < 1MeV and e'))[:3])
step('the collection is chosen from a menu')
print('   choices:', [ n for n, _ in t.menu_choices('collection') ])
t.on_field_edited('collection','beamz')
t.on_field_apply('collection','beamz')
t.shown()
t.on_field_apply('collection','default')
t.shown()
step('adding a plot (the field is emptied, and the plot shown)')
t.on_field_apply('plot','hypot(x,y)/cm;logy')
t.shown()
step('changing the shown plot, and removing it (empty text)')
t.on_field_edited('shown_plot','')
t.on_field_apply('shown_plot','hypot(x,y)/mm;logy')
t.shown()
t.on_field_apply('shown_plot','')
t.shown()
step('keys outside the fields')
for k in ( 'Down', 'MoveDown', 'Up', 'P', 'Enter', 'w', 'v', '?' ):
    print(f'  key {k}:')
    t.on_key(k)
    t.shown()
step('the file names (the suggested one is written, the same again is refused)')
name = t.suggested_filename('write')
t.on_file('write',name)
t.on_file('write',name)
t.on_file('state',None)
print('   written:', sorted( f.name for f in pathlib.Path('.').glob('*.mcpl*') if f.name != 'example.mcpl' ))
step('a click on a plot of the overview shows it on its own')
t.on_select(0)
t.shown()
ax = t.pane._panels[2][0]
bb = ax.get_window_extent()
t.on_click(MouseEvent('button_press_event',t.fig.canvas,(bb.x0+bb.x1)/2,(bb.y0+bb.y1)/2,button=1))
t.shown()
step('the buttons of the actions, and quit')
t.on_action('help')
t.on_action('quit')
print('closed:', t.closed)
