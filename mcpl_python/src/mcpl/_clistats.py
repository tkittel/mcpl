
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


def _view( filename, skip, limit, pick, edit ):
    """The particles of a file to use, after -s, -l, -p, and -E"""
    from ._reader import _FileView
    f = MCPLFile(filename)
    if not ( skip or limit or pick is not None or edit is not None ):
        return f
    return _FileView(f,skip,limit,pick,edit)

def _plot_backend( outfn, terminal, color = None, allow_overwrite = False ):
    """Backend object for showing the histogram of mcpltool -H (in a window,
    or with -t in the terminal, with the --color setting), or saving it in outfn
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

def mcpltool_stats(filename,skip,limit,pick,edit):
    from ._stats import _PickedFile, dump_stats
    f = _view(filename,skip,limit,pick,edit)
    if MCPLFile(filename).nparticles == 0:
        raise MCPLError("can not calculate statistics for an empty file")
    if f.nparticles == 0:
        raise MCPLError("can not calculate statistics when no particles are picked")
    dump_stats(_PickedFile(f,None))

def mcpltool_hist(filelist,hist,skip,limit,pick,edit,outfn,terminal,bad,color=None,
                  allow_overwrite=False):
    """The histogram of mcpltool -H (shown with matplotlib, or in the
    terminal if terminal is set), printed with the print option, or else
    plotted (in the file outfn with -o, or else shown)"""
    from ._histfill import _fill
    from ._histstring import _parse_hist
    if not filelist:
        bad("no input file specified")
    #(the histogram string is already checked, see _cli):
    o = _parse_hist(hist)
    if o['print'] and ( outfn or color ):
        bad("the histogram option print can not be used together with -o or --color")
    files = contextlib.ExitStack()
    sources = [ files.enter_context(_view(fn,skip,limit,pick,edit)) for fn in filelist ]
    try:
        selection = tuple( None if e is None else e.expression for e in ( pick, edit ) )
        #Unless the number of bins is given, it is chosen automatically, with at
        #most the resolution of the plot (if the backend has one, like the text
        #backends, whose plots are then fitted to the bins):
        bk = maxbins = None
        if not o['print']:
            bk = _plot_backend(outfn,terminal,color,allow_overwrite)
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
        if outfn:
            print('Created ' + ', '.join(bk.save([figure(h)],outfn)))
        else:
            bk.show([figure(h)])
    finally:
        files.close()
