"""CP-19 AI Gateway (External 계층).

책임: VLM(서버 안 오픈소스 모델)·LLM(외부 API) 호출, 프롬프트 버전 관리, JSON 스키마 강제, 인물 미분석 지시.
사진은 VLM에만 전달하고 LLM에는 보내지 않는다 (NFR-04, AD-08). 제공 인터페이스: IF-19 Vision/TextModel.

공급자 (환경변수로 선택, QA-05: 모델을 바꿔도 다른 컴포넌트는 수정하지 않는다)
- VLM_PROVIDER=fake   : 모의 VLM. 사진 색 분포로 장면(바다·야경·음식·녹지·골목·거리)을 추정하고 후보 유형·거리와 맞춰 본다.
                        실제 모델이 아니므로 정확도 평가용이 아니라 흐름 시연·테스트용이다.
                        실제 사진 시연 세트(var/demo_photos/vlm_replay.json)가 있으면 그 사진에는 미리 정한 응답을 쓴다.
- VLM_PROVIDER=ollama : Ollama로 실행하는 오픈소스 멀티모달 모델 (예: qwen2.5vl:7b), JSON 스키마 강제
- LLM_PROVIDER=fake   : 모의 LLM. 공식 데이터 필드를 그대로 써서 템플릿 문장을 만든다
- LLM_PROVIDER=anthropic : Claude Haiku (구조화 출력)
- LLM_PROVIDER=gemini    : Gemini 무료 플랜 (JSON 응답)
"""
from __future__ import annotations

import base64
import io
import json
import math
import threading
import time
from collections import Counter
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from app.config import settings

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
VLM_MATCH_PROMPT = "vlm_match_v1"
VLM_COMPARE_PROMPT = "vlm_compare_v1"
STORY_PROMPT = "story_v1"

VLM_MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "place_id": {"type": "string"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["place_id", "confidence", "reason"],
    "additionalProperties": False,
}
VLM_COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "visit_id": {"type": "string"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["visit_id", "confidence", "reason"],
    "additionalProperties": False,
}
SENTENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "place_ids": {"type": "array", "items": {"type": "string"}},
        "fields": {"type": "array", "items": {"type": "string"}},
        "is_fact": {"type": "boolean"},
    },
    "required": ["text", "place_ids", "fields", "is_fact"],
    "additionalProperties": False,
}
STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "paragraphs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "integer"},
                    "sentences": {"type": "array", "items": SENTENCE_SCHEMA},
                },
                "required": ["day", "sentences"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "paragraphs"],
    "additionalProperties": False,
}
PARAGRAPH_SCHEMA = {
    "type": "object",
    "properties": {"sentences": {"type": "array", "items": SENTENCE_SCHEMA}},
    "required": ["sentences"],
    "additionalProperties": False,
}

STYLE_GUIDES = {
    "blog": "블로그형 — 친근한 해요체, 읽는 사람에게 소개하듯이",
    "diary": "일기형 — 담백한 반말(~했다), 내 하루를 돌아보듯이",
    "brief": "간결형 — 짧은 문장, 핵심 정보 위주",
}


class AIError(RuntimeError):
    """AI 호출 실패 (네트워크, 거절, 형식 오류)."""


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


# ======================================================================
# 모의 VLM: 색 분포 기반 장면 추정
# ======================================================================
SCENES = ("sea", "night", "food", "green", "colorful", "street")
SCENE_KO = {"sea": "바다·하늘", "night": "야경", "food": "음식", "green": "녹지", "colorful": "알록달록한 골목", "street": "거리·건물"}
TYPE_COMPAT = {
    "바다": {"sea": 1.0, "night": 0.5},
    "공원": {"green": 1.0, "sea": 0.7, "night": 0.7, "colorful": 0.3, "street": 0.3},
    "관광지": {"sea": 0.8, "green": 0.7, "night": 0.6, "colorful": 0.6, "street": 0.6, "food": 0.2},
    "문화마을": {"colorful": 1.0, "street": 0.5, "sea": 0.3, "green": 0.3},
    "시장": {"street": 0.8, "food": 0.8, "colorful": 0.5},
    "음식점": {"food": 1.0, "street": 0.3, "night": 0.3},
    "카페": {"food": 0.6, "street": 0.6},
    "거리": {"street": 1.0, "night": 0.6, "colorful": 0.5, "food": 0.4},
    "전시·체험": {"street": 0.5, "sea": 0.3},
}
DEFAULT_COMPAT = 0.25


def scene_probs(jpeg: bytes) -> dict[str, float]:
    """사진의 색 분포로 장면 확률을 추정한다 (모의 VLM 전용 간이 특징)."""
    with Image.open(io.BytesIO(jpeg)) as im:
        im = im.convert("RGB")
        im.thumbnail((128, 128))
        hsv = np.asarray(im.convert("HSV"), dtype=np.float32)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1], hsv[..., 2]
    sat = (s > 60) & (v > 60)
    blue = float(np.mean(sat & (h >= 180) & (h <= 250)))
    green = float(np.mean(sat & (h >= 75) & (h < 165)))
    warm = float(np.mean((s > 70) & (v > 70) & ((h < 50) | (h > 340))))
    mean_v = float(np.mean(v))
    hist, _ = np.histogram(h[sat], bins=12, range=(0, 360))
    distinct = int(np.sum(hist > 0.04 * h.size))
    raw = {
        "sea": blue * 2.2 if mean_v > 80 else blue * 0.6,
        "night": max(0.0, (95 - mean_v) / 45),
        "food": max(0.0, warm * 2.4 - blue),
        "green": green * 2.2,
        "colorful": max(0.0, (distinct - 4) / 2.5),
        "street": 0.2,
    }
    total = sum(raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


def _type_score(ptype: str | None, probs: dict[str, float]) -> float:
    compat = TYPE_COMPAT.get(ptype or "", {})
    return sum(p * compat.get(scene, DEFAULT_COMPAT) for scene, p in probs.items())


def fake_vlm_match(jpeg: bytes, candidates: list[dict]) -> dict:
    probs = scene_probs(jpeg)
    top_scene = max(probs, key=probs.get)
    scored = []
    for c in candidates:
        dist = float(c.get("distance_m") or 0)
        s = math.exp(-dist / 250.0) * _type_score(c.get("type"), probs)
        scored.append((s, c))
    if not scored:
        return {"place_id": "none", "confidence": 0.0, "reason": "후보가 없어요."}
    scored.sort(key=lambda x: x[0], reverse=True)
    s_top, best = scored[0]
    if s_top < 0.12:
        return {"place_id": "none", "confidence": 0.2,
                "reason": f"사진은 {SCENE_KO[top_scene]} 장면으로 보이는데 후보와 잘 맞지 않아요."}
    # 1순위 점수가 다른 후보보다 얼마나 앞서는지를 확신도로 쓴다 (제곱 비율, 0.02는 "후보 밖" 몫)
    conf = s_top ** 2 / (sum(s ** 2 for s, _ in scored) + 0.02)
    conf = round(min(0.97, conf), 2)
    reason = (f"사진이 {SCENE_KO[top_scene]} 장면으로 보이고, '{best.get('type')}' 유형인 "
              f"{josa(best.get('name') or '', '이/가')} 촬영 위치에서 {round(best.get('distance_m') or 0)}m로 가장 잘 맞아요.")
    if len(scored) > 1 and scored[1][0] > s_top * 0.6:
        reason += f" 다만 {(scored[1][1].get('name') or '')}도 비슷하게 가능성이 있어요."
    return {"place_id": best["place_id"], "confidence": conf, "reason": reason}


def color_signature(jpeg: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(jpeg)) as im:
        im = im.convert("HSV")
        im.thumbnail((96, 96))
        arr = np.asarray(im, dtype=np.float32)
    hist, _ = np.histogramdd(arr.reshape(-1, 3), bins=(12, 3, 3), range=((0, 256), (0, 256), (0, 256)))
    hist = hist.ravel()
    return hist / (np.linalg.norm(hist) or 1.0)


def fake_vlm_compare(jpeg: bytes, neighbors: list[tuple[str, str, bytes]]) -> dict:
    sig = color_signature(jpeg)
    sims = [(float(np.dot(sig, color_signature(img))), vid, name) for vid, name, img in neighbors]
    sims.sort(reverse=True)
    best_sim, vid, name = sims[0]
    margin = best_sim - (sims[1][0] if len(sims) > 1 else 0.0)
    conf = round(min(0.95, 0.5 + margin * 2), 2)
    return {"visit_id": vid, "confidence": conf, "reason": f"사진의 색감·풍경이 {name} 대표 사진과 가장 비슷해요."}


# ======================================================================
# 시연 사진 세트용 미리 정한 응답 (모의 VLM 보조, 발표용)
# ======================================================================
REPLAY_FILE = "vlm_replay.json"


def image_ahash(jpeg: bytes) -> int:
    """16×16 흑백 축소본의 평균 해시(256비트). 다시 인코딩·축소돼도 거의 같은 값이 나온다."""
    with Image.open(io.BytesIO(jpeg)) as im:
        g = im.convert("L").resize((16, 16), Image.Resampling.BILINEAR)
    px = np.asarray(g, dtype=np.float32).ravel()
    bits = 0
    for b in px > px.mean():
        bits = (bits << 1) | int(b)
    return bits


class DemoReplay:
    """실제 사진 시연 세트(scripts/import_demo_photos.py)에 사람이 미리 적어 둔 VLM 응답을 돌려준다.

    모의 VLM은 사진 내용을 알아보지 못해 실제 사진에 엉뚱한 근거를 붙인다(대나무 숲 → '바다·하늘').
    그래서 시연 사진에 한해 '실제 VLM이 낼 법한 답'을 정해 두고 재생한다. 인식 결과가 아니므로 정확도 평가에 쓰지 않는다.
    세트에 없는 사진이거나 정해 둔 장소가 후보 목록에 없으면 None → 색 분포 휴리스틱으로 돌아간다(폐쇄형 선택 유지).
    """

    MAX_BIT_DIFF = 12  # 256비트 중 다른 비트 허용치 (다시 인코딩해도 보통 0~4비트 차이)

    def __init__(self, path: Path) -> None:
        self.path = path
        self._mtime: float | None = None
        self._items: list[tuple[int, dict]] = []
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def _load(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._items, self._mtime = [], None
            return
        if mtime != self._mtime:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._items = [(int(x["ahash"], 16), x["answer"]) for x in raw.get("photos", []) if x.get("answer")]
            self._mtime = mtime

    @property
    def active(self) -> bool:
        with self._lock:
            self._load()
            return bool(self._items)

    def lookup(self, jpeg: bytes, candidate_ids: set[str]) -> dict | None:
        with self._lock:
            self._load()
            if not self._items:
                return None
            h = image_ahash(jpeg)
            diff, answer = min(((bin(h ^ k).count("1"), a) for k, a in self._items), key=lambda t: t[0])
            if diff > self.MAX_BIT_DIFF:
                return None
            if answer["place_id"] != "none" and answer["place_id"] not in candidate_ids:
                self.misses += 1  # 정해 둔 장소가 후보에 없음 → 휴리스틱
                return None
            self.hits += 1
            return dict(answer)


# ======================================================================
# 모의 LLM: 공식 데이터 필드를 그대로 쓰는 템플릿 여행기
# ======================================================================
WEEKDAYS = "월화수목금토일"


def _time_phrase(hour: int) -> str:
    if hour < 11:
        return "아침"
    if hour < 14:
        return "점심 무렵"
    if hour < 17:
        return "오후"
    if hour < 19:
        return "해 질 무렵"
    return "저녁"


def _first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    s = text.strip().split(". ")[0].strip()
    return s if s.endswith(".") else s + "."


def _has_batchim(word: str) -> bool | None:
    """마지막 글자의 받침 여부 (한글이 아니면 None)."""
    for ch in reversed(word.strip()):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch.isalnum():
            return ch.lower() in "lmnr0136789"  # 영문·숫자 끝소리 대략값
    return None


def josa(word: str, pair: str) -> str:
    """조사 붙이기: josa('해운대해수욕장', '을/를') → '해운대해수욕장을'. '으로/로'는 ㄹ받침 예외."""
    a, b = pair.split("/")
    last = next((ch for ch in reversed(word.strip()) if ch.isalnum()), "")
    if pair == "으로/로" and "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 == 8:
        return word + b
    bat = _has_batchim(word)
    return word + (a if bat or bat is None else b)


def _copula(phrase: str, style: str) -> str:
    """명사로 끝나는 개요 문장에 서술어를 붙인다 (블로그형 '…이에요/예요', 일기형 '…이다/다')."""
    bat = _has_batchim(phrase)
    if style == "blog":
        return phrase + ("이에요" if bat or bat is None else "예요")
    if style == "diary":
        return phrase + ("이다" if bat or bat is None else "다")
    return phrase


def _fact_sentence(name: str, overview_first: str, style: str) -> str:
    body = overview_first.rstrip(".").strip()
    if body.endswith(("다", "요", "니다")):  # 이미 문장으로 끝나면 그대로 (실제 TourAPI 개요 형식)
        return body + "."
    if style == "brief":
        return f"{name}: {body}."
    return f"{josa(name, '은/는')} {_copula(body, style)}."


_ENDINGS = {
    "blog": (lambda t, n: f"{t}에는 {n}에 들렀어요.", lambda t, n: f"{t}, {josa(n, '으로/로')} 이동했어요.",
             lambda t, n: f"다음으로 {josa(n, '을/를')} 찾았어요."),
    "diary": (lambda t, n: f"{t}, {n}에 갔다.", lambda t, n: f"{t}에는 {josa(n, '으로/로')} 향했다.",
              lambda t, n: f"그다음 {n}에 들렀다."),
    "brief": (lambda t, n: f"{t} · {n}.", lambda t, n: f"{t} · {n} 방문.", lambda t, n: f"이어서 {n}."),
}
_OPENERS = {
    "blog": "{wd}요일 {t}, {n}에서 여행을 시작했어요.",
    "diary": "{wd}요일 {t}, {n}에서 여행을 시작했다.",
    "brief": "{wd}요일 {t}, {n}에서 출발.",
}
_OTHER = {
    "blog": "{t}에는 공식 정보가 없는 곳에서 잠시 쉬어 갔어요.",
    "diary": "{t}에는 이름 모를 곳에서 잠시 쉬었다.",
    "brief": "{t} · 기타 장소에서 휴식.",
}
_USETIME = {
    "blog": "{n} 운영시간은 '{u}'로 안내돼 있어요.",
    "diary": "{n} 운영시간은 '{u}'로 안내돼 있다.",
    "brief": "운영시간: {u}.",
}
_CLOSERS = {
    "blog": ("하루를 사진으로 돌아보니 동선이 한눈에 들어왔어요.", "사진 한 장 한 장에 그날의 바다 냄새가 남아 있는 것 같아요."),
    "diary": ("사진을 다시 보니 하루가 짧게 느껴졌다.", "걷고 또 걸은 하루였다."),
    "brief": ("일정 끝.", "하루 마무리."),
}


def fake_story(payload: dict, variant: int = 0) -> dict:
    style = payload.get("style", "blog")
    visits = payload["visits"]
    days: dict[int, list[dict]] = {}
    for v in visits:
        days.setdefault(v["day"], []).append(v)
    paragraphs = []
    for day in sorted(days):
        sentences = _fake_paragraph(style, days[day], variant, first_day=(day == min(days)))
        paragraphs.append({"day": day, "sentences": sentences})
    first = next((v for v in visits if v.get("name")), None)
    n_days = len(days)
    span = f"{n_days - 1}박 {n_days}일" if n_days > 1 else "당일치기"
    title = f"{first['name']}에서 시작한 부산 {span}" if first else f"부산 {span} 여행"
    return {"title": title, "paragraphs": paragraphs}


def _fake_paragraph(style: str, visits: list[dict], variant: int, first_day: bool) -> list[dict]:
    out = []
    for i, v in enumerate(visits):
        t = _time_phrase(int(v["start_hour"]))
        pid, name, facts = v.get("place_id"), v.get("name"), v.get("facts") or {}
        if not pid:
            out.append({"text": _OTHER[style].format(t=t), "place_ids": [], "fields": [], "is_fact": False})
            continue
        if i == 0 and first_day and variant % 2 == 0:
            text = _OPENERS[style].format(wd=v["weekday"], t=t, n=name)
        else:
            text = _ENDINGS[style][(i + variant) % len(_ENDINGS[style])](t, name)
        out.append({"text": text, "place_ids": [pid], "fields": [], "is_fact": False})
        ov = _first_sentence(facts.get("overview"))
        if ov:
            out.append({"text": _fact_sentence(name, ov, style), "place_ids": [pid], "fields": ["overview"], "is_fact": True})
        if facts.get("usetime") and (variant + i) % 2 == 0:
            out.append({"text": _USETIME[style].format(n=name, u=facts["usetime"]), "place_ids": [pid],
                        "fields": ["usetime"], "is_fact": True})
    if out:
        out.append({"text": _CLOSERS[style][variant % 2], "place_ids": [], "fields": [], "is_fact": False})
    return out


# ======================================================================
# Gateway
# ======================================================================
class AIGateway:
    def __init__(self) -> None:
        self.calls: Counter = Counter()
        self._lock = threading.Lock()
        self.replay = DemoReplay(settings.data_dir / "demo_photos" / REPLAY_FILE)

    def _count(self, name: str) -> None:
        with self._lock:
            self.calls[name] += 1

    def _fake_delay(self) -> None:
        if settings.fake_ai_latency > 0:
            time.sleep(settings.fake_ai_latency)

    def info(self) -> dict:
        replay = settings.vlm_provider != "ollama" and self.replay.active
        if settings.vlm_provider == "ollama":
            vlm = settings.vlm_model
        elif replay:
            vlm = "모의 VLM (시연 사진은 미리 정한 응답, 그 밖은 색 분포 + 거리 휴리스틱)"
        else:
            vlm = "모의 VLM (색 분포 + 거리 휴리스틱)"
        if settings.llm_provider == "anthropic":
            llm = settings.anthropic_model
        elif settings.llm_provider == "gemini":
            llm = settings.gemini_model
        else:
            llm = "모의 LLM (공식 데이터 템플릿)"
        return {"vlm_provider": settings.vlm_provider, "vlm_model": vlm, "llm_provider": settings.llm_provider,
                "llm_model": llm, "prompts": {"vlm": VLM_MATCH_PROMPT, "story": STORY_PROMPT}, "calls": dict(self.calls),
                "vlm_replay": {"active": replay, "hits": self.replay.hits, "misses": self.replay.misses}}

    # ---- VLM (사진은 서버 안 VLM에만 전달) ----
    def vlm_match(self, jpeg: bytes, candidates: list[dict]) -> str:
        """후보 중 장소 판별. 원문(JSON 문자열)을 돌려주고 검증은 CP-11이 한다."""
        self._count("vlm_match")
        if settings.vlm_provider == "ollama":
            lines = "\n".join(
                f"- place_id={c['place_id']} | 이름={c.get('name')} | 유형={c.get('type')} | 거리={round(c.get('distance_m') or 0)}m"
                + (f" | 개요={(c.get('overview') or '')[:120]}" if c.get("overview") else "")
                for c in candidates
            )
            prompt = load_prompt(VLM_MATCH_PROMPT).replace("{candidates}", lines)
            return self._ollama(prompt, [jpeg], VLM_MATCH_SCHEMA)
        self._fake_delay()
        scripted = self.replay.lookup(jpeg, {c["place_id"] for c in candidates})
        return json.dumps(scripted or fake_vlm_match(jpeg, candidates), ensure_ascii=False)

    def vlm_compare(self, jpeg: bytes, neighbors: list[tuple[str, str, bytes]]) -> str:
        """위치 없는 사진과 인접 방문지 대표 사진 비교 (FR-06)."""
        self._count("vlm_compare")
        if settings.vlm_provider == "ollama":
            lines = "\n".join(f"- visit_id={vid} | {name}" for vid, name, _ in neighbors)
            prompt = load_prompt(VLM_COMPARE_PROMPT).replace("{visits}", lines)
            return self._ollama(prompt, [jpeg] + [img for _, _, img in neighbors], VLM_COMPARE_SCHEMA)
        self._fake_delay()
        return json.dumps(fake_vlm_compare(jpeg, neighbors), ensure_ascii=False)

    def _ollama(self, prompt: str, images: list[bytes], schema: dict) -> str:
        body = {
            "model": settings.vlm_model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
            "messages": [{"role": "user", "content": prompt,
                          "images": [base64.b64encode(i).decode() for i in images]}],
        }
        try:
            r = httpx.post(f"{settings.ollama_url}/api/chat", json=body, timeout=60.0)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise AIError(f"VLM 호출 실패: {e}") from e

    # ---- LLM (사진 없이 확정 사실만 전달) ----
    def llm_story(self, payload: dict) -> str:
        self._count("llm_story")
        style = payload.get("style", "blog")
        system = load_prompt(STORY_PROMPT).replace("{style_guide}", STYLE_GUIDES.get(style, STYLE_GUIDES["blog"]))
        if settings.llm_provider == "fake":
            self._fake_delay()
            return json.dumps(fake_story(payload), ensure_ascii=False)
        return self._llm(system, json.dumps(payload, ensure_ascii=False), STORY_SCHEMA)

    def llm_rewrite_paragraph(self, payload: dict, variant: int) -> str:
        """문단 다시 쓰기 (FR-10): 해당 날짜의 방문지 사실만 넣고 문단 하나를 새로 쓴다."""
        self._count("llm_rewrite")
        style = payload.get("style", "blog")
        if settings.llm_provider == "fake":
            self._fake_delay()
            sents = _fake_paragraph(style, payload["visits"], variant, first_day=payload.get("first_day", False))
            return json.dumps({"sentences": sents}, ensure_ascii=False)
        system = load_prompt(STORY_PROMPT).replace("{style_guide}", STYLE_GUIDES.get(style, STYLE_GUIDES["blog"]))
        system += "\n이번에는 입력된 하루치 방문지로 문단 하나만, 이전과 다른 표현으로 다시 쓰세요."
        return self._llm(system, json.dumps(payload, ensure_ascii=False), PARAGRAPH_SCHEMA)

    def _llm(self, system: str, user: str, schema: dict) -> str:
        if settings.llm_provider == "anthropic":
            return self._anthropic(system, user, schema)
        if settings.llm_provider == "gemini":
            return self._gemini(system, user)
        raise AIError(f"알 수 없는 LLM_PROVIDER: {settings.llm_provider}")

    def _anthropic(self, system: str, user: str, schema: dict) -> str:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise AIError("anthropic 패키지가 없어요 (pip install -r requirements-optional.txt)") from e
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        try:
            resp = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.RateLimitError as e:
            raise AIError("LLM 요청 한도를 넘었어요. 잠시 후 다시 시도해 주세요.") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"LLM 오류 ({e.status_code})") from e
        except anthropic.APIConnectionError as e:
            raise AIError("LLM 서버에 연결하지 못했어요.") from e
        if resp.stop_reason == "refusal":
            raise AIError("LLM이 요청을 거절했어요.")
        if resp.stop_reason == "max_tokens":
            raise AIError("LLM 응답이 너무 길어 잘렸어요.")
        return next(b.text for b in resp.content if b.type == "text")

    def _gemini(self, system: str, user: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        try:
            r = httpx.post(url, params={"key": settings.gemini_api_key}, json=body, timeout=60.0)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise AIError(f"LLM 호출 실패: {e}") from e


ai_gateway = AIGateway()
