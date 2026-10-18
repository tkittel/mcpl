
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
    from ._plotbackend import PlotBackend
    if color is None or isinstance(cls,PlotBackend):
        return {}
    if cls.kind == 'terminal' and f'{cls.name}_color' in _option_names(cls):
        return { f'{cls.name}_color' : color }
    if backend is not None:
        raise MCPLError(f'--color can not be used with the {cls.name}'
                        ' plotting backend (only for plots in the terminal)')
    return {}

def _option_names( cls ):
    import inspect
    return set(inspect.signature(cls).parameters)

def mcpltool_stats(filename,skip,limit,pick,edit,outfn,backend,bad):
    from ._stats import _PickedFile, dump_stats
    f = _view(filename,skip,limit,pick,edit)
    if MCPLFile(filename).nparticles == 0:
        bad("Can not calculate statistics for an empty file")
    if f.nparticles == 0:
        bad("Can not calculate statistics when no particles are picked")
    f = _PickedFile(f,None)
    if not outfn:
        dump_stats(f)
        return
    from ._statsplot import plot_stats
    try:
        files = plot_stats(f,filename=outfn,backend=_plot_backend(outfn,backend,False))
    except MCPLError as e:
        bad(str(e))
    if files:
        print('Created ' + ', '.join(files))

def mcpltool_hist(filelist,histstr,skip,limit,pick,edit,outfn,backend,terminal,bad,
                  color=None):
    from ._histogram import _histogram, _parse_hist
    if not filelist:
        bad("No input file specified")
    try:
        o = _parse_hist(histstr)
    except MCPLError as e:
        bad(str(e))
    if o['print'] and ( outfn or backend or terminal or color ):
        bad("The histogram option print can not be used together with -o, -B,"
            " -t or --color.")
    exprs = o['exprs']
    #Unless the number of bins is given, it is chosen automatically, with at
    #most the resolution of the plot (if the backend has one, like the text
    #backends, whose plots are then fitted to the bins):
    bk, maxbins = None, None
    if not o['print']:
        try:
            bk = _plot_backend(outfn,backend,terminal,color)
        except MCPLError as e:
            bad(str(e))
        if o['bins'] is None:
            res = bk.resolution()
            if res is not None:
                maxbins = tuple(res) if len(exprs) == 2 else res[0]
    sources = [ _view(fn,skip,limit,pick,edit) for fn in filelist ]
    try:
        h = _histogram(sources,o,_maxbins=maxbins)
    except MCPLError as e:
        bad(str(e))
    title = [ f'{what}: {e.expression}' for what, e in (('pick',pick),
                                                         ('edit',edit))
              if e is not None ]
    if title:
        h.title = '\n'.join(title)
    if o['print']:
        print(h.to_text())
        return
    try:
        if maxbins is not None and hasattr(bk,'_fit_resolution'):
            #(draw the bins exactly, with a whole number of columns each):
            bk._fit_resolution(h._display_bins)
        files = h.plot(filename=outfn,backend=bk)
    except MCPLError as e:
        bad(str(e))
    if files:
        print('Created ' + ', '.join(files))
