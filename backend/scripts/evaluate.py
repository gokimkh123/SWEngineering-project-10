"""AI 평가 스크립트 — 방문지 단위 장소 매칭 정확도와 후보 포함률 (NFR-02, AC-04, AIR-08).

정확도 = AI 1순위가 정답인 방문지 ÷ 평가셋 전체 방문지 (목표 80% 이상)
후보 포함률 = 정답이 후보 목록에 들어온 방문지 ÷ 전체 방문지 (목표 90% 이상) → 검색(CP-10)과 판별(CP-11) 중 원인 구분

사용: python scripts/evaluate.py [사진 폴더]   (폴더에 labels.json 필요, 기본: var/demo_photos)
labels.json 형식은 scripts/make_demo_photos.py 출력과 같다. 팀 촬영 평가셋(DR-07d)도 같은 형식으로 만든다.
VLM_PROVIDER=ollama 등으로 실제 모델을 지정하면 그 모델로 측정한다. 프롬프트 버전이 결과에 함께 찍힌다.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("FAKE_AI_LATENCY", "0")
os.environ.setdefault("DATA_DIR", str(Path(__file__).resolve().parent.parent / "var" / "eval"))

from app.adapters.cp19_ai_gateway import VLM_MATCH_PROMPT, ai_gateway  # noqa: E402
from app.components import cp08_exif, cp09_clusterer  # noqa: E402
from app.components.cp11_matcher import route  # noqa: E402
from app.models import SessionLocal, init_db  # noqa: E402
from app.services import finder, matcher  # noqa: E402


def main(folder: Path) -> None:
    labels = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
    init_db()
    photos = {p["file"]: p for p in labels["photos"] if p["has_gps"]}
    points, images = [], {}
    for name in photos:
        data = (folder / name).read_bytes()
        meta = cp08_exif.extract_meta(data)
        points.append(cp09_clusterer.PhotoPoint(name, meta.taken_at, meta.lat, meta.lng))
        images[name] = cp08_exif.make_vlm_image(data)
    clusters = cp09_clusterer.cluster_photos(points).visits

    rows, correct, included = [], 0, 0
    statuses: Counter = Counter()
    with SessionLocal() as db:
        for v in clusters:
            # 정답: 방문지에 묶인 사진들의 라벨 다수결
            truth = Counter(photos[pid]["place_id"] for pid in v.photo_ids).most_common(1)[0][0]
            cands, radius = finder.find(db, v.center_lat, v.center_lng)
            vlm_cands = [{"place_id": c.place_id, "name": c.record.name, "type": c.record.type,
                          "distance_m": round(c.distance_m), "overview": c.record.overview} for c in cands]
            answer, err = matcher.ask(images[v.rep_photo_id], vlm_cands) if cands else (None, "후보 없음")
            status = route(answer)
            statuses[status.value] += 1
            hit = answer is not None and answer.place_id == truth
            inc = any(c.place_id == truth for c in cands)
            correct += hit
            included += inc
            rows.append((v.order, truth, answer.place_id if answer else None, answer.confidence if answer else None,
                         status.value, "O" if hit else "X", "O" if inc else "X", err or ""))

    n = len(clusters)
    print(f"평가셋: {folder} · 방문지 {n}곳 · VLM {ai_gateway.info()['vlm_model']} · 프롬프트 {VLM_MATCH_PROMPT}")
    print(f"{'#':>2} {'정답':<14} {'AI 1순위':<14} {'확신도':>6} {'상태':<6} 정답 포함 비고")
    for r in rows:
        conf = f"{r[3]:.2f}" if r[3] is not None else "-"
        print(f"{r[0]:>2} {str(r[1] or '없음'):<14} {str(r[2] or 'none'):<14} {conf:>6} {r[4]:<6} {r[5]:^4} {r[6]:^4} {r[7]}")
    print(f"\n방문지 단위 정확도: {correct}/{n} = {correct / n:.0%} (목표 80%)")
    print(f"정답 후보 포함률:   {included}/{n} = {included / n:.0%} (목표 90%)")
    print("상태 분포:", dict(statuses))
    if labels.get("scripted"):
        print("※ 실제 사진 시연 세트(import_demo_photos.py)는 촬영 시각·위치와 정답을 임의로 정한 세트다. "
              "평가에서는 미리 정한 응답(vlm_replay.json)을 쓰지 않지만, 정답 자체가 각색이라 NFR-02 근거가 될 수 없다.")
    if ai_gateway.info()["vlm_provider"] == "fake":
        print("※ 모의 VLM 결과는 흐름 확인용이며 NFR-02 판정에 쓰지 않는다. 실제 모델(VLM_PROVIDER=ollama)과 팀 촬영 평가셋으로 측정할 것.")


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "var" / "demo_photos"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
