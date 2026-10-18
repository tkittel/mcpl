********************************************************
Picking, editing and plotting particles with expressions
********************************************************

The ``mcpltool`` command and the ``mcpl`` Python module can pick, edit and
plot particles based on short expressions like
``"pdgcode == neutron and ekin < 25meV"``. This page describes the syntax of
these expressions, and shows how to use them from the :doc:`command
line <usage_cmdline>` and from :doc:`Python <usage_python>`.

Expressions are used in three ways:

+------------------+-------------------+--------------------------+-------------------------------------------+
| Use              | Command line      | Python API               | Example                                   |
+==================+===================+==========================+===========================================+
| Pick particles   | ``-p PICK``       | ``ParticleFilter(PICK)`` | ``"pdgcode == neutron and ekin < 25meV"`` |
+------------------+-------------------+--------------------------+-------------------------------------------+
| Edit particles   | ``-E EDIT``       | ``ParticleEdit(EDIT)``   | ``"z += 1m;weight *= 0.5"``               |
+------------------+-------------------+--------------------------+-------------------------------------------+
| Values for       | ``-H HIST``       | ``ParticleValue(EXPR)``, | ``"ekin/eV"``                             |
| histograms       |                   | ``histogram(..)``        |                                           |
+------------------+-------------------+--------------------------+-------------------------------------------+

Expressions are evaluated efficiently with NumPy on blocks of particles, and
not with Python's ``eval()``, so they can only do what is described here.
Whitespace, including newlines, only separates the parts of expressions, so
long expressions can be written over several lines (in Python code).
Expressions can only contain printable ASCII characters, and not the
characters ``" ' { } [ ] # $`` backtick or backslash. With ``mcpltool``, put
them in double quotes, which works in all the usual shells on Unix and
Windows.

.. _usage_expressions-particle-fields:

Particle fields
---------------

Expressions use the same names for the particle fields as the Python API:

+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| Name                    | Description                                                                       | Units                   |
+=========================+===================================================================================+=========================+
| ``x``, ``y``, ``z``     | Position                                                                          | length                  |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``ux``, ``uy``, ``uz``  | Direction (unit vector)                                                           | none                    |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``polx``, ``poly``,     | Polarisation vector                                                               | none                    |
| ``polz``                |                                                                                   |                         |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``ekin``                | Kinetic energy                                                                    | energy                  |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``time``                | Time                                                                              | time                    |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``weight``              | Weight                                                                            | none                    |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``pdgcode``             | Particle type (`PDG                                                               | none (integer)          |
|                         | code <https://pdg.lbl.gov/2024/reviews/rpp2024-rev-monte-carlo-numbering.pdf>`__) |                         |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``userflags``           | User flags                                                                        | none (integer)          |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``fileidx``             | Position of the particle in the file, counting from 0 (can not be edited)         | none (integer)          |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+
| ``wavelength``          | Wavelength of neutrons and gammas (calculated from ``ekin``)                      | length                  |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+

The wavelength is only defined for neutrons and gammas, and it is an error to
use it for other particles. Expressions must therefore pick neutrons or
gammas before using the wavelength, as in
``"pdgcode == neutron and wavelength > 1.8Aa"``. The right side of ``and`` is
only evaluated for the particles where the left side is true (and the right
side of ``or`` only where the left side is false), so here the wavelength is
only used for neutrons. Without the ``pdgcode == neutron``, the expression
gives an error for files which contain other particles than neutrons and
gammas.

.. _usage_expressions-units:

Units
-----

Values which have units must always be given with units (except for a plain
``0``, which is the same in all units, as in ``x > 0``). The units are:

+--------------------------------------+--------------------------------------+
| Quantity                             | Units                                |
+======================================+======================================+
| Energy                               | ``meV``, ``eV``, ``keV``, ``MeV``,   |
|                                      | ``GeV``, ``TeV``                     |
+--------------------------------------+--------------------------------------+
| Time                                 | ``ns``, ``us``, ``ms``, ``s``        |
+--------------------------------------+--------------------------------------+
| Length (also wavelengths)            | ``Aa`` (Angstrom), ``nm``, ``um``,   |
|                                      | ``mm``, ``cm``, ``m``, ``km``        |
+--------------------------------------+--------------------------------------+
| Angle                                | ``deg``, ``rad`` (angles are         |
|                                      | otherwise in radians, as from        |
|                                      | ``acos``)                            |
+--------------------------------------+--------------------------------------+

Numbers followed by a unit, like ``25meV`` or ``1.8Aa`` (with or without a
space), are values with units, and a power directly after a unit only applies
to the unit (``4cm^2`` is 4 cm^2). Units are checked: values can only be added,
subtracted or compared if they have the same units (e.g. both are lengths,
which can then be in different units, like ``x < 10mm + 2cm``), and values
without units can not be combined with values with units:

::

   x < 2cm            # ok
   x > 0              # ok (0 needs no units)
   x < 2              # error: missing units
   x < 2meV           # error: length vs. energy
   x^2 + y^2 < 4cm^2  # ok (an area)
   acos(uz) < 10deg   # ok
   x = 2m*ux          # ok (in -E)
   x = 2*ux           # error: no units for x

Plain numbers can still be used as factors (``2*x``) and for the fields without
units (``ux > 0.9``, ``weight *= 0.5``, ``pdgcode == 2112``). Dividing by a
unit gives a value without units, which is how `histograms <#histograms>`__
choose the units of their axes: ``ekin/eV`` is the kinetic energy in eV.

.. _usage_expressions-operators-functions-and-names:

Operators, functions and names
------------------------------

+--------------------------------------+--------------------------------------+
| Arithmetic                           | ``+``, ``-``, ``*``, ``/``, and      |
|                                      | ``^`` (or ``**``) for powers         |
+--------------------------------------+--------------------------------------+
| Comparisons                          | ``==``, ``!=``, ``<``, ``<=``,       |
|                                      | ``>``, ``>=`` (which can be chained, |
|                                      | as in ``0 < x < 2cm``)               |
+--------------------------------------+--------------------------------------+
| Logic                                | ``and``, ``or``, ``not``             |
+--------------------------------------+--------------------------------------+
| Bitwise (for ``userflags``)          | ``&``, \|, ``~`` (not), with         |
|                                      | integers like ``16``, ``0x10`` or    |
|                                      | ``0b10000``                          |
+--------------------------------------+--------------------------------------+
| Functions                            | ``sqrt``, ``abs``, ``floor``,        |
|                                      | ``ceil``, ``exp``, ``log``,          |
|                                      | ``log10``, ``sin``, ``cos``,         |
|                                      | ``tan``, ``asin``, ``acos``,         |
|                                      | ``atan``, ``atan2(y,x)``,            |
|                                      | ``hypot(a,b,...)``,                  |
|                                      | ``min(a,b,...)``, ``max(a,b,...)``,  |
|                                      | ``clamp(value,low,high)``,           |
|                                      | ``mod(a,b)`` (integers),             |
|                                      | ``angle_to(x,y,z)``                  |
+--------------------------------------+--------------------------------------+
| Constants                            | ``pi``                               |
+--------------------------------------+--------------------------------------+

The function ``hypot`` takes two or more arguments, so ``hypot(x,y)`` is the
distance from the z axis and ``hypot(x,y,z)`` the distance from the origin. The
function ``angle_to(x,y,z)`` gives the angle between the direction of the
particles and the vector (x,y,z), precisely also for very small angles (unlike
``acos``). For instance, ``angle_to(0,0,1) < 1deg`` selects particles within 1
degree of the z axis, and ``angle_to(x,y,z)`` is the angle between the
direction and the position. The function ``mod(a,b)`` gives the remainder of
the division of two integers without units, so ``mod(fileidx,10) == 0`` picks
every tenth particle in the file.

The C-like operators ``&&``, ``||``, ``!`` and ``%`` can not be used, and give
an error saying what to write instead (``!=`` can of course be used).

Instead of PDG codes, the following names can be used for common particles:

================================== ===========
Name                               PDG code
================================== ===========
``neutron``, ``antineutron``       2112, -2112
``proton``, ``antiproton``         2212, -2212
``electron``                       11
``positron`` (or ``antielectron``) -11
``muon``, ``antimuon``             13, -13
``gamma`` (or ``photon``)          22
================================== ===========

For instance, ``-p "pdgcode == neutron"`` picks the neutrons.

.. _usage_expressions-selecting-particles:

Picking particles
-----------------

Picks are expressions which are true for the particles to pick:

::

   pdgcode == neutron and ekin < 25meV
   pdgcode == gamma and hypot(x,y) < 5cm
   pdgcode == neutron and acos(uz) < 2deg
   x > 0 and 0 < z < 1m
   userflags & 0x10
   (userflags & 0xff) == 7 or time > 10us
   not (pdgcode == neutron or pdgcode == gamma)

Integers which are not 0 count as true, so ``userflags & 0x10`` picks the
particles for which this bit is set in the userflags.

On the command line, ``-p`` can be used when showing particles, when
extracting particles into a new file (``-e``), with ``-S`` and with ``-H``.
Here the gammas above 1 MeV are shown (``-n`` leaves out the header):

.. literalinclude:: ../build/autogen/cmdline_pick_show.txt
   :language: console

The ``-l`` and ``-s`` options choose a range of particles in the file, after
which the particles are picked (and edited). When showing particles, at most
10 of the picked particles are shown unless ``-l`` is given.

.. _usage_expressions-editing-particles:

Editing particles
-----------------

Edits are statements separated by ``;``, which are executed in order (so each
statement sees the results of the previous ones):

::

   z += 1m;time += 1.5ms
   wavelength = 1.8Aa
   weight *= 0.5;pdgcode = neutron
   rotate_y(90deg);x += 10cm
   tmp = x;x = y;y = tmp
   swap(x, y)
   x = clamp(x, -5cm, 5cm)

The statements are:

+-------------------------+-------------------------+-------------------------+
| Statement               | Example                 |                         |
+=========================+=========================+=========================+
| Assignment to a field   | ``z += 1m``             | Also with ``=``,        |
|                         |                         | ``-=``, ``*=`` and      |
|                         |                         | ``/=``. The values must |
|                         |                         | have the units of the   |
|                         |                         | field (e.g. a length    |
|                         |                         | for ``x``, an energy    |
|                         |                         | for ``ekin``).          |
|                         |                         | Assigning the           |
|                         |                         | wavelength changes the  |
|                         |                         | kinetic energy, and is  |
|                         |                         | only possible for       |
|                         |                         | neutrons and gammas.    |
+-------------------------+-------------------------+-------------------------+
| Assignment to a         | ``tmp = x``             | Variables are lowercase |
| variable                |                         | names which are not     |
|                         |                         | names of fields, units, |
|                         |                         | constants or functions. |
|                         |                         | They keep the units of  |
|                         |                         | their values, and can   |
|                         |                         | be used in later        |
|                         |                         | statements, for         |
|                         |                         | instance to keep the    |
|                         |                         | original value of a     |
|                         |                         | field. Variables which  |
|                         |                         | are never used are      |
|                         |                         | errors (to catch typos  |
|                         |                         | in field names).        |
+-------------------------+-------------------------+-------------------------+
| ``swap(a,b)``           | ``swap(x,y)``           | Exchanges the values of |
|                         |                         | two fields (or          |
|                         |                         | variables) with the     |
|                         |                         | same units.             |
+-------------------------+-------------------------+-------------------------+
| ``rotate_x(angle)``,    | ``rotate_z(90deg)``     | Rotate the position,    |
| ``rotate_y(angle)``,    |                         | direction and           |
| ``rotate_z(angle)``     |                         | polarisation around the |
|                         |                         | given axis (through the |
|                         |                         | origin). The rotation   |
|                         |                         | is counter-clockwise    |
|                         |                         | when looking from the   |
|                         |                         | positive axis towards   |
|                         |                         | the origin. Rotations   |
|                         |                         | by multiples of 90      |
|                         |                         | degrees are exact.      |
+-------------------------+-------------------------+-------------------------+

Since the statements are executed in order, ``x = -y;y = x`` sets both ``x``
and ``y`` to ``-y``. A rotation around the z axis by 90 degrees can instead be
written as ``rotate_z(90deg)``, or with a variable as
``tmp = x;x = -y;y = tmp``. The order also matters for combinations of
rotations and translations: ``rotate_y(90deg);x += 10cm`` first rotates and
then moves the particles along the (new) x axis, while
``x += 10cm;rotate_y(90deg)`` moves them before the rotation (so they end up
moved along the z axis).

For instance, extracting the neutrons below 1 MeV within 10 cm of the z axis,
setting their z coordinates to 0 and their wavelengths to 1.8 Aa (the
particles are picked before they are edited):

.. literalinclude:: ../build/autogen/cmdline_pick_edit.txt
   :language: console

The options are described in a comment added to the header of the new file
(e.g. ``mcpltool: extracted particles with -p "pdgcode == neutron"``), unless
the ``--no-comment`` option is used. Since files can only be merged if their
comments are identical, files extracted in different ways can only be merged
if they were extracted with ``--no-comment``.

Following the :doc:`stat:sum <format_statsum>` guidelines, *stat:sum*
entries in the header are kept when particles are picked based on their
properties, but marked as not available (-1) when they are picked based on
their position in the file (with ``-l``, ``-s``, or ``fileidx`` in ``-p``) or
when their weights are edited. In the latter case, ``--keep-statsum`` keeps them, for edits which are
known to be compatible with the *stat:sum* entries.

.. _usage_expressions-histograms:

Histograms
----------

Histograms show the values of an expression without units, so values with units
are divided by a unit, which then becomes the unit of the axis (e.g.
``ekin/eV`` or ``hypot(x,y)/mm``). With ``-H`` (``--hist``), ``mcpltool`` plots
such histograms. The options of the histogram follow the expression, separated
by ``;``:

.. code:: shell

   mcpltool -H "ekin/MeV;logx;split=pdgcode" example.mcpl

This shows the kinetic energy spectrum with logarithmic bins, with a curve for
each particle type. The options in the histogram string are:

+--------------------------------------+--------------------------------------+
| Option                               |                                      |
+======================================+======================================+
| ``bins=N``                           | Number of bins (default: chosen from |
|                                      | the number of particles).            |
+--------------------------------------+--------------------------------------+
| ``range=LOW:HIGH``                   | Range of the histogram, in the units |
|                                      | of the expression (default is all    |
|                                      | values).                             |
+--------------------------------------+--------------------------------------+
| ``logx``, ``logy``                   | Logarithmic bins and x axis, or      |
|                                      | logarithmic y axis.                  |
+--------------------------------------+--------------------------------------+
| ``lethargy``                         | Divide the contents by the bin       |
|                                      | widths in lethargy, ln(E2/E1), as is |
|                                      | usual for energy spectra (implies    |
|                                      | ``logx``).                           |
+--------------------------------------+--------------------------------------+
| ``split=EXPR``                       | A curve for each value of the        |
|                                      | expression, e.g. ``split=pdgcode``   |
|                                      | or ``split=x > 0cm``.                |
+--------------------------------------+--------------------------------------+
| ``unweighted``                       | Count particles rather than summing  |
|                                      | their weights.                       |
+--------------------------------------+--------------------------------------+
| ``print``                            | Print the contents of the histogram  |
|                                      | as text instead of plotting it.      |
+--------------------------------------+--------------------------------------+

And the options of ``mcpltool`` for histograms are:

+--------------------------------------+--------------------------------------+
| Option                               |                                      |
+======================================+======================================+
| ``-p PICK``, ``-E EDIT``,            | Only use the picked particles (and   |
| ``-lN``, ``-sN``                     | edit them), or only a range of the   |
|                                      | particles in the file.               |
+--------------------------------------+--------------------------------------+
| ``-t``                               | Show the plot in the terminal.       |
+--------------------------------------+--------------------------------------+
| ``-o FILE``                          | Save the plot in a file, in the      |
|                                      | format given by the extension:       |
|                                      | ``.png``, ``.pdf``, ``.svg``, or     |
|                                      | ``.txt`` for plots drawn as text.    |
+--------------------------------------+--------------------------------------+
| ``-B NAME``                          | Plotting backend: ``matplotlib``, or |
|                                      | ``unicode`` and ``ascii`` which draw |
|                                      | plots as text. By default, plots are |
|                                      | shown in a window with matplotlib,   |
|                                      | or else in the terminal, and saved   |
|                                      | with the backend for the format.     |
+--------------------------------------+--------------------------------------+

With more than one file, there is a curve for each file, and two expressions
separated by ``:`` give a 2D histogram, with the options ``xrange=LOW:HIGH``
and ``yrange=LOW:HIGH`` for the ranges of the axes (e.g.
``-H "x/cm : y/cm;xrange=-10:10"``). For instance, the neutron spectrum per
unit lethargy, printed as a table:

.. literalinclude:: ../build/autogen/cmdline_hist_print.txt
   :language: console

.. _usage_expressions-more-command-line-examples:

More command line examples
--------------------------

.. code:: shell

   # Neutron spectrum per unit lethargy:
   mcpltool -H "ekin/eV;lethargy" \
     -p "pdgcode == neutron" run.mcpl.gz

   # Neutron wavelengths from 0 to 10 Aa, in a PDF:
   mcpltool -H "wavelength/Aa;range=0:10;bins=200" \
     -p "pdgcode == neutron" -o wl.pdf run.mcpl.gz

   # Positions of the neutrons in the x-y plane:
   mcpltool -H "x/cm : y/cm" -p "pdgcode == neutron" \
     run.mcpl.gz

   # Distance from the z axis, from 0 to 50 mm:
   mcpltool -H "hypot(x,y)/mm;range=0:50" run.mcpl.gz

   # Angle to the z axis for each particle type:
   mcpltool -H "acos(uz)/deg;range=0:90;split=pdgcode" \
     run.mcpl.gz

   # Azimuthal angle versus polar angle:
   mcpltool -H "atan2(uy,ux)/deg : acos(uz)/deg" \
     run.mcpl.gz

   # Times of neutrons below 100 keV (log y axis):
   mcpltool -H "time/ms;logy" run.mcpl.gz \
     -p "pdgcode == neutron and ekin < 100keV"

   # Spectra of two files in one plot, in the terminal:
   mcpltool -H "ekin/MeV;logx" -t \
     before.mcpl.gz after.mcpl.gz

   # Distribution of the particle weights:
   mcpltool -H "weight;unweighted;logy" run.mcpl.gz

   # Spectra for particles with x > 0 and x < 0:
   mcpltool -H "ekin/MeV;logx;split=x > 0cm" run.mcpl.gz

   # Statistics and overview plot of gammas above 1 keV:
   mcpltool -S -p "pdgcode == gamma and ekin > 1keV" \
     run.mcpl.gz
   mcpltool -S -o gammas.pdf run.mcpl.gz \
     -p "pdgcode == gamma and ekin > 1keV"

   # The first 20 neutrons with wavelength > 4 Aa:
   mcpltool -l20 run.mcpl.gz \
     -p "pdgcode == neutron and wavelength > 4Aa"

   # New file with neutrons within 5 cm of z axis:
   mcpltool -e run.mcpl.gz out.mcpl.gz \
     -p "pdgcode == neutron and hypot(x,y) < 5cm"

   # New file with every tenth particle:
   mcpltool -e -p "mod(fileidx,10) == 0" \
     run.mcpl.gz out.mcpl.gz

   # Move particles 2 m back and delay by 1.5 ms:
   mcpltool -e run.mcpl.gz out.mcpl.gz \
     -E "z -= 2m;time += 1.5ms"

   # Make all neutrons monochromatic:
   mcpltool -e run.mcpl.gz out.mcpl.gz \
     -p "pdgcode == neutron" -E "wavelength = 1.8Aa"

   # Place particles 2 m from origin along direction:
   mcpltool -e run.mcpl.gz out.mcpl.gz \
     -E "x = 2m*ux;y = 2m*uy;z = 2m*uz"

.. _usage_expressions-from-python:

From Python
-----------

When reading or writing files, picks and edits can be given directly to
``MCPLFile`` and ``MCPLOutFile`` with the ``pick`` and ``edit`` arguments.
When reading, the blocks of particles (and single particles) then only contain
the picked particles, with the edits applied. When writing, they are applied
to all the particles added:

.. code:: python

   import mcpl
   fin = mcpl.MCPLFile(
       "input.mcpl.gz",
       pick = "pdgcode == neutron and ekin < 25meV",
       edit = "z += 1m" )
   fout = mcpl.MCPLOutFile( "output.mcpl.gz" )
   with fin, fout:
       fout.transfer_metadata( fin )
       for block in fin.particle_blocks:
           fout.add_particles( block )

Here, the particles are copied exactly, except for the edited ``z``
coordinates. Small picks from several blocks in the file are merged into
blocks of about the usual size (``blocklength``). The particles keep their
positions in the file (``fileidx`` of particles and of blocks), while
``nparticles`` is still the number of particles in the file.

The same expressions are also used by the classes ``ParticleFilter``,
``ParticleEdit`` and ``ParticleValue`` in the ``mcpl`` module, which are
applied to blocks of particles:

.. code:: python

   import mcpl
   flt = mcpl.ParticleFilter(
       "pdgcode == neutron and ekin < 25meV" )
   edit = mcpl.ParticleEdit(
       "z += 1m;wavelength = 1.8Aa" )
   val = mcpl.ParticleValue( "ekin/meV" )
   fin = mcpl.MCPLFile( "input.mcpl.gz" )
   fout = mcpl.MCPLOutFile( "output2.mcpl.gz" )
   with fin, fout:
       fout.transfer_metadata( fin )
       for block in fin.particle_blocks:
           sel = block[ flt( block ) ]
           print( val( sel ) )  # energies in meV
           fout.add_particles( sel, **edit( sel ) )

Histograms are made with ``mcpl.histogram`` (and ``mcpl.histogram2d``), which
take the same options as ``mcpltool -H``, as arguments or in the same
histogram strings. The results can be plotted, saved, or used directly:

.. code:: python

   import mcpl
   h = mcpl.histogram( "input.mcpl.gz", "ekin/eV",
                       pick = "pdgcode == neutron",
                       lethargy = True, bins = 50 )
   # Or: mcpl.histogram( "input.mcpl.gz",
   #                     "ekin/eV;lethargy;bins=50",
   #                     pick = "pdgcode == neutron" )
   h.plot()  # or h.plot( filename = "spectrum.pdf" )
   # Bin edges and values (per unit lethargy):
   print( h.edges, h.values() )

The plots are made with the plotting backend selected with the ``backend``
argument (``-B`` for ``mcpltool``) or with
``mcpl.plotting.set_default_backend(...)``. Otherwise, plots are shown in a
window with matplotlib if it is installed (and there is a display), or else in
the terminal with the ``unicode`` backend (or the ``ascii`` backend, in
terminals which can not show its characters), or always in the terminal with
``terminal = True``. Plots are saved with the backend for the format given by
the extension of the file name (see ``mcpl.plotting.available_backends()`` and
``mcpl.plotting.formats()``). The ``unicode`` and ``ascii`` backends need no
extra packages. Options for the backends are given as keyword arguments named
after the backend, like ``matplotlib_backend = "agg"`` or
``unicode_width = 100``. Custom backends can be added by subclassing
``mcpl.plotting.Backend`` and calling ``mcpl.plotting.register_backend``.

Several histograms can be shown or saved together with
``mcpl.plot_histograms``, also on top of each other in a single plot (e.g. to
compare simulations):

.. code:: python

   h1 = mcpl.histogram( "run1.mcpl.gz", "ekin/eV;logx" )
   h2 = mcpl.histogram( "run2.mcpl.gz", "ekin/eV;logx" )
   labels = [ "run 1", "run 2" ]
   mcpl.plot_histograms( [ h1, h2 ], labels = labels,
                         overlay = True )

The figures are described with the classes in the ``mcpl.plotting`` module
(``Figure``, ``Panel``, ``StepHist``, ...), which can also be used to make
other plots, shown or saved with ``mcpl.plotting.show`` and
``mcpl.plotting.save``.
