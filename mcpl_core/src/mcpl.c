
////////////////////////////////////////////////////////////////////////////////
//                                                                            //
//  This file is part of MCPL (see https://mctools.github.io/mcpl/)           //
//                                                                            //
//  Copyright 2015-2026 MCPL developers.                                      //
//                                                                            //
//  Licensed under the Apache License, Version 2.0 (the "License");           //
//  you may not use this file except in compliance with the License.          //
//  You may obtain a copy of the License at                                   //
//                                                                            //
//      http://www.apache.org/licenses/LICENSE-2.0                            //
//                                                                            //
//  Unless required by applicable law or agreed to in writing, software       //
//  distributed under the License is distributed on an "AS IS" BASIS,         //
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  //
//  See the License for the specific language governing permissions and       //
//  limitations under the License.                                            //
//                                                                            //
////////////////////////////////////////////////////////////////////////////////

////////////////////////////////////////////////////////////////////////////////
//                                                                            //
//  Monte Carlo Particle Lists : MCPL                                         //
//                                                                            //
//  Utilities for reading and writing .mcpl files: A binary format with       //
//  lists of particle state information, for interchanging and reshooting     //
//  events between various Monte Carlo simulation applications.               //
//                                                                            //
//  Client code including mcpl.h does not need any special build flags and    //
//  can be compiled with any complient compiler and any current C or C++      //
//  standard.                                                                 //
//                                                                            //
//  Compilation of mcpl.c on the other hand is currently not supported for    //
//  C89, although this could be revisited. Thus, compilation of mcpl.c can    //
//  proceed using any complient C-compiler using -std=c99 or -std=c11 or any  //
//  complient C++ compiler using any version of the C++ standard, and the     //
//  resulting code must always be linked with libm (using -lm).               //
//                                                                            //
//  Find more information and updates at https://mctools.github.io/mcpl/      //
//                                                                            //
//  Written by Thomas Kittelmann, 2015-2026.                                  //
//                                                                            //
////////////////////////////////////////////////////////////////////////////////


////////////////////////////////////////////////////////////////////////////////
//  MCPL_FORMATVERSION history:                                               //
//                                                                            //
//  3: Current version. Changed packing of unit vectors from octahedral to    //
//     the better performing "Adaptive Projection Packing".                   //
//  2: First public release.                                                  //
//  1: Format used during early development. No longer supported.             //
////////////////////////////////////////////////////////////////////////////////

//Before including mcpl.h, we attempt to get PRIu64 defined in a relatively
//robust manner by enabling feature test macros for gcc and including relevant
//headers:
#ifndef __STDC_FORMAT_MACROS
#  define __STDC_FORMAT_MACROS
#endif
#ifndef _POSIX_C_SOURCE
#  define _POSIX_C_SOURCE 200809L
#endif
#ifndef _ISOC99_SOURCE
#  define _ISOC99_SOURCE 1
#endif
#ifndef _C99_SOURCE
#  define _C99_SOURCE 1
#endif
#ifdef _FILE_OFFSET_BITS
#  undef _FILE_OFFSET_BITS
#endif
#define _FILE_OFFSET_BITS 64
#include <inttypes.h>
#include <stdio.h>
#ifndef PRIu64//bad compiler - fallback to guessing
#  if defined(_MSC_VER) && (_MSC_VER<1900)
#    define PRIu64 "I64u"
#  else
#    if defined(__WORDSIZE) && (__WORDSIZE==64)
#      define PRIu64 "lu"
#    else
#      define PRIu64 "llu"
#    endif
#  endif
#endif

#include "mcpl.h"
#include "zlib.h"
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <math.h>
#include <limits.h>

#ifdef Z_SOLO
#  error "MCPL needs zlib with gzip functionality"
#endif

#ifndef INFINITY
//Missing in ICC 12 C99 compilation:
#  define  INFINITY (__builtin_inf())
#endif

#include "mcpl_fileutils.h"

#define MCPLIMP_NPARTICLES_POS 8
#define MCPLIMP_MAX_PARTICLE_SIZE 96
#define MCPL_STATIC_ASSERT0(COND,MSG) { typedef char mcpl_##MSG[(COND)?1:-1]; mcpl_##MSG dummy; (void)dummy; }
#define MCPL_STATIC_ASSERT3(expr,x) MCPL_STATIC_ASSERT0(expr,fail_at_line_##x)
#define MCPL_STATIC_ASSERT2(expr,x) MCPL_STATIC_ASSERT3(expr,x)
#define MCPL_STATIC_ASSERT(expr)    MCPL_STATIC_ASSERT2(expr,__LINE__)

MCPL_LOCAL void mcpl_default_print_handler( const char * msg )
{
  printf("%s",msg);
}

//Make sure we don't have any raw printf's below
#ifdef printf
#  undef printf
#endif
#define printf MCPLNOUSEPRINTF

typedef void (*MCPL_CHARTOVOID_FCT)(const char *);

MCPL_LOCAL MCPL_CHARTOVOID_FCT* mcpl_current_print_handler(void)
{
  static MCPL_CHARTOVOID_FCT current = NULL;
  return &current;
}

MCPL_LOCAL void mcpl_print( const char * msg )
{
  MCPL_CHARTOVOID_FCT current = *mcpl_current_print_handler();
  if (!current) {
    mcpl_default_print_handler(msg);
  } else {
    current(msg);
  }
}

#define MCPL_STRINGIFY(x)   MCPL_STRINGIFY2(x)
#define MCPL_STRINGIFY2(x)  #x

MCPL_LOCAL void mcpl_default_error_handler(const char * msg) {
  char buf[4096];
  if ( strlen(msg)+64 < sizeof(buf) ) {
    snprintf(buf,sizeof(buf),"MCPL ERROR: %s\n",msg);
    mcpl_print(buf);
  } else {
    mcpl_print("MCPL ERROR:\n");
    mcpl_print(msg);
  }
  exit(1);
}

MCPL_LOCAL MCPL_CHARTOVOID_FCT* mcpl_current_error_handler(void)
{
  static MCPL_CHARTOVOID_FCT current = NULL;
  return &current;
}

MCPL_LOCAL void mcpl_error(const char * msg)
{
  MCPL_CHARTOVOID_FCT current = *mcpl_current_error_handler();
  if (!current) {
    mcpl_default_error_handler(msg);
  } else {
    current(msg);
    //Error handler should not return, but in case it does anyway, we use the
    //default handler to ensure a hard exit.
    mcpl_default_error_handler("Handler given to mcpl_set_error_handler returns"
                               " to calling code which is not allowed!");
  }
}

MCPL_LOCAL char * mcpl_internal_malloc(size_t n)
{
  char * res = (char*)malloc(n ? n : 1);
  if (!res)
    mcpl_error("memory allocation failed");
  return res;
}

MCPL_LOCAL char * mcpl_internal_calloc(size_t num, size_t size)
{
  char * res = (char*)calloc( ( num ? num : 1 ),
                              ( size ? size : 1 ) );
  if (!res)
    mcpl_error("memory allocation failed");
  return res;
}

MCPL_LOCAL void * mcpl_internal_realloc( void* mem, size_t new_size)
{
  void * res = realloc( mem, new_size );
  if (!res)
    mcpl_error("memory allocation failed");
  return res;
}

void mcpl_set_error_handler(void (*handler)(const char *))
{
  MCPL_CHARTOVOID_FCT* cptr = mcpl_current_error_handler();
  *cptr = handler;
}

void mcpl_set_print_handler(void (*handler)(const char *))
{
  MCPL_CHARTOVOID_FCT* cptr = mcpl_current_print_handler();
  *cptr = handler;
}

MCPL_LOCAL int mcpl_platform_is_little_endian(void) {
  //Return 0 for big endian, 1 for little endian.
  volatile uint32_t i=0x01234567;
  return (*((uint8_t*)(&i))) == 0x67;
}

MCPL_LOCAL void mcpl_store_string(char** dest, const char * src)
{
  size_t n = strlen(src);
  if (n>65534) {
    n = 65534;
    mcpl_error("string length out of range");
  }
  if (*dest)
    free(*dest);
  *dest = mcpl_internal_malloc(n+1);

  //Usage of strncpy cause compiler warning on newer gcc, so we use memcpy
  //instead (should be safe, we just checked strlen above!):
  //strncpy( *dest,src,n );
  memcpy( *dest,src,n );
  (*dest)[n] = '\0';
  return;
}

MCPL_LOCAL void mcpl_write_buffer(FILE* f, uint32_t n, const char * data, const char * errmsg)
{
  size_t nb = fwrite(&n, 1, sizeof(n), f);
  if (nb!=sizeof(n))
    mcpl_error(errmsg);
  nb = fwrite(data, 1, n, f);
  if (nb!=n)
    mcpl_error(errmsg);
}

MCPL_LOCAL void mcpl_write_string(FILE* f, const char * str, const char * errmsg)
{
  size_t n = strlen(str);
  if ( n >= 4294967295 )
    mcpl_error("too large string encountered");
  mcpl_write_buffer(f,(uint32_t)n,str,errmsg);//nb: we don't write the terminating null-char
}

MCPL_LOCAL int mcpl_internal_fakeconstantversion( int enable )
{
  //For consistent output of unit tests:
  static int fakev = 0;
  if ( enable )
    fakev = 1;
  return fakev;
}

#define MCPL_STATSUMINI "stat:sum:"
#define MCPL_STATSUMINI_LENGTH (sizeof(MCPL_STATSUMINI)-1)
#define MCPL_STATSUMKEY_MAXLENGTH 64
#define MCPL_STATSUMVAL_LENGTH 24
#define MCPL_STATSUMVAL_ENCODEDZERO   "                       0"
#define MCPL_STATSUMBUF_MAXLENGTH ( MCPL_STATSUMKEY_MAXLENGTH + \
                                    MCPL_STATSUMVAL_LENGTH +    \
                                    MCPL_STATSUMINI_LENGTH +   \
                                    1 ) //+1 for final colon

typedef struct MCPL_LOCAL {
  char key[MCPL_STATSUMKEY_MAXLENGTH+1];
  double value;
  uint32_t writtenstrlen;
  uint64_t writtenpos;
} mcpl_internal_statsuminfo_t;

typedef struct MCPL_LOCAL {
  char * filename;
  FILE * file;
  char * hdr_srcprogname;
  uint32_t ncomments;
  char ** comments;
  uint32_t nblobs;
  char ** blobkeys;
  uint32_t * bloblengths;
  char ** blobs;
  int opt_userflags;
  int opt_polarisation;
  int opt_singleprec;
  int32_t opt_universalpdgcode;
  double opt_universalweight;
  int header_notwritten;
  uint64_t nparticles;
  unsigned particle_size;
  mcpl_particle_t* puser;
  unsigned opt_signature;
  char particle_buffer[MCPLIMP_MAX_PARTICLE_SIZE];
  mcpl_internal_statsuminfo_t * statsuminfo;
  unsigned nstatsuminfo;
} mcpl_outfileinternal_t;

#define MCPLIMP_OUTFILEDECODE mcpl_outfileinternal_t * f = (mcpl_outfileinternal_t *)of.internal; assert(f)

MCPL_LOCAL void mcpl_recalc_psize(mcpl_outfile_t of)
{
  MCPLIMP_OUTFILEDECODE;
  unsigned fp = f->opt_singleprec ? sizeof(float) : sizeof(double);
  f->particle_size = 7*fp;
  if (f->opt_polarisation)
    f->particle_size += 3*fp;
  if (!f->opt_universalpdgcode)
    f->particle_size += sizeof(int32_t);
  if (!f->opt_universalweight)
    f->particle_size += fp;
  if (f->opt_userflags)
    f->particle_size += sizeof(uint32_t);
  if ( ! (f->particle_size<=MCPLIMP_MAX_PARTICLE_SIZE) )
    mcpl_error("unexpected particle size");
  f->opt_signature = 0
    + 1 * f->opt_singleprec
    + 2 * f->opt_polarisation
    + 4 * (f->opt_universalpdgcode?1:0)
    + 8 * (f->opt_universalweight?1:0)
    + 16 * f->opt_userflags;
}

MCPL_LOCAL void mcpl_platform_compatibility_check(void) {
  MCPL_STATIC_ASSERT(CHAR_BIT==8);
  MCPL_STATIC_ASSERT(sizeof(float)==4);
  MCPL_STATIC_ASSERT(sizeof(double)==8);

  int32_t m1_32 = -1;
  int32_t not0_32 = ~((int32_t)0);
  int64_t m1_64 = -1;
  int64_t not0_64 = ~((int64_t)0);
  if ( m1_32 != not0_32 || m1_64 != not0_64 )
    mcpl_error("Platform compatibility check failed (integers are not two's complement)");

  if (copysign(1.0, -0.0) != -1.0)
    mcpl_error("Platform compatibility check failed (floating point numbers do not have signed zero)");

  mcpl_particle_t pd;
  if ( (char*)&(pd.userflags)-(char*)&(pd) != 12*sizeof(double)+sizeof(uint32_t) )
    mcpl_error("Platform compatibility check failed (unexpected padding in mcpl_particle_t)");
}

MCPL_LOCAL FILE * mcpl_internal_fopen( const char * filename, const char * mode )
{
  mcu8str f = mcu8str_view_cstr( filename );
  return mctools_fopen( &f, mode );
}

MCPL_LOCAL void mcpl_internal_cleanup_outfile(mcpl_outfileinternal_t * f)
{
  if (!f)
    return;
  if ( f->file ) {
    fclose(f->file);
    f->file = NULL;
  }
  if ( f->filename ) {
    free(f->filename);
    f->filename = NULL;
  }
  if ( f->puser ) {
    free(f->puser);
    f->puser = NULL;
  }
  if ( f->statsuminfo ) {
    free(f->statsuminfo);
    f->statsuminfo = NULL;
  }
  free(f);
}

mcpl_outfile_t mcpl_create_outfile(const char * filename)
{
  //Sanity check chosen filename and append ".mcpl" if missing to help people
  //who forgot to add the extension (in the hope of higher consistency).
  if (!filename)
    mcpl_error("mcpl_create_outfile called with null string.");
  size_t n = strlen(filename);
  if (!n)
    mcpl_error("mcpl_create_outfile called with empty string.");
  if (n>4096)
    mcpl_error("mcpl_create_outfile called with too long string.");
  const char * lastdot = strrchr(filename, '.');
  if (lastdot==filename && n==5)
    mcpl_error("mcpl_create_outfile called with string with no basename part (\".mcpl\").");

  //Initialise data structures and open file:
  mcpl_platform_compatibility_check();

  mcpl_outfile_t out;
  out.internal = NULL;

  mcpl_outfileinternal_t * f
    = (mcpl_outfileinternal_t*)mcpl_internal_calloc( 1, sizeof(mcpl_outfileinternal_t) );

  if (!lastdot || strcmp(lastdot, ".mcpl") != 0) {
    f->filename = mcpl_internal_malloc(n+6);
    memcpy(f->filename,filename,n);
    memcpy(f->filename+n,".mcpl",6);
  } else {
    f->filename = mcpl_internal_malloc(n+1);
    memcpy(f->filename,filename,n+1);
  }

  f->hdr_srcprogname = NULL;
  f->ncomments = 0;
  f->comments = NULL;
  f->nblobs = 0;
  f->blobkeys = NULL;
  f->bloblengths = NULL;
  f->blobs = NULL;
  f->opt_userflags = 0;
  f->opt_polarisation = 0;
  f->opt_singleprec = 1;
  f->opt_universalpdgcode = 0;
  f->opt_universalweight = 0.0;
  f->header_notwritten = 1;
  f->nparticles = 0;

  f->puser = NULL;
  f->statsuminfo = NULL;
  f->nstatsuminfo = 0;
  f->file = mcpl_internal_fopen(f->filename,"wb");
  if (!f->file) {
    mcpl_internal_cleanup_outfile(f);
    mcpl_error("Unable to open output file!");
  }
  out.internal = f;
  mcpl_recalc_psize(out);
  return out;
}

const char * mcpl_outfile_filename(mcpl_outfile_t of) {
  MCPLIMP_OUTFILEDECODE;
  return f->filename;
}

void mcpl_hdr_set_srcname(mcpl_outfile_t of,const char * spn)
{
  MCPLIMP_OUTFILEDECODE;
  if (!f->header_notwritten)
    mcpl_error("mcpl_hdr_set_srcname called too late.");
  mcpl_store_string(&(f->hdr_srcprogname),spn);
}

MCPL_LOCAL int mcpl_check_char( const char * c, int allow_extra )
{
  // Check that cstr only contains certain allowed characters. This is
  // alphanumeric or underscore ("a-zA-Z0-9_"), and if allow_extra is set, also
  // "+-.:"
  while ( *c ) {
    int isanum = ( ( *c >= 'a' && *c <= 'z' )
                   || ( *c >= 'A' && *c <= 'Z' )
                   || ( *c >= '0' && *c <= '9' ) );
    if ( !isanum && *c != '_' ) {
      if ( allow_extra ) {
        if ( *c != '+' && *c != '-'  && *c != '.' && *c != ':' )
          return 0;
      } else {
        return 0;
      }
    }
    ++c;
  }
  return 1;
}

MCPL_LOCAL int mcpl_check_isidentifier( const char * c )
{
  //Check if could be used as an identifier in Python/C++/C (not counting
  //reserved words and so on). Must be nonempty, only alphanumeric + underscore,
  //and must start with a letter.
  return ( ( (*c>='a'&&*c<='z')||(*c>='A'&&*c<='Z') )
           && mcpl_check_char( c, 0 ) );
}

#define MCPL_COMMENT_IS_STATSUM(x) ( *x == 's' \
                                     && strncmp(x,MCPL_STATSUMINI,      \
                                                MCPL_STATSUMINI_LENGTH)==0 )


typedef struct MCPL_LOCAL {
  //The rest is only if actually starts with "stat:sum:":

  //Error message in case of syntax errors (NULL means OK):
  const char * errmsg;
  double value;//-1 or >=0 (never inf or nan)
  char key[MCPL_STATSUMKEY_MAXLENGTH+1];
} mcpl_internal_statsum_t;

MCPL_LOCAL void mcpl_internal_statsumparse( const char * comment,
                                            mcpl_internal_statsum_t* res )
{
  res->key[0] = 0;
  res->value = -2;
  res->errmsg = NULL;

  if ( !MCPL_COMMENT_IS_STATSUM(comment) )
    return;

  res->key[0] = 0;
  res->value = -2;
  res->errmsg = NULL;

  const char * c = comment + MCPL_STATSUMINI_LENGTH;
  const char * csep = strchr(c,':');
  if (!csep) {
    res->errmsg = "did not find colon separating key and value";
    return;
  }
  size_t nkey = csep - c;
  if ( nkey < 1 ) {
    res->errmsg = "empty key";
    return;
  }
  if ( nkey > MCPL_STATSUMKEY_MAXLENGTH ) {
    res->errmsg = ( "key length exceeds "
                   MCPL_STRINGIFY(MCPL_STATSUMKEY_MAXLENGTH) " characters" );
    return;
  }
  memcpy( res->key, c, nkey );
  res->key[nkey] = 0;
  if (!mcpl_check_isidentifier(res->key)) {
    res->errmsg = ( "key does not adhere to naming [a-zA-Z][a-zA-Z0-9_]*" );
    res->key[0] = 0;
    return;
  }
  c += nkey;
  if ( !*c || csep != c )
    mcpl_error("mcpl_internal_statsumparse logic error");
  ++c; //skip colon as well
  if ( strlen(c) != MCPL_STATSUMVAL_LENGTH ) {
    res->errmsg = ( "value field is not exactly "
                    MCPL_STRINGIFY(MCPL_STATSUMVAL_LENGTH)
                    " characters wide" );
    return;
  }

  //We will ultimately use strtod to parse the value, but first we will
  //explicitly strip trailing or leading simply space (' ') chars:
  char bufval[MCPL_STATSUMVAL_LENGTH+1];
  const char * expected_str_end = NULL;
  {
    const char * cE = c + MCPL_STATSUMVAL_LENGTH;
    while ( *c == ' ' )
      ++c;//ignore initial space
    while ( cE > c && *(cE-1)==' ' )
      --cE;
    if ( c == cE ) {
      res->errmsg = "value field missing actual value";
      return;
    }
    memcpy(bufval,c,cE-c);
    bufval[cE-c] = 0;
    expected_str_end = &(bufval[cE-c]);
  }
  {
    //check that only chars in "0123456789.-+eE" are allowed.
    const char * bp = bufval;
    while ( *bp ) {
      char b = *bp;
      if ( ! ( ('0'<= b && b<='9')
               || b=='.' || b=='-' || b== '+'
               || b=='e' || b=='E' ) ) {
        res->errmsg = ( "value field holds forbidden characters, only"
                        " 0123456789.-+eE are allowed in addition to leading"
                        " or trailing simply spaces)" );
        return;
      }
      ++bp;
    }
  }

  char * str_end;
  double val = strtod( bufval, &str_end );
  if ( str_end != expected_str_end ) {
    res->errmsg = "could not decode contents of value field";
    return;
  }
  if ( isnan(val) ) {
    res->errmsg = "value field holds forbidden value (NaN)";
    return;
  }
  if ( !( val>=0.0 || val == -1.0 ) ) {
    res->errmsg = "value field must hold non-zero value or -1";
    return;
  }
  if ( isinf(val) ) {
    res->errmsg = "value field holds forbidden value (+INFINITY)";
    return;
  }
  res->value = val;
  return;
}

MCPL_LOCAL void mcpl_internal_statsum_parse_or_emit_err( const char * comment,
                                                         mcpl_internal_statsum_t* res )
{
  mcpl_internal_statsumparse( comment, res );
  if ( !res->errmsg )
    return;
  if ( strlen(comment) > 16*MCPL_STATSUMBUF_MAXLENGTH
       || strlen(res->errmsg) > 1024 ) {
    mcpl_error("Syntax error: could not properly decode comment "
               "starting with \"stat:sum:\" (content too long to show)");
  } else {
    char buf[1200+16*MCPL_STATSUMBUF_MAXLENGTH];
    snprintf(buf,sizeof(buf),
             "Syntax error: could not properly decode comment starting"
             " with \"stat:sum:\" (%s). Issue with comment \"%s\"",
             res->errmsg,comment);
    mcpl_error(buf);
  }
}

void mcpl_hdr_add_comment(mcpl_outfile_t of,const char *comment)
{
  MCPLIMP_OUTFILEDECODE;
  if (!f->header_notwritten)
    mcpl_error("mcpl_hdr_add_comment called too late.");
  if ( MCPL_COMMENT_IS_STATSUM(comment) ) {
    //comment starts with "stat:sum:". Let us require it to live up to the
    //syntax by decoding it, to trigger any issues:
    mcpl_internal_statsum_t sc;
    mcpl_internal_statsum_parse_or_emit_err( comment, &sc );
  } else {
    if ( strncmp( comment, "stat:", 5 ) == 0 )
      mcpl_error("Refusing to create file with comments starting with"
                 " \"stat:\" unless starting with \"stat:sum:\", as such"
                 " syntax is reserved for future usage.");
  }
  size_t oldn = f->ncomments;
  f->ncomments += 1;
  if (oldn)
    f->comments = (char **)mcpl_internal_realloc( f->comments,
                                                  f->ncomments * sizeof(char*) );
  else
    f->comments = (char **)mcpl_internal_calloc(f->ncomments,sizeof(char*));
  f->comments[oldn] = NULL;
  mcpl_store_string(&(f->comments[oldn]),comment);
}

void mcpl_hdr_add_data(mcpl_outfile_t of, const char * key,
                       uint32_t ldata, const char * data)
{
  MCPLIMP_OUTFILEDECODE;
  if (!f->header_notwritten)
    mcpl_error("mcpl_hdr_add_data called too late.");
  size_t oldn = f->nblobs;
  f->nblobs += 1;
  //Check that key is unique
  unsigned i;
  for (i = 0; i<oldn; ++i) {
    if (strcmp(f->blobkeys[i],key)==0)
      mcpl_error("mcpl_hdr_add_data got duplicate key");
  }
  //store key:
  if (oldn)
    f->blobkeys = (char **)mcpl_internal_realloc(f->blobkeys,
                                                 f->nblobs * sizeof(char*) );
  else
    f->blobkeys = (char **)mcpl_internal_calloc(f->nblobs,
                                                sizeof(char*));
  f->blobkeys[oldn] = NULL;
  mcpl_store_string(&(f->blobkeys[oldn]),key);
  //store blob-lengths:
  if (oldn)
    f->bloblengths = (uint32_t*)mcpl_internal_realloc(f->bloblengths,
                                                      f->nblobs * sizeof(uint32_t) );
  else
    f->bloblengths = (uint32_t *)mcpl_internal_calloc(f->nblobs,
                                                      sizeof(uint32_t));
  f->bloblengths[oldn] = ldata;

  //store data:
  if (oldn)
    f->blobs = (char **)mcpl_internal_realloc(f->blobs,
                                              f->nblobs * sizeof(char*) );
  else
    f->blobs = (char **)mcpl_internal_calloc(f->nblobs,
                                             sizeof(char*));
  f->blobs[oldn] = mcpl_internal_malloc(ldata);
  memcpy(f->blobs[oldn],data,ldata);
}

void mcpl_enable_userflags(mcpl_outfile_t of)
{
  MCPLIMP_OUTFILEDECODE;
  if (f->opt_userflags)
    return;
  if (!f->header_notwritten)
    mcpl_error("mcpl_enable_userflags called too late.");
  f->opt_userflags = 1;
  mcpl_recalc_psize(of);
}

void mcpl_enable_polarisation(mcpl_outfile_t of)
{
  MCPLIMP_OUTFILEDECODE;
  if (f->opt_polarisation)
    return;
  if (!f->header_notwritten)
    mcpl_error("mcpl_enable_polarisation called too late.");
  f->opt_polarisation = 1;
  mcpl_recalc_psize(of);
}

void mcpl_enable_doubleprec(mcpl_outfile_t of)
{
  MCPLIMP_OUTFILEDECODE;
  if (!f->opt_singleprec)
    return;
  if (!f->header_notwritten)
    mcpl_error("mcpl_enable_doubleprec called too late.");
  f->opt_singleprec = 0;
  mcpl_recalc_psize(of);
}

void mcpl_enable_universal_pdgcode(mcpl_outfile_t of, int32_t pdgcode)
{
  MCPLIMP_OUTFILEDECODE;
  if (pdgcode==0)
    mcpl_error("mcpl_enable_universal_pdgcode must be called with non-zero pdgcode.");
  if (f->opt_universalpdgcode) {
    if (f->opt_universalpdgcode!=pdgcode)
      mcpl_error("mcpl_enable_universal_pdgcode called multiple times");
    return;
  }
  if (!f->header_notwritten)
    mcpl_error("mcpl_enable_universal_pdgcode called too late.");
  f->opt_universalpdgcode = pdgcode;
  mcpl_recalc_psize(of);
}

void mcpl_enable_universal_weight(mcpl_outfile_t of, double w)
{
  MCPLIMP_OUTFILEDECODE;
  if (w<=0.0||isinf(w)||isnan(w))
    mcpl_error("mcpl_enable_universal_weight must be called with positive but finite weight.");
  if (f->opt_universalweight) {
    if (f->opt_universalweight!=w)
      mcpl_error("mcpl_enable_universal_weight called multiple times");
    return;
  }
  if (!f->header_notwritten)
    mcpl_error("mcpl_enable_universal_weight called too late.");
  f->opt_universalweight = w;
  mcpl_recalc_psize(of);
}

MCPL_LOCAL void mcpl_internal_encodestatsum( const char * key,
                                             double value,
                                             char * targetbuf )
{
  //Sanity check value:
  size_t nbufleft = MCPL_STATSUMBUF_MAXLENGTH+1;
  if ( isnan(value) )
    mcpl_error("Invalid value for \"stat:sum:...\". Value is invalid (NaN)");
  if ( isinf(value) ) {
    if ( value > 0.0 )
      mcpl_error("Invalid value for \"stat:sum:...\". Value is invalid (+INF).");
    else
      mcpl_error("Invalid value for \"stat:sum:...\". Value is invalid (-INF).");
  }
  if ( !( value>=0.0 || value==-1.0 ) ) {
      char ebuf[256];
      snprintf(ebuf,sizeof(ebuf),"Invalid value for \"stat:sum:...\"."
               " Value is negative but is not -1.0 (it is %.15g).",value);
      mcpl_error(ebuf);
  }
  //Check key:
  size_t nkey = strlen(key);
  if ( nkey < 1 )
    mcpl_error("stat:sum: key must not be empty");
  if ( nkey > MCPL_STATSUMKEY_MAXLENGTH ) {
    size_t nbuf = 128 + nkey;
    char fixbuf[2056];
    char * buf = fixbuf;
    if ( nbuf > sizeof(fixbuf) )
      buf = mcpl_internal_malloc(nbuf);//never freed, but need to pass to
                                       //non-returning mcpl_error so we can not.
    snprintf(buf,nbuf,
             "stat:sum: key \"%s\" too long (%llu chars, max %i allowed)",
             key,
             (unsigned long long)nkey,
             (int)(MCPL_STATSUMKEY_MAXLENGTH) );
    mcpl_error(buf);
  }

  if ( !mcpl_check_isidentifier(key) ) {
    char buf[MCPL_STATSUMKEY_MAXLENGTH+256];
    snprintf(buf,sizeof(buf),
             "Invalid stat:sum: key \"%s\" (must begin with a letter and"
             " otherwise only contain alphanumeric characters and underscores)",
             key);
    mcpl_error(buf);
  }

  //Add initial marker including colon:
  MCPL_STATIC_ASSERT( MCPL_STATSUMINI_LENGTH < MCPL_STATSUMBUF_MAXLENGTH );
  memcpy(targetbuf, MCPL_STATSUMINI, MCPL_STATSUMINI_LENGTH);
  targetbuf += MCPL_STATSUMINI_LENGTH;
  nbufleft -= MCPL_STATSUMINI_LENGTH;

  //Add key marker:
  if ( nkey > nbufleft )
    mcpl_error("stat:sum: encode buffer error");
  memcpy(targetbuf, key, nkey );
  targetbuf += nkey;
  nbufleft -= nkey;

  //Add colon:
  if ( !nbufleft )
    mcpl_error("stat:sum: encode buffer error");
  *targetbuf = ':';
  ++targetbuf;
  --nbufleft;

  //Add MCPL_STATSUMVAL_LENGTH bytes containing the actual value, as well as a
  //final null termination byte:
  if ( nbufleft < MCPL_STATSUMVAL_LENGTH + 1 )
    mcpl_error("stat:sum: encode buffer error");
  if ( value == 0.0 ) {
    //special case, like this to ensure we do not format a negative zero with
    //the sign.
    MCPL_STATIC_ASSERT(sizeof(MCPL_STATSUMVAL_ENCODEDZERO) == MCPL_STATSUMVAL_LENGTH + 1 );
    memcpy( targetbuf, MCPL_STATSUMVAL_ENCODEDZERO, MCPL_STATSUMVAL_LENGTH + 1 );
  } else {
    //In general lossless encoding of doubles require .17g, but we first try
    //with .15g to potentially avoid messy encodings like 0.1 being encoded as
    //"0.10000000000000001" rather than "0.1".
    int w1 = snprintf( targetbuf, nbufleft,
                       "%" MCPL_STRINGIFY(MCPL_STATSUMVAL_LENGTH) ".15g",
                       value );
    if ( w1 != MCPL_STATSUMVAL_LENGTH )
      mcpl_error("stat:sum: value encoding length error");
    double v = strtod( targetbuf, NULL );
    if ( v != value ) {
      //ok, .15g was not good enough, go for full .17g:
      int w2 = snprintf( targetbuf,
                         nbufleft,
                         "%" MCPL_STRINGIFY(MCPL_STATSUMVAL_LENGTH) ".17g",
                         value );
      if ( w2 != MCPL_STATSUMVAL_LENGTH )
        mcpl_error("stat:sum: value encoding length error");
    }
  }

  if ( strlen( targetbuf ) != MCPL_STATSUMVAL_LENGTH )
    mcpl_error("Unexpected encoding of stat:sum: value");
}

#ifdef _WIN32
#  define MCPL_FSEEK( fh, pos)  _fseeki64(fh,(__int64)(pos), SEEK_SET)
#  define MCPL_FSEEK_CUR( fh, pos)  _fseeki64(fh,(__int64)(pos), SEEK_CUR)
#  define MCPL_FSEEK_END( fh)  _fseeki64(fh,(__int64)(0), SEEK_END)
#  define MCPL_FTELL( fh)  _ftelli64(fh)
#else
#  define MCPL_FSEEK( fh, pos) fseek(fh,(ssize_t)(pos), SEEK_SET)
#  define MCPL_FSEEK_CUR( fh, pos) fseek(fh,(ssize_t)(pos), SEEK_CUR)
#  define MCPL_FSEEK_END( fh) fseek(fh,(ssize_t)(0), SEEK_END)
#  define MCPL_FTELL( fh) ftell(fh)
#endif

MCPL_LOCAL void mcpl_write_header(mcpl_outfileinternal_t * f)
{
  if (!f->header_notwritten)
    mcpl_error("Logical error!");

  const char * errmsg="Errors encountered while attempting to write file header.";
  //Always start the file with an unsigned char-array (for endian agnosticity)
  //containing magic word (MCPL), file format version ('001'-'999') and
  //endianness used in the file ('L' or 'B'):
  unsigned char start[8] = {'M','C','P','L','0','0','0','L'};
  start[4] = (MCPL_FORMATVERSION/100)%10 + '0';
  start[5] = (MCPL_FORMATVERSION/10)%10 + '0';
  start[6] = MCPL_FORMATVERSION%10 + '0';
  if (!mcpl_platform_is_little_endian())
    start[7] = 'B';
  size_t nb = fwrite(start, 1, sizeof(start), f->file);
  if (nb!=sizeof(start))
    mcpl_error(errmsg);

  //Right after the initial 8 bytes, we put the number of particles (0 for now,
  //but important that position is fixed so we can seek and update it later).:
  int64_t nparticles_pos = MCPL_FTELL(f->file);
  if (nparticles_pos!=MCPLIMP_NPARTICLES_POS)
    mcpl_error(errmsg);
  nb = fwrite(&f->nparticles, 1, sizeof(f->nparticles), f->file);
  if (nb!=sizeof(f->nparticles))
    mcpl_error(errmsg);

  //Then a bunch of numbers:
  uint32_t arr[8];
  arr[0] = f->ncomments;
  arr[1] = f->nblobs;
  arr[2] = f->opt_userflags;
  arr[3] = f->opt_polarisation;
  arr[4] = f->opt_singleprec;
  arr[5] = (uint32_t)f->opt_universalpdgcode;
  arr[6] = f->particle_size;
  arr[7] = (f->opt_universalweight?1:0);
  MCPL_STATIC_ASSERT(sizeof(arr)==32);
  nb = fwrite(arr, 1, sizeof(arr), f->file);
  if (nb!=sizeof(arr))
    mcpl_error(errmsg);

  if (f->opt_universalweight) {
    MCPL_STATIC_ASSERT(sizeof(f->opt_universalweight)==8);
    nb = fwrite((void*)(&(f->opt_universalweight)), 1, sizeof(f->opt_universalweight), f->file);
    if (nb!=sizeof(f->opt_universalweight))
      mcpl_error(errmsg);
  }

  //src progname:
  mcpl_write_string(f->file,f->hdr_srcprogname?f->hdr_srcprogname:"unknown",errmsg);

  //Write comments and record positions of any stat:sum: entries:

  //First just count and allocate memory structure for stat:sum: entries:
  for (uint32_t i = 0; i < f->ncomments; ++i) {
    char * c = f->comments[i];
    if ( MCPL_COMMENT_IS_STATSUM(c) )
      ++(f->nstatsuminfo);
  }

  if ( f->nstatsuminfo ) {
    f->statsuminfo = (mcpl_internal_statsuminfo_t *)
      mcpl_internal_calloc( f->nstatsuminfo,
                            sizeof(mcpl_internal_statsuminfo_t) );
  }

  //Now fill statsuminfo and write comment strings to file:
  uint32_t i;
  unsigned nstatsuminfo_written = 0;
  for (i = 0; i < f->ncomments; ++i) {
    if ( nstatsuminfo_written < f->nstatsuminfo
         && MCPL_COMMENT_IS_STATSUM(f->comments[i]) ) {
      mcpl_internal_statsum_t sc;
      mcpl_internal_statsum_parse_or_emit_err( f->comments[i], &sc );
      if ( !sc.key[0] )
        mcpl_error("logic error while writing stat:sum: comments to header");
      mcpl_internal_statsuminfo_t * statsuminfo
        = &f->statsuminfo[nstatsuminfo_written++];
      size_t lcomment = strlen(f->comments[i]);
      if ( lcomment > (size_t)(UINT32_MAX) )
        mcpl_error("logic error: unexpected large comment strlen");
      statsuminfo->writtenstrlen = (uint32_t)lcomment;
      statsuminfo->writtenpos = MCPL_FTELL( f->file );
      statsuminfo->value = sc.value;
      size_t nn = strlen(sc.key);
      if ( nn > MCPL_STATSUMBUF_MAXLENGTH )
        mcpl_error("stat:sum: key unexpected strlen");
      memcpy( statsuminfo->key, sc.key, nn );
    }
    mcpl_write_string(f->file,f->comments[i],errmsg);
  }

  //blob keys:
  for (i = 0; i < f->nblobs; ++i)
    mcpl_write_string(f->file,f->blobkeys[i],errmsg);

  //blobs:
  for (i = 0; i < f->nblobs; ++i)
    mcpl_write_buffer(f->file, f->bloblengths[i], f->blobs[i],errmsg);

  //Reduce the likelihood of partially written headers (not guaranteed to have
  //an effect, but can't hurt):
  fflush(f->file);

  //Free up acquired memory only needed for header writing:
  free(f->hdr_srcprogname);
  f->hdr_srcprogname = NULL;
  if (f->ncomments) {
    for (i = 0; i < f->ncomments; ++i)
      free(f->comments[i]);
    free(f->comments);
    f->comments = NULL;
    f->ncomments = 0;
  }
  if (f->nblobs) {
    for (i = 0; i < f->nblobs; ++i)
      free(f->blobkeys[i]);
    free(f->blobkeys);
    f->blobkeys = NULL;
    for (i = 0; i < f->nblobs; ++i)
      free(f->blobs[i]);
    free(f->blobs);
    f->blobs = NULL;
    free(f->bloblengths);
    f->bloblengths = NULL;
    f->nblobs = 0;
  }
  f->header_notwritten = 0;
}

MCPL_LOCAL void mcpl_unitvect_pack_adaptproj(const double* in, double* out) {

  //Precise packing of unit vector into 2 floats + 1 bit using the "Adaptive
  //Projection Packing" method (T. Kittelmann, 2017).
  //
  //The Adaptive Projection Packing method is a variant on the traditional projection
  //method where one would store (x,y,sign(z)) and upon unpacking recover the
  //magnitude of z with |z|=sqrt(1-x^2-y^2), a formula which suffers from
  //numerical precision issues when |z| is small. In this improved version, one
  //gets rid of the precision issues by always storing the components that are
  //smallest in magnitude (the last one must then have a magnitude in the
  //interval [1/sqrt(3),1] = [0.577,1.0] which is never small). This just leaves
  //the issue of being able to recognise the coordinate choices again upon
  //unpacking. Since all components are at most of unit magnitude, this is
  //achieved by storing 1/z rather than z and replacing either x or y as
  //needed (infinity when z=0). Thus, the packed data will contain:
  //
  //              ( 1/z,  y, sign(x) ) when |x|>|y|,|z|
  //              ( x,  1/z, sign(y) ) when |y|>|x|,|z|
  //              ( x,    y, sign(z) ) when |z|>|x|,|y|
  //
  //The unpacking code can determine which of the three scenarios is used to
  //encode a given piece of data by checking if the first or second field is
  //greater than unity.
  //
  //Note that the arrays "in" and "out" are both of dimension 3, however out[2]
  //will contain only binary information, in the form of the sign of the
  //component which was projected away (-1.0 or 1.0).
  const double absx = fabs(in[0]);
  const double absy = fabs(in[1]);
  if ( fabs(in[2]) < fmax(absx,absy) ) {
    const double invz = ( in[2] ? (1.0/in[2]) : INFINITY );
    if (absx>=absy) {
      //output (1/z,y,sign(x))
      out[0] = invz; out[1] = in[1]; out[2] = in[0];
    } else {
      //output (x,1/z,sign(y))
      out[0] = in[0]; out[1] = invz; out[2] = in[1];
    }
  } else {
    //output (x,y,sign(z))
    out[0] = in[0]; out[1] = in[1]; out[2] = in[2];
  }
  out[2] = copysign(1.0,out[2]);
}

MCPL_LOCAL void mcpl_unitvect_unpack_adaptproj( const double* in, double* out ) {

  //Unpacking for the "Adaptive Projection Packing" method (T. Kittelmann, 2017).
  //See mcpl_unitvect_pack_adaptproj for more information.
  //
  //Note that the arrays "in" and "out" are both of dimension 3, however in[2]
  //will contain only binary information, in the form of the sign of the
  //component which was projected away.

  assert(in[2]==1.0||in[2]==-1.0);
  if (fabs(in[0]) > 1.0) {
    //input is (1/z,y,sign(x))
    out[1] = in[1]; out[2] = 1.0 / in[0];
    out[0] = in[2] * sqrt( fmax( 0.0, 1.0 - ( in[1]*in[1] + out[2]*out[2] ) ) );
  } else if (fabs(in[1])>1.0) {
    //input is (x,1/z,sign(y))
    out[0] = in[0]; out[2] = 1.0 / in[1];
    out[1] = in[2] * sqrt( fmax ( 0.0, 1.0 - ( in[0]*in[0] + out[2]*out[2] ) ) );
  } else {
    //input is (x,y,sign(z))
    out[0] = in[0]; out[1] = in[1];
    out[2] = in[2] * sqrt( fmax( 0.0, 1.0 - ( in[0]*in[0] + in[1]*in[1] ) ) );
  }
}

MCPL_LOCAL void mcpl_unitvect_unpack_oct(const double* in, double* out) {

  //Octahedral packing inspired by http://jcgt.org/published/0003/02/01/
  //
  //and:
  //
  //Octahedron Environment Maps, T. Engelhardt & C. Dachsbacher, Conference:
  //Proceedings of the Vision, Modeling, and Visualization Conference 2008, VMV
  //2008, Konstanz, Germany, October 8-10, 2008
  //
  //Note: Octahedral packing was used for the MCPL-2 format, which we are no
  //longer writing, only reading. Thus, we only keep the unpacking function in
  //the code.

  //restore z-coord of octahedron:
  out[2] = 1.0 - fabs(in[0]) - fabs(in[1]);
  if (out[2]<0) {
    //lower hemisphere
    out[0] = ( 1.0 - fabs( in[1] ) ) * ( in[0] >= 0.0 ? 1.0 : -1.0 );
    out[1] = ( 1.0 - fabs( in[0] ) ) * ( in[1] >= 0.0 ? 1.0 : -1.0 );
  } else {
    //upper hemisphere
    out[0] = in[0];
    out[1] = in[1];
  }
  //project from octahedron to unit sphere:
  double n = 1.0 / sqrt(out[0]*out[0]+out[1]*out[1]+out[2]*out[2]);
  out[0] *= n; out[1] *= n; out[2] *= n;
}

MCPL_LOCAL void mcpl_internal_wr_float( char * buf, float v ) { memcpy( buf, &v, sizeof(v) ); }
MCPL_LOCAL void mcpl_internal_wr_double( char * buf, double v ) { memcpy( buf, &v, sizeof(v) ); }
MCPL_LOCAL void mcpl_internal_wr_int32( char * buf, int32_t v ) { memcpy( buf, &v, sizeof(v) ); }
MCPL_LOCAL void mcpl_internal_wr_uint32( char * buf, uint32_t v ) { memcpy( buf, &v, sizeof(v) ); }
MCPL_LOCAL float mcpl_internal_rd_float( const char * buf ) { float v; memcpy( &v, buf, sizeof(v) ); return v; }
MCPL_LOCAL double mcpl_internal_rd_double( const char * buf ) { double v; memcpy( &v, buf, sizeof(v) ); return v; }
MCPL_LOCAL int32_t mcpl_internal_rd_int32( const char * buf ) { int32_t v; memcpy( &v, buf, sizeof(v) ); return v; }
MCPL_LOCAL uint32_t mcpl_internal_rd_uint32( const char * buf ) { uint32_t v; memcpy( &v, buf, sizeof(v) ); return v; }

MCPL_LOCAL void mcpl_internal_serialise_particle_to_buffer( const mcpl_particle_t* particle,
                                                            mcpl_outfileinternal_t * f ) {

  //Serialise the provided particle into the particle_buffer of the output file
  //(according to the settings of the output file).

  double pack_ekindir[3];

  //Sanity check (add more??):
  double dirsq = particle->direction[0] * particle->direction[0]
    + particle->direction[1] * particle->direction[1]
    + particle->direction[2] * particle->direction[2];
  if (fabs(dirsq-1.0)>1.0e-5)
    mcpl_error("attempting to add particle with non-unit direction vector");
  if (particle->ekin<0.0)
    mcpl_error("attempting to add particle with negative kinetic energy");
  //direction and ekin are packed into 3 doubles:
  mcpl_unitvect_pack_adaptproj(particle->direction,pack_ekindir);
  //pack_ekindir[2] is now just a sign(1.0 or -1.0), so we can store the
  //ekin in that field as well (since it must be non-negative). We use copysign
  //to be sure the signbit is set also if ekin=0:
  pack_ekindir[2] = copysign(particle->ekin,pack_ekindir[2]);

  //serialise particle object to buffer:
  unsigned ibuf = 0;
  char * pbuf = &(f->particle_buffer[0]);
  int i;
  if (f->opt_singleprec) {
    if (f->opt_polarisation) {
      for (i=0;i<3;++i) {
        mcpl_internal_wr_float( &pbuf[ibuf], (float)particle->polarisation[i] );
        ibuf += sizeof(float);
      }
    }
    for (i=0;i<3;++i) {
      mcpl_internal_wr_float( &pbuf[ibuf], (float)particle->position[i] );
      ibuf += sizeof(float);
    }
    for (i=0;i<3;++i) {
      mcpl_internal_wr_float( &pbuf[ibuf], (float)pack_ekindir[i] );
      ibuf += sizeof(float);
    }
    mcpl_internal_wr_float( &pbuf[ibuf], (float)particle->time );
    ibuf += sizeof(float);
    if (!f->opt_universalweight) {
      mcpl_internal_wr_float( &pbuf[ibuf], (float)particle->weight );
      ibuf += sizeof(float);
    }
  } else {
    if (f->opt_polarisation) {
      for (i=0;i<3;++i) {
        mcpl_internal_wr_double( &pbuf[ibuf], particle->polarisation[i] );
        ibuf += sizeof(double);
      }
    }
    for (i=0;i<3;++i) {
      mcpl_internal_wr_double( &pbuf[ibuf], particle->position[i] );
      ibuf += sizeof(double);
    }
    for (i=0;i<3;++i) {
      mcpl_internal_wr_double( &pbuf[ibuf], pack_ekindir[i] );
      ibuf += sizeof(double);
    }
    mcpl_internal_wr_double( &pbuf[ibuf], particle->time );
    ibuf += sizeof(double);
    if (!f->opt_universalweight) {
      mcpl_internal_wr_double( &pbuf[ibuf], particle->weight );
      ibuf += sizeof(double);
    }
  }
  if (!f->opt_universalpdgcode) {
    mcpl_internal_wr_int32( &pbuf[ibuf], particle->pdgcode );
    ibuf += sizeof(int32_t);
  }
  if (f->opt_userflags) {
    mcpl_internal_wr_uint32( &pbuf[ibuf], particle->userflags );
#ifndef NDEBUG
    ibuf += sizeof(uint32_t);
#endif
  }
  assert(ibuf==f->particle_size);
}

MCPL_LOCAL void mcpl_internal_write_particle_buffer_to_file(mcpl_outfileinternal_t * f ) {
  //Ensure header is written:
  if (f->header_notwritten)
    mcpl_write_header(f);

  //Increment nparticles and write buffer to file:
  f->nparticles += 1;
  size_t nb;
  nb = fwrite(&(f->particle_buffer[0]), 1, f->particle_size, f->file);
  if (nb!=f->particle_size)
    mcpl_error("Errors encountered while attempting to write particle data.");
}

void mcpl_add_particle(mcpl_outfile_t of,const mcpl_particle_t* particle)
{
  MCPLIMP_OUTFILEDECODE;
  mcpl_internal_serialise_particle_to_buffer(particle,f);
  mcpl_internal_write_particle_buffer_to_file(f);
}

MCPL_LOCAL void mcpl_update_nparticles(FILE* f, uint64_t n)
{
  //Seek and update nparticles at correct location in header:
  const char * errmsg = ( "Errors encountered while attempting "
                          "to update number of particles in file." );
  int64_t savedpos = MCPL_FTELL(f);
  if (savedpos<0)
    mcpl_error(errmsg);
  if (MCPL_FSEEK( f, MCPLIMP_NPARTICLES_POS ))
    mcpl_error(errmsg);
  size_t nb = fwrite(&n, 1, sizeof(n), f);
  if (nb != sizeof(n))
    mcpl_error(errmsg);
  if (MCPL_FSEEK( f, savedpos ))
    mcpl_error(errmsg);
}

mcpl_particle_t* mcpl_get_empty_particle(mcpl_outfile_t of)
{
  MCPLIMP_OUTFILEDECODE;
  if (f->puser) {
    //Calling more than once. This could be innocent, or it could indicate
    //problems in multi-threaded user-code. Better disallow and give an error:
    mcpl_error("mcpl_get_empty_particle must not be"
               " called more than once per output file");
  } else {
    f->puser = (mcpl_particle_t*)mcpl_internal_calloc(1,sizeof(mcpl_particle_t));
  }
  return f->puser;
}

void mcpl_close_outfile(mcpl_outfile_t of)
{
  MCPLIMP_OUTFILEDECODE;
  if (f->header_notwritten)
    mcpl_write_header(f);
  if (f->nparticles)
    mcpl_update_nparticles(f->file,f->nparticles);
  mcpl_internal_cleanup_outfile(f);
}

void mcpl_transfer_metadata(mcpl_file_t source, mcpl_outfile_t target)
{
  //Note that MCPL format version 2 and 3 have the same meta-data in the header,
  //except of course the version number itself.

  if (mcpl_hdr_little_endian(source) != mcpl_platform_is_little_endian())
    mcpl_error("mcpl_transfer_metadata can only work on files with same endianness as current platform.");

  mcpl_hdr_set_srcname(target,mcpl_hdr_srcname(source));
  unsigned i;
  for (i = 0; i < mcpl_hdr_ncomments(source); ++i)
    mcpl_hdr_add_comment(target,mcpl_hdr_comment(source,i));
  const char** blobkeys = mcpl_hdr_blobkeys(source);
  if (blobkeys) {
    int nblobs = mcpl_hdr_nblobs(source);
    uint32_t ldata;
    const char * data;
    int ii;
    for (ii = 0; ii < nblobs; ++ii) {
      int res = mcpl_hdr_blob(source,blobkeys[ii],&ldata,&data);
      if (!res)
        mcpl_error("unexpected key problem in mcpl_transfer_metadata");
      (void)res;
      mcpl_hdr_add_data(target, blobkeys[ii], ldata, data);
    }
  }
  if (mcpl_hdr_has_userflags(source))
    mcpl_enable_userflags(target);
  if (mcpl_hdr_has_polarisation(source))
    mcpl_enable_polarisation(target);
  if (mcpl_hdr_has_doubleprec(source))
    mcpl_enable_doubleprec(target);
  int32_t updg = mcpl_hdr_universal_pdgcode(source);
  if (updg)
    mcpl_enable_universal_pdgcode(target,updg);
  double uw = mcpl_hdr_universal_weight(source);
  if (uw)
    mcpl_enable_universal_weight(target,uw);
}

int mcpl_closeandgzip_outfile_rc(mcpl_outfile_t of)
{
  mcpl_print("MCPL WARNING: Usage of function mcpl_closeandgzip_outfile_rc is obsolete as"
             " mcpl_closeandgzip_outfile now also returns the status. Please update your code"
             " to use mcpl_closeandgzip_outfile instead.\n");
  return mcpl_closeandgzip_outfile(of);
}

int mcpl_closeandgzip_outfile(mcpl_outfile_t of)
{
  MCPLIMP_OUTFILEDECODE;
  char * filename = f->filename;
  f->filename = NULL;//prevent free in mcpl_close_outfile
  mcpl_close_outfile(of);
  int rc = mcpl_gzip_file(filename);
  free(filename);
  return rc;
}

typedef struct {
  FILE * file;
  gzFile filegz;
  char * hdr_srcprogname;
  unsigned format_version;
  int opt_userflags;
  int opt_polarisation;
  int opt_singleprec;
  int32_t opt_universalpdgcode;
  double opt_universalweight;
  int is_little_endian;
  uint64_t nparticles;
  uint32_t ncomments;
  char ** comments;
  uint32_t nblobs;
  char ** blobkeys;
  uint32_t * bloblengths;
  char ** blobs;
  unsigned particle_size;
  uint64_t first_particle_pos;
  uint64_t current_particle_idx;
  mcpl_particle_t* particle;
  unsigned opt_signature;
  char particle_buffer[MCPLIMP_MAX_PARTICLE_SIZE];
  uint64_t first_comment_pos;
  uint32_t * repaired_statsum_icomments;
} mcpl_fileinternal_t;

#define MCPLIMP_FILEDECODE mcpl_fileinternal_t * f = (mcpl_fileinternal_t *)ff.internal; assert(f)

MCPL_LOCAL uint64_t mcpl_read_buffer(mcpl_fileinternal_t* f, unsigned* n, char ** buf, const char * errmsg)
{
  //Reads buffer and returns number of bytes consumed from file
  size_t nb;
  if (f->filegz)
    nb = gzread(f->filegz, n, sizeof(*n));
  else
    nb = fread(n, 1, sizeof(*n), f->file);
  if (nb!=sizeof(*n))
    mcpl_error(errmsg);
  *buf = mcpl_internal_calloc(*n,1);
  if (f->filegz)
    nb = gzread(f->filegz, *buf, *n);
  else
    nb = fread(*buf, 1, *n, f->file);
  if (nb!=*n)
    mcpl_error(errmsg);
  return sizeof(*n) + *n;
}

MCPL_LOCAL uint64_t mcpl_read_string(mcpl_fileinternal_t* f, char ** dest, const char* errmsg)
{
  //Reads string and returns number of bytes consumed from file
  size_t nb;
  uint32_t n;
  if (f->filegz)
    nb = gzread(f->filegz, &n, sizeof(n));
  else
    nb = fread(&n, 1, sizeof(n), f->file);
  if (nb!=sizeof(n))
    mcpl_error(errmsg);
  char * s = mcpl_internal_calloc(n+1,1);
  if (f->filegz)
    nb = gzread(f->filegz, s, n);
  else
    nb = fread(s, 1, n, f->file);
  if (nb!=n)
    mcpl_error(errmsg);
  s[n] = '\0';
  *dest = s;
  if ( strlen(s) != n )
    mcpl_error("encountered unexpected null-byte in string read from file");
  return sizeof(n) + n;
}

MCPL_LOCAL gzFile mcpl_gzopen( const char * filename, const char * mode )
{
  mcu8str f = mcu8str_view_cstr( filename );
#ifdef _WIN32
  wchar_t* wpath = mctools_path2wpath(&f);//must free(..) return value.
  gzFile res = gzopen_w(wpath,mode);
  free(wpath);
#else
  mcu8str rp = mctools_real_path( &f );
  const char * use_fn = ( rp.c_str && rp.size > 0 ) ? rp.c_str : filename ;
#  ifdef Z_LARGE64
  gzFile res = gzopen64( use_fn, mode );
#  else
  gzFile res = gzopen( use_fn, mode );
#  endif
  mcu8str_dealloc( &rp );
#endif
  return res;
}

MCPL_LOCAL int mcpl_gzseek( gzFile fh, int64_t pos )
{
  //Invokes gzseek in SEEK_SET mode and returns 1 on success, 0 on failure.
  MCPL_STATIC_ASSERT(sizeof(int)>=sizeof(int32_t));
#ifdef _WIN32
  MCPL_STATIC_ASSERT(sizeof(z_off_t)>=sizeof(int32_t));
  //Windows. Here z_off_t is always signed, and most(all?) zlib builds are
  //WITHOUT 64bit support. We assume here for simplicity that it is actually 32
  //or 64 bit (this is likely always the case).
  MCPL_STATIC_ASSERT(sizeof(z_off_t)==sizeof(int32_t)||sizeof(z_off_t)==sizeof(int64_t));
  const int64_t seekmax = ( sizeof(z_off_t)>=sizeof(int64_t)
                            ? INT64_MAX : INT32_MAX ) - 1;//-1 is just safety
  if ( pos >= seekmax ) {
    // We could just throw an error:
    //
    // mcpl_error("Can not seek to positions in gzipped files beyond the"
    //            " 2GB limit with the current zlib build.");
    //
    // But instead we emulate by first seeking to seekmax, then uncompressing
    // and reading off the bytes one chunk at a time with gzread. In practice
    // this actually seems to be not much slower than a pure gzseek.
    if ( gzseek( fh, (z_off_t)seekmax, SEEK_SET ) != (z_off_t)seekmax )
      return 0;
    int64_t current = seekmax;
    char buf[65536];
    while (1) {
      int64_t missing = pos-current;
      if (!missing)
        break;
      int to_read = ( missing > (int64_t)sizeof(buf)
                      ? (int)sizeof(buf) : (int)missing );
      int nread = gzread( fh, buf, (unsigned)to_read );
      if ( nread != to_read )
        return 0;
      current += nread;
    }
    return 1;
  } else {
    return ( gzseek( fh, (z_off_t)pos, SEEK_SET ) == (z_off_t)pos ? 1 : 0 );
  }
#else
  //Until proven otherwise, we will simply demand that zlib on Unix has the
  //proper large file support.
  MCPL_STATIC_ASSERT(sizeof(z_off_t)==sizeof(int64_t));
  return ( gzseek( fh, pos, SEEK_SET ) == pos ? 1 : 0 );
#endif
}

MCPL_LOCAL void mcpl_internal_cleanup_file(mcpl_fileinternal_t * f)
{
  if (!f)
    return;
  if ( f->hdr_srcprogname ) {
    free(f->hdr_srcprogname);
    f->hdr_srcprogname = NULL;
  }
  if ( f->comments ) {
    uint32_t i;
    for (i = 0; i < f->ncomments; ++i) {
      if ( f->comments[i] ) {
        free(f->comments[i]);
        f->comments[i] = NULL;
      }
    }
    free(f->comments);
    f->comments = NULL;
  }
  if ( f->blobkeys ) {
    for ( uint32_t i = 0; i < f->nblobs; ++i ) {
      if ( f->blobkeys[i] ) {
        free(f->blobkeys[i]);
        f->blobkeys[i] = NULL;
      }
    }
    free(f->blobkeys);
    f->blobkeys = NULL;
  }
  if ( f->blobs ) {
    for ( uint32_t i = 0; i < f->nblobs; ++i ) {
      if ( f->blobs[i] ) {
        free(f->blobs[i]);
        f->blobs[i] = NULL;
      }
    }
    free(f->blobs);
    f->blobs = NULL;
  }
  if ( f->bloblengths ) {
    free(f->bloblengths);
    f->bloblengths = NULL;
  }
  if ( f->repaired_statsum_icomments ) {
    free( f->repaired_statsum_icomments );
    f->repaired_statsum_icomments = NULL;
  }
  if ( f->particle ) {
    free(f->particle);
    f->particle = NULL;
  }
  if (f->filegz) {
    gzclose(f->filegz);
    f->filegz = NULL;
  }
  if (f->file) {
    fclose(f->file);
    f->file = NULL;
  }
  free(f);
}

MCPL_LOCAL mcpl_file_t mcpl_actual_open_file(const char * filename, int * repair_status)
{
  int caller_is_mcpl_repair = *repair_status;
  *repair_status = 0;//file not broken

  if (!filename)
    mcpl_error("mcpl_open_file called with null string");

  mcpl_platform_compatibility_check();

  mcpl_file_t out;
  out.internal = NULL;

  mcpl_fileinternal_t * f
    = (mcpl_fileinternal_t*)mcpl_internal_calloc(1,sizeof(mcpl_fileinternal_t));

  //open file (with gzopen if filename ends with .gz):
  f->file = NULL;
  f->filegz = NULL;
  const char * lastdot = strrchr(filename, '.');
  if (lastdot && strcmp(lastdot, ".gz") == 0) {
    f->filegz = mcpl_gzopen( filename, "rb" );
    if (!f->filegz) {
      mcpl_internal_cleanup_file(f);
      mcpl_error("Unable to open file!");
    }
  } else {
    f->file = mcpl_internal_fopen(filename,"rb");
    if (!f->file) {
      mcpl_internal_cleanup_file(f);
      mcpl_error("Unable to open file!");
    }
  }

  //First read and check magic word, format version and endianness.
  unsigned char start[8];// = {'M','C','P','L','0','0','0','L'};
  size_t nb;
  if (f->filegz)
    nb = gzread(f->filegz, start, sizeof(start));
  else
    nb = fread(start, 1, sizeof(start), f->file);
  if (nb>=4&&(start[0]!='M'||start[1]!='C'||start[2]!='P'||start[3]!='L'))
    mcpl_error("File is not an MCPL file!");
  if (nb!=sizeof(start))
    mcpl_error("Error while reading first bytes of file!");
  f->format_version = (start[4]-'0')*100 + (start[5]-'0')*10 + (start[6]-'0');
  if (f->format_version!=2&&f->format_version!=3)
    mcpl_error("File is in an unsupported MCPL version!");
  f->is_little_endian = mcpl_platform_is_little_endian();
  if (start[7]!=(f->is_little_endian?'L':'B')) {
    if (start[7]=='L'||start[7]=='B')
      mcpl_error("Endian-ness of current platform is different than the one used to write the file.");
    else
      mcpl_error("Unexpected value in endianness field!");
  }
  int64_t current_pos = sizeof(start);

  //proceed reading header, knowing we have a consistent version and endian-ness.
  const char * errmsg = "Errors encountered while attempting to read header";

  uint64_t numpart;
  if (f->filegz)
    nb = gzread(f->filegz, &numpart, sizeof(numpart));
  else
    nb = fread(&numpart, 1, sizeof(numpart), f->file);
  if (nb!=sizeof(numpart))
    mcpl_error(errmsg);
  current_pos += nb;
  f->nparticles = numpart;

  uint32_t arr[8];
  MCPL_STATIC_ASSERT(sizeof(arr)==32);
  if (f->filegz)
    nb = gzread(f->filegz, arr, sizeof(arr));
  else
    nb=fread(arr, 1, sizeof(arr), f->file);
  if (nb!=sizeof(arr))
    mcpl_error(errmsg);
  current_pos += nb;

  f->ncomments = arr[0];
  f->nblobs = arr[1];
  f->opt_userflags = arr[2];
  f->opt_polarisation = arr[3];
  f->opt_singleprec = arr[4];
  memcpy(&f->opt_universalpdgcode, &arr[5], sizeof(int32_t));
  f->particle_size = arr[6];//We could check consistency here with the calculated value.
  if ( ! (f->particle_size<=MCPLIMP_MAX_PARTICLE_SIZE) )
    mcpl_error("unexpected particle size");

  if (arr[7]) {
    //file has universal weight
    if (f->filegz)
      nb = gzread(f->filegz, (void*)&(f->opt_universalweight), sizeof(f->opt_universalweight));
    else
      nb=fread((void*)&(f->opt_universalweight), 1, sizeof(f->opt_universalweight), f->file);
    if (nb!=sizeof(f->opt_universalweight))
      mcpl_error(errmsg);
    current_pos += nb;
  }

  f->opt_signature = 0
    + 1 * f->opt_singleprec
    + 2 * f->opt_polarisation
    + 4 * (f->opt_universalpdgcode?1:0)
    + 8 * (f->opt_universalweight?1:0)
    + 16 * f->opt_userflags;

  //Then some strings:
  current_pos += mcpl_read_string(f,&f->hdr_srcprogname,errmsg);
  f->comments = ( f->ncomments
                  ? (char **)mcpl_internal_calloc(f->ncomments,sizeof(char*))
                  : NULL );
  f->first_comment_pos = current_pos;

  //Validate stat: entries to get error on load rather than later on use:
  int unknown_stat_syntax = 0;
  uint32_t n_statsum_comments = 0;
  for (uint32_t i = 0; i < f->ncomments; ++i) {
    current_pos += mcpl_read_string(f,&(f->comments[i]),errmsg);
    if ( strncmp( f->comments[i], "stat:", 5 ) != 0 )
      continue;
    if ( MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
      ++n_statsum_comments;
    else
      unknown_stat_syntax = 1;
  }
  if ( n_statsum_comments ) {
    //Check for correct syntax as well as duplicate keys. We reuse
    //mcpl_internal_statsum_t although we will only use the key field.
    mcpl_internal_statsum_t * ssi_buf
      = (mcpl_internal_statsum_t*)
      mcpl_internal_calloc( n_statsum_comments,
                            sizeof(mcpl_internal_statsum_t) );
    mcpl_internal_statsum_t * ssi_buf_next = ssi_buf;
    for (uint32_t i = 0; i < f->ncomments; ++i) {
      if ( !MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
        continue;
      mcpl_internal_statsum_parse_or_emit_err( f->comments[i], ssi_buf_next );
      for ( mcpl_internal_statsum_t * it = ssi_buf;
            it < ssi_buf_next; ++it ) {
        if ( strcmp( it->key, ssi_buf_next->key ) == 0 ) {
          //emit error!
          char buf[MCPL_STATSUMKEY_MAXLENGTH+256];
          snprintf(buf,sizeof(buf),
                   "Duplicate stat:sum: key. The key \"%s\" appears"
                   " more than once in the file.",it->key);
          free(ssi_buf);
          mcpl_error(buf);
        }
      }
      ++ssi_buf_next;
    }
    free(ssi_buf);
  }
  if (unknown_stat_syntax) {
    mcpl_print("MCPL WARNING: Opened file with unknown \"stat:...\" syntax in"
               " comments. The present installation only has special support"
               " for \"stat:sum:...\" comments. It might be a sign that your"
               " installation of MCPL is too old.\n");
  }

  f->blobkeys = NULL;
  f->bloblengths = NULL;
  f->blobs = NULL;
  if (f->nblobs) {
    f->blobs = (char **)mcpl_internal_calloc(f->nblobs,sizeof(char*));
    f->blobkeys = (char **)mcpl_internal_calloc(f->nblobs,sizeof(char*));
    f->bloblengths = (uint32_t *)mcpl_internal_calloc(f->nblobs,sizeof(uint32_t));
    for (uint32_t i =0; i < f->nblobs; ++i)
      current_pos += mcpl_read_string(f,&(f->blobkeys[i]),errmsg);
    for (uint32_t i =0; i < f->nblobs; ++i)
      current_pos += mcpl_read_buffer(f, &(f->bloblengths[i]), &(f->blobs[i]), errmsg);
  }
  f->particle = (mcpl_particle_t*)mcpl_internal_calloc(1,sizeof(mcpl_particle_t));

  //At first event now:
  f->current_particle_idx = 0;
  f->first_particle_pos = current_pos;
  f->repaired_statsum_icomments = NULL;

  if ( f->nparticles==0 || caller_is_mcpl_repair ) {
    //TODO: Perhaps the placeholder nparticles should be UINT64_MAX instead of
    //0, so we know that nparticles=0 is a properly closed file.

    //Although empty files are permitted, it is possible that the file was never
    //closed properly (maybe the writing program ended prematurely). Let us
    //check to possibly recover usage of the file. If caller is mcpl_repair, we
    //always check since the file might have been truncated after it was first
    //closed properly.
    if (f->filegz) {
      //SEEK_END is not supported by zlib, and there is no reliable way to get
      //the input size. Thus, all we can do is to uncompress the whole thing,
      //which we won't since it might stall operations for a long time. But we
      //can at least try to check whether the file is indeed empty or not, and
      //give an error in the latter case:
      if (f->nparticles==0) {
        char testbuf[4];
        nb = gzread(f->filegz, testbuf, sizeof(testbuf));
        if (nb>0) {
          if (caller_is_mcpl_repair) {
            *repair_status = 1;//file broken but can't recover since gzip.
          } else {
            mcpl_error("Input file appears to not have been closed properly"
                       " and data recovery is disabled for gzipped files.");
          }
        }
      } else {
        if (!caller_is_mcpl_repair)
          mcpl_error("logic error (!caller_is_mcpl_repair)");
        *repair_status = 2;//file brokenness can not be determined since gzip.
      }
      if (!mcpl_gzseek( f->filegz, f->first_particle_pos ) )
        mcpl_error("Unexpected issue skipping to start of empty gzipped file");
    } else {
      //SEEK_END is not guaranteed to always work, so we fail our recovery
      //attempt silently:
      if (f->file && !MCPL_FSEEK_END( f->file )) {
        int64_t endpos = MCPL_FTELL(f->file);
        if (endpos > (int64_t)f->first_particle_pos && (uint64_t)endpos != f->first_particle_pos) {
          uint64_t np = ( endpos - f->first_particle_pos ) / f->particle_size;
          if ( f->nparticles != np ) {
            if ( f->nparticles > 0 && np > f->nparticles ) {
              //should really not happen unless file was corrupted or file was
              //first closed properly and then something was appended to it.
              mcpl_error("Input file has invalid combination of meta-data & filesize.");
            }
            if (caller_is_mcpl_repair) {
              *repair_status = 3;//file broken and should be able to repair
            } else {
              if (f->nparticles!=0)
                mcpl_error("unexpected nparticles value");
              char buf[256];
              snprintf(buf,sizeof(buf),"MCPL WARNING: Input file appears to"
                       " not have been closed properly. Recovered %"
                       PRIu64 " particles.\n",np);
              mcpl_print(buf);
            }
            f->nparticles = np;
            //If we have any stat:sum: entries, their values will be
            //untrustworthy, so we mark them as unavailable.
            for (uint32_t i = 0; i < f->ncomments; ++i) {
              if (!MCPL_COMMENT_IS_STATSUM(f->comments[i]))
                continue;
              mcpl_internal_statsum_t sc;
              mcpl_internal_statsum_parse_or_emit_err( f->comments[i], &sc );
              if ( sc.value == -1.0 )
                continue;//already marked as not available
              char buf[256+MCPL_STATSUMKEY_MAXLENGTH];
              snprintf(buf,sizeof(buf),
                       "MCPL WARNING: Marking stat:sum:%s entry as not avail"
                       "able (-1) since file not closed properly.\n",sc.key);
              mcpl_print(buf);

              if ( caller_is_mcpl_repair ) {
                //record indices of statsum comments that must be repaired
                //also on-disk later.
                if (!f->repaired_statsum_icomments) {
                  //allocate array. First entry will be the size.
                  f->repaired_statsum_icomments
                    = (uint32_t *)mcpl_internal_calloc(f->ncomments+1,
                                                       sizeof(uint32_t));
                  f->repaired_statsum_icomments[0] = 0;
                }
                uint32_t ir = ((f->repaired_statsum_icomments[0])++) + 1;
                f->repaired_statsum_icomments[ir] = i;
              }
              char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
              mcpl_internal_encodestatsum( sc.key, -1.0, new_comment );
              size_t nn = strlen(f->comments[i]);
              if ( nn != strlen(new_comment) )
                mcpl_error("inconsistent length of stat:sum: comment");
              memcpy(f->comments[i],new_comment,nn);
            }
          }
        }
      }
      MCPL_FSEEK( f->file, f->first_particle_pos );//if this fseek failed, it
                                                   //might just be that we are
                                                   //at EOF with no particles.
    }
  }

  out.internal = f;
  return out;
}

mcpl_file_t mcpl_open_file(const char * filename)
{
  int repair_status = 0;
  return mcpl_actual_open_file(filename,&repair_status);
}

MCPL_LOCAL void mcpl_internal_updatestatsum( FILE * f,
                                             mcpl_internal_statsuminfo_t*sc,
                                             const char * new_comment )
{
  //Seek and update comment at correct location in header.

  const char * errmsg = ( "Errors encountered while attempting "
                          "to update stat:sum: header in file." );
  if (!f||!sc||!new_comment)
    mcpl_error(errmsg);

  uint32_t n = sc->writtenstrlen;
  if ( n != strlen(new_comment) )
    mcpl_error("preallocated space for stat:sum: update does not fit (2)");

  int64_t savedpos = MCPL_FTELL(f);
  if (savedpos<0)
    mcpl_error(errmsg);
  uint64_t updatepos = sc->writtenpos;
  updatepos += sizeof(uint32_t);//skip strlen data (no, we can't read it since
                                //the file is in output mode)
  if (MCPL_FSEEK( f, updatepos ))
    mcpl_error(errmsg);
  size_t nb = fwrite( new_comment, 1, n, f);
  if ( nb != n )
    mcpl_error(errmsg);
  if (MCPL_FSEEK( f, savedpos ))
    mcpl_error(errmsg);

}

void mcpl_repair(const char * filename)
{
  int repair_status = 1;
  mcpl_file_t f = mcpl_actual_open_file(filename,&repair_status);
  uint64_t nparticles = mcpl_hdr_nparticles(f);
  mcpl_fileinternal_t * fi = (mcpl_fileinternal_t *)f.internal;

  //Collect information about any stat:sum: entries that we must modify during
  //the repair (i.e. we must mark then as unavailable by setting them to -1).
  mcpl_internal_statsuminfo_t * ssi = NULL;
  uint32_t nssi_to_repair = 0;
  if ( fi->repaired_statsum_icomments ) {
    nssi_to_repair = fi->repaired_statsum_icomments[0];
    ssi = (mcpl_internal_statsuminfo_t *)
      mcpl_internal_calloc( nssi_to_repair,
                            sizeof(mcpl_internal_statsuminfo_t) );
    uint32_t nssi_repair_check = 0;
    uint64_t next_comment_pos = fi->first_comment_pos;
    uint32_t* icmt_next_to_repair = &fi->repaired_statsum_icomments[1];
    for (uint32_t i = 0; i < fi->ncomments; ++i) {
      const char * comment = fi->comments[i];
      size_t lcomment = strlen(comment);
      uint64_t writtenpos = next_comment_pos;
      next_comment_pos += ( lcomment + sizeof(uint32_t) );
      if ( i == *icmt_next_to_repair ) {
        ++icmt_next_to_repair;
        mcpl_internal_statsum_t sc;
        mcpl_internal_statsum_parse_or_emit_err( comment, &sc );
        if ( !(sc.value==-1.0) ) {
          //value should already have been repaired to be -1 in the in-mem
          //comment string.
          mcpl_error("unexpected stat:sum value in file");
        }
        mcpl_internal_statsuminfo_t * s = &ssi[nssi_repair_check++];
        memcpy( s->key, sc.key, strlen(sc.key) + 1 );
        if ( lcomment > (size_t)(UINT32_MAX) )
          mcpl_error("logic error: unexpected large stat:sum comment strlen");
        s->writtenstrlen = (uint32_t)lcomment;
        s->writtenpos = writtenpos;
      }
    }
    if ( nssi_to_repair != nssi_repair_check )
      mcpl_error("logic error during stat:sum repair");
  }

  mcpl_close_file(f);
  fi = NULL;

  if (repair_status==0) {
    free(ssi);
    mcpl_error("File does not appear to be broken.");
  } else if (repair_status==1) {
    free(ssi);
    mcpl_error("Input file is indeed broken, but must be gunzipped before it can be repaired.");
  } else if (repair_status==2) {
    free(ssi);
    mcpl_error("File must be gunzipped before it can be checked and possibly repaired.");
  }

  //Ok, we should repair the file by updating nparticles in the header, and also
  //possibly by setting any stat:sum comment entries to the value -1 since they
  //are not trustworthy. We update nparticles last, since after that the file
  //will appear as already having been repaired:

  FILE * fh = mcpl_internal_fopen(filename,"r+b");
  if (!fh)
    mcpl_error("Unable to open file in update mode!");

  if ( ssi ) {
    for ( uint32_t i = 0; i < nssi_to_repair; ++i ) {
      char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
      mcpl_internal_encodestatsum( ssi[i].key, -1.0, new_comment );
      mcpl_internal_updatestatsum( fh, &ssi[i], new_comment );
      ssi[i].value = -1.0;
    }
    free(ssi);
  }

  mcpl_update_nparticles(fh, nparticles);
  fclose(fh);
  //Verify that we fixed it:
  repair_status = 1;
  f = mcpl_actual_open_file( filename, &repair_status );
  uint64_t nparticles2 = mcpl_hdr_nparticles(f);
  mcpl_close_file(f);
  if ( repair_status == 0 && nparticles == nparticles2 ) {
    char buf[256];
    snprintf(buf,sizeof(buf),"MCPL: Successfully repaired file with %"
             PRIu64 " particles.\n",nparticles);
    mcpl_print(buf);
  } else {
    mcpl_error("Something went wrong while attempting to repair file.");
  }
}

void mcpl_close_file(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  mcpl_internal_cleanup_file(f);
}

unsigned mcpl_hdr_version(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->format_version;
}

uint64_t mcpl_hdr_nparticles(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->nparticles;
}

unsigned mcpl_hdr_ncomments(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->ncomments;
}

const char * mcpl_hdr_comment(mcpl_file_t ff, unsigned i)
{
  MCPLIMP_FILEDECODE;
  if (i>=f->ncomments)
    mcpl_error("Invalid comment requested (index out of bounds)");
  return f->comments[i];
}

int mcpl_hdr_nblobs(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->nblobs;
}

const char** mcpl_hdr_blobkeys(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return (const char**)f->blobkeys;
}

int mcpl_hdr_blob(mcpl_file_t ff, const char* key,
                  uint32_t* ldata, const char ** data)
{
  MCPLIMP_FILEDECODE;
  uint32_t i;
  for (i = 0; i < f->nblobs; ++i) {
    if (strcmp(f->blobkeys[i],key)==0) {
      *data = f->blobs[i];
      *ldata = f->bloblengths[i];
      return 1;
    }
  }
  *data = NULL;
  *ldata = 0;
  return 0;
}

const char* mcpl_hdr_srcname(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->hdr_srcprogname;
}

int mcpl_hdr_has_userflags(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->opt_userflags;
}

int mcpl_hdr_has_polarisation(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->opt_polarisation;
}

int mcpl_hdr_has_doubleprec(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return !f->opt_singleprec;
}

const mcpl_particle_t* mcpl_read(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  f->current_particle_idx += 1;
  if ( f->current_particle_idx > f->nparticles ) {
    f->current_particle_idx = f->nparticles;//overflow guard
    return 0;
  }

  //read particle data:
  size_t nb;
  unsigned lbuf = f->particle_size;
  char * pbuf = &(f->particle_buffer[0]);
  if (f->filegz)
    nb = gzread(f->filegz, pbuf, lbuf);
  else
    nb = fread(pbuf, 1, lbuf, f->file);
  if (nb!=lbuf)
    mcpl_error("Errors encountered while attempting to read particle data.");

  //Transfer to particle struct:
  unsigned ibuf = 0;
  mcpl_particle_t * p = f->particle;
  double pack_ekindir[3];
  p->weight = f->opt_universalweight;
  int i;
  if (f->opt_singleprec) {
    if (f->opt_polarisation) {
      for (i=0;i<3;++i) {
        p->polarisation[i] = mcpl_internal_rd_float( &pbuf[ibuf] );
        ibuf += sizeof(float);
      }
    } else {
      for (i=0;i<3;++i)
        p->polarisation[i] = 0.0;
    }
    for (i=0;i<3;++i) {
      p->position[i] = mcpl_internal_rd_float( &pbuf[ibuf] );
      ibuf += sizeof(float);
    }
    for (i=0;i<3;++i) {
      pack_ekindir[i] = mcpl_internal_rd_float( &pbuf[ibuf] );
      ibuf += sizeof(float);
    }
    p->time = mcpl_internal_rd_float( &pbuf[ibuf] );
    ibuf += sizeof(float);
    if (!p->weight) {
      p->weight = mcpl_internal_rd_float( &pbuf[ibuf] );
      ibuf += sizeof(float);
    }
  } else {
    if (f->opt_polarisation) {
      for (i=0;i<3;++i) {
        p->polarisation[i] = mcpl_internal_rd_double( &pbuf[ibuf] );
        ibuf += sizeof(double);
      }
    } else {
      for (i=0;i<3;++i)
        p->polarisation[i] = 0.0;
    }
    for (i=0;i<3;++i) {
      p->position[i] = mcpl_internal_rd_double( &pbuf[ibuf] );
      ibuf += sizeof(double);
    }
    for (i=0;i<3;++i) {
      pack_ekindir[i] = mcpl_internal_rd_double( &pbuf[ibuf] );
      ibuf += sizeof(double);
    }
    p->time = mcpl_internal_rd_double( &pbuf[ibuf] );
    ibuf += sizeof(double);
    if (!p->weight) {
      p->weight = mcpl_internal_rd_double( &pbuf[ibuf] );
      ibuf += sizeof(double);
    }
  }

  if (f->opt_universalpdgcode) {
    p->pdgcode = f->opt_universalpdgcode;
  } else {
    p->pdgcode = mcpl_internal_rd_int32( &pbuf[ibuf] );
    ibuf += sizeof(int32_t);
  }
  if (f->opt_userflags) {
    p->userflags = mcpl_internal_rd_uint32( &pbuf[ibuf] );
#ifndef NDEBUG
    ibuf += sizeof(uint32_t);
#endif
  } else {
    f->opt_userflags = 0;
  }
  assert(ibuf==lbuf);

  //Unpack direction and ekin:

  if (f->format_version>=3) {
    p->ekin = fabs(pack_ekindir[2]);
    pack_ekindir[2] = copysign(1.0,pack_ekindir[2]);
    mcpl_unitvect_unpack_adaptproj(pack_ekindir,p->direction);
  } else {
    assert(f->format_version==2);
    mcpl_unitvect_unpack_oct(pack_ekindir,p->direction);
    p->ekin = pack_ekindir[2];
    if (signbit(pack_ekindir[2])) {
      p->ekin = -p->ekin;
      p->direction[2] = 0.0;
    }
  }
  return p;
}

int mcpl_skipforward(mcpl_file_t ff,uint64_t n)
{
  MCPLIMP_FILEDECODE;
  //increment, but guard against overflows:
  if ( n >= f->nparticles || f->current_particle_idx >= f->nparticles )
    f->current_particle_idx = f->nparticles;
  else
    f->current_particle_idx += n;
  if ( f->current_particle_idx > f->nparticles )
    f->current_particle_idx = f->nparticles;

  int notEOF = f->current_particle_idx<f->nparticles;
  if (n==0)
    return notEOF;
  if (notEOF) {
    int error;
    if (f->filegz) {
      int64_t targetpos = f->current_particle_idx*f->particle_size+f->first_particle_pos;
      error = ! mcpl_gzseek(f->filegz, targetpos );
    } else {
      error = MCPL_FSEEK_CUR( f->file, f->particle_size * n )!=0;
    }
    if (error)
      mcpl_error("Errors encountered while skipping in particle list");
  }
  return notEOF;
}

int mcpl_rewind(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  int already_there = (f->current_particle_idx==0);
  f->current_particle_idx = 0;
  int notEOF = f->current_particle_idx<f->nparticles;
  if (notEOF&&!already_there) {
    int error;
    if (f->filegz) {
      error = ! mcpl_gzseek( f->filegz, f->first_particle_pos );
    } else {
      error = MCPL_FSEEK( f->file, f->first_particle_pos )!=0;
    }
    if (error)
      mcpl_error("Errors encountered while rewinding particle list");
  }
  return notEOF;
}

int mcpl_seek(mcpl_file_t ff,uint64_t ipos)
{
  MCPLIMP_FILEDECODE;
  int already_there = (f->current_particle_idx==ipos);
  f->current_particle_idx = (ipos<f->nparticles?ipos:f->nparticles);
  int notEOF = f->current_particle_idx<f->nparticles;
  if (notEOF&&!already_there) {
    int error;
    if (f->filegz) {
      int64_t targetpos = f->current_particle_idx*f->particle_size+f->first_particle_pos;
      error = ! mcpl_gzseek( f->filegz, targetpos );
    } else {
      error = MCPL_FSEEK( f->file, f->first_particle_pos + f->particle_size * ipos )!=0;
    }
    if (error)
      mcpl_error("Errors encountered while seeking in particle list");
  }
  return notEOF;
}

uint64_t mcpl_currentposition(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->current_particle_idx;
}

char * mcpl_basename(const char * filename)
{
  mcu8str fn = mcu8str_view_cstr( filename );
  mcu8str bn = mctools_basename( &fn );
  char * res = mcpl_internal_malloc( bn.size + 1 );
  if ( bn.size == 0 || !bn.c_str ) {
    res[0] = '\0';
  } else {
    memcpy( res, bn.c_str, bn.size + 1 );
  }
  mcu8str_dealloc( &bn );
  return res;
}

int mcpl_hdr_particle_size(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->particle_size;
}

uint64_t mcpl_hdr_header_size(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->first_particle_pos;
}

int mcpl_hdr_universal_pdgcode(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->opt_universalpdgcode;
}

int mcpl_hdr_universel_pdgcode(mcpl_file_t ff)
{
  mcpl_print("MCPL WARNING: Usage of function mcpl_hdr_universel_pdgcode"
             " is obsolete as it has been renamed to"
             " mcpl_hdr_universal_pdgcode. Please update your code.\n");
  return mcpl_hdr_universal_pdgcode(ff);
}

double mcpl_hdr_universal_weight(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->opt_universalweight;
}

int mcpl_hdr_little_endian(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->is_little_endian;
}

void mcpl_transfer_last_read_particle(mcpl_file_t source, mcpl_outfile_t target)
{
  mcpl_outfileinternal_t * ft = (mcpl_outfileinternal_t *)target.internal;
  assert(ft);
  mcpl_fileinternal_t * fs = (mcpl_fileinternal_t *)source.internal;
  assert(fs);

  if ( fs->current_particle_idx==0 && fs->particle->weight==0.0 && fs->particle->pdgcode==0 ) {
    mcpl_error("mcpl_transfer_last_read_particle called with source file in invalid state"
               " (did you forget to first call mcpl_read() on the source file before calling this function?)");
    return;
  }

  //Sanity checks for universal fields here (but not in mcpl_add_particle since users are allowed to create files by setting just the universal fields):
  if ( ft->opt_universalpdgcode && fs->particle->pdgcode != ft->opt_universalpdgcode) {
    char buf[256];
    snprintf(buf,sizeof(buf),"mcpl_transfer_last_read_particle asked to"
             " transfer particle with pdgcode %li into a file with"
             " universal pdgcode of %li\n",
             (long)fs->particle->pdgcode,
             (long)ft->opt_universalpdgcode);
    mcpl_error(buf);
    return;
  }
  if ( ft->opt_universalweight && fs->particle->weight != ft->opt_universalweight) {
    char buf[256];
    snprintf(buf,sizeof(buf),"mcpl_transfer_last_read_particle asked to"
             " transfer particle with weight %g into a file with universal"
             " weight of %g\n",
             fs->particle->weight,
             ft->opt_universalweight );
    mcpl_error(buf);
    return;
  }
  //NB: We don't sanity check that polarisation/userflags are enabled if present
  //in the input particle, since it is a valid use-case to use this function to
  //discard such info.

  if ( fs->format_version == 2 || ( fs->opt_singleprec && !ft->opt_singleprec ) ) {
    //source file is in old format with different unit vector packing, or the
    //floating point precision is increasing. In these scenarious we can not
    //reuse the 3 floats representing packed direction+ekin but must proceed via
    //a full unpacking+repacking.
    mcpl_add_particle(target,fs->particle);
    return;
  }

  if ( ft->opt_signature == fs->opt_signature ) {
    //Particle data is encoded in exactly the same manner in src and target (a
    //common scenario for many merge or extraction scenarios) -> simply transfer
    //the bytes and be done with it:
    if ( fs->particle_size!=ft->particle_size )
      mcpl_error("unexpectedly inconsistent particle sizes");
    memcpy(ft->particle_buffer,fs->particle_buffer,fs->particle_size);
    mcpl_internal_write_particle_buffer_to_file(ft);
    return;
  }

  //The hard way - first serialise the source particle into the output buffer:
  mcpl_internal_serialise_particle_to_buffer( fs->particle, ft );

  //If possible, override the 3 FP representing packed ekin+dir from the packing
  //in the source, thus avoiding potentially lossy unpacking+packing:
  size_t fpsize_target = ft->opt_singleprec ? sizeof(float) : sizeof(double);
  size_t idx_packekindir_target = (ft->opt_polarisation ? 6 : 3) * fpsize_target;
  size_t idx_packekindir_src = (fs->opt_polarisation ? 6 : 3) * fpsize_target;
  if (fs->opt_singleprec == ft->opt_singleprec) {
    memcpy( &(ft->particle_buffer[idx_packekindir_target]),
            &(fs->particle_buffer[idx_packekindir_src]),
            fpsize_target * 3);
  } else if ( ft->opt_singleprec && !fs->opt_singleprec ) {
    //For the case of double precision -> single precision, we can simply
    //perform a narrowing conversion:
    double * packekindir_src = (double*)&(fs->particle_buffer[idx_packekindir_src]);
    float * packekindir_target = (float*)&(ft->particle_buffer[idx_packekindir_target]);
    for (unsigned i = 0; i < 3; ++i) {
      packekindir_target[i] = (float)packekindir_src[i];
    }
  }

  mcpl_internal_write_particle_buffer_to_file(ft);
}

void mcpl_dump_header(mcpl_file_t f)
{
  char buf[4096];
  mcpl_print("\n  Basic info\n");
  snprintf(buf,sizeof(buf),
           "    Format             : MCPL-%i\n",mcpl_hdr_version(f));
  mcpl_print(buf);
  snprintf(buf,sizeof(buf),
           "    No. of particles   : %" PRIu64 "\n",mcpl_hdr_nparticles(f) );
  mcpl_print(buf);
  snprintf(buf,sizeof(buf),
           "    Header storage     : %" PRIu64 " bytes\n",
           mcpl_hdr_header_size(f));
  mcpl_print(buf);
  snprintf(buf,sizeof(buf),
           "    Data storage       : %" PRIu64 " bytes\n",
           mcpl_hdr_nparticles(f)*mcpl_hdr_particle_size(f));
  mcpl_print(buf);
  mcpl_print("\n  Custom meta data\n");

  //srcname or comments might be too long for our static print buffer, so we use
  //a dynamic buffer if needed.
  unsigned ncomments = mcpl_hdr_ncomments(f);
  unsigned nblobs = mcpl_hdr_nblobs(f);
  const char** blobkeys = mcpl_hdr_blobkeys(f);
  size_t lmax = strlen(mcpl_hdr_srcname(f));
  {
    for (unsigned ic = 0; ic < ncomments; ++ic) {
      size_t lc = strlen(mcpl_hdr_comment(f,ic));
      if ( lc > lmax )
        lmax = lc;
    }
    for (uint32_t ib = 0; ib < nblobs; ++ib) {
      size_t lbk = strlen(blobkeys[ib]);
      if ( lbk > lmax )
        lmax = lbk;
    }
  }
  lmax += 128;//safe + other parts of the printed lines

  char * flexbuf = buf;
  size_t lflexbuf = sizeof(buf);
  if ( lmax > lflexbuf ) {
    lflexbuf = lmax;
    flexbuf = mcpl_internal_malloc( lflexbuf );
  }

  snprintf(flexbuf,lflexbuf,
           "    Source             : \"%s\"\n",mcpl_hdr_srcname(f));
  mcpl_print(flexbuf);
  snprintf(buf,sizeof(buf),
           "    Number of comments : %i\n",ncomments);
  mcpl_print(buf);
  unsigned ic;
  for (ic = 0; ic < ncomments; ++ic) {
    snprintf(flexbuf,lflexbuf,
             "          -> comment %i : \"%s\"\n",ic,mcpl_hdr_comment(f,ic));
    mcpl_print(flexbuf);
  }
  snprintf(buf,sizeof(buf),
           "    Number of blobs    : %i\n",nblobs);
  mcpl_print(buf);
  for (uint32_t ib = 0; ib < nblobs; ++ib) {
    const char * data;
    uint32_t ldata;
    int ok = mcpl_hdr_blob(f, blobkeys[ib], &ldata, &data);
    if (!ok) {
      if ( flexbuf != buf )
        free(flexbuf);
      mcpl_error("Unexpected blob access error");
    }
    snprintf(flexbuf,lflexbuf,
             "          -> %lu bytes of data with key \"%s\"\n",
             (unsigned long)ldata,blobkeys[ib]);
    mcpl_print(flexbuf);
  }

  if ( flexbuf != buf )
    free(flexbuf);

  mcpl_print("\n  Particle data format\n");
  snprintf(buf,sizeof(buf),
           "    User flags         : %s\n",
           (mcpl_hdr_has_userflags(f)?"yes":"no") );
  mcpl_print(buf);
  snprintf(buf,sizeof(buf),
           "    Polarisation info  : %s\n",
           (mcpl_hdr_has_polarisation(f)?"yes":"no"));
  mcpl_print(buf);
  mcpl_print("    Fixed part. type   : ");
  int32_t updg = mcpl_hdr_universal_pdgcode(f);
  if (updg) {
    snprintf(buf,sizeof(buf),"yes (pdgcode %li)\n",(long)updg);
    mcpl_print(buf);
  } else {
    mcpl_print("no\n");
  }
  mcpl_print("    Fixed part. weight : ");
  double uw = mcpl_hdr_universal_weight(f);
  if (uw) {
    snprintf(buf,sizeof(buf),"yes (weight %g)\n",uw);
    mcpl_print(buf);
  } else {
    mcpl_print("no\n");
  }
  snprintf(buf,sizeof(buf),
           "    FP precision       : %s\n",
           (mcpl_hdr_has_doubleprec(f)?"double":"single"));
  mcpl_print(buf);
  snprintf(buf,sizeof(buf),
           "    Endianness         : %s\n",
           (mcpl_hdr_little_endian(f)?"little":"big"));
  mcpl_print(buf);
  snprintf(buf,sizeof(buf),
           "    Storage            : %i bytes/particle\n\n",
           mcpl_hdr_particle_size(f));
  mcpl_print(buf);
}

void mcpl_dump_particles(mcpl_file_t f, uint64_t nskip, uint64_t nlimit,
                         int(filter)(const mcpl_particle_t*))
{
  int has_uf = mcpl_hdr_has_userflags(f);
  int has_pol = mcpl_hdr_has_polarisation(f);
  double uweight = mcpl_hdr_universal_weight(f);
  mcpl_print("index     pdgcode   ekin[MeV]       x[cm]       y[cm]"
             "       z[cm]          ux          uy          uz    time[ms]");
  if (!uweight)
    mcpl_print("      weight");
  if (has_pol)
    mcpl_print("       pol-x       pol-y       pol-z");
  if (has_uf)
    mcpl_print("  userflags");
  mcpl_print("\n");
  mcpl_skipforward(f,nskip);
  //Writing the next loop in an annoying way to silence MSVC C4706 warning:
  char buf[256];
  for ( uint64_t count = nlimit ; ( nlimit==0 || count-- ) ; ) {
    const mcpl_particle_t* p = mcpl_read(f);
    if (!p)
      break;
    if (filter && !filter(p) ) {
      ++count;
      continue;
    }
    uint64_t idx = mcpl_currentposition(f)-1;//-1 since mcpl_read skipped ahead
    snprintf(buf,sizeof(buf),
             "%5" PRIu64
            " %11i %11.5g %11.5g %11.5g %11.5g %11.5g %11.5g %11.5g %11.5g",
            idx, p->pdgcode, p->ekin,
            p->position[0], p->position[1], p->position[2],
            p->direction[0], p->direction[1], p->direction[2],
            p->time );
    mcpl_print(buf);
    if (!uweight) {
      snprintf(buf,sizeof(buf)," %11.5g",p->weight);
      mcpl_print(buf);
    }
    if (has_pol) {
      snprintf(buf,sizeof(buf),
               " %11.5g %11.5g %11.5g",
               p->polarisation[0],p->polarisation[1],p->polarisation[2]);
      mcpl_print(buf);
    }
    if (has_uf) {
      snprintf(buf,sizeof(buf)," 0x%08x",p->userflags);
      mcpl_print(buf);
    }
    mcpl_print("\n");
  }
}

void mcpl_dump(const char * filename, int parts, uint64_t nskip, uint64_t nlimit)
{
  if (parts<0||parts>2)
    mcpl_error("mcpl_dump got forbidden value for argument parts");
  mcpl_file_t f = mcpl_open_file(filename);
  {
    char * bn = mcpl_basename(filename);
    size_t n = 128 + strlen(bn);
    char * buf = mcpl_internal_malloc( n );
    snprintf(buf,n,"Opened MCPL file %s:\n",bn);
    mcpl_print(buf);
    free(bn);
    free(buf);
  }
  if (parts==0||parts==1)
    mcpl_dump_header(f);
  if (parts==0||parts==2)
    mcpl_dump_particles(f,nskip,nlimit,NULL);
  mcpl_close_file(f);
}

MCPL_LOCAL int mcpl_actual_can_merge(mcpl_file_t ff1, mcpl_file_t ff2)
{
  mcpl_fileinternal_t * f1 = (mcpl_fileinternal_t *)ff1.internal;
  mcpl_fileinternal_t * f2 = (mcpl_fileinternal_t *)ff2.internal;
  assert(f1);
  assert(f2);
  if (f1->first_particle_pos!=f2->first_particle_pos)
    return 0;//different header

  //Note, we do not check the format_version field here, since mcpl_merge_files
  //can actually work on files with different versions.

  //Very strict checking of everything except nparticles. Even order of blobs
  //and comments must be preserved (could possibly be relaxed a bit):
  if (strcmp(f1->hdr_srcprogname,f2->hdr_srcprogname)!=0) return 0;
  if (f1->opt_userflags!=f2->opt_userflags) return 0;
  if (f1->opt_polarisation!=f2->opt_polarisation) return 0;
  if (f1->opt_singleprec!=f2->opt_singleprec) return 0;
  if (f1->opt_universalpdgcode!=f2->opt_universalpdgcode) return 0;
  if (f1->opt_universalweight!=f2->opt_universalweight) return 0;
  if (f1->is_little_endian!=f2->is_little_endian) return 0;
  if (f1->particle_size!=f2->particle_size) return 0;
  if (f1->ncomments!=f2->ncomments) return 0;
  if (f1->nblobs!=f2->nblobs) return 0;
  uint32_t i;
  for (i = 0; i<f1->ncomments; ++i) {
    const char * c1 = f1->comments[i];
    const char * c2 = f2->comments[i];
    if (strcmp(c1,c2)!=0) {
      //incompatible, unless it represents the same stat:sum: entry.
      if ( !MCPL_COMMENT_IS_STATSUM(c1) || !MCPL_COMMENT_IS_STATSUM(c2) )
        return 0;
      mcpl_internal_statsum_t sc1, sc2;
      mcpl_internal_statsum_parse_or_emit_err( c1, &sc1 );
      mcpl_internal_statsum_parse_or_emit_err( c2, &sc2 );
      if ( !sc1.key[0] || !sc2.key[0])
        return 0;
      if ( strcmp( sc1.key, sc2.key ) != 0 )
        return 0;
    }
  }
  for (i = 0; i<f1->nblobs; ++i) {
    if (f1->bloblengths[i]!=f2->bloblengths[i]) return 0;
    if (strcmp(f1->blobkeys[i],f2->blobkeys[i])!=0) return 0;
    if (memcmp(f1->blobs[i],f2->blobs[i],f1->bloblengths[i])!=0) return 0;
  }
  return 1;
}


int mcpl_can_merge(const char * file1, const char* file2)
{
  mcpl_file_t f1 = mcpl_open_file(file1);
  mcpl_file_t f2 = mcpl_open_file(file2);
  int can_merge = mcpl_actual_can_merge(f1,f2);
  mcpl_close_file(f1);
  mcpl_close_file(f2);
  return can_merge;
}

MCPL_LOCAL int mcpl_file_certainly_exists(const char * filename)
{
  mcu8str fn = mcu8str_view_cstr( filename );
  return mctools_is_file( &fn );
}

MCPL_LOCAL void mcpl_error_on_dups(unsigned n, const char ** filenames)
{
  //Checks that no filenames in provided list represent the same file, and
  //produce error if they do.
  //
  //Note: This used to be merely a warning, but in order to ensure consistent
  //operations on Windows it became an error in MCPL 2.0.0.
  //
  //Since this is C, we resort to slow O(N^2) comparison for simplicity.

  if (n<2)
    return;

  unsigned i;
  unsigned j;
  for (i = 0; i<n; ++i) {
    mcu8str fn_i = mcu8str_view_cstr( filenames[i] );
    for (j = 0; j<i; ++j) {
      mcu8str fn_j = mcu8str_view_cstr( filenames[j] );
      if ( mctools_is_same_file(&fn_i, &fn_j) )
        mcpl_error("Merging file with itself");
    }
  }
}


//Internal function for merges which will transfer the particle data in the
//input file into an output file handle which must already be open and ready to
//be written to, and otherwise be associated with an MCPL file with a compatible
//format. Note that the error messages assume the overall operation is a merge:
void mcpl_transfer_particle_contents(FILE * fo, mcpl_file_t ffi, uint64_t nparticles)
{
  mcpl_fileinternal_t * fi = (mcpl_fileinternal_t *)ffi.internal;
  assert(fi);

  if (!nparticles)
    return;//no particles to transfer

  unsigned particle_size = fi->particle_size;

  //buffer for transferring up to 1000 particles at a time:
  const unsigned npbufsize = 1000;
  char * buf = mcpl_internal_malloc(npbufsize*particle_size);
  uint64_t np_remaining = nparticles;

  while(np_remaining) {
    //NB: On linux > 2.6.33 we could use sendfile for more efficient in-kernel
    //transfer of data between two files!
    uint64_t toread = np_remaining >= npbufsize ? npbufsize : np_remaining;
    np_remaining -= toread;

    //read:
    uint64_t nb;
    if (fi->filegz) {
      assert( ((unsigned)toread)*particle_size < UINT32_MAX );
      nb = gzread(fi->filegz, buf, ((unsigned)toread)*particle_size);
    } else {
      nb = fread(buf,1,toread*particle_size,fi->file);
    }
    if (nb!=toread*particle_size)
      mcpl_error("Unexpected read-error while merging");

    //write:
    nb = fwrite(buf,1,toread*particle_size,fo);
    if (nb!=toread*particle_size)
      mcpl_error("Unexpected write-error while merging");
  }

  free(buf);
}


mcpl_outfile_t mcpl_forcemerge_files( const char * file_output,
                                      unsigned nfiles,
                                      const char ** files,
                                      int keep_userflags )
{
  ////////////////////////////////////
  // Initial sanity check of input: //
  ////////////////////////////////////

  if (!nfiles)
    mcpl_error("mcpl_forcemerge_files must be called"
               " with at least one input file");

  mcpl_error_on_dups(nfiles,files);

  //Create new file:
  if (mcpl_file_certainly_exists(file_output))
    mcpl_error("requested output file of mcpl_forcemerge_files already exists");

  ///////////////////////////////////////////
  // Fallback to normal merge if possible: //
  ///////////////////////////////////////////

  //Check all files for compatibility before we start (for robustness, we check
  //again when actually merging each file).
  unsigned ifile;
  int normal_merge_ok = 1;
  for (ifile = 1; ifile < nfiles; ++ifile) {
    if (!mcpl_can_merge(files[0],files[ifile])) {
      normal_merge_ok = 0;
      break;
    }
  }
  if (normal_merge_ok) {
    char prbuf[256];
    snprintf(prbuf,sizeof(prbuf),
             "MCPL mcpl_forcemerge_files called with %i files that are"
             " compatible for a standard merge => falling back to"
             " standard mcpl_merge_files function\n", nfiles );
    mcpl_print(prbuf);
    return mcpl_merge_files(file_output,nfiles,files);
  }

  /////////////////////////////
  // Actual forcemerge code: //
  /////////////////////////////

  //Run through files and collect meta-data:
  int opt_dp = 0;
  int opt_pol = 0;
  int opt_uf = 0;
  int lastseen_universalpdg = 0;
  int disallow_universalpdg = 0;
  double lastseen_universalweight = 0;
  int disallow_universalweight = 0;

  for (ifile = 0; ifile < nfiles; ++ifile) {
    mcpl_file_t f = mcpl_open_file(files[ifile]);
    if (!mcpl_hdr_nparticles(f)) {
      mcpl_close_file(f);
      continue;//won't affect anything
    }

    if (mcpl_hdr_has_userflags(f))
      opt_uf = 1;//enable if any

    if (mcpl_hdr_has_polarisation(f))
      opt_pol = 1;//enable if any

    if (mcpl_hdr_has_doubleprec(f))
      opt_dp = 1;

    int32_t updg = mcpl_hdr_universal_pdgcode(f);
    if ( !updg
         || ( lastseen_universalpdg && lastseen_universalpdg != updg ) ) {
      disallow_universalpdg = 1;
    } else {
      lastseen_universalpdg = updg;
    }
    double uw = mcpl_hdr_universal_weight(f);
    if ( !uw
         || ( lastseen_universalweight && lastseen_universalweight != uw ) ) {
      disallow_universalweight = 1;
    } else {
      lastseen_universalweight = uw;
    }
    mcpl_close_file(f);
  }
  if (!keep_userflags)
    opt_uf = 0;

  mcpl_outfile_t out = mcpl_create_outfile(file_output);

  if ( mcpl_internal_fakeconstantversion(0) )
    mcpl_hdr_set_srcname(out,"mcpl_forcemerge_files (from MCPL v" "99.99.99" ")");
  else
    mcpl_hdr_set_srcname(out,"mcpl_forcemerge_files (from MCPL v" MCPL_VERSION_STR ")");
  if ( opt_uf )
    mcpl_enable_userflags(out);
  if ( opt_pol )
    mcpl_enable_polarisation(out);
  if (opt_dp)
    mcpl_enable_doubleprec(out);
  if ( !disallow_universalpdg && lastseen_universalpdg )
    mcpl_enable_universal_pdgcode(out,lastseen_universalpdg);
  if ( !disallow_universalweight && lastseen_universalweight )
    mcpl_enable_universal_weight(out,lastseen_universalweight);

  //Figure out largest filename for print buffer:
  size_t nbuf = strlen(file_output);
  for (ifile = 0; ifile < nfiles; ++ifile) {
    size_t nf = strlen(files[ifile]);
    if ( nf > nbuf )
      nbuf = nf;
  }
  nbuf += 128;//other stuff on the lines
  char * buf = mcpl_internal_malloc(nbuf);

  //Finally, perform the transfer:
  for (ifile = 0; ifile < nfiles; ++ifile) {
    mcpl_file_t f = mcpl_open_file(files[ifile]);
    uint64_t np = mcpl_hdr_nparticles(f);
    snprintf(buf,nbuf,"MCPL force-merge: Transferring %" PRIu64
             " particle%s from file %s\n",
             np,(np==1?"":"s"),files[ifile]);
    mcpl_print(buf);
    while ( mcpl_read(f) != 0 )
      mcpl_transfer_last_read_particle(f, out);//lossless transfer when possible
    mcpl_close_file(f);
  }

  mcpl_outfileinternal_t * out_internal = (mcpl_outfileinternal_t *)out.internal;
  uint64_t np = out_internal->nparticles;
  snprintf(buf,nbuf,
           "MCPL force-merge: Transferred a total of %" PRIu64
           " particle%s to new file %s\n",
           np,(np==1?"":"s"),file_output);
  mcpl_print(buf);
  free(buf);
  return out;
}

MCPL_LOCAL void mcpl_internal_delete_file( const char * filename );

MCPL_LOCAL void mcpl_impl_stablesum_add( double* s1, double* s2, double x )
{
  //Numerically stable summation, based on Neumaier's algorithm
  //(doi:10.1002/zamm.19740540106).

  //s1 is the naive sum, s2 is the correction. Both should be initialised to 0,
  //and the final sum is simply their sum (s1+s2).
  double t = *s1 + x;
  if ( isinf(t) || isinf(*s1) || isinf(x) ) {
    if ( (*s1 >= 0.0) == ( x >= 0.0 ) ) {
      //same sign infinities, we can avoid NaN in this case by going directly to
      //infinity: For the use-case in MCPL this overhead is not important, but
      //avoiding the NaN is.
      *s1 = INFINITY;
      *s2 = 0.0;
      return;
    }
  }
  *s2 += fabs(*s1) >= fabs(x)  ? (*s1-t)+x : (x-t)+*s1;
  *s1 = t;

}

mcpl_outfile_t mcpl_merge_files( const char* file_output,
                                 unsigned nfiles, const char ** files )
{
  mcpl_outfile_t out;
  out.internal = NULL;

  if (!nfiles)
    mcpl_error("mcpl_merge_files must be called with at least one input file");

  //Check all files for compatibility before we start (for robustness, we check
  //again when actually merging each file).
  mcpl_error_on_dups(nfiles,files);
  unsigned ifile;
  for (ifile = 1; ifile < nfiles; ++ifile) {
    if (!mcpl_can_merge(files[0],files[ifile]))
      mcpl_error("Attempting to merge incompatible files.");
  }

  //Create new file:
  if (mcpl_file_certainly_exists(file_output))
    mcpl_error("requested output file of mcpl_merge_files already exists");

  out = mcpl_create_outfile(file_output);
  mcpl_outfileinternal_t * out_internal = (mcpl_outfileinternal_t *)out.internal;

  mcpl_file_t f1;
  f1.internal = NULL;

  int warned_oldversion = 0;

  unsigned n_scinfo = 0;
  uint32_t * scinfo_indices = NULL;
  //values kept in two doubles, s1 and s2, for use with stablesum.
  double * scinfo_values_s1 = NULL;
  double * scinfo_values_s2 = NULL;

  for (ifile = 0; ifile < nfiles; ++ifile) {
    mcpl_file_t fi = mcpl_open_file(files[ifile]);
    mcpl_fileinternal_t * fi_internal = (mcpl_fileinternal_t *)fi.internal;
    assert( fi_internal );


    if (ifile==0) {
      //Add metadata from the first file:
      mcpl_transfer_metadata(fi, out);

      //Check for stat:sum: info, and convert all values in the output file to
      //-1 initially (and update only just before returning the file handle):
      if ( !(out_internal->header_notwritten) )
        mcpl_error("unexpected early header write");
      uint32_t ncomments = out_internal->ncomments;
      if ( !fi_internal || fi_internal->ncomments != ncomments )
        mcpl_error("unexpected ncomments after transfer");
      for ( uint32_t ic = 0; ic < ncomments; ++ic ) {
        if ( MCPL_COMMENT_IS_STATSUM(fi_internal->comments[ic]) ) {
          mcpl_internal_statsum_t sc;
          mcpl_internal_statsum_parse_or_emit_err( fi_internal->comments[ic],
                                                   &sc );
          if (!scinfo_indices) {
            scinfo_indices
              = (uint32_t*)mcpl_internal_malloc( sizeof(uint32_t)*ncomments );
            scinfo_values_s1
              = (double*)mcpl_internal_malloc( sizeof(double)*ncomments );
            scinfo_values_s2
              = (double*)mcpl_internal_malloc( sizeof(double)*ncomments );
          }
          scinfo_indices[n_scinfo] = ic;
          scinfo_values_s1[n_scinfo] = 0.0;
          scinfo_values_s2[n_scinfo] = 0.0;
          if ( sc.value == -1 ) {
            scinfo_values_s1[n_scinfo] = -1.0;
          } else {
            mcpl_impl_stablesum_add( scinfo_values_s1+n_scinfo,
                                     scinfo_values_s2+n_scinfo,
                                     sc.value );
          }
          ++n_scinfo;
          //register -1 for now:
          if ( sc.value != -1.0 ) {
            char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
            mcpl_internal_encodestatsum( sc.key, -1.0, new_comment );
            size_t nn = strlen(out_internal->comments[ic]);
            if ( nn != strlen(new_comment) )
              mcpl_error("inconsistent length of stat:sum: comment");
            memcpy(out_internal->comments[ic],new_comment,nn);
          }
        }
      }

      mcpl_write_header(out_internal);
      f1 = fi;
    } else {
      //Check file is still compatible with first file
      if (!mcpl_actual_can_merge(f1,fi)) {
        if ( scinfo_indices ) {
          free(scinfo_indices);
          scinfo_indices = NULL;
        }
        if ( scinfo_values_s1 ) {
          free(scinfo_values_s1);
          scinfo_values_s1 = NULL;
        }
        if ( scinfo_values_s2 ) {
          free(scinfo_values_s2);
          scinfo_values_s2 = NULL;
        }
        mcpl_close_outfile( out );
        mcpl_internal_delete_file( file_output );
        mcpl_close_file(fi);
        mcpl_close_file(f1);
        mcpl_error("Aborting merge of suddenly incompatible files.");
      }
      //Update stat:sum: data (adding up, except that -1 combines with anything
      //to give -1):
      if ( n_scinfo ) {
        for ( unsigned isc = 0; isc < n_scinfo; ++isc ) {
          uint32_t isc_idx = scinfo_indices[isc];
          if ( scinfo_values_s1[isc] == -1.0 && scinfo_values_s2[isc] == 0.0 )
            continue;//ignore
          if ( !fi_internal || isc_idx >= fi_internal->ncomments )
            mcpl_error("Number of comments changed during merge");
          if ( !MCPL_COMMENT_IS_STATSUM(fi_internal->comments[isc_idx]) )
            mcpl_error("logic error during stat:sum: merge");
          mcpl_internal_statsum_t sc;
          mcpl_internal_statsum_parse_or_emit_err( fi_internal->comments[isc_idx],
                                                   &sc );
          if ( sc.value == -1.0 ) {
            scinfo_values_s1[isc] = -1.0;
            scinfo_values_s2[isc] = 0.0;
          } else {
            mcpl_impl_stablesum_add( scinfo_values_s1+isc,
                                     scinfo_values_s2+isc,
                                     sc.value );
          }
        }
      }
    }

    //Transfer particle contents:
    if (mcpl_hdr_version(fi)==MCPL_FORMATVERSION) {
      //Can transfer raw bytes:
      uint64_t npi = mcpl_hdr_nparticles(fi);
      mcpl_transfer_particle_contents(out_internal->file, fi, npi);
      out_internal->nparticles += npi;
    } else {
      //Merging from older version. Transfer via public interface to re-encode
      //particle data for latest format:
      if (!warned_oldversion) {
        warned_oldversion = 1;
        mcpl_print("MCPL WARNING: Merging files from older MCPL"
                   " format. Output will be in latest format.\n");
      }

      //Writing the next loop in an annoying way to silence MSVC C4706 warning:
      for(;;) {
        const mcpl_particle_t* particle = mcpl_read(fi);
        if (!particle)
          break;
        mcpl_add_particle(out,particle);
      }
    }

    if (ifile!=0)
      mcpl_close_file(fi);
  }

  mcpl_close_file(f1);

  //Finally we must update the sum stats:
  if ( scinfo_values_s1 && scinfo_values_s2 && scinfo_indices ) {
    int warned_statsuminf = 0;
    if ( n_scinfo != out_internal->nstatsuminfo || !out_internal->statsuminfo )
      mcpl_error("stat:sum: merge logic error");
    for ( unsigned isc = 0; isc < n_scinfo; ++isc ) {
      double val = scinfo_values_s1[isc] + scinfo_values_s2[isc];
      if ( val == -1.0 )
        continue;//already at -1
      if ( isinf(val) ) {
        if ( !warned_statsuminf ) {
          warned_statsuminf = 1;
          mcpl_print("MCPL WARNING: Merging files results in one or more"
                     " stat:sum: entries overflowing floating point"
                     " range and producing infinity. Reverting value to -1"
                     " to indicate that a precise result is not available.\n");
        }
        continue;//leave at -1
      }
      mcpl_internal_statsuminfo_t * sci = out_internal->statsuminfo + isc;
      char comment[MCPL_STATSUMBUF_MAXLENGTH+1];
      mcpl_internal_encodestatsum( sci->key, val, comment );
      mcpl_internal_updatestatsum( out_internal->file, sci, comment );
      sci->value = val;
    }

    free(scinfo_indices);
    free(scinfo_values_s1);
    free(scinfo_values_s2);
  }
  return out;
}

void mcpl_merge(const char * file1, const char* file2)
{
  mcpl_print("MCPL WARNING: Usage of function mcpl_merge is obsolete as it has"
             " been renamed to mcpl_merge_inplace. Please update your code.\n");
  mcpl_merge_inplace(file1, file2);
}

void mcpl_merge_inplace(const char * file1, const char* file2)
{
  {
    mcu8str file1_str = mcu8str_view_cstr( file1 );
    mcu8str file2_str = mcu8str_view_cstr( file2 );
    if ( mctools_is_same_file(&file1_str, &file2_str) )
      mcpl_error("Merging file with itself");
  }

  mcpl_file_t ff1 = mcpl_open_file(file1);
  mcpl_file_t ff2 = mcpl_open_file(file2);
  int can_merge = mcpl_actual_can_merge(ff1,ff2);
  if (!can_merge) {
    mcpl_close_file(ff1);
    mcpl_close_file(ff2);
    mcpl_error("Attempting to merge incompatible files");
  }

  //Access internals:
  mcpl_fileinternal_t * f1 = (mcpl_fileinternal_t *)ff1.internal;
  mcpl_fileinternal_t * f2 = (mcpl_fileinternal_t *)ff2.internal;
  assert(f1);
  assert(f2);

  if (f1->format_version!=f2->format_version) {
    mcpl_close_file(ff1);
    mcpl_close_file(ff2);
    mcpl_error("Attempting to merge incompatible files (can not mix"
               " MCPL format versions when merging inplace)");
  }

  if (f1->filegz) {
    mcpl_close_file(ff1);
    mcpl_close_file(ff2);
    mcpl_error("direct modification of gzipped files is not supported.");
  }

  uint64_t np1 = f1->nparticles;
  uint64_t np2 = f2->nparticles;
  if (!np2) {
    //nothing to take from file 2.
    mcpl_close_file(ff1);
    mcpl_close_file(ff2);
    return;
  }

  unsigned particle_size = f1->particle_size;
  uint64_t first_particle_pos = f1->first_particle_pos;

  //Should be same since can_merge:
  if ( particle_size != f2->particle_size
       || first_particle_pos != f2->first_particle_pos )
    mcpl_error("mcpl_merge_inplace: unexpected particle size or position");

  //Collect information on any stat:sum entries needing to be updated
  //post-merge:

  mcpl_internal_statsuminfo_t * statsuminfo = NULL;
  double * statsuminfo_newvalues = NULL;
  uint32_t nssi = 0;
  {
    uint64_t next_comment_pos = f1->first_comment_pos;
    for (uint32_t i = 0; i < f1->ncomments; ++i) {
      char * comment = f1->comments[i];
      size_t lcomment = strlen(comment);
      uint64_t writtenpos = next_comment_pos;
      next_comment_pos += ( lcomment + sizeof(uint32_t) );
      if ( !MCPL_COMMENT_IS_STATSUM(comment) )
        continue;
      mcpl_internal_statsum_t sc, sc2;
      mcpl_internal_statsum_parse_or_emit_err( comment, &sc );
      mcpl_internal_statsum_parse_or_emit_err( f2->comments[i], &sc2 );
      if (!statsuminfo) {
        statsuminfo = (mcpl_internal_statsuminfo_t *)
          mcpl_internal_calloc( f1->ncomments-i,
                                sizeof(mcpl_internal_statsuminfo_t) );
        statsuminfo_newvalues = (double*) mcpl_internal_calloc( f1->ncomments-i,
                                                                sizeof(double) );
      }
      uint32_t idx = nssi++;
      mcpl_internal_statsuminfo_t * s = &statsuminfo[idx];
      statsuminfo_newvalues[idx] = -1;
      if ( sc.value != -1.0 && sc2.value != -1.0 ) {
        statsuminfo_newvalues[idx] = sc.value + sc2.value;
        if ( isinf(statsuminfo_newvalues[idx]) ) {
          mcpl_print("MCPL WARNING: Merging files results in one or more"
                     " stat:sum: entries overflowing floating point"
                     " range and producing infinity. Reverting value to -1"
                     " to indicate that a precise result is not available.\n");
          statsuminfo_newvalues[idx] = -1.0;
        }
      }
      memcpy( s->key, sc.key, strlen(sc.key) + 1 );
      if ( lcomment > (size_t)(UINT32_MAX) )
        mcpl_error("logic error: unexpected large stat:sum comment strlen");
      s->writtenstrlen = (uint32_t)lcomment;
      s->writtenpos = writtenpos;
    }
  }

  //Now, close file1 and reopen a file handle in append mode:
  mcpl_close_file(ff1);
  FILE * f1a = mcpl_internal_fopen(file1,"r+b");

  //Update file positions. Note that f2->file is already at the position for the
  //first particle and that the seek operation on f1a correctly discards any
  //partial entries at the end, which could be there if the file was in need of
  //mcpl_repair:
  if (!f1a) {
    free(statsuminfo);
    free(statsuminfo_newvalues);
    mcpl_close_file(ff2);
    mcpl_error("Unable to open file1 in update mode!");
  }
  if (MCPL_FSEEK( f1a, first_particle_pos + particle_size*np1 )) {
    free(statsuminfo);
    free(statsuminfo_newvalues);
    mcpl_close_file(ff2);
    fclose(f1a);
    mcpl_error("Unable to seek to end of file1 in update mode");
  }

  //Transfer particle contents, and update stat:sum: comments. We set nparticles
  //to 0 and stat sums to -1 during the operation (so the file appears broken
  //and in need of mcpl_repair in case of errors during the transfer):
  mcpl_update_nparticles(f1a,0);

  fflush(f1a);

  //Set stat:sum entries to -1:
  if ( nssi && statsuminfo && statsuminfo_newvalues ) {
    for ( uint32_t i = 0; i < nssi; ++i ) {
      char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
      mcpl_internal_encodestatsum( statsuminfo[i].key, -1.0, new_comment );
      mcpl_internal_updatestatsum( f1a, &statsuminfo[i], new_comment );
      statsuminfo[i].value = -1.0;
    }
  }
  //Transfer particles (potentially a lot of work and chance of running out of
  //quota, etc.):
  mcpl_transfer_particle_contents(f1a, ff2, np2);

  //Set stat:sum entries to final values:
  if ( nssi && statsuminfo && statsuminfo_newvalues ) {
    for ( uint32_t i = 0; i < nssi; ++i ) {
      double newval = statsuminfo_newvalues[i];
      if ( newval == -1.0 )
        continue;//already fine
      char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
      mcpl_internal_encodestatsum( statsuminfo[i].key, newval, new_comment );
      mcpl_internal_updatestatsum( f1a, &statsuminfo[i], new_comment );
      statsuminfo[i].value = newval;
    }
  }

  //Finally we can update nparticles:
  mcpl_update_nparticles(f1a,np1+np2);

  //Finish up.
  fclose(f1a);
  mcpl_close_file(ff2);
  free(statsuminfo);
  free(statsuminfo_newvalues);
}

#define MCPLIMP_TOOL_DEFAULT_NLIMIT 10
#define MCPLIMP_TOOL_DEFAULT_NSKIP 0

char* mcpl_usage_progname( const char * argv0 )
{
  //Basically return the basename, but with any trailing .exe/.EXE discarded.
  char * bn = mcpl_basename(argv0);
  size_t npn = strlen(bn);
  const int has_exe_suffix = ( npn > 4
                               && ( strcmp(bn+(npn-4),".exe")==0
                                    || strcmp(bn+(npn-4),".EXE")==0 ) );
  if ( has_exe_suffix ) {
    npn -= 4;
    bn[npn] = '\0';
  }
  //Fallback to PROGNAME if empty or starts with a dot:
  if ( npn == 0 || bn[0]=='.' ) {
    free(bn);
    bn = mcpl_internal_malloc(9);
    memcpy(bn,"PROGNAME",9);
  }
  return bn;
}

MCPL_LOCAL int mcpl_tool_usage( char** argv, const char * errmsg ) {
  if (errmsg) {
    size_t n = strlen(errmsg) + 128;
    char * ebuf = mcpl_internal_malloc(n);
    snprintf(ebuf,n,
             "ERROR: %s\n\n"
             "Run with -h or --help for usage information\n",
             errmsg);
    mcpl_print(ebuf);
    free(ebuf);
    return 1;
  }
  char * progname = mcpl_usage_progname(argv[0]);
  size_t nbuf = 256 + strlen(progname);
  char * buf = mcpl_internal_malloc(nbuf);
  mcpl_print("Tool for inspecting or modifying Monte Carlo Particle List (.mcpl) files.\n");
  mcpl_print("\n");
  mcpl_print("The default behaviour is to display the contents of the FILE in human readable\n");
  mcpl_print("format (see Dump Options below for how to modify what is displayed).\n");
  mcpl_print("\n");
  mcpl_print("This installation supports direct reading of gzipped files (.mcpl.gz).\n");
  mcpl_print("\n");
  mcpl_print("Usage:\n");
  snprintf(buf,nbuf,
           "  %s [dump-options] FILE\n",progname);
  mcpl_print(buf);
  snprintf(buf,nbuf,
           "  %s --merge [merge-options] FILE1 FILE2\n",progname);
  mcpl_print(buf);
  snprintf(buf,nbuf,
           "  %s --extract [extract-options] FILE1 FILE2\n",progname);
  mcpl_print(buf);
  snprintf(buf,nbuf,
           "  %s --repair FILE\n",progname);
  mcpl_print(buf);
  snprintf(buf,nbuf,
           "  %s --version\n",progname);
  mcpl_print(buf);
  snprintf(buf,nbuf,
           "  %s --help\n",progname);
  mcpl_print(buf);
  mcpl_print("\n");
  mcpl_print("Dump options:\n");
  mcpl_print("  By default include the info in the FILE header plus the first ten contained\n");
  mcpl_print("  particles. Modify with the following options:\n");
  MCPL_STATIC_ASSERT(MCPLIMP_TOOL_DEFAULT_NLIMIT==10);
  mcpl_print("  -j, --justhead  : Dump just header info and no particle info.\n");
  mcpl_print("  -n, --nohead    : Dump just particle info and no header info.\n");
  snprintf(buf,nbuf,
           "  -lN             : Dump up to N particles from the file (default %i). You\n",
           MCPLIMP_TOOL_DEFAULT_NLIMIT);
  mcpl_print(buf);
  mcpl_print("                    can specify -l0 to disable this limit.\n");
  snprintf(buf,nbuf,
           "  -sN             : Skip past the first N particles in the file (default %i).\n",
           MCPLIMP_TOOL_DEFAULT_NSKIP);
  mcpl_print(buf);
  mcpl_print("  -bKEY           : Dump binary blob stored under KEY to standard output.\n");
  mcpl_print("\n");
  mcpl_print("Merge options:\n");
  mcpl_print("  -m, --merge FILEOUT FILE1 FILE2 ... FILEN\n");
  mcpl_print("                    Creates new FILEOUT with combined particle contents from\n");
  mcpl_print("                    specified list of N existing and compatible files.\n");
  mcpl_print("  -m, --merge --inplace FILE1 FILE2 ... FILEN\n");
  mcpl_print("                    Appends the particle contents in FILE2 ... FILEN into\n");
  mcpl_print("                    FILE1. Note that this action modifies FILE1!\n");
  mcpl_print("  --forcemerge [--keepuserflags] FILEOUT FILE1 FILE2 ... FILEN\n");
  mcpl_print("               Like --merge but works with incompatible files as well, at the\n");
  mcpl_print("               heavy price of discarding most metadata like comments and blobs.\n");
  mcpl_print("               Userflags will be discarded unless --keepuserflags is specified.\n");
  mcpl_print("\n");
  mcpl_print("Extract options:\n");
  mcpl_print("  -e, --extract FILE1 FILE2\n");
  mcpl_print("                    Extracts particles from FILE1 into a new FILE2.\n");
  mcpl_print("  -lN, -sN        : Select range of particles in FILE1 (as above).\n");
  mcpl_print("  -pPDGCODE       : Select particles of type given by PDGCODE.\n");
  mcpl_print("\n");
  mcpl_print("Other options:\n");
  mcpl_print("  -r, --repair FILE\n");
  mcpl_print("                    Attempt to repair FILE which was not properly closed, by up-\n");
  mcpl_print("                    dating the file header with the correct number of particles.\n");
  mcpl_print("  -t, --text MCPLFILE OUTFILE\n");
  mcpl_print("                    Read particle contents of MCPLFILE and write into OUTFILE\n");
  mcpl_print("                    using a simple ASCII-based format.\n");
  mcpl_print("  -v, --version   : Display version of MCPL installation.\n");
  mcpl_print("  -h, --help      : Display this usage information (ignores all other options).\n");

  free(buf);
  free(progname);
  return 0;
}

MCPL_LOCAL int mcpl_str2int(const char* str, size_t len, int64_t* res)
{
  //portable 64bit str2int with error checking (only INT64_MIN might not be
  //possible to specify).
  *res = 0;
  if (!len)
    len=strlen(str);
  if (!len)
    return 0;
  int sign = 1;
  if (str[0]=='-') {
    sign = -1;
    len -= 1;
    str += 1;
  }
  int64_t tmp = 0;
  size_t i;
  for (i=0; i<len; ++i) {
    if (str[i]<'0'||str[i]>'9') {
      return 0;
    }
    int64_t prev = tmp;
    tmp *= 10;
    tmp += str[i] - '0';
    if (prev>=tmp)
      return 1;//overflow (hopefully it did not trigger a signal or FPE)
  }
  *res = sign * tmp;
  return 1;
}

MCPL_LOCAL void mcpl_internal_dump_to_stdout( const char *, unsigned long );

#ifdef _WIN32
int mcpl_wrap_wmain( int argc, wchar_t** wargv, int(*appfct)(int,char**)  )
{
  char ** argv = malloc( sizeof(char*) * argc );
  for ( int i = 0; i < argc; ++i ) {
    mcu8str u8str = mctool_wcharstr_to_u8str( wargv[i] );
    mcu8str_ensure_dynamic_buffer(&u8str);
    argv[i] = u8str.c_str;
  }
  int ec = (*appfct)(argc,argv);
  for ( int i = 0; i < argc; ++i )
    free( argv[i] );
  free(argv);
  return ec;
}
#endif

int mcpl_tool(int argc,char** argv) {

  int nfilenames = 0;
  char ** filenames = NULL;
  const char * blobkey = NULL;
  const char * pdgcode_str = NULL;
  int opt_justhead = 0;
  int opt_nohead = 0;
  int64_t opt_num_limit = -1;
  int64_t opt_num_skip = -1;
  int opt_merge = 0;
  int opt_forcemerge = 0;
  int opt_keepuserflags = 0;
  int opt_inplace = 0;
  int opt_extract = 0;
  int opt_preventcomment = 0;//undocumented unoffical flag for mcpl unit tests
  int opt_repair = 0;
  int opt_version = 0;
  int opt_text = 0;
  int opt_fakeversion = 0;//undocumented unoffical flag for mcpl unit tests

  int i;
  for (i = 1; i<argc; ++i) {
    char * a = argv[i];
    size_t n=strlen(a);
    if (!n)
      continue;
    if (n>=2&&a[0]=='-'&&a[1]!='-') {
      //short options:
      int64_t * consume_digit = NULL;
      size_t j;
      for (j=1; j<n; ++j) {
        if (consume_digit) {
          if (a[j]<'0'||a[j]>'9') {
            free(filenames);
            return mcpl_tool_usage(argv,"Bad option: expected number");
          }
          *consume_digit *= 10;
          *consume_digit += a[j] - '0';
          continue;
        }
        if (a[j]=='b') {
          if (blobkey) {
            free(filenames);
            return mcpl_tool_usage(argv,"-b specified more than once");
          }
          if (j+1==n) {
            free(filenames);
            return mcpl_tool_usage(argv,"Missing argument for -b");
          }
          blobkey = a+j+1;
          break;
        }
        if (a[j]=='p') {
          if (pdgcode_str) {
            free(filenames);
            return mcpl_tool_usage(argv,"-p specified more than once");
          }
          if (j+1==n) {
            free(filenames);
            return mcpl_tool_usage(argv,"Missing argument for -p");
          }
          pdgcode_str = a+j+1;
          break;
        }

        switch(a[j]) {
        case 'h':
          {
            free(filenames);
            return mcpl_tool_usage(argv,0);
          }
        case 'j': opt_justhead = 1; break;
        case 'n': opt_nohead = 1; break;
        case 'm': opt_merge = 1; break;
        case 'e': opt_extract = 1; break;
        case 'r': opt_repair = 1; break;
        case 'v': opt_version = 1; break;
        case 't': opt_text = 1; break;
        case 'l': consume_digit = &opt_num_limit; break;
        case 's': consume_digit = &opt_num_skip; break;
        default:
          {
            free(filenames);
            return mcpl_tool_usage(argv,"Unrecognised option");
          }
        }
        if (consume_digit) {
          *consume_digit = 0;
          if (j+1==n) {
            free(filenames);
            return mcpl_tool_usage(argv,"Bad option: missing number");
          }
        }
      }
    } else if (n>=3&&a[0]=='-'&&a[1]=='-') {
      a+=2;
      //long options:
      const char * lo_help = "help";
      const char * lo_justhead = "justhead";
      const char * lo_nohead = "nohead";
      const char * lo_merge = "merge";
      const char * lo_inplace = "inplace";
      const char * lo_extract = "extract";
      const char * lo_preventcomment = "preventcomment";
      const char * lo_fakeversion = "fakeversion";
      const char * lo_repair = "repair";
      const char * lo_version = "version";
      const char * lo_text = "text";
      const char * lo_forcemerge = "forcemerge";
      const char * lo_keepuserflags = "keepuserflags";
      //Use strstr instead of "strcmp(a,"--help")==0" to support shortened
      //versions (works since all our long-opts start with unique char).
      if (strstr(lo_help,a)==lo_help) return free(filenames), mcpl_tool_usage(argv,0);
      else if (strstr(lo_justhead,a)==lo_justhead) opt_justhead = 1;
      else if (strstr(lo_nohead,a)==lo_nohead) opt_nohead = 1;
      else if (strstr(lo_merge,a)==lo_merge) opt_merge = 1;
      else if (strstr(lo_forcemerge,a)==lo_forcemerge) opt_forcemerge = 1;
      else if (strstr(lo_keepuserflags,a)==lo_keepuserflags) opt_keepuserflags = 1;
      else if (strstr(lo_inplace,a)==lo_inplace) opt_inplace = 1;
      else if (strstr(lo_extract,a)==lo_extract) opt_extract = 1;
      else if (strstr(lo_repair,a)==lo_repair) opt_repair = 1;
      else if (strstr(lo_version,a)==lo_version) opt_version = 1;
      else if (strstr(lo_preventcomment,a)==lo_preventcomment) opt_preventcomment = 1;
      else if (strstr(lo_fakeversion,a)==lo_fakeversion) opt_fakeversion = 1;
      else if (strstr(lo_text,a)==lo_text) opt_text = 1;
      else return free(filenames),mcpl_tool_usage(argv,"Unrecognised option");
    } else if (n>=1&&a[0]!='-') {
      //input file
      if (!filenames)
        filenames = (char **)mcpl_internal_calloc(argc,sizeof(char*));
      filenames[nfilenames] = a;
      ++nfilenames;
    } else {
      return free(filenames),mcpl_tool_usage(argv,"Bad arguments");
    }
  }

  if ( opt_fakeversion )
    mcpl_internal_fakeconstantversion(1);

  if ( opt_extract==0 && pdgcode_str )
    return free(filenames),mcpl_tool_usage(argv,"-p can only be used with --extract.");

  if ( opt_merge==0 && opt_inplace!=0 )
    return free(filenames),mcpl_tool_usage(argv,"--inplace can only be used with --merge.");

  if ( opt_forcemerge==0 && opt_keepuserflags!=0 )
    return free(filenames),mcpl_tool_usage(argv,"--keepuserflags can only be used with --forcemerge.");

  if ( opt_merge!=0 && opt_forcemerge!=0 )
    return free(filenames),mcpl_tool_usage(argv,"--merge and --forcemerge can not both be specified .");

  int number_dumpopts = (opt_justhead + opt_nohead + (blobkey!=0));
  if (opt_extract==0)
    number_dumpopts += (opt_num_limit!=-1) + (opt_num_skip!=-1);
  int any_dumpopts = number_dumpopts != 0;
  int any_extractopts = (opt_extract!=0||pdgcode_str!=0);
  int any_mergeopts = (opt_merge!=0||opt_forcemerge!=0);
  int any_textopts = (opt_text!=0);
  if (any_dumpopts+any_mergeopts+any_extractopts+any_textopts+opt_repair+opt_version>1)
    return free(filenames),mcpl_tool_usage(argv,"Conflicting options specified.");

  if (blobkey&&(number_dumpopts>1))
    return free(filenames),mcpl_tool_usage(argv,"Do not specify other dump options with -b.");

  if (opt_version) {
    free(filenames);
    if (nfilenames)
      return mcpl_tool_usage(argv,"Unrecognised arguments for --version.");

    if ( mcpl_internal_fakeconstantversion(0) )
      mcpl_print("MCPL version " "99.99.99" "\n");
    else
      mcpl_print("MCPL version " MCPL_VERSION_STR "\n");
    return 0;
  }

  if (any_mergeopts) {

    if (nfilenames<2)
      return free(filenames),mcpl_tool_usage(argv,
                                             (opt_forcemerge?"Too few arguments for --forcemerge.":"Too few arguments for --merge.") );

    int ifirstinfile = (opt_inplace ? 0 : 1);
    if (!opt_forcemerge) {
      for (i = ifirstinfile+1; i < nfilenames; ++i)
        if (!mcpl_can_merge(filenames[ifirstinfile],filenames[i]))
          return free(filenames),mcpl_tool_usage(argv,"Requested files are incompatible for merge as they have different header info.");
    }

    if (opt_inplace) {
      if ( ! ( !opt_forcemerge && opt_merge) )
        mcpl_error("logic error in argument parsing");
      //Note that if there are more than two files merged this way, that we do
      //not get the same stablesum combination of stat:sum: values as with
      //mcpl_merge_files!
      for (i = ifirstinfile+1; i < nfilenames; ++i)
        mcpl_merge_inplace(filenames[ifirstinfile],filenames[i]);
    } else {
      if (mcpl_file_certainly_exists(filenames[0]))
        return free(filenames),mcpl_tool_usage(argv,"Requested output file already exists.");

      //Disallow .gz endings unless it is .mcpl.gz, in which case we attempt to gzip automatically.
      char * outfn = filenames[0];
      size_t lfn = strlen(outfn);
      int attempt_gzip = 0;
      if( lfn > 8 && !strcmp(outfn + (lfn - 8), ".mcpl.gz")) {
        attempt_gzip = 1;
        outfn = mcpl_internal_malloc(lfn-2);//lfn+1-3
        memcpy(outfn,filenames[0],lfn-3);
        outfn[lfn-3] = '\0';
        if (mcpl_file_certainly_exists(outfn))
          return free(filenames),mcpl_tool_usage(argv,"Requested output file already exists (without .gz extension).");
      } else if( lfn > 3 && !strcmp(outfn + (lfn - 3), ".gz")) {
        return free(filenames),mcpl_tool_usage(argv,"Requested output file should not have .gz extension (unless it is .mcpl.gz).");
      }

      mcpl_outfile_t mf = ( opt_forcemerge ?
                            mcpl_forcemerge_files( outfn, nfilenames-1, (const char**)filenames + 1, opt_keepuserflags) :
                            mcpl_merge_files( outfn, nfilenames-1, (const char**)filenames + 1) );
      if (attempt_gzip) {
        if (!mcpl_closeandgzip_outfile(mf)) {
          mcpl_print("MCPL WARNING: Failed to gzip output. Non-gzipped output is found in ");
          mcpl_print(outfn);
          mcpl_print("\n");
        }
      } else {
        mcpl_close_outfile(mf);
      }
      if (outfn != filenames[0])
        free(outfn);
    }

    free(filenames);
    return 0;
  }

  if (opt_extract) {
    if (nfilenames>2)
      return free(filenames),mcpl_tool_usage(argv,"Too many arguments.");

    if (nfilenames!=2)
      return free(filenames),mcpl_tool_usage(argv,"Must specify both input and output files with --extract.");

    if (mcpl_file_certainly_exists(filenames[1]))
      return free(filenames),mcpl_tool_usage(argv,"Requested output file already exists.");

    mcpl_file_t fi = mcpl_open_file(filenames[0]);
    mcpl_outfile_t fo = mcpl_create_outfile(filenames[1]);
    mcpl_transfer_metadata(fi, fo);
    uint64_t fi_nparticles = mcpl_hdr_nparticles(fi);

    if (!opt_preventcomment) {
      char comment[1024];
      snprintf(comment, sizeof(comment), "mcpltool: extracted particles from"
               " file with %" PRIu64 " particles",fi_nparticles);
      mcpl_hdr_add_comment(fo,comment);
    }

    int32_t pdgcode_select = 0;
    if (pdgcode_str) {
      int64_t pdgcode64;
      if (!mcpl_str2int(pdgcode_str, 0, &pdgcode64) || -pdgcode64>2147483648 || pdgcode64>2147483647 || !pdgcode64)
        return free(filenames),mcpl_tool_usage(argv,"Must specify non-zero 32bit integer as argument to -p.");
      pdgcode_select = (int32_t)pdgcode64;
    }

    if ( fi_nparticles > 0
         && ( opt_num_skip > 0
              || ( opt_num_limit>0 && opt_num_limit < (int64_t)fi_nparticles ) ) ) {
      int need_stat_scaling = 0;
      unsigned ncomments = mcpl_hdr_ncomments(fi);
      for ( unsigned ic = 0; ic < ncomments; ++ic ) {
        const char * comment = mcpl_hdr_comment(fi,ic);
        if ( !MCPL_COMMENT_IS_STATSUM(comment) )
          continue;
        mcpl_internal_statsum_t sc;
        mcpl_internal_statsum_parse_or_emit_err( comment, &sc );
        if ( sc.value != -1.0 ) {
          need_stat_scaling = 1;
          break;
        }
      }
      if ( need_stat_scaling ) {
        mcpl_print("MCPL WARNING: Marking stat:sum entries in output file as "
                   "not available (-1) when filtering based on particle "
                   "positions\n");
        mcpl_hdr_scale_stat_sums( fo, -1.0 );
      }
    }

    if (opt_num_skip>0)
      mcpl_seek(fi,(uint64_t)opt_num_skip);

    //uint64_t(-1) instead of UINT64_MAX to fix clang c++98 compilation
    uint64_t left = opt_num_limit>0 ? (uint64_t)opt_num_limit : (uint64_t)-1;
    uint64_t added = 0;

    //Writing the next loop in an annoying way to silence MSVC C4706 warning:
    for (;left;) {
      --left;
      const mcpl_particle_t* particle = mcpl_read(fi);
      if (!particle)
        break;
      if (pdgcode_select && pdgcode_select!= particle->pdgcode)
        continue;
      mcpl_transfer_last_read_particle(fi, fo);
      ++added;
    }

    const char * outfile_fn = mcpl_outfile_filename(fo);
    size_t nn = strlen(outfile_fn);
    char *fo_filename = mcpl_internal_malloc(nn+4);
    //fo_filename[0] = '\0';
    memcpy(fo_filename,outfile_fn,nn+1);
    //memcpy(fo_filename+nn,".gz",4);
    //  strncat(fo_filename,mcpl_outfile_filename(fo),nn);
    if (mcpl_closeandgzip_outfile(fo))
      memcpy(fo_filename+nn,".gz",4);
    //strncat(fo_filename,".gz",3);
    mcpl_close_file(fi);

    char buf[256];
    snprintf(buf,sizeof(buf),
             "MCPL: Successfully extracted %" PRIu64 " / %"
             PRIu64 " particles from ",added,fi_nparticles);
    mcpl_print(buf);
    mcpl_print(filenames[0]);
    mcpl_print(" into ");
    mcpl_print(fo_filename);
    mcpl_print("\n");
    free(fo_filename);
    free(filenames);
    return 0;
  }

  if (opt_text) {

    if (nfilenames>2)
      return free(filenames),mcpl_tool_usage(argv,"Too many arguments.");

    if (nfilenames!=2)
      return free(filenames),mcpl_tool_usage(argv,"Must specify both input and output files with --text.");

    if (mcpl_file_certainly_exists(filenames[1]))
      return free(filenames),mcpl_tool_usage(argv,"Requested output file already exists.");

    mcpl_file_t fi = mcpl_open_file(filenames[0]);
    FILE * fout = mcpl_internal_fopen(filenames[1],"w");
    if (!fout) {
      mcpl_close_file(fi);
      free(filenames);
      return mcpl_tool_usage(argv,"Could not open output file.");
    }

    fprintf(fout,"#MCPL-ASCII\n#ASCII-FORMAT: v1\n#NPARTICLES: %" PRIu64 "\n#END-HEADER\n",mcpl_hdr_nparticles(fi));
    fprintf(fout,"index     pdgcode               ekin[MeV]                   x[cm]          "
            "         y[cm]                   z[cm]                      ux                  "
            "    uy                      uz                time[ms]                  weight  "
            "                 pol-x                   pol-y                   pol-z  userflags\n");
    //Writing the next loop in an annoying way to silence MSVC C4706 warning:
    while (1) {
      const mcpl_particle_t* p = mcpl_read(fi);
      if (!p)
        break;
      uint64_t idx = mcpl_currentposition(fi)-1;//-1 since mcpl_read skipped ahead
      fprintf( fout,"%5" PRIu64
               " %11i %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g %23.18g"
               " %23.18g %23.18g %23.18g %23.18g %23.18g 0x%08x\n",
               idx,p->pdgcode,p->ekin,p->position[0],p->position[1],p->position[2],
               p->direction[0],p->direction[1],p->direction[2],p->time,p->weight,
               p->polarisation[0],p->polarisation[1],p->polarisation[2],p->userflags);
    }
    fclose(fout);
    mcpl_close_file(fi);
    free(filenames);
    return 0;
  }

  if (nfilenames>1)
    return free(filenames),mcpl_tool_usage(argv,"Too many arguments.");

  if (!nfilenames)
    return free(filenames),mcpl_tool_usage(argv,"No input file specified");

  if (opt_repair) {
    mcpl_repair(filenames[0]);
    free(filenames);
    return 0;
  }

  //Dump mode:
  if (blobkey) {
    mcpl_file_t mcplfile = mcpl_open_file(filenames[0]);
    uint32_t ldata;
    const char * data;
    if (!mcpl_hdr_blob(mcplfile, blobkey, &ldata, &data)) {
      mcpl_close_file(mcplfile);
      return 1;
    }
    mcpl_internal_dump_to_stdout( data, ldata );
    free(filenames);
    mcpl_close_file(mcplfile);
    return 0;
  }

  if (opt_justhead&&(opt_num_limit!=-1||opt_num_skip!=-1))
    return free(filenames),mcpl_tool_usage(argv,"Do not specify -l or -s with --justhead");

  if (opt_num_limit<0) opt_num_limit = MCPLIMP_TOOL_DEFAULT_NLIMIT;
  if (opt_num_skip<0) opt_num_skip = MCPLIMP_TOOL_DEFAULT_NSKIP;

  if (opt_justhead&&opt_nohead)
    return free(filenames),mcpl_tool_usage(argv,"Do not supply both --justhead and --nohead.");

  int parts = 0;
  if (opt_nohead) parts=2;
  else if (opt_justhead) parts=1;
  mcpl_dump(filenames[0],parts,opt_num_skip,opt_num_limit);
  free(filenames);
  return 0;
}

int mcpl_gzip_file_rc(const char * filename)
{
  mcpl_print("MCPL WARNING: Usage of function mcpl_gzip_file_rc is obsolete as"
             " mcpl_gzip_file now also returns the status. Please update your"
             " code to use mcpl_gzip_file instead.\n");
  return mcpl_gzip_file(filename);
}

MCPL_LOCAL int mcpl_internal_do_gzip(const char *filename)
{
  //Open input file:
  FILE *handle_in = mcpl_internal_fopen(filename, "rb");
  if (!handle_in)
    return 0;

  //Construct output file name by appending .gz:
  size_t nn = strlen(filename);
  char * outfn = mcpl_internal_malloc(nn + 4);
  memcpy(outfn,filename,nn);
  memcpy(outfn+nn,".gz",4);

  //Open output file:
  gzFile handle_out = mcpl_gzopen(outfn, "wb");

  free(outfn);

  if (!handle_out) {
    fclose(handle_in);
    return 0;
  }

  //Compress input to output:
  char buf[16384];
  size_t len;
  while (1) {
    len = (int)fread(buf, 1, sizeof(buf), handle_in);
    if (ferror(handle_in)) {
      fclose(handle_in);
      gzclose(handle_out);
      return 0;
    }
    if (!len)
      break;
    if ((size_t)gzwrite(handle_out, buf, (unsigned)len) != len) {
      fclose(handle_in);
      gzclose(handle_out);
      return 0;
    }
  }

  //close file:
  fclose(handle_in);
  if (gzclose(handle_out) != Z_OK)
    return 0;

  //remove input file and return success:
  mcpl_internal_delete_file( filename );
  return 1;

}

int mcpl_gzip_file(const char * filename)
{
  char * bn = mcpl_basename(filename);
  size_t n = 128 + strlen(bn);
  char * buf = mcpl_internal_malloc(n);
  snprintf(buf,n,"MCPL: Compressing file %s\n",bn);
  mcpl_print(buf);
  int ec;
  if (!mcpl_internal_do_gzip(filename)) {
    ec = 0;
    snprintf(buf,n,
             "MCPL ERROR: Problems encountered while compressing file %s.\n",
             bn);
  } else {
    ec = 1;
    snprintf(buf,n,"MCPL: Compressed file into %s.gz\n",bn);
  }
  mcpl_print(buf);
  free(bn);
  free(buf);
  return ec;
}

#ifdef _WIN32
// for _setmode and O_BINARY
#  include <fcntl.h>
#  include <io.h>
#else
// for write(..) and unlink()
#  include "unistd.h"
#endif

void mcpl_internal_dump_to_stdout( const char * data,
                                   unsigned long ldata )
{
#ifdef _WIN32
  int the_stdout_fileno = _fileno(stdout);
  if ( the_stdout_fileno == -2 )
    mcpl_error("stdout is not associated with an output stream");
  if ( the_stdout_fileno == -1 )
    mcpl_error("could not determine file number of stdout");
  int oldmode = _setmode(the_stdout_fileno, O_BINARY);
  int nb = _write(the_stdout_fileno,data,ldata);
  if ( oldmode != O_BINARY )
    _setmode(the_stdout_fileno, oldmode);
  if (nb!=(int)ldata)
    mcpl_error("Problems writing to stdout");
#else
  ssize_t nb = write(STDOUT_FILENO,data,ldata);
  if (nb!=(ssize_t)ldata)
    mcpl_error("Problems writing to stdout");
#endif
}

void mcpl_internal_delete_file( const char * filename )
{
  assert(filename);
#ifdef _WIN32
  mcu8str f = mcu8str_view_cstr( filename );
  wchar_t* wpath = mctools_path2wpath(&f);//must free(..) return value.
  _wunlink(wpath);
  free(wpath);
#else
  unlink(filename);
#endif
}

mcpl_generic_wfilehandle_t mcpl_generic_wfopen( const char * filename )
{
  mcpl_generic_wfilehandle_t res;
  res.mode = 0;
  res.current_pos = 0;
  res.internal = NULL;
  res.internal = (void*)mcpl_internal_fopen(filename,"wb");
  if (!res.internal)
    mcpl_error("Unable to open file for writing!");
  return res;
}

void mcpl_generic_fwrite( mcpl_generic_wfilehandle_t* fh,
                          const char * src, uint64_t nbytes )
{
  MCPL_STATIC_ASSERT( sizeof(size_t) >= sizeof(uint32_t) );
  MCPL_STATIC_ASSERT( sizeof(int) >= sizeof(int32_t) );

  //Write nbytes. For safety, we do this in chunks well inside 32bit limit.
  const uint64_t chunk_max = INT32_MAX / 4;
  while ( nbytes > chunk_max ) {
    mcpl_generic_fwrite( fh, src, chunk_max );
    nbytes -= chunk_max;
    src += chunk_max;
  }

  if ( !nbytes )
    return;

  size_t to_write = (size_t)nbytes;
  size_t written = fwrite( src, 1, to_write, (FILE*)(fh->internal) );
  fh->current_pos += written;
  if ( written != to_write )
    mcpl_error("Error while writing to file");
}

void mcpl_generic_fwclose( mcpl_generic_wfilehandle_t* fh )
{
  if ( !fh->internal )
    mcpl_error("Error trying to close invalid file handle");
  fclose( (FILE*)(fh->internal) );
  fh->mode = 0;
  fh->current_pos = 0;
  fh->internal = NULL;
}

void mcpl_generic_fwseek( mcpl_generic_wfilehandle_t* fh,
                          uint64_t position )
{
  int rv;
  if ( position == UINT64_MAX ) {
    rv = MCPL_FSEEK_END( (FILE*)(fh->internal) );
    fh->current_pos = (uint64_t)MCPL_FTELL((FILE*)(fh->internal));
  } else {
    rv = MCPL_FSEEK( (FILE*)(fh->internal), position );
    fh->current_pos = position;
  }
  if ( rv != 0 )
    mcpl_error("Error while seeking in output file");
}

mcpl_generic_filehandle_t mcpl_generic_fopen_try( const char * filename )
{
  mcpl_generic_filehandle_t res;
  res.mode = 0;
  res.current_pos = 0;
  res.internal = NULL;

  const char * lastdot = strrchr(filename, '.');
  if (lastdot && strcmp(lastdot, ".gz") == 0) {
    MCPL_STATIC_ASSERT( sizeof(gzFile) == sizeof(void*) );
    res.internal = (void*)mcpl_gzopen( filename, "rb" );
    res.mode = 0x1;
  } else {
    res.internal = (void*)mcpl_internal_fopen(filename,"rb");
  }
  return res;
}


mcpl_generic_filehandle_t mcpl_generic_fopen( const char * filename )
{
  mcpl_generic_filehandle_t res = mcpl_generic_fopen_try(filename);
  if (!res.internal)
    mcpl_error("Unable to open file!");
  return res;
}

void mcpl_generic_fclose( mcpl_generic_filehandle_t* fh )
{
  if ( !fh->internal )
    mcpl_error("Error trying to close invalid file handle");

  //NB: We only use 1 bit in mode flag for now, so we dont have to actually do
  //"fh->mode & 0x1" to test if it is gzipped.
  if ( fh->mode )
    gzclose((gzFile)(fh->internal));
  else
    fclose( (FILE*)(fh->internal) );

  fh->mode = 0;
  fh->current_pos = 0;
  fh->internal = NULL;
}

void mcpl_generic_fread( mcpl_generic_filehandle_t* fh,
                         char * dest, uint64_t nbytes )
{
  MCPL_STATIC_ASSERT( sizeof(size_t) >= sizeof(uint32_t) );
  MCPL_STATIC_ASSERT( sizeof(int) >= sizeof(int32_t) );
  MCPL_STATIC_ASSERT( sizeof(z_off_t) >= sizeof(int32_t) );

  //Ensure we only call gzread/fread with requests well inside 32bit limit (even
  //signed since gzread can read at most INT_MAX).
  const uint64_t chunk_max = INT32_MAX / 4;
  while ( nbytes > chunk_max ) {
    mcpl_generic_fread( fh, dest, chunk_max );
    nbytes -= chunk_max;
    dest += chunk_max;
  }

  if ( !nbytes )
    return;

  unsigned to_read = (unsigned)nbytes;
  unsigned actually_read = mcpl_generic_fread_try( fh, dest, to_read );
  if ( actually_read != to_read )
    mcpl_error("Error while reading from file");
}

unsigned mcpl_generic_fread_try( mcpl_generic_filehandle_t* fh,
                                 char * dest, unsigned nbytes )
{
  MCPL_STATIC_ASSERT( sizeof(size_t) >= sizeof(uint32_t) );
  MCPL_STATIC_ASSERT( sizeof(unsigned) >= sizeof(int32_t) );
  MCPL_STATIC_ASSERT( sizeof(z_off_t) >= sizeof(int32_t) );

  if ( nbytes > INT32_MAX )
    mcpl_error("too large nbytes value for mcpl_generic_fread_try");

  unsigned nb_left = nbytes;
  unsigned nb_read = 0;

  while (1) {
    if ( !nb_left )
      return nb_read;
    unsigned nb_totry = ( nb_left > 32768 ? 32768 : nb_left );
    if ( fh->mode ) {
      int rv = gzread((gzFile)(fh->internal), dest, (z_off_t)nb_totry);
      if ( rv < 0 )
        mcpl_error("Error while reading from file");
      if ( rv < 1 )
        return nb_read;
      nb_read += (unsigned)rv;
      fh->current_pos += nb_read;
      dest += rv;
      nb_left -= (unsigned)rv;
    } else {
      size_t rv = fread(dest, 1, (size_t)nb_totry, (FILE*)(fh->internal));
      if ( rv != (size_t)nb_totry ) {
        if ( feof((FILE*)(fh->internal)) ) {
          //not an error, simply reached the end of the file.
          if ( rv ) {
            nb_read += (unsigned)rv;
            fh->current_pos += rv;
          }
          return nb_read;
        }
        mcpl_error("Error while reading from file");
      }
      dest += rv;
      nb_read += (unsigned)rv;
      fh->current_pos += rv;
      nb_left -= (unsigned)rv;
    }

  }
}

typedef struct MCPL_LOCAL {
  char * buf;
  size_t size;
  size_t capacity;
} mcpl_buffer_t;

MCPL_LOCAL mcpl_buffer_t mcpl_internal_buf_create( size_t capacity )
{
  mcpl_buffer_t res;
  res.size = 0;
  if ( capacity == 0 ) {
    res.buf = NULL;
    res.capacity = 0;
  } else {
    res.buf = mcpl_internal_malloc(capacity);
    res.capacity = capacity;
  }
  return res;
}

MCPL_LOCAL void mcpl_internal_buf_squeeze(mcpl_buffer_t* buf)
{
  if ( buf->size == buf->capacity )
    return;
  char * oldbuf = buf->buf;
  char * newbuf = mcpl_internal_malloc( buf->size );
  memcpy( newbuf, oldbuf, buf->size );
  buf->buf = newbuf;
  free(oldbuf);
}

MCPL_LOCAL void mcpl_internal_buf_swap(mcpl_buffer_t* b1, mcpl_buffer_t* b2)
{
  mcpl_buffer_t tmp = *b1;
  *b1 = *b2;
  *b2 = tmp;
}

MCPL_LOCAL void mcpl_internal_buf_reserve(mcpl_buffer_t* buf, size_t n)
{
  if ( n <= buf->capacity )
    return;
  char * oldbuf = buf->buf;
  char * newbuf = mcpl_internal_malloc( n );
  memcpy( newbuf, oldbuf, buf->size );
  buf->buf = newbuf;
  buf->capacity = n;
  free(oldbuf);
}

MCPL_LOCAL int mcpl_buf_is_text( mcpl_buffer_t* buf ) {
  //We correctly allow ASCII & UTF-8 but not UTF-16 and UTF-32 (by design).
  const unsigned char * it = (unsigned char*)buf->buf;
  const unsigned char * itE = it + buf->size;
  for (; it!=itE; ++it)
    if ( ! ( ( *it >=9 && *it<=13 ) || ( *it >=32 && *it<=126 ) || *it >=128 ) )
      return 0;
  return 1;
}

MCPL_LOCAL void mcpl_internal_normalise_eol( mcpl_buffer_t* bufobj )
{
  //Replace \r\n with \n and \r with \n.

  //First replace all \r not followed by \n inplace. Noting down if we saw any
  //\r\n along the way:
  size_t count_rn = 0;
  {
    char * buf = bufobj->buf;
    char * bufE = buf + bufobj->size;
    while( buf != bufE ) {
      char * hit = (char*)memchr( buf, '\r', bufE - buf );
      if (!hit)
        break;//done
      buf = hit + 1;
      if ( buf == bufE || *buf != '\n' ) {
        *hit = '\n';// \r but not \r\n so just with \n
      } else {
        //must be \r\n
        ++count_rn;
        ++buf;//skip over the \n
      }
    }
  }

  if (!count_rn)
    return;//done, we were able to fix everything inplace

  //Next replace \r\n with \n, requiring us to copy everything except any \r
  //chars to a new buffer:
  {
    size_t count_rn_replaced = 0;
    mcpl_buffer_t out = mcpl_internal_buf_create( bufobj->size - count_rn );
    char * dest = out.buf;
    {
      const char * buf = bufobj->buf;
      const char * bufE = buf + bufobj->size;
      while ( buf != bufE ) {
        char * hit = (char*)memchr( buf, '\r', bufE-buf );
        if (!hit) {
          //no more hits, just copy the rest:
          memcpy(dest,buf,bufE-buf);
          break;
        }
        ++count_rn_replaced;
        size_t ncopym1 = hit-buf;
        size_t ncopy = ncopym1+1;
        memcpy(dest,buf,ncopy);
        dest += ncopym1;
        buf += ncopy;
        if (buf==bufE || *buf != '\n' || *dest!='\r' )
          mcpl_error(" mcpl_internal_normalise_eol logic error (1)");
        *dest = '\n';
        ++dest;
        ++buf;//skip original '\n'
      }
      out.size = out.capacity;
      if ( count_rn_replaced != count_rn )
        mcpl_error(" mcpl_internal_normalise_eol logic error (2)");
      mcpl_internal_buf_swap(&out,bufobj);
      free(out.buf);
    }
  }
}

void mcpl_read_file_to_buffer( const char * filename,
                               uint64_t maxsize,
                               int require_text,
                               uint64_t* user_result_size,
                               char ** user_result_buf )
{
  MCPL_STATIC_ASSERT( sizeof(size_t) >= sizeof(uint64_t) );

  if ( maxsize == 0 )
    maxsize = UINT64_MAX;

  mcpl_generic_filehandle_t file = mcpl_generic_fopen( filename );
  mcpl_buffer_t out = mcpl_internal_buf_create( 65536 > maxsize
                                                ? maxsize
                                                : 65536 );

  const unsigned max_at_a_time = INT32_MAX;

  while (1) {
    if ( out.capacity >= 1103806595072 )
      mcpl_error("mcpl_read_file_to_buffer trying to load more than 1TB");
    if ( out.capacity - out.size < max_at_a_time )
      mcpl_internal_buf_reserve( &out, ( out.capacity * 2 > (size_t)maxsize
                                         ? (size_t)maxsize
                                         : out.capacity*2) );
    size_t nread_max = out.capacity - out.size;
    unsigned max_in_this_go = ( nread_max > max_at_a_time
                                ? max_at_a_time
                                : (unsigned)nread_max );
    unsigned nread_actual = mcpl_generic_fread_try( &file,
                                                    out.buf + out.size,
                                                    max_in_this_go );
    out.size += nread_actual;
    if ( nread_actual < max_in_this_go || out.size == maxsize )
      break;//no more to read
  }

  mcpl_generic_fclose( &file );

  if ( require_text ) {
    if ( !mcpl_buf_is_text(&out) )
      mcpl_error("File is not a text file");
    mcpl_internal_normalise_eol(&out);
  }

  //Discard excess allocations:
  mcpl_internal_buf_squeeze( &out );

  //Done:
  *user_result_size = out.size;
  *user_result_buf = out.buf;
}

void mcpl_hdr_add_stat_sum( mcpl_outfile_t of,
                            const char * key, double value )
{

  char comment[MCPL_STATSUMBUF_MAXLENGTH+1];
  mcpl_internal_encodestatsum( key, value, comment );
  if ( !(value>=0.0 || value == -1.0 ) || isnan(value) || isinf(value) )
    mcpl_error("logic error: lack of expected input sanitisation.");

  size_t nkey = strlen(key);

  MCPLIMP_OUTFILEDECODE;
  if (f->header_notwritten) {
    //Header not written yet, simply check other in-mem comments for clashes.
    for ( uint32_t i = 0; i < f->ncomments; ++i ) {
      if ( !MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
        continue;
      mcpl_internal_statsum_t sc;
      mcpl_internal_statsum_parse_or_emit_err( f->comments[i], &sc );
      if ( strlen(sc.key)==nkey && memcmp(sc.key,key,nkey+1)==0 ) {
        //Same variable! Simply update in place.
        size_t n = strlen(comment);
        size_t nalloc = strlen(f->comments[i]);
        if ( n != nalloc )
          mcpl_error("preallocated space for stat:sum: update does not fit");
        memcpy(f->comments[i],comment,nalloc);
        return;
      }
    }
    //Ok not there already, just add a new comment:
    mcpl_hdr_add_comment( of, comment );
    return;
  }

  //Header was already written, so we must jump back and figure out where to
  //update in the file!
  mcpl_internal_statsuminfo_t * sc_to_update = NULL;

  for ( unsigned i = 0; i < f->nstatsuminfo; ++i ) {
    if ( memcmp( f->statsuminfo[i].key, key, nkey+1 ) == 0 ) {
      sc_to_update = f->statsuminfo + i;
      break;
    }
  }
  if (!sc_to_update)
    mcpl_error("mcpl_hdr_add_stat:sum: called after first particle was added "
               "to file, but without first registering a value for the same "
               "key earlier (the special value -1 can be used for this)");

  mcpl_internal_updatestatsum( f->file, sc_to_update, comment );
  sc_to_update->value = value;
}


void mcpl_hdr_scale_stat_sums( mcpl_outfile_t of, double scale )
{
  if ( isnan(scale) )
    mcpl_error("mcpl_hdr_scale_stat_sums called with NaN (not-a-number) scale");
  if ( scale < 0.0 && scale != -1.0 )
    mcpl_error("mcpl_hdr_scale_stat_sums called with negative scale");
  if ( isinf(scale) )
    mcpl_error("mcpl_hdr_scale_stat_sums called with infinite scale");
  if ( scale == 0.0 )
    mcpl_error("mcpl_hdr_scale_stat_sums called with zero scale");

  MCPLIMP_OUTFILEDECODE;
  int any_values_turned_to_inf = 0;
  if (f->header_notwritten) {
    //Header not written yet, simply update in-mem comments.
    for ( uint32_t i = 0; i < f->ncomments; ++i ) {
      if ( !MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
        continue;
      mcpl_internal_statsum_t sc;
      mcpl_internal_statsum_parse_or_emit_err( f->comments[i], &sc );
      double new_value = ( ( scale == -1.0 || sc.value == -1.0 )
                           ? -1.0 : ( sc.value * scale ) );
      if ( isinf(new_value) ) {
        any_values_turned_to_inf = 1;
        new_value = -1.0;
      }
      if ( sc.value == new_value )
        continue;//no update needed
      char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
      mcpl_internal_encodestatsum( sc.key, new_value, new_comment );
      size_t n = strlen(new_comment);
      size_t nalloc = strlen(f->comments[i]);
      if ( n != nalloc )
        mcpl_error("preallocated space for stat:sum: update does not fit");
      memcpy(f->comments[i],new_comment,nalloc);
    }
  } else {
    //Header already written, must update on-disk.
    for ( unsigned i = 0; i < f->nstatsuminfo; ++i ) {
      mcpl_internal_statsuminfo_t * si = &f->statsuminfo[i];
      double new_value = ( ( scale == -1.0 || si->value == -1.0 )
                           ? -1.0 : ( si->value * scale ) );
      if ( isinf(new_value) ) {
        any_values_turned_to_inf = 1;
        new_value = -1.0;
      }
      if ( si->value == new_value )
        continue;//no update needed
      char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
      mcpl_internal_encodestatsum( si->key, new_value, new_comment );
      mcpl_internal_updatestatsum( f->file, si, new_comment );
      si->value = new_value;
    }
  }
  if ( any_values_turned_to_inf ) {
    mcpl_print("MCPL WARNING: The call to mcpl_hdr_scale_stat_sums resulted in"
               " one or more stat:sum: entries overflowing floating point"
               " range and producing infinity. Reverting value to -1"
               " to indicate that a precise result is not available.\n");
  }
}

double mcpl_hdr_stat_sum( mcpl_file_t ff, const char * key )
{
  MCPLIMP_FILEDECODE;
  for ( uint32_t i = 0; i < f->ncomments; ++i ) {
    const char * c = f->comments[i];
    if ( MCPL_COMMENT_IS_STATSUM(c) ) {
      mcpl_internal_statsum_t sc;
      mcpl_internal_statsum_parse_or_emit_err( c, &sc );
      if ( strcmp(key,sc.key)==0 )
        return sc.value;
    }
  }
  return -2.0;//not present
}

MCPL_LOCAL void mcpl_internal_strip_ending( mcu8str* ss,
                                            const char * ending )
{
  size_t ne = strlen( ending );
  if ( ne > ss->size )
    return;
  size_t k = ss->size - ne;
  if ( memcmp( ss->c_str + k, ending, ne ) != 0)
    return;
  ss->c_str[k] = '\0';
  ss->size = (unsigned)k;
}

MCPL_LOCAL mcu8str mcpl_internal_namehelper( const char * filename,
                                             unsigned long iproc,
                                             char mode )
{
  //mode: "m" : /abs/path/base.mpiworker<iproc>.mcpl
  //mode: "g" : /abs/path/base.mpiworker<iproc>.mcpl.gz
  //mode: "M" : /abs/path/base.mcpl
  //mode: "G" : /abs/path/base.mcpl.gz
  //mode: "B" : /abs/path/base

  //Place filename in fn and chop off any .mcpl or .mcpl.gz:
  char buf[4096];
  mcu8str fn = mcu8str_create_from_staticbuffer( buf, sizeof(buf) );
  mcu8str_append_cstr( &fn, filename );
  mcpl_internal_strip_ending(&fn,".mcpl");
  mcpl_internal_strip_ending(&fn,".mcpl.gz");

  //Make path absolute:
  {
    mcu8str tmp = mctools_absolute_path( &fn );
    mcu8str_swap( &fn, &tmp );
    mcu8str_dealloc( &tmp );
  }

  if ( mode == 'm' || mode == 'g' ) {
    //append ".mpiworker<iproc>"
    mode = ( mode == 'm' ? 'M' : 'G' );
    char ebuf[128];
    snprintf(ebuf,sizeof(ebuf),".mpiworker%lu",iproc);
    mcu8str_append_cstr( &fn, ebuf );
  }

  if ( mode == 'M' ) {
    mcu8str_append_cstr( &fn, ".mcpl" );
  } else if ( mode == 'G' ) {
    mcu8str_append_cstr( &fn, ".mcpl.gz" );
  } else if ( mode != 'B' ) {
    mcpl_error("mcpl_internal_namehelper: bad mode");
  }
  mcu8str_ensure_dynamic_buffer( &fn );
  return fn;
}

mcpl_outfile_t mcpl_create_outfile_mpi( const char * filename,
                                        unsigned long iproc,
                                        unsigned long nproc )
{
  if ( nproc > 100000000 )
    mcpl_error("mcpl_create_outfile_mpi: nproc too large");
  if ( nproc == 0 )
    mcpl_error("mcpl_create_outfile_mpi: nproc must be larger than 0");
  if ( iproc >= nproc )
    mcpl_error("mcpl_create_outfile_mpi: iproc must be less than nproc");
  mcu8str fn;

  if ( nproc > 1 ) {
    fn = mcpl_internal_namehelper( filename, iproc, 'm' );
  } else {
    //Write directly to target destination:
    fn = mcpl_internal_namehelper( filename, iproc, 'M' );
  }
  mcpl_outfile_t outfile = mcpl_create_outfile( fn.c_str );
  mcu8str_dealloc( &fn );
  return outfile;
}

void mcpl_merge_outfiles_mpi( const char * filename,
                              unsigned long nproc )
{
  if ( nproc > 100000000 )
    mcpl_error("mcpl_merge_outfiles_mpi: nproc too large");
  if ( nproc == 0 )
    mcpl_error("mcpl_merge_outfiles_mpi: nproc must be larger than 0");

  if ( nproc == 1 ) {
    //nothing to do, we wrote directly to the target. But for consistency with
    //the nproc>1 case, we do verify that the expected output file exist.
    mcu8str fngz = mcpl_internal_namehelper( filename, 0, 'G' );
    int ok = mctools_is_file( &fngz);
    if ( !ok ) {
      char ebuf[4096];
      mcu8str errmsg = mcu8str_create_from_staticbuffer( ebuf, sizeof(ebuf) );
      mcu8str_reserve( &errmsg, fngz.size + 128 );//leak only if overflows ebuf
      snprintf( errmsg.c_str, errmsg.buflen,
                "mcpl_merge_outfiles_mpi: expected output"
                " file \"%s\" from iproc=0 not found.",
                fngz.c_str );
      mcu8str_dealloc( &fngz );
      mcpl_error(errmsg.c_str);
    }
    mcu8str_dealloc( &fngz );
    return;
  }

  mcu8str targetfn = mcpl_internal_namehelper( filename, 0, 'M' );
  char ** fns = (char **)mcpl_internal_malloc( sizeof(char*) * nproc);
  for ( unsigned long iproc = 0; iproc < nproc; ++iproc ) {
    mcu8str fn_i = mcpl_internal_namehelper( filename, iproc, 'g' );
    fns[iproc] = fn_i.c_str;
  }
  //Merge worker files:
  mcpl_outfile_t outfh = mcpl_merge_files( targetfn.c_str, nproc,
                                           (const char**)fns);
  //Remove worker files:
  for ( unsigned long iproc = 0; iproc < nproc; ++iproc ) {
    char * bn = mcpl_basename(fns[iproc]);
    size_t n = 128 + strlen(bn);
    char * buf = mcpl_internal_malloc(n);
    snprintf(buf,n,"MCPL: Removing file %s\n",bn);
    mcpl_internal_delete_file( fns[iproc] );
    mcpl_print(buf);
    free(bn);
    free(buf);
  }
  //Compress merged file, removes uncompressed file too
  if ( !mcpl_closeandgzip_outfile(outfh) )
    mcpl_error("mcpl_merge_outfiles_mpi: problems gzipping final output");
  //Cleanup memory:
  mcu8str_dealloc( &targetfn );
  for ( unsigned long iproc = 0; iproc < nproc; ++iproc )
    free( fns[iproc] );
  free(fns);
}

char * mcpl_name_helper( const char * filename, char mode )
{
  //mode: "M" : /abs/path/base.mcpl
  //mode: "G" : /abs/path/base.mcpl.gz
  //mode: "B" : /abs/path/base
  //mode: "m" : base.mcpl
  //mode: "g" : base.mcpl.gz
  //mode: "b" : base

  char mode_upper = ( ( mode >= 'a' && mode <= 'z' )
                      ? 'A' + (mode - 'a') : mode );

  if ( mode_upper != 'M' && mode_upper != 'G' && mode_upper != 'B' )
    mcpl_error("mcpl_name_helper: invalid mode");

  mcu8str res = mcpl_internal_namehelper( filename, 0, mode_upper );

  if ( mode != mode_upper ) {
    mcu8str tmp = mctools_basename( &res );
    mcu8str_swap( &res, &tmp );
    mcu8str_dealloc( &tmp );
  }

  mcu8str_ensure_dynamic_buffer( &res );
  return res.c_str;
}
