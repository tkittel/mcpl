
////////////////////////////////////////////////////////////////////////////////
//                                                                            //
//  This file is part of MCPL (see https://mctools.github.io/mcpl/)           //
//                                                                            //
//  Copyright 2015-2026 MCPL developers.                                      //
//                                                                            //
//  Licensed under the Apache License, Version 2.0 (the "License");           //
//  you may not use this file except in compliance with the License.          //
//  You may obtain a copy of the License at                                   //
//                                                                            //
//      http://www.apache.org/licenses/LICENSE-2.0                            //
//                                                                            //
//  Unless required by applicable law or agreed to in writing, software       //
//  distributed under the License is distributed on an "AS IS" BASIS,         //
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  //
//  See the License for the specific language governing permissions and       //
//  limitations under the License.                                            //
//                                                                            //
////////////////////////////////////////////////////////////////////////////////

// NEEDS: C++17

//Tests of errors while writing data with the C++ interface (mcplcpp.h), like
//with full disks, which are emulated with a limit on the size of files
//(RLIMIT_FSIZE). Since when errors are detected depends on the buffering in
//the C library, this test has no reference log. It is skipped on Windows,
//which has no such limits.

#include "mcpltest_cpputils.hh"

#ifdef _WIN32

int main()
{
  std::cout << "Test skipped on Windows (no limits on file sizes)" << std::endl;
  return 0;
}

#else

#include <csignal>
#include <sys/resource.h>

namespace {

  struct rlimit original_limit;

  void set_filesize_limit( rlim_t nbytes )
  {
    struct rlimit l = original_limit;
    l.rlim_cur = nbytes;
    if ( setrlimit( RLIMIT_FSIZE, &l ) != 0 )
      mcpltest::fail("could not set file size limit");
  }

  void reset_filesize_limit()
  {
    if ( setrlimit( RLIMIT_FSIZE, &original_limit ) != 0 )
      mcpltest::fail("could not reset file size limit");
  }

  std::uint64_t count_particles( const std::string& filename )
  {
    mcpltest::CollectMessages msgs;//(warnings about unfinished files)
    mcpl::MCPLFile f(filename);
    std::uint64_t n = 0;
    for ( auto p : f ) {
      if ( p.x() != static_cast<double>(n) )
        mcpltest::fail("unexpected particle in file left after errors");
      ++n;
    }
    return n;
  }

  void test_add()
  {
    std::cout << "\n==> Errors while adding particles:" << std::endl;
    set_filesize_limit(20000);
    unsigned n = 0;
    {
      mcpl::MCPLOutFile f("cdf1.mcpl");
      auto x = f.add_userdata_field<double>("p");
      auto p = f.new_particle();
      p.set_uz(1.0);
      try {
        for ( ; n < 100000; ++n ) {
          p.set_x(n);
          p.set_userdata(x,n);
          f.add(p);
        }
        mcpltest::fail("no error");
      } catch ( const mcpl::IOError& e ) {
        std::cout << "add -> mcpl::IOError: " << e.what() << std::endl;
      }
      //The file is unusable, and closing it leaves it unfinished (without
      //reporting the error again, as in the C API):
      mcpltest::expect_throw( "add after the error", [&]{ f.add(p); } );
      mcpltest::expect_ok( "close after the error", [&]{ f.close(); } );
      if ( f.is_open() )
        mcpltest::fail("file still open");
    }
    reset_filesize_limit();
    std::uint64_t nrec = count_particles("cdf1.mcpl");
    if ( nrec == 0 || nrec > n )
      mcpltest::fail("unexpected number of particles");
    std::cout << "file left unfinished with the first particles" << std::endl;
    mcpl::set_print_handler( []( const char * ) {} );
    mcpl::repair("cdf1.mcpl");
    mcpl::set_print_handler( nullptr );
    if ( count_particles("cdf1.mcpl") != nrec )
      mcpltest::fail("different number of particles after repair");
    std::remove("cdf1.mcpl");
  }

  void test_close()
  {
    std::cout << "\n==> Errors when closing:" << std::endl;
    //A few particles, which are still buffered when the limit is hit:
    set_filesize_limit(300);
    {
      mcpl::MCPLOutFile f("cdf2.mcpl");
      auto p = f.new_particle();
      p.set_uz(1.0);
      for ( int i = 0; i < 20; ++i ) {
        p.set_x(i);
        f.add(p);
      }
      mcpltest::expect_throw( "close", [&]{ f.close(); } );
    }
    reset_filesize_limit();
    std::uint64_t nrec = count_particles("cdf2.mcpl");
    if ( nrec == 0 || nrec >= 20 )
      mcpltest::fail("unexpected number of particles");
    std::remove("cdf2.mcpl");

    //Destructors do not throw, also in case of errors:
    set_filesize_limit(300);
    {
      mcpl::MCPLOutFile f("cdf3.mcpl");
      auto p = f.new_particle();
      p.set_uz(1.0);
      for ( int i = 0; i < 20; ++i ) {
        p.set_x(i);
        f.add(p);
      }
    }
    std::cout << "destructor of file with buffered particles exceeding the"
              << " limit -> ok" << std::endl;
    reset_filesize_limit();
    nrec = count_particles("cdf3.mcpl");
    if ( nrec == 0 || nrec >= 20 )
      mcpltest::fail("unexpected number of particles");
    std::remove("cdf3.mcpl");

    //Merges (left unfinished):
    for ( int k = 0; k < 2; ++k ) {
      mcpl::MCPLOutFile f( k ? "cdf_in2.mcpl" : "cdf_in1.mcpl" );
      auto p = f.new_particle();
      p.set_uz(1.0);
      for ( int i = 0; i < 2000; ++i ) {
        p.set_x(2000*k+i);
        f.add(p);
      }
      f.close();
    }
    set_filesize_limit(20000);
    try {
      mcpl::merge_files( "cdf_merged.mcpl", { "cdf_in1.mcpl", "cdf_in2.mcpl" } );
      mcpltest::fail("no error");
    } catch ( const mcpl::IOError& e ) {
      std::cout << "merge_files -> mcpl::IOError: " << e.what() << std::endl;
    }
    reset_filesize_limit();
    nrec = count_particles("cdf_merged.mcpl");
    if ( nrec == 0 || nrec >= 4000 )
      mcpltest::fail("unexpected number of particles");
    std::cout << "merged file left unfinished with the first particles"
              << std::endl;
    std::remove("cdf_merged.mcpl");
    std::remove("cdf_in1.mcpl");
    std::remove("cdf_in2.mcpl");
  }

}

int main()
{
  //Writing beyond the limit should give errors, not end the process:
  std::signal(SIGXFSZ,SIG_IGN);
  if ( getrlimit( RLIMIT_FSIZE, &original_limit ) != 0 )
    mcpltest::fail("could not get file size limit");
  test_add();
  test_close();
  std::cout << "\nAll ok" << std::endl;
  return 0;
}

#endif
