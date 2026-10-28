
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

"""Reference documentation of the public Python API of the mcpl package,
generated from its docstrings, as Markdown which can be used both by the
current (Jekyll) website and by Sphinx (with the MyST parser). The docstrings
are the only source of the documentation, so a future Sphinx website could
also use them directly (with autodoc)."""

import inspect
import re
import sys

#Sections of the page, with the modules whose public names they show:
_sections = [
    ( 'Reading files', ('_reader','_blocks') ),
    ( 'Writing files', ('_writer',) ),
    ( 'File operations', ('_fileops',) ),
    ( 'Expressions', ('_expressions',) ),
    ( 'Statistics and histograms', ('_stats','_histogram') ),
    ( 'Other', ('_common','_messages','_statsum','_cli') ),
]

def import_mcpl():
    """Import the mcpl package of the repository (not an installed one)."""
    from .dirs import pyroot
    sys.path.insert(0,str(pyroot / 'src'))
    import mcpl
    srcdir = ( pyroot / 'src' / 'mcpl' ).resolve()
    from pathlib import Path
    if Path(mcpl.__file__).resolve().parent != srcdir:
        raise SystemExit(f'Error: imported mcpl from {mcpl.__file__} and not from {srcdir}')
    return mcpl

def _escape( text ):
    """Escape characters with special meaning in Markdown, except inside
    `code`."""
    parts = re.split(r'(`[^`]*`)',text)
    return ''.join( p if p.startswith('`') else re.sub(r'([\\*_<>|\[\]#])',r'\\\1',p)
                    for p in parts )

def _inline( text ):
    """Text of a paragraph, with "quoted" expressions as inline code"""
    text = re.sub(r'"([^"\n]+)"',lambda m : f'`{m.group(1)}`',text)
    return _escape(text)

def _source_doc( obj ):
    """The docstring of obj as written in the source code, and the indentation
    of its body there (or obj.__doc__ and None if the source is not
    available). Python 3.13+ removes the indentation from __doc__, which is
    needed to distinguish the examples (indented more) from the text."""
    import ast
    import textwrap
    try:
        src = textwrap.dedent(inspect.getsource(obj))
        node = ast.parse(src).body[0]
    except (OSError,TypeError,SyntaxError,IndexError):
        return obj.__doc__, None
    first = node.body[0] if getattr(node,'body',None) else None
    if not ( isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant)
             and isinstance(first.value.value,str) ):
        return obj.__doc__, None
    return first.value.value, node.col_offset + 4

def doc_to_markdown( doc, base = None ):
    """Convert a docstring (plain text) to Markdown: paragraphs, lists (lines
    starting with "* "), and code blocks (lines indented more than the
    paragraphs, which are indented by base in the source code, if known)."""
    if not doc:
        return ''
    if base is None:
        lines = inspect.cleandoc(doc).splitlines()
    else:
        lines = doc.expandtabs().splitlines()
        lines = [ lines[0].strip() ] + [ ( line[base:] if line[:base].strip() == '' else line.lstrip() )
                                         for line in lines[1:] ]
        while lines and not lines[-1].strip():
            lines.pop()
    out = []
    i = 0
    def indent( line ):
        return len(line) - len(line.lstrip())
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if indent(line) > 0 and not line.lstrip().startswith('* '):
            #Code block (until a non-indented line):
            block = []
            while i < len(lines) and ( not lines[i].strip() or indent(lines[i]) > 0 ):
                block.append(lines[i])
                i += 1
            while block and not block[-1].strip():
                block.pop()
            n = min( indent(b) for b in block if b.strip() )
            out += [ '```python' ] + [ b[n:] for b in block ] + [ '```', '' ]
            continue
        if line.lstrip().startswith('* '):
            #List item (with continuation lines):
            item = [ line.lstrip()[2:] ]
            i += 1
            while ( i < len(lines) and lines[i].strip()
                    and not lines[i].lstrip().startswith('* ') and indent(lines[i]) > 0 ):
                item.append(lines[i].strip())
                i += 1
            out.append( '* ' + _inline(' '.join(item)) )
            #(blank lines between items do not end the list):
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].lstrip().startswith('* '):
                i = j
            else:
                out.append('')
            continue
        #Paragraph (until an empty or indented line, or a list):
        par = []
        while ( i < len(lines) and lines[i].strip() and indent(lines[i]) == 0
                and not lines[i].startswith('* ') ):
            par.append(lines[i].strip())
            i += 1
        out += [ _inline(' '.join(par)), '' ]
    return '\n'.join(out).rstrip('\n')

def _signature( name, obj ):
    """Signature, without self and private parameters (starting with _)"""
    try:
        sig = inspect.signature(obj)
    except (TypeError,ValueError):
        return f'{name}(...)'
    params = [ prm for pn, prm in sig.parameters.items()
               if pn != 'self' and not pn.startswith('_') ]
    return _wrap_signature(f'{name}{sig.replace(parameters=params)}')

def _wrap_signature( text, width = 50 ):
    """Signature wrapped at the commas between parameters (with a hanging
    indent), so code blocks on the website need no horizontal scrolling."""
    if len(text) <= width or '(' not in text:
        return text
    head, _, rest = text.partition('(')
    #Split the parameters at top level commas:
    parts, depth, cur = [], 0, ''
    for ch in rest:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur.strip() + ',')
            cur = ''
        else:
            cur += ch
    parts.append(cur.strip())
    lines, line = [ head + '(' ], '   '
    for part in parts:
        if len(line) + 1 + len(part) > width and line.strip():
            lines.append(line)
            line = '   '
        line += ' ' + part
    lines.append(line)
    return '\n'.join(lines)

def _members( cls ):
    """Public methods and properties defined by the class (or its mcpl base
    classes), in the order of definition"""
    res = []
    seen = set()
    for klass in cls.__mro__:
        if klass is object or not klass.__module__.startswith(cls.__module__.split('.')[0]):
            continue
        for name, obj in vars(klass).items():
            if name.startswith('_') or name in seen:
                continue
            seen.add(name)
            if isinstance(obj,property):
                res.append( ( name, 'property', obj ) )
            elif isinstance(obj,(staticmethod,classmethod)):
                res.append( ( name, 'method', obj.__func__ ) )
            elif inspect.isfunction(obj):
                res.append( ( name, 'method', obj ) )
    return res

#Names of public objects without docstrings, found by generate():
_undocumented = []

def _document( out, qualname, obj, level ):
    h = '#' * level
    if not ( getattr(obj,'__doc__',None) or '' ).strip():
        _undocumented.append(qualname)
    if inspect.isclass(obj):
        for name, kind, m in _members(obj):
            if not ( m.__doc__ or '' ).strip():
                _undocumented.append(f'{qualname}.{name}')
    if inspect.isclass(obj):
        out += [ f'{h} {qualname} (class)', '', '```python',
                 _signature('class ' + qualname.split('.')[-1],obj), '```', '' ]
        doc = doc_to_markdown(*_source_doc(obj))
        if doc:
            out += [ doc, '' ]
        #Properties with short descriptions in a list, others like methods:
        def pdoc( prop ):
            return doc_to_markdown(*_source_doc(prop.fget))
        def is_short( prop ):
            return '```' not in pdoc(prop)
        props = [ ( name, m ) for name, kind, m in _members(obj)
                  if kind == 'property' and is_short(m) ]
        if props:
            out += [ 'Properties:', '' ]
        out += [ f'* `{name}`: '
                 + pdoc(m).replace('\n\n',' ').replace('\n',' ')
                 for name, m in props ]
        if props:
            out.append('')
        for name, kind, m in _members(obj):
            if kind == 'property' and not is_short(m):
                out += [ f'{h}# {qualname.split(".")[-1]}.{name} (property)', '',
                         pdoc(m), '' ]
            if kind == 'method':
                out += [ f'{h}# {qualname.split(".")[-1]}.{name}', '', '```python',
                         _signature(name,m), '```', '' ]
                doc = doc_to_markdown(*_source_doc(m))
                if doc:
                    out += [ doc, '' ]
    else:
        out += [ f'{h} {qualname}', '', '```python', _signature(qualname.split('.')[-1],obj),
                 '```', '' ]
        doc = doc_to_markdown(*_source_doc(obj))
        if doc:
            out += [ doc, '' ]

def generate( front_matter = None, strict = False, note = None ):
    """Markdown of the reference documentation (with the given lines of Jekyll
    front matter at the top, if any, followed by the note). With strict, public
    objects without docstrings are errors."""
    mcpl = import_mcpl()
    _undocumented.clear()
    out = []
    if front_matter is not None:
        out += [ '---' ] + list(front_matter) + [ '---', '' ]
    if note:
        out += [ note, '' ]
    out += [ ( '<!-- Generated by "mcpldevtool pyapi" from the docstrings of the'
               f' mcpl package (version {mcpl.__version__}). Do not edit. -->' ), '' ]
    out += [ ( 'This page describes all the public classes, functions and modules'
               ' of the `mcpl` Python package, as given by its built-in'
               ' documentation (e.g. `help(mcpl.MCPLFile)`). Everything is'
               ' available directly after `import mcpl`, except the contents of'
               ' the `mcpl.plotting` and `mcpl.constants` modules.' ), '' ]
    names = [ n for n in mcpl.__all__ if n not in ('plotting','constants') ]
    done = set()
    for title, mods in _sections:
        objs = [ n for n in names
                 if getattr(getattr(mcpl,n),'__module__','').split('.')[-1] in mods ]
        if not objs:
            continue
        out += [ f'## {title}', '' ]
        for n in objs:
            _document(out,f'mcpl.{n}',getattr(mcpl,n),3)
            done.add(n)
    missing = sorted(set(names) - done)
    if missing:
        raise SystemExit(f'Error: names not in any section: {missing}')
    #The plotting module:
    plotting = mcpl.plotting
    out += [ '## mcpl.plotting', '', doc_to_markdown(plotting.__doc__,0), '' ]
    for n in plotting.__all__:
        _document(out,f'mcpl.plotting.{n}',getattr(plotting,n),3)
    #The constants module:
    constants = mcpl.constants
    out += [ '## mcpl.constants', '', doc_to_markdown(constants.__doc__,0), '',
             '| Name | Value |', '|---|---|' ]
    out += [ f'| `{n}` | `{getattr(constants,n)!r}` |' for n in constants.__all__ ]
    out.append('')
    if strict and _undocumented:
        raise SystemExit('Error: public objects without docstrings: '
                         + ', '.join(_undocumented))
    return '\n'.join(out)
