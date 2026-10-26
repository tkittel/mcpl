
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
A plot in several standard groups is one view, with a card in each (see
_viewer_widgets.WidgetViewer.cards), and the custom plots (which are always shown) are the only ones which
can be reordered, given titles and removed."""

__all__ = []

from ._stdviews import (
    _default_groups,
    _groups,
    _plot_item,
    custom_key,
    custom_title,
)
from ._viewer_overviews import Overview


class PlotGroups:
    """The groups of plots: the keys of the standard groups shown (in the order
    of _stdviews), and the custom plots (histogram strings) with their titles.
    The extra plot items of groups are added to their plots (e.g. those of
    the fields of the userdata to the fields). The standard groups have
    settings (see setting): the particle type of their plots, what they show
    a curve of each value of, and the variables of correlation plots, with
    defaults from what the reading of the file found (see found)."""
    def __init__( self, extra = None ):
        self.shown = list(_default_groups)
        self.custom = []
        self.titles = {}#(custom plot -> title)
        self._extra = extra or {}
        self.settings = {}#(group key -> {setting name -> value} chosen, see setting)
        #(what the reading found, see _viewer_reading._Computation.found):
        self.found = { 'constants' : {}, 'types' : [], 'correlations' : {} }

    def overview( self, key, add_cell = False ):
        """The Overview of the group (with its settings, and for the custom
        group with add_cell, the place of a new plot after its plots)"""
        if key == custom_key:
            return Overview(custom_title,self.custom,'user added plots',add_cell = add_cell)
        title, descr, items, opts = _groups[key]
        from ._particles import _particle_display_only
        only = _particle_display_only(self.setting(key,'display_only'))
        if 'variables' in opts:
            return Overview(title,description = descr,layout = 'correlation',display_only = only,
                            variables = self.setting(key,'variables'))
        plots = [ _plot_item(i)[0] for i in ( *items, *self._extra.get(key,()) ) ]
        return Overview(title,plots,descr,display_only = only,
                        display_by = self.setting(key,'display_by'))

    def items( self, key ):
        """The plots (histogram strings) of the group, with their titles, as a
        list of (plot, title)"""
        if key == custom_key:
            return [ ( p, self.titles.get(p) ) for p in self.custom ]
        _, _, items, _ = _groups[key]
        ov = self.overview(key)
        if ov.correlation_plot:
            #(the 2D histograms are titled by their expressions, without the
            #options, and the others get the titles of their fields):
            from ._histstring import _hist_exprs, _hist_parts
            return [ ( p, _hist_parts(p)[0] if len(_hist_exprs(p)) == 2 else None )
                     for p in ov.plots ]
        titles = [ _plot_item(i)[1] for i in ( *items, *self._extra.get(key,()) ) ]
        return list(zip(ov.cells,titles))

    #The settings of the standard groups:

    def setting_names( self, key ):
        """The names of the settings of the group: the particle type shown, and
        what the plots show a curve of each value of (not in correlation plots,
        which have the variables instead)"""
        if key == custom_key:
            return []
        correlation_plot = 'variables' in _groups[key][3]
        return [ 'display_only', 'variables' if correlation_plot else 'display_by' ]

    def setting( self, key, name ):
        """The value of a setting of the group: as chosen, or its default. The
        particle type (display_only) is a PDG code, or None for all particles
        (by default the most common type for correlation plots of several types),
        display_by is pdgcode (a curve of each type, by default) or single,
        and the variables are expressions (by default those of fields with
        more than one value)"""
        chosen = self.settings.get(key,{})
        if name in chosen:
            return chosen[name]
        opts = _groups[key][3]
        if name == 'display_by':
            return 'pdgcode'
        if name == 'display_only':
            types = self.found['types']
            return types[0][0] if 'variables' in opts and len(types) > 1 else None
        varying = [ v for v in opts['variables'] if not self._constant(v) ]
        return varying if len(varying) >= 2 else list(opts['variables'])

    def set_setting( self, key, name, value ):
        """Choose the value of a setting of the group (see setting), or its
        default (with None for variables): whether it changed"""
        old = self.setting(key,name)
        if value is None and name == 'variables':
            self.settings.get(key,{}).pop(name,None)
        else:
            self.settings.setdefault(key,{})[name] = value
        return self.setting(key,name) != old

    def setting_choices( self, key, name ):
        """The possible values of a setting: the particle types found (and None
        for all), pdgcode or single, or the variables which correlation plots can
        have"""
        if name == 'display_only':
            return [ None ] + [ pdg for pdg, _ in self.found['types'] ]
        if name == 'display_by':
            return [ 'pdgcode', 'single' ]
        return list(_groups[key][3]['variables'])

    def coefficients( self, key ):
        """The correlation coefficients of the fields of the correlation plot of the
        group (for its particle type), as {(field, field) : r}, as far as
        known (see Moments.coefficients)"""
        if key == custom_key or 'variables' not in _groups[key][3]:
            return {}
        return self.found['correlations'].get(self.setting(key,'display_only'),{})

    def most_correlated( self, key, n = 4 ):
        """The n variables of the correlation plot of the group with the strongest
        correlations (the largest absolute correlation coefficient with any
        other one, of those with more than one value), in their order, or
        None if the coefficients are not known"""
        coeffs = self.coefficients(key)
        if not coeffs:
            return None
        choices = [ v for v in self.setting_choices(key,'variables') if not self._constant(v) ]
        def score( v ):
            return max( ( abs(r) for pair, r in coeffs.items() if v in pair and r is not None
                          and all( u in choices for u in pair ) ), default = 0.0 )
        top = sorted(choices,key = lambda v : -score(v))[:n]
        return [ v for v in choices if v in top ]

    def _constant( self, expr ):
        """Whether the particles have one value of the expression (of fields with
        one value)"""
        from ._exprcore import _Expr
        fields = _Expr(expr).fields
        return bool(fields) and fields <= set(self.found['constants'])

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
            for p, t in self.items(k):
                if p not in seen or k == custom_key:
                    seen.add(p)
                    res.append( ( p, t, k ) )
        return res

    def overviews( self, add_cell = False ):
        """The overviews of the groups shown, as (group key, Overview), see
        overview"""
        return [ ( k, ov ) for k, ov in ( ( k, self.overview(k,add_cell) ) for k in self.keys() )
                 if ov.plots ]

    def is_custom( self, plot ):
        return plot in self.custom

    def use( self, keys ):
        """Show the standard groups with the keys (only those)"""
        self.shown = [ k for k in _groups if k in keys ]

    def show( self, key, shown = True ):
        """Show (or hide) the standard group with the key: whether it changed"""
        if ( key in self.shown ) == shown:
            return False
        self.shown = [ k for k in _groups if ( k in self.shown ) != ( k == key ) ]
        return True

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
        """The groups shown (if not the default ones), the custom
        plots (plot items, see _stdviews), and the settings of groups which
        were chosen"""
        from ._stdviews import _item
        res = {}
        if set(self.shown) != set(_default_groups):
            res['groups'] = list(self.shown)
        if self.custom:
            res['custom'] = [ _item(p,self.titles.get(p)) for p in self.custom ]
        if any(self.settings.values()):
            res['settings'] = { k : dict(v) for k, v in self.settings.items() if v }
        return res

def title_of( key ):
    """The title of the group with the key"""
    return custom_title if key == custom_key else _groups[key][0]

def group_names():
    """The keys of the standard groups, with their titles and descriptions, as
    (key, description)"""
    return [ ( k, f'{_groups[k][0]}: {_groups[k][1]}' ) for k in _groups ]

def parse_groups( text ):
    """The keys of the groups in the text (separated by commas), or None if
    it is not a list of keys of standard groups"""
    keys = [ k.strip() for k in text.split(',') ]
    return keys if keys and all( k in _groups for k in keys ) else None
