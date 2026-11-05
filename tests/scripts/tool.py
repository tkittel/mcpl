
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
        return test_data_dir.joinpath('ref',fn)
    def ddv2(fn):
        return test_data_dir.joinpath('reffmt2',fn)

    f2 = dd('reffile_16.mcpl')
    f1 = Path('rf16cp.mcpl')
    assert not f1.exists(),"must run in clean directory"
    copy(f2,f1)

    f_statsum_crash = Path('f_statsum_crash.mcpl')
    copy( dd('ref_statsum_crash.mcpl'), f_statsum_crash)

    copy( dd('ref_statsum.mcpl.gz'), 'statsum_copy_a.mcpl.gz')
    copy( dd('ref_statsum.mcpl.gz'), 'statsum_copy_b.mcpl.gz')
    gunzip('statsum_copy_a.mcpl.gz')
    gunzip('statsum_copy_b.mcpl.gz')
    copy( dd('ref_statsum.mcpl.gz'), 'statsum_copy.mcpl.gz')

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

    #file in MCPL-2 format, for testing some commands mixing MCPL-2 and MCPL-3
    #files:
    f2v2 = copy(ddv2('reffile_16.mcpl'),'rf16cp_fmt2.mcpl')
    Path('difficult_unitvector.mcpl').write_bytes(
        gzip.decompress(dd('difficult_unitvector.mcpl.gz').read_bytes())
    )

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

    cmd(f_statsum_crash)
    cmd('-r',f_statsum_crash)
    cmd(f_statsum_crash)

    cmd('statsum_copy_a.mcpl')
    cmd('statsum_copy_b.mcpl')
    cmd('--merge','--inplace','statsum_copy_a.mcpl','statsum_copy_b.mcpl')
    cmd('statsum_copy_a.mcpl')
    cmd('statsum_copy_b.mcpl')

    copy(dd('reffile_truncated.mcpl.gz'),'rftrunc.mcpl.gz')
    cmd('-r','rftrunc.mcpl.gz',fail=True)
    copy(dd('reffile_truncated.mcpl'),'rftrunc.mcpl')
    cmd('-r','rftrunc.mcpl')

    cmd('rftrunc.mcpl')
    cmd('fake.mcpl',fail=True)
    cmd('fake.mcpl.gz',fail=True)
    cmd('fake2.mcpl.gz',fail=True)
    cmd('-x',fmisc,'extracted_0')
    cmd('-x',fmisc,'extracted_0',fail=True)#already exists (as .mcpl)
    #(--no-comment, since the files are merged again below):
    cmd('--extract','-e','pdgcode == 2112','--no-comment',fmisc,'extracted_1.mcpl.gz')
    cmd('--extract','-e','pdgcode == -11','--no-comment',fmisc,'extracted_2.mcpl.gz')
    cmd('-x','-e','pdgcode == -1000020040','--no-comment',fmiscnogz,'extracted_3.mcpl.gz')
    cmd('-x','-e','pdgcode == 1000922350','--no-comment',fmisc,'extracted_4.mcpl.gz')
    cmd('-x','-e','pdgcode == 111','-l999999','-s150','--no-comment',fmiscnogz,'extracted_5.mcpl.gz')
    #An edit keeping no particles gives an empty file:
    cmd('-x','-e','pdgcode == 0',fmiscnogz,'badpdg.mcpl')
    Path('badpdg.mcpl').unlink()
    #Invalid edits must not leave output files behind, like numbers which are
    #too large, and leading zeros:
    cmd('-x','-e','pdgcode == 99999999999999999999',fmiscnogz,'badpdg.mcpl',fail=True)
    cmd(f1,'-l99999999999999999999',fail=True)
    cmd('-x','-e','pdgcode == 022','--no-comment',fmisc,'extracted_6.mcpl.gz',fail=True)
    #Outputs with the name of an existing directory are refused:
    Path('dirout.mcpl.gz').mkdir()
    cmd('-x',fmisc,'dirout.mcpl.gz',fail=True)
    Path('dirout.mcpl.gz').rmdir()
    cmd('-x','-e','pdgcode == abc',fmiscnogz,'badpdg.mcpl',fail=True)
    cmd('-x','-e','pdgcode == Neutron',fmiscnogz,'badpdg.mcpl',fail=True)
    cmd('-x','-e','pdgcode == neutron',fmiscnogz,'extracted_names_1.mcpl')
    #Conditions after changes see the changed values:
    cmd('-x','-e','rotate_y(90deg); x > 0cm; weight *= 2','--no-comment',fmiscnogz,'extracted_rotated.mcpl')
    cmd('-n','-l3','extracted_rotated.mcpl')
    #The -e (extracting) and -pPDGCODE of earlier versions give errors:
    cmd('-e',fmiscnogz,'old.mcpl',fail=True)
    cmd('-e','-p2112',fmiscnogz,'old.mcpl',fail=True)
    cmd('-x','-p2112',fmiscnogz,'old.mcpl',fail=True)
    cmd('-x','-p','pdgcode == 22',fmiscnogz,'old.mcpl',fail=True)
    cmd('-x','-e','pdgcode == antiproton','-l200',fmiscnogz,'extracted_names_2.mcpl')
    cmd('-x','-e','pdgcode == photon',fmiscnogz,'extracted_names_3.mcpl')
    cmd('-x','-e','pdgcode == antielectron',fmiscnogz,'extracted_names_4.mcpl')
    cmd('-x','-e','pdgcode == -11',fmiscnogz,'extracted_names_5.mcpl')
    cmd('-n','-l3','extracted_names_3.mcpl')
    assert not Path('badpdg.mcpl').exists()
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
    cmd('--extract','-e','pdgcode == 2112','--no-comment',fmiscnogz,'extracted_1_new.mcpl')
    cmd('--extract','-e','pdgcode == -11','--no-comment',fmiscnogz,'extracted_2_new.mcpl')
    cmd('-x','-e','pdgcode == 1000922350','--no-comment',fmiscnogz,'extracted_4_new.mcpl')
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
    #error - can't mix MCPL versions when merging inplace:
    cmd('--merge','--inplace',f2v2,f2,fail=True)
    cmd('--merge','--inplace',f2,f2v2,fail=True)
    #but ok when not inplace (does trigger warning though):
    cmd('--merge','mix.mcpl',f2v2,f2)
    cmd('-l0','mix.mcpl')
    #test that extraction & merges do not change bytes in transferred particles
    #(using hidden --preventcomment flag):
    cmd('-x','difficult_unitvector.mcpl','extracted_all','-l0','--preventcomment')
    cmd('-x','difficult_unitvector.mcpl','extracted_none','-s999999999','--preventcomment')
    #comments describing the extraction (and --no-comment):
    cmd('-x','-l3','-s2','-e','pdgcode == neutron',fmiscnogz,'extracted_comment_1.mcpl')
    cmd('-x','-e','pdgcode == -11',fmiscnogz,'extracted_comment_2.mcpl')
    cmd('-x',fmiscnogz,'extracted_comment_3.mcpl')
    cmd('-x','--no-comment','-e','pdgcode == 22',fmiscnogz,'extracted_comment_4.mcpl')
    cmd('-j','extracted_comment_1.mcpl')
    cmd('-j','extracted_comment_2.mcpl')
    cmd('-j','extracted_comment_3.mcpl')
    cmd('-j','extracted_comment_4.mcpl')
    cmd('--no-comment',fmiscnogz,fail=True)
    #with comments, files extracted in the same way can be merged, but not
    #files extracted in different ways:
    cmd('-x','-e','pdgcode == neutron','-s5',fmiscnogz,'extracted_comment_5.mcpl')
    cmd('-x','-e','pdgcode == neutron','-l5',fmiscnogz,'extracted_comment_6.mcpl')
    cmd('-x','-e','pdgcode == 2112',fmisc,'extracted_comment_7.mcpl')
    cmd('--merge','merged_comment_1.mcpl','extracted_comment_1.mcpl','extracted_comment_5.mcpl',fail=True)
    cmd('--merge','merged_comment_2.mcpl','extracted_comment_7.mcpl','extracted_comment_6.mcpl',fail=True)
    cmd('-x','-e','pdgcode == neutron',fmisc,'extracted_comment_8.mcpl')
    #(the edits are recorded in their canonical form, here pdgcode==neutron for
    #both pdgcode == 2112 and pdgcode == neutron, so the files can be merged):
    cmd('--merge','merged_comment_3.mcpl','extracted_comment_7.mcpl','extracted_comment_8.mcpl')
    cmd('-j','merged_comment_3.mcpl')
    cmd('-x','-e','(pdgcode==2112) and ekin>5000eV',fmisc,'extracted_comment_9.mcpl')
    cmd('-x','-e','pdgcode == neutron and ekin > 5keV',fmisc,'extracted_comment_10.mcpl')
    cmd('--merge','merged_comment_4.mcpl','extracted_comment_9.mcpl','extracted_comment_10.mcpl')
    cmd('-j','merged_comment_4.mcpl')
    #the code doing the same as -e (for files like the input file):
    cmd('-x','--code=c','-e','pdgcode == neutron and ekin > 5keV',fmisc)
    cmd('-x','--code=cpp','-e','x += 1cm; weight *= 2',fmisc)
    fud = copy(test_data_dir.joinpath('reffmt4','reffile_ud_scalars.mcpl'),'.')
    cmd('-x','--code=c','-e','userdata.temp > 300K; ekin = userdata.e',fud)
    cmd('-x','--code=c','-e','userdata.temp > 300K',fmisc,fail=True)
    cmd('-x','--code=py',fmisc,fail=True)
    cmd('--code=c',fmisc,fail=True)
    #(the code does what -e does with the range and comment options):
    cmd('-x','--code=c','-s2','-l5','--no-comment',fmisc)
    cmd('-x','--code=cpp','-e','z > 0','--keep-statsum',fmisc)
    cmd('-x','--code=c','-d',fmisc,fail=True)
    cmd('-x','--code=cpp',fmisc,'out.mcpl',fail=True)

    cmd('-m','extracted_recombined','extracted_none.mcpl','extracted_all.mcpl')
    cmd('-m','--inplace','extracted_none.mcpl','extracted_all.mcpl')
    check_same('difficult_unitvector.mcpl','extracted_recombined.mcpl')
    check_same('difficult_unitvector.mcpl','extracted_none.mcpl')
    check_same('extracted_recombined.mcpl','extracted_none.mcpl')

    cmd('--extract','statsum_copy.mcpl.gz','statsum_extract1.mcpl')
    cmd('statsum_extract1.mcpl')

    cmd('--extract','-l7','statsum_copy.mcpl.gz','statsum_extract2.mcpl')
    cmd('statsum_extract2.mcpl')

    cmd('--extract','-s30','statsum_copy.mcpl.gz','statsum_extract3.mcpl')
    cmd('statsum_extract3.mcpl')

    cmd('--extract','-l4','-s20','statsum_copy.mcpl.gz','statsum_extract4.mcpl')
    cmd('statsum_extract4.mcpl')

    cmd('--extract','-l300','statsum_copy.mcpl.gz','statsum_extract_all.mcpl')
    cmd('statsum_extract_all.mcpl')

    cmd('--extract','-l40','-s1',
        'statsum_copy.mcpl.gz','statsum_extract5.mcpl')
    cmd('statsum_extract5.mcpl')
    cmd('-x','-l40','-s1','-e','pdgcode == 22',
        'statsum_copy.mcpl.gz','statsum_extract5photons.mcpl')
    cmd('statsum_extract5photons.mcpl')

    cmd('--extract','-e','pdgcode == 22',
        'statsum_copy.mcpl.gz','statsum_extractphotons_all.mcpl')
    cmd('statsum_extractphotons_all.mcpl')

    cmd('--extract','-e','pdgcode == 22','-l400',
        'statsum_copy.mcpl.gz','statsum_extractphotons_all2.mcpl')
    cmd('statsum_extractphotons_all2.mcpl')

    #More bad files:
    cmd(dd('reffile_bad1.mcpl'),fail=True)
    cmd(dd('reffile_bad2.mcpl'),fail=True)
    cmd(dd('reffile_bad3.mcpl'),fail=True)
    cmd(dd('reffile_bad4.mcpl'),fail=True)
    cmd(dd('reffile_bad1.mcpl.gz'),fail=True)
    cmd(dd('reffile_bad2.mcpl.gz'),fail=True)
    cmd(dd('reffile_bad3.mcpl.gz'),fail=True)
    cmd(dd('reffile_bad4.mcpl.gz'),fail=True)
    #missing file (also tests whether or not we complain about the extension):
    cmd('bla.txt',fail=True)
    Path('bla.txt').write_bytes(b'hello\n')
    #not missing but bad (also tests whether or not we complain about the extension):
    cmd('bla.txt',fail=True)
    cmd(dd('reffile_truncated.mcpl.gz'),fail=True)
    cmd(dd('reffile_truncated.mcpl'),fail=True)
    #A file which is not really gzipped opens nicely, despite its name:
    cmd(dd('reffile_notreallygz.mcpl.gz'))
    cmd(dd('reffile_uw.mcpl.gz'))

    #This one contains a non-utf8 comment! (todo: should this actually be forbidden and detected??):
    #print(mcpltool_cmd)
    cmd(dd('reffile_encodings.mcpl.gz'))

    oslash='\u00f8'
    for bk in ['asciidata','asciidata_empty','utf8data','binarydata',f'utf8bl{oslash}bkey']:
        print(f'====> extracting and calculating md5sum of blob with key "{bk}":')
        cmd(dd('reffile_encodings.mcpl.gz'),f'-b{bk}',print_md5sum_of_output=True)

    #NOTE: Not possible apparently to pass b'notutf8key_\xff\xfe_' to subprocess.run:
    #So we are missing the following output:
    #====> extracting and calculating md5sum of blob with key "notutf8key_XXX_":
    #a04637816e7436951f0512d38d48f212

if __name__ == '__main__':
    main()
