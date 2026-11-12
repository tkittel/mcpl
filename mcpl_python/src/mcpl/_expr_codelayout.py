
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

"""The layout of generated code (see _expr_ast2code): long lines broken at
places which the code marks, and comments and strings split at spaces, so the
code stays within _width columns where it can. The syntax of the language
(see _Syntax) tells where comments and strings are, and after which
operators lines can also be broken."""

__all__ = []

import re
from collections import namedtuple

_width = 100

#The marks of the places where long lines can be broken: after the operators
#joining conditions (_BRK, one operand on each line), then where still needed
#after other operators and commas (_BRK2), and last after the opening
#parentheses of calls (_BRK3):
_BRK, _BRK2, _BRK3 = '\x00', '\x01', '\x02'
_ARGSEP = ', ' + _BRK2

#The syntax which the layout needs: the start and end of inline comments, the
#quote of strings, and the places after which long lines can also be broken:
_Syntax = namedtuple('_Syntax',( 'comment_start', 'comment_end', 'quote', 'breaks' ))

def _unmarked( line ):
    return line.replace(_BRK,'').replace(_BRK2,'').replace(_BRK3,'')

def _marked( line, syntax ):
    """The line, with the places after the breaks of the syntax (outside of
    strings and comments) also marked with _BRK2"""
    res, quoted, i = [], False, 0
    q = syntax.quote
    while i < len(line):
        if not quoted and line.startswith(syntax.comment_start,i):
            end = line.find(syntax.comment_end,i) + len(syntax.comment_end)
            res.append(line[i:end])
            i = end
            continue
        ch = line[i]
        quoted = quoted != ( ch == q and line[i-1:i] != '\\' )
        res.append(ch)
        i += 1
        if ( not quoted and line[i:i+1] not in ( _BRK, _BRK2, _BRK3 )
             and any( line.startswith(s,i-len(s)) for s in syntax.breaks ) ):
            res.append(_BRK2)
    return ''.join(res)

def _fill( line, marks, indent ):
    """The line, broken where needed at the places marked with the first of
    the marks (as many parts on each line as fit), and parts which are still
    too long at those of the next marks"""
    if len(_unmarked(line)) <= _width or not marks:
        return [ _unmarked(line).rstrip() ]
    lines, cur = [], ''
    for piece in line.split(marks[0]):
        if cur.strip() and len(_unmarked(cur + piece.rstrip())) > _width:
            lines.append(cur.rstrip())
            cur = indent + piece
        else:
            cur += piece
    lines.append(cur.rstrip())
    return [ done for part in lines for done in _fill(part,marks[1:],indent) ]

def _layout( lines, syntax ):
    """The lines of code, with those longer than _width columns broken at the
    places marked with _BRK (one part on each line), and then where still
    needed at those marked with _BRK2 and _BRK3 (the continuation lines
    indented 4 columns more), and the marks removed. Long lines are also
    marked after the breaks of the syntax (see _marked)."""
    res = []
    for line in lines:
        if len(_unmarked(line)) <= _width:
            res.append(_unmarked(line))
            continue
        line = _marked(line,syntax)
        indent = ' ' * ( len(line) - len(line.lstrip()) + 4 )
        first, *more = line.split(_BRK)
        for part in [ first ] + [ indent + p for p in more ]:
            res += _fill(part,( _BRK2, _BRK3 ),indent)
    return res

def _split_text( text, width, anywhere = False ):
    """The text in parts of at most width characters (where possible, or
    always with anywhere), split after spaces and semicolons (or anywhere in
    longer words, with anywhere), so they join to the text"""
    parts, cur = [], ''
    for word in re.split(r'(?<=[ ;])',text):
        if cur and len(cur) + len(word.rstrip()) > width and not ( anywhere and len(word) > width ):
            parts.append(cur)
            cur = ''
        cur += word
        while anywhere and len(cur) > width:
            parts.append(cur[:width])
            cur = cur[width:]
    return parts + [ cur ]

def _comment_lines( text, first, more, end = '' ):
    """Comment lines with the text, after first on the first line, and more
    on the others (as /* and *, or //), split at spaces and semicolons"""
    parts = [ p.rstrip() for p in _split_text(text,_width - len(more) - len(end)) ]
    lines = [ first + parts[0] ] + [ more + p for p in parts[1:] ]
    lines[-1] += end
    return lines

def _string_call( start, text, end, string, indent = 0 ):
    """The line(s) of a call with a string argument (start ends with the
    opening parenthesis), split in adjacent strings if long (see
    _split_text), for lines indented by indent more columns, where
    string(text) is the text as a string of the language"""
    width = _width - indent
    line = f'{start}{string(text)}{end}'
    if len(line) <= width:
        return [ line ]
    pad = ' ' * len(start)
    parts = [ string(p) for p in _split_text(text,width - len(start) - len(end) - 4,True) ]
    return ( [ start + parts[0] ] + [ pad + p for p in parts[1:-1] ] + [ pad + parts[-1] + end ] )
