"""Proximity to Russia and military burden: two-way fixed-effects event study.

Implements the specification in docs/RESEARCH_DESIGN.md. Estimation is plain
numpy OLS with country and year dummies, so the wild cluster bootstrap can reuse
the same design matrix for thousands of draws (statsmodels is used in the tests
to cross-check point estimates and cluster-robust standard errors).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

EXCLUDED = {"RUS": "belligerent", "UKR": "belligerent", "BLR": "co-belligerent",
            "ISL": "no armed forces (zero spending)"}  # fmt: skip
CAUCASUS = {"ARM", "AZE", "GEO"}
BALTICS = {"EST", "LVA", "LTU"}
BASE_YEAR = 2013
YEARS = (2005, 2025)


# --------------------------------------------------------------------- panel


def build_panel(
    share_gdp: pd.DataFrame,
    milex_real: pd.DataFrame,
    exposure: pd.DataFrame,
    wdi: pd.DataFrame | None = None,
    years: tuple[int, int] = YEARS,
    include_caucasus: bool = False,
) -> pd.DataFrame:
    """Country-year panel. Rows with a missing outcome are dropped later, per model."""
    g = share_gdp[["iso3", "country", "year", "value"]].rename(columns={"value": "share_gdp"})
    k = milex_real[["iso3", "year", "value"]].rename(columns={"value": "milex_real"})
    d = g.merge(k, on=["iso3", "year"], how="outer")
    d["country"] = d.groupby("iso3")["country"].transform("first")
    d = d[d["year"].between(*years)]
    drop = set(EXCLUDED) | (set() if include_caucasus else CAUCASUS)
    d = d[~d["iso3"].isin(drop)]
    ex = exposure[["iso3", "dist_russia_km", "dist_front_km", "nato_accession_year"]]
    d = d.merge(ex, on="iso3", how="inner")
    d["dist"] = d["dist_russia_km"].astype(float) / 1000
    d["dist_front"] = d["dist_front_km"].astype(float) / 1000
    acc = d["nato_accession_year"].astype("Float64")
    d["nato"] = (acc.notna() & (d["year"] >= acc)).astype(float)
    d["share_gdp"] = d["share_gdp"].astype(float)
    real = d["milex_real"].astype(float)
    d["log_milex_real"] = np.log(real.where(real > 0))
    if wdi is not None:
        w = wdi[["iso3", "year", "gdp_pc_const2015_usd"]]
        d = d.merge(w, on=["iso3", "year"], how="left")
        d["log_gdp_pc"] = np.log(d["gdp_pc_const2015_usd"].astype(float))
    return d.sort_values(["iso3", "year"], ignore_index=True)


# ---------------------------------------------------------------- estimation


@dataclass
class Fit:
    terms: list[str]
    coef: dict[str, float]
    se: dict[str, float]
    n_obs: int
    n_clusters: int
    vcov_terms: np.ndarray
    p_boot: dict[str, float] = field(default_factory=dict)
    countries: list[str] = field(default_factory=list)

    def ci(self, term: str, level: float = 0.95) -> tuple[float, float]:
        q = stats.t.ppf(0.5 + level / 2, self.n_clusters - 1)
        return self.coef[term] - q * self.se[term], self.coef[term] + q * self.se[term]

    def p_cluster(self, term: str) -> float:
        t = self.coef[term] / self.se[term]
        return float(2 * stats.t.sf(abs(t), self.n_clusters - 1))


def design(df: pd.DataFrame, y: str, terms: list[str]):
    d = df.dropna(subset=[y, *terms]).reset_index(drop=True)
    X_terms = d[terms].to_numpy(float)
    C = pd.get_dummies(d["iso3"], drop_first=True, dtype=float).to_numpy()
    T = pd.get_dummies(d["year"], drop_first=True, dtype=float).to_numpy()
    X = np.column_stack([X_terms, np.ones(len(d)), C, T])
    groups = pd.factorize(d["iso3"])[0]
    return d, d[y].to_numpy(float), X, groups


def _cluster_vcov(X, u, groups, XtX_inv):
    G = groups.max() + 1
    N, K = X.shape
    S = np.zeros((G, K))
    np.add.at(S, groups, X * u[:, None])
    meat = S.T @ S
    c = G / (G - 1) * (N - 1) / (N - K)  # CR1, as in Stata
    return c * XtX_inv @ meat @ XtX_inv


def fit(df: pd.DataFrame, y: str, terms: list[str]) -> Fit:
    d, yv, X, g = design(df, y, terms)
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ yv
    V = _cluster_vcov(X, yv - X @ b, g, XtX_inv)
    k = len(terms)
    return Fit(
        terms=terms,
        coef={t: float(b[i]) for i, t in enumerate(terms)},
        se={t: float(np.sqrt(V[i, i])) for i, t in enumerate(terms)},
        n_obs=len(d),
        n_clusters=int(g.max() + 1),
        vcov_terms=V[:k, :k],
        countries=sorted(d["country"].unique()),
    )


def wild_cluster_p(df: pd.DataFrame, y: str, terms: list[str], term: str,
                   draws: int = 9999, seed: int = 20261017) -> float:  # fmt: skip
    """Wild cluster bootstrap-t p-value with the null (coef = 0) imposed (WCR, Rademacher)."""
    d, yv, X, g = design(df, y, terms)
    j = terms.index(term)
    G, N = g.max() + 1, len(yv)
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ yv

    def t_stats(Y):  # Y: N x B
        B_ = XtX_inv @ X.T @ Y
        U = Y - X @ B_
        z = X @ XtX_inv[j]  # row j of the sandwich bread
        S = np.zeros((G, Y.shape[1]))
        np.add.at(S, g, z[:, None] * U)
        c = G / (G - 1) * (N - 1) / (N - X.shape[1])
        return B_[j] / np.sqrt(c * (S**2).sum(0))

    t_obs = t_stats(yv[:, None])[0]
    Xr = np.delete(X, j, axis=1)
    br = np.linalg.lstsq(Xr, yv, rcond=None)[0]
    fitted_r, u_r = Xr @ br, yv - Xr @ br
    rng = np.random.default_rng(seed)
    exceed, done = 0, 0
    for chunk in np.array_split(np.arange(draws), max(1, draws // 2000)):
        w = rng.choice([-1.0, 1.0], size=(G, len(chunk)))
        Y = fitted_r[:, None] + u_r[:, None] * w[g]
        exceed += int((np.abs(t_stats(Y)) >= abs(t_obs)).sum())
        done += len(chunk)
    return (exceed + 1) / (done + 1)


# ------------------------------------------------------------- specifications


def did_terms(df: pd.DataFrame, exposure: str = "dist") -> tuple[pd.DataFrame, list[str]]:
    d = df.copy()
    d["exp_x_post2014"] = d[exposure] * (d["year"] >= 2014)
    d["exp_x_post2022"] = d[exposure] * (d["year"] >= 2022)
    return d, ["exp_x_post2014", "exp_x_post2022"]


def event_study(df: pd.DataFrame, y: str = "share_gdp", exposure: str = "dist") -> tuple[pd.DataFrame, dict]:
    """Year-by-year gradients relative to BASE_YEAR, plus a joint pre-trend test."""
    d = df.copy()
    years = sorted(int(t) for t in d["year"].unique() if t != BASE_YEAR)
    terms = []
    for t in years:
        name = f"exp_x_{t}"
        d[name] = d[exposure] * (d["year"] == t)
        terms.append(name)
    f = fit(d, y, terms)
    rows = [{"year": BASE_YEAR, "coef": 0.0, "lo": 0.0, "hi": 0.0, "se": 0.0}]
    for t, name in zip(years, terms):
        lo, hi = f.ci(name)
        rows.append({"year": t, "coef": f.coef[name], "se": f.se[name], "lo": lo, "hi": hi})
    es = pd.DataFrame(rows).sort_values("year", ignore_index=True)
    pre = [i for i, t in enumerate(years) if t < 2014]
    b = np.array([f.coef[terms[i]] for i in pre])
    V = f.vcov_terms[np.ix_(pre, pre)]
    q = len(pre)
    F = float(b @ np.linalg.pinv(V) @ b / q)
    p = float(stats.f.sf(F, q, f.n_clusters - 1))
    return es, {"F": F, "df1": q, "df2": f.n_clusters - 1, "p": p, "n_obs": f.n_obs,
                "n_clusters": f.n_clusters}  # fmt: skip


def did(df: pd.DataFrame, y: str = "share_gdp", exposure: str = "dist",
        extra: list[str] | None = None, draws: int = 9999) -> Fit:  # fmt: skip
    d, terms = did_terms(df, exposure)
    terms = terms + (extra or [])
    f = fit(d, y, terms)
    if draws:
        for t in ("exp_x_post2014", "exp_x_post2022"):
            f.p_boot[t] = wild_cluster_p(d, y, terms, t, draws=draws)
    return f


def placebo(df: pd.DataFrame, fake_year: int = 2009, draws: int = 9999) -> Fit:
    d = df[df["year"] < 2014].copy()
    d["exp_x_fake"] = d["dist"] * (d["year"] >= fake_year)
    f = fit(d, "share_gdp", ["exp_x_fake"])
    if draws:
        f.p_boot["exp_x_fake"] = wild_cluster_p(d, "share_gdp", ["exp_x_fake"], "exp_x_fake", draws)
    return f


def leave_one_out(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for iso in sorted(df["iso3"].unique()):
        f = did(df[df["iso3"] != iso], draws=0)
        rows.append({"dropped": df.loc[df["iso3"] == iso, "country"].iloc[0],
                     "post2014": f.coef["exp_x_post2014"], "post2022": f.coef["exp_x_post2022"]})  # fmt: skip
    return pd.DataFrame(rows)


def robustness(main: pd.DataFrame, with_caucasus: pd.DataFrame, draws: int = 9999) -> pd.DataFrame:
    specs = [
        ("Main: % of GDP, distance to Russia", main, "share_gdp", "dist", None),
        ("Outcome: log real expenditure", main, "log_milex_real", "dist", None),
        ("Including South Caucasus", with_caucasus, "share_gdp", "dist", None),
        ("Exposure: nearest war event", main, "share_gdp", "dist_front", None),
        ("Control: NATO membership", main, "share_gdp", "dist", ["nato"]),
        ("Excluding Baltic states", main[~main["iso3"].isin(BALTICS)], "share_gdp", "dist", None),
    ]
    if "log_gdp_pc" in main:
        specs.append(("Log real exp., GDP per capita control", main, "log_milex_real", "dist", ["log_gdp_pc"]))
    rows = []
    for name, d, y, e, extra in specs:
        f = did(d, y, e, extra, draws)
        rows.append({
            "specification": name, "outcome": y, "exposure": e,
            "post2014": f.coef["exp_x_post2014"], "se_post2014": f.se["exp_x_post2014"],
            "p_boot_post2014": f.p_boot.get("exp_x_post2014"),
            "post2022": f.coef["exp_x_post2022"], "se_post2022": f.se["exp_x_post2022"],
            "p_boot_post2022": f.p_boot.get("exp_x_post2022"),
            "n_obs": f.n_obs, "countries": f.n_clusters,
        })  # fmt: skip
    return pd.DataFrame(rows)


def raw_change(df: pd.DataFrame, y0: int = BASE_YEAR, y1: int = 2025) -> pd.DataFrame:
    """Descriptive: change in % of GDP between two years, by distance (no model)."""
    w = df.pivot_table(index=["iso3", "country", "dist"], columns="year", values="share_gdp")
    out = (w[y1] - w[y0]).rename("change_pp").dropna().reset_index()
    return out.sort_values("dist", ignore_index=True)
