
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
    return 'Update INSTALL.md from doc/install_source.md'

def main( parser ):
    parser.init( """Generate INSTALL.md from doc/install_source.md (which is
    also the source of the "Building from source" page of the website).""" )
    parser.add_argument( '--rst', action='store_true',
                         help="""Print the reST of the website page instead
                         (for inspection)""" )
    args = parser.parse_args()
    from . import installdoc
    if args.rst:
        print( installdoc.produce_get_source_rst(), end='' )
        return
    if installdoc.check_install_md():
        print(f'{installdoc.install_md_relpath} is already up to date')
    else:
        installdoc.check_install_md( fix = True )
