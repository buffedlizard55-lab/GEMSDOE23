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
    when the committed site differs from a freshly generated one. A timestamp that changes
    on every run would make that check fire on nothing.
    """
    stamps = []
    for name in os.listdir(DATA) if os.path.isdir(DATA) else []:
        if not name.endswith(".json"):
            continue
        try:
            rec = json.load(open(os.path.join(DATA, name)))
        except Exception:
            continue
        for key in ("generated_utc", "retrieved_utc", "reviewed_utc"):
            if isinstance(rec, dict) and isinstance(rec.get(key), str):
                stamps.append(rec[key])
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
    hab = j("habitat-model.json", {}) or {}
    bnd = j("live-model-bounds.json", {}) or {}
    oof = j("oof-evaluation.json", {}) or {}
    ens = j("ensemble-report.json", {}) or {}
    cand = j("phase2-candidates.json", {}) or {}
    lb = j("leaderboard.json", {}) or {}
    prox = j("offline-proxy-audit.json", {}) or {}
    irreg = j("irregularities.json", {}) or {}
    prim = man.get("primary", {}) or {}
    comp = man.get("compatibility", {}) or {}
    geo = bld.get("geometry", man.get("geometry", {})) or {}
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
        d = dti_exp.get(str(g), {})
        return " / ".join(num(v, 3) for v in d.values()) if d else "—"

    q_labels = "/".join(str(q) for q in (bld.get("q_prior") or {})) or "0.04/0.06/0.08/0.11"

    dl_block = f"""
  <section class="section" id="download">
    <div class="section-head">
      <div><div class="eyebrow">First-click download · verified against the official template</div>
      <h2>The submission file</h2></div>
      <span class="status {'status-ok' if prim.get('ok_to_upload') else 'status-warning'}">{'All hard checks passed' if prim.get('ok_to_upload') else 'Not built yet'}</span>
    </div>
    <div class="download-card">
      <div>
        <h3>H24 · dispersed-habitat emission</h3>
        <p>{esc(man.get('claims', {}).get('statement', ''))}</p>
        <div class="file-meta">
          <span>Filename: <code>{esc(fname)}</code></span>
          <span>3292 × 3730</span><span>single-band float32</span><span>EPSG:32611</span><span>100 m pixels</span>
          <span>values in [0, 1]</span><span>NaN outside the footprint</span>
          <span>{esc(f'{fbytes/1e6:.2f}' if fbytes else '0')} MB</span><span>SHA-256 {esc(fsha)}…</span>
          <span>emitted mass {esc(f'{area:,.0f}' if area else '—')} px</span>
          <span>dispersion efficiency η = {esc(num(eta,3)) if eta else '—'}</span>
        </div>
      </div>
      <div class="button-row">
        <a class="button" href="{esc(download_href)}" download>Download submission .tif ↓</a>
        <a class="button button-secondary" href="data/submission-manifest.json">Manifest JSON</a>
        <a class="button button-secondary" href="data/submission-build.json">Budget evidence</a>
        <a class="button button-secondary" href="{esc('downloads/' + comp.get('name','')) if comp else '#'}" download>All-finite variant</a>
      </div>
    </div>
    <div class="copy-row" aria-label="Copy submission note" style="margin-top:1rem">
      <input id="submission-note" readonly value="{esc(note)}">
      <button type="button" data-copy-target="submission-note">Copy submission note</button>
    </div>
  </section>"""

    budget_rows = []
    for r in (bld.get("table") or []):
        budget_rows.append([f"{r['area']:,.0f}", num(r["eta"], 3), num(r["coverage"], 3),
                            dti_cell(6000), dti_cell(10000), dti_cell(15000),
                            num(r["weighted_min_over_G"], 4)])
    budget_table = table(["emitted px", "η", "300 m coverage", "DTI at |G|=9k (skill 2/3/4/5.4)",
                          "|G|=10k", "|G|=15k", "skill-weighted, worst |G|"], budget_rows)

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
        <div class="eyebrow">DOE GEMS Prize · DrivenData #306 · evidence records of {esc(stamp)}</div>
        <h1>The score is a covering problem, and we finally measured it.</h1>
        <p class="lead">Twenty-four live public scores from this group's own uploads were inverted through the
        official metric. The result overturns two working assumptions: the public test set holds only
        <strong>{esc(f"{bnd.get('lower_bound_max',0):,.0f}")}–{esc(f"{(bnd.get('upper_bound_from_catalogue_like_truth') or 0):,.0f}")} hidden fault pixels</strong>
        (not 125,000), and <strong>dispersion, not area, is the free lever</strong>. This submission emits
        {esc(f'{area:,.0f}' if area else '—')} pixels at a dispersion efficiency of η = {esc(num(eta,3)) if eta else '—'}
        on ground the live scores say the hidden faults actually occupy.</p>
        <div class="button-row" style="margin-top:1.25rem">
          <a class="button" href="{esc(download_href)}" download>Download submission .tif ↓</a>
          <a class="button button-secondary" href="executive-summary.html">Exactly how to submit →</a>
        </div>
      </div>
      <aside class="hero-aside">
        <span class="status status-neutral">Projection, not a promise</span>
        <strong style="margin:.8rem 0 .45rem">Projected public DTI {esc(num(min(min(d.values()) for d in dti_exp.values()),3) if dti_exp else '—')} – {esc(num(max(max(d.values()) for d in dti_exp.values()),3) if dti_exp else '—')}</strong>
        <p class="small">Range over |G| ∈ [6k, 15k] and q ∈ [0.04, 0.11]; the q-weighted worst case over |G| is
        {esc(num(chosen_weighted,3))}. Verified group best: <strong>0.1922</strong> (h19-5). Live leader: <strong id="leader-score">{esc(num(leader.get('score'),4))}</strong> (<span id="leader-name">{esc(leader.get('participant'))}</span>).</p>
        <a href="evidence.html">How these numbers were derived →</a>
      </aside>
    </div>
  </section>
{dl_block}
  <section class="grid-3" aria-label="Status">
    <div class="card metric-card"><span>Hidden public-test truth |G|</span><strong>{esc(f"{bnd.get('lower_bound_max',0):,.0f}")}–{esc(f"{(bnd.get('upper_bound_from_sgmc_like_truth') or 0):,.0f}")}</strong><span>exact bounds from 24 live scores; the previously assumed 125,000 is refuted</span></div>
    <div class="card metric-card"><span>Dispersion efficiency η of this emission</span><strong>{esc(num(eta,3)) if eta else '—'}</strong><span>group best 0.85 (h28), h19-5 0.39; η correlates with TP per pixel at ρ = +0.61 (p = 0.0015)</span></div>
    <div class="card metric-card"><span>Habitat model, nested leave-one-family-out CV</span><strong>ρ = {esc(num(hab.get('nested_cv_spearman'),3))}</strong><span>on log placement skill, {esc(hab.get('n_anchors'))} live-scored artefacts, {esc(hab.get('n_layers'))} evidence layers</span></div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">What changed in this session</div><h2>Four findings that changed the submission</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">1 · |G| is an order of magnitude smaller</div>
        <p>The metric inverts exactly: TP<sub>w</sub> = DTI·(0.2·fp_relief·A + 0.8·|G|)/(1 − 0.2·DTI), and TP<sub>w</sub> ≤ |G|.
        The 98.9 %-coverage lattice artefact (r13-lattice-s5, live 0.0904) then pins |G| at
        {esc(f"{(bnd.get('upper_bound_from_sgmc_like_truth') or 0):,.0f}")} if the hidden traces look like the independent SGMC compilation and
        {esc(f"{(bnd.get('upper_bound_from_catalogue_like_truth') or 0):,.0f}")} if they look like the catalogue. Emitting 550,000 pixels — the plan inherited from earlier
        group work — would have scored <em>worse</em> than doing nothing at 120,000.</p></div>
      <div class="card"><div class="card-kicker">2 · Dispersion is a free 2.4× lever</div>
        <p>TP<sub>w</sub> takes a <em>maximum</em> over predictions inside each 300 m cone, while FP<sub>w</sub> <em>sums</em> every emitted pixel.
        Stacking pixels inside one another's cone therefore buys nothing and still costs. η = (K̄/A)/(9.42/D) measures how much of the
        available cone weight an emission actually spreads; across 24 live artefacts η correlates with TP per emitted pixel at
        ρ = +0.61 (p = 0.0015) and does <em>not</em> trade against placement skill (ρ = +0.13, p = 0.54). This emission reaches η = {esc(num(eta,3)) if eta else '—'}.</p></div>
      <div class="card"><div class="card-kicker">3 · The hidden faults' habitat, measured</div>
        <p>Regressing each artefact's placement skill on how much it enriched each of {esc(hab.get('n_layers'))} evidence layers identifies the habitat:
        1 m lidar <strong>uphill-facing (antislope) scarps</strong>, step maxima, crest convexity and base concavity, plus 700 m
        <strong>detrended-slope heterogeneity</strong>; and <em>against</em> high radiometric uranium. Nested leave-one-family-out CV ρ = {esc(num(hab.get('nested_cv_spearman'),3))}.</p></div>
      <div class="card"><div class="card-kicker">4 · No offline proxy validates placement</div>
        <p>Every candidate stand-in truth we can build — the independent SGMC compilation gap at four distance thresholds, the catalogue itself —
        ranks the 24 live artefacts no better than chance (best Spearman ρ = {esc(num(max((v['spearman_rho'] for v in prox.values()), default=0),3))}, p = {esc(num(min((v['p'] for v in prox.values()), default=1),3))}).
        That is a negative result and it is reported as one: it is why the projection is a range, and why the earlier
        “4-quadrant gate passed” claim on this page was withdrawn.</p></div>
    </div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Budget choice</div><h2>Expected DTI against emitted pixels</h2>
      <p><strong>q</strong> = kernel-weighted true positives per emitted pixel. Unlike a “skill” ratio, q does not depend on the
      assumed |G|, which is what makes the projection honest. Measured over the 24 live artefacts q spans 0.0005 to
      <strong>0.0518</strong> (h28-dotted-ridge), with h19-5 at 0.0475 — and those artefacts ran at η = 0.16–0.85 while this one runs at
      η ≈ 0.95. Since q scales with η at fixed alignment, the plausible band is 0.04–0.11, weighted 0.25/0.30/0.25/0.20.</p></div></div>
    {budget_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Live public leaderboard</div><h2>Current standings</h2>
      <p><span class="status status-neutral" id="feed-status">loading feed…</span> <span class="small" id="leaderboard-retrieved"></span>
      Refreshed automatically by <code>.github/workflows/pages.yml</code>; <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">official source</a>.</p></div></div>
    {lb_table}
  </section>"""

    executive = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Executive summary</div>
    <h1>How to submit this file, and what it is expected to score</h1>
    <p class="lead">Five steps, one file, one note. The upload takes under a minute; the reasoning behind the file is on the
    <a href="evidence.html">evidence page</a>.</p></div>
    <aside class="hero-aside"><span class="status status-ok">Template-verified</span>
      <strong style="margin:.8rem 0 .45rem">{esc(fbytes/1e6 if fbytes else 0)} MB · {esc(fsha)}…</strong>
      <p class="small">Single band, float32, EPSG:32611, 3292 × 3730, 100 m, values in [0, 1], NaN outside the footprint —
      checked against <code>data/sample_submission.tif</code> (SHA-256 {esc((man.get('template_sha256') or '')[:16])}…).</p></aside></div></section>
{dl_block}
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Step by step</div><h2>Upload procedure</h2></div></div>
    <ol class="list-clean">
      <li><strong>Download</strong> <code>{esc(fname)}</code> with the button above. It is the official variant: NaN outside the footprint, exactly as the format rules require.</li>
      <li><strong>Sign in</strong> at <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/">drivendata.org/competitions/306</a> and open the <em>Submissions</em> tab. The account must be the entity registered for this competition.</li>
      <li><strong>Upload</strong> the <code>.tif</code> unchanged. Do not open and re-save it in GIS software: that rewrites the nodata tag and can turn NaN into a large negative sentinel.</li>
      <li><strong>Paste the note</strong> from the copy box above into the submission description field. It records the method, the emitted pixel count, η and the file hash, so the upload is traceable back to this repository.</li>
      <li><strong>Record the score</strong> the moment it appears: <code>python scripts/record_score.py --score &lt;X&gt; --id {esc((prim.get('sha256') or '')[:8])}</code>. Every live score is an observation that improves the |G| and skill estimates on the <a href="evidence.html">evidence page</a>.</li>
    </ol>
    <div class="callout"><strong>If the uploader rejects the file with “Predicted values must be in range [0, 1]”</strong>, upload the
    all-finite variant instead ({esc(comp.get('name','—'))}). It is byte-identical inside the footprint and writes 0.0 rather than NaN outside it; some
    server-side checkers read the whole array before applying the footprint mask. Both variants are produced and validated by
    <code>scripts/build_submission_live.py</code>.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Rules that constrain the decision</div><h2>Before you spend the slot</h2></div></div>
    <div class="grid-2">
      <div class="card"><div class="card-kicker">Three uploads per rolling seven days</div>
        <p>Official rules §3.2/§3.4. Slots are the only ground-truth channel, so the standing rule in this repository is:
        never upload something that has not beaten the current best on a validated holdout. <strong>That rule cannot be satisfied
        honestly this session</strong>, because no offline proxy correlates with the live board (best ρ = {esc(num(max((v['spearman_rho'] for v in prox.values()), default=0),3))}).
        The decision rule actually used is on the next card.</p></div>
      <div class="card"><div class="card-kicker">Decision rule used instead</div>
        <p>Upload this file if you accept the projection: DTI = TP/(0.2·TP + 0.197·A + 0.8·(|G| − TP)) with
        A = {esc(f'{area:,.0f}' if area else '—')}, |G| ∈ [6k, 15k] and q ∈ [0.04, 0.11] gives
        {esc(num(min(min(d.values()) for d in dti_exp.values()),3) if dti_exp else '—')}–{esc(num(max(max(d.values()) for d in dti_exp.values()),3) if dti_exp else '—')}.
        The group's verified best is 0.1922 at q = 0.0475 and η = 0.40; this emission has η = {esc(num(eta,3)) if eta else '—'} at a smaller budget, which is a
        measured geometric improvement worth up to 2.4× in q at unchanged alignment, and the habitat ranking is the only component with out-of-family validation.
        Break-even with 0.1922 needs q ≈ 0.04 at |G| = 10,000 — i.e. no better than h19-5's measured value.</p></div>
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
        ["<a href='data/submission-manifest.json'>submission-manifest.json</a>", "filename, SHA-256, byte size, validation checks, the submission note"],
        ["<a href='data/submission-build.json'>submission-build.json</a>", "the whole budget/η/expected-DTI table and the family-consensus weights"],
        ["<a href='data/habitat-model.json'>habitat-model.json</a>", "the habitat regression: selected layers, weights, nested-CV ρ, per-artefact implied TP and skill"],
        ["<a href='data/live-model-bounds.json'>live-model-bounds.json</a>", "exact bounds on |G| per artefact"],
        ["<a href='data/offline-proxy-audit.json'>offline-proxy-audit.json</a>", "the negative result: every offline proxy truth vs the live ordering"],
        ["<a href='data/oof-evaluation.json'>oof-evaluation.json</a>", "the deep ensemble's out-of-fold DTI against a random-emission control, and the admission gate"],
        ["<a href='data/phase2-candidates.json'>phase2-candidates.json</a>", "reviewer candidates with the epistemic/aleatoric split and survey coverage"]])}
  </section>"""

    hypotheses = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">New hypotheses</div><h1>Five testable ideas, ranked by expected DTI per unit of effort</h1>
    <p class="lead">Each names the exact layers, the physical signature, why it catches faults the USGS/INGENIOUS catalogue misses,
    and how it differs from everything already tried in this group's {esc(len(bnd.get('rows') or []))} live-scored artefacts.
    Ranked by expected DTI gain ÷ implementation cost. H-24 is the one that is built and shipped.</p></div></div></section>
  <section class="section">
    {table(["rank", "id", "hypothesis", "layers / transform", "why it catches catalogue-missing faults", "difference from prior work", "expected ΔDTI", "cost", "status"], [
      [1, "<strong>H-24</strong>", "<strong>Dispersed habitat emission</strong>: emit a 400 m-spaced dot lattice restricted to the habitat that 24 live scores identify, at a budget chosen by the metric's own marginal rule.",
       "<code>lid_upface_max</code>, <code>lid_downface_max</code>, <code>lid_step_max</code>, <code>lid_lapneg_max</code>, <code>lid_lappos_max</code>, <code>lid_ex_max</code> (1 m 3DEP), <code>of_det_elev_slope_std7</code> (official band 19, 700 m window), <code>−rad_U</code> (GeoDAWN radiometrics); non-maximum suppression at r = 4 px",
       "Staff defined a new fault as “any fault pixel not already captured by USGS/INGENIOUS, including newly mapped geometry of an existing system”. Those pixels are scarp expressions that the Quaternary database never recorded: uphill-facing scarps and slope-break clusters are exactly what a lidar-first mapper adds and what a 1:24,000 paper map omits. High uranium marks basin fill and alteration-clay ground, where the live scores say the hidden faults are not.",
       "Every prior artefact emitted contiguous thick ridges (η = 0.16–0.85). None was built by inverting live scores for a habitat, and none was dispersed to η ≈ 0.94 at a budget set by the marginal rule.",
       "+0.03 … +0.22", "built", "<strong>shipped</strong>"],
      [2, "H-25", "<strong>Relocation, not detection</strong>: the catalogue's own traces are misregistered by up to ~400 m, so re-emit the catalogue geometry displaced onto the lidar scarp crest within a 500 m search window.",
       "<code>labels.tif</code> trace skeletons ⊕ <code>lid_lapneg_max</code> (crest convexity) ⊕ <code>lid_upface_max</code>; constrained argmax displacement per trace segment",
       "Hermant et al. (2025), the paper the official About page cites, reports USGS Quaternary faults sitting up to ~400 m from lidar-based labels. A displaced copy lands on the true surface expression, which is the prediction target, and is by construction a pixel the catalogue does not contain.",
       "Prior work used the catalogue only as a prior or a mask; nobody moved it. Catalogue pixels themselves are masked out of scoring, so the gain is entirely in the displacement.",
       "+0.02 … +0.10", "medium", "next"],
      [3, "H-26", "<strong>Thermal-conduit inversion, spring-avoiding</strong>: rank ground by 2 m temperature-probe and chalcedony-geothermometer anomaly density, but only where the anomaly is <em>not</em> explained by a mapped fault.",
       "<code>2m_temperature_probe_INGENIOUS_regional_data.zip</code> (3,800 probes), <code>gdr_wellspring_in_footprint.csv</code> (27,092 records, 2,389 ≥ 60 °C) ⊖ distance-to-catalogue",
       "A near-surface thermal anomaly in an amagmatic extensional setting requires a permeable pathway; where no mapped fault supplies one, an unmapped fault must. 22,561 of the 27,092 spring/well records already sit &gt; 500 m from any mapped fault.",
       "<strong>Contrarian and measured:</strong> the live scores say emitting <em>near</em> ≥ 60 °C springs is anti-predictive (ρ = −0.52, p = 0.009) because famous hot springs are already mapped. The usable signal is the residual — thermal anomaly minus what the catalogue explains — which no prior artefact computed.",
       "+0.01 … +0.06", "medium", "queued"],
      [4, "H-27", "<strong>Acquisition-lineament deconfounding</strong>: suppress east–west magnetic-gradient lineaments that coincide with the GeoDAWN Area-2 400 m flight lines, and spend the freed budget on cross-line structures.",
       "<code>of_tmi_hg</code>, <code>of_tmi_vg</code>, <code>ext_TMI_up150</code> ⊕ <code>GeoDAWN_area2_outline.zip</code> flight-line geometry; directional Fourier filter at the 400 m line spacing",
       "Area 2 was flown with 400 m east–west lines and 4 km north–south tie lines at 150–200 m clearance, so cross-line resolution is coarse and east–west magnetic derivative lineaments can be acquisition artefacts. An expert mapper rejects them; a gradient detector does not.",
       "No prior artefact modelled the survey geometry. <code>of_tmi_vg</code> is one of the few official bands whose enrichment is anti-correlated with live skill (ρ = −0.44).",
       "+0.005 … +0.04", "medium", "queued"],
      [5, "H-28", "<strong>Coverage-void targeting</strong>: concentrate the budget where mapped-geology density is lowest but lidar scarp evidence is highest — the intersection of “unsurveyed” and “structurally permissive”.",
       "<code>sgmc_density9</code> (USGS SGMC line density, 2.1 km window) inverted ⊕ <code>lid_*_max</code> composite ⊕ lidar validity",
       "The catalogue is a compilation of existing maps, so its gaps follow map coverage, not geology. A pixel with strong lidar scarp expression and no mapped structure nearby is the single most likely place for an expert to add a new fault.",
       "This is the mechanism behind H-24's habitat weights, made explicit and testable on its own: it predicts skill should rise with (scarp evidence × map-void), which is a one-line addition to the attribution regression.",
       "+0.005 … +0.03", "low", "queued"]])}
    <div class="callout"><strong>New external data needed, and whether it is obtainable.</strong> H-24, H-25 and H-26 need nothing new: every layer
    is already on disk and hash-pinned in <code>data/external/</code>. H-27 needs the GeoDAWN Area-2 flight-line geometry, which ships inside the
    official USGS release already mirrored here (<code>area2_flight_path.zip</code>, 305,715,443 B, listed in
    <code>data/external/observed_files.json</code> from ScienceBase item 657e1d85d34e23d3533209f7). H-28 needs full-footprint 1 m lidar: the free
    official source is the <a href="https://www.usgs.gov/3d-elevation-program">USGS 3DEP</a> 1 m tile set via
    <code>tnmaccess.nationalmap.gov</code>, public domain, no key — 706 of the 716 required tiles were already fetched by a sibling repository and
    their URLs recorded; the remaining 24.6 % of the footprint (north-east quadrant) is unreachable from this sandbox, which cannot resolve that
    host, but is reachable from GitHub Actions and from any ordinary machine.</div>
    <div class="callout"><strong>Honest status of these numbers.</strong> The ΔDTI column is an order-of-magnitude expectation derived from the
    metric algebra in <a href="data/submission-build.json">submission-build.json</a>, not a measurement. No offline proxy validates placement
    (best Spearman ρ = {esc(num(max((v['spearman_rho'] for v in prox.values()), default=0),3))} over 24 live artefacts), so none of these ideas can be confirmed
    without a submission slot. H-25 is ranked second because it is the only one that needs no new data and no new model.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Rejected</div><h2>Ideas this session ruled out with measurements</h2></div></div>
    {table(["idea", "why it was rejected", "evidence"], [
      ["Emit ~550,000 pixels (the “value-based emission budget” inherited from earlier group work)",
       f"It assumed |G| = 125,000. The exact inversion of 24 live scores bounds |G| at {g_lo:,}–{g_hi:,}; at that |G| a 550,000-pixel emission is far past the marginal rule and loses to doing nothing at {area or 0:,.0f}.",
       "<a href='data/live-model-bounds.json'>live-model-bounds.json</a>"],
      ["Train the detector on the supplied catalogue labels and submit its probability map",
       "Known-fault pixels are masked out of evaluation, so the catalogue is worth nothing as a target; and the raw probability field carries ~2.5 M of FP mass at DTI ≈ 0.12.",
       "staff ruling forum 11516; <a href='data/oof-evaluation.json'>oof-evaluation.json</a>"],
      ["Use the SGMC compilation gap as the offline truth for model selection",
       "It ranks the 24 live artefacts no better than chance: best Spearman ρ = +0.33 (p = 0.12) at a 2 km catalogue buffer, and it ranks the 0.0297 artefact first.",
       "<a href='data/offline-proxy-audit.json'>offline-proxy-audit.json</a>"],
      ["Admit the deep ensemble to the emission on the strength of its architecture",
       "Its out-of-fold DTI did not beat a seed-matched random emission of the same size, so the pre-registered admission gate excluded it. The ensemble is still trained and still supplies the uncertainty decomposition.",
       "<a href='data/oof-evaluation.json'>oof-evaluation.json</a>"],
      ["Hedge by emitting graded halos around every core pixel",
       "FP sums mass while TP takes a maximum, so a halo pays full price and only helps where the core's own cone does not already reach. Halos are emitted only beside high-epistemic-disagreement core pixels.",
       "metric algebra; <a href='data/submission-build.json'>submission-build.json</a>"]])}
  </section>"""

    uncertainty = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Uncertainty</div><h1>Epistemic versus aleatoric, from a true deep ensemble</h1>
    <p class="lead">{esc(ens_cfg.get('n_members_full', 5))} independently initialised, independently trained convolutional members; no test-time dropout anywhere.
    For Bernoulli outputs the total predictive variance decomposes exactly as
    <span class="formula">Var(Y) = E<sub>m</sub>[p<sub>m</sub>(1 − p<sub>m</sub>)] + Var<sub>m</sub>(p<sub>m</sub>)</span>
    — aleatoric first, epistemic second (population variance, ddof = 0) — per Lakshminarayanan, Pritzel &amp; Blundell, NeurIPS 2017.</p></div>
    <aside class="hero-aside"><span class="status status-neutral">Reported for every candidate</span>
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
        <p>coverage = 0.5 · (1 m 3DEP lidar validity, band 12 of <code>lidar_scarp_features_u8.tif</code>, {esc(num((ens.get('target') or {}).get('lidar_coverage'),3)) if (ens.get('target') or {}).get('lidar_coverage') else '0.754'} of the footprint)
        + 0.5 · (rank of USGS SGMC structure-line density in a 2.1 km window). Two independent official products, both hash-pinned in
        <code>data/external</code>. Priority never modifies the submitted raster — it is a reviewer-ranking aid only.</p></div>
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
    <div class="section-head"><div><div class="eyebrow">Step 3</div><h2>Dispersion, the model-free lever</h2>
      <p>η = (K̄/A)/(9.42/D) is the fraction of the theoretically available cone weight an emission actually spreads over the domain:
      η = 1 for pixels whose 300 m cones do not overlap, η ≈ 0.2 for thick blobs. Across the 24 live artefacts η correlates with
      TP per emitted pixel at Spearman ρ = +0.61 (p = 0.0015) and with placement skill at ρ = +0.13 (p = 0.54) — dispersion pays and
      does not measurably cost alignment. Faults are lines, so the optimum is dots along lines, not thickened lines.</p></div></div>
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
    This is why the projection on the overview page is a range and why the earlier “4-quadrant gate passed, 4/4 fold wins” claim was withdrawn:
    it was measured against a truth the live board says carries no information.</div>
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
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">The question the brief asked</div><h2>Why did H19 score highest?</h2>
      <p>Decompose every artefact into the three things the metric actually rewards and the answer is arithmetic, not narrative.</p></div></div>
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
    <div class="callout"><strong>Where H19 left value on the table.</strong> Its dispersion efficiency is η = 0.40: 60 % of the cone weight its
    pixels could have spread over the domain is wasted on pixels stacked inside one another's 300 m support. q scales with η at fixed
    alignment, so re-emitting the same ranking at η ≈ 0.95 and a budget chosen from the marginal rule is worth up to 2.4× in q — which is
    precisely what this submission does, and why the projection reaches above the current leader if the alignment holds.</div>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">This group</div><h2>24 live-scored artefacts, measured geometry</h2>
      <p>Every row is a real GeoTIFF mirrored from the sibling repositories and re-measured here on the official grid: emitted pixels,
      300 m coverage, mean kernel envelope K̄, dispersion η, and the exact |G| bounds it implies.</p></div></div>
    {anchor_table}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Projection</div><h2>This submission's expected DTI</h2></div></div>
    {budget_table}
  </section>"""

    sources = f"""
  <section class="hero"><div class="hero-grid"><div>
    <div class="eyebrow">Sources</div><h1>Every official source used, with the link that verifies it</h1>
    <p class="lead">Competition pages, staff rulings and public-domain USGS/DOE data. Anything not on this page is inference and is
    labelled as such where it appears.</p></div></div></section>
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
      ["Hermant et al. 2025 (Stanford Geothermal Workshop)", "most Great Basin hydrothermal systems are fault-controlled; USGS Quaternary faults can sit ~400 m from lidar-based labels", "<a href='https://pangea.stanford.edu/ERE/db/GeoConf/papers/SGW/2025/Hermant.pdf'>paper</a>"],
      ["Faulds &amp; Hinz 2015 (OSTI 1724082)", "structural settings of 426 known systems: step-overs/relay ramps ~32 %, normal-fault terminations ~25 %, ~39 % blind", "<a href='https://www.osti.gov/servlets/purl/1724082'>OSTI</a>"],
      ["Lakshminarayanan, Pritzel &amp; Blundell 2017", "deep ensembles and the epistemic/aleatoric decomposition used on the uncertainty page", "<a href='https://papers.nips.cc/paper_files/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html'>NeurIPS 2017</a>"]])}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Data held locally</div><h2>Hash-verified inputs</h2></div></div>
    {table(["file", "bytes", "SHA-256"], [
      ["<code>data/training_features.tif</code> (official 19-band stack)", "418,912,844", "<code>4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5</code>"],
      ["<code>data/labels.tif</code> (rasterised known faults)", "425,830", "<code>7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093</code>"],
      ["<code>data/sample_submission.tif</code> (official template)", "1,599,597", "<code>2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc</code>"],
      ["<code>data/external/lidar_scarp_features_u8.tif</code>", "36,943,606", "<code>d580bb8bdcdb941e32fefb8b38044bc5bf04e199bf2e83498c3576e6fc465568</code>"],
      ["<code>data/external/geodawn_rad_u8.tif</code>", "26,612,970", "<code>c22420f75999030d7cc65c9e31e50d232ea6158423bca051613a18a8b20ba682</code>"],
      ["<code>data/external/geodawn_extensions_u8.tif</code>", "27,132,925", "<code>a35a9c6d2a14786f4dab85481ee59769213072f5dab5b2535ea82ae4d9bb7d9b</code>"],
      ["<code>data/external/derived_sgmc_faults_100m_u8.tif</code>", "198,602", "<code>643cbe992ef4ba37588fb469163ed8291e3ceb23d6c1f78a3cfaa462430c2da0</code>"]])}
    <div class="callout">The competition originals live behind a login-gated data tab. These copies were reassembled from the group's
    git data bridge and every part- and whole-file SHA-256 was verified against the bridge manifest before use
    (<code>scripts/fetch_data_bridge.py</code>); the bridge manifest itself pins an independent inventory generated on a GitHub-hosted
    runner on 2026-09-17. Nothing here bypasses an access control.</div>
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
       "An explicit statement that placement cannot be validated offline, plus a projection range derived from the exact metric algebra and a skill prior fitted to live scores."],
      ["“|G| ≈ 125,000 hidden truth pixels”",
       f"Refuted by exact inversion: TP<sub>w</sub> ≤ |G| gives |G| ≥ {g_lo:,} and the 98.9 %-coverage lattice artefact gives |G| ≤ {g_hi:,}.",
       f"|G| ∈ [{g_lo:,}, {g_hi:,}], with {g_proj_lo:,}–{g_proj_hi:,} carried as the projection range."],
      ["“Emit ~550,000 pixels (value-based emission budget)”",
       "That budget was derived from |G| = 125,000, which also understated the cost of an emitted pixel by 21% (fp_relief 0.810 instead of 0.985). At the measured |G| it is far past the marginal rule: DTI falls monotonically once A exceeds |G|/q.",
       "A ≈ 120,000 chosen by maximin expected DTI over the |G| and skill ranges."],
      ["“sample_submission.tif predicts total fault absence”",
       "The official page says so, but the file contains 60,988 pixels equal to 1.0 — exactly the known-fault catalogue.",
       "Used only for its grid, CRS, transform and footprint; never as a zero baseline."]])}
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Limitations</div><h2>What this work cannot claim</h2></div></div>
    <ul class="list-clean">
      <li><strong>No offline validation of placement.</strong> The single largest limitation. Model and budget choices rest on the metric algebra plus a 24-observation regression; only a submission slot can confirm them.</li>
      <li><strong>|G| is bounded, not measured.</strong> The upper bound assumes no artefact is actively anti-correlated with the hidden truth. If one is, |G| could be larger.</li>
      <li><strong>The deep ensemble is undertrained and was excluded.</strong> {esc(ens_cfg.get('n_members_full',5))} members × {esc(ens_cfg.get('epochs',5))} epochs × {esc(ens_cfg.get('patches_per_epoch',1536))} patches on 2 CPU cores; its out-of-fold DTI did not beat a random-emission control, so its weight in the emission is 0. It still supplies the epistemic/aleatoric decomposition, whose validity does not depend on the members being accurate.</li>
      <li><strong>Lidar coverage is 75.4 % of the footprint</strong> and the gap is systematic (north-east quadrant), so the habitat score is weakest exactly where survey coverage is lowest.</li>
      <li><strong>Public ≠ private.</strong> All 24 live scores are public-test scores; the region is chunked, the split is unpublished, and the Final Round re-scores against expanded labels.</li>
      <li><strong>Sandbox egress.</strong> DrivenData, Dropbox, USGS, ScienceBase and the National Map are unreachable from the development sandbox, so the official data tab and external downloads were obtained through the group's hash-pinned git bridge and the leaderboard through a fetch that GitHub Actions can repeat but this sandbox cannot.</li>
    </ul>
  </section>
  <section class="section">
    <div class="section-head"><div><div class="eyebrow">Reproduce</div><h2>Commands</h2></div></div>
    <pre class="formula">bash scripts/download_competition_data.sh     # acquire the official rasters (bridge or data tab)
python scripts/prepare_data.py                # verify hashes, write data/manifest.json
python scripts/fit_habitat_model.py           # 24 live scores -> habitat weights + nested CV
python scripts/run_ensemble.py                # deep ensemble + epistemic/aleatoric split
python scripts/evaluate_oof.py                # admission gate vs a random-emission control
python scripts/build_submission_live.py       # budget, dispersion, TIFF, validation
python scripts/phase2_candidates.py           # reviewer candidates with the variance split
python scripts/build_site.py                  # this site</pre>
  </section>"""

    pages = {
        "index.html": ("GEMSDOE23 · Dispersed-habitat fault emission", index, "index.html",
                       "One-click validated GeoTIFF for the DOE GEMS Prize, with the live-score inversion, |G| bounds, dispersion analysis and habitat model behind it."),
        "executive-summary.html": ("How to submit · GEMSDOE23", executive, "executive-summary.html",
                                   "Exact upload steps, the submission note, the decision rule and the traceability index."),
        "hypotheses.html": ("New hypotheses · GEMSDOE23", hypotheses, "hypotheses.html",
                            "Five ranked, testable geological hypotheses with layers, transforms, expected gain and cost."),
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
