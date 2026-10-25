
################################################################################
##                                                                            ##
##  This file is part of MCPL (see https://mctools.github.io/mcpl/)           ##
##                                                                            ##
##  Copyright 2015-2026 MCPL developers.                                      ##
##                                                                            ##
##  Licensed under the Apache License, Version 2.0 (the "License");           ##
##  you may not use this file except in compliance with the License.          ##
##  You may obtain a copy of the License at                                   ##
##                                                                            ##
##      http://www.apache.org/licenses/LICENSE-2.0                            ##
##                                                                            ##
##  Unless required by applicable law or agreed to in writing, software       ##
##  distributed under the License is distributed on an "AS IS" BASIS,         ##
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  ##
##  See the License for the specific language governing permissions and       ##
##  limitations under the License.                                            ##
##                                                                            ##
################################################################################

"""Descriptions of the names which can be used in expressions and histogram
strings (short ones for completion while typing, long ones for the help), and
the help texts of mcpltool -p help, -E help and -H help."""

__all__ = []


from ._particles import _particle_help

#(group, name, short description, long description):
_hints = (
    ( 'fields', 'x',
      'x coordinate of the position (a length)',
      'x coordinate of the position (a length: e.g. x > 2cm, or x/cm)' ),
    ( 'fields', 'y',
      'y coordinate of the position (a length)',
      'y coordinate of the position (a length: e.g. y > 2cm, or y/cm)' ),
    ( 'fields', 'z',
      'z coordinate of the position (a length)',
      'z coordinate of the position (a length: e.g. z > 2cm, or z/cm)' ),
    ( 'fields', 'ux',
      'x component of the direction (no unit)',
      'x component of the direction, a unit vector (no unit, from -1 to 1: e.g. ux > 0.9)' ),
    ( 'fields', 'uy',
      'y component of the direction (no unit)',
      'y component of the direction, a unit vector (no unit, from -1 to 1: e.g. uy > 0.9)' ),
    ( 'fields', 'uz',
      'z component of the direction (no unit)',
      'z component of the direction, a unit vector (no unit, from -1 to 1: e.g. uz > 0.9)' ),
    ( 'fields', 'polx',
      'x component of the polarisation (no unit)',
      'x component of the polarisation vector (no unit: e.g. polx > 0.5; zero in files without polarisation)' ),
    ( 'fields', 'poly',
      'y component of the polarisation (no unit)',
      'y component of the polarisation vector (no unit: e.g. poly > 0.5; zero in files without polarisation)' ),
    ( 'fields', 'polz',
      'z component of the polarisation (no unit)',
      'z component of the polarisation vector (no unit: e.g. polz > 0.5; zero in files without polarisation)' ),
    ( 'fields', 'ekin',
      'kinetic energy (an energy)',
      'kinetic energy (an energy: e.g. ekin > 2eV, or ekin/MeV)' ),
    ( 'fields', 'time',
      'time (a time)',
      'time (a time: e.g. time < 5ms, or time/ms)' ),
    ( 'fields', 'weight',
      'weight (no unit)',
      'statistical weight (no unit: e.g. weight > 0.1, or in edits weight *= 0.5)' ),
    ( 'fields', 'pdgcode',
      'particle type, as a PDG code (an integer)',
      'particle type, as a PDG code (an integer: e.g. pdgcode == 2112, or pdgcode == neutron)' ),
    ( 'fields', 'userflags',
      'user flags (an integer)',
      'user flags (a 32 bit integer: e.g. userflags & 0x10, or (userflags & 0xff) == 7)' ),
    ( 'vectors', 'pos',
      'position (x,y,z) (a vector of lengths)',
      'position, the vector (x,y,z) (lengths: e.g. abs(pos) < 1m)' ),
    ( 'vectors', 'dir',
      'direction (ux,uy,uz) (a unit vector)',
      'direction, the unit vector (ux,uy,uz) (no unit: e.g. dir.z > 0.9, the same as uz > 0.9)' ),
    ( 'vectors', 'pol',
      'polarisation (polx,poly,polz) (a vector)',
      'polarisation, the vector (polx,poly,polz) (no unit: e.g. abs(pol) > 0.5)' ),
    ( 'vectors', 'dot(v,w)',
      'dot product of vectors',
      'dot product of two vectors of the same size (e.g. dot(pos,dir) > 0cm)' ),
    ( 'vectors', 'cross(v,w)',
      'cross product of 3D vectors (a vector)',
      'cross product of two 3D vectors, a vector (e.g. abs(cross(pos,dir)) < 1cm, the distance of the line of flight from the origin)' ),
    ( 'vectors', 'angle(v,w)',
      'angle between vectors (an angle)',
      'angle between two vectors of the same size, precise also for small angles (e.g. angle(dir,(0,0,1)) < 1deg, or angle(pos,dir) for the angle between position and direction)' ),
    ( 'fields', 'fileidx',
      'position in the file (an integer)',
      'position of the particle in the file, counting from 0 (an integer, which can not be changed: e.g. mod(fileidx,10) == 0 for every tenth particle)' ),
    ( 'fields', 'wavelength',
      'wavelength (a length)',
      'wavelength, calculated from ekin, only for neutrons and gammas (a length: e.g. pdgcode == neutron and wavelength > 1.8Aa, or wavelength/Aa)' ),
    ( 'fields', 'userdata.NAME',
      'a field of the userdata (no unit)',
      'the field NAME of the userdata of the particles, in files with userdata (no unit, and it can not be changed: e.g. userdata.nscat > 2)' ),
    ( 'fields', 'userdata.NAME.at(INDEX)',
      'a value of an array in the userdata (no unit)',
      'the value with the INDEX (counting from 0) of the field NAME of the userdata, for fields with several values per particle (e.g. userdata.origdir.at(2) for the third value of a field origdir:float32[3])' ),
    ( 'constants', 'pi',
      'pi (no unit)',
      'pi = 3.14159... (no unit: e.g. atan2(y,x) > pi/2)' ),
    *( ( 'particles', name, f'PDG code {pdg}',
         f'the PDG code of {descr}, {pdg} (e.g. pdgcode == {name})' )
       for name, pdg, descr in _particle_help ),
    ( 'units', 'meV',
      'energy unit, 1e-9 MeV',
      'unit of energy: 1meV = 1e-9 MeV (e.g. ekin < 25meV)' ),
    ( 'units', 'eV',
      'energy unit, 1e-6 MeV',
      'unit of energy: 1eV = 1e-6 MeV (e.g. ekin > 1eV)' ),
    ( 'units', 'keV',
      'energy unit, 1e-3 MeV',
      'unit of energy: 1keV = 1e-3 MeV (e.g. ekin > 10keV)' ),
    ( 'units', 'MeV',
      'energy unit',
      'unit of energy, the one used in MCPL files (e.g. ekin/MeV)' ),
    ( 'units', 'GeV',
      'energy unit, 1000 MeV',
      'unit of energy: 1GeV = 1000 MeV (e.g. ekin > 1GeV)' ),
    ( 'units', 'TeV',
      'energy unit, 1e6 MeV',
      'unit of energy: 1TeV = 1e6 MeV (e.g. ekin > 1TeV)' ),
    ( 'units', 'ns',
      'time unit, 1e-6 ms',
      'unit of time: 1ns = 1e-6 ms (e.g. time < 100ns)' ),
    ( 'units', 'us',
      'time unit, 1e-3 ms (microsecond)',
      'unit of time, the microsecond: 1us = 1e-3 ms (e.g. time < 10us)' ),
    ( 'units', 'ms',
      'time unit',
      'unit of time, the one used in MCPL files (e.g. time/ms)' ),
    ( 'units', 's',
      'time unit, 1000 ms',
      'unit of time: 1s = 1000 ms (e.g. time < 1s)' ),
    ( 'units', 'Aa',
      'length unit, 1e-8 cm (angstrom)',
      'unit of length, the angstrom: 1Aa = 1e-8 cm (e.g. wavelength > 1.8Aa)' ),
    ( 'units', 'nm',
      'length unit, 1e-7 cm',
      'unit of length: 1nm = 1e-7 cm (e.g. wavelength > 0.18nm)' ),
    ( 'units', 'um',
      'length unit, 1e-4 cm (micrometre)',
      'unit of length, the micrometre: 1um = 1e-4 cm (e.g. abs(x) < 50um)' ),
    ( 'units', 'mm',
      'length unit, 0.1 cm',
      'unit of length: 1mm = 0.1 cm (e.g. abs(x) < 5mm)' ),
    ( 'units', 'cm',
      'length unit',
      'unit of length, the one used in MCPL files (e.g. x/cm)' ),
    ( 'units', 'm',
      'length unit, 100 cm',
      'unit of length: 1m = 100 cm (e.g. 0 < z < 1m)' ),
    ( 'units', 'km',
      'length unit, 1e5 cm',
      'unit of length: 1km = 1e5 cm (e.g. hypot(x,y,z) > 1km)' ),
    ( 'units', 'deg',
      'angle unit, pi/180',
      'unit of angle: 1deg = pi/180 (e.g. angle(dir,(0,0,1)) < 1deg, or rotate_z(90deg))' ),
    ( 'units', 'rad',
      'angle unit, 1',
      'unit of angle: 1rad = 1 (e.g. angle(dir,(0,0,1)) < 0.01rad)' ),
    ( 'functions', 'sqrt(a)',
      'square root',
      'square root, of a value without unit or with a squared unit (e.g. sqrt(x^2 + y^2) < 1cm; sqrt(ekin) is an error)' ),
    ( 'functions', 'abs(a)',
      'absolute value (same unit)',
      'absolute value (same unit as a: e.g. abs(x) < 5cm)' ),
    ( 'functions', 'round(a)',
      'nearest integer',
      'the nearest integer, of a value without units (e.g. round(x/cm))' ),
    ( 'functions', 'floor(a)',
      'round down to an integer',
      'round down to an integer, of a value without units (e.g. floor(time/ms))' ),
    ( 'functions', 'ceil(a)',
      'round up to an integer',
      'round up to an integer, of a value without units (e.g. ceil(ekin/MeV))' ),
    ( 'functions', 'min(a,b,...)',
      'smallest value (same unit)',
      'smallest of the values, which must have the same unit (e.g. min(x,y) > 0cm)' ),
    ( 'functions', 'max(a,b,...)',
      'largest value (same unit)',
      'largest of the values, which must have the same unit (e.g. max(abs(x),abs(y)) < 5cm)' ),
    ( 'functions', 'hypot(a,b,...)',
      'sqrt(a^2+b^2+...) (same unit)',
      'sqrt(a^2 + b^2 + ...), of values with the same unit (e.g. hypot(x,y) < 10cm, the distance from the z axis)' ),
    ( 'functions', 'mod(a,b)',
      'remainder of a/b (integers)',
      'remainder of the division a/b of integers without units (e.g. mod(userflags,4) == 1)' ),
    ( 'functions', 'clamp(v,low,high)',
      'v limited to [low,high] (same unit)',
      'v limited to the range from low to high, all with the same unit (e.g. in edits x = clamp(x, -5cm, 5cm))' ),
    ( 'functions', 'exp(a)',
      'exponential (a without unit)',
      'exponential function (a must have no unit: e.g. exp(-time/ms) > 0.5)' ),
    ( 'functions', 'log(a)',
      'natural logarithm (a without unit)',
      'natural logarithm (a must have no unit: e.g. log(ekin/MeV) > 0)' ),
    ( 'functions', 'log10(a)',
      'base 10 logarithm (a without unit)',
      'base 10 logarithm (a must have no unit: e.g. log10(ekin/eV) histogrammed with -H)' ),
    ( 'functions', 'sin(a)',
      'sine (a: an angle)',
      'sine (a is an angle, or a value without unit taken as radians: e.g. sin(30deg))' ),
    ( 'functions', 'cos(a)',
      'cosine (a: an angle)',
      'cosine (a is an angle, or a value without unit taken as radians: e.g. cos(30deg))' ),
    ( 'functions', 'tan(a)',
      'tangent (a: an angle)',
      'tangent (a is an angle, or a value without unit taken as radians: e.g. tan(30deg))' ),
    ( 'functions', 'asin(a)',
      'arcsine (an angle)',
      'arcsine, as an angle (a must have no unit: e.g. asin(uz) > 80deg)' ),
    ( 'functions', 'acos(a)',
      'arccosine (an angle)',
      'arccosine, as an angle (a must have no unit: e.g. acos(uz) < 10deg; for small angles angle(dir,(0,0,1)) is more precise)' ),
    ( 'functions', 'atan(a)',
      'arctangent (an angle)',
      'arctangent, as an angle (a must have no unit: e.g. atan(ux/uz) < 5deg)' ),
    ( 'functions', 'atan2(y,x)',
      'angle of the point (x,y) (an angle)',
      'angle of the point (x,y) from the x axis, from -180deg to 180deg (x and y with the same unit: e.g. atan2(y,x) > 0deg)' ),
    ( 'statements', 'swap(a,b)',
      'exchange two fields (same unit)',
      'exchange the values of two fields or variables with the same unit (e.g. swap(x,y))' ),
    ( 'statements', 'rotate_x(angle)',
      'rotate around the x axis',
      'rotate position, direction and polarisation around the x axis, counter-clockwise (e.g. rotate_x(90deg))' ),
    ( 'statements', 'rotate_y(angle)',
      'rotate around the y axis',
      'rotate position, direction and polarisation around the y axis, counter-clockwise (e.g. rotate_y(90deg))' ),
    ( 'statements', 'rotate_z(angle)',
      'rotate around the z axis',
      'rotate position, direction and polarisation around the z axis, counter-clockwise (e.g. rotate_z(90deg))' ),
    ( 'statements', 'rotate_around(axis,angle)',
      'rotate around the axis (a vector)',
      'rotate position, direction and polarisation around the axis (a vector) through the origin, counter-clockwise (e.g. rotate_around((1,1,0),30deg))' ),
    ( 'statements', 'rotate_frame(v,vout,u,uout)',
      'rotate v to vout and u to uout',
      'rotate position, direction and polarisation so that the direction of the vector v becomes that of vout, and u that of uout (e.g. rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0)) turns z into x and keeps y; the angles between v and u and between vout and uout must be the same)' ),
    ( 'histoptions', 'bins=N',
      'number of bins',
      'number of bins (default: chosen from the number of particles, e.g. bins=50)' ),
    ( 'histoptions', 'range=LOW:HIGH',
      'range of the histogram',
      'range of the histogram, with units if the expression has units (default: all values, e.g. range=0:10, or range=1meV:10MeV)' ),
    ( 'histoptions', 'xrange=LOW:HIGH',
      'range of x in 2D histograms',
      'range of the first expression of a 2D histogram (default: all values, e.g. xrange=-10cm:10cm)' ),
    ( 'histoptions', 'yrange=LOW:HIGH',
      'range of y in 2D histograms',
      'range of the second expression of a 2D histogram (default: all values, e.g. yrange=-10cm:10cm)' ),
    ( 'histoptions', 'logx=1|0|auto',
      'logarithmic x axis',
      'logarithmic binning and x axis (e.g. "ekin/MeV;logx", or logx=auto if suitable for the values)' ),
    ( 'histoptions', 'logy=1|0|auto',
      'logarithmic y axis',
      'logarithmic y axis (and bins, of 2D histograms), or scale of bar charts (logy=auto if suitable)' ),
    ( 'histoptions', 'logz=1|0',
      'logarithmic colour scale',
      'logarithmic colour scale of 2D histograms (the default, logz=0 gives a linear scale)' ),
    ( 'histoptions', 'equal=1|0',
      'equal scales of the axes',
      'the same scale on both axes of 2D histograms of expressions with the same units, so lengths on the axes compare (e.g. "x : y;equal")' ),
    ( 'histoptions', 'lethargy=1|0',
      'per unit lethargy (implies logx=1)',
      'divide by the bin widths in lethargy, so 1/E spectra are flat (implies logx=1)' ),
    ( 'histoptions', 'split=EXPR',
      'one curve per value of EXPR',
      'one curve for each value of the expression EXPR (e.g. split=pdgcode, or split=x > 0cm)' ),
    ( 'histoptions', 'only=COND',
      'only the particles of a condition',
      'only the particles for which the condition is true, on top of the pick (a condition as in picks, but only one, without variables: e.g. only=pdgcode == neutron)' ),
    ( 'histoptions', 'groups=N|auto',
      'number of curves of split',
      'the number of curves of split, the others are combined into one (default: auto, which is 8)' ),
    ( 'histoptions', 'bar=N|auto|0',
      'bars of distinct values',
      'a bar chart, with a bar for each value (which must be whole numbers), for the N largest ones, the others are combined into one (auto: 10, e.g. "pdgcode;bar" or "round(x/cm);bar")' ),
    ( 'histoptions', 'unweighted=1|0',
      'count particles',
      'count particles instead of summing their weights' ),
    ( 'histoptions', 'points=N|auto',
      'points of 3D plots',
      'the number of points of a 3D plot, a sample of the particles chosen with their weights (auto: 5000)' ),
    ( 'histoptions', 'print=1|0',
      'print contents instead of plotting',
      'print the contents of the histogram instead of plotting it' ),)

_group_titles = { 'histoptions' : 'Options',
                  'fields' : 'Fields of the particles',
                  'vectors' : 'Vectors',
                  'constants' : 'Constants',
                  'particles' : 'Particle names (PDG codes)',
                  'units' : 'Units',
                  'functions' : 'Functions',
                  'statements' : 'Statements' }

#Examples of the expressions (picks, edits and histogram strings), from simple
#to advanced, with what they do, for the help texts and the viewers:
#The examples of expressions, by topic, in groups of (title, the sentence
#before them or None, and the examples as (expression, what it does)):
examples = {
    'pick' : (
        ( 'Particle types', None, (
            ( 'pdgcode == neutron', 'Neutrons.' ),
            ( 'pdgcode in (neutron,gamma)', 'Neutrons and gammas.' ),
            ( 'abs(pdgcode) in (electron,muon)', 'Electrons, muons and their antiparticles.' ) ) ),
        ( 'Values and ranges', None, (
            ( 'ekin < 25meV', 'Kinetic energies below 25 meV.' ),
            ( '0cm < z < 10cm', 'Positions between z = 0 and 10 cm.' ),
            ( 'pdgcode == neutron and wavelength > 1.8Aa',
              ( 'Neutrons with wavelengths above 1.8 Aa (only neutrons and gammas have'
                ' wavelengths, so they are picked first).' ) ),
            ( 'not ( time > 10us or weight < 0.1 )', 'Early particles with large weights.' ) ) ),
        ( 'Variables', ( 'Values can be given names before the condition, as NAME = VALUE'
                         ' separated by ";", and then used in it:' ), (
            ( 'r = hypot(x,y); r > 2cm and r < 5cm',
              'Between 2 and 5 cm from the z axis, with the distance named r.' ),
            ( 'e = ekin/MeV; e > 1 and e < 10',
              'Energies from 1 to 10 MeV (e is a number, without a unit).' ) ) ),
        ( 'Vectors', ( 'The position, direction and polarisation are the vectors pos, dir and'
                       ' pol, vectors are written as (a,b,c), and abs(v), angle(v,w) and'
                       ' dot(v,w) give lengths, angles and dot products:' ), (
            ( 'angle(dir,(0,0,1)) < 1deg', 'Moving within 1 degree of the z axis.' ),
            ( 'd = pos - (0,0,1m); abs(d) < 10cm',
              'Within 10 cm of the point (0,0,1m), with the vector from it named d.' ),
            ( 'dot(dir,(1,0,0)) < 0', 'Moving towards negative x.' ) ) ),
        ( 'Bits, positions in the file and userdata', None, (
            ( '(userflags & 0xff) == 7', 'The lowest 8 bits of the user flags are 7.' ),
            ( 'mod(fileidx,10) == 0', 'Every tenth particle in the file.' ),
            ( 'userdata.nscat >= 2', 'The userdata field nscat is 2 or more (in files with userdata).' ),
            ( 'userdata.origdir.at(2) > 0.99',
              'The third value (counting from 0) of the userdata field origdir is above 0.99.' ) ) ),
    ),
    'edit' : (
        ( 'Changing values', None, (
            ( 'z += 1cm', 'Move the particles 1 cm along z.' ),
            ( 'weight *= 0.5', 'Halve the weights.' ),
            ( 'wavelength = 1.8Aa',
              'Give the particles the energy of a wavelength of 1.8 Aa (only for neutrons and gammas).' ),
            ( 'swap(x,y)', 'Swap the x and y coordinates.' ),
            ( 'time += hypot(x,y,z)/(2200m/s)', 'Add the time to fly to the origin at 2200 m/s.' ) ) ),
        ( 'Rotations', None, (
            ( 'rotate_y(90deg);x += 10cm', 'Rotate around the y axis, then move along x.' ),
            ( 'rotate_around((1,1,0),30deg)', 'Rotate by 30 degrees around the axis (1,1,0).' ),
            ( 'rotate_frame((0,0,1),(1,0,0),(0,1,0),(0,1,0))',
              'Turn the z axis into the x axis, keeping the y axis (v=z to vout=x, u=y to uout=y).' ) ) ),
        ( 'Variables', ( 'Values can be given names, as NAME = VALUE, and then used in the'
                         ' statements after it:' ), (
            ( 'r = hypot(x,y);x = r;y = 0cm', 'Move the particles onto the x axis, at the same distance.' ), ) ),
        ( 'Vectors', ( 'The position, direction and polarisation are the vectors pos, dir and'
                       ' pol, which can be changed as a whole:' ), (
            ( 'pos += 50cm*dir', 'Move the particles 50 cm along their directions.' ),
            ( 'dir = (0,0,1)', 'Make all particles move along z.' ) ) ),
    ),
    'hist' : (
        ( 'Histograms', None, (
            ( 'ekin', 'The kinetic energies, in a suitable unit.' ),
            ( 'ekin/MeV;logx;split=pdgcode',
              'The energies in MeV, on a logarithmic axis, with a curve for each particle type.' ),
            ( 'ekin;logx;lethargy', 'The energies per unit of lethargy.' ),
            ( 'wavelength/Aa;range=0:10',
              'The wavelengths from 0 to 10 Aa (only of neutrons and gammas, the others are left out).' ),
            ( 'angle(dir,(0,0,1))/deg;logy;split=pdgcode in (neutron,gamma)',
              'The angles to the z axis, for neutrons and gammas, and for the others.' ) ) ),
        ( '2D histograms and 3D plots', None, (
            ( 'x : y;xrange=-10cm:10cm;yrange=-10cm:10cm', 'The positions in the x-y plane.' ),
            ( 'atan2(uy,ux)/deg : uz', 'The directions: the azimuth around the z axis, and uz.' ),
            ( 'x : y : z;split=pdgcode',
              'The positions in 3D, as points for a sample of the particles, by particle type (in windows).' ) ) ),
        ( 'Bar charts', None, (
            ( 'pdgcode;bar', 'A bar chart of the particle types.' ),
            ( 'userdata.nscat;bar;unweighted', 'The numbers of particles for each value of nscat.' ) ) ),
    ),
}

def example_rows( topic ):
    """All examples of the topic, as (expression, what it does)"""
    return [ row for _, _, rows in examples[topic] for row in rows ]

_intro = {
    'pick' : ( 'PICK: an expression which is true for the particles to use, for example:',
               '''The operators are: + - * / (and ^ for powers), == != < <= > >=, in and
not in (one of the values in parentheses), and, or, not (and & | ~ for
bits). Values with units must be written with units
(e.g. 25meV or 10cm), except for a plain 0 (e.g. x > 0), and the wavelength
can only be used for neutrons and gammas, which must be picked first (e.g.
"pdgcode == neutron and wavelength > 1.8Aa").''' ),
    'edit' : ( 'EDIT: statements separated by ";", executed in order, for example:',
               '''The statements are assignments to fields (=, +=, -=, *= and /=, with values
in the units of the field, and wavelength = ... changing ekin), assignments
to variables (other lowercase names, which can be used in later statements),
and the statements listed below. The expressions are written as for -p (see
-p help).''' ),
    'hist' : ( '''HIST: what to plot, an expression of the particles (written as for -p),
or two separated by ":" for a 2D histogram (or three for a 3D plot of a
sample of the particles, in windows), followed by options separated by ";".
For example:''',
               '''The plots are shown in a window, or in the terminal (with -t), or saved in a
file (with -o FILE). -H can be given several times, for several plots, and
with -w it adds plots to the viewer.''' ),
}

#(the end of the help texts, if any):
_outro = {
    'hist' : '''Options which are on or off are given as 1 or 0, and alone (as in "ekin;logy")
they mean 1 (bar alone means bar=auto).

The expressions, with the fields of the particles, units and functions, are
described by -p help.''',
}

#(texts at the start of groups in the help texts):
_group_notes = {
    'vectors' : ( 'Vectors are written as (a,b,c), or (a,b) in 2D, with the same unit'
                  ' for all values (except a plain 0, as in (0,0,1m)). Their values are'
                  ' v.x, v.y and v.z, or v.at(0), v.at(1) and v.at(2) (counting from 0):'
                  ' x is just an alias of pos.x (or pos.at(0)), and uz of dir.z. Vectors'
                  ' can be added and subtracted, and multiplied and divided by numbers,'
                  ' abs(v) is their length, and v^2 their length squared. Edits can'
                  ' assign pos, dir and pol (e.g. pos += (0,0,1m)).' ),
}

_topic_groups = {
    'pick' : ( 'fields', 'vectors', 'constants', 'particles', 'units', 'functions' ),
    'edit' : ( 'statements', 'fields', 'vectors', 'constants', 'particles', 'units',
               'functions' ),
    'hist' : ( 'histoptions', ),
}

def _help_blocks( topic ):
    """Help for -p help ('pick'), -E help ('edit') or -H help ('hist'), as
    blocks (see _helptext)"""
    head, tail = _intro[topic]
    opt = { 'pick' : '-p', 'edit' : '-E', 'hist' : '-H' }[topic]
    blocks = [ ( 'text', head ) ]
    for title, note, rows in examples[topic]:
        blocks += [ ( 'gap', ), ( 'subsection', title ) ]
        if note:
            blocks.append( ( 'note', note ) )
        blocks.append( ( 'examples', [ ( f'{opt} "{expr}"', what ) for expr, what in rows ] ) )
    blocks += [ ( 'gap', ), ( 'text', tail ) ]
    for g in _topic_groups[topic]:
        blocks += [ ( 'gap', ), ( 'section', _group_titles[g] ) ]
        if g in _group_notes:
            blocks.append( ( 'note', _group_notes[g] ) )
        blocks += [ ( 'item', name, long ) for grp, name, _short, long in _hints if grp == g ]
    if topic in _outro:
        blocks += [ ( 'gap', ), ( 'text', _outro[topic] ) ]
    return blocks

def _help_text( topic ):
    """Help text for -p help ('pick'), -E help ('edit') or -H help ('hist')"""
    from ._helptext import plain_text
    return plain_text(_help_blocks(topic))

def _short_hint( name ):
    """Short description of a name (for completion), or None"""
    for _, n, short, _ in _hints:
        if n.split('(')[0].split('=')[0] == name:
            return short
    return None
