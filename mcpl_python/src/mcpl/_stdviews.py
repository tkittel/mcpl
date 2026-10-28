
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

"""The standard groups of plots of the viewer.

Each group has a key, a title, its plots (fixed: changing
one copies it into the custom group of the viewer, see _viewer_groups), and
its overview: a grid of all its plots, or for groups of variables, a
correlation plot (the histograms of the expressions on the diagonal, and the
2D histograms of each pair below it, see
_viewer_overviews.correlation_cells). Each group adds plots of its own (a
plot in several groups is the same view), and the groups shown are chosen
with -wGROUPS (keys separated by commas, or in the viewer); the state of the
viewer is saved as the groups which are shown, their settings and the custom
plots.

The plots are plot items, as in the state of the viewer: a histogram string
(as for -H), or a dict with it as "plot" and a "title" (shown instead of the
histogram string, in the viewers with windows). Plots whose title follows
from their expression (e.g. Energy for ekin, see _viewer._auto_title) have
no title of their own.

The keys are not valid expressions (which is tested), so -wGROUPS can be
either groups or a view."""

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
             _item(f'hypot({a},{b})','Distance to axis'),
             _item(f'angle(dir,({vector}))/deg;logy',f'Angle to {axis} axis'),
             f'{axis}' )

#The titles of plots of single fields (also divided by units, as in ekin/MeV),
#when they have no title of their own (see _viewer._auto_title):
_field_titles = { 'ekin' : 'Energy', 'x' : 'Position x', 'y' : 'Position y',
                  'z' : 'Position z', 'ux' : 'Direction x', 'uy' : 'Direction y',
                  'uz' : 'Direction z', 'polx' : 'Polarisation x', 'poly' : 'Polarisation y',
                  'polz' : 'Polarisation z', 'time' : 'Time', 'weight' : 'Weight',
                  'pdgcode' : 'Particle type', 'userflags' : 'User flags',
                  'wavelength' : 'Wavelength', 'fileidx' : 'Position in the file' }

#The key and title of the group of the plots added by users:
custom_key, custom_title = 'custom', 'Custom'

#The standard groups, as key -> (title, plot items, options), with the option
#variables (the expressions which a correlation plot can have, see
#_viewer_groups):
_groups = {
    'spectra' : ( 'Spectra', (
        'ekin;logx=auto;logy',
        #(as usual in shielding studies):
        'ekin;lethargy;logy',
        'wavelength;logx',
        'time;logx=auto;logy',
        'pdgcode;bar;logy=auto' ), {} ),
    #(the fields in the order of mcpltool, and those of the userdata, see
    #_viewer_groups):
    'fields' : ( 'Fields', (
        'ekin;logx=auto;logy', 'x', 'y', 'z', 'ux', 'uy', 'uz', 'time;logx=auto;logy',
        'weight;logx=auto;logy;unweighted',
        'polx', 'poly', 'polz', 'userflags;bar;logy=auto' ), {} ),
    #(the positions and directions projected on the planes, in rows):
    'geometry' : ( 'Geometry', (
        'x : y', 'y : z', 'z : x', 'ux : uy', 'uy : uz', 'uz : ux' ), {} ),
    'beamz' : ( 'Z beam profile',
                _beam('z','x','y'), {} ),
    'beamx' : ( 'X beam profile',
                _beam('x','y','z'), {} ),
    'beamy' : ( 'Y beam profile',
                _beam('y','z','x'), {} ),
    '3d' : ( '3D', (
        _item('x : y : z','Positions in 3D'),
        _item('ux : uy : uz','Directions in 3D') ), {} ),
    'correlations' : ( 'Correlations', (),
                       { 'variables' : ( 'x', 'y', 'z', 'ux', 'uy', 'uz', 'ekin', 'time',
                                         'weight' ) } ),
}

#The groups shown by default:
_default_groups = ( 'spectra', 'fields' )
