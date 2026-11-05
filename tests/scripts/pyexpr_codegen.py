
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

# Tests of the C and C++ code generated for picks and edits (_expr_ast2c and
# _expr_ast2cpp), without compiling it (which mcpldevtool codegen does): the
# programs for some picks and edits, the helper functions they use, and the
# errors. The log freezes the generated code.

from mcpldev._common import MCPLError
from mcpldev._expr_ast2c import _expr_ast2c
from mcpldev._expr_ast2cpp import _expr_ast2cpp


def show( pick, edit, layout = None, **options ):
    for lang, fct in ( ( 'C', _expr_ast2c ), ( 'C++', _expr_ast2cpp ) ):
        print(f'===== {lang} for pick {pick!r}, edit {edit!r}' + ( f', layout {layout!r}' if layout else '' )
              + ''.join( f', {k} {v!r}' for k, v in options.items() ))
        print(fct(pick,edit,layout,**options),end='')

def test_programs():
    show('pdgcode in (neutron,gamma) and userdata.id+1 > 100 and mod(userflags,4) == 0',
         'ekin = 25meV; x += 1cm','id:uint64')
    show('pdgcode == neutron and ekin < 25meV',None)
    show(None,'rotate_z(90deg); pos += 50cm*dir; pdgcode = antielectron')
    #(edits of weights and PDG codes, which are refused in files with universal
    #weights or PDG codes):
    show(None,'weight *= 2; pdgcode = gamma')

def test_options():
    #(fixed filenames, the range of particles as by mcpltool -s and -l, a
    #comment, and stat:sum entries marked as not available, as for the code of
    #the viewer and mcpltool -e --code):
    show('mod(fileidx,3) == 0',None,filenames = ( 'in "a".mcpl', 'out.mcpl' ),skip = 5,limit = 10,
         comment = 'mcpltool: extracted particles with -p "mod(fileidx,3)==0"',mark_statsums = True)
    show(None,'x = fileidx*1cm',skip = 2)
    show('z > 0',None,limit = 7)

def test_helpers():
    #(the helper functions used by each kind of expression):
    for pick, edit, layout in (
            ( 'userflags + 1 > 0 and pdgcode - 1 < 0 and fileidx * 2 > 0', None, None ),
            ( 'userdata.n // 2 == 1 and -userdata.n < 0 and abs(userdata.i) > 0 and userflags > pdgcode',
              None, 'n:uint64,i:int64' ),
            ( 'sqrt(ekin/MeV) > 1 and x/y > 0 and (ux)^2 > 0 and round(x/cm) > 0', None, None ),
            ( 'pdgcode == neutron and wavelength > 1Aa and angle(dir,(0,0,1)) < 1deg', None, None ),
            ( 'through_sphere((0,0,1m),5cm)', 'wavelength = 1.8Aa; userflags = 7', None ),
            ( None, 'rotate_around((1,1,0),30deg); rotate_frame(dir,(0,0,1),pos,(1,0,0))', None ),
            ( 'userdata.temp > 300K', None, 'temp:float32:K' ) ):
        code = _expr_ast2c(pick,edit,layout)
        helpers = [ line.split('(')[0].split()[-1] for line in code.splitlines()
                    if line.startswith('static ') ]
        print(f'Helpers for pick {pick!r}, edit {edit!r}: {", ".join(helpers) or "none"}')

def test_errors():
    print('Errors:')
    for pick, edit, layout in ( ( 'x > 1MeV', None, None ), ( 'userdata.temp > 300K', None, None ),
                                ( 'userdata.temp > 300K', None, 'other:float32' ),
                                ( 'userdata.d > 1', None, 'd:int32[3]' ),
                                ( 'userdata.d.at(3) > 1', None, 'd:int32[3]' ),
                                ( 'mod(userdata.f,2) == 0', None, 'f:float32' ) ):
        try:
            _expr_ast2c(pick,edit,layout)
            print(f'  {pick!r} with layout {layout!r}: no error')
        except MCPLError as e:
            print(f'  {pick!r} with layout {layout!r}: {e}')

if __name__ == '__main__':
    test_programs()
    test_options()
    test_helpers()
    test_errors()
