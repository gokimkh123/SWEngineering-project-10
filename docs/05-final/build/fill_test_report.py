"""테스트 결과서(Word) 생성 — 강의 템플릿 docs/03_테스트_보고서_템플릿.docx의 서식은 그대로 두고 내용만 채운다.

기준 문서: 요구사항 명세서 v1.0 (docs/submission/02_요구사항분석서_찰칵부산_Team10.docx, 2026-10-26).
근거 데이터: docs/05-final/tests/*_1125.json (11/25 결함 수정 배포 후 공개 서버 재실행, 11/23 첫 실행은 이름에 날짜 없는 파일), backend pytest 87개.
문구 원본: build/tc_text.json (기능 테스트 케이스), build/requirements_trace.json (요구사항별 결과·명세서와 다른 점) — PPT와 함께 사용.
사용: python fill_test_report.py <템플릿.docx> <tests 폴더> <출력.docx>
"""
import copy
import json
import re
import sys
from pathlib import Path

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.text.run import Run
from docx.table import Table
from docx.text.paragraph import Paragraph

TEMPLATE, TESTS, OUT = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
HERE = Path(__file__).resolve().parent
tc = json.loads((TESTS / "tc_results_1125.json").read_text(encoding="utf-8"))
sec = json.loads((TESTS / "security_1125.json").read_text(encoding="utf-8"))
nfr = json.loads((TESTS / "nfr_result_1125.json").read_text(encoding="utf-8"))
ev = json.loads((TESTS / "vlm_eval_1125.json").read_text(encoding="utf-8"))  # 정확도 대체 평가 (웹 사진 27곳)
cand = json.loads((TESTS / "candidate_inclusion.json").read_text(encoding="utf-8"))
TCT = json.loads((HERE / "tc_text.json").read_text(encoding="utf-8"))
TRACE = json.loads((HERE / "requirements_trace.json").read_text(encoding="utf-8"))
REQS, DIFFS, STATES = TRACE["requirements"], TRACE["differences"], TRACE["states"]
BENCH = json.loads((HERE / "deck_data.json").read_text(encoding="utf-8"))["bench"]  # 모델 선택 시험 (정식 NFR-02 아님)

d = docx.Document(TEMPLATE)
body = d.element.body


# ------------------------------------------------------------------ 편집 도구 (템플릿 서식 유지)
def set_par(p: Paragraph, text: str, bold=None):
    """첫 run의 서식을 살려 글자만 바꾼다 (템플릿은 낱말마다 run이 나뉘어 있음)."""
    runs = p.runs
    if not runs:
        r = p.add_run(text)
        if bold is not None:
            r.bold = bold
        return p
    runs[0].text = text
    if bold is not None:
        runs[0].bold = bold
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    return p


def set_cell(cell, text, bold=None, donor=None):
    """셀 글자 교체. 줄바꿈(\n)은 같은 서식의 문단을 복제해 나눈다. 빈 셀은 같은 행의 run(donor) 서식을 빌린다."""
    lines = str(text).split("\n")
    ps = cell.paragraphs
    first = ps[0]
    for extra in ps[1:]:
        extra._p.getparent().remove(extra._p)
    if not first.runs and donor is not None:
        first._p.append(copy.deepcopy(donor))
    set_par(first, lines[0], bold)
    prev = first
    for ln in lines[1:]:
        np_ = copy.deepcopy(first._p)
        prev._p.addnext(np_)
        prev = Paragraph(np_, first._parent)
        set_par(prev, ln, bold)


def clone_row(table: Table, src_idx: int):
    tr = copy.deepcopy(table.rows[src_idx]._tr)
    table._tbl.append(tr)
    return table.rows[-1]


def fill_rows(table: Table, rows, src_idx=1, bold_first=False):
    """머리 행은 두고, src_idx 행을 본으로 필요한 만큼 행을 만든 뒤 채운다."""
    while len(table.rows) > src_idx + 1:
        table._tbl.remove(table.rows[-1]._tr)
    for _ in range(len(rows) - 1):
        clone_row(table, src_idx)
    for r, vals in zip(table.rows[src_idx:], rows):
        donor = next((copy.deepcopy(run._r) for c in r.cells for p in c.paragraphs for run in p.runs), None)
        if donor is not None:
            for b in donor.findall(qn("w:rPr") + "/" + qn("w:b")):
                b.getparent().remove(b)
        for i, (c, v) in enumerate(zip(r.cells, vals)):
            set_cell(c, v, bold=True if (bold_first and i == 0) else None, donor=donor)


def set_widths(table: Table, inches):
    tblPr = table._tbl.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = tblPr.makeelement(qn("w:tblW"), {})
        tblPr.append(tblW)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(int(sum(inches) * 1440)))
    lay = tblPr.find(qn("w:tblLayout"))  # 고정 너비: Word 자동 맞춤이 좁은 칸(TC ID)을 줄이지 않게
    if lay is None:
        lay = tblPr.makeelement(qn("w:tblLayout"), {})
        after = [tblPr.find(qn(t)) for t in ("w:tblCellMar", "w:tblLook", "w:tblCaption", "w:tblDescription")]
        after = next((e for e in after if e is not None), None)
        if after is not None:
            after.addprevious(lay)
        else:
            tblPr.append(lay)
    lay.set(qn("w:type"), "fixed")
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), inches):
        gc.set(qn("w:w"), str(int(w * 1440)))
    for r in table.rows:
        for c, w in zip(r.cells, inches):
            c.width = Inches(w)


def par_after(anchor, like: Paragraph, text: str):
    """like 문단(스타일 견본)을 복제해 anchor 뒤에 넣는다."""
    el = copy.deepcopy(like._p)
    anchor_el = anchor._p if isinstance(anchor, Paragraph) else anchor._tbl
    anchor_el.addnext(el)
    return set_par(Paragraph(el, like._parent), text)


def table_after(anchor, like: Table):
    el = copy.deepcopy(like._tbl)
    anchor_el = anchor._p if isinstance(anchor, Paragraph) else anchor._tbl
    anchor_el.addnext(el)
    return Table(el, like._parent)


def find_par(prefix: str) -> Paragraph:
    return next(p for p in d.paragraphs if p.text.strip().startswith(prefix))


def next_table(p: Paragraph) -> Table:
    el = p._p.getnext()
    while el is not None and el.tag != qn("w:tbl"):
        el = el.getnext()
    return Table(el, p._parent)


def next_par(p: Paragraph) -> Paragraph:
    el = p._p.getnext()
    while el is not None and el.tag != qn("w:p"):
        el = el.getnext()
    return Paragraph(el, p._parent)


def remove(x):
    el = x._p if isinstance(x, Paragraph) else x._tbl
    el.getparent().remove(el)


BULLET = next(p for p in d.paragraphs if p.style.name == "List Bullet")
NORMAL_BODY = find_par("[테스트의 목적과 범위]")
H2 = find_par("1.1 목적")


def bullets_after(anchor, items):
    last = anchor
    for it in items:
        last = par_after(last, BULLET, it)
    return last


def allow_split(table: Table):
    """본문 행을 쪽 경계에서 나눌 수 있게 함 (긴 행 때문에 쪽 끝에 큰 빈칸이 생기지 않게, 머리 행은 쪽마다 반복)."""
    for tr in table._tbl.tr_lst[1:]:
        for cs in tr.findall(qn("w:trPr") + "/" + qn("w:cantSplit")):
            cs.getparent().remove(cs)


def keep_lead(table: Table, rows=2):
    """표 바로 앞 문단(제목)과 머리 행·첫 행을 같은 쪽에 둠 (쪽 끝에 제목과 머리 행만 남지 않게)."""
    prev = table._tbl.getprevious()
    if prev is not None and prev.tag == qn("w:p"):
        Paragraph(prev, table._parent).paragraph_format.keep_with_next = True
    for row in table.rows[:rows]:
        for c in row.cells:
            for par in c.paragraphs:
                par.paragraph_format.keep_with_next = True


def set_header(table: Table, names):
    for c, t in zip(table.rows[0].cells, names):
        set_cell(c, t)


def set_rich(p: Paragraph, parts):
    """문단을 [(글자, 굵게 여부), …]로 채움 — 핵심 수치만 굵게 강조할 때 사용."""
    set_par(p, parts[0][0], bold=parts[0][1])
    base = p.runs[0]._r
    prev = base
    for text, bold in parts[1:]:
        r = copy.deepcopy(base)
        prev.addnext(r)
        prev = r
        run = Run(r, p)
        run.text = text
        run.bold = bold


def status_grid(anchor):
    """요구사항 20개 판정 현황: 색칠한 칸(표)으로 한 번에 보이게 — Word에서 그대로 고칠 수 있는 기본 표."""
    fill = {"충족": "DCD8FA", "조건부": "F8D9A8", "부분": "FBF1E3", "미실시": "E9EAEE"}
    ink = {"충족": "3F33B5", "조건부": "8A5A12", "부분": "8A5A12", "미실시": "6B7079"}
    t = d.add_table(rows=4, cols=6)
    t.style = d.styles["Table Grid"]
    anchor._p.addnext(t._tbl)
    tblPr = t._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "24"); el.set(qn("w:space"), "0"); el.set(qn("w:color"), "FFFFFF")
        borders.append(el)
    nxt = next((tblPr.find(qn(x)) for x in ("w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook") if tblPr.find(qn(x)) is not None), None)
    nxt.addprevious(borders) if nxt is not None else tblPr.append(borders)

    def paint(cell, color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), color)
        tcPr.append(shd)

    def write(cell, lines):  # lines: [(글자, 크기pt, 굵게, 색)]
        ps = cell.paragraphs
        for i, (text, size, bold, color) in enumerate(lines):
            para = ps[0] if i == 0 else cell.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.space_before = Pt(0); para.paragraph_format.space_after = Pt(0)
            r = para.add_run(text); r.font.size = Pt(size); r.bold = bold; r.font.color.rgb = RGBColor.from_string(color)

    reqs_fr = [q for q in REQS if q["id"].startswith("FR")]
    reqs_nf = [q for q in REQS if q["id"].startswith("NFR")]
    for i, q in enumerate(reqs_fr):
        c = t.cell(i // 6, i % 6); paint(c, fill[q["state"]]); write(c, [(q["id"], 8.5, True, ink[q["state"]]), (q["name"], 7, False, "4B5059")])
    for i, q in enumerate(reqs_nf):
        c = t.cell(2 + i // 4, i % 4); paint(c, fill[q["state"]]); write(c, [(q["id"], 8.5, True, ink[q["state"]]), (q["name"], 7, False, "4B5059")])
    lg = t.cell(2, 4).merge(t.cell(3, 5))
    paint(lg, "FFFFFF")
    ps = lg.paragraphs
    for i, (k, v) in enumerate(fill.items()):
        para = ps[0] if i == 0 else lg.add_paragraph()
        para.paragraph_format.space_before = Pt(0); para.paragraph_format.space_after = Pt(0)
        r = para.add_run("■ "); r.font.size = Pt(10); r.font.color.rgb = RGBColor.from_string({"충족": "5B4BE0", "조건부": "D9902C", "부분": "F0C98A", "미실시": "C9CBD2"}[k])
        r2 = para.add_run(f"{k}  {sum(1 for q in REQS if q['state'] == k)}개"); r2.font.size = Pt(8); r2.bold = True; r2.font.color.rgb = RGBColor.from_string(ink[k])
    set_widths(t, [1.153] * 6)
    return t


# ------------------------------------------------------------------ 표지 (역할: 팀 확정 11/24)
cover = d.tables[0]
cover_vals = {
    "프로젝트명": "찰칵부산: 여행 사진으로 방문지·동선·출처 있는 여행기를 만드는 부산 여행 서비스",
    "팀명": "2026-2 소프트웨어공학 Team 10",
    "팀원": "김건한 / 2243219 / 테스트·PM\n김예슬 / 2443358 / 백엔드\n전규민 / 2229930 / 프론트엔드·테스트\n황웅재 / 2243416 / 백엔드",
    "버전": "v1.0 (최종 제출본)",
    "작성일": "2026-11-25",
    "담당교수": "임한신",
}
for r in cover.rows:
    k = r.cells[0].text.strip()
    if k in cover_vals:
        set_cell(r.cells[1], cover_vals[k])

# 문서 관리: 실제 이력 한 줄만
hist = next_table(find_par("문서 관리"))
fill_rows(hist, [["1.0", "2026-11-25", "김건한",
                  "최종 제출본 작성: 요구사항 명세서 v1.0 기준으로 기능 테스트 15개, 보안 점검 11개, 비기능 측정, 자동 테스트 87개 결과와 결함 7건(모두 수정) 정리, 11/25 재실행 결과 반영"]])
set_widths(hist, [0.6, 1.0, 0.8, 4.52])

# ------------------------------------------------------------------ 1. 테스트 개요
set_par(NORMAL_BODY, "요구사항 명세서 v1.0(2026-10-26 제출)의 요구사항을 최종 구현이 충족하는지 확인함")
bullets_after(NORMAL_BODY, [
    "기준 문서: 요구사항 명세서 v1.0(제출 파일 02_요구사항분석서), 기능 요구사항 12개(FR-01~12) · 비기능 요구사항 8개(NFR-01~08) · 인수 기준 17개(AC-01~17)",
    "확인 방법: 인수 기준(AC)마다 테스트 케이스(TC) 연결(5장) · 명세서와 다른 점은 5.1, 계획서·설계서 대비는 5.2에 정리",
])
scope = find_par("1.2 테스트 대상/제외 범위")
b1, b2 = next_par(scope), next_par(next_par(scope))
set_par(b1, "대상: 웹 화면(React), API 서버(FastAPI), 작업 큐(Redis/RQ)와 워커, AI 분석(VLM 장소 판별·LLM 여행기 작성), "
            "데이터 저장(PostgreSQL·썸네일), 공개 배포 구성(nginx·Cloudflare 터널), 설계서 컴포넌트 CP-01~CP-19")
set_par(b2, "제외: 외부 서비스의 내부 동작(Cloudflare, OpenStreetMap 지도, Ollama 모델 내부)")
bullets_after(b2, [
    "장소 데이터: 공공데이터 API 키를 발급받지 못해, 같은 형식의 샘플 장소 40곳으로 테스트함 (키 발급 후 재측정 필요, 5.1 참조)",
    "계획 대비 미실시: 실제 휴대폰(iOS Safari·Android Chrome) 테스트(NFR-06), 팀 외 5명 사용성 테스트(NFR-05) (6장 참조)",
])

env = next_table(find_par("1.3 테스트 환경"))
env_rows = [
    ["OS", "서버 PC: Windows 11 Pro + Docker Desktop 28.2(WSL2), 컨테이너 7개(web·api·worker·vlm·postgres·redis·tunnel)\n"
           "AMD Ryzen 9 7950X3D(16코어) · RAM 32GB · NVIDIA RTX 4080 SUPER 16GB"],
    ["Browser", "Chromium(Playwright) 데스크톱 1280×660 · 모바일 390×844·360×800 화면 크기"],
    ["Backend", "Python 3.12.16 · FastAPI 0.162.0 · SQLAlchemy 2.1.8 · RQ 2.12.0(워커 1개) · scikit-learn 1.9.1(DBSCAN 방문지 묶기) · "
                "Pillow 13.0.0 · pillow-heif 1.8.1(HEIC)"],
    ["Database", "PostgreSQL 17.12 · Redis 7.4.12(작업 큐)"],
    ["AI Model/API", "Ollama 0.40.17 · qwen3.5:4b(VLM 장소 판별·LLM 여행기 작성 공용, GPU 실행) · 비교 평가: qwen3.5:2b·9b"],
    ["Frontend·배포", "React 18.3.1 · Vite 5.4.11 · Leaflet 1.9.4 · nginx 1.31.7 · cloudflared 2026.10.0(무료 Quick Tunnel)"],
    ["테스트 도구", "pytest 9.2.0 · 자동 실행 스크립트(tc_run.py·security_run.py·nfr_container.py, httpx) · nvidia-smi·docker stats(자원 측정) · "
                "gitleaks(비밀값 검사) · Playwright(화면 녹화)"],
]
fill_rows(env, env_rows, bold_first=True)
set_widths(env, [1.25, 5.67])

# 1.4 용어 정리 (처음 읽는 사람용)
h14 = par_after(env, H2, "1.4 용어 정리")
terms = table_after(h14, env)
set_header(terms, ["용어", "뜻"])
fill_rows(terms, [
    ["FR / NFR / AC / UC", "기능 요구사항 / 비기능 요구사항 / 인수 기준 / 유스케이스 (명세서 v1.0 번호 그대로)"],
    ["EXIF", "사진 파일에 저장된 촬영 시각·위치(GPS) 정보"],
    ["VLM / LLM", "사진을 보고 답하는 AI / 글을 쓰는 AI (이 서비스는 둘 다 서버의 qwen3.5:4b 사용)"],
    ["확신도", "AI가 고른 장소가 맞을 가능성(0~1): 0.8 이상 '자동확정', 0.5~0.8 '확인필요', 0.5 미만 '선택필요'"],
    ["템플릿 여행기", "LLM 응답이 실패하거나 형식이 틀릴 때, 공식 데이터 문장으로 만드는 대체 여행기"],
    ["워커", "작업 큐에 등록된 사진 분석·여행기 작성 작업을 차례로 처리하는 프로그램"],
], bold_first=True)
set_widths(terms, [1.5, 5.42])

# ------------------------------------------------------------------ 2. 테스트 전략 (담당: 팀 역할 기준)
strat_h = find_par("2. 테스트 전략")
strat = next_table(strat_h)
set_cell(strat.rows[0].cells[3], "담당")
fill_rows(strat, [
    ["단위\n(Unit)", "모듈·함수 검증", "주요 컴포넌트 테스트 51개: 촬영 정보 추출, 방문지 묶기(DBSCAN), 후보 검색, 장소 판별(후보에 없는 답 거부), 사실 대조 등",
     "황웅재·김예슬", "pytest"],
    ["통합\n(Integration)", "컴포넌트 연결 검증", "API·DB·작업 큐·AI 연결 흐름 17개(인수 기준 번호별, 모의 AI·장애 상황 포함), 명세서 보완 5개, 공개 운영 안전장치 14개",
     "황웅재·김예슬", "pytest · FastAPI TestClient"],
    ["시스템\n(System)", "전체 요구사항 검증", "공개 서버 기능 테스트 15개, 보안 점검 11개, 비기능 측정(성능·부하·자원·개인정보)",
     "김건한·전규민", "자동 실행 스크립트(httpx) · nvidia-smi · docker stats · gitleaks"],
    ["인수\n(Acceptance)", "사용자 요구 충족 확인", "주요 유스케이스 시연(UC-01~06·08·09, 사진 7장, 휴대폰 화면 크기) · UC-07은 TC-13, 팀 외 5명 사용성 테스트(미실시)",
     "김건한·전규민", "Playwright 녹화(시연 영상)"],
], bold_first=True)
set_widths(strat, [0.95, 1.05, 2.72, 0.95, 1.25])
bullets_after(strat, [
    "기능 테스트 케이스: 명세서의 유스케이스 흐름·인수 기준에서 도출(블랙박스, 강의 8주차 형식)",
    "통합 테스트: 테스트 이름에 인수 기준 번호 표기(예: test_ac01_upload_limits) · 명세서 9장 시나리오(사진 24장: 위치 있음 21장·없음 3장, "
    "방문지 6곳)를 같은 구성의 생성 사진과 모의 AI로 자동 확인함",
])

# ------------------------------------------------------------------ 3. 테스트 케이스
tc_h = find_par("3. 테스트 케이스")
tct = next_table(tc_h)
rows = []
for r in tc["results"]:
    t = TCT[r["id"]]
    rows.append([r["id"], t["req"].replace(" / ", "\n"), t["item"], t["pre"], t["input"], t["expected"], t["actual"],
                 "Pass" if r["pass"] else "Fail", t["note"]])
fill_rows(tct, rows, bold_first=True)
set_widths(tct, [0.58, 0.86, 0.78, 0.7, 0.92, 0.95, 0.99, 0.45, 0.69])
allow_split(tct)
run_at = tc["run_at"].replace("T", " ")[:16]
intro = par_after(tc_h, H2, "3.1 기능 테스트 케이스")
bullets_after(intro, [
    f"실행 일시: {run_at}, 공개 주소(Cloudflare 터널)에서 자동 실행 스크립트(tc_run.py)로 수행",
    "공통 사전조건: 서버 정상 동작, 기기 토큰 발급 완료 · 원본 결과: tests/tc_results_1125.json · 관련 요구사항 칸: 명세서의 요구사항/유스케이스/인수 기준 번호",
])

# 3.2 자동 테스트 · 3.3 결함 목록
h32 = par_after(tct, H2, "3.2 자동 테스트 (pytest 87개 모두 Pass, 18.9초, 11/25 재실행)")
hist_like = next_table(find_par("문서 관리"))
auto = table_after(h32, hist_like)
set_header(auto, ["구분", "테스트 파일", "개수", "결과"])
fill_rows(auto, [
    ["단위", "test_unit_components.py: 촬영 정보 추출·방문지 묶기·후보 검색·장소 판별·사실 대조(한자·시간대 포함)·조사 처리", "51", "51 Pass"],
    ["통합", "test_api_flow.py: 인수 기준(AC)별 흐름, 업로드→분석→확인→여행기→공유→삭제, 외부 API 장애 모의", "17", "17 Pass"],
    ["명세서 보완", "test_spec_gaps.py: 기타 장소 저장·600m 확대·HEIC·PNG 위치 추출·캐시 적중·가짜 키 비노출", "5", "5 Pass"],
    ["공개 운영", "test_public_mode.py: 사용 한도·자동 삭제·날짜별 여행기 생성·실패한 날만 대체·잘린 응답 거부·작성 방식 표시", "14", "14 Pass"],
], bold_first=True)
set_widths(auto, [0.9, 4.32, 0.7, 1.0])
h33 = par_after(auto, H2, "3.3 결함 목록")
nfr_like = next_table(find_par("4. 비기능 테스트"))
defects = table_after(h33, nfr_like)
set_header(defects, ["ID", "결함 내용", "심각도", "발견", "조치", "상태"])
fill_rows(defects, [
    ["D-01", "문단 다시 쓰기 결과가 이전 문단과 같음(LLM이 같은 문단을 반환)", "중간\n(Medium)", "TC-13 1차 실행 (11/23)",
     "재요청 시 생성 조건(temperature·seed) 변경, 그래도 같으면 템플릿 문단으로 교체, 자동 테스트 추가", "수정 완료 (재실행 Pass)"],
    ["D-02", "방문 시각이 들어간 문장('10시에 감천문화마을로…')을 사실 대조가 근거 없음으로 삭제하여 여행기에서 장소 이름이 빠짐",
     "중간\n(Medium)", "시연 리허설 (11/23)", "사진 기록의 방문 시각·날짜를 근거로 인정, 자동 테스트 3개 추가", "수정 완료"],
    ["D-03", "위치 없는 사진 추천 문구의 조사 오류('감천문화마을와')", "낮음\n(Low)", "시연 리허설 (11/23)",
     "받침 유무에 따라 '과/와' 선택", "수정 완료"],
    ["D-04", "방문지 14곳 여행에서 LLM 여행기 응답이 10회 중 9회 잘려 템플릿으로 대체(원인: 입력+출력이 문맥 4096토큰 초과) · Must FR-09에 영향",
     "높음\n(High)", "비기능 측정 (11/23)", "날짜별·방문지 5곳 단위로 나눠 생성, 잘린 응답 거부, 실패한 날만 템플릿 · 재측정 LLM 작성 10/10회", "수정 완료 (11/25 재측정)"],
    ["D-05", "대기 중 워커가 약 6분 40초마다 Redis 연결 시간 초과로 종료·재시작(11/25까지 282회)", "낮음\n(Low)",
     "서버 로그 점검 (11/24)", "작업 대기 주기를 45초로 줄임(소켓 시간 초과가 설정보다 약 3% 일찍 남) · 배포 후 20분 재시작 0회", "수정 완료 (11/25)"],
    ["D-06", "템플릿으로 쓴 여행기에도 'AI가 … 작성한 글' 문구가 표시됨", "낮음\n(Low)", "재점검 (11/24)",
     "문단마다 작성 방식 기록, 템플릿 문단은 '공식 데이터 문장으로 자동 작성' 표시, 공유 카드 문구도 구분", "수정 완료 (11/25)"],
    ["D-07", "LLM 여행기에 한자 시간 표현('午時가 되면')이 섞이고 실제 방문 시각(15:05)과 다름 · 사실 대조가 놓침",
     "중간\n(Medium)", "시연 녹화 (11/25)", "사실 대조에 한자·시간대 표현 검사 추가, 자동 테스트 7개 · 실제 여행기 52문장 재검사(오삭제 0)", "수정 완료 (11/25)"],
], bold_first=True)
set_widths(defects, [0.5, 2.16, 0.74, 0.95, 1.77, 0.8])
keep_lead(defects)

# ------------------------------------------------------------------ 4. 비기능 테스트 (품질 속성·목표는 명세서 4장 표현 그대로)
runs = nfr["phases"]["nfr01"]["runs"]
p1 = nfr["phases"]["nfr01"]
conc = nfr["phases"]["concurrency"]
load = nfr["phases"]["api_load"]
pv = nfr["privacy"]
llm_runs = [r for r in runs if not r["model"].startswith("템플릿")]
llm_par, all_par = sum(r.get("llm_paragraphs", 0) for r in runs), sum(r.get("paragraphs", 0) for r in runs)
ev_pct = f"{ev['correct'] / ev['n']:.1%}"
tpl_runs = [r for r in runs if r["model"].startswith("템플릿")]
facts = sum(r["facts"] for r in runs)
noted = sum(r["facts_with_note"] for r in runs)
cand_scored = [c for c in cand if c.get("included") is not None]  # 정답이 '없음'인 4건은 후보 포함률 계산에서 제외
cand_in = sum(1 for c in cand_scored if c["included"])
def bench_acc(m):  # 정답 장소가 있는 항목만(정답 '없음' 시험 4건은 따로)
    rows = BENCH[m]["rows"]
    lab = [r for r in rows if r["truth"] != "none"]; trap = [r for r in rows if r["truth"] == "none"]
    return sum(r["ok"] for r in lab), len(lab), sum(r["ok"] for r in trap), len(trap), len({r["truth"] for r in lab})
b2, b4, b9 = bench_acc("qwen3.5:2b"), bench_acc("qwen3.5:4b"), bench_acc("qwen3.5:9b")
trips_load = [r for r in load if r["path"] == "/trips"]
nfr_t = nfr_like
nfr_h = find_par("4. 비기능 테스트")
fill_rows(nfr_t, [
    ["NFR-01", "성능 (응답시간)", "사진 20장 분석 시간(업로드 완료~방문지 확인 화면), 20장 세트 10회", "1분 이내 (10회 평균)",
     f"평균 {p1['analysis_avg']}초 · 최대 {p1['analysis_max']:.1f}초 · 최소 {p1['analysis_min']:.1f}초", "Pass"],
    ["NFR-01", "성능 (부하, 추가 측정)", "동시 분석 1·2·4건(각 20장), 가장 늦게 끝난 작업", "1분 이내",
     " / ".join(f"{c['n']}건 {c['max_s']:.1f}초" for c in conc)
     + f" · 처리량 분당 {min(c['photos_per_min'] for c in conc):.0f}~{max(c['photos_per_min'] for c in conc):.0f}장", "Pass"],
    ["참고", "성능 (API 응답, 추가 측정)", "여행 목록 API에 동시 10·50·100개 접속, 각 8초", "오류 0건",
     f"오류 0건(총 {sum(r['requests'] for r in trips_load):,}건) · 95% 응답 시간(p95) " + " / ".join(f"{r['p95_ms']:.0f}ms" for r in trips_load), "Pass"],
    ["NFR-02", "정확도", "방문지 단위 정확도(AI 1순위 정답 ÷ 전체 방문지), 팀 촬영 평가셋(방문지 20곳 이상)", "80% 이상",
     f"웹 공개 사진 {ev['n']}곳 대체 평가(팀 촬영 아님): 정답 {ev['correct']}/{ev['n']} ({ev_pct}) · 확신 오답 {ev['confident_wrong']}건 · "
     f"AI '없음' {ev['statuses'].get('선택필요', 0)}곳은 사용자 선택", "Pass (조건부)"],
    ["NFR-02", "정확도 (후보 포함률)", "정답 장소가 후보 목록에 들어 있는 비율", "90% 이상",
     f"{ev['included']}/{ev['n']} ({ev['included'] / ev['n']:.0%}): 같은 웹 사진 대체 평가 · 샘플 40곳이라 방문지당 후보가 1~3곳으로 적음", "Pass (조건부)"],
    ["NFR-03", "신뢰성 (출처)", "여행기 사실 문장의 출처 표시율, 여행기 10회(시스템이 사실로 분류한 문장)", "100%",
     f"{noted}/{facts} (100%): LLM 작성 {len(llm_runs)}/10회(문단 {llm_par}/{all_par}) · 11/23에는 9회 템플릿(D-04 수정) · 사람 전수 검토 미실시", "Pass (조건부)"],
    ["NFR-04", "개인정보 보호", "동의 후 분석, 외부 AI 미전송, 원본·좌표 삭제, 썸네일 위치 정보, 삭제 후 남은 데이터 (AC-09)", "남은 데이터 0건",
     f"동의 없는 분석 거부(TC-03) · 원본 {pv['originals_left']}장 · 좌표 {pv['coords_left']}건 · 썸네일 위치 정보 {pv['gps_in_thumbs']}/{pv['photos']} · "
     f"삭제 후 DB {pv['after_delete_rows']}행·파일 {pv['after_delete_thumbs']}개 · 외부 AI 호출 없음 · 인물 분석 안 함(프롬프트 규칙, 테스트 없음)", "Pass"],
    ["NFR-05", "사용성", "팀 외 5명이 안내 없이 업로드부터 여행기까지 걸린 시간 (AC-11)", "5분 이내",
     "미실시 (팀 시연 기준 업로드~여행기 약 2분) · 확인이 필요한 방문지만 묻는 동작은 TC-05로 확인", "미실시"],
    ["NFR-06", "호환성 (이식성)", "iOS Safari·Android Chrome 모바일 웹 (AC-12)", "실기기에서 정상 동작",
     "실기기 미실시 · Chromium 390×844·360×800 에뮬레이션으로 화면 배치만 확인(가로 넘침 0px)", "미실시"],
    ["NFR-07", "보안", "서버 API 키 노출(저장소·화면 코드, AC-15) + 공개 서버 보안 점검 11항목(4.1)", "노출 0건",
     f"gitleaks 0건(파일 474개) · JS 서버 키 0건 · 보안 점검 {sum(1 for c in sec['checks'] if c['pass'])}/{len(sec['checks'])} · "
     "가짜 키 비노출 테스트 · API 키 미발급 상태(키 설정 후 재점검)", "Pass (조건부)"],
    ["NFR-08", "비용·가용성 (오류 복구)", "외부 API 실패 시 동작(AC-16), 운영 비용", "무료·저가 요금 안 동작, 실패 시 오류 안내·재시도",
     f"장애 모의 테스트 4개 통과(장애 난 방문지만 '선택필요') · LLM 작성 {len(llm_runs)}/10회(D-04 수정) · 워커 재시작 0회(D-05 수정) · "
     "재분석 캐시 적중(자동 테스트) · 운영 비용 0원",
     "Pass (조건부)"],
], bold_first=True)
set_widths(nfr_t, [0.62, 0.95, 1.6, 0.7, 2.25, 0.8])
allow_split(nfr_t)
bullets_after(nfr_h, [
    "측정 방법: 11/25 결함 수정 배포 후 일회용 worker 컨테이너에서 API를 직접 호출함(nginx 요청 제한 제외) · 사진 20장 세트(위치 없는 사진 1장 포함) · 원본: tests/nfr_result_1125.json",
    "보안 점검: 11/25 공개 주소로 외부 사용자와 같은 경로에서 수행함 · 원본: tests/security_1125.json · 정확도 평가 원본: tests/vlm_eval_1125.json",
    "목표 칸: 명세서 4장 기준 값 · 판정: 충족(명세서대로) · 조건부(다른 조건·대체 평가) · 부분(일부만 확인) · 미실시",
])

# 4.1 보안 점검 — 기대·실제 결과는 '뜻(코드)' 순서로 다시 적음 (원본 문구는 tests/security.json)
SEC_TEXT = [
    ("API 문서", "API 문서·스키마 비공개", "비공개(404)", "문서 주소 3개(docs·openapi.json·redoc) 모두 404"),
    ("시연용", "시연용 데이터 생성 주소 차단", "차단(404)", "404"),
    ("기기 토큰", "기기 토큰 없는 요청 거부", "거부(401)", "401"),
    ("경로 조작", "경로 조작(../)으로 서버 파일 접근 불가", "파일 내용 노출 없음(앱 화면 또는 404)", "앱 화면(200) 또는 404 · 파일 내용 노출 0건"),
    ("다른 기기", "다른 기기의 여행 접근 차단", "조회 불가(404)", "404"),
    ("위장", "이미지로 위장한 파일 거부", "접수 0장", "접수 0장 · 사유 '이미지 파일이 아니에요'"),
    ("45MB", "요청당 45MB 초과 업로드 차단", "차단(413)", "413"),
    ("요청 폭주", "요청 폭주 제한 (IP당 초당 15회·순간 40회)", "한도 초과분 제한(429)", None),
    ("보안 헤더", "보안 헤더 (CSP·HSTS·X-Frame-Options 등)", "6종 적용", "6종 모두 적용 · X-Frame-Options DENY"),
    ("서버 버전", "서버 버전 비노출", "버전 숫자 없음", "Server: cloudflare (버전 숫자 없음)"),
    ("JS", "화면 코드(JS)에 서버 키 없음", "0건", "화면 코드 파일 1개 검사 · 발견 0건"),
]
assert len(SEC_TEXT) == len(sec["checks"])
sec_rows = []
for i, (c, (key, item, exp, act)) in enumerate(zip(sec["checks"], SEC_TEXT), 1):
    assert key in c["item"], (key, c["item"])
    if act is None:
        m = re.search(r"동시 (\d+)회 요청 → 200 (\d+)회 · 429 (\d+)회", c["actual"])
        act = f"동시 {m.group(1)}회 요청 → 정상(200) {m.group(2)}회 · 제한(429) {m.group(3)}회"
    sec_rows.append([f"S-{i:02d}", item, exp, act, "Pass" if c["pass"] else "Fail"])
h41 = par_after(nfr_t, H2, "4.1 보안 점검 상세 (NFR-07, 공개 주소)")
trace_like = next_table(find_par("5. 요구사항-테스트 추적표"))
sect = table_after(h41, trace_like)
set_header(sect, ["No", "점검 항목", "기대 결과", "실제 결과", "판정"])
fill_rows(sect, sec_rows, bold_first=True)
set_widths(sect, [0.55, 2.2, 1.45, 2.12, 0.6])
r1 = nfr["resources"]["nfr01"]
h42 = par_after(sect, H2, "4.2 자원 사용량 (20장 10회 분석 구간)")
g1 = bullets_after(h42, ["GPU"])
set_rich(g1, [("GPU: 사용률 평균 ", False), (f"{r1['gpu_util_avg']:.0f}%", True), (" · 메모리 최대 ", False), (f"{r1['vram_max_mib'] / 1024:.1f}GB", True),
              ("(16GB 중) · 상세: tests/nfr_result_1125.json", False)])

# ------------------------------------------------------------------ 5. 추적표 (요구사항 명세서 v1.0 기준) · 5.1 명세서와 다른 점
FINAL = {"충족": "검증 완료(Verified)", "조건부": "검증 완료(조건부)", "부분": "미완료(Open)", "미실시": "미완료(Open)"}
trace = trace_like
h5 = find_par("5. 요구사항-테스트 추적표")
b5 = bullets_after(h5, [
    "요구사항 20개 판정(아래 색 칸, 판정 뜻은 4장과 같음) · Test Case 칸은 '인수 기준(AC): 테스트' · 통합 테스트 이름에 AC 번호 사용(AC-02는 단위 테스트)",
])
grid = status_grid(b5)
gap = par_after(grid, NORMAL_BODY, "")  # 색 칸과 추적표 사이 한 줄
fill_rows(trace, [[f"{q['id']} {q['name']}", f"{q['ac']}: {q['tests']}", q["result"], q["issue"], FINAL[q["state"]]] for q in REQS],
          bold_first=True)
set_widths(trace, [1.95, 1.7, 0.72, 1.25, 1.3])
allow_split(trace)
h51 = par_after(trace, H2, "5.1 명세서 v1.0과 다른 점 (7건은 v2.0에 반영)")
diff = table_after(h51, hist_like)
set_header(diff, ["요구사항", "명세서 v1.0", "실제 구현·테스트", "판단·조치"])
fill_rows(diff, [[x["req"], x["spec"], x["actual"], x["action"]] for x in DIFFS], bold_first=True)
set_widths(diff, [1.2, 1.75, 2.45, 1.52])
allow_split(diff)
# 5.2 중간 산출물 중 계획서·설계서 대비 (요구사항 명세서는 5장·5.1)
h52 = par_after(diff, H2, "5.2 계획서·설계서 대비 확인")
pdt = table_after(h52, hist_like)
set_header(pdt, ["항목", "계획서·설계서 v1.0", "실제", "판단"])
fill_rows(pdt, [[x["item"], x["plan"], x["actual"], x["judge"]] for x in TRACE["plan_design"]], bold_first=True)
set_widths(pdt, [1.15, 1.8, 2.55, 1.42])
allow_split(pdt)

# ------------------------------------------------------------------ 6. 결론
fr = [q for q in REQS if q["id"].startswith("FR")]
nf = [q for q in REQS if q["id"].startswith("NFR")]
ids = lambda st: "·".join(q["id"].replace("NFR-", "") for q in nf if q["state"] == st)  # 예: "02·08"
met = sum(1 for q in nf if q["state"] in ("충족", "조건부"))
fr_met = sum(1 for q in fr if q["state"] in ("충족", "조건부"))
fr_cond = "·".join(q["id"] for q in fr if q["state"] == "조건부")
concl = find_par("6. 테스트 결과 요약 및 결론")
items = [next_par(concl)]
for _ in range(3):
    items.append(next_par(items[-1]))
set_rich(items[0], [("전체 테스트 케이스: 기능 테스트 ", False), (f"{len(tc['results'])}개", True), (" + 보안 점검 ", False), (f"{len(sec['checks'])}개", True),
                    (" (자동 테스트 87개는 별도)", False)])
set_rich(items[1], [("Pass: 기능 ", False), (f"{sum(1 for r in tc['results'] if r['pass'])}개", True), (" · 보안 ", False), (f"{sum(1 for c in sec['checks'] if c['pass'])}개", True),
                    (" · 자동 ", False), ("87개", True), (" / Fail: ", False), ("0개", True), (" (TC-13은 1차 Fail → D-01 수정 후 Pass)", False)])
st = lambda arr, k: sum(1 for q in arr if q["state"] == k)
set_rich(items[2], [("미해결 Critical/High 결함: ", False), ("0개", True), (" (D-01~D-07 모두 수정, 11/25 재실행 확인)", False)])
set_rich(items[3], [("릴리스 가능 여부 및 근거: ", False), ("조건부 릴리스", True),
                    (" (결함 모두 수정 · 기능 ", False),
                    (f"충족 {st(fr, '충족')}", True), (f"·조건부 {st(fr, '조건부')}·부분 {st(fr, '부분')}, 비기능 ", False),
                    (f"충족 {st(nf, '충족')}", True), (f"·조건부 {st(nf, '조건부')}·미실시 {st(nf, '미실시')})", False)])
final = next_par(items[3])
set_par(final, "최종 평가: 주요 흐름 정상 동작 · 남은 과제: 실기기·사용성, 팀 촬영 사진 정확도, 키 연동 후 재측정")
last_final = final
ai_note = par_after(last_final, NORMAL_BODY,
                    "AI 활용 명기: " + TRACE["ai_note"])
for r in ai_note.runs:
    r.italic = True

d.core_properties.title = "테스트 및 품질 보고서: 찰칵부산 Team 10"
d.core_properties.author = "Team 10"
d.save(OUT)
print("saved", OUT)
