
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

"""Figures for tests of the plotting backends, with the kinds of plots of the
viewer: curves (also several in one plot), a 2D map and bars."""

_plots = ( 'ekin;logx=auto;logy;display_by=pdgcode', 'angle(dir,(0,0,1))/deg;logy;display_by=pdgcode',
           'x : y', 'time;logx=auto;logy;display_by=single', 'pdgcode;bar;logy=auto',
           'x;display_by=single' )

def example_figures( mcpl, filename ):
    """An overview of 6 plots of the file (2 rows of 3, with the title of the
    file), followed by each of them on its own (mcpl is the mcpl module)"""
    import pathlib
    hists = [ mcpl.histogram(filename,p) for p in _plots ]
    overview = mcpl.plotting.Figure( title = f'Overview of {pathlib.Path(filename).name}', nrows = 2,
                                     ncols = 3, panels = [ h.panel() for h in hists ] )
    return [ overview ] + [ h.figure() for h in hists ]
