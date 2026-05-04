#!/usr/bin/env python3
"""
Generate a self-contained ERC or DRC report page (HTML5).

Reads a .rpt (plain text) and .json file produced by `kicad-cli`, embeds
their contents inline, and writes a single HTML file with:

  - Valid HTML5 structure (<!DOCTYPE html>, <html>, <head>, <body>)
  - charset + viewport meta tags
  - Inline CSS, no external dependencies
  - Heading: "ERC Report" or "DRC Report"
  - Summary card (count of errors / warnings parsed from the JSON)
  - Tabular violation list when JSON is valid; preformatted .rpt text fallback
  - "Download .rpt" and "Download .json" buttons (Blob-based, work offline)

Usage:
    python3 generate_report_page.py \
        --kind erc \
        --rpt output/reports/erc.rpt \
        --json output/reports/erc.json \
        --output output/reports/erc-erc.html \
        --project Nano-Board-rev-2
"""
import argparse
import html
import json
import pathlib
import sys


def parse_json_violations(data):
    """Walk a kicad-cli ERC/DRC JSON tree and collect violation rows."""
    if not isinstance(data, dict):
        return []
    rows = []

    def push(items):
        for v in items or []:
            if not isinstance(v, dict):
                continue
            sev = (v.get("severity") or "").lower()
            code = v.get("type") or v.get("code") or ""
            desc = v.get("description") or v.get("message") or ""
            items_field = v.get("items") or []
            refs = []
            for it in items_field if isinstance(items_field, list) else []:
                if isinstance(it, dict):
                    d = it.get("description") or ""
                    if d:
                        refs.append(d)
            rows.append({
                "severity": sev,
                "code": code,
                "description": desc,
                "items": " | ".join(refs),
            })

    # ERC structure: data['sheets'][i]['violations']
    for sh in data.get("sheets", []) or []:
        push(sh.get("violations"))

    # DRC structure: top-level 'violations' / 'unconnected_items' / 'schematic_parity'
    for k in ("violations", "unconnected_items", "schematic_parity"):
        push(data.get(k))

    return rows


def base64_data_url(path, mime):
    import base64
    raw = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg: #f6f8fa; --panel: #ffffff; --line: #d0d7de; --text: #1f2328;
    --muted: #57606a; --accent: #0969da; --error: #cf222e; --warn: #9a6700;
    --ok: #1a7f37;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
  }}
  header {{
    background: var(--panel); border-bottom: 1px solid var(--line);
    padding: 24px 32px; display: flex; justify-content: space-between;
    align-items: center; flex-wrap: wrap; gap: 12px;
  }}
  header h1 {{ margin: 0; font-size: 22px; }}
  header .meta {{ color: var(--muted); font-size: 13px; }}
  main {{ max-width: 1200px; margin: 24px auto; padding: 0 24px 48px; }}
  .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }}
  .btn {{
    appearance: none; border: 1px solid var(--line); background: var(--panel);
    color: var(--text); padding: 8px 14px; border-radius: 6px; cursor: pointer;
    font-size: 13px; font-weight: 500; text-decoration: none; display: inline-block;
  }}
  .btn:hover {{ background: #eef2f6; }}
  .btn.primary {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .btn.primary:hover {{ background: #0860c5; }}
  .summary {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }}
  .card {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
    padding: 16px;
  }}
  .card .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
  .card .value {{ font-size: 28px; font-weight: 600; margin-top: 4px; }}
  .card.error .value {{ color: var(--error); }}
  .card.warn .value {{ color: var(--warn); }}
  .card.ok .value {{ color: var(--ok); }}
  table {{
    width: 100%; border-collapse: collapse; background: var(--panel);
    border: 1px solid var(--line); border-radius: 8px; overflow: hidden;
  }}
  th, td {{
    padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--line);
    font-size: 13px; vertical-align: top;
  }}
  th {{ background: #eaeef2; font-weight: 600; color: var(--muted); }}
  tr:last-child td {{ border-bottom: 0; }}
  .sev {{
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 600; text-transform: uppercase;
  }}
  .sev.error   {{ background: #ffebe9; color: var(--error); }}
  .sev.warning {{ background: #fff8c5; color: var(--warn); }}
  .sev.info    {{ background: #ddf4ff; color: var(--accent); }}
  pre {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
    padding: 16px; overflow: auto; font-size: 12.5px; line-height: 1.5;
    max-height: 70vh;
  }}
  .empty {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
    padding: 40px; text-align: center; color: var(--muted);
  }}
  h2 {{ margin: 32px 0 12px; font-size: 16px; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>{title}</h1>
    <div class="meta">Project: {project} &middot; generated locally, no server required</div>
  </div>
  <div class="actions">
    <button class="btn primary" onclick="download_rpt()">Download .rpt</button>
    <button class="btn primary" onclick="download_json()">Download .json</button>
    <a class="btn" href="Nano-Board-rev-2-navigate_reports.html">&larr; Back to navigate</a>
  </div>
</header>

<main>
  <div class="summary">
    <div class="card error"><div class="label">Errors</div><div class="value" id="count-errors">0</div></div>
    <div class="card warn"><div class="label">Warnings</div><div class="value" id="count-warnings">0</div></div>
    <div class="card"><div class="label">Total entries</div><div class="value" id="count-total">0</div></div>
  </div>

  <h2>Violations</h2>
  <div id="rows-host"></div>

  <h2>Raw report (.rpt)</h2>
  <pre id="rpt-pre">(no .rpt file was found)</pre>
</main>

<script>
  // Inlined data — survives offline use, no fetch() / no CORS needed.
  const RPT_TEXT = {rpt_js};
  const JSON_TEXT = {json_js};
  const ROWS = {rows_js};
  const FILE_BASE = {file_base_js};

  document.getElementById('rpt-pre').textContent = RPT_TEXT || '(no .rpt file was found)';

  const errCount = ROWS.filter(r => r.severity === 'error').length;
  const warnCount = ROWS.filter(r => r.severity === 'warning').length;
  document.getElementById('count-errors').textContent = errCount;
  document.getElementById('count-warnings').textContent = warnCount;
  document.getElementById('count-total').textContent = ROWS.length;

  const host = document.getElementById('rows-host');
  if (ROWS.length === 0) {{
    host.innerHTML = '<div class="empty">No violations parsed from JSON. See the raw .rpt below.</div>';
  }} else {{
    const tbl = document.createElement('table');
    tbl.innerHTML =
      '<thead><tr><th>Sev</th><th>Code</th><th>Description</th><th>Items</th></tr></thead>';
    const tb = document.createElement('tbody');
    for (const r of ROWS) {{
      const tr = document.createElement('tr');
      const sev = (r.severity || 'info').toLowerCase();
      tr.innerHTML =
        '<td><span class="sev ' + sev + '">' + sev + '</span></td>' +
        '<td>' + escapeHtml(r.code || '') + '</td>' +
        '<td>' + escapeHtml(r.description || '') + '</td>' +
        '<td>' + escapeHtml(r.items || '') + '</td>';
      tb.appendChild(tr);
    }}
    tbl.appendChild(tb);
    host.appendChild(tbl);
  }}

  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c =>
      ({{ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }})[c]);
  }}

  function downloadBlob(content, mime, name) {{
    const blob = new Blob([content], {{ type: mime }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(() => {{ a.remove(); URL.revokeObjectURL(url); }}, 0);
  }}

  function download_rpt() {{
    if (!RPT_TEXT) {{ alert('No .rpt content available.'); return; }}
    downloadBlob(RPT_TEXT, 'text/plain;charset=utf-8', FILE_BASE + '.rpt');
  }}
  function download_json() {{
    if (!JSON_TEXT) {{ alert('No .json content available.'); return; }}
    downloadBlob(JSON_TEXT, 'application/json;charset=utf-8', FILE_BASE + '.json');
  }}
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["erc", "drc"], required=True)
    ap.add_argument("--rpt", type=pathlib.Path, required=True)
    ap.add_argument("--json", type=pathlib.Path, required=True)
    ap.add_argument("--output", type=pathlib.Path, required=True)
    ap.add_argument("--project", default="")
    args = ap.parse_args()

    rpt_text = args.rpt.read_text(encoding="utf-8", errors="replace") if args.rpt.exists() else ""
    json_text = args.json.read_text(encoding="utf-8", errors="replace") if args.json.exists() else ""

    rows = []
    if json_text.strip():
        try:
            rows = parse_json_violations(json.loads(json_text))
        except Exception as e:
            print(f"warn: could not parse {args.json}: {e}", file=sys.stderr)

    title = "ERC Report" if args.kind == "erc" else "DRC Report"
    file_base = f"{args.project}-{args.kind}" if args.project else args.kind

    page = PAGE.format(
        title=html.escape(title),
        project=html.escape(args.project or "(unknown)"),
        rpt_js=json.dumps(rpt_text),
        json_js=json.dumps(json_text),
        rows_js=json.dumps(rows),
        file_base_js=json.dumps(file_base),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"wrote {args.output} ({len(rows)} violations from JSON, {len(rpt_text)} bytes RPT)")


if __name__ == "__main__":
    main()
