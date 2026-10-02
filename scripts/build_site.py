#!/usr/bin/env python3
"""Regenerate the whole static site from the JSON evidence in docs/data.

    python scripts/build_site.py

HTML is generated from dated evidence records plus explicitly labelled policy text. Historical
records are not silently treated as current or independently reproduced.
The Pages workflow may refresh the public snapshot, but generated pages preserve capture dates,
time precision, source caveats, and historical-vs-current labels. They are not a substitute for checking the live
competition page or re-running model validation.
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
       ("hypotheses.html", "New hypotheses"), ("uncertainty.html", "Uncertainty"),
       ("evidence.html", "Evidence"), ("results.html", "Scores"),
       ("sources.html", "Sources"), ("verification.html", "Audit")]


def evidence_stamp() -> str:
    """Newest `generated_utc` across the evidence records.

    Deliberately not the wall clock: `build_site.py` must be idempotent, because CI fails
    when the committed site differs from a freshly generated one. If the latest public-board
    capture has date-only precision, do not imply an exact time by borrowing a timestamp from
    an unrelated validation record.
    """
    stamps = []
    date_only = []
    for name in os.listdir(DATA) if os.path.isdir(DATA) else []:
        if not name.endswith(".json"):
            continue
        try:
            rec = json.load(open(os.path.join(DATA, name)))
        except Exception:
            continue
        for key in ("generated_utc", "retrieved_utc", "reviewed_utc"):
            value = rec.get(key) if isinstance(rec, dict) else None
            if isinstance(value, str):
                if len(value) == 10 and value[4] == "-" and value[7] == "-":
                    date_only.append(value)
                else:
                    stamps.append(value)
    if date_only:
        return max(date_only) + " UTC"
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


def build():
    stamp = evidence_stamp()
    man = j("submission-manifest.json", {}) or {}
    bld = j("submission-build.json", {}) or {}
    oof = j("oof-evaluation.json", {}) or {}
    ens = j("ensemble-report.json", {}) or {}
    cand = j("phase2-candidates.json", {}) or {}
    lb = j("leaderboard.json", {}) or {}
    irreg = j("irregularities.json", {}) or {}
    prim = man.get("primary", {}) or {}
    comp = man.get("compatibility", {}) or {}
    release_decision = man.get("release_decision", {}) or {}
    format_preflight = prim.get("format_preflight_passed")
    if format_preflight is None:
        format_preflight = bool((man.get("validation", {}).get("nan", {}) or {}).get("passed"))
    release_status = release_decision.get("status", "BLOCKED")
    release_approved = (
        release_status in {"APPROVED", "APPROVED_BY_SPATIAL_HOLDOUT_GATE"}
        and prim.get("release_approved") is True
        and prim.get("ok_to_upload") is True
    )
    release_reason = release_decision.get(
        "reason", "No verified spatial holdout approval is recorded. Format checks alone do not release a submission."
    )
    geo = bld.get("geometry", man.get("geometry", {})) or {}
    note = "GEMSDOE23 QA ONLY — not for upload | " + str(prim.get("name", "candidate")) + " | sha256 " + str(prim.get("sha256", ""))[:8]
    rows_lb = sorted((lb.get("rows") or []), key=lambda r: r.get("rank", 999))
    leader = rows_lb[0] if rows_lb else dict(participant="—", score=0)
    capture_method = str(lb.get("capture_method", "method not recorded")).strip().rstrip(".")
    fname = prim.get("name", "(not built yet)")
    fsha = prim.get("sha256", "")[:16]
    fbytes = prim.get("bytes", 0)
    download_href = "downloads/" + fname if prim else "#"
    eta = geo.get("eta")
    area = geo.get("area")
    dl_block = f"""
  <section class="section" id="download">
    <div class="section-head">
      <div><div class="eyebrow">First-page download · template format preflight only</div>
      <h2>Downloadable QA candidate</h2></div>
      <span class="status {'status-ok' if format_preflight and release_approved else 'status-warning'}">{'Format preflight PASS · release ' + esc(release_status) if format_preflight else 'Format preflight failed'}</span>
    </div>
    <div class="download-card">
      <div>
        <h3>H24 · research candidate only</h3>
        <p>The file is provided for format QA and inspection, not as a recommendation or approved submission. Its geological placement has not passed a current-best spatial holdout; historical score projections are intentionally not repeated here.</p>
        <div class="file-meta">
          <span>Filename: <code>{esc(fname)}</code></span>
          <span>3292 × 3730</span><span>single-band float32</span><span>EPSG:32611</span><span>100 m pixels</span>
          <span>values in [0, 1]</span><span>NaN outside the footprint</span>
          <span>{esc(f'{fbytes/1e6:.2f}' if fbytes else '0')} MB</span><span>SHA-256 {esc(fsha)}…</span>
          <span>candidate mass {esc(f'{area:,.0f}' if area else '—')} px</span>
          <span>dispersion efficiency η = {esc(num(eta,3)) if eta else '—'}</span>
        </div>
        <div class="callout"><strong>Do not upload or spend a weekly slot.</strong> {esc(release_reason)}</div>
      </div>
      <div class="button-row">
        <a class="button" href="{esc(download_href)}" download>Download QA candidate .tif ↓</a>
        <a class="button button-secondary" href="data/submission-manifest.json">Candidate manifest</a>
        <a class="button button-secondary" href="data/current-holdout-best.json">Holdout release status</a>
        <a class="button button-secondary" href="{esc('downloads/' + comp.get('name','')) if comp else '#'}" download>All-finite QA variant</a>
      </div>
    </div>
    <div class="copy-row" aria-label="Candidate note (not for upload)" style="margin-top:1rem">
      <input id="submission-note" readonly value="{esc(note)}">
      <button type="button" data-copy-target="submission-note">Copy candidate note</button>
    </div>
  </section>"""

    # Historical score-inversion/projection tables are deliberately not rendered as current evidence.

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
    reported_score_rows = []
    for label, score in [("User-reported current score", 0.3049), ("H19-5 reported score", 0.1922), ("H19-4 reported score", 0.1894)]:
        match = next((r for r in rows_lb if abs(float(r.get("score", -1)) - score) < 0.00005), None)
        reported_score_rows.append([label, num(score, 4),
                                    (str(match.get("rank")) if match else "no matching row"),
                                    (esc(match.get("participant", "—")) if match else "—"),
                                    "Score match only; not TIFF/team attribution" if match else "Not present in this dated snapshot"])
    reported_score_table = table(["reported value", "score", "snapshot rank", "displayed participant", "interpretation"], reported_score_rows)

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
        <div class="eyebrow">DOE GEMS Prize · DrivenData #306 · evidence records of {esc(stamp)}</div>
        <h1>Spatial validation before submissions.</h1>
        <p class="lead">A first-page H24 GeoTIFF is available for format QA, but it is <strong>not approved for a competition slot</strong>.
        Its hard template checks pass; no reproducible candidate-versus-current-best spatial holdout is registered. The organizer says
        the discovery target is expert-mapped fault geometry missing from the public catalogue—not the catalogue labels themselves.</p>
        <div class="button-row" style="margin-top:1.25rem">
          <a class="button" href="{esc(download_href)}" download>Download QA candidate .tif ↓</a>
          <a class="button button-secondary" href="executive-summary.html">Release gate and submission guide →</a>
        </div>
      </div>
      <aside class="hero-aside">
        <span class="status status-warning">Release gate {esc(release_status)}</span>
        <strong style="margin:.8rem 0 .45rem">No slot is authorized</strong>
        <p class="small">Official public leaderboard snapshot: <strong id="leader-score">{esc(num(leader.get('score'),4))}</strong>
        (<span id="leader-name">{esc(leader.get('participant'))}</span>). Retrieved {esc(lb.get('retrieved_utc','date not recorded'))}; see score caveats below.</p>
        <a href="verification.html">Why release is blocked →</a>
      </aside>
    </div>
  </section>
{dl_block}
  <section class="grid-3" aria-label="Status">
    <div class="card metric-card"><span>Official footprint</span><strong>5,167,373 px</strong><span>3292×3730, EPSG:32611, 100 m; labels are incomplete, not negatives</span></div>
    <div class="card metric-card"><span>Data ready locally</span><strong>19 bands</strong><span>Core rasters and prepared arrays are present; external feature products are absent from this checkout</span></div>
    <div class="card metric-card"><span>Current holdout-best record</span><strong>BLOCKED</strong><span>No validated independent spatial comparison is registered; do not spend a submission slot</span></div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Evidence boundary</div><h2>What a leaderboard score can—and cannot—tell us</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">H19 values are score matches, not verified attribution</div>
        <p>The reported H19-5 0.1922 and H19-4 0.1894 match official public rows at ranks 26 and 28, but the board does not expose file hashes or submission IDs. The H19 page itself calls those TIFFs “not live-scored yet”. The four-line geological rationale and spatial-holdout results remain self-reported and unreproduced in this checkout.</p></div>
      <div class="card"><div class="card-kicker">No causal ablation is available</div>
        <p>A scalar public score cannot isolate the gain from fault-length scaling, thermal residuals, lidar morphology, or geophysical edges. To claim mechanism, reproduce artifacts and compare controlled ablations on the same frozen spatial holdout against the registered current best.</p></div>
    </div>
    <p><a href="hypotheses.html">See four distinct, ranked hypotheses and their holdout status →</a></p>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Official public board</div><h2>Current standings</h2>
      <p><span class="status status-neutral" id="feed-status">Dated snapshot · captured from official page by hand</span> <span class="small" id="leaderboard-retrieved">Snapshot date: {esc(lb.get('retrieved_utc','not recorded'))}</span>
      Manual dated public snapshot; check the official source for newer rows. <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">Official source</a>.</p></div></div>
    {lb_table}
    <p class="small">{lb_attribution}</p>
    <p class="small">{lb_phase}</p>
  </section>"""

    executive = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Executive summary · release gate {esc(release_status)}</div>
    <h1>Candidate QA, not submission approval.</h1>
    <p class="lead">The available GeoTIFF passes hard format checks against the official template. The current-best spatial holdout is blocked,
    so <strong>do not upload this candidate or spend a weekly slot</strong>. Review the gate and exact future upload steps below.</p></div>
    <aside class="hero-aside"><span class="status status-warning">{'Format preflight PASS' if format_preflight else 'Format preflight failed'} · release {esc(release_status)}</span>
      <strong style="margin:.8rem 0 .45rem">{esc(fbytes/1e6 if fbytes else 0)} MB · {esc(fsha)}…</strong>
      <p class="small">Single band, float32, EPSG:32611, 3292×3730, 100 m, values in [0,1], NaN outside — template checked. This is file-format evidence only, not placement/score validation.</p></aside></div></section>
{dl_block}
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Only after approval</div><h2>Future upload steps</h2></div></div>
    <div class="callout"><strong>Current status: do not upload.</strong> {esc(release_reason)} The visible download is only for QA and inspection.</div>
    <ol class="list-clean">
      <li><strong>Wait for a new release artifact.</strong> It must be uniquely named and produced by <code>scripts/build_submission.py</code> only after a passing spatial holdout against the exact registered current-best OOF map.</li>
      <li><strong>Run the final preflight</strong> with <code>scripts/validate_submission.py --template data/sample_submission.tif --prediction &lt;release.tif&gt;</code>. Confirm every hard check passes and compare the reported SHA-256 with its manifest.</li>
      <li><strong>Sign in</strong> at <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/">the official competition page</a> and open the Submissions tab for the registered team/entity.</li>
      <li><strong>Upload the single-band <code>.tif</code> unchanged</strong>; do not round-trip it through GIS software. Paste the release manifest’s short, unique note and retain the artifact SHA-256.</li>
      <li><strong>Record the returned public score</strong> with its retrieval date and artifact hash. Keep public, private Initial Round, and expert-updated Final Round results separate.</li>
    </ol>
    <div class="callout"><strong>Range-error fallback.</strong> The all-finite candidate variant writes 0 outside the footprint with nodata=0 and passes the template hard checks; this may help if a platform checker evaluates every cell before masking. The uploader has not been tested here. Use a fallback only after a release is approved and its exact TIFF is preflighted.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Decision gate</div><h2>Why no slot is authorized</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">Current holdout best is not registered</div>
        <p><code>data/current-holdout-best.json</code> is BLOCKED. The prior known-catalogue validation report is WITHDRAWN, and self-reported H19 holdout results cannot be reproduced from this checkout. A public score projection or a format pass cannot substitute for a candidate-versus-current-best spatial test.</p></div>
      <div class="card"><div class="card-kicker">Release builder fails closed</div>
        <p><code>scripts/build_submission.py</code> requires a verified four-fold current-best record, matching OOF hashes and a passing candidate comparison. <code>scripts/build_submission_live.py</code> is only a candidate/preflight builder and labels its files not approved.</p></div>
      <div class="card"><div class="card-kicker">Public is not private or final</div>
        <p>The official problem page describes separate public/private scoring and later expert review. Public rank is not hidden Initial Prize Round performance; the same selected submission is later rescored against expanded expert labels. See the <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/">official task page</a> and <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/rules/">rules</a>.</p></div>
      <div class="card"><div class="card-kicker">Attribution remains unresolved</div>
        <p>The official board rows at 0.1922 and 0.1894 do not identify the H19 TIFFs. The H19 page itself calls them not live-scored yet. No causal H19 feature contribution is claimed.</p></div>
    </div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Traceability</div><h2>Every number on this page</h2></div></div>
    {table(["file", "what it records"], [
        ["<a href='data/submission-manifest.json'>submission-manifest.json</a>", "QA candidate filename/hash and explicit BLOCKED release decision"],
        ["<a href='data/current-template-validation.json'>current-template-validation.json</a>", "current formal TIFF-to-template hard checks; format evidence only"],
        ["<a href='data/current-holdout-best.json'>current-holdout-best.json</a>", "release registry; BLOCKED until a reproducible current-best spatial holdout exists"],
        ["<a href='data/validation-report.json'>validation-report.json</a>", "historical known-catalogue comparison; WITHDRAWN and never a release gate"],
        ["<a href='data/irregularities.json'>irregularities.json</a>", "audit flags, attribution conflicts, and documented limitations"],
        ["<a href='data/ensemble-report.json'>ensemble-report.json</a>", "historical ensemble report; not reproduced in the current checkout"],
        ["<a href='data/phase2-candidates.json'>phase2-candidates.json</a>", "historical Phase 2 candidate uncertainty report; retrain before reuse"]])}
  </section>"""

    hypotheses = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">New geological hypotheses · not release-approved</div>
    <h1>Four distinct tests, ranked by ordinal DTI potential and cost</h1>
    <p class="lead">Expected potential is a reasoned ranking, not a score forecast. No numeric ΔDTI is reported because there is no
    reproducible current-best spatial holdout in this checkout. Each candidate is checked against the existing code and prior-work register.</p>
  </div></div></section>
  <section class="section">
    {table(["rank", "id", "hypothesis and physical signature", "layers / transform", "why it may find uncatalogued faults", "difference from existing work", "expected DTI potential", "cost / status"], [
      [1, "<strong>H-29</strong>", "<strong>Potential-field Euler source-depth stability.</strong> Solve contact-like / dyke-like Euler deconvolution around coherent magnetic and gravity edges; retain only stable, plausible-depth solutions across windows/structural indices.",
       "Existing `tmi`, `rtp`, `tmi_hg`, `tmi_vg`, `iso_grav_anom`, `iso_grav_anom_hg`, `iso_grav_anom_vg`; no external data. Method context: <a href='https://www.nature.com/articles/s41598-025-26220-9'>open-access Euler study</a> (method transfer only).",
       "Buried basement offsets can juxtapose rocks with magnetic susceptibility/density contrasts yet leave weak surface scarps; stable source boundaries can focus expert review in covered terrain.",
       "Current geophysical code combines edge/gradient evidence but does not solve Euler source locations/depths or test structural-index stability. This is a new transform on existing bands.",
       "Moderate-to-high potential; sign and ΔDTI unknown until holdout.",
       "Medium; implement, synthetic-test, then spatial holdout. Not implemented."],
      [2, "<strong>H-30</strong>", "<strong>Multi-height potential-field edge persistence.</strong> Upward-continue magnetic and gravity grids at frozen heights; score ridges whose location/orientation persist across height and across property families.",
       "`tmi`/`rtp`, `tmi_vg`, `iso_grav_anom`, `iso_grav_anom_vg` and horizontal gradients; FFT continuation with mask/boundary controls; no new data.",
       "Deeper/regional fault-related contacts may remain coherent after shallow, short-wavelength noise is attenuated; concordance can reduce single-band lineament artifacts.",
       "Prior code refers to one fixed 150 m TMI-up layer and a multiband edge consensus; this tests scale persistence rather than a single continuation height.",
       "Moderate potential; no numeric ΔDTI.",
       "Low-to-medium; implement with sensitivity checks. Not implemented."],
      [3, "<strong>H-31</strong>", "<strong>Drainage deflection and knickpoint persistence.</strong> Extract channel network/profile breaks and reach azimuth anomalies; control for basin size, lithology, base level, roads, landslides and DEM seams.",
       "USGS 3DEP bare-earth 1 m DEM where available, 10 m fallback; compare channel anomalies to potential-field corridors. <a href='https://www.usgs.gov/3d-elevation-program/about-3dep-products-services'>Official free 3DEP products/coverage tools</a>.",
       "Young or active faults can deflect channels, offset terraces, or produce persistent aligned profile breaks even where a local scarp is weak.",
       "Existing H19/code emphasis is openness, local relief and scarp morphology; this targets network topology and longitudinal profiles.",
       "Moderate, coverage-dependent potential; no numeric ΔDTI.",
       "High; public source obtainable, exact AOI tile coverage/quality not confirmed. Not implemented."],
      [4, "<strong>H-32</strong>", "<strong>Depth-integrated conductance as a regional prior.</strong> Test native-resolution 2–12 km and 12–20 km conductance boundaries aligned with shallow candidate corridors; do not upscale into false 100 m detail.",
       "USGS Great Basin conductance GeoTIFFs listed at <a href='https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b'>ScienceBase item 62979746d34ec53d276c113b</a>, DOI 10.5066/P9TWT2LU; not downloaded.",
       "A deep conductive body may be compatible with fluid/alteration pathways that continue beyond mapped surface traces, providing a broad review prior rather than a fault trace.",
       "Adds an independent electrical-conductivity observation not established in the current 19-band transforms or the H19 hub's four named evidence lines.",
       "Low-to-moderate potential; major scale/nonuniqueness risk.",
       "Medium-to-high; public files listed, license/CRS/resolution/AOI overlap need review. Not implemented."]])}
    <div class="callout"><strong>Top-candidate holdout state: BLOCKED.</strong> H-29 is ranked first because its source bands are already local and its depth-estimation mechanism is distinct from the current edge consensus. It has not been implemented or validated. `data/current-holdout-best.json` has no verified incumbent OOF artifact, and the old catalogue-label validation report is withdrawn. A spatial holdout cannot be reported as passed until an independent target and exact current-best comparator are available. Do not spend a weekly submission slot.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Validation plan</div><h2>Pre-register before coding</h2></div></div>
    <ol class="list-clean">
      <li>Freeze candidate source, structural-index/window settings, plausible depth bounds, score transform, output budget, and spatial folds.</li>
      <li>Keep candidate OOF predictions blind to each held-out block; compare against the exact registered current-best OOF map on the same independent uncatalogued-fault truth.</li>
      <li>Publish fold deltas, mean delta, win count, buffer sensitivity, prediction/config/truth hashes, and failed/ambiguous runs.</li>
      <li>Only a passing strict release gate can authorize building a competition TIFF; format checks follow and do not replace the geological holdout.</li>
    </ol>
  </section>"""

    uncertainty = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Uncertainty · historical report</div><h1>Epistemic and aleatoric uncertainty—retrain before reuse.</h1>
    <p class="lead">The mathematical decomposition is exact for an independently trained Bernoulli deep ensemble:
    <span class="formula">Var(Y) = E<sub>m</sub>[p<sub>m</sub>(1 − p<sub>m</sub>)] + Var<sub>m</sub>(p<sub>m</sub>)</span>.
    Historical JSON records five full-domain members and blocked out-of-fold runs, but model checkpoints and some input layers are absent from this checkout;
    this continuation did not reproduce those predictions. See the member-provenance and coverage caveat below.</p></div>
    <aside class="hero-aside"><span class="status status-warning">Historical values · not re-run here</span>
      <strong style="margin:.8rem 0 .45rem">Recorded epistemic share {esc(num(ens_full.get('epistemic_share_of_total'),3))}</strong>
      <p class="small">This number is quoted from <code>data/ensemble-report.json</code>, not newly generated or verified against checkpoints in this checkout.</p></aside></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">The brief's rule, implemented literally</div><h2>How survey coverage changes a candidate's priority</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">High epistemic variance in under-surveyed terrain → a finding</div>
        <p>Project review policy: members' disagreement in independently confirmed low-coverage terrain <em>raises</em> review priority because the area may be under-mapped.
        The historical candidate report records {esc(cand.get('n_under_surveyed_raising_priority', 0))} candidates in this class; this count is not recomputed here.</p></div>
      <div class="card"><div class="card-kicker">High epistemic variance in well-surveyed terrain → suspicion</div>
        <p>If independent records confirm adequate survey coverage and members still disagree, treat the disagreement with suspicion rather than as positive evidence.
        The historical candidate report flags {esc(cand.get('n_well_surveyed_flagged', 0))} candidate(s); this count is not recomputed here.</p></div>
      <div class="card"><div class="card-kicker">Aleatoric variance never changes priority</div>
        <p>E<sub>m</sub>[p<sub>m</sub>(1 − p<sub>m</sub>)] summarizes within-member Bernoulli uncertainty; it is distinct from disagreement between trained members.
        Report both components and the model/data definition. This historic report was not reproduced here, so neither component is used for release decisions.</p></div>
      <div class="card"><div class="card-kicker">Coverage is measured, not assumed</div>
        <p>The historical report combined 3DEP validity and USGS SGMC structure-line density. The referenced coverage raster is not present in this checkout, so its mapped percentage and candidate zones cannot be rechecked here.
        Future reviews must compute coverage from the actual AOI grids and their metadata, keep the epistemic/aleatoric split, and treat coverage-adjusted uncertainty as a reviewer aid—not as a submission raster.</p></div>
    </div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Out-of-fold honesty check</div><h2>Did the detector beat a random emission?</h2>
      <p>The historical report records the gate as <strong>{'PASSED' if oof.get('gate_passed') else 'NOT PASSED'}</strong>
      ({esc(oof.get('folds_beating_random',0))}/{esc(oof.get('n_folds',0))} folds), with mean values {esc(num(oof.get('mean_dti'),4))} versus
      {esc(num(oof.get('mean_random'),4))}). These numbers are not reproduced from current checkpoints/data and are not release evidence.
      The report states the detector was excluded; see <a href="data/submission-build.json">the archived build record</a>.</p></div></div>
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
    <div class="eyebrow">Inference guide</div><h1>What the public score can—and cannot—support</h1>
    <p class="lead">A public leaderboard value is one scalar from one hidden evaluation split. It can rank returned submissions for that split;
    by itself it cannot identify the TIFF, explain which geology helped, estimate private/final performance, or validate spatial generalization.</p>
  </div></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Reported method, not independently reproduced</div><h2>What the H19 project says it tried</h2></div></div>
    {table(["reported approach", "geological mechanism", "evidence boundary"], [
      ["Fault-length / power-law population scaling", "Extend mapped traces or weight candidate geometry using an assumed fault-size population and terminal/relay deficits.", "The H19 public page describes this; local fold predictions, configs, and a held-out truth set were not found in this checkout."],
      ["Thermal / geochemical conduit inversion", "Use springs, wells, temperature probes, and geothermometer anomalies as indirect evidence for permeable pathways.", "Plausible regional prior, but mapped hot springs are strongly selected; no local reproducible ablation identifies gain from this family."],
      ["3DEP topographic openness and local relief", "Use lidar/DEM scarp and landform morphology to locate surface expressions missed by regional maps.", "Physical rationale is testable, but the external lidar derivative products cited by prior reports are absent from this checkout."],
      ["Geophysical lineaments / cross-line corroboration", "Use magnetic and gravity contacts, with caution about flight-line artifacts and survey resolution.", "Competition bands are locally present, but no H19 per-layer ablation or exact high-score artifact attribution is available here."]])}
    <p class="small">These summaries are attributed to the self-published <a href="https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html">19GEMSDOE H19 project page</a>, not to a confirmed public leaderboard row or an independently reproduced model.</p>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Score interpretation</div><h2>Separate the three result channels</h2></div></div>
    <div class="grid-3">
      <div class="card"><div class="card-kicker">Public leaderboard</div><p>Visible ranking on its current public split. A score-name match is not a TIFF hash, team attribution, private score, or winning submission proof.</p></div>
      <div class="card"><div class="card-kicker">Initial Prize Round</div><p>Private evaluation, not visible in the public snapshot. Do not infer it from public rank or from a project page's reported score.</p></div>
      <div class="card"><div class="card-kicker">Final Prize Round</div><p>Later expert-reviewed evaluation may use expanded labels. It is a separate result from the public board and private Initial Round.</p></div>
    </div>
    <p>Review the dated rows and stated retrieval-time precision on <a href="results.html">Scores</a>. The committed snapshot reports a 0.3195 leader when captured; the user-reported 0.3049 does not appear in that snapshot. H19-like values 0.1922 and 0.1894 match rows but do not identify their source files.</p>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Official metric</div><h2>Why a scalar does not isolate a geological mechanism</h2></div></div>
    <p>The organizer's distance-weighted Tversky score rewards proximity to newly labelled target fault pixels and penalizes weighted false-positive emission, under the published mask and distance kernel. One scalar mixes spatial alignment, prediction mass, target density, masking, and split composition. Many different rasters and feature mechanisms can yield the same score.</p>
    <p>Known-catalogue pixels are not a valid substitute for the hidden new-geometry target: staff clarified that known USGS/INGENIOUS fault pixels are masked from evaluation. A catalogue-trained model can therefore look good on a catalogue holdout while failing the scored population.</p>
    <div class="callout"><strong>Current gate.</strong> The historic catalogue-quadrant validation record is WITHDRAWN. <code>data/current-holdout-best.json</code> is BLOCKED; no live score projection or file-format preflight can authorize a competition submission.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Causal analysis standard</div><h2>What evidence would support a “why” claim?</h2></div></div>
    <ol class="list-clean">
      <li>Obtain exact, attributable candidate TIFFs and immutable configs for each approach. Match a score to an artifact only through an explicit submission record—not score equality.</li>
      <li>Define an independent target of uncatalogued fault geometry, document its semantics and survey coverage, then freeze spatially separated blocks before tuning.</li>
      <li>Run paired feature-family ablations and compare each candidate with the exact current-best prediction on identical held-out geography and metrics.</li>
      <li>Report per-fold deltas, uncertainty, coverage strata, negative controls, failed runs, and prediction/config/truth hashes. Keep public, private, and final results separate.</li>
    </ol>
    <p>Until then, H19 methods are useful hypotheses—not established causes of a score.</p>
  </section>"""

    results = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Scores · dated public snapshot</div><h1>Leaderboard evidence with attribution limits</h1>
    <p class="lead">This page reports the official public board snapshot captured at <code>{esc(lb.get('retrieved_utc','date not recorded'))}</code>.
    It is not a live guarantee, not the private Initial Prize Round, and not the Final Prize Round. Confirm current rows directly with the official source.</p>
    <p><a class="button" href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">Open official leaderboard →</a></p>
  </div><aside class="hero-aside"><span class="status status-neutral">Capture: {esc(lb.get('source_status','unknown'))}</span>
    <strong style="margin:.8rem 0 .45rem">{esc(num(leader.get('score'),4))}</strong>
    <p class="small">{esc(leader.get('participant','—'))} · rank {esc(leader.get('rank','—'))} in this {esc(len(rows_lb))}-row capture.</p></aside></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Snapshot</div><h2>Displayed public leaderboard</h2>
      <p>Captured by {esc(capture_method)}. Latest status: {esc(lb.get('refresh_status',{}).get('status', lb.get('source_status','unknown')))}.
      <span id="leaderboard-retrieved">{esc(lb.get('retrieved_utc','date not recorded'))}</span></p></div></div>
    {lb_table}
    <p class="small">{lb_attribution}</p>
    <p class="small">{lb_phase}</p>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Resolve reported values</div><h2>Do the quoted scores appear in this capture?</h2></div></div>
    {reported_score_table}
    <div class="callout"><strong>0.3049 conflict.</strong> The user-reported 0.3049 is not present in the committed 50-row snapshot captured at {esc(lb.get('retrieved_utc','date not recorded'))}. That snapshot's leader is 0.3195 ({esc(leader.get('participant','—'))}); the nearest high-scoring displayed row is not a substitution for a fresh capture. This mismatch may be due to a different retrieval time, split, or source; it is unresolved here.
    The 0.1922 and 0.1894 matches are rows at ranks 26 and 28 in this snapshot, but DrivenData does not expose public prediction hashes/submission IDs. Do not treat either as verified H19 artifact attribution. The H19 page also says H19-4/H19-5 were “not live-scored yet.” In addition, prior project prose calls 0.1894 the highest in one place while listing 0.1922 elsewhere; numerically 0.1922 is larger, and neither score is verified as an H19 artifact.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">What can be inferred</div><h2>Leaderboard analysis without overclaiming</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">Valid inference</div>
        <p>The displayed rank and score values are a snapshot of the public evaluation when captured. The reported H19 scores have numerical matches in public rows; H19 methods are plausible candidate strategies worth examining as hypotheses.</p></div>
      <div class="card"><div class="card-kicker">Not supported by these rows</div>
        <p>Score equality does not prove which TIFF/account earned a row. A single aggregate does not identify causal gains from any feature family, a holdout win, private-round performance, Final Round outcome, or future leaderboard state.</p></div>
      <div class="card"><div class="card-kicker">Reported high-scoring strategy families</div>
        <p>The H19 public write-up describes fault-length scaling, thermal/geochemical conduit evidence, 3DEP terrain morphology, and geophysical lineaments. The write-up's four-quadrant holdout claims are self-reported; the folds, predictions, config, and truth are not available here to reproduce.</p></div>
      <div class="card"><div class="card-kicker">Current project decision</div>
        <p>Do not submit the downloadable H24 QA candidate. <code>data/current-holdout-best.json</code> is BLOCKED and the legacy known-catalogue comparison is WITHDRAWN. The leaderboard does not replace spatially blocked validation.</p></div>
    </div>
    <p><a href="evidence.html">Read the inference limits and reported-method review →</a> · <a href="hypotheses.html">Review new testable hypotheses →</a></p>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Artifact and claim register</div><h2>Follow the evidence</h2></div></div>
    {table(["record", "purpose"], [
      ["<a href='data/leaderboard.json'>leaderboard.json</a>", "50-row capture, date/time precision, method, public score rows, attribution and round caveats"],
      ["<a href='data/leaderboard-status.json'>leaderboard-status.json</a>", "refresh status and diagnostics recorded with this snapshot"],
      ["<a href='data/irregularities.json'>irregularities.json</a>", "score, attribution, and other unresolved conflicts"],
      ["<a href='data/reference-artifact-audit.json'>reference-artifact-audit.json</a>", "historical local artifact audit; not proof that a board row came from a file"],
      ["<a href='research/knowledge_base.md'>knowledge_base.md</a>", "dated external-source register, facts, self-reports, hypotheses, and unknowns"]])}
  </section>"""

    sources = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Sources</div><h1>Every official source used, with the link that verifies it</h1>
    <p class="lead">Competition pages, staff rulings and public-domain USGS/DOE data. Anything not on this page is inference and is
    labelled as such where it appears.</p></div></div></section>
  <section class="section">
    {table(["source", "what it establishes", "link"], [
      ["DrivenData problem description", "task, data, metric formulas, worked example (0.60), submission format", "<a href='https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/'>page 967</a>"],
      ["DrivenData leaderboard", "dated public-score snapshot captured from the official page on 2026-10-02; check the live page for changes",  "<a href='https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/'>leaderboard</a>"],
      ["Staff ruling, forum 11516", "“Pixels corresponding to known USGS/INGENIOUS faults are masked / excluded from evaluation, so they do not count towards penalty terms” — and the same masking applies in the Final Round", "<a href='https://community.drivendata.org/t/11516'>topic 11516</a>"],
      ["Staff ruling, forum 11536", "“‘new fault’ means ‘any fault pixel not already captured by USGS/INGENIOUS’ and can include newly mapped geometry of an existing fault system”", "<a href='https://community.drivendata.org/t/11536'>topic 11536</a>"],
      ["NLR/DOE rules (OSTI 96647)", "3 uploads per rolling 7 days, one final submission per entity, $50,000 Initial and $250,000 Final rounds, external-data licensing, AI disclosure", "<a href='https://docs.nlr.gov/docs/fy26osti/96647.pdf'>rules PDF</a>"],
      ["USGS GeoDAWN release", "the airborne magnetic and radiometric survey behind the feature bands; Area 2 flown with 400 m E–W lines and 4 km N–S tie lines at 150–200 m clearance", "<a href='https://www.sciencebase.gov/catalog/item/657e1d85d34e23d3533209f7'>ScienceBase item</a> · <a href='https://doi.org/10.5066/P93LGLVQ'>DOI 10.5066/P93LGLVQ</a>"],
      ["USGS 3DEP", "free public 1 m / 10 m DEM products and coverage tools; exact AOI tile availability and quality must be checked before use",  "<a href='https://www.usgs.gov/3d-elevation-program'>3DEP</a>"],
      ["USGS SGMC", "State Geologic Map Compilation; a regional mapped-geology source, not the hidden competition truth and not present in this checkout",  "<a href='https://mrdata.usgs.gov/geology/state/'>landing page</a> · <a href='https://doi.org/10.3133/ds1052'>DOI 10.3133/ds1052</a>"],
      ["Geothermal Data Repository (INGENIOUS)", "public geothermal-data repository cited by historical methods; exact datasets/counts used in prior claims are not present or re-audited here",  "<a href='https://gdr.openei.org/'>gdr.openei.org</a>"],
      ["Organisers' reference solution", "U-Net ensemble, TverskyLoss(α=0.2, β=0.8), 128-px patches, 5 random 50/50 splits", "<a href='https://github.com/drivendataorg/gems-prize-reference-solution'>GitHub</a>"],
      ["H19 project hub (self-reported)", "power-law, thermal/geochemical, 3DEP morphology and geopotential methods plus holdout claims; artifacts/configs not independently reproduced here", "<a href='https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html'>19GEMSDOE hub</a>"],
      ["Hermant et al. 2025 (Stanford Geothermal Workshop)", "most Great Basin hydrothermal systems are fault-controlled; USGS Quaternary faults can sit ~400 m from lidar-based labels", "<a href='https://pangea.stanford.edu/ERE/db/GeoConf/papers/SGW/2025/Hermant.pdf'>paper</a>"],
      ["Faulds &amp; Hinz 2015 (OSTI 1724082)", "structural settings of 426 known systems: step-overs/relay ramps ~32 %, normal-fault terminations ~25 %, ~39 % blind", "<a href='https://www.osti.gov/servlets/purl/1724082'>OSTI</a>"],
      ["Lakshminarayanan, Pritzel &amp; Blundell 2017", "deep ensembles and the epistemic/aleatoric decomposition used on the uncertainty page", "<a href='https://papers.nips.cc/paper_files/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html'>NeurIPS 2017</a>"]])}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Data present in this checkout</div><h2>Local files and their recorded hashes</h2></div></div>
    {table(["path", "bytes / SHA-256", "scope"], [
      ["<code>data/training_features.tif</code>", "418,912,844 · <code>4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5</code>", "19-band competition feature stack; local ignored file"],
      ["<code>data/labels.tif</code>", "425,830 · <code>7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093</code>", "known-fault catalogue labels; unlabelled does not mean fault-free"],
      ["<code>data/sample_submission.tif</code>", "1,599,597 · <code>2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc</code>", "official grid/CRS/affine/footprint template"],
      ["<code>data/processed/manifest.json</code>", "local generated record", "input hashes, grid, band metadata, sentinel handling and label semantics"],
      ["<code>data/external/</code>", "not present", "3DEP scarp products, downloaded GeoDAWN extensions and SGMC derivatives are not in this checkout"]])}
    <div class="callout">The TIFFs and prepared arrays are local and Git-ignored. Their hashes are recorded in the generated preparation manifest; that verifies the bytes against this checkout's record, not independently against an official-host copy. The public git bridge also verifies downloads against its own manifest, not against a second independent source. No access-control bypass is used. For later work, read <code>README.md</code> first and use <code>data/README.md</code> for authorized data placement.</div>
  </section>"""

    verification = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Audit · three-pass review</div><h1>Evidence boundaries, irregularities and remaining work</h1>
    <p class="lead">Release status is <strong>{esc(release_status)}</strong>. The candidate passes template format preflight only;
    the spatial holdout gate is blocked. Historical scores, models and projections are identified as such rather than presented as new results.</p>
  </div><aside class="hero-aside"><span class="status status-warning">No slot authorized</span>
    <p class="small">Review record: <a href="research/review-log-2026-10-02.md">three-pass review log</a>.</p></aside></div></section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Release and format records</div><h2>What was checked</h2></div></div>
    {table(["record", "result", "interpretation"], [
      ["<a href='data/current-template-validation.json'>current-template-validation.json</a>", "hard checks pass for H24 NaN and all-finite files", "single-band Float32, CRS/grid/affine, in-footprint [0,1], nodata/outside-footprint checks; not an online uploader test"],
      ["<a href='data/current-holdout-best.json'>current-holdout-best.json</a>", "BLOCKED", "no verified exact-current-best OOF artifact or non-withdrawn spatial holdout is registered"],
      ["<a href='data/validation-report.json'>validation-report.json</a>", "WITHDRAWN", "historical catalogue-label quadrant validation was not valid evidence for the masked uncatalogued-fault target"],
      ["<a href='data/submission-manifest.json'>submission-manifest.json</a>", "QA candidate only", "contains file identity and format report; release approval must remain false"],
      ["<a href='data/irregularities.json'>irregularities.json</a>", "open flags shown below", "each item records how established, action, and relevant official link where available"]])}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Flagged</div><h2>Irregularity register</h2></div></div>
    {irregular_table if irregular_rows else '<p class="small">See <code>docs/data/irregularities.json</code>.</p>'}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Unresolved questions</div><h2>What this evidence cannot establish</h2></div></div>
    <ul class="list-clean">
      <li><strong>Public scores do not identify TIFFs.</strong> The official leaderboard has names and scalar scores but no public artifact hash or submission ID. H19 score matches are not verified file/team attribution. Its “not live-scored yet” notice conflicts with upload-oriented prose.</li>
      <li><strong>Score figures refer to different records unless proven otherwise.</strong> This repository's snapshot was captured at <code>{esc(lb.get('retrieved_utc','date not recorded'))}</code> and records top public score {esc(num(leader.get('score'),4))} for {esc(leader.get('participant','—'))}; the reported 0.3049 is not in that 50-row snapshot. H19-like matches 0.1922 and 0.1894 appear at ranks 26 and 28 but do not identify artifacts. See <a href="results.html">score snapshot and caveats</a>.</li>
      <li><strong>No offline proxy is accepted as a placement validator.</strong> The model, if revived, must be tested against an independent truth population using pre-registered spatial blocks and the exact incumbent OOF map.</li>
      <li><strong>Uncertainty must be rerun.</strong> Phase 2 epistemic variance should raise priority in independently documented under-surveyed terrain and trigger suspicion in well-surveyed terrain; aleatoric and epistemic components must come from independently initialized and trained members, not dropout at inference. Current historical report/checkpoints are not reproduced.</li>
      <li><strong>Source coverage remains uneven.</strong> USGS 3DEP AOI tile completeness, Great Basin conductance overlap, and survey coverage masks must be checked before H-31/H-32 or candidate uncertainty maps are trusted.</li>
      <li><strong>Submission limit is conserved.</strong> No submission was made. Do not spend one until the spatial gate passes and the release builder's exact current-best hash checks succeed.</li>
    </ul>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Three-pass verification</div><h2>Review sequence</h2></div></div>
    <ol class="list-clean">
      <li><strong>Pass 1 · evidence and scope.</strong> Read the brief, inspect current data/manifests and public scores, identify missing inputs, stale claims, and attribution contradictions.</li>
      <li><strong>Pass 2 · implementation.</strong> Keep candidate format QA separate from release approval; fail closed without exact-best OOF hashes; correct site and submission guidance; preserve H19 hypotheses as unverified.</li>
      <li><strong>Pass 3 · verification.</strong> Regenerate static pages, validate local links/status/GeoTIFF metadata, run available tests, inspect the diff, and report unrun model/online checks explicitly.</li>
    </ol>
    <p class="small">The dated record includes commands, outcomes, and remaining limitations. It is not a claim that the holdout gate passed.</p>
  </section>"""

    pages = {
        "index.html": ("GEMSDOE23 · geothermal fault discovery", index, "index.html",
                       "First-page QA GeoTIFF download, current release gate, leaderboard context, and evidence limits for DOE GEMS Prize submissions."),
        "executive-summary.html": ("Release gate and upload guide · GEMSDOE23", executive, "executive-summary.html",
                                   "Current submission status, release-blocking spatial holdout, conditional future upload steps, and traceability records."),
        "hypotheses.html": ("Ranked geological hypotheses · GEMSDOE23", hypotheses, "hypotheses.html",
                            "Four distinct unimplemented geological hypotheses with layers, physical signatures, rationale, ordinal potential, cost, and validation plan."),
        "uncertainty.html": ("Uncertainty · GEMSDOE23", uncertainty, "uncertainty.html",
                             "Historical deep-ensemble uncertainty report, survey-coverage policy, and explicit reproduction caveats."),
        "evidence.html": ("Inference guide · GEMSDOE23", evidence, "evidence.html",
                          "What public leaderboard scores do and do not establish; reported H19 strategies and validation requirements."),
        "results.html": ("Dated leaderboard snapshot · GEMSDOE23", results, "results.html",
                         "Dated official public leaderboard snapshot, reported-score conflicts, H19 attribution caveats, and separate evaluation rounds."),
        "sources.html": ("Sources and data provenance · GEMSDOE23", sources, "sources.html",
                         "Official competition pages, staff rulings, public USGS/DOE sources, and current-checkout data provenance."),
        "verification.html": ("Audit and review log · GEMSDOE23", verification, "verification.html",
                              "Current release/format records, irregularities, three-pass implementation review, and remaining limitations."),
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
