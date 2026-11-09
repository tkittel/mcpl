
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

from ._common import MCPLError


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

def _statsum_syntax_error( comment ):
    """Error message for invalid "stat:sum:..." comment (bytes), with the same
    reasons as given by the C library"""
    def reason():
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
        return 'unknown issue'
    if len(comment) > 16 * ( 64 + 24 + len(b'stat:sum:') + 1 ):
        return ( 'Syntax error: could not properly decode comment '
                 'starting with "stat:sum:" (content too long to show)' )
    return ( 'Syntax error: could not properly decode comment starting'
             f' with "stat:sum:" ({reason()}). Issue with comment'
             f' "{comment.decode("utf-8","replace")}"' )

def _parse_statsum_comment( comment ):
    prefix = b'stat:sum:'
    lval = 24
    err = ( False, (None, None) )
    if not comment.startswith(prefix):
        return err
    c = comment[len(prefix):].split(b':')
    if ( len(c) != 2 or len(c[1])!=lval ):
        return err
    keyb, valstr = c
    key = keyb.decode('ascii',errors='ignore')
    if len(keyb) != len(key) or not is_valid_stat_sum_key(key):
        return err
    valstr = valstr.strip(b' ')#remove leading and trailing simple spaces
    if not all(e in b'0123456789.-+eE' for e in valstr):
        return err
    try:
        val = float(valstr)
    except ValueError:
        val = None
    import math
    if ( val is None or math.isinf(val) or math.isnan(val)
         or not (val == -1.0 or val>=0.0) ):
        return err
    return ( True, (key,val) )

def _parse_statsum( comments ):
    #Parse list of byte strings for any stat:sum: entries.
    d = {}
    prefix = b'stat:sum:'
    error_comment = None
    for comment in comments:
        if not comment.startswith(prefix):
            continue
        ok, (key,val) = _parse_statsum_comment( comment)
        if ok:
            if key in d:
                raise MCPLError('Duplicate stat:sum: key. The key '
                                f'"{key}" appears more than once in the file.')
            d[key] = None if val == -1.0 else val
        else:
            error_comment = comment
            break
    if error_comment:
        example = error_comment.decode('utf-8',errors='backslashreplace')
        raise MCPLError('Input has "stat:sum:..." comment entry not'
                        f' following the specification: "{example}"')
    return d

def _statsum_marking( statsum, nparticles, skip, limit, edit, keepstatsum = False ):
    """Why the stat:sum entries (statsum) of a file of nparticles particles
    are marked as not available (-1) in a file with its particles in a range
    (skip and limit), edited (with a ParticleEdit, or None): 'positions' when
    filtering particles based on their positions in the file, 'weights' when
    changing their weights (unless keepstatsum), or None (see the guidelines
    for stat:sum entries)"""
    if not any( v is not None for v in statsum.values() ):
        return None, None
    if nparticles > 0 and ( ( skip or 0 ) > 0 or 0 < ( limit or 0 ) < nparticles
                            or ( edit is not None and edit.filters_on_fileidx ) ):
        return 'positions'
    if not keepstatsum and edit is not None and edit.has_weight_changes:
        return 'weights'
    return None
