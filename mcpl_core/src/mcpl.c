
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
//  4: Current version. Like version 3, but with optional per-particle        //
//     userdata, signalled by 0x2 in the userflags field of the header. With  //
//     userdata, the header contains the userdata layout string (after the    //
//     universal weight, if any), and the userdata bytes are at the end of    //
//     each particle. Without userdata, files are identical to version 3      //
//     files, except for the version number. MCPL currently only writes files //
//     with userdata in version 4, and other files in version 3.              //
//  3: Changed packing of unit vectors from octahedral to the better          //
//     performing "Adaptive Projection Packing".                              //
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
//Opening files fails if the header would need more memory than this (to
//protect against corrupted or malicious files, e.g. small gzipped files with
//huge headers), with the memory estimated roughly as the size of the header
//plus an overhead per comment and blob:
#define MCPLIMP_MAX_HEADER_MEMORY 5000000000
#define MCPLIMP_HEADER_TOO_LARGE_MSG                                    \
  "File header is too large (it would need more than 5GB of memory)"
#define MCPLIMP_HEADER_TOO_LARGE_WRITE_MSG                              \
  "File header would become too large (it would need more than 5GB of"   \
  " memory when reading the file)"
#define MCPLIMP_HEADER_ENTRY_OVERHEAD 64
//When writing files, comments and blobs are only accepted up to a smaller
//limit, so the files can always be read. The margin covers the parts of the
//header which are not counted when writing (the fixed part, and the source
//name and userdata layout strings, which are at most 65534 chars each):
#define MCPLIMP_HEADER_WRITE_MARGIN 10000000
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
typedef void (*MCPL_CHARCTXTOVOID_FCT)(const char *, void *);

typedef struct {
  MCPL_CHARTOVOID_FCT handler;
  MCPL_CHARCTXTOVOID_FCT ctxhandler;
  void * ctx;
} mcpl_internal_printhandler_t;

MCPL_LOCAL mcpl_internal_printhandler_t* mcpl_current_print_handler(void)
{
  static mcpl_internal_printhandler_t current = { NULL, NULL, NULL };
  return &current;
}

MCPL_LOCAL void mcpl_print( const char * msg )
{
  mcpl_internal_printhandler_t * current = mcpl_current_print_handler();
  if ( current->ctxhandler )
    current->ctxhandler( msg, current->ctx );
  else if ( current->handler )
    current->handler( msg );
  else
    mcpl_default_print_handler(msg);
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

//Errors in functions with an error state (es) argument: If es is NULL, the
//error is raised with mcpl_error (which does not return). Otherwise the error
//state is filled and 0 is returned, after which the caller must clean up and
//return with an error value itself:
MCPL_LOCAL int mcpl_internal_raise( mcpl_errstate_t * es, int code,
                                    const char * msg )
{
  //NB: No code after mcpl_error, since MSVC warns about unreachable code.
  if ( !es ) {
    mcpl_error(msg);
  } else {
    es->code = code;
    es->reserved = 0;
    size_t n = strlen(msg);
    if ( n >= sizeof(es->msg) )
      n = sizeof(es->msg) - 1;
    memcpy( es->msg, msg, n );
    es->msg[n] = '\0';
  }
  return 0;
}

//All public functions with an error state start by resetting the error code.
//Their return values in case of errors are unspecified in the API, but are
//fixed by the tests (to not change them by accident):
#define MCPLIMP_ES_RESET if (es) es->code = 0

MCPL_LOCAL int mcpl_internal_raise_runtime( mcpl_errstate_t * es,
                                            const char * msg )
{
  return mcpl_internal_raise( es, MCPL_ERROR_RUNTIME, msg );
}

MCPL_LOCAL int mcpl_internal_raise_io( mcpl_errstate_t * es,
                                       const char * msg )
{
  return mcpl_internal_raise( es, MCPL_ERROR_IO, msg );
}

MCPL_LOCAL int mcpl_internal_raise_nomem( mcpl_errstate_t * es )
{
  return mcpl_internal_raise( es, MCPL_ERROR_MEMORY,
                              "memory allocation failed" );
}

MCPL_LOCAL char * mcpl_internal_malloc_es( size_t n, mcpl_errstate_t * es )
{
  char * res = (char*)malloc(n ? n : 1);
  if (!res)
    mcpl_internal_raise_nomem( es );
  return res;
}

MCPL_LOCAL char * mcpl_internal_calloc_es( size_t num, size_t size,
                                           mcpl_errstate_t * es )
{
  char * res = (char*)calloc( ( num ? num : 1 ),
                              ( size ? size : 1 ) );
  if (!res)
    mcpl_internal_raise_nomem( es );
  return res;
}

//Capacity for one more entry in an array with n entries and capacity cap,
//growing to at most nmax entries (for arrays whose size in the file header can
//not be trusted for allocating them up front):
MCPL_LOCAL uint32_t mcpl_internal_grow_capacity( uint32_t n, uint32_t cap,
                                                 uint32_t nmax )
{
  if ( n < cap )
    return cap;
  uint64_t newcap = 2 * (uint64_t)cap;
  if ( newcap < 16 )
    newcap = 16;
  if ( newcap > nmax )
    newcap = nmax;
  return (uint32_t)newcap;
}

MCPL_LOCAL void * mcpl_internal_realloc_es( void * mem, size_t new_size,
                                            mcpl_errstate_t * es )
{
  void * res = realloc( mem, new_size ? new_size : 1 );
  if (!res)
    mcpl_internal_raise_nomem( es );
  return res;
}

MCPL_LOCAL char * mcpl_internal_malloc(size_t n)
{
  return mcpl_internal_malloc_es( n, NULL );
}

MCPL_LOCAL char * mcpl_internal_calloc(size_t num, size_t size)
{
  return mcpl_internal_calloc_es( num, size, NULL );
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
  mcpl_internal_printhandler_t * current = mcpl_current_print_handler();
  current->ctxhandler = NULL;
  current->ctx = NULL;
  current->handler = handler;
}

void mcpl_set_print_handler_ctx( void (*handler)(const char *, void *),
                                 void * ctx )
{
  mcpl_internal_printhandler_t * current = mcpl_current_print_handler();
  current->handler = NULL;
  current->ctxhandler = handler;
  current->ctx = handler ? ctx : NULL;
}

MCPL_LOCAL int mcpl_platform_is_little_endian(void) {
  //Return 0 for big endian, 1 for little endian.
  volatile uint32_t i=0x01234567;
  return (*((uint8_t*)(&i))) == 0x67;
}

//Replaces *dest with a copy of src, returning 0 in case of errors (in which
//case *dest is unchanged):
MCPL_LOCAL int mcpl_store_string_es( char** dest, const char * src,
                                     mcpl_errstate_t * es )
{
  if (!src)
    return mcpl_internal_raise_runtime( es, "string is NULL" );
  size_t n = strlen(src);
  if (n>65534)
    return mcpl_internal_raise_runtime( es, "string length out of range" );
  char * newstr = mcpl_internal_malloc_es(n+1,es);
  if (!newstr)
    return 0;
  //Usage of strncpy cause compiler warning on newer gcc, so we use memcpy
  //instead (should be safe, we just checked strlen above!):
  memcpy( newstr,src,n );
  newstr[n] = '\0';
  if (*dest)
    free(*dest);
  *dest = newstr;
  return 1;
}

MCPL_LOCAL void mcpl_store_string(char** dest, const char * src)
{
  mcpl_store_string_es( dest, src, NULL );
}

MCPL_LOCAL int mcpl_write_buffer_es( FILE* f, uint32_t n, const char * data,
                                     const char * errmsg, mcpl_errstate_t * es )
{
  size_t nb = fwrite(&n, 1, sizeof(n), f);
  if (nb!=sizeof(n))
    return mcpl_internal_raise_io( es, errmsg );
  nb = fwrite(data, 1, n, f);
  if (nb!=n)
    return mcpl_internal_raise_io( es, errmsg );
  return 1;
}

MCPL_LOCAL int mcpl_write_string_es( FILE* f, const char * str,
                                     const char * errmsg,
                                     mcpl_errstate_t * es )
{
  size_t n = strlen(str);
  if ( n >= 4294967295 )
    return mcpl_internal_raise_runtime( es, "too large string encountered" );
  //nb: we don't write the terminating null-char
  return mcpl_write_buffer_es( f, (uint32_t)n, str, errmsg, es );
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

//Parsing of userdata layouts like "temp:float32:K,origin:int32,tags:uint8[3]"
//(names are required, to avoid mixing up data with the same types, and the
//units are optional):

#define MCPLIMP_USERDATA_MAXSIZE 65535
#define MCPLIMP_USERDATA_MAXNAMELENGTH 64

typedef struct {
  const char * name;//not null-terminated
  size_t lname;
  const char * typespec;//e.g. "float32[3]", not null-terminated
  size_t ltypespec;
  const char * unit;//e.g. "MeV.cm^2", not null-terminated (NULL if none)
  size_t lunit;
  unsigned typesize;
  uint32_t offset;
} mcpl_internal_udfield_t;

MCPL_LOCAL unsigned mcpl_internal_udtype_size( const char * t, size_t n )
{
  static const char * names[10] = { "int8", "uint8", "int16", "uint16",
                                    "int32", "uint32", "int64", "uint64",
                                    "float32", "float64" };
  static const unsigned sizes[10] = { 1, 1, 2, 2, 4, 4, 8, 8, 4, 8 };
  for ( unsigned i = 0; i < 10; ++i )
    if ( strlen(names[i]) == n && strncmp( names[i], t, n ) == 0 )
      return sizes[i];
  return 0;
}

//Checks the unit of a field (n characters at u): base units in the order
//cm, MeV, ms, K, deg, each at most once, separated by dots, each with an
//optional power of a single non-zero digit (not 1), possibly negative (e.g.
//"MeV.cm^2" is not valid, but "cm^2.MeV" and "MeV^-1" are). Returns an error
//message, or NULL if the unit is valid:
MCPL_LOCAL const char * mcpl_internal_udunit_problem( const char * u, size_t n )
{
  static const char * names[5] = { "cm", "MeV", "ms", "K", "deg" };
  const char * end = u + n;
  //(common ways of writing units, which are not used here):
  if ( memchr( u, '(', n ) || memchr( u, ')', n ) )
    return ( "parentheses are not allowed in units (give each unit its own"
             " power, like cm^-2.MeV^-1 for 1/(cm^2*MeV))" );
  if ( memchr( u, '/', n ) )
    return ( "division is not allowed in units (use negative powers, like"
             " MeV.cm^-1 for MeV/cm)" );
  if ( memchr( u, '*', n ) )
    return "units are separated by dots, like cm.MeV for cm*MeV";
  int last = -1;
  while ( 1 ) {
    const char * q = u;
    while ( q < end && *q != '.' && *q != '^' )
      ++q;
    if ( q == u )
      return "empty unit (the units are cm, MeV, ms, K and deg, like cm^2.MeV)";
    int idx = -1;
    for ( int i = 0; i < 5; ++i )
      if ( strlen(names[i]) == (size_t)(q-u) && strncmp( names[i], u, (size_t)(q-u) ) == 0 )
        idx = i;
    if ( idx < 0 )
      return "unknown unit (the units are cm, MeV, ms, K and deg, like cm^2.MeV)";
    if ( idx == last )
      return "each unit can appear only once";
    if ( idx < last )
      return "the units must be in the order cm, MeV, ms, K, deg";
    last = idx;
    if ( q < end && *q == '^' ) {
      ++q;
      int neg = ( q < end && *q == '-' );
      if ( neg )
        ++q;
      if ( q >= end || *q < '1' || *q > '9' || ( *q == '1' && !neg ) )
        return ( "invalid power (powers are single digits from 2 to 9"
                 " or -1 to -9, like cm^2 or MeV^-1)" );
      ++q;
    }
    if ( q == end )
      return NULL;
    if ( *q != '.' )
      return ( "invalid power (powers are single digits from 2 to 9"
               " or -1 to -9, like cm^2 or MeV^-1)" );
    u = q + 1;
  }
}

//Parses the layout, returning an error message (or NULL if valid). If fields
//is not NULL, it must have room for one more entry than the number of commas
//in the layout, and will be filled. The total size is returned in size.
MCPL_LOCAL const char * mcpl_internal_udlayout_parse( const char * layout,
                                                      mcpl_internal_udfield_t * fields,
                                                      uint32_t * nfields,
                                                      uint32_t * size )
{
  *nfields = 0;
  *size = 0;
  if ( !layout || !*layout )
    return "empty layout";
  uint64_t offset = 0;
  const char * c = layout;
  while ( 1 ) {
    const char * fend = strchr( c, ',' );
    if ( !fend )
      fend = c + strlen(c);
    mcpl_internal_udfield_t fld;
    if ( fend == c )
      return "empty field";
    const char * colon = (const char*)memchr( c, ':', (size_t)(fend-c) );
    if ( !colon )
      return "fields must be given as name:type";
    fld.name = c;
    fld.lname = (size_t)(colon-c);
    fld.typespec = colon + 1;
    fld.ltypespec = (size_t)(fend - fld.typespec);
    //optional unit, after a second colon:
    const char * colon2 = (const char*)memchr( fld.typespec, ':', fld.ltypespec );
    fld.unit = colon2 ? colon2 + 1 : NULL;
    fld.lunit = colon2 ? (size_t)(fend - fld.unit) : 0;
    if ( colon2 )
      fld.ltypespec = (size_t)(colon2 - fld.typespec);
    const char * tend = fld.typespec + fld.ltypespec;
    if ( fld.lname == 0 )
      return "empty field name";
    if ( fld.lname > MCPLIMP_USERDATA_MAXNAMELENGTH )
      return "too long field name";
    if ( !( *c >= 'a' && *c <= 'z' ) )
      return "field names must start with a lowercase letter";
    for ( size_t i = 1; i < fld.lname; ++i ) {
      char ch = c[i];
      if ( !( ( ch >= 'a' && ch <= 'z' ) || ( ch >= '0' && ch <= '9' )
              || ch == '_' ) )
        return ( "field names must only contain lowercase letters,"
                 " digits and underscores" );
    }
    //type and optional array size:
    const char * bracket = (const char*)memchr( fld.typespec, '[', fld.ltypespec );
    size_t ltype = bracket ? (size_t)(bracket - fld.typespec) : fld.ltypespec;
    fld.typesize = mcpl_internal_udtype_size( fld.typespec, ltype );
    if ( !fld.typesize )
      return ( "unknown type (must be one of int8, uint8, int16, uint16,"
               " int32, uint32, int64, uint64, float32, float64)" );
    uint64_t count = 1;
    if ( bracket ) {
      const char * d = bracket + 1;
      if ( d >= tend || *d < '1' || *d > '9' || tend[-1] != ']' )
        return "invalid array size (must be like [3])";
      count = 0;
      for ( ; d < tend - 1; ++d ) {
        if ( *d < '0' || *d > '9' )
          return "invalid array size (must be like [3])";
        count = count * 10 + (uint64_t)(*d - '0');
        if ( count > MCPLIMP_USERDATA_MAXSIZE )
          return "too large userdata (at most 65535 bytes are allowed)";
      }
    }
    if ( fld.unit ) {
      const char * uerr = mcpl_internal_udunit_problem( fld.unit, fld.lunit );
      if ( uerr )
        return uerr;
    }
    //unique names:
    if ( fields ) {
      for ( uint32_t i = 0; i < *nfields; ++i )
        if ( fields[i].lname == fld.lname
             && strncmp( fields[i].name, fld.name, fld.lname ) == 0 )
          return "duplicate field name";
    }
    fld.offset = (uint32_t)offset;
    offset += count * fld.typesize;
    if ( offset > MCPLIMP_USERDATA_MAXSIZE )
      return "too large userdata (at most 65535 bytes are allowed)";
    if ( fields )
      fields[*nfields] = fld;
    *nfields += 1;
    if ( !*fend )
      break;
    c = fend + 1;
  }
  *size = (uint32_t)offset;
  return NULL;
}

MCPL_LOCAL int mcpl_internal_udlayout_error( const char * layout,
                                             const char * errmsg,
                                             mcpl_errstate_t * es )
{
  char buf[512];
  snprintf( buf, sizeof(buf), "Invalid userdata layout \"%.200s%s\": %s",
            layout ? layout : "",
            ( layout && strlen(layout) > 200 ) ? "..." : "", errmsg );
  return mcpl_internal_raise_runtime( es, buf );
}

//Validates the layout and returns the number of bytes (with an error in case
//of invalid layouts, in which case 0 is returned, since valid layouts are
//never empty):
MCPL_LOCAL const char * mcpl_internal_blobkey_problem( const char * key )
{
  //Blob keys must be non-empty, ASCII, no non-printable characters,
  //whitespace, backslash, or quotation marks (including backtick). This is
  //required in format version 4, and when adding keys to new files. Returns
  //NULL if the key is valid:
  if ( !*key )
    return "empty keys are not allowed";
  for ( const char * c = key; *c; ++c ) {
    const unsigned char uc = (unsigned char)(*c);
    if ( uc > 127 )
      return "non-ASCII characters are not allowed";
    if ( uc == ' ' )
      return "whitespace is not allowed";
    if ( uc < 32 || uc == 127 )
      return "non-printable characters are not allowed";
    if ( uc == '"' || uc == '\'' || uc == '\\' || uc == '`' )
      return "quotation marks, backslash and backtick are not allowed";
  }
  return NULL;
}

MCPL_LOCAL uint32_t mcpl_internal_udlayout_validate( const char * layout,
                                                     mcpl_errstate_t * es )
{
  uint32_t nfields, size;
  //First pass for syntax and count, second pass also checks for duplicates:
  const char * err = mcpl_internal_udlayout_parse( layout, NULL,
                                                   &nfields, &size );
  if ( !err ) {
    mcpl_internal_udfield_t * fields = (mcpl_internal_udfield_t *)
      mcpl_internal_malloc_es( nfields * sizeof(mcpl_internal_udfield_t), es );
    if ( !fields )
      return 0;
    err = mcpl_internal_udlayout_parse( layout, fields, &nfields, &size );
    free(fields);
  }
  if ( err ) {
    mcpl_internal_udlayout_error( layout, err, es );
    return 0;
  }
  return size;
}

uint32_t mcpl_userdata_layout_size_es( const char * layout,
                                       mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  return mcpl_internal_udlayout_validate( layout, es );
}

uint32_t mcpl_userdata_layout_size( const char * layout )
{
  return mcpl_internal_udlayout_validate( layout, NULL );
}

uint32_t mcpl_userdata_offset_es( const char * layout, const char * name,
                                  const char * type, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  uint32_t nfields, size;
  if ( !mcpl_internal_udlayout_validate( layout, es ) )
    return UINT32_MAX;
  mcpl_internal_udlayout_parse( layout, NULL, &nfields, &size );
  mcpl_internal_udfield_t * fields = (mcpl_internal_udfield_t *)
    mcpl_internal_malloc_es( nfields * sizeof(mcpl_internal_udfield_t), es );
  if ( !fields )
    return UINT32_MAX;
  mcpl_internal_udlayout_parse( layout, fields, &nfields, &size );
  size_t lname = name ? strlen(name) : 0;
  const char * err = "no such field in the userdata layout";
  uint32_t offset = 0;
  for ( uint32_t i = 0; i < nfields; ++i ) {
    if ( !name || fields[i].lname != lname
         || strncmp( fields[i].name, name, lname ) != 0 )
      continue;
    if ( !type || strlen(type) != fields[i].ltypespec
         || strncmp( fields[i].typespec, type, fields[i].ltypespec ) != 0 ) {
      err = "field has a different type in the userdata layout";
    } else {
      err = NULL;
      offset = fields[i].offset;
    }
    break;
  }
  free(fields);
  if ( err ) {
    char buf[512];
    snprintf( buf, sizeof(buf), "mcpl_userdata_offset(\"%.200s\",\"%.70s\","
              "\"%.20s\"): %s", layout, name ? name : "",
              type ? type : "", err );
    mcpl_internal_raise_runtime( es, buf );
    return UINT32_MAX;
  }
  return offset;
}

uint32_t mcpl_userdata_offset( const char * layout, const char * name,
                               const char * type )
{
  return mcpl_userdata_offset_es( layout, name, type, NULL );
}

#define MCPLIMP_UD_GETSET(tname,ctype)                                      \
  ctype mcpl_userdata_get_##tname( const uint8_t * ud, uint32_t offset )   \
  {                                                                         \
    ctype v;                                                                \
    memcpy( &v, ud + offset, sizeof(v) );                                   \
    return v;                                                               \
  }                                                                         \
  void mcpl_userdata_set_##tname( uint8_t * ud, uint32_t offset, ctype v ) \
  {                                                                         \
    memcpy( ud + offset, &v, sizeof(v) );                                   \
  }

MCPLIMP_UD_GETSET(int8,int8_t)
MCPLIMP_UD_GETSET(uint8,uint8_t)
MCPLIMP_UD_GETSET(int16,int16_t)
MCPLIMP_UD_GETSET(uint16,uint16_t)
MCPLIMP_UD_GETSET(int32,int32_t)
MCPLIMP_UD_GETSET(uint32,uint32_t)
MCPLIMP_UD_GETSET(int64,int64_t)
MCPLIMP_UD_GETSET(uint64,uint64_t)
MCPLIMP_UD_GETSET(float32,float)
MCPLIMP_UD_GETSET(float64,double)

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
  char * userdata_layout;//NULL if no userdata
  uint32_t userdata_size;//included in particle_size
  char * particle_buffer;//particle_size bytes
  mcpl_internal_statsuminfo_t * statsuminfo;
  unsigned nstatsuminfo;
  uint64_t hdr_memory;//estimated memory needed for the header when reading
  //After errors while writing to the file, the file can only be closed (which
  //leaves it unfinished), and all other functions fail with the same error:
  int failed;
  mcpl_errstate_t failure;
} mcpl_outfileinternal_t;

#define MCPLIMP_OUTFILEDECODE mcpl_outfileinternal_t * f = (mcpl_outfileinternal_t *)of.internal; assert(f)

//For functions with an error state, also give an error (and return, with
//the return statement given) for invalid handles, and for files which are
//unusable after earlier errors:
#define MCPLIMP_OUTFILEDECODE_ES_IMPL(returnstatement)                  \
  mcpl_outfileinternal_t * f = (mcpl_outfileinternal_t *)of.internal;   \
  if (!f) {                                                             \
    mcpl_internal_raise_runtime( es, "invalid output file handle (NULL)" ); \
    returnstatement;                                                    \
  }                                                                     \
  if ( f->failed ) {                                                    \
    mcpl_internal_raise( es, f->failure.code, f->failure.msg );         \
    returnstatement;                                                    \
  }
#define MCPLIMP_OUTFILEDECODE_ES(retval) MCPLIMP_OUTFILEDECODE_ES_IMPL(return retval)
//(for functions returning void, since MSVC warns about empty macro arguments):
#define MCPLIMP_OUTFILEDECODE_ES_VOID MCPLIMP_OUTFILEDECODE_ES_IMPL(return)

//Remember error (which was just raised in es) to make the file unusable:
MCPL_LOCAL void mcpl_internal_outfile_failed( mcpl_outfileinternal_t * f,
                                              const mcpl_errstate_t * es )
{
  if ( !es )
    return;//not reached (errors without error state end the program)
  f->failed = 1;
  f->failure = *es;
}

//Recalculate particle size after changing options (returns 0 in case of
//errors, in which case nothing was changed):
MCPL_LOCAL int mcpl_recalc_psize_es( mcpl_outfileinternal_t * f,
                                     mcpl_errstate_t * es )
{
  unsigned fp = f->opt_singleprec ? sizeof(float) : sizeof(double);
  unsigned psize = 7*fp;
  if (f->opt_polarisation)
    psize += 3*fp;
  if (!f->opt_universalpdgcode)
    psize += sizeof(int32_t);
  if (!f->opt_universalweight)
    psize += fp;
  if (f->opt_userflags)
    psize += sizeof(uint32_t);
  if ( ! (psize<=MCPLIMP_MAX_PARTICLE_SIZE) )
    return mcpl_internal_raise_runtime( es, "unexpected particle size" );
  psize += f->userdata_size;
  void * newbuf = mcpl_internal_realloc_es( f->particle_buffer, psize, es );
  if ( !newbuf )
    return 0;
  f->particle_buffer = (char*)newbuf;
  f->particle_size = psize;
  f->opt_signature = 0
    + 1 * f->opt_singleprec
    + 2 * f->opt_polarisation
    + 4 * (f->opt_universalpdgcode?1:0)
    + 8 * (f->opt_universalweight?1:0)
    + 16 * f->opt_userflags
    + 32 * (f->userdata_size?1:0);
  return 1;
}

MCPL_LOCAL int mcpl_platform_compatibility_check_es( mcpl_errstate_t * es ) {
  MCPL_STATIC_ASSERT(CHAR_BIT==8);
  MCPL_STATIC_ASSERT(sizeof(float)==4);
  MCPL_STATIC_ASSERT(sizeof(double)==8);

  int32_t m1_32 = -1;
  int32_t not0_32 = ~((int32_t)0);
  int64_t m1_64 = -1;
  int64_t not0_64 = ~((int64_t)0);
  if ( m1_32 != not0_32 || m1_64 != not0_64 )
    return mcpl_internal_raise_runtime( es, "Platform compatibility check failed (integers are not two's complement)" );

  if (copysign(1.0, -0.0) != -1.0)
    return mcpl_internal_raise_runtime( es, "Platform compatibility check failed (floating point numbers do not have signed zero)" );

  mcpl_particle_t pd;
  if ( (char*)&(pd.userflags)-(char*)&(pd) != 12*sizeof(double)+sizeof(uint32_t) )
    return mcpl_internal_raise_runtime( es, "Platform compatibility check failed (unexpected padding in mcpl_particle_t)" );
  return 1;
}

MCPL_LOCAL void mcpl_platform_compatibility_check(void) {
  mcpl_platform_compatibility_check_es( NULL );
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
  if ( f->userdata_layout ) {
    free(f->userdata_layout);
    f->userdata_layout = NULL;
  }
  if ( f->particle_buffer ) {
    free(f->particle_buffer);
    f->particle_buffer = NULL;
  }
  if ( f->statsuminfo ) {
    free(f->statsuminfo);
    f->statsuminfo = NULL;
  }
  //Header data (normally already freed when the header was written):
  if ( f->hdr_srcprogname ) {
    free(f->hdr_srcprogname);
    f->hdr_srcprogname = NULL;
  }
  if ( f->comments ) {
    for ( uint32_t i = 0; i < f->ncomments; ++i )
      free(f->comments[i]);
    free(f->comments);
    f->comments = NULL;
  }
  if ( f->blobkeys ) {
    for ( uint32_t i = 0; i < f->nblobs; ++i )
      free(f->blobkeys[i]);
    free(f->blobkeys);
    f->blobkeys = NULL;
  }
  if ( f->blobs ) {
    for ( uint32_t i = 0; i < f->nblobs; ++i )
      free(f->blobs[i]);
    free(f->blobs);
    f->blobs = NULL;
  }
  if ( f->bloblengths ) {
    free(f->bloblengths);
    f->bloblengths = NULL;
  }
  free(f);
}

mcpl_outfile_t mcpl_create_outfile_es( const char * filename,
                                       mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  mcpl_outfile_t out;
  out.internal = NULL;

  //Sanity check chosen filename and append ".mcpl" if missing to help people
  //who forgot to add the extension (in the hope of higher consistency).
  if (!filename) {
    mcpl_internal_raise_runtime( es, "mcpl_create_outfile called with null"
                                 " string." );
    return out;
  }
  size_t n = strlen(filename);
  if (!n) {
    mcpl_internal_raise_runtime( es, "mcpl_create_outfile called with empty"
                                 " string." );
    return out;
  }
  if (n>4096) {
    mcpl_internal_raise_runtime( es, "mcpl_create_outfile called with too"
                                 " long string." );
    return out;
  }
  const char * lastdot = strrchr(filename, '.');
  if (lastdot==filename && n==5) {
    mcpl_internal_raise_runtime( es, "mcpl_create_outfile called with string"
                                 " with no basename part (\".mcpl\")." );
    return out;
  }

  //Initialise data structures and open file:
  if ( !mcpl_platform_compatibility_check_es( es ) )
    return out;

  mcpl_outfileinternal_t * f
    = (mcpl_outfileinternal_t*)mcpl_internal_calloc_es( 1, sizeof(mcpl_outfileinternal_t), es );
  if (!f)
    return out;

  if (!lastdot || strcmp(lastdot, ".mcpl") != 0) {
    f->filename = mcpl_internal_malloc_es(n+6,es);
    if (!f->filename) {
      mcpl_internal_cleanup_outfile(f);
      return out;
    }
    memcpy(f->filename,filename,n);
    memcpy(f->filename+n,".mcpl",6);
  } else {
    f->filename = mcpl_internal_malloc_es(n+1,es);
    if (!f->filename) {
      mcpl_internal_cleanup_outfile(f);
      return out;
    }
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
  f->userdata_layout = NULL;
  f->userdata_size = 0;
  f->particle_buffer = NULL;
  f->statsuminfo = NULL;
  f->nstatsuminfo = 0;
  f->hdr_memory = 0;
  f->failed = 0;
  if ( !mcpl_recalc_psize_es( f, es ) ) {
    mcpl_internal_cleanup_outfile(f);
    return out;
  }
  f->file = mcpl_internal_fopen(f->filename,"wb");
  if (!f->file) {
    mcpl_internal_cleanup_outfile(f);
    mcpl_internal_raise_io( es, "Unable to open output file!" );
    return out;
  }
  out.internal = f;
  return out;
}

mcpl_outfile_t mcpl_create_outfile(const char * filename)
{
  return mcpl_create_outfile_es( filename, NULL );
}

const char * mcpl_outfile_filename(mcpl_outfile_t of) {
  MCPLIMP_OUTFILEDECODE;
  return f->filename;
}

const char * mcpl_outfile_userdata_layout(mcpl_outfile_t of) {
  MCPLIMP_OUTFILEDECODE;
  return f->userdata_layout;
}

void mcpl_hdr_set_srcname_es( mcpl_outfile_t of, const char * spn,
                              mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_set_srcname called too late." );
    return;
  }
  mcpl_store_string_es( &(f->hdr_srcprogname), spn, es );
}

void mcpl_hdr_set_srcname(mcpl_outfile_t of,const char * spn)
{
  mcpl_hdr_set_srcname_es( of, spn, NULL );
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
                        " or trailing spaces" );
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
    res->errmsg = "value field must hold a non-negative value or -1";
    return;
  }
  if ( isinf(val) ) {
    res->errmsg = "value field holds forbidden value (+INFINITY)";
    return;
  }
  res->value = val;
  return;
}

MCPL_LOCAL int mcpl_internal_statsum_parse_or_emit_err_es( const char * comment,
                                                           mcpl_internal_statsum_t* res,
                                                           mcpl_errstate_t * es )
{
  //Returns 0 (after raising an error) in case of syntax errors:
  mcpl_internal_statsumparse( comment, res );
  if ( !res->errmsg )
    return 1;
  if ( strlen(comment) > 16*MCPL_STATSUMBUF_MAXLENGTH
       || strlen(res->errmsg) > 1024 ) {
    return mcpl_internal_raise_runtime( es, "Syntax error: could not properly"
                                        " decode comment starting with"
                                        " \"stat:sum:\" (content too long to"
                                        " show)" );
  } else {
    char buf[1200+16*MCPL_STATSUMBUF_MAXLENGTH];
    snprintf(buf,sizeof(buf),
             "Syntax error: could not properly decode comment starting"
             " with \"stat:sum:\" (%s). Issue with comment \"%s\"",
             res->errmsg,comment);
    return mcpl_internal_raise_runtime( es, buf );
  }
}

MCPL_LOCAL void mcpl_internal_statsum_parse_or_emit_err( const char * comment,
                                                         mcpl_internal_statsum_t* res )
{
  mcpl_internal_statsum_parse_or_emit_err_es( comment, res, NULL );
}

//Check that a header entry with the given number of bytes can be added
//(returns 0 in case of errors):
MCPL_LOCAL int mcpl_internal_check_hdr_memory( mcpl_outfileinternal_t * f,
                                               uint64_t nbytes,
                                               mcpl_errstate_t * es )
{
  MCPL_STATIC_ASSERT( MCPLIMP_HEADER_WRITE_MARGIN
                      >= 8 + 8 + 32 + 8 + 2 * ( 4 + 65534 ) );
  if ( f->hdr_memory + nbytes + MCPLIMP_HEADER_ENTRY_OVERHEAD
       > (uint64_t)MCPLIMP_MAX_HEADER_MEMORY - MCPLIMP_HEADER_WRITE_MARGIN )
    return mcpl_internal_raise_runtime( es, MCPLIMP_HEADER_TOO_LARGE_WRITE_MSG );
  return 1;
}

void mcpl_hdr_add_comment_es( mcpl_outfile_t of, const char * comment,
                              mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_add_comment called too late." );
    return;
  }
  if (!comment) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_add_comment called with null"
                                 " string." );
    return;
  }
  if ( MCPL_COMMENT_IS_STATSUM(comment) ) {
    //comment starts with "stat:sum:". Let us require it to live up to the
    //syntax by decoding it, to trigger any issues:
    mcpl_internal_statsum_t sc;
    if ( !mcpl_internal_statsum_parse_or_emit_err_es( comment, &sc, es ) )
      return;
    //Files with duplicate keys can not be read:
    for ( uint32_t i = 0; i < f->ncomments; ++i ) {
      if ( !MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
        continue;
      mcpl_internal_statsum_t sc_other;
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( f->comments[i],
                                                        &sc_other, es ) )
        return;
      if ( strcmp( sc.key, sc_other.key ) == 0 ) {
        char buf[MCPL_STATSUMKEY_MAXLENGTH+256];
        snprintf(buf,sizeof(buf),"Duplicate stat:sum: key. The key \"%s\""
                 " appears more than once.",sc.key);
        mcpl_internal_raise_runtime( es, buf );
        return;
      }
    }
  } else {
    if ( strncmp( comment, "stat:", 5 ) == 0 ) {
      mcpl_internal_raise_runtime( es, "Refusing to create file with comments"
                                   " starting with \"stat:\" unless starting"
                                   " with \"stat:sum:\", as such syntax is"
                                   " reserved for future usage." );
      return;
    }
  }
  const uint64_t nbytes = sizeof(uint32_t) + strlen(comment);
  if ( !mcpl_internal_check_hdr_memory( f, nbytes, es ) )
    return;
  //Allocate everything before changing anything:
  char * newcomment = NULL;
  if ( !mcpl_store_string_es( &newcomment, comment, es ) )
    return;
  void * newarr = mcpl_internal_realloc_es( f->comments,
                                            ( f->ncomments + 1 ) * sizeof(char*),
                                            es );
  if ( !newarr ) {
    free(newcomment);
    return;
  }
  f->comments = (char **)newarr;
  f->comments[f->ncomments] = newcomment;
  f->ncomments += 1;
  f->hdr_memory += nbytes + MCPLIMP_HEADER_ENTRY_OVERHEAD;
}

void mcpl_hdr_add_comment(mcpl_outfile_t of,const char *comment)
{
  mcpl_hdr_add_comment_es( of, comment, NULL );
}

//With lenient, the rules for blob keys are not applied (for keys copied from
//files in format versions before 4, where they did not apply):
MCPL_LOCAL void mcpl_internal_hdr_add_data_es( mcpl_outfile_t of,
                                               const char * key,
                                               uint32_t ldata,
                                               const char * data,
                                               int lenient,
                                               mcpl_errstate_t * es )
{
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_add_data called too late." );
    return;
  }
  if ( !key || ( ldata && !data ) ) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_add_data called with null"
                                 " pointer." );
    return;
  }
  const char * keyproblem = lenient ? NULL : mcpl_internal_blobkey_problem( key );
  if ( keyproblem ) {
    char buf[256];
    snprintf(buf,sizeof(buf),"mcpl_hdr_add_data got invalid key"
             " (%s).",keyproblem);
    mcpl_internal_raise_runtime( es, buf );
    return;
  }
  //Check that key is unique
  for ( uint32_t i = 0; i < f->nblobs; ++i ) {
    if (strcmp(f->blobkeys[i],key)==0) {
      mcpl_internal_raise_runtime( es, "mcpl_hdr_add_data got duplicate key" );
      return;
    }
  }
  const uint64_t nbytes = 2*sizeof(uint32_t) + strlen(key) + (uint64_t)ldata;
  if ( !mcpl_internal_check_hdr_memory( f, nbytes, es ) )
    return;
  //Allocate everything before changing anything (the arrays might grow
  //without the new entry being added, which is harmless):
  char * newkey = NULL;
  if ( !mcpl_store_string_es( &newkey, key, es ) )
    return;
  char * newdata = mcpl_internal_malloc_es( ldata, es );
  if ( !newdata ) {
    free(newkey);
    return;
  }
  const uint32_t n = f->nblobs + 1;
  void * p1 = mcpl_internal_realloc_es( f->blobkeys, n * sizeof(char*), es );
  if ( p1 )
    f->blobkeys = (char**)p1;
  void * p2 = p1 ? mcpl_internal_realloc_es( f->blobs, n * sizeof(char*), es ) : NULL;
  if ( p2 )
    f->blobs = (char**)p2;
  void * p3 = p2 ? mcpl_internal_realloc_es( f->bloblengths, n * sizeof(uint32_t), es ) : NULL;
  if ( !p3 ) {
    free(newkey);
    free(newdata);
    return;
  }
  f->bloblengths = (uint32_t*)p3;
  if ( ldata )
    memcpy(newdata,data,ldata);
  f->blobkeys[f->nblobs] = newkey;
  f->blobs[f->nblobs] = newdata;
  f->bloblengths[f->nblobs] = ldata;
  f->nblobs = n;
  f->hdr_memory += nbytes + MCPLIMP_HEADER_ENTRY_OVERHEAD;
}

void mcpl_hdr_add_data_es( mcpl_outfile_t of, const char * key,
                           uint32_t ldata, const char * data,
                           mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  mcpl_internal_hdr_add_data_es( of, key, ldata, data, 0, es );
}

void mcpl_hdr_add_data(mcpl_outfile_t of, const char * key,
                       uint32_t ldata, const char * data)
{
  mcpl_hdr_add_data_es( of, key, ldata, data, NULL );
}

//Enabling options: Set option (with oldval being the value to restore in
//case of errors), recalculate particle size, and restore the option in case
//of errors:
#define MCPLIMP_SET_OPTION(field,value)                                 \
  do {                                                                  \
    f->field = value;                                                   \
    if ( !mcpl_recalc_psize_es( f, es ) )                               \
      f->field = oldval;                                                \
  } while (0)

void mcpl_enable_userflags_es( mcpl_outfile_t of, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (f->opt_userflags)
    return;
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_userflags called too late." );
    return;
  }
  int oldval = f->opt_userflags;
  MCPLIMP_SET_OPTION(opt_userflags,1);
}

void mcpl_enable_userflags(mcpl_outfile_t of)
{
  mcpl_enable_userflags_es( of, NULL );
}

void mcpl_enable_userdata_es( mcpl_outfile_t of, const char * layout,
                              mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  uint32_t size = mcpl_internal_udlayout_validate( layout, es );
  if ( !size )
    return;
  if ( f->userdata_layout ) {
    if ( strcmp( f->userdata_layout, layout ) != 0 )
      mcpl_internal_raise_runtime( es, "mcpl_enable_userdata called multiple"
                                   " times with different layouts" );
    return;
  }
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_userdata called too late." );
    return;
  }
  char * newlayout = NULL;
  if ( !mcpl_store_string_es( &newlayout, layout, es ) )
    return;
  f->userdata_size = size;
  if ( !mcpl_recalc_psize_es( f, es ) ) {
    f->userdata_size = 0;
    free(newlayout);
    return;
  }
  f->userdata_layout = newlayout;
}

void mcpl_enable_userdata(mcpl_outfile_t of, const char * layout)
{
  mcpl_enable_userdata_es( of, layout, NULL );
}

void mcpl_enable_polarisation_es( mcpl_outfile_t of, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (f->opt_polarisation)
    return;
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_polarisation called too"
                                 " late." );
    return;
  }
  int oldval = f->opt_polarisation;
  MCPLIMP_SET_OPTION(opt_polarisation,1);
}

void mcpl_enable_polarisation(mcpl_outfile_t of)
{
  mcpl_enable_polarisation_es( of, NULL );
}

void mcpl_enable_doubleprec_es( mcpl_outfile_t of, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (!f->opt_singleprec)
    return;
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_doubleprec called too"
                                 " late." );
    return;
  }
  int oldval = f->opt_singleprec;
  MCPLIMP_SET_OPTION(opt_singleprec,0);
}

void mcpl_enable_doubleprec(mcpl_outfile_t of)
{
  mcpl_enable_doubleprec_es( of, NULL );
}

void mcpl_enable_universal_pdgcode_es( mcpl_outfile_t of, int32_t pdgcode,
                                       mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (pdgcode==0) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_universal_pdgcode must be"
                                 " called with non-zero pdgcode." );
    return;
  }
  if (f->opt_universalpdgcode) {
    if (f->opt_universalpdgcode!=pdgcode)
      mcpl_internal_raise_runtime( es, "mcpl_enable_universal_pdgcode called"
                                   " multiple times" );
    return;
  }
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_universal_pdgcode called"
                                 " too late." );
    return;
  }
  int32_t oldval = f->opt_universalpdgcode;
  MCPLIMP_SET_OPTION(opt_universalpdgcode,pdgcode);
}

void mcpl_enable_universal_pdgcode(mcpl_outfile_t of, int32_t pdgcode)
{
  mcpl_enable_universal_pdgcode_es( of, pdgcode, NULL );
}

void mcpl_enable_universal_weight_es( mcpl_outfile_t of, double w,
                                      mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if (w<=0.0||isinf(w)||isnan(w)) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_universal_weight must be"
                                 " called with positive but finite weight." );
    return;
  }
  if (f->opt_universalweight) {
    if (f->opt_universalweight!=w)
      mcpl_internal_raise_runtime( es, "mcpl_enable_universal_weight called"
                                   " multiple times" );
    return;
  }
  if (!f->header_notwritten) {
    mcpl_internal_raise_runtime( es, "mcpl_enable_universal_weight called"
                                 " too late." );
    return;
  }
  double oldval = f->opt_universalweight;
  MCPLIMP_SET_OPTION(opt_universalweight,w);
}

void mcpl_enable_universal_weight(mcpl_outfile_t of, double w)
{
  mcpl_enable_universal_weight_es( of, w, NULL );
}
#undef MCPLIMP_SET_OPTION

//Encodes stat:sum: comment into targetbuf, returning 0 in case of errors:
MCPL_LOCAL int mcpl_internal_encodestatsum_es( const char * key,
                                               double value,
                                               char * targetbuf,
                                               mcpl_errstate_t * es )
{
  //Sanity check value:
  size_t nbufleft = MCPL_STATSUMBUF_MAXLENGTH+1;
  if ( isnan(value) )
    return mcpl_internal_raise_runtime( es, "Invalid value for \"stat:sum:...\". Value is invalid (NaN)" );
  if ( isinf(value) ) {
    if ( value > 0.0 )
      return mcpl_internal_raise_runtime( es, "Invalid value for \"stat:sum:...\". Value is invalid (+INF)." );
    else
      return mcpl_internal_raise_runtime( es, "Invalid value for \"stat:sum:...\". Value is invalid (-INF)." );
  }
  if ( !( value>=0.0 || value==-1.0 ) ) {
      char ebuf[256];
      snprintf(ebuf,sizeof(ebuf),"Invalid value for \"stat:sum:...\"."
               " Value is negative but is not -1.0 (it is %.15g).",value);
      return mcpl_internal_raise_runtime( es, ebuf );
  }
  //Check key:
  size_t nkey = strlen(key);
  if ( nkey < 1 )
    return mcpl_internal_raise_runtime( es, "stat:sum: key must not be empty" );
  if ( nkey > MCPL_STATSUMKEY_MAXLENGTH ) {
    char buf[2056];
    snprintf(buf,sizeof(buf),
             "stat:sum: key \"%.1900s%s\" too long (%llu chars, max %i allowed)",
             key, ( nkey > 1900 ? "..." : "" ),
             (unsigned long long)nkey,
             (int)(MCPL_STATSUMKEY_MAXLENGTH) );
    return mcpl_internal_raise_runtime( es, buf );
  }

  if ( !mcpl_check_isidentifier(key) ) {
    char buf[MCPL_STATSUMKEY_MAXLENGTH+256];
    snprintf(buf,sizeof(buf),
             "Invalid stat:sum: key \"%s\" (must begin with a letter and"
             " otherwise only contain alphanumeric characters and underscores)",
             key);
    return mcpl_internal_raise_runtime( es, buf );
  }

  //Add initial marker including colon:
  MCPL_STATIC_ASSERT( MCPL_STATSUMINI_LENGTH < MCPL_STATSUMBUF_MAXLENGTH );
  memcpy(targetbuf, MCPL_STATSUMINI, MCPL_STATSUMINI_LENGTH);
  targetbuf += MCPL_STATSUMINI_LENGTH;
  nbufleft -= MCPL_STATSUMINI_LENGTH;

  //Add key marker:
  if ( nkey > nbufleft )
    return mcpl_internal_raise_runtime( es, "stat:sum: encode buffer error" );
  memcpy(targetbuf, key, nkey );
  targetbuf += nkey;
  nbufleft -= nkey;

  //Add colon:
  if ( !nbufleft )
    return mcpl_internal_raise_runtime( es, "stat:sum: encode buffer error" );
  *targetbuf = ':';
  ++targetbuf;
  --nbufleft;

  //Add MCPL_STATSUMVAL_LENGTH bytes containing the actual value, as well as a
  //final null termination byte:
  if ( nbufleft < MCPL_STATSUMVAL_LENGTH + 1 )
    return mcpl_internal_raise_runtime( es, "stat:sum: encode buffer error" );
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
      return mcpl_internal_raise_runtime( es, "stat:sum: value encoding length error" );
    double v = strtod( targetbuf, NULL );
    if ( v != value ) {
      //ok, .15g was not good enough, go for full .17g:
      int w2 = snprintf( targetbuf,
                         nbufleft,
                         "%" MCPL_STRINGIFY(MCPL_STATSUMVAL_LENGTH) ".17g",
                         value );
      if ( w2 != MCPL_STATSUMVAL_LENGTH )
        return mcpl_internal_raise_runtime( es, "stat:sum: value encoding length error" );
    }
  }

  if ( strlen( targetbuf ) != MCPL_STATSUMVAL_LENGTH )
    return mcpl_internal_raise_runtime( es, "Unexpected encoding of stat:sum: value" );
  return 1;
}

MCPL_LOCAL void mcpl_internal_encodestatsum( const char * key,
                                             double value,
                                             char * targetbuf )
{
  mcpl_internal_encodestatsum_es( key, value, targetbuf, NULL );
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

//Writes the header, returning 0 in case of errors (after which the file is
//unusable):
MCPL_LOCAL int mcpl_write_header_es( mcpl_outfileinternal_t * f,
                                     mcpl_errstate_t * es )
{
  if (!f->header_notwritten)
    return mcpl_internal_raise_runtime( es, "Logical error!" );

  const char * errmsg="Errors encountered while attempting to write file header.";
  //Files with userdata are in format version 4, where all blob keys must
  //follow the rules (they might not, when copied from older files):
  if ( f->userdata_layout ) {
    for ( uint32_t i = 0; i < f->nblobs; ++i ) {
      const char * keyproblem = mcpl_internal_blobkey_problem( f->blobkeys[i] );
      if ( keyproblem ) {
        char buf[256];
        snprintf(buf,sizeof(buf),"The output file would have an invalid"
                 " blob key copied from an input file (%s).",keyproblem);
        return mcpl_internal_raise_runtime( es, buf );
      }
    }
  }

  //Always start the file with an unsigned char-array (for endian agnosticity)
  //containing magic word (MCPL), file format version ('001'-'999') and
  //endianness used in the file ('L' or 'B'):
  //(files with userdata are in format version 4, others still in 3):
  unsigned char start[8] = {'M','C','P','L','0','0','0','L'};
  MCPL_STATIC_ASSERT(MCPL_FORMATVERSION==4);
  const int version = f->userdata_layout ? 4 : 3;
  start[4] = (unsigned char)((version/100)%10 + '0');
  start[5] = (unsigned char)((version/10)%10 + '0');
  start[6] = (unsigned char)(version%10 + '0');
  if (!mcpl_platform_is_little_endian())
    start[7] = 'B';
  size_t nb = fwrite(start, 1, sizeof(start), f->file);
  if (nb!=sizeof(start))
    return mcpl_internal_raise_io( es, errmsg );

  //Right after the initial 8 bytes, we put the number of particles (0 for now,
  //but important that position is fixed so we can seek and update it later).:
  int64_t nparticles_pos = MCPL_FTELL(f->file);
  if (nparticles_pos!=MCPLIMP_NPARTICLES_POS)
    return mcpl_internal_raise_io( es, errmsg );
  nb = fwrite(&f->nparticles, 1, sizeof(f->nparticles), f->file);
  if (nb!=sizeof(f->nparticles))
    return mcpl_internal_raise_io( es, errmsg );

  //Then a bunch of numbers:
  uint32_t arr[8];
  arr[0] = f->ncomments;
  arr[1] = f->nblobs;
  arr[2] = ( f->opt_userflags ? 0x1 : 0 ) | ( f->userdata_layout ? 0x2 : 0 );
  arr[3] = f->opt_polarisation;
  arr[4] = f->opt_singleprec;
  arr[5] = (uint32_t)f->opt_universalpdgcode;
  arr[6] = f->particle_size;
  arr[7] = (f->opt_universalweight?1:0);
  MCPL_STATIC_ASSERT(sizeof(arr)==32);
  nb = fwrite(arr, 1, sizeof(arr), f->file);
  if (nb!=sizeof(arr))
    return mcpl_internal_raise_io( es, errmsg );

  if (f->opt_universalweight) {
    MCPL_STATIC_ASSERT(sizeof(f->opt_universalweight)==8);
    nb = fwrite((void*)(&(f->opt_universalweight)), 1, sizeof(f->opt_universalweight), f->file);
    if (nb!=sizeof(f->opt_universalweight))
      return mcpl_internal_raise_io( es, errmsg );
  }

  //Userdata layout (only in version 4, and only with userdata):
  if (f->userdata_layout
      && !mcpl_write_string_es(f->file,f->userdata_layout,errmsg,es) )
    return 0;

  //src progname:
  if ( !mcpl_write_string_es(f->file,f->hdr_srcprogname?f->hdr_srcprogname:"unknown",errmsg,es) )
    return 0;

  //Write comments and record positions of any stat:sum: entries:

  //First just count and allocate memory structure for stat:sum: entries:
  for (uint32_t i = 0; i < f->ncomments; ++i) {
    char * c = f->comments[i];
    if ( MCPL_COMMENT_IS_STATSUM(c) )
      ++(f->nstatsuminfo);
  }

  if ( f->nstatsuminfo ) {
    f->statsuminfo = (mcpl_internal_statsuminfo_t *)
      mcpl_internal_calloc_es( f->nstatsuminfo,
                               sizeof(mcpl_internal_statsuminfo_t), es );
    if ( !f->statsuminfo ) {
      f->nstatsuminfo = 0;
      return 0;
    }
  }

  //Now fill statsuminfo and write comment strings to file:
  uint32_t i;
  unsigned nstatsuminfo_written = 0;
  for (i = 0; i < f->ncomments; ++i) {
    if ( nstatsuminfo_written < f->nstatsuminfo
         && MCPL_COMMENT_IS_STATSUM(f->comments[i]) ) {
      mcpl_internal_statsum_t sc;
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( f->comments[i], &sc, es ) )
        return 0;
      if ( !sc.key[0] )
        return mcpl_internal_raise_runtime( es, "logic error while writing"
                                            " stat:sum: comments to header" );
      mcpl_internal_statsuminfo_t * statsuminfo
        = &f->statsuminfo[nstatsuminfo_written++];
      size_t lcomment = strlen(f->comments[i]);
      if ( lcomment > (size_t)(UINT32_MAX) )
        return mcpl_internal_raise_runtime( es, "logic error: unexpected large"
                                            " comment strlen" );
      statsuminfo->writtenstrlen = (uint32_t)lcomment;
      statsuminfo->writtenpos = MCPL_FTELL( f->file );
      statsuminfo->value = sc.value;
      size_t nn = strlen(sc.key);
      if ( nn > MCPL_STATSUMBUF_MAXLENGTH )
        return mcpl_internal_raise_runtime( es, "stat:sum: key unexpected"
                                            " strlen" );
      memcpy( statsuminfo->key, sc.key, nn );
    }
    if ( !mcpl_write_string_es(f->file,f->comments[i],errmsg,es) )
      return 0;
  }

  //blob keys:
  for (i = 0; i < f->nblobs; ++i)
    if ( !mcpl_write_string_es(f->file,f->blobkeys[i],errmsg,es) )
      return 0;

  //blobs:
  for (i = 0; i < f->nblobs; ++i)
    if ( !mcpl_write_buffer_es(f->file, f->bloblengths[i], f->blobs[i],errmsg,es) )
      return 0;

  //Reduce the likelihood of partially written headers (not guaranteed to have
  //an effect, but can't hurt), and detect write errors early (errors are often
  //only detected when buffered data is actually written):
  if ( fflush(f->file) )
    return mcpl_internal_raise_io( es, errmsg );

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
  return 1;
}

MCPL_LOCAL void mcpl_write_header(mcpl_outfileinternal_t * f)
{
  mcpl_write_header_es( f, NULL );
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
  //project from octahedron to unit sphere (using fma to avoid
  //platform-dependent results from compilers contracting the expression):
  double n = 1.0 / sqrt( fma( out[2], out[2],
                              fma( out[1], out[1], out[0] * out[0] ) ) );
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

MCPL_LOCAL int mcpl_internal_isfinite3( const double* v )
{
  return isfinite(v[0]) && isfinite(v[1]) && isfinite(v[2]);
}

MCPL_LOCAL const char * mcpl_internal_nonfinite_field( const mcpl_particle_t* p,
                                                       int check_polarisation,
                                                       int check_weight )
{
  //Name of the first field (to be stored) with a NaN or infinite value, or
  //NULL if all are finite:
  if ( !mcpl_internal_isfinite3( p->position ) )
    return "position";
  if ( !mcpl_internal_isfinite3( p->direction ) )
    return "direction";
  if ( check_polarisation && !mcpl_internal_isfinite3( p->polarisation ) )
    return "polarisation";
  if ( !isfinite( p->ekin ) )
    return "kinetic energy";
  if ( !isfinite( p->time ) )
    return "time";
  if ( check_weight && !isfinite( p->weight ) )
    return "weight";
  return NULL;
}

MCPL_LOCAL int mcpl_internal_serialise_particle_to_buffer( const mcpl_particle_t* particle,
                                                           const uint8_t * userdata,
                                                           mcpl_outfileinternal_t * f,
                                                           mcpl_errstate_t * es ) {

  //Serialise the provided particle (and userdata, NULL meaning zeros) into the
  //particle_buffer of the output file (according to the settings of the output
  //file). Returns 0 in case of errors (invalid particles).
  if (!particle)
    return mcpl_internal_raise_runtime( es, "attempting to add particle"
                                        " which is NULL" );

  double pack_ekindir[3];

  //Sanity checks:
  const char * nonfinite = mcpl_internal_nonfinite_field( particle,
                                                          f->opt_polarisation,
                                                          !f->opt_universalweight );
  if ( nonfinite ) {
    char buf[128];
    snprintf(buf,sizeof(buf),"attempting to add particle with NaN or"
             " infinite %s",nonfinite);
    return mcpl_internal_raise_runtime( es, buf );
  }
  double dirsq = particle->direction[0] * particle->direction[0]
    + particle->direction[1] * particle->direction[1]
    + particle->direction[2] * particle->direction[2];
  if (fabs(dirsq-1.0)>1.0e-5)
    return mcpl_internal_raise_runtime( es, "attempting to add particle with"
                                        " non-unit direction vector" );
  if (particle->ekin<0.0)
    return mcpl_internal_raise_runtime( es, "attempting to add particle with"
                                        " negative kinetic energy" );
  //direction and ekin are packed into 3 doubles:
  mcpl_unitvect_pack_adaptproj(particle->direction,pack_ekindir);
  //pack_ekindir[2] is now just a sign(1.0 or -1.0), so we can store the
  //ekin in that field as well (since it must be non-negative). We use copysign
  //to be sure the signbit is set also if ekin=0:
  pack_ekindir[2] = copysign(particle->ekin,pack_ekindir[2]);

  if (f->opt_singleprec) {
    //Values must not overflow when stored in single precision (except the
    //first two values of the packed direction, which can legitimately be
    //infinite):
    const char * toolarge = NULL;
    if ( !isfinite((float)particle->position[0])
         || !isfinite((float)particle->position[1])
         || !isfinite((float)particle->position[2]) )
      toolarge = "position";
    else if ( f->opt_polarisation
              && ( !isfinite((float)particle->polarisation[0])
                   || !isfinite((float)particle->polarisation[1])
                   || !isfinite((float)particle->polarisation[2]) ) )
      toolarge = "polarisation";
    else if ( !isfinite((float)particle->ekin) )
      toolarge = "kinetic energy";
    else if ( !isfinite((float)particle->time) )
      toolarge = "time";
    else if ( !f->opt_universalweight && !isfinite((float)particle->weight) )
      toolarge = "weight";
    if ( toolarge ) {
      char buf[128];
      snprintf(buf,sizeof(buf),"attempting to add particle with %s too large"
               " for single precision storage",toolarge);
      return mcpl_internal_raise_runtime( es, buf );
    }
  }

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
    ibuf += sizeof(uint32_t);
  }
  if (f->userdata_size) {
    if (userdata)
      memcpy( &pbuf[ibuf], userdata, f->userdata_size );
    else
      memset( &pbuf[ibuf], 0, f->userdata_size );
    ibuf += f->userdata_size;
  }
  assert(ibuf==f->particle_size);
  (void)ibuf;
  return 1;
}

//Writes the particle buffer to file (and the header first, if needed),
//returning 0 in case of errors (after which the file is unusable):
MCPL_LOCAL int mcpl_internal_write_particle_buffer_to_file_es( mcpl_outfileinternal_t * f,
                                                              mcpl_errstate_t * es ) {
  //Ensure header is written:
  if ( f->header_notwritten && !mcpl_write_header_es( f, es ) ) {
    mcpl_internal_outfile_failed( f, es );
    return 0;
  }

  //Increment nparticles and write buffer to file:
  size_t nb;
  nb = fwrite(&(f->particle_buffer[0]), 1, f->particle_size, f->file);
  if (nb!=f->particle_size) {
    mcpl_internal_raise_io( es, "Errors encountered while attempting to write"
                            " particle data." );
    mcpl_internal_outfile_failed( f, es );
    return 0;
  }
  f->nparticles += 1;
  return 1;
}

MCPL_LOCAL void mcpl_internal_write_particle_buffer_to_file( mcpl_outfileinternal_t * f )
{
  mcpl_internal_write_particle_buffer_to_file_es( f, NULL );
}

void mcpl_add_particle_es( mcpl_outfile_t of, const mcpl_particle_t* particle,
                           mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if ( f->userdata_size ) {
    mcpl_internal_raise_runtime( es, "mcpl_add_particle called for a file with"
                                 " userdata (use mcpl_add_particle_with_userdata,"
                                 " with NULL for userdata with all bytes zero)" );
    return;
  }
  if ( mcpl_internal_serialise_particle_to_buffer( particle, NULL, f, es ) )
    mcpl_internal_write_particle_buffer_to_file_es( f, es );
}

void mcpl_add_particle(mcpl_outfile_t of,const mcpl_particle_t* particle)
{
  mcpl_add_particle_es( of, particle, NULL );
}

void mcpl_add_particle_with_userdata_es( mcpl_outfile_t of,
                                         const mcpl_particle_t* particle,
                                         const uint8_t * userdata,
                                         mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if ( userdata && !f->userdata_size ) {
    mcpl_internal_raise_runtime( es, "mcpl_add_particle_with_userdata called"
                                 " with userdata for a file without userdata"
                                 " (see mcpl_enable_userdata)" );
    return;
  }
  if ( mcpl_internal_serialise_particle_to_buffer( particle, userdata, f, es ) )
    mcpl_internal_write_particle_buffer_to_file_es( f, es );
}

void mcpl_add_particle_with_userdata(mcpl_outfile_t of,
                                     const mcpl_particle_t* particle,
                                     const uint8_t * userdata)
{
  mcpl_add_particle_with_userdata_es( of, particle, userdata, NULL );
}

MCPL_LOCAL int mcpl_update_nparticles_es( FILE* f, uint64_t n,
                                          mcpl_errstate_t * es )
{
  //Seek and update nparticles at correct location in header (returns 0 in
  //case of errors):
  const char * errmsg = ( "Errors encountered while attempting "
                          "to update number of particles in file." );
  int64_t savedpos = MCPL_FTELL(f);
  if (savedpos<0)
    return mcpl_internal_raise_io( es, errmsg );
  if (MCPL_FSEEK( f, MCPLIMP_NPARTICLES_POS ))
    return mcpl_internal_raise_io( es, errmsg );
  size_t nb = fwrite(&n, 1, sizeof(n), f);
  if (nb != sizeof(n))
    return mcpl_internal_raise_io( es, errmsg );
  if (MCPL_FSEEK( f, savedpos ))
    return mcpl_internal_raise_io( es, errmsg );
  return 1;
}

MCPL_LOCAL void mcpl_update_nparticles(FILE* f, uint64_t n)
{
  mcpl_update_nparticles_es( f, n, NULL );
}

mcpl_particle_t* mcpl_get_empty_particle_es( mcpl_outfile_t of,
                                             mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES(NULL);
  if (f->puser) {
    //Calling more than once. This could be innocent, or it could indicate
    //problems in multi-threaded user-code. Better disallow and give an error:
    mcpl_internal_raise_runtime( es, "mcpl_get_empty_particle must not be"
                                 " called more than once per output file" );
    return NULL;
  }
  f->puser = (mcpl_particle_t*)mcpl_internal_calloc_es(1,sizeof(mcpl_particle_t),es);
  return f->puser;
}

mcpl_particle_t* mcpl_get_empty_particle(mcpl_outfile_t of)
{
  return mcpl_get_empty_particle_es( of, NULL );
}

//Finishes and closes the file, and frees the file object (also in case of
//errors). Returns 0 in case of errors, in which case the file is left
//unfinished: with nparticles=0 in the header, so it can be recovered (if
//the header was written completely), unless the error happened when updating
//nparticles or closing the file.
MCPL_LOCAL int mcpl_internal_close_outfile_es( mcpl_outfileinternal_t * f,
                                               mcpl_errstate_t * es )
{
  int ok = 1;
  if ( f->failed ) {
    //Already failed (and reported), just leave the file unfinished:
    mcpl_internal_cleanup_outfile(f);
    return 1;
  }
  if ( f->header_notwritten && !mcpl_write_header_es( f, es ) )
    ok = 0;
  //Make sure all particles were actually written, before updating nparticles
  //in the header (otherwise files would not be recognised as unfinished):
  if ( ok && fflush(f->file) ) {
    mcpl_internal_raise_io( es, "Errors encountered while attempting to write"
                            " particle data." );
    ok = 0;
  }
  if ( ok && f->nparticles && !mcpl_update_nparticles_es( f->file,
                                                          f->nparticles, es ) )
    ok = 0;
  FILE * fh = f->file;
  f->file = NULL;
  if ( fclose(fh) && ok ) {
    mcpl_internal_raise_io( es, "Errors encountered while attempting to close"
                            " file." );
    ok = 0;
  }
  mcpl_internal_cleanup_outfile(f);
  return ok;
}

void mcpl_close_outfile_es( mcpl_outfile_t of, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  //Closing an invalid handle (internal NULL) does nothing:
  mcpl_outfileinternal_t * f = (mcpl_outfileinternal_t *)of.internal;
  if ( f )
    mcpl_internal_close_outfile_es( f, es );
}

void mcpl_close_outfile(mcpl_outfile_t of)
{
  mcpl_close_outfile_es( of, NULL );
}

void mcpl_close_outfile_unfinished_es( mcpl_outfile_t of, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  //Closing an invalid handle (internal NULL) does nothing:
  mcpl_outfileinternal_t * f = (mcpl_outfileinternal_t *)of.internal;
  if ( !f )
    return;
  //Write any buffered particles, but leave the header unchanged (the header is
  //not written if it was not already, and nparticles stays 0). Errors after
  //earlier errors are not reported again:
  if ( f->file && !f->failed ) {
    int ok = 1;
    if ( !f->header_notwritten && fflush(f->file) ) {
      mcpl_internal_raise_io( es, "Errors encountered while attempting to"
                              " write particle data." );
      ok = 0;
    }
    FILE * fh = f->file;
    f->file = NULL;
    if ( fclose(fh) && ok )
      mcpl_internal_raise_io( es, "Errors encountered while attempting to"
                              " close file." );
  }
  mcpl_internal_cleanup_outfile(f);
}

//Transfer metadata, returning 0 in case of errors:
MCPL_LOCAL int mcpl_internal_transfer_metadata_es( mcpl_file_t source,
                                                   mcpl_outfile_t target,
                                                   mcpl_errstate_t * es )
{
  //Note that MCPL format version 2 and 3 have the same meta-data in the header,
  //except of course the version number itself.

  if (mcpl_hdr_little_endian(source) != mcpl_platform_is_little_endian())
    return mcpl_internal_raise_runtime( es, "mcpl_transfer_metadata can only"
                                        " work on files with same endianness"
                                        " as current platform." );

#define MCPLIMP_TMD_CALL(x) do { x; if ( es && es->code ) return 0; } while (0)
  MCPLIMP_TMD_CALL(mcpl_hdr_set_srcname_es(target,mcpl_hdr_srcname(source),es));
  unsigned i;
  for (i = 0; i < mcpl_hdr_ncomments(source); ++i)
    MCPLIMP_TMD_CALL(mcpl_hdr_add_comment_es(target,mcpl_hdr_comment(source,i),es));
  const char** blobkeys = mcpl_hdr_blobkeys(source);
  if (blobkeys) {
    int nblobs = mcpl_hdr_nblobs(source);
    uint32_t ldata;
    const char * data;
    int ii;
    for (ii = 0; ii < nblobs; ++ii) {
      int res = mcpl_hdr_blob(source,blobkeys[ii],&ldata,&data);
      if (!res)
        return mcpl_internal_raise_runtime( es, "unexpected key problem in"
                                            " mcpl_transfer_metadata" );
      //(keys from files in format versions before 4 are copied even if they
      //do not follow the rules of version 4, as long as the new file does
      //not have userdata):
      MCPLIMP_TMD_CALL(mcpl_internal_hdr_add_data_es(target, blobkeys[ii],
                                                     ldata, data,
                                                     mcpl_hdr_version(source) < 4,
                                                     es));
    }
  }
  if (mcpl_hdr_has_userflags(source))
    MCPLIMP_TMD_CALL(mcpl_enable_userflags_es(target,es));
  if (mcpl_hdr_has_polarisation(source))
    MCPLIMP_TMD_CALL(mcpl_enable_polarisation_es(target,es));
  if (mcpl_hdr_has_doubleprec(source))
    MCPLIMP_TMD_CALL(mcpl_enable_doubleprec_es(target,es));
  int32_t updg = mcpl_hdr_universal_pdgcode(source);
  if (updg)
    MCPLIMP_TMD_CALL(mcpl_enable_universal_pdgcode_es(target,updg,es));
  double uw = mcpl_hdr_universal_weight(source);
  if (uw)
    MCPLIMP_TMD_CALL(mcpl_enable_universal_weight_es(target,uw,es));
  const char * udlayout = mcpl_hdr_userdata_layout(source);
  if (udlayout)
    MCPLIMP_TMD_CALL(mcpl_enable_userdata_es(target,udlayout,es));
#undef MCPLIMP_TMD_CALL
  return 1;
}

void mcpl_transfer_metadata_es( mcpl_file_t source, mcpl_outfile_t target,
                                mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  mcpl_outfile_t of = target;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if ( !source.internal ) {
    mcpl_internal_raise_runtime( es, "invalid file handle (NULL)" );
    return;
  }
  //Errors after some of the metadata was transferred leave the target file
  //unusable (to not produce files with partial metadata):
  if ( !mcpl_internal_transfer_metadata_es( source, target, es ) )
    mcpl_internal_outfile_failed( f, es );
}

void mcpl_transfer_metadata(mcpl_file_t source, mcpl_outfile_t target)
{
  mcpl_transfer_metadata_es( source, target, NULL );
}

int mcpl_closeandgzip_outfile_rc(mcpl_outfile_t of)
{
  mcpl_print("MCPL WARNING: Usage of function mcpl_closeandgzip_outfile_rc is obsolete as"
             " mcpl_closeandgzip_outfile now also returns the status. Please update your code"
             " to use mcpl_closeandgzip_outfile instead.\n");
  return mcpl_closeandgzip_outfile(of);
}

MCPL_LOCAL int mcpl_internal_do_gzip(const char *filename);

int mcpl_closeandgzip_outfile_es( mcpl_outfile_t of, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  //Closing an invalid handle (internal NULL) does nothing:
  mcpl_outfileinternal_t * f = (mcpl_outfileinternal_t *)of.internal;
  if ( !f )
    return 0;
  if ( f->failed ) {
    mcpl_internal_close_outfile_es( f, es );
    return 0;
  }
  char * filename = f->filename;
  f->filename = NULL;//prevent free when closing
  if ( !mcpl_internal_close_outfile_es( f, es ) ) {
    free(filename);
    return 0;
  }
  char * bn = mcpl_basename(filename);
  size_t n = 256 + strlen(bn);
  char * buf = mcpl_internal_malloc_es(n,es);
  if (!buf) {
    free(bn);
    free(filename);
    return 0;
  }
  snprintf(buf,n,"MCPL: Compressing file %s\n",bn);
  mcpl_print(buf);
  int ok = mcpl_internal_do_gzip(filename);
  if ( ok ) {
    snprintf(buf,n,"MCPL: Compressed file into %s.gz\n",bn);
    mcpl_print(buf);
  } else {
    snprintf(buf,n,"Problems encountered while compressing file %s (it was"
             " closed properly, so the uncompressed file might be fine)",bn);
    mcpl_internal_raise_io( es, buf );
  }
  free(buf);
  free(bn);
  free(filename);
  return ok;
}

int mcpl_closeandgzip_outfile(mcpl_outfile_t of)
{
  //Not via mcpl_closeandgzip_outfile_es, since failures to compress files are
  //not errors here (they are reported, and 0 is returned):
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
  char * userdata_layout;//NULL if no userdata
  uint32_t userdata_size;//included in particle_size
  int last_read_valid;//whether particle_buffer holds the last read particle
  char * particle_buffer;//particle_size bytes
  uint64_t first_comment_pos;
  uint32_t * repaired_statsum_icomments;
  int warned_nonfinite;
  //After errors in functions reading particles (or seeking), the file can only
  //be closed and all other such functions fail with the same error:
  int failed;
  mcpl_errstate_t failure;
  uint64_t hdr_entries_overhead;//estimated memory for comments and blobs
} mcpl_fileinternal_t;

#define MCPLIMP_FILEDECODE mcpl_fileinternal_t * f = (mcpl_fileinternal_t *)ff.internal; assert(f)

//For functions with an error state argument, also give an error (returning
//retval) for invalid handles:
#define MCPLIMP_FILEDECODE_ES(retval)                                   \
  mcpl_fileinternal_t * f = (mcpl_fileinternal_t *)ff.internal;         \
  if (!f) {                                                             \
    mcpl_internal_raise_runtime( es, "invalid file handle (NULL)" );    \
    return retval;                                                      \
  }

//Fail (returning retval) if an earlier error made the file unusable:
#define MCPLIMP_FILE_CHECKFAILED(retval)                                \
  if ( f->failed ) {                                                    \
    mcpl_internal_raise( es, f->failure.code, f->failure.msg );         \
    return retval;                                                      \
  }

//Remember error (which was just raised in es) to make the file unusable:
MCPL_LOCAL void mcpl_internal_file_failed( mcpl_fileinternal_t * f,
                                           const mcpl_errstate_t * es )
{
  if ( !es )
    return;//not reached (errors without error state end the program)
  f->failed = 1;
  f->failure = *es;
}

//Errors after failed (or short) reads. These are I/O errors if the stream
//reports one, otherwise the file simply ended prematurely or holds invalid
//data:
MCPL_LOCAL int mcpl_internal_readerr( mcpl_fileinternal_t * f,
                                      const char * msg,
                                      mcpl_errstate_t * es )
{
  int is_io_error;
  if ( f->filegz ) {
    int errnum = 0;
    gzerror( f->filegz, &errnum );
    is_io_error = ( errnum == Z_ERRNO );
  } else {
    is_io_error = ( f->file && ferror(f->file) );
  }
  return mcpl_internal_raise( es, ( is_io_error ? MCPL_ERROR_IO
                                    : MCPL_ERROR_RUNTIME ), msg );
}

//Errors after failed seeks (where a failed gzseek might also be due to
//truncated or invalid compressed data):
MCPL_LOCAL int mcpl_internal_seekerr( mcpl_fileinternal_t * f,
                                      mcpl_errstate_t * es,
                                      const char * msg )
{
  if ( f->filegz )
    return mcpl_internal_readerr( f, msg, es );
  return mcpl_internal_raise_io( es, msg );
}

//Reads a length n (uint32) followed by n bytes into a newly allocated buffer
//(*dest, with a terminating null-byte added), and adds the number of bytes
//consumed from the file to pos. Returns 0 in case of errors. The buffer grows
//while the data is read, so invalid lengths in corrupted files do not lead to
//huge allocations:
MCPL_LOCAL int mcpl_read_lengthdata( mcpl_fileinternal_t* f, uint32_t * n,
                                     char ** dest, int64_t * pos,
                                     const char * errmsg,
                                     mcpl_errstate_t * es )
{
  size_t nb;
  if (f->filegz)
    nb = gzread(f->filegz, n, sizeof(*n));
  else
    nb = fread(n, 1, sizeof(*n), f->file);
  if (nb!=sizeof(*n))
    return mcpl_internal_readerr( f, errmsg, es );
  if ( (uint64_t)*pos + sizeof(*n) + *n + f->hdr_entries_overhead
       > (uint64_t)MCPLIMP_MAX_HEADER_MEMORY )
    return mcpl_internal_raise_runtime( es, MCPLIMP_HEADER_TOO_LARGE_MSG );
  //The buffer starts with (at most) 1MB and its capacity is doubled when
  //needed, so the copying when growing it stays proportional to the size of
  //the data (realloc might copy the data every time, e.g. on Windows). The
  //data is read in chunks of at most 1MB:
  const size_t chunk = 1048576;
  const size_t ntotal = (size_t)*n + 1;//+1 for the terminating null-byte
  size_t capacity = ( ntotal < chunk ? ntotal : chunk );
  void * p = mcpl_internal_realloc_es( *dest, capacity, es );
  if (!p)
    return 0;
  *dest = (char*)p;
  size_t nread = 0;
  while ( nread < (size_t)*n ) {
    if ( nread + 1 == capacity ) {
      size_t newcapacity = 2 * capacity;
      if ( newcapacity > ntotal )
        newcapacity = ntotal;
      p = mcpl_internal_realloc_es( *dest, newcapacity, es );
      if (!p)
        return 0;
      *dest = (char*)p;
      capacity = newcapacity;
    }
    size_t ntoread = capacity - 1 - nread;
    if ( ntoread > chunk )
      ntoread = chunk;
    if (f->filegz)
      nb = gzread(f->filegz, *dest + nread, (unsigned)ntoread);
    else
      nb = fread(*dest + nread, 1, ntoread, f->file);
    if ( nb != ntoread )
      return mcpl_internal_readerr( f, errmsg, es );
    nread += ntoread;
  }
  (*dest)[nread] = '\0';
  *pos += sizeof(*n) + *n;
  return 1;
}

MCPL_LOCAL int mcpl_read_buffer( mcpl_fileinternal_t* f, uint32_t* n,
                                 char ** buf, int64_t * pos,
                                 const char * errmsg, mcpl_errstate_t * es )
{
  //Reads buffer and adds the number of bytes consumed from file to pos.
  //Returns 0 in case of errors.
  return mcpl_read_lengthdata( f, n, buf, pos, errmsg, es );
}

MCPL_LOCAL int mcpl_read_string( mcpl_fileinternal_t* f, char ** dest,
                                 int64_t * pos, const char* errmsg,
                                 mcpl_errstate_t * es )
{
  //Reads string and adds the number of bytes consumed from file to pos.
  //Returns 0 in case of errors.
  uint32_t n;
  if ( !mcpl_read_lengthdata( f, &n, dest, pos, errmsg, es ) )
    return 0;
  if ( strlen(*dest) != n )
    return mcpl_internal_raise_runtime( es, "encountered unexpected null-byte"
                                        " in string read from file" );
  return 1;
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
  if ( f->userdata_layout ) {
    free(f->userdata_layout);
    f->userdata_layout = NULL;
  }
  if ( f->particle_buffer ) {
    free(f->particle_buffer);
    f->particle_buffer = NULL;
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

//Raise error and return 0 from mcpl_internal_open_file:
#define MCPLIMP_OPENFAIL(code,msg) return mcpl_internal_raise( es, code, msg )

//Opens the file and reads the header into f, returning 0 in case of errors
//(after which the caller must clean up f):
MCPL_LOCAL int mcpl_internal_open_file( mcpl_fileinternal_t * f,
                                        const char * filename,
                                        int caller_is_mcpl_repair,
                                        int * repair_status,
                                        mcpl_errstate_t * es )
{
  //open file (with gzopen if filename ends with .gz):
  f->file = NULL;
  f->filegz = NULL;
  const char * lastdot = strrchr(filename, '.');
  if (lastdot && strcmp(lastdot, ".gz") == 0) {
    f->filegz = mcpl_gzopen( filename, "rb" );
    if (!f->filegz)
      MCPLIMP_OPENFAIL(MCPL_ERROR_IO,"Unable to open file!");
  } else {
    f->file = mcpl_internal_fopen(filename,"rb");
    if (!f->file)
      MCPLIMP_OPENFAIL(MCPL_ERROR_IO,"Unable to open file!");
  }

  //First read and check magic word, format version and endianness.
  unsigned char start[8];// = {'M','C','P','L','0','0','0','L'};
  size_t nb;
  if (f->filegz)
    nb = gzread(f->filegz, start, sizeof(start));
  else
    nb = fread(start, 1, sizeof(start), f->file);
  if (nb>=4&&nb<=sizeof(start)
      &&(start[0]!='M'||start[1]!='C'||start[2]!='P'||start[3]!='L'))
    MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"File is not an MCPL file!");
  if (nb!=sizeof(start)) {
    mcpl_internal_readerr( f, "Error while reading first bytes of file!", es );
    return 0;
  }
  f->format_version = (start[4]-'0')*100 + (start[5]-'0')*10 + (start[6]-'0');
  if (f->format_version<2||f->format_version>4)
    MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"File is in an unsupported MCPL version!");
  f->is_little_endian = mcpl_platform_is_little_endian();
  if (start[7]!=(f->is_little_endian?'L':'B')) {
    if (start[7]=='L'||start[7]=='B')
      MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"Endian-ness of current platform is different than the one used to write the file.");
    else
      MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"Unexpected value in endianness field!");
  }
  int64_t current_pos = sizeof(start);

  //proceed reading header, knowing we have a consistent version and endian-ness.
  const char * errmsg = "Errors encountered while attempting to read header";

  uint64_t numpart;
  if (f->filegz)
    nb = gzread(f->filegz, &numpart, sizeof(numpart));
  else
    nb = fread(&numpart, 1, sizeof(numpart), f->file);
  if (nb!=sizeof(numpart)) {
    mcpl_internal_readerr( f, errmsg, es );
    return 0;
  }
  current_pos += nb;
  f->nparticles = numpart;

  uint32_t arr[8];
  MCPL_STATIC_ASSERT(sizeof(arr)==32);
  if (f->filegz)
    nb = gzread(f->filegz, arr, sizeof(arr));
  else
    nb=fread(arr, 1, sizeof(arr), f->file);
  if (nb!=sizeof(arr)) {
    mcpl_internal_readerr( f, errmsg, es );
    return 0;
  }
  current_pos += nb;

  //The numbers of comments and blobs are counted while reading them below (so
  //invalid numbers in corrupted files do not lead to huge allocations):
  const uint32_t ncomments_hdr = arr[0];
  const uint32_t nblobs_hdr = arr[1];
  f->ncomments = 0;
  f->nblobs = 0;
  f->hdr_entries_overhead = ( (uint64_t)ncomments_hdr + nblobs_hdr )
    * MCPLIMP_HEADER_ENTRY_OVERHEAD;
  if ( (uint64_t)current_pos + f->hdr_entries_overhead
       > (uint64_t)MCPLIMP_MAX_HEADER_MEMORY )
    MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,MCPLIMP_HEADER_TOO_LARGE_MSG);
  //The flags in the header must have exactly the values of the format: 0x1 or
  //0x0 (for userflags, polarisation, single precision and universal weight).
  //In format version 4, the userflags field also holds 0x2 if the particles
  //have userdata (and the header has a userdata layout), so files in version
  //4 without userdata are identical to files in version 3 except for the
  //version number:
  if ( arr[2] > ( f->format_version >= 4 ? 3u : 1u ) )
    MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"unexpected value of userflags field");
  if ( arr[3] > 1 )
    MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"unexpected value of polarisation"
                     " field");
  if ( arr[4] > 1 )
    MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"unexpected value of precision field");
  if ( arr[7] > 1 )
    MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"unexpected value of universal weight"
                     " field");
  const int has_userdata = ( arr[2] & 0x2 ) ? 1 : 0;
  f->opt_userflags = arr[2] & 0x1;
  f->opt_polarisation = arr[3];
  f->opt_singleprec = arr[4];
  memcpy(&f->opt_universalpdgcode, &arr[5], sizeof(int32_t));
  f->particle_size = arr[6];//Checked below.

  if (arr[7]) {
    //file has universal weight
    if (f->filegz)
      nb = gzread(f->filegz, (void*)&(f->opt_universalweight), sizeof(f->opt_universalweight));
    else
      nb=fread((void*)&(f->opt_universalweight), 1, sizeof(f->opt_universalweight), f->file);
    if (nb!=sizeof(f->opt_universalweight)) {
      mcpl_internal_readerr( f, errmsg, es );
      return 0;
    }
    current_pos += nb;
    //(must be positive and finite, as when writing files):
    if ( !( f->opt_universalweight > 0.0 ) || isinf(f->opt_universalweight) )
      MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"invalid universal weight");
  }

  if ( has_userdata ) {
    //Userdata layout (only in version 4, and only with userdata):
    if (!mcpl_read_string(f,&f->userdata_layout,&current_pos,errmsg,es))
      return 0;
    f->userdata_size = mcpl_internal_udlayout_validate( f->userdata_layout, es );
    if (!f->userdata_size)
      return 0;
  }
  {
    //The particle size in the header must be consistent with the size of the
    //fields:
    unsigned fp = f->opt_singleprec ? sizeof(float) : sizeof(double);
    uint64_t expected = 7*fp + ( f->opt_polarisation ? 3*fp : 0 )
      + ( f->opt_universalpdgcode ? 0 : sizeof(int32_t) )
      + ( arr[7] ? 0 : fp )
      + ( f->opt_userflags ? sizeof(uint32_t) : 0 )
      + f->userdata_size;
    if ( f->particle_size != expected )
      MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"unexpected particle size");
  }
  f->particle_buffer = (char*)mcpl_internal_malloc_es( f->particle_size
                                                       ? f->particle_size : 1,
                                                       es );
  if (!f->particle_buffer)
    return 0;

  f->opt_signature = 0
    + 1 * f->opt_singleprec
    + 2 * f->opt_polarisation
    + 4 * (f->opt_universalpdgcode?1:0)
    + 8 * (f->opt_universalweight?1:0)
    + 16 * f->opt_userflags
    + 32 * (f->userdata_size?1:0);

  //Then some strings:
  if (!mcpl_read_string(f,&f->hdr_srcprogname,&current_pos,errmsg,es))
    return 0;
  f->first_comment_pos = current_pos;

  //Validate stat: entries to get error on load rather than later on use:
  int unknown_stat_syntax = 0;
  uint32_t n_statsum_comments = 0;
  uint32_t capacity = 0;
  for (uint32_t i = 0; i < ncomments_hdr; ++i) {
    uint32_t newcap = mcpl_internal_grow_capacity( i, capacity, ncomments_hdr );
    if ( newcap != capacity ) {
      void * p = mcpl_internal_realloc_es( f->comments, newcap*sizeof(char*), es );
      if (!p)
        return 0;
      f->comments = (char**)p;
      capacity = newcap;
    }
    f->comments[i] = NULL;
    f->ncomments = i + 1;//(entry is now owned by f)
    if (!mcpl_read_string(f,&(f->comments[i]),&current_pos,errmsg,es))
      return 0;
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
      mcpl_internal_calloc_es( n_statsum_comments,
                               sizeof(mcpl_internal_statsum_t), es );
    if (!ssi_buf)
      return 0;
    mcpl_internal_statsum_t * ssi_buf_next = ssi_buf;
    for (uint32_t i = 0; i < f->ncomments; ++i) {
      if ( !MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
        continue;
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( f->comments[i],
                                                        ssi_buf_next, es ) ) {
        free(ssi_buf);
        return 0;
      }
      for ( mcpl_internal_statsum_t * it = ssi_buf;
            it < ssi_buf_next; ++it ) {
        if ( strcmp( it->key, ssi_buf_next->key ) == 0 ) {
          //emit error!
          char buf[MCPL_STATSUMKEY_MAXLENGTH+256];
          snprintf(buf,sizeof(buf),
                   "Duplicate stat:sum: key. The key \"%s\" appears"
                   " more than once in the file.",it->key);
          free(ssi_buf);
          MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,buf);
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
  capacity = 0;
  for (uint32_t i = 0; i < nblobs_hdr; ++i) {
    uint32_t newcap = mcpl_internal_grow_capacity( i, capacity, nblobs_hdr );
    if ( newcap != capacity ) {
      void * p = mcpl_internal_realloc_es( f->blobkeys, newcap*sizeof(char*), es );
      if (!p)
        return 0;
      f->blobkeys = (char**)p;
      p = mcpl_internal_realloc_es( f->blobs, newcap*sizeof(char*), es );
      if (!p)
        return 0;
      f->blobs = (char**)p;
      p = mcpl_internal_realloc_es( f->bloblengths, newcap*sizeof(uint32_t), es );
      if (!p)
        return 0;
      f->bloblengths = (uint32_t*)p;
      capacity = newcap;
    }
    f->blobkeys[i] = NULL;
    f->blobs[i] = NULL;
    f->bloblengths[i] = 0;
    f->nblobs = i + 1;//(entries are now owned by f)
    if (!mcpl_read_string(f,&(f->blobkeys[i]),&current_pos,errmsg,es))
      return 0;
    if ( f->format_version >= 4 ) {
      const char * keyproblem = mcpl_internal_blobkey_problem( f->blobkeys[i] );
      if ( keyproblem ) {
        char buf[256];
        snprintf(buf,sizeof(buf),"File has an invalid blob key (%s).",
                 keyproblem);
        MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,buf);
      }
    }
  }
  for (uint32_t i =0; i < f->nblobs; ++i)
    if (!mcpl_read_buffer(f, &(f->bloblengths[i]), &(f->blobs[i]), &current_pos, errmsg, es))
      return 0;
  f->particle = (mcpl_particle_t*)mcpl_internal_calloc_es(1,sizeof(mcpl_particle_t),es);
  if (!f->particle)
    return 0;

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
            MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"Input file appears to not have been closed properly"
                             " and data recovery is disabled for gzipped files.");
          }
        }
      } else {
        if (!caller_is_mcpl_repair)
          MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"logic error (!caller_is_mcpl_repair)");
        *repair_status = 2;//file brokenness can not be determined since gzip.
      }
      if (!mcpl_gzseek( f->filegz, f->first_particle_pos ) )
        MCPLIMP_OPENFAIL(MCPL_ERROR_IO,"Unexpected issue skipping to start of empty gzipped file");
    } else {
      //SEEK_END is not guaranteed to always work, so we fail our recovery
      //attempt silently:
      if (f->file && !MCPL_FSEEK_END( f->file )) {
        int64_t endpos = MCPL_FTELL(f->file);
        if (endpos >= (int64_t)f->first_particle_pos) {
          uint64_t ndata = endpos - f->first_particle_pos;
          uint64_t np = ndata / f->particle_size;
          int has_partial_particle = ( ndata % f->particle_size ) != 0;
          if ( f->nparticles != np || has_partial_particle ) {
            if ( f->nparticles > 0 && np > f->nparticles ) {
              //should really not happen unless file was corrupted or file was
              //first closed properly and then something was appended to it.
              MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"Input file has invalid combination of meta-data & filesize.");
            }
            if (caller_is_mcpl_repair) {
              *repair_status = 3;//file broken and should be able to repair
            } else {
              if (f->nparticles!=0)
                MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"unexpected nparticles value");
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
              if ( !mcpl_internal_statsum_parse_or_emit_err_es( f->comments[i],
                                                                &sc, es ) )
                return 0;
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
                    = (uint32_t *)mcpl_internal_calloc_es(f->ncomments+1,
                                                          sizeof(uint32_t),
                                                          es);
                  if (!f->repaired_statsum_icomments)
                    return 0;
                  f->repaired_statsum_icomments[0] = 0;
                }
                uint32_t ir = ((f->repaired_statsum_icomments[0])++) + 1;
                f->repaired_statsum_icomments[ir] = i;
              }
              char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
              mcpl_internal_encodestatsum( sc.key, -1.0, new_comment );
              size_t nn = strlen(f->comments[i]);
              if ( nn != strlen(new_comment) )
                MCPLIMP_OPENFAIL(MCPL_ERROR_RUNTIME,"inconsistent length of stat:sum: comment");
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

  return 1;
}
#undef MCPLIMP_OPENFAIL

MCPL_LOCAL mcpl_file_t mcpl_actual_open_file( const char * filename,
                                              int * repair_status,
                                              mcpl_errstate_t * es )
{
  int caller_is_mcpl_repair = *repair_status;
  *repair_status = 0;//file not broken

  mcpl_file_t out;
  out.internal = NULL;

  if (!filename) {
    mcpl_internal_raise_runtime( es, "mcpl_open_file called with null string" );
    return out;
  }

  if ( !mcpl_platform_compatibility_check_es( es ) )
    return out;

  mcpl_fileinternal_t * f
    = (mcpl_fileinternal_t*)mcpl_internal_calloc_es(1,sizeof(mcpl_fileinternal_t),es);
  if (!f)
    return out;

  if ( !mcpl_internal_open_file( f, filename, caller_is_mcpl_repair,
                                 repair_status, es ) ) {
    mcpl_internal_cleanup_file(f);
    return out;
  }
  out.internal = f;
  return out;
}

mcpl_file_t mcpl_open_file_es( const char * filename, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  int repair_status = 0;
  return mcpl_actual_open_file(filename,&repair_status,es);
}

mcpl_file_t mcpl_open_file(const char * filename)
{
  return mcpl_open_file_es( filename, NULL );
}

MCPL_LOCAL int mcpl_internal_updatestatsum_es( FILE * f,
                                               mcpl_internal_statsuminfo_t*sc,
                                               const char * new_comment,
                                               mcpl_errstate_t * es )
{
  //Seek and update comment at correct location in header (returns 0 in case
  //of errors).

  const char * errmsg = ( "Errors encountered while attempting "
                          "to update stat:sum: header in file." );
  if (!f||!sc||!new_comment)
    return mcpl_internal_raise_io( es, errmsg );

  uint32_t n = sc->writtenstrlen;
  if ( n != strlen(new_comment) )
    return mcpl_internal_raise_runtime( es, "preallocated space for stat:sum:"
                                        " update does not fit (2)" );

  int64_t savedpos = MCPL_FTELL(f);
  if (savedpos<0)
    return mcpl_internal_raise_io( es, errmsg );
  uint64_t updatepos = sc->writtenpos;
  updatepos += sizeof(uint32_t);//skip strlen data (no, we can't read it since
                                //the file is in output mode)
  if (MCPL_FSEEK( f, updatepos ))
    return mcpl_internal_raise_io( es, errmsg );
  size_t nb = fwrite( new_comment, 1, n, f);
  if ( nb != n )
    return mcpl_internal_raise_io( es, errmsg );
  if (MCPL_FSEEK( f, savedpos ))
    return mcpl_internal_raise_io( es, errmsg );
  return 1;
}

MCPL_LOCAL void mcpl_internal_updatestatsum( FILE * f,
                                             mcpl_internal_statsuminfo_t*sc,
                                             const char * new_comment )
{
  mcpl_internal_updatestatsum_es( f, sc, new_comment, NULL );
}

#ifdef _WIN32
// for _setmode, O_BINARY, _chsize_s and _fileno
#  include <fcntl.h>
#  include <io.h>
#else
// for write(..), unlink(), ftruncate and fileno
#  include "unistd.h"
#endif

MCPL_LOCAL int mcpl_internal_truncate_file( FILE * fh, uint64_t size )
{
  if ( fflush(fh) )
    return 0;
#ifdef _WIN32
  return _chsize_s( _fileno(fh), (__int64)size ) == 0;
#else
  return ftruncate( fileno(fh), (off_t)size ) == 0;
#endif
}

void mcpl_repair_es( const char * filename, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  int repair_status = 1;
  mcpl_file_t f = mcpl_actual_open_file(filename,&repair_status,es);
  if ( !f.internal )
    return;
  uint64_t nparticles = mcpl_hdr_nparticles(f);
  mcpl_fileinternal_t * fi = (mcpl_fileinternal_t *)f.internal;
  uint64_t repaired_filesize = ( fi->first_particle_pos
                                 + nparticles * fi->particle_size );

  //Collect information about any stat:sum: entries that we must modify during
  //the repair (i.e. we must mark then as unavailable by setting them to -1).
  mcpl_internal_statsuminfo_t * ssi = NULL;
  uint32_t nssi_to_repair = 0;
  const char * errmsg = NULL;
  if ( fi->repaired_statsum_icomments ) {
    nssi_to_repair = fi->repaired_statsum_icomments[0];
    ssi = (mcpl_internal_statsuminfo_t *)
      mcpl_internal_calloc_es( nssi_to_repair,
                               sizeof(mcpl_internal_statsuminfo_t), es );
    if ( !ssi ) {
      mcpl_close_file(f);
      return;
    }
    uint32_t nssi_repair_check = 0;
    uint64_t next_comment_pos = fi->first_comment_pos;
    uint32_t* icmt_next_to_repair = &fi->repaired_statsum_icomments[1];
    for (uint32_t i = 0; i < fi->ncomments; ++i) {
      const char * comment = fi->comments[i];
      size_t lcomment = strlen(comment);
      uint64_t writtenpos = next_comment_pos;
      next_comment_pos += ( lcomment + sizeof(uint32_t) );
      if ( nssi_repair_check < nssi_to_repair && i == *icmt_next_to_repair ) {
        ++icmt_next_to_repair;
        mcpl_internal_statsum_t sc;
        mcpl_internal_statsumparse( comment, &sc );
        if ( sc.errmsg || !(sc.value==-1.0) ) {
          //value should already have been repaired to be -1 in the in-mem
          //comment string.
          errmsg = "unexpected stat:sum value in file";
          break;
        }
        mcpl_internal_statsuminfo_t * s = &ssi[nssi_repair_check++];
        memcpy( s->key, sc.key, strlen(sc.key) + 1 );
        s->writtenstrlen = (uint32_t)lcomment;
        s->writtenpos = writtenpos;
      }
    }
    if ( !errmsg && nssi_to_repair != nssi_repair_check )
      errmsg = "logic error during stat:sum repair";
  }

  mcpl_close_file(f);
  fi = NULL;

  if (!errmsg) {
    if (repair_status==0)
      errmsg = "File does not appear to be broken.";
    else if (repair_status==1)
      errmsg = "Input file is indeed broken, but must be gunzipped before it can be repaired.";
    else if (repair_status==2)
      errmsg = "File must be gunzipped before it can be checked and possibly repaired.";
  }
  if (errmsg) {
    free(ssi);
    mcpl_internal_raise_runtime( es, errmsg );
    return;
  }

  //Ok, we should repair the file by updating nparticles in the header, and also
  //possibly by setting any stat:sum comment entries to the value -1 since they
  //are not trustworthy. We update nparticles last, since after that the file
  //will appear as already having been repaired (so errors before that leave the
  //file in need of repair):

  FILE * fh = mcpl_internal_fopen(filename,"r+b");
  if (!fh) {
    free(ssi);
    mcpl_internal_raise_io( es, "Unable to open file in update mode!" );
    return;
  }

  int ok = 1;
  for ( uint32_t i = 0; ok && i < nssi_to_repair; ++i ) {
    char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
    ok = ( mcpl_internal_encodestatsum_es( ssi[i].key, -1.0, new_comment, es )
           && mcpl_internal_updatestatsum_es( fh, &ssi[i], new_comment, es ) );
    ssi[i].value = -1.0;
  }
  free(ssi);

  //Remove any partially written particle at the end:
  if ( ok && !mcpl_internal_truncate_file( fh, repaired_filesize ) )
    ok = mcpl_internal_raise_io( es, "Unable to remove incomplete particle"
                                 " data at end of file." );

  if ( ok )
    ok = mcpl_update_nparticles_es(fh, nparticles, es);
  if ( fclose(fh) && ok )
    ok = mcpl_internal_raise_io( es, "Errors encountered while attempting to"
                                 " close file." );
  if ( !ok )
    return;

  //Verify that we fixed it:
  repair_status = 1;
  f = mcpl_actual_open_file( filename, &repair_status, es );
  if ( !f.internal )
    return;
  uint64_t nparticles2 = mcpl_hdr_nparticles(f);
  mcpl_close_file(f);
  if ( repair_status == 0 && nparticles == nparticles2 ) {
    char buf[256];
    snprintf(buf,sizeof(buf),"MCPL: Successfully repaired file with %"
             PRIu64 " particles.\n",nparticles);
    mcpl_print(buf);
  } else {
    mcpl_internal_raise_runtime( es, "Something went wrong while attempting"
                                 " to repair file." );
  }
}

void mcpl_repair(const char * filename)
{
  mcpl_repair_es( filename, NULL );
}

void mcpl_close_file(mcpl_file_t ff)
{
  //Closing an invalid handle (internal NULL) does nothing:
  mcpl_internal_cleanup_file( (mcpl_fileinternal_t *)ff.internal );
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

const char * mcpl_hdr_comment_es( mcpl_file_t ff, unsigned i,
                                  mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_FILEDECODE_ES(NULL);
  if (i>=f->ncomments) {
    mcpl_internal_raise_runtime( es, "Invalid comment requested (index out"
                                 " of bounds)" );
    return NULL;
  }
  return f->comments[i];
}

const char * mcpl_hdr_comment(mcpl_file_t ff, unsigned i)
{
  return mcpl_hdr_comment_es( ff, i, NULL );
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

const mcpl_particle_t* mcpl_read_es( mcpl_file_t ff, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_FILEDECODE_ES(NULL);
  MCPLIMP_FILE_CHECKFAILED(NULL);
  f->last_read_valid = 0;
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
  if (nb!=lbuf) {
    mcpl_internal_readerr( f, "Errors encountered while attempting to read"
                           " particle data.", es );
    mcpl_internal_file_failed( f, es );
    return NULL;
  }

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
    if (!f->opt_universalweight) {
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
    if (!f->opt_universalweight) {
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
    ibuf += sizeof(uint32_t);
  } else {
    p->userflags = 0;
  }
  assert(ibuf+f->userdata_size==lbuf);
  (void)ibuf;
  f->last_read_valid = 1;

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

  //NaN or infinite values are not allowed in MCPL files, but files might
  //still have them, so warn (once per file):
  if ( !f->warned_nonfinite
       && mcpl_internal_nonfinite_field( p, f->opt_polarisation, 1 ) ) {
    f->warned_nonfinite = 1;
    char buf[256];
    snprintf(buf,sizeof(buf),"MCPL WARNING: File contains particles with NaN"
             " or infinite values (first one found at index %llu). They can"
             " not be added to other MCPL files.\n",
             (unsigned long long)(f->current_particle_idx-1));
    mcpl_print(buf);
  }
  return p;
}

const mcpl_particle_t* mcpl_read(mcpl_file_t ff)
{
  return mcpl_read_es( ff, NULL );
}

const char * mcpl_hdr_userdata_layout(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->userdata_layout;
}

uint32_t mcpl_hdr_userdata_size(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  return f->userdata_size;
}

const uint8_t * mcpl_last_read_userdata(mcpl_file_t ff)
{
  MCPLIMP_FILEDECODE;
  if ( !f->userdata_size || !f->last_read_valid )
    return NULL;
  return (const uint8_t*)( f->particle_buffer
                           + ( f->particle_size - f->userdata_size ) );
}

const mcpl_particle_t* mcpl_read_with_userdata_es( mcpl_file_t ff,
                                                   const uint8_t ** userdata,
                                                   mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  if (userdata)
    *userdata = NULL;
  const mcpl_particle_t* p = mcpl_read_es( ff, es );
  if ( p && userdata )
    *userdata = mcpl_last_read_userdata(ff);
  return p;
}

const mcpl_particle_t* mcpl_read_with_userdata(mcpl_file_t ff,
                                               const uint8_t ** userdata)
{
  return mcpl_read_with_userdata_es( ff, userdata, NULL );
}

int mcpl_skipforward_es( mcpl_file_t ff, uint64_t n, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_FILEDECODE_ES(0);
  MCPLIMP_FILE_CHECKFAILED(0);
  f->last_read_valid = 0;
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
    if (error) {
      mcpl_internal_seekerr( f, es, "Errors encountered while skipping in"
                              " particle list" );
      mcpl_internal_file_failed( f, es );
      return 0;
    }
  }
  return notEOF;
}

int mcpl_skipforward(mcpl_file_t ff,uint64_t n)
{
  return mcpl_skipforward_es( ff, n, NULL );
}

int mcpl_rewind_es( mcpl_file_t ff, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_FILEDECODE_ES(0);
  MCPLIMP_FILE_CHECKFAILED(0);
  f->last_read_valid = 0;
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
    if (error) {
      mcpl_internal_seekerr( f, es, "Errors encountered while rewinding"
                              " particle list" );
      mcpl_internal_file_failed( f, es );
      return 0;
    }
  }
  return notEOF;
}

int mcpl_rewind(mcpl_file_t ff)
{
  return mcpl_rewind_es( ff, NULL );
}

int mcpl_seek_es( mcpl_file_t ff, uint64_t ipos, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_FILEDECODE_ES(0);
  MCPLIMP_FILE_CHECKFAILED(0);
  f->last_read_valid = 0;
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
    if (error) {
      mcpl_internal_seekerr( f, es, "Errors encountered while seeking in"
                              " particle list" );
      mcpl_internal_file_failed( f, es );
      return 0;
    }
  }
  return notEOF;
}

int mcpl_seek(mcpl_file_t ff,uint64_t ipos)
{
  return mcpl_seek_es( ff, ipos, NULL );
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

void mcpl_transfer_last_read_particle_es( mcpl_file_t source,
                                          mcpl_outfile_t target,
                                          mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  mcpl_outfile_t of = target;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  mcpl_outfileinternal_t * ft = f;
  mcpl_fileinternal_t * fs = (mcpl_fileinternal_t *)source.internal;
  if (!fs) {
    mcpl_internal_raise_runtime( es, "invalid file handle (NULL)" );
    return;
  }
  if ( fs->failed ) {
    mcpl_internal_raise( es, fs->failure.code, fs->failure.msg );
    return;
  }

  if ( fs->current_particle_idx==0 && fs->particle->weight==0.0 && fs->particle->pdgcode==0 ) {
    mcpl_internal_raise_runtime( es, "mcpl_transfer_last_read_particle called with source file in invalid state"
               " (did you forget to first call mcpl_read() on the source file before calling this function?)" );
    return;
  }

  //Sanity checks for universal fields here (but not in mcpl_add_particle since users are allowed to create files by setting just the universal fields):
  if ( ft->opt_universalpdgcode && fs->particle->pdgcode != ft->opt_universalpdgcode) {
    char buf[256];
    snprintf(buf,sizeof(buf),"mcpl_transfer_last_read_particle asked to"
             " transfer particle with pdgcode %li into a file with"
             " universal pdgcode of %li",
             (long)fs->particle->pdgcode,
             (long)ft->opt_universalpdgcode);
    mcpl_internal_raise_runtime( es, buf );
    return;
  }
  if ( ft->opt_universalweight && fs->particle->weight != ft->opt_universalweight) {
    char buf[256];
    snprintf(buf,sizeof(buf),"mcpl_transfer_last_read_particle asked to"
             " transfer particle with weight %g into a file with universal"
             " weight of %g",
             fs->particle->weight,
             ft->opt_universalweight );
    mcpl_internal_raise_runtime( es, buf );
    return;
  }
  //NB: We don't sanity check that polarisation/userflags/userdata are enabled
  //if present in the input particle, since it is a valid use-case to use this
  //function to discard such info.

  //Userdata to transfer (the target can only have userdata if the source has
  //the same layout):
  const uint8_t * userdata = NULL;
  if ( ft->userdata_size && !fs->userdata_size ) {
    mcpl_internal_raise_runtime( es, "mcpl_transfer_last_read_particle asked to transfer"
               " particle without userdata into a file with userdata" );
    return;
  }
  if ( ft->userdata_size ) {
    if ( strcmp( ft->userdata_layout, fs->userdata_layout ) != 0 ) {
      mcpl_internal_raise_runtime( es, "mcpl_transfer_last_read_particle asked to transfer"
                 " particle into a file with a different userdata layout" );
      return;
    }
    userdata = (const uint8_t*)( fs->particle_buffer
                                 + ( fs->particle_size - fs->userdata_size ) );
  }

  //NaN or infinite values are not allowed (the source file might have them,
  //and they might otherwise be transferred directly):
  const char * nonfinite = mcpl_internal_nonfinite_field( fs->particle,
                                                          ft->opt_polarisation,
                                                          !ft->opt_universalweight );
  if ( nonfinite ) {
    char buf[160];
    snprintf(buf,sizeof(buf),"mcpl_transfer_last_read_particle asked to"
             " transfer particle with NaN or infinite %s",nonfinite);
    mcpl_internal_raise_runtime( es, buf );
    return;
  }

  if ( fs->format_version == 2 || ( fs->opt_singleprec && !ft->opt_singleprec ) ) {
    //source file is in old format with different unit vector packing, or the
    //floating point precision is increasing. In these scenarious we can not
    //reuse the 3 floats representing packed direction+ekin but must proceed via
    //a full unpacking+repacking.
    mcpl_add_particle_with_userdata_es(target,fs->particle,userdata,es);
    return;
  }

  if ( ft->opt_signature == fs->opt_signature ) {
    //Particle data is encoded in exactly the same manner in src and target (a
    //common scenario for many merge or extraction scenarios) -> simply transfer
    //the bytes and be done with it:
    if ( fs->particle_size!=ft->particle_size ) {
      mcpl_internal_raise_runtime( es, "unexpectedly inconsistent particle"
                                   " sizes" );
      return;
    }
    memcpy(ft->particle_buffer,fs->particle_buffer,fs->particle_size);
    mcpl_internal_write_particle_buffer_to_file_es(ft,es);
    return;
  }

  //The hard way - first serialise the source particle into the output buffer:
  if ( !mcpl_internal_serialise_particle_to_buffer( fs->particle, userdata,
                                                    ft, es ) )
    return;

  //If possible, override the 3 FP representing packed ekin+dir from the packing
  //in the source, thus avoiding potentially lossy unpacking+packing:
  size_t fpsize_target = ft->opt_singleprec ? sizeof(float) : sizeof(double);
  size_t fpsize_src = fs->opt_singleprec ? sizeof(float) : sizeof(double);
  size_t idx_packekindir_target = (ft->opt_polarisation ? 6 : 3) * fpsize_target;
  size_t idx_packekindir_src = (fs->opt_polarisation ? 6 : 3) * fpsize_src;
  if (fs->opt_singleprec == ft->opt_singleprec) {
    memcpy( &(ft->particle_buffer[idx_packekindir_target]),
            &(fs->particle_buffer[idx_packekindir_src]),
            fpsize_target * 3);
  } else if ( ft->opt_singleprec && !fs->opt_singleprec ) {
    //For the case of double precision -> single precision, we can simply
    //perform a narrowing conversion:
    for (unsigned i = 0; i < 3; ++i) {
      double v = mcpl_internal_rd_double( &(fs->particle_buffer[idx_packekindir_src + i * sizeof(double)]) );
      mcpl_internal_wr_float( &(ft->particle_buffer[idx_packekindir_target + i * sizeof(float)]), (float)v );
    }
  }

  mcpl_internal_write_particle_buffer_to_file_es(ft,es);
}

void mcpl_transfer_last_read_particle(mcpl_file_t source, mcpl_outfile_t target)
{
  mcpl_transfer_last_read_particle_es( source, target, NULL );
}

//Destination of the output of the dump functions (the print handler if fct is
//NULL):
typedef struct {
  MCPL_CHARCTXTOVOID_FCT fct;
  void * ctx;
} mcpl_internal_output_t;

MCPL_LOCAL void mcpl_internal_output( const mcpl_internal_output_t * out,
                                      const char * msg )
{
  if ( out->fct )
    out->fct( msg, out->ctx );
  else
    mcpl_print( msg );
}

//Dump the header (returns 0 in case of errors):
MCPL_LOCAL int mcpl_internal_dump_header( mcpl_file_t f,
                                          const mcpl_internal_output_t * out,
                                          mcpl_errstate_t * es )
{
  char buf[4096];
  mcpl_internal_output(out,"\n  Basic info\n");
  snprintf(buf,sizeof(buf),
           "    Format             : MCPL-%i\n",mcpl_hdr_version(f));
  mcpl_internal_output(out,buf);
  snprintf(buf,sizeof(buf),
           "    No. of particles   : %" PRIu64 "\n",mcpl_hdr_nparticles(f) );
  mcpl_internal_output(out,buf);
  snprintf(buf,sizeof(buf),
           "    Header storage     : %" PRIu64 " bytes\n",
           mcpl_hdr_header_size(f));
  mcpl_internal_output(out,buf);
  snprintf(buf,sizeof(buf),
           "    Data storage       : %" PRIu64 " bytes\n",
           mcpl_hdr_nparticles(f)*mcpl_hdr_particle_size(f));
  mcpl_internal_output(out,buf);
  mcpl_internal_output(out,"\n  Custom meta data\n");

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
    flexbuf = mcpl_internal_malloc_es( lflexbuf, es );
    if (!flexbuf)
      return 0;
  }

  snprintf(flexbuf,lflexbuf,
           "    Source             : \"%s\"\n",mcpl_hdr_srcname(f));
  mcpl_internal_output(out,flexbuf);
  snprintf(buf,sizeof(buf),
           "    Number of comments : %i\n",ncomments);
  mcpl_internal_output(out,buf);
  unsigned ic;
  for (ic = 0; ic < ncomments; ++ic) {
    snprintf(flexbuf,lflexbuf,
             "          -> comment %i : \"%s\"\n",ic,mcpl_hdr_comment(f,ic));
    mcpl_internal_output(out,flexbuf);
  }
  snprintf(buf,sizeof(buf),
           "    Number of blobs    : %i\n",nblobs);
  mcpl_internal_output(out,buf);
  for (uint32_t ib = 0; ib < nblobs; ++ib) {
    const char * data;
    uint32_t ldata;
    int ok = mcpl_hdr_blob(f, blobkeys[ib], &ldata, &data);
    if (!ok) {
      if ( flexbuf != buf )
        free(flexbuf);
      return mcpl_internal_raise_runtime( es, "Unexpected blob access error" );
    }
    snprintf(flexbuf,lflexbuf,
             "          -> %lu bytes of data with key \"%s\"\n",
             (unsigned long)ldata,blobkeys[ib]);
    mcpl_internal_output(out,flexbuf);
  }

  if ( flexbuf != buf )
    free(flexbuf);

  mcpl_internal_output(out,"\n  Particle data format\n");
  snprintf(buf,sizeof(buf),
           "    User flags         : %s\n",
           (mcpl_hdr_has_userflags(f)?"yes":"no") );
  mcpl_internal_output(out,buf);
  snprintf(buf,sizeof(buf),
           "    Polarisation info  : %s\n",
           (mcpl_hdr_has_polarisation(f)?"yes":"no"));
  mcpl_internal_output(out,buf);
  if (mcpl_hdr_userdata_size(f)) {
    //(only shown for files with userdata, keeping the output for other files):
    const char * udl = mcpl_hdr_userdata_layout(f);
    size_t nudbuf = strlen(udl) + 128;
    char * udbuf = mcpl_internal_malloc_es( nudbuf, es );
    if (!udbuf)
      return 0;
    snprintf(udbuf,nudbuf,
             "    User data          : %lu bytes (layout \"%s\")\n",
             (unsigned long)mcpl_hdr_userdata_size(f), udl);
    mcpl_internal_output(out,udbuf);
    free(udbuf);
  }
  mcpl_internal_output(out,"    Fixed part. type   : ");
  int32_t updg = mcpl_hdr_universal_pdgcode(f);
  if (updg) {
    snprintf(buf,sizeof(buf),"yes (pdgcode %li)\n",(long)updg);
    mcpl_internal_output(out,buf);
  } else {
    mcpl_internal_output(out,"no\n");
  }
  mcpl_internal_output(out,"    Fixed part. weight : ");
  double uw = mcpl_hdr_universal_weight(f);
  if (uw) {
    snprintf(buf,sizeof(buf),"yes (weight %g)\n",uw);
    mcpl_internal_output(out,buf);
  } else {
    mcpl_internal_output(out,"no\n");
  }
  snprintf(buf,sizeof(buf),
           "    FP precision       : %s\n",
           (mcpl_hdr_has_doubleprec(f)?"double":"single"));
  mcpl_internal_output(out,buf);
  snprintf(buf,sizeof(buf),
           "    Endianness         : %s\n",
           (mcpl_hdr_little_endian(f)?"little":"big"));
  mcpl_internal_output(out,buf);
  snprintf(buf,sizeof(buf),
           "    Storage            : %i bytes/particle\n\n",
           mcpl_hdr_particle_size(f));
  mcpl_internal_output(out,buf);
  return 1;
}

void mcpl_dump_header(mcpl_file_t f)
{
  mcpl_internal_output_t out = { NULL, NULL };
  mcpl_internal_dump_header( f, &out, NULL );
}

//Dump particles, starting nskip particles after the current position (or at
//the absolute position nskip if absolute is set). Returns 0 in case of errors:
MCPL_LOCAL int mcpl_internal_dump_particles( mcpl_file_t f, uint64_t nskip,
                                             uint64_t nlimit,
                                             int(filter)(const mcpl_particle_t*),
                                             int absolute,
                                             const mcpl_internal_output_t * out,
                                             mcpl_errstate_t * es )
{
  int has_uf = mcpl_hdr_has_userflags(f);
  int has_pol = mcpl_hdr_has_polarisation(f);
  double uweight = mcpl_hdr_universal_weight(f);
  mcpl_internal_output(out,"index     pdgcode   ekin[MeV]       x[cm]       y[cm]"
             "       z[cm]          ux          uy          uz    time[ms]");
  if (!uweight)
    mcpl_internal_output(out,"      weight");
  if (has_pol)
    mcpl_internal_output(out,"       pol-x       pol-y       pol-z");
  if (has_uf)
    mcpl_internal_output(out,"  userflags");
  uint32_t udsize = mcpl_hdr_userdata_size(f);
  if (udsize)
    mcpl_internal_output(out,"  userdata");
  mcpl_internal_output(out,"\n");
  if ( absolute )
    mcpl_seek_es(f,nskip,es);
  else
    mcpl_skipforward_es(f,nskip,es);
  if ( es && es->code )
    return 0;
  //Writing the next loop in an annoying way to silence MSVC C4706 warning:
  char buf[256];
  for ( uint64_t count = nlimit ; ( nlimit==0 || count-- ) ; ) {
    const mcpl_particle_t* p = mcpl_read_es(f,es);
    if ( es && es->code )
      return 0;
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
    mcpl_internal_output(out,buf);
    if (!uweight) {
      snprintf(buf,sizeof(buf)," %11.5g",p->weight);
      mcpl_internal_output(out,buf);
    }
    if (has_pol) {
      snprintf(buf,sizeof(buf),
               " %11.5g %11.5g %11.5g",
               p->polarisation[0],p->polarisation[1],p->polarisation[2]);
      mcpl_internal_output(out,buf);
    }
    if (has_uf) {
      snprintf(buf,sizeof(buf)," 0x%08x",p->userflags);
      mcpl_internal_output(out,buf);
    }
    if (udsize) {
      //Bytes in hex (at most the first 16):
      const uint8_t * ud = mcpl_last_read_userdata(f);
      mcpl_internal_output(out,"  ");
      for ( uint32_t i = 0; i < udsize && i < 16; ++i ) {
        snprintf(buf,sizeof(buf),"%02x",(unsigned)ud[i]);
        mcpl_internal_output(out,buf);
      }
      if ( udsize > 16 )
        mcpl_internal_output(out,"...");
    }
    mcpl_internal_output(out,"\n");
  }
  return 1;
}

void mcpl_dump_particles(mcpl_file_t f, uint64_t nskip, uint64_t nlimit,
                         int(filter)(const mcpl_particle_t*))
{
  mcpl_internal_output_t out = { NULL, NULL };
  mcpl_internal_dump_particles( f, nskip, nlimit, filter, 0, &out, NULL );
}

void mcpl_check_error( const mcpl_errstate_t * es )
{
  if ( es && es->code )
    mcpl_error( es->msg );
}

void mcpl_dump_file_es( mcpl_file_t ff, int parts, uint64_t nskip,
                        uint64_t nlimit,
                        void (*output)(const char * msg, void * ctx),
                        void * ctx, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  //(not using MCPLIMP_FILEDECODE_ES etc., since MSVC warns about empty macro
  //arguments):
  mcpl_fileinternal_t * f = (mcpl_fileinternal_t *)ff.internal;
  if (!f) {
    mcpl_internal_raise_runtime( es, "invalid file handle (NULL)" );
    return;
  }
  if ( f->failed ) {
    mcpl_internal_raise( es, f->failure.code, f->failure.msg );
    return;
  }
  if ( parts < 0 || parts > 2 ) {
    mcpl_internal_raise_runtime( es, "mcpl_dump_file got forbidden value for"
                                 " argument parts" );
    return;
  }
  mcpl_internal_output_t out = { output, ctx };
  if ( parts == 0 || parts == 1 ) {
    if ( !mcpl_internal_dump_header( ff, &out, es ) )
      return;
  }
  if ( parts == 0 || parts == 2 ) {
    uint64_t pos = f->current_particle_idx;
    if ( !mcpl_internal_dump_particles( ff, nskip, nlimit, NULL, 1, &out, es ) )
      return;
    mcpl_seek_es( ff, pos, es );
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

//Checks whether two files can be merged, and if not, writes the reason (the
//first difference found) into reason (of size nreason). Returns 1 if they can
//be merged.
MCPL_LOCAL int mcpl_internal_merge_compat( mcpl_file_t ff1, mcpl_file_t ff2,
                                           char * reason, size_t nreason )
{
  mcpl_fileinternal_t * f1 = (mcpl_fileinternal_t *)ff1.internal;
  mcpl_fileinternal_t * f2 = (mcpl_fileinternal_t *)ff2.internal;
  assert(f1);
  assert(f2);
  reason[0] = '\0';

  //Note, we do not check the format_version field here, since mcpl_merge_files
  //can actually work on files with different versions.

  //Very strict checking of everything except nparticles. Even order of blobs
  //and comments must be preserved (could possibly be relaxed a bit):
  if (strcmp(f1->hdr_srcprogname,f2->hdr_srcprogname)!=0) {
    snprintf(reason,nreason,"source name: \"%.60s%s\" vs \"%.60s%s\"",
             f1->hdr_srcprogname, strlen(f1->hdr_srcprogname)>60 ? "..." : "",
             f2->hdr_srcprogname, strlen(f2->hdr_srcprogname)>60 ? "..." : "");
    return 0;
  }
  if (f1->opt_userflags!=f2->opt_userflags) {
    snprintf(reason,nreason,"userflags: %s vs %s",
             f1->opt_userflags?"yes":"no", f2->opt_userflags?"yes":"no");
    return 0;
  }
  if (f1->opt_polarisation!=f2->opt_polarisation) {
    snprintf(reason,nreason,"polarisation info: %s vs %s",
             f1->opt_polarisation?"yes":"no", f2->opt_polarisation?"yes":"no");
    return 0;
  }
  if (f1->opt_singleprec!=f2->opt_singleprec) {
    snprintf(reason,nreason,"FP precision: %s vs %s",
             f1->opt_singleprec?"single":"double",
             f2->opt_singleprec?"single":"double");
    return 0;
  }
  if (f1->opt_universalpdgcode!=f2->opt_universalpdgcode) {
    char b1[32], b2[32];
    if (f1->opt_universalpdgcode)
      snprintf(b1,sizeof(b1),"%li",(long)f1->opt_universalpdgcode);
    if (f2->opt_universalpdgcode)
      snprintf(b2,sizeof(b2),"%li",(long)f2->opt_universalpdgcode);
    snprintf(reason,nreason,"universal pdgcode: %s vs %s",
             f1->opt_universalpdgcode?b1:"none",
             f2->opt_universalpdgcode?b2:"none");
    return 0;
  }
  if (f1->opt_universalweight!=f2->opt_universalweight) {
    char b1[64], b2[64];
    if (f1->opt_universalweight)
      snprintf(b1,sizeof(b1),"%g",f1->opt_universalweight);
    if (f2->opt_universalweight)
      snprintf(b2,sizeof(b2),"%g",f2->opt_universalweight);
    snprintf(reason,nreason,"universal weight: %s vs %s",
             f1->opt_universalweight?b1:"none",
             f2->opt_universalweight?b2:"none");
    return 0;
  }
  if (f1->is_little_endian!=f2->is_little_endian) {
    snprintf(reason,nreason,"endianness: %s vs %s",
             f1->is_little_endian?"little":"big",
             f2->is_little_endian?"little":"big");
    return 0;
  }
  if ( (f1->userdata_layout!=NULL) != (f2->userdata_layout!=NULL)
       || ( f1->userdata_layout
            && strcmp(f1->userdata_layout,f2->userdata_layout)!=0 ) ) {
    snprintf(reason,nreason,"userdata layout: %s%.200s%s vs %s%.200s%s",
             f1->userdata_layout?"\"":"", f1->userdata_layout?f1->userdata_layout:"none",
             f1->userdata_layout?"\"":"",
             f2->userdata_layout?"\"":"", f2->userdata_layout?f2->userdata_layout:"none",
             f2->userdata_layout?"\"":"");
    return 0;
  }
  if (f1->ncomments!=f2->ncomments) {
    snprintf(reason,nreason,"number of comments: %lu vs %lu",
             (unsigned long)f1->ncomments,(unsigned long)f2->ncomments);
    return 0;
  }
  uint32_t i;
  for (i = 0; i<f1->ncomments; ++i) {
    const char * c1 = f1->comments[i];
    const char * c2 = f2->comments[i];
    if (strcmp(c1,c2)!=0) {
      //incompatible, unless it represents the same stat:sum: entry.
      int same_statsum = 0;
      if ( MCPL_COMMENT_IS_STATSUM(c1) && MCPL_COMMENT_IS_STATSUM(c2) ) {
        mcpl_internal_statsum_t sc1, sc2;
        mcpl_internal_statsum_parse_or_emit_err( c1, &sc1 );
        mcpl_internal_statsum_parse_or_emit_err( c2, &sc2 );
        same_statsum = ( sc1.key[0] && sc2.key[0]
                         && strcmp( sc1.key, sc2.key ) == 0 );
      }
      if ( !same_statsum ) {
        snprintf(reason,nreason,"comment %lu differs",(unsigned long)i);
        return 0;
      }
    }
  }
  if (f1->nblobs!=f2->nblobs) {
    snprintf(reason,nreason,"number of blobs: %lu vs %lu",
             (unsigned long)f1->nblobs,(unsigned long)f2->nblobs);
    return 0;
  }
  for (i = 0; i<f1->nblobs; ++i) {
    if (strcmp(f1->blobkeys[i],f2->blobkeys[i])!=0) {
      snprintf(reason,nreason,"blob %lu key differs",(unsigned long)i);
      return 0;
    }
    if ( f1->bloblengths[i]!=f2->bloblengths[i]
         || memcmp(f1->blobs[i],f2->blobs[i],f1->bloblengths[i])!=0 ) {
      snprintf(reason,nreason,"blob %lu data differs",(unsigned long)i);
      return 0;
    }
  }
  //Should be unreachable given the checks above, but to be safe:
  if (f1->particle_size!=f2->particle_size) {
    snprintf(reason,nreason,"particle size: %lu vs %lu bytes",
             (unsigned long)f1->particle_size,(unsigned long)f2->particle_size);
    return 0;
  }
  if (f1->first_particle_pos!=f2->first_particle_pos) {
    snprintf(reason,nreason,"header size differs");
    return 0;
  }
  return 1;
}

MCPL_LOCAL int mcpl_actual_can_merge(mcpl_file_t ff1, mcpl_file_t ff2)
{
  char reason[512];
  return mcpl_internal_merge_compat(ff1,ff2,reason,sizeof(reason));
}

//Like mcpl_actual_can_merge, but raising an error with the given message
//prefix and the reason (like "<prefix> (<reason>).") if incompatible (returns
//0 in that case):
MCPL_LOCAL int mcpl_internal_require_mergeable( mcpl_file_t ff1, mcpl_file_t ff2,
                                                const char * msgprefix,
                                                mcpl_errstate_t * es )
{
  char reason[512];
  if ( mcpl_internal_merge_compat(ff1,ff2,reason,sizeof(reason)) )
    return 1;
  char buf[1024];
  snprintf(buf,sizeof(buf),"%s (%s).",msgprefix,reason);
  return mcpl_internal_raise_runtime( es, buf );
}

int mcpl_can_merge_es( const char * file1, const char * file2,
                       mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  mcpl_file_t f1 = mcpl_open_file_es(file1,es);
  if ( !f1.internal )
    return 0;
  mcpl_file_t f2 = mcpl_open_file_es(file2,es);
  if ( !f2.internal ) {
    mcpl_close_file(f1);
    return 0;
  }
  int can_merge = mcpl_actual_can_merge(f1,f2);
  mcpl_close_file(f1);
  mcpl_close_file(f2);
  return can_merge;
}

int mcpl_can_merge(const char * file1, const char* file2)
{
  return mcpl_can_merge_es( file1, file2, NULL );
}

MCPL_LOCAL int mcpl_file_certainly_exists(const char * filename)
{
  mcu8str fn = mcu8str_view_cstr( filename );
  return mctools_is_file( &fn );
}

MCPL_LOCAL int mcpl_error_on_dups( unsigned n, const char ** filenames,
                                   mcpl_errstate_t * es )
{
  //Checks that no filenames in provided list represent the same file, and
  //produce error if they do (returning 0). Also checks for NULL filenames.
  //
  //Note: This used to be merely a warning, but in order to ensure consistent
  //operations on Windows it became an error in MCPL 2.0.0.
  //
  //Since this is C, we resort to slow O(N^2) comparison for simplicity.

  unsigned i;
  unsigned j;
  for (i = 0; i<n; ++i)
    if ( !filenames || !filenames[i] )
      return mcpl_internal_raise_runtime( es, "Merging files with null"
                                          " string as filename" );
  for (i = 0; i<n; ++i) {
    mcu8str fn_i = mcu8str_view_cstr( filenames[i] );
    for (j = 0; j<i; ++j) {
      mcu8str fn_j = mcu8str_view_cstr( filenames[j] );
      if ( mctools_is_same_file(&fn_i, &fn_j) )
        return mcpl_internal_raise_runtime( es, "Merging file with itself" );
    }
  }
  return 1;
}


//Internal function for merges which will transfer the particle data in the
//input file into an output file handle which must already be open and ready to
//be written to, and otherwise be associated with an MCPL file with a compatible
//format. Note that the error messages assume the overall operation is a merge.
//Returns 0 in case of errors:
MCPL_LOCAL int mcpl_transfer_particle_contents( FILE * fo, mcpl_file_t ffi,
                                                uint64_t nparticles,
                                                mcpl_errstate_t * es )
{
  mcpl_fileinternal_t * fi = (mcpl_fileinternal_t *)ffi.internal;
  assert(fi);

  if (!nparticles)
    return 1;//no particles to transfer

  unsigned particle_size = fi->particle_size;

  //buffer for transferring up to 1000 particles at a time:
  const unsigned npbufsize = 1000;
  char * buf = mcpl_internal_malloc_es(npbufsize*particle_size,es);
  if (!buf)
    return 0;
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
    if (nb!=toread*particle_size) {
      free(buf);
      return mcpl_internal_readerr( fi, "Unexpected read-error while merging",
                                    es );
    }

    //write:
    nb = fwrite(buf,1,toread*particle_size,fo);
    if (nb!=toread*particle_size) {
      free(buf);
      return mcpl_internal_raise_io( es, "Unexpected write-error while"
                                     " merging" );
    }
  }

  free(buf);
  return 1;
}


//Transfer the particles of all files into out, returning 0 in case of errors:
MCPL_LOCAL int mcpl_internal_forcemerge_transfer( mcpl_outfile_t out,
                                                  const char * file_output,
                                                  unsigned nfiles,
                                                  const char ** files,
                                                  mcpl_errstate_t * es )
{
  //Figure out largest filename for print buffer:
  unsigned ifile;
  size_t nbuf = strlen(file_output);
  for (ifile = 0; ifile < nfiles; ++ifile) {
    size_t nf = strlen(files[ifile]);
    if ( nf > nbuf )
      nbuf = nf;
  }
  nbuf += 128;//other stuff on the lines
  char * buf = mcpl_internal_malloc_es(nbuf,es);
  if (!buf)
    return 0;

  //Finally, perform the transfer:
  for (ifile = 0; ifile < nfiles; ++ifile) {
    mcpl_file_t f = mcpl_open_file_es(files[ifile],es);
    if ( !f.internal ) {
      free(buf);
      return 0;
    }
    uint64_t np = mcpl_hdr_nparticles(f);
    snprintf(buf,nbuf,"MCPL force-merge: Transferring %" PRIu64
             " particle%s from file %s\n",
             np,(np==1?"":"s"),files[ifile]);
    mcpl_print(buf);
    while ( mcpl_read_es(f,es) != 0 ) {
      //lossless transfer when possible:
      mcpl_transfer_last_read_particle_es(f, out, es);
      if ( es && es->code )
        break;
    }
    mcpl_close_file(f);
    if ( es && es->code ) {
      free(buf);
      return 0;
    }
  }

  mcpl_outfileinternal_t * out_internal = (mcpl_outfileinternal_t *)out.internal;
  uint64_t np = out_internal->nparticles;
  snprintf(buf,nbuf,
           "MCPL force-merge: Transferred a total of %" PRIu64
           " particle%s to new file %s\n",
           np,(np==1?"":"s"),file_output);
  mcpl_print(buf);
  free(buf);
  return 1;
}

mcpl_outfile_t mcpl_forcemerge_files_es( const char * file_output,
                                         unsigned nfiles,
                                         const char ** files,
                                         int keep_userflags,
                                         mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  mcpl_outfile_t out;
  out.internal = NULL;

  ////////////////////////////////////
  // Initial sanity check of input: //
  ////////////////////////////////////

  if (!nfiles) {
    mcpl_internal_raise_runtime( es, "mcpl_forcemerge_files must be called"
                                 " with at least one input file" );
    return out;
  }

  if ( !mcpl_error_on_dups(nfiles,files,es) )
    return out;

  //Create new file:
  if ( !file_output ) {
    mcpl_internal_raise_runtime( es, "mcpl_forcemerge_files called with null"
                                 " string as output filename" );
    return out;
  }
  if (mcpl_file_certainly_exists(file_output)) {
    mcpl_internal_raise_runtime( es, "requested output file of"
                                 " mcpl_forcemerge_files already exists" );
    return out;
  }

  ///////////////////////////////////////////
  // Fallback to normal merge if possible: //
  ///////////////////////////////////////////

  //Check all files for compatibility before we start (for robustness, we check
  //again when actually merging each file).
  unsigned ifile;
  int normal_merge_ok = 1;
  for (ifile = 1; ifile < nfiles; ++ifile) {
    int can_merge = mcpl_can_merge_es(files[0],files[ifile],es);
    if ( es && es->code )
      return out;
    if (!can_merge) {
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
    return mcpl_merge_files_es(file_output,nfiles,files,es);
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
  //Userdata is kept only if all files have the same layout:
  char * udlayout = NULL;
  int seen_file = 0;
  int discard_userdata = 0;
  //For reporting which settings change relative to the input files:
  int any_sp = 0, any_nopol = 0, any_nouf = 0, any_updg = 0, any_uw = 0;
  int any_metadata = 0;

  for (ifile = 0; ifile < nfiles; ++ifile) {
    mcpl_file_t f = mcpl_open_file_es(files[ifile],es);
    if ( !f.internal ) {
      free(udlayout);
      return out;
    }
    if (!mcpl_hdr_nparticles(f)) {
      mcpl_close_file(f);
      continue;//won't affect anything
    }

    const char * udl = mcpl_hdr_userdata_layout(f);
    if (!seen_file) {
      if ( udl && !mcpl_store_string_es(&udlayout,udl,es) ) {
        mcpl_close_file(f);
        return out;
      }
    } else if ( (udl!=NULL) != (udlayout!=NULL)
                || ( udl && strcmp(udl,udlayout)!=0 ) ) {
      discard_userdata = 1;
    }
    seen_file = 1;

    if (mcpl_hdr_has_userflags(f))
      opt_uf = 1;//enable if any
    else
      any_nouf = 1;

    if (mcpl_hdr_has_polarisation(f))
      opt_pol = 1;//enable if any
    else
      any_nopol = 1;

    if (mcpl_hdr_has_doubleprec(f))
      opt_dp = 1;
    else
      any_sp = 1;

    if ( mcpl_hdr_ncomments(f) || mcpl_hdr_nblobs(f) )
      any_metadata = 1;
    if ( mcpl_hdr_universal_pdgcode(f) )
      any_updg = 1;
    if ( mcpl_hdr_universal_weight(f) )
      any_uw = 1;

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
  //Report the settings which change relative to the input files (and
  //discarded data):
  if ( opt_dp && any_sp )
    mcpl_print("MCPL force-merge: Files have different FP precision (single"
               " and double), using double\n");
  if ( opt_pol && any_nopol )
    mcpl_print("MCPL force-merge: Files have different polarisation info (no"
               " and yes), enabling it\n");
  if ( opt_uf && !keep_userflags ) {
    mcpl_print("MCPL force-merge: Discarding userflags of the input files"
               " (keep_userflags is not set)\n");
    opt_uf = 0;
  } else if ( opt_uf && any_nouf ) {
    mcpl_print("MCPL force-merge: Files have different userflags (no and"
               " yes), enabling them (zero for particles without)\n");
  }
  if ( any_updg && disallow_universalpdg )
    mcpl_print("MCPL force-merge: Not all files have the same universal"
               " pdgcode, storing the pdgcode per particle\n");
  if ( any_uw && disallow_universalweight )
    mcpl_print("MCPL force-merge: Not all files have the same universal"
               " weight, storing the weight per particle\n");
  if ( any_metadata )
    mcpl_print("MCPL force-merge: Discarding comments and blobs of the input"
               " files\n");
  if ( discard_userdata ) {
    mcpl_print("MCPL WARNING: Discarding userdata in forced merge, since"
               " not all files have the same userdata layout.\n");
    if (udlayout) {
      free(udlayout);
      udlayout = NULL;
    }
  }

  out = mcpl_create_outfile_es(file_output,es);
  if ( !out.internal ) {
    free(udlayout);
    return out;
  }

#define MCPLIMP_FM_CALL(x) do { x; if ( es && es->code ) goto_fail = 1; } while (0)
  int goto_fail = 0;
  if ( mcpl_internal_fakeconstantversion(0) )
    MCPLIMP_FM_CALL(mcpl_hdr_set_srcname_es(out,"mcpl_forcemerge_files (from MCPL v" "99.99.99" ")",es));
  else
    MCPLIMP_FM_CALL(mcpl_hdr_set_srcname_es(out,"mcpl_forcemerge_files (from MCPL v" MCPL_VERSION_STR ")",es));
  if ( opt_uf && !goto_fail )
    MCPLIMP_FM_CALL(mcpl_enable_userflags_es(out,es));
  if ( opt_pol && !goto_fail )
    MCPLIMP_FM_CALL(mcpl_enable_polarisation_es(out,es));
  if ( opt_dp && !goto_fail )
    MCPLIMP_FM_CALL(mcpl_enable_doubleprec_es(out,es));
  if ( !disallow_universalpdg && lastseen_universalpdg && !goto_fail )
    MCPLIMP_FM_CALL(mcpl_enable_universal_pdgcode_es(out,lastseen_universalpdg,es));
  if ( !disallow_universalweight && lastseen_universalweight && !goto_fail )
    MCPLIMP_FM_CALL(mcpl_enable_universal_weight_es(out,lastseen_universalweight,es));
  if ( udlayout && !goto_fail )
    MCPLIMP_FM_CALL(mcpl_enable_userdata_es(out,udlayout,es));
#undef MCPLIMP_FM_CALL
  free(udlayout);
  udlayout = NULL;

  if ( goto_fail
       || !mcpl_internal_forcemerge_transfer( out, file_output, nfiles,
                                              files, es ) ) {
    //Leave the output file unfinished:
    mcpl_internal_outfile_failed( (mcpl_outfileinternal_t *)out.internal, es );
    mcpl_internal_close_outfile_es( (mcpl_outfileinternal_t *)out.internal, NULL );
    out.internal = NULL;
  }
  return out;
}

mcpl_outfile_t mcpl_forcemerge_files( const char * file_output,
                                      unsigned nfiles,
                                      const char ** files,
                                      int keep_userflags )
{
  return mcpl_forcemerge_files_es( file_output, nfiles, files,
                                   keep_userflags, NULL );
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

//State of an ongoing mcpl_merge_files (freed in one place, also after errors):
typedef struct {
  mcpl_file_t f1;
  mcpl_file_t fi;
  unsigned n_scinfo;
  uint32_t * scinfo_indices;
  //values kept in two doubles, s1 and s2, for use with stablesum.
  double * scinfo_values_s1;
  double * scinfo_values_s2;
  int delete_output;
} mcpl_internal_mergestate_t;

//Merge the files into out (in which the header is not written yet), returning
//0 in case of errors:
MCPL_LOCAL int mcpl_internal_merge_files( mcpl_outfile_t out,
                                          unsigned nfiles, const char ** files,
                                          mcpl_internal_mergestate_t * st,
                                          mcpl_errstate_t * es )
{
  mcpl_outfileinternal_t * out_internal = (mcpl_outfileinternal_t *)out.internal;
  int warned_oldversion = 0;

  for ( unsigned ifile = 0; ifile < nfiles; ++ifile ) {
    st->fi = mcpl_open_file_es(files[ifile],es);
    if ( !st->fi.internal )
      return 0;
    mcpl_fileinternal_t * fi_internal = (mcpl_fileinternal_t *)st->fi.internal;

    if (ifile==0) {
      //Add metadata from the first file:
      mcpl_transfer_metadata_es(st->fi, out, es);
      if ( es && es->code )
        return 0;

      //Check for stat:sum: info, and convert all values in the output file to
      //-1 initially (and update only just before returning the file handle):
      if ( !(out_internal->header_notwritten) )
        return mcpl_internal_raise_runtime( es, "unexpected early header"
                                            " write" );
      uint32_t ncomments = out_internal->ncomments;
      if ( fi_internal->ncomments != ncomments )
        return mcpl_internal_raise_runtime( es, "unexpected ncomments after"
                                            " transfer" );
      for ( uint32_t ic = 0; ic < ncomments; ++ic ) {
        if ( MCPL_COMMENT_IS_STATSUM(fi_internal->comments[ic]) ) {
          mcpl_internal_statsum_t sc;
          if ( !mcpl_internal_statsum_parse_or_emit_err_es( fi_internal->comments[ic],
                                                            &sc, es ) )
            return 0;
          if (!st->scinfo_indices) {
            st->scinfo_indices
              = (uint32_t*)mcpl_internal_malloc_es( sizeof(uint32_t)*ncomments, es );
            st->scinfo_values_s1
              = (double*)mcpl_internal_malloc_es( sizeof(double)*ncomments, es );
            st->scinfo_values_s2
              = (double*)mcpl_internal_malloc_es( sizeof(double)*ncomments, es );
            if ( !st->scinfo_indices || !st->scinfo_values_s1
                 || !st->scinfo_values_s2 )
              return 0;
          }
          unsigned n = st->n_scinfo;
          st->scinfo_indices[n] = ic;
          st->scinfo_values_s1[n] = 0.0;
          st->scinfo_values_s2[n] = 0.0;
          if ( sc.value == -1 ) {
            st->scinfo_values_s1[n] = -1.0;
          } else {
            mcpl_impl_stablesum_add( st->scinfo_values_s1+n,
                                     st->scinfo_values_s2+n,
                                     sc.value );
          }
          ++(st->n_scinfo);
          //register -1 for now:
          if ( sc.value != -1.0 ) {
            char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
            if ( !mcpl_internal_encodestatsum_es( sc.key, -1.0, new_comment, es ) )
              return 0;
            size_t nn = strlen(out_internal->comments[ic]);
            if ( nn != strlen(new_comment) )
              return mcpl_internal_raise_runtime( es, "inconsistent length of"
                                                  " stat:sum: comment" );
            memcpy(out_internal->comments[ic],new_comment,nn);
          }
        }
      }

      if ( !mcpl_write_header_es(out_internal,es) )
        return 0;
      st->f1 = st->fi;
      st->fi.internal = NULL;
    } else {
      //Check file is still compatible with first file
      if (!mcpl_actual_can_merge(st->f1,st->fi)) {
        st->delete_output = 1;
        return mcpl_internal_raise_runtime( es, "Aborting merge of suddenly"
                                            " incompatible files." );
      }
      //Update stat:sum: data (adding up, except that -1 combines with anything
      //to give -1):
      for ( unsigned isc = 0; isc < st->n_scinfo; ++isc ) {
        uint32_t isc_idx = st->scinfo_indices[isc];
        if ( st->scinfo_values_s1[isc] == -1.0 && st->scinfo_values_s2[isc] == 0.0 )
          continue;//ignore
        if ( isc_idx >= fi_internal->ncomments )
          return mcpl_internal_raise_runtime( es, "Number of comments changed"
                                              " during merge" );
        if ( !MCPL_COMMENT_IS_STATSUM(fi_internal->comments[isc_idx]) )
          return mcpl_internal_raise_runtime( es, "logic error during"
                                              " stat:sum: merge" );
        mcpl_internal_statsum_t sc;
        if ( !mcpl_internal_statsum_parse_or_emit_err_es( fi_internal->comments[isc_idx],
                                                          &sc, es ) )
          return 0;
        if ( sc.value == -1.0 ) {
          st->scinfo_values_s1[isc] = -1.0;
          st->scinfo_values_s2[isc] = 0.0;
        } else {
          mcpl_impl_stablesum_add( st->scinfo_values_s1+isc,
                                   st->scinfo_values_s2+isc,
                                   sc.value );
        }
      }
    }

    //Transfer particle contents:
    mcpl_file_t fcur = ( ifile == 0 ? st->f1 : st->fi );
    if (mcpl_hdr_version(fcur)>=3) {
      //Can transfer raw bytes (particle data is encoded in the same way in
      //format versions 3 and 4, and versions 2 and 4 can not be mixed since the
      //userdata layouts must be the same):
      uint64_t npi = mcpl_hdr_nparticles(fcur);
      if ( !mcpl_transfer_particle_contents( out_internal->file, fcur, npi, es ) ) {
        mcpl_internal_outfile_failed( out_internal, es );
        return 0;
      }
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
        const mcpl_particle_t* particle = mcpl_read_es(fcur,es);
        if (!particle)
          break;
        mcpl_add_particle_es(out,particle,es);
        if ( es && es->code )
          return 0;
      }
      if ( es && es->code )
        return 0;
    }

    if (ifile!=0) {
      mcpl_close_file(st->fi);
      st->fi.internal = NULL;
    }
  }

  mcpl_close_file(st->f1);
  st->f1.internal = NULL;

  //Finally we must update the sum stats:
  if ( st->scinfo_values_s1 && st->scinfo_values_s2 && st->scinfo_indices ) {
    int warned_statsuminf = 0;
    if ( st->n_scinfo != out_internal->nstatsuminfo || !out_internal->statsuminfo )
      return mcpl_internal_raise_runtime( es, "stat:sum: merge logic error" );
    for ( unsigned isc = 0; isc < st->n_scinfo; ++isc ) {
      double val = st->scinfo_values_s1[isc] + st->scinfo_values_s2[isc];
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
      if ( !mcpl_internal_encodestatsum_es( sci->key, val, comment, es ) )
        return 0;
      if ( !mcpl_internal_updatestatsum_es( out_internal->file, sci, comment, es ) ) {
        mcpl_internal_outfile_failed( out_internal, es );
        return 0;
      }
      sci->value = val;
    }
  }
  return 1;
}

mcpl_outfile_t mcpl_merge_files_es( const char* file_output,
                                    unsigned nfiles, const char ** files,
                                    mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  mcpl_outfile_t out;
  out.internal = NULL;

  if (!nfiles) {
    mcpl_internal_raise_runtime( es, "mcpl_merge_files must be called with at"
                                 " least one input file" );
    return out;
  }

  //Check all files for compatibility before we start (for robustness, we check
  //again when actually merging each file).
  if ( !mcpl_error_on_dups(nfiles,files,es) )
    return out;
  for ( unsigned ifile = 1; ifile < nfiles; ++ifile ) {
    mcpl_file_t f1 = mcpl_open_file_es(files[0],es);
    if ( !f1.internal )
      return out;
    mcpl_file_t f2 = mcpl_open_file_es(files[ifile],es);
    if ( !f2.internal ) {
      mcpl_close_file(f1);
      return out;
    }
    int ok = mcpl_internal_require_mergeable(f1,f2,"Attempting to merge"
                                             " incompatible files",es);
    mcpl_close_file(f1);
    mcpl_close_file(f2);
    if (!ok)
      return out;
  }

  //Create new file:
  if ( !file_output ) {
    mcpl_internal_raise_runtime( es, "mcpl_merge_files called with null string"
                                 " as output filename" );
    return out;
  }
  if (mcpl_file_certainly_exists(file_output)) {
    mcpl_internal_raise_runtime( es, "requested output file of mcpl_merge_files"
                                 " already exists" );
    return out;
  }

  out = mcpl_create_outfile_es(file_output,es);
  if ( !out.internal )
    return out;

  mcpl_internal_mergestate_t st;
  memset(&st,0,sizeof(st));
  st.f1.internal = NULL;
  st.fi.internal = NULL;
  int ok = mcpl_internal_merge_files( out, nfiles, files, &st, es );
  mcpl_close_file(st.fi);
  mcpl_close_file(st.f1);
  free(st.scinfo_indices);
  free(st.scinfo_values_s1);
  free(st.scinfo_values_s2);
  if ( !ok ) {
    //Leave the output file unfinished (or remove it if the input files were
    //incompatible):
    char * fn = NULL;
    if ( st.delete_output )
      mcpl_store_string_es( &fn, mcpl_outfile_filename(out), NULL );
    mcpl_internal_outfile_failed( (mcpl_outfileinternal_t *)out.internal, es );
    mcpl_internal_close_outfile_es( (mcpl_outfileinternal_t *)out.internal, NULL );
    out.internal = NULL;
    if ( fn ) {
      mcpl_internal_delete_file( fn );
      free(fn);
    }
  }
  return out;
}

mcpl_outfile_t mcpl_merge_files( const char* file_output,
                                 unsigned nfiles, const char ** files )
{
  return mcpl_merge_files_es( file_output, nfiles, files, NULL );
}

void mcpl_merge(const char * file1, const char* file2)
{
  mcpl_print("MCPL WARNING: Usage of function mcpl_merge is obsolete as it has"
             " been renamed to mcpl_merge_inplace. Please update your code.\n");
  mcpl_merge_inplace(file1, file2);
}

//Appends the particles of ff2 to the file (already opened as *pff1, which is
//closed before modifying it), returning 0 in case of errors. Errors before
//file1 is modified leave it unchanged, while errors during the transfer leave
//it marked as unfinished (nparticles=0 and stat:sum: values -1), so it can be
//repaired:
MCPL_LOCAL int mcpl_internal_merge_inplace( const char * file1,
                                            mcpl_file_t * pff1, mcpl_file_t ff2,
                                            mcpl_errstate_t * es )
{
  mcpl_file_t ff1 = *pff1;
  {
    char reason[512];
    if ( !mcpl_internal_merge_compat(ff1,ff2,reason,sizeof(reason)) ) {
      char buf[1024];
      snprintf(buf,sizeof(buf),"Attempting to merge incompatible files (%s).",reason);
      return mcpl_internal_raise_runtime( es, buf );
    }
  }

  //Access internals:
  mcpl_fileinternal_t * f1 = (mcpl_fileinternal_t *)ff1.internal;
  mcpl_fileinternal_t * f2 = (mcpl_fileinternal_t *)ff2.internal;
  assert(f1);
  assert(f2);

  if (f1->format_version!=f2->format_version)
    return mcpl_internal_raise_runtime( es, "Attempting to merge incompatible"
                                        " files (can not mix MCPL format"
                                        " versions when merging inplace)" );

  if (f1->filegz)
    return mcpl_internal_raise_runtime( es, "direct modification of gzipped"
                                        " files is not supported." );

  uint64_t np1 = f1->nparticles;
  uint64_t np2 = f2->nparticles;
  if (!np2)
    return 1;//nothing to take from file 2.

  unsigned particle_size = f1->particle_size;
  uint64_t first_particle_pos = f1->first_particle_pos;

  //Should be same since can_merge:
  if ( particle_size != f2->particle_size
       || first_particle_pos != f2->first_particle_pos )
    return mcpl_internal_raise_runtime( es, "mcpl_merge_inplace: unexpected"
                                        " particle size or position" );

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
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( comment, &sc, es )
           || !mcpl_internal_statsum_parse_or_emit_err_es( f2->comments[i], &sc2, es ) ) {
        free(statsuminfo);
        free(statsuminfo_newvalues);
        return 0;
      }
      if (!statsuminfo) {
        statsuminfo = (mcpl_internal_statsuminfo_t *)
          mcpl_internal_calloc_es( f1->ncomments-i,
                                   sizeof(mcpl_internal_statsuminfo_t), es );
        statsuminfo_newvalues = (double*) mcpl_internal_calloc_es( f1->ncomments-i,
                                                                   sizeof(double),
                                                                   es );
        if ( !statsuminfo || !statsuminfo_newvalues ) {
          free(statsuminfo);
          free(statsuminfo_newvalues);
          return 0;
        }
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
      s->writtenstrlen = (uint32_t)lcomment;
      s->writtenpos = writtenpos;
    }
  }

  //Now, close file1 and reopen a file handle in update mode:
  mcpl_close_file(ff1);
  pff1->internal = NULL;
  f1 = NULL;
  FILE * f1a = mcpl_internal_fopen(file1,"r+b");

  //Update file positions. Note that f2->file is already at the position for the
  //first particle and that the seek operation on f1a correctly discards any
  //partial entries at the end, which could be there if the file was in need of
  //mcpl_repair:
  if (!f1a) {
    free(statsuminfo);
    free(statsuminfo_newvalues);
    return mcpl_internal_raise_io( es, "Unable to open file1 in update mode!" );
  }
  if (MCPL_FSEEK( f1a, first_particle_pos + particle_size*np1 )) {
    free(statsuminfo);
    free(statsuminfo_newvalues);
    fclose(f1a);
    return mcpl_internal_raise_io( es, "Unable to seek to end of file1 in"
                                   " update mode" );
  }

  //Transfer particle contents, and update stat:sum: comments. We set nparticles
  //to 0 and stat sums to -1 during the operation (so the file appears broken
  //and in need of mcpl_repair in case of errors during the transfer). From
  //here on, errors leave the file in that state:
  int ok = mcpl_update_nparticles_es(f1a,0,es);
  if ( ok && fflush(f1a) )
    ok = mcpl_internal_raise_io( es, "Errors encountered while attempting to"
                                 " update number of particles in file." );

  //Set stat:sum entries to -1:
  for ( uint32_t i = 0; ok && i < nssi; ++i ) {
    char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
    ok = ( mcpl_internal_encodestatsum_es( statsuminfo[i].key, -1.0,
                                           new_comment, es )
           && mcpl_internal_updatestatsum_es( f1a, &statsuminfo[i],
                                              new_comment, es ) );
    statsuminfo[i].value = -1.0;
  }
  //Transfer particles (potentially a lot of work and chance of running out of
  //quota, etc.):
  if ( ok )
    ok = mcpl_transfer_particle_contents(f1a, ff2, np2, es);

  //Make sure all particles were written, before updating the header:
  if ( ok && fflush(f1a) )
    ok = mcpl_internal_raise_io( es, "Unexpected write-error while merging" );

  //Set stat:sum entries to final values:
  for ( uint32_t i = 0; ok && i < nssi; ++i ) {
    double newval = statsuminfo_newvalues[i];
    if ( newval == -1.0 )
      continue;//already fine
    char new_comment[MCPL_STATSUMBUF_MAXLENGTH+1];
    ok = ( mcpl_internal_encodestatsum_es( statsuminfo[i].key, newval,
                                           new_comment, es )
           && mcpl_internal_updatestatsum_es( f1a, &statsuminfo[i],
                                              new_comment, es ) );
    statsuminfo[i].value = newval;
  }

  //Finally we can update nparticles:
  if ( ok )
    ok = mcpl_update_nparticles_es(f1a,np1+np2,es);

  //Finish up.
  if ( fclose(f1a) && ok )
    ok = mcpl_internal_raise_io( es, "Errors encountered while attempting to"
                                 " close file." );
  free(statsuminfo);
  free(statsuminfo_newvalues);
  return ok;
}

void mcpl_merge_inplace_es( const char * file1, const char * file2,
                            mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  if ( !file1 || !file2 ) {
    mcpl_internal_raise_runtime( es, "mcpl_merge_inplace called with null"
                                 " string as filename" );
    return;
  }
  {
    mcu8str file1_str = mcu8str_view_cstr( file1 );
    mcu8str file2_str = mcu8str_view_cstr( file2 );
    if ( mctools_is_same_file(&file1_str, &file2_str) ) {
      mcpl_internal_raise_runtime( es, "Merging file with itself" );
      return;
    }
  }

  mcpl_file_t ff1 = mcpl_open_file_es(file1,es);
  if ( !ff1.internal )
    return;
  mcpl_file_t ff2 = mcpl_open_file_es(file2,es);
  if ( !ff2.internal ) {
    mcpl_close_file(ff1);
    return;
  }
  mcpl_internal_merge_inplace( file1, &ff1, ff2, es );
  mcpl_close_file(ff1);//(does nothing if already closed)
  mcpl_close_file(ff2);
}

void mcpl_merge_inplace(const char * file1, const char* file2)
{
  mcpl_merge_inplace_es( file1, file2, NULL );
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

MCPL_LOCAL int32_t mcpl_internal_pdgcode_from_name( const char * name )
{
  //Names of a few common particles which can be used instead of PDG codes in
  //"mcpltool-c -p" (mcpltool has an identical list):
  static const struct { const char * name; int32_t pdgcode; } names[] = {
    { "neutron", 2112 }, { "antineutron", -2112 },
    { "proton", 2212 }, { "antiproton", -2212 },
    { "electron", 11 }, { "positron", -11 }, { "antielectron", -11 },
    { "muon", 13 }, { "antimuon", -13 },
    { "gamma", 22 }, { "photon", 22 } };
  for ( size_t i = 0; i < sizeof(names)/sizeof(names[0]); ++i )
    if ( strcmp( name, names[i].name ) == 0 )
      return names[i].pdgcode;
  return 0;
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
  mcpl_print("This is a minimal version (written in C) of the mcpltool command from the\n");
  mcpl_print("mcpl-python package, which can in addition show statistics and histograms, and\n");
  mcpl_print("select or edit particles with expressions.\n");
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
  mcpl_print("                    FILEOUT will be gzipped if its name ends with .mcpl.gz.\n");
  mcpl_print("  -m, --merge --inplace FILE1 FILE2 ... FILEN\n");
  mcpl_print("                    Appends the particle contents in FILE2 ... FILEN into\n");
  mcpl_print("                    FILE1. Note that this action modifies FILE1!\n");
  mcpl_print("  --forcemerge [--keepuserflags] FILEOUT FILE1 FILE2 ... FILEN\n");
  mcpl_print("               Like --merge but works with incompatible files as well, at the\n");
  mcpl_print("               heavy price of discarding most metadata like comments and blobs.\n");
  mcpl_print("               Userflags will be discarded unless --keepuserflags is specified.\n");
  mcpl_print("               Userdata will be discarded unless all files have the same\n");
  mcpl_print("               userdata layout.\n");
  mcpl_print("\n");
  mcpl_print("Extract options:\n");
  mcpl_print("  -e, --extract FILE1 FILE2\n");
  mcpl_print("                    Extracts particles from FILE1 into a new FILE2.\n");
  mcpl_print("                    FILE2 will be gzipped if its name ends with .mcpl.gz.\n");
  mcpl_print("  -lN, -sN        : Select range of particles in FILE1 (as above).\n");
  mcpl_print("  -pPDGCODE       : Select particles of type given by PDGCODE. Instead of the\n");
  mcpl_print("                    PDGCODE, one of the following names can be used: neutron,\n");
  mcpl_print("                    antineutron, proton, antiproton, electron, positron (or\n");
  mcpl_print("                    antielectron), muon, antimuon, gamma (or photon).\n");
  mcpl_print("  --no-comment    : Do not add a comment to the header of FILE2 about how the\n");
  mcpl_print("                    particles were extracted.\n");
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

MCPL_LOCAL const char * mcpl_internal_tool_outfn( char * fn, char ** outfn,
                                                  int * attempt_gzip )
{
  //Output file name for --merge and --extract. Disallow .gz endings unless it
  //is .mcpl.gz, in which case we attempt to gzip automatically. Returns an
  //error message in case of problems. If *outfn != fn, it must be freed.
  *outfn = fn;
  *attempt_gzip = 0;
  if (mcpl_file_certainly_exists(fn))
    return "Requested output file already exists.";
  size_t lfn = strlen(fn);
  if( lfn > 8 && !strcmp(fn + (lfn - 8), ".mcpl.gz")) {
    *attempt_gzip = 1;
    *outfn = mcpl_internal_malloc(lfn-2);//lfn+1-3
    memcpy(*outfn,fn,lfn-3);
    (*outfn)[lfn-3] = '\0';
    if (mcpl_file_certainly_exists(*outfn)) {
      free(*outfn);
      *outfn = fn;
      return "Requested output file already exists (without .gz extension).";
    }
  } else if( lfn > 3 && !strcmp(fn + (lfn - 3), ".gz")) {
    return "Requested output file should not have .gz extension (unless it is .mcpl.gz).";
  } else if( !( lfn > 5 && !strcmp(fn + (lfn - 5), ".mcpl") ) ) {
    //mcpl_create_outfile will append .mcpl:
    char * fnmcpl = mcpl_internal_malloc(lfn+6);
    memcpy(fnmcpl,fn,lfn);
    memcpy(fnmcpl+lfn,".mcpl",6);
    int exists = mcpl_file_certainly_exists(fnmcpl);
    free(fnmcpl);
    if (exists)
      return "Requested output file already exists (with .mcpl extension).";
  }
  return NULL;
}

MCPL_LOCAL void mcpl_internal_tool_remove_output( const char * outfn )
{
  //Removes the output file of a failed --merge, --forcemerge or --extract
  //(which did not exist before, see mcpl_internal_tool_outfn), with the name
  //given to it by mcpl_create_outfile:
  size_t n = strlen(outfn);
  if ( n > 5 && !strcmp(outfn + (n - 5), ".mcpl") ) {
    if ( mcpl_file_certainly_exists(outfn) )
      mcpl_internal_delete_file(outfn);
    return;
  }
  char * fn = mcpl_internal_malloc(n+6);
  memcpy(fn,outfn,n);
  memcpy(fn+n,".mcpl",6);
  if ( mcpl_file_certainly_exists(fn) )
    mcpl_internal_delete_file(fn);
  free(fn);
}

MCPL_LOCAL int mcpl_internal_tool_extract( mcpl_file_t fi, const char * outfn,
                                           int attempt_gzip,
                                           int opt_nocomment,
                                           int64_t opt_num_limit,
                                           int64_t opt_num_skip,
                                           int32_t pdgcode_select,
                                           uint64_t * added,
                                           char ** fo_filename,
                                           mcpl_errstate_t * es )
{
  //The extraction of --extract, returning 0 in case of errors (after which
  //the output file is closed, and must be removed by the caller). On success,
  //*fo_filename is the name of the output file (to be freed by the caller).
  mcpl_outfile_t fo = mcpl_create_outfile_es(outfn,es);
  if ( !fo.internal )
    return 0;
#define MCPLIMP_EXTRACT_CHECK if ( es->code ) { \
    mcpl_close_outfile_unfinished_es( fo, NULL ); return 0; }
  mcpl_transfer_metadata_es(fi, fo, es);
  MCPLIMP_EXTRACT_CHECK;
  uint64_t fi_nparticles = mcpl_hdr_nparticles(fi);

  if (!opt_nocomment) {
    //Describe which particles were extracted (but nothing specific to the
    //input file, to keep files extracted in the same way mergeable):
    char comment[1024];
    int n = snprintf(comment, sizeof(comment), "mcpltool: extracted particles");
    const char * sep = " with ";
    if ( opt_num_limit > 0 ) {
      n += snprintf(comment+n, sizeof(comment)-n, "%s-l%" PRId64, sep, opt_num_limit);
      sep = " ";
    }
    if ( opt_num_skip > 0 ) {
      n += snprintf(comment+n, sizeof(comment)-n, "%s-s%" PRId64, sep, opt_num_skip);
      sep = " ";
    }
    if ( pdgcode_select && n < (int)sizeof(comment) )
      snprintf(comment+n, sizeof(comment)-n, "%s-p%" PRId32, sep, pdgcode_select);
    mcpl_hdr_add_comment_es(fo,comment,es);
    MCPLIMP_EXTRACT_CHECK;
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
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( comment, &sc, es ) ) {
        mcpl_close_outfile_unfinished_es( fo, NULL );
        return 0;
      }
      if ( sc.value != -1.0 ) {
        need_stat_scaling = 1;
        break;
      }
    }
    if ( need_stat_scaling ) {
      mcpl_print("MCPL WARNING: Marking stat:sum entries in output file as "
                 "not available (-1) when filtering based on particle "
                 "positions\n");
      mcpl_hdr_scale_stat_sums_es( fo, -1.0, es );
      MCPLIMP_EXTRACT_CHECK;
    }
  }

  if (opt_num_skip>0) {
    mcpl_seek_es(fi,(uint64_t)opt_num_skip,es);
    MCPLIMP_EXTRACT_CHECK;
  }

  //uint64_t(-1) instead of UINT64_MAX to fix clang c++98 compilation
  uint64_t left = opt_num_limit>0 ? (uint64_t)opt_num_limit : (uint64_t)-1;

  //Writing the next loop in an annoying way to silence MSVC C4706 warning:
  for (;left;) {
    --left;
    const mcpl_particle_t* particle = mcpl_read_es(fi,es);
    MCPLIMP_EXTRACT_CHECK;
    if (!particle)
      break;
    if (pdgcode_select && pdgcode_select!= particle->pdgcode)
      continue;
    mcpl_transfer_last_read_particle_es(fi, fo, es);
    MCPLIMP_EXTRACT_CHECK;
    ++(*added);
  }
#undef MCPLIMP_EXTRACT_CHECK

  const char * outfile_fn = mcpl_outfile_filename(fo);
  size_t nn = strlen(outfile_fn);
  *fo_filename = mcpl_internal_malloc(nn+4);
  memcpy(*fo_filename,outfile_fn,nn+1);
  if (attempt_gzip) {
    if (mcpl_closeandgzip_outfile_es(fo,es))
      memcpy(*fo_filename+nn,".gz",4);
  } else {
    mcpl_close_outfile_es(fo,es);
  }
  if ( es->code ) {
    free(*fo_filename);
    *fo_filename = NULL;
    return 0;
  }
  return 1;
}

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
  int opt_nocomment = 0;
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
      const char * lo_preventcomment = "preventcomment";//old name of --no-comment
      const char * lo_nocomment = "no-comment";
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
      else if (strstr(lo_preventcomment,a)==lo_preventcomment) opt_nocomment = 1;
      else if (strcmp(lo_nocomment,a)==0) opt_nocomment = 1;
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

  if ( opt_extract==0 && opt_nocomment )
    return free(filenames),mcpl_tool_usage(argv,"--no-comment can only be used with --extract.");

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
      for (i = ifirstinfile+1; i < nfilenames; ++i) {
        mcpl_file_t f1 = mcpl_open_file(filenames[ifirstinfile]);
        mcpl_file_t f2 = mcpl_open_file(filenames[i]);
        char reason[512];
        int ok = mcpl_internal_merge_compat(f1,f2,reason,sizeof(reason));
        mcpl_close_file(f1);
        mcpl_close_file(f2);
        if (!ok) {
          char buf[1024];
          snprintf(buf,sizeof(buf),"Requested files are incompatible for merge"
                   " as they have different header info (%s).",reason);
          free(filenames);
          return mcpl_tool_usage(argv,buf);
        }
      }
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
      char * outfn;
      int attempt_gzip;
      const char * outfn_err = mcpl_internal_tool_outfn( filenames[0], &outfn,
                                                         &attempt_gzip );
      if (outfn_err)
        return free(filenames),mcpl_tool_usage(argv,outfn_err);

      //A failed merge must not leave an output file behind, so errors are
      //only reported after removing it:
      mcpl_errstate_t es;
      mcpl_outfile_t mf = ( opt_forcemerge ?
                            mcpl_forcemerge_files_es( outfn, nfilenames-1, (const char**)filenames + 1, opt_keepuserflags, &es ) :
                            mcpl_merge_files_es( outfn, nfilenames-1, (const char**)filenames + 1, &es ) );
      if ( es.code ) {
        mcpl_internal_tool_remove_output( outfn );
        if (outfn != filenames[0])
          free(outfn);
        free(filenames);
        mcpl_check_error( &es );
        return 1;
      }
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

    int32_t pdgcode_select = 0;
    if (pdgcode_str) {
      pdgcode_select = mcpl_internal_pdgcode_from_name(pdgcode_str);
      int64_t pdgcode64;
      if ( !pdgcode_select ) {
        if (!mcpl_str2int(pdgcode_str, 0, &pdgcode64) || -pdgcode64>2147483648 || pdgcode64>2147483647 || !pdgcode64)
          return free(filenames),mcpl_tool_usage(argv,"Must specify non-zero 32bit integer or particle name as argument to -p.");
        pdgcode_select = (int32_t)pdgcode64;
      }
    }

    char * outfn;
    int attempt_gzip;
    const char * outfn_err = mcpl_internal_tool_outfn( filenames[1], &outfn,
                                                       &attempt_gzip );
    if (outfn_err)
      return free(filenames),mcpl_tool_usage(argv,outfn_err);

    mcpl_file_t fi = mcpl_open_file(filenames[0]);
    uint64_t fi_nparticles = mcpl_hdr_nparticles(fi);
    //A failed extraction must not leave an output file behind, so errors are
    //only reported after removing it:
    mcpl_errstate_t es;
    uint64_t added = 0;
    char * fo_filename = NULL;
    int ok = mcpl_internal_tool_extract( fi, outfn, attempt_gzip,
                                         opt_nocomment, opt_num_limit,
                                         opt_num_skip, pdgcode_select,
                                         &added, &fo_filename, &es );
    mcpl_close_file(fi);
    if ( !ok ) {
      mcpl_internal_tool_remove_output( outfn );
      if (outfn != filenames[1])
        free(outfn);
      free(filenames);
      mcpl_check_error( &es );
      return 1;
    }
    if (outfn != filenames[1])
      free(outfn);

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

    fprintf(fout,"#MCPL-ASCII\n#ASCII-FORMAT: v1\n#NPARTICLES: %" PRIu64 "\n",mcpl_hdr_nparticles(fi));
    //Userdata is not included in the output, which is noted in the header:
    if (mcpl_hdr_userdata_size(fi))
      fprintf(fout,"#WARNING: The userdata of the particles in the MCPL file is"
              " not included\n");
    fprintf(fout,"#END-HEADER\n");
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
  //Compresses filename into filename.gz, removing filename on success. In
  //case of errors, any partially written filename.gz is removed. Returns 0
  //in case of errors.

  //Open input file:
  FILE *handle_in = mcpl_internal_fopen(filename, "rb");
  if (!handle_in)
    return 0;

  //Construct output file name by appending .gz:
  size_t nn = strlen(filename);
  char * outfn = (char*)malloc(nn + 4);
  if (!outfn) {
    fclose(handle_in);
    return 0;
  }
  memcpy(outfn,filename,nn);
  memcpy(outfn+nn,".gz",4);

  //Open output file:
  gzFile handle_out = mcpl_gzopen(outfn, "wb");
  if (!handle_out) {
    //(nothing was created, so nothing to remove)
    free(outfn);
    fclose(handle_in);
    return 0;
  }

  //Compress input to output:
  int ok = 1;
  char buf[16384];
  size_t len;
  while (1) {
    len = (int)fread(buf, 1, sizeof(buf), handle_in);
    if (ferror(handle_in)) {
      ok = 0;
      break;
    }
    if (!len)
      break;
    if ((size_t)gzwrite(handle_out, buf, (unsigned)len) != len) {
      ok = 0;
      break;
    }
  }

  //close files:
  fclose(handle_in);
  if (gzclose(handle_out) != Z_OK)
    ok = 0;

  if ( ok ) {
    //remove input file:
    mcpl_internal_delete_file( filename );
  } else {
    //remove partial output file:
    mcpl_internal_delete_file( outfn );
  }
  free(outfn);
  return ok;
}

int mcpl_gzip_file_es( const char * filename, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  if (!filename) {
    mcpl_internal_raise_runtime( es, "mcpl_gzip_file called with null string" );
    return 0;
  }
  char * bn = mcpl_basename(filename);
  size_t n = 256 + strlen(bn);
  char * buf = mcpl_internal_malloc_es(n,es);
  if (!buf) {
    free(bn);
    return 0;
  }
  snprintf(buf,n,"MCPL: Compressing file %s\n",bn);
  mcpl_print(buf);
  int ok = mcpl_internal_do_gzip(filename);
  if ( ok ) {
    snprintf(buf,n,"MCPL: Compressed file into %s.gz\n",bn);
    mcpl_print(buf);
  } else {
    snprintf(buf,n,"Problems encountered while compressing file %s",bn);
    mcpl_internal_raise_io( es, buf );
  }
  free(bn);
  free(buf);
  return ok;
}

int mcpl_gzip_file(const char * filename)
{
  //Not via mcpl_gzip_file_es, since failures to compress files are not errors
  //here (they are reported, and 0 is returned):
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

void mcpl_hdr_add_stat_sum_es( mcpl_outfile_t of, const char * key,
                               double value, mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_OUTFILEDECODE_ES_VOID;
  if ( !key ) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_add_stat_sum called with null"
                                 " string." );
    return;
  }
  char comment[MCPL_STATSUMBUF_MAXLENGTH+1];
  if ( !mcpl_internal_encodestatsum_es( key, value, comment, es ) )
    return;
  if ( !(value>=0.0 || value == -1.0 ) || isnan(value) || isinf(value) ) {
    mcpl_internal_raise_runtime( es, "logic error: lack of expected input"
                                 " sanitisation." );
    return;
  }

  size_t nkey = strlen(key);

  if (f->header_notwritten) {
    //Header not written yet, simply check other in-mem comments for clashes.
    for ( uint32_t i = 0; i < f->ncomments; ++i ) {
      if ( !MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
        continue;
      mcpl_internal_statsum_t sc;
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( f->comments[i], &sc, es ) )
        return;
      if ( strlen(sc.key)==nkey && memcmp(sc.key,key,nkey+1)==0 ) {
        //Same variable! Simply update in place.
        size_t n = strlen(comment);
        size_t nalloc = strlen(f->comments[i]);
        if ( n != nalloc ) {
          mcpl_internal_raise_runtime( es, "preallocated space for stat:sum:"
                                       " update does not fit" );
          return;
        }
        memcpy(f->comments[i],comment,nalloc);
        return;
      }
    }
    //Ok not there already, just add a new comment:
    mcpl_hdr_add_comment_es( of, comment, es );
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
  if (!sc_to_update) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_add_stat_sum called after first"
                                 " particle was added to file, but without"
                                 " first registering a value for the same key"
                                 " earlier (the special value -1 can be used"
                                 " for this)" );
    return;
  }

  if ( !mcpl_internal_updatestatsum_es( f->file, sc_to_update, comment, es ) ) {
    mcpl_internal_outfile_failed( f, es );
    return;
  }
  sc_to_update->value = value;
}

void mcpl_hdr_add_stat_sum( mcpl_outfile_t of,
                            const char * key, double value )
{
  mcpl_hdr_add_stat_sum_es( of, key, value, NULL );
}

void mcpl_hdr_scale_stat_sums_es( mcpl_outfile_t of, double scale,
                                  mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  const char * errmsg = NULL;
  if ( isnan(scale) )
    errmsg = "mcpl_hdr_scale_stat_sums called with NaN (not-a-number) scale";
  else if ( scale < 0.0 && scale != -1.0 )
    errmsg = "mcpl_hdr_scale_stat_sums called with negative scale";
  else if ( isinf(scale) )
    errmsg = "mcpl_hdr_scale_stat_sums called with infinite scale";
  else if ( scale == 0.0 )
    errmsg = "mcpl_hdr_scale_stat_sums called with zero scale";
  if ( errmsg ) {
    mcpl_internal_raise_runtime( es, errmsg );
    return;
  }

  MCPLIMP_OUTFILEDECODE_ES_VOID;
  int any_values_turned_to_inf = 0;
  if (f->header_notwritten) {
    //Header not written yet, simply update in-mem comments (first encoding
    //all of them, so nothing is changed in case of errors).
    char (*new_comments)[MCPL_STATSUMBUF_MAXLENGTH+1] = NULL;
    if ( f->ncomments ) {
      new_comments = (char (*)[MCPL_STATSUMBUF_MAXLENGTH+1])
        mcpl_internal_calloc_es( f->ncomments, MCPL_STATSUMBUF_MAXLENGTH+1, es );
      if ( !new_comments )
        return;
    }
    for ( uint32_t i = 0; i < f->ncomments; ++i ) {
      if ( !MCPL_COMMENT_IS_STATSUM(f->comments[i]) )
        continue;
      mcpl_internal_statsum_t sc;
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( f->comments[i], &sc, es ) ) {
        free(new_comments);
        return;
      }
      double new_value = ( ( scale == -1.0 || sc.value == -1.0 )
                           ? -1.0 : ( sc.value * scale ) );
      if ( isinf(new_value) ) {
        any_values_turned_to_inf = 1;
        new_value = -1.0;
      }
      if ( sc.value == new_value )
        continue;//no update needed
      if ( !mcpl_internal_encodestatsum_es( sc.key, new_value, new_comments[i], es ) ) {
        free(new_comments);
        return;
      }
      size_t n = strlen(new_comments[i]);
      size_t nalloc = strlen(f->comments[i]);
      if ( n != nalloc ) {
        free(new_comments);
        mcpl_internal_raise_runtime( es, "preallocated space for stat:sum:"
                                     " update does not fit" );
        return;
      }
    }
    for ( uint32_t i = 0; i < f->ncomments; ++i )
      if ( new_comments[i][0] )
        memcpy(f->comments[i],new_comments[i],strlen(f->comments[i]));
    free(new_comments);
  } else {
    //Header already written, must update on-disk (errors leave the file
    //unusable).
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
      if ( !mcpl_internal_encodestatsum_es( si->key, new_value, new_comment, es )
           || !mcpl_internal_updatestatsum_es( f->file, si, new_comment, es ) ) {
        mcpl_internal_outfile_failed( f, es );
        return;
      }
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

void mcpl_hdr_scale_stat_sums( mcpl_outfile_t of, double scale )
{
  mcpl_hdr_scale_stat_sums_es( of, scale, NULL );
}

double mcpl_hdr_stat_sum_es( mcpl_file_t ff, const char * key,
                             mcpl_errstate_t * es )
{
  MCPLIMP_ES_RESET;
  MCPLIMP_FILEDECODE_ES(-3.0);
  if ( !key ) {
    mcpl_internal_raise_runtime( es, "mcpl_hdr_stat_sum called with null"
                                 " string" );
    return -3.0;
  }
  for ( uint32_t i = 0; i < f->ncomments; ++i ) {
    const char * c = f->comments[i];
    if ( MCPL_COMMENT_IS_STATSUM(c) ) {
      mcpl_internal_statsum_t sc;
      if ( !mcpl_internal_statsum_parse_or_emit_err_es( c, &sc, es ) )
        return -3.0;
      if ( strcmp(key,sc.key)==0 )
        return sc.value;
    }
  }
  return -2.0;//not present
}

double mcpl_hdr_stat_sum( mcpl_file_t ff, const char * key )
{
  return mcpl_hdr_stat_sum_es( ff, key, NULL );
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
