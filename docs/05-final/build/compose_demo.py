"""휴대폰 화면 녹화 프레임 → 1920x1080 시연 영상 (PowerPoint 재생용 H.264).

화면 구성: 왼쪽 휴대폰 틀 안에 휴대폰 웹 브라우저(상태 표시줄·주소창·아래 버튼 줄) + 녹화한 웹 페이지 + 터치·스크롤 표시 + 강조 상자,
오른쪽 설명 칸에 단계 목록 · 단계 제목 · 요구사항 번호 · 설명 줄(지금 보는 줄 강조) · 강조 부분 확대 · 처리 시간.
주소창에는 녹화한 공개 주소를 표시하고, 녹화 처음의 주소 입력(url_type)·접속(nav_start~nav_end)에 맞춰 입력 글자·로딩 막대를 그린다.
문구는 문어체 개조식 (과장 표현 없이 화면에 보이는 사실만).

사용: python compose_demo.py <녹화 폴더> <출력.mp4> [--preview 초,초,...]
출력: <출력.mp4>, 같은 폴더의 <출력>.chapters.json (단계 시작 시각 → deck_data.json chapters)
"""
import json
import math
import subprocess
import sys
import time
from bisect import bisect_right
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
PREVIEW = [float(x) for x in sys.argv[sys.argv.index("--preview") + 1].split(",")] if "--preview" in sys.argv else None
FPS, W, H = 30, 1920, 1080
FD = "/mnt/c/Windows/Fonts/"


def font(weight, size):
    return ImageFont.truetype(FD + f"Pretendard-{weight}.ttf", size)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# 발표 자료와 같은 색 (build_deck.js)
INK, BODY, MUTED = rgb("16181D"), rgb("4B5059"), rgb("8A8F98")
PURPLE, LAV, LAV_LINE = rgb("5B4BE0"), rgb("EEECFC"), rgb("D6D0F7")
FAINT, BG1, BG2 = rgb("B9BCC4"), rgb("F7F6FD"), rgb("ECEAFA")

M = json.loads((REC / "phone.json").read_text())
EV = M["events"]
FACTS = M.get("facts", {})
T0, DUR = M["t0"], M["t_end"] - M["t0"]
TS = [f[0] for f in M["frames"]]
VW, VH, DSF = M["vw"], M["vh"], M["dsf"]
SCREEN_H = M.get("screen_h", VH)                                   # 휴대폰 화면 전체 높이 (CSS px)
C_TOP, C_BOT = M.get("chrome_top", 0), M.get("chrome_bottom", 0)  # 브라우저 위(상태 표시줄+주소창)·아래(버튼 줄)
URL, HOST = M.get("url", ""), M.get("host", "")
REC_DATE = time.strftime("%Y.%m.%d", time.localtime(T0))

# ------------------------------------------------------------------ 설명 문구 (단계별)
chips = FACTS.get("chips", [])
n_auto = sum(1 for c in chips if c == "자동확정")
n_ask = sum(1 for c in chips if c in ("선택필요", "확인필요"))
model = FACTS.get("story_model") or ""
by_llm = "qwen" in model.lower()
STEPS = {
    1: ("사진 업로드", "FR-01 · NFR-04", ["휴대폰 브라우저에서 공개 주소로 접속 (HTTPS)", "첫 화면에서 새 여행기 시작",
                                         "갤러리에서 여행 사진 7장 선택", "AI 분석 동의 (서버 안의 AI만 사용)",
                                         "원본 사진·위치 좌표는 분석 후 삭제"]),
    2: ("AI 장소 판별", "FR-02 · FR-03 · FR-04", ["촬영 시각·위치(EXIF)로 방문지 묶기", "반경 300m 안 관광 데이터 후보 조회 (샘플 40곳)",
                                                  "서버 AI(Qwen3.5 4B)가 후보 중에서 선택", f"확신도 0.8 이상 {n_auto}곳: 자동 확정",
                                                  f"확신도가 낮은 {n_ask}곳: 사용자 확인 요청"]),
    3: ("사용자 확인", "FR-05 · FR-06", ["AI 판단 근거·확신도 표시", "후보 중에서 장소 직접 선택",
                                        "위치 없는 사진: 촬영 시각·사진 비교로 추천", "추천 방문지에 배정 → 방문지 6곳 확정"]),
    4: ("동선 지도", "FR-07 · FR-08", ["날짜별 방문 순서·경로 (지도)", "구간별 이동 수단·거리·예상 시간",
                                     "장소 상세: 개요·주소·출처·갱신일"]),
    5: ("출처 있는 여행기", "FR-09 · NFR-03", ["문체 선택: 블로그형·일기형·간결형",
                                              "확정 장소·공식 데이터만으로 작성" + (" (서버 LLM)" if by_llm else ""),
                                              "문장마다 공식 데이터와 사실 대조", "장소 이름 링크 · 사실 문장마다 출처 번호",
                                              "출처 목록: 제공 기관·항목·갱신일"]),
    6: ("공유 카드", "FR-11", ["대표 사진·제목·날짜별 동선 요약 이미지", "좌표·정확한 위치 정보 제외"]),
}
SHORT = {1: "사진 업로드", 2: "장소 판별", 3: "사용자 확인", 4: "동선 지도", 5: "여행기", 6: "공유 카드"}
CIRC = "①②③④⑤⑥"
STORY_NOTE = (f"작성 모델: {model}" if by_llm else "이번 녹화: LLM 응답 형식 오류 → 템플릿 여행기로 대체 (D-04)") if model else ""

# ------------------------------------------------------------------ 배치
SCR_H = 944
SCR_W = round(SCR_H * VW / SCREEN_H)
S = SCR_H / SCREEN_H                # 화면 1 CSS px → 영상 px
PAGE_TOP = round(C_TOP * S)         # 휴대폰 화면 안에서 웹 페이지가 시작하는 높이 (영상 px)
PAGE_H = round((C_TOP + VH) * S) - PAGE_TOP
BEZ, RAD = 15, 50
PX = 470 - SCR_W // 2               # 화면 왼쪽 위
PY = (H - SCR_H) // 2
PANEL_X, PANEL_W = 820, 1020
LINE_Y, LINE_GAP = 330, 64          # 설명 줄 시작·간격
ZOOM_BOTTOM = 1004                  # 확대 칸 아래 끝 (그 아래는 출처 줄)


def zoom_area(n):
    """확대 칸 위치·최대 높이: 설명 줄이 적은 단계일수록 크게."""
    y = LINE_Y + len(STEPS[n][2]) * LINE_GAP + (40 if n == 5 and STORY_NOTE else 0) + 56
    return y, ZOOM_BOTTOM - y - 28

# ------------------------------------------------------------------ 이벤트 정리
steps = [e for e in EV if e["kind"] == "step"]
url_ev = next((e for e in EV if e["kind"] == "url_type"), None)
nav_ev = (next((e["t"] for e in EV if e["kind"] == "nav_start"), None), next((e["t"] for e in EV if e["kind"] == "nav_end"), None))
taps = [e for e in EV if e["kind"] == "tap"]
swipes = [e for e in EV if e["kind"] == "swipe"]
hls = []  # (시작, 끝, 상자)
for i, e in enumerate(EV):
    if e["kind"] == "hl":
        end = next((x["t"] for x in EV[i + 1:] if x["kind"] in ("hl", "hl_off")), M["t_end"])
        hls.append((e["t"], end, (e["x"], e["y"], e["w"], e["h"])))
timers = {}
for e in EV:
    if e["kind"] == "timer_start":
        timers.setdefault(e["key"], {})["start"] = e["t"]
    elif e["kind"] == "timer_stop":
        timers.setdefault(e["key"], {})["stop"] = e["t"]


def step_at(t):
    cur = steps[0] if steps else {"n": 1, "line": [0], "t": T0}
    for e in steps:
        if e["t"] <= t:
            cur = e
    return cur


def first_step_time(n):
    return next(e["t"] for e in steps if e["n"] == n)


# ------------------------------------------------------------------ 그리기 도구
_frame_cache: dict = {}


def frame_src(t):
    i = max(0, bisect_right(TS, t) - 1)
    if i not in _frame_cache:
        if len(_frame_cache) > 12:
            _frame_cache.clear()
        _frame_cache[i] = Image.open(REC / "phone" / M["frames"][i][1]).convert("RGB")
    return _frame_cache[i], i


_screen_cache: dict = {}


def screen_img(t):
    src, i = frame_src(t)
    if i not in _screen_cache:
        if len(_screen_cache) > 12:
            _screen_cache.clear()
        _screen_cache[i] = src.resize((SCR_W, PAGE_H), Image.LANCZOS)
    return _screen_cache[i], src


def vgrad(w, h, c1, c2):
    g = Image.new("RGB", (1, h))
    for y in range(h):
        k = y / (h - 1)
        g.putpixel((0, y), tuple(int(a + (b - a) * k) for a, b in zip(c1, c2)))
    return g.resize((w, h))


def base_bg():
    bg = vgrad(W, H, BG1, BG2)
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle((PX - BEZ + 6, PY - BEZ + 16, PX + SCR_W + BEZ + 6, PY + SCR_H + BEZ + 16), RAD + BEZ, fill=120)
    bg.paste((60, 56, 90), mask=sh.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((PX - BEZ, PY - BEZ, PX + SCR_W + BEZ, PY + SCR_H + BEZ), RAD + BEZ, fill=(22, 23, 28))
    d.rounded_rectangle((PX - BEZ + 3, PY - BEZ + 3, PX + SCR_W + BEZ - 3, PY + SCR_H + BEZ - 3), RAD + BEZ - 3, outline=(70, 72, 82), width=2)
    return bg


BG = base_bg().convert("RGBA")
MASK = Image.new("L", (SCR_W, SCR_H), 0)
ImageDraw.Draw(MASK).rounded_rectangle((0, 0, SCR_W - 1, SCR_H - 1), RAD, fill=255)

F_CHIP, F_CHIP_B = font("Medium", 23), font("Bold", 23)
F_TITLE, F_REQ = font("Bold", 62), font("SemiBold", 25)
F_LINE, F_LINE_B = font("Regular", 33), font("Bold", 33)
F_NOTE, F_FOOT, F_TIMER = font("Medium", 25), font("Regular", 22), font("SemiBold", 28)

# ------------------------------------------------------------------ 휴대폰 웹 브라우저 (상태 표시줄 · 주소창 · 아래 버튼 줄)
B_INK, B_ICON, B_PILL, B_LINE, B_BLUE = (32, 33, 36), (95, 99, 104), (241, 243, 244), (218, 220, 224), (26, 115, 232)
SB_H = round(24 * S)                         # 상태 표시줄 높이 (영상 px)
NAV_Y = PAGE_TOP + PAGE_H                    # 아래 버튼 줄 시작
PILL = (14, SB_H + 10, SCR_W - 88, PAGE_TOP - 10)  # 주소 입력 칸
F_SB, F_URL, F_TAB = font("SemiBold", 16), font("Regular", 17), font("Bold", 12)


def chrome_base():
    im = Image.new("RGBA", (SCR_W, SCR_H), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    cy = SB_H // 2 + 1
    d.ellipse((SCR_W // 2 - 7, cy - 7, SCR_W // 2 + 7, cy + 7), fill=(12, 12, 14))        # 전면 카메라
    x = SCR_W - 34                                                                       # 배터리
    d.rounded_rectangle((x - 22, cy - 6, x, cy + 6), 3, outline=B_INK, width=2)
    d.rectangle((x - 18, cy - 2, x - 5, cy + 2), fill=B_INK)
    d.rectangle((x + 1, cy - 2, x + 3, cy + 2), fill=B_INK)
    x -= 40                                                                              # 와이파이
    for r in (12, 8):
        d.arc((x - r, cy + 6 - r, x + r, cy + 6 + r), 225, 315, fill=B_INK, width=2)
    d.pieslice((x - 4, cy + 2, x + 4, cy + 10), 225, 315, fill=B_INK)
    x -= 36                                                                              # 신호 세기
    for i in range(4):
        h = 4 + 3 * i
        d.rectangle((x + i * 5, cy + 6 - h, x + i * 5 + 3, cy + 6), fill=B_INK)
    cy2 = (PILL[1] + PILL[3]) // 2                                                       # 탭 수 · 메뉴
    cx = SCR_W - 62
    d.rounded_rectangle((cx - 10, cy2 - 10, cx + 10, cy2 + 10), 4, outline=B_ICON, width=2)
    d.text((cx, cy2 + 1), "1", font=F_TAB, fill=B_ICON, anchor="mm")
    cx = SCR_W - 30
    for dy in (-7, 0, 7):
        d.ellipse((cx - 2.4, cy2 + dy - 2.4, cx + 2.4, cy2 + dy + 2.4), fill=B_ICON)
    d.line((0, PAGE_TOP - 1, SCR_W, PAGE_TOP - 1), fill=B_LINE, width=1)
    d.rectangle((0, NAV_Y, SCR_W, SCR_H), fill=(246, 247, 249))                         # 아래 버튼 줄 (뒤로·홈·최근)
    ny, mx = NAV_Y + (SCR_H - NAV_Y) // 2 - 3, SCR_W // 2
    d.line([(mx - 104, ny - 8), (mx - 116, ny), (mx - 104, ny + 8), (mx - 104, ny - 8)], fill=B_ICON, width=2, joint="curve")
    d.ellipse((mx - 8, ny - 8, mx + 8, ny + 8), outline=B_ICON, width=2)
    d.rounded_rectangle((mx + 103, ny - 7, mx + 117, ny + 7), 2, outline=B_ICON, width=2)
    return im


CHROME = chrome_base()


def url_state(t):
    """주소창 상태: 빈 칸 → 주소 입력(url_type) → 접속 중 로딩 막대(nav_start~nav_end) → 주소 표시."""
    if url_ev is None:
        return "loaded", HOST, None
    ta, dur = url_ev["t"], url_ev.get("dur", 2.4)
    ns, ne = nav_ev
    if t < ta:
        return "empty", "", None
    if ns is None or t < ns:
        return "typing", HOST[:min(len(HOST), 1 + int(len(HOST) * (t - ta) / dur))], None
    if ne is None or t < ne:
        return "loaded", HOST, 0.12 + 0.75 * (1 - math.exp(-(t - ns) / 0.7))
    if t < ne + 0.25:
        return "loaded", HOST, min(1.0, 0.87 + (t - ne) / 0.12 * 0.13)
    return "loaded", HOST, None


def draw_lock(d, cx, cy):
    d.rounded_rectangle((cx - 6, cy - 2, cx + 6, cy + 7), 2, fill=B_ICON)
    d.arc((cx - 4, cy - 9, cx + 4, cy - 1), 180, 360, fill=B_ICON, width=2)
    d.line((cx - 4, cy - 5, cx - 4, cy - 1), fill=B_ICON, width=2)
    d.line((cx + 4, cy - 5, cx + 4, cy - 1), fill=B_ICON, width=2)


def draw_chrome(scr, t):
    d = ImageDraw.Draw(scr)
    d.text((32, SB_H // 2 + 1), time.strftime("%H:%M", time.localtime(t)), font=F_SB, fill=B_INK, anchor="lm")
    state, text, bar = url_state(t)
    x0, y0, x1, y1 = PILL
    rad = (y1 - y0) // 2
    if state == "typing":
        d.rounded_rectangle(PILL, rad, fill=(255, 255, 255), outline=B_BLUE, width=2)
    else:
        d.rounded_rectangle(PILL, rad, fill=B_PILL)
    ty = (y0 + y1) // 2
    tx = x0 + 18
    if state == "loaded":
        draw_lock(d, x0 + 21, ty)
        tx = x0 + 37
    if state == "empty":
        d.text((tx, ty), "검색어 또는 URL 입력", font=F_URL, fill=B_ICON, anchor="lm")
    else:
        avail = x1 - 14 - tx
        tw = d.textlength(text, font=F_URL)
        layer = Image.new("RGBA", (avail, y1 - y0), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        off = min(0, avail - 6 - tw) if state == "typing" else 0   # 입력 중에는 커서 쪽(끝)을 보임
        ld.text((off, (y1 - y0) // 2), text, font=F_URL, fill=B_INK, anchor="lm")
        if state == "typing" and (t - url_ev["t"] < url_ev.get("dur", 2.4) or int((t - url_ev["t"]) * 2) % 2 == 0):
            cxx = off + tw + 2
            ld.line((cxx, 9, cxx, y1 - y0 - 9), fill=B_BLUE, width=2)
        fade = Image.new("L", layer.size, 255)
        fd = ImageDraw.Draw(fade)
        if tw > avail and state == "loaded":          # 긴 주소는 오른쪽 끝을 흐리게 (휴대폰 브라우저와 같음)
            for k in range(28):
                fd.line((avail - 28 + k, 0, avail - 28 + k, layer.height), fill=int(255 * (1 - k / 28)))
        if off < 0:
            for k in range(20):
                fd.line((k, 0, k, layer.height), fill=int(255 * k / 20))
        # 글자 불투명도 × 흐림 (fade가 255인 곳은 그대로, 0인 곳은 투명)
        layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", layer.size, 0), fade))
        scr.alpha_composite(layer, (tx, y0))
    if bar:
        d.rectangle((0, PAGE_TOP - 3, int(SCR_W * bar), PAGE_TOP - 1), fill=B_BLUE)


def text_w(d, s, f):
    return d.textlength(s, font=f)


_panel_cache: dict = {}


def panel(n, active):
    key = (n, tuple(active))
    if key in _panel_cache:
        return _panel_cache[key]
    im = Image.new("RGBA", (PANEL_W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # 단계 목록
    x, y = 0, 64
    for k in range(1, 7):
        label = f"{CIRC[k - 1]} {SHORT[k]}"
        f = F_CHIP_B if k == n else F_CHIP
        w = text_w(d, label, f) + 34
        if k == n:
            d.rounded_rectangle((x, y, x + w, y + 46), 23, fill=PURPLE)
            d.text((x + 17, y + 23), label, font=f, fill="white", anchor="lm")
        elif k < n:
            d.rounded_rectangle((x, y, x + w, y + 46), 23, fill=LAV)
            d.text((x + 17, y + 23), label, font=f, fill=PURPLE, anchor="lm")
        else:
            d.rounded_rectangle((x, y, x + w, y + 46), 23, outline=LAV_LINE, width=2, fill=(255, 255, 255))
            d.text((x + 17, y + 23), label, font=f, fill=MUTED, anchor="lm")
        x += w + 10
    title, req, lines = STEPS[n]
    d.text((0, 168), f"{CIRC[n - 1]} {title}", font=F_TITLE, fill=INK, anchor="lt")
    rw = text_w(d, "요구사항 " + req, F_REQ) + 32
    d.rounded_rectangle((2, 258, 2 + rw, 300), 21, fill=LAV)
    d.text((18, 279), "요구사항 " + req, font=F_REQ, fill=PURPLE, anchor="lm")
    y = LINE_Y
    last = max(active) if active else -1
    for i, ln in enumerate(lines):
        on = i in active
        if on:
            d.rounded_rectangle((0, y - 6, PANEL_W, y + 52), 12, fill=(255, 255, 255))
            d.rectangle((0, y - 6, 7, y + 52), fill=PURPLE)
            d.text((28, y + 23), ln, font=F_LINE_B, fill=INK, anchor="lm")
        else:
            col = BODY if i < last else FAINT
            d.text((28, y + 23), ln, font=F_LINE, fill=col, anchor="lm")
        y += LINE_GAP
    if n == 5 and STORY_NOTE:
        d.text((28, y + 12), STORY_NOTE, font=F_NOTE, fill=MUTED, anchor="lm")
    _panel_cache[key] = im
    return im


FOOT = f"공개 서버에서 녹화 ({REC_DATE}) · 휴대폰 화면 크기({VW}×{SCREEN_H}) 웹 브라우저 · 처리 시간 실제 속도"


def draw_ring(img, x, y, k):
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    r = 30 + 12 * k
    d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, int(130 * (1 - k))), outline=(40, 40, 60, int(170 * (1 - k))), width=3)
    img.alpha_composite(over)


def to_video(x, y):
    """웹 페이지 좌표(CSS px) → 영상 좌표 (주소창 아래부터 페이지)."""
    return PX + x * S, PY + (C_TOP + y) * S


def hl_at(t):
    for a, b, box in hls:
        if a <= t < b:
            return a, b, box
    return None


def draw_highlight(img, t, a, b, box):
    k = min(1.0, (t - a) / 0.3, max(0.0, (b - t) / 0.2))
    x, y, w, h = box
    x0, y0 = to_video(x, y)
    x1, y1 = to_video(x + w, y + h)
    x0, y0, x1, y1 = max(PX, x0), max(PY + PAGE_TOP, y0), min(PX + SCR_W, x1), min(PY + PAGE_TOP + PAGE_H, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:  # 상자가 웹 페이지 영역 밖이면 그리지 않음
        return
    dim = Image.new("RGBA", (SCR_W, SCR_H), (20, 18, 40, int(95 * k)))
    hole = Image.new("L", (SCR_W, SCR_H), 255)
    ImageDraw.Draw(hole).rounded_rectangle((x0 - PX, y0 - PY, x1 - PX, y1 - PY), 10, fill=0)
    m2 = Image.new("L", (SCR_W, SCR_H), 0)
    m2.paste(hole, (0, 0), MASK)
    dim.putalpha(Image.eval(m2, lambda v: int(v * 95 * k / 255)))
    od = ImageDraw.Draw(dim)
    od.rounded_rectangle((x0 - PX - 2, y0 - PY - 2, x1 - PX + 2, y1 - PY + 2), 12, outline=PURPLE + (int(255 * k),), width=5)
    img.alpha_composite(dim, (PX, PY))


def zoom_inset(img, t, a, b, box, src, n):
    """강조 부분 확대: 휴대폰 화면보다 1.45배 이상 커질 때만 설명 줄 아래에 표시."""
    x, y, w, h = box
    ZOOM_Y, ZOOM_H = zoom_area(n)
    maxw, maxh = PANEL_W - 40, ZOOM_H
    sc = min(maxw / w, maxh / h, 2.7)
    if sc < 1.45 * S:
        return
    k = min(1.0, (t - a) / 0.3, max(0.0, (b - t) / 0.2))
    cx0, cy0 = max(0, int(x * DSF)), max(0, int(y * DSF))
    cx1, cy1 = min(src.width, int((x + w) * DSF)), min(src.height, int((y + h) * DSF))
    if cx1 - cx0 < 10 or cy1 - cy0 < 10:
        return
    crop = src.crop((cx0, cy0, cx1, cy1))
    zw, zh = int((cx1 - cx0) / DSF * sc), int((cy1 - cy0) / DSF * sc)
    crop = crop.resize((zw, zh), Image.LANCZOS)
    ox, oy = PANEL_X, ZOOM_Y
    card = Image.new("RGBA", (zw + 28, zh + 28), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle((0, 0, zw + 27, zh + 27), 16, fill=(255, 255, 255, 255), outline=PURPLE, width=4)
    cm = Image.new("L", (zw, zh), 0)
    ImageDraw.Draw(cm).rounded_rectangle((0, 0, zw - 1, zh - 1), 8, fill=255)
    card.paste(crop, (14, 14), cm)
    if k < 1:
        card.putalpha(Image.eval(card.getchannel("A"), lambda v: int(v * k)))
    img.alpha_composite(card, (ox, oy))
    ImageDraw.Draw(img).text((ox + 2, oy - 32), "확대", font=F_FOOT, fill=PURPLE, anchor="lt")


def timer_text(t):
    for key, label in (("analysis", "분석 시작 → 결과 화면"), ("story", "여행기 만들기 → 여행기 화면")):
        tm = timers.get(key)
        if not tm or "start" not in tm or t < tm["start"]:
            continue
        stop = tm.get("stop", M["t_end"])
        if t < stop:
            return f"{label}  처리 중 {t - tm['start']:4.1f}초"
        if t < stop + 6:
            return f"{label}  {stop - tm['start']:.1f}초 (실제 속도)"
    return None


def phone_frame(t_rel, progress):
    t = T0 + t_rel
    img = BG.copy().convert("RGBA")
    page, src = screen_img(t)
    scr = CHROME.copy()
    scr.paste(page, (0, PAGE_TOP))
    draw_chrome(scr, t)
    img.paste(scr, (PX, PY), MASK)
    if url_ev and url_ev["t"] - 0.35 <= t < url_ev["t"] + 0.25:  # 주소창 터치
        draw_ring(img, PX + (PILL[0] + PILL[2]) / 2, PY + (PILL[1] + PILL[3]) / 2, (t - url_ev["t"] + 0.35) / 0.6)
    h = hl_at(t)
    if h:
        draw_highlight(img, t, *h)
    for e in taps:
        if e["t"] <= t < e["t"] + 0.6:
            draw_ring(img, *to_video(e["x"], e["y"]), (t - e["t"]) / 0.6)
    for e in swipes:
        dur = e.get("dur", 0.5) + 0.2
        if e["t"] <= t < e["t"] + dur:
            k = (t - e["t"]) / dur
            yy = e["y"] - (e["dy"] * 0.35) * min(1.0, k * 1.2) * (1 if abs(e["dy"]) < 900 else 900 / abs(e["dy"]))
            draw_ring(img, *to_video(e["x"], yy), 0.15 + 0.6 * k)
    st = step_at(t)
    img.alpha_composite(panel(st["n"], st["line"]), (PANEL_X, 0))
    if h:
        zoom_inset(img, t, *h, src, st["n"])
    d = ImageDraw.Draw(img)
    tt = timer_text(t)
    if tt:
        tw = d.textlength(tt, font=F_TIMER) + 40
        x1 = PANEL_X + PANEL_W
        d.rounded_rectangle((x1 - tw, 253, x1, 303), 25, fill=(255, 255, 255), outline=LAV_LINE, width=2)
        d.text((x1 - tw + 20, 278), tt, font=F_TIMER, fill=PURPLE, anchor="lm")
    d.text((PANEL_X, H - 44), FOOT, font=F_FOOT, fill=MUTED, anchor="lm")
    d.rectangle((0, H - 6, int(W * progress), H), fill=PURPLE)
    return img.convert("RGB")


def card(title, lines, small):
    img = vgrad(W, H, BG1, BG2)
    d = ImageDraw.Draw(img)
    d.text((170, 300), title, font=font("Bold", 92), fill=INK, anchor="lt")
    y = 450
    for ln in lines:
        d.ellipse((176, y + 20, 188, y + 32), fill=PURPLE)
        d.text((212, y + 26), ln, font=font("SemiBold", 42), fill=BODY, anchor="lm")
        y += 74
    y += 40
    for ln in small:
        d.text((176, y), ln, font=font("Regular", 30), fill=MUTED, anchor="lt")
        y += 48
    return img


INTRO_IMG = card("찰칵부산 시연 (휴대폰 웹 브라우저)",
                 ["공개 주소로 접속 → 부산 여행 사진 7장 업로드", "방문지 6곳 확정 → 날짜별 동선 지도", "출처 있는 여행기 → 공유 카드"],
                 [f"녹화: {REC_DATE} · 공개 서버(Docker Compose) · 처리 시간 실제 속도",
                  f"공개 주소: {URL} (녹화 당시 주소)",
                  "AI: 서버 안의 Qwen3.5 4B (장소 판별·여행기 작성)",
                  f"화면: 휴대폰 화면 크기({VW}×{SCREEN_H}) 브라우저로 녹화, 휴대폰 틀·주소창은 덧그림 (실기기 테스트 아님)",
                  "사진: 웹 사진 7장에 시연용 촬영 시각·위치 입력",
                  "장소 데이터: 공식 데이터와 같은 형식의 샘플 40곳 (공공데이터 API 키 미발급)"])
an_s, st_s = FACTS.get("analysis_s"), FACTS.get("story_s")
OUTRO_IMG = card("시연 결과 요약",
                 [f"사진 7장 분석 {an_s:.1f}초 (사진 전송 포함)",
                  f"방문지 6곳 확정 = 자동 확정 {n_auto}곳 + 사용자 선택 {n_ask}곳",
                  "위치 없는 사진 1장 → 추천 방문지에 배정",
                  f"여행기 작성 {st_s:.1f}초 · " + (f"서버 LLM({model}) 작성" if by_llm else "템플릿 여행기로 대체 (D-04)")],
                 ["처리 시간: 녹화 중 측정값 (분석 시작 → 결과 화면, 여행기 만들기 → 여행기 화면)"])
INTRO, OUTRO, XFADE = 4.5, 5.5, 0.4
TOTAL = INTRO + DUR + OUTRO


def frame_at(v):
    p = v / TOTAL
    if v < INTRO:
        if v > INTRO - XFADE:
            return Image.blend(INTRO_IMG, phone_frame(0, p), (v - (INTRO - XFADE)) / XFADE)
        return INTRO_IMG
    v -= INTRO
    if v < DUR:
        img = phone_frame(v, p)
        if v > DUR - XFADE:
            img = Image.blend(img, OUTRO_IMG, (v - (DUR - XFADE)) / XFADE)
        return img
    return OUTRO_IMG


chapters = [[round(INTRO + first_step_time(n) - T0, 1), f"{CIRC[n - 1]} {STEPS[n][0]}"] for n in range(1, 7)]
info = {"video_seconds": round(TOTAL, 1), "chapters": chapters, "facts": FACTS}
Path(str(OUT) + ".chapters.json").write_text(json.dumps(info, ensure_ascii=False, indent=1))
print(json.dumps(info, ensure_ascii=False)[:600])

if PREVIEW:
    for v in PREVIEW:
        frame_at(v).save(OUT.parent / f"preview_{v:06.1f}.jpg", quality=90)
    sys.exit()

n = int(TOTAL * FPS)
ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                       "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                       "-profile:v", "high", "-level", "4.1", "-movflags", "+faststart", str(OUT)], stdin=subprocess.PIPE)
for k in range(n):
    v = k / FPS
    ff.stdin.write(frame_at(v).tobytes())
    if k % (FPS * 15) == 0:
        print(f"{v:6.1f}s / {TOTAL:.1f}s", flush=True)
ff.stdin.close()
ff.wait()
print("done", OUT, round(TOTAL, 1), "s")
