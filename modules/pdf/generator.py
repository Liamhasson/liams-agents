"""
PDF generator — HTML → PDF via Playwright (Chromium).

Layout copies Liam's own resume (his reference PDF): Carlito, uppercase section
headers with a dark rule, bold role + italic grey date on the right, small
bullets. The cover letter reuses the same header so the pack reads as one set.
Always one A4 page: content that overflows is scaled down to fit.

Fonts: Carlito loads from Google Fonts, falling back to Lato/Calibri/Arial so it
still renders on macOS (local) and Ubuntu (GitHub Actions) without it.

CV markdown format (what the Writer produces):

    # Liam Hasson
    Product Designer
    email · Berlin · linkedin.com/in/... · site.com

    ## Summary
    One paragraph.

    ## Experience
    ### Role, Company | Aug 2026 - Present
    - Bullet

    ## Projects
    ### Project, Context | Dec 2025 - Feb 2026
    _One italic line describing it._
    - Bullet

    ## Skills
    **Tools:** Figma · Claude Code
"""

from __future__ import annotations
import asyncio
import html as htmlmod
import re
from pathlib import Path
import playwright.async_api as pw

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"

FONT_LINK = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Carlito:ital,wght@0,400;0,700;1,400;1,700&display=block">')
FONT_STACK = '"Carlito", "Lato", "Calibri", "Arial", "DejaVu Sans", sans-serif'

INK = "#222222"
MUTED = "#6b6b6b"
CONTACT = "#555555"

# Shared header: name / title / contact line, as on Liam's resume.
HEADER_CSS = f"""
.cv-name {{
    font-size: 19pt;
    font-weight: 700;
    text-transform: uppercase;
    line-height: 1.1;
    color: {INK};
}}
.cv-subtitle {{ font-size: 10pt; color: {MUTED}; margin-top: 3px; }}
.cv-contact {{ font-size: 8pt; color: {CONTACT}; margin-top: 4px; }}
.cv-contact a {{ color: {CONTACT}; text-decoration: underline; text-underline-offset: 1.5px; }}
.cv-contact .sep {{ padding: 0 5px; }}
"""

CV_CSS = f"""
@page {{ size: A4; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
    font-family: {FONT_STACK};
    font-size: 8.5pt;
    line-height: 1.3;
    color: {INK};
}}
{HEADER_CSS}

/* ── Section headers: uppercase, tracked, dark rule underneath ── */
h2 {{
    font-size: 9pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: {INK};
    border-bottom: 0.75pt solid {INK};
    padding-bottom: 3px;
    margin-top: 11px;
    margin-bottom: 6px;
}}

/* ── Entry header: bold title left, italic grey date right ── */
.role-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-top: 6px;
}}
h2 + .role-header {{ margin-top: 0; }}
.role-title {{ font-weight: 700; font-size: 9pt; }}
.role-date  {{ font-style: italic; color: {MUTED}; font-size: 8.5pt; white-space: nowrap; padding-left: 10px; }}
.role-desc  {{ font-style: italic; color: {MUTED}; margin-top: 2px; }}

/* ── Bullets ── */
ul {{ list-style: none; margin-top: 3px; }}
ul li {{ position: relative; padding-left: 14px; margin-bottom: 2.5px; }}
ul li::before {{
    content: "•";
    position: absolute;
    left: 4px;
    font-size: 7pt;
    line-height: 1.6;
}}

/* ── Paragraphs + label lines (skills, languages) ── */
p {{ margin-bottom: 3px; }}
"""

COVER_LETTER_CSS = f"""
@page {{ size: A4; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
    font-family: {FONT_STACK};
    font-size: 10.5pt;
    line-height: 1.5;
    color: {INK};
}}
{HEADER_CSS}
.cl-header {{
    border-bottom: 0.75pt solid {INK};
    padding-bottom: 10px;
    margin-bottom: 26px;
}}
p {{ margin-bottom: 12px; }}
.signature {{ margin-top: 20px; }}
"""


def _esc(s: str) -> str:
    return htmlmod.escape(s, quote=False)


def _inline(s: str) -> str:
    """Escape, then apply **bold** and _italic_."""
    s = _esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"<em>\1</em>", s)
    return s


def _fmt_date(d: str) -> str:
    """'Aug 2026 - Present' / 'Aug 2026–Present' → 'Aug 2026 – Present'."""
    return re.sub(r"\s*[-–—]\s*", " – ", d.strip())


def _contact_html(line: str) -> str:
    """Contact items split on · or |; emails and web addresses become underlined links."""
    items = [i.strip() for i in re.split(r"\s*[·|]\s*", line) if i.strip()]
    out = []
    for it in items:
        e = _esc(it)
        if "@" in it and " " not in it:
            out.append(f'<a href="mailto:{e}">{e}</a>')
        elif re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", it):
            href = it if it.startswith("http") else f"https://{it}"
            out.append(f'<a href="{_esc(href)}">{e}</a>')
        else:
            out.append(e)
    return '<span class="sep">·</span>'.join(out)


def parse_header(md: str) -> tuple[str, str, str]:
    """Name, title and contact line from the top of a CV markdown."""
    lines = []
    for raw in md.split("\n"):
        s = raw.strip()
        if s.startswith("## "):
            break
        if not s or s == "---":
            continue
        lines.append(s.lstrip("# ").strip())
    lines += ["", "", ""]
    return lines[0], lines[1], lines[2]


def _header_html(name: str, title: str, contact: str) -> str:
    parts = [f'<div class="cv-name">{_esc(name)}</div>']
    if title:
        parts.append(f'<div class="cv-subtitle">{_esc(title)}</div>')
    if contact:
        parts.append(f'<div class="cv-contact">{_contact_html(contact)}</div>')
    return "\n".join(parts)


# ─────────────────────────────────────────────
# CV markdown → HTML
# ─────────────────────────────────────────────

def _entry_header(title: str, date: str) -> str:
    return (f'<div class="role-header"><span class="role-title">{_inline(title)}</span>'
            f'<span class="role-date">{_esc(_fmt_date(date))}</span></div>')


def _markdown_cv_to_html(md: str) -> str:
    html: list[str] = [_header_html(*parse_header(md))]
    in_ul = False
    in_header = True

    def close_ul():
        nonlocal in_ul
        if in_ul:
            html.append("</ul>")
            in_ul = False

    for line in md.split("\n"):
        s = line.strip()

        if s.startswith("## "):
            in_header = False
            close_ul()
            html.append(f"<h2>{_esc(s[3:])}</h2>")
            continue
        if in_header or not s or s == "---":
            if not s:
                close_ul()
            continue

        # ── Entry header: ### Title | Date  (or legacy **Title** | Date) ──
        if s.startswith("### ") or (s.startswith("**") and " | " in s and ":**" not in s):
            close_ul()
            inner = re.sub(r"^###\s+", "", s)
            inner = re.sub(r"\*+", "", inner).strip()
            title, date = inner.rsplit(" | ", 1) if " | " in inner else (inner, "")
            html.append(_entry_header(title.strip(), date))
            continue

        # ── Italic one-line description under an entry ──
        if (s.startswith("_") and s.endswith("_")) or (s.startswith("*") and s.endswith("*")
                                                       and not s.startswith("**")):
            close_ul()
            html.append(f'<div class="role-desc">{_esc(s.strip("_*").strip())}</div>')
            continue

        if s.startswith(("- ", "• ", "* ")):
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append(f"<li>{_inline(s[2:].strip())}</li>")
            continue

        close_ul()
        html.append(f"<p>{_inline(s)}</p>")

    close_ul()
    return "\n".join(html)


# ─────────────────────────────────────────────
# Cover letter text → HTML
# ─────────────────────────────────────────────

def _cover_letter_to_html(text: str, header: tuple[str, str, str]) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    parts = ['<div class="cl-header">', _header_html(*header), "</div>"]
    for i, para in enumerate(paras):
        body = "<br>".join(_inline(l.strip()) for l in para.split("\n"))
        is_sign = i == len(paras) - 1 and len(para) < 40
        parts.append(f'<p class="signature">{body}</p>' if is_sign else f"<p>{body}</p>")
    return "\n".join(parts)


def _build_html(body_html: str, css: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
{FONT_LINK}
<style>{css}</style>
</head>
<body>{body_html}</body>
</html>"""


async def _render_pdf_async(html: str, output_path: Path, margins: dict) -> Path:
    """
    Renders HTML to a single A4 page PDF.
    Measures actual content height at the printed width, scales down if it overflows.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def mm(v: str) -> float:
        return float(v.replace("mm", ""))

    usable_w_px = (210 - mm(margins["left"]) - mm(margins["right"])) * 96 / 25.4
    usable_h_px = (297 - mm(margins["top"]) - mm(margins["bottom"])) * 96 / 25.4

    async with pw.async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": round(usable_w_px), "height": 5000})
        await page.set_content(html, wait_until="networkidle")
        await page.evaluate("document.fonts.ready")

        scroll_height = await page.evaluate("document.body.scrollHeight")
        if scroll_height > usable_h_px:
            scale = max(0.75, round(usable_h_px / scroll_height - 0.005, 3))
            print(f"  [pdf] Scaling to {scale:.0%} ({scroll_height:.0f}px → {usable_h_px:.0f}px)")
        else:
            scale = 1.0

        await page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            scale=scale,
            margin=margins,
        )
        await browser.close()
    return output_path


CV_MARGINS = {"top": "12.7mm", "right": "12.7mm", "bottom": "12.7mm", "left": "12.7mm"}
CL_MARGINS = {"top": "16mm", "right": "20mm", "bottom": "16mm", "left": "20mm"}


def generate_cv_pdf(cv_markdown: str, output_path: Path) -> Path:
    html = _build_html(_markdown_cv_to_html(cv_markdown), CV_CSS)
    return asyncio.run(_render_pdf_async(html, output_path, CV_MARGINS))


def generate_cover_letter_pdf(cover_letter_text: str, output_path: Path,
                              cv_markdown: str = "") -> Path:
    """Cover letter with the same header as the CV (taken from `cv_markdown`)."""
    header = parse_header(cv_markdown) if cv_markdown.strip() else ("Liam Hasson", "", "")
    html = _build_html(_cover_letter_to_html(cover_letter_text, header), COVER_LETTER_CSS)
    return asyncio.run(_render_pdf_async(html, output_path, CL_MARGINS))
