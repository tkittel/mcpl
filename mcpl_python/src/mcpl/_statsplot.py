
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

"""Plots of the statistics collected by collect_stats (figures for the
plotting backends), separate from _stats so that statistics can be collected
and printed without loading any plotting code."""

__all__ = ['plot_stats', 'stats_figures']

import os
import warnings

from ._common import MCPLError
from ._expressions import _domain_note, _expr_field_domains
from ._histogram import _bars_panel, _top_keys, _value_colors
from ._numpy import np
from ._physics import _pdg_label, _pdg_name
from ._plotbackend import PlotBackend
from ._stats import (
    _freq_alt_descr,
    _possible_freq_stats,
    _possible_std_stats,
    collect_stats,
)
from .plotting import (
    Bars,
    Figure,
    Hist2D,
    Panel,
    StepHist,
    Text,
    save,
    show,
)


def _type_label(k):
    """Label of a particle type in plots (with symbols, see _pdg_symbols)"""
    return 'other' if k == 'other' else _pdg_label(k,unicode=True)

def _overview_figure(stats):
    """Overview page with energy, wavelength and angle distributions by
    particle type, the x-y distribution, and times."""
    ov = stats['overview']
    info = stats['file']
    title = f"{info.get('filename','')}: {info['nparticles']} particles, sum(weights) = {info['integral']:g}"
    if info.get('pick'):
        title += f"\npick: {info['pick']}"
    if info.get('edit'):
        title += f"\nedit: {info['edit']}"
    fig = Figure( title = title, nrows = 2, ncols = 3 )
    #Same colour for each particle type in all plots:
    colors = _value_colors('pdgcode',list(ov['ekin']))
    def steps(panel,bins,hists):
        for k,h in hists.items():
            if h.any():
                panel.add(StepHist(bins,h,label=_type_label(k),color=colors.get(k)))
    def nonzero_range(bins,hists):
        nz = np.flatnonzero(sum(h for h in hists))
        return ( bins[nz[0]], bins[nz[-1]+1] ) if len(nz) else None
    p = fig.add(Panel( title = 'Kinetic energy', xlabel = 'ekin [MeV]',
                       logx = ov['ekin_log'], logy = True,
                       xlim = nonzero_range(ov['ekin_bins'],ov['ekin'].values()) ))
    steps(p,ov['ekin_bins'],ov['ekin'])
    #(the wavelength is only defined for some particles, see _expr_field_domains):
    wl_note = _domain_note([ _expr_field_domains['wavelength'] ],unicode=True)
    p = fig.add(Panel( title = f'Wavelength {wl_note}',
                       xlabel = 'wavelength [Aa]', logx = True ))
    if ov['wl']:
        lo, hi = [], []
        for k in sorted(ov['wl'],key=lambda k : colors.get(k,len(colors))):
            h, bins = ov['wl'][k], ov['wl_bins'][k]
            p.add(StepHist(bins,h,label=_type_label(k),color=colors.get(k)))
            r = nonzero_range(bins,[h])
            if r:
                lo.append(r[0])
                hi.append(r[1])
        if lo:
            p.xlim = ( min(lo), max(hi) )
    else:
        p.logx = False
        p.add(Text('No neutrons or gammas' if ov['ekin_log'] else 'Not available'))
    p = fig.add(Panel( title = 'Direction',
                       xlabel = 'angle to z axis [degrees]', logy = True,
                       xlim = ( 0.0, 180.0 ) ))
    steps(p,ov['theta_bins'],ov['theta'])
    (x0,x1),(y0,y1) = ov['xy_range']
    p = fig.add(Panel( title = 'Position', xlabel = 'x [cm]',
                       ylabel = 'y [cm]' ))
    nb = ov['xy'].shape
    p.add(Hist2D(np.linspace(x0,x1,nb[0]+1),np.linspace(y0,y1,nb[1]+1),ov['xy']))
    p = fig.add(Panel( title = 'Time', xlabel = 'time [ms]',
                       logx = ov['time_log'], logy = True ))
    p.add(StepHist(ov['time_bins'],ov['time']))
    title = 'Particle types'
    if 'pdgcode' in stats:
        u,c = stats['pdgcode']['unique_values'], stats['pdgcode']['unique_values_counts']
        sums = dict(zip(( int(e) for e in u ),( float(e) for e in c )))
        shown, rest = _top_keys(sums,10)
        keys = shown + ( [ 'other' ] if rest else [] )
        values = [ sums[k] for k in shown ] + ( [ sum( sums[k] for k in rest ) ] if rest else [] )
        colors = _value_colors('pdgcode',keys)
        fig.add(_bars_panel([ _type_label(k) for k in keys ],values,
                            [ colors[k] for k in keys ],'auto',title = title))
    else:
        fig.add(Panel( title = title ))
    return fig

def stats_figures(stats):
    """Figures (see mcpl.plotting) with plots of the statistics collected with
    collect_stats() (or a file, for which collect_stats() is called): an
    overview page, and a page for each field."""
    if not isinstance(stats,dict):
        stats = collect_stats(stats,bin_data=True)
    figures = []
    if 'overview' in stats:
        figures.append(_overview_figure(stats))
    showmax=10
    for s in _possible_freq_stats:
        if s not in stats:
            continue
        freq=stats[s]
        u,c=freq['unique_values'],freq['unique_values_counts']
        #(names of particle types with symbols, see _pdg_symbols):
        fct_alt_descr = ( ( lambda x : _pdg_name(x,True) ) if s == 'pdgcode'
                          else _freq_alt_descr.get(s,lambda x: None) )
        def fmt_fct_raw(x, fct_alt_descr=fct_alt_descr):
            alttxt = fct_alt_descr(x)
            return f'{x!s}\n({alttxt})' if alttxt is not None else str(x)
        names = [ fmt_fct_raw(x) for x in u ]
        if len(c)>showmax:
            sum_other = c[showmax-1:].sum()
            names, c = names[0:showmax], c[0:showmax].copy()
            c[showmax-1] = sum_other
            names[showmax-1] = 'other'
        percents = c.astype(float)*100.0/sum(c)
        labels = [f'{e}\n{percents[i]:.2f}%' for i,e in enumerate(names)]
        figures.append(Figure( panels = [ Panel( title = s,
                                                 items = [ Bars(labels,c) ] ) ] ))
    for s in _possible_std_stats:
        if s not in stats:
            continue
        h=stats[s]
        hist,bins = h['hist'],h['hist_bins']
        xlabel = h['summary']
        if h.get('hist_outside') and stats['file']['integral']:
            frac = h['hist_outside'] / stats['file']['integral']
            xlabel += f'\n({100.0*frac:.3g}% of {"weights" if h["weighted"] else "particles"} outside plot range)'
        title = '{}{}{}'.format(s,
                                ' [{}]'.format(h['unit']) if h['unit'] is not None else '',
                                '' if h['weighted'] else ' (unweighted)')
        figures.append(Figure( panels = [ Panel( title = title, xlabel = xlabel,
                                                 xlim = ( bins[0], bins[-1] ),
                                                 items = [ StepHist(bins,hist) ] ) ] ))
    return figures

def plot_stats(stats,pdf=False,set_backend=None,backend=None,filename=None,
               terminal=False,**options):
    """Show the overview plot of provided statistics object (from
    collect_stats(), or a file for which collect_stats() is called), or save
    it in a file if filename is given, in the format given by its extension
    (e.g. "overview.png" or "overview.pdf"). The backend parameter selects
    the plotting backend (name or Backend object, default is chosen as
    described in mcpl.plotting, in the terminal if terminal is True), and
    further keyword arguments are options for it (e.g.
    matplotlib_backend='agg'). Returns the list of created files when saving.
    The plots of each field are available from stats_figures(). The pdf and
    set_backend parameters are deprecated (use filename and
    matplotlib_backend instead)."""
    if pdf is True:
        raise MCPLError('If set, the pdf parameter should be a string'
                        +' containing the desired filename of the PDF file to be created')
    if pdf:
        warnings.warn('The pdf parameter of plot_stats is deprecated, use'
                      ' filename instead', DeprecationWarning, stacklevel=2)
    filename = filename or pdf or None
    if filename and os.path.exists(filename):
        raise MCPLError(f'File {filename} already exists')
    if set_backend:
        warnings.warn('The set_backend parameter of plot_stats is deprecated,'
                      ' use matplotlib_backend instead', DeprecationWarning,
                      stacklevel=2)
        #It was only used for matplotlib (for which the option is called
        #matplotlib_backend):
        from ._plotbackend import _save_backend, _show_backend
        cls = ( _save_backend(filename,backend) if filename
                else _show_backend(backend,terminal) )
        opt = f'{getattr(cls,"name","")}_backend'
        import inspect
        if not isinstance(cls,PlotBackend) and opt in inspect.signature(cls).parameters:
            options.setdefault(opt,set_backend)
    figures = stats_figures(stats)[:1]
    if filename:
        return save(figures,filename,backend=backend,**options)
    show(figures,backend=backend,terminal=terminal,**options)
    return None
