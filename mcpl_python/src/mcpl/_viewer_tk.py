
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
from ._viewer_tkbase import tk_modules
from ._viewer_tkcards import CardList
from ._viewer_tkwindows import CodeWindow, Examples, WriteWindow
from ._viewer_widgets import (
    WidgetViewer,
    card_colors,
    colors,
    part_colors,
    run_with_ctrl_c,
)

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
        tk, ttk = tk_modules()
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg,
            NavigationToolbar2Tk,
        )
        from matplotlib.figure import Figure
        self.root = root
        root.title(f'MCPL viewer: {viewer.filename}')#(see show_title)
        root.geometry('1400x900')
        style = ttk.Style(root)
        system = root.tk.call('tk','windowingsystem')
        if system in ( 'x11', 'aqua' ):
            #(the default theme of X11 looks dated, and the native theme of
            #macOS ignores the colours of the parts and buttons):
            style.theme_use('clam')
        if system == 'x11':
            _check_fonts(root)
        #(the button of new plots, in the colour of the selected card):
        accent = card_colors['accent']
        style.configure('Accent.TButton',foreground='white',background=accent,
                        bordercolor=accent)
        style.map('Accent.TButton',background=[ ( 'disabled', '#a9bdd2' ), ( 'active', '#3d74ab' ) ],
                  foreground=[ ( 'disabled', '#eef2f7' ) ])
        #(the other buttons light, in the colours of the cards, instead of the
        #grey of the clam theme; the native theme of Windows keeps its look):
        for name in ( 'TButton', 'TMenubutton' ):
            style.configure(name,background='#f7f9fc',bordercolor=card_colors['border'])
            style.map(name,background=[ ( 'active', '#e4ebf4' ) ])
        #(choices shown as a row of buttons, with the chosen one in the colour
        #of the selected card):
        style.configure('Choice.Toolbutton',relief='raised',borderwidth=1,padding=(8,3),
                        background='#e3e8ee')
        style.map('Choice.Toolbutton',background=[ ( 'selected', accent ), ( 'active', '#d0d8e2' ) ],
                  foreground=[ ( 'selected', 'white' ) ],relief=[ ( 'selected', 'sunken' ) ])
        #(the small buttons next to fields, as high as the fields):
        style.configure('Small.TButton',padding=(2,0))
        style.configure('Small.Accent.TButton',padding=(2,0))
        style.configure('Compact.TMenubutton',padding=(6,0))
        #(the cache button, green when the plots use all particles, else red):
        for name, color in ( ( 'CacheAll', colors['ok'] ), ( 'CacheCut', colors['error'] ) ):
            style.configure(f'{name}.Compact.TMenubutton',foreground=color)
        #(the compact buttons in the header of the part of the shown plot):
        for name in ( 'Head.TButton', 'Head.Accent.TButton' ):
            style.configure(name,padding=(8,0),width=-4)
        import tkinter.font
        bold = tkinter.font.nametofont('TkDefaultFont').copy()
        bold.configure(weight='bold')
        self.bold = bold
        #(the parts below the plot, see _part):
        for name, bg in part_colors.items():
            style.configure(f'{name}.TFrame',background=bg)
            style.configure(f'{name}.TLabel',background=bg)
            style.configure(f'{name}Head.TLabel',background=bg,foreground=card_colors['accent'],
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
        #has its button with the pick and edit; in a row with the help menu,
        #see _help_menu):
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
        self._cards = CardList(left,self)
        self._hover(self._cards.canvas,'views')
        #The status and the plot (on the right):
        main = ttk.Frame(root,padding=(0,6,6,0))
        main.grid(row=0,column=1,sticky='nsew')
        main.columnconfigure(0,weight=1)
        main.rowconfigure(2,weight=1)
        self._status = [ ttk.Label(main,font=bold), ttk.Label(main,foreground=colors['dim']) ]
        for i, label in enumerate(self._status):
            label.grid(row=i,column=0,sticky='w')
        #(the button of the cache at the right of the name of the file, away
        #from the pick and edit, see cache_menu):
        self._cache = ttk.Menubutton(main,takefocus=0,style='CacheAll.Compact.TMenubutton')
        self._cache.grid(row=0,column=0,sticky='e')
        #(the menu is kept, as the option of the button only has its name):
        self._cache_choices = tk.Menu(self._cache,tearoff=0,postcommand=self._cache_menu)
        self._cache['menu'] = self._cache_choices
        self._hover(self._cache,'cache')
        #(the part of the shown plot, in the colours of its selected card: the
        #plot with its toolbar, and its fields below them, see _plot_part):
        bg = part_colors['Plot']
        part, head = _part(main,'Plot','Plot','the shown plot',card_colors['accent'])
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
        #(the help, above the cards):
        self._help_menu(self._top_row)
        self.canvas.mpl_connect('button_press_event',self._on_mpl_click)
        self.canvas.mpl_connect('key_press_event',self._on_mpl_key)
        self.canvas.mpl_connect('motion_notify_event',self._on_mpl_motion)
        self._inaxes = None#(the axes under the mouse)
        self._applies = {}#field -> its Apply button (see show_pending)
        self._placeholders = {}#entry -> text shown in grey while it is empty
        self._showing = set()#(the entries showing their placeholder)
        self._plot_part(fields,head)
        _tint(part,'Plot')
        #Below the plot: the part of the particles (for all plots), and the
        #line below it:
        bottom = ttk.Frame(root,padding=(0,4,6,6))
        bottom.grid(row=1,column=1,sticky='ew')
        bottom.columnconfigure(0,weight=1)
        part, head = _part(bottom,'Particles','Pick & edit','filter or modify particles',
                           card_colors['border'])
        #(the numbers of the particles used, at the right of the header):
        self._counts = ttk.Label(head,foreground=colors['dim'],style='Particles.TLabel')
        self._counts.pack(side='right')
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
        cols = {}#field -> column of its label
        for r, row in enumerate(rows):
            col = 0
            for field in row:
                cols[field] = col
                _, label, _key, kpos, empty = info[field]
                first = field == row[0]
                lab = ttk.Label(grid,text=label + ':',underline=kpos,
                                **( _row_label if first else {} ))
                lab.grid(row=r,column=col,sticky='e',padx=(0 if first else 12,4),pady=1)
                wide = field in ui.example_topics
                w = ttk.Entry(grid,width=20 if wide else 10)
                w.grid(row=r,column=col+1,sticky='ew' if wide else 'w')
                self._placeholders[w] = empty
                self._bind_entry(w,field)
                col += 2
                #(the Apply button and the examples right after the field, then
                #the mark of its check):
                if field in ui.example_topics:
                    self._apply_button(grid,field).grid(row=r,column=col,padx=(2,0))
                    self._examples_button(grid,field).grid(row=r,column=col+1,padx=(2,0))
                    col += 2
                mark = ttk.Label(grid,width=2)
                mark.grid(row=r,column=col)
                col += 1
                self._entries[field], self._marks[field] = w, mark
                self._hover(lab,field)
                self._hover(w,field)
        #(writing the picked and edited particles, in the corner, which opens
        #a window with the name of the file and the code):
        self._write = ttk.Button(grid,text='Create new MCPL file...',
                                 style='Head.Accent.TButton',takefocus=0,
                                 command=lambda : self.on_action('write'))
        #(below skip and limit, from the start of the one to the end of the other):
        self._write.grid(row=len(rows)-1,column=cols['skip'],
                         columnspan=cols['limit']+2-cols['skip'],sticky='ew',padx=(12,0))
        self._hover(self._write,'write')
        _tint(part,'Particles')
        #(the line of messages, and at its right what is under the mouse):
        self._line = ttk.Label(bottom)
        self._line.grid(row=1,column=0,sticky='w',pady=(2,0))
        self._statusbar = ttk.Label(bottom,foreground=colors['dim'])
        self._statusbar.grid(row=1,column=0,sticky='e',pady=(2,0))
        #(the window is at least as wide as the cards and the widest row of
        #the fields of the shown plot, so nothing is cut off):
        root.update_idletasks()
        root.minsize(left.winfo_reqwidth() + self._axes[0].master.winfo_reqwidth() + 40,600)
        self._popup = None#(the list of completions: (field, start, Toplevel, Listbox))
        root.bind('<Key>',self._on_root_key)
        root.protocol('WM_DELETE_WINDOW',self.close_window)

    def _help_menu( self, parent ):
        """The help menu (at the left of the row parent), with the topics of
        help_topics"""
        tk, ttk = tk_modules()
        button = ttk.Menubutton(parent,text='Help',takefocus=0,style='Compact.TMenubutton')
        button.pack(side='left',padx=(8,0))
        menu = tk.Menu(button,tearoff=0)
        button['menu'] = menu
        for label, title, text in self.help_topics():
            menu.add_command(label=label,command=lambda t=title, x=text : self.show_text(t,x))
        self._help_choices = menu

    def _plot_part( self, part, head ):
        """The fields of the shown plot (or of a new plot): its title, its axes
        (with the quantities of _viewer_ui.quantities in their lists), its
        settings and its plot expression, with the buttons of plots in the
        header of the part (head)"""
        tk, ttk = tk_modules()
        #(the buttons at the right of the header):
        b = ttk.Button(head,text='+  New plot',style='Head.Accent.TButton',takefocus=0,
                       command=self.on_new_plot)
        b.pack(side='right',padx=(6,0))
        self._hover(b,'new_plot')
        self._remove = ttk.Button(head,text='Remove plot',style='Head.TButton',takefocus=0,
                                  command=self.on_remove)
        self._remove.pack(side='right',padx=(6,0))
        self._code = ttk.Button(head,text='</>  Plot code',style='Head.TButton',takefocus=0,
                                command=lambda : CodeWindow(self,'Code of the plot',
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
        #(the axes, and the settings below them, are shown unless "Advanced"
        #shows the plot expression instead, which has them all):
        simple = ttk.Frame(frame)
        simple.pack(side='left')
        self._simple = simple
        self._menu = [ f'{name}:  {plot.split(";")[0]}' for name, plot in ui.quantities ]
        self._axes = []
        for label in ( 'X axis:', 'Y axis:', 'Z axis:' ):
            ttk.Label(simple,text=label,**( _row_label if not self._axes else {} )).pack(
                side='left',padx=(0 if not self._axes else 10,4))
            w = ttk.Combobox(simple,width=18,values=self._menu if not self._axes else [ '' ] + self._menu)
            w.pack(side='left')
            w.bind('<<ComboboxSelected>>',lambda _e, w=w : self._on_axis_chosen(w))
            w.bind('<KeyRelease>',lambda e, w=w : self._on_axis_key(w,e))
            w.bind('<Return>',lambda _e, w=w : self._on_axes_enter(w))
            w.bind('<KP_Enter>',lambda _e, w=w : self._on_axes_enter(w))
            w.bind('<Escape>',lambda _e : self._on_axis_escape())
            #(Tab completes the expressions, as in the other fields, and Up and
            #Down choose in the list of completions, if shown, else in the list
            #of quantities):
            w.bind('<Tab>',lambda _e, w=w : self._on_entry_tab(w,'axis'))
            for key, delta in ( ( '<Up>', -1 ), ( '<Down>', 1 ) ):
                w.bind(key,lambda _e, w=w, d=delta : ( self._on_entry_updown(w,'axis',d)
                                                       if self._popup is not None else None ))
            self._axes.append(w)
        #(empty y and z axes say what they mean):
        for w, empty in zip(self._axes[1:],( 'none (1D histogram)', 'none (no 3D plot)' )):
            self._placeholders[w] = empty
            w.bind('<FocusIn>',lambda _e, w=w : self._set_text(w,self._text(w)),'+')
            w.bind('<FocusOut>',lambda _e, w=w : self._on_entry_unfocus(w),'+')
        self._marks['axes'] = ttk.Label(simple,width=2)
        self._marks['axes'].pack(side='left')
        #(the plot expression, which has the axes and the settings, shown
        #instead of them with the toggle "Advanced", see _show_advanced):
        self._advanced = tk.BooleanVar(frame,value=False)
        toggle = ttk.Checkbutton(frame,text='Advanced',variable=self._advanced,takefocus=0,
                                 style='Choice.Toolbutton',command=self._show_advanced)
        toggle.pack(side='right',padx=(6,0))
        self._toggle = toggle
        self._hover(toggle,'advanced')
        expr = ttk.Frame(frame)
        self._expression = expr
        ttk.Label(expr,text='Expression:',**_row_label).pack(side='left',padx=(0,4))
        w = ttk.Entry(expr,width=16)
        w.pack(side='left',fill='x',expand=True)
        self._apply_button(expr,'shown_plot').pack(side='left',padx=(2,0))
        self._examples_button(expr,'shown_plot').pack(side='left',padx=(2,0))
        mark = ttk.Label(expr,width=2)
        mark.pack(side='left')
        self._bind_entry(w,'shown_plot')
        self._entries['shown_plot'], self._marks['shown_plot'] = w, mark
        #(the settings):
        self._plot_row = frame
        frame = ttk.Frame(part)
        frame.pack(fill='x',pady=1)
        self._settings_row = frame
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

    def _on_axis_key( self, w, event ):
        if event.keysym in ( 'Return', 'KP_Enter', 'Escape', 'Up', 'Down', 'Tab' ):
            return
        self._close_popup()
        self.on_axes_edited(*self._axis_texts())

    def _on_axis_escape( self ):
        if self._popup is not None:
            self._close_popup()
            return 'break'
        return self._on_title_escape()

    def _on_axes_enter( self, w = None ):
        if self._popup is not None and w is not None:
            self._insert_choice(w)
            return 'break'
        if self.on_axes(*self._axis_texts()):
            self.show_check('axes',None)
            self.canvas.get_tk_widget().focus_set()
        return 'break'

    #Implementation of WidgetViewer:

    def show_views( self, cards, current ):
        self._cards.show(cards,current)

    def show_status( self, first, second ):
        #(the numbers of the particles used are shown with the pick and edit,
        #and on the button writing them):
        v = self.v
        self._status[0].configure(text=v.file_text())
        self._status[1].configure(text=second)
        self._counts.configure(text=v.counts_text() or '')
        text, used = ui.cache_text(v.cache_info())
        self._cache.configure(text=text,style=f'Cache{"All" if used else "Cut"}.Compact.TMenubutton')

    def show_field( self, field, text ):
        if field == 'plot':
            return#(no field, see focus_field)
        if field == 'collection':
            return#(the groups are shown with the cards)
        self._set_text(self._entries[field],text)
        self.show_pending(field,False)

    def show_plot_field( self, text, title, axes ):
        axes = axes or ( None, None, None )
        for w, value in ( ( self._entries['shown_plot'], text ), ( self._title, title ),
                          *zip(self._axes,axes) ):
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
                if w is self._entries['shown_plot']:
                    self.show_pending('shown_plot',False)
        self._remove.configure(state='disabled' if text is None else 'normal')
        #(the fields are only shown for plots, so the overview gets more room):
        if text is None:
            self._plot_fields.pack_forget()
        elif not self._plot_fields.winfo_manager():
            self._plot_fields.pack(side='bottom',fill='x',before=self._plotbox)
        #(a new plot has no code yet):
        self._code.configure(state='disabled' if self._new_plot is not None else 'normal')

    def show_line( self, text, style ):
        self._line.configure(text=text,foreground=colors.get(style,colors['normal']))

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
            #(in blue only when there is something to write):
            self._write.state([ '!disabled' if enabled else 'disabled' ])
            n = self.v.nused
            self._write.configure(style='Head.Accent.TButton' if enabled else 'Head.TButton',
                                  text=( f'Create new MCPL file with {ui.count_text(n,True)} particles...'
                                         if enabled and n is not None else 'Create new MCPL file...' ))
            return
        self._actions_menu.entryconfigure(self._actions[action],
                                          state='normal' if enabled else 'disabled')

    def show_controls( self, controls ):
        self._controls.show(controls)

    def show_check( self, field, ok ):
        if field in ( 'plot', 'collection' ):#(no marks)
            return
        mark = self._marks[field]
        if ok is None:
            mark.configure(text='')
        else:
            mark.configure(text='\u2713' if ok else '\u2717',
                           foreground=colors['ok' if ok else 'error'])

    def _cache_menu( self ):
        """Fill the menu of the cache button (see cache_menu), under its title"""
        menu = self._cache_choices
        menu.delete(0,'end')
        menu._used = tk_modules()[0].StringVar(menu,value='')
        menu.add_command(label=ui.cache_menu_title,state='disabled')
        menu.add_separator()
        for i, ( label, limit, used, fits ) in enumerate(ui.cache_menu(self.v.cache_info())):
            if used:
                menu._used.set(str(i))
            menu.add_radiobutton(label=label,value=str(i),variable=menu._used,
                                 foreground=colors['ok' if fits else 'error'],
                                 command=lambda x=limit : self.on_cache_limit(x))

    def show_colour_bar_menu( self, entries ):
        tk, _ttk = tk_modules()
        menu = tk.Menu(self.root,tearoff=0)
        #(the scale used is marked):
        menu._used = tk.StringVar(menu,value=next( ( s for _, u, s in entries if u ), '' ))
        for label, _used, shown in entries:
            menu.add_radiobutton(label=label,value=shown,variable=menu._used,
                                 command=lambda s=shown : self.on_control('logz',s))
        x, y = self.root.winfo_pointerxy()
        menu.tk_popup(x,y)

    def show_pending( self, field, pending ):
        b = self._applies.get(field)
        if b is not None:
            #(lit up, in the colour of the selected card, while there is
            #something to apply):
            b.configure(style='Small.Accent.TButton' if pending else 'Small.TButton')
            b.state([ '!disabled' if pending else 'disabled' ])

    def draw_plot( self ):
        self.canvas.draw_idle()

    def _show_advanced( self ):
        """Show the plot expression instead of the axes and the settings, which
        are the parts of it, or the other way around (see the toggle
        "Advanced")"""
        if self._advanced.get():
            self._simple.pack_forget()
            self._settings_row.pack_forget()
            self._expression.pack(side='left',fill='x',expand=True)
        else:
            self._expression.pack_forget()
            self._simple.pack(side='left',before=self._toggle)
            self._settings_row.pack(fill='x',pady=1,after=self._plot_row)

    def focus_field( self, field ):
        if field == 'x_axis':
            if self._advanced.get():#(the axes are not shown then)
                self._advanced.set(False)
                self._show_advanced()
            self._axes[0].focus_set()
            return
        if field == 'shown_plot' and not self._advanced.get():
            self._advanced.set(True)
            self._show_advanced()
        if field == 'collection':
            self.show_line('The groups of plots are in the list of plots: the inactive ones at'
                           ' the end are activated with a click','normal')
            return
        w = self._entries[field]
        w.focus_set()
        w.icursor('end')
        self.on_field_edited(field,self._text(w))

    def ask_file( self, action ):
        if action == 'write':
            WriteWindow(self)
            return
        self.ask_file_name(action,lambda name : self.on_file(action,name))

    def ask_file_name( self, action, then ):
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
        self.show_text('Help',ui.help_text)

    def show_text( self, title, content ):
        """A window with the text (of help, see help_topics), which can be
        scrolled"""
        tk, ttk = tk_modules()
        top = tk.Toplevel(self.root)
        top.title(f'MCPL viewer: {title}')
        frame = ttk.Frame(top)
        frame.pack(fill='both',expand=True)
        text = tk.Text(frame,width=82,height=40,font='TkFixedFont',wrap='word')
        bar = ttk.Scrollbar(frame,orient='vertical',command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        text.pack(side='left',fill='both',expand=True)
        text.insert('1.0',content)
        text.configure(state='disabled')
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
        tk, _ttk = tk_modules()
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
        tk, ttk = tk_modules()
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
        _, ttk = tk_modules()
        return ttk.Button(parent,text='?',width=2,takefocus=0,style='Small.TButton',
                          command=lambda : Examples(self,ui.example_topics[field],
                                                     lambda e : self._use_example(field,e)))

    def _apply_button( self, parent, field ):
        """The Apply button of a field, enabled while it has a text which is
        not applied (see show_pending)"""
        _, ttk = tk_modules()
        b = ttk.Button(parent,text='Apply',width=5,takefocus=0,style='Small.TButton',
                       command=lambda : self._on_entry_enter(self._entries[field],field))
        b.state([ 'disabled' ])
        self._applies[field] = b
        return b

    def _use_example( self, field, text ):
        """Put the example in the field, to be applied (or changed) there,
        with the keyboard focus in it (after the window of the examples is
        closed)"""
        w = self._entries[field]
        self._set_text(w,text)
        w.icursor('end')
        self.on_field_edited(field,text)
        def focus():
            self.root.focus_force()
            w.focus_set()
            w.icursor('end')
        self.root.after_idle(focus)

    def _bind_entry( self, w, field ):
        w.bind('<KeyRelease>',lambda e : self._on_entry_key(w,field,e))
        w.bind('<Return>',lambda _e : self._on_entry_enter(w,field))
        w.bind('<KP_Enter>',lambda _e : self._on_entry_enter(w,field))
        w.bind('<Escape>',lambda _e : self._on_entry_escape(field))
        w.bind('<Up>',lambda _e : self._on_entry_updown(w,field,-1))
        w.bind('<Down>',lambda _e : self._on_entry_updown(w,field,1))
        w.bind('<Tab>',lambda _e : self._on_entry_tab(w,field))
        w.bind('<FocusIn>',lambda _e : self._on_entry_focus(w,field),'+')
        w.bind('<FocusOut>',lambda _e : self._on_field_unfocus(w,field),'+')

    def _text( self, w ):
        """The text of the entry (empty while it shows its placeholder)"""
        return '' if w in self._showing else w.get()

    def _set_text( self, w, text ):
        """Set the text of the entry (or show its placeholder if it is empty and
        not edited)"""
        w.delete(0,'end')
        self._showing.discard(w)
        w.configure(foreground=colors['normal'])
        if not text and w in self._placeholders and self.root.focus_get() is not w:
            w.insert(0,self._placeholders[w])
            w.configure(foreground=colors['dim'])
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

    def _on_field_unfocus( self, w, field ):
        """The focus left the field: its text is applied if it moved to
        another part of the main window (not if the window lost the focus, or
        e.g. the window of the examples was opened)"""
        text = self._text(w)
        self._on_entry_unfocus(w)
        def check():
            new = self.root.focus_get()
            if new is not None and new is not w and new.winfo_toplevel() is self.root:
                self.on_field_unfocused(field,text)
        self.root.after_idle(check)

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
        if field in ui.completing_fields or field in ( 'shown_plot', 'axis' ):
            text, cursor, choices, start = self.on_complete(field,self._text(w),w.index('insert'))
            w.delete(0,'end')
            w.insert(0,text)
            w.icursor(cursor)
            if choices:
                self._open_popup(w,field,start,choices)
            self._edited(w,field)
        return 'break'

    def _edited( self, w, field ):
        """The text of the field (or of an axis) was changed"""
        if field == 'axis':
            self.on_axes_edited(*self._axis_texts())
        else:
            self.on_field_edited(field,self._text(w))

    def _open_popup( self, w, field, start, choices ):
        """The completions in a list below the field (Up and Down choose one,
        Enter or Tab inserts it, Esc closes the list)"""
        tk, _ttk = tk_modules()
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
        self._edited(w,field)

    def _close_popup( self ):
        if self._popup is not None:
            self._popup[2].destroy()
            self._popup = None

#(the labels at the start of the rows of the parts, in a column):
_row_label = { 'width' : 9, 'anchor' : 'e' }

def _part( parent, name, title, what, border ):
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

def _tint( part, name ):
    """Give the frames and labels in the part (see _part) its colours (those
    with their own style keep it)"""
    _, ttk = tk_modules()
    for w in part.winfo_children():
        if isinstance(w,ttk.Frame) and not w.cget('style'):
            w.configure(style=f'{name}.TFrame')
            _tint(w,name)
        elif isinstance(w,ttk.Label) and not w.cget('style'):
            w.configure(style=f'{name}.TLabel')

class _Controls:
    """The settings of a plot (see WidgetViewer.plot_controls): a menu or a
    text field for each, in a row, which call on_change(option, shown text)
    when changed (with Enter, for the text fields). The row is made again
    when the kind of plot changes. The menu of split has a choice for writing
    an expression, which on_hint (if given) explains."""
    #(the choice of the menu of split for writing an expression in it):
    expression_choice = 'an expression...'

    def __init__( self, parent, on_change, on_hint = None, style = None ):
        _, ttk = tk_modules()
        #(the style of the labels and the frame, e.g. of a part, see _part):
        self._styles = { 'style' : f'{style}.TLabel' } if style else {}
        self.frame = ttk.Frame(parent,**( { 'style' : f'{style}.TFrame' } if style else {} ))
        self._on_change = on_change
        self._on_hint = on_hint
        self._kind = None
        self._widgets, self._used, self._greyed = {}, {}, set()

    def show( self, controls ):
        _, ttk = tk_modules()
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
                w.configure(foreground=colors['normal'])
                self._greyed.discard(w)
            return
        if not w.get():
            self._used[w] = used
            w.insert(0,used)
            w.configure(foreground=colors['dim'])
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
        tk, _ttk = tk_modules()
        import matplotlib.backends.backend_tkagg  # noqa: F401
    except ImportError:
        return None
    try:
        return tk.Tk()
    except tk.TclError:
        return None

def run_viewer( viewer, root ):
    """Run the viewer in the Tk window root (from _root) until it is closed"""
    tk, _ttk = tk_modules()
    if tk.TkVersion < 8.6:
        #(which can not show PNG images, e.g. the Tk of the Python of Apple's
        #command line tools):
        root.destroy()
        from ._common import MCPLError
        raise MCPLError(f'The viewer needs Tk 8.6 or later, but this Python has Tk {tk.TkVersion}'
                        ' (use a Python with a newer Tk, e.g. from conda-forge or python.org)')
    tv = TkViewer(viewer,root)
    tv.start()
    root.after(200,tv._tick)
    try:
        run_with_ctrl_c(root.mainloop,tv.close_window)
    finally:
        tv.on_close()
