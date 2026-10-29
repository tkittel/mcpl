
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

def short_description():
    return ( 'Create the font cache of matplotlib and open a first Tk window'
             ' (e.g. before tests in CI)' )

def main( parser ):
    parser.init( short_description() )
    parser.parse_args()
    #(the first use of matplotlib, and the first Tk window on macOS, can take
    #very long, which tests of plots and of the viewer should not wait for):
    try:
        import matplotlib.font_manager  # noqa: F401
        print('The font cache of matplotlib is ready')
    except ImportError:
        print('matplotlib is not installed (no font cache made)')
    try:
        import tkinter
    except ImportError:
        print('tkinter is not available (no Tk window made)')
        return
    try:
        root = tkinter.Tk()
        root.update()
        root.destroy()
        print('A Tk window was made')
    except tkinter.TclError:
        print('Tk can not show windows here (no Tk window made)')
