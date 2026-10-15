*******************
Using MCPL from C++
*******************

The header file
`mcplcpp.h <https://github.com/mctools/mcpl/blob/main/mcpl_core/include/mcplcpp.h>`__
provides a C++ interface to MCPL. It is installed along with ``mcpl.h``, and
needs C++17 but no additional library: like the C API, it is used by linking
with the MCPL library (see :doc:`Using MCPL from C or C++ <usage_c>` for
how to do that with CMake). Everything is in the namespace ``mcpl``, and the
interface offers the same functionality as the :doc:`C API <usage_c>`,
with the usual benefits of C++: errors are reported as exceptions, files are
closed automatically, and particles and their userdata are accessed through
type-safe objects. This page introduces the interface with examples, and all
classes and functions are described in the :doc:`C++ API
reference <cpp_api>`. A complete example is in
`example_cppmcpl.cc <https://github.com/mctools/mcpl/blob/main/examples/example_cppmcpl.cc>`__.

As in the C API, the units are MeV (``ekin``), cm (positions) and milliseconds
(``time``), and particle types are given by their `PDG
codes <https://pdg.lbl.gov/2024/reviews/rpp2024-rev-monte-carlo-numbering.pdf>`__
(2112=neutron, 22=gamma, etc.).

.. _usage_cpp-reading-files:

Reading files
-------------

Files are read with ``mcpl::MCPLFile``, which gives access to the header data
of the file and to the particles, for instance with range-based for loops:

.. code:: cpp

   #include "mcplcpp.h"
   #include <iostream>

   void example_read()
   {
     mcpl::MCPLFile f("myfile.mcpl");
     std::cout << f.nparticles()
               << " particles" << std::endl;
     for ( auto c : f.comments() )
       std::cout << "comment: " << c << std::endl;
     for ( auto p : f ) {
       if ( p.pdgcode() == 2112 && p.ekin() < 0.1 )
         std::cout << p.x() << " " << p.weight()
                   << std::endl;
     }
   }

The particles (``mcpl::Particle``) are lightweight views of the particle data
in the file object, which are only valid until the next particle is read.
Likewise, strings and other header data are views which are valid as long as
the file is open. Particles can also be read one at a time with ``read()``,
which gives an empty particle at the end of the file:

.. code:: cpp

   while ( auto p = f.read() ) {
     // use p
   }

Files can also be dumped, like with ``mcpltool``, with ``f.dump()`` or on a
stream with ``f.dump(std::cout)``.

.. _usage_cpp-writing-files:

Writing files
-------------

Files are written with ``mcpl::MCPLOutFile``. The header data and options are
set first, and particles are then added with the particle object of the file,
whose values are kept after adding the particle (so only the values which
change need to be set):

.. code:: cpp

   #include "mcplcpp.h"

   void example_write()
   {
     mcpl::MCPLOutFile f("myfile.mcpl");
     f.set_srcname("my program");
     f.add_comment("Some neutrons");
     auto p = f.new_particle();
     p.set_pdgcode(2112);
     p.set_weight(1.0);
     for ( int i = 0; i < 1000; ++i ) {
       p.set_ekin(0.001*i);
       p.set_position(0.0, 0.0, 0.1*i);
       p.set_direction(0.0, 0.0, 1.0);
       f.add(p);
     }
     f.close();
   }

Files are only finished by ``close()`` (or ``close_and_gzip()``). If an
``mcpl::MCPLOutFile`` is destroyed without being closed, for instance because
an exception was thrown while writing the file, the file is left unfinished.
Such files can often be recovered with ``mcpl::repair`` (or
``mcpltool --repair``).

Particles read from another file can be transferred exactly, which avoids any
loss of precision when filtering files:

.. code:: cpp

   mcpl::MCPLFile in("input.mcpl");
   mcpl::MCPLOutFile out("output.mcpl");
   out.transfer_metadata(in);
   for ( auto p : in )
     if ( p.ekin() < 0.1 )
       out.transfer_last_read_particle(in);
   out.close();

.. _usage_cpp-userdata:

Userdata
--------

Particles can carry custom data, described by a layout of named fields in the
file header (see the :ref:`format
description <format-mcpl-4-per-particle-userdata>`). In C++, fields
are accessed through ``mcpl::UserdataField`` objects, whose type is checked
once, when they are created, which makes their use efficient. When writing
files, fields are added one at a time, and their values are set with
``set_userdata``:

.. code:: cpp

   mcpl::MCPLOutFile f("myfile.mcpl");
   auto temp = f.add_userdata_field<float>("temp");
   auto dir = f.add_userdata_field<float,3>("dir");
   auto p = f.new_particle();
   //... set the other particle values ...
   p.set_userdata(temp, 293.15f);
   p.set_userdata(dir, {0.0f, 0.6f, 0.8f});
   f.add(p);

When reading files, the field objects are obtained from the file, and give the
values when called with particles:

.. code:: cpp

   mcpl::MCPLFile f("myfile.mcpl");
   auto temp = f.userdata_field<float>("temp");
   auto dir = f.userdata_field<float,3>("dir");
   for ( auto p : f ) {
     float t = temp(p);
     std::array<float,3> d = dir(p);
     float dz = dir(p,2);//(single element)
   }

.. _usage_cpp-errors:

Errors
------

All errors are reported as exceptions: ``mcpl::Error`` (derived from
``std::runtime_error``) for invalid files or arguments, the derived
``mcpl::IOError`` for failed I/O operations, and ``std::bad_alloc`` when memory
allocation fails:

.. code:: cpp

   try {
     mcpl::MCPLFile f("myfile.mcpl");
     // ...
   } catch ( const mcpl::Error& e ) {
     std::cout << "Error: " << e.what() << std::endl;
   }

.. _usage_cpp-operations-on-files:

Operations on files
-------------------

Files can be merged, repaired and compressed with functions like
``mcpl::merge_files``, ``mcpl::repair`` and ``mcpl::gzip_file``. Lists of files
can be given as containers (e.g. ``std::vector``) or as braced lists:

.. code:: cpp

   auto m = mcpl::merge_files("all.mcpl", {"a.mcpl", "b.mcpl"});
   m.close();

.. _usage_cpp-filenames:

Filenames
---------

Filenames can be given as ``std::filesystem::path`` objects, which work with
all names on all platforms, or as strings (``std::string``,
``std::string_view`` or C strings), which are interpreted as UTF-8 like
elsewhere in MCPL.

.. _usage_cpp-messages:

Messages
--------

MCPL prints some messages (e.g. warnings about files which were not properly
closed) to standard output. They can be passed to any function instead:

.. code:: cpp

   mcpl::set_print_handler( []( const char * msg )
                            { mylogger << msg; } );
