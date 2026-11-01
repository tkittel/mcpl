
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

# NEEDS: numpy matplotlib tkinter

# The tests of the viewer in real Tk windows (on Linux and FreeBSD in CI with a
# virtual display, Xvfb), run one after the other, as their windows would
# take the keyboard focus from each other if they ran at the same time: the
# test of the Tk front end (MCPLTestUtils.viewer_tk) and the random use of the
# viewer (MCPLTestUtils.viewer_monkey). Each runs in its own process (as they
# change things in the modules of the viewer, e.g. how windows are made), in
# a directory of its own, and its output is shown here.

import pathlib
import subprocess
import sys

for name in ( 'viewer_tk', 'viewer_monkey' ):
    print(f'==> {name}',flush=True)
    rundir = pathlib.Path(name)
    rundir.mkdir()
    p = subprocess.run([ sys.executable, '-m', f'MCPLTestUtils.{name}' ],cwd=rundir,
                       capture_output=True,text=True,encoding='utf-8',check=False)
    sys.stdout.write(p.stdout)
    sys.stdout.flush()
    if p.stderr:
        sys.stderr.write(p.stderr)
    if p.returncode != 0:
        raise SystemExit(f'{name} failed (exit code {p.returncode})')
