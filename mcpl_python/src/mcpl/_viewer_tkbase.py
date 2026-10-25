
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
