
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

"""The mcpltool command."""

__all__ = ['app_mcpltool', 'app_pymcpltool']

import os
import re
import sys

from ._common import MCPLError, _determine_version, _output_bytearray_raw
from ._extract import _mcpltool_close, _mcpltool_extract, _tool_outfn
from ._fileops import (
    convert2ascii,
    dump_file,
    forcemerge_files,
    merge_files,
    merge_inplace,
    repair,
)
from ._messages import _ForcePrinting, _info
from ._particles import _particle_names
from ._reader import MCPLFile

_short_help = """
Tool for inspecting or modifying Monte Carlo Particle List (.mcpl) files.

Usage:
  PROGNAME [options] FILE                  Show the header and first particles
  PROGNAME -S [options] FILE               Summary of the particles
  PROGNAME -w [options] FILE               View the particles interactively
  PROGNAME -H HIST [options] FILE [...]    Histogram
  PROGNAME -e [options] FILE OUT.mcpl.gz   Extract particles into a new file
  PROGNAME -m OUT.mcpl.gz FILE1 FILE2 ...  Merge compatible files
  PROGNAME -r FILE                         Repair a file not properly closed

Common options:
  -lN, -sN       Use only N particles, or skip the first N particles.
  -p PICK        Only particles for which PICK is true, e.g.
                 -p "pdgcode == neutron and ekin < 25meV".
  -E EDIT        Change particles, e.g. -E "z += 1cm;weight *= 0.5".
  -t             Show plots in the terminal.
  -o FILE        Save the plot in FILE (.png, .pdf, .svg or .txt).
  -d             Dry run: do everything except writing files.

Examples:
  PROGNAME -H "ekin/MeV;logx=1;split=pdgcode" file.mcpl.gz
  PROGNAME -e -p "pdgcode == neutron" file.mcpl.gz neutrons.mcpl.gz
  PROGNAME -S file.mcpl.gz

More help:
  --full-help              All options.
  -p help, -E help, -H help
                           How to write PICK, EDIT and HIST.
"""

_full_help = """
Tool for inspecting or modifying Monte Carlo Particle List (.mcpl) files.

Usage:
  PROGNAME [options] FILE                  Show the header and first particles
  PROGNAME -S [options] FILE               Summary of the particles
  PROGNAME -w [options] FILE               View the particles interactively
  PROGNAME -H HIST [options] FILE [...]    Histogram
  PROGNAME -e [options] FILE OUT.mcpl.gz   Extract particles into a new file
  PROGNAME -m OUT.mcpl.gz FILE1 FILE2 ...  Merge compatible files
  PROGNAME --forcemerge OUT.mcpl.gz FILE1 FILE2 ...
  PROGPADS                                 Merge also incompatible files
  PROGNAME -r FILE                         Repair a file not properly closed
  PROGNAME --text FILE OUT.txt             Write the particles as text
  PROGNAME --create-examples[=N]           Create example files
  PROGNAME -v | -h | --full-help

Particles (when showing particles, and with -S, -w, -H and -e):
  -lN, -sN         Use only N particles (all with -l0), or skip the first N
                   particles in the file. Without -l, at most 10 particles are
                   shown when showing particles.
  -p, --pick PICK  Only particles for which PICK is true (see -p help). The
                   particles are picked before -E is applied.
  -E, --edit EDIT  Change the particles with the statements in EDIT (see -E
                   help).

Showing particles:
  -j, --justhead   Show just the header.
  -n, --nohead     Show just the particles.
  -bKEY            Write the blob stored under KEY to standard output.

Summary (-S, --stats):
  -o, --output FILE
                   Save the overview plot in FILE instead (see below).
  -B, --backend NAME
                   Plotting backend for -o (see below).

Viewer (-w, --view):
  Shows an overview and plots of the particles (histograms as for -H, which
  can be changed, reordered and removed in the viewer, and further ones added,
  also with -H, given more than once), in a window with matplotlib, or else in
  the terminal. -l, -s, -p and -E can be changed in the viewer, and the
  particles can be written to a new file (press h for help).
  -wVIEW, --view=VIEW
                   The view shown first: overview, or a plot, e.g. -wekin.
  -wFILE.json, --view=FILE.json, --view="{...}"
                   The state of the viewer, saved in the viewer (press v), or
                   as printed when the viewer is closed.
  -t, --term       Show the viewer in the terminal.
  -B, --backend NAME
                   Plotting backend of the viewer: matplotlib, unicode or ascii.
  --color=WHEN     Colours in the terminal: auto, always or never (as for -H).

Histogram (-H, --hist HIST):
  HIST is an expression with options, e.g. "ekin/MeV;logx=1;split=pdgcode" (see
  -H help). With more files, there is a curve for each file.
  -t, --term       Show the plot in the terminal.
  -o, --output FILE
                   Save the plot in FILE, in the format given by the extension:
                   .png, .pdf, .svg or .txt.
  -B, --backend NAME
                   Plotting backend: matplotlib, unicode or ascii. By
                   default, plots are shown in a window with matplotlib, or
                   else in the terminal, and are saved with the backend for
                   the format.
  --color=WHEN     Colours of plots in the terminal: auto (the default: in
                   terminals, unless the NO_COLOR environment variable is set,
                   or always if FORCE_COLOR is set), always or never.

Extract (-e, --extract FILE OUT.mcpl.gz):
  --no-comment     Do not add comments to the header of OUT about how the
                   particles were extracted.
  --keep-statsum   Keep stat:sum entries when -E changes weights (if the edit
                   is known to be compatible with them). Otherwise they are
                   marked as not available (-1), as they are with -l or -s.

Merge (-m, --merge OUT.mcpl.gz FILE1 FILE2 ...):
  --inplace        Append the particles of FILE2 ... to FILE1 instead
                   (PROGNAME -m --inplace FILE1 FILE2 ...).
  The files must be compatible. --forcemerge also merges incompatible files,
  at the price of discarding comments and blobs, userflags (unless
  --keepuserflags is given), and userdata (unless all files have the same
  userdata layout).

Other options:
  -d, --dry-run    Do everything except writing files (ignored by commands
                   which do not write files).
  --traceback      Show the Python traceback of errors (for debugging).
  -v, --version    Show the version of MCPL.
  -h, --help       Show the short usage information.
  --full-help      Show this usage information.
  -p help, -E help, -H help
                   How to write PICK, EDIT and HIST.

Output files are gzipped if their names end with .mcpl.gz.
"""

def _mcpltool_usage(progname,errmsg=None,full=False):
    if errmsg:
        print(f"ERROR: {errmsg}\n")
        print("Run with -h or --help for usage information")
        sys.exit(1)
    msg = _full_help if full else _short_help
    print(msg.strip().replace('PROGNAME',progname)
          .replace('PROGPADS',' '*len(progname)))
    sys.exit(0)

def _topic_help(topic):
    from ._exprhelp import _help_text
    print(_help_text(topic))
    sys.exit(0)

def app_mcpltool(argv=None):
    """Implements the mcpltool command. If no argv list is
    passed in, sys.argv will be used. In case of errors, MCPLError exceptions
    are raised. Messages are always printed, even if use_logging() was
    called."""
    with _ForcePrinting():
        _app_mcpltool(argv)

#Options which take a value (given in the next argument, or attached as in
#-pVALUE or --pick=VALUE), by short and long names:
_value_opts = { '-p' : '--pick', '-E' : '--edit', '-H' : '--hist',
                '-o' : '--output', '-B' : '--backend' }
#(and those without short names):
_long_value_opts = ( '--color', )
#Flags, by long name (with short name, if any):
_flag_opts = { '--stats' : '-S', '--extract' : '-e', '--merge' : '-m',
               '--repair' : '-r', '--dry-run' : '-d', '--justhead' : '-j',
               '--nohead' : '-n', '--version' : '-v', '--term' : '-t',
               '--help' : '-h', '--forcemerge' : None, '--inplace' : None,
               '--keepuserflags' : None, '--text' : None,
               '--no-comment' : None, '--preventcomment' : None,
               '--keep-statsum' : None, '--full-help' : None,
               '--traceback' : None }
#Options of earlier versions, which are removed:
_removed_opts = {
    '--pdf' : 'a similar option now is: -S -o FILE.pdf',
    '--gui' : 'use -w instead',
}

def _app_mcpltool(argv):
    if argv is None:
        argv = sys.argv

    progname,args = os.path.basename(argv[0]),argv[1:]
    if progname == '__main__.py':
        progname = 'python -m mcpl'

    #NB: We do not use standard python parsing modules, since we want to be
    #as strictly compatible with mcpltool-c as possible.

    if not args:
        print('ERROR: No input file specified\n\nRun with -h or --help for usage information')
        sys.exit(1)
    def bad(errmsg):
        _mcpltool_usage(progname,errmsg)
    args = list(args)
    #(--create-examples can only be combined with --dry-run):
    opt_examples = None
    for a in args:
        if a == '--create-examples' or a.startswith('--create-examples='):
            if opt_examples is not None:
                bad("--create-examples specified more than once")
            opt_examples = a.partition('=')[2]
    if opt_examples is not None:
        if any( not ( a.startswith('--create-examples') or a in
                      ('-d','--dry-run','--traceback') ) for a in args ):
            bad("--create-examples can only be combined with --dry-run.")
        n = None
        if opt_examples:
            if not opt_examples.isdigit() or not int(opt_examples) > 0:
                bad("--create-examples=N requires a positive integer N")
            n = int(opt_examples)
        from ._examples import create_examples
        dry_run = '-d' in args or '--dry-run' in args
        try:
            create_examples( n, dry_run = dry_run )
        except MCPLError as e:
            bad(str(e))
        _mcpltool_dryrun_note(dry_run)
        return

    #Parse the arguments into flags (set of long names), values (dict by long
    #name), -l, -s and -b, and the list of files:
    flags, values, filelist = set(), {}, []
    opt_limit = opt_skip = opt_blobkey = None
    opt_view = None#(the view shown first with -w, '' for the default)
    hists = []#(all -H strings, since the viewer can have several)
    longtoshort = { v : k for k,v in _value_opts.items() }
    def set_value(name, value):
        if name == '--hist':
            hists.append(value)
            values.setdefault(name,value)
            return
        if name in values:
            bad(f"{longtoshort.get(name,name)} specified more than once")
        values[name] = value
    short_flags = { v : k for k,v in _flag_opts.items() if v }
    short_values = _value_opts
    while args:
        a = args.pop(0)
        if a.startswith('--'):
            name, eq, value = a.partition('=')
            if name in _removed_opts:
                bad(f"{name} is no longer supported as an option"
                    f" ({_removed_opts[name]})")
            if name == '--view':
                #(with an optional value, which must be attached):
                if opt_view is not None:
                    bad("-w specified more than once")
                opt_view = value if eq else ''
            elif name in _value_opts.values() or name in _long_value_opts:
                if not eq:
                    if not args:
                        bad(f"Missing argument for {name}")
                    value = args.pop(0)
                set_value(name,value)
            elif name in _flag_opts and not eq:
                flags.add(name)
            else:
                bad(f"Unrecognised option : {a}")
        elif a.startswith('-') and len(a) > 1:
            a = a[1:]
            while a:
                f, a = a[0], a[1:]
                if f'-{f}' in short_values:
                    name = short_values[f'-{f}']
                    if not a:
                        if not args:
                            bad(f"Missing argument for -{f}")
                        a = args.pop(0)
                    set_value(name,a)
                    a = ''
                elif f'-{f}' in short_flags:
                    flags.add(short_flags[f'-{f}'])
                elif f == 'w':
                    if opt_view is not None:
                        bad("-w specified more than once")
                    opt_view, a = a, ''
                elif f == 'b':
                    if opt_blobkey is not None:
                        bad("-b specified more than once")
                    if not a:
                        bad("Missing argument for -b")
                    opt_blobkey,a = a,''
                elif f in 'ls':
                    if not a:
                        bad("Bad option: missing number")
                    if not a.isdigit():
                        bad("Bad option: expected number")
                    if f == 'l':
                        if opt_limit is not None:
                            bad("-l specified more than once")
                        opt_limit = int(a)
                    else:
                        if opt_skip is not None:
                            bad("-s specified more than once")
                        opt_skip = int(a)
                    a = ''
                else:
                    bad(f"Unrecognised option : -{f}")
        else:
            filelist.append(a)

    if '--help' in flags:
        _mcpltool_usage(progname)
    if '--full-help' in flags:
        _mcpltool_usage(progname,full=True)
    for name, topic in (('--pick','pick'),('--edit','edit'),('--hist','hist')):
        if values.get(name,'').strip() == 'help':
            _topic_help(topic)

    #The mode:
    #(with -w, -H adds plots to the viewer):
    modes = [ m for m in ('--stats','--hist','--extract','--merge',
                          '--forcemerge','--repair','--text','--version')
              if ( m in flags or m in values )
              and not ( m == '--hist' and opt_view is not None ) ]
    if opt_view is not None:
        modes.insert(0,'--view')
    modenames = { 'dump' : 'when showing particles', '--stats' : '-S',
                  '--hist' : '-H', '--extract' : '-e', '--merge' : '-m',
                  '--forcemerge' : '--forcemerge', '--repair' : '-r',
                  '--text' : '--text', '--version' : '-v', '--view' : '-w' }
    if len(modes) > 1:
        bad(f"{modenames[modes[0]]} and {modenames[modes[1]]} can not be used"
            " together.")
    mode = modes[0] if modes else 'dump'
    def allowed(optname, okmodes, given, hint = '', msg = None):
        if given and mode not in okmodes:
            others = [ modenames[m] for m in okmodes if m != 'dump' ]
            w = ''
            if others:
                w = 'with ' + ( f"{', '.join(others[:-1])} or {others[-1]}"
                                if len(others) > 1 else others[0] )
            if 'dump' in okmodes:
                w = modenames['dump'] + ( f', or {w}' if w else '' )
            bad(msg or f"{optname} can only be used {w}{hint}.")
    datamodes = ('dump','--stats','--view','--hist','--extract')
    if len(hists) > 1 and mode != '--view':
        bad("-H specified more than once (several plots are only possible with -w)")
    allowed('-l',datamodes,opt_limit is not None)
    allowed('-s',datamodes,opt_skip is not None)
    allowed('-p',datamodes,'--pick' in values)
    allowed('-E',datamodes,'--edit' in values)
    allowed('-j',('dump',),'--justhead' in flags)
    allowed('-n',('dump',),'--nohead' in flags)
    allowed('-b',('dump',),opt_blobkey is not None)
    #(-t was the short form of --text in earlier versions, as in -t FILE OUT):
    allowed('-t',('--hist','--view'),'--term' in flags,
            msg = "-t can not be used without -H or -w" + ( " (did you mean --text?)."
                                                            if mode == 'dump' else "." ))
    allowed('-o',('--stats','--hist'),'--output' in values)
    allowed('-B',('--stats','--hist','--view'),'--backend' in values)
    allowed('--color',('--hist','--view'),'--color' in values)
    if values.get('--color',"auto") not in ('auto','always','never'):
        bad("--color must be auto, always or never.")
    if '--color' in values and '--output' in values:
        bad("--color can not be used with -o (plots are saved without colours).")
    allowed('--no-comment',('--extract',),bool(flags & {'--no-comment','--preventcomment'}))
    allowed('--keep-statsum',('--extract',),'--keep-statsum' in flags)
    allowed('--inplace',('--merge',),'--inplace' in flags)
    allowed('--keepuserflags',('--forcemerge',),'--keepuserflags' in flags)
    if mode == '--stats' and '--backend' in values and '--output' not in values:
        bad("-B can only be used with -S together with -o.")
    if '--term' in flags and '--output' in values:
        bad("-t and -o can not be used together.")
    opt_dryrun = '--dry-run' in flags
    if opt_dryrun and '--output' in values:
        bad("-d can not be used with -o (which saves plots in files).")

    #-p and -E, which are checked here to give errors before reading files:
    pick = edit = None
    if '--pick' in values:
        v = values['--pick'].strip()
        if v in _particle_names or re.fullmatch(r'[-+]?[0-9]+',v):
            bad(f'-p takes an expression (PICK): to pick particles of a type,'
                f' use -p "pdgcode == {v}"')
        from ._expressions import ParticleFilter
        try:
            pick = ParticleFilter(values['--pick'])
        except MCPLError as e:
            bad(str(e))
    if '--edit' in values:
        from ._expressions import ParticleEdit
        try:
            edit = ParticleEdit(values['--edit'])
        except MCPLError as e:
            bad(str(e))

    if mode == '--version':
        if filelist:
            bad("Unrecognised arguments for --version.")
        print(f"MCPL version {_determine_version()}")
        sys.exit(0)

    if mode in ('--merge','--forcemerge'):
        _mcpltool_merge(filelist,mode == '--forcemerge','--inplace' in flags,
                        '--keepuserflags' in flags,opt_dryrun,bad)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode == '--extract':
        _mcpltool_extract(filelist,opt_limit,opt_skip,pick,edit,
                          bool(flags & {'--no-comment','--preventcomment'}),
                          '--keep-statsum' in flags,opt_dryrun,bad)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode == '--view':
        _mcpltool_view(progname,filelist,opt_view,opt_skip,opt_limit,values,
                       hists,'--term' in flags,opt_dryrun,bad)
        sys.exit(0)

    if mode == '--hist':
        from ._clistats import mcpltool_hist
        mcpltool_hist(filelist,values['--hist'],opt_skip,opt_limit,pick,edit,
                      values.get('--output'),values.get('--backend'),
                      '--term' in flags,bad,color=values.get('--color'))
        sys.exit(0)

    if mode == '--text':
        if len(filelist)>2:
            bad("Too many arguments.")
        if len(filelist)!=2:
            bad("Must specify both input and output files with --text.")
        if (os.path.exists(filelist[1])):
            bad("Requested output file already exists.")
        if opt_dryrun:
            #(still read and convert everything, for the same errors):
            import io
            convert2ascii(filelist[0],io.StringIO())
            _mcpltool_dryrun_note(opt_dryrun)
            sys.exit(0)
        try:
            fout = open(filelist[1],'w')  # noqa: SIM115
        except OSError:
            fout = None
        if not fout:
            raise MCPLError('Could not open output file.')
        try:
            convert2ascii(filelist[0],fout)
        finally:
            fout.close()
        sys.exit(0)

    #Dump, stats or repair:
    if len(filelist)>1:
        bad("Too many arguments.")
    if not filelist:
        bad("No input file specified")

    if mode == '--repair':
        repair(filelist[0], dry_run = opt_dryrun)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode == '--stats':
        from ._clistats import mcpltool_stats
        mcpltool_stats(filelist[0],opt_skip,opt_limit,pick,edit,
                       values.get('--output'),values.get('--backend'),bad)
        sys.exit(0)

    #Dump
    opt_justhead, opt_nohead = '--justhead' in flags, '--nohead' in flags
    if opt_blobkey:
        if ( opt_justhead or opt_nohead or opt_limit is not None
             or opt_skip is not None or pick is not None or edit is not None ):
            bad("Do not specify other dump options with -b.")
        with MCPLFile(filelist[0]) as f:
            thedata = f.blobs.get(opt_blobkey,None)
            if thedata is None and 'blobs_raw' in f._hdr:
                #Under LANG=C and python3, utf-8 keys might be in trouble:
                thedata = f._hdr['blobs_raw'].get(os.fsencode(opt_blobkey),None)
            if thedata is None:
                sys.exit(1)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
            _output_bytearray_raw(thedata)
            sys.exit(0)
    if (opt_limit is not None or opt_skip is not None) and opt_justhead:
        bad("Do not specify -l or -s with --justhead")
    if (pick is not None or edit is not None) and opt_justhead:
        bad("Do not specify -p or -E with --justhead")
    if opt_justhead and opt_nohead:
        bad("Do not supply both --justhead and --nohead.")
    if pick is None and edit is None:
        dump_file(filelist[0],header=not opt_nohead,particles=not opt_justhead,
                  limit=10 if opt_limit is None else opt_limit,
                  skip=opt_skip or 0)
        sys.exit(0)
    #With -p or -E, -l and -s pick the range of particles in the file:
    from ._reader import _FileView
    f = MCPLFile(filelist[0])
    print(f"Opened MCPL file {os.path.basename(filelist[0])}:")
    if not opt_nohead:
        f.dump_hdr()
    if not opt_justhead:
        for what, e in (('picked',pick),('edited',edit)):
            if e is not None:
                print(f"Showing particles {what} with: {e.expression}")
        print()
        view = _FileView(f,opt_skip,opt_limit,pick,edit)
        f.dump_particles(limit=10 if opt_limit is None else 0,_view=view)
    sys.exit(0)

def _mcpltool_dryrun_note(dry_run):
    if dry_run:
        _info('dry run, nothing was written')

def _mcpltool_merge(filelist, opt_forcemerge, opt_inplace, opt_keepuserflags,
                      dry_run, bad):
    if len(filelist) < 2:
        bad("Too few arguments for --forcemerge." if opt_forcemerge
            else "Too few arguments for --merge.")
    ifirst = 0 if opt_inplace else 1
    if not opt_forcemerge:
        from ._fileops import _merge_incompat_reason, _open_raw
        for f in filelist[ifirst+1:]:
            with _open_raw(filelist[ifirst]) as f1, _open_raw(f) as f2:
                reason = _merge_incompat_reason(f1, f2)
            if reason is not None:
                bad("Requested files are incompatible for merge as they have"
                    f" different header info ({reason}).")
    if opt_inplace:
        for f in filelist[ifirst+1:]:
            merge_inplace(filelist[ifirst],f,dry_run=dry_run)
        return
    err, outfn, attempt_gzip = _tool_outfn(filelist[0])
    if err:
        bad(err)
    if opt_forcemerge:
        out = forcemerge_files(outfn,filelist[1:],opt_keepuserflags,dry_run=dry_run)
    else:
        out = merge_files(outfn,filelist[1:],dry_run=dry_run)
    if out is not None:
        _mcpltool_close(out,attempt_gzip)

def _mcpltool_view(progname, filelist, view, skip, limit, values, hists,
                   terminal, dry_run, bad):
    from ._plotbackend import _create, _viewer_backend
    from ._viewer import Viewer
    from ._viewer_ui import closing_text
    if not filelist:
        bad("No input file specified")
    if len(filelist) > 1:
        bad("The viewer shows one file (-w can only be used with one file).")
    try:
        v = Viewer(filelist[0],skip=skip or 0,limit=limit,
                   pick=values.get('--pick'),edit=values.get('--edit'),
                   plots=hists,view=view or None,dry_run=dry_run,
                   progname=progname)
        from ._clistats import _color_options
        cls = _viewer_backend(values.get('--backend'),terminal)
        bk = _create(cls,**_color_options(cls,values.get('--backend'),
                                          values.get('--color')))
        bk.run_viewer(v)
    except MCPLError as e:
        bad(str(e))
    print(closing_text(v))

def main():
    """This function simply calls app_mcpltool(), but any raised MCPLError
    exception will be caught and transformed into a corresponding error message
    followed by a call to sys.exit(1). This is what the mcpltool command and
    "python -m mcpl" run. With the --traceback option, MCPLError exceptions
    are not caught, so their Python traceback is shown."""
    if '--traceback' in sys.argv[1:]:
        app_mcpltool()
        return
    try:
        app_mcpltool()
    except MCPLError as e:
        print(f'MCPL ERROR: {e!s}')
        sys.exit(1)

def app_pymcpltool(argv=None):
    """The old name of app_mcpltool (still available for backwards
    compatibility)."""
    print('MCPL WARNING: app_pymcpltool has been renamed to app_mcpltool,'
          ' and will be removed in a future release.')
    app_mcpltool(argv)

def _main_pymcpltool():
    """The pymcpltool command, which is the old name of the mcpltool
    command."""
    print('MCPL WARNING: The pymcpltool command has been renamed to mcpltool,'
          ' and will be removed in a future release.')
    main()
