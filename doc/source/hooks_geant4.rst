*********************
MCPL hooks for Geant4
*********************

The interface between MCPL and `Geant4 <http://geant4.cern.ch/>`__ consists of
two classes,
`G4MCPLGenerator <https://github.com/mctools/mcpl-geant4/blob/HEAD/src/mcpl_geant4/cmake/include/MCPLGeant4/G4MCPLGenerator.hh>`__
and
`G4MCPLWriter <https://github.com/mctools/mcpl-geant4/blob/HEAD/src/mcpl_geant4/cmake/include/MCPLGeant4/G4MCPLWriter.hh>`__,
residing in a dedicated ``mcpl-geant4`` package, which users can use to either
generate primary events from the particles in an existing MCPL file (1 particle
per event), or to capture the particle state of particles entering one or more
specified volumes in the simulation geometry and write them to a new MCPL file.
A detailed description of the classes as well as how to use them is given in
`the MCPL paper (section
3.1) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.3.1>`__, and
the present page will merely provide examples for the most basic usage as well
as a brief discussion of how to actually integrate the MCPL code in your Geant4
setup.

Note that users of the
`simple-build-dgcode <https://mctools.github.io/simplebuild-dgcode>`__
framework have more powerful Geant4-MCPL hooks available out of the box, and
they should refer to the `relevant
documentation <https://mctools.github.io/simplebuild-dgcode/mcpl.html>`__
rather than the present page.

.. _hooks_geant4-basic-usage-examples:

Basic usage examples
====================

.. _hooks_geant4-using-mcpl-files-as-simulation-input-via-g4mcplgenerator:

Using MCPL files as simulation input via G4MCPLGenerator
--------------------------------------------------------

The ``G4MCPLGenerator`` class is a subclass of Geant4's
``G4VUserPrimaryGeneratorAction`` interface class, and can be activated in the
usual manner for such classes. The name of the MCPL file to be used as input
must be provided in the form of a string to the constructor
of\ ``G4MCPLGenerator``. Additionally, if the MCPL file runs out of particles
(which it will eventually if Geant4 is requested to simulate more events than
there are particles in the MCPL file), the ``G4MCPLGenerator`` will graciously
request the ``G4RunManager`` to abort the simulation. Thus, a convenient way in
which to use the entire input file for simulation is to launch the simulation
with a very high number of events requested, as is shown in the following
example:

.. code:: cpp

   #include "MCPLGeant4/G4MCPLGenerator.hh"
   #include "G4RunManager.hh"
   #include <limits>

   //Not shown here: Code defining MyGeometry and
   //MyPhysicsList.

   int main( int argc, char** argv ) {

     G4RunManager runManager;
     G4RunManager& rm = runManager;
     rm.SetUserInitialization(new MyGeometry);
     rm.SetUserInitialization(new MyPhysicsList);
     rm.SetUserAction(
       new G4MCPLGenerator("myfile.mcpl") );
     rm.Initialize();
     rm.BeamOn(std::numeric_limits<G4int>::max());

     return 0;
   }

For advanced use-cases, it is possible to fine-tune the way the particles from
the input MCPL file are used. For instance, it is possible to apply a filter in
order to ignore some of the particles, or to modify their properties (e.g.
performing coordinate transformations, time-shifting or re-weighting). In order
to do so, the user must sub-class the ``G4MCPLGenerator`` and overwrite one or
two methods as relevant. Refer to the detailed instructions in `the MCPL paper
(section
3.1) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.3.1>`__ for
more information.

.. _hooks_geant4-creating-mcpl-files-from-simulations-via-g4mcplwriter:

Creating MCPL files from simulations via G4MCPLWriter
-----------------------------------------------------

The ``G4MCPLWriter`` class is a subclass of Geant4's ``G4VSensitiveDetector``
interface class, and can be activated in the usual manner for such classes. In
the default configuration it "consumes" all particles which, during a
simulation, enter any geometrical volume(s) to which it is attached by the user
and stores them into the MCPL file which was specified as an argument to its
constructor. It also asks Geant4 to end further simulation of those particles
("killing" them), in order to avoid potential issues of double-counting.

It is of course also possible to add meta-data to, or otherwise modify the
settings of, the newly created MCPL file. The following code sample illustrates
the typical usage pattern (``alogvol`` is here a logical volume in Geant4,
chosen by the user according to their needs):

.. code:: cpp

   #include "MCPLGeant4/G4MCPLWriter.hh"

   //...

   //Provide output filename when creating
   //G4MCPLWriter instance:
   G4MCPLWriter * mcplwriter
     = new G4MCPLWriter("myoutput.mcpl");

   //Optional calls which add meta-data or change
   //flags:
   mcplwriter->AddComment("Some useful description");
   mcplwriter->AddData( ... );
   mcplwriter->EnableDoublePrecision();
   mcplwriter->EnablePolarisation();
   mcplwriter->EnableUniversalWeight(1.0);

   //Register with G4SDManager and on one or more
   //logical volumes to activate:
   auto sdm = G4SDManager::GetSDMpointer();
   sdm->AddNewDetector(mcplwriter);
   alogvol->SetSensitiveDetector(mcplwriter);

For advanced use-cases, it is possible to fine-tune the way the particles are
captured and whether they are "killed" or merely recorded, and it is also
possible to fill custom information into the MCPL *userflags* in the resulting
file. In order to do either, the user must sub-class the ``G4MCPLWriter`` and
overwrite the relevant method(s). Refer to the detailed instructions in `the
MCPL paper (section
3.1) <https://mctools.github.io/mcpl/mcpl.pdf#nameddest=subsection.3.1>`__ for
more information.

.. _hooks_geant4-integrating-mcpl-in-a-given-geant4-setup:

Integrating MCPL in a given Geant4 setup
========================================

Note that in order to actually install and build with the ``G4MCPLGenerator``
and ``G4MCPLWriter`` classes, the simplest approach is to first install MCPL
and Geant4, and then ``pip install mcpl-geant4``. Finally, follow the
instructions and look at the examples provided at
https://github.com/mctools/mcpl-geant4.
