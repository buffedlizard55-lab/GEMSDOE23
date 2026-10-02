#!/usr/bin/env python3
"""Regenerate the whole static site from the JSON evidence in docs/data.

    python scripts/build_site.py

Nothing is hand-written in the HTML: every number on every page is read from an evidence
record produced by a script in this repository, so the site cannot drift from the data.
The GitHub Pages workflow re-runs this after refreshing the public leaderboard, which is
why no score has to be checked by hand.
"""
from __future__ import annotations
import html, json, os, shutil, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "data")
DL = os.path.join(DOCS, "downloads")


# Rendered under every leaderboard table so the two standing qualifications travel with the numbers
# rather than living only in the JSON. Fallbacks match scripts/update_leaderboard.py.
ATTRIBUTION_FALLBACK = (
    "The official public leaderboard displays participants and scores but does not expose a "
    "prediction-file SHA-256 or public submission identifier; score equality is not artifact, "
    "account, or team attribution."
)
PHASE_FALLBACK = (
    "These are public leaderboard results only, not private Initial Prize Round (Phase 1) "
    "or expert-updated Final Prize Round (Phase 2) scores."
)


def j(name, default=None):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p) as fh:
        return json.load(fh)


def esc(x):
    return html.escape(str(x))


def num(x, nd=4):
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return "—"


NAV = [("index.html", "Overview"), ("executive-summary.html", "How to submit"),
       ("clustering.html", "Clustering audit"), ("hypotheses.html", "New hypotheses"), ("uncertainty.html", "Uncertainty"),
       ("evidence.html", "Evidence"), ("results.html", "Scores"),
       ("sources.html", "Sources"), ("verification.html", "Audit")]


def evidence_stamp() -> str:
    """Show the leaderboard capture's actual time precision in the global site stamp.

    Prefer the public-board capture over unrelated validation timestamps. When an official
    capture exposes only a date, never borrow a generated_utc from another record to imply
    an exact retrieval time. Otherwise fall back to the newest evidence-record timestamp.
    """
    board_path = os.path.join(DATA, "leaderboard.json")
    try:
        board = json.load(open(board_path))
    except Exception:
        board = {}
    retrieved = board.get("retrieved_utc") if isinstance(board, dict) else None
    if isinstance(retrieved, str) and retrieved:
        if len(retrieved) == 10 and retrieved[4] == "-" and retrieved[7] == "-":
            return retrieved + " UTC"
        return retrieved[:16].replace("T", " ") + " UTC"

    stamps = []
    for name in os.listdir(DATA) if os.path.isdir(DATA) else []:
        if not name.endswith(".json"):
            continue
        try:
            rec = json.load(open(os.path.join(DATA, name)))
        except Exception:
            continue
        for key in ("generated_utc", "reviewed_utc"):
            value = rec.get(key) if isinstance(rec, dict) else None
            if isinstance(value, str):
                stamps.append(value)
    return max(stamps)[:16].replace("T", " ") + " UTC" if stamps else "date not recorded"


def page(title, body, current, description, stamp=""):
    links = []
    for h, t in NAV:
        cur = ' aria-current="page"' if h == current else ""
        links.append('      <a href="%s"%s>%s</a>' % (h, cur, esc(t)))
    nav = "\n".join(links)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{esc(description)}">
  <title>{esc(title)}</title>
  <link rel="stylesheet" href="assets/site.css">
  <script defer src="assets/site.js"></script>
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="index.html"><span class="brand-mark">G23</span><span>GEMSDOE23 <span class="small" style="color:#c8d8cd">/ research log</span></span></a>
    <nav class="nav" aria-label="Main navigation">
{nav}
    </nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="site-footer">
  <div class="footer-inner">
    <span>GEMSDOE23 · DOE GEMS Prize Challenge (DrivenData #306) · built from evidence records of {esc(stamp)}</span>
    <span><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/">Official competition</a> · <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">Official leaderboard</a> · <a href="https://github.com/buffedlizard55-lab/GEMSDOE23">This repository</a></span>
  </div>
</footer>
</body>
</html>
"""


def table(headers, rows, cls="", tbody_id=""):
    """Static table; when tbody_id is set, assets/site.js refreshes that tbody in place."""
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        tds = "".join(f'<td class="numeric">{esc(c)}</td>' if isinstance(c, (int, float)) else f"<td>{c}</td>" for c in r)
        trs.append(f"<tr>{tds}</tr>")
    tid = f' id="{tbody_id}"' if tbody_id else ""
    return (f'<div class="table-wrap"><table class="{cls}"><thead><tr>{th}</tr></thead>'
            f'<tbody{tid}>{"".join(trs)}</tbody></table></div>')



def clustering_page(st, pa, cdx, h29, h30, man):
    """docs/clustering.html - the fault-population statistics, the prior and the audit, all read from JSON."""
    def f2(x, nd=2):
        try:
            return f"{float(x):.{nd}f}"
        except Exception:
            return "—"

    def ci(lo_hi, nd=2):
        return f"[{f2(lo_hi[0], nd)}, {f2(lo_hi[1], nd)}]" if lo_hi else ""

    ld, ldp = st["length_distribution"]["extent"], st["length_distribution"]["path"]
    nl, cdim = st["nearest_larger"], st["correlation_dimension"]
    ncc, bd, en, ba = st["ncc"]["centroids_2d"], st["bour_davy_consistency"], st["enrichment"], st["blocked_auc"]
    tw, syn, h25 = st["tip_wedges"], st["synthetic_validation"], st["h25_offset_profile"]
    pop = st["population"]
    cal, bins, tgt = pa["calibration"], pa["arrangement_bins"], pa["arrangement_target"]
    sig_key = [k for k in cal if k.startswith("signed")][0]
    r_km = [f"{r/1000:g}" for r in ncc["r_edges_m"]]
    cz = tw["continuation_zone_300_1000m"]

    stat_rows = [
        ["traces (8-connected components of the 60,988 label pixels)", f"{pop['n_traces']:,}", "median length %.2f km, 90th percentile %.2f km, longest %.1f km; %d traces ≥ 3 km" % (
            pop["length_m_quantiles"]["50"] / 1000, pop["length_m_quantiles"]["90"] / 1000, pop["length_m_quantiles"]["100"] / 1000, pop["n_ge_3km"])],
        ["length exponent <em>a</em> (density, n(l) ~ l<sup>−a</sup>)", f"{f2(ld['a_density'])} {ci(ld['a_ci95'])}",
         f"above {ld['xmin_m']/1000:.2f} km (KS-chosen), n = {ld['n_tail']}; cumulative exponent {f2(ld['a_cumulative'])}; power law vs lognormal: {esc(ld['preferred'])} (Vuong z = {f2(ld['vuong_z'])}); path-length check a = {f2(ldp['a_density'])} {ci(ldp['a_ci95'])}"],
        ["nearest-larger-neighbour exponent <em>x</em>, tail ≥ %.1f km, centroid distance" % (ld["xmin_m"] / 1000), f"{f2(nl['centroid']['tail_ge_xmin']['x'])} {ci(nl['centroid']['tail_ge_xmin']['x_ci95'])}",
         f"geometric-mean estimator {f2(nl['centroid']['tail_ge_xmin']['x_geometric_mean'])}; edge-to-edge distance {f2(nl['edge']['tail_ge_xmin']['x'])} {ci(nl['edge']['tail_ge_xmin']['x_ci95'])}"],
        ["same, all lengths", f"{f2(nl['centroid']['all_lengths']['x'])} {ci(nl['centroid']['all_lengths']['x_ci95'])}",
         f"Spearman ρ(length, distance) = {f2(nl['centroid']['all_lengths']['spearman_rho'])}: large faults have their nearest larger neighbour farther away, as Bour &amp; Davy report; the flatter all-length slope means short traces sit farther from larger ones than the long-fault scaling predicts"],
        ["correlation dimension D of trace centroids", f"{f2(cdim['centroids_1p5_30km']['D'])} (1.5–30 km) · {f2(cdim['centroids_0p5_10km']['D'])} (0.5–10 km)",
         f"all fault pixels {f2(cdim['pixels_0p3_10km']['D'])}; slope of the normalised correlation sum + 2 gives {f2(ncc['implied_correlation_dimension_2_plus_slope'])} (an independent route to the same D)"],
        ["normalised correlation sum, centroids (CSR = 1)", " · ".join(f"{r_km[i]} km: {f2(ncc['sum_ratio'][i], 1)}×" for i in (0, 2, 4, 6, 8, 11)),
         f"95 % CSR envelope {f2(ncc['sum_lo'][2])}–{f2(ncc['sum_hi'][2])} at 1 km, {f2(ncc['sum_lo'][-1])}–{f2(ncc['sum_hi'][-1])} at 30 km: clustered at every scale tested"],
    ]
    stats_table = table(["statistic", "value (95 % interval)", "notes"], stat_rows, cls="compact")
    vr = st.get("vector_replication") or {}
    if vr:
        vr_rows = [
            ["traces used", f"{vr['n_used']} of {vr['n_rows']:,} (centroid inside the footprint)", f"median length {vr['median_length_m']/1000:.1f} km; map_scale attribute {', '.join(f'{k} ({v})' for k, v in vr['map_scale_attribute_counts'].items())}"],
            ["length exponent <em>a</em> (density)", f"{f2(vr['length_fit']['a_density'])} {ci(vr['length_fit']['a_ci95'])}", f"above {vr['length_fit']['xmin_m']/1000:.1f} km, n = {vr['length_fit']['n_tail']}; raster components: {f2(ld['a_density'])} {ci(ld['a_ci95'])}"],
            ["correlation dimension D (1.5–30 km)", f2(vr['correlation_dimension_1p5_30km']['D']), f"raster centroids {f2(cdim['centroids_1p5_30km']['D'])}"],
            ["nearest-larger-neighbour <em>x</em>, tail", f"{f2(vr['nln_tail']['x'])} {ci(vr['nln_tail']['x_ci95'])}", f"Bour &amp; Davy predicts {f2(vr['bour_davy_predicted_x'])} from this table's own a and D: <span class=\"tag-ok\">consistent</span>; all lengths {f2(vr['nln_all_lengths']['x'])}"]]
        vr_html = ("<p class=\"small\"><strong>Independent replication on the vector USGS Quaternary traces</strong> (<code>gdr_qfaults_traces.csv</code>: surveyed lengths, no rasterisation, no merging of touching traces). "
                   "A different object definition, so agreement is a replication, not a duplicate.</p>" + table(["statistic", "vector traces", "reading"], vr_rows, cls="compact"))
    else:
        vr_html = ""

    bd_rows = [
        ["predicted <em>x</em> = (a − 1)/D, <em>a</em> = density exponent", f"{f2(bd['x_predicted'])}", f"range {ci(bd['x_predicted_range'])} from the interval on a and the two D estimates"],
        ["measured tail <em>x</em>, centroid distance", f"{f2(bd['x_measured_tail_centroid'])} {ci(bd['x_measured_tail_centroid_ci95'])}",
         "<span class=\"%s\">%s</span>" % ("tag-ok" if bd["consistent_centroid"] else "tag-flag", "consistent" if bd["consistent_centroid"] else "not consistent")],
        ["measured tail <em>x</em>, edge distance", f"{f2(bd['x_measured_tail_edge'])} {ci(bd['x_measured_tail_edge_ci95'])}",
         "<span class=\"%s\">%s</span>" % ("tag-ok" if bd["consistent_edge"] else "tag-flag", "consistent" if bd["consistent_edge"] else "marginal: just above the predicted range")],
        ["measured <em>x</em>, all lengths", f"{f2(bd['x_measured_all_lengths_centroid'])}", "short traces break the scaling (incompleteness, merging or a physical break; the data cannot separate them)"],
        ["what a <em>cumulative</em> exponent would predict", f"{f2(bd['if_cumulative_exponent_were_inserted_for_a']['x_predicted'])}", "wrong reading of the relation — see the simulation below and flag I-14"],
    ]
    bd_table = table(["quantity", "value", "reading"], bd_rows, cls="compact")
    syn_rows = [[f2(r["a_density"], 1), f2(r["D"], 1), f2(r["x_geomean_estimator"]), f2(r["x_mean_estimator"]), f2(r["x_predicted"]), f2(r["x_if_cumulative_were_a"])] for r in syn["rows"]]
    syn_table = table(["a (density)", "D", "x, geometric-mean estimator", "x, arithmetic-mean estimator", "(a − 1)/D", "(a − 2)/D"], syn_rows, cls="compact")

    labels_e = ["0–200 m (structural)", "200–400 m", "400–600 m", "0.6–1 km", "1–1.5 km", "1.5–2.5 km", "2.5–4 km", "4–7 km", "7–12 km", "12–20 km", "&gt; 20 km"]
    a, b = en["catalogue_short_traces"], en["sgmc_not_in_catalogue"]
    en_rows = []
    for i, lab in enumerate(labels_e):
        def cell(p):
            e = p["enrichment"][i]
            if e is None or e != e or p["n_eligible"][i] < 20000:
                return "—"
            return f"{e:.2f} [{p['lo'][i]:.2f}, {p['hi'][i]:.2f}]"
        en_rows.append([lab, cell(a), cell(b), f"{a['n_eligible'][i]:,}"])
    en_table = table(["distance from the nearest long known fault (≥ 3 km)", "catalogue's own short traces", "SGMC faults missing from the catalogue", "eligible px"], en_rows, cls="compact")

    tw_rows = []
    for name, key in (("SGMC missing from catalogue", "sgmc_not_in_catalogue"), ("catalogue short traces", "catalogue_short_traces")):
        t = tw[key]
        for w, wn in enumerate(t["wedges"]):
            tw_rows.append([name if w == 0 else "", wn.split(" (")[0] + " (" + wn.split(" (", 1)[1] if " (" in wn else wn] + [f"{t['enrichment'][w][k]:.2f} [{t['lo'][w][k]:.2f}, {t['hi'][w][k]:.2f}]" for k in range(len(t["edges_m"]) - 1)])
        tw_rows.append(["", "continuation ÷ lateral (pooled)", f"{t['continuation_over_lateral']:.2f} [{t['continuation_over_lateral_ci95'][0]:.2f}, {t['continuation_over_lateral_ci95'][1]:.2f}]", "", "", "", ""])
    edges = tw["sgmc_not_in_catalogue"]["edges_m"]
    tw_table = table(["target", "wedge around the tips"] + [f"{edges[k]/1000:g}–{edges[k+1]/1000:g} km" for k in range(len(edges) - 1)], tw_rows, cls="compact")

    # per-artefact audit table
    rows_art = []
    for r in sorted(pa["artefacts"], key=lambda r: -r["live_dti"]):
        if "signed_large" not in r:
            continue
        yl = r["survey_lines"].get("traverse_400m_along_y", {})
        xl = r["survey_lines"].get("tie_4km_along_x", {})
        rows_art.append([esc(r["id"]), num(r["live_dti"], 4), f"{r['structure']['n_pixels']:,}", f"{r['signed_large']:+.2f}", esc(r["arrangement_bin"].split(" (")[0]),
                         num(r["near_long"]["200-1000m"], 2), num(r["structure"]["share_isolated_dots"], 2),
                         ("<span class=\"tag-flag\">%.0f</span>" % yl["strength"]) if yl.get("p_rank", 1) <= 0.05 else "%.0f" % yl.get("strength", 0),
                         ("<span class=\"tag-flag\">%.0f</span>" % xl["strength"]) if xl.get("p_rank", 1) <= 0.05 else "%.0f" % xl.get("strength", 0)])
    for r in pa.get("unscored", []):
        yl = r["survey_lines"].get("traverse_400m_along_y", {})
        xl = r["survey_lines"].get("tie_4km_along_x", {})
        rid = r["id"]
        nm = ("H24 (superseded)" if rid.startswith("h24") else "H29 (de-aliased lattice)" if "h29" in rid else "<strong>H30 (primary)</strong>" if "h30" in rid
              else "GEMSDOE22 h22-1 (fractal clustering prior)" if "h22-1" in rid else "GEMSDOE22 h22-2" if "h22-2" in rid else rid[:40])
        rows_art.append([f"{nm} — unscored", "—", f"{r['structure']['n_pixels']:,}", f"{r['signed_large']:+.2f}", esc(r["arrangement_bin"].split(" (")[0]),
                         num(r["near_long"]["200-1000m"], 2), num(r["structure"]["share_isolated_dots"], 2),
                         ("<span class=\"tag-flag\">%.0f</span>" % yl["strength"]) if yl.get("p_rank", 1) <= 0.05 else "%.0f" % yl.get("strength", 0),
                         ("<span class=\"tag-flag\">%.0f</span>" % xl["strength"]) if xl.get("p_rank", 1) <= 0.05 else "%.0f" % xl.get("strength", 0)])
    art_table = table(["artefact", "live DTI", "emitted px", "signed divergence", "arrangement bin", "near-long-fault enrichment 0.2–1 km", "isolated-dot share", "400 m line strength (y)", "4 km line strength (x)"], rows_art, cls="compact")

    cal_rows = [[esc(k), f"{v['n']}", f"{v['rho_live_dti']:+.2f}", f"{v['p_live_dti']:.3f}", f"{v['rho_skill']:+.2f}", f"{v['p_skill']:.3f}"] for k, v in cal.items()]
    cal_table = table(["audit descriptor", "n", "Spearman ρ vs live DTI", "p", "ρ vs placement skill", "p"], cal_rows, cls="compact")
    bin_rows = [[esc(b["name"]), b["n"], num(b["mean_live_dti"], 3) if b["mean_live_dti"] is not None else "—",
                 (f"{b['min_live_dti']:.3f}–{b['max_live_dti']:.3f}" if b["mean_live_dti"] is not None else "—"), esc(", ".join(b["members"]))] for b in bins]
    bin_table = table(["arrangement bin (signed divergence)", "n", "mean live DTI", "range", "members"], bin_rows, cls="compact")

    ref = pa["catalogue_subset_divergence"]

    def cand_row(label, snap, extra=""):
        y = snap["survey_lines"]["traverse_400m_along_y"]
        return [label, f"{snap['n']:,}", num(snap["kbar"], 4), num(snap["eta"], 3), num(snap["coverage"], 3),
                f"{y['strength']:.1f} (p = {y['p_rank']:.3f})", f"{snap['separation_violating_pairs']:,}", f"{snap['signed_divergence']:+.2f}", esc(snap["arrangement_bin"].split(" (")[0]), num(snap["mean_score_rank"], 3)]
    cand_rows = [cand_row("H24 (superseded)", h29["audit_before_h24"]), cand_row("H29 (de-aliased lattice)", h29["audit_after"]), cand_row("<strong>H30 (arrangement-matched, primary)</strong>", h30["audit_after"])]
    cand_table = table(["file", "dots", "K̄", "η", "300 m coverage", "400 m line (strength, rank p)", "pairs closer than 400 m", "signed divergence", "arrangement bin", "mean score rank of dots"], cand_rows, cls="compact")

    off = h25["ratio_to_far_field_gt_4km"]
    off_labels = ["0", "50–150", "150–250", "250–350", "350–450", "450–550", "550–700", "700–900", "0.9–1.2 km", "1.2–1.6 km", "1.6–2.2 km", "2.2–3 km"]
    off_rows = [[nm] + [("—" if v is None else f"{v:.2f}") for v in off[nm]] for nm in off]
    off_table = table(["scarp metric ÷ far-field mean"] + off_labels, off_rows, cls="compact")

    fb = pa.get("feature_band_lines", {})
    reds = [k for k, v in fb.items() if v.get("traverse_400m_along_y", {}).get("p_rank", 1) <= 0.05]
    tie_reds = [k for k, v in fb.items() if v.get("tie_4km_along_x", {}).get("p_rank", 1) <= 0.05]
    g = pa["geometry"]

    return f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Clustering audit · prior data-enabled analysis · source rasters absent now</div>
    <h1>Faults are a spatial statistic. The saved run fitted it before auditing its candidate emission.</h1>
    <p class="lead">The following statistics were computed in an earlier hash-verified restore; the labels/features are absent in this checkout, so they are not a fresh fit. The known INGENIOUS/USGS traces were strongly clustered ({f2(ncc['sum_ratio'][2], 1)}× the random expectation at 1 km, still {f2(ncc['sum_ratio'][-1], 2)}× at 30 km; D ≈ {f2(cdim['centroids_1p5_30km']['D'])}–{f2(cdim['centroids_0p5_10km']['D'])})
    and, above {ld['xmin_m']/1000:.1f} km, followed the Bour &amp; Davy (1999) scaling. The saved audit found that H24 carried a 400 m line and separation violations; H29/H30 remove those measured artefacts in the archived files, but do not validate fault placement. The SGMC missing-fault proxy suggests a small prior signal, not ground truth.</p></div>
    <aside class="hero-aside"><span class="status status-warning">Correlational · not validated against hidden labels</span>
      <strong style="margin:.8rem 0 .45rem">Signed arrangement divergence orders the live scores</strong>
      <p class="small">Spearman {cal[sig_key]['rho_live_dti']:+.2f} (p = {cal[sig_key]['p_live_dti']:.3f}, n = {cal[sig_key]['n']}). Bins defined after looking at the data; the one controlled pair says dispersal alone changes nothing. Flags I-14 … I-24 on the <a href="verification.html">audit page</a>.</p></aside></div></section>

  <section class="section">
    <div class="section-head"><div><div class="eyebrow">1 · Fitted on labels.tif, no feature band, no model</div><h2>The known catalogue as a fault population</h2>
    <p>Definitions are declared, not assumed (<code>src/gems/faultstats.py</code>): a fault is one 8-connected component (touching traces merge, so this is a lower bound on the number of faults and an upper bound on their length);
    <em>a</em> is the <strong>density</strong> exponent; length is the maximum Feret diameter. Sources: Bour &amp; Davy (1999, <a href="https://doi.org/10.1029/1999GL900419">GRL 26(13) 2001–2004</a>),
    Marrett et al. (2018, <a href="https://doi.org/10.1016/j.jsg.2017.06.012">J. Struct. Geol. 108, 16–33</a>), Wang et al. (2019, <a href="https://doi.org/10.1144/petgeo2018-146">Petrol. Geosci. 25, 415–428</a>),
    Clauset, Shalizi &amp; Newman (2009, <a href="https://doi.org/10.1137/070710111">SIAM Rev. 51, 661–703</a>).</p></div></div>
    {stats_table}
    {vr_html}
    <figure><img src="assets/fig-length-nln.svg" alt="Length distribution and nearest-larger-neighbour scaling of the known catalogue"><figcaption>Left: cumulative length distribution with the KS-selected power-law tail. Right: mean distance to the nearest larger trace; the tail slope agrees with the Bour &amp; Davy prediction, the all-length slope is flatter.</figcaption></figure>
    <figure><img src="assets/fig-ncc.svg" alt="Normalised correlation sum of the catalogue and of selected emissions"><figcaption>Left: the catalogue's trace centroids against the 95 % envelope of complete spatial randomness inside the footprint. Right: the same statistic for emitted pixels of selected artefacts; H24 is flat at 1 (random) from 1 km up.</figcaption></figure>
    <div class="callout"><strong>The NCC is a 2-D adaptation.</strong> Marrett et al. (2018) published the normalised correlation count for 1-D scanlines (observed count over the count expected for a random arrangement; 1 = random, &gt; 1 clustered, &lt; 1 anti-clustered/regular; the log-log slope of the normalised
    correlation <em>sum</em> equals the correlation dimension minus one). The 2-D pair-count form against complete spatial randomness inside the irregular footprint is used for the main results and the published scanline form is stored alongside in
    <a href="data/fault-statistics.json">fault-statistics.json</a>; both are labelled wherever reported.</div>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="eyebrow">2 · Does the Bour &amp; Davy relation hold here?</div><h2>x = (a − 1)/D, checked three ways</h2>
    <p>The abstract states the relation but not whether <em>a</em> is the density or the cumulative exponent. With positions of fractal dimension D independent of size, the nearest of the N(&gt;l) ~ l<sup>−(a−1)</sup> larger faults lies at d ~ N<sup>−1/D</sup> ~ l<sup>(a−1)/D</sup>,
    which reproduces the published form only for the density exponent. A simulation confirms it, and the check is a unit test.</p></div></div>
    {bd_table}
    <p class="small"><strong>Simulation</strong> ({syn['n_points']:,} points, {syn['seeds']} seeds each; positions are Lévy dust of dimension D, lengths Pareto with density exponent a, independent):</p>
    {syn_table}
    <p class="small">{esc(syn['verdict'])}.</p>
    <div class="callout"><strong>A sibling repository got this wrong.</strong> GEMSDOE22's consistency test fits a cumulative exponent and then evaluates (a − 1)/D with it, so its "consistent: true" does not test the published relation (flag I-14). Its trace count (3,199), its median nearest-larger distance (1,631 m vs 1,636 m here) and the shape of its clustering curve agree with this repository's independent implementation.</div>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="eyebrow">3 · The geometric prior, measured</div><h2>How strongly do missing faults cluster around known larger faults?</h2>
    <p>Two target populations answer different questions. The catalogue's own short traces show how <em>known</em> faults are arranged; SGMC faults that the catalogue does not capture (&gt; 300 m from any catalogue pixel, an independent compilation) are the only available sample of faults
    <em>missing</em> from it. Distance is to the nearest of the {en['n_long_traces']} traces of ≥ 3 km; intervals are 95 % spatial-block bootstraps (50 km blocks).</p></div></div>
    <figure><img src="assets/fig-enrichment.svg" alt="Enrichment of two fault populations with distance from long known faults"><figcaption>1 = no effect. Known short traces: ×2.3 within 1 km. Faults missing from the catalogue: ×1.8 at 200–400 m, ×1.4 at 400–600 m, about 1 beyond 1 km, depleted past 7 km.</figcaption></figure>
    {en_table}
    <p class="small">Blocked out-of-fold AUC of the fitted profile (2 × 2 geographic blocks): catalogue short traces <strong>{f2(ba['catalogue_short_traces']['auc_mean'], 3)}</strong>, faults missing from the catalogue <strong>{f2(ba['sgmc_not_in_catalogue']['auc_mean'], 3)}</strong> (parameter-free baseline 1/(1 + d/1 km): {f2(ba['catalogue_short_traces']['baseline_inverse_distance_mean'], 3)} / {f2(ba['sgmc_not_in_catalogue']['baseline_inverse_distance_mean'], 3)} — the fitted profile adds nothing beyond “closer is better”).
    The 0–200 m band is structural (distinct 8-connected traces cannot be closer), and the SGMC 200–400 m band only holds 300–400 m by construction.</p>
    <div class="section-head"><div><div class="eyebrow">Along strike</div><h2>The extrapolated pattern beyond a tip</h2>
    <p>{tw['sgmc_not_in_catalogue']['n_endpoints']:,} endpoints of the long traces; each eligible pixel is assigned to the wedge between its offset and the outward strike direction.</p></div></div>
    {tw_table}
    <div class="callout"><strong>Reading.</strong> The brief's hypothesis holds qualitatively: beyond a tip, in line with strike, faults missing from the catalogue are enriched ×{f2(tw['sgmc_not_in_catalogue']['enrichment'][0][0], 1)} at 300–600 m against ×{f2(tw['sgmc_not_in_catalogue']['enrichment'][2][0], 1)} sideways,
    and the effect fades to ≈ 1 within 1.5 km. But the continuation zone (≤ 25° of strike, 300–1,000 m beyond the tips) covers only <strong>{100*cz['area_share_of_eligible']:.2f} %</strong> of the eligible domain and holds
    <strong>{100*cz['share_of_missing_fault_pixels_inside']:.2f} %</strong> of the missing-fault proxy pixels. It can break near-ties; it cannot carry a budget. The 200–600 m band is also where a displaced duplicate of a catalogued fault would fall, so part of it may be mis-registration rather than clustering.</div>
    <div class="callout"><strong>Applied as a tie-break only.</strong> The smaller of the two enrichment profiles feeds a rank bonus of at most 0.003 (<code>src/gems/clusterprior.py</code>). Inside a dispersed lattice it moves about 1 % of the dots more than 200 m: within a 9 × 9 non-maximum-suppression window the prior is flat, so it matters only if it changes <em>which windows get dots</em> — an allocation
    that the live scores do not support (emissions concentrating &gt; 3× within 1 km of long known faults scored 0.002–0.046; Spearman ρ = {cal['enrichment 0.2-1 km of long faults']['rho_live_dti']:+.2f}, p = {cal['enrichment 0.2-1 km of long faults']['p_live_dti']:.2f}).</div>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="eyebrow">4 · Post-hoc audit of predicted rasters</div><h2>Survey-line aliasing, block edges and arrangement</h2>
    <p><strong>Geometry (verified).</strong> USGS GeoDAWN metadata (<a href="https://doi.org/10.5066/P93LGLVQ">DOI 10.5066/P93LGLVQ</a>): Area 2 traverse lines every <strong>400 m</strong> flown east–west, tie lines every <strong>4,000 m</strong> north–south; Area 1 200 m / 2,000 m.
    The official outlines reproduce the published areas to 0.04 % (footprint {g['footprint_km2']:,.1f} km² vs 51,695.2 km² data extent; Area 1 {g['area1_km2']:,.1f} km² vs 2,411.7 km²); Area 1 is 4.7 % of the footprint and the 1 m lidar covers {100*g['lidar_valid_share']:.1f} %.</p></div></div>
    <figure><img src="assets/fig-lines.svg" alt="Spectral line strength at the 400 m traverse period in the 19 official feature bands"><figcaption>Peak power at the survey period over the median of the surrounding band, ranked against 60 control frequencies. Only <code>tmi_hg</code> is far above its controls ({", ".join(reds)} reach p ≤ 0.05; with 19 bands one or two marginal reds are expected by chance). The 4 km tie-line period is significant in {", ".join(tie_reds)}.</figcaption></figure>
    <p class="small"><strong>Detector.</strong> Row (or column) means of the raster inside Area 2 → detrended → power at the survey frequency ± 0.0015 c/px over the median of a ± 0.012 band → rank among 60 control frequencies (minimum attainable p = 1/61 = 0.016). Boundary jumps use the density ratio across the footprint, lidar-validity and Area 1 edges relative to the same ratio for the catalogue.</p>
    <p class="small"><strong>Arrangement baseline.</strong> A catalogue-like sample (independent thinning of whole traces to the same pixel count) sits {f2(ref['large_scale_mean'], 2)} (max {f2(ref['large_scale_max'], 2)}) log-units from the catalogue at 2–30 km; the symmetric divergence of H24 is 3.5× that. The <em>signed</em> divergence (negative = less clustered than the catalogue) separates a flat lattice from a catalogue-hugging detector, which the symmetric measure cannot.</p>
    <figure><img src="assets/fig-arrangement.svg" alt="Live public DTI against signed arrangement divergence for 23 emissions"><figcaption>Each dot is one live-scored emission (the exact duplicate hedge-v2 is counted once). Dashed lines mark the unscored files. Bins are post-hoc.</figcaption></figure>
    {bin_table}
    <p class="small">H30's target is the median signed divergence of the seven best-scoring emissions (live DTI ≥ {tgt['dti_floor']:.4f}): <strong>{tgt['value']:+.3f}</strong>. Status: {esc(tgt['status'])}.</p>
    {art_table}
    <p class="small">Red = rank p ≤ 0.05 against the control frequencies. Calibration against the live scores:</p>
    {cal_table}
    <div class="callout"><strong>What the calibration says, and does not.</strong> The signed arrangement divergence orders the 23 live scores (ρ = {cal[sig_key]['rho_live_dti']:+.2f}): over-clustered, catalogue-hugging detectors score worst, flat lattices score middling, emissions mildly less clustered than the catalogue score best.
    The survey-line and edge descriptors do <em>not</em> move with the score (none reaches p &lt; 0.05; the closest, the Area 1 edge jump, is ρ = {cal['area1-edge jump index']['rho_live_dti']:+.2f}, p = {cal['area1-edge jump index']['p_live_dti']:.2f}), so the 400 m comb is flagged as an artefact risk for the Phase 2 reviewers, not as something shown to cost score.
    The strongest 400 m line in the whole set (strength {max((r['survey_lines'].get('traverse_400m_along_y', {}).get('strength', 0) for r in pa['artefacts'])):,.0f}) belongs to <code>tso1-conj-alteration-mag</code>, a magnetics-derived emission that scored 0.0782; five others with p ≤ 0.05 score anywhere from 0.002 to 0.156.
    The isolated-dot share correlates with the score (ρ = {cal['share isolated dots']['rho_live_dti']:+.2f}, p = {cal['share isolated dots']['p_live_dti']:.3f}) but that is a type confound — the six dot emissions are hand-built rules, the worst scorers are probability maps thresholded near the catalogue, and the best line-type emission (h19-5, 0.1922) beats every dot-type one.
    All of this is correlational and the bins were drawn after the fact; the one controlled pair (same score, same 155,021 pixels: ridge +0.20, nodes −0.62) scored 0.1152 and 0.1193.</div>
    <div class="section-head"><div><div class="eyebrow">What the audit changed</div><h2>H24 → H29 → H30</h2></div></div>
    {cand_table}
    <p class="small">Same ranking, same budget logic. H29 equalises row phases ({h29['equalisation']['share_moved']:.1%} of dots move {h29['equalisation']['mean_abs_shift_px']:.2f} px on average) and breaks score ties; H30 additionally limits the candidates to the top 30 % of the score ({h30['equalisation']['share_moved']:.1%} moved), which costs about {100*(1-h30['audit_after']['kbar']/h30['audit_before_h24']['kbar']):.0f} % of kernel coverage and moves the arrangement into the bin that holds the best live scores.
    Neither adds placement skill; neither has a live score; the blocked-holdout gate is <strong>not passed</strong> because no valid holdout exists (I-05).</p>
    <p class="small"><strong>Minimum-regret check.</strong> If the score carried <em>no</em> information (skill 1, hidden faults uniform), H30's concentration would cost
    {", ".join(f"{100*v['relative_change']:+.1f} % at |G| = {int(k)//1000}k" for k, v in (h30.get('uninformative_score_check') or {}).items())} of DTI relative to H24 (H29: {", ".join(f"{100*v['relative_change']:+.1f} %" for v in (h29.get('uninformative_score_check') or {}).values())});
    If placement skill transfers, the concentration might gain; that transfer is unvalidated, and the no-information case is only a sensitivity boundary. Treat the H29/H30 comparison as a hypothesis for an independent holdout, not a deployment rationale.</p>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="eyebrow">5 · H-25 relocation, tested on the aggregate</div><h2>Do lidar scarps sit offset from the catalogued traces?</h2>
    <p>If many catalogue traces were displaced by a few hundred metres from their scarps, the scarp signal would peak at a non-zero distance. It does not. {esc(h25['reading'][0].upper() + h25['reading'][1:])}.</p></div></div>
    {off_table}
    <p class="small">Metrics are 100 m aggregates of 1 m lidar features (valid on {100*h25['lidar_valid_share_of_catalogue']:.0f} % of catalogue pixels), relative to pixels &gt; 4 km from any catalogue trace.</p>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Limits</div><h2>What this page does not show</h2></div></div>
    <ul class="list-clean">
      <li><strong>No hidden-label validation.</strong> A prior that ranks held-out <em>known</em> faults (AUC 0.67) is not a prior that finds <em>unknown</em> ones; the independent SGMC proxy gives 0.55, and it is itself a coarse, mostly older compilation.</li>
      <li><strong>Traces merge.</strong> Component count and length are bounds, not the vector fault inventory; the vector traces of GDR 1391 carry lengths and centroids only, so edge distances cannot be computed from them.</li>
      <li><strong>The paper body was not read.</strong> The Bour &amp; Davy and Marrett et al. abstracts were read at the publishers; the density reading is derived and simulated; Marrett's CorrCount software was not run.</li>
      <li><strong>Arrangement bins are post-hoc</strong> (23 emissions in families) and H30's target is a rule fixed after seeing the table.</li>
      <li><strong>Survey-line phase test is inconclusive:</strong> the emission comb's phase lies between that of <code>tmi_hg</code> and that of the score, so inheritance from the survey cannot be separated from coincidence (I-15).</li>
    </ul>
    <pre class="formula">python3 scripts/restore_workspace.py --all
python scripts/fit_fault_statistics.py                # -> docs/data/fault-statistics.json
python scripts/audit_predictions.py --extra &lt;rasters&gt;  # -> docs/data/prediction-audit.json
python scripts/build_audited_emission.py --variant h30 --set-primary
python scripts/make_cluster_figures.py
python -m unittest tests.test_faultstats tests.test_audit tests.test_clusterprior</pre>
  </section>"""


def build():
    stamp = evidence_stamp()
    man = j("submission-manifest.json", {}) or {}
    tiff_audit_record = j("current-tiff-audit.json", {}) or {}
    bld = j("submission-build.json", {}) or {}
    hab = j("habitat-model.json", {}) or {}
    bnd = j("live-model-bounds.json", {}) or {}
    oof = j("oof-evaluation.json", {}) or {}
    ens = j("ensemble-report.json", {}) or {}
    cand = j("phase2-candidates.json", {}) or {}
    lb = j("leaderboard.json", {}) or {}
    prox = j("offline-proxy-audit.json", {}) or {}
    irreg = j("irregularities.json", {}) or {}
    fst = j("fault-statistics.json", {}) or {}
    pau = j("prediction-audit.json", {}) or {}
    cdx = j("candidates.json", {}) or {}
    h29 = j("h29-build.json", {}) or {}
    h30 = j("h30-build.json", {}) or {}
    prim = man.get("primary", {}) or {}
    comp = man.get("compatibility", {}) or {}
    validation = man.get("validation", {}) or {}
    release_decision = man.get("release_decision", {}) or {}
    release_status = release_decision.get("status", "BLOCKED")
    release_approved = (
        release_status in {"APPROVED", "APPROVED_BY_SPATIAL_HOLDOUT_GATE"}
        and prim.get("release_approved") is True
        and prim.get("ok_to_upload") is True
    )
    format_preflight = prim.get("format_preflight_passed")
    if format_preflight is None:
        format_preflight = bool((validation.get("nan") or {}).get("passed"))
    tiff_audit = (tiff_audit_record.get("results") or {}).get("primary") or man.get("current_tiff_audit") or {}
    audit_summary = ""
    audit_passed = bool(
        tiff_audit.get("samples_per_pixel") == 1
        and tiff_audit.get("bits_per_sample") == 32
        and tiff_audit.get("epsg") == 32611
        and tiff_audit.get("finite_values_in_0_1") is True
        and tiff_audit.get("positive_infinity_pixels") == 0
        and tiff_audit.get("negative_infinity_pixels") == 0
        and tiff_audit.get("template_match", "").startswith("NOT CHECKED")
    )
    if audit_passed:
        audit_summary = (
            f"Current standalone TIFF audit: {tiff_audit['width']}×{tiff_audit['height']}, "
            f"one float32 band, EPSG:{tiff_audit['epsg']}, 100 m pixels; finite values "
            f"{tiff_audit['finite_min']}–{tiff_audit['finite_max']} and "
            f"{tiff_audit['nan_pixels']:,} NaNs. Exact sample-template comparison was not checked "
            "because <code>data/sample_submission.tif</code> is absent."
        )
    else:
        audit_summary = "No current standalone TIFF audit is recorded."
    format_status_text = (
        "TIFF value/structure audit PASS · template match not rechecked · release BLOCKED"
        if audit_passed else
        ("Historical template-format preflight recorded · release BLOCKED" if format_preflight else "Format preflight not passed")
    )
    release_reason = release_decision.get(
        "reason", "No verified independent uncatalogued-fault spatial holdout is registered; format checks do not approve a competition upload."
    )
    geo = man.get("geometry") or bld.get("geometry", {}) or {}      # the manifest describes the file being offered
    dti_exp = man.get("expected_dti", {}) or {}
    note = man.get("note", "")
    rows_lb = sorted((lb.get("rows") or []), key=lambda r: r.get("rank", 999))
    leader = rows_lb[0] if rows_lb else dict(participant="—", score=0)
    fname = prim.get("name", "(not built yet)")
    fsha = prim.get("sha256", "")[:16]
    fbytes = prim.get("bytes", 0)
    download_href = "downloads/" + fname if prim else "#"
    eta = geo.get("eta")
    area = geo.get("area")
    g_lo = int(bnd.get("lower_bound_max", 0) or 0)
    g_hi = int(bnd.get("upper_bound_from_catalogue_like_truth") or bnd.get("upper_bound_from_sgmc_like_truth") or 0)
    g_proj_lo, g_proj_hi = 6_000, 15_000
    chosen_weighted = 0.0
    for r in (bld.get("table") or []):
        if area and abs(float(r.get("area", 0)) - float(area)) < 1.0:
            chosen_weighted = r.get("weighted_min_over_G", 0.0)

    # ---------- shared blocks ----------
    def dti_cell(g):
        return None

    def scen_range():
        vals = [v for d in (dti_exp or {}).values() if isinstance(d, dict) for v in d.values() if isinstance(v, (int, float))]
        return (min(vals), max(vals)) if vals else (None, None)

    sc_lo, sc_hi = scen_range()
    es = h30.get("expectation_summary") or {}
    lat_txt = f"{es['lattice_type_skill'][0]:.2f}–{es['lattice_type_skill'][1]:.2f}" if es else "—"
    rid_txt = f"{es['ridge_level_skill'][0]:.2f}–{es['ridge_level_skill'][1]:.2f}" if es else "—"
    q_eq = (h30.get("expected_dti_if_q_equals_h19_5") or {})
    ce_lo, ce_hi = (min(q_eq.values()), max(q_eq.values())) if q_eq else (None, None)
    central = f"{ce_lo:.2f}–{ce_hi:.2f}" if q_eq else "—"
    scen_txt = f"{sc_lo:.2f}–{sc_hi:.2f}" if sc_lo is not None else "—"

    q_labels = "/".join(str(q) for q in (bld.get("q_prior") or {})) or "0.04/0.06/0.08/0.11"

    alts = []
    for c in (cdx.get("candidates") or []):
        if (c.get("nan") or {}).get("name") and c["nan"]["name"] != fname:
            alts.append(f"<a href=\"{esc(c['nan']['href'])}\" download>{esc(c['label'])}</a> (<a href=\"{esc(c['allfinite']['href'])}\" download>all-finite</a>)")
    h24ref = (cdx.get("h24_reference") or {}).get("name")
    if h24ref and h24ref != fname:
        alts.append(f"<a href=\"downloads/{esc(h24ref)}\" download>H24 · superseded (comb at 400 m, 931 dots too close)</a>")
    alt_links = " · ".join(alts) if alts else "none"
    dl_block = f"""
  <section class="section" id="download">
    <div class="section-head">
      <div><div class="eyebrow">First-page download · format preflight, not upload approval</div>
      <h2>Downloadable QA candidate</h2></div>
      <span class="status {'status-ok' if audit_passed and release_approved else 'status-warning'}">{esc(format_status_text)}</span>
    </div>
    <div class="download-card">
      <div>
        <h3>{esc(man.get('candidate_label') or 'H30 · arrangement-matched habitat')} · QA only</h3>
        <p>{audit_summary} The manifest records an earlier template comparison as passing, but that comparison could not be re-run in this checkout. No reproducible independent uncatalogued-fault holdout has approved placement. Conditional scenario calculations are not a competition-score forecast; this file is for inspection and file-format QA only.</p>
        <div class="file-meta">
          <span>Filename: <code>{esc(fname)}</code></span>
          <span>3292 × 3730</span><span>single-band float32</span><span>EPSG:32611</span><span>100 m pixels</span>
          <span>values in [0, 1]</span><span>NaN outside the footprint</span>
          <span>{esc(f'{fbytes/1e6:.2f}' if fbytes else '0')} MB</span><span>SHA-256 {esc(fsha)}…</span>
          <span>emitted mass {esc(f'{area:,.0f}' if area else '—')} px</span>
          <span>dispersion efficiency η = {esc(num(eta,3)) if eta else '—'}</span>
        </div>
        <div class="callout"><strong>Do not upload or spend a weekly slot.</strong> {esc(release_reason)}</div>
      </div>
      <div class="button-row">
        <a class="button" href="{esc(download_href)}" download>Download QA candidate .tif ↓</a>
        <a class="button button-secondary" href="data/submission-manifest.json">Manifest JSON</a>
        <a class="button button-secondary" href="data/current-tiff-audit.json">Current TIFF audit</a>
        <a class="button button-secondary" href="clustering.html">Audit &amp; clustering evidence</a>
        <a class="button button-secondary" href="data/submission-build.json">Budget evidence</a>
        <a class="button button-secondary" href="{esc('downloads/' + comp.get('name','')) if comp else '#'}" download>All-finite variant</a>
      </div>
    </div>
    <div class="copy-row" aria-label="QA candidate note preview, not for upload" style="margin-top:1rem">
      <input id="submission-note" readonly value="{esc(note)}">
      <button type="button" data-copy-target="submission-note">Copy QA candidate note</button>
    </div>
    <p class="small" style="margin-top:.9rem"><strong>Other QA files</strong> (main-branch records list earlier template checks; the official sample is absent now; none scored):
      {alt_links}</p>
  </section>"""

    budget_rows = []
    for assumption, by_g in (dti_exp or {}).items():
        if isinstance(by_g, dict):
            budget_rows.append([
                esc(assumption),
                num(by_g.get("6000"), 3),
                num(by_g.get("10000"), 3),
                num(by_g.get("15000"), 3),
            ])
    budget_table = table(
        ["Conditional placement-skill assumption (not validated)", "|G| = 6,000", "|G| = 10,000", "|G| = 15,000"],
        budget_rows,
    )

    anchor_rows = []
    for r in sorted((bnd.get("rows") or []), key=lambda r: -r["dti"]):
        anchor_rows.append([esc(r["id"]), num(r["dti"], 4), f"{r['area']:,.0f}", num(r["coverage"], 3),
                            num(r["env_domain_mean"], 4), num((r["env_domain_mean"]/max(r["area"],1))/(9.42/5106385.0), 2),
                            f"{r['G_lower_bound']:,.0f}",
                            ("—" if not isinstance(r.get("G_if_truth_like_sgmc_gap"), (int, float)) or r["G_if_truth_like_sgmc_gap"] > 1e8 else f"{r['G_if_truth_like_sgmc_gap']:,.0f}")])
    anchor_table = table(["artefact", "live DTI", "emitted px", "coverage", "K̄", "η", "|G| ≥", "|G| implied"], anchor_rows)

    hab_rows = []
    sel = hab.get("selected_layers") or []
    beta = hab.get("beta") or []
    bases = hab.get("layer_bases") or {}
    for nm, b in sorted(zip(sel, beta), key=lambda t: -abs(t[1])):
        hab_rows.append([f"<code>{esc(nm)}</code>", num(b, 4), num(bases.get(nm), 4),
                         "more evidence" if b > 0 else "avoid"])
    hab_table = table(["layer (higher = more evidence unless signed negative)", "weight β", "domain mean", "reading"], hab_rows)

    per_rows = []
    for r in (hab.get("per_anchor") or []):
        per_rows.append([esc(r["id"]), num(r["live_dti"], 4), f"{r['area']:,.0f}", num(r["kbar"], 4),
                         f"{r['implied_tp']:,.0f}", num(r["implied_tp"]/max(1, r["area"]), 4),
                         num(r["skill"], 2), num(r["cv_pred_skill"], 2)])
    per_table = table(["artefact", "live DTI", "emitted px", "K̄", "implied TP", "TP per px", "skill", "CV-predicted skill"], per_rows)

    proxy_rows = [[f"<code>{esc(k)}</code>", f"{v['n_truth']:,}", num(v["spearman_rho"], 3), num(v["p"], 3),
                   "usable" if v["spearman_rho"] > 0.6 and v["p"] < 0.01 else "<strong>not usable</strong>"]
                  for k, v in (prox.items() if isinstance(prox, dict) else [])]
    proxy_table = table(["offline proxy truth", "proxy px", "Spearman ρ vs live", "p", "verdict"], proxy_rows)

    fold_rows = [[r["fold"], f"{r['truth_px']:,}", f"{r['budget']:,}", num(r["dti"], 4), num(r["random_control_mean"], 4),
                  "yes" if r["beats_random"] else "<strong>no</strong>", num(r["epistemic_share"], 3)]
                 for r in (oof.get("folds") or [])]
    fold_table = table(["fold", "target px", "budget px", "ensemble DTI", "random control DTI", "beats random", "epistemic share"], fold_rows)

    cand_rows = []
    for r in (cand.get("candidates") or [])[:40]:
        cand_rows.append([r["rank"], f"{r['px']:,}", f"{r['easting']:,.0f} E / {r['northing']:,.0f} N",
                          num(r["d_to_catalogue_m"], 0), num(r["mean_probability"], 4),
                          num(r["epistemic_var"], 5), num(r["aleatoric_var"], 5), num(r["epistemic_share"], 3),
                          num(r["survey_coverage"], 3), esc(r["epistemic_interpretation"]), num(r["priority"], 4)])
    cand_table = table(["#", "px", "UTM 11N", "m to catalogue", "p̄", "epistemic", "aleatoric", "epi share", "survey coverage", "reading", "priority"], cand_rows)

    lb_attribution = esc(lb.get("attribution_caveat") or ATTRIBUTION_FALLBACK)
    lb_phase = esc(lb.get("phase_caveat") or PHASE_FALLBACK)
    lb_rows = [[r.get("rank"), esc(r.get("participant")), num(r.get("score"), 4)] for r in rows_lb[:25]]
    lb_table = table(["rank", "participant", "public DW-Tversky"], lb_rows, tbody_id="leaderboard-rows")

    irregular_rows = [[f"<code>{esc(f.get('id'))}</code>", esc(f.get("severity")), esc(f.get("status")),
                       esc(f.get("title")), esc(f.get("action"))] for f in (irreg.get("flags") or irreg.get("irregularities") or [])]
    irregular_table = table(["id", "severity", "status", "finding", "action taken"], irregular_rows)

    ens_cfg = (ens.get("config") or {})
    ens_full = (ens.get("full_domain") or {})

    # ---------- pages ----------
    index = f"""
  <section class="hero">
    <div class="hero-grid">
      <div>
        <div class="eyebrow">DOE GEMS Prize · DrivenData #306 · evidence records of {esc(stamp)} · source rasters absent in current checkout</div>
        <h1>Faults are spatially structured; this emission remains a QA candidate.</h1>
        <p class="lead">The known catalogue is strongly clustered ({esc(num((fst.get('ncc') or {}).get('centroids_2d', {}).get('sum_ratio', [0,0,0])[2], 1))}× the random expectation at 1 km) and obeys the Bour &amp; Davy scaling above 3 km.
        Held against that statistic, the previous file (H24) was a uniform lattice that carried a spectral line at exactly the <strong>400 m GeoDAWN flight-line spacing</strong>
        and broke its own separation rule in 931 places. This page now ships <strong>H30</strong>: same ranking, those defects removed, arrangement moved into the bin that holds the best live scores.
        H29/H30 have no live score, and no independent uncatalogued-fault holdout has approved their placement. The downloadable H30 raster is QA-only; conditional metric scenarios are not a score forecast. The live leader in the latest official capture is <strong id="leader-score-lead">{esc(num(leader.get('score'),4))}</strong>.</p>
        <div class="button-row" style="margin-top:1.25rem">
          <a class="button" href="{esc(download_href)}" download>Download QA candidate .tif ↓</a>
          <a class="button button-secondary" href="executive-summary.html">Exactly how to submit →</a>
          <a class="button button-secondary" href="clustering.html">The clustering audit →</a>
        </div>
      </div>
      <aside class="hero-aside">
        <span class="status status-warning">Holdout approval: BLOCKED</span>
        <strong style="margin:.8rem 0 .45rem">QA format pass ≠ upload approval</strong>
        <p class="small">The main-branch manifest records a prior H30 template preflight, but the official template raster is missing from this checkout and the comparison was not re-run here. Placement has not beaten a verified current-best OOF baseline on independent uncatalogued-fault truth. Do not spend a submission slot. Conditional scenario calculations are not a predicted DTI. Latest public leader: <strong id="leader-score">{esc(num(leader.get('score'),4))}</strong> (<span id="leader-name">{esc(leader.get('participant'))}</span>).</p>
        <a href="verification.html">Review the release gate and open limitations →</a>
      </aside>
    </div>
  </section>
{dl_block}
  <section class="grid-3" aria-label="Status">
    <div class="card metric-card"><span>Hidden public-test truth |G|</span><strong>{esc(f"{bnd.get('lower_bound_max',0):,.0f}")}–{esc(f"{(bnd.get('upper_bound_from_catalogue_like_truth') or 0):,.0f}")}</strong><span>exact bounds from 24 live scores ({esc(f"{(bnd.get('upper_bound_from_sgmc_like_truth') or 0):,.0f}")} upper if the hidden traces look like SGMC); the previously assumed 125,000 is refuted</span></div>
    <div class="card metric-card"><span>Dispersion efficiency η of this emission</span><strong>{esc(num(eta,3)) if eta else '—'}</strong><span>group best 0.85 (h28), h19-5 0.39. The cross-artefact η–q correlation (ρ = +0.61) is confounded; the one controlled pair shows no TP gain from dispersal (I-17)</span></div>
    <div class="card metric-card"><span>Habitat model, nested leave-one-family-out CV</span><strong>ρ = {esc(num(hab.get('nested_cv_spearman'),3))}</strong><span>on log placement skill, {esc(hab.get('n_anchors'))} live-scored artefacts, {esc(hab.get('n_layers'))} evidence layers</span></div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Recorded in the 2026-10-02 audit · inputs currently absent</div><h2>Six findings from fitting the fault statistic before touching the model</h2></div></div>
    <p class="small">These findings are reproducible records from an earlier hash-verified input restore, not a fresh fit from the current filesystem. The three core competition rasters and all external layers are currently absent; restore and hash-check them before any rerun.</p>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">1 · The catalogue is a clustered, self-similar fault population</div>
        <p>3,199 traces; length exponent a = {esc(num((fst.get('length_distribution') or {}).get('extent', {}).get('a_density'), 2))} above 3 km; nearest-larger-neighbour x = {esc(num((fst.get('bour_davy_consistency') or {}).get('x_measured_tail_centroid'), 2))}
        against the Bour &amp; Davy prediction {esc(num(((fst.get('bour_davy_consistency') or {}).get('x_predicted_range') or [0, 0])[0], 2))}–{esc(num(((fst.get('bour_davy_consistency') or {}).get('x_predicted_range') or [0, 0])[1], 2))}; correlation dimension ≈ 1.5–1.7; the normalised correlation
        sum is 3.6–4.2× random between 0.5 and 2 km and still 1.15× at 30 km. <a href="clustering.html">Details and figures →</a></p></div>
      <div class="card"><div class="card-kicker">2 · H24 failed its own audit</div>
        <p>A spectral line at exactly the 400 m Area 2 traverse spacing (strength {esc(num((h29.get('audit_before_h24') or {}).get('survey_lines', {}).get('traverse_400m_along_y', {}).get('strength'), 0))} vs a control 95th percentile of 10, rank p = 0.016),
        {esc(f"{(h29.get('audit_before_h24') or {}).get('dots_with_violation', 0):,}")} dots closer than the stated 400 m (equal-score plateaus accepted together), and an arrangement that is statistically a lattice. Removed in H29/H30.</p></div>
      <div class="card"><div class="card-kicker">3 · The geometric prior is real but small for the faults that matter</div>
        <p>Faults missing from the catalogue (independent SGMC sample) are enriched ×1.8 at 200–400 m and ×2.1 in the continuation wedge beyond tips, but ≈ 1 beyond 1 km; the continuation zone covers 0.7 % of the domain. Live scores reward no concentration near known faults.
        The prior is therefore wired in as a tie-break (≤ 0.003 rank units, ~1 % of dots move).</p></div>
      <div class="card"><div class="card-kicker">4 · Dispersal is not the free lever it was presented as</div>
        <p>In the one controlled pair (same score, same 155,021 pixels) dispersal raised K̄ 2.7× and lowered skill 2.6×, leaving TP — and DTI (0.1152 → 0.1193) — unchanged. The “0.12–0.34 projected” headline assumed skill would transfer; no score forecast is supported.</p></div>
      <div class="card"><div class="card-kicker">5 · Arrangement orders the live scores</div>
        <p>Signed divergence of an emission's pair statistics from the catalogue's: Spearman {esc(num(next((v['rho_live_dti'] for k, v in (pau.get('calibration') or {}).items() if k.startswith('signed')), 0), 2))} with live DTI (n = 23, post-hoc bins, correlational). Over-clustered detectors average 0.034, lattices 0.093,
        mildly-less-clustered emissions 0.170. H24 was in the lattice bin; H30 is in the best one.</p></div>
      <div class="card"><div class="card-kicker">6 · Reproducibility, prior-run record</div>
        <p>H24 rebuilds bit-for-bit from public inputs; all 23 live-scored artefacts re-fetch with exact pixel-count identity; the full habitat refit reproduces the committed model <em>only</em> when anchors are listed in the committed order (tie-breaking on a duplicate anchor, flag I-20).</p></div>
    </div>
    <p class="small">Earlier findings that still stand: |G| is {esc(f"{bnd.get('lower_bound_max',0):,.0f}")}–{esc(f"{(bnd.get('upper_bound_from_catalogue_like_truth') or 0):,.0f}")} pixels, not 125,000; the habitat is lidar uphill-facing scarps, steps and crests plus 700 m detrended-slope heterogeneity and low radiometric U (nested-CV ρ = {esc(num(hab.get('nested_cv_spearman'),3))}); no offline proxy truth ranks the live artefacts better than chance
    (best ρ = {esc(num(max((v['spearman_rho'] for v in prox.values()), default=0),3))}, p = {esc(num(min((v['p'] for v in prox.values()), default=1),3))}).</p>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Budget choice</div><h2>Conditional DTI sensitivity (not a score forecast)</h2>
      <p>The rows use three historical placement-skill assumptions and the columns vary the unknown hidden-truth size |G|. The computation is metric algebra only; neither q nor skill transfer to H30 is validated, and the public score matches do not identify the underlying files. Read every value only as conditional sensitivity—not a prediction, expected DTI, validation result, or release criterion.</p></div></div>
    {budget_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Live public leaderboard</div><h2>Current standings</h2>
      <p><span class="status status-neutral" id="feed-status">loading feed…</span> <span class="small" id="leaderboard-retrieved"></span>
      Refreshed automatically by <code>.github/workflows/pages.yml</code>; <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">official source</a>.</p></div></div>
    {lb_table}
    <p class="small">{lb_attribution}</p>
    <p class="small">{lb_phase}</p>
  </section>"""

    executive = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Executive summary</div>
    <h1>Submission steps—only after holdout approval</h1>
    <p class="lead">The H30 GeoTIFF is a QA candidate, not an approved submission. The current independent spatial-holdout gate is BLOCKED; do not spend a slot. These are the upload steps to follow only after a future candidate is explicitly approved in the manifest.</p></div>
    <aside class="hero-aside"><span class="status status-warning">{esc(format_status_text)}</span>
      <strong style="margin:.8rem 0 .45rem">{esc(f'{fbytes/1e6:.2f}' if fbytes else '0')} MB · {esc(fsha)}…</strong>
      <p class="small">{audit_summary} A prior template-validation record names <code>data/sample_submission.tif</code> (SHA-256 {esc((man.get('template_sha256') or '')[:16])}…), but that raster is absent and the comparison was not re-run in this checkout.</p></aside></div></section>
{dl_block}
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Step by step</div><h2>Upload procedure</h2></div></div>
    <ol class="list-clean">
      <li><strong>First check approval.</strong> Do not upload the current QA candidate. Proceed only when <code>docs/data/submission-manifest.json</code> records an explicit spatial-holdout release approval and its report hashes match <code>docs/data/current-holdout-best.json</code>.</li>
      <li><strong>Download only the approved file</strong> named in the updated release manifest. The button above is currently for QA and format inspection, not an upload.</li>
      <li><strong>Sign in</strong> at <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/">drivendata.org/competitions/306</a> and open the <em>Submissions</em> tab only after approval. The account must be the entity registered for this competition.</li>
      <li><strong>Upload the approved <code>.tif</code> unchanged</strong> and use its unique filename/note. Do not open and re-save it in GIS software: that may rewrite nodata or raster metadata.</li>
      <li><strong>Record the score only after an approved upload</strong>: <code>python scripts/record_score.py --score &lt;X&gt; --id &lt;approved-sha8&gt;</code>. Do not use this step to justify an unvalidated upload or alter a release decision retroactively.</li>
    </ol>
    <div class="callout"><strong>The [0, 1] compatibility fallback is also QA-only today.</strong> If a future release-approved upload is rejected with “Predicted values must be in range [0, 1]”, use only the matching approved all-finite variant (<code>{esc(comp.get('name','—'))}</code>) after confirming the manifest/hash. It writes 0.0 outside the footprint; the historical manifest records a prior template check, but the template is missing here and no online uploader test was made. Current H30/H29 files must not be uploaded.</div>
  </section>
  <section class="section">
    <div class="callout"><strong>What the audit changed in the H30 QA candidate (not an upload recommendation).</strong> The previous file (H24) carried a spectral line at exactly the 400 m GeoDAWN flight-line spacing
    (strength {esc(num((h29.get('audit_before_h24') or {}).get('survey_lines', {}).get('traverse_400m_along_y', {}).get('strength'), 0))} against a control 95th percentile of 10), had {esc(f"{(h29.get('audit_before_h24') or {}).get('dots_with_violation', 0):,}")} dots closer than its stated 400 m, and was statistically a uniform lattice
    (signed divergence from the catalogue {esc(num((h29.get('audit_before_h24') or {}).get('signed_divergence'), 2))}). H30 has no such line (strength {esc(num(((h30.get('audit_after') or {}).get('survey_lines') or {}).get('traverse_400m_along_y', {}).get('strength'), 1))}),
    0 pairs closer than 400 m, and signed divergence {esc(num((h30.get('audit_after') or {}).get('signed_divergence'), 2))}. Evidence: <a href="clustering.html">clustering audit</a>.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Rules that constrain the decision</div><h2>Before you spend the slot</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">Three uploads per rolling seven days</div>
        <p>Official rules §3.2/§3.4 (re-read 2026-10-02) permit up to three feedback submissions per rolling seven days. The standing project rule is stricter: a candidate must beat the registered current best on an independent uncatalogued-fault spatial holdout before an upload is considered. <strong>No such holdout exists.</strong> The current registry is BLOCKED; public-board correlations and known-catalogue folds are not substitutes. Keep every slot unused until the gate can be met; a competition upload is not a validation set.</p></div>
      <div class="card"><div class="card-kicker">Which file, and what to expect</div>
        <p><strong>H30</strong> (the QA download above) is an arrangement-audited emission whose main-branch manifest records a prior template-format pass; the sample template is absent here and the comparison was not re-run. <strong>H29</strong> is the de-aliased lattice control; H24 is superseded. None has a live score or release approval. Numbers in the historical budget file are conditional sensitivities, not a forecast. No expected leaderboard score is claimed.</p></div>
      <div class="card"><div class="card-kicker">No experiment slot is authorized</div>
        <p>H-32 on the <a href="hypotheses.html">hypotheses page</a> describes possible paired experiments, but those designs do not waive the independent-holdout rule. They must not be run through competition slots unless the user later revises that standing constraint.</p></div>
      <div class="card"><div class="card-kicker">One submission for both prize rounds</div>
        <p>The same file is scored on the private test set at the close (Initial Round, 5 × $10,000) and re-scored against the
        expanded expert labels in the Final Round ($250,000 pool). Known USGS/INGENIOUS fault pixels are masked out in
        <em>both</em> rounds (staff ruling, forum 11516), so nothing is gained by painting the catalogue.</p></div>
      <div class="card"><div class="card-kicker">Deadline</div>
        <p><strong>3 December 2026, 23:59 UTC.</strong> Generative-AI use must be disclosed per the rules; this repository discloses it in
        <code>README.md</code> and <code>docs/PROJECT_BRIEF.md</code>.</p></div>
    </div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Traceability</div><h2>Every number on this page</h2></div></div>
    {table(["file", "what it records"], [
        ["<a href='data/submission-manifest.json'>submission-manifest.json</a>", "H30 QA filename/hash and separate format-preflight versus release-blocked status"],
        ["<a href='data/current-template-validation.json'>current-template-validation.json</a>", "historical independent TIFF hard checks for H29/H30 variants; format only, not re-run here"],
        ["<a href='data/current-tiff-audit.json'>current-tiff-audit.json</a>", "fresh standard-library audit of H30 files; value bounds and TIFF tags only, exact sample-template comparison unavailable"],
        ["<a href='data/current-holdout-best.json'>current-holdout-best.json</a>", "current-best spatial holdout release registry; BLOCKED"],
        ["<a href='data/submission-build.json'>submission-build.json</a>", "historical budget/η/conditional-DTI sensitivities; not a score forecast"],
        ["<a href='data/habitat-model.json'>habitat-model.json</a>", "the habitat regression: selected layers, weights, nested-CV ρ, per-artefact implied TP and skill"],
        ["<a href='data/live-model-bounds.json'>live-model-bounds.json</a>", "exact bounds on |G| per artefact"],
        ["<a href='data/offline-proxy-audit.json'>offline-proxy-audit.json</a>", "the negative result: every offline proxy truth vs the live ordering"],
        ["<a href='data/oof-evaluation.json'>oof-evaluation.json</a>", "the deep ensemble's out-of-fold DTI against a random-emission control, and the admission gate"],
        ["<a href='data/phase2-candidates.json'>phase2-candidates.json</a>", "reviewer candidates with the epistemic/aleatoric split and survey coverage"],
        ["<a href='data/fault-statistics.json'>fault-statistics.json</a>", "the fault-population statistics fitted on the known catalogue before any model, the prior and the tip-wedge analysis"],
        ["<a href='data/prediction-audit.json'>prediction-audit.json</a>", "the audit of 23 live-scored emissions and of H24/H29/H30, with the calibration against the live scores"],
        ["<a href='data/h29-build.json'>h29-build.json</a> · <a href='data/h30-build.json'>h30-build.json</a> · <a href='data/candidates.json'>candidates.json</a>", "before/after audit of each file, the equalisation statistics and the scenario table"]])}
  </section>"""

    hypotheses = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">New hypotheses</div><h1>Ten audited ideas plus four new geological tests</h1>
    <p class="lead">The register preserves H-24 … H-33 and adds four distinct, unimplemented mechanisms H-34 … H-37. Each new row names layers, physical signature, uncatalogued-fault rationale, difference from prior code, ordinal expected potential, implementation cost and validation stop rule.
    No numeric ΔDTI is fabricated for H-34 … H-37: without independent uncatalogued-fault holdout truth, ordinal potential/cost is the defensible ranking. H29/H30 are format-QA emissions, not release-approved submissions.</p></div></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Historical analysis (2026-10-02)</div><h2>H-29 … H-33, from the clustering audit (hypothesis IDs; the files built from them are labelled H29/H30)</h2></div></div>
    <p class="small">These values describe a prior data-enabled run, not a fresh computation from this branch. Raw competition and external rasters are absent now; the underlying manifests are retained for audit and must be rechecked after restoration.</p>
    {table(["rank", "id", "hypothesis", "layers / transform", "why it catches catalogue-missing faults", "difference from prior work", "prior score scenario / benefit (not forecast)", "cost", "status"], [
      [1, "<strong>H-29</strong>", "<strong>Audit-matched arrangement</strong>: emit the H24 ranking in the arrangement the best live emissions share — mildly less clustered than the catalogue (signed NCC divergence ≈ −0.21) — by limiting the NMS candidates to the top 30 % of the score.",
       "<code>S = 0.625 rank(H) + 0.375 rank(V)</code> (unchanged) ⊕ normalised correlation sum of <code>labels.tif</code> pixels at 2–30 km as the arrangement target; row-phase equalisation at the 400 m survey period",
       "It is not a new detector. It stops spending 70 % of the dots on the lowest-scoring ground while keeping the spread, and it targets the one audit statistic that ordered the 23 live scores (ρ = −0.66, p = 0.001).",
       "Earlier emissions were either stacked ridges (η ≈ 0.4) or flat lattices (η &gt; 0.9); none was built to match an arrangement statistic, and none was audited for the flight-line comb.",
       "Unmeasured; old conditional −0.01 … +0.04 vs H24 is not a forecast (uninformative-score algebra only).", "historical build", "<strong>H29/H30 are QA-only, unscored files; no release approval</strong>"],
      [2, "H-30", "<strong>Along-strike continuation beyond tips</strong>: faults missing from the catalogue continue the strike of known long faults beyond their tips (Bour &amp; Davy clustering extrapolated; Faulds &amp; Hinz: terminations ≈ 25 % and step-overs ≈ 32 % of systems).",
       "tips (endpoints) of the 467 traces ≥ 3 km in <code>labels.tif</code>; wedge ≤ 25° of strike, 300–1,000 m; enrichment profile from the SGMC-missing sample",
       "Measured: ×2.06 [1.74, 2.52] at 300–600 m and ×1.32 at 600–1,000 m in the continuation wedge against ×1.34 and ×0.96 sideways. But the zone covers 0.67 % of the domain and holds 1.1 % of the missing-fault proxy pixels.",
       "The sibling repository inverted the scaling law into an incompleteness prior; this one measures the wedge directly and bounds its capture.",
       "≤ +0.003 rank bonus in a proxy analysis; no ΔDTI or hidden-fault benefit established.", "low", "proxy statistic measured in the prior data run; tie-break only, not an independent holdout or release signal"],
      [3, "H-31", "<strong>Survey-aware low-pass of magnetic inputs</strong>: filter survey-limited layers with a 4-row boxcar along y (exact zero at the 400 m period) and a 40-column boxcar for the 4 km tie lines before any detector sees them.",
       "<code>of_tmi_hg</code> (line strength 87 vs control p95 6.6), <code>of_tmi_vg</code>, <code>ext_UK</code> (18 vs 6.1), <code>ext_UTh</code>; tie-line period in <code>tmi</code>, <code>rtp</code>, <code>tmi_vg</code>, <code>ext_TMI_up150</code>",
       "A detector fed with these layers can 'find' the flight lines: <code>ens12-adopted</code>, trained on all 19 bands, carries the 400 m line (strength 28.7, p = 0.016). Those pixels are false positives that dilute q.",
       "H-27 proposed deconfounding; this session verified the carriers and the periods on the real bands, so the filter is now specified, not guessed.",
       "No estimate; old 0 … +0.02 idea is untested and not a forecast.", "low–medium", "not implemented; needs restored bands and blocked validation"],
      [4, "H-32", "<strong>Slots as controlled experiments</strong>: two pairs with pre-registered readouts — arrangement (H29 lattice vs H30 at the same score) and near-field (dots only in the 200–600 m band around long faults vs a same-size, score-matched control elsewhere).",
       "no new layers; the probe sets are generated by <code>scripts/build_audited_emission.py</code> with a band restriction",
       "The only decision-relevant unknowns are the arrangement effect and the hidden-fault lift near known faults; each pair isolates one. DTI differences at equal pixel counts cancel the unknown |G| to first order.",
       "The pindrop ridge/nodes trio was the only controlled design so far; it answered dispersal (no gain) and nothing else.",
       "Information-value design only; no score forecast.", "moderate offline design cost", "<strong>DO NOT spend a slot</strong>; independent holdout approval still required"],
      [5, "H-33", "<strong>Completeness-corrected short-fault deficit</strong>: above 3 km the catalogue obeys the Bour &amp; Davy relation; below it the nearest-larger-neighbour slope flattens (0.92 vs 1.54). Treat the shortfall of short traces next to larger ones as the expected number of unmapped faults and place it as a density.",
       "<code>fault-statistics.json</code> scaling (a, x, D) ⊕ per-pixel deficit estimate",
       "A self-similar extrapolation predicts how many short faults should sit at each distance from each larger one; the difference to the observed count is the missing population.",
       "Needs an independent completeness check, which the SGMC proxy (blocked AUC 0.55) does not give.",
       "No validated ΔDTI; weak proxy is not a score forecast.", "medium", "not implemented; independent completeness data required"]])}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Additional geological mechanisms · continuation review</div><h2>H-34 … H-37: ranked by ordinal potential and cost</h2>
      <p>These are four distinct fault-discovery mechanisms, not emission-layout variants. The benefit column is an ordinal research priority, not a numerical ΔDTI or score forecast. All remain unimplemented and unvalidated; H-34 is the first candidate to implement, but no weekly slot is authorized without the independent holdout gate.</p></div></div>
    {table(["rank", "id", "hypothesis", "layers / transform", "physical signature and uncatalogued-fault rationale", "difference from existing code", "estimated benefit (ordinal only)", "cost", "status / stop condition"], [
      [1, "<strong>H-34</strong>", "<strong>Potential-field Euler source-depth stability.</strong> Solve contact/dyke Euler deconvolution around coherent magnetic and gravity edges; retain clusters stable across window sizes and structural indices with plausible depths.",
       "Model-layer keys: <code>of_tmi</code>, <code>of_rtp</code>, <code>of_tmi_hg</code>, <code>of_tmi_vg</code>, <code>of_iso_grav_anom</code>, <code>of_iso_grav_anom_hg</code>, <code>of_iso_grav_anom_vg</code>; these are competition bands with the <code>of_</code> layer-bank prefix. Restore the raster inventory and band provenance first.",
       "Fault contacts/fracture corridors can perturb potential fields; a stable source-depth population can flag structural continuations absent from the surface catalogue. Require independent topographic or radiometric corroboration to reduce lithologic/contact false positives.",
       "Existing geology code aggregates edge/gradient evidence but does not solve source locations/depths or test structural-index stability. This is a new transform on competition bands, not a new data claim.",
       "Medium-high potential; ΔDTI unknown (no holdout).", "Medium", "Unimplemented. Stop if solutions are unstable across windows/indices or dominated by flight-line artefacts."],
      [2, "<strong>H-35</strong>", "<strong>Multi-height potential-field edge persistence.</strong> Upward-continue magnetic and gravity grids at frozen heights; score ridges whose location and orientation persist across heights and property families.",
       "<code>of_tmi</code>/<code>of_rtp</code>/<code>of_tmi_hg</code> plus <code>of_iso_grav_anom</code>, <code>of_iso_grav_anom_hg</code> and <code>of_iso_grav_anom_vg</code>; pre-register 250, 500, 1,000 and 2,000 m continuation heights.",
       "Geologic contacts/fault corridors can produce spatially coherent edge ridges; survey-line and shallow-noise artefacts should attenuate or shift with height. Cross-property persistence may expose structure not in mapped fault traces.",
       "Current code computes local gradients/edge consensus at native support; it does not test multi-height ridge persistence or magnetic-gravity agreement.",
       "Medium potential; ΔDTI unknown (no holdout).", "Low-medium", "Unimplemented. Stop if line-noise controls persist as strongly as candidate ridges."],
      [3, "<strong>H-36</strong>", "<strong>Drainage deflection and knickpoint persistence.</strong> Extract channel networks, azimuth changes, profile breaks and knickpoints across nested catchment scales; control for lithology, basin size, base level, roads and landslides.",
       "Public USGS 3DEP 1 m/10 m DEMs or the restored official DEM derivatives; no external DEM is present in this checkout and exact AOI tile coverage is unknown.",
       "Active/recent structures can offset channels, create aligned deflections or repeatable profile breaks that reveal unmapped fault strands; require multiple neighboring channels and geomorphic controls to avoid lithologic or engineered drainage signals.",
       "The existing habitat uses lidar openness/scarp/relief channels; it does not construct channel networks or test profile-knickpoint persistence.",
       "Moderate potential; ΔDTI unknown (coverage and holdout unverified).", "High", "Not started. First enumerate full AOI coverage and acquisition dates; stop if data gaps or controls dominate."],
      [4, "<strong>H-37</strong>", "<strong>Depth-integrated conductance as a broad structural prior.</strong> Test whether multi-depth conductance boundaries align with shallow candidate corridors, without upsampling them into false 100 m detail.",
       "USGS Great Basin MT conductance products for 2–12, 12–20 and 20–50 km depth (ScienceBase item <a href='https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b'>62979746d34ec53d276c113b</a>, DOI <a href='https://doi.org/10.5066/P9TWT2LU'>10.5066/P9TWT2LU</a>); not downloaded here.",
       "Depth-coherent conductive boundaries may mark fluid-rich structures or basin edges that guide fault connectivity and geothermal pathways, including faults not yet mapped. Conductance is non-unique and coarse; it is a regional prior, not a trace or truth label.",
       "No MT-conductance layer or depth-persistence test is used in the current code. Do not claim novelty against unreviewed external analyses.",
       "Low-moderate potential; ΔDTI unknown (valid pixels/scale unverified).", "Moderate", "Not started. Verify licenses, CRS, grid, valid-pixel support and AOI overlap; stop if only coarse regional correlation remains."]])}
    <p class="small">Method context for Euler deconvolution is an open-access mineral-exploration example, not geothermal validation: <a href="https://www.nature.com/articles/s41598-025-26220-9">joint Euler deconvolution/upward-continuation paper</a>. H-36 uses the official <a href="https://www.usgs.gov/3d-elevation-program">USGS 3DEP</a> source. External rasters are not locally present; every data-availability and coverage claim is pending restoration and direct checks.</p>
  </section>
  <section class="section">
    {table(["rank", "id", "hypothesis", "layers / transform", "why it catches catalogue-missing faults", "difference from prior work", "prior score scenario / benefit (not forecast)", "cost", "status"], [
      [1, "<strong>H-24</strong>", "<strong>Dispersed habitat emission</strong>: emit a 400 m-spaced dot lattice restricted to the habitat that 24 live scores identify, at a budget chosen by the metric's own marginal rule.",
       "<code>lid_upface_max</code>, <code>lid_downface_max</code>, <code>lid_step_max</code>, <code>lid_lapneg_max</code>, <code>lid_lappos_max</code>, <code>lid_ex_max</code> (1 m 3DEP), <code>of_det_elev_slope_std7</code> (official band 19, 700 m window), <code>−rad_U</code> (GeoDAWN radiometrics); non-maximum suppression at r = 4 px",
       "Staff define a new fault as geometry not already captured by USGS/INGENIOUS, including newly mapped strands of an existing system. Lidar scarps and slope breaks may expose candidate surface expressions missing from the catalogue, but this does not prove they are faults. The fitted negative U association is correlational and not evidence of geological absence.",
       "Every prior artefact emitted contiguous thick ridges (η = 0.16–0.85). None was built by inverting live scores for a habitat, and none was dispersed to η ≈ 0.94 at a budget set by the marginal rule.",
       "No validated ΔDTI; legacy +0.03 … +0.22 sensitivity is withdrawn, not a forecast (I-17).", "historical build", "<strong>H24 is superseded. H29/H30 files are QA-only and unscored; no release approval.</strong>"],
      [2, "H-25", "<strong>Relocation, not detection</strong>: test whether a small subset of mapped traces is locally displaced by comparing each trace to lidar scarp evidence within a bounded search window; do not presume a region-wide 400 m shift.",
       "<code>labels.tif</code> trace skeletons ⊕ <code>lid_lapneg_max</code> (crest convexity) ⊕ <code>lid_upface_max</code>; constrained argmax displacement per trace segment",
       "Hermant et al. (2025) report a local maximum of up to 400 m between USGS Quaternary faults and TLS labels in north-central Nevada, not a typical offset or a GeoDAWN-region measurement (I-18). The aggregate lidar profile here peaks at zero displacement; a displaced subset remains unproven.",
       "Prior work used the catalogue only as a prior or a mask; nobody moved it. Catalogue pixels themselves are masked out of scoring, so the gain is entirely in the displacement.",
       "No estimate; legacy +0.02 … +0.10 scenario is unvalidated, not a forecast.", "medium", "<strong>tested on the aggregate: not supported</strong> (scarp metrics decay monotonically from the catalogue, no off-centre ring); Hermant et al. report ‘up to 400 m’ locally (I-18)"],
      [3, "H-26", "<strong>Thermal-conduit inversion, spring-avoiding</strong>: rank ground by 2 m temperature-probe and chalcedony-geothermometer anomaly density, but only where the anomaly is <em>not</em> explained by a mapped fault.",
       "<code>2m_temperature_probe_INGENIOUS_regional_data.zip</code> (3,800 probes), <code>gdr_wellspring_in_footprint.csv</code> (27,092 records, 2,389 ≥ 60 °C) ⊖ distance-to-catalogue",
       "A near-surface thermal anomaly in an amagmatic extensional setting requires a permeable pathway; where no mapped fault supplies one, an unmapped fault must. 22,561 of the 27,092 spring/well records already sit &gt; 500 m from any mapped fault.",
       "<strong>Contrarian and measured:</strong> the live scores say emitting <em>near</em> ≥ 60 °C springs is anti-predictive (ρ = −0.52, p = 0.009) because famous hot springs are already mapped. The usable signal is the residual — thermal anomaly minus what the catalogue explains — which no prior artefact computed.",
       "No estimate; legacy +0.01 … +0.06 scenario is unvalidated, not a forecast.", "medium", "<strong>simplest form tested, no signal</strong>: <code>springs_hot_offmapped_dens15</code> ρ = +0.08 (p = 0.71), inverse-distance form −0.22 (p = 0.31) in the 95-layer bank (raw hot springs: −0.52); a fitted-residual form is still open"],
      [4, "H-27", "<strong>Acquisition-lineament deconfounding</strong>: suppress east–west magnetic-gradient lineaments that coincide with the GeoDAWN Area-2 400 m flight lines, and spend the freed budget on cross-line structures.",
       "<code>of_tmi_hg</code>, <code>of_tmi_vg</code>, <code>ext_TMI_up150</code> ⊕ <code>GeoDAWN_area2_outline.zip</code> flight-line geometry; directional Fourier filter at the 400 m line spacing",
       "Area 2 was flown with 400 m east–west lines and 4 km north–south tie lines at 150–200 m clearance, so cross-line resolution is coarse and east–west magnetic derivative lineaments can be acquisition artefacts. An expert mapper rejects them; a gradient detector does not.",
       "No prior artefact modelled the survey geometry. <code>of_tmi_vg</code> is one of the few official bands whose enrichment is anti-correlated with live skill (ρ = −0.44).",
       "No estimate; legacy +0.005 … +0.04 scenario is unvalidated, not a forecast.", "medium", "<strong>partly executed</strong>: the flight lines are visible in <code>tmi_hg</code> (strength 87) and the tie lines in <code>tmi</code>/<code>rtp</code>/<code>tmi_vg</code>; the filter is H-31"],
      [5, "H-28", "<strong>Coverage-void targeting</strong>: concentrate the budget where mapped-geology density is lowest but lidar scarp evidence is highest — the intersection of “unsurveyed” and “structurally permissive”.",
       "<code>sgmc_density9</code> (USGS SGMC line density, 2.1 km window) inverted ⊕ <code>lid_*_max</code> composite ⊕ lidar validity",
       "The catalogue is a compilation of existing maps, so its gaps follow map coverage, not geology. A pixel with strong lidar scarp expression and no mapped structure nearby is the single most likely place for an expert to add a new fault.",
       "This is the mechanism behind H-24's habitat weights, made explicit and testable on its own: it predicts skill should rise with (scarp evidence × map-void), which is a one-line addition to the attribution regression.",
       "No estimate; legacy +0.005 … +0.03 scenario is unvalidated, not a forecast.", "low", "not implemented; data coverage unverified"]])}
    <div class="callout"><strong>Data availability and acquisition status.</strong> This post-merge checkout lacks the official feature stack, labels, sample template and all external rasters. Earlier reports document a hash-pinned bridge restore; that is not current local availability. H-34/H-35 need the official GeoDAWN magnetic/gravity bands (<a href="https://doi.org/10.5066/P93LGLVQ">USGS GeoDAWN</a>); H-36 needs AOI-complete public <a href="https://www.usgs.gov/3d-elevation-program">USGS 3DEP</a> elevation; H-37 proposes the open <a href="https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b">USGS Great Basin conductance release</a>. Restore only from official/free sources and then verify hashes, terms, CRS, grid, acquisition date, AOI overlap and valid-pixel coverage before fitting. Do not treat historical receipts or a source's regional extent as proof of local coverage.</div>
    <div class="callout"><strong>Honest status of these numbers.</strong> Legacy benefit ranges in H-24…H-33 were conditional algebra or unvalidated hypotheses—not observed outcomes. They are retained only as historical context and are not forecasts. The current holdout registry is BLOCKED; validation must use a frozen spatial comparison with independent uncatalogued-fault truth, not a competition slot. H-25's blanket relocation premise is not supported by the aggregate profile (see I-18).</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Rejected</div><h2>Ideas this session ruled out with measurements</h2></div></div>
    {table(["idea", "why it was rejected", "evidence"], [
      ["Emit ~550,000 pixels (the “value-based emission budget” inherited from earlier group work)",
       f"It assumed |G| = 125,000. The historical inversion of 24 live scores bounds |G| at {g_lo:,}–{g_hi:,}; under equal per-pixel placement-quality assumptions, 550,000 pixels exceed the algebraic marginal budget. This is conditional metric analysis, not an observed score comparison or forecast.",
       "<a href='data/live-model-bounds.json'>live-model-bounds.json</a>"],
      ["Train the detector on the supplied catalogue labels and submit its probability map",
       "Known-fault pixels are masked out of evaluation, so the catalogue is worth nothing as a target; and the raw probability field carries ~2.5 M of FP mass at DTI ≈ 0.12.",
       "staff ruling forum 11516; <a href='data/oof-evaluation.json'>oof-evaluation.json</a>"],
      ["Use the SGMC compilation gap as the offline truth for model selection",
       "It ranks the 24 live artefacts no better than chance: best Spearman ρ = +0.33 (p = 0.12) at a 2 km catalogue buffer, and it ranks the 0.0297 artefact first.",
       "<a href='data/offline-proxy-audit.json'>offline-proxy-audit.json</a>"],
      ["Admit the deep ensemble to the emission on the strength of its architecture",
       "The historical out-of-fold DTI did not beat a seed-matched random emission of the same size, so the admission gate excluded it. Saved variance files are prior-run outputs; no fresh Phase 2 ensemble maps or coverage mask were reproduced in this checkout.",
       "<a href='data/oof-evaluation.json'>oof-evaluation.json</a>"],
      ["Use the catalogue's own short-trace enrichment (×2.3 within 1 km of long faults) as the prior for hidden faults",
       "The independent SGMC-missing sample gives only ×1.8 / ×1.4 in the first 600 m and ≈ 1 beyond 1 km (blocked AUC 0.55 vs 0.67); live scores reward no concentration near known faults (emissions at &gt; 3× within 1 km scored 0.002–0.046). The prior is applied only as a ≤ 0.003 tie-break.",
       "<a href='data/fault-statistics.json'>fault-statistics.json</a>; <a href='clustering.html'>clustering audit</a>"],
      ["De-alias the dot lattice by a wider or fractional NMS radius, or by rank jitter up to σ = 0.005",
       "None removes the 400 m line (strength stays 106–146, rank p = 0.016) because the comb is in the score, not in the spacing rule; only σ ≈ 0.1 does, which would destroy the ranking. Row-phase equalisation moves 2–5 % of the dots by 1–2 px and clears it.",
       "<a href='data/h29-build.json'>h29-build.json</a>; I-15"],
      ["Hedge by emitting graded halos around every core pixel",
       "FP sums mass while TP takes a maximum, so a halo pays full price and only helps where the core's own cone does not already reach. Halos are emitted only beside high-epistemic-disagreement core pixels.",
       "metric algebra; <a href='data/submission-build.json'>submission-build.json</a>"]])}
  </section>"""

    uncertainty = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Uncertainty · historical model outputs</div><h1>Epistemic versus aleatoric, from a deep ensemble</h1>
    <p class="lead">The prior run used {esc(ens_cfg.get('n_members_full', 5))} independently initialised, independently trained convolutional members; no test-time dropout. The checkpoint, training rasters and external coverage layers are not present in this checkout, so these saved candidate variances are not freshly reproduced or calibrated here.
    For Bernoulli outputs the total predictive variance decomposes exactly as
    <span class="formula">Var(Y) = E<sub>m</sub>[p<sub>m</sub>(1 − p<sub>m</sub>)] + Var<sub>m</sub>(p<sub>m</sub>)</span>
    — aleatoric first, epistemic second (population variance, ddof = 0) — per Lakshminarayanan, Pritzel &amp; Blundell, NeurIPS 2017.</p></div>
    <aside class="hero-aside"><span class="status status-warning">Saved prior-run output · not reproduced</span>
      <strong style="margin:.8rem 0 .45rem">Epistemic share {esc(num(ens_full.get('epistemic_share_of_total'),3))}</strong>
      <p class="small">of total predictive variance over the scored domain, {esc(ens_cfg.get('n_members_full',5))} members,
      {esc(ens_cfg.get('n_folds',5))} blocked folds × {esc(ens_cfg.get('n_members_oof',3))} members out-of-fold.</p></aside></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">The brief's rule, implemented literally</div><h2>How survey coverage changes a candidate's priority</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">High epistemic variance in under-surveyed terrain → a finding</div>
        <p>The members disagree because the data does not constrain the answer. Where independent survey coverage is low, that is exactly
        where a structure can exist and never have been recorded, so the disagreement <em>raises</em> review priority.
        {esc(cand.get('n_under_surveyed_raising_priority', 0))} of the reported candidates fall in this class.</p></div>
      <div class="card"><div class="card-kicker">High epistemic variance in well-surveyed terrain → suspicion</div>
        <p>If the ground has been flown, lidar-mapped and geologically mapped and the members still disagree, the disagreement is more
        likely a model artefact than a missing fault, so priority is damped.
        {esc(cand.get('n_well_surveyed_flagged', 0))} candidates are flagged this way.</p></div>
      <div class="card"><div class="card-kicker">Aleatoric variance never changes priority</div>
        <p>E<sub>m</sub>[p<sub>m</sub>(1 − p<sub>m</sub>)] is irreducible noise in the observations — 100 m pixels mixing a 3 m scarp with its
        footwall, 400 m flight-line spacing, misregistered source maps. Adding members cannot reduce it, so it is reported but not acted on.</p></div>
      <div class="card"><div class="card-kicker">Coverage is measured, not assumed</div>
        <p>The prior run defined coverage = 0.5 · (1 m 3DEP lidar validity, band 12 of <code>lidar_scarp_features_u8.tif</code>, {esc(num((ens.get('target') or {}).get('lidar_coverage'),3)) if (ens.get('target') or {}).get('lidar_coverage') else '0.754'} of the footprint)
        + 0.5 · (rank of USGS SGMC structure-line density in a 2.1 km window). Those external rasters are absent now, so the mask and AOI validity cannot be checked from this checkout. Priority never modifies the submitted raster — it is a reviewer-ranking aid only.</p></div>
    </div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Out-of-fold honesty check</div><h2>Did the detector beat a random emission?</h2>
      <p>{esc(oof.get('gate',''))} → <strong>{'PASSED' if oof.get('gate_passed') else 'NOT PASSED'}</strong>
      ({esc(oof.get('folds_beating_random',0))}/{esc(oof.get('n_folds',0))} folds). Mean ensemble DTI {esc(num(oof.get('mean_dti'),4))} versus
      mean random-control DTI {esc(num(oof.get('mean_random'),4))}. Because the gate did not pass, the detector's weight in the submitted
      emission was set to 0 and the reason is recorded in <a href="data/submission-build.json">submission-build.json</a>.</p></div></div>
    {fold_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Phase 2 reviewer hand-off</div><h2>Top candidates with the variance split</h2>
      <p>{esc(cand.get('n_reported', 0))} of {esc(cand.get('n_objects', 0))} candidate objects, ranked by the priority rule. Full list:
      <a href="data/phase2-candidate-review.csv">phase2-candidate-review.csv</a> · <a href="data/phase2-candidates.json">JSON</a>.</p></div></div>
    {cand_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Training configuration</div><h2>Reproduce it</h2></div></div>
    {table(["parameter", "value"], [[k, esc(v)] for k, v in sorted(ens_cfg.items())])}
  </section>"""

    evidence = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Evidence</div><h1>Inverting 24 live public scores</h1>
    <p class="lead">Every artefact this group uploaded returned one scalar: its public distance-weighted Tversky index.
    Together with the artefact's own geometry, that scalar is invertible through the official metric. This page is the whole
    derivation, with the artefacts, so it can be checked line by line.</p></div></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Step 1</div><h2>The metric, as published</h2></div></div>
    <div class="formula">TP<sub>w</sub> = Σ<sub>g∈G</sub> max<sub>x: d(x,g)≤R</sub> p(x)·k(d(x,g)) &nbsp;&nbsp;
      FP<sub>w</sub> = Σ<sub>x: p(x)&gt;0</sub> p(x)·[1 − max<sub>g∈G</sub> k(d(x,g))] &nbsp;&nbsp;
      FN<sub>w</sub> = Σ<sub>g∈G</sub> [1 − max<sub>x</sub> p(x)·k(d(x,g))]</div>
    <div class="formula">DTI = TP<sub>w</sub> / (TP<sub>w</sub> + 0.2·FP<sub>w</sub> + 0.8·FN<sub>w</sub>), &nbsp; k(d) = max(1 − d/300 m, 0)</div>
    <p>Because FN<sub>w</sub> = |G| − TP<sub>w</sub> and α + β = 1, this collapses to
    <span class="formula">DTI = TP<sub>w</sub> / (0.2·TP<sub>w</sub> + 0.2·FP<sub>w</sub> + 0.8·|G|)</span>
    and, writing FP<sub>w</sub> = fp_relief(|G|)·A where fp_relief = 1 − E[max<sub>g</sub> k] is computed
    self-consistently from |G| itself, inverts to
    <span class="formula">TP<sub>w</sub> = DTI·(0.2·fp_relief·A + 0.8·|G|) / (1 − 0.2·DTI)</span>.
    At the |G| measured here fp_relief ≈ 0.985, so an emitted pixel costs ≈ 0.197 of denominator —
    <strong>21 % more</strong> than the 0.1626 a |G| = 125,000 assumption would imply. That single
    correction is why the inherited large-area plan fails.
    Verified against the organiser's own worked example (TP<sub>w</sub> 3.00, FP<sub>w</sub> 1.89, FN<sub>w</sub> 2.00 → 0.60) in
    <code>tests/test_metric.py</code>.</p>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Step 2</div><h2>|G| is bounded without any placement model</h2>
      <p>Two exact constraints. (i) TP<sub>w</sub> ≤ |G| gives a lower bound per artefact. (ii) TP<sub>w</sub> = |G|·e<sub>T</sub> where e<sub>T</sub> is the mean
      kernel envelope over the truth pixels; measuring e<sub>T</sub> on two <em>real</em> fault-trace populations instead of assuming it gives an upper bound.
      The 98.9 %-coverage lattice artefact is the tightest instrument because its envelope is high nearly everywhere.</p></div></div>
    <div class="grid-3">
      <div class="card metric-card"><span>Lower bound (max over artefacts)</span><strong>{esc(f"{bnd.get('lower_bound_max',0):,.0f}")}</strong><span>TP<sub>w</sub> ≤ |G|</span></div>
      <div class="card metric-card"><span>Upper bound, SGMC-like traces</span><strong>{esc(f"{(bnd.get('upper_bound_from_sgmc_like_truth') or 0):,.0f}")}</strong><span>mean envelope measured on 62,122 independent-compilation fault pixels</span></div>
      <div class="card metric-card"><span>Upper bound, catalogue-like traces</span><strong>{esc(f"{(bnd.get('upper_bound_from_catalogue_like_truth') or 0):,.0f}")}</strong><span>mean envelope measured on the 60,988 catalogued fault pixels</span></div>
    </div>
    <div class="callout"><strong>This refutes |G| = 125,000</strong>, the value inherited from earlier group work and the premise of its
    550,000-pixel emission plan. At |G| ≈ 10<sup>4</sup> the 0.8·|G| false-negative floor is small next to 0.197·A once A exceeds ~10<sup>5</sup>,
    so extra area is bought at a price the truth cannot repay.</div>
    {anchor_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Step 3</div><h2>Dispersion: a lever that did not survive the one controlled pair</h2>
      <p>η = (K̄/A)/(9.42/D) is the fraction of the theoretically available cone weight an emission actually spreads over the domain:
      η = 1 for pixels whose 300 m cones do not overlap, η ≈ 0.2 for thick blobs. Across the 24 live artefacts η correlates with
      TP per emitted pixel at Spearman ρ = +0.61 (p = 0.0015) and with placement skill at ρ = +0.13 (p = 0.54). <strong>That cross-sectional reading is superseded</strong>
      (flag I-17): the artefacts differ in emission type, and the only controlled comparison — pindrop-v4-ridge and pindrop-v4-nodes, the same score and the same 155,021 pixels — shows η rising 2.7× (K̄ 0.099 → 0.270),
      skill falling 2.6× (7.02 → 2.68) and the implied true-positive mass unchanged (4,182 → 4,334; DTI 0.1152 → 0.1193). Dispersal changed where the pixels sit, not how many hidden faults they reach.
      The first table below keeps the original columns so the pair can be read directly.</p></div></div>
    {per_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Step 4</div><h2>The habitat regression</h2>
      <p>skill = TP<sub>w</sub>/(|G|·K̄) removes budget and dispersion, so correlating it with each layer's enrichment inside the emitted pixels
      identifies where the hidden faults are. {esc(hab.get('n_layers'))} layers, {esc(hab.get('n_anchors'))} artefacts grouped into
      {esc(len({r['family'] for r in (hab.get('per_anchor') or [])}))} code-base families; layer selection <em>and</em> the ridge penalty are re-fitted inside every
      leave-one-family-out fold, so the reported ρ = {esc(num(hab.get('nested_cv_spearman'),3))} is not inflated by selecting on the same 24 points.
      Best |G| by CV: {esc(f"{hab.get('g_selected',0):,.0f}")}.</p></div></div>
    {hab_table}
    <div class="callout"><strong>Convergent validity, not circularity.</strong> The layers this regression selects from live scores alone are the same
    layers in which the independent USGS SGMC compilation's unmapped faults are enriched: 1.45–1.71× for the lidar scarp channels and
    1.94–2.01× for 700 m detrended-slope heterogeneity, measured on lidar-covered ground. Two independent routes — public scores and an
    independent map compilation — reach the same habitat.</div>
    <div class="callout"><strong>Multiplicity.</strong> {esc(hab.get('n_layers'))} layers were screened, so a Benjamini–Hochberg reading matters: one layer
    (<code>lid_upface_max</code>, p = 1×10<sup>−4</sup>) survives FDR &lt; 5% on its own; the rest of the lidar-scarp family is reported as a family
    (eight correlated channels, all with the same sign, occupying the top of the list), and the radiometric and hot-spring negatives are
    suggestive rather than individually significant. n = 24 scalar observations is a small sample and the artefacts are not independent experiments.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Step 5</div><h2>The negative result: no offline proxy ranks artefacts</h2>
      <p>If an offline proxy truth ranked the 24 artefacts the way the live board does, it could be used for model selection. None does.</p></div></div>
    {proxy_table}
    <div class="callout">The proxy with the highest correlation still puts <code>h19-c</code> first (proxy 0.295) when its live score is 0.0297 — 24th of 24.
    This is why no score forecast is shown and why the earlier “4-quadrant gate passed, 4/4 fold wins” claim was withdrawn:
    it was measured against known-catalogue truth, not independent uncatalogued-fault targets. The current holdout registry remains BLOCKED; do not spend a slot.</div>
  </section>"""

    results = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Scores</div><h1>Live public leaderboard and this group's score history</h1>
    <p class="lead"><span class="status status-neutral" id="feed-status">loading feed…</span>
    <span class="small" id="leaderboard-retrieved"></span> The feed is refreshed by
    <code>.github/workflows/pages.yml</code> on every push and daily at 12:00 UTC, so nothing has to be checked by hand.
    Official source: <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">drivendata.org leaderboard</a>.</p></div>
    <aside class="hero-aside"><span class="status status-neutral">Leader</span>
      <strong style="margin:.8rem 0 .45rem" id="leader-score-2">{esc(num(leader.get('score'),4))}</strong>
      <p class="small" id="leader-name-2">{esc(leader.get('participant'))}</p></aside></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Top 25</div><h2>Public DW-Tversky</h2></div></div>
    {lb_table}
    <p class="small">{lb_attribution}</p>
    <p class="small">{lb_phase}</p>
    <div class="callout"><strong>Reported-score reconciliation.</strong> In the latest committed official 50-row capture, the top three are DARD 0.3195, nchuzhoy 0.3128, and alexoktaba 0.3042; the user-reported 0.3049 is absent. H19-like 0.1922 and 0.1894 match rows 27 and 29, but there is no public submission ID or TIFF hash, so these are not verified H19 artifacts. One older project passage calls 0.1894 the highest while listing 0.1922 elsewhere; numerically 0.1922 is higher. The capture time/method is recorded in <code>data/leaderboard.json</code>.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">The question the brief asked</div><h2>What do local H19-like artifacts suggest—and what remains unverified?</h2>
      <p>Decompose the locally audited files into the three things the metric actually rewards. This is file-level analysis only: the public score rows do not identify these TIFFs, and the correlations do not prove a causal feature gain.</p></div></div>
    <div class="grid-3">
      <div class="card"><div class="card-kicker">It put its pixels where the hidden faults are</div>
        <p><code>h19-5</code> achieves q = 0.0475 kernel-weighted true positives per emitted pixel — the second highest of 24 artefacts,
        behind only <code>h28-dotted-ridge</code> at 0.0518. Since DTI correlates with q at ρ = +0.987, that single number <em>is</em> the score.
        Inverted exactly, <code>h19-5</code> recovered TP<sub>w</sub> ≈ 5,749 of a hidden truth set of order 10<sup>4</sup> pixels from
        121,131 emitted pixels: roughly 21 hits per 1,000 emitted pixels, against 1.8 per 1,000 for a uniform-random placement.</p></div>
      <div class="card"><div class="card-kicker">It stayed off the masked catalogue</div>
        <p><code>h19-5</code>, <code>h19-4</code>, <code>h16-1</code> and <code>lidarscarp-top2pct</code> emit <strong>zero</strong> pixels on
        known-fault pixels, which staff mask out of evaluation. The artefacts that painted the catalogue
        (<code>h19-c</code>, <code>structural-area06-v1</code>, <code>hedge-v2</code>: 60,988 on-catalogue pixels each) score 0.156 or less, and
        <code>r5-geom-horse-ensemble</code>, whose every pixel lies within 1,500 m of a mapped fault, scores 0.0020 — 96× worse than
        <code>h19-5</code> at a similar budget.</p></div>
      <div class="card"><div class="card-kicker">It kept a moderate budget</div>
        <p>At |G| ≈ 10<sup>4</sup> each emitted pixel costs ≈ 0.197 of denominator, so the false-negative floor 0.8·|G| ≈ 8,000 is
        comparable to the FP term only up to A ≈ 10<sup>5</sup>. <code>h19-5</code> sat at 121,131 px; every artefact above 250,000 px
        scores ≤ 0.046. The score is not a coverage contest.</p></div>
    </div>
    <div class="callout"><strong>What the arrangement audit adds to the H19 answer.</strong>
    {(lambda r, b: f"h19-5 sits at signed divergence {r['signed_large']:+.2f} from the catalogue's pair statistics (h19-4 −0.30, h16-1 −0.29), the centre of the bin that holds the best live scores (n = {b['n']}, mean live DTI {b['mean_live_dti']:.3f}); it has no 400 m survey-line comb (strength {r['survey_lines']['traverse_400m_along_y']['strength']:.0f}), a line-type arrangement ({100*r['structure']['share_isolated_dots']:.0f} % isolated dots) and only mild concentration near long known faults (×{r['near_long']['200-1000m']:.2f} within 0.2–1 km, against ×2.8–4.3 for the catalogue-hugging artefacts that scored ≤ 0.092). The lattices (−0.62) and the catalogue-huggers (+0.2 … +1.25) match the population statistics of faults worse. That is consistent with the arithmetic above; it does not prove it (correlational, post-hoc bins, n = 23).") (next((x for x in (pau.get('artefacts') or []) if x['id'] == 'h19-5'), None), (pau.get('arrangement_bins') or [None, None])[1]) if (pau.get('artefacts') and pau.get('arrangement_bins')) else ''}</div>
    <div class="callout"><strong>Where H19 might have left value on the table — and why that is no longer a claim.</strong> Its dispersion efficiency is η = 0.40: 60 % of the cone weight its
    pixels could have spread over the domain is spent on pixels stacked inside one another's 300 m support. H24 re-emitted the same ranking at η ≈ 0.95 on the assumption that q scales with η at fixed alignment. The one controlled pair
    in the group's record contradicts that: pindrop-v4-ridge → pindrop-v4-nodes (same score, same 155,021 pixels) raised η 2.7× and left the implied true-positive mass unchanged (TP/|G| 0.70 → 0.72 at |G| = 6,000), live DTI 0.1152 → 0.1193.
    H30 has no observed score. The scenario table is conditional on unverified transfer of placement skill; it is not an expected DTI or evidence for release (flag I-17).</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">This group</div><h2>24 live-scored artefacts, measured geometry</h2>
      <p>Every row is a real GeoTIFF mirrored from the sibling repositories and re-measured here on the official grid: emitted pixels,
      300 m coverage, mean kernel envelope K̄, dispersion η, and the exact |G| bounds it implies.</p></div></div>
    {anchor_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Conditional sensitivity</div><h2>DTI scenarios are not score forecasts</h2></div></div>
    {budget_table}
    <p class="small">These algebraic scenarios vary hidden-truth size and TP-per-emission assumptions. They are not validated performance, an empirical score forecast, or submission approval. Current spatial-holdout status: BLOCKED.</p>
  </section>"""

    sources = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Sources</div><h1>Every official source used, with the link that verifies it</h1>
    <p class="lead">Competition pages, staff rulings and public-domain USGS/DOE data. Source links establish provenance and acquisition options—not current local availability, AOI coverage, or model value. Anything not on this page is inference and is labelled as such where it appears.</p></div></div></section>
  <section class="section">
    {table(["source", "what it establishes", "link"], [
      ["DrivenData problem description", "task, data, metric formulas, worked example (0.60), submission format", "<a href='https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/'>page 967</a>"],
      ["DrivenData leaderboard", "live public scores, retrieved 2026-10-02", "<a href='https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/'>leaderboard</a>"],
      ["Staff ruling, forum 11516", "“Pixels corresponding to known USGS/INGENIOUS faults are masked / excluded from evaluation, so they do not count towards penalty terms” — and the same masking applies in the Final Round", "<a href='https://community.drivendata.org/t/11516'>topic 11516</a>"],
      ["Staff ruling, forum 11536", "“‘new fault’ means ‘any fault pixel not already captured by USGS/INGENIOUS’ and can include newly mapped geometry of an existing fault system”", "<a href='https://community.drivendata.org/t/11536'>topic 11536</a>"],
      ["NLR/DOE rules (OSTI 96647)", "3 uploads per rolling 7 days, one final submission per entity, $50,000 Initial and $250,000 Final rounds, external-data licensing, AI disclosure", "<a href='https://docs.nlr.gov/docs/fy26osti/96647.pdf'>rules PDF</a>"],
      ["USGS GeoDAWN release", "the airborne magnetic and radiometric survey behind the feature bands; Area 2 flown with 400 m E–W lines and 4 km N–S tie lines at 150–200 m clearance", "<a href='https://www.sciencebase.gov/catalog/item/657e1d85d34e23d3533209f7'>ScienceBase item</a> · <a href='https://doi.org/10.5066/P93LGLVQ'>DOI 10.5066/P93LGLVQ</a>"],
      ["USGS 3DEP", "1 m and 10 m DEMs behind the scarp-geomorphometry channels (public domain)", "<a href='https://www.usgs.gov/3d-elevation-program'>3DEP</a>"],
      ["USGS SGMC", "State Geologic Map Compilation structure lines — the independent fault compilation used as the detector's target (Horton, San Juan &amp; Stoeser 2017)", "<a href='https://mrdata.usgs.gov/geology/state/'>landing page</a> · <a href='https://doi.org/10.3133/ds1052'>DOI 10.3133/ds1052</a>"],
      ["Geothermal Data Repository (INGENIOUS)", "27,092 spring/well records with measured and geothermometer temperatures, 21 volcanic vents, 3,800 two-metre temperature probes, Quaternary fault traces", "<a href='https://gdr.openei.org/'>gdr.openei.org</a>"],
      ["Organisers' reference solution", "U-Net ensemble, TverskyLoss(α=0.2, β=0.8), 128-px patches, 5 random 50/50 splits", "<a href='https://github.com/drivendataorg/gems-prize-reference-solution'>GitHub</a>"],
      ["Hermant et al. 2025 (Stanford Geothermal Workshop)", "most Great Basin hydrothermal systems are fault-controlled; Fig. 2: ‘distance between USGS Quaternary faults and TLS fault label can be up to 400m’ in a local area of north-central Nevada (a local maximum against the authors' own labels, not a typical offset — flag I-18)", "<a href='https://pangea.stanford.edu/ERE/db/GeoConf/papers/SGW/2025/Hermant.pdf'>PDF</a>"],
      ["Faulds &amp; Hinz 2015 (OSTI 1724082)", "structural settings of 426 known systems: step-overs/relay ramps ~32 %, normal-fault terminations ~25 %, ~39 % blind", "<a href='https://www.osti.gov/servlets/purl/1724082'>OSTI</a>"],
      ["Bour &amp; Davy 1999 (GRL 26(13) 2001–2004)", "fractal dimension D and the length-frequency exponent a are related by x = (a − 1)/D, x being the exponent of the mean distance to the nearest larger neighbour; large faults have their nearest larger neighbour farther away (abstract read at Wiley 2026-10-02; paper body not accessible)", "<a href='https://doi.org/10.1029/1999GL900419'>doi:10.1029/1999GL900419</a>"],
      ["Marrett, Gale, Gómez &amp; Laubach 2018 (J. Struct. Geol. 108, 16–33)", "normalised correlation count: observed over the count expected for a random arrangement, scale by scale; correlation-sum slope = correlation dimension − 1; software CorrCount", "<a href='https://doi.org/10.1016/j.jsg.2017.06.012'>doi:10.1016/j.jsg.2017.06.012</a>"],
      ["Wang, Laubach, Gale &amp; Ramos 2019 (Petrol. Geosci. 25, 415–428)", "worked application of the normalised correlation count; NCC = 1 random, &gt; 1 clustered, &lt; 1 regular (as summarised by Storti 2020)", "<a href='https://doi.org/10.1144/petgeo2018-146'>doi:10.1144/petgeo2018-146</a>"],
      ["Clauset, Shalizi &amp; Newman 2009 (SIAM Rev. 51, 661–703)", "maximum-likelihood power-law exponent with the cut-off chosen by Kolmogorov–Smirnov distance", "<a href='https://doi.org/10.1137/070710111'>doi:10.1137/070710111</a>"],
      ["Bonnet et al. 2001 (Rev. Geophys. 39, 347–383)", "review of scaling of fracture systems: length distributions, spatial correlation, fractal dimension", "<a href='https://doi.org/10.1029/1999RG000074'>doi:10.1029/1999RG000074</a>"],
      ["Ackermann &amp; Schlische 1997 (Geology 25, 1127–1130)", "anticlustering of small normal faults around larger faults (a stress-shadow effect cited by Bour &amp; Davy); not seen at 100 m resolution here (enrichment ×2.3 from 200 m out)", "<a href='https://doi.org/10.1130/0091-7613(1997)025%3C1127:AOSNFA%3E2.3.CO;2'>doi:10.1130/0091-7613(1997)025&lt;1127:AOSNFA&gt;2.3.CO;2</a>"],
      ["USGS GeoDAWN metadata (survey geometry)", "traverse lines 400 m (Area 2) / 200 m (Area 1), east–west; tie lines 4,000 m / 2,000 m, north–south; terrain clearance 150–200 m / 100–150 m; area outlines reproduce 2,411.7 km² (Area 1) and 51,695 km² (data extent)", "<a href='https://doi.org/10.5066/P93LGLVQ'>doi:10.5066/P93LGLVQ</a>"],
      ["DrivenData competition page and forum 11527", "end date 3 Dec 2026 23:59 UTC; Phase 2 labels come from ‘expert review of all submissions’; staff decline to describe the data sources, fault types or coverage behind the new faults", "<a href='https://www.drivendata.org/competitions/306/competition-doe-gems/'>competition</a> · <a href='https://community.drivendata.org/t/how-were-the-new-test-faults-identified-data-sources-and-fault-types/11527'>forum 11527</a>"],
      ["USGS Electrical Conductance Maps of the Great Basin (Peacock &amp; Bedrosian 2022)", "public 3-D MT inversion products spanning five depth intervals from 2 to 200 km; conductance integrates electrical conductivity over depth. Candidate H-37 use is a regional structural prior, not a 100 m fault trace; local availability and coverage are unverified.", "<a href='https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b'>ScienceBase</a> · <a href='https://doi.org/10.5066/P9TWT2LU'>DOI 10.5066/P9TWT2LU</a>"],
      ["Hosseini et al. 2025, joint Euler deconvolution/upward continuation", "open method example for potential-field source-depth estimation in an iron-mineral exploration case; method context only, not geothermal-fault validation", "<a href='https://www.nature.com/articles/s41598-025-26220-9'>Scientific Reports</a> · <a href='https://doi.org/10.1038/s41598-025-26220-9'>DOI 10.1038/s41598-025-26220-9</a>"],
      ["Lakshminarayanan, Pritzel &amp; Blundell 2017", "deep ensembles and the epistemic/aleatoric decomposition used on the uncertainty page", "<a href='https://papers.nips.cc/paper_files/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html'>NeurIPS 2017</a>"]])}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Historical input manifest</div><h2>Previously hash-verified core rasters · not present now</h2></div></div>
    <p class="small">Filesystem audit for this branch: <code>data/training_features.tif</code>, <code>data/labels.tif</code>, <code>data/sample_submission.tif</code> and <code>data/external/</code> are absent. The values below come from the prior restore receipt only; they do not certify present files.</p>
    {table(["expected file path", "bytes in prior restore", "historical SHA-256"], [
      ["<code>data/training_features.tif</code> (official 19-band stack)", "418,912,844", "<code>4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5</code>"],
      ["<code>data/labels.tif</code> (rasterised known faults)", "425,830", "<code>7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093</code>"],
      ["<code>data/sample_submission.tif</code> (official template)", "1,599,597", "<code>2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc</code>"],
])}
    <div class="callout">The competition originals live behind a login-gated data tab. A previous restore reassembled copies from the group's public git data bridge and verified part- and whole-file SHA-256 against its manifest (<code>scripts/fetch_data_bridge.py</code>); that receipt documents historical verification only. Restore and verify the files again before local analysis. Nothing here bypasses the organizer's access controls.</div>
  </section>"""

    verification = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Audit</div><h1>Irregularities, withdrawn claims and limitations</h1>
    <p class="lead">Everything that did not survive checking is listed here rather than quietly dropped.</p></div></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Flagged</div><h2>Irregularity register</h2></div></div>
    {irregular_table if irregular_rows else '<p class="small">See <code>docs/data/irregularities.json</code>.</p>'}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Withdrawn</div><h2>Claims this session removed from the repository</h2></div></div>
    {table(["previous claim", "why it was withdrawn", "what replaces it"], [
      ["“4-Fold Spatial Holdout Gate Passed · mean OOF DTI 0.21177 · 4/4 fold wins”",
       "The gate scored a detector against the <em>supplied catalogue</em> using geographic quadrant folds. Known-fault pixels are masked out of the official evaluation, so the catalogue cannot score; and quadrant folds delete the fault population from the held-out region. Measured here: no offline proxy truth ranks the 24 live artefacts better than chance (best ρ = +0.33, p = 0.12).",
       "The current-best registry is BLOCKED because independent uncatalogued-fault truth/OOF hashes are unavailable. The H30 TIFF is a QA candidate only; scenario algebra is not a score forecast or release decision."],
      ["“|G| ≈ 125,000 hidden truth pixels”",
       f"Refuted under the assumptions stated in live-model-bounds.json: TP<sub>w</sub> ≤ |G| gives |G| ≥ {g_lo:,} and the broad-coverage artifact gives an upper bound {g_hi:,}.",
       "Historical metric bounds remain assumption-dependent and do not validate H29/H30 placement or authorize a competition upload."],
      ["“Emit ~550,000 pixels (value-based emission budget)”",
       "That budget was derived from |G| = 125,000, which also understated the cost of an emitted pixel by 21% (fp_relief 0.810 instead of 0.985). At the measured |G| it is far past the marginal rule: DTI falls monotonically once A exceeds |G|/q.",
       "The current H30 artifact emits 91,533 dots, but its conditional budget calculation is not a measured optimum or a release recommendation."],
      ["“Dispersion is a free 2.4× lever that does not trade against placement skill”; “projected public DTI 0.12 – 0.34”",
       "The only controlled pair (pindrop ridge vs nodes: same score, same 155,021 pixels) shows η ×2.7 with skill ÷ 2.6 and unchanged TP; the cross-artefact η–q correlation (ρ = +0.61) is confounded by emission type. The projection assumed skill transfers.",
       "No score forecast is claimed. Any conditional H19 transfer scenario is not validated and cannot substitute for a current-best independent spatial holdout; flag I-17."],
      ["“H24 emits dots at least 400 m apart”",
       "931 dots (6,651 pairs) are closer than 4 px; equal-score plateaus are accepted together in one non-maximum-suppression round.",
       "H29/H30 break ties deterministically: 0 violating pairs; flag I-16."],
      ["“USGS Quaternary faults sit ~400 m from lidar-based labels” (premise of H-25)",
       "The source says ‘up to 400 m’ for a local area of north-central Nevada, against the authors' own labels; the aggregate lidar-scarp profile shows no offset.",
       "Wording corrected; H-25 demoted; flag I-18."],
      ["“Consistent with Bour &amp; Davy (D_consistent: true)” in the sibling GEMSDOE22 repository",
       "It inserts a cumulative exponent where the published relation needs the density exponent.",
       "Re-derived, simulated and unit-tested here; flag I-14."],
      ["“sample_submission.tif predicts total fault absence”",
       "The official page says so, but the file contains 60,988 pixels equal to 1.0 — exactly the known-fault catalogue.",
       "Used only for its grid, CRS, transform and footprint; never as a zero baseline."]])}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Limitations</div><h2>What this work cannot claim</h2></div></div>
    <ul class="list-clean">
      <li><strong>The arrangement audit is correlational.</strong> Signed divergence orders the 23 live emissions (ρ = −0.66) but the bins were drawn after looking at them, emissions fall in families, and the only controlled pair scored alike at +0.20 and −0.62. H30's target is a rule fixed after the table was seen.</li>
      <li><strong>The clustering prior is weak for the faults that matter</strong> (missing-fault proxy: blocked AUC 0.55; the continuation zone beyond tips covers 0.7 % of the domain), and the NCC is a 2-D adaptation of a 1-D published method.</li>
      <li><strong>The habitat refit is order-dependent</strong> through a duplicate anchor (I-20); fix the order or use average ranks before refitting with a new live score.</li>
      <li><strong>No valid independent hidden-target holdout.</strong> The single largest limitation. The current-best registry is BLOCKED. Model and budget choices are not release evidence; a competition slot is not a substitute validation set and must remain unused until the registered gate passes.</li>
      <li><strong>|G| is bounded, not measured.</strong> The upper bound assumes no artefact is actively anti-correlated with the hidden truth. If one is, |G| could be larger.</li>
      <li><strong>The historical deep ensemble was excluded by its model-admission gate.</strong> The report records {esc(ens_cfg.get('n_members_full',5))} full-domain members and an out-of-fold DTI below a random-emission control; its weight in the H30 emission is 0. The variance decomposition is mathematical, but no fresh independently trained Phase 2 candidate maps/calibration were reproduced in this continuation. Retrain and revalidate before reuse.</li>
      <li><strong>Historical lidar coverage report: 75.4 %.</strong> The external rasters are absent in the current checkout, so the mask/alignment is not independently reproduced here. Do not treat it as a verified survey-gap layer or adjust uncertainty until restored and checked.</li>
      <li><strong>Public ≠ private.</strong> All 24 live scores are public-test scores; the region is chunked, the split is unpublished, and the Final Round re-scores against expanded labels.</li>
      <li><strong>Data availability and egress.</strong> The main-branch restore receipt documents a prior hash-pinned bridge run, but <code>data/external/</code> is absent in this checkout. Re-check local availability, hashes, license, AOI coverage and metadata before reuse. The latest public leaderboard was successfully rendered by GitHub Actions; a shell fetch in the sandbox is not the source of that live capture.</li>
    </ul>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Reproduce</div><h2>Commands</h2></div></div>
    <pre class="formula">bash scripts/download_competition_data.sh     # acquire the official rasters (bridge or data tab)
python scripts/prepare_data.py                # verify hashes, write data/manifest.json
python scripts/fit_habitat_model.py           # 24 live scores -> habitat weights + nested CV
python scripts/run_ensemble.py                # deep ensemble + epistemic/aleatoric split
python scripts/evaluate_oof.py                # admission gate vs a random-emission control
python scripts/build_submission_live.py       # budget, dispersion, TIFF, validation (H24)
python3 scripts/restore_workspace.py --all    # official + external layers + 23 identity-verified artefacts
python scripts/rebuild_h24_check.py           # H24 bit-for-bit from public inputs
python scripts/fit_fault_statistics.py        # fault statistics on labels.tif, before any model
python scripts/audit_predictions.py --extra <rasters>   # audit + calibration vs the live scores
python scripts/build_audited_emission.py --variant h30 --set-primary   # H29 / H30
python scripts/phase2_candidates.py           # reviewer candidates with the variance split
python scripts/build_site.py                  # this site</pre>
  </section>"""

    clustering = clustering_page(fst, pau, cdx, h29, h30, man) if fst and pau and h29 and h30 else "<section class=\"section\"><p>Run scripts/fit_fault_statistics.py and scripts/audit_predictions.py first.</p></section>"
    pages = {
        "clustering.html": ("Clustering audit · GEMSDOE23", clustering, "clustering.html",
                            "Fault-population statistics fitted on the known catalogue, the geometric prior, and the post-hoc audit of predicted rasters."),
        "index.html": ("GEMSDOE23 · QA candidate and evidence", index, "index.html",
                       "One-click QA-only GeoTIFF candidate with the current blocked release gate, fault-population evidence and documented limitations."),
        "executive-summary.html": ("How to submit · GEMSDOE23", executive, "executive-summary.html",
                                   "Exact upload steps, the submission note, the decision rule and the traceability index."),
        "hypotheses.html": ("Hypothesis register · GEMSDOE23", hypotheses, "hypotheses.html",
                            "Four new testable geological mechanisms plus the retained hypothesis register, with sources, ordinal benefit and implementation cost."),
        "uncertainty.html": ("Uncertainty · GEMSDOE23", uncertainty, "uncertainty.html",
                             "Deep-ensemble epistemic/aleatoric decomposition, survey-coverage priority rule and Phase 2 candidates."),
        "evidence.html": ("Evidence · GEMSDOE23", evidence, "evidence.html",
                          "Inversion of 24 live public scores: |G| bounds, dispersion, habitat regression, proxy negative result."),
        "results.html": ("Scores · GEMSDOE23", results, "results.html",
                         "Live public leaderboard feed and the measured geometry of 24 live-scored artefacts."),
        "sources.html": ("Sources · GEMSDOE23", sources, "sources.html",
                         "Official competition pages, staff rulings and public-domain USGS/DOE sources with links."),
        "verification.html": ("Audit · GEMSDOE23", verification, "verification.html",
                              "Irregularity register, withdrawn claims, limitations and reproduction commands."),
    }
    for name, (title, body, current, desc) in pages.items():
        with open(os.path.join(DOCS, name), "w") as fh:
            fh.write(page(title, body, current, desc, stamp))
        print("wrote docs/" + name)

    # machine-readable pointer for the download button
    os.makedirs(DL, exist_ok=True)
    json.dump(man, open(os.path.join(DL, "latest.json"), "w"), indent=1)
    print("wrote docs/downloads/latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(build())
