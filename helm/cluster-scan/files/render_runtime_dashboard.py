#!/usr/bin/env python3
"""Render a dark-mode native runtime vulnerability dashboard as a standalone HTML file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", help="Directory containing runtime reporting JSON files")
    parser.add_argument("output_html", help="Path to write dashboard HTML")
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    summary = load_json(report_dir / "runtime-vulnerability-summary.json")
    clusters = load_json(report_dir / "cluster-runtime-vulnerability-report.json")
    workloads = load_json(report_dir / "workload-vulnerability-dashboard.json")
    applications = load_json(report_dir / "application-vulnerability-dashboard.json")
    images = load_json(report_dir / "runtime-artifacts.json")

    payload = {
        "summary": summary,
        "clusters": clusters,
        "workloads": workloads,
        "applications": applications,
        "images": images,
    }

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>cluster-scan runtime dashboard</title>
  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap\" rel=\"stylesheet\">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08090a;
      --panel: #0f1011;
      --surface: rgba(255,255,255,0.03);
      --surface-strong: rgba(255,255,255,0.05);
      --border: rgba(255,255,255,0.08);
      --border-soft: rgba(255,255,255,0.05);
      --text: #f7f8f8;
      --muted: #8a8f98;
      --soft: #d0d6e0;
      --accent: #7170ff;
      --accent-bg: #5e6ad2;
      --danger: #ff6b7a;
      --warn: #f6b73c;
      --ok: #10b981;
      --radius: 12px;
      --shadow: rgba(0,0,0,0.28) 0 10px 30px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: 'Inter', system-ui, sans-serif;
      background: radial-gradient(circle at top, rgba(113,112,255,0.12), transparent 30%), var(--bg);
      color: var(--text);
    }}
    .shell {{ max-width: 1480px; margin: 0 auto; padding: 32px 24px 48px; }}
    .hero {{ display: grid; gap: 20px; margin-bottom: 28px; }}
    .eyebrow {{ color: var(--accent); font-size: 12px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: clamp(2rem, 4vw, 3.8rem); line-height: 1; letter-spacing: -0.06em; font-weight: 600; }}
    .lede {{ max-width: 900px; color: var(--muted); font-size: 1rem; line-height: 1.7; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 24px 0 28px; }}
    .card {{ background: var(--surface); border: 1px solid var(--border-soft); border-radius: var(--radius); box-shadow: var(--shadow); }}
    .metric {{ padding: 18px; }}
    .metric .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .metric .value {{ font-size: 32px; font-weight: 600; letter-spacing: -0.04em; margin-top: 8px; }}
    .metric .hint {{ color: var(--soft); font-size: 13px; margin-top: 8px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 18px; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .tab {{
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--border-soft);
      border-radius: 999px;
      padding: 10px 14px;
      color: var(--soft);
      cursor: pointer;
      font: inherit;
    }}
    .tab.active {{ background: var(--accent-bg); color: white; border-color: transparent; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .search {{
      width: min(320px, 100%);
      background: rgba(255,255,255,0.02);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 11px 14px;
      outline: none;
    }}
    .download {{
      text-decoration: none;
      color: var(--soft);
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--border-soft);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 13px;
    }}
    .panel {{ display: none; padding: 18px; }}
    .panel.active {{ display: block; }}
    .panel h2 {{ margin: 0 0 6px; font-size: 1.25rem; }}
    .panel .sub {{ margin: 0 0 18px; color: var(--muted); }}
    .list {{ display: grid; gap: 12px; }}
    .row {{ padding: 16px; border: 1px solid var(--border-soft); border-radius: 12px; background: rgba(255,255,255,0.02); }}
    .row-head {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 10px; }}
    .title {{ font-size: 16px; font-weight: 600; }}
    .meta {{ color: var(--muted); font-size: 13px; display: flex; flex-wrap: wrap; gap: 10px; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .chip {{ padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,0.04); border: 1px solid var(--border-soft); color: var(--soft); font-size: 12px; }}
    .sev {{ display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--soft); }}
    .badge {{ padding: 6px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
    .critical {{ background: rgba(255,107,122,0.12); color: #ff9cab; border: 1px solid rgba(255,107,122,0.2); }}
    .high {{ background: rgba(246,183,60,0.12); color: #ffd27b; border: 1px solid rgba(246,183,60,0.2); }}
    .clean {{ background: rgba(16,185,129,0.12); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.2); }}
    .mono {{ font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; }}
    .two-col {{ display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, .9fr); gap: 14px; }}
    .sidebox {{ padding: 16px; border-left: 1px solid var(--border-soft); }}
    .empty {{ color: var(--muted); padding: 18px; border: 1px dashed var(--border-soft); border-radius: 12px; text-align: center; }}
    @media (max-width: 980px) {{ .two-col {{ grid-template-columns: 1fr; }} .sidebox {{ border-left: none; border-top: 1px solid var(--border-soft); }} }}
  </style>
</head>
<body>
  <div class=\"shell\">
    <section class=\"hero\">
      <div class=\"eyebrow\">cluster-scan</div>
      <h1>Nightly runtime vulnerability dashboard</h1>
      <p class=\"lede\">Cluster inventory is deduplicated for scanning, then re-consolidated for reporting so you can see what is actually running, where it is running, and how ugly the vuln story currently is.</p>
    </section>

    <section class=\"summary-grid\" id=\"summary-grid\"></section>

    <section class=\"toolbar\">
      <div class=\"tabs\" id=\"tabs\"></div>
      <div class=\"actions\">
        <input id=\"search\" class=\"search\" placeholder=\"Search clusters, workloads, apps, images...\" />
        <a class=\"download\" href=\"runtime-vulnerability-summary.json\" download>Summary JSON</a>
        <a class=\"download\" href=\"workload-vulnerability-dashboard.json\" download>Workloads JSON</a>
        <a class=\"download\" href=\"application-vulnerability-dashboard.json\" download>Apps JSON</a>
        <a class=\"download\" href=\"cluster-runtime-vulnerability-report.json\" download>Clusters JSON</a>
        <a class=\"download\" href=\"runtime-artifacts.json\" download>Images JSON</a>
      </div>
    </section>

    <section class=\"card panel active\" data-panel=\"workloads\">
      <h2>Per workload</h2>
      <p class=\"sub\">Flattened by cluster / namespace / workload. This is the fastest way to answer “what exact thing is running the bad image?”</p>
      <div id=\"workloads\" class=\"list\"></div>
    </section>

    <section class=\"card panel\" data-panel=\"apps\">
      <h2>Per app</h2>
      <p class=\"sub\">App rollup across all workloads, clusters, and namespaces using app labels when available and workload names as fallback.</p>
      <div id=\"apps\" class=\"list\"></div>
    </section>

    <section class=\"card panel\" data-panel=\"clusters\">
      <h2>Per cluster</h2>
      <p class=\"sub\">Nested runtime view for cluster, namespace, and workload ownership.</p>
      <div id=\"clusters\" class=\"list\"></div>
    </section>

    <section class=\"card panel\" data-panel=\"images\">
      <h2>Per unique image</h2>
      <p class=\"sub\">The deduped image scan layer. Efficient for scanning, still tied back to sightings for blast-radius reporting.</p>
      <div id=\"images\" class=\"list\"></div>
    </section>
  </div>

  <script id=\"dashboard-data\" type=\"application/json\">{json.dumps(payload)}</script>
  <script>
    const data = JSON.parse(document.getElementById('dashboard-data').textContent);
    const tabs = [
      ['workloads', 'Workloads'],
      ['apps', 'Apps'],
      ['clusters', 'Clusters'],
      ['images', 'Images'],
    ];
    const summaryGrid = document.getElementById('summary-grid');
    const searchInput = document.getElementById('search');
    const tabWrap = document.getElementById('tabs');
    const panels = [...document.querySelectorAll('.panel')];

    function sevBadge(summary) {{
      const critical = Number(summary?.critical || 0);
      const high = Number(summary?.high || 0);
      if (critical > 0) return `<span class=\"badge critical\">${{critical}} critical / ${{high}} high</span>`;
      if (high > 0) return `<span class=\"badge high\">${{high}} high</span>`;
      return `<span class=\"badge clean\">clean</span>`;
    }}

    function summaryCards() {{
      const cards = [
        ['Clusters', data.summary.clusterCount, 'Clusters scanned nightly'],
        ['Workloads', data.summary.workloadCount, 'Flattened runtime workload entries'],
        ['Apps', data.summary.applicationCount, 'Application rollups for dashboarding'],
        ['Unique Images', data.summary.uniqueRuntimeImageCount, 'Deduped images scanned once'],
        ['Containers', data.summary.containerCount, 'Total runtime containers represented'],
        ['Exposed Containers', data.summary.containersWithHighOrCritical, 'Containers tied to high/critical findings'],
      ];
      summaryGrid.innerHTML = cards.map(([label, value, hint]) => `
        <div class=\"card metric\">
          <div class=\"label\">${{label}}</div>
          <div class=\"value\">${{value}}</div>
          <div class=\"hint\">${{hint}}</div>
        </div>
      `).join('');
    }}

    function renderTabs() {{
      tabWrap.innerHTML = tabs.map(([key, label], idx) => `<button class=\"tab ${{idx === 0 ? 'active' : ''}}\" data-tab=\"${{key}}\">${{label}}</button>`).join('');
      tabWrap.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => setPanel(btn.dataset.tab)));
    }}

    function setPanel(key) {{
      document.querySelectorAll('.tab').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === key));
      panels.forEach(panel => panel.classList.toggle('active', panel.dataset.panel === key));
      renderAll();
    }}

    function matchesQuery(parts, query) {{
      if (!query) return true;
      return parts.filter(Boolean).join(' ').toLowerCase().includes(query);
    }}

    function renderWorkloads(query) {{
      const root = document.getElementById('workloads');
      const items = data.workloads.filter(item => matchesQuery([
        item.clusterName, item.namespace, item.workloadKind, item.workloadName, item.appName,
        ...(item.images || [])
      ], query));
      root.innerHTML = items.length ? items.map(item => `
        <div class=\"row\">
          <div class=\"row-head\">
            <div>
              <div class=\"title\">${{item.workloadKind}} / ${{item.workloadName}}</div>
              <div class=\"meta\"><span>${{item.clusterName}} / ${{item.namespace}}</span><span>app: ${{item.appName || 'n/a'}}</span><span>owner: ${{item.ownerTeam || 'n/a'}}</span></div>
            </div>
            ${{sevBadge({{ critical: item.summary.maxCritical, high: item.summary.maxHigh }})}}
          </div>
          <div class=\"chips\">${{(item.images || []).map(image => `<span class=\"chip mono\">${{image}}</span>`).join('')}}</div>
          <div class=\"meta\" style=\"margin-top: 12px;\"><span>${{item.summary.containerCount}} containers</span><span>${{item.summary.highOrCriticalContainerCount}} vulnerable containers</span><span>${{item.summary.fixableHighOrCriticalContainerCount}} fixable containers</span></div>
        </div>
      `).join('') : `<div class=\"empty\">No workload rows match the current search.</div>`;
    }}

    function renderApps(query) {{
      const root = document.getElementById('apps');
      const items = data.applications.filter(item => matchesQuery([
        item.appName, ...(item.clusters || []), ...(item.images || []), ...(item.ownerTeams || [])
      ], query));
      root.innerHTML = items.length ? items.map(item => `
        <div class=\"row two-col\">
          <div style=\"padding:16px;\">
            <div class=\"row-head\">
              <div>
                <div class=\"title\">${{item.appName}}</div>
                <div class=\"meta\"><span>clusters: ${{item.clusters.length}}</span><span>workloads: ${{item.summary.workloadCount}}</span><span>owners: ${{(item.ownerTeams || []).join(', ') || 'n/a'}}</span></div>
              </div>
              ${{sevBadge({{ critical: item.summary.maxCritical, high: item.summary.maxHigh }})}}
            </div>
            <div class=\"chips\">${{(item.images || []).slice(0, 8).map(image => `<span class=\"chip mono\">${{image}}</span>`).join('')}}</div>
            <div class=\"meta\" style=\"margin-top:12px;\"><span>${{item.summary.containerCount}} containers</span><span>${{item.summary.highOrCriticalContainerCount}} vulnerable containers</span><span>${{item.summary.fixableHighOrCriticalContainerCount}} fixable containers</span></div>
          </div>
          <div class=\"sidebox\">
            <div class=\"meta\" style=\"margin-bottom:10px; color: var(--soft);\">Workloads</div>
            <div class=\"list\">${{(item.workloads || []).map(w => `<div class=\"meta\"><span>${{w.clusterName}} / ${{w.namespace}}</span><span>${{w.workloadKind}} / ${{w.workloadName}}</span></div>`).join('')}}</div>
          </div>
        </div>
      `).join('') : `<div class=\"empty\">No app rows match the current search.</div>`;
    }}

    function renderClusters(query) {{
      const root = document.getElementById('clusters');
      const items = data.clusters.filter(item => matchesQuery([item.clusterName], query));
      root.innerHTML = items.length ? items.map(cluster => `
        <div class=\"row\">
          <div class=\"row-head\">
            <div>
              <div class=\"title\">${{cluster.clusterName}}</div>
              <div class=\"meta\"><span>${{cluster.summary.namespaceCount}} namespaces</span><span>${{cluster.summary.imageCount}} images</span><span>${{cluster.summary.containerCount}} containers</span></div>
            </div>
            <span class=\"badge ${{cluster.summary.highOrCriticalContainerCount > 0 ? 'high' : 'clean'}}\">${{cluster.summary.highOrCriticalContainerCount}} vulnerable containers</span>
          </div>
          <div class=\"list\">${{(cluster.namespaces || []).map(ns => `<div class=\"row\" style=\"margin-top:8px;\"><div class=\"title\" style=\"font-size:14px;\">${{ns.namespace}}</div><div class=\"meta\"><span>${{ns.summary.workloadCount}} workloads</span><span>${{ns.summary.containerCount}} containers</span><span>${{ns.summary.highOrCriticalContainerCount}} vulnerable containers</span></div></div>`).join('')}}</div>
        </div>
      `).join('') : `<div class=\"empty\">No cluster rows match the current search.</div>`;
    }}

    function renderImages(query) {{
      const root = document.getElementById('images');
      const items = data.images.filter(item => matchesQuery([
        item.image, item.normalizedImageName, item.canonicalKey, ...(item.clusters || [])
      ], query));
      root.innerHTML = items.length ? items.map(item => `
        <div class=\"row\">
          <div class=\"row-head\">
            <div>
              <div class=\"title mono\">${{item.image || item.normalizedImageName}}</div>
              <div class=\"meta\"><span>${{item.sightingCount}} sightings</span><span>${{(item.clusters || []).length}} clusters</span><span>family: ${{item.scan?.baseFamily || 'unmatched'}}</span></div>
            </div>
            ${{sevBadge(item.scan?.summary || {{}})}}
          </div>
          <div class=\"chips\">${{(item.sightings || []).slice(0, 10).map(s => `<span class=\"chip\">${{s.clusterName || 'cluster'}} / ${{s.namespace || 'ns'}} / ${{s.workloadName || s.appName || s.podName || 'workload'}}</span>`).join('')}}</div>
        </div>
      `).join('') : `<div class=\"empty\">No image rows match the current search.</div>`;
    }}

    function renderAll() {{
      const query = searchInput.value.trim().toLowerCase();
      renderWorkloads(query);
      renderApps(query);
      renderClusters(query);
      renderImages(query);
    }}

    searchInput.addEventListener('input', renderAll);
    summaryCards();
    renderTabs();
    renderAll();
  </script>
</body>
</html>"""

    Path(args.output_html).write_text(html)


if __name__ == "__main__":
    main()
