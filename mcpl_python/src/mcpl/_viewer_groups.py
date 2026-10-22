
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

"""The plots of the viewer (see _viewer.Viewer), in groups: the standard groups
which are shown (see _stdviews), with their fixed plots, and the custom
group, with the plots which were added (and the copies of standard plots
which were changed). Each group has its overview (see _viewer_overviews).
The plots of the standard groups are shown once, in the first group which has
them, and the custom plots (which are always shown) are the only ones which
can be reordered, given titles and removed."""

__all__ = []

from ._stdviews import _default_preset, _groups, _plot_item, _presets
from ._viewer_overviews import Overview, grid_columns, pair_cells

custom_key, custom_title = 'custom', 'Custom'

class PlotGroups:
    """The groups of plots: the keys of the standard groups shown (in the order
    of _stdviews), and the custom plots (histogram strings) with their titles.
    The extra plot items of groups are added to their plots (e.g. those of
    the fields of the userdata to the fields)."""
    def __init__( self, extra = None ):
        self.shown = list(_presets[_default_preset][1])
        self.custom = []
        self.titles = {}#(custom plot -> title)
        self._extra = extra or {}

    def _items( self, key ):
        """The plots (histogram strings) of the group, with their titles, as a
        list of (plot, title)"""
        if key == custom_key:
            return [ ( p, self.titles.get(p) ) for p in self.custom ]
        _, _, items, opts = _groups[key]
        if 'pairs' in opts:
            return [ ( c, None ) for c in pair_cells(list(opts['pairs'])) if c is not None ]
        return [ _plot_item(i) for i in ( *items, *self._extra.get(key,()) ) ]

    def keys( self ):
        """The keys of the groups shown, in order: the standard ones, and the
        custom group (if it has plots)"""
        return [ k for k in _groups if k in self.shown ] + ( [ custom_key ] if self.custom else [] )

    def cards( self ):
        """The plots shown, in order, as (plot, title, group key): those of the
        standard groups each in the first group which has it, and the custom
        plots (also those which are in standard groups)"""
        res, seen = [], set()
        for k in self.keys():
            for p, t in self._items(k):
                if p not in seen or k == custom_key:
                    seen.add(p)
                    res.append( ( p, t, k ) )
        return res

    def overviews( self ):
        """The overviews of the groups shown, as (group key, Overview)"""
        res = []
        for k in self.keys():
            opts = _groups[k][3] if k != custom_key else {}
            if 'pairs' in opts:
                cells, ncols = pair_cells(list(opts['pairs'])), len(opts['pairs'])
            else:
                cells = [ p for p, _ in self._items(k) ]
                ncols = grid_columns(len(cells))
            if cells:
                res.append( ( k, Overview(title_of(k),cells,ncols,correlation_plot = 'pairs' in opts) ) )
        return res

    def folded( self ):
        """The titles of the groups which are folded at the start"""
        return [ _groups[k][0] for k in _groups if _groups[k][3].get('folded') ]

    def is_custom( self, plot ):
        return plot in self.custom

    def use_preset( self, name ):
        """Show the groups of the preset (or of the group, given by its key)"""
        self.shown = list( _presets[name][1] if name in _presets else ( name, ) )

    def show( self, key, shown = True ):
        """Show (or hide) the standard group with the key: whether it changed"""
        if ( key in self.shown ) == shown:
            return False
        self.shown = [ k for k in _groups if ( k in self.shown ) != ( k == key ) ]
        return True

    def preset( self ):
        """The name of the preset of the groups shown, or None"""
        return next( ( n for n, ( _, keys ) in _presets.items()
                       if set(keys) == set(self.shown) ), None )

    #The custom plots:

    def add( self, plot, title = None, after = None ):
        """Add a custom plot (after the custom plot after, else at the end)"""
        i = self.custom.index(after) + 1 if after in self.custom else len(self.custom)
        self.custom.insert(i,plot)
        self.set_title(plot,title)

    def set_title( self, plot, title ):
        if title:
            self.titles[plot] = title
        else:
            self.titles.pop(plot,None)

    def remove( self, plot ):
        self.custom.remove(plot)
        self.titles.pop(plot,None)

    def move_to( self, plot, index ):
        """Move the custom plot to the index among the custom plots: whether it
        moved"""
        i = self.custom.index(plot)
        index = max( 0, min( len(self.custom) - 1, index ) )
        if index == i:
            return False
        self.custom.insert(index,self.custom.pop(i))
        return True

    #The state (see _viewer.Viewer.state):

    def state( self ):
        """The groups shown (if not those of the default preset), and the custom
        plots (plot items, see _stdviews)"""
        from ._stdviews import _item
        res = {}
        if set(self.shown) != set(_presets[_default_preset][1]):
            res['groups'] = self.preset() or list(self.shown)
        if self.custom:
            res['custom'] = [ _item(p,self.titles.get(p)) for p in self.custom ]
        return res

def title_of( key ):
    """The title of the group with the key"""
    return custom_title if key == custom_key else _groups[key][0]

def group_names():
    """The names which can be chosen as the groups: the presets, and the keys
    of the groups, with their descriptions, as (name, description)"""
    return ( [ ( n, d ) for n, ( d, _ ) in _presets.items() ]
             + [ ( k, f'only {_groups[k][0]}: {_groups[k][1]}' ) for k in _groups
                 if k not in _presets ] )
