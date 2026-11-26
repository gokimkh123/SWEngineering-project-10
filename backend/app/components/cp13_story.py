"""CP-13 Story Generator (Analysis 계층, 여행기 작업 워커).

책임: 확정 사실만으로 LLM 여행기 생성, 문장별 장소 ID·필드 수신, 각주 생성, AI 작성 표시, 문단 다시 쓰기
(FR-09, FR-10, AIR-05, AIR-06, UC-06, UC-07). 사실 대조는 CP-14를 부른다 (UC-09 포함 관계).
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.adapters.cp19_ai_gateway import STORY_PART_VISITS, STORY_PROMPT, WEEKDAYS, AIError, AIGateway, template_title
from app.components import cp14_fact_checker as fc
from app.components.cp05_route import load_stops, route_summary
from app.components.cp16_place_cache import PlaceCache
from app.models import Footnote, Story, Trip, VisitStatus

log = logging.getLogger("chalkak.story")
STYLES = {"blog": "블로그형", "diary": "일기형", "brief": "간결형"}
FIELD_LABELS = {"overview": "개요", "address": "주소", "usetime": "운영시간", "type": "유형", "name": "이름"}
AI_LABEL = "AI가 확정된 방문지와 공식 데이터로 작성한 글이에요. 사실 문장마다 출처를 달았어요."
# 템플릿 문단(LLM 실패 시 공식 데이터 문장)에는 'AI 작성'이라고 쓰지 않는다 (D-06)
TEMPLATE_LABEL = "AI 응답을 쓰지 못해 공식 데이터 문장으로 자동 작성한 글이에요. 사실 문장마다 출처를 달았어요."
MIXED_LABEL = ("AI가 확정된 방문지와 공식 데이터로 작성한 글이에요. {days}일차는 AI 응답을 쓰지 못해 공식 데이터 문장으로 "
               "자동 작성했어요. 사실 문장마다 출처를 달았어요.")
# LLM 입력에 넣는 필드 길이 상한: 실제 TourAPI 개요는 수백 자라 그대로 넣으면 문맥 한도를 넘는다 (대조는 원문 전체로 한다)
LLM_FIELD_CHARS = {"overview": 220, "address": 80, "usetime": 80}


def _brief_facts(f: dict) -> dict:
    out = {}
    for k, v in f.items():
        lim = LLM_FIELD_CHARS.get(k)
        if lim and isinstance(v, str) and len(v) > lim:
            cut = v[:lim]
            dot = cut.rfind(". ")
            v = cut[:dot + 1] if dot > lim // 2 else cut
        out[k] = v
    return out


def _template_days(body: list[dict]) -> list[int]:
    return sorted({p["day"] for p in body if p.get("source") == "template"})


def ai_label(body: list[dict]) -> str:
    """여행기 아래 작성 방식 문구: 모두 LLM · 모두 템플릿 · 일부 날짜만 템플릿."""
    tpl = _template_days(body)
    if not tpl:
        return AI_LABEL
    if len(tpl) == len({p["day"] for p in body}):
        return TEMPLATE_LABEL
    return MIXED_LABEL.format(days="·".join(map(str, tpl)))


def model_label(body: list[dict], model: str) -> str:
    """작성 모델 표시. 템플릿 문단이 있으면 '템플릿'을 넣는다 (측정 스크립트도 이 낱말로 구분)."""
    tpl = _template_days(body)
    if not tpl:
        return model
    if len(tpl) == len({p["day"] for p in body}):
        return f"템플릿 (LLM {model} 응답을 쓰지 못해 대체)"
    return f"{model} + 템플릿 ({'·'.join(map(str, tpl))}일차)"


def _plain(text: str) -> str:
    """LLM이 섞어 쓰는 마크다운 기호(굵게·제목·코드)를 지우고, 숫자와 단위 사이 띄어쓰기('1950 년대')를 붙인다."""
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"(\d)\s+(년|월|일|시|분|층|곳|번|개|명|km|m)(?![A-Za-z])", r"\1\2", text)
    return re.sub(r"^\s*(#+|[-*•]\s)\s*", "", text).strip()


def _squash(text: str) -> str:
    """문단 비교용: 마크다운·공백을 지운 글자만."""
    return re.sub(r"\s+", "", _plain(text))


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
        spans = []
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
                entry.update(place_id=rec.place_id, name=rec.name, type=rec.type, facts=_brief_facts(f))
            spans.append((entry["place_id"], v.day, v.start_at, v.end_at))
            payload_visits.append(entry)
        known = self.cache.known_names(db)
        for pid, f in facts.items():
            if f.get("name"):
                known[f["name"]] = pid
        return {
            "visits": payload_visits, "facts": facts, "sources": sources, "known": known,
            "confirmed": set(facts), "stops": load_stops(db, visits, self.cache),
            "trip": fc.TripRecord.from_visits(spans),
        }

    # ------------------------------------------------------------ 생성
    def generate(self, db: Session, story: Story) -> Story:
        """날짜별로(하루 방문지가 많으면 5곳씩) LLM에 나눠 쓰게 하고, 실패한 날만 템플릿 문단으로 바꾼다 (D-04).

        한 번에 여행 전체를 쓰게 하면 방문지 14곳 여행에서 입력+출력이 Ollama 문맥 4096토큰을 넘어 응답이 잘렸다.
        """
        trip = story.trip
        ctx = self._context(db, trip)
        info = self.gateway.info()
        model, fake = info["llm_model"], info["llm_provider"] == "fake"
        days: dict[int, list[dict]] = {}
        for v in ctx["visits"]:
            days.setdefault(v["day"], []).append(v)
        first_day = min(days)
        base = {"style": story.style, "trip": {"start_date": trip.start_date, "end_date": trip.end_date}}
        jobs = []
        for d in sorted(days):
            parts = [days[d][i:i + STORY_PART_VISITS] for i in range(0, len(days[d]), STORY_PART_VISITS)]
            for ci, part in enumerate(parts):
                jobs.append((d, ci, base | {"day": d, "visits": part, "first": d == first_day and ci == 0,
                                            "last": ci == len(parts) - 1}))

        def run(job):
            d, ci, payload = job
            try:
                got = self._parse(self.gateway.llm_story_part(payload), story_level=False)
                if not got["sentences"]:
                    raise AIError("빈 문단")
                return d, ci, got["sentences"], None
            except AIError as e:
                if fake:
                    raise
                return d, ci, None, str(e)

        with ThreadPoolExecutor(max_workers=2) as pool:  # Ollama 슬롯 2개를 함께 쓴다
            results = list(pool.map(run, jobs))
        failed: dict[int, str] = {}
        paragraphs = []
        for d in sorted(days):
            mine = sorted((r for r in results if r[0] == d), key=lambda r: r[1])
            bad = next((r[3] for r in mine if r[2] is None), None)
            if bad is not None:
                failed[d] = bad
                paragraphs.append(self._template_day(story.style, days[d], d == first_day, d))
            else:
                paragraphs.append({"day": d, "source": "llm", "sentences": [x for r in mine for x in r[2]]})
        self._assemble(db, story, paragraphs, ctx)

        # 사실 대조 뒤 문장이 남지 않았거나 뺀 문장이 더 많은 날, 또는 여행 전체에 출처 문장이 없으면 그 날들만 템플릿으로
        removed_by_day: dict[int, int] = {}
        for r in story.meta.get("removed", []):
            removed_by_day[r.get("day")] = removed_by_day.get(r.get("day"), 0) + 1
        weak = {p["day"]: "근거 있는 문장이 부족해요" for p in story.body if p["source"] == "llm"
                and (not p["sentences"] or removed_by_day.get(p["day"], 0) > len(p["sentences"]))}
        if not weak and ctx["facts"] and not any(s["footnotes"] for p in story.body for s in p["sentences"]):
            weak = {p["day"]: "출처 있는 사실 문장이 없어요" for p in story.body if p["source"] == "llm"}
        if weak and not fake:
            failed.update(weak)
            paragraphs = [self._template_day(story.style, days[p["day"]], p["day"] == first_day, p["day"])
                          if p["day"] in weak else p for p in paragraphs]
            self._assemble(db, story, paragraphs, ctx)
        for d, why in sorted(failed.items()):
            log.warning("LLM 여행기 %d일차 실패 → 템플릿 문단으로 대체: %s", d, why)

        story.title = self._title(base | {"visits": ctx["visits"]}, fake)
        story.route_summary = route_summary(ctx["stops"])
        story.prompt_version = STORY_PROMPT
        story.model = model_label(story.body, model)
        story.status = "ready"
        story.error = None
        return story

    def _template_day(self, style: str, visits: list[dict], first: bool, day: int) -> dict:
        data = self._parse(self.gateway.template_paragraph({"style": style, "visits": visits, "first_day": first}, 0), story_level=False)
        return {"day": day, "source": "template", "sentences": data["sentences"]}

    def _title(self, payload: dict, fake: bool) -> str:
        """LLM 제목. 실패하거나 한자 등이 섞이면 공식 데이터로 만든 제목."""
        try:
            t = _plain(str(json.loads(self.gateway.llm_title(payload)).get("title") or ""))
            if t and not fc.foreign_script(t):
                return t[:200]
        except (AIError, ValueError, TypeError, AttributeError):
            if fake:
                raise
        return template_title(payload)[:200]

    @staticmethod
    def _paragraphs(data: dict) -> list[dict]:
        """날짜별 문단 하나(D2 화면·문단 다시 쓰기가 날짜 단위). LLM이 장소마다 문단을 나누면 같은 날짜끼리 합친다."""
        out: list[dict] = []
        for i, p in enumerate(data["paragraphs"]):
            try:
                day = int(p.get("day") or i + 1)
            except (TypeError, ValueError):
                day = i + 1
            if out and out[-1]["day"] == day:
                out[-1]["sentences"] = out[-1]["sentences"] + list(p["sentences"])
            else:
                out.append({"day": day, "sentences": list(p["sentences"])})
        return out

    def rewrite_paragraph(self, db: Session, story: Story, paragraph_id: str) -> Story:
        """문단 다시 쓰기 (FR-10). 실패하면 기존 문단을 그대로 둔다 (UC-07 2a)."""
        ctx = self._context(db, story.trip)
        body = story.body
        idx = next((i for i, p in enumerate(body) if p["id"] == paragraph_id), None)
        if idx is None:
            raise KeyError("문단을 찾을 수 없어요")
        day = body[idx]["day"]
        variant = int(body[idx].get("variant", 0)) + 1
        first = day == min(p["day"] for p in body)
        payload = {"style": story.style, "day": day, "visits": [v for v in ctx["visits"] if v["day"] == day],
                   "first_day": first, "first": first, "last": True, "previous": [s["text"] for s in body[idx]["sentences"]]}
        before = _squash(" ".join(payload["previous"]))
        data = None
        for v in (variant, variant + 1):  # 같은 문단이 그대로 나오면 시드를 바꿔 한 번 더
            try:
                got = self._parse(self.gateway.llm_rewrite_paragraph(payload, v), story_level=False)
                if not got["sentences"]:
                    raise AIError("빈 문단")
            except AIError:
                if self.gateway.info()["llm_provider"] == "fake":
                    raise
                break
            if _squash(" ".join(x.get("text", "") for x in got["sentences"])) != before:
                data, variant = got, v
                break
        source = "llm"
        if data is None:  # AI 오류이거나 같은 문단만 나오면 공식 데이터 문장으로 만든 문단 (UC-07 2a)
            data = self._parse(self.gateway.template_paragraph(payload, variant), story_level=False)
            source = "template"
        default_src = "template" if (story.model or "").startswith("템플릿") else "llm"  # 작성 방식 기록 전에 만든 여행기
        paragraphs = [dict(p) for p in body]
        paragraphs[idx] = {"day": day, "sentences": data["sentences"], "variant": variant, "source": source}
        # 다른 문단은 원문 그대로 다시 검사·각주 번호를 매긴다
        for i, p in enumerate(paragraphs):
            if i != idx:
                paragraphs[i] = {"day": p["day"], "variant": p.get("variant", 0), "source": p.get("source", default_src),
                                 "sentences": [{k: s[k] for k in ("text", "place_ids", "fields", "is_fact")} | {"edited": s.get("edited", False)}
                                               for s in p["sentences"]]}
        self._assemble(db, story, paragraphs, ctx)
        story.model = model_label(story.body, self.gateway.info()["llm_model"])
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
            res = fc.check_edited_sentence(text, ctx["facts"], ctx["confirmed"], ctx["known"], s.get("place_ids"), trip=ctx.get("trip"))
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
        bad = AIError("여행기 응답 형식이 올바르지 않아요")
        if not isinstance(data, dict):
            raise bad
        if story_level:
            if not isinstance(data.get("paragraphs"), list) or any(not isinstance(p, dict) for p in data["paragraphs"]):
                raise bad
            sentences_lists = [p.get("sentences") for p in data["paragraphs"]]
        else:
            sentences_lists = [data.get("sentences")]
        if any(not isinstance(sl, list) or any(not isinstance(s, dict) for s in sl) for sl in sentences_lists):
            raise bad
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
                if not s.get("edited"):
                    text = _plain(text)
                if not text:
                    continue
                pids = [x for x in s.get("place_ids", []) if isinstance(x, str)]
                flds = [x for x in s.get("fields", []) if isinstance(x, str)]
                if s.get("edited"):
                    res = fc.check_edited_sentence(text, facts, confirmed, known, pids, trip=ctx.get("trip"))
                    res_is_fact = s.get("is_fact", False)
                else:
                    res = fc.check_generated_sentence(text, pids, flds, bool(s.get("is_fact")), facts, confirmed, known,
                                                      trip=ctx.get("trip"), day=p["day"])
                    res_is_fact = res.is_fact
                    if not res.ok:  # AIR-06: 근거 없는 사실 문장·확정되지 않은 장소 문장·한자·맞지 않는 시간대 표현은 제거
                        removed.append({"text": text, "reasons": [w.message for w in res.warnings], "day": p["day"]})
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
            body.append({"id": f"p{pi}", "day": p["day"], "variant": p.get("variant", 0), "source": p.get("source", "llm"),
                         "sentences": out_sents})
        story.body = body
        story.footnotes.clear()
        db.flush()
        for (pid, f), num in sorted(foot_index.items(), key=lambda x: x[1]):
            src, updated = sources.get(pid, ("출처 미상", None))
            name = facts[pid].get("name", pid)
            story.footnotes.append(Footnote(num=num, place_id=pid, field=f, source_name=src, updated_at=updated,
                                            label=f"{src} · {name} {FIELD_LABELS.get(f, f)}"))
        story.meta = {"removed": removed, "ai_label": ai_label(body),
                      "places": [{"place_id": pid, "name": f.get("name")} for pid, f in facts.items()]}
