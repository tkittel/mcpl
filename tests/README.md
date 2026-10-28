MCPL unit tests
---------------

This subdirectory adds a suite of unit tests for MCPL. The primary way to
exercise them is to configure and build (but not install) the CMake project at
the root of the repository (i.e. one level up from here), with the option
`MCPL_ENABLE_TESTING=ON`, and then subsequently launch the tests via
ctest. Additionally, the `MCPLEXTRA_ADDITIONAL_TESTS` option can be used to add
extra tests not residing in this repository.

Alternatively, one can also use the developer command `mcpldevtool` from the
folder at `<reporoot>/devel/bin` (on unix one can inject it into the PATH by
sourcing the script at `<reporoot>/devel/setup.sh`). With that, one can simply
launch the tests via the command `mcpldevtool cmake`.

Note that in addition to the tests here, the command `mcpldevtool check` provides
several fast checks of the repository based on static code inspection.
