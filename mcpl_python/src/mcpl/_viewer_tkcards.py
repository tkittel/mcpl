
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

"""The list of the cards of the views of the viewer with Tk (see _viewer_tk and
WidgetViewer.cards)"""

__all__ = []

from ._viewer_tkbase import elided, tk_modules, wrapped
from ._viewer_widgets import card_colors, colors

#The heights of the cards:
_card_heights = { 'card' : 64, 'small' : 30, 'header' : 26 }

class CardList:
    """The cards of the views (see WidgetViewer.cards and Card) on a canvas
    which can be scrolled: a small image of the plot, its name and badges, or
    a compact card with its name and status, under the headers of their
    groups, with the shown one selected. Cards are clicked to show them,
    dragged to move them (the custom plots), and removed with their menu
    (right click), as far as they allow it. The groups are folded (showing
    only their overview) except that of the shown view (see
    WidgetViewer.folded_groups), a click on a header shows the overview of
    its group, and the standard groups are deactivated with the menu of their
    header. The inactive groups are at the end, and activated by a click."""
    width, thumb = 300, ( 84, 50 )

    def __init__( self, parent, viewer ):
        tk, ttk = tk_modules()
        self.tv = viewer
        frame = ttk.Frame(parent)
        frame.pack(fill='both',expand=True)
        self.canvas = tk.Canvas(frame,width=self.width+12,background=card_colors['bg'],
                                highlightthickness=0)
        bar = ttk.Scrollbar(frame,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        self._images = {}#PNG data -> PhotoImage (kept, as Tk needs them)
        self._shown = None#(what is drawn, to only draw it again when changed)
        self._slots = []#(top, bottom, kind, what): 'card' (the Card), 'header' (group) or 'add'
        self._drag = None#(the key of the card dragged, and where it started)
        c = self.canvas
        c.bind('<ButtonPress-1>',self._on_press)
        c.bind('<B1-Motion>',self._on_motion)
        c.bind('<ButtonRelease-1>',self._on_release)
        #(a menu of the card, with the right button, or Ctrl and a click on
        #macOS, where Tk before 8.7 gives the right button as button 2):
        if c.tk.call('tk','windowingsystem') == 'aqua':
            old = tk.TkVersion < 8.7
            buttons = ( '<Button-2>' if old else '<Button-3>', '<Control-Button-1>' )
        else:
            buttons = ( '<Button-3>', '<Button-2>' )
        for button in buttons:
            c.bind(button,self._on_menu)
        #(scrolling with the wheel, as given by Windows and macOS, or X11):
        c.bind('<MouseWheel>',lambda e : c.yview_scroll(-1 if e.delta > 0 else 1,'units'))
        c.bind('<Button-4>',lambda _e : c.yview_scroll(-1,'units'))
        c.bind('<Button-5>',lambda _e : c.yview_scroll(1,'units'))

    def _image( self, key ):
        tk, _ttk = tk_modules()
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
        folded = self.tv.folded_groups()
        images = [ self._image(c.key) if c.image else None for c in cards ]
        current = self.tv.shown_key
        shown = ( tuple(cards), current, tuple(sorted(folded)),
                  tuple( id(i) for i in images ) )
        if shown == self._shown:
            return
        new_current = self._shown is None or self._shown[1] != current
        self._shown = shown
        c = self.canvas
        c.delete('all')
        self._slots = []
        y, group = 6, False#(False: before the first header)
        selected = None#(where the shown card is, if it is a new one)
        added = False#(whether the card adding a plot is drawn)
        for card, img in zip(cards,images):
            if card.inactive and not added:
                y, added = self._add_card(y), True
            if card.grouped and card.group != group:
                group = card.group
                self._header(y,group)
                y += _card_heights['header']
            shown = card.key == current
            if card.grouped and group in folded and not ( shown or card.pinned ):
                continue
            lines = None if card.compact or card.inactive else self._name_lines(card)
            h = _card_heights['small' if lines is None else 'card']
            if lines is not None:
                h = max( h, 12 + self._text_height(card,lines) )#(e.g. for larger fonts)
            self._card(y,h,card,img,shown,lines)
            self._slots.append( ( y, y + h, 'card', card ) )
            if shown and new_current:
                selected = ( y, y + h )
            y += h + 6
        if not added:
            y = self._add_card(y)
        c.configure(scrollregion=( 0, 0, self.width + 8, y ))
        #(the view stays within the cards when there are fewer of them, e.g.
        #when groups are folded, so there is no empty space above them):
        height = c.winfo_height()
        if y <= height:
            c.yview_moveto(0)
        elif c.canvasy(0) > y - height:
            c.yview_moveto(( y - height ) / y)
        if selected is not None:
            #(the selected card is scrolled into view):
            top, bottom = c.canvasy(0), c.canvasy(c.winfo_height())
            if selected[0] < top or selected[1] > bottom:
                c.yview_moveto(max( 0.0, ( selected[0] - 40 ) / y ))

    def _rect( self, x0, y0, x1, y1, r, **kw ):
        pts = [ x0+r, y0, x1-r, y0, x1, y0, x1, y0+r, x1, y1-r, x1, y1,
                x1-r, y1, x0+r, y1, x0, y1, x0, y1-r, x0, y0+r, x0, y0 ]
        return self.canvas.create_polygon(pts,smooth=True,**kw)

    def _add_card( self, y ):
        """Draw the card adding a plot (after the custom plots), returning the
        position below it"""
        col = card_colors
        self._rect(4,y,self.width,y+34,12,outline=col['border'],dash=(3,3),fill='')
        self.canvas.create_text(self.width/2,y+17,text='+  New plot',fill=col['accent'],
                                font=self.tv.bold)
        self._slots.append( ( y, y + 34, 'add', None ) )
        return y + 40

    def _header( self, y, group ):
        mark = '\u25b8' if group in self.tv.folded_groups() else '\u25be'
        self.canvas.create_text(8,y+13,anchor='w',fill=card_colors['dim'],
                                text=f'{mark}  {( group or "More plots" ).upper()}',
                                font=( self.tv.bold.cget('family'), 8, 'bold' ))
        self._slots.append( ( y, y + _card_heights['header'], 'header', group ) )

    def _name_lines( self, card ):
        """The lines of the name of a card (one or two, see wrapped)"""
        return wrapped(card.name,self.tv.bold,self.width-( 14 + self.thumb[0] + 12 )-22)

    def _text_height( self, card, lines ):
        """The height of the lines of the name and of the badges (or the
        problem) below them, as drawn by _card"""
        below = card.problem or card.badges
        return len(lines) * self.tv.bold.metrics('linespace') + ( 22 if below else 0 )

    def _card( self, y, h, card, img, selected, lines ):
        c, col = self.canvas, card_colors
        if card.inactive:
            #(the card of an inactive group, in grey with a dashed outline):
            self._rect(4,y,self.width,y+h,12,fill=col['bg'],outline=col['border'],dash=(3,3))
            c.create_text(16,y+h/2,anchor='w',fill=col['dim'],font=self.tv.bold,text=card.name)
            c.create_text(self.width-10,y+h/2,anchor='e',fill=col['accent'],
                          font=( self.tv.bold.cget('family'), 8 ),text=card.status)
            return
        fill = col['selected'] if selected else ( col['badge'] if card.overview else col['card'] )
        self._rect(4,y,self.width,y+h,12,fill=fill,
                   outline=col['accent'] if selected else col['border'],width=2 if selected else 1)
        if card.overview:
            #(the overview of a group: tinted, with a stripe at its left):
            c.create_rectangle(5,y+10,9,y+h-10,fill=col['accent'],outline='')
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
            c.create_text(x+self.thumb[0]/2,y+h/2,text='\u2717',fill=colors['error'],
                          font=( self.tv.bold.cget('family'), 22, 'bold' ))
        x += self.thumb[0] + 12
        #(the name in one or two lines, with the badges or the problem below
        #them, in the middle of the card):
        ls = self.tv.bold.metrics('linespace')
        y0 = y + ( h - self._text_height(card,lines) ) / 2
        for i, line in enumerate(lines):
            c.create_text(x,y0+ls*i,anchor='nw',fill=col['text'],font=self.tv.bold,text=line)
        top = y0 + len(lines) * ls + 4
        if card.problem:
            c.create_text(x,top+9,anchor='w',fill=colors['error'],
                          font=( self.tv.bold.cget('family'), 8 ),
                          text=elided(card.problem,self.tv.bold,self.width-x-22))
        for b in ( () if card.problem else card.badges ):
            w = 10 + 6.5 * len(b)
            self._rect(x,top,x+w,top+18,8,fill=col['card'] if card.overview else col['badge'],
                       outline='')
            c.create_text(x+w/2,top+9,text=b,fill=col['accent'],
                          font=( self.tv.bold.cget('family'), 8 ))
            x += w + 5
        if card.draggable:
            c.create_text(self.width-10,y+h/2,text='\u2807',fill=col['border'])#(drag handle)

    def _slot( self, event ):
        y = self.canvas.canvasy(event.y)
        return next( ( s for s in self._slots if s[0] <= y < s[1] + 6 ), None )

    def _on_menu( self, event ):
        """A menu for the card: show or remove it (as far as it allows it), or
        for the header of a group: show it as an overview"""
        tk, _ = tk_modules()
        s = self._slot(event)
        key = self.tv.group_key(s[3]) if s is not None and s[2] == 'header' else None
        if key is not None:
            #(the standard groups can be hidden):
            menu = tk.Menu(self.canvas,tearoff=0)
            menu.add_command(label='Deactivate this group',
                             command=lambda : self.tv.on_show_group(key,False))
            menu.tk_popup(event.x_root,event.y_root)
            return
        if s is None or s[2] != 'card' or not ( s[3].selectable or s[3].removable ):
            return
        card = s[3]
        menu = tk.Menu(self.canvas,tearoff=0)
        if card.selectable:
            menu.add_command(label='Show',command=lambda : self.tv.on_select_key(card.key))
        if card.removable:
            menu.add_command(label=card.remove_text or 'Remove this card',
                             command=lambda : self.tv.on_remove(card.key))
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
                self.canvas.create_line(4,s[0]-3,self.width,s[0]-3,fill=card_colors['accent'],
                                        width=3,tags='drop')

    def _on_release( self, event ):
        drag, self._drag = self._drag, None
        self.canvas.delete('drop')
        s = self._slot(event)
        if drag is not None and drag[2]:
            if s is None:
                return
            #(onto a card, or onto the header of the custom plots, before them):
            if s[2] == 'card':
                self.tv.on_drop(drag[0],s[3].key)
            elif s[2] == 'header':
                self.tv.on_drop(drag[0],None)
            return
        if s is None:
            return
        if s[2] == 'header':
            self.tv.on_group_header(s[3])
        elif s[2] == 'card' and s[3].selectable:
            self.tv.on_select_key(s[3].key)
        elif s[2] == 'add':
            self.tv.on_new_plot()
