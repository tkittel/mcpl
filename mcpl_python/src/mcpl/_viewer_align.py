
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

"""The align helper of the viewers: the mean position and direction of the
particles (weighted), and edits which turn the mean direction into a target
direction (keeping another axis as well as possible) and move the mean
position to a target point."""

__all__ = []

from ._common import MCPLError
from ._numpy import np

#The axes which can be chosen by name (as +x), also for the axis to keep:
axis_choices = { '+x' : (1,0,0), '-x' : (-1,0,0), '+y' : (0,1,0), '-y' : (0,-1,0),
                 '+z' : (0,0,1), '-z' : (0,0,-1) }

#The number of particles of the first estimate of the means:
estimate_particles = 200000

class AlignStats:
    """The sums of the weights of particles, and of their weighted positions
    and directions, and the weights of their types"""
    def __init__( self ):
        self.n, self.w = 0, 0.0
        self.wpos, self.wdir = np.zeros(3), np.zeros(3)
        self.wtypes = {}#pdgcode -> sum of weights
        self.complete = False#(all particles were added)

    def add( self, b ):
        w = np.asarray(b.weight,dtype=float)
        self.n += len(b)
        self.w += float(w.sum())
        self.wpos += [ float(np.dot(w,getattr(b,c))) for c in ( 'x', 'y', 'z' ) ]
        self.wdir += [ float(np.dot(w,getattr(b,c))) for c in ( 'ux', 'uy', 'uz' ) ]
        codes, inverse = np.unique(np.asarray(b.pdgcode),return_inverse=True)
        for code, sw in zip(codes.tolist(),np.bincount(inverse,weights=w).tolist()):
            self.wtypes[code] = self.wtypes.get(code,0.0) + sw

    @property
    def mean_pos( self ):
        """The mean position (cm), or None without weights"""
        return self.wpos / self.w if self.w > 0 else None

    @property
    def mean_dir( self ):
        """The direction of the mean of the directions (a unit vector), or None
        if it is not defined (no weights, or directions which cancel)"""
        norm = np.linalg.norm(self.wdir)
        return self.wdir / norm if self.w > 0 and norm > 1e-12 * self.w else None

    @property
    def spread_deg( self ):
        """The spread of the directions around their mean direction: the angle
        whose 1-cos is the mean of 1-cos of the angles to the mean direction
        (the root-mean-square angle for small angles), in degrees"""
        if self.w <= 0:
            return None
        r = min( 1.0, float(np.linalg.norm(self.wdir)) / self.w )
        return float(np.degrees( 2 * np.arcsin(np.sqrt( ( 1 - r ) / 2 )) ))

    def types_text( self, maxtypes = 3 ):
        """The particle types with their fractions of the weights, as a text"""
        from ._particles import _particle_text
        if self.w <= 0:
            return ''
        types = sorted( self.wtypes.items(), key = lambda kv : -kv[1] )
        parts = [ f'{_particle_text(code)} {100*w/self.w:.3g}%' for code, w in types[:maxtypes] ]
        if len(types) > maxtypes:
            parts.append(f'{len(types)-maxtypes} more')
        return ', '.join(parts)

def read_stats( blocks, publish, cancelled ):
    """Add the blocks to AlignStats, publishing the stats (with publish) after
    estimate_particles and at the end (with complete set). Stops when cancelled
    returns True."""
    stats = AlignStats()
    estimated = False
    for b in blocks:
        if cancelled():
            return
        stats.add(b)
        if not estimated and stats.n >= estimate_particles:
            estimated = True
            publish(_copy(stats))
    stats.complete = True
    publish(stats)

def _copy( stats ):
    res = AlignStats()
    res.n, res.w, res.wpos, res.wdir = stats.n, stats.w, stats.wpos.copy(), stats.wdir.copy()
    res.wtypes = dict(stats.wtypes)
    return res

def parse_vector( text, what, unit = '' ):
    """The vector of a text: an axis of axis_choices (as +z), or three numbers
    as in (1,1,0) or 1,1,0. With the unit cm (for points), the numbers can
    also have units of lengths, as in (0,0,1m) or (1,2,3)cm."""
    text = text.strip()
    if text in axis_choices:
        return np.array(axis_choices[text],dtype=float)
    inner, after = text, ''
    if unit and ')' in text:
        inner, after = text.rsplit(')',1)
    parts = inner.strip().strip('()').split(',')
    try:
        v = np.array([ _number_in(p,after.strip(),unit) for p in parts ])
    except ValueError:
        v = None
    if v is None or len(v) != 3 or not np.all(np.isfinite(v)):
        if unit:
            raise MCPLError(f'The {what} must be three lengths, as in (0,0,1m) (or numbers'
                            f' in cm, as in (0,0,100)), not "{text}"')
        raise MCPLError(f'The {what} must be three numbers, as in (0,0,1), or an axis'
                        f' like +z, not "{text}"')
    return v

def _number_in( text, unit, length ):
    """The number of the text (in cm if length is set, with an optional unit
    of lengths after it, or else the unit given)"""
    from ._exprsyntax import _expr_units
    text = text.strip()
    if length:
        for name in sorted(_expr_units,key = len,reverse = True):
            if text.endswith(name) and _expr_units[name][1] == _expr_units['cm'][1]:
                if unit:
                    raise ValueError('two units')
                return float(text[:-len(name)]) * _expr_units[name][0]
        if unit:
            if _expr_units.get(unit,(0,None))[1] != _expr_units['cm'][1]:
                raise ValueError('not a length')
            return float(text) * _expr_units[unit][0]
    elif unit:
        raise ValueError('a unit')
    return float(text)

def number( v ):
    """A number for an expression, exactly (as the shortest text of the double
    value), with values within 1e-15 of whole numbers as those numbers"""
    v = float(v)
    r = round(v)
    if abs( v - r ) <= 1e-15 and abs(r) < 1e15:
        return str(int(r))
    return repr(v)

def _vector( v, unit = '' ):
    return '(' + ','.join( number(c) + ( unit if number(c) != '0' else '' ) for c in v ) + ')'

def align_edit( stats, target = None, keep = None, pivot = 'mean', centre = None,
                coords = 'xyz' ):
    """The statements of an edit (a text) which turns the mean direction of
    the stats into the target direction (if given), rotating around the pivot
    ('mean' for the mean position, 'origin', or a point in cm), and keeping
    the axis to keep (if given) as well as possible: in the plane it spans with
    the target, on the same side. Then the mean position is moved to the
    point centre (in cm, if given) in the coordinates in coords. Returns the
    text and the mean position and direction after the edit."""
    from ._exprrotation import _rotation_matrix
    pos, mdir = stats.mean_pos, stats.mean_dir
    if pos is None:
        raise MCPLError('There are no particles (with weights) to align')
    statements, shift = [], np.zeros(3)
    if target is not None:
        if mdir is None:
            raise MCPLError('The directions of the particles have no mean direction'
                            ' (they cancel out)')
        t = np.asarray(target,dtype=float)
        if not np.linalg.norm(t) > 0:
            raise MCPLError('The target direction must not be zero')
        t = t / np.linalg.norm(t)
        if keep is None:
            #(the smallest rotation, around the axis perpendicular to both):
            axis = np.cross(mdir,t)
            if np.linalg.norm(axis) < 1e-12:
                #(already along the target, or opposite: half a turn around
                #an axis perpendicular to it):
                if np.dot(mdir,t) > 0:
                    axis = None
                else:
                    other = np.eye(3)[np.argmin(np.abs(t))]
                    axis = np.cross(t,other)
            u = None if axis is None else np.cross(axis,mdir)
            uout = None if axis is None else np.cross(axis,t)
        else:
            k = np.asarray(keep,dtype=float)
            if not np.linalg.norm(k) > 0:
                raise MCPLError('The axis to keep must not be zero')
            #(the parts of the axis perpendicular to the mean direction and
            #to the target, which the rotation turns into each other):
            u, uout = k - np.dot(k,mdir) * mdir, k - np.dot(k,t) * t
            limit = 1e-6 * np.linalg.norm(k)
            if np.linalg.norm(u) <= limit or np.linalg.norm(uout) <= limit:
                raise MCPLError('The axis to keep must not be along the mean direction'
                                ' or the target direction')
        if u is not None:
            u, uout = u / np.linalg.norm(u), uout / np.linalg.norm(uout)
            args = ( mdir, t, u, uout )
            text = 'rotate_frame(' + ','.join( _vector(a) for a in args ) + ')'
            #(the rotation of the numbers as written, so the result shown is
            #that of the edit):
            R = _rotation_matrix('rotate_frame',[ float(number(c)) for a in args for c in a ])
            if isinstance(R,str):
                raise MCPLError(f'The rotation can not be made ({R})')
            R = R[0]
            p = pos if isinstance(pivot,str) and pivot == 'mean' else (
                np.zeros(3) if isinstance(pivot,str) else np.asarray(pivot,dtype=float) )
            p = np.array([ float(number(c)) for c in p ])
            if np.any( p != 0 ):
                statements.append(f'pos -= {_vector(p,"cm")}')
                shift = p
            statements.append(text)
            pos = R @ ( pos - p ) + p
            mdir = R @ mdir
    if centre is not None:
        c = np.asarray(centre,dtype=float)
        move = np.array([ c[i] - pos[i] if 'xyz'[i] in coords else 0.0 for i in range(3) ])
        move = np.array([ float(number(m)) for m in move ])
        pos = pos + move
        shift = shift + move
    if np.any( shift != 0 ):
        statements.append(f'pos += {_vector(shift,"cm")}')
    if not statements:
        raise MCPLError('Nothing to do: choose a target direction or a point to move to')
    return ';'.join(statements), pos, mdir
