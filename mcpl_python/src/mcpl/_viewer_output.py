
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

"""The state of the viewer (see Viewer.state), the commands and code doing
the same as it, and the writing of its particles to new files"""

__all__ = []

import os
import pathlib

from ._common import MCPLError
from ._stdviews import _groups
from ._viewer_groups import PlotGroups, settings_without_file
from ._viewer_ui import plot_of


class _Output:
    """The state, commands, and writing of the Viewer (a part of it, with its
    attributes)"""

    #The state:

    def state( self, full = True ):
        """The state of the viewer, as a dict with what differs from the start:
        skip, limit, and edit (unless full is False, with its statements which
        are switched off as inactive(..), see edit_lines), the groups of plots
        shown (a list of the keys of groups, if not the default ones), the
        custom plots (histogram strings), the settings of groups which
        were chosen (see PlotGroups.setting), and the view shown (if not the
        first). It is given as the state argument to open the viewer
        in the same state."""
        res = {}
        if full:
            for k in ( 'skip', 'limit' ):
                if getattr(self._s,k):
                    res[k] = getattr(self._s,k)
            edit = _state_edit(self._edit_lines)
            if edit:
                res['edit'] = edit
        res.update(self._groups.state())
        key = self.views[self.current][0] if self.views else None
        if key is not None and key != self.views[0][0]:
            #(plots as their histogram strings, with custom: only for custom
            #plots which are also in a standard group, see _view_key):
            plot = plot_of(key)
            res['view'] = key if plot is None or self._view_key(plot) != key else plot
        return res

    def _apply_state( self, state ):
        """Apply the state (from _as_state) to the start (see state())"""
        groups = state.get('groups')
        if groups is not None:
            self._groups.use(groups)
        for k in ( 'skip', 'limit', 'edit' ):
            if state.get(k):
                self._set_or_raise(k,str(state[k]))
        for p in state.get('custom',[]):
            self._set_or_raise('plot',p)
        for k, settings in state.get('settings',{}).items():
            for name, value in settings.items():
                self._groups.set_setting(k,name,value)
        self._sync()
        self._current = None

    def suggested_state_filename( self ):
        """<input>_viewer.json, or <input>_viewer2.json, ... if that exists"""
        return _free_filename(self.filename,'_viewer','.json')

    def try_save_state( self, filename, allow_overwrite = False ):
        """Save the state (see state()) as JSON in a new file (overwriting an
        existing file only with allow_overwrite, and without writing in a dry
        run): (ok, message)"""
        import json
        if not allow_overwrite and os.path.lexists(filename):
            return False, f'The output file "{filename}" already exists'
        if self._dry_run:
            return True, f'Dry run: the viewer state was not saved in {filename}'
        try:
            pathlib.Path(filename).write_text(json.dumps(self.state(),indent=1) + '\n')
        except OSError as e:
            return False, f'Can not write {filename} ({e})'
        return True, f'Saved the viewer state in {filename}'

    #Commands:

    def _options( self ):
        from ._extract import _range_options
        s = self._s
        return _range_options(s.skip,s.limit,s.expression)

    def commands( self, option = '-w' ):
        """Commands doing the same as the viewer: 'view' (opening the viewer in
        the same state, given after the option -w for a window or -t for the
        terminal) and 'extract' (writing the edited particles to a new
        file)"""
        import json

        from ._extract import _shell_path
        prog, fn = self._progname, _shell_path(self.filename)
        opts = self._options()
        #The state beyond the options, as JSON with the strings in single
        #quotes (see _as_state), in double quotes (which work in all shells, as
        #the texts contain none of the characters which are special in some of
        #them):
        state = self.state(full = False)
        if not state:
            view = option
        else:
            text = json.dumps(state,separators=(',',':')).replace('"',"'")
            view = f'{option} "{text}"'
        return { 'view' : ' '.join([ prog, view ] + opts + [ fn ]),
                 'extract' : ' '.join([ prog, '-x' ] + opts + [ fn, self.suggested_filename() ]) }

    def code( self, plots = None, filename = None ):
        """The command (of mcpltool) and the code doing the same as the viewer,
        as a dict with the keys of _viewer_code.kinds: histograms of the plots
        (a list of histogram strings), or else writing the edited particles to
        the file filename (default suggested_filename())"""
        from ._reader import MCPLFile
        from ._viewer_code import _Job, code
        s = self._s
        mark, layout, comment = False, None, None
        if plots is None:
            from ._extract import _extraction_comment, _statsum_marking
            with MCPLFile(self.filename) as f:
                #(as by mcpltool -x):
                mark = _statsum_marking(f,s.skip,s.limit,s.edit) is not None
                layout = f.userdata_layout
            comment = _extraction_comment(s.skip,s.limit,s.edit)
        job = _Job(self.filename,s.skip,s.limit,s.expression,plots,
                   filename or self.suggested_filename(),mark,layout,comment)
        return code(job,self._progname)

    #Writing:

    @property
    def has_userdata( self ):
        """Whether the particles of the file have userdata"""
        return bool(self._ud_fields)

    def arguments( self ):
        """The arguments of Viewer making a viewer of the same file in the same
        state (also in another process, as they are simple values)"""
        return { 'filename' : self.filename, 'state' : self.state(),
                 'dry_run' : self._dry_run, 'progname' : self._progname }

    def for_file( self, filename, particles = True ):
        """A viewer of another file, in the same state, but without skip and
        limit and the settings of groups which depend on the file (which are of
        this file, see _viewer_groups.file_settings), and without the edit
        unless particles is set (not for a file written with it): (viewer,
        message), with the message saying what could not be kept (e.g. an edit
        with fields of the userdata which the other file does not have), or
        empty"""
        drop = ( 'skip', 'limit' ) + ( () if particles else ( 'edit', ) )
        kw = self.arguments()
        state = { k : v for k, v in kw.pop('state').items() if k not in drop }
        if 'settings' in state:
            state['settings'] = settings_without_file(state['settings'])
        del kw['filename']
        try:
            return type(self)(filename,state=state,**kw), ''
        except MCPLError as e:
            problem = e
        for drop, what in ( ( ( 'edit', ), 'the edit' ),
                            ( ( 'edit', 'custom', 'view' ), 'the edit and plots' ) ):
            try:
                return ( type(self)(filename,state={ k : v for k, v in state.items() if k not in drop },**kw),
                         f'Not kept for this file: {what} ({problem})' )
            except MCPLError:
                pass
        return type(self)(filename,**kw), f'Not kept for this file: the state of the viewer ({problem})'

    @property
    def changes_particles( self ):
        """Whether the particles shown are not just those of the file (with
        skip, limit, or edit), so writing them gives a new file"""
        s = self._s
        return bool( s.skip or s.limit or s.edit is not None )

    #(the reason why writing is not possible, see changes_particles):
    nothing_to_write = 'Edit or choose a range of particles first, to write them to a new file'

    def particles( self ):
        """The particles used, as the file, skip, limit, and edit (the
        arguments of the functions which threads run with them, like
        edited_blocks and try_write, see _viewer_threads)"""
        s = self._s
        return self.filename, s.skip, s.limit, s.edit

    @property
    def edit_text( self ):
        """The text of the edit used (empty if none)"""
        return self._s.expression or ''

    def suggested_filename( self ):
        """<input>_selected.mcpl, or <input>_selected2.mcpl, ... if that (or
        the same with .gz) exists"""
        return _free_filename(self.filename,'_selected','.mcpl','.mcpl.gz')

    def file_to_overwrite( self, action, filename ):
        """The existing file which the action ('write' or 'state') would
        overwrite with this file name (for writing, also the file which a
        .mcpl.gz file is compressed from), or None. None also if the name is
        refused anyway (e.g. the file viewed), so that no question is asked
        before the error."""
        if action == 'state':
            return filename if os.path.lexists(filename) else None
        from ._writer import _is_same_file, _outfile_name
        try:
            fn, gzip = _outfile_name(filename)
        except MCPLError:
            return None
        final = fn + '.gz' if gzip else fn
        if any( _is_same_file(f,self.filename) for f in ( fn, final ) ):
            return None
        return next( ( f for f in ( final, fn ) if os.path.lexists(f) ), None )

    def write_arguments( self, filename = None, allow_overwrite = False ):
        """The arguments of try_write (or write) writing the edited particles
        to a new file (named filename, or else as
        suggested_filename), overwriting an existing file only with
        allow_overwrite, and without writing in a dry run"""
        return ( *self.particles(), filename or self.suggested_filename(),
                 allow_overwrite, self._dry_run )

    def try_write( self, filename = None, allow_overwrite = False ):
        """Write the particles (see write_arguments): (ok, message), see
        try_write of the module"""
        return try_write(*self.write_arguments(filename,allow_overwrite))

    def write( self, filename = None, allow_overwrite = False ):
        """Write the particles (see write_arguments), returning the messages
        (as for mcpltool -x)"""
        return write(*self.write_arguments(filename,allow_overwrite))

def _state_edit( lines ):
    """The edit of a saved state: the lines of the edit (as (text, active),
    see Viewer.edit_lines), with each statement of the inactive lines with a
    valid syntax as inactive(..)"""
    from ._expr_str2ast import _expr_str2ast, _split_statements
    def inactive( text ):
        try:
            _expr_str2ast(text,'edit')
            return [ f'inactive({st})' for st, _ in _split_statements(text) ]
        except MCPLError:
            return []
    return '; '.join( st for text, active in lines
                      for st in ( [ text ] if active else inactive(text) ) )

def edited_blocks( filename, skip, limit, edit ):
    """The blocks of the particles of the file (see _Output.particles) as they
    are written, read from the file opened here (so this can run in another
    thread)"""
    from ._reader import MCPLFile
    with MCPLFile(filename,skip=skip,limit=limit or None,edit=edit) as f:
        yield from f.particle_blocks

def write( filename, skip, limit, edit, output, allow_overwrite, dry_run ):
    """Write the particles of the file (see _Output.particles) to the file
    output (overwriting an existing file only with allow_overwrite, and
    without writing in a dry run). Returns the messages (as for mcpltool -x)."""
    from ._extract import _mcpltool_extract
    from ._messages import _CollectMessages
    def bad( msg ):
        raise MCPLError(msg)
    #(collecting the messages of this thread only, as it can run in its own):
    with _CollectMessages() as out:
        _mcpltool_extract([filename,output],limit,skip,edit,False,False,dry_run,bad,
                          allow_overwrite)
    return '\n'.join(out.lines).strip()

def try_write( *args ):
    """As write, but returning (ok, message): the last line of the output, or
    the problem"""
    try:
        lines = ( write(*args) or '' ).splitlines()
    except MCPLError as e:
        return False, str(e).removesuffix('.')
    return True, lines[-1] if lines else ''

def try_write_to( mailbox, *args ):
    """try_write, putting (ok, message) in the mailbox (in a thread, see
    _viewer_threads)"""
    mailbox.put(try_write(*args))

def _free_filename( filename, suffix, ext, *other_exts ):
    """The name <input><suffix><ext> next to the file (without its extensions
    .mcpl and .gz), or with 2, 3, ... after the suffix if that (or the same
    with one of the other extensions) exists"""
    p = pathlib.Path(filename)
    stem = p.name
    for e in ( '.gz', '.mcpl' ):
        stem = stem.removesuffix(e)
    i = 1
    while True:
        name = f'{stem}{suffix}{i if i > 1 else ""}'
        cands = [ p.with_name(name + e) for e in ( ext, ) + other_exts ]
        if not any( c.exists() for c in cands ):
            return str(cands[0]) if p.parent != pathlib.Path('.') else cands[0].name
        i += 1

#The entries of the state (see Viewer.state):
_state_keys = ( 'skip', 'limit', 'edit', 'groups', 'custom', 'settings', 'view' )

def _as_state( state ):
    """The state of the viewer (see Viewer.state), from a dict, its JSON
    text, or the name of a .json file with it"""
    import json
    if isinstance(state,dict):
        where = 'The viewer state'
    elif not isinstance(state,str):
        raise MCPLError('The viewer state must be a dict, its JSON text, or the name of a .json file')
    elif state.lstrip().startswith('{'):
        #(as JSON, or with the strings in single quotes, which is easier on
        #command lines, see Viewer.commands; the texts of the state can
        #contain neither kind of quote):
        text = state if '"' in state else state.replace("'",'"')
        where = f'The viewer state "{state}"'
        try:
            state = json.loads(text)
        except ValueError as e:
            raise MCPLError(f'{where} is not valid JSON ({e})')
    elif state.endswith('.json'):
        where = f'The viewer state in {state}'
        try:
            state = json.loads(pathlib.Path(state).read_text())
        except OSError as e:
            raise MCPLError(f'Can not read the viewer state from {state} ({e})')
        except ValueError as e:
            raise MCPLError(f'{where} is not valid JSON ({e})')
    else:
        raise MCPLError(f'The viewer state "{state}" must be a .json file or its JSON'
                        ' text, like {"edit":"pdgcode == neutron"}')
    def check( ok, what ):
        if not ok:
            raise MCPLError(f'{where} is not valid: {what}')
    check(isinstance(state,dict),'it must be a JSON object, like {"edit":"pdgcode == neutron"}')
    for k in state:
        check(k in _state_keys,f'unknown entry "{k}" (the entries are: {", ".join(_state_keys)})')
    for k in ( 'skip', 'limit' ):
        check(isinstance(state.get(k,0),int),f'{k} must be a number')
    for k in ( 'edit', 'view' ):
        check(isinstance(state.get(k,''),str),f'{k} must be a text')
    groups = state.get('groups',[])
    check(isinstance(groups,list) and all( g in _groups for g in groups ),
          f'groups must be a list of the groups of plots ({", ".join(_groups)})')
    check(groups or state.get('custom') or 'groups' not in state,
          'groups can only be empty if there are custom plots')
    settings = state.get('settings',{})
    check(isinstance(settings,dict) and all( k in _groups and isinstance(v,dict)
                                             for k, v in settings.items() ),
          'settings must give the settings of groups, like {"correlations":'
          ' {"particle_type": 2112}}')
    for k, v in settings.items():
        names = PlotGroups.setting_names(k)
        for name, value in v.items():
            check(name in names,f'the settings of the group "{k}" can be: {", ".join(names)}')
            if name == 'particle_type':
                ok = value is None or ( isinstance(value,int) and not isinstance(value,bool) )
                check(ok,'particle_type must be a PDG code (or null for all particles)')
            elif name == 'display_by':
                check(value in ( 'pdgcode', 'single' ),'display_by must be "pdgcode" or "single"')
            else:
                choices = _groups[k][2]['variables']
                check(isinstance(value,list) and len(value) >= 2 and all( c in choices for c in value ),
                      'variables must be a list of at least two of: ' + ', '.join(choices))
    custom = state.get('custom',[])
    check(isinstance(custom,list) and all( isinstance(p,str) for p in custom ),
          'custom must be a list of plots (histogram strings)')
    return state
