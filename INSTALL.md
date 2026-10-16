Standard installation
=====================

The recommended manner in which to install MCPL is via prebuilt Conda or Python
packages which are available for most modern platforms (including Linux, macOS,
and Windows for both Intel, AMD and ARM platforms):

If using conda, the `mcpl` package can be installed from the conda-forge
channel, by running the command (the `mcpl-extra` package can be installed in a
similar manner):

```
conda install conda-forge::mcpl
```

![Conda Version](https://img.shields.io/conda/v/conda-forge/mcpl)
![Conda Platform](https://img.shields.io/conda/pn/conda-forge/mcpl-core)
![Conda Downloads](https://img.shields.io/conda/dn/conda-forge/mcpl)

For consistency, it is recommended that your conda environment ONLY uses
packages from the conda-forge channel.

If not using conda, MCPL packages can be installed via a Python installation
tool like `pip`, via the command (again, the `mcpl-extra` package can be
installed in a similar manner):

```
pip install mcpl
```

The `mcpl` Python package only needs `numpy`. To also install matplotlib,
which is needed for plots in windows and in .pdf, .png or .svg files, use the
extra `[plot]` (or `[all]`), for instance:

```
pip install "mcpl[plot]"
```

![PyPI - Version](https://img.shields.io/pypi/v/mcpl)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mcpl)




Building from source (experts)
==============================

Advanced users might wish to build MCPL code from the sources in the upstream
repository (https://github.com/mctools/mcpl). This is considered an
expert-only procedure, but it *is* based on standard tools such as CMake and
`pyproject.toml` so should hopefully be somewhat straight forward. A brief
high-level description will be given in the following, but feel free to reach
out and ask questions on https://github.com/mctools/mcpl/discussions in case
something is not clear, or if you run into issues.

Note that to avoid potential conflicts, it is highly recommended that you
uninstall any existing MCPL packages from your environment before performing
manual installations! If you are in a conda environment, you should ensure that
only the conda-forge channel is enabled, and that the following packages are
also installed into the conda environment: `c-compiler`, `cmake`, and `make`
(unix only), `zlib`, `numpy`, `pip`, and `python`.

The repository contains one directory for each package: `mcpl_core`
(`mcpl-core`: the C library, header files, `mcpltool` and `mcpl-config`),
`mcpl_python` (`mcpl-python`: the `mcpl` Python module and `pymcpltool`),
`mcpl_extra` (`mcpl-extra`: the converters for MCNP and PHITS) and
`mcpl_metapkg` (`mcpl`: a package which only depends on `mcpl-core` and
`mcpl-python`).




Installation with pip
---------------------

From the root of a clone of the repository, the Python packages can be built
and installed with `pip` (Python 3.9 or later):

```
pip install ./mcpl_core ./mcpl_python ./mcpl_metapkg
```

The `mcpl-extra` package must be built against the `mcpl-core` package
installed above, which requires the build dependencies to be installed first,
and the build isolation of `pip` to be disabled:

```
pip install scikit-build-core
pip install --no-build-isolation ./mcpl_extra
```




Installation with CMake
-----------------------

The `mcpl_core` and `mcpl_extra` directories can also be built and installed
as regular CMake projects (needing CMake 3.16 or later, a C compiler, and zlib),
here into the directory `/path/to/install`:

```
cmake -S mcpl_core -B build_core -DCMAKE_INSTALL_PREFIX=/path/to/install
cmake --build build_core
cmake --install build_core
cmake -S mcpl_extra -B build_extra -DCMAKE_INSTALL_PREFIX=/path/to/install \
      -DCMAKE_PREFIX_PATH=/path/to/install
cmake --build build_extra
cmake --install build_extra
```

The `mcpl-config` command in `/path/to/install/bin` provides information about
the installation (e.g. `mcpl-config --show libdir`), and downstream CMake
projects can use the installation with `find_package(MCPL)` (see the
`examples/downstream_cmake` directory).




Running the tests
-----------------

Note that the CTests defined in `tests/` are only meant to be invoked by running
CMake on the root of the source repository, while actual packages with code is
meant to be build by running CMake on the `mcpl_xxx/` directory in
question. There is for various reasons (mostly lack of manpower) no support for
running CTests directly on a `mcpl_xxx/` subdirectory. For instance:

```
cmake -S . -B build_tests -DMCPL_ENABLE_TESTING=ON
cmake --build build_tests
ctest --test-dir build_tests
```

Developers can also use the `devel/bin/mcpldevtool` command (e.g.
`mcpldevtool cmake` to build and run the tests, and `mcpldevtool check` for
static code checks).
