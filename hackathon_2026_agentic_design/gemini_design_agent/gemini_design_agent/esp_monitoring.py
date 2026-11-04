"""Real-time ESP smart monitoring: twin-based residuals, multivariate anomaly detection,
fault classification, health index and remaining useful life (RUL).

The monitor sits between the live well and the yearly closed-loop controller:

    sensors (hourly)  ->  digital-twin expectation (GEMINI ESP curve + inflow)
                      ->  residuals + robust multivariate anomaly score
                      ->  fault signature classifier (gas / wear / thermal / trip)
                      ->  health index, RUL, alert with recommended action
                      ->  esp_efficiency_factor override for the closed-loop twin

No field data exists for the hackathon case, so :func:`simulate_esp_telemetry` generates hourly
telemetry from the twin at the dispatcher's set-points and injects four fault modes. The
detector never sees the fault labels; they are only used to score it.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .subsurface import DoubletModel
from .system import SystemDesign, get_doublet_model
from .spec import SPEC, HackathonSpec

SENSORS = ["flow_m3_h", "freq_hz", "p_intake_bar", "p_discharge_bar", "t_intake_c", "t_motor_c",
           "current_a", "power_kw", "vibration_g"]
MOTOR_V = 3000.0          # V, line-line
MOTOR_PF = 0.85
MOTOR_ETA = 0.92
TRIP_CURRENT_A = 5.0


# ------------------------------------------------------------------------------------------
# Twin expectation at an operating point
# ------------------------------------------------------------------------------------------
class EspTwin:
    """Cheap per-sample expectation built on the DoubletModel (GEMINI ESP curve and IPR)."""

    def __init__(self, model: DoubletModel, ref_flow_m3_h: float):
        self.m = model
        wp = model.evaluate(ref_flow_m3_h)
        self.stages = wp.esp_stages
        self.bubble_point_bar = wp.bubble_point_bar
        self.ref_flow = ref_flow_m3_h
        self.ref_p_in = wp.esp_intake_pressure_bar
        self.ref_t_in = wp.esp_intake_temperature_c
        self.pi = model._pi  # m3/h per bar
        self.eta_h = model.spec.constraints.pump_hydraulic_efficiency

    def head_bar(self, freq: float, flow: float) -> float:
        return self.m._esp_head_bar(self.stages, freq, flow)

    def p_intake_bar(self, flow: float) -> float:
        # intake pressure falls with drawdown: 1/PI bar per m3/h around the reference point
        return self.ref_p_in - (flow - self.ref_flow) / self.pi

    def power_kw(self, freq: float, flow: float, eff_factor: float = 1.0) -> float:
        head = self.head_bar(freq, flow)
        return flow / 3600.0 * head * 1e5 / self.eta_h / eff_factor / 1e3

    def current_a(self, power_kw: float) -> float:
        return power_kw * 1e3 / MOTOR_ETA / (math.sqrt(3.0) * MOTOR_V * MOTOR_PF)

    def expect(self, freq: np.ndarray, flow: np.ndarray) -> pd.DataFrame:
        head = np.array([self.head_bar(f, q) for f, q in zip(freq, flow)])
        p_in = self.p_intake_bar(flow)
        pw = np.array([self.power_kw(f, q) for f, q in zip(freq, flow)])
        return pd.DataFrame({"head_bar": head, "p_intake_bar": p_in, "p_discharge_bar": p_in + head,
                             "power_kw": pw, "current_a": self.current_a(pw)})


# ------------------------------------------------------------------------------------------
# Telemetry simulator with injected faults
# ------------------------------------------------------------------------------------------
@dataclass
class FaultWindow:
    kind: str                 # gas_interference | wear | thermal | trip
    start_h: int
    end_h: int
    severity: float = 1.0


DEFAULT_FAULTS = [
    FaultWindow("gas_interference", 20 * 24, 24 * 24, 1.0),
    FaultWindow("wear", 40 * 24, 90 * 24, 1.0),            # gradual, keeps growing
    FaultWindow("thermal", 70 * 24, 74 * 24, 1.0),
    FaultWindow("trip", 85 * 24, 86 * 24, 1.0),
]


def simulate_esp_telemetry(twin: EspTwin, daily_flow: np.ndarray, daily_freq: np.ndarray,
                           days: int = 90, faults: list[FaultWindow] | None = None, seed: int = 7,
                           t_motor_base_c: float | None = None) -> pd.DataFrame:
    """Hourly ESP sensor data for one producer. Set-points come from the dispatcher (daily flow
    and VSD frequency); hourly variation, sensor noise and fault signatures are added."""
    rng = np.random.default_rng(seed)
    faults = DEFAULT_FAULTS if faults is None else faults
    n = days * 24
    hours = np.arange(n)
    day = hours // 24
    flow_sp = np.asarray(daily_flow)[day % len(daily_flow)]
    freq_sp = np.asarray(daily_freq)[day % len(daily_freq)]
    # intra-day modulation (district demand follows a diurnal pattern) and slow drift
    flow_sp = flow_sp * (1.0 + 0.04 * np.sin(2 * np.pi * (hours % 24) / 24.0)) + rng.normal(0, 1.5, n)
    freq_sp = freq_sp * (1.0 + 0.02 * np.sin(2 * np.pi * (hours % 24) / 24.0))

    t_in = twin.ref_t_in + rng.normal(0, 0.3, n)
    t_motor_base = t_motor_base_c if t_motor_base_c is not None else twin.ref_t_in + 25.0
    eff = np.ones(n)
    gas = np.zeros(n)
    thermal = np.zeros(n)
    trip = np.zeros(n, dtype=bool)
    label = np.array(["healthy"] * n, dtype=object)
    for fw in faults:
        sl = slice(fw.start_h, min(fw.end_h, n))
        label[sl] = fw.kind
        if fw.kind == "wear":
            # efficiency erodes linearly to about 0.85 x severity by the end of the window
            ramp = np.linspace(0, 1, min(fw.end_h, n) - fw.start_h)
            eff[sl] = 1.0 - 0.15 * fw.severity * ramp
            eff[min(fw.end_h, n):] = eff[sl][-1] if len(ramp) else 1.0
        elif fw.kind == "gas_interference":
            gas[sl] = fw.severity
        elif fw.kind == "thermal":
            thermal[sl] = fw.severity
        elif fw.kind == "trip":
            trip[sl] = True

    # actual flow: wear reduces head so the VSD cannot fully compensate (flow slips a few %)
    flow = flow_sp * (1.0 - 0.3 * (1.0 - eff))
    freq = freq_sp.copy()
    # gas interference: intake pressure near bubble point, head and flow unstable
    gas_noise = gas * rng.normal(0, 1.0, n)
    flow = flow * (1.0 - 0.12 * gas * (0.5 + 0.5 * np.abs(gas_noise)))
    p_in = twin.p_intake_bar(flow) - gas * (twin.p_intake_bar(flow) - twin.bubble_point_bar - 2.0) + rng.normal(0, 0.4, n)
    head = np.array([twin.head_bar(f, q) for f, q in zip(freq, flow)]) * eff
    head = head * (1.0 - 0.15 * gas * np.abs(gas_noise))
    p_disc = p_in + head + rng.normal(0, 0.5, n)
    power = np.array([twin.power_kw(f, q) for f, q in zip(freq, flow)])   # worn stages: same power, less head
    power = power * (1.0 + 0.10 * gas * gas_noise) * (1.0 + 0.06 * thermal)
    current = twin.current_a(power) * (1.0 + 0.03 * rng.normal(0, 1, n) * (1 + 3 * gas))
    vib = 0.6 + 0.015 * np.abs(flow - twin.ref_flow) / 10.0 + 2.5 * (1.0 - eff) + 0.6 * gas * np.abs(gas_noise) + rng.normal(0, 0.05, n)
    t_motor = t_motor_base + 0.02 * (power - np.median(power)) + 18.0 * thermal * np.linspace(0.3, 1.0, n) + rng.normal(0, 0.5, n)
    # trip: pump stops, current to no-load, flow to zero, discharge to intake
    flow[trip] = rng.normal(0, 0.5, trip.sum())
    freq[trip] = 0.0
    power[trip] = 2.0
    current[trip] = TRIP_CURRENT_A + rng.normal(0, 0.3, trip.sum())
    p_disc[trip] = p_in[trip] + rng.normal(0, 0.5, trip.sum())
    vib[trip] = 0.05
    df = pd.DataFrame({"hour": hours, "flow_m3_h": flow, "freq_hz": freq, "p_intake_bar": p_in,
                       "p_discharge_bar": p_disc, "t_intake_c": t_in, "t_motor_c": t_motor,
                       "current_a": current, "power_kw": power, "vibration_g": vib,
                       "true_label": label, "true_eff": eff})
    return df


# ------------------------------------------------------------------------------------------
# Monitor
# ------------------------------------------------------------------------------------------
@dataclass
class Alert:
    hour: int
    kind: str
    score: float
    message: str
    action: str


@dataclass
class MonitorResult:
    frame: pd.DataFrame
    alerts: list[Alert]
    health_now: float
    rul_days: float | None
    esp_efficiency_factor: float
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"health_now": self.health_now, "rul_days": self.rul_days,
                "esp_efficiency_factor": self.esp_efficiency_factor, "summary": self.summary,
                "alerts": [a.__dict__ for a in self.alerts]}


class EspMonitor:
    """Hybrid monitor: physics residuals against the twin + data-driven multivariate detector."""

    def __init__(self, twin: EspTwin, train_hours: int = 14 * 24, contamination: float = 0.01,
                 health_workover: float = 90.0, cusum_k: float = 0.5, cusum_h: float = 8.0):
        self.twin = twin
        self.train_hours = train_hours
        self.contamination = contamination
        self.health_workover = health_workover
        self.cusum_k, self.cusum_h = cusum_k, cusum_h

    # ---- features
    def _features(self, df: pd.DataFrame) -> pd.DataFrame:
        exp = self.twin.expect(df["freq_hz"].to_numpy(), df["flow_m3_h"].to_numpy())
        f = pd.DataFrame(index=df.index)
        running = df["current_a"] > 2 * TRIP_CURRENT_A
        f["r_head"] = (df["p_discharge_bar"] - df["p_intake_bar"]) - exp["head_bar"]            # bar
        f["r_pin"] = df["p_intake_bar"] - exp["p_intake_bar"]                                   # bar
        f["r_power"] = (df["power_kw"] - exp["power_kw"]) / exp["power_kw"].clip(lower=1.0)     # fraction
        # hydraulic efficiency factor estimate: (q*head/eta_h) / P_el, relative to new pump
        hyd_kw = df["flow_m3_h"] / 3600.0 * (df["p_discharge_bar"] - df["p_intake_bar"]).clip(lower=0) * 1e5 / self.twin.eta_h / 1e3
        f["eff_est"] = np.where(running, hyd_kw / df["power_kw"].clip(lower=1.0), np.nan)
        f["margin_pb"] = df["p_intake_bar"] - self.twin.bubble_point_bar                        # bar above bubble point
        f["cur_cv"] = df["current_a"].rolling(6, min_periods=3).std() / df["current_a"].rolling(6, min_periods=3).mean()
        f["flow_cv"] = df["flow_m3_h"].rolling(6, min_periods=3).std() / df["flow_m3_h"].rolling(6, min_periods=3).mean().clip(lower=1)
        f["t_motor"] = df["t_motor_c"]
        f["vib"] = df["vibration_g"]
        f["running"] = running
        return f.bfill()

    def run(self, df: pd.DataFrame) -> MonitorResult:
        from sklearn.covariance import MinCovDet
        from sklearn.ensemble import IsolationForest

        f = self._features(df)
        cols = ["r_head", "r_pin", "r_power", "cur_cv", "flow_cv", "t_motor", "vib"]
        train = f.loc[: self.train_hours - 1, cols].to_numpy()
        mu, sd = train.mean(0), train.std(0) + 1e-9
        z_all = (f[cols].to_numpy() - mu) / sd
        z_train = (train - mu) / sd
        # detector 1: robust Mahalanobis distance (MinCovDet on the healthy window)
        mcd = MinCovDet(random_state=0).fit(z_train)
        md = np.sqrt(mcd.mahalanobis(z_all))
        md_thr = np.quantile(np.sqrt(mcd.mahalanobis(z_train)), 0.995) * 1.5
        # detector 2: Isolation Forest on the same standardised features
        iso = IsolationForest(n_estimators=200, contamination=self.contamination, random_state=0).fit(z_train)
        iso_score = -iso.score_samples(z_all)
        iso_thr = np.quantile(-iso.score_samples(z_train), 0.995)
        # detector 3: CUSUM on the efficiency estimate (slow drift the others miss). It only
        # integrates "quiet" hours (no fast-detector alarm) so a transient such as gas
        # interference cannot latch it, and it resets when the pump stops.
        fast = (md > md_thr) | (iso_score > iso_thr)
        eff = f["eff_est"].to_numpy()
        eff0 = np.nanmedian(eff[: self.train_hours])
        eff_sd = np.nanstd(eff[: self.train_hours]) + 1e-6
        running = f["running"].to_numpy()
        s, cus = 0.0, np.zeros(len(eff))
        for i, e in enumerate(eff):
            if not running[i]:
                s = 0.0
            elif not (np.isnan(e) or fast[i]):
                s = min(4.0 * self.cusum_h, max(0.0, s + ((eff0 - e) / eff_sd - self.cusum_k)))
            cus[i] = s
        anomaly = fast | (cus > self.cusum_h) | (~running)
        # debounce: 3 of the last 4 hours anomalous
        a = pd.Series(anomaly.astype(int)).rolling(4, min_periods=1).sum().to_numpy() >= 3
        a |= ~f["running"].to_numpy()

        # ---- fault classification by residual signature (per hour)
        kind = np.array(["normal"] * len(f), dtype=object)
        zf = pd.DataFrame(z_all, columns=cols)
        for i in np.where(a)[0]:
            if not f["running"].iat[i]:
                kind[i] = "trip"
            elif (f["margin_pb"].iat[i] < 8.0 and (zf["cur_cv"].iat[i] > 2 or zf["flow_cv"].iat[i] > 2)) or zf["r_pin"].iat[i] < -4:
                kind[i] = "gas_interference"
            elif zf["t_motor"].iat[i] > 3 and zf["r_power"].iat[i] > 1:
                kind[i] = "thermal"
            elif cus[i] > self.cusum_h or (zf["r_head"].iat[i] < -2 and zf["vib"].iat[i] > 1):
                kind[i] = "wear"
            else:
                kind[i] = "unclassified"

        # ---- health index (EWMA of the efficiency estimate relative to new) and RUL
        # the health index integrates only quiet running hours, so a transient (gas slug, trip)
        # does not read as lost pump life
        eff_rel = pd.Series(np.where(running & ~fast, eff / eff0, np.nan)).clip(upper=1.05)
        health = (100.0 * eff_rel.ewm(halflife=24, ignore_na=True).mean()).ffill().to_numpy()
        health_now = float(np.nanmean(health[-24:]))

        def rul_at(end: int) -> float | None:
            hh = health[max(0, end - 7 * 24):end]
            ok = ~np.isnan(hh)
            if ok.sum() < 48:
                return None
            h_now = float(np.nanmean(hh[-24:]))
            if h_now <= self.health_workover:
                return 0.0
            slope_per_h = np.polyfit(np.arange(len(hh))[ok], hh[ok], 1)[0]
            if slope_per_h >= -0.002:     # flat or improving: no finite RUL
                return None
            return float(min(3650.0, (h_now - self.health_workover) / (-slope_per_h) / 24.0))

        rul_series = np.full(len(health), np.nan)
        for end in range(self.train_hours + 24, len(health) + 1, 24):   # no RUL inside the training window
            r = rul_at(end)
            rul_series[end - 24:end] = np.nan if r is None else r
        rul_days = rul_at(len(health))

        # ---- alerts: one per contiguous episode of the same kind
        actions = {
            "gas_interference": "Intake within 8 bar of the bubble point with unstable current: reduce VSD frequency 2-3 Hz to raise intake pressure, re-balance flow to the other doublets; if recurring, set the ESP deeper at the next workover.",
            "wear": "Hydraulic efficiency drifting down with rising vibration (scale or stage wear): book an ESP workover when RUL falls under 90 days; meanwhile hold frequency and let the dispatcher share load across doublets.",
            "thermal": "Motor temperature and power above the twin with normal flow: check motor cooling flow past the housing and the VSD harmonics; derate to 45 Hz until cleared.",
            "trip": "Pump stopped (no-load current, zero flow): dispatcher moves the load to the remaining doublets within the 300 m3/h cap; investigate shaft or electrical fault before restart.",
            "unclassified": "Multivariate deviation from the twin without a known signature: hold set-point and review sensors.",
        }
        alerts: list[Alert] = []
        i = 0
        while i < len(kind):
            if a[i] and kind[i] != "normal":
                j = i
                while j + 1 < len(kind) and a[j + 1] and kind[j + 1] == kind[i]:
                    j += 1
                if j - i + 1 >= 8:  # at least 8 h
                    score = float(np.nanmax(md[i:j + 1]))
                    alerts.append(Alert(int(i), str(kind[i]), round(score, 1),
                                        f"{kind[i].replace('_', ' ')} detected from hour {i} to {j} (day {i // 24 + 1}-{j // 24 + 1}), "
                                        f"max distance {score:.1f}, health {health[j]:.0f} %", actions[str(kind[i])]))
                i = j + 1
            else:
                i += 1

        out = df.copy()
        out["anomaly"] = a
        out["fault_kind"] = kind
        out["mahalanobis"] = md
        out["iso_score"] = iso_score
        out["cusum_eff"] = cus
        out["eff_est"] = eff
        out["health"] = health
        out["rul_days"] = rul_series
        for c in cols:
            out["z_" + c] = zf[c].to_numpy()
        eff_factor = float(np.clip(health_now / 100.0, 0.5, 1.0))
        summary = {"hours": int(len(df)), "anomalous_hours": int(a.sum()), "n_alerts": len(alerts),
                   "md_threshold": float(md_thr), "iso_threshold": float(iso_thr), "eff0": float(eff0)}
        if "true_label" in df:
            truth = df["true_label"].to_numpy() != "healthy"
            tp = int((a & truth).sum()); fp = int((a & ~truth).sum()); fn = int((~a & truth).sum())
            summary.update({"true_positive_h": tp, "false_positive_h": fp, "false_negative_h": fn,
                            "recall": tp / max(1, truth.sum()), "false_alarm_rate": fp / max(1, (~truth).sum())})
            # classification accuracy on detected fault hours
            det = a & truth
            summary["label_accuracy"] = float((kind[det] == df["true_label"].to_numpy()[det]).mean()) if det.sum() else None
        return MonitorResult(out, alerts, health_now, rul_days, eff_factor, summary)


# ------------------------------------------------------------------------------------------
# Convenience: build twin from a design, run the demo, write outputs
# ------------------------------------------------------------------------------------------
def demo(ds: SystemDesign, daily: pd.DataFrame, out_dir: Path, days: int = 90, spec: HackathonSpec = SPEC,
         start_day: int = 0) -> MonitorResult:
    model = get_doublet_model(ds, spec)
    flows = daily["flow_per_doublet"].to_numpy()
    freqs = daily["esp_freq"].to_numpy()
    sel = slice(start_day, start_day + days)
    twin = EspTwin(model, float(np.median(flows[sel])))
    tele = simulate_esp_telemetry(twin, flows[sel], freqs[sel], days=days)
    res = EspMonitor(twin).run(tele)
    out_dir.mkdir(exist_ok=True, parents=True)
    res.frame.to_csv(out_dir / "esp_telemetry.csv", index=False, float_format="%.4g")
    (out_dir / "esp_monitoring.json").write_text(json.dumps(res.to_dict(), indent=1, default=float), encoding="utf-8")
    return res
