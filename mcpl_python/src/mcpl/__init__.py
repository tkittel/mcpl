
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

"""Python package for reading, writing and processing MCPL files.

The MCPL (Monte Carlo Particle Lists) format is thoroughly documented on the
project homepage, from where it is also possible to download the entire MCPL
distribution:

     https://mctools.github.io/mcpl/

Specifically, more documentation about how to use the present Python package
can be found at:

     https://mctools.github.io/mcpl/usage_python/

This package can be freely used as per the terms in the LICENSE file distributed with
MCPL, also available at https://github.com/mctools/mcpl/blob/master/LICENSE .

A substantial effort went into developing MCPL. If you use it for your work, we
would appreciate it if you would use the following reference in your work:

   T. Kittelmann, et al., Monte Carlo Particle Lists: MCPL, Computer Physics
   Communications 218, 17-42 (2017), https://doi.org/10.1016/j.cpc.2017.04.012

The mcpl Python package was written by Thomas Kittelmann, 2017-2026. The work
was supported by the European Union's Horizon 2020 research and innovation
programme under grant agreement No 676548 (the BrightnESS project)
"""

__all__ = [
            'MCPLError',
            'MCPLFile',
            'MCPLOutFile',
            'MCPLParticle',
            'MCPLParticleBlock',
            'ParticleEdit',
            'ParticleFilter',
            'ParticleValue',
            'app_mcpltool',
            'app_pymcpltool',
            'can_merge',
            'collect_stats',
            'constants',
            'convert2ascii',
            'create_outfile_mpi',
            'dump_file',
            'dump_stats',
            'encode_stat_sum',
            'forcemerge_files',
            'gzip_file',
            'histogram',
            'histogram2d',
            'is_valid_stat_sum_key',
            'merge_files',
            'merge_inplace',
            'merge_outfiles_mpi',
            'name_helper',
            'plot_histograms',
            'plot_stats',
            'plotting',
            'repair',
            'use_logging',
            'view',
           ]

__version__ = '2.2.9'

from . import constants
from ._blocks import MCPLParticle, MCPLParticleBlock
from ._common import MCPLError
from ._fileops import (
            can_merge,
            convert2ascii,
            create_outfile_mpi,
            dump_file,
            forcemerge_files,
            merge_files,
            merge_inplace,
            merge_outfiles_mpi,
            name_helper,
            repair,
)
from ._messages import use_logging
from ._reader import MCPLFile
from ._statsum import encode_stat_sum, is_valid_stat_sum_key
from ._writer import MCPLOutFile, gzip_file

#Expressions, statistics, histograms, plotting and the mcpltool command are
#only imported when used (so the code for reading and writing files does not
#depend on them in any way):
_on_demand = {
    'ParticleEdit' : '_expressions',
    'ParticleFilter' : '_expressions',
    'ParticleValue' : '_expressions',
    'app_mcpltool' : '_cli',
    'app_pymcpltool' : '_cli',
    'collect_stats' : '_stats',
    'dump_stats' : '_stats',
    'histogram' : '_histogram',
    'histogram2d' : '_histogram',
    'plot_histograms' : '_histogram',
    'plot_stats' : '_stats',
    'plotting' : 'plotting',
    'view' : '_viewer',
}

def __getattr__(name):
    modname = _on_demand.get(name)
    if modname is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    import importlib
    mod = importlib.import_module(f'.{modname}',__name__)
    obj = mod if name == modname else getattr(mod,name)
    globals()[name] = obj
    return obj

def __dir__():
    return sorted(set(globals()) | set(__all__))
