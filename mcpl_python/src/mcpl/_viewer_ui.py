
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
the fields with their labels and keys, the other actions, the texts of the
status line, the help text, and what is printed when the viewer is closed."""

__all__ = []

#The fields, in the order they are shown: (field of the Viewer, label, key,
#position of the key in the label, text shown when the field is empty):
fields = ( ( 'skip', 'Skip', 's', 0, '0' ),
           ( 'limit', 'Limit', 'i', 1, 'all' ),
           ( 'collection', 'Plot collection', 'c', 5, 'default' ),
           ( 'pick', 'Pick', 'p', 0, 'all particles' ),
           ( 'edit', 'Edit', 'e', 0, 'no changes' ),
           ( 'plot', 'Add plot', 'a', 0, 'e.g. hypot(x,y)/cm;logy' ) )

#What the fields are, for the hover texts:
field_descriptions = {
    'skip' : 'the number of particles at the start of the file which are left out',
    'limit' : 'the largest number of particles to use, after those skipped',
    'collection' : 'the plots to start from, for some uses',
    'pick' : 'an expression which is true for the particles to use',
    'edit' : 'statements which change the particles, after they are picked',
    'plot' : 'a histogram string of a new plot',
}

#The fields shown on the same line (the short ones together):
field_rows = ( ( 'skip', 'limit', 'collection' ), ( 'pick', ), ( 'edit', ), ( 'plot', ) )
assert [ f for row in field_rows for f in row ] == [ f[0] for f in fields ]

#The fields chosen from a menu (see LineEditor):
menu_fields = ( 'collection', )

#The other actions: (action, label, keys, position of the key in the label):
actions = ( ( 'write', 'Write file...', ( 'w', ), 0 ),
            ( 'state', 'Save viewer state...', ( 'v', ), 5 ),
            ( 'help', 'Help', ( 'h', '?', 'F1' ), 0 ),
            ( 'quit', 'Quit', ( 'q', ), 0 ) )

#The actions of the terminal only (as the others, shown after them):
terminal_actions = ( ( 'gui_plot', 'Open plot in GUI', ( 'o', ), 0 ),
                     ( 'gui_viewer', 'GUI viewer', ( 'g', ), 0 ) )

#The keys of the terminal for log scales of the shown plot (in windows, the
#keys of matplotlib do this):
scale_keys = { 'l' : 'logy', 'k' : 'logx' }

#The actions asking for a file name, with the label of its field:
file_prompts = { 'write' : 'Write to: ', 'state' : 'Save to: ' }

#Keys of the views (in addition to clicking on them), as given by the front
#ends: MoveUp and MoveDown are Up and Down with Shift, Ctrl, Alt or the
#Windows/Command key (any of them, as window managers take some):
view_keys = { 'Up' : 'previous', 'Down' : 'next', 'MoveUp' : 'move_up',
              'MoveDown' : 'move_down' }

def key_action( key, terminal = False ):
    """The action (or field to edit) of a key outside the fields (as given by
    the front end: a character, or 'Up', 'Down', 'MoveUp', 'MoveDown', 'Enter'
    or 'F1'), or None (with the actions of the terminal if terminal is set)"""
    if key in view_keys:
        return view_keys[key]
    if key == 'Enter':
        return 'change'#(of the shown plot)
    if len(key) == 1:
        key = key.lower()#(the keys of letters work with Shift or Caps Lock too)
    for f, _, k, _, _ in fields:
        if key == k:
            return f
    for a, _, keys, _ in actions + ( terminal_actions if terminal else () ):
        if key in keys:
            return a
    return None

def field_label( field ):
    for f, label, _, _, _ in fields:
        if f == field:
            return label
    raise KeyError(field)

def shortcut_text( name ):
    """Text of the status line when the mouse is over a field or action"""
    for f, label, k, _, _ in fields:
        if f == name:
            return ( f'{label}: {field_descriptions[f]} (key {k};'
                     f' {", ".join( f"{key} {does}" for key, does in field_keys(f) )})' )
    for a, label, keys, _ in actions + terminal_actions:
        if a == name:
            return f'{label.rstrip(".")}: press {" or ".join(keys)}'
    if name == 'new_plot':#(the button of the viewers with windows)
        return 'New plot: press a'
    if name == 'views':
        return 'Views: click on one, or press Up and Down (with Shift, Ctrl or Alt to move the plot)'
    if name == 'panel':
        return 'Click to show this plot on its own'
    return ''

#The settings of the shown plot in the viewers with windows (see
#WidgetViewer.plot_controls), for 1D histograms, bar charts and 2D histograms:
#(option, label, choices), with the choices as (shown text, value of the
#option: None if it is not given, True if it is given without a value), or
#None for a text field:
_scale = ( ( 'linear', None ), ( 'log', True ), ( 'auto', 'auto' ) )
_count = ( 'unweighted', 'Count', ( ( 'weights', None ), ( 'particles', True ) ) )
plot_controls = {
    '1d' : ( ( 'logx', 'X axis', _scale ), ( 'logy', 'Y axis', _scale ),
             ( 'split', 'Split by', ( ( 'none', None ), ( 'particle type', 'pdgcode' ) ) ),
             _count, ( 'bins', 'Bins', None ), ( 'range', 'Range', None ) ),
    'bar' : ( ( 'logy', 'Scale', _scale ), _count, ( 'bar', 'Bars', None ) ),
    '2d' : ( _count, ( 'bins', 'Bins', None ), ( 'xrange', 'X range', None ),
             ( 'yrange', 'Y range', None ) ),
}

#The quantities offered when adding a plot in the viewers with windows (as the
#start of a histogram string), besides any expression:
quantities = ( ( 'Energy', 'ekin;logx=auto' ), ( 'Wavelength', 'wavelength' ),
               ( 'Time', 'time;logx=auto' ), ( 'Position x', 'x' ), ( 'Position y', 'y' ),
               ( 'Position z', 'z' ), ( 'Direction x', 'ux' ), ( 'Direction y', 'uy' ),
               ( 'Direction z', 'uz' ), ( 'Angle to the z axis', 'angle_to(0,0,1)/deg' ),
               ( 'Distance from the z axis', 'hypot(x,y)' ), ( 'Weight', 'weight' ),
               ( 'Particle types', 'pdgcode;bar' ), ( 'User flags', 'userflags;bar' ) )

#The fields with Tab completion of names:
completing_fields = ( 'pick', 'edit', 'plot' )

def field_keys( field ):
    """The keys of a field while it is edited (as (key, what it does)): the
    menu keys for the fields of menus, Tab for those with completion, and Up
    and Down for earlier texts, except in the fields of the file names"""
    if field in menu_fields:
        return [ ( 'Up/Down', 'choose' ), ( 'Enter', 'applies' ), ( 'Esc', 'cancels' ) ]
    res = [ ( 'Enter', 'applies' ) ]
    if field in completing_fields:
        res.append( ( 'Tab', 'completes' ) )
    if field not in file_prompts:
        res.append( ( 'Up/Down', 'for earlier texts' ) )
    return res + [ ( 'Esc', 'cancels' ) ]

def field_hint( field ):
    """The line below the fields while the field is edited (and there is
    nothing else to show), e.g. 'Enter: apply   Esc: cancel'"""
    short = { 'applies' : 'apply', 'completes' : 'complete', 'cancels' : 'cancel',
              'for earlier texts' : 'earlier texts' }
    return '   '.join( f'{key}: {short.get(does,does)}' for key, does in field_keys(field) )

def hint_line( editor, popup = False ):
    """The line below the fields while one is edited (with the LineEditor
    editor, or None): the completions, the message of the check, or a hint,
    as (text, style) with style 'dim' or 'error'. Tab completion is always
    mentioned (after the message or hint) for the fields with expressions.
    With popup, the completions are shown in a popup, and the line tells how
    to use it (else it lists them, with the chosen one in brackets)."""
    if editor is None:
        return '', 'dim'
    if editor.menu and popup:
        return field_hint(editor.field), 'dim'
    if editor.choices:
        if popup:
            return 'Up/Down: choose   Enter or Tab: insert   Esc: close', 'dim'
        return '  '.join( f'[{n}]' if i == editor.selected else n
                          for i, (n, _) in enumerate(editor.choices) ), 'dim'
    if editor.replaces is not None and not editor.text.strip():
        return 'Enter: remove this plot   Esc: cancel', 'dim'
    tab = '  (Tab: complete)' if editor.field in completing_fields else ''
    if not editor.ok and editor.message:
        return editor.message + tab, 'error'
    if editor.hint:
        return 'hint: ' + editor.hint + tab, 'dim'
    return field_hint(editor.field), 'dim'

help_text = '''\
The viewer shows the particles of an MCPL file: an overview with the first
plots, and each plot on its own. The plots are histograms of expressions (as
for -H), which can be changed, removed and reordered, and further ones added.
Plots are updated while the file is read, and are complete when the reading
is done.

Keys:
  Up, Down     Show the previous or next view (or click on a view).
  Shift+Up, Shift+Down
               Move the shown plot up or down (also with Ctrl, Alt or the
               Windows or Command key instead of Shift).
  PgUp, PgDn   Scroll plots which are taller than the window (in the
               terminal).
  s, i         Skip particles at the start of the file, or limit the number
               of particles used (like the -s and -l options).
  p            Pick particles with an expression, e.g. pdgcode == neutron and
               ekin < 1MeV (like -p, see mcpltool -p help).
  e            Edit the particles, e.g. z += 1cm;weight *= 0.5 (like -E, see
               mcpltool -E help). The particles are picked before they are
               edited.
  a            Add a plot of an expression, with options as for -H, e.g.
               hypot(x,y)/cm;logy (see mcpltool -H help).
  c            Choose the collection of plots to start from, e.g. beamz for a
               beam along the z axis (added plots are kept).
  Enter        Change the shown plot (an empty text removes it).
  w            Write the picked and edited particles to a new file.
  v            Save the state of the viewer (the settings and plots) in a
               file, which -wFILE.json (or --view=FILE.json) opens again.
  l, k         Log or linear scale of the y or x axis of the plot (in a GUI
               window, of the plot under the mouse, as in matplotlib).
  o            Open the plot in a GUI window (in the terminal; the window
               shows the plot as it is, and stays open).
  g            Open the viewer in a GUI window, in the same state (in the
               terminal; it stays open, and the terminal viewer goes on).
  h, ?, F1     Show this help.
  q            Quit (the commands doing the same are then printed).

In the fields: Enter applies the text, Tab completes names, Up and Down show
earlier texts, and Esc cancels. Texts are checked while they are typed. When
Tab shows several completions, Up and Down choose one, Enter or Tab inserts
it, and Esc closes them.'''

#Shown in Jupyter without the ipympl backend of matplotlib:
no_widget_text = ( 'For interactive plots (zoom, pan, and clicking the plots of'
                   ' the overview), install ipympl and run %matplotlib widget'
                   ' before mcpl.view.' )

def closing_text( viewer ):
    """What is printed when the viewer is closed: the commands doing the same
    (writing the particles only if some were picked or edited)"""
    c = viewer.commands()
    text = f'To open the viewer like this again:\n  {c["view"]}'
    if viewer.field_text('pick') or viewer.field_text('edit'):
        text += f'\nTo write the picked and edited particles to a file:\n  {c["extract"]}'
    return text

def labelled( label, keypos ):
    """The label split into the parts before, at and after the shortcut key
    (for highlighting the key)"""
    return label[:keypos], label[keypos:keypos+1], label[keypos+1:]

def popup_rows( editor, maxrows ):
    """The completions shown in a popup with at most maxrows lines (scrolled
    to the chosen one): (index of the first, number shown)"""
    n = len(editor.choices)
    rows = max( 1, min( n, maxrows ) )
    return min( max( 0, editor.selected - rows + 1 ), n - rows ), rows

def editor_for( viewer, action ):
    """The LineEditor for an action (a field, 'write', 'state', or 'change' of
    the shown plot), or None if there is nothing to edit"""
    if action in ( 'skip', 'limit', 'pick', 'edit', 'collection', 'plot' ):
        return LineEditor(viewer,action)
    if action == 'write':
        return LineEditor(viewer,'write',viewer.suggested_filename())
    if action == 'state':
        return LineEditor(viewer,'state',viewer.suggested_state_filename())
    if action == 'change':
        key = viewer.views[viewer.current][0]
        if key.startswith('plot:'):
            return LineEditor(viewer,'plot',replaces=key[5:])
    return None

#The functions below are the behaviour of the fields, for all front ends
#(with a LineEditor, or with the text fields of a GUI toolkit):

def check_text( viewer, field, text, replaces = None ):
    """Check of the text of a field while it is typed, as (ok, message): the
    field is a field of the viewer, a file prompt, or 'plot' with replaces
    (the plot changed by the text, which an empty text removes)"""
    if field in file_prompts:
        return bool(text.strip()), ''
    if replaces is not None and not text.strip():
        return True, ''
    return viewer.check(field,text)

def apply_text( viewer, field, text, replaces = None ):
    """Apply the text of a field (see check_text): (done, message, replot),
    where done tells whether it was applied, message is to be shown (an error,
    or the result of writing a file) and replot whether the plots changed"""
    if field == 'write':
        ok, msg = viewer.try_write(text.strip())
        return ok, msg if ok else f'Not written: {msg}', False
    if field == 'state':
        ok, msg = viewer.try_save_state(text.strip())
        return ok, msg if ok else f'Not saved: {msg}', False
    if replaces is not None:
        ok, msg = viewer.change_plot(replaces,text)
    else:
        ok, msg = viewer.set(field,text)
    return ok, msg, ok

def complete_text( viewer, field, text, cursor ):
    """Tab completion of the name at the cursor: (text, cursor, choices,
    start), with the name completed in the text as far as it is the same for
    all completions, and the completions to choose from if there are several
    (as (name, description), for the name starting at start)"""
    import os
    if field in file_prompts:
        return text, cursor, [], cursor
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

def apply_editor( viewer, editor ):
    """Apply the text of the editor (Enter), see apply_text"""
    return apply_text(viewer,editor.field,editor.text,editor.replaces)

class LineEditor:
    """Editing of the text of a field with keys (for the front ends without
    their own text fields): characters, Left, Right, Home, End, Backspace,
    Delete, Tab (completion), Up and Down (earlier texts), Enter (apply) and
    Esc (cancel). The text is checked after each change (ok and message)."""
    def __init__( self, viewer, field, text = None, replaces = None ):
        #(replaces: the added plot changed by the text of a plot field, which
        #removes it when empty):
        self.viewer, self.field, self.replaces = viewer, field, replaces
        self.text = ( replaces if replaces is not None else
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

