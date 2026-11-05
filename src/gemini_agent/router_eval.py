"""Calibrate and evaluate the optional router on labelled turns (data/router_labels.yaml).

  PYTHONPATH=src python -m gemini_agent.router_eval [model] [--write]

1. one router call per labelled turn (raw letter log-probabilities, tokens, latency);
2. temperature scaling fitted by 2-fold cross-validation, so every reported number is held-out;
3. accuracy, negative log-likelihood and expected calibration error, raw vs calibrated;
4. for each confidence threshold: how many turns the router would answer itself (off-topic /
   incomplete) and how many of those would be wrong ("false acts" -- the costly error);
5. --write stores the temperature (fitted on all turns) and the threshold with no false act that
   answers the most turns (the most cautious one on a tie) in data/router_calibration.json.
"""

from __future__ import annotations

import json
import math
import sys
import time

import yaml

from gemini_agent.router import CALIBRATION, DATA, LABELS, Router, _softmax

CODE = {v: k for k, v in LABELS.items()}
TEMPS = [round(0.5 * 1.08**i, 3) for i in range(70)]  # 0.5 ... ~110
THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
ACTS = {"off_topic", "incomplete"}  # the only labels the router answers itself


def _nll(rows, temp):
    return sum(
        -math.log(max(_softmax(r["raw"], temp)[CODE[r["label"]]], 1e-12)) for r in rows
    ) / len(rows)


def fit_temperature(rows) -> float:
    return min(TEMPS, key=lambda t: _nll(rows, t))


def ece(pairs, bins=5) -> float:
    """Expected calibration error of (confidence, correct) pairs."""
    tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, ok) for c, ok in pairs if lo < c <= hi or (b == 0 and c == 0)]
        if sel:
            tot += (
                len(sel)
                / len(pairs)
                * abs(sum(ok for _, ok in sel) / len(sel) - sum(c for c, _ in sel) / len(sel))
            )
    return round(tot, 3)


def evaluate(rows, temp_of) -> dict:
    """Held-out metrics; temp_of(row) gives the temperature fitted without that row."""
    pred = []
    for r in rows:
        p = _softmax(r["raw"], temp_of(r))
        best = max(p, key=p.get)
        pred.append(
            {
                "label": r["label"],
                "pred": LABELS[best],
                "conf": p[best],
                "p_true": p[CODE[r["label"]]],
                "design": r["design"],
            }
        )
    out = {
        "accuracy": round(sum(x["pred"] == x["label"] for x in pred) / len(pred), 3),
        "nll": round(sum(-math.log(max(x["p_true"], 1e-12)) for x in pred) / len(pred), 3),
        "ece": ece([(x["conf"], x["pred"] == x["label"]) for x in pred]),
        "thresholds": [],
    }
    for th in THRESHOLDS:
        acts = [
            x
            for x in pred
            if x["pred"] in ACTS
            and x["conf"] >= th
            and not (x["pred"] == "incomplete" and x["design"])
        ]
        out["thresholds"].append(
            {
                "threshold": th,
                "router_answers": len(acts),
                "false_acts": sum(x["pred"] != x["label"] for x in acts),
                "missed": sum(1 for x in pred if x["label"] in ACTS)
                - sum(x["pred"] == x["label"] for x in acts),
            }
        )
    out["confusion"] = [
        (x["label"], x["pred"], round(x["conf"], 3)) for x in pred if x["pred"] != x["label"]
    ]
    return out


def main(argv):
    from gemini_agent.agents import DEFAULT_MODEL

    write = "--write" in argv
    args = [a for a in argv if not a.startswith("--")]
    router = Router(
        args[0] if args else DEFAULT_MODEL, calibration=DATA / "_none.json"
    )  # raw: temperature 1
    rows = yaml.safe_load((DATA / "router_labels.yaml").read_text())
    for i, r in enumerate(rows):
        d = router.classify(r["message"], r["design"], r.get("previous"))
        r.update(
            raw={CODE[k]: v for k, v in d["raw_logprobs"].items()},
            tokens=d["prompt_tokens"],
            completion=d["completion_tokens"],
            latency=d["latency_s"],
        )
        print(
            f"{i + 1:2d}/{len(rows)} {r['label']:10s} raw->{d['label']:10s} "
            f"{d['latency_s']:6.1f} s",
            flush=True,
        )
    folds = [rows[0::2], rows[1::2]]
    t_fold = [fit_temperature(folds[1]), fit_temperature(folds[0])]  # fitted on the other fold
    fold_of = {id(r): k for k, f in enumerate(folds) for r in f}
    res = {
        "model": router.model,
        "n": len(rows),
        "date": time.strftime("%Y-%m-%d"),
        "router_prompt_tokens_mean": round(sum(r["tokens"] for r in rows) / len(rows)),
        "router_latency_s_mean": round(sum(r["latency"] for r in rows) / len(rows), 2),
        "cv_temperatures": t_fold,
        "raw": evaluate(rows, lambda r: 1.0),
        "calibrated_cv": evaluate(rows, lambda r: t_fold[fold_of[id(r)]]),
        "temperature_all": fit_temperature(rows),
    }
    # no false act; among those, the most turns answered; then the most cautious threshold
    safe = [
        t
        for t in res["calibrated_cv"]["thresholds"]
        if t["false_acts"] == 0 and t["router_answers"]
    ]
    res["threshold"] = (
        max(safe, key=lambda t: (t["router_answers"], t["threshold"]))["threshold"]
        if safe
        else None
    )
    print(json.dumps({k: v for k, v in res.items()}, indent=1))
    (DATA.parent.parent.parent / "runs").mkdir(exist_ok=True)
    (DATA.parent.parent.parent / "runs" / "router_eval.json").write_text(json.dumps(res, indent=1))
    if write and res["threshold"] is not None:
        CALIBRATION.write_text(
            json.dumps(
                {
                    "model": res["model"],
                    "temperature": res["temperature_all"],
                    "threshold": res["threshold"],
                    "fitted_on": res["n"],
                    "date": res["date"],
                    "eval": "runs/router_eval.json",
                },
                indent=1,
            )
        )
        print("wrote", CALIBRATION)


if __name__ == "__main__":
    main(sys.argv[1:])
