*******************************
Application-specific MCPL hooks
*******************************

In addition to using :doc:`generic tools <usage_cmdline>` to access and
manipulate MCPL files, it is the intention that most users should be able to
use MCPL as a means for file-based i/o of their simulation application, simply
by utilising existing plugins and converters ("hooks") written by experts of
those applications (possibly in collaboration with MCPL experts).

While more details about some such plugins and converters can be found in `the
MCPL paper (section
3) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=section.3>`__, brief
documentation of some hooks can also be found on pages of this website. Use the
menu or one of the following links to learn more about hooks for particular
applications:

- :doc:`MCPL hooks for Geant4 <hooks_geant4>`
- :doc:`MCPL hooks for McStas <hooks_mcstas>`
- :doc:`MCPL hooks for McXtrace <hooks_mcxtrace>`
- :doc:`MCPL hooks for MCNP <hooks_mcnp>`
- :doc:`MCPL hooks for PHITS <hooks_phits>`
- :doc:`MCPL hooks for other applications <hooks_others>`

Please :doc:`get in touch <contact>` if you are interested in helping out
with providing hooks for applications not listed above, or to provide feedback
on the existing hooks.

.. toctree::
   :hidden:

   hooks_geant4
   hooks_mcstas
   hooks_mcxtrace
   hooks_mcnp
   hooks_phits
   hooks_others
