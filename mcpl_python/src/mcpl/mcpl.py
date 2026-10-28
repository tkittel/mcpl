
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

"""The mcpl.mcpl module of earlier releases, kept for backwards compatibility.

All the names are available directly in the mcpl package (after "import mcpl"),
which is how they should be used. Using them from mcpl.mcpl gives a
DeprecationWarning (except for main, which is the entry point of the mcpltool command (or
pymcpltool, as it was called before) in some installations).
"""

__all__ = [
    'MCPLError',  # noqa: F822
    'MCPLFile',  # noqa: F822
    'MCPLParticle',  # noqa: F822
    'MCPLParticleBlock',  # noqa: F822
    'app_pymcpltool',  # noqa: F822
    'collect_stats',  # noqa: F822
    'convert2ascii',  # noqa: F822
    'dump_file',  # noqa: F822
    'dump_stats',  # noqa: F822
    'encode_stat_sum',  # noqa: F822
    'is_valid_stat_sum_key',  # noqa: F822
    'main',
    'plot_stats',  # noqa: F822
]

from . import _blocks, _cli, _common, _fileops, _reader, _stats, _statsum
from ._cli import main

_moved = {
    '__version__': _common,
    'MCPLError': _common,
    'MCPLFile': _reader,
    'MCPLParticle': _blocks,
    'MCPLParticleBlock': _blocks,
    'app_pymcpltool': _cli,
    'collect_stats': _stats,
    'convert2ascii': _fileops,
    'dump_file': _fileops,
    'dump_stats': _stats,
    'encode_stat_sum': _statsum,
    'is_valid_stat_sum_key': _statsum,
    'plot_stats': _stats,
}

def __getattr__(name):
    mod = _moved.get(name)
    if mod is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    import warnings
    warnings.warn(f'mcpl.mcpl.{name} is deprecated, use mcpl.{name} (after'
                  ' "import mcpl") instead', DeprecationWarning, stacklevel=2)
    obj = getattr(mod, name)
    #Only warn on the first use:
    globals()[name] = obj
    return obj

def __dir__():
    return sorted(set(__all__) | {'__version__'})

if __name__ == '__main__':
    main()
