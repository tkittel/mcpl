
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

// A small standalone example of how one might output an MCPL file from a C
// programme.


#include "mcpl.h"
#include <stdio.h>
#include <stdlib.h>
#include <memory.h>


double randuniform(double a, double b)
{
  return a + rand() * (b-a) / RAND_MAX;
}

int main(int argc,char**argv) {

  if (argc!=2) {
    printf("Please supply output filename\n");
    return 1;
  }

  const char * filename = argv[1];

  // Initialisation, create output file handle, embed name of source application
  // in the header and declare that this is a neutron-only file. Note that an
  // ".mcpl" extension will be added to the filename if it doesn't have it
  // already, and that files with names ending with ".mcpl.gz" are gzipped when
  // closed, resulting in smaller files (which can also be read directly by
  // MCPL):

  mcpl_outfile_t f = mcpl_create_outfile(filename);
  mcpl_hdr_set_srcname(f,"my_cool_program_name");

  // By default, floating point numbers will be stored in single precision and
  // neither polarisation nor user-flags will be stored in the file. These
  // defaults can be modified by one or more of the following calls (perhaps
  // they could be options to your McStas component):
  //
  //    mcpl_enable_userflags(f);
  //    mcpl_enable_polarisation(f);
  //    mcpl_enable_doubleprec(f);

  // If all particles will be of the same type, optimise the file a bit by:
  //
  //    mcpl_enable_universal_pdgcode(f,2112);//all particles are neutrons

  //We can add comments (strings) to the header. It is always a good idea to add
  //comments explaining things like coordinate system, contents of user-flags
  //(if any), and what the values in the "weight" field means exactly.:
  mcpl_hdr_add_comment(f,"Some comment.");
  mcpl_hdr_add_comment(f,"Another comment.");

  //It is also possible to add binary data with mcpl_hdr_add_data, if desired
  //(can be indexed by strings). So for instance, custom persistified
  //configuration meta-data could be added (or perhaps just a text file used by
  //configuration by your programme, if appropriate).

  //Allocate the particle structure we will use during the simulation loop
  //to register particle data in the output file:
  mcpl_particle_t * particle = mcpl_get_empty_particle(f);

  //Simulation loop, modify the particle struct and add to the file as many
  //times as needed (here everything will simply be filled with some stupid
  //random numbers):
  int i;
  for (i = 0; i < 100; ++i) {
    //particle type:
    if (rand()%2)
      particle->pdgcode = 2112;//50% neutrons
    else
      particle->pdgcode = 22;//50% gammas
    //position in centimeters:
    particle->position[0] = randuniform(-100,100);
    particle->position[1] = randuniform(-100,100);
    particle->position[2] = randuniform(-100,100);
    //kinetic energy in MeV:
    particle->ekin = randuniform(0.001,10);
    //momentum direction (unit vector):
    particle->direction[0] = 0.0;
    particle->direction[1] = 0;
    particle->direction[2] = 1.0;
    //time in milliseconds:
    particle->time = randuniform(0,100);
    //weight in unspecified units:
    particle->weight = randuniform(0.01,10);
    //modify userflags and polarisation (what units?) as well, if enabled.

    //Finally, add the particle to the file:
    mcpl_add_particle(f,particle);
  }

  //At the end, remember to properly close the output file (and cleanup memory):
  mcpl_close_outfile(f);

  return 0;
}

