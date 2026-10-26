
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

//Tests of writing files with the C++ interface (mcplcpp.h). The files written
//are checked by reading them with the C API.

#include "mcpltest_cpputils.hh"
#include <cmath>
#include <limits>
#include <type_traits>

using mcpltest::require;
using mcpltest::expect_throw;
using mcpltest::expect_ok;

static_assert( !std::is_copy_constructible_v<mcpl::MCPLOutFile> );
static_assert( !std::is_copy_assignable_v<mcpl::MCPLOutFile> );
static_assert( std::is_nothrow_move_constructible_v<mcpl::MCPLOutFile> );
static_assert( std::is_nothrow_move_assignable_v<mcpl::MCPLOutFile> );
static_assert( std::is_trivially_copyable_v<mcpl::OutParticle> );

namespace {

  //Print the file with the C API (header and particles):
  void dump_c( const char * filename )
  {
    std::cout << std::flush;
    mcpl_dump( filename, 0, 0, 0 );
  }

  //Read the file with the C API and check its userdata against the expected
  //bytes for each particle:
  void check_userdata_c( const char * filename,
                         const std::vector<std::vector<std::uint8_t>>& expected )
  {
    mcpl_file_t f = mcpl_open_file(filename);
    std::uint32_t n = mcpl_hdr_userdata_size(f);
    std::size_t i = 0;
    const std::uint8_t * ud;
    while ( mcpl_read_with_userdata(f,&ud) ) {
      require( i < expected.size() && expected[i].size() == n
               && ( n == 0 || std::memcmp(ud,expected[i].data(),n) == 0 ),
               "unexpected userdata in file" );
      ++i;
    }
    require( i == expected.size(), "unexpected number of particles" );
    mcpl_close_file(f);
  }

  void test_basic()
  {
    std::cout << "\n==> Writing a file with all options:" << std::endl;
    {
      mcpl::MCPLOutFile f("basic");//(.mcpl is appended)
      std::cout << "filename() = " << f.filename() << std::endl;
      f.set_srcname("cppapi_write");
      f.add_comment("first comment");
      f.add_comment(std::string("second comment"));
      const std::uint8_t bytes[4] = { 0, 1, 254, 255 };
      f.add_blob("rawbytes",bytes,sizeof(bytes));
      f.add_blob("vector",std::vector<std::uint8_t>{ 7, 8, 9 });
      f.add_blob("text",std::string_view("some text"));
      f.add_blob("empty",nullptr,0);
      f.enable_userflags();
      f.enable_polarisation();
      f.enable_doubleprec();
      f.add_stat_sum("nevents",1000.0);
      f.add_stat_sum("nevents",2000.0);//(updates the value)
      f.reserve_stat_sum("later");
      f.reserve_stat_sum("unset");
      auto p = f.new_particle();
      for ( int i = 0; i < 4; ++i ) {
        p.set_ekin( 0.5 * ( i + 1 ) );
        p.set_position( 1.0 * i, 2.0, 3.0 );
        p.set_direction( 0.0, 0.0, 1.0 );
        p.set_polarisation( 0.1, 0.2, 0.3 );
        p.set_time( 0.25 * i );
        p.set_weight( 1.5 );
        p.set_pdgcode( 2112 );
        p.set_userflags( 0xabcd0000u + static_cast<std::uint32_t>(i) );
        if ( i == 2 ) {
          //Individual setters:
          p.set_x(-1.0); p.set_y(-2.0); p.set_z(-3.0);
          p.set_ux(0.6); p.set_uy(0.0); p.set_uz(0.8);
          p.set_polx(-0.1); p.set_poly(-0.2); p.set_polz(-0.3);
        }
        if ( i == 3 ) {
          //Arrays, and the C struct:
          p.set_position( std::array<double,3>{ 7.0, 8.0, 9.0 } );
          p.set_direction( std::array<double,3>{ 0.0, 1.0, 0.0 } );
          p.set_polarisation( std::array<double,3>{ 1.0, 0.0, 0.0 } );
          p.c_struct().pdgcode = 22;
        }
        //Values can be read back:
        require( p.ekin() == 0.5 * ( i + 1 ) && p.time() == 0.25 * i
                 && p.weight() == 1.5 && p.userflags() == 0xabcd0000u
                                                         + static_cast<std::uint32_t>(i)
                 && p.position()[0] == p.x() && p.direction()[2] == p.uz()
                 && p.polarisation()[1] == p.poly()
                 && p.c_struct().ekin == p.ekin(),
                 "values set differ" );
        f.add(p);
      }
      f.add_stat_sum("later",42.0);
      f.close();
      std::cout << "after close(): is_open()=" << f.is_open() << std::endl;
      f.close();//(does nothing)
    }
    dump_c("basic.mcpl");
    {
      mcpl_file_t c = mcpl_open_file("basic.mcpl");
      std::cout << "stat sums: nevents=" << mcpl_hdr_stat_sum(c,"nevents")
                << " later=" << mcpl_hdr_stat_sum(c,"later")
                << " unset=" << mcpl_hdr_stat_sum(c,"unset") << std::endl;
      std::uint32_t ldata;
      const char * data;
      mcpl_hdr_blob(c,"rawbytes",&ldata,&data);
      require( ldata == 4 && static_cast<unsigned char>(data[3]) == 255,
               "blob contents" );
      mcpl_close_file(c);
    }

    std::cout << "\n==> Universal pdgcode and weight, gzipped:" << std::endl;
    {
      mcpl::MCPLOutFile f(std::string("universal.mcpl"));
      f.enable_universal_pdgcode(22);
      f.enable_universal_weight(0.5);
      auto p = f.new_particle();
      p.set_pdgcode(22);
      p.set_weight(0.5);
      p.set_ekin(1.0);
      p.set_uz(1.0);
      f.add(p);
      p.set_ekin(2.0);
      f.add(p);
      //Other pdgcodes or weights of particles are ignored (as in the C API):
      p.set_pdgcode(2112);
      p.set_weight(1.0);
      p.set_ekin(3.0);
      f.add(p);
      f.close_and_gzip();
    }
    require( mcpltest::file_exists("universal.mcpl.gz")
             && !mcpltest::file_exists("universal.mcpl"), "gzipped file" );
    dump_c("universal.mcpl.gz");
    std::remove("universal.mcpl.gz");
  }

  void test_userdata_fields()
  {
    std::cout << "\n==> Userdata with add_userdata_field:" << std::endl;
    std::vector<std::vector<std::uint8_t>> expected;
    {
      mcpl::MCPLOutFile f("ud1.mcpl");
      auto a = f.add_userdata_field<std::int8_t>("a");
      auto b = f.add_userdata_field<std::uint8_t>("b");
      auto c = f.add_userdata_field<std::int16_t>("c");
      auto d = f.add_userdata_field<std::uint16_t>("d");
      auto e = f.add_userdata_field<std::int32_t>("e");
      auto g = f.add_userdata_field<std::uint32_t>("g");
      auto h = f.add_userdata_field<std::int64_t>("h");
      auto i = f.add_userdata_field<std::uint64_t>("i");
      auto j = f.add_userdata_field<float>("j","K");
      auto k = f.add_userdata_field<double>("k");
      auto dir = f.add_userdata_field<float,3>("dir","cm");
      auto tags = f.add_userdata_field<std::uint8_t,4>("tags");
      auto ids = f.add_userdata_field<std::int64_t,2>("ids");
      std::cout << "layout before adding particles: \"" << f.userdata_layout()
                << "\"" << std::endl;
      std::cout << "offsets: " << a.offset() << " " << b.offset() << " "
                << c.offset() << " " << d.offset() << " " << e.offset() << " "
                << g.offset() << " " << h.offset() << " " << i.offset() << " "
                << j.offset() << " " << k.offset() << " " << dir.offset() << " "
                << tags.offset() << " " << ids.offset() << std::endl;
      //Lookup of fields:
      auto j2 = f.userdata_field<float>("j");
      require( j2.offset() == j.offset(), "lookup of field" );
      expect_throw( "userdata_field<double>(\"j\")",
                    [&]{ f.userdata_field<double>("j"); } );
      expect_throw( "add_userdata_field<float>(\"x\",\"m\")",
                    [&]{ f.add_userdata_field<float>("x","m"); } );
      auto p = f.new_particle();
      std::cout << "after new_particle(): userdata_size()="
                << p.userdata_size() << " layout=\"" << f.userdata_layout()
                << "\"" << std::endl;
      for ( int n = 0; n < 3; ++n ) {
        p.set_ekin(1.0+n);
        p.set_uz(1.0);
        p.set_userdata(a,-n);
        p.set_userdata(b,200+n);
        p.set_userdata(c,-300*n);
        p.set_userdata(d,60000+n);
        p.set_userdata(e,-70000*n);
        p.set_userdata(g,4000000000u+static_cast<unsigned>(n));
        p.set_userdata(h,-(INT64_C(1)<<50)*n);
        p.set_userdata(i,UINT64_MAX-static_cast<unsigned>(n));
        p.set_userdata(j,0.5f*static_cast<float>(n));
        p.set_userdata(k,1e-300*n);
        if ( n == 0 ) {
          p.set_userdata(dir,{0.0f,0.6f,0.8f});//(braced list)
          const std::uint8_t t[4] = { 1, 2, 3, 4 };//(C array)
          p.set_userdata(tags,t);
          p.set_userdata(ids,std::array<std::int64_t,2>{ -1, 1 });
        } else {
          p.set_userdata(dir,2,static_cast<float>(n));//(elements)
          p.set_userdata(tags,0,static_cast<std::uint8_t>(10+n));
          p.set_userdata(ids,1,INT64_C(1)<<(40+n));
        }
        //Values can be read back:
        require( a(p) == -n && b(p) == 200+n && c(p) == -300*n
                 && d(p) == 60000+n && e(p) == -70000*n
                 && g(p) == 4000000000u+static_cast<unsigned>(n)
                 && h(p) == -(INT64_C(1)<<50)*n
                 && i(p) == UINT64_MAX-static_cast<unsigned>(n)
                 && j(p) == 0.5f*static_cast<float>(n) && k(p) == 1e-300*n
                 && dir(p,1) == 0.6f && tags(p)[3] == 4 && ids(p)[0] == -1,
                 "userdata values set differ" );
        expected.emplace_back( p.raw_userdata(),
                               p.raw_userdata() + p.userdata_size() );
        f.add(p);
      }
      //Errors:
      expect_throw( "dir set element 3", [&]{ p.set_userdata(dir,3,1.0f); } );
      expect_throw( "dir(p,3)", [&]{ dir(p,3); } );
      f.close();
    }
    check_userdata_c("ud1.mcpl",expected);
    dump_c("ud1.mcpl");
    {
      //Reading back with the C++ interface:
      mcpl::MCPLFile f("ud1.mcpl");
      auto dir = f.userdata_field<float,3>("dir");
      auto ids = f.userdata_field<std::int64_t,2>("ids");
      auto i = f.userdata_field<std::uint64_t>("i");
      for ( auto p : f ) {
        auto v = dir(p);
        std::cout << "  read back: dir=" << v[0] << "," << v[1] << "," << v[2]
                  << " ids=" << ids(p,0) << "," << ids(p,1)
                  << " i=" << i(p) << std::endl;
      }
    }
    std::remove("ud1.mcpl");

    std::cout << "\n==> Userdata with enable_userdata:" << std::endl;
    {
      mcpl::MCPLOutFile f("ud2.mcpl");
      f.enable_userdata("x:float64,n:uint16[2]");
      std::cout << "layout: \"" << f.userdata_layout() << "\"" << std::endl;
      auto x = f.userdata_field<double>("x");
      auto n = f.userdata_field<std::uint16_t,2>("n");
      expect_throw( "add_userdata_field after enable_userdata",
                    [&]{ f.add_userdata_field<float>("y"); } );
      expect_throw( "userdata_field<float>(\"x\")",
                    [&]{ f.userdata_field<float>("x"); } );
      expect_throw( "userdata_field<std::uint16_t>(\"n\")",
                    [&]{ f.userdata_field<std::uint16_t>("n"); } );
      expect_throw( "enable_userdata again (other layout)",
                    [&]{ f.enable_userdata("y:float64"); } );
      auto p = f.new_particle();
      p.set_userdata(x,3.25);
      p.set_userdata(n,{ std::uint16_t(1), std::uint16_t(2) });
      p.set_ekin(1.0);
      p.set_uz(1.0);
      f.add(p);
      //Adding a particle as a C struct gives zero userdata:
      mcpl_particle_t cp = p.c_struct();
      cp.ekin = 2.0;
      f.add(cp);
      expect_throw( "enable_userdata after adding particles",
                    [&]{ f.enable_userdata("x:float64,n:uint16[2]"); } );
      f.close();
    }
    dump_c("ud2.mcpl");
    std::remove("ud2.mcpl");

    std::cout << "\n==> Fields added but no particles:" << std::endl;
    {
      mcpl::MCPLOutFile f("ud3.mcpl");
      f.add_userdata_field<float>("x");
      f.close();
    }
    dump_c("ud3.mcpl");
    std::remove("ud3.mcpl");
  }

  void test_userdata_errors()
  {
    std::cout << "\n==> Userdata errors:" << std::endl;
    mcpl::MCPLOutFile f("ud_err.mcpl");
    f.add_userdata_field<float>("x");
    expect_throw( "add_userdata_field (duplicate name)",
                  [&]{ f.add_userdata_field<double>("x"); } );
    expect_throw( "add_userdata_field (invalid name)",
                  [&]{ f.add_userdata_field<double>("Bad"); } );
    expect_throw( "add_userdata_field (empty name)",
                  [&]{ f.add_userdata_field<double>(""); } );
    expect_throw( "add_userdata_field (name with colon)",
                  [&]{ f.add_userdata_field<double>("a:b"); } );
    expect_throw( "add_userdata_field (too large)",
                  [&]{ f.add_userdata_field<std::uint8_t,70000>("big"); } );
    std::cout << "layout unchanged by these errors: \"" << f.userdata_layout()
              << "\"" << std::endl;
    expect_throw( "enable_userdata after add_userdata_field",
                  [&]{ f.enable_userdata("y:float32"); } );
    auto y = f.add_userdata_field<float>("y");
    auto p = f.new_particle();
    expect_throw( "add_userdata_field after new_particle",
                  [&]{ f.add_userdata_field<float>("z"); } );
    p.set_userdata(y,1.0f);
    p.set_uz(1.0);
    f.add(p);
    f.close();
    dump_c("ud_err.mcpl");
    std::remove("ud_err.mcpl");

    //Invalid layouts given to enable_userdata:
    mcpl::MCPLOutFile g("ud_err2.mcpl");
    expect_throw( "enable_userdata(\"x:float16\")",
                  [&]{ g.enable_userdata("x:float16"); } );
    expect_throw( "enable_userdata(\"\")", [&]{ g.enable_userdata(""); } );
    expect_throw( "userdata_field<float>(\"x\") (no userdata)",
                  [&]{ g.userdata_field<float>("x"); } );
    //Fields from files with longer userdata:
    mcpl::MCPLOutFile h("ud_err3.mcpl");
    auto big = h.add_userdata_field<double,4>("big");
    auto pg = g.new_particle();
    expect_throw( "set_userdata on particle without userdata",
                  [&]{ pg.set_userdata(big,0,1.0); } );
    expect_throw( "add_userdata_field after new_particle (no userdata)",
                  [&]{ g.add_userdata_field<float>("x"); } );
    g.close();
    h.close();
    std::remove("ud_err2.mcpl");
    std::remove("ud_err3.mcpl");
  }

  void test_errors()
  {
    std::cout << "\n==> Errors:" << std::endl;
    expect_throw( "MCPLOutFile(\"\")", []{ mcpl::MCPLOutFile f(""); } );
    expect_throw( "MCPLOutFile(\"nosuchdir/out.mcpl\")",
                  []{ mcpl::MCPLOutFile f("nosuchdir/out.mcpl"); } );
    mcpl::MCPLOutFile f("errors.mcpl");
    expect_throw( "add_stat_sum(\"x\",-1)",
                  [&]{ f.add_stat_sum("x",-1.0); } );
    expect_throw( "add_stat_sum(\"x\",NaN)",
                  [&]{ f.add_stat_sum("x",std::numeric_limits<double>::quiet_NaN()); } );
    expect_throw( "add_stat_sum(\"x\",inf)",
                  [&]{ f.add_stat_sum("x",std::numeric_limits<double>::infinity()); } );
    expect_throw( "add_stat_sum(\"a:b\",1)",
                  [&]{ f.add_stat_sum("a:b",1.0); } );
    expect_throw( "reserve_stat_sum(\"\")", [&]{ f.reserve_stat_sum(""); } );
    expect_throw( "scale_stat_sums(0)", [&]{ f.scale_stat_sums(0.0); } );
    expect_throw( "enable_universal_pdgcode(0)",
                  [&]{ f.enable_universal_pdgcode(0); } );
    expect_throw( "enable_universal_weight(-1)",
                  [&]{ f.enable_universal_weight(-1.0); } );
    expect_throw( "add_blob (duplicate key)", [&]{
      f.add_blob("k","a"); f.add_blob("k","b");
    } );
    auto p = f.new_particle();
    p.set_ekin(1.0);
    p.set_uz(1.0);
    f.add(p);
    expect_throw( "set_srcname after adding particles",
                  [&]{ f.set_srcname("x"); } );
    expect_throw( "add_comment after adding particles",
                  [&]{ f.add_comment("x"); } );
    expect_throw( "enable_doubleprec after adding particles",
                  [&]{ f.enable_doubleprec(); } );
    p.set_ekin(std::numeric_limits<double>::quiet_NaN());
    expect_throw( "add (NaN energy)", [&]{ f.add(p); } );
    p.set_ekin(2.0);
    p.set_uz(0.0);
    expect_throw( "add (zero direction)", [&]{ f.add(p); } );
    p.set_uz(1.0);
    expect_ok( "add (the file is still usable)", [&]{ f.add(p); } );
    //Particles of other files:
    mcpl::MCPLOutFile g("errors2.mcpl");
    auto pg = g.new_particle();
    pg.set_uz(1.0);
    expect_throw( "add (particle of another file)", [&]{ f.add(pg); } );
    g.close();
    expect_throw( "add (default constructed particle)",
                  [&]{ f.add(mcpl::OutParticle()); } );
    f.close();
    dump_c("errors.mcpl");
    std::remove("errors.mcpl");
    std::remove("errors2.mcpl");
  }

  void test_unfinished()
  {
    std::cout << "\n==> Files not closed are left unfinished:" << std::endl;
    {
      mcpl::MCPLOutFile f("unfinished.mcpl");
      f.add_stat_sum("nevents",10.0);
      auto p = f.new_particle();
      for ( int i = 0; i < 5; ++i ) {
        p.set_ekin(1.0+i);
        p.set_uz(1.0);
        f.add(p);
      }
      //(destructor called here)
    }
    {
      mcpltest::CollectMessages msgs;
      mcpl::MCPLFile f("unfinished.mcpl");
      std::cout << "reading unfinished.mcpl: nparticles=" << f.nparticles()
                << " stat_sum(nevents)="
                << ( f.stat_sum("nevents") ? "available" : "not available" )
                << std::endl;
      std::cout << "  messages: " << msgs.str();
    }
    {
      mcpltest::CollectMessages msgs;
      mcpl::repair("unfinished.mcpl");
      std::cout << "repair: " << msgs.str();
    }
    dump_c("unfinished.mcpl");
    std::remove("unfinished.mcpl");

    //Exceptions while writing:
    try {
      mcpl::MCPLOutFile f("exception.mcpl");
      auto p = f.new_particle();
      p.set_uz(1.0);
      for ( int i = 0; i < 3; ++i ) {
        p.set_ekin(1.0+i);
        f.add(p);
      }
      throw std::runtime_error("some problem");
    } catch ( const std::runtime_error& e ) {
      std::cout << "exception while writing: " << e.what() << std::endl;
    }
    {
      mcpltest::CollectMessages msgs;
      mcpl::MCPLFile f("exception.mcpl");
      std::uint64_t n = 0;
      for ( auto p : f ) {
        (void)p;
        ++n;
      }
      std::cout << "exception.mcpl has " << n << " particles, messages: "
                << msgs.str();
    }
    std::remove("exception.mcpl");

    //Explicitly abandoned, and before the header is written:
    {
      mcpl::MCPLOutFile f("abandoned.mcpl");
      f.set_srcname("abandoned");
      f.abandon();
      std::cout << "after abandon(): is_open()=" << f.is_open() << std::endl;
      f.abandon();//(does nothing)
      expect_throw( "set_srcname after abandon()",
                    [&]{ f.set_srcname("x"); } );
    }
    std::cout << "abandoned.mcpl (header not written) has "
              << mcpltest::file_contents("abandoned.mcpl").size()
              << " bytes" << std::endl;
    expect_throw( "MCPLFile(\"abandoned.mcpl\")",
                  []{ mcpl::MCPLFile f("abandoned.mcpl"); } );
    std::remove("abandoned.mcpl");
  }

  void test_transfers()
  {
    std::cout << "\n==> Transferring metadata and particles:" << std::endl;
    {
      mcpl::MCPLOutFile f("src.mcpl");
      f.set_srcname("source");
      f.add_comment("source comment");
      f.add_blob("key","value");
      f.add_stat_sum("nevents",100.0);
      f.enable_polarisation();
      auto t = f.add_userdata_field<double>("t");
      auto id = f.add_userdata_field<std::uint32_t,2>("id");
      auto p = f.new_particle();
      for ( int i = 0; i < 6; ++i ) {
        p.set_ekin(0.1*(i+1));
        p.set_direction(0.0,0.6,0.8);
        p.set_polarisation(1.0,0.0,0.0);
        p.set_pdgcode( i % 3 ? 2112 : 22 );
        p.set_userdata(t,1000.0+i);
        p.set_userdata(id,{ static_cast<std::uint32_t>(i), 7u });
        f.add(p);
      }
      f.close();
    }
    //Filtering (only neutrons), keeping everything else:
    {
      mcpl::MCPLFile in("src.mcpl");
      mcpl::MCPLOutFile out("filtered.mcpl");
      out.transfer_metadata(in);
      std::cout << "after transfer_metadata: layout=\""
                << out.userdata_layout() << "\"" << std::endl;
      auto t = out.userdata_field<double>("t");
      auto tin = in.userdata_field<double>("t");
      for ( auto p : in ) {
        if ( p.pdgcode() == 2112 ) {
          require( t.offset() == tin.offset(), "offsets differ" );
          out.transfer_last_read_particle(in);
        }
      }
      //Adding a modified particle:
      auto q = out.new_particle();
      q.set_ekin(5.0);
      q.set_uz(1.0);
      q.set_pdgcode(2112);
      q.set_userdata(t,-1.0);
      out.add(q);
      expect_throw( "transfer_metadata after adding particles",
                    [&]{ out.transfer_metadata(in); } );
      out.close();
    }
    dump_c("filtered.mcpl");
    {
      //Errors:
      mcpl::MCPLFile in("src.mcpl");
      mcpl::MCPLOutFile out("transfer_err.mcpl");
      expect_throw( "transfer_last_read_particle before reading",
                    [&]{ out.transfer_last_read_particle(in); } );
      mcpl::MCPLOutFile out2("transfer_err2.mcpl");
      out2.add_userdata_field<float>("other");
      in.read();
      expect_throw( "transfer_metadata (different userdata)",
                    [&]{ out2.transfer_metadata(in); } );
      out.close();
      out2.close();
    }
    std::remove("transfer_err.mcpl");
    std::remove("transfer_err2.mcpl");
    std::remove("src.mcpl");
    std::remove("filtered.mcpl");
  }

  void test_moves()
  {
    std::cout << "\n==> Moving output files:" << std::endl;
    mcpl::MCPLOutFile f("moved.mcpl");
    auto x = f.add_userdata_field<float>("x");
    auto p = f.new_particle();
    p.set_uz(1.0);
    p.set_ekin(1.0);
    p.set_userdata(x,1.0f);
    f.add(p);
    mcpl::MCPLOutFile g( std::move(f) );
    std::cout << "after move construction: f.is_open()=" << f.is_open()
              << " g.is_open()=" << g.is_open() << " g.filename()="
              << g.filename() << std::endl;
    //Particles of the moved file are still valid:
    p.set_ekin(2.0);
    p.set_userdata(x,2.0f);
    g.add(p);
    expect_throw( "f.add(p) (moved from)", [&]{ f.add(p); } );
    expect_throw( "f.filename() (moved from)", [&]{ f.filename(); } );
    expect_throw( "f.set_srcname (moved from)", [&]{ f.set_srcname("x"); } );
    expect_throw( "f.new_particle() (moved from)", [&]{ f.new_particle(); } );
    expect_throw( "f.add_userdata_field (moved from)",
                  [&]{ f.add_userdata_field<float>("y"); } );
    expect_throw( "f.userdata_layout() (moved from)",
                  [&]{ f.userdata_layout(); } );
    f.close();//(does nothing)
    //Move assignment (abandoning the file assigned to):
    mcpl::MCPLOutFile h("other.mcpl");
    h.set_srcname("other");
    h = std::move(g);
    std::cout << "after move assignment: g.is_open()=" << g.is_open()
              << " h.is_open()=" << h.is_open() << std::endl;
    p.set_ekin(3.0);
    p.set_userdata(x,3.0f);
    h.add(p);
    mcpl::MCPLOutFile& href = h;
    h = std::move(href);
    h.close();
    dump_c("moved.mcpl");
    std::cout << "other.mcpl (abandoned before the header was written) has "
              << mcpltest::file_contents("other.mcpl").size() << " bytes"
              << std::endl;
    std::remove("moved.mcpl");
    std::remove("other.mcpl");
    //Output files in containers:
    std::vector<mcpl::MCPLOutFile> files;
    for ( int i = 0; i < 3; ++i )
      files.emplace_back( "vec" + std::to_string(i) + ".mcpl" );
    for ( auto& ff : files ) {
      auto pp = ff.new_particle();
      pp.set_uz(1.0);
      ff.add(pp);
      ff.close();
    }
    for ( int i = 0; i < 3; ++i ) {
      std::string fn = "vec" + std::to_string(i) + ".mcpl";
      mcpl::MCPLFile ff(fn);
      require( ff.nparticles() == 1, "file in vector" );
      ff.close();
      std::remove(fn.c_str());
    }
    std::cout << "output files in a vector: ok" << std::endl;
  }

  void test_misc()
  {
    std::cout << "\n==> Filenames, new_particle and C handles:" << std::endl;
    {
      mcpl::MCPLOutFile f( std::filesystem::path("viapath.mcpl") );
      std::cout << "MCPLOutFile(path).filename() = " << f.filename()
                << std::endl;
      //new_particle() always gives the same particle, reset to zero:
      auto p1 = f.new_particle();
      p1.set_ekin(5.0);
      auto p2 = f.new_particle();
      require( p2.ekin() == 0.0 && p1.ekin() == 0.0
               && &p1.c_struct() == &p2.c_struct(), "new_particle" );
      std::cout << "new_particle() gives the same particle, reset to zero"
                << std::endl;
      //The C API on c_handle():
      mcpl_hdr_add_comment(f.c_handle(),"added with the C API");
      p1.set_uz(1.0);
      f.add(p1);
      mcpl_add_particle(f.c_handle(),&p1.c_struct());
      f.close();
    }
    {
      mcpl::MCPLFile f("viapath.mcpl");
      std::cout << "viapath.mcpl: nparticles=" << f.nparticles()
                << " comment(0)=\"" << f.comment(0) << "\"" << std::endl;
    }
    std::remove("viapath.mcpl");
    {
      mcpl::MCPLOutFile f( std::string_view("viastringview.mcpl") );
      std::cout << "MCPLOutFile(string_view).filename() = " << f.filename()
                << std::endl;
      f.close();
    }
    std::remove("viastringview.mcpl");

    std::cout << "\n==> Scaling stat sums, closing twice:" << std::endl;
    {
      mcpl::MCPLOutFile f("scaled.mcpl");
      f.add_stat_sum("a",10.0);
      f.add_stat_sum("b",3.0);
      f.scale_stat_sums(2.5);
      f.close_and_gzip();
      f.close_and_gzip();//(does nothing)
      f.close();//(does nothing)
      mcpl::MCPLFile r("scaled.mcpl.gz");
      std::cout << "scaled by 2.5: a=" << *r.stat_sum("a") << " b="
                << *r.stat_sum("b") << std::endl;
    }
    std::remove("scaled.mcpl.gz");
    {
      mcpl::MCPLOutFile f("unavailable.mcpl");
      f.add_stat_sum("a",10.0);
      f.scale_stat_sums(-1.0);
      f.close();
      mcpl::MCPLFile r("unavailable.mcpl");
      std::cout << "scaled by -1: a is "
                << ( r.stat_sum("a") ? "available" : "not available" )
                << std::endl;
    }
    std::remove("unavailable.mcpl");

    std::cout << "\n==> Errors when fixing the layout at close:" << std::endl;
    {
      //Particles added with the C API write the header before the fields
      //added with add_userdata_field are given to the C library:
      mcpl::MCPLOutFile f("latelayout.mcpl");
      f.add_userdata_field<float>("x");
      mcpl_particle_t cp;
      std::memset(&cp,0,sizeof(cp));
      cp.direction[2] = 1.0;
      mcpl_add_particle(f.c_handle(),&cp);
      expect_throw( "close (layout can not be given)", [&]{ f.close(); } );
      std::cout << "is_open() = " << f.is_open() << std::endl;
    }
    {
      mcpltest::CollectMessages msgs;
      mcpl::MCPLFile r("latelayout.mcpl");
      std::cout << "latelayout.mcpl (left unfinished): nparticles="
                << r.nparticles() << " layout=\"" << r.userdata_layout()
                << "\"" << std::endl;
    }
    std::remove("latelayout.mcpl");
  }

}

int main()
{
  test_basic();
  test_userdata_fields();
  test_userdata_errors();
  test_errors();
  test_unfinished();
  test_transfers();
  test_moves();
  test_misc();
  std::remove("basic.mcpl");
  std::cout << "\nAll ok" << std::endl;
  return 0;
}
