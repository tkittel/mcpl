
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

"""Operations on whole MCPL files."""

__all__ = [
    'can_merge',
    'convert2ascii',
    'create_outfile_mpi',
    'dump_file',
    'forcemerge_files',
    'merge_files',
    'merge_inplace',
    'merge_outfiles_mpi',
    'name_helper',
    'repair',
]

import os

from ._common import MCPLError, _determine_version
from ._messages import _info, _warning
from ._reader import MCPLFile
from ._statsum import _parse_statsum_comment, _statsum_syntax_error, encode_stat_sum
from ._writer import MCPLOutFile


def dump_file(filename,header=True,particles=True,limit=10,skip=0,pick=None,**kwargs):
    """Python equivalent of mcpl_dump(..) function from mcpl.h, which can be used to
    dump both header and particle contents of a file to stdout. If pick is
    given (an expression or a ParticleFilter), only the picked particles are
    shown."""
    with MCPLFile(filename,**kwargs) as f:
        print(f"Opened MCPL file {os.path.basename(filename)}:")
        if header:
            f.dump_hdr()
        if particles:
            if pick is not None:
                from ._expressions import _as_filter
                print(f"Showing particles picked with: {_as_filter(pick).expression}")
                print()
            f.dump_particles(limit=limit,skip=skip,pick=pick)

def convert2ascii(mcplfile,outfile):
    """Read particle contents of mcplfile and write into outfile using a simple ASCII-based format"""
    if not hasattr(outfile,'write'):
        with open(outfile,'w') as fh:
            convert2ascii(mcplfile,fh)
        return
    if not isinstance(mcplfile,MCPLFile):
        with MCPLFile(mcplfile) as mfh:
            convert2ascii(mfh,outfile)
        return

    fout = outfile
    fin = mcplfile
    fout.write(f"#MCPL-ASCII\n#ASCII-FORMAT: v1\n#NPARTICLES: {fin.nparticles}\n")
    #Userdata is not included in the output, which is noted in the header:
    if fin.userdata_size:
        fout.write("#WARNING: The userdata of the particles in the MCPL file is"
                   " not included\n")
    fout.write("#END-HEADER\n")
    fout.write("index     pdgcode               ekin[MeV]                   x[cm]          "
               +"         y[cm]                   z[cm]                      ux                  "
               +"    uy                      uz                time[ms]                  weight  "
               +"                 pol-x                   pol-y                   pol-z  userflags\n")
    fmtstr="%5i %11i %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g 0x%08x\n"
    for idx,p in enumerate(fin.particles):
        fout.write(fmtstr%(idx,p.pdgcode,p.ekin,p.x,p.y,p.z,p.ux,p.uy,p.uz,p.time,p.weight,p.polx,p.poly,p.polz,p.userflags))

def _open_raw(filename, **kw):
    return MCPLFile(filename, raw_strings = True, **kw)

def _comment_positions(f):
    """Positions in the file of the comment strings of MCPLFile f (pairs of
    position and comment)"""
    h = f._hdr
    pos = 8 + 8 + 32 + (8 if f.opt_universalweight else 0)
    pos += 4 + len(h['sourcename'])
    res = []
    for c in h['comments']:
        pos += 4
        res.append((pos,c))
        pos += len(c)
    return res

def _statsum_entries(f):
    """List of (comment index, key, value) for the stat:sum entries of MCPLFile f
    (value is -1.0 when not available)"""
    res = []
    for i,c in enumerate(f._hdr['comments']):
        if c.startswith(b'stat:sum:'):
            ok, (key, value) = _parse_statsum_comment(c)
            if not ok:
                raise MCPLError(_statsum_syntax_error(c))
            res.append((i, key, -1.0 if value is None else value))
    return res

def _merge_incompat_reason(f1, f2):
    """Why two files (MCPLFile objects opened with raw strings) can not be
    merged, i.e. the first difference found in their headers, or None if they
    can be merged (like mcpl_internal_merge_compat in mcpl.c, with the same
    messages)."""
    #Very strict checking of everything except nparticles. Even order of blobs
    #and comments must be preserved:
    def trunc(b):
        s = b.decode('utf-8','replace')
        return s[:60] + ( '...' if len(s) > 60 else '' )
    if f1._hdr['sourcename'] != f2._hdr['sourcename']:
        return ( f'source name: "{trunc(f1._hdr["sourcename"])}" vs'
                 f' "{trunc(f2._hdr["sourcename"])}"' )
    yn = ( 'no', 'yes' )
    if f1.opt_userflags != f2.opt_userflags:
        return f'userflags: {yn[f1.opt_userflags]} vs {yn[f2.opt_userflags]}'
    if f1.opt_polarisation != f2.opt_polarisation:
        return ( f'polarisation info: {yn[f1.opt_polarisation]} vs'
                 f' {yn[f2.opt_polarisation]}' )
    if f1.opt_singleprec != f2.opt_singleprec:
        sd = { True : 'single', False : 'double' }
        return f'FP precision: {sd[f1.opt_singleprec]} vs {sd[f2.opt_singleprec]}'
    if f1.opt_universalpdgcode != f2.opt_universalpdgcode:
        return ( 'universal pdgcode: '
                 f'{f1.opt_universalpdgcode or "none"} vs'
                 f' {f2.opt_universalpdgcode or "none"}' )
    if f1.opt_universalweight != f2.opt_universalweight:
        def w(v):
            return f'{v:g}' if v else 'none'
        return ( 'universal weight: '
                 f'{w(f1.opt_universalweight)} vs {w(f2.opt_universalweight)}' )
    if f1.endianness != f2.endianness:
        lb = { 'L' : 'little', 'B' : 'big' }
        return f'endianness: {lb[f1.endianness]} vs {lb[f2.endianness]}'
    if f1.userdata_layout != f2.userdata_layout:
        def ud(v):
            return f'"{v[:200]}"' if v is not None else 'none'
        return ( 'userdata layout: '
                 f'{ud(f1.userdata_layout)} vs {ud(f2.userdata_layout)}' )
    c1s, c2s = f1._hdr['comments'], f2._hdr['comments']
    if len(c1s) != len(c2s):
        return f'number of comments: {len(c1s)} vs {len(c2s)}'
    for i, (c1, c2) in enumerate(zip(c1s, c2s)):
        if c1 != c2:
            #incompatible, unless it represents the same stat:sum: entry.
            same_statsum = False
            if c1.startswith(b'stat:sum:') and c2.startswith(b'stat:sum:'):
                ok1, (k1, _) = _parse_statsum_comment(c1)
                ok2, (k2, _) = _parse_statsum_comment(c2)
                same_statsum = ok1 and ok2 and k1 == k2
            if not same_statsum:
                return f'comment {i} differs'
    k1s, k2s = f1._hdr['blobkeys'], f2._hdr['blobkeys']
    if len(k1s) != len(k2s):
        return f'number of blobs: {len(k1s)} vs {len(k2s)}'
    for i, (k1, k2) in enumerate(zip(k1s, k2s)):
        if k1 != k2:
            return f'blob {i} key differs'
        if f1._hdr['blobs'][k1] != f2._hdr['blobs'][k2]:
            return f'blob {i} data differs'
    #Should be unreachable given the checks above, but to be safe:
    if f1.particlesize != f2.particlesize:
        return f'particle size: {f1.particlesize} vs {f2.particlesize} bytes'
    if f1.headersize != f2.headersize:
        return 'header size differs'
    return None

def _actual_can_merge(f1, f2):
    return _merge_incompat_reason(f1, f2) is None

def can_merge(file1, file2):
    """Check if two MCPL files can be merged (like mcpl_can_merge in the C
    API). This requires everything in the headers except the number of
    particles and the values of stat:sum entries to be identical."""
    with _open_raw(file1) as f1, _open_raw(file2) as f2:
        return _actual_can_merge(f1, f2)

def _file_certainly_exists(filename):
    import pathlib
    return pathlib.Path(filename).is_file()

def _is_same_file(f1, f2):
    import pathlib
    try:
        return pathlib.Path(f1).samefile(f2)
    except OSError:
        return False

def _error_on_dups(files):
    for i in range(len(files)):
        for j in range(i):
            if _is_same_file(files[i], files[j]):
                raise MCPLError('Merging file with itself')

def _stablesum_add(s, x):
    """Numerically stable summation (Neumaier's algorithm, like in mcpl.c). s is
    a list [naive sum, correction]."""
    import math
    t = s[0] + x
    if ( ( math.isinf(t) or math.isinf(s[0]) or math.isinf(x) )
         and ( s[0] >= 0.0 ) == ( x >= 0.0 ) ):
        #same sign infinities, avoid NaN by going directly to infinity:
        s[0], s[1] = math.inf, 0.0
        return
    s[1] += (s[0] - t) + x if abs(s[0]) >= abs(x) else (x - t) + s[0]
    s[0] = t

def merge_files(file_output, files, *, dry_run = False):
    """Merge the particle contents of a list of compatible files into a new file
    (like mcpl_merge_files in the C API). Values of stat:sum entries are
    added up. Returns the new file as an open MCPLOutFile object, which must
    be closed with close() or closeandgzip(). With dry_run=True, everything
    is done except writing (nothing is created or modified), and None is
    returned."""
    import math
    files = [ os.fspath(f) for f in files ]
    file_output = os.fspath(file_output)
    if not files:
        raise MCPLError('merge_files must be called with at least one input file')
    _error_on_dups(files)
    for f in files[1:]:
        with _open_raw(files[0]) as f1, _open_raw(f) as f2:
            reason = _merge_incompat_reason(f1, f2)
        if reason is not None:
            raise MCPLError(f'Attempting to merge incompatible files ({reason}).')
    if _file_certainly_exists(file_output):
        raise MCPLError('requested output file of merge_files already exists')
    out = MCPLOutFile(file_output, _dry_run = dry_run)
    try:
        warned_oldversion = False
        scinfo = None
        for ifile, fn in enumerate(files):
            with _open_raw(fn) as fi:
                if ifile == 0:
                    out.transfer_metadata(fi)
                    scinfo = []
                    for _, key, value in _statsum_entries(fi):
                        s = [0.0, 0.0]
                        if value == -1.0:
                            s[0] = -1.0
                        else:
                            _stablesum_add(s, value)
                        scinfo.append((key, s))
                        if value != -1.0:
                            out.hdr_add_stat_sum(key, -1.0)
                    out._write_header()
                else:
                    for (key, s), (_, _, value) in zip(scinfo, _statsum_entries(fi)):
                        if s[0] == -1.0 and s[1] == 0.0:
                            continue
                        if value == -1.0:
                            s[0], s[1] = -1.0, 0.0
                        else:
                            _stablesum_add(s, value)
                if fi.version >= 3:
                    #Can transfer raw bytes (like in C, without checking the
                    #values of the particles). Particles are encoded in the
                    #same way in format versions 3 and 4, and versions 2 and 4
                    #can not be mixed, since the userdata layouts must be the
                    #same:
                    fi._check_nonfinite = False
                    for b in fi.particle_blocks:
                        out._write_records(b._data)
                else:
                    if not warned_oldversion:
                        warned_oldversion = True
                        _warning('Merging files from older MCPL'
                                 ' format. Output will be in latest format.')
                    for b in fi.particle_blocks:
                        out.add_particles(position=b.position, direction=b.direction,
                                          polarisation=b.polarisation, ekin=b.ekin,
                                          time=b.time, weight=b.weight,
                                          pdgcode=b.pdgcode, userflags=b.userflags)
    except BaseException:
        out._abort()
        raise
    warned_statsuminf = False
    for key, s in scinfo:
        val = s[0] + s[1]
        if val == -1.0:
            continue
        if math.isinf(val):
            if not warned_statsuminf:
                warned_statsuminf = True
                _warning('Merging files results in one or more'
                         ' stat:sum: entries overflowing floating point'
                         ' range and producing infinity. Reverting value to -1'
                         ' to indicate that a precise result is not available.')
            continue
        out.hdr_add_stat_sum(key, val)
    if dry_run:
        out.close()
        return None
    return out

def forcemerge_files(file_output, files, *, keep_userflags = False, dry_run = False):
    """Merge particle contents of a list of files, even if they are not
    compatible, at the price of discarding most meta-data like comments and
    blobs (like mcpl_forcemerge_files in the C API). Userflags are discarded
    unless keep_userflags is set. Returns the new file as an open MCPLOutFile
    object, which must be closed with close() or closeandgzip(). With
    dry_run=True, everything is done except writing (nothing is created or
    modified), and None is returned."""
    files = [ os.fspath(f) for f in files ]
    file_output = os.fspath(file_output)
    if not files:
        raise MCPLError('forcemerge_files must be called with at least one input file')
    _error_on_dups(files)
    if _file_certainly_exists(file_output):
        raise MCPLError('requested output file of forcemerge_files already exists')
    if all( can_merge(files[0], f) for f in files[1:] ):
        _info(f'forcemerge_files called with {len(files)} files that are'
              ' compatible for a standard merge => falling back to'
              ' standard merge_files function', prefix = 'MCPL ')
        return merge_files(file_output, files, dry_run = dry_run)
    opt_dp = opt_pol = opt_uf = False
    lastseen_pdg, disallow_pdg = 0, False
    lastseen_w, disallow_w = 0.0, False
    #Userdata is kept only if all files have the same layout:
    udlayouts = set()
    #For reporting which settings change relative to the input files:
    any_sp = any_nopol = any_nouf = any_updg = any_uw = any_metadata = False
    for fn in files:
        with _open_raw(fn) as f:
            if not f.nparticles:
                continue
            udlayouts.add(f.userdata_layout)
            opt_uf = opt_uf or bool(f.opt_userflags)
            opt_pol = opt_pol or bool(f.opt_polarisation)
            opt_dp = opt_dp or not f.opt_singleprec
            any_nouf = any_nouf or not f.opt_userflags
            any_nopol = any_nopol or not f.opt_polarisation
            any_sp = any_sp or bool(f.opt_singleprec)
            any_metadata = any_metadata or bool( f._hdr['comments']
                                                 or f._hdr['blobkeys'] )
            any_updg = any_updg or bool(f.opt_universalpdgcode)
            any_uw = any_uw or bool(f.opt_universalweight)
            updg = f.opt_universalpdgcode
            if not updg or ( lastseen_pdg and lastseen_pdg != updg ):
                disallow_pdg = True
            else:
                lastseen_pdg = updg
            uw = f.opt_universalweight
            if not uw or ( lastseen_w and lastseen_w != uw ):
                disallow_w = True
            else:
                lastseen_w = uw
    #Report the settings which change relative to the input files (and
    #discarded data), like in mcpl.c:
    fm = 'force-merge: '
    if opt_dp and any_sp:
        _info(fm + 'Files have different FP precision (single and double),'
              ' using double', prefix = 'MCPL ')
    if opt_pol and any_nopol:
        _info(fm + 'Files have different polarisation info (no and yes),'
              ' enabling it', prefix = 'MCPL ')
    if opt_uf and not keep_userflags:
        _info(fm + 'Discarding userflags of the input files (keep_userflags'
              ' is not set)', prefix = 'MCPL ')
    elif opt_uf and any_nouf:
        _info(fm + 'Files have different userflags (no and yes), enabling'
              ' them (zero for particles without)', prefix = 'MCPL ')
    if any_updg and disallow_pdg:
        _info(fm + 'Not all files have the same universal pdgcode, storing'
              ' the pdgcode per particle', prefix = 'MCPL ')
    if any_uw and disallow_w:
        _info(fm + 'Not all files have the same universal weight, storing'
              ' the weight per particle', prefix = 'MCPL ')
    if any_metadata:
        _info(fm + 'Discarding comments and blobs of the input files',
              prefix = 'MCPL ')
    if len(udlayouts) > 1:
        _warning('Discarding userdata in forced merge, since not all files have'
                 ' the same userdata layout.')
    out = MCPLOutFile( file_output, _dry_run = dry_run,
                       sourcename = ( 'mcpl_forcemerge_files (from MCPL v'
                                      f'{_determine_version()})' ),
                       opt_userflags = opt_uf and keep_userflags,
                       opt_polarisation = opt_pol,
                       opt_singleprec = not opt_dp,
                       opt_universalpdgcode = 0 if disallow_pdg else lastseen_pdg,
                       opt_universalweight = 0.0 if disallow_w else lastseen_w )
    if len(udlayouts) == 1 and None not in udlayouts:
        out.enable_userdata(udlayouts.pop())
    try:
        for fn in files:
            with _open_raw(fn) as f:
                np_ = f.nparticles
                _info(f'force-merge: Transferring {np_} particle'
                      f'{"" if np_==1 else "s"} from file {fn}', prefix = 'MCPL ')
                for b in f.particle_blocks:
                    out.add_particles(b)
    except BaseException:
        out._abort()
        raise
    np_ = out.nparticles
    _info(f'force-merge: {"Would transfer" if dry_run else "Transferred"} a'
          f' total of {np_} particle{"" if np_==1 else "s"} to new file'
          f' {file_output}', prefix = 'MCPL ')
    if dry_run:
        out.close()
        return None
    return out

def merge_inplace(file1, file2, *, dry_run = False):
    """Append the particle contents of file2 to file1 (like mcpl_merge_inplace in
    the C API). The files must be compatible, and file1 must not be
    gzipped. Values of stat:sum entries are added up. With dry_run=True,
    everything is done except writing (nothing is modified)."""
    import math
    import struct
    file1, file2 = os.fspath(file1), os.fspath(file2)
    if _is_same_file(file1, file2):
        raise MCPLError('Merging file with itself')
    with _open_raw(file1) as f1, _open_raw(file2) as f2:
        reason = _merge_incompat_reason(f1, f2)
        if reason is not None:
            raise MCPLError(f'Attempting to merge incompatible files ({reason}).')
        if f1.version != f2.version:
            raise MCPLError('Attempting to merge incompatible files (can not'
                            ' mix MCPL format versions when merging inplace)')
        if f1._is_gz:
            raise MCPLError('direct modification of gzipped files is not supported.')
        np1, np2 = f1.nparticles, f2.nparticles
        if not np2:
            return
        psize, first_particle_pos = f1.particlesize, f1.headersize
        positions = { i: p for i,(p,_) in enumerate(_comment_positions(f1)) }
        updates = []
        sc2 = { k : v for _,k,v in _statsum_entries(f2) }
        for i, key, value in _statsum_entries(f1):
            newval = -1.0
            if value != -1.0 and sc2[key] != -1.0:
                newval = value + sc2[key]
                if math.isinf(newval):
                    _warning('Merging files results in one or more'
                             ' stat:sum: entries overflowing floating point'
                             ' range and producing infinity. Reverting value to -1'
                             ' to indicate that a precise result is not available.')
                    newval = -1.0
            updates.append((positions[i], key, newval))
        if dry_run:
            return
        try:
            fh = open(file1,'r+b')  # noqa: SIM115
        except OSError:
            raise MCPLError('Unable to open file1 in update mode!')
        with fh:
            def write_at(pos, data):
                fh.seek(pos)
                fh.write(data)
            #While transferring, the file appears broken and in need of repair:
            write_at(8, struct.pack('=Q', 0))
            for pos, key, _ in updates:
                write_at(pos, encode_stat_sum(key, -1.0).encode('ascii'))
            fh.seek(first_particle_pos + psize * np1)
            f2._check_nonfinite = False
            fh.writelines(b._data.tobytes() for b in f2.particle_blocks)
            for pos, key, newval in updates:
                if newval != -1.0:
                    write_at(pos, encode_stat_sum(key, newval).encode('ascii'))
            write_at(8, struct.pack('=Q', np1 + np2))

def repair(filename, *, dry_run = False):
    """Repair a file which was not properly closed, or which was truncated, by
    updating the number of particles in the header and removing any
    incomplete particle data at the end (like mcpl_repair in the C API).
    With dry_run=True, everything is done except writing (nothing is
    modified)."""
    import pathlib
    import struct
    filename = os.fspath(filename)
    with _open_raw(filename, _recover = False) as f:
        nparticles = f.nparticles
        if f._is_gz:
            if nparticles == 0:
                if len(f._fileread(dtype='u1',count=1)):
                    raise MCPLError('Input file is indeed broken, but must be'
                                    ' gunzipped before it can be repaired.')
                raise MCPLError('File does not appear to be broken.')
            raise MCPLError('File must be gunzipped before it can be checked'
                            ' and possibly repaired.')
        ndata = pathlib.Path(filename).stat().st_size - f.headersize
        if ndata < 0:
            raise MCPLError('File does not appear to be broken.')
        np_ = ndata // f.particlesize
        if np_ == nparticles and not ndata % f.particlesize:
            raise MCPLError('File does not appear to be broken.')
        if nparticles > 0 and np_ > nparticles:
            raise MCPLError('Input file has invalid combination of meta-data & filesize.')
        positions = { i: p for i,(p,_) in enumerate(_comment_positions(f)) }
        statsums = [ (positions[i], key) for i, key, value in _statsum_entries(f)
                     if value != -1.0 ]
        headersize, psize = f.headersize, f.particlesize
    for _, key in statsums:
        _warning(f'Marking stat:sum:{key} entry as not available'
                 ' (-1) since file not closed properly.')
    if dry_run:
        _info(f'Would repair file with {np_} particles.')
        return
    with open(filename,'r+b') as fh:
        for pos, key in statsums:
            fh.seek(pos)
            fh.write(encode_stat_sum(key, -1.0).encode('ascii'))
        fh.truncate(headersize + np_ * psize)
        fh.seek(8)
        fh.write(struct.pack('=Q', np_))
    _info(f'Successfully repaired file with {np_} particles.')

def _absolute_path(path):
    #Like mctools_absolute_path in C. Not with pathlib, which would also
    #remove "." components (unlike the C code on non-Windows platforms):
    if os.name == 'nt':
        return os.path.abspath(path)
    return path if os.path.isabs(path) else os.path.join(os.getcwd(), path)

def _namehelper(filename, iproc, mode):
    fn = os.fspath(filename)
    for ending in ('.mcpl', '.mcpl.gz'):
        fn = fn.removesuffix(ending)
    fn = _absolute_path(fn)
    if mode in ('m', 'g'):
        fn += f'.mpiworker{iproc}'
        mode = mode.upper()
    if mode == 'M':
        return fn + '.mcpl'
    if mode == 'G':
        return fn + '.mcpl.gz'
    if mode == 'B':
        return fn
    raise MCPLError('internal namehelper: bad mode')

def name_helper(filename, mode):
    """Estimate the output name of a given filename (like mcpl_name_helper in the
    C API), which can be relative or absolute and with or without .mcpl or
    .mcpl.gz suffixes. The mode controls the returned name: "M" for
    /abs/path/base.mcpl, "G" for /abs/path/base.mcpl.gz, "B" for
    /abs/path/base, and "m", "g", "b" for the same without the directory."""
    if mode not in ('M', 'G', 'B', 'm', 'g', 'b'):
        raise MCPLError('name_helper: invalid mode')
    res = _namehelper(filename, 0, mode.upper())
    import pathlib
    return res if mode.isupper() else pathlib.PurePath(res).name

def create_outfile_mpi(filename, iproc, nproc, **kwargs):
    """Create output file for worker process iproc out of nproc (like
    mcpl_create_outfile_mpi in the C API). The worker files must be closed
    with closeandgzip(), after which merge_outfiles_mpi can be used to merge
    them into the final file. Keyword arguments are passed on to
    MCPLOutFile."""
    if nproc > 100000000:
        raise MCPLError('create_outfile_mpi: nproc too large')
    if nproc == 0:
        raise MCPLError('create_outfile_mpi: nproc must be larger than 0')
    if iproc >= nproc:
        raise MCPLError('create_outfile_mpi: iproc must be less than nproc')
    return MCPLOutFile(_namehelper(filename, iproc, 'm' if nproc > 1 else 'M'), **kwargs)

def merge_outfiles_mpi(filename, nproc):
    """Merge the gzipped worker files created with create_outfile_mpi into the
    final gzipped output file and remove them (like mcpl_merge_outfiles_mpi in
    the C API)."""
    if nproc > 100000000:
        raise MCPLError('merge_outfiles_mpi: nproc too large')
    if nproc == 0:
        raise MCPLError('merge_outfiles_mpi: nproc must be larger than 0')
    import pathlib
    if nproc == 1:
        fngz = _namehelper(filename, 0, 'G')
        if not pathlib.Path(fngz).is_file():
            raise MCPLError(f'merge_outfiles_mpi: expected output file "{fngz}"'
                            ' from iproc=0 not found.')
        return
    targetfn = _namehelper(filename, 0, 'M')
    fns = [ _namehelper(filename, iproc, 'g') for iproc in range(nproc) ]
    out = merge_files(targetfn, fns)
    for fn in fns:
        f = pathlib.Path(fn)
        f.unlink()
        _info(f'Removing file {f.name}')
    if not out.closeandgzip():
        raise MCPLError('merge_outfiles_mpi: problems gzipping final output')
