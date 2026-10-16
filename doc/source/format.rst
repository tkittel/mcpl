***************
The MCPL format
***************

While there are often new releases of the MCPL software distribution, the
actual binary MCPL *format* itself is very stable and rarely receives updates.

Furthermore, since the format version is encoded at the beginning of all MCPL
files, it is always possible for the latest MCPL software to read files in
older formats (except the format ``MCPL-1`` which was an early format never
released to the wider public). This backwards compatibility is obviously an
important design feature, intended to ensure that older MCPL files can always
be read with the latest MCPL software releases.

.. _format-list-of-mcpl-formats:

List of MCPL formats
====================

- **MCPL-1**: An early prototype format. This format was never used beyond
  internal developments and is as undocumented and unsupported as it is unused.
- **MCPL-2**: The first publicly released format, written by MCPL release 1.0.0
  (2016).
- **MCPL-3**: The format written since MCPL release 1.1.0 (2017). It differs
  from ``MCPL-2`` only in how the direction vectors of the particles are packed:
  ``MCPL-3`` uses the superior Adaptive Projection Packing algorithm, while
  ``MCPL-2`` uses Octahedral packing (see Appendix B of the `MCPL paper
  <https://doi.org/10.1016/j.cpc.2017.04.012>`__ :openaccess:`open access`).
- **MCPL-4**: Like ``MCPL-3``, with the addition of optional custom
  per-particle data ("userdata"). It is supported since MCPL release 3.0.0, which writes it for
  files with userdata, while it still writes other files as ``MCPL-3``, so
  they can be read by older MCPL releases.

.. _format-binary-layout:

Binary layout
=============

This section describes the binary layout of MCPL files in full detail, so that
MCPL files can be read and written without the MCPL software. The tables are
adapted from Appendix A of the `MCPL paper
<https://doi.org/10.1016/j.cpc.2017.04.012>`__ :openaccess:`open access`
(available under the CC BY 4.0 license), with the additions of the ``MCPL-4``
format.

An MCPL file consists of a header, followed by the particles, all with the same
size and layout. The types of the numbers are:

- UINT32 and UINT64: unsigned integers of 32 and 64 bits.
- INT32: a signed integer of 32 bits (two's complement).
- FP64: a double precision (64 bit) floating point number.
- FP: a single (32 bit) or double (64 bit) precision floating point number,
  depending on the precision flag in the header.

All floating point numbers follow the IEEE-754 standard, and all numbers are
stored in the byte order given in the header (see :ref:`format-byte-order`).

.. _format-header:

The header
----------

The header starts with 48 bytes of fixed layout:

.. list-table:: Header (first part)
   :header-rows: 1
   :widths: 10 8 10 72

   * - Position
     - Size
     - Type
     - Description
   * - 0
     - 4 B
     -
     - Magic number identifying the file as an MCPL file: always
       ``0x4d43504c`` (``MCPL`` in ASCII).
   * - 4
     - 3 B
     -
     - File format version, as a 3 digit zero-prefixed ASCII number (``002``,
       ``003`` or ``004``).
   * - 7
     - 1 B
     -
     - Byte order (endianness) of the numbers in the file: ``0x4c`` (ASCII
       ``L``) for little-endian or ``0x42`` (ASCII ``B``) for big-endian.
   * - 8
     - 8 B
     - UINT64
     - Number of particles in the file (see
       :ref:`format-number-of-particles`).
   * - 16
     - 4 B
     - UINT32
     - Number of comments in the file, NCMTS.
   * - 20
     - 4 B
     - UINT32
     - Number of binary data blobs in the file, NBLOBS.
   * - 24
     - 4 B
     - UINT32
     - Userflags field: ``0x1`` if the particles have userflags, otherwise
       ``0x0``. In ``MCPL-4`` files, ``0x2`` is added if the particles have
       userdata (so the possible values are ``0x0`` to ``0x3``).
   * - 28
     - 4 B
     - UINT32
     - Polarisation field: ``0x1`` if the particles have polarisation vectors,
       otherwise ``0x0``.
   * - 32
     - 4 B
     - UINT32
     - Precision field: ``0x1`` if the floating point numbers of the particles
       (FP) are in single precision, or ``0x0`` for double precision.
   * - 36
     - 4 B
     - INT32
     - Universal PDG code: the type of all particles in the file, or ``0`` if
       each particle has its own PDG code.
   * - 40
     - 4 B
     - UINT32
     - Size of each particle in bytes, which must agree with the other fields
       (see :ref:`format-particles`).
   * - 44
     - 4 B
     - UINT32
     - Universal weight field: ``0x1`` if a universal weight follows (the
       weight of all particles in the file), or ``0x0`` if each particle has
       its own weight.

The fields at positions 24, 28, 32 and 44 must have exactly the values given
above. They are followed by entries whose presence and number depend on these
values:

.. list-table:: Header (second part)
   :header-rows: 1
   :widths: 20 18 62

   * - Size
     - Type
     - Description
   * - 0 B or 8 B
     - FP64
     - The universal weight, if the universal weight field is ``0x1``. It must
       be positive and finite.
   * - 0 B or 4 B+
     - DATA ARRAY
     - The userdata layout, if the userflags field has ``0x2`` (only in
       ``MCPL-4`` files, see :ref:`below
       <format-mcpl-4-per-particle-userdata>`).
   * - 4 B+
     - DATA ARRAY
     - The source name: the name of the application which created the file.
       Always present (but it might be empty).
   * - NCMTS |times| 4 B+
     - DATA ARRAYS
     - The comments.
   * - NBLOBS |times| 4 B+
     - DATA ARRAYS
     - The keys of the binary data blobs.
   * - NBLOBS |times| 4 B+
     - DATA ARRAYS
     - The binary data blobs (in the same order as their keys).

.. _format-data-arrays:

Strings and data arrays
-----------------------

A DATA ARRAY is a UINT32 with the number of bytes in it, followed by those
bytes. Strings (the userdata layout, the source name, the comments and the
blob keys) are stored without a terminating null character, and must not
contain null characters. The userdata layout is ASCII, and the source name
and comments are usually ASCII or UTF-8 text.

The blob keys must be unique. In ``MCPL-4`` files, they must not be empty,
and can only have printable ASCII characters other than whitespace, quotes,
backslash and backtick (bytes 33 to 126, except ``"``, ``'``, ``\`` and
`````). The MCPL software applies these rules to keys added to new files in
any format version, but still copies other keys from the headers of
``MCPL-2`` and ``MCPL-3`` files (for instance when merging such files), unless
the new file has userdata. The data of the blobs can be any bytes.

Comments starting with ``stat:`` are reserved: comments starting with
``stat:sum:`` follow the :doc:`stat:sum convention <format_statsum>`, and
other comments starting with ``stat:`` are reserved for future use.

.. _format-particles:

The particles
-------------

The header is followed by the particles, each with the following fields in
this order:

.. list-table:: Particle
   :header-rows: 1
   :widths: 18 18 64

   * - Presence
     - Count & type
     - Description
   * - Optional
     - 3 |times| FP
     - Polarisation vector (if the polarisation field is ``0x1``).
   * - Always
     - 3 |times| FP
     - Position (x, y, z) in cm.
   * - Always
     - 3 |times| FP
     - Packed direction and kinetic energy (see
       :ref:`format-packing`).
   * - Always
     - 1 |times| FP
     - Time in ms.
   * - Optional
     - 1 |times| FP
     - Weight (if the universal weight field is ``0x0``).
   * - Optional
     - 1 |times| INT32
     - PDG code (if the universal PDG code is ``0``).
   * - Optional
     - 1 |times| UINT32
     - Userflags (if the userflags field has ``0x1``).
   * - Optional
     - Bytes
     - Userdata (if the userflags field has ``0x2``, with the number of bytes
       given by the userdata layout).

The size of each particle in the header (at position 40) is therefore 7 FP
(28 or 56 bytes), plus 3 FP for polarisation, 4 bytes for the PDG code, 1 FP
for the weight, 4 bytes for the userflags and the size of the userdata, when
present. Particles without polarisation vectors have the polarisation
``(0,0,0)``, and particles without userflags have the userflags ``0``.

The PDG code is the particle type, as defined by the Particle Data Group (like
2112 for neutrons, 22 for gammas and 11 for electrons). The direction is a
unit vector, and the kinetic energy (in MeV) is not negative.

.. _format-packing:

Packing of direction and kinetic energy
---------------------------------------

The direction ``(ux,uy,uz)`` (a unit vector) and the kinetic energy ``ekin``
are packed into three FP numbers ``(p0,p1,p2)``. In ``MCPL-3`` and ``MCPL-4``
files, this uses the Adaptive Projection Packing algorithm: the two components
of the direction with the smallest magnitudes are stored directly, while the
third is replaced by its inverse (with a magnitude of at least 1), and its
sign is stored in the sign bit of ``p2``, whose magnitude is ``ekin``:

.. code-block:: text

   Packing (s is the sign of the component which is
   left out, +1.0 or -1.0, and 1/uz is +infinity
   if uz is zero, also for -0.0):

     if |uz| < max(|ux|,|uy|):
       if |ux| >= |uy|:  (p0,p1) = (1/uz, uy),  s = sign(ux)
       else:             (p0,p1) = (ux, 1/uz),  s = sign(uy)
     else:               (p0,p1) = (ux, uy),    s = sign(uz)
     p2 = ekin, with the sign bit set if s is -1.0

   Unpacking (s is -1.0 if the sign bit of p2 is set,
   otherwise +1.0):

     ekin = |p2|
     if |p0| > 1:
       uz = 1/p0;  uy = p1;  ux = s * sqrt(max(0, 1-uy*uy-uz*uz))
     else if |p1| > 1:
       uz = 1/p1;  ux = p0;  uy = s * sqrt(max(0, 1-ux*ux-uz*uz))
     else:
       ux = p0;  uy = p1;  uz = s * sqrt(max(0, 1-ux*ux-uy*uy))

The packing is done in double precision, and the results are then stored as
FP. Signs are those of the IEEE-754 sign bits, also for zeros (so ``-0.0`` has
the sign ``-1.0``). Note that ``p0`` or ``p1`` is infinite for directions with
``uz = 0`` and ``|uz| < max(|ux|,|uy|)``, and that the sign bit of ``p2`` is
also used when ``ekin`` is zero.

``MCPL-2`` files use octahedral packing instead, where ``(p0,p1)`` are the
coordinates of the direction projected on an octahedron, unfolded into a
plane, and the sign bit of ``p2`` tells that ``uz`` is exactly zero:

.. code-block:: text

   Unpacking in MCPL-2:

     z = 1 - |p0| - |p1|
     if z < 0:
       x = (1 - |p1|) * (+1 if p0 >= 0, otherwise -1)
       y = (1 - |p0|) * (+1 if p1 >= 0, otherwise -1)
     else:
       x = p0;  y = p1
     n = sqrt(x*x + y*y + z*z)
     (ux,uy,uz) = (x/n, y/n, z/n)
     ekin = |p2|, and if the sign bit of p2 is set: uz = 0

``MCPL-2`` files are no longer written by the MCPL software, which only reads
them.

.. _format-mcpl-4-per-particle-userdata:

Userdata (MCPL-4)
-----------------

In addition to the 32 bit ``userflags``, particles can carry a fixed number of
bytes of custom data, the *userdata*. This requires the ``MCPL-4`` format, in
which the userdata is optional: ``0x2`` in the userflags field of the header
tells that the particles have userdata, and only then is the userdata layout
in the header and are the userdata bytes at the end of each particle. An
``MCPL-4`` file without userdata is therefore identical to an ``MCPL-3`` file,
except for the version number, so changing the version number turns one into
the other. This requires that the ``MCPL-3`` file follows the rules of
``MCPL-4`` (no NaN or infinite values in the particle fields, see
:ref:`format-values-of-particle-data`, and blob keys as described in
:ref:`format-data-arrays`).

The userdata layout is a comma-separated list of fields written as
``name:type`` or ``name:type[n]`` for arrays of ``n`` values, for instance
``temp:float32,origin:int32,tags:uint8[3]``, without any whitespace:

- The types are ``int8``, ``uint8``, ``int16``, ``uint16``, ``int32``,
  ``uint32``, ``int64``, ``uint64``, ``float32`` and ``float64`` (signed
  integers in two's complement, and floating point numbers following
  IEEE-754).
- Names must start with a lowercase letter, followed by lowercase letters,
  digits or underscores, have at most 64 characters, and be unique within the
  layout. Names are required also for plain bytes (e.g. ``data:uint8[27]``),
  so that files whose userdata merely has the same types are not mixed up when
  merging.
- Array sizes ``n`` are written as decimal numbers without leading zeros, and
  are at least 1.
- The layout has at least one field, and the userdata has at most 65535 bytes
  per particle.

The values are packed in the order of the layout without any padding, in the
byte order of the file. Files can only be merged when their userdata layouts
are identical (forced merges discard the userdata unless all files have the
same layout). The userdata is accessed with the :ref:`C
API <usage_c-per-particle-userdata>` and the :ref:`Python
API <usage_python_advanced-per-particle-userdata>`.

.. _format-number-of-particles:

Number of particles and unfinished files
----------------------------------------

The number of particles in the header must be the number of particles after
the header, and the file must end after the last particle (so its size is the
size of the header plus the number of particles times the size of each
particle). Writers usually do not know the number of particles until the end,
so they first write ``0`` and update the number when the file is finished.

A file whose number of particles is ``0`` while it has particle data was
therefore not finished properly (for instance because the program writing it
was stopped). The MCPL software can still read the complete particles of such
files (when they are not compressed), and it can repair them by updating the
number of particles and removing an incomplete last particle (``mcpltool
--repair``). The values of ``stat:sum`` comments in such files can not be
trusted (see :doc:`format_statsum`).

.. _format-compression:

Compression
-----------

MCPL files can be compressed as a whole with gzip, which is indicated by the
extension ``.mcpl.gz`` (instead of ``.mcpl``). The contents of the
uncompressed data are exactly as described above.

.. _format-byte-order:

Byte order
==========

Numbers in MCPL files are stored in the byte order (endianness) of the platform
which wrote the file, which is recorded in the header (the 8th byte of the file
is ``L`` for little-endian or ``B`` for big-endian). All platforms on which
MCPL is currently developed and tested are little-endian, so in practice MCPL
files are little-endian. The C API currently only reads files in the byte order
of the platform, while the Python API is written to read files in either byte
order.

All numbers in the header, the particle data and the userdata have known types,
so files in either byte order can in principle be read on any platform, which
future MCPL releases might support. The exception is the contents of binary
blobs, which MCPL stores byte for byte: applications storing binary numbers in
blobs should therefore define their byte order themselves (or use text).

.. _format-values-of-particle-data:

Values of particle data
=======================

In ``MCPL-4`` files, the particle fields must not contain NaN (not-a-number)
or infinite values (except ``p0`` and ``p1`` of the packed direction, as
described above). This does not apply to the userdata, whose floating point
values may be NaN or infinite. The older formats do not forbid such values, so
``MCPL-2`` and ``MCPL-3`` files might contain them. Since release 3.0.0, MCPL
refuses to add particles with NaN or infinite values to any file (and values
too large to be stored in single precision to files in single precision), and
gives a warning when reading files with such values.

.. _format-reading-rules:

Summary of rules for readers
============================

A reader must refuse files which do not follow the rules above. The MCPL
software refuses files with:

- an unknown magic number, format version or byte order;
- other values than those given above in the fields at positions 24, 28, 32
  and 44 of the header;
- a particle size (at position 40) which does not agree with the other fields;
- a universal weight which is not positive and finite;
- an invalid userdata layout, or (in ``MCPL-4`` files) invalid blob keys;
- null characters in strings;
- a number of particles which does not agree with the size of the file (except
  as described in :ref:`format-number-of-particles`).

Files with NaN or infinite values in the particle fields are read with a
warning.

.. _format-conventions:

Conventions
===========

In addition to the actual binary format itself, release 2.1.0 of the MCPL
software distribution introduced the notion of a convention for encoding
statistics in MCPL headers in comment fields. Crucially, the convention
includes a definition of how these statistics should be updated when MCPL files
are merged or otherwise edited. Refer to the dedicated page describing the
:doc:`stat:sum convention <format_statsum>` for more details.
Additionally, note that any MCPL comment starting with the 5 characters
``stat:`` is considered to be reserved for future usage.

.. |times| unicode:: U+00D7

.. toctree::
   :hidden:

   format_statsum
