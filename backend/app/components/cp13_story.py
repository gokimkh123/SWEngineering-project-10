"""CP-13 Story Generator (Analysis 계층, 여행기 작업 워커).

책임: 확정 사실만으로 LLM 여행기 생성, 문장별 장소 ID·필드 수신, 각주 생성, AI 작성 표시, 문단 다시 쓰기
(FR-09, FR-10, AIR-05, AIR-06, UC-06, UC-07). 사실 대조는 CP-14를 부른다 (UC-09 포함 관계).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.adapters.cp19_ai_gateway import STORY_PROMPT, WEEKDAYS, AIError, AIGateway
from app.components import cp14_fact_checker as fc
from app.components.cp05_route import load_stops, route_summary
from app.components.cp16_place_cache import PlaceCache
from app.models import Footnote, Story, Trip, VisitStatus

STYLES = {"blog": "블로그형", "diary": "일기형", "brief": "간결형"}
FIELD_LABELS = {"overview": "개요", "address": "주소", "usetime": "운영시간", "type": "유형", "name": "이름"}
AI_LABEL = "AI가 확정된 방문지와 공식 데이터로 작성한 글이에요. 사실 문장마다 출처를 달았어요."


class StoryNotReady(RuntimeError):
    """확정되지 않은 방문지가 남아 있음 (UC-06 사전조건)."""


class StoryGenerator:
    def __init__(self, gateway: AIGateway, cache: PlaceCache) -> None:
        self.gateway = gateway
        self.cache = cache

    # ------------------------------------------------------------ 입력 구성 (AIR-05)
    def _context(self, db: Session, trip: Trip) -> dict:
        visits = sorted(trip.visits, key=lambda v: v.order)
        if not visits:
            raise StoryNotReady("방문지가 없어요")
        if any(not VisitStatus(v.status).is_final for v in visits):
            raise StoryNotReady("확인이 필요한 방문지가 남아 있어요")
        facts: dict[str, dict[str, str]] = {}
        sources: dict[str, tuple[str, str | None]] = {}
        payload_visits = []
        for v in visits:
            rec = self.cache.resolve(db, v.place_id, v.center_lat, v.center_lng) if v.place_id else None
            entry = {
                "order": v.order, "day": v.day, "date": v.date, "weekday": WEEKDAYS[v.start_at.weekday()],
                "time_range": f"{v.start_at:%H:%M}~{v.end_at:%H:%M}", "start_hour": v.start_at.hour,
                "place_id": None, "name": None, "type": None, "facts": {},
            }
            if rec is not None and v.status != VisitStatus.OTHER_PLACE.value:
                if rec.source == "kakao":
                    # 카카오 로컬 결과는 장소 ID·URL 외 저장 금지 → 여행기(저장됨)에는 장소 이름만 쓴다
                    f = {"name": rec.name} if rec.name else {}
                else:
                    f = {k: val for k, val in {"name": rec.name, "type": rec.type, "address": rec.address,
                                                "overview": rec.overview, "usetime": rec.usetime}.items() if val}
                facts[rec.place_id] = f
                sources[rec.place_id] = (rec.source_name, rec.updated_at)
                entry.update(place_id=rec.place_id, name=rec.name, type=rec.type, facts=f)
            payload_visits.append(entry)
        known = self.cache.known_names(db)
        for pid, f in facts.items():
            if f.get("name"):
                known[f["name"]] = pid
        return {
            "visits": payload_visits, "facts": facts, "sources": sources, "known": known,
            "confirmed": set(facts), "stops": load_stops(db, visits, self.cache),
        }

    # ------------------------------------------------------------ 생성
    def generate(self, db: Session, story: Story) -> Story:
        trip = story.trip
        ctx = self._context(db, trip)
        payload = {"style": story.style, "trip": {"start_date": trip.start_date, "end_date": trip.end_date},
                   "visits": ctx["visits"]}
        raw = self.gateway.llm_story(payload)
        data = self._parse(raw, story_level=True)
        paragraphs = [{"day": int(p.get("day") or i + 1), "sentences": p["sentences"]} for i, p in enumerate(data["paragraphs"])]
        story.title = (data.get("title") or "부산 여행기").strip()[:200]
        story.route_summary = route_summary(ctx["stops"])
        story.prompt_version = STORY_PROMPT
        story.model = self.gateway.info()["llm_model"]
        self._assemble(db, story, paragraphs, ctx)
        story.status = "ready"
        story.error = None
        return story

    def rewrite_paragraph(self, db: Session, story: Story, paragraph_id: str) -> Story:
        """문단 다시 쓰기 (FR-10). 실패하면 기존 문단을 그대로 둔다 (UC-07 2a)."""
        ctx = self._context(db, story.trip)
        body = story.body
        idx = next((i for i, p in enumerate(body) if p["id"] == paragraph_id), None)
        if idx is None:
            raise KeyError("문단을 찾을 수 없어요")
        day = body[idx]["day"]
        variant = int(body[idx].get("variant", 0)) + 1
        payload = {"style": story.style, "visits": [v for v in ctx["visits"] if v["day"] == day],
                   "first_day": day == min(p["day"] for p in body), "previous": [s["text"] for s in body[idx]["sentences"]]}
        raw = self.gateway.llm_rewrite_paragraph(payload, variant)
        data = self._parse(raw, story_level=False)
        paragraphs = [dict(p) for p in body]
        paragraphs[idx] = {"day": day, "sentences": data["sentences"], "variant": variant}
        # 다른 문단은 원문 그대로 다시 검사·각주 번호를 매긴다
        for i, p in enumerate(paragraphs):
            if i != idx:
                paragraphs[i] = {"day": p["day"], "variant": p.get("variant", 0),
                                 "sentences": [{k: s[k] for k in ("text", "place_ids", "fields", "is_fact")} | {"edited": s.get("edited", False)}
                                               for s in p["sentences"]]}
        self._assemble(db, story, paragraphs, ctx)
        return story

    # ------------------------------------------------------------ 편집 대조 (FR-10, UC-09)
    def apply_edits(self, db: Session, story: Story, edits: list[dict]) -> Story:
        ctx = self._context(db, story.trip)
        body = [dict(p, sentences=[dict(s) for s in p["sentences"]]) for p in story.body]
        by_id = {s["id"]: s for p in body for s in p["sentences"]}
        for e in edits:
            s = by_id.get(e.get("sentence_id"))
            if s is None:
                continue
            text = (e.get("text") or "").strip()
            if not text:
                s["deleted"] = True
                continue
            res = fc.check_edited_sentence(text, ctx["facts"], ctx["confirmed"], ctx["known"], s.get("place_ids"))
            s.update(text=text, edited=True, warnings=[w.to_dict() for w in res.warnings])
        for p in body:
            p["sentences"] = [s for s in p["sentences"] if not s.get("deleted")]
        story.body = body
        return story

    # ------------------------------------------------------------ 내부
    @staticmethod
    def _parse(raw: str, story_level: bool) -> dict:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as e:
            raise AIError("여행기 응답 형식이 올바르지 않아요") from e
        sentences_lists = [p.get("sentences") for p in data.get("paragraphs", [])] if story_level else [data.get("sentences")]
        if (story_level and not isinstance(data.get("paragraphs"), list)) or any(not isinstance(s, list) for s in sentences_lists):
            raise AIError("여행기 응답 형식이 올바르지 않아요")
        for sl in sentences_lists:
            for s in sl:
                s.setdefault("place_ids", [])
                s.setdefault("fields", [])
                s.setdefault("is_fact", False)
        return data

    def _assemble(self, db: Session, story: Story, paragraphs: list[dict], ctx: dict) -> None:
        """사실 대조(CP-14) → 근거 없는 사실 문장 제거 → 각주 번호 부여 (NFR-03: 사실 문장 출처 100%)."""
        facts, confirmed, known, sources = ctx["facts"], ctx["confirmed"], ctx["known"], ctx["sources"]
        foot_index: dict[tuple[str, str], int] = {}
        body, removed = [], []
        for pi, p in enumerate(paragraphs):
            out_sents = []
            for s in p["sentences"]:
                text = (s.get("text") or "").strip()
                if not text:
                    continue
                pids = [x for x in s.get("place_ids", []) if isinstance(x, str)]
                flds = [x for x in s.get("fields", []) if isinstance(x, str)]
                if s.get("edited"):
                    res = fc.check_edited_sentence(text, facts, confirmed, known, pids)
                    res_is_fact = s.get("is_fact", False)
                else:
                    res = fc.check_generated_sentence(text, pids, flds, bool(s.get("is_fact")), facts, confirmed, known)
                    res_is_fact = res.is_fact
                    if not res.ok:  # AIR-06: 근거 없는 사실 문장·확정되지 않은 장소 문장은 제거
                        removed.append({"text": text, "reasons": [w.message for w in res.warnings]})
                        continue
                notes = []
                if res_is_fact:
                    for pid in pids:
                        for f in flds:
                            if pid in facts and f in facts[pid]:
                                key = (pid, f)
                                if key not in foot_index:
                                    foot_index[key] = len(foot_index) + 1
                                notes.append(foot_index[key])
                out_sents.append({
                    "id": f"p{pi}s{len(out_sents)}", "text": text, "place_ids": pids, "fields": flds,
                    "is_fact": res_is_fact, "footnotes": sorted(set(notes)), "edited": bool(s.get("edited")),
                    "warnings": [w.to_dict() for w in res.warnings] if s.get("edited") else [],
                })
            body.append({"id": f"p{pi}", "day": p["day"], "variant": p.get("variant", 0), "sentences": out_sents})
        story.body = body
        story.footnotes.clear()
        db.flush()
        for (pid, f), num in sorted(foot_index.items(), key=lambda x: x[1]):
            src, updated = sources.get(pid, ("출처 미상", None))
            name = facts[pid].get("name", pid)
            story.footnotes.append(Footnote(num=num, place_id=pid, field=f, source_name=src, updated_at=updated,
                                            label=f"{src} · {name} {FIELD_LABELS.get(f, f)}"))
        story.meta = {"removed": removed, "ai_label": AI_LABEL,
                      "places": [{"place_id": pid, "name": f.get("name")} for pid, f in facts.items()]}
