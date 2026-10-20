
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

"""The viewer in a window with Tk (the tkinter module of Python), with the
views on the left, the plot (a matplotlib figure, with the toolbar of
matplotlib) on the right, and the fields and actions below it (see
_viewer_widgets for what happens when they are used)."""

__all__ = []

from . import _viewer_ui as ui
from ._viewer_widgets import WidgetViewer, run_with_ctrl_c


def _tk():
    """The modules of tkinter (imported when used, since Python can come
    without them)"""
    import tkinter
    from tkinter import ttk
    return tkinter, ttk

#Colours of the line below the fields, and of the marks of the checks:
_colors = { 'normal' : 'black', 'dim' : '#777777', 'ok' : '#2ca02c', 'error' : '#d62728' }

#Tk key names, as names of _viewer_ui (the others are characters):
_keymap = { 'Return' : 'Enter', 'KP_Enter' : 'Enter', 'Escape' : 'Esc',
            'F1' : 'F1', 'Up' : 'Up', 'Down' : 'Down', 'Prior' : 'PageUp',
            'Next' : 'PageDown' }
#(Shift, Control, Alt, and the Windows or Command key, in Tk event states):
_modifiers = 0x1 | 0x4 | 0x8 | 0x40

def _key_name( event ):
    """The name of the key of a Tk event, as in _viewer_ui, or None"""
    name = _keymap.get(event.keysym)
    if name in ( 'Up', 'Down' ) and event.state & _modifiers:
        return 'Move' + name
    if name is None and len(event.char) == 1 and event.char.isprintable():
        return event.char
    return name

class TkViewer(WidgetViewer):
    """The viewer in the Tk window root"""
    def __init__( self, viewer, root ):
        tk, ttk = _tk()
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg,
            NavigationToolbar2Tk,
        )
        from matplotlib.figure import Figure
        self.root = root
        root.title(f'MCPL viewer: {viewer.filename}')
        root.geometry('1400x900')
        if root.tk.call('tk','windowingsystem') == 'x11':
            ttk.Style(root).theme_use('clam')#(the default of X11 looks dated)
        import tkinter.font
        bold = tkinter.font.nametofont('TkDefaultFont').copy()
        bold.configure(weight='bold')
        self._bold = bold
        root.columnconfigure(1,weight=1)
        root.rowconfigure(0,weight=1)
        #The logo and the views (on the left):
        left = ttk.Frame(root,padding=6)
        left.grid(row=0,column=0,rowspan=2,sticky='ns')
        import base64

        from ._logo import logo_png
        self._logo = tk.PhotoImage(data=base64.b64encode(logo_png())).subsample(3)
        ttk.Label(left,image=self._logo).pack(anchor='w',pady=(0,6))
        self._views = tk.Listbox(left,width=34,activestyle='none',exportselection=False,
                                 takefocus=0,highlightthickness=0)
        self._views.pack(fill='y',expand=True)
        self._views.bind('<<ListboxSelect>>',self._on_view)
        moves = ttk.Frame(left)
        moves.pack(fill='x',pady=(6,0))
        for label, delta in ( ( 'Move up', -1 ), ( 'Move down', 1 ) ):
            ttk.Button(moves,text=label,takefocus=0,
                       command=lambda d=delta : self.on_move(d)).pack(side='left',expand=True,fill='x')
        self._hover(self._views,'views')
        #The status and the plot (on the right):
        main = ttk.Frame(root,padding=(0,6,6,0))
        main.grid(row=0,column=1,sticky='nsew')
        main.columnconfigure(0,weight=1)
        main.rowconfigure(2,weight=1)
        self._status = [ ttk.Label(main,font=bold), ttk.Label(main,foreground=_colors['dim']) ]
        for i, label in enumerate(self._status):
            label.grid(row=i,column=0,sticky='w')
        plot = ttk.Frame(main)
        plot.grid(row=2,column=0,sticky='nsew')
        fig = Figure(figsize=(10,6),dpi=100)
        self.canvas = FigureCanvasTkAgg(fig,master=plot)
        self.toolbar = NavigationToolbar2Tk(self.canvas,plot,pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side='bottom',fill='x')
        self.canvas.get_tk_widget().pack(side='top',fill='both',expand=True)
        super().__init__(viewer,fig)
        self.canvas.mpl_connect('button_press_event',self._on_mpl_click)
        self.canvas.mpl_connect('key_press_event',self._on_mpl_key)
        self.canvas.mpl_connect('motion_notify_event',self._on_mpl_motion)
        self._inaxes = None#(the axes under the mouse)
        #The fields, the line below them and the actions:
        bottom = ttk.Frame(root,padding=(6,4,6,6))
        bottom.grid(row=1,column=1,sticky='ew')
        bottom.columnconfigure(0,weight=1)
        self._entries, self._marks = {}, {}
        self._placeholders = {}#entry -> text shown in grey while it is empty
        self._showing = set()#(the entries showing their placeholder)
        info = { f[0] : f for f in ui.fields }
        for r, row in enumerate(ui.field_rows):
            frame = ttk.Frame(bottom)
            frame.grid(row=r,column=0,sticky='ew',pady=1)
            for field in row:
                _, label, _key, kpos, empty = info[field]
                lab = ttk.Label(frame,text=label + ':',underline=kpos)
                lab.pack(side='left',padx=(0 if field == row[0] else 12,4))
                if field in ui.menu_fields:
                    choices = self.menu_choices(field)
                    w = ttk.Combobox(frame,state='readonly',width=48,
                                     values=[ f'{n}  ({d})' for n, d in choices ])
                    w.bind('<<ComboboxSelected>>',lambda _e, f=field, c=choices :
                           self._on_menu(f,c))
                    w.pack(side='left')
                else:
                    w = ttk.Entry(frame,width=12 if len(row) > 1 else 60)
                    w.pack(side='left',fill='x',expand=len(row) == 1)
                    self._placeholders[w] = empty
                    self._bind_entry(w,field)
                mark = ttk.Label(frame,width=2)
                mark.pack(side='left')
                self._entries[field], self._marks[field] = w, mark
                self._hover(lab,field)
                self._hover(w,field)
        #(the field of the shown plot, which changes it, or removes it when
        #emptied):
        frame = ttk.Frame(bottom)
        frame.grid(row=len(ui.field_rows),column=0,sticky='ew',pady=1)
        ttk.Label(frame,text='Shown plot:').pack(side='left',padx=(0,4))
        w = ttk.Entry(frame,width=60)
        w.pack(side='left',fill='x',expand=True)
        self._bind_entry(w,'shown_plot')
        mark = ttk.Label(frame,width=2)
        mark.pack(side='left')
        self._entries['shown_plot'], self._marks['shown_plot'] = w, mark
        self._line = ttk.Label(bottom)
        self._line.grid(row=len(ui.field_rows)+1,column=0,sticky='w',pady=(2,2))
        buttons = ttk.Frame(bottom)
        buttons.grid(row=len(ui.field_rows)+2,column=0,sticky='w')
        for action, label, _keys, kpos in ui.actions:
            b = ttk.Button(buttons,text=label,underline=kpos,takefocus=0,
                           command=lambda a=action : self.on_action(a))
            b.pack(side='left',padx=(0,6))
            self._hover(b,action)
        self._statusbar = ttk.Label(bottom,foreground=_colors['dim'])
        self._statusbar.grid(row=len(ui.field_rows)+3,column=0,sticky='w',pady=(4,0))
        self._popup = None#(the list of completions: (field, start, Toplevel, Listbox))
        root.bind('<Key>',self._on_root_key)
        root.protocol('WM_DELETE_WINDOW',self.close_window)

    #Implementation of WidgetViewer:

    def show_views( self, labels, current ):
        lb = self._views
        if list(lb.get(0,'end')) != labels:
            lb.delete(0,'end')
            lb.insert('end',*labels)
        lb.selection_clear(0,'end')
        lb.selection_set(current)
        lb.see(current)

    def show_status( self, first, second ):
        self._status[0].configure(text=first)
        self._status[1].configure(text=second)

    def show_field( self, field, text ):
        w = self._entries[field]
        if field in ui.menu_fields:
            descr = dict(self.menu_choices(field)).get(text,'')
            w.set(f'{text}  ({descr})')
            return
        self._set_text(w,text)

    def show_plot_field( self, text ):
        w = self._entries['shown_plot']
        if text is None:
            w.configure(state='normal')
            w.delete(0,'end')
            w.configure(state='disabled')
        elif str(w['state']) == 'disabled' or self.root.focus_get() is not w:
            #(not while it is edited):
            w.configure(state='normal')
            if w.get() != text:
                w.delete(0,'end')
                w.insert(0,text)

    def show_line( self, text, style ):
        self._line.configure(text=text,foreground=_colors.get(style,_colors['normal']))

    def show_check( self, field, ok ):
        mark = self._marks[field]
        if ok is None:
            mark.configure(text='')
        else:
            mark.configure(text='\u2713' if ok else '\u2717',
                           foreground=_colors['ok' if ok else 'error'])

    def draw_plot( self ):
        self.canvas.draw_idle()

    def focus_field( self, field ):
        w = self._entries[field]
        w.focus_set()
        if field in ui.menu_fields:
            w.event_generate('<Down>')#(opens the list of the menu)
        else:
            w.icursor('end')
            self.on_field_edited(field,self._text(w))

    def ask_file( self, action ):
        import os
        from tkinter import filedialog
        name = self.suggested_filename(action)
        title = 'Write the particles to' if action == 'write' else 'Save the viewer state in'
        chosen = filedialog.asksaveasfilename(parent=self.root,title=title,
                                              initialdir=os.path.dirname(os.path.abspath(name)),
                                              initialfile=os.path.basename(name),
                                              confirmoverwrite=False)
        self.on_file(action,chosen or None)

    def show_help( self ):
        tk, ttk = _tk()
        top = tk.Toplevel(self.root)
        top.title('MCPL viewer: help')
        text = tk.Text(top,width=82,height=40,font='TkFixedFont',wrap='none')
        text.insert('1.0',ui.help_text)
        text.configure(state='disabled')
        text.pack(fill='both',expand=True)
        ttk.Button(top,text='Close',command=top.destroy).pack(pady=4)
        top.bind('<Escape>',lambda _e : top.destroy())
        top.focus_set()

    def close_window( self ):
        tk, _ttk = _tk()
        self.on_close()
        try:
            self.root.destroy()
        except tk.TclError:#(already destroyed)
            pass

    #Events of Tk and matplotlib:

    def _tick( self ):
        self.on_timer()
        if not self.closed:
            self.root.after(200,self._tick)

    def _on_view( self, _event ):
        sel = self._views.curselection()
        if sel and sel[0] != self.v.current:
            self.on_select(sel[0])

    def _on_menu( self, field, choices ):
        i = self._entries[field].current()
        if i >= 0:
            self.on_field_apply(field,choices[i][0])
        self.canvas.get_tk_widget().focus_set()

    def _hover( self, widget, name ):
        """Show the shortcut of the field or action under the mouse"""
        widget.bind('<Enter>',lambda _e : self._statusbar.configure(text=ui.shortcut_text(name)),'+')
        widget.bind('<Leave>',lambda _e : self._statusbar.configure(text=''),'+')

    def _on_root_key( self, event ):
        """Keys outside the text fields (the keys in them are handled by
        _bind_entry, and those over the plot by _on_mpl_key)"""
        tk, ttk = _tk()
        w = event.widget
        if isinstance(w,( ttk.Entry, ttk.Combobox, tk.Entry, tk.Text )) or w is self.canvas.get_tk_widget():
            return
        k = _key_name(event)
        if k is not None:
            self.on_key(k)

    def _on_mpl_key( self, event ):
        if event.key is None:
            return
        #(l and k change the log scales of the plot under the mouse, as in
        #matplotlib):
        if event.key.lower() in ui.scale_keys and self._inaxes in self.pane.axes:
            ax, axis = self._inaxes, ui.scale_keys[event.key.lower()]
            get, set_ = ( ( ax.get_yscale, ax.set_yscale ) if axis == 'logy'
                          else ( ax.get_xscale, ax.set_xscale ) )
            set_('linear' if get() == 'log' else 'log')
            self.canvas.draw_idle()
            return
        k = { 'up' : 'Up', 'down' : 'Down', 'enter' : 'Enter', 'escape' : 'Esc',
              'f1' : 'F1' }.get(event.key,event.key)
        for arrow, name in ( ( '+up', 'MoveUp' ), ( '+down', 'MoveDown' ) ):
            if k.endswith(arrow):
                k = name
        if k.startswith('shift+') and len(k) == 7:
            k = k[-1].upper()
        if len(k) == 1 or k in ( 'Up', 'Down', 'MoveUp', 'MoveDown', 'Enter', 'F1' ):
            self.on_key(k)

    def _on_mpl_motion( self, event ):
        self._inaxes = event.inaxes

    def _on_mpl_click( self, event ):
        self.canvas.get_tk_widget().focus_set()
        if not self.toolbar.mode:#(not while zooming or panning)
            self.on_click(event)

    #The text fields:

    def _bind_entry( self, w, field ):
        w.bind('<KeyRelease>',lambda e : self._on_entry_key(w,field,e))
        w.bind('<Return>',lambda _e : self._on_entry_enter(w,field))
        w.bind('<KP_Enter>',lambda _e : self._on_entry_enter(w,field))
        w.bind('<Escape>',lambda _e : self._on_entry_escape(field))
        w.bind('<Up>',lambda _e : self._on_entry_updown(w,field,-1))
        w.bind('<Down>',lambda _e : self._on_entry_updown(w,field,1))
        w.bind('<Tab>',lambda _e : self._on_entry_tab(w,field))
        w.bind('<FocusIn>',lambda _e : self._on_entry_focus(w,field),'+')
        w.bind('<FocusOut>',lambda _e : self._on_entry_unfocus(w),'+')

    def _text( self, w ):
        """The text of the entry (empty while it shows its placeholder)"""
        return '' if w in self._showing else w.get()

    def _set_text( self, w, text ):
        """Set the text of the entry (or show its placeholder if it is empty and
        not edited)"""
        w.delete(0,'end')
        self._showing.discard(w)
        w.configure(foreground=_colors['normal'])
        if not text and w in self._placeholders and self.root.focus_get() is not w:
            w.insert(0,self._placeholders[w])
            w.configure(foreground=_colors['dim'])
            self._showing.add(w)
        else:
            w.insert(0,text)

    def _on_entry_focus( self, w, field ):
        if w in self._showing:
            self._set_text(w,'')
        self.on_field_edited(field,self._text(w))

    def _on_entry_unfocus( self, w ):
        self._close_popup()
        if not w.get():
            self._set_text(w,'')

    def _on_entry_key( self, w, field, event ):
        if event.keysym in ( 'Return', 'KP_Enter', 'Escape', 'Up', 'Down', 'Tab' ):
            return
        self._close_popup()
        self.on_field_edited(field,self._text(w))

    def _on_entry_enter( self, w, field ):
        if self._popup is not None:
            self._insert_choice(w)
            return 'break'
        if self.on_field_apply(field,self._text(w)):
            self.canvas.get_tk_widget().focus_set()
        return 'break'

    def _on_entry_escape( self, field ):
        if self._popup is not None:
            self._close_popup()
            return 'break'
        self.on_field_cancel(field)
        self.canvas.get_tk_widget().focus_set()
        return 'break'

    def _on_entry_updown( self, w, field, delta ):
        if self._popup is not None:
            lb = self._popup[3]
            i = ( lb.curselection() or ( 0, ) )[0]
            i = ( i + delta ) % lb.size()
            lb.selection_clear(0,'end')
            lb.selection_set(i)
            lb.see(i)
            return 'break'
        text = self.on_history(field,delta)
        if text is not None:
            w.delete(0,'end')
            w.insert(0,text)
            self.on_field_edited(field,text)
        return 'break'

    def _on_entry_tab( self, w, field ):
        if self._popup is not None:
            self._insert_choice(w)
            return 'break'
        if field in ui.completing_fields or field == 'shown_plot':
            text, cursor, choices, start = self.on_complete(field,self._text(w),w.index('insert'))
            w.delete(0,'end')
            w.insert(0,text)
            w.icursor(cursor)
            if choices:
                self._open_popup(w,field,start,choices)
            self.on_field_edited(field,text)
        return 'break'

    def _open_popup( self, w, field, start, choices ):
        """The completions in a list below the field (Up and Down choose one,
        Enter or Tab inserts it, Esc closes the list)"""
        tk, _ttk = _tk()
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        nw = max( len(n) for n, _ in choices )
        lb = tk.Listbox(top,font='TkFixedFont',height=min(12,len(choices)),
                        width=min(100,max( nw + 2 + len(d or '') for n, d in choices )),
                        exportselection=False,activestyle='none')
        for n, d in choices:
            lb.insert('end',n.ljust(nw) + '  ' + ( d or '' ))
        lb.selection_set(0)
        lb.pack()
        lb.bind('<ButtonRelease-1>',lambda _e : self._insert_choice(w))
        top.geometry(f'+{w.winfo_rootx()}+{w.winfo_rooty() + w.winfo_height()}')
        self._popup = ( field, start, top, lb, choices )

    def _insert_choice( self, w ):
        field, start, _top, lb, choices = self._popup
        i = ( lb.curselection() or ( 0, ) )[0]
        name = choices[i][0]
        text, cursor = self._text(w), w.index('insert')
        w.delete(0,'end')
        w.insert(0,text[:start] + name + text[cursor:])
        w.icursor(start + len(name))
        self._close_popup()
        w.focus_set()
        self.on_field_edited(field,self._text(w))

    def _close_popup( self ):
        if self._popup is not None:
            self._popup[2].destroy()
            self._popup = None

def _root():
    """A Tk root window, or None if Tk can not show windows here (no tkinter,
    no display, or no Tk support in matplotlib)"""
    try:
        tk, _ttk = _tk()
        import matplotlib.backends.backend_tkagg  # noqa: F401
    except ImportError:
        return None
    try:
        return tk.Tk()
    except tk.TclError:
        return None

def run_viewer( viewer, root ):
    """Run the viewer in the Tk window root (from _root) until it is closed"""
    tv = TkViewer(viewer,root)
    tv.start()
    root.after(200,tv._tick)
    try:
        run_with_ctrl_c(root.mainloop,tv.close_window)
    finally:
        tv.on_close()
