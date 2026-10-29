
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
menus and the cards of the views on the left, the shown plot (a matplotlib
figure, with the toolbar of matplotlib) with its fields on the right, and the
pick and edit below it (see _viewer_widgets for what happens when they are
used)."""

__all__ = []

from . import _viewer_ui as ui
from ._viewer_tkbase import (
    GreyText,
    bind_enter,
    bind_shortcut,
    command_keys,
    focus_of,
    mnemonics,
    on_paste,
    repaint_after_resize,
    shortcut_name,
    tk_modules,
    windowing_system,
)
from ._viewer_tkcards import CardList
from ._viewer_tkcontrols import Controls, OverviewControls, make_part, row_label, tint
from ._viewer_tkwindows import (
    AlignWindow,
    CodeWindow,
    Examples,
    HelpWindow,
    WriteWindow,
)
from ._viewer_ui import card_colors, colors, part_colors
from ._viewer_widgets import WindowFrontend, WindowLogic, run_with_ctrl_c

#Tk key names, as names of _viewer_ui (the others are characters):
_keymap = { 'Return' : 'Enter', 'KP_Enter' : 'Enter', 'Escape' : 'Esc', 'Delete' : 'Delete',
            'F1' : 'F1', 'Up' : 'Up', 'Down' : 'Down', 'Prior' : 'PageUp',
            'Next' : 'PageDown' }
#(Shift, Control, Alt, and the Windows or Command key, in Tk event states):
_modifiers = 0x1 | 0x4 | 0x8 | 0x40

#(Control, and Alt, or the Command key of macOS, where Option is 0x10, as
#the num lock of X11):
_shortcut_modifiers = 0x4 | 0x8

def _key_name( event ):
    """The name of the key of a Tk event, as in _viewer_ui, or None (also for
    characters typed with Control, Alt, Command or Option, which are not the
    keys of the viewer, e.g. Cmd+W)"""
    name = _keymap.get(event.keysym)
    if name in ( 'Up', 'Down' ) and event.state & _modifiers:
        return 'Move' + name
    if name is None and len(event.char) == 1 and event.char.isprintable():
        mods = _shortcut_modifiers
        if windowing_system(event.widget) == 'aqua':
            mods |= 0x10
        return None if event.state & mods else event.char
    return name

class TkViewer(WindowFrontend):
    """The viewer in the Tk window root"""
    def __init__( self, viewer, root ):
        tk, ttk = tk_modules()
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg,
            NavigationToolbar2Tk,
        )
        from matplotlib.figure import Figure
        #(the logic of the viewer, which this shows, and whose on_* methods
        #the widgets call):
        fig = Figure(figsize=(10,6),dpi=100)
        self.logic = WindowLogic(viewer,self,fig)
        self._tick_id = None#(the next call of _tick, see close_window)
        self.root = root
        root.title(f'MCPL viewer: {viewer.filename}')#(see show_title)
        #(1400x900, or less to fit on the screen, with room for the menu bars,
        #docks and task bars of the desktop):
        root.geometry(f'{min( 1400, root.winfo_screenwidth() - 40 )}'
                      f'x{min( 900, root.winfo_screenheight() - 120 )}')
        style = ttk.Style(root)
        system = self.system = windowing_system(root)
        #(text in dark grey on white, also in the dark mode of macOS, where the
        #default text colour is light):
        for option, value in ( ( 'foreground', card_colors['text'] ), ( 'background', 'white' ) ):
            for widget in ( 'Text', 'Listbox' ):
                root.option_add(f'*{widget}.{option}',value)
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
        #(the size of small texts, e.g. badges: 8 for the usual default size 10
        #of Linux, and more on macOS, where it is 13; negative sizes are in
        #pixels):
        size = int(bold.cget('size'))
        self.small = ( 1 if size > 0 else -1 ) * max( 7, round( 0.8 * abs(size) ) )
        self.small_font = ( bold.cget('family'), self.small )
        self.small_bold = ( *self.small_font, 'bold' )
        #(the parts of the window, see make_part):
        for name, bg in part_colors.items():
            style.configure(f'{name}.TFrame',background=bg)
            style.configure(f'{name}.TLabel',background=bg)
            style.configure(f'{name}Head.TLabel',background=bg,foreground=card_colors['accent'],
                            font=self.small_bold)
        root.columnconfigure(1,weight=1)
        root.rowconfigure(0,weight=1)
        #The logo and the views (on the left):
        left = ttk.Frame(root,padding=6)
        left.grid(row=0,column=0,rowspan=2,sticky='ns')
        from ._logo import _icon_base64, _logo_base64
        self._logo = tk.PhotoImage(data=_logo_base64).subsample(3)
        #(the icon of the windows, e.g. in the Dock and when switching
        #applications, also for the windows opened later):
        self._icons = [ tk.PhotoImage(data=_icon_base64[size]) for size in ( 256, 32 ) ]
        root.iconphoto(True,*self._icons)
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
        self._menu_keys = {}#(the keys opening the menus, see on_key)
        self._menu_key(button,menu,'m')
        menu.add_command(label='Open MCPL file...',underline=0,command=self._ask_open,
                         accelerator=shortcut_name('O',root))
        bind_shortcut(root,'O',self._ask_open)
        self._actions_menu = menu
        for action, label, keys, kpos in ui.actions:
            if action not in ( 'write', 'help' ):#(help has its own menu)
                menu.add_command(label=label,underline=kpos,accelerator=keys[0],
                                 command=lambda a=action : self.logic.on_action(a))
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
        #from the pick and edit, see ui.cache_menu):
        self._cache = ttk.Menubutton(main,takefocus=0,style='CacheAll.Compact.TMenubutton')
        self._cache.grid(row=0,column=0,sticky='e')
        #(the menu is kept, as the option of the button only has its name):
        self._cache_choices = tk.Menu(self._cache,tearoff=0,postcommand=self._cache_menu)
        self._cache['menu'] = self._cache_choices
        self._hover(self._cache,'cache')
        #(the part of the shown plot, tinted, with an outline in the colour of
        #the outline of its selected card: the plot with its toolbar, and its
        #fields below them, see _plot_part):
        bg = part_colors['Plot']
        part, head = make_part(main,'Plot','Plot','the shown plot',card_colors['accent'])
        part.master.grid(row=2,column=0,sticky='nsew')
        #(the fields at the bottom, packed first so the plot gets the rest):
        fields = ttk.Frame(part)
        fields.pack(side='bottom',fill='x')
        self._plot_fields = fields#(not shown for views which are not plots)
        #(the settings of overviews, shown instead of the fields, see
        #show_overview_controls):
        self._overview_controls = OverviewControls(part,self.logic.on_overview_control,'Plot')
        plot = tk.Frame(part,name='plotbox',background=bg)
        self._plotbox = plot
        plot.pack(fill='both',expand=True,pady=(0,4))
        #(the widgets of the toolbar get the colour when they are made, as
        #matplotlib draws its icons on their background):
        for option in ( 'background', 'highlightBackground', 'activeBackground' ):
            root.option_add(f'*plotbox*{option}',bg)
        self.canvas = FigureCanvasTkAgg(fig,master=plot)
        self.toolbar = NavigationToolbar2Tk(self.canvas,plot,pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side='bottom',fill='x')
        #(the plot fills the space left, so it asks for little):
        self.canvas.get_tk_widget().configure(width=400,height=300)
        self.canvas.get_tk_widget().pack(side='top',fill='both',expand=True)
        #(the help, above the cards):
        self._help_menu(self._top_row)
        self.canvas.mpl_connect('button_press_event',self._on_mpl_click)
        self.canvas.mpl_connect('key_press_event',self._on_mpl_key)
        self._applies = {}#field -> its Apply button (see show_pending)
        self._placeholders = {}#entry -> text shown in grey while it is empty
        self._grey = GreyText()#(of the entries showing their placeholder)
        self._plot_part(fields,head)
        tint(part,'Plot')
        #Below the plot: the part of the particles (for all plots), and the
        #line below it:
        bottom = ttk.Frame(root,padding=(0,4,6,6))
        bottom.grid(row=1,column=1,sticky='ew')
        bottom.columnconfigure(0,weight=1)
        part, head = make_part(bottom,'Particles','Pick & edit','globally filter or modify entire file',
                           card_colors['border'])
        #(the numbers of the particles used, at the right of the header):
        self._counts = ttk.Label(head,foreground=colors['dim'],style='Particles.TLabel')
        self._counts.pack(side='right')
        part.master.grid(row=0,column=0,sticky='ew',pady=(2,0))
        info = { f[0] : f for f in ui.fields }
        #(plots are added with "+ New plot", and groups are activated in the
        #list of plots; the expressions get the width of the rows):
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
                                **( row_label if first else {} ))
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
                    #(for the edit with the button of the align helper):
                    box = ttk.Frame(grid)
                    box.grid(row=r,column=col+1,padx=(2,0),sticky='w')
                    self._examples_button(box,field).pack(side='left')
                    if field == 'edit':
                        b = ttk.Button(box,text='Align...',takefocus=0,style='Small.TButton',
                                       command=lambda : AlignWindow(self))
                        b.pack(side='left',padx=(2,0))
                        self._hover(b,'align')
                    col += 2
                mark = ttk.Label(grid,width=2)
                mark.grid(row=r,column=col)
                col += 1
                self._entries[field], self._marks[field] = w, mark
                self._hover(lab,field)
                self._hover(w,field)
        #(the button writing the picked and edited particles, which opens a
        #window with the name of the file and the code):
        self._write = ttk.Button(grid,text='New MCPL file...',
                                 style='Head.Accent.TButton',takefocus=0,
                                 command=lambda : self.logic.on_action('write'))
        #(below skip and limit, from the start of the one to the end of the other):
        self._write.grid(row=len(rows)-1,column=cols['skip'],
                         columnspan=cols['limit']+2-cols['skip'],sticky='ew',padx=(12,0))
        self._hover(self._write,'write')
        tint(part,'Particles')
        #(the line of messages, and at its right what is under the mouse):
        self._line = ttk.Label(bottom)
        self._line.grid(row=1,column=0,sticky='w',pady=(2,0))
        self._statusbar = ttk.Label(bottom,foreground=colors['dim'])
        self._statusbar.grid(row=1,column=0,sticky='e',pady=(2,0))
        #(the window is at least as wide as the cards and the widest row of
        #the fields of the shown plot, so nothing is cut off, but fits on the
        #screen, as in the geometry above, where the fields get narrower):
        root.update_idletasks()
        root.minsize(min( left.winfo_reqwidth() + self._axes[0].master.winfo_reqwidth() + 40,
                          root.winfo_screenwidth() - 40 ),
                     min( 600, root.winfo_screenheight() - 120 ))
        self._popup = None#(the list of completions: (field, start, Toplevel, Listbox, choices))
        root.bind('<Key>',self._on_root_key)
        root.protocol('WM_DELETE_WINDOW',self.close_window)
        if self.system == 'aqua':
            root.configure(menu=self._menubar(root))
            #(Quit in the menu of the application, or Cmd-Q, as closing the window):
            root.createcommand('tk::mac::Quit',self.close_window)
        repaint_after_resize(root)

    def _help_menu( self, parent ):
        """The help menu (at the left of the row parent), with the topics of
        help_topics"""
        tk, ttk = tk_modules()
        button = ttk.Menubutton(parent,text='Help',takefocus=0,style='Compact.TMenubutton')
        button.pack(side='left',padx=(8,0))
        menu = tk.Menu(button,tearoff=0)
        button['menu'] = menu
        self._menu_key(button,menu,'h')
        self._add_help_topics(menu)
        self._help_choices = menu

    def _add_help_topics( self, menu ):
        topics = self.logic.help_topics()
        #(w for the viewer, as for mcpltool -w):
        for ( label, title, text ), pos in zip(topics,mnemonics([ t[0] for t in topics ],
                                                                { 'The viewer' : 'w' })):
            menu.add_command(label=label,underline=pos,
                             command=lambda t=title, x=text : self.show_text(t,x))

    def _menubar( self, root ):
        """The menu bar of the window with the menus of the viewer (only used
        on macOS, where the menu bar at the top of the screen otherwise has
        default menus, and elsewhere would repeat the menus in the window)"""
        tk, _ = tk_modules()
        bar = tk.Menu(root,tearoff=0)
        menu = tk.Menu(bar,tearoff=0)
        menu.add_command(label='Open MCPL file...',command=self._ask_open,
                         accelerator=shortcut_name('O',root))
        menu.add_command(label='New MCPL file...',command=lambda : self.logic.on_action('write'))
        for action, label, _keys, _kpos in ui.actions:
            #(Quit is in the menu of the application):
            if action not in ( 'write', 'help', 'quit' ):
                menu.add_command(label=label,command=lambda a=action : self.logic.on_action(a))
        bar.add_cascade(label='File',menu=menu)
        self._bar_file = menu
        #(the name help makes it the help menu of macOS, with its search field):
        menu = tk.Menu(bar,name='help',tearoff=0)
        self._add_help_topics(menu)
        bar.add_cascade(label='Help',menu=menu)
        return bar

    def _plot_part( self, part, head ):
        """The fields of the shown plot (or of a new plot): its title, its axes
        (with the quantities of _viewer_ui.quantities in their lists), its
        settings and its plot expression, with the buttons of plots in the
        header of the part (head)"""
        tk, ttk = tk_modules()
        #(the buttons at the right of the header):
        b = ttk.Button(head,text='+  New plot',style='Head.Accent.TButton',takefocus=0,
                       command=self.logic.on_new_plot)
        b.pack(side='right',padx=(6,0))
        self._hover(b,'new_plot')
        self._remove = ttk.Button(head,text='Remove plot',style='Head.TButton',takefocus=0,
                                  command=self.logic.on_remove)
        self._remove.pack(side='right',padx=(6,0))
        self._code = ttk.Button(head,text='</>  Plot code',style='Head.TButton',takefocus=0,
                                command=lambda : CodeWindow(self,'Code of the plot',
                                                             self.logic.plot_code()))
        self._code.pack(side='right')
        #(the title, in the header):
        ttk.Label(head,text='Title:',style='Plot.TLabel').pack(side='left',padx=(16,4))
        t = ttk.Entry(head,width=32)
        t.pack(side='left')
        self._placeholders[t] = 'the name in the list of plots'
        bind_enter(t,lambda : self._on_title_enter(t))
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
        self._menu = dict(ui.quantity_choices)#(the texts of the quantities -> expressions)
        self._axes = []
        for label in ( 'X axis:', 'Y axis:', 'Z axis:' ):
            ttk.Label(simple,text=label,**( row_label if not self._axes else {} )).pack(
                side='left',padx=(0 if not self._axes else 10,4))
            w = ttk.Combobox(simple,width=18,values=list(self._menu) if not self._axes else [ '', *self._menu ])
            w.pack(side='left')
            w.bind('<<ComboboxSelected>>',lambda _e, w=w : self._on_axis_chosen(w))
            w.bind('<KeyRelease>',lambda e, w=w : self._on_axis_key(w,e))
            on_paste(w,lambda : self.logic.on_axes_edited(*self._axis_texts()))
            bind_enter(w,lambda w=w : self._on_axes_enter(w))
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
        #(the Apply button of the axes, as Enter in their fields):
        b = ttk.Button(simple,text='Apply',width=5,takefocus=0,style='Small.TButton',
                       command=self._on_axes_enter)
        b.state([ 'disabled' ])
        b.pack(side='left',padx=(4,0))
        self._applies['axes'] = b
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
        ttk.Label(expr,text='Expression:',**row_label).pack(side='left',padx=(0,4))
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
        ttk.Label(frame,text='Settings:',**row_label).pack(side='left',padx=(0,4))
        self._controls = Controls(frame,self.logic.on_control,self.logic.on_control_edited,
                                   self._bind_written,style = 'Plot')
        self._controls.frame.pack(side='left',fill='x',expand=True)

    def _axis_texts( self ):
        """The texts of the axes (empty while showing their placeholders)"""
        return [ self._text(a) for a in self._axes ]

    def _on_axis_chosen( self, w ):
        """A quantity was chosen from the list of an axis: its expression is
        shown, and the plot changed"""
        text = w.get()
        self._set_text(w,self._menu.get(text,text))
        self._on_axes_enter()

    def _bind_written( self, w, name ):
        """The keys of the menu of a setting of plots in which an expression is
        written (see Controls): Tab completes it, with the list of completions
        as in the other fields, and it is checked while it is written"""
        w.bind('<KeyRelease>',lambda e : self._on_written_key(w,name,e))
        w.bind('<Tab>',lambda _e : self._on_entry_tab(w,name))
        bind_enter(w,lambda : self._on_written_enter(w,name))
        w.bind('<Escape>',lambda _e : self._on_written_escape())
        w.bind('<FocusOut>',lambda _e : self._close_popup(),'+')
        for key, delta in ( ( '<Up>', -1 ), ( '<Down>', 1 ) ):
            w.bind(key,lambda _e, d=delta : ( self._on_entry_updown(w,name,d)
                                              if self._popup is not None else None ))

    def _on_written_key( self, w, name, event ):
        if event.keysym in command_keys:
            return
        self._close_popup()
        self.logic.on_control_edited(name,w.get())

    def _on_written_enter( self, w, name ):
        if self._popup is not None:
            self._insert_choice(w)
            return 'break'
        self.canvas.get_tk_widget().focus_set()
        self.logic.on_control(name,w.get())
        return 'break'

    def _on_written_escape( self ):
        if self._popup is not None:
            self._close_popup()
            return 'break'
        self.canvas.get_tk_widget().focus_set()
        self.show_line('','dim')
        self.logic.refresh(plot = False)
        return 'break'

    def _on_axis_key( self, w, event ):
        if event.keysym in command_keys:
            return
        self._close_popup()
        self.logic.on_axes_edited(*self._axis_texts())

    def _on_axis_escape( self ):
        if self._popup is not None:
            self._close_popup()
            return 'break'
        return self._on_title_escape()

    def _on_axes_enter( self, w = None ):
        if self._popup is not None and w is not None:
            self._insert_choice(w)
            return 'break'
        if self.logic.on_axes(*self._axis_texts()):
            self.show_check('axes',None)
            self.canvas.get_tk_widget().focus_set()
        return 'break'

    def _menu_key( self, button, menu, key ):
        """The key (underlined in the label of the button) opens the menu
        (see on_key), and closes it again when it is open"""
        button.configure(underline=button.cget('text').lower().index(key))
        self._menu_keys[key] = button
        for k in ( key, key.upper() ):
            menu.bind(f'<KeyPress-{k}>',lambda _e : ( menu.tk.call('tk::MenuUnpost',str(menu)),
                                                     'break' )[1])

    def on_key( self, key ):
        #(m and h open the menu and the help menu, whose other keys are then
        #those of their underlined letters):
        if key.lower() in self._menu_keys:
            self._menu_keys[key.lower()].event_generate('<<Invoke>>')
            return
        self.logic.on_key(key)

    #Implementation of WindowFrontend:

    def show_views( self, cards ):
        self._cards.show(cards)

    def show_status( self, first, second ):
        #(the numbers of the particles used are shown with the pick and edit,
        #and on the button writing them):
        v = self.logic.v
        self._status[0].configure(text=v.file_text())
        self._status[1].configure(text=second)
        self._counts.configure(text=v.counts_text() or '')
        text, used = ui.cache_text(v.cache_info())
        self._cache.configure(text=text,style=f'Cache{"All" if used else "Cut"}.Compact.TMenubutton')

    def show_field( self, field, text ):
        if field == 'plot':
            return#(no field: plots are added with "+ New plot", see on_new_plot)
        if field == 'groups':
            return#(no field: the groups are activated in the list of plots)
        self._set_text(self._entries[field],text)
        self.show_pending(field,False)

    def show_plot_field( self, text, title, axes ):
        axes = axes or ( None, None, None )
        for w, value in ( ( self._entries['shown_plot'], text ), ( self._title, title ),
                          *zip(self._axes,axes) ):
            if text is None:
                w.configure(state='normal')
                self._grey.forget(w)
                w.delete(0,'end')
                w.configure(state='disabled')
            elif str(w['state']) == 'disabled' or focus_of(self.root) is not w:
                #(not while it is edited):
                w.configure(state='normal')
                if self._text(w) != ( value or '' ) or ( not value and not self._grey.showing(w) ):
                    self._set_text(w,value or '')
                if w is self._entries['shown_plot']:
                    self.show_pending('shown_plot',False)
        if focus_of(self.root) not in self._axes:
            self.show_pending('axes',False)#(the axes are those of the plot)
        #(only custom plots can be removed, or a new plot given up):
        removable = self.logic._new_plot is not None or ( text is not None and self.logic.v.is_custom(text) )
        self._remove.configure(state='normal' if removable else 'disabled')
        #(the fields are only shown for plots, so the overview gets more room):
        if text is None:
            self._plot_fields.pack_forget()
        elif not self._plot_fields.winfo_manager():
            self._plot_fields.pack(side='bottom',fill='x',before=self._plotbox)
        #(a new plot has no code yet):
        self._code.configure(state='disabled' if self.logic._new_plot is not None else 'normal')

    def show_line( self, text, style ):
        self._line.configure(text=text,foreground=colors.get(style,colors['normal']))

    def show_title( self, filename ):
        self.root.title(f'MCPL viewer: {filename}')

    def _ask_open( self ):
        """Ask for another file to show (see on_open_file)"""
        import os
        from tkinter import filedialog
        chosen = filedialog.askopenfilename(parent=self.root,title='Open an MCPL file',
                                            initialdir=os.path.dirname(os.path.abspath(self.logic.v.filename)),
                                            filetypes=[ ( 'MCPL files', '*.mcpl *.mcpl.gz' ),
                                                        ( 'All files', '*' ) ])
        if chosen:
            self.logic.on_open_file(chosen)

    def show_enabled( self, action, enabled ):
        assert action == 'write'#(the only action enabled or not)
        #(in blue only when there is something to write):
        self._write.state([ '!disabled' if enabled else 'disabled' ])
        if getattr(self,'_bar_file',None) is not None:#(the menu bar on macOS)
            self._bar_file.entryconfigure(1,state='normal' if enabled else 'disabled')
        n = self.logic.v.nused_text(compact = True)
        self._write.configure(style='Head.Accent.TButton' if enabled else 'Head.TButton',
                              text=( f'New MCPL file ({n} particles)...'
                                     if enabled and n is not None else 'New MCPL file...' ))

    def show_controls( self, controls ):
        self._controls.show(controls)

    def show_overview_controls( self, controls ):
        frame = self._overview_controls.frame
        if controls is None:
            frame.pack_forget()
            return
        if not frame.winfo_manager():
            frame.pack(side='bottom',fill='x',pady=(0,4),before=self._plotbox)
        self._overview_controls.show(controls)

    def show_check( self, field, ok ):
        if field in ( 'plot', 'groups' ):#(no fields, see show_field)
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
        for i, ( label, limit, used, fits ) in enumerate(ui.cache_menu(self.logic.v.cache_info())):
            if used:
                menu._used.set(str(i))
            #(marked also with a symbol for all or a part of the particles in
            #memory, as menus on macOS have no colours):
            mark = '' if limit is None else ( '\u25cf  ' if fits else '\u25d0  ' )
            menu.add_radiobutton(label=mark + label,
                                 value=str(i),variable=menu._used,
                                 foreground=colors['ok' if fits else 'error'],
                                 command=lambda x=limit : self.logic.on_cache_limit(x))
        #(the help about the cache, as in the help menu):
        menu.add_separator()
        menu.add_command(label='About caching',
                         command=lambda : self.show_text('Data caching',ui.cache_blocks))

    def show_colour_bar_menu( self, entries ):
        tk, _ttk = tk_modules()
        menu = tk.Menu(self.root,tearoff=0)
        #(the scale used is marked):
        menu._used = tk.StringVar(menu,value=next( ( s for _, u, s in entries if u ), '' ))
        for label, _used, shown in entries:
            menu.add_radiobutton(label=label,value=shown,variable=menu._used,
                                 command=lambda s=shown : self.logic.on_control('logz',s))
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
        if field == 'groups':
            self.show_line(ui.groups_hint,'normal')
            return
        w = self._entries[field]
        w.focus_set()
        w.icursor('end')
        self.logic.on_field_edited(field,self._text(w))

    def ask_file( self, action ):
        if action == 'write':
            WriteWindow(self)
            return
        self.ask_file_name(action,lambda name : self.logic.on_file(action,name))

    def ask_file_name( self, action, then ):
        """Ask for the name of the file in a file dialog, and call then with it
        (None if cancelled)"""
        import os
        from tkinter import filedialog
        name = self.logic.suggested_filename(action)
        title = 'Write the particles to' if action == 'write' else 'Save the viewer state in'
        chosen = filedialog.asksaveasfilename(parent=self.root,title=title,
                                              initialdir=os.path.dirname(os.path.abspath(name)),
                                              initialfile=os.path.basename(name),
                                              confirmoverwrite=False)
        then(chosen or None)

    def show_help( self ):
        self.show_text('Help',ui.help_blocks)

    def show_text( self, title, blocks ):
        HelpWindow(self,title,blocks)

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
        self.logic.on_close()
        #(the next call of _tick would come after the window is gone):
        if self._tick_id is not None:
            self.root.after_cancel(self._tick_id)
            self._tick_id = None
        try:
            self.root.destroy()
        except tk.TclError:#(already destroyed)
            pass

    #Events of Tk and matplotlib:

    def _tick( self ):
        """Calls the on_timer method of the logic every 0.2 s, until the
        viewer is closed"""
        self._tick_id = None
        self.logic.on_timer()
        if not self.logic.closed:
            self._tick_id = self.root.after(200,self._tick)

    def _on_title_enter( self, w ):
        self.logic.on_title(self._text(w))
        self.canvas.get_tk_widget().focus_set()
        return 'break'

    def _on_title_escape( self ):
        self.show_check('axes',None)
        self.canvas.get_tk_widget().focus_set()
        self.logic.refresh(plot = False)
        return 'break'

    def _on_title_focus( self, w ):
        if self._grey.showing(w):
            self._set_text(w,'')
        self.show_line('Enter: set the title (an empty title shows the expressions)'
                       '   Esc: cancel','dim')

    def _hover( self, widget, name ):
        """Show the shortcut of the field or action under the mouse"""
        widget.bind('<Enter>',lambda _e : self._statusbar.configure(text=self.logic.hover_text(name)),'+')
        widget.bind('<Leave>',lambda _e : self._statusbar.configure(text=''),'+')

    def _on_root_key( self, event ):
        """Keys outside the text fields (the keys in them are handled by
        _bind_entry, and those over the plot by _on_mpl_key)"""
        tk, ttk = tk_modules()
        w = event.widget
        k = _key_name(event)
        if isinstance(w,ttk.Combobox) and str(w.cget('state')) == 'readonly':
            #(menus take only Up, Down and Enter, and the characters are
            #keys of the viewer):
            if k is not None and len(k) == 1:
                self.on_key(k)
            return
        if isinstance(w,( ttk.Entry, ttk.Combobox, tk.Entry, tk.Text )) or w is self.canvas.get_tk_widget():
            return
        if k is not None:
            self.on_key(k)

    def _on_mpl_key( self, event ):
        if event.key is None:
            return
        #(l and k change the log scales of the plot, or of the plot of the
        #overview under the mouse):
        if event.key.lower() in ui.scale_keys:
            self.logic.on_scale_key(event.key,self.logic.pane.view_at(event))
            return
        from ._viewer_figure import key_name
        k = key_name(event.key)
        if len(k) == 1 or k in ( 'Up', 'Down', 'MoveUp', 'MoveDown', 'Enter', 'F1', 'Delete' ):
            self.on_key(k)

    def _on_mpl_click( self, event ):
        from ._viewer_figure import after_event
        self.canvas.get_tk_widget().focus_set()
        if not self.toolbar.mode:#(not while zooming or panning)
            after_event(self.canvas,self.logic.on_click,event)

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
        self.logic.on_field_edited(field,text)
        def focus():
            self.root.focus_force()
            w.focus_set()
            w.icursor('end')
        self.root.after_idle(focus)

    def _bind_entry( self, w, field ):
        w.bind('<KeyRelease>',lambda e : self._on_entry_key(w,field,e))
        on_paste(w,lambda : self.logic.on_field_edited(field,self._text(w)))
        bind_enter(w,lambda : self._on_entry_enter(w,field))
        w.bind('<Escape>',lambda _e : self._on_entry_escape(field))
        w.bind('<Up>',lambda _e : self._on_entry_updown(w,field,-1))
        w.bind('<Down>',lambda _e : self._on_entry_updown(w,field,1))
        w.bind('<Tab>',lambda _e : self._on_entry_tab(w,field))
        w.bind('<FocusIn>',lambda _e : self._on_entry_focus(w,field),'+')
        w.bind('<FocusOut>',lambda _e : self._on_field_unfocus(w,field),'+')

    def _text( self, w ):
        """The text of the entry (empty while it shows its placeholder)"""
        return self._grey.text(w)

    def _set_text( self, w, text ):
        """Set the text of the entry (or show its placeholder if it is empty and
        not edited)"""
        if not text and w in self._placeholders and focus_of(self.root) is not w:
            self._grey.show(w,self._placeholders[w])
        else:
            self._grey.set(w,text)

    def _on_entry_focus( self, w, field ):
        if self._grey.showing(w):
            self._set_text(w,'')
        self.logic.on_field_edited(field,self._text(w))

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
            new = focus_of(self.root)
            if new is not None and new is not w and new.winfo_toplevel() is self.root:
                self.logic.on_field_unfocused(field,text)
        self.root.after_idle(check)

    def _on_entry_key( self, w, field, event ):
        if event.keysym in command_keys:
            return
        self._close_popup()
        self.logic.on_field_edited(field,self._text(w))

    def _on_entry_enter( self, w, field ):
        if self._popup is not None:
            self._insert_choice(w)
            return 'break'
        if self.logic.on_field_apply(field,self._text(w)):
            self.canvas.get_tk_widget().focus_set()
        return 'break'

    def _on_entry_escape( self, field ):
        if self._popup is not None:
            self._close_popup()
            return 'break'
        self.logic.on_field_cancel(field)
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
        text = self.logic.on_history(field,delta)
        if text is not None:
            w.delete(0,'end')
            w.insert(0,text)
            self.logic.on_field_edited(field,text)
        return 'break'

    def _on_entry_tab( self, w, field ):
        if self._popup is not None:
            self._insert_choice(w)
            return 'break'
        if ( field in ui.completing_fields or field in ui.written_options
             or field in ( 'shown_plot', 'axis' ) ):
            text, cursor, choices, start = self.logic.on_complete(field,self._text(w),w.index('insert'))
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
            self.logic.on_axes_edited(*self._axis_texts())
        elif field in ui.written_options:
            self.logic.on_control_edited(field,w.get())
        else:
            self.logic.on_field_edited(field,self._text(w))

    def _open_popup( self, w, field, start, choices ):
        """The completions in a list below the field (Up and Down choose one,
        Enter or Tab inserts it, Esc closes the list)"""
        tk, _ttk = tk_modules()
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        if self.system == 'aqua':
            #(else it takes the focus from the field on macOS, which closes it):
            try:
                top.tk.call('::tk::unsupported::MacWindowStyle','style',top._w,'help',
                            'noActivates')
            except tk.TclError:
                pass
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
    tv.logic.start()
    tv._tick()
    try:
        run_with_ctrl_c(root.mainloop,tv.close_window)
    finally:
        tv.logic.on_close()
