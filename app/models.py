from typing import Literal

from pydantic import BaseModel, Field


class VaultNote(BaseModel):
    id: str
    title: str
    relative_path: str
    content: str
    frontmatter: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    modified_ns: int
    content_hash: str


class NoteChunk(BaseModel):
    id: str
    note_id: str
    title: str
    relative_path: str
    heading: str | None = None
    text: str
    tags: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    chunk: NoteChunk
    score: float


class IndexStats(BaseModel):
    notes: int
    chunks: int
    embedded: int
    removed: int


class Source(BaseModel):
    note_id: str
    title: str
    relative_path: str
    excerpt: str
    score: float | None = None
    obsidian_uri: str


class NoteView(BaseModel):
    note_id: str
    title: str
    relative_path: str
    content: str
    tags: list[str]
    links: list[str]
    obsidian_uri: str


class KnowledgeStatus(BaseModel):
    vault_name: str
    index_ready: bool
    notes: int
    chunks: int


class AgentAnswer(BaseModel):
    status: Literal["answered", "no_evidence"]
    answer: str
    sources: list[Source]

