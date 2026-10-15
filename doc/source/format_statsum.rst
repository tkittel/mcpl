***********************
The stat:sum convention
***********************

The *stat:sum* convention for statistics in MCPL headers, allows the addition
of custom statistics to the headers of MCPL files.

These values are encoded into MCPL header comment fields in the form
``stat:sum:<key>:<value>``, and the values are combined through simple addition
when two or more MCPL files are merged. The present page provides both a brief
introduction to these *stat:sum* entries, and after an introduction includes
detailed descriptions of the syntax, software support, and guidelines for how
to deal with *stat:sum* values in various scenarios where MCPL files are
filtered, merged, split, or otherwise edited.

.. _format_statsum-introduction:

Introduction
============

In short, the *stat:sum* convention brings an often-requested feature to MCPL:
Statistics in the header which are automatically combined when files are
merged!

More specifically, *stat:sum* values are to be combined via simple addition
when files are merged. Examples of such statistics could for instance be
*"number of seed particles in simulation run"*, *"number of seconds of
beam-time simulated"*, or *"number of proton collisions modelled"*. Note that
this is not the same as the number of actual particles in the MCPL file, which
could be either larger or smaller than any particular *stat:sum* parameter
value. But in general the number of particles in the MCPL file is expected to
scale roughly linearly with the values of the *stat:sum* entries -- at least in
the limit of large statistics.

When inspecting MCPL files, the *stat:sum* entries will show up as
human-readable comments where the encoded value will usually be a
human-readable string representation of a non-negative and finite floating
point number. In some cases you might also see the special value *-1* which
means *Not Available*. Here is how it might look when using the ``mcpltool`` to
inspect such a file:

::

     Custom meta data
       Source             : "my_cool_program_name"
       Number of comments : 2
             -> comment 0 : "stat:sum:my_custom_source_stat:                 1234500"
             -> comment 1 : "Some other comment."
       Number of blobs    : 0

Note that depending on your font, you might have to scroll to the right to see
the actual value on this website, as for technical reasons values are always
padded with spaces to take up exactly 24 characters. Now imagine a second
(otherwise compatible) file with:

::

     Custom meta data
       Source             : "my_cool_program_name"
       Number of comments : 2
             -> comment 0 : "stat:sum:my_custom_source_stat:                 2000000"
             -> comment 1 : "Some other comment."
       Number of blobs    : 0

Before the MCPL software release version 2.1.0, the two files would not have
been possible to merge with the usual tools (``mcpltool --merge`` or the MCPL C
API), but now they are not only mergeable, the values are properly combined via
addition to produce the new post-merge value. The resulting file thus ends up
with all the particles from both files and the header:

::

     Custom meta data
       Source             : "my_cool_program_name"
       Number of comments : 2
             -> comment 0 : "stat:sum:my_custom_source_stat:                 3234500"
             -> comment 1 : "Some other comment."
       Number of blobs    : 0

If desired, users or developers interacting with MCPL files through the MCPL
software can interact with these ``stat:sum:<key>:<value>`` entries
programmatically through the C or Python APIs, and likewise the
``mcpltool --merge`` and ``mcpltool --extract`` modes have been updated to
handle *stat:sum* entries.

It is highly recommended that anyone implementing custom code for merging,
splitting, or filtering MCPL files familiarise themselves with the full details
of the convention described below.

.. _format_statsum-the-syntax:

The syntax
==========

The syntax of the comments defining a statistics with both a key and a value
is: ``"stat:sum:<key>:<value>"`` with the following additional constraints:

- The entire string must be encoded with printable ASCII values only.

- The user definable ``<key>`` must be from 1 to 64 characters long, begin with
  an ASCII letter (``a-z`` or ``A-Z``), and contain only ASCII letters, numbers
  (``0-9``) or underscores (``_``).

- The ``<value>`` must always be exactly 24 characters long, and contain an
  ASCII representation of the value including only characters from the list
  ``0123456789.+-eE``. If less than 24 characters are needed for the value
  itself, the string can be padded with extra ASCII spaces at either end
  (and only at the ends). If manually composing the strings in languages like
  C, C++, or Python, one can for instance encode the value using a print-format
  specifier like ``%24.17g``, which has the advantage of loss-less encoding of
  double-precision floating point values (assuming 64 bit IEEE-754 floating
  point encoding).

- The actual value represented in the ``<value>`` string must not be negative,
  NaN (not-a-number) or infinity. The exception is that a value of -1 is
  allowed, with the special meaning of "Not Available". This can for instance
  be used to reserve space in a file with the intention of overwriting it with
  an actual value later. In case of an exceptional programme abort, where the
  file header had been written but the job ended before all particles could be
  written to the file, the header would in that case hold a value meaning "Not
  Available", rather than a misleading value. Any operations on statistics
  during file merges or splitting should yield -1 if any input value is -1 or
  if the result does not otherwise fit (i.e. if merges would lead to values of
  infinity)

- In addition to ``stat:sum:...`` entries in the list of comments, all entries
  starting with the string ``stat:`` are reserved for future usage. Thus, it is
  for now recommended that software dealing with MCPL files will prevent people
  from creating comments starting with ``stat:``, except if it is a
  ``stat:sum:<key>:value`` entry compliant with the syntax defined above.

.. _format_statsum-software-support:

Software support
================

The MCPL software release supports the *stat:sum* convention starting with
release 2.1.0. Earlier releases will simply treat the *stat:sum* entries as any
other comment in the MCPL header, which will often be OK, but might not be
(e.g. when merging files). For consistency, it is recommended that applications
modify their software dependency list to require at least version 2.1.0 of the
MCPL software release.

When using MCPL release 2.1.0 or later, built-in operations like file merging
automatically update *stat:sum* values when it is unambiguous how they should
be updated. In case of ambiguities (e.g. when splitting files), values are set
to -1 to be conservative. Additionally, C and Python APIs allow interaction
with *stat:sum* values through keys and values directly, rather than having to
manually encode or decode ``stat:sum:<key>:<value>`` comments. In the
following, the *stat:sum* support in the MCPL software APIs will be briefly
discussed.

.. _format_statsum-python-api:

Python API
----------

The ``MCPLFile`` objects in the Python API now have ``.stat_sum`` properties,
which are dictionaries of ``(key,value)`` pairs:

.. code:: py

   >>> import mcpl
   >>> f = mcpl.MCPLFile('somefile.mcpl')
   >>> print( f.stat_sum )
   {'my_custom_source_stat': 3234500.0}

Note that values of -1.0 in the actual ``stat:sum:<key>:<value>`` comments in
the data, are translated into ``None`` in the Python interface.

Since MCPL release 3.0.0, the Python API can also create files (see
:ref:`Python <usage_python_advanced-creating-mcpl-files>`). Here,
*stat:sum* entries are added with the ``hdr_add_stat_sum`` method (or the
``stat_sum`` keyword argument), and scaled with ``hdr_scale_stat_sums``, which
work like the corresponding C functions described below:

.. code:: py

   >>> f = mcpl.MCPLOutFile('newfile.mcpl',
   ...         stat_sum = {'nsimulated' : -1})
   >>> with f:
   ...     f.add_particles( ... )
   ...     f.hdr_add_stat_sum('nsimulated', 1e6)

Likewise, the Python functions for merging files (``merge_files`` and
``merge_inplace``) handle *stat:sum* entries in the same way as the C
functions.

.. _format_statsum-c-api:

C API
-----

The C API gains three new functions:

.. code:: c

   double mcpl_hdr_stat_sum( mcpl_file_t,
                             const char * key );
   void mcpl_hdr_add_stat_sum( mcpl_outfile_t,
                               const char * key,
                               double value );
   void mcpl_hdr_scale_stat_sums( mcpl_outfile_t,
                                  double scale );

The ``mcpl_hdr_stat_sum`` function is used to extract ``stat:sum:`` values from
an existing file, by a particular key, returning -2 in case the key is not
present in the file.

The ``mcpl_hdr_add_stat_sum`` function is used to add values into files. Of
course, this could also be done through careful usage of the
``mcpl_hdr_add_comment`` function, but this is not recommended. In particular
because the ``mcpl_hdr_add_stat_sum`` function can also be called *after* the
first particle has been written to disk, as long as a *stat:sum* entry with the
key in question was also added *before* the first particle was written. For
this initial reservation of space in the on-disk header one can ideally use a
value of -1. This is for instance useful if the size of a given Monte Carlo
simulation is not initially known -- perhaps because of a dynamic criteria for
ending the job like "keep running until I have registered a million entries in
my detector tally".

Finally, the function ``mcpl_hdr_scale_stat_sums`` is intended for usage by
people who might be implementing custom editing, filtering or splitting of
files via the C API (normally in conjunction with the
``mcpl_transfer_metadata`` function). If simply filtering based upon particle
properties (perhaps picking only certain particle types or energies), this is
typically not needed. But if somehow splitting a file or otherwise selecting
particles based on their position in the file (perhaps producing a file
containing the first N particles of another file), the *stat:sum* values in the
new file should probably be reduced somehow, and this can be done with the
``mcpl_hdr_scale_stat_sums`` function. If in doubt, invoking
``mcpl_hdr_scale_stat_sums`` with a value of -1 ensures that the output file
will get a value of -1 for any *stat:sum* entries, thus avoiding misleading
values.

Naturally, other relevant functions in the C API, such as for merging or
repairing files, have been updated to handle *stat:sum* entries appropriately.

.. _format_statsum-command-line-api:

Command-line API
----------------

As the new *stat:sum* values are encoded in MCPL comments, it is trivially true
that any tool displaying such comments will display the *stat:sum* values as
well. This of course includes the ``mcpltool`` and any other code in the MCPL
software releases, old or new.

The ``mcpltool --extract`` mode has been updated to properly deal with
*stat:sum* entries. Specifically, it will leave them unaltered if only using
the ``-p`` flag to extract particles of a particular type. However, if using
the ``-l`` and ``-s`` flags to extract particles based on position in the file,
the ``mcpltool`` code will conservatively set all *stat:sum* values in the
resulting file to -1 (meaning *Not Available*). This is done since the generic
MCPL code can not possibly know with certainty how to calculate the new values.

Finally, other modes, like ``mcpltool --merge`` and ``mcpltool --repair``, have
also been updated to handle *stat:sum* entries appropriately. Note that
``mcpltool --forcemerge`` discards all comments, including any *stat:sum*
entries.

.. _format_statsum-guidelines-for-custom-code:

Guidelines for custom code
==========================

Depending on the scenario, custom code modifying MCPL files may or may not have
to be updated in order to properly deal with the new *stat:sum* entries:

- Custom code *filtering* files based only on individual particle properties
  will most likely not require any changes.

- Custom code *splitting* files, extracting particles based on position in
  files, or manually editing particle weights, will most likely require an
  application-specific calculation of the scaling factor required to preserve
  the correct meaning of *stat:sum* entries. The ``mcpl_hdr_scale_stat_sums``
  function can be used to apply such a scale. If nothing else, such code should
  at least invoke ``mcpl_hdr_scale_stat_sums`` with a scale of -1, to
  effectively mark all the *stat:sum* numbers in the file as unavailable.

- The MCPL developers are not aware of anyone actually merging MCPL data
  without using tools from the MCPL software release, but for completeness we
  mention that custom code *merging* files will have to carefully add up any
  *stat:sum* values with the same keys. If a key has a value of -1 (or is
  absent) in either of the input files, it should get a value of -1 in the new
  file. It should also get a value of -1 in the hypothetical scenario where
  addition of the values from the two files would end up with a value
  overflowing the range of 64 bit floating point numbers (i.e. always store -1
  instead of infinity).
