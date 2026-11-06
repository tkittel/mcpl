
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

"""The windows opened by the viewer with Tk (see _viewer_tk): the help, the
examples of expressions, the code of the plots, and the writing of a new
file (the Composer of the edit is in _viewer_tkcompose)"""

__all__ = []

from . import _viewer_ui as ui
from ._viewer_tkbase import TextSearch, bind_enter, on_paste, tip, tk_modules
from ._viewer_ui import card_colors, code_styles, colors


def closed_by_escape( window, focus = None ):
    """The window (Toplevel) closes with Esc, and gets the keyboard focus (in
    the widget returned by the function focus, or else itself) when it is
    shown, so Esc and its other keys work at once (also on macOS)"""
    window.bind('<Escape>',lambda _e : window.destroy())
    give = lambda : ( focus() if focus else window ).focus_force()
    window.after_idle(give)
    #(and again when it is visible, which can be later, e.g. without a window
    #manager, where the focus can not be given before; but not when the focus
    #is already in it, as the visibility also changes when e.g. a list of
    #completions covers it):
    def visible( e ):
        f = window.focus_get()
        if e.widget is window and ( f is None or f.winfo_toplevel() is not window ):
            give()
    window.bind('<Visibility>',visible,'+')

class HelpWindow:
    """A window with the help (see help_topics), formatted from its blocks
    (see _helptext), which can be scrolled"""
    def __init__( self, tv, title, blocks ):
        tk, ttk = tk_modules()
        top = tk.Toplevel(tv.root)
        top.title(f'MCPL: {title}')
        frame = ttk.Frame(top)
        frame.pack(fill='both',expand=True)
        text = tk.Text(frame,width=90,height=40,wrap='word',padx=14,pady=10,
                       font='TkDefaultFont',relief='flat',spacing1=1,spacing3=1)
        bar = ttk.Scrollbar(frame,orient='vertical',command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        text.pack(side='left',fill='both',expand=True)
        _format_help(text,blocks)
        text.configure(state='disabled')
        #(as high as the text needs, up to 40 lines, when it has its width):
        top.update_idletasks()
        #(the height is in lines of the font, and the text has larger headings
        #and spacing, so its height in pixels is used):
        pixels = text.count('1.0','end','update','ypixels')
        pixels = pixels[-1] if isinstance(pixels,tuple) else pixels
        line = int(text.tk.call('font','metrics','TkDefaultFont','-linespace'))
        if pixels:
            text.configure(height=min( 40, -( -int(pixels) // line ) + 1 ))
        close = ttk.Button(top,text='Close',command=top.destroy)
        close.pack(pady=4)
        self.search = TextSearch(top,text,close)
        for key in ( '<KeyPress-q>', '<KeyPress-Q>' ):
            top.bind(key,lambda _e : top.destroy())
        closed_by_escape(top)

def _format_help( text, blocks ):
    """Insert the help blocks (see _helptext) in the Text widget, formatted:
    sections as headings, the names and keys in bold in a column, code in a
    fixed font, paragraphs flowing with the width of the window, and web
    addresses which open in a browser when clicked"""
    #(the fonts, from the default one, as (family, size, style); negative
    #sizes are in pixels):
    call = text.tk.call
    actual = dict(zip(*[ iter(call('font','actual','TkDefaultFont')) ] * 2))
    family, size = str(actual['-family']), int(actual['-size'])
    bold, heading = ( family, size, 'bold' ), ( family, round(1.25*size), 'bold' )
    code = 'TkFixedFont'
    #(the column of the descriptions of keys and examples):
    column = max( int(call('font','measure',bold,'Shift+Up, Shift+Down')),
                  int(call('font','measure',code,'x'*28)) ) + 30
    text.tag_configure('section',font=heading,spacing1=14,spacing3=4)
    text.tag_configure('subsection',font=bold,spacing1=10,spacing3=2)
    text.tag_configure('para',spacing1=6,spacing3=6)
    text.tag_configure('note',lmargin1=12,lmargin2=12,spacing3=6)
    text.tag_configure('bullet',lmargin1=12,lmargin2=26,spacing3=3)
    text.tag_configure('item',lmargin1=12,lmargin2=36,spacing1=3)
    text.tag_configure('row',lmargin1=12,lmargin2=column,tabs=(column,),spacing1=3)
    #(the descriptions of codes too wide for the column, on the next line):
    text.tag_configure('below',lmargin1=column,lmargin2=column)
    text.tag_configure('name',font=bold)
    text.tag_configure('code',font=code,foreground=card_colors['accent'])
    for kind, *args in blocks:
        if kind == 'gap':
            continue
        if kind in ( 'text', 'note' ):
            #(the line breaks of plain text are left out):
            for para in args[0].split('\n\n'):
                text.insert('end',' '.join(para.split('\n')) + '\n',
                            'para' if kind == 'text' else 'note')
        elif kind in ( 'section', 'subsection' ):
            text.insert('end',args[0] + '\n',kind)
        elif kind == 'bullet':
            text.insert('end','\u2022  ' + args[0] + '\n','bullet')
        elif kind == 'item':
            text.insert('end',args[0],( 'item', 'code' ),': ' + args[1] + '\n','item')
        elif kind == 'key':
            text.insert('end',args[0],( 'row', 'name' ),'\t' + args[1] + '\n','row')
        else:#(examples)
            for c, what in args[0]:
                if int(call('font','measure',code,c)) + 12 < column - 8:
                    text.insert('end',c,( 'row', 'code' ),'\t' + what + '\n','row')
                else:
                    text.insert('end',c + '\n',( 'row', 'code' ),what + '\n','below')
            text.insert('end','\n')
    _links(text)

def _links( text ):
    """Make the web addresses in the Text widget open in a browser when
    clicked"""
    import re
    import webbrowser
    text.tag_configure('link',foreground=card_colors['accent'],underline=True)
    text.tag_bind('link','<Enter>',lambda _e : text.configure(cursor='hand2'))
    text.tag_bind('link','<Leave>',lambda _e : text.configure(cursor=''))
    for i, line in enumerate(text.get('1.0','end').split('\n')):
        for m in re.finditer(r'https://[^\s]*[^\s.,)]',line):
            tag, url = f'link{i}_{m.start()}', m.group(0)
            for t in ( 'link', tag ):
                text.tag_add(t,f'{i+1}.{m.start()}',f'{i+1}.{m.end()}')
            text.tag_bind(tag,'<Button-1>',lambda _e, u=url : webbrowser.open(u))

class Examples:
    """A window with examples of expressions (of _exprhelp.examples), with what
    they do, where clicking one calls on_choose with it"""
    def __init__( self, tv, topic, on_choose ):
        from ._exprhelp import example_rows, examples
        tk, ttk = tk_modules()
        w = tk.Toplevel(tv.root)
        w.title(f'MCPL: {ui.example_titles[topic]}')
        w.transient(tv.root)
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        ttk.Label(f,text='Click an example to apply it (it can be changed afterwards), or see'
                  ' more details (all fields, units, and functions).',
                  foreground=colors['dim']).pack(anchor='w')
        #(with a scroll bar, as there are more examples than fit):
        box = ttk.Frame(f)
        box.pack(fill='both',expand=True,pady=(6,0))
        text = tk.Text(box,width=84,height=min(34,3*len(example_rows(topic))),wrap='word',
                       relief='flat',background='white',padx=8,pady=6,cursor='arrow')
        bar = ttk.Scrollbar(box,orient='vertical',command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        text.pack(side='left',fill='both',expand=True)
        text.tag_configure('what',lmargin1=24,lmargin2=24,spacing3=6,foreground=colors['dim'],
                           font='TkDefaultFont')
        text.tag_configure('expr',font='TkFixedFont',foreground=card_colors['accent'])
        text.tag_configure('hover',underline=True)
        text.tag_configure('title',font=tv.bold,spacing1=8,spacing3=2)
        text.tag_configure('note',foreground=colors['dim'],spacing3=4,font='TkDefaultFont')
        i = 0
        for title, note, group in examples[topic]:
            text.insert('end',title + '\n','title')
            if note:
                text.insert('end',note + '\n','note')
            for expr, what in group:
                i += 1
                self._example(text,w,i,expr,what,on_choose)
        text.configure(state='disabled')
        ttk.Button(f,text='Close',command=w.destroy).pack(side='right',pady=(8,0))
        #(the help of the expressions of the topic, as in the Help menu):
        title, blocks = next( ( t, b ) for _, t, b in tv.logic.help_topics()
                              if t == ui.help_titles[topic] )
        details = lambda : ( w.destroy(), tv.show_text(title,blocks) )
        b = ttk.Button(f,text='More details',underline=0,command=details)
        b.pack(side='right',padx=(0,6),pady=(8,0))
        tip(b,'details')
        for key in ( 'm', 'M' ):
            w.bind(f'<Key-{key}>',lambda _e : details())
        closed_by_escape(w)

    @staticmethod
    def _example( text, w, i, expr, what, on_choose ):
        """Insert the example (number i), which calls on_choose with it when
        clicked"""
        tag = f'example{i}'
        text.insert('end',expr,( 'expr', tag ))
        text.insert('end','\n')
        text.insert('end',what + '\n','what')
        text.tag_bind(tag,'<Button-1>',lambda _e : ( on_choose(expr), w.destroy() ))
        text.tag_bind(tag,'<Enter>',lambda _e : text.tag_add('hover',f'{tag}.first',f'{tag}.last'))
        text.tag_bind(tag,'<Leave>',lambda _e : text.tag_remove('hover','1.0','end'))

class CodeWindow:
    """A window with the command of mcpltool, and the code (in Python, C++, or
    C, in tabs) doing the same as the viewer (see Viewer.code),
    each with a button copying it, and optionally widgets above them (made
    by top(frame))"""
    max_width = 130#(characters)

    def __init__( self, tv, title, code, top = None ):
        from ._viewer_code import kinds
        tk, ttk = tk_modules()
        self.tv = tv
        w = self.window = tk.Toplevel(tv.root)
        w.title(f'MCPL: {title}')
        w.transient(tv.root)
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        if top is not None:
            top(f)
        self._texts = {}
        def section( parent, key, label, copy = 'Copy' ):
            row = ttk.Frame(parent)
            row.pack(fill='x',pady=(8,2))
            if label:
                ttk.Label(row,text=label,font=tv.bold).pack(side='left')
            text = tk.Text(parent,font='TkFixedFont',wrap='none',width=90,height=1,
                           relief='flat',background='white',padx=6,pady=4)
            text.pack(fill='both',expand=True)
            for style, opts in code_styles.items():
                text.tag_configure(style,**opts)
            #(a scroll bar for the longer lines, if any, see show):
            bar = ttk.Scrollbar(parent,orient='horizontal',command=text.xview)
            text.configure(xscrollcommand=bar.set)
            text._bar = bar
            b = ttk.Button(row,text=copy,takefocus=0,command=lambda : self._copy(text))
            b.pack(side='right')
            tip(b,'copy')
            self._texts[key] = text
        section(f,'command','Command line:')
        langs = [ ( k, label ) for k, label in kinds[1:] if k in code ]#(no C++ and C for plots)
        if len(langs) == 1:
            section(f,langs[0][0],f'{langs[0][1]}:')
        else:
            #(the languages as tabs, each with its code):
            ttk.Label(f,text='Code:',font=tv.bold).pack(anchor='w',pady=(12,4))
            self.tabs = ttk.Notebook(f)
            self.tabs.pack(fill='both',expand=True)
            for key, label in langs:
                page = ttk.Frame(self.tabs,padding=(0,0,0,4))
                section(page,key,None,f'Copy {label} code')
                self.tabs.add(page,text=label)
        self.show(code)
        ttk.Button(f,text='Close',command=w.destroy).pack(side='right',pady=(10,0))
        if top is None:#(else the widgets above choose the focus)
            closed_by_escape(w)

    def show( self, code ):
        from ._viewer_code import highlight
        #(the texts of the code, as high as the longest code of all languages):
        height = max( v.count('\n') + 1 for k, v in code.items() if k != 'command' )
        for key, text in self._texts.items():
            value = code[key]
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
            for start, end, style in highlight(value,key):
                text.tag_add(style,f'1.0+{start}c',f'1.0+{end}c')
            text.configure(state='disabled')

    def _copy( self, text ):
        self.tv.copy_text(text.get('1.0','end-1c'))
        how = { 'aqua' : 'Cmd+V', 'win32' : 'Ctrl+V' }.get(self.tv.system,
                                                           'Ctrl+V or the middle mouse button')
        self.tv.show_line(f'Copied (paste with {how})','normal')

class PlotCodeWindow:
    """The window with the command and the Python code of the shown plot (or
    of the plots of the overview), of all particles of the range, or of only
    those which the plots of the viewer use, which a check button chooses
    (checked and disabled when they use all, see Viewer.cache_info)"""
    def __init__( self, tv ):
        tk, _ = tk_modules()
        self.tv = tv
        fits = tv.logic.v.cache_info()['fits']
        self.exact = tk.BooleanVar(tv.root,value = fits)
        self._code = CodeWindow(tv,'Code of the plot',tv.logic.plot_code(),top = self._top)
        if fits:
            self.button.state(['disabled'])
        closed_by_escape(self._code.window)

    def _top( self, frame ):
        _, ttk = tk_modules()
        self.button = ttk.Checkbutton(frame,variable = self.exact,command = self._changed,
                                      text = 'Reproduce viewer plots exactly'
                                      ' (depends on viewer cache size)')
        self.button.pack(anchor='w')
        tip(self.button,'exact_code')

    def _changed( self ):
        self._code.show(self.tv.logic.plot_code(exact = self.exact.get()))

class WriteWindow:
    """The window for writing the edited particles to a new file:
    its name, with the command and the code (Python, C++, or C) doing the
    same"""
    def __init__( self, tv ):
        self.tv = tv
        self._code = CodeWindow(tv,'Write file',tv.logic.v.code(),top = self._top)
        closed_by_escape(self._code.window,lambda : self._name)

    def _top( self, f ):
        _, ttk = tk_modules()
        ttk.Label(f,text='Write the edited particles to a new file:',
                  font=self.tv.bold).pack(anchor='w')
        row = ttk.Frame(f)
        row.pack(fill='x',pady=(6,0))
        self._name = ttk.Entry(row,width=60)
        self._name.insert(0,self.tv.logic.suggested_filename('write'))
        self._name.pack(side='left',fill='x',expand=True)
        self._name.bind('<KeyRelease>',lambda _e : self._changed())
        on_paste(self._name,self._changed)
        bind_enter(self._name,self._write)
        b = ttk.Button(row,text='Browse...',takefocus=0,
                       command=lambda : self.tv.ask_file_name('write',self._chosen))
        b.pack(side='left',padx=(6,0))
        tip(b,'browse')
        self._buttons = [ ttk.Button(row,text='Write file',style='Accent.TButton',
                                     command=self._write),
                          ttk.Button(row,text='Write and open file',
                                     command=lambda : self._write(view = True)) ]
        for b in self._buttons:
            b.pack(side='left',padx=(6,0))
        tip(self._buttons[0],'write')
        tip(self._buttons[1],'write_open')
        self._writing = False
        self._confirmed = None#(the existing file which the file dialog asked to overwrite)
        self._message = ttk.Label(f,foreground=colors['error'])
        self._message.pack(anchor='w')

    def _chosen( self, name, confirmed ):
        if name:
            self._name.delete(0,'end')
            self._name.insert(0,name)
            self._confirmed = confirmed
            self._changed()

    def _changed( self ):
        self._code.show(self.tv.logic.v.code(filename = self._name.get().strip() or None))

    def _write( self, view = False ):
        """Write the file (and show it in the viewer, if view is set), in a
        thread, so the window is not frozen while writing (and compressing)
        large files"""
        from ._viewer_output import try_write_to
        from ._viewer_threads import Mailbox, start
        if self._writing:
            return
        name = self._name.get().strip() or self.tv.logic.suggested_filename('write')
        if not self.tv.logic.may_overwrite('write',name,self._confirmed):
            return
        self._writing = True
        for b in self._buttons:
            b.state(['disabled'])
        self._message.configure(text=f'Writing {name} ...',foreground=colors['normal'])
        mailbox = Mailbox()
        start(try_write_to,mailbox,*self.tv.logic.v.write_arguments(name,True))
        def check():
            if not mailbox.done:
                self.tv.root.after(100,check)
                return
            self._writing = False
            if self._code.window.winfo_exists():
                for b in self._buttons:
                    b.state(['!disabled'])
                self._message.configure(foreground=colors['error'])
            results = mailbox.take()
            self._written(name,view,*( results[0] if results else ( False, 'Writing failed' ) ))
        self.tv.root.after(100,check)

    def _written( self, name, view, ok, msg ):
        if not ok:
            if self._code.window.winfo_exists():
                self._message.configure(text=msg)
            else:
                self.tv.show_line(msg,'error')
            return
        if self._code.window.winfo_exists():
            self._code.window.destroy()
        #(the new file has the edited particles, so only the plots
        #are kept):
        if not view:
            self.tv.show_line(msg,'normal')
        else:
            self.tv.logic.on_open_file(name,particles = False)#(with its own message)

def use_example( tv, field, text ):
    """Put the example in the field of the viewer tv and apply it, or if it
    can not be applied, leave it there to be changed, with the keyboard focus
    in it (after the window of the examples is closed)"""
    w = tv._entries[field]
    tv._set_text(w,text)
    w.icursor('end')
    tv.logic.on_field_edited(field,text)
    if tv.logic.on_field_apply(field,text):
        return
    def focus():
        tv.root.focus_force()
        w.focus_set()
        w.icursor('end')
    tv.root.after_idle(focus)
