************************
Using MCPL from C or C++
************************

It is possible for advanced users to interact directly with MCPL files from C
or C++ code, by including the header file
`mcpl.h <https://github.com/mctools/mcpl/blob/main/mcpl_core/include/mcpl.h.in>`__
and making sure the resulting library or application is linked with the code in
the `mcpl.c <https://github.com/mctools/mcpl/blob/main/mcpl_core/src/mcpl.c>`__
file. This is described in more detail in `the MCPL paper (section
2.2) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.2.2>`__ and
the API is documented in detail in `the MCPL paper (appendix
C) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=section.9>`__.

However, notice that most end-users should not have to write such code. Rather,
they should be able to use pre-existing converters or plugins for their Monte
Carlo applications (c.f. :doc:`hooks <hooks>`).

.. _usage_c-code-examples-for-c-or-c-code:

Code examples for C or C++ code
-------------------------------

For inspiration, please find here a few code examples dealing with MCPL files.
Note that units on the fields of the ``mcpl_particle_t`` struct are MeV (ekin),
cm (position) and milliseconds (time). The particle type is given by the
pdgcode field, which must follow the `PDG code
standard <https://pdg.lbl.gov/2024/reviews/rpp2024-rev-monte-carlo-numbering.pdf>`__
(2112=neutron, 22=gamma, etc.).

Also note that the code below should normally be compiled and linked with
appropriate flags, in order to include the mcpl.h header and link against the
MCPL library. One simple way to do that in CMake based projects is (assuming
MCPL was installed via CMake and your example programme is in a file called
``mymcplapp.c``), to use a small CMakeLists.txt file (in the same dir):

.. code:: cmake

    cmake_minimum_required(VERSION 3.16...3.31)
    project(MyExampleProject LANGUAGES C)
    if( NOT DEFINED "MCPL_DIR" )
      execute_process(
        COMMAND mcpl-config --show cmakedir
        OUTPUT_VARIABLE "MCPL_DIR"
        OUTPUT_STRIP_TRAILING_WHITESPACE
      )
    endif()
    find_package(MCPL 2.0.0 REQUIRED)
    add_executable(mymcplapp
      "${PROJECT_SOURCE_DIR}/mymcplapp.c")
    target_link_libraries( mymcplapp MCPL::MCPL )
    install( TARGETS mymcplapp
             RUNTIME DESTINATION bin )

The call to ``execute_process(..)`` above is only needed in order to be able to
work with MCPL installed from Python wheels (e.g. after a
``pip install mcpl``).

.. _usage_c-reading-mcpl-files:

Reading MCPL files
~~~~~~~~~~~~~~~~~~

.. code:: c

   #include "mcpl.h"
   void example()
   {
     mcpl_file_t f = mcpl_open_file("myfile.mcpl");
     const mcpl_particle_t* p;
     while ( ( p = mcpl_read(f) ) ) {
       /* Particle properties can here be accessed
          through the pointer "p":
          p->pdgcode
          p->position[k] (k=0,1,2)
          p->direction[k] (k=0,1,2)
          p->polarisation[k] (k=0,1,2)
          p->ekin
          p->time
          p->weight
          p->userflags
       */
     }
     mcpl_close_file(f);
   }

.. _usage_c-creating-mcpl-files:

Creating MCPL files
~~~~~~~~~~~~~~~~~~~

.. code:: c

   #include "mcpl.h"
   void example()
   {
     mcpl_outfile_t f;
     f = mcpl_create_outfile("myfile.mcpl");
     mcpl_hdr_set_srcname(f,"MyAppName-1.0");

     /* Tune file options or add custom comments or
        binary data into the header:

        mcpl_enable_userflags(f);
        mcpl_enable_polarisation(f);
        mcpl_enable_doubleprec(f);
        mcpl_enable_universal_pdgcode(f,mypdgcode);
        mcpl_enable_universal_weight(f,myweight);
        mcpl_hdr_add_comment(f,"Some comment.");
        mcpl_hdr_add_data(f,"mydatakey",
                          my_datalength, my_databuf);
     */

     mcpl_particle_t * p;
     p = mcpl_get_empty_particle(f);

     int i;
     for ( i = 0; i < 1000; ++i ) {

       /* The following particle properties must
          always be set here:

          p->position[k] (k=0,1,2)
          p->direction[k] (k=0,1,2)
          p->ekin
          p->time

          These should also be set when required by
          file options:

          p->pdgcode
          p->weight
          p->userflags
          p->polarisation[k] (k=0,1,2)
       */

       mcpl_add_particle(f,p);
     }

     mcpl_close_outfile(f);
   }

.. _usage_c-per-particle-userdata:

Per-particle userdata
~~~~~~~~~~~~~~~~~~~~~

Particles can carry custom data beyond the 32 bit ``userflags``: a fixed number
of bytes per particle, described by a *layout* of named fields which is stored
in the file header (see the :ref:`format
description <format-mcpl-4-per-particle-userdata>`). Files with
userdata use the ``MCPL-4`` format. The example below writes a temperature and
a volume identifier with each particle. The field offsets are looked up once
with ``mcpl_userdata_offset``, which checks the name and type against the
layout, and the values are set with the helper functions for the types in the
layout:

.. code:: c

   #include "mcpl.h"
   void example_write()
   {
     const char * layout;
     layout = "temp:float32,volume:int32";
     mcpl_outfile_t f;
     f = mcpl_create_outfile("myfile.mcpl");
     mcpl_enable_userdata(f,layout);
     mcpl_hdr_add_comment(f,"Userdata: temp is the"
                          " temperature [K], volume"
                          " the volume identifier");
     uint32_t o_temp, o_vol;
     o_temp = mcpl_userdata_offset(layout,"temp",
                                   "float32");
     o_vol = mcpl_userdata_offset(layout,"volume",
                                  "int32");
     uint8_t userdata[8];/* layout size is 8 */
     mcpl_particle_t * p;
     p = mcpl_get_empty_particle(f);
     int i;
     for ( i = 0; i < 1000; ++i ) {
       /* ... set p->position, etc. as usual ... */
       mcpl_userdata_set_float32(userdata,o_temp,
                                 293.15f);
       mcpl_userdata_set_int32(userdata,o_vol,17);
       mcpl_add_particle_with_userdata(f,p,userdata);
     }
     mcpl_close_outfile(f);
   }

In files with userdata, every particle must be added with
``mcpl_add_particle_with_userdata`` (using ``mcpl_add_particle`` is an error),
where ``NULL`` instead of the userdata gives a particle with all userdata bytes
zero. When reading, the layout is found in the header, and the userdata of each
particle is obtained along with the particle:

.. code:: c

   #include "mcpl.h"
   #include <stdio.h>
   void example_read()
   {
     mcpl_file_t f = mcpl_open_file("myfile.mcpl");
     const char * layout;
     layout = mcpl_hdr_userdata_layout(f);
     if ( !layout ) {
       printf("No userdata in file\n");
       return;
     }
     uint32_t o_temp;
     o_temp = mcpl_userdata_offset(layout,"temp",
                                   "float32");
     const mcpl_particle_t* p;
     const uint8_t * userdata;
     while ( 1 ) {
       p = mcpl_read_with_userdata(f,&userdata);
       if ( !p )
         break;
       float temp;
       temp = mcpl_userdata_get_float32(userdata,
                                        o_temp);
       printf("ekin=%g temp=%g\n",p->ekin,
              (double)temp);
     }
     mcpl_close_file(f);
   }

The userdata of the particle from the last ``mcpl_read`` is also available with
``mcpl_last_read_userdata(f)``, and ``mcpl_hdr_userdata_size(f)`` gives the
number of bytes per particle (0 if the file has no userdata). A complete
example is found in the file
`example_userdatamcpl.c <https://github.com/mctools/mcpl/blob/main/examples/example_userdatamcpl.c>`__.

.. _usage_c-extracting-subset-of-particles-from-file:

Extracting subset of particles from file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The example below shows a small C-programme which can be used to extract just
neutrons
(`pdgcode <https://pdg.lbl.gov/2024/reviews/rpp2024-rev-monte-carlo-numbering.pdf>`__
2112) with EKin<0.1MeV from an existing MCPL file into a new one:

.. code:: c


   #include "mcpl.h"
   #include <stdio.h>

   int main(int argc,char**argv) {

     if (argc!=3) {
       printf("Please supply input and output"
              " filenames\n");
       return 1;
     }

     const char * infilename = argv[1];
     const char * outfilename = argv[2];

     // Initialisation, open existing file and
     // create output file handle. Transfer all
     // meta-data from existing file, and add an
     // extra comment in the output file to
     // document the process:

     mcpl_file_t fi = mcpl_open_file(infilename);
     mcpl_outfile_t fo;
     fo = mcpl_create_outfile(outfilename);
     mcpl_transfer_metadata(fi, fo);
     mcpl_hdr_add_comment( fo,
                           "Applied custom filter to"
                           " select neutrons with"
                           " ekin<0.1MeV" );

     //Loop over particles from input, only adding
     //the chosen particles to the output file:

     const mcpl_particle_t* p;
     while ( ( p = mcpl_read(fi) ) ) {
       if ( p->pdgcode == 2112 && p->ekin < 0.1 ) {
         mcpl_transfer_last_read_particle(fi,fo);
         //Note that if we had needed to modify the
         //particle properties, we could have called
         //mcpl_add_particle(fo,p) instead. However,
         //for pure filtering,
         //mcpl_transfer_last_read_particle is better
         //since it avoids a lossy unpacking and
         //repacking of direction vectors.
       }
     }

     //Close up files:
     mcpl_close_outfile(fo);
     mcpl_close_file(fi);
   }

Note that if we would have selected particles based on their position in file
(e.g. transferring just the first 100 particles), we should have added a call
to ``mcpl_hdr_scale_stat_sums( fo, -1.0 )``, in order to avoid misleading
statistics in the output. Refer to :doc:`this page <format_statsum>` for
more information.

.. _usage_c-example-project-with-c-code-and-cmake-configuration:

Example project with C code and CMake configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``mcpl`` repository contains a small but complete example of how to make a
CMake-based project using the MCPL C API. Please find the example in the
`examples/downstream_cmake <https://github.com/mctools/mcpl/tree/HEAD/examples/downstream_cmake>`__
folder.
