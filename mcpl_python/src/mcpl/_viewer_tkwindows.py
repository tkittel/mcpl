
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
file"""

__all__ = []

from . import _viewer_ui as ui
from ._viewer_tkbase import bind_enter, on_paste, tk_modules
from ._common import MCPLError
from ._viewer_ui import card_colors, code_styles, colors


class HelpWindow:
    """A window with the help (see help_topics), formatted from its blocks
    (see _helptext), which can be scrolled"""
    def __init__( self, tv, title, blocks ):
        tk, ttk = tk_modules()
        top = tk.Toplevel(tv.root)
        top.title(f'MCPL viewer: {title}')
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
        ttk.Button(top,text='Close',command=top.destroy).pack(pady=4)
        for key in ( '<Escape>', '<KeyPress-q>', '<KeyPress-Q>' ):
            top.bind(key,lambda _e : top.destroy())
        #(when it is shown, so it gets the keys also on macOS):
        top.after_idle(top.focus_force)

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
        w.title(ui.example_titles[topic])
        w.transient(tv.root)
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        ttk.Label(f,text='Click an example to use it (and change it as needed). Help lists all'
                  ' fields, units and functions.',foreground=colors['dim']).pack(anchor='w')
        text = tk.Text(f,width=84,height=min(34,3*len(example_rows(topic))),wrap='word',
                       relief='flat',background='white',padx=8,pady=6,cursor='arrow')
        text.pack(fill='both',expand=True,pady=(6,0))
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
        w.bind('<Escape>',lambda _e : w.destroy())

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
    """A window with the command of mcpltool, and the code (in Python, C++ or
    C, chosen with buttons) doing the same as the viewer (see Viewer.code),
    each with a button copying it, and optionally widgets above them (made
    by top(frame))"""
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
        how = { 'aqua' : 'Cmd+V', 'win32' : 'Ctrl+V' }.get(self.tv.system,
                                                           'Ctrl+V or the middle mouse button')
        self.tv.show_line(f'Copied (paste with {how})','normal')

class WriteWindow:
    """The window for writing the picked and edited particles to a new file:
    its name, with the command and the code (Python, C++ or C) doing the
    same"""
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
        on_paste(self._name,self._changed)
        bind_enter(self._name,self._write)
        ttk.Button(row,text='Browse...',takefocus=0,
                   command=lambda : self.tv.ask_file_name('write',self._chosen)).pack(side='left',padx=(6,0))
        self._buttons = [ ttk.Button(row,text='Write now',style='Accent.TButton',
                                     command=self._write),
                          ttk.Button(row,text='Write now and view it',
                                     command=lambda : self._write(view = True)) ]
        for b in self._buttons:
            b.pack(side='left',padx=(6,0))
        self._writing = False
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
        """Write the file (and show it in the viewer, if view is set), in a
        thread, so the window is not frozen while writing (and compressing)
        large files"""
        import threading
        if self._writing:
            return
        name = self._name.get().strip() or self.tv.suggested_filename('write')
        result = []
        thread = threading.Thread(target = lambda : result.append(self.tv.v.try_write(name)),
                                  daemon = True)
        self._writing = True
        for b in self._buttons:
            b.state(['disabled'])
        self._message.configure(text=f'Writing {name} ...',foreground=colors['normal'])
        thread.start()
        def check():
            if thread.is_alive():
                self.tv.root.after(100,check)
                return
            self._writing = False
            if self._code.window.winfo_exists():
                for b in self._buttons:
                    b.state(['!disabled'])
                self._message.configure(foreground=colors['error'])
            self._written(name,view,*result[0])
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
        #(the new file has the picked and edited particles, so only the plots
        #are kept):
        if not view:
            self.tv.show_line(msg,'normal')
        else:
            self.tv.on_open_file(name,particles = False)#(with its own message)

class AlignWindow:
    """The window of the align helper (see _viewer_align): the mean position
    and direction of the particles used (after the current edit), and the
    statements of an edit which turn the mean direction into a target
    direction, and move the mean position to a point, which are added to the
    edit (to be applied there)"""
    def __init__( self, tv ):
        import threading

        from . import _viewer_align as al
        tk, ttk = tk_modules()
        self.tv, self._al = tv, al
        w = tk.Toplevel(tv.root)
        w.title('MCPL viewer: Align particles')
        w.transient(tv.root)
        self.window = w
        f = ttk.Frame(w,padding=10)
        f.pack(fill='both',expand=True)
        edit = tv.v.edit_text
        ttk.Label(f,text=( 'The weighted means of the particles used'
                           + ( f' (after the edit "{edit}"):' if edit else ':' ) ),
                  font=tv.bold).pack(anchor='w')
        self._means = ttk.Label(f,justify='left')
        self._means.pack(anchor='w',pady=(4,8))
        dirs = [ '' ] + list(al.axis_choices)
        #(1. turning the mean direction):
        self._rotate = tk.BooleanVar(w,value=True)
        ttk.Checkbutton(f,text='Turn the mean direction into the direction',
                        variable=self._rotate,command=self._update).pack(anchor='w')
        row = ttk.Frame(f)
        row.pack(fill='x',padx=(24,0),pady=(2,6))
        self._target = self._combo(row,'Direction:',dirs[1:],'+z',14)
        self._keep = self._combo(row,'keeping the axis:',[ 'none' ] + dirs[1:],'none',14)
        self._pivot = self._combo(row,'rotating around:',[ 'mean position', 'origin' ],
                                  'mean position',18)
        ttk.Label(f,text='(any vector can be typed, as in (1,1,0), and a point to rotate around,'
                  ' as in (0,0,1m))',foreground=colors['dim']).pack(anchor='w',padx=(24,0))
        #(2. moving the mean position):
        self._move = tk.BooleanVar(w,value=False)
        ttk.Checkbutton(f,text='Then move the mean position to the point',
                        variable=self._move,command=self._update).pack(anchor='w',pady=(8,0))
        row = ttk.Frame(f)
        row.pack(fill='x',padx=(24,0),pady=(2,6))
        self._point = self._combo(row,'Point:',[ '(0,0,0)' ],'(0,0,0)',18)
        ttk.Label(row,text='in').pack(side='left',padx=(12,4))
        self._coords = {}
        for c in 'xyz':
            self._coords[c] = tk.BooleanVar(w,value=True)
            ttk.Checkbutton(row,text=c,variable=self._coords[c],
                            command=self._update).pack(side='left')
        #(the result):
        ttk.Label(f,text='Added to the edit:',font=tv.bold).pack(anchor='w',pady=(8,0))
        self._edit = tk.Text(f,width=90,height=3,wrap='char',font='TkFixedFont',relief='flat',
                             background='white',padx=6,pady=4)
        self._edit.pack(fill='x',pady=(2,0))
        self._result = ttk.Label(f,justify='left')
        self._result.pack(anchor='w',pady=(4,0))
        row = ttk.Frame(f)
        row.pack(fill='x',pady=(10,0))
        self._add = ttk.Button(row,text='Add to the edit',style='Accent.TButton',
                               command=self._on_add)
        self._add.pack(side='left')
        ttk.Button(row,text='Close',command=w.destroy).pack(side='left',padx=(6,0))
        w.bind('<Escape>',lambda _e : w.destroy())
        #(the means are read in a thread, first estimated from the first
        #particles, see _viewer_align.read_stats):
        self._stats, self._statements = None, None
        self._lock, self._new, self._gone = threading.Lock(), [], threading.Event()
        w.bind('<Destroy>',lambda e : self._gone.set() if e.widget is w else None)
        threading.Thread(target = lambda : al.read_stats(tv.v.picked_blocks(),self._publish,
                                                          self._gone.is_set),
                         daemon = True).start()
        self._update()
        self._poll()

    def _combo( self, parent, label, values, value, width ):
        _, ttk = tk_modules()
        ttk.Label(parent,text=label).pack(side='left',padx=(0 if label == 'Direction:'
                                                          or label == 'Point:' else 12,4))
        c = ttk.Combobox(parent,values=values,width=width)
        c.set(value)
        c.pack(side='left')
        c.bind('<<ComboboxSelected>>',lambda _e : self._update())
        c.bind('<KeyRelease>',lambda _e : self._update())
        return c

    def _publish( self, stats ):
        with self._lock:#(from the thread, shown by _poll)
            self._new.append(stats)

    def _poll( self ):
        if self._gone.is_set():
            return
        with self._lock:
            new, self._new = self._new, []
        if new:
            self._stats = new[-1]
            self._update()
        if self._stats is None or not self._stats.complete:
            self.window.after(200,self._poll)

    def _update( self ):
        """Show the means, and the statements of the edit with the result"""
        from ._viewer_ui import count_text, number_text
        al, s = self._al, self._stats
        self._statements = None
        if s is None:
            self._means.configure(text='Reading the particles ...')
            self._show('',None)
            return
        if s.w <= 0:
            self._means.configure(text='No particles (with weights) to align')
            self._show('',None)
            return
        how = 'all' if s.complete else f'estimate from the first {count_text(s.n)}'
        d = s.mean_dir
        self._means.configure(text=(
            f'Position: {_xyz(s.mean_pos)} cm\n'
            f'Direction: {"not defined (the directions cancel out)" if d is None else _xyz(d)},'
            f' spread {s.spread_deg:.3g} deg (typical angle to the mean direction)\n'
            f'Particles: {count_text(s.n)} ({how}), {chr(0x3a3)}w = {number_text(s.w)},'
            f' {s.types_text()}' ))
        try:
            target = keep = centre = None
            pivot = 'mean'
            if self._rotate.get():
                target = al.parse_vector(self._target.get(),'direction')
                k = self._keep.get().strip()
                keep = None if k in ( '', 'none' ) else al.parse_vector(k,'axis to keep')
                p = self._pivot.get().strip()
                pivot = ( 'mean' if p == 'mean position' else 'origin' if p == 'origin'
                          else al.parse_vector(p,'point to rotate around','cm') )
            if self._move.get():
                centre = al.parse_vector(self._point.get(),'point','cm')
            coords = ''.join( c for c in 'xyz' if self._coords[c].get() )
            text, pos, d = al.align_edit(s,target,keep,pivot,centre,coords)
        except MCPLError as e:
            self._show('',str(e))
            return
        self._statements = text
        self._show(text,( f'After it: position {_xyz(pos)} cm, direction {_xyz(d)}'
                          + ( '' if s.complete else ' (estimated)' ) ))

    def _show( self, text, result ):
        self._edit.configure(state='normal')
        self._edit.delete('1.0','end')
        self._edit.insert('1.0',text)
        self._edit.configure(state='disabled')
        error = result is not None and not text
        self._result.configure(text=result or '',foreground=colors['error' if error else 'dim'])
        #(added when the means of all particles are known):
        done = self._stats is not None and self._stats.complete
        self._add.state([ '!disabled' if text and done else 'disabled' ])

    def _on_add( self ):
        if not self._statements:
            return
        edit = self.tv.v.edit_text
        self.tv._use_example('edit',f'{edit};{self._statements}' if edit else self._statements)
        self.window.destroy()

def _xyz( v ):
    """A vector as a text, with rounding noise (as 1e-23 in a unit vector) as 0"""
    tiny = 1e-12 * max( 1.0, max( abs(c) for c in v ) )
    return '(' + ', '.join( f'{c:.6g}' if abs(c) > tiny else '0' for c in v ) + ')'
