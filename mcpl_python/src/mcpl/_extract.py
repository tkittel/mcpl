
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

"""Extracting particles into a new file, as with mcpltool -x (also used by the
viewer), and the output file names of mcpltool."""

__all__ = []

from ._messages import _info, _warning
from ._reader import MCPLFile
from ._writer import MCPLOutFile


def _shell_arg( expression ):
    """Expression in double quotes, as a command-line argument"""
    #(enough for sh, bash, zsh, fish, tcsh, cmd, and PowerShell, since the
    #characters which are special inside double quotes are not allowed)
    return f'"{expression}"'

def _option_arg( text, hist = False ):
    """The text of -e or -H (hist) as a command-line argument, with its first
    statement or expression (before the first ";", or for a histogram also
    before the first ":") in parentheses if it starts with "-", which would
    otherwise be taken as an option (statements starting with "-" are filter
    conditions, which can be put in parentheses)"""
    if text.startswith('-'):
        first, sep, rest = text.partition(';')
        if hist:
            first, colon, others = first.partition(':')
            rest = ( f' : {others.strip()}' if colon else '' ) + sep + rest
        else:
            rest = sep + rest
        text = f'({first.strip()})' + rest
    return _shell_arg(text)

def _shell_path( filename ):
    """The filename as a command-line argument (in double quotes if it has
    spaces)"""
    return _shell_arg(filename) if ' ' in filename else filename

def _range_options( skip, limit, edit ):
    """The options -l, -s, and -e of mcpltool for the range of particles and
    the edit (an expression as a text, or None)"""
    opts = ( [ f'-l{limit}' ] if limit else [] ) + ( [ f'-s{skip}' ] if skip else [] )
    if edit is not None:
        opts += [ '-e', _option_arg(edit) ]
    return opts

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

def _extraction_comment( skip, limit, edit ):
    """The comment of mcpltool -x describing which particles were extracted
    (but nothing specific to the input file, to keep files extracted in the
    same way mergeable)"""
    opts = _range_options(skip,limit,None if edit is None else edit.expression)
    return 'mcpltool: extracted particles' + ( ' with ' + ' '.join(opts) if opts else '' )

def _mcpltool_code(filename, lang, limit, skip, edit, preventcomment):
    """Print the program in the language (c or cpp) which does what mcpltool
    -x does with the options, for files like the given one (with its
    userdata layout and stat:sum entries), see _expr_ast2c"""
    with MCPLFile(filename,skip=skip,limit=limit,edit=edit) as f:
        layout, ( scale, reason ) = f.userdata_layout, f._stat_sum_scale
        skip, limit = f._skip, f._limit
    from ._expressions import _edit_code
    print(_edit_code(lang,edit,layout,skip = skip,limit = limit,
                     statsums = ( None if scale is None else 'unavailable'
                                  if reason == 'fileidx' else 'scaled' ),
                     comment = None if preventcomment else _extraction_comment(skip,limit,edit)),
          end='')

def _mcpltool_extract(infn, outfn, limit, skip, edit, preventcomment,
                      dry_run, allow_overwrite = False):
    from ._writer import _check_merge_output
    _check_merge_output(outfn,[ infn ],allow_overwrite)
    with MCPLFile(infn,raw_strings=True,skip=skip,limit=limit,edit=edit) as fi:
        skip, limit = fi._skip, fi._limit
        fo = MCPLOutFile(outfn, allow_overwrite = allow_overwrite, _dry_run = dry_run)
        #(a failed extraction must not leave an output file behind)
        try:
            fo.transfer_metadata(fi)
            n_in = fi._nparticles_raw
            if not preventcomment:
                fo.hdr_add_comment(_extraction_comment(skip,limit,edit))
            scale, reason = fi._stat_sum_scale
            if scale == -1.0:
                _warning("Setting stat:sum entries in output file to -1"
                         " (not available), as "
                         + ( "-e filters on the positions of the particles in"
                             " the file (fileidx)" if reason == 'fileidx'
                             else "no particles are in the range of -s and -l" ))
            elif scale is not None:
                _info("Scaling stat:sum entries in output file by the fraction"
                      f" of the particles in the range of -s and -l ({scale:.6g})")
            if scale is not None:
                fo.hdr_scale_stat_sums(scale)
            for b in fi.particle_blocks:
                fo.add_particles(b)
            n_added = fo.nparticles
            outname = _mcpltool_close(fo)
        except BaseException:
            fo._abort()
            raise
    _info(f"{'Would extract' if dry_run else 'Successfully extracted'}"
          f" {n_added} / {n_in} particles from {infn} into {outname}")
