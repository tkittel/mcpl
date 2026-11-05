
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
"""

   Scenarios of using the mcpl package (Python API and mcpltool), and running
   them in new Python processes to find the modules they really import (used by
   the pyimports test and by "mcpldevtool graph").

"""

import gzip
import json
import os
import pathlib
import shutil
import subprocess
import sys


def _tool(*args):
    return f"mcpl.app_mcpltool(['mcpltool',{','.join(repr(a) for a in args)}])"

_edit = ( "for b in mcpl.MCPLFile('example.mcpl',"
          " edit='pdgcode == neutron; rotate_z(90deg)').particle_blocks: pass" )

#( key, title, code ), the code using the files made by prepare_files:
scenarios = [
    ( 'import', 'import mcpl', 'pass' ),
    #(example.mcpl has no stat:sum entries):
    ( 'header', 'open file and read the header',
      "f = mcpl.MCPLFile('example.mcpl'); f.nparticles; f.comments" ),
    ( 'read', 'read blocks and single particles',
      ( "f = mcpl.MCPLFile('example.mcpl'); [ b.ekin.sum() for b in f.particle_blocks ]\n"
        "[ p.ux for p in mcpl.MCPLFile('example.mcpl').particles ]" ) ),
    ( 'read_gz', 'read gzipped file',
      "[ b.x for b in mcpl.MCPLFile('example.mcpl.gz').particle_blocks ]" ),
    #(the stat:sum entries of files are checked when they are opened):
    ( 'read_statsum', 'read file with stat:sum entries',
      "[ b.x for b in mcpl.MCPLFile('statsum.mcpl.gz').particle_blocks ]" ),
    ( 'wavelength', 'wavelengths',
      "[ b[b.pdgcode == 2112].wavelength for b in mcpl.MCPLFile('example.mcpl').particle_blocks ]" ),
    ( 'write', 'write blocks and single particles',
      ( "f = mcpl.MCPLOutFile('w1.mcpl'); f.add_particles(direction=(0,0,1.))\n"
        "f.add_particle(direction=(0,1.,0), ekin=2.0, pdgcode=22); f.close()" ) ),
    ( 'copy', 'copy blocks with numpy mask',
      ( "fin = mcpl.MCPLFile('example.mcpl'); fout = mcpl.MCPLOutFile('w2.mcpl')\n"
        "fout.transfer_metadata(fin)\n"
        "[ fout.add_particles(b[b.pdgcode == 2112]) for b in fin.particle_blocks ]\n"
        "fout.close()" ) ),
    ( 'merge', 'merge files',
      ( "mcpl.merge_files('w3.mcpl', ['example.mcpl','example2.mcpl']).close()\n"
        "mcpl.forcemerge_files('w4.mcpl', ['w3.mcpl','example.mcpl']).close()\n"
        "mcpl.merge_inplace('w3.mcpl', 'example.mcpl')" ) ),
    ( 'text', 'convert to text', "mcpl.convert2ascii('example.mcpl','t2.txt')" ),
    ( 'repair', 'repair', "mcpl.repair('torepair.mcpl')" ),
    ( 'edit', 'read with an edit', _edit ),
    ( 'stats', 'statistics', "mcpl.dump_stats(mcpl.collect_stats('example.mcpl'))" ),
    ( 'stats_edit', 'statistics with an edit',
      "mcpl.dump_stats(mcpl.collect_stats('example.mcpl', edit='x > 0cm'))" ),
    ( 'hist', 'histogram contents',
      "print(mcpl.histogram('example.mcpl','ekin/MeV;bins=4').contents)" ),
    ( 'tool', 'mcpltool FILE', _tool('example.mcpl') ),
    ( 'tool_edit', 'mcpltool --edit', _tool('-l3','--edit','pdgcode == gamma','example.mcpl') ),
    ( 'tool_stats', 'mcpltool --stats', _tool('--stats','example.mcpl') ),
    ( 'tool_hist', 'mcpltool --hist with print', _tool('--hist','ekin/MeV;print','example.mcpl') ),
    ( 'tool_extract', 'mcpltool --extract', _tool('--extract','example.mcpl','e1.mcpl') ),
    ( 'tool_extract_edit', 'mcpltool --extract --edit',
      _tool('--extract','example.mcpl','e2.mcpl','--edit','z += 1m') ),
    ( 'tool_merge', 'mcpltool --merge', _tool('--merge','m.mcpl','example.mcpl','example2.mcpl') ),
    ( 'tool_repair', 'mcpltool --repair', _tool('--repair','torepair2.mcpl') ),
    ( 'tool_text', 'mcpltool --text', _tool('--text','example.mcpl','t.txt') ),
    #(plots saved as text, which needs no plotting packages):
    ( 'plot', 'plot saved as text',
      "mcpl.histogram('example.mcpl','ekin/MeV;bins=4').plot('plot.txt')" ),
    ( 'tool_plot', 'mcpltool --terminal saved as text',
      _tool('--terminal','--hist','ekin/MeV','-o','tool_plot.txt','example.mcpl') ),
]

def prepare_files( data_dir ):
    """Makes the files used by the scenarios in the current directory, from the
    test data directory"""
    example_file = data_dir.joinpath('example.mcpl')
    shutil.copy(example_file, 'example.mcpl')
    shutil.copy(example_file, 'example2.mcpl')
    #File which looks like it was not properly closed (number of particles in
    #the header is 0), for repairs:
    data = bytearray(example_file.read_bytes())
    data[8:16] = bytes(8)
    pathlib.Path('torepair.mcpl').write_bytes(data)
    pathlib.Path('torepair2.mcpl').write_bytes(data)
    pathlib.Path('example.mcpl.gz').write_bytes(gzip.compress(example_file.read_bytes()))
    shutil.copy(data_dir.joinpath('ref','ref_statsum.mcpl.gz'),'statsum.mcpl.gz')

_code_template = """
import contextlib, json, os, sys
class Recorder:
    #Records the module whose code imports each module of the package (the
    #first frame outside of importlib):
    imports = []
    def find_spec( self, name, path, target = None ):
        if name.startswith('{package}.'):
            f = sys._getframe(1)
            while f.f_globals.get('__name__','').startswith(('importlib','_frozen_importlib')):
                f = f.f_back
            Recorder.imports.append( ( f.f_globals.get('__name__'), name ) )
        return None
sys.meta_path.insert(0,Recorder())
import {package} as mcpl
with open(os.devnull,'w',encoding='utf-8') as devnull, contextlib.redirect_stdout(devnull):
    try:
{code}
    except SystemExit:
        pass
print(json.dumps([sorted(sys.modules),Recorder.imports]))
"""

def run_scenario( code, package, pythonpath ):
    """Runs the code (in the current directory) in a new Python process, with
    the mcpl package imported from the named package and the directories as
    PYTHONPATH. Returns (the modules of the package imported, as names without
    the package and with __init__ for the package itself, all other top level
    modules imported, and the imports as (importing module, imported module) of
    the modules of the package)."""
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(str(p) for p in pythonpath)
    code = ''.join( f'        {line}\n' for line in code.splitlines() )
    rv = subprocess.run([sys.executable,'-c',_code_template.format(package=package,code=code)],
                        capture_output=True, text=True, env=env, check=False)
    if rv.returncode != 0:
        raise RuntimeError(f'scenario failed:\n{rv.stderr}')
    mods, imports = json.loads(rv.stdout.strip().splitlines()[-1])
    def short( m ):
        return '__init__' if m == package else m[len(package)+1:]
    own = { short(m) for m in mods if m == package or m.startswith(package + '.') }
    others = { m.split('.')[0] for m in mods if m.split('.')[0] != package }
    return own, others, [ ( short(a), short(b) ) for a, b in imports ]
