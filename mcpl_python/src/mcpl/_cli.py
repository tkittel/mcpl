
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

from ._common import MCPLError, _determine_version, _output_bytearray_raw, _parse_count
from ._messages import _ForcePrinting, _info
from ._reader import MCPLFile

_short_help = """
Tool for inspecting or modifying Monte Carlo Particle List (.mcpl) files.

Usage:
  PROGNAME [options] FILE                  Show the header and first particles
  PROGNAME -S [options] FILE               Summary of the particles
  PROGNAME -H HIST [options] FILE [...]    Histogram in a window
  PROGNAME -t -H HIST [options] FILE [...] Histogram in the terminal
  PROGNAME -x [options] FILE OUT.mcpl.gz   Extract particles into a new file
  PROGNAME -m OUT.mcpl.gz FILE1 FILE2 ...  Merge compatible files
  PROGNAME -r FILE                         Repair a file not properly closed

Common options:
  -lN, -sN       Use only N particles, or skip the first N particles.
  -e EDIT        Pick and change particles, e.g.
                 -e "pdgcode == neutron; z += 1cm; ekin < 25meV".
  -o FILE        Save the histogram in FILE (.png, .pdf, or .svg, or .txt with
                 -t).
  -d             Dry run: do everything except writing files.

Examples:
  PROGNAME -H "ekin/MeV;logx;display_edit=pdgcode==neutron" file.mcpl.gz
  PROGNAME -x -e "pdgcode == neutron" file.mcpl.gz neutrons.mcpl.gz
  PROGNAME -S file.mcpl.gz

More help:
  --full-help              All options.
  -e help                  How to write EDIT.
  --hist-help              How to write HIST.
"""

_full_help = """
Tool for inspecting or modifying Monte Carlo Particle List (.mcpl) files.

Usage:
  PROGNAME [options] FILE                  Show the header and first particles
  PROGNAME -S [options] FILE               Summary of the particles
  PROGNAME -H HIST [options] FILE [...]    Histogram in a window
  PROGNAME -t -H HIST [options] FILE [...] Histogram in the terminal
  PROGNAME -x [options] FILE OUT.mcpl.gz   Extract particles into a new file
  PROGNAME -m OUT.mcpl.gz FILE1 FILE2 ...  Merge compatible files
  PROGNAME --forcemerge OUT.mcpl.gz FILE1 FILE2 ...
  PROGPADS                                 Merge also incompatible files
  PROGNAME -r FILE                         Repair a file not properly closed
  PROGNAME --text FILE OUT.txt             Write the particles as text
  PROGNAME --create-examples[=N]           Create example files
  PROGNAME -v | -h | --full-help

Particles (when showing particles, and with -S, -H, and -x):
  -sN, --skip N    Skip the first N particles in the file.
  -lN, --limit N   Use only N particles (all with -l0). Without -l, at most 10
                   particles are shown when showing particles.
  -e, --edit EDIT  Pick and change the particles with the statements in EDIT,
                   executed in order, e.g. -e "pdgcode == neutron; z += 1m;
                   through_sphere((0,0,2m),10cm)" (see -e help).
  -s and -l choose particles by their position in the file, before -e.

Showing particles:
  -j, --justhead   Show just the header.
  -n, --nohead     Show just the particles.
  -bKEY            Write the blob stored under KEY to standard output.

Histogram (-H, --hist HIST):
  HIST is an expression with options, e.g.
  "ekin/MeV;logx;display_edit=pdgcode==neutron" (see --hist-help). The
  histogram is shown in a window (with matplotlib), or with -t in the terminal
  (with Unicode characters, or else ASCII). With more files, 1D histograms
  have a curve for each file (2D histograms and 3D plots combine them).
  -o, --output FILE
                   Save the histogram in FILE instead: .png, .pdf, or .svg, or
                   .txt with -t.
  --color=WHEN     Colours in the terminal (with -t): auto (the default: in
                   terminals, unless the NO_COLOR environment variable is set,
                   or always if FORCE_COLOR is set), always, or never.

Extract (-x, --extract FILE OUT.mcpl.gz):
  --no-comment     Do not add comments to the header of OUT about how the
                   particles were extracted.
  --keep-statsum   Keep stat:sum entries when -e changes weights (if the edit
                   is known to be compatible with them). Otherwise they are
                   marked as not available (-1), as they are with -l or -s.
  --code=LANG      Instead of extracting, print a program in C (LANG c) or C++
                   (LANG cpp) which does the same for files like FILE (with its
                   userdata layout and stat:sum entries), taking the input and
                   output files as arguments (PROGNAME -x --code=LANG
                   [options] FILE).
  With -s or -l, the stat:sum values are scaled to the fraction of the file
  used.

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
                   Allow the output files of -m, --forcemerge, -x, --text, -o,
                   and --create-examples to overwrite existing files.
  --traceback      Show the Python traceback of errors (for debugging).
  -v, --version    Show the version of MCPL.
  -h, --help       Show the short usage information.
  --full-help      Show this usage information.
  -e help          How to write EDIT.
  --hist-help      How to write HIST.

Long options can be abbreviated, as long as they are unique (e.g. --ext for
--extract).

Output files are gzipped if their names end with .mcpl.gz.
"""

#Where errors in the values of options are explained (see _UsageError):
_option_help = { '--edit' : 'Run with "-e help" for how to write edit expressions',
                 '--hist' : 'Run with "--hist-help" for how to write histograms' }

class _UsageError(MCPLError):
    """A problem with the command line, with the option whose value has the
    problem (if any, see _option_help)"""
    def __init__( self, msg, option = None ):
        super().__init__(msg)
        self.option = option

def _progname( argv0 ):
    name = os.path.basename(argv0)
    return 'python -m mcpl' if name == '__main__.py' else name

def _print_help( progname, full = False ):
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
    the command, it ends with SystemExit: with code 0 when done, and 2 after
    printing the problem with the command line (e.g. an unknown option) to
    standard error. Problems with files (e.g. missing or invalid files) raise
    MCPLError exceptions. Messages are always printed, even if use_logging()
    was called."""
    argv = sys.argv if argv is None else argv
    progname = _progname(argv[0])
    with _ForcePrinting():
        try:
            _app_mcpltool(progname,list(argv[1:]))
        except _UsageError as e:
            sys.stdout.flush()
            print(f'usage: {progname} [options] FILE ...  (see {progname} -h)\n'
                  f'{progname}: error: {e}', file = sys.stderr)
            if e.option in _option_help:
                print(_option_help[e.option],file = sys.stderr)
            sys.exit(2)

def _bad( msg, option = None ):
    """A problem with the command line (see _UsageError)"""
    raise _UsageError(msg,option)

#Flags, by long name (with short name, if any):
_flag_opts = { '--stats' : '-S', '--extract' : '-x', '--merge' : '-m',
               '--repair' : '-r', '--dry-run' : '-d', '--justhead' : '-j',
               '--nohead' : '-n', '--version' : '-v',
               '--help' : '-h', '--forcemerge' : None, '--inplace' : None,
               '--keepuserflags' : None, '--text' : None,
               '--no-comment' : None, '--preventcomment' : None,
               '--keep-statsum' : None, '--full-help' : None,
               '--allow-overwrite' : None,
               '--hist-help' : None, '--traceback' : None,
               '--window' : '-w', '--terminal' : '-t' }
#Options which take a value, by long name (with short name, if any):
_value_opts = { '--edit' : '-e', '--hist' : '-H', '--output' : '-o',
                '--color' : None, '--code' : None }
#Options of earlier versions, which are removed:
_removed_opts = {
    '--pdf' : 'a similar option now is: -H HIST -o FILE.pdf',
    '--gui' : 'use -w instead',
}

#The options -e (--extract) and -pPDGCODE of earlier versions:
_old_extract = '-e takes an edit expression (to extract particles, use -x)'
def _old_pick( value ):
    example = f'pdgcode == {value}' if re.fullmatch(r'[-+]?[0-9]+',value) else 'pdgcode == neutron'
    return f'-p is not an option (use -e, e.g. -e "{example}")'

def _parser():
    """The parser of the options of mcpltool (argparse's own help is not
    used; see _short_help and _full_help)"""
    import argparse

    class Parser(argparse.ArgumentParser):
        def error( self, message ):
            #(as by newer Pythons also with older ones, which report a flag
            #followed by more characters, like -vy, as "argument -v/--version:
            #ignored explicit argument 'y'"):
            import re
            m = re.fullmatch(r"argument \S+: ignored explicit argument '(.*)'",message)
            if message == 'argument -e/--edit: expected one argument':
                _bad(_old_extract)
            _bad(f'unrecognized arguments: -{m.group(1)}' if m else message)

    class Once(argparse.Action):
        """Options which can only be given once"""
        def __call__( self, parser, namespace, values, option_string = None ):
            if getattr(namespace,self.dest) is not None:
                _bad(f"{self.option_strings[0]} specified more than once")
            setattr(namespace,self.dest,values)

    def count( text ):
        n = _parse_count(text)
        if n is None:
            raise argparse.ArgumentTypeError(f"expected a non-negative whole number, not '{text}'")
        return n

    p = Parser(add_help = False)
    for name, short in _flag_opts.items():
        p.add_argument(*( [short] if short else [] ),name,dest = name,action = 'store_true')
    for name, short in _value_opts.items():
        p.add_argument(*( [short] if short else [] ),name,dest = name,action = Once)
    p.add_argument('-l','--limit',dest = '-l',action = Once,type = count)
    p.add_argument('-s','--skip',dest = '-s',action = Once,type = count)
    #(the -p of earlier versions, see _old_pick):
    p.add_argument('-p',dest = '-p')
    p.add_argument('-b',dest = '-b',action = Once)
    p.add_argument('--create-examples',dest = '--create-examples',action = Once,
                   nargs = '?',const = '')
    p.add_argument('files',nargs = '*')
    return p

def _parse_args( args ):
    """The options (by name) and files of the arguments of mcpltool"""
    for a in args:
        name = a.partition('=')[0]
        if name in _removed_opts:
            _bad(f"{name} is not an option ({_removed_opts[name]})")
    opts = vars(_parser().parse_intermixed_args(args))
    return opts, opts.pop('files')

def _app_mcpltool(progname,args):
    if not args:
        _bad("no input file specified")
    bad = _bad
    opts, filelist = _parse_args(args)

    #(--create-examples can only be combined with --dry-run):
    opt_examples = opts.pop('--create-examples')
    if opt_examples is not None:
        others = [ n for n, v in opts.items() if v not in ( None, False )
                   and n not in ( '--dry-run', '--traceback', '--allow-overwrite' ) ]
        if others or filelist:
            bad("--create-examples can only be combined with --dry-run and"
                " --allow-overwrite")
        n = None
        if opt_examples:
            n = _parse_count(opt_examples)
            if not n:
                bad("--create-examples=N requires a positive integer N")
        from ._examples import create_examples
        dry_run = opts['--dry-run']
        create_examples( n, dry_run = dry_run, allow_overwrite = opts['--allow-overwrite'] )
        _mcpltool_dryrun_note(dry_run)
        return

    #The options as flags (set of long names), values (dict by long name), -l,
    #-s, and -b:
    if opts['-p'] is not None:
        bad(_old_pick(opts['-p']))
    flags = { n for n in _flag_opts if opts[n] }
    values = { n : opts[n] for n in _value_opts if opts[n] is not None }
    opt_limit, opt_skip, opt_blobkey = opts['-l'], opts['-s'], opts['-b']

    if '--help' in flags:
        _print_help(progname)
    if '--full-help' in flags:
        _print_help(progname,full=True)
    if '--hist-help' in flags:
        _topic_help('hist')
    if values.get('--edit','').strip().lower() == 'help':
        _topic_help('edit')

    #The mode:
    #(a histogram is shown in a window, unless -t is given):
    if '--hist' in values and '--terminal' not in flags:
        flags.add('--window')
    modes = [ m for m in ('--stats','--window','--terminal','--extract','--merge',
                          '--forcemerge','--repair','--text','--version')
              if m in flags ]
    modenames = { 'dump' : 'when showing particles', '--stats' : '-S',
                  '--window' : '-w', '--terminal' : '-t', '--extract' : '-x',
                  '--merge' : '-m', '--forcemerge' : '--forcemerge', '--repair' : '-r',
                  '--text' : '--text', '--version' : '-v' }
    if '--hist' in values and not opts['--window']:
        modenames['--window'] = '-H'#(the window of a histogram, without -w)
    if len(modes) > 1:
        bad(f"{modenames[modes[0]]} and {modenames[modes[1]]} can not be used"
            " together")
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
            bad(msg or f"{optname} can only be used {w}{hint}")
    datamodes = ('dump','--stats','--window','--terminal','--extract')
    histmodes = ('--window','--terminal')
    allowed('-l',datamodes,opt_limit is not None)
    allowed('-s',datamodes,opt_skip is not None)
    allowed('-e',datamodes,'--edit' in values)
    allowed('-j',('dump',),'--justhead' in flags)
    allowed('-n',('dump',),'--nohead' in flags)
    allowed('-b',('dump',),opt_blobkey is not None)
    stats_hint = ' (-S only prints text, for plots use -H)' if mode == '--stats' else ''
    allowed('-H',histmodes,'--hist' in values)
    if '--output' in values and '--hist' not in values:
        bad("-o can only be used with a histogram (-H HIST)" + stats_hint)
    allowed('--color',('--terminal',),'--color' in values)
    if values.get('--color',"auto") not in ('auto','always','never'):
        bad("--color must be auto, always, or never")
    if '--color' in values and '--output' in values:
        bad("--color can not be used with -o (plots are saved without colours)")
    allowed('--no-comment',('--extract',),bool(flags & {'--no-comment','--preventcomment'}))
    allowed('--keep-statsum',('--extract',),'--keep-statsum' in flags)
    allowed('--code',('--extract',),'--code' in values)
    if values.get('--code','c') not in ('c','cpp'):
        bad("--code must be c or cpp")
    if '--code' in values:
        others = [ o for o, given in ( ( '-d', '--dry-run' in flags ),
                                       ( '--allow-overwrite', '--allow-overwrite' in flags ) )
                   if given ]
        if others:
            bad(f"--code can not be used with {others[0]} (it writes no files)")
    allowed('--inplace',('--merge',),'--inplace' in flags)
    allowed('--keepuserflags',('--forcemerge',),'--keepuserflags' in flags)
    opt_allow_overwrite = '--allow-overwrite' in flags
    if opt_allow_overwrite and ( '--inplace' in flags or mode not in
                                 ('--merge','--forcemerge','--extract','--text')
                                 and not ( mode in histmodes and '--output' in values ) ):
        bad("--allow-overwrite can only be used with --merge, --forcemerge,"
            " --extract, --text, or -o")
    #(-w and -t only choose where a histogram of -H is shown):
    hist = values.get('--hist')
    if mode in histmodes and hist is None:
        bad(f"{modenames[mode]} is used with -H HIST (see --hist-help)")
    if hist is not None:
        ext = os.path.splitext(values.get('--output',''))[1].lower()
        if mode == '--window' and ext == '.txt':
            bad('histograms are saved as .txt files with -t (as in -t -H HIST -o FILE.txt)')
        if mode == '--terminal' and ext not in ( '', '.txt' ):
            bad('-t saves histograms as .txt files (without -t, as .png, .pdf, or .svg files)')
    opt_dryrun = '--dry-run' in flags
    if opt_dryrun and '--output' in values:
        bad("-d can not be used with -o (which saves plots in files)")

    #-e, which is checked here to give errors before reading files:
    edit = None
    if '--edit' in values:
        v = values['--edit'].strip()
        if v.endswith(('.mcpl','.gz')) or os.path.exists(v):
            bad(_old_extract)
        from ._expressions import ParticleEdit
        try:
            edit = ParticleEdit(values['--edit'])
        except MCPLError as e:
            bad(str(e),'--edit')
    #(and the histogram, with the same checks as when it is made):
    if hist is not None:
        from ._histfill import _filler_for
        from ._histstring import _parse_hist
        try:
            _filler_for(_parse_hist(hist))
        except MCPLError as e:
            bad(str(e),'--hist')

    if mode == '--version':
        if filelist:
            bad(f"unrecognized arguments: {' '.join(filelist)}")
        print(f"MCPL version {_determine_version()}")
        sys.exit(0)

    if mode in ('--merge','--forcemerge'):
        _mcpltool_merge(filelist,mode == '--forcemerge','--inplace' in flags,
                        '--keepuserflags' in flags,opt_dryrun,bad,
                        allow_overwrite = opt_allow_overwrite)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode == '--extract' and '--code' in values:
        from ._extract import _mcpltool_code
        _check_inputs(filelist[:1])
        _mcpltool_code(filelist,values['--code'],opt_limit,opt_skip,edit,
                       bool(flags & {'--no-comment','--preventcomment'}),
                       '--keep-statsum' in flags,bad)
        sys.exit(0)

    if mode == '--extract':
        from ._extract import _mcpltool_extract
        if len(filelist) > 2:
            _bad("too many arguments")
        if len(filelist) != 2:
            _bad("must specify both input and output files with -x")
        _check_inputs(filelist[:1])
        _mcpltool_extract(filelist,opt_limit,opt_skip,edit,
                          bool(flags & {'--no-comment','--preventcomment'}),
                          '--keep-statsum' in flags,opt_dryrun,bad,
                          allow_overwrite = opt_allow_overwrite)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode in histmodes:
        from ._clistats import mcpltool_hist
        if not filelist:
            _bad("no input file specified")
        if hist['print'] and ( '--output' in values or '--color' in values ):
            _bad("the histogram option print can not be used together with -o or --color")
        _check_inputs(filelist)
        mcpltool_hist(filelist,hist,opt_skip,opt_limit,edit,
                      values.get('--output'),mode == '--terminal',bad,
                      color=values.get('--color'),
                      allow_overwrite=opt_allow_overwrite)
        sys.exit(0)

    if mode == '--text':
        if len(filelist)>2:
            bad("too many arguments")
        if len(filelist)!=2:
            bad("must specify both input and output files with --text")
        _check_inputs(filelist[:1])
        #(the output file must not be the input file, or exist unless allowed):
        try:
            same = os.path.samefile(filelist[1],filelist[0])
        except OSError:
            same = False
        if same:
            raise MCPLError(f'The output file "{filelist[1]}" is also one of the input files')
        if not opt_allow_overwrite and os.path.lexists(filelist[1]):
            raise MCPLError(f'The output file "{filelist[1]}" already exists')
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
            raise MCPLError(f'{filelist[1]}: can not open the file for writing')
        try:
            convert2ascii(filelist[0],fout)
        finally:
            fout.close()
        sys.exit(0)

    #Dump, stats, or repair:
    if len(filelist)>1:
        bad("too many arguments")
    if not filelist:
        bad("no input file specified")
    _check_inputs(filelist)

    if mode == '--repair':
        from ._fileops import repair
        repair(filelist[0], dry_run = opt_dryrun)
        _mcpltool_dryrun_note(opt_dryrun)
        sys.exit(0)

    if mode == '--stats':
        from ._clistats import mcpltool_stats
        mcpltool_stats(filelist[0],opt_skip,opt_limit,edit)
        sys.exit(0)

    #Dump
    opt_justhead, opt_nohead = '--justhead' in flags, '--nohead' in flags
    if opt_blobkey:
        if ( opt_justhead or opt_nohead or opt_limit is not None
             or opt_skip is not None or edit is not None ):
            bad("do not specify other dump options with -b")
        with MCPLFile(filelist[0]) as f:
            thedata = f.blobs.get(opt_blobkey,None)
            if thedata is None and 'blobs_raw' in f._hdr:
                #Under LANG=C and python3, utf-8 keys might be in trouble:
                thedata = f._hdr['blobs_raw'].get(os.fsencode(opt_blobkey),None)
            if thedata is None:
                raise MCPLError(f'{filelist[0]}: no blob with the key "{opt_blobkey}"')
            if sys.platform == "win32":
                import msvcrt
                msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
            _output_bytearray_raw(thedata)
            sys.exit(0)
    if (opt_limit is not None or opt_skip is not None) and opt_justhead:
        bad("do not specify -l or -s with --justhead")
    if edit is not None and opt_justhead:
        bad("do not specify -e with --justhead")
    if opt_justhead and opt_nohead:
        bad("do not specify both --justhead and --nohead")
    #(-l and -s give the range of particles in the file, before -e):
    from ._reader import _dump
    with MCPLFile(filelist[0],skip=opt_skip,limit=opt_limit,edit=edit) as f:
        _dump(f,not opt_nohead,not opt_justhead,10 if opt_limit is None else 0)
    sys.exit(0)

def _check_inputs( filenames ):
    """Error (naming the file) for input files which do not exist, or are
    directories"""
    for fn in filenames:
        if not os.path.lexists(fn):
            raise MCPLError(f'{fn}: no such file')
        if os.path.isdir(fn):
            raise MCPLError(f'{fn}: is a directory')

def _mcpltool_dryrun_note(dry_run):
    if dry_run:
        _info('dry run, nothing was written')

def _mcpltool_merge(filelist, opt_forcemerge, opt_inplace, opt_keepuserflags,
                      dry_run, allow_overwrite = False):
    ifirst = 0 if opt_inplace else 1
    _check_inputs(filelist[ifirst:])
    from ._fileops import forcemerge_files, merge_files, merge_inplace
    if not opt_forcemerge:
        from ._fileops import _merge_incompat_reason, _open_raw
        for f in filelist[ifirst+1:]:
            with _open_raw(filelist[ifirst]) as f1, _open_raw(f) as f2:
                reason = _merge_incompat_reason(f1, f2)
            if reason is not None:
                raise MCPLError("Requested files are incompatible for merge as they have"
                                f" different header info ({reason})")
    if opt_inplace:
        for f in filelist[ifirst+1:]:
            merge_inplace(filelist[ifirst],f,dry_run=dry_run)
        return
    from ._extract import _mcpltool_close, _tool_check_outfn
    outfn = filelist[0]
    err = _tool_check_outfn( outfn, filelist[1:], allow_overwrite )
    if err:
        raise MCPLError(err)
    if opt_forcemerge:
        out = forcemerge_files(outfn,filelist[1:],keep_userflags=opt_keepuserflags,
                               allow_overwrite=allow_overwrite,dry_run=dry_run)
    else:
        out = merge_files(outfn,filelist[1:],allow_overwrite=allow_overwrite,
                          dry_run=dry_run)
    if out is not None:
        _mcpltool_close(out)

def main():
    """This function simply calls app_mcpltool(), but any raised MCPLError
    exception will be caught and printed to standard error, followed by a call
    to sys.exit(1). This is what the mcpltool command and "python -m mcpl"
    run. With the --traceback option, MCPLError exceptions are not caught, so
    their Python traceback is shown."""
    if '--traceback' in sys.argv[1:]:
        app_mcpltool()
        return
    try:
        app_mcpltool()
    except MCPLError as e:
        sys.stdout.flush()
        print(f'{_progname(sys.argv[0])}: {e!s}',file = sys.stderr)
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
