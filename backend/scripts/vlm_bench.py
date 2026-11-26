"""실제 VLM 비교 시험 — 같은 사진·같은 후보로 여러 Qwen 모델의 장소 판별과 여행기 글쓰기를 잰다.

사진마다 촬영 위치(시험용으로 지정)에서 실제 후보 검색(CP-10)을 돌리고, 파이프라인과 같은 축소 사진(CP-08)과
같은 프롬프트·검증(CP-11: closed-set, 1회 재요청)으로 묻는다. 기록: 정답 여부, 확신도와 라우팅, JSON 형식 오류,
응답 시간(첫 호출 = 모델 적재 포함), GPU 메모리. 여행기는 같은 사실 입력으로 쓰게 하고 사실 대조(CP-14)에서
살아남은 문장 비율을 본다. 정확도(NFR-02) 측정이 아니라 배포할 모델을 고르기 위한 작은 시험이다.

사용(도커 안, VLM 서버와 같은 망): python scripts/vlm_bench.py /bench/manifest.json qwen3.5:2b qwen3.5:4b qwen3.5:9b
manifest = [{"name", "image", "lat", "lng", "truth"(장소 ID 또는 "none")}]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATA_DIR"] = os.environ.get("BENCH_DATA_DIR", "/tmp/vlm-bench")  # 서비스 데이터 볼륨(/data)은 건드리지 않음
os.environ["DATABASE_URL"] = f"sqlite:///{os.environ['DATA_DIR']}/bench.db"
os.environ["VLM_PROVIDER"] = "ollama"
os.environ["LLM_PROVIDER"] = "ollama"

import httpx  # noqa: E402

from app.adapters.cp19_ai_gateway import ai_gateway  # noqa: E402
from app.components import cp08_exif, cp14_fact_checker as fc  # noqa: E402
from app.components.cp11_matcher import route  # noqa: E402
from app.components.cp13_story import StoryGenerator  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import SessionLocal, init_db  # noqa: E402
from app.services import finder, matcher, place_cache  # noqa: E402

STORY_PLACES = ["tour:900101", "tour:900102", "tour:900108"]  # 해운대 → 광안리 → 감천 (1일차)


def candidates(db, lat: float, lng: float) -> list[dict]:
    cands, _ = finder.find(db, lat, lng)
    out = []
    for c in cands:
        d = {"place_id": c.place_id, "name": c.record.name, "type": c.record.type, "distance_m": round(c.distance_m)}
        if c.record.source != "kakao":
            d["overview"] = c.record.overview
        out.append(d)
    return out


def vram_gb() -> float | None:
    try:
        ps = httpx.get(f"{settings.ollama_url}/api/ps", timeout=10).json().get("models", [])
        return round(sum(m.get("size_vram", 0) for m in ps) / 1e9, 2)
    except httpx.HTTPError:
        return None


def story_test(db) -> dict:
    """같은 확정 사실로 여행기를 쓰게 하고, 사실 대조에서 남은 문장 수를 센다."""
    facts, visits = {}, []
    for i, pid in enumerate(STORY_PLACES):
        rec = place_cache.resolve(db, pid)
        f = {k: v for k, v in {"name": rec.name, "type": rec.type, "address": rec.address, "overview": rec.overview,
                               "usetime": rec.usetime}.items() if v}
        facts[pid] = f
        visits.append({"order": i + 1, "day": 1, "date": "2026-10-10", "weekday": "토", "time_range": f"{10 + 3 * i}:00~{11 + 3 * i}:00",
                       "start_hour": 10 + 3 * i, "place_id": pid, "name": rec.name, "type": rec.type, "facts": f})
    payload = {"style": "blog", "trip": {"start_date": "2026-10-10", "end_date": "2026-10-10"}, "visits": visits}
    known = place_cache.known_names(db) | {f["name"]: pid for pid, f in facts.items()}
    t0 = time.time()
    try:
        data = StoryGenerator._parse(ai_gateway.llm_story(payload), story_level=True)
    except Exception as e:  # 형식 오류도 결과로 기록
        return {"ok": False, "error": str(e)[:120], "seconds": round(time.time() - t0, 1)}
    kept, removed, fact_kept, sample = 0, 0, 0, []
    for p in data["paragraphs"]:
        for s in p["sentences"]:
            res = fc.check_generated_sentence(s.get("text", ""), s.get("place_ids", []), s.get("fields", []), bool(s.get("is_fact")),
                                              facts, set(facts), known)
            if res.ok:
                kept += 1
                fact_kept += bool(res.is_fact)
                if len(sample) < 4:
                    sample.append(s.get("text", ""))
            else:
                removed += 1
    return {"ok": True, "seconds": round(time.time() - t0, 1), "kept": kept, "removed": removed, "fact_kept": fact_kept,
            "title": data.get("title"), "sample": sample}


def main() -> None:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    models = sys.argv[2:]
    Path(os.environ["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    init_db()
    results = {}
    with SessionLocal() as db:
        cases = []
        for m in manifest:
            data = Path(m["image"]).read_bytes()
            cases.append({**m, "jpeg": cp08_exif.make_vlm_image(data), "cands": candidates(db, m["lat"], m["lng"])})
        for model in models:
            settings.vlm_model = model
            settings.llm_model = model
            rows = []
            for i, c in enumerate(cases):
                t0 = time.time()
                ans, err = matcher.ask(c["jpeg"], c["cands"])
                dt = time.time() - t0
                got = (ans.place_id or "none") if ans else None
                rows.append({"name": c["name"], "truth": c["truth"], "got": got, "conf": ans.confidence if ans else None,
                             "status": route(ans).value, "ok": got == c["truth"], "error": err, "seconds": round(dt, 1),
                             "first": i == 0, "reason": ans.reason if ans else None, "n_cands": len(c["cands"])})
                print(f"[{model}] {c['name']:<22} 정답 {c['truth']:<12} 답 {str(got):<12} 확신도 {rows[-1]['conf']} "
                      f"{rows[-1]['status']} {dt:5.1f}s {'O' if rows[-1]['ok'] else 'X'} {err or ''}", flush=True)
            vram = vram_gb()
            story = story_test(db)
            print(f"[{model}] 여행기: {json.dumps(story, ensure_ascii=False)[:400]}", flush=True)
            warm = [r["seconds"] for r in rows if not r["first"]]
            results[model] = {
                "correct": sum(r["ok"] for r in rows), "n": len(rows),
                "json_errors": sum(1 for r in rows if r["error"]),
                "confident_wrong": sum(1 for r in rows if not r["ok"] and r["status"] == "자동확정"),
                "first_call_s": rows[0]["seconds"] if rows else None,
                "avg_s": round(sum(warm) / len(warm), 2) if warm else None,
                "vram_gb": vram, "story": story, "rows": rows,
            }
            # 다음 모델을 재기 전에 GPU에서 내림
            try:
                httpx.post(f"{settings.ollama_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
            except httpx.HTTPError:
                pass
    print("\n== 요약 ==")
    print(f"{'모델':<14} {'정답':>6} {'형식오류':>6} {'확신오답':>6} {'첫호출':>7} {'평균':>6} {'GPU':>6} 여행기(남은/지운 문장, 사실, 초)")
    for model, r in results.items():
        s = r["story"]
        st = f"{s.get('kept')}/{s.get('removed')}, {s.get('fact_kept')}, {s.get('seconds')}" if s.get("ok") else f"실패 {s.get('error')}"
        print(f"{model:<14} {r['correct']:>3}/{r['n']:<2} {r['json_errors']:>6} {r['confident_wrong']:>6} {r['first_call_s']:>6}s "
              f"{r['avg_s']:>5}s {r['vram_gb']:>5}GB {st}")
    out = Path(os.environ.get("BENCH_OUT", "/tmp/vlm-bench/result.json"))
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("결과:", out)


if __name__ == "__main__":
    main()
