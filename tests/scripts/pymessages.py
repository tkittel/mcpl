
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


# NEEDS: numpy

# Test that messages and warnings are printed by default, sent to the logger
# "mcpl" after use_logging(), and always printed by mcpltool. Also test the
# --traceback option of mcpltool.

import logging
import subprocess
import sys

import mcpldev as mcpl
from MCPLTestUtils.dirs import test_data_dir

files = [ test_data_dir.joinpath('ref', fn)
          for fn in ('ref_statsum_crash.mcpl', 'ref_statunsupported.mcpl.gz') ]

class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
    def emit(self, record):
        self.records.append(record)

def open_files():
    for f in files:
        print(f'--> Opening {f.name}')
        with mcpl.MCPLFile(f):
            pass

def run_tool(*args):
    print(f'--> Running mcpltool {" ".join(args)}')
    sys.stdout.flush()
    rv = subprocess.run([sys.executable, '-m', 'mcpldev', *args],
                        capture_output=True, text=True, check=False)
    print(f'    exit code: {rv.returncode}')
    for line in rv.stdout.splitlines():
        print(f'    stdout: {line}')
    if rv.stderr:
        print(f'    last line of stderr: {rv.stderr.splitlines()[-1]}')

def main():
    print('==> By default, warnings are printed:')
    open_files()

    handler = ListHandler()
    logger = logging.getLogger('mcpl')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    print('==> After use_logging(), they are sent to the logger:')
    mcpl.use_logging()
    open_files()
    for r in handler.records:
        print(f'    logged by "{r.name}" with level {r.levelname}: {r.getMessage()}')
    nrecords = len(handler.records)

    print('==> mcpltool always prints:')
    try:
        mcpl.app_mcpltool(['mcpltool', '-n', '-l1', str(files[0])])
    except SystemExit as e:
        print(f'--> mcpltool exited with code {e.code}')
    assert len(handler.records) == nrecords

    print('==> After use_logging(False), warnings are printed again:')
    mcpl.use_logging(False)
    open_files()
    assert len(handler.records) == nrecords

    print('==> Errors in mcpltool, with and without --traceback:')
    run_tool('nonexistent.mcpl')
    run_tool('--traceback', 'nonexistent.mcpl')
    run_tool('--trace', 'nonexistent.mcpl')

    print('==> Program name in the usage with "python -m mcpl":')
    rv = subprocess.run([sys.executable, '-m', 'mcpldev', '--help'],
                        capture_output=True, text=True, check=True)
    lines = rv.stdout.splitlines()
    print(f'    {lines[lines.index("Usage:")+1]}')

    print('==> The old pymcpltool command warns, and works like mcpltool:')
    code = ( 'import sys;sys.argv[0]="pymcpltool";'
             'from mcpldev._cli import _main_pymcpltool as m;m()' )
    rv = subprocess.run([sys.executable, '-c', code, '-j', str(files[1])],
                        capture_output=True, text=True, check=True)
    for line in rv.stdout.splitlines()[:3]:
        print(f'    stdout: {line}')

if __name__ == '__main__':
    main()
