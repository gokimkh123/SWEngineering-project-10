"""비기능 측정 (worker 컨테이너 안에서 api:8000 직접 호출 — nginx 요청 제한을 거치지 않는 서버 성능 측정).

A. NFR-01: 사진 20장 분석 10회 (분석 시작 → 완료) + 매 회 여행기 생성 시간 (NFR-03 출처 표시율 집계)
B. NFR-04: 분석 후 원본 사진·좌표 잔존, 썸네일 EXIF 위치, 삭제 후 잔존 확인
C. 동시 분석 부하: 1·2·4건 동시 (처리량·응답시간)
D. API 읽기 부하: 동시 10·50·100 연결 (처리량·p50·p95·오류율)
결과: /tmp/nfr/result.json
"""
import asyncio
import io
import json
import secrets
import statistics
import sys
import threading
import time
from pathlib import Path

import httpx
from PIL import Image

B = "http://api:8000/api/v1"
PH = sorted(Path("/tmp/nfr").glob("*.jpg"))
OUT = Path("/tmp/nfr/result.json")
R = {"photos": len(PH), "phases": {}}
STYLES = ["blog", "diary", "brief"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def client(tag):
    return httpx.Client(base_url=B, headers={"X-Device-Token": f"nfr-{tag}-" + secrets.token_hex(8)}, timeout=300)


def wait_job(c, job_id, poll=0.25):
    t0 = time.time()
    while True:
        j = c.get(f"/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j, time.time() - t0
        time.sleep(poll)


def analyze(c, title="nfr"):
    t = c.post("/trips", json={"title": title}).json()["id"]
    t0 = time.time()
    up = c.post(f"/trips/{t}/photos", files=[("files", (p.name, p.read_bytes(), "image/jpeg")) for p in PH]).json()
    t_up = time.time() - t0
    job = c.post(f"/trips/{t}/analysis", json={"consent": True}).json()["job_id"]
    j, t_an = wait_job(c, job)
    v = c.get(f"/trips/{t}/visits").json()
    return t, {"upload_s": round(t_up, 2), "analysis_s": round(t_an, 2), "status": j["status"], "visits": len(v["visits"]),
               "auto": sum(1 for x in v["visits"] if x["status"] == "자동확정"),
               "needs_user": sum(1 for x in v["visits"] if x["needs_user"]), "untagged": len(v["untagged"]),
               "accepted": len(up["accepted"])}, v


def confirm_all(c, t, v):
    for x in v["visits"]:
        if x["needs_user"]:
            cands = c.get(f"/visits/{x['id']}/candidates").json()["candidates"]
            body = {"place_id": cands[0]["place_id"]} if cands else {"other": True}
            c.put(f"/visits/{x['id']}/place", json=body).raise_for_status()
    for u in v["untagged"]:
        if u["assign_state"] == "pending":
            body = {"visit_id": u["suggested_visit_id"]} if u.get("suggested_visit_id") else {"skip": True}
            c.put(f"/photos/{u['id']}/visit", json=body).raise_for_status()


def story(c, t, style):
    r = c.post(f"/trips/{t}/stories", json={"style": style}).json()
    j, sec = wait_job(c, r["job_id"])
    s = c.get(f"/stories/{r['story_id']}").json()
    sents = [x for p in s["paragraphs"] for x in p["sentences"]]
    facts = [x for x in sents if x["is_fact"]]
    # 11/25부터 문단마다 작성 방식(source: llm·template)이 기록됨 → 문단 단위로 LLM·템플릿을 센다 (D-04 재측정)
    src = [p.get("source", "template" if s["model"].startswith("템플릿") else "llm") for p in s["paragraphs"]]
    by_src = {k: [x for p, ps in zip(s["paragraphs"], src) if ps == k for x in p["sentences"] if x["is_fact"]] for k in ("llm", "template")}
    return s, {"style": style, "story_s": round(sec, 2), "status": s["status"], "model": s["model"], "sentences": len(sents),
               "facts": len(facts), "facts_with_note": sum(1 for x in facts if x["footnotes"]),
               "removed": len((s.get("meta") or {}).get("removed", [])), "footnotes": len(s["footnotes"]),
               "paragraphs": len(src), "llm_paragraphs": src.count("llm"), "template_paragraphs": src.count("template"),
               "facts_llm": len(by_src["llm"]), "facts_llm_noted": sum(1 for x in by_src["llm"] if x["footnotes"]),
               "facts_template": len(by_src["template"]), "facts_template_noted": sum(1 for x in by_src["template"] if x["footnotes"]),
               "removed_reasons": [r.get("reasons") for r in (s.get("meta") or {}).get("removed", [])]}


# ------------------------------------------------------------------ A + B
log("A: 20장 x 10회")
runs = []
c = client("a")
for i in range(10):
    t, row, v = analyze(c, f"nfr-{i}")
    if i == 0:  # B. 개인정보 잔존 확인 (분석 직후)
        sys.path.insert(0, "/srv/backend")
        from app.models import Photo, SessionLocal  # noqa: E402
        from app.components.cp17_media_store import media_store  # noqa: E402
        with SessionLocal() as db:
            photos = db.query(Photo).filter(Photo.trip_id == t).all()
            coords_left = sum(1 for p in photos if p.lat is not None or p.lng is not None)
            ids = [p.id for p in photos]
        originals_left = media_store.remaining_originals(t)
        gps_in_thumbs = 0
        for pid in ids:
            data = c.get(f"/photos/{pid}/thumb", params={"t": c.headers["X-Device-Token"]}).content
            ex = Image.open(io.BytesIO(data)).getexif()
            gps_in_thumbs += 1 if ex and ex.get_ifd(0x8825) else 0
        R["privacy"] = {"photos": len(ids), "originals_left": originals_left, "coords_left": coords_left, "gps_in_thumbs": gps_in_thumbs}
    confirm_all(c, t, v)
    s, srow = story(c, t, STYLES[i % 3])
    row.update(srow)
    runs.append(row)
    log(f"run {i + 1}: 업로드 {row['upload_s']}s 분석 {row['analysis_s']}s 방문지 {row['visits']} 자동 {row['auto']} · 여행기 {srow['story_s']}s 사실 {srow['facts_with_note']}/{srow['facts']} 제거 {srow['removed']} · 문단 LLM {srow['llm_paragraphs']}/{srow['paragraphs']} · {srow['model']}")
    if i == 0:
        c.delete(f"/trips/{t}")
        with SessionLocal() as db:
            left_rows = db.query(Photo).filter(Photo.trip_id == t).count()
        thumbs_left = sum(1 for pid in ids if media_store.thumb_path(pid).exists())
        R["privacy"].update({"after_delete_rows": left_rows, "after_delete_thumbs": thumbs_left})
        log("privacy", R["privacy"])
    else:
        c.delete(f"/trips/{t}")
an = [r["analysis_s"] for r in runs]
st = [r["story_s"] for r in runs]
R["phases"]["nfr01"] = {"runs": runs, "analysis_avg": round(statistics.mean(an), 2), "analysis_max": max(an), "analysis_min": min(an),
                        "story_avg": round(statistics.mean(st), 2), "story_max": max(st)}
log("NFR-01 평균", R["phases"]["nfr01"]["analysis_avg"], "최대", max(an), "여행기 평균", R["phases"]["nfr01"]["story_avg"])
OUT.write_text(json.dumps(R, ensure_ascii=False, indent=1))

# ------------------------------------------------------------------ C. 동시 분석
conc = []
for n in (1, 2, 4):
    log(f"C: 동시 분석 {n}건 시작")
    out, threads = [None] * n, []

    def worker(k):
        cc = client(f"c{n}{k}")
        t, row, _ = analyze(cc, f"conc{n}-{k}")
        out[k] = row
        cc.delete(f"/trips/{t}")

    t0 = time.time()
    for k in range(n):
        th = threading.Thread(target=worker, args=(k,))
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    span = time.time() - t0
    times = [o["analysis_s"] for o in out]
    conc.append({"n": n, "makespan_s": round(span, 2), "per_job": times, "avg_s": round(statistics.mean(times), 2),
                 "max_s": max(times), "photos_per_min": round(n * len(PH) / span * 60, 1), "start": t0, "end": time.time()})
    log(f"C: {n}건 → 평균 {conc[-1]['avg_s']}s 최대 {max(times)}s 처리량 {conc[-1]['photos_per_min']}장/분")
    time.sleep(3)
R["phases"]["concurrency"] = conc
OUT.write_text(json.dumps(R, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ D. API 읽기 부하
async def load(n, seconds, path, token):
    lat, errs = [], 0
    stop = time.time() + seconds
    async with httpx.AsyncClient(base_url=B, headers={"X-Device-Token": token}, timeout=30,
                                 limits=httpx.Limits(max_connections=n, max_keepalive_connections=n)) as ac:
        async def one():
            nonlocal errs
            while time.time() < stop:
                t0 = time.perf_counter()
                try:
                    r = await ac.get(path)
                    if r.status_code != 200:
                        errs += 1
                except Exception:
                    errs += 1
                lat.append((time.perf_counter() - t0) * 1000)
        t0 = time.time()
        await asyncio.gather(*[one() for _ in range(n)])
        dur = time.time() - t0
    lat.sort()
    q = lambda p: round(lat[min(len(lat) - 1, int(len(lat) * p))], 1)  # noqa: E731
    return {"conc": n, "path": path, "requests": len(lat), "rps": round(len(lat) / dur, 1), "p50_ms": q(0.5), "p95_ms": q(0.95),
            "p99_ms": q(0.99), "errors": errs, "error_rate": round(errs / max(1, len(lat)), 4)}

tok = "nfr-load-" + secrets.token_hex(8)
cl = httpx.Client(base_url=B, headers={"X-Device-Token": tok}, timeout=30)
for i in range(3):
    cl.post("/trips", json={"title": f"load-{i}"})
loadres = []
for path in ("/trips", "/meta"):
    for n in (10, 50, 100):
        t0 = time.time()
        res = asyncio.run(load(n, 8, path, tok))
        res.update({"start": t0, "end": time.time()})
        loadres.append(res)
        log("D:", res)
        time.sleep(2)
for t in cl.get("/trips").json():
    cl.delete(f"/trips/{t['id']}")
R["phases"]["api_load"] = loadres
OUT.write_text(json.dumps(R, ensure_ascii=False, indent=1))
log("끝")
