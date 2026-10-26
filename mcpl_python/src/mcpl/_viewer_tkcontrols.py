
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

"""The parts below the plot of the viewer with Tk (see _viewer_tk), and the
settings of plots and overviews in them"""

__all__ = []

from ._viewer_tkbase import Flow, GreyText, focus_of, tk_modules
from ._viewer_ui import part_colors

#(the labels at the start of the rows of the parts, in a column):
row_label = { 'width' : 9, 'anchor' : 'e' }

def make_part( parent, name, title, what, border ):
    """A part below the plot (with the colours of part_colors[name]), with a
    header with its title and what it is for. Returns the frame for its
    contents (in a frame with the border, its master), and the frame of the
    header (e.g. for buttons at its right)."""
    tk, ttk = tk_modules()
    box = tk.Frame(parent,background=part_colors[name],highlightthickness=1,
                   highlightbackground=border,highlightcolor=border)
    frame = ttk.Frame(box,style=f'{name}.TFrame',padding=(10,4,10,6))
    frame.pack(fill='both',expand=True)
    head = ttk.Frame(frame,style=f'{name}.TFrame')
    head.pack(fill='x',pady=(0,6))
    ttk.Label(head,text=f'{title.upper()}  \u00b7  {what}',
              style=f'{name}Head.TLabel').pack(side='left')
    return frame, head

def tint( part, name ):
    """Give the frames and labels in the part (see make_part) its colours (those
    with their own style keep it)"""
    _, ttk = tk_modules()
    for w in part.winfo_children():
        if isinstance(w,ttk.Frame) and not w.cget('style'):
            w.configure(style=f'{name}.TFrame')
            tint(w,name)
        elif isinstance(w,ttk.Label) and not w.cget('style'):
            w.configure(style=f'{name}.TLabel')

#(the choices of the menus of Controls for writing in them, and their hints):
written = {
    'display_by' : ( 'an expression...', ( 'Type what to show a curve of each value of,'
                                           ' e.g. x > 0cm or userflags, and press Enter' ) ),
    'display_only' : ( 'a condition...', ( 'Type which particles to show, e.g.'
                                           ' ekin > 1MeV, and press Enter' ) ) }

class Controls:
    """The settings of a plot (see WidgetViewer.plot_controls): a menu or a
    text field for each, in a row, which call on_change(option, shown text)
    when changed (with Enter, for the text fields). The row is made again
    when the kind of plot changes. The menus of display_by and display_only
    have a choice for writing an expression or a condition in them, which
    on_hint (if given) explains."""
    written = written

    def __init__( self, parent, on_change, on_hint = None, style = None ):
        _, ttk = tk_modules()
        #(the style of the labels and the frame, e.g. of a part, see make_part):
        self._styles = { 'style' : f'{style}.TLabel' } if style else {}
        self._frames = { 'style' : f'{style}.TFrame' } if style else {}
        self.frame = ttk.Frame(parent,**self._frames)
        #(each setting in a frame, in rows as wide as the window):
        self._flow = Flow(self.frame,**self._frames)
        self._on_change = on_change
        self._on_hint = on_hint
        self._kind = None
        self._widgets, self._used, self._grey = {}, {}, GreyText()

    def show( self, controls ):
        _, ttk = tk_modules()
        kind = controls[0] if controls else None
        if kind != self._kind:
            for w in self.frame.winfo_children():
                w.destroy()
            self._kind, self._widgets = kind, {}
            self._used = {}#entry -> its greyed text (what is used)
            self._grey = GreyText()#(of the entries showing it)
            items = []
            for name, label, choices, _, _ in ( controls[1] if controls else () ):
                item = ttk.Frame(self.frame,**self._frames)
                items.append(item)
                ttk.Label(item,text=label,**self._styles).pack(side='left',padx=(0,3))
                if choices is not None:
                    #(some also take what is written, the others only the choices):
                    if name in self.written:
                        choices = [ *choices, self.written[name][0] ]
                    w = ttk.Combobox(item,values=choices,
                                     width=14 if name in self.written else 7,
                                     state='normal' if name in self.written else 'readonly')
                    w.bind('<<ComboboxSelected>>',lambda _e, n=name, w=w : self._chosen(n,w))
                else:
                    w = ttk.Entry(item,width=12 if 'range' in name else 7)
                    #(the greyed text is removed while it is edited):
                    w.bind('<FocusIn>',lambda _e, w=w : self._show_used(w,None),'+')
                    w.bind('<FocusOut>',lambda _e, w=w : self._show_used(w,self._used.get(w)),'+')
                if name in self.written or choices is None:
                    w.bind('<Return>',lambda _e, n=name, w=w : self._on_change(n,self._text(w)))
                w.pack(side='left')
                self._widgets[name] = w
            self._flow.set(items)
        if not controls:
            return
        focus = focus_of(self.frame)
        for name, _, choices, shown, used in controls[1]:
            w = self._widgets[name]
            if w is focus:
                continue#(not while it is edited)
            if choices is not None:
                w.set(shown)
            else:
                self._show_used(w,None)
                w.delete(0,'end')
                w.insert(0,shown)
                if not shown and used:
                    self._show_used(w,used)

    def _show_used( self, w, used ):
        """Show the text of what is used greyed in the empty entry w (or remove
        it, if used is None)"""
        if used is None:
            self._grey.remove(w)
        elif not w.get():
            self._used[w] = used
            self._grey.show(w,used)

    def _text( self, w ):
        """The text of the entry w (empty while it shows a greyed text)"""
        return self._grey.text(w)

    def _chosen( self, name, w ):
        choice, hint = self.written.get(name,( None, None ))
        if w.get() != choice:
            self._on_change(name,w.get())
            return
        #(it is written in the field, and applied with Enter):
        w.set('')
        w.focus_set()
        if self._on_hint is not None:
            self._on_hint(hint)

class OverviewControls:
    """The settings of an overview (see WidgetViewer.overview_controls): a menu,
    toggle buttons (for the variables) or a button for each, in rows as wide
    as the window, which call on_change(name, shown text) when changed (for
    toggles, the text of the toggle). They are made again when the choices
    change. The style is that of the labels and the frames (see
    Controls)."""
    def __init__( self, parent, on_change, style ):
        _, ttk = tk_modules()
        self._frames = { 'style' : f'{style}.TFrame' }
        self.frame = ttk.Frame(parent,**self._frames)
        self._label = { 'style' : f'{style}.TLabel' }
        ttk.Label(self.frame,text='Settings:',**row_label,**self._label).pack(side='left',
                                                                             anchor='n',padx=(0,4))
        body = ttk.Frame(self.frame,**self._frames)
        body.pack(side='left',fill='x',expand=True)
        self._body, self._flow = body, Flow(body,pad = 4,**self._frames)
        self._on_change = on_change
        self._made, self._widgets = None, {}

    def show( self, controls ):
        tk, ttk = tk_modules()
        made = [ ( name, tuple(texts) ) for name, _, texts, _ in controls ]
        if made != self._made:
            for w in self._body.winfo_children():
                w.destroy()
            self._made, self._widgets, items = made, {}, []
            def label( text ):
                items.append(ttk.Label(self._body,text=text,**self._label))
            for name, text, texts, _ in controls:
                if text is None:#(a button, with its text)
                    w = ttk.Button(self._body,text=texts[0],takefocus=0,style='Small.TButton',
                                   command=lambda n=name, t=texts[0] : self._on_change(n,t))
                    items.append(w)
                    self._widgets[name] = w
                    continue
                label(f'{text}:')
                if name == 'variables':
                    toggles = {}
                    for t in texts:
                        var = tk.BooleanVar(self._body,value=False)
                        items.append(ttk.Checkbutton(self._body,text=t,variable=var,takefocus=0,
                                                     style='Choice.Toolbutton',
                                                     command=lambda n=name, t=t : self._on_change(n,t)))
                        toggles[t] = var
                    self._widgets[name] = toggles
                else:
                    w = ttk.Combobox(self._body,values=texts,state='readonly',
                                     width=max( len(t) for t in texts ) + 1)
                    w.bind('<<ComboboxSelected>>',lambda _e, n=name, w=w : self._on_change(n,w.get()))
                    items.append(w)
                    self._widgets[name] = w
            self._flow.set(items)
        for name, text, _, shown in controls:
            w = self._widgets[name]
            if isinstance(w,dict):#(toggles, on if shown)
                for t, var in w.items():
                    var.set(t in shown)
            elif text is not None:
                w.set(shown)
