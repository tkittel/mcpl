
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

"""The particle types with names: the one table of their PDG codes with names
for labels, symbols and colours for plots, and the names which can be used for
them in expressions (as in mcpltool -p; mcpltool-c has the same names, see
mcpl_core/src/mcpl.c), with their descriptions in the help."""

__all__ = []

#(PDG code, name in labels, symbol in plots (or None), colour in plots (an
#index in the colour cycles of the backends, which are those of matplotlib, or
#None), and names in expressions with their descriptions in the help). The
#colours of neutrons, gammas and electrons are close to those of their tracks in
#the MCPL logo (blue, yellow and orange). The symbols are only used in plots,
#never in texts which might be copied:
_particles = (
    ( 2112, 'n', None, 0, ( ( 'neutron', 'neutrons' ), ) ),
    ( -2112, 'n-bar', 'n\u0304', None, ( ( 'antineutron', 'antineutrons' ), ) ),
    ( 2212, 'p', None, 4, ( ( 'proton', 'protons' ), ) ),
    ( -2212, 'p-bar', 'p\u0304', None, ( ( 'antiproton', 'antiprotons' ), ) ),
    ( 11, 'e-', 'e\u207b', 1, ( ( 'electron', 'electrons' ), ) ),
    ( -11, 'e+', 'e\u207a', 3, ( ( 'positron', 'positrons' ),
                                ( 'antielectron', 'positrons (same as positron)' ) ) ),
    ( 13, 'mu-', '\u03bc\u207b', 5, ( ( 'muon', 'muons (negative)' ), ) ),
    ( -13, 'mu+', '\u03bc\u207a', 6, ( ( 'antimuon', 'antimuons (positive muons)' ), ) ),
    ( 22, 'gamma', '\u03b3', 8, ( ( 'gamma', 'gammas (photons)' ),
                                ( 'photon', 'photons (same as gamma)' ) ) ),
    ( 15, 'tau-', '\u03c4\u207b', None, () ),
    ( -15, 'tau+', '\u03c4\u207a', None, () ),
    ( 12, 'nu_e', '\u03bd\u2091', None, () ),
    ( -12, 'nu_e-bar', '\u03bd\u0304\u2091', None, () ),
    ( 14, 'nu_mu', '\u03bd\u03bc', None, () ),
    ( -14, 'nu_mu-bar', '\u03bd\u0304\u03bc', None, () ),
    ( 16, 'nu_tau', '\u03bd\u03c4', None, () ),
    ( -16, 'nu_tau-bar', '\u03bd\u0304\u03c4', None, () ),
    ( 211, 'pi+', '\u03c0\u207a', 2, () ),
    ( -211, 'pi-', '\u03c0\u207b', 7, () ),
    ( 111, 'pi0', '\u03c0\u2070', None, () ),
    ( 321, 'K+', 'K\u207a', None, () ),
    ( -321, 'K-', 'K\u207b', None, () ),
    ( 130, 'Klong', 'K\u2070L', None, () ),
    ( 310, 'Kshort', 'K\u2070S', None, () ),
    ( 1000010020, 'D', None, None, () ),
    ( -1000010020, 'D-bar', 'D\u0304', None, () ),
    ( 1000010030, 'T', None, None, () ),
    ( -1000010030, 'T-bar', 'T\u0304', None, () ),
    ( 1000020040, 'alpha', '\u03b1', None, () ),
    ( -1000020040, 'alpha-bar', '\u03b1\u0304', None, () ),
)

#The particle types for which wavelengths are defined (neutrons and gammas):
_wavelength_pdgcodes = ( 2112, 22 )

#The table by PDG code (names, colours), by name (symbols) and by name in
#expressions (PDG codes, and the descriptions in the help):
_pdg_names = { p[0] : p[1] for p in _particles }
_pdg_symbols = { p[1] : p[2] for p in _particles if p[2] is not None }
_pdg_colors = { p[0] : p[3] for p in _particles if p[3] is not None }
_particle_names = { name : p[0] for p in _particles for name, _ in p[4] }

def _particle_name( pdgcode ):
    """The name of a particle type (a PDG code) in expressions, like neutron
    (or the code, if it has no name)"""
    return next( ( n for n, p in _particle_names.items() if p == pdgcode ), str(pdgcode) )

def _particle_text( pdgcode ):
    """The name of a particle type (a PDG code) in texts: its name in
    expressions (like neutron), else in labels (like pi+), else the code"""
    name = _particle_name(pdgcode)
    return _pdg_names.get(pdgcode,name) if name == str(pdgcode) else name
_particle_help = [ ( name, p[0], descr ) for p in _particles for name, descr in p[4] ]
