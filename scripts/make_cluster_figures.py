#!/usr/bin/env python3
"""Render the figures for docs/clustering.html from the evidence records (matplotlib, SVG).

    python scripts/make_cluster_figures.py        # needs: pip install matplotlib

Reads docs/data/fault-statistics.json and docs/data/prediction-audit.json (and candidates.json when present) and
writes docs/assets/fig-*.svg.  The figures are committed, so CI and the Pages build do not need matplotlib.
SVG text is stored as text (not paths) and metadata carries no date, so re-running on unchanged JSON is idempotent.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
OUT = os.path.join(ROOT, "docs", "assets")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:                                    # pragma: no cover
    sys.exit("matplotlib is required for figures: pip install matplotlib")

matplotlib.rcParams.update({"svg.fonttype": "none", "svg.hashsalt": "gems", "font.family": "sans-serif", "font.size": 10,
                            "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#52665e",
                            "axes.labelcolor": "#142520", "xtick.color": "#52665e", "ytick.color": "#52665e"})
FOREST, TEAL, AMBER, RED, MUTED, LIME = "#173d32", "#2c7665", "#e2a54b", "#a53c2b", "#52665e", "#d7e9a5"


def j(name):
    with open(os.path.join(DATA, name)) as fh:
        return json.load(fh)


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), format="svg", metadata={"Date": None, "Creator": "gems make_cluster_figures"}, bbox_inches="tight")
    if os.environ.get("FIG_PNG_DIR"):                  # optional raster preview for visual checks
        os.makedirs(os.environ["FIG_PNG_DIR"], exist_ok=True)
        fig.savefig(os.path.join(os.environ["FIG_PNG_DIR"], name.replace(".svg", ".png")), dpi=110, bbox_inches="tight")
    plt.close(fig)
    print("wrote docs/assets/" + name)


def fig_length_nln(st):
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.9))
    c = st["length_ccdf"]
    l, n = np.array(c["l_m"]) / 1000.0, np.array(c["n_ge"], float)
    ax[0].loglog(l, n, "o", ms=3.5, color=FOREST, label="traces (8-connected)")
    ld = st["length_distribution"]["extent"]
    xm = ld["xmin_m"] / 1000.0
    x = np.logspace(np.log10(xm), np.log10(l.max()), 40)
    ax[0].loglog(x, ld["n_tail"] * (x / xm) ** (-ld["a_cumulative"]), "-", color=AMBER, lw=2,
                 label=f"tail fit: a = {ld['a_density']:.2f} (density), {ld['a_cumulative']:.2f} cumulative")
    ax[0].axvline(xm, color=MUTED, lw=.8, ls=":")
    from matplotlib.ticker import FuncFormatter as _FF
    ax[0].xaxis.set_major_formatter(_FF(lambda v, _: f"{v:g}"))
    ax[0].yaxis.set_major_formatter(_FF(lambda v, _: f"{v:g}"))
    ax[0].set_xlabel("trace length (km, maximum Feret diameter)")
    ax[0].set_ylabel("number of traces ≥ length")
    ax[0].set_title("Length distribution of the known catalogue", fontsize=10.5, loc="left")
    ax[0].legend(frameon=False, fontsize=8.5)
    nl = st["nearest_larger"]["centroid"]
    bins = nl["all_lengths"]["bins"]
    lb = np.array([b["l_geomean_m"] for b in bins]) / 1000.0
    db = np.array([b["d_mean_m"] for b in bins]) / 1000.0
    ax[1].loglog(lb, db, "o", color=FOREST, ms=5, label="binned mean distance to nearest larger trace")
    tail = nl["tail_ge_xmin"]
    allf = nl["all_lengths"]
    xs = np.logspace(np.log10(lb.min()), np.log10(lb.max()), 30)
    ax[1].loglog(xs, allf["A_m"] / 1000.0 * (xs * 1000.0) ** allf["x"], "-", color=TEAL, lw=1.6, label=f"all lengths: x = {allf['x']:.2f}")
    xt = np.logspace(np.log10(xm), np.log10(lb.max()), 30)
    ax[1].loglog(xt, tail["A_m"] / 1000.0 * (xt * 1000.0) ** tail["x"], "-", color=AMBER, lw=2.2,
                 label=f"tail ≥ {xm:.1f} km: x = {tail['x']:.2f} [{tail['x_ci95'][0]:.2f}, {tail['x_ci95'][1]:.2f}]")
    bd = st["bour_davy_consistency"]
    from matplotlib.ticker import FixedLocator, FuncFormatter
    ax[1].xaxis.set_major_locator(FixedLocator([0.3, 0.5, 1, 2, 3, 5]))
    ax[1].xaxis.set_minor_locator(FixedLocator([]))
    ax[1].xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[1].yaxis.set_major_locator(FixedLocator([0.5, 1, 2, 5, 10]))
    ax[1].yaxis.set_minor_locator(FixedLocator([]))
    ax[1].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[1].set_xlabel("trace length l (km)")
    ax[1].set_ylabel("⟨d⟩ to nearest larger trace (km)")
    ax[1].set_title(f"Bour & Davy: predicted x = (a−1)/D ∈ [{bd['x_predicted_range'][0]:.2f}, {bd['x_predicted_range'][1]:.2f}]", fontsize=10.5, loc="left")
    ax[1].legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    save(fig, "fig-length-nln.svg")


def fig_ncc(st, pa, cands):
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.9))
    nc = st["ncc"]["centroids_2d"]
    r = np.array(nc["r_edges_m"]) / 1000.0
    ax[0].fill_between(r, nc["sum_lo"], nc["sum_hi"], color=LIME, alpha=.8, label="95 % envelope of complete spatial randomness")
    ax[0].loglog(r, nc["sum_ratio"], "o-", color=FOREST, lw=2, ms=4, label="known catalogue: trace centroids")
    ax[0].axhline(1.0, color=MUTED, lw=.8, ls=":")
    ax[0].set_xlabel("scale r (km)")
    ax[0].set_ylabel("normalised correlation sum  N(≤r) / E[N_CSR(≤r)]")
    ax[0].set_title(f"Faults are clustered at every scale tested\nslope → D = {nc['implied_correlation_dimension_2_plus_slope']:.2f}", fontsize=10.5, loc="left")
    from matplotlib.ticker import FixedLocator, FuncFormatter
    ax[0].yaxis.set_major_locator(FixedLocator([1, 1.5, 2, 3, 4]))
    ax[0].yaxis.set_minor_locator(FixedLocator([]))
    ax[0].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[0].xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[0].legend(frameon=False, fontsize=8.5)
    rr = np.array(pa["method"]["r_m"]) / 1000.0
    ax[1].loglog(rr, pa["reference"]["ncc_sum_ratio"], "o-", color=FOREST, lw=2.2, ms=4, label="known catalogue (pixels)")
    pick = {"h19-5": (TEAL, "h19-5 · live 0.1922"), "h28-dotted-ridge": (AMBER, "h28-dotted-ridge · 0.1839"),
            "f-ensemble-2pct": (RED, "f-ensemble-2pct · 0.0187"), "pindrop-v4-nodes": (MUTED, "pindrop-v4-nodes · 0.1193")}
    for row in pa["artefacts"]:
        if row["id"] in pick and "ncc_sum_ratio" in row:
            col, lab = pick[row["id"]]
            ax[1].loglog(rr, row["ncc_sum_ratio"], "-", color=col, lw=1.4, label=lab)
    for row in pa.get("unscored", []):
        if row["id"].startswith("h24"):
            ax[1].loglog(rr, row["ncc_sum_ratio"], "--", color="black", lw=1.6, label="H24 (unscored)")
    for row in pa.get("unscored", []):
        if "h30" in row["id"] and "ncc_sum_ratio" in row:
            ax[1].loglog(rr, row["ncc_sum_ratio"], "--", color=AMBER, lw=2, label="H30 (unscored)")
    ax[1].axhline(1.0, color=MUTED, lw=.8, ls=":")
    ax[1].set_xlabel("scale r (km)")
    ax[1].yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 30]))
    ax[1].yaxis.set_minor_locator(FixedLocator([]))
    ax[1].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[1].xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax[1].set_title("Arrangement of emitted pixels vs the catalogue", fontsize=10.5, loc="left")
    ax[1].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    save(fig, "fig-ncc.svg")


def fig_arrangement(pa, cands):
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    rows = [r for r in pa["artefacts"] if "signed_large" in r]
    ymax = 0.205
    for lo, hi, name in ((-1.0, -0.55, "lattice-like"), (-0.55, -0.15, "mildly less\nclustered (best bin)"),
                         (-0.15, 0.20, "catalogue-like"), (0.20, 1.45, "over-clustered\n(catalogue-hugging)")):
        best = "best" in name
        ax.axvspan(lo, hi, color=LIME if best else "#eef0e9", alpha=.55 if best else .6, lw=0)
        ax.text((lo + hi) / 2, ymax + 0.004, name, ha="center", va="bottom", fontsize=8, color=MUTED, clip_on=False)
    ax.scatter([r["signed_large"] for r in rows], [r["live_dti"] for r in rows], s=34, color=FOREST, zorder=3)
    lab = {"h19-5": (-40, 5), "h28-dotted-ridge": (7, 3), "f-ensemble-2pct": (-86, 7), "pindrop-v4-nodes": (7, -3),
           "r13-lattice-s5": (7, -3), "ens12-adopted": (7, 3), "pindrop-v4-ridge": (7, 3)}
    for r in rows:
        if r["id"] in lab:
            ax.annotate(r["id"], (r["signed_large"], r["live_dti"]), xytext=lab[r["id"]], textcoords="offset points", fontsize=7.6, color=MUTED)
    marks = []
    if pa.get("unscored"):
        marks.append((pa["unscored"][0]["signed_large"], ["H24"], "black"))
    for c in (cands or {}).get("candidates", []):
        col = AMBER if c["id"] == "h30" else TEAL
        for m in marks:
            if abs(m[0] - c["signed_divergence"]) < 0.04:
                m[1].append(c["id"].upper())
                break
        else:
            marks.append((c["signed_divergence"], [c["id"].upper()], col))
    for x, names, col in marks:
        ax.axvline(x, color=col, lw=1.6, ls="--", zorder=2)
        ax.text(x + 0.012, 0.002, " / ".join(names) + " (unscored)", rotation=90, ha="left", va="bottom", fontsize=8, color=col)
    ax.set_xlim(-1.0, 1.45)
    ax.set_ylim(0, ymax)
    ax.set_xlabel("signed arrangement divergence from the catalogue, mean log(NCC_pred / NCC_cat), 2–30 km")
    ax.set_ylabel("live public DTI")
    ax.set_title("Arrangement orders the live scores (Spearman −0.66, p = 0.001; correlational, post-hoc bins, n = 23)",
                 fontsize=9.6, loc="left", pad=34)
    fig.tight_layout()
    save(fig, "fig-arrangement.svg")


def fig_enrichment(st):
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    en = st["enrichment"]
    for key, col, lab in (("catalogue_short_traces", FOREST, "catalogue's own short traces (< 3 km)"),
                          ("sgmc_not_in_catalogue", AMBER, "SGMC faults missing from the catalogue (independent)")):
        p = en[key]
        e = np.array(p["edges_m"])
        mid = np.sqrt(np.maximum(e[:-1], 100.0) * np.minimum(e[1:], 40000.0))
        E, lo, hi = np.array(p["enrichment"], float), np.array(p["lo"], float), np.array(p["hi"], float)
        ok = np.isfinite(E) & (np.arange(len(E)) >= 1) & (e[1:] < 4e4) & (np.array(p["n_eligible"]) > 5000)
        ax.fill_between(mid[ok] / 1000.0, lo[ok], hi[ok], color=col, alpha=.18, lw=0)
        ax.plot(mid[ok] / 1000.0, E[ok], "o-", color=col, lw=2, ms=4, label=lab)
    ax.axhline(1.0, color=MUTED, lw=.9, ls=":")
    ax.set_xscale("log")
    from matplotlib.ticker import FixedLocator, FuncFormatter
    ax.xaxis.set_major_locator(FixedLocator([0.3, 0.5, 1, 2, 4, 8, 15]))
    ax.xaxis.set_minor_locator(FixedLocator([]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("distance from the nearest known long fault (≥ 3 km), km")
    ax.set_ylabel("enrichment of the target population (1 = no effect)")
    ax.set_title("Clustering around larger faults: strong for known short traces,\nweak and local for faults the catalogue misses", fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=8.8)
    fig.tight_layout()
    save(fig, "fig-enrichment.svg")


def fig_lines(pa):
    fb = pa.get("feature_band_lines")
    if not fb:
        return
    names = list(fb)
    s = np.array([fb[n].get("traverse_400m_along_y", {}).get("strength", np.nan) for n in names])
    p = np.array([fb[n].get("traverse_400m_along_y", {}).get("p_rank", np.nan) for n in names])
    c95 = np.array([fb[n].get("traverse_400m_along_y", {}).get("control_p95", np.nan) for n in names])
    order = np.argsort(-s)
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    y = np.arange(len(names))
    cols = [RED if p[i] <= 0.05 else MUTED for i in order]
    ax.barh(y, s[order], color=cols, height=.7)
    ax.scatter(c95[order], y, marker="|", s=90, color="black", zorder=3, label="95th percentile of control frequencies")
    ax.set_yticks(y)
    ax.set_yticklabels([names[i] for i in order], fontsize=8)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("spectral line strength at the 400 m traverse period (4 px, along y)")
    ax.set_title("The 400 m flight-line spacing is clearly imprinted in tmi_hg only\n(red = rank p ≤ 0.05; 1-2 marginal reds in 19 bands are expected by chance)", fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.tight_layout()
    save(fig, "fig-lines.svg")


def main():
    os.makedirs(OUT, exist_ok=True)
    st, pa = j("fault-statistics.json"), j("prediction-audit.json")
    cands = j("candidates.json") if os.path.exists(os.path.join(DATA, "candidates.json")) else None
    fig_length_nln(st)
    fig_ncc(st, pa, cands)
    fig_arrangement(pa, cands)
    fig_enrichment(st)
    fig_lines(pa)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
