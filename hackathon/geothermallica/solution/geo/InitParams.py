"""Plot house style: figure size, colours and the matplotlib settings, applied on import (geo.common imports it before pyplot).

Text goes through LaTeX only when a latex binary is on the PATH, so the scripts run on a machine without LaTeX.
"""
import shutil

import matplotlib

fig_width = 5.7 * 0.75          # figure width, inches; figures are sized as multiples of it
fig_height = fig_width / 1.618  # golden ratio
COLORS = ["Navy", "Crimson", "mediumseagreen", "darkorchid"]
LINE = 0.75                     # line and axis width, points

matplotlib.rcParams.update({
    "font.size": 11, "axes.titlesize": 11, "axes.labelsize": 11,
    "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
    "font.family": "sans-serif", "font.weight": "medium",
    "mathtext.fontset": "dejavuserif", "mathtext.rm": "serif", "mathtext.bf": "serif:bold", "mathtext.it": "serif:italic",
    "xtick.direction": "in", "ytick.direction": "in", "xtick.top": True, "ytick.right": True,
    "xtick.major.size": 6, "ytick.major.size": 6, "xtick.minor.size": 3, "ytick.minor.size": 3,
    "xtick.major.width": 0.75 * LINE, "ytick.major.width": 0.75 * LINE,
    "xtick.minor.width": 0.75 * LINE, "ytick.minor.width": 0.75 * LINE,
    "axes.linewidth": LINE, "lines.linewidth": LINE, "lines.markeredgewidth": LINE, "lines.markersize": 7,
    "axes.spines.top": True, "axes.spines.right": True,
    "legend.handlelength": 1.7, "legend.frameon": False,
    "figure.figsize": [fig_width, fig_height], "figure.constrained_layout.use": True,
    "text.usetex": shutil.which("latex") is not None,
    "text.latex.preamble": "\n".join([r"\usepackage[utf8]{inputenc}", r"\usepackage[T1]{fontenc}",
                                      r"\usepackage[detect-all, per-mode=symbol]{siunitx}", r"\usepackage{amsmath, amssymb}"]),
})
