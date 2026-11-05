
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


#INSTALL.md and the "Building from source" page of the website are both
#generated from doc/install_source.md, which is written in a small subset of
#Markdown (see the comment at the top of that file).

import re

source_relpath = 'doc/install_source.md'
install_md_relpath = 'INSTALL.md'

def _source_text():
    from .dirs import reporoot
    return reporoot.joinpath(source_relpath).read_text()

def _drop_comments( text ):
    return re.sub( r'<!--.*?-->\n*', '', text, flags = re.DOTALL )

def produce_install_md():
    return _drop_comments( _source_text() ).rstrip('\n') + '\n'

def _parse_blocks( text ):
    """Splits the text into blocks: ('heading',level,text), ('code',lines),
    ('image',line) and ('para',lines)."""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        nxt = lines[i+1] if i + 1 < len(lines) else ''
        if nxt and set(nxt) <= {'='} and len(nxt) == len(line):
            blocks.append( ('heading', 1, line) )
            i += 2
            continue
        if nxt and set(nxt) <= {'-'} and len(nxt) == len(line):
            blocks.append( ('heading', 2, line) )
            i += 2
            continue
        if line.startswith('```'):
            j = i + 1
            while not lines[j].startswith('```'):
                j += 1
            blocks.append( ('code', lines[i+1:j]) )
            i = j + 1
            continue
        if line.startswith('!['):
            blocks.append( ('image', line) )
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip() and not lines[j].startswith(('```','![')):
            j += 1
        blocks.append( ('para', lines[i:j]) )
        i = j
    return blocks

def _slug( title ):
    return re.sub( r'[^a-z0-9]+', '_', title.lower() ).strip('_')

def _rst_inline( line ):
    #`code` -> ``code`` (emphasis and plain URLs are the same in reST):
    return re.sub( r'`([^`]+)`', r'``\1``', line )

def produce_get_source_rst( pagekey = 'get_source' ):
    """Contents of the website page (reST, without its title): the sections
    after the first part of the source, with a label for each section."""
    blocks = _parse_blocks( _drop_comments( _source_text() ) )
    #Skip the first part (the standard installation), and the heading of the
    #second part (which is the title of the page):
    heading1 = [ i for i,b in enumerate(blocks)
                 if b[0] == 'heading' and b[1] == 1 ]
    assert len(heading1) == 2, 'expected two parts in ' + source_relpath
    blocks = blocks[heading1[1]+1:]
    out = []
    for b in blocks:
        if b[0] == 'heading':
            title = b[2]
            out += [ f'.. _{pagekey}-{_slug(title)}:', '', title,
                     '=' * len(title), '' ]
        elif b[0] == 'code':
            out += [ '.. code-block:: sh', '' ]
            out += [ ( '   ' + line ) if line else '' for line in b[1] ]
            out += [ '' ]
        elif b[0] == 'image':
            continue#(badges are only shown in INSTALL.md)
        else:
            out += [ _rst_inline(line) for line in b[1] ] + [ '' ]
    return '\n'.join(out).rstrip('\n') + '\n'

def check_install_md( fix = False ):
    from .dirs import reporoot
    f = reporoot.joinpath(install_md_relpath)
    expected = produce_install_md()
    if f.read_text() == expected:
        return True
    if fix:
        f.write_text(expected)
        print(f'Updated {install_md_relpath}')
        return True
    return False
