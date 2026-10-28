
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

# Test the selection of plotting backends (by name, with set_default_backend,
# and automatically, for showing plots or for saving them in files of a
# format), custom backends registered with register_backend, Backend objects,
# backend options, and the -B, -t and -o options of mcpltool.

import os
import subprocess
import sys

import mcpldev as mcpl
from mcpldev.plotting import Backend, Figure, Panel, Text
from MCPLTestUtils.dirs import test_data_dir

example_file = test_data_dir.joinpath('example.mcpl')
fig = Figure( title = 'A figure', panels = [ Panel( items = [ Text('Hello') ] ) ] )

class PrintingBackend(Backend):
    """Custom backend printing the titles of the figures"""
    name = 'printing'
    formats = ('txt',)
    def __init__( self, printing_prefix = '' ):
        self._prefix = printing_prefix
    def show( self, figures ):
        for f in figures:
            print(f'{self._prefix}printing backend shows: {f.title!r}')
    def save( self, figures, filename ):
        self.check_format(filename)
        print(f'{self._prefix}printing backend saves {len(figures)} figure(s) in {filename}')
        return [ filename ]

class UnavailableBackend(Backend):
    name = 'unavailable'
    requirement = 'some_missing_package'
    @classmethod
    def is_available( cls ):
        return False

def expect_error( title, fct ):
    try:
        fct()
        print(f'{title}: no error')
    except mcpl.MCPLError as e:
        print(f'{title}: MCPLError: {e}')

def test_registry():
    mcpl.plotting.register_backend(PrintingBackend)
    mcpl.plotting.register_backend(UnavailableBackend)
    avail = mcpl.plotting.available_backends()
    print(f'printing backend available: {"printing" in avail},'
          f' unavailable backend available: {"unavailable" in avail},'
          f' built-in backends first: {avail[-1] == "printing"}')
    mcpl.plotting.show(fig, backend='printing')
    mcpl.plotting.show(fig, backend='printing', printing_prefix='[options] ')
    print(f'formats of the printing backend: {mcpl.plotting.formats("printing")}')
    print(f'formats of the test backend: {mcpl.plotting.formats("test")}')
    expect_error('register_backend(PrintingBackend) again',
                 lambda : mcpl.plotting.register_backend(PrintingBackend))
    expect_error('register_backend(object)', lambda : mcpl.plotting.register_backend(object))
    expect_error('unavailable backend', lambda : mcpl.plotting.show(fig, backend='unavailable'))
    expect_error('unknown option', lambda : mcpl.plotting.show(fig, backend='printing',
                                                                matplotlib_backend='agg'))
    expect_error('wrong format', lambda : mcpl.plotting.save(fig, 'x.pdf', backend='printing'))
    expect_error('backend=42', lambda : mcpl.plotting.show(fig, backend=42))

def test_default():
    for default in ( 'printing', PrintingBackend(printing_prefix='[object] '), None ):
        mcpl.plotting.set_default_backend(default)
        label = 'PrintingBackend object' if isinstance(default,Backend) else repr(default)
        print(f'==> set_default_backend({label}):')
        if default is None:
            print(f'   available backends: {mcpl.plotting.available_backends()}')
            print(f'   formats which can be saved: {mcpl.plotting.formats()}')
            continue
        mcpl.plotting.show(fig)
        mcpl.plotting.show(fig, backend='test')#explicit backend wins
        mcpl.histogram(example_file, 'ekin/MeV', bins=5, display_by='single').plot()
        print(f'   formats: {mcpl.plotting.formats()}')
    obj = PrintingBackend()
    expect_error('Backend object with options',
                 lambda : mcpl.plotting.show(fig, backend=obj, printing_prefix='x'))
    mcpl.plotting.set_default_backend(obj)
    expect_error('default Backend object with options',
                 lambda : mcpl.plotting.show(fig, printing_prefix='x'))
    mcpl.plotting.set_default_backend('unavailable')
    expect_error('unavailable default backend', lambda : mcpl.plotting.show(fig))
    expect_error('set_default_backend("foo")',
                 lambda : mcpl.plotting.set_default_backend('foo'))
    expect_error('set_default_backend(42)',
                 lambda : mcpl.plotting.set_default_backend(42))
    mcpl.plotting.set_default_backend(None)

def test_automatic():
    #Without a backend, the backend for saving is chosen by the format:
    for fn in ( 'auto.txt', 'auto.pdf', 'auto.html', 'auto' ):
        expect_error(f'save(fig, {fn!r})',
                     lambda fn = fn : print(f'   created {mcpl.plotting.save(fig, fn)}'))

def test_tool_backends():
    #-B selects the backend, otherwise it is chosen automatically (by the
    #extension of the file with -o, and for the terminal with -t):
    for args in ( ['-B','test'], ['-B','foo'], ['-t','-B','test'],
                  ['-o','tool1.txt'], ['-o','tool2.txt','-B','test'],
                  ['-o','tool3.txt','-B','ascii'], ['-t'] ):
        sys.stdout.flush()
        #(with UTF-8 output, also on Windows, so the plots in the terminal are
        #drawn with the unicode backend):
        rv = subprocess.run([sys.executable, '-m', 'mcpldev', '-H', 'ekin/MeV;bins=3;display_by=single',
                             *args, str(example_file)],
                            capture_output=True, encoding='utf-8', check=False,
                            env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        print(f'==> mcpltool -H ekin/MeV;bins=3;display_by=single {" ".join(args)}:'
              f' exit code {rv.returncode}')
        for line in rv.stdout.splitlines()[:4]:
            print(f'   | {line}')

if __name__ == '__main__':
    test_registry()
    test_default()
    test_automatic()
    test_tool_backends()
