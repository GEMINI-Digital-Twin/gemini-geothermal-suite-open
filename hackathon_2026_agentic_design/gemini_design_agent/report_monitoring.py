"""Run the ESP smart-monitoring demo, write the report, figure and dashboard datasets.

    python report_monitoring.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gemini_design_agent.esp_monitoring import demo  # noqa: E402
from gemini_design_agent.system import SystemDesign  # noqa: E402

OUT = ROOT / "outputs_monitoring"
DASH = ROOT / "outputs_dashboard"
KIND_LABEL = {"gas_interference": "gas interference", "wear": "stage wear / scale", "thermal": "motor thermal",
              "trip": "pump trip", "unclassified": "unclassified"}


def main():
    ds = SystemDesign.from_dict(json.loads((ROOT / "outputs_claude" / "final_design.json").read_text(encoding="utf-8")))
    daily = pd.read_csv(ROOT / "outputs_claude" / "daily_dispatch.csv")
    res = demo(ds, daily, OUT, days=90, start_day=0)
    fr, sm = res.frame, res.summary

    # ---- dashboard datasets (hourly rows, reduced columns; alerts)
    keep = ["hour", "flow_m3_h", "freq_hz", "p_intake_bar", "p_discharge_bar", "t_motor_c", "current_a", "power_kw",
            "vibration_g", "mahalanobis", "cusum_eff", "eff_est", "health", "rul_days", "anomaly", "fault_kind", "true_label"]
    d = fr[keep].copy()
    d["day"] = d["hour"] / 24.0
    d["anomaly"] = d["anomaly"].astype(int)
    d.to_csv(DASH / "esp_telemetry.csv", index=False, float_format="%.4g")
    alerts = [{"hour": a.hour, "day": round(a.hour / 24 + 1, 1), "kind": KIND_LABEL.get(a.kind, a.kind), "score": a.score,
               "message": a.message, "action": a.action} for a in res.alerts]
    (DASH / "esp_alerts.json").write_text(json.dumps(alerts), encoding="utf-8")
    bp = fr["p_intake_bar"].min()

    # ---- report
    L = ["# Real-time ESP smart monitoring\n",
         "Hourly telemetry of one producer ESP (flow, VSD frequency, intake and discharge pressure, intake and motor "
         "temperature, motor current, power, vibration) is compared with the GEMINI-based digital twin at every sample. "
         "The twin gives the expected head (affinity-scaled ESP stage curve at the measured frequency and flow), intake "
         "pressure (inflow performance) and power; the monitor works on the residuals.\n",
         "**Detectors** (trained on the first 14 days, assumed healthy, no labels used):\n",
         "1. Robust Mahalanobis distance (minimum-covariance-determinant) over seven standardised features: head, intake-pressure and power residuals, current and flow variability, motor temperature, vibration.",
         "2. Isolation Forest on the same features (second opinion for non-elliptical deviations).",
         "3. CUSUM on the hydraulic-efficiency estimate, integrating quiet hours only, for slow drift the first two miss.",
         "4. Run/stop logic from motor current.\n",
         "A sample is anomalous when any detector fires on 3 of the last 4 hours; a fault signature classifier then labels it "
         "(gas interference: intake within 8 bar of the bubble point with unstable current/flow; stage wear: head below the twin "
         "with rising vibration or CUSUM drift; motor thermal: motor temperature and power above the twin; trip: no-load current). "
         "A health index (EWMA of hydraulic efficiency relative to a new pump, quiet hours only) and a remaining-useful-life "
         "estimate (linear trend of the last 7 days to the 90 % workover threshold) are updated hourly; the index is the "
         "`esp_efficiency_factor` the 25-year closed loop uses, so field data replaces the assumed wear rate.\n",
         "## Demo on the selected design (3 doublets, 3,500 m), January to March\n",
         "Synthetic telemetry from the twin at the dispatcher's set-points, with four injected faults the detector was not told about: "
         "gas interference days 21-24, gradual stage wear from day 41, motor overheating days 71-74, pump trip day 86.\n",
         "| Metric | Value |", "|---|---|",
         f"| Hours monitored | {sm['hours']} |",
         f"| Recall on fault hours | {sm['recall'] * 100:.1f} % |",
         f"| False-alarm rate on healthy hours | {sm['false_alarm_rate'] * 100:.2f} % |",
         f"| Fault label accuracy on detected hours | {sm['label_accuracy'] * 100:.0f} % |",
         f"| Health index at day 90 | {res.health_now:.1f} % (true hydraulic efficiency {fr['true_eff'].iloc[-1] * 100:.0f} %) |",
         f"| RUL at day 90 | {'workover due' if res.rul_days == 0 else f'{res.rul_days:.0f} days'} |",
         f"| Closed-loop override | esp_efficiency_factor = {res.esp_efficiency_factor:.2f} |",
         "\n## Alerts raised\n", "| Day | Fault | Max distance | Recommended action |", "|---|---|---|---|"]
    for a in res.alerts:
        L.append(f"| {a.hour / 24 + 1:.0f} | {KIND_LABEL.get(a.kind, a.kind)} | {a.score:.0f} | {a.action} |")
    L += ["\n## Wiring into the agentic loop\n",
          "- Trip or gas interference: the daily dispatcher re-balances flow to the other doublets inside the 50-300 m3/h band (the same code path as the maintenance windows).",
          "- Wear: the RUL feeds the closed-loop controller, which books the ESP workover at the next low-load window instead of on a fixed 5-year cycle.",
          "- The health index replaces the assumed 2 %/yr efficiency loss in the 25-year twin (`esp_efficiency_factor` override).",
          "- Limitations: telemetry is synthetic (no field data in the challenge); thresholds are set on a 14-day healthy window and would be re-tuned per well; the classifier is signature-based, a learned classifier needs labelled field events."]

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        t = fr["hour"] / 24.0
        fig, ax = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
        cols = {"gas_interference": "#8e44ad", "wear": "#e67e22", "thermal": "#c0392b", "trip": "#2c3e50", "unclassified": "#7f8c8d"}
        for a in ax:
            for k, c in cols.items():
                m = (fr["fault_kind"] == k).to_numpy()
                if m.any():
                    a.fill_between(t, 0, 1, where=m, transform=a.get_xaxis_transform(), color=c, alpha=0.15, lw=0)
        ax[0].plot(t, fr["flow_m3_h"], lw=0.8, label="flow m3/h"); ax[0].plot(t, fr["current_a"], lw=0.8, label="motor current A"); ax[0].legend(fontsize=8); ax[0].set_ylabel("flow / current")
        ax[1].plot(t, fr["p_intake_bar"], lw=0.8, label="intake pressure"); ax[1].axhline(res.frame["p_intake_bar"].min() * 0 + json.loads((ROOT / "outputs_claude" / "final_kpis.json").read_text())["kpis"]["bubble_point_bar"], ls=":", c="k", label="bubble point"); ax[1].plot(t, fr["t_motor_c"], lw=0.8, label="motor T C"); ax[1].legend(fontsize=8); ax[1].set_ylabel("bar / C")
        ax[2].plot(t, fr["health"], c="#27ae60", label="health index %"); ax[2].axhline(90, ls="--", c="#c0392b", label="workover threshold"); ax2 = ax[2].twinx(); ax2.plot(t, fr["rul_days"], c="#2980b9", lw=0.8, label="RUL days"); ax2.set_ylabel("RUL days"); ax[2].legend(fontsize=8, loc="lower left"); ax[2].set_ylabel("health %")
        ax[3].semilogy(t, fr["mahalanobis"], lw=0.6, label="robust Mahalanobis"); ax[3].axhline(sm["md_threshold"], ls="--", c="k", lw=0.8, label="threshold"); ax[3].plot(t, fr["cusum_eff"], lw=0.8, c="#e67e22", label="CUSUM efficiency"); ax[3].legend(fontsize=8); ax[3].set_ylabel("score"); ax[3].set_xlabel("day")
        for k, c in cols.items():
            ax[0].plot([], [], c=c, lw=6, alpha=0.3, label=KIND_LABEL[k])
        ax[0].legend(fontsize=7, ncol=4)
        fig.suptitle("ESP smart monitoring: shaded = detected fault episodes")
        fig.tight_layout(); fig.savefig(OUT / "fig_esp_monitoring.png", dpi=130); plt.close(fig)
        L.append("\n![esp monitoring](fig_esp_monitoring.png)\n")
    except Exception as e:  # pragma: no cover
        L.append(f"\n(figure not generated: {e!r})\n")
    (OUT / "ESP_MONITORING_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[10:20]))
    print("written", OUT / "ESP_MONITORING_REPORT.md", "and dashboard files", len(d), "rows,", len(alerts), "alerts")


if __name__ == "__main__":
    main()
