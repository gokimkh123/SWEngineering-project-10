"""정확도 평가 (NFR-02·AC-04 대체 평가): 장소마다 사진 1장 → 후보 조회(CP-10) → VLM 판별(CP-11) → 정답 비교.

명세서의 평가 기준은 '팀 촬영 평가셋(방문지 20곳 이상)'이다. 이 평가는 그 대신 웹 공개 사진(위키미디어 공용, CC 라이선스)
27장에 촬영 위치(샘플 장소 좌표에서 임의 방향 0~100m)를 넣어 측정한다. 팀이 찍은 사진으로 바꿔 같은 방법으로 다시 잴 수 있다.

측정 값
- 정확도: AI 1순위 = 정답인 방문지 ÷ 전체 (목표 80%)
- 후보 포함률: 정답이 후보 목록에 든 방문지 ÷ 전체 (목표 90%) → 후보 조회(CP-10)와 판별(CP-11) 중 원인 구분
- 확신 오답: 확신도 0.8 이상인데 틀린 답 (사용자 확인 없이 잘못 확정되는 경우, 목표 0건)
- 같은 장소가 출처별로 따로 있으면(예: 감천문화마을 TourAPI·부산시) 이름이 같을 때 정답으로 본다

실행 (운영 DB를 쓰지 않게 SQLite·작업 큐 없이):
  docker compose run -d --rm --no-deps --name chalkak-eval -e DATABASE_URL= -e REDIS_URL= -e DATA_DIR=/tmp/evaldata worker sleep 3600
  (사진 폴더를 컨테이너 /tmp/evalset으로 복사) → docker exec -i chalkak-eval python - /tmp/evalset < vlm_eval.py
결과: <사진 폴더>/result.json
"""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("FAKE_AI_LATENCY", "0")
sys.path.insert(0, "/srv/backend")

from app.adapters.cp19_ai_gateway import VLM_MATCH_PROMPT, ai_gateway  # noqa: E402
from app.components import cp08_exif  # noqa: E402
from app.components.cp11_matcher import AUTO_THRESHOLD, route  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import SessionLocal, init_db  # noqa: E402
from app.services import finder, matcher  # noqa: E402

folder = Path(sys.argv[1])
labels = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
assert not settings.database_url.startswith("postgres"), "운영 DB에 연결하지 않도록 DATABASE_URL을 비워서 실행"
init_db()
rows, statuses = [], Counter()
t_all = time.time()
with SessionLocal() as db:
    for item in labels["photos"]:
        data = (folder / item["file"]).read_bytes()
        meta = cp08_exif.extract_meta(data)
        image = cp08_exif.make_vlm_image(data)
        cands, radius = finder.find(db, meta.lat, meta.lng)
        vlm_cands = [{"place_id": c.place_id, "name": c.record.name, "type": c.record.type,
                      "distance_m": round(c.distance_m), "overview": c.record.overview} for c in cands]
        t0 = time.time()
        answer, err = matcher.ask(image, vlm_cands) if cands else (None, "후보 없음")
        sec = time.time() - t0
        status = route(answer)
        statuses[status.value] += 1
        names = {c.place_id: c.record.name for c in cands}
        picked = answer.place_id if answer else None
        hit = picked is not None and (picked == item["place_id"] or names.get(picked) == item["name"])
        included = any(c.place_id == item["place_id"] or c.record.name == item["name"] for c in cands)
        conf = answer.confidence if answer else None
        rows.append({"file": item["file"], "truth": item["name"], "truth_id": item["place_id"], "offset_m": item["offset_m"],
                     "radius_m": radius, "candidates": [c.record.name for c in cands], "answer": names.get(picked, "없음" if answer else None),
                     "confidence": conf, "status": status.value, "correct": hit, "included": included,
                     "confident_wrong": bool(answer and picked and not hit and conf is not None and conf >= AUTO_THRESHOLD),
                     "reason": (answer.reason if answer else err or "")[:200], "vlm_s": round(sec, 2)})
        print(f"{item['file']}: 정답 {item['name']} · 후보 {len(cands)}곳 · AI {rows[-1]['answer']} ({conf}) · {status.value} · "
              f"{'O' if hit else 'X'}", flush=True)

n = len(rows)
auto = [r for r in rows if r["status"] == "자동확정"]
result = {
    "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "set": labels.get("note"), "gps_noise": labels.get("gps_noise"),
    "vlm_model": ai_gateway.info()["vlm_model"], "prompt": VLM_MATCH_PROMPT, "n": n,
    "correct": sum(r["correct"] for r in rows), "included": sum(r["included"] for r in rows),
    "confident_wrong": sum(r["confident_wrong"] for r in rows), "auto": len(auto), "auto_correct": sum(r["correct"] for r in auto),
    "statuses": dict(statuses), "elapsed_s": round(time.time() - t_all, 1), "rows": rows,
}
(folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n정확도 {result['correct']}/{n} = {result['correct'] / n:.1%} (목표 80%) · 후보 포함률 {result['included']}/{n} = "
      f"{result['included'] / n:.1%} (목표 90%) · 확신 오답 {result['confident_wrong']}건 · 자동확정 {len(auto)}곳 중 정답 {result['auto_correct']}")
