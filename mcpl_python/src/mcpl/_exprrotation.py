
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

"""Rotation matrices of the rotations of edits (see _expressions)"""

__all__ = []

from ._numpy import np

#(the tolerance of rotate_frame, as in NCrystal's RotMatrix):
_rotate_frame_tolerance = 1e-6

def _exact_cos_sin( angle ):
    """The cos and sin of the angles (in radians), exact (0 and +-1) for
    multiples of 90 degrees (whose cos and sin in radians are not exactly 0
    and +-1)"""
    q = np.asarray(angle,dtype=float) / ( 0.5 * np.pi )
    k = np.round(q)
    quarter = np.abs( q - k ) <= 8 * np.finfo(float).eps * np.maximum( 1.0, np.abs(k) )
    kq = np.mod(k,4).astype(int)
    c = np.where(quarter,np.choose(kq,(1.0,0.0,-1.0,0.0)),np.cos(angle))
    s = np.where(quarter,np.choose(kq,(0.0,1.0,0.0,-1.0)),np.sin(angle))
    return c, s

def _rotation_matrix( fname, args ):
    """The rotation matrices (shape (n,3,3), or (1,3,3) for constants) of
    rotate_around(ax,ay,az,angle) or of rotate_frame(v,vout,u,uout) (12
    numbers), from the values of the arguments (arrays or numbers), or a text
    saying what is wrong with them. Matrix elements within 1e-15 of 0 or +-1
    are exactly 0 or +-1, so rotations around the axes by multiples of 90
    degrees are exact."""
    a = [ np.atleast_1d(np.asarray(x,dtype=float)) for x in args ]
    n = np.broadcast_shapes(*( x.shape for x in a ))[0]
    vec = lambda i : np.stack([ np.broadcast_to(x,(n,)) for x in a[i:i+3] ],axis=-1)
    def unit( v ):
        norm = np.linalg.norm(v,axis=-1,keepdims=True)
        return None if np.any( norm == 0.0 ) or not np.all(np.isfinite(norm)) else v / norm
    if fname == 'rotate_around':
        k = unit(vec(0))
        if k is None:
            return 'the axis must not be zero'
        c, s = _exact_cos_sin(np.broadcast_to(a[3],(n,)))
        c, s = c[:,None,None], s[:,None,None]
        kx, ky, kz = k[:,0], k[:,1], k[:,2]
        zero = np.zeros(n)
        cross = np.stack([ np.stack([zero,-kz,ky],-1), np.stack([kz,zero,-kx],-1),
                           np.stack([-ky,kx,zero],-1) ],-2)
        R = c * np.eye(3) + s * cross + ( 1.0 - c ) * k[:,:,None] * k[:,None,:]
    else:
        tol = _rotate_frame_tolerance
        v, vo, u, uo = ( unit(vec(i)) for i in ( 0, 3, 6, 9 ) )
        if v is None or u is None or vo is None or uo is None:
            return 'the vectors must not be zero'
        if np.any( np.linalg.norm(np.cross(v,u),axis=-1) <= tol ):
            return 'v and u must not be parallel'
        if np.any( np.abs( np.sum(v*u,axis=-1) - np.sum(vo*uo,axis=-1) ) > tol ):
            return 'the angle between v and u must be that between vout and uout'
        def frame( e1, w ):
            e2 = w - np.sum(w*e1,axis=-1,keepdims=True) * e1
            e2 /= np.linalg.norm(e2,axis=-1,keepdims=True)
            return np.stack([ e1, e2, np.cross(e1,e2) ],axis=-1)#(columns)
        E, F = frame(v,u), frame(vo,uo)
        R = F @ np.swapaxes(E,-1,-2)
    for exact in ( 0.0, 1.0, -1.0 ):
        R = np.where( np.abs( R - exact ) <= 1e-15, exact, R )
    return R
