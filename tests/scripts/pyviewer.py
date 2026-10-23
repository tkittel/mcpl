
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

import copy
import pathlib
import runpy
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
    from mcpldev._viewer_groups import PlotGroups
    _default_plots = [ p for p, _, _ in PlotGroups().cards() ]
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
        #as titles), and the overviews have the plots of their groups:
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
                ok &= str(e) in str(describe([figs[v._view_key(p)]]))
                continue
            h.title = title or None
            ok &= same(figs[v._view_key(p)],h.figure())
        ov = figs['overview:overview']
        ok &= [ describe([mcpl.plotting.Figure(panels=[pn])]).split('\n',1)[1]
                for pn in ov.panels ] == [
                    describe([mcpl.plotting.Figure(panels=[ figs[k].panels[0] ])]).split('\n',1)[1]
                    .replace(f"Panel {figs[k].panels[0].title!r}","Panel None",1)
                    for k in v.overview_keys('overview:overview') ]
        print(f'skip={skip} limit={limit} pick={pick!r} edit={edit!r}:')
        print(f'   {v.status_lines()[0]}')
        print(f'   {len(v.views)} views, same figures as mcpltool -H: {ok}')
        for p, e in failed:
            print(f'   plot {p!r} shows: {e}')
        assert ok
        v.stop()

def test_groups():
    import shlex

    from mcpldev._stdviews import _default_preset, _groups, _plot_item, _presets
    from mcpldev._viewer import _auto_title
    from mcpldev._viewer_groups import PlotGroups
    assert _default_preset in _presets
    assert all( k in _groups for _, keys in _presets.values() for k in keys )
    #The names of the presets and groups can never be views (plots), as they
    #are not valid expressions or plots (so -wNAME can be either):
    for name in ( *_presets, *_groups ):
        for check in ( mcpl.ParticleValue, mcpl.ParticleFilter ):
            try:
                check(name)
            except mcpl.MCPLError:
                continue
            raise AssertionError(f'group or preset name {name!r} is a valid expression')
        assert not Viewer(ex).check('plot',name)[0], f'group or preset name {name!r} is a valid plot'
    #All plots of all groups work, and plots whose title follows from their
    #expressions have no title of their own (so it follows changes of the
    #expressions, see _viewer._auto_title):
    g = PlotGroups()
    g.use_preset('all')
    for key, ( title, descr, items, opts ) in _groups.items():
        plots = [ _plot_item(i) for i in items ]
        assert len({ p for p, _ in plots }) == len(plots)
        for p, t in plots:
            assert t is None or _auto_title(p) is None, ( f'{key}: the plot {p!r} has the title'
                                                         f' {t!r}, but gets one from its expression' )
        ov = dict(g.overviews())[key]
        for p in ov.plots:
            assert Viewer(ex).check('plot',p)[0], p
            mcpl.histogram(ex,p)
        print(f'group {key}: {title}: {descr}, {len(ov.plots)} plots in {ov.nrows}x{ov.ncols}'
              f'{" (corner)" if ov.corner else ""}{" (folded)" if opts.get("folded") else ""}')
    for name, ( descr, keys ) in _presets.items():
        print(f'preset {name}: {descr}: {", ".join(keys)}')
    v = Viewer(ex,view='beamz',plots=['x;bins=5'])
    v.multi_overview = True
    print('-wbeamz:', v.field_text('collection'), v.groups, [ k for k, _ in v.views ][:2],
          '| state:', v.state(), '| command:', v.commands()['view'])
    #(a plot of a standard group is copied into the custom group when it is
    #changed, with its title, and is not removed; custom plots are):
    print('changed:', v.change_plot('x : y','x/mm : y/mm'), v.current_key,
          v.plot_info(v.current_key)['name'], v.plot_info(v.current_key)['group'],
          '| still there:', 'plot:x : y' in dict(v.views), '| state:', v.state(full = False))
    print('removing a standard plot:', v.change_plot('x : y',''))
    print('removing a custom plot:', v.change_plot('x/mm : y/mm',''), v._groups.custom)
    #(also when the changed plot is in another group, or among the custom
    #plots, which shows a copy of it, keeping the other settings):
    v.set('collection','default')
    print('changed to a plot of another group:', v.change_plot('ekin;logx=auto;logy;split=pdgcode','ekin'),
          v.current_key, v.plot_info(v.current_key)['group'], v._groups.custom)
    print('again, a setting:', v.change_plot('plot:ekin','ekin;bins=20'), v.current_key, v._groups.custom)
    print('the custom one:', v.change_plot('custom:ekin','ekin;logy'), v.current_key, v._groups.custom,
          '| state:', v.state(full = False))
    print('check:', v.check('collection','beam'), v.check('collection',''), v.check('collection','3d'))
    print('completions:', v.complete('collection','beam'), '| hint:', v.hint('collection','beamx'))
    print('switched:', v.set('collection','shielding'), v.groups, [ k for k, _ in v.views ][:2],
          'custom plot kept:', v._s.plots[-1], '| state:', v.state(full = False))
    print('group shown:', v.show_group('3d'), v.groups, 'again:', v.show_group('3d'),
          '| hidden:', v.show_group('shielding',False), v.groups, '| state:', v.state(full = False))
    arg = shlex.split(v.commands()['view'])[1]
    w = Viewer(ex,view=arg.split('=',1)[1] if arg.startswith('--') else arg[2:])
    print('opened with the command: same state:', w.state() == v.state())
    #(a state given as a dict, as in the Python API):
    w = Viewer(ex,view=v.state())
    print('opened with the state as a dict: same state:', w.state() == v.state())
    #Titles of the custom plots, kept when they are changed, and in the
    #state (as plot items); the standard plots keep theirs:
    t = Viewer(ex)
    t.set('plot','hypot(x,y)/cm;logy')
    t.set('plot','uz;bins=20')
    print('titles:', t.set_title('hypot(x,y)/cm;logy','Radius'), t.set_title('x : y','Beam spot'),
          t.set_title('hypot(x,y)/cm;logy','a\nb'), t.set_title('nope','x'))
    t.change_plot('hypot(x,y)/cm;logy','hypot(x,y)/mm')
    print('info of a changed custom plot:', t.plot_info('custom:hypot(x,y)/mm'))
    print('info of a standard plot:', t.plot_info('plot:polx'))
    print('moved:', t.move_to('uz;bins=20',0), t._groups.custom, '| a standard plot:',
          t.move_to('polx',0))
    st = t.state()
    print('state:', st)
    print('opened with it: same state:', Viewer(ex,view=st).state() == st)
    for bad in ( "{'custom':[{'title':'A'}]}", "{'custom':[{'plot':'x','color':'red'}]}",
                 "{'custom':[3]}", "{'custom':[{'plot':'x','title':''}]}", "{'custom':{}}",
                 "{'groups':'nope'}", "{'groups':3}", "{'groups':['fields','nope']}" ):
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
    v.set('plot','hypot(x,y)/cm')
    v.set('plot','uz;bins=20')
    print('move up:', v.move(-1), 'again:', v.move(-1), 'down:', v.move(1), '| current:', v.current_key,
          v._groups.custom)
    v.select(0)
    print('move the overview:', v.move(1))
    v.select_key('plot:x')
    print('move a standard plot:', v.move(1))
    v.change_plot('ekin','ekin/keV;logy=1')
    v.change_plot('hypot(x,y)/cm','')
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
    for view in ( 'x', ' x ', 'overview', 'overview:fields', 'pdgcode;bar = auto ; logy=auto' ):
        w = Viewer(ex,view=view)
        w.multi_overview = True
        print(f'view {view!r}:', w.views[w.current][0])
    for bad in ( "{'foo':1}", '{"limit":"a"}', "{bad", "[1]", "nope.json", 'nope', 'overview:nope' ):
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
    def run( keys, show = True, backend = None, window = None, **kw ):
        v = Viewer(ex,**kw)
        s = FakeScreen(keys)
        s.viewer = v
        t = TextViewer(v,s,backend)
        if window is not None:
            t.open_window = window
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
    #o shows the plot, and g the viewer in the same state, in a GUI window
    #(here with a function which only notes what is shown, so no window is
    #opened in tests):
    shown = []
    def window( action, what ):
        shown.append( ( action, what ) )
    v, t = run(['WAIT','Down','o','g','WAIT'],show=False,window=window)
    print('   o shows the plot in a window:', shown[0][0], shown[0][1].panels[0].xlabel,
          '| the plot shown:', v.views[v.current][0])
    print('   g opens the viewer in a window:', shown[1][0], shown[1][1] is v,
          '| messages:', [ ln.strip() for f in t.s.frames for ln in f.splitlines()
                           if 'GUI window' in ln ][-1:])
    def fail( action, what ):
        raise mcpl.MCPLError('The matplotlib plotting backend can not show plots here')
    _, t = run(['WAIT','O'],show=False,window=fail)
    print('   without a display:', next( ln.strip() for f in t.s.frames for ln in f.splitlines()
                                            if 'Not shown' in ln ))
    #l and k toggle the options logy and logx of the shown plot (from the
    #scale shown, also for auto), in its histogram string:
    v, t = run(['WAIT','l','WAIT','k','Down','WAIT','K','WAIT'],show=False)
    print('   l and k:', [ k for k, _ in v.views ][:3])
    print('   the figure:', 'logx' if v.figure().panels[0].logx else 'linear x')
    v, t = run(['WAIT','l','k'],show=False)
    print('   k before the changed plot is drawn:', next( ln.strip() for f in t.s.frames
                                                          for ln in f.splitlines() if 'not drawn' in ln ))
    #c shows a menu of the collections of plots (Up and Down choose one, which
    #Enter applies; the keys work with Shift too):
    e = ui.editor_for(v,'collection')
    e.key('Down')
    e.key('Down')
    print('   c shows the collections:', [ n for n, _ in e.choices ],
          'chosen:', e.choices[e.selected][0], '| key hint:', ui.hint_line(e,popup=True)[0])
    v, t = run(['WAIT','C','Down','Down','WAIT'],show=False)
    print('   the menu on the screen:', [ ln.strip() for ln in t.s.frames[-2].splitlines()
                                          if 'beamy' in ln or 'Up/Down' in ln ])
    v, _ = run(['WAIT','c','Down','Down','Enter','WAIT'],show=False)
    print('   c changes the collection:', v.field_text('collection'), v.views[v.current][0])
    v, _ = run(['WAIT','c','Down','Esc','WAIT'],show=False)
    print('   Esc keeps the collection:', v.field_text('collection'))
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

def test_code():
    print('The command and code of plots, and of writing files:')
    def show( code, kinds = ( 'command', 'python' ) ):
        print(f'  {code["command"]}  (code: {", ".join(code)})')
        for k in ( k for k in kinds[1:] if k in code ):
            print(''.join( f'     {k:>6} | {line}\n' for line in code[k].splitlines() ),end='')
    for pick, edit, skip, limit in ( (None,None,0,None),
                                     ('pdgcode == neutron','z += 1m;weight *= 2',0,None),
                                     ('ekin > 1MeV',None,100,300) ):
        v = Viewer(ex,pick=pick,edit=edit,skip=skip,limit=limit)
        for plots in ( ['ekin;logx'], ['x','y : z;bins=10'] ):
            show(v.code(plots))
        allkinds = ( 'command', 'python', 'cpp', 'c' )
        show(v.code(['ekin;logx']) if skip else v.code(filename = 'by_python.mcpl'),
             allkinds if skip or pick else allkinds[:2])
        if skip:
            show(v.code(filename = 'by_python.mcpl'),allkinds)
        code = v.code(filename = 'by_python.mcpl')['python']
        #The code makes the same histograms (as figures, but without the pick
        #and edit as titles), and writes the same particles, as the viewer:
        def run( code ):
            script = pathlib.Path('code.py')
            script.write_text(code.replace('import mcpl\n',''))
            return runpy.run_path(str(script),init_globals = { 'mcpl' : mcpl })
        ns = run(v.code(_plots)['python'].replace('mcpl.plot_histograms( hs )',
                                            'figs = [ h.figure() for h in hs ]'))
        vp = Viewer(ex,pick=pick,edit=edit,skip=skip,limit=limit,plots=_plots)
        vp.start()
        vp.wait()
        def untitled( fig ):
            fig = copy.deepcopy(fig)
            for panel in fig.panels:
                panel.title = None
            return fig
        same_figs = all( same(a,untitled(vp.figure(key = f'plot:{p}')))
                         for a, p in zip( ns['figs'], _plots ) )
        vp.stop()
        run(code)
        v.write('by_viewer.mcpl')
        with MCPLFile('by_python.mcpl') as a, MCPLFile('by_viewer.mcpl') as b:
            same_particles = ( a.nparticles == b.nparticles and
                               all( (x.ekin == y.ekin).all() and (x.z == y.z).all()
                                    and (x.weight == y.weight).all() for x, y in
                                    zip(a.particle_blocks,b.particle_blocks) ) )
        print(f'  same figures: {same_figs}, same particles: {same_particles}')
        for fn in ( 'by_python.mcpl', 'by_viewer.mcpl', 'code.py' ):
            pathlib.Path(fn).unlink()

def test_c_translation():
    #Simple picks and edits are translated to C and C++ (the generated code was
    #compiled and compared with the viewer when this was written), and the
    #others are left to the users:
    from mcpldev._viewer_code import _c_condition, _c_edit, _CTranslator
    for pick in ( 'pdgcode == neutron', 'abs(pdgcode) in (electron,muon) or ekin < 25meV and hypot(x,y) < 5cm',
                  'pdgcode not in (22,2112)', '(userflags & 0xff) == 0 and not ekin > 1MeV', '0cm < x < 2cm',
                  'ekin/MeV > 0.5 and uz > 0.9', 'sqrt(x^2+y^2) < 3cm', '-x > 1mm', 'pdgcode/2 > 1000',
                  'angle(dir,(0,0,1)) < 1deg', 'wavelength > 1.8Aa', 'mod(fileidx,10) == 0',
                  'pos.z > 1cm and dir.at(2) > 0' ):
        for lang, kind in ( ('c','c'), ('cpp','cpp') ):
            tr = _CTranslator(lang,'p',kind)
            print(f'pick {pick!r} in {lang}: {_c_condition(pick,tr)}  {sorted(tr.headers)}')
    for edit in ( 'z += 1m;weight *= 0.5', 'x = 2*y;ekin = ekin/2', 'time = time + 1ms*abs(x)/1cm',
                  'rotate_z(90deg)', 'rotate_y(-90deg)', 'rotate_x(30deg)', 'swap(x,y)',
                  'swap(pdgcode,userflags)', 'rotate_z(x/cm*1deg)', 'ux = 1', 'a = 2*x;y = a',
                  'rotate_around((0,0,1),90deg)', 'rotate_frame((0,0,1),(1,1,0),(0,1,0),(0,0,1))',
                  'rotate_around(dir,10deg)', 'rotate_around((0,0,-(1)),90deg)', 'x = pos.y',
                  'pos += (0,0,1m)' ):
        print(f'edit {edit!r}: {_c_edit(edit,_CTranslator("c","q","struct"),"")}')
    #In files with userdata, the edited particles keep it:
    import numpy as np
    with mcpl.MCPLOutFile('ud.mcpl', userdata_layout = 'temp:float32') as f:
        f.add_particles( pdgcode = 2112, position = np.zeros((3,3)), direction = (0,0,1),
                         ekin = 1.0, weight = 1.0, userdata = { 'temp' : 300.0 } )
    code = Viewer('ud.mcpl',edit = 'z += 1cm').code(filename = 'out.mcpl')
    for kind in ( 'cpp', 'c' ):
        print(f'{kind} with userdata:', [ line.strip() for line in code[kind].splitlines()
                                          if 'userdata' in line or 'add' in line or 'out.' in line ])
    pathlib.Path('ud.mcpl').unlink()
    #The highlighting of the code (the styles of its parts):
    from mcpldev._viewer_code import highlight
    code = Viewer(ex,pick='pdgcode == neutron',skip=5).code(filename = 'out.mcpl')
    for kind in ( 'command', 'python', 'cpp', 'c' ):
        print(f'highlighted {kind}:', ' '.join( f'{style}[{code[kind][a:b]}]'
                                                for a, b, style in highlight(code[kind],kind) ))

def test_plot_changes():
    #k and l toggle logx and logy from what is shown, and the same key again
    #undoes it (also back to auto), unless the plot was changed otherwise:
    v = Viewer(ex)
    v.start()
    v.wait()
    v.select_key('plot:ekin;logx=auto;logy;split=pdgcode')
    for option in ( 'logx', 'logx', 'logx', 'logy', 'logx' ):
        print(f'toggle {option}:', v.toggle_scale(option), v.current_key)
        v.wait()
    v.change_plot(v.current_key,'ekin;logx=auto')
    v.wait()
    print('after another change:', v.toggle_scale('logx'), v.toggle_scale('logx'), v.current_key)
    #Titles get (??) when the expressions of the plot change (not its options):
    p = 'wavelength;logx;split=pdgcode'
    for new in ( 'wavelength;split=pdgcode', 'wavelength/nm;split=pdgcode', 'ekin/MeV;split=pdgcode' ):
        v.change_plot(p,new)
        print(f'title after {new!r}:', v.plot_info(f'plot:{new}')['title'])
        p = new
    v.set('plot','x;bins=10')
    v.change_plot('x;bins=10','y;bins=10')
    print('without a title:', v.plot_info('plot:y;bins=10')['title'], v.plot_info('plot:y;bins=10')['name'])
    #Fields the file does not have:
    print('absent:', [ v.plot_info(k)['name'] for k, _ in v.views if v.plot_info(k)['absent'] ])
    v.stop()

def test_range_and_userdata():
    #A limit beyond the end of the file gives the same particles, so the
    #reading is not restarted:
    v = Viewer(ex)
    v.start()
    v.wait()
    for field, text in ( ('limit','1e9'), ('limit','500'), ('limit','all'), ('skip','2000'),
                         ('skip','3000') ):
        g = v._generation
        v.set(field,text)
        print(f'{field} {text}: read again: {v._generation != g}')
    v.stop()
    #The userdata fields of the file, in completions and checks:
    fn = 'ud_viewer.mcpl'
    with mcpl.MCPLOutFile(fn,userdata_layout='nscat:uint8,temp:float32,dir:float32[3]') as o:
        o.add_particles( x = [1.0,2.0], uz = 1.0, ekin = 1.0, pdgcode = 2112, weight = 1.0,
                         userdata = { 'nscat' : [0,1], 'temp' : [10.0,20.0], 'dir' : [[0,0,1]]*2 } )
    v = Viewer(fn)
    for field, text in ( ('pick','userd'), ('pick','x > 0cm and userdata.'), ('plot','userdata.t'),
                         ('pick','userdata.d') ):
        print(f'completions of {text!r}:', [ c for c, _ in v.complete(field,text)[1] ])
    for text in ( 'userdata.nscat > 0', 'userdata.nope > 0', 'userdata.dir > 0',
                  'userdata.dir.at(2) > 0', 'userdata.dir.at(3) > 0', 'userdata.nscat.at(0) > 0' ):
        print(f'check of {text!r}:', v.check('pick',text))
    w = Viewer(ex)
    print('without userdata:', w.check('plot','userdata.nscat;bar'), w.check('pick','x > 0cm and userdata.'),
          w.hint('pick','userdata.'))
    #Another file in the same state (without skip and limit, and without what
    #does not work for the other file):
    v = Viewer(fn,pick='userdata.nscat > 0',edit='z += 1m',skip=1)
    v.set('plot','ekin;bins=20')
    for other, particles in ( ( ex, True ), ( fn, True ), ( fn, False ) ):
        w, msg = v.for_file(other,particles)
        print(f'for {other} (particles {particles}): pick {w.field_text("pick")!r}, edit'
              f' {w.field_text("edit")!r}, skip {w.field_text("skip")!r}, {len(w.views)} views,'
              f' message {msg!r}')
    pathlib.Path(fn).unlink()

def test_memory():
    #The particles are kept in memory from the start of the file up to the
    #memory limit, giving the same figures as without, and only those after
    #them are read again:
    import numpy as np
    from mcpldev._viewer_reading import _InMemory
    v = Viewer(ex,plots = [ 'ekin;bins=20' ])
    info = v.memory_info()
    print('memory:', info)
    v.set_memory_limit(info['size'] * 300)
    print('with a lower limit:', { k : v.memory_info()[k] for k in ( 'limit', 'fits', 'nfit' ) })
    v.start()
    for pick in ( '', 'ekin < 1MeV', '' ):
        v.set('pick',pick)
        v.wait()
        vals = np.concatenate([ np.asarray(it.values) for it in
                                v.figure(key = 'custom:ekin;bins=20').panels[0].items
                                if hasattr(it,'values') ])
        h = mcpl.histogram(mcpl.MCPLFile(ex,pick = pick or None),'ekin;bins=20')
        ref = np.concatenate([ np.asarray(c) for c in h.contents.values() ])
        print(f'  pick {pick!r}: as without memory: {np.array_equal(vals,ref)}')
    v.stop()
    class Limit:
        memory_limit = info['size'] * 300
    f = _InMemory(mcpl.MCPLFile(ex,blocklength = 100),Limit())
    for i in range(2):
        offsets = [ b.file_offset for b in f.particle_blocks ]
        print(f'  reading {i}: blocks from {offsets[:4]} to {offsets[-1]}, kept: {f._end}')

test_memory()
test_figures()
test_code()
test_c_translation()
test_plot_changes()
test_range_and_userdata()
test_fields()
test_reading()
test_groups()
test_state()
test_write()
test_terminal()
test_tool()
