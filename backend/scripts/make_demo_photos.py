"""시연·테스트용 합성 사진 세트를 만든다 (요구사항분석서 9장 시연 시나리오 대응).

부산 1박 2일 사진 24장(위치 있음 21, 없음 3), 정답 방문지 6곳(1일차 5곳, 2일차 1곳).
실제 사진이 아니라 Pillow로 그린 장면 그림에 EXIF(촬영 시각·GPS)를 넣은 것이다.
팀 촬영 사진(DR-07d)으로 평가셋을 만들 때까지 흐름 시연·자동 테스트에 쓴다.

사용: python scripts/make_demo_photos.py [출력 폴더]   (기본: backend/var/demo_photos)
정답 라벨은 출력 폴더의 labels.json (방문지 묶기 AC-02, 정확도 평가 스크립트 입력 형식)
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1280, 960

# (라벨, 장면, 정답 장소 ID, 중심 좌표, 촬영 시각 목록)
VISITS = [
    ("V1", "beach", "tour:900101", (35.15845, 129.16005), ["2026-10-10 10:20", "10:28", "10:35", "10:44", "10:52"]),
    ("V2", "coast_train", "tour:900103", (35.15900, 129.17140), ["2026-10-10 11:35", "11:48", "12:00", "12:10"]),
    ("V3", "food", "kakao:S9001", (35.15790, 129.05960), ["2026-10-10 13:10", "13:22", "13:35"]),
    ("V4", "beach_late", "tour:900102", (35.15350, 129.11900), ["2026-10-10 17:20", "17:35", "17:48", "18:00"]),
    ("V5", "night_bridge", "busan:B001", (35.15550, 129.13310), ["2026-10-10 19:30", "19:38", "19:46"]),
    ("V6", "village", "tour:900108", (35.09740, 129.01040), ["2026-10-11 10:30", "11:15"]),
]
# 위치 없는 사진 (메신저로 받은 사진처럼 GPS가 지워진 경우) → 정답 방문지
UNTAGGED = [
    ("U1", "food_side", "V3", "2026-10-10 12:40"),
    ("U2", "beach_late", "V4", "2026-10-10 18:15"),
    ("U3", "village", "V6", "2026-10-11 10:50"),
]


def _grad(d: ImageDraw.ImageDraw, box, top, bottom):
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        d.line([(x0, y), (x1, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))


def _jit(rng, c, k=12):
    return tuple(max(0, min(255, v + rng.randint(-k, k))) for v in c)


def scene(kind: str, rng: random.Random) -> Image.Image:
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    if kind in ("beach", "beach_late"):
        late = kind == "beach_late"
        horizon = int(H * rng.uniform(0.38, 0.45))
        shore = int(H * rng.uniform(0.62, 0.68))
        _grad(d, (0, 0, W, horizon), _jit(rng, (120, 175, 235) if not late else (150, 180, 230)),
              _jit(rng, (190, 220, 245) if not late else (235, 215, 190)))
        # 건물 실루엣 (해운대) / 다리 (광안리)
        if not late:
            x = 0
            while x < W * 0.55:
                bw, bh = rng.randint(40, 90), rng.randint(60, 200)
                d.rectangle([x, horizon - bh, x + bw, horizon], fill=_jit(rng, (150, 160, 175)))
                x += bw + rng.randint(2, 12)
        else:
            y = horizon - 40
            d.line([(0, y + 20), (W, y + 5)], fill=(110, 115, 130), width=8)
            for px in (int(W * 0.3), int(W * 0.65)):
                d.rectangle([px - 8, y - 90, px + 8, y + 20], fill=(110, 115, 130))
                for k in range(-1, 2, 2):
                    d.line([(px, y - 90), (px + k * 220, y + 12)], fill=(130, 135, 150), width=3)
        _grad(d, (0, horizon, W, shore), _jit(rng, (40, 110, 190)), _jit(rng, (70, 150, 210)))
        for _ in range(14):
            y = rng.randint(horizon + 10, shore - 5)
            x = rng.randint(0, W)
            d.arc([x, y, x + rng.randint(60, 160), y + 14], 200, 340, fill=(220, 235, 250), width=3)
        _grad(d, (0, shore, W, H), _jit(rng, (235, 215, 170)), _jit(rng, (215, 190, 140)))
        for _ in range(rng.randint(3, 6)):
            x, y = rng.randint(50, W - 50), rng.randint(shore + 40, H - 80)
            col = rng.choice([(235, 80, 60), (245, 160, 40), (60, 120, 220), (240, 200, 60)])
            d.polygon([(x - 70, y), (x + 70, y), (x, y - 50)], fill=col)
            d.line([(x, y), (x, y + 80)], fill=(90, 80, 70), width=4)
    elif kind == "coast_train":
        horizon = int(H * 0.42)
        _grad(d, (0, 0, W, horizon), _jit(rng, (125, 180, 235)), _jit(rng, (195, 225, 245)))
        _grad(d, (0, horizon, W, H), _jit(rng, (35, 105, 185)), _jit(rng, (60, 140, 205)))
        d.polygon([(0, H * 0.35), (W * 0.45, H * 0.55), (W * 0.35, H), (0, H)], fill=_jit(rng, (70, 140, 80)))
        for _ in range(40):
            x, y = rng.randint(0, int(W * 0.35)), rng.randint(int(H * 0.45), H)
            d.ellipse([x, y, x + 40, y + 30], fill=_jit(rng, (55, 120, 65), 20))
        ty = int(H * rng.uniform(0.55, 0.62))
        d.line([(0, ty + 70), (W, ty + 40)], fill=(90, 85, 80), width=10)
        tx = rng.randint(200, 420)
        for car, col in enumerate([(235, 190, 40), (230, 70, 60), (235, 190, 40)]):
            x0 = tx + car * 260
            d.rounded_rectangle([x0, ty - 70, x0 + 240, ty + 50], radius=30, fill=col)
            for wx in range(x0 + 25, x0 + 220, 55):
                d.rectangle([wx, ty - 45, wx + 35, ty - 10], fill=(200, 230, 245))
    elif kind in ("food", "food_side"):
        _grad(d, (0, 0, W, H), _jit(rng, (150, 95, 55)), _jit(rng, (120, 75, 40)))
        for _ in range(30):
            y = rng.randint(0, H)
            d.line([(0, y), (W, y + rng.randint(-20, 20))], fill=_jit(rng, (135, 85, 48), 15), width=3)
        if kind == "food":
            cx, cy, r = W // 2 + rng.randint(-60, 60), H // 2 + rng.randint(-40, 40), 300
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(245, 240, 232))
            d.ellipse([cx - r + 40, cy - r + 40, cx + r - 40, cy + r - 40], fill=_jit(rng, (238, 222, 195), 6))
            for _ in range(25):
                x, y = cx + rng.randint(-180, 180), cy + rng.randint(-180, 180)
                d.ellipse([x, y, x + 22, y + 10], fill=(90, 160, 70))
            for _ in range(6):
                x, y = cx + rng.randint(-150, 130), cy + rng.randint(-150, 130)
                d.ellipse([x, y, x + 70, y + 45], fill=(210, 170, 150))
        n = 4 if kind == "food_side" else 2
        for i in range(n):
            x, y = rng.randint(40, W - 260), rng.choice([60, H - 250])
            d.ellipse([x, y, x + 200, y + 190], fill=(240, 236, 228))
            d.ellipse([x + 30, y + 30, x + 170, y + 160], fill=rng.choice([(205, 55, 40), (225, 120, 50), (200, 70, 50)]))
    elif kind == "night_bridge":
        _grad(d, (0, 0, W, int(H * 0.55)), _jit(rng, (12, 18, 45), 5), _jit(rng, (30, 35, 75), 5))
        _grad(d, (0, int(H * 0.55), W, H), _jit(rng, (15, 20, 50), 5), _jit(rng, (8, 12, 30), 5))
        for _ in range(40):
            x, y = rng.randint(0, W), rng.randint(0, int(H * 0.4))
            d.point((x, y), fill=(220, 220, 240))
        deck = int(H * 0.55)
        d.line([(0, deck), (W, deck)], fill=(180, 190, 220), width=10)
        for px in (int(W * 0.28), int(W * 0.72)):
            d.rectangle([px - 10, deck - 250, px + 10, deck], fill=(190, 200, 230))
        for i in range(0, W, 8):
            t = i / W
            y = deck - 240 * abs(math.sin(t * math.pi * 2)) * 0.8
            d.ellipse([i, y, i + 4, y + 4], fill=(250, 210, 90))
        for _ in range(60):
            x = rng.randint(0, W)
            y = rng.randint(deck + 10, H)
            d.line([(x, y), (x + rng.randint(10, 40), y)], fill=(200, 170, 80), width=2)
    elif kind == "village":
        _grad(d, (0, 0, W, int(H * 0.3)), _jit(rng, (130, 185, 235)), _jit(rng, (200, 225, 245)))
        d.rectangle([0, int(H * 0.3), W, H], fill=_jit(rng, (110, 125, 110)))
        colors = [(70, 150, 220), (240, 120, 150), (250, 205, 70), (120, 200, 170), (240, 140, 70), (170, 120, 210), (245, 245, 240)]
        for row in range(9):
            y = int(H * 0.28) + row * 78
            x = -rng.randint(0, 60)
            while x < W:
                bw = rng.randint(70, 130)
                d.rectangle([x, y, x + bw, y + 70], fill=rng.choice(colors))
                d.polygon([(x - 4, y), (x + bw + 4, y), (x + bw // 2, y - 22)], fill=rng.choice(colors[:5]))
                d.rectangle([x + 14, y + 20, x + 34, y + 44], fill=(60, 70, 90))
                x += bw + rng.randint(4, 16)
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    # 센서 잡음
    noise = Image.effect_noise((W, H), 10).convert("L")
    return Image.blend(im, Image.merge("RGB", (noise, noise, noise)), 0.04)


def _dms(deg: float):
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60)
    s = round((deg - d - m / 60) * 3600, 2)
    return (float(d), float(m), float(s))


def save_with_exif(im: Image.Image, path: Path, taken: datetime, latlng: tuple[float, float] | None) -> None:
    exif = Image.Exif()
    exif[0x010F] = "Chalkak"
    exif[0x0110] = "DemoCam"
    stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
    exif[0x0132] = stamp
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = stamp
    ifd[0x9004] = stamp
    if latlng:
        lat, lng = latlng
        gps = exif.get_ifd(0x8825)
        gps.update({0: b"\x02\x03\x00\x00", 1: "N" if lat >= 0 else "S", 2: _dms(lat), 3: "E" if lng >= 0 else "W", 4: _dms(lng)})
    im.save(path, "JPEG", quality=86, exif=exif.tobytes())


def _offset(rng: random.Random, center: tuple[float, float], meters: float) -> tuple[float, float]:
    lat, lng = center
    ang = rng.uniform(0, 2 * math.pi)
    r = rng.uniform(0, meters)
    return (lat + r * math.cos(ang) / 111_320, lng + r * math.sin(ang) / (111_320 * math.cos(math.radians(lat))))


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()
    (out / "vlm_replay.json").unlink(missing_ok=True)  # 실제 사진 세트의 미리 정한 응답이 남지 않게
    rng = random.Random(20261010)
    labels = []
    n = 0
    day1 = None
    for label, kind, place_id, center, times in VISITS:
        base_date = times[0].split(" ")[0]
        for t in times:
            stamp = t if " " in t else f"{base_date} {t}"
            taken = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
            n += 1
            name = f"busan_{n:02d}_{taken:%m%d_%H%M}.jpg"
            save_with_exif(scene(kind, rng), out / name, taken, _offset(rng, center, 25))
            labels.append({"file": name, "visit": label, "place_id": place_id, "has_gps": True, "taken_at": taken.isoformat()})
            day1 = day1 or taken.date()
    for label, kind, visit, stamp in UNTAGGED:
        taken = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        n += 1
        name = f"busan_{n:02d}_{taken:%m%d_%H%M}_nogps.jpg"
        save_with_exif(scene(kind, rng), out / name, taken, None)
        place = next(v[2] for v in VISITS if v[0] == visit)
        labels.append({"file": name, "visit": visit, "place_id": place, "has_gps": False, "taken_at": taken.isoformat()})
    (out / "labels.json").write_text(json.dumps({
        "note": "합성 시연 세트 정답 라벨 (팀 촬영 평가셋으로 교체 예정)",
        "visits": [{"visit": v[0], "place_id": v[2], "photos": len(v[4])} for v in VISITS],
        "photos": labels,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{n}장 생성 → {out}")


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "var" / "demo_photos"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
