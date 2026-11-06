
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

# The lines of the Composer of the viewer, without a window (see
# _viewer_compose): the controls of each kind of line and the statements
# they write, typed lines, checks, the numbers of particles left after each
# line, applying the lines, and the align lines.

import shutil

from mcpldev import _viewer_align as al
from mcpldev._viewer import Viewer
from mcpldev._viewer_compose import Composer, kinds
from mcpldev._viewer_threads import Mailbox
from MCPLTestUtils.common import rounded_numbers
from MCPLTestUtils.dirs import test_data_dir

shutil.copy(test_data_dir / 'example.mcpl','example.mcpl')

def show( c, title ):
    print(f'{title}:')
    checks, counts = c.checks(), c.counts()
    for i, line in enumerate(c.lines):
        print(f'   [{"x" if line.active else " "}] {kinds[line.kind]:<10} {rounded_numbers(line.text)!r}'
              f' | error: {checks[i]!r} | left: {counts[i] if counts else None}')
    print(f'   pending: {c.pending} | expression: {c.expression!r}')

def rows( c, i ):
    for r in c.rows(i):
        controls = ', '.join( f'{x.name or x.kind}={x.value!r}'
                              + ( f' of {len(x.choices)}' if x.kind in ( 'menu', 'select' ) else '' )
                              for x in r.controls )
        print(f'   row {r.option or "-"} {r.label!r}: {controls}')

def test_kinds():
    v = Viewer('example.mcpl')
    v.start()
    v.wait()
    c = Composer(v)
    #(a new line is empty, and a kind writes nothing until its values are
    #given):
    i = c.add()
    print('new line:', kinds[c.lines[i].kind], repr(c.lines[i].text))
    c.set_kind(i,'filter')
    print('keep only:', repr(c.lines[i].text))
    rows(c,i)
    print('particle types:', c.rows(i)[0].controls[0].choices[:3])
    #(the controls write the line; values are given as shown):
    for name, value in ( ( 'pdg', 'gamma (24%)' ), ( 'option', 'quantity' ),
                         ( 'quantity', 'Wavelength:  wavelength' ), ( 'op', '>=' ),
                         ( 'value', '1.8' ), ( 'quantity', 'Time:  time' ),
                         ( 'quantity', 'angle(dir,(0,0,1))/deg' ), ( 'option', 'near' ),
                         ( 'radius', '5' ), ( 'runit', 'mm' ), ( 'point', '(0,0,1m)' ),
                         ( 'option', 'sphere' ), ( 'bcentre', '(0,0,1m)' ),
                         ( 'half', '(5cm,5cm,1mm)' ) ):
        c.set_value(i,name,value)
        units = next( x.choices for r in c.rows(i) for x in r.controls if x.name == 'unit' ) \
            if any( x.name == 'unit' for r in c.rows(i) for x in r.controls ) else None
        print(f'   {name} = {value!r}: {c.lines[i].text!r} | units {units}')
    for kind, values in ( ( 'change', ( ( 'field', 'Wavelength:  wavelength' ), ( 'op', '=' ),
                                        ( 'value', '1.8' ), ( 'op', '*=' ), ( 'value', '2' ),
                                        ( 'field', 'Direction:  dir' ), ( 'op', '=' ),
                                        ( 'value', '(0,0,1)' ) ) ),
                          ( 'rotate', ( ( 'axis', 'y axis' ), ( 'angle', '30' ),
                                        ( 'aunit', 'rad' ), ( 'option', 'around' ),
                                        ( 'vector', '(1,1,0)' ), ( 'angle2', '45' ),
                                        ( 'option', 'frame' ), ( 'v', '(0,0,1)' ),
                                        ( 'vout', '(1,0,0)' ), ( 'u', '(0,1,0)' ),
                                        ( 'uout', '(0,1,0)' ) ) ),
                          ( 'variable', ( ( 'name', 'd' ), ( 'value', 'pos - (0,0,1m)' ) ) ) ):
        j = c.add()
        c.set_kind(j,kind)
        print(f'{kinds[kind]}: {c.lines[j].text!r}')
        rows(c,j)
        for name, value in values:
            c.set_value(j,name,value)
            print(f'   {name} = {value!r}: {c.lines[j].text!r}')
    #(a typed line is an expression, with completion and hints):
    k = c.add()
    c.set_text(k,'ek')
    print('typed:', kinds[c.lines[k].kind], '| rows:', c.rows(k), '| completions:',
          c.complete('ek',2)[:2], c.complete('pdgcode == neu',14)[:2], '| hint:', c.hint('ekin',2))
    #(names are also found by a later part, after a "_", as "sph" finds
    #through_sphere, which Tab then writes in place of what is typed):
    for typed in ( 'sph', 'around', 'rot' ):
        print(f'completions of {typed!r}:', [ n for n, _ in c.completions(typed,len(typed))[1] ],
              '| Tab:', c.complete(typed,len(typed))[:2])
    show(c,'all lines')
    v.stop()

def test_lines():
    v = Viewer('example.mcpl',state={'edit':'pdgcode == neutron; inactive(z += 1m);'
                                             ' d = pos - (0,0,1m); abs(d) < 120cm; ekin < 1MeV'})
    v.start()
    v.wait()
    c = Composer(v)
    show(c,'from the viewer')
    #(each line is checked after the active lines before it; a variable used
    #by a later line is fine):
    c.set_text(3,'abs(d) < 1')
    show(c,'with an error')
    c.set_text(3,'abs(d) < 1m')
    c.set_active(2,False)
    show(c,'variable switched off')
    c.set_active(2,True)
    c.move(4,-1)
    c.move(0,-1)#(not possible)
    c.delete(1)
    i = c.add()
    c.set_value(i,'option','quantity')
    show(c,'moved, deleted, and added')
    print('applied:', c.apply(), '| field:', repr(v.field_text('edit')))
    v.wait()
    show(c,'after applying')
    #(empty lines are dropped when applied, and lines with errors are not
    #applied):
    c.add()
    c.set_text(len(c.lines) - 1,'')
    c.set_text(0,'x >')
    print('applied with an error:', c.apply(), '| field:', repr(v.field_text('edit')))
    c.set_text(0,'pdgcode == neutron')
    print('applied:', c.apply(), '| lines:', len(c.lines))
    #(the lines follow an edit applied elsewhere, unless changed here):
    c.set_text(0,'pdgcode == gamma')
    v.set('edit','ekin < 1MeV')
    print('sync while changed here:', c.sync(), len(c.lines))
    c.reset()
    v.set('edit','pdgcode == gamma; ekin < 1MeV')
    print('sync:', c.sync(), [ line.text for line in c.lines ])
    #(an own function applying the lines, as the window has):
    applied = []
    c2 = Composer(v,apply_lines = lambda lines : applied.append(lines) or True)
    c2.set_active(0,False)
    print('own apply:', c2.apply(), applied)
    v.stop()

def test_align():
    v = Viewer('example.mcpl',edit='pdgcode == neutron')
    v.start()
    v.wait()
    c = Composer(v)
    i = c.add()
    c.set_kind(i,'align')
    print('align line before the means are known:', repr(c.lines[i].text))
    rows(c,i)
    #(the means are read with the edit of the lines before it, here in this
    #thread, as the window does in another one):
    key, args = c.align_reading(i)
    print('reading with:', args[1:], '| again:', c.align_reading(i) is not None)
    mailbox = Mailbox()
    al.read_file_stats(mailbox,*args)
    c.set_align_stats(c.lines[i],key,mailbox.take()[-1])
    print('read again after:', c.align_reading(i))
    print('statements:', rounded_numbers(c.lines[i].text))
    for r in c.rows(i):
        for x in r.controls:
            if x.kind == 'note':
                print(f'   {x.name}: {rounded_numbers(x.value)}')
    for name, value in ( ( 'move', True ), ( 'cz', False ), ( 'keep', '(0,1,0)' ),
                         ( 'turn', False ), ( 'point', '(1,2)' ) ):
        c.set_value(i,name,value)
        print(f'   {name} = {value!r}: {rounded_numbers(c.lines[i].text)!r} |'
              f' {rounded_numbers(c.rows(i)[-1].controls[0].value)}')
    c.set_value(i,'point','(0,0,0)')
    print('applied:', c.apply())
    v.wait()
    show(c,'with the align line')
    #(a line before it changes the particles it is about, so they are read
    #again; and errors of the reading are shown):
    j = c.add()
    c.set_text(j,'wavelength > 1Aa')
    c.move(j,-1)
    c.set_text(0,'ekin > 0')
    key, args = c.align_reading(2)
    print('read again with:', args[3])
    mailbox = Mailbox()
    al.read_file_stats(mailbox,*args)
    c.set_align_stats(c.lines[2],key,mailbox.take()[-1])
    print('error:', c.rows(2)[0].controls[0].value, '| text:', repr(c.lines[2].text))
    v.stop()

test_kinds()
test_lines()
test_align()
