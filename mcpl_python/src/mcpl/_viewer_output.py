
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

import pathlib

from ._common import MCPLError
from ._stdviews import _groups, _plot_item, _presets
from ._viewer_groups import group_names
from ._viewer_ui import plot_of


class _Output:
    """The state, commands and writing of the Viewer (a part of it, with its
    attributes)"""

    #The state:

    def state( self, full = True ):
        """The state of the viewer, as a dict with what differs from the start:
        skip, limit, pick and edit (unless full is False), the groups of plots
        shown (a preset or a list of the keys of groups, if not the default
        ones), the custom plots (plot items, see _stdviews), the settings of
        groups which were chosen (see PlotGroups.setting), and the view shown
        (if not the first). It is given as the view argument to open the viewer
        in the same state."""
        res = {}
        if full:
            for k in ( 'skip', 'limit' ):
                if getattr(self._s,k):
                    res[k] = getattr(self._s,k)
            for k in ( 'pick', 'edit' ):
                if self._texts[k]:
                    res[k] = self._texts[k]
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
            self._groups.shown = []
            if isinstance(groups,str):
                self._groups.use_preset(groups)
            for k in ( groups if isinstance(groups,list) else () ):
                self._groups.show(k)
        for k in ( 'skip', 'limit', 'pick', 'edit' ):
            if state.get(k):
                self._set_or_raise(k,str(state[k]))
        for item in state.get('custom',[]):
            p, title = _plot_item(item)
            self._set_or_raise('plot',p)
            p = self._same_plot(p,self._groups.custom)
            if self._groups.is_custom(p):
                self._groups.set_title(p,title)
        for k, settings in state.get('settings',{}).items():
            for name, value in settings.items():
                self._groups.set_setting(k,name,value)
        self._sync()
        self._current = None

    def suggested_state_filename( self ):
        """<input>_viewer.json, or <input>_viewer2.json, ... if that exists"""
        return _free_filename(self.filename,'_viewer','.json')

    def try_save_state( self, filename ):
        """Save the state (see state()) as JSON in a new file (never overwriting
        existing files, and without writing in a dry run): (ok, message)"""
        import json
        if pathlib.Path(filename).exists():
            return False, f'The file {filename} already exists'
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
        return _range_options(s.skip,s.limit,*( None if e is None else e.expression
                                               for e in ( s.pick, s.edit ) ))

    def commands( self ):
        """Commands doing the same as the viewer: 'view' (opening the viewer in
        the same state) and 'extract' (writing the picked and edited
        particles to a new file)"""
        import json

        from ._extract import _shell_path
        prog, fn = self._progname, _shell_path(self.filename)
        opts = self._options()
        #The state beyond the options, as --view=VIEW, or as JSON with the
        #strings in single quotes (see _as_state), in double quotes (which
        #work in all shells, as the texts contain none of the characters which
        #are special in some of them):
        state = self.state(full = False)
        if not state:
            view = '-w'
        elif list(state) == [ 'view' ]:
            view = f'--view="{state["view"]}"'
        elif list(state) == [ 'groups' ] and isinstance(state['groups'],str):
            view = f'-w{state["groups"]}'
        else:
            text = json.dumps(state,separators=(',',':')).replace('"',"'")
            view = f'--view="{text}"'
        return { 'view' : ' '.join([ prog, view ] + opts + [ fn ]),
                 'extract' : ' '.join([ prog, '-e' ] + opts + [ fn, self.suggested_filename() ]) }

    def code( self, plots = None, filename = None ):
        """The command (of mcpltool) and the code doing the same as the viewer,
        as a dict with the keys of _viewer_code.kinds: histograms of the plots
        (a list of histogram strings), or else writing the picked and edited
        particles to the file filename (default suggested_filename())"""
        from ._reader import MCPLFile
        from ._viewer_code import _Job, code
        s = self._s
        expr = lambda e : None if e is None else e.expression
        mark, userdata = False, False
        if plots is None:
            from ._extract import _statsum_marking
            with MCPLFile(self.filename) as f:
                #(as by mcpltool -e):
                mark = _statsum_marking(f,s.skip,s.limit,s.pick,s.edit) is not None
                userdata = f.userdata_layout is not None
        job = _Job(self.filename,s.skip,s.limit,expr(s.pick),expr(s.edit),plots,
                   filename or self.suggested_filename(),mark,userdata)
        return code(job,self._progname)

    #Writing:

    @property
    def has_userdata( self ):
        """Whether the particles of the file have userdata"""
        return bool(self._ud_fields)

    def arguments( self ):
        """The arguments of Viewer making a viewer of the same file in the same
        state (also in another process, as they are simple values)"""
        return { 'filename' : self.filename, 'view' : self.state(),
                 'dry_run' : self._dry_run, 'progname' : self._progname }

    def for_file( self, filename, particles = True ):
        """A viewer of another file, in the same state, but without skip and
        limit (which are of this file), and without the pick and edit unless
        particles is set (not for a file written with them): (viewer, message),
        with the message saying what could not be kept (e.g. a pick with fields
        of the userdata which the other file does not have), or empty"""
        drop = ( 'skip', 'limit' ) + ( () if particles else ( 'pick', 'edit' ) )
        kw = self.arguments()
        state = { k : v for k, v in kw.pop('view').items() if k not in drop }
        del kw['filename']
        try:
            return type(self)(filename,view=state,**kw), ''
        except MCPLError as e:
            problem = e
        for drop, what in ( ( ( 'pick', 'edit' ), 'the pick and edit' ),
                            ( ( 'pick', 'edit', 'custom', 'view' ), 'the pick, edit and plots' ) ):
            try:
                return ( type(self)(filename,view={ k : v for k, v in state.items() if k not in drop },**kw),
                         f'Not kept for this file: {what} ({problem})' )
            except MCPLError:
                pass
        return type(self)(filename,**kw), f'Not kept for this file: the state of the viewer ({problem})'

    @property
    def changes_particles( self ):
        """Whether the particles shown are not just those of the file (with
        skip, limit, pick or edit), so writing them gives a new file"""
        s = self._s
        return bool( s.skip or s.limit or s.pick is not None or s.edit is not None )

    #(the reason why writing is not possible, see changes_particles):
    nothing_to_write = 'Pick, edit or choose a range of particles first, to write them to a new file'

    def suggested_filename( self ):
        """<input>_selected.mcpl.gz, or <input>_selected2.mcpl.gz, ... if that
        (or the same without .gz) exists"""
        return _free_filename(self.filename,'_selected','.mcpl.gz','.mcpl')

    def try_write( self, filename = None ):
        """As write, but returning (ok, message): the last line of the output,
        or the problem"""
        try:
            out = self.write(filename)
        except MCPLError as e:
            return False, str(e)
        lines = ( out or '' ).splitlines()
        return True, lines[-1] if lines else ''

    def write( self, filename = None ):
        """Write the picked and edited particles to a new file (never
        overwriting existing files, and without writing in a dry run).
        Returns the messages (as for mcpltool -e)."""
        import contextlib
        import io

        from ._extract import _mcpltool_extract
        filename = filename or self.suggested_filename()
        if pathlib.Path(filename).exists() or pathlib.Path(filename + '.gz').exists():
            raise MCPLError(f'The file {filename} already exists')
        s = self._s
        out = io.StringIO()
        def bad( msg ):
            raise MCPLError(msg)
        with contextlib.redirect_stdout(out):
            _mcpltool_extract([self.filename,filename],s.limit,s.skip,s.pick,
                              s.edit,False,False,self._dry_run,bad)
        return out.getvalue().strip()

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

#The entries of the state (see Viewer.state), and of its changes of the plots:
_state_keys = ( 'skip', 'limit', 'pick', 'edit', 'groups', 'custom', 'settings', 'view' )

def _as_state( view ):
    """The state given as the view argument of the viewer (a dict, its JSON
    text, or the name of a .json file with it), or None if it is a view"""
    import json
    if view is None:
        return None
    if isinstance(view,dict):
        state, where = view, 'The viewer state'
    elif view.lstrip().startswith('{'):
        #(as JSON, or with the strings in single quotes, which is easier on
        #command lines, see Viewer.commands; the texts of the state can
        #contain neither kind of quote):
        text = view if '"' in view else view.replace("'",'"')
        where = f'The viewer state "{view}"'
        try:
            state = json.loads(text)
        except ValueError as e:
            raise MCPLError(f'{where} is not valid JSON ({e})')
    elif view.endswith('.json'):
        where = f'The viewer state in {view}'
        try:
            state = json.loads(pathlib.Path(view).read_text())
        except OSError as e:
            raise MCPLError(f'Can not read the viewer state from {view} ({e})')
        except ValueError as e:
            raise MCPLError(f'{where} is not valid JSON ({e})')
    else:
        return None
    def check( ok, what ):
        if not ok:
            raise MCPLError(f'{where} is not valid: {what}')
    check(isinstance(state,dict),'it must be a JSON object, like {"pick":"pdgcode == neutron"}')
    for k in state:
        check(k in _state_keys,f'unknown entry "{k}" (the entries are: {", ".join(_state_keys)})')
    for k in ( 'skip', 'limit' ):
        check(isinstance(state.get(k,0),int),f'{k} must be a number')
    for k in ( 'pick', 'edit', 'view' ):
        check(isinstance(state.get(k,''),str),f'{k} must be a text')
    names = [ n for n, _ in group_names() ]
    groups = state.get('groups',[])
    check(( isinstance(groups,str) and groups in names )
          or ( isinstance(groups,list) and all( g in _groups for g in groups ) ),
          f'groups must be the name of a preset ({", ".join(_presets)}) or a list of the'
          f' groups of plots ({", ".join(_groups)})')
    settings = state.get('settings',{})
    check(isinstance(settings,dict) and all( k in _groups and isinstance(v,dict)
                                             and set(v) <= { 'display_only', 'display_by',
                                                             'variables' }
                                             for k, v in settings.items() ),
          'settings must give the settings of groups, like {"correlations":'
          ' {"display_only": 2112}}')
    custom = state.get('custom',[])
    check(isinstance(custom,list),'custom must be a list of plots')
    for item in custom:
        try:
            _plot_item(item)
        except ( TypeError, ValueError ) as e:
            check(False,f'in the custom plots, {e}')
    return state
