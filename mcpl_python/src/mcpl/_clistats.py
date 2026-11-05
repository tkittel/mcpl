
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

"""The --stats, --window, and --terminal modes of mcpltool, separate from _cli
so that the other modes do not load the code for statistics, histograms, and
plots."""

__all__ = []

import contextlib
import os

from ._common import MCPLError
from ._reader import MCPLFile


def _view( filename, skip, limit, edit ):
    """The file opened with -s, -l, and -e (where -l0 is all particles)"""
    return MCPLFile(filename,skip=skip or 0,limit=limit or None,edit=edit)

def _plot_backend( outfn, terminal, color = None, allow_overwrite = False ):
    """Backend object for showing the histogram of mcpltool -w (in a window)
    or -t (in the terminal, with the --color setting), or saving it in outfn
    (with -o, where an existing file is only overwritten if allowed)"""
    from ._plotregistry import _save_backend, _show_backend
    if outfn:
        if not allow_overwrite and os.path.lexists(outfn):
            raise MCPLError(f'The output file "{outfn}" already exists.')
        bk = _save_backend(outfn)
        bk.check_format(outfn)
        return bk
    return _show_backend(terminal,color=color,
                         hint=' Use -t to show the histogram in the terminal.')

def mcpltool_stats(filename,skip,limit,edit,bad):
    from ._stats import _EditedFile, dump_stats
    if MCPLFile(filename).nparticles == 0:
        bad("Can not calculate statistics for an empty file")
    f = _EditedFile(_view(filename,skip,limit,edit),None)
    if f.nparticles == 0:
        bad("Can not calculate statistics when no particles are kept")
    dump_stats(f)

def mcpltool_hist(filelist,hist,skip,limit,edit,outfn,terminal,bad,color=None,
                  allow_overwrite=False):
    """The histogram of mcpltool -w or -t (shown with matplotlib, or in the
    terminal if terminal is set), printed with the print option, or else
    plotted (in the file outfn with -o, or else shown)"""
    from ._histfill import _fill
    from ._histstring import _parse_hist
    if not filelist:
        bad("No input file specified")
    #(the histogram string is already checked, see _cli):
    o = _parse_hist(hist)
    if o['print'] and ( outfn or color ):
        bad("The histogram option print can not be used together with -o or --color.")
    files = contextlib.ExitStack()
    sources = [ files.enter_context(_view(fn,skip,limit,edit)) for fn in filelist ]
    try:
        selection = None if edit is None else edit.expression
        #Unless the number of bins is given, it is chosen automatically, with at
        #most the resolution of the plot (if the backend has one, like the text
        #backends, whose plots are then fitted to the bins):
        bk = maxbins = None
        if not o['print']:
            try:
                bk = _plot_backend(outfn,terminal,color,allow_overwrite)
            except MCPLError as e:
                bad(str(e))
            res = bk.resolution() if o['bins'] is None else None
            if res is not None:
                maxbins = tuple(res) if len(o['exprs']) == 2 else res[0]
        try:
            h = _fill(sources,o,_maxbins=maxbins,selection=selection)
        except MCPLError as e:
            bad(str(e),'--hist')
        if o['print']:
            print(h.to_text())
            return
        from ._histfigures import figure
        #(drawn with the bins exactly, with a whole number of columns each):
        if maxbins is not None:
            bk._fit_resolution(h._display_bins)
        try:
            if outfn:
                print('Created ' + ', '.join(bk.save([figure(h)],outfn)))
            else:
                bk.show([figure(h)])
        except MCPLError as e:
            bad(str(e))
    finally:
        files.close()
