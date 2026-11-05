
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

# Tests of the canonical forms of expressions (the .expression of values and
# edit expressions, with or without conditions) and of histogram strings, across the modules: for all
# examples of the help, a list of expressions, and random expressions, the
# normalised trees give exactly the same values (or the same errors) as the
# trees as parsed, on the particles of a reference file, and the canonical
# texts are their own canonical texts. The log freezes the canonical forms.
# Files extracted with conditions written in different ways can be merged.

import os
import pathlib
import random
import shutil
import subprocess
import sys

import mcpldev as mcpl
import numpy as np
from mcpldev._common import MCPLError
from mcpldev._expr_ast2astnorm import _expr_ast2astnorm
from mcpldev._expr_astcheck import _expr_astcheck
from mcpldev._expr_eval import _ExprEvaluator, _run_statements
from mcpldev._expr_str2ast import _expr_normalise, _expr_str2ast
from mcpldev._exprhelp import example_rows
from mcpldev._exprplot import _PlotValue
from mcpldev._histstring import _canonical_hist, _hist_exprs, _parse_hist, _Range
from MCPLTestUtils.dirs import test_data_dir

reffile = test_data_dir / 'ref' / 'miscphys.mcpl.gz'
#(the expressions of histograms are values which can have units):
#(conditions are edit expressions, listed apart):
classes = { 'condition' : mcpl.ParticleEdit, 'value' : mcpl.ParticleValue,
            'edit' : mcpl.ParticleEdit, 'plot' : _PlotValue }

def block():
    with mcpl.MCPLFile(reffile) as f:
        return f.read_block()

def outcome( text, kind, b, normalise ):
    """What the expression gives for the particles of the block b, evaluating
    its tree as parsed, or its normalised tree: ( kind, values ) or ( 'error',
    message ), where the values of edit expressions are those of the changed
    fields and the positions of the particles kept"""
    try:
        t = _expr_normalise(text)
        kind = { 'plot' : 'value', 'condition' : 'edit' }.get(kind,kind)
        tree = _expr_str2ast(t,kind)
        _expr_astcheck(tree,t)
        if normalise:
            tree = _expr_ast2astnorm(tree)
        ev = _ExprEvaluator(b,t)
        if kind == 'value':
            q = ev.scalar(ev(tree),'the value of an expression')
            return kind, [ np.asarray(q.v), q.d ]
        modified = set()
        _run_statements(ev,tree.statements,t,modified)
        return kind, [ ( n, np.asarray(ev.state[n].v) ) for n in sorted(modified) ] + [ ev.kept ]
    except MCPLError as e:
        return 'error', str(e)

def same( a, b ):
    if a[0] != b[0]:
        return False
    if a[0] == 'error':
        return a[1] == b[1]
    def eq( x, y ):
        if isinstance(x,np.ndarray):
            return x.dtype == y.dtype and np.array_equal(x,y,equal_nan = x.dtype.kind == 'f')
        if isinstance(x,( list, tuple )):
            return len(x) == len(y) and all( eq(u,v) for u, v in zip(x,y) )
        return x == y
    return eq(a[1],b[1])

def check( text, kind, b, show = True ):
    """The invariants of the canonical form of the expression (returns whether
    it is valid)"""
    a, n = outcome(text,kind,b,False), outcome(text,kind,b,True)
    assert same(a,n), ( text, a, n )
    if a[0] == 'error':
        if show:
            print(f'  {text!r}: {a[1]}')
        return False
    try:
        obj = classes[kind](text)
    except MCPLError as e:
        #(e.g. values with units, which ParticleValue refuses):
        if show:
            print(f'  {text!r}: {e}')
        return False
    c = obj.expression
    assert classes[kind](c).expression == c, ( text, c )
    assert obj.expression_original == _expr_normalise(text)
    assert same(outcome(c,kind,b,True),n), ( text, c )
    if show:
        print(f'  {text!r} -> {c!r}')
    return True

def test_examples( b ):
    print('Examples of the help:')
    for text, _ in example_rows('edit'):
        check(text,'edit',b)
    print('Histogram strings of the help:')
    for text, _ in example_rows('hist'):
        for e in _hist_exprs(text):
            check(e,'plot',b,show = False)
        c = _canonical_hist(text)
        assert _canonical_hist(c) == c, ( text, c )
        print(f'  {text!r} -> {c!r}')

expressions = {
    'condition' : ( 'pdgcode == neutron', '(pdgcode==2112)', 'pdgcode == positron', 'pdgcode == antielectron',
               'pdgcode == -11', 'pdgcode in (neutron, gamma)', 'pdgcode in (22,2112,neutron)',
               'pdgcode not in (proton,antiproton)', 'abs(pdgcode) in (11,electron)',
               'ekin > 5000 eV and pdgcode == neutron', '(pdgcode==2112) and ekin>5keV', 'ekin > 5e3eV',
               'ekin > 0.001MeV', 'ekin > 1e-12MeV', 'ekin > 0keV', 'ekin > 0.0 MeV', 'x > 10mm',
               'x>0.5mm', 'x > -2 cm', 'x > -0.02m', 'z < 1.8Aa', 'z<20Aa', 'abs(y) < 1e5um',
               'time > 2000us', 'time < 5e-4ns', 'ux > cos(90.0deg)', 'x^2+y^2 < 40000mm^2',
               '1/x^2 > 1e-6mm^-2', 'not (x > 1cm)', 'x > 0x10 mm', 'r = sqrt(x^2+y^2); r < 10mm',
               'pdgcode == neutron and wavelength > 1.8Aa', 'ekin > (1/2) keV', 'weight > 2.0',
               'userflags & 0x2 == 2', 'x > neutron*1cm', 'ekin > 1.5e20 eV', 'mod(fileidx,2) == 0',
               'pdgcode == 12345', 'x < 123456789012345678901234567890Aa' ),
    'value' : ( 'ekin/MeV', '(ekin) / MeV', 'ekin/0.001keV', 'x/10mm', '2.5e-3MeV*ekin/MeV^2',
                'angle(dir,(0,0,1))/deg', '(pos - (0,0,1m)).z/cm', 'pdgcode == neutron',
                'abs(pdgcode)', 'hypot(x,y)/0.1m', 'x/cm^0.5/cm^0.5', 'pdgcode*1' ),
    'edit' : ( 'weight *= 2', 'weight*=2.0', 'x = x + 10mm', 'x += 0.01m', 'ekin = 25meV; pdgcode = neutron',
               'ekin=0.025eV;pdgcode=2112', 'rotate_z(90.0deg)', 'z -= 1.5km', 'pdgcode = -11',
               'tmp = x; x = y; y = tmp', 'pos += (0,0,1e3mm)', 'wavelength = 0.18nm',
               'rotate_y(90deg); x > 0cm', 'pdgcode == neutron; wavelength > 1.8Aa;  weight *= 2',
               'x > 0; inactive(y += 1cm); z += 2cm' ),
}
#Groups of expressions with the same canonical form, and different ones:
same_forms = [
    [ 'pdgcode == neutron', '(pdgcode==2112)', 'pdgcode == 2112' ],
    [ 'pdgcode == positron', 'pdgcode == antielectron', 'pdgcode == -11' ],
    [ 'ekin > 5000 eV and pdgcode == neutron', 'ekin>5keV and (pdgcode==2112)',
      'ekin > 5e3eV and pdgcode == neutron', 'ekin > 0.005MeV and pdgcode==2112' ],
    [ 'ekin > 0keV', 'ekin > 0.0 MeV', 'ekin > 0meV', 'ekin > 0eV' ],
    [ 'x > 10mm', 'x > 1cm', 'x > 0.01m', 'x > 1e4um', 'x > 1e8Aa', 'x > 1.0cm' ],
    [ 'time > 2000us', 'time > 2ms', 'time > 0.002s', 'time > 2e6ns' ],
    [ 'pdgcode in (neutron, gamma)', 'pdgcode in (2112,photon)', 'pdgcode in (22,2112,neutron)' ],
    [ 'x^2+y^2 < 40000mm^2', 'x^2 + y^2 < 4e-2m^2', 'x^2+y^2<400cm^2' ],
]
different_forms = [ 'ekin > 5keV', 'ekin > 5.0001keV', 'ekin > 5eV', 'ekin < 5keV', 'ux > cos(90rad)',
                    'x >= 1cm', 'x > 1cm^2/cm', 'weight > 2', 'weight > 2.0', 'userflags > 0x2' ]

def test_expressions( b ):
    for kind, texts in expressions.items():
        print(f'Canonical forms ({kind}):')
        for text in texts:
            check(text,kind,b)
    forms = []
    for group in same_forms:
        f = { mcpl.ParticleEdit(e).expression for e in group }
        assert len(f) == 1, ( group, f )
        forms += f
    forms += [ mcpl.ParticleEdit(e).expression for e in different_forms ]
    assert len(set(forms)) == len(forms), forms
    print(f'{len(same_forms)} groups of expressions have the same canonical forms, and'
          f' {len(forms)} different ones different forms')

def test_errors( b ):
    #(invalid expressions, and errors when evaluating, which must be the same
    #for the normalised trees):
    print('Errors:')
    for text, kind in ( ( 'x > 1MeV', 'condition' ), ( 'mod(pdgcode,3) == 1', 'condition' ), ( 'pdgcode * 1000000000 > 0', 'condition' ),
                        ( 'x < 1e400cm', 'condition' ), ( 'x > 1e308km', 'condition' ), ( 'wavelength > 1Aa', 'condition' ),
                        ( 'pdgcode in (neutron) and ekin/(ekin-ekin) > 0', 'condition' ), ( 'x', 'value' ),
                        ( 'pdgcode = 2.5', 'edit' ), ( 'x = 1MeV', 'edit' ), ( 'ekin < 5000 eV + x', 'condition' ),
                        ( 'neutron', 'condition' ), ( 'pdgcode in (1cm)', 'condition' ) ):
        assert not check(text,kind,b)

def random_expressions( rng ):
    plain = [ 'ux', 'uz', '(x/cm)', '(ekin/MeV)', 'weight', '2', '3.5', '1e3', '0x10', '(4cm^2/cm^2)',
              '(25meV/eV)', '(x/2cm)', '(2cm^(-1)*x)', '(sqrt(ekin)/sqrt(eV))', '(2^(ux)MeV/MeV)',
              '(-2meV/eV)', '(5000eV/keV)', '(0.01m/mm)', '(pdgcode/2112)', '(neutron/2)' ]
    def val( d ):
        if d <= 0 or rng.random() < 0.25:
            return rng.choice(plain)
        k = rng.random()
        if k < 0.45:
            return val(d-1) + rng.choice(['+','-','*','/']) + val(d-1)
        if k < 0.6:
            return rng.choice(['-','+']) + val(d-1)
        if k < 0.75:
            return f'({val(d-1)})^' + rng.choice(['2','-1','0.5','(1/2)'])
        if k < 0.85:
            return rng.choice(['abs','cos','atan2','hypot','max']) + f'({val(d-1)},{val(d-1)})'
        return f'({val(d-1)})'
    def cond( d ):
        k = rng.random()
        if d <= 0 or k < 0.3:
            return val(2) + rng.choice(['<','>=','==','!=']) + val(2)
        if k < 0.4:
            return rng.choice([ 'pdgcode == neutron', 'pdgcode != 22', 'pdgcode in (11,-11,gamma)',
                                'abs(pdgcode) not in (positron,2112)', 'x > 0.5mm', 'ekin < 5000eV',
                                'time >= 0.0ms' ])
        if k < 0.7:
            return cond(d-1) + rng.choice([' and ',' or ']) + cond(d-1)
        if k < 0.85:
            return 'not ' + cond(d-1)
        return f'({cond(d-1)})'
    return [ ( val(4), 'value' ) for _ in range(300) ] + [ ( cond(3), 'condition' ) for _ in range(300) ]

def test_random( b ):
    nvalid = 0
    texts = random_expressions(random.Random(12345))
    for text, kind in texts:
        nvalid += check(text,kind,b,show = False)
    print(f'Random expressions: {nvalid} valid ones (and {len(texts)-nvalid} errors), all with'
          ' the same values (or errors) from the normalised trees, and canonical forms')

def test_hist():
    print('Canonical histogram strings:')
    for text in ( 'ekin / MeV ; logx ; bins = 50', 'ekin/MeV;bins=50;logx=1', 'ekin/MeV;logx=0;bar=0',
                  'x/cm : y/cm;xrange=-10:10;yrange=0cm:0.1m;bins=50,40;logz',
                  'pdgcode;bar=5;logy', 'ux:uy:uz;points=50;display_edit=pdgcode == 2112',
                  'ekin/MeV;display_edit=ekin > 5000eV', 'ekin/MeV;display_by=1',
                  'x/cm:y/cm;display_edit=rotate_z(45deg); ekin > 5000eV;;',
                  'ekin/MeV;display_by=pdgcode in (neutron,gamma)', 'x/cm:y/cm;equal;logz=0',
                  'ekin/MeV;logx=auto;logy=auto;unweighted;print;lethargy=0', 'ekin/eV;range=0:1e3' ):
        c = _canonical_hist(text)
        assert _canonical_hist(c) == c, ( text, c )
        #(the same options, with ranges compared by their values, while the
        #expressions are compared above):
        a, k = ( { o : ( v.lo, v.hi, v.dim ) if isinstance(v,_Range) else v
                   for o, v in _parse_hist(h).items()
                   if o not in ( 'exprs', 'display_by', 'display_edit' ) } for h in ( text, c ) )
        assert a == k, ( text, a, k )
        print(f'  {text!r} -> {c!r}')
    for bad in ( 'ekin/MeV;foo', 'ekin/MeV;bins=x', 'x > 1MeV' ):
        try:
            _canonical_hist(bad)
        except MCPLError as e:
            print(f'  {bad!r}: {e}')

def test_merge():
    print('Files extracted with conditions written in different ways can be merged:')
    d = pathlib.Path('merge')
    d.mkdir()
    env = { **os.environ, 'PYMCPLTOOL_FAKE_PYVERSION' : '1' }
    def tool( *args ):
        rv = subprocess.run( [ sys.executable, '-m', 'mcpldev', *map(str,args) ], cwd = d,
                             capture_output = True, check = False, env = env )
        assert rv.returncode == 0 and not rv.stderr, ( args, rv.stdout, rv.stderr )
    shutil.copy(reffile,d/'in.mcpl.gz')
    for out, edit in ( ( 'a.mcpl', 'pdgcode == neutron and ekin > 5000 eV' ),
                       ( 'b.mcpl', '(pdgcode==2112) and ekin>5keV' ) ):
        tool('--extract','-e',edit,'in.mcpl.gz',out)
        with mcpl.MCPLFile(d/out) as f:
            print(f'  {out} (-e "{edit}"): {f.comments[-1]}')
    tool('--merge','merged.mcpl','a.mcpl','b.mcpl')
    n = []
    for fn in ( 'a.mcpl', 'b.mcpl', 'merged.mcpl' ):
        with mcpl.MCPLFile(d/fn) as f:
            n.append(f.nparticles)
    assert n[2] == n[0] + n[1] > 0, n
    print(f'  merged.mcpl: {n[0]} + {n[1]} = {n[2]} particles')

if __name__ == '__main__':
    b = block()
    test_examples(b)
    test_expressions(b)
    test_errors(b)
    test_random(b)
    test_hist()
    test_merge()
