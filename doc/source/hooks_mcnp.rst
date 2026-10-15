************************
MCPL converters for MCNP
************************

The MCNP-MCPL interface currently supports MCNPX, MCNP5 and MCNP6 and exploits
the existing MCNP capability to stop and subsequently restart simulations at a
user-defined set of surfaces through the Surface Source Write/Read (SSW/SSR)
functionality, based on intermediate files. We refer to such files as "SSW
files", although different names are occasionally used (e.g. "RSSA files"). The
MCNP-MCPL interface is thus implemented as two standalone commandline
converters: ``ssw2mcpl`` and ``mcpl2ssw``. A detailed description of the
commands, as well as references to the relevant MCNP manuals in which it is
described how to enable the SSW functionality in a given MCNP *input deck*, is
given in `the MCPL paper (section
3.2) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.3.2>`__ and
the present page will merely provide a few typical usage examples.

Note that the ``ssw2mcpl`` and ``mcpl2ssw`` are provided as part of the
``mcpl-extra`` package, so if the commands are missing you should double-check
that you have :doc:`installed the mcpl-extra package <get>` as well as
``mcpl`` itself.

.. _hooks_mcnp-examples:

Examples
--------

A few examples and instructions of how to use ``ssw2mcpl`` and ``mcpl2ssw`` are
provided in the following.

.. _hooks_mcnp-converting-an-ssw-file-to-mcpl:

Converting an SSW file to MCPL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Simply providing the ``ssw2mcpl`` command with the name of an existing SSW file
and the desired name of the MCPL file to be created, is enough to trigger the
conversion:

.. code:: shell

   ssw2mcpl sswfile.w newfile.mcpl

::

   ssw_open_file: Opened file "sswfile.w":
   ssw_open_file:    File layout detected : MCNPX
   ssw_open_file:    Code ID fields : "mcnpx" / "2.7.0"
   ssw_open_file:    Title field : "Example to write mcpl from mcnp5,mcnp6 and mcnpx"
   ssw_open_file:    Source statistics (histories):        1000
   ssw_open_file:    Particles in file            :        2000
   ssw_open_file:    Number of surfaces           :           2
   ssw_open_file:    Histories at surfaces        :        1000
   MCPL: Compressing file newfile.mcpl
   MCPL: Compressed file into newfile.mcpl.gz
   Created newfile.mcpl.gz

However, it is possible to add more than the minimal amount of information into
the output file. First of all, the ``-d`` flag can be used to enable
double-precision rather than single-precision storage of floating point
numbers. Next, the ``-s`` flag will cause the MCNP surface ID's to be embedded
in the MCPL userflags fields, and finally specifying
``-c <path_to_input_deck>`` will cause the MCNP input deck used to generate the
SSW file in question to be embedded into the MCPL header (can later be
retrieved with ``mcpltool -bmcnp_input_deck newfile.mcpl``). In particular, it
is highly recommended to embed the input_deck with ``-c`` for later reference,
and the ``-s`` might be essential if the file is intended to be converted back
for usage in an MCNP simulation with compatible surface ID's. Thus, enabling as
much information as possible in the MCPL file would happen with:

.. code:: shell

   ssw2mcpl -d -s -c input_deck \
     sswfile.w newfile.mcpl

Inspecting the resulting ``newfile.mcpl.gz`` with ``mcpltool`` might give an
output like this (admittedly the SSW file was not from a very interesting
simulation):

.. code:: shell

   mcpltool newfile.mcpl.gz

::

   Opened MCPL file newfile.mcpl.gz:

     Basic info
       Format             : MCPL-3
       No. of particles   : 2000
       Header storage     : 1095 bytes
       Data storage       : 144000 bytes

     Custom meta data
       Source             : "MCNPX"
       Number of comments : 4
             -> comment 0 : "SSW file from MCNPX converted with ssw2mcpl"
             -> comment 1 : "SSW metadata: [kods='mcnpx', vers='2.7.0', title='Example to write mcpl from mcnp5,mcnp6 and mcnpx']"
             -> comment 2 : "The userflags in this file are the surface IDs found in the SSW file"
             -> comment 3 : "stat:sum:ssw_np1:                    1000"
       Number of blobs    : 1
             -> 747 bytes of data with key "mcnp_input_deck"

     Particle data format
       User flags         : yes
       Polarisation info  : no
       Fixed part. type   : no
       Fixed part. weight : no
       FP precision       : double
       Endianness         : little
       Storage            : 72 bytes/particle

   index     pdgcode   ekin[MeV]       x[cm]       y[cm]       z[cm]          ux          uy          uz    time[ms]      weight  userflags
       0        2112         250        1050           0           0           1           0           0  5.7379e-05           1 0x00000004
       1        2112         250        1500           0           0           1           0           0  8.1853e-05           1 0x00000005
       2        2112         250        1050           0           0           1           0           0  5.7379e-05           1 0x00000004
       3        2112         250        1500           0           0           1           0           0  8.1853e-05           1 0x00000005
       4        2112         250        1050           0           0           1           0           0  5.7379e-05           1 0x00000004
       5        2112         250        1500           0           0           1           0           0  8.1853e-05           1 0x00000005
       6        2112         250        1050           0           0           1           0           0  5.7379e-05           1 0x00000004
       7        2112         250        1500           0           0           1           0           0  8.1853e-05           1 0x00000005
       8        2112         250        1050           0           0           1           0           0  5.7379e-05           1 0x00000004
       9        2112         250        1500           0           0           1           0           0  8.1853e-05           1 0x00000005

.. _hooks_mcnp-converting-an-mcpl-file-to-ssw:

Converting an MCPL file to SSW
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Usage of the ``mcpl2ssw`` command to convert an MCPL file into the SSW format
is slightly more involved than the reverse conversion: in addition to an input
MCPL file, the user must also supply a reference SSW file in a format suitable
for the MCNP setup in which the resulting SSW file is subsequently intended to
be used as input. This added complexity is necessary since different MCNP
flavours have different SSW format, but also because the SSW file actually
contains details about the simulation geometry used in a particular setup. It
doesn't matter how many particles are stored in the reference SSW file, it can
in principle be very small. Additionally, ``mcpl2ssw`` needs to assign MCNP
surface ID's to all particles. This can be set globally with the ``-s`` flag,
or else ``mcpl2ssw`` will try to use the contents of the MCPL userflags field
as the surface ID's.

Assuming ``refsswfile.w`` is an SSW file in a format compatible with the target
setup, the MCPL file ``myfile.mcpl.gz`` can be converted into a compatible SSW
file, newfile.w, with the following command:

.. code:: shell

   mcpl2ssw myfile.mcpl.gz refsswfile.w newfile.w

::

   Opened MCPL file produced with "MCNPX" (contains 2000 particles)
   Opening reference SSW file:
   ssw_open_file: Opened file "refsswfile.w":
   ssw_open_file:    File layout detected : MCNP6
   ssw_open_file:    Code ID fields : "mcnp" / "6"
   ssw_open_file:    Title field : "Example to write mcpl from mcnp5,mcnp6 and mcnpx"
   ssw_open_file:    Source statistics (histories):        1000
   ssw_open_file:    Particles in file            :        2000
   ssw_open_file:    Number of surfaces           :           2
   ssw_open_file:    Histories at surfaces        :        1000
   Creating (or overwriting) output SSW file.
   Initiating particle conversion loop.
   Ending particle conversion loop.
   Created newfile.w with 2000 particles (nrss) and 2000 histories (np1).

Note that here ``refsswfile.w`` is associated with MCNP6 while
``myfile.mcpl.gz`` was created with ``ssw2mcpl`` from an MCNPX file, but of
course MCPL files from non-MCNP simulations can be used as well - assuming the
surface ID's can be specified globally or in the userflags field. The reason
the above example worked was that ``myfile.mcpl.gz`` had been created from with
the ``-s`` flag to ``ssw2mcpl`` (the user should of course make sure that the
surface ID's in the two setups were compatible).

Here is another example, in which the MCPL file originates in a Geant4
simulation, and the surface ID is set globally to 4 (again, it is the users
responsibility that this makes sense):

.. code:: shell

   mcpl2ssw -s4 g4output.mcpl refsswfile.w newfile.w

::

   Opened MCPL file produced with "G4MCPLWriter [G4MCPLWriter]" (contains 1006 particles)
   Opening reference SSW file:
   ssw_open_file: Opened file "refsswfile.w":
   ssw_open_file:    File layout detected : MCNP6
   ssw_open_file:    Code ID fields : "mcnp" / "6"
   ssw_open_file:    Title field : "Example to write mcpl from mcnp5,mcnp6 and mcnpx"
   ssw_open_file:    Source statistics (histories):        1000
   ssw_open_file:    Particles in file            :        2000
   ssw_open_file:    Number of surfaces           :           2
   ssw_open_file:    Histories at surfaces        :        1000
   Creating (or overwriting) output SSW file.
   Initiating particle conversion loop.
   Ending particle conversion loop.
   Created newfile.w with 1006 particles (nrss) and 1006 histories (np1).

.. _hooks_mcnp-get-full-usage-instructions:

Get full usage instructions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full usage instructions are obtainable with the ``--help`` flag:

.. code:: shell

   ssw2mcpl --help

::

   Usage:

     ssw2mcpl [options] input.ssw [output.mcpl]

   Converts the Monte Carlo particles in the input.ssw file (MCNP Surface
   Source Write format) to MCPL format and stores in the designated output
   file (defaults to "output.mcpl").

   Options:

     -h, --help   : Show this usage information.
     -d, --double : Enable double-precision storage of floating point values.
     -s, --surf   : Store SSW surface IDs in the MCPL userflags.
     -n, --nogzip : Do not attempt to gzip output file.
     -c FILE      : Embed entire configuration FILE (the input deck)
                    used to produce input.ssw in the MCPL header.

and

.. code:: shell

   mcpl2ssw --help

::

   Usage:

     mcpl2ssw [options] <input.mcpl> <reference.ssw> [output.ssw]

   Converts the Monte Carlo particles in the input MCPL file to SSW format
   (MCNP Surface Source Write) and stores the result in the designated output
   file (defaults to "output.ssw").

   In order to do so and get the details of the SSW format correct, the user
   must also provide a reference SSW file from the same approximate setup
   (MCNP version, input deck...) where the new SSW file is to be used. The
   reference SSW file can of course be very small, as only the file header is
   important (the new file essentially gets a copy of the header found in the
   reference file, except for certain fields related to number of particles
   whose values are changed).

   Finally, one must pay attention to the Surface ID assigned to the
   particles in the resulting SSW file: Either the user specifies a global
   one with -s<ID>, or it is assumed that the MCPL userflags field in the
   input file is actually intended to become the Surface ID. Note that not
   all MCPL files have userflag fields and that valid Surface IDs are
   integers in the range 1-999999.

   Options:

     -h, --help   : Show this usage information.
     -s<ID>       : All particles in the SSW file will get this surface ID.
     -l<LIMIT>    : Limit the number of particles transferred to the SSW file
                    (defaults to 2147483647, the maximal SSW capacity).
