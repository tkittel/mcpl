/* On the API reference pages, entries (functions, classes, ...) are collapsed
   to their signature and a one-line summary, and expanded by clicking the
   signature. Links to entries expand them (and the entries they are in). */
document.addEventListener( 'DOMContentLoaded', function () {
  if ( !/(^|\/)(c|python|cpp)_api(\/|\/index\.html)?$/.test( location.pathname ) )
    return;
  var entries = Array.prototype.filter.call(
    document.querySelectorAll( 'dl.c, dl.py, dl.cpp' ),
    function ( dl ) {
      /* (namespaces only contain the other entries, so they stay open) */
      return ( dl.querySelector( ':scope > dt' ) && dl.querySelector( ':scope > dd' )
               && !/^namespace\s/.test( dl.querySelector( ':scope > dt' )
                                           .textContent.trim() ) );
    } );
  if ( !entries.length )
    return;
  var collapsible = [];
  entries.forEach( function ( dl ) {
    var dd = dl.querySelector( ':scope > dd' );
    dl.classList.add( 'mcpl-entry' );
    /* One-line summary: the first sentence of the description: */
    var p = dd.querySelector( ':scope > p' );
    var summarytext = '';
    if ( p ) {
      var text = p.textContent.replace( /\s+/g, ' ' ).trim();
      var m = text.match( /^.*?[.:](\s|$)/ );
      summarytext = m ? m[0].trim() : text;
      var summary = document.createElement( 'span' );
      summary.className = 'mcpl-summary';
      summary.textContent = summarytext;
      dl.insertBefore( summary, dd );
    }
    /* Entries whose description is just that sentence (or which have no
       description) are always shown on one line, and not collapsible: */
    var content = Array.prototype.filter.call( dd.children, function ( c ) {
      return c.textContent.trim() !== '';
    } );
    if ( content.length === 0
         || ( content.length === 1 && content[0] === p
              && p.textContent.replace( /\s+/g, ' ' ).trim() === summarytext ) ) {
      dl.classList.add( 'mcpl-oneline' );
      return;
    }
    collapsible.push( dl );
    dl.classList.add( 'mcpl-collapsible', 'mcpl-collapsed' );
    dl.querySelectorAll( ':scope > dt' ).forEach( function ( sig ) {
      sig.addEventListener( 'click', function ( ev ) {
        if ( ev.target.closest( 'a' ) )
          return;/* (links in signatures still work) */
        dl.classList.toggle( 'mcpl-collapsed' );
      } );
    } );
  } );
  /* Expand all / collapse all: */
  var bar = document.createElement( 'div' );
  bar.className = 'mcpl-togglebar';
  [ [ 'Expand all', false ], [ 'Collapse all', true ] ].forEach( function ( b ) {
    var button = document.createElement( 'button' );
    button.type = 'button';
    button.textContent = b[0];
    button.addEventListener( 'click', function () {
      collapsible.forEach( function ( dl ) {
        dl.classList.toggle( 'mcpl-collapsed', b[1] );
      } );
    } );
    bar.appendChild( button );
  } );
  var h1 = document.querySelector( '.rst-content h1' );
  if ( h1 )
    h1.parentNode.insertBefore( bar, h1.nextSibling );
  /* Expand the entry targeted by the URL (and the entries it is in): */
  function openTarget() {
    var id = decodeURIComponent( location.hash.slice( 1 ) );
    var el = id && document.getElementById( id );
    if ( !el )
      return;
    for ( var n = el; n; n = n.parentElement ) {
      if ( n.classList && n.classList.contains( 'mcpl-collapsible' ) )
        n.classList.remove( 'mcpl-collapsed' );
    }
    el.scrollIntoView();
  }
  openTarget();
  window.addEventListener( 'hashchange', openTarget );
} );
