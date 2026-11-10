
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

"""Encoding and decoding of stat:sum: comments."""

__all__ = ['encode_stat_sum', 'is_valid_stat_sum_key']

from ._common import MCPLError, _particle_range


def encode_stat_sum( key, value ):
    """
    Function which can help encode a key and value into the special format
    needed for "stat:sum:..." comments in MCPL headers. A value of either None
    or -1.0 maps to -1.0 in the encoding.
    """
    import math
    if hasattr(key,'decode'):
        key = key.decode('ascii')
    value = float(-1.0 if value is None else value)
    if math.isnan(value):
        raise MCPLError('Invalid value for "stat:sum:...". Value is invalid (NaN)')
    if math.isinf(value):
        raise MCPLError('Invalid value for "stat:sum:...". Value is invalid'
                        f' ({"+" if value > 0 else "-"}INF).')
    if not ( value >= 0.0 or value == -1.0 ):
        raise MCPLError('Invalid value for "stat:sum:...". Value is negative'
                        f' but is not -1.0 (it is {value:.15g}).')
    if not key:
        raise MCPLError('stat:sum: key must not be empty')
    if len(key) > 64:
        raise MCPLError(f'stat:sum: key "{key}" too long ({len(key)} chars,'
                        ' max 64 allowed)')
    if not is_valid_stat_sum_key(key):
        raise MCPLError(f'Invalid stat:sum: key "{key}" (must begin with a'
                        ' letter and otherwise only contain alphanumeric'
                        ' characters and underscores)')
    v = f'{value:24.15g}'
    if float(v)!=value:
        v = f'{value:24.17g}'
    return f'stat:sum:{key}:{v}'

def is_valid_stat_sum_key( key ):
    """
    Function which can be used to verify that a particular key has the correct
    format needed for "stat:sum:..." comments in MCPL headers.
    """
    if not ( ( 1<=len(key)<=64 ) and key.isascii() and key.isidentifier() ):
        return False
    k0 = key[0].lower()
    if hasattr(k0,'decode'):
        return b'a' <= k0 <= b'z'
    else:
        return 'a' <= k0 <= 'z'

def _statsum_problem( comment ):
    """The reason why a comment (bytes) starting with "stat:sum:" is not a
    valid stat:sum entry (as given by the C library), or None if it is one"""
    c = comment[len(b'stat:sum:'):]
    i = c.find(b':')
    if i < 0:
        return 'did not find colon separating key and value'
    key, v = c[:i], c[i+1:]
    if not key:
        return 'empty key'
    if len(key) > 64:
        return 'key length exceeds 64 characters'
    if not is_valid_stat_sum_key(key.decode('ascii','replace')):
        return 'key does not adhere to naming [a-zA-Z][a-zA-Z0-9_]*'
    if len(v) != 24:
        return 'value field is not exactly 24 characters wide'
    v = v.strip(b' ')
    if not v:
        return 'value field missing actual value'
    if not all( e in b'0123456789.-+eE' for e in v ):
        return ( 'value field holds forbidden characters, only'
                 ' 0123456789.-+eE are allowed in addition to leading'
                 ' or trailing spaces' )
    try:
        val = float(v)
    except ValueError:
        return 'could not decode contents of value field'
    import math
    if math.isnan(val):
        return 'value field holds forbidden value (NaN)'
    if not ( val >= 0.0 or val == -1.0 ):
        return 'value field must hold a non-negative value or -1'
    if math.isinf(val):
        return 'value field holds forbidden value (+INFINITY)'
    return None

def _statsum_syntax_error( comment ):
    """Error message for an invalid "stat:sum:..." comment (bytes), as given
    by the C library"""
    if len(comment) > 16 * ( 64 + 24 + len(b'stat:sum:') + 1 ):
        return ( 'Syntax error: could not properly decode comment '
                 'starting with "stat:sum:" (content too long to show)' )
    return ( 'Syntax error: could not properly decode comment starting'
             f' with "stat:sum:" ({_statsum_problem(comment)}). Issue with comment'
             f' "{comment.decode("utf-8","replace")}"' )

def _parse_statsum_comment( comment ):
    """(True, (key, value)) for a valid stat:sum comment (bytes), and
    otherwise (False, (None, None))"""
    if not comment.startswith(b'stat:sum:') or _statsum_problem(comment):
        return ( False, (None, None) )
    key, value = comment[len(b'stat:sum:'):].split(b':')
    return ( True, (key.decode('ascii'), float(value)) )

def _parse_statsum( comments ):
    """The stat:sum entries of the comments (bytes), as a dict of the values
    by key, with None for -1 (not available)"""
    d = {}
    for comment in comments:
        if not comment.startswith(b'stat:sum:'):
            continue
        ok, (key,val) = _parse_statsum_comment(comment)
        if not ok:
            raise MCPLError(_statsum_syntax_error(comment))
        if key in d:
            raise MCPLError('Duplicate stat:sum: key. The key '
                            f'"{key}" appears more than once in the file.')
        d[key] = None if val == -1.0 else val
    return d

def _statsum_scale( statsum, nparticles, skip, limit, edit ):
    """The factor by which mcpltool --extract scales the stat:sum entries
    (statsum) of a file of nparticles particles, for its particles in the
    range of skip and limit (None for all, see _as_limit), with the edit (a
    ParticleEdit, or None), and why, as (factor, reason): the fraction of the
    particles of the file in the range ('range'), -1 (not available) when the
    edit filters on the positions of the particles in the file ('fileidx') or
    the range is empty ('empty'), or None to keep them (None), see the
    guidelines for stat:sum entries"""
    if not any( v is not None for v in statsum.values() ):
        return None, None
    if edit is not None and edit.filters_on_fileidx:
        return -1.0, 'fileidx'
    first, end = _particle_range(nparticles,skip,limit)
    n = end - first
    if n == nparticles:
        return None, None
    return ( n / nparticles, 'range' ) if n else ( -1.0, 'empty' )
