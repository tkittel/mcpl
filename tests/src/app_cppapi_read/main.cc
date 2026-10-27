
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

//Tests of reading files with the C++ interface (mcplcpp.h). The files are
//written with the C API, and everything read is compared with the C API.

#include "mcpltest_cpputils.hh"
#include <algorithm>
#include <cmath>
#include <type_traits>

using mcpltest::require;
using mcpltest::expect_throw;
using mcpltest::expect_ok;

static_assert( !std::is_copy_constructible_v<mcpl::MCPLFile> );
static_assert( !std::is_copy_assignable_v<mcpl::MCPLFile> );
static_assert( std::is_nothrow_move_constructible_v<mcpl::MCPLFile> );
static_assert( std::is_nothrow_move_assignable_v<mcpl::MCPLFile> );
static_assert( std::is_trivially_copyable_v<mcpl::Particle> );
static_assert( sizeof(mcpl::Particle) <= 3*sizeof(void*) );
static_assert( std::is_same_v< mcpl::UserdataField<float>::value_type, float > );
static_assert( std::is_same_v< mcpl::UserdataField<float,3>::value_type,
                               std::array<float,3> > );

namespace {

  //Layout with all types (and some arrays), in total 75 bytes:
  const char * full_layout = "a:int8,b:uint8,c:int16,d:uint16,e:int32,"
                             "f:uint32,g:int64,h:uint64,i:float32,j:float64,"
                             "k:float32[3],l:uint8[5],m:int64[2]";

  void fill( mcpl_particle_t * p, int i )
  {
    std::memset(p,0,sizeof(*p));
    p->ekin = 0.25 * ( i + 1 );
    p->position[0] = 1.0 + i;
    p->position[1] = -2.0 * i;
    p->position[2] = 0.5;
    p->direction[0] = 0.0;
    p->direction[1] = 0.6;
    p->direction[2] = 0.8;
    p->polarisation[0] = 0.1 * i;
    p->polarisation[1] = 0.2;
    p->polarisation[2] = -0.3;
    p->time = 10.0 * i;
    p->weight = 1.0 + 0.5 * i;
    p->pdgcode = ( i % 2 ) ? 22 : 2112;
    p->userflags = 0x1000u + static_cast<std::uint32_t>(i);
  }

  void fill_userdata( std::uint8_t * ud, int i )
  {
    std::uint32_t o = 0;
    mcpl_userdata_set_int8(ud,o,static_cast<std::int8_t>(-i)); o += 1;
    mcpl_userdata_set_uint8(ud,o,static_cast<std::uint8_t>(200+i)); o += 1;
    mcpl_userdata_set_int16(ud,o,static_cast<std::int16_t>(-1000*i)); o += 2;
    mcpl_userdata_set_uint16(ud,o,static_cast<std::uint16_t>(60000+i)); o += 2;
    mcpl_userdata_set_int32(ud,o,-100000*i); o += 4;
    mcpl_userdata_set_uint32(ud,o,4000000000u+static_cast<std::uint32_t>(i)); o += 4;
    mcpl_userdata_set_int64(ud,o,-(INT64_C(1)<<40)*i); o += 8;
    mcpl_userdata_set_uint64(ud,o,(UINT64_C(1)<<63)+static_cast<std::uint64_t>(i)); o += 8;
    mcpl_userdata_set_float32(ud,o,1.5f*static_cast<float>(i)); o += 4;
    mcpl_userdata_set_float64(ud,o,1e100*i); o += 8;
    for ( int k = 0; k < 3; ++k, o += 4 )
      mcpl_userdata_set_float32(ud,o,static_cast<float>(10*i+k));
    for ( int k = 0; k < 5; ++k, o += 1 )
      mcpl_userdata_set_uint8(ud,o,static_cast<std::uint8_t>(i+k));
    for ( int k = 0; k < 2; ++k, o += 8 )
      mcpl_userdata_set_int64(ud,o,INT64_C(-5)*i-k);
    require( o == 75, "unexpected layout size" );
  }

  //File with everything (written with the C API):
  void create_full_file( const char * filename, int n )
  {
    mcpl_outfile_t f = mcpl_create_outfile(filename);
    mcpl_hdr_set_srcname(f,"cppapi_read");
    mcpl_hdr_add_comment(f,"comment one");
    mcpl_hdr_add_comment(f,"comment two");
    mcpl_hdr_add_stat_sum(f,"nevents",1234.5);
    mcpl_hdr_add_stat_sum(f,"notdone",-1.0);
    const char blob1[5] = { 'a', '\0', 'b', '\xff', 'c' };
    mcpl_hdr_add_data(f,"binary",5,blob1);
    mcpl_hdr_add_data(f,"text",11,"hello world");
    mcpl_hdr_add_data(f,"empty",0,"");
    mcpl_enable_userflags(f);
    mcpl_enable_polarisation(f);
    mcpl_enable_doubleprec(f);
    mcpl_enable_userdata(f,full_layout);
    mcpl_particle_t * p = mcpl_get_empty_particle(f);
    std::uint8_t ud[75];
    for ( int i = 0; i < n; ++i ) {
      fill(p,i);
      fill_userdata(ud,i);
      mcpl_add_particle_with_userdata(f,p,ud);
    }
    mcpl_close_outfile(f);
  }

  //Simple file (single precision, universal pdgcode and weight, no options):
  void create_simple_file( const char * filename, int n )
  {
    mcpl_outfile_t f = mcpl_create_outfile(filename);
    mcpl_enable_universal_pdgcode(f,2112);
    mcpl_enable_universal_weight(f,2.5);
    mcpl_particle_t * p = mcpl_get_empty_particle(f);
    for ( int i = 0; i < n; ++i ) {
      fill(p,i);
      p->pdgcode = 2112;
      p->weight = 2.5;
      mcpl_add_particle(f,p);
    }
    mcpl_close_outfile(f);
  }

  //Path from a UTF-8 encoded string (u8path is deprecated from C++20):
  std::filesystem::path utf8_path( const std::string& s )
  {
#if defined(__cpp_char8_t) && __cpp_char8_t >= 201811L
    return std::filesystem::path( std::u8string( s.begin(), s.end() ) );
#else
    return std::filesystem::u8path( s );
#endif
  }

  bool same_particle( const mcpl_particle_t& a, const mcpl_particle_t& b )
  {
    return std::memcmp(&a,&b,sizeof(a)) == 0;
  }

  void print_particle( const mcpl::Particle& p )
  {
    std::cout << "  particle: ekin=" << p.ekin()
              << " pos=(" << p.x() << "," << p.y() << "," << p.z() << ")"
              << " dir=(" << p.ux() << "," << p.uy() << "," << p.uz() << ")"
              << " pol=(" << p.polx() << "," << p.poly() << "," << p.polz() << ")"
              << " time=" << p.time() << " weight=" << p.weight()
              << " pdgcode=" << p.pdgcode() << " userflags=0x" << std::hex
              << p.userflags() << std::dec << std::endl;
    auto pos = p.position();
    auto dir = p.direction();
    auto pol = p.polarisation();
    const mcpl_particle_t& c = p.c_struct();
    for ( std::size_t k = 0; k < 3; ++k ) {
      require( pos[k] == c.position[k] && dir[k] == c.direction[k]
               && pol[k] == c.polarisation[k], "array accessors differ" );
    }
    require( p.x() == c.position[0] && p.y() == c.position[1]
             && p.z() == c.position[2] && p.ux() == c.direction[0]
             && p.uy() == c.direction[1] && p.uz() == c.direction[2]
             && p.polx() == c.polarisation[0] && p.poly() == c.polarisation[1]
             && p.polz() == c.polarisation[2] && p.ekin() == c.ekin
             && p.time() == c.time && p.weight() == c.weight
             && p.pdgcode() == c.pdgcode && p.userflags() == c.userflags,
             "accessors differ from the C struct" );
  }

  void test_header()
  {
    std::cout << "\n==> Header data:" << std::endl;
    mcpl::MCPLFile f("full.mcpl");
    mcpl_file_t c = mcpl_open_file("full.mcpl");
    std::cout << "version=" << f.version() << " nparticles=" << f.nparticles()
              << " srcname=\"" << f.srcname() << "\"" << std::endl;
    std::cout << "has_userflags=" << f.has_userflags()
              << " has_polarisation=" << f.has_polarisation()
              << " has_doubleprec=" << f.has_doubleprec()
              << " universal_pdgcode=" << f.universal_pdgcode()
              << " universal_weight=" << f.universal_weight() << std::endl;
    std::cout << "header_size=" << f.header_size()
              << " particle_size=" << f.particle_size()
              << " userdata_size=" << f.userdata_size()
              << " userdata_layout=\"" << f.userdata_layout() << "\"" << std::endl;
    require( f.version() == mcpl_hdr_version(c)
             && f.nparticles() == mcpl_hdr_nparticles(c)
             && f.srcname() == mcpl_hdr_srcname(c)
             && f.header_size() == mcpl_hdr_header_size(c)
             && f.particle_size() == mcpl_hdr_particle_size(c)
             && f.little_endian() == ( mcpl_hdr_little_endian(c) != 0 )
             && f.userdata_size() == mcpl_hdr_userdata_size(c)
             && f.userdata_layout() == mcpl_hdr_userdata_layout(c),
             "header data differs from the C API" );

    //Comments:
    auto comments = f.comments();
    std::cout << "ncomments=" << f.ncomments() << " comments().size()="
              << comments.size() << std::endl;
    for ( auto cm : comments )
      std::cout << "  comment: \"" << cm << "\"" << std::endl;
    for ( std::size_t i = 0; i < comments.size(); ++i )
      require( comments[i] == mcpl_hdr_comment(c,static_cast<unsigned>(i))
               && f.comment(i) == comments[i], "comments differ" );
    std::vector<std::string> copies( comments.begin(), comments.end() );
    require( copies.size() == comments.size() && copies.back() == comments[3],
             "copying comments failed" );
    require( std::distance( comments.begin(), comments.end() ) == 4
             && comments.end() - comments.begin() == 4
             && *( comments.begin() + 1 ) == comments[1]
             && comments.begin()[2] == comments[2]
             && std::find( comments.begin(), comments.end(), "comment two" )
                - comments.begin() == 1,
             "comment iterators failed" );
    expect_throw( "comments()[4]", [&]{ (void)comments[4]; } );
    expect_throw( "comment(99)", [&]{ (void)f.comment(99); } );

    //Blobs:
    auto keys = f.blob_keys();
    std::cout << "nblobs=" << f.nblobs() << " blob_keys():";
    for ( auto k : keys )
      std::cout << " \"" << k << "\"";
    std::cout << std::endl;
    for ( auto k : keys ) {
      mcpl::BlobView b = f.blob(k);
      std::cout << "  blob \"" << k << "\": " << b.size() << " bytes:";
      for ( auto byte : b )
        std::cout << " " << static_cast<unsigned>(byte);
      std::cout << ( b.empty() ? " (empty)" : "" ) << std::endl;
      std::uint32_t ldata;
      const char * data;
      require( mcpl_hdr_blob(c,std::string(k).c_str(),&ldata,&data)
               && ldata == b.size()
               && ( ldata == 0
                    || std::memcmp(data,b.data(),ldata) == 0 )
               && ( b.empty() || b[b.size()-1] == b.data()[b.size()-1] ),
               "blob differs from the C API" );
      require( f.has_blob(k), "has_blob failed" );
    }
    require( !f.has_blob("nosuchkey"), "has_blob(nosuchkey) failed" );
    expect_throw( "blob(\"nosuchkey\")", [&]{ f.blob("nosuchkey"); } );
    expect_throw( "blob_keys()[3]", [&]{ (void)keys[3]; } );

    //Statistics "sum":
    std::cout << "has_stat_sum(nevents)=" << f.has_stat_sum("nevents")
              << " has_stat_sum(notdone)=" << f.has_stat_sum("notdone")
              << " has_stat_sum(nosuchkey)=" << f.has_stat_sum("nosuchkey")
              << std::endl;
    auto v1 = f.stat_sum("nevents");
    auto v2 = f.stat_sum("notdone");
    std::cout << "stat_sum(nevents)=" << ( v1 ? std::to_string(*v1) : "none" )
              << " stat_sum(notdone)=" << ( v2 ? std::to_string(*v2) : "none" )
              << std::endl;
    expect_throw( "stat_sum(\"nosuchkey\")", [&]{ f.stat_sum("nosuchkey"); } );

    //String views stay valid while the file is open:
    std::string_view sv = f.srcname();
    std::string_view cv = f.comment(0);
    mcpl::BlobView bv = f.blob("text");
    for ( int i = 0; i < 3; ++i )
      f.read();
    require( sv == "cppapi_read" && cv == "comment one"
             && std::string_view( reinterpret_cast<const char*>(bv.data()),
                                  bv.size() ) == "hello world",
             "views changed while reading" );
    mcpl_close_file(c);

    //Simple file:
    mcpl::MCPLFile s("simple.mcpl");
    std::cout << "simple file: version=" << s.version()
              << " srcname=\"" << s.srcname() << "\""
              << " ncomments=" << s.ncomments()
              << " nblobs=" << s.nblobs()
              << " blob_keys().size()=" << s.blob_keys().size()
              << " comments().empty()=" << s.comments().empty()
              << " has_doubleprec=" << s.has_doubleprec()
              << " universal_pdgcode=" << s.universal_pdgcode()
              << " universal_weight=" << s.universal_weight()
              << " userdata_size=" << s.userdata_size()
              << " userdata_layout=\"" << s.userdata_layout() << "\""
              << std::endl;
    int n = 0;
    for ( auto k : s.blob_keys() ) {
      (void)k;
      ++n;
    }
    for ( auto cm : s.comments() ) {
      (void)cm;
      ++n;
    }
    require( n == 0, "iteration over empty lists" );
  }

  void test_reading()
  {
    std::cout << "\n==> Reading particles:" << std::endl;
    mcpl::MCPLFile f("full.mcpl");
    mcpl_file_t c = mcpl_open_file("full.mcpl");
    //Range-based for loop:
    std::uint64_t n = 0;
    for ( auto p : f ) {
      require( static_cast<bool>(p), "empty particle in loop" );
      const mcpl_particle_t * pc = mcpl_read(c);
      require( pc && same_particle(*pc,p.c_struct()),
               "particle differs from the C API" );
      require( p.userdata_size() == 75
               && std::memcmp( p.raw_userdata(), mcpl_last_read_userdata(c),
                               75 ) == 0,
               "userdata differs from the C API" );
      print_particle(p);
      ++n;
    }
    require( n == f.nparticles() && f.current_position() == n,
             "wrong number of particles" );
    //At the end, read() gives empty particles, and loops do nothing:
    mcpl::Particle p = f.read();
    require( !p && !f.read(), "particle after the end" );
    require( f.begin() == f.end(), "loop at the end of the file" );
    std::cout << "at the end: read() gives an empty particle, and loops do"
              << " nothing" << std::endl;

    //While loop:
    require( f.rewind(), "rewind failed" );
    n = 0;
    while ( auto pp = f.read() )
      ++n;
    std::cout << "while loop read " << n << " particles" << std::endl;

    //Seeking and skipping (also loops continue from the current position):
    std::cout << "rewind()=" << f.rewind();
    std::cout << " seek(1)=" << f.seek(1);
    std::cout << " current_position()=" << f.current_position();
    std::cout << " read().x()=" << f.read().x();
    std::cout << " skip_forward(1)=" << f.skip_forward(1);
    std::cout << " read().x()=" << f.read().x();
    std::cout << " seek(5)=" << f.seek(5);
    std::cout << " seek(100)=" << f.seek(100);
    std::cout << " current_position()=" << f.current_position();
    std::cout << " rewind()=" << f.rewind();
    std::cout << " skip_forward(2)=" << f.skip_forward(2);
    std::cout << " skip_forward(10)=" << f.skip_forward(10) << std::endl;
    f.seek(2);
    std::cout << "loop from position 2:";
    for ( auto pp : f )
      std::cout << " " << pp.x();
    std::cout << std::endl;

    //Iterators with standard algorithms:
    f.rewind();
    auto ngammas = std::count_if( f.begin(), f.end(),
                                  []( const mcpl::Particle& pp )
                                  { return pp.pdgcode() == 22; } );
    std::cout << "count_if(pdgcode==22) = " << ngammas << std::endl;
    f.rewind();
    auto it = f.begin();
    double x0 = it->x();
    auto it0 = it++;
    std::cout << "iterator: it->x()=" << x0 << " after it++: it->x()="
              << it->x() << " (*it).ekin()=" << (*it).ekin()
              << " it==end: " << ( it == f.end() )
              << " it!=end: " << ( it != f.end() ) << std::endl;
    (void)it0;
    mcpl_close_file(c);

    //Simple file (single precision, universal pdgcode and weight):
    mcpl::MCPLFile s("simple.mcpl");
    for ( auto pp : s ) {
      print_particle(pp);
      require( pp.raw_userdata() == nullptr && pp.userdata_size() == 0,
               "userdata in file without userdata" );
    }
  }

  void test_userdata()
  {
    std::cout << "\n==> Userdata fields:" << std::endl;
    mcpl::MCPLFile f("full.mcpl");
    auto a = f.userdata_field<std::int8_t>("a");
    auto b = f.userdata_field<std::uint8_t>("b");
    auto c = f.userdata_field<std::int16_t>("c");
    auto d = f.userdata_field<std::uint16_t>("d");
    auto e = f.userdata_field<std::int32_t>("e");
    auto ff = f.userdata_field<std::uint32_t>("f");
    auto g = f.userdata_field<std::int64_t>("g");
    auto h = f.userdata_field<std::uint64_t>("h");
    auto i = f.userdata_field<float>("i");
    auto j = f.userdata_field<double>("j");
    auto k = f.userdata_field<float,3>("k");
    auto l = f.userdata_field<std::uint8_t,5>("l");
    auto m = f.userdata_field<std::int64_t,2>("m");
    std::cout << "offsets: " << a.offset() << " " << b.offset() << " "
              << c.offset() << " " << d.offset() << " " << e.offset() << " "
              << ff.offset() << " " << g.offset() << " " << h.offset() << " "
              << i.offset() << " " << j.offset() << " " << k.offset() << " "
              << l.offset() << " " << m.offset() << " sizes: " << a.size()
              << " " << k.size() << " " << l.size() << " " << m.size()
              << std::endl;
    int idx = 0;
    for ( auto p : f ) {
      const std::uint8_t * ud = p.raw_userdata();
      require( a(p) == mcpl_userdata_get_int8(ud,a.offset())
               && b(p) == mcpl_userdata_get_uint8(ud,b.offset())
               && c(p) == mcpl_userdata_get_int16(ud,c.offset())
               && d(p) == mcpl_userdata_get_uint16(ud,d.offset())
               && e(p) == mcpl_userdata_get_int32(ud,e.offset())
               && ff(p) == mcpl_userdata_get_uint32(ud,ff.offset())
               && g(p) == mcpl_userdata_get_int64(ud,g.offset())
               && h(p) == mcpl_userdata_get_uint64(ud,h.offset())
               && i(p) == mcpl_userdata_get_float32(ud,i.offset())
               && j(p) == mcpl_userdata_get_float64(ud,j.offset()),
               "userdata differs from the C API" );
      std::array<float,3> kv = k(p);
      std::array<std::uint8_t,5> lv = l(p);
      std::array<std::int64_t,2> mv = m(p);
      for ( std::size_t q = 0; q < 3; ++q )
        require( kv[q] == k(p,q)
                 && kv[q] == mcpl_userdata_get_float32(ud,k.offset()
                                                       +4*static_cast<std::uint32_t>(q)),
                 "array userdata differs" );
      for ( std::size_t q = 0; q < 5; ++q )
        require( lv[q] == l(p,q), "array userdata differs" );
      for ( std::size_t q = 0; q < 2; ++q )
        require( mv[q] == m(p,q), "array userdata differs" );
      std::cout << "  particle " << idx++ << ": a=" << int(a(p))
                << " b=" << unsigned(b(p)) << " c=" << c(p) << " d=" << d(p)
                << " e=" << e(p) << " f=" << ff(p) << " g=" << g(p)
                << " h=" << h(p) << " i=" << i(p) << " j=" << j(p)
                << " k=" << kv[0] << "," << kv[1] << "," << kv[2]
                << " l=" << unsigned(lv[0]) << "," << unsigned(lv[4])
                << " m=" << mv[0] << "," << mv[1] << std::endl;
    }

    //Errors when getting fields:
    expect_throw( "userdata_field<double>(\"i\") (float32 field)",
                  [&]{ f.userdata_field<double>("i"); } );
    expect_throw( "userdata_field<std::uint8_t>(\"a\") (int8 field)",
                  [&]{ f.userdata_field<std::uint8_t>("a"); } );
    expect_throw( "userdata_field<float>(\"k\") (array field)",
                  [&]{ f.userdata_field<float>("k"); } );
    expect_throw( "userdata_field<float,2>(\"k\") (float32[3] field)",
                  [&]{ f.userdata_field<float,2>("k"); } );
    expect_throw( "userdata_field<float,1>(\"i\") (scalar field)",
                  [&]{ f.userdata_field<float,1>("i"); } );
    expect_throw( "userdata_field<float>(\"nosuch\")",
                  [&]{ f.userdata_field<float>("nosuch"); } );
    expect_throw( "userdata_field<float>(\"\")",
                  [&]{ f.userdata_field<float>(""); } );
    mcpl::MCPLFile s("simple.mcpl");
    expect_throw( "userdata_field<float>(\"i\") (file without userdata)",
                  [&]{ s.userdata_field<float>("i"); } );

    //Errors when using fields:
    f.rewind();
    mcpl::Particle p = f.read();
    expect_throw( "k(p,3)", [&]{ k(p,3); } );
    expect_throw( "l(p,5)", [&]{ l(p,5); } );
    mcpl::Particle ps = s.read();
    expect_throw( "i(particle without userdata)", [&]{ i(ps); } );
    expect_throw( "k(particle without userdata,0)", [&]{ k(ps,0); } );
    mcpl::Particle empty;
    expect_throw( "i(empty particle)", [&]{ i(empty); } );
    //Fields from other files with shorter userdata:
    {
      mcpl_outfile_t o = mcpl_create_outfile("short.mcpl");
      mcpl_enable_userdata(o,"p:float64,q:float64");
      mcpl_particle_t * pp = mcpl_get_empty_particle(o);
      fill(pp,0);
      mcpl_add_particle_with_userdata(o,pp,nullptr);
      mcpl_close_outfile(o);
    }
    mcpl::MCPLFile sh("short.mcpl");
    mcpl::Particle psh = sh.read();
    expect_throw( "m(particle with shorter userdata)", [&]{ m(psh); } );
    expect_throw( "m(particle with shorter userdata,0)", [&]{ m(psh,0); } );
    std::cout << "a(particle with shorter userdata) = " << int(a(psh))
              << " (fields within the userdata can be used)" << std::endl;
    //Fields can be used with other files having the same layout:
    create_full_file("full2.mcpl",2);
    mcpl::MCPLFile f2("full2.mcpl");
    f2.skip_forward(1);
    std::cout << "j(particle 1 of another file) = " << j(f2.read())
              << std::endl;
    sh.close();
    std::remove("short.mcpl");
  }

  void test_errors()
  {
    std::cout << "\n==> Errors:" << std::endl;
    expect_throw( "MCPLFile(\"nosuchfile.mcpl\")",
                  []{ mcpl::MCPLFile f("nosuchfile.mcpl"); } );
    expect_throw( "MCPLFile(\"\")", []{ mcpl::MCPLFile f(""); } );
    {
      std::string data = mcpltest::file_contents("full.mcpl");
      mcpltest::write_file( "trunc_hdr.mcpl", data.substr(0,40) );
      mcpltest::write_file( "trunc_data.mcpl",
                            data.substr(0,data.size()-10) );
      mcpltest::write_file( "garbage.mcpl", "this is not an MCPL file" );
    }
    expect_throw( "MCPLFile(\"trunc_hdr.mcpl\")",
                  []{ mcpl::MCPLFile f("trunc_hdr.mcpl"); } );
    expect_throw( "MCPLFile(\"garbage.mcpl\")",
                  []{ mcpl::MCPLFile f("garbage.mcpl"); } );
    {
      mcpl::MCPLFile f("trunc_data.mcpl");
      std::cout << "trunc_data.mcpl opened, reading:";
      try {
        for ( auto p : f )
          std::cout << " " << p.x();
        mcpltest::fail("no error while reading truncated data");
      } catch ( const mcpl::Error& ) {
        std::cout << std::endl << "  -> " << mcpltest::describe_current_exception()
                  << std::endl;
      }
      //The error is sticky (the file can then only be closed):
      expect_throw( "read() after the error", [&]{ f.read(); } );
      expect_throw( "rewind() after the error", [&]{ f.rewind(); } );
      expect_throw( "seek(0) after the error", [&]{ f.seek(0); } );
      expect_throw( "skip_forward(0) after the error",
                    [&]{ f.skip_forward(0); } );
      expect_throw( "dump() after the error", [&]{ f.dump(); } );
      std::cout << "header data still available: nparticles="
                << f.nparticles() << std::endl;
    }
    for ( const char * fn : { "trunc_hdr.mcpl", "trunc_data.mcpl",
                              "garbage.mcpl" } )
      std::remove(fn);
  }

  void test_moves()
  {
    std::cout << "\n==> Moving and closing:" << std::endl;
    mcpl::MCPLFile f("full.mcpl");
    f.read();
    mcpl::MCPLFile g( std::move(f) );
    std::cout << "after move construction: f.is_open()=" << f.is_open()
              << " g.is_open()=" << g.is_open()
              << " g.current_position()=" << g.current_position()
              << std::endl;
    expect_throw( "f.nparticles() (moved from)", [&]{ f.nparticles(); } );
    expect_throw( "f.srcname() (moved from)", [&]{ f.srcname(); } );
    expect_throw( "f.comments() (moved from)", [&]{ f.comments(); } );
    expect_throw( "f.blob_keys() (moved from)", [&]{ f.blob_keys(); } );
    expect_throw( "f.has_blob(\"text\") (moved from)",
                  [&]{ f.has_blob("text"); } );
    expect_throw( "f.read() (moved from)", [&]{ f.read(); } );
    expect_throw( "f.seek(0) (moved from)", [&]{ f.seek(0); } );
    expect_throw( "f.current_position() (moved from)",
                  [&]{ f.current_position(); } );
    expect_throw( "f.stat_sum(\"nevents\") (moved from)",
                  [&]{ f.stat_sum("nevents"); } );
    expect_throw( "f.userdata_field<float>(\"i\") (moved from)",
                  [&]{ f.userdata_field<float>("i"); } );
    expect_throw( "f.userdata_size() (moved from)",
                  [&]{ f.userdata_size(); } );
    expect_throw( "f.dump() (moved from)", [&]{ f.dump(); } );
    expect_throw( "loop over f (moved from)", [&]{
      for ( auto p : f ) { (void)p; }
    } );
    //Move assignment (closing the file assigned to):
    mcpl::MCPLFile h("simple.mcpl");
    h = std::move(g);
    std::cout << "after move assignment: g.is_open()=" << g.is_open()
              << " h.is_open()=" << h.is_open()
              << " h.srcname()=\"" << h.srcname() << "\""
              << " h.current_position()=" << h.current_position()
              << std::endl;
    //Moving into a moved-from object, and self-move:
    f = std::move(h);
    mcpl::MCPLFile& fref = f;
    f = std::move(fref);
    std::cout << "f.is_open()=" << f.is_open() << " after self-move"
              << std::endl;
    //Closing:
    f.close();
    f.close();
    std::cout << "after close(): is_open()=" << f.is_open() << std::endl;
    expect_throw( "f.version() (closed)", [&]{ f.version(); } );
    //Objects can be kept in containers:
    std::vector<mcpl::MCPLFile> files;
    files.emplace_back("full.mcpl");
    files.emplace_back("simple.mcpl");
    files.emplace_back("full2.mcpl");
    std::uint64_t ntot = 0;
    for ( auto& ff : files )
      ntot += ff.nparticles();
    std::cout << "files in a vector: " << ntot << " particles in total"
              << std::endl;
  }

  void test_misc()
  {
    std::cout << "\n==> Filenames, gzipped files and C handles:" << std::endl;
    std::string s("simple.mcpl");
    std::string_view sv(s);
    std::filesystem::path p(s);
    expect_ok( "MCPLFile(std::string)", [&]{ mcpl::MCPLFile f(s); } );
    expect_ok( "MCPLFile(std::string_view)", [&]{ mcpl::MCPLFile f(sv); } );
    expect_ok( "MCPLFile(std::filesystem::path)", [&]{ mcpl::MCPLFile f(p); } );
    expect_ok( "MCPLFile(const char*)",
               [&]{ mcpl::MCPLFile f(s.c_str()); } );
    //Non-ASCII filenames (UTF-8):
    const std::string u8name = "simple_\xc3\xa6\xc3\xb8\xc3\xa5.mcpl";
    {
      mcpl_outfile_t o = mcpl_create_outfile(u8name.c_str());
      mcpl_close_outfile(o);
    }
    expect_ok( "MCPLFile(UTF-8 std::string)",
               [&]{ mcpl::MCPLFile f(u8name); } );
    expect_ok( "MCPLFile(std::filesystem::path from UTF-8 name)",
               [&]{ mcpl::MCPLFile f(utf8_path(u8name)); } );
    std::filesystem::remove(utf8_path(u8name));

    //Gzipped files:
    {
      std::string data = mcpltest::file_contents("full.mcpl");
      mcpltest::write_file("fullgz.mcpl",data);
      mcpl::set_print_handler( []( const char * ) {} );
      mcpl::gzip_file("fullgz.mcpl");
      mcpl::set_print_handler( nullptr );
    }
    {
      mcpl::MCPLFile f("fullgz.mcpl.gz");
      mcpl::MCPLFile fref("full.mcpl");
      std::uint64_t n = 0;
      for ( auto pp : f ) {
        require( same_particle( pp.c_struct(), fref.read().c_struct() ),
                 "gzipped file differs" );
        ++n;
      }
      f.seek(1);
      std::cout << "gzipped file: " << n << " particles, seek(1) then read()"
                << " gives x=" << f.read().x() << std::endl;
    }
    std::remove("fullgz.mcpl.gz");

    //C handles:
    mcpl::MCPLFile f("full.mcpl");
    mcpl_file_t c = f.c_handle();
    std::cout << "C API on c_handle(): nparticles="
              << mcpl_hdr_nparticles(c) << ", mcpl_read gives x="
              << mcpl_read(c)->position[0] << ", then read().x()="
              << f.read().x() << std::endl;
  }

}

int main()
{
  create_full_file("full.mcpl",5);
  create_simple_file("simple.mcpl",3);
  test_header();
  test_reading();
  test_userdata();
  test_errors();
  test_moves();
  test_misc();
  std::remove("full.mcpl");
  std::remove("full2.mcpl");
  std::remove("simple.mcpl");
  std::cout << "\nAll ok" << std::endl;
  return 0;
}
