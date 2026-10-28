
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

"""The interface implemented by the plotting backends, and their registry (see
also plotting.py)."""

__all__ = []

import importlib
import inspect
import pathlib
from typing import ClassVar

from ._common import MCPLError


class PlotBackend:
    """Interface of plotting backends (public as mcpl.plotting.Backend), which
    show or save lists of Figure objects. Subclasses set name (a unique name
    used to select the backend), kind (what plots are shown on: 'window' or
    'terminal', or None for backends which are only used when
    selected by name), priority (the preference among the backends of the
    same kind, higher is preferred), formats (a dict with the file extensions
    which save() can create, and their priorities among the backends which can
    create them) and requirement (the Python package needed, if any). They
    implement show() and save(), and is_available() and can_show() if the
    backend is not always available or able to show plots. Backends with a
    viewer (see mcpl.view) set viewer_module to the name of the module (in
    this package) with its run_viewer function. Options can be
    given as keyword arguments to __init__, named with the backend name as
    prefix (like matplotlib_backend)."""
    name = None
    kind = None
    priority = 0
    formats: ClassVar[dict] = {}
    requirement = None
    viewer_module = None
    #Options to use when plots are only saved in files, e.g. by mcpltool (like
    #a backend of matplotlib which needs no display):
    batch_options: ClassVar[dict] = {}

    @classmethod
    def is_available( cls ):
        """Whether the backend can be used (e.g. if its requirement is
        installed). This should not import any heavy modules."""
        return True

    @classmethod
    def supports_viewer( cls ):
        return cls.viewer_module is not None

    def run_viewer( self, viewer ):
        """Run the viewer (a mcpl._viewer.Viewer) until it is closed"""
        if not self.supports_viewer():
            raise MCPLError(f'The {self.name} plotting backend has no viewer')
        #(loaded when needed, like the modules of the backends):
        mod = importlib.import_module(f'.{self.viewer_module}',__package__)
        mod.run_viewer(viewer,self)

    @classmethod
    def can_show( cls ):
        """Whether the backend can show plots here (e.g. if there is a
        display), assuming that it is available."""
        return True

    @classmethod
    def available_formats( cls ):
        """File extensions which save() can create in this installation"""
        return tuple(cls.formats)

    def resolution( self ):
        """Number of bins which histograms should have to match the resolution
        of the plots, as a tuple (nx,ny) for the two axes, or None if the
        backend has no preference (like matplotlib, which draws
        bins at any resolution). The text backends return the numbers of
        columns and rows of their plots, so histograms with that many bins
        are shown without any resampling."""
        return

    def show( self, figures ):
        """Show the figures interactively."""
        raise NotImplementedError

    def save( self, figures, filename ):
        """Save the figures in a file, with format given by the extension of
        the filename (one of the available formats). If the format can only
        hold a single figure, and there are more figures, files with numbered
        names are created (e.g. plot_1.png, plot_2.png). Returns the list of
        created files."""
        raise NotImplementedError

    def check_format( self, filename ):
        """Extension of filename, if it is an available format (otherwise
        MCPLError is raised)."""
        ext = _extension(filename)
        avail = self.available_formats()
        if ext not in avail:
            raise MCPLError(f'The {self.name} plotting backend can not create'
                            f' .{ext} files (supported: '
                            + ', '.join(f'.{e}' for e in avail) + ')')
        return ext

def _extension( filename ):
    return pathlib.Path(filename).suffix.lower().lstrip('.')

def numbered_filenames( filename, n ):
    """Filenames for n figures: just filename if n==1, otherwise with
    numbers added before the extension."""
    if n == 1:
        return [ filename ]
    p = pathlib.Path(filename)
    return [ str(p.with_name(f'{p.stem}_{i+1}{p.suffix}')) for i in range(n) ]

#Registered backends, as names of the modules implementing the built-in ones
#(loaded when needed, with the name of the class after a colon if it is not
#Backend), or classes. Which one is used is decided by their attributes (kind,
#priority, formats, ...):
_registry = { 'matplotlib' : '_plotbackend_mpl',
              'unicode' : '_plotbackend_text:UnicodeBackend',
              'ascii' : '_plotbackend_text:AsciiBackend' }
#Backend for unit tests (not listed by available_backends):
_hidden = { 'test' : '_plotbackend_test' }
#Default backend set with set_default_backend (name or PlotBackend object):
_default = None

def _backend_class( name, source = None ):
    entry = _registry.get(name) or _hidden.get(name)
    if entry is None:
        raise MCPLError(f'Unknown plotting backend "{name}"{_from(source)}. The'
                        ' plotting backends are: ' + ', '.join(_registry))
    if isinstance(entry,str):
        modname, _, clsname = entry.partition(':')
        mod = importlib.import_module(f'.{modname}',__package__)
        entry = getattr(mod,clsname or 'Backend')
    return entry

def _from( source ):
    return f' (selected with {source})' if source else ''

def _register_backend( cls ):
    if not ( isinstance(cls,type) and issubclass(cls,PlotBackend) ):
        raise MCPLError('register_backend must be called with a subclass of'
                        ' mcpl.plotting.Backend')
    if not ( isinstance(cls.name,str) and cls.name ):
        raise MCPLError('Plotting backends must have a name')
    if cls.name in _registry or cls.name in _hidden:
        raise MCPLError(f'A plotting backend named "{cls.name}" is already'
                        ' registered')
    if cls.kind not in ( 'window', 'terminal', None ):
        raise MCPLError('The kind of a plotting backend must be "window",'
                        ' "terminal" or None')
    _registry[cls.name] = cls

def _ordered( classes ):
    """Backends in order of preference for showing plots: those showing them
    in a window first, then those for the terminal (each by
    priority, and otherwise in the order of registration)."""
    classes = list(classes)
    return sorted( classes, key = lambda c : ( c.kind is None,
                                               c.kind == 'terminal',
                                               -c.priority,
                                               classes.index(c) ) )

def _all_classes():
    return [ _backend_class(n) for n in _registry ]

def _available_backends():
    return [ c.name for c in _ordered(_all_classes()) if c.is_available() ]

def _set_default_backend( backend ):
    global _default
    if backend is not None and not isinstance(backend,PlotBackend):
        if not isinstance(backend,str):
            raise MCPLError('set_default_backend must be called with the name'
                            ' of a plotting backend, a mcpl.plotting.Backend'
                            ' object, or None')
        _backend_class(backend)#check that the name is known
    _default = backend

def _chosen( backend ):
    """Backend selected (name or object), and how it was selected (for error
    messages), or (None,None) if it should be chosen automatically"""
    if backend is not None:
        return backend, None
    if _default is not None:
        return _default, 'set_default_backend'
    return None, None

def _explicit( b, source ):
    """Class (or object) of an explicitly selected backend, which must be
    available"""
    if isinstance(b,PlotBackend):
        return b
    if not isinstance(b,str):
        raise MCPLError('The backend must be the name of a plotting backend or'
                        ' a mcpl.plotting.Backend object')
    cls = _backend_class(b,source)
    if not cls.is_available():
        raise MCPLError(f'The {b} plotting backend{_from(source)} is not'
                        ' available' + ( f' (install the {cls.requirement}'
                                         ' Python package)' if cls.requirement else '' ))
    return cls

def _show_backend( backend = None, terminal = False ):
    """Backend class (or object) for showing plots: the given or default one,
    or else the preferred available backend which can show plots (in the
    terminal if terminal is True). A note is printed when plots are shown in
    the terminal only because the preferred backend is not installed."""
    b, source = _chosen(backend)
    if b is not None:
        cls = _explicit(b,source)
        if not isinstance(cls,PlotBackend) and not cls.can_show():
            if cls.kind == 'terminal':
                raise MCPLError(f'The {cls.name} plotting backend{_from(source)}'
                                ' does not work in this terminal (a solution'
                                ' might be to switch terminal or try the ascii'
                                ' or matplotlib backends)')
            raise MCPLError(f'The {cls.name} plotting backend{_from(source)}'
                            ' can not show plots here (is there no display?)')
        return cls
    ordered = [ c for c in _ordered(_all_classes()) if c.kind is not None ]
    if not terminal:
        others = [ c for c in ordered if c.kind != 'terminal' ]
        for cls in others:
            if cls.is_available() and cls.can_show():
                return cls
        if others and not others[0].is_available() and others[0].requirement:
            from ._messages import _info
            _info(f'Showing plots in the terminal, since {others[0].requirement}'
                  ' is not installed')
    for cls in ordered:
        if cls.kind == 'terminal' and cls.is_available() and cls.can_show():
            return cls
    raise MCPLError('No plotting backend can show plots here')

def _viewer_backend( backend = None, terminal = False ):
    """Backend class (or object) for the viewer: the given or default one
    (which must have a viewer), or else the preferred available backend with
    a viewer which can show plots here (in the terminal if terminal is
    True)."""
    b, source = _chosen(backend)
    if b is not None:
        cls = _show_backend(backend,terminal)
        if not cls.supports_viewer():
            names = ', '.join( c.name for c in _ordered(_all_classes())
                               if c.kind is not None and c.supports_viewer() )
            raise MCPLError(f'The {cls.name} plotting backend{_from(source)} has'
                            f' no viewer (the viewer is shown with the backends {names})')
        return cls
    ordered = [ c for c in _ordered(_all_classes())
                if c.kind is not None and c.supports_viewer()
                and ( c.kind == 'terminal' or not terminal ) ]
    for cls in ordered:
        if cls.is_available() and cls.can_show():
            if cls.kind == 'terminal' and not terminal:
                missing = [ c.requirement for c in ordered if c.kind != 'terminal'
                            and not c.is_available() and c.requirement ]
                if missing:
                    from ._messages import _info
                    _info(f'Showing the viewer in the terminal, since {missing[0]}'
                          ' is not installed')
            return cls
    raise MCPLError('No plotting backend can show the viewer here')

def _save_backend( filename, backend = None ):
    """Backend class (or object) for saving plots in filename: the given or
    default one, or else the available backend with the highest priority for
    the format given by the extension of the filename."""
    ext = _extension(filename)
    b, source = _chosen(backend)
    if b is not None:
        cls = _explicit(b,source)
        if not ext:
            raise MCPLError(f'The file name {filename} has no extension (which'
                            ' gives the format of the plots, e.g. .'
                            + ', .'.join(cls.available_formats()) + ')')
        return cls
    classes = [ c for c in _ordered(_all_classes()) if c.kind is not None ]
    known = []
    for c in classes:
        known += [ e for e in c.formats if e not in known ]
    if not ext or ext not in known:
        what = ( f'The file name {filename} has no extension' if not ext else
                 f'Plots can not be saved as .{ext} files' )
        raise MCPLError(f'{what} (the extension gives the format of the plots: '
                        + ', '.join( f'.{e}' for e in known ) + ')')
    cands = [ c for c in classes if ext in c.formats ]
    avail = [ c for c in cands if c.is_available() and ext in c.available_formats() ]
    if not avail:
        reqs = [ c.requirement for c in cands if c.requirement ]
        raise MCPLError(f'Plots can not be saved as .{ext} files in this'
                        ' installation' + ( f' (install the {reqs[0]} Python'
                                            ' package)' if reqs else '' ))
    return max( avail, key = lambda c : ( _format_priority(c,ext), c.priority ) )

def _format_priority( cls, ext ):
    """Priority of the backend class for creating files of the format (the
    formats can also be given as a list without priorities)"""
    f = cls.formats
    return f.get(ext,0) if isinstance(f,dict) else 0

def _option_names( cls ):
    """The names of the options of a backend class"""
    return set(inspect.signature(cls).parameters)

def _create( b, **options ):
    """Backend object from class (or object) b, with the options."""
    if isinstance(b,PlotBackend):
        if options:
            raise MCPLError('Options for plotting backends ('
                            + ', '.join(sorted(options)) + ') can not be used'
                            ' together with a mcpl.plotting.Backend object')
        return b
    unsupported = set(options) - _option_names(b)
    if unsupported:
        raise MCPLError(f'Unsupported option(s) for the {b.name} plotting'
                        ' backend: ' + ', '.join(sorted(unsupported)))
    return b(**options)

def _formats( backend = None ):
    """File extensions which the backend (or else any available backend) can
    create"""
    b, source = _chosen(backend)
    if b is not None:
        return tuple(_explicit(b,source).available_formats())
    res = []
    for c in _ordered(_all_classes()):
        if c.kind is not None and c.is_available():
            res += [ e for e in c.available_formats() if e not in res ]
    return tuple(res)
