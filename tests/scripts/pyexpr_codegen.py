
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

# Tests of the C and C++ code generated for edit expressions (_expr_ast2c and
# _expr_ast2cpp), without compiling it (which mcpldevtool codegen does): the
# programs for some edit expressions, the helper functions they use, and the
# errors. The log freezes the generated code.

from mcpldev._common import MCPLError
from mcpldev._expressions import _edit_code


def show( edit, layout = None, **options ):
    for lang, key in ( ( 'C', 'c' ), ( 'C++', 'cpp' ) ):
        print(f'===== {lang} for edit {edit!r}' + ( f', layout {layout!r}' if layout else '' )
              + ''.join( f', {k} {v!r}' for k, v in options.items() ))
        print(_edit_code(key,edit,layout,**options),end='')

def test_programs():
    show('pdgcode in (neutron,gamma) and userdata.id+1 > 100 and mod(userflags,4) == 0;'
         ' ekin = 25meV; x += 1cm','id:uint64')
    show('pdgcode == neutron and ekin < 25meV')
    show('rotate_z(90deg); pos += 50cm*dir; pdgcode = antielectron')
    #(filter conditions after changes):
    show('rotate_y(90deg); x > 0cm; weight *= 2')
    #(edits of weights and PDG codes, which are refused in files with universal
    #weights or PDG codes):
    show('weight *= 2; pdgcode = gamma')

def test_options():
    #(fixed filenames, the range of particles as by mcpltool -s and -l, a
    #comment, and stat:sum entries marked as not available, as for the code of
    #the viewer and mcpltool -x --code):
    show('mod(fileidx,3) == 0',filenames = ( 'in "a".mcpl', 'out.mcpl' ),skip = 5,limit = 10,
         comment = 'mcpltool: extracted particles with -e "mod(fileidx,3)==0"',mark_statsums = True)
    show('x = fileidx*1cm',skip = 2)
    show('z > 0',limit = 7)

def test_helpers():
    #(the helper functions used by each kind of expression):
    for edit, layout in (
            ( 'userflags + 1 > 0 and pdgcode - 1 < 0 and fileidx * 2 > 0', None ),
            ( 'userdata.n // 2 == 1 and -userdata.n < 0 and abs(userdata.i) > 0 and userflags > pdgcode',
              'n:uint64,i:int64' ),
            ( 'sqrt(ekin/MeV) > 1 and x/y > 0 and (ux)^2 > 0 and round(x/cm) > 0', None ),
            ( 'pdgcode == neutron and wavelength > 1Aa and angle(dir,(0,0,1)) < 1deg', None ),
            ( 'through_sphere((0,0,1m),5cm); wavelength = 1.8Aa; userflags = 7', None ),
            ( 'through_box((0,0,1m),(5cm,5cm,1mm))', None ),
            ( 'rotate_around((1,1,0),30deg); rotate_frame(dir,(0,0,1),pos,(1,0,0))', None ),
            ( 'userdata.temp > 300K', 'temp:float32:K' ) ):
        code = _edit_code('c',edit,layout)
        helpers = [ line.split('(')[0].split()[-1] for line in code.splitlines()
                    if line.startswith('static ') ]
        print(f'Helpers for edit {edit!r}: {", ".join(helpers) or "none"}')

def test_widths():
    #Long lines are broken (after && and ||, then other operators and commas,
    #and comments and strings at spaces, or anywhere in strings), so the code
    #stays within 100 columns:
    long_edit = ( 'through_sphere((1cm,2cm,3cm),1cm) and abs(x)<2cm and abs(y)<2cm and'
                  ' abs(z)<20cm and ekin>0.1MeV and ekin<10MeV and weight>0.001 or'
                  ' (x+y+z)/cm*ux*uy*uz/(ekin/MeV+1)>hypot(x,y)/cm*sqrt(ekin/MeV)'
                  '+polx*poly*polz+time/ms' )
    comment = 'mcpltool: extracted particles with -e "' + long_edit + '"'
    for lang, key in ( ( 'C', 'c' ), ( 'C++', 'cpp' ) ):
        lines = _edit_code(key,long_edit,comment=comment).split('\n')
        print(f'{lang}: {len(lines)} lines, the longest {max(map(len,lines))} columns')
    show(long_edit,comment=comment)

def test_errors():
    print('Errors:')
    for edit, layout in ( ( 'x > 1MeV', None ), ( 'userdata.temp > 300K', None ),
                          ( 'userdata.temp > 300K', 'other:float32' ),
                          ( 'userdata.d > 1', 'd:int32[3]' ),
                          ( 'userdata.d.at(3) > 1', 'd:int32[3]' ),
                          ( 'mod(userdata.f,2) == 0', 'f:float32' ) ):
        try:
            _edit_code('c',edit,layout)
            print(f'  {edit!r} with layout {layout!r}: no error')
        except MCPLError as e:
            print(f'  {edit!r} with layout {layout!r}: {e}')

if __name__ == '__main__':
    test_programs()
    test_options()
    test_helpers()
    test_widths()
    test_errors()
