
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

#Files in MCPL format version 4 without userdata are identical to files in
#version 3 except for the version number, so any such file can be turned into
#the other by changing the version number (for version 3 files without NaN or
#infinite values). Both must be read in the same way by the C and Python code.
#MCPL itself writes files without userdata in version 3, so the version 4
#files are made here from version 3 reference files. Files with userdata have
#0x2 in the userflags field of the header.

import gzip
import pathlib
import subprocess

import mcpldev as mcpl
from MCPLTestUtils.dirs import mcpltool_cmd, test_data_dir


def set_version( src, tgt, version ):
    data = src.read_bytes()
    assert data[0:4] == b'MCPL' and data[4:7] in (b'003',b'004')
    tgt.write_bytes( data[0:4] + version + data[7:] )

def run_c( *args ):
    rv = subprocess.run( [mcpltool_cmd]+[str(a) for a in args],
                         capture_output = True, check = True )
    assert not rv.stderr
    return rv.stdout.decode('utf-8','replace')

def run_py( *args ):
    import sys
    code = ( 'import sys; import mcpldev;'
             ' mcpldev.app_mcpltool(["mcpltool"]+sys.argv[1:])' )
    rv = subprocess.run( [sys.executable,'-c',code]+[str(a) for a in args],
                         capture_output = True, check = True )
    assert not rv.stderr
    return rv.stdout.decode('utf-8','replace')

def without_filename_and_version( dump ):
    return [ line for line in dump.splitlines()
             if 'Opened MCPL file' not in line
             and not line.strip().startswith('Format ') ]

def particles( fn ):
    with mcpl.MCPLFile(fn) as f:
        assert f.userdata_layout is None and f.userdata_size == 0
        return [ ( p.pdgcode, tuple(p.position), tuple(p.direction), p.ekin,
                   p.time, p.weight, tuple(p.polarisation), p.userflags )
                 for p in f.particles ]

def fmt4_problem( fn ):
    """Reason why a file in version 3 can not become a file in version 4 (None
    if it can): NaN or infinite values in the particle fields, or blob keys
    which are not allowed in version 4 (non-empty, ASCII, no non-printable
    characters, whitespace, backslash, or quotation marks)."""
    import numpy as np
    with mcpl.MCPLFile(fn) as f:
        for key in f.blobs:
            k = key.encode() if isinstance(key,str) else key
            if not k or not all( 33 <= c <= 126 and c not in b'"\'\\`'
                                 for c in k ):
                return f'blob key {key!r} not allowed in MCPL-4'
        for b in f.particle_blocks:
            for a in ( b.position, b.direction, b.ekin, b.time, b.weight,
                       b.polarisation ):
                if not np.all(np.isfinite(a)):
                    return 'NaN or infinite values in the particle data'
    return None

def check( src, f3 ):
    f4 = pathlib.Path( 'v4_' + f3.name )
    set_version( f3, f4, b'004' )
    print(f'{src.name}:')
    with mcpl.MCPLFile(f4) as f:
        assert f.version == 4, f.version
    #Same header and particles in the dumps (C and Python):
    for runner, name in ( (run_c,'C'), (run_py,'Python') ):
        d3 = runner( '-l0', f3 )
        d4 = runner( '-l0', f4 )
        assert 'MCPL-3' in d3 and 'MCPL-4' in d4
        d3 = without_filename_and_version( d3 )
        d4 = without_filename_and_version( d4 )
        assert d3 == d4, (name, d3, d4)
        print(f'  {name}: same dump as MCPL-3')
    assert particles(f3) == particles(f4)
    print('  Python: same particles as MCPL-3')
    #Merging with the MCPL-3 file, and extracting (which give MCPL-3 files):
    for runner, name in ( (run_c,'C'), (run_py,'Python') ):
        out = pathlib.Path(f'merged_{name}_{f3.name}')
        runner( '--merge', out, f4, f3 )
        with mcpl.MCPLFile(out) as f:
            assert f.version == 3
        assert particles(out) == particles(f3) * 2
        out = pathlib.Path(f'extracted_{name}_{f3.name}')
        runner( '--extract', f4, out )
        assert particles(out) == particles(f3)
        print(f'  {name}: merging with the MCPL-3 file and extracting work')
    #Round trips: version 3 -> 4 -> 3, and version 4 -> 3 -> 4:
    f3b = pathlib.Path( 'back_' + f3.name )
    set_version( f4, f3b, b'003' )
    assert f3b.read_bytes() == f3.read_bytes()
    f4b = pathlib.Path( 'back_' + f4.name )
    set_version( f3b, f4b, b'004' )
    assert f4b.read_bytes() == f4.read_bytes()
    print('  Round trips MCPL-3 -> MCPL-4 -> MCPL-3 and back give the same files')

def check_with_userdata():
    print('With userdata:')
    fn = pathlib.Path('withud.mcpl')
    for userflags in ( False, True ):
        with mcpl.MCPLOutFile( fn, userdata_layout = 'temp:float32',
                               opt_userflags = userflags ):
            pass
        data = fn.read_bytes()
        assert data[0:7] == b'MCPL004'
        flags = int.from_bytes(data[24:28],'little')
        assert flags == ( 0x3 if userflags else 0x2 ), flags
        for runner in ( run_c, run_py ):
            runner( '-l0', fn )
        #Invalid values of the userflags field in version 4:
        for bad in ( 0x4, 0x6, 0xff ):
            badfn = pathlib.Path(f'bad{bad}.mcpl')
            badfn.write_bytes( data[0:24] + bad.to_bytes(4,'little')
                               + data[28:] )
            try:
                mcpl.MCPLFile(badfn)
            except mcpl.MCPLError as e:
                assert 'userflags field' in str(e)
            else:
                raise AssertionError('invalid userflags field not detected')
            rv = subprocess.run( [mcpltool_cmd,'-l0',str(badfn)],
                                 capture_output = True, check = False )
            assert rv.returncode != 0 and b'userflags field' in rv.stdout+rv.stderr
    print('  0x2 in the userflags field, invalid values detected (C and Python)')

def expect_open_failure( fn, errmsg_part ):
    try:
        mcpl.MCPLFile(fn)
    except mcpl.MCPLError as e:
        assert errmsg_part in str(e), str(e)
    else:
        raise AssertionError(f'Python reader did not refuse {fn}')
    rv = subprocess.run( [mcpltool_cmd,'-l0',str(fn)],
                         capture_output = True, check = False )
    assert rv.returncode != 0 and errmsg_part.encode() in rv.stdout+rv.stderr, rv

def check_header_rules():
    print('Header rules:')
    src = test_data_dir / 'ref' / 'reffile_1.mcpl'
    data3 = src.read_bytes()
    data4 = b'MCPL004' + data3[7:]
    #Flags must have exactly the values of the format (and in version 4 the
    #userflags field can also have 0x2):
    fields = { 24 : 'userflags field', 28 : 'polarisation field',
               32 : 'precision field', 44 : 'universal weight field' }
    for version, data in ( (3, data3), (4, data4) ):
        for pos, what in fields.items():
            values = [ 2, 0x100, 0xffffffff ]
            if version == 4 and pos == 24:
                values = [ 4, 6, 0x100, 0xffffffff ]
            for value in values:
                fn = pathlib.Path(f'badflag_v{version}_{pos}_{value}.mcpl')
                fn.write_bytes( data[0:pos] + value.to_bytes(4,'little')
                                + data[pos+4:] )
                expect_open_failure( fn, f'unexpected value of {what}' )
    print('  Invalid values of the flags detected in MCPL-3 and MCPL-4'
          ' (C and Python)')
    #The particle size must be consistent with the other fields:
    psize = int.from_bytes(data3[40:44],'little')
    for version, data in ( (3, data3), (4, data4) ):
        for value in ( 0, psize - 1, psize + 1, psize + 4 ):
            fn = pathlib.Path(f'badpsize_v{version}_{value}.mcpl')
            fn.write_bytes( data[0:40] + value.to_bytes(4,'little')
                            + data[44:] )
            expect_open_failure( fn, 'unexpected particle size' )
    print('  Inconsistent particle sizes detected in MCPL-3 and MCPL-4'
          ' (C and Python)')
    #The universal weight must be positive and finite:
    import struct
    src = test_data_dir / 'ref' / 'reffile_uw.mcpl.gz'
    datauw = gzip.decompress(src.read_bytes())
    assert int.from_bytes(datauw[44:48],'little') == 1
    for value in ( 0.0, -0.0, -1.0, float('inf'), float('nan') ):
        fn = pathlib.Path(f'baduw_{value}.mcpl')
        fn.write_bytes( datauw[0:48] + struct.pack('<d',value) + datauw[56:] )
        expect_open_failure( fn, 'invalid universal weight' )
    print('  Invalid universal weights detected (C and Python)')
    #Strings must not contain null characters (here in the source name, which
    #starts after the 48 bytes of the first part of the header, with a UINT32
    #with its length):
    lsrc = int.from_bytes(data3[48:52],'little')
    assert lsrc >= 2
    fn = pathlib.Path('nullchar.mcpl')
    fn.write_bytes( data3[0:53] + b'\0' + data3[54:] )
    expect_open_failure( fn, 'unexpected null-byte' )
    print('  Null characters in strings detected (C and Python)')
    #Blob keys in version 4: non-empty, ASCII, no non-printable characters,
    #whitespace, backslash, or quotation marks (including backtick):
    src = test_data_dir / 'ref' / 'reffile_encodings.mcpl.gz'
    data3 = gzip.decompress(src.read_bytes())
    fn3 = pathlib.Path('badkeys_v3.mcpl')
    fn3.write_bytes( data3 )
    run_c( '-l0', fn3 )
    run_py( '-l0', fn3 )
    fn4 = pathlib.Path('badkeys_v4.mcpl')
    set_version( fn3, fn4, b'004' )
    expect_open_failure( fn4, 'File has an invalid blob key' )
    print('  Invalid blob keys accepted in MCPL-3 but not in MCPL-4'
          ' (C and Python)')
    #The Python writer refuses invalid keys, but copies them from the headers
    #of MCPL-3 files, except to files with userdata (MCPL-4). The C writer is
    #tested in the same way in the genisotrop and userdata tests:
    for key in ( '', 'a b', 'a"b', "a'b", 'a\\b', 'a`b', 'a\tb', 'bl\u00f8b' ):
        with mcpl.MCPLOutFile('pybadkey.mcpl') as o:
            try:
                o.hdr_add_data(key,b'data')
            except mcpl.MCPLError as e:
                assert 'invalid key' in str(e)
            else:
                raise AssertionError(f'key {key!r} not refused')
    with mcpl.MCPLFile(fn3, raw_strings=True) as src, \
         mcpl.MCPLOutFile('pycopiedkeys.mcpl') as o:
        o.transfer_metadata(src)
    with mcpl.MCPLFile(fn3, raw_strings=True) as src:
        o = mcpl.MCPLOutFile('pycopiedkeys_ud.mcpl')
        o.transfer_metadata(src)
        o.enable_userdata('p:int8')
        try:
            o.close()
        except mcpl.MCPLError as e:
            assert 'invalid blob key copied from an input file' in str(e)
        else:
            raise AssertionError('copied invalid keys accepted with userdata')
    print('  Python writer refuses invalid keys, but copies them from MCPL-3'
          ' files without userdata')
    #The Python writer refuses null characters in strings:
    for fct, arg in ( ('hdr_set_srcname','a\0b'), ('hdr_add_comment','a\0b') ):
        with mcpl.MCPLOutFile('pynullchar.mcpl') as o:
            try:
                getattr(o,fct)(arg)
            except mcpl.MCPLError as e:
                assert 'null characters' in str(e)
            else:
                raise AssertionError(f'{fct} accepted null character')
    print('  Python writer refuses null characters in strings')

def main():
    #All reference files in version 3 which can be read without problems:
    nchecked = 0
    for src in sorted( (test_data_dir / 'ref').glob('*.mcpl*') ):
        f3 = pathlib.Path( 'v3_' + src.name.replace('.mcpl.gz','_gz.mcpl') )
        data = src.read_bytes()
        try:
            data = gzip.decompress(data) if src.name.endswith('.gz') else data
        except (OSError, EOFError):
            print(f'{src.name}: skipped (not a valid gzip file)')
            continue
        if data[0:7] != b'MCPL003':
            print(f'{src.name}: skipped (not in version 3)')
            continue
        f3.write_bytes( data )
        rv = subprocess.run( [mcpltool_cmd,'-l0',str(f3)],
                             capture_output = True, check = False )
        if rv.returncode != 0 or rv.stderr or b'WARNING' in rv.stdout:
            print(f'{src.name}: skipped (can not be read without problems)')
            continue
        problem = fmt4_problem( f3 )
        if problem:
            print(f'{src.name}: skipped ({problem})')
            continue
        check( src, f3 )
        nchecked += 1
    assert nchecked >= 15, nchecked
    check_with_userdata()
    check_header_rules()

if __name__ == '__main__':
    main()
