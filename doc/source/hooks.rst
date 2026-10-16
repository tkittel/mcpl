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

.. container:: mcplcards

   .. container:: mcplcard

      .. container:: mcplcard-badge

         G4

      :doc:`Geant4 <hooks_geant4>`

      Read particles from MCPL files into Geant4 simulations, or write them to MCPL files, with the classes of the mcpl-geant4 package.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         McS

      :doc:`McStas <hooks_mcstas>`

      Read or write MCPL files in McStas instruments, with the MCPL_input and MCPL_output components.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         McX

      :doc:`McXtrace <hooks_mcxtrace>`

      Read or write MCPL files in McXtrace instruments, with the MCPL_input and MCPL_output components.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         MCNP

      :doc:`MCNP <hooks_mcnp>`

      Convert between MCPL files and the SSW files of MCNPX, MCNP5 and MCNP6, with ssw2mcpl and mcpl2ssw.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         PHITS

      :doc:`PHITS <hooks_phits>`

      Convert between MCPL files and PHITS dump files, with phits2mcpl and mcpl2phits.

   .. container:: mcplcard

      .. container:: mcplcard-badge

         \+

      :doc:`Other applications <hooks_others>`

      Many more applications support MCPL natively, like OpenMC, VITESS, RESTRAX and McVINE.

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
