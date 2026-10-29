<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/mctools/mcpl-logo/main/svg/mcpl-logo-dark.svg">
    <img alt="MCPL logo" src="https://raw.githubusercontent.com/mctools/mcpl-logo/main/svg/mcpl-logo.svg" width="420">
  </picture>
</p>

MCPL - Monte Carlo Particle Lists
=================================

MCPL files, with extensions `.mcpl` and `.mcpl.gz` is a binary format for usage
in physics particle simulations. It contains lists of particle state
information, and can be used to interchange or reuse particles between various
Monte Carlo simulation applications. The format itself is formally described in:

   T. Kittelmann, et al., Monte Carlo Particle Lists: MCPL, Computer Physics
   Communications 218, 17-42 (2017), https://doi.org/10.1016/j.cpc.2017.04.012
   (open access)

All MCPL code is provided under the highly liberal open source Apache 2.0
license (http://www.apache.org/licenses/LICENSE-2.0), and further instructions
and documentation can be found at https://mctools.github.io/mcpl/.



The mcpl-python package
-----------------------

The `mcpl-python` package provides a Python API for working with MCPL
files. More details about the Python API and how to use it can be found at the
https://mctools.github.io/mcpl/usage_python page.

Additionally, the package also provides the command-line tool `mcpltool`,
which can show the contents, statistics and plots of MCPL files, view them
interactively, merge, extract or repair files, and select or edit particles
with expressions.

Note that it is recommended for most users to simply install the package named
`mcpl`, rather than referring to the package named `mcpl-python` directly.



Scientific reference
--------------------

Copyright 2015-2026 MCPL developers.

This software was mainly developed at the European Spallation Source ERIC (ESS)
and the Technical University of Denmark (DTU). This work was supported in part
by the European Union's Horizon 2020 research and innovation programme under
grant agreement No 676548 (the BrightnESS project).

All MCPL files are distributed under the Apache 2.0 license, available at
http://www.apache.org/licenses/LICENSE-2.0, as well as in the LICENSE file found
in the source distribution.

A substantial effort went into developing MCPL. If you use it for your work, we
would appreciate it if you would use the following reference in your work:

   T. Kittelmann, et al., Monte Carlo Particle Lists: MCPL, Computer Physics
   Communications 218, 17-42 (2017), https://doi.org/10.1016/j.cpc.2017.04.012
   (open access)



Support for specific third party applications
---------------------------------------------

Note that some users might also wish to additionally install the `mcpl-extra`
package, which contains cmdline tools for converting between the binary data
files native to some third-party Monte Carlo applications (currently PHITS and
MCNP[X/5/6]). Users of Geant4 might wish to install the `mcpl-geant4` package,
which provides C++ classes (and CMake configuration code) for integrating MCPL
I/O into Geant4 simulations. Finally, many Monte Carlo applications have
directly integrated support for MCPL I/O into their codes. At the time of
writing, the list of applications with known support from MCPL I/O includes:

* McStas (built in)
* McXtrace (built in)
* OpenMC (built in)
* Cinema/Prompt (built in)
* VITESS (built in)
* RESTRAX/SIMRES (built in)
* McVine (built in)
* MCNPX, MCNP5, MCNP6 (based on `ssw2mcpl`/`mcpl2ssw` from the `mcpl-extra` package)
* PHITS (based on `phits2mcpl`/`mcpl2phits` from the `mcpl-extra` package)
* Geant4 (based on C++/CMake code from the `mcpl-geant4` package)

Note that instructions for installation and setup of third-party products like
those listed above are beyond the scope of the MCPL project. Please refer to the
products own instructions for more information.
