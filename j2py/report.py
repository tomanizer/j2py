"""Static HTML review report generation."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from j2py.pipeline import TranslationResult


@dataclass(frozen=True)
class ReportInput:
    source_path: Path
    java_source: str
    python_source: str
    confidence: float
    used_llm: bool
    diagnostics: list[str]


def write_translation_report(
    path: Path,
    results: list[TranslationResult],
    *,
    title: str = "j2py translation report",
) -> None:
    inputs = [
        ReportInput(
            source_path=result.source_path,
            java_source=result.source_path.read_text(),
            python_source=result.python_source,
            confidence=result.confidence,
            used_llm=result.used_llm,
            diagnostics=[
                f"line {item.line}: {item.reason}"
                for item in (result.diagnostics.unhandled if result.diagnostics else [])
            ],
        )
        for result in results
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_translation_report(inputs, title=title))


def render_translation_report(inputs: list[ReportInput], *, title: str) -> str:
    avg_confidence = sum(item.confidence for item in inputs) / len(inputs) if inputs else 0.0
    nav = "\n".join(_nav_item(index, item) for index, item in enumerate(inputs))
    sections = "\n".join(_file_section(index, item) for index, item in enumerate(inputs))
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
  <span class="score">{avg_confidence:.0%} avg confidence</span>
</header>
<main>
  <nav aria-label="Translated files">
    {nav}
  </nav>
  <section class="files">
    {sections}
  </section>
</main>
</body>
</html>
"""


def _nav_item(index: int, item: ReportInput) -> str:
    return (
        f'<a href="#file-{index}">'
        f"<span>{escape(item.source_path.name)}</span>"
        f"<strong>{item.confidence:.0%}</strong>"
        "</a>"
    )


def _file_section(index: int, item: ReportInput) -> str:
    diagnostics = "<br>".join(escape(diagnostic) for diagnostic in item.diagnostics)
    if not diagnostics:
        diagnostics = "No unresolved rule-layer diagnostics."
    return f"""
<article id="file-{index}" class="file">
  <div class="file-head">
    <h2>{escape(str(item.source_path))}</h2>
    <span class="badge">{item.confidence:.0%}</span>
  </div>
  <div class="diagnostics">{diagnostics}</div>
  <div class="split">
    <div class="pane">
      <h3>Java</h3>
      {_source_lines(item.java_source, provenance="java", diagnostics=[])}
    </div>
    <div class="pane">
      <h3>Python</h3>
      {
        _source_lines(
            item.python_source,
            provenance="llm" if item.used_llm else "rule",
            diagnostics=item.diagnostics,
        )
    }
    </div>
  </div>
</article>
"""


def _source_lines(source: str, *, provenance: str, diagnostics: list[str]) -> str:
    lines = source.splitlines() or [""]
    rendered = [
        _line_html(number, line, provenance=provenance, diagnostics=diagnostics)
        for number, line in enumerate(lines, start=1)
    ]
    return '<ol class="code-lines">\n' + "\n".join(rendered) + "\n</ol>"


def _line_html(
    number: int,
    line: str,
    *,
    provenance: str,
    diagnostics: list[str],
) -> str:
    is_todo = "TODO(j2py)" in line or "__j2py_todo__" in line
    classes = [provenance]
    if is_todo:
        classes.append("todo")
    detail = ""
    if is_todo:
        line_diagnostics = [item for item in diagnostics if item.startswith(f"line {number}:")]
        reason = "<br>".join(escape(item) for item in line_diagnostics) or "TODO(j2py)"
        detail = f"<details><summary>TODO</summary><p>{reason}</p></details>"
    return (
        f'<li data-line="{number}" data-provenance="{provenance}" '
        f'class="{" ".join(classes)}">'
        f"<code>{escape(line) or ' '}</code>{detail}</li>"
    )


_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --ink: #17202a;
  --muted: #5f6b7a;
  --line: #d8dee8;
  --rule: #e7f6ed;
  --llm: #fff4d8;
  --todo: #ffe1df;
  --panel: #ffffff;
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
  gap: 16px;
  justify-content: space-between;
  padding: 14px 20px;
  position: sticky;
  top: 0;
  z-index: 2;
}
h1, h2, h3 { margin: 0; }
h1 { font-size: 18px; }
h2 { font-size: 15px; overflow-wrap: anywhere; }
h3 { color: var(--muted); font-size: 12px; letter-spacing: .04em; text-transform: uppercase; }
main { display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 56px); }
nav {
  background: var(--panel);
  border-right: 1px solid var(--line);
  padding: 12px;
}
nav a {
  align-items: center;
  border-radius: 6px;
  color: inherit;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding: 8px;
  text-decoration: none;
}
nav a:hover { background: var(--bg); }
.files { padding: 16px; }
.file {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin: 0 0 16px;
  overflow: hidden;
}
.file-head, .diagnostics {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 10px 12px;
}
.diagnostics { color: var(--muted); display: block; font-size: 12px; }
.score, .badge {
  background: #edf2f7;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px 8px;
}
.split { display: grid; grid-template-columns: 1fr 1fr; }
.pane { min-width: 0; }
.pane + .pane { border-left: 1px solid var(--line); }
.pane h3 { border-bottom: 1px solid var(--line); padding: 8px 12px; }
.code-lines {
  counter-reset: line;
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  list-style: none;
  margin: 0;
  overflow: auto;
  padding: 0;
}
.code-lines li {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) auto;
  min-height: 22px;
}
.code-lines li::before {
  color: var(--muted);
  content: attr(data-line);
  padding: 2px 10px;
  text-align: right;
}
.code-lines code { padding: 2px 10px; white-space: pre; }
.rule { background: var(--rule); }
.llm { background: var(--llm); }
.java { background: #f8fafc; }
.todo { background: var(--todo); }
details { padding: 2px 8px; }
details p { margin: 6px 0; max-width: 360px; white-space: normal; }
@media (max-width: 860px) {
  main { grid-template-columns: 1fr; }
  nav { border-right: 0; border-bottom: 1px solid var(--line); }
  .split { grid-template-columns: 1fr; }
  .pane + .pane { border-left: 0; border-top: 1px solid var(--line); }
}
"""
