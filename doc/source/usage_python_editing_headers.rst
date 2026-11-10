***************
Editing headers
***************

The header of an MCPL file (its comments, binary blobs, stat:sum entries, and
how the particles are stored) is written when the file is created, and can not
be changed in place. To change it, the file is copied with the ``mcpl`` Python
module (available since MCPL release 3.0.0): the header is copied with
``transfer_metadata(..., editable=True)``, changed, and then the particles are
copied unchanged:

.. code:: python

   import mcpl

   with mcpl.MCPLFile( "input.mcpl" ) as fin, \
        mcpl.MCPLOutFile( "output.mcpl" ) as fout:
       fout.transfer_metadata( fin, editable = True )
       # ... change the header of fout here ...
       for block in fin.particle_blocks:
           fout.add_particles( block )

The header can be changed until the first particle is added. The examples
below show what to put in place of the comment.

.. _usage_python_editing_headers-files-which-can-not-be-merged:

Files which can not be merged because of their stat:sum entries
----------------------------------------------------------------

Files can only be merged if their headers are the same, except for the values
of their :doc:`stat:sum entries <format_statsum>`, which are added up. Files
from different simulations often have different stat:sum entries, like
``initial_ray_count`` in files from McStas and ``geant4_nevts`` in files from
Geant4. Their sums count different things, so the merged file can not have
meaningful values for them. To merge such files anyway, the stat:sum entries
are removed from copies of the files:

.. code:: python

   for key in list( fout.stat_sum ):
       fout.hdr_remove_stat_sum( key )

The copies can then be merged (if the rest of their headers are the same),
with ``mcpl.merge_files`` or with ``mcpltool --merge``.

.. _usage_python_editing_headers-single-precision:

Single precision
----------------

Files written in double precision can be reduced to single precision, which
makes them about half as large (the floating point values are then rounded to
about 7 significant digits):

.. code:: python

   fout.enable_doubleprec( False )

.. _usage_python_editing_headers-comments-blobs-and-statsum-entries:

Comments, blobs, and stat:sum entries
-------------------------------------

All comments are replaced with ``hdr_set_comments``, so they can be changed,
removed, added, or reordered as a list:

.. code:: python

   comments = fout.comments
   comments[0] = "A corrected first comment"
   del comments[2]
   fout.hdr_set_comments( comments )

The stat:sum entries are comments too. A stat:sum entry is changed with
``hdr_add_stat_sum``, and removed with ``hdr_remove_stat_sum``:

.. code:: python

   fout.hdr_add_stat_sum( "nevents", 1e6 )
   fout.hdr_remove_stat_sum( "old_key" )

A binary blob is replaced by adding new data with the same key, and removed
with ``hdr_remove_data``:

.. code:: python

   fout.hdr_add_data( "MyApp/settings", new_settings )
   fout.hdr_remove_data( "MyApp/old_settings" )

The name of the program which wrote the file is set with
``hdr_set_srcname``.

.. _usage_python_editing_headers-how-particles-are-stored:

How particles are stored
------------------------

With ``editable=True``, the settings copied from the input file can be
changed with the ``enable_`` methods: ``False`` turns polarisation, userflags,
and double precision off, ``None`` turns universal values off, and other
values replace them. Particles are converted when they are added (fields
which are not stored are dropped):

.. code:: python

   fout.enable_polarisation( False )      # drop the polarisation vectors
   fout.enable_userflags( False )         # drop the userflags
   fout.enable_universal_weight( None )   # store the weight of each particle

Setting a universal PDG code or weight stores only that value, also for
particles which had other values.

.. _usage_python_editing_headers-userdata:

Userdata
--------

The userdata of the particles (see :ref:`per-particle userdata
<usage_python_advanced-per-particle-userdata>`) is removed with
``enable_userdata(None)``. With another layout, the userdata of the particles
must be given when they are added, as it can not be converted automatically.
For instance, keeping only the field ``temp``:

.. code:: python

   fout.enable_userdata( "temp:float32:K" )
   for block in fin.particle_blocks:
       fout.add_particles( block,
                           userdata = { "temp" : block.userdata["temp"] } )

(In this case the particles are added in this loop, instead of the loop
copying them unchanged.)
