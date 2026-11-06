
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

"""The Composer of the viewer, without a toolkit (see _viewer_tkcompose):
the edit as a list of lines, each with one or more statements, which are
typed, or written by the controls of their kind (keeping only some particles,
changing a field, rotating, or aligning the particles). The window shows the
controls of a line as rows (see Composer.rows), and applies the final
expression to the viewer."""

__all__ = []

import collections
import functools

from ._common import MCPLError

#The kinds of lines, as shown:
kinds = { 'filter' : 'Filter condition', 'change' : 'Change', 'rotate' : 'Rotate',
          'align' : 'Align', 'variable' : 'Define variable', 'expression' : 'Expression' }

#The controls of a line, in rows (see Composer.rows). The kinds of controls
#are menu (choices, or any typed text), select (choices only), entry, check
#(choices is its label), text (fixed words), and note (a text computed here),
#with a hint shown while a menu or entry is empty:
Control = collections.namedtuple('Control','name kind value choices hint',defaults=( None, ))
#(option is the value of the option control choosing the row, if any):
Row = collections.namedtuple('Row','option label controls')

_comparisons = ( '<', '<=', '>', '>=', '==', '!=' )
_operations = ( '=', '+=', '-=', '*=', '/=' )
_axes = ( ( 'x axis', 'x' ), ( 'y axis', 'y' ), ( 'z axis', 'z' ) )
_angle_units = ( 'deg', 'rad' )

class Line:
    """A line of the Composer: its text (one or more statements),
    whether it is active, and its kind and the values of its controls (for
    lines written by controls, see kinds)"""
    def __init__( self, text = '', active = True, kind = 'expression', form = None ):
        self.text, self.active, self.kind, self.form = text, active, kind, form or {}
        #(the means of the particles before an align line, and the edit they are of):
        self.stats, self.stats_key = None, None

class Composer:
    """The lines of the edit of the viewer v (see Viewer.edit_lines) being
    composed, applied with apply_lines (by default Viewer.set_edit_lines, which
    gives (ok, message))"""
    def __init__( self, v, apply_lines = None ):
        self.v = v
        self._apply_lines = apply_lines or ( lambda lines : v.set_edit_lines(lines)[0] )
        self.reset()

    def reset( self ):
        """Start again from the edit of the viewer"""
        self._base = self.v.edit_lines
        self.lines = [ Line(text,active) for text, active in self._base ]

    def _texts( self ):
        return [ ( line.text.strip(), line.active ) for line in self.lines if line.text.strip() ]

    @property
    def pending( self ):
        """Whether the lines differ from the edit of the viewer"""
        return self._texts() != self.v.edit_lines

    @property
    def expression( self ):
        """The edit of the active lines"""
        return '; '.join( t for t, active in self._texts() if active )

    def sync( self ):
        """Start again from the edit of the viewer if it was changed elsewhere,
        unless the lines were changed here. Returns whether it did."""
        if self.v.edit_lines == self._base or self._texts() != self._base:
            return False
        self.reset()
        return True

    def apply( self ):
        """Apply the lines to the viewer: whether it was done"""
        if not self._apply_lines(self._texts()):
            return False
        self._base = self.v.edit_lines
        self.lines = [ line for line in self.lines if line.text.strip() ]
        return True

    def checks( self ):
        """The error of each line (empty if none, None for empty lines). Each
        line is checked after the variables assigned by the active lines before
        it which have no errors (which is all a line can depend on when
        checked, so the errors are about the line itself)."""
        res, before = [], []
        for line in self.lines:
            if not line.text.strip():
                res.append(None)
                continue
            ok, msg = self.v.check_start('; '.join(before + [ line.text ]))
            res.append(msg)
            if ok and line.active and _assigns_variables(line.text):
                before.append(line.text)
        return res

    def counts( self ):
        """The numbers of particles left after each line (see
        Viewer.edit_line_counts, None for inactive and empty lines), or None
        if not known or the lines are not applied"""
        counts = None if self.pending else self.v.edit_line_counts()
        if counts is None:
            return None
        counts = iter(counts)
        return [ next(counts) if line.text.strip() else None for line in self.lines ]

    #Changing the lines:

    def add( self ):
        """Add an empty line at the end: its index"""
        self.lines.append(Line())
        return len(self.lines) - 1

    def delete( self, i ):
        del self.lines[i]

    def move( self, i, step ):
        """Move line i up (step -1) or down (step 1), if possible"""
        j = i + step
        if 0 <= j < len(self.lines):
            self.lines[i], self.lines[j] = self.lines[j], self.lines[i]

    def set_active( self, i, active ):
        self.lines[i].active = active

    def set_text( self, i, text ):
        """The text of the line was typed, which makes it an expression"""
        line = self.lines[i]
        line.text, line.kind = text, 'expression'

    def set_kind( self, i, kind ):
        """Make line i one of the kind (see kinds), with the default values of
        its controls"""
        line = self.lines[i]
        line.kind, line.form = kind, self._defaults(kind)
        self._write(line)

    def set_value( self, i, name, value ):
        """Set the control of line i with the name to the value (as shown, for
        menus and selects), which writes the line"""
        line = self.lines[i]
        choices = dict( self._choices(line,name) )
        before = _is_vector(line.form.get('field'))
        line.form[name] = choices.get(value,value)
        #(a control of one of the options chooses that option; rows without an
        #option of their own continue the one before them):
        option = None
        for row in self.rows(i):
            option = row.option or option
            if option and any( x.name == name for x in row.controls ):
                line.form['option'] = option
        if name == 'field' and _is_vector(line.form['field']) != before:
            line.form['value'] = ''#(a number is no vector, and the other way around)
        if name in ( 'quantity', 'field', 'op' ):#(the units fitting the new choice)
            units = self._units(line)
            if name != 'op' or line.form.get('unit') not in units:
                line.form['unit'] = units[0] if units else ''
        self._write(line)

    #The controls of the lines:

    def rows( self, i ):
        """The controls of line i, as rows (see Row and Control), with their
        values and choices as shown"""
        line = self.lines[i]
        def c( name, kind, hint = None ):
            choices = [ t for t, _ in self._choices(line,name) ]
            value = line.form.get(name)
            shown = next( ( t for t, v in self._choices(line,name) if v == value ),
                          '' if value is None else value )
            return Control(name,kind,shown,choices,hint)
        text = lambda words : Control('',"text",words,())
        check = lambda name, label : Control(name,'check',bool(line.form.get(name)),label)
        vector = 'a vector, e.g. (0,0,1m)'
        if line.kind == 'filter':
            unit = [ c('unit','select') ] if self._units(line) else []
            return [ Row('type','Particle type',[ c('pdg','select') ]),
                     Row('quantity','Quantity',[ c('quantity','menu','choose or type'),
                                                 c('op','select'), c('value','entry','value'),
                                                 *unit ]),
                     Row('near','Near a point',[ text('within'), c('radius','entry','distance'),
                                                 c('runit','select'), text('of'),
                                                 c('point','entry',vector) ]),
                     Row('sphere','Sphere',[ text('flying through it, at'),
                                             c('centre','entry',vector), text('with radius'),
                                             c('sradius','entry','radius'), c('sunit','select') ]),
                     Row('box','Box',[ text('flying through it, at'), c('bcentre','entry',vector),
                                       text('with half dimensions'),
                                       c('half','entry','a vector, e.g. (5cm,5cm,1mm)') ]) ]
        if line.kind == 'change':
            unit = [ c('unit','select') ] if self._units(line) else []
            value = vector if _is_vector(line.form.get('field')) else 'value'
            return [ Row(None,'',[ c('field','menu','choose a field'), c('op','select'),
                                   c('value','entry',value), *unit ]) ]
        if line.kind == 'rotate':
            direction = 'a direction, e.g. (1,1,0)'
            return [ Row('xyz','Around x, y, or z',[ c('axis','select'), text('by'),
                                                      c('angle','entry','angle'),
                                                      c('aunit','select') ]),
                     Row('around','Around an axis',[ c('vector','entry',direction), text('by'),
                                                     c('angle2','entry','angle'),
                                                     c('aunit2','select') ]),
                     Row('frame','From a frame',[ text('turning the direction'),
                                                  c('v','entry',direction), text('into'),
                                                  c('vout','entry',direction) ]),
                     Row(None,'',[ text('and the direction'), c('u','entry',direction),
                                   text('into'), c('uout','entry',direction) ]) ]
        if line.kind == 'align':
            means, result = _align_notes(line)
            return [ Row(None,'',[ Control('means','note',means,()) ]),
                     Row(None,'',[ check('turn','Turn the mean direction into'), c('target','menu'),
                                   text('keeping the axis'), c('keep','menu'), text('around'),
                                   c('pivot','menu') ]),
                     Row(None,'',[ check('move','Then move the mean position to'), c('point','menu'),
                                   text('changing'), check('cx','x'), check('cy','y'),
                                   check('cz','z') ]),
                     Row(None,'',[ Control('result','note',result,()) ]) ]
        if line.kind == 'variable':
            return [ Row(None,'',[ c('name','entry','name, e.g. d'), text('='),
                                   c('value','menu','value, e.g. pos - (0,0,1m)') ]) ]
        return []

    def _choices( self, line, name ):
        """The choices of a control of the line, as (shown text, value)"""
        from . import _viewer_ui as ui
        from ._viewer_align import direction_choices
        if name == 'pdg':
            return ui.type_choices(self.v.found)
        if name == 'quantity' or ( name == 'value' and line.kind == 'variable' ):
            return [ ( t, e ) for t, e in ui.quantity_choices if not e.endswith(';bar') ]
        if name == 'field':
            return _field_choices()
        if name == 'op':
            return [ ( o, o ) for o in ( _comparisons if line.kind == 'filter' else _operations ) ]
        if name == 'unit':
            return [ ( u, u ) for u in self._units(line) ]
        if name in ( 'runit', 'sunit' ):
            return [ ( u, u ) for u in _units('x') ]
        if name == 'axis':
            return list(_axes)
        if name in ( 'aunit', 'aunit2' ):
            return [ ( u, u ) for u in _angle_units ]
        if name in ( 'target', 'keep' ):
            return [ ( d, d ) for d in ( () if name == 'target' else ( 'none', ) ) + direction_choices ]
        if name == 'pivot':
            return [ ( 'mean position', 'mean position' ), ( '(0,0,0)', '(0,0,0)' ) ]
        if name == 'point' and line.kind == 'align':
            return [ ( '(0,0,0)', '(0,0,0)' ) ]
        return []

    def _units( self, line ):
        """The units fitting the value of the line (keep or change), the default
        first, none for multiplications, divisions, and vectors"""
        f = line.form
        if line.kind == 'change' and f.get('op') in ( '*=', '/=' ):
            return ()
        return _units(f.get('quantity' if line.kind == 'filter' else 'field',''))

    def _defaults( self, kind ):
        """The values of the controls of a new line of the kind (no values
        which are to be given, only choices, e.g. of units)"""
        if kind == 'filter':
            return { 'op' : '<', 'runit' : 'cm', 'sunit' : 'cm' }
        if kind == 'change':
            return { 'op' : '+=' }
        if kind == 'rotate':
            return { 'axis' : 'z', 'aunit' : 'deg', 'aunit2' : 'deg' }
        if kind == 'align':
            return { 'turn' : True, 'target' : '(0,0,1)', 'keep' : 'none',
                     'pivot' : 'mean position', 'move' : False, 'point' : '(0,0,0)',
                     'cx' : True, 'cy' : True, 'cz' : True }
        return {}

    def _write( self, line ):
        """Write the text of a line from its controls"""
        if line.kind != 'expression':
            line.text = _statement(line)

    #Help with typing, and the align lines:

    def complete( self, text, cursor ):
        """Completion of the name at the cursor of a typed line (see
        _viewer_ui.complete_text)"""
        from ._viewer_ui import complete_text
        return complete_text(self.v,'edit',text,cursor)

    def completions( self, text, cursor ):
        """The completions of the name being typed at the cursor of a typed
        line, as (start, candidates), see Viewer.complete"""
        return self.v.complete('edit',text,cursor)

    def hint( self, text, cursor ):
        """The hint for the name at the cursor of a typed line (see Viewer.hint)"""
        return self.v.hint('edit',text,cursor)

    def align_reading( self, i ):
        """If align line i needs the means of the particles before it: the key
        of these particles (the skip, limit, and edit before it), and the
        arguments of _viewer_align.read_file_stats after the mailbox (file,
        skip, limit, and that edit), else None"""
        line = self.lines[i]
        before = '; '.join( l.text for l in self.lines[:i] if l.active and l.text.strip() )
        filename, skip, limit, _ = self.v.particles()
        #(the means are read again when the particles change):
        key = ( skip, limit, before )
        if line.kind != 'align' or line.stats_key == key:
            return None
        if before and not self.v.check('edit',before)[0]:
            return None
        return key, ( filename, skip, limit, before or None )

    def set_align_stats( self, line, key, stats ):
        """The means (stats, see _viewer_align.read_stats, or the MCPLError of
        reading them) of the particles before the align line (an object of
        self.lines), for the edit key"""
        line.stats, line.stats_key = stats, key
        self._write(line)

def _assigns_variables( text ):
    """Whether the statements of a (valid) line assign variables"""
    from ._expr_ast import Assign
    from ._expr_str2ast import _expr_str2ast
    from ._expr_vocab import _assignable
    return any( isinstance(st,Assign) and st.target not in _assignable
                for st in _expr_str2ast(text,'edit').statements )

@functools.lru_cache(maxsize=256)
def _units( expr ):
    """The units fitting the values of an expression (the default first), or
    () for values without units, or which can not be evaluated"""
    from ._expr_eval import _EmptyBlock
    from ._expr_vocab import _expr_unit_hints
    from ._expressions import _Expr
    from ._exprunits import _expr_units
    try:
        d = _Expr(expr).evaluate(_EmptyBlock()).d
    except MCPLError:
        return ()
    units = [ u for u, ( _, ud ) in _expr_units.items() if ud is not None and ud == d ]
    if not units:
        return ()
    default = 'Aa' if expr.strip() == 'wavelength' else _expr_unit_hints.get(d,units[0])
    return ( default, *( u for u in units if u != default ) )

@functools.cache
def _field_choices():
    """The fields (and vectors) which can be changed, as (shown text, name)"""
    from ._expr_vocab import _assignable
    from ._stdviews import _field_titles
    vectors = { 'pos' : 'Position', 'dir' : 'Direction', 'pol' : 'Polarisation' }
    return [ ( f'{_field_titles.get(f) or vectors[f]}:  {f}', f ) for f in _assignable ]

def _is_vector( field ):
    return field in ( 'pos', 'dir', 'pol' )

def _statement( line ):
    """The text of a line written by its controls (empty while values which
    are needed are not given)"""
    from ._particles import _particle_filter
    f = { k : ( v.strip() if isinstance(v,str) else v ) for k, v in line.form.items() }
    def given( *names ):
        return all( f.get(n) not in ( None, '' ) for n in names )
    with_unit = lambda v, unit : f'{f[v]}{f.get(unit) or ""}'
    option = f.get('option')
    if line.kind == 'filter':
        if option == 'type' and given('pdg'):
            return _particle_filter(f['pdg'])
        if option == 'quantity' and given('quantity','value'):
            return f'{f["quantity"]} {f["op"]} {with_unit("value","unit")}'
        if option == 'near' and given('point','radius'):
            return f'abs(pos - {f["point"]}) < {with_unit("radius","runit")}'
        if option == 'sphere' and given('centre','sradius'):
            return f'through_sphere({f["centre"]},{with_unit("sradius","sunit")})'
        if option == 'box' and given('bcentre','half'):
            return f'through_box({f["bcentre"]},{f["half"]})'
    elif line.kind == 'change' and given('field','value'):
        return f'{f["field"]} {f["op"]} {with_unit("value","unit")}'
    elif line.kind == 'rotate':
        if option == 'xyz' and given('axis','angle'):
            return f'rotate_{f["axis"]}({with_unit("angle","aunit")})'
        if option == 'around' and given('vector','angle2'):
            return f'rotate_around({f["vector"]},{with_unit("angle2","aunit2")})'
        if option == 'frame' and given('v','vout','u','uout'):
            return f'rotate_frame({f["v"]},{f["vout"]},{f["u"]},{f["uout"]})'
    elif line.kind == 'variable' and given('name','value'):
        return f'{f["name"]} = {f["value"]}'
    elif line.kind == 'align':
        try:
            return _align_statements(line)[0]
        except MCPLError:
            pass
    elif line.kind == 'expression':
        return line.text
    return ''

def _align_statements( line ):
    """The statements of an align line, with the mean position and direction
    after them (see _viewer_align.align_edit)"""
    from . import _viewer_align as al
    f, s = line.form, line.stats
    if s is None:
        raise MCPLError('Reading the particles ...')
    if isinstance(s,MCPLError):
        raise s
    target = keep = centre = None
    pivot = 'mean'
    if f.get('turn'):
        target = al.parse_vector(f.get('target',''),'direction')
        k = f.get('keep','').strip()
        keep = None if k in ( '', 'none' ) else al.parse_vector(k,'axis to keep')
        p = f.get('pivot','').strip()
        pivot = 'mean' if p == 'mean position' else al.parse_vector(p,'point to rotate around','cm')
    if f.get('move'):
        centre = al.parse_vector(f.get('point',''),'point','cm')
    coords = ''.join( c for c in 'xyz' if f.get(f'c{c}') )
    return al.align_edit(s,target,keep,pivot,centre,coords)

def _align_notes( line ):
    """The texts about the means of the particles before an align line, and
    about them after it (or the problem)"""
    from ._viewer_ui import count_text
    s = line.stats
    if s is None:
        return 'Reading the particles ...', ''
    if isinstance(s,MCPLError):
        return str(s), ''
    if s.w <= 0:
        return 'No particles (with weights) to align', ''
    how = '' if s.complete else ' (estimated from the first ones)'
    d = s.mean_dir
    means = ( f'The weighted means of the {count_text(s.n)} particles before this line{how}:'
              f' position {xyz(s.mean_pos)} cm, direction'
              f' {"not defined" if d is None else xyz(d)}, spread {s.spread_deg:.3g} deg' )
    try:
        _, pos, d = _align_statements(line)
    except MCPLError as e:
        return means, str(e)
    return means, f'After it: position {xyz(pos)} cm, direction {xyz(d)}'

def xyz( v ):
    """A vector as a text, with rounding noise (as 1e-23 in a unit vector) as 0"""
    tiny = 1e-12 * max( 1.0, max( abs(c) for c in v ) )
    return '(' + ', '.join( f'{c:.6g}' if abs(c) > tiny else '0' for c in v ) + ')'
