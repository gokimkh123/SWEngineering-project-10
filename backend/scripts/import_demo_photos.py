"""실제 사진으로 시연 세트를 만든다 (발표용, 임의 각색).

팀원이 올린 사진 9장(저장소 루트의 KakaoTalk_*.jpg)은 부산에서 찍은 사진이 아니다(담양·서울·경주·일본·중국, 2022~2025년).
그래서 부산 1박 2일(2026-02-07~08)에 찍은 것처럼 촬영 시각·위치를 아래 PLAN대로 임의로 정해 복사본에 새로 넣는다.

- 원본은 읽기만 한다. 복사본은 방향을 바로잡고(긴 변 2000px), 원래 EXIF(실제 GPS·기기 정보)를 모두 버린 뒤
  정해 둔 촬영 시각·좌표만 넣는다.
- 모의 VLM은 사진 내용을 알아보지 못하므로, 방문지 대표 사진에는 "실제 VLM이 낼 법한 답"을 사람이 정해 둔다
  (vlm_replay.json, CP-19 DemoReplay). 인식 결과가 아니므로 정확도 평가(NFR-02)에 쓰지 않는다.
- 누가 봐도 부산이 아닌 사진(광화문, 경주 동궁과 월지)은 부산 장소로 꾸미지 않는다.
  광화문 → 근처 후보와 맞지 않는다고 답하는 장면(선택필요 → 기타 장소), 동궁과 월지 → 촬영 정보가 없는 사진(직접 고르거나 제외).

사용: python scripts/import_demo_photos.py [--src 원본 폴더] [--out 출력 폴더] [--check]
      기본 원본: 저장소 루트, 기본 출력: backend/var/demo_photos (기존 시연 사진은 지운다)
      합성 세트로 되돌리기: python scripts/make_demo_photos.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.adapters.cp19_ai_gateway import REPLAY_FILE, image_ahash  # noqa: E402
from app.components import cp08_exif  # noqa: E402

MAX_SIDE = 2000

# 방문지: (라벨, 정답 장소 ID, 설명)
VISITS = [
    ("V1", "busan:B002", "1일차 오전 · 부산시민공원 (폭포)"),
    ("V2", "busan:B007", "1일차 오후 · 온천천시민공원 (산책로 + 위치 없는 벽 글귀 사진)"),
    ("V3", "tour:900119", "1일차 해 질 녘 · 다대포해수욕장"),
    ("V4", "tour:900122", "2일차 오전 · 금정산성 (확인필요: 확신도 0.66)"),
    ("V5", "tour:900123", "2일차 오후 · 아홉산숲"),
    ("V6", None, "2일차 오후 · 해동용궁사 근처에서 찍었다고 둔 광화문 사진 (AI: 맞는 후보 없음 → 선택필요)"),
    ("V7", "tour:900124", "2일차 밤 · 황령산 봉수대"),
]

# 사진: 원본 파일, 방문지, 촬영 시각(없으면 None), 좌표(없으면 None), 미리 정한 VLM 응답(대표 사진만)
PLAN = [
    {"src": "KakaoTalk_20261110_113558052_08.jpg", "visit": "V1", "taken": "2026-02-07 10:40", "gps": (35.16855, 129.05790),
     "answer": {"place_id": "busan:B002", "confidence": 0.88,
                "reason": "계단식으로 떨어지는 폭포와 데크 전망대, 둘레의 숲이 보여요. 도심 공원 풍경이라 촬영 위치에서 가장 가까운 부산시민공원과 잘 맞아요."}},
    {"src": "KakaoTalk_20261110_113558052_01.jpg", "visit": "V2", "taken": "2026-02-07 14:50", "gps": (35.19655, 129.08250),
     "answer": {"place_id": "busan:B007", "confidence": 0.86,
                "reason": "하천을 따라 난 나무 데크 산책로와 겨울 가로수가 보여요. 물길 옆 산책로라서 온천천시민공원과 잘 맞아요."}},
    {"src": "KakaoTalk_20261110_113558052_04.jpg", "visit": "V2", "taken": "2026-02-07 15:04", "gps": None, "answer": None},
    {"src": "KakaoTalk_20261110_113558052_02.jpg", "visit": "V3", "taken": "2026-02-07 17:48", "gps": (35.04700, 128.96450),
     "answer": {"place_id": "tour:900119", "confidence": 0.93,
                "reason": "수평선 위로 해가 지는 바다와 멀리 작은 섬이 보여요. 노을로 알려진 다대포해수욕장과 잘 맞아요."}},
    {"src": "KakaoTalk_20261110_113558052_07.jpg", "visit": "V4", "taken": "2026-02-08 11:20", "gps": (35.27590, 129.05690),
     "answer": {"place_id": "tour:900122", "confidence": 0.66,
                "reason": "산 능선과 겨울 숲이 내려다보이는 높은 곳이에요. 가장 가까운 후보인 금정산성으로 보이지만, 성벽이나 성문이 보이지 않아 확인이 필요해요."}},
    {"src": "KakaoTalk_20261110_113558052.jpg", "visit": "V5", "taken": "2026-02-08 14:10", "gps": (35.28580, 129.17620),
     "answer": {"place_id": "tour:900123", "confidence": 0.95,
                "reason": "굵은 대나무가 빽빽하게 자란 대숲이 보여요. 대나무 숲으로 이름난 아홉산숲과 잘 맞아요."}},
    {"src": "KakaoTalk_20261110_113558052_05.jpg", "visit": "V6", "taken": "2026-02-08 16:10", "gps": (35.18900, 129.22240),
     "answer": {"place_id": "none", "confidence": 0.15,
                "reason": "넓은 광장 뒤로 큰 목조 성문과 바위산이 보여요. 후보인 해동용궁사는 바닷가 바위 위의 사찰이라 풍경이 달라서, 맞는 후보가 없다고 판단했어요."}},
    {"src": "KakaoTalk_20261110_113558052_06.jpg", "visit": "V7", "taken": "2026-02-08 19:40", "gps": (35.15710, 129.08220),
     "answer": {"place_id": "tour:900124", "confidence": 0.90,
                "reason": "높은 곳에서 내려다본 넓은 도시 야경이에요. 도심 야경 전망지인 황령산 봉수대와 잘 맞아요."}},
    # 메신저로 받은 사진처럼 촬영 시각·위치가 모두 없는 사진 → 사용자가 직접 고르거나 제외
    {"src": "KakaoTalk_20261110_113558052_03.jpg", "visit": None, "taken": None, "gps": None, "answer": None},
]


def _dms(deg: float) -> tuple[float, float, float]:
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60)
    return (float(d), float(m), round((deg - d - m / 60) * 3600, 2))


def convert(src: Path, dst: Path, taken: datetime | None, gps: tuple[float, float] | None) -> None:
    with Image.open(src) as raw:
        icc = raw.info.get("icc_profile")
        im = ImageOps.exif_transpose(raw).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    exif = Image.Exif()  # 원본 EXIF는 하나도 옮기지 않는다
    if taken:
        stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
        exif[0x0132] = stamp
        sub = exif.get_ifd(0x8769)
        sub[0x9003] = stamp
        sub[0x9004] = stamp
    if gps:
        lat, lng = gps
        exif.get_ifd(0x8825).update({0: b"\x02\x03\x00\x00", 1: "N" if lat >= 0 else "S", 2: _dms(lat),
                                     3: "E" if lng >= 0 else "W", 4: _dms(lng)})
    kwargs = {"quality": 87, "exif": exif.tobytes()}
    if icc:
        kwargs["icc_profile"] = icc
    im.save(dst, "JPEG", **kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(description="실제 사진으로 시연 세트 만들기 (촬영 시각·위치 임의 각색)")
    ap.add_argument("--src", type=Path, default=BACKEND.parent)
    ap.add_argument("--out", type=Path, default=BACKEND / "var" / "demo_photos")
    ap.add_argument("--check", action="store_true", help="원본이 다 있는지만 확인 (없으면 종료 코드 2)")
    args = ap.parse_args()

    missing = [p["src"] for p in PLAN if not (args.src / p["src"]).exists()]
    if missing:
        print(f"원본 사진이 없어요 ({args.src}): {', '.join(missing)}", file=sys.stderr)
        return 2
    if args.check:
        return 0

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()

    labels, replay = [], []
    order = sorted(PLAN, key=lambda p: (p["taken"] is None, p["taken"] or ""))
    for n, p in enumerate(order, start=1):
        taken = datetime.strptime(p["taken"], "%Y-%m-%d %H:%M") if p["taken"] else None
        if taken is None:
            name = f"busan_{n:02d}_noinfo.jpg"
        else:
            name = f"busan_{n:02d}_{taken:%m%d_%H%M}{'' if p['gps'] else '_nogps'}.jpg"
        convert(args.src / p["src"], out / name, taken, p["gps"])
        data = (out / name).read_bytes()
        meta = cp08_exif.extract_meta(data)  # 넣은 값이 그대로 읽히는지 확인
        assert meta.taken_at == taken and meta.has_gps == bool(p["gps"]), name
        place_id = next((v[1] for v in VISITS if v[0] == p["visit"]), None)
        labels.append({"file": name, "visit": p["visit"], "place_id": place_id, "has_gps": bool(p["gps"]),
                       "taken_at": taken.isoformat() if taken else None, "original": p["src"]})
        if p["answer"]:
            replay.append({"file": name, "ahash": f"{image_ahash(cp08_exif.make_vlm_image(data)):064x}",
                           "answer": p["answer"]})
        print(f"  {name:<28} ← {p['src']}  ({p['visit'] or '방문지 없음'}, {(out / name).stat().st_size // 1024}KB)")

    (out / "labels.json").write_text(json.dumps({
        "note": "실제 사진 시연 세트 (촬영 시각·위치는 부산 여행처럼 임의로 정한 값). scripts/import_demo_photos.py가 만든다.",
        "scripted": True,
        "visits": [{"visit": v[0], "place_id": v[1], "desc": v[2],
                    "photos": sum(1 for p in PLAN if p["visit"] == v[0])} for v in VISITS],
        "photos": labels,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / REPLAY_FILE).write_text(json.dumps({
        "note": "모의 VLM이 시연 사진에 돌려줄 미리 정한 응답 (사람이 정한 값, 인식 결과 아님 · 정확도 평가에 쓰지 않음)",
        "photos": replay,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(order)}장 → {out} (미리 정한 VLM 응답 {len(replay)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
