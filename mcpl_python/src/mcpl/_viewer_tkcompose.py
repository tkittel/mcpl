
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

"""The Compose window of the viewer with Tk (see _viewer_compose for its
logic): the lines of the edit as cards, of which the one clicked unfolds with
the controls of its kind, a last card adding a line, the particles left after
each line, and the means of the particles for align lines, read in a thread."""

__all__ = []

from ._viewer_tkbase import (
    CompletionList,
    GreyText,
    auto_complete,
    bind_enter,
    command_keys,
    copy_menu,
    on_paste,
    tip,
    tk_modules,
    wrap_to_width,
)
from ._viewer_tkwindows import closed_by_escape
from ._viewer_ui import card_colors, colors, edit_color

#(the styles of the cards, closed and open, see _styles):
_card_styles = { False : 'Compose', True : 'ComposeOpen' }

class ComposeWindow:
    """The Compose window of the viewer tv (one at a time, see show)"""
    @staticmethod
    def of( tv ):
        """The open Compose window of the viewer tv, or None"""
        w = tv._compose
        return w if w is not None and w.window.winfo_exists() else None

    @staticmethod
    def show( tv ):
        """Open the Compose window (or show it again, if it is open)"""
        w = ComposeWindow.of(tv)
        if w is None:
            tv._compose = ComposeWindow(tv)
        else:
            w.window.lift()
            w.window.focus_force()

    def __init__( self, tv ):
        tk, ttk = tk_modules()
        self.tv = tv
        #(the lines which are not applied are kept when the window is closed,
        #for the next time it is opened, as long as the file is the same):
        old = tv._composer
        self.composer = old if old is not None and old.v is tv.logic.v else self._new_composer()
        self._grey = GreyText()
        w = tk.Toplevel(tv.root)
        w.title('MCPL: Composer')
        w.transient(tv.root)
        self.window = w
        _styles(ttk.Style(w))
        #(in a line of the colour of edits, as the part of the edit):
        line = tk.Frame(w,highlightthickness=2,highlightbackground=edit_color,
                        highlightcolor=edit_color)
        line.pack(fill='both',expand=True,padx=4,pady=4)
        f = ttk.Frame(line,padding=10)
        f.pack(fill='both',expand=True)
        ttk.Label(f,text=( 'Statements run from top to bottom. Filter conditions keep only the particles'
                           ' for which they are true, and the statements after them see only'
                           ' those. Click a part to change it.' ),
                  foreground=colors['dim'],wraplength=720,justify='left').pack(anchor='w')
        ttk.Label(f,text='Particles left',foreground=colors['dim']).pack(anchor='e',padx=(0,92),
                                                                         pady=(6,0))
        self._list = ttk.Frame(f)
        self._list.pack(fill='x')
        self._status = ttk.Label(f,foreground=colors['dim'])
        self._status.pack(anchor='w',pady=(6,0))
        buttons = ttk.Frame(f)
        buttons.pack(fill='x',pady=(6,0))
        help = ttk.Button(buttons,text='Help',command=self._help)
        help.pack(side='left')
        tip(help,'compose_help')
        close = ttk.Button(buttons,text='Close',command=w.destroy)
        close.pack(side='right')
        tip(close,'close')
        self._apply = ttk.Button(buttons,text='Apply',style='Accent.TButton',command=self._on_apply)
        self._apply.pack(side='right',padx=(0,6))
        tip(self._apply,'compose_apply')
        self._open = None#(the index of the unfolded line)
        self._popup = CompletionList(w,tv.system == 'aqua')
        self._reading = None#(of align lines: (key, line, mailbox))
        w.bind('<Destroy>',lambda e : self._stop_reading() if e.widget is w else None)
        self._build()
        self._poll()
        w.bind('<Alt-Key-a>',lambda _e : ( self._add(), 'break' )[1])
        closed_by_escape(w,lambda : next( ( x['text'] for x in self._lines if x['text'] ), w ))

    def _new_composer( self ):
        from ._viewer_compose import Composer
        self.tv._composer = Composer(self.tv.logic.v,apply_lines = self.tv.logic.on_edit_lines)
        return self.tv._composer

    def _help( self ):
        """The help of edit expressions (as in the Help menu)"""
        from ._viewer_ui import help_titles
        title, blocks = next( ( t, b ) for _, t, b in self.tv.logic.help_topics()
                              if t == help_titles['edit'] )
        self.tv.show_text(title,blocks)

    #The cards:

    def _build( self, focus = None ):
        """Make the cards of the lines (with the keyboard focus in the text of
        line focus, if given)"""
        for c in self._list.winfo_children():
            c.destroy()
        self._lines = []#(per line: its widgets by name)
        for i in range(len(self.composer.lines)):
            self._card(i)
        self._add_card()
        self._update()
        if focus is not None and focus < len(self._lines) and self._lines[focus]['text']:
            e = self._lines[focus]['text']
            e.focus_set()
            e.icursor('end')

    def _card( self, i ):
        tk, ttk = tk_modules()
        line, is_open = self.composer.lines[i], i == self._open
        st = _card_styles[is_open]
        card = ttk.Frame(self._list,style=f'{st}.Card.TFrame',padding=6)
        card.pack(fill='x',pady=2)
        top = ttk.Frame(card,style=f'{st}.TFrame')
        top.pack(fill='x')
        on = tk.BooleanVar(self.window,value=line.active)
        tick = ttk.Checkbutton(top,variable=on,style=f'{st}.TCheckbutton',takefocus=0,
                               command=lambda : self._toggle(i,on.get()))
        tick.pack(side='left')
        tip(tick,'line_on')
        arrow = ttk.Label(top,text='\u25be' if is_open else '\u25b8',style=f'{st}.TLabel',
                          cursor='hand2')
        arrow.pack(side='left',padx=(0,4))
        for widget in ( card, top, arrow ):
            widget.bind('<Button-1>',lambda _e : self._unfold(None if is_open else i))
        #(the text of an expression is typed in a field, under the menu of
        #the kind of the part when it is unfolded, and the text written by the
        #controls of the other kinds is only shown):
        if is_open:
            from ._viewer_compose import kinds
            kind = ttk.Combobox(top,values=list(kinds.values()),state='readonly',width=16)
            kind.set(kinds[line.kind])
            kind.pack(side='left',padx=(0,8))
            tip(kind,'line_kind')
            names = { text : name for name, text in kinds.items() }
            kind.bind('<<ComboboxSelected>>',lambda _e : self._set_kind(i,names[kind.get()]))
        e, after = None, top
        if line.kind == 'expression':
            row = top
            if is_open:
                row = after = ttk.Frame(card,style=f'{st}.TFrame',padding=(44,6,0,0))
                row.pack(fill='x')
            e = ttk.Entry(row,font='TkFixedFont',width=60)
            e.insert(0,line.text)
            e.pack(side='left',fill='x',expand=True)
            self._bind_text(e,i)
            shown = e
        else:
            shown = ttk.Label(top,text=line.text,font='TkFixedFont',style=f'{st}.TLabel')
            shown.pack(side='left',fill='x',expand=True)
            shown.bind('<Button-1>',lambda _e : self._unfold(None if is_open else i))
        mark = ttk.Label(top,width=2,style=f'{st}.TLabel')
        mark.pack(side='left',padx=(4,0))
        for label, name, command in ( ( '\u2715', 'line_delete', lambda : self._delete(i) ),
                                      ( '\u2193', 'line_down', lambda : self._move(i,1) ),
                                      ( '\u2191', 'line_up', lambda : self._move(i,-1) ) ):
            b = ttk.Button(top,text=label,width=2,takefocus=0,style='Small.TButton',
                           command=command)
            b.pack(side='right',padx=(2,0))
            tip(b,name)
        count = ttk.Label(top,width=14,anchor='e',style=f'{st}.TLabel',foreground=colors['dim'])
        count.pack(side='right',padx=(6,6))
        error = ttk.Label(card,style=f'{st}.TLabel',foreground=colors['error'],justify='left')
        wrap_to_width(error)
        copy_menu(error,self.tv.copy_text)
        self._lines.append({ 'top' : top, 'text' : e, 'shown' : shown, 'after' : after,
                             'mark' : mark, 'count' : count, 'error' : error, 'notes' : {} })
        if is_open:
            self._body(card,i,st)

    def _add_card( self ):
        _, ttk = tk_modules()
        card = ttk.Frame(self._list,style='ComposeAdd.Card.TFrame',padding=8,cursor='hand2')
        card.pack(fill='x',pady=2)
        label = ttk.Label(card,text='+  Add new part',style='ComposeAdd.TLabel',underline=3)
        label.pack(side='left',padx=(6,0))
        for widget in ( card, label ):
            widget.bind('<Button-1>',lambda _e : self._add())
            tip(widget,'add_line')

    def _body( self, card, i, st ):
        """The controls of the unfolded line i, in the rows of its kind (none
        for expressions)"""
        tk, ttk = tk_modules()
        line = self.composer.lines[i]
        rows = self.composer.rows(i)
        if not rows:
            return
        body = ttk.Frame(card,style=f'{st}.TFrame',padding=(44,6,0,2))
        body.pack(fill='x')
        option = tk.StringVar(self.window,value=line.form.get('option',''))
        for row in rows:
            fr = ttk.Frame(body,style=f'{st}.TFrame')
            fr.pack(fill='x',pady=2)
            if row.option:
                ttk.Radiobutton(fr,text=row.label,value=row.option,variable=option,width=16,
                                style=f'{st}.TRadiobutton',takefocus=0,
                                command=lambda : self._set(i,'option',option.get(),True)
                                ).pack(side='left')
            elif row.label:
                ttk.Label(fr,text=row.label,style=f'{st}.TLabel').pack(side='left',padx=(0,6))
            for c in row.controls:
                self._control(fr,i,c,st)

    def _control( self, parent, i, c, st ):
        """A control of line i (see _viewer_compose.Control)"""
        tk, ttk = tk_modules()
        if c.kind in ( 'text', 'note' ):
            label = ttk.Label(parent,text=c.value,style=f'{st}.TLabel',wraplength=680,
                              justify='left',**( { 'foreground' : colors['dim'] }
                                                  if c.kind == 'note' else {} ))
            label.pack(side='left',padx=(0,4))
            if c.kind == 'note':
                self._lines[i]['notes'][c.name] = label
            return
        if c.kind == 'check':
            var = tk.BooleanVar(self.window,value=c.value)
            ttk.Checkbutton(parent,text=c.choices,variable=var,style=f'{st}.TCheckbutton',
                            takefocus=0,command=lambda : self._set(i,c.name,var.get(),True)
                            ).pack(side='left',padx=(0,4))
            return
        width = max( [ 6, len(c.value) + 3, len(c.hint or '') + 1 ] )
        if c.kind == 'entry':
            w = ttk.Entry(parent,width=width)
            w.insert(0,c.value)
        else:
            width = max( [ width, *( len(t) + 1 for t in c.choices ) ] )
            w = ttk.Combobox(parent,values=c.choices,width=min(28,width),
                             state='readonly' if c.kind == 'select' else 'normal')
            w.set(c.value)
            def chosen( _e ):
                self._grey.forget(w)
                self._set(i,c.name,w.get(),True)
            w.bind('<<ComboboxSelected>>',chosen)
        if c.kind != 'select':
            w.bind('<KeyRelease>',lambda _e : self._set(i,c.name,self._grey.text(w),False))
            on_paste(w,lambda : self._set(i,c.name,self._grey.text(w),False))
            bind_enter(w,self._on_apply)
        if c.hint:
            #(the hint is shown while it is empty, and not typed in):
            if not c.value:
                self._grey.show(w,c.hint)
            w.bind('<FocusIn>',lambda _e : self._grey.remove(w),'+')
            w.bind('<FocusOut>',lambda _e : None if w.get() else self._grey.show(w,c.hint),'+')
        w.pack(side='left',padx=(0,4))

    #Changes:

    def _unfold( self, i ):
        self._open = i
        self._build()

    def _add( self ):
        """Add a new part (an expression), unfolded, with the keyboard focus
        in its text"""
        self._open = self.composer.add()
        self._build(focus = self._open)

    def _delete( self, i ):
        self.composer.delete(i)
        self._open = None
        self._build()

    def _move( self, i, step ):
        self.composer.move(i,step)
        if self._open == i and 0 <= i + step < len(self.composer.lines):
            self._open = i + step
        self._build()

    def _toggle( self, i, active ):
        self.composer.set_active(i,active)
        self._update()

    def _set_kind( self, i, kind ):
        self.composer.set_kind(i,kind)
        self._build()

    def _set( self, i, name, value, rebuild ):
        """Set a control of line i (rebuilding the cards when it can change the
        controls, e.g. the units of a new quantity, else only showing the new
        text of the line)"""
        self.composer.set_value(i,name,value)
        if rebuild:
            self._build()
            return
        self._lines[i]['shown'].configure(text=self.composer.lines[i].text)
        self._update()

    #The texts of the lines, with completion:

    def _bind_text( self, e, i ):
        e.bind('<KeyRelease>',lambda ev : self._on_key(e,i,ev))
        on_paste(e,lambda : self._typed(e,i))
        e.bind('<Tab>',lambda _e : self._complete(e,i))
        bind_enter(e,lambda : self._on_enter(e))
        e.bind('<Escape>',lambda _e : self._popup.close() or 'break' if self._popup.shown else None)
        for key, delta in ( ( '<Up>', -1 ), ( '<Down>', 1 ) ):
            e.bind(key,lambda _e, d=delta : ( self._popup.move(d) or 'break'
                                              if self._popup.shown else None ))
        e.bind('<FocusOut>',lambda _e : self._popup.close(),'+')

    def _on_key( self, e, i, event ):
        if event.keysym in command_keys:
            return
        self._popup.close()
        self._typed(e,i)
        e = self._lines[i]['text']#(a new card, if the line became typed)
        auto_complete(self._popup,e,self.composer.completions,lambda : self._typed(e,i))

    def _typed( self, e, i ):
        """The text of line i was typed in, which makes it an expression"""
        was = self.composer.lines[i].kind
        self.composer.set_text(i,e.get())
        self._status.configure(text=self.composer.hint(e.get(),e.index('insert')) or '')
        if was != 'expression' and self._open == i:
            cursor = e.index('insert')
            self._build(focus = i)
            self._lines[i]['text'].icursor(cursor)
        else:
            self._update()

    def _complete( self, e, i ):
        text, cursor, choices, start = self.composer.complete(e.get(),e.index('insert'))
        e.delete(0,'end')
        e.insert(0,text)
        e.icursor(cursor)
        if choices:
            self._popup.open(e,start,choices,None,lambda : self._typed(e,i))
        self._typed(e,i)
        return 'break'

    def _on_enter( self, e ):
        if self._popup.shown:
            self._popup.insert(e)
        else:
            self._on_apply()
        return 'break'

    #Checks, counts, and applying:

    def _update( self ):
        """Show the checks and counts of the lines, and whether they can be
        applied"""
        checks, counts = self.composer.checks(), self.composer.counts()
        blocking = False
        for i, ( line, w ) in enumerate(zip(self.composer.lines,self._lines)):
            msg = checks[i]
            w['shown'].configure(foreground=colors['normal' if line.active else 'dim'])
            w['mark'].configure(text='\u2717' if msg else ( '\u2713' if msg == '' else '' ),
                                foreground=colors['error' if msg else 'ok'])
            w['error'].configure(text=msg or '')
            if msg:
                w['error'].pack(fill='x',padx=(44,0),after=w['after'])
            else:
                w['error'].pack_forget()
            blocking = blocking or bool( msg and line.active )
        self._show_counts(counts)
        ok = self.composer.pending and not blocking
        self._apply.configure(style='Accent.TButton' if ok else 'TButton')
        self._apply.state([ '!disabled' if ok else 'disabled' ])

    def _show_counts( self, counts = None ):
        counts = counts if counts is not None else self.composer.counts()
        for i, ( line, w ) in enumerate(zip(self.composer.lines,self._lines)):
            c = counts[i] if counts else None
            w['count'].configure(text=c or ( '(off)' if not line.active else '' ))

    def _on_apply( self ):
        if self.composer.apply():
            self._build()
        else:
            self._update()
        return 'break'

    #Following the viewer, and reading the particles of align lines:

    def _poll( self ):
        """Follow the viewer (another file, or an edit applied elsewhere), show
        the counts while the particles are read, and the means of align lines"""
        if not self.window.winfo_exists():
            return
        if self.composer.v is not self.tv.logic.v:
            self._stop_reading()
            self.composer, self._open = self._new_composer(), None
            self._build()
        elif self.composer.sync():
            self._open = None
            self._build()
        else:
            self._show_counts()
        self._read_align()
        self.window.after(300,self._poll)

    def _read_align( self ):
        """Read the means of the particles before an align line (one at a
        time, in a thread, see _viewer_threads), and show them"""
        from . import _viewer_align as al
        from ._viewer_threads import Mailbox, start
        if self._reading is not None:
            key, line, mailbox = self._reading
            items = mailbox.take()
            if items and line in self.composer.lines:
                self.composer.set_align_stats(line,key,items[-1])
                self._show_line(self.composer.lines.index(line))
            if mailbox.done or line not in self.composer.lines:
                self._stop_reading()
            return
        for i in range(len(self.composer.lines)):
            request = self.composer.align_reading(i)
            if request is not None:
                key, args = request
                mailbox = Mailbox()
                self._reading = ( key, self.composer.lines[i], mailbox )
                start(al.read_file_stats,mailbox,*args)
                return

    def _stop_reading( self ):
        if self._reading is not None:
            self._reading[2].stop()
            self._reading = None

    def _show_line( self, i ):
        """Show the text and the notes of line i again (e.g. after the means
        of an align line are known)"""
        w = self._lines[i]
        w['shown'].configure(text=self.composer.lines[i].text)
        for row in ( self.composer.rows(i) if w['notes'] else () ):
            for c in row.controls:
                if c.name in w['notes']:
                    w['notes'][c.name].configure(text=c.value)
        self._update()

def _styles( style ):
    """The styles of the cards: closed, open (unfolded), and the card adding a
    line"""
    for open_, name in _card_styles.items():
        bg = card_colors['selected' if open_ else 'card']
        style.configure(f'{name}.TFrame',background=bg)
        style.configure(f'{name}.Card.TFrame',background=bg,relief='solid',borderwidth=1,
                        bordercolor=card_colors['border'])
        for widget in ( 'TLabel', 'TCheckbutton', 'TRadiobutton' ):
            style.configure(f'{name}.{widget}',background=bg)
            style.map(f'{name}.{widget}',background=[ ( 'active', bg ) ])
    style.configure('ComposeAdd.Card.TFrame',background=card_colors['bg'],relief='solid',
                    borderwidth=1,bordercolor=card_colors['border'])
    style.configure('ComposeAdd.TLabel',background=card_colors['bg'],
                    foreground=card_colors['accent'],font='TkDefaultFont 10 bold')
