"""Central paths and source definitions.

Everything that describes *where* data comes from lives here, so the pipeline,
the dashboard and the documentation all read the same facts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "sample"
PUBLIC_DIR = DATA_DIR / "public"  # committed derived data whose licence permits it
REPORTS_DIR = ROOT / "reports"
QUALITY_DIR = REPORTS_DIR / "data_quality"
FIGURES_DIR = REPORTS_DIR / "figures"

DB_PATH = Path(os.getenv("ECSI_DB_PATH", PROCESSED_DIR / "security.duckdb"))

# Sample (synthetic) files shipped with the repository.
SYNTHETIC_EVENTS_CSV = SAMPLE_DIR / "SYNTHETIC_demo_events_acled_format.csv"
SYNTHETIC_MILEX_CSV = SAMPLE_DIR / "SYNTHETIC_demo_milex.csv"

# Validated European UCDP subset (CC BY 4.0), committed so deployments start with real data.
UCDP_PUBLIC_PARQUET = PUBLIC_DIR / "ucdp_ged_europe.parquet"
UCDP_PUBLIC_META = PUBLIC_DIR / "ucdp_ged_europe.meta.json"
CANDIDATE_PUBLIC_PARQUET = PUBLIC_DIR / "ucdp_candidate_europe.parquet"
CANDIDATE_PUBLIC_META = PUBLIC_DIR / "ucdp_candidate_europe.meta.json"
EXPOSURE_PUBLIC_CSV = PUBLIC_DIR / "exposure.csv"
WDI_PUBLIC_CSV = PUBLIC_DIR / "wdi_gdp_per_capita.csv"
RESEARCH_DIR = REPORTS_DIR / "research"

# Natural Earth admin-0 boundaries (public domain) used for coordinate checks.
BOUNDARIES_ZIP = RAW_DIR / "naturalearth" / "ne_50m_admin_0_countries.zip"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    publisher: str
    url: str
    licence: str
    licence_url: str
    citation: str
    raw_dir: Path
    download_url: str | None = None
    redistribution: str = ""
    notes: list[str] = field(default_factory=list)


SOURCES: dict[str, SourceSpec] = {
    "ucdp_ged": SourceSpec(
        key="ucdp_ged",
        name="UCDP Georeferenced Event Dataset (GED) Global v26.1",
        publisher="Uppsala Conflict Data Program, Uppsala University",
        url="https://ucdp.uu.se/downloads/",
        download_url="https://ucdp.uu.se/downloads/ged/ged261-csv.zip",
        licence="CC BY 4.0",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        citation=(
            "Davies, Shawn, Therése Pettersson & Magnus Öberg (2026). Organized violence "
            "1989-2025. Journal of Peace Research; Sundberg, Ralph & Erik Melander (2013). "
            "Introducing the UCDP Georeferenced Event Dataset. Journal of Peace Research 50(4)."
        ),
        raw_dir=RAW_DIR / "ucdp",
        redistribution="Redistribution and derived works permitted with attribution (CC BY 4.0).",
        notes=[
            "Only events within conflicts/dyads that cross the UCDP threshold of 25 "
            "battle-related deaths in a calendar year are included; every event has "
            "at least one estimated death.",
            "Fatalities are estimates (best / low / high), not exact counts.",
        ],
    ),
    "ucdp_candidate": SourceSpec(
        key="ucdp_candidate",
        name="UCDP Candidate Events (provisional monthly releases)",
        publisher="Uppsala Conflict Data Program, Uppsala University",
        url="https://ucdp.uu.se/downloads/",
        download_url="https://ucdp.uu.se/downloads/candidateged/",
        licence="CC BY 4.0",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        citation=(
            "Hegre, Håvard, Mihai Croicu, Kristine Eck & Stina Högbladh (2020). Introducing the UCDP "
            "Candidate Events Dataset. Research & Politics; Högbladh, Stina (2026). UCDP Candidate "
            "Events Dataset Codebook v1.5."
        ),
        raw_dir=RAW_DIR / "ucdp_candidate",
        redistribution="Redistribution and derived works permitted with attribution (CC BY 4.0).",
        notes=[
            "PROVISIONAL. Candidate events relax the 25-death annual threshold and are revised, added or "
            "removed in the next annual GED. Counts are not comparable with UCDP GED.",
            "code_status flags events with higher uncertainty (Check deaths, Check dyad, ...).",
        ],
    ),
    "acled": SourceSpec(
        key="acled",
        name="ACLED - Armed Conflict Location & Event Data",
        publisher="ACLED",
        url="https://acleddata.com/",
        download_url="https://acleddata.com/api/acled/read",
        licence="ACLED End User License Agreement (non-commercial, registration required)",
        licence_url="https://acleddata.com/eula",
        citation="Armed Conflict Location & Event Data (ACLED); see https://acleddata.com/attributionpolicy",
        raw_dir=RAW_DIR / "acled",
        redistribution=(
            "Raw ACLED data must NOT be redistributed or committed to a public repository. "
            "This project never commits ACLED files and disables row-level export for ACLED."
        ),
        notes=["Requires a myACLED account. Credentials are read from environment variables only."],
    ),
    "sipri_milex": SourceSpec(
        key="sipri_milex",
        name="SIPRI Military Expenditure Database 1949-2025 (v1.2)",
        publisher="Stockholm International Peace Research Institute (SIPRI)",
        url="https://www.sipri.org/databases/milex",
        download_url="https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx",
        licence="SIPRI Terms and Conditions (free non-commercial use with attribution)",
        licence_url="https://www.sipri.org/about/terms-and-conditions",
        citation=(
            "Information from the Stockholm International Peace Research Institute (SIPRI), "
            "Military Expenditure Database, https://www.sipri.org/databases/milex, "
            "doi:10.55163/CQGC9685"
        ),
        raw_dir=RAW_DIR / "sipri",
        redistribution=(
            "Reproducing more than 10% of a SIPRI dataset requires permission. The workbook "
            "and its derivatives are not committed, and the dashboard does not offer SIPRI exports."
        ),
        notes=[
            "Blue figures in the workbook are SIPRI estimates; red figures are highly uncertain. "
            "These flags are preserved from cell font colours.",
        ],
    ),
    "synthetic_events": SourceSpec(
        key="synthetic_events",
        name="SYNTHETIC demonstration events (ACLED-style layout)",
        publisher="This project (scripts/generate_synthetic_data.py)",
        url="",
        licence="Project licence (MIT)",
        licence_url="",
        citation="Synthetic - not real-world observations.",
        raw_dir=SAMPLE_DIR,
        redistribution="Freely redistributable; contains no real observations.",
        notes=["Generated with a fixed random seed. Contains deliberately injected data-quality defects."],
    ),
    "synthetic_milex": SourceSpec(
        key="synthetic_milex",
        name="SYNTHETIC demonstration military expenditure series",
        publisher="This project (scripts/generate_synthetic_data.py)",
        url="",
        licence="Project licence (MIT)",
        licence_url="",
        citation="Synthetic - not real-world observations.",
        raw_dir=SAMPLE_DIR,
        redistribution="Freely redistributable; contains no real observations.",
        notes=["Random-walk series with a fixed seed. Values are not SIPRI figures."],
    ),
    "world_bank_wdi": SourceSpec(
        key="world_bank_wdi",
        name="World Bank WDI: GDP per capita, constant 2015 US$ (NY.GDP.PCAP.KD)",
        publisher="World Bank",
        url="https://data.worldbank.org/indicator/NY.GDP.PCAP.KD",
        download_url="https://api.worldbank.org/v2/country/{codes}/indicator/NY.GDP.PCAP.KD",
        licence="CC BY 4.0",
        licence_url="https://datacatalog.worldbank.org/public-licenses",
        citation="World Bank, World Development Indicators, NY.GDP.PCAP.KD.",
        raw_dir=RAW_DIR / "worldbank",
        redistribution="Redistribution permitted with attribution (CC BY 4.0).",
        notes=["Used only as a robustness control in the proximity analysis."],
    ),
    "exposure": SourceSpec(
        key="exposure",
        name="Capital-city exposure distances and NATO accession (derived)",
        publisher="This project, from Natural Earth (public domain), UCDP GED (CC BY 4.0) and nato.int",
        url="https://www.naturalearthdata.com",
        licence="Derived from public-domain and CC BY 4.0 data",
        licence_url="",
        citation="Natural Earth 1:50m admin-0 and populated places; UCDP GED v26.1; NATO member countries.",
        raw_dir=RAW_DIR / "naturalearth_places",
        redistribution="Freely redistributable with attribution to UCDP.",
        notes=["Distance to Russia excludes Crimea (internationally recognised borders).",
               "Distances are planar in EPSG:3035, from the capital city."],
    ),
}

# Sources whose row-level data may be exported from the dashboard.
EXPORTABLE_SOURCES = {"ucdp_ged", "ucdp_candidate", "synthetic_events", "synthetic_milex", "world_bank_wdi", "exposure"}


def acled_credentials() -> tuple[str, str] | None:
    """Return ACLED credentials from the environment, or None if unset."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:  # pragma: no cover - python-dotenv is in requirements
        pass
    user, pwd = os.getenv("ACLED_USERNAME"), os.getenv("ACLED_PASSWORD")
    if user and pwd:
        return user, pwd
    return None
