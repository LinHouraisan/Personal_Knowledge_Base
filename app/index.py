import asyncio
import json
import math
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.models import IndexStats, NoteChunk, SearchHit
from app.vault import chunk_note, scan_vault


class Embedder(Protocol):
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def aembed_query(self, text: str) -> list[float]: ...


class Retriever(Protocol):
    async def load(self) -> None: ...

    async def retrieve(self, query: str, top_k: int) -> list[SearchHit]: ...

    async def rebuild(self) -> IndexStats: ...

    def ready(self) -> bool: ...


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


class JsonVectorIndex:
    def __init__(self, vault_path: Path, index_path: Path, embedder: Embedder):
        self.vault_path = vault_path
        self.index_path = index_path
        self.embedder = embedder
        self._records: list[tuple[NoteChunk, list[float]]] = []
        self._note_hashes: dict[str, str] = {}
        self._ready = False

    @property
    def note_count(self) -> int:
        return len(self._note_hashes)

    @property
    def chunk_count(self) -> int:
        return len(self._records)

    def ready(self) -> bool:
        return self._ready

    async def load(self) -> None:
        try:
            payload = await asyncio.to_thread(self._read_json)
            if payload.get("version") != 1:
                raise ValueError("unsupported index version")
            hashes = payload["note_hashes"]
            records = payload["records"]
            if not isinstance(hashes, dict) or not isinstance(records, list):
                raise ValueError("invalid index shape")
            loaded = [
                (NoteChunk.model_validate(item["chunk"]), [float(v) for v in item["vector"]])
                for item in records
            ]
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError):
            self._records = []
            self._note_hashes = {}
            self._ready = False
            return
        self._records = loaded
        self._note_hashes = {str(key): str(value) for key, value in hashes.items()}
        self._ready = True

    def _read_json(self) -> dict:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    async def rebuild(self) -> IndexStats:
        notes = await asyncio.to_thread(scan_vault, self.vault_path)
        current_hashes = {note.relative_path: note.content_hash for note in notes}
        unchanged = {
            path
            for path, digest in current_hashes.items()
            if self._note_hashes.get(path) == digest
        }
        kept = [
            record for record in self._records if record[0].relative_path in unchanged
        ]
        changed_notes = [note for note in notes if note.relative_path not in unchanged]
        changed_chunks = [chunk for note in changed_notes for chunk in chunk_note(note)]
        vectors = (
            await self.embedder.aembed_documents([chunk.text for chunk in changed_chunks])
            if changed_chunks
            else []
        )
        if len(vectors) != len(changed_chunks):
            raise ValueError("Embedding 返回数量与 Chunk 数量不一致")

        removed = len(set(self._note_hashes) - set(current_hashes))
        self._records = kept + list(zip(changed_chunks, vectors, strict=True))
        self._note_hashes = current_hashes
        self._ready = True
        await asyncio.to_thread(self._write_json)
        return IndexStats(
            notes=len(notes),
            chunks=len(self._records),
            embedded=len(changed_chunks),
            removed=removed,
        )

    def _write_json(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        payload = {
            "version": 1,
            "note_hashes": self._note_hashes,
            "records": [
                {"chunk": chunk.model_dump(), "vector": vector}
                for chunk, vector in self._records
            ],
        }
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.index_path)

    async def retrieve(self, query: str, top_k: int) -> list[SearchHit]:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k 必须在 1 到 20 之间")
        if not self._ready or not self._records:
            return []
        query_vector = await self.embedder.aembed_query(query)
        ranked = [
            SearchHit(chunk=chunk, score=_cosine(query_vector, vector))
            for chunk, vector in self._records
        ]
        ranked = [hit for hit in ranked if hit.score > 0]
        ranked.sort(key=lambda hit: (-hit.score, hit.chunk.relative_path, hit.chunk.id))
        return ranked[:top_k]
