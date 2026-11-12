
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

"""The helper functions of the C and C++ code (see _expr_clike): the
operations which can fail, stopping the program with the errors of the
expressions, and the functions of the expressions which C and C++ do not
have."""

__all__ = []

from ._expr_codelayout import _BRK2
from ._expr_vocab import _expr_wl_unit, _int_bits


class _CHelpers:
    """The helper functions which the code uses, written for the language
    provider lang (see _CLikeCode, for the types, casts, calls of the math
    library, and errors). The methods give the names of the functions, and
    code has their code (by name, in the order they are first needed)."""

    def __init__( self, lang ):
        self.lang = lang
        self.code = {}

    def function( self, name, signature, body ):
        """Use the helper function with the signature (with the name in it,
        as {name}) and the lines of the body"""
        if name not in self.code:
            self.code[name] = f'static {signature.format(name=name)}\n{{\n{body}}}'
        return name

    def int_op( self, op, t ):
        """The checked operation op on integers of type t: add, sub, mul, div
        (as //), mod, neg, abs, or as (a signed integer as the unsigned type
        t, if not negative)"""
        name = f'{op}_{t}'
        T = self.lang.ctype(t)
        bits, signed = _int_bits[t], t[0] == 'i'
        mx, mn, umx = f'INT{bits}_MAX', f'INT{bits}_MIN', f'UINT{bits}_MAX'
        one, two = f'{{name}}( {T} a )', f'{{name}}( {T} a, {T} b )'
        if op == 'as':
            return self.function(f'as_{t}',f'{T} {{name}}( {self.lang.ctype("i64")} a )',
                                 self.lang.fail('a < 0','Negative integer value') + f'  return {self.lang.cast("a",t)};\n')
        if op == 'neg':
            if signed:
                body = self.lang.fail(f'a == {mn}','Integer overflow') + '  return -a;\n'
            else:
                body = self.lang.fail('a != 0','Negative integer value') + '  return 0;\n'
            return self.function(name,f'{T} {one}',body)
        if op == 'abs':
            return self.function(name,f'{T} {one}',self.lang.fail(f'a == {mn}','Integer overflow')
                                 + '  return a < 0 ? -a : a;\n')
        if op in ( 'div', 'mod' ):
            body = self.lang.fail('a < 0 || b < 0','Negative integer value') if signed else ''
            body += self.lang.fail('b == 0','Division by zero')
            return self.function(name,f'{T} {two}',body + f'  return a {"/" if op == "div" else "%"} b;\n')
        sym = { 'add' : '+', 'sub' : '-', 'mul' : '*' }[op]
        if bits == 32:
            #(computed in 64 bits, where the results fit):
            wide = 'i64' if signed or op == 'sub' else 'u64'
            check = ( f'r < {mn} || r > {mx}' if signed else 'r < 0' if op == 'sub' else f'r > {umx}' )
            body = ( f'  {self.lang.ctype(wide)} r = {self.lang.cast("a",wide)} {sym} b;\n'
                     + self.lang.fail(check,'Integer overflow') + f'  return {self.lang.cast("r",t)};\n' )
            return self.function(name,f'{T} {two}',body)
        if op == 'add':
            check = ( f'( b > 0 && a > {mx} - b ) || ( b < 0 && a < {mn} - b )' if signed
                      else f'a > {umx} - b' )
        elif op == 'sub':
            check = ( f'( b < 0 && a > {mx} + b ) || ( b > 0 && a < {mn} + b )' if signed
                      else 'a < b' )
        else:
            check = ( f'a > 0 ? ( b > 0 ? a > {mx} / b : b < {mn} / a )'
                      f' : ( b > 0 ? a < {mn} / b : ( a != 0 && b < {mx} / a ) )' if signed
                      else f'a != 0 && b > {umx} / a' )
        return self.function(name,f'{T} {two}',self.lang.fail(check,'Integer overflow') + f'  return a {sym} b;\n')

    def min_max( self, which, t ):
        """The function giving the smaller (which is 'min') or larger ('max')
        of two numbers of the type t"""
        T = self.lang.ctype(t)
        return self.function(f'{which}_{t}',f'{T} {{name}}( {T} a, {T} b )',
                             f'  return a {"<" if which == "min" else ">"} b ? a : b;\n')

    def toint( self ):
        return self.function('toint',f'{self.lang.ctype("i64")} {{name}}( double v )',
                             self.lang.fail(f'!( {self.lang.fct("fabs","v")} < 4611686018427387904.0 )',
                                       'Value too large for integers')
                             + f'  return {self.lang.cast("v","i64")};\n')

    def sphere( self ):
        """The function of through_sphere, of the vector r from the position to
        the center, the direction d, and the radius: whether the distance of
        the center from the line (the length of the cross product of r and d,
        as d is a unit vector) is at most the radius"""
        return self.function('through_sphere','int {name}( double rx, double ry, double rz,\n'
                             '                           double dx, double dy, double dz,\n'
                             '                           double radius )',
                             self.lang.fail('radius < 0.0','Negative radius')
                             + '  double cx = ry * dz - rz * dy, cy = rz * dx - rx * dz,'
                             ' cz = rx * dy - ry * dx;\n'
                             '  return cx * cx + cy * cy + cz * cz <= radius * radius;\n')

    def box( self ):
        """The function of through_box, of the vector r from the position to the
        center, the direction d, and the half dimensions h: whether the parts of
        the line between the two planes of the box along x, y, and z overlap"""
        fabs = self.lang.fct('fabs','r[i]')
        return self.function('through_box','int {name}( double rx, double ry, double rz,\n'
                             '                        double dx, double dy, double dz,\n'
                             '                        double hx, double hy, double hz )',
                             self.lang.fail('hx < 0.0 || hy < 0.0 || hz < 0.0','Negative half dimension')
                             + '  double r[3] = { rx, ry, rz }, d[3] = { dx, dy, dz }, h[3] = { hx, hy, hz };\n'
                             '  double lo = 0.0, hi = 0.0;\n'
                             '  int any = 0;\n'
                             '  for ( int i = 0; i < 3; ++i ) {\n'
                             '    if ( d[i] == 0.0 ) {\n'
                             f'      if ( {fabs} > h[i] )\n'
                             '        return 0;\n'
                             '      continue;\n'
                             '    }\n'
                             '    double t1 = ( r[i] - h[i] ) / d[i], t2 = ( r[i] + h[i] ) / d[i];\n'
                             '    if ( t1 > t2 ) { double t = t1; t1 = t2; t2 = t; }\n'
                             '    if ( !any || t1 > lo ) lo = t1;\n'
                             '    if ( !any || t2 < hi ) hi = t2;\n'
                             '    any = 1;\n'
                             '  }\n'
                             '  return !any || lo <= hi;\n')

    def angle( self ):
        sq = lambda e : self.lang.fct('sqrt',e)
        return self.function('angle','double {name}( double ax, double ay, double az,\n'
                             '                     double bx, double by, double bz )',
                             '  /* Precise also for small angles */\n'
                             f'  double na = {sq("ax*ax + ay*ay + az*az")}, nb = {sq("bx*bx + by*by + bz*bz")};\n'
                             '  double dx = ax/na - bx/nb, dy = ay/na - by/nb, dz = az/na - bz/nb;\n'
                             '  double sx = ax/na + bx/nb, sy = ay/na + by/nb, sz = az/na + bz/nb;\n'
                             f'  return 2.0 * {self.lang.fct("atan2",sq("dx*dx + dy*dy + dz*dz"),sq("sx*sx + sy*sy + sz*sz"))};\n')

    def wavelength( self ):
        from .constants import hc_eV_Aa, neutron_mass_energy
        return self.function('wavelength',f'double {{name}}( double ekin, {self.lang.ctype("i32")} pdgcode )',
                             '  /* Wavelength in cm, of neutrons and gammas */\n'
                             + self.lang.fail('pdgcode != 2112 && pdgcode != 22',
                                         'The wavelength is only defined for neutrons and gammas')
                             + self.lang.fail('!( ekin > 0.0 )','The wavelength is infinite for zero kinetic energy')
                             + '  double pc = pdgcode == 22 ? ekin : '
                             + self.lang.fct('sqrt',f'ekin * ( ekin + 2 * {neutron_mass_energy!r} )') + ';\n'
                             + f'  return {hc_eV_Aa!r} * 1e-6 / pc * {_expr_wl_unit!r};\n')

    def ekin( self ):
        from .constants import hc_eV_Aa, neutron_mass_energy
        mc2 = repr(neutron_mass_energy)
        return self.function('ekin_of_wavelength',
                             f'double {{name}}( double wl, {self.lang.ctype("i32")} pdgcode )',
                             '  /* Kinetic energy of a wavelength in cm, of neutrons and gammas */\n'
                             + self.lang.fail('pdgcode != 2112 && pdgcode != 22',
                                         'The wavelength can only be set for neutrons and gammas,'
                                         ' so keep only those first')
                             + self.lang.fail('!( wl > 0.0 )','The wavelength must be positive')
                             + f'  double pc = {hc_eV_Aa!r} * 1e-6 / ( wl / {_expr_wl_unit!r} );\n'
                             + '  if ( pdgcode == 22 )\n    return pc;\n'
                             + f'  return pc * pc / ( {self.lang.fct("sqrt",f"pc * pc + {mc2}*{mc2}")} + {mc2} );\n')

    def exact_cos_sin( self ):
        f = self.lang.fct
        return self.function('exact_cos_sin','void {name}( double a, double * c, double * s )',
                             '  /* Exact for multiples of 90 degrees */\n'
                             '  double q = a / ( 0.5 * 3.141592653589793 );\n'
                             f'  double k = {f("rint","q")};\n'
                             f'  if ( {f("fabs","q - k")} <= 8 * 2.220446049250313e-16 * ( {f("fabs","k")} > 1.0 ? {f("fabs","k")} : 1.0 ) ) {{\n'
                             f'    int kq = {self.lang.cast(f("fmod","k","4.0"),"i32")};\n'
                             '    if ( kq < 0 )\n      kq += 4;\n'
                             '    *c = kq == 0 ? 1.0 : ( kq == 2 ? -1.0 : 0.0 );\n'
                             '    *s = kq == 1 ? 1.0 : ( kq == 3 ? -1.0 : 0.0 );\n'
                             '  } else {\n'
                             f'    *c = {f("cos","a")};\n    *s = {f("sin","a")};\n  }}\n')

    def rotation_matrix( self, fname ):
        """The helpers of rotate_around or rotate_frame (see _rotation_matrix)"""
        f, sq = self.lang.fct, lambda e : self.lang.fct('sqrt',e)
        #(the difference of the cosines of the angles, v-u and vout-uout):
        angle_diff = ( f'( v[0]*u[0] + v[1]*u[1] + v[2]*u[2] ) - {_BRK2}'
                       '( vo[0]*uo[0] + vo[1]*uo[1] + vo[2]*uo[2] )' )
        self.function('unit_vector','int {name}( const double * v, double * u )',
                      f'  double n = {sq("v[0]*v[0] + v[1]*v[1] + v[2]*v[2]")};\n'
                      '  if ( !( n > 0.0 && n <= 1.7976931348623157e308 ) )\n    return 0;\n'
                      '  u[0] = v[0] / n;\n  u[1] = v[1] / n;\n  u[2] = v[2] / n;\n  return 1;\n')
        self.function('exact_matrix','void {name}( double * R )',
                      '  /* Elements within 1e-15 of 0 or +-1 are exact */\n'
                      '  for ( int i = 0; i < 9; ++i ) {\n'
                      f'    if ( {f("fabs","R[i]")} <= 1e-15 )\n      R[i] = 0.0;\n'
                      f'    if ( {f("fabs","R[i] - 1.0")} <= 1e-15 )\n      R[i] = 1.0;\n'
                      f'    if ( {f("fabs","R[i] + 1.0")} <= 1e-15 )\n      R[i] = -1.0;\n  }}\n')
        if fname == 'rotate_around':
            self.exact_cos_sin()
            return self.function('rotate_around','void {name}( const double * axis, double angle, double * R )',
                                 '  double k[3], c, s;\n'
                                 + self.lang.fail('!unit_vector( axis, k )','In rotate_around(..), the axis must not be zero')
                                 + '  exact_cos_sin( angle, &c, &s );\n'
                                 '  double cr[9] = { 0.0, -k[2], k[1], k[2], 0.0, -k[0], -k[1], k[0], 0.0 };\n'
                                 '  for ( int i = 0; i < 3; ++i )\n'
                                 '    for ( int j = 0; j < 3; ++j )\n'
                                 '      R[3*i+j] = c * ( i == j ? 1.0 : 0.0 ) + s * cr[3*i+j] + ( 1.0 - c ) * k[i] * k[j];\n'
                                 '  exact_matrix( R );\n')
        self.function('frame','void {name}( const double * e1, const double * w, double * E )',
                      '  /* The columns e1, e2, and e1 x e2 */\n'
                      '  double d = w[0]*e1[0] + w[1]*e1[1] + w[2]*e1[2];\n'
                      '  double e2[3] = { w[0] - d * e1[0], w[1] - d * e1[1], w[2] - d * e1[2] };\n'
                      f'  double n = {sq("e2[0]*e2[0] + e2[1]*e2[1] + e2[2]*e2[2]")};\n'
                      '  e2[0] /= n;\n  e2[1] /= n;\n  e2[2] /= n;\n'
                      '  double e3[3] = { e1[1]*e2[2] - e1[2]*e2[1], e1[2]*e2[0] - e1[0]*e2[2],\n'
                      '                   e1[0]*e2[1] - e1[1]*e2[0] };\n'
                      '  for ( int i = 0; i < 3; ++i ) {\n'
                      '    E[3*i] = e1[i];\n    E[3*i+1] = e2[i];\n    E[3*i+2] = e3[i];\n  }\n')
        self.function('cross_norm','double {name}( const double * a, const double * b )',
                      '  double c0 = a[1]*b[2] - a[2]*b[1], c1 = a[2]*b[0] - a[0]*b[2], c2 = a[0]*b[1] - a[1]*b[0];\n'
                      f'  return {sq("c0*c0 + c1*c1 + c2*c2")};\n')
        return self.function('rotate_frame','void {name}( const double * v0, const double * vo0,\n'
                             '                          const double * u0, const double * uo0, double * R )',
                             '  double v[3], vo[3], u[3], uo[3], E[9], F[9];\n'
                             + self.lang.fail('!unit_vector( v0, v ) || !unit_vector( vo0, vo ) || !unit_vector( u0, u )'
                                         ' || !unit_vector( uo0, uo )','In rotate_frame(..), the vectors must not be zero')
                             + self.lang.fail('cross_norm( v, u ) <= 1e-6','In rotate_frame(..), v and u must not be parallel')
                             + self.lang.fail('cross_norm( vo, uo ) <= 1e-6',
                                         'In rotate_frame(..), vout and uout must not be parallel')
                             + self.lang.fail(f'{f("fabs",angle_diff)} > 1e-6',
                                         'In rotate_frame(..), the angle between v and u must be that between vout and uout')
                             + '  frame( v, u, E );\n  frame( vo, uo, F );\n'
                             '  /* R = F E^T */\n'
                             '  for ( int i = 0; i < 3; ++i )\n'
                             '    for ( int j = 0; j < 3; ++j )\n'
                             '      R[3*i+j] = F[3*i]*E[3*j] + F[3*i+1]*E[3*j+1] + F[3*i+2]*E[3*j+2];\n'
                             '  exact_matrix( R );\n')

    def check_finite( self ):
        return self.function('check_finite','double {name}( double v )',
                             self.lang.fail(f'!{self.lang.fct("isfinite","v")}','NaN or infinite value')
                             + '  return v;\n')

    def to_int_field( self, name, t, lo, hi ):
        """The function converting floating point numbers to integers of the
        type t for pdgcode or userflags, which must be integers from lo to hi"""
        T = self.lang.ctype(t)
        return self.function(f'to_{name}',f'{T} {{name}}( double v )',
                             self.lang.fail(f'!( v >= {lo}.0 && v <= {hi}.0 ) || v != {self.lang.fct("floor","v")}',
                                            f'Values of {name} must be integers from {lo} to {hi}')
                             + f'  return {self.lang.cast("v",t)};\n')
