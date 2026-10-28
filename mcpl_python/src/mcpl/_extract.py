
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

"""Extracting particles into a new file, as with mcpltool -e (also used by the
viewer), and the output file names of mcpltool."""

__all__ = []

import pathlib

from ._messages import _info, _warning
from ._reader import MCPLFile, _blocks_in_range, _particle_range
from ._writer import MCPLOutFile


def _shell_arg( expression ):
    """Expression in double quotes, as a command-line argument"""
    #(enough for sh, bash, zsh, fish, tcsh, cmd and PowerShell, since the
    #characters which are special inside double quotes are not allowed)
    return f'"{expression}"'

def _shell_path( filename ):
    """The filename as a command-line argument (in double quotes if it has
    spaces)"""
    return _shell_arg(filename) if ' ' in filename else filename

def _range_options( skip, limit, pick, edit ):
    """The options -l, -s, -p and -E of mcpltool for the range of particles
    and the pick and edit (expressions as texts, or None)"""
    opts = ( [ f'-l{limit}' ] if limit else [] ) + ( [ f'-s{skip}' ] if skip else [] )
    for opt, e in ( ('-p',pick), ('-E',edit) ):
        if e is not None:
            opts += [ opt, _shell_arg(e) ]
    return opts

def _statsum_marking( f, skip, limit, pick, edit, keepstatsum = False ):
    """Why the stat:sum entries of the file f are marked as not available (-1)
    in a file with its particles in a range (skip and limit), picked and edited
    (a ParticleFilter and a ParticleEdit, or None): 'positions' when picking
    particles based on their positions in the file, 'weights' when editing
    their weights (unless keepstatsum), or None, as in mcpltool-c (see the
    guidelines for stat:sum entries)"""
    if not any( v is not None for v in f.stat_sum.values() ):
        return None
    n = f.nparticles
    if n > 0 and ( ( skip or 0 ) > 0 or 0 < ( limit or 0 ) < n
                   or ( pick is not None and pick._uses_fileidx ) ):
        return 'positions'
    if not keepstatsum and edit is not None and 'weight' in edit.modified_fields:
        return 'weights'
    return None

def _tool_outfn(fn):
    """Output filename for --merge and --extract like in mcpltool (returns error
    message, filename to create, and whether to gzip it)."""
    if pathlib.Path(fn).is_file():
        return "Requested output file already exists.", None, False
    if fn.endswith('.mcpl.gz'):
        if pathlib.Path(fn[:-3]).is_file():
            return ( "Requested output file already exists (without .gz extension).",
                     None, False )
        return None, fn[:-3], True
    if fn.endswith('.gz'):
        return ( "Requested output file should not have .gz extension (unless it is .mcpl.gz).",
                 None, False )
    if not fn.endswith('.mcpl') and pathlib.Path(fn+'.mcpl').is_file():
        return "Requested output file already exists (with .mcpl extension).", None, False
    return None, fn, False

def _mcpltool_close(outfile, attempt_gzip):
    if attempt_gzip:
        if not outfile.closeandgzip():
            _warning("Failed to gzip output. Non-gzipped output is"
                     f" found in {outfile.filename}")
            return outfile.filename
        return outfile.filename + '.gz'
    outfile.close()
    return outfile.filename

def _mcpltool_extract(filelist, limit, skip, pick, edit, preventcomment,
                      keepstatsum, dry_run, bad):
    if len(filelist) > 2:
        bad("Too many arguments.")
    if len(filelist) != 2:
        bad("Must specify both input and output files with --extract.")
    err, outfn, attempt_gzip = _tool_outfn(filelist[1])
    if err:
        bad(err)
    limit = limit or 0
    skip = skip or 0
    with MCPLFile(filelist[0],raw_strings=True) as fi:
        #Like mcpltool-c, only warn about NaN or infinite values in the
        #particles in the range given by -s and -l:
        fi._check_nonfinite = False
        fo = MCPLOutFile(outfn, _dry_run = dry_run)
        #(a failed extraction must not leave an output file behind)
        try:
            fo.transfer_metadata(fi)
            n_in = fi.nparticles
            if not preventcomment:
                #Describe which particles were extracted (but nothing specific
                #to the input file, to keep files extracted in the same way
                #mergeable):
                opts = _range_options(skip,limit,*( None if e is None else e.expression
                                                    for e in ( pick, edit ) ))
                fo.hdr_add_comment('mcpltool: extracted particles'
                                   + ( ' with ' + ' '.join(opts)
                                       if opts else '' ))
            marking = _statsum_marking(fi,skip,limit,pick,edit,keepstatsum)
            if marking == 'positions':
                _warning("Marking stat:sum entries in output file as "
                         "not available (-1) when filtering based on particle "
                         "positions")
            elif marking == 'weights':
                _warning("Marking stat:sum entries in output file as "
                         "not available (-1) when editing particle weights"
                         " (use --keep-statsum to keep them)")
            if marking is not None:
                fo.hdr_scale_stat_sums(-1.0)
            for b in _blocks_in_range(fi.particle_blocks,*_particle_range(n_in,skip,limit or None)):
                fi._warn_if_nonfinite(b)
                if pick is not None:
                    b = b[pick(b)]
                if edit is not None:
                    fo.add_particles(b,**edit(b))
                else:
                    fo.add_particles(b)
            n_added = fo.nparticles
            outname = _mcpltool_close(fo,attempt_gzip)
        except BaseException:
            fo._abort()
            raise
    _info(f"{'Would extract' if dry_run else 'Successfully extracted'}"
          f" {n_added} / {n_in} particles from {filelist[0]} into {outname}")
