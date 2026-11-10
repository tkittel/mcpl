
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

// A small standalone example of how to write and read custom per-particle
// data ("userdata") with the MCPL C API. Files with userdata are written in
// the MCPL-4 format, which needs MCPL release 3.0.0 or later.

#include "mcpl.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc,char**argv) {

  if (argc!=2) {
    printf("Please supply output filename\n");
    return 1;
  }

  const char * filename = argv[1];

  //////////////////////////////////////////////////////////////////////////////
  // Writing a file with userdata                                             //
  //////////////////////////////////////////////////////////////////////////////

  mcpl_outfile_t fout = mcpl_create_outfile(filename);
  mcpl_hdr_set_srcname(fout,"my_cool_program_name");
  mcpl_enable_universal_pdgcode(fout,2112);//all particles are neutrons

  // The userdata of each particle is described by a layout: a list of named
  // fields with types int8, uint8, int16, uint16, int32, uint32, int64, uint64,
  // float32, or float64, or arrays of them like "origin:float32[3]", optionally
  // with units like "temp:float32:K". Here each particle gets a temperature,
  // the number of scatterings it underwent, the identifier of the volume it was
  // last in, and its initial position. The layout is stored in the file header,
  // so it is always known when reading the file. As usual, it is a good idea to
  // explain the fields in a comment:
  const char * layout = ( "temp:float32:K,nscat:uint32,volume:int32,"
                          "origin:float32[3]:cm" );
  mcpl_enable_userdata(fout,layout);
  mcpl_hdr_add_comment(fout,"Userdata: temp is the temperature at the last"
                       " scattering, nscat the number of scatterings, volume"
                       " the identifier of the last volume, and origin the"
                       " initial position.");

  // Offsets of the fields in the userdata bytes, looked up once. The type is
  // checked against the layout, so mistakes are caught early:
  uint32_t o_temp = mcpl_userdata_offset(layout,"temp","float32");
  uint32_t o_nscat = mcpl_userdata_offset(layout,"nscat","uint32");
  uint32_t o_volume = mcpl_userdata_offset(layout,"volume","int32");
  // (for array fields, the type includes the size, and element k of the array
  // is at the offset of the field plus k times the size of the type, which
  // for float32 is sizeof(float)):
  uint32_t o_origin = mcpl_userdata_offset(layout,"origin","float32[3]");
  const uint32_t fsize = (uint32_t)sizeof(float);

  // Buffer for the userdata of one particle (mcpl_userdata_layout_size gives
  // the number of bytes, here 24):
  uint8_t * userdata = (uint8_t*)malloc( mcpl_userdata_layout_size(layout) );

  mcpl_particle_t * particle = mcpl_get_empty_particle(fout);

  int i;
  for ( i = 0; i < 1000; ++i ) {
    // Fill the usual particle fields (here just some numbers):
    particle->position[0] = 0.1 * i;
    particle->position[1] = 0.0;
    particle->position[2] = 0.0;
    particle->direction[0] = 0.0;
    particle->direction[1] = 0.0;
    particle->direction[2] = 1.0;
    particle->ekin = 0.025e-6 * ( 1 + i % 10 );//MeV
    particle->time = 0.0;
    particle->weight = 1.0;

    // Fill the userdata with the helper functions for the types in the layout:
    mcpl_userdata_set_float32( userdata, o_temp,
                               293.15f + 0.5f * (float)( i % 7 ) );
    mcpl_userdata_set_uint32( userdata, o_nscat, (uint32_t)( i % 4 ) );
    mcpl_userdata_set_int32( userdata, o_volume, ( i % 3 ) ? 17 : -1 );
    uint32_t k;
    for ( k = 0; k < 3; ++k )
      mcpl_userdata_set_float32( userdata, o_origin + k * fsize,
                                 0.5f * (float)k * (float)i );

    // In files with userdata, particles are added together with their userdata
    // (using mcpl_add_particle would be an error, and NULL instead of the
    // userdata gives a particle with all userdata bytes zero):
    mcpl_add_particle_with_userdata(fout,particle,userdata);
  }

  free(userdata);
  mcpl_close_outfile(fout);

  //////////////////////////////////////////////////////////////////////////////
  // Reading the file again                                                   //
  //////////////////////////////////////////////////////////////////////////////

  mcpl_file_t fin = mcpl_open_file(filename);

  // The layout is in the header (NULL for files without userdata), and the
  // field offsets are looked up in the same way as when writing. Note that
  // the layout is needed for the lookups, so code reading unknown files should
  // check it (or check mcpl_hdr_userdata_size(fin) for zero):
  const char * layout_in = mcpl_hdr_userdata_layout(fin);
  if ( !layout_in ) {
    printf("File has no userdata!\n");
    return 1;
  }
  printf("Userdata layout: %s (%u bytes per particle)\n",
         layout_in, (unsigned)mcpl_hdr_userdata_size(fin));
  o_temp = mcpl_userdata_offset(layout_in,"temp","float32");
  o_nscat = mcpl_userdata_offset(layout_in,"nscat","uint32");
  o_volume = mcpl_userdata_offset(layout_in,"volume","int32");
  o_origin = mcpl_userdata_offset(layout_in,"origin","float32[3]");

  // Loop over the particles, getting the userdata along with each particle:
  const mcpl_particle_t* p;
  const uint8_t * ud;
  double temp_sum = 0.0;
  unsigned long nscat_sum = 0;
  unsigned long n_escaped = 0;
  while ( ( p = mcpl_read_with_userdata(fin,&ud) ) ) {
    temp_sum += mcpl_userdata_get_float32(ud,o_temp);
    nscat_sum += mcpl_userdata_get_uint32(ud,o_nscat);
    if ( mcpl_userdata_get_int32(ud,o_volume) == -1 )
      ++n_escaped;
    if ( mcpl_currentposition(fin) <= 3 )
      printf("Particle %lu: ekin=%g MeV, temp=%g K, nscat=%u, volume=%i,"
             " origin=(%g,%g,%g)\n",
             (unsigned long)( mcpl_currentposition(fin) - 1 ), p->ekin,
             (double)mcpl_userdata_get_float32(ud,o_temp),
             (unsigned)mcpl_userdata_get_uint32(ud,o_nscat),
             (int)mcpl_userdata_get_int32(ud,o_volume),
             (double)mcpl_userdata_get_float32(ud,o_origin),
             (double)mcpl_userdata_get_float32(ud,o_origin+fsize),
             (double)mcpl_userdata_get_float32(ud,o_origin+2*fsize));
  }
  unsigned long n = (unsigned long)mcpl_hdr_nparticles(fin);
  printf("Read %lu particles: mean temp %g K, mean nscat %g, %lu escaped\n",
         n, temp_sum / (double)n, (double)nscat_sum / (double)n, n_escaped);

  mcpl_close_file(fin);
  return 0;
}
