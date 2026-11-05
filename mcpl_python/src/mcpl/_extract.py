
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

"""Extracting particles into a new file, as with mcpltool -x, and the output
file names of mcpltool."""

__all__ = []

from ._messages import _info, _warning
from ._reader import MCPLFile, _blocks_in_range, _particle_range
from ._writer import MCPLOutFile


def _shell_arg( expression ):
    """Expression in double quotes, as a command-line argument"""
    #(enough for sh, bash, zsh, fish, tcsh, cmd, and PowerShell, since the
    #characters which are special inside double quotes are not allowed)
    return f'"{expression}"'

def _range_options( skip, limit, edit ):
    """The options -l, -s, and -e of mcpltool for the range of particles and
    the edit (an expression as a text, or None)"""
    opts = ( [ f'-l{limit}' ] if limit else [] ) + ( [ f'-s{skip}' ] if skip else [] )
    if edit is not None:
        opts += [ '-e', _shell_arg(edit) ]
    return opts

def _statsum_marking( f, skip, limit, edit, keepstatsum = False ):
    """Why the stat:sum entries of the file f are marked as not available (-1)
    in a file with its particles in a range (skip and limit), edited (with a
    ParticleEdit, or None): 'positions' when keeping particles based on their
    positions in the file, 'weights' when editing their weights (unless
    keepstatsum), or None (see the guidelines for stat:sum entries)"""
    if not any( v is not None for v in f.stat_sum.values() ):
        return None
    n = f.nparticles
    if n > 0 and ( ( skip or 0 ) > 0 or 0 < ( limit or 0 ) < n
                   or ( edit is not None and edit._uses_fileidx ) ):
        return 'positions'
    if not keepstatsum and edit is not None and 'weight' in edit.modified_fields:
        return 'weights'
    return None

def _tool_check_outfn( fn, inputs, allow_overwrite = False ):
    """Usage error message unless the output file of --merge, --forcemerge or
    --extract can be created, or None if it can. Checked
    before creating the file, so the output of a failed command can be
    removed."""
    from ._common import MCPLError
    from ._writer import _check_merge_output
    try:
        _check_merge_output( fn, inputs, allow_overwrite )
    except MCPLError as e:
        return f'{e}.'
    return None

def _mcpltool_close(outfile):
    """Close the output of --merge, --forcemerge, or --extract, returning its
    name. If compressing it (for names ending with .mcpl.gz) fails, the
    uncompressed output is kept, with a warning."""
    if not outfile._gzip_at_close or outfile._dry_run:
        outfile.close()
        return outfile.filename + ( '.gz' if outfile._gzip_at_close else '' )
    if not outfile._close( gzip_errors = False ):
        _warning("Failed to gzip output. Non-gzipped output is"
                 f" found in {outfile.filename}")
        return outfile.filename
    return outfile.filename + '.gz'

def _mcpltool_extract(filelist, limit, skip, edit, preventcomment,
                      keepstatsum, dry_run, bad, allow_overwrite = False):
    if len(filelist) > 2:
        bad("Too many arguments.")
    if len(filelist) != 2:
        bad("Must specify both input and output files with --extract.")
    outfn = filelist[1]
    err = _tool_check_outfn( outfn, filelist[:1], allow_overwrite )
    if err:
        bad(err)
    limit = limit or 0
    skip = skip or 0
    with MCPLFile(filelist[0],raw_strings=True) as fi:
        #Only warn about NaN or infinite values in the particles in the range
        #given by -s and -l:
        fi._check_nonfinite = False
        fo = MCPLOutFile(outfn, allow_overwrite = allow_overwrite, _dry_run = dry_run)
        #(a failed extraction must not leave an output file behind)
        try:
            fo.transfer_metadata(fi)
            n_in = fi.nparticles
            if not preventcomment:
                #Describe which particles were extracted (but nothing specific
                #to the input file, to keep files extracted in the same way
                #mergeable):
                opts = _range_options(skip,limit,None if edit is None else edit.expression)
                fo.hdr_add_comment('mcpltool: extracted particles'
                                   + ( ' with ' + ' '.join(opts)
                                       if opts else '' ))
            marking = _statsum_marking(fi,skip,limit,edit,keepstatsum)
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
            for b in fi.particle_blocks:
                fo.add_particles(b)
            n_added = fo.nparticles
            outname = _mcpltool_close(fo)
        except BaseException:
            fo._abort()
            raise
    _info(f"{'Would extract' if dry_run else 'Successfully extracted'}"
          f" {n_added} / {n_in} particles from {filelist[0]} into {outname}")
