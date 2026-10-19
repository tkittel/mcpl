
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

# Test the core of the viewer (mcpltool -w and mcpl.view) without a display:
# the views and their figures (which must be identical to those of -S and
# -H), the fields with their checks, completions and history, the commands,
# writing files, and the viewer in the terminal on a screen in memory.

import pathlib
import shutil
import subprocess
import sys

import mcpldev as mcpl
from mcpldev import _viewer_ui as ui
from mcpldev._plotbackend_test import describe
from mcpldev._plotbackend_text import AsciiBackend
from mcpldev._plotbackend_text_gui import TextViewer, _ansi_segments
from mcpldev._reader import MCPLFile, _FileView
from mcpldev._viewer import Viewer
from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )
ex = 'example.mcpl'

def same( a, b ):
    return describe([a]) == describe([b])

#The added plots of test_figures:
_plots = [ 'ekin/MeV;logx=1;split=pdgcode', 'x/cm : y/cm;bins=10', 'wavelength;logy=1' ]

def test_figures():
    from mcpldev._stdviews import _collections
    _default_plots = _collections['default'][1]
    for skip, limit, pick, edit in ( (0,None,None,None),
                                     (0,None,'pdgcode == neutron',None),
                                     (100,500,'ekin > 1MeV','z += 1m'),
                                     (0,None,'mod(fileidx,3) == 0','weight *= 2') ):
        v = Viewer(ex,skip=skip,limit=limit,pick=pick,edit=edit,
                   plots=_plots)
        v.multi_overview = True#(as in the matplotlib window)
        v.start()
        v.wait()
        keys = [ k for k, _ in v.views ]
        figs = { k : v.figure(i) for i, k in enumerate(keys) }
        #Each plot is as with mcpltool -H (with the pick and edit expressions
        #as titles), and the overview has the first ones:
        title = '\n'.join( f'{w}: {e}' for w, e in (('pick',pick),('edit',edit)) if e )
        src = _FileView(MCPLFile(ex),skip,limit,
                        mcpl.ParticleFilter(pick) if pick else None,
                        mcpl.ParticleEdit(edit) if edit else None)
        ok, failed = True, []
        for p in list(_default_plots) + _plots:
            try:
                h = mcpl.histogram(src,p)
            except mcpl.MCPLError as e:
                failed.append( ( p, str(e) ) )
                ok &= str(e) in str(describe([figs[f'plot:{p}']]))
                continue
            h.title = title or None
            ok &= same(figs[f'plot:{p}'],h.figure())
        ov = figs['overview:multi']
        ok &= [ describe([mcpl.plotting.Figure(panels=[pn])]).split('\n',1)[1]
                for pn in ov.panels ] == [
                    describe([mcpl.plotting.Figure(panels=[ figs[k].panels[0] ])]).split('\n',1)[1]
                    .replace(f"Panel {figs[k].panels[0].title!r}","Panel None",1)
                    for k in v.overview_keys() ]
        print(f'skip={skip} limit={limit} pick={pick!r} edit={edit!r}:')
        print(f'   {v.status_lines()[0]}')
        print(f'   {len(v.views)} views, same figures as mcpltool -H: {ok}')
        for p, e in failed:
            print(f'   plot {p!r} shows: {e}')
        assert ok
        v.stop()

def test_collections():
    import shlex

    from mcpldev._stdviews import _collections, _default_collection
    assert _default_collection in _collections
    #The names of the collections can never be views (plots), as they are not
    #valid expressions or plots (so -wNAME can be either):
    for name in _collections:
        for check in ( mcpl.ParticleValue, mcpl.ParticleFilter ):
            try:
                check(name)
            except mcpl.MCPLError:
                continue
            raise AssertionError(f'collection name {name!r} is a valid expression')
        assert not Viewer(ex).check('plot',name)[0], f'collection name {name!r} is a valid plot'
    #All plots of all collections work:
    for name, ( descr, plots ) in _collections.items():
        assert len(set(plots)) == len(plots)
        for p in plots:
            mcpl.histogram(ex,p)
        print(f'collection {name}: {descr}, {len(plots)} plots, first: {plots[0]!r}')
    v = Viewer(ex,view='beamz',plots=['x;bins=5'])
    print('-wbeamz:', v.field_text('collection'), [ k for k, _ in v.views ][:2],
          '| state:', v.state(), '| command:', v.commands()['view'])
    v.change_plot('x : y','x/mm : y/mm')
    print('changed:', v.state(full = False))
    print('check:', v.check('collection','beam'), v.check('collection',''))
    print('completions:', v.complete('collection','beam'), '| hint:', v.hint('collection','beamx'))
    g = v._generation
    print('same collection:', v.set('collection','beamz'), 'restarted:', v._generation != g)
    print('switched:', v.set('collection','shielding'), [ k for k, _ in v.views ][:2],
          'added plot kept:', v._s.plots[-1], '| state:', v.state(full = False))
    arg = shlex.split(v.commands()['view'])[1]
    w = Viewer(ex,view=arg.split('=',1)[1] if arg.startswith('--') else arg[2:])
    print('opened with the command: same state:', w.state() == v.state())
    for bad in ( "{'collection':'nope'}", "{'collection':3}" ):
        try:
            Viewer(ex,view=bad)
        except mcpl.MCPLError as e:
            print(f'view {bad!r}: {e}')

def test_state():
    import json
    import shlex
    v = Viewer(ex)
    v.multi_overview = True
    print('state at the start:', v.state(), '| command:', v.commands()['view'])
    v.select(2)
    print('move up:', v.move(-1), 'down twice:', v.move(1), v.move(1), '| current:', v.views[v.current][0])
    v.select(0)
    print('move the overview:', v.move(1))
    v.select(len(v.views)-1)
    print('move the last down:', v.move(1))
    v.change_plot('ekin','ekin/keV;logy=1')
    v.change_plot('polx','')
    v.set('plot','hypot(x,y)/cm')
    v.set('pick','pdgcode != gamma')
    v.set('limit','500')
    print('state:', v.state())
    print('state without the options:', v.state(full = False))
    cmd = v.commands()['view']
    print('command:', cmd)
    args = shlex.split(cmd)
    w = Viewer(ex,view=args[1].split('=',1)[1],pick=args[4],limit=500)
    w.multi_overview = True
    print('opened with the command: same state:', w.state() == v.state(),
          '| current:', w.views[w.current][0])
    fn = 'example_viewer.json'
    print('suggested state file:', v.suggested_state_filename())
    print('save:', v.try_save_state(fn))
    print('save again:', v.try_save_state(fn))
    print('suggested state file now:', v.suggested_state_filename())
    print('saved:', json.loads(pathlib.Path(fn).read_text()) == v.state())
    w = Viewer(ex,view=fn)
    w.multi_overview = True
    print('opened from the file: same state:', w.state() == v.state())
    w = Viewer(ex,view=fn,limit=7,plots=['x;bins=5'])
    print('arguments after the state:', w.field_text('limit'), w._s.plots[-1])
    d = Viewer(ex,dry_run=True)
    print('dry run:', d.try_save_state('dry.json'), pathlib.Path('dry.json').exists())
    for view in ( 'x', ' x ', 'overview', 'pdgcode;bar = auto ; logy=auto' ):
        w = Viewer(ex,view=view)
        print(f'view {view!r}:', w.views[w.current][0])
    for bad in ( "{'foo':1}", '{"limit":"a"}', "{'plots':{'change':{'nope':'x'}}}",
                 "{'plots':{'remove':['x;bins=7']}}", "{'plots':{'foo':[]}}",
                 "{'plots':{'add':['x;bins=0']}}", "{bad", "[1]", "nope.json", 'nope' ):
        try:
            Viewer(ex,view=bad)
            print(f'view {bad!r}: no error')
        except mcpl.MCPLError as e:
            print(f'view {bad!r}: {e}')

def test_fields():
    v = Viewer(ex)
    print('views:', ', '.join( k for k, _ in v.views ))
    for field, text in ( ('skip','10'), ('skip','x'), ('limit','all'),
                         ('limit','-5'), ('limit',' 1e6 '), ('limit','2.5e3'),
                         ('limit','1.5'), ('limit','1e400'), ('limit','nan'),
                         ('pick','pdgcode == neutron'),
                         ('pick','x > 1'), ('pick','x > 0 && y > 0'),
                         ('edit','z += 1cm;weight *= 0.5'), ('edit','x = 2'),
                         ('edit','fileidx = 1'), ('plot','ekin/MeV;logx=1'),
                         ('plot','ekin'), ('plot','ekin/MeV;print=1'),
                         ('plot',''), ('plot','x/cm : y/cm;range=1:2') ):
        print(f'check({field!r},{text!r}): {v.check(field,text)}')
    for field, text, cursor in ( ('pick','pdgcode == neu',None),
                                 ('pick','ek',None), ('pick','sq',None),
                                 ('edit','rot',None), ('plot','ekin/MeV;lo',None),
                                 ('plot','hyp',None), ('skip','1',None) ):
        print(f'complete({field!r},{text!r}): {v.complete(field,text,cursor)}')
    for text, cursor in ( ('ekin > 1MeV',2), ('pdgcode == gamma',None), ('x',None),
                          ('1 + 2',None) ):
        print(f'hint({text!r},{cursor}): {v.hint("pick",text,cursor)}')
    for field, typed in ( ('plot',''), ('plot','ek'), ('plot','ekin/MeV'), ('skip','x') ):
        e = ui.LineEditor(v,field)
        for c in typed:
            e.key(c)
        print(f'hint line while editing {field} with {typed!r}:', ui.hint_line(e))
    #Choosing a completion with Up and Down, and inserting it:
    e = ui.LineEditor(v,'plot')
    for k in ['e','Tab','Down','Down']:
        e.key(k)
    print('completions of "e":', [ n for n, _ in e.choices ], 'chosen:', e.choices[e.selected][0],
          '| list line:', ui.hint_line(e)[0], '| popup line:', ui.hint_line(e,popup=True)[0])
    print('Enter inserts it:', e.key('Enter'), repr(e.text), 'completions left:', e.choices)
    for k in ['Backspace','Backspace','Tab','Up']:
        e.key(k)
    print('Up from the first wraps to:', e.choices[e.selected][0], end=' ')
    print('| Esc closes without inserting:', e.key('Esc'), repr(e.text), e.choices)
    print('unknown view:', end=' ')
    try:
        Viewer(ex,view='foo')
    except mcpl.MCPLError as e:
        print(e)
    try:
        Viewer(ex,pick='x > 1')
    except mcpl.MCPLError as e:
        print('invalid pick:', e)

def test_reading():
    v = Viewer(ex,plots=['time/ms;logx=1'],view='ekin')
    print('view shown first:', v.views[v.current])
    v.start()
    v.wait()
    print(v.status_lines())
    for field, text in ( ('pick','pdgcode == gamma'), ('skip','1000'), ('limit','3'),
                         ('pick','x > 1km'), ('pick',''), ('skip','0'), ('limit','') ):
        ok, _ = v.set(field,text)
        v.wait()
        print(f'set({field!r},{text!r}): {ok}, {v.status_lines()}')
    v.set('plot','ekin/MeV')
    v.set('plot','time/ms;logx=1')#(already there, so it is shown)
    print('views after adding plots:', [ k for k, _ in v.views ][-2:], 'current:',
          v.views[v.current][0])
    v.set('limit','1e3')
    print('limit 1e3:', v.field_text('limit'), v.commands()['view'])
    v.set('limit','')
    print('history of pick:', v.history('pick'))
    for k, c in v.commands().items():
        print(f'command {k}: {c}')
    v.select(0)
    print('commands of the overview:', v.commands())
    #Texts written differently are compared normalised:
    w = Viewer(ex,pick='pdgcode == neutron',plots=['ekin/MeV;logx=1;bins=50'])
    g = w._generation
    print('same pick, written differently:', w.set('pick','pdgcode==neutron'),
          'restarted:', w._generation != g, repr(w.field_text('pick')))
    print('limit 1e3 then 1000:', w.set('limit','1e3'), w.set('limit','1000'),
          'restarts:', w._generation - g)
    print('same plot, written differently:', w.set('plot','ekin / MeV ; bins=50;logx=1'),
          'plots:', w._s.plots, 'current:', w.views[w.current][0])
    print('changed to the same plot:', w.change_plot('ekin/MeV;logx=1;bins=50','ekin/MeV ;bins=50; logx=1'),
          'plots:', w._s.plots)
    #Changing and removing added plots:
    print('unchanged:', v.change_plot('ekin/MeV',' ekin/MeV '), [ k for k, _ in v.views ][-2:],
          'current:', v.views[v.current][0])
    print('change to keV:', v.change_plot('ekin/MeV','ekin/keV'), [ k for k, _ in v.views ][-2:],
          'current:', v.views[v.current][0])
    print('change to an existing plot:', v.change_plot('ekin/keV','time/ms;logx=1'),
          [ k for k, _ in v.views ][-2:])
    print('invalid change:', v.change_plot('time/ms;logx=1','foo'))
    print('unknown plot:', v.change_plot('nope','ekin'))
    print('remove:', v.change_plot('time/ms;logx=1',''), [ k for k, _ in v.views ][-1:],
          'current:', v.views[v.current][0])
    v.stop()

def test_write():
    v = Viewer(ex,pick='pdgcode == neutron',edit='z += 1m',dry_run=True)
    print('suggested name:', v.suggested_filename())
    print('dry run:', v.write())
    print('files after the dry run:', sorted( p.name for p in pathlib.Path('.').glob('example_selected*') ))
    v = Viewer(ex,pick='pdgcode == neutron',edit='z += 1m')
    print('written:', v.write().splitlines()[-1])
    print('next suggested name:', v.suggested_filename())
    pathlib.Path('example_selected2.mcpl').write_bytes(b'')
    print('next suggested name:', v.suggested_filename())
    try:
        v.write('example_selected.mcpl.gz')
    except mcpl.MCPLError as e:
        print('existing file:', e)
    with mcpl.MCPLFile('example_selected.mcpl.gz') as f:
        print(f'written file: {f.nparticles} particles, comments: {f.comments[-1]!r}')
    print(ui.closing_text(v))
    print('without pick and edit:')
    print(ui.closing_text(Viewer(ex,limit=100)))

class FakeScreen:
    """A screen in memory, with the keys to give"""
    colors = True
    def __init__( self, keys, h = 44, w = 110 ):
        self.h, self.w, self.keys = h, w, list(keys)
        self.clear()
    def size( self ):
        return ( self.h, self.w )
    def clear( self ):
        self.grid = [ [' '] * self.w for _ in range(self.h) ]
    def put( self, y, x, text, style = 'normal' ):
        if 0 <= y < self.h:
            for i, c in enumerate(text):
                if 0 <= x + i < self.w:
                    self.grid[y][x+i] = c
    def refresh( self ):
        pass
    def getkey( self ):
        self.last = self.text()
        self.frames = getattr(self,'frames',[]) + [ self.last ]
        while self.keys:
            k = self.keys.pop(0)
            if k == 'WAIT':
                self.viewer.wait()
                return None
            if k == 'Ctrl-C':
                raise KeyboardInterrupt
            return k
        #(Esc ends the editing of a field, if any, and q quits):
        self.ending = not getattr(self,'ending',False)
        return 'Esc' if self.ending else 'q'
    def text( self ):
        return '\n'.join( ''.join(r).rstrip() for r in self.grid ).rstrip()

def test_terminal():
    def run( keys, show = True, backend = None, **kw ):
        v = Viewer(ex,**kw)
        s = FakeScreen(keys)
        s.viewer = v
        t = TextViewer(v,s,backend)
        t.run()
        print(f'==> keys {keys}:')
        if show:
            for line in s.text().splitlines():
                print(f'   | {line}')
        return v, t
    run(['WAIT','p'] + list('pdgcode == neu') + ['Tab','Enter','WAIT','Down','Down','Down','WAIT'])
    run(['WAIT','e'] + list('x = 2') + ['WAIT'])
    v, _ = run(['WAIT','a'] + list('hypot(x,y)/cm;lo') + ['Tab'] + list('y=1') + ['Enter','WAIT'],
               show = False)
    print('   views:', [ k for k, _ in v.views ][-1], 'current:', v.views[v.current][0])
    #Enter on an added plot changes it (and an empty text removes it):
    v, _ = run(['WAIT','a'] + list('ekin/MeV') + ['Enter','WAIT','Enter']
               + ['Backspace'] * 3 + list('keV') + ['Enter','WAIT'],show=False)
    print('   changed with Enter:', [ k for k, _ in v.views ][-1], 'current:', v.views[v.current][0])
    v, _ = run(['WAIT','a'] + list('ekin/MeV') + ['Enter','WAIT','Enter','Enter','WAIT'],show=False)
    print('   Enter twice keeps the plot:', [ k for k, _ in v.views ][-1], 'current:', v.views[v.current][0])
    w = Viewer(ex,plots=['ekin/MeV'],view='ekin/MeV')
    e = ui.editor_for(w,'change')
    print('   Enter on an added plot, editing:', repr(e.text), '| hint line when emptied:', end=' ')
    for _ in e.text:
        e.key('Backspace')
    print(ui.hint_line(e), e.ok)
    v, _ = run(['WAIT','a'] + list('ekin/MeV') + ['Enter','WAIT','Enter']
               + ['Backspace'] * 8 + ['Enter','WAIT'],show=False)
    print('   removed with an empty text:', [ k for k, _ in v.views ][-1], 'current:', v.views[v.current][0])
    print('   Enter on another view, editing:', ui.editor_for(Viewer(ex),'change') is not None)
    run(['WAIT','h'],show=False)
    #Moving the shown plot (Up and Down with Shift, Ctrl, Alt, ...):
    v, _ = run(['WAIT','Down','Down','MoveUp','WAIT'],show=False)
    print('   moved up:', v._s.plots[:3], 'current:', v.views[v.current][0])
    #c changes the collection of plots (the field starts with the current one):
    v, _ = run(['WAIT','c'] + ['Backspace'] * 7 + list('beamx') + ['Enter','WAIT'],show=False)
    print('   c changes the collection:', v.field_text('collection'), v.views[v.current][0])
    before = set(pathlib.Path('.').glob('*.json'))
    run(['WAIT','v','Enter','WAIT'],show=False)
    print('   v saves the state in:', sorted( str(f) for f in set(pathlib.Path('.').glob('*.json')) - before ))
    v, _ = run(['WAIT','s','1','2','Esc','i','5','0','Enter','WAIT','p','Up','Esc'],show=False)
    print('   skip, limit:', repr(v.field_text('skip')), repr(v.field_text('limit')),
          v.status_lines()[0])
    v, _ = run(['WAIT',('Mouse',2,3,True),'WAIT'],show=False)
    print('   view after clicking on line 3:', v.views[v.current][0])
    v, _ = run(['WAIT','p','x','Ctrl-C','p','y'],show=False)
    print('   Ctrl-C quits like q, while editing a field:', repr(v.field_text('pick')),
          'running:', v._thread is not None and v._thread.is_alive())
    #The completions in a popup above the field:
    v, t = run(['WAIT','a','e','Tab','Down'],show=False)
    lines = next( f for f in t.s.frames[::-1] if '\u2510' in f ).splitlines()
    y0 = next( i for i, line in enumerate(lines) if '\u2510' in line and '\u250c' in line )
    x0, x1 = lines[y0].index('\u250c'), lines[y0].index('\u2510')
    print('   popup of the completions:')
    for line in lines[y0:]:
        print('   |', line[x0:x1+1])
        if line[x0:x0+1] == '\u2514':
            break
    #With the ascii backend, only ASCII characters are shown:
    v, t = run(['WAIT','p'] + list('pdgcode == neu') + ['WAIT'],show=False,
               backend=AsciiBackend(),view='pdgcode;bar;logy=auto')
    text = t.s.last
    print('   ascii backend, only ASCII characters:', text.isascii(),
          '| selected view:', [ ln.strip() for ln in text.splitlines() if ln.startswith('>') ][:1])
    print('ANSI segments:', _ansi_segments('ab\x1b[31mcd\x1b[0me\x1b[32;41mf\x1b[0m'))

def test_tool():
    for args in ( ['-w','-S'], ['-w','-o','x.pdf'], ['-H','x/cm','-H','y/cm'],
                  ['-w','-B','ascii'], ['--view=foo'], ['-w','--color=always'],
                  ['-w','-p','x > 1'], ['-wekin','-w'] ):
        rv = subprocess.run([sys.executable,'-m','mcpldev',*args,ex],
                            capture_output=True,text=True,check=False)
        print(f'mcpltool {" ".join(args)}: exit code {rv.returncode}')
        print(f'   | {rv.stdout.splitlines()[0] if rv.stdout else ""}')
    rv = subprocess.run([sys.executable,'-m','mcpldev','-w',ex,ex],
                        capture_output=True,text=True,check=False)
    print(f'mcpltool -w with two files: {rv.stdout.splitlines()[0]}')

test_figures()
test_fields()
test_reading()
test_collections()
test_state()
test_write()
test_terminal()
test_tool()
