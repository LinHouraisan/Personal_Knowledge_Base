from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.knowledge import KnowledgeService
from app.models import Source, VaultNote


class ReflectionRequest(BaseModel):
    mode: Literal["review", "plan"] = "review"
    scope: Literal["all", "learning", "project"] = "all"
    topic: str = Field(default="", max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    goal_id: str | None = Field(default=None, max_length=64)
    focus: Literal["all", "open"] = "all"

    @model_validator(mode="after")
    def check_range_and_goal(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        if self.mode == "plan" and not self.goal_id:
            raise ValueError("请先选择一个目标")
        return self


def note_date(note: VaultNote) -> date | None:
    value = note.frontmatter.get("date", note.frontmatter.get("created"))
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def note_info(note: VaultNote) -> dict:
    return {"id": note.id, "title": note.title, "path": note.relative_path,
            "date": note_date(note), "type": str(note.frontmatter.get("type", "reference")),
            "topic": str(note.frontmatter.get("topic", "")), "tags": note.tags}


def workspace(service: KnowledgeService) -> dict:
    notes = [note_info(note) for note in service.list_notes()]
    dates = [note["date"] for note in notes if note["type"] in ("learning", "project") and note["date"]]
    return {"notes": sorted(notes, key=lambda n: (str(n["date"] or ""), n["title"]), reverse=True),
            "goals": [note for note in notes if note["type"] == "goal"],
            "topics": sorted({note["topic"] for note in notes if note["topic"]}),
            "start_date": min(dates) if dates else None, "end_date": max(dates) if dates else None}


def source_for(service: KnowledgeService, note: VaultNote, text: str) -> dict:
    view = service.read_by_id(note.id)
    return Source(note_id=note.id, title=note.title, relative_path=note.relative_path,
                  excerpt=text, obsidian_uri=view.obsidian_uri).model_dump()


HEADINGS = {"已完成": "completed", "进行中": "progress", "未解决": "open", "待验证": "open", "下一步": "next", "计划": "next"}


def entries(note: VaultNote):
    # ponytail: demo reads explicit sections; arbitrary prose needs a separately evaluated model.
    section = None
    for line in note.content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            section = HEADINGS.get(line.lstrip("# "))
        elif section and line.startswith("- "):
            text = line[2:].strip()
            subject, separator, detail = text.partition("：")
            if text:
                yield section, subject if separator else text, detail if separator else text, text


def build_reflection(service: KnowledgeService, request: ReflectionRequest) -> dict:
    notes = service.list_notes()
    goal = None
    topic = request.topic.strip()
    if request.mode == "plan":
        goal_note = next((note for note in notes if note.id == request.goal_id and note.frontmatter.get("type") == "goal"), None)
        if goal_note is None:
            raise ValueError("目标不存在，请重新选择")
        goal = note_info(goal_note)
        if not goal["topic"] or (topic and topic != goal["topic"]):
            raise ValueError("目标和资料主题不一致")
        topic = goal["topic"]
        goal["source"] = source_for(service, goal_note, goal_note.content)

    selected, warnings = [], []
    for note in notes:
        kind = note.frontmatter.get("type")
        if kind not in ("learning", "project") or (request.scope != "all" and kind != request.scope):
            continue
        if topic and note.frontmatter.get("topic") != topic:
            continue
        recorded = note_date(note)
        if recorded is None:
            warnings.append(f"《{note.title}》无日期或日期无效，未计入本次复盘。")
            continue
        if request.start_date and recorded < request.start_date:
            continue
        if request.end_date and recorded > request.end_date:
            continue
        selected.append((recorded, note))
    selected.sort(key=lambda pair: (pair[0], pair[1].relative_path))

    states, next_steps, history = {}, {}, {}
    for recorded, note in selected:
        for state, subject, detail, text in entries(note):
            key = (str(note.frontmatter.get("topic", "")), subject)
            item = {"subject": subject, "text": text, "detail": detail, "date": recorded,
                    "source": source_for(service, note, text)}
            if state == "next":
                next_steps[key] = item
            else:
                states[key] = (state, item)
                history.setdefault(key, set()).add(note.id)
                if state == "completed":
                    next_steps.pop(key, None)

    sections = []
    for state, label in [("completed", "已完成"), ("progress", "正在推进"), ("open", "还没解决")]:
        if request.focus == "open" and state == "completed":
            continue
        items = [dict(item, occurrences=len(history[key])) for key, (current, item) in states.items() if current == state]
        items.sort(key=lambda item: (item["date"], item["subject"]), reverse=True)
        if items:
            sections.append({"key": state, "label": label, "items": items})

    actions = []
    for key, item in sorted(next_steps.items(), key=lambda pair: (pair[1]["date"], pair[0]), reverse=True):
        action, separator, done_when = item["detail"].partition("；完成标准：")
        actions.append({"subject": item["subject"], "text": action, "done_when": done_when if separator else "原笔记未写明，请补充完成标准。",
                        "reason": f"来自《{item['source']['title']}》中明确记录的下一步" + (f"，主题与目标《{goal['title']}》一致。" if goal else "。"),
                        "source": item["source"], "date": item["date"]})
    actions = actions[:3]
    status = "ready" if sections or actions else "no_evidence"
    warnings.append("按笔记中的明确记录整理，不代表已掌握某项能力；未记录的内容不作推断。")
    if request.mode == "plan":
        warnings.append("行动来自所选时间范围内的笔记，按最近记录排列，最多三项；这是待你确认的建议。")
    return {"status": status, "mode": request.mode, "method": "explicit_note_rules",
            "title": "下一步，先把这几件事做实" if request.mode == "plan" else "把积累看清楚，再往前走",
            "topic": topic, "notes_count": len(selected), "goal": goal,
            "period": {"start": request.start_date, "end": request.end_date},
            "sections": sections, "actions": actions, "warnings": warnings,
            "focus": request.focus}
