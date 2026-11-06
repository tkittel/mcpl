
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


# (run by the test pyviewer_tk, which needs numpy, matplotlib, and tkinter)

# Test the viewer in a real Tk window (on Linux and FreeBSD in CI with a
# virtual display, Xvfb): that it opens, reads the file, shows cards, plots,
# and the cache button, and reacts to clicks, typing, and its menus. The logic
# behind it is tested without a display by pyviewer_widgets; this checks that
# the Tk front end works with the real toolkit.

import pathlib
import shutil
import sys
import time
import tkinter

import matplotlib.backends._backend_tk as backend_tk
import mcpldev
import mcpldev._viewer_tk as viewer_tk
import mcpldev._viewer_ui as viewer_ui
from mcpldev._viewer import Viewer
from mcpldev._viewer_tk import TkViewer, _root
from mcpldev._viewer_tkbase import Flow, focus_of
from mcpldev._viewer_tkwindows import AlignWindow, Examples, WriteWindow

from MCPLTestUtils.common import rounded_numbers
from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

#(no warning about fonts without Xft, which depends on the Tk installed):
viewer_tk._check_fonts = lambda root : None

root = _root()
assert root is not None, 'Tk can not open a window here'
print('Tk 8.6 or later:', tkinter.TkVersion >= 8.6)

v = Viewer('example.mcpl')
tv = TkViewer(v,root)
tv.logic.start()
tv._tick()

def pump( seconds = 0.3 ):
    """Let Tk handle events and the viewer update the window"""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)

def where_focus():
    """Where the keyboard focus is, as Tk says (also in the list of a combobox,
    which tkinter does not know as a widget)"""
    return root.tk.call('focus') or 'in no window of this program'

def take_focus( widget ):
    """Give the keyboard focus to the widget (keys go to the focus, which other
    programs on the display can take, e.g. tests running in parallel), saying
    so if it fails"""
    for _ in range(100):
        widget.focus_force()
        pump(0.02)
        if widget.focus_get() is widget:
            break
    else:
        print(f'   NO KEYBOARD FOCUS for {widget} after 100 tries: it is {where_focus()}')
        print('   ', focus_diagnostics(widget))
    pump()

def focus_diagnostics( widget ):
    """Why the widget may not get the keyboard focus: whether it is shown
    (mapped and viewable, and where, which may be off the screen), and the
    window, its state, and the screen"""
    def geometry( w ):
        return f'{w.winfo_width()}x{w.winfo_height()} at ({w.winfo_rootx()},{w.winfo_rooty()})'
    return ( f'widget: mapped {bool(widget.winfo_ismapped())}, viewable'
             f' {bool(widget.winfo_viewable())}, {geometry(widget)} | window: {root.wm_state()},'
             f' {geometry(root)}, focus of the window {root.tk.call("focus","-lastfor",root)} |'
             f' screen: {root.winfo_screenwidth()}x{root.winfo_screenheight()}' )

def wait():
    """Until the file is read and the window shows the result"""
    for _ in range(3000):
        pump(0.01)
        if not v.reading:
            break
    tv.logic.on_timer()
    pump()

def text( w ):
    return str(w.cget('text'))

def show( what ):
    print(f'{what}:')
    print('   status:', text(tv._status[0]))
    print('   counts:', text(tv._counts))
    print('   cache button:', text(tv._cache), str(tv._cache.cget('style')))
    print('   write buttons:', [ ( text(b), str(b.cget('style')), 'disabled' in b.state() )
                                  for b in ( tv._write, tv._write_code ) ])
    print('   shown:', v.current_key)

wait()
print('window title:', root.title())
show('after reading the file')
cards = [ s[3] for s in tv._cards._slots if s[2] == 'card' ]
print('cards:', len(cards), '| first:', [ c.name for c in cards[:4] ])
print('axes drawn:', len(tv.canvas.figure.axes) > 0)

#The cards are those of the groups: a click on one shows its overview (and the
#plots are shown from the overviews, see the logic):
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
click_card(cards[1].name)
click_card(cards[0].name)

#A right click on a plot of the overview shows its menu, also on macOS, where
#matplotlib swaps the buttons 2 and 3 (for the older Tk there), while newer Tk
#numbers the right button 3, as elsewhere (here matplotlib's Tk backend is
#made to see Linux, and then macOS, for real Tk clicks):
class SysOf:
    def __init__( self, platform ):
        self.platform = platform
    def __getattr__( self, name ):
        return getattr(sys,name)
menus, real_menu = [], tv.show_plot_menu
tv.show_plot_menu = lambda entries : menus.append([ label for label, _ in entries ])
widget = tv.canvas.get_tk_widget()
bb = tv.canvas.figure.axes[0].get_window_extent()
x, y = int( ( bb.x0 + bb.x1 ) / 2 ), int( widget.winfo_height() - ( bb.y0 + bb.y1 ) / 2 )
for platform in ( 'linux', 'darwin' ):
    backend_tk.sys = SysOf(platform)
    try:
        widget.event_generate('<ButtonPress-3>',x=x,y=y)
        widget.event_generate('<ButtonRelease-3>',x=x,y=y)
        pump()
    finally:
        backend_tk.sys = sys
    print(f'right click on a plot of the overview ({platform}): menu',
          menus.pop() if menus else None, '| shown:', v.current_key)
tv.show_plot_menu = real_menu
#(a plot is then shown from the overview, as by a click on it there):
tv.logic.on_select_key('plot:ekin;logx=auto;logy')
pump()
print('help menu:', [ tv._help_choices.entrycget(i,'label')
                      for i in range(tv._help_choices.index('end') + 1) ])
#(m and h, outside the text fields, open the menu and the help menu, and
#close it again; the menus are not really opened here, since menus on macOS
#are native, and wait until they are closed):
for key, menu in ( ( 'm', tv._actions_menu ), ( 'h', tv._help_choices ) ):
    button, events = tv._menu_keys[key], []
    real = button.event_generate
    button.event_generate = events.append
    tv.on_key(key)
    button.event_generate = real
    print(f'menu opened by {key}:', events == [ '<<Invoke>>' ],
          '| closed by it again:', bool(menu.bind(f'<KeyPress-{key}>')))

#Tab completes in the X axis field (and stays there), and with several
#completions shows a list, where Down and Enter choose one:
xaxis = tv._axes[0]
take_focus(xaxis)
for typed, keys in ( ( 'ek', [ '<Tab>' ] ), ( 'po', [ '<Tab>', '<Down>', '<Return>' ] ) ):
    tv._set_text(xaxis,typed)
    xaxis.icursor('end')
    for k in keys:
        xaxis.event_generate(k)
        pump(0.1)
        if k == '<Tab>' and tv._popup is not None:
            #(after the hint, see ui.axis_hint):
            print('   completions of', repr(typed), ':', [ c[0] for c in tv._popup[4] if c ])
    print(f'X axis after typing {typed!r} and {" ".join(keys)}: {tv._text(xaxis)!r},'
          f' focus kept: {root.focus_get() is xaxis}')
tv._on_axis_escape()
pump()

#The Apply button (at the right, above "Advanced") is enabled while something
#typed in the axes or the settings is not applied, and applies it as Enter
#does, with the mark of the check of the axes only while they are typed:
apply, mark = tv._apply, tv._marks['axes']
def apply_state():
    return f'enabled: {"disabled" not in apply.state()}, mark: {str(mark.cget("text"))!r}'
print('apply of the axes:', apply_state())
take_focus(xaxis)
tv._set_text(xaxis,'x')
xaxis.event_generate('<KeyRelease>',keysym='x')
pump()
print('after typing an axis:', apply_state(), '| shown:', v.current_key)
apply.invoke()
pump()
print('after clicking Apply:', apply_state(), '| shown:', v.current_key)
bins = tv._controls._widgets['bins']
take_focus(bins)
bins.delete(0,'end')
bins.insert(0,'7')
bins.event_generate('<KeyRelease>',keysym='7')
pump()
print('after typing the bins:', apply_state())
apply.invoke()
pump()
print('after clicking Apply:', apply_state(), '| shown:', v.current_key)
#(with "Advanced", the same button applies the plot expression, which has no
#Apply button of its own):
tv._advanced.set(True)
tv._show_advanced()
pump()
expression = tv._entries['shown_plot']
print('Apply buttons of the expression:', [ str(w.cget('text')) for w in tv._expression.winfo_children()
                                            if w.winfo_class() == 'TButton' ],
      '| the Apply button shown:', bool(apply.winfo_ismapped()))
take_focus(expression)
tv._set_text(expression,'x;bins=5')
expression.event_generate('<KeyRelease>',keysym='5')
pump()
print('after typing the expression:', apply_state())
apply.invoke()
pump()
print('after clicking Apply:', apply_state(), '| shown:', v.current_key)
tv._advanced.set(False)
tv._show_advanced()
tv.logic.on_select_key('plot:ekin;logx=auto;logy')
pump()

#The header of the plot says what is shown, with the button back to the
#overview while a plot is shown (also with b):
def head():
    back = '\u2190 ' if tv._back.winfo_manager() else ''
    return back + str(tv._plot_head.title.cget('text'))
print('header of a plot:', repr(head()))
tv.logic.on_new_plot()
pump()
print('header of a new plot:', repr(head()))
tv.logic.on_select_key('plot:ekin;logx=auto;logy')
pump()
tv._back.invoke()
pump()
print('after the button back:', v.current_key, '| header:', repr(head()))
tv.logic.on_select_key('plot:ekin;logx=auto;logy')
pump()

#The lists of the axes start with the hint that expressions can be typed,
#which keeps the text when chosen (in the list of the field, and in that of
#its completions):
print('first line of the list of the X axis:', repr(xaxis.cget('values')[0]))
take_focus(xaxis)
tv._axis_before = 'ekin'
xaxis.set(xaxis.cget('values')[0])
tv._on_axis_chosen(xaxis)
pump()
print('after choosing it:', repr(xaxis.get()), '| shown:', v.current_key)
tv._set_text(xaxis,'w')
xaxis.icursor('end')
tv._on_entry_tab(xaxis,'axis')
pump()
lines = tv._popup[3].get(0,'end')
print('completions of "w":', [ str(t).split()[0] for t in lines[1:] ], '| first line:', repr(lines[0]),
      '| selected:', tv._popup[3].curselection())
tv._popup[3].selection_clear(0,'end')
tv._popup[3].selection_set(0)
tv._insert_choice(xaxis)
pump()
print('after choosing the first line:', repr(xaxis.get()), '| list closed:', tv._popup is None)
tv._on_axis_escape()
tv.logic.on_select_key('plot:ekin;logx=auto;logy')
pump()

#The code of the plot, and the cache button:
print('code button:', repr(str(tv._code.cget('text'))), str(tv._code.cget('style')))
print('cache button:', str(tv._cache.cget('text')), str(tv._cache.cget('style')))

#With the list of a combobox open, the focus can be in it (which tkinter
#before Python 3.13 does not know as a widget, so focus_get fails), also when
#a field loses the focus:
yaxis = tv._axes[1]
root.tk.call('ttk::combobox::Post',str(yaxis))
root.tk.call('focus','-force',f'{yaxis}.popdown.f.l')
pump()
focus = focus_of(root)
print('focus in the open list of the Y axis:', focus is None or isinstance(focus,tkinter.Misc))
tv._on_entry_unfocus(yaxis)
root.tk.call('ttk::combobox::Unpost',str(yaxis))
pump()

#After a 3D plot, the mouse events of the plot shown next do not go to the
#3D plot any more (which would fail):
from matplotlib.backend_bases import MouseEvent

v.show_group('3d')
tv.logic.on_select_key('plot:x : y : z')
pump(1)
print('3D plot shown:', [ a.name for a in tv.canvas.figure.axes ])
tv.logic.on_select_key('plot:ekin;logx=auto;logy')
pump(1)
for name in ( 'button_press_event', 'button_release_event', 'motion_notify_event' ):
    MouseEvent(name,tv.canvas,100,100,1)._process()
print('mouse events after the 3D plot handled')

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
take_focus(entry)
tv._set_text(entry,'ekin < 1MeV')
ok = focus_of(root) is entry
print('focus in the pick field before Enter:', ok if ok else f'{ok} (it is {where_focus()})')
entry.event_generate('<Return>')
wait()
print('pick applied:', repr(v.field_text('pick')))
show('after the pick')

#The menu of the cache button, and a limit with which not all particles fit:
tv._cache_menu()
menu = tv._cache_choices
#(without the spaces lining them up with the check mark, as many as fit the
#font):
labels = [ menu.entrycget(i,'label').lstrip(' ') for i in range(menu.index('end') + 1)
           if menu.type(i) != 'separator' ]
print('cache menu:', labels)
tv.logic.on_cache_limit(v.cache_info()['size'] * 300)
wait()
show('with a small cache')
menu.invoke(next( i for i in range(menu.index('end') + 1) if menu.type(i) != 'separator'
                 and menu.entrycget(i,'label').rsplit('  ',1)[-1].startswith('Max 500 MB') ))
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
print('after clicking the inactive group', repr(inactive[3].name), ':', v.current_key)

#The settings of overviews, shown instead of the fields of plots: a menu of
#the particle types, and the toggles of the variables of correlation plots:
def overview_settings():
    oc = tv._overview_controls
    return { 'shown' : bool(oc.frame.winfo_ismapped()),
             'plot fields shown' : bool(tv._plot_fields.winfo_ismapped()),
             **{ name : ( [ t for t, var in w.items() if var.get() ] if isinstance(w,dict)
                          else text(w) if w.winfo_class() == 'TButton' else w.get() )
                 for name, w in oc._widgets.items() } }
tv.logic.on_show_group('correlations')
tv.logic.on_select_key('overview:correlations')
wait()
print('settings of the correlations:', overview_settings())
toggles = [ c for c in tv._overview_controls._body.winfo_children()
            if str(c.cget('style')) == 'Choice.Toolbutton' ]
next( c for c in toggles if text(c) == 'ux' ).invoke()
menu = tv._overview_controls._widgets['display_only']
menu.set(menu.cget('values')[0])
menu.event_generate('<<ComboboxSelected>>')
wait()
print('after turning ux off and choosing all:', overview_settings(),
      v.group_settings('correlations')[0][1])
button = next( c for c in tv._overview_controls._body.winfo_children()
               if c.winfo_class() == 'TButton' )
for _ in range(2):
    clicked = text(button)
    button.invoke()
    wait()
    button = next( c for c in tv._overview_controls._body.winfo_children()
                   if c.winfo_class() == 'TButton' )
    print(f'after clicking {clicked!r}:', overview_settings()['variables'],
          '| button now:', text(button))
tv.logic.on_select_key('plot:x')
pump()
print('with a plot shown:', overview_settings()['shown'], overview_settings()['plot fields shown'])

#The windows of the help topics, formatted (see _helptext):
for label, title, blocks in tv.logic.help_topics():
    before = set(root.winfo_children())
    tv.show_text(title,blocks)
    pump(0.1)
    top, = set(root.winfo_children()) - before
    text = next( w for w in top.winfo_children()[0].winfo_children() if w.winfo_class() == 'Text' )
    print(f'help {label!r}:', top.title(), '| sections:', len(text.tag_ranges('section')) // 2,
          '| lines:', int(text.index('end').split('.')[0]) > 10)
    take_focus(text)
    text.event_generate('<KeyPress-q>')#(closes it, as Esc)
    pump(0.1)
    print('   closed with q:', not top.winfo_exists())
print('help in the menu:', [ tv._actions_menu.entrycget(i,'label')
                             for i in range(tv._actions_menu.index('end') + 1) ])
#The menu bar (only used on macOS, with the menus of the viewer), and the
#icon of the windows (in two sizes):
bar = tv._menubar(root)
print('menu bar:', { bar.entrycget(i,'label') : [ m.entrycget(j,'label') for j in range(m.index('end') + 1) ]
                     for i in range(bar.index('end') + 1)
                     for m in [ root.nametowidget(bar.entrycget(i,'menu')) ] })
print('icons:', [ ( im.width(), im.height() ) for im in tv._icons ])

#Rows of settings wrap in narrow frames, also with items in frames, whose sizes
#Tk only knows when idle:
top = tkinter.Toplevel(root)
narrow = tkinter.Frame(top,width=200,height=100)
narrow.pack(fill='both',expand=True)
top.geometry('200x100')
pump()
flow = Flow(narrow)
items = []
for i in range(4):
    item = tkinter.Frame(narrow)
    tkinter.Label(item,text=f'setting {i}').pack(side='left')
    items.append(item)
flow.set(items)
pump()
print('settings in a narrow frame, rows:', len(flow._rows))
top.destroy()

#The align helper: the means of the particles (read in a thread), and the
#edit added to the edit field:
aw = AlignWindow(tv)
for _ in range(500):
    pump(0.02)
    if aw._stats is not None and aw._stats.complete:
        break
print('align means:', str(aw._means.cget('text')).replace('\n',' | '))
print('align edit:', rounded_numbers(aw._edit.get('1.0','end').strip()))
print('align result:', str(aw._result.cget('text')), '| add enabled:', 'disabled' not in aw._add.state())
aw._keep.set('(0,1,0)')
aw._move.set(True)
aw._point.set('(0,0,1m)')
aw._coords['z'].set(False)
aw._update()
print('align edit, keeping (0,1,0) and moving to (0,0,1m) in x and y:',
      rounded_numbers(aw._edit.get('1.0','end').strip()))
print('align result:', str(aw._result.cget('text')))
aw._target.set('(1,2)')
aw._update()
print('align with a bad direction:', str(aw._result.cget('text')),
      '| add enabled:', 'disabled' not in aw._add.state())
aw._target.set('(0,0,1)')
aw._update()
aw._on_add()
pump()
wait()
print('edit field after adding:', rounded_numbers(tv._entries['edit'].get())[:60], '...',
      '| applied:', v.field_text('edit') == tv._entries['edit'].get(),
      '| align window closed:', not aw.window.winfo_exists())
v.set('edit','')
wait()

#A zoom of the plot shown is kept when it is drawn again (e.g. when the
#particles used change), but other plots are not zoomed:
tv.logic.on_select_key('plot:x')
wait()
tv.logic.pane.axes[0].set_xlim(2,20)
v.set('limit','500')
wait()
tv.logic.refresh(plot=True)
print('x range after changing the limit, zoom kept:',
      tuple( float(x) for x in tv.logic.pane.axes[0].get_xlim() ))
tv.logic.on_select_key('plot:y')
wait()
print('x range of another plot, not zoomed:', tv.logic.pane.axes[0].get_xlim() != (2,20))
v.set('limit','')
wait()

#"Show code" (next to "Write file") shows the command and the code
#writing the picked and edited particles, in all languages:
print('show code button enabled:', 'disabled' not in tv._write_code.state())
tv._write_code.invoke()
pump()
codewin = next( w for w in root.winfo_children()
                if isinstance(w,tkinter.Toplevel) and w.title() == 'Code of a new file' )
def descendants( w ):
    for c in w.winfo_children():
        yield c
        yield from descendants(c)
tabs = next( c for c in descendants(codewin) if c.winfo_class() == 'TNotebook' )
print('code window: tabs', [ tabs.tab(t,'text') for t in tabs.tabs() ],
      '| copy buttons', [ str(c.cget('text')) for c in descendants(codewin)
                          if c.winfo_class() == 'TButton' and 'Copy' in str(c.cget('text')) ],
      '| command:', next( c.get('1.0','end').strip() for c in descendants(codewin)
                          if c.winfo_class() == 'Text' ))
codewin.destroy()
#(the focus goes back to the main window when it is closed):
pump(0.5)

#(the changes of the focus, and who moves it to the plot, shown below if a
#window does not get the focus, to find out why):
focus_log = []
root.bind_all('<FocusIn>',lambda e : focus_log.append(f'{time.monotonic():.2f} FocusIn {e.widget}'),'+')
_canvas_focus_set = tv.canvas.get_tk_widget().focus_set
def _logged_focus_set():
    import traceback
    focus_log.append(f'{time.monotonic():.2f} canvas.focus_set from\n'
                     + ''.join(traceback.format_stack(limit = 6)[:-1]))
    _canvas_focus_set()
tv.canvas.get_tk_widget().focus_set = _logged_focus_set

#Each secondary window gets the keyboard focus when it is shown, and Esc (in
#the widget with the focus) closes it:
openers = { 'help' : lambda : tv.show_text('Data caching',viewer_ui.cache_blocks),
            'examples' : lambda : Examples(tv,viewer_ui.example_topics['pick'],lambda _e : None),
            'plot code' : tv._code.invoke,
            'code of a new file' : tv._write_code.invoke,
            'write' : lambda : WriteWindow(tv),
            'align' : lambda : AlignWindow(tv) }
for name, opener in openers.items():
    before = set(root.winfo_children())
    opener()
    pump(0.3)
    window = next( w for w in root.winfo_children()
                   if w not in before and isinstance(w,tkinter.Toplevel) )
    #(which can take a moment, with some window managers):
    focus_log.append(f'{time.monotonic():.2f} opened the {name} window {window}')
    for _ in range(30):
        focus = root.focus_get()
        has_focus = focus is not None and focus.winfo_toplevel() is window
        if has_focus:
            break
        pump(0.1)
    if not has_focus:
        #(what the window and the focus are, to find out why, on systems
        #where this fails):
        sys.stderr.write(f'DIAGNOSTICS {name} window: focus in {focus!r}'
                         f' (toplevel {focus.winfo_toplevel()!r})' if focus is not None else
                         f'DIAGNOSTICS {name} window: no focus in this application')
        sys.stderr.write(f' | window {window!r}: mapped {window.winfo_ismapped()}, viewable'
                         f' {window.winfo_viewable()}, state {window.state()}, geometry'
                         f' {window.winfo_geometry()}, screen {window.winfo_screenwidth()}x'
                         f'{window.winfo_screenheight()}, Tk {tkinter.TkVersion}'
                         f' | focus of Tk: {root.tk.call("focus")!r}\n')
        window.focus_force()
        pump(0.5)
        sys.stderr.write(f'DIAGNOSTICS after focus_force: {root.focus_get()!r}\n')
        sys.stderr.write('DIAGNOSTICS focus log:\n' + '\n'.join(focus_log) + '\n')
    ( focus or window ).event_generate('<Escape>')
    pump()
    print(f'{name} window: keyboard focus in it: {has_focus} | closed by Esc:',
          not window.winfo_exists())

#Writing a file happens in a thread, with a message and the buttons disabled
#meanwhile (the window closes when it is written):
ww = WriteWindow(tv)
ww._name.delete(0,'end')
ww._name.insert(0,'written_by_tk.mcpl.gz')
ww._write()
print('while writing:', str(ww._message.cget('text')), [ str(b.state()) for b in ww._buttons ])
for _ in range(500):
    pump(0.02)
    if not ww._writing:
        break
print('written:', pathlib.Path('written_by_tk.mcpl.gz').exists(),
      '| window closed:', not ww._code.window.winfo_exists(), '| status:', str(tv._status[0].cget('text')))

#Writing the same file again asks first (here with a stand-in for the question,
#since native dialogs wait until they are closed): no keeps the window open,
#yes overwrites the file:
for answer in ( False, True ):
    tv.ask_yes_no = lambda question, answer = answer : print(' asked:', question, answer) or answer
    ww = WriteWindow(tv)
    ww._name.delete(0,'end')
    ww._name.insert(0,'written_by_tk.mcpl.gz')
    ww._write()
    for _ in range(500):
        pump(0.02)
        if not ww._writing:
            break
    print(' window closed:', not ww._code.window.winfo_exists(), '| status:', str(tv._status[0].cget('text')))
    if ww._code.window.winfo_exists():
        ww._code.window.destroy()

#In a small window (as on a screen of 1024x768 pixels, where the window can be
#narrower than its layout wants), nothing is squeezed away: the axes, and
#skip, limit, and the button writing the particles go to lines of their own, so all fields and buttons are shown and wide enough. In a large
#window, they are back in their rows. In both, the parts with narrow layouts
#use them exactly when their wide layouts do not fit (as the large window is
#only as large as the screen allows, which on some systems is not enough for
#the wide layouts).
def squeezed():
    """The fields and buttons which are not shown or narrower than half of
    what they ask for (only those whose part of the window is shown)"""
    res, todo = [], [ root ]
    while todo:
        w = todo.pop()
        todo += w.winfo_children()
        if ( w.winfo_class() in ( 'TEntry', 'TCombobox', 'TButton', 'TCheckbutton', 'TMenubutton' )
             and w.winfo_manager() and w.master.winfo_ismapped()
             and ( not w.winfo_ismapped() or w.winfo_width() < w.winfo_reqwidth() // 2 ) ):
            res.append(str(w))
    return res
def misfits():
    """The parts with narrow layouts whose layout does not match the width
    they have: narrow when the wide layout fits, or wide when it does not"""
    res = []
    for name, lay in ( ( 'particles', tv._particle_layout ), ):
        fits = lay._wide_width is None or lay._available() >= lay._wide_width
        if lay.is_narrow == fits:
            res.append(name)
    flow = tv._axes_flow#(the axes, in more than one row when one is too narrow)
    need = sum( w.winfo_reqwidth() + flow._pad for w in flow._items )
    if ( len(flow._rows) > 1 ) != ( need > flow.frame.winfo_width() ):
        res.append('axes')
    return res
minsize = root.minsize()
tv.logic.on_select_key('plot:x')
for name, geometry in ( ( 'small', '984x648' ), ( 'large', '1400x900' ) ):
    root.minsize(1,1)
    root.geometry(geometry)
    pump()
    #(which layouts are narrow depends on the fonts and the size of the
    #window, so only whether they fit is shown):
    bad = misfits()
    #(skip, limit, and the buttons writing the particles end at the right
    #edge, also in their own row in narrow windows):
    writing = tv._write.master
    at_right = writing.winfo_rootx() + writing.winfo_width() == ( writing.master.winfo_rootx()
                                                                 + writing.master.winfo_width() )
    print(f'{name} window: squeezed: {squeezed()} | layouts fit the width: {not bad}'
          + ( f' (not: {bad})' if bad else '' ) + f' | write buttons at the right: {at_right}')
root.minsize(*minsize)

#The layout, in the large window: the labels of the axes, the settings, and
#the plot expression start at the left edge, and skip is right before limit,
#together at the right, above the button writing the particles:
tv.logic.on_select_key('plot:ekin;logx=auto;logy')
pump()
def left( w ):
    return w.winfo_rootx() - tv._plot_head.winfo_rootx()
xlabel = xaxis.master.winfo_children()[0]
setting = tv._controls.frame.winfo_children()[0]
tv._advanced.set(True)
tv._show_advanced()
pump()
expr_label = tv._expression.winfo_children()[0]
print('left edges of "X axis:", the first setting, and "Expression:" (from the header):',
      left(xlabel), left(setting), left(expr_label))
tv._advanced.set(False)
tv._show_advanced()
pump()
skip_entry, limit_label = tv._entries['skip'], tv._entries['limit'].master.winfo_children()[3]
gap = limit_label.winfo_rootx() - ( skip_entry.winfo_rootx() + skip_entry.winfo_width() )
box = skip_entry.master
right = lambda w : w.winfo_rootx() + w.winfo_width()
print('skip and limit in one group:', skip_entry.master is tv._entries['limit'].master,
      '| room between skip and limit:', gap,
      '| limit as far right as the buttons below:',
      right(tv._entries['limit']) == right(box) == right(tv._write.master),
      '| right of the pick fields:', box.winfo_rootx() > right(tv._entries['pick']))
#(the marks of the checks of skip and limit are inside their fields, at the
#right end):
for field in ( 'skip', 'limit' ):
    tv.show_check(field,False)
    pump()
    entry, mark = tv._entries[field], tv._marks[field]
    print(f'mark of {field}: {str(mark.cget("text"))!r} | inside the field at its right end:',
          entry.winfo_rootx() < mark.winfo_rootx() and right(mark) <= right(entry)
          and right(entry) - right(mark) < 10)
    tv.show_check(field,None)

#The scrollbar of the cards is only shown when they do not fit (as in the low
#window):
for name, geometry in ( ( 'high', '1400x2000' ), ( 'low', '1400x500' ) ):
    root.minsize(1,1)
    root.geometry(geometry)
    pump()
    c = tv._cards.canvas
    fits = float(c.cget('scrollregion').split()[3]) <= c.winfo_height()
    #(whether they fit in the high window depends on the size of the screen):
    print(f'{name} window: scrollbar shown exactly when the cards do not fit:',
          bool(tv._cards.bar.winfo_ismapped()) == ( not fits ),
          *( [ '| the cards fit:', fits ] if name == 'low' else [] ))
root.geometry('1400x900')
root.minsize(*minsize)
pump()

#The window of examples of picks has a button (and the key m) showing more
#details, the help of picks:
examples = Examples(tv,'pick',lambda e : None)
pump()
window = [ w for w in root.winfo_children() if w.winfo_class() == 'Toplevel' ][-1]
buttons = [ w for f in window.winfo_children() for w in f.winfo_children() if w.winfo_class() == 'TButton' ]
print('buttons of the examples:', [ ( str(b.cget('text')), int(b.cget('underline')) ) for b in buttons ])
print('focus in the window of the examples:', str(focus_of(root) or '').startswith(str(window)))
focus_of(root).event_generate('<Key-m>')
pump()
helps = [ w for w in root.winfo_children() if w.winfo_class() == 'Toplevel' and w.winfo_exists() ]
print('after the key m: examples closed:', not window.winfo_exists(),
      '| help shown:', [ w.title() for w in helps ])
for w in helps:
    w.destroy()

#The examples can be scrolled, and a click on one applies it (and closes the
#window):
Examples(tv,'pick',lambda e : tv._use_example('pick',e))
pump()
window = [ w for w in root.winfo_children() if w.winfo_class() == 'Toplevel' ][-1]
def descendants_of( w ):
    for c in w.winfo_children():
        yield c
        yield from descendants_of(c)
text = next( w for w in descendants_of(window) if w.winfo_class() == 'Text' )
print('examples with a scroll bar:', any( w.winfo_class() == 'TScrollbar' for w in descendants_of(window) ),
      '| more than shown:', text.yview()[1] < 1.0)
example = text.get('example1.first','example1.last')
x, y, _, _ = text.bbox('example1.first')
#(over it first, as Tk finds the text under the mouse with its motion):
text.event_generate('<Motion>',x=x+2,y=y+2)
text.event_generate('<Button-1>',x=x+2,y=y+2)
wait()
print(f'after clicking the example {example!r}: applied: {v.field_text("pick") == example}',
      '| window closed:', not window.winfo_exists())
v.set('pick','')
wait()

tv.close_window()
print('closed:', tv.logic.closed)

#The viewer as started by mcpltool -w (and mcpl.view), here with a window
#which is closed after a while, after which the commands doing the same are
#printed:
def root_closing_soon():
    #(closed as by the user, with the handler of closing the window):
    r = _root()
    r.after(2000,lambda : r.tk.eval(r.protocol('WM_DELETE_WINDOW')))
    return r
viewer_tk._root = root_closing_soon
try:
    mcpldev.app_mcpltool(['mcpltool','-w','{"groups":["spectra"]}','-p','pdgcode == gamma','example.mcpl'])
except SystemExit as e:
    print('mcpltool -w ended with exit code', e.code)
