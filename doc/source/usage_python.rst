**********************
Using MCPL from Python
**********************

If desired, it is possible to access the content of MCPL files from Python code
by using the ``mcpl`` Python module described on this page, available since
MCPL release 1.2.0. Since MCPL release 3.0.0, the module can also be used to
create new MCPL files, and to select, edit, merge or plot particles.
Notice that most end-users should not normally have to write code in order to
use MCPL. Rather, they should be able to use pre-existing converters or plugins
for their Monte Carlo applications (c.f. :doc:`hooks <hooks>`).

This page shows the basic usage with short recipes, while more details are
given on the page about :doc:`advanced usage <usage_python_advanced>`,
and all classes and functions are described in the :doc:`API
reference <python_api>`.

.. _usage_python-reading-mcpl-files:

Reading MCPL files
------------------

.. _usage_python-opening-mcpl-files-and-accessing-particle-contents:

Opening MCPL files and accessing particle contents
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The simplest usage, opening an MCPL file and accessing the particle contents in
order, is straightforward:

.. code:: python

   import mcpl
   myfile = mcpl.MCPLFile("myfile.mcpl")
   for p in myfile.particles:
      print( p.x, p.y, p.z, p.ekin )

Here we access and print out the particle positions (units of cm) and kinetic
energies (units of MeV). The field names and units are the same as in the
:doc:`C/C++ <usage_c>` interface, and are documented directly via the
integrated help system of Python. Thus, one can get a full list of all
available data fields by adding a ``help(mcpl.MCPLFile)`` statement anywhere.

.. _usage_python-access-blocks-of-particles-for-efficiency:

Access blocks of particles for efficiency
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For large files, it can be much more efficient to load a large number of
particles at once, using instead the ``particle_blocks`` interface:

.. code:: python

   import mcpl
   myfile = mcpl.MCPLFile("myfile.mcpl")
   for p in myfile.particle_blocks:
      print( p.x, p.y, p.z, p.ekin )

The code looks similar to the non-block case above, but fields like ``p.x`` or
``p.ekin`` are now actually `NumPy <http://www.numpy.org/>`__ arrays rather
than single numbers. By default each block encompasses 10000 particles, a
number which can be tuned by adding a ``blocklength`` parameter when
instantiating a new ``MCPLFile`` object. Of course, unless the number of
particles in the file is a multiple of ``blocklength``, the last block in the
file will have fewer particles (and shorter arrays).

.. _usage_python-access-file-level-meta-data:

Access file-level meta-data
~~~~~~~~~~~~~~~~~~~~~~~~~~~

In addition to particle contents, it is of course also possible to access
file-level meta-data, as can be seen in this example:

.. code:: python

   import mcpl
   myfile = mcpl.MCPLFile("myfile.mcpl")
   print( 'Particles:', myfile.nparticles )
   print( 'Created by:', myfile.sourcename )
   if myfile.opt_polarisation:
       print( 'File has polarisation info' )
   for c in myfile.comments:
       print( 'Comment:', c )

For a full list of all available meta-data fields, one can access the
integrated documentation by adding a line with ``help(mcpl.MCPLFile)``.

.. _usage_python-quick-recipes:

Quick recipes
-------------

.. _usage_python-creating-a-file:

Creating a file
~~~~~~~~~~~~~~~

Particles are added to new files in blocks, with the particle data given as
NumPy arrays (or single values used for all particles):

.. code:: python

   import mcpl
   import numpy as np

   n = 1000
   with mcpl.MCPLOutFile( "myfile.mcpl" ) as f:
       f.add_particles(
           pdgcode = 2112,  # all are neutrons
           position = np.zeros((n,3)),
           direction = (0.0, 0.0, 1.0),  # all same
           ekin = np.linspace(1e-9, 1e-6, n),
           weight = 1.0 )

Positions are in cm, kinetic energies in MeV, and times in ms. See the
:ref:`advanced usage <usage_python_advanced-creating-mcpl-files>` for the
header information and file settings.

.. _usage_python-selecting-and-editing-particles:

Selecting and editing particles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Particles can be selected and edited with short
:doc:`expressions <usage_expressions>`, for instance when copying them
into a new file. Here the neutrons below 25 meV within 5 cm of the z axis are
copied, rotated 90 degrees around the z axis and moved 1 m along it:

.. code:: python

   import mcpl
   sel = ( "pdgcode == neutron && ekin < 25meV"
           " && hypot(x,y) < 5cm" )
   edit = "rotate_z(90deg), z += 1m"
   fin = mcpl.MCPLFile( "input.mcpl", select = sel,
                        edit = edit )
   with mcpl.MCPLOutFile( "output.mcpl" ) as fout:
       fout.transfer_metadata( fin )  # copy header
       for block in fin.particle_blocks:
           fout.add_particles( block )

.. _usage_python-merging-files:

Merging files
~~~~~~~~~~~~~

.. code:: python

   import mcpl
   files = [ "file1.mcpl", "file2.mcpl" ]
   with mcpl.merge_files( "out.mcpl", files ) as f:
       print( "Particles:", f.nparticles )

.. _usage_python-per-particle-userdata:

Per-particle userdata
~~~~~~~~~~~~~~~~~~~~~

Particles can carry custom data beyond the 32 bit ``userflags``, described by a
layout of named fields (see the :ref:`advanced
usage <usage_python_advanced-per-particle-userdata>`):

.. code:: python

   import mcpl
   layout = "temp:float32,volume:int32"
   f = mcpl.MCPLOutFile( "out.mcpl",
                         userdata_layout = layout )
   with f:
       f.add_particles( ..., userdata = {
           "temp" : temps, "volume" : volumes } )
   with mcpl.MCPLFile( "out.mcpl" ) as f:
       for block in f.particle_blocks:
           print( block.userdata["temp"].mean() )

.. _usage_python-plotting:

Plotting
~~~~~~~~

Histograms of any quantity can be plotted (or saved in files) with
:ref:`expressions <usage_expressions-histograms>`. Here the angles (in
degrees) between the z axis and the directions of the neutrons above 1 keV are
shown, as a curve for each half of the x-y plane:

.. code:: python

   import mcpl
   h = mcpl.histogram(
       "myfile.mcpl", "acos(uz)/deg",
       select = "pdgcode == neutron && ekin > 1keV",
       split = "x > 0cm", range = (0, 90) )
   h.plot()  # or h.plot( filename = "angles.pdf" )

And plots of all the particle data, like those of ``mcpltool --stats`` on the
:ref:`command line <usage_cmdline-extract-statistics-from-a-file>`, are
made with (this also works with earlier MCPL releases):

.. code:: python

   import mcpl
   mcpl.plot_stats( "myfile.mcpl" )

.. _usage_python-where-to-find-more-documentation:

Where to find more documentation
--------------------------------

Python's integrated ``help()`` function shows the documentation of the
``mcpl`` module and its classes and functions, and the same documentation is in
the :doc:`Python API reference <python_api>`.

More complete examples can be found in
`pyexample_readmcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_readmcpl>`__,
`pyexample_writemcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_writemcpl>`__,
`pyexample_filtermcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_filtermcpl>`__
and
`pyexample_editmcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_editmcpl>`__.
