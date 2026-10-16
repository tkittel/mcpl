**********
Using MCPL
**********

Using MCPL typically implies using pre-existing :doc:`plugins or
converters <hooks>` to either create or read a list of particles
from MCPL files via a given simulation tool, such as
:doc:`Geant4 <hooks_geant4>`, :doc:`McStas <hooks_mcstas>`,
:doc:`McXtrace <hooks_mcxtrace>`, :doc:`MCNP <hooks_mcnp>`, or
:doc:`PHITS <hooks_phits>`. Additionally, most users will find it
beneficial to use the generic :doc:`mcpltool <usage_cmdline>` command from
the command line, in order to inspect or perform operations on files, and some users with advanced
use-cases might write :doc:`C/C++ code <usage_c>` or :doc:`Python
code <usage_python>` in order to inspect or manipulate MCPL files
(for instance, to create new plugins or converters for their tools). Particles
can also be selected, edited and plotted
with short :doc:`expressions <usage_expressions>`, from the command line
or from Python.

.. container:: mcplcards

   .. container:: mcplcard

      .. container:: mcplcard-badge

         |arrows|

      :doc:`Application hooks <hooks>`

      Plugins and converters for Geant4, McStas, McXtrace, MCNP, PHITS and other applications.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         $_

      :doc:`Command line <usage_cmdline>`

      Inspect, merge, extract, repair and plot MCPL files with the mcpltool command.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         C

      :doc:`C API <usage_c>`

      Read and write MCPL files from C (or C++) code, with the mcpl.h header and the MCPL library.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         C++

      :doc:`C++ interface <usage_cpp>`

      The header-only mcplcpp.h, with exceptions, files which close automatically, and type-safe userdata.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         Py

      :doc:`Python <usage_python>`

      Read MCPL files from Python, with the particles in blocks of numpy arrays.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         Py+

      :doc:`Advanced Python <usage_python_advanced>`

      Create files, add userdata, compute statistics and plots, and merge files from Python.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         f(x)

      :doc:`Expressions <usage_expressions>`

      Select, edit and plot particles with short expressions, from the command line or from Python.

Many more details can be found in `the MCPL paper (section
2) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=section.2>`__ and in `the
MCPL paper (section
3) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=section.3>`__.

.. |arrows| unicode:: U+21C4

.. toctree::
   :hidden:

   usage_cmdline
   usage_c
   usage_cpp
   usage_python
   usage_python_advanced
   usage_expressions
