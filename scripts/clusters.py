"""Shared content-cluster taxonomy for towwiththeflow.com.

Each cluster is (slug, label, [substring patterns matched against a
lowercased keyword/title]). First match wins, so more specific patterns
should come before broader ones. Falls back to a general catch-all cluster
for anything that doesn't match — expected to be a small minority.

Used by: assign_clusters.py (backfills the `cluster:` frontmatter field on
existing posts), generate_post.py (assigns it to new posts), and
build_seo_data.py (rolls cluster stats into the SEO dashboard).
"""

from __future__ import annotations

CLUSTERS: list[tuple[str, str, list[str]]] = [
    ("towing-cost", "Towing Cost & Pricing", [
        "towing cost", "tow truck cost", "tow truck price", "towing price",
        "towing rate", "tow cost", "cost per mile", "per mile", "price to tow",
        "how much does a tow", "how much is a tow", "how much does towing",
        "extra cost", "what it costs", "what you'll pay", "what you'll actually pay",
    ]),
    ("insurance-coverage", "Insurance & Roadside Coverage", [
        "insurance", "aaa", "state farm", "allstate", "geico", "progressive",
        "farmers", "liberty mutual", "deductible", "reimbursement",
        "membership", "roadside assistance", "roadside coverage",
    ]),
    ("battery-starting", "Battery & Starting Problems", [
        "battery", "wont start", "won't start", "will not start", "jump start",
        "clicking", "alternator", "dead car", "car won't turn over",
        "car wont turn over", "ignition", "key broke", "click but not start",
        "died at a red light", "died at red light", "dies immediately",
        "died while driving",
    ]),
    ("engine-mechanical", "Engine & Mechanical Breakdown", [
        "engine", "overheat", "stall", "smoke", "smoking", "grinding",
        "transmission", "axle", "fuel pump", "oil pressure", "oil light",
        "run out of oil", "coolant", "radiator", "check engine", "knocking",
        "brake", "shakes", "shaking", "leaking fluid", "fluid leak",
        "wont shift", "won't shift", "gas pedal", "pedal stuck",
        "ran out of gas", "out of gas",
    ]),
    ("tire-wheel", "Tire & Wheel Issues", [
        "tire", "blowout", "wheel", "flat",
    ]),
    ("accident-liability", "Accidents & Towing Liability", [
        "accident", "who pays", "damage", "liability", "police", "totaled",
        "crash", "airbag",
    ]),
    ("highway-safety", "Highway & Freeway Safety", [
        "highway", "freeway", "interstate", "shoulder", "hazard", "bridge",
        "night", "safety",
    ]),
    ("winter-weather", "Winter & Weather Breakdowns", [
        "snow", "winter", "cold weather", "frozen", "ice", "blizzard",
    ]),
    ("towing-logistics", "Towing Logistics & Process", [
        "long distance", "flatbed", "wheel-lift", "wheel lift", "impound",
        "storage fee", "response time", "how long does a tow", "miles away",
        "locked out", "locked keys", "keys locked", "credit card",
        "illegal to leave", "sit broken down", "near me",
        "what to keep in your car", "emergency kit",
    ]),
]

CATCHALL: tuple[str, str] = ("roadside-help", "General Roadside Help")


def assign_cluster(text: str) -> tuple[str, str]:
    """Return (cluster_slug, cluster_label) for a keyword or post title."""
    t = text.lower()
    for slug, label, patterns in CLUSTERS:
        if any(p in t for p in patterns):
            return slug, label
    return CATCHALL


def cluster_label(slug: str) -> str:
    for cluster_slug, label, _patterns in CLUSTERS:
        if cluster_slug == slug:
            return label
    return CATCHALL[1]
