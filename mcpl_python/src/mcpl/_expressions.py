
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

"""Particle expressions (picks and edits), which are evaluated with numpy
on blocks of particles. They are parsed (_expr_str2ast) and checked
(_expr_astcheck) once, and their trees are evaluated (_expr_eval)."""

__all__ = [ 'ParticleEdit', 'ParticleFilter', 'ParticleValue' ]

import functools
import re

from ._common import MCPLError
from ._expr_ast import Name, _names
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
    _modified_fields,
)
from ._exprunits import _dim_unknown
from ._numpy import np


def _parsed( expression, kind ):
    """The text (with normalised whitespace) and the checked tree of an
    expression of the kind (see _expr_str2ast)"""
    text = _expr_normalise(expression)
    tree = _expr_str2ast(text,kind)
    _expr_astcheck(tree,text)
    return text, tree

def _expr_canonical( expr, edit = False ):
    """The normalised form of an expression (or of the statements of an edit,
    or of a pick with statements), generated from its parsed form: the same
    for all ways of writing it which are parsed the same, e.g. "ekin/MeV" and
    "(ekin) / MeV", or "25meV" and "25 meV". Raises MCPLError for invalid
    syntax."""
    return _expr_ast2str(_expr_str2ast(expr,'edit' if edit else 'pick'))

class _Expr:
    """A parsed and checked expression of a value, with the properties derived
    from its tree, and its evaluation"""
    def __init__( self, text ):
        self.text, self.tree = _parsed(text,'value')

    @functools.cached_property
    def canonical( self ):
        """The normalised text, generated from the tree (see _expr_canonical)"""
        return _expr_ast2str(self.tree)

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

    @property
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
            mask &= np.isin(np.broadcast_to(getattr(block,field),(len(block),)),list(values))
        return mask

    def evaluate( self, block, active = None ):
        """The value (a _Q) for the particles of the block (for those of the mask
        active, if given)"""
        ev = _ExprEvaluator(block,self.text)
        ev.active = active
        return ev.scalar(ev(self.tree),'the value of an expression')

class ParticleFilter:
    """Picks particles with an expression, which is evaluated with numpy on
    blocks of particles (this is also what the pick arguments of MCPLFile,
    MCPLOutFile, histogram, collect_stats, etc. do, and mcpltool -p). For
    instance:

       flt = ParticleFilter("pdgcode == neutron"
                            " and ekin < 25meV"
                            " and abs(x) <= 2mm")
       for block in mcplfile.particle_blocks:
           picked = block[ flt(block) ]

    Whitespace (including newlines) is only used to separate the parts of
    expressions, so long expressions can be written over several lines. The
    expression syntax is like in Python: particle fields (x, y, z, ux, uy,
    uz, polx, poly, polz, ekin, time, weight, pdgcode, userflags, and
    wavelength), fileidx (the position of the particles in the file,
    counting from 0, e.g. "mod(fileidx,10) == 0" for every tenth particle),
    numbers, arithmetic (+, -, *, /, // for the division of non-negative
    integers, and ^ or ** for powers),
    comparisons (which can be chained, as in "0 < x < 2cm"), logical operations
    (and, or, not), bitwise & and | on integers (e.g. on userflags, as in
    "userflags & 0x10", where integers which are not 0 are true), functions
    (sqrt, abs, floor, ceil, exp, log, log10, sin, cos, tan, asin, acos,
    atan, atan2, hypot, min, max, clamp, round, and mod(a,b) for the remainder
    of the division of non-negative integers), the fields of the userdata of
    particles (userdata.NAME, and userdata.NAME.at(INDEX) for the values of
    arrays, with the units of the fields in the userdata layout, e.g.
    "userdata.temp > 300K"),
    vectors (pos, dir, and pol for the position,
    direction, and polarisation, of which x is an alias of pos.x or pos.at(0),
    or written as (0,0,1m), with +, -, *, and / by numbers, abs(v) for their
    lengths, v^2, dot(v,w), cross(v,w), and angle(v,w) for the angle between
    them, which is precise also for small angles), through_sphere(center,
    radius) for whether the line of flight of the particles (through their
    positions along their directions, both forwards and backwards) passes
    through a sphere, as in "through_sphere((0,0,1m),5cm)", the constant
    pi, and the names neutron, antineutron, proton, antiproton, electron,
    positron (or antielectron), muon, antimuon, and gamma (or photon), which
    can be used for pdgcode values. The wavelength is only defined for
    neutrons and gammas, so it is an error to use it for other particles, and
    expressions must pick neutrons or gammas before using it, as in
    "pdgcode == neutron and wavelength > 1.8Aa" (the right side of and is
    only evaluated for particles where the left side is true, and the right
    side of or only for particles where the left side is false).

    Variables can be assigned before the condition, separated by ";" as the
    statements of edits (see ParticleEdit), as in "r = hypot(x,y); r > 2cm
    and r < 5cm", but the fields of the particles can not be changed.

    Values with units must always be given with units (except for a plain 0,
    as in "x > 0"): meV, eV, keV, MeV,
    GeV, TeV (energy), ns, us, ms, s (time), Aa, nm, um, mm, cm, m, km
    (length, also for wavelengths), K (temperature, for userdata fields), as
    in "ekin < 25meV", "pdgcode == neutron and wavelength > 0.18nm" or
    "x^2 + y^2 < 4cm^2" (a power directly after a unit only
    applies to the unit, and units can also have half powers, as in
    "sqrt(ekin)/sqrt(eV)"). The units deg and rad can be used for
    angles (which are otherwise in radians), as in "acos(uz) < 10deg".
    Expressions with missing or inconsistent units, like "x < 2" or "x <
    1meV", are rejected.

    Integers (like pdgcode, userflags, and integer userdata) work essentially
    as in C, but with more protection against problems like overflow, which
    gives an error, as does combining unsigned integers (like userflags) with
    negative values. The operator / always divides as floating point numbers
    (e.g. 1/2 is 0.5), and // divides non-negative integers (e.g. 7//2 is 3).
    """
    def __init__( self, expression ):
        #(statements before the condition, as in "r = hypot(x,y); r > 2cm"):
        self._expr, self._tree = _parsed(expression,'pick')
        self(_EmptyBlock())#check units etc.
        #(for marking stat:sum entries as not available when particles are
        #picked by their positions in the file):
        self._uses_fileidx = 'fileidx' in _fields_used(self._tree)
    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """Return boolean array picking particles in the block"""
        ev = _ExprEvaluator(block,self._expr)
        _run_statements(ev,self._tree.statements,self._expr,set())
        res = np.asarray(ev.scalar(ev(self._tree.condition),'a condition').v)
        if res.dtype.kind in 'iu':
            res = res != 0#like in C, e.g. for "userflags & 0x10"
        if res.dtype != bool:
            raise MCPLError(f'Expression "{self._expr}" is not a condition'
                            ' (e.g. a comparison)')
        return np.broadcast_to(res,(len(block),))
    def __repr__( self ):
        return f'ParticleFilter({self._expr!r})'

def _values( q, block ):
    """The values of an evaluated expression (a _Q) for each particle of the
    block (with 1 and 0 for true and false)"""
    v = np.asarray(q.v)
    if v.dtype == bool:
        v = v.astype(float)
    return np.broadcast_to(v,(len(block),))

class ParticleValue:
    """Numerical value calculated from particle fields with an expression
    (with the syntax of ParticleFilter), for instance for histograms. The
    expression must not have units, so values with units must be divided by
    a unit, as in "ekin/MeV" or "hypot(x,y)/mm". Boolean expressions (like
    "x > 0cm") give 1 for true and 0 for false. For instance:

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
        """The expression (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """Return array with the values for the particles in the block"""
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
        return f'ParticleValue({self._expr!r})'

class ParticleEdit:
    """Modification of particle fields given by an expression with statements
    separated by ";", which are evaluated with numpy on blocks of particles.
    For instance:

       edit = ParticleEdit("rotate_z(90deg); z += 10cm;"
                           " wavelength = 1.8Aa")
       for block in mcplfile.particle_blocks:
           outfile.add_particles( block, **edit(block) )

    The statements are executed in order, so each statement sees the results
    of the previous ones. The statements are:

      * Assignments to fields, like "x = 2m*ux" or "z += 1cm" (also -=, *=,
        /=, ^=, and &= and |= for integers), where the right hand sides use
        the syntax of ParticleFilter.
        The values must have the units of the field (e.g. a length for x).
        Assigning wavelength changes the kinetic energy of neutrons and gammas.
        The vectors pos, dir, and pol can be assigned too, as in
        "pos += (0,0,1m)".
      * Assignments to variables (lowercase names which are not names of
        fields, units, constants, or functions), which can be used in later
        statements, for instance to keep original values: "tmp = x; x = y;
        y = tmp". Variables keep the units of their values.
      * swap(a,b), which exchanges the values of two fields (or variables)
        with the same units, e.g. "swap(x,y)".
      * rotate_x(angle), rotate_y(angle), rotate_z(angle), which rotate the
        position, direction, and polarisation of the particles around the
        given axis (through the origin), e.g. "rotate_y(90deg)" (angles
        written as numbers need a unit, deg or rad). The rotation is
        counter-clockwise when looking from the positive axis towards the
        origin. Rotations by multiples of 90 degrees are exact (e.g.
        "rotate_z(90deg)" changes (x,y) to exactly (-y,x)), and rotations never
        give negative zeros (-0.0).
      * rotate_around(axis,angle), which rotates them around the axis (a
        vector, which need not be a unit vector) through the origin,
        counter-clockwise when looking from the axis towards the origin, e.g.
        "rotate_around((1,1,0),30deg)".
      * rotate_frame(v,vout,u,uout), the rotation which turns the direction
        of the vector v into that of vout, and u into uout (as RotMatrix of
        NCrystal), e.g. a beam direction and an "up" direction of one frame
        into those of another. The angle between v and u must be that
        between vout and uout, and v and u must not be parallel.
    """
    def __init__( self, expression ):
        self._expr, self._tree = _parsed(expression,'edit')
        self._modified = _modified_fields(self._tree.statements)
        self(_EmptyBlock())#check units etc.

    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr

    @property
    def modified_fields( self ):
        """Names of the fields which the edit can modify (ekin for edits of
        the wavelength)."""
        return self._modified

    def __call__( self, block ):
        """Return dictionary with new values of the modified fields, which can
        be passed as keyword arguments to MCPLOutFile.add_particles together
        with the block."""
        ev = _ExprEvaluator(block,self._expr)
        modified = set()
        _run_statements(ev,self._tree.statements,self._expr,modified)
        state, n = ev.state, len(block)
        res = {}
        for name in sorted(modified):
            v = np.asarray(state[name].v)
            if name in ('pdgcode','userflags'):
                #(e.g. after swap(..)):
                v = _int_field_values(name,v,self._expr)
            res[name] = np.broadcast_to(v,(n,))
        return res

    def __repr__( self ):
        return f'ParticleEdit({self._expr!r})'

def _quantity_functions( coords ):
    """Functions calculating the values of expressions for a block, given as a
    dictionary of names and expressions. Each function returns the values (an
    array) and their dimension (powers of length, energy, time and
    temperature, in which the values are in the units of MCPL: cm, MeV, ms
    and K, or None for values without units)."""
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
    """The expression as an object of the class (ParticleFilter, ParticleEdit
    or ParticleValue) if it is a text, else as given (e.g. None)"""
    return cls(expr) if isinstance(expr,str) else expr

def _as_filter(pick):
    return _as_expression(ParticleFilter,pick)

def _as_edit(edit):
    return _as_expression(ParticleEdit,edit)
