
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

"""The parser of particle expressions (see _expressions), giving their trees
(see _expr_ast). Interface: _expr_str2ast(text, kind) for values and edit
expressions, _expr_statements(text) for the statements of an edit expression
(also the inactive ones), and _expr_normalise(text) for the text with
normalised whitespace. The
parser only knows the syntax, and the names of units and particles: whether
the names and functions exist, and the units fit, is checked later."""

__all__ = []

import re

from ._common import MCPLError
from ._expr_ast import (
    Assign,
    Binary,
    Call,
    Compare,
    Edit,
    Float,
    In,
    Int,
    Logical,
    Name,
    Part,
    Particle,
    Quantity,
    Unary,
    Unit,
    Userdata,
    Value,
    Vector,
    _assign_ops,
    _binary_ops,
    _compare_ops,
    _power_ops,
    _unary_ops,
    _vector_parts,
)
from ._exprunits import _expr_units
from ._particles import _particle_names


def _expr_str2ast( text, kind = 'value' ):
    """The tree of the expression of a value (kind 'value', a Value), or of
    the statements of an edit expression (kind 'edit', an Edit, which can
    have none), without its inactive statements. Raises MCPLError for invalid
    syntax."""
    text = _expr_normalise(text)
    if kind == 'value':
        return Value(_parse(text,'eval'))
    statements = []
    for part, pos, inner in _statement_parts(text):
        st = _parse(part if inner is None else inner,'exec',( text, pos ))
        if inner is None:
            statements.append(st)
    return Edit(tuple(statements))

def _expr_statements( text ):
    """The statements of an edit expression, as (text, active), where the text
    of an inactive statement is the statement in inactive(..)"""
    return [ ( part if inner is None else inner, inner is None )
             for part, _, inner in _statement_parts(_expr_normalise(text)) ]

def _statement_parts( text ):
    """The statements of the (normalised) text with their positions in it, and
    for inactive statements, inactive(STATEMENT), the statement (else None)"""
    res = []
    for part, pos in _split_statements(text):
        m = re.match(r'inactive\s*\(\s*',part)
        inner = part[m.end():-1].rstrip() if m and part.endswith(')') else None
        if inner is not None and _balanced(inner):
            res.append( ( part, pos + m.end(), inner ) )
        else:
            res.append( ( part, pos, None ) )
    return res

def _balanced( text ):
    """Whether the parentheses in the text are balanced"""
    depth = 0
    for c in text:
        depth += ( c == '(' ) - ( c == ')' )
        if depth < 0:
            return False
    return depth == 0

#Characters which can not be used in expressions (nor in the histogram strings
#of mcpltool -w and -t), although they are printable ASCII characters:
_forbidden_chars = '"\'{}[]#$`\\'

def _check_chars( text, what = 'expression' ):
    """Check that the text only has printable ASCII characters (and ASCII
    whitespace, including newlines), and none of the forbidden characters."""
    for c in text:
        if c in _forbidden_chars:
            raise MCPLError(f'The character {c} can not be used in {what}s'
                            f' (in "{_ascii_repr(text)}")')
        if not ( ' ' <= c <= '~' or c in '\t\n\r\f\v' ):
            raise MCPLError(f'Only printable ASCII characters can be used in'
                            f' {what}s (not U+{ord(c):04X}, in'
                            f' "{_ascii_repr(text)}")')

def _ascii_repr( text ):
    return text.encode('ascii','backslashreplace').decode('ascii')

def _expr_normalise( expr ):
    """Expression with all whitespace (including newlines, e.g. in long
    expressions written over several lines) normalised to single spaces."""
    if not isinstance(expr,str):
        raise MCPLError(f'Expressions must be strings (got {type(expr).__name__})')
    _check_chars(expr)
    return ' '.join(expr.split())

def _split_statements( expr ):
    """The statements separated by ";" (outside parentheses) of an edit
    expression, with their positions in it"""
    parts, depth, start = [], 0, 0
    for i, c in enumerate(expr):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        if c == ',' and depth == 0:
            raise MCPLError('Separate statements with ";"'
                            f' (not ","), in expression "{expr}"')
        if c == ';' and depth == 0:
            parts.append( ( expr[start:i], start ) )
            start = i + 1
    parts.append( ( expr[start:], start ) )
    return [ ( p.strip(), pos + len(p) - len(p.lstrip()) ) for p, pos in parts if p.strip() ]

#C-style operators, which give errors saying what to use instead:
_unsupported_ops = ( ( '&&', 'and', 'x > 0 and y > 0' ),
                     ( '||', 'or', 'x > 0 or y > 0' ),
                     ( '!', 'not', 'not (x > 0)' ),
                     ( '%', 'mod(a,b)', 'mod(userflags,4) == 1' ) )

def _check_ops( expr ):
    #NB: Do not add support for these: ! and % break command lines in some
    #shells (bash history expansion, Windows batch files).
    if '~' in expr:
        raise MCPLError('The operator ~ is not supported in expressions (e.g.'
                        ' "(userflags & 0x10) == 0" tests that a bit is not set),'
                        f' in expression "{expr}"')
    for op, alt, example in _unsupported_ops:
        found = ( re.search(r'!(?!=)',expr) if op == '!' else op in expr )
        if found:
            raise MCPLError(f'Use "{alt}" instead of "{op}" in expressions (e.g.'
                            f' "{example}"), in expression "{expr}"')

def _parse( expr, mode, context = None ):
    """Parse an expression (mode 'eval') or a statement (mode 'exec'). For a
    statement of an edit expression, context is (the whole text, the
    position of the statement in it), for messages."""
    _check_ops(expr)
    try:
        return _Parser(expr).parse(mode)
    except _SyntaxError as e:
        text, pos = ( expr, e.pos ) if context is None else ( context[0], context[1] + e.pos )
        hint = ( ' (use == for comparisons)'
                 if mode == 'eval' and re.search(r'(?<![=<>!])=(?!=)',expr) else '' )
        raise MCPLError(f'Syntax error in expression "{text}", {_where(text,pos)}:'
                        f' {e.what}{hint}') from None

def _where( expr, pos ):
    """Where the position pos in the expression is, for messages: at the start,
    at the end, or after the text before it (the end of it, if it is long)"""
    before = expr[:pos].rstrip()
    if not before:
        return 'at the start'
    if not expr[pos:].strip():
        return 'at the end'
    if len(before) > 30:
        before = '...' + before[-27:]
    return f'after "{before}"'

class _SyntaxError(Exception):
    """A syntax error at the position pos of the expression, with a short
    description (what)"""
    def __init__( self, pos, what ):
        super().__init__(what)
        self.pos, self.what = pos, what

#The numbers: decimal and hexadecimal integers, and floating point numbers:
_int_forms = r'0|[1-9][0-9]*|0[xX][0-9a-fA-F]+'
_number_forms = ( _int_forms + r'|([0-9]+\.[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?|[0-9]+[eE][-+]?[0-9]+' )
#The tokens: numbers (as anything starting like a number which continues
#with "_", or 0x, 0o, and 0b, so _Parser._number can say what is wrong),
#names, and the operators (the longest first):
_token_regex = re.compile( r'(?P<space>\s+)'
                           r'|(?P<number>0[xXoObB][0-9A-Za-z_]*'
                           r'|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?(?:_[0-9A-Za-z_.]*|\.[0-9][0-9A-Za-z_.]*)?)'
                           r'|(?P<name>[A-Za-z_][A-Za-z_0-9]*)'
                           r'|(?P<op>//=|\*\*=|//|\*\*|==|!=|<=|>=|[-+*/^&|]=|[-+*/^&|<>=(),.;:])' )
#(the binary operators of each precedence, from the lowest):
_op_levels = [ tuple( s for s, p in _binary_ops.items() if p == prec )
               for prec in sorted(set(_binary_ops.values())) ]

class _Parser:
    """Parser of expressions and statements. The precedences are, from the
    lowest: or, and, not, comparisons (which can be chained, as in
    0 < x < 2cm, and "in" or "not in" a list of integers or particle names,
    as in pdgcode in (neutron,gamma), which can not), |, &, + and -, *, / and //,
    unary - and +, the multiplication by a unit directly after a number or a
    closing parenthesis (as in 25meV or 2^(ekin/MeV)MeV), and ^ (or **, which
    is right-associative, with unary - and + allowed in exponents). Units are
    values (MeV is 1MeV), and a power directly after a unit applies to the
    unit only (as in 4cm^2 or cm^(1/2)), and must be a constant."""
    def __init__( self, expr ):
        self._expr = expr
        #(the tokens, as (kind, text), with their positions in the expression):
        self._toks, self._pos = [], []
        pos = 0
        while pos < len(expr):
            m = _token_regex.match(expr,pos)
            if m is None:
                raise _SyntaxError(pos,f'"{expr[pos]}" can not be used here')
            kind = m.lastgroup
            if kind != 'space':
                self._toks.append( ( kind, m.group() ) )
                self._pos.append(pos)
            pos = m.end()
        self._i = 0

    def parse( self, mode ):
        node = self._statement() if mode == 'exec' else self._expression()
        if self._i != len(self._toks):
            kind, s = self._peek()
            missing = kind in ( 'name', 'number' ) or ( kind, s ) == ( 'op', '(' )
            raise self._error('an operator is missing' if missing else f'unexpected "{s}"')
        return node

    #Tokens:

    def _error( self, what ):
        """The syntax error at the next token (or at the end)"""
        pos = self._pos[self._i] if self._i < len(self._pos) else len(self._expr)
        return _SyntaxError(pos,what)

    def _peek( self, k = 0 ):
        i = self._i + k
        return self._toks[i] if i < len(self._toks) else ( None, None )

    def _take( self ):
        if self._i >= len(self._toks):
            raise self._error('a value is missing')
        self._i += 1
        return self._toks[self._i-1]

    def _accept( self, kind, *strings ):
        t = self._peek()
        if t[0] == kind and t[1] in strings:
            self._i += 1
            return t[1]
        return None

    def _expect( self, kind, string ):
        if not self._accept(kind,string):
            t = self._peek()
            raise self._error(f'"{string}" is missing' if t[0] is None
                              else f'"{string}" is expected, not "{t[1]}"')

    #Statements (of edit expressions):

    def _statement( self ):
        name, op = self._peek(), self._peek(1)
        if name == ( 'name', 'userdata' ) and op == ( 'op', '.' ):
            #(an assignment after userdata.NAME, or after the 8 tokens of
            #userdata.NAME.at(INDEX)):
            nxt = self._peek(8 if self._peek(3) == ( 'op', '.' ) else 3)
            if nxt[0] == 'op' and nxt[1] in _assign_ops:
                raise self._error('fields of the userdata can not be changed')
        if name[0] == 'name' and op[0] == 'op' and op[1] in _assign_ops:
            self._i += 2
            return Assign(name[1],_assign_ops[op[1]],self._expression())
        return self._expression()

    #Expressions, by precedence (from the lowest):

    def _expression( self ):
        return self._logical('or',self._and)

    def _and( self ):
        return self._logical('and',self._not)

    def _logical( self, word, sub ):
        values = [ sub() ]
        while self._accept('name',word):
            values.append(sub())
        return values[0] if len(values) == 1 else Logical(word,tuple(values))

    def _not( self ):
        if self._accept('name','not'):
            return Unary('not',self._not())
        return self._comparison()

    def _comparison( self ):
        first, ops, values = self._binary(), [], []
        while ( op := self._accept('op',*_compare_ops) ):
            ops.append(op)
            values.append(self._binary())
        if self._peek() == ( 'name', 'in' ) or ( self._peek() == ( 'name', 'not' )
                                                 and self._peek(1) == ( 'name', 'in' ) ):
            if ops:
                raise self._error('"in" can not be used in a chain of comparisons')
            negated = bool(self._accept('name','not'))
            self._take()
            self._expect('op','(')
            values = [ self._in_value() ]
            while self._accept('op',','):
                values.append(self._in_value())
            self._expect('op',')')
            if self._peek()[0] == 'op' and self._peek()[1] in _compare_ops:
                raise self._error('"in" can not be used in a chain of comparisons')
            return In(first,negated,tuple(values))
        return Compare(first,tuple(ops),tuple(values)) if ops else first

    def _in_value( self ):
        """A value in the list after "in": an integer (with an optional sign)
        or the name of a particle"""
        sign = self._accept('op',*_unary_ops)
        kind, s = self._peek()
        res = None
        if kind == 'number' and re.fullmatch(_int_forms,s):
            n = self._number(s)
            res = Int(-n.value if sign == '-' else n.value,n.hex)
        elif kind == 'name' and s in _particle_names and not sign:
            res = Particle(s)
        if res is not None:
            self._i += 1
        if res is None or self._peek() not in ( ( 'op', ',' ), ( 'op', ')' ) ):
            raise self._error('the values after "in" must be integers or names of particles,'
                              ' as in pdgcode in (neutron,gamma) or userflags in (1,2)')
        return res

    def _binary( self, level = 0 ):
        #(the left-associative binary operators, from the lowest precedence):
        if level == len(_op_levels):
            return self._unary()
        node = self._binary(level+1)
        while ( op := self._accept('op',*_op_levels[level]) ):
            node = Binary(op,node,self._binary(level+1))
        return node

    def _unary( self ):
        if ( op := self._accept('op',*_unary_ops) ):
            return Unary(op,self._unary())
        return self._implied()

    def _implied( self ):
        node = self._power()
        prev, nxt = self._toks[self._i-1], self._peek()
        if ( nxt[0] == 'name' and nxt[1] in _expr_units and not isinstance(node,Unit)
             and ( prev[0] == 'number' or prev == ( 'op', ')' ) ) ):
            unit = self._unit()
            if isinstance(node,(Int,Float)):
                return Quantity(node,unit.unit,unit.power)
            node = Binary('*',node,unit)
        return node

    def _power( self ):
        base = self._parts(self._primary())
        if self._accept('op',*_power_ops):
            return Binary('^',base,self._exponent())
        return base

    def _exponent( self ):
        #(unary operators are allowed in exponents, as in 2^-x):
        if ( op := self._accept('op',*_unary_ops) ):
            return Unary(op,self._exponent())
        return self._power()

    def _primary( self ):
        if self._i >= len(self._toks):
            raise self._error('a value is missing')
        err = self._error('a value is expected, not "{}"')
        kind, s = self._take()
        if kind == 'number':
            return self._number(s)
        if kind == 'op' and s == '(':
            node = self._expression()
            if self._accept('op',','):
                #(a vector, of two or three values):
                elts = [ node, self._expression() ]
                while self._accept('op',','):
                    elts.append(self._expression())
                self._expect('op',')')
                if len(elts) > 3:
                    raise self._error('vectors have two or three values')
                return Vector(tuple(elts))
            self._expect('op',')')
            return node
        if kind != 'name' or s in ( 'and', 'or', 'not' ):
            err.what = err.what.format(s)
            raise err
        if s in _expr_units:
            self._i -= 1
            return self._unit()
        if self._accept('op','('):
            args = []
            if not self._accept('op',')'):
                args.append(self._expression())
                while self._accept('op',','):
                    args.append(self._expression())
                self._expect('op',')')
            return Call(s,tuple(args))
        if s == 'userdata' and self._peek() == ( 'op', '.' ):
            return self._userdata()
        return Particle(s) if s in _particle_names else Name(s)

    def _parts( self, node ):
        """The value of a vector, as in pos.x or pos.at(0) (counting from 0)"""
        while self._accept('op','.'):
            kind, name = self._peek()
            if kind == 'name' and name in _vector_parts:
                self._i += 1
                index = _vector_parts.index(name)
            elif kind == 'name' and name == 'at':
                self._i += 1
                index = self._at_index('a value of a vector')
            else:
                raise self._error('the values of vectors are written as .x, .y, .z or'
                                  ' .at(INDEX) (as in pos.x or pos.at(0))')
            node = Part(node,index)
        return node

    def _userdata( self ):
        """A field of the userdata (after the name userdata), as userdata.NAME,
        or userdata.NAME.at(INDEX) for a value of an array (counting from 0)"""
        self._take()#(the ".")
        kind, field = self._peek()
        if kind != 'name':
            raise self._error('the name of a userdata field is missing')
        self._i += 1
        if not self._accept('op','.'):
            return Userdata(field)
        if not self._accept('name','at'):
            raise self._error('values of arrays in the userdata are written as'
                              ' userdata.NAME.at(INDEX)')
        return Userdata(field,self._at_index('a value in an array'))

    def _at_index( self, what ):
        """The index of .at(INDEX) (after "at"), of what (for errors)"""
        self._expect('op','(')
        kind, index = self._peek()
        if kind != 'number' or not index.isdigit():
            raise self._error(f'the index of {what} must be a whole number (counting from 0)')
        self._i += 1
        self._expect('op',')')
        return int(index)

    def _number( self, s ):
        """A number: a decimal integer, a hexadecimal one (like 0x1f), or a
        floating point number (like 0.5, .5, 5., or 1e-3), all as in C"""
        if re.fullmatch(_number_forms,s):
            if s[:2] in ( '0x', '0X' ):
                return Int(int(s,16),hex = True)
            return Int(int(s)) if s.isdigit() else Float(float(s))
        if s[:1] == '0' and s.isdigit():
            hint = ' (integers can not start with 0)'
        elif '_' in s:
            hint = ' (numbers can not contain "_")'
        elif re.fullmatch(r'0[oObB][0-9a-fA-F]*',s):
            hint = ' (only decimal and hexadecimal numbers, like 0x1f, can be used)'
        else:
            hint = ''
        raise MCPLError(f'Invalid number {s}{hint} in expression "{self._expr}"')

    #Units:

    def _unit( self ):
        _, name = self._take()
        power = 1
        if self._accept('op',*_power_ops):
            power = self._unit_power()
        return Unit(name,power)

    def _unit_power( self ):
        sign = 1
        while ( op := self._accept('op','-','+') ):
            sign = -sign if op == '-' else sign
        err = self._error('the power of a unit must be a number, like cm^2 or cm^(1/2)')
        if self._i >= len(self._toks):
            raise err
        kind, s = self._take()
        if kind == 'number':
            v = self._number(s).value
        elif ( kind, s ) == ( 'op', '(' ):
            v = self._constant(self._expression())
            self._expect('op',')')
        else:
            raise err
        v = sign * v
        if 2 * v != round(2 * v):
            raise MCPLError('Units can only have whole or half powers (like cm^2 or'
                            f' cm^0.5), in expression "{self._expr}"')
        return int(v) if float(v).is_integer() else float(v)

    def _constant( self, node ):
        """Value of a constant power of a unit, like (1/2)"""
        if isinstance(node,(Int,Float)):
            return node.value
        if isinstance(node,Unary) and node.op in _unary_ops:
            v = self._constant(node.operand)
            return -v if node.op == '-' else v
        ops = { '+' : lambda a, b : a + b, '-' : lambda a, b : a - b,
                '*' : lambda a, b : a * b, '/' : lambda a, b : a / b }
        if isinstance(node,Binary) and node.op in ops:
            try:
                return ops[node.op](self._constant(node.left),self._constant(node.right))
            except ZeroDivisionError:
                pass
        raise MCPLError('Powers of units must be numbers (like cm^2 or cm^(1/2)), in'
                        f' expression "{self._expr}"')
