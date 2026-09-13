import asyncio
from pathlib import Path

from app.index import Retriever
from app.models import (
    IndexStats,
    KnowledgeStatus,
    NoteView,
    SearchHit,
    Source,
    VaultNote,
)
from app.obsidian import build_obsidian_uri
from app.vault import parse_note, safe_note_path, scan_vault


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
    ) -> Source:
        return Source(
            note_id=note.id,
            title=note.title,
            relative_path=note.relative_path,
            excerpt=(excerpt or note.content).replace("\n", " ")[:240],
            score=score,
            obsidian_uri=build_obsidian_uri(self.vault_name, note.relative_path),
        )

    async def search(self, query: str, top_k: int = 3) -> list[Source]:
        hits: list[SearchHit] = await self.retriever.retrieve(query, top_k)
        return [
            self._source(
                self._notes_by_id[hit.chunk.note_id],
                excerpt=hit.chunk.text,
                score=hit.score,
            )
            for hit in hits
            if hit.chunk.note_id in self._notes_by_id
        ]

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
