"""CP-06 Share Card Renderer (Application 계층).

책임: 썸네일·제목·동선 요약으로 공유 이미지 생성. 좌표·EXIF는 넣지 않는다 (FR-11, AC-10, UC-08).
썸네일은 이미 EXIF가 제거된 것만 쓰고, 결과 PNG도 메타데이터 없이 저장한다.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1350
BG = (255, 248, 242)
INK = (34, 30, 28)
SUB = (120, 110, 104)
ACCENT = (240, 92, 44)

FONT_CANDIDATES = {
    "bold": ["/usr/share/fonts/truetype/nanum/NanumSquareB.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
             "/System/Library/Fonts/AppleSDGothicNeo.ttc", "C:/Windows/Fonts/malgunbd.ttf"],
    "regular": ["/usr/share/fonts/truetype/nanum/NanumSquareR.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/System/Library/Fonts/AppleSDGothicNeo.ttc", "C:/Windows/Fonts/malgun.ttf"],
}


def _font(kind: str, size: int):
    for p in FONT_CANDIDATES[kind]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list[str]:
    """띄어쓰기 단위로 줄바꿈 (한 단어가 너무 길면 글자 단위)."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while draw.textlength(cur, font=font) > width:  # 긴 단어는 글자 단위로 자름
            cut = len(cur)
            while cut > 1 and draw.textlength(cur[:cut], font=font) > width:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip()[:-1] + "…"
    return lines


def render_share_card(title: str, date_range: str, route_summary: list[dict], thumb_jpeg: bytes | None) -> bytes:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # 대표 사진 (EXIF 없는 썸네일)
    photo_h = 700
    if thumb_jpeg:
        with Image.open(io.BytesIO(thumb_jpeg)) as t:
            photo = ImageOps.fit(t.convert("RGB"), (W, photo_h))
        img.paste(photo, (0, 0))
    else:
        d.rectangle([0, 0, W, photo_h], fill=(250, 214, 190))
    d.rectangle([0, photo_h - 8, W, photo_h], fill=ACCENT)

    y = photo_h + 48
    for line in _wrap(d, title, _font("bold", 64), W - 120, 2):
        d.text((60, y), line, font=_font("bold", 64), fill=INK)
        y += 80
    d.text((60, y + 4), date_range, font=_font("regular", 34), fill=SUB)
    y += 70

    small = _font("regular", 32)
    badge = _font("bold", 24)
    left, right = 190, W - 60
    for day in route_summary[:3]:
        if y > H - 170:
            break
        d.text((60, y), f"{day['day']}일차", font=_font("bold", 32), fill=ACCENT)
        x = left
        for i, stop in enumerate(day["stops"]):
            label = stop["name"]
            w = 46 + d.textlength(label, font=small) + (34 if i < len(day["stops"]) - 1 else 0)
            if x + w > right and x > left:  # 다음 줄로
                y += 54
                x = left
                if y > H - 170:
                    d.text((x, y), "…", font=small, fill=SUB)
                    break
            color = tuple(int(stop.get("color", "#8A8F98").lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
            d.ellipse([x, y + 2, x + 36, y + 38], fill=color)
            num = str(stop["order"])
            d.text((x + 18 - d.textlength(num, font=badge) / 2, y + 7), num, font=badge, fill=(255, 255, 255))
            d.text((x + 44, y + 1), label, font=small, fill=INK)
            x += 46 + d.textlength(label, font=small)
            if i < len(day["stops"]) - 1:
                d.text((x + 6, y + 1), "›", font=small, fill=SUB)
                x += 34
        y += 70
    footer = "찰칵부산 · AI가 공식 관광 데이터로 작성한 여행기"
    d.text((60, H - 80), footer, font=_font("regular", 28), fill=SUB)

    buf = io.BytesIO()
    img.save(buf, "PNG")  # 메타데이터 없이 저장 (좌표·EXIF 없음, AC-10)
    return buf.getvalue()
