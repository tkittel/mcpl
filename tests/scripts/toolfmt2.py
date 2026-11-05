
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

import gzip
import os
from pathlib import Path

from MCPLTestUtils.dirs import test_data_dir
from MCPLTestUtils.toolcheck_common import check_same, cmd, copy, gunzip


def main():
    def dd(fn):
        return test_data_dir.joinpath('reffmt2',fn)

    f2 = dd('reffile_16.mcpl')
    f1 = Path('rf16cp.mcpl')
    assert not f1.exists(),"must run in clean directory"
    copy(f2,f1)

    #hard link:
    f1_hl=Path('rf16cp_hl.mcpl')
    os.link(f1,f1_hl)
    assert f1_hl.read_bytes() == f2.read_bytes()
    assert f1_hl.samefile( f1 )
    #soft links:
    f1_sl=Path('rf16cp_sl.mcpl')
    f1_sl.symlink_to(f1)
    f2_sl=Path('rf16_sl.mcpl')
    f2_sl.symlink_to(f2)
    assert f1_sl.read_bytes() == f2.read_bytes()
    assert f2_sl.read_bytes() == f2.read_bytes()
    copy(dd('reffile_5.mcpl'),'rf5cp.mcpl')
    copy(dd('reffile_5.mcpl.gz'),'rf5cp.mcpl.gz')

    fc = copy(dd('reffile_crash.mcpl'),'rfcrash.mcpl')
    fcgz = copy(dd('reffile_crash.mcpl.gz'),'rfcrash.mcpl.gz')

    Path('fake.mcpl').write_bytes(b'lasfsdfsfla\n')
    Path('fake.mcpl.gz').write_bytes(b'lasfsdfsfla\n')
    Path('fake2.mcpl.gz').write_bytes(gzip.compress(b'lasfsdfsfla\n'))

    copy(dd('reffile_empty.mcpl'),'rfempty.mcpl')
    copy(dd('reffile_empty.mcpl.gz'),'rfempty.mcpl.gz')

    fmisc = copy(dd('miscphys.mcpl.gz'),'.')
    fmiscnogz = Path('miscphysnogz.mcpl')
    fmiscnogz.write_bytes(gzip.decompress(fmisc.read_bytes()))


    #Test various options (also illegal ones):
    cmd('-h')
    cmd('--help')
    #(--h and --n are ambiguous):
    cmd('--h',fail=True)
    cmd('--version')
    cmd('--v')
    cmd(f1,'--justhead')
    cmd(f1,'--ju')
    cmd(f1,'-j')
    cmd(f1,'--nohead')
    cmd(f1,'--n',fail=True)
    cmd(f1,'--n','-m','--inplace',fail=True)
    cmd(f1,'--ju','-l2',fail=True)
    cmd(f1,'--ju','-s1',fail=True)
    cmd(f1,'-l2','-r',fail=True)
    cmd(f1,'--v','--h',fail=True)
    cmd(f1,'--v','--m','--inplace',fail=True)
    cmd(f1,'-l0','-s2')
    cmd(f1,'-l2','-s0')
    cmd(f1,'-m','--inplace',f2)
    cmd(f1,'-l0')


    #this used to give a warning on purpose, but since MCPL 2.0.0 it is an error:
    cmd(f1,'--mer','--inpl',f1,fail=True)
    cmd(f1,'-l0')
    #this used to give a warning on purpose, but since MCPL 2.0.0 it is an error:
    cmd(f1,'--m','--inplac',f1,fail=True)
    cmd(f1,'-l0')
    #this used to give a warning on purpose, but since MCPL 2.0.0 it is an error:
    cmd(f1,'--merge','--inplace',f1,fail=True)
    #lots of warnings (errors since MCPL 2.0.0):
    cmd('-m','dupmerge.mcpl',
        f1.name,
        f'./{f1.name}',
        f'../{f1.absolute().parent.name}/{f1.name}',
        f1_sl,
        f1_hl,
        f2_sl,
        f2_sl,fail=True)
    assert not Path('dupmerge.mcpl').is_file()
    cmd('-m','--inplace','dupmerge.mcpl','./dupmerge.mcpl',fail=True)
    cmd('-m','--inplace','dupmerge.mcpl','dupmerge.mcpl',fail=True)
    cmd(f1,'-l0')
    cmd('-l0','-s2',dd('reffile_5.mcpl.gz'))
    cmd('-l0','-s2',dd('reffile_5.mcpl'))
    cmd('-l0','-s2',dd('reffile_empty.mcpl'))
    cmd('-l0','-s2',dd('reffile_empty.mcpl.gz'))
    cmd('-m','--inplace','rf5cp.mcpl',dd('reffile_5.mcpl.gz'))
    cmd('-m','--inpla','rf5cp.mcpl.gz',dd('reffile_5.mcpl'),fail=True)
    cmd('-m','--inplac','rf5cp.mcpl.gz',dd('reffile_5.mcpl.gz'),fail=True)
    cmd(fc)
    cmd('--repair',fc)
    cmd(fc)
    cmd('--r',fc,fail=True)#already repaired
    cmd(fc)
    cmd('-r',fcgz,fail=True)#can not repair gz
    cmd(fc)
    cmd('-r',f1,fail=True)#already repaired
    cmd('rfempty.mcpl')
    cmd('-r','rfempty.mcpl',fail=True)#not broken
    cmd('rfempty.mcpl')
    cmd('rfempty.mcpl.gz')
    cmd('-r','rfempty.mcpl.gz',fail=True)#can not repair gz, and not broken
    cmd('rfempty.mcpl.gz')

    for fn in ('reffile_crash_0p4.mcpl','reffile_crash_8p7.mcpl'):
        fpartial = copy(dd(fn),f'rf{fn[8:]}')
        cmd(fpartial)
        cmd('-r',fpartial)
        cmd(fpartial)
        cmd('-r',fpartial,fail=True)#already repaired

    cmd('fake.mcpl',fail=True)
    cmd('fake.mcpl.gz',fail=True)
    cmd('fake2.mcpl.gz',fail=True)
    cmd('-x',fmisc,'extracted_0')
    cmd('-x',fmisc,'extracted_0',fail=True)#already exists (as .mcpl)
    cmd('--no-comment','--extract','-e','pdgcode == 2112',fmisc,'extracted_1.mcpl.gz')
    cmd('--no-comment','--extract','-e','pdgcode == -11',fmisc,'extracted_2.mcpl.gz')
    cmd('--no-comment','-x','-e','pdgcode == -1000020040',fmiscnogz,'extracted_3.mcpl.gz')
    cmd('--no-comment','-x','-e','pdgcode == 1000922350',fmisc,'extracted_4.mcpl.gz')
    cmd('--no-comment','-x','-e','pdgcode == 111','-l999999','-s150',fmiscnogz,'extracted_5.mcpl.gz')
    cmd('-l0','extracted_1.mcpl.gz')
    cmd('-l0','extracted_2.mcpl.gz')
    cmd('-l0','extracted_3.mcpl.gz')
    cmd('-l0','extracted_4.mcpl.gz')
    cmd('-l0','extracted_5.mcpl.gz')
    #this works because the embedded comment from extracting is (so far) identical:
    cmd('--merge','merged_new_file.mcpl','extracted_1.mcpl.gz','extracted_2.mcpl.gz')
    cmd('--merge','merged_1to5_new_filea.mcpl','extracted_1.mcpl.gz','extracted_2.mcpl.gz','extracted_3.mcpl.gz','extracted_4.mcpl.gz','extracted_5.mcpl.gz')
    gunzip('extracted_1.mcpl.gz')
    gunzip('extracted_2.mcpl.gz')
    cmd('--merge','merged_1to5_new_fileb.mcpl','extracted_1.mcpl','extracted_2.mcpl','extracted_3.mcpl.gz','extracted_4.mcpl.gz','extracted_5.mcpl.gz')
    check_same('merged_1to5_new_filea.mcpl','merged_1to5_new_fileb.mcpl')
    cmd('--merge','--inplace','extracted_1.mcpl','extracted_2.mcpl')
    cmd('extracted_1.mcpl')
    check_same('merged_new_file.mcpl','extracted_1.mcpl')
    check_same('miscphys.mcpl.gz','miscphysnogz.mcpl')
    cmd('--merge','--inplace','extracted_1.mcpl','extracted_3.mcpl.gz','extracted_4.mcpl.gz','extracted_5.mcpl.gz')
    check_same('extracted_1.mcpl','merged_1to5_new_fileb.mcpl')

    gunzip('extracted_3.mcpl.gz')
    gunzip('extracted_4.mcpl.gz')
    gunzip('extracted_5.mcpl.gz')
    cmd('--no-comment','--extract','-e','pdgcode == 2112',fmiscnogz,'extracted_1_new.mcpl')
    cmd('--no-comment','--extract','-e','pdgcode == -11',fmiscnogz,'extracted_2_new.mcpl')
    cmd('--no-comment','-x','-e','pdgcode == 1000922350',fmiscnogz,'extracted_4_new.mcpl')
    cmd('--merge','merged_1to5_new_filec.mcpl','extracted_1_new.mcpl','extracted_2_new.mcpl','extracted_3.mcpl','extracted_4_new.mcpl','extracted_5.mcpl')
    #merge to gzipped output by specifying .mcpl.gz:
    #  -> but fail since .mcpl file exists:
    cmd('--merge','merged_1to5_new_filec.mcpl.gz','extracted_1_new.mcpl','extracted_2_new.mcpl','extracted_3.mcpl','extracted_4_new.mcpl','extracted_5.mcpl',fail=True)
    #  -> but fail since wrong ending:
    cmd('--merge','merged_1to5_new_filec.gz','extracted_1_new.mcpl','extracted_2_new.mcpl','extracted_3.mcpl','extracted_4_new.mcpl','extracted_5.mcpl',fail=True)
    #  -> ok (might fail in old releases if gzip support was absent!):
    cmd('--merge','merged_1to5_new_filec_unique.mcpl.gz','extracted_1_new.mcpl','extracted_2_new.mcpl','extracted_3.mcpl','extracted_4_new.mcpl','extracted_5.mcpl')
    check_same('merged_1to5_new_filec.mcpl','merged_1to5_new_filec_unique.mcpl.gz')

    cmd('--merge','--inplace','extracted_1_new.mcpl','extracted_2_new.mcpl','extracted_3.mcpl','extracted_4_new.mcpl','extracted_5.mcpl')
    check_same('merged_1to5_new_filec.mcpl','extracted_1_new.mcpl')
    check_same('merged_1to5_new_filea.mcpl','merged_1to5_new_filec.mcpl')

    #mistakes with --merge but no --inplace should fail:
    cmd('--merge','extracted_1.mcpl','extracted_2.mcpl',fail=True)
    #too few pars:
    cmd('--merge','--inplace','extracted_1.mcpl',fail=True)
    cmd('--merge','newfile.mcpl',fail=True)

if __name__ == '__main__':
    main()
