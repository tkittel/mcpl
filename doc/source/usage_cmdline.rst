********************************
Using MCPL from the command line
********************************

MCPL provides the command-line tool ``mcpltool`` (from the ``mcpl-python``
package), which can be used to inspect MCPL files, show statistics and plots of
their contents, select or edit particles with expressions, and carry out
operations like merging, extracting or repairing files. Before MCPL 3.0.0, it
was called ``pymcpltool``.

This page includes a few examples of how ``mcpltool`` can be used,
but users are referred to `the MCPL paper (section
2.3) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.2.3>`__ for
more information.

.. _usage_cmdline-examples:

Examples
--------

A few examples of how to use ``mcpltool`` are provided here (the outputs shown
are those of the current version of ``mcpltool``). Note that a small sample
MCPL file is available at
`examples/example.mcpl <https://github.com/mctools/mcpl/raw/HEAD/examples/example.mcpl>`__,
in case new users would like something to try the ``mcpltool`` on.

.. _usage_cmdline-inspect-file-contents:

Inspect file contents
~~~~~~~~~~~~~~~~~~~~~

Simply invoking ``mcpltool`` on a file with no additional arguments, results
in a summary of the header information being printed, in addition to the
particle state information of the first ten particles in the file:

.. literalinclude:: ../build/autogen/cmdline_inspect.txt
   :language: console

The ``-l`` (limit) and ``-s`` (skip) flags can be used to change which
particles are printed (use ``-l0`` to print *all* particles), and ``-j`` can be
used to suppress the header information.

.. _usage_cmdline-extract-some-particles-from-a-file:

Extract some particles from a file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using the ``--extract`` flag to ``mcpltool``, it is possible to extract a
subset of particles from a file, into a new file. Using the ``-p`` flag, one
can select according to `particle
type <https://pdg.lbl.gov/2024/reviews/rpp2024-rev-monte-carlo-numbering.pdf>`__
(2112=neutron, 22=gamma, etc.). Since MCPL release 3.0.0, names of
:ref:`common particles <usage_expressions-operators-functions-and-names>`
can be used as well, as in ``-pneutron``. The comment which ``--extract`` adds
to the header of the new file will then also describe how the particles were
selected (e.g. ``mcpltool: extracted particles with -p2112``), rather than
giving the number of particles in the original file, and it can be disabled
with the new ``--no-comment`` option.

.. literalinclude:: ../build/autogen/cmdline_extract_p.txt
   :language: console

The output file is compressed with gzip if its name ends with ``.mcpl.gz``.

You can also use the ``-l`` and ``-s`` flags to extract particles according to
their position in the file, which might for instance be useful to extract a
specific interesting particle from a huge file. Here we extract 1 particle
starting from position 123:

.. literalinclude:: ../build/autogen/cmdline_extract_ls.txt
   :language: console

.. _usage_cmdline-merging-compatible-files:

Merging compatible files
~~~~~~~~~~~~~~~~~~~~~~~~

Using the ``--merge`` flag to ``mcpltool``, it is possible to merge contents
from a list of compatible files into a single new one. Here three existing
files are merged, creating newfile.mcpl as a result:

.. literalinclude:: ../build/autogen/cmdline_merge.txt
   :language: console

Note that files are considered compatible if and only if they have similar
settings and meta-data such as comments and binary blobs. Thus, the resulting
file will have the same such settings and meta-data as the originals.

.. _usage_cmdline-merging-incompatible-files-forcemerge:

Merging incompatible files ("forcemerge")
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Occasionally, the compatibility requirements for the --merge option can not be
satisfied. At the expense of discarding descriptive meta-data such as comments
and binary blobs, a brute-force merge of the files can be instead performed
with the ``--forcemerge`` flag. Here the example file is merged with a file
which was made from it with ``--select`` and ``--edit`` (see below), and thus
has more comments:

.. literalinclude:: ../build/autogen/cmdline_forcemerge.txt
   :language: console

The settings and per-particle storage requirements of the resulting file will
automatically be adapted to be such that particles from all the input files can
be safely represented. For example, even if just one input file uses
double-precision storage for its particles, the merged output file will use
double-precision for all of its particles.

Due to the loss of meta-data, the usage of the ``--forcemerge`` option should
be considered as a last-resort only and is in general not recommended.

.. _usage_cmdline-dry-runs:

Dry runs
~~~~~~~~

To see what a command would do before doing it, or to be sure that nothing is
written, add ``--dry-run`` (or ``-d``). Everything is then
done except writing files, with the same checks, warnings, errors and messages
as the real run, followed by a note that nothing was written:

.. literalinclude:: ../build/autogen/cmdline_dryrun.txt
   :language: console

This works with ``--merge``, ``--forcemerge``, ``--extract``, ``--repair`` and
``--text``, and the option is ignored with commands which do not write files
(so it can always be added), except that plots can not be saved in a dry run.

.. _usage_cmdline-selecting-editing-and-plotting-particles-with-expressions:

Selecting, editing and plotting particles with expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Particles can be selected and edited based on expressions
with the ``--select`` and ``--edit`` options, and histograms of expressions can
be plotted with ``--hist``. Here neutrons below 1 MeV within 10 cm of the z
axis are extracted, while setting their z coordinates to 0 and their
wavelengths to 1.8 Aa:

.. literalinclude:: ../build/autogen/cmdline_select_edit.txt
   :language: console

And here the energy spectrum of all particles is plotted, with a curve for each
particle type:

.. code:: console

   $ mcpltool --hist "ekin/MeV" --logx --split pdgcode example.mcpl

.. image:: ../build/autogen/cmdline_hist.png
   :alt: Energy spectrum of each particle type

The expressions, and many more examples, are described on :doc:`a page of their
own <usage_expressions>`.

.. _usage_cmdline-get-full-usage-instructions:

Get full usage instructions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full usage instructions are obtainable with the ``--help`` flag, and are also
listed in the :doc:`command reference <cmdline>`:

.. code:: console

   $ mcpltool --help

.. literalinclude:: ../build/autogen/mcpltool_help.txt
   :language: none

.. _usage_cmdline-extract-statistics-from-a-file:

Extract statistics from a file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using ``mcpltool`` with the ``--stats`` flag, it is possible to analyse a
file to get statistics of the contained particles and the distribution of their
state parameters:

.. code:: console

   $ mcpltool --stats example.mcpl

.. literalinclude:: ../build/autogen/stats_example.txt
   :language: none

Or, one can view the parameter distributions graphically by adding ``--gui``:

.. code:: console

   $ mcpltool --stats --gui example.mcpl

Resulting in plots of the file contents like these (an overview of the most
important distributions, followed by plots of each field):

.. image:: ../build/autogen/stats_overview.png
   :alt: Overview of the particles in the file

.. image:: ../build/autogen/stats_pdgcode.png
   :width: 32%
   :alt: Particle types
.. image:: ../build/autogen/stats_x.png
   :width: 32%
   :alt: Distribution of x
.. image:: ../build/autogen/stats_uz.png
   :width: 32%
   :alt: Distribution of uz

Or one can produce a PDF file like :download:`this one
<../build/autogen/mcpltool_stats.pdf>` containing the plots by adding instead
the ``--pdf`` flag:

.. code:: console

   $ mcpltool --stats --pdf example.mcpl

.. _usage_cmdline-extract-file-contents-to-text-file:

Extract file contents to text file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using ``mcpltool`` with the ``--text`` flag, it is possible to extract particle data from MCPL
files into simple text (ASCII) files. This might be useful for compatibility
with software expecting data in column-based text files, but the resulting
files are obviously significantly larger and less efficient to use than the
original MCPL files:

.. literalinclude:: ../build/autogen/cmdline_text.txt
   :language: console

The first lines of the resulting file:

.. literalinclude:: ../build/autogen/cmdline_text_head.txt
   :language: none

.. _usage_cmdline-the-minimal-mcpltool-c:

The minimal ``mcpltool-c``
--------------------------

The ``mcpl-core`` package provides a minimal version of ``mcpltool`` written
in C, ``mcpltool-c`` (which was called ``mcpltool`` before MCPL 3.0.0). It is
used in the same way, but can not show statistics or histograms, nor select or
edit particles with expressions, and some options (like ``--dry-run``) are
only available in ``mcpltool``. Its options are listed by ``mcpltool-c
--help``.
