"""Mermaid(.mmd) → PNG (로컬 헤드리스 Chromium, 맑은 고딕). 사용: python render.py <mmd 폴더> <출력 폴더> [이름...]"""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright
SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
NAMES = sys.argv[3:] or [p.stem for p in sorted(SRC.glob("*.mmd"))]
HERE = Path(__file__).resolve().parent
CHROME = "/home/geonhan/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"
BASE = {
    "theme": "base", "fontFamily": "Pretendard", "markdownAutoWrap": False,
    "themeVariables": {
        "fontFamily": "Pretendard", "fontSize": "20px",
        "primaryColor": "#EEECFC", "primaryBorderColor": "#5B4BE0", "primaryTextColor": "#16181D",
        "secondaryColor": "#F3F4F6", "tertiaryColor": "#F3F4F6", "lineColor": "#4B5059",
        "clusterBkg": "#F7F7FB", "clusterBorder": "#B8B1F0",
        "actorBkg": "#EEECFC", "actorBorder": "#5B4BE0", "actorTextColor": "#16181D", "actorLineColor": "#A7ABB3",
        "signalColor": "#4B5059", "signalTextColor": "#16181D", "labelBoxBkgColor": "#5B4BE0", "labelBoxBorderColor": "#5B4BE0",
        "labelTextColor": "#FFFFFF", "loopTextColor": "#16181D", "noteBkgColor": "#FFF4D1", "noteBorderColor": "#E0B84B",
        "activationBkgColor": "#DCD8FA", "activationBorderColor": "#5B4BE0", "sequenceNumberColor": "#FFFFFF",
        "edgeLabelBackground": "#FFFFFF",
    },
    "sequence": {"useMaxWidth": False, "mirrorActors": False, "messageFontSize": 19, "actorFontSize": 19, "noteFontSize": 17, "actorMargin": 46,
                 "messageMargin": 30, "boxMargin": 8, "width": 190, "height": 56, "showSequenceNumbers": True,
                 "messageFontFamily": "Pretendard", "actorFontFamily": "Pretendard"},
    "class": {"padding": 8, "useMaxWidth": False},
    "state": {"useMaxWidth": False},
    "flowchart": {"subGraphTitleMargin": {"top": 6, "bottom": 22}, "useMaxWidth": False, "htmlLabels": True, "curve": "basis", "nodeSpacing": 40, "rankSpacing": 55},
}
async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--allow-file-access-from-files"])
        pg = await (await b.new_context(viewport={"width": 3200, "height": 2400}, device_scale_factor=2)).new_page()
        await pg.goto((HERE / "render_uml.html").as_uri())
        for n in NAMES:
            code = (SRC / f"{n}.mmd").read_text()
            w, h = await pg.evaluate("([c, cfg]) => window.renderDiagram(c, cfg)", [code, BASE])
            await pg.locator("#out").screenshot(path=str(OUT / f"{n}.png"))
            print(n, round(w), "x", round(h))
        await b.close()
asyncio.run(main())
