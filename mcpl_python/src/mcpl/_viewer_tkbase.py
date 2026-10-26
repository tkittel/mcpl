
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
    """The windowing system of Tk (x11, win32 or aqua for macOS)"""
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

def mnemonics( labels ):
    """The positions of the letters to underline in the labels of a menu: of
    a letter which no label before it has, preferring capitals, then the
    starts of words (or -1)"""
    used, res = set(), []
    for label in labels:
        free = [ i for i, c in enumerate(label) if c.isalpha() and c.lower() not in used ]
        starts = [ i for i in free if i == 0 or not label[i-1].isalpha() ]
        i = next( iter([ i for i in free if label[i].isupper() ] + starts + free), -1 )
        if i >= 0:
            used.add(label[i].lower())
        res.append(i)
    return res

def bind_menu_key( root, button, letter ):
    """Open the menu of the button with Alt and the letter (Option on macOS),
    which is underlined in its label"""
    button.configure(underline=button.cget('text').index(letter))
    mod = 'Option' if windowing_system(root) == 'aqua' else 'Alt'
    for key in ( letter.lower(), letter.upper() ):
        root.bind(f'<{mod}-Key-{key}>',lambda _e : ( button.event_generate('<<Invoke>>'), 'break' )[1])

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

class Flow:
    """Lays out widgets of a frame (the items, in their order) in rows as wide
    as the frame, as many on each row as fit, and again when its width
    changes (e.g. the settings of plots, in narrow windows). The rows have the
    style (of frames) given."""
    def __init__( self, frame, style = None, pad = 10 ):
        self.frame, self._style, self._pad = frame, style, pad
        self._items, self._rows, self._width = [], [], None
        frame.bind('<Configure>',lambda _e : self.layout(),'+')

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

    def layout( self ):
        _, ttk = tk_modules()
        width = self.frame.winfo_width()
        if width == self._width:
            return
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
