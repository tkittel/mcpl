
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
from ._reader import MCPLFile
from ._writer import MCPLOutFile


def _shell_arg( expression ):
    """Expression in double quotes, as a command-line argument"""
    #(enough for sh, bash, zsh, fish, tcsh, cmd and PowerShell, since the
    #characters which are special inside double quotes are not allowed)
    return f'"{expression}"'

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
                opts = ( ( [ f'-l{limit}' ] if limit > 0 else [] )
                         + ( [ f'-s{skip}' ] if skip > 0 else [] ) )
                for opt, e in ( ('-p',pick), ('-E',edit) ):
                    if e is not None:
                        opts += [ opt, _shell_arg(e.expression) ]
                fo.hdr_add_comment('mcpltool: extracted particles'
                                   + ( ' with ' + ' '.join(opts)
                                       if opts else '' ))
            #As in mcpltool-c, stat:sum entries are marked as not available
            #when picking particles based on their positions in the file,
            #and also when editing their weights unless --keep-statsum was
            #used (see the guidelines for stat:sum entries):
            has_statsum = any( v is not None for v in fi.stat_sum.values() )
            by_position = ( skip > 0 or 0 < limit < n_in
                            or ( pick is not None and pick._uses_fileidx ) )
            if has_statsum and n_in > 0 and by_position:
                _warning("Marking stat:sum entries in output file as "
                         "not available (-1) when filtering based on particle "
                         "positions")
                fo.hdr_scale_stat_sums(-1.0)
            elif ( has_statsum and not keepstatsum and edit is not None
                   and 'weight' in edit.modified_fields ):
                _warning("Marking stat:sum entries in output file as "
                         "not available (-1) when editing particle weights"
                         " (use --keep-statsum to keep them)")
                fo.hdr_scale_stat_sums(-1.0)
            iend = skip + limit if limit > 0 else n_in
            for b in fi.particle_blocks:
                off = b.file_offset
                if off + len(b) <= skip:
                    continue
                if off >= iend:
                    break
                b = b[max(0,skip-off):min(len(b),iend-off)]
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
