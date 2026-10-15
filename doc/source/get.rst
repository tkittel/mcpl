********
Get MCPL
********

The easiest way to install MCPL is via the prebuilt Python or Conda packages.
The package named ``mcpl`` provides both :doc:`command-line
tools <usage_cmdline>`, and APIs for :doc:`C/C++ <usage_c>`,
:doc:`Python <usage_python>`, and CMake configuration.

Additionally, the package named ``mcpl-extra`` provides (as the name indicates)
extra optional utilities such as optional converters between MCPL and other
file formats.

.. _get-install-via-python-tools:

Install via Python tools
------------------------

Complete MCPL packages are provided as wheels on PyPI, and installation is as
simple as:

::

   pip install mcpl mcpl-extra

As noted above, the ``mcpl-extra`` package is optional.

.. _get-install-via-conda:

Install via Conda
-----------------

If using conda, you can simply install MCPL from the
`conda-forge <https://conda-forge.org/>`__ channel. Thus:

::

   conda install -c conda-forge mcpl mcpl-extra

As noted above, the ``mcpl-extra`` package is optional.

For consistency, it is recommended that your conda environment ONLY uses
packages from the conda-forge channel.

.. _get-custom-builds-expert-only:

Custom builds (expert only)
---------------------------

Experts might wish to build MCPL packages manually. Please refer to the
instructions `here <https://github.com/mctools/mcpl/blob/HEAD/INSTALL.md>`__
for more details.
