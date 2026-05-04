#!/usr/bin/env python3
# ============================================================================
# generate_error_report.py
# ----------------------------------------------------------------------------
# Reads KiCad / KiBot ERC and DRC reports and emits a single self-contained
# HTML file (`error-report.html`) summarising every violation.
#
# Inputs (any subset — missing files are tolerated):
#   --erc-json   path to KiCad ERC JSON (kicad-cli / KiBot `erc` output)
#   --drc-json   path to KiCad DRC JSON (kicad-cli / KiBot `drc` output)
#   --erc-rpt    fallback plain-text ERC .rpt file (KiCad legacy)
#   --drc-rpt    fallback plain-text DRC .rpt file (KiCad legacy)
#   --pcb-image  optional path to a PNG/SVG of the board (embedded if given)
#   --output     output HTML path (default: error-report.html)
#
# Header metadata is read from environment variables that GitHub Actions
# already provides:
#   GITHUB_REPOSITORY, GITHUB_REF_NAME, GITHUB_SHA, GITHUB_RUN_ID,
#   GITHUB_SERVER_URL, KICAD_PROJECT
#
# The output HTML is fully standalone — all CSS and JS are inlined. No CDN.
# ============================================================================

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------

@dataclass
class Violation:
    kind: str               # "ERC" or "DRC"
    severity: str           # "error" | "warning" | "exclusion" | "info"
    code: str               # e.g. "lib_symbol_issues", "clearance"
    description: str        # human-readable
    refs: list[str] = field(default_factory=list)   # affected components / nets
    sheet: str = ""         # ERC: sheet path
    layer: str = ""         # DRC: layer name
    pos: str = ""           # "x mm, y mm" or empty
    extra: str = ""         # clearance value, etc.


# ----------------------------------------------------------------------------
# Parsers — JSON (preferred)
# ----------------------------------------------------------------------------

def _coalesce_severity(raw: str | None) -> str:
    if not raw:
        return "warning"
    s = raw.strip().lower()
    if s in ("error", "err"):
        return "error"
    if s in ("warning", "warn"):
        return "warning"
    if s in ("exclusion", "excluded"):
        return "exclusion"
    return s or "warning"


def _format_pos(item: dict) -> str:
    pos = item.get("pos") or item.get("position") or {}
    if isinstance(pos, dict):
        x = pos.get("x")
        y = pos.get("y")
        if x is not None and y is not None:
            return f"{x:.2f} mm, {y:.2f} mm"
    return ""


def _refs_from_items(items: list[dict]) -> list[str]:
    refs = []
    for it in items or []:
        desc = it.get("description") or ""
        # Pull "R1", "U3", "C5" style refs out of free-form descriptions.
        for m in re.findall(r"\b([A-Z]{1,3}\d{1,4})\b", desc):
            if m not in refs:
                refs.append(m)
    return refs


def parse_erc_json(path: Path) -> list[Violation]:
    out: list[Violation] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warn: failed to parse ERC JSON {path}: {exc}", file=sys.stderr)
        return out

    sheets = data.get("sheets") or [data]
    for sheet in sheets:
        sheet_path = sheet.get("path") or sheet.get("name") or "/"
        for v in sheet.get("violations", []) or []:
            items = v.get("items", []) or []
            pos = _format_pos(items[0]) if items else ""
            refs = _refs_from_items(items)
            out.append(Violation(
                kind="ERC",
                severity=_coalesce_severity(v.get("severity")),
                code=v.get("type", "") or v.get("code", ""),
                description=v.get("description", "") or "",
                refs=refs,
                sheet=sheet_path,
                pos=pos,
            ))
    return out


def parse_drc_json(path: Path) -> list[Violation]:
    out: list[Violation] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"warn: failed to parse DRC JSON {path}: {exc}", file=sys.stderr)
        return out

    sections = (
        ("violations", "rule"),
        ("unconnected_items", "unconnected"),
        ("schematic_parity", "schematic_parity"),
    )
    for section, default_code in sections:
        for v in data.get(section, []) or []:
            items = v.get("items", []) or []
            pos = _format_pos(items[0]) if items else ""
            layer = ""
            if items:
                layer = items[0].get("layer", "") or ""
            refs = _refs_from_items(items)
            extra = ""
            # Clearance violations frequently embed actual/required values.
            desc = v.get("description", "") or ""
            m = re.search(r"clearance\s+([\d.]+).*?(?:min|required)\s+([\d.]+)", desc, re.I)
            if m:
                extra = f"actual {m.group(1)} / required {m.group(2)}"
            out.append(Violation(
                kind="DRC",
                severity=_coalesce_severity(v.get("severity")),
                code=v.get("type", "") or default_code,
                description=desc,
                refs=refs,
                layer=layer,
                pos=pos,
                extra=extra,
            ))
    return out


# ----------------------------------------------------------------------------
# Parsers — legacy .rpt fallback (KiCad text reports)
# ----------------------------------------------------------------------------

_RPT_LINE_RE = re.compile(
    r"\[(?P<code>[a-z_]+)\]\s*:\s*(?P<desc>.+?)$",
    re.IGNORECASE,
)
_RPT_SEVERITY_RE = re.compile(r";\s*(error|warning)", re.IGNORECASE)
_RPT_POS_RE = re.compile(r"@\(\s*([\d.]+)\s*mm\s*,\s*([\d.]+)\s*mm\s*\)\s*:\s*(.+)")


def _parse_rpt(path: Path, kind: str) -> list[Violation]:
    out: list[Violation] = []
    if not path.exists():
        return out
    sheet = "/"
    pending: Violation | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.rstrip()
        if line.startswith("***** Sheet"):
            sheet = line.replace("***** Sheet", "").strip() or "/"
            continue
        m = _RPT_LINE_RE.search(line.strip())
        if m and not line.startswith(" "):
            if pending:
                out.append(pending)
            pending = Violation(
                kind=kind,
                severity="warning",
                code=m.group("code"),
                description=m.group("desc").strip(),
                sheet=sheet,
            )
            continue
        sev = _RPT_SEVERITY_RE.search(line)
        if sev and pending:
            pending.severity = _coalesce_severity(sev.group(1))
            continue
        pos = _RPT_POS_RE.search(line)
        if pos and pending:
            pending.pos = f"{pos.group(1)} mm, {pos.group(2)} mm"
            for ref in re.findall(r"\b([A-Z]{1,3}\d{1,4})\b", pos.group(3)):
                if ref not in pending.refs:
                    pending.refs.append(ref)
    if pending:
        out.append(pending)
    return out


# ----------------------------------------------------------------------------
# HTML rendering
# ----------------------------------------------------------------------------

CSS = r"""
*,*::before,*::after { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  color: #1F2937;
  background: #F3F4F6;
  line-height: 1.45;
}
header.banner {
  background: #1F2937;
  color: #F9FAFB;
  padding: 28px 32px 24px;
}
header.banner h1 {
  margin: 0 0 6px;
  font-size: 22px;
  letter-spacing: 0.5px;
}
header.banner .sub {
  color: #9CA3AF;
  font-size: 13px;
}
header.banner a { color: #93C5FD; }
.fail-bar {
  background: #DC2626;
  color: #fff;
  padding: 12px 32px;
  font-weight: 600;
  letter-spacing: 1px;
}
.fail-bar.ok { background: #16A34A; }
main { padding: 24px 32px; max-width: 1200px; margin: 0 auto; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}
.card {
  background: #fff;
  padding: 14px 16px;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
  border-left: 4px solid #E5E7EB;
}
.card .label { font-size: 11px; text-transform: uppercase; color: #6B7280; letter-spacing: .8px; }
.card .value { font-size: 26px; font-weight: 700; margin-top: 4px; }
.card.err  { border-left-color: #DC2626; }
.card.warn { border-left-color: #F59E0B; }
.card.ok   { border-left-color: #16A34A; }
.card.err  .value { color: #DC2626; }
.card.warn .value { color: #F59E0B; }
.card.ok   .value { color: #16A34A; }
.badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .5px;
}
.badge.error    { background: #FEE2E2; color: #B91C1C; }
.badge.warning  { background: #FEF3C7; color: #B45309; }
.badge.ok       { background: #DCFCE7; color: #166534; }
.badge.exclusion{ background: #E5E7EB; color: #374151; }
section { margin-bottom: 32px; }
section h2 {
  font-size: 16px;
  margin: 0 0 12px;
  display: flex; align-items: center; gap: 10px;
}
.toolbar {
  display: flex; gap: 8px; flex-wrap: wrap;
  margin-bottom: 12px; align-items: center;
}
.toolbar input[type=search] {
  padding: 7px 10px; border: 1px solid #D1D5DB;
  border-radius: 6px; min-width: 220px; font-size: 13px;
}
.toolbar label {
  font-size: 12px; color: #374151;
  display: inline-flex; align-items: center; gap: 6px;
}
.toolbar select {
  padding: 6px 8px; border: 1px solid #D1D5DB; border-radius: 6px;
  font-size: 13px; background: #fff;
}
table {
  width: 100%; border-collapse: collapse; background: #fff;
  border-radius: 8px; overflow: hidden;
  box-shadow: 0 1px 2px rgba(0,0,0,.05);
  font-size: 13px;
}
th, td { text-align: left; padding: 10px 12px; vertical-align: top; }
thead { background: #F9FAFB; }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .6px; color: #6B7280; }
tbody tr { border-top: 1px solid #F3F4F6; }
tbody tr.severity-error    { background: #FEF2F2; }
tbody tr.severity-warning  { background: #FFFBEB; }
tbody tr.hidden { display: none; }
code {
  background: #F3F4F6; padding: 1px 6px; border-radius: 4px;
  font-size: 12px; color: #374151;
}
.refs code { margin-right: 4px; }
.fixes {
  background: #fff; padding: 16px 20px; border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,.05);
}
.fixes h3 { margin-top: 0; font-size: 14px; }
.fixes ul { margin: 0; padding-left: 20px; }
.fixes li { margin-bottom: 6px; font-size: 13px; }
.empty {
  background: #fff; padding: 22px; text-align: center; color: #6B7280;
  border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.05);
}
.image-block { background: #fff; padding: 12px; border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,.05); margin-top: 12px; }
.image-block img { max-width: 100%; height: auto; display: block; }
@media print {
  body { background: #fff; }
  header.banner { background: #fff; color: #111; border-bottom: 2px solid #DC2626; }
  header.banner .sub, header.banner a { color: #374151; }
  .toolbar { display: none; }
  .card { break-inside: avoid; }
}
"""

JS = r"""
function applyFilter(tableId) {
  const t = document.getElementById(tableId);
  if (!t) return;
  const sevSel = document.querySelector(`[data-target="${tableId}"][data-kind="sev"]`);
  const codeSel = document.querySelector(`[data-target="${tableId}"][data-kind="code"]`);
  const search = document.querySelector(`[data-target="${tableId}"][data-kind="search"]`);
  const sev = sevSel ? sevSel.value : 'all';
  const code = codeSel ? codeSel.value : 'all';
  const q = (search ? search.value : '').toLowerCase().trim();
  t.querySelectorAll('tbody tr').forEach(tr => {
    const rsev = tr.dataset.severity || '';
    const rcode = tr.dataset.code || '';
    const text = (tr.innerText || '').toLowerCase();
    let show = true;
    if (sev !== 'all' && rsev !== sev) show = false;
    if (code !== 'all' && rcode !== code) show = false;
    if (q && !text.includes(q)) show = false;
    tr.classList.toggle('hidden', !show);
  });
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-target]').forEach(el => {
    const target = el.dataset.target;
    el.addEventListener('input', () => applyFilter(target));
    el.addEventListener('change', () => applyFilter(target));
  });
});
"""


def _embed_image(path: Path) -> str:
    if not path or not path.exists():
        return ""
    suffix = path.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "svg": "image/svg+xml",
            "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix, "")
    if not mime:
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (f'<div class="image-block"><img alt="PCB preview" '
            f'src="data:{mime};base64,{data}"/></div>')


def _row(v: Violation) -> str:
    refs = " ".join(f"<code>{html.escape(r)}</code>" for r in v.refs) or "&mdash;"
    location_bits = []
    if v.sheet:
        location_bits.append(f"sheet <code>{html.escape(v.sheet)}</code>")
    if v.layer:
        location_bits.append(f"layer <code>{html.escape(v.layer)}</code>")
    if v.pos:
        location_bits.append(f"@ <code>{html.escape(v.pos)}</code>")
    if v.extra:
        location_bits.append(html.escape(v.extra))
    location = "<br>".join(location_bits) or "&mdash;"

    return (
        f'<tr class="severity-{html.escape(v.severity)}" '
        f'data-severity="{html.escape(v.severity)}" '
        f'data-code="{html.escape(v.code)}">'
        f'<td><span class="badge {html.escape(v.severity)}">'
        f'{html.escape(v.severity)}</span></td>'
        f'<td><code>{html.escape(v.code)}</code></td>'
        f'<td>{html.escape(v.description)}</td>'
        f'<td class="refs">{refs}</td>'
        f'<td>{location}</td>'
        f'</tr>'
    )


def _toolbar(table_id: str, codes: Iterable[str]) -> str:
    code_options = "".join(
        f'<option value="{html.escape(c)}">{html.escape(c)}</option>'
        for c in sorted({c for c in codes if c})
    )
    return (
        f'<div class="toolbar">'
        f'<input type="search" placeholder="Search refs, nets, descriptions…" '
        f'data-target="{table_id}" data-kind="search"/>'
        f'<label>Severity '
        f'<select data-target="{table_id}" data-kind="sev">'
        f'<option value="all">all</option>'
        f'<option value="error">errors only</option>'
        f'<option value="warning">warnings only</option>'
        f'</select></label>'
        f'<label>Code '
        f'<select data-target="{table_id}" data-kind="code">'
        f'<option value="all">all</option>{code_options}'
        f'</select></label>'
        f'</div>'
    )


def _section(title: str, table_id: str, items: list[Violation]) -> str:
    if not items:
        return (
            f'<section><h2>{html.escape(title)} '
            f'<span class="badge ok">no issues</span></h2>'
            f'<div class="empty">No {html.escape(title)} entries.</div></section>'
        )
    rows = "".join(_row(v) for v in items)
    return (
        f'<section>'
        f'<h2>{html.escape(title)} '
        f'<span class="badge error">{sum(1 for v in items if v.severity=="error")} errors</span> '
        f'<span class="badge warning">{sum(1 for v in items if v.severity=="warning")} warnings</span>'
        f'</h2>'
        f'{_toolbar(table_id, (v.code for v in items))}'
        f'<table id="{table_id}"><thead><tr>'
        f'<th>Severity</th><th>Code</th><th>Description</th>'
        f'<th>Components / Nets</th><th>Location</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
        f'</section>'
    )


def _card(label: str, value: int, kind: str) -> str:
    return (f'<div class="card {kind}"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{value}</div></div>')


def render_html(erc: list[Violation], drc: list[Violation],
                pcb_image: Path | None,
                show_erc: bool = True, show_drc: bool = True) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF_NAME", "")
    sha = os.environ.get("GITHUB_SHA", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    project = os.environ.get("KICAD_PROJECT", "(unknown project)")
    run_url = f"{server}/{repo}/actions/runs/{run_id}" if (repo and run_id) else ""
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    erc_err = sum(1 for v in erc if v.severity == "error")
    erc_warn = sum(1 for v in erc if v.severity == "warning")
    drc_err = sum(1 for v in drc if v.severity == "error")
    drc_warn = sum(1 for v in drc if v.severity == "warning")
    failed = (erc_err if show_erc else 0) + (drc_err if show_drc else 0) > 0

    card_chunks = []
    if show_erc:
        card_chunks.append(_card("ERC errors", erc_err, "err" if erc_err else "ok"))
        card_chunks.append(_card("ERC warnings", erc_warn, "warn" if erc_warn else "ok"))
    if show_drc:
        card_chunks.append(_card("DRC errors", drc_err, "err" if drc_err else "ok"))
        card_chunks.append(_card("DRC warnings", drc_warn, "warn" if drc_warn else "ok"))
    cards = "".join(card_chunks)

    status_cards = ""
    if show_erc:
        erc_badge = ('<span class="badge error">FAIL</span>' if erc_err
                     else '<span class="badge ok">PASS</span>')
        status_cards += f'<div class="card"><div class="label">ERC</div><div class="value">{erc_badge}</div></div>'
    if show_drc:
        drc_badge = ('<span class="badge error">FAIL</span>' if drc_err
                     else '<span class="badge ok">PASS</span>')
        status_cards += f'<div class="card"><div class="label">DRC</div><div class="value">{drc_badge}</div></div>'

    image_block = _embed_image(pcb_image) if pcb_image else ""

    sub_bits = []
    if branch:
        sub_bits.append(f'branch <code>{html.escape(branch)}</code>')
    if sha:
        sub_bits.append(f'commit <code>{html.escape(sha[:8])}</code>')
    if run_url:
        sub_bits.append(f'<a href="{html.escape(run_url)}">workflow run</a>')
    sub_bits.append(timestamp)
    sub_html = " &middot; ".join(sub_bits)

    if show_erc and show_drc:
        kinds = "ERC / DRC"
    elif show_erc:
        kinds = "ERC"
    else:
        kinds = "DRC"

    fail_bar_class = "fail-bar" if failed else "fail-bar ok"
    fail_bar_text = (f"&#9888;&#65039; {kinds} FAILED &mdash; merge blocked"
                     if failed else f"&#10003; {kinds} passed")

    title_kind = kinds
    sections_html = ""
    if show_erc:
        sections_html += _section("ERC violations", "erc-table", erc)
    if show_drc:
        sections_html += _section("DRC violations", "drc-table", drc)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{html.escape(project)} — {html.escape(title_kind)} report</title>
<style>{CSS}</style>
</head>
<body>
<header class="banner">
  <h1>{html.escape(project)} &mdash; {html.escape(title_kind.lower())} report</h1>
  <div class="sub">{sub_html}</div>
</header>
<div class="{fail_bar_class}">{fail_bar_text}</div>
<main>
  <div class="cards">
    {cards}
    {status_cards}
  </div>

  {image_block}

  {sections_html}

  <section class="fixes">
    <h3>How to fix common issues</h3>
    <ul>
      <li><b>lib_symbol_issues / footprint_link_issues</b> — open the symbol/footprint library manager and add the missing library, or change the symbol/footprint to one from a configured library.</li>
      <li><b>unconnected pins</b> — connect the pin or place a "no-connect" flag if it is intentionally unused.</li>
      <li><b>clearance</b> — increase track-to-track or pad-to-track spacing, or relax the design rule for that net class if appropriate.</li>
      <li><b>track width</b> — match the design-rule minimum for the net class (typically 0.15 mm for signal, 0.25 mm+ for power).</li>
      <li><b>silkscreen over pad</b> — move the reference designator off the pad in the footprint editor or hide it.</li>
      <li><b>schematic_parity</b> — re-run "Update PCB from Schematic" so the layout matches the latest netlist.</li>
      <li><b>holes too close</b> — separate drilled holes by at least the manufacturer minimum (commonly 0.5 mm).</li>
    </ul>
  </section>
</main>
<script>{JS}</script>
</body>
</html>
"""


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Generate ERC/DRC HTML report")
    ap.add_argument("--erc-json", type=Path)
    ap.add_argument("--drc-json", type=Path)
    ap.add_argument("--erc-rpt", type=Path)
    ap.add_argument("--drc-rpt", type=Path)
    ap.add_argument("--pcb-image", type=Path)
    ap.add_argument("--output", type=Path, default=Path("error-report.html"))
    args = ap.parse_args()

    erc: list[Violation] = []
    drc: list[Violation] = []

    # A kind is "shown" if at least one of its inputs was passed on the
    # CLI. The per-kind pages (erc-erc.html, drc-drc.html) call this script
    # with only one set of flags and get a single-kind page; the combined
    # error-report.html passes both sets and gets the dual-kind page. If
    # neither side was passed, fall back to showing both (legacy behavior).
    erc_requested = bool(args.erc_json or args.erc_rpt)
    drc_requested = bool(args.drc_json or args.drc_rpt)
    if not erc_requested and not drc_requested:
        erc_requested = drc_requested = True

    if args.erc_json and args.erc_json.exists():
        erc = parse_erc_json(args.erc_json)
    elif args.erc_rpt and args.erc_rpt.exists():
        erc = _parse_rpt(args.erc_rpt, "ERC")

    if args.drc_json and args.drc_json.exists():
        drc = parse_drc_json(args.drc_json)
    elif args.drc_rpt and args.drc_rpt.exists():
        drc = _parse_rpt(args.drc_rpt, "DRC")

    html_doc = render_html(erc, drc, args.pcb_image,
                           show_erc=erc_requested, show_drc=drc_requested)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc, encoding="utf-8")

    print(f"Wrote {args.output} "
          f"(ERC: {len(erc)} entries, DRC: {len(drc)} entries)")

    fail_erc = erc_requested and any(v.severity == "error" for v in erc)
    fail_drc = drc_requested and any(v.severity == "error" for v in drc)
    return 1 if (fail_erc or fail_drc) else 0


if __name__ == "__main__":
    sys.exit(main())
