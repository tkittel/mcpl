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

The binary layout of MCPL files is described in detail in `Appendix A of the
MCPL paper <https://doi.org/10.1016/j.cpc.2017.04.012>`__ :openaccess:`open
access`, for the ``MCPL-3`` format. The tables below are adapted from the
paper (which is available under the CC BY 4.0 license), with the additions of
the ``MCPL-4`` format.

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
     - File format version, as a 3 digit zero-prefixed ASCII number (e.g.
       ``003``).
   * - 7
     - 1 B
     -
     - Byte order (endianness) of the numbers in the file: ``0x4c`` (ASCII
       ``L``) for little-endian or ``0x42`` (ASCII ``B``) for big-endian.
   * - 8
     - 8 B
     - UINT64
     - Number of particles in the file.
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
     - Whether userflags are enabled (1) or disabled (0).
   * - 28
     - 4 B
     - UINT32
     - Whether polarisation vectors are enabled (1) or disabled (0).
   * - 32
     - 4 B
     - UINT32
     - Whether the floating point numbers of the particles are in single (1)
       or double (0) precision.
   * - 36
     - 4 B
     - INT32
     - Universal PDG code. The value 0 means that each particle has its own
       PDG code.
   * - 40
     - 4 B
     - UINT32
     - Size of each particle in bytes (redundant, as it follows from the other
       values; in ``MCPL-4`` files it includes the userdata).
   * - 44
     - 4 B
     - UINT32
     - Whether a universal weight is present in the header (1), or each
       particle has its own weight (0).

It is followed by entries whose presence and count depend on these values:

.. list-table:: Header (second part)
   :header-rows: 1
   :widths: 20 18 62

   * - Size
     - Type
     - Description
   * - 0 B or 8 B
     - FP64
     - The universal weight, if enabled.
   * - 4 B+
     - DATA ARRAY
     - The userdata layout (only in ``MCPL-4`` files, where it is empty if
       the particles have no userdata, see
       :ref:`below <format-mcpl-4-per-particle-userdata>`).
   * - 4 B+
     - DATA ARRAY
     - The source name. Always present, but might be empty.
   * - NCMTS |times| 4 B+
     - DATA ARRAYS
     - The comments.
   * - NBLOBS |times| 4 B+
     - DATA ARRAYS
     - The keys of the binary data blobs.
   * - NBLOBS |times| 4 B+
     - DATA ARRAYS
     - The binary data blobs (in the same order as their keys).

After the header follow the particles, all with the same size and layout:

.. list-table:: Particle
   :header-rows: 1
   :widths: 18 18 64

   * - Presence
     - Count & type
     - Description
   * - Optional
     - 3 |times| FP
     - Polarisation vector (if enabled in the file).
   * - Always
     - 3 |times| FP
     - Position.
   * - Always
     - 3 |times| FP
     - Packed direction vector and kinetic energy.
   * - Always
     - 1 |times| FP
     - Time.
   * - Optional
     - 1 |times| FP
     - Weight (if the file has no universal weight).
   * - Optional
     - 1 |times| INT32
     - PDG code (if the file has no universal PDG code).
   * - Optional
     - 1 |times| UINT32
     - Userflags (if enabled in the file).
   * - Optional
     - Bytes
     - Userdata (only in ``MCPL-4`` files, with the number of bytes given by
       the layout).

Here, UINT32 and UINT64 are 32 and 64 bit unsigned integers, INT32 is a 32 bit
signed integer (two's complement), and FP64 is a double precision floating
point number, while FP is a single (32 bit) or double (64 bit) precision
floating point number, depending on the flag in the header. All floating point
numbers follow the IEEE-754 standard. A DATA ARRAY starts with a UINT32 with
the number of bytes which follow it (strings are stored without a terminating
null character).

The packed direction vector and kinetic energy are three numbers: the first two
are the packed direction (with the Adaptive Projection Packing algorithm, see
Appendix B of the paper, and they can legitimately be infinite), and the
magnitude of the third is the kinetic energy, while its sign bit holds the
last bit of information about the direction.

.. _format-mcpl-4-per-particle-userdata:

Userdata (MCPL-4)
-----------------

In addition to the 32 bit ``userflags``, particles can carry a fixed number of
bytes of custom data, the *userdata*. This requires the ``MCPL-4`` format,
which differs from ``MCPL-3`` only by the userdata layout in the header and
the userdata bytes at the end of each particle (see the tables above). The
userdata is optional in ``MCPL-4`` files: an empty layout means that the
particles have no userdata.

The userdata layout is a comma-separated list of fields written as
``name:type`` or ``name:type[n]`` for arrays of ``n`` values, for instance
``temp:float32,origin:int32,tags:uint8[3]``. The types are ``int8``, ``uint8``,
``int16``, ``uint16``, ``int32``, ``uint32``, ``int64``, ``uint64``,
``float32`` and ``float64``. Names must start with a lowercase letter followed
by lowercase letters, digits or underscores, and must be unique within the
layout. Names are required also for plain bytes (e.g. ``data:uint8[27]``), so
that files whose userdata merely has the same types are not mixed up when
merging. The values are packed in the order of the layout without any padding,
in the byte order of the file, and at most 65535 bytes of userdata per particle
are allowed.

Files can only be merged when their userdata layouts are identical (forced
merges discard the userdata unless all files have the same layout). The
userdata is accessed with the :ref:`C
API <usage_c-per-particle-userdata>` and the :ref:`Python
API <usage_python_advanced-per-particle-userdata>`.

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
or infinite values (except the packed direction, as described above). This
does not apply to the userdata, whose floating point values may be NaN or
infinite. The older formats do not forbid such values, so ``MCPL-2`` and
``MCPL-3`` files might contain them. Since release 3.0.0, MCPL refuses to add
particles with NaN or infinite values to any file (and values too large to be
stored in single precision to files in single precision), and gives a warning
when reading files with such values.

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
