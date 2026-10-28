
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

"""The --stats and --hist modes of mcpltool, separate from _cli so that the
other modes do not load the code for statistics, histograms and plots."""

__all__ = []

import contextlib
import os

from ._common import MCPLError
from ._reader import MCPLFile


def _view( filename, skip, limit, pick, edit ):
    """The particles of a file to use, after -s, -l, -p and -E"""
    from ._reader import _FileView
    f = MCPLFile(filename)
    if not ( skip or limit or pick is not None or edit is not None ):
        return f
    return _FileView(f,skip,limit,pick,edit)

def _plot_backend( outfn, backend, terminal, color = None ):
    """Backend object for showing plots (or saving them in outfn), with the
    options for mcpltool (e.g. a backend of matplotlib which needs no display
    when saving files, and the --color setting for plots in the terminal)"""
    from ._plotbackend import PlotBackend, _create, _save_backend, _show_backend
    if outfn:
        if os.path.exists(outfn):
            raise MCPLError("Requested output file already exists.")
        cls = _save_backend(outfn,backend)
        bk = _create(cls,**( {} if isinstance(cls,PlotBackend) else cls.batch_options ))
        bk.check_format(outfn)
        return bk
    cls = _show_backend(backend,terminal)
    return _create(cls,**_color_options(cls,backend,color))

def _color_options( cls, backend, color ):
    """Options of the backend (class) for the --color setting (None if not
    given), for plots in the terminal. An error if the backend was chosen
    (backend is not None) and is not for the terminal."""
    from ._plotbackend import PlotBackend, _option_names
    if color is None or isinstance(cls,PlotBackend):
        return {}
    if cls.kind == 'terminal' and f'{cls.name}_color' in _option_names(cls):
        return { f'{cls.name}_color' : color }
    if backend is not None:
        raise MCPLError(f'--color can not be used with the {cls.name}'
                        ' plotting backend (only for plots in the terminal)')
    return {}

def mcpltool_stats(filename,skip,limit,pick,edit,bad):
    from ._stats import _PickedFile, dump_stats
    with MCPLFile(filename) as raw:
        if raw.nparticles == 0:
            bad("Can not calculate statistics for an empty file")
    with _view(filename,skip,limit,pick,edit) as f:
        if f.nparticles == 0:
            bad("Can not calculate statistics when no particles are picked")
        dump_stats(_PickedFile(f,None))

def mcpltool_hist(filelist,hists,skip,limit,pick,edit,outfn,backend,terminal,bad,
                  color=None):
    """The histograms of -H (which can be given several times): printed (with
    the print option), or plotted (in a file with -o, with a page or file for
    each, or else shown)"""
    from ._histogram import _histogram
    from ._histstring import _parse_hist
    if not filelist:
        bad("No input file specified")
    opts = []
    for histstr in hists:
        try:
            opts.append(_parse_hist(histstr))
        except MCPLError as e:
            bad(str(e))
        if opts[-1]['print'] and ( outfn or backend or terminal or color ):
            bad("The histogram option print can not be used together with -o, -B,"
                " -t or --color.")
    files = contextlib.ExitStack()
    sources = [ files.enter_context(_view(fn,skip,limit,pick,edit)) for fn in filelist ]
    try:
        selection = tuple( None if e is None else e.expression for e in ( pick, edit ) )
        figures = []#(plotted together at the end, in a file or in windows, with the
                    #numbers of bins to fit the plot to, see below)
        bk = None
        for o in opts:
            #Unless the number of bins is given, it is chosen automatically, with
            #at most the resolution of the plot (if the backend has one, like the
            #text backends, whose plots are then fitted to the bins):
            maxbins = None
            if not o['print']:
                try:
                    bk = _plot_backend(outfn,backend,terminal,color)
                except MCPLError as e:
                    bad(str(e))
                res = bk.resolution() if o['bins'] is None else None
                if res is not None:
                    maxbins = tuple(res) if len(o['exprs']) == 2 else res[0]
            try:
                h = _histogram(sources,o,_maxbins=maxbins,selection=selection)
            except MCPLError as e:
                bad(str(e))
            if o['print']:
                print(h.to_text())
            elif outfn or bk.resolution() is None:
                figures.append( ( h.figure(), h._display_bins if maxbins is not None else None ) )
            else:
                #(in the terminal, each is drawn when it is ready, with the bins
                #drawn exactly, with a whole number of columns each):
                if maxbins is not None:
                    bk._fit_resolution(h._display_bins)
                try:
                    h.plot(backend=bk)
                except MCPLError as e:
                    bad(str(e))
        if figures:
            from .plotting import save, show
            if len(figures) == 1 and figures[0][1] is not None and bk.resolution() is not None:
                bk._fit_resolution(figures[0][1])#(as in the terminal, see above)
            figures = [ f for f, _ in figures ]
            try:
                if outfn:
                    print('Created ' + ', '.join(save(figures,outfn,backend=bk)))
                else:
                    show(figures,backend=bk)
            except MCPLError as e:
                bad(str(e))
    finally:
        files.close()
