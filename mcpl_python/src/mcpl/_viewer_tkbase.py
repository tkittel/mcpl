
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

"""Helpers of the parts of the viewer with Tk (see _viewer_tk)"""

__all__ = []

import weakref

from ._viewer_ui import colors


def tk_modules():
    """The modules of tkinter (imported when used, since Python can come
    without them)"""
    import tkinter
    from tkinter import ttk
    return tkinter, ttk

def focus_of( widget ):
    """The widget with the keyboard focus (as widget.focus_get()), or None,
    also while the focus is in the list of a combobox (which tkinter does
    not know as a widget)"""
    try:
        return widget.focus_get()
    except KeyError:
        return None

def wrapped( text, font, width, nlines = 2 ):
    """The text in at most nlines lines which fit the width (in pixels) with
    the font, broken at spaces, with the last line elided if needed"""
    lines, words = [], text.split(' ')
    while words and len(lines) < nlines - 1:
        n = 1
        while n < len(words) and font.measure(' '.join(words[:n+1])) <= width:
            n += 1
        if font.measure(words[0]) > width:
            break#(a word which does not fit is elided on the last line)
        lines.append(' '.join(words[:n]))
        words = words[n:]
    if words:
        lines.append(elided(' '.join(words),font,width))
    return lines

def elided( text, font, width ):
    """The text, shortened with ... at the end to fit the width (in pixels)
    with the font"""
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + '\u2026') > width:
        text = text[:-1]
    return text.rstrip() + '\u2026'

def on_paste( widget, fct ):
    """Call fct after text is pasted in or cut from the widget (with the keys or
    the menus: on macOS, Cmd+V gives no key release event)"""
    for event in ( '<<Paste>>', '<<Cut>>' ):
        widget.bind(event,lambda _e : widget.after_idle(fct),'+')

#The keys of entries which do something else than editing the text (so the
#text is not checked again after them):
command_keys = ( 'Return', 'KP_Enter', 'Escape', 'Up', 'Down', 'Tab' )

def windowing_system( widget ):
    """The windowing system of Tk (x11, win32, or aqua for macOS)"""
    return widget.tk.call('tk','windowingsystem')

def repaint_after_resize( root, delay = 150 ):
    """Repaint all widgets of the window root once its size has stopped
    changing (for delay milliseconds). With compositing (e.g. under Wayland),
    parts of widgets which Tk did not redraw while the window was resized
    (e.g. maximised while busy) could otherwise keep old pixels, also when
    other windows are moved over them."""
    pending, size = [ None ], [ None ]
    def repaint():
        pending[0] = None
        todo = [ root ]
        while todo:
            w = todo.pop()
            todo += w.winfo_children()
            if w.winfo_ismapped():
                w.event_generate('<Expose>')
    def on_configure( event ):
        if event.widget is not root or ( event.width, event.height ) == size[0]:
            return
        size[0] = ( event.width, event.height )
        if pending[0] is not None:
            root.after_cancel(pending[0])
        pending[0] = root.after(delay,repaint)
    root.bind('<Configure>',on_configure,'+')

def mnemonics( labels, preferred = None ):
    """The positions of the letters to underline in the labels of a menu: of
    the preferred letter of the label (in the dict preferred), or else of a
    letter which no label before it has, preferring capitals, then the starts
    of words (or -1)"""
    preferred = preferred or {}
    used, res = { c.lower() for c in preferred.values() }, []
    for label in labels:
        if label in preferred:
            i = label.lower().index(preferred[label].lower())
            res.append(i)
            continue
        free = [ i for i, c in enumerate(label) if c.isalpha() and c.lower() not in used ]
        starts = [ i for i in free if i == 0 or not label[i-1].isalpha() ]
        i = next( iter([ i for i in free if label[i].isupper() ] + starts + free), -1 )
        if i >= 0:
            used.add(label[i].lower())
        res.append(i)
    return res

def shortcut_name( letter, root ):
    """The name of the shortcut of the letter (see bind_shortcut), as shown"""
    return f'{"Cmd" if windowing_system(root) == "aqua" else "Ctrl"}+{letter.upper()}'

def bind_shortcut( root, letter, fct ):
    """Call fct() for Ctrl and the letter, or Alt and the letter (both work
    the same, also Cmd and Option on macOS), anywhere in the window root"""
    tk, _ = tk_modules()
    mods = ( 'Control', 'Alt' ) + ( ( 'Command', 'Option' ) if windowing_system(root) == 'aqua' else () )
    for mod in mods:
        for key in ( letter.lower(), letter.upper() ):
            try:
                root.bind(f'<{mod}-Key-{key}>',lambda _e : ( fct(), 'break' )[1])
            except tk.TclError:#(a modifier which this Tk does not have)
                pass

def bind_enter( widget, fct ):
    """Call fct() when Enter (also that of the keypad) is pressed in the widget"""
    for key in ( '<Return>', '<KP_Enter>' ):
        widget.bind(key,lambda _e : fct())

class GreyText:
    """Grey texts shown in empty entries (e.g. placeholders, or what is used
    when nothing is given), which are not the texts of the entries"""
    def __init__( self ):
        self._showing = set()#(the entries showing a grey text)

    def showing( self, w ):
        return w in self._showing

    def text( self, w ):
        """The text of the entry w (empty while it shows a grey text)"""
        return '' if w in self._showing else w.get()

    def set( self, w, text ):
        """Set the (normal) text of the entry w"""
        w.delete(0,'end')
        self._showing.discard(w)
        w.configure(foreground=colors['normal'])
        w.insert(0,text)

    def show( self, w, grey ):
        """Show the grey text in the entry w"""
        w.delete(0,'end')
        w.insert(0,grey)
        w.configure(foreground=colors['dim'])
        self._showing.add(w)

    def remove( self, w ):
        """Remove the grey text of the entry w, if it shows one"""
        if w in self._showing:
            self.set(w,'')

    def forget( self, w ):
        """The entry w no longer shows a grey text (e.g. it was emptied)"""
        self._showing.discard(w)

def arrow_image( widget ):
    """A solid arrow pointing left, as high as the capital letters of the
    default font, in the colour of the texts of buttons (drawn, as arrow
    characters are thin, and some are colour symbols on macOS)"""
    import tkinter.font
    tk, ttk = tk_modules()
    font = tkinter.font.nametofont('TkDefaultFont')
    h = max( 9, round( 0.8 * font.metrics('ascent') ) ) | 1
    w = round( 1.2 * h )
    color = ttk.Style(widget).lookup('TButton','foreground') or 'black'
    img = tk.PhotoImage(width=w,height=h)
    mid, head, shaft = h // 2, ( h + 1 ) // 2, max( 2, h // 4 )
    for x in range(w):
        #(the head, a triangle as wide as half the height, then the shaft):
        half = mid * x // head if x < head else shaft // 2
        img.put(color,to=(x,mid-half,x+1,mid+half+1))
    return img

class Tooltip:
    """A small window with the text (from the function text) next to the
    mouse, when it stays over the widget for a moment, until it leaves it, or
    a mouse button or key is pressed"""
    delay = 500#(ms)

    def __init__( self, widget, text ):
        self._widget, self._text = widget, text
        self._pending = self._window = None
        widget.bind('<Enter>',self._schedule,'+')
        for event in ( '<Leave>', '<ButtonPress>', '<KeyPress>' ):
            widget.bind(event,self._hide,'+')

    def _schedule( self, event ):
        self._hide()
        self._pending = self._widget.after(self.delay,lambda : self._show(event.x_root,event.y_root))

    def _show( self, x, y ):
        tk, ttk = tk_modules()
        self._pending = None
        text = self._text()
        if not text or not self._widget.winfo_exists():
            return
        self._window = w = tk.Toplevel(self._widget)
        w.wm_overrideredirect(True)
        ttk.Label(w,text=text,background=colors['tooltip'],relief='solid',borderwidth=1,
                  padding=(6,3),wraplength=420).pack()
        #(below and right of the mouse, but on the screen):
        w.update_idletasks()
        x = min( x + 12, w.winfo_screenwidth() - w.winfo_reqwidth() - 4 )
        if y + 20 + w.winfo_reqheight() > w.winfo_screenheight():
            y -= 10 + w.winfo_reqheight()
        else:
            y += 20
        w.wm_geometry(f'+{x}+{y}')

    def _hide( self, _event = None ):
        if self._pending is not None:
            self._widget.after_cancel(self._pending)
            self._pending = None
        if self._window is not None:
            self._window.destroy()
            self._window = None

#The layouts which follow the widths of their frames (NarrowLayout and Flow,
#which change them when Tk tells of new sizes, see settle):
_layouts = weakref.WeakSet()

def settle( root ):
    """Lays out the window now, to its final sizes (instead of in steps, when
    idle and when Tk tells the layouts of the new sizes of their frames), e.g.
    before a slow plot is drawn, so the fields do not move while it is drawn"""
    #(the layouts in the window of root, and not e.g. of a closed one):
    layouts = [ layout for layout in list(_layouts) if layout.widget.tk is root.tk ]
    for _ in range(10):
        root.update_idletasks()
        #(all fitted, also after one which changed):
        changed = [ layout._fit() for layout in layouts ]
        if not any(changed):
            return

class NarrowLayout:
    """Switches a part of a window to its narrow layout (with narrow(True))
    when the width it has (available(), by default the width of the part, when
    it changes) is less than the width it asks for in its wide layout
    (measured once, when it is first shown), and back (with narrow(False))
    when it has enough, so nothing in it gets squeezed away (Tk hides widgets
    which get no room, e.g. in the small windows of small screens)"""
    def __init__( self, part, narrow, available = None ):
        self._part, self._narrow = part, narrow
        self.widget = part
        self._available = available or part.winfo_width
        self._wide_width, self.is_narrow = None, False
        part.bind('<Configure>',lambda _e : self._fit(),'+')
        _layouts.add(self)

    def _fit( self ):
        """Switches the layout if needed (and returns whether it did)"""
        if not self._part.winfo_exists():
            return False
        if self._wide_width is None:
            self._wide_width = self._part.winfo_reqwidth()
        narrow = self._available() < self._wide_width
        if narrow == self.is_narrow:
            return False
        self.is_narrow = narrow
        self._narrow(narrow)
        return True

class Flow:
    """Lays out widgets of a frame (the items, in their order) in rows as wide
    as the frame, as many on each row as fit, and again when its width
    changes (e.g. the settings of plots, in narrow windows). The rows have the
    style (of frames) given."""
    def __init__( self, frame, style = None, pad = 10 ):
        self.frame, self._style, self._pad = frame, style, pad
        self.widget = frame
        self._items, self._rows, self._width = [], [], None
        frame.bind('<Configure>',lambda _e : self.layout(),'+')
        _layouts.add(self)

    def set( self, items ):
        """Lay out these items (instead of those before)"""
        self._items = list(items)
        self._relayout()
        #(again when the sizes of new items are known, which Tk computes when
        #idle, e.g. of frames):
        self.frame.after_idle(self._relayout)

    def _relayout( self ):
        if self.frame.winfo_exists():
            self._width = None
            self.layout()

    def _fit( self ):
        return self.frame.winfo_exists() and self.layout()

    def layout( self ):
        """Lays out the items for the width of the frame, if it changed (and
        returns whether it did)"""
        _, ttk = tk_modules()
        width = self.frame.winfo_width()
        if width == self._width:
            return False
        self._width = width
        if width <= 1:#(not shown yet: in one row)
            width = 10**9
        for row in self._rows:
            row.destroy()#(which unpacks the items in it)
        self._rows, x = [], width
        for w in self._items:
            need = w.winfo_reqwidth() + self._pad
            if x + need > width and ( x > 0 or not self._rows ):
                row = ttk.Frame(self.frame,**( { 'style' : self._style } if self._style else {} ))
                row.pack(fill='x',anchor='w')
                self._rows.append(row)
                x = 0
            w.pack(in_=self._rows[-1],side='left',padx=(0,self._pad))
            w.lift()#(above the row, which is made after it)
            x += need
        return True
