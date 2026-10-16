
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


#The C API reference of the website, generated from the declarations and
#comments in mcpl.h (in the C domain of Sphinx). The header is organised in
#sections with banners like:
#
#  /*********/
#  /* Types */
#  /*********/
#
#and the declarations have comments before them (for one declaration, or for
#a group of declarations without blank lines between them) or after them on
#the same line. Comments followed by a blank line are text of the section.

import re


def header_file():
    from .dirs import reporoot
    return reporoot / 'mcpl_core' / 'include' / 'mcpl.h.in'

def _comment_text( line ):
    """Contents of a line like '  /* text */' (None if not such a line)"""
    s = line.strip()
    if not ( s.startswith('/*') and s.endswith('*/') ) or s.startswith('/**'):
        return None
    return s[2:-2].rstrip()

def _is_banner( line ):
    return bool( re.fullmatch( r'\s*/\*{3,}/\s*', line ) )

def _split_trailing_comment( code ):
    """('code', 'comment') for a line like 'code;/* comment */'"""
    m = re.search( r'/\*(.*?)\*/\s*$', code )
    if m and not code.strip().startswith('/*'):
        return code[:m.start()].rstrip(), m.group(1).strip()
    return code.rstrip(), None

class Decl:
    def __init__( self, kind, code, doc = None, members = None ):
        self.kind = kind#'function', 'struct', 'macro'
        self.code = code
        self.doc = list(doc or [])#comment lines
        self.members = members or []#(code,doc) of struct members
        self.windows_only = False

    def name( self ):
        if self.kind == 'struct':
            return self.code
        if self.kind == 'macro':
            return self.code.split()[0]
        m = re.search( r'(\w+)\s*\(', self.code )
        return m.group(1)

def parse_header( text = None ):
    """List of sections (title, items), where items are ('text', lines) or
    ('group', lines, decls)."""
    lines = ( text or header_file().read_text() ).splitlines()
    start = next( i for i, l in enumerate(lines)
                  if _is_banner(l) and _comment_text(lines[i+1]) == ' Types' )
    end = max( i for i, l in enumerate(lines) if l.strip() == '#ifdef __cplusplus' )
    lines = lines[start:end]
    sections = []
    comment = []
    group = None
    windows = False
    def flush_comment_as_text():
        nonlocal comment
        if comment and sections:
            sections[-1][1].append( ( 'text', comment ) )
        comment = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if ( _is_banner(line) and i + 2 < len(lines)
             and _is_banner(lines[i+2]) ):
            flush_comment_as_text()
            group = None
            sections.append( ( _comment_text(lines[i+1]).strip(), [] ) )
            i += 3
            continue
        if not line.strip():
            flush_comment_as_text()
            group = None
            i += 1
            continue
        if line.strip().startswith('#pragma'):
            i += 1
            continue
        if line.strip() == '#ifdef _WIN32':
            windows = True
            i += 1
            continue
        if line.strip() == '#endif':
            windows = False
            i += 1
            continue
        c = _comment_text( line )
        if c is not None:
            if group is not None and not comment and c.strip().startswith('('):
                #(continuation of the documentation of the last declaration)
                group[2][-1].doc.append( c )
            else:
                comment.append( c )
                group = None
            i += 1
            continue
        s = line.strip()
        if s.startswith('typedef struct'):
            #typedef struct MCPL_API { ... } name; (maybe on one line)
            code_lines = [ s ]
            while '}' not in code_lines[-1]:
                i += 1
                code_lines.append( lines[i].strip() )
            last, trailing = _split_trailing_comment( code_lines[-1] )
            name = re.search( r'}\s*(\w+)\s*;', last ).group(1)
            members = []
            member_comment = []
            body = ' '.join( code_lines )
            if '{' in code_lines[0] and '}' in code_lines[0]:
                inner = body[body.index('{')+1:body.index('}')]
                members = [ ( m.strip() + ';', [] )
                            for m in inner.split(';') if m.strip() ]
            else:
                for cl in code_lines[1:-1]:
                    mc = _comment_text( cl )
                    if mc is not None:
                        member_comment.append( mc )
                        continue
                    code, tc = _split_trailing_comment( cl )
                    doc = member_comment + ( [ ' ' + tc ] if tc else [] )
                    members.append( ( code, doc ) )
                    member_comment = []
            d = Decl( 'struct', name, doc = comment
                      + ( [ ' ' + trailing ] if trailing else [] ),
                      members = members )
            if member_comment:
                d.doc += member_comment
            sections[-1][1].append( ( 'group', [], [ d ] ) )
            comment = []
            group = None
            i += 1
            continue
        if s.startswith('#define'):
            code, tc = _split_trailing_comment( s[len('#define'):].strip() )
            d = Decl( 'macro', code, doc = [ ' ' + tc ] if tc else [] )
        elif s.startswith('MCPL_API'):
            code_lines = [ s ]
            while ';' not in _split_trailing_comment( code_lines[-1] )[0]:
                i += 1
                code_lines.append( lines[i].strip() )
            code, tc = _split_trailing_comment( ' '.join( code_lines ) )
            code = re.sub( r'\s+', ' ', code.replace('MCPL_API','',1) ).strip()
            code = re.sub( r'\(\s+', '(', code )
            code = re.sub( r'\s+\)', ')', code )
            #(parameters of function type, like "int(filter)(...)", as the
            #equivalent function pointers, which Sphinx can parse):
            code = re.sub( r'\b(\w+)\((\w+)\)\(', r'\1 (*\2)(', code )
            d = Decl( 'function', code.rstrip(';').strip(),
                      doc = [ ' ' + tc ] if tc else [] )
        else:
            raise SystemExit( f'Unexpected line in mcpl.h: {line!r}' )
        d.windows_only = windows
        if group is None:
            group = ( 'group', comment, [] )
            sections[-1][1].append( group )
            comment = []
        elif comment:
            #(comment directly between two declarations, for the next one)
            group = ( 'group', comment, [] )
            sections[-1][1].append( group )
            comment = []
        group[2].append( d )
        i += 1
    flush_comment_as_text()
    return sections

def _slug( title ):
    return re.sub( r'[^a-z0-9]+', '_', title.lower() ).strip('_')

def _rst_text( comment_lines, known_names ):
    """reST for the lines of a comment: paragraphs, with lines indented more
    than the others as literal blocks, and with links to known names."""
    out = []
    para = []
    literal = []
    def esc( text ):
        text = text.replace('\\','\\\\').replace('`','\\`').replace('*','\\*')
        text = text.replace('|','\\|')
        text = re.sub( r'(?<=\w)_(?=\W|$)', r'\\_', text )
        def link( m ):
            name = m.group(0)
            if name in known_names:
                role = 'c:struct' if name.endswith('_t') else 'c:func'
                if name.startswith('MCPL_'):
                    role = 'c:macro'
                return f':{role}:`{name}`'
            return name
        text = re.sub( r'\b(?:mcpl|MCPL)_\w*[A-Za-z0-9]', link, text )
        #(reST needs a separator between a role and a following "("):
        return text.replace( '`(', '`\\ (' )
    def flush():
        nonlocal para, literal
        if para:
            out.append( esc( ' '.join( p.strip() for p in para ) ) )
            out.append( '' )
        if literal:
            out.append( '::' )
            out.append( '' )
            out.extend( '   ' + li for li in literal )
            out.append( '' )
        para, literal = [], []
    for line in comment_lines:
        if not line.strip():
            flush()
            continue
        indent = len(line) - len(line.lstrip())
        if indent > 1:
            if para:
                out.append( esc( ' '.join( p.strip() for p in para ) ) )
                out.append( '' )
                para = []
            literal.append( line[2:] )
        else:
            if literal:
                flush()
            para.append( line )
    flush()
    return out

def _version_macros():
    """The version macros at the top of mcpl.h"""
    return [ ( 'MCPL_VERSION_MAJOR', 'Major version number of MCPL.' ),
             ( 'MCPL_VERSION_MINOR', 'Minor version number of MCPL.' ),
             ( 'MCPL_VERSION_PATCH', 'Patch version number of MCPL.' ),
             ( 'MCPL_VERSION', ( 'Version number of MCPL as one integer'
                                 ' (10000*MAJOR+100*MINOR+PATCH).' ) ),
             ( 'MCPL_VERSION_STR', ( 'Version number of MCPL as a string,'
                                     ' like "2.2.9".' ) ),
             ( 'MCPL_FORMATVERSION', ( 'Latest MCPL format version supported'
                                       ' (see :doc:`format`).' ) ) ]

def produce_c_api_rst( pagekey = 'c_api' ):
    """Contents of the website page (reST, without its title)"""
    sections = parse_header()
    known = { d.name() for _, items in sections for it in items
              if it[0] == 'group' for d in it[2] }
    known.update( n for n, _ in _version_macros() )
    out = []
    def section( title ):
        out.extend( [ f'.. _{pagekey}-{_slug(title)}:', '', title,
                      '=' * len(title), '' ] )
    section( 'Version numbers' )
    for name, descr in _version_macros():
        out.extend( [ f'.. c:macro:: {name}', '', f'   {descr}', '' ] )
    for title, items in sections:
        section( title )
        for it in items:
            if it[0] == 'text':
                out += _rst_text( it[1], known )
                continue
            _, comment, decls = it
            single = len(decls) == 1
            if comment and not single:
                out += _rst_text( comment, known )
            for d in decls:
                doc = ( comment if single else [] ) + d.doc
                if d.windows_only:
                    doc = doc + [ '', ' (Only on Windows.)' ]
                if d.kind == 'struct':
                    out += [ f'.. c:struct:: {d.code}', '' ]
                elif d.kind == 'macro':
                    out += [ f'.. c:macro:: {d.name()}', '' ]
                else:
                    out += [ f'.. c:function:: {d.code}', '' ]
                out += [ ( '   ' + li ) if li else '' for li in _rst_text( doc, known ) ]
                for mcode, mdoc in d.members:
                    out += [ f'   .. c:member:: {mcode.rstrip(";")}', '' ]
                    out += [ ( '      ' + li ) if li else ''
                             for li in _rst_text( mdoc, known ) ]
    return '\n'.join( out ).rstrip('\n') + '\n'
