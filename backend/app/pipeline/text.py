"""Load the text of a downloaded file: PDF pages, or cleaned HTML / .eml."""

import io
import re
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

import pdfplumber
from bs4 import BeautifulSoup

from app.pipeline.detect import FileKind

MAX_PDF_PAGES = 50


class TooManyPages(Exception):
    """Raised when a PDF exceeds MAX_PDF_PAGES."""


@dataclass(frozen=True)
class LoadedText:
    kind: FileKind
    pages: list[str]


def _strip_nul(text: str) -> str:
    """Postgres rejects NUL in text and JSON columns."""
    return text.replace("\x00", "")


def clean_html(html: str) -> str:
    """Convert HTML to plain text.

    Drops script and style. A table containing other tables is layout: it is
    unwrapped so its text appears once. Innermost tables become one
    `a | b | c` line per row.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for table in reversed(soup.find_all("table")):  # innermost first
        if table.find("table"):
            for part in table.find_all(["tr", "td", "th"]):
                part.append("\n")
            table.unwrap()
            continue
        rows = [
            " | ".join(c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"]))
            for tr in table.find_all("tr")
        ]
        table.replace_with("\n" + "\n".join(rows) + "\n")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "li"]):
        block.append("\n")
    text = soup.get_text("")
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return _strip_nul(re.sub(r"\n{2,}", "\n", text).strip())


def eml_body(data: bytes) -> str:
    """Return the largest text/html part, else the text/plain body."""
    return eml_part(data)[0]


def eml_part(data: bytes) -> tuple[str, str]:
    """Return (body, subtype): the largest text/html part, else text/plain, else ("", "plain")."""
    message = BytesParser(policy=policy.default).parsebytes(data)
    for subtype in ("html", "plain"):
        parts = [
            p
            for p in message.walk()
            if p.get_content_type() == f"text/{subtype}" and not p.is_attachment()
        ]
        if parts:
            return max((p.get_content() for p in parts), key=len), subtype
    return "", "plain"


def load_text(data: bytes, kind: FileKind) -> LoadedText:
    """Extract text pages from a PDF, HTML or .eml file. CSV/xlsx are not text-loaded."""
    if kind == "pdf":
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                raise TooManyPages(f"{len(pdf.pages)} pages")
            return LoadedText(kind, [_strip_nul(page.extract_text() or "") for page in pdf.pages])
    if kind == "html":
        return LoadedText(kind, [clean_html(data.decode("utf-8", errors="replace"))])
    if kind == "eml":
        body = eml_body(data)
        is_html = "<" in body and re.search(r"<(html|body|p|div|table)\b", body, re.I)
        return LoadedText(kind, [clean_html(body) if is_html else _strip_nul(body.strip())])
    raise ValueError(f"load_text does not handle {kind!r}")
