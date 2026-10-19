
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
description and the plots (histogram strings, as for -H) the viewer starts
with, of which the first ones are shown together in the overview. The
collection is chosen with -wNAME (or in the viewer), and the state of the
viewer is saved as the changes of the plots of its collection.

The names are not valid expressions (which is tested), so -wNAME can be
either a collection or a view."""

__all__ = []

#The angles of the directions to the axis of a beam along z, x or y (with
#the two components across the beam):
def _beam( axis, a, b ):
    div_a, div_b = f'atan2(u{a},u{axis})/deg', f'atan2(u{b},u{axis})/deg'
    return ( f'{a} : {b}',
             f'{div_a} : {div_b}',
             f'{a} : {div_a}',
             f'{b} : {div_b}',
             'ekin;logx=auto;logy;split=pdgcode',
             'wavelength;split=pdgcode',
             f'hypot({a},{b})',
             f'acos(abs(u{axis}))/deg;logy',
             'time;logx=auto;logy',
             'pdgcode;bar;logy=auto',
             f'{axis}',
             'weight;unweighted;logy' )

_collections = {
    'default' : ( 'an overview of all particle fields',
                  ( 'ekin;logx=auto;logy;split=pdgcode',
                    'wavelength;logx;split=pdgcode',
                    'acos(uz)/deg;range=0:180;logy;split=pdgcode',
                    'x : y',
                    'time;logx=auto;logy',
                    'pdgcode;bar;logy=auto',
                    'userflags;bar;logy=auto',
                    'ekin', 'x', 'y', 'z', 'ux', 'uy', 'uz', 'time',
                    'weight;unweighted', 'polx', 'poly', 'polz' ) ),
    'beamz' : ( 'a beam along the z axis: profiles and divergences', _beam('z','x','y') ),
    'beamx' : ( 'a beam along the x axis: profiles and divergences', _beam('x','y','z') ),
    'beamy' : ( 'a beam along the y axis: profiles and divergences', _beam('y','z','x') ),
    'shielding' : ( 'spectra, directions and weights of all particle types',
                    ( 'pdgcode;bar;logy=auto',
                      'ekin;logx=auto;logy;split=pdgcode',
                      'ekin;lethargy;logy;split=pdgcode',
                      'acos(uz)/deg;range=0:180;logy;split=pdgcode',
                      'time;logx=auto;logy;split=pdgcode',
                      'weight;logx=auto;logy;unweighted;split=pdgcode',
                      'x : y',
                      'hypot(x,y);logy;split=pdgcode',
                      'wavelength;logx;split=pdgcode' ) ),
}

_default_collection = 'default'
