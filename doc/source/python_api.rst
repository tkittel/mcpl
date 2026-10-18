********************
Python API reference
********************

The Python API is provided by the ``mcpl`` module of the ``mcpl-python``
package.

.. module:: mcpl

.. _python_api-reading-files:

Reading files
=============

.. autoclass:: mcpl.MCPLFile

.. autoclass:: mcpl.MCPLParticleBlock

.. autoclass:: mcpl.MCPLParticle

.. _python_api-writing-files:

Writing files
=============

.. autoclass:: mcpl.MCPLOutFile

.. autofunction:: mcpl.gzip_file

.. _python_api-operations-on-files:

Operations on files
===================

.. autofunction:: mcpl.merge_files
.. autofunction:: mcpl.merge_inplace
.. autofunction:: mcpl.forcemerge_files
.. autofunction:: mcpl.can_merge
.. autofunction:: mcpl.repair
.. autofunction:: mcpl.dump_file
.. autofunction:: mcpl.convert2ascii
.. autofunction:: mcpl.name_helper

.. _python_api-selecting-and-editing-particles:

Selecting and editing particles
===============================

.. autoclass:: mcpl.ParticleFilter
.. autoclass:: mcpl.ParticleEdit
.. autoclass:: mcpl.ParticleValue

.. _python_api-statistics-and-histograms:

Statistics and histograms
=========================

.. autofunction:: mcpl.collect_stats
.. autofunction:: mcpl.dump_stats
.. autofunction:: mcpl.histogram
.. autofunction:: mcpl.histogram2d
.. autofunction:: mcpl.plot_histograms

The histograms which ``histogram`` and ``histogram2d`` return (their classes
are not made directly):

.. autoclass:: mcpl._histogram.Histogram
.. autoclass:: mcpl._histogram.Histogram2D

.. _python_api-plotting:

Plotting
========

.. automodule:: mcpl.plotting
   :members:

.. _python_api-the-stat-sum-convention:

The stat:sum convention
=======================

.. autofunction:: mcpl.encode_stat_sum
.. autofunction:: mcpl.is_valid_stat_sum_key

.. _python_api-mpi-helpers:

MPI helpers
===========

.. autofunction:: mcpl.create_outfile_mpi
.. autofunction:: mcpl.merge_outfiles_mpi

.. _python_api-messages-and-errors:

Messages and errors
===================

.. autofunction:: mcpl.use_logging
.. autoexception:: mcpl.MCPLError

.. _python_api-physical-constants:

Physical constants
==================

.. automodule:: mcpl.constants
   :members:

.. _python_api-the-mcpltool-command:

The mcpltool command
====================

.. autofunction:: mcpl.app_mcpltool
