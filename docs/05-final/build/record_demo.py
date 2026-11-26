"""시연 영상 녹화 (휴대폰 웹 브라우저): CDP 화면 전송(screencast)으로 프레임을 받고,
터치·스크롤·강조 상자·단계 설명·주소 입력 시점을 따로 기록한다 (합성은 compose_demo.py).

사용: python record_demo.py <공개 주소> <출력 폴더> <사진 폴더> [--shots] [--size 360x800]
- 브라우저: Chromium, 휴대폰 화면 크기 390×844(CSS px) · 기기 배율 2 · 터치 입력 (실제 휴대폰 아님)
- 휴대폰 브라우저처럼 위 상태 표시줄 24px·주소창 56px, 아래 버튼 줄 48px를 빼고 웹 페이지 영역(390×716)만 녹화.
  상태 표시줄·주소창·버튼 줄은 compose_demo.py가 그린다
- 빈 화면에서 공개 주소를 입력해 실제로 접속하는 장면부터 녹화 (주소 입력 시각은 events의 url_type, 접속은 nav_start·nav_end)
- 매번 새 기기 토큰으로 시작 → 빈 첫 화면 (공개 서버는 3일 지난 여행을 자동 삭제)
- --shots: 단계마다 화면 캡처를 따로 저장하고 가로 넘침(가로 스크롤 생김)을 기록 (사전 점검·화면 배치 확인용)
- --size: 휴대폰 화면 크기 (기본 390x844, 명세서 UI-08 최소 폭 확인은 360x800)
"""
import asyncio, base64, json, re, secrets, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

U, OUT, PHOTO_DIR = sys.argv[1].rstrip("/"), Path(sys.argv[2]), Path(sys.argv[3])
PHOTOS = sorted(PHOTO_DIR.glob("*.jpg"))
SHOTS = "--shots" in sys.argv
CHROME = "/home/geonhan/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"
VW, SCREEN_H, DSF = 390, 844, 2
if "--size" in sys.argv:
    VW, SCREEN_H = (int(x) for x in sys.argv[sys.argv.index("--size") + 1].split("x"))
CHROME_TOP, CHROME_BOTTOM = 24 + 56, 48  # 상태 표시줄 + 주소창, 아래 버튼 줄 (CSS px)
VH = SCREEN_H - CHROME_TOP - CHROME_BOTTOM  # 웹 페이지 영역 높이
CTA_TOP = VH - 104  # 아래 고정 버튼 띠 위쪽 경계 (이 아래는 가려짐)
HOST = U.split("://", 1)[-1]
TYPE_DUR = 2.4  # 주소 입력 장면 길이 (초)


class Rec:
    def __init__(self, page, ctx, token):
        self.page, self.ctx, self.token = page, ctx, token
        self.dir = OUT / "phone"
        self.dir.mkdir(parents=True, exist_ok=True)
        for f in self.dir.glob("*.jpg"):
            f.unlink()
        self.frames, self.events, self.errors, self.facts = [], [], [], {}
        self.nshot, self.hl_on = 0, False
        page.on("pageerror", lambda e: self.errors.append(str(e)[:200]))
        page.on("response", lambda r: self.errors.append(f"HTTP {r.status} {r.url[-70:]}") if r.status >= 400 else None)

    async def start(self):
        self.cdp = await self.ctx.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.t0 = time.time()
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": VW * DSF, "maxHeight": VH * DSF,
                                                     "everyNthFrame": 1})
        await asyncio.sleep(0.6)

    def _frame(self, p):
        ts = p["metadata"].get("timestamp") or time.time()
        fn = f"{len(self.frames):05d}.jpg"
        (self.dir / fn).write_bytes(base64.b64decode(p["data"]))
        self.frames.append((ts, fn))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]}))

    def log(self, kind, **kw):
        self.events.append({"t": time.time(), "kind": kind, **kw})

    def step(self, n, line):
        """오른쪽 설명 칸: n단계의 line번째 줄(여러 줄이면 목록) 강조 (문구는 compose_demo.py의 STEPS)."""
        self.log("step", n=n, line=line if isinstance(line, list) else [line])
        print(f"{time.time() - self.t0:6.1f}s  step {n}.{line}  {self.page.url[len(U):]}", flush=True)

    async def shot(self, name):
        if SHOTS:
            self.nshot += 1
            await self.page.screenshot(path=str(OUT / f"shot_{self.nshot:02d}_{name}.png"))
            over = await self.page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            self.facts.setdefault("overflow_px", {})[name] = over

    async def box(self, loc):
        """요소 위치가 멈출 때까지 기다린 뒤 상자 (CSS px, 화면 기준)."""
        await loc.wait_for(state="visible", timeout=60000)
        prev, b = None, None
        for _ in range(25):
            b = await loc.bounding_box()
            cur = tuple(round(b[k]) for k in ("x", "y", "width", "height"))
            if cur == prev:
                break
            prev = cur
            await asyncio.sleep(0.1)
        return b["x"], b["y"], b["width"], b["height"]

    def off(self):
        if self.hl_on:
            self.log("hl_off")
            self.hl_on = False

    async def scroll(self, dy, gap=0.03):
        """휴대폰 화면 스크롤: 헤드리스에서는 터치 끌기가 안 돼 휠로 굴리고, 손가락 표시는 합성 때 그린다."""
        self.off()
        steps = max(10, min(30, int(abs(dy) / 20)))
        x, y = VW / 2, VH * 0.58
        self.log("swipe", x=x, y=y, dy=dy, dur=steps * gap)
        await self.page.mouse.move(x, y)
        for _ in range(steps):
            await self.page.mouse.wheel(0, dy / steps)
            await asyncio.sleep(gap)
        await asyncio.sleep(0.3)

    async def reveal(self, loc, top=76, bottom=CTA_TOP):
        """요소가 화면(아래 고정 버튼 띠 제외) 안에 들어오도록 천천히 스크롤."""
        for _ in range(4):
            x, y, w, h = await self.box(loc)
            if y >= top and y + h <= bottom:
                return
            dy = (y + h - bottom + 28) if y + h > bottom else (y - top - 28)
            if h > bottom - top:
                dy = y - top - 12
            await self.scroll(dy)
            if abs((await self.box(loc))[1] - y) < 2:  # 더 움직이지 않음 (끝)
                return

    async def tap(self, loc, pause=0.35, files=None, reveal=True):
        if reveal:
            await self.reveal(loc)
        x, y, w, h = await self.box(loc)
        await asyncio.sleep(pause)
        self.off()
        self.log("tap", x=x + w / 2, y=y + h / 2)
        if files is not None:
            async with self.page.expect_file_chooser() as fc:
                await loc.tap()
            await (await fc.value).set_files(files)
        else:
            await loc.tap()

    async def hl(self, loc, pad=5, reveal=True):
        """강조 상자 (다음 터치·스크롤 때까지 표시)."""
        if reveal:
            await self.reveal(loc)
        x, y, w, h = await self.box(loc)
        self.log("hl", x=x - pad, y=y - pad, w=w + 2 * pad, h=h + 2 * pad)
        self.hl_on = True

    async def hold(self, s):
        await asyncio.sleep(s)

    async def api(self, path):
        return await self.page.evaluate(
            """async ([p, t]) => { const r = await fetch('/api/v1' + p, {headers: {'X-Device-Token': t}});
                return r.ok ? await r.json() : {status: r.status}; }""", [path, self.token])

    async def stop(self):
        self.off()
        await asyncio.sleep(0.4)
        await self.cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.3)
        meta = {"name": "phone", "vw": VW, "vh": VH, "dsf": DSF, "screen_h": SCREEN_H, "chrome_top": CHROME_TOP,
                "chrome_bottom": CHROME_BOTTOM, "url": U, "host": HOST, "t0": self.t0, "t_end": time.time(), "frames": self.frames,
                "events": self.events, "errors": self.errors, "facts": self.facts}
        (OUT / "phone.json").write_text(json.dumps(meta, ensure_ascii=False, indent=0))
        print("frames", len(self.frames), "dur", round(meta["t_end"] - self.t0, 1), "errors", self.errors, "facts", self.facts)


def vis(page, sel, **kw):
    return page.locator(", ".join(x.strip() + ":visible" for x in sel.split(",")), **kw).first


async def flow(r, pg):
    # ⓪ 공개 주소 접속: 빈 화면 → 주소창에 주소 입력 → 실제 접속 ----------------------------
    r.step(1, 0)
    await r.hold(1.0)
    r.log("url_type", text=HOST, dur=TYPE_DUR)
    await r.hold(TYPE_DUR + 0.5)
    r.log("nav_start")
    t_nav = time.time()
    await pg.goto(U + "/", wait_until="networkidle")
    await pg.get_by_role("button", name="사진으로 새 여행기 만들기").wait_for(timeout=60000)
    r.facts["load_s"] = round(time.time() - t_nav, 2)
    r.log("nav_end")
    await r.hold(1.2)

    # ① 사진 업로드 ------------------------------------------------------------
    r.step(1, 1)
    await r.hold(2.4)
    await r.tap(pg.get_by_role("button", name="사진으로 새 여행기 만들기"))
    await pg.wait_for_url(re.compile("/upload"))
    await r.hold(1.6)
    await r.shot("upload")
    r.step(1, 2)
    await r.tap(vis(pg, "button", has_text="갤러리에서 선택"), files=[str(f) for f in PHOTOS])
    await pg.locator(".photo-grid .cell").nth(len(PHOTOS) - 1).wait_for(timeout=60000)
    await r.hold(0.6)
    await r.hl(pg.locator(".photo-grid"))
    await r.hold(3.4)
    await r.shot("picked")
    r.step(1, 3)
    await r.tap(pg.locator("label.check"))
    await r.hold(0.5)
    await r.hl(pg.locator("label.check"), pad=8)
    await r.hold(2.6)
    r.step(1, 4)
    await r.hl(pg.locator("label.check + ul"), pad=8)
    await r.hold(3.4)
    await r.shot("consent")
    t_an = time.time()
    r.log("timer_start", key="analysis")
    await r.tap(pg.locator(".bottom-cta.mobile-only button"), reveal=False)

    # ② AI 장소 판별 ------------------------------------------------------------
    await pg.wait_for_url(re.compile(r"/analyzing"), timeout=60000)
    r.step(2, 0)
    trip_id = re.search(r"/trips/([^/]+)/", pg.url).group(1)
    line = 0
    while not re.search(r"/visits$", pg.url):
        done = await pg.locator(".stage.done").count()
        want = 0 if done < 2 else (1 if done < 3 else 2)
        if want > line:
            line = want
            r.step(2, line)
        if time.time() - t_an > 240:
            raise TimeoutError("분석이 4분 안에 끝나지 않음")
        await asyncio.sleep(0.2)
    r.facts["analysis_s"] = round(time.time() - t_an, 1)
    r.log("timer_stop", key="analysis")
    await pg.locator(".visit-card").first.wait_for(timeout=30000)
    await r.shot("visits")
    trip = await r.api(f"/trips/{trip_id}")
    r.facts["trip"] = {k: trip.get(k) for k in ("visit_count", "photo_count", "status")} if isinstance(trip, dict) else trip
    r.facts["chips"] = await pg.locator(".visit-card .chip, .visit-card [class*='chip']").all_inner_texts()
    await r.hold(1.0)
    r.step(2, 3)
    await r.hl(pg.locator(".visit-card").first)
    await r.hold(3.4)
    await r.scroll(330)
    await r.hold(1.6)
    r.step(2, 4)
    ask = pg.locator(".visit-card", has_text=re.compile("선택필요|확인필요")).first
    await r.hl(ask)
    await r.hold(3.4)
    await r.shot("visits2")

    # ③ 사용자 확인 -------------------------------------------------------------
    await r.tap(pg.locator(".bottom-cta button", has_text="장소 확인하기"), reveal=False)
    await pg.wait_for_selector("text=이 사진, 어디서 찍었나요?", timeout=30000)
    await r.hold(1.4)
    r.step(3, 0)
    await r.shot("placecheck")
    await r.hl(vis(pg, ".reason"))
    await r.hold(4.8)
    r.step(3, 1)
    cand = pg.locator("button.cand").first
    await r.tap(cand)
    await r.hold(0.4)
    await r.hl(cand)
    await r.hold(2.4)
    await r.shot("cand")
    await r.tap(vis(pg, ".bottom-cta button", has_text="이 장소로 확정"), reveal=False)
    await pg.wait_for_url(re.compile(r"/visits$"), timeout=30000)
    await r.hold(1.6)
    r.step(3, 2)
    await r.tap(pg.locator(".bottom-cta button", has_text="위치 없는 사진 배정하기"), reveal=False)
    await pg.wait_for_url(re.compile("/untagged"))
    await pg.locator("button:has-text('이 방문지에 넣기')").first.wait_for(timeout=30000)
    await r.hold(1.2)
    await r.shot("untagged")
    card = pg.locator(".card", has=pg.locator("button:has-text('이 방문지에 넣기')")).first
    await r.hl(card.locator(".small").nth(1))
    await r.hold(5.0)
    r.step(3, 3)
    await r.hl(card.locator("select"))
    await r.hold(2.2)
    await r.tap(pg.locator("button:has-text('이 방문지에 넣기'):not([disabled])").first)
    try:
        await pg.wait_for_url(re.compile("/done"), timeout=8000)
    except Exception:
        await r.tap(vis(pg, ".bottom-cta button", has_text="확정 완료"), reveal=False)
        await pg.wait_for_url(re.compile("/done"))
    await r.hold(1.0)
    await r.shot("done")
    await r.hold(2.8)

    # ④ 동선 지도 ---------------------------------------------------------------
    await r.tap(vis(pg, "a, button", has_text="동선 보기"), reveal=False)
    await pg.wait_for_url(re.compile("/route"))
    await r.hold(1.0)
    r.step(4, 0)
    await pg.locator(".sheet .place-card").first.wait_for(timeout=30000)
    await r.hold(3.4)
    await r.shot("route_map")
    await r.tap(pg.get_by_role("tab", name="2일차"), reveal=False)
    await r.hold(3.4)
    await r.tap(pg.get_by_role("tab", name="1일차"), reveal=False)
    await r.hold(1.2)
    r.step(4, 1)
    await r.tap(vis(pg, ".route-switch button", has_text="타임라인"), reveal=False)
    await r.hold(1.0)
    await r.hl(vis(pg, ".leg"), pad=4)
    await r.hold(4.0)
    await r.shot("route_timeline")
    r.step(4, 2)
    await r.tap(vis(pg, "button.tl-item", has_text="오륙도"))
    await pg.wait_for_url(re.compile("/places/"))
    await r.hold(1.6)
    await r.shot("place")
    await r.hl(vis(pg, "dl.kv"))
    await r.hold(4.2)
    await r.tap(vis(pg, "button[aria-label='뒤로']"), reveal=False)
    await pg.wait_for_url(re.compile("/route"))
    await r.hold(1.0)

    # ⑤ 출처 있는 여행기 --------------------------------------------------------
    await r.tap(vis(pg, ".bottom-cta button", has_text="여행기 만들기"), reveal=False)
    await pg.wait_for_url(re.compile("/story/new"))
    await r.hold(1.2)
    r.step(5, 0)
    await r.shot("style")
    blog = vis(pg, "button", has_text="블로그형")
    await r.tap(blog)
    await r.hold(0.4)
    await r.hl(blog)
    await r.hold(2.4)
    t_st = time.time()
    r.log("timer_start", key="story")
    await r.tap(vis(pg, ".bottom-cta button", has_text="여행기 만들기"), reveal=False)
    r.step(5, [1, 2])
    await pg.wait_for_url(re.compile(r"/stories/[^/]+$"), timeout=300000)
    r.facts["story_s"] = round(time.time() - t_st, 1)
    r.log("timer_stop", key="story")
    story_id = re.search(r"/stories/([^/?#]+)", pg.url).group(1)
    st = await r.api(f"/stories/{story_id}")
    if isinstance(st, dict):
        r.facts["story_model"] = st.get("model")
        r.facts["story_ai_label"] = (st.get("meta") or {}).get("ai_label")
        r.facts["story_removed"] = len((st.get("meta") or {}).get("removed") or [])
        r.facts["story_footnotes"] = len(st.get("footnotes") or [])
    await pg.locator(".j-text").wait_for(timeout=30000)
    await pg.wait_for_timeout(800)
    await r.shot("story")
    await r.hold(2.0)
    r.step(5, 3)
    await r.scroll(400)
    await r.hold(0.8)
    # 장소 이름 링크와 출처 번호가 함께 있는 문장 중 줄 수가 가장 적은 문장 (확대했을 때 옆 문장이 덜 섞이게)
    cands = pg.locator(".j-text span:has(a.place-link):has(sup)")
    best, best_h = 0, 1e9
    for i in range(min(await cands.count(), 8)):
        b = await cands.nth(i).bounding_box()
        if b and b["height"] < best_h - 1:
            best, best_h = i, b["height"]
    sent = cands.nth(best)
    await r.hl(sent, pad=4)
    await r.hold(4.4)
    await r.shot("story2")
    r.step(5, 4)
    link = sent.locator("sup a").first
    frag = ((await link.get_attribute("href")) or "").split("#")[-1]
    await r.tap(link)
    await r.hold(1.0)
    # 누른 출처 번호의 항목 (목록 첫 항목은 화면 위로 벗어날 수 있음)
    await r.hl(pg.locator(f"[id='{frag}']") if frag else vis(pg, ".footnotes li"), pad=4)
    await r.hold(4.0)
    await r.shot("sources")

    # ⑥ 공유 카드 ---------------------------------------------------------------
    r.step(6, 0)
    await r.scroll(-4000)
    await r.hold(0.6)
    await r.tap(vis(pg, "button[aria-label='더 보기']"), reveal=False)
    await r.hold(0.9)
    await r.tap(pg.get_by_role("menuitem", name="공유 카드 만들기"), reveal=False)
    await pg.wait_for_url(re.compile("/share"))
    img = pg.locator("img[alt='공유 카드 미리보기']")
    await img.wait_for(timeout=30000)
    await r.hold(1.0)
    await r.hl(img, reveal=False)
    await r.hold(4.0)
    await r.shot("share")
    r.step(6, 1)
    await r.hl(vis(pg, ".notice", has_text="좌표"))
    await r.hold(4.6)
    await r.shot("share2")


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=[f"--force-device-scale-factor={DSF}"])
        ctx = await b.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=DSF, is_mobile=True, has_touch=True,
                                  locale="ko-KR", timezone_id="Asia/Seoul")
        token = "demo" + secrets.token_hex(12)
        await ctx.add_init_script(f"try {{ localStorage.setItem('chalkak.deviceToken', '{token}'); localStorage.removeItem('chalkak.theme') }} catch (e) {{}}")
        pg = await ctx.new_page()
        await pg.goto(U + "/", wait_until="networkidle")  # 미리 한 번 열어 둠 (터널·정적 파일 준비)
        await pg.wait_for_timeout(1000)
        await pg.goto("about:blank")  # 빈 화면에서 주소 입력부터 녹화
        await pg.wait_for_timeout(500)
        r = Rec(pg, ctx, token)
        await r.start()
        try:
            await flow(r, pg)
        except Exception as e:
            print("ERROR", type(e).__name__, str(e)[:400], pg.url)
            await pg.screenshot(path=str(OUT / "phone_error.png"))
            r.facts["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        finally:
            await r.stop()
            (OUT / "token.txt").write_text(token)
            await ctx.close()
            await b.close()

asyncio.run(main())
