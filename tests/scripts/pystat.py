
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

# NEEDS: numpy

def files_for_testing():
    import itertools

    from MCPLTestUtils.dirs import test_data_dir as tdir
    for p in itertools.chain( tdir.joinpath('ref').glob('*.mcpl*'),
                              tdir.joinpath('reffmt2').glob('*.mcpl*') ):
        if 'bad' in p.name or 'truncated' in p.name or 'crash' in p.name:
            continue
        yield p

def main():
    import mcpldev as mcpl
    for path in sorted( files_for_testing(),
                        key = lambda f : (f.parent.name,f.name,f) ):
        with mcpl.MCPLFile(path) as f:
            nparticles = f.nparticles
        for blocklength in sorted({max(1,nparticles),nparticles+1,max(1,nparticles-1)}):
            print('\n'*3+'='*100+'\n'*3)
            fnprint = '/'.join(path.parts[-2:])
            print(f'Testing {fnprint} '
                  f'(nparticles={nparticles}) with blocklength={blocklength}')
            with mcpl.MCPLFile(path,blocklength=blocklength) as f:
                #print (path,blocklength)
                assert f.blocklength == blocklength
                for p in f.particle_blocks:
                    lens = [ len(p.x),len(p.y),len(p.z),
                             len(p.ux),len(p.uy),len(p.uz),
                             len(p.polx),len(p.poly),len(p.polz),
                             len(p.pdgcode),len(p.weight),len(p.userflags),
                             len(p.position),len(p.polarisation),len(p.direction),
                             len(p.time),len(p.ekin) ]
                    #print (lens)
                    assert len(set(lens))==1
                    assert lens[0]<=blocklength
                    assert blocklength>=1
                if nparticles>0:
                    s=mcpl.collect_stats(f)
                    mcpl.dump_stats(s)

    #stat:sum entries marked as not available (since file was not closed):
    from MCPLTestUtils.dirs import test_data_dir
    print('\n'*3+'='*100+'\n'*3)
    print('Testing ref/ref_statsum_crash.mcpl')
    mcpl.dump_stats(mcpl.collect_stats(test_data_dir.joinpath('ref','ref_statsum_crash.mcpl'),bin_data=False))

    #Conditions leaving blocks without particles, and keeping none at all:
    print('\n'*3+'='*100+'\n'*3)
    f1 = test_data_dir.joinpath('ref','reffile_1.mcpl')
    print('Testing ref/reffile_1.mcpl with blocklength=2 and a condition keeping the last particle')
    with mcpl.MCPLFile(f1,blocklength=2,edit='fileidx >= 4') as f:
        mcpl.dump_stats(mcpl.collect_stats(f))
    with mcpl.MCPLFile(f1,edit='fileidx > 100') as f:
        print('Edit keeping no particles gives:',mcpl.collect_stats(f))

if __name__ == '__main__':
    main()
