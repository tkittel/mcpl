# Distribution packaging

## Debian

The `debian/` subdirectory contains the template for building Debian packages of
MCPL (also for derivatives like Ubuntu). It needs Debian 13 (trixie) or Ubuntu
26.04, or later. For Ubuntu 24.04, see below.

To build the packages, run the following in the root directory of an MCPL
source tree. Nothing needs to be installed beforehand: `apt build-dep` installs
everything needed for the build (dpkg-buildpackage, debhelper, cmake, compilers,
Python build tools, ...), as listed in `debian/control`.

```
devel/packaging/prepare-debian
sudo apt build-dep ./
dpkg-buildpackage -b -us -uc
```

`prepare-debian` copies the template to `debian/`, names the library package
after the major version in the `VERSION` file (`libmcpl<major>`), and writes
`debian/changelog` with that version.

The packages (`.deb` files) end up in the parent directory. To check them with
`lintian *.changes`, or to run the package tests in `debian/tests` on the
installed packages with `autopkgtest`, first `sudo apt install lintian
autopkgtest`.

For Ubuntu 24.04, whose Python build tools are older, use
`devel/packaging/prepare-debian --ubuntu2404` instead, which also applies
`ubuntu2404.patch`.

Binary packages (`apt install mcpl` installs all but `mcpl-extra`, like the
`mcpl` packages on PyPI and conda-forge):

- `libmcpl<major>`: the shared library (named after its SONAME, see above).
- `libmcpl-dev`: headers and CMake files.
- `python3-mcpl`: the MCPL Python module.
- `mcpl`: the command-line tools `mcpltool` and `mcpl-config` (not the
  deprecated `pymcpltool`).
- `mcpl-extra`: the converters for MCNP (`ssw2mcpl`, `mcpl2ssw`) and PHITS
  (`phits2mcpl`, `mcpl2phits`).

Notes:

- The build runs the test suite of the repository (`DEB_BUILD_OPTIONS=nocheck`
  skips it).
- Man pages are generated from the `--help` output of the commands, which come
  from `[project.scripts]` in `mcpl_python/pyproject.toml` and
  `mcpl_extra/pyproject.toml` (plus `mcpl-config`). New commands need a
  description in `debian/genmanpages` and an entry in the `.install` file of
  their package.
- Packages are built with `-O3 -DNDEBUG`, as in upstream's default builds.
  `DEB_BUILD_OPTIONS=noopt` gives a debug build (`-O0`, assertions enabled).
  Debug symbols go into the `-dbgsym` packages (or stay in the binaries with
  `DEB_BUILD_OPTIONS=nostrip`).
