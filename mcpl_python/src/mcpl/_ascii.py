
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

"""Conversion of MCPL files to a simple ASCII-based text format."""


__all__ = ['convert2ascii']

from ._reader import MCPLFile


def convert2ascii(mcplfile,outfile,*,allow_overwrite=False):
    """Read particle contents of mcplfile and write into outfile using a simple
    ASCII-based format. An existing outfile is only overwritten if
    allow_overwrite is True."""
    if not hasattr(outfile,'write'):
        import os
        if not allow_overwrite and os.path.lexists(outfile):
            from ._common import MCPLError
            raise MCPLError(f'The output file "{os.fspath(outfile)}" already exists')
        with open(outfile,'w') as fh:
            convert2ascii(mcplfile,fh)
        return
    if not isinstance(mcplfile,MCPLFile):
        with MCPLFile(mcplfile) as mfh:
            convert2ascii(mfh,outfile)
        return

    fout = outfile
    fin = mcplfile
    n = fin.nparticles
    if n is None:
        #(an edit filters out particles, so they must be counted first):
        n = sum( len(b) for b in fin.particle_blocks )
    fout.write(f"#MCPL-ASCII\n#ASCII-FORMAT: v1\n#NPARTICLES: {n}\n")
    #Userdata is not included in the output, which is noted in the header:
    if fin.userdata_size:
        fout.write("#WARNING: The userdata of the particles in the MCPL file is"
                   " not included\n")
    fout.write("#END-HEADER\n")
    fout.write("index     pdgcode               ekin[MeV]                   x[cm]          "
               +"         y[cm]                   z[cm]                      ux                  "
               +"    uy                      uz                time[ms]                  weight  "
               +"                 pol-x                   pol-y                   pol-z  userflags\n")
    fmtstr="%5i %11i %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g 0x%08x\n"
    for idx,p in enumerate(fin.particles):
        fout.write(fmtstr%(idx,p.pdgcode,p.ekin,p.x,p.y,p.z,p.ux,p.uy,p.uz,p.time,p.weight,p.polx,p.poly,p.polz,p.userflags))
