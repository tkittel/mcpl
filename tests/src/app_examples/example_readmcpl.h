
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

// A small standalone example of how one might read particles from an MCPL
// file into a C programme.

#include "mcpl.h"
#include <stdio.h>
#include <stdlib.h>
#include <memory.h>

int main(int argc,char**argv) {

  if (argc!=2) {
    printf("Please supply input filename\n");
    return 1;
  }

  const char * filename = argv[1];

  //Open the file:
  mcpl_file_t f = mcpl_open_file(filename);

  //For fun, access and print a bit of the info found in the header (see mcpl.h
  //for more):

  printf("Opened MCPL file produced with %s\n",mcpl_hdr_srcname(f));
  unsigned i;
  for (i = 0; i < mcpl_hdr_ncomments(f); ++i)
    printf( "file had comment: '%s'\n", mcpl_hdr_comment(f,i) );
  printf( "File contains %llu particles\n",
          (unsigned long long)mcpl_hdr_nparticles(f) );

  //Now, loop over particles and print some info:

  const mcpl_particle_t* p;
  while ( 1 ) {
    p = mcpl_read(f);
    if ( !p )
      break;

    //print some info (see the mcpl_particle_t struct in mcpl.h for all fields):
    printf( "  found particle with "
            "pdgcode %i and time-stamp %g ms with weight %g\n",
            p->pdgcode, p->time, p->weight );

  }

  mcpl_close_file(f);
  return 0;
}
