"""최종 설계서(v2.0) 생성: 중간 설계서 v1.0(docx)의 표지·머리글·문단·표 서식은 그대로 두고 본문을 최종 구현 기준으로 다시 쓴다.

- 1~3장: v1.0의 구조(개요, 아키텍처, 컴포넌트)를 유지하고 최종 구현(11/25)에 맞게 고침
- 2.6절(신규): 중간 설계 대비 수정사항 (강의 최종발표 기준 '2. 시스템 아키텍처 수정사항')
- 4장(신규): UML 설계(클래스·도메인 모델·화면). v1.0에서 '최종 설계서에서 작성'으로 남긴 상세 설계 (강의 기준 '4. UML 설계')
- 그림: docs/05-final/uml/*.png (Mermaid 원본 .mmd), 화면 캡처는 build/img/screens_360.png
- 측정값: docs/05-final/tests/*_1125.json (11/25 재측정)
- 글쓰기: 문어체 개조식, 쉬운 말, 과장 표현·줄표 쓰지 않음
사용: python make_design_doc.py <v1.0 설계서 docx> <출력 docx>
"""
import copy
import json
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.table import Table
from docx.text.paragraph import Paragraph

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
HERE = Path(__file__).resolve().parent
F = HERE.parent
UML, TESTS = F / "uml", F / "tests"
TRACE = json.loads((HERE / "requirements_trace.json").read_text(encoding="utf-8"))


def load(name):
    p = TESTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


NFR = load("nfr_result_1125.json")
EVAL = load("vlm_eval_1125.json")

d = docx.Document(SRC)
body = d.element.body


# ------------------------------------------------------------------ 서식 도우미 (fill_test_report.py와 같은 방식)
def set_par(p: Paragraph, text: str, bold=None):
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


def fill_rows(table: Table, rows, src_idx=1, bold_first=False):
    while len(table.rows) > src_idx + 1:
        table._tbl.remove(table.rows[-1]._tr)
    for _ in range(len(rows) - 1):
        table._tbl.append(copy.deepcopy(table.rows[src_idx]._tr))
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
    lay = tblPr.find(qn("w:tblLayout"))
    if lay is None:
        lay = tblPr.makeelement(qn("w:tblLayout"), {})
        after = next((e for e in (tblPr.find(qn(t)) for t in ("w:tblCellMar", "w:tblLook", "w:tblCaption")) if e is not None), None)
        if after is not None:
            after.addprevious(lay)
        else:
            tblPr.append(lay)
    lay.set(qn("w:type"), "fixed")
    for gc, w in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), inches):
        gc.set(qn("w:w"), str(int(w * 1440)))
    for r in table.rows:
        for c, w in zip(r.cells, inches):
            c.width = Inches(w)


def keep_lead(table: Table, rows=2):
    """표 머리 행·첫 행과 바로 앞 문단을 같은 쪽에 둔다."""
    prev = table._tbl.getprevious()
    if prev is not None and prev.tag == qn("w:p"):
        Paragraph(prev, table._parent).paragraph_format.keep_with_next = True
    for row in table.rows[:rows]:
        for c in row.cells:
            for par in c.paragraphs:
                par.paragraph_format.keep_with_next = True


# ------------------------------------------------------------------ 견본 (본문을 지우기 전에 복사)
paras = d.paragraphs
P_H1 = copy.deepcopy(next(p for p in paras if p.text.strip() == "1. 개요")._p)
P_H2 = copy.deepcopy(next(p for p in paras if p.text.strip() == "1.1 목적")._p)
P_BUL = copy.deepcopy(next(p for p in paras if p.style.name == "List Bullet")._p)
P_FIG = copy.deepcopy(next(p for p in paras if p._p.findall(".//" + qn("w:drawing")))._p)
P_CAP = copy.deepcopy(next(p for p in paras if p.text.startswith("그림 2-1"))._p)
P_SUB = copy.deepcopy(next(p for p in paras if p.text.startswith("(1) 사진 분석"))._p)
P_PLAIN = copy.deepcopy(next(p for p in paras if p.text.startswith("의존 규칙"))._p)
P_AI = copy.deepcopy(paras[-1]._p)
P_GAP = copy.deepcopy(next(p for p in paras if not p.text.strip() and not p._p.findall(".//" + qn("w:drawing")) and p.style.name == "Normal")._p)
tables = d.tables
T_BY_COLS = {}
for t in tables[2:]:
    T_BY_COLS.setdefault(len(t.columns), copy.deepcopy(t._tbl))

# 표지·문서 관리
cover = tables[0]
cover_vals = {
    "프로젝트명": "찰칵부산: 여행 사진으로 방문지·동선·출처 있는 여행기를 만드는 부산 여행 서비스",
    "팀원": "김건한 / 2243219 / 테스트·PM\n김예슬 / 2443358 / 백엔드\n전규민 / 2229930 / 프론트엔드·테스트\n황웅재 / 2243416 / 백엔드",
    "버전": "v2.0 (최종 제출본)",
    "작성일": "2026-11-25",
}
for r in cover.rows:
    k = r.cells[0].text.strip()
    if k in cover_vals:
        set_cell(r.cells[1], cover_vals[k])
hist = tables[1]
hist._tbl.append(copy.deepcopy(hist.rows[-1]._tr))
row = hist.rows[-1]
for c, v in zip(row.cells, ["2.0", "2026-11-25", "김건한",
                            "최종 제출본: 최종 구현(11/25) 기준으로 1~3장 수정, 2.6절 수정사항·4장 UML 설계(클래스·도메인 모델·화면·알고리즘) 추가, "
                            "결함 수정(D-04~D-07) 반영"]):
    set_cell(c, v)

note = next(p for p in d.paragraphs if p.text.startswith("요구사항 ID("))
set_par(note, "요구사항 ID(FR, NFR, UI, DR, AIR, AC)와 유스케이스 ID(UC-01~09)는 요구사항 명세서 v2.0 기준(ID는 v1.0과 같음). 이 문서에서 정의하는 ID: "
              "QA(품질 속성), AD(아키텍처 결정), CP(컴포넌트), IF(인터페이스). 중간 설계(v1.0, 10/26)와 다른 부분은 2.6절에 정리")

# 본문(1. 개요부터) 삭제
start = next(p for p in d.paragraphs if p.text.strip() == "1. 개요")._p
el = start
while el is not None and el.tag != qn("w:sectPr"):
    nxt = el.getnext()
    body.remove(el)
    el = nxt

cur = [note._p]


def put(el):
    cur[0].addnext(el)
    cur[0] = el
    return el


def par(tpl, text, bold=None):
    el = put(copy.deepcopy(tpl))
    return set_par(Paragraph(el, note._parent), text, bold)


def h1(t):
    return par(P_H1, t)


def h2(t):
    return par(P_H2, t)


def bul(*items):
    for t in items:
        par(P_BUL, t)


def sub(t):
    return par(P_SUB, t)


def plain(t):
    return par(P_PLAIN, t)


def gap():
    put(copy.deepcopy(P_GAP))


def figure(path: Path, caption: str, width=6.3):
    el = put(copy.deepcopy(P_FIG))
    for r in list(el.findall(qn("w:r"))):
        el.remove(r)
    p = Paragraph(el, note._parent)
    p.add_run().add_picture(str(path), width=Inches(width))
    p.paragraph_format.keep_with_next = True
    par(P_CAP, caption)


def table(header, rows, widths, bold_first=True):
    tpl = T_BY_COLS[len(header)]
    el = put(copy.deepcopy(tpl))
    t = Table(el, note._parent)
    for c, v in zip(t.rows[0].cells, header):
        set_cell(c, v)
    fill_rows(t, rows, bold_first=bold_first)
    set_widths(t, widths)
    keep_lead(t)
    gap()
    return t


# ------------------------------------------------------------------ 측정값 요약
def nfr_numbers():
    if not NFR:
        return {}
    n1 = NFR["phases"]["nfr01"]
    runs = n1["runs"]
    conc = {r["n"]: r for r in NFR["phases"].get("concurrency", [])} if isinstance(NFR["phases"].get("concurrency"), list) else {}
    return {"avg": n1["analysis_avg"], "max": n1["analysis_max"], "story": n1["story_avg"],
            "llm_par": sum(r.get("llm_paragraphs", 0) for r in runs), "par": sum(r.get("paragraphs", 0) for r in runs),
            "noted": sum(r["facts_with_note"] for r in runs), "facts": sum(r["facts"] for r in runs), "conc": conc}


N = nfr_numbers()
perf = f"평균 {N['avg']}초·최대 {N['max']}초" if N else "평균 7.5초 (11/23)"
llm_share = f"LLM 작성 문단 {N['llm_par']}/{N['par']}, 사실 문장 출처 {N['noted']}/{N['facts']}" if N else "-"
acc = (f"웹 공개 사진 평가셋(장소 {EVAL['n']}곳) 정확도 {EVAL['correct']}/{EVAL['n']} · 확신 오답 {EVAL['confident_wrong']}건"
       if EVAL else "정식 평가 미실시")

# ================================================================== 1. 개요
h1("1. 개요")
h2("1.1 목적")
bul("요구사항 명세서 v2.0의 기능·품질 요구사항을 실현한 최종 구조 기록",
    "중간 설계(v1.0, 10/26)에서 바뀐 결정과 그 이유 기록 (2.6절)",
    "3.4절 매핑과 테스트 결과서 5장 추적표는 같은 요구사항 번호 사용")
h2("1.2 범위")
bul("2장 시스템 아키텍처(품질 속성, 스타일과 결정, 전체 구조, 동작 흐름·상태, 배포, 중간 설계 대비 수정사항) · 3장 컴포넌트 설계(책임, "
    "외부 인터페이스, 의존관계, 요구사항 매핑) · 4장 UML 설계(클래스, 도메인 모델·데이터베이스, 화면, 주요 알고리즘)",
    "기준 구현: backend(FastAPI·RQ 워커), frontend(React), docker-compose.yml(컨테이너 7개), 11/25 공개 서버 배포본")
h2("1.3 설계 원칙")
table(["원칙", "아키텍처에 반영한 방식"], [
    ["AI 사용 범위 제한", "VLM·LLM 호출은 AI Gateway(CP-19) 한 곳에서만 처리. 방문지 묶기·후보 조회·사실 대조는 코드로 처리"],
    ["후보 안에서만 판별", "Place Matcher(CP-11)가 공식 데이터 후보 목록 밖의 답을 코드로 거부"],
    ["사실 문장마다 출처", "여행기 문장마다 장소 ID·근거 필드를 받고 Fact Checker(CP-14)가 전수 대조, 통과한 사실 문장에만 각주"],
    ["원본 비보관", "원본 사진·좌표는 분석이 끝나면 삭제(CP-17), 썸네일은 위치 정보 제거. 사진은 서버 안 AI만 분석"],
    ["변경 요소 격리", "외부 장소 API와 AI 모델은 어댑터(CP-18·19) 뒤에 배치. 실제로 LLM을 외부 API에서 Ollama로 바꿀 때 다른 컴포넌트 수정 없음"],
], [1.6, 5.3])

# ================================================================== 2. 아키텍처 설계
h1("2. 시스템 아키텍처 설계")
h2("2.1 품질 속성 시나리오")
bul("비기능 요구사항을 '자극 → 응답 → 측정' 시나리오로 바꾸고 설계 전술 지정. 결과 칸은 11/25 공개 서버 재측정(사진 20장 세트 10회) 기준")
table(["ID (요구사항)", "시나리오 (자극 → 응답 → 측정)", "설계 전술 (최종)", "결과"], [
    ["QA-01 성능\n(NFR-01)", "사진 20장 업로드를 마치면 → 방문지 확인 화면 준비 → 60초 이내",
     "작업 큐 + 워커, 방문지별 VLM 동시 2개, 대표 사진 1장 512px 축소, 장소 캐시", perf],
    ["QA-02 정확도\n(NFR-02)", "VLM이 후보 밖 장소·틀린 형식을 답하면 → 거부 후 1회 재요청 → 잘못된 자동 확정 0건",
     "후보 안에서만 선택(closed-set), JSON 스키마, 확신도 0.8·0.5 기준 분기, 매칭 로그", acc],
    ["QA-03 신뢰성\n(NFR-03)", "여행기를 만들면 → 사실 문장마다 근거 장소·출처 연결 → 출처 표시율 100%",
     "문장별 장소 ID·필드 태깅, 날짜별·5곳 단위 생성, 사실 대조(수치·장소·한자·시간대), 근거 없는 문장 제거", llm_share],
    ["QA-04 개인정보\n(NFR-04)", "분석이 끝나면 → 원본 사진·좌표 삭제 → 서버 잔존 0건",
     "임시 저장 + 종료 시 삭제 + 30분 주기 정리, 위치 정보 없는 썸네일, 공개 서버 3일 뒤 자동 삭제",
     "원본 0 · 좌표 0 · 썸네일 위치 0 · 삭제 후 0"],
    ["QA-05 변경 용이성", "AI 모델·제공처를 바꾸면 → AI Gateway와 설정만 수정",
     "어댑터, 환경변수로 공급자 선택(fake·ollama·anthropic·gemini), 프롬프트 버전 기록", "LLM 외부 API → Ollama 교체 시 다른 코드 수정 0건"],
    ["QA-06 가용성·비용\n(NFR-08)", "외부 API가 실패하면 → 2회 재시도 후 그 방문지만 사용자 선택 → 전체 작업 실패 없음",
     "시간 제한·재시도, 방문지 단위 실패 격리, 장소 캐시, LLM 실패한 날만 템플릿 문단", "장애 모의 테스트 통과 · 운영 비용 0원"],
    ["QA-07 보안\n(NFR-07)", "저장소·화면 코드를 검사하면 → 서버 API 키 없음 → 노출 0건",
     "키는 서버 환경변수에만, 외부 호출은 서버 경유, 터널(열린 포트 0개), 요청 수 제한·보안 헤더", "보안 점검 11/11 통과"],
    ["QA-08 테스트 용이성", "파이프라인을 테스트하면 → 외부 API·GPU 없이 같은 결과 재현",
     "순수 함수 분리(CP-08·09·14), 모의 AI·샘플 데이터 주입, 장애 주입", "자동 테스트 87개 통과"],
], [1.15, 2.0, 2.2, 1.55], bold_first=True)

h2("2.2 아키텍처 스타일과 결정")
bul("스타일 후보 비교: A 단일 서버·동기 처리(분석 중 요청이 수십 초 묶이고 화면 이탈 시 작업 유실)와 C 마이크로서비스(4명·4주에 운영 부담 과다)는 제외, "
    "B 계층형 + 비동기 작업 큐 채택(긴 작업 분리·진행률 조회, 큐·워커 운영 요소 추가는 감수). 최종 구현까지 유지")
table(["ID", "결정 (최종)", "이유", "관련"], [
    ["AD-01", "계층형 구조 (Presentation → Application → Analysis·Domain → Data, External)", "계층별 담당 분리, 변경 영향 제한", "2.3"],
    ["AD-02", "사진 분석·여행기 생성은 작업 큐(Redis + RQ) + 워커", "처리 시간이 길고 화면을 떠나도 계속되어야 함", "NFR-01, UI-03"],
    ["AD-03", "분석 워커는 파이프라인 (EXIF → 방문지 묶기 → 후보 조회 → VLM 판별)", "단계별 입출력이 명확, 진행률 표시", "UI-01"],
    ["AD-04", "외부 API·AI 모델은 어댑터(CP-18, CP-19) 뒤에 배치", "모델 변경, 테스트용 모의 응답 주입", "QA-05·08"],
    ["AD-05", "여행기 생성은 분석과 별도 작업", "장소 확정·문체 선택 뒤에 작성", "FR-09"],
    ["AD-06", "진행 상태는 2초마다 조회(polling)", "구현이 단순하고 모바일 웹에서 안정적", "UI-01~03"],
    ["AD-07", "회원 기능 없이 익명 기기 토큰으로 여행 구분", "회원 기능은 범위 밖", "1.2"],
    ["AD-08 (변경)", "VLM·LLM 모두 서버 GPU의 Ollama Qwen3.5 4B (같은 모델 하나만 적재)", "외부 AI 비용 0원, 사진·여행 기록 외부 미전송", "NFR-04·08"],
    ["AD-09 (추가)", "Cloudflare 무료 터널 + nginx로 공개 (서버 포트 미개방)", "외부 접속, 열린 포트 0개", "NFR-07"],
    ["AD-10 (추가)", "여행기를 날짜별·방문지 5곳 단위로 나눠 생성, 실패한 날만 템플릿 문단", "한 번에 쓰면 문맥 4096토큰을 넘어 응답이 잘림(D-04)", "FR-09, NFR-03"],
    ["AD-11 (추가)", "공개 서버 사용 한도(기기별 여행 수·동시 작업)와 3일 자동 삭제", "GPU 보호, 개인정보 최소화", "NFR-04·08"],
], [1.05, 2.85, 2.2, 0.8])

h2("2.3 전체 구조")
table(["계층", "역할", "의존 방향"], [
    ["Presentation", "화면 15개(React 모바일 웹), 지도 표시(OpenStreetMap, 키가 있으면 카카오맵), 2초 진행률 조회", "Application만 호출"],
    ["Application", "업무 REST API 23개, 요청 검증, 작업 등록, 짧은 동기 처리(사용자 확정, 공유 카드)", "Analysis·Domain, Data"],
    ["Analysis·Domain", "워커의 긴 처리(사진 분석, 여행기 생성)와 공용 모듈(동선, 후보 검색, 사실 대조)", "Data, External"],
    ["Data", "PostgreSQL, 장소 캐시, 썸네일·임시 원본", "-"],
    ["External Adapter", "장소 데이터·AI 호출, 응답 형식 통일, 시간 제한·재시도", "공공데이터 API(키 없으면 샘플), Ollama"],
], [1.4, 3.9, 1.6])
bul("컴포넌트 단위 연결은 3.3절 그림 3-1, 서버 배치는 2.5절 그림 2-4 참고")

h2("2.4 주요 동작 흐름")
sub("(1) 사진 분석 (UC-01, UC-02): 업로드 후 작업 큐로 전달, 화면은 2초마다 진행 상태 조회")
figure(UML / "seq_analysis.png", "그림 2-1. 사진 분석 흐름 (UC-01, UC-02)", 6.4)
sub("(2) 방문지 상태 변화 (UC-02): 상태 값 6가지는 요구사항 명세서 DR-02와 같음")
figure(UML / "state_visit.png", "그림 2-2. 방문지 상태 변화", 3.8)
sub("(3) 여행기 생성·사실 대조 (UC-06, UC-09): 날짜별·5곳 단위로 나눠 쓰고 문장마다 대조")
figure(UML / "seq_story.png", "그림 2-3. 여행기 생성 흐름 (UC-06, UC-09)", 6.4)

h2("2.5 배포 구조")
bul("서버 PC 한 대의 Docker Compose로 web·api·worker·vlm·postgres·redis·tunnel 실행, API 키는 서버 환경변수 파일(저장소 미포함)로만 주입",
    "tunnel(cloudflared)이 Cloudflare에 먼저 연결하는 방식이라 외부에 열린 포트 없음. 데이터베이스·큐는 내부 망에만 연결")
table(["영역", "기술 (최종)", "선택 이유"], [
    ["프론트엔드", "React 18.3, Vite 5.4, Leaflet(OpenStreetMap)", "설치 없는 모바일 웹, 카카오 키 없이 지도 표시"],
    ["백엔드·작업 큐", "FastAPI 0.162, RQ 2.12 + Redis 7.4", "분석 코드와 언어 통일, 워커 분리(AD-02)"],
    ["분석", "Pillow·pillow-heif, scikit-learn(DBSCAN), httpx", "HEIC 입력, 방문지 묶기, 외부 호출"],
    ["데이터", "PostgreSQL 17 (시험은 SQLite)", "엔티티 8개(4.2절), 장소 캐시"],
    ["AI", "Ollama 0.40 + qwen3.5:4b (VLM·LLM 공용)", "GPU 메모리 3.4GB, 모델 선택 시험(11/23)에서 확신 오답 0건, 여행기 통과 문장 가장 많음"],
    ["공개·품질", "nginx, cloudflared, pytest 87개 (CI 미구성)", "열린 포트 0개, 자동 테스트로 회귀 확인"],
], [1.3, 2.8, 2.8])
figure(UML / "deployment.png", "그림 2-4. 배포 구조 (Docker Compose, 컨테이너 7개)", 5.8)

h2("2.6 중간 설계 대비 수정사항")
table(["항목", "중간 설계 (v1.0, 10/26)", "최종 구현 (11/25)", "이유"], [
    ["LLM 실행 위치", "외부 저가·무료 LLM API", "서버 Ollama Qwen3.5 4B (VLM과 같은 모델)", "비용 0원, 여행 기록 외부 미전송"],
    ["공개 배포", "개발 PC에서 실행", "Cloudflare 무료 터널 + nginx", "외부 접속, 열린 포트 0개"],
    ["지도", "카카오맵", "OpenStreetMap (키가 있으면 카카오맵)", "카카오 키 미발급"],
    ["사진 전송", "원본 그대로", "브라우저에서 축소, 6장씩 전송", "Cloudflare 요청 크기 한도"],
    ["공개 서버 운영", "한도 없음, 사용자 삭제 시까지 보관", "기기별 여행 수·동시 작업 한도, 요청 수 제한, 3일 뒤 자동 삭제", "GPU 보호, 개인정보 최소화"],
    ["여행기 생성 단위", "여행 전체를 한 번에", "날짜별·방문지 5곳 단위, 실패한 날만 템플릿 (D-04)", "문맥 4096토큰 초과로 응답 잘림"],
    ["사실 대조 범위", "수치·장소명", "수치·장소명 + 한자·방문 시각과 다른 시간대 (D-07)", "녹화 중 '午時' 문장 발견"],
    ["워커 대기 주기", "RQ 기본값 (405초)", "45초 (D-05)", "소켓 시간 초과로 6분 40초마다 재시작"],
    ["API", "18개", "23개 (5개 추가)", "화면 구현 중 필요"],
    ["CI", "GitHub Actions", "미구성 (자동 테스트 87개는 로컬 실행)", "일정 부족"],
], [1.25, 1.65, 2.35, 1.65])

# ================================================================== 3. 컴포넌트 설계
h1("3. 컴포넌트 설계")
h2("3.1 컴포넌트 명세")
bul("컴포넌트 19개는 중간 설계와 같고, 책임 칸에 최종 구현 내용을 적음",
    "구현 파일은 번호를 따름: CP-01 frontend/src, CP-02~04 backend/app/api/cp0N_*.py, CP-05~17 backend/app/components/cpNN_*.py, "
    "CP-18·19 backend/app/adapters/cpNN_*.py")
table(["ID", "컴포넌트", "계층", "책임 (최종)"], [
    ["CP-01", "Web Client", "Presentation", "화면 15개, 사진 선택(30장)·축소 전송(6장씩), AI 분석 동의, 2초 진행률 조회, 지도·타임라인"],
    ["CP-02", "Trip API", "Application", "여행 생성·삭제, 업로드 검증(형식·개수·크기), 동의 확인 후 작업 등록, 기기별 사용 한도"],
    ["CP-03", "Visit API", "Application", "방문지·후보·AI 근거 조회, 장소 확정·기타 장소, 직접 검색, 위치 없는 사진 배정, 동선·근처 추천"],
    ["CP-04", "Story API", "Application", "여행기 생성·다시 쓰기 작업 등록, 편집 저장과 사실 대조 경고, 공유 카드 요청"],
    ["CP-05", "Route Service", "Domain", "날짜별 동선, 이동 시간(직선 거리 × 보정 계수), 타임라인"],
    ["CP-06", "Share Card Renderer", "Application", "대표 사진·제목·동선 요약 이미지(좌표·EXIF 제외), 작성 방식에 맞는 표시 문구"],
    ["CP-07", "Analysis Orchestrator", "Analysis", "파이프라인 실행, 진행률 기록, 방문지 단위 실패 격리, 종료 시 원본·좌표 삭제"],
    ["CP-08", "EXIF Extractor", "Analysis", "촬영 시각·GPS 추출(JPEG·PNG·HEIC), 512px VLM용 축소본, 위치 정보 없는 썸네일"],
    ["CP-09", "Visit Clusterer", "Analysis", "DBSCAN 방문지 묶기, 날짜 분리, 대표 사진"],
    ["CP-10", "Candidate Finder", "Domain", "반경 300m → 600m 후보 조회, 출처별 중복 합치기, 거리순 3곳, 키워드 검색"],
    ["CP-11", "Place Matcher", "Analysis", "VLM 판별 요청, 후보 밖 답 거부·1회 재요청, 확신도 분기, 매칭 로그"],
    ["CP-12", "Untagged Photo Resolver", "Analysis", "위치 없는 사진의 방문지 추천(촬영 시각, 애매하면 VLM 사진 비교)"],
    ["CP-13", "Story Generator", "Analysis", "날짜별·5곳 단위 LLM 생성(동시 2개), 실패한 날만 템플릿 문단, 각주, 문단별 작성 방식 표시, 다시 쓰기"],
    ["CP-14", "Fact Checker", "Domain", "문장의 장소·수치·시간대 표현을 공식 데이터·사진 기록과 대조, 한자·일본어 글자 검사 (편집 문장은 장소명·수치)"],
    ["CP-15", "Trip Repository", "Data", "여행·방문지·사진·여행기·각주·매칭 로그 저장, 여행 삭제 시 연쇄 삭제"],
    ["CP-16", "Place Cache", "Data", "장소를 (출처, 원본 ID)로 저장, 조회 결과 24시간 캐시, 출처·갱신일 보관"],
    ["CP-17", "Media Store", "Data", "원본 임시 저장과 삭제(작업 종료·30분 주기), 썸네일 보관"],
    ["CP-18", "Place Data Adapter", "External", "TourAPI·부산시·카카오 로컬 공통 형식, 키가 없으면 같은 형식의 샘플 40곳, 시간 제한·재시도"],
    ["CP-19", "AI Gateway", "External", "Ollama VLM·LLM 호출, JSON 스키마 강제, 잘린 응답(done_reason=length) 거부, 프롬프트 버전, 인물 미분석 지시"],
], [0.6, 1.55, 1.0, 3.75], bold_first=True)

h2("3.2 외부 인터페이스 (REST API)")
bul("모든 경로는 /api/v1 아래, 요청 헤더의 익명 기기 토큰으로 여행 소유자 구분(AD-07). 설계 API 18개 모두 구현, 화면 구현 중 5개 추가(표의 '추가'). 상태 확인용 /health·/meta 2개는 표에서 제외")
table(["IF", "엔드포인트 (최종)", "컴포넌트", "관련"], [
    ["IF-02 Trip", "POST·GET /trips, GET·PATCH /trips/{id}(추가), DELETE /trips/{id}, POST /trips/{id}/photos, "
                   "POST /trips/{id}/analysis, GET /jobs/{id}, GET /photos/{id}/thumb(추가)", "CP-02", "FR-01~04, NFR-04"],
    ["IF-03 Visit", "GET /trips/{id}/visits, GET /visits/{id}/candidates, PUT /visits/{id}/place, GET /places/search, "
                    "GET /places/{id}, PUT /photos/{id}/visit, GET /trips/{id}/route, GET /trips/{id}/nearby(추가)", "CP-03", "FR-05~08, FR-12"],
    ["IF-04 Story", "POST /trips/{id}/stories, GET /trips/{id}/stories(추가), GET·PATCH /stories/{id}, "
                    "POST /stories/{id}/paragraphs/{pid}/rewrite, POST /stories/{id}/share-card", "CP-04", "FR-09~11"],
], [1.0, 4.1, 0.75, 1.05])
bul("VLM 판별 응답은 {place_id, confidence, reason} JSON만 허용, 후보 밖 ID는 CP-11이 거부(AIR-02·03)",
    "여행기 문장 응답은 {text, place_ids, fields, is_fact} JSON. 문단마다 작성 방식(source: llm·template)을 함께 저장")

h2("3.3 의존관계와 컴포넌트 다이어그램")
plain("의존 규칙 (그림 3-1):")
for i, t in enumerate([
    "위 계층만 아래 계층 호출. Data·External 계층은 위 계층을 모름",
    "오래 걸리는 호출(Application → Analysis)은 작업 큐 경유, 서버 쪽 외부 호출은 CP-18·19 경유(지도 타일만 브라우저가 직접)",
    "순수 로직(CP-08, CP-09, CP-14)은 다른 컴포넌트에 의존하지 않음 → 단위 테스트 대상",
    "객체 조립은 services.py 한 곳에서 수행(의존성 주입) → 시험 때 모의 AI·장애 상황 주입",
], 1):
    plain(f"{i}. {t}")
figure(UML / "components.png", "그림 3-1. 컴포넌트 의존관계 (최종 구현)", 6.4)

h2("3.4 요구사항 ↔ 컴포넌트 ↔ 테스트 매핑")
table(["FR", "요구사항", "주 컴포넌트", "협력 컴포넌트", "테스트"], [
    ["FR-01", "사진 업로드·EXIF 추출", "CP-08", "CP-01, 02, 07, 17", "TC-01·02, HEIC·PNG 자동 테스트"],
    ["FR-02", "방문지 군집화", "CP-09", "CP-07", "TC-04"],
    ["FR-03", "공식 데이터 후보 조회", "CP-10", "CP-07, 16, 18", "TC-05, 600m 확대 자동 테스트"],
    ["FR-04", "VLM 판별·확신도", "CP-11", "CP-07, 19", "TC-05, 정확도 평가(웹 사진)"],
    ["FR-05", "사용자 확인·수정", "CP-03", "CP-01, 10, 15", "TC-07, 기타 장소 자동 테스트"],
    ["FR-06", "위치 없는 사진 처리", "CP-12", "CP-03, 07, 19", "TC-08"],
    ["FR-07", "지도 동선·타임라인", "CP-05", "CP-01, 03", "TC-09"],
    ["FR-08", "장소 상세", "CP-03", "CP-16, 18", "TC-10"],
    ["FR-09", "근거 기반 여행기", "CP-13", "CP-04, 14, 19", "TC-06·12, 비기능 10회"],
    ["FR-10", "문단 다시 쓰기·사실 대조", "CP-14", "CP-04, 13", "TC-13"],
    ["FR-11", "공유 카드", "CP-06", "CP-04, 17", "TC-14"],
    ["FR-12", "근처 못 가본 곳 추천", "CP-10", "CP-03, 05", "TC-11"],
], [0.6, 1.85, 1.0, 1.4, 2.05])

# ================================================================== 4. UML 설계
h1("4. UML 설계")
bul("UML 다이어그램: 클래스(그림 4-1) · 도메인 모델(그림 4-2) · 시퀀스(그림 2-1, 2-3) · 상태(그림 2-2) · 배포(그림 2-4) · 컴포넌트(그림 3-1)")
h2("4.1 클래스 다이어그램")
bul("분석 워커·여행기의 주요 클래스. 외부 호출은 어댑터 2개(AIGateway, PlaceDataAdapter)에만 둠",
    "적용한 설계 방식: 어댑터(외부 API·AI), 리포지토리(DB 접근), 파이프라인(분석 순서 제어), 캐시 우선 조회(장소 캐시), 의존성 주입(services.py)")
figure(UML / "class_core.png", "그림 4-1. 주요 클래스 (분석 파이프라인·여행기, 계층 구분은 그림 3-1과 같음)", 6.9)

h2("4.2 도메인 모델과 데이터베이스")
figure(UML / "class_domain.png", "그림 4-2. 도메인 모델 (backend/app/models.py, 테이블 8개)", 4.6)
bul("PostgreSQL 테이블 8개(그림 4-2의 클래스와 1:1): trips(DR-01) · visits(DR-02) · places(DR-03) · photos(DR-04) · stories(DR-05) · "
    "footnotes(DR-06) · match_logs(DR-09) · jobs(작업 진행률)",
    "여행을 지우면 딸린 행 연쇄 삭제, 공개 서버는 3일 뒤 자동 삭제. 좌표는 분석 후 삭제, 매칭 로그(정확도 측정용)에는 사진·좌표 미저장. "
    "places는 장소 캐시로 여행과 독립")

h2("4.3 화면 설계")
bul("모바일 우선 반응형 웹(960px 이상은 두 단 배치). 화면 15개를 흐름 순서로 배치, 경로 정의는 frontend/src/main.jsx",
    "그림 4-3은 명세서 UI-08의 최소 폭 360px에서 녹화한 화면 (11/25, 가로 넘침 0px)")
table(["구분", "화면", "관련"], [
    ["A 업로드", "일기장 첫 화면, 새 여행기·AI 분석 동의, 사진 분석 진행", "FR-01·02, UI-01~03"],
    ["B 확인", "방문지 확인, 장소 확인, 위치 없는 사진, 확정 완료", "FR-04~06"],
    ["C 동선", "동선 지도·타임라인, 장소 상세, 근처 못 가본 곳", "FR-07·08·12"],
    ["D 여행기", "문체 선택, 여행기·출처, 편집, 공유 카드, MY(내 여행기)", "FR-09~11"],
], [1.0, 4.4, 1.5])
figure(HERE / "img" / "screens_360.png", "그림 4-3. 주요 화면 (휴대폰 화면 크기 360×800, 왼쪽부터 업로드·방문지 확인·장소 확인·동선·여행기·공유 카드)", 6.2)



h2("4.4 주요 알고리즘")
table(["알고리즘", "동작 (코드 상수 기준)", "위치"], [
    ["방문지 묶기", "날짜별 DBSCAN(eps 1, min_samples 1). 두 사진 거리 = max(거리 ÷ 200m, 시간차 ÷ 60분). "
                "위치 있는 사진이 없으면 촬영 간격 60분 이하끼리 묶음", "CP-09"],
    ["후보 조회", "반경 300m, 없으면 600m. 출처 우선순위·거리순 정렬, 이름이 같거나 포함 관계이고 150m 안이면 하나로 합침, 최대 3곳", "CP-10"],
    ["확신도 분기", "형식 오류·후보 밖 답은 1회 재요청 후 거부. 0.8 이상 자동확정, 0.5 이상 확인필요, 그 밖은 선택필요(기준값은 환경변수)", "CP-11"],
    ["여행기 분할 생성", "날짜별 방문지 5곳씩 LLM 요청(동시 2개, 출력 1,500토큰 상한). 대조 뒤 문장이 없거나 뺀 문장이 더 많은 날만 템플릿 문단", "CP-13"],
    ["문장 사실 대조", "근거 없는 사실·확정 안 된 장소·한자·가나·시간대 불일치 문장 제거. 시간대 단어(아침 4~11시 등)는 촬영 시각 ±1시간과 비교", "CP-14"],
], [1.35, 4.75, 0.8])

par(P_AI, "AI 활용 명기: " + TRACE["ai_note"])

d.core_properties.title = "소프트웨어 설계서: 찰칵부산 Team 10 (v2.0)"
d.save(OUT)
print("saved", OUT)
