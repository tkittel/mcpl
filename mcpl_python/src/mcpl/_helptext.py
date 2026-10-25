
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

"""Help texts as blocks, shown as plain text (in terminals and by mcpltool -p
help) or formatted (in the windows of the viewer). The blocks are tuples of a
kind and its texts:

  ('text', TEXT)            a paragraph (with its line breaks for plain text)
  ('gap',)                  an empty line (in plain text)
  ('section', TITLE)        the title of a section
  ('subsection', TITLE)     the title of a part of a section (e.g. of examples)
  ('note', TEXT)            a paragraph at the start of a section
  ('item', NAME, TEXT)      the description of a name (e.g. a function)
  ('key', KEYS, TEXT)       the description of keys
  ('examples', ROWS)        examples, as rows of (code, what it does)"""

__all__ = []

import textwrap


def plain_text( blocks, width = 79 ):
    """The blocks as plain text, with lines of at most width characters"""
    lines = []
    def wrap( text, first, rest ):
        lines.extend(textwrap.wrap(text,width = width,initial_indent = first,
                                   subsequent_indent = rest))
    for kind, *args in blocks:
        if kind == 'gap':
            lines.append('')
        elif kind == 'text':
            #(with the line breaks given, and longer lines wrapped):
            for line in args[0].split('\n'):
                if len(line) > width:
                    wrap(line,'','')
                else:
                    lines.append(line)
        elif kind in ( 'section', 'subsection' ):
            lines.append(f'{args[0]}:')
        elif kind == 'note':
            wrap(args[0],'  ','  ')
        elif kind == 'item':
            wrap(args[1],f'  {args[0]}: ','      ')
        elif kind == 'key':
            #(the descriptions in a column, after the keys if they fit):
            if len(args[0]) <= 11:
                wrap(args[1],f'  {args[0]:<13}',' ' * 15)
            else:
                lines.append(f'  {args[0]}')
                wrap(args[1],' ' * 15,' ' * 15)
        else:
            assert kind == 'examples'
            for code, what in args[0]:
                code = f'  {code}'
                text = textwrap.wrap(what,width = width - 30)
                if len(code) <= 28:
                    lines.append(f'{code:<30}{text[0]}')
                    text = text[1:]
                else:
                    lines.append(code)
                lines += [ ' ' * 30 + t for t in text ]
    return '\n'.join(lines)
