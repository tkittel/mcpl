==================
MCPL documentation
==================

This directory contains the sources of the Sphinx-based MCPL website
(currently in development; the published website is still the one in the
gh-pages branch). To build and view it locally, either use the developer tool
from the repository root::

  ./devel/bin/mcpldevtool sphinx            # build in doc/build/html
  ./devel/bin/mcpldevtool sphinx --serve    # rebuild and serve on changes

or run ``sphinx-build -b html source build/html`` in this directory, and direct
your browser at ``doc/build/html/index.html``. The required Python packages (for Python 3.10 or
later) are listed in ``devel/reqs/requirements_doc.txt``, and Doxygen is also
needed (for the C++ API reference).

================
Reading material
================

* https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html
* https://breathe.readthedocs.io/
