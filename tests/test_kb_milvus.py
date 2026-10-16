from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "api")]

from app.config import Settings
from app.services.kb_chunks import collect_corpus
from app.services.kb_embed import EmbeddingError, embed_text
from app.services.kb_milvus import (
    ALLOWED_COLLECTION,
    MilvusCollectionError,
    collection_name,
    search_vectors,
)


def test_paper_literature_is_rejected_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    constructed: list[object] = []

    def forbid(*_args, **_kwargs):
        constructed.append(True)
        raise AssertionError("must not construct a Milvus client")

    monkeypatch.setattr("app.services.kb_milvus.MilvusClient", forbid)
    settings = Settings(
        milvus_uri="http://121.37.215.121:19530",
        milvus_token="root:secret",
        milvus_collection_name="paper_literature",
    )
    with pytest.raises(MilvusCollectionError):
        collection_name(settings)
    assert constructed == []


def test_search_only_names_ippilab(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []

    class FakeClient:
        def has_collection(self, name: str) -> bool:
            seen.append(("has", name))
            return True

        def describe_collection(self, name: str) -> dict:
            seen.append(("describe", name))
            return {"fields": [{"name": "vector", "params": {"dim": 1024}}]}

        def describe_index(self, name: str, _field: str) -> dict:
            seen.append(("index", name))
            return {"metric_type": "COSINE"}

        def get_collection_stats(self, name: str) -> dict:
            seen.append(("stats", name))
            return {"row_count": 2}

        def search(self, *, collection_name: str, **_kwargs):
            seen.append(("search", collection_name))
            return [
                [
                    {
                        "id": 1,
                        "distance": 0.81,
                        "entity": {
                            "parent_text": "NEU-20 不是论文完整 test split",
                            "parent_id": "parent-1",
                            "file_name": "writing.md",
                            "section_path": "写作纪律",
                            "source_label": "导师审定",
                            "slug": "writing-protocol",
                        },
                    }
                ]
            ]

    monkeypatch.setattr("app.services.kb_milvus.MilvusClient", lambda *_a, **_k: FakeClient())
    settings = Settings(
        milvus_uri="http://example:19530",
        milvus_token="root:secret",
        milvus_collection_name=ALLOWED_COLLECTION,
        llm_embed_dim=1024,
    )
    hits = search_vectors(settings, [0.0] * 1024)
    assert hits is not None
    assert hits[0]["title"] == "写作纪律"
    assert {name for _op, name in seen} == {ALLOWED_COLLECTION}
    assert "paper_literature" not in repr(seen)


def _search_settings() -> Settings:
    return Settings(
        milvus_uri="http://example:19530",
        milvus_token="root:secret",
        milvus_collection_name=ALLOWED_COLLECTION,
        llm_embed_dim=1024,
    )


def _install_search(monkeypatch: pytest.MonkeyPatch, rows: list[dict], seen: dict | None = None) -> None:
    class FakeClient:
        def has_collection(self, _name: str) -> bool:
            return True

        def describe_collection(self, _name: str) -> dict:
            return {"fields": [{"name": "vector", "params": {"dim": 1024}}]}

        def describe_index(self, _name: str, _field: str) -> dict:
            return {"metric_type": "COSINE"}

        def get_collection_stats(self, _name: str) -> dict:
            return {"row_count": len(rows)}

        def search(self, *, collection_name: str, limit: int, **_kwargs):
            if seen is not None:
                seen["collection"] = collection_name
                seen["limit"] = limit
            return [rows]

    monkeypatch.setattr("app.services.kb_milvus.MilvusClient", lambda *_a, **_k: FakeClient())


def test_diversify_keeps_lower_score_card(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = []
    for index, score in enumerate((0.91, 0.88, 0.86, 0.84)):
        rows.append(
            {
                "id": index,
                "distance": score,
                "entity": {
                    "parent_text": f"表行 {index}",
                    "parent_id": f"row-{index}",
                    "file_name": "steel_defect_segmentation_review.md",
                    "section_path": "排行榜",
                    "source_label": "分割稿",
                    "slug": "seg",
                    "block_type": "table_row",
                },
            }
        )
    rows.append(
        {
            "id": 9,
            "distance": 0.7,
            "entity": {
                "parent_text": "ResNet DOI 10.1109/cvpr.2016.90",
                "parent_id": "card-1",
                "file_name": "课题组学习路线安排.md",
                "section_path": "12.1 ResNet",
                "source_label": "学习路线",
                "slug": "path",
                "block_type": "paper_card",
            },
        }
    )
    seen: dict = {}
    _install_search(monkeypatch, rows, seen)
    hits = search_vectors(_search_settings(), [0.0] * 1024, query="检测和分割差在哪")
    assert seen["limit"] == 24
    assert hits is not None
    assert any(item["block_type"] == "paper_card" for item in hits)
    assert sum(item["block_type"] == "table_row" for item in hits) < len(hits)


def test_proper_name_rescues_narrow_score(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "id": 1,
            "distance": 0.46,
            "entity": {
                "parent_text": "NEU-20 不是论文完整 test split",
                "parent_id": "neu",
                "file_name": "写作与实验纪律",
                "section_path": "写作与实验纪律",
                "source_label": "导师审定",
                "slug": "writing-protocol",
                "block_type": "narrative",
            },
        },
        {
            "id": 2,
            "distance": 0.46,
            "entity": {
                "parent_text": "一张没有专名的表",
                "parent_id": "plain",
                "file_name": "steel_defect_detection_review.md",
                "section_path": "数据集",
                "source_label": "检测稿",
                "slug": "det",
                "block_type": "table_row",
            },
        },
        {
            "id": 3,
            "distance": 0.43,
            "entity": {
                "parent_text": "番茄叶片病害数据集",
                "parent_id": "tomato",
                "file_name": "steel_defect_segmentation_review.md",
                "section_path": "数据集",
                "source_label": "分割稿",
                "slug": "seg",
                "block_type": "table_row",
            },
        },
    ]
    _install_search(monkeypatch, rows)
    hits = search_vectors(_search_settings(), [0.0] * 1024, query="NEU-20 是不是论文完整 test split")
    assert hits is not None
    assert [item["parent_id"] for item in hits] == ["neu"]


def test_embed_uses_cache_and_survives_cache_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[int] = []

    class Response:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": {"embedding": [0.25] * 1024, "object": "embedding"}}

    class Client:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

        def post(self, *_args, **_kwargs):
            posted.append(1)
            return Response()

    monkeypatch.setattr("app.services.kb_embed.httpx.Client", Client)
    monkeypatch.setattr("app.cache.cache_get_json", lambda _key: None)
    monkeypatch.setattr("app.cache.cache_set_json", lambda *_args, **_kwargs: None)
    settings = Settings(
        llm_api_key="sk-test",
        llm_base_url="https://ark.cn-beijing.volces.com/api/v3",
        llm_embed_dim=1024,
    )
    assert embed_text("缓存未命中", settings=settings) == [0.25] * 1024
    assert posted == [1]

    def broken(*_args, **_kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.cache.cache_get_json", broken)
    monkeypatch.setattr("app.cache.cache_set_json", broken)
    assert embed_text("缓存故障", settings=settings) == [0.25] * 1024
    assert posted == [1, 1]

    monkeypatch.setattr("app.cache.cache_get_json", lambda _key: [0.5] * 1024)
    assert embed_text("缓存命中", settings=settings) == [0.5] * 1024
    assert posted == [1, 1]


def test_embed_rejects_wrong_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"data": {"embedding": [0.1, 0.2], "object": "embedding"}}

    class Client:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

        def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("app.services.kb_embed.httpx.Client", Client)
    monkeypatch.setattr("app.cache.cache_get_json", lambda _key: None)
    monkeypatch.setattr("app.cache.cache_set_json", lambda *_args, **_kwargs: None)
    settings = Settings(
        llm_api_key="sk-test",
        llm_base_url="https://ark.cn-beijing.volces.com/api/v3",
        llm_embed_dim=1024,
    )
    with pytest.raises(EmbeddingError):
        embed_text("钢铁缺陷", settings=settings)


def test_corpus_is_only_kb_markdown_and_seed() -> None:
    rows = collect_corpus(ROOT / "docs" / "kb")
    names = {row["file_name"] for row in rows}
    assert "课题组学习路线安排.md" in names
    assert "steel_defect_detection_review.md" in names
    assert "steel_defect_segmentation_review.md" in names
    assert "写作与实验纪律" in names or any("纪律" in name for name in names)
    blob = " ".join(row["text"] for row in rows)
    assert "paper_literature" not in blob
    assert all(row["approved"] is True for row in rows)


def test_paper_card_keeps_doi_and_trigger_together() -> None:
    rows = collect_corpus(ROOT / "docs" / "kb")
    cards = [
        row
        for row in rows
        if row["block_type"] == "paper_card" and "12.1 ResNet" in row["section_path"]
    ]
    assert len(cards) == 1
    card = cards[0]
    assert "必读论文卡" in card["section_path"]
    assert "10.1109/cvpr.2016.90" in card["parent_text"]
    assert "推荐触发" in card["parent_text"]
    assert "短名" in card["parent_text"]


def test_table_row_and_reference_stay_atomic() -> None:
    rows = collect_corpus(ROOT / "docs" / "kb")
    picks = [
        row
        for row in rows
        if row["block_type"] == "table_row" and "不会 Python" in row["text"]
    ]
    assert len(picks) == 1
    assert picks[0]["parent_text"].count("不会 Python") == 1
    refs = [
        row
        for row in rows
        if row["file_name"] == "steel_defect_detection_review.md"
        and row["block_type"] == "reference"
        and "10.1109/tim.2019.2915404" in row["text"]
    ]
    assert len(refs) == 1
    assert refs[0]["parent_text"].lower().count("doi:") == 1
