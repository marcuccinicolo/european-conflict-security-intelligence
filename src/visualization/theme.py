"""Chart palette and Plotly template.

Categorical slots follow a CVD-validated fixed order. Colours are assigned to
*entities* (an event type, a country) through ``color_map`` so a filter never
repaints the survivors. More than eight series fold into "Other".
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#898781"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
DIVERGING = {"neg": "#e34948", "mid": "#f0efec", "pos": "#2a78d6"}
FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

# Stable colours for known categories (both sources), assigned once.
FIXED = {
    # UCDP
    "State-based conflict": SERIES[0],
    "Non-state conflict": SERIES[1],
    "One-sided violence": SERIES[2],
    # ACLED
    "Battles": SERIES[0],
    "Explosions/Remote violence": SERIES[1],
    "Violence against civilians": SERIES[2],
    "Protests": SERIES[3],
    "Riots": SERIES[4],
    "Strategic developments": SERIES[6],
}


def color_map(names: list[str]) -> dict[str, str]:
    """Colour per entity: fixed for known categories, else stable order of first sight."""
    out, free = {}, [c for c in SERIES]
    for n in names:
        if n in FIXED:
            out[n] = FIXED[n]
    used = set(out.values())
    free = [c for c in SERIES if c not in used]
    for n in sorted(set(names) - set(out)):
        out[n] = free.pop(0) if free else OTHER
    out["Other"] = OTHER
    return out


def assign_stable(registry: dict[str, str], names: list[str]) -> dict[str, str]:
    """Update a persistent name->colour registry: survivors keep their colour,
    removed names free their slot, new names take the first free slot."""
    for n in [k for k in registry if k not in names]:
        del registry[n]
    for n in names:
        if n not in registry:
            free = [c for c in SERIES if c not in registry.values()]
            registry[n] = free[0] if free else OTHER
    return registry


def _template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, size=13, color=INK),
        title=dict(font=dict(size=15, color=INK), x=0, xanchor="left", y=0.97),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=SERIES,
        margin=dict(l=8, r=16, t=48, b=8),
        hoverlabel=dict(bgcolor="white", bordercolor=AXIS, font=dict(family=FONT, color=INK)),
        xaxis=dict(showgrid=False, linecolor=AXIS, ticks="outside", tickcolor=AXIS,
                   tickfont=dict(color=INK_2), title=dict(font=dict(color=INK_2))),  # fmt: skip
        yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=AXIS, tickfont=dict(color=INK_2),
                   title=dict(font=dict(color=INK_2))),  # fmt: skip
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(color=INK_2), title=None),
        hovermode="x unified",
    )
    return t


pio.templates["ecsi"] = _template()
TEMPLATE = "plotly_white+ecsi"
