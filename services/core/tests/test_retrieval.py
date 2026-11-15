"""Hybrid document retrieval: BM25 keywords + embeddings, file-name bonus,
neighbouring passages, embedding task prefixes and re-indexing on change."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from jarvis_core.adapters.documents.folder_index import SIGNATURE_KEY, FolderDocumentIndex
from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import (
    SqliteDocumentChunkStore,
    SqlitePreferenceStore,
)
from jarvis_core.application.retrieval import (
    NAME_BONUS,
    KeywordIndex,
    embedding_prefixes,
    fuse,
    names_in_query,
    tokenize,
)
from tests.fakes import FakeEmbedder

# ------------------------------------------------------------ pure logic


def test_tokenize_folds_plurals_and_drops_stopwords() -> None:
    assert tokenize("What are my Meralco bills?") == ["meralco", "bill"]
    assert tokenize("Policy no. PH-2026-00451") == ["policy", "no", "ph", "2026", "00451"]
    assert tokenize("class address") == ["class", "address"]  # -ss stays


def test_keyword_index_finds_exact_codes() -> None:
    passages = [
        "Car insurance with Malayan. Policy number PH-2026-00451, renews in March.",
        "Health card from Maxicare, member since 2021.",
        "Meralco bill for October: 3,210 pesos.",
    ]
    index = KeywordIndex(passages)
    assert index.search("what is policy PH-2026-00451?")[0][0] == 0
    assert [p for p, _ in index.search("meralco")] == [2]
    assert index.search("weather tomorrow") == []
    assert index.search("") == []


def test_keyword_index_ignores_terms_found_everywhere() -> None:
    passages = [f"Payment {i} for the month." for i in range(10)] + ["BDO payment schedule."]
    index = KeywordIndex(passages)
    # "payment" is in every passage, so only "bdo" decides.
    assert [p for p, _ in index.search("BDO payment")] == [10]


def test_fuse_combines_rankings_and_applies_the_name_bonus() -> None:
    ranked = fuse([1, 2, 3], [3, 4], limit=4)
    assert ranked[0].position == 3  # in both lists
    assert {r.position for r in ranked} == {1, 2, 3, 4}
    boosted = fuse([1, 2], [], bonus=[2], limit=2)
    assert [r.position for r in boosted] == [2, 1]
    assert boosted[0].score == pytest.approx(1 / 62 + NAME_BONUS)
    assert fuse([], [], bonus=[5]) == []  # the bonus alone never adds a passage


def test_names_in_query() -> None:
    names = ["cv/resume.pdf", "money/Debts 2026.xlsx", "car-insurance_policy.pdf", "notes.md"]
    assert names_in_query("what's on my resume", names) == {"cv/resume.pdf"}
    assert names_in_query("how much are my debts", names) == {"money/Debts 2026.xlsx"}
    assert names_in_query("car insurance renewal", names) == {"car-insurance_policy.pdf"}
    assert names_in_query("insurance", names) == set()  # 1 of 3 words isn't enough
    assert names_in_query("cv folder", names) == set()  # folders don't count


@pytest.mark.parametrize(
    ("model", "prefixes"),
    [
        ("nomic-embed-text", ("search_query: ", "search_document: ")),
        ("nomic-embed-text:latest", ("search_query: ", "search_document: ")),
        (
            "mxbai-embed-large:335m",
            ("Represent this sentence for searching relevant passages: ", ""),
        ),
        ("all-minilm", ("", "")),
    ],
)
def test_embedding_prefixes(model: str, prefixes: tuple[str, str]) -> None:
    assert embedding_prefixes(model) == prefixes


# ------------------------------------------------------------ the index


class ConstantEmbedder:
    """Every text means the same: only keywords can tell passages apart."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.fail_queries = False

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail_queries and any(t.startswith("Q: ") for t in texts):
            raise RuntimeError("embedding model unloaded")
        self.texts += texts
        return [[1.0, 0.0, 0.0] for _ in texts]


def write(folder: Path, name: str, text: str) -> None:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_index(folder: Path, embedder: object, **kwargs: object) -> FolderDocumentIndex:
    return FolderDocumentIndex(
        folder,
        SqliteDocumentChunkStore(Database(":memory:")),
        embedder,  # type: ignore[arg-type]
        rescan_s=0,
        **kwargs,  # type: ignore[arg-type]
    )


async def test_keywords_find_what_embeddings_cannot(tmp_path: Path) -> None:
    write(tmp_path, "insurance.md", "Car insurance with Malayan. Policy number PH-2026-00451.")
    write(tmp_path, "health.md", "Health card from Maxicare, member since 2021.")
    index = make_index(tmp_path, ConstantEmbedder(), min_score=0.99)
    await index.refresh()
    hits = await index.search("Which insurer has policy PH-2026-00451?")
    assert hits[0].path == "insurance.md"


async def test_search_still_works_when_query_embedding_fails(tmp_path: Path) -> None:
    write(tmp_path, "health.md", "Health card from Maxicare, member since 2021.")
    embedder = ConstantEmbedder()
    index = make_index(tmp_path, embedder, query_prefix="Q: ")
    await index.refresh()
    embedder.fail_queries = True
    assert [h.path for h in await index.search("Maxicare")] == ["health.md"]


async def test_a_named_file_wins(tmp_path: Path) -> None:
    write(tmp_path, "resume.md", "Senior engineer. Worked at Globe Telecom 2018 to 2023.")
    write(tmp_path, "notes.md", "Ideas for engineer meetups and work talks at Globe.")
    index = make_index(tmp_path, FakeEmbedder(), min_score=0.0)
    await index.refresh()
    hits = await index.search("where did I work, according to my resume?")
    assert hits[0].path == "resume.md"


async def test_top_hits_include_the_next_passage(tmp_path: Path) -> None:
    first = "Employment history. " + "Accenture, technology consultant. " * 22
    second = "Before that: Globe Telecom, software engineer, 2018 to 2023."
    write(tmp_path, "resume.md", f"{first}\n\n{second}")
    index = make_index(tmp_path, FakeEmbedder(), min_score=0.0)
    await index.refresh()
    assert (await index.status()).files[0].chunks == 2
    [hit] = await index.search("employment history accenture", limit=1)
    assert hit.text.startswith("Employment history.")
    assert "Globe Telecom" in hit.text  # the following passage came along


async def test_prefixes_and_reindex_when_the_embedding_setup_changes(tmp_path: Path) -> None:
    write(tmp_path, "a.md", "Adobo recipe with vinegar.")
    database = Database(":memory:")
    store = SqliteDocumentChunkStore(database)
    meta = SqlitePreferenceStore(database)

    def index(embedder: ConstantEmbedder, signature: str) -> FolderDocumentIndex:
        return FolderDocumentIndex(
            tmp_path,
            store,
            embedder,
            rescan_s=0,
            query_prefix="search_query: ",
            document_prefix="search_document: ",
            meta=meta,
            signature=signature,
        )

    first = ConstantEmbedder()
    assert await index(first, "nomic-embed-text").refresh() == 1
    assert first.texts == ["search_document: a.md\nAdobo recipe with vinegar."]
    assert "nomic-embed-text" in str(await meta.get(SIGNATURE_KEY))

    same = ConstantEmbedder()
    assert await index(same, "nomic-embed-text").refresh() == 0  # nothing changed
    await index(same, "nomic-embed-text").search("adobo")
    assert same.texts == ["search_query: adobo"]

    switched = ConstantEmbedder()
    assert await index(switched, "mxbai-embed-large").refresh() == 1  # new model: re-embed
    assert await index(switched, "mxbai-embed-large").refresh() == 0
