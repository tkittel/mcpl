
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
from ._messages import _ForcePrinting, _info
from ._reader import MCPLFile, dump_file

_short_help = """
Tool for inspecting or modifying Monte Carlo Particle List (.mcpl) files.

Usage:
  PROGNAME [options] FILE                  Show the header and first particles
  PROGNAME -S [options] FILE               Summary of the particles
  PROGNAME -w [options] FILE               View the particles in a window
  PROGNAME -t [options] FILE               View the particles in the terminal
  PROGNAME -w HIST [options] FILE [...]    Histogram in a window
  PROGNAME -t HIST [options] FILE [...]    Histogram in the terminal
  PROGNAME -e [options] FILE OUT.mcpl.gz   Extract particles into a new file
  PROGNAME -m OUT.mcpl.gz FILE1 FILE2 ...  Merge compatible files
  PROGNAME -r FILE                         Repair a file not properly closed

Common options:
  -lN, -sN       Use only N particles, or skip the first N particles.
  -p PICK        Only particles for which PICK is true, e.g.
                 -p "pdgcode == neutron and ekin < 25meV".
  -E EDIT        Change particles, e.g. -E "z += 1cm;weight *= 0.5".
  -o FILE        Save the histogram in FILE (.png, .pdf, or .svg with -w, .txt
                 with -t).
  -d             Dry run: do everything except writing files.

Examples:
  PROGNAME -w file.mcpl.gz
  PROGNAME -w "ekin/MeV;logx;display_only=neutron" file.mcpl.gz
  PROGNAME -e -p "pdgcode == neutron" file.mcpl.gz neutrons.mcpl.gz
  PROGNAME -S file.mcpl.gz

More help:
  --full-help              All options.
  -p help, -E help, --hist-help
                           How to write PICK, EDIT, and HIST.
"""

_full_help = """
Tool for inspecting or modifying Monte Carlo Particle List (.mcpl) files.

Usage:
  PROGNAME [options] FILE                  Show the header and first particles
  PROGNAME -S [options] FILE               Summary of the particles
  PROGNAME -w [options] FILE               View the particles in a window
  PROGNAME -t [options] FILE               View the particles in the terminal
  PROGNAME -w HIST [options] FILE [...]    Histogram in a window
  PROGNAME -t HIST [options] FILE [...]    Histogram in the terminal
  PROGNAME -e [options] FILE OUT.mcpl.gz   Extract particles into a new file
  PROGNAME -m OUT.mcpl.gz FILE1 FILE2 ...  Merge compatible files
  PROGNAME --forcemerge OUT.mcpl.gz FILE1 FILE2 ...
  PROGPADS                                 Merge also incompatible files
  PROGNAME -r FILE                         Repair a file not properly closed
  PROGNAME --text FILE OUT.txt             Write the particles as text
  PROGNAME --create-examples[=N]           Create example files
  PROGNAME -v | -h | --full-help

Particles (when showing particles, and with -S, -w, -t, and -e):
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

Viewer (-w, --window or -t, --terminal, without HIST):
  Shows an overview and plots of the particles of a file, in a window (with
  Tk, the plots drawn with matplotlib) with -w, or in the terminal (with
  curses, the plots drawn as text) with -t. -l, -s, -p, and -E can be changed
  in the viewer, plots can be added, changed, and removed, and the particles
  can be written to a new file (press h for help).
  -w=STATE, -t=STATE
                   Start in a state of the viewer: a .json file, as saved in
                   the viewer (press v), or its text, as printed when the
                   viewer is closed.

Histogram (-w, --window HIST or -t, --terminal HIST):
  HIST is an expression with options, e.g.
  "ekin/MeV;logx;display_only=neutron" (see --hist-help), given as -w HIST,
  -w=HIST, --window HIST, or --window=HIST (and likewise with -t). -w shows the
  histogram in a window (with matplotlib), and -t in the terminal (with
  Unicode characters, or else ASCII). With more files, there is a curve for
  each file.
  -o, --output FILE
                   Save the histogram in FILE instead: .png, .pdf, or .svg with
                   -w, or .txt with -t.
  --color=WHEN     Colours in the terminal (with -t): auto (the default: in
                   terminals, unless the NO_COLOR environment variable is set,
                   or always if FORCE_COLOR is set), always, or never.

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
  --allow-overwrite
                   Allow the output files of -m, --forcemerge, -e, --text, -o,
                   and --create-examples to overwrite existing files.
  --traceback      Show the Python traceback of errors (for debugging).
  -v, --version    Show the version of MCPL.
  -h, --help       Show the short usage information.
  --full-help      Show this usage information.
  -p help, -E help, --hist-help
                   How to write PICK, EDIT, and HIST.

Long options can be abbreviated, as long as they are unique (e.g. --ext for
--extract).

Output files are gzipped if their names end with .mcpl.gz.
"""

#Where errors in the values of options are explained (see _mcpltool_usage):
_option_help = { '--pick' : 'Run with "-p help" for how to pick particles with expressions',
                 '--edit' : 'Run with "-E help" for how to edit particles with expressions',
                 '--hist' : 'Run with "--hist-help" for how to write histograms' }

def _mcpltool_usage(progname,errmsg=None,full=False,option=None):
    """Print the usage information, or the error (in the value of the option,
    if given, see _option_help) and exit"""
    if errmsg:
        print(f"ERROR: {errmsg}\n")
        print(_option_help.get(option,"Run with -h or --help for usage information"))
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
    """Implements the mcpltool command, with the command line argv starting
    with the program name, like sys.argv (which is used if argv is None). Like
    the command, it ends with SystemExit: with code 0 when done, and 1 after
    printing the problem with the command line (e.g. an unknown option).
    Problems with files (e.g. missing or invalid files) raise MCPLError
    exceptions. Messages are always printed, even if use_logging() was
    called."""
    with _ForcePrinting():
        _app_mcpltool(argv)

#Options which take a value (given in the next argument, or attached as in
#-pVALUE or --pick=VALUE), by short and long names:
_value_opts = { '-p' : '--pick', '-E' : '--edit', '-o' : '--output' }
#(and those without short names):
_long_value_opts = ( '--color', )
#Options with an optional value (a histogram): given as -w=VALUE or
#--window=VALUE, or as the next argument when it is followed by the files (see
#_optional_value):
_optional_value_opts = { '-w' : '--window', '-t' : '--terminal' }
#Flags, by long name (with short name, if any):
_flag_opts = { '--stats' : '-S', '--extract' : '-e', '--merge' : '-m',
               '--repair' : '-r', '--dry-run' : '-d', '--justhead' : '-j',
               '--nohead' : '-n', '--version' : '-v',
               '--help' : '-h', '--forcemerge' : None, '--inplace' : None,
               '--keepuserflags' : None, '--text' : None,
               '--no-comment' : None, '--preventcomment' : None,
               '--keep-statsum' : None, '--full-help' : None,
               '--allow-overwrite' : None,
               '--hist-help' : None, '--traceback' : None }
#Options of earlier versions, which are removed:
_removed_opts = {
    '--pdf' : 'a similar option now is: -w HIST -o FILE.pdf',
    '--gui' : 'use -w instead',
}

def _long_option( arg, bad ):
    """The long option given by arg (as --name or --name=value), also when
    abbreviated (unique), as (name, '=' or '', value)"""
    name, eq, value = arg.partition('=')
    names = ( *_value_opts.values(), *_long_value_opts, *_optional_value_opts.values(),
              *_flag_opts, *_removed_opts, '--create-examples' )
    if name not in names:
        matches = sorted( n for n in names if n.startswith(name) and n not in _removed_opts )
        if len(matches) == 1:
            name = matches[0]
        elif matches:
            bad(f"Ambiguous option {name} (could be {', '.join(matches)})")
    return name, eq, value

def _optional_value( name, value, files ):
    """The value of -w or -t (by long name): as given with '=', or else the
    argument right after the option, if more arguments which are not options
    follow (the files, as a histogram is given before them), or None. files
    is the list of the arguments which are not options, as (the long name of
    the option right before it, or None, argument), from which the value is
    removed."""
    if value is not None:
        return value
    i = next( ( i for i, ( after, _ ) in enumerate(files) if after == name ), None )
    if i is None or len(files) < 2:
        return None
    return files.pop(i)[1]

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
    def bad(errmsg,option=None):
        _mcpltool_usage(progname,errmsg,option=option)
    args = list(args)
    #(--create-examples can only be combined with --dry-run):
    opt_examples = None
    longnames = [ _long_option(a,bad)[0] if a.startswith('--') else a for a in args ]
    for a, name in zip(args,longnames):
        if name == '--create-examples':
            if opt_examples is not None:
                bad("--create-examples specified more than once")
            opt_examples = a.partition('=')[2]
    if opt_examples is not None:
        if any( name not in ('--create-examples','-d','--dry-run','--traceback',
                             '--allow-overwrite')
                for name in longnames ):
            bad("--create-examples can only be combined with --dry-run and"
                " --allow-overwrite.")
        n = None
        if opt_examples:
            if not opt_examples.isdigit() or not int(opt_examples) > 0:
                bad("--create-examples=N requires a positive integer N")
            n = int(opt_examples)
        from ._examples import create_examples
        dry_run = '-d' in longnames or '--dry-run' in longnames
        try:
            create_examples( n, dry_run = dry_run,
                             allow_overwrite = '--allow-overwrite' in longnames )
        except MCPLError as e:
            bad(str(e))
        _mcpltool_dryrun_note(dry_run)
        return

    #Parse the arguments into flags (set of long names), values (dict by long
    #name), -l, -s, -b, and the list of files:
    flags, values, files = set(), {}, []
    opt_limit = opt_skip = opt_blobkey = None
    optional = {}#(-w and -t, by long name, with their values if given with =)
    after = None#(the option with an optional value right before, see _optional_value)
    longtoshort = { v : k for k,v in ( *_value_opts.items(), *_optional_value_opts.items() ) }
    def set_value(name, value):
        if name in values:
            bad(f"{longtoshort.get(name,name)} specified more than once")
        values[name] = value
    def set_optional(name, value):
        if name in optional:
            bad(f"{longtoshort[name]} specified more than once")
        optional[name] = value
        return None if value is not None else name
    short_flags = { v : k for k,v in _flag_opts.items() if v }
    short_values = _value_opts
    while args:
        a = args.pop(0)
        option_before, after = after, None
        if a.startswith('--'):
            name, eq, value = _long_option(a,bad)
            if name in _removed_opts:
                bad(f"{name} is no longer supported as an option"
                    f" ({_removed_opts[name]})")
            if name in _optional_value_opts.values():
                after = set_optional(name,value if eq else None)
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
                if f'-{f}' in _optional_value_opts:
                    if a and not a.startswith('='):
                        bad(f"-{f} takes a value as -{f}=VALUE or -{f} VALUE (not -{f}{a})")
                    after = set_optional(_optional_value_opts[f'-{f}'],a[1:] if a else None)
                    a = ''
                elif f'-{f}' in short_values:
                    name = short_values[f'-{f}']
                    if not a:
                        if not args:
                            bad(f"Missing argument for -{f}")
                        a = args.pop(0)
                    set_value(name,a)
                    a = ''
                elif f'-{f}' in short_flags:
                    flags.add(short_flags[f'-{f}'])
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
            files.append( ( option_before, a ) )
    #(-w and -t, whose values can be given as the next argument):
    for name, value in list(optional.items()):
        optional[name] = _optional_value(name,value,files)
    filelist = [ a for _, a in files ]

    if '--help' in flags:
        _mcpltool_usage(progname)
    if '--full-help' in flags:
        _mcpltool_usage(progname,full=True)
    if '--hist-help' in flags:
        _topic_help('hist')
    for name, topic in (('--pick','pick'),('--edit','edit')):
        if values.get(name,'').strip().lower() == 'help':
            _topic_help(topic)

    #The mode:
    modes = [ m for m in ('--stats','--window','--terminal','--extract','--merge',
                          '--forcemerge','--repair','--text','--version')
              if m in flags or m in values or m in optional ]
    modenames = { 'dump' : 'when showing particles', '--stats' : '-S',
                  '--window' : '-w', '--terminal' : '-t', '--extract' : '-e',
                  '--merge' : '-m', '--forcemerge' : '--forcemerge', '--repair' : '-r',
                  '--text' : '--text', '--version' : '-v' }
    if len(modes) > 1:
        bad(f"{modenames[modes[0]]} and {modenames[modes[1]]} can not be used"
            " together.")
    mode = modes[0] if modes else 'dump'
    def allowed(optname, okmodes, given, hint = '', msg = None):
        if given and mode not in okmodes:
            others = [ modenames[m] for m in okmodes if m != 'dump' ]
            w = ''
            if others:
                #(with the Oxford comma for three or more):
                sep = ',' if len(others) > 2 else ''
                w = 'with ' + ( f"{', '.join(others[:-1])}{sep} or {others[-1]}"
                                if len(others) > 1 else others[0] )
            if 'dump' in okmodes:
                w = modenames['dump'] + ( f', or {w}' if w else '' )
            bad(msg or f"{optname} can only be used {w}{hint}.")
    datamodes = ('dump','--stats','--window','--terminal','--extract')
    histmodes = ('--window','--terminal')
    allowed('-l',datamodes,opt_limit is not None)
    allowed('-s',datamodes,opt_skip is not None)
    allowed('-p',datamodes,'--pick' in values)
    allowed('-E',datamodes,'--edit' in values)
    allowed('-j',('dump',),'--justhead' in flags)
    allowed('-n',('dump',),'--nohead' in flags)
    allowed('-b',('dump',),opt_blobkey is not None)
    stats_hint = ' (-S only prints text, for plots use -w or -t)' if mode == '--stats' else ''
    allowed('-o',histmodes,'--output' in values,hint=stats_hint)
    allowed('--color',('--terminal',),'--color' in values)
    if values.get('--color',"auto") not in ('auto','always','never'):
        bad("--color must be auto, always, or never.")
    if '--color' in values and '--output' in values:
        bad("--color can not be used with -o (plots are saved without colours).")
    allowed('--no-comment',('--extract',),bool(flags & {'--no-comment','--preventcomment'}))
    allowed('--keep-statsum',('--extract',),'--keep-statsum' in flags)
    allowed('--inplace',('--merge',),'--inplace' in flags)
    allowed('--keepuserflags',('--forcemerge',),'--keepuserflags' in flags)
    opt_allow_overwrite = '--allow-overwrite' in flags
    if opt_allow_overwrite and ( '--inplace' in flags or mode not in
                                 ('--merge','--forcemerge','--extract','--text')
                                 and not ( mode in histmodes and '--output' in values ) ):
        bad("--allow-overwrite can only be used with --merge, --forcemerge,"
            " --extract, --text, or -o.")
    #(-w and -t show the viewer, unless given a histogram, and not a state of
    #the viewer):
    hist = state = None
    viewer = False
    if mode in histmodes:
        opt = modenames[mode]
        value = optional[mode]
        if value is not None and value.endswith(('.mcpl','.mcpl.gz')) and os.path.isfile(value):
            #(-t was the short form of --text in earlier versions, as in -t FILE OUT):
            bad(f'{opt} takes the histogram before the files, as in {opt} "ekin/MeV;logx" FILE'
                + ( ' (or did you mean --text?).' if opt == '-t' else '.' ))
        if value is None or value.lstrip().startswith('{') or value.endswith('.json'):
            viewer, state = True, value
            if '--output' in values:
                bad(f'-o can only be used with a histogram, as in {opt} "ekin/MeV;logx" FILE -o'
                    f' {"plot.pdf" if opt == "-w" else "plot.txt"}.')
            if ( len(filelist) == 1 and not os.path.exists(filelist[0])
                 and not filelist[0].endswith(('.mcpl','.gz')) ):
                bad(f'No such file: {filelist[0]} (a histogram is given before the files,'
                    f' as in {opt} "{filelist[0]}" FILE).')
        else:
            hist = value
        ext = os.path.splitext(values.get('--output',''))[1].lower()
        if mode == '--window' and ext == '.txt':
            bad('-w saves histograms as .png, .pdf, or .svg files (use -t HIST -o FILE.txt for text).')
        if mode == '--terminal' and ext not in ( '', '.txt' ):
            bad('-t saves histograms as .txt files (use -w HIST -o FILE for .png, .pdf, or .svg).')
    opt_dryrun = '--dry-run' in flags
    if opt_dryrun and '--output' in values:
        bad("-d can not be used with -o (which saves plots in files).")

    #-p and -E, which are checked here to give errors before reading files:
    pick = edit = None
    if '--pick' in values:
        v = values['--pick'].strip()
        from ._particles import _particle_names
        if v in _particle_names or re.fullmatch(r'[-+]?[0-9]+',v):
            bad(f'-p takes an expression (PICK): to pick particles of a type,'
                f' use -p "pdgcode == {v}"','--pick')
        from ._expressions import ParticleFilter
        try:
            pick = ParticleFilter(values['--pick'])
        except MCPLError as e:
            bad(str(e),'--pick')
    if '--edit' in values:
        from ._expressions import ParticleEdit
        try:
            edit = ParticleEdit(values['--edit'])
        except MCPLError as e:
            bad(str(e),'--edit')
    #(and the histogram, with the same checks as when it is made):
    if hist is not None:
        from ._histogram import _filler_for
        from ._histstring import _parse_hist
        try:
            _filler_for(_parse_hist(hist))
        except MCPLError as e:
            bad(str(e),'--hist')

    if mode == '--version':
        if filelist:
            bad("Unrecognised arguments for --version.")
        print(f"MCPL version {_determine_version()}")
        sys.exit(0)

    if mode in ('--merge','--forcemerge'):
        _mcpltool_merge(filelist,mode == '--forcemerge','--inplace' in flags,
                        '--keepuserflags' in flags,opt_dryrun,bad,
                        allow_overwrite = opt_allow_overwrite)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode == '--extract':
        from ._extract import _mcpltool_extract
        _mcpltool_extract(filelist,opt_limit,opt_skip,pick,edit,
                          bool(flags & {'--no-comment','--preventcomment'}),
                          '--keep-statsum' in flags,opt_dryrun,bad,
                          allow_overwrite = opt_allow_overwrite)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if viewer:
        _mcpltool_view(progname,filelist,state,opt_skip,opt_limit,values,
                       mode == '--terminal',opt_dryrun,bad)
        sys.exit(0)

    if mode in histmodes:
        from ._clistats import mcpltool_hist
        mcpltool_hist(filelist,hist,opt_skip,opt_limit,pick,edit,
                      values.get('--output'),mode == '--terminal',bad,
                      color=values.get('--color'),
                      allow_overwrite=opt_allow_overwrite)
        sys.exit(0)

    if mode == '--text':
        if len(filelist)>2:
            bad("Too many arguments.")
        if len(filelist)!=2:
            bad("Must specify both input and output files with --text.")
        #(the output file must not be the input file, or exist unless allowed):
        try:
            same = os.path.samefile(filelist[1],filelist[0])
        except OSError:
            same = False
        if same:
            bad(f'The output file "{filelist[1]}" is also one of the input files.')
        if not opt_allow_overwrite and os.path.lexists(filelist[1]):
            bad(f'The output file "{filelist[1]}" already exists.')
        from ._ascii import convert2ascii
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

    #Dump, stats, or repair:
    if len(filelist)>1:
        bad("Too many arguments.")
    if not filelist:
        bad("No input file specified")

    if mode == '--repair':
        from ._fileops import repair
        repair(filelist[0], dry_run = opt_dryrun)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode == '--stats':
        from ._clistats import mcpltool_stats
        mcpltool_stats(filelist[0],opt_skip,opt_limit,pick,edit,bad)
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
                      dry_run, bad, allow_overwrite = False):
    if len(filelist) < 2:
        bad("Too few arguments for --forcemerge." if opt_forcemerge
            else "Too few arguments for --merge.")
    ifirst = 0 if opt_inplace else 1
    from ._fileops import forcemerge_files, merge_files, merge_inplace
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
    from ._extract import _mcpltool_close, _tool_check_outfn
    outfn = filelist[0]
    err = _tool_check_outfn( outfn, filelist[1:], allow_overwrite )
    if err:
        bad(err)
    if opt_forcemerge:
        out = forcemerge_files(outfn,filelist[1:],keep_userflags=opt_keepuserflags,
                               allow_overwrite=allow_overwrite,dry_run=dry_run)
    else:
        out = merge_files(outfn,filelist[1:],allow_overwrite=allow_overwrite,
                          dry_run=dry_run)
    if out is not None:
        _mcpltool_close(out)

def _mcpltool_view(progname, filelist, state, skip, limit, values, terminal,
                   dry_run, bad):
    """The viewer of -w (in a window) or -t (in the terminal), starting in the
    state if given"""
    from ._viewer import Viewer, _run_viewer
    from ._viewer_ui import closing_text
    if not filelist:
        bad("No input file specified")
    if len(filelist) > 1:
        bad(f"The viewer shows one file ({'-t' if terminal else '-w'} without a histogram"
            " can only be used with one file).")
    try:
        v = Viewer(filelist[0],skip=skip or 0,limit=limit,
                   pick=values.get('--pick'),edit=values.get('--edit'),
                   state=state,dry_run=dry_run,progname=progname)
        _run_viewer(v,terminal,values.get('--color'),
                    hint='Use -t for the viewer in the terminal.')
    except MCPLError as e:
        bad(str(e))
    print(closing_text(v,'-t' if terminal else '-w'))

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
