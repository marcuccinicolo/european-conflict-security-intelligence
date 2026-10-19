"""Synthetic control for the most exposed countries (RESEARCH_DESIGN.md §9.2).

Abadie, Diamond & Hainmueller (2010): the treated unit's pre-2014 path of
military burden is reproduced by a convex combination of distant donor countries;
the post-2014 gap between actual and synthetic is the treated unit's *excess*
response. Inference is by placebo-in-space: every donor is treated in turn, and
the treated unit's post/pre RMSPE ratio is ranked among all units.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

PRE = range(2005, 2014)
POST = range(2014, 2026)
DONOR_MIN_KM = 1000
TREATED = {"EST": "Estonia", "LVA": "Latvia", "LTU": "Lithuania", "POL": "Poland"}
BALTIC_AVG = "BALTIC"


def wide_panel(panel: pd.DataFrame, y: str = "share_gdp") -> pd.DataFrame:
    """Year x iso3 matrix; adds the unweighted Baltic average as a pseudo-unit."""
    w = panel.pivot_table(index="year", columns="iso3", values=y, aggfunc="first").astype(float)
    w = w.loc[min(PRE):max(POST)]
    if all(c in w for c in ("EST", "LVA", "LTU")):
        w[BALTIC_AVG] = w[["EST", "LVA", "LTU"]].mean(axis=1, skipna=False)
    return w


def donor_pool(panel: pd.DataFrame, wide: pd.DataFrame) -> list[str]:
    far = panel.groupby("iso3")["dist_russia_km"].first()
    far = far[far > DONOR_MIN_KM].index
    complete = wide.columns[wide.notna().all()]
    return sorted(set(far) & set(complete))


def fit_weights(Y0: np.ndarray, y1: np.ndarray) -> np.ndarray:
    """Non-negative weights summing to one that minimise ||y1 - Y0 w||^2."""
    J = Y0.shape[1]
    obj = lambda w: float(((y1 - Y0 @ w) ** 2).sum())  # noqa: E731
    grad = lambda w: -2 * Y0.T @ (y1 - Y0 @ w)  # noqa: E731
    res = minimize(obj, np.full(J, 1 / J), jac=grad, method="SLSQP", bounds=[(0, 1)] * J,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500, "ftol": 1e-12})  # fmt: skip
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def synth(wide: pd.DataFrame, treated: str, donors: list[str],
          pre=PRE, post=POST) -> dict:  # fmt: skip
    donors = [d for d in donors if d != treated]
    pre, post = list(pre), list(post)
    Y0 = wide.loc[pre, donors].to_numpy()
    y1 = wide.loc[pre, treated].to_numpy()
    w = fit_weights(Y0, y1)
    years = pre + post
    synthetic = wide.loc[years, donors].to_numpy() @ w
    actual = wide.loc[years, treated].to_numpy()
    gap = pd.Series(actual - synthetic, index=years)
    pre_rmspe = float(np.sqrt((gap.loc[pre] ** 2).mean()))
    post_rmspe = float(np.sqrt((gap.loc[post] ** 2).mean()))
    return {
        "treated": treated,
        "weights": pd.Series(w, index=donors).sort_values(ascending=False),
        "actual": pd.Series(actual, index=years),
        "synthetic": pd.Series(synthetic, index=years),
        "gap": gap,
        "pre_rmspe": pre_rmspe,
        "post_rmspe": post_rmspe,
        "ratio": post_rmspe / pre_rmspe if pre_rmspe > 0 else np.inf,
    }


def placebo_p(wide: pd.DataFrame, treated: str, donors: list[str], result: dict) -> dict:
    """Placebo-in-space: rank of the treated RMSPE ratio among treated + all donors."""
    ratios = {d: synth(wide, d, [x for x in donors if x != d])["ratio"] for d in donors}
    rank = 1 + sum(r >= result["ratio"] for r in ratios.values())
    return {"rank": int(rank), "units": len(donors) + 1, "p": rank / (len(donors) + 1),
            "placebo_ratios": ratios}  # fmt: skip


def placebo_in_time(wide: pd.DataFrame, treated: str, donors: list[str], fake: int = 2009) -> float:
    """Mean gap after a fake treatment year, using only pre-2014 data."""
    r = synth(wide, treated, donors, pre=range(min(PRE), fake), post=range(fake, 2014))
    return float(r["gap"].loc[fake:2013].mean())


def run(panel: pd.DataFrame) -> dict:
    wide = wide_panel(panel)
    donors = donor_pool(panel, wide)
    names = panel.groupby("iso3")["country"].first().to_dict()
    names[BALTIC_AVG] = "Baltic states (average)"
    out = {"donors": [names[d] for d in donors], "donor_min_km": DONOR_MIN_KM, "units": {}}
    for unit in [BALTIC_AVG, *TREATED]:
        if unit not in wide or wide.loc[list(PRE) + list(POST), unit].isna().any():
            continue
        r = synth(wide, unit, donors)
        pl = placebo_p(wide, unit, donors, r)
        out["units"][unit] = {
            "name": names[unit],
            "weights": {names[k]: float(v) for k, v in r["weights"].items() if v > 0.001},
            "years": list(r["actual"].index.astype(int)),
            "actual": r["actual"].round(4).tolist(),
            "synthetic": r["synthetic"].round(4).tolist(),
            "mean_gap_2014_2021": float(r["gap"].loc[2014:2021].mean()),
            "mean_gap_2022_2025": float(r["gap"].loc[2022:2025].mean()),
            "gap_2025": float(r["gap"].loc[2025]),
            "pre_rmspe": r["pre_rmspe"],
            "ratio": r["ratio"],
            "placebo_rank": pl["rank"], "placebo_units": pl["units"], "placebo_p": pl["p"],
            "placebo_in_time_gap": placebo_in_time(wide, unit, donors),
        }  # fmt: skip
    return out
