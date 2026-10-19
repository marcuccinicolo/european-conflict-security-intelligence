"""Run the pre-specified proximity analysis (docs/RESEARCH_DESIGN.md) end to end.

Used by both the dashboard's Research page and the report, so they show the same
numbers. Results are also written to reports/research/proximity_results.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from src.analysis import proximity as P
from src.analysis import synthetic_control as SC
from src.config import RESEARCH_DIR
from src.database import queries as Q


def available(con) -> bool:
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    return {"exposure", "milex"} <= tables and "sipri_milex" in Q.milex_sources(con)


def load_inputs(con) -> dict:
    gdp = Q.milex(con, "sipri_milex", "share_gdp_pct")
    real = Q.milex(con, "sipri_milex", "milex_constant_usd_m")
    ex = con.execute("SELECT * FROM exposure").df()
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    wdi = con.execute("SELECT * FROM macro").df() if "macro" in tables else None
    return {"gdp": gdp, "real": real, "exposure": ex, "wdi": wdi}


def run(con, draws: int = 9999) -> dict:
    i = load_inputs(con)
    main = P.build_panel(i["gdp"], i["real"], i["exposure"], i["wdi"])
    cauc = P.build_panel(i["gdp"], i["real"], i["exposure"], i["wdi"], include_caucasus=True)
    es, pretrend = P.event_study(main)
    es_real, pretrend_real = P.event_study(main, y="log_milex_real")
    m = P.did(main, draws=draws)
    rob = P.robustness(main, cauc, draws=draws)
    extra = []
    for name, d in [("Excluding SIPRI-estimated country-years", P.drop_estimated_years(main)),
                    ("Excluding countries with any SIPRI estimate", P.drop_estimated_countries(main))]:  # fmt: skip
        f = P.did(d, draws=draws)
        extra.append({"specification": name, "outcome": "share_gdp", "exposure": "dist",
                      "post2014": f.coef["exp_x_post2014"], "se_post2014": f.se["exp_x_post2014"],
                      "p_boot_post2014": f.p_boot["exp_x_post2014"],
                      "post2022": f.coef["exp_x_post2022"], "se_post2022": f.se["exp_x_post2022"],
                      "p_boot_post2022": f.p_boot["exp_x_post2022"],
                      "n_obs": f.n_obs, "countries": f.n_clusters})  # fmt: skip
    rob = pd.concat([rob, pd.DataFrame(extra)], ignore_index=True)
    perm = P.permutation_test(main, draws=draws)
    synth = SC.run(main)
    loo = P.leave_one_out(main)
    plc = P.placebo(main, draws=draws)
    raw = P.raw_change(main)
    ex = i["exposure"]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "draws": draws,
        "sample": {
            "countries": m.countries, "n_countries": m.n_clusters, "n_obs": m.n_obs,
            "years": list(P.YEARS),
            "excluded": {ex.set_index("iso3").loc[k, "country"]: v for k, v in P.EXCLUDED.items()},
            "caucasus_excluded_in_main": sorted(ex.set_index("iso3").loc[list(P.CAUCASUS), "country"]),
        },  # fmt: skip
        "main": {
            "post2014": m.coef["exp_x_post2014"], "se_post2014": m.se["exp_x_post2014"],
            "ci_post2014": m.ci("exp_x_post2014"), "p_boot_post2014": m.p_boot["exp_x_post2014"],
            "p_cluster_post2014": m.p_cluster("exp_x_post2014"),
            "post2022": m.coef["exp_x_post2022"], "se_post2022": m.se["exp_x_post2022"],
            "ci_post2022": m.ci("exp_x_post2022"), "p_boot_post2022": m.p_boot["exp_x_post2022"],
            "p_cluster_post2022": m.p_cluster("exp_x_post2022"),
        },  # fmt: skip
        "pretrend": pretrend,
        "pretrend_log_real": pretrend_real,
        "event_study": es.to_dict("records"),
        "event_study_log_real": es_real.to_dict("records"),
        "robustness": rob.to_dict("records"),
        "leave_one_out": {
            "post2014_min": float(loo["post2014"].min()), "post2014_max": float(loo["post2014"].max()),
            "post2022_min": float(loo["post2022"].min()), "post2022_max": float(loo["post2022"].max()),
            "most_influential_2022": loo.loc[(loo["post2022"] - m.coef["exp_x_post2022"]).abs().idxmax(), "dropped"],
            "rows": loo.to_dict("records"),
        },  # fmt: skip
        "placebo_2009": {"coef": plc.coef["exp_x_fake"], "se": plc.se["exp_x_fake"],
                         "p_boot": plc.p_boot["exp_x_fake"]},  # fmt: skip
        "raw_change_2013_2025": raw.to_dict("records"),
        "permutation": perm,
        "synthetic_control": synth,
    }


def save(results: dict) -> str:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    path = RESEARCH_DIR / "proximity_results.json"
    path.write_text(json.dumps(results, indent=2, default=float))
    return str(path)


def as_frames(results: dict) -> dict[str, pd.DataFrame]:
    return {
        "event_study": pd.DataFrame(results["event_study"]),
        "event_study_log_real": pd.DataFrame(results["event_study_log_real"]),
        "robustness": pd.DataFrame(results["robustness"]),
        "loo": pd.DataFrame(results["leave_one_out"]["rows"]),
        "raw": pd.DataFrame(results["raw_change_2013_2025"]),
    }
