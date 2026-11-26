"""최종 발표 시연 영상용 사진 세트 (docs/1~7 사진 → 촬영 정보를 넣은 복사본).

docs/1.jpg~7.jpg(5번은 webp)는 웹에서 받은 사진이라 EXIF(촬영 시각·GPS)가 없다.
시연을 위해 부산 1박 2일(2026-11-21~22)에 찍은 것처럼 시각·좌표를 임의로 정해 JPEG 복사본에 넣는다.
좌표는 sample_places.json의 해당 장소 좌표 근처. 원본은 읽기만 한다.

- 4.jpg(감천 전경)는 일부러 GPS를 빼고 시각만 넣는다 → '위치 없는 사진' 흐름(FR-06) 시연
사용: backend/.venv/bin/python docs/05-final/build/make_demo_set.py
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
from import_demo_photos import convert  # noqa: E402  (원본 EXIF는 버리고 시각·좌표만 새로 넣음)
from app.components import cp08_exif  # noqa: E402

PLAN = [  # 원본, 촬영 시각, GPS(없으면 None), 실제 장소
    ("3.jpg", "2026-11-21 10:12", (35.09762, 129.01048), "감천문화마을 골목"),
    ("4.jpg", "2026-11-21 11:16", None, "감천문화마을 전경 (위치 없음)"),
    ("5.webp", "2026-11-21 12:20", (35.07852, 129.04510), "흰여울 해안터널"),
    ("7.jpg", "2026-11-21 15:05", (35.10052, 129.12432), "오륙도 스카이워크"),
    ("1.jpg", "2026-11-22 10:40", (35.16058, 129.19226), "청사포 다릿돌전망대"),
    ("6.jpg", "2026-11-22 13:10", (35.15855, 129.16018), "해운대해수욕장"),
    ("2.jpg", "2026-11-22 15:00", (35.15962, 129.16118), "SEA LIFE 부산아쿠아리움"),
]

src_dir, out_dir = ROOT / "docs", Path(__file__).resolve().parents[1] / "demo_photos"
out_dir.mkdir(exist_ok=True)
for name, taken, gps, label in PLAN:
    dst = out_dir / (Path(name).stem + ".jpg")
    convert(src_dir / name, dst, datetime.strptime(taken, "%Y-%m-%d %H:%M"), gps)
    meta = cp08_exif.extract_meta(dst.read_bytes())
    print(f"{dst.name:6} {label:24} {meta.taken_at} gps={meta.lat, meta.lng} {dst.stat().st_size // 1024}KB")
