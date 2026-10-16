******************
MCPL file contents
******************

An MCPL file contains a list of particles, typically those crossing a surface
or leaving a volume in a simulation, all with the same fields. A header at the
start of the file describes the file as a whole. Files are usually compressed
with gzip (with the extension ``.mcpl.gz``), and can be read in that form.

The details of how all this is stored are described on the
:doc:`format` page.

.. _file_contents-header:

The header
==========

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Content
     - Description
   * - Format version
     - ``MCPL-3``, or ``MCPL-4`` for files with userdata (see below).
   * - Number of particles
     - The number of particles in the file.
   * - Source name
     - The name of the application which created the file, like ``Geant4``
       or ``McStas``.
   * - Comments
     - Any number of text comments, for instance describing the simulation.
       Comments like ``stat:sum:<key>:<value>`` hold statistics, like the
       number of simulated events, which are added up when files are merged
       (see :doc:`format_statsum`).
   * - Blobs
     - Any number of binary data items, each stored under a key, for instance
       the configuration file of the simulation.
   * - Options
     - Which of the optional particle fields are present (polarisation,
       userflags and userdata, the latter with a *layout* describing its
       fields), whether numbers are stored in single or double precision, and
       whether all particles have the same type or weight (which is then
       stored only once, in the header).

.. _file_contents-particles:

The particles
=============

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Field
     - Unit
     - Description
   * - ``pdgcode``
     -
     - The particle type as a number defined by the Particle Data Group, like
       2112 for neutrons, 22 for gammas and 11 for electrons.
   * - ``x``, ``y``, ``z``
     - cm
     - The position.
   * - ``ux``, ``uy``, ``uz``
     -
     - The direction of motion (a unit vector).
   * - ``ekin``
     - MeV
     - The kinetic energy.
   * - ``time``
     - ms
     - The time.
   * - ``weight``
     -
     - The weight, or intensity, of the particle.
   * - ``polx``, ``poly``, ``polz``
     -
     - The polarisation vector (optional).
   * - ``userflags``
     -
     - A 32 bit number with custom information, whose meaning is defined by
       the application which created the file (optional).
   * - userdata
     -
     - A fixed number of bytes of custom data, with named fields (like
       ``temp:float32``) described by the layout in the header (optional,
       only in ``MCPL-4`` files).

The names of the fields are the ones used in the :doc:`Python API
<usage_python>` and in :doc:`expressions <usage_expressions>`, while the C API
has the arrays ``position``, ``direction`` and ``polarisation`` instead of
their components.

.. _file_contents-size:

The size of a file
==================

Uncompressed, each particle takes between 28 and 92 bytes, plus any userflags
and userdata (see :ref:`format-binary-layout` for the details). Compression
with gzip typically reduces the size further.
