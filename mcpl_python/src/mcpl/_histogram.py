
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


"""The histograms of the public API (mcpl.histogram): read-only views of the
histograms of _histfill, which can be plotted."""

#(the classes of the results are made by histogram, not directly):
__all__ = [ 'Hist1D', 'Hist2D', 'HistDiscrete', 'PointSet3D', 'histogram' ]

from ._common import MCPLError
from ._histfill import (
    _fill,
    _Hist1DData,
    _Hist2DData,
    _HistDiscreteData,
    _PointSet3DData,
)
from ._numpy import np


def _readonly( a ):
    """Read-only array with the values of a"""
    v = np.array(a,dtype=float)
    v.flags.writeable = False
    return v

class _Result:
    """Common basis of the results of histogram(): a read-only view of the
    histogram (of _histfill), which can be plotted"""
    __slots__ = ( '_d', )
    def __init__( self ):
        raise TypeError(f'{type(self).__name__} objects are made by mcpl.histogram')

    def plot( self, filename = None ):
        """Show the plot in a window (with matplotlib), or save it in a file if
        filename is given, in the format given by its extension: .pdf, .png,
        or .svg (with matplotlib), or .txt (drawn as text). Existing files are
        not overwritten. Returns the list of created files when saving."""
        from ._histfigures import figure
        from ._plotting import save, show
        if filename:
            return save([ figure(self._d) ],filename)
        show([ figure(self._d) ])
        return None

class Hist1D(_Result):
    """1D histogram of the values of an expression, the result of histogram()
    for a histogram string with one expression, e.g. "ekin/eV;logx". The
    contents are the sums of the weights of the particles in the bins (or
    their numbers, with the option unweighted), of all particles, also when
    the plot shows separate curves (see the option display_by)."""
    __slots__ = ()
    @property
    def expression( self ):
        """The expression"""
        return self._d.expression
    @property
    def edges( self ):
        """The bin edges (an array of n+1 values)"""
        return _readonly(self._d.edges*self._d._scale)
    @property
    def contents( self ):
        """The contents of the bins (an array of n values)"""
        c = list(self._d.contents.values())
        return _readonly(sum(c) if c else np.zeros(len(self._d.edges)-1))

class Hist2D(_Result):
    """2D histogram of the values of two expressions, the result of
    histogram() for a histogram string with two expressions, e.g. "x/cm :
    y/cm". The contents are the sums of the weights of the particles in the
    bins (or their numbers, with the option unweighted)."""
    __slots__ = ()
    @property
    def expressions( self ):
        """The two expressions (x and y)"""
        return ( self._d.xexpression, self._d.yexpression )
    @property
    def xedges( self ):
        """The bin edges of x (an array of nx+1 values)"""
        return _readonly(self._d.xedges*self._d._scales[0])
    @property
    def yedges( self ):
        """The bin edges of y (an array of ny+1 values)"""
        return _readonly(self._d.yedges*self._d._scales[1])
    @property
    def contents( self ):
        """The contents of the bins (an array of shape (nx, ny))"""
        return _readonly(self._d.contents)

class HistDiscrete(_Result):
    """Histogram of an expression with whole numbers, the result of histogram()
    for a histogram string with the option bar, e.g. "pdgcode;bar". The
    contents are the sums of the weights of the particles with each value (or
    their numbers, with the option unweighted), of all values, also when the
    plot combines the smallest ones."""
    __slots__ = ()
    def _sorted( self ):
        sums = self._d._value_sums
        return sorted( sums, key = lambda k : ( -sums[k], k ) )
    @property
    def expression( self ):
        """The expression"""
        return self._d.expression
    @property
    def values( self ):
        """The values (whole numbers), the largest contents first"""
        v = np.array(self._sorted(),dtype=np.int64)
        v.flags.writeable = False
        return v
    @property
    def contents( self ):
        """The contents of the values (an array, in the order of values)"""
        return _readonly([ self._d._value_sums[k] for k in self._sorted() ])

class PointSet3D(_Result):
    """Values of three expressions for particles chosen at random with their
    weights, the result of histogram() for a histogram string with three
    expressions, e.g. "x/cm : y/cm : z/cm". At most as many particles as the
    option points gives (5000 unless given) are chosen, in proportion to their
    weights (or all equally likely, with the option unweighted): the particles
    with the largest values of u^(1/w), where w is the weight and u a number
    from a fixed hash of the position of the particle in the file. So the
    same particles are always chosen for the same file, and particles which
    remain after a stricter condition stay. With fewer particles, all are used.
    Their plots say which particles they show."""
    __slots__ = ()
    @property
    def expressions( self ):
        """The three expressions"""
        return tuple(self._d.expressions)
    @property
    def points( self ):
        """The values of the expressions for the chosen particles (an array of
        shape (n, 3))"""
        return _readonly(np.asarray(self._d._points).reshape(-1,3))
    @property
    def nparticles( self ):
        """The number of particles the points were chosen from"""
        return self._d.nparticles

_public_classes = { _Hist1DData : Hist1D, _HistDiscreteData : HistDiscrete,
                    _Hist2DData : Hist2D, _PointSet3DData : PointSet3D }

def histogram( file, expression ):
    """Histogram of the values of one or more expressions (see ParticleValue)
    for the particles in an MCPL file (a file name, or an MCPLFile, whose
    skip, limit, and edit apply), for instance:

       h = mcpl.histogram( "myfile.mcpl", "ekin/eV;logx;lethargy" )
       h.plot()
       print( h.edges, h.contents )

    The expression is a histogram string, as for mcpltool -w (see mcpltool
    --hist-help), with one expression for a Hist1D (or a HistDiscrete
    with the option bar), two for a Hist2D (as in "x/cm : y/cm"), or
    three for a PointSet3D (as in "x/cm : y/cm : z/cm"). The values are in
    the units the expressions give, e.g. eV for "ekin/eV", and in the units
    of MCPL (cm, MeV, ms, ...) for expressions with units which are not
    divided by one (as "ekin"), whose plots choose suitable units.
    """
    from ._histstring import _parse_hist
    if isinstance(file,(list,tuple)):
        raise MCPLError('mcpl.histogram takes one file')
    if not isinstance(expression,str):
        raise MCPLError('The expression of mcpl.histogram must be a histogram string')
    o = _parse_hist(expression)
    if o['print']:
        raise MCPLError('The histogram option print is only for the mcpltool command')
    data = _fill([ file ],o)
    res = object.__new__(_public_classes[type(data)])
    res._d = data
    return res
