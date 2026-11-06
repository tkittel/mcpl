
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

# Test the logic of the viewer in a window (_viewer_widgets.WindowLogic, used
# by Tk) without a display, with a fake front end which prints what it is
# asked to show.

import pathlib
import shutil

from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from mcpldev import _viewer_ui as ui
from mcpldev._viewer import Viewer
from mcpldev._viewer_overviews import Moments
from mcpldev._viewer_widgets import WindowFrontend, WindowLogic
from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

class FakeToolkit(WindowFrontend):
    """Prints what the front end is asked to show: the views, the status, and
    the plot (which depend on the reading of the file) only when shown() is
    called (after the reading), the rest when it happens. Its logic is
    self.logic."""
    def __init__( self, viewer ):
        fig = Figure(figsize=(10,6))
        FigureCanvasAgg(fig)
        self.logic = WindowLogic(viewer,self,fig)
        self.state = {}

    def show_views( self, cards ):
        c = next( c for c in cards if c.key == self.logic.selected_card() )
        self.state['views'] = ( f'{len(cards)} cards, selected: {c.name!r} (badges {c.badges}),'
                                f' shown: {self.logic.shown_key}' )
        self.state['inactive cards'] = [ f'{c.name}: {c.status}' for c in cards if c.inactive ]
        self.state['thumbnails'] = sum( c.image and self.logic.thumbnail(c.key,84,50) is not None
                                        for c in cards )
        self.state['removable cards'] = [ c.name for c in cards if c.removable ]

    def show_status( self, first, second ):
        self.state['status'] = first

    def show_plot_field( self, text, axes ):
        self.state['shown plot field'] = ( text, axes )

    def show_controls( self, controls ):
        self.state['settings'] = None if controls is None else ( controls[0], { name : shown
                                                       for name, _, _, shown, _ in controls[1] } )
        self.state['bins used'] = None if controls is None else next(
            ( used for name, _, _, _, used in controls[1] if name == 'bins' ), None )

    def draw_plot( self ):
        self.state['plot'] = f'{len(self.logic.pane.axes)} axes'

    def shown( self ):
        """Wait for the reading, and print the views, status, and plot"""
        self.logic.v.wait()
        self.logic.on_timer()
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
        print(f'   asked for a file to {action}, suggested: {self.logic.suggested_filename(action)}')

    answer = False#(the answer of ask_yes_no)

    def ask_yes_no( self, question ):
        print(f'   asked: {question} {"yes" if self.answer else "no"}')
        return self.answer

    def show_plot_menu( self, entries ):
        print('   menu of the plot:', [ label for label, _ in entries ])

    def show_help( self ):
        print(f'   help shown: {ui_help_lines()} lines')

    def open_composer( self ):
        print('   composer opened')

    def close_window( self ):
        print('   window closed')
        self.logic.on_close()

def ui_help_lines():
    return len(ui.help_text.splitlines())

def step( what ):
    print(f'==> {what}')

def click( key, button = 1 ):
    """Click (with the button) on the plot of the view with the key in the
    shown overview (drawn first)"""
    t.logic.v.wait()
    t.logic.on_timer()
    pane = t.logic.pane
    for ax, *_ in pane._panels:
        bb = ax.get_window_extent()
        event = MouseEvent('button_press_event',t.logic.fig.canvas,(bb.x0+bb.x1)/2,
                           (bb.y0+bb.y1)/2,button=button)
        if pane.view_at(event) == key:
            t.logic.on_click(event)
            return
    print(f'   no plot {key} in the overview')

v = Viewer('example.mcpl',state={'groups':['spectra','fields','correlations']})
t = FakeToolkit(v)
step('start, and the end of the reading')
t.logic.start()
t.shown()
step('typing in the edit field: invalid, then valid with a hint')
t.logic.on_field_edited('edit','pdgcode == neu')
t.logic.on_field_edited('edit','pdgcode == neutron')
step('applying an invalid edit, then a valid one')
t.logic.on_field_apply('edit','x = 2')
t.logic.on_field_apply('edit','pdgcode == neutron')
t.shown()
step('Esc in the edit field restores its text')
t.logic.on_field_edited('edit','x += ')
t.logic.on_field_cancel('edit')
step('earlier texts of the edit field (Up and Down)')
print('   up:', repr(t.logic.on_history('edit',-1)), '| down:', repr(t.logic.on_history('edit',1)))
step('Tab completion')
t.logic.on_field_edited('edit','ekin < 1MeV and e')
print('  ', t.logic.on_complete('edit','ekin < 1MeV and e',len('ekin < 1MeV and e'))[:3])
print('   (not mentioned after it was used)')
t.logic.on_field_edited('edit','')
step('the groups of plots are chosen in a field')
t.logic.on_field_edited('groups','beamz')
t.logic.on_field_apply('groups','beamz')
t.shown()
t.logic.on_field_apply('groups','spectra,fields,correlations')
t.shown()
step('adding a plot (the field is emptied, and the plot shown)')
t.logic.on_field_apply('plot','hypot(x,y)/cm;logy')
t.shown()
step('changing the shown plot, and removing it (empty text)')
t.logic.on_field_edited('shown_plot','')
t.logic.on_field_apply('shown_plot','hypot(x,y)/mm;logy')
t.shown()
t.logic.on_field_apply('shown_plot','')
t.shown()
step('keys outside the fields')
for k in ( 'Down', 'MoveDown', 'Up', 'E', 'Enter', 'w', 'v', '?' ):
    print(f'  key {k}:')
    t.logic.on_key(k)
    t.shown()
step('the file names (the suggested one is written, and the same again only if the'
     ' user agrees, unless the file dialog asked)')
name = t.logic.suggested_filename('write')
t.logic.on_file('write',name)
t.logic.on_file('write',name)
t.answer = True
t.logic.on_file('write',name)
t.answer = False
t.logic.on_file('write',name,confirmed = name)
t.logic.on_file('write',name + '.gz')
t.logic.on_file('state',None)
print('   written:', sorted( f.name for f in pathlib.Path('.').glob('*.mcpl*') if f.name != 'example.mcpl' ))
step('a click on a plot of the overview shows it on its own, with b back to the overview')
t.logic.on_select_key(v.views[0][0])
t.shown()
click(v.overview_keys(v.current_key)[2])
t.shown()
print('   can go back:', t.logic.can_go_back, '| title:', t.logic.part_title())
t.logic.on_key('b')
print('   after b:', v.current_key, t.logic.can_go_back, '| title:', t.logic.part_title())
step('Up and Down: the groups, or the plots of the overview of the shown plot')
t.logic.on_key('Down')
print('   Down:', v.current_key)
t.logic.on_key('Up')
t.logic.on_key('Up')
print('   Up twice:', v.current_key)
click(v.overview_keys(v.current_key)[0])
for k in ( 'Down', 'Down', 'Up' ):
    t.logic.on_key(k)
    print(f'   {k}:', v.current_key)
t.logic.on_key('b')
print('   b:', v.current_key)
step('the menus of the plots of overviews (right click), and moving custom plots')
t.logic.on_add_plot('hypot(x,y)/cm')
t.logic.on_add_plot('uz;bins=10')
t.logic.on_select_key('overview:custom')
click('custom:uz;bins=10',button=3)
print('   still shown:', v.current_key)
dict(t.logic.plot_menu('custom:uz;bins=10'))['Move earlier']()
print('   moved earlier:', v._groups.custom)
dict(t.logic.plot_menu('custom:uz;bins=10'))['Move earlier']()
print('   again (already first):', v._groups.custom)
dict(t.logic.plot_menu('custom:uz;bins=10'))['Move later']()
print('   moved later:', v._groups.custom)
t.logic.on_select_key('overview:fields')
click('plot:x',button=3)
#(the right button as matplotlib numbers it on macOS with newer Tk):
click('plot:x',button=2)
print('   still shown:', v.current_key)
t.logic.on_select_key('plot:x')
t.logic.on_key('MoveUp')
t.shown()
print('   state:', v.state(full = False))
step('copy and edit: a change of the copied plot adds the changed plot')
t.logic.on_select_key('overview:fields')
dict(t.logic.plot_menu('plot:x'))['Copy and edit']()
print('   title:', t.logic.part_title())
t.logic.on_control('bins','17')
print('   copy added:', v.current_key, v._groups.custom, '| title:', t.logic.part_title())
t.logic.on_control('bins','18')
print('   then changed:', v.current_key, v._groups.custom)
t.logic.on_select_key('overview:custom')
dict(t.logic.plot_menu('custom:x;bins=18'))['Copy and edit']()
t.logic.on_axes('y')
print('   copy of a custom plot:', v.current_key, v._groups.custom)
for k in ( 'custom:x;bins=18', 'custom:y;bins=18' ):
    dict(t.logic.plot_menu(k))['Remove plot']()
print('   removed again:', v._groups.custom)
step('the settings of the shown plot')
for name, shown in ( ('logy','linear'), ('display_by','particle type'), ('bins','40'),
                     ('range','0:90'), ('display_by','single'), ('logx','nonsense') ):
    print(f'  {name} set to {shown!r}:')
    t.logic.on_control(name,shown)
t.shown()
step('the colour bar of 2D histograms has a menu of the colour scales')
print('   menu of a 1D plot:', t.logic.colour_bar_menu())
t.logic.on_select_key(next( k for k, _ in v.views if k.startswith('plot:') and k.count(' : ') == 1 ))
print('   menu:', t.logic.colour_bar_menu())
t.logic.on_control('logz','linear')
print('   linear:', v.current_key, t.logic.colour_bar_menu())
t.logic.on_control('logz','log')
print('   log again:', v.current_key)
step('the cache: green when the plots use all particles, else red, with a menu of limits')
print('   button:', ui.cache_text(v.cache_info()))
for entry in ui.cache_menu(v.cache_info()):
    print('   menu:', entry)
t.logic.on_cache_limit(v.cache_info()['size'] * 300)
v.wait()
print('   button:', ui.cache_text(v.cache_info()))
t.logic.refresh()
print('   counts:', v.counts_text(), '| write button count:', v.nused)
t.logic.on_cache_limit(None)
print('   button:', ui.cache_text(v.cache_info()))
t.logic.on_cache_limit(500e6)
v.wait()
#(the percentage is rounded down, so 100% is only shown when all fit, and the
#button is purple while the particles are put in the cache):
info = dict(v.cache_info())
for nused, filling in ( ( 1006, True ), ( 1005, False ), ( 503, False ), ( 5, False ) ):
    info.update(nused=nused,fits=nused == 1006,filling=filling)
    print(f'   button with {nused} of 1006 particles, filling: {filling}:', ui.cache_text(info))
step('the title of the shown view in the header')
t.logic.on_select_key(next( k for k, _ in v.views if k.startswith('overview:') ))
print('   overview:', t.logic.part_title())
t.logic.on_select_key('plot:x')
print('   plot:', t.logic.part_title())
t.logic.on_new_plot()
print('   new plot:', t.logic.part_title())
t.logic.on_select_key('plot:x')
step('plot strings of quantities and expressions')
for x, y, settings in ( ('Energy','',()), ('Energy','',(('logx','linear'),('logy','log'))),
                        ('Position x','Direction x',(('bins','30'),)),
                        ('Particle type','',(('bar','5'),)), ('hypot(x,y)/cm','',()) ):
    plot = t.logic.compose(x,y,settings = settings)
    print(f'   {x!r} against {y!r} with {settings}: {plot!r}, settings {t.logic.plot_controls(plot)[0]}')
print('   added:', t.logic.on_add_plot(t.logic.compose('Time',settings = (('logy','linear'),))))
print('   3D:', t.logic.compose('Position x','Position y','Position z'))
t.shown()
print('   added again:', t.logic.on_add_plot(t.logic.compose('Time')))
t.shown()
step('changing the axes of the shown plot (keeping the options which can be kept)')
for x, y, z in ( ('wavelength','',''), ('Energy','',''), ('ekin : time','',''), ('','time : ekin',''),
                 ('x','y',''), ('x','y','z'), ('x','','z'), ('x','',''), ('','',''),
                 ('nonsense','','') ):
    print(f'  {x!r}, {y!r}, {z!r}:', t.logic.on_axes(x,y,z), v.current_key, t.logic.axis_texts())
t.logic.on_axes_edited('ekin : nonsense')
t.logic.on_axes_edited('ekin','','x')
t.shown()
step('a new plot: shown as a card until its axes are chosen, or given up')
t.logic.on_key('a')
t.shown()
t.logic.on_axes_edited('')
print('   added:', t.logic.on_axes('hypot(x,y)/cm',''))
t.shown()
t.logic.on_new_plot()
t.logic.on_select_key(v.views[1][0])
print('   given up when another view is shown:', t.logic.shown_key, len(t.logic.cards()))
t.logic.on_new_plot()
t.logic.on_remove()
print('   given up when removed:', t.logic.shown_key, len(t.logic.cards()))
t.logic.on_new_plot()
print('   added with a plot expression:', t.logic.on_field_apply('shown_plot','uz;bins=20'), v.current_key)
step('the command of the shown plot, and of the plots of the overview')
print('  ', '\n    '.join(t.logic.plot_code()['command'].splitlines()))
v.select_key('overview:spectra')
print('  ', '\n    '.join(t.logic.plot_code()['command'].splitlines()))
step('writing needs an edit or a range of particles')
t.logic.on_field_apply('edit','')
t.shown()
print('   changes particles:', v.changes_particles)
t.logic.on_key('w')
step('another file, with the same plots and edit')
t.logic.on_field_apply('edit','pdgcode == neutron')
t.shown()
shutil.copy('example.mcpl','other.mcpl')
print('   opened:', t.logic.on_open_file('other.mcpl'))
t.shown()
print('   file:', v.filename, '| the viewer:', t.logic.v.filename, t.logic.v.field_text('edit'))
print('   a file which does not exist:', t.logic.on_open_file('nonexisting.mcpl'), t.logic.v.filename)
v = t.logic.v
step('removing plots, with Delete (only custom ones)')
t.logic.on_select_key('plot:x')
t.logic.on_key('Delete')
t.logic.on_select_key(f'custom:{v._groups.custom[0]}')
t.logic.on_key('Delete')
t.shown()
step('the groups: an overview of each, which hides it with Delete, and shown again')
print('  ', [ ( k, ov.title, len(ov.plots), f'{ov.nrows}x{ov.ncols}' ) for k, ov in v.overviews() ])
print('   inactive groups:', [ ( c.key, c.name, c.status ) for c in t.logic.cards() if c.inactive ])
t.logic.on_select_key('overview:correlations')
print('   code of the shown overview:', len(t.logic.plot_code()['command'].splitlines()), 'plots')
t.logic.on_key('Delete')
print('   after Delete:', v.groups, t.logic.shown_key, '| state:', v.state(full = False))
t.logic.on_show_group('correlations')
print('   shown again:', v.groups, t.logic.shown_key)
t.logic.on_show_group('3d')
print('   3D shown:', v.groups, t.logic.shown_key, [ c.name for c in t.logic.cards() if c.group == '3D' ])
#(the menu of an inactive card activates it, with or without showing it, and
#that of an active one deactivates it):
card = next( c for c in t.logic.cards() if c.key == 'info:group:beamx' )
print('   menu of an inactive card:', [ label for label, _ in t.logic.card_menu(card) ])
shown = t.logic.shown_key
dict(t.logic.card_menu(card))['Activate']()
print('   after Activate:', 'beamx' in v.groups, '| shown unchanged:', t.logic.shown_key == shown)
card = next( c for c in t.logic.cards() if c.key == 'overview:beamx' )
print('   menu of an active card:', [ label for label, _ in t.logic.card_menu(card) ])
dict(t.logic.card_menu(card))[card.remove_text]()
print('   after it:', 'beamx' in v.groups)
t.logic.on_select_key('info:group:beamz')
print('   beamz activated by its card:', v.groups, t.logic.shown_key,
      [ c.name for c in t.logic.cards() if c.inactive ])
print('   order of the groups:', list(dict.fromkeys( c.group for c in t.logic.cards() )))
t.logic.on_select_key('overview:custom')
t.logic.on_key('Delete')
print('   the custom group is not hidden:', t.logic.shown_key)
#(its overview ends with the place of a new plot, which starts one when
#clicked):
print('   cells of the custom overview:', v.overview_keys('overview:custom')[-2:],
      [ type(p.items[0]).__name__ for p in v.figure(key='overview:custom').panels[-2:] ])
t.logic.on_timer()
ax = t.logic.pane._panels[-1][0]
bb = ax.get_window_extent()
t.logic.on_click(MouseEvent('button_press_event',t.logic.fig.canvas,(bb.x0+bb.x1)/2,(bb.y0+bb.y1)/2,button=1))
print('   after clicking it:', t.logic.shown_key)
t.logic.on_remove()
#(a right click on a plot of an overview shows its menu, and on a plot shown on
#its own goes back to its overview, as b):
def right_click( panel = 0 ):
    t.logic.on_timer()
    if t.logic.pane._panels:
        bb = t.logic.pane._panels[panel][0].get_window_extent()
        x, y = (bb.x0+bb.x1)/2, (bb.y0+bb.y1)/2
    else:
        x, y = [ s/2 for s in t.logic.fig.canvas.get_width_height() ]
    t.logic.on_click(MouseEvent('button_press_event',t.logic.fig.canvas,x,y,button=3))
t.logic.on_select_key('overview:spectra')
right_click()
print('   right click in an overview: shown:', t.logic.shown_key)
t.logic.on_select_key(v.overview_keys('overview:spectra')[0])
print('   shown:', t.logic.shown_key)
right_click()
print('   right click on a plot shown on its own: shown:', t.logic.shown_key)
step('the settings of overviews: the particle type, and the variables of correlation plots')
t.logic.on_field_apply('edit','')
v.wait()
t.logic.on_select_key('overview:spectra')
print('   of the overview:', t.logic.overview_controls())
t.logic.on_select_key('overview:correlations')
print('   of the correlations:', t.logic.overview_controls())
for var in ( 'time', 'z: all 20 cm' ):#(off, and a constant one on)
    t.logic.on_overview_control('variables',var)
ov = dict(v.overviews())['overview:correlations']
print('   variables:', ov.variables, f'{ov.nrows}x{ov.ncols}', ov.cells[:2], ov.kinds[:2])
for var in ( 'x', 'y', 'z: all 20 cm', 'ux', 'uy', 'uz' ):#(until fewer than two are left)
    t.logic.on_overview_control('variables',var)
t.logic.on_overview_control('particle_type','gamma (24%)')
v.wait()
fig = v.figure(key='overview:correlations')
print('   title:', fig.title)
print('   cells:', [ type(p.items[0]).__name__ for p in fig.panels ],
      [ p.items[0].number for p in fig.panels if hasattr(p.items[0],'value') ])
state = v.state(full = False)
print('   state:', state['settings'])
print('   restored:', Viewer('example.mcpl',state=state).group_settings('correlations'))
t.logic.on_overview_control('variables','x')
print('   back to the default variables:', v.set_group_setting('correlations','variables',None),
      v.group_setting('correlations','variables'))
t.logic.on_overview_control('most',ui.most_correlated)
print('   most correlated:', v.group_setting('correlations','variables'),
      '| button:', t.logic.overview_controls()[-1][3])
t.logic.on_overview_control('most',ui.all_variables)
print('   all again:', v.group_setting('correlations','variables'),
      '| button:', t.logic.overview_controls()[-1][3])
#(the particle type of a group is the setting Particles of its plots, also
#when they are copied into the custom group):
t.logic.on_select_key('overview:spectra')
t.logic.on_overview_control('particle_type','gamma (24%)')
v.wait()
t.logic.on_select_key(next( k for k in v.overview_keys('overview:spectra') if 'wavelength' in k ))
print('   Particles of a plot of the overview:', t.logic.plot_controls()[1][-1][2:4])
t.logic.on_control('display_edit','all')
print('   after choosing all:', t.logic.shown_key)
#(the curves by particle type of a group, or single: the plots which can show
#several curves get display_by=single, the others, like 2D histograms, not):
t.logic.on_select_key('overview:fields')
t.logic.on_overview_control('display_by','single')
ov = dict(v.overviews())['overview:fields']
print('   fields with single curves:', [ s for n, _, _, s in t.logic.overview_controls() ],
      ov.cells[:2], ov.cells[-1])
t.logic.on_overview_control('display_by','particle type')
print('   and by particle type again:', dict(v.overviews())['overview:fields'].cells[:2])
#(the coefficients, from sums over blocks of particles: of values on a line,
#either way, with weights, by particle type and for all, on a logarithmic
#axis for values spanning more than two decades, and none for one value):
class Block:
    def __init__( self, **fields ):
        self.__dict__.update(fields)
    def __len__( self ):
        return len(self.x)
m = Moments(['x','y','ekin','z'])
for _ in range(2):
    m.add(Block(x=[1.,2.,3.,4.],y=[2.,4.,6.,9.],ekin=[1e-3,1e-2,1e-1,1.],z=[5.,5.,5.,5.],
                weight=[1.,1.,2.,2.],pdgcode=[2112,2112,22,22]))
for k, r in m.coefficients().items():
    print('   coefficients of', k, ':', { f'{a}:{b}' : None if c is None else round(c,4)
                                         for ( a, b ), c in r.items() })
step('the most correlated variables of a single particle (none varies)')
t1 = FakeToolkit(Viewer('example.mcpl',limit=1,state={'groups':['correlations']}))
t1.logic.start()
t1.logic.v.wait()
t1.logic.on_select_key('overview:correlations')
t1.logic.on_overview_control('most',ui.most_correlated)
t1.logic.v.stop()
step('a plot of several groups: its card, and b and Down, follow the overview it was chosen in')
v.set_group_setting('spectra','particle_type',None)
key = next( k for k in v.overview_keys('overview:spectra') if k.startswith('plot:time') )
for overview in ( 'overview:fields', 'overview:spectra' ):
    t.logic.on_select_key(overview)
    click(key)
    print(f'   {key} from {overview}: card {t.logic.selected_card()}', end='')
    t.logic.on_key('Down')
    print(f', Down: {v.current_key}', end='')
    t.logic.on_key('b')
    print(f', b: {v.current_key}')
step('expressions written in the settings of plots')
t.logic.on_select_key(next( k for k, _ in v.views if k.startswith('plot:') and ' : ' in k ))
print('   choices of display_edit:', next( c for n, _, c, _, _ in t.logic.plot_controls()[1]
                                           if n == 'display_edit' ))
for text in ( '', 'ekin > 1Me', 'ekin >> 1', 'ekin > 1MeV' ):
    t.logic.on_control_edited('display_edit',text)
print('   completed:', t.logic.on_complete('display_edit','ekin > 1Me',10)[0])
step('the buttons of the actions, and quit')
t.logic.on_action('help')
t.logic.on_action('quit')
print('closed:', t.logic.closed)
