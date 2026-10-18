*****************
Command reference
*****************

.. _cmdline-the-mcpltool-command:

The ``mcpltool`` command
========================

The ``mcpltool`` command inspects and modifies MCPL files. Its built-in
documentation is repeated here: all options (``mcpltool --full-help``), and how
to write the expressions of the ``-p``, ``-E`` and ``-H`` options (``mcpltool
-p help``, ``-E help`` and ``-H help``). The most common options are also
summarised by ``mcpltool -h``.

.. literalinclude:: ../build/autogen/mcpltool_fullhelp.txt
   :language: none

The ``mcpl-core`` package also provides a minimal version of ``mcpltool``
written in C, ``mcpltool-c`` (see :ref:`Using MCPL from the command line
<usage_cmdline-the-minimal-mcpltool-c>`).

.. _cmdline-pick-expressions:

Expressions for ``-p``
----------------------

.. literalinclude:: ../build/autogen/mcpltool_help_pick.txt
   :language: none

.. _cmdline-edit-expressions:

Statements for ``-E``
---------------------

.. literalinclude:: ../build/autogen/mcpltool_help_edit.txt
   :language: none

.. _cmdline-hist-expressions:

Histograms for ``-H``
---------------------

.. literalinclude:: ../build/autogen/mcpltool_help_hist.txt
   :language: none
