"""Knowledge sources: the documents folder (PDF, Word, Excel, CSV), exact
spreadsheet answers, and web search (fallback, redaction, DuckDuckGo, pages)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from jarvis_core.adapters.documents.extractors import (
    UnreadableDocumentError,
    extract_text,
    make_table,
    read_tables,
)
from jarvis_core.adapters.documents.folder_index import FolderDocumentIndex
from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import SqliteDocumentChunkStore
from jarvis_core.adapters.web.duckduckgo import DuckDuckGoSearchProvider, parse_results
from jarvis_core.adapters.web.pages import HttpPageReader, is_public_url, page_text
from jarvis_core.api.app import create_app
from jarvis_core.application.persona import Persona, describe_abilities
from jarvis_core.application.spreadsheets import (
    describe_table,
    format_amount,
    match_file,
    parse_number,
)
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.web import (
    FallbackWebSearch,
    best_passages,
    redact_query,
)
from jarvis_core.config import Settings
from jarvis_core.container import Container, assemble
from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.models import ToolCall
from jarvis_core.domain.records import SearchResult
from tests.fakes import LOCAL, FakeEmbedder, FakeLlm, FakeVad

# ------------------------------------------------------------- test files


def write_pdf(path: Path, text: str) -> None:
    """A one-page PDF with ``text`` in Helvetica (pypdf can't write text itself)."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(bytes(out))


def write_scanned_pdf(path: Path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    with path.open("wb") as handle:
        writer.write(handle)


def write_docx(path: Path) -> None:
    import docx

    document = docx.Document()
    document.add_paragraph("Ryan Pacot — Senior Software Engineer")
    document.add_paragraph("Ten years building payment systems in Manila.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Skills"
    table.rows[0].cells[1].text = "Python, TypeScript"
    document.save(str(path))


def write_debts(path: Path) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Debts"
    sheet.append(["My debts 2026"])  # a title row above the header
    sheet.append(["Creditor", "Balance", "Monthly", "Rate", "Account no"])
    for row in [
        ("BDO card", 52000, 5000, 0.035, 1234),
        ("Home Credit", 8400, 1400, 0.029, 99),
        ("Pag-IBIG loan", 122000, 3100, 0.0625, 77),
    ]:
        sheet.append(row)
    for row in sheet.iter_rows(min_row=3):
        row[1].number_format = '"₱"#,##0.00'
        row[3].number_format = "0.0%"
    hidden = workbook.create_sheet("Scratch")
    hidden.append(["ignore", "me"])
    hidden.sheet_state = "hidden"
    workbook.save(str(path))


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    (root / "money").mkdir(parents=True)
    write_pdf(root / "resume.pdf", "Ryan worked at Globe Telecom from 2018 to 2023.")
    write_scanned_pdf(root / "scan.pdf")
    write_docx(root / "profile.docx")
    write_debts(root / "money" / "Debts 2026.xlsx")
    (root / "money" / "bills.csv").write_text(
        'Bill,Amount,Due date\nMeralco,"₱3,210.50",2026-11-20\nPLDT,PHP 1699,2026-11-25\n',
        encoding="utf-8",
    )
    (root / "~$Debts 2026.xlsx").write_bytes(b"lock")  # Office lock file
    (root / ".hidden").mkdir()
    (root / ".hidden" / "secret.txt").write_text("nope", encoding="utf-8")
    return root


def library(folder: Path | str, embedder: FakeEmbedder | None = None) -> FolderDocumentIndex:
    return FolderDocumentIndex(
        folder,
        SqliteDocumentChunkStore(Database(":memory:")),
        embedder or FakeEmbedder(),
        min_score=0.1,
        rescan_s=0,
    )


# ------------------------------------------------------------- extractors


def test_extracts_pdf_word_and_spreadsheets(folder: Path) -> None:
    assert "Globe Telecom" in extract_text(folder / "resume.pdf")
    word = extract_text(folder / "profile.docx")
    assert "Senior Software Engineer" in word
    assert "Skills | Python, TypeScript" in word
    sheet = extract_text(folder / "money" / "Debts 2026.xlsx", "money/Debts 2026.xlsx")
    assert "[money/Debts 2026.xlsx, sheet Debts]" in sheet
    assert "Creditor: BDO card; Balance: ₱52000; Monthly: 5000; Rate: 3.5%" in sheet
    assert "ignore" not in sheet  # hidden sheets are skipped


def test_scanned_pdf_is_reported_not_indexed(folder: Path) -> None:
    with pytest.raises(UnreadableDocumentError, match="scan"):
        extract_text(folder / "scan.pdf")
    with pytest.raises(UnreadableDocumentError, match="supported"):
        extract_text(folder / "photo.png")


def test_table_header_detection() -> None:
    table = make_table("f.csv", "f", [["Total", None], ["Name", "Amount"], ["A", "5"]])
    assert table is not None
    assert table.header == ("Name", "Amount")
    assert table.rows == (("A", "5"),)
    headerless = make_table("f.csv", "f", [["A", 5], ["B", 6, 7]])
    assert headerless is not None
    assert headerless.header == ("Column A", "Column B", "Column C")
    assert headerless.rows[0] == ("A", 5, None)
    assert make_table("f.csv", "f", [[None, ""], []]) is None


def test_csv_with_semicolons(tmp_path: Path) -> None:
    path = tmp_path / "budget.csv"
    path.write_text("Item;Cost\nRent;15000\nFood;8000\n", encoding="utf-8")
    [table] = read_tables(path, "budget.csv")
    assert table.header == ("Item", "Cost")
    assert "total 23,000" in describe_table(table)


# ----------------------------------------------------------- spreadsheets


@pytest.mark.parametrize(
    ("cell", "value", "currency", "percent"),
    [
        (52000, 52000.0, None, False),
        ("₱52,000.50", 52000.5, "₱", False),
        ("PHP 1,699", 1699.0, "₱", False),
        ("P 500", 500.0, "₱", False),
        ("(1,200)", -1200.0, None, False),
        ("-75", -75.0, None, False),
        ("3.5%", 3.5, None, True),
        ("$12", 12.0, "$", False),
    ],
)
def test_parse_number(cell: str | int, value: float, currency: str | None, percent: bool) -> None:
    parsed = parse_number(cell)
    assert parsed is not None
    assert (parsed.value, parsed.currency, parsed.percent) == (value, currency, percent)


@pytest.mark.parametrize("cell", [None, "", "BDO card", "2026-11-20", "n/a", "Pasig"])
def test_parse_number_rejects_text(cell: str | None) -> None:
    assert parse_number(cell) is None


def test_describe_table_adds_up_exactly(folder: Path) -> None:
    [table] = read_tables(folder / "money" / "Debts 2026.xlsx", "money/Debts 2026.xlsx")
    text = describe_table(table)
    assert "Balance: total ₱182,400, largest ₱122,000 (Pag-IBIG loan)" in text
    assert "smallest ₱8,400 (Home Credit)" in text
    assert "Monthly: total 9,500" in text
    assert "Rate: largest 6.25%" in text and "Rate: total" not in text  # rates don't add up
    assert "Account no:" not in text  # identifiers are not summarised

    bdo = describe_table(table, "bdo")
    assert '1 row(s) matching "bdo" of 3' in bdo
    assert "Balance: total ₱52,000." in bdo


def test_format_amount() -> None:
    assert format_amount(4909.5, "₱") == "₱4,909.50"
    assert format_amount(182400.0, "₱") == "₱182,400"
    assert format_amount(3166.666) == "3,166.67"
    assert format_amount(-75) == "-75"
    assert format_amount(6.25, percent=True) == "6.25%"


def test_match_file() -> None:
    names = ["money/Debts 2026.xlsx", "money/bills.csv", "budget.xlsx"]
    assert match_file("debts", names) == "money/Debts 2026.xlsx"
    assert match_file("my debt spreadsheet", names) == "money/Debts 2026.xlsx"
    assert match_file("bill", names) == "money/bills.csv"
    assert match_file("car loan", names) is None
    assert match_file("excel", names) is None


# ------------------------------------------------------------ folder index


async def test_index_reads_every_kind_and_reports_problems(folder: Path) -> None:
    docs = library(folder)
    assert await docs.refresh() == 4  # pdf, docx, xlsx, csv; the scan has no text

    hits = await docs.search("Globe Telecom work history")
    assert hits[0].path == "resume.pdf"
    status = await docs.status()
    assert [f.path for f in status.files] == [
        "money/Debts 2026.xlsx",
        "money/bills.csv",
        "profile.docx",
        "resume.pdf",
        "scan.pdf",
    ]
    scan = next(f for f in status.files if f.path == "scan.pdf")
    assert scan.chunks == 0 and scan.problem and "scan" in scan.problem
    assert all(f.chunks for f in status.files if f.path != "scan.pdf")

    assert await docs.refresh() == 0  # unchanged files (and the known-bad scan) are skipped
    assert await docs.spreadsheets() == ["money/Debts 2026.xlsx", "money/bills.csv"]


async def test_switching_folders_drops_the_old_files(folder: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    (other / "notes.md").write_text("Adobo recipe: vinegar and soy sauce.", encoding="utf-8")
    docs = library(folder)
    await docs.refresh()
    docs.set_folder(f'"{other}"')  # pasted with quotes ("Copy as path")
    await docs.refresh()
    assert docs.folder == str(other)
    assert [h.path for h in await docs.search("adobo vinegar recipe")] == ["notes.md"]
    assert all(h.path == "notes.md" for h in await docs.search("Globe Telecom"))

    docs.set_folder("")
    assert (await docs.status()).folder == ""
    assert await docs.search("adobo") == []


async def test_embedding_failure_is_reported(folder: Path) -> None:
    embedder = FakeEmbedder()
    embedder.fail = True
    docs = library(folder, embedder)
    assert await docs.refresh() == 0
    status = await docs.status()
    assert status.error and "embedding model" in status.error


async def test_tables_refuses_paths_outside_the_folder(folder: Path) -> None:
    docs = library(folder)
    with pytest.raises(JarvisError):
        await docs.tables("../outside.csv")
    [table] = await docs.tables("money/bills.csv")
    assert table.sheet == "bills"


# ------------------------------------------------------------------ tools


async def test_document_tools(folder: Path) -> None:
    docs = library(folder)
    await docs.refresh()
    registry = ToolRegistry()
    registry.extend(builtin.document_tools(docs, "Ryan"))

    total = await registry.execute(ToolCall("read_spreadsheet", {"file": "debts"}))
    assert "total ₱182,400" in total
    bdo = await registry.execute(ToolCall("read_spreadsheet", {"file": "debts", "filter": "BDO"}))
    assert "Balance: total ₱52,000." in bdo
    which = await registry.execute(ToolCall("read_spreadsheet", {}))
    assert which.startswith("Which spreadsheet?") and "money/bills.csv" in which
    missing = await registry.execute(ToolCall("read_spreadsheet", {"file": "car"}))
    assert "No spreadsheet matches 'car'" in missing

    listed = await registry.execute(ToolCall("list_documents", {}))
    assert listed.startswith("5 files (2 spreadsheet, 2 PDF, 1 Word)")

    found = await registry.execute(ToolCall("search_documents", {"query": "Globe Telecom"}))
    assert "[resume.pdf]" in found and "name the file" in found


async def test_document_tools_without_a_folder() -> None:
    registry = ToolRegistry()
    registry.extend(builtin.document_tools(library(""), "Ryan"))
    for name, args in [("search_documents", {"query": "resume"}), ("read_spreadsheet", {})]:
        result = await registry.execute(ToolCall(name, args))
        assert "Settings → Knowledge" in result and "Ryan" in result


# --------------------------------------------------------------------- web


def test_redact_query_removes_personal_numbers() -> None:
    assert redact_query("BDO card 4321 5678 9012 3456 interest") == "BDO card interest"
    assert redact_query("call 0917-123-4567 now") == "call now"
    assert redact_query("email ryan@example.com about PSEi") == "email about PSEi"
    assert redact_query("price of 1,500 shares in 2026") == "price of 1,500 shares in 2026"


class _Search:
    def __init__(self, label: str, results: list[SearchResult] | None = None) -> None:
        self.label = label
        self.results = results
        self.queries: list[str] = []

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        self.queries.append(query)
        if self.results is None:
            raise JarvisError("down")
        return self.results


async def test_fallback_search() -> None:
    hit = [SearchResult("PSEi closes higher", "The index rose 1%.", "https://www.rappler.com/x")]
    down, backup = _Search("SearXNG"), _Search("DuckDuckGo", hit)
    search = FallbackWebSearch([down, backup])
    assert search.label == "SearXNG, then DuckDuckGo"
    assert await search.search("psei") == hit
    with pytest.raises(JarvisError):
        await FallbackWebSearch([_Search("a"), _Search("b")]).search("q")


DDG_HTML = """
<div class="result results_links result--ad">
  <a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=shop.example">Buy now</a>
  <a class="result__snippet" href="#">An advert</a>
</div>
<div class="result results_links">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.rappler.com%2Fbusiness%2Fpsei&amp;rut=abc">
    PSEi <b>closes</b> higher</a></h2>
  <a class="result__snippet" href="#">The <b>index</b> rose 1% on Friday.</a>
</div>
<div class="result results_links">
  <a class="result__a" href="https://example.org/direct">Direct link</a>
  <div class="result__snippet">No redirect here.</div>
</div>
"""


def test_parse_duckduckgo_results() -> None:
    results = parse_results(DDG_HTML)
    assert [(r.title, r.url, r.snippet) for r in results] == [
        (
            "PSEi closes higher",
            "https://www.rappler.com/business/psei",
            "The index rose 1% on Friday.",
        ),
        ("Direct link", "https://example.org/direct", "No redirect here."),
    ]


async def test_duckduckgo_backs_off_after_a_captcha() -> None:
    calls = []
    now = [1000.0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(202, text='<div class="anomaly-modal">bots</div>')
        return httpx.Response(200, text=DDG_HTML)

    client = httpx.AsyncClient(base_url="https://ddg", transport=httpx.MockTransport(handler))
    provider = DuckDuckGoSearchProvider(client=client, cooldown_s=300, clock=lambda: now[0])
    with pytest.raises(JarvisError, match="limiting"):
        await provider.search("psei")
    with pytest.raises(JarvisError, match="limiting"):
        await provider.search("psei")  # still cooling down: no request at all
    assert len(calls) == 1
    now[0] += 301
    assert len(await provider.search("psei")) == 2
    assert calls[1].content.decode().startswith("q=psei")


def test_page_text_and_best_passages() -> None:
    html = """<html><head><script>var x = 'menu';</script><style>p{}</style></head>
    <body><nav>Home | News | Sports</nav>
    <p>The Philippine Stock Exchange index closed 1.2 percent higher at 6,500 points
    on Friday as banks rallied.</p>
    <p>Elsewhere, the weather in Manila stayed sunny and warm through the weekend, with
    no rain expected.</p><footer>Copyright</footer></body></html>"""
    text = page_text(html)
    assert "menu" not in text and "Home | News" not in text and "Copyright" not in text
    [passage] = best_passages(text, "PSEi stock exchange index today", count=1)
    assert passage.startswith("The Philippine Stock Exchange index closed")


async def test_private_addresses_are_never_fetched() -> None:
    assert not await is_public_url("http://127.0.0.1:8765/api/settings")
    assert not await is_public_url("http://192.168.1.10/")
    assert not await is_public_url("https://my-pc.tailnet.ts.net/")
    assert not await is_public_url("file:///C:/Windows")
    reader = HttpPageReader()
    with pytest.raises(JarvisError, match="public"):
        await reader.read("http://localhost:8765/")


async def test_web_search_tool_reads_the_top_pages() -> None:
    class Reader:
        async def read(self, url: str) -> str:
            if "bad" in url:
                raise JarvisError("nope")
            return (
                "Short menu line\n"
                "The PSEi rose 1.2 percent to 6,500 on Friday, led by banks and property firms."
            )

    results = [
        SearchResult("PSEi up", "Index rises.", "https://www.rappler.com/psei"),
        SearchResult("Broken", "x", "https://bad.example/psei"),
    ]
    search = _Search("DuckDuckGo", results)
    registry = ToolRegistry()
    registry.extend(builtin.web_search_tools(search, Reader()))
    text = await registry.execute(ToolCall("web_search", {"query": "PSEi today 0917-123-4567"}))
    assert search.queries == ["PSEi today"]  # the phone number never left
    assert "1. PSEi up (rappler.com): Index rises." in text
    assert "From rappler.com: The PSEi rose 1.2 percent" in text
    assert "bad.example:" not in text.split("From", 1)[-1]


# ---------------------------------------------------------- persona & API


def test_persona_lists_web_and_documents() -> None:
    abilities = describe_abilities(web=True, documents=True)
    prompt = Persona("Jarvis", "Ryan", "", abilities=abilities).system_message(
        tools_on_request=True
    )
    assert "searching the internet" in prompt.content
    assert "documents" in prompt.content
    assert "Never say you can't do something listed here" in prompt.content


@pytest.fixture
def container(folder: Path) -> Container:
    return assemble(
        Settings(tools_enabled=True, documents_dir=str(folder), documents_rescan_s=0),
        llm=FakeLlm([]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
        documents=library(""),
        web_search=_Search("DuckDuckGo", []),
    )


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container=container), client=LOCAL) as test_client:
        yield test_client


async def test_knowledge_api(container: Container, client: TestClient, folder: Path) -> None:
    assert container.documents is not None
    assert container.documents.folder == str(folder)  # from the setting
    assert isinstance(container.documents, FolderDocumentIndex)
    await container.documents.refresh()

    body = client.get("/api/knowledge").json()
    docs = body["documents"]
    assert (docs["folder"], docs["exists"], docs["total"], docs["indexed"]) == (
        str(folder),
        True,
        5,
        4,
    )
    assert docs["by_kind"] == {"spreadsheet": 2, "word": 1, "pdf": 2}
    assert body["web"] == {
        "enabled": True,
        "provider": "DuckDuckGo",
        "mode": "auto",
        "searxng": False,
        "reads_pages": True,
    }
    assert client.post("/api/documents/reindex").status_code == 202
    tool_names = {spec.name for spec in container.tools.specs()}
    assert {"search_documents", "read_spreadsheet", "list_documents", "web_search"} <= tool_names


def test_documents_folder_is_changed_only_on_the_pc(
    container: Container, client: TestClient, tmp_path: Path
) -> None:
    token = client.post("/api/devices", json={"name": "Phone"}).json()["token"]
    with TestClient(create_app(container=container), client=("100.64.0.5", 5000)) as phone:
        headers = {"Authorization": f"Bearer {token}"}
        refused = phone.put("/api/settings", json={"documents_dir": "C:/"}, headers=headers)
        assert refused.status_code == 403
        same = phone.put(
            "/api/settings",
            json={"documents_dir": container.runtime.current.documents_dir, "tts_speed": 1.1},
            headers=headers,
        )
        assert same.status_code == 200
    moved = client.put("/api/settings", json={"documents_dir": f'"{tmp_path}"'})
    assert moved.json()["values"]["documents_dir"] == str(tmp_path)
    assert container.documents is not None and container.documents.folder == str(tmp_path)
