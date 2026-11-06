
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

from ._helptext import plain_text
from ._stdviews import _default_groups, _field_titles

#The fields, in the order they are shown: (field of the Viewer, label, key,
#position of the key in the label or None if it is not in it, text shown when
#the field is empty):
fields = ( ( 'skip', 'Skip', 's', 0, '0' ),
           ( 'limit', 'Limit', 'i', 1, 'all' ),
           ( 'groups', 'Plot groups', 'c', None, ','.join(_default_groups) ),
           ( 'edit', 'Edit', 'e', 0, 'all particles, no changes' ),
           ( 'plot', 'Add plot', 'a', 0, 'e.g. hypot(x,y)/cm;logy' ) )
field_names = tuple( f[0] for f in fields )

#What the fields are, for the hover texts:
field_descriptions = {
    'skip' : 'the number of particles at the start of the file which are left out',
    'limit' : 'the largest number of particles to use, after those skipped',
    'groups' : 'the groups of plots shown, chosen from a menu',
    'edit' : ( 'statements separated by ";", executed in order: filter conditions keeping'
               ' the particles for which they are true, and changes of the particles' ),
    'plot' : 'a histogram string of a new plot',
}

#The fields shown on the same line (the short ones together):
field_rows = ( ( 'skip', 'limit', 'groups' ), ( 'edit', ), ( 'plot', ) )
assert [ f for row in field_rows for f in row ] == [ f[0] for f in fields ]

#The fields chosen from a menu (see LineEditor):
menu_fields = ( 'groups', )

#The other actions: (action, label, keys, position of the key in the label):
actions = ( ( 'write', 'Write file...', ( 'w', ), 0 ),
            ( 'state', 'Save viewer state...', ( 'v', ), 5 ),
            ( 'help', 'Help', ( 'h', '?', 'F1' ), 0 ),
            ( 'quit', 'Quit', ( 'q', ), 0 ) )

#The actions of the terminal only (as the others, shown after them):
terminal_actions = ( ( 'gui_plot', 'Open plot in GUI', ( 'o', ), 0 ),
                     ( 'gui_viewer', 'GUI viewer', ( 'g', ), 0 ) )

#The keys for log scales of the shown plot (as the keys of matplotlib):
scale_keys = { 'l' : 'logy', 'k' : 'logx' }

#The actions asking for a file name, with the label of its field:
file_prompts = { 'write' : 'Write to: ', 'state' : 'Save to: ' }

#Keys of the views (in addition to clicking on them), as given by the front
#ends: MoveUp and MoveDown are Up and Down with Shift, Ctrl, Alt, or the
#Windows/Command key (any of them, as window managers take some):
view_keys = { 'Up' : 'previous', 'Down' : 'next', 'MoveUp' : 'move_up',
              'MoveDown' : 'move_down' }

def key_action( key, terminal = False ):
    """The action (or field to edit) of a key outside the fields (as given by
    the front end: a character, or 'Up', 'Down', 'MoveUp', 'MoveDown', 'Enter',
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

def shortcut_text( name ):
    """Text (of the status line or tooltip) when the mouse is over a field or action"""
    for f, label, k, _, _ in fields:
        if f == name:
            return ( f'{label}: {field_descriptions[f]} (key {k};'
                     f' {", ".join( f"{key} {does}" for key, does in field_keys(f) )})' )
    for a, label, keys, _ in actions + terminal_actions:
        if a == name:
            return f'{label.rstrip(".")}: press {" or ".join(keys)}'
    return tips.get(name,'')

#The tooltips of the buttons and other parts of the viewers with windows (see
#shortcut_text):
tips = {
    'menu' : 'Menu: open another file, save the viewer state, and quit (press m)',
    'help_menu' : 'Help: the viewer, the expressions, the cache, and MCPL (press h)',
    'new_plot' : 'New plot: press a',
    'remove_plot' : 'Remove plot: remove the shown plot from the custom plots',
    'plot_code' : ( 'Show plot code: the command of mcpltool, and the Python code, making the'
                    ' shown plot' ),
    'apply' : 'Apply what is typed (or press Enter)',
    'examples' : 'Examples of plot expressions, which can be used in the field',
    'write_code' : ( 'Show code: the command of mcpltool, and the Python, C++, and C code,'
                     ' writing the edited particles to a new file' ),
    'compose' : ( 'Open Composer: build the edit part by part with menus (filter'
                  ' conditions, changes, rotations, or aligning), seeing the particles left'
                  ' after each part (press c)' ),
    'views' : 'Groups of plots: click on one to show its overview, or press Up and Down',
    'back' : 'Back to the overview: press b, or right-click the plot',
    'panel' : 'Click to show this plot on its own (right click: its menu)',
    'cache' : ( 'Cache: the memory for the particles which are read, which decides how'
                ' many of them the plots use (click to change it)' ),
    'advanced' : ( 'Advanced: show the plot expression instead of the axes and settings'
                   ' (the histogram string of the plot, which has them all)' ),
    'most' : 'Show the variables with the strongest correlations, or all of them again',
    'line_on' : 'Use this part (parts switched off are kept, but not used)',
    'line_up' : 'Move this part up',
    'line_down' : 'Move this part down',
    'line_delete' : 'Delete this part',
    'add_line' : 'Add a new part at the end (press Alt+A)',
    'line_kind' : 'What this part does: a filter condition, a change, a rotation, aligning, a variable, or an expression typed in',
    'compose_apply' : 'Apply the parts to the edit (or press Enter in a part)',
    'compose_help' : 'How to write the statements of edits, with examples',
    'close' : 'Close the window (what is not applied is kept for the next time)',
    'copy' : 'Copy this to the clipboard',
    'browse' : 'Choose the name of the file in a file dialog',
    'write_open' : 'Write the file, and show it in the viewer',
    'details' : 'The help of these expressions (press m)',
}

#The look of the viewers with windows (for toolkits with colours): the
#colours of the line of messages and of the marks of the checks, of the
#highlighted code (see _viewer_code.highlight), of the cards of the views (see
#WindowLogic.cards, where the shown card is marked in the accent colour),
#and of the parts below the plot (that of the shown plot, tinted, and that of
#the edit):
colors = { 'normal' : 'black', 'dim' : '#777777', 'ok' : '#2ca02c', 'error' : '#d62728',
           'filling' : '#9467bd', 'tooltip' : '#ffffe8' }
code_styles = { 'comment' : { 'foreground' : '#6a737d' },
                'string' : { 'foreground' : '#067d17' },
                'keyword' : { 'foreground' : '#0033b3' },
                'number' : { 'foreground' : '#1750eb' },
                'preprocessor' : { 'foreground' : '#9e5b00' },
                'option' : { 'foreground' : '#871094' } }
card_colors = { 'bg' : '#eef1f5', 'card' : '#ffffff', 'selected' : '#e2ebf6',
                'border' : '#d5dbe3', 'accent' : '#2f5f8f', 'text' : '#1d2733',
                'dim' : '#7a8594', 'badge' : '#dfe7f1', 'overview' : '#d3e0ef',
                'stack' : '#b9c9dc' }
part_colors = { 'Plot' : card_colors['selected'], 'Particles' : card_colors['bg'] }
#(the colour of the thicker line around what edits the particles, the part of
#the edit and the Composer: a slate blue of the MCPL logo):
edit_color = '#6e87a4'

#The settings of the shown plot in the viewers with windows (see
#WindowLogic.plot_controls), for 1D histograms, bar charts, and 2D histograms:
#(option, label, choices), with the choices as (shown text, value of the
#option: None if it is not given, True if it is given without a value), or
#None for a text field:
_scale = ( ( 'linear', None ), ( 'log', True ), ( 'auto', 'auto' ) )
_count = ( 'unweighted', 'Count', ( ( 'weights', None ), ( 'particles', True ) ) )
#(the particle types of the file, see WindowLogic.type_choices):
_only = ( 'display_edit', 'Display edit', 'types' )
#(a curve of each particle type by default, see _histstring._display_by, or
#of each value of an expression written in the menu):
display_by_choices = ( ( 'particle type', None ), ( 'single', 'single' ) )
_by = ( 'display_by', 'Display by', display_by_choices )
#(the settings of plots in whose menus an expression can be written, with the
#choice for it, its hint, and the field whose completions and hints it has):
written_options = {
    'display_by' : ( 'Type expression...', ( 'Type what to show a curve of each value of,'
                                             ' e.g. x > 0cm or userflags, and press Enter' ),
                     'plot' ),
    'display_edit' : ( 'Type expression...', ( 'Type an edit of the particles shown,'
                                               ' e.g. ekin > 1MeV, and press Enter' ), 'edit' ) }
plot_controls = {
    '1d' : ( ( 'logx', 'X scale', _scale ), ( 'logy', 'Y scale', _scale ), _by,
             _count, ( 'bins', 'Bins', None ), ( 'range', 'Range', None ), _only ),
    'bar' : ( ( 'logy', 'Scale', _scale ), _count, ( 'bar', 'Bars', None ), _only ),
    '2d' : ( ( 'logz', 'Colour scale', ( ( 'log', None ), ( 'linear', '0' ) ) ),
             ( 'equal', 'Aspect', ( ( 'auto', None ), ( 'equal', True ) ) ), _count,
             ( 'bins', 'Bins', None ), ( 'xrange', 'X range', None ),
             ( 'yrange', 'Y range', None ), _only ),
    '3d' : ( _by, ( 'unweighted', 'Sample by', ( ( 'weights', None ), ( 'particles', True ) ) ),
             ( 'points', 'Points', None ), _only ),
}

def quantity_plot( text ):
    """The start of a plot string for one of the quantities (see quantities),
    given as its name or its expression (e.g. Energy or ekin for
    ekin;logx=auto), or the text itself for other expressions"""
    t = text.strip()
    return next( ( p for name, p in quantities if t in ( name, p.split(';')[0] ) ), t )

#(the options which are on unless given as 0, like the logarithmic colour
#scale of 2D histograms):
on_by_default = ( 'logz', )

#The quantities offered when adding a plot in the viewers with windows (as the
#start of a histogram string), besides any expression:
#(the titles of fields, as in the cards, see _stdviews._field_titles):
quantities = tuple( ( title or _field_titles[p.split(';')[0]], p ) for title, p in (
    ( None, 'ekin;logx=auto' ), ( None, 'wavelength;logx=auto' ), ( None, 'time;logx=auto' ),
    ( None, 'x' ), ( None, 'y' ), ( None, 'z' ), ( None, 'ux' ), ( None, 'uy' ), ( None, 'uz' ),
    ( 'Angle to z axis', 'angle(dir,(0,0,1))/deg' ), ( 'Distance to z axis', 'hypot(x,y)' ),
    ( None, 'weight' ), ( None, 'pdgcode;bar' ), ( None, 'userflags;bar' ) ) )

#(the choices of quantities in menus, as (text, expression)):
#(the first line of the lists of the axes, saying that they also take
#expressions, which only puts the cursor in the field when chosen):
axis_hint = 'or type any expression, like ekin/meV or x/cm + y/cm'
quantity_choices = tuple( ( f'{name}:  {p.split(";")[0]}', p.split(';')[0] )
                          for name, p in quantities )

#(where the groups of plots are chosen, in the viewers with windows):
groups_hint = ( 'The groups of plots are in the list of plots: the inactive ones (in grey)'
                ' are activated with a click' )

#The titles of the examples of expressions (see _exprhelp.examples), and the
#topics of the examples of the fields:
example_titles = { 'edit' : 'Examples of edits', 'hist' : 'Examples of plot expressions' }
example_topics = { 'edit' : 'edit', 'shown_plot' : 'hist' }
#(the titles of their help, see WindowLogic.help_topics):
help_titles = { 'edit' : 'Edit expressions', 'hist' : 'Plot expressions' }

def group_of( key ):
    """The key of the group of the view with the key if it is an overview
    (overview:GROUP), else None"""
    return key[9:] if key is not None and key.startswith('overview:') else None

def plot_of( key ):
    """The plot (histogram string) of the view with the key: plot:PLOT for the
    plots of the standard groups, and custom:PLOT for the custom plots (see
    _viewer_groups), or None for other views (e.g. overviews)"""
    for prefix in ( 'plot:', 'custom:' ):
        if key is not None and key.startswith(prefix):
            return key[len(prefix):]
    return None

#The fields with Tab completion of names:
completing_fields = ( 'edit', 'plot' )

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
    return f'Statements are separated by ";"   {keys}' if field == 'edit' else keys

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

#The help of the viewer, as blocks (see _helptext), and as plain text:
help_blocks = (
    ( 'text', '''The viewer shows the particles of an MCPL file in groups of plots (in windows
with an overview of each group: its plots together, or a correlation plot of
the fields). The plots are histograms of expressions (as for
mcpltool -H). New plots are added to the custom group, where they can be changed,
removed, and reordered (changing a plot of the other groups copies it there).
Plots are updated while the file is read, and are complete when the reading
is done.''' ),
    ( 'gap', ),
    ( 'section', 'Keys' ),
    ( 'key', 'Up, Down', ( 'Show the previous or next view (in windows: the previous or next'
      ' group, or plot of the overview of the shown plot).' ) ),
    ( 'key', 'b', ( 'Back to the overview of the shown plot (in windows, where plots are shown'
      ' by clicking on them in the overviews of their groups, a right click on the plot does'
      ' the same).' ) ),
    ( 'key', 'Shift+Up, Shift+Down', ( 'Move the shown plot up or down (in the terminal, also'
      ' with Ctrl, Alt or the Windows or Command key instead of Shift; in windows, with the menu'
      ' of the plot in its overview: right click).' ) ),
    ( 'key', 'PgUp, PgDn', 'Scroll plots which are taller than the window (in the terminal).' ),
    ( 'key', 's, i', ( 'Skip particles at the start of the file, or limit the number of particles'
      ' used (like the -s and -l options).' ) ),
    ( 'key', 'e', ( 'Edit the particles with statements executed in order, keeping those for'
      ' which filter conditions are true and changing them, e.g. pdgcode == neutron; z += 1cm (like'
      ' -e, see mcpltool -e help).' ) ),
    ( 'key', 'a', ( 'Add a plot of an expression, with options as for mcpltool -H, e.g.'
      ' hypot(x,y)/cm;logy (see mcpltool --hist-help).' ) ),
    ( 'key', 'c', ( 'Choose the group of plots shown, from a menu (in windows, groups are'
      ' activated in the list of plots). The custom plots are kept.' ) ),
    ( 'key', 'Enter', 'Change the shown plot (an empty text removes a custom plot).' ),
    ( 'key', 'w', ( 'Write the edited particles to a new file (compressed if its'
                    ' name ends with .mcpl.gz). An existing file is only overwritten after'
                    ' asking.' ) ),
    ( 'key', 'v', ( 'Save the state of the viewer (the settings and plots) in a file, which'
      ' mcpltool -w FILE.json FILE (or -t FILE.json FILE) opens again.' ) ),
    ( 'key', 'l, k', ( 'Log or linear y or x axis of the plot: its option logy or logx (in the'
      ' overview of a GUI window, of the plot under the mouse).' ) ),
    ( 'key', 'o', ( 'Open the plot in a GUI window (in the terminal; the window shows the plot'
      ' as it is, and stays open).' ) ),
    ( 'key', 'g', ( 'Open the viewer in a GUI window, in the same state (in the terminal; it'
      ' stays open, and the terminal viewer goes on).' ) ),
    ( 'key', 'h, ?, F1', 'Show this help.' ),
    ( 'key', 'q', 'Quit (the commands doing the same are then printed).' ),
    ( 'gap', ),
    ( 'text', '''In the fields: Enter applies the text, Tab completes names, Up and Down show
earlier texts, and Esc cancels. In the window, a changed text is also applied
with its Apply button, or by clicking elsewhere in the window. Texts are
checked while they are typed. When Tab shows several completions, Up and Down
choose one, Enter or Tab inserts it, and Esc closes them.''' ),
)
help_text = plain_text(help_blocks)

def closing_text( viewer, option = '-w' ):
    """What is printed when the viewer (opened with the option -w or -t of
    mcpltool) is closed: the command opening it again with the same state"""
    return f'Command to launch viewer with same state:\n\n  {viewer.commands(option)["view"]}\n'

def labelled( label, keypos ):
    """The label split into the parts before, at, and after the shortcut key
    (for highlighting the key; the key part is empty for keypos None)"""
    if keypos is None:
        return label, '', ''
    return label[:keypos], label[keypos:keypos+1], label[keypos+1:]

def label_segments( label, keypos ):
    """The label of a field as segments (text, style), with its shortcut key
    in the style 'key', followed by ': '"""
    a, b, c = labelled(label,keypos)
    return [ ( a, 'normal' ), ( b, 'key' ), ( c + ': ', 'normal' ) ]

def action_button( label, keypos ):
    """The button of an action (in the viewers drawn as text), as segments
    (text, style), like [Write], with its shortcut key in the style 'key'"""
    a, b, c = labelled(label,keypos)
    return [ ( '[' + a, 'normal' ), ( b, 'key' ), ( c + ']', 'normal' ) ]

def popup_lines( editor, maxrows ):
    """The lines of the popup of the completions of the editor (see popup_rows):
    (index of the first shown, the texts of the completions shown, as the
    name and its description, and the count, like 3/40, or None if all are
    shown)"""
    first, rows = popup_rows(editor,maxrows)
    choices = editor.choices
    nw = max( len(name) for name, _ in choices )
    texts = [ name.ljust(nw) + '  ' + ( descr or '' ) for name, descr in choices[first:first+rows] ]
    count = f'{editor.selected+1}/{len(choices)}' if rows < len(choices) else None
    return first, texts, count

def popup_rows( editor, maxrows ):
    """The completions shown in a popup with at most maxrows lines (scrolled
    to the chosen one): (index of the first, number shown)"""
    n = len(editor.choices)
    rows = max( 1, min( n, maxrows ) )
    return min( max( 0, editor.selected - rows + 1 ), n - rows ), rows

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

class KeyViewer:
    """What the viewers used with keys (in the terminal, and on matplotlib
    figures) have in common: the field being edited (a LineEditor, or None),
    the message shown in the status line (with its style, see set_message),
    whether the help is shown, and the handling of keys: by the field being
    edited (see editor_key), the keys of log scales (see scale_key), and the
    actions of key_action (see do). The front ends draw the viewer."""
    def __init__( self, viewer ):
        self.v = viewer
        self.editor = None
        self.overwrite = False#(whether the editor asks to overwrite a file)
        self.message, self.message_style = '', 'normal'
        self.hover = None
        self.show_help = False

    def status_text( self, hover ):
        """The text of the status line: the message, or else the shortcut of
        what is under the mouse (the hover, a field or action, 'views', or
        'panel'), if any"""
        return self.message or ( shortcut_text(hover) if hover is not None else '' )

    def set_message( self, text, ok = True ):
        """Show the message (in the style of errors unless ok)"""
        self.message, self.message_style = text, 'normal' if ok else 'error'

    def view_changed( self ):
        """Called when another view is shown, or the plots changed"""

    def editor_key( self, k ):
        """Give the key k to the field being edited (Enter applies it, and Esc
        ends the editing): whether the plots changed. A file prompt which would
        overwrite a file first asks (y applies it, other keys continue the
        editing)."""
        confirmed = self.overwrite
        if self.overwrite:
            self.overwrite = False
            if k.lower() != 'y':
                self.set_message('')
                return False
            r = 'apply'
        else:
            r = self.editor.key(k)
            question = ( overwrite_question(self.v,self.editor.field,self.editor.text)
                         if r == 'apply' else None )
            if question is not None:
                self.overwrite = True
                self.set_message(f'{question} (y/n)')
                return False
        if r == 'cancel':
            self.editor = None
        elif r == 'apply':
            done, msg, replot = apply_editor(self.v,self.editor,confirmed)
            self.set_message(msg,done)
            if done:
                self.editor = None
            if replot:
                self.view_changed()
            return replot
        return False

    def scale_key( self, k, key = None ):
        """Toggle the log scale of the plot (the view with the key, default the
        shown one) if k is a key of log scales (see scale_keys): whether it
        is one"""
        option = scale_keys.get(k.lower())
        if option is None:
            return False
        self.set_message(*reversed(self.v.toggle_scale(option,key)))
        return True

    def do( self, action ):
        """Do the action (see key_action): 'quit' to quit, the action if the
        front end does it (e.g. opening a window), or None"""
        v = self.v
        self.set_message('')
        if action in ( 'previous', 'next' ):
            v.select(v.current + ( -1 if action == 'previous' else 1 ))
            self.view_changed()
        elif action in ( 'move_up', 'move_down' ):
            v.move(-1 if action == 'move_up' else 1)
        elif action == 'write' and not v.changes_particles:
            self.set_message(v.nothing_to_write,False)
        elif action == 'help':
            self.show_help = True
        elif action == 'quit':
            return 'quit'
        else:
            self.editor = editor_for(v,action)
            return action if self.editor is None else None
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

def apply_text( viewer, field, text, replaces = None, allow_overwrite = False ):
    """Apply the text of a field (see check_text): (done, message, replot),
    where done tells whether it was applied, message is to be shown (an error,
    or the result of writing a file) and replot whether the plots changed.
    Existing files are only overwritten with allow_overwrite (asked for with
    the question of overwrite_question)."""
    if field == 'write':
        ok, msg = viewer.try_write(text.strip(),allow_overwrite)
        return ok, msg if ok else f'Not written: {msg}', False
    if field == 'state':
        ok, msg = viewer.try_save_state(text.strip(),allow_overwrite)
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
    viewer.tab_used = True
    start, cands = viewer.complete(field,text,cursor)
    if not cands:
        return text, cursor, [], start
    names = [ n for n, _ in cands ]
    common = os.path.commonprefix(names)
    #(the common start only if it continues what is typed, which names matched
    #by a later part, see Viewer.complete, need not do):
    if len(cands) == 1 or ( len(common) > cursor - start
                            and common.startswith(text[start:cursor]) ):
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

def apply_editor( viewer, editor, allow_overwrite = False ):
    """Apply the text of the editor (Enter), see apply_text"""
    return apply_text(viewer,editor.field,editor.text,editor.replaces,allow_overwrite)

def overwrite_question( viewer, field, text ):
    """The question to ask before applying the text of a file prompt which
    would overwrite an existing file, or None"""
    if field not in file_prompts:
        return None
    existing = viewer.file_to_overwrite(field,text.strip())
    return None if existing is None else f'Overwrite {existing}?'

class LineEditor:
    """Editing of the text of a field with keys (for the front ends without
    their own text fields): characters, Left, Right, Home, End, Backspace,
    Delete, Tab (completion), Up and Down (earlier texts), Enter (apply), and
    Esc (cancel). The text is checked after each change (ok and message).
    The fields of menu_fields are a menu instead: Up and Down choose, Enter
    applies, and Esc cancels."""
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
        """Handle a key: returns 'apply', 'cancel', or None. While completions
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

def count_text( n ):
    """A number (of particles) as a text with thousands separators, like
    1,006,000"""
    return f'{n:,}'

def number_text( x ):
    """A number (like a sum of weights) as a text: whole numbers as for
    count_text, others with 6 significant digits"""
    if float(x).is_integer() and abs(x) < 1e15:
        return count_text(int(x))
    return f'{x:.6g}'

#The particles kept in memory by the viewer (see Viewer.cache_info), with the
#button and the menu of the viewers with windows:

def _bytes( n ):
    """A number of bytes as a text (like 2 GB, 1.2 GB or 500 MB)"""
    if n >= 1e9:
        return f'{n/1e9:.2g} GB' if n < 1e10 else f'{n/1e9:.0f} GB'
    return f'{n/1e6:.0f} MB' if n >= 1e6 else f'{n/1e3:.0f} kB'

def _used_text( n, nrange ):
    """The particles used by the plots, as a text"""
    if n >= nrange:
        return f'all {count_text(nrange)} particles'
    return f'the first {count_text(n)} of {count_text(nrange)} particles'

def cache_text( info ):
    """The text of the button of the cache (info from Viewer.cache_info): the
    memory used and the percentage of the particles of the range which fit
    in it, and its state (for its colour): 'filling' while the particles are
    put there, else 'all' when the plots use all particles of the range, or
    'cut' when they only use the first ones, which fit in the cache"""
    if info['limit'] is None:
        return 'no cache', 'all'
    n, nused = info['nrange'], info['nused']
    #(rounded down, so 100% means all of them):
    percent = '100%' if nused >= n else f'{100 * nused // n}%' if 100 * nused >= n else '<1%'
    state = 'filling' if info['filling'] else 'all' if info['fits'] else 'cut'
    return f'cache: {_bytes(info["cached"])} ({percent})', state

#The cache limits offered (in bytes, None for no cache):
cache_presets = ( 5e6, 20e6, 100e6, 500e6, 2e9, 5e9, 10e9, None )

#The cache limit (in bytes) unless one is chosen:
default_cache_limit = 100e6

def used_particles( n, size, limit ):
    """The number of particles the plots use, of the n particles of the range
    (of size bytes each), with the cache limit (in bytes, or None for no
    cache): all if they fit, else those which fit (at least one)"""
    if limit is None or n * size <= limit:
        return n
    return max( 1, int( limit // size ) )

#The title of the menu of the cache (see cache_menu):
cache_menu_title = 'Memory for the particles used by the plots (counted before the edit):'

def cache_menu( info ):
    """The entries of the menu of the cache (info from Viewer.cache_info), as
    (label, cache limit, whether it is used, whether the plots use all
    particles with it)"""
    entries, n = [], info['nrange']
    for limit in cache_presets:
        if limit is None:
            label = 'No memory cache (refreshing plots from file on each change)'
            fits = True
        else:
            used = used_particles(n,info['size'],limit)
            fits = n * info['size'] <= limit
            label = f'Max {_bytes(limit)}: {_used_text(used,n)}'
            if not fits:
                label += f' ({100.0*used/max(1,n):.2g}%)'
        entries.append( ( label, limit, limit == info['limit'], fits ) )
    return entries

def cache_line( info ):
    """The message after the cache limit was changed"""
    if info['fits']:
        return f'The plots use all {count_text(info["nrange"])} particles'
    return ( f'The plots use the first {count_text(info["nused"])} of the'
             f' {count_text(info["nrange"])} particles'
             ' (those in the cache), but new files get all' )

def about_blocks():
    """The help blocks (see _helptext) about MCPL: its version, website, and
    how to help its development"""
    from ._common import __version__
    repo = 'https://github.com/mctools/mcpl'
    return (
        ( 'text', f'MCPL (Monte Carlo Particle Lists), version {__version__}.' ),
        ( 'text', 'The documentation is on the website: https://mctools.github.io/mcpl/' ),
        ( 'text', 'To help MCPL developments you can:' ),
        ( 'bullet', f'Post ideas and questions on {repo}/discussions' ),
        ( 'bullet', f'Submit issues or feature requests on {repo}/issues' ),
        ( 'bullet', 'Help add MCPL support to your favourite Monte Carlo' ),
        ( 'bullet', f'Give it a star on GitHub: {repo}' ) )

#The help about the cache (see cache_menu), as blocks (see _helptext):
cache_blocks = (
    ( 'text', ( 'The viewer keeps the particles it reads in memory (the cache), so it does'
      ' not need to read the file again when the plots or the edit change.' ) ),
    ( 'gap', ),
    ( 'section', 'The memory limit' ),
    ( 'text', ( 'The button at the top right shows the memory used, and its menu sets the'
      f' limit ({_bytes(default_cache_limit)} unless chosen). The memory is counted for the'
      ' particles before the edit.' ) ),
    ( 'key', 'Green', 'All particles fit: the plots use all of them.' ),
    ( 'key', 'Red', ( 'Not all particles fit: the plots use only the first ones, those which'
      ' fit, and the others are not read, so the viewer stays fast. The numbers of'
      ' particles kept by the edit are then estimates (marked \u2248).' ) ),
    ( 'key', 'No cache', 'All particles are read from the file again for each change.' ),
    ( 'gap', ),
    ( 'section', 'New files' ),
    ( 'text', ( 'New MCPL files always get all particles of the skip, limit, and edit,'
      ' whatever the memory limit.' ) ),
)

#The settings of the overviews of the standard groups (see
#WindowLogic.overview_controls), as name -> label:
overview_controls = { 'particle_type' : 'Display only', 'display_by' : 'Display by',
                      'variables' : 'Variables' }

#The button of the settings of correlation plots choosing the variables with the
#strongest correlations, and then all of them again (see
#WindowLogic.overview_controls):
most_correlated, all_variables = 'Most correlated', 'All variables'

def type_choices( found ):
    """The particle types found in the file (see Viewer.found), as (shown
    text, PDG code), the most common first"""
    from ._particles import _particle_text
    types = found['types']
    total = sum( w for _, w in types ) or 1.0
    return [ ( particle_type_text(_particle_text(pdg),w / total), pdg ) for pdg, w in types ]

def particle_type_text( name, fraction ):
    """The text of a particle type (its name, or None for all) in the menu of
    the settings of overviews, with its share of the weights"""
    if name is None:
        return 'all'
    return f'{name} ({100*fraction:.0f}%)' if fraction >= 0.01 else f'{name} (<1%)'

def variable_text( expr, constant ):
    """The text of a variable of a correlation plot, with its value if all
    particles have it (e.g. "z: all 20 cm")"""
    return expr if constant is None else f'{expr}: all {constant}'

#Shown instead of the plot while a new plot is made (in the viewers with
#windows, see WindowLogic.on_new_plot):
new_plot_hints = """New plot: choose or type what to plot below, and press Enter

\u2022  Choose a quantity in the list of an axis, or type any expression
\u2022  Tab completes the names of fields, units, and functions
\u2022  Add a Y axis for a 2D histogram, and also a Z axis for a 3D plot
\u2022  mcpltool -p help lists all names, and the ? buttons show examples"""
