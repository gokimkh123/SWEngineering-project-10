"""단위 테스트 — 순수 로직 컴포넌트 (계획서 8.1: CP-08, CP-09, CP-11 라우팅, CP-14) + CP-05, CP-12."""
import io
import json
from datetime import datetime, timedelta

import pytest
from PIL import Image

from app.components import cp05_route, cp08_exif, cp09_clusterer, cp12_untagged
from app.components import cp14_fact_checker as fc
from app.components.cp11_matcher import InvalidVlmResponse, PlaceMatcher, VlmAnswer, parse_vlm_response, route
from app.models import VisitStatus


# ---------------------------------------------------------------- CP-08 EXIF Extractor
class TestExif:
    def test_reads_time_and_gps(self, demo_dir, demo_labels):
        p = demo_labels["photos"][0]
        meta = cp08_exif.extract_meta((demo_dir / p["file"]).read_bytes())
        assert meta.taken_at == datetime.fromisoformat(p["taken_at"])
        assert meta.has_gps and 35.0 < meta.lat < 35.3 and 128.9 < meta.lng < 129.3

    def test_no_gps_photo(self, demo_dir, demo_labels):
        p = next(x for x in demo_labels["photos"] if not x["has_gps"])
        meta = cp08_exif.extract_meta((demo_dir / p["file"]).read_bytes())
        assert meta.taken_at is not None and not meta.has_gps

    def test_thumbnail_strips_location(self, demo_dir, demo_labels):
        """AC-09: 썸네일에 EXIF 위치 없음."""
        data = (demo_dir / demo_labels["photos"][0]["file"]).read_bytes()
        assert cp08_exif.has_location_exif(data)
        thumb = cp08_exif.make_thumbnail(data)
        assert not cp08_exif.has_location_exif(thumb)
        with Image.open(io.BytesIO(thumb)) as im:
            assert max(im.size) <= cp08_exif.THUMB_MAX_PX
            assert not im.getexif()

    def test_png_without_exif(self):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        meta = cp08_exif.extract_meta(buf.getvalue())
        assert meta.format == "PNG" and meta.taken_at is None and not meta.has_gps

    def test_rejects_unsupported(self):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "GIF")
        with pytest.raises(cp08_exif.UnsupportedImageError):
            cp08_exif.detect_format(buf.getvalue())
        with pytest.raises(cp08_exif.UnsupportedImageError):
            cp08_exif.detect_format(b"not an image")


# ---------------------------------------------------------------- CP-09 Visit Clusterer
class TestClusterer:
    def _points(self, demo_dir, demo_labels):
        pts = []
        for p in demo_labels["photos"]:
            m = cp08_exif.extract_meta((demo_dir / p["file"]).read_bytes())
            pts.append(cp09_clusterer.PhotoPoint(p["file"], m.taken_at, m.lat, m.lng))
        return pts

    def test_demo_set_matches_labels(self, demo_dir, demo_labels):
        """AC-02: 위치 있는 21장이 정답 라벨과 같은 6개 방문지로 묶이고(사진별 배정 일치) 날짜별로 구분."""
        res = cp09_clusterer.cluster_photos(self._points(demo_dir, demo_labels))
        assert len(res.visits) == 6
        assert [v.day for v in res.visits] == [1, 1, 1, 1, 1, 2]
        truth = {}
        for p in demo_labels["photos"]:
            if p["has_gps"]:
                truth.setdefault(p["visit"], set()).add(p["file"])
        assert sorted(map(frozenset, truth.values()), key=sorted) == sorted((frozenset(v.photo_ids) for v in res.visits), key=sorted)
        assert len(res.untagged_ids) == 3
        assert all(len(str(v.center_lat).split(".")[1]) <= 4 for v in res.visits)  # 중심 좌표 소수점 4자리

    def test_time_only_when_no_gps(self):
        t0 = datetime(2026, 10, 10, 10, 0)
        pts = [cp09_clusterer.PhotoPoint(str(i), t0 + timedelta(minutes=m), None, None) for i, m in enumerate([0, 10, 20, 200, 210])]
        res = cp09_clusterer.cluster_photos(pts)
        assert res.time_only and len(res.visits) == 2 and res.visits[0].center_lat is None

    def test_no_info_photos(self):
        pts = [cp09_clusterer.PhotoPoint("a", None, None, None),
               cp09_clusterer.PhotoPoint("b", datetime(2026, 10, 10, 9), 35.1, 129.1)]
        res = cp09_clusterer.cluster_photos(pts)
        assert res.no_info_ids == ["a"] and len(res.visits) == 1

    def test_same_place_different_time_splits(self):
        t0 = datetime(2026, 10, 10, 10, 0)
        pts = [cp09_clusterer.PhotoPoint("a", t0, 35.15, 129.16), cp09_clusterer.PhotoPoint("b", t0 + timedelta(hours=3), 35.15, 129.16)]
        assert len(cp09_clusterer.cluster_photos(pts).visits) == 2


# ---------------------------------------------------------------- CP-11 Place Matcher
class TestMatcher:
    IDS = {"tour:1", "kakao:2"}

    def test_parse_valid(self):
        a = parse_vlm_response('{"place_id": "tour:1", "confidence": 0.86, "reason": "다리"}', self.IDS)
        assert a.place_id == "tour:1" and a.confidence == 0.86

    def test_parse_none(self):
        assert parse_vlm_response('{"place_id": "none", "confidence": 0.1, "reason": ""}', self.IDS).place_id is None

    @pytest.mark.parametrize("raw", [
        '{"place_id": "tour:999", "confidence": 0.9, "reason": ""}',  # 후보 밖 (closed-set 위반)
        '{"place_id": "tour:1", "confidence": 1.5, "reason": ""}',  # 범위 밖
        '{"place_id": "tour:1", "confidence": "high", "reason": ""}',  # 타입 오류
        '{"place_id": "tour:1", "confidence": 0.9, "reason": "", "extra": 1}',  # 정해진 필드 아님
        'Haeundae beach',  # JSON 아님
    ])
    def test_parse_rejects(self, raw):
        with pytest.raises(InvalidVlmResponse):
            parse_vlm_response(raw, self.IDS)

    @pytest.mark.parametrize("conf,expected", [
        (0.95, VisitStatus.AUTO_CONFIRMED), (0.8, VisitStatus.AUTO_CONFIRMED), (0.79, VisitStatus.NEEDS_CHECK),
        (0.5, VisitStatus.NEEDS_CHECK), (0.49, VisitStatus.NEEDS_SELECTION),
    ])
    def test_routing(self, conf, expected):
        """FR-04: 0.8 이상 자동확정, 0.5 이상 0.8 미만 확인필요, 0.5 미만 선택필요."""
        assert route(VlmAnswer("tour:1", conf, "")) == expected

    def test_routing_none(self):
        assert route(VlmAnswer(None, 0.9, "")) == VisitStatus.NEEDS_SELECTION
        assert route(None) == VisitStatus.NEEDS_SELECTION

    def test_retry_once_then_selection(self):
        """AIR-03: 후보 밖 ID·형식 오류는 거부 후 1회 재요청, 재실패 시 사용자 선택."""
        class GW:
            def __init__(self, answers):
                self.answers, self.calls = list(answers), 0

            def vlm_match(self, image, cands):
                self.calls += 1
                return self.answers.pop(0)

        cands = [{"place_id": "tour:1"}]
        gw = GW(['{"place_id": "tour:9", "confidence": 0.9, "reason": ""}', '{"place_id": "tour:1", "confidence": 0.9, "reason": "ok"}'])
        ans, err = PlaceMatcher(gw).ask(b"", cands)
        assert gw.calls == 2 and ans.place_id == "tour:1" and err is None
        gw = GW(["oops", "still oops"])
        ans, err = PlaceMatcher(gw).ask(b"", cands)
        assert gw.calls == 2 and ans is None and "응답 오류" in err


class TestDemoReplay:
    """실제 사진 시연 세트의 미리 정한 응답: 같은 사진(재인코딩 포함)에만, 후보 안의 장소일 때만 쓴다."""

    @staticmethod
    def _jpeg(color_top, color_bottom, quality=90) -> bytes:
        im = Image.new("RGB", (320, 240), color_top)
        im.paste(Image.new("RGB", (320, 120), color_bottom), (0, 120))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality)
        return buf.getvalue()

    def _replay(self, tmp_path, answer):
        from app.adapters.cp19_ai_gateway import DemoReplay, image_ahash
        img = self._jpeg((20, 120, 30), (200, 200, 210))
        path = tmp_path / "vlm_replay.json"
        path.write_text(json.dumps({"photos": [{"ahash": f"{image_ahash(img):064x}", "answer": answer}]}), encoding="utf-8")
        return DemoReplay(path), img

    def test_hit_after_reencode(self, tmp_path):
        replay, img = self._replay(tmp_path, {"place_id": "tour:1", "confidence": 0.9, "reason": "대숲"})
        small = io.BytesIO()
        Image.open(io.BytesIO(img)).resize((160, 120)).save(small, "JPEG", quality=70)
        assert replay.lookup(small.getvalue(), {"tour:1"})["place_id"] == "tour:1"
        assert replay.hits == 1

    def test_other_photo_or_missing_candidate_falls_back(self, tmp_path):
        replay, img = self._replay(tmp_path, {"place_id": "tour:1", "confidence": 0.9, "reason": "대숲"})
        assert replay.lookup(self._jpeg((200, 200, 210), (20, 120, 30)), {"tour:1"}) is None  # 다른 사진
        assert replay.lookup(img, {"tour:2"}) is None  # 정해 둔 장소가 후보에 없음 → 휴리스틱 (폐쇄형 유지)
        assert replay.misses == 1

    def test_none_answer_allowed(self, tmp_path):
        replay, img = self._replay(tmp_path, {"place_id": "none", "confidence": 0.15, "reason": "맞는 후보 없음"})
        assert replay.lookup(img, {"tour:2"})["place_id"] == "none"

    def test_no_file_inactive(self, tmp_path):
        from app.adapters.cp19_ai_gateway import DemoReplay
        replay = DemoReplay(tmp_path / "nothing.json")
        assert not replay.active and replay.lookup(self._jpeg((0, 0, 0), (255, 255, 255)), {"tour:1"}) is None


# ---------------------------------------------------------------- CP-14 Fact Checker
FACTS = {
    "tour:1": {"name": "해운대해수욕장", "overview": "약 1.5km 길이의 백사장.", "address": "부산광역시 해운대구 우동"},
    "tour:3": {"name": "해운대 블루라인파크", "usetime": "해변열차 09:30~18:00"},
}
KNOWN = {"해운대해수욕장": "tour:1", "해운대 블루라인파크": "tour:3", "광안리해수욕장": "tour:2"}
CONFIRMED = {"tour:1", "tour:3"}


class TestFactChecker:
    def test_cited_fact_ok(self):
        r = fc.check_generated_sentence("해운대해수욕장은 약 1.5km 길이의 백사장이 있다.", ["tour:1"], ["overview"], True, FACTS, CONFIRMED, KNOWN)
        assert r.ok and r.is_fact

    def test_fact_without_source(self):
        r = fc.check_generated_sentence("해운대해수욕장은 1965년에 개장했다.", ["tour:1"], [], True, FACTS, CONFIRMED, KNOWN)
        assert not r.ok and r.warnings[0].code == "no_source"

    def test_undeclared_fact_detected(self):
        """LLM이 is_fact를 false로 표시해도 숫자가 있으면 사실 문장으로 본다 (AIR-06)."""
        r = fc.check_generated_sentence("백사장은 2km나 됐다.", ["tour:1"], [], False, FACTS, CONFIRMED, KNOWN)
        assert r.is_fact and not r.ok

    def test_number_mismatch(self):
        r = fc.check_generated_sentence("백사장 길이는 3km다.", ["tour:1"], ["overview"], True, FACTS, CONFIRMED, KNOWN)
        assert any(w.code == "number_mismatch" for w in r.warnings)

    def test_unvisited_place(self):
        r = fc.check_generated_sentence("광안리해수욕장도 들렀다.", [], [], False, FACTS, CONFIRMED, KNOWN)
        assert any(w.code == "unvisited_place" for w in r.warnings)

    def test_unconfirmed_place_id(self):
        r = fc.check_generated_sentence("좋았다.", ["tour:2"], [], False, FACTS, CONFIRMED, KNOWN)
        assert any(w.code == "unconfirmed_place" for w in r.warnings)

    def test_edited_time_mismatch(self):
        """FR-10: 편집한 문장의 운영시간이 공식 데이터와 다르면 경고."""
        r = fc.check_edited_sentence("해운대 블루라인파크 해변열차는 오후 8시까지 운행한다.", FACTS, CONFIRMED, KNOWN)
        assert [w.code for w in r.warnings] == ["time_mismatch"]
        assert "09:30~18:00" in r.warnings[0].message

    def test_edited_time_ok(self):
        r = fc.check_edited_sentence("해운대 블루라인파크 열차는 18:00까지였다.", FACTS, CONFIRMED, KNOWN)
        assert r.ok

    def test_edited_plain_count_not_checked(self):
        r = fc.check_edited_sentence("해운대해수욕장에서 사진을 30장 찍었다.", FACTS, CONFIRMED, KNOWN)
        assert r.ok

    def test_time_tokens(self):
        assert fc.time_tokens("오후 8시 30분, 09:30") == {"20:30", "09:30"}


# ---------------------------------------------------------------- CP-12 / CP-05
class TestUntaggedAndRoute:
    T = datetime(2026, 10, 10)
    SPANS = [
        cp12_untagged.VisitSpan("a", "A", T.replace(hour=10), T.replace(hour=10, minute=50)),
        cp12_untagged.VisitSpan("b", "B", T.replace(hour=13), T.replace(hour=13, minute=40)),
    ]

    def test_within_visit(self):
        s = cp12_untagged.suggest_by_time(self.T.replace(hour=10, minute=55), self.SPANS)
        assert s.visit_id == "a" and s.method == "time"

    def test_closer_in_time(self):
        s = cp12_untagged.suggest_by_time(self.T.replace(hour=11, minute=20), self.SPANS)
        assert s.visit_id == "a"

    def test_ambiguous_goes_to_vlm(self):
        s = cp12_untagged.suggest_by_time(self.T.replace(hour=11, minute=55), self.SPANS)
        assert s.method == "vlm" and s.neighbors == ["a", "b"]

    def test_route_legs_and_days(self):
        mk = lambda i, day, h, lat, lng: cp05_route.RouteStop(  # noqa: E731
            str(i), i, day, f"2026-10-1{day}", self.T.replace(day=9 + day, hour=h), self.T.replace(day=9 + day, hour=h, minute=30),
            lat, lng, f"S{i}", "바다", None, 2, None, "확정")
        stops = [mk(1, 1, 10, 35.1587, 129.1604), mk(2, 1, 12, 35.1588, 129.1717), mk(3, 2, 10, 35.0975, 129.0106)]
        r = cp05_route.build_route(stops)
        assert len(r["pins"]) == 3 and len(r["legs"]) == 1  # 날짜가 바뀌면 경로를 잇지 않음
        assert r["legs"][0]["mode"] == "도보" and r["legs"][0]["minutes"] > 0
        assert len(cp05_route.build_route(stops, day=2)["pins"]) == 1
        summary = cp05_route.route_summary(stops)
        assert "lat" not in json.dumps(summary)  # 공유 카드·여행기 요약에 좌표 없음
