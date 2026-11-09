
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

"""Particle expressions (edit expressions and values), which are evaluated
with numpy on blocks of particles. They are parsed (_expr_str2ast), checked
(_expr_astcheck), and normalised (_expr_ast2astnorm) once, and their
normalised trees are evaluated (_expr_eval), and written as their canonical
texts (_expr_ast2str)."""

__all__ = [ 'ParticleEdit', 'ParticleValue' ]

import functools
import re

from ._blocks import _EditedParticleBlock
from ._common import MCPLError
from ._expr_ast import Name, _names
from ._expr_ast2astnorm import _expr_ast2astnorm
from ._expr_ast2str import _expr_ast2str
from ._expr_astcheck import _expr_astcheck
from ._expr_eval import (
    _dimstr,
    _EmptyBlock,
    _ExprEvaluator,
    _int_field_values,
    _run_statements,
)
from ._expr_str2ast import _expr_normalise, _expr_str2ast
from ._expr_vocab import (
    _expr_field_domains,
    _expr_fields,
    _expr_unit_hints,
    _expr_value_names,
    _fields_used,
    _filters_on_fileidx,
    _is_condition,
    _modified_fields,
)
from ._exprunits import _dim_unknown
from ._numpy import np


def _parsed( expression, kind, unused_ok = False ):
    """The text (with normalised whitespace), the checked and normalised tree,
    and the canonical text of an expression of the kind (see _expr_str2ast and
    _expr_astcheck)"""
    text = _expr_normalise(expression)
    tree = _expr_str2ast(text,kind)
    _expr_astcheck(tree,text,unused_ok)
    tree = _expr_ast2astnorm(tree)
    return text, tree, _expr_ast2str(tree)

def _expr_canonical( expr, edit = False ):
    """The canonical text of a value (or of an edit expression), from its
    normalised tree: the same for all ways of writing it which are recognised
    as the same, e.g. "ekin/MeV" and "(ekin) / MeV", or "ekin > 5000eV" and
    "ekin > 5keV". Raises MCPLError for invalid expressions."""
    return _parsed(expr,'edit' if edit else 'value')[2]

class _Expr:
    """A parsed, checked, and normalised expression of a value, with its text
    (with normalised whitespace) and canonical text, the properties derived
    from its tree, and its evaluation"""
    def __init__( self, text ):
        self.text, self.tree, self.canonical = _parsed(text,'value')

    @functools.cached_property
    def names( self ):
        """All names used (fields, vectors, constants, particles, functions,
        and userdata fields)"""
        return _names(self.tree)

    @functools.cached_property
    def fields( self ):
        """The particle fields used (including fileidx, and those of the
        vectors used, as x for pos)"""
        return _fields_used(self.tree)

    @property
    def field( self ):
        """The field if the expression is just a field (as "pdgcode"), else None"""
        e = self.tree.expr
        return e.id if isinstance(e,Name) and e.id in _expr_fields else None

    @functools.cached_property
    def domains( self ):
        """Where the expression is defined, if only for some particles (as for
        wavelengths): a list of (field, values) which must all hold (see
        _expr_field_domains)"""
        return [ _expr_field_domains[f] for f in sorted(self.fields) if f in _expr_field_domains ]

    def value_label( self, value, unicode = False ):
        """Label of a value of the expression if it is a field whose values have
        names (as "n (2112)" for pdgcode, see _expr_value_names), else None"""
        names = _expr_value_names.get(self.field)
        return names[0](value,unicode) if names else None

    def domain_mask( self, block ):
        """Mask of the particles of the block for which the expression is
        defined"""
        mask = np.ones(len(block),dtype=bool)
        for field, values in self.domains:
            mask &= np_isin_few(np.broadcast_to(getattr(block,field),(len(block),)),values)
        return mask

    def evaluate( self, block, active = None ):
        """The value (a _Q) for the particles of the block (for those of the mask
        active, if given)"""
        ev = _ExprEvaluator(block,self.text)
        ev.active = active
        return ev.scalar(ev(self.tree),'the value of an expression')

def _values( q, block ):
    """The values of an evaluated expression (a _Q) for each particle of the
    block (with 1 and 0 for true and false)"""
    v = np.asarray(q.v)
    if v.dtype == bool:
        v = v.astype(float)
    return np.broadcast_to(v,(len(block),))

class ParticleValue:
    """Numerical value calculated from particle fields with an expression
    (with the syntax of ParticleEdit), e.g. for histograms. Values with units
    must be divided by a unit, as in "ekin/MeV" or "hypot(x,y)/mm", and
    conditions (like "x > 0cm") give 1 for true and 0 for false. Example:

       val = ParticleValue("ekin/meV")
       for block in mcplfile.particle_blocks:
           print( val(block) )
    """
    def __init__( self, expression ):
        self._e = _Expr(expression)
        self._expr = self._e.text
        self(_EmptyBlock())#check units etc.
    @property
    def expression( self ):
        """The expression in its canonical form (see ParticleEdit.expression)"""
        return self._e.canonical
    @property
    def expression_original( self ):
        """The expression as given (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """The values for the particles of the block (an array)"""
        q = self._e.evaluate(block)
        if q.d not in ( None, _dim_unknown ):
            u = _expr_unit_hints.get(q.d)
            if u == 'cm' and 'wavelength' in self._expr:
                u = 'Aa'
            e = self._expr.strip()
            e = e if re.fullmatch(r'\w+|userdata\.\w+(\.at\(\d+\))?',e) else f'({e})'
            hint = f', e.g. {e}/{u}' if u else ''
            raise MCPLError(f'Expression "{self._expr}" has units'
                            f' ({_dimstr(q.d)}), so divide it by a unit{hint}')
        return _values(q,block)
    def __repr__( self ):
        return f'ParticleValue({self._e.canonical!r})'

class ParticleEdit:
    """Filters and changes particles with an edit expression: statements
    separated by ";", executed in order with numpy on blocks of particles.
    For instance:

       edit = ParticleEdit("pdgcode == neutron; rotate_z(90deg);"
                           " z += 10cm; ekin < 25meV")
       for block in mcplfile.particle_blocks:
           outfile.add_particles( edit(block) )

    The statements are:

      * Conditions, like "ekin < 25meV", which keep the particles for which
        they are true. The statements after them only see those.
      * Assignments to fields, like "x = 2m*ux" or "z += 1cm" (also -=, *=,
        /=, ^=, and for integers //=, &=, and |=). The values must have the units
        of the field (e.g. a length for x). Assigning wavelength changes the
        kinetic energy of neutrons and gammas. The vectors pos, dir, and pol
        can be assigned too, as in "pos += (0,0,1m)".
      * Assignments to variables (lowercase names which are not names of
        fields, units, constants, or functions), which can be used in later
        statements, as in "r = hypot(x,y); r > 2cm and r < 5cm". Variables
        keep the units of their values.
      * swap(a,b), which exchanges the values of two fields (or variables)
        with the same units, e.g. "swap(x,y)".
      * rotate_x(angle), rotate_y(angle), rotate_z(angle), which rotate the
        position, direction, and polarisation of the particles around the
        given axis (through the origin), e.g. "rotate_y(90deg)" (angles
        written as numbers need a unit, deg or rad). The rotation is
        counter-clockwise when looking from the positive axis towards the
        origin. Rotations by multiples of 90deg are exact.
      * rotate_around(axis,angle), which rotates them around the axis (a
        vector, which need not be a unit vector) through the origin,
        counter-clockwise when looking from the axis towards the origin, e.g.
        "rotate_around((1,1,0),30deg)".
      * rotate_frame(v,vout,u,uout), the rotation which turns the direction
        of the vector v into that of vout, and u into uout, e.g. a beam
        direction and an "up" direction of one frame into those of another.
        The angle between v and u must be that between vout and uout, and v
        and u must not be parallel.

    Whitespace (also newlines) only separates the parts of expressions, so
    long expressions can be written over several lines. The syntax is like
    that of Python (but ^ is a power, as is **), with:

      * The particle fields x, y, z, ux, uy, uz, polx, poly, polz, ekin,
        time, weight, pdgcode, userflags, wavelength, and fileidx (the
        position of the particle in the file, from 0, as in
        "mod(fileidx,10) == 0" for every tenth particle).
      * The fields of the userdata, userdata.NAME (and userdata.NAME.at(i)
        for the values of arrays), with the units of the userdata layout, as
        in "userdata.temp > 300K".
      * Numbers, the constant pi, and the particle names neutron,
        antineutron, proton, antiproton, electron, positron (or
        antielectron), muon, antimuon, and gamma (or photon) for PDG codes.
      * Arithmetic (+, -, *, /, // for integers, and ^ or ** for powers),
        comparisons (which can be chained, as in "0cm < x < 2cm"), in and
        not in (as in "pdgcode in (neutron,gamma)"), and, or, and not, and
        the bitwise & and | of integers (as in "userflags & 0x10", where
        integers other than 0 are true).
      * The functions sqrt, abs, floor, ceil, round, exp, log, log10, sin,
        cos, tan, asin, acos, atan, atan2, hypot, min, max, clamp, and
        mod(a,b) (the remainder of non-negative integers).
      * Vectors: pos, dir, and pol (x is pos.x, also written pos.at(0)), and
        vectors like (0,0,1m), with +, -, and * and / by numbers, abs(v) for
        their lengths, v^2, dot(v,w), cross(v,w), and angle(v,w) (precise
        also for small angles).
      * through_sphere(center,radius) and through_box(center,half): whether
        the line of flight (forwards and backwards) passes through a sphere,
        or a box with its sides along the axes (half its sizes along x, y,
        and z), as in "through_sphere((0,0,1m),5cm)".

    The wavelength is only defined for neutrons and gammas, so keep only
    those first, as in "pdgcode == neutron; wavelength > 1.8Aa" (the right
    side of "and" is only evaluated where the left side is true, and that of
    "or" where it is false).

    Values with units must always be given with units (except for a plain 0,
    as in "x > 0"): meV, eV, keV, MeV, GeV, and TeV (energy), ns, us, ms,
    and s (time), Aa, nm, um, mm, cm, m, and km (length, also for
    wavelengths), and K (temperature, for userdata fields), as
    in "ekin < 25meV", "pdgcode == neutron and wavelength > 0.18nm", or
    "x^2 + y^2 < 4cm^2" (a power directly after a unit only
    applies to the unit, and units can also have half powers, as in
    "sqrt(ekin)/sqrt(eV)"). The units deg and rad can be used for
    angles (which are otherwise in radians), as in "acos(uz) < 10deg".
    Expressions with missing or inconsistent units, like "x < 2" or "x <
    1meV", are rejected.

    Integers (pdgcode, userflags, and integer userdata) follow the rules of C,
    except that overflow, and combining unsigned integers (like userflags)
    with negative values, are errors. The operator / always divides as floating point numbers
    (e.g. 1/2 is 0.5), and // divides non-negative integers (e.g. 7//2 is 3).
    """
    _unused_ok = False#(see _EditStart)

    def __init__( self, expression ):
        self._expr, self._tree, self._canonical = _parsed(expression,'edit',self._unused_ok)
        statements = self._tree.statements
        self._modified = _modified_fields(statements)
        self._has_filters = any( _is_condition(st) for st in statements )
        self._filters_on_fileidx = _filters_on_fileidx(statements)
        self._apply(_EmptyBlock())#check units etc.

    @property
    def expression( self ):
        """The expression in its canonical form, which is the same for all
        ways of writing it which are recognised as the same (e.g. "ekin >
        5000 eV" and "ekin>5keV" are both "ekin>5keV")"""
        return self._canonical
    @property
    def expression_original( self ):
        """The expression as given (with normalised whitespace)"""
        return self._expr

    @property
    def modified_fields( self ):
        """Names of the fields which the expression can change (ekin for
        changes of the wavelength)."""
        return self._modified

    @property
    def has_filters( self ):
        """Whether the expression can filter out particles"""
        return self._has_filters

    @property
    def has_changes( self ):
        """Whether the expression can change particles"""
        return bool(self._modified)

    @property
    def has_weight_changes( self ):
        """Whether the expression can change the weights of particles"""
        return 'weight' in self._modified

    @property
    def filters_on_fileidx( self ):
        """Whether the particles which the expression filters out can depend
        on their positions in the file (fileidx), as with "mod(fileidx,10) ==
        0", or "x = fileidx*1cm; x > 5cm"."""
        return self._filters_on_fileidx

    def __call__( self, block ):
        """The particles of the block which are kept, with their changes (a
        new block)"""
        return self._edited(block)

    def _edited( self, block, counts = None ):
        """As __call__, where counts (if given) gets the number of particles
        left after each statement added"""
        kept, fields = self._apply(block,counts)
        if kept is not None:
            block = block[kept]
        return _EditedParticleBlock(block,fields) if fields else block

    def _apply( self, block, counts = None ):
        """The positions in the block of the particles which are kept (None
        for all), and the new values of their changed fields (see _edited for
        counts)"""
        ev = _ExprEvaluator(block,self._expr)
        modified = set()
        _run_statements(ev,self._tree.statements,self._expr,modified,counts)
        state, n = ev.state, len(ev._block)
        fields = {}
        for name in sorted(modified):
            v = np.asarray(state[name].v)
            if name in ('pdgcode','userflags'):
                #(e.g. after swap(..)):
                v = _int_field_values(name,v,self._expr)
            fields[name] = np.broadcast_to(v,(n,))
        return ev.kept, fields

    def __repr__( self ):
        return f'ParticleEdit({self._canonical!r})'

class _EditStart(ParticleEdit):
    """The first statements of an edit expression, where variables may be
    unused (as they can be used by the statements after them)"""
    _unused_ok = True

def _quantity_functions( coords ):
    """Functions calculating the values of expressions for a block, given as a
    dictionary of names and expressions. Each function returns the values (an
    array) and their dimension (powers of length, energy, time, and
    temperature, or None without units); values are in cm, MeV, ms, and K."""
    if isinstance(coords,str) or not hasattr(coords,'items'):
        raise MCPLError('The coords parameter must be a dictionary of'
                        ' coordinate names and expressions')
    res = {}
    for name, expr in coords.items():
        if not isinstance(name,str) or not name:
            raise MCPLError('Coordinate names must be non-empty strings')
        e = _Expr(expr)
        def fct( block, e = e ):
            q = e.evaluate(block)
            return _values(q,block), q.d
        fct(_EmptyBlock())#check units etc.
        res[name] = fct
    return res

def _as_expression( cls, expr ):
    """The expression as an object of the class (ParticleEdit or
    ParticleValue) if it is a text, else as given (e.g. None)"""
    return cls(expr) if isinstance(expr,str) else expr

def _as_edit(edit):
    return _as_expression(ParticleEdit,edit)
