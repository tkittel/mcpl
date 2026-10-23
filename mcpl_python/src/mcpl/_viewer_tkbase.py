
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

"""Helpers of the parts of the viewer with Tk (see _viewer_tk)"""

__all__ = []

def tk_modules():
    """The modules of tkinter (imported when used, since Python can come
    without them)"""
    import tkinter
    from tkinter import ttk
    return tkinter, ttk

def wrapped( text, font, width, nlines = 2 ):
    """The text in at most nlines lines which fit the width (in pixels) with
    the font, broken at spaces, with the last line elided if needed"""
    lines, words = [], text.split(' ')
    while words and len(lines) < nlines - 1:
        n = 1
        while n < len(words) and font.measure(' '.join(words[:n+1])) <= width:
            n += 1
        if font.measure(words[0]) > width:
            break#(a word which does not fit is elided on the last line)
        lines.append(' '.join(words[:n]))
        words = words[n:]
    if words:
        lines.append(elided(' '.join(words),font,width))
    return lines

def elided( text, font, width ):
    """The text, shortened with ... at the end to fit the width (in pixels)
    with the font"""
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + '\u2026') > width:
        text = text[:-1]
    return text.rstrip() + '\u2026'
