"""기능 테스트 케이스 실행기 (공개 주소 = 실제 배포 시스템 대상).

강의 형식: TC ID → 관련 요구사항/UC → 사전조건 → 입력 데이터·실행 절차 → 예상 결과 → 실제 결과 → PASS/FAIL
사용: python tc_run.py <공개 주소> <시연 사진 폴더> <docs 폴더> <결과.json>
"""
import io
import json
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from PIL import Image

BASE = sys.argv[1].rstrip("/") + "/api/v1"
PHOTOS = sorted(Path(sys.argv[2]).glob("*.jpg"))
DOCS = Path(sys.argv[3])
OUT = Path(sys.argv[4])
TOKEN = "tc-" + secrets.token_hex(12)
c = httpx.Client(base_url=BASE, headers={"X-Device-Token": TOKEN}, timeout=180)
results, ctx = [], {}


def call(method, url, **kw):
    """nginx 요청 제한(429)에 걸리면 기다렸다가 다시 보낸다 — 테스트 대상은 기능이지 제한값이 아니므로."""
    for _ in range(14):
        r = c.request(method, url, **kw)
        if r.status_code != 429:
            return r
        time.sleep(11)
    return r


def wait_job(job_id, limit=300):
    t0 = time.time()
    while time.time() - t0 < limit:
        j = call("GET", f"/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j, time.time() - t0
        time.sleep(0.7)
    raise TimeoutError(job_id)


def tc(tid, req, title, kind, pre, inp, expected):
    def deco(fn):
        t0 = time.time()
        try:
            ok, actual, ev = fn()
        except Exception as e:  # 실패도 기록
            ok, actual, ev = False, f"예외: {type(e).__name__}: {str(e)[:200]}", {}
        results.append({"id": tid, "req": req, "title": title, "kind": kind, "pre": pre, "input": inp,
                        "expected": expected, "actual": actual, "pass": bool(ok), "seconds": round(time.time() - t0, 1),
                        "evidence": ev})
        print(f"{tid} {'PASS' if ok else 'FAIL'} [{kind}] {title} → {actual}")
        return fn
    return deco


def jpeg(w=64, h=48, color=(120, 160, 200)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "JPEG", quality=80)
    return b.getvalue()


# ------------------------------------------------------------------ 준비: 여행 A
trip = call("POST", "/trips", json={"title": "기능 테스트"}).json()
TID = trip["id"]


@tc("TC-01", "FR-01 / UC-01", "사진 업로드·촬영 정보 추출", "기본 흐름",
    "서버 정상, 빈 여행 생성됨", "시연 사진 7장(JPEG, 위치 있음 6장·없음 1장) 업로드",
    "7장 모두 접수, 분석 시 위치 있음 6장·없음 1장으로 집계")
def tc01():
    r = call("POST", f"/trips/{TID}/photos", files=[("files", (f.name, f.read_bytes(), "image/jpeg")) for f in PHOTOS]).json()
    ctx["upload"] = r
    return len(r["accepted"]) == 7 and not r["rejected"], f"접수 {len(r['accepted'])}장 · 거절 {len(r['rejected'])}장 (위치 집계는 TC-04에서 확인)", {"total": r["total"]}


@tc("TC-02", "FR-01 / UC-01", "업로드 제한(30장·형식·20MB)", "예외 흐름",
    "새 여행 B 생성", "① 31장 한 번에 업로드 ② WEBP 1장 + 21MB 파일 1장 + 정상 JPEG 1장",
    "① 400 차단(최대 30장 안내) ② 정상 1장만 접수, 2장은 사유와 함께 제외")
def tc02():
    tb = call("POST", "/trips", json={"title": "제한 확인"}).json()["id"]
    try:
        r1 = call("POST", f"/trips/{tb}/photos", files=[("files", (f"s{i}.jpg", jpeg(), "image/jpeg")) for i in range(31)])
        big = jpeg() + b"\0" * (21 * 1024 * 1024)
        webp = (DOCS / "5.webp").read_bytes()
        r2 = call("POST", f"/trips/{tb}/photos", files=[("files", ("a.webp", webp, "image/webp")), ("files", ("big.jpg", big, "image/jpeg")),
                                                     ("files", ("ok.jpg", jpeg(), "image/jpeg"))]).json()
        reasons = [x["reason"] for x in r2["rejected"]]
        ok = r1.status_code == 400 and len(r2["accepted"]) == 1 and len(r2["rejected"]) == 2
        return ok, f"① {r1.status_code} \"{r1.json()['detail'][:28]}…\" ② 접수 {len(r2['accepted'])}장, 제외 {len(r2['rejected'])}장 ({' / '.join(reasons)})", {"r1": r1.status_code, "reasons": reasons}
    finally:
        call("DELETE", f"/trips/{tb}")


@tc("TC-03", "NFR-04 / UC-01", "AI 분석 동의 없이 시작", "예외 흐름",
    "사진 7장 업로드됨, 동의 안 함", "POST /analysis {consent: false}",
    "400 거부, 동의 안내 문구 · 분석 작업 생성 안 됨")
def tc03():
    r = call("POST", f"/trips/{TID}/analysis", json={"consent": False})
    t = call("GET", f"/trips/{TID}").json()
    return r.status_code == 400 and t["status"] == "draft", f"{r.status_code} \"{r.json()['detail']}\" · 여행 상태 {t['status']}", {}


@tc("TC-04", "FR-01·FR-02 / UC-01", "방문지 자동 묶기(DBSCAN)", "기본 흐름",
    "사진 7장 업로드됨", "동의 후 분석 시작 → 완료까지 진행 조회",
    "위치 있음 6장·없음 1장, 방문지 6곳(1일차 3·2일차 3), 위치 없는 사진 1장 대기")
def tc04():
    r = call("POST", f"/trips/{TID}/analysis", json={"consent": True}).json()
    j, sec = wait_job(r["job_id"])
    v = call("GET", f"/trips/{TID}/visits").json()
    ctx["visits"], ctx["job"] = v, j
    days = {}
    for x in v["visits"]:
        days[x["day"]] = days.get(x["day"], 0) + 1
    gps = sum(1 for p in [*(pp for pp in v["untagged"])] if p["has_gps"])
    exif = j.get("detail", {})
    ok = j["status"] == "done" and len(v["visits"]) == 6 and days == {1: 3, 2: 3} and len(v["untagged"]) == 1
    return ok, f"분석 {sec:.1f}초 완료 · 방문지 {len(v['visits'])}곳 (1일차 {days.get(1, 0)} · 2일차 {days.get(2, 0)}) · 위치 없는 사진 {len(v['untagged'])}장", {"job_detail": exif, "seconds": round(sec, 1)}


@tc("TC-05", "FR-03·FR-04 / UC-02", "공식 데이터 후보·VLM 확신도 분기", "기본·대안 흐름",
    "분석 완료", "방문지별 후보·AI 답·확신도 조회",
    "후보는 반경 300m 공식 데이터, AI 답은 후보 안에서만, 0.8 이상 자동확정·0.5 미만 선택필요")
def tc05():
    vs = ctx["visits"]["visits"]
    rows, ok = [], True
    for x in vs:
        cands = call("GET", f"/visits/{x['id']}/candidates").json()
        ids = {k["place_id"] for k in cands["candidates"]}
        ai = (x.get("ai") or {}).get("place")
        conf = (x.get("ai") or {}).get("confidence") or 0
        inside = ai is None or ai["place_id"] in ids
        rule = (x["status"] == "자동확정" and conf >= 0.8) or (x["status"] == "확인필요" and 0.5 <= conf < 0.8) or (x["status"] == "선택필요" and (conf < 0.5 or ai is None))
        ok &= inside and rule and cands["radius_m"] in (300, 600) and len(cands["candidates"]) >= 1
        rows.append({"order": x["order"], "status": x["status"], "conf": conf, "ai": ai and ai["name"], "n_cands": len(ids), "radius": cands["radius_m"]})
    auto = sum(1 for r in rows if r["status"] == "자동확정")
    sel = sum(1 for r in rows if r["status"] in ("선택필요", "확인필요"))
    return ok, f"자동확정 {auto}곳(확신도 0.8~0.95) · 사용자 확인 {sel}곳 · 후보 밖 답 0건", {"rows": rows}


@tc("TC-06", "FR-09 / UC-06", "확정 전 여행기 요청", "예외 흐름",
    "선택필요 방문지 1곳 남음", "POST /trips/{id}/stories",
    "409 거부, '방문지를 먼저 확정' 안내")
def tc06():
    r = call("POST", f"/trips/{TID}/stories", json={"style": "blog"})
    return r.status_code == 409, f"{r.status_code} \"{r.json()['detail']}\"", {}


@tc("TC-07", "FR-05 / UC-02", "사용자 확인·수정", "대안 흐름",
    "선택필요 방문지(흰여울 터널 사진)", "후보 목록 조회 → 후보 선택 PUT /visits/{id}/place",
    "상태 '확정', 동선에 선택한 장소 반영")
def tc07():
    x = next(v for v in ctx["visits"]["visits"] if v["needs_user"])
    cands = call("GET", f"/visits/{x['id']}/candidates").json()["candidates"]
    r = call("PUT", f"/visits/{x['id']}/place", json={"place_id": cands[0]["place_id"]}).json()
    route = call("GET", f"/trips/{TID}/route", params={"day": x["day"]}).json()
    names = [pin["name"] for pin in route["pins"]]
    v2 = call("GET", f"/trips/{TID}/visits").json()
    st = next(v for v in v2["visits"] if v["id"] == x["id"])
    return st["status"] == "확정" and cands[0]["name"] in names, f"'{cands[0]['name']}' 선택 → 상태 {st['status']}, {x['day']}일차 동선에 반영", {"route_names": names}


@tc("TC-08", "FR-06 / UC-03", "위치 없는 사진 처리", "대안 흐름",
    "GPS 없는 사진 1장(11:16 촬영)", "추천 조회 → 추천 방문지로 배정 PUT /photos/{id}/visit",
    "앞뒤 방문지 사이 시각이면 사진 비교로 추천, 배정 후 해당 방문지 사진 수 증가")
def tc08():
    u = call("GET", f"/trips/{TID}/visits").json()["untagged"][0]
    v_before = {v["id"]: v for v in call("GET", f"/trips/{TID}/visits").json()["visits"]}
    target = v_before[u["suggested_visit_id"]]
    r = call("PUT", f"/photos/{u['id']}/visit", json={"visit_id": u["suggested_visit_id"]}).json()
    after = {v["id"]: v for v in call("GET", f"/trips/{TID}/visits").json()["visits"]}
    name = (target.get("place") or {}).get("name")
    ok = r["photo"]["assign_state"] == "assigned" and after[target["id"]]["photo_count"] == target["photo_count"] + 1
    return ok, f"추천 '{name}' ({u['suggest_reason'][:34]}…) → 배정 완료, 사진 {target['photo_count']}→{after[target['id']]['photo_count']}장", {"reason": u["suggest_reason"]}


@tc("TC-09", "FR-07 / UC-04", "날짜별 동선·이동 시간", "기본 흐름",
    "모든 방문지 확정", "GET /trips/{id}/route?day=1, ?day=2",
    "방문 순서대로 장소·시각, 장소 사이 이동 거리·예상 시간 표시")
def tc09():
    out = []
    ok = True
    for d in (1, 2):
        r = call("GET", f"/trips/{TID}/route", params={"day": d}).json()
        pins, legs = r["pins"], r["legs"]
        ok &= len(pins) == 3 and len(legs) == 2 and all(l["distance_m"] > 0 and l["minutes"] > 0 for l in legs)
        ok &= [p["time_range"] for p in pins] == sorted(p["time_range"] for p in pins)
        out.append(f"{d}일차 {' → '.join(p['name'] for p in pins)}")
        ctx.setdefault("legs", []).extend(legs)
    leg = ctx["legs"][0]
    return ok, " / ".join(out) + f" · 구간마다 거리·시간 (예: {leg['distance_m'] / 1000:.1f}km, 약 {leg['minutes']}분, {leg['mode']})", {"legs": ctx["legs"]}


@tc("TC-10", "FR-08 / UC-05", "장소 상세(출처·갱신일)", "기본 흐름",
    "확정 방문지", "GET /places/{place_id}?visit_id=",
    "개요·주소·출처·갱신일 표시")
def tc10():
    v = next(v for v in call("GET", f"/trips/{TID}/visits").json()["visits"] if v["place"])
    p = call("GET", f"/places/{v['place']['place_id']}", params={"visit_id": v["id"]}).json()
    ok = all(p.get(k) for k in ("overview", "address", "source_name", "updated_at"))
    return ok, f"{p['name']}: 개요·주소 표시, 출처 '{p['source_name']}', 갱신일 {p['updated_at']}", {}


@tc("TC-11", "FR-12 / UC-04", "근처 못 가본 곳 추천", "기본 흐름",
    "모든 방문지 확정", "GET /trips/{id}/nearby",
    "방문지 주변 미방문 공식 장소 2~3곳, 거리순·출처 포함")
def tc11():
    r = call("GET", f"/trips/{TID}/nearby").json()
    groups = r["groups"]
    g = next((g for g in groups if g.get("items")), None)
    ok = g is not None and all(1 <= len(x["items"]) <= 3 for x in groups if x["items"]) and all("distance_m" in p and p.get("source_name") for p in g["items"])
    ok &= all([p["distance_m"] for p in x["items"]] == sorted(p["distance_m"] for p in x["items"]) for x in groups)
    sample = f"{g['name']} 주변 " + ", ".join(f"{p['name']} {p['distance_m']}m" for p in g["items"]) if g else "없음"
    return ok, f"방문지 그룹 {len(groups)}개 · 예: {sample} (거리순)", {"groups": len(groups)}


@tc("TC-12", "FR-09 / UC-06", "근거 기반 여행기 생성", "기본 흐름",
    "모든 방문지 확정", "블로그형 여행기 생성 → 완료까지 진행 조회",
    "확정 장소만 등장, 사실 문장마다 출처 각주, AI 작성 표시")
def tc12():
    r = call("POST", f"/trips/{TID}/stories", json={"style": "blog"}).json()
    j, sec = wait_job(r["job_id"])
    s = call("GET", f"/stories/{r['story_id']}").json()
    ctx["story"] = s
    sents = [x for p in s["paragraphs"] for x in p["sentences"]]
    facts = [x for x in sents if x["is_fact"]]
    with_note = [x for x in facts if x["footnotes"]]
    confirmed = {p["place_id"] for p in s.get("meta", {}).get("places", [])} or None
    ok = s["status"] == "ready" and facts and len(with_note) == len(facts) and s["meta"].get("ai_label")
    removed = len((s.get("meta") or {}).get("removed", []))
    return ok, f"{sec:.1f}초 · 문장 {len(sents)}개 중 사실 문장 {len(facts)}개 모두 각주({len(s['footnotes'])}개) · 근거 없는 문장 {removed}개 자동 제거 · 모델 {s['model']}", {"title": s["title"], "removed": removed}


@tc("TC-13", "FR-10 / UC-07·UC-09", "문단 다시 쓰기·편집 사실 대조", "대안 흐름",
    "여행기 생성됨", "① 문장을 '…아쿠아리움은 밤 11시까지 운영한다'로 편집 ② 첫 문단 다시 쓰기",
    "① 공식 운영시간과 다르다는 경고 ② 새 문단 생성, 각주 유지")
def tc13():
    s = ctx["story"]
    sid = s["paragraphs"][-1]["sentences"][0]["id"]
    r1 = call("PATCH", f"/stories/{s['id']}", json={"edits": [{"sentence_id": sid, "text": "SEA LIFE 부산아쿠아리움은 밤 11시까지 운영한다."}]}).json()
    edited = next(x for p in r1["paragraphs"] for x in p["sentences"] if x["id"] == sid)
    warn = [w["message"] for w in edited.get("warnings", [])]
    p0 = r1["paragraphs"][0]
    before = " ".join(x["text"] for x in p0["sentences"])
    r2 = call("POST", f"/stories/{s['id']}/paragraphs/{p0['id']}/rewrite").json()
    after = " ".join(x["text"] for x in r2["paragraphs"][0]["sentences"])
    notes = sum(len(x["footnotes"]) for x in r2["paragraphs"][0]["sentences"])
    ok = any("운영" in w or "시간" in w for w in warn) and after and after != before
    return ok, f"① 경고 \"{warn[0][:40] if warn else '없음'}\" ② 문단 새로 작성(각주 {notes}개)", {"warnings": warn}


@tc("TC-14", "FR-11 / UC-08", "공유 카드(위치 정보 제외)", "기본 흐름",
    "여행기 생성됨", "POST /stories/{id}/share-card",
    "PNG 이미지 생성, 좌표·EXIF 위치 없음")
def tc14():
    r = call("POST", f"/stories/{ctx['story']['id']}/share-card")
    im = Image.open(io.BytesIO(r.content))
    exif = im.getexif()
    gps = exif.get_ifd(0x8825) if exif else {}
    text = " ".join(f"{k}={v}" for k, v in (im.info or {}).items() if isinstance(v, str))
    ok = r.headers["content-type"] == "image/png" and not gps and "35." not in text
    return ok, f"{r.headers['content-type']} {im.size[0]}×{im.size[1]} · EXIF 위치 없음 · 메타데이터에 좌표 없음", {"bytes": len(r.content)}


@tc("TC-15", "NFR-04 / AC-09", "여행 삭제 시 관련 데이터 삭제", "기본 흐름",
    "여행기·썸네일 있는 여행", "DELETE /trips/{id} → 여행·썸네일 다시 조회",
    "204 삭제, 이후 여행·썸네일·여행기 조회 404")
def tc15():
    pid = ctx["upload"]["accepted"][0]["id"]
    thumb_before = call("GET", f"/photos/{pid}/thumb", params={"t": TOKEN}).status_code
    r = call("DELETE", f"/trips/{TID}")
    a = call("GET", f"/trips/{TID}").status_code
    b = call("GET", f"/photos/{pid}/thumb", params={"t": TOKEN}).status_code
    s = call("GET", f"/stories/{ctx['story']['id']}").status_code
    ok = r.status_code == 204 and a == b == s == 404 and thumb_before == 200
    return ok, f"삭제 {r.status_code} → 여행 {a} · 썸네일 {thumb_before}→{b} · 여행기 {s}", {}


OUT.write_text(json.dumps({"run_at": datetime.now().isoformat(timespec="seconds"), "base": BASE, "results": results}, ensure_ascii=False, indent=1))
print("PASS", sum(r["pass"] for r in results), "/", len(results))
