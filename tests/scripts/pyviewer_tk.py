
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

# Test the viewer in a real Tk window (on Linux and FreeBSD in CI with a
# virtual display, Xvfb): that it opens, reads the file, shows cards, plots
# and the cache button, and reacts to clicks, typing and its menus. The logic
# behind it is tested without a display by pyviewer_widgets; this checks that
# the Tk front end works with the real toolkit.

import shutil
import time
import tkinter

import mcpldev._viewer_tk as viewer_tk
from mcpldev._viewer import Viewer
from mcpldev._viewer_tk import TkViewer, _root
from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

#(no warning about fonts without Xft, which depends on the Tk installed):
viewer_tk._check_fonts = lambda root : None

root = _root()
assert root is not None, 'Tk can not open a window here'
print('Tk 8.6 or later:', tkinter.TkVersion >= 8.6)

v = Viewer('example.mcpl')
tv = TkViewer(v,root)
tv.start()
root.after(200,tv._tick)

def pump( seconds = 0.3 ):
    """Let Tk handle events and the viewer update the window"""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)

def wait():
    """Until the file is read and the window shows the result"""
    for _ in range(3000):
        pump(0.01)
        if not v.reading:
            break
    tv.on_timer()
    pump()

def text( w ):
    return str(w.cget('text'))

def show( what ):
    print(f'{what}:')
    print('   status:', text(tv._status[0]))
    print('   counts:', text(tv._counts))
    print('   cache button:', text(tv._cache), str(tv._cache.cget('style')))
    print('   write button:', text(tv._write))
    print('   shown:', v.current_key)

wait()
print('window title:', root.title())
show('after reading the file')
cards = [ s[3] for s in tv._cards._slots if s[2] == 'card' ]
print('cards:', len(cards), '| first:', [ c.title or c.name for c in cards[:4] ])
print('axes drawn:', len(tv.canvas.figure.axes) > 0)

#All groups start folded (showing their overviews). A click on the overview of
#the first group expands it, and a click on its second card shows its plot:
canvas = tv._cards.canvas
def click_card( name ):
    canvas.yview_moveto(0)
    pump()
    y0, y1, _, _ = next( s for s in tv._cards._slots if s[2] == 'card' and s[3].name == name )
    y = ( y0 + y1 ) // 2
    canvas.event_generate('<ButtonPress-1>',x=60,y=y)
    canvas.event_generate('<ButtonRelease-1>',x=60,y=y)
    pump()
    shown = [ s[3].name for s in tv._cards._slots if s[2] == 'card' ]
    print(f'after clicking the card {name!r}: {v.current_key} | {len(shown)} cards shown')
#(clicking the overview of the expanded group again folds it, and again
#expands it):
for _ in range(3):
    click_card(cards[0].name)
click_card('Energy')
print('help menu:', [ tv._help_choices.entrycget(i,'label')
                      for i in range(tv._help_choices.index('end') + 1) ])

#Tab completes in the X axis field (and stays there), and with several
#completions shows a list, where Down and Enter choose one:
xaxis = tv._axes[0]
xaxis.focus_force()
pump()
for typed, keys in ( ( 'ek', [ '<Tab>' ] ), ( 'po', [ '<Tab>', '<Down>', '<Return>' ] ) ):
    tv._set_text(xaxis,typed)
    xaxis.icursor('end')
    for k in keys:
        xaxis.event_generate(k)
        pump(0.1)
        if k == '<Tab>' and tv._popup is not None:
            print('   completions of', repr(typed), ':', [ c[0] for c in tv._popup[4] ])
    print(f'X axis after typing {typed!r} and {" ".join(keys)}: {tv._text(xaxis)!r},'
          f' focus kept: {root.focus_get() is xaxis}')
tv._on_axis_escape()
tv._on_title_escape()
pump()

#"Advanced" shows the plot expression instead of the axes and settings (the
#parts of it), and back:
def parts():
    return { name : bool(w.winfo_ismapped()) for name, w in
             ( ( 'axes', tv._axes[0] ), ( 'settings', tv._settings_row ),
               ( 'expression', tv._entries['shown_plot'] ) ) }
print('shown parts of the plot:', parts())
for _ in range(2):
    tv._toggle.invoke()
    pump()
    print(f'after clicking Advanced (on: {tv._advanced.get()}): {parts()},'
          f' expression {tv._text(tv._entries["shown_plot"])!r}')

#Typing a pick and pressing Enter:
entry = tv._entries['pick']
entry.focus_force()
pump()
tv._set_text(entry,'ekin < 1MeV')
entry.event_generate('<Return>')
wait()
show('after the pick')

#The menu of the cache button, and a limit with which not all particles fit:
tv._cache_menu()
menu = tv._cache_choices
labels = [ menu.entrycget(i,'label') for i in range(menu.index('end') + 1)
           if menu.type(i) != 'separator' ]
print('cache menu:', labels)
tv.on_cache_limit(v.cache_info()['size'] * 300)
wait()
show('with a small cache')
menu.invoke(3)#(500 MB)
wait()
show('with 500 MB')

#A click on the grey card of an inactive group activates it and shows its
#overview (and only the group of the shown view is expanded):
def click_slot( slot ):
    canvas.yview_moveto(0)
    pump()
    top, bottom = slot[0], slot[1]
    frac = top / float(canvas.cget('scrollregion').split()[3])
    canvas.yview_moveto(frac)
    pump()
    y = int( ( top + bottom ) / 2 - canvas.canvasy(0) )
    canvas.event_generate('<ButtonPress-1>',x=60,y=y)
    canvas.event_generate('<ButtonRelease-1>',x=60,y=y)
    pump()
inactive = next( s for s in tv._cards._slots if s[2] == 'card' and s[3].inactive )
click_slot(inactive)
print('after clicking the inactive group', repr(inactive[3].name), ':', v.current_key,
      '| folded:', sorted(tv.folded_groups()))

tv.close_window()
print('closed:', tv.closed)
