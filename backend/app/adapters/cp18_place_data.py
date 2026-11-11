"""CP-18 Place Data Adapter (External 계층).

책임: TourAPI·부산시·카카오 로컬을 공통 형식(PlaceRecord)으로 감싸기, 시간 제한·2회 재시도·호출 수 기록,
부산시 목록 일 1회 적재 (FR-03, FR-08, NFR-08, QA-06). 제공 인터페이스: IF-18 PlaceSource.

소스별로 API 키가 있으면 실제 API를, 없으면 샘플 데이터(app/data/sample_places.json)를 쓴다.
실제 API 응답 형식은 공개 문서 기준으로 작성했고, 키를 발급받아 스프린트 1 PoC에서 확인한다.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from app.config import settings
from app.geo import haversine_m

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_places.json"

SOURCE_NAMES = {
    "tour": "한국관광공사 TourAPI",
    "busan": "부산광역시 명소·맛집 정보",
    "kakao": "카카오 로컬",
}
SOURCE_LICENSES = {
    "tour": "공공누리 — 출처 표시",
    "busan": "공공누리 — 출처 표시",
    "kakao": "카카오 지도·로컬 API 운영정책 (장소 ID·URL만 저장)",
}

# TourAPI contenttypeid → 화면 유형
TOUR_TYPES = {"12": "관광지", "14": "전시·체험", "15": "축제", "25": "여행코스", "28": "레포츠", "32": "숙박", "38": "쇼핑", "39": "음식점"}
BEACH_WORDS = ("해수욕장", "해변")


class PlaceSourceError(RuntimeError):
    """외부 API가 재시도 후에도 실패 (방문지 단위로 격리, AC-16)."""


@dataclass
class PlaceRecord:
    source: str
    source_id: str
    name: str | None
    type: str | None
    lat: float | None
    lng: float | None
    address: str | None = None
    overview: str | None = None
    image_url: str | None = None
    place_url: str | None = None
    usetime: str | None = None
    updated_at: str | None = None
    sample: bool = False

    @property
    def place_id(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def source_name(self) -> str:
        name = SOURCE_NAMES.get(self.source, self.source)
        return f"{name} (샘플)" if self.sample else name

    def to_dict(self) -> dict:
        d = asdict(self)
        d["place_id"] = self.place_id
        d["source_name"] = self.source_name
        d["license"] = SOURCE_LICENSES.get(self.source, "")
        return d


@dataclass
class CallStats:
    counts: Counter = field(default_factory=Counter)
    failures: Counter = field(default_factory=Counter)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def hit(self, name: str, ok: bool = True) -> None:
        with self.lock:
            self.counts[name] += 1
            if not ok:
                self.failures[name] += 1


def _http_get_json(url: str, params: dict, headers: dict | None, stats: CallStats, name: str) -> dict:
    """시간 제한 5초, 실패 시 2회 재시도(지수 백오프) 후 PlaceSourceError (QA-06)."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(url, params=params, headers=headers)
                r.raise_for_status()
                stats.hit(name)
                return r.json()
        except (httpx.HTTPError, ValueError) as e:
            last = e
            stats.hit(name, ok=False)
            if attempt < 2:
                time.sleep(0.3 * (2 ** attempt))
    raise PlaceSourceError(f"{name} 호출 실패: {last}")


# ---------------------------------------------------------------- 샘플 데이터
class SampleData:
    def __init__(self, path: Path = SAMPLE_PATH) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        updated = raw.get("updated_at")
        self.records: list[PlaceRecord] = []
        for p in raw["places"]:
            self.records.append(PlaceRecord(
                source=p["source"], source_id=p["source_id"], name=p["name"], type=p["type"],
                lat=p["lat"], lng=p["lng"], address=p.get("address"), overview=p.get("overview"),
                usetime=p.get("usetime"), place_url=None, updated_at=updated, sample=True,
            ))

    def by_source(self, source: str) -> list[PlaceRecord]:
        return [r for r in self.records if r.source == source]

    def nearby(self, source: str, lat: float, lng: float, radius_m: float) -> list[PlaceRecord]:
        return [r for r in self.by_source(source) if haversine_m(lat, lng, r.lat, r.lng) <= radius_m]

    def get(self, place_id: str) -> PlaceRecord | None:
        return next((r for r in self.records if r.place_id == place_id), None)

    def search(self, source: str, query: str) -> list[PlaceRecord]:
        q = query.replace(" ", "")
        return [r for r in self.by_source(source) if q and q in (r.name or "").replace(" ", "")]


# ---------------------------------------------------------------- 어댑터
class PlaceDataAdapter:
    """IF-18 PlaceSource 구현."""

    TOUR_BASE = "https://apis.data.go.kr/B551011/KorService2"
    BUSAN_ATTRACTION = "https://apis.data.go.kr/6260000/AttractionService/getAttractionKr"
    BUSAN_FOOD = "https://apis.data.go.kr/6260000/FoodService/getFoodKr"
    KAKAO_BASE = "https://dapi.kakao.com/v2/local/search"

    def __init__(self) -> None:
        self.sample = SampleData()
        self.stats = CallStats()
        # 장애 주입 (NFR-08 시스템 테스트·시연): FAULT_INJECT=kakao,tour 처럼 주면 해당 소스 호출이 실패한다
        self.fail_sources: set[str] = {x.strip() for x in os.environ.get("FAULT_INJECT", "").split(",") if x.strip()}

    # 모드
    @property
    def tour_real(self) -> bool:
        return bool(settings.tour_api_key)

    @property
    def busan_real(self) -> bool:
        return bool(settings.busan_api_key)

    @property
    def kakao_real(self) -> bool:
        return bool(settings.kakao_rest_key)

    def modes(self) -> dict:
        return {
            "tour": "real" if self.tour_real else "sample",
            "busan": "real" if self.busan_real else "sample",
            "kakao": "real" if self.kakao_real else "sample",
        }

    def _check_fault(self, source: str) -> None:
        if source in self.fail_sources:
            self.stats.hit(source, ok=False)
            raise PlaceSourceError(f"{source} 장애(모의)")

    # ---- TourAPI ----
    def tour_nearby(self, lat: float, lng: float, radius_m: int) -> list[PlaceRecord]:
        self._check_fault("tour")
        if not self.tour_real:
            self.stats.hit("tour")
            return self.sample.nearby("tour", lat, lng, radius_m)
        data = _http_get_json(f"{self.TOUR_BASE}/locationBasedList2", {
            "serviceKey": settings.tour_api_key, "MobileOS": "ETC", "MobileApp": "Chalkak", "_type": "json",
            "mapX": lng, "mapY": lat, "radius": radius_m, "arrange": "E", "numOfRows": 20, "pageNo": 1,
        }, None, self.stats, "tour")
        return [self._tour_record(it) for it in _tour_items(data)]

    def tour_detail(self, source_id: str) -> PlaceRecord | None:
        if not self.tour_real:
            return self.sample.get(f"tour:{source_id}")
        data = _http_get_json(f"{self.TOUR_BASE}/detailCommon2", {
            "serviceKey": settings.tour_api_key, "MobileOS": "ETC", "MobileApp": "Chalkak", "_type": "json",
            "contentId": source_id,
        }, None, self.stats, "tour")
        items = _tour_items(data)
        return self._tour_record(items[0]) if items else None

    def tour_search(self, query: str) -> list[PlaceRecord]:
        if not self.tour_real:
            return self.sample.search("tour", query)
        data = _http_get_json(f"{self.TOUR_BASE}/searchKeyword2", {
            "serviceKey": settings.tour_api_key, "MobileOS": "ETC", "MobileApp": "Chalkak", "_type": "json",
            "keyword": query, "areaCode": 6, "numOfRows": 10, "pageNo": 1,  # areaCode 6 = 부산
        }, None, self.stats, "tour")
        return [self._tour_record(it) for it in _tour_items(data)]

    @staticmethod
    def _tour_record(it: dict) -> PlaceRecord:
        title = it.get("title") or ""
        ptype = "바다" if any(w in title for w in BEACH_WORDS) else TOUR_TYPES.get(str(it.get("contenttypeid")), "관광지")
        mod = str(it.get("modifiedtime") or "")
        return PlaceRecord(
            source="tour", source_id=str(it.get("contentid")), name=title, type=ptype,
            lat=_float(it.get("mapy")), lng=_float(it.get("mapx")), address=it.get("addr1"),
            overview=_strip_html(it.get("overview")), image_url=it.get("firstimage") or None,
            updated_at=f"{mod[:4]}-{mod[4:6]}-{mod[6:8]}" if len(mod) >= 8 else None,
        )

    # ---- 부산광역시 (하루 한 번 전체 목록을 받아 캐시에서 반경 검색) ----
    def busan_all(self) -> list[PlaceRecord]:
        self._check_fault("busan")
        if not self.busan_real:
            self.stats.hit("busan")
            return self.sample.by_source("busan")
        out: list[PlaceRecord] = []
        for url, key, ptype in ((self.BUSAN_ATTRACTION, "getAttractionKr", "관광지"), (self.BUSAN_FOOD, "getFoodKr", "음식점")):
            data = _http_get_json(url, {"serviceKey": settings.busan_api_key, "pageNo": 1, "numOfRows": 500, "resultType": "json"},
                                  None, self.stats, "busan")
            for it in (data.get(key) or {}).get("item", []) or []:
                out.append(PlaceRecord(
                    source="busan", source_id=str(it.get("UC_SEQ")), name=it.get("MAIN_TITLE") or it.get("PLACE"),
                    type=ptype, lat=_float(it.get("LAT")), lng=_float(it.get("LNG")),
                    address=it.get("ADDR1"), overview=_strip_html(it.get("ITEMCNTNTS")),
                    image_url=it.get("MAIN_IMG_NORMAL") or None, usetime=it.get("USAGE_DAY_WEEK_AND_TIME") or None,
                    updated_at=time.strftime("%Y-%m-%d"),
                ))
        return out

    # ---- 카카오 로컬 (결과는 장소 ID·URL만 저장, 나머지는 필요할 때 조회) ----
    def kakao_nearby(self, lat: float, lng: float, radius_m: int) -> list[PlaceRecord]:
        self._check_fault("kakao")
        if not self.kakao_real:
            self.stats.hit("kakao")
            return self.sample.nearby("kakao", lat, lng, radius_m)
        out: list[PlaceRecord] = []
        for code in ("FD6", "CE7"):  # 음식점, 카페 보조 검색
            data = _http_get_json(f"{self.KAKAO_BASE}/category.json", {
                "category_group_code": code, "x": lng, "y": lat, "radius": radius_m, "sort": "distance", "size": 5,
            }, {"Authorization": f"KakaoAK {settings.kakao_rest_key}"}, self.stats, "kakao")
            out.extend(self._kakao_record(d) for d in data.get("documents", []))
        return out

    def kakao_lookup(self, source_id: str, near_lat: float | None, near_lng: float | None) -> PlaceRecord | None:
        """카카오 장소를 실시간으로 다시 조회한다 (ID로 직접 조회하는 API가 없어 근처 검색 후 ID로 찾음)."""
        if not self.kakao_real:
            self.stats.hit("kakao")
            return self.sample.get(f"kakao:{source_id}")
        if near_lat is None or near_lng is None:
            return None
        for code in ("FD6", "CE7"):
            data = _http_get_json(f"{self.KAKAO_BASE}/category.json", {
                "category_group_code": code, "x": near_lng, "y": near_lat, "radius": 1000, "sort": "distance", "size": 15,
            }, {"Authorization": f"KakaoAK {settings.kakao_rest_key}"}, self.stats, "kakao")
            for d in data.get("documents", []):
                if str(d.get("id")) == str(source_id):
                    return self._kakao_record(d)
        return None

    def kakao_search(self, query: str, lat: float | None, lng: float | None) -> list[PlaceRecord]:
        if not self.kakao_real:
            return self.sample.search("kakao", query)
        params = {"query": query, "size": 10}
        if lat is not None and lng is not None:
            params.update({"x": lng, "y": lat, "radius": 20000, "sort": "distance"})
        data = _http_get_json(f"{self.KAKAO_BASE}/keyword.json", params,
                              {"Authorization": f"KakaoAK {settings.kakao_rest_key}"}, self.stats, "kakao")
        return [self._kakao_record(d) for d in data.get("documents", [])]

    @staticmethod
    def _kakao_record(d: dict) -> PlaceRecord:
        cat = d.get("category_group_name") or (d.get("category_name") or "").split(">")[-1].strip() or "장소"
        return PlaceRecord(
            source="kakao", source_id=str(d.get("id")), name=d.get("place_name"), type=cat,
            lat=_float(d.get("y")), lng=_float(d.get("x")),
            address=d.get("road_address_name") or d.get("address_name"), place_url=d.get("place_url"),
        )


def _tour_items(data: dict) -> list[dict]:
    items = (((data.get("response") or {}).get("body") or {}).get("items") or {})
    if isinstance(items, dict):
        item = items.get("item") or []
        return item if isinstance(item, list) else [item]
    return []


def _float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _strip_html(s: str | None) -> str | None:
    if not s:
        return s
    import re
    return re.sub(r"<[^>]+>", " ", s).replace("&nbsp;", " ").strip()


place_adapter = PlaceDataAdapter()
