#ifndef MCPLCPP_H
#define MCPLCPP_H

/******************************************************************************/
/*                                                                            */
/*  This file is part of MCPL (see https://mctools.github.io/mcpl/)           */
/*                                                                            */
/*  Copyright 2015-2026 MCPL developers.                                      */
/*                                                                            */
/*  Licensed under the Apache License, Version 2.0 (the "License");           */
/*  you may not use this file except in compliance with the License.          */
/*  You may obtain a copy of the License at                                   */
/*                                                                            */
/*      http://www.apache.org/licenses/LICENSE-2.0                            */
/*                                                                            */
/*  Unless required by applicable law or agreed to in writing, software       */
/*  distributed under the License is distributed on an "AS IS" BASIS,         */
/*  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  */
/*  See the License for the specific language governing permissions and       */
/*  limitations under the License.                                            */
/*                                                                            */
/******************************************************************************/

////////////////////////////////////////////////////////////////////////////////
//                                                                            //
// Header-only C++ interface to MCPL (requires C++17 or later), documented    //
// below.                                                                     //
//                                                                            //
////////////////////////////////////////////////////////////////////////////////

#include "mcpl.h"

#if defined(_MSVC_LANG) && _MSVC_LANG > __cplusplus
#  define MCPLCPP_CPLUSPLUS _MSVC_LANG
#else
#  define MCPLCPP_CPLUSPLUS __cplusplus
#endif
#if MCPLCPP_CPLUSPLUS < 201703L
#  error "mcplcpp.h requires C++17 or later"
#endif

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <exception>
#include <filesystem>
#include <functional>
#include <initializer_list>
#include <iterator>
#include <memory>
#include <mutex>
#include <new>
#include <optional>
#include <ostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

/**
 * @brief Header-only C++ interface to MCPL.
 *
 * The C++ interface to MCPL requires C++17 or later, and is built on the
 * functions of the C API with error states (the `_es` variants). It offers
 * the same functionality as the C API, with errors reported as exceptions
 * (see mcpl::Error), files which are closed automatically, and type-safe
 * access to particles and their userdata.
 *
 * Reading files:
 * @code{.cpp}
 * mcpl::MCPLFile f("input.mcpl");
 * auto temp = f.userdata_field<float>("temp");    // (if needed)
 * for ( auto p : f )
 *   if ( p.ekin() > 1.0 )
 *     do_something( p.position(), temp(p) );
 * @endcode
 *
 * Particles (mcpl::Particle) are lightweight views of the particle data in
 * the file object, which are only valid until the next particle is read.
 * Views of header data (strings, comments and blobs) are valid as long as
 * the file object is open.
 *
 * Writing files:
 * @code{.cpp}
 * mcpl::MCPLOutFile out("output.mcpl");
 * out.set_srcname("my program");
 * auto temp = out.add_userdata_field<float>("temp");    // (if needed)
 * auto p = out.new_particle();
 * p.set_ekin(1.5);
 * p.set_userdata(temp,300.0f);
 * out.add(p);
 * //... add many more particles
 * out.close();
 * @endcode
 *
 * Output files are only finished by close() or close_and_gzip(). If an
 * mcpl::MCPLOutFile is destroyed without being closed (e.g. because of an
 * exception), the file is left unfinished (it can often be recovered with
 * mcpl::repair). File objects can be moved, but not copied.
 *
 * Filenames can be given as `std::filesystem::path` objects, which work
 * with all names on all platforms, or as strings (`std::string`,
 * `std::string_view` or C strings), which are interpreted as UTF-8 like
 * elsewhere in MCPL.
 */
namespace mcpl {

  //////////////////////////////////////////////////////////////////////////////
  // Exceptions

  /**
   * @brief Errors from MCPL.
   *
   * All errors are reported as exceptions: mcpl::Error for invalid files or
   * arguments (and other errors), the derived mcpl::IOError for failed I/O
   * operations (e.g. when opening or writing files), and `std::bad_alloc`
   * when memory allocation fails. After an error while reading particles, or
   * while writing data to an output file, the file object can only be closed
   * (and further calls give the same error). Other errors, like invalid
   * arguments, leave the file usable.
   */
  class Error : public std::runtime_error {
  public:
    /**
     * @brief Error with the given message.
     *
     * @param msg The error message.
     */
    explicit Error( const std::string& msg ) : std::runtime_error(msg) {}
  };

  /** @brief Failed I/O operations (e.g. when opening or writing files). */
  class IOError : public Error {
  public:
    /**
     * @brief Error with the given message.
     *
     * @param msg The error message.
     */
    explicit IOError( const std::string& msg ) : Error(msg) {}
  };

  //////////////////////////////////////////////////////////////////////////////
  // Implementation details

  namespace detail {

    [[noreturn]] inline void throw_error( const mcpl_errstate_t& es )
    {
      if ( es.code == MCPL_ERROR_MEMORY )
        throw std::bad_alloc();
      if ( es.code == MCPL_ERROR_IO )
        throw IOError(es.msg);
      throw Error(es.msg);
    }

    [[noreturn]] inline void throw_runtime( const std::string& msg )
    {
      throw Error(msg);
    }

    //Sizes passed to the C API as 32 bit integers:
    inline std::uint32_t to_uint32( std::size_t n, const char * what )
    {
      if constexpr ( sizeof(std::size_t) > sizeof(std::uint32_t) ) {
        if ( n > std::size_t(0xFFFFFFFF) )
          throw_runtime(what);
      }
      return static_cast<std::uint32_t>(n);
    }

    //Error state passed to the C functions, throwing in check() in case of
    //errors:
    class ErrState {
    public:
      ErrState() noexcept { m_es.code = 0; }
      mcpl_errstate_t* get() noexcept { return &m_es; }
      operator mcpl_errstate_t*() noexcept { return &m_es; }
      void check() const { if ( m_es.code ) throw_error(m_es); }
    private:
      mcpl_errstate_t m_es;
    };

    inline std::string path_to_utf8( const std::filesystem::path& p )
    {
#if defined(__cpp_char8_t) && __cpp_char8_t >= 201811L
      std::u8string s = p.u8string();
      return std::string( reinterpret_cast<const char*>(s.data()), s.size() );
#else
      return p.u8string();
#endif
    }

    //Filenames given as std::filesystem::path, std::string, std::string_view
    //or C strings (only meant to be used for function arguments):
    class FilenameArg {
    public:
      FilenameArg( const char * s ) : m_cstr(s) {}
      FilenameArg( const std::string& s ) : m_cstr(s.c_str()) {}
      FilenameArg( std::string_view s ) : m_buf(s), m_cstr(m_buf.c_str()) {}
      FilenameArg( const std::filesystem::path& p )
        : m_buf(path_to_utf8(p)), m_cstr(m_buf.c_str()) {}
      FilenameArg( const FilenameArg& ) = delete;
      FilenameArg& operator=( const FilenameArg& ) = delete;
      const char * c_str() const noexcept { return m_cstr; }
    private:
      std::string m_buf;
      const char * m_cstr;
    };

    inline std::string to_utf8( const char * s ) { return s ? s : ""; }
    inline std::string to_utf8( const std::string& s ) { return s; }
    inline std::string to_utf8( std::string_view s ) { return std::string(s); }
    inline std::string to_utf8( const std::filesystem::path& p )
    {
      return path_to_utf8(p);
    }

    //Filenames as C strings (for the C functions taking lists of files):
    class FilenameList {
    public:
      template<class Range>
      explicit FilenameList( const Range& files )
      {
        for ( const auto& f : files )
          m_names.push_back( to_utf8(f) );
        init_ptrs();
      }
      unsigned size() const
      {
        return to_uint32( m_ptrs.size(), "too many files" );
      }
      const char ** data() noexcept { return m_ptrs.data(); }
    private:
      void init_ptrs()
      {
        m_ptrs.reserve(m_names.size());
        for ( const auto& n : m_names )
          m_ptrs.push_back( n.c_str() );
      }
      std::vector<std::string> m_names;
      std::vector<const char*> m_ptrs;
    };

    //Userdata types (as named in layouts):
    template<class T> struct UDType;
    template<> struct UDType<std::int8_t>   { static constexpr const char * name = "int8"; };
    template<> struct UDType<std::uint8_t>  { static constexpr const char * name = "uint8"; };
    template<> struct UDType<std::int16_t>  { static constexpr const char * name = "int16"; };
    template<> struct UDType<std::uint16_t> { static constexpr const char * name = "uint16"; };
    template<> struct UDType<std::int32_t>  { static constexpr const char * name = "int32"; };
    template<> struct UDType<std::uint32_t> { static constexpr const char * name = "uint32"; };
    template<> struct UDType<std::int64_t>  { static constexpr const char * name = "int64"; };
    template<> struct UDType<std::uint64_t> { static constexpr const char * name = "uint64"; };
    template<> struct UDType<float>         { static constexpr const char * name = "float32"; };
    template<> struct UDType<double>        { static constexpr const char * name = "float64"; };

    template<class T>
    constexpr bool is_ud_type_v = ( std::is_same_v<T,std::int8_t>
                                    || std::is_same_v<T,std::uint8_t>
                                    || std::is_same_v<T,std::int16_t>
                                    || std::is_same_v<T,std::uint16_t>
                                    || std::is_same_v<T,std::int32_t>
                                    || std::is_same_v<T,std::uint32_t>
                                    || std::is_same_v<T,std::int64_t>
                                    || std::is_same_v<T,std::uint64_t>
                                    || std::is_same_v<T,float>
                                    || std::is_same_v<T,double> );

    //Type of a field as in layouts, e.g. "float32" or "float32[3]":
    template<class T, std::size_t N>
    std::string ud_type_str()
    {
      std::string s = UDType<T>::name;
      if constexpr ( N > 0 ) {
        s += '[';
        s += std::to_string(N);
        s += ']';
      }
      return s;
    }

    //Print handler (the C++ function is passed as the context pointer of the C
    //handler, so it also works with several copies of this code in different
    //shared libraries - unlike a static mutex which might not):
    using PrintFct = std::function<void(const char*)>;

    extern "C" {
      inline void mcplcpp_print_trampoline( const char * msg,
                                            void * ctx ) noexcept
      {
        (*static_cast<PrintFct*>(ctx))(msg);
      }
    }

    struct PrintHandlerState {
      std::mutex mtx;
      std::unique_ptr<PrintFct> current;
    };

    inline PrintHandlerState& print_handler_state()
    {
      static PrintHandlerState state;
      return state;
    }

    //Output of dumps to a std::ostream (exceptions are rethrown after the C
    //function returns):
    struct DumpStream {
      std::ostream * os;
      std::exception_ptr eptr;
    };

    extern "C" {
      inline void mcplcpp_dump_trampoline( const char * msg,
                                           void * ctx ) noexcept
      {
        DumpStream * ds = static_cast<DumpStream*>(ctx);
        if ( ds->eptr )
          return;
        try {
          ds->os->write( msg, static_cast<std::streamsize>(std::strlen(msg)) );
        } catch (...) {
          ds->eptr = std::current_exception();
        }
      }
    }

  }//end of implementation details

  //////////////////////////////////////////////////////////////////////////////
  // Messages

  /**
   * @brief Pass all messages from MCPL to a function.
   *
   * MCPL prints some messages (e.g. warnings about files which were not
   * properly closed) to standard output by default. With this, they are
   * passed to the handler instead, for example:
   * @code{.cpp}
   * mcpl::set_print_handler( []( const char * msg )
   *                          { mylogger << msg; } );
   * @endcode
   *
   * Handlers should be set before using MCPL from several threads, and
   * handlers which might be called from several threads must be thread safe
   * themselves. Handlers must not throw exceptions (`std::terminate` is called
   * if they do).
   *
   * @param handler Function called with the messages, or `nullptr` (or an empty function) to restore the default.
   */
  inline void set_print_handler( std::function<void(const char*)> handler )
  {
    auto& state = detail::print_handler_state();
    std::lock_guard<std::mutex> lock(state.mtx);
    std::unique_ptr<detail::PrintFct> previous = std::move(state.current);
    if ( handler ) {
      state.current = std::make_unique<detail::PrintFct>(std::move(handler));
      mcpl_set_print_handler_ctx( detail::mcplcpp_print_trampoline,
                                  state.current.get() );
    } else {
      mcpl_set_print_handler( nullptr );
    }
  }

  //////////////////////////////////////////////////////////////////////////////
  // Header data of files being read

  /**
   * @brief View of a blob (bytes of data stored under a key in the header).
   *
   * Obtained from MCPLFile::blob, and valid as long as the file is open.
   * Blobs are stored byte for byte, so binary numbers in them are in the byte
   * order chosen by the application that wrote them.
   */
  class BlobView {
  public:
    /** @brief Empty view. */
    BlobView() noexcept = default;
    /**
     * @brief View of the given bytes.
     *
     * @param bytes The bytes.
     * @param nbytes Number of bytes.
     */
    BlobView( const std::uint8_t * bytes, std::size_t nbytes ) noexcept
      : m_data(bytes), m_size(nbytes) {}
    /** @brief The bytes. */
    const std::uint8_t * data() const noexcept { return m_data; }
    /** @brief Number of bytes. */
    std::size_t size() const noexcept { return m_size; }
    /** @brief Whether there are no bytes. */
    bool empty() const noexcept { return m_size == 0; }
    /**
     * @brief Byte number `i`.
     *
     * @param i Index of the byte.
     */
    std::uint8_t operator[]( std::size_t i ) const noexcept { return m_data[i]; }
    /** @brief Begin iterator for range-based for loops over the bytes. */
    const std::uint8_t * begin() const noexcept { return m_data; }
    /** @brief End iterator for range-based for loops over the bytes. */
    const std::uint8_t * end() const noexcept { return m_data + m_size; }
  private:
    const std::uint8_t * m_data = nullptr;
    std::size_t m_size = 0;
  };

  /**
   * @brief View of a list of strings in the header (comments or blob keys).
   *
   * Obtained from MCPLFile::comments and MCPLFile::blob_keys, and valid as
   * long as the file is open. It supports `size()`, `[i]` and range-based for
   * loops, giving `std::string_view` values:
   * @code{.cpp}
   * for ( auto c : f.comments() )
   *   std::cout << c << std::endl;
   * @endcode
   */
  class StringListView {
  public:
    /** @brief Random access iterator over the strings. */
    class iterator {
    public:
      using iterator_category = std::random_access_iterator_tag;
      using value_type = std::string_view;
      using difference_type = std::ptrdiff_t;
      using pointer = void;
      using reference = std::string_view;
      iterator() noexcept = default;
      iterator( const StringListView * v, std::size_t i ) noexcept : m_v(v), m_i(i) {}
      std::string_view operator*() const { return (*m_v)[m_i]; }
      std::string_view operator[]( difference_type n ) const
      {
        return (*m_v)[ static_cast<std::size_t>( static_cast<difference_type>(m_i) + n ) ];
      }
      iterator& operator++() noexcept { ++m_i; return *this; }
      iterator operator++(int) noexcept { iterator r = *this; ++m_i; return r; }
      iterator& operator--() noexcept { --m_i; return *this; }
      iterator operator--(int) noexcept { iterator r = *this; --m_i; return r; }
      iterator& operator+=( difference_type n ) noexcept
      {
        m_i = static_cast<std::size_t>( static_cast<difference_type>(m_i) + n );
        return *this;
      }
      iterator& operator-=( difference_type n ) noexcept { return *this += -n; }
      friend iterator operator+( iterator a, difference_type n ) noexcept { return a += n; }
      friend iterator operator+( difference_type n, iterator a ) noexcept { return a += n; }
      friend iterator operator-( iterator a, difference_type n ) noexcept { return a -= n; }
      friend difference_type operator-( const iterator& a, const iterator& b ) noexcept
      {
        return static_cast<difference_type>(a.m_i) - static_cast<difference_type>(b.m_i);
      }
      friend bool operator==( const iterator& a, const iterator& b ) noexcept { return a.m_i == b.m_i; }
      friend bool operator!=( const iterator& a, const iterator& b ) noexcept { return a.m_i != b.m_i; }
      friend bool operator<( const iterator& a, const iterator& b ) noexcept { return a.m_i < b.m_i; }
      friend bool operator>( const iterator& a, const iterator& b ) noexcept { return a.m_i > b.m_i; }
      friend bool operator<=( const iterator& a, const iterator& b ) noexcept { return a.m_i <= b.m_i; }
      friend bool operator>=( const iterator& a, const iterator& b ) noexcept { return a.m_i >= b.m_i; }
    private:
      const StringListView * m_v = nullptr;
      std::size_t m_i = 0;
    };
    /** @brief Number of strings. */
    std::size_t size() const noexcept { return m_size; }
    /** @brief Whether there are no strings. */
    bool empty() const noexcept { return m_size == 0; }
    /**
     * @brief String number `i`.
     *
     * @param i Index of the string.
     * @throws std::out_of_range for invalid indices.
     */
    std::string_view operator[]( std::size_t i ) const
    {
      if ( i >= m_size )
        throw std::out_of_range("index out of range");
      if ( m_keys )
        return m_keys[i];
      detail::ErrState es;
      const char * c = mcpl_hdr_comment_es( m_file, static_cast<unsigned>(i), es );
      es.check();
      return c;
    }
    /** @brief Begin iterator for range-based for loops. */
    iterator begin() const noexcept { return iterator(this,0); }
    /** @brief End iterator for range-based for loops. */
    iterator end() const noexcept { return iterator(this,m_size); }
  private:
    friend class MCPLFile;
    StringListView( mcpl_file_t f, std::size_t n, const char ** keys ) noexcept
      : m_file(f), m_size(n), m_keys(keys) {}
    mcpl_file_t m_file;
    std::size_t m_size;
    const char ** m_keys;//blob keys (NULL for comments)
  };

  //////////////////////////////////////////////////////////////////////////////
  // Particles

  template<class T, std::size_t N> class UserdataField;

  /**
   * @brief Values of particles, common to mcpl::Particle and mcpl::OutParticle.
   *
   * These are the members of `mcpl_particle_t` in the C API.
   *
   * @tparam Derived The particle class (mcpl::Particle or mcpl::OutParticle).
   */
  template<class Derived>
  class ParticleAccessors {
  public:
    /** @name Particle values */
    ///@{
    /** @brief Kinetic energy [MeV]. */
    double ekin() const noexcept { return s().ekin; }
    /** @brief Position [cm]. */
    std::array<double,3> position() const noexcept
    {
      return { s().position[0], s().position[1], s().position[2] };
    }
    /** @brief Direction (unit vector). */
    std::array<double,3> direction() const noexcept
    {
      return { s().direction[0], s().direction[1], s().direction[2] };
    }
    /** @brief Polarisation vector. */
    std::array<double,3> polarisation() const noexcept
    {
      return { s().polarisation[0], s().polarisation[1], s().polarisation[2] };
    }
    /** @brief Position: x coordinate [cm]. */
    double x() const noexcept { return s().position[0]; }
    /** @brief Position: y coordinate [cm]. */
    double y() const noexcept { return s().position[1]; }
    /** @brief Position: z coordinate [cm]. */
    double z() const noexcept { return s().position[2]; }
    /** @brief Direction: x component. */
    double ux() const noexcept { return s().direction[0]; }
    /** @brief Direction: y component. */
    double uy() const noexcept { return s().direction[1]; }
    /** @brief Direction: z component. */
    double uz() const noexcept { return s().direction[2]; }
    /** @brief Polarisation: x component. */
    double polx() const noexcept { return s().polarisation[0]; }
    /** @brief Polarisation: y component. */
    double poly() const noexcept { return s().polarisation[1]; }
    /** @brief Polarisation: z component. */
    double polz() const noexcept { return s().polarisation[2]; }
    /** @brief Time [ms]. */
    double time() const noexcept { return s().time; }
    /** @brief Weight or intensity. */
    double weight() const noexcept { return s().weight; }
    /** @brief Particle type (PDG code, e.g. 2112 for neutrons and 22 for gammas). */
    std::int32_t pdgcode() const noexcept { return s().pdgcode; }
    /** @brief User flags (32 bits). */
    std::uint32_t userflags() const noexcept { return s().userflags; }
    /** @brief The particle as the `mcpl_particle_t` struct of the C API. */
    const mcpl_particle_t& c_struct() const noexcept { return s(); }
    ///@}
  private:
    const mcpl_particle_t& s() const noexcept
    {
      return *static_cast<const Derived*>(this)->m_p;
    }
  };

  /**
   * @brief Particle read from a file.
   *
   * This is a lightweight view of the particle data in the file object,
   * which is only valid until the next particle is read from the file (or
   * the file is closed). Default constructed objects (and the particles
   * returned by MCPLFile::read at the end of the file) are empty, which can
   * be tested by converting them to `bool`. Accessing the data of empty
   * particles is not allowed. The userdata of particles is read with
   * mcpl::UserdataField objects.
   */
  class Particle : public ParticleAccessors<Particle> {
  public:
    /** @brief Empty particle. */
    Particle() noexcept = default;
    /** @brief Whether the particle is not empty. */
    explicit operator bool() const noexcept { return m_p != nullptr; }
    /**
     * @brief Raw userdata bytes (`nullptr` if the file has no userdata).
     *
     * These are normally accessed with mcpl::UserdataField objects instead.
     */
    const std::uint8_t * raw_userdata() const noexcept { return m_ud; }
    /** @brief Number of userdata bytes. */
    std::uint32_t userdata_size() const noexcept { return m_udsize; }
  private:
    friend class ParticleAccessors<Particle>;
    friend class MCPLFile;
    Particle( const mcpl_particle_t * p, const std::uint8_t * ud,
              std::uint32_t udsize ) noexcept
      : m_p(p), m_ud(ud), m_udsize(udsize) {}
    const mcpl_particle_t * m_p = nullptr;
    const std::uint8_t * m_ud = nullptr;
    std::uint32_t m_udsize = 0;
  };

  /**
   * @brief Particle to be added to an output file.
   *
   * Obtained from MCPLOutFile::new_particle, and added with
   * MCPLOutFile::add. It refers to data in the file object, and is only
   * valid as long as the file is open. All values are kept after adding the
   * particle, so only changed values need to be set before adding the next
   * particle. Values can be read with the same methods as for
   * mcpl::Particle.
   */
  class OutParticle : public ParticleAccessors<OutParticle> {
  public:
    /** @brief Empty particle (which can not be added to files). */
    OutParticle() noexcept = default;
    /** @name Setting values */
    ///@{
    /**
     * @brief Set the kinetic energy [MeV].
     *
     * @param v The value.
     */
    void set_ekin( double v ) noexcept { m_p->ekin = v; }
    /**
     * @brief Set the position [cm].
     *
     * @param posx x coordinate.
     * @param posy y coordinate.
     * @param posz z coordinate.
     */
    void set_position( double posx, double posy, double posz ) noexcept
    {
      m_p->position[0] = posx; m_p->position[1] = posy;
      m_p->position[2] = posz;
    }
    /**
     * @brief Set the position [cm].
     *
     * @param v The coordinates.
     */
    void set_position( const std::array<double,3>& v ) noexcept
    {
      set_position(v[0],v[1],v[2]);
    }
    /**
     * @brief Set the direction (unit vector).
     *
     * @param dirx x component.
     * @param diry y component.
     * @param dirz z component.
     */
    void set_direction( double dirx, double diry, double dirz ) noexcept
    {
      m_p->direction[0] = dirx; m_p->direction[1] = diry;
      m_p->direction[2] = dirz;
    }
    /**
     * @brief Set the direction (unit vector).
     *
     * @param v The components.
     */
    void set_direction( const std::array<double,3>& v ) noexcept
    {
      set_direction(v[0],v[1],v[2]);
    }
    /**
     * @brief Set the polarisation vector.
     *
     * @param polarx x component.
     * @param polary y component.
     * @param polarz z component.
     */
    void set_polarisation( double polarx, double polary,
                           double polarz ) noexcept
    {
      m_p->polarisation[0] = polarx; m_p->polarisation[1] = polary;
      m_p->polarisation[2] = polarz;
    }
    /**
     * @brief Set the polarisation vector.
     *
     * @param v The components.
     */
    void set_polarisation( const std::array<double,3>& v ) noexcept
    {
      set_polarisation(v[0],v[1],v[2]);
    }
    /**
     * @brief Set the x coordinate of the position [cm].
     *
     * @param v The value.
     */
    void set_x( double v ) noexcept { m_p->position[0] = v; }
    /**
     * @brief Set the y coordinate of the position [cm].
     *
     * @param v The value.
     */
    void set_y( double v ) noexcept { m_p->position[1] = v; }
    /**
     * @brief Set the z coordinate of the position [cm].
     *
     * @param v The value.
     */
    void set_z( double v ) noexcept { m_p->position[2] = v; }
    /**
     * @brief Set the x component of the direction.
     *
     * @param v The value.
     */
    void set_ux( double v ) noexcept { m_p->direction[0] = v; }
    /**
     * @brief Set the y component of the direction.
     *
     * @param v The value.
     */
    void set_uy( double v ) noexcept { m_p->direction[1] = v; }
    /**
     * @brief Set the z component of the direction.
     *
     * @param v The value.
     */
    void set_uz( double v ) noexcept { m_p->direction[2] = v; }
    /**
     * @brief Set the x component of the polarisation.
     *
     * @param v The value.
     */
    void set_polx( double v ) noexcept { m_p->polarisation[0] = v; }
    /**
     * @brief Set the y component of the polarisation.
     *
     * @param v The value.
     */
    void set_poly( double v ) noexcept { m_p->polarisation[1] = v; }
    /**
     * @brief Set the z component of the polarisation.
     *
     * @param v The value.
     */
    void set_polz( double v ) noexcept { m_p->polarisation[2] = v; }
    /**
     * @brief Set the time [ms].
     *
     * @param v The value.
     */
    void set_time( double v ) noexcept { m_p->time = v; }
    /**
     * @brief Set the weight or intensity.
     *
     * @param v The value.
     */
    void set_weight( double v ) noexcept { m_p->weight = v; }
    /**
     * @brief Set the particle type (PDG code).
     *
     * @param v The value.
     */
    void set_pdgcode( std::int32_t v ) noexcept { m_p->pdgcode = v; }
    /**
     * @brief Set the user flags (32 bits).
     *
     * @param v The value.
     */
    void set_userflags( std::uint32_t v ) noexcept { m_p->userflags = v; }
    ///@}

    /** @name Userdata */
    ///@{
    /**
     * @brief Set the value of a userdata field (see mcpl::UserdataField).
     *
     * Values of single-value fields are converted to the type of the field,
     * and values of array fields can be given as `T[N]`.
     *
     * @tparam T Type of the values of the field.
     * @tparam N Number of values of array fields (0 for single values).
     * @tparam V Type of the value.
     * @param field The field.
     * @param value The value.
     */
    template<class T, std::size_t N, class V>
    void set_userdata( const UserdataField<T,N>& field, const V& value );
    /**
     * @brief Set the values of an array field.
     *
     * The values can also be given as braced lists, like `{0.0f, 0.6f, 0.8f}`.
     *
     * @tparam T Type of the values of the field.
     * @tparam N Number of values of array fields (0 for single values).
     * @param field The field.
     * @param values The values.
     */
    template<class T, std::size_t N, class = std::enable_if_t<(N>0)>>
    void set_userdata( const UserdataField<T,N>& field,
                       const std::array<T,N>& values );
    /**
     * @brief Set one element of an array field.
     *
     * @tparam T Type of the values of the field.
     * @tparam N Number of values of array fields (0 for single values).
     * @param field The field.
     * @param i Index of the element.
     * @param value The value.
     * @throws std::out_of_range if `i>=N`.
     */
    template<class T, std::size_t N>
    void set_userdata( const UserdataField<T,N>& field, std::size_t i,
                       T value );


    /** @brief Raw userdata bytes (`nullptr` if the file has no userdata). */
    std::uint8_t * raw_userdata() noexcept { return m_ud; }
    /** @brief Raw userdata bytes (`nullptr` if the file has no userdata). */
    const std::uint8_t * raw_userdata() const noexcept { return m_ud; }
    /** @brief Number of userdata bytes. */
    std::uint32_t userdata_size() const noexcept { return m_udsize; }
    ///@}

    /**
     * @brief The particle as the `mcpl_particle_t` struct of the C API.
     *
     * This allows direct modification of the values.
     */
    mcpl_particle_t& c_struct() noexcept { return *m_p; }
    using ParticleAccessors<OutParticle>::c_struct;
  private:
    friend class ParticleAccessors<OutParticle>;
    friend class MCPLOutFile;
    OutParticle( mcpl_particle_t * p, std::uint8_t * ud, std::uint32_t udsize,
                 const void * owner ) noexcept
      : m_p(p), m_ud(ud), m_udsize(udsize), m_owner(owner) {}
    mcpl_particle_t * m_p = nullptr;
    std::uint8_t * m_ud = nullptr;
    std::uint32_t m_udsize = 0;
    const void * m_owner = nullptr;
  };

  //////////////////////////////////////////////////////////////////////////////
  // Userdata fields

  /**
   * @brief Access to a field of the userdata of particles.
   *
   * Objects are obtained from MCPLFile::userdata_field or from
   * MCPLOutFile::add_userdata_field (or MCPLOutFile::userdata_field), which
   * check that the field exists with exactly this type, so that their use is
   * efficient. Values are read with `field(particle)` (and array elements with
   * `field(particle,i)`), and set with OutParticle::set_userdata:
   * @code{.cpp}
   * mcpl::MCPLFile f("myfile.mcpl");
   * //For "temp:float32,dir:float32[3]":
   * auto temp = f.userdata_field<float>("temp");
   * auto dir = f.userdata_field<float,3>("dir");
   * for ( auto p : f ) {
   *   float t = temp(p);
   *   std::array<float,3> d = dir(p);
   *   float dz = dir(p,2);//(single element)
   * }
   * @endcode
   *
   * Fields can be used with particles from any file (e.g. when reading
   * several files with the same layout), but give errors if the userdata of
   * the particle is too short.
   *
   * @tparam T Type of the values: `std::int8_t`, `std::uint8_t`, ..., `std::uint64_t`, `float` or `double`, for the types `int8`, `uint8`, ..., `uint64`, `float32` and `float64` in layouts.
   * @tparam N Number of values of array fields (0, the default, for single values).
   */
  template<class T, std::size_t N = 0>
  class UserdataField {
    static_assert( detail::is_ud_type_v<T>,
                   "Userdata fields must have type std::int8_t, std::uint8_t,"
                   " std::int16_t, std::uint16_t, std::int32_t, std::uint32_t,"
                   " std::int64_t, std::uint64_t, float or double" );
  public:
    /** @brief Number of values (1 for single-value fields). */
    static constexpr std::size_t nvalues = ( N == 0 ? 1 : N );
    /** @brief Number of bytes of the field. */
    static constexpr std::size_t nbytes = nvalues * sizeof(T);
    /** @brief Type of values: `T` for single-value fields, `std::array<T,N>` for array fields. */
    using value_type = std::conditional_t< N == 0, T, std::array<T,(N==0?1:N)> >;

    /**
     * @brief Field object which is not associated with any field.
     *
     * Such objects can not be used with particles.
     */
    UserdataField() noexcept = default;
    /** @brief Offset of the field in the userdata [bytes]. */
    std::uint32_t offset() const noexcept { return m_offset; }
    /** @brief Number of values (1 for single-value fields). */
    std::size_t size() const noexcept { return nvalues; }

    /**
     * @brief Value of the field.
     *
     * @param p The particle.
     * @throws mcpl::Error if the particle has no (or too short) userdata.
     */
    value_type operator()( const Particle& p ) const
    {
      return get( p.raw_userdata(), p.userdata_size() );
    }
    /**
     * @brief Value of the field.
     *
     * @param p The particle.
     * @throws mcpl::Error if the particle has no (or too short) userdata.
     */
    value_type operator()( const OutParticle& p ) const
    {
      return get( p.raw_userdata(), p.userdata_size() );
    }
    /**
     * @brief Element of an array field.
     *
     * @param p The particle.
     * @param i Index of the element.
     * @throws std::out_of_range if `i>=N`, and mcpl::Error if the particle has no (or too short) userdata.
     */
    T operator()( const Particle& p, std::size_t i ) const
    {
      return get_element( p.raw_userdata(), p.userdata_size(), i );
    }
    /**
     * @brief Element of an array field.
     *
     * @param p The particle.
     * @param i Index of the element.
     * @throws std::out_of_range if `i>=N`, and mcpl::Error if the particle has no (or too short) userdata.
     */
    T operator()( const OutParticle& p, std::size_t i ) const
    {
      return get_element( p.raw_userdata(), p.userdata_size(), i );
    }

  private:
    friend class MCPLFile;
    friend class MCPLOutFile;
    friend class OutParticle;
    explicit UserdataField( std::uint32_t offset ) noexcept : m_offset(offset) {}

    void check( const void * ud, std::uint32_t udsize ) const
    {
      if ( !ud || static_cast<std::uint64_t>(m_offset) + nbytes > udsize )
        detail::throw_runtime( ud ? "userdata of particle is too short for"
                                    " the userdata field"
                                  : "particle has no userdata" );
    }
    value_type get( const std::uint8_t * ud, std::uint32_t udsize ) const
    {
      check(ud,udsize);
      value_type v;
      std::memcpy( &v, ud + m_offset, nbytes );
      return v;
    }
    T get_element( const std::uint8_t * ud, std::uint32_t udsize,
                   std::size_t i ) const
    {
      static_assert( N > 0, "element access is only for array fields" );
      if ( i >= N )
        throw std::out_of_range("userdata array index out of range");
      check(ud,udsize);
      T v;
      std::memcpy( &v, ud + m_offset + i * sizeof(T), sizeof(T) );
      return v;
    }
    void set( std::uint8_t * ud, std::uint32_t udsize, const T * values ) const
    {
      check(ud,udsize);
      std::memcpy( ud + m_offset, values, nbytes );
    }
    void set_element( std::uint8_t * ud, std::uint32_t udsize,
                      std::size_t i, T value ) const
    {
      static_assert( N > 0, "element access is only for array fields" );
      if ( i >= N )
        throw std::out_of_range("userdata array index out of range");
      check(ud,udsize);
      std::memcpy( ud + m_offset + i * sizeof(T), &value, sizeof(T) );
    }
    std::uint32_t m_offset = 0;
  };

  template<class T, std::size_t N, class V>
  inline void OutParticle::set_userdata( const UserdataField<T,N>& field,
                                         const V& value )
  {
    if constexpr ( N == 0 ) {
      static_assert( std::is_convertible_v<V,T>,
                     "value can not be converted to the type of the field" );
      const T v = static_cast<T>(value);
      field.set( m_ud, m_udsize, &v );
    } else if constexpr ( std::is_same_v<V,T[N]> ) {
      field.set( m_ud, m_udsize, &value[0] );
    } else {
      static_assert( std::is_same_v<V,std::array<T,N>>,
                     "values of array fields must be given as std::array<T,N>"
                     " or T[N]" );
    }
  }

  template<class T, std::size_t N, class>
  inline void OutParticle::set_userdata( const UserdataField<T,N>& field,
                                         const std::array<T,N>& values )
  {
    field.set( m_ud, m_udsize, values.data() );
  }

  template<class T, std::size_t N>
  inline void OutParticle::set_userdata( const UserdataField<T,N>& field,
                                         std::size_t i, T value )
  {
    field.set_element( m_ud, m_udsize, i, value );
  }

  //////////////////////////////////////////////////////////////////////////////
  // Reading files

  /** @brief Parts of files shown by MCPLFile::dump. */
  enum class DumpParts { All = 0, Header = 1, Particles = 2 };

  /** @brief Whether mcpl::forcemerge_files keeps the userflags of particles. */
  enum class KeepUserflags { No, Yes };

  /**
   * @brief File being read.
   *
   * Files are opened by the constructor, and closed when the object is
   * destroyed (or with close()). Objects can be moved (e.g. into
   * containers), but not copied. Particles are read with range-based for
   * loops, or with read():
   * @code{.cpp}
   * mcpl::MCPLFile f("myfile.mcpl");
   * for ( auto p : f )
   *   std::cout << p.ekin() << std::endl;
   * @endcode
   */
  class MCPLFile {
  public:
    /**
     * @brief Open the file.
     *
     * Gzipped files (with names ending in `.gz`) can be read directly.
     *
     * @param filename Name of the file.
     * @throws mcpl::IOError if the file can not be read, and mcpl::Error if it is not a valid MCPL file.
     */
    explicit MCPLFile( detail::FilenameArg filename )
    {
      detail::ErrState es;
      m_f = mcpl_open_file_es( filename.c_str(), es );
      if ( es.get()->code ) {
        mcpl_close_file( m_f );
        es.check();
      }
      m_udsize = mcpl_hdr_userdata_size( m_f );
    }
    /** @brief Closes the file. */
    ~MCPLFile() { close(); }
    MCPLFile( const MCPLFile& ) = delete;
    MCPLFile& operator=( const MCPLFile& ) = delete;
    /**
     * @brief Move constructor (o is left closed).
     *
     * @param o The file object moved from.
     */
    MCPLFile( MCPLFile&& o ) noexcept : m_f(o.m_f), m_udsize(o.m_udsize)
    {
      o.m_f.internal = nullptr;
    }
    /**
     * @brief Move assignment (closing any file of this object first).
     *
     * @param o The file object moved from.
     * @return This object.
     */
    MCPLFile& operator=( MCPLFile&& o ) noexcept
    {
      if ( this != &o ) {
        close();
        m_f = o.m_f;
        m_udsize = o.m_udsize;
        o.m_f.internal = nullptr;
      }
      return *this;
    }

    /** @brief Close the file (does nothing if it is not open). */
    void close() noexcept
    {
      if ( m_f.internal ) {
        mcpl_close_file( m_f );
        m_f.internal = nullptr;
      }
    }
    /** @brief Whether the file is open (not closed or moved from). */
    bool is_open() const noexcept { return m_f.internal != nullptr; }

    /** @name Header data */
    ///@{
    /**
     * @brief MCPL format version of the file.
     *
     * Strings are views of data in the file object, valid as long as the file is open.
     */
    unsigned version() const { return mcpl_hdr_version( h() ); }
    /** @brief Number of particles in the file. */
    std::uint64_t nparticles() const { return mcpl_hdr_nparticles( h() ); }
    /** @brief Name of the application which created the file. */
    std::string_view srcname() const { return mcpl_hdr_srcname( h() ); }
    /** @brief Number of comments. */
    std::size_t ncomments() const { return mcpl_hdr_ncomments( h() ); }
    /**
     * @brief Comment number `i`.
     *
     * @param i Index of the comment.
     * @throws std::out_of_range for invalid indices.
     */
    std::string_view comment( std::size_t i ) const { return comments()[i]; }
    /** @brief List of all comments. */
    StringListView comments() const
    {
      mcpl_file_t f = h();
      return StringListView( f, mcpl_hdr_ncomments( f ), nullptr );
    }
    /** @brief Number of blobs (binary data stored by key). */
    std::size_t nblobs() const
    {
      return static_cast<std::size_t>( mcpl_hdr_nblobs( h() ) );
    }
    /** @brief List of the keys of all blobs. */
    StringListView blob_keys() const
    {
      const char ** keys = mcpl_hdr_blobkeys( h() );
      return StringListView( m_f, keys ? nblobs() : 0, keys );
    }
    /**
     * @brief Whether there is a blob with the key.
     *
     * @param key The key.
     */
    bool has_blob( std::string_view key ) const
    {
      uint32_t ldata;
      const char * data;
      return mcpl_hdr_blob( h(), std::string(key).c_str(), &ldata, &data ) != 0;
    }
    /**
     * @brief The blob with the key.
     *
     * @param key The key.
     * @throws mcpl::Error if there is no blob with the key.
     */
    BlobView blob( std::string_view key ) const
    {
      uint32_t ldata = 0;
      const char * data = nullptr;
      std::string k(key);
      if ( !mcpl_hdr_blob( h(), k.c_str(), &ldata, &data ) )
        detail::throw_runtime( "no blob with key \"" + k + "\"" );
      return BlobView( reinterpret_cast<const std::uint8_t*>(data), ldata );
    }
    /** @brief Whether particles in the file have userflags. */
    bool has_userflags() const { return mcpl_hdr_has_userflags( h() ) != 0; }
    /** @brief Whether particles in the file have polarisation. */
    bool has_polarisation() const { return mcpl_hdr_has_polarisation( h() ) != 0; }
    /** @brief Whether values are stored in double precision. */
    bool has_doubleprec() const { return mcpl_hdr_has_doubleprec( h() ) != 0; }
    /** @brief Number of bytes used by the header (uncompressed). */
    std::uint64_t header_size() const { return mcpl_hdr_header_size( h() ); }
    /** @brief Number of bytes used per particle (uncompressed). */
    int particle_size() const { return mcpl_hdr_particle_size( h() ); }
    /** @brief PDG code of all particles (0 if particles have individual PDG codes). */
    std::int32_t universal_pdgcode() const { return mcpl_hdr_universal_pdgcode( h() ); }
    /** @brief Weight of all particles (0.0 if particles have individual weights). */
    double universal_weight() const { return mcpl_hdr_universal_weight( h() ); }
    /** @brief Whether numbers are stored in little endian byte order. */
    bool little_endian() const { return mcpl_hdr_little_endian( h() ) != 0; }

    /**
     * @brief Whether there is a stat:sum entry with the key.
     *
     * @param key The key.
     */
    bool has_stat_sum( std::string_view key ) const
    {
      return stat_sum_raw(key) != -2.0;
    }
    /**
     * @brief Value of a stat:sum entry.
     *
     * @param key The key.
     * @return The value, or an empty value if it is not available (-1 in the file, e.g. if the program writing the file crashed).
     * @throws mcpl::Error if there is no entry with the key.
     */
    std::optional<double> stat_sum( std::string_view key ) const
    {
      double v = stat_sum_raw(key);
      if ( v == -2.0 )
        detail::throw_runtime( "no stat:sum entry with key \""
                               + std::string(key) + "\"" );
      if ( v == -1.0 )
        return std::nullopt;
      return v;
    }

    /** @brief Layout of the userdata (empty if the file has no userdata). */
    std::string_view userdata_layout() const
    {
      const char * l = mcpl_hdr_userdata_layout( h() );
      return l ? l : std::string_view();
    }
    /** @brief Number of userdata bytes per particle. */
    std::uint32_t userdata_size() const { h(); return m_udsize; }

    /**
     * @brief Field in the userdata (see mcpl::UserdataField).
     *
     * For example `userdata_field<float>("temp")` for a field `temp:float32`, or `userdata_field<float,3>("dir")` for `dir:float32[3]`.
     *
     * @tparam T Type of the values of the field.
     * @tparam N Number of values of array fields (0 for single values).
     * @param name Name of the field.
     * @throws mcpl::Error if the file has no userdata, or the field does not exist with exactly this type.
     */
    template<class T, std::size_t N = 0>
    UserdataField<T,N> userdata_field( std::string_view name ) const
    {
      const char * l = mcpl_hdr_userdata_layout( h() );
      if ( !l )
        detail::throw_runtime( "file has no userdata" );
      detail::ErrState es;
      std::uint32_t off = mcpl_userdata_offset_es( l, std::string(name).c_str(),
                                                   detail::ud_type_str<T,N>().c_str(),
                                                   es );
      es.check();
      return UserdataField<T,N>(off);
    }
    ///@}

    /** @name Reading particles */
    ///@{
    /**
     * @brief Read the next particle.
     *
     * @return The particle, or an empty particle at the end of the file.
     */
    Particle read()
    {
      detail::ErrState es;
      const std::uint8_t * ud = nullptr;
      const mcpl_particle_t * p = mcpl_read_with_userdata_es( h(), &ud, es );
      es.check();
      return Particle( p, ud, ud ? m_udsize : 0 );
    }

    /**
     * @brief Skip particles.
     *
     * @param n Number of particles to skip.
     * @return Whether there is a particle at the new position.
     */
    bool skip_forward( std::uint64_t n )
    {
      detail::ErrState es;
      int r = mcpl_skipforward_es( h(), n, es );
      es.check();
      return r != 0;
    }
    /**
     * @brief Go to the first particle.
     *
     * @return Whether there is a particle at the new position.
     */
    bool rewind()
    {
      detail::ErrState es;
      int r = mcpl_rewind_es( h(), es );
      es.check();
      return r != 0;
    }
    /**
     * @brief Go to a particle.
     *
     * @param ipos Index of the particle.
     * @return Whether there is a particle at the new position.
     */
    bool seek( std::uint64_t ipos )
    {
      detail::ErrState es;
      int r = mcpl_seek_es( h(), ipos, es );
      es.check();
      return r != 0;
    }
    /** @brief Index of the next particle to be read. */
    std::uint64_t current_position() const { return mcpl_currentposition( h() ); }

    /** @brief Input iterator over the particles, for range-based for loops. */
    class iterator {
    public:
      using iterator_category = std::input_iterator_tag;
      using value_type = Particle;
      using difference_type = std::ptrdiff_t;
      using pointer = const Particle*;
      using reference = const Particle&;
      iterator() noexcept = default;
      const Particle& operator*() const noexcept { return m_p; }
      const Particle* operator->() const noexcept { return &m_p; }
      iterator& operator++() { m_p = m_f->read(); return *this; }
      iterator operator++(int) { iterator r = *this; ++*this; return r; }
      friend bool operator==( const iterator& a, const iterator& b ) noexcept
      {
        return !a.m_p && !b.m_p;
      }
      friend bool operator!=( const iterator& a, const iterator& b ) noexcept
      {
        return !( a == b );
      }
    private:
      friend class MCPLFile;
      explicit iterator( MCPLFile * f ) : m_f(f), m_p(f->read()) {}
      MCPLFile * m_f = nullptr;
      Particle m_p;
    };
    /** @brief Begin iterator for range-based for loops (reads from the current position). */
    iterator begin() { return iterator(this); }
    /** @brief End iterator for range-based for loops. */
    iterator end() noexcept { return iterator(); }
    ///@}

    /**
     * @brief Show the contents of the file (like `mcpl_dump`) through the print handler.
     *
     * The position in the file is not changed, but particles read before are no longer valid afterwards (also for MCPLOutFile::transfer_last_read_particle).
     *
     * @param parts Parts of the file to show.
     * @param nskip Index of the first particle shown.
     * @param nlimit Maximum number of particles shown (0 for all).
     */
    void dump( DumpParts parts = DumpParts::All, std::uint64_t nskip = 0,
               std::uint64_t nlimit = 0 )
    {
      detail::ErrState es;
      mcpl_dump_file_es( h(), static_cast<int>(parts), nskip, nlimit,
                         nullptr, nullptr, es );
      es.check();
    }
    /**
     * @brief Show the contents of the file (like `mcpl_dump`) on a stream.
     *
     * @param os The stream.
     * @param parts Parts of the file to show.
     * @param nskip Index of the first particle shown.
     * @param nlimit Maximum number of particles shown (0 for all).
     */
    void dump( std::ostream& os, DumpParts parts = DumpParts::All,
               std::uint64_t nskip = 0, std::uint64_t nlimit = 0 )
    {
      detail::ErrState es;
      detail::DumpStream ds{ &os, nullptr };
      mcpl_dump_file_es( h(), static_cast<int>(parts), nskip, nlimit,
                         detail::mcplcpp_dump_trampoline, &ds, es );
      if ( ds.eptr )
        std::rethrow_exception( ds.eptr );
      es.check();
    }

    /** @brief The file object of the C API (for direct use with the C functions). */
    mcpl_file_t c_handle() const noexcept { return m_f; }

  private:
    //Handle for the C functions without error states (which do not check for
    //invalid handles):
    mcpl_file_t h() const
    {
      if ( !m_f.internal )
        detail::throw_runtime( "MCPLFile object is not open" );
      return m_f;
    }
    double stat_sum_raw( std::string_view key ) const
    {
      detail::ErrState es;
      double v = mcpl_hdr_stat_sum_es( h(), std::string(key).c_str(), es );
      es.check();
      return v;
    }
    mcpl_file_t m_f = { nullptr };
    std::uint32_t m_udsize = 0;
  };

  //////////////////////////////////////////////////////////////////////////////
  // Writing files

  /**
   * @brief File being written.
   *
   * Files are created by the constructor, and only finished by close() (or
   * close_and_gzip()). Files which are not closed, for instance because an
   * exception was thrown while writing them, are left unfinished when the
   * object is destroyed (or when abandon() is called). Such files can often be
   * recovered with mcpl::repair. Objects can be moved, but not copied.
   */
  class MCPLOutFile {
  public:
    /**
     * @brief Create the file.
     *
     * @param filename Name of the file (`.mcpl` is appended if it does not end with `.mcpl`).
     * @throws mcpl::IOError if the file can not be created.
     */
    explicit MCPLOutFile( detail::FilenameArg filename )
    {
      detail::ErrState es;
      m_f = mcpl_create_outfile_es( filename.c_str(), es );
      if ( es.get()->code ) {
        detail::ErrState ignored;
        mcpl_close_outfile_unfinished_es( m_f, ignored );
        m_f.internal = nullptr;
        es.check();
      }
    }
    /** @brief Leaves the file unfinished, unless it was closed. */
    ~MCPLOutFile() { abandon(); }
    MCPLOutFile( const MCPLOutFile& ) = delete;
    MCPLOutFile& operator=( const MCPLOutFile& ) = delete;
    /**
     * @brief Move constructor (o is left closed).
     *
     * @param o The file object moved from.
     */
    MCPLOutFile( MCPLOutFile&& o ) noexcept
      : m_f(o.m_f), m_pending_layout(std::move(o.m_pending_layout)),
        m_ud(std::move(o.m_ud)), m_puser(o.m_puser),
        m_layout_locked(o.m_layout_locked)
    {
      o.m_f.internal = nullptr;
      o.m_puser = nullptr;
      o.m_layout_locked = false;
    }
    /**
     * @brief Move assignment (abandoning any file of this object first).
     *
     * @param o The file object moved from.
     * @return This object.
     */
    MCPLOutFile& operator=( MCPLOutFile&& o ) noexcept
    {
      if ( this != &o ) {
        abandon();
        m_f = o.m_f;
        m_pending_layout = std::move(o.m_pending_layout);
        m_ud = std::move(o.m_ud);
        m_puser = o.m_puser;
        m_layout_locked = o.m_layout_locked;
        o.m_f.internal = nullptr;
        o.m_puser = nullptr;
        o.m_layout_locked = false;
      }
      return *this;
    }

    /**
     * @brief Finish and close the file.
     *
     * Errors leave the file unfinished, and the object is closed in any case. Does nothing if the file is not open.
     */
    void close()
    {
      if ( !m_f.internal )
        return;
      finalise_layout_for_closing();
      detail::ErrState es;
      mcpl_outfile_t f = release();
      mcpl_close_outfile_es( f, es );
      es.check();
    }
    /** @brief Finish, close and compress the file (like close()). */
    void close_and_gzip()
    {
      if ( !m_f.internal )
        return;
      finalise_layout_for_closing();
      detail::ErrState es;
      mcpl_outfile_t f = release();
      mcpl_closeandgzip_outfile_es( f, es );
      es.check();
    }
    /**
     * @brief Close the file without finishing it, leaving it unfinished.
     *
     * Like the destructor. Errors are ignored.
     */
    void abandon() noexcept
    {
      if ( m_f.internal ) {
        //(an error state must be given, since errors would otherwise go to
        //the error handler, which by default ends the program):
        detail::ErrState ignored;
        mcpl_close_outfile_unfinished_es( release(), ignored );
      }
    }
    /** @brief Whether the file is open (not closed or moved from). */
    bool is_open() const noexcept { return m_f.internal != nullptr; }

    /** @brief Name of the file (valid as long as the file is open). */
    std::string_view filename() const { return mcpl_outfile_filename( h() ); }

    /** @name Header data and options */
    ///@{
    /**
     * @brief Set the name of the application creating the file.
     *
     * These must be set before the first particle is added (except stat:sum values, which can be updated until the file is closed).
     *
     * @param name The name.
     */
    void set_srcname( std::string_view name )
    {
      call( mcpl_hdr_set_srcname_es, std::string(name).c_str() );
    }
    /**
     * @brief Add a comment.
     *
     * @param comment The comment.
     */
    void add_comment( std::string_view comment )
    {
      call( mcpl_hdr_add_comment_es, std::string(comment).c_str() );
    }
    /**
     * @brief Add binary data under a key.
     *
     * @param key The key (unique, non-empty, ASCII, no non-printable
     *            characters, whitespace, backslash, or quotation marks).
     * @param data The data.
     * @param size Number of bytes.
     */
    void add_blob( std::string_view key, const void * data, std::size_t size )
    {
      call( mcpl_hdr_add_data_es, std::string(key).c_str(),
            detail::to_uint32( size, "blob too large" ),
            static_cast<const char*>(data) );
    }
    /**
     * @brief Add binary data under a key.
     *
     * @param key The key (unique, non-empty, ASCII, no non-printable
     *            characters, whitespace, backslash, or quotation marks).
     * @param data The data.
     */
    void add_blob( std::string_view key, const std::vector<std::uint8_t>& data )
    {
      add_blob( key, data.data(), data.size() );
    }
    /**
     * @brief Add binary data under a key.
     *
     * @param key The key (unique, non-empty, ASCII, no non-printable
     *            characters, whitespace, backslash, or quotation marks).
     * @param data The data.
     */
    void add_blob( std::string_view key, std::string_view data )
    {
      add_blob( key, data.data(), data.size() );
    }
    /** @brief Store the userflags of particles. */
    void enable_userflags() { call( mcpl_enable_userflags_es ); }
    /** @brief Store the polarisation of particles. */
    void enable_polarisation() { call( mcpl_enable_polarisation_es ); }
    /** @brief Store values in double precision. */
    void enable_doubleprec() { call( mcpl_enable_doubleprec_es ); }
    /**
     * @brief All particles have this PDG code.
     *
     * @param pdgcode The PDG code.
     */
    void enable_universal_pdgcode( std::int32_t pdgcode )
    {
      call( mcpl_enable_universal_pdgcode_es, pdgcode );
    }
    /**
     * @brief All particles have this weight.
     *
     * @param w The weight.
     */
    void enable_universal_weight( double w )
    {
      call( mcpl_enable_universal_weight_es, w );
    }

    /**
     * @brief Add a stat:sum entry.
     *
     * Entries can be added again to update their values.
     *
     * @param key The key.
     * @param value The value (non-negative).
     */
    void add_stat_sum( std::string_view key, double value )
    {
      if ( !( value >= 0.0 ) )
        detail::throw_runtime( "stat:sum values must be non-negative (use"
                               " reserve_stat_sum to reserve entries)" );
      call( mcpl_hdr_add_stat_sum_es, std::string(key).c_str(), value );
    }
    /**
     * @brief Reserve a stat:sum entry whose value is not yet known.
     *
     * A value must then be added (with add_stat_sum) before closing the file.
     *
     * @param key The key.
     */
    void reserve_stat_sum( std::string_view key )
    {
      call( mcpl_hdr_add_stat_sum_es, std::string(key).c_str(), -1.0 );
    }
    /**
     * @brief Scale all stat:sum values (like `mcpl_hdr_scale_stat_sums`).
     *
     * @param scale Finite factor >0, or -1 to mark all values as not available.
     */
    void scale_stat_sums( double scale )
    {
      call( mcpl_hdr_scale_stat_sums_es, scale );
    }

    ///@}
    /** @name Userdata */
    ///@{
    /**
     * @brief Add a field to the userdata.
     *
     * For example `add_userdata_field<float>("temp","K")` for a field `temp:float32:K`, or `add_userdata_field<float,3>("dir")` for `dir:float32[3]`. Fields are added one at a time, and the layout is fixed when the first particle is added (or new_particle() is called), after which no fields can be added.
     *
     * @tparam T Type of the values of the field.
     * @tparam N Number of values of array fields (0 for single values).
     * @param name Name of the field.
     * @param unit Unit of the values (e.g. `"cm"` or `"MeV^-1"`), or empty for none.
     * @return The field object for setting the values.
     * @throws mcpl::Error for invalid names or units, or after the layout is fixed.
     */
    template<class T, std::size_t N = 0>
    UserdataField<T,N> add_userdata_field( std::string_view name, std::string_view unit = {} )
    {
      h();
      if ( m_layout_locked || mcpl_outfile_userdata_layout( m_f ) )
        detail::throw_runtime( "userdata fields can not be added after the"
                               " userdata layout is fixed" );
      std::string field = std::string(name) + ":" + detail::ud_type_str<T,N>();
      if ( !unit.empty() )
        field += ":" + std::string(unit);
      std::string layout = m_pending_layout.empty()
        ? field : m_pending_layout + "," + field;
      detail::ErrState es;
      //(validates the layout, e.g. names and duplicates):
      mcpl_userdata_layout_size_es( layout.c_str(), es );
      es.check();
      std::uint32_t off = mcpl_userdata_offset_es( layout.c_str(),
                                                   std::string(name).c_str(),
                                                   detail::ud_type_str<T,N>().c_str(),
                                                   es );
      es.check();
      m_pending_layout = std::move(layout);
      return UserdataField<T,N>(off);
    }
    /**
     * @brief Give the whole userdata layout at once (instead of add_userdata_field).
     *
     * @param layout The layout, like `"temp:float32:K,dir:float32[3]"`.
     */
    void enable_userdata( std::string_view layout )
    {
      h();
      if ( !m_pending_layout.empty() )
        detail::throw_runtime( "enable_userdata can not be used after"
                               " add_userdata_field" );
      if ( m_layout_locked )
        detail::throw_runtime( "enable_userdata must be called before"
                               " particles are added (or new_particle is"
                               " called)" );
      call( mcpl_enable_userdata_es, std::string(layout).c_str() );
      update_userdata_buffer();
    }
    /** @brief Layout of the userdata (empty if none). */
    std::string userdata_layout() const
    {
      const char * l = mcpl_outfile_userdata_layout( h() );
      return l ? std::string(l) : m_pending_layout;
    }
    /**
     * @brief Field in an already given layout (e.g. from enable_userdata or transfer_metadata).
     *
     * @tparam T Type of the values of the field.
     * @tparam N Number of values of array fields (0 for single values).
     * @param name Name of the field.
     * @throws mcpl::Error if there is no userdata, or the field does not exist with exactly this type.
     */
    template<class T, std::size_t N = 0>
    UserdataField<T,N> userdata_field( std::string_view name ) const
    {
      std::string layout = userdata_layout();
      if ( layout.empty() )
        detail::throw_runtime( "file has no userdata" );
      detail::ErrState es;
      std::uint32_t off = mcpl_userdata_offset_es( layout.c_str(),
                                                   std::string(name).c_str(),
                                                   detail::ud_type_str<T,N>().c_str(),
                                                   es );
      es.check();
      return UserdataField<T,N>(off);
    }

    ///@}
    /** @name Adding particles */
    ///@{
    /**
     * @brief The particle object of the file, reset to zero (also the userdata).
     *
     * It is the same object every time, and valid as long as the file is open.
     */
    OutParticle new_particle()
    {
      h();
      fix_layout();
      if ( !m_puser ) {
        detail::ErrState es;
        m_puser = mcpl_get_empty_particle_es( m_f, es );
        es.check();
      }
      std::memset( m_puser, 0, sizeof(mcpl_particle_t) );
      if ( !m_ud.empty() )
        std::memset( m_ud.data(), 0, m_ud.size() );
      return OutParticle( m_puser, m_ud.empty() ? nullptr : m_ud.data(),
                          static_cast<std::uint32_t>(m_ud.size()),
                          m_f.internal );
    }

    /**
     * @brief Add the particle (with its userdata, if the file has userdata).
     *
     * @param p The particle (from new_particle()).
     */
    void add( const OutParticle& p )
    {
      h();
      if ( p.m_owner != m_f.internal )
        detail::throw_runtime( "particle does not belong to this output file" );
      add_impl( p.c_struct(), p.m_ud );
    }
    /**
     * @brief Add a particle given as in the C API (with all userdata bytes zero, if the file has userdata).
     *
     * @param p The particle.
     */
    void add( const mcpl_particle_t& p )
    {
      h();
      fix_layout();
      add_impl( p, nullptr );
    }

    /**
     * @brief Copy all header data and options from a file being read (like `mcpl_transfer_metadata`).
     *
     * Must be called before particles are added (or new_particle() is called).
     *
     * @param source The file being read.
     */
    void transfer_metadata( const MCPLFile& source )
    {
      h();
      if ( m_layout_locked )
        detail::throw_runtime( "transfer_metadata must be called before"
                               " particles are added (or new_particle is"
                               " called)" );
      fix_pending_layout();
      detail::ErrState es;
      mcpl_transfer_metadata_es( source.c_handle(), m_f, es );
      es.check();
      update_userdata_buffer();
    }
    /**
     * @brief Add the last particle read from a file, transferred exactly (like `mcpl_transfer_last_read_particle`).
     *
     * This avoids any loss of precision when copying files.
     *
     * @param source The file being read.
     */
    void transfer_last_read_particle( const MCPLFile& source )
    {
      h();
      fix_layout();
      detail::ErrState es;
      mcpl_transfer_last_read_particle_es( source.c_handle(), m_f, es );
      es.check();
    }

    ///@}
    /** @brief The file object of the C API (for direct use with the C functions). */
    mcpl_outfile_t c_handle() const noexcept { return m_f; }

  private:
    friend MCPLOutFile merge_files( detail::FilenameArg,
                                    detail::FilenameList&& );
    friend MCPLOutFile forcemerge_files( detail::FilenameArg,
                                         detail::FilenameList&&,
                                         KeepUserflags );
    explicit MCPLOutFile( mcpl_outfile_t f ) : m_f(f), m_layout_locked(true)
    {
      try {
        update_userdata_buffer();
      } catch (...) {
        abandon();
        throw;
      }
    }

    mcpl_outfile_t h() const
    {
      if ( !m_f.internal )
        detail::throw_runtime( "MCPLOutFile object is not open" );
      return m_f;
    }
    template<class Fct, class... Args>
    void call( Fct fct, Args... args )
    {
      detail::ErrState es;
      fct( h(), args..., es );
      es.check();
    }
    mcpl_outfile_t release() noexcept
    {
      mcpl_outfile_t f = m_f;
      m_f.internal = nullptr;
      m_puser = nullptr;
      m_ud.clear();
      m_pending_layout.clear();
      m_layout_locked = false;
      return f;
    }
    //Give any fields added with add_userdata_field to the C library:
    void fix_pending_layout()
    {
      h();
      if ( !m_pending_layout.empty() ) {
        call( mcpl_enable_userdata_es, m_pending_layout.c_str() );
        m_pending_layout.clear();
      }
      update_userdata_buffer();
    }
    //Fix the layout before particles are added:
    void fix_layout()
    {
      if ( !m_layout_locked ) {
        fix_pending_layout();
        m_layout_locked = true;
      }
    }
    void finalise_layout_for_closing()
    {
      //(errors are only reported, the file is closed by the caller anyway):
      if ( m_f.internal && !m_pending_layout.empty() ) {
        detail::ErrState es;
        mcpl_enable_userdata_es( m_f, m_pending_layout.c_str(), es );
        m_pending_layout.clear();
        if ( es.get()->code ) {
          abandon();
          es.check();
        }
      }
    }
    void update_userdata_buffer()
    {
      const char * l = mcpl_outfile_userdata_layout( m_f );
      std::uint32_t n = 0;
      if ( l ) {
        detail::ErrState es;
        n = mcpl_userdata_layout_size_es( l, es );
        es.check();
      }
      if ( m_ud.size() != n )
        m_ud.assign( n, 0 );
    }
    void add_impl( const mcpl_particle_t& p, const std::uint8_t * ud )
    {
      detail::ErrState es;
      if ( !m_ud.empty() )
        mcpl_add_particle_with_userdata_es( m_f, &p, ud, es );
      else
        mcpl_add_particle_es( m_f, &p, es );
      es.check();
    }

    mcpl_outfile_t m_f = { nullptr };
    std::string m_pending_layout;//fields not yet given to the C library
    std::vector<std::uint8_t> m_ud;//userdata of new_particle()
    mcpl_particle_t * m_puser = nullptr;
    bool m_layout_locked = false;//set when particles can be added
  };

  //////////////////////////////////////////////////////////////////////////////
  // Operations on files. Lists of files can be given as containers (like
  // std::vector) of C strings, std::string, std::string_view or
  // std::filesystem::path, or as initializer lists like {"a.mcpl","b.mcpl"}.

  /// @cond INTERNAL
  inline MCPLOutFile merge_files( detail::FilenameArg file_output,
                                  detail::FilenameList&& files )
  {
    detail::ErrState es;
    mcpl_outfile_t f = mcpl_merge_files_es( file_output.c_str(), files.size(),
                                            files.data(), es );
    es.check();
    return MCPLOutFile(f);
  }
  /// @endcond
  /**
   * @brief Merge files into a new file (like `mcpl_merge_files`).
   *
   * The returned output file must be closed with close() (but can have more particles added first).
   *
   * @tparam Range Container of filenames (e.g. `std::vector<std::string>`).
   * @param file_output Name of the new file (which must not exist).
   * @param files The files to merge.
   * @return The output file (still open).
   */
  template<class Range>
  inline MCPLOutFile merge_files( detail::FilenameArg file_output,
                                  const Range& files )
  {
    return merge_files( file_output.c_str(), detail::FilenameList(files) );
  }
  /**
   * @brief Merge files into a new file, given as a braced list like `{"a.mcpl","b.mcpl"}`.
   *
   * @param file_output Name of the new file (which must not exist).
   * @param files The files to merge.
   * @return The output file (still open).
   */
  inline MCPLOutFile merge_files( detail::FilenameArg file_output,
                                  std::initializer_list<detail::FilenameArg> files )
  {
    std::vector<std::string> names;
    for ( const auto& f : files )
      names.emplace_back( f.c_str() );
    return merge_files( file_output.c_str(), detail::FilenameList(names) );
  }

  /// @cond INTERNAL
  inline MCPLOutFile forcemerge_files( detail::FilenameArg file_output,
                                       detail::FilenameList&& files,
                                       KeepUserflags keep_userflags )
  {
    detail::ErrState es;
    mcpl_outfile_t f = mcpl_forcemerge_files_es( file_output.c_str(),
                                                 files.size(), files.data(),
                                                 keep_userflags == KeepUserflags::Yes
                                                 ? 1 : 0, es );
    es.check();
    return MCPLOutFile(f);
  }
  /// @endcond
  /**
   * @brief Merge files with different settings, discarding data if needed (like `mcpl_forcemerge_files`).
   *
   * @tparam Range Container of filenames.
   * @param file_output Name of the new file (which must not exist).
   * @param files The files to merge.
   * @param keep_userflags Whether the userflags are kept.
   * @return The output file (still open).
   */
  template<class Range>
  inline MCPLOutFile forcemerge_files( detail::FilenameArg file_output,
                                       const Range& files,
                                       KeepUserflags keep_userflags = KeepUserflags::No )
  {
    return forcemerge_files( file_output.c_str(), detail::FilenameList(files),
                             keep_userflags );
  }
  /**
   * @brief Merge files with different settings, given as a braced list.
   *
   * @param file_output Name of the new file (which must not exist).
   * @param files The files to merge.
   * @param keep_userflags Whether the userflags are kept.
   * @return The output file (still open).
   */
  inline MCPLOutFile forcemerge_files( detail::FilenameArg file_output,
                                       std::initializer_list<detail::FilenameArg> files,
                                       KeepUserflags keep_userflags = KeepUserflags::No )
  {
    std::vector<std::string> names;
    for ( const auto& f : files )
      names.emplace_back( f.c_str() );
    return forcemerge_files( file_output.c_str(), detail::FilenameList(names),
                             keep_userflags );
  }

  /**
   * @brief Whether two files can be merged.
   *
   * @param file1 First file.
   * @param file2 Second file.
   */
  inline bool can_merge( detail::FilenameArg file1, detail::FilenameArg file2 )
  {
    detail::ErrState es;
    int r = mcpl_can_merge_es( file1.c_str(), file2.c_str(), es );
    es.check();
    return r != 0;
  }

  /**
   * @brief Append the particles of file2 to file1.
   *
   * @param file1 File to which the particles are added.
   * @param file2 File with the particles to add.
   */
  inline void merge_inplace( detail::FilenameArg file1,
                             detail::FilenameArg file2 )
  {
    detail::ErrState es;
    mcpl_merge_inplace_es( file1.c_str(), file2.c_str(), es );
    es.check();
  }

  /**
   * @brief Repair a file which was not properly closed.
   *
   * @param filename Name of the file.
   */
  inline void repair( detail::FilenameArg filename )
  {
    detail::ErrState es;
    mcpl_repair_es( filename.c_str(), es );
    es.check();
  }

  /**
   * @brief Compress a file (replacing filename with filename.gz).
   *
   * @param filename Name of the file.
   */
  inline void gzip_file( detail::FilenameArg filename )
  {
    detail::ErrState es;
    mcpl_gzip_file_es( filename.c_str(), es );
    es.check();
  }

}

#endif
