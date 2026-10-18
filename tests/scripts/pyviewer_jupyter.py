
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


# NEEDS: numpy matplotlib ipywidgets

# Test the viewer in Jupyter (the panel of ipywidgets, without a notebook).

import shutil

from mcpldev._viewer import Viewer
from mcpldev._viewer_jupyter import JupyterViewer
from MCPLTestUtils.dirs import test_data_dir

shutil.copy( test_data_dir / 'example.mcpl', 'example.mcpl' )

v = Viewer('example.mcpl')
j = JupyterViewer(v)
j.start()
v.wait()
j.refresh()
print('views:', len(j._views.options))
print('status:', j._status.value)
#The overview, as a grid of its plots with buttons:
print('overview as a grid:', j._right.children[1] is j._grid,
      'plots:', all( i.value[:4] == b'\x89PNG' for i in j._panels.values() ))
print('buttons:', [ c.children[1].description for c in j._grid.children ])
j._grid.children[1].children[1].click()
print('view after the button of wavelength:', v.views[v.current][0],
      'selected in the list:', j._views.index == v.current,
      'single image:', j._right.children[1] is j._image)
#An edit changes the plot shown (also with the polling thread running):
j._views.index = [ k for k, _ in v.views ].index('ekin')
before = j._image.value
j._fields['edit'].value = 'ekin += 1000MeV'
v.wait()
j.refresh()
print('plot changed by the edit:', j._image.value != before,
      'polling thread alive:', j._thread.is_alive())
j._fields['edit'].value = ''
v.wait()
j._views.index = 0
j._fields['pick'].value = 'pdgcode == neutron'
v.wait()
j.refresh()
print('status after the pick:', j._status.value)
j._fields['edit'].value = 'x = 2'
print('message for an invalid edit:', j._message.value)
j._fields['plot'].value = 'ekin/MeV;logx=1'
v.wait()
j.refresh()
print('view:', j._views.options[j._views.index], 'field emptied:', j._fields['plot'].value == '')
print('This plot box shown:', j._change.layout.display != 'none', repr(j._change.value))
j._change.value = 'ekin/keV;logx=1'
v.wait()
j.refresh()
print('changed in the box:', [ k for k, _ in v.views ][-1], 'current:', v.views[v.current][0],
      'message:', repr(j._message.value))
j._change.value = ''
v.wait()
j.refresh()
print('emptied, plot removed:', [ k for k, _ in v.views ][-1], 'box shown:', j._change.layout.display != 'none')
j._views.index = 3
print('view selected:', v.views[v.current][0])
print('suggested name:', j._filename.value)
j._on_write(None)
print('written:', j._message.value)
print('next name:', j._filename.value)
j._on_help(None)
print('help shown:', j._extra.value.startswith('<pre>The viewer'))
print('command:', j._commands.value)
j.close()
