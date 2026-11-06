
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


# NEEDS: numpy

# Test that the threads of the viewers never use objects of the windows and
# plots (see _viewer_threads): only _viewer_threads starts threads, the modules
# whose functions and objects threads get import no modules of windows and
# plots (also not inside functions, directly or indirectly), and start()
# refuses other functions and arguments.

import ast
import importlib.util
import pathlib
import shutil
import time

import numpy as np
from mcpldev import _viewer, _viewer_align, _viewer_output, _viewer_threads
from mcpldev._viewer_threads import Mailbox, start, worker_modules
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.pymoddeps import package_imports

#Packages of windows and plots:
gui_packages = { 'tkinter', 'matplotlib', 'curses', 'PIL', 'IPython', 'ipywidgets' }

pkgdir = pathlib.Path(importlib.util.find_spec('mcpldev').origin).parent
imports = package_imports(pkgdir)

def imported_by( module ):
    """All modules of the package which the module imports, directly or
    indirectly, also inside functions and by name"""
    res, todo = set(), [ module ]
    while todo:
        m = todo.pop()
        if m in res:
            continue
        res.add(m)
        internal, infunc, byname, _ = imports[m]
        todo += sorted( internal | infunc | byname )
    return res

def test_worker_modules():
    for m in worker_modules:
        mods = imported_by(m)
        gui = sorted( ( x, p ) for x in mods for p in imports[x][3] if p in gui_packages )
        print(f'{m}: imports {len(mods)-1} modules of the package, of windows and plots: {gui or "none"}')
        assert not gui, (m, gui)

def thread_calls( path ):
    """The calls in the file which start threads"""
    names = { 'Thread', 'Timer', 'ThreadPoolExecutor', 'start_new_thread', 'start_new' }
    res = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node,ast.Call):
            f = node.func
            name = f.attr if isinstance(f,ast.Attribute) else getattr(f,'id',None)
            if name in names:
                res.append(f'{path.name}:{node.lineno}')
    return res

def test_only_threads_module():
    calls = { f.stem : thread_calls(f) for f in sorted(pkgdir.glob('*.py')) }
    starting = sorted( m for m, c in calls.items() if c )
    print('modules starting threads:', starting)
    assert starting == [ '_viewer_threads' ], calls

class Window:
    """(an object of another module, like a window)"""
    def method( self ):
        pass

def module_function( mailbox ):
    pass

def test_refused():
    window = Window()
    def inner():
        return window
    cases = ( ( 'lambda', lambda : None, () ),
              ( 'function made in a function', inner, () ),
              ( 'method of another object', window.method, () ),
              ( 'function of another module', module_function, ( Mailbox(), ) ),
              ( 'function of the viewer module', _viewer._estimate, () ),
              ( 'object of another module as argument', _viewer_output.try_write_to,
                ( Mailbox(), window ) ),
              ( 'lambda as argument', _viewer_output.try_write_to, ( Mailbox(), lambda : 1 ) ),
              ( 'numpy array of objects as argument', _viewer_output.try_write_to,
                ( Mailbox(), np.array([ window ]) ) ),
              ( 'object in a tuple as argument', _viewer_output.try_write_to,
                ( Mailbox(), ( 1, window ) ) ) )
    for what, fct, args in cases:
        try:
            start(fct,*args)
            print(f'{what}: started!')
        except TypeError as e:
            print(f'{what}: TypeError: {e}')

def test_started():
    #Threads of the viewers, with plain values and a mailbox (and a local copy
    #of the file, for printouts without full paths):
    shutil.copy(test_data_dir.joinpath('example.mcpl'),'example.mcpl')
    ex = 'example.mcpl'
    mailbox = Mailbox()
    start(_viewer_align.read_file_stats,mailbox,ex,0,None,None)
    while not mailbox.done:
        time.sleep(0.01)
    stats = mailbox.take()
    print('align stats:', len(stats), 'results, the last complete:', stats[-1].complete,
          'particles:', stats[-1].n)
    mailbox = Mailbox()
    start(_viewer_output.try_write_to,mailbox,ex,0,10,None,'out.mcpl',False,False)
    while not mailbox.done:
        time.sleep(0.01)
    print('write:', mailbox.take())
    print('worker modules:', worker_modules, 'module:', _viewer_threads.__name__)

test_worker_modules()
test_only_threads_module()
test_refused()
test_started()
