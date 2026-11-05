
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

import gzip
import hashlib
import os
import shlex
import subprocess
import sys
from pathlib import Path

from .common import flush
from .dirs import test_data_dir


def gunzip( f ):
    f = Path(f)
    assert f.name.endswith('.gz')
    ftgt = f.absolute().parent.joinpath(f.name[:-3])
    assert f.is_file()
    assert not ftgt.is_file()
    content = gzip.decompress(f.read_bytes())
    f.unlink()
    ftgt.write_bytes(content)

def cmd(*args, print_md5sum_of_output = False, fail = False):
    """Run mcpltool with the arguments (with a fixed version in its
    printouts), printing its output (and its errors, in order), and check that
    it fails if fail is set"""
    flush()
    print("----------------------------------------------")
    def argfmt( a ):
        a = str(a)
        if str(test_data_dir) in a:
            a = a.replace(str(test_data_dir),'<TESTDATADIR>')
        if '\\' in a and '/' not in a:
            a = a.replace('\\','/')
        return a
    args_print = shlex.join( argfmt(a) for a in args )
    fullcmd = [ sys.executable, '-m', 'mcpldev', *( str(a) for a in args ) ]
    print(f"Running mcpltool {args_print}")
    print("----------------------------------------------")
    flush()
    rv = subprocess.run( fullcmd, stdout = subprocess.PIPE, stderr = subprocess.STDOUT,
                         check = False,
                         env = { **os.environ, 'PYMCPLTOOL_FAKE_PYVERSION' : '1' } )
    flush()
    if print_md5sum_of_output:
        print('>>>{}<<<'.format(rv.stdout
              .replace(b'\r',b'<CR>')
              .replace(b'\n',b'<LF>')
              .decode('ascii','backslashreplace')))
        print( hashlib.md5(rv.stdout).hexdigest() )
    else:
        sys.stdout.buffer.write(rv.stdout)
    print()
    flush()
    if rv.returncode != 0:
        print("===> Command failed!")
    if bool(fail) != (rv.returncode != 0):
        raise SystemExit('Command did not end as expected!')

def check_same( f1, f2 ):
    f1 = Path(f1)
    f2 = Path(f2)
    if not f1.exists() and not f2.exists():
        #no files, no check
        return
    print(f"===> Checking that {f1.name} and {f2.name} have identical contents.")
    c1 = f1.read_bytes()
    c2 = f2.read_bytes()
    if f1.name.endswith('.gz'):
        c1 = gzip.decompress( c1 )
    if f2.name.endswith('.gz'):
        c2 = gzip.decompress( c2 )
    if c1 != c2:
        print("===> Check failed!")
        raise SystemExit(1)

def copy( src, tgt ):
    psrc = Path(src)
    if isinstance(tgt,str) and tgt == '.':
        ptgt = Path('.').joinpath(psrc.name)
    else:
        ptgt = Path(tgt)
    assert psrc.is_file()
    assert not ptgt.exists()
    ptgt.write_bytes(psrc.read_bytes())
    return ptgt
