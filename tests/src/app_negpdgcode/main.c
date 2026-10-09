
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

#include "mcpl.h"
#include <stdio.h>

//Negative PDG codes (antiparticles) are stored as unsigned 32 bit integers in
//the file, so check that they are read back correctly.

void mcpltests_write( const char * filename, int universal )
{
  mcpl_outfile_t f = mcpl_create_outfile(filename);
  mcpl_hdr_set_srcname(f,"mcpltests_negpdgcode");
  if (universal)
    mcpl_enable_universal_pdgcode(f,-2112);
  mcpl_particle_t * p = mcpl_get_empty_particle(f);
  const int pdgcodes[3] = { -11, 2112, -2147483647 - 1 };
  for ( int i = 0; i < 3; ++i ) {
    p->pdgcode = universal ? -2112 : pdgcodes[i];
    p->ekin = 1.0 + i;
    p->direction[2] = 1.0;
    p->weight = 1.0;
    mcpl_add_particle(f,p);
  }
  mcpl_close_outfile(f);
}

void mcpltests_read( const char * filename )
{
  mcpl_file_t f = mcpl_open_file(filename);
  printf("%s: universal pdgcode %li\n",filename,
         (long)mcpl_hdr_universal_pdgcode(f));
  const mcpl_particle_t * p;
  while ( ( p = mcpl_read(f) ) )
    printf("  pdgcode %li\n",(long)p->pdgcode);
  mcpl_close_file(f);
}

int main(int argc,char**argv) {
  (void)argc;
  (void)argv;
  mcpltests_write("universal.mcpl",1);
  mcpltests_read("universal.mcpl");
  mcpltests_write("perparticle.mcpl",0);
  mcpltests_read("perparticle.mcpl");
  return 0;
}
