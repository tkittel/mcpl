
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

"""The syntax of particle expressions (see _expressions): their units, the
parser giving trees of ast nodes, and the writer of their (normalised)
texts."""

__all__ = []

import ast
import math
import re

from ._common import MCPLError

#Dimensions (length,energy,time) and units of quantities in expressions. Values
#are internally in the units of MCPL (cm, MeV, ms), also for wavelengths:
_dim_none = (0,0,0)
_dim_L, _dim_E, _dim_T = (1,0,0), (0,1,0), (0,0,1)
_expr_units = { 'meV' : (1e-9,_dim_E), 'eV' : (1e-6,_dim_E),
                'keV' : (1e-3,_dim_E), 'MeV' : (1.0,_dim_E),
                'GeV' : (1e3,_dim_E), 'TeV' : (1e6,_dim_E),
                'ns' : (1e-6,_dim_T), 'us' : (1e-3,_dim_T),
                'ms' : (1.0,_dim_T), 's' : (1e3,_dim_T),
                'Aa' : (1e-8,_dim_L), 'nm' : (1e-7,_dim_L),
                'um' : (1e-4,_dim_L), 'mm' : (0.1,_dim_L),
                'cm' : (1.0,_dim_L), 'm' : (100.0,_dim_L),
                'km' : (1e5,_dim_L),
                'deg' : (math.pi/180,None), 'rad' : (1.0,None) }
#C-style operators, which give errors saying what to use instead:
_expr_unsupported_ops = ( ( '&&', 'and', 'x > 0 and y > 0' ),
                          ( '||', 'or', 'x > 0 or y > 0' ),
                          ( '!', 'not', 'not (x > 0)' ),
                          ( '%', 'mod(a,b)', 'mod(userflags,4) == 1' ) )

def _expr_check_ops( expr ):
    #NB: Do not add support for these: ! and % break command lines in some
    #shells (bash history expansion, Windows batch files).
    for op, alt, example in _expr_unsupported_ops:
        found = ( re.search(r'!(?!=)',expr) if op == '!' else op in expr )
        if found:
            raise MCPLError(f'Use "{alt}" instead of "{op}" in expressions (e.g.'
                            f' "{example}"), in expression "{expr}"')

def _expr_parse( expr, mode = 'eval', context = None ):
    """Parse an expression (mode 'eval') or an edit statement (mode 'exec') to
    a tree of ast nodes, with _ExprParser. For a statement of an edit, context
    is (the edit, the position of the statement in it), for messages."""
    _expr_check_ops(expr)
    try:
        return _ExprParser(expr).parse(mode)
    except _ExprSyntaxError as e:
        text, pos = ( expr, e.pos ) if context is None else ( context[0], context[1] + e.pos )
        hint = ( ' (use == for comparisons)'
                 if mode == 'eval' and re.search(r'(?<![=<>!])=(?!=)',expr) else '' )
        raise MCPLError(f'Syntax error in expression "{text}", {_expr_where(text,pos)}:'
                        f' {e.what}{hint}') from None

def _expr_where( expr, pos ):
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

class _Unit(ast.expr):
    """A unit with a power (e.g. cm^2) in a parsed expression, standing for its
    value (as 1cm^2 would)"""
    _fields = ( 'unit', 'power' )

class _ExprSyntaxError(Exception):
    """A syntax error at the position pos of the expression, with a short
    description (what)"""
    def __init__( self, pos, what ):
        super().__init__(what)
        self.pos, self.what = pos, what

#The operators, with their nodes, for the parser and the writer, and their
#precedences (higher binds tighter):
_prec_or, _prec_and, _prec_not, _prec_cmp = 1, 2, 3, 4
_prec_unary, _prec_implied, _prec_power, _prec_atom = 10, 10.5, 11, 12
_op_bool = { 'or' : ( ast.Or, _prec_or ), 'and' : ( ast.And, _prec_and ) }
#(left-associative):
_op_binary = { '|' : ( ast.BitOr, 5 ), '&' : ( ast.BitAnd, 6 ), '+' : ( ast.Add, 8 ),
               '-' : ( ast.Sub, 8 ), '*' : ( ast.Mult, 9 ), '/' : ( ast.Div, 9 ),
               '//' : ( ast.FloorDiv, 9 ) }
#(right-associative, written as ^):
_op_power = ( '^', '**' )
_op_cmp = { '==' : ast.Eq, '!=' : ast.NotEq, '<' : ast.Lt, '<=' : ast.LtE, '>' : ast.Gt,
            '>=' : ast.GtE }
_op_unary = { '-' : ast.USub, '+' : ast.UAdd, '~' : ast.Invert }
_op_assign = { **{ f'{s}=' : cls for s, ( cls, _ ) in _op_binary.items() },
               **{ f'{s}=' : ast.Pow for s in _op_power } }
#(the binary operators of each precedence, from the lowest):
_op_levels = [ { s : cls for s, ( cls, p ) in _op_binary.items() if p == prec }
               for prec in sorted({ p for _, p in _op_binary.values() }) ]
#(the symbols and precedences of the nodes):
_op_of_node = { cls : ( s, p ) for s, ( cls, p ) in ( *_op_bool.items(), *_op_binary.items() ) }
_op_of_node[ast.Pow] = ( _op_power[0], _prec_power )
_op_of_node.update( { cls : ( s, None ) for s, cls in ( *_op_cmp.items(), *_op_unary.items() ) } )

class _ExprParser:
    """Parser of expressions and edit statements, reading the tokens of Python
    (with tokenize) and giving trees of ast nodes. The precedences are, from
    the lowest: or, and, not, comparisons (which can be chained, as in
    0 < x < 2cm, and "in" or "not in" a list of values, as in
    pdgcode in (neutron,gamma), which can not), |, &, + and -, * and / and //, unary - + ~, the multiplication
    by a unit directly after a number or a closing parenthesis (as in 25meV or
    2^(ekin/MeV)MeV), and ^ (or **, which is right-associative, with unary
    - + ~ allowed in exponents). Units are values (MeV is 1MeV), and a power
    directly after a unit applies to the unit only (as in 4cm^2 or cm^(1/2)),
    and must be a constant."""
    def __init__( self, expr ):
        import io
        import tokenize
        self._expr = expr
        self._toks = []
        skip = ( tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER, tokenize.INDENT,
                 tokenize.DEDENT )
        kinds = { tokenize.OP : 'op', tokenize.NAME : 'name', tokenize.NUMBER : 'number' }
        #(the tokens, with their positions in the expression, which has no
        #newlines):
        self._pos = []
        try:
            for t in tokenize.generate_tokens(io.StringIO(expr).readline):
                if t.type in skip:
                    continue
                if t.type == tokenize.ERRORTOKEN and t.string.isspace():
                    continue#(Python before 3.12 gives spaces before unknown characters)
                if ( t.type == tokenize.ERRORTOKEN and len(t.string) == 1
                     and t.string not in '"\'' ):
                    t = t._replace(type = tokenize.OP)#(as from Python 3.12)
                if t.type not in kinds:
                    raise _ExprSyntaxError(t.start[1],f'"{t.string}" can not be used here')
                self._toks.append( ( kinds[t.type], t.string ) )
                self._pos.append(t.start[1])
        except tokenize.TokenError:
            #(with parentheses which do not match: an unmatched ")", or else a
            #missing one at the end):
            depth = 0
            for ( kind, t ), pos in zip(self._toks,self._pos):
                depth += { '(' : 1, ')' : -1 }.get(t,0) if kind == 'op' else 0
                if depth < 0:
                    raise _ExprSyntaxError(pos,'unexpected ")"') from None
            raise _ExprSyntaxError(len(expr),'")" is missing') from None
        except SyntaxError as e:
            raise _ExprSyntaxError(max( 0, ( e.offset or 1 ) - 1 ),'invalid text') from None
        self._i = 0

    def parse( self, mode ):
        node = self._statement() if mode == 'exec' else self._expression()
        if self._i != len(self._toks):
            kind, s = self._peek()
            missing = kind in ( 'name', 'number' ) or ( kind, s ) == ( 'op', '(' )
            raise self._error('an operator is missing' if missing else f'unexpected "{s}"')
        if mode == 'exec':
            return ast.Module( body = [ node ], type_ignores = [] )
        return ast.Expression( body = node )

    #Tokens:

    def _error( self, what ):
        """The syntax error at the next token (or at the end)"""
        pos = self._pos[self._i] if self._i < len(self._pos) else len(self._expr)
        return _ExprSyntaxError(pos,what)

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

    #Statements (of edits):

    def _statement( self ):
        name, op = self._peek(), self._peek(1)
        if name == ( 'name', 'userdata' ) and op == ( 'op', '.' ):
            #(an assignment after userdata.NAME, or after the 8 tokens of
            #userdata.NAME.at(INDEX)):
            nxt = self._peek(8 if self._peek(3) == ( 'op', '.' ) else 3)
            if nxt[0] == 'op' and ( nxt[1] == '=' or nxt[1] in _op_assign ):
                raise self._error('fields of the userdata can not be changed')
        if name[0] == 'name' and op[0] == 'op' and ( op[1] == '=' or op[1] in _op_assign ):
            self._i += 2
            target = ast.Name( id = name[1], ctx = ast.Store() )
            value = self._expression()
            if op[1] == '=':
                return ast.Assign( targets = [ target ], value = value )
            return ast.AugAssign( target = target, op = _op_assign[op[1]](), value = value )
        return ast.Expr( value = self._expression() )

    #Expressions, by precedence (from the lowest):

    def _expression( self ):
        return self._boolop('or',self._and)

    def _and( self ):
        return self._boolop('and',self._not)

    def _boolop( self, word, sub ):
        values = [ sub() ]
        while self._accept('name',word):
            values.append(sub())
        if len(values) == 1:
            return values[0]
        return ast.BoolOp( op = _op_bool[word][0](), values = values )

    def _not( self ):
        if self._accept('name','not'):
            return ast.UnaryOp( op = ast.Not(), operand = self._not() )
        return self._comparison()

    def _comparison( self ):
        left, ops, rights = self._binary(), [], []
        while ( op := self._accept('op',*_op_cmp) ):
            ops.append(_op_cmp[op]())
            rights.append(self._binary())
        if self._peek() == ( 'name', 'in' ) or ( self._peek() == ( 'name', 'not' )
                                                 and self._peek(1) == ( 'name', 'in' ) ):
            if ops:
                raise self._error('"in" can not be used in a chain of comparisons')
            op = ast.NotIn() if self._accept('name','not') else ast.In()
            self._take()
            self._expect('op','(')
            values = [ self._expression() ]
            while self._accept('op',','):
                values.append(self._expression())
            self._expect('op',')')
            if self._peek()[0] == 'op' and self._peek()[1] in _op_cmp:
                raise self._error('"in" can not be used in a chain of comparisons')
            return ast.Compare( left = left, ops = [ op ],
                                comparators = [ ast.Tuple( elts = values, ctx = ast.Load() ) ] )
        return ast.Compare( left = left, ops = ops, comparators = rights ) if ops else left

    def _binary( self, level = 0 ):
        #(the left-associative binary operators, from the lowest precedence):
        if level == len(_op_levels):
            return self._unary()
        ops = _op_levels[level]
        node = self._binary(level+1)
        while ( op := self._accept('op',*ops) ):
            node = ast.BinOp( left = node, op = ops[op](), right = self._binary(level+1) )
        return node

    def _unary( self ):
        if ( op := self._accept('op',*_op_unary) ):
            return ast.UnaryOp( op = _op_unary[op](), operand = self._unary() )
        return self._implied()

    def _implied( self ):
        node = self._power()
        prev, nxt = self._toks[self._i-1], self._peek()
        if ( nxt[0] == 'name' and nxt[1] in _expr_units and not isinstance(node,_Unit)
             and ( prev[0] == 'number' or prev == ( 'op', ')' ) ) ):
            node = ast.BinOp( left = node, op = ast.Mult(), right = self._unit() )
        return node

    def _power( self ):
        base = self._primary()
        if self._accept('op',*_op_power):
            return ast.BinOp( left = base, op = ast.Pow(), right = self._exponent() )
        return base

    def _exponent( self ):
        #(unary operators are allowed in exponents, as in 2^-x):
        if ( op := self._accept('op',*_op_unary) ):
            return ast.UnaryOp( op = _op_unary[op](), operand = self._exponent() )
        return self._power()

    def _primary( self ):
        if self._i >= len(self._toks):
            raise self._error('a value is missing')
        err = self._error('a value is expected, not "{}"')
        kind, s = self._take()
        if kind == 'number':
            return ast.Constant( value = self._number(s) )
        if kind == 'op' and s == '(':
            node = self._expression()
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
            return ast.Call( func = ast.Name( id = s, ctx = ast.Load() ), args = args,
                             keywords = [] )
        if self._peek() == ( 'op', '.' ):
            if s != 'userdata':
                raise self._error('"." can only be used for fields of the userdata'
                                  ' (as userdata.NAME)')
            return self._userdata()
        return ast.Name( id = s, ctx = ast.Load() )

    def _userdata( self ):
        """A field of the userdata (after the name userdata), as one name
        "userdata.NAME", or "userdata.NAME.at(INDEX)" for a value of an array
        (counting from 0), see _ExprEvaluator.name"""
        self._take()#(the ".")
        kind, field = self._peek()
        if kind != 'name':
            raise self._error('the name of a userdata field is missing')
        self._i += 1
        if not self._accept('op','.'):
            return ast.Name( id = f'userdata.{field}', ctx = ast.Load() )
        if not self._accept('name','at'):
            raise self._error('values of arrays in the userdata are written as'
                              ' userdata.NAME.at(INDEX)')
        self._expect('op','(')
        kind, index = self._peek()
        if kind != 'number' or not index.isdigit():
            raise self._error('the index of a value in an array must be a whole number'
                              ' (counting from 0)')
        self._i += 1
        self._expect('op',')')
        return ast.Name( id = f'userdata.{field}.at({int(index)})', ctx = ast.Load() )

    def _number( self, s ):
        v = ast.literal_eval(s)
        if not isinstance(v,(int,float)):
            raise MCPLError(f'Unsupported value in expression "{self._expr}"')
        return v

    #Units:

    def _unit( self ):
        _, name = self._take()
        power = 1
        if self._accept('op',*_op_power):
            power = self._unit_power()
        return _Unit( unit = name, power = power )

    def _unit_power( self ):
        sign = 1
        while ( op := self._accept('op','-','+') ):
            sign = -sign if op == '-' else sign
        err = self._error('the power of a unit must be a number, like cm^2 or cm^(1/2)')
        if self._i >= len(self._toks):
            raise err
        kind, s = self._take()
        if kind == 'number':
            v = self._number(s)
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
        if isinstance(node,ast.Constant):
            return node.value
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            v = self._constant(node.operand)
            return -v if isinstance(node.op,ast.USub) else v
        ops = { ast.Add : lambda a, b : a + b, ast.Sub : lambda a, b : a - b,
                ast.Mult : lambda a, b : a * b, ast.Div : lambda a, b : a / b }
        if isinstance(node,ast.BinOp) and type(node.op) in ops:
            try:
                return ops[type(node.op)](self._constant(node.left),self._constant(node.right))
            except ZeroDivisionError:
                pass
        raise MCPLError('Powers of units must be numbers (like cm^2 or cm^(1/2)), in'
                        f' expression "{self._expr}"')

def _expr_unparse( tree ):
    """Expression text (with the syntax of expressions) of a parsed tree (of an
    expression, or of the statements of an edit)"""
    return _ExprWriter().text(tree)

class _ExprWriter:
    """Writes the text of parsed expressions and edit statements (as read by
    _ExprParser), without spaces except around and, or and not, and with
    parentheses only where they are needed. Multiplications by units are
    written as implied multiplications where possible (as in 25meV)."""

    def text( self, node ):
        if isinstance(node,ast.Module):
            return ';'.join( self.text(st) for st in node.body )
        if isinstance(node,ast.Expression):
            return self.text(node.body)
        if isinstance(node,ast.Expr):
            return self.text(node.value)
        if isinstance(node,ast.Assign):
            return f'{node.targets[0].id}={self.text(node.value)}'
        if isinstance(node,ast.AugAssign):
            return f'{node.target.id}{_op_of_node[type(node.op)][0]}={self.text(node.value)}'
        return self._write(node)[0]

    def _sub( self, node, minprec ):
        t, prec = self._write(node)
        return t if prec >= minprec else f'({t})'

    def _exponent( self, node ):
        #(unary operators are allowed in exponents, but not multiplications by
        #units, which bind less tightly than ^):
        if isinstance(node,ast.UnaryOp) and not isinstance(node.op,ast.Not):
            return _op_of_node[type(node.op)][0] + self._exponent(node.operand)
        return self._sub(node,_prec_power)

    def _write( self, node ):
        """(text, precedence)"""
        if isinstance(node,ast.Constant):
            return repr(node.value), _prec_atom
        if isinstance(node,ast.Name):
            return node.id, _prec_atom
        if isinstance(node,_Unit):
            return node.unit + ( '' if node.power == 1 else f'^{node.power!r}' ), _prec_atom
        if isinstance(node,ast.Call):
            return f'{node.func.id}(' + ','.join( self._sub(a,0) for a in node.args ) + ')', _prec_atom
        if isinstance(node,ast.BoolOp):
            op, prec = _op_of_node[type(node.op)]
            return f' {op} '.join( self._sub(v,prec) for v in node.values ), prec
        if isinstance(node,ast.UnaryOp):
            if isinstance(node.op,ast.Not):
                return 'not ' + self._sub(node.operand,_prec_not), _prec_not
            return _op_of_node[type(node.op)][0] + self._sub(node.operand,_prec_unary), _prec_unary
        if isinstance(node,ast.Compare) and isinstance(node.ops[0],(ast.In,ast.NotIn)):
            values = ','.join( self._sub(e,0) for e in node.comparators[0].elts )
            op = ' not in ' if isinstance(node.ops[0],ast.NotIn) else ' in '
            return self._sub(node.left,_prec_cmp+1) + f'{op}({values})', _prec_cmp
        if isinstance(node,ast.Compare):
            t = self._sub(node.left,_prec_cmp+1)
            for op, right in zip(node.ops,node.comparators):
                t += _op_of_node[type(op)][0] + self._sub(right,_prec_cmp+1)
            return t, _prec_cmp
        if isinstance(node,ast.BinOp):
            implied = self._implied(node)
            if implied is not None:
                return implied, _prec_implied
            op, prec = _op_of_node[type(node.op)]
            if isinstance(node.op,ast.Pow):
                #(right-associative):
                return self._sub(node.left,_prec_atom) + op + self._exponent(node.right), prec
            return self._sub(node.left,prec) + op + self._sub(node.right,prec+1), prec
        raise MCPLError(f'Can not write expression with {type(node).__name__}')

    def _implied( self, node ):
        """Text of a multiplication by a unit written as an implied
        multiplication (as in 25meV), if it can be (after a number or a closing
        parenthesis), else None"""
        if not ( isinstance(node.op,ast.Mult) and isinstance(node.right,_Unit) ):
            return None
        if isinstance(node.left,_Unit) or ( isinstance(node.left,ast.BinOp) and
                                            isinstance(node.left.right,_Unit) ):
            return None#(e.g. 2cm^-1*cm, not (2cm^-1)cm)
        left = self._sub(node.left,_prec_power)
        last = node.left
        while not left.endswith(')') and isinstance(last,(ast.BinOp,ast.UnaryOp)):
            #(the last token of the left side):
            last = last.right if isinstance(last,ast.BinOp) else last.operand
        if not ( left.endswith(')') or isinstance(last,ast.Constant) ):
            return None
        return left + self._write(node.right)[0]
