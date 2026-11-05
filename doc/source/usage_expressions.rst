***********************************************
Editing and plotting particles with expressions
***********************************************

The ``mcpltool`` command and the ``mcpl`` Python module can edit (keep and
change) and plot particles based on short expressions like
``"pdgcode == neutron and ekin < 25meV; z += 1m"``. This page describes the syntax of
these expressions, and shows how to use them from the :doc:`command
line <usage_cmdline>` and from :doc:`Python <usage_python>`.

Expressions are used in two ways:

+------------------+-------------------+--------------------------+-------------------------------------------+
| Use              | Command line      | Python API               | Example                                   |
+==================+===================+==========================+===========================================+
| Edit particles   | ``-e EDIT``       | ``ParticleEdit(EDIT)``,  | ``"pdgcode == neutron; z += 1m"``         |
|                  |                   | ``edit=EDIT``            |                                           |
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

.. _usage_expressions-examples:

Examples
--------

Some examples, from simple to advanced (which ``mcpltool -e help`` and
``--hist-help`` also show, and the "?" buttons of the viewer):

.. include:: ../build/autogen/expression_examples.rst

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
| ``userdata.NAME``       | The field NAME of the userdata, in files with userdata (can not be edited), and   | the unit of the field   |
|                         | ``userdata.NAME.at(INDEX)`` the values of fields with several values per          | in the userdata layout  |
|                         | particle, counting from 0 (e.g. ``userdata.origdir.at(2)``)                       |                         |
+-------------------------+-----------------------------------------------------------------------------------+-------------------------+

The wavelength is only defined for neutrons and gammas, and it is an error to
use it for other particles. Edits must therefore keep only neutrons or
gammas before using the wavelength, as in
``"pdgcode == neutron; wavelength > 1.8Aa"`` or
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
| Temperature (for fields of the       | ``K``                                |
| userdata with the unit ``K``)        |                                      |
+--------------------------------------+--------------------------------------+

Numbers followed by a unit, like ``25meV`` or ``1.8Aa`` (with or without a
space), are values with units (``ekin/2MeV`` is ``ekin/(2*MeV)``), and so are
units on their own (``MeV`` is ``1MeV``). Numbers with units are exact
(``5000eV`` is exactly ``5keV``). A power directly after a unit only
applies to the unit (``4cm^2`` is 4 cm^2), and half powers are possible, as in
``sqrt(ekin)/sqrt(eV)``. Units are checked: values can only be added,
subtracted, or compared if they have the same units (e.g. both are lengths,
which can then be in different units, like ``x < 10mm + 2cm``), and values
without units can not be combined with values with units:

::

   x < 2cm            # ok
   x > 0              # ok (0 needs no units)
   x < 2              # error: missing units
   x < 2meV           # error: length vs. energy
   x^2 + y^2 < 4cm^2  # ok (an area)
   acos(uz) < 10deg   # ok
   x = 2m*ux          # ok (in an edit)
   x = 2*ux           # error: no units for x

Plain numbers can still be used as factors (``2*x``) and for the fields without
units (``ux > 0.9``, ``weight *= 0.5``, ``pdgcode == 2112``). Dividing by a
unit gives a value without units: ``ekin/eV`` is the kinetic energy in eV, which
is also how the unit of the axis of a `histogram <#histograms>`__ can be
chosen.

.. _usage_expressions-operators-functions-and-names:

Operators, functions, and names
-------------------------------

+--------------------------------------+--------------------------------------+
| Arithmetic                           | ``+``, ``-``, ``*``, ``/``, ``//``   |
|                                      | (dividing non-negative integers, as  |
|                                      | in ``7//2`` which is ``3``), and     |
|                                      | ``^`` (or ``**``) for powers         |
+--------------------------------------+--------------------------------------+
| Comparisons                          | ``==``, ``!=``, ``<``, ``<=``,       |
|                                      | ``>``, ``>=`` (which can be chained, |
|                                      | as in ``0 < x < 2cm``), and ``in``   |
|                                      | or ``not in`` integers or particle   |
|                                      | names, as in                         |
|                                      | ``pdgcode in (neutron,gamma)``       |
+--------------------------------------+--------------------------------------+
| Logic                                | ``and``, ``or``, ``not``             |
+--------------------------------------+--------------------------------------+
| Bitwise (for ``userflags``)          | ``&``, \|, with integers like        |
|                                      | ``16`` or ``0x10``                   |
+--------------------------------------+--------------------------------------+
| Functions                            | ``sqrt``, ``abs``, ``round``,        |
|                                      | ``floor``, ``ceil``, ``exp``,        |
|                                      | ``log``, ``log10``, ``sin``, ``cos``,|
|                                      | ``tan``, ``asin``, ``acos``,         |
|                                      | ``atan``, ``atan2(y,x)``,            |
|                                      | ``hypot(a,b,...)``,                  |
|                                      | ``min(a,b,...)``, ``max(a,b,...)``,  |
|                                      | ``clamp(value,low,high)``,           |
|                                      | ``mod(a,b)`` (integers), and for     |
|                                      | vectors (see below) ``dot``,         |
|                                      | ``cross``, ``angle``,                |
|                                      | ``through_sphere``, and              |
|                                      | ``through_box``                      |
+--------------------------------------+--------------------------------------+
| Constants                            | ``pi``                               |
+--------------------------------------+--------------------------------------+

The function ``hypot`` takes two or more arguments, so ``hypot(x,y)`` is the
distance from the z axis and ``hypot(x,y,z)`` the distance from the origin. The
function ``mod(a,b)`` gives the remainder of
the division of two integers without units, so ``mod(fileidx,10) == 0`` keeps
every tenth particle in the file.

The C-like operators ``&&``, ``||``, ``!``, and ``%`` can not be used, and give
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

For instance, ``-e "pdgcode == neutron"`` keeps the neutrons.

.. _usage_expressions-vectors:

Vectors
-------

The position, direction, and polarisation of the particles are also vectors:
``pos``, ``dir``, and ``pol``. Other vectors are written in parentheses, with
two or three values which have the same units, as in ``(0,0,1)`` or
``(0,0,1m)`` (a plain ``0`` fits any units). The values of a vector ``v`` are
``v.x``, ``v.y``, and ``v.z``, or ``v.at(0)``, ``v.at(1)``, and ``v.at(2)``
(counting from 0). The fields are simply aliases of these values: ``y`` is
``pos.y`` (or ``pos.at(1)``), and ``uz`` is ``dir.z`` (or ``dir.at(2)``).

Vectors can be added and subtracted, and multiplied and divided by numbers
(with or without units). ``abs(v)`` is the length of a vector, ``v^2`` its
length squared, ``dot(v,w)`` and ``cross(v,w)`` the dot and cross products
(``cross`` only for 3D vectors), and ``angle(v,w)`` the angle between two
vectors, which is precise also for very small angles (unlike ``acos`` of a dot
product). ``through_sphere(c,r)`` is whether the line through the position along
the direction (forwards and backwards) passes through the sphere with the
center ``c`` and the radius ``r``, and ``through_box(c,h)`` whether it passes
through the box with its sides along the axes, the center ``c``, and the half
dimensions ``h`` (half its sizes along x, y, and z). Vectors can not be compared, which gives an error suggesting
``abs(v)``. For instance:

::

   angle(dir,(0,0,1)) < 1deg             # within 1 degree of the z axis
   abs(pos - (0,0,1m)) < 10cm            # within 10 cm of a point
   d = pos - (0,0,1m); abs(d) < 10cm     # the same, with a variable
   abs(cross(pos,dir)) < 1cm             # flying close to the origin
   through_sphere((0,0,1m),5cm)          # flying within 5 cm of a point
   through_box((0,0,1m),(5cm,5cm,1mm))   # flying through a 10x10 cm box
   angle(pos,dir)/deg                    # (a plot) direction vs. position

In edits, ``pos``, ``dir``, and ``pol`` can be assigned, as in ``pos += 50cm*dir``
(moving the particles 50 cm along their directions) or ``dir = -dir``, and
changing ``x`` changes ``pos`` and the other way around.

.. _usage_expressions-editing-particles:

Edit expressions
----------------

An edit expression is a list of statements separated by ``;``, which are
executed in order (so each statement sees the results of the previous ones).
Filter conditions keep only the particles for which they are true, and the other
statements change the particles:

::

   pdgcode == neutron and ekin < 25meV
   pdgcode == gamma; hypot(x,y) < 5cm
   z += 1m; time += 1.5ms
   pdgcode == neutron; wavelength = 1.8Aa
   rotate_y(90deg); x += 10cm; x > 0
   r = hypot(x,y); r > 2cm and r < 5cm
   tmp = x; x = y; y = tmp

The statements are:

+-------------------------+-------------------------+-------------------------+
| Statement               | Example                 |                         |
+=========================+=========================+=========================+
| Filter condition        | ``ekin < 25meV``        | Keeps only the          |
|                         |                         | particles for which it  |
|                         |                         | is true (the later      |
|                         |                         | statements do not see   |
|                         |                         | the others). Integers   |
|                         |                         | which are not 0 count   |
|                         |                         | as true, so             |
|                         |                         | ``userflags & 0x10``    |
|                         |                         | keeps the particles     |
|                         |                         | with this bit set.      |
+-------------------------+-------------------------+-------------------------+
| Assignment to a field   | ``z += 1m``             | Also with ``=``,        |
|                         |                         | ``-=``, ``*=``, ``/=``, |
|                         |                         | ``//=``, ``^=``,        |
|                         |                         | ``&=``, and ``|=``. The |
|                         |                         | values must have the    |
|                         |                         | units of the field      |
|                         |                         | (e.g. a length for      |
|                         |                         | ``x``, an energy for    |
|                         |                         | ``ekin``). Assigning    |
|                         |                         | the wavelength changes  |
|                         |                         | the kinetic energy, and |
|                         |                         | is only possible for    |
|                         |                         | neutrons and gammas.    |
+-------------------------+-------------------------+-------------------------+
| Assignment to a         | ``tmp = x``             | Variables are lowercase |
| variable                |                         | names which are not     |
|                         |                         | names of fields, units, |
|                         |                         | constants, or           |
|                         |                         | functions. They keep    |
|                         |                         | the units of their      |
|                         |                         | values, and can be used |
|                         |                         | in later statements,    |
|                         |                         | for instance to keep    |
|                         |                         | the original value of a |
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
| ``rotate_y(angle)``,    |                         | direction, and          |
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
| ``rotate_around``       | (see below)             | Rotate them around any  |
|                         |                         | axis through the        |
|                         |                         | origin.                 |
+-------------------------+-------------------------+-------------------------+
| ``rotate_frame``        | (see below)             | Rotate them from one    |
|                         |                         | frame to another.       |
+-------------------------+-------------------------+-------------------------+
| ``inactive(statement)`` | ``inactive(z += 1m)``   | Left out (the syntax of |
|                         |                         | the statement must be   |
|                         |                         | valid). The viewer      |
|                         |                         | writes it for parts     |
|                         |                         | switched off in its     |
|                         |                         | Composer.               |
+-------------------------+-------------------------+-------------------------+

The axis of ``rotate_around(axis,angle)`` is a :ref:`vector
<usage_expressions-vectors>` (which does not need to be a unit vector), and the
rotation is counter-clockwise when looking from the axis towards the origin.
``rotate_frame(v,vout,u,uout)`` is given four vectors, and
turns the direction of ``v`` into that of ``vout``, and ``u`` into ``uout``,
for instance a beam direction and an "up" direction of one frame into those of
another. The angle between ``v`` and ``u`` must be that between ``vout`` and
``uout``, and ``v`` and ``u`` must not be parallel. For instance:

.. code:: text

   rotate_around((1,1,0),30deg)
   rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))

The first rotates by 30 degrees around the axis (1,1,0), and the second turns
the z axis into the x axis while keeping the y axis (the same as
``rotate_y(90deg)``).

Since the statements are executed in order, ``x = -y;y = x`` sets both ``x``
and ``y`` to ``-y``. A rotation around the z axis by 90 degrees can instead be
written as ``rotate_z(90deg)``, or with a variable as
``tmp = x;x = -y;y = tmp``. The order also matters for combinations of
rotations and translations: ``rotate_y(90deg);x += 10cm`` first rotates and
then moves the particles along the (new) x axis, while
``x += 10cm;rotate_y(90deg)`` moves them before the rotation (so they end up
moved along the z axis).

Any other statement, like ``ekin*2``, is an error. Mind that ``x = 1cm``
changes the particles, while ``x == 1cm`` is a filter condition.

On the command line, ``-e`` can be used when showing particles, when
extracting particles into a new file (``-x``), with ``-S``, with the viewer
(``-w`` and ``-t``), and with histograms (``-H``).
Here the gammas above 1 MeV are shown (``-n`` leaves out the header):

.. literalinclude:: ../build/autogen/cmdline_edit_show.txt
   :language: console

The ``-l`` and ``-s`` options choose a range of particles in the file, before
the edit. When showing particles, at most 10 of the edited particles are shown
unless ``-l`` is given.

For instance, extracting the neutrons below 1 MeV, setting their z
coordinates to 0 and their wavelengths to 1.8 Aa, and keeping those within 10
cm of the z axis:

.. literalinclude:: ../build/autogen/cmdline_edit.txt
   :language: console

The options are described in a comment added to the header of the new file
(e.g. ``mcpltool: extracted particles with -e "pdgcode==neutron"``), unless
the ``--no-comment`` option is used. Since files can only be merged if their
comments are identical, files extracted in different ways can only be merged
if they were extracted with ``--no-comment``.

Following the :doc:`stat:sum <format_statsum>` guidelines, *stat:sum*
entries in the header are kept when the particles are filtered on their
properties or changed, scaled by the fraction of the particles in the range of
``-l`` and ``-s``, and set to -1 (not available) when ``-e`` filters on the
positions of the particles in the file (with ``fileidx``).

.. _usage_expressions-histograms:

Histograms
----------

Histograms show the values of an expression. Values with units are shown in a
suitable unit (like ``x [cm]``), unless divided by one (e.g. ``ekin/keV`` or
``hypot(x,y)/mm``), and their ranges are given with units (``range=0cm:10cm``).
Particles for which the wavelength is not defined are left out of histograms
of it.
With ``-H HIST`` (``--hist``), ``mcpltool`` plots such a histogram in a
window, and with ``-t -H HIST`` (``--terminal``) in the terminal. The options of
the histogram follow the expression, separated by ``;``:

.. code:: shell

   mcpltool -H "ekin/MeV;logx" example.mcpl

This shows the kinetic energy spectrum with logarithmic bins, with a curve for
each particle type (as by default). The options in the histogram string are (those which are
on or off are given as 1 or 0, as in ``logy=0``, and alone they are on, as in
``logy``). With ``auto``, a scale is logarithmic if the values on it span more
than two decades:

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
| ``logx=1|0|auto``                    | Whether to use a logarithmic x axis  |
|                                      | (default: auto).                     |
+--------------------------------------+--------------------------------------+
| ``logy=1|0|auto``                    | Whether to use a logarithmic y axis  |
|                                      | (default: auto).                     |
+--------------------------------------+--------------------------------------+
| ``logz=1|0|auto``                    | Whether to use a logarithmic colour  |
|                                      | scale (default: auto).               |
+--------------------------------------+--------------------------------------+
| ``equal``                            | The same scale on all axes of 2D     |
|                                      | histograms and 3D plots of           |
|                                      | expressions with the same units      |
|                                      | (e.g. ``x : y;equal``).              |
+--------------------------------------+--------------------------------------+
| ``lethargy``                         | Divide the contents by the bin       |
|                                      | widths in lethargy, ln(E2/E1), as is |
|                                      | usual for energy spectra (implies    |
|                                      | ``logx``).                           |
+--------------------------------------+--------------------------------------+
| ``display_by=EXPR``                  | A curve for each value of the        |
|                                      | expression (at most 8, the others    |
|                                      | are combined into one), by default   |
|                                      | ``pdgcode`` (a curve for each        |
|                                      | particle type), e.g.                 |
|                                      | ``display_by=x > 0cm``, or one curve |
|                                      | with ``display_by=single``.          |
+--------------------------------------+--------------------------------------+
| ``display_edit=EDIT``                | An edit of the particles of this     |
|                                      | plot only (after the edit of the     |
|                                      | file), e.g.                          |
|                                      | ``display_edit=ekin > 1MeV`` or      |
|                                      | ``display_edit=rotate_z(45deg)``. It |
|                                      | must be the last option, as it takes |
|                                      | the rest of the text (with its       |
|                                      | ``;``).                              |
+--------------------------------------+--------------------------------------+
| ``bar``, ``bar=N``                   | A bar chart of whole numbers, with   |
|                                      | the 10 (or N) largest bars, e.g.     |
|                                      | ``"pdgcode;bar"``.                   |
+--------------------------------------+--------------------------------------+
| ``unweighted``                       | Count particles rather than summing  |
|                                      | their weights.                       |
+--------------------------------------+--------------------------------------+
| ``print``                            | Print the contents of the histogram  |
|                                      | as text instead of plotting it.      |
+--------------------------------------+--------------------------------------+

The options can be used for these kinds of plots (others give an error):

.. include:: ../build/autogen/hist_option_kinds.rst

And the options of ``mcpltool`` for histograms are:

+--------------------------------------+--------------------------------------+
| Option                               |                                      |
+======================================+======================================+
| ``-e EDIT``, ``-lN``, ``-sN``        | Only use the edited particles, or    |
|                                      | only a range of the particles in the |
|                                      | file.                                |
+--------------------------------------+--------------------------------------+
| ``-o FILE``                          | Save the plot in a file instead, in  |
|                                      | the format given by the extension:   |
|                                      | ``.png``, ``.pdf``, or ``.svg``, or  |
|                                      | ``.txt`` (the plot drawn as text)    |
|                                      | with ``-t``.                         |
+--------------------------------------+--------------------------------------+
| ``--color=WHEN``                     | Colours of the plot in the terminal  |
|                                      | (with ``-t``): ``auto``, ``always``, |
|                                      | or ``never``.                        |
+--------------------------------------+--------------------------------------+

With more than one file, 1D histograms have a curve for each file (unless
``display_by`` is given). Two expressions
separated by ``:`` give a 2D histogram, with the options ``xrange=LOW:HIGH``
and ``yrange=LOW:HIGH`` for the ranges of the axes (e.g.
``-H "x/cm : y/cm;xrange=-10:10"``). Three expressions give a 3D plot of
particles randomly sampled according to weights, not with ``-t`` (e.g.
``-H "x : y : z"``, with ``maxpoints=N`` for the largest number of points, by
default 5000; the same particles are always chosen). For instance,
the neutron spectrum per unit lethargy, printed as a table:

.. literalinclude:: ../build/autogen/cmdline_hist_print.txt
   :language: console

.. _usage_expressions-more-command-line-examples:

More command line examples
--------------------------

.. code:: shell

   # Neutron spectrum per unit lethargy:
   mcpltool -H "ekin/eV;lethargy" \
     -e "pdgcode == neutron" run.mcpl.gz

   # Neutron wavelengths from 0 to 10 Aa, in a PDF:
   mcpltool -H "wavelength/Aa;range=0:10;bins=200" \
     -e "pdgcode == neutron" -o wl.pdf run.mcpl.gz

   # Positions of the neutrons in the x-y plane:
   mcpltool -H "x/cm : y/cm" -e "pdgcode == neutron" \
     run.mcpl.gz

   # Distance from the z axis, from 0 to 50 mm:
   mcpltool -H "hypot(x,y)/mm;range=0:50" run.mcpl.gz

   # Angle to the z axis for each particle type:
   mcpltool -H "acos(uz)/deg;range=0:90" run.mcpl.gz

   # The same, above 1 MeV and as one curve:
   mcpltool -H "acos(uz)/deg;display_by=single;display_edit=ekin > 1MeV" \
     run.mcpl.gz

   # Azimuthal angle versus polar angle:
   mcpltool -H "atan2(uy,ux)/deg : acos(uz)/deg" \
     run.mcpl.gz

   # Times of neutrons below 100 keV (log y axis):
   mcpltool -H "time/ms;logy" run.mcpl.gz \
     -e "pdgcode == neutron and ekin < 100keV"

   # Spectra of two files in one plot, in the terminal:
   mcpltool -t -H "ekin/MeV;logx" \
     before.mcpl.gz after.mcpl.gz

   # Distribution of the particle weights:
   mcpltool -H "weight;unweighted;logy" run.mcpl.gz

   # Spectra for particles with x > 0 and x < 0:
   mcpltool -H "ekin/MeV;logx;display_by=x > 0cm" run.mcpl.gz

   # Positions after a rotation, of the plot only:
   mcpltool -H "x/cm : y/cm;display_edit=rotate_z(45deg)" run.mcpl.gz

   # Statistics and spectrum (in a PDF file) of gammas above 1 keV:
   mcpltool -S -e "pdgcode == gamma and ekin > 1keV" \
     run.mcpl.gz
   mcpltool -H "ekin;logx;logy" -o gammas.pdf run.mcpl.gz \
     -e "pdgcode == gamma and ekin > 1keV"

   # The neutrons with wavelength > 4 Aa among the first 20 particles:
   mcpltool -l20 run.mcpl.gz \
     -e "pdgcode == neutron and wavelength > 4Aa"

   # New file with neutrons within 5 cm of z axis:
   mcpltool -x run.mcpl.gz out.mcpl.gz \
     -e "pdgcode == neutron and hypot(x,y) < 5cm"

   # New file with every tenth particle:
   mcpltool -x -e "mod(fileidx,10) == 0" \
     run.mcpl.gz out.mcpl.gz

   # Move particles 2 m back and delay by 1.5 ms:
   mcpltool -x run.mcpl.gz out.mcpl.gz \
     -e "z -= 2m; time += 1.5ms"

   # Only neutrons, made monochromatic:
   mcpltool -x run.mcpl.gz out.mcpl.gz \
     -e "pdgcode == neutron; wavelength = 1.8Aa"

   # Place particles 2 m from origin along direction:
   mcpltool -x run.mcpl.gz out.mcpl.gz \
     -e "pos = 2m*dir"

.. _usage_expressions-from-python:

From Python
-----------

When reading or writing files, edits can be given directly to ``MCPLFile``
and ``MCPLOutFile`` with the ``edit`` argument. When reading, the blocks of
particles (and single particles) then only contain the kept particles, with
their changes. When writing, the edit is applied to all the particles added:

.. code:: python

   import mcpl
   fin = mcpl.MCPLFile(
       "input.mcpl.gz",
       edit = "pdgcode == neutron and ekin < 25meV; z += 1m" )
   fout = mcpl.MCPLOutFile( "output.mcpl.gz" )
   with fin, fout:
       fout.transfer_metadata( fin )
       for block in fin.particle_blocks:
           fout.add_particles( block )

Here, the particles are copied exactly, except for the edited ``z``
coordinates. Few particles kept from several blocks in the file are merged
into blocks of about the usual size (``blocklength``). The particles keep
their positions in the file (``fileidx`` of particles and of blocks), and
``nparticles`` is ``None``, as the number of particles kept is only known after
reading them.

The same expressions are also used by the classes ``ParticleEdit`` and
``ParticleValue`` in the ``mcpl`` module, which are applied to blocks of
particles:

.. code:: python

   import mcpl
   edit = mcpl.ParticleEdit(
       "pdgcode == neutron and ekin < 25meV; z += 1m" )
   val = mcpl.ParticleValue( "ekin/meV" )
   fin = mcpl.MCPLFile( "input.mcpl.gz" )
   fout = mcpl.MCPLOutFile( "output2.mcpl.gz" )
   with fin, fout:
       fout.transfer_metadata( fin )
       for block in fin.particle_blocks:
           edited = edit( block )
           print( val( edited ) )  # energies in meV
           fout.add_particles( edited )

The ``expression`` of these objects is in a canonical form, which is the same
for all ways of writing it which are recognised as the same (both
``"pdgcode == 2112"`` and ``"(pdgcode==neutron)"`` give
``"pdgcode==neutron"``), while ``expression_original`` is the expression as
given.

Histograms are made with ``mcpl.histogram``, from the same histogram strings
as ``mcpltool -H``. The results can be read (but not changed), and plotted:

.. code:: python

   import mcpl
   h = mcpl.histogram( "input.mcpl.gz",
                       "ekin/eV;logx;lethargy;bins=50",
                       edit = "pdgcode == neutron" )
   print( h.edges, h.contents )
   h.plot()  # or h.plot( "spectrum.pdf" )

The results are a ``Hist1D`` (one expression), ``HistDiscrete`` (one
expression with the option ``bar``), ``Hist2D`` (two expressions), or
``PointSet3D`` (three expressions). Their values are in the units the
expressions give (eV for ``ekin/eV``), and else in those of MCPL. Plots are
shown in a window with matplotlib (an error says so when that is not
possible, e.g. without a display), or saved in the format given by the
extension of the file name: ``.pdf``, ``.png``, or ``.svg`` (with
matplotlib), or ``.txt`` (drawn as text).
