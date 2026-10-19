
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

"""The viewer in the terminal (with curses), drawing the plots with the
unicode plotting backend. The drawing is done on a screen object (see
_CursesScreen), so it can also be tested with a screen in memory."""

__all__ = []

import re

from . import _viewer_ui as ui
from ._common import MCPLError

#Styles of the text (mapped to curses attributes by the screen):
#'normal', 'bold', 'reverse', 'key' (highlighted shortcut letters), 'ok',
#'error', 'dim', and ('rgb', fg, bg) with colour numbers 0-255 (or None).

_sgr = re.compile(r'\x1b\[([0-9;]*)m')

def _ansi_segments( text ):
    """Split a line with ANSI colour sequences (of 8 or 256 colours) into
    segments of (text, fg, bg)"""
    res, fg, bg, pos = [], None, None, 0
    for m in _sgr.finditer(text):
        if m.start() > pos:
            res.append( ( text[pos:m.start()], fg, bg ) )
        codes = [ int(c) for c in m.group(1).split(';') if c ]
        i = 0
        while i < len(codes):
            code = codes[i]
            if code == 0:
                fg = bg = None
            elif 30 <= code <= 37:
                fg = code - 30
            elif 40 <= code <= 47:
                bg = code - 40
            elif code in ( 38, 48 ) and i + 2 < len(codes) and codes[i+1] == 5:
                if code == 38:
                    fg = codes[i+2]
                else:
                    bg = codes[i+2]
                i += 2
            i += 1
        pos = m.end()
    if pos < len(text):
        res.append( ( text[pos:], fg, bg ) )
    return res

class _CursesScreen:
    """The terminal, with curses"""
    def __init__( self, stdscr, use_colors = True ):
        import curses
        self._c, self._w = curses, stdscr
        try:
            curses.curs_set(0)
        except curses.error:
            pass#(terminals which can not hide the cursor)
        stdscr.keypad(True)
        stdscr.timeout(100)
        curses.mousemask( curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION )
        self.colors = use_colors and curses.has_colors()
        self._pairs = {}
        self.ncolors = 0
        if self.colors:
            curses.start_color()
            self.ncolors = 256 if curses.COLORS >= 256 else 8
            try:
                curses.use_default_colors()
                self._default = -1
            except curses.error:
                self._default = 0
        self._keys = { curses.KEY_UP : 'Up', curses.KEY_DOWN : 'Down',
                       curses.KEY_LEFT : 'Left', curses.KEY_RIGHT : 'Right',
                       curses.KEY_HOME : 'Home', curses.KEY_END : 'End',
                       curses.KEY_BACKSPACE : 'Backspace', 127 : 'Backspace',
                       8 : 'Backspace', curses.KEY_DC : 'Delete',
                       curses.KEY_F1 : 'F1', curses.KEY_PPAGE : 'PageUp',
                       curses.KEY_NPAGE : 'PageDown', 10 : 'Enter', 13 : 'Enter',
                       curses.KEY_ENTER : 'Enter', 27 : 'Esc', 9 : 'Tab',
                       curses.KEY_RESIZE : 'Resize', curses.KEY_SR : 'MoveUp',
                       curses.KEY_SF : 'MoveDown' }
    def size( self ):
        return self._w.getmaxyx()
    def clear( self ):
        self._w.erase()
    def _pair( self, fg, bg ):
        key = ( fg, bg )
        if key not in self._pairs:
            n = len(self._pairs) + 1
            if n >= self._c.COLOR_PAIRS:
                return 0
            d = self._default
            self._c.init_pair( n, d if fg is None else fg, d if bg is None else bg )
            self._pairs[key] = n
        return self._c.color_pair(self._pairs[key])
    def put( self, y, x, text, style = 'normal' ):
        c = self._c
        h, w = self.size()
        if not ( 0 <= y < h ) or x >= w:
            return
        text = text[:max(0,w-x-(1 if y == h-1 else 0))]
        if isinstance(style,tuple):
            attr = self._pair(style[1],style[2]) if self.colors else 0
        else:
            attr = { 'bold' : c.A_BOLD, 'reverse' : c.A_REVERSE,
                     'dim' : c.A_DIM }.get(style,0)
            if self.colors and style in ( 'key', 'ok', 'error' ):
                attr = self._pair( { 'key' : 3, 'ok' : 2, 'error' : 1 }[style], None ) | (
                    c.A_BOLD if style == 'key' else 0 )
            elif style == 'key':
                attr = c.A_UNDERLINE
        try:
            self._w.addstr(y,x,text,attr)
        except c.error:
            pass
    def refresh( self ):
        self._w.refresh()
    def getkey( self ):
        """The next key ('Up', 'Enter', 'a', ...), ('Mouse', x, y, clicked),
        or None after the timeout"""
        c = self._c
        try:
            k = self._w.get_wch()
        except c.error:
            return None
        if isinstance(k,str):
            if len(k) == 1 and ord(k) in self._keys:
                return self._keys[ord(k)]
            return k
        if k == c.KEY_MOUSE:
            try:
                _, x, y, _, bstate = c.getmouse()
            except c.error:
                return None
            clicked = bool( bstate & ( c.BUTTON1_CLICKED | c.BUTTON1_PRESSED
                                       | c.BUTTON1_RELEASED ) )
            return ( 'Mouse', x, y, clicked )
        if k not in self._keys:
            #(Up and Down with modifiers, which terminals give as keys named
            #kUP3 to kUP7 and kDN3 to kDN7):
            try:
                name = c.keyname(k)
            except ( c.error, ValueError ):
                return None
            for prefix, key in ( (b'kUP','MoveUp'), (b'kDN','MoveDown') ):
                if name.startswith(prefix) and name[3:].isdigit():
                    return key
        return self._keys.get(k)

def _box_width( n, available, editing ):
    """Width of the box of a field with a text of n characters: as wide as the
    text, but while it is edited at least 30 (and one more for the cursor),
    and at most what is available (at least 10)"""
    want = max( 30, n + 1 ) if editing else n
    return max( 1, min( want, max( 10, available ) ) )

class TextViewer:
    """The viewer in a terminal (on a screen, see _CursesScreen)"""
    def __init__( self, viewer, screen, backend = None ):
        from ._plotbackend_text import UnicodeBackend
        self.v, self.s = viewer, screen
        #(the backend drawing the plots, also deciding whether only ASCII
        #characters are used):
        self.bk = backend if backend is not None else UnicodeBackend()
        self.ascii = self.bk.encoding == 'ascii'
        self.editor = None#(LineEditor of the field being edited)
        self.message = ''#(shown in the status line)
        self.hover = None
        self.show_help = False
        self.scroll = 0
        self._regions = []#(y, x0, x1, what) of the clickable things

    def run( self ):
        self.v.start()
        try:
            self.draw()
            while True:
                k = self.s.getkey()
                if k is None:
                    if self.v.poll():
                        self.draw()
                    continue
                if self.handle(k) == 'quit':
                    return
                self.draw()
        except KeyboardInterrupt:
            pass#(Ctrl-C quits, like q)
        finally:
            self.v.stop()

    #Keys and mouse:

    def handle( self, k ):
        if isinstance(k,tuple):
            return self._mouse(*k[1:])
        if k == 'Resize':
            return None
        if self.show_help:
            self.show_help = False
            return None
        if self.editor is not None:
            r = self.editor.key(k)
            if r == 'cancel':
                self.editor = None
            elif r == 'apply':
                self._apply()
            return None
        if k == 'PageDown':
            self.scroll += 5
            return None
        if k == 'PageUp':
            self.scroll = max( 0, self.scroll - 5 )
            return None
        return self._do( ui.key_action(k) )

    def _do( self, action ):
        v = self.v
        self.message = ''
        if action == 'previous':
            v.select(v.current - 1)
            self.scroll = 0
        elif action == 'next':
            v.select(v.current + 1)
            self.scroll = 0
        elif action in ( 'move_up', 'move_down' ):
            v.move(-1 if action == 'move_up' else 1)
        elif action in ( 'skip', 'limit', 'pick', 'edit', 'plot', 'write', 'state', 'change' ):
            self.editor = ui.editor_for(v,action)
        elif action == 'help':
            self.show_help = True
        elif action == 'quit':
            return 'quit'
        return None

    def _apply( self ):
        done, self.message, replot = ui.apply_editor(self.v,self.editor)
        if done:
            self.editor = None
        if replot:
            self.scroll = 0

    def _mouse( self, x, y, clicked ):
        for ry, x0, x1, what in self._regions:
            if ry == y and x0 <= x < x1:
                self.hover = what
                if clicked:
                    if isinstance(what,int):
                        self.v.select(what)
                        self.scroll = 0
                        self.editor = None
                    else:
                        return self._do(what)
                return None
        self.hover = None
        return None

    #Drawing:

    def draw( self ):
        s, v = self.s, self.v
        s.clear()
        self._regions = []
        h, w = s.size()
        if self.show_help:
            for i, line in enumerate(ui.help_text.splitlines()):
                s.put(i,1,line)
            s.put(h-1,1,'(press any key)','dim')
            s.refresh()
            return
        views = v.views
        lw = min( max( len(label) for _, label in views ) + 4, max( 12, w // 4 ) )
        nbottom = len(ui.fields) + 5
        top = max( 3, h - nbottom )
        #The views (from the second line, below the first status line):
        for i, (_, label) in enumerate(views[:max(0,top-1)]):
            sel = i == v.current
            mark = ( '> ' if self.ascii else '\u25b8 ' ) if sel else '  '
            s.put(i+1,0,mark + label[:lw-3],'reverse' if sel else 'normal')
            self._regions.append( ( i + 1, 0, lw - 1, i ) )
        #The status and the plot:
        first, second = v.status_lines(**( {'weights':'sum(weights)'} if self.ascii else {} ))
        s.put(0,lw+1,first,'bold')
        s.put(1,lw+1,second)
        self._draw_plot(2,lw+1,top-2,w-lw-2)
        #The fields:
        popup = None#(line and column of the name completed, if any)
        y = top
        for field, label, key, kpos, empty in ui.fields:
            a, b, c = ui.labelled(label,kpos)
            x = 1
            for part, style in ( (a,'normal'), (b,'key'), (c+': ','normal') ):
                s.put(y,x,part,style)
                x += len(part)
            ed = self.editor if self.editor is not None and self.editor.field == field else None
            text = ed.text if ed else v.field_text(field)
            fw = _box_width( len(text) if ed else len(text or empty), w - x - 4, ed is not None )
            if ed:
                start = max( 0, ed.cursor - fw + 1 )
                shown = text[start:start+fw]
                s.put(y,x,'[' + shown.ljust(fw) + ']','reverse')
                if ed.choices:
                    popup = ( y, x + 1 + max( 0, ed.choice_start - start ) )
                cx = x + 1 + ed.cursor - start
                s.put(y,cx,( text[ed.cursor] if ed.cursor < len(text) else ' ' ),'bold')
                marks = ( '+', 'x' ) if self.ascii else ( '\u2713', '\u2717' )
                s.put(y,x+fw+3,marks[0] if ed.ok else marks[1],'ok' if ed.ok else 'error')
            else:
                s.put(y,x,'[' + ( text or empty )[:fw] + ']',
                      'normal' if text else 'dim')
            self._regions.append( ( y, 1, w - 1, field ) )
            y += 1
        #Hint, or message of the check, or completions:
        line, style = ui.hint_line(self.editor,popup=True)
        s.put(y,1,line,style)
        y += 1
        #The actions (the commands doing the same are printed on quit):
        x = 1
        for action, label, keys, kpos in ui.actions:
            if self.editor is not None and self.editor.field == action in ui.file_prompts:
                part = ui.file_prompts[action]
                s.put(y,x,part,'bold')
                fw = _box_width( len(self.editor.text), w - x - len(part) - 4, True )
                s.put(y,x+len(part),'[' + self.editor.text[-fw:].ljust(fw) + ']','reverse')
                break
            a, b, c = ui.labelled(label,kpos)
            x0 = x
            for part, style in ( ('[' + a,'normal'), (b,'key'), (c + ']','normal') ):
                s.put(y,x,part,style)
                x += len(part)
            self._regions.append( ( y, x0, x, action ) )
            x += 2
        y += 1
        #Status line: messages, or the shortcut of what is under the mouse:
        status = self.message or ( ui.shortcut_text(self.hover if isinstance(self.hover,str) else 'views')
                                   if self.hover is not None else '' )
        s.put(min(y,h-1),1,status,'error' if self.message.startswith('Not') else 'normal')
        if popup:
            self._draw_popup(*popup)
        s.refresh()

    def _draw_popup( self, y, x ):
        """The completions in a box above the line y, from the column x (as many
        as fit, scrolled to the chosen one)"""
        s, ed = self.s, self.editor
        w = s.size()[1]
        choices = ed.choices
        n = len(choices)
        first, rows = ui.popup_rows(ed,min( y - 3, 15 ))
        nw = max( len(name) for name, _ in choices )
        dw = max( len(d or '') for _, d in choices )
        width = min( nw + 2 + dw, w - 4 )
        x = max( 0, min( x - 1, w - width - 3 ) )
        top = y - rows - 2
        hl, vl, corners = ( ( '-', '|', '++++' ) if self.ascii else
                            ( '\u2500', '\u2502', '\u250c\u2510\u2514\u2518' ) )
        count = f' {ed.selected+1}/{n} ' if rows < n else ''
        s.put(top,x,corners[0] + hl * width + corners[1],'normal')
        for i in range(rows):
            k = first + i
            name, descr = choices[k]
            text = ( name.ljust(nw) + '  ' + ( descr or '' ) )[:width].ljust(width)
            s.put(top+1+i,x,vl,'normal')
            if k == ed.selected:
                s.put(top+1+i,x+1,text,'reverse')
            else:
                s.put(top+1+i,x+1,name.ljust(nw)[:width],'bold')
                s.put(top+1+i,x+1+nw,text[nw:],'dim')
            s.put(top+1+i,x+1+width,vl,'normal')
        bottom = hl * max( 0, width - len(count) ) + count
        s.put(top+1+rows,x,corners[2] + bottom[:width] + corners[3],'normal')

    def _draw_plot( self, y0, x0, height, width ):
        fig = self.v.figure()
        if fig is None or height < 6 or width < 40:
            return
        npanels = max( 1, len(fig.panels) )
        #(as many rows per panel as fit, but at least 5):
        lines = None
        for h in range( max( 5, ( height - 2 ) // npanels - 4 ), 4, -1 ):
            n = self.bk.name
            bk = type(self.bk)(**{ f'{n}_width' : width, f'{n}_height' : h,
                                   f'{n}_color' : 'never' })
            bk._nc = getattr(self.s,'ncolors',8 if self.s.colors else 0)
            lines = bk.draw(fig).split('\n')
            if len(lines) <= height:
                break
        self.scroll = min( self.scroll, max( 0, len(lines) - height ) )
        for i, line in enumerate(lines[self.scroll:self.scroll+height]):
            x = x0
            for text, fg, bg in _ansi_segments(line):
                self.s.put(y0+i,x,text,( 'rgb', fg, bg ) if fg is not None or bg is not None else 'normal')
                x += len(text)

def run_viewer( viewer, backend = None ):
    """Run the viewer in the terminal (with curses), with the plots drawn with
    the backend (a text backend, default unicode, whose colour setting is
    used)"""
    try:
        import curses
    except ImportError:
        import sys
        extra = ( ' (install the windows-curses Python package)'
                  if sys.platform == 'win32' else '' )
        raise MCPLError('The viewer in the terminal needs the curses module of'
                        f' Python{extra}')
    import sys
    if not ( sys.stdin.isatty() and sys.stdout.isatty() ):
        raise MCPLError('The viewer in the terminal needs a terminal (its input'
                        ' and output can not be redirected)')
    from ._termcolor import _use_colors
    #(as for plots printed in the terminal, but curses knows which colours the
    #terminal has):
    use_colors = _use_colors(getattr(backend,'_when','auto'),lambda : True)
    def main( stdscr ):
        TextViewer(viewer,_CursesScreen(stdscr,use_colors),backend).run()
    curses.wrapper(main)
