
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

"""The collections of plots of the viewer: each has a name, a short
description and the plots the viewer starts with, of which the first ones are
shown together in the overview. The collection is chosen with -wNAME (or in
the viewer), and the state of the viewer is saved as the changes of the plots
of its collection.

The plots are plot items, as in the state of the viewer: a histogram string
(as for -H), or a dict with it as "plot", and optionally a "title" (shown
instead of the histogram string, in the viewers with windows) and a "group"
(where the plot is listed there).

The names are not valid expressions (which is tested), so -wNAME can be
either a collection or a view."""

__all__ = []

_item_keys = ( 'plot', 'title', 'group' )

def _plot_item( item ):
    """The (plot, title, group) of a plot item (title and group are None if
    not given), or TypeError or ValueError if it is not a valid plot item"""
    if isinstance(item,str):
        return item, None, None
    if not isinstance(item,dict):
        raise TypeError('a plot must be a histogram string, or a JSON object with it'
                         ' as "plot", and optionally a "title" and a "group"')
    for k, v in item.items():
        if k not in _item_keys:
            raise ValueError(f'unknown entry "{k}" of a plot (the entries are:'
                             f' {", ".join(_item_keys)})')
        if not isinstance(v,str) or not v.strip() or not v.isprintable():
            raise ValueError(f'the {k} of a plot must be a text on one line')
    if 'plot' not in item:
        raise ValueError('a plot without its histogram string ("plot")')
    return item['plot'].strip(), *( item[k].strip() if k in item else None
                                    for k in ( 'title', 'group' ) )

def _item( plot, title = None, group = None ):
    """The plot item of the plot (see _plot_item): its histogram string if it
    has no title and group"""
    if title is None and group is None:
        return plot
    return { k : v for k, v in ( ( 'title', title ), ( 'plot', plot ), ( 'group', group ) )
             if v is not None }

#The angles of the directions to the axis of a beam along z, x or y (with
#the two components across the beam):
def _beam( axis, a, b ):
    div_a, div_b = f'atan2(u{a},u{axis})/deg', f'atan2(u{b},u{axis})/deg'
    vector = ','.join( '1' if c == axis else '0' for c in 'xyz' )
    beam = 'Profiles and divergences'
    return ( _item(f'{a} : {b}','Beam profile',beam),
             _item(f'{div_a} : {div_b}','Divergences',beam),
             _item(f'{a} : {div_a}',f'Phase space {a}',beam),
             _item(f'{b} : {div_b}',f'Phase space {b}',beam),
             _item('ekin;logx=auto;logy;split=pdgcode','Energy spectrum','Spectra'),
             _item('wavelength;logx=auto;logy=auto;split=pdgcode','Wavelength','Spectra'),
             _item(f'hypot({a},{b})','Distance from the axis','Other'),
             _item(f'angle_to({vector})/deg;logy',f'Angle to the {axis} axis','Other'),
             _item('time;logx=auto;logy','Time','Other'),
             _item('pdgcode;bar;logy=auto','Particle type','Other'),
             _item(f'{axis}',f'Position {axis}','Other'),
             _item('weight;unweighted;logy',None,'Other') )

#The titles of plots of single fields (also divided by units, as in ekin/MeV),
#when they have no title of their own (see _viewer._auto_title):
_field_titles = { 'ekin' : 'Energy', 'x' : 'Position x', 'y' : 'Position y',
                  'z' : 'Position z', 'ux' : 'Direction x', 'uy' : 'Direction y',
                  'uz' : 'Direction z', 'polx' : 'Polarisation x', 'poly' : 'Polarisation y',
                  'polz' : 'Polarisation z', 'time' : 'Time', 'weight' : 'Weight',
                  'pdgcode' : 'Particle type', 'userflags' : 'User flags',
                  'wavelength' : 'Wavelength', 'fileidx' : 'Position in the file' }

_collections = {
    'default' : ( 'an overview of all particle fields', (
        _item('ekin;logx=auto;logy;split=pdgcode','Energy spectrum','Main plots'),
        _item('wavelength;logx;split=pdgcode','Wavelength','Main plots'),
        _item('angle_to(0,0,1)/deg;logy;split=pdgcode','Angle to the z axis','Main plots'),
        _item('x : y','Position x-y','Main plots'),
        _item('time;logx=auto;logy','Time','Main plots'),
        _item('pdgcode;bar;logy=auto','Particle type','Main plots'),
        #(the fields in the order of mcpltool, with the titles from their
        #expressions, see _viewer._auto_title):
        *( _item(f,t,'Fields') for f, t in (
            ( 'ekin', None ), ( 'x', None ), ( 'y', None ), ( 'z', None ), ( 'ux', None ),
            ( 'uy', None ), ( 'uz', None ), ( 'time', None ), ( 'weight;unweighted', None ),
            ( 'polx', None ), ( 'poly', None ), ( 'polz', None ),
            ( 'userflags;bar;logy=auto', None ) ) ) ) ),
    'beamz' : ( 'a beam along the z axis: profiles and divergences', _beam('z','x','y') ),
    'beamx' : ( 'a beam along the x axis: profiles and divergences', _beam('x','y','z') ),
    'beamy' : ( 'a beam along the y axis: profiles and divergences', _beam('y','z','x') ),
    'shielding' : ( 'spectra, directions and weights of all particle types', (
        _item('pdgcode;bar;logy=auto','Particle type','Main plots'),
        _item('ekin;logx=auto;logy;split=pdgcode','Energy spectrum','Main plots'),
        _item('ekin;lethargy;logy;split=pdgcode','Lethargy spectrum','Main plots'),
        _item('angle_to(0,0,1)/deg;logy;split=pdgcode','Angle to the z axis','Main plots'),
        _item('time;logx=auto;logy;split=pdgcode','Time','Main plots'),
        _item('weight;logx=auto;logy;unweighted;split=pdgcode',None,'Main plots'),
        _item('x : y','Position x-y','More plots'),
        _item('hypot(x,y);logy;split=pdgcode','Distance from the z axis','More plots'),
        _item('wavelength;logx;split=pdgcode','Wavelength','More plots') ) ),
}

_default_collection = 'default'
