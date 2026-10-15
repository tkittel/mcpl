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
- **MCPL-2**: The first publicly released format, used briefly around
  2015-2016.
- **MCPL-3**: The default format produced since the MCPL software release 1.0.0
  in 2016.
- **MCPL-4**: Introduced with the next MCPL software release, and used only for
  files with custom per-particle data ("userdata"). Files without userdata are
  still written as ``MCPL-3``, so they can be read by older MCPL releases.

.. _format-full-format-specifications:

Full format specifications
==========================

The actual binary file formats ``MCPL-2`` and ``MCPL-3`` are described in great
detail in `section 2 of the MCPL
paper <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=section.2>`__. As
described in the paper, the two formats are in fact almost identical, with the
only difference being which packing algorithm is used to pack particle
direction vectors. ``MCPL-3`` uses the superior Adaptive Projection Packing
algorithm, while ``MCPL-2`` uses Octahedral packing.

.. _format-mcpl-4-per-particle-userdata:

MCPL-4: per-particle userdata
-----------------------------

In addition to the 32 bit ``userflags``, particles can carry a fixed number of
bytes of custom data, the *userdata*. Files with userdata are written in the
``MCPL-4`` format, which is identical to ``MCPL-3`` except for two additions:

- The header contains one more string (a 32 bit length followed by that many
  bytes, like the other header strings), placed right after the universal
  weight (if present) and before the source name: the *userdata layout*, which
  describes the contents of the userdata.
- Each particle record is followed by the userdata bytes, whose number is given
  by the layout (and included in the particle size stored in the header).

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

The particle data must not contain NaN (not-a-number) or infinite values. The C
and Python APIs refuse to add particles with such values to files (or values
too large to be stored in single precision), and give a warning when reading
files which nevertheless have such values.

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

.. toctree::
   :hidden:

   format_statsum
