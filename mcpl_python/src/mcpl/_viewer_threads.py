
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

"""The threads of the viewers, which read the file, write files, and the like,
while the viewer shows its windows.

The windows and plots (of Tk, matplotlib, and curses) are only used in the main
thread, which also decides when it looks at what the threads did (it polls
them). The threads only work with MCPL data, and never use the windows:

  * This module is the only one of the package which starts threads (with
    start), and those only run functions of the modules in worker_modules,
    which import (also inside functions) no modules of windows and plots,
    directly or indirectly (both are checked by the test pyviewerthreads).

  * start refuses functions which could bring other objects into a thread
    (lambdas and other functions with variables of where they were made, and
    methods of objects of other modules), and arguments which are not plain
    values (like numbers, strings, and numpy arrays) or objects of the
    worker_modules.

What a thread finds is given to the main thread with a Mailbox."""

__all__ = []

import pathlib
import threading
import types

#The modules whose functions threads run, and whose objects they get:
worker_modules = ( '_viewer_threads', '_viewer_reading', '_viewer_align',
                   '_viewer_output', '_expressions' )

_package = __name__.rpartition('.')[0]

def _module_ok( name ):
    """Whether the module (a full name) is one of the worker_modules"""
    pkg, _, mod = ( name or '' ).rpartition('.')
    return pkg == _package and mod in worker_modules

def _check_function( fct ):
    if isinstance(fct,types.MethodType):
        if not _module_ok(type(fct.__self__).__module__):
            raise TypeError(f'Threads do not get methods of {type(fct.__self__).__name__}'
                            ' objects (see _viewer_threads)')
        fct = fct.__func__
    if not isinstance(fct,types.FunctionType):
        raise TypeError(f'Threads only run functions, not {fct!r} (see _viewer_threads)')
    if fct.__closure__ or '<' in fct.__qualname__:
        raise TypeError(f'Threads do not run lambdas or functions made in other functions'
                        f' ({fct.__qualname__}, see _viewer_threads)')
    if not _module_ok(fct.__module__):
        raise TypeError(f'Threads do not run functions of {fct.__module__}'
                        ' (see _viewer_threads)')

def _check_argument( arg ):
    if arg is None or isinstance(arg,(bool,int,float,str,bytes,pathlib.PurePath)):
        return
    if isinstance(arg,(tuple,list,frozenset)):
        for a in arg:
            _check_argument(a)
        return
    if isinstance(arg,( types.FunctionType, types.MethodType, types.BuiltinFunctionType,
                        types.BuiltinMethodType )):
        _check_function(arg)
        return
    t = type(arg)
    if t.__module__ == 'numpy' or t.__module__.startswith('numpy.'):
        if getattr(arg,'dtype',None) is not None and arg.dtype.hasobject:
            raise TypeError('Threads do not get numpy arrays of objects (see _viewer_threads)')
        return
    if not _module_ok(t.__module__):
        raise TypeError(f'Threads do not get {t.__name__} objects (see _viewer_threads)')

def start( fct, *args ):
    """Start a thread running fct(*args), after checking them (see the module
    docstring). Returns the thread (a daemon thread, so it does not keep the
    program running)."""
    _check_function(fct)
    for a in args:
        _check_argument(a)
    thread = threading.Thread( target = _run, args = ( fct, args ), daemon = True )
    thread.start()
    return thread

def _run( fct, args ):
    try:
        fct(*args)
    finally:
        for a in args:
            if isinstance(a,Mailbox):
                a._done.set()

class Mailbox:
    """What a thread gives to the main thread (with put), which the main thread
    takes when it looks (with take), and whether it should stop (stop, and
    stopped in the thread). done is set when the thread (which got the
    mailbox as an argument of start) ended."""
    def __init__( self ):
        self._lock, self._items = threading.Lock(), []
        self._stop, self._done = threading.Event(), threading.Event()

    def put( self, item ):
        with self._lock:
            self._items.append(item)

    def take( self ):
        """The items put since the last call (a list)"""
        with self._lock:
            items, self._items = self._items, []
        return items

    def stop( self ):
        self._stop.set()

    def stopped( self ):
        return self._stop.is_set()

    @property
    def done( self ):
        return self._done.is_set()
