
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

def is_well_known_binary( frel ):
    if frel.split('/')[-1] in ('dump_dmp',):
        return True
    if frel.endswith(('.gz', '.mcpl', '.w')):
        return True
    if frel in ['devel/misc/test_encodings.log']:
        return True
    #Images of the website:
    if frel.startswith('doc/source/images/') and frel.endswith('.png'):
        return True

def main():
    search_str = 'f' + 'i' + 'x' + 'm' + 'e'
    from .dirs import reporoot
    from .srciter import all_files_iter
    hits = []
    #Ignore well-known false positives:
    whitelist = {
        '.github/workflows/fix'+'me.yml' : 1,
        'devel/pypath/mcpl_repo_tools/_check_misc.py' : 1,
    }
    actually_ignored = []
    for f in all_files_iter():
        frel = str(f.relative_to(reporoot)).replace('\\','/')
        if is_well_known_binary ( frel ):
            print(f"Skip known binary: {frel}")
            continue
        n = 0
        try:
            content = f.read_text()
        except UnicodeDecodeError as e:
            raise RuntimeError(f'Binary file: {f}') from e
        for line in content.splitlines():
            if search_str in line.lower():
                n+=1
        nignore = whitelist.get(frel,0)
        if n < nignore:
            raise SystemExit(f"ERROR: More whitelisted {search_str}'s ("
                             f"{nignore}) in {frel} than actually found ({n})")
        n -= nignore
        if n:
            hits.append( ( n, frel ) )
        if nignore:
            actually_ignored.append( ( nignore, frel ) )
    def print_list( hitlist, do_ignore ):
        if not hitlist:
            print("    (none)")
            return 0
        ntot = sum( n for n,f in hitlist )
        hitlist.append( (ntot, 'TOTAL' ) )
        hitlist.sort()
        wn = max( len(str(n)) for n,f in hitlist )
        for n,f in hitlist:
            print( f'     {str(n).rjust(wn)} {f}' )
        return ntot

    print(f"Whitelisted {search_str}'s:")
    print()
    print_list(actually_ignored,True)
    print()
    print(f"Problematic {search_str}'s:")
    print()
    ntot = print_list(hits,False)
    print()
    if ntot:
        raise SystemExit( f"ERROR: A total of {ntot} "
                          f"problematic {search_str}'s found!" )

if __name__=='__main__':
    main()
