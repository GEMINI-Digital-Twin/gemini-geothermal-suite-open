"""Write GEMINI's own docstrings and README to ai/runs/gemini_docs.md for the notes corpus; run: python AI09_gemini_docs.py."""
import ast
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

DEV = Path(os.environ.get("GEMINI_DEV_SRC", os.path.expanduser("~/src/gemini-dev/src")))
SRC = DEV if (DEV / "gemini_model").is_dir() else Path(os.environ.get("GEMINI_SRC", os.path.expanduser("~/src/gemini-geothermal-suite-open/src")))
OUT = Path(__file__).parent / "runs" / "gemini_docs.md"
MAX_DOC, MAX_FUNC, MAX_FILE = 40, 10, 2200   # line caps: module/class docstring, function docstring, whole file
# keys GEMINI docstrings rarely list, read from the code instead
KEY = {"parameters": re.compile(r"self\.parameters\[\s*[\"'](\w+)"), "inputs": re.compile(r"\bu\[\s*[\"'](\w+)"),
       "outputs": re.compile(r"self\.output\[\s*[\"'](\w+)")}


def doc(node, indent="", cap=MAX_DOC):
    lines = (ast.get_docstring(node) or "").splitlines()
    lines = lines[:cap] + ["..."] if len(lines) > cap else lines
    return "\n".join(indent + s if s else "" for s in lines)


def modules():
    return [p for pkg in ("gemini_model", "gemini_simulator") for p in sorted((SRC / pkg).rglob("*.py"))
            if "__pycache__" not in p.parts and "test" not in p.name.lower()]


def section(path, sha, common):
    src = path.read_text(errors="ignore")
    tree = ast.parse(src)
    rel = path.relative_to(SRC).as_posix()
    out = [f"## {rel}", "", f"GEMINI source: src/{rel} @ {sha}", "", doc(tree) or "(no module docstring)", ""]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out += [f"### class {node.name}", "", doc(node) or "(no class docstring)", ""]
            code = ast.get_source_segment(src, node) or ""
            for kind, rx in KEY.items():
                keys = sorted(set(rx.findall(code)))
                if keys:
                    out.append(f"{kind} (keys read from the code): {', '.join(keys)}")
            out.append("")
            funcs = [f for f in node.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs = [node]
        else:
            continue
        for f in funcs:
            d = ast.get_docstring(f)
            if d and common[d] < 3:   # a docstring repeated 3+ times is boilerplate: skip
                out += [f"- `{f.name}`:", doc(f, "  ", MAX_FUNC), ""]
    return out


def main():
    sha = subprocess.run(["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "no git"
    paths = modules()
    common = Counter(ast.get_docstring(f) for p in paths for f in ast.walk(ast.parse(p.read_text(errors="ignore")))
                     if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)))
    lines = [f"# GEMINI documentation (TNO) @ {sha}", "", f"Extracted by ai/AI09_gemini_docs.py from {SRC}.", ""]
    for p in paths:
        lines += section(p, sha, common)
    lines = "\n".join(lines).splitlines()
    readme, tail = SRC.parent / "README.md", []
    if readme.exists():   # the README goes last and is never cut; the module part gives way
        tail = ["## README.md", "", f"GEMINI source: README.md @ {sha}", ""]
        tail += [re.sub(r"^#{1,3}(?=\s)", "####", s) for s in readme.read_text(errors="ignore").splitlines()]
    room = MAX_FILE - len(tail)
    if len(lines) > room:
        lines = lines[:room - 2] + ["", f"... (modules cut at {room} lines to keep the file at {MAX_FILE})"]
    lines += [""] + tail
    OUT.write_text("\n".join(lines) + "\n")
    print(f"{OUT}: {len(paths)} modules, {len(lines)} lines, GEMINI {SRC} @ {sha}")


if __name__ == "__main__":
    main()
