import asyncio
import re
from pathlib import Path

from app.index import Retriever
from app.lexical import contains_term, find_terms
from app.models import (
    IndexStats,
    KnowledgeStatus,
    NoteView,
    SearchHit,
    Source,
    VaultNote,
)
from app.obsidian import build_obsidian_uri
from app.vault import chunk_note, parse_note, safe_note_path, scan_vault


def _names(note: VaultNote) -> set[str]:
    names = {note.title, Path(note.relative_path).stem, note.relative_path.removesuffix(".md")}
    aliases = note.frontmatter.get("aliases", [])
    if isinstance(aliases, str):
        names.add(aliases)
    elif isinstance(aliases, list):
        names.update(str(alias) for alias in aliases)
    return {name.replace("\\", "/").strip() for name in names if name.strip()}


class KnowledgeService:
    def __init__(self, vault_path: Path, vault_name: str, retriever: Retriever):
        self.vault_path = vault_path
        self.vault_name = vault_name
        self.retriever = retriever
        self._notes_by_path: dict[str, VaultNote] = {}
        self._notes_by_id: dict[str, VaultNote] = {}

    async def load(self) -> None:
        await self.retriever.load()
        await self._refresh_notes()

    async def rebuild(self) -> IndexStats:
        stats = await self.retriever.rebuild()
        await self._refresh_notes()
        return stats

    async def _refresh_notes(self) -> None:
        notes = await asyncio.to_thread(scan_vault, self.vault_path)
        self._notes_by_path = {note.relative_path: note for note in notes}
        self._notes_by_id = {note.id: note for note in notes}

    def status(self) -> KnowledgeStatus:
        return KnowledgeStatus(
            vault_name=self.vault_name,
            index_ready=self.retriever.ready(),
            notes=len(self._notes_by_id),
            chunks=int(getattr(self.retriever, "chunk_count", 0)),
        )

    def _source(
        self,
        note: VaultNote,
        excerpt: str | None = None,
        score: float | None = None,
        chunk_id: str | None = None,
        heading: str | None = None,
    ) -> Source:
        return Source(
            note_id=note.id,
            title=note.title,
            relative_path=note.relative_path,
            excerpt=(excerpt or note.content).replace("\n", " ")[:240],
            score=score,
            chunk_id=chunk_id,
            heading=heading,
            obsidian_uri=build_obsidian_uri(self.vault_name, note.relative_path),
        )

    async def search(self, query: str, top_k: int = 3) -> list[Source]:
        hits: list[SearchHit] = await self.retriever.retrieve(query, top_k)
        return [
            self._source(
                self._notes_by_id[hit.chunk.note_id],
                excerpt=hit.chunk.text,
                score=None if getattr(self.retriever, 'mode', None) == 'lexical' else hit.score,
                chunk_id=hit.chunk.id,
                heading=hit.chunk.heading,
            )
            for hit in hits
            if hit.chunk.note_id in self._notes_by_id
        ]

    def keyword_sources(self, terms: list[str], top_k: int = 3) -> list[Source]:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k 必须在 1 到 20 之间")
        ranked = []
        for note in self._notes_by_id.values():
            # A heading or tag alone is not body evidence.
            excluded = [(m.start(), m.end()) for m in re.finditer(
                r"(?m)^\s{0,3}#{1,6}[^\S\n]+[^\n]*|(?<![\w/])#[\w/-]+", note.content)]
            matches = [match for match in find_terms(note.content, terms)
                       if not any(start <= match[0] < end for start, end in excluded)]
            if not matches:
                continue
            position = matches[0][0]
            start = max(0, position - 80)
            excerpt = note.content[start:start + 240]
            chunk = self._chunk_at(note, position)
            source = self._source(note, chunk_id=chunk.id if chunk else None,
                                  heading=chunk.heading if chunk else None)
            source.excerpt = excerpt
            priority = (sum(contains_term(note.title, term) for term in terms),
                        sum(contains_term(" ".join(note.tags), term) for term in terms))
            ranked.append((priority, note.relative_path, source))
        ranked.sort(key=lambda item: (-item[0][0], -item[0][1], item[1]))
        return [source for _, _, source in ranked[:top_k]]

    @staticmethod
    def _chunk_at(note: VaultNote, position: int):
        # Mirror only the existing whitespace compaction, preserving original offsets.
        positions = []
        for match in re.finditer(r"[^\n]+", note.content):
            line = match.group()
            left = len(line) - len(line.lstrip())
            right = len(line.rstrip())
            positions.extend(range(match.start() + left, match.start() + right))
        compact = "".join(note.content[index] for index in positions)
        cursor = 0
        for chunk in chunk_note(note):
            start = compact.find(chunk.text, cursor)
            if start < 0:
                continue
            end = start + len(chunk.text)
            if positions[start] <= position <= positions[end - 1]:
                return chunk
            cursor = end
        return None

    def read(self, relative_path: str) -> NoteView:
        path = safe_note_path(self.vault_path, relative_path)
        note = self._notes_by_path.get(path.relative_to(self.vault_path.resolve()).as_posix())
        if note is None:
            raise KeyError(relative_path)
        return self._view(note)

    def read_by_id(self, note_id: str) -> NoteView:
        note = self._notes_by_id.get(note_id)
        if note is None:
            raise KeyError(note_id)
        return self._view(note)

    def _view(self, note: VaultNote) -> NoteView:
        return NoteView(
            note_id=note.id,
            title=note.title,
            relative_path=note.relative_path,
            content=note.content,
            tags=note.tags,
            links=note.links,
            obsidian_uri=build_obsidian_uri(self.vault_name, note.relative_path),
        )

    def related(self, relative_path: str) -> list[Source]:
        current = self.read(relative_path)
        current_note = self._notes_by_id[current.note_id]
        current_names = _names(current_note)
        direct_targets = {link.replace("\\", "/") for link in current_note.links}
        direct: list[VaultNote] = []
        tag_matches: list[VaultNote] = []
        for candidate in self._notes_by_id.values():
            if candidate.id == current_note.id:
                continue
            candidate_names = _names(candidate)
            candidate_targets = {link.replace("\\", "/") for link in candidate.links}
            linked = bool(direct_targets & candidate_names or candidate_targets & current_names)
            if linked:
                direct.append(candidate)
            elif set(current_note.tags) & set(candidate.tags):
                tag_matches.append(candidate)
        ordered = sorted(direct, key=lambda note: note.relative_path) + sorted(
            tag_matches, key=lambda note: note.relative_path
        )
        return [self._source(note) for note in ordered[:10]]
