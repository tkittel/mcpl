*************************
MCPL converters for PHITS
*************************

The PHITS-MCPL interface has been tested with
`PHITS <https://phits.jaea.go.jp/>`__ v3.10 and exploits the existing PHITS
capability to stop and subsequently restart simulations via intermediate binary
files, the so-called PHITS dump files. Available since MCPL release v1.3.0, the
PHITS-MCPL interface is thus implemented as two standalone commandline
converters: ``phits2mcpl`` and ``mcpl2phits``.

A detailed description of PHITS dump files can be found in `the PHITS
manual <https://phits.jaea.go.jp/manual/manualE-phits.pdf>`__, but as the dump
files must be configured to include the relevant information, the necessary
PHITS input deck configuration will be discussed below. Afterwards, a few
typical usage examples of ``phits2mcpl`` and ``mcpl2phits`` will be provided.

Note that the ``phits2mcpl`` and ``mcpl2phits`` are provided as part of the
``mcpl-extra`` package, so if the commands are missing you should double-check
that you have :doc:`installed the mcpl-extra package <get>` as well as
``mcpl`` itself.

.. _hooks_phits-configuration-for-phits-input-deck:

Configuration for PHITS input deck
----------------------------------

.. _hooks_phits-producing-binary-dump-files-with-phits:

Producing binary dump files with PHITS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Binary dump files can be produced by PHITS in either of the so-called
``t-cross``, ``t-product`` or ``t-time`` tallies. In all cases, lines like the
following must be added in the relevant tally section:

::

      dump = 13
      1 2 3 4 5 6 7 8 9 10 14 15 16
      file = myout

Which will result in the binary dump files being produced with the name
``myout_dmp`` alongside a dump summary text file named ``myout``. The
configuration with 13 parameters given above includes polarisation
(spin-direction) information. The other supported variant forgoes polarisation
information and thus saves 22% on the resulting file size:

::

      dump = 10
      1 2 3 4 5 6 7 8 9 10
      file = myout

The ``phits2mcpl`` command can accept binary dump files in either of the two
formats above, and is able to distinguish between them automatically. It is not
possible to use any other dump format than those two thus presented.

An example which includes the lines in a t-cross tally, capturing all particles
going from region 1 to region 2 in a particular PHITS setup, is:

::

   [ t-cross ]
      part = all
      mesh = reg
      reg = 1
      r-from r-to area
       1      2   1.0
      dump = 13
      1 2 3 4 5 6 7 8 9 10 14 15 16
      file = myout

If one wishes to be more selective about the particle types captured, one can
change the ``part`` parameter, for example to:
``part = proton neutron photon``.

Refer to the PHITS manual (linked above) for more details.

.. _hooks_phits-reading-binary-dump-files-into-phits:

Reading binary dump files into PHITS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Simply specify the binary dump file in the ``[ Source ]`` section of the file.
Note that the dump configuration must be listed exactly as below in order to
consume the dump files produced by default when using ``mcpl2phits``:

::

   [ Source ]
      s-type =  17
       file = phits.dmp
       dump = 13
       1 2 3 4 5 6 7 8 9 10 14 15 16

If files without polarisation info are produced by ``mcpl2phits --nopol``, then
the format changes slightly:

::

   [ Source ]
      s-type =  17
       file = phits.dmp
       dump = 10
       1 2 3 4 5 6 7 8 9 10

Refer to the PHITS manual (linked above) for more details.

.. _hooks_phits-examples:

Examples
--------

A few examples and instructions of how to use ``phits2mcpl`` and ``mcpl2phits``
are provided in the following.

.. _hooks_phits-converting-a-phits-file-to-mcpl:

Converting a PHITS file to MCPL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Simply providing the ``phits2mcpl`` command with the name of an existing PHITS
file and the desired name of the MCPL file to be created, is enough to trigger
the conversion:

.. code:: shell

   phits2mcpl phits.dmp newfile.mcpl

Which produces an MCPL file (which has been automatically compressed to
``newfile.mcpl.gz``). However, it is possible to add more than the minimal
amount of information into the output file. First of all, the ``-d`` flag can
be used to enable double-precision rather than single-precision storage of
floating point numbers. Next, specifying ``-c <path_to_input_deck>`` will cause
the PHITS input deck used to generate the PHITS file in question to be embedded
into the MCPL header (can later be retrieved with
``mcpltool -bphits_input_deck newfile.mcpl``). Finally, the PHITS dump summary
text file which is created alongside the binary dump file can be likewise
embedded, this time using the ``-s`` flag. It is retrievable via
``mcpltool -bphits_dump_summary_file newfile.mcpl``. It is highly recommended
to embed these two files (input_deck with ``-c`` and dump summary with ``-s``)
for later reference. Thus, enabling as much information as possible in the MCPL
file would happen with:

.. code:: shell

   phits2mcpl -d -c input_deck -s dump_summary \
     phits.dmp newfile.mcpl

Inspecting the resulting ``newfile.mcpl.gz`` with ``mcpltool`` might give an
output like this (admittedly the PHITS file was not from a very interesting
simulation):

.. code:: shell

   mcpltool newfile.mcpl.gz

::

   Opened MCPL file newfile.mcpl.gz:

     Basic info
       Format             : MCPL-3
       No. of particles   : 594
       Header storage     : 6407 bytes
       Data storage       : 54648 bytes

     Custom meta data
       Source             : "PHITS"
       Number of comments : 1
             -> comment 0 : "Converted from PHITS with phits2mcpl"
       Number of blobs    : 2
             -> 4363 bytes of data with key "phits_input_deck"
             -> 1892 bytes of data with key "phits_dump_summary_file"

     Particle data format
       User flags         : no
       Polarisation info  : yes
       Fixed part. type   : no
       Fixed part. weight : no
       FP precision       : double
       Endianness         : little
       Storage            : 92 bytes/particle

   index     pdgcode   ekin[MeV]       x[cm]       y[cm]       z[cm]          ux          uy          uz    time[ms]      weight       pol-x       pol-y       pol-z
       0        2112      1169.8     -2.0164      6.4596          10    -0.10218     0.32878     0.93886  1.1387e-06           1           0           0           0
       1        2112      26.151      3.0151      -4.268          10     0.18738    -0.23192     0.95452  3.1847e-06           1           0           0           0
       2        2112       42.51     -2.9759      14.841          10    -0.12301     0.61496     0.77891  3.1431e-06           1           0           0           0
       3        2112      39.573      34.363     -10.041          10     0.85331    -0.24925     0.45798  5.1811e-06           1           0           0           0
       4        2112      2.9449     -2.3766     -16.498          10   -0.070877     -0.6887     0.72158  1.1026e-05      0.9933           0           0           0
       5        2112      4.2087     -1.2293     -47.557          10   -0.015955    -0.94258     0.33361  1.8554e-05     0.99917           0           0           0
       6        2112      3.3349      5.1802     -11.839          10     0.28463    -0.52526     0.80193  9.4695e-06     0.99974           0           0           0
       7        2112     0.64025     -2.5525      11.771          10    -0.14217     0.56105     0.81548  2.1009e-05     0.99084           0           0           0
       8        2112     0.85396     -48.013      0.3756          10     -0.9519    0.054016      0.3016  4.2223e-05     0.99978           0           0           0
       9        2112     0.87755      2.9275     -11.281          10     0.21556    -0.45874     0.86203  1.7931e-05     0.99229           0           0           0

.. _hooks_phits-converting-an-mcpl-file-to-phits:

Converting an MCPL file to PHITS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Usage of the ``mcpl2phits`` command to convert an MCPL file into the PHITS
format is even simpler - simply supply the name of the input and output files:

.. code:: shell

   mcpl2phits newfile.mcpl.gz phits.dmp

::

   Opened MCPL file produced with "PHITS" (contains 594 particles)
   Creating (or overwriting) output PHITS file.
   Initiating particle conversion loop.
   Ending particle conversion loop.
   Created phits.dmp with 594 particles.

This will likely be all that is needed, but advanced users can of course find a
few more options for fine-tuning via ``mcpl2phits --help``.

.. _hooks_phits-get-full-usage-instructions:

Get full usage instructions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full usage instructions are obtainable with the ``--help`` flag:

.. code:: shell

   phits2mcpl --help

::

   Usage:

     phits2mcpl [options] dumpfile [output.mcpl]

   Converts the Monte Carlo particles in the input dump file (binary PHITS dump
   file format in suitable configuration) to MCPL format and stores in the
   designated output file (defaults to "output.mcpl").

   Options:

     -h, --help   : Show this usage information.
     -d, --double : Enable double-precision storage of floating point values.
     -n, --nogzip : Do not attempt to gzip output file.
     -c FILE      : Embed entire configuration FILE (the input deck)
                    used to produce dumpfile in the MCPL header.
     -s FILE      : Embed into the MCPL header the dump summary text file,
                    which was produced along with the dumpfile itself.

and

.. code:: shell

   mcpl2phits --help

::

   Usage:

     mcpl2phits [options] <input.mcpl> [phits.dmp]

   Converts the Monte Carlo particles in the input MCPL file to binary PHITS
   dump file format and stores the result in the designated output file
   (defaults to "phitsdata_dmp"). The file can be read in PHITS using
   a configuration of (assuming the filename is "phits.dmp"):
        dump = 13
        1 2 3 4 5 6 7 8 9 10 14 15 16
        file = phits.dmp

   Options:

     -h, --help   : Show this usage information.
     -n, --nopol  : Do not write polarisation info (saving ~22% in file size). The
                    PHITS configuration reading the file must then be (assuming the
                    filename is "phits.dmp"):
                                               dump = 10
                                               1 2 3 4 5 6 7 8 9 10
                                               file = phits.dmp
     -f           : Write Fortran records with 64 bit integer markers. Note that
                    the default (32 bit) is almost always the correct choice.
     -l<LIMIT>    : Limit the number of particles transferred to the PHITS file
                    (defaults to 0, meaning no limit).
