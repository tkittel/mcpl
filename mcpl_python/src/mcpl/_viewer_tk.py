
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
_keymap = { 'Return' : 'Enter', 'KP_Enter' : 'Enter', 'Escape' : 'Esc', 'Delete' : 'Delete',
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
        root.title(f'MCPL viewer: {viewer.filename}')#(see show_title)
        root.geometry('1400x900')
        style = ttk.Style(root)
        if root.tk.call('tk','windowingsystem') == 'x11':
            style.theme_use('clam')#(the default of X11 looks dated)
            _check_fonts(root)
        #(the button of new plots, in the colour of the selected card):
        accent = _card_colors['accent']
        style.configure('Accent.TButton',foreground='white',background=accent,
                        bordercolor=accent)
        style.map('Accent.TButton',background=[ ( 'active', '#3d74ab' ) ])
        #(choices shown as a row of buttons, with the chosen one in the colour
        #of the selected card):
        style.configure('Choice.Toolbutton',relief='raised',borderwidth=1,padding=(8,3),
                        background='#e3e8ee')
        style.map('Choice.Toolbutton',background=[ ( 'selected', accent ), ( 'active', '#d0d8e2' ) ],
                  foreground=[ ( 'selected', 'white' ) ],relief=[ ( 'selected', 'sunken' ) ])
        #(the small buttons next to fields, as high as the fields):
        style.configure('Small.TButton',padding=(2,0))
        style.configure('Compact.TMenubutton',padding=(6,0))
        #(the compact buttons in the header of the part of the shown plot):
        for name in ( 'Head.TButton', 'Head.Accent.TButton' ):
            style.configure(name,padding=(8,0),width=-4)
        import tkinter.font
        bold = tkinter.font.nametofont('TkDefaultFont').copy()
        bold.configure(weight='bold')
        self._bold = bold
        #(the parts below the plot, see _part):
        for name, bg in _part_colors.items():
            style.configure(f'{name}.TFrame',background=bg)
            style.configure(f'{name}.TLabel',background=bg)
            style.configure(f'{name}Head.TLabel',background=bg,foreground=_card_colors['accent'],
                            font=( bold.cget('family'), 8, 'bold' ))
        root.columnconfigure(1,weight=1)
        root.rowconfigure(0,weight=1)
        #The logo and the views (on the left):
        left = ttk.Frame(root,padding=6)
        left.grid(row=0,column=0,rowspan=2,sticky='ns')
        import base64

        from ._logo import logo_png
        self._logo = tk.PhotoImage(data=base64.b64encode(logo_png())).subsample(3)
        ttk.Label(left,image=self._logo).pack(anchor='w',pady=(0,6))
        self._entries, self._marks = {}, {}
        #(the actions in a menu: another file, with the same plots, pick and
        #edit, see on_open_file, and those of ui.actions but writing, which
        #has its button with the pick and edit; in a row with the collection
        #of plots, see _menu_field):
        self._top_row = ttk.Frame(left)
        self._top_row.pack(fill='x',pady=(0,6))
        button = ttk.Menubutton(self._top_row,text='\u2630 Menu',takefocus=0,
                                style='Compact.TMenubutton')
        button.pack(side='left')
        menu = tk.Menu(button,tearoff=0)
        button['menu'] = menu
        menu.add_command(label='Open MCPL file...',command=self._ask_open)
        self._actions_menu, self._actions = menu, {}#(action -> index of its entry)
        for action, label, keys, kpos in ui.actions:
            if action != 'write':
                menu.add_command(label=label,underline=kpos,accelerator=keys[0],
                                 command=lambda a=action : self.on_action(a))
                self._actions[action] = menu.index('end')
        self._cards = _CardList(left,self)
        self._hover(self._cards.canvas,'views')
        #The status and the plot (on the right):
        main = ttk.Frame(root,padding=(0,6,6,0))
        main.grid(row=0,column=1,sticky='nsew')
        main.columnconfigure(0,weight=1)
        main.rowconfigure(2,weight=1)
        self._status = [ ttk.Label(main,font=bold), ttk.Label(main,foreground=_colors['dim']) ]
        for i, label in enumerate(self._status):
            label.grid(row=i,column=0,sticky='w')
        #(the part of the shown plot, in the colours of its selected card: the
        #plot with its toolbar, and its fields below them, see _plot_part):
        bg = _part_colors['Plot']
        part, head = _part(main,'Plot','Plot','the shown plot',_card_colors['accent'])
        part.master.grid(row=2,column=0,sticky='nsew')
        #(the fields at the bottom, packed first so the plot gets the rest):
        fields = ttk.Frame(part)
        fields.pack(side='bottom',fill='x')
        self._plot_fields = fields#(not shown for views which are not plots)
        plot = tk.Frame(part,name='plotbox',background=bg)
        self._plotbox = plot
        plot.pack(fill='both',expand=True,pady=(0,4))
        #(the widgets of the toolbar get the colour when they are made, as
        #matplotlib draws its icons on their background):
        for option in ( 'background', 'highlightBackground', 'activeBackground' ):
            root.option_add(f'*plotbox*{option}',bg)
        fig = Figure(figsize=(10,6),dpi=100)
        self.canvas = FigureCanvasTkAgg(fig,master=plot)
        self.toolbar = NavigationToolbar2Tk(self.canvas,plot,pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side='bottom',fill='x')
        #(the plot fills the space left, so it asks for little):
        self.canvas.get_tk_widget().configure(width=400,height=300)
        self.canvas.get_tk_widget().pack(side='top',fill='both',expand=True)
        super().__init__(viewer,fig)
        #(the collection of plots, above their cards):
        self._menu_field(self._top_row,'collection')
        self.canvas.mpl_connect('button_press_event',self._on_mpl_click)
        self.canvas.mpl_connect('key_press_event',self._on_mpl_key)
        self.canvas.mpl_connect('motion_notify_event',self._on_mpl_motion)
        self._inaxes = None#(the axes under the mouse)
        self._placeholders = {}#entry -> text shown in grey while it is empty
        self._showing = set()#(the entries showing their placeholder)
        self._plot_part(fields,head)
        _tint(part,'Plot')
        #Below the plot: the part of the particles (for all plots), and the
        #line below it:
        bottom = ttk.Frame(root,padding=(0,4,6,6))
        bottom.grid(row=1,column=1,sticky='ew')
        bottom.columnconfigure(0,weight=1)
        part, _ = _part(bottom,'Particles','Pick & edit','particles from the input file',
                        _card_colors['border'])
        part.master.grid(row=0,column=0,sticky='ew',pady=(2,0))
        info = { f[0] : f for f in ui.fields }
        #(plots are added with "+ New plot", and the collection is chosen
        #above the cards; the expressions get the width of the rows):
        rows = ( ( 'pick', 'skip', 'limit' ), ( 'edit', ) )
        assert sorted( f for row in rows for f in row ) == sorted(
            f for row in ui.field_rows for f in row if f not in ( 'plot', *ui.menu_fields ) )
        #(in a grid, so the expressions of the rows have the same width):
        grid = ttk.Frame(part)
        grid.pack(fill='x')
        grid.columnconfigure(1,weight=1)
        for r, row in enumerate(rows):
            col = 0
            for field in row:
                _, label, _key, kpos, empty = info[field]
                first = field == row[0]
                lab = ttk.Label(grid,text=label + ':',underline=kpos,
                                **( _row_label if first else {} ))
                lab.grid(row=r,column=col,sticky='e',padx=(0 if first else 12,4),pady=1)
                wide = field in _example_topics
                w = ttk.Entry(grid,width=20 if wide else 10)
                w.grid(row=r,column=col+1,sticky='ew' if wide else 'w')
                self._placeholders[w] = empty
                self._bind_entry(w,field)
                col += 2
                #(the examples right after the field, then the mark of its check):
                if field in _example_topics:
                    self._examples_button(grid,field).grid(row=r,column=col,padx=(2,0))
                    col += 1
                mark = ttk.Label(grid,width=2)
                mark.grid(row=r,column=col)
                col += 1
                self._entries[field], self._marks[field] = w, mark
                self._hover(lab,field)
                self._hover(w,field)
        #(writing the picked and edited particles, in the corner, which opens
        #a window with the name of the file and the code):
        self._write = ttk.Button(grid,text='Write modified MCPL file / code...',
                                 style='Head.TButton',takefocus=0,
                                 command=lambda : self.on_action('write'))
        self._write.grid(row=len(rows)-1,column=4,columnspan=6,sticky='e')
        self._hover(self._write,'write')
        _tint(part,'Particles')
        #(the line of messages, and at its right what is under the mouse):
        self._line = ttk.Label(bottom)
        self._line.grid(row=1,column=0,sticky='w',pady=(2,0))
        self._statusbar = ttk.Label(bottom,foreground=_colors['dim'])
        self._statusbar.grid(row=1,column=0,sticky='e',pady=(2,0))
        #(the window is at least as wide as the cards and the widest row of
        #the fields of the shown plot, so nothing is cut off):
        root.update_idletasks()
        root.minsize(left.winfo_reqwidth() + self._axes[0].master.winfo_reqwidth() + 40,600)
        self._popup = None#(the list of completions: (field, start, Toplevel, Listbox))
        root.bind('<Key>',self._on_root_key)
        root.protocol('WM_DELETE_WINDOW',self.close_window)

    def _menu_field( self, parent, field ):
        """A field of _viewer_ui.menu_fields: its label and menu (at the left
        of the row parent). The menu shows the chosen value, and its list the
        values with their descriptions."""
        _, ttk = _tk()
        _, label, _key, kpos, _ = next( f for f in ui.fields if f[0] == field )
        choices = self.menu_choices(field)
        frame = ttk.Frame(parent)
        frame.pack(side='left',fill='x',expand=True,padx=(8,0))
        lab = ttk.Label(frame,text=label + ':',underline=kpos)
        lab.pack(side='left',padx=(0,4))
        values = [ f'{n}  \u2013  {d}' for n, d in choices ]
        w = ttk.Combobox(frame,state='readonly',values=values,style='Menu.TCombobox',width=8)
        w.configure(postcommand=lambda : self._widen_list(w,values))
        w.pack(side='left',fill='x',expand=True)
        w.bind('<<ComboboxSelected>>',lambda _e : self._on_menu(field,choices))
        self._entries[field] = w
        self._marks[field] = ttk.Label(frame)#(menus are not checked)
        self._hover(lab,field)
        self._hover(w,field)

    def _widen_list( self, w, values ):
        """The list of the menu w is made as wide as its values (when it
        opens), also beyond the menu"""
        import tkinter.font
        _, ttk = _tk()
        font = tkinter.font.nametofont('TkTextFont')
        extra = max( 0, max( font.measure(v) for v in values ) + 30 - w.winfo_width() )
        ttk.Style(self.root).configure('Menu.TCombobox',postoffset=( 0, 0, extra, 0 ))

    def _plot_part( self, part, head ):
        """The fields of the shown plot (or of a new plot): its title, its axes
        (with the quantities of _viewer_ui.quantities in their lists), its
        settings and its plot expression, with the buttons of plots in the
        header of the part (head)"""
        _, ttk = _tk()
        #(the buttons at the right of the header):
        b = ttk.Button(head,text='+  New plot',style='Head.Accent.TButton',takefocus=0,
                       command=self.on_new_plot)
        b.pack(side='right',padx=(6,0))
        self._hover(b,'new_plot')
        self._remove = ttk.Button(head,text='Remove plot',style='Head.TButton',takefocus=0,
                                  command=self.on_remove)
        self._remove.pack(side='right',padx=(6,0))
        self._code = ttk.Button(head,text='</>  Plot code',style='Head.TButton',takefocus=0,
                                command=lambda : _CodeWindow(self,'Code of the plot',
                                                             self.plot_code()))
        self._code.pack(side='right')
        #(the title, in the header):
        ttk.Label(head,text='Title:',style='Plot.TLabel').pack(side='left',padx=(16,4))
        t = ttk.Entry(head,width=32)
        t.pack(side='left')
        self._placeholders[t] = 'the name in the list of plots'
        t.bind('<Return>',lambda _e : self._on_title_enter(t))
        t.bind('<KP_Enter>',lambda _e : self._on_title_enter(t))
        t.bind('<Escape>',lambda _e : self._on_title_escape())
        t.bind('<FocusIn>',lambda _e : self._on_title_focus(t),'+')
        t.bind('<FocusOut>',lambda _e : self._on_entry_unfocus(t),'+')
        self._title = t
        #(the axes, where choosing a quantity of the list puts its expression,
        #and the plot expression, which changes the plot, or removes it when
        #emptied):
        frame = ttk.Frame(part)
        frame.pack(fill='x',pady=1)
        self._menu = [ f'{name}:  {plot.split(";")[0]}' for name, plot in ui.quantities ]
        self._axes = []
        for label in ( 'X axis:', 'Y axis:' ):
            ttk.Label(frame,text=label,**( _row_label if not self._axes else {} )).pack(
                side='left',padx=(0 if not self._axes else 10,4))
            w = ttk.Combobox(frame,width=22,values=self._menu if not self._axes else [ '' ] + self._menu)
            w.pack(side='left')
            w.bind('<<ComboboxSelected>>',lambda _e, w=w : self._on_axis_chosen(w))
            w.bind('<KeyRelease>',lambda e : None if e.keysym in ( 'Return', 'KP_Enter', 'Escape' )
                   else self.on_axes_edited(*self._axis_texts()))
            w.bind('<Return>',lambda _e : self._on_axes_enter())
            w.bind('<KP_Enter>',lambda _e : self._on_axes_enter())
            w.bind('<Escape>',lambda _e : self._on_title_escape())
            self._axes.append(w)
        #(an empty y axis says what it means):
        y = self._axes[1]
        self._placeholders[y] = 'none (1D histogram)'
        y.bind('<FocusIn>',lambda _e : self._set_text(y,self._text(y)),'+')
        y.bind('<FocusOut>',lambda _e : self._on_entry_unfocus(y),'+')
        self._marks['axes'] = ttk.Label(frame,width=2)
        self._marks['axes'].pack(side='left')
        ttk.Label(frame,text='Expression:').pack(side='left',padx=(10,4))
        w = ttk.Entry(frame,width=30)
        w.pack(side='left',fill='x',expand=True)
        self._examples_button(frame,'shown_plot').pack(side='left',padx=(2,0))
        mark = ttk.Label(frame,width=2)
        mark.pack(side='left')
        self._bind_entry(w,'shown_plot')
        self._entries['shown_plot'], self._marks['shown_plot'] = w, mark
        #(the settings):
        frame = ttk.Frame(part)
        frame.pack(fill='x',pady=1)
        ttk.Label(frame,text='Settings:',**_row_label).pack(side='left',padx=(0,4))
        self._controls = _Controls(frame,self.on_control,
                                   on_hint = lambda text : self.show_line(text,'dim'),
                                   style = 'Plot')
        self._controls.frame.pack(side='left',fill='x')

    def _axis_texts( self ):
        """The texts of the axes (empty while showing their placeholders)"""
        return [ self._text(a) for a in self._axes ]

    def _on_axis_chosen( self, w ):
        """A quantity was chosen from the list of an axis: its expression is
        shown, and the plot changed"""
        text = w.get()
        self._set_text(w,ui.quantities[self._menu.index(text)][1].split(';')[0]
                       if text in self._menu else text)
        self._on_axes_enter()

    def _on_axes_enter( self ):
        if self.on_axes(*self._axis_texts()):
            self.show_check('axes',None)
            self.canvas.get_tk_widget().focus_set()
        return 'break'

    #Implementation of WidgetViewer:

    def show_views( self, cards, current ):
        self._cards.show(cards,current)

    def show_status( self, first, second ):
        self._status[0].configure(text=first)
        self._status[1].configure(text=second)

    def show_field( self, field, text ):
        if field == 'plot':
            return#(no field, see focus_field)
        w = self._entries[field]
        if field in ui.menu_fields:
            w.set(text)
            return
        self._set_text(w,text)

    def show_plot_field( self, text, title, axes ):
        x, y = axes or ( None, None )
        for w, value in ( ( self._entries['shown_plot'], text ), ( self._title, title ),
                          ( self._axes[0], x ), ( self._axes[1], y ) ):
            if text is None:
                w.configure(state='normal')
                self._showing.discard(w)
                w.delete(0,'end')
                w.configure(state='disabled')
            elif str(w['state']) == 'disabled' or self.root.focus_get() is not w:
                #(not while it is edited):
                w.configure(state='normal')
                if self._text(w) != ( value or '' ) or ( not value and w not in self._showing ):
                    self._set_text(w,value or '')
        self._remove.configure(state='disabled' if text is None else 'normal')
        #(the fields are only shown for plots, so the overview gets more room):
        if text is None:
            self._plot_fields.pack_forget()
        elif not self._plot_fields.winfo_manager():
            self._plot_fields.pack(side='bottom',fill='x',before=self._plotbox)
        #(a new plot has no code yet):
        self._code.configure(state='disabled' if self._new_plot is not None else 'normal')

    def show_line( self, text, style ):
        self._line.configure(text=text,foreground=_colors.get(style,_colors['normal']))

    def show_title( self, filename ):
        self.root.title(f'MCPL viewer: {filename}')

    def _ask_open( self ):
        """Ask for another file to show (see on_open_file)"""
        import os
        from tkinter import filedialog
        chosen = filedialog.askopenfilename(parent=self.root,title='Open an MCPL file',
                                            initialdir=os.path.dirname(os.path.abspath(self.v.filename)),
                                            filetypes=[ ( 'MCPL files', '*.mcpl *.mcpl.gz' ),
                                                        ( 'All files', '*' ) ])
        if chosen:
            self.on_open_file(chosen)

    def show_enabled( self, action, enabled ):
        if action == 'write':
            self._write.state([ '!disabled' if enabled else 'disabled' ])
            return
        self._actions_menu.entryconfigure(self._actions[action],
                                          state='normal' if enabled else 'disabled')

    def show_controls( self, controls ):
        self._controls.show(controls)

    def show_check( self, field, ok ):
        if field == 'plot':
            return
        mark = self._marks[field]
        if ok is None:
            mark.configure(text='')
        else:
            mark.configure(text='\u2713' if ok else '\u2717',
                           foreground=_colors['ok' if ok else 'error'])

    def draw_plot( self ):
        self.canvas.draw_idle()

    def focus_field( self, field ):
        if field == 'x_axis':
            self._axes[0].focus_set()
            return
        w = self._entries[field]
        w.focus_set()
        if field in ui.menu_fields:
            w.event_generate('<Down>')#(opens the list of the menu)
        else:
            w.icursor('end')
            self.on_field_edited(field,self._text(w))

    def ask_file( self, action ):
        if action == 'write':
            _WriteWindow(self)
            return
        self._ask_file_name(action,lambda name : self.on_file(action,name))

    def _ask_file_name( self, action, then ):
        """Ask for the name of the file in a file dialog, and call then with it
        (None if cancelled)"""
        import os
        from tkinter import filedialog
        name = self.suggested_filename(action)
        title = 'Write the particles to' if action == 'write' else 'Save the viewer state in'
        chosen = filedialog.asksaveasfilename(parent=self.root,title=title,
                                              initialdir=os.path.dirname(os.path.abspath(name)),
                                              initialfile=os.path.basename(name),
                                              confirmoverwrite=False)
        then(chosen or None)

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

    def copy_text( self, text ):
        """Copy the text to the clipboard (for Ctrl+V) and to the primary
        selection (for the middle mouse button), both owned by the main window,
        so they stay after the window which copied is closed"""
        root = self.root
        root.clipboard_clear()
        root.clipboard_append(text)
        root.selection_handle(lambda offset, length : text[int(offset):int(offset)+int(length)],
                              selection='PRIMARY')
        root.selection_own(selection='PRIMARY')

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

    def _on_title_enter( self, w ):
        self.on_title(self._text(w))
        self.canvas.get_tk_widget().focus_set()
        return 'break'

    def _on_title_escape( self ):
        self.show_check('axes',None)
        self.canvas.get_tk_widget().focus_set()
        self.refresh(plot = False)
        return 'break'

    def _on_title_focus( self, w ):
        if w in self._showing:
            self._set_text(w,'')
        self.show_line('Enter: set the title (an empty title shows the expressions)'
                       '   Esc: cancel','dim')

    def _on_menu( self, field, choices ):
        i = self._entries[field].current()
        if i >= 0:
            self.on_field_apply(field,choices[i][0])
        self.canvas.get_tk_widget().focus_set()

    def _hover_text( self, name ):
        if name == 'write' and not self.v.changes_particles:
            return self.v.nothing_to_write
        return ui.shortcut_text(name)

    def _hover( self, widget, name ):
        """Show the shortcut of the field or action under the mouse"""
        widget.bind('<Enter>',lambda _e : self._statusbar.configure(text=self._hover_text(name)),'+')
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
        #(l and k change the log scales of the plot, or of the plot of the
        #overview under the mouse):
        if event.key.lower() in ui.scale_keys:
            self.on_scale_key(event.key,self.pane.view_at(event))
            return
        k = { 'up' : 'Up', 'down' : 'Down', 'enter' : 'Enter', 'escape' : 'Esc',
              'f1' : 'F1', 'delete' : 'Delete' }.get(event.key,event.key)
        for arrow, name in ( ( '+up', 'MoveUp' ), ( '+down', 'MoveDown' ) ):
            if k.endswith(arrow):
                k = name
        if k.startswith('shift+') and len(k) == 7:
            k = k[-1].upper()
        if len(k) == 1 or k in ( 'Up', 'Down', 'MoveUp', 'MoveDown', 'Enter', 'F1', 'Delete' ):
            self.on_key(k)

    def _on_mpl_motion( self, event ):
        self._inaxes = event.inaxes

    def _on_mpl_click( self, event ):
        self.canvas.get_tk_widget().focus_set()
        if not self.toolbar.mode:#(not while zooming or panning)
            self.on_click(event)

    #The text fields:

    def _examples_button( self, parent, field ):
        """The "?" button of a field, showing examples to use in it"""
        _, ttk = _tk()
        return ttk.Button(parent,text='?',width=2,takefocus=0,style='Small.TButton',
                          command=lambda : _Examples(self,_example_topics[field],
                                                     lambda e : self._use_example(field,e)))

    def _use_example( self, field, text ):
        """Put the example in the field, to be applied (or changed) there"""
        w = self._entries[field]
        w.focus_set()
        self._set_text(w,text)
        w.icursor('end')
        self.on_field_edited(field,text)

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

#The heights of the cards of _CardList, and its colours:
_card_heights = { 'card' : 64, 'small' : 30, 'header' : 26 }
#(the styles of the highlighted code, see _viewer_code.highlight):
_code_styles = { 'comment' : { 'foreground' : '#6a737d' },
                 'string' : { 'foreground' : '#067d17' },
                 'keyword' : { 'foreground' : '#0033b3' },
                 'number' : { 'foreground' : '#1750eb' },
                 'preprocessor' : { 'foreground' : '#9e5b00' },
                 'option' : { 'foreground' : '#871094' } }

_card_colors = { 'bg' : '#eef1f5', 'card' : '#ffffff', 'selected' : '#e2ebf6',
                 'border' : '#d5dbe3', 'accent' : '#2f5f8f', 'text' : '#1d2733',
                 'dim' : '#7a8594', 'badge' : '#dfe7f1' }
#(the parts below the plot: that of the shown plot in the colour of its
#selected card, and that of the particles):
_part_colors = { 'Plot' : _card_colors['selected'], 'Particles' : _card_colors['bg'] }

#(the labels at the start of the rows of the parts, in a column):
_row_label = { 'width' : 9, 'anchor' : 'e' }

def _part( parent, name, title, what, border ):
    """A part below the plot (with the colours of _part_colors[name]), with a
    header with its title and what it is for. Returns the frame for its
    contents (in a frame with the border, its master), and the frame of the
    header (e.g. for buttons at its right)."""
    tk, ttk = _tk()
    box = tk.Frame(parent,background=_part_colors[name],highlightthickness=1,
                   highlightbackground=border,highlightcolor=border)
    frame = ttk.Frame(box,style=f'{name}.TFrame',padding=(10,4,10,6))
    frame.pack(fill='both',expand=True)
    head = ttk.Frame(frame,style=f'{name}.TFrame')
    head.pack(fill='x',pady=(0,6))
    ttk.Label(head,text=f'{title.upper()}  \u00b7  {what}',
              style=f'{name}Head.TLabel').pack(side='left')
    return frame, head

def _tint( part, name ):
    """Give the frames and labels in the part (see _part) its colours (those
    with their own style keep it)"""
    _, ttk = _tk()
    for w in part.winfo_children():
        if isinstance(w,ttk.Frame) and not w.cget('style'):
            w.configure(style=f'{name}.TFrame')
            _tint(w,name)
        elif isinstance(w,ttk.Label) and not w.cget('style'):
            w.configure(style=f'{name}.TLabel')

def _elided( text, font, width ):
    """The text, shortened with ... at the end to fit the width (in pixels)
    with the font"""
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + '\u2026') > width:
        text = text[:-1]
    return text.rstrip() + '\u2026'

class _CardList:
    """The cards of the views (see WidgetViewer.cards and Card) on a canvas
    which can be scrolled: a small image of the plot, its name and badges, or
    a compact card with its name and status, under the headers of their
    groups (which can be folded), with the shown one selected. Cards are
    clicked to show them, dragged to move them (also into another group), and
    removed with their menu (right click), as far as they allow it."""
    width, thumb = 300, ( 84, 50 )

    def __init__( self, parent, viewer ):
        tk, ttk = _tk()
        self.tv = viewer
        frame = ttk.Frame(parent)
        frame.pack(fill='both',expand=True)
        self.canvas = tk.Canvas(frame,width=self.width+12,background=_card_colors['bg'],
                                highlightthickness=0)
        bar = ttk.Scrollbar(frame,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        self.folded = set()#(the groups which are folded)
        self._images = {}#PNG data -> PhotoImage (kept, as Tk needs them)
        self._shown = None#(what is drawn, to only draw it again when changed)
        self._slots = []#(top, bottom, kind, what): 'card' (the Card), 'header' (group) or 'add'
        self._drag = None#(the key of the card dragged, and where it started)
        c = self.canvas
        c.bind('<ButtonPress-1>',self._on_press)
        c.bind('<B1-Motion>',self._on_motion)
        c.bind('<ButtonRelease-1>',self._on_release)
        #(a menu of the card, with the right button, or Ctrl and a click on macOS):
        for button in ( '<Button-3>', '<Control-Button-1>' if c.tk.call('tk','windowingsystem') == 'aqua' else '<Button-2>' ):
            c.bind(button,self._on_menu)
        #(scrolling with the wheel, as given by Windows and macOS, or X11):
        c.bind('<MouseWheel>',lambda e : c.yview_scroll(-1 if e.delta > 0 else 1,'units'))
        c.bind('<Button-4>',lambda _e : c.yview_scroll(-1,'units'))
        c.bind('<Button-5>',lambda _e : c.yview_scroll(1,'units'))

    def _image( self, key ):
        tk, _ttk = _tk()
        import base64
        png = self.tv.thumbnail(key,*self.thumb)
        if png is None:
            return None
        if png not in self._images:
            if len(self._images) > 200:#(the images of plots shown before)
                self._images = { k : v for k, v in self._images.items() if k in self._used }
            self._images[png] = tk.PhotoImage(data=base64.b64encode(png))
        self._used.add(png)
        return self._images[png]

    def show( self, cards, current ):
        """Draw the cards (see WidgetViewer.cards), with the one of the shown
        view selected (if anything changed; current, the index of the shown
        view, is not needed, since the cards have the keys of the views)"""
        self._used = set()
        images = [ self._image(c.key) if c.image else None for c in cards ]
        current = self.tv.shown_key
        shown = ( tuple(cards), current, tuple(sorted(self.folded)),
                  tuple( id(i) for i in images ) )
        if shown == self._shown:
            return
        new_current = self._shown is None or self._shown[1] != current
        self._shown = shown
        c, col = self.canvas, _card_colors
        c.delete('all')
        self._slots = []
        y, group = 6, False#(False: before the first header)
        selected = None#(where the shown card is, if it is a new one)
        for card, img in zip(cards,images):
            if card.grouped and card.group != group:
                group = card.group
                self._header(y,group)
                y += _card_heights['header']
            shown = card.key == current
            if card.grouped and group in self.folded and not shown:
                continue
            h = _card_heights['small' if card.compact else 'card']
            self._card(y,h,card,img,shown)
            self._slots.append( ( y, y + h, 'card', card ) )
            if shown and new_current:
                selected = ( y, y + h )
            y += h + 6
        #(the card adding a plot):
        self._rect(4,y,self.width,y+34,12,outline=col['border'],dash=(3,3),fill='')
        c.create_text(self.width/2,y+17,text='+  New plot',fill=col['accent'],
                      font=self.tv._bold)
        self._slots.append( ( y, y + 34, 'add', None ) )
        y += 40
        c.configure(scrollregion=( 0, 0, self.width + 8, y ))
        if selected is not None:
            #(the selected card is scrolled into view):
            top, bottom = c.canvasy(0), c.canvasy(c.winfo_height())
            if selected[0] < top or selected[1] > bottom:
                c.yview_moveto(max( 0.0, ( selected[0] - 40 ) / y ))

    def _rect( self, x0, y0, x1, y1, r, **kw ):
        pts = [ x0+r, y0, x1-r, y0, x1, y0, x1, y0+r, x1, y1-r, x1, y1,
                x1-r, y1, x0+r, y1, x0, y1, x0, y1-r, x0, y0+r, x0, y0 ]
        return self.canvas.create_polygon(pts,smooth=True,**kw)

    def _header( self, y, group ):
        mark = '\u25b8' if group in self.folded else '\u25be'
        self.canvas.create_text(8,y+13,anchor='w',fill=_card_colors['dim'],
                                text=f'{mark}  {( group or "More plots" ).upper()}',
                                font=( self.tv._bold.cget('family'), 8, 'bold' ))
        self._slots.append( ( y, y + _card_heights['header'], 'header', group ) )

    def _card( self, y, h, card, img, selected ):
        c, col = self.canvas, _card_colors
        self._rect(4,y,self.width,y+h,12,fill=col['selected'] if selected else col['card'],
                   outline=col['accent'] if selected else col['border'],width=2 if selected else 1)
        if card.compact:
            c.create_text(16,y+h/2,anchor='w',fill=col['dim'],
                          text=f'{card.name}  \u00b7  {card.status}')
            return
        x = 14
        if img is not None:
            c.create_image(x,y+h/2,image=img,anchor='w')
        if card.problem:
            #(a plot which failed, e.g. with fields of the userdata which the
            #file does not have, with its problem):
            c.create_text(x+self.thumb[0]/2,y+h/2,text='\u2717',fill=_colors['error'],
                          font=( self.tv._bold.cget('family'), 22, 'bold' ))
        x += self.thumb[0] + 12
        c.create_text(x,y+20,anchor='w',fill=col['text'],font=self.tv._bold,
                      text=_elided(card.name,self.tv._bold,self.width-x-22))
        if card.problem:
            c.create_text(x,y+43,anchor='w',fill=_colors['error'],
                          font=( self.tv._bold.cget('family'), 8 ),
                          text=_elided(card.problem,self.tv._bold,self.width-x-22))
        for b in ( () if card.problem else card.badges ):
            w = 10 + 6.5 * len(b)
            self._rect(x,y+34,x+w,y+52,8,fill=col['badge'],outline='')
            c.create_text(x+w/2,y+43,text=b,fill=col['accent'],
                          font=( self.tv._bold.cget('family'), 8 ))
            x += w + 5
        if card.draggable:
            c.create_text(self.width-10,y+h/2,text='\u2807',fill=col['border'])#(drag handle)

    def _slot( self, event ):
        y = self.canvas.canvasy(event.y)
        return next( ( s for s in self._slots if s[0] <= y < s[1] + 6 ), None )

    def _on_menu( self, event ):
        """A menu for the card: show or remove it (as far as it allows it)"""
        tk, _ = _tk()
        s = self._slot(event)
        if s is None or s[2] != 'card' or not ( s[3].selectable or s[3].removable ):
            return
        card = s[3]
        menu = tk.Menu(self.canvas,tearoff=0)
        if card.selectable:
            menu.add_command(label='Show',command=lambda : self.tv.on_select_key(card.key))
        if card.removable:
            menu.add_command(label='Remove this card',command=lambda : self.tv.on_remove(card.key))
        menu.tk_popup(event.x_root,event.y_root)

    def _on_press( self, event ):
        s = self._slot(event)
        self._drag = None
        if s is not None and s[2] == 'card' and s[3].draggable:
            self._drag = ( s[3].key, event.y, False )

    def _on_motion( self, event ):
        if self._drag is not None and abs( event.y - self._drag[1] ) > 6:
            key, y0, _ = self._drag
            self._drag = ( key, y0, True )
            #(a line where the card would go):
            self.canvas.delete('drop')
            s = self._slot(event)
            if s is not None:
                self.canvas.create_line(4,s[0]-3,self.width,s[0]-3,fill=_card_colors['accent'],
                                        width=3,tags='drop')

    def _on_release( self, event ):
        drag, self._drag = self._drag, None
        self.canvas.delete('drop')
        s = self._slot(event)
        if drag is not None and drag[2]:
            if s is None:
                return
            if s[2] == 'card':
                index, group = self.tv.plot_index(s[3].key), s[3].group
            elif s[2] == 'header':
                #(at the start of the group: before its first plot):
                group = s[3]
                index = next( ( self.tv.plot_index(x[3].key) for x in self._slots
                                if x[2] == 'card' and x[0] > s[0] and x[3].draggable ),
                              self.tv.plot_index(None) )
            else:
                index, group = self.tv.plot_index(None), None
            self.tv.on_drop(drag[0],index,group)
            return
        if s is None:
            return
        if s[2] == 'header':
            self.folded ^= { s[3] }
            self.tv.refresh(plot = False)
        elif s[2] == 'card' and s[3].selectable:
            self.tv.on_select_key(s[3].key)
        elif s[2] == 'add':
            self.tv.on_new_plot()

class _Controls:
    """The settings of a plot (see WidgetViewer.plot_controls): a menu or a
    text field for each, in a row, which call on_change(option, shown text)
    when changed (with Enter, for the text fields). The row is made again
    when the kind of plot changes. The menu of split has a choice for writing
    an expression, which on_hint (if given) explains."""
    #(the choice of the menu of split for writing an expression in it):
    expression_choice = 'an expression...'

    def __init__( self, parent, on_change, on_hint = None, style = None ):
        _, ttk = _tk()
        #(the style of the labels and the frame, e.g. of a part, see _part):
        self._styles = { 'style' : f'{style}.TLabel' } if style else {}
        self.frame = ttk.Frame(parent,**( { 'style' : f'{style}.TFrame' } if style else {} ))
        self._on_change = on_change
        self._on_hint = on_hint
        self._kind = None
        self._widgets, self._used, self._greyed = {}, {}, set()

    def show( self, controls ):
        _, ttk = _tk()
        kind = controls[0] if controls else None
        if kind != self._kind:
            for w in self.frame.winfo_children():
                w.destroy()
            self._kind, self._widgets = kind, {}
            self._used = {}#entry -> its greyed text (what is used)
            self._greyed = set()#(the entries showing it)
            for i, ( name, label, choices, _, _ ) in enumerate( controls[1] if controls else () ):
                ttk.Label(self.frame,text=label,**self._styles).pack(side='left',
                                                                     padx=(0 if i == 0 else 10,3))
                if choices is not None:
                    #(split also takes an expression, the others only the choices):
                    if name == 'split':
                        choices = [ *choices, self.expression_choice ]
                    w = ttk.Combobox(self.frame,values=choices,width=14 if name == 'split' else 7,
                                     state='normal' if name == 'split' else 'readonly')
                    w.bind('<<ComboboxSelected>>',lambda _e, n=name, w=w : self._chosen(n,w))
                else:
                    w = ttk.Entry(self.frame,width=12 if 'range' in name else 7)
                    #(the greyed text is removed while it is edited):
                    w.bind('<FocusIn>',lambda _e, w=w : self._show_used(w,None),'+')
                    w.bind('<FocusOut>',lambda _e, w=w : self._show_used(w,self._used.get(w)),'+')
                if name == 'split' or choices is None:
                    w.bind('<Return>',lambda _e, n=name, w=w : self._on_change(n,self._text(w)))
                w.pack(side='left')
                self._widgets[name] = w
        if not controls:
            return
        focus = self.frame.focus_get()
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
            if w in self._greyed:
                w.delete(0,'end')
                w.configure(foreground=_colors['normal'])
                self._greyed.discard(w)
            return
        if not w.get():
            self._used[w] = used
            w.insert(0,used)
            w.configure(foreground=_colors['dim'])
            self._greyed.add(w)

    def _text( self, w ):
        """The text of the entry w (empty while it shows a greyed text)"""
        return '' if w in self._greyed else w.get()

    def _chosen( self, name, w ):
        if w.get() != self.expression_choice:
            self._on_change(name,w.get())
            return
        #(an expression is written in the field, and applied with Enter):
        w.set('')
        w.focus_set()
        if self._on_hint is not None:
            self._on_hint('Type what to split the plot by, e.g. x > 0cm or abs(pdgcode),'
                          ' and press Enter')

    def values( self ):
        """The shown texts of the settings, as (option, text)"""
        return [ ( n, w.get() ) for n, w in self._widgets.items() ]

_example_titles = { 'pick' : 'Examples of picks', 'edit' : 'Examples of edits',
                    'hist' : 'Examples of plot expressions' }
#(the topics of the examples of the fields, see _exprhelp.examples):
_example_topics = { 'pick' : 'pick', 'edit' : 'edit', 'shown_plot' : 'hist' }

class _Examples:
    """A window with examples of expressions (of _exprhelp.examples), with what
    they do, where clicking one calls on_choose with it"""
    def __init__( self, tv, topic, on_choose ):
        from ._exprhelp import examples
        tk, ttk = _tk()
        w = tk.Toplevel(tv.root)
        w.title(_example_titles[topic])
        w.transient(tv.root)
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        ttk.Label(f,text='Click an example to use it (and change it as needed). Help lists all'
                  ' fields, units and functions.',foreground=_colors['dim']).pack(anchor='w')
        text = tk.Text(f,width=84,height=min(30,3*len(examples[topic])),wrap='word',
                       relief='flat',background='white',padx=8,pady=6,cursor='arrow')
        text.pack(fill='both',expand=True,pady=(6,0))
        text.tag_configure('what',lmargin1=24,lmargin2=24,spacing3=6,foreground=_colors['dim'],
                           font='TkDefaultFont')
        text.tag_configure('expr',font='TkFixedFont',foreground=_card_colors['accent'])
        text.tag_configure('hover',underline=True)
        for i, ( expr, what ) in enumerate(examples[topic]):
            tag = f'example{i}'
            text.insert('end',expr,( 'expr', tag ))
            text.insert('end','\n')
            text.insert('end',what + '\n','what')
            text.tag_bind(tag,'<Button-1>',lambda _e, x=expr : ( on_choose(x), w.destroy() ))
            text.tag_bind(tag,'<Enter>',lambda _e, t=tag : text.tag_add('hover',f'{t}.first',f'{t}.last'))
            text.tag_bind(tag,'<Leave>',lambda _e : text.tag_remove('hover','1.0','end'))
        text.configure(state='disabled')
        ttk.Button(f,text='Close',command=w.destroy).pack(side='right',pady=(8,0))
        w.bind('<Escape>',lambda _e : w.destroy())

class _CodeWindow:
    """A window with the command of mcpltool, and tabs with the code (in
    Python, C++ and C) doing the same as the viewer (see Viewer.code), each
    with a button copying it, and optionally widgets above them (made by
    top(frame))"""
    max_width = 130#(characters)

    def __init__( self, tv, title, code, top = None ):
        from ._viewer_code import kinds
        tk, ttk = _tk()
        self.tv = tv
        w = self.window = tk.Toplevel(tv.root)
        w.title(title)
        w.transient(tv.root)
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        if top is not None:
            top(f)
        self._texts = {}
        def section( parent, key, label ):
            row = ttk.Frame(parent)
            row.pack(fill='x',pady=(8,2))
            if label:
                ttk.Label(row,text=label,font=tv._bold).pack(side='left')
            text = tk.Text(parent,font='TkFixedFont',wrap='none',width=90,height=1,
                           relief='flat',background='white',padx=6,pady=4)
            text.pack(fill='both',expand=True)
            for style, opts in _code_styles.items():
                text.tag_configure(style,**opts)
            #(a scroll bar for the longer lines, if any, see show):
            bar = ttk.Scrollbar(parent,orient='horizontal',command=text.xview)
            text.configure(xscrollcommand=bar.set)
            text._bar = bar
            ttk.Button(row,text='Copy',takefocus=0,
                       command=lambda : self._copy(text)).pack(side='right')
            self._texts[key] = text
        section(f,'command','Command line:')
        langs = [ ( k, label ) for k, label in kinds[1:] if k in code ]#(no C++ and C for plots)
        if len(langs) == 1:
            section(f,langs[0][0],f'{langs[0][1]}:')
        else:
            #(the languages as buttons in a row, which are hard to miss, and one
            #text with the code of the chosen language):
            row = ttk.Frame(f)
            row.pack(fill='x',pady=(10,0))
            ttk.Label(row,text='Code in:',font=tv._bold).pack(side='left',padx=(0,6))
            self._lang = tk.StringVar(value=langs[0][0])
            for key, label in langs:
                ttk.Radiobutton(row,text=label,value=key,variable=self._lang,
                                style='Choice.Toolbutton',command=self._show_lang).pack(side='left',padx=(0,4))
            page = ttk.Frame(f)
            page.pack(fill='both',expand=True)
            section(page,'code',None)
        self.show(code)
        ttk.Button(f,text='Close',command=w.destroy).pack(side='right',pady=(10,0))
        w.bind('<Escape>',lambda _e : w.destroy())

    def _show_lang( self ):
        self.show(self._code)

    def show( self, code ):
        from ._viewer_code import highlight
        self._code = code
        #(the kind of code in each text, with one text for the language chosen,
        #as high as the longest code of all languages):
        kinds = { k : ( self._lang.get() if k == 'code' else k ) for k in self._texts }
        height = max( v.count('\n') + 1 for k, v in code.items() if k != 'command' )
        for key, text in self._texts.items():
            value = code[kinds[key]]
            #(as wide as the longest line, up to a maximum):
            longest = max( len(line) for line in value.splitlines() )
            text.configure(state='normal',height=1 if key == 'command' else height,
                           width=min(max(longest+1,60),self.max_width))
            if longest + 1 > self.max_width:
                text._bar.pack(fill='x',after=text)
            else:
                text._bar.pack_forget()
            text.delete('1.0','end')
            text.insert('1.0',value)
            for start, end, style in highlight(value,kinds[key]):
                text.tag_add(style,f'1.0+{start}c',f'1.0+{end}c')
            text.configure(state='disabled')

    def _copy( self, text ):
        self.tv.copy_text(text.get('1.0','end-1c'))
        self.tv.show_line('Copied (paste with Ctrl+V or the middle mouse button)','normal')

class _WriteWindow:
    """The window for writing the picked and edited particles to a new file:
    its name, with the command and Python code doing the same"""
    def __init__( self, tv ):
        self.tv = tv
        self._code = _CodeWindow(tv,'Write file',tv.v.code(),top = self._top)
        self._name.focus_set()

    def _top( self, f ):
        _, ttk = _tk()
        ttk.Label(f,text='Write the picked and edited particles to a new file:',
                  font=self.tv._bold).pack(anchor='w')
        row = ttk.Frame(f)
        row.pack(fill='x',pady=(6,0))
        self._name = ttk.Entry(row,width=60)
        self._name.insert(0,self.tv.suggested_filename('write'))
        self._name.pack(side='left',fill='x',expand=True)
        self._name.bind('<KeyRelease>',lambda _e : self._changed())
        self._name.bind('<Return>',lambda _e : self._write())
        ttk.Button(row,text='Browse...',takefocus=0,
                   command=lambda : self.tv._ask_file_name('write',self._chosen)).pack(side='left',padx=(6,0))
        ttk.Button(row,text='Write now',style='Accent.TButton',
                   command=self._write).pack(side='left',padx=(6,0))
        ttk.Button(row,text='Write now and view it',
                   command=lambda : self._write(view = True)).pack(side='left',padx=(6,0))
        self._message = ttk.Label(f,foreground=_colors['error'])
        self._message.pack(anchor='w')

    def _chosen( self, name ):
        if name:
            self._name.delete(0,'end')
            self._name.insert(0,name)
            self._changed()

    def _changed( self ):
        self._code.show(self.tv.v.code(filename = self._name.get().strip() or None))

    def _write( self, view = False ):
        """Write the file (and show it in the viewer, if view is set)"""
        name = self._name.get().strip() or self.tv.suggested_filename('write')
        ok, msg = self.tv.v.try_write(name)
        if not ok:
            self._message.configure(text=msg)
            return
        self._code.window.destroy()
        #(the new file has the picked and edited particles, so only the plots
        #are kept):
        if not view or not self.tv.on_open_file(name,particles = False):
            self.tv.show_line(msg,'normal')

def _has_xft( root ):
    """Whether Tk uses Xft for its fonts, or None if not known: as Tk says
    (which Tk without Xft can not, as the default Tk of conda-forge), else
    whether the Xft library was loaded (on Linux)"""
    import pathlib
    import tkinter
    try:
        return str(root.tk.call('::tk::pkgconfig','get','fontsystem')) == 'xft'
    except tkinter.TclError:
        pass
    maps = pathlib.Path('/proc/self/maps')
    try:
        return 'libXft' in maps.read_text()
    except OSError:
        return None

def _check_fonts( root ):
    """Warn if the fonts are not antialiased, as with a Tk built without Xft on
    X11 (like the default Tk of conda-forge)"""
    if _has_xft(root) is False:
        from ._messages import _warning
        _warning('The fonts of the viewer are not smooth (antialiased), since the Tk'
                 ' library used by Python was built without Xft. In a conda'
                 ' environment, a Tk with Xft can be installed with:'
                 ' conda install -c conda-forge "tk=*=xft_*"')

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
