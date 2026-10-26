
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

# Test colours in the text plotting backends: when they are used (--color,
# NO_COLOR, FORCE_COLOR, TERM, and whether the output is a terminal), the
# number of colours (COLORTERM, TERM), the escape sequences, that the output
# without the escape sequences is the same as without colours, and the
# --color option of mcpltool.

import contextlib
import io
import os
import pathlib
import re
import subprocess
import sys

import mcpldev as mcpl
from mcpldev import _termcolor
from mcpldev._plotbackend_text import AsciiBackend, UnicodeBackend
from mcpldev._termcolor import _code256, _ncolors, _paint
from mcpldev.plotting import Hist2D, StepHist
from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.plots import example_figures

example_file = test_data_dir.joinpath('example.mcpl')

class FakeStream:
    def __init__( self, tty ):
        self._tty = tty
    def isatty( self ):
        return self._tty

@contextlib.contextmanager
def environ( **env ):
    names = ( 'NO_COLOR', 'FORCE_COLOR', 'TERM', 'COLORTERM' )
    old = { n : os.environ.get(n) for n in names }
    for n in names:
        os.environ.pop(n,None)
    os.environ.update( { k : v for k, v in env.items() if v is not None } )
    try:
        yield
    finally:
        for n, v in old.items():
            os.environ.pop(n,None)
            if v is not None:
                os.environ[n] = v

def test_when():
    #(the fake streams are terminals, also on Windows where real terminals are
    #also checked for support of the escape sequences):
    _termcolor._is_terminal = lambda stream : stream.isatty()
    print('Number of colours (stream is a terminal or not):')
    for env in ( {}, {'NO_COLOR':'1'}, {'NO_COLOR':''}, {'FORCE_COLOR':'1'},
                 {'NO_COLOR':'1','FORCE_COLOR':'1'}, {'TERM':'dumb'},
                 {'TERM':'dumb','FORCE_COLOR':'1'}, {'TERM':'xterm-256color'},
                 {'COLORTERM':'truecolor'}, {'COLORTERM':'24bit','TERM':'xterm'} ):
        with environ(**env):
            res = [ f'{when}: {_ncolors(when,FakeStream(True))}'
                    f'/{_ncolors(when,FakeStream(False))}'
                    for when in ('auto','always','never') ]
        print(f'   {env}: ' + ', '.join(res))
    try:
        _ncolors('sometimes')
    except mcpl.MCPLError as e:
        print(f'   _ncolors("sometimes"): MCPLError: {e}')

def test_sequences():
    for n in ( 8, 256, 16777216 ):
        print(f'{n} colours: {_paint("X",n,(31,119,180))!r}'
              f' {_paint("X",n,(253,231,37),(68,1,84))!r}')
    print(f'no colours: {_paint("X",0,(31,119,180))!r}')
    print('256 colour codes of black, white, grey, red:',
          [ _code256(c) for c in ( (0,0,0), (255,255,255), (128,128,128), (255,0,0) ) ])

ansi = re.compile(r'\x1b\[[0-9;]*m')

def shown( backend, figures ):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        backend.show(figures)
    return out.getvalue()

def test_stripped():
    h1 = mcpl.histogram(example_file,'ekin/MeV;logx=1;bins=20;display_by=single')
    hs = mcpl.histogram(example_file,'ekin/MeV;logx=1;display_by=pdgcode;bins=20')
    h2 = mcpl.histogram(example_file,'x/cm : y/cm;bins=10')
    stats = example_figures(mcpl,example_file)[0]
    cases = ( ('1D',h1.figure()), ('split',hs.figure()), ('2D',h2.figure()),
              ('overview',stats) )
    with environ(COLORTERM='truecolor'):
        for cls, opt in ( (UnicodeBackend,'unicode'), (AsciiBackend,'ascii') ):
            for name, fig in cases:
                kw = { f'{opt}_width' : 70, f'{opt}_height' : 8 }
                plain = shown( cls(**kw, **{f'{opt}_color':'never'}), [fig] )
                col = shown( cls(**kw, **{f'{opt}_color':'always'}), [fig] )
                same = ansi.sub('',col) == plain
                print(f'{opt} {name}: colours used: {col != plain},'
                      f' same text without them: {same}')
                has2d = any( isinstance(i,Hist2D) for p in fig.panels for i in p.items )
                curves = any( sum( isinstance(i,StepHist) for i in p.items ) > 1
                              for p in fig.panels )
                if ( has2d or curves ) and opt == 'unicode':
                    #(2D maps are drawn with half blocks, two cells per
                    #character, and several curves are lines of braille dots,
                    #without colour with their markers along them, but
                    #everything else is the same):
                    if has2d:
                        print('   half blocks:', '\u2580' in col and '\u2580' not in plain)
                    if curves:
                        braille = [ any( 0x2800 < ord(ch) <= 0x28ff for ch in t )
                                    for t in ( col, plain ) ]
                        print('   braille lines:', all(braille), '| markers only without colour:',
                              '\u25cb' in plain and '\u25cb' not in ansi.sub('',col))
                    assert not same
                else:
                    assert same
        #Files are written without colours:
        UnicodeBackend(unicode_color='always').save([h1.figure()],'colour.txt')
        print('file without escape sequences:',
              '\x1b' not in pathlib.Path('colour.txt').read_text(encoding='utf-8'))

def tool( *args, **env ):
    sys.stdout.flush()
    e = dict(os.environ)
    for n in ( 'NO_COLOR', 'FORCE_COLOR', 'COLORTERM' ):
        e.pop(n,None)
    e.update(env)
    rv = subprocess.run([sys.executable,'-m','mcpldev',*args,str(example_file)],
                        capture_output=True,env=e,check=False)
    out = rv.stdout.decode('utf-8')
    colours = '\x1b[' in out
    print(f'mcpltool {" ".join(args)} {env if env else ""}: exit code'
          f' {rv.returncode}, colours: {colours}')
    if rv.returncode:
        for line in out.splitlines()[:1]:
            print(f'   | {line}')

def test_tool():
    h = 'ekin/MeV;bins=5;display_by=single'
    tool('-H',h,'-t')
    tool('-H',h,'-t','--color=always')
    tool('-H',h,'-t','--color','always')
    tool('-H',h,'-t','--color=never',FORCE_COLOR='1')
    tool('-H',h,'-t',FORCE_COLOR='1')
    tool('-H',h,'-t','--color=always',NO_COLOR='1')
    tool('-H',h,'-t',NO_COLOR='1',FORCE_COLOR='1')
    tool('-H',h,'-B','ascii','--color=always')
    tool('-H',h,'--color=sometimes')
    tool('-H',h,'--color=always','-o','x.txt')
    tool('-H',h+';print=1','--color=always')
    tool('-S','--color=always')
    tool('-H',h,'-t','--color=always','--color=never')

test_when()
test_sequences()
test_stripped()
test_tool()
