"""Plant diagram generated from the GEMINI project file of a design.

The same project dictionary that GEMINI's simulator solves (components +
connections) is drawn as a flowsheet, so the picture always matches what was
simulated. Two outputs:

* Mermaid (``.md``): renders directly on GitHub and in VS Code, no install.
* Graphviz DOT (``.dot``, plus ``.svg``/``.png`` when the ``dot`` program exists).

    python -m agentic_design.diagram --doublets 2 --depth 3500 --hp 1 --abs 7.5 --ec 5
"""

import argparse
import shutil
import subprocess
from pathlib import Path

from agentic_design.annual import PlantDesign, run_year
from agentic_design.config import Assumptions
from agentic_design.plant_json import build_project_dict
from agentic_design.verify import operating_point
from agentic_design.wells import WellDesign

OUT = Path(__file__).resolve().parent / "results"

# stream -> (colour, label); decided from the port names of each connection
STREAMS = [("gas", "#8a5a00", "gas"), ("drive", "#c0392b", "brine"), ("primary", "#c0392b", "brine"),
           ("secondary", "#2471a3", "network"), ("water", "#2471a3", "network"), ("hot", "#2471a3", "network"),
           ("chilled", "#17a589", "cooling"), ("evap", "#17a589", "cooling"), ("source", "#c0392b", "brine"),
           ("", "#c0392b", "brine"), ("pressure", "#999999", "pressure")]
KIND = {"producer_well_fixed_rate": ("Production well", "#f5b7b1"), "injector_well_corrected": ("Injection well", "#f5b7b1"),
        "injector_well": ("Injection well", "#f5b7b1"), "mixer": ("Mixer", "#eeeeee"), "splitter": ("Splitter", "#eeeeee"),
        "separator": ("Gas separator", "#fad7a0"), "filter": ("Filter", "#eeeeee"),
        "heat_exchanger": ("Heat exchanger", "#aed6f1"), "boiler": ("Gas boiler", "#fad7a0"),
        "heat_pump": ("Heat pump", "#a9dfbf"), "absorption_chiller": ("Absorption chiller", "#a2d9ce"),
        "electric_chiller": ("Electric chiller", "#a2d9ce")}


def _stream(ports):
    names = " ".join(a + " " + b for a, b in ports).lower()
    if all("pressure" in a.lower() for a, _ in ports) or "flow" not in names and "output" not in names:
        return STREAMS[-1]  # state-only links (pressure/temperature) duplicate a flow link: not drawn
    for key, colour, label in STREAMS[:-2]:
        if key in names:
            return key, colour, label
    return STREAMS[-2]


def _label(name, comp):
    title, colour = KIND.get(comp["type"], (comp["type"], "#ffffff"))
    p = comp.get("parameters", {})
    extra = ""
    if "depth_m" in p:
        extra = f"{p['depth_m']:.0f} m"
    if comp["type"] == "boiler":
        extra = "associated gas" if "assoc" in name else "natural gas"
    if comp["type"] == "electric_chiller":
        extra = "grid electricity"
    if comp["type"] == "heat_exchanger":
        extra = f"UA {p.get('heat_transfer_coefficient', 0) / 1e6:.2f} MW/K"
    suffix = name.rsplit("_", 1)[-1]
    num = f" {suffix}" if suffix.isdigit() else (" " + suffix.upper() if suffix in ("a", "b") else "")
    return f"{title}{num}" + (f"\\n{extra}" if extra else ""), colour


def project_to_dot(project, title="", reinjection=False):
    lines = ["digraph plant {", '  rankdir=LR; splines=true; nodesep=0.35; ranksep=0.6;',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11];',
             '  edge [fontname="Helvetica", fontsize=9];',
             f'  labelloc="t"; label="{title}"; fontname="Helvetica"; fontsize=14;']
    for name, comp in project["components"].items():
        label, colour = _label(name, comp)
        lines.append(f'  "{name}" [label="{label}", fillcolor="{colour}"];')
    seen = set()
    for c in project["connections"]:
        _, colour, label = _stream(c["ports"])
        if label == "pressure" or (c["predecessor"], c["successor"], label) in seen:
            continue  # pressure links duplicate a flow link; one arrow per pair and stream
        seen.add((c["predecessor"], c["successor"], label))
        lines.append(f'  "{c["predecessor"]}" -> "{c["successor"]}" [color="{colour}", fontcolor="{colour}", label="{label}"];')
    if reinjection:  # not a GEMINI component: drawn dashed
        lines.append('  "gas_compressor" [label="Gas compressor\\n(reinjection, outside GEMINI)", fillcolor="#fad7a0", style="rounded,filled,dashed"];')
        lines.append('  "gas_splitter" -> "gas_compressor" [color="#8a5a00", fontcolor="#8a5a00", label="surplus gas"];')
        for name in project["components"]:
            if name.startswith("injector_well"):
                lines.append(f'  "gas_compressor" -> "{name}" [color="#8a5a00", style=dashed];')
    lines.append("}")
    return "\n".join(lines)


def project_to_mermaid(project, title=""):
    ids = {n: f"n{i}" for i, n in enumerate(project["components"])}
    lines = ["```mermaid", "flowchart LR"]
    for name, comp in project["components"].items():
        label, _ = _label(name, comp)
        lines.append(f'  {ids[name]}["{label.replace(chr(92) + "n", "<br/>")}"]')
    seen = set()
    for c in project["connections"]:
        _, _, label = _stream(c["ports"])
        if label == "pressure" or (c["predecessor"], c["successor"], label) in seen:
            continue
        seen.add((c["predecessor"], c["successor"], label))
        lines.append(f'  {ids[c["predecessor"]]} -- {label} --> {ids[c["successor"]]}')
    lines.append("```")
    return (f"# {title}\n\n" if title else "") + "\n".join(lines) + "\n"


def design_diagram(design: PlantDesign, a: Assumptions = None, out_dir=OUT):
    """Draw the plant on the day the most installed components run (ties: peak cooling day)."""
    a = a or Assumptions()
    daily, k, _, _ = run_year(design, a)
    cols = [c for c, cap in (("heat_pump_mw", design.heat_pump_mw), ("cooling_absorption_mw", design.absorption_mw),
                             ("cooling_electric_mw", design.electric_chiller_mw)) if cap > 0]
    active = (daily[cols] > 1e-3).sum(axis=1) if cols else daily["heating_mw"] * 0
    score = active * 1e3 + daily["cooling_mw"] + (daily["doublets_on"] == design.n_doublets) * 1e2
    day = int(score.idxmax())
    project = build_project_dict(design, operating_point(daily.loc[day], a), a, hx_ua_w_k=k["hx_ua_mw_k"] * 1e6)
    title = f"{design.name} (GEMINI project, {daily.loc[day, 'date'].date()})"
    out = Path(out_dir) / design.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "plant_diagram.md").write_text(project_to_mermaid(project, title), encoding="utf-8")
    dot = project_to_dot(project, title, reinjection=getattr(design, "gas_reinjection", False))
    (out / "plant_diagram.dot").write_text(dot, encoding="utf-8")
    files = [out / "plant_diagram.md", out / "plant_diagram.dot"]
    if shutil.which("dot"):
        for fmt in ("svg", "png"):
            subprocess.run(["dot", f"-T{fmt}", "-Gdpi=160", "-o", str(out / f"plant_diagram.{fmt}")],
                           input=dot.encode(), check=True)
            files.append(out / f"plant_diagram.{fmt}")
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doublets", type=int, default=2)
    ap.add_argument("--depth", type=float, default=3500.0)
    ap.add_argument("--hp", type=float, default=0.0)
    ap.add_argument("--abs", type=float, default=0.0)
    ap.add_argument("--ec", type=float, default=0.0)
    ap.add_argument("--ri", action="store_true", help="reinject surplus associated gas")
    args = ap.parse_args()
    from agentic_design.agent.tools import ToolBox
    name = ToolBox.canonical_name(args.doublets, args.depth, 0.20, 650.0, args.hp, args.abs, args.ec, args.ri)
    d = PlantDesign(name, args.doublets, WellDesign(args.depth), heat_pump_mw=args.hp, absorption_mw=args.abs,
                    electric_chiller_mw=args.ec, gas_reinjection=args.ri)
    for f in design_diagram(d):
        print(f)


if __name__ == "__main__":
    main()
