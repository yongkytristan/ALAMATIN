"""Render the participant-facing Markdown document as a shareable A4 PDF."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROWSER_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


def inline_markup(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(
        r"\[([^]]+)]\((https?://[^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    return escaped


def markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    list_kind: str | None = None
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{inline_markup(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_kind
        if not list_items or list_kind is None:
            return
        tag = "ol" if list_kind == "ordered" else "ul"
        rendered = []
        for item in list_items:
            checkbox = re.match(r"^\[([ xX])]\s*(.*)$", item)
            if checkbox:
                checked = " checked" if checkbox.group(1).lower() == "x" else ""
                content = (
                    f'<label class="check"><input type="checkbox" disabled{checked}>'
                    f"<span>{inline_markup(checkbox.group(2))}</span></label>"
                )
            else:
                content = inline_markup(item)
            rendered.append(f"<li>{content}</li>")
        blocks.append(f"<{tag}>{''.join(rendered)}</{tag}>")
        list_items.clear()
        list_kind = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        ordered = re.match(r"^\d+\.\s+(.+)$", line)
        unordered = re.match(r"^-\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{inline_markup(heading.group(2))}</h{level}>")
        elif ordered or unordered:
            flush_paragraph()
            kind = "ordered" if ordered else "unordered"
            if list_kind and list_kind != kind:
                flush_list()
            list_kind = kind
            list_items.append((ordered or unordered).group(1))
        elif list_kind and raw_line[:1].isspace():
            list_items[-1] = f"{list_items[-1]} {line}"
        else:
            flush_list()
            paragraph.append(line)
    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def document_html(markdown: str) -> str:
    body = markdown_to_html(markdown)
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>Pertanyaan Wawancara Verifikasi Alamat Pengiriman</title>
<style>
  @page {{ size: A4; margin: 17mm 16mm 18mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    color: #172033;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10.6pt;
    line-height: 1.48;
    margin: 0;
  }}
  h1 {{
    color: #0b5d55;
    font-size: 22pt;
    line-height: 1.15;
    margin: 0 0 12pt;
    padding-bottom: 9pt;
    border-bottom: 3px solid #20a486;
  }}
  h2 {{
    break-after: avoid-page;
    color: #0b5d55;
    font-size: 15pt;
    margin: 20pt 0 7pt;
    padding: 6pt 8pt;
    background: #e8f6f2;
    border-left: 4px solid #20a486;
  }}
  h3 {{
    break-after: avoid-page;
    color: #284c61;
    font-size: 12pt;
    margin: 15pt 0 5pt;
  }}
  p {{ margin: 0 0 8pt; }}
  ol, ul {{ margin: 4pt 0 10pt 18pt; padding-left: 8pt; }}
  li {{ break-inside: avoid; margin: 0 0 5pt; padding-left: 2pt; }}
  strong {{ color: #0b453f; }}
  .check {{ display: flex; align-items: flex-start; gap: 7pt; }}
  .check input {{ flex: 0 0 auto; height: 12pt; width: 12pt; margin-top: 2pt; }}
  a {{ color: #0b5d55; text-decoration: none; }}
  h1 + p {{ font-size: 11.2pt; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def find_browser() -> Path:
    for candidate in BROWSER_CANDIDATES:
        if candidate.is_file():
            return candidate
    for command in ("msedge", "chrome", "chromium"):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)
    raise RuntimeError("Microsoft Edge or Google Chrome is required to render PDF")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "docs" / "participant-interview-questions.md",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "participant-interview-questions.pdf",
    )
    parser.add_argument("--html-output", type=Path)
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    rendered = document_html(source.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="alamatin-pdf-") as temp_dir:
        temp_root = Path(temp_dir)
        html_path = temp_root / "participant-interview-questions.html"
        html_path.write_text(rendered, encoding="utf-8")
        if args.html_output:
            html_output = args.html_output.resolve()
            html_output.write_text(rendered, encoding="utf-8")
        command = [
            str(find_browser()),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--user-data-dir={temp_root / 'browser-profile'}",
            f"--print-to-pdf={output}",
            html_path.as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Browser PDF rendering failed")

    if not output.is_file() or output.stat().st_size < 1_000:
        raise RuntimeError("PDF output is missing or unexpectedly small")
    if not output.read_bytes().startswith(b"%PDF-"):
        raise RuntimeError("Output does not have a valid PDF header")
    print(f"Created {output} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
