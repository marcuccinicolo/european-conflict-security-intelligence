"""Download raw files from documented official endpoints and record provenance.

Every downloaded file gets a sidecar ``<file>.provenance.json`` with the URL,
UTC download time, size and SHA-256, so the dataset registry can state exactly
which file a figure came from. Nothing is scraped: only the documented download
links (UCDP, SIPRI, Natural Earth) and ACLED's documented OAuth API are used.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from src.config import BOUNDARIES_ZIP, SOURCES, acled_credentials
from src.data.countries import EUROPE, HISTORICAL

NATURAL_EARTH_URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip"
USER_AGENT = "european-conflict-security-intelligence/1.0 (research portfolio project)"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_provenance(path: Path, url: str, method: str = "download") -> dict:
    meta = {
        "file": path.name,
        "url": url,
        "method": method,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    Path(f"{path}.provenance.json").write_text(json.dumps(meta, indent=2))
    return meta


def read_provenance(path: Path) -> dict:
    """Provenance for a raw file; falls back to file metadata for manual placements."""
    side = Path(f"{path}.provenance.json")
    if side.exists():
        return json.loads(side.read_text())
    st = Path(path).stat()
    return {
        "file": Path(path).name,
        "url": None,
        "method": "manual placement (no provenance sidecar)",
        "retrieved_at_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(
            timespec="seconds"
        ),
        "bytes": st.st_size,
        "sha256": sha256(path),
    }


def download(url: str, dest: Path, force: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  exists, skipping: {dest.relative_to(dest.parents[2])}")
        return dest
    print(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.replace(dest)
    write_provenance(dest, url)
    return dest


def fetch_ucdp(force: bool = False) -> Path:
    spec = SOURCES["ucdp_ged"]
    return download(spec.download_url, spec.raw_dir / Path(spec.download_url).name, force)


def fetch_sipri(force: bool = False) -> Path:
    spec = SOURCES["sipri_milex"]
    return download(spec.download_url, spec.raw_dir / Path(spec.download_url).name, force)


def fetch_boundaries(force: bool = False) -> Path:
    return download(NATURAL_EARTH_URL, BOUNDARIES_ZIP, force)


# ---------------------------------------------------------------- ACLED (optional)

ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_READ_URL = "https://acleddata.com/api/acled/read"
# ACLED spellings that differ from our display names.
_ACLED_NAMES = {"Czechia": "Czech Republic"}


def acled_country_names() -> list[str]:
    return [_ACLED_NAMES.get(n, n) for iso, (n, _) in EUROPE.items() if iso not in HISTORICAL]


def acled_token(username: str, password: str, session: requests.Session) -> str:
    r = session.post(
        ACLED_TOKEN_URL,
        data={
            "username": username,
            "password": password,
            "grant_type": "password",
            "client_id": "acled",
            "scope": "authenticated",
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_acled(
    start: str = "2018-01-01",
    end: str | None = None,
    page_size: int = 5000,
    session: requests.Session | None = None,
) -> Path:
    """Fetch European ACLED events through the documented API.

    Requires ACLED_USERNAME and ACLED_PASSWORD in the environment (or .env).
    The output lands in data/raw/acled/, which is git-ignored because ACLED's
    licence forbids redistribution.
    """
    creds = acled_credentials()
    if creds is None:
        raise RuntimeError(
            "ACLED credentials not set. Copy .env.example to .env and fill in "
            "ACLED_USERNAME / ACLED_PASSWORD (myACLED account), or export a CSV "
            "from https://acleddata.com and place it in data/raw/acled/."
        )
    session = session or requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    token = acled_token(*creds, session)
    headers = {"Authorization": f"Bearer {token}"}
    end = end or datetime.now(timezone.utc).date().isoformat()
    frames, page = [], 1
    while True:
        params = {
            "_format": "json",
            "country": ":OR:".join(acled_country_names()),
            "event_date": f"{start}|{end}",
            "event_date_where": "BETWEEN",
            "limit": page_size,
            "page": page,
        }
        r = session.get(ACLED_READ_URL, params=params, headers=headers, timeout=120)
        r.raise_for_status()
        rows = r.json().get("data", [])
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        print(f"  page {page}: {len(rows)} rows")
        if len(rows) < page_size:
            break
        page += 1
        time.sleep(1)  # be polite to the API
    if not frames:
        raise RuntimeError("ACLED API returned no rows for the requested period.")
    out_dir = SOURCES["acled"].raw_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"acled_europe_{start}_{end}.csv"
    pd.concat(frames, ignore_index=True).to_csv(dest, index=False)
    write_provenance(dest, ACLED_READ_URL, method=f"ACLED API, {start} to {end}")
    return dest
