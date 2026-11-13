"""Read the text out of the files in the user's documents folder.

Supported: plain-text notes, PDF (``pypdf``), Word ``.docx`` (``python-docx``)
and spreadsheets ``.xlsx``/``.xlsm`` (``openpyxl``) and ``.csv``/``.tsv``
(standard library). All are pure Python and read the file locally; nothing is
uploaded anywhere.

Scanned PDFs (photos of paper) contain no text layer and come back empty;
:class:`UnreadableDocumentError` says so.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time
from pathlib import Path

from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.records import Cell, SheetTable

TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".rst", ".org"})
PDF_SUFFIXES = frozenset({".pdf"})
WORD_SUFFIXES = frozenset({".docx"})
SHEET_SUFFIXES = frozenset({".xlsx", ".xlsm", ".csv", ".tsv"})
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES | WORD_SUFFIXES | SHEET_SUFFIXES

MAX_PDF_PAGES = 300
MAX_SHEET_ROWS = 5000
MAX_SHEET_COLUMNS = 40
MAX_SHEETS = 20
#: Rows per indexed passage, so a passage keeps its sheet name for context.
ROWS_PER_PASSAGE = 8
_CURRENCY_FORMATS = ("₱", "PHP", "$", "€", "£", "¥")

# pypdf reports every odd PDF construct as a warning; the index has its own logging.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class UnreadableDocumentError(JarvisError):
    """A file was found but no text could be read from it."""


def kind_of(path: Path) -> str | None:
    """``text``, ``pdf``, ``word`` or ``spreadsheet``; ``None`` if unsupported."""
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix in PDF_SUFFIXES:
        return "pdf"
    if suffix in WORD_SUFFIXES:
        return "word"
    if suffix in SHEET_SUFFIXES:
        return "spreadsheet"
    return None


def extract_text(path: Path, name: str | None = None) -> str:
    """The searchable text of ``path`` (blocking; run it in a worker thread).

    Args:
        path: The file.
        name: How to refer to the file in spreadsheet passages (relative path).

    Raises:
        UnreadableDocumentError: The file is unsupported, damaged, encrypted
            or has no text (a scanned PDF).
    """
    kind = kind_of(path)
    try:
        if kind == "text":
            text = path.read_text(encoding="utf-8", errors="ignore")
        elif kind == "pdf":
            text = _pdf_text(path)
        elif kind == "word":
            text = _docx_text(path)
        elif kind == "spreadsheet":
            text = tables_to_text(read_tables(path, name or path.name))
        else:
            raise UnreadableDocumentError(f"{path.suffix or 'this'} files aren't supported")
    except UnreadableDocumentError:
        raise
    except Exception as exc:
        raise UnreadableDocumentError(f"couldn't be read ({type(exc).__name__})") from exc
    if not text.strip():
        hint = "no text layer — probably a scan" if kind == "pdf" else "it's empty"
        raise UnreadableDocumentError(hint)
    return text


def read_tables(path: Path, name: str) -> list[SheetTable]:
    """Every non-empty sheet of a spreadsheet (blocking).

    Args:
        path: An ``.xlsx``, ``.xlsm``, ``.csv`` or ``.tsv`` file.
        name: The file's relative path, stored on each table.
    """
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        sheets = [(path.stem, _csv_rows(path, "\t" if suffix == ".tsv" else None))]
    elif suffix in {".xlsx", ".xlsm"}:
        sheets = _xlsx_sheets(path)
    else:
        raise UnreadableDocumentError(f"{suffix} isn't a spreadsheet")
    tables = []
    for sheet, rows in sheets:
        table = make_table(name, sheet, rows)
        if table is not None:
            tables.append(table)
    return tables


def make_table(file: str, sheet: str, raw_rows: Iterable[Sequence[Cell]]) -> SheetTable | None:
    """Find the header row and square up the data rows.

    The header is the first row (within the first ten) with at least two
    filled cells that are mostly text. Without one, columns are named
    ``Column A``, ``Column B``, …

    Returns:
        The table, or ``None`` when the sheet is empty.
    """
    rows = [_trim(row) for row in raw_rows]
    rows = [row for row in rows if row]
    if not rows:
        return None
    header_at = next(
        (i for i, row in enumerate(rows[:10]) if _looks_like_header(row)),
        None,
    )
    if header_at is None:
        width = max(len(row) for row in rows)
        header = tuple(f"Column {_column_letter(i)}" for i in range(width))
        data = rows
    else:
        width = max(len(row) for row in rows[header_at:])
        names = rows[header_at]
        header = tuple(
            str(names[i]).strip()
            if i < len(names) and names[i] not in (None, "")
            else f"Column {_column_letter(i)}"
            for i in range(width)
        )
        data = rows[header_at + 1 :]
    squared = tuple(tuple(row) + (None,) * (width - len(row)) for row in data)
    return SheetTable(file=file, sheet=sheet, header=header, rows=squared)


def tables_to_text(tables: Sequence[SheetTable]) -> str:
    """Spreadsheet contents as passages for semantic search.

    Each passage names its file and sheet and lists a few rows as
    ``Column: value`` pairs, so a match can be understood on its own.
    """
    passages: list[str] = []
    for table in tables:
        label = f"{table.file}, sheet {table.sheet}"
        passages.append(f"Spreadsheet {label}. Columns: {', '.join(table.header)}.")
        for start in range(0, len(table.rows), ROWS_PER_PASSAGE):
            lines = [
                "; ".join(
                    f"{name}: {_show(value)}"
                    for name, value in zip(table.header, row, strict=True)
                    if value not in (None, "")
                )
                for row in table.rows[start : start + ROWS_PER_PASSAGE]
            ]
            passages.append(f"[{label}]\n" + "\n".join(line for line in lines if line))
    return "\n\n".join(passages)


# ------------------------------------------------------------------ helpers


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted and not reader.decrypt(""):
        raise UnreadableDocumentError("it's password-protected")
    pages = [page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES]]
    return "\n\n".join(page.strip() for page in pages if page.strip())


def _docx_text(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        rows = [
            " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            for row in table.rows
        ]
        parts.append("\n".join(row for row in rows if row))
    return "\n\n".join(part for part in parts if part)


def _csv_rows(path: Path, delimiter: str | None) -> list[list[Cell]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[list[Cell]] = []
    for row in reader:
        rows.append([cell.strip() or None for cell in row[:MAX_SHEET_COLUMNS]])
        if len(rows) >= MAX_SHEET_ROWS:
            break
    return rows


def _xlsx_sheets(path: Path) -> list[tuple[str, list[list[Cell]]]]:
    from openpyxl import load_workbook

    # data_only: formulas come back as the values Excel last calculated.
    workbook = load_workbook(str(path), read_only=True, data_only=True)
    try:
        sheets = []
        for sheet in workbook.worksheets[:MAX_SHEETS]:
            if getattr(sheet, "sheet_state", "visible") != "visible":
                continue
            rows: list[list[Cell]] = []
            for row in sheet.iter_rows(max_col=MAX_SHEET_COLUMNS):
                rows.append([_cell(c.value, getattr(c, "number_format", "")) for c in row])
                if len(rows) >= MAX_SHEET_ROWS:
                    break
            sheets.append((sheet.title, rows))
        return sheets
    finally:
        workbook.close()


def _cell(value: object, number_format: str | None) -> Cell:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        fmt = number_format or ""
        symbol = next((s for s in _CURRENCY_FORMATS if s in fmt), None)
        if symbol is not None:
            return f"{'₱' if symbol == 'PHP' else symbol}{value}"
        if "%" in fmt:
            return f"{value * 100:g}%"
        return value
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time() else value.isoformat(" ")
    if isinstance(value, date | time):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _trim(row: Sequence[Cell]) -> list[Cell]:
    cells = list(row)
    while cells and cells[-1] in (None, ""):
        cells.pop()
    return cells


def _looks_like_header(row: Sequence[Cell]) -> bool:
    filled = [cell for cell in row if cell not in (None, "")]
    if len(filled) < 2:
        return False
    texts = [cell for cell in filled if isinstance(cell, str) and not _is_numeric_text(cell)]
    # At most one number or date (e.g. a year column header like 2026).
    return len(texts) >= max(2, len(filled) - 1)


def _is_numeric_text(text: str) -> bool:
    cleaned = text.replace(",", "").replace("₱", "").replace("%", "").strip()
    try:
        float(cleaned)
    except ValueError:
        return False
    return True


def _show(value: Cell) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters
