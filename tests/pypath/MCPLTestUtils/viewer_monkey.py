
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


# NEEDS: numpy matplotlib tkinter

# Random use of the viewer in a real Tk window (a "monkey test"): many random
# clicks, keys, settings, fields and windows, on files with and without
# userdata, with one particle and without particles, and then on files which do
# not fit in the memory of the viewer (its cache), failing on any exception
# (also in the callbacks of Tk and matplotlib, and in threads) or warning.

import faulthandler
import gzip
import random
import shutil
import threading
import time
import traceback
import warnings

import mcpldev as mcpl
import mcpldev._viewer_reading as viewer_reading
import mcpldev._viewer_tk as viewer_tk
from mcpldev._viewer import Viewer
from MCPLTestUtils.dirs import test_data_dir

#(if it hangs, the stacks of all threads are shown before the timeout of the
#test, and it ends):
faulthandler.dump_traceback_later(420,exit=True)

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )
with mcpl.MCPLOutFile('ud.mcpl',userdata_layout='nscat:uint8,dir:float32[3]') as o:
    o.add_particles( x = [1.0,2.0,3.0], uz = 1.0, ekin = [1.0,2.0,0.5], pdgcode = [2112,22,2112],
                     weight = 1.0, userdata = { 'nscat' : [0,1,2], 'dir' : [[0,0,1]]*3 } )
with mcpl.MCPLOutFile('one.mcpl') as o:
    o.add_particles( x = [1.0], uz = 1.0, ekin = 1.0, pdgcode = 2112, weight = 1.0 )
with mcpl.MCPLOutFile('empty.mcpl') as o:
    pass
with open('example.mcpl','rb') as fin, gzip.open('example.mcpl.gz','wb') as fout:
    fout.write(fin.read())
files = [ 'example.mcpl', 'example.mcpl.gz', 'ud.mcpl', 'one.mcpl', 'empty.mcpl' ]

rng = random.Random(1)
problems, done = [], []
def record( what, text ):
    problems.append(f'{what} after {done[-5:]}:\n{text}')
threading.excepthook = lambda a : record('thread',''.join(traceback.format_exception(
    a.exc_type,a.exc_value,a.exc_traceback)))
def on_warning( message, category, filename, lineno, file = None, line = None ):
    record('warning',f'{category.__name__}: {message} ({filename}:{lineno})')
warnings.showwarning = on_warning
warnings.simplefilter('always',ResourceWarning)#(e.g. files not closed, hidden by default)

viewer_tk._check_fonts = lambda root : None
root = viewer_tk._root()
assert root is not None, 'Tk can not open a window here'
root.report_callback_exception = lambda *e : record('Tk callback',''.join(traceback.format_exception(*e)))
tv = viewer_tk.TkViewer(Viewer(files[0]),root)
def catch_mpl():
    tv.canvas.callbacks.exception_handler = lambda e : record(
        'matplotlib callback',''.join(traceback.format_exception(e)))
catch_mpl()
tv.logic.start()
tv._tick()

def pump( seconds ):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)

exprs = [ 'ekin', 'x', 'y : z', 'ux : uy : uz', 'wavelength', 'log10(ekin/eV)', 'userdata.nscat',
          'x +', '', 'weight', 'angle(dir,(0,0,1))/deg', 'ekin/MeV', 'pdgcode', 'userflags' ]
fields = { 'pick' : [ '', 'pdgcode == neutron', 'ekin < 1MeV', 'x >', 'ekin < 0eV',
                      'userdata.nscat > 0', 'mod(fileidx,2) == 0' ],
           'edit' : [ '', 'z += 1cm', 'weight *= 2', 'x =' ],
           'skip' : [ '', '10', '100000000', 'x' ], 'limit' : [ '', '5', '0' ] }

def card():
    tv.logic.on_select_key(rng.choice(tv.logic.cards()).key)
def click():
    w = tv.canvas.get_tk_widget()
    x, y = rng.randrange(1,max(2,w.winfo_width())), rng.randrange(1,max(2,w.winfo_height()))
    w.event_generate('<Motion>',x=x,y=y)
    w.event_generate('<ButtonPress-1>',x=x,y=y)
    w.event_generate('<ButtonRelease-1>',x=x,y=y)
def key():
    tv.on_key(rng.choice([ 'Up', 'Down', 'Delete', 'l', 'k', 'MoveUp', 'MoveDown', 'Enter' ]))
def overview():
    controls = tv.logic.overview_controls()
    if controls:
        name, _, texts, _ = rng.choice(controls)
        tv.logic.on_overview_control(name,rng.choice(texts))
def setting():
    controls = tv.logic.plot_controls()
    if controls:
        name, _, choices, _, _ = rng.choice(controls[1])
        tv.logic.on_control(name,rng.choice(choices or [ '', '10', '0:10', '-5cm:5cm', 'x' ]))
def axes():
    x, y, z = ( rng.choice(exprs) if rng.random() < p else '' for p in ( 1, 0.4, 0.2 ) )
    tv.logic.on_axes_edited(x,y,z)
    tv.logic.on_axes(x,y,z)
def field():
    name = rng.choice(list(fields))
    text = rng.choice(fields[name])
    tv.logic.on_field_edited(name,text)
    tv.logic.on_field_apply(name,text)
def new_plot():
    tv.logic.on_new_plot()
    tv.logic.on_axes(rng.choice(exprs))
def group():
    tv.logic.on_show_group(rng.choice(tv.logic.v.group_list())[0],rng.random() < 0.6)
def header():
    tv.logic.on_group_header(rng.choice(tv.logic.v.group_list())[1])
def help_window():
    before = set(root.winfo_children())
    _, title, blocks = rng.choice(tv.logic.help_topics())
    tv.show_text(title,blocks)
    pump(0.02)
    for w in set(root.winfo_children()) - before:
        w.destroy()
def other_file():
    tv.logic.on_open_file(rng.choice(files),rng.random() < 0.5)
    catch_mpl()
def size():
    root.geometry(rng.choice([ '1400x900', '1000x650', '800x600' ]))
def wait():
    for _ in range(3000):
        pump(0.01)
        if not tv.logic.v.reading:
            break
actions = { card : 10, click : 8, key : 6, overview : 6, setting : 8, axes : 5, field : 5,
            new_plot : 3, tv.logic.on_remove : 2, group : 3, header : 3, help_window : 2,
            tv.logic.plot_code : 2, other_file : 1, size : 1, wait : 4,
            ( lambda : tv.logic.on_cache_limit(rng.choice(cache_limits)) ) : 2,
            ( lambda : tv.logic.on_title(rng.choice([ 'A title', '', 'x' * 80 ])) ) : 2,
            ( lambda : tv._toggle.invoke() ) : 2 }
def run( n ):
    for _ in range(n):
        action = rng.choices(list(actions),list(actions.values()))[0]
        done.append(getattr(action,'__name__','?'))
        action()#(an exception fails the test, with its traceback)
        pump(rng.choice([ 0.0, 0.01, 0.05 ]))
    wait()

cache_limits = [ 1e5, 5e6, None ]
run(300)
#With a cache (of 20 kB) in which the particles of the files (44 kB) do not
#all fit, so the plots use the first ones, and the rest are not read:
viewer_reading._cache_limit = 2e4
files[:] = [ 'example.mcpl', 'example.mcpl.gz' ]
cache_limits = [ 1e4, 2e4, 3e4, None ]
tv.logic.on_open_file('example.mcpl')
catch_mpl()
wait()
print('particles fit in the cache:', tv.logic.v.cache_info()['fits'])
run(150)
tv.close_window()
print('random actions done:', len(done), '| closed:', tv.logic.closed)
print('problems:', len(problems))
for p in problems:
    print(p)
