"""
CAAR Dashboard Builder
=======================
Takes caar_all_enriched.json and builds the password-protected HTML dashboard
that will be served at jurisnair.com/caar-tracker.html

Output: caar-tracker.html  (in the script's working directory)
"""

import json
import sys
from datetime import datetime
from collections import Counter


# ==== PASSWORD - same as BHC tracker ====
DASHBOARD_PASSWORD = "sanjradhappu110305#"


def build_dashboard_data(records):
    """Compute pre-aggregated stats from records."""
    total = len(records)

    def bench_of(r):
        return 'Mumbai' if 'Mumbai' in r['section'] else 'Delhi'

    section_counts = Counter(r['section'] for r in records)
    bench_counts = Counter(bench_of(r) for r in records)

    # Year x Section (for timeline)
    year_section = {}
    for r in records:
        y = r.get('year', '')
        if not y:
            continue
        year_section.setdefault(y, {s: 0 for s in
            ['Mumbai Rulings', 'Mumbai Orders', 'Delhi Rulings', 'Delhi Orders']})
        year_section[y][r['section']] += 1

    # PDF heatmap
    pdf_heatmap = {}
    for r in records:
        y = r.get('year', '')
        if not y:
            continue
        pdf_heatmap.setdefault(y, {})
        pdf_heatmap[y].setdefault(r['section'], {'total': 0, 'with_pdf': 0})
        pdf_heatmap[y][r['section']]['total'] += 1
        if r.get('pdf_available') == 'YES':
            pdf_heatmap[y][r['section']]['with_pdf'] += 1

    return {
        'total': total,
        'section_counts': dict(section_counts),
        'bench_counts': dict(bench_counts),
        'pdf_yes': sum(1 for r in records if r.get('pdf_available') == 'YES'),
        'pdf_no': sum(1 for r in records if r.get('pdf_available') == 'NO'),
        'year_section': year_section,
        'issue_counts': dict(Counter(r.get('issue_type', '') for r in records)),
        'top_applicants': Counter(r['applicant'].strip()
                                  for r in records if r.get('applicant')).most_common(15),
        'pdf_heatmap': pdf_heatmap,
        'records': records,
        'last_updated': datetime.utcnow().strftime('%d %b %Y %H:%M UTC'),
    }


def build_html(dashboard_data, password):
    data_json = json.dumps(dashboard_data, ensure_ascii=False, separators=(',', ':'))
    last_updated = dashboard_data['last_updated']

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>CAAR Tracker | Juris Nair</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --gold: #B8974A; --gold-light: #D4B878;
  --dark: #0E0E0E; --dark2: #161616; --dark3: #1E1E1E;
  --text: #E8E0D0; --text-muted: #9A9080;
  --border: rgba(184,151,74,0.2);
  --green: #4ADE80; --yellow: #FBBF24; --red: #F87171;
  --blue: #60A5FA; --purple: #C084FC;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--dark); color: var(--text);
  font-family: 'DM Sans', sans-serif; font-weight: 300;
  line-height: 1.6; min-height: 100vh;
}

/* ========== AUTH GATE ========== */
.gate {
  position: fixed; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--dark); z-index: 1000;
}
.gate-box {
  background: var(--dark3); border: 1px solid var(--border);
  padding: 3rem 2.5rem; border-radius: 4px;
  max-width: 400px; width: 90%; text-align: center;
}
.gate-brand {
  font-family: 'Cormorant Garamond', serif;
  font-size: 1.3rem; font-weight: 600; color: var(--gold);
  letter-spacing: 0.05em; margin-bottom: 0.3rem;
}
.gate-title {
  font-family: 'Cormorant Garamond', serif;
  font-size: 1.8rem; margin-bottom: 0.5rem;
}
.gate-subtitle { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 2rem; }
.gate-input {
  width: 100%; padding: 0.8rem 1rem;
  background: var(--dark2); border: 1px solid var(--border);
  color: var(--text); font-family: 'DM Sans', sans-serif;
  font-size: 0.95rem; border-radius: 2px; margin-bottom: 1rem;
  outline: none;
}
.gate-input:focus { border-color: var(--gold); }
.gate-btn {
  width: 100%; padding: 0.8rem;
  background: var(--gold); color: var(--dark);
  border: none; font-family: 'DM Sans', sans-serif;
  font-size: 0.9rem; font-weight: 500; letter-spacing: 0.05em;
  text-transform: uppercase; cursor: pointer; border-radius: 2px;
  transition: background 0.3s;
}
.gate-btn:hover { background: var(--gold-light); }
.gate-error { color: var(--red); font-size: 0.82rem; margin-top: 1rem; min-height: 1rem; }

/* ========== MAIN ========== */
.main { display: none; padding: 2rem 2.5rem; }
.main.visible { display: block; }
.header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 1.5rem; margin-bottom: 2rem;
  display: flex; align-items: flex-end; justify-content: space-between;
  flex-wrap: wrap; gap: 1rem;
}
.brand {
  font-family: 'Cormorant Garamond', serif;
  font-size: 1.4rem; font-weight: 600; color: var(--gold);
  letter-spacing: 0.05em;
}
.page-tag {
  font-size: 0.7rem; letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--gold); border: 1px solid var(--border);
  padding: 0.3rem 0.8rem; display: inline-block; margin-bottom: 0.8rem;
}
h1 {
  font-family: 'Cormorant Garamond', serif;
  font-size: 2.5rem; font-weight: 600;
  line-height: 1.15; margin-bottom: 0.5rem;
}
h1 em { font-style: italic; color: var(--gold); }
.subtitle { color: var(--text-muted); font-size: 1rem; }
.scope-note { font-size: 0.78rem; color: var(--text-muted); text-align: right; }
.scope-note strong { color: var(--gold); font-weight: 500; }

.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: 1rem; margin-bottom: 2.5rem;
}
.kpi {
  background: var(--dark3); border: 1px solid var(--border);
  padding: 1.2rem; border-radius: 4px;
  position: relative; overflow: hidden;
}
.kpi::before {
  content: ''; position: absolute; top: 0; left: 0; height: 3px; width: 100%;
  background: linear-gradient(90deg, var(--gold), var(--gold-light));
}
.kpi-num {
  font-family: 'Cormorant Garamond', serif;
  font-size: 2.2rem; font-weight: 600; color: var(--gold);
  line-height: 1; margin-bottom: 0.3rem;
}
.kpi-label {
  font-size: 0.7rem; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--text-muted);
}

.section-tag {
  font-size: 0.7rem; letter-spacing: 0.18em;
  text-transform: uppercase; color: var(--gold);
  margin-bottom: 0.4rem;
}
.section-title {
  font-family: 'Cormorant Garamond', serif;
  font-size: 1.6rem; font-weight: 600;
  margin-bottom: 1rem; padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border);
}
.section-title em { font-style: italic; color: var(--gold); }
section { margin-bottom: 2.5rem; }

.charts-row { display: grid; gap: 1.2rem; margin-bottom: 1.5rem; }
.charts-row.cols-2 { grid-template-columns: 1fr 1fr; }
@media (max-width: 900px) { .charts-row.cols-2 { grid-template-columns: 1fr; } }
.chart-card {
  background: var(--dark3); border: 1px solid var(--border);
  padding: 1.4rem; border-radius: 4px;
}
.chart-title {
  font-size: 0.85rem; font-weight: 500;
  color: var(--text); margin-bottom: 1rem;
  letter-spacing: 0.04em;
}
.chart-subtitle {
  font-size: 0.74rem; color: var(--text-muted);
  font-style: italic; margin-top: 0.5rem;
}

.bar-row {
  display: grid;
  grid-template-columns: 130px 1fr 60px;
  align-items: center; gap: 0.8rem;
  margin-bottom: 0.55rem;
  font-size: 0.82rem;
}
.bar-track {
  height: 18px; background: var(--dark);
  border-radius: 2px; overflow: hidden;
  border: 1px solid var(--border);
}
.bar-fill {
  height: 100%; background: linear-gradient(90deg, var(--gold-light), var(--gold));
  border-radius: 2px;
}
.bar-val {
  color: var(--gold); font-weight: 500;
  text-align: right; font-variant-numeric: tabular-nums;
}

.timeline { display: flex; flex-direction: column; gap: 0.5rem; }
.timeline-row {
  display: grid;
  grid-template-columns: 60px 1fr 70px;
  align-items: center; gap: 0.8rem;
  font-size: 0.85rem;
}
.timeline-year { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.timeline-bar {
  height: 22px; background: var(--dark); border-radius: 2px;
  display: flex; overflow: hidden; border: 1px solid var(--border);
}
.timeline-bar > div {
  height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.65rem; color: var(--dark); font-weight: 600;
}
.timeline-total { color: var(--gold); font-weight: 500; font-variant-numeric: tabular-nums; }
.legend-row {
  display: flex; gap: 1.5rem; flex-wrap: wrap;
  font-size: 0.78rem; margin-top: 1rem;
  padding-top: 0.8rem; border-top: 1px solid var(--border);
}
.legend-item { display: flex; align-items: center; gap: 0.4rem; color: var(--text-muted); }
.legend-dot { width: 12px; height: 12px; border-radius: 2px; }

.heatmap { display: grid; gap: 2px; font-size: 0.75rem; }
.heatmap-row { display: grid; grid-template-columns: 50px repeat(4, 1fr); gap: 2px; }
.heatmap-cell { padding: 0.5rem 0.4rem; text-align: center; border-radius: 2px; font-variant-numeric: tabular-nums; }
.heatmap-cell.label { background: var(--dark2); color: var(--text-muted); text-align: right; font-weight: 500; }
.heatmap-cell.header { background: var(--dark2); color: var(--gold); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; }
.heatmap-cell.data { background: var(--dark3); color: var(--text); }
.heatmap-cell.high { background: rgba(74, 222, 128, 0.35); color: var(--text); }
.heatmap-cell.mid { background: rgba(251, 191, 36, 0.35); color: var(--text); }
.heatmap-cell.low { background: rgba(248, 113, 113, 0.35); color: var(--text); }
.heatmap-cell.empty { background: var(--dark); color: var(--text-muted); }

.filters {
  display: flex; gap: 0.7rem; flex-wrap: wrap;
  margin-bottom: 1rem; align-items: center;
  padding: 1rem; background: var(--dark3); border: 1px solid var(--border);
  border-radius: 4px;
}
.filter-label {
  font-size: 0.7rem; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--text-muted);
}
select, input[type="text"] {
  background: var(--dark2); color: var(--text);
  border: 1px solid var(--border); padding: 0.5rem 0.85rem;
  font-family: 'DM Sans', sans-serif; font-size: 0.85rem;
  border-radius: 2px; outline: none;
}
select:focus, input:focus { border-color: var(--gold); }
input[type="text"] { min-width: 220px; flex: 1; max-width: 320px; }
.clear-btn {
  background: transparent; color: var(--text-muted);
  border: 1px solid var(--border); padding: 0.5rem 0.85rem;
  font-family: 'DM Sans', sans-serif; font-size: 0.78rem;
  border-radius: 2px; cursor: pointer; transition: all 0.3s;
}
.clear-btn:hover { color: var(--gold); border-color: var(--gold); }

.table-wrap {
  background: var(--dark3); border: 1px solid var(--border);
  border-radius: 4px; overflow-x: auto;
}
table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
thead { background: var(--dark2); border-bottom: 2px solid var(--gold); position: sticky; top: 0; }
th {
  padding: 0.8rem 0.7rem; text-align: left;
  color: var(--gold); font-weight: 500; font-size: 0.7rem;
  letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap;
}
td {
  padding: 0.6rem 0.7rem;
  border-bottom: 1px solid var(--border); vertical-align: top;
  font-size: 0.82rem;
}
tr:hover td { background: rgba(184, 151, 74, 0.04); }
.pill {
  display: inline-block; padding: 0.15rem 0.55rem;
  font-size: 0.66rem; letter-spacing: 0.04em;
  border-radius: 2px; font-weight: 500; white-space: nowrap;
}
.pill.bench-mumbai { background: rgba(74,222,128,0.18); color: var(--green); }
.pill.pill.bench-delhi { background: rgba(251,191,36,0.18); color: var(--yellow); }
.pill.bench-delhi { background: rgba(251,191,36,0.18); color: var(--yellow); }
.pill.issue-classification { background: rgba(184,151,74,0.18); color: var(--gold); }
.pill.issue-exemption { background: rgba(96,165,250,0.18); color: var(--blue); }
.pill.issue-valuation { background: rgba(192,132,252,0.18); color: var(--purple); }
.pill.issue-procedural { background: rgba(154,144,128,0.18); color: var(--text-muted); }
.pill.issue-other { background: rgba(248,113,113,0.15); color: var(--red); }
.pill.pdf-no { background: rgba(248,113,113,0.18); color: var(--red); }
td a { color: var(--gold); text-decoration: none; }
td a:hover { text-decoration: underline; }
.result-count {
  font-size: 0.82rem; color: var(--text-muted);
  margin-top: 1rem;
}
.result-count strong { color: var(--gold); }

.update-banner {
  background: var(--dark3);
  border-left: 3px solid var(--green);
  padding: 0.7rem 1rem;
  margin-bottom: 1.5rem;
  font-size: 0.82rem;
  color: var(--text-muted);
  border-radius: 0 4px 4px 0;
}
.update-banner strong { color: var(--green); }
.update-banner .download-link {
  color: var(--gold); margin-left: 0.5rem; text-decoration: underline;
  cursor: pointer;
}

footer {
  margin-top: 3rem; padding-top: 1.5rem;
  border-top: 1px solid var(--border);
  text-align: center; font-size: 0.78rem;
  color: var(--text-muted);
}
footer strong { color: var(--gold); }

@media (max-width: 768px) {
  .main { padding: 1.5rem 1rem; }
  h1 { font-size: 1.8rem; }
}
</style>
</head>
<body>

<!-- AUTH GATE -->
<div class="gate" id="gate">
  <div class="gate-box">
    <div class="gate-brand">Juris Nair</div>
    <div class="gate-title">CAAR Tracker</div>
    <div class="gate-subtitle">Access requires team credentials.</div>
    <input type="password" id="gatePassword" class="gate-input" placeholder="Enter password" autofocus />
    <button class="gate-btn" onclick="checkPassword()">Enter</button>
    <div class="gate-error" id="gateError"></div>
  </div>
</div>

<!-- MAIN -->
<div class="main" id="main">

<div class="header">
  <div>
    <div class="brand">Juris Nair</div>
    <span class="page-tag">CAAR Tracker &middot; Auto-Updating</span>
    <h1>CAAR Litigation <em>Analytics</em></h1>
    <p class="subtitle">An evidence-led view of India's Customs Authority for Advance Rulings</p>
  </div>
  <div class="scope-note">
    Coverage: <strong>FY 2021 - 2026</strong><br>
    Benches: <strong>Mumbai &amp; New Delhi</strong><br>
    Last refresh: <strong>''' + last_updated + '''</strong>
  </div>
</div>

<div class="update-banner">
  <strong>Live dataset</strong> | This dashboard refreshes automatically every Sunday at 04:00 IST from the CBIC public portal. Underlying data: <a class="download-link" href="data/caar/caar_all_enriched.csv" download>CSV</a> &middot; <a class="download-link" href="data/caar/caar_all_enriched.json" download>JSON</a> &middot; <a class="download-link" href="data/caar/caar_analytics.xlsx" download>Excel</a>
</div>

<div class="kpis" id="kpiStrip"></div>

<section>
  <p class="section-tag">Volume Over Time</p>
  <h2 class="section-title">Year-on-Year <em>Activity</em></h2>
  <div class="chart-card">
    <div class="chart-title">Records per Year, Stacked by Section</div>
    <div id="timeline" class="timeline"></div>
    <div class="legend-row" id="timelineLegend"></div>
  </div>
</section>

<section>
  <p class="section-tag">Issue and Bench Distribution</p>
  <h2 class="section-title">Issue Type and <em>Top Applicants</em></h2>
  <div class="charts-row cols-2">
    <div class="chart-card">
      <div class="chart-title">Issue Type Composition</div>
      <div id="issueBars"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Most Frequent Applicants (Top 15)</div>
      <div id="topApplicants"></div>
    </div>
  </div>
</section>

<section>
  <p class="section-tag">Data Completeness</p>
  <h2 class="section-title">PDF Coverage <em>Heatmap</em></h2>
  <div class="chart-card">
    <div class="chart-title">PDF Availability by Year and Section</div>
    <div id="pdfHeatmap"></div>
    <div class="legend-row">
      <div class="legend-item"><span class="legend-dot" style="background: rgba(74,222,128,0.7)"></span>&ge; 90%</div>
      <div class="legend-item"><span class="legend-dot" style="background: rgba(251,191,36,0.7)"></span>70-90%</div>
      <div class="legend-item"><span class="legend-dot" style="background: rgba(248,113,113,0.7)"></span>&lt; 70%</div>
    </div>
  </div>
</section>

<section>
  <p class="section-tag">Underlying Data</p>
  <h2 class="section-title">Searchable <em>Register</em></h2>

  <div class="filters">
    <span class="filter-label">Filter:</span>
    <select id="fBench"><option value="">All Benches</option><option>Mumbai</option><option>Delhi</option></select>
    <select id="fType"><option value="">All Types</option><option>Rulings</option><option>Orders</option></select>
    <select id="fYear"><option value="">All Years</option></select>
    <select id="fIssue"><option value="">All Issues</option><option>Classification</option><option>Exemption</option><option>Valuation</option><option>Procedural</option><option>Country of Origin</option><option>Trade Remedy</option></select>
    <input type="text" id="fSearch" placeholder="Search applicant, subject, ruling no..." />
    <button class="clear-btn" onclick="clearFilters()">Clear</button>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="width:40px;">#</th>
          <th>Section</th>
          <th>Applicant</th>
          <th>Date of Ruling</th>
          <th>Issue Type</th>
          <th>Subject</th>
          <th>Ruling No.</th>
          <th>PDF</th>
        </tr>
      </thead>
      <tbody id="recordsBody"></tbody>
    </table>
  </div>
  <p class="result-count">Showing <strong id="visibleCount">0</strong> of <strong id="totalCount">0</strong> records</p>
</section>

<footer>
  <strong>Juris Nair</strong> &middot; CAAR Tracker &middot; Updated automatically from cbic.gov.in &middot; Confidential
</footer>

</div>

<script>
// ===== AUTH =====
const PASSWORD = "''' + password + '''";

function checkPassword() {
  const input = document.getElementById('gatePassword').value;
  if (input === PASSWORD) {
    sessionStorage.setItem('caar_unlocked', '1');
    showMain();
  } else {
    document.getElementById('gateError').textContent = 'Incorrect password';
    document.getElementById('gatePassword').value = '';
    document.getElementById('gatePassword').focus();
  }
}

function showMain() {
  document.getElementById('gate').style.display = 'none';
  document.getElementById('main').classList.add('visible');
}

document.getElementById('gatePassword').addEventListener('keypress', function(e) {
  if (e.key === 'Enter') checkPassword();
});

if (sessionStorage.getItem('caar_unlocked') === '1') {
  showMain();
}

// ===== DATA =====
const DATA = ''' + data_json + ''';

function fmt(n) { return typeof n === 'number' ? n.toLocaleString('en-IN') : n; }
function pct(n, total) { return total ? (n/total*100).toFixed(1) + '%' : '0%'; }
function escapeHtml(s) { return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }

// ===== KPIs =====
const kpis = [
  { num: DATA.total, label: 'Total Records' },
  { num: DATA.section_counts['Mumbai Rulings'] || 0, label: 'Mumbai Rulings' },
  { num: DATA.section_counts['Mumbai Orders'] || 0, label: 'Mumbai Orders' },
  { num: DATA.section_counts['Delhi Rulings'] || 0, label: 'Delhi Rulings' },
  { num: DATA.section_counts['Delhi Orders'] || 0, label: 'Delhi Orders' },
  { num: pct(DATA.pdf_yes, DATA.total), label: 'PDF Coverage' },
];
document.getElementById('kpiStrip').innerHTML = kpis.map(k =>
  `<div class="kpi"><div class="kpi-num">${fmt(k.num)}</div><div class="kpi-label">${k.label}</div></div>`
).join('');

// ===== TIMELINE =====
const sectionColors = {
  'Mumbai Rulings': '#B8974A', 'Mumbai Orders': '#D4B878',
  'Delhi Rulings': '#60A5FA', 'Delhi Orders': '#93C5FD',
};
const years = Object.keys(DATA.year_section).sort();
let timelineMax = 0;
years.forEach(y => {
  const t = Object.values(DATA.year_section[y]).reduce((a,b)=>a+b, 0);
  if (t > timelineMax) timelineMax = t;
});
document.getElementById('timeline').innerHTML = years.map(y => {
  const counts = DATA.year_section[y];
  const total = Object.values(counts).reduce((a,b)=>a+b, 0);
  const widthRatio = (total / timelineMax * 100).toFixed(1);
  const segments = Object.entries(counts).filter(([_,v]) => v > 0).map(([sec, v]) => {
    const segPct = (v / total * 100).toFixed(1);
    return `<div style="width:${segPct}%; background:${sectionColors[sec]};" title="${sec}: ${v}">${v >= 30 ? v : ''}</div>`;
  }).join('');
  return `<div class="timeline-row">
    <div class="timeline-year">${y}</div>
    <div class="timeline-bar" style="width:${widthRatio}%">${segments}</div>
    <div class="timeline-total">${total}</div>
  </div>`;
}).join('');
document.getElementById('timelineLegend').innerHTML = Object.entries(sectionColors).map(([sec, col]) =>
  `<div class="legend-item"><span class="legend-dot" style="background:${col}"></span>${sec}</div>`
).join('');

// ===== ISSUE BARS =====
const issueOrder = ['Classification', 'Procedural', 'Exemption', 'Valuation', 'Country of Origin', 'Trade Remedy', 'Other / Unclear', 'Unspecified'];
const maxIssue = Math.max(...Object.values(DATA.issue_counts));
document.getElementById('issueBars').innerHTML = issueOrder
  .filter(k => DATA.issue_counts[k])
  .map(k => {
    const v = DATA.issue_counts[k];
    const w = (v / maxIssue * 100).toFixed(1);
    return `<div class="bar-row">
      <div>${k}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${w}%"></div></div>
      <div class="bar-val">${v}</div>
    </div>`;
  }).join('');

// ===== TOP APPLICANTS =====
if (DATA.top_applicants.length > 0) {
  const maxApp = DATA.top_applicants[0][1];
  document.getElementById('topApplicants').innerHTML = DATA.top_applicants.map(([name, count]) => {
    const w = (count / maxApp * 100).toFixed(1);
    let cleanName = name.replace(/^M\\/[Ss]\\.?\\s*/, '').trim();
    const m = cleanName.match(/^(.{1,55}?(?:Ltd\\.?|Limited|LLP|Pvt|Inc\\.?|Corp\\.?|Co\\.?)\\b)/i);
    if (m) cleanName = m[1];
    else cleanName = cleanName.substring(0, 55) + (cleanName.length > 55 ? '...' : '');
    return `<div class="bar-row" style="grid-template-columns: 220px 1fr 50px;">
      <div title="${escapeHtml(name)}" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(cleanName)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${w}%"></div></div>
      <div class="bar-val">${count}</div>
    </div>`;
  }).join('');
}

// ===== PDF HEATMAP =====
const heatYears = Object.keys(DATA.pdf_heatmap).sort();
const heatSections = ['Mumbai Rulings', 'Mumbai Orders', 'Delhi Rulings', 'Delhi Orders'];
let heatHtml = '<div class="heatmap-row"><div class="heatmap-cell header"></div>';
heatSections.forEach(s => {
  heatHtml += `<div class="heatmap-cell header">${s.replace('Mumbai ','M ').replace('Delhi ','D ')}</div>`;
});
heatHtml += '</div>';
heatYears.forEach(y => {
  heatHtml += `<div class="heatmap-row"><div class="heatmap-cell label">${y}</div>`;
  heatSections.forEach(s => {
    const cell = DATA.pdf_heatmap[y][s];
    if (!cell || cell.total === 0) {
      heatHtml += '<div class="heatmap-cell empty">-</div>';
    } else {
      const ratio = cell.with_pdf / cell.total;
      let cls = ratio >= 0.9 ? 'high' : ratio >= 0.7 ? 'mid' : 'low';
      heatHtml += `<div class="heatmap-cell ${cls}" title="${cell.with_pdf} of ${cell.total} have PDFs">${(ratio*100).toFixed(0)}%<br><span style="font-size:0.65rem; opacity:0.65;">(${cell.total})</span></div>`;
    }
  });
  heatHtml += '</div>';
});
document.getElementById('pdfHeatmap').innerHTML = heatHtml;

// ===== TABLE =====
function bench(r) { return r.section.includes('Mumbai') ? 'Mumbai' : 'Delhi'; }
function docType(r) { return r.section.includes('Rulings') ? 'Rulings' : 'Orders'; }
function issueClass(it) {
  const slug = it.toLowerCase().split(/[\\s\\/]+/)[0];
  return 'issue-' + (['classification','exemption','valuation','procedural','trade'].includes(slug) ? slug : 'other');
}

const allYears = [...new Set(DATA.records.map(r => r.year).filter(Boolean))].sort();
const yearSelect = document.getElementById('fYear');
allYears.forEach(y => {
  const opt = document.createElement('option');
  opt.value = y; opt.textContent = y;
  yearSelect.appendChild(opt);
});

function transformPdfUrl(originalUrl) {
  if (!originalUrl) return '';
  return originalUrl.replace('/CONTENTREPO/', '/content/pdf/CONTENTREPO/');
}

function renderTable() {
  const fb = document.getElementById('fBench').value;
  const ft = document.getElementById('fType').value;
  const fy = document.getElementById('fYear').value;
  const fi = document.getElementById('fIssue').value;
  const fs = document.getElementById('fSearch').value.toLowerCase().trim();

  let visible = 0;
  let html = '';

  for (const r of DATA.records) {
    if (fb && bench(r) !== fb) continue;
    if (ft && docType(r) !== ft) continue;
    if (fy && r.year !== fy) continue;
    if (fi && r.issue_type !== fi) continue;
    if (fs) {
      const blob = (r.applicant + ' ' + r.subject + ' ' + r.ruling_no).toLowerCase();
      if (blob.indexOf(fs) === -1) continue;
    }
    visible++;
    html += `<tr>
      <td>${visible}</td>
      <td><span class="pill bench-${bench(r).toLowerCase()}">${escapeHtml(r.section)}</span></td>
      <td>${escapeHtml(r.applicant)}</td>
      <td style="white-space:nowrap;">${escapeHtml(r.date_ruling)}</td>
      <td><span class="pill ${issueClass(r.issue_type)}">${escapeHtml(r.issue_type)}</span></td>
      <td style="font-size:0.78rem; color:var(--text-muted);">${escapeHtml(r.subject)}</td>
      <td style="font-family:monospace; font-size:0.73rem;">${escapeHtml(r.ruling_no)}</td>
      <td>${r.pdf_link ? `<a href="${transformPdfUrl(r.pdf_link)}" target="_blank" rel="noopener">PDF</a>` : '<span class="pill pdf-no">-</span>'}</td>
    </tr>`;
  }

  if (visible === 0) {
    html = '<tr><td colspan="8" style="text-align:center; padding:2rem; color:var(--text-muted);">No matches. Adjust filters.</td></tr>';
  }

  document.getElementById('recordsBody').innerHTML = html;
  document.getElementById('visibleCount').textContent = fmt(visible);
  document.getElementById('totalCount').textContent = fmt(DATA.records.length);
}

function clearFilters() {
  ['fBench','fType','fYear','fIssue','fSearch'].forEach(id => document.getElementById(id).value = '');
  renderTable();
}

['fBench','fType','fYear','fIssue','fSearch'].forEach(id => {
  document.getElementById(id).addEventListener('change', renderTable);
  document.getElementById(id).addEventListener('input', renderTable);
});

renderTable();
</script>

</body>
</html>
'''
    return html


def main():
    print("Building CAAR tracker dashboard...")

    try:
        with open('caar_all_enriched.json', 'r', encoding='utf-8') as f:
            records = json.load(f)
    except FileNotFoundError:
        print("ERROR: caar_all_enriched.json not found. Run postprocess.py first.")
        sys.exit(1)

    dashboard_data = build_dashboard_data(records)
    html = build_html(dashboard_data, DASHBOARD_PASSWORD)

    out_path = 'caar-tracker.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Dashboard built: {out_path}")
    print(f"  Records:        {dashboard_data['total']}")
    print(f"  Last updated:   {dashboard_data['last_updated']}")


if __name__ == "__main__":
    main()
