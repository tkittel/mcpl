
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

"""Physics data and conversions, like descriptions of PDG codes and wavelengths."""

__all__ = []

from ._common import MCPLError
from ._numpy import np
from .constants import hc_eV_Aa, neutron_mass_energy

_db_pdg = None
_db_elem = None
def _pdg_database(pdgcode):
    global _db_pdg, _db_elem
    if _db_pdg is None:
        _db_pdg = { 12:'nu_e',14:'nu_mu',16:'nu_tau',-12:'nu_e-bar',-14:'nu_mu-bar',
                    -16:'nu_tau-bar',2112:'n',2212:'p',-2112:'n-bar',-2212:'p-bar',
                    22:'gamma',11:'e-',-11:'e+',13:'mu-',-13:'mu+',15:'tau-',-15:'tau+',
                    211:'pi+',-211:'pi-',111:'pi0',321:'K+',-321:'K-',130:'Klong',
                    310:'Kshort',-1000010020:'D-bar',-1000010030:'T-bar',1000010020:'D',
                    1000010030:'T',1000020040:'alpha',-1000020040:'alpha-bar' }
    r=_db_pdg.get(pdgcode,None)
    if r is not None:
        return r
    if _db_elem is None:
        _db_elem = ['H',  'He', 'Li', 'Be', 'B',  'C',  'N',  'O',  'F',  'Ne',
                    'Na', 'Mg', 'Al', 'Si', 'P' , 'S',  'Cl', 'Ar', 'K',  'Ca', 'Sc',
                    'Ti', 'V',  'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge',
                    'As', 'Se', 'Br', 'Kr', 'Rb', 'Sr', 'Y',  'Zr', 'Nb', 'Mo', 'Tc',
                    'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn', 'Sb', 'Te', 'I',  'Xe',
                    'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb',
                    'Dy', 'Ho', 'Er', 'Tm', 'Yb', 'Lu', 'Hf', 'Ta', 'W',  'Re', 'Os',
                    'Ir', 'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi', 'Po', 'At', 'Rn', 'Fr',
                    'Ra', 'Ac', 'Th', 'Pa', 'U',  'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf',
                    'Es', 'Fm', 'Md', 'No', 'Lr', 'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt',
                    'Ds', 'Rg']
    if pdgcode>0 and pdgcode//100000000==10:
        III = pdgcode % 10
        pdgcode //= 10
        AAA = pdgcode%1000
        pdgcode //= 1000
        ZZZ = pdgcode%1000
        pdgcode //= 1000
        L = pdgcode % 10
        pdgcode //= 10
        if pdgcode==10 and ZZZ>0 and AAA>0:
            if L==0 and III==0 and ZZZ < len(_db_elem)+1:
                return f'{_db_elem[ZZZ-1]}{AAA}'
            s = f'ion(Z={ZZZ},A={AAA}'
            if L:
                s += f',L={L}'
            if III:
                s += f',I={III}'
            s += ')'
            return s
    return None

#Names of a few common particles, which can be used instead of PDG codes in
#"mcpltool -p" (mcpltool-c has an identical list):
_particle_names = { 'neutron' : 2112, 'antineutron' : -2112,
                    'proton' : 2212, 'antiproton' : -2212,
                    'electron' : 11, 'positron' : -11, 'antielectron' : -11,
                    'muon' : 13, 'antimuon' : -13,
                    'gamma' : 22, 'photon' : 22 }

#Symbols of particles for plots (legends and other decorations, never texts
#which might be copied, like the names in expressions):
_pdg_symbols = { 'gamma' : '\u03b3', 'e-' : 'e\u207b', 'e+' : 'e\u207a',
                 'mu-' : '\u03bc\u207b', 'mu+' : '\u03bc\u207a', 'tau-' : '\u03c4\u207b',
                 'tau+' : '\u03c4\u207a', 'pi+' : '\u03c0\u207a', 'pi-' : '\u03c0\u207b',
                 'pi0' : '\u03c0\u2070', 'K+' : 'K\u207a', 'K-' : 'K\u207b',
                 'nu_e' : '\u03bd\u2091', 'alpha' : '\u03b1' }

def _pdg_name( pdgcode, unicode = False ):
    """Name of a particle type, like "n" (with the symbol for plots, like "\u03b3", if
    unicode is set), or None if unknown"""
    name = _pdg_database(int(pdgcode))
    return _pdg_symbols.get(name,name) if unicode else name

def _pdg_label( pdgcode, unicode = False ):
    """Label of a particle type, like "n (2112)" (or "2112" if unknown, see
    _pdg_name for unicode)"""
    name = _pdg_name(pdgcode,unicode)
    return f'{name} ({int(pdgcode)})' if name else str(int(pdgcode))

def _ascii_symbols( text ):
    """The text with the symbols of particles for plots (see _pdg_symbols)
    replaced by their names, for plots in ASCII"""
    for name, sym in sorted( _pdg_symbols.items(), key = lambda kv : -len(kv[1]) ):
        text = text.replace(sym,name)
    return text

def wavelength_from_ekin(ekin, pdgcode = 2112):
    """Convert kinetic energy [MeV] to (de Broglie) wavelength [Aa] for
    neutrons (pdgcode 2112) and gammas (pdgcode 22), using the CODATA 2022
    constants in mcpl.constants (and relativistic kinematics for neutrons).
    Returns NaN for other particles. Works with numbers or numpy arrays."""
    e = np.asarray(ekin,dtype=float)
    pdg = np.asarray(pdgcode)
    with np.errstate(divide='ignore',invalid='ignore'):
        #momentum times c [MeV] (for neutrons: pc = sqrt(E*(E+2mc^2))):
        pc = np.where( pdg == 2112, np.sqrt( e * ( e + 2 * neutron_mass_energy ) ),
                       np.where( pdg == 22, e, np.nan ) )
        res = hc_eV_Aa * 1e-6 / pc
    return res if res.ndim else float(res)

def ekin_from_wavelength(wavelength, pdgcode = 2112):
    """Convert (de Broglie) wavelength [Aa] to kinetic energy [MeV] for
    neutrons (pdgcode 2112) and gammas (pdgcode 22), using the CODATA 2022
    constants in mcpl.constants (and relativistic kinematics for neutrons).
    Returns NaN for other particles. Works with numbers or numpy arrays."""
    wl = np.asarray(wavelength,dtype=float)
    pdg = np.asarray(pdgcode)
    mc2 = neutron_mass_energy
    with np.errstate(divide='ignore',invalid='ignore'):
        pc = hc_eV_Aa * 1e-6 / wl#[MeV]
        #For neutrons E = sqrt(pc^2+(mc^2)^2)-mc^2, written in a form which is
        #numerically stable when pc << mc^2:
        res = np.where( pdg == 2112, np.square(pc) / ( np.sqrt( np.square(pc) + mc2*mc2 ) + mc2 ),
                        np.where( pdg == 22, pc, np.nan ) )
    return res if res.ndim else float(res)

def wavelength_checked(ekin, pdgcode):
    """Like wavelength_from_ekin, but raising MCPLError instead of returning NaN
    or infinite values (for particles which are not neutrons or gammas, or which
    have zero kinetic energy)."""
    pdg = np.asarray(pdgcode)
    notng = ~np.isin(pdg,(2112,22))
    if np.any(notng):
        bad = int(pdg[notng].flat[0])
        raise MCPLError('The wavelength is only defined for neutrons (pdgcode'
                        ' 2112) and gammas (pdgcode 22), not for particles with'
                        f' pdgcode {bad}, so pick neutrons or gammas first'
                        ' (e.g. with block[block.pdgcode == 2112])')
    res = wavelength_from_ekin(ekin, pdgcode)
    if not np.all(np.isfinite(res)):
        raise MCPLError('The wavelength of particles with zero kinetic energy is'
                        ' infinite')
    return res
