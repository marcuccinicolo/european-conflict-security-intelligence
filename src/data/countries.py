"""Country name harmonisation across sources.

Each source spells countries differently (UCDP uses Gleditsch-Ward names such as
"Russia (Soviet Union)"; SIPRI uses "Russia"; ACLED uses "Russia"). We map every
spelling to an ISO 3166-1 alpha-3 code and a single display name so that the
dashboard can offer one country selector. The mapping is explicit on purpose: an
unknown name is reported, never guessed.
"""

from __future__ import annotations

# ISO3 -> (display name, SIPRI subregion). Historical entities get pseudo-codes.
EUROPE: dict[str, tuple[str, str]] = {
    "ALB": ("Albania", "Central Europe"),
    "BIH": ("Bosnia and Herzegovina", "Central Europe"),
    "BGR": ("Bulgaria", "Central Europe"),
    "HRV": ("Croatia", "Central Europe"),
    "CZE": ("Czechia", "Central Europe"),
    "EST": ("Estonia", "Central Europe"),
    "HUN": ("Hungary", "Central Europe"),
    "XKX": ("Kosovo", "Central Europe"),
    "LVA": ("Latvia", "Central Europe"),
    "LTU": ("Lithuania", "Central Europe"),
    "MKD": ("North Macedonia", "Central Europe"),
    "MNE": ("Montenegro", "Central Europe"),
    "POL": ("Poland", "Central Europe"),
    "ROU": ("Romania", "Central Europe"),
    "SRB": ("Serbia", "Central Europe"),
    "SVK": ("Slovakia", "Central Europe"),
    "SVN": ("Slovenia", "Central Europe"),
    "ARM": ("Armenia", "Eastern Europe"),
    "AZE": ("Azerbaijan", "Eastern Europe"),
    "BLR": ("Belarus", "Eastern Europe"),
    "GEO": ("Georgia", "Eastern Europe"),
    "MDA": ("Moldova", "Eastern Europe"),
    "RUS": ("Russia", "Eastern Europe"),
    "UKR": ("Ukraine", "Eastern Europe"),
    "AUT": ("Austria", "Western Europe"),
    "BEL": ("Belgium", "Western Europe"),
    "CYP": ("Cyprus", "Western Europe"),
    "DNK": ("Denmark", "Western Europe"),
    "FIN": ("Finland", "Western Europe"),
    "FRA": ("France", "Western Europe"),
    "DEU": ("Germany", "Western Europe"),
    "GRC": ("Greece", "Western Europe"),
    "ISL": ("Iceland", "Western Europe"),
    "IRL": ("Ireland", "Western Europe"),
    "ITA": ("Italy", "Western Europe"),
    "LUX": ("Luxembourg", "Western Europe"),
    "MLT": ("Malta", "Western Europe"),
    "NLD": ("Netherlands", "Western Europe"),
    "NOR": ("Norway", "Western Europe"),
    "PRT": ("Portugal", "Western Europe"),
    "ESP": ("Spain", "Western Europe"),
    "SWE": ("Sweden", "Western Europe"),
    "CHE": ("Switzerland", "Western Europe"),
    "GBR": ("United Kingdom", "Western Europe"),
    # Historical entities (SIPRI keeps separate series; no ISO3 exists).
    "XCS": ("Czechoslovakia", "Central Europe"),
    "XDD": ("German Democratic Republic", "Central Europe"),
    "XYU": ("Yugoslavia", "Central Europe"),
    "XSU": ("USSR", "Eastern Europe"),
}

HISTORICAL = {"XCS", "XDD", "XYU", "XSU"}

# Alternative spellings -> ISO3.
ALIASES: dict[str, str] = {
    "Bosnia-Herzegovina": "BIH",
    "Russia (Soviet Union)": "RUS",
    "Serbia (Yugoslavia)": "SRB",
    "Macedonia, FYR": "MKD",
    "Macedonia": "MKD",
    "Czech Republic": "CZE",
    "Moldova, Republic of": "MDA",
    "Republic of Moldova": "MDA",
}

_BY_NAME = {name: iso for iso, (name, _) in EUROPE.items()}


def to_iso3(name: str | None) -> str | None:
    """Map a source country name to ISO3; None if it is not a known European country."""
    if name is None:
        return None
    name = str(name).strip()
    return ALIASES.get(name) or _BY_NAME.get(name)


def display_name(iso3: str | None) -> str | None:
    if iso3 is None:
        return None
    return EUROPE.get(iso3, (iso3, ""))[0]


def subregion(iso3: str | None) -> str | None:
    if iso3 is None or iso3 not in EUROPE:
        return None
    return EUROPE[iso3][1]
