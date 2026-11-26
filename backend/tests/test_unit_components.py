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

    # 사진 기록(방문 시각·날짜)과 맞는 표현은 공식 데이터에 없어도 지우지 않는다
    TRIP = fc.TripRecord.from_spans([(datetime(2026, 11, 21, 10, 12), datetime(2026, 11, 21, 10, 40)),
                                     (datetime(2026, 11, 22, 15, 5), datetime(2026, 11, 22, 15, 5))])

    def test_trip_time_not_checked_against_official_data(self):
        for text in ("먼저 10시에 해운대해수욕장으로 향했다.", "오후 3시에는 해운대해수욕장을 다시 찾았다.",
                     "2026년 11월 22일, 2일차에는 해운대해수욕장에 갔다.", "10:40까지 해운대해수욕장에 머물렀다."):
            r = fc.check_generated_sentence(text, ["tour:1"], ["overview"], True, FACTS, CONFIRMED, KNOWN, trip=self.TRIP)
            assert r.ok, (text, r.warnings)

    def test_time_not_in_trip_still_checked(self):
        r = fc.check_generated_sentence("오후 7시에 해운대해수욕장으로 향했다.", ["tour:1"], ["overview"], True, FACTS, CONFIRMED, KNOWN, trip=self.TRIP)
        assert any(w.code == "number_mismatch" for w in r.warnings)
        r = fc.check_generated_sentence("10시에 들른 해운대해수욕장 백사장은 3km다.", ["tour:1"], ["overview"], True, FACTS, CONFIRMED, KNOWN, trip=self.TRIP)
        assert [w.message for w in r.warnings] == ["공식 데이터에 없는 수치가 있어요: 3"]

    def test_edited_visit_time_is_not_opening_hours(self):
        r = fc.check_edited_sentence("오후 3시에 해운대 블루라인파크 열차를 탔다.", FACTS, CONFIRMED, KNOWN, trip=self.TRIP)
        assert r.ok


# ---------------------------------------------------------------- CP-12 / CP-05
class TestFactCheckerScriptAndTimeOfDay:
    """D-07: 한자가 섞이거나 사진 기록의 방문 시각과 다른 시간대 표현은 생성 문장에서 뺀다."""
    FACTS = {"tour:16": {"name": "오륙도 스카이워크", "overview": "해안 절벽 끝에 설치된 유리 바닥 전망대."},
             "tour:8": {"name": "감천문화마을", "overview": "1950년대 피란민 정착지에서 시작된 산비탈 마을.", "usetime": "09:00~18:00"}}
    KNOWN = {"오륙도 스카이워크": "tour:16", "감천문화마을": "tour:8"}
    CONFIRMED = {"tour:16", "tour:8"}
    TRIP = fc.TripRecord.from_visits([("tour:8", 1, datetime(2026, 11, 21, 10, 12), datetime(2026, 11, 21, 10, 12)),
                                      ("tour:16", 1, datetime(2026, 11, 21, 15, 5), datetime(2026, 11, 21, 15, 5))])

    def check(self, text, pids=(), fields=(), is_fact=False, day=1):
        return fc.check_generated_sentence(text, list(pids), list(fields), is_fact, self.FACTS, self.CONFIRMED, self.KNOWN,
                                           trip=self.TRIP, day=day)

    def test_hanja_rejected(self):
        """실제 녹화(11/25)에서 나온 문장: 한자 '午時' + 방문 시각(15:05)과 다른 시간."""
        r = self.check("午時가 되면 해안 절벽 끝에 설치된 오륙도 스카이워크로 올라서 바다 전망을 감상했습니다.", ["tour:16"])
        assert "foreign_script" in [w.code for w in r.warnings]

    def test_time_of_day_mismatch_removed(self):
        r = self.check("정오가 되자 오륙도 스카이워크에 올랐어요.", ["tour:16"])
        assert [w.code for w in r.warnings] == ["time_of_day_mismatch"]
        r = self.check("저녁에는 감천문화마을을 걸었어요.", [])  # 장소 ID 없이 이름만 나와도 그 장소 방문 시각과 대조
        assert [w.code for w in r.warnings] == ["time_of_day_mismatch"]

    def test_time_of_day_matches_visit(self):
        assert self.check("아침에 감천문화마을에서 여행을 시작했어요.", ["tour:8"]).ok
        assert self.check("오후에는 오륙도 스카이워크에 들렀어요.", ["tour:16"]).ok
        assert self.check("점심 무렵 감천문화마을을 둘러봤어요.", ["tour:8"]).ok  # 10:12 → 앞뒤 1시간 허용

    def test_opening_hours_sentence_not_time_of_day(self):
        """운영시간 문장의 '아침'은 방문 시각이 아니므로 대조하지 않는다."""
        r = self.check("감천문화마을 안내센터는 아침 09:00부터 18:00까지 운영해요.", ["tour:8"], ["usetime"], True)
        assert r.ok

    def test_sentence_without_place_uses_that_day(self):
        assert not self.check("밤늦게 하루를 마무리했다.").ok      # 1일차 방문은 10:12·15:05 → 밤은 맞지 않음
        assert self.check("오후에 하루를 정리했다.").ok

    def test_template_time_phrases_always_pass(self):
        """템플릿 문장(_time_phrase)이 쓰는 시간대 표현은 어떤 방문 시각에서도 지워지지 않는다."""
        from app.adapters.cp19_ai_gateway import _time_phrase
        for h in range(24):
            trip = fc.TripRecord.from_visits([("tour:8", 1, datetime(2026, 11, 21, h, 0), datetime(2026, 11, 21, h, 0))])
            r = fc.check_generated_sentence(f"{_time_phrase(h)}에는 감천문화마을에 들렀어요.", ["tour:8"], [], False,
                                            self.FACTS, self.CONFIRMED, self.KNOWN, trip=trip, day=1)
            assert r.ok, (h, r.warnings)

    def test_chestnut_is_not_night(self):
        assert fc.time_of_day_words("군밤을 먹었다") == [] or all(w != "밤" for w, _, _ in fc.time_of_day_words("밤을 줍는 체험"))


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
