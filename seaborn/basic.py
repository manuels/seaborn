from __future__ import division
from itertools import product
from textwrap import dedent

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

from .external.six import string_types

from . import utils
from .utils import categorical_order, get_color_cycle
from .algorithms import bootstrap
from .palettes import color_palette


__all__ = ["lineplot"]


class _BasicPlotter(object):

    # TODO use different lists for mpl 1 and 2?
    # We could use "line art glyphs" (e.g. "P") on mpl 2
    default_markers = ["o", "s", "D", "v", "^", "p"]
    marker_scales = {"o": 1, "s": .85, "D": .9, "v": 1.3, "^": 1.3, "p": 1.25}
    default_dashes = ["", (4, 1.5), (1, 1),
                      (3, 1, 1.5, 1), (5, 1, 1, 1), (5, 1, 2, 1, 2, 1)]

    def establish_variables(self, x=None, y=None,
                            hue=None, size=None, style=None,
                            data=None):
        """Parse the inputs to define data for plotting."""
        # Initialize label variables
        x_label = y_label = None

        # Option 1:
        # We have a wide-form datast
        # --------------------------

        if x is None and y is None:

            self.input_format = "wide"

            # Option 1a:
            # The input data is a Pandas DataFrame
            # ------------------------------------
            # We will assign the index to x, the values to y,
            # and the columns names to both hue and style

            # TODO accept a dict and try to coerce to a dataframe?

            if isinstance(data, pd.DataFrame):

                # Enforce numeric values
                try:
                    data.astype(np.float)
                except ValueError:
                    err = "A wide-form input must have only numeric values."
                    raise ValueError(err)

                plot_data = data.copy()
                plot_data.loc[:, "x"] = data.index
                plot_data = pd.melt(plot_data, "x",
                                    var_name="hue", value_name="y")
                plot_data["style"] = plot_data["hue"]

                x_label = getattr(data.index, "name", None)

            # Option 1b:
            # The input data is an array or list
            # ----------------------------------

            else:

                if not len(data):

                    plot_data = pd.DataFrame(columns=["x", "y"])

                elif np.isscalar(data[0]):

                    # The input data is a flat list(like):
                    # We assign a numeric index for x and use the values for y

                    plot_data = pd.DataFrame(dict(x=np.arange(len(data)),
                                                  y=data))

                elif hasattr(data, "shape"):

                    # The input data is an array(like):
                    # We assign a numeric index to x, the values to y, and
                    # numeric values to both hue and style

                    plot_data = pd.DataFrame(data)
                    plot_data.loc[:, "x"] = plot_data.index
                    plot_data = pd.melt(plot_data, "x",
                                        var_name="hue", value_name="y")
                    plot_data["style"] = plot_data["hue"]

                else:

                    # The input data is a nested list: We will assign a numeric
                    # index for x, use the values for, y and use numeric
                    # hue/style identifiers for each entry.

                    plot_data = pd.concat([
                        pd.DataFrame(dict(x=np.arange(len(data_i)),
                                          y=data_i, hue=i, style=i, size=None))
                        for i, data_i in enumerate(data)
                    ])

        # Option 2:
        # We have long-form data
        # ----------------------

        elif x is not None and y is not None:

            self.input_format = "long"

            # Use variables as from the dataframe if specified
            if data is not None:
                x = data.get(x, x)
                y = data.get(y, y)
                hue = data.get(hue, hue)
                size = data.get(size, size)
                style = data.get(style, style)

            # Validate the inputs
            for input in [x, y, hue, size, style]:
                if isinstance(input, string_types):
                    err = "Could not interpret input '{}'".format(input)
                    raise ValueError(err)

            # Extract variable names
            x_label = getattr(x, "name", None)
            y_label = getattr(y, "name", None)

            # Reassemble into a DataFrame
            plot_data = dict(x=x, y=y, hue=hue, style=style, size=size)
            plot_data = pd.DataFrame(plot_data)

        # Option 3:
        # Only one variable arugment
        # --------------------------

        else:
            err = ("Either both or neither of `x` and `y` must be specified "
                   "(but try passing to `data`, which is more flexible).")
            raise ValueError(err)

        # ---- Post-processing

        # Assign default values for missing attribute variables
        for attr in ["hue", "style", "size"]:
            if attr not in plot_data:
                plot_data[attr] = None

        self.x_label = x_label
        self.y_label = y_label
        self.plot_data = plot_data

        return plot_data

    def categorical_to_palette(self, data, order, palette):
        """Determine colors when the hue variable is qualitative."""
        # -- Identify the order and name of the levels

        if order is None:
            levels = categorical_order(data)
        else:
            levels = order
        n_colors = len(levels)

        # -- Identify the set of colors to use

        if isinstance(palette, dict):

            missing = set(levels) - set(palette)
            if any(missing):
                err = "The palette dictionary is missing keys: {}"
                raise ValueError(err.format(missing))

        else:

            if palette is None:
                if n_colors <= len(get_color_cycle()):
                    colors = color_palette(None, n_colors)
                else:
                    colors = color_palette("husl", n_colors)
            else:
                colors = color_palette(palette, n_colors)

            palette = dict(zip(levels, colors))

        return levels, palette

    def numeric_to_palette(self, data, order, palette, limits):
        """Determine colors when the hue variable is quantitative."""
        levels = list(np.sort(data.unique()))

        # TODO do we want to do something complicated to ensure contrast
        # at the extremes of the colormap against the background?

        # Identify the colormap to use
        if palette is None:
            cmap = mpl.cm.get_cmap(plt.rcParams["image.cmap"])
        elif isinstance(palette, dict):
            missing = set(levels) - set(palette)
            if any(missing):
                err = "The palette dictionary is missing keys: {}"
                raise ValueError(err.format(missing))
            cmap = None
        elif isinstance(palette, list):
            if len(palette) != len(levels):
                err = "The palette has the wrong number of colors"
                raise ValueError(err)
            palette = dict(zip(levels, palette))
            cmap = None
        elif isinstance(palette, mpl.colors.Colormap):
            cmap = palette
        else:
            try:
                cmap = mpl.cm.get_cmap(palette)
            except (ValueError, TypeError):
                err = "Palette {} not understood"
                raise ValueError(err)

        if cmap is not None:

            if limits is None:
                hue_min, hue_max = data.min(), data.max()
            else:
                hue_min, hue_max = limits
                hue_min = data.min() if hue_min is None else hue_min
                hue_max = data.max() if hue_max is None else hue_max

            limits = hue_min, hue_max
            normalize = mpl.colors.Normalize(hue_min, hue_max, clip=True)
            palette = {l: cmap(normalize(l)) for l in levels}

        return levels, palette, cmap, limits

    def style_to_attributes(self, levels, style, defaults, name):
        """Convert a style argument to a dict of matplotlib attributes."""
        if style is True:
            attrdict = dict(zip(levels, defaults))
        elif style and isinstance(style, dict):
            attrdict = style
        elif style:
            attrdict = dict(zip(levels, style))
        else:
            attrdict = {}

        if attrdict:
            missing_levels = set(levels) - set(attrdict)
            if any(missing_levels):
                err = "These `style` levels are missing {}: {}"
                raise ValueError(err.format(name, missing_levels))

        return attrdict

    def _empty_data(self, data):

        empty_data = data.isnull().all()
        return empty_data

    def _attribute_type(self, data):

        if self.input_format == "wide":
            return "categorical"
        else:
            try:
                data.astype(np.float)
                return "numeric"
            except ValueError:
                return "categorical"


class _LinePlotter(_BasicPlotter):

    def __init__(self,
                 x=None, y=None, hue=None, size=None, style=None, data=None,
                 palette=None, hue_order=None, hue_limits=None,
                 dashes=None, markers=None, style_order=None,
                 size_limits=None, size_range=None, size_order=None,
                 units=None, estimator=None, ci=None, n_boot=None,
                 sort=True, errstyle=None, legend=None):

        plot_data = self.establish_variables(x, y, hue, size, style, data)

        self.parse_hue(plot_data["hue"], palette, hue_order, hue_limits)
        self.parse_size(plot_data["size"], size_limits, size_range, size_order)
        self.parse_style(plot_data["style"], markers, dashes, style_order)

        self.sort = sort
        self.estimator = estimator
        self.ci = ci
        self.n_boot = n_boot
        self.errstyle = errstyle

    def subset_data(self):

        data = self.plot_data
        all_true = pd.Series(True, data.index)

        iter_levels = product(self.hue_levels,
                              self.size_levels,
                              self.style_levels)

        for hue, size, style in iter_levels:

            hue_rows = all_true if hue is None else data["hue"] == hue
            size_rows = all_true if size is None else data["size"] == size
            style_rows = all_true if style is None else data["style"] == style

            rows = hue_rows & size_rows & style_rows
            subset_data = data.loc[rows, ["x", "y"]].dropna()

            if not len(subset_data):
                continue

            yield (hue, size, style), subset_data

    def parse_hue(self, data, palette, order, limits):
        """Determine what colors to use given data characteristics."""
        if self._empty_data(data):

            # Set default values when not using a hue mapping
            levels = [None]
            palette = {}
            var_type = None
            cmap = None

        else:

            # Determine what kind of hue mapping we want
            var_type = self._attribute_type(data)

        # -- Option 1: categorical color palette

        if var_type == "categorical":

            cmap = None
            levels, palette = self.categorical_to_palette(
                data, order, palette
            )

        # -- Option 2: sequential color palette

        elif var_type == "numeric":

            levels, palette, cmap, limits = self.numeric_to_palette(
                data, order, palette, limits
            )

        self.hue_levels = levels
        self.hue_limits = limits
        self.hue_type = var_type
        self.palette = palette
        self.cmap = cmap

    def parse_size(self, data, size_limits, size_range, size_order):
        """Determine the widths of the lines."""
        if self._empty_data(data):
            size_levels = [None]
            sizes = {}

        else:

            if self._attribute_type(data) == "categorical":
                # TODO be more flexible, it could be fine to do heavy and light
                # lines for categorical variables
                err = "The variable that determines size must be numeric."
                raise ValueError(err)

            size_levels = categorical_order(data)

            if size_range is None:
                default = plt.rcParams["lines.linewidth"]
                min_width, max_width = default * .5, default * 2
            else:
                min_width, max_width = size_range

            if size_limits is None:
                s_min, s_max = data.min(), data.max()
            else:
                s_min, s_max = size_limits
                s_min = data.min() if s_min is None else s_min
                s_max = data.max() if s_max is None else s_max

            size_limits = s_min, s_max
            size_range = min_width, max_width
            normalize = mpl.colors.Normalize(s_min, s_max, clip=True)
            sizes = {l: min_width + (normalize(l) * max_width)
                     for l in size_levels}

        self.size_levels = size_levels
        self.size_limits = size_limits
        self.size_range = size_range
        self.sizes = sizes

    def parse_style(self, data, markers, dashes, order):
        """Determine the markers and line dashes."""

        if self._empty_data(data):

            levels = [None]
            dashes = {}
            markers = {}

        else:

            if order is None:
                levels = categorical_order(data)
            else:
                levels = order

            markers = self.style_to_attributes(
                levels, markers, self.default_markers, "markers"
            )

            dashes = self.style_to_attributes(
                levels, dashes, self.default_dashes, "dashes"
            )

        self.style_levels = levels
        self.dashes = dashes
        self.markers = markers

    def aggregate(self, vals, grouper, func, ci):

        n_boot = self.n_boot

        # TODO rework this logic, which is a mess
        if callable(func):
            def f(x):
                try:
                    return x.apply(func)
                except AttributeError:
                    return func(x)

        else:
            def f(x):
                return getattr(x, func)()

        null_ci = pd.Series(index=["low", "high"], dtype=np.float)

        def bootstrapped_cis(vals):

            if len(vals) == 1:
                return null_ci

            boots = bootstrap(vals, func=f, n_boot=n_boot)
            cis = utils.ci(boots, ci)
            return pd.Series(cis, ["low", "high"])

        grouped = vals.groupby(grouper, sort=self.sort)

        est = f(grouped)

        if ci is None:
            return est.index, est, None
        elif ci == "sd":
            sd = grouped.std()
            cis = pd.DataFrame(np.c_[est - sd, est + sd],
                               index=est.index,
                               columns=["low", "high"]).stack()
        else:
            cis = grouped.apply(bootstrapped_cis)

        if cis.notnull().any():
            cis = cis.unstack()
        else:
            cis = None

        return est.index, est, cis

    def plot(self, ax, legend, kws):

        orig_color = kws.pop("color", None)
        orig_dashes = kws.pop("dashes", (np.inf, 1))
        orig_marker = kws.pop("marker", None)
        orig_linewidth = kws.pop("linewidth", kws.pop("lw", None))

        kws.setdefault("markeredgewidth", kws.pop("mew", .75))
        kws.setdefault("markeredgecolor", kws.pop("mec", "w"))

        for (hue, size, style), subset_data in self.subset_data():

            if self.sort:
                subset_data = subset_data.sort_values(["x", "y"])

            x, y = subset_data["x"], subset_data["y"]

            if self.estimator is not None:
                x, y, y_ci = self.aggregate(y, x, self.estimator, self.ci)
            else:
                y_ci = None

            kws["color"] = self.palette.get(hue, orig_color)
            kws["dashes"] = self.dashes.get(style, orig_dashes)
            kws["marker"] = self.markers.get(style, orig_marker)
            kws["linewidth"] = self.sizes.get(size, orig_linewidth)

            # TODO handle marker size adjustment

            line, = ax.plot(x.values, y.values, **kws)
            line_color = line.get_color()
            line_alpha = line.get_alpha()

            if y_ci is not None:

                if self.errstyle == "band":

                    ax.fill_between(x, y_ci["low"], y_ci["high"],
                                    color=line_color, alpha=.2)

                elif self.errstyle == "bars":

                    ci_xy = np.empty((len(x), 2, 2))
                    ci_xy[:, :, 0] = x[:, np.newaxis]
                    ci_xy[:, :, 1] = y_ci.values
                    lines = LineCollection(ci_xy,
                                           color=line_color,
                                           alpha=line_alpha)
                    ax.add_collection(lines)
                    ax.autoscale_view()

        # TODO this should go in its own method?
        if self.x_label is not None:
            x_visible = any(t.get_visible() for t in ax.get_xticklabels())
            ax.set_xlabel(self.x_label, visible=x_visible)
        if self.y_label is not None:
            y_visible = any(t.get_visible() for t in ax.get_yticklabels())
            ax.set_ylabel(self.y_label, visible=y_visible)

        # Add legend data
        if legend:
            self.add_legend_data(ax, legend)
            handles, _ = ax.get_legend_handles_labels()
            if handles:
                ax.legend()

    def add_legend_data(self, ax, legend):

        # TODO doesn't handle overlapping keys (i.e. hue="a", style="a") well

        if legend not in ["brief", "full"]:
            err = "`legend` must be 'brief', 'full', or False"
            raise ValueError(err)

        for level in self.hue_levels:
            if level is not None:
                ax.plot([], [], color=self.palette[level], label=level)

        for level in self.size_levels:
            if level is not None:
                ax.plot([], [], color=".2",
                        linewidth=self.sizes[level], label=level)

        for level in self.style_levels:
            if level is not None:
                marker = self.markers.get(level, "")
                dashes = self.dashes.get(level, "")
                ax.plot([], [], color=".2",
                        marker=marker, dashes=dashes, label=level)


class _ScatterPlotter(_BasicPlotter):

    def __init__(self):
        pass

    def plot(self, ax=None):
        pass


_basic_docs = dict(

    main_api_narrative=dedent("""\
    """),

)


def lineplot(x=None, y=None, hue=None, size=None, style=None, data=None,
             palette=None, hue_order=None, hue_limits=None,
             dashes=True, markers=None, style_order=None,
             size_limits=None, size_range=None, size_order=None,
             units=None, estimator="mean", ci=95, n_boot=1000,
             sort=True, errstyle="band",
             legend="brief", ax=None, **kwargs):

    # TODO add a "brief_legend" or similar that handles many legend entries
    # using a matplotlib ticker ... maybe have it take threshold where you
    # flip from itemizing levels to showing level ticks

    p = _LinePlotter(
        x=x, y=y, hue=hue, size=size, style=style, data=data,
        palette=palette, hue_order=hue_order, hue_limits=hue_limits,
        dashes=dashes, markers=markers, style_order=style_order,
        size_limits=size_limits, size_range=size_range, size_order=size_order,
        units=units, estimator=estimator, ci=ci, n_boot=n_boot,
        sort=sort, errstyle=errstyle,
    )

    if ax is None:
        ax = plt.gca()

    p.plot(ax, legend, kwargs)

    return ax


def scatterplot(x=None, y=None, hue=None, style=None, size=None, data=None,
                palette=None, hue_order=None, hue_limits=None,
                markers=None, style_order=None,
                size_range=None, size_limits=None,
                x_bins=None, y_bins=None,
                estimator=None, ci=95, n_boot=1000, units=None,
                errstyle="bars", alpha="auto",
                x_jitter=None, y_jitter=None,
                ax=None, **kwargs):

    # TODO auto alpha

    pass
