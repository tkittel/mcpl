
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

import contextlib as _contextlib
import sys


def flush():
    sys.stderr.flush()
    sys.stdout.flush()

@_contextlib.contextmanager
def work_in_tmpdir():
    """Context manager for working in a temporary directory (automatically
    created+cleaned) and then switching back"""
    import os
    import tempfile
    the_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            os.chdir(tmpdir)
            yield
        finally:
            os.chdir(the_cwd)#Important to leave tmpdir *before* deletion, to
                             #avoid PermissionError on Windows.

def calc_md5hexdigest( str_or_bytes, / ):
    import hashlib
    if hasattr(str_or_bytes,'encode'):
        data = str_or_bytes.encode('utf8',errors='backslashreplace')
    else:
        data = str_or_bytes
    return hashlib.md5( data ).hexdigest()

def print_text_file_with_snipping(content,
                                  nstart=30,
                                  nend=20,
                                  prefix=''):
    """Prints text files, but snips out the middle part of larger
    files. Printout includes a checksum of the snipped part."""
    nstart = max(3,nstart)
    nend = max(3,nend)
    lines=content.splitlines()
    if len(lines) < int((nstart+nend)*1.5+1):
        for line in lines:
            print(f'{prefix}{line}')
    else:
        for i in range(nstart):
            print(f'{prefix}{lines[i]}')
        md5 = calc_md5hexdigest( '\n'.join(lines[nstart:-nend]) )
        def nleading_spaces( s ):
            return len(s)-len(s.lstrip(' '))
        nspaces = min(nleading_spaces(lines[nstart-1]),
                      nleading_spaces(lines[-nend]))
        spaces = ' '*nspaces
        print(f"{prefix}{spaces}<<<SNIPPED {len(lines)-nstart-nend} LINES,"
              f" MD5={md5}>>>")
        for i in range(nend):
            print(f'{prefix}{lines[-nend+i]}')

def rounded_numbers( text, digits = 6 ):
    """The text with its decimal numbers (with a point or an exponent) rounded
    to digits significant digits, for output which must be the same on all
    platforms (whose last digits of computed values can differ)"""
    import re
    return re.sub(r'\d+\.\d*(?:e[-+]?\d+)?|\d+e[-+]?\d+',
                  lambda m : f'{float(m.group()):.{digits}g}',text)
