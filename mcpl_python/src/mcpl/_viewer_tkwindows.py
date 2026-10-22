
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

"""The windows opened by the viewer with Tk (see _viewer_tk): the examples of
expressions, the code of the plots, and the writing of a new file"""

__all__ = []

from . import _viewer_ui as ui
from ._viewer_tkbase import tk_modules
from ._viewer_widgets import card_colors, code_styles, colors


class Examples:
    """A window with examples of expressions (of _exprhelp.examples), with what
    they do, where clicking one calls on_choose with it"""
    def __init__( self, tv, topic, on_choose ):
        from ._exprhelp import examples
        tk, ttk = tk_modules()
        w = tk.Toplevel(tv.root)
        w.title(ui.example_titles[topic])
        w.transient(tv.root)
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        ttk.Label(f,text='Click an example to use it (and change it as needed). Help lists all'
                  ' fields, units and functions.',foreground=colors['dim']).pack(anchor='w')
        text = tk.Text(f,width=84,height=min(30,3*len(examples[topic])),wrap='word',
                       relief='flat',background='white',padx=8,pady=6,cursor='arrow')
        text.pack(fill='both',expand=True,pady=(6,0))
        text.tag_configure('what',lmargin1=24,lmargin2=24,spacing3=6,foreground=colors['dim'],
                           font='TkDefaultFont')
        text.tag_configure('expr',font='TkFixedFont',foreground=card_colors['accent'])
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

class CodeWindow:
    """A window with the command of mcpltool, and tabs with the code (in
    Python, C++ and C) doing the same as the viewer (see Viewer.code), each
    with a button copying it, and optionally widgets above them (made by
    top(frame))"""
    max_width = 130#(characters)

    def __init__( self, tv, title, code, top = None ):
        from ._viewer_code import kinds
        tk, ttk = tk_modules()
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
            ttk.Label(row,text='Code in:',font=tv.bold).pack(side='left',padx=(0,6))
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

class WriteWindow:
    """The window for writing the picked and edited particles to a new file:
    its name, with the command and Python code doing the same"""
    def __init__( self, tv ):
        self.tv = tv
        self._code = CodeWindow(tv,'Write file',tv.v.code(),top = self._top)
        self._name.focus_set()

    def _top( self, f ):
        _, ttk = tk_modules()
        ttk.Label(f,text='Write the picked and edited particles to a new file:',
                  font=self.tv.bold).pack(anchor='w')
        row = ttk.Frame(f)
        row.pack(fill='x',pady=(6,0))
        self._name = ttk.Entry(row,width=60)
        self._name.insert(0,self.tv.suggested_filename('write'))
        self._name.pack(side='left',fill='x',expand=True)
        self._name.bind('<KeyRelease>',lambda _e : self._changed())
        self._name.bind('<Return>',lambda _e : self._write())
        ttk.Button(row,text='Browse...',takefocus=0,
                   command=lambda : self.tv.ask_file_name('write',self._chosen)).pack(side='left',padx=(6,0))
        ttk.Button(row,text='Write now',style='Accent.TButton',
                   command=self._write).pack(side='left',padx=(6,0))
        ttk.Button(row,text='Write now and view it',
                   command=lambda : self._write(view = True)).pack(side='left',padx=(6,0))
        self._message = ttk.Label(f,foreground=colors['error'])
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

class MemoryWindow:
    """The window with the memory used for the particles, when they do not
    fit in the memory of the viewer: all can be kept in memory, or a limit
    of the number of particles set (see WidgetViewer.memory_summary)"""
    def __init__( self, tv ):
        tk, ttk = tk_modules()
        self.tv = tv
        info = tv.v.memory_info()
        w = self.window = tk.Toplevel(tv.root)
        w.title('Memory')
        w.transient(tv.root)
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        ttk.Label(f,text=tv.memory_summary(),wraplength=520,justify='left').pack(anchor='w')
        def choice( text, command ):
            ttk.Button(f,text=text,command=lambda : ( command(), w.destroy() )).pack(
                anchor='w',fill='x',pady=(8,0))
        choice(f'Keep them all in memory ({tv.memory_choice("",note = False)})',
               tv.on_memory_keep_all)
        skip = tv.v._parse('skip',tv.v.field_text('skip'))
        if info['nfit'] > skip:
            fit = str(info['nfit'] - skip)
            choice(f'Use only the first {tv.memory_choice(fit)}',tv.on_memory_fit)
        #(another limit, with what it uses while it is typed):
        ttk.Label(f,text='Or use another limit of the number of particles:',
                  font=tv.bold).pack(anchor='w',pady=(12,0))
        row = ttk.Frame(f)
        row.pack(fill='x',pady=(4,0))
        self._limit = ttk.Entry(row,width=14)
        self._limit.insert(0,tv.v.field_text('limit') or '')
        self._limit.pack(side='left')
        self._what = ttk.Label(row,foreground=colors['dim'])
        self._what.pack(side='left',padx=(8,0))
        ttk.Button(f,text='Use this limit',command=self._use).pack(anchor='w',pady=(6,0))
        self._limit.bind('<KeyRelease>',lambda _e : self._show())
        self._limit.bind('<Return>',lambda _e : self._use())
        ttk.Button(f,text='Close',command=w.destroy).pack(side='right',pady=(12,0))
        w.bind('<Escape>',lambda _e : w.destroy())
        self._show()
        self._limit.focus_set()

    def _show( self ):
        self._what.configure(text=self.tv.memory_choice(self._limit.get()))

    def _use( self ):
        if self.tv.on_field_apply('limit',self._limit.get()):
            self.window.destroy()
