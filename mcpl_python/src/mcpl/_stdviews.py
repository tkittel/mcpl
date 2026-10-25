
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

"""The standard groups of plots of the viewer, and the presets of them.

Each group has a key, a title, a description, its plots (fixed: changing
one copies it into the custom group of the viewer, see _viewer_groups), and
its overview: a grid of all its plots, or for groups of variables, a corner plot
(the histograms of the expressions on the diagonal, and the 2D histograms of
each pair below it, see _viewer_overviews.corner_cells). The presets are sets
of groups, chosen with -wNAME (or in the viewer); the state of the viewer is
saved as the groups which are shown and the custom plots.

The plots are plot items, as in the state of the viewer: a histogram string
(as for -H), or a dict with it as "plot" and a "title" (shown instead of the
histogram string, in the viewers with windows). Plots whose title follows
from their expression (e.g. Energy for ekin, see _viewer._auto_title) have
no title of their own.

The names are not valid expressions (which is tested), so -wNAME can be
either a preset or a view."""

__all__ = []

_item_keys = ( 'plot', 'title' )

def _plot_item( item ):
    """The (plot, title) of a plot item (title is None if not given), or
    TypeError or ValueError if it is not a valid plot item"""
    if isinstance(item,str):
        return item, None
    if not isinstance(item,dict):
        raise TypeError('a plot must be a histogram string, or a JSON object with it'
                         ' as "plot", and optionally a "title"')
    for k, v in item.items():
        if k not in _item_keys:
            raise ValueError(f'unknown entry "{k}" of a plot (the entries are:'
                             f' {", ".join(_item_keys)})')
        if not isinstance(v,str) or not v.strip() or not v.isprintable():
            raise ValueError(f'the {k} of a plot must be a text on one line')
    if 'plot' not in item:
        raise ValueError('a plot without its histogram string ("plot")')
    return item['plot'].strip(), item['title'].strip() if 'title' in item else None

def _item( plot, title = None ):
    """The plot item of the plot (see _plot_item): its histogram string if it
    has no title"""
    return plot if title is None else { 'title' : title, 'plot' : plot }

#The plots of a beam along z, x or y (with the angles of the directions to
#the axis, of the two components across the beam):
def _beam( axis, a, b ):
    div_a, div_b = f'atan2(u{a},u{axis})/deg', f'atan2(u{b},u{axis})/deg'
    vector = ','.join( '1' if c == axis else '0' for c in 'xyz' )
    return ( _item(f'{a} : {b}','Beam profile'),
             _item(f'{div_a} : {div_b}','Divergences'),
             _item(f'{a} : {div_a}',f'Phase space {a}'),
             _item(f'{b} : {div_b}',f'Phase space {b}'),
             'ekin;logx=auto;logy;split=pdgcode',
             'wavelength;logx=auto;logy=auto;split=pdgcode',
             _item(f'hypot({a},{b})','Distance to axis'),
             _item(f'angle(dir,({vector}))/deg;logy',f'Angle to {axis} axis'),
             'time;logx=auto;logy',
             'pdgcode;bar;logy=auto',
             f'{axis}',
             'weight;unweighted;logy' )

#The titles of plots of single fields (also divided by units, as in ekin/MeV),
#when they have no title of their own (see _viewer._auto_title):
_field_titles = { 'ekin' : 'Energy', 'x' : 'Position x', 'y' : 'Position y',
                  'z' : 'Position z', 'ux' : 'Direction x', 'uy' : 'Direction y',
                  'uz' : 'Direction z', 'polx' : 'Polarisation x', 'poly' : 'Polarisation y',
                  'polz' : 'Polarisation z', 'time' : 'Time', 'weight' : 'Weight',
                  'pdgcode' : 'Particle type', 'userflags' : 'User flags',
                  'wavelength' : 'Wavelength', 'fileidx' : 'Position in the file' }

#The standard groups, as key -> (title, description, plot items, options),
#with the option variables (the expressions which a corner plot can have, see
#_viewer_groups; the plots are shown in the first group which has them, so
#the correlations, which have many plots of other groups, come last):
_groups = {
    'overview' : ( 'Overview', 'the main plots of the particles', (
        'ekin;logx=auto;logy;split=pdgcode',
        'wavelength;logx;split=pdgcode',
        _item('angle(dir,(0,0,1))/deg;logy;split=pdgcode','Angle to z axis'),
        _item('x : y','Position x-y'),
        'time;logx=auto;logy',
        'pdgcode;bar;logy=auto' ), {} ),
    #(the fields in the order of mcpltool, and those of the userdata, see
    #_viewer_groups):
    'fields' : ( 'Fields', 'a plot of each particle field', (
        'ekin', 'x', 'y', 'z', 'ux', 'uy', 'uz', 'time', 'weight;unweighted',
        'polx', 'poly', 'polz', 'userflags;bar;logy=auto' ), {} ),
    'beamz' : ( 'Beam along z', 'profiles and divergences of a beam along z',
                _beam('z','x','y'), {} ),
    'beamx' : ( 'Beam along x', 'profiles and divergences of a beam along x',
                _beam('x','y','z'), {} ),
    'beamy' : ( 'Beam along y', 'profiles and divergences of a beam along y',
                _beam('y','z','x'), {} ),
    'shielding' : ( 'Shielding', 'spectra, directions and weights of all particle types', (
        'pdgcode;bar;logy=auto',
        #(the energy spectra per unit lethargy, as usual in shielding):
        'ekin;lethargy;logy;split=pdgcode',
        _item('angle(dir,(0,0,1))/deg;logy;split=pdgcode','Angle to z axis'),
        'time;logx=auto;logy;split=pdgcode',
        'weight;logx=auto;logy;unweighted;split=pdgcode',
        _item('x : y','Position x-y'),
        _item('hypot(x,y);logy;split=pdgcode','Distance to z axis'),
        'wavelength;logx;split=pdgcode' ), {} ),
    '3d' : ( '3D', 'the positions and directions in 3D, of a sample of the particles', (
        _item('x : y : z;split=pdgcode','Positions in 3D'),
        _item('ux : uy : uz;split=pdgcode','Directions in 3D') ), {} ),
    'correlations' : ( 'Correlations', ( 'the correlations of the positions, directions,'
                                         ' energy and weight, as a corner plot' ), (),
                       { 'variables' : ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'ekin', 'time',
                                         'weight' ) } ),
}

#The presets of groups, as name -> (description, groups):
_presets = {
    'default' : ( 'the overview, the fields and their correlations',
                  ( 'overview', 'fields', 'correlations' ) ),
    'beamz' : ( 'a beam along the z axis: profiles, divergences and correlations',
                ( 'beamz', 'correlations' ) ),
    'beamx' : ( 'a beam along the x axis: profiles, divergences and correlations',
                ( 'beamx', 'correlations' ) ),
    'beamy' : ( 'a beam along the y axis: profiles, divergences and correlations',
                ( 'beamy', 'correlations' ) ),
    'shielding' : ( 'spectra, directions and weights of all particle types',
                    ( 'shielding', ) ),
    'all' : ( 'all groups', tuple(_groups) ),
}

_default_preset = 'default'
