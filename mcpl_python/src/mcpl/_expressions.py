
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
on blocks of particles."""

__all__ = [ 'ParticleEdit', 'ParticleFilter', 'ParticleValue' ]

import ast
import functools

from ._common import MCPLError
from ._exprcore import (
    _Q,
    _V,
    _dimstr,
    _edit_statements,
    _EmptyBlock,
    _Expr,
    _expr_constants,
    _expr_field_dims,
    _expr_fields,
    _expr_functions,
    _expr_normalise,
    _expr_unit_hints,
    _expr_vectors,
    _expr_wl_unit,
    _ExprEvaluator,
    _rotated_vectors,
    _rotation_matrix_args,
    _rotation_planes,
    _unit_hint,
)
from ._exprrotation import _rotation_matrix
from ._exprsyntax import (
    _dim_E,
    _expr_parse,
    _expr_units,
    _expr_unparse,
)
from ._numpy import np
from ._particles import _particle_names, _wavelength_pdgcodes
from ._physics import (
    ekin_from_wavelength,
)


def _expr_canonical( expr, edit = False ):
    """The normalised form of an expression (or of the statements of an edit,
    or of a pick with statements), generated from its parsed form: the same
    for all ways of writing it which are parsed the same, e.g. "ekin/MeV" and
    "(ekin) / MeV", or "25meV" and "25.0 meV". Raises MCPLError for invalid
    syntax."""
    expr = _expr_normalise(expr)
    parts = _split_statements(expr,positions = True)
    if not edit and len(parts) == 1:
        return _Expr(parts[0][0]).canonical
    return ';'.join( _expr_unparse(_expr_parse(part, mode = 'exec', context = ( expr, pos )))
                     for part, pos in parts )

def _check_conditions( node, expr ):
    """Raise MCPLError where a PDG code is used as a condition (in the
    expression of a pick, or a part of it combined with and, or and not), as
    in "neutron" or "pdgcode and x > 0cm", which would be true for all
    particles (other integers can be conditions, as in userflags & 0x10)"""
    if isinstance(node,ast.BoolOp):
        for v in node.values:
            _check_conditions(v,expr)
        return
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):
        _check_conditions(node.operand,expr)
        return
    if ( isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
         and node.func.id == 'abs' and len(node.args) == 1 ):
        node = node.args[0]
    if isinstance(node,ast.Name) and node.id in _particle_names:
        raise MCPLError(f'{node.id} is a PDG code ({_particle_names[node.id]}), not a condition'
                        f' (e.g. pdgcode == {node.id}), in expression "{expr}"')
    if isinstance(node,ast.Name) and node.id == 'pdgcode':
        raise MCPLError(f'pdgcode is not a condition (e.g. pdgcode == neutron), in'
                        f' expression "{expr}"')

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
    numbers, arithmetic (+, -, *, /, and ^ or ** for powers),
    comparisons (which can be chained, as in "0 < x < 2cm"), logical operations
    (and, or, not), bitwise &, | and ~ on integers (e.g. on userflags, as in
    "userflags & 0x10", where integers which are not 0 are true), functions
    (sqrt, abs, floor, ceil, exp, log, log10, sin, cos, tan, asin, acos,
    atan, atan2, hypot, min, max, clamp, and mod(a,b) for the remainder of the
    division of integers), vectors (pos, dir and pol for the position,
    direction and polarisation, of which x is an alias of pos.x or pos.at(0),
    or written as (0,0,1m), with +, -, * and / by numbers, abs(v) for their
    lengths, v^2, dot(v,w), cross(v,w), and angle(v,w) for the angle between
    them, which is precise also for small angles), the constant
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
    (length, also for wavelengths), as in "ekin < 25meV", "wavelength >
    0.18nm" or "x^2 + y^2 < 4cm^2" (a power directly after a unit only
    applies to the unit, and units can also have half powers, as in
    "sqrt(ekin)/sqrt(eV)"). The units deg and rad can be used for
    angles (which are otherwise in radians), as in "acos(uz) < 10deg".
    Expressions with missing or inconsistent units, like "x < 2" or "x <
    1meV", are rejected.
    """
    def __init__( self, expression ):
        #(statements before the condition, as in "r = hypot(x,y); r > 2cm"):
        self._statements_of = _Statements(expression,pick = True)
        self._e = self._statements_of.condition
        self._expr = self._statements_of.text
        _check_conditions(self._e.tree.body,self._expr)
        self(_EmptyBlock())#check units etc.
        #(for marking stat:sum entries as not available when particles are
        #picked by their positions in the file):
        self._uses_fileidx = 'fileidx' in self._statements_of.fields
    @property
    def expression( self ):
        """The expression (with normalised whitespace)"""
        return self._expr
    def __call__( self, block ):
        """Return boolean array picking particles in the block"""
        ev = _ExprEvaluator(block,self._expr)
        self._statements_of.run(ev,set())
        res = np.asarray(ev.scalar(ev(self._e.tree),'a condition').v)
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
        if q.d is not None:
            u = _expr_unit_hints.get(q.d)
            if u == 'cm' and 'wavelength' in self._expr:
                u = 'Aa'
            e = self._expr.strip()
            e = e if e.isidentifier() else f'({e})'
            hint = f', e.g. {e}/{u}' if u else ''
            raise MCPLError(f'Expression "{self._expr}" has units'
                            f' ({_dimstr(q.d)}), so divide it by a unit{hint}')
        return _values(q,block)
    def __repr__( self ):
        return f'ParticleValue({self._expr!r})'

def _assignable_fields():
    """The fields (and vectors, like pos) which edits can assign"""
    return tuple( f for f in _expr_fields if f != 'fileidx' ) + tuple(_expr_vectors)

class _Statements:
    """Statements separated by ";", which edits are made of (see ParticleEdit),
    and which picks can have before their condition (see ParticleFilter), as
    in "r = hypot(x,y); r > 2cm", where they can only assign variables. They
    are parsed once, and run on blocks of particles by run()."""
    _assignable = _assignable_fields()

    def __init__( self, expression, pick = False ):
        self.text = _expr_normalise(expression)
        self.statements = []
        self.variables, self._used = set(), set()
        parts = _split_statements(self.text,positions = True)
        if pick:
            parts, ( last, lastpos ) = parts[:-1], parts[-1]
        for part, pos in parts:
            self._parse(part,pos,pick)
        #(the condition of a pick, the last part):
        self.condition = None
        if pick:
            try:
                tree = _expr_parse(last, context = ( self.text, lastpos ))
            except MCPLError:
                if ';' in self.text and self._is_assignment(last):
                    raise MCPLError('A pick ends with its condition, as in'
                                    f' "r = hypot(x,y); r > 2cm", in "{self.text}"') from None
                raise
            self.condition = _Expr(self.text, tree = tree.body, variables = self.variables)
            self._used.update( self.condition.names & self.variables )
        unused = sorted(self.variables - self._used)
        if unused:
            fields = ( '' if pick else ' (fields which can be assigned are: '
                       + ', '.join(self._assignable) + ')' )
            raise MCPLError(f'Variable "{unused[0]}" is assigned but never used'
                            f' in "{self.text}"{fields}')

    @staticmethod
    def _is_assignment( part ):
        """Whether the text is an assignment (as of a variable)"""
        try:
            stmt = _expr_parse(part, mode = 'exec').body
        except MCPLError:
            return False
        return len(stmt) == 1 and isinstance(stmt[0],( ast.Assign, ast.AugAssign ))

    def _check_var( self, name, pick ):
        """Check that a variable can have the name"""
        if name in _expr_fields:
            raise MCPLError(f'{name} (the position of the particles in the'
                            f' file) can not be changed, in "{self.text}"')
        if not ( name.isidentifier() and name == name.lower() ) or (
                name in _expr_constants or name in _expr_units
                or name in _expr_functions or name in _edit_statements ):
            fields = ( '' if pick else 'fields which can be assigned are: '
                       + ', '.join(self._assignable) + ', and other ' )
            raise MCPLError(f'Can not assign to "{name}" in "{self.text}" ({fields}'
                            'lowercase names which are not names of fields, units,'
                            ' constants or functions can be used for variables)')

    def _parse( self, part, pos, pick ):
        """Parse a statement (in a pick, only assignments of variables)"""
        variables = self.variables
        tree = _expr_parse(part, mode = 'exec', context = ( self.text, pos ))
        stmt = tree.body[0] if len(tree.body) == 1 else None
        if ( isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Call)
             and isinstance(stmt.value.func,ast.Name)
             and stmt.value.func.id in _edit_statements ):
            if pick:
                raise MCPLError(f'{stmt.value.func.id}(..) changes the particles, which'
                                f' picks can not do (edits can), in "{self.text}"')
            self.statements.append(self._parse_call(stmt.value,part,variables))
            return
        if not isinstance(stmt,(ast.Assign,ast.AugAssign)):
            if pick:
                raise MCPLError('Only assignments of variables, like "r = hypot(x,y)",'
                                ' can come before the condition of a pick (separated'
                                f' by ";"), in "{self.text}"')
            raise MCPLError(f'Expected assignments like "x = 2*y" (or'
                            ' swap(..) or rotations like rotate_z(..)) in'
                            f' "{self.text}"')
        target = stmt.targets if isinstance(stmt,ast.Assign) else [stmt.target]
        if len(target) != 1 or not isinstance(target[0],ast.Name):
            raise MCPLError(f'Unsupported assignment "{part}" in "{self.text}"')
        name = target[0].id
        if name in self._assignable and pick:
            raise MCPLError(f'Picks can not change the particles (here {name}), only'
                            ' variables, like "r = hypot(x,y)" (edits can change the'
                            f' particles), in "{self.text}"')
        if name not in self._assignable:
            self._check_var(name,pick)
            if isinstance(stmt,ast.AugAssign) and name not in variables:
                raise MCPLError(f'Variable "{name}" used before it is'
                                f' assigned in "{self.text}"')
        if isinstance(stmt,ast.AugAssign):
            value = ast.BinOp(left = ast.Name(id = name, ctx = ast.Load()),
                              op = stmt.op, right = stmt.value)
        else:
            value = stmt.value
        value = _Expr(self.text, tree = value, variables = variables)
        self._used.update( value.names & variables )
        if name not in self._assignable:
            variables.add(name)
        self.statements.append( ('assign', name, value) )

    def _parse_call( self, call, part, variables ):
        fname = call.func.id
        if call.keywords:
            raise MCPLError(f'Unsupported syntax "{part}" in "{self.text}"')
        if fname == 'swap':
            if len(call.args) != 2 or not all( isinstance(a,ast.Name)
                                               for a in call.args ):
                raise MCPLError(f'swap(..) takes two fields (or variables)'
                                f' as arguments, as in swap(x,y), in "{self.text}"')
            names = [ a.id for a in call.args ]
            for n in names:
                if n == 'fileidx':
                    raise MCPLError('fileidx (the position of the particles in'
                                    ' the file) can not be changed, in'
                                    f' "{self.text}"')
                if n not in self._assignable and n not in variables:
                    raise MCPLError(f'Can not swap "{n}" in "{self.text}"'
                                    ' (it is not a field or variable)')
            self._used.update( n for n in names if n in variables )
            return ( 'swap', names[0], names[1] )
        if fname in _rotation_matrix_args:
            nargs = _rotation_matrix_args[fname]
            if len(call.args) != nargs:
                what = ( 'an axis and an angle, as in rotate_around((0,0,1),90deg)'
                         if fname == 'rotate_around' else 'the vectors v, vout, u and'
                         ' uout, as in rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))' )
                raise MCPLError(f'{fname}(..) takes {nargs} arguments ({what}) in'
                                f' "{self.text}"')
            args = tuple( _Expr(self.text, tree = a, variables = variables)
                          for a in call.args )
            for a in args:
                self._used.update( a.names & variables )
            return ( fname, args )
        if len(call.args) != 1:
            raise MCPLError(f'{fname}(..) takes one argument (an angle) in'
                            f' "{self.text}"')
        angle = _Expr(self.text, tree = call.args[0], variables = variables)
        self._used.update( angle.names & variables )
        return ( fname, angle )

    @functools.cached_property
    def fields( self ):
        """The particle fields used (including fileidx)"""
        exprs, names = [ self.condition ] if self.condition is not None else [], set()
        for st in self.statements:
            for v in st[1:]:
                if isinstance(v,_Expr):
                    exprs.append(v)
                elif isinstance(v,tuple):
                    exprs += v
                elif v in _expr_fields:
                    names.add(v)#(of swap)
        return frozenset(names).union(*( e.fields for e in exprs ))

    @functools.cached_property
    def modified( self ):
        """Names of the fields which the statements can modify (ekin for
        assignments of the wavelength)"""
        mod = set()
        for st in self.statements:
            if st[0] == 'assign' and st[1] in self._assignable:
                mod.update( _expr_vectors.get(st[1],
                                              ( 'ekin' if st[1] == 'wavelength' else st[1], )) )
            elif st[0] == 'swap':
                mod.update( n for n in st[1:] if n in self._assignable )
            elif st[0] in _rotation_planes:
                for plane in _rotation_planes[st[0]]:
                    mod.update(plane)
            elif st[0] in _rotation_matrix_args:
                for vector in _rotated_vectors:
                    mod.update(vector)
        return frozenset(mod)

    def run( self, ev, modified ):
        """Run the statements with the evaluator ev (of a block), which gets
        the values of the variables and of the changed fields in its state,
        adding the names of the changed fields to the set modified"""
        state = ev.state
        for st in self.statements:
            if st[0] == 'assign':
                _, name, value = st
                q = ev(value.tree)
                if name in _expr_vectors:
                    comps = _expr_vectors[name]
                    d = _expr_field_dims.get(comps[0])
                    if not ( isinstance(q,_V) and len(q.c) == 3
                             and ( q.d == d or all( c.zero for c in q.c ) ) ):
                        what = q.describe() if isinstance(q,_V) else 'a number'
                        dname = f' of {_dimstr(d)}s' if d else ' without units'
                        raise MCPLError(f'Can not assign {what} to {name}, which is a'
                                        f' 3D vector{dname}, in expression "{self.text}"')
                    for c, qc in zip(comps,q.c):
                        self._assign_field(ev,c,qc,modified)
                elif name in self._assignable:
                    self._assign_field(ev,name,ev.scalar(q,f'assigned to {name}'),modified)
                else:
                    state[name] = q
            elif st[0] == 'swap':
                _, a, b = st
                qa, qb = ( ev.scalar(ev.name(c),'swapped') for c in (a,b) )
                ev.same(qa,qb,'swap(..)')
                state[a], state[b] = qb, qa
                modified.update( e for e in (a,b) if e in self._assignable )
            elif st[0] in _rotation_matrix_args:
                self._rotate_by_matrix(ev,st[0],st[1],modified)
            else:
                fname, angle = st
                qa = ev.scalar(ev(angle.tree),f'an angle in {fname}(..)')
                if qa.d is not None:
                    ev.error(f'{fname}(..) requires an angle (e.g. 90deg), not'
                             f' {_dimstr(qa.d)}')
                c, s = np.cos(qa.v), np.sin(qa.v)
                #Rotations by multiples of 90 degrees are done exactly, by
                #swapping and negating values, since the cos and sin of such
                #angles in radians are not exactly 0 and +-1 (e.g. rotate_z(90deg)
                #gives exactly (x,y) -> (-y,x)). Adding 0.0 to the results
                #avoids negative zeros (-0.0 + 0.0 is 0.0):
                q = np.asarray(qa.v,dtype=float) / ( 0.5 * np.pi )
                k = np.round(q)
                quarter = ( np.abs( q - k ) <= 8 * np.finfo(float).eps
                            * np.maximum( 1.0, np.abs(k) ) )
                kq = np.mod(k,4).astype(int)
                for a, b in _rotation_planes[fname]:
                    va, vb = ev.name(a), ev.name(b)
                    ra, rb = c * va.v - s * vb.v, s * va.v + c * vb.v
                    if np.any(quarter):
                        A, B = np.asarray(va.v), np.asarray(vb.v)
                        ra = np.where(quarter, np.choose(kq,(A,-B,-A,B)), ra)
                        rb = np.where(quarter, np.choose(kq,(B,A,-B,-A)), rb)
                    state[a] = _Q(ra + 0.0, va.d)
                    state[b] = _Q(rb + 0.0, vb.d)
                    modified.update((a,b))
    def _assign_field( self, ev, name, q, modified ):
        """Assign the value q to the field"""
        d = _expr_field_dims.get(name)
        if q.d != d and not q.zero:
            what = _dimstr(q.d) if q.d is None else f'value with {_dimstr(q.d)}'
            dname = 'unitless' if d is None else f'a {_dimstr(d)}'
            dname = dname.replace('a energy','an energy')
            hint = _unit_hint(d) if q.d is None else ''
            raise MCPLError(f'Can not assign {what} to {name}, which is'
                            f' {dname}{hint}, in expression "{self.text}"')
        v = np.broadcast_to(np.asarray(q.v,dtype=( float if name not in
                                                   ('pdgcode','userflags')
                                                   else None )),(len(ev._block),))
        if name == 'wavelength':
            self._set_wavelength(ev,v,modified)
            return
        ev.state[name] = _Q(v,d)
        modified.add(name)

    def _rotate_by_matrix( self, ev, fname, args, modified ):
        """Rotate the positions, directions and polarisations with the matrix
        of rotate_around or rotate_frame (see _rotation_matrix)"""
        qs = [ ev(a.tree) for a in args ]
        #(3D vectors, and the angle of rotate_around):
        values = []
        for i, q in enumerate(qs):
            if fname == 'rotate_around' and i == 1:
                q = ev.scalar(q,f'the angle in {fname}(..)')
                if q.d is not None:
                    ev.error(f'{fname}(..) requires an angle (e.g. 90deg) as its last'
                             f' argument, not {_dimstr(q.d)}')
                values.append(q.v)
            elif not ( isinstance(q,_V) and len(q.c) == 3 ):
                what = ( 'a 3D vector (the axis) and an angle, as in rotate_around((0,0,1),90deg)'
                         if fname == 'rotate_around' else 'four 3D vectors, as in'
                         ' rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))' )
                ev.error(f'{fname}(..) takes {what}')
            else:
                values += [ c.v for c in q.c ]
        R = _rotation_matrix(fname,values)
        if isinstance(R,str):
            ev.error(f'In {fname}(..), {R}')
        state, n = ev.state, len(ev._block)
        for names in _rotated_vectors:
            qv = [ ev.name(c) for c in names ]
            V = np.stack([ np.broadcast_to(np.asarray(q.v,dtype=float),(n,)) for q in qv ],
                         axis=-1)
            res = np.einsum('...ij,...j->...i',R,V) + 0.0#(no negative zeros)
            for i, c in enumerate(names):
                state[c] = _Q(res[:,i],qv[i].d)
                modified.add(c)

    def _set_wavelength( self, ev, wl, modified ):
        """Set kinetic energy from wavelength (given in cm)"""
        pdg = np.asarray(ev.name('pdgcode').v)
        if not np.all( np.isin( pdg, _wavelength_pdgcodes ) ):
            raise MCPLError('wavelength can only be assigned to neutrons'
                            ' (pdgcode 2112) and gammas (pdgcode 22)'
                            f' in expression "{self.text}"')
        if np.any( np.asarray(wl) <= 0.0 ):
            raise MCPLError('wavelength must be assigned positive values'
                            f' in expression "{self.text}"')
        ev.state['ekin'] = _Q(np.broadcast_to(ekin_from_wavelength(wl/_expr_wl_unit,pdg),
                                              wl.shape),_dim_E)
        modified.add('ekin')

def _split_statements( expr, positions = False ):
    """The statements separated by ";" (outside parentheses) of an edit or a
    pick (with their positions in it, if positions is set)"""
    parts, depth, start = [], 0, 0
    for i, c in enumerate(expr):
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        if c == ',' and depth == 0:
            raise MCPLError('Separate statements with ";"'
                            f' (not ",") in "{expr}"')
        if c == ';' and depth == 0:
            parts.append( ( expr[start:i], start ) )
            start = i + 1
    parts.append( ( expr[start:], start ) )
    parts = [ ( p.strip(), pos + len(p) - len(p.lstrip()) ) for p, pos in parts if p.strip() ]
    if not parts:
        raise MCPLError('Empty expression')
    return parts if positions else [ p for p, _ in parts ]


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
        and /=), where the right hand sides use the syntax of ParticleFilter.
        The values must have the units of the field (e.g. a length for x).
        Assigning wavelength changes the kinetic energy of neutrons and gammas.
        The vectors pos, dir and pol can be assigned too, as in
        "pos += (0,0,1m)".
      * Assignments to variables (lowercase names which are not names of
        fields, units, constants or functions), which can be used in later
        statements, for instance to keep original values: "tmp = x; x = y;
        y = tmp". Variables keep the units of their values.
      * swap(a,b), which exchanges the values of two fields (or variables)
        with the same units, e.g. "swap(x,y)".
      * rotate_x(angle), rotate_y(angle), rotate_z(angle), which rotate the
        position, direction and polarisation of the particles around the
        given axis (through the origin), e.g. "rotate_y(90deg)". The rotation
        is counter-clockwise when looking from the positive axis towards the
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
    _assignable = _assignable_fields()
    def __init__( self, expression ):
        self._statements_of = _Statements(expression)
        self._expr = self._statements_of.text
        self._statements = self._statements_of.statements
        self._modified = self._statements_of.modified
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
        self._statements_of.run(ev,modified)
        state, n = ev.state, len(block)
        res = {}
        for name in sorted(modified):
            v = np.asarray(state[name].v)
            if name in ('pdgcode','userflags') and v.dtype.kind not in 'iub':
                vi = np.round(v).astype(np.int64)
                if not np.all( vi == v ):
                    raise MCPLError(f'Non-integer values assigned to {name}')
                v = vi
            res[name] = np.broadcast_to(v,(n,))
        return res

    def __repr__( self ):
        return f'ParticleEdit({self._expr!r})'

def _quantity_functions( coords ):
    """Functions calculating the values of expressions for a block, given as a
    dictionary of names and expressions. Each function returns the values (an
    array) and their dimension (powers of length, energy and time, in which
    the values are in the units of MCPL: cm, MeV and ms, or None for values
    without units)."""
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

def _as_filter(pick):
    if isinstance(pick,str):
        return ParticleFilter(pick)
    return pick

def _as_edit(edit):
    if isinstance(edit,str):
        return ParticleEdit(edit)
    return edit
