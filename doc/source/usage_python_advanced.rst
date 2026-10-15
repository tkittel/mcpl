**********************************
Advanced usage of MCPL from Python
**********************************

This page describes the ``mcpl`` Python module in more detail than the :doc:`basic
usage <usage_python>` page, which also describes how to read MCPL
files. Most of the functionality described here is only available starting with
the next MCPL release.

The ``mcpl`` module is implemented in pure Python, using
`NumPy <http://www.numpy.org/>`__ to efficiently process blocks of particles.
When writing files, it produces exactly the same files as the
:doc:`C/C++ <usage_c>` interface.

.. _usage_python_advanced-creating-mcpl-files:

Creating MCPL files
-------------------

.. _usage_python_advanced-writing-blocks-of-particles:

Writing blocks of particles
~~~~~~~~~~~~~~~~~~~~~~~~~~~

New MCPL files are created with the ``MCPLOutFile`` class. Like when reading
files, particles are most efficiently handled in blocks, with the particle data
given as NumPy arrays:

.. code:: python

   import mcpl
   import numpy as np

   n = 1000
   f = mcpl.MCPLOutFile( "myfile.mcpl",
                         sourcename = "MySim" )
   with f:
       f.hdr_add_comment( "Relative to the sample" )
       f.add_particles(
           pdgcode = 2112,  # all are neutrons
           position = np.zeros((n,3)),
           direction = (0.0, 0.0, 1.0),  # all same
           ekin = np.linspace(1e-9, 1e-6, n),
           time = np.zeros(n),
           weight = 1.0 )

The particle fields have the same names as when reading files: ``position`` (or
``x``, ``y`` and ``z``), ``direction`` (or ``ux``, ``uy`` and ``uz``),
``polarisation`` (or ``polx``, ``poly`` and ``polz``), ``ekin``, ``time``,
``weight``, ``pdgcode``, and ``userflags``. Each field can be given as an array
with one value per particle, or as a single value used for all particles in the
block. Fields which are not given are set to zero, except that the direction
must always be specified (as a unit vector). Note that the file is closed
automatically at the end of the ``with`` block, otherwise one must call
``close()`` when done.

.. _usage_python_advanced-adding-single-particles:

Adding single particles
~~~~~~~~~~~~~~~~~~~~~~~

Particles can also be added one at a time, with the same field names. They are
internally collected and written in blocks, so this is also reasonably
efficient:

.. code:: python

   with mcpl.MCPLOutFile( "myfile.mcpl" ) as f:
       f.add_particle( pdgcode = 22,
                       position = (1.0, 2.0, 3.0),
                       direction = (0.0, 1.0, 0.0),
                       ekin = 0.5, weight = 1.0 )

.. _usage_python_advanced-header-information-and-file-settings:

Header information and file settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The header of the file can be configured with keyword arguments when creating
the ``MCPLOutFile``, named like the corresponding attributes of ``MCPLFile``
objects when reading files, and/or with methods named like the corresponding
functions in the :doc:`C/C++ <usage_c>` interface (without the ``mcpl_``
prefix). The two can be freely mixed:

+---------------------------------+------------------------------------+----------------------------------------+
| Keyword argument                | Method                             | Meaning                                |
+=================================+====================================+========================================+
| ``sourcename = "..."``          | ``hdr_set_srcname("...")``         | Name of the application which created  |
|                                 |                                    | the file                               |
+---------------------------------+------------------------------------+----------------------------------------+
| ``comments = [...]``            | ``hdr_add_comment("...")``         | Human-readable comments                |
+---------------------------------+------------------------------------+----------------------------------------+
| ``blobs = { key : data }``      | ``hdr_add_data(key, data)``        | Binary data (bytes) stored under a key |
+---------------------------------+------------------------------------+----------------------------------------+
| ``stat_sum = { key : value }``  | ``hdr_add_stat_sum(key, value)``   | :doc:`stat:sum <format_statsum>`       |
|                                 |                                    | entries                                |
+---------------------------------+------------------------------------+----------------------------------------+
| ``opt_userflags = True``        | ``enable_userflags()``             | Store 32 bit user-flags for each       |
|                                 |                                    | particle                               |
+---------------------------------+------------------------------------+----------------------------------------+
| ``opt_polarisation = True``     | ``enable_polarisation()``          | Store polarisation vectors             |
+---------------------------------+------------------------------------+----------------------------------------+
| ``opt_singleprec = False``      | ``enable_doubleprec()``            | Store numbers in double precision      |
+---------------------------------+------------------------------------+----------------------------------------+
| ``opt_universalpdgcode = 2112`` | ``enable_universal_pdgcode(2112)`` | All particles have the same type       |
+---------------------------------+------------------------------------+----------------------------------------+
| ``opt_universalweight = 1.0``   | ``enable_universal_weight(1.0)``   | All particles have the same weight     |
+---------------------------------+------------------------------------+----------------------------------------+

For example:

.. code:: python

   f = mcpl.MCPLOutFile( "myfile.mcpl",
                         sourcename = "MySim",
                         opt_polarisation = True )
   with f:
       f.hdr_add_comment( "Some comment" )
       f.hdr_add_data( "config", b"binary data" )
       f.enable_universal_pdgcode( 2112 )
       f.add_particles( ... )

As in the C/C++ interface, all of the header must be set up before the first
particle is added. The only exception is the values of
:doc:`stat:sum <format_statsum>` entries, which can be updated until the
file is closed, as long as the entry was added before the first particle (for
instance with the special value -1 meaning "not available"):

.. code:: python

   f = mcpl.MCPLOutFile( "myfile.mcpl",
                         stat_sum = { "nsim" : -1 } )
   with f:
       nsim = 0
       for i in range(10):
           ... # simulate 1000 particles, add
               # interesting ones to f
           nsim += 1000
       f.hdr_add_stat_sum( "nsim", nsim )

.. _usage_python_advanced-gzipped-output:

Gzipped output
~~~~~~~~~~~~~~

Calling ``closeandgzip()`` instead of ``close()`` results in a compressed file,
named with an additional ``.gz`` extension. Such files can be read directly by
MCPL:

.. code:: python

   f = mcpl.MCPLOutFile( "myfile.mcpl" )
   f.add_particles( ... )
   f.closeandgzip() # creates myfile.mcpl.gz

.. _usage_python_advanced-copying-filtering-or-converting-existing-files:

Copying, filtering or converting existing files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Blocks of particles read with ``MCPLFile`` can be passed directly to
``add_particles``, in which case the particle data is transferred exactly. The
whole header of an existing file, including its settings, can be copied with
``transfer_metadata`` (as in the next section). To change the settings, parts
of the header can instead be copied individually. For instance, the following
copies a file while changing its settings to use double precision and to drop
polarisation information (any binary blobs and stat:sum entries are not copied
here, but could be with ``hdr_add_data`` and ``hdr_add_stat_sum``):

.. code:: python

   fin = mcpl.MCPLFile( "input.mcpl" )
   fout = mcpl.MCPLOutFile( "output.mcpl",
                            opt_singleprec = False )
   with fin, fout:
       fout.hdr_set_srcname( fin.sourcename )
       for c in fin.comments:
           fout.hdr_add_comment( c )
       for block in fin.particle_blocks:
           fout.add_particles( block )

.. _usage_python_advanced-selecting-and-editing-particles:

Selecting and editing particles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Indexing a block of particles with a NumPy mask (or with an array of indices,
or a slice) gives a new block with just those particles, which can be passed to
``add_particles`` like any other block. Here, only neutrons with kinetic
energies below 1 eV are kept:

.. code:: python

   fin = mcpl.MCPLFile( "input.mcpl" )
   fout = mcpl.MCPLOutFile( "output.mcpl" )
   with fin, fout:
       fout.transfer_metadata( fin )
       fout.hdr_add_comment( "Neutrons below 1eV" )
       for b in fin.particle_blocks:
           sel = (b.pdgcode==2112) & (b.ekin<1e-6)
           fout.add_particles( b[ sel ] )

Particle properties can be edited by passing new values for some of the fields
as keyword arguments together with the block, while the other fields are
transferred unchanged. For neutrons and gammas, the ``wavelength`` [Aa] can be
given instead of the kinetic energy. For instance, rotating the coordinate
system 90 degrees around the z axis, moving the particles 10 cm along it, and
giving all neutrons a wavelength of 1.8 Aa:

.. code:: python

   for b in fin.particle_blocks:
       n = b[ b.pdgcode == 2112 ]
       fout.add_particles( n, x = -n.y, y = n.x,
                           z = n.z + 10.0,
                           ux = -n.uy, uy = n.ux,
                           wavelength = 1.8 )

Wavelengths can also be read with ``p.wavelength`` or ``block.wavelength``,
which gives an error for particles which are not neutrons or gammas (so those
must be selected first, e.g. with ``block[block.pdgcode == 2112]``), or which
have zero kinetic energy. The conversions between kinetic energies and
wavelengths use relativistic kinematics for neutrons, and the CODATA 2022
values of the physical constants, which are available in the ``mcpl.constants``
module.

Selections and edits can also be given as strings, which is for instance
convenient when they are provided by the users of a script. They are evaluated
efficiently on whole blocks, without using Python's ``eval()``:

.. code:: python

   flt = mcpl.ParticleFilter(
       "pdgcode == neutron && ekin < 25meV"
       " && abs(x) <= 2mm" )
   edit = mcpl.ParticleEdit(
       "rotate_z(90deg), z += 10cm,"
       " wavelength = 1.8Aa" )
   for b in fin.particle_blocks:
       sel = b[ flt( b ) ]
       fout.add_particles( sel, **edit( sel ) )

The syntax of these expressions, which can also be used to make histograms
(with ``mcpl.histogram``), is described on :doc:`a page of its
own <usage_expressions>`. The same expressions can be used with
``pymcpltool`` on the :doc:`command line <usage_cmdline>`.

More complete examples can be found in
`pyexample_filtermcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_filtermcpl>`__
and
`pyexample_editmcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_editmcpl>`__,
which also shows how a file can be split into several files.

Note that if particles are selected based on anything else than their own
properties (for instance, if only the first half of the file is copied), the
values of any :doc:`stat:sum <format_statsum>` entries should be scaled
accordingly, with ``fout.hdr_scale_stat_sums(...)`` (see the
:doc:`C/C++ <usage_c>` interface for details).

.. _usage_python_advanced-per-particle-userdata:

Per-particle userdata
---------------------

Particles can carry custom data beyond the 32 bit ``userflags``: a fixed number
of bytes per particle, described by a *layout* of named fields which is stored
in the file header (see the :ref:`format
description <format-mcpl-4-per-particle-userdata>`). Files with
userdata use the ``MCPL-4`` format. The layout is given when creating the file
(or with ``enable_userdata``), and the userdata of the particles is given to
``add_particles`` as a dictionary with an array (or a single value) for each
field, here a temperature and a volume identifier:

.. code:: python

   import mcpl
   import numpy as np

   n = 1000
   layout = "temp:float32,volume:int32"
   f = mcpl.MCPLOutFile( "myfile.mcpl",
                         userdata_layout = layout )
   with f:
       f.hdr_add_comment( "Userdata: temp is the"
                          " temperature [K], volume"
                          " the volume identifier" )
       f.add_particles(
           pdgcode = 2112,
           position = np.zeros((n,3)),
           direction = (0.0, 0.0, 1.0),
           ekin = np.linspace(1e-9, 1e-6, n),
           weight = 1.0,
           userdata = { "temp" : 293.15,
                        "volume" : np.arange(n) } )

Fields left out of the dictionary are zero (so ``userdata = {}`` gives
particles with all userdata bytes zero), and the values of integer fields must
be integers within the range of their type. In files with userdata, the
``userdata`` argument is required for ``add_particles`` and ``add_particle``,
except when the particles are passed as blocks read from a file with the same
userdata layout, whose userdata is then transferred (or replaced if the
argument is given). Array fields like ``tags:uint8[3]`` are given with one row
per particle, i.e. with shape ``(n,3)``.

When reading files, the layout is available as ``userdata_layout`` (``None``
for files without userdata), and the userdata of a block of particles is a
NumPy structured array with the fields of the layout. It is a view of the data
read from the file, so it costs nothing unless used:

.. code:: python

   with mcpl.MCPLFile( "myfile.mcpl" ) as f:
       print( f.userdata_layout )
       for block in f.particle_blocks:
           ud = block.userdata
           print( ud["temp"].mean() )
           # select with masks as for any field:
           hot = block[ ud["temp"] > 300.0 ]
       # single particles have a NumPy record:
       p = f.read()
       print( p.userdata["volume"] )

Merging files requires identical userdata layouts (forced merges discard the
userdata unless all files have the same layout), and ``pymcpltool`` keeps the
userdata when extracting particles. A complete example is found in the file
`pyexample_userdatamcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_userdatamcpl>`__.

.. _usage_python_advanced-statistics-and-plots:

Statistics and plots
--------------------

The statistics and plots of ``pymcpltool --stats`` (see :ref:`command
line <usage_cmdline-extract-statistics-from-a-file>`) are also
available from Python:

.. code:: python

   import mcpl
   stats = mcpl.collect_stats( "myfile.mcpl" )
   mcpl.dump_stats( stats )  # print summary
   mcpl.plot_stats( stats )  # show plots
   # Save plots in a file:
   mcpl.plot_stats( stats, filename = "plots.pdf" )

.. _usage_python_advanced-merging-and-other-file-operations:

Merging and other file operations
---------------------------------

The ``mcpl`` module also provides the file-level operations of the
:doc:`C/C++ <usage_c>` interface and the
:doc:`mcpltool <usage_cmdline>`:

+--------------------------------------------+--------------------------------------+
| Function                                   | Purpose                              |
+============================================+======================================+
| ``merge_files(output, files)``             | Merge particles of compatible files  |
|                                            | into a new file (adding up stat:sum  |
|                                            | values)                              |
+--------------------------------------------+--------------------------------------+
| ``can_merge(file1, file2)``                | Check if two files are compatible    |
|                                            | for merging                          |
+--------------------------------------------+--------------------------------------+
| ``forcemerge_files(output, files)``        | Merge particles of any files, at the |
|                                            | price of discarding most meta-data   |
+--------------------------------------------+--------------------------------------+
| ``merge_inplace(file1, file2)``            | Append particles of file2 to file1   |
+--------------------------------------------+--------------------------------------+
| ``repair(file)``                           | Repair a file which was not properly |
|                                            | closed                               |
+--------------------------------------------+--------------------------------------+
| ``gzip_file(file)``                        | Compress a file with gzip            |
+--------------------------------------------+--------------------------------------+
| ``create_outfile_mpi(file, iproc, nproc)`` | Create output file for one of        |
|                                            | several parallel processes           |
+--------------------------------------------+--------------------------------------+
| ``merge_outfiles_mpi(file, nproc)``        | Merge the output files of parallel   |
|                                            | processes                            |
+--------------------------------------------+--------------------------------------+

Note that ``merge_files`` and ``forcemerge_files`` return the new file as an
open ``MCPLOutFile``, so it must be closed:

.. code:: python

   files = [ "file1.mcpl", "file2.mcpl" ]
   with mcpl.merge_files( "out.mcpl", files ) as f:
       print( "Particles:", f.nparticles )

.. _usage_python_advanced-messages-and-warnings:

Messages and warnings
---------------------

By default, messages and warnings from the ``mcpl`` module (like
``MCPL WARNING: Input file appears to not have been closed properly. ...``) are
printed, like those of the C library. Applications using Python's ``logging``
module can instead get them as records of the logger named ``mcpl`` (without
the ``MCPL:`` and ``MCPL WARNING:`` prefixes), by calling
``mcpl.use_logging()``:

.. code:: python

   import logging
   import mcpl
   mcpl.use_logging()
   logging.basicConfig( level = logging.INFO )

Note that everything is available directly in the ``mcpl`` module after
``import mcpl``. Older code using the ``mcpl.mcpl`` submodule (e.g.
``import mcpl.mcpl`` and ``mcpl.mcpl.MCPLFile``) still works, but gives
deprecation warnings starting with the next MCPL release.

.. _usage_python_advanced-where-to-find-more-documentation:

Where to find more documentation
--------------------------------

All classes and functions are described in the :doc:`API
reference <python_api>`, and with Python's integrated ``help()``
functionality (see the :ref:`basic
usage <usage_python-where-to-find-more-documentation>` page), and
the :doc:`expressions <usage_expressions>` page describes how particles
can be selected, edited and plotted. More complete examples can be found in
`pyexample_writemcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_writemcpl>`__,
`pyexample_filtermcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_filtermcpl>`__
and
`pyexample_editmcpl <https://github.com/mctools/mcpl/blob/main/examples/pyexample_editmcpl>`__.
