
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

"""Histogram strings, as in mcpltool -H: an expression (or two separated by
":" for 2D histograms), followed by options NAME=VALUE separated by ";", like
"ekin/MeV;logx;bins=50"."""

__all__ = []

from ._common import MCPLError
from ._expressions import _dimstr, _range_value

#Options of histogram strings ("EXPR;logx;bins=50"), as NAME=VALUE, with the
#kinds of their values (bool: 1 or 0, auto: also auto):
_hist_options = { 'bins' : 'bins', 'range' : 'range', 'xrange' : 'range',
                  'yrange' : 'range', 'logx' : 'auto', 'logy' : 'auto',
                  'lethargy' : 'bool', 'split' : 'expr', 'groups' : 'count',
                  'bar' : 'count', 'unweighted' : 'bool', 'print' : 'bool' }
#The values of the options given without a value (as "logy" or "bar"):
_hist_implied = { 'logx' : '1', 'logy' : '1', 'lethargy' : '1', 'unweighted' : '1',
                  'print' : '1', 'bar' : 'auto' }
#(words for booleans, which are written 1 or 0):
_bool_words = ( 'true', 'false', 'on', 'off', 'yes', 'no' )

def _hist_bool( name, value, text, auto = False ):
    """The value of a boolean option (1 or 0, or auto if allowed)"""
    if value in ( '1', '0' ):
        return value == '1'
    if auto and value == 'auto':
        return 'auto'
    if value.lower() in _bool_words:
        raise MCPLError(f'Histogram options which are on or off are given as 1 or 0'
                        f' (not "{value}"), like {name}=1, in "{text}"')
    allowed = '1, 0 or auto' if auto else '1 or 0'
    raise MCPLError(f'Histogram option "{name}" must be {allowed} (not "{value}"),'
                    f' in "{text}"')

def _hist_count( name, value, text ):
    """The value of an option giving a number of curves or bars: a number of at
    least 2, or auto (None), or 0 for bar=0 (False)"""
    if value == 'auto':
        return None
    if name == 'bar' and value == '0':
        return False
    if value.isdigit() and int(value) >= 2:
        return int(value)
    off = ', or 0' if name == 'bar' else ''
    raise MCPLError(f'Histogram option "{name}" must be a number of at least 2 or auto{off}'
                    f' (not "{value}"), in "{text}"')

def _hist_defaults( exprs ):
    """The options of a histogram of the expressions (one, or two for 2D
    histograms) when none are given"""
    return { 'exprs' : list(exprs), 'bins' : None, 'range' : None, 'xrange' : None,
             'yrange' : None, 'logx' : False, 'logy' : None, 'lethargy' : False,
             'split' : None, 'unweighted' : False, 'print' : False, 'groups' : None,
             'bar' : False }

def _parse_hist( text ):
    """Parse a histogram string: an expression (or two separated by ":" for 2D
    histograms), followed by options NAME=VALUE separated by ";", like
    "ekin/MeV;logx;bins=50" or "x/cm : y/cm;xrange=-10:10". Returns a
    dict with the expressions (a list of one or two), and the options (with
    defaults for those not given)."""
    from ._expressions import _check_chars
    _check_chars(text,'histogram')
    parts = [ e.strip() for e in text.split(';') ]
    exprs = [ e.strip() for e in parts[0].split(':') ]
    if len(exprs) > 2 or not all(exprs):
        raise MCPLError(f'Histograms are of an expression, or two expressions'
                        f' separated by ":" for 2D histograms, in "{text}"')
    res = _hist_defaults(exprs)
    seen = set()
    for opt in parts[1:]:
        if not opt:
            continue
        name, eq, value = ( e.strip() for e in opt.partition('=') )
        if name not in _hist_options:
            raise MCPLError(f'Unknown histogram option "{name}" in "{text}"'
                            ' (the options are: ' + ', '.join(_hist_options) + ')')
        if name in seen:
            raise MCPLError(f'Histogram option "{name}" given more than once'
                            f' in "{text}"')
        seen.add(name)
        kind = _hist_options[name]
        if not eq and name in _hist_implied:
            value = _hist_implied[name]
        elif not ( eq and value ):
            raise MCPLError(f'Histogram option "{name}" needs a value, like {name}=...,'
                            f' in "{text}"')
        if kind in ( 'bool', 'auto' ):
            res[name] = _hist_bool(name,value,text,auto = kind == 'auto')
        elif kind == 'count':
            v = _hist_count(name,value,text)
            #(bar=auto is given as True):
            res[name] = True if ( name == 'bar' and v is None ) else v
        elif name == 'bins':
            nb = [ e.strip() for e in value.split(',') ]
            if ( len(nb) > len(exprs) or not all( e.isdigit() and int(e) > 0
                                                  for e in nb ) ):
                raise MCPLError(f'bins must be a positive integer (or two'
                                f' for 2D histograms, like bins=50,40) in "{text}"')
            res['bins'] = int(nb[0]) if len(nb) == 1 else tuple( int(e) for e in nb )
        elif name in ('range','xrange','yrange'):
            if ( name == 'range' ) != ( len(exprs) == 1 ):
                use = 'range' if len(exprs) == 1 else 'xrange and yrange'
                raise MCPLError(f'Histogram option "{name}" can only be used for'
                                f' {"2D" if len(exprs) == 1 else "1D"} histograms'
                                f' (use {use}), in "{text}"')
            res[name] = _as_range(value,name,text)
        else:
            res['split'] = value
    _check_hist_options(res,text)
    return res

def _check_hist_options( o, text ):
    """Check that the options o (see _parse_hist) of the histogram text can be
    used together"""
    if len(o['exprs']) == 2:
        for name in ('logx','logy','lethargy','split','bar'):
            if o[name]:
                raise MCPLError(f'Histogram option "{name}" can not be used'
                                f' for 2D histograms, in "{text}"')
    if o['bar'] is not False:
        for name in ('bins','range','logx','lethargy','split'):
            if o[name]:
                hint = ' (logy=1 gives a logarithmic scale of the bars)' if name == 'logx' else ''
                raise MCPLError(f'Histogram option "{name}" can not be used for bar'
                                f' charts{hint}, in "{text}"')
    if o['groups'] is not None and o['split'] is None:
        raise MCPLError(f'Histogram option "groups" can only be used with split, in "{text}"')

class _Range:
    """Range of an axis of a histogram: lo and hi in the units of MCPL, with
    the dimension dim (None for values without units)"""
    def __init__( self, lo, hi, dim ):
        self.lo, self.hi, self.dim = lo, hi, dim

def _as_range( rng, name = 'range', text = None ):
    """The _Range of a range given as text LOW:HIGH (with units for
    expressions with units, as in 0cm:10cm) or as a tuple (low,high) of numbers
    or texts (or None)"""
    if rng is None or isinstance(rng,_Range):
        return rng
    where = f', in "{text}"' if text else ''
    parts = rng.split(':') if isinstance(rng,str) else list(rng)
    try:
        if len(parts) != 2:
            raise ValueError
        values = [ _range_value(e) if isinstance(e,str) else ( float(e), None ) for e in parts ]
    except ( ValueError, TypeError, MCPLError ):
        values = None
    if values is not None:
        ( lo, dlo ), ( hi, dhi ) = values
        #(a plain 0 needs no units):
        dlo, dhi = ( dlo or ( dhi if lo == 0 else None ) ), ( dhi or ( dlo if hi == 0 else None ) )
    if values is None or dlo != dhi or not lo < hi:
        raise MCPLError(f'The {name} must be given as {name}=LOW:HIGH with LOW < HIGH'
                        f' (with units if the expression has units, as in {name}=0cm:10cm){where}')
    return _Range(lo,hi,dlo)

def _check_range( rng, vals, name ):
    """Check that the range has the units of the expression"""
    if rng is None or rng.dim == vals.dim:
        return
    if rng.dim is None:
        raise MCPLError(f'The {name} of "{vals.expression}" must be given with units, as'
                        f' it has units ({_dimstr(vals.dim)}), e.g. {name}=0cm:10cm')
    if vals.dim is None:
        raise MCPLError(f'The {name} of "{vals.expression}" must be given without units,'
                        ' as it has none')
    raise MCPLError(f'The {name} of "{vals.expression}" ({_dimstr(vals.dim)}) has'
                    f' other units ({_dimstr(rng.dim)})')

def _hist_key( text ):
    """Normalised form of a histogram string, for comparing them (the same
    for all strings giving the same histogram, e.g. with other whitespace or
    order of the options)"""
    from ._expressions import _expr_canonical
    o = _parse_hist(text)
    parts = [ ':'.join( _expr_canonical(e) for e in o['exprs'] ) ]
    for name in _hist_options:
        v = o[name]
        if v is None or v is False:
            continue
        if v is True:
            parts.append(name)#(the implied value, see _hist_implied)
        elif v == 'auto':
            parts.append(f'{name}=auto')
        elif name == 'split':
            parts.append(f'split={_expr_canonical(v)}')
        elif isinstance(v,_Range):
            #(the values, in the units of MCPL):
            parts.append(f'{name}={v.lo!r}:{v.hi!r}')
        else:
            parts.append(f'{name}={v!r}')
    return ';'.join(parts)

def _hist_with_args( expression, given ):
    """The options (as from _parse_hist) of a histogram of the expression,
    which can be a histogram string with options, and the options given as
    arguments (those which are not None or False)"""
    o = _parse_hist(expression) if isinstance(expression,str) else _hist_defaults([ expression ])
    for name, v in given.items():
        if v is None or v is False:
            continue
        if o[name] not in ( None, False ):
            raise MCPLError(f'The histogram option {name} can not be given'
                            ' both as an argument and in the expression'
                            f' "{expression}"')
        if name in ( 'bar', 'groups' ) and not ( ( v is True and name == 'bar' ) or
                                                 ( type(v) is int and v >= 2 ) ):
            what = 'True or a number' if name == 'bar' else 'a number'
            raise MCPLError(f'The histogram argument {name} must be {what} of at least 2'
                            f' (not {v!r})')
        o[name] = _as_range(v) if name == 'range' else v
    _check_hist_options(o,expression)
    return o
