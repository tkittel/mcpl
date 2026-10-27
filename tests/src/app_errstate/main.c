
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

//Tests of the functions reporting errors in an error state (the _es variants)
//when reading files. Broken files are crafted byte by byte, and every error
//is checked in-process. (The functions without _es are wrappers which pass a
//NULL error state, and their errors are tested in errstate_legacy.py.)

#include "mcpltest_errstate.h"

////////////////////////////////////////////////////////////////////////////////
// Test files

static void fill_particle( mcpl_particle_t * p, int i )
{
  p->position[0] = 1.0 + i;
  p->position[1] = 2.0 * i;
  p->position[2] = -3.0 - i;
  p->direction[0] = 0.0;
  p->direction[1] = 0.6;
  p->direction[2] = 0.8;
  p->polarisation[0] = 0.5;
  p->polarisation[1] = -0.5;
  p->polarisation[2] = 0.25;
  p->ekin = 0.001 * ( i + 1 );
  p->time = 0.1 * i;
  p->weight = 1.0 + 0.5 * i;
  p->pdgcode = ( i % 2 ) ? 22 : 2112;
  p->userflags = (uint32_t)( 1000 + i );
}

//File "a.mcpl": MCPL-3, single precision, polarisation, userflags, comments
//(also stat:sum), a blob, and 10 particles:
static void create_file_a(void)
{
  mcpl_outfile_t f = mcpl_create_outfile("a.mcpl");
  mcpl_hdr_set_srcname(f,"errstate_test");
  mcpl_hdr_add_comment(f,"first comment");
  mcpl_hdr_add_comment(f,"xtat:unknown");//turned into "stat:unknown" below
  mcpl_hdr_add_stat_sum(f,"nevents",1000.0);
  mcpl_hdr_add_stat_sum(f,"nevento",2000.0);//turned into a duplicate below
  mcpl_hdr_add_data(f,"blobkey",8,"blobdata");
  mcpl_enable_userflags(f);
  mcpl_enable_polarisation(f);
  mcpl_particle_t * p = mcpl_get_empty_particle(f);
  for ( int i = 0; i < 10; ++i ) {
    fill_particle(p,i);
    mcpl_add_particle(f,p);
  }
  mcpl_close_outfile(f);
}

//File "b.mcpl": MCPL-4 (userdata), double precision, universal pdgcode and
//weight, and 5 particles:
static void create_file_b(void)
{
  mcpl_outfile_t f = mcpl_create_outfile("b.mcpl");
  mcpl_hdr_set_srcname(f,"errstate_test_b");
  mcpl_enable_doubleprec(f);
  mcpl_enable_universal_pdgcode(f,2112);
  mcpl_enable_universal_weight(f,2.0);
  mcpl_enable_userdata(f,"temp:float32,tags:uint8[3]");
  mcpl_particle_t * p = mcpl_get_empty_particle(f);
  uint8_t ud[7];
  for ( int i = 0; i < 5; ++i ) {
    fill_particle(p,i);
    p->pdgcode = 2112;
    p->weight = 2.0;
    mcpl_userdata_set_float32(ud,0,(float)(300+i));
    ud[4] = (uint8_t)i;
    ud[5] = (uint8_t)(2*i);
    ud[6] = (uint8_t)(3*i);
    mcpl_add_particle_with_userdata(f,p,ud);
  }
  mcpl_close_outfile(f);
}

//File "d.mcpl": with a stat:sum: entry which is not available (-1), and two
//comments turned into invalid stat:sum: entries with long keys below:
static void create_file_d(void)
{
  mcpl_outfile_t f = mcpl_create_outfile("d.mcpl");
  mcpl_hdr_add_stat_sum(f,"notavail",-1.0);
  mcpl_hdr_add_stat_sum(f,"avail",17.0);
  char buf[2100];
  memcpy(buf,"xtat:sum:",9);
  memset(buf+9,'k',1200);
  buf[1209] = '\0';
  mcpl_hdr_add_comment(f,buf);
  memcpy(buf,"ytat:sum:",9);
  memset(buf+9,'k',2000);
  buf[2009] = '\0';
  mcpl_hdr_add_comment(f,buf);
  mcpl_particle_t * p = mcpl_get_empty_particle(f);
  for ( int i = 0; i < 3; ++i ) {
    fill_particle(p,i);
    mcpl_add_particle(f,p);
  }
  mcpl_close_outfile(f);
}

//File "c.mcpl": with 1000 particles (for tests of truncated gzipped data):
static void create_file_c(void)
{
  mcpl_outfile_t f = mcpl_create_outfile("c.mcpl");
  mcpl_particle_t * p = mcpl_get_empty_particle(f);
  for ( int i = 0; i < 1000; ++i ) {
    fill_particle(p,i);
    mcpl_add_particle(f,p);
  }
  mcpl_close_outfile(f);
}

////////////////////////////////////////////////////////////////////////////////
// Opening files

//Try to open the file with mcpl_open_file_es, returning 1 if it could be
//opened (and printing the result unless quiet):
static int check_open_ex( const char * filename, mcpl_errstate_t * es,
                          int quiet )
{
  es_reset(es);
  mcpl_file_t f = mcpl_open_file_es(filename,es);
  int ok = !es_failed(es);
  if ( ok != ( f.internal != NULL ) )
    test_fail("mcpl_open_file_es: inconsistent return value and error state");
  if (!quiet) {
    char what[256];
    snprintf(what,sizeof(what),"open(%s)",filename);
    print_result(what,es);
  }
  mcpl_close_file(f);//does nothing for f.internal==NULL
  return ok;
}

static int check_open( const char * filename )
{
  mcpl_errstate_t es;
  return check_open_ex( filename, &es, 0 );
}

//Open files with the first n bytes of the file, for all n in [0,nmax],
//printing ranges of n with the same result. With dogzip, the truncated files
//are gzipped first:
static void test_truncations( const char * label, const buffer_t * b,
                              size_t nmax, int dogzip )
{
  printf("\n==> Opening %s truncated to n bytes%s:\n",label,
         dogzip ? " (gzipped)" : "");
  mcpl_errstate_t es;
  char prev[1100];
  prev[0] = '\0';
  size_t range_start = 0;
  for ( size_t n = 0; n <= nmax + 1; ++n ) {
    char res[1100];
    if ( n <= nmax ) {
      save_modified("trunc.mcpl",b,n,0,NULL,0);
      const char * fn = "trunc.mcpl";
      if ( dogzip ) {
        quiet_gzip("trunc.mcpl");
        fn = "trunc.mcpl.gz";
      }
      if ( check_open_ex( fn, &es, 1 ) )
        snprintf(res,sizeof(res),"ok");
      else
        snprintf(res,sizeof(res),"ERROR %s: %s",code_name(es.code),es.msg);
      remove(fn);
    } else {
      res[0] = '\0';
    }
    if ( n == 0 ) {
      memcpy(prev,res,sizeof(res));
      continue;
    }
    if ( strcmp(res,prev) != 0 ) {
      printf("  n=[%u,%u] -> %s\n",(unsigned)range_start,(unsigned)(n-1),prev);
      range_start = n;
      memcpy(prev,res,sizeof(res));
    }
  }
}

static void test_open_errors(void)
{
  printf("\n==> Opening missing files, directories and NULL:\n");
  check_open("doesnotexist.mcpl");
  check_open("doesnotexist.mcpl.gz");
  {
    //Directories (fopen fails on some platforms, fread on others, so the
    //messages differ, but both are I/O errors):
    mcpl_errstate_t es;
    check_open_ex( ".", &es, 1 );
    printf("open(.) -> ERROR %s\n",code_name(es.code));
  }
  {
    mcpl_errstate_t es;
    es_reset(&es);
    mcpl_file_t f = mcpl_open_file_es(NULL,&es);
    if ( f.internal )
      test_fail("open(NULL) succeeded");
    print_result("open(NULL)",&es);
  }

  buffer_t a = file_load("a.mcpl");
  buffer_t b = file_load("b.mcpl");

  printf("\n==> Opening modified files:\n");
  save_modified("x.mcpl",&a,a.size,0,"X",1);
  check_open("x.mcpl");
  save_modified("x.mcpl",&a,a.size,4,"001",3);
  check_open("x.mcpl");
  save_modified("x.mcpl",&a,a.size,4,"005",3);
  check_open("x.mcpl");
  save_modified("x.mcpl",&a,a.size,4,"0a3",3);
  check_open("x.mcpl");
  {
    //Endianness: the other one, and an invalid value:
    const char other = ( a.data[7] == 'L' ? 'B' : 'L' );
    save_modified("x.mcpl",&a,a.size,7,&other,1);
    check_open("x.mcpl");
    save_modified("x.mcpl",&a,a.size,7,"X",1);
    check_open("x.mcpl");
  }
  {
    //Particle size (at byte 40) too large for MCPL-3, or not matching the
    //fields in MCPL-4:
    uint32_t psize = 97;
    save_modified("x.mcpl",&a,a.size,40,&psize,4);
    check_open("x.mcpl");
    memcpy(&psize,b.data+40,4);
    psize += 1;
    save_modified("x.mcpl",&b,b.size,40,&psize,4);
    check_open("x.mcpl");
  }
  //Not an MCPL file (gzipped files are read transparently by zlib when not
  //compressed):
  file_save("x.mcpl.gz",(const unsigned char*)"Hello world, not MCPL",21);
  check_open("x.mcpl.gz");
  remove("x.mcpl.gz");
  //Null byte in a string:
  save_modified("x.mcpl",&a,a.size,buf_find(&a,"errstate_test")+3,"\0",1);
  check_open("x.mcpl");
  //Invalid userdata layout:
  save_modified("x.mcpl",&b,b.size,buf_find(&b,"temp:float32"),"Temp",4);
  check_open("x.mcpl");
  save_modified("x.mcpl",&b,b.size,buf_find(&b,"tags:uint8[3]")+11,"0",1);
  check_open("x.mcpl");
  //Invalid stat:sum: comment:
  save_modified("x.mcpl",&a,a.size,buf_find(&a,"stat:sum:nevents:")+20,"x",1);
  check_open("x.mcpl");
  save_modified("x.mcpl",&a,a.size,buf_find(&a,"stat:sum:nevents:")+16,"?",1);
  check_open("x.mcpl");
  //Duplicate stat:sum: keys:
  save_modified("x.mcpl",&a,a.size,buf_find(&a,"stat:sum:nevento")+15,"s",1);
  check_open("x.mcpl");
  //Unknown stat: syntax only gives a warning:
  save_modified("x.mcpl",&a,a.size,buf_find(&a,"xtat:unknown"),"s",1);
  check_open("x.mcpl");
  //Files which were not closed properly (nparticles=0 in the header) can be
  //read (with a warning), except when gzipped:
  {
    uint64_t zero = 0;
    save_modified("x.mcpl",&a,a.size,8,&zero,8);
    check_open("x.mcpl");
    save_modified("x.mcpl",&a,a.size-7,8,&zero,8);
    check_open("x.mcpl");
    save_modified("x.mcpl",&a,a.size,8,&zero,8);
    quiet_gzip("x.mcpl");
    check_open("x.mcpl.gz");
    remove("x.mcpl.gz");
  }
  //Long invalid stat:sum: comments (the error message is truncated to 1023
  //characters in the error state):
  {
    buffer_t d = file_load("d.mcpl");
    save_modified("x.mcpl",&d,d.size,buf_find(&d,"xtat:sum:"),"s",1);
    mcpl_errstate_t es;
    check_open_ex( "x.mcpl", &es, 1 );
    printf("open(x.mcpl) -> ERROR %s: %.150s... (%u characters)\n",
           code_name(es.code),es.msg,(unsigned)strlen(es.msg));
    save_modified("x.mcpl",&d,d.size,buf_find(&d,"ytat:sum:"),"s",1);
    check_open("x.mcpl");
    //Not properly closed file with a stat:sum: entry which is already not
    //available (-1), so only the other one is marked as such:
    uint64_t zero = 0;
    save_modified("x.mcpl",&d,d.size,8,&zero,8);
    check_open("x.mcpl");
    free(d.data);
  }
  //Huge numbers of comments or blobs, exceeding the limit on the memory
  //needed for headers (5 GB, estimated with 64 bytes per comment or blob in
  //addition to their data). The arrays also only grow as entries are actually
  //read, so smaller numbers do not lead to huge allocations either (here,
  //with 70 million comments, reading beyond the real comments gives string
  //lengths which exceed the limit as well):
  {
    uint32_t huge = 0xFFFFFFFF;
    uint32_t many = 70000000;//4.48 GB
    const char * fn[2] = { "huge_comments.mcpl", "huge_blobs.mcpl" };
    for ( int i = 0; i < 2; ++i ) {
      save_modified(fn[i],&a,a.size,16+4*i,&huge,4);
      check_open(fn[i]);
      save_modified(fn[i],&a,a.size,16+4*i,&many,4);
      check_open(fn[i]);
      remove(fn[i]);
    }
    //Many comments and a long string, together exceeding the limit:
    unsigned char * d = (unsigned char*)malloc(a.size);
    memcpy(d,a.data,a.size);
    memcpy(d+16,&many,4);
    uint32_t len = 600000000;
    memcpy(d+buf_find(&a,"errstate_test")-4,&len,4);
    file_save("x.mcpl",d,a.size);
    free(d);
    check_open("x.mcpl");
  }
  remove("x.mcpl");

  //Truncated headers (all lengths):
  mcpl_file_t fa = mcpl_open_file("a.mcpl");
  size_t hdr_a = (size_t)mcpl_hdr_header_size(fa);
  mcpl_close_file(fa);
  mcpl_file_t fb = mcpl_open_file("b.mcpl");
  size_t hdr_b = (size_t)mcpl_hdr_header_size(fb);
  mcpl_close_file(fb);
  test_truncations("a.mcpl",&a,hdr_a,0);
  test_truncations("a.mcpl",&a,hdr_a,1);
  test_truncations("b.mcpl",&b,hdr_b,0);
  test_truncations("b.mcpl",&b,hdr_b,1);

  free(a.data);
  free(b.data);
}

////////////////////////////////////////////////////////////////////////////////
// Reading, seeking and header access

static void print_read( const char * what, const mcpl_particle_t * p,
                        mcpl_errstate_t * es )
{
  char buf[256];
  if (p)
    snprintf(buf,sizeof(buf),"%s (particle with x=%g)",what,p->position[0]);
  else
    snprintf(buf,sizeof(buf),"%s (NULL)",what);
  print_result(buf,es);
}

static void test_invalid_handle(void)
{
  printf("\n==> Functions called with invalid file objects (internal NULL):\n");
  mcpl_file_t f;
  f.internal = NULL;
  mcpl_errstate_t es;
  const uint8_t * ud = (const uint8_t *)"x";

  es_reset(&es);
  const mcpl_particle_t * p = mcpl_read_es(f,&es);
  print_read("read",p,&es);

  es_reset(&es);
  p = mcpl_read_with_userdata_es(f,&ud,&es);
  print_read("read_with_userdata",p,&es);
  if ( ud )
    test_fail("userdata not NULL after error");

  es_reset(&es);
  printf("  skipforward returned %i\n",mcpl_skipforward_es(f,1,&es));
  print_result("skipforward",&es);

  es_reset(&es);
  printf("  rewind returned %i\n",mcpl_rewind_es(f,&es));
  print_result("rewind",&es);

  es_reset(&es);
  printf("  seek returned %i\n",mcpl_seek_es(f,0,&es));
  print_result("seek",&es);

  es_reset(&es);
  const char * c = mcpl_hdr_comment_es(f,0,&es);
  printf("  hdr_comment returned %s\n",c?"non-NULL":"NULL");
  print_result("hdr_comment",&es);

  es_reset(&es);
  printf("  hdr_stat_sum returned %g\n",mcpl_hdr_stat_sum_es(f,"nevents",&es));
  print_result("hdr_stat_sum",&es);

  //Closing does nothing:
  mcpl_close_file(f);
  printf("close -> ok\n");
}

static void test_reading_ok(void)
{
  printf("\n==> Successful calls only set the error code (to 0):\n");
  mcpl_errstate_t es;
  es_reset(&es);
  mcpl_file_t f = mcpl_open_file_es("a.mcpl",&es);
  print_result("open(a.mcpl)",&es);
  unsigned n = 0;
  while ( mcpl_read_es(f,&es) )
    ++n;
  printf("  read %u particles\n",n);
  print_result("read until end of file",&es);
  int r1 = mcpl_rewind_es(f,&es);
  int r2 = mcpl_skipforward_es(f,3,&es);
  int r3 = mcpl_seek_es(f,9,&es);
  int r4 = mcpl_seek_es(f,10,&es);
  int r5 = mcpl_skipforward_es(f,100,&es);
  printf("  rewind -> %i, skipforward(3) -> %i, seek(9) -> %i, seek(10) -> %i,"
         " skipforward(100) -> %i\n",r1,r2,r3,r4,r5);
  print_result("rewind/skipforward/seek",&es);
  printf("  comment 0: \"%s\", stat:sum:nevents: %g, stat:sum:nokey: %g\n",
         mcpl_hdr_comment_es(f,0,&es),mcpl_hdr_stat_sum_es(f,"nevents",&es),
         mcpl_hdr_stat_sum_es(f,"nokey",&es));
  print_result("header access",&es);
  mcpl_close_file(f);

  es_reset(&es);
  f = mcpl_open_file_es("b.mcpl",&es);
  const uint8_t * ud = NULL;
  const mcpl_particle_t * p;
  uint32_t o_temp = mcpl_userdata_offset_es(mcpl_hdr_userdata_layout(f),
                                            "temp","float32",&es);
  while ( ( p = mcpl_read_with_userdata_es(f,&ud,&es) ) )
    printf("  particle x=%g weight=%g pdgcode=%i temp=%g tags=%u,%u,%u\n",
           p->position[0],p->weight,(int)p->pdgcode,
           (double)mcpl_userdata_get_float32(ud,o_temp),
           (unsigned)ud[4],(unsigned)ud[5],(unsigned)ud[6]);
  if ( ud )
    test_fail("userdata not NULL at end of file");
  print_result("reading b.mcpl with userdata",&es);
  mcpl_close_file(f);
}

static void test_header_errors(void)
{
  printf("\n==> Errors in header access leave the file usable:\n");
  mcpl_errstate_t es;
  es_reset(&es);
  mcpl_file_t f = mcpl_open_file_es("a.mcpl",&es);
  const mcpl_particle_t * p = mcpl_read_es(f,&es);
  print_read("read",p,&es);

  es_reset(&es);
  const char * c = mcpl_hdr_comment_es(f,4,&es);
  printf("  hdr_comment(4) returned %s\n",c?"non-NULL":"NULL");
  print_result("hdr_comment(4)",&es);

  es_reset(&es);
  printf("  hdr_stat_sum(NULL) returned %g\n",mcpl_hdr_stat_sum_es(f,NULL,&es));
  print_result("hdr_stat_sum(NULL)",&es);

  //A successful call after an error resets the code (without es_reset):
  mcpl_hdr_comment_es(f,0,&es);
  printf("  code after successful call following an error: %i\n",es.code);

  es_reset(&es);
  p = mcpl_read_es(f,&es);
  print_read("read",p,&es);
  printf("  comment 3: \"%s\"\n",mcpl_hdr_comment_es(f,3,&es));
  print_result("hdr_comment(3)",&es);
  mcpl_close_file(f);
}

//Read file until EOF or an error, then check that the file can only be
//closed (and that other functions give the same error):
static void test_read_failure( const char * filename, int print_count )
{
  printf("\n==> Reading %s:\n",filename);
  mcpl_errstate_t es;
  es_reset(&es);
  mcpl_file_t f = mcpl_open_file_es(filename,&es);
  print_result("open",&es);
  if ( !f.internal )
    test_fail("could not open file");
  unsigned n = 0;
  const mcpl_particle_t * p;
  while ( ( p = mcpl_read_es(f,&es) ) )
    ++n;
  if ( print_count )
    printf("  read %u particles of %u\n",n,(unsigned)mcpl_hdr_nparticles(f));
  else if ( n == 0 )
    test_fail("no particles read");
  print_read("read",p,&es);
  if ( !es_failed(&es) )
    test_fail("expected error not seen");
  mcpl_errstate_t first = es;

  //Further reading, skipping or seeking gives the same error:
  es_reset(&es);
  p = mcpl_read_es(f,&es);
  print_read("read again",p,&es);
  es_reset(&es);
  const uint8_t * ud = (const uint8_t *)"x";
  p = mcpl_read_with_userdata_es(f,&ud,&es);
  if ( ud )
    test_fail("userdata not NULL after error");
  print_read("read_with_userdata",p,&es);
  es_reset(&es);
  printf("  skipforward returned %i\n",mcpl_skipforward_es(f,1,&es));
  print_result("skipforward",&es);
  es_reset(&es);
  printf("  rewind returned %i\n",mcpl_rewind_es(f,&es));
  print_result("rewind",&es);
  es_reset(&es);
  printf("  seek returned %i\n",mcpl_seek_es(f,0,&es));
  print_result("seek",&es);
  if ( es.code != first.code || strcmp(es.msg,first.msg) != 0 )
    test_fail("different error after the first one");

  //The header can still be accessed:
  es_reset(&es);
  const char * comment0 = "<none>";
  if ( mcpl_hdr_ncomments(f) )
    comment0 = mcpl_hdr_comment_es(f,0,&es);
  printf("  header still available: nparticles=%u, srcname=\"%s\","
         " comment 0: \"%s\", stat:sum:nevents: %g\n",
         (unsigned)mcpl_hdr_nparticles(f),mcpl_hdr_srcname(f),comment0,
         mcpl_hdr_stat_sum_es(f,"nevents",&es));
  print_result("header access",&es);
  mcpl_close_file(f);
}

static void test_truncated_data(void)
{
  //Particle data ending in the middle of the 7th particle (the header still
  //says 10 particles):
  buffer_t a = file_load("a.mcpl");
  mcpl_file_t f = mcpl_open_file("a.mcpl");
  size_t hdr = (size_t)mcpl_hdr_header_size(f);
  size_t psize = (size_t)mcpl_hdr_particle_size(f);
  mcpl_close_file(f);
  save_modified("trdata.mcpl",&a,hdr + 6 * psize + psize / 2,0,NULL,0);
  test_read_failure("trdata.mcpl",1);
  save_modified("trdata.mcpl",&a,hdr + 6 * psize + psize / 2,0,NULL,0);
  quiet_gzip("trdata.mcpl");
  test_read_failure("trdata.mcpl.gz",1);
  free(a.data);

  //Seeking to the missing particles works, but reading them fails:
  printf("\n==> Seeking in truncated files:\n");
  const char * fns[2] = { "trdata2.mcpl", "trdata2.mcpl.gz" };
  for ( int i = 0; i < 2; ++i ) {
    mcpl_errstate_t es;
    a = file_load("a.mcpl");
    save_modified("trdata2.mcpl",&a,hdr + 6 * psize + psize / 2,0,NULL,0);
    free(a.data);
    if ( i == 1 )
      quiet_gzip("trdata2.mcpl");
    es_reset(&es);
    f = mcpl_open_file_es(fns[i],&es);
    printf("  %s: seek(8) -> %i\n",fns[i],mcpl_seek_es(f,8,&es));
    print_result("  seek(8)",&es);
    const mcpl_particle_t * p = mcpl_read_es(f,&es);
    print_read("  read",p,&es);
    mcpl_close_file(f);
    es_reset(&es);
    f = mcpl_open_file_es(fns[i],&es);
    printf("  %s: skipforward(8) -> %i\n",fns[i],mcpl_skipforward_es(f,8,&es));
    print_result("  skipforward(8)",&es);
    mcpl_close_file(f);
    remove(fns[i]);
  }

  //Truncated compressed data (where exactly the data ends depends on the
  //compression, so only the error is printed):
  buffer_t c = file_load("c.mcpl");
  file_save("cz.mcpl",c.data,c.size);
  free(c.data);
  quiet_gzip("cz.mcpl");
  buffer_t cz = file_load("cz.mcpl.gz");
  file_save("cz.mcpl.gz",cz.data,cz.size/2);
  free(cz.data);
  test_read_failure("cz.mcpl.gz",0);

  //Seeking and skipping beyond the end of truncated compressed data works,
  //since zlib only skips the data when reading the next time, so the error
  //comes when reading. After that, rewinding fails as well:
  printf("\n==> Seeking in truncated compressed data:\n");
  {
    mcpl_errstate_t es;
    es_reset(&es);
    f = mcpl_open_file_es("cz.mcpl.gz",&es);
    printf("  seek(990) -> %i\n",mcpl_seek_es(f,990,&es));
    print_result("  seek(990)",&es);
    mcpl_close_file(f);
    es_reset(&es);
    f = mcpl_open_file_es("cz.mcpl.gz",&es);
    printf("  skipforward(10) -> %i\n",mcpl_skipforward_es(f,10,&es));
    print_result("  skipforward(10)",&es);
    printf("  rewind -> %i\n",mcpl_rewind_es(f,&es));
    print_result("  rewind",&es);
    printf("  skipforward(990) -> %i\n",mcpl_skipforward_es(f,990,&es));
    print_result("  skipforward(990)",&es);
    mcpl_close_file(f);
    es_reset(&es);
    f = mcpl_open_file_es("cz.mcpl.gz",&es);
    printf("  skipforward(10) -> %i\n",mcpl_skipforward_es(f,10,&es));
    printf("  seek(5) -> %i\n",mcpl_seek_es(f,5,&es));
    print_result("  seek(5)",&es);
    while ( mcpl_read_es(f,&es) ) {}
    print_result("  read until error",&es);
    es_reset(&es);
    printf("  rewind -> %i\n",mcpl_rewind_es(f,&es));
    print_result("  rewind after error",&es);
    mcpl_close_file(f);
  }
  remove("cz.mcpl.gz");
  remove("trdata.mcpl");
  remove("trdata.mcpl.gz");
}

////////////////////////////////////////////////////////////////////////////////
// Userdata layouts

static void check_layout( const char * layout )
{
  mcpl_errstate_t es;
  es_reset(&es);
  uint32_t n = mcpl_userdata_layout_size_es(layout,&es);
  char what[512];
  snprintf(what,sizeof(what),"layout_size(\"%s\") = %u",
           layout?layout:"<NULL>",(unsigned)n);
  print_result(what,&es);
  if ( es_failed(&es) != ( n == 0 ) )
    test_fail("mcpl_userdata_layout_size_es: inconsistent return value");
}

static void check_offset( const char * layout, const char * name,
                          const char * type )
{
  mcpl_errstate_t es;
  es_reset(&es);
  uint32_t o = mcpl_userdata_offset_es(layout,name,type,&es);
  char what[512];
  snprintf(what,sizeof(what),"offset(\"%s\",%s,%s) = %u",
           layout?layout:"<NULL>",name?name:"<NULL>",type?type:"<NULL>",
           (unsigned)o);
  print_result(what,&es);
  if ( es_failed(&es) != ( o == UINT32_MAX ) )
    test_fail("mcpl_userdata_offset_es: inconsistent return value");
}

static void test_layouts(void)
{
  printf("\n==> Userdata layouts:\n");
  const char * layouts[] = {
    "a:int8", "a:uint8,b:int16,c:uint16,d:int32,e:uint32,f:int64,g:uint64,"
    "h:float32,i:float64", "temp:float32,tags:uint8[3]", "x_1:float64[65535]",
    NULL, "", ",", "a:int8,", ",a:int8", "a", "a:", ":int8", "A:int8",
    "1a:int8", "a-b:int8", "a b:int8", "a:int9", "a:INT8", "a:int8,a:float32",
    "a:uint8[0]", "a:uint8[]", "a:uint8[3", "a:uint8[03]", "a:uint8[3]x",
    "a:uint8[x]", "a:uint8[65536]", "a:uint8[65535],b:uint8",
    "a:float64[8192]", "a:uint8[99999999999999999999]",
    "abcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcd:int8",
    "abcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcdefghijabcde:int8",
    /* units: */
    "a:float32:cm", "a:float64:MeV,b:float32:ms,c:float32:K,d:float32:deg",
    "a:float32[3]:cm", "a:float64:cm^2.MeV", "a:float64:MeV^-1",
    "a:float64:cm.ms^-1", "a:float64:cm^-9.MeV^9.ms.K^2.deg^-1", "a:int32:K",
    "a:float32:", "a:float32:m", "a:float32:CM", "a:float32:cm.cm",
    "a:float32:MeV.cm", "a:float32:cm^1", "a:float32:cm^0", "a:float32:cm^-0",
    "a:float32:cm^10", "a:float32:cm^", "a:float32:cm^-", "a:float32:cm.",
    "a:float32:.cm", "a:float32:cm..MeV", "a:float32:cm*MeV", "a:float32:cm/ms",
    "a:float32:cm:MeV", "a:float32[3:cm", "a:float32:cm[3]",
    /* (division, parentheses and "*", with hints): */
    "a:float32:MeV/cm", "a:float32:1/cm", "a:float32:(cm.MeV)^-1",
    "a:float32:cm^(-1)", "a:float32:cm^-1/ms",
  };
  for ( size_t i = 0; i < sizeof(layouts)/sizeof(layouts[0]); ++i )
    check_layout(layouts[i]);
  const char * l = "temp:float32,origin:int32,tags:uint8[3],pos:float64[3]";
  check_offset(l,"temp","float32");
  check_offset(l,"origin","int32");
  check_offset(l,"tags","uint8[3]");
  check_offset(l,"pos","float64[3]");
  check_offset(l,"tags","uint8");
  check_offset(l,"pos","float32[3]");
  check_offset(l,"nosuchfield","int32");
  check_offset(l,"tem","float32");
  check_offset(l,NULL,"float32");
  check_offset(l,"temp",NULL);
  check_offset("a:int9","a","int9");
  /* the types of fields with units are without the units: */
  check_offset("temp:float32:K,dir:float32[3]:cm","temp","float32");
  check_offset("temp:float32:K,dir:float32[3]:cm","dir","float32[3]");
  check_offset("temp:float32:K,dir:float32[3]:cm","temp","float32:K");
  check_offset(NULL,"a","int8");
}

////////////////////////////////////////////////////////////////////////////////
// Print handlers

static char ctx_collected[4096];

static void ctx_print_handler( const char * msg, void * ctx )
{
  if ( ctx != (void*)ctx_collected )
    test_fail("print handler called with wrong context");
  size_t n = strlen(ctx_collected);
  size_t nmsg = strlen(msg);
  if ( nmsg > sizeof(ctx_collected) - 1 - n )
    nmsg = sizeof(ctx_collected) - 1 - n;
  memcpy(ctx_collected+n,msg,nmsg);
  ctx_collected[n+nmsg] = '\0';
}

static void plain_print_handler( const char * msg )
{
  printf("  [plain handler] %s",msg);
}

static void test_print_handlers(void)
{
  printf("\n==> Print handlers:\n");
  buffer_t a = file_load("a.mcpl");
  uint64_t zero = 0;
  save_modified("x.mcpl",&a,a.size,8,&zero,8);//gives a warning when opened
  free(a.data);
  ctx_collected[0] = '\0';
  mcpl_set_print_handler_ctx(ctx_print_handler,(void*)ctx_collected);
  mcpl_close_file(mcpl_open_file("x.mcpl"));
  mcpl_set_print_handler(plain_print_handler);//replaces the ctx handler
  mcpl_close_file(mcpl_open_file("x.mcpl"));
  mcpl_set_print_handler_ctx(ctx_print_handler,(void*)ctx_collected);
  mcpl_set_print_handler_ctx(NULL,(void*)ctx_collected);//default handler
  mcpl_close_file(mcpl_open_file("x.mcpl"));
  printf("  collected by the handler with context: %s",ctx_collected);
  remove("x.mcpl");
}

////////////////////////////////////////////////////////////////////////////////

int main( int argc, char ** argv )
{
  (void)argc;
  (void)argv;
  printf("sizeof(mcpl_errstate_t) = %u, codes: %i %i %i\n",
         (unsigned)sizeof(mcpl_errstate_t),MCPL_ERROR_RUNTIME,MCPL_ERROR_IO,
         MCPL_ERROR_MEMORY);
  create_file_a();
  create_file_b();
  create_file_c();
  create_file_d();
  test_layouts();
  test_reading_ok();
  test_header_errors();
  test_invalid_handle();
  test_open_errors();
  test_truncated_data();
  test_print_handlers();
  remove("a.mcpl");
  remove("b.mcpl");
  remove("c.mcpl");
  remove("d.mcpl");
  return 0;
}
