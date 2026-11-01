
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

"""Colours in terminals: whether to use them (from the --color setting, the
NO_COLOR, FORCE_COLOR, TERM and COLORTERM environment variables, and whether
the output is a terminal), and the escape sequences for 8, 256 or 2^24
colours."""

__all__ = []

import os
import sys

from ._common import MCPLError

_color_settings = ( 'auto', 'always', 'never' )

def _check_setting( when ):
    if when not in _color_settings:
        raise MCPLError(f'The colour setting must be auto, always or never'
                        f' (not "{when}")')
    return when

def _ncolors( when = 'auto', stream = None ):
    """Number of colours to use for output to the stream (default
    sys.stdout): 0 (no colours), 8, 256 or 16777216 (see _use_colors)"""
    return _depth() if _use_colors(when,lambda : _is_terminal(stream)) else 0

def _use_colors( when, is_terminal ):
    """Whether colours are used with the setting (auto, always or never), for
    output where is_terminal() tells whether it is a terminal which can show
    colours. With when='auto', colours are used for terminals, unless NO_COLOR
    is set (to a non-empty value) or TERM is "dumb", and always if FORCE_COLOR
    is set (like in CPython)."""
    _check_setting(when)
    if when != 'auto':
        return when == 'always'
    env = os.environ
    if env.get('NO_COLOR'):
        return False
    return bool( env.get('FORCE_COLOR') ) or ( env.get('TERM') != 'dumb'
                                                and is_terminal() )

def _is_terminal( stream ):
    stream = sys.stdout if stream is None else stream
    try:
        if not stream.isatty():
            return False
    except (AttributeError, ValueError, OSError):
        return False
    if sys.platform == 'win32':
        #Only terminals which understand the escape sequences:
        try:
            import nt
            return bool(nt._supports_virtual_terminal())
        except (ImportError, AttributeError):
            return False
    return True

def _depth():
    if os.environ.get('COLORTERM','').lower() in ( 'truecolor', '24bit' ):
        return 16777216
    if '256' in os.environ.get('TERM',''):
        return 256
    return 8

#The tab10 colours of matplotlib (for curves), and points of the viridis
#colour map (for 2D maps), as (r,g,b):
_tab10 = ( (31,119,180), (255,127,14), (44,160,44), (214,39,40), (148,103,189),
           (140,86,75), (227,119,194), (127,127,127), (188,189,34),
           (23,190,207) )
_viridis = ( (68,1,84), (72,36,117), (65,68,135), (53,95,141), (42,120,142),
             (33,145,140), (34,168,132), (68,191,112), (122,209,81),
             (189,223,38), (253,231,37) )
#The 8 basic colours (as usually shown):
_basic8 = ( (0,0,0), (205,0,0), (0,205,0), (205,205,0), (0,0,238), (205,0,205),
            (0,205,205), (229,229,229) )

def _curve_rgb( i ):
    return _tab10[ i % len(_tab10) ]

def _map_rgb( f ):
    """Colour of the value f (from 0 to 1) in a 2D map"""
    f = min( 1.0, max( 0.0, float(f) ) ) * ( len(_viridis) - 1 )
    i = min( int(f), len(_viridis) - 2 )
    t = f - i
    a, b = _viridis[i], _viridis[i+1]
    return tuple( round( x + t * ( y - x ) ) for x, y in zip(a,b) )

def _dist2( a, b ):
    return sum( ( x - y )**2 for x, y in zip(a,b) )

def _code256( rgb ):
    levels = ( 0, 95, 135, 175, 215, 255 )
    idx = [ min( range(6), key = lambda k : abs(levels[k] - c) ) for c in rgb ]
    cube = tuple( levels[k] for k in idx )
    gray = min( range(24), key = lambda k : abs( 8 + 10 * k - sum(rgb) / 3 ) )
    gv = 8 + 10 * gray
    if _dist2( (gv,gv,gv), rgb ) < _dist2( cube, rgb ):
        return 232 + gray
    return 16 + 36 * idx[0] + 6 * idx[1] + idx[2]

def _sgr( rgb, ncolors, background = False ):
    """Parameters of the escape sequence setting the foreground (or
    background) colour"""
    if ncolors >= 16777216:
        return f'{48 if background else 38};2;{rgb[0]};{rgb[1]};{rgb[2]}'
    if ncolors >= 256:
        return f'{48 if background else 38};5;{_code256(rgb)}'
    #(black is only used for backgrounds, since black text is invisible on
    #dark backgrounds):
    k = min( range( 0 if background else 1, len(_basic8) ),
             key = lambda k : _dist2(_basic8[k],rgb) )
    return str( ( 40 if background else 30 ) + k )

def _paint( text, ncolors, fg = None, bg = None ):
    """Text with foreground and background colours (given as (r,g,b), or None)"""
    if not ncolors or ( fg is None and bg is None ) or not text:
        return text
    codes = [ _sgr(c,ncolors,b) for c, b in ( (fg,False), (bg,True) ) if c is not None ]
    return f'\x1b[{";".join(codes)}m{text}\x1b[0m'
