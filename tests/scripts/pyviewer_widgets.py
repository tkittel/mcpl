
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
    """Prints what the front end is asked to show: the views, the status and
    the plot (which depend on the reading of the file) only when shown() is
    called (after the reading), the rest when it happens. Its logic is
    self.logic."""
    def __init__( self, viewer ):
        fig = Figure(figsize=(10,6))
        FigureCanvasAgg(fig)
        self.logic = WindowLogic(viewer,self,fig)
        self.state = {}

    def show_views( self, cards ):
        c = next( c for c in cards if c.key == self.logic.shown_key )
        self.state['views'] = ( f'{len(cards)} views, shown: {c.name!r} ({c.plot},'
                                f' group {c.group}, badges {c.badges})' )
        self.state['compact cards'] = [ f'{c.name}: {c.status}' for c in cards if c.compact ]
        self.state['problems'] = [ c.name for c in cards if c.problem ]
        self.state['thumbnails'] = sum( c.image and self.logic.thumbnail(c.key,84,50) is not None
                                        for c in cards )
        #(what the kinds of cards allow: selectable, draggable, removable and
        #grouped, by their names, e.g. the overview, a plot and the reminder of
        #userdata in files without it):
        kinds = sorted({ ''.join( k[0] if getattr(c,k) else '-' for k in
                                  ( 'selectable', 'draggable', 'removable', 'grouped' ) )
                         for c in cards })
        self.state['kinds of cards'] = kinds

    def show_status( self, first, second ):
        self.state['status'] = first

    def show_plot_field( self, text, title, axes ):
        self.state['shown plot field'] = ( text, title, axes )

    def show_controls( self, controls ):
        self.state['settings'] = None if controls is None else ( controls[0], { name : shown
                                                       for name, _, _, shown, _ in controls[1] } )
        self.state['bins used'] = None if controls is None else next(
            ( used for name, _, _, _, used in controls[1] if name == 'bins' ), None )

    def draw_plot( self ):
        self.state['plot'] = f'{len(self.logic.pane.axes)} axes'

    def shown( self ):
        """Wait for the reading, and print the views, status and plot"""
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

    def show_help( self ):
        print(f'   help shown: {ui_help_lines()} lines')

    def close_window( self ):
        print('   window closed')
        self.logic.on_close()

def ui_help_lines():
    return len(ui.help_text.splitlines())

def step( what ):
    print(f'==> {what}')

v = Viewer('example.mcpl',view='spectra,fields,correlations')
t = FakeToolkit(v)
step('start, and the end of the reading')
t.logic.start()
t.shown()
step('typing in the pick field: invalid, then valid with a hint')
t.logic.on_field_edited('pick','pdgcode == neu')
t.logic.on_field_edited('pick','pdgcode == neutron')
step('applying an invalid pick, then a valid one')
t.logic.on_field_apply('pick','pdgcode = 1')
t.logic.on_field_apply('pick','pdgcode == neutron')
t.shown()
step('Esc in the edit field restores its text')
t.logic.on_field_edited('edit','x += ')
t.logic.on_field_cancel('edit')
step('earlier texts of the pick field (Up and Down)')
print('   up:', repr(t.logic.on_history('pick',-1)), '| down:', repr(t.logic.on_history('pick',1)))
step('Tab completion')
t.logic.on_field_edited('pick','ekin < 1MeV and e')
print('  ', t.logic.on_complete('pick','ekin < 1MeV and e',len('ekin < 1MeV and e'))[:3])
print('   (not mentioned after it was used)')
t.logic.on_field_edited('pick','')
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
for k in ( 'Down', 'MoveDown', 'Up', 'P', 'Enter', 'w', 'v', '?' ):
    print(f'  key {k}:')
    t.logic.on_key(k)
    t.shown()
step('the file names (the suggested one is written, the same again is refused)')
name = t.logic.suggested_filename('write')
t.logic.on_file('write',name)
t.logic.on_file('write',name)
t.logic.on_file('state',None)
print('   written:', sorted( f.name for f in pathlib.Path('.').glob('*.mcpl*') if f.name != 'example.mcpl' ))
step('a click on a plot of the overview shows it on its own')
t.logic.on_select(0)
t.shown()
ax = t.logic.pane._panels[2][0]
bb = ax.get_window_extent()
t.logic.on_click(MouseEvent('button_press_event',t.logic.fig.canvas,(bb.x0+bb.x1)/2,(bb.y0+bb.y1)/2,button=1))
t.shown()
step('the title of the shown plot (not of standard plots), and dragging custom plots')
t.logic.on_title('Angle to the beam')
t.logic.on_add_plot('hypot(x,y)/cm','Radius')
t.logic.on_add_plot('uz;bins=10')
t.logic.on_drop(v.current_key,'custom:hypot(x,y)/cm')
print('   dragged:', v._groups.custom)
t.logic.on_drop(v.current_key,'plot:x')
t.logic.on_select_key('plot:x')
t.logic.on_key('MoveUp')
t.shown()
print('   state:', v.state(full = False))
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
print('   button:', ui.cache_text(v.cache_info()))
v.wait()
t.logic.refresh()
print('   counts:', v.counts_text(), '| write button count:', v.nused)
t.logic.on_cache_limit(None)
print('   button:', ui.cache_text(v.cache_info()))
t.logic.on_cache_limit(500e6)
v.wait()
step('plot strings of quantities and expressions')
for x, y, settings in ( ('Energy','',()), ('Energy','',(('logx','linear'),('logy','log'))),
                        ('Position x','Direction x',(('bins','30'),)),
                        ('Particle type','',(('bar','5'),)), ('hypot(x,y)/cm','',()) ):
    plot = t.logic.compose(x,y,settings = settings)
    print(f'   {x!r} against {y!r} with {settings}: {plot!r}, settings {t.logic.plot_controls(plot)[0]}')
print('   added:', t.logic.on_add_plot(t.logic.compose('Time',settings = (('logy','linear'),)),'Arrival time'))
print('   3D:', t.logic.compose('Position x','Position y','Position z'))
t.shown()
print('   added again, with another title:', t.logic.on_add_plot(t.logic.compose('Time'),'Another'))
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
t.logic.on_title('Radius')
t.logic.on_axes_edited('')
print('   added:', t.logic.on_axes('hypot(x,y)/cm',''))
t.shown()
t.logic.on_new_plot()
t.logic.on_select(1)#(the first plot)
print('   given up when another view is shown:', t.logic.shown_key, len(t.logic.cards()))
t.logic.on_new_plot()
t.logic.on_remove()
print('   given up when removed:', t.logic.shown_key, len(t.logic.cards()))
t.logic.on_new_plot()
print('   added with a plot expression:', t.logic.on_field_apply('shown_plot','uz;bins=20'), v.current_key)
step('the command of the shown plot, and of the plots of the overview')
print('  ', t.logic.plot_code()['command'])
v.select_key('overview:spectra')
print('  ', t.logic.plot_code()['command'])
step('writing needs a pick, an edit or a range of particles')
t.logic.on_field_apply('pick','')
t.shown()
print('   changes particles:', v.changes_particles)
t.logic.on_key('w')
step('another file, with the same plots, pick and edit')
t.logic.on_field_apply('pick','pdgcode == neutron')
t.shown()
shutil.copy('example.mcpl','other.mcpl')
print('   opened:', t.logic.on_open_file('other.mcpl'))
t.shown()
print('   file:', v.filename, '| the viewer:', t.logic.v.filename, t.logic.v.field_text('pick'))
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
print('   folded:', sorted(t.logic.folded_groups()), '| shown:', t.logic.shown_key)
t.logic.on_group_header('Correlations')
print('   after clicking the header of Correlations:', t.logic.shown_key, sorted(t.logic.folded_groups()))
t.logic.on_select_key('plot:x')
print('   with a plot of Fields shown:', sorted(t.logic.folded_groups()))
print('   inactive groups:', [ ( c.key, c.name, c.status ) for c in t.logic.cards() if c.inactive ])
t.logic.on_select_key('overview:correlations')
print('   code of the shown overview:', len(t.logic.plot_code()['command'].split(' -H ')) - 1, 'plots')
t.logic.on_key('Delete')
print('   after Delete:', v.groups, t.logic.shown_key, '| state:', v.state(full = False))
t.logic.on_show_group('correlations')
print('   shown again:', v.groups, t.logic.shown_key)
t.logic.on_show_group('3d')
print('   3D shown:', v.groups, t.logic.shown_key, [ c.name for c in t.logic.cards() if c.group == '3D' ])
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
step('the settings of overviews: the particle type, and the variables of correlation plots')
t.logic.on_field_apply('pick','')
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
t.logic.on_overview_control('display_only','gamma (24%)')
v.wait()
fig = v.figure(key='overview:correlations')
print('   title:', fig.title)
print('   cells:', [ type(p.items[0]).__name__ for p in fig.panels ],
      [ p.items[0].text for p in fig.panels if hasattr(p.items[0],'value') ])
state = v.state(full = False)
print('   state:', state['settings'])
print('   restored:', Viewer('example.mcpl',view=state).group_settings('correlations'))
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
t.logic.on_overview_control('display_only','gamma (24%)')
v.wait()
t.logic.on_select_key(next( c.key for c in t.logic.cards() if c.group == 'Spectra' and 'wavelength' in c.key ))
print('   Particles of a plot of the overview:', t.logic.plot_controls()[1][-1][2:4])
t.logic.on_control('display_only','all')
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
t1 = FakeToolkit(Viewer('example.mcpl',limit=1,view='correlations'))
t1.logic.start()
t1.logic.v.wait()
t1.logic.on_select_key('overview:correlations')
t1.logic.on_overview_control('most',ui.most_correlated)
t1.logic.v.stop()
step('a plot of several groups has a card in each')
v.set_group_setting('spectra','display_only',None)
cards = t.logic.cards()
def plots_of( group ):
    return [ c.name for c in cards if c.group == group and not c.overview ]
print('   Spectra:', plots_of('Spectra'))
print('   Fields:', plots_of('Fields'))
key = next( c.key for c in cards if c.group == 'Spectra' and c.name == 'Time' )
print('   time:', key, '| also in Fields:', any( c.key == key and c.group == 'Fields' for c in cards ))
t.logic.on_select_key(key,'Fields')
print('   selected in:', t.logic.shown_group(t.logic.cards()), '| expanded:',
      sorted( { 'Spectra', 'Fields' } - t.logic.folded_groups() ))
t.logic.on_select_key(key,'Spectra')
print('   selected in:', t.logic.shown_group(t.logic.cards()))
step('expressions written in the settings of plots')
t.logic.on_select_key(next( k for k, _ in v.views if k.startswith('plot:') and ' : ' in k ))
print('   choices of display_only:', next( c for n, _, c, _, _ in t.logic.plot_controls()[1]
                                           if n == 'display_only' ))
for text in ( '', 'ekin > 1Me', 'ekin >> 1', 'ekin > 1MeV' ):
    t.logic.on_control_edited('display_only',text)
print('   completed:', t.logic.on_complete('display_only','ekin > 1Me',10)[0])
step('the buttons of the actions, and quit')
t.logic.on_action('help')
t.logic.on_action('quit')
print('closed:', t.logic.closed)
