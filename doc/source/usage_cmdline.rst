********************************
Using MCPL from the command line
********************************

MCPL provides the command-line tool ``mcpltool`` (from the ``mcpl-python``
package), which can be used to inspect MCPL files, show statistics and plots of
their contents, pick or edit particles with expressions, and carry out
operations like merging, extracting, or repairing files. Before MCPL 3.0.0, it
was called ``pymcpltool``.

This page includes a few examples of how ``mcpltool`` can be used. `The MCPL
paper (section 2.3)
<https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.2.3>`__ describes
the earlier version of the tool (written in C).

.. _usage_cmdline-examples:

Examples
--------

A few examples of how to use ``mcpltool`` are provided here (the outputs shown
are those of the current version of ``mcpltool``). Note that a small sample
MCPL file is available at
`examples/example.mcpl <https://github.com/mctools/mcpl/raw/HEAD/examples/example.mcpl>`__,
in case new users would like something to try the ``mcpltool`` on, and
``mcpltool --create-examples`` creates three larger example files (with a
million particles each by default, or N with ``--create-examples=N``).

.. _usage_cmdline-inspect-file-contents:

Inspect file contents
~~~~~~~~~~~~~~~~~~~~~

Simply invoking ``mcpltool`` on a file with no additional arguments, results
in a summary of the header information being printed, in addition to the
particle state information of the first ten particles in the file:

.. literalinclude:: ../build/autogen/cmdline_inspect.txt
   :language: console

The ``-l`` (limit) and ``-s`` (skip) flags can be used to change which
particles are printed (use ``-l0`` to print *all* particles), ``-n`` suppresses
the header information, and ``-j`` shows only the header.

.. _usage_cmdline-extract-some-particles-from-a-file:

Extract some particles from a file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using the ``-e`` (``--extract``) flag to ``mcpltool``, it is possible to
extract a subset of particles from a file, into a new file. With ``-p``
(``--pick``), the particles are picked with an :doc:`expression
<usage_expressions>`, for instance by `particle
type <https://pdg.lbl.gov/2024/reviews/rpp2024-rev-monte-carlo-numbering.pdf>`__
(2112=neutron, 22=gamma, etc., or the names of :ref:`common particles
<usage_expressions-operators-functions-and-names>`). The comment which ``-e``
adds to the header of the new file describes how the particles were extracted
(e.g. ``mcpltool: extracted particles with -p "pdgcode==neutron"``, with the
expressions in their :ref:`canonical forms <usage_expressions-from-python>`,
so that files extracted in the same way can be merged), and it can be disabled
with the ``--no-comment`` option.

.. literalinclude:: ../build/autogen/cmdline_extract_p.txt
   :language: console

The output file is compressed with gzip if its name ends with ``.mcpl.gz``.
Existing files are not overwritten, unless the ``--allow-overwrite`` option is
given (this holds for all files written by ``mcpltool``).

You can also use the ``-l`` and ``-s`` flags to extract particles according to
their position in the file, which might for instance be useful to extract a
specific interesting particle from a huge file. Here we extract 1 particle
starting from position 123:

.. literalinclude:: ../build/autogen/cmdline_extract_ls.txt
   :language: console

.. _usage_cmdline-merging-compatible-files:

Merging compatible files
~~~~~~~~~~~~~~~~~~~~~~~~

Using the ``-m`` (``--merge``) flag to ``mcpltool``, it is possible to merge
contents from a list of compatible files into a single new one. Here three
existing files are merged, creating newfile.mcpl.gz as a result:

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
which was made from it with ``-p`` and ``-E`` (see below), and thus has more
comments:

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
done except writing files, with the same checks, warnings, errors, and messages
as the real run, followed by a note that nothing was written:

.. literalinclude:: ../build/autogen/cmdline_dryrun.txt
   :language: console

This works with ``-m``, ``--forcemerge``, ``-e``, ``-r``, ``--text``, and
``--create-examples``, and
the option is ignored with commands which do not write files (so it can always
be added), except that plots can not be saved in a dry run (with ``-o``).

.. _usage_cmdline-selecting-editing-and-plotting-particles-with-expressions:

Picking, editing, and plotting particles with expressions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Particles can be picked and edited based on expressions with the ``-p``
(``--pick``) and ``-E`` (``--edit``) options, and a histogram of expressions
can be plotted with ``-H HIST`` (``--hist``, in a window, or with ``-t`` in
the terminal). Here neutrons below 1 MeV within 10 cm
of the z axis are extracted, while setting their z coordinates to 0 and their
wavelengths to 1.8 Aa:

.. literalinclude:: ../build/autogen/cmdline_pick_edit.txt
   :language: console

With ``--code=c`` (or ``--code=cpp``), ``-e`` instead prints a complete C (or
C++) program doing the same, with the other options, for files like the given
one (with the same userdata layout). The program takes the input and output
files as arguments, and is built against MCPL like any other program using it
(see :doc:`usage_c` and :doc:`usage_cpp`):

.. literalinclude:: ../build/autogen/cmdline_code.txt
   :language: none

And here the energy spectrum of all particles is plotted, with a curve for each
particle type (the options of the histogram follow the expression, separated
by ``;``):

.. code:: console

   $ mcpltool -H "ekin/MeV;logx" example.mcpl

.. image:: ../build/autogen/cmdline_hist.png
   :alt: Energy spectrum of each particle type

With ``-w``, the plot is shown in a window with matplotlib (an error says so
when this is not possible), and with ``-t`` in the terminal, drawn with
Unicode characters (or ASCII characters, in terminals which can not show
them):

.. literalinclude:: ../build/autogen/cmdline_hist_term.txt
   :language: none

In terminals, such plots are shown in colour, unless the ``NO_COLOR``
environment variable is set (or always, if ``FORCE_COLOR`` is set), which
``--color=always`` or ``--color=never`` overrides. With ``-o FILE``, the plot
is saved in a file instead, in the format given by the extension: ``.png``,
``.pdf``, or ``.svg`` with ``-w``, and ``.txt`` (the plot drawn as text) with
``-t``.
The expressions, and many more examples, are described on :doc:`a page of their
own <usage_expressions>`.

.. _usage_cmdline-get-full-usage-instructions:

Get usage instructions
~~~~~~~~~~~~~~~~~~~~~~

A summary of the most common options is shown with ``-h`` (``--help``):

.. code:: console

   $ mcpltool -h

.. literalinclude:: ../build/autogen/mcpltool_help.txt
   :language: none

All options are shown with ``--full-help``, and how to write the expressions
of ``-p`` and ``-E`` and the histograms with ``-p help``, ``-E help``, and
``--hist-help``.
All of these are also listed in the :doc:`command reference <cmdline>`.

.. _usage_cmdline-extract-statistics-from-a-file:

Extract statistics from a file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using ``mcpltool`` with the ``-S`` (``--stats``) flag, it is possible to
analyse a file to get statistics of the contained particles and the
distribution of their state parameters (also with ``-p``, ``-E``, ``-l``, and
``-s``, for only some of the particles):

.. code:: console

   $ mcpltool -S example.mcpl

.. literalinclude:: ../build/autogen/stats_example.txt
   :language: none

For plots of the particles, use the viewer (``-w`` or ``-t``, see below) or
histograms (``-H HIST``).

.. _usage_cmdline-view-the-particles-interactively:

View the particles interactively
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With ``-w`` (``--window``), ``mcpltool`` opens a viewer in a window (with Tk,
the ``tkinter`` module of Python, and the plots drawn with matplotlib), and
with ``-t`` (``--terminal``) in the terminal:

.. code:: console

   $ mcpltool -w example.mcpl

.. image:: ../build/autogen/viewer.png
   :alt: The viewer of mcpltool

It shows histograms of the particles (as for ``-H HIST``) in groups, by default the
spectra (energy, also per unit lethargy, wavelength, time, and particle types)
and the particle fields (in the window with an overview of each group: all its
plots together, or for the correlations a correlation plot of the fields which
vary, with the correlation coefficients of each pair). Below an overview, its settings choose which
particles its plots show ("Display only": by default all, but the most common
type for the correlations), whether they show a curve for each particle type
("Display by", the default) or one curve, and the fields of the correlation plot.
New plots are added to the group "Custom", where they can be reordered and
removed; changing a plot of the other groups copies it there. In the window,
the groups are cards, which show their overviews when clicked. A click on a
plot of an overview shows it on its own (``b``, or the button "Overview" at
the left of its header, returns to the overview), and its menu (a right click) copies it to make a
changed copy ("Copy and edit"), and moves or removes the custom plots. Up and
Down show the previous or next group, or plot of the shown overview. The
other groups (geometry, the beam profiles along z, x, and y, 3D plots, and
the correlations) are listed in grey in their places, and activated with a
click (and deactivated with a right click on their cards).
Each group adds plots of its own, and a plot in several groups is the same
plot.
With the shown plot are
its X, Y, and Z axes (a quantity from the list, or any expression), its settings (such as
logarithmic scales, also chosen by clicking on the colour bar of a 2D plot).
"Advanced" shows instead the plot expression, which has the axes and settings,
and "+ New plot" starts a new plot there.
"Show plot code" shows the ``mcpltool`` command and the Python code making the shown
plot. "Show code" (with the pick and edit) shows the command and the code (in
Python, C, and C++) writing the picked and edited particles to a new file, and
"Write file" writes it (also showing the command and code).
In the menu (m), "Open MCPL file..." (Ctrl+O or Alt+O) shows another file with the
same plots, pick and edit, and the menu "Help" (h) describes the viewer and
the expressions (as ``-p help``, ``-E help``, and ``--hist-help``), and MCPL itself
(its version, website, and where to get support). The particles are kept in memory (the cache, up to 100 MB of them),
so that changes do not read the file again. The button at the right of the name
of the file shows the memory used and the share of the particles which fit in it
(purple while they are put there), in red when not all particles fit, and then
the plots use only the first particles, those which fit (counted before the
pick; new files always get all particles). The numbers of picked particles are
then estimated for all particles (marked with |approx|). Its menu says how many
particles each amount of memory gives, or turns the cache off. In both
viewers, the plots can be changed (Enter),
reordered (Shift+Up or Shift+Down), and removed, further ones added (``a``),
and the particles of all plots can be
changed in their fields: Skip and Limit (like ``-s`` and ``-l``), Pick and Edit
(like ``-p`` and ``-E``). The plots are updated while the file is read. With
``w``, the picked and edited particles are written to a file (asking before
overwriting an existing one), and ``h`` shows the help.

With ``v``, the state of the viewer (the fields, the groups shown, and the
plots) is saved in a file, which ``mcpltool -w FILE.json FILE`` (or with ``-t``)
opens again. When the viewer is closed, the command opening it again in the
same state is printed (with its state as text, as in
``-w "{'groups':['spectra','beamz']}"``). The groups are also chosen with
``c`` in the viewer.

The viewer in the terminal (``-t``) uses the ``curses`` module of Python, which
on Windows needs the ``windows-curses`` package (included in the ``curses``
and ``all`` extras of ``mcpl-python``). It draws the plots with Unicode
characters (or ASCII characters, in terminals which can not show them), and
``--color=never`` turns off its colours (as for ``-t -H HIST``). With ``o``, it
opens the current plot in a window, and with ``g`` the whole viewer, in the
same state (if Tk can open a window there).

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

.. |approx| unicode:: U+2248
