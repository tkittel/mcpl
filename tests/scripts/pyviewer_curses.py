
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

# The viewer in the terminal (mcpltool -w -t) on a real terminal, with curses:
# it is started in a pseudo-terminal, which shows the file, takes keys and
# quits with q, printing the commands doing the same. (The parts of the
# terminal viewer are tested with a screen in memory by pyviewer; this checks
# that it works with curses.) Without a reference log, as nothing is done on
# Windows, which has no pseudo-terminals.

import sys

if sys.platform == 'win32':
    print('Not tested on Windows (no pseudo-terminals)')
    raise SystemExit(0)

import fcntl
import os
import re
import select
import shutil
import struct
import subprocess
import termios
import time

from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

master, slave = os.openpty()
#(a terminal of 120x40 characters):
fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,120,0,0))
env = dict(os.environ,TERM='xterm-256color')
p = subprocess.Popen([ sys.executable, '-m', 'mcpldev', '-w', '-t', 'example.mcpl' ],
                     stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True)
os.close(slave)
output = []

def text():
    """What was written to the terminal so far, without the escape sequences
    of curses"""
    s = b''.join(output).decode('utf-8','replace')
    return re.sub(r'\x1b(\[[0-9;?]*[A-Za-z@]|[()][A-Z0-9]|[=>78M])','',s)

def read( seconds ):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        r, _, _ = select.select([ master ],[],[],0.05)
        if r:
            try:
                data = os.read(master,65536)
            except OSError:#(the terminal is closed when the viewer ends)
                return
            if not data:
                return
            output.append(data)

def wait_for( what, seconds = 60 ):
    end = time.monotonic() + seconds
    while what not in text():
        assert time.monotonic() < end and p.poll() is None, (
            f'{what!r} not shown in the terminal, which shows:\n{text()[-3000:]}' )
        read(0.2)

wait_for('example.mcpl')
print('the viewer shows the file')
#(Down, Down and Up, which show other views, as sent by terminals in the
#keypad mode of curses):
shown = len(text())
for key in ( b'\x1bOB', b'\x1bOB', b'\x1bOA' ):
    os.write(master,key)
    read(0.5)
assert p.poll() is None, f'the viewer ended after keys:\n{text()[-3000:]}'
assert len(text()) > shown, 'the keys did not change what the terminal shows'
print('the viewer takes keys')
os.write(master,b'q')
end = time.monotonic() + 60
while p.poll() is None and time.monotonic() < end:
    read(0.2)
read(0.5)
os.close(master)
assert p.poll() == 0, f'exit code {p.poll()}:\n{text()[-3000:]}'
assert 'To open the viewer like this again:' in text(), text()[-3000:]
print('the viewer quits with q, printing the commands doing the same')
