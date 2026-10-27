
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

#include "mcpltestmodutils.h"

//Test functions for per-particle userdata (used by tests/scripts/userdata.py).

MCPLTEST_CTYPE_DICTIONARY
{
  return
    "void mcpltest_ud_layout( const char * );"
    "void mcpltest_ud_offset( const char *, const char *, const char * );"
    "void mcpltest_ud_write( const char *, const char *, unsigned, unsigned );"
    "void mcpltest_ud_read( const char * );"
    "void mcpltest_ud_transfer( const char *, const char *, const char *,"
    "                           unsigned );"
    "void mcpltest_ud_transfer_meta_with_userdata( const char *,"
    "                                              const char *,"
    "                                              const char * );"
    "void mcpltest_ud_merge( const char *, const char *, const char * );"
    "void mcpltest_ud_forcemerge( const char *, const char *, const char * );"
    "void mcpltest_ud_merge_inplace( const char *, const char * );"
    "int mcpltest_ud_can_merge( const char *, const char * );"
    "void mcpltest_ud_dump( const char * );"
    "void mcpltest_ud_text( const char *, const char * );"
    "void mcpltest_ud_misuse( unsigned );"
    ;
}

MCPLTEST_CTYPES void mcpltest_ud_layout( const char * layout )
{
  printf("layout \"%s\" has size %u\n", layout,
         (unsigned)mcpl_userdata_layout_size(layout));
  fflush(stdout);
}

MCPLTEST_CTYPES void mcpltest_ud_offset( const char * layout,
                                         const char * name,
                                         const char * type )
{
  //(name "<NULL>" for passing NULL):
  const char * n = strcmp(name,"<NULL>")==0 ? NULL : name;
  printf("offset of %s (%s) in \"%s\" is %u\n", name, type, layout,
         (unsigned)mcpl_userdata_offset(layout,n,type));
  fflush(stdout);
}

//The layout used for fields with known types in the tests:
static const char * mcpltest_ud_stdlayout = ( "temp:float32,origin:int32,"
                                              "tags:uint8[3],big:float64,"
                                              "id:uint64,s:int16" );

static int mcpltest_ud_is_std( const char * layout )
{
  return layout && strcmp(layout,mcpltest_ud_stdlayout)==0;
}

//Write file with nparticles particles. Layout "<NONE>" means no userdata,
//"<STD>" the standard layout above, and otherwise the bytes are set to
//(i*7+j)%256. Options: bit 0 for double precision, bit 1 for polarisation,
//bit 2 to add every other particle with NULL userdata (i.e. zeros):
MCPLTEST_CTYPES void mcpltest_ud_write( const char * filename,
                                        const char * layout,
                                        unsigned nparticles,
                                        unsigned options )
{
  if ( strcmp(layout,"<STD>")==0 )
    layout = mcpltest_ud_stdlayout;
  mcpl_outfile_t f = mcpl_create_outfile( filename );
  mcpl_hdr_set_srcname(f,"mcpltest_ud_write");
  if ( options & 1 )
    mcpl_enable_doubleprec(f);
  if ( options & 2 )
    mcpl_enable_polarisation(f);
  uint32_t udsize = 0;
  if ( strcmp(layout,"<NONE>")!=0 ) {
    mcpl_enable_userdata(f,layout);
    mcpl_enable_userdata(f,layout);//calling again with same layout is OK
    udsize = mcpl_userdata_layout_size(layout);
  }
  uint8_t * ud = (uint8_t*)malloc( udsize ? udsize : 1 );
  mcpl_particle_t * p = mcpl_get_empty_particle(f);
  for ( unsigned i = 0; i < nparticles; ++i ) {
    p->position[0] = 1.0 + i;
    p->direction[2] = 1.0;
    p->ekin = 0.5 * ( i + 1 );
    p->pdgcode = 2112;
    p->weight = 1.0;
    p->polarisation[1] = 0.5;
    if ( mcpltest_ud_is_std(layout) ) {
      mcpl_userdata_set_float32(ud,mcpl_userdata_offset(layout,"temp","float32"),
                                (float)(293.15+i));
      mcpl_userdata_set_int32(ud,mcpl_userdata_offset(layout,"origin","int32"),
                              -1000*(int32_t)i);
      uint32_t otags = mcpl_userdata_offset(layout,"tags","uint8[3]");
      for ( unsigned j = 0; j < 3; ++j )
        mcpl_userdata_set_uint8(ud,otags+j,(uint8_t)(10*i+j));
      mcpl_userdata_set_float64(ud,mcpl_userdata_offset(layout,"big","float64"),
                                1.0e300*(i+1));
      mcpl_userdata_set_uint64(ud,mcpl_userdata_offset(layout,"id","uint64"),
                               UINT64_MAX-i);
      mcpl_userdata_set_int16(ud,mcpl_userdata_offset(layout,"s","int16"),
                              (int16_t)(-32768+(int)i));
    } else {
      for ( uint32_t j = 0; j < udsize; ++j )
        ud[j] = (uint8_t)((i*7+j)%256);
    }
    if ( !udsize )
      mcpl_add_particle(f,p);
    else
      mcpl_add_particle_with_userdata(f,p,( ( options & 4 ) && i % 2 ) ? NULL : ud);
  }
  free(ud);
  mcpl_close_outfile(f);
}

MCPLTEST_CTYPES void mcpltest_ud_read( const char * filename )
{
  mcpl_file_t f = mcpl_open_file(filename);
  const char * layout = mcpl_hdr_userdata_layout(f);
  uint32_t udsize = mcpl_hdr_userdata_size(f);
  printf("%s: format version %u, userdata layout %s%s%s, size %u,"
         " particle size %i\n", filename, mcpl_hdr_version(f),
         layout?"\"":"", layout?layout:"NULL", layout?"\"":"",
         (unsigned)udsize, mcpl_hdr_particle_size(f));
  if ( mcpl_last_read_userdata(f) )
    printf("ERROR: userdata before first read\n");
  const uint8_t * ud;
  const mcpl_particle_t * p;
  while ( ( p = mcpl_read_with_userdata(f,&ud) ) ) {
    printf("  particle %i x=%g ekin=%g:", (int)(mcpl_currentposition(f)-1),
           p->position[0], p->ekin);
    if ( ud != mcpl_last_read_userdata(f) )
      printf(" ERROR: inconsistent pointers");
    if ( !ud ) {
      printf(" no userdata\n");
      continue;
    }
    if ( mcpltest_ud_is_std(layout) ) {
      uint32_t otags = mcpl_userdata_offset(layout,"tags","uint8[3]");
      printf(" temp=%.2f origin=%li tags=%u,%u,%u big=%g id=%llu s=%i\n",
             (double)mcpl_userdata_get_float32(ud,mcpl_userdata_offset(layout,"temp","float32")),
             (long)mcpl_userdata_get_int32(ud,mcpl_userdata_offset(layout,"origin","int32")),
             (unsigned)mcpl_userdata_get_uint8(ud,otags),
             (unsigned)mcpl_userdata_get_uint8(ud,otags+1),
             (unsigned)mcpl_userdata_get_uint8(ud,otags+2),
             mcpl_userdata_get_float64(ud,mcpl_userdata_offset(layout,"big","float64")),
             (unsigned long long)mcpl_userdata_get_uint64(ud,mcpl_userdata_offset(layout,"id","uint64")),
             (int)mcpl_userdata_get_int16(ud,mcpl_userdata_offset(layout,"s","int16")));
    } else {
      printf(" ");
      for ( uint32_t j = 0; j < udsize && j < 12; ++j )
        printf("%02x",(unsigned)ud[j]);
      printf("%s\n", udsize > 12 ? "..." : "");
    }
  }
  if ( mcpl_last_read_userdata(f) )
    printf("ERROR: userdata after EOF\n");
  if ( mcpl_hdr_nparticles(f) ) {
    mcpl_seek(f,0);
    if ( mcpl_last_read_userdata(f) )
      printf("ERROR: userdata after seek\n");
    mcpl_read(f);
    if ( udsize && !mcpl_last_read_userdata(f) )
      printf("ERROR: no userdata after mcpl_read\n");
    mcpl_skipforward(f,1);
    if ( mcpl_last_read_userdata(f) )
      printf("ERROR: userdata after skipforward\n");
    mcpl_rewind(f);
    if ( mcpl_last_read_userdata(f) )
      printf("ERROR: userdata after rewind\n");
  }
  mcpl_close_file(f);
  fflush(stdout);
}

//Transfer all particles with mcpl_transfer_last_read_particle into a new
//file. Layout "<META>" means using mcpl_transfer_metadata, "<NONE>" no
//userdata, and otherwise the given layout. Options as in mcpltest_ud_write:
MCPLTEST_CTYPES void mcpltest_ud_transfer( const char * src,
                                           const char * dst,
                                           const char * layout,
                                           unsigned options )
{
  mcpl_file_t fi = mcpl_open_file(src);
  mcpl_outfile_t fo = mcpl_create_outfile(dst);
  if ( strcmp(layout,"<META>")==0 ) {
    mcpl_transfer_metadata(fi,fo);
  } else {
    if ( strcmp(layout,"<STD>")==0 )
      layout = mcpltest_ud_stdlayout;
    if ( strcmp(layout,"<NONE>")!=0 )
      mcpl_enable_userdata(fo,layout);
  }
  if ( options & 1 )
    mcpl_enable_doubleprec(fo);
  if ( options & 2 )
    mcpl_enable_polarisation(fo);
  while ( mcpl_read(fi) )
    mcpl_transfer_last_read_particle(fi,fo);
  mcpl_close_file(fi);
  mcpl_close_outfile(fo);
}

MCPLTEST_CTYPES void mcpltest_ud_transfer_meta_with_userdata( const char * src,
                                                             const char * dst,
                                                             const char * layout )
{
  //Header of src, with userdata (and no particles):
  mcpl_file_t fi = mcpl_open_file(src);
  mcpl_outfile_t fo = mcpl_create_outfile(dst);
  mcpl_transfer_metadata(fi,fo);
  mcpl_enable_userdata(fo,layout);
  mcpl_close_file(fi);
  mcpl_close_outfile(fo);
  printf("Wrote %s with the header of %s and userdata\n",dst,src);
  fflush(stdout);
}

MCPLTEST_CTYPES void mcpltest_ud_merge( const char * out,
                                        const char * f1, const char * f2 )
{
  const char * files[2] = { f1, f2 };
  mcpl_close_outfile( mcpl_merge_files(out,2,files) );
}

MCPLTEST_CTYPES void mcpltest_ud_forcemerge( const char * out,
                                             const char * f1, const char * f2 )
{
  const char * files[2] = { f1, f2 };
  mcpl_close_outfile( mcpl_forcemerge_files(out,2,files,0) );
}

MCPLTEST_CTYPES void mcpltest_ud_merge_inplace( const char * f1,
                                                const char * f2 )
{
  mcpl_merge_inplace(f1,f2);
}

MCPLTEST_CTYPES int mcpltest_ud_can_merge( const char * f1, const char * f2 )
{
  return mcpl_can_merge(f1,f2);
}

MCPLTEST_CTYPES void mcpltest_ud_dump( const char * filename )
{
  mcpl_dump(filename,0,0,0);
}

MCPLTEST_CTYPES void mcpltest_ud_text( const char * filename,
                                       const char * outfile )
{
  char a0[] = "mcpltool";
  char a1[] = "--text";
  char * argv[4] = { a0, a1, (char*)filename, (char*)outfile };
  mcpl_tool(4,argv);
}

//Wrong usage which must give errors:
MCPLTEST_CTYPES void mcpltest_ud_misuse( unsigned icase )
{
  mcpl_outfile_t f = mcpl_create_outfile("misuse.mcpl");
  mcpl_particle_t * p = mcpl_get_empty_particle(f);
  p->direction[2] = 1.0;
  uint8_t ud[4] = { 1, 2, 3, 4 };
  if ( icase == 0 ) {
    //userdata for a file without userdata:
    mcpl_add_particle_with_userdata(f,p,ud);
  } else if ( icase == 1 ) {
    //enabling after the first particle:
    mcpl_add_particle(f,p);
    mcpl_enable_userdata(f,"p:int32");
  } else if ( icase == 2 ) {
    //enabling twice with different layouts:
    mcpl_enable_userdata(f,"p:int32");
    mcpl_enable_userdata(f,"p:float32");
  } else if ( icase == 3 ) {
    //NULL layout:
    mcpl_enable_userdata(f,NULL);
  } else if ( icase == 4 ) {
    //mcpl_add_particle for a file with userdata:
    mcpl_enable_userdata(f,"p:int32");
    mcpl_add_particle(f,p);
  } else {
    //NULL userdata is allowed (zeros):
    mcpl_enable_userdata(f,"p:int32");
    mcpl_add_particle_with_userdata(f,p,NULL);
    mcpl_close_outfile(f);
    mcpl_file_t fi = mcpl_open_file("misuse.mcpl");
    const uint8_t * rd;
    mcpl_read_with_userdata(fi,&rd);
    printf("NULL userdata gives p=%li\n",
           (long)mcpl_userdata_get_int32(rd,mcpl_userdata_offset(
                                           mcpl_hdr_userdata_layout(fi),
                                           "p","int32")));
    fflush(stdout);
    mcpl_close_file(fi);
    return;
  }
  mcpl_close_outfile(f);
}
