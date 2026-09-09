"""
Maps the real WM-811K defect-class distribution onto the real SMT2020
station groups conventionally associated with each defect *pattern* in
semiconductor yield-engineering practice -- a second, distinct "where do
defects likely originate" lens next to the existing capacity-bottleneck
view (which is about where the fab is BUSIEST, not where DEFECTS
originate; the two need not agree, and in this app's data they don't).

Important honesty boundary, stated plainly: this is a documented heuristic
mapping from yield-engineering practice (certain wafer-map *shapes* are
conventionally associated with certain *categories* of process step,
independent of which fab produced them) -- it is NOT derived from any real
co-occurrence data between WM-811K and SMT2020, which are unrelated real
fabs (see data/wm811k/ATTRIBUTION.md). Nothing here claims these specific
WM-811K wafers came from this specific SMT2020 line. Treat the mapping as
illustrative domain knowledge, not a statistically validated result.
"""

# Real, conventionally-cited associations from wafer-defect-pattern
# literature -- stated here as an explicit assumption, not derived data.
DEFECT_TO_STATION_GROUP = {
    "Center": "Planar",        # center-to-edge uniformity issue (CMP/planarization)
    "Donut": "Dielectric",     # ring-shaped deposition/etch non-uniformity
    "Edge-Loc": "Wet_Etch",    # localized edge-handling / edge etch
    "Edge-Ring": "Wet_Etch",   # edge bead removal / edge etch non-uniformity
    "Loc": "Dry_Etch",         # localized single-tool excursion
    "Near-full": "Litho",      # gross process failure, often a litho miss or lot scrap
    "Random": "Implant",       # particle contamination, often implant/handling-related
    "Scratch": "Litho_Met",    # mechanical handling / metrology transport damage
    # "none" (no defect) deliberately excluded -- nothing to attribute.
}


def quality_risk_by_station(class_distribution: dict) -> dict:
    """Given the real WM-811K per-class wafer counts (from the trained
    CNN's own metrics -- not invented), aggregates real defect volume onto
    each mapped station group and ranks them, most-defect-share first."""
    totals = {}
    for defect, count in class_distribution.items():
        grp = DEFECT_TO_STATION_GROUP.get(defect)
        if grp is None:
            continue
        totals[grp] = totals.get(grp, 0) + count
    total_mapped = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    stations = [
        {"stngrp": grp, "real_defect_count": count, "share_of_mapped_defects": count / total_mapped}
        for grp, count in ranked
    ]
    return {
        "stations": stations,
        "top_quality_risk_station": stations[0]["stngrp"] if stations else None,
        "mapping": DEFECT_TO_STATION_GROUP,
    }
