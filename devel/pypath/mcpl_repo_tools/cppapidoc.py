
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

"""Reference documentation of the C++ interface (mcplcpp.h), generated from
its Doxygen comments, as Markdown which can be used both by the current
(Jekyll) website and by Sphinx (with the MyST parser). Doxygen is used to
parse the header, and its XML output could also be used directly by a future
Sphinx website (with Breathe)."""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

#Sections of the page, with the classes and functions they show:
_sections = [
    ( 'Errors', ('mcpl::Error','mcpl::IOError') ),
    ( 'Reading files', ('mcpl::MCPLFile','mcpl::Particle','mcpl::StringListView',
                        'mcpl::BlobView','mcpl::DumpParts') ),
    ( 'Userdata', ('mcpl::UserdataField',) ),
    ( 'Writing files', ('mcpl::MCPLOutFile','mcpl::OutParticle') ),
    ( 'Operations on files', ('mcpl::merge_files','mcpl::forcemerge_files',
                              'mcpl::KeepUserflags','mcpl::can_merge',
                              'mcpl::merge_inplace','mcpl::repair',
                              'mcpl::gzip_file') ),
    ( 'Messages', ('mcpl::set_print_handler',) ),
]

#Classes which are not shown themselves (the members of ParticleAccessors are
#shown in the derived classes):
_hidden_classes = ('mcpl::ParticleAccessors',)

def header_file():
    from .dirs import coreroot_include
    return coreroot_include / 'mcplcpp.h'

def doxyfile( xmldir ):
    """Doxygen configuration, producing only XML output."""
    return '\n'.join( [
        f'INPUT = "{header_file()}"',
        f'OUTPUT_DIRECTORY = "{xmldir}"',
        'XML_OUTPUT = .',
        'GENERATE_XML = YES',
        'GENERATE_HTML = NO',
        'GENERATE_LATEX = NO',
        'EXTRACT_ALL = NO',
        'EXTRACT_PRIVATE = NO',
        ( 'EXCLUDE_SYMBOLS = mcpl::detail mcpl::MCPLFile::iterator'
          ' mcpl::StringListView::iterator' ),
        'INLINE_INHERITED_MEMB = YES',
        'AUTOLINK_SUPPORT = NO',
        'PREDEFINED = __cplusplus=201703L',
        'WARN_IF_UNDOCUMENTED = YES',
        'WARN_NO_PARAMDOC = NO',
        'WARN_IF_INCOMPLETE_DOC = NO',
        'QUIET = YES',
        '' ] )

doxygen_missing_msg = """Doxygen is needed to build the website (for the C++ API
reference), but the doxygen command was not found. Doxygen is not available
from PyPI, so it can not be installed with pip. Instead, either use a conda
environment (devel/reqs/conda_doc.yml includes it), or install it with the
package manager of your system, for example:

  sudo apt install doxygen    (Debian and Ubuntu)
  sudo dnf install doxygen    (Fedora)
  brew install doxygen        (macOS with Homebrew)

or from https://www.doxygen.nl/download.html"""

def run_doxygen( xmldir ):
    """Run Doxygen on mcplcpp.h, writing its XML to xmldir. Returns the
    warnings."""
    import pathlib
    exe = shutil.which('doxygen')
    if not exe:
        raise SystemExit('Error: '+doxygen_missing_msg)
    xmldir = pathlib.Path(xmldir)
    xmldir.mkdir(parents=True,exist_ok=True)
    (xmldir/'Doxyfile').write_text(doxyfile(xmldir.absolute()))
    warnfile = xmldir / 'warnings.log'
    with open(warnfile,'w') as fh:
        subprocess.run( [ exe, 'Doxyfile' ], cwd = xmldir, check = True,
                        stdout = subprocess.DEVNULL, stderr = fh )
    return [ w for w in warnfile.read_text().splitlines() if w.strip() ]

################################################################################
# Conversion of descriptions to Markdown

def _escape( text ):
    from .pyapidoc import _escape as e
    return e(text)

def _code_text( elem ):
    return ''.join(elem.itertext())

#Names in the text which are shown as code (qualified names like
#mcpl::MCPLFile::read, and calls like close()):
_re_code = re.compile(r'\b(?:[A-Za-z_]\w*::)+[A-Za-z_]\w*(?:\(\))?|\b[A-Za-z_]\w*\(\)')

def _text( text ):
    """Escaped text, with names shown as code."""
    out, pos = [], 0
    for m in _re_code.finditer(text):
        out += [ _escape(text[pos:m.start()]), '`' + m.group(0) + '`' ]
        pos = m.end()
    out.append( _escape(text[pos:]) )
    return ''.join(out)

def _inline( elem ):
    """Markdown of the inline contents of elem (without nested blocks)."""
    out = [ _text(elem.text or '') ]
    for ch in elem:
        if ch.tag in ('computeroutput','ref'):
            out.append( '`' + _code_text(ch).strip() + '`' )
        elif ch.tag == 'emphasis':
            out.append( '*' + _inline(ch) + '*' )
        elif ch.tag == 'bold':
            out.append( '**' + _inline(ch) + '**' )
        elif ch.tag == 'ulink':
            out.append( f'[{_inline(ch)}]({ch.get("url")})' )
        elif ch.tag in ('sp','linebreak'):
            out.append(' ')
        elif ch.tag in _block_tags:
            pass
        else:
            out.append( _inline(ch) )
        out.append( _text(ch.tail or '') )
    return re.sub(r'\s+',' ',''.join(out))

_block_tags = ('programlisting','itemizedlist','orderedlist','parameterlist',
               'simplesect')

def _programlisting( elem ):
    #(the text of codelines is in highlight elements, with sp for spaces):
    def walk( e, top, parts ):
        if e.tag == 'sp':
            parts.append(' ')
        else:
            parts.append( e.text or '' )
            for c in e:
                walk(c,top,parts)
        if e is not top:
            parts.append( e.tail or '' )
    lines = []
    for cl in elem.findall('codeline'):
        parts = []
        walk(cl,cl,parts)
        lines.append(''.join(parts).rstrip())
    return [ '```cpp' ] + lines + [ '```' ]

class _Desc:
    """Contents of a description: text blocks (Markdown), parameters,
    template parameters, return value and exceptions."""
    def __init__( self ):
        self.blocks = []
        self.params = []
        self.tparams = []
        self.returns = None
        self.throws = []
    def empty( self ):
        return not ( self.blocks or self.params or self.tparams
                     or self.returns or self.throws )
    def simple( self ):
        """Only a single line of text."""
        return ( len(self.blocks) == 1 and '\n' not in self.blocks[0]
                 and not ( self.params or self.tparams or self.returns
                           or self.throws ) )

def _paras( elem, desc ):
    for para in elem.findall('para'):
        text = _inline(para).strip()
        if text:
            desc.blocks.append(text)
        for ch in para:
            if ch.tag == 'programlisting':
                desc.blocks.append( '\n'.join(_programlisting(ch)) )
            elif ch.tag in ('itemizedlist','orderedlist'):
                items = []
                for li in ch.findall('listitem'):
                    sub = _Desc()
                    _paras(li,sub)
                    items.append( '* ' + ' '.join(sub.blocks) )
                desc.blocks.append('\n'.join(items))
            elif ch.tag == 'parameterlist':
                for item in ch.findall('parameteritem'):
                    names = [ _code_text(n).strip() for n in item.iter('parametername') ]
                    sub = _Desc()
                    _paras(item.find('parameterdescription'),sub)
                    text = ' '.join(sub.blocks)
                    for n in names:
                        { 'param' : desc.params,
                          'templateparam' : desc.tparams,
                          'exception' : desc.throws }[ch.get('kind')].append( ( n, text ) )
            elif ch.tag == 'simplesect':
                sub = _Desc()
                _paras(ch,sub)
                text = ' '.join(sub.blocks)
                if ch.get('kind') == 'return':
                    desc.returns = text
                else:
                    desc.blocks.append( f'{ch.get("kind").capitalize()}: {text}' )

def _description( elem ):
    desc = _Desc()
    for tag in ('briefdescription','detaileddescription'):
        d = elem.find(tag)
        if d is not None:
            _paras(d,desc)
    return desc

def _desc_markdown( desc ):
    out = []
    for b in desc.blocks:
        out += [ b, '' ]
    if desc.tparams:
        out += [ 'Template parameters:', '' ]
        out += [ f'* `{n}`: {t}' for n, t in desc.tparams ] + [ '' ]
    if desc.params:
        out += [ 'Parameters:', '' ]
        out += [ f'* `{n}`: {t}' for n, t in desc.params ] + [ '' ]
    if desc.returns:
        out += [ f'Returns: {desc.returns}', '' ]
    for n, t in desc.throws:
        out += [ f'Throws `{n}` {t}', '' ]
    return out

################################################################################
# Signatures

def _clean_type( text ):
    text = re.sub(r'\s+',' ',text).strip()
    text = text.replace('detail::FilenameArg','Filename')
    text = re.sub(r'<\s+','<',text)
    text = re.sub(r'\s+>','>',text)
    text = re.sub(r'\s+&','&',text)
    text = re.sub(r'&(?=[\w.])','& ',text)
    return text

def _template_prefix( elem ):
    tpl = elem.find('templateparamlist')
    if tpl is None:
        return ''
    parts = []
    for p in tpl.findall('param'):
        s = _clean_type(_code_text(p.find('type')))
        dn = p.findtext('declname')
        if dn:
            s += ' ' + dn
        dv = p.find('defval')
        if dv is not None:
            s += ' = ' + _clean_type(_code_text(dv))
        parts.append(s)
    return 'template<' + ', '.join(parts) + '>\n'

def _wrap( text ):
    from .pyapidoc import _wrap_signature
    return '\n'.join( _wrap_signature(line,width=60) for line in text.split('\n') )

def _member_signature( m ):
    kind = m.get('kind')
    name = m.findtext('name')
    typ = _clean_type(_code_text(m.find('type')) if m.find('type') is not None else '')
    if kind == 'function':
        args = _clean_type(m.findtext('argsstring') or '')
        #(spaces around = of default arguments and "= default"):
        args = re.sub(r'(?<![=!<>])=(?!=)',' = ',args)
        args = re.sub(r'\s+=\s+',' = ',args)
        pre = 'explicit ' if m.get('explicit') == 'yes' else ''
        sig = f'{pre}{typ} {name}{args}'.strip()
    elif kind == 'typedef':
        sig = f'using {name} = {typ}'
    elif kind == 'variable':
        pre = 'static ' if m.get('static') == 'yes' else ''
        sig = f'{pre}{typ} {name}'
    else:
        sig = f'{typ} {name}'
    return _template_prefix(m) + _wrap(sig.replace('  ',' '))

def _is_deleted( m ):
    return ( m.findtext('argsstring') or '' ).replace(' ','').endswith('=delete')

################################################################################
# Pages

#Names of public entities without documentation, found by generate():
_undocumented = []

def _member_list( out, members, qualname ):
    """Members, with runs of members with single line descriptions shown
    together (one code block, and a list of descriptions)."""
    i = 0
    while i < len(members):
        m = members[i]
        desc = _description(m)
        if desc.empty():
            _undocumented.append(f'{qualname}::{m.findtext("name")}')
        if desc.simple():
            run = [ ( m, desc ) ]
            j = i + 1
            while j < len(members):
                d = _description(members[j])
                if not d.simple():
                    break
                run.append( ( members[j], d ) )
                j += 1
            out += [ '```cpp' ] + [ _member_signature(x) for x, _ in run ] + [ '```', '' ]
            if len(run) == 1:
                out += [ run[0][1].blocks[0], '' ]
            else:
                for x, d in run:
                    nm = x.findtext('name')
                    call = nm if x.get('kind') != 'function' else nm + '()'
                    out.append( f'* `{call}`: {d.blocks[0]}' )
                out.append('')
            i = j
            continue
        out += [ '```cpp', _member_signature(m), '```', '' ]
        out += _desc_markdown(desc)
        i += 1

def _class( out, cd, xmldir ):
    qualname = cd.findtext('compoundname')
    short = qualname.split('::')[-1]
    kind = cd.get('kind')
    desc = _description(cd)
    if desc.empty():
        _undocumented.append(qualname)
    bases = [ b.text for b in cd.findall('basecompoundref')
              if b.get('prot') == 'public' and 'ParticleAccessors' not in b.text ]
    sig = _template_prefix(cd) + f'{kind} {qualname}'
    if bases:
        sig += ' : public ' + ', public '.join(bases)
    out += [ f'### {qualname} ({kind})', '', '```cpp', sig, '```', '' ]
    out += _desc_markdown(desc)
    own, inherited = [], []
    for sd in cd.findall('sectiondef'):
        k = sd.get('kind')
        if not ( k == 'user-defined' or k.startswith('public') ):
            continue
        for m in sd.findall('memberdef'):
            if m.get('prot') != 'public' or _is_deleted(m):
                continue
            is_inherited = not m.get('id').startswith(cd.get('id') + '_')
            grp = sd.findtext('header') if k == 'user-defined' else None
            line = int(m.find('location').get('line'))
            ( inherited if is_inherited else own ).append( ( line, grp, m ) )
    def show( entries ):
        #In the order of the header, with headings for the groups (and for
        #members outside groups after a group):
        entries.sort( key = lambda e : e[0] )
        runs = []
        for line, grp, m in entries:
            if runs and runs[-1][0] == grp:
                runs[-1][1].append(m)
            else:
                runs.append( ( grp, [ m ] ) )
        seen_group = False
        for grp, ms in runs:
            if grp:
                out.extend( [ f'#### {short}: {grp}', '' ] )
                seen_group = True
            elif seen_group:
                out.extend( [ f'#### {short}: Other', '' ] )
            elif has_groups:
                out.extend( [ f'#### {short}: Basics', '' ] )
            else:
                out.extend( [ 'Members:', '' ] )
            _member_list(out,ms,qualname)
    has_groups = any( g for _, g, _ in own + inherited )
    show(own)
    show(inherited)

def _enum( out, m ):
    qualname = 'mcpl::' + m.findtext('name')
    desc = _description(m)
    if desc.empty():
        _undocumented.append(qualname)
    values = ', '.join( v.findtext('name') for v in m.findall('enumvalue') )
    strong = 'enum class' if m.get('strong') == 'yes' else 'enum'
    out += [ f'### {qualname} (enum)', '', '```cpp',
             f'{strong} {qualname} {{ {values} }}', '```', '' ]
    out += _desc_markdown(desc)

def _functions( out, name, ms ):
    out += [ f'### {name}', '' ]
    for m in ms:
        desc = _description(m)
        if desc.empty():
            _undocumented.append(name)
        out += [ '```cpp', _member_signature(m), '```', '' ]
        out += _desc_markdown(desc)

def generate( front_matter = None, strict = False, note = None, xmldir = None ):
    """Markdown of the reference documentation (with the given lines of Jekyll
    front matter at the top, if any, followed by the note). The XML of Doxygen
    is written to xmldir (a temporary directory if None). With strict,
    entities without documentation (and any Doxygen warnings) are errors."""
    import pathlib
    import tempfile
    _undocumented.clear()
    with tempfile.TemporaryDirectory() as tmpdir:
        xd = pathlib.Path(xmldir) if xmldir else pathlib.Path(tmpdir)
        warnings = run_doxygen(xd)
        index = ET.parse(xd/'index.xml').getroot()
        compounds = {}
        for c in index.findall('compound'):
            if c.get('kind') in ('class','struct','namespace'):
                cd = ET.parse(xd/(c.get('refid')+'.xml')).getroot().find('compounddef')
                compounds[cd.findtext('compoundname')] = cd
    ns = compounds.pop('mcpl')
    nsmembers = {}
    for sd in ns.findall('sectiondef'):
        for m in sd.findall('memberdef'):
            nsmembers.setdefault( 'mcpl::'+m.findtext('name'), [] ).append(m)
    out = []
    if front_matter is not None:
        out += [ '---' ] + list(front_matter) + [ '---', '' ]
    if note:
        out += [ note, '' ]
    out += [ ( '<!-- Generated by "mcpldevtool cppapi" from the documentation'
               ' comments in mcplcpp.h. Do not edit. -->' ), '' ]
    out += [ ( 'This page describes the C++ interface of MCPL in the header'
               ' file `mcplcpp.h` (which requires C++17 or later), as given by'
               ' the'
               ' documentation comments in that file. Everything is in the'
               ' namespace `mcpl`. Arguments of type `Filename` can be'
               ' `std::filesystem::path` objects, which work with all names on'
               ' all platforms, or strings (`std::string`, `std::string_view`'
               ' or C strings), which are interpreted as UTF-8.' ), '' ]
    done = set()
    for title, names in _sections:
        out += [ f'## {title}', '' ]
        for n in names:
            if n in compounds:
                _class(out,compounds[n],None)
            elif n in nsmembers:
                ms = nsmembers[n]
                if ms[0].get('kind') == 'enum':
                    _enum(out,ms[0])
                else:
                    _functions(out,n,ms)
            else:
                raise SystemExit(f'Error: {n} not found in mcplcpp.h')
            done.add(n)
    missing = sorted( n for n in list(compounds) + list(nsmembers)
                      if n not in done and n not in _hidden_classes
                      and not n.startswith('std') )
    if missing:
        raise SystemExit(f'Error: not in any section of the page: {missing}')
    if strict and ( _undocumented or warnings ):
        raise SystemExit( 'Error: undocumented: ' + ', '.join(_undocumented)
                          + ( '\nDoxygen warnings:\n' + '\n'.join(warnings)
                              if warnings else '' ) )
    while out and not out[-1]:
        out.pop()
    return '\n'.join(out) + '\n'
