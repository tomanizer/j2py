"""Self-contained HTML dashboard for directory translation results."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from j2py.state import StateEntry, entry_from_result, load_state

if TYPE_CHECKING:
    from j2py.pipeline import TranslationResult


def write_dashboard_for_results(
    path: Path,
    results: list[TranslationResult],
    *,
    source_root: Path,
    output_root: Path,
    title: str = "j2py translation dashboard",
) -> None:
    entries = [
        entry_from_result(result, source_root=source_root, output_root=output_root)
        for result in results
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(entries, title=title))


def write_dashboard_from_state(
    output_root: Path,
    dashboard_path: Path,
    *,
    title: str = "j2py translation dashboard",
) -> None:
    entries = list(load_state(output_root).values())
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.write_text(render_dashboard(entries, title=title))


def render_dashboard(entries: list[StateEntry], *, title: str) -> str:
    total = len(entries)
    avg_confidence = sum(item.confidence for item in entries) / total if total else 0.0
    llm_count = sum(1 for item in entries if item.used_llm)
    validation_known = [item for item in entries if item.validation_ok is not None]
    validation_pass = sum(1 for item in validation_known if item.validation_ok)
    todo_files = sum(1 for item in entries if item.todo_count)
    table_rows = "\n".join(_table_row(item) for item in entries)
    treemap = "\n".join(_treemap_item(item) for item in entries)
    breakdown = _unhandled_breakdown(entries)
    data_json = json.dumps([_entry_payload(item) for item in entries]).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
{_CSS}
</style>
</head>
<body>
<header>
  <h1>{escape(title)}</h1>
  <span>{total} files</span>
</header>
<main>
  <section class="summary" aria-label="Summary">
    {_metric("Average confidence", f"{avg_confidence:.0%}")}
    {_metric("LLM usage", f"{llm_count}/{total}" if total else "0/0")}
    {
        _metric(
            "Validation pass",
            f"{validation_pass}/{len(validation_known)}" if validation_known else "not run",
        )
    }
    {_metric("Files with TODOs", str(todo_files))}
  </section>
  <section>
    <div class="section-head">
      <h2>Confidence Heatmap</h2>
      <span>Box size follows source LOC; color follows confidence.</span>
    </div>
    <div class="treemap">{treemap or "<p>No files translated.</p>"}</div>
  </section>
  <section>
    <div class="section-head">
      <h2>Unhandled Breakdown</h2>
      <span>Total unresolved rule diagnostics by file.</span>
    </div>
    <div class="bars">{breakdown or "<p>No unresolved constructs recorded.</p>"}</div>
  </section>
  <section>
    <div class="section-head">
      <h2>Files</h2>
      <span>Click column headers to sort.</span>
    </div>
    <table id="files">
      <thead>
        <tr>
          <th data-type="text">File</th>
          <th data-type="number">Confidence</th>
          <th data-type="text">Rule/LLM</th>
          <th data-type="text">Validation</th>
          <th data-type="number">TODOs</th>
          <th data-type="number">Unhandled</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </section>
</main>
<script id="j2py-dashboard-data" type="application/json">{data_json}</script>
<script>
{_SCRIPT}
</script>
</body>
</html>
"""


def _metric(label: str, value: str) -> str:
    return f"<article><span>{escape(label)}</span><strong>{escape(value)}</strong></article>"


def _table_row(item: StateEntry) -> str:
    validation = (
        "not run" if item.validation_ok is None else "pass" if item.validation_ok else "fail"
    )
    return f"""
<tr>
  <td>{escape(item.source_path)}</td>
  <td data-value="{item.confidence:.6f}">{item.confidence:.0%}</td>
  <td>{"LLM" if item.used_llm else "Rule only"}</td>
  <td>{validation}</td>
  <td data-value="{item.todo_count}">{item.todo_count}</td>
  <td data-value="{item.unhandled_count}">{item.unhandled_count}</td>
</tr>"""


def _treemap_item(item: StateEntry) -> str:
    loc = max(item.loc, 1)
    color = _confidence_color(item.confidence)
    return (
        f'<a class="tile" href="#files" style="flex-grow:{loc};background:{color}" '
        f'title="{escape(item.source_path)}">'
        f"<span>{escape(Path(item.source_path).name)}</span>"
        f"<strong>{item.confidence:.0%}</strong>"
        "</a>"
    )


def _confidence_color(confidence: float) -> str:
    red = round(232 - (confidence * 118))
    green = round(79 + (confidence * 118))
    blue = round(79 + (confidence * 41))
    return f"rgb({red}, {green}, {blue})"


def _unhandled_breakdown(entries: list[StateEntry]) -> str:
    selected = sorted(
        [item for item in entries if item.unhandled_count],
        key=lambda item: (-item.unhandled_count, item.source_path),
    )[:12]
    if not selected:
        return ""
    max_count = max(item.unhandled_count for item in selected)
    rows = []
    for item in selected:
        width = round((item.unhandled_count / max_count) * 100)
        rows.append(
            f'<div class="bar"><span>{escape(item.source_path)}</span>'
            f'<strong style="width:{width}%">{item.unhandled_count}</strong></div>'
        )
    return "\n".join(rows)


def _entry_payload(item: StateEntry) -> dict[str, object]:
    return {
        "source_path": item.source_path,
        "output_path": item.output_path,
        "confidence": item.confidence,
        "used_llm": item.used_llm,
        "validation_ok": item.validation_ok,
        "todo_count": item.todo_count,
        "unhandled_count": item.unhandled_count,
        "loc": item.loc,
    }


_CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --ink: #18212f;
  --muted: #687386;
  --line: #d8dee8;
  --panel: #ffffff;
  --accent: #1f7a8c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  align-items: center;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 16px 22px;
}
h1, h2 { margin: 0; }
h1 { font-size: 20px; }
h2 { font-size: 16px; }
main { display: grid; gap: 18px; padding: 18px; }
section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.summary {
  background: transparent;
  border: 0;
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.summary article {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.summary span, .section-head span { color: var(--muted); font-size: 12px; }
.summary strong { display: block; font-size: 24px; margin-top: 4px; }
.section-head {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 12px 14px;
}
.treemap {
  align-content: stretch;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 220px;
  padding: 12px;
}
.tile {
  border: 1px solid rgba(0,0,0,.18);
  border-radius: 6px;
  color: #08111f;
  display: flex;
  flex-basis: 120px;
  flex-direction: column;
  justify-content: space-between;
  min-height: 74px;
  min-width: 120px;
  overflow: hidden;
  padding: 8px;
  text-decoration: none;
}
.tile span { overflow-wrap: anywhere; }
.tile strong { align-self: flex-end; }
.bars { display: grid; gap: 8px; padding: 12px; }
.bar {
  align-items: center;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(120px, 280px) 1fr;
}
.bar span { color: var(--muted); overflow-wrap: anywhere; }
.bar strong {
  background: var(--accent);
  border-radius: 4px;
  color: white;
  min-width: 28px;
  padding: 3px 7px;
}
table {
  border-collapse: collapse;
  width: 100%;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 9px 10px;
  text-align: left;
}
th {
  background: #eef2f6;
  cursor: pointer;
  user-select: none;
}
td:first-child { overflow-wrap: anywhere; }
@media (max-width: 780px) {
  .summary { grid-template-columns: 1fr 1fr; }
  .section-head { align-items: flex-start; flex-direction: column; gap: 4px; }
}
"""

_SCRIPT = """
document.querySelectorAll("th").forEach((header, index) => {
  header.addEventListener("click", () => {
    const table = header.closest("table");
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const type = header.dataset.type;
    const direction = header.dataset.direction === "asc" ? -1 : 1;
    document.querySelectorAll("th").forEach((item) => item.dataset.direction = "");
    header.dataset.direction = direction === 1 ? "asc" : "desc";
    rows.sort((left, right) => {
      const leftCell = left.children[index];
      const rightCell = right.children[index];
      const leftValue = leftCell.dataset.value || leftCell.textContent.trim();
      const rightValue = rightCell.dataset.value || rightCell.textContent.trim();
      if (type === "number") {
        return (Number(leftValue) - Number(rightValue)) * direction;
      }
      return leftValue.localeCompare(rightValue) * direction;
    });
    rows.forEach((row) => tbody.appendChild(row));
  });
});
"""
