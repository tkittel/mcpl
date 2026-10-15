********************
MCPL hooks in McStas
********************

MCPL input or output from `McStas <http://mcstas.org>`__ is handled via two
components,
`MCPL_input <https://mcstas.org/download/components/current/misc/MCPL_input.html>`__
and
`MCPL_output <https://mcstas.org/download/components/current/misc/MCPL_output.html>`__,
which users can activate by adding entries at relevant points in their
instrument files. Please refer to `the MCPL paper (section
3.3) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.3.3>`__ for
a more detailed discussion of these.

.. _hooks_mcstas-how-to-use-the-components:

How to use the components
-------------------------

.. _hooks_mcstas-mcpl_input:

MCPL_input
~~~~~~~~~~

In its most simple form, users can add the following lines to their instrument
files in order to inject particles from an MCPL file into their instrument
simulations:

.. code:: c

   COMPONENT vin = MCPL_input(
     filename="myfile.mcpl" )
   AT(0,0,0) RELATIVE Origin

The initial position of the particles will be given by the coordinates found in
the MCPL file, relative to the position of the MCPL_input component in the
instrument. In the example above, the particle coordinates will thus be
interpreted as being relative to the Origin component.

For further details, refer to `the MCPL paper (section
3.3) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.3.3>`__
and/or bring up documentation specific to the actual version of MCPL_input
being used by typing:

.. code:: shell

   mcdoc MCPL_input

.. _hooks_mcstas-mcpl_output:

MCPL_output
~~~~~~~~~~~

In its most simple form, users can add the following lines to their instrument
files at a given point in order to capture a snapshot of particles at that
point in their instrument simulations and store them in an MCPL file:

.. code:: c

   COMPONENT mcplout = MCPL_output(
     filename="myoutput.mcpl" )
   AT(0,0,0) RELATIVE PREVIOUS

The coordinates of the stored particle will be relative to the MCPL_output
component itself. Thus, the above lines capture particles relative to the
previous component. This could for instance make sense if the previous
component was the sample component, and you need the coordinates to be written
to be relative to the sample position. If instead you need the coordinates to
be absolute, you could either specify ``ABSOLUTE`` or position it relative to
the ``Origin`` component:

.. code:: c

   COMPONENT mcplout = MCPL_output(
     filename="myoutput.mcpl" )
   AT(0,0,0) ABSOLUTE

For further details, refer to `the MCPL paper (section
3.3) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.3.3>`__
and/or bring up documentation specific to the actual version of MCPL_output
being used by typing:

.. code:: shell

   mcdoc MCPL_output
