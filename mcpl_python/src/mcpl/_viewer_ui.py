
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

"""What all front ends of the viewer show and do (so they behave the same):
the fields with their labels and keys, editing them (with checks, completions
and history), the texts of the status line, and what is printed when the
viewer is closed."""

__all__ = []

from ._stdviews import _default_groups

#The fields, in the order they are shown: (field of the Viewer, label, key,
#position of the key in the label or None if it is not in it, text shown when
#the field is empty):
fields = ( ( 'skip', 'Skip', 's', 0, '0' ),
           ( 'limit', 'Limit', 'i', 1, 'all' ),
           ( 'groups', 'Plot groups', 'c', None, ','.join(_default_groups) ),
           ( 'pick', 'Pick', 'p', 0, 'all particles' ),
           ( 'edit', 'Edit', 'e', 0, 'no changes' ),
           ( 'plot', 'Add plot', 'a', 0, 'e.g. hypot(x,y)/cm;logy' ) )
field_names = tuple( f[0] for f in fields )

#The fields chosen from a menu (see LineEditor):
menu_fields = ( 'groups', )

#The actions asking for a file name, with the label of its field:
file_prompts = { 'write' : 'Write to: ', 'state' : 'Save to: ' }

def plot_of( key ):
    """The plot (histogram string) of the view with the key: plot:PLOT for the
    plots of the standard groups, and custom:PLOT for the custom plots (see
    _viewer_groups), or None for other views (e.g. overviews)"""
    for prefix in ( 'plot:', 'custom:' ):
        if key is not None and key.startswith(prefix):
            return key[len(prefix):]
    return None

#The fields with Tab completion of names:
completing_fields = ( 'pick', 'edit', 'plot' )

def field_keys( field, tab = True ):
    """The keys of a field while it is edited (as (key, what it does)): the
    menu keys for the fields of menus, Tab for those with completion (if tab
    is set), and Up and Down for earlier texts, except in the fields of the
    file names"""
    if field in menu_fields:
        return [ ( 'Up/Down', 'choose' ), ( 'Enter', 'applies' ), ( 'Esc', 'cancels' ) ]
    res = [ ( 'Enter', 'applies' ) ]
    if tab and field in completing_fields:
        res.append( ( 'Tab', 'completes' ) )
    if field not in file_prompts:
        res.append( ( 'Up/Down', 'for earlier texts' ) )
    return res + [ ( 'Esc', 'cancels' ) ]

def field_hint( field, viewer = None ):
    """The line below the fields while the field is edited (and there is
    nothing else to show), e.g. 'Enter: apply   Esc: cancel', mentioning Tab
    completion until it was used with the viewer (see Viewer.tab_used)"""
    short = { 'applies' : 'apply', 'completes' : 'complete', 'cancels' : 'cancel',
              'for earlier texts' : 'earlier texts' }
    tab = viewer is None or not viewer.tab_used
    keys = '   '.join( f'{key}: {short.get(does,does)}' for key, does in field_keys(field,tab) )
    return f'Edits are separated by ";"   {keys}' if field == 'edit' else keys

def hint_line( editor, popup = False ):
    """The line below the fields while one is edited (with the LineEditor
    editor, or None): the completions, the message of the check, or a hint,
    as (text, style) with style 'dim' or 'error'. Tab completion is
    mentioned (after the message or hint) for the fields with expressions,
    until it was used.
    With popup, the completions are shown in a popup, and the line tells how
    to use it (else it lists them, with the chosen one in brackets)."""
    if editor is None:
        return '', 'dim'
    if editor.menu and popup:
        return field_hint(editor.field,editor.viewer), 'dim'
    if editor.choices:
        if popup:
            return 'Up/Down: choose   Enter or Tab: insert   Esc: close', 'dim'
        return '  '.join( f'[{n}]' if i == editor.selected else n
                          for i, (n, _) in enumerate(editor.choices) ), 'dim'
    if editor.replaces is not None and not editor.text.strip():
        return 'Enter: remove this plot   Esc: cancel', 'dim'
    tab = ( '  (Tab: complete)' if editor.field in completing_fields
            and not editor.viewer.tab_used else '' )
    if not editor.ok and editor.message:
        return editor.message + tab, 'error'
    if editor.hint:
        return 'hint: ' + editor.hint + tab, 'dim'
    return field_hint(editor.field,editor.viewer), 'dim'

def closing_text( viewer, option = '-w' ):
    """What is printed when the viewer (opened with the option -w or -t of
    mcpltool) is closed: the commands doing the same (writing the particles
    only if they are not just those of the file, see
    Viewer.changes_particles)"""
    c = viewer.commands(option)
    text = f'To open the viewer like this again:\n  {c["view"]}'
    if viewer.changes_particles:
        text += f'\nTo write these particles to a new file:\n  {c["extract"]}'
    return text

def editor_for( viewer, action ):
    """The LineEditor for an action (a field, 'write', 'state', or 'change' of
    the shown plot), or None if there is nothing to edit"""
    if action in field_names:
        return LineEditor(viewer,action)
    if action == 'write':
        return LineEditor(viewer,'write',viewer.suggested_filename())
    if action == 'state':
        return LineEditor(viewer,'state',viewer.suggested_state_filename())
    if action == 'change':
        key = viewer.views[viewer.current][0]
        if plot_of(key) is not None:
            return LineEditor(viewer,'plot',replaces=key)
    return None

#The functions below are the behaviour of the fields, for all front ends
#(with a LineEditor, or with the text fields of a GUI toolkit):

def check_text( viewer, field, text, replaces = None ):
    """Check of the text of a field while it is typed, as (ok, message): the
    field is a field of the viewer, a file prompt, or 'plot' with replaces
    (the key of the view of the plot changed by the text, which an empty text
    removes)"""
    if field in file_prompts:
        return bool(text.strip()), ''
    if replaces is not None and not text.strip():
        return True, ''
    return viewer.check(field,text)

def complete_text( viewer, field, text, cursor ):
    """Tab completion of the name at the cursor: (text, cursor, choices,
    start), with the name completed in the text as far as it is the same for
    all completions, and the completions to choose from if there are several
    (as (name, description), for the name starting at start)"""
    import os
    if field in file_prompts:
        return text, cursor, [], cursor
    viewer.tab_used = True
    start, cands = viewer.complete(field,text,cursor)
    if not cands:
        return text, cursor, [], start
    names = [ n for n, _ in cands ]
    common = os.path.commonprefix(names)
    if len(cands) == 1 or len(common) > cursor - start:
        insert = names[0] if len(cands) == 1 else common
        text, cursor = text[:start] + insert + text[cursor:], start + len(insert)
    return text, cursor, ( cands if len(cands) > 1 else [] ), start

class History:
    """The earlier texts of a field (none for the file prompts), shown with Up
    and Down (step -1 and 1), after which comes an empty text"""
    def __init__( self, viewer, field ):
        self._hist = [] if field in file_prompts else viewer.history(field)
        self._pos = len(self._hist)

    def step( self, delta ):
        """The text after moving delta in the history, or None if there is no
        history"""
        if not self._hist:
            return None
        self._pos = max( 0, min( len(self._hist), self._pos + delta ) )
        return self._hist[self._pos] if self._pos < len(self._hist) else ''

class LineEditor:
    """Editing of the text of a field with keys (for the front ends without
    their own text fields): characters, Left, Right, Home, End, Backspace,
    Delete, Tab (completion), Up and Down (earlier texts), Enter (apply) and
    Esc (cancel). The text is checked after each change (ok and message).
    The fields of menu_fields are a menu instead: Up and Down choose, Enter
    applies and Esc cancels."""
    def __init__( self, viewer, field, text = None, replaces = None ):
        #(replaces: the key of the view of the plot changed by the text of a
        #plot field, which removes it when empty):
        self.viewer, self.field, self.replaces = viewer, field, replaces
        self.text = ( plot_of(replaces) if replaces is not None else
                      viewer.field_text(field) if text is None else text )
        self.cursor = len(self.text)
        self._hist = History(viewer,field)
        self.choices = []#(completions shown, when Tab gives several)
        self.selected = 0#(index of the chosen one)
        self.choice_start = 0#(position in the text of the name they complete)
        #Fields with few values are a menu of them (choices, which Enter applies):
        self.menu = field in menu_fields
        if self.menu:
            self.choices = viewer.complete(field,'')[1]
            names = [ name for name, _ in self.choices ]
            self.selected = names.index(self.text) if self.text in names else 0
        self._recheck()

    def _recheck( self ):
        self.ok, self.message = check_text(self.viewer,self.field,self.text,self.replaces)

    @property
    def hint( self ):
        if self.field in file_prompts:
            return None
        return self.viewer.hint(self.field,self.text,self.cursor)

    def key( self, key ):
        """Handle a key: returns 'apply', 'cancel' or None. While completions
        are shown, Up and Down choose one, Enter and Tab insert it, and Esc
        closes them."""
        t, c = self.text, self.cursor
        if self.menu:
            if key in ( 'Up', 'Down' ):
                self.selected = ( self.selected + ( -1 if key == 'Up' else 1 ) ) % len(self.choices)
            elif key == 'Enter':
                self.text = self.choices[self.selected][0]
                self._recheck()
                return 'apply'
            elif key == 'Esc':
                return 'cancel'
            return None
        if self.choices:
            if key in ( 'Up', 'Down' ):
                n = len(self.choices)
                self.selected = ( self.selected + ( -1 if key == 'Up' else 1 ) ) % n
                return None
            if key in ( 'Enter', 'Tab' ):
                name = self.choices[self.selected][0]
                self.text = t[:self.choice_start] + name + t[c:]
                self.cursor = self.choice_start + len(name)
                self.choices = []
                self._recheck()
                return None
            if key == 'Esc':
                self.choices = []
                return None
        if key == 'Enter':
            return 'apply'
        if key == 'Esc':
            return 'cancel'
        self.choices = []
        if key == 'Left':
            self.cursor = max( 0, c - 1 )
        elif key == 'Right':
            self.cursor = min( len(t), c + 1 )
        elif key == 'Home':
            self.cursor = 0
        elif key == 'End':
            self.cursor = len(t)
        elif key == 'Backspace':
            if c > 0:
                self.text, self.cursor = t[:c-1] + t[c:], c - 1
        elif key == 'Delete':
            self.text = t[:c] + t[c+1:]
        elif key in ( 'Up', 'Down' ):
            text = self._hist.step( -1 if key == 'Up' else 1 )
            if text is not None:
                self.text, self.cursor = text, len(text)
        elif key == 'Tab':
            self.text, self.cursor, choices, start = complete_text(self.viewer,self.field,
                                                                   self.text,self.cursor)
            if choices:
                self.choices, self.selected, self.choice_start = choices, 0, start
        elif isinstance(key,str) and len(key) == 1 and ' ' <= key <= '~':
            self.text, self.cursor = t[:c] + key + t[c:], c + 1
        else:
            return None
        self._recheck()
        return None

#Numbers in the texts of the viewers:

def count_text( n, compact = False ):
    """A number (of particles) as a text with thousands separators, like
    1,006,000, or if compact in the short form of round numbers, like 1e6 or
    2.5e6, where it is exact and shorter"""
    text = f'{n:,}'
    if compact and n >= 1e5:
        mantissa, exponent = f'{n:e}'.split('e')
        short = f'{float(mantissa):g}e{int(exponent)}'
        if float(short) == n and len(short) < len(text):
            return short
    return text

def number_text( x ):
    """A number (like a sum of weights) as a text: whole numbers as for
    count_text, others with 6 significant digits"""
    if float(x).is_integer() and abs(x) < 1e15:
        return count_text(int(x))
    return f'{x:.6g}'

#The particles kept in memory by the viewer (see Viewer.cache_info), with the
#button and the menu of the viewers with windows:

#The cache limits offered (in bytes, None for no cache):
cache_presets = ( 5e6, 20e6, 100e6, 500e6, 2e9, 5e9, 10e9, None )

#The cache limit (in bytes) unless one is chosen:
default_cache_limit = 500e6

def used_particles( n, size, limit ):
    """The number of particles the plots use, of the n particles of the range
    (of size bytes each), with the cache limit (in bytes, or None for no
    cache): all if they fit, else those which fit (at least one)"""
    if limit is None or n * size <= limit:
        return n
    return max( 1, int( limit // size ) )

