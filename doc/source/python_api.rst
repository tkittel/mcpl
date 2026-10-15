********************
Python API reference
********************

The Python API is provided by the ``mcpl`` module of the ``mcpl-python``
package.

.. module:: mcpl

Reading files
=============

.. autoclass:: mcpl.MCPLFile

.. autoclass:: mcpl.MCPLParticleBlock

.. autoclass:: mcpl.MCPLParticle

Writing files
=============

.. autoclass:: mcpl.MCPLOutFile

.. autofunction:: mcpl.gzip_file

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

Selecting and editing particles
===============================

.. autoclass:: mcpl.ParticleFilter
.. autoclass:: mcpl.ParticleEdit
.. autoclass:: mcpl.ParticleValue

Statistics and histograms
=========================

.. autofunction:: mcpl.collect_stats
.. autofunction:: mcpl.dump_stats
.. autofunction:: mcpl.stats_figures
.. autofunction:: mcpl.plot_stats
.. autoclass:: mcpl.Histogram
.. autoclass:: mcpl.Histogram2D
.. autofunction:: mcpl.histogram
.. autofunction:: mcpl.histogram2d
.. autofunction:: mcpl.plot_histograms

Plotting
========

.. automodule:: mcpl.plotting
   :members:

The stat:sum convention
=======================

.. autofunction:: mcpl.encode_stat_sum
.. autofunction:: mcpl.is_valid_stat_sum_key

MPI helpers
===========

.. autofunction:: mcpl.create_outfile_mpi
.. autofunction:: mcpl.merge_outfiles_mpi

Messages and errors
===================

.. autofunction:: mcpl.use_logging
.. autoexception:: mcpl.MCPLError

Physical constants
==================

.. automodule:: mcpl.constants
   :members:

The pymcpltool command
======================

.. autofunction:: mcpl.app_pymcpltool
