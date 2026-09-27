import asyncio
import re
import unicodedata
from pathlib import Path

from app.models import IndexStats, NoteChunk, SearchHit
from app.vault import chunk_note, scan_vault


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def query_terms(text: str) -> set[str]:
    normalized = normalize_text(text).strip()
    terms = set(re.findall(r"[a-z0-9]+(?:[+/#._-]+[a-z0-9]+)*[+#]*", normalized))
    for run in re.findall(r"[\u3400-\u9fff]{2,}", normalized):
        terms.add(run)
        terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return terms


def term_pattern(term: str) -> re.Pattern:
    normalized = normalize_text(term)
    pattern = re.escape(normalized)
    if re.search(r"[a-z0-9]", normalized):
        pattern = r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])"
    return re.compile(pattern)


def contains_term(text: str, term: str) -> bool:
    return bool(term and term_pattern(term).search(normalize_text(text)))


def lexical_score(query: str, chunk: NoteChunk) -> float:
    terms = query_terms(query)
    if not terms:
        return 0.0
    fields = [(4, chunk.title), (3, " ".join(chunk.tags)), (2, chunk.relative_path), (1, chunk.text)]
    return sum(weight * sum(contains_term(text, term) for term in terms) / len(terms)
               for weight, text in fields)


class LexicalRetriever:
    mode = "lexical"

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self._chunks: list[NoteChunk] = []
        self._paths: set[str] = set()
        self._ready = False

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def ready(self) -> bool:
        return self._ready

    async def load(self) -> None:
        await self.rebuild()

    async def rebuild(self) -> IndexStats:
        notes = await asyncio.to_thread(scan_vault, self.vault_path)
        paths = {note.relative_path for note in notes}
        removed = len(self._paths - paths)
        self._chunks = list({chunk.id: chunk for note in notes for chunk in chunk_note(note)}.values())
        self._paths = paths
        self._ready = True
        return IndexStats(notes=len(notes), chunks=len(self._chunks), embedded=0, removed=removed)

    async def retrieve(self, query: str, top_k: int) -> list[SearchHit]:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k 必须在 1 到 20 之间")
        hits = [SearchHit(chunk=chunk, score=lexical_score(query, chunk)) for chunk in self._chunks]
        hits = [hit for hit in hits if hit.score > 0]
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.relative_path, hit.chunk.id))
        return hits[:top_k]


def find_terms(text: str, terms: list[str]) -> list[tuple[int, int, str]]:
    """Match normalized aliases but return original character offsets and longest aliases."""
    normalized_parts, positions = [], []
    for index, character in enumerate(text):
        part = normalize_text(character)
        normalized_parts.append(part)
        positions.extend([index] * len(part))
    normalized = "".join(normalized_parts)
    matches = []
    for term in sorted(set(terms), key=lambda value: (-len(value), value)):
        if not term:
            continue
        for match in term_pattern(term).finditer(normalized):
            matches.append((positions[match.start()], positions[match.end() - 1] + 1, normalize_text(term)))
    matches.sort(key=lambda match: (match[0], -(match[1] - match[0]), match[2]))
    result = []
    end = -1
    for match in matches:
        if match[0] >= end:
            result.append(match)
            end = match[1]
    return result
