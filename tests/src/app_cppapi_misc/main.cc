
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

//Tests of the C++ interface (mcplcpp.h): operations on files, dumping files,
//print handlers and exceptions.

#include "mcpltest_cpputils.hh"
#include <algorithm>
#include <array>
#include <list>

using mcpltest::require;
using mcpltest::expect_throw;
using mcpltest::expect_ok;

static_assert( std::is_base_of_v<std::runtime_error,mcpl::Error> );
static_assert( std::is_base_of_v<mcpl::Error,mcpl::IOError> );

namespace {

  //File with n particles (x values starting at x0), optionally with userdata
  //and in double precision:
  void create_file( const std::string& filename, int n, int x0,
                    bool userdata = false, bool doubleprec = false )
  {
    mcpl::MCPLOutFile f(filename);
    f.set_srcname("cppapi_misc");
    f.add_comment("a comment");
    f.add_stat_sum("nevents",10.0*n);
    if ( doubleprec )
      f.enable_doubleprec();
    mcpl::UserdataField<std::int32_t> id;
    if ( userdata )
      id = f.add_userdata_field<std::int32_t>("id");
    auto p = f.new_particle();
    p.set_uz(1.0);
    for ( int i = 0; i < n; ++i ) {
      p.set_x(x0+i);
      p.set_ekin(0.001*(x0+i));
      p.set_pdgcode( i % 2 ? 22 : 2112 );
      p.set_weight(1.0);
      if ( userdata )
        p.set_userdata(id,100*(x0+i));
      f.add(p);
    }
    f.close();
  }

  //Summary of a file:
  void show( const std::string& filename )
  {
    mcpltest::CollectMessages msgs;
    mcpl::MCPLFile f(filename);
    std::cout << "  " << filename << ": nparticles=" << f.nparticles()
              << " doubleprec=" << f.has_doubleprec()
              << " layout=\"" << f.userdata_layout() << "\""
              << " srcname=\"" << f.srcname().substr(0,15) << "\""
              << " nevents=";
    if ( f.has_stat_sum("nevents") ) {
      auto v = f.stat_sum("nevents");
      std::cout << ( v ? std::to_string(*v) : "n/a" );
    } else {
      std::cout << "none";
    }
    std::cout << " x:";
    for ( auto p : f )
      std::cout << " " << p.x();
    std::cout << std::endl;
    if ( !msgs.str().empty() )
      std::cout << "  (messages: " << msgs.str() << ")" << std::endl;
  }

  void test_merging()
  {
    std::cout << "\n==> Merging files:" << std::endl;
    create_file("a.mcpl",2,1);
    create_file("b.mcpl",3,11);
    create_file("c.mcpl",1,21);
    create_file("dp.mcpl",2,31,false,true);
    create_file("ud.mcpl",2,41,true);
    create_file("ud2.mcpl",1,51,true);

    std::cout << "can_merge(a,b)=" << mcpl::can_merge("a.mcpl","b.mcpl")
              << " can_merge(a,dp)=" << mcpl::can_merge("a.mcpl","dp.mcpl")
              << " can_merge(a,ud)=" << mcpl::can_merge("a.mcpl","ud.mcpl")
              << " can_merge(ud,ud2)=" << mcpl::can_merge("ud.mcpl","ud2.mcpl")
              << std::endl;
    expect_throw( "can_merge(a,nosuchfile)",
                  []{ mcpl::can_merge("a.mcpl","nosuchfile.mcpl"); } );

    //Lists of files in various forms:
    {
      auto m = mcpl::merge_files( "m1.mcpl", { "a.mcpl", "b.mcpl" } );
      m.close();
      show("m1.mcpl");
    }
    {
      std::vector<std::string> files = { "a.mcpl", "b.mcpl", "c.mcpl" };
      mcpl::merge_files( "m2.mcpl", files ).close();
      show("m2.mcpl");
    }
    {
      std::vector<std::filesystem::path> files = { "c.mcpl", "a.mcpl" };
      mcpl::merge_files( std::filesystem::path("m3.mcpl"), files ).close();
      show("m3.mcpl");
    }
    {
      std::array<const char*,2> files = { "b.mcpl", "c.mcpl" };
      mcpl::merge_files( std::string("m4.mcpl"), files ).close();
      std::list<std::string_view> files2 = { "a.mcpl" };
      mcpl::merge_files( "m5.mcpl", files2 ).close();
      show("m4.mcpl");
      show("m5.mcpl");
    }
    //More particles can be added to merged files (also with userdata):
    {
      auto m = mcpl::merge_files( "m6.mcpl", { "ud.mcpl", "ud2.mcpl" } );
      std::cout << "merged file with userdata: layout=\""
                << m.userdata_layout() << "\"" << std::endl;
      auto id = m.userdata_field<std::int32_t>("id");
      auto p = m.new_particle();
      p.set_uz(1.0);
      p.set_x(99.0);
      p.set_userdata(id,-1);
      m.add(p);
      expect_throw( "add_userdata_field on merged file",
                    [&]{ m.add_userdata_field<float>("r"); } );
      m.close();
      show("m6.mcpl");
      mcpl::MCPLFile f("m6.mcpl");
      auto idr = f.userdata_field<std::int32_t>("id");
      std::cout << "  ids:";
      for ( auto pp : f )
        std::cout << " " << idr(pp);
      std::cout << std::endl;
    }
    //Merged files which are not closed are left unfinished:
    {
      auto m = mcpl::merge_files( "m7.mcpl", { "a.mcpl", "b.mcpl" } );
    }
    show("m7.mcpl");
    //Errors:
    expect_throw( "merge_files (incompatible files)",
                  []{ mcpl::merge_files( "e1.mcpl", { "a.mcpl", "dp.mcpl" } ); } );
    expect_throw( "merge_files (missing file)",
                  []{ mcpl::merge_files( "e2.mcpl", { "a.mcpl", "nosuch.mcpl" } ); } );
    expect_throw( "merge_files (output exists)",
                  []{ mcpl::merge_files( "m1.mcpl", { "a.mcpl", "b.mcpl" } ); } );
    expect_throw( "merge_files (no files)",
                  []{ mcpl::merge_files( "e3.mcpl", std::vector<std::string>() ); } );
    expect_throw( "merge_files (same file twice)",
                  []{ mcpl::merge_files( "e4.mcpl", { "a.mcpl", "a.mcpl" } ); } );
    require( !mcpltest::file_exists("e1.mcpl")
             && !mcpltest::file_exists("e2.mcpl")
             && !mcpltest::file_exists("e3.mcpl")
             && !mcpltest::file_exists("e4.mcpl"),
             "output files left by failed merges" );

    std::cout << "\n==> Forced merging:" << std::endl;
    {
      mcpltest::CollectMessages msgs;
      mcpl::forcemerge_files( "f1.mcpl", { "a.mcpl", "dp.mcpl", "ud.mcpl" } )
        .close();
      std::vector<std::string> files = { "a.mcpl", "dp.mcpl" };
      mcpl::forcemerge_files( "f2.mcpl", files,
                              mcpl::KeepUserflags::Yes ).close();
      std::cout << "  (" << std::count( msgs.str().begin(), msgs.str().end(),
                                        '\n' ) << " lines of messages)"
                << std::endl;
    }
    show("f1.mcpl");
    show("f2.mcpl");
    expect_throw( "forcemerge_files (missing file)",
                  []{ mcpl::forcemerge_files( "e5.mcpl", { "a.mcpl", "nosuch.mcpl" } ); } );

    std::cout << "\n==> Merging in place:" << std::endl;
    create_file("ip.mcpl",2,1);
    mcpl::merge_inplace( "ip.mcpl", "b.mcpl" );
    show("ip.mcpl");
    expect_throw( "merge_inplace (incompatible)",
                  []{ mcpl::merge_inplace( "ip.mcpl", "dp.mcpl" ); } );
    expect_throw( "merge_inplace (same file)",
                  []{ mcpl::merge_inplace( "ip.mcpl", "ip.mcpl" ); } );
    expect_throw( "merge_inplace (missing file)",
                  []{ mcpl::merge_inplace( "ip.mcpl", "nosuch.mcpl" ); } );
    show("ip.mcpl");

    for ( const char * fn : { "a.mcpl", "b.mcpl", "c.mcpl", "dp.mcpl",
                              "ud.mcpl", "ud2.mcpl", "m1.mcpl", "m2.mcpl",
                              "m3.mcpl", "m4.mcpl", "m5.mcpl", "m6.mcpl",
                              "m7.mcpl", "f1.mcpl", "f2.mcpl", "ip.mcpl" } )
      std::remove(fn);
  }

  void test_repair_gzip()
  {
    std::cout << "\n==> Repairing and compressing:" << std::endl;
    create_file("r.mcpl",3,1);
    expect_throw( "repair (not broken)", []{ mcpl::repair("r.mcpl"); } );
    expect_throw( "repair (missing file)", []{ mcpl::repair("nosuch.mcpl"); } );
    {
      mcpl::MCPLOutFile f("broken.mcpl");
      auto p = f.new_particle();
      p.set_uz(1.0);
      f.add(p);
      f.add(p);
    }
    {
      mcpltest::CollectMessages msgs;
      mcpl::repair("broken.mcpl");
      std::cout << "repair(broken.mcpl): " << msgs.str();
    }
    show("broken.mcpl");
    {
      mcpltest::CollectMessages msgs;
      mcpl::gzip_file("r.mcpl");
      std::cout << "gzip_file(r.mcpl): " << msgs.str();
    }
    require( mcpltest::file_exists("r.mcpl.gz")
             && !mcpltest::file_exists("r.mcpl"), "gzip_file" );
    show("r.mcpl.gz");
    expect_throw( "gzip_file (missing file)",
                  []{ mcpl::gzip_file("nosuch.mcpl"); } );
    expect_throw( "repair (gzipped file)", []{ mcpl::repair("r.mcpl.gz"); } );
    std::remove("r.mcpl.gz");
    std::remove("broken.mcpl");
  }

  void test_dump()
  {
    std::cout << "\n==> Dumping files:" << std::endl;
    create_file("d.mcpl",5,1,true);
    mcpl::MCPLFile f("d.mcpl");
    //To a stream:
    std::ostringstream os;
    f.dump(os);
    std::cout << os.str();
    //Via the print handler (identical output):
    {
      mcpltest::CollectMessages msgs;
      f.dump();
      require( msgs.str() == os.str(), "dump via print handler differs" );
      std::cout << "dump() via the print handler gives the same output"
                << std::endl;
    }
    //Parts and ranges:
    std::ostringstream os2;
    f.dump(os2,mcpl::DumpParts::Particles,1,2);
    std::cout << "dump(Particles,nskip=1,nlimit=2):\n" << os2.str();
    std::ostringstream os3;
    f.dump(os3,mcpl::DumpParts::Header);
    std::cout << "dump(Header) gives " << os3.str().size() << " characters"
              << std::endl;
    //The position is unchanged:
    f.seek(3);
    f.dump(os3,mcpl::DumpParts::Particles);
    std::cout << "position after dump: " << f.current_position()
              << ", next x=" << f.read().x() << std::endl;
    //Invalid parts:
    expect_throw( "dump(DumpParts(7))",
                  [&]{ f.dump(static_cast<mcpl::DumpParts>(7)); } );
    //Exceptions from streams are passed on:
    {
      //A stream buffer which fails after some characters:
      struct LimitedBuf : std::streambuf {
        int remaining = 100;
        int overflow( int c ) override
        {
          if ( remaining-- <= 0 )
            throw std::runtime_error("stream buffer full");
          return c;
        }
      };
      LimitedBuf buf;
      std::ostream limited(&buf);
      limited.exceptions( std::ios::badbit );
      expect_throw( "dump to a stream whose buffer throws",
                    [&]{ f.dump(limited); } );
    }
    f.rewind();
    std::cout << "file still usable after these: read().x()="
              << f.read().x() << std::endl;
    f.close();
    std::remove("d.mcpl");
  }

  void test_print_handlers()
  {
    std::cout << "\n==> Print handlers:" << std::endl;
    create_file("ph.mcpl",2,1);
    std::string collected;
    mcpl::set_print_handler( [&collected]( const char * msg )
                             { collected += "[A]"; collected += msg; } );
    mcpl::gzip_file("ph.mcpl");
    //Replacing the handler:
    std::size_t ncalls = 0;
    mcpl::set_print_handler( [&ncalls]( const char * ) { ++ncalls; } );
    mcpl::MCPLFile("ph.mcpl.gz").dump();
    std::cout << "first handler got: " << collected;
    std::cout << "second handler was called " << ( ncalls > 10 ? "many" : "few" )
              << " times" << std::endl;
    //Empty functions and nullptr restore the default (printing to stdout):
    mcpl::set_print_handler( std::function<void(const char*)>() );
    std::cout << std::flush;
    mcpl::MCPLFile("ph.mcpl.gz").dump(mcpl::DumpParts::Particles,0,1);
    mcpl::set_print_handler( []( const char * ) {} );
    mcpl::MCPLFile("ph.mcpl.gz").dump();
    mcpl::set_print_handler( nullptr );
    std::cout << std::flush;
    mcpl::MCPLFile("ph.mcpl.gz").dump(mcpl::DumpParts::Particles,1,1);
    //Handlers set with the C API are replaced, and replace C++ handlers:
    mcpl_set_print_handler( []( const char * ) {} );
    collected.clear();
    mcpl::set_print_handler( [&collected]( const char * msg )
                             { collected += msg; } );
    mcpl::MCPLFile("ph.mcpl.gz").dump(mcpl::DumpParts::Particles,0,1);
    mcpl_set_print_handler( nullptr );
    std::cout << "C++ handler after C handler got "
              << ( collected.empty() ? "nothing" : "the output" ) << std::endl;
    std::remove("ph.mcpl.gz");
  }

  void test_exceptions()
  {
    std::cout << "\n==> Exceptions:" << std::endl;
    //Mapping of error codes:
    for ( int code : { MCPL_ERROR_RUNTIME, MCPL_ERROR_IO, MCPL_ERROR_MEMORY } ) {
      mcpl_errstate_t es;
      es.code = code;
      es.reserved = 0;
      std::snprintf( es.msg, sizeof(es.msg), "message for code %i", code );
      expect_throw( "error state with code " + std::to_string(code),
                    [&]{ mcpl::detail::throw_error(es); } );
    }
    //Catching as base classes:
    try {
      mcpl::MCPLFile f("nosuchfile.mcpl");
    } catch ( const std::runtime_error& e ) {
      std::cout << "caught as std::runtime_error: " << e.what() << std::endl;
    }
    try {
      mcpl::MCPLFile f("nosuchfile.mcpl");
    } catch ( const mcpl::Error& e ) {
      std::cout << "caught as mcpl::Error: " << e.what() << std::endl;
    }
    //Exceptions can be created by users:
    mcpl::Error e1("custom");
    mcpl::IOError e2("custom io");
    std::cout << "user exceptions: " << e1.what() << ", " << e2.what()
              << std::endl;
    //Long messages are truncated to 1023 characters:
    {
      mcpl::MCPLOutFile f("long.mcpl");
      std::string longkey( 2000, 'k' );
      try {
        f.add_stat_sum( longkey, 1.0 );
        mcpltest::fail("no exception");
      } catch ( const mcpl::Error& e ) {
        std::cout << "long message: " << std::strlen(e.what())
                  << " characters" << std::endl;
      }
      f.close();
      std::remove("long.mcpl");
    }
  }

}

int main()
{
  test_merging();
  test_repair_gzip();
  test_dump();
  test_print_handlers();
  test_exceptions();
  std::cout << "\nAll ok" << std::endl;
  return 0;
}
