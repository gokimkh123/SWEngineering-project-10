"""최종 계획서(v2.0)·최종 요구사항분석서(v2.0) 생성: 중간 제출본(v1.0, docs/submission)의 서식은 그대로 두고 바뀐 곳만 고친다.

- 계획서: 표지(버전·작성일·최종 역할), 문서 관리 2.0 행, 2.3 최종 산출물, 4.2 구현 역할 확정, 5.1 마일스톤 상태,
  10장 '계획 대비 실적' 신설(requirements_trace.json의 plan_design + 범위·비용·위험), AI 활용 명기
- 요구사항분석서: 표지, 문서 관리 2.0 행 + 'v2.0 변경 요구사항' 표, 바뀐 요구사항 본문(FR-07·09·10, UC-06·07 대안 흐름,
  DR 보관 기간, AIR-01, 운영 환경·제약, AI 사용 범위), 10장 추적표 상태를 최종 판정으로, AI 활용 명기. 11장 승인은 비워 둠
- 공통: 줄표(—)를 쓰지 않음 (' — ' → ': ', 빈 칸 표시 '—' → '-')
- 확인한 사실만 적음: 설문·인터뷰, 스프린트 리뷰·회고, 실기기 GPS 확인처럼 기록이 없는 일은 실적으로 적지 않음
사용: python make_final_plan_srs.py <중간 제출본 폴더(docs/submission)> <출력 폴더>
"""
import copy
import json
import re
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.shared import Emu
from docx.table import Table
from docx.text.paragraph import Paragraph

SUB, OUT = Path(sys.argv[1]), Path(sys.argv[2])
HERE = Path(__file__).resolve().parent
TRACE = json.loads((HERE / "requirements_trace.json").read_text(encoding="utf-8"))
DATE = "2026-11-26"


# ------------------------------------------------------------------ 서식 도우미 (make_design_doc.py와 같은 방식)
def set_par(p: Paragraph, text: str):
    runs = p.runs
    if not runs:
        p.add_run(text)
        return p
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    return p


def set_cell(cell, text):
    lines = str(text).split("\n")
    ps = cell.paragraphs
    first = ps[0]
    for extra in ps[1:]:
        extra._p.getparent().remove(extra._p)
    set_par(first, lines[0])
    prev = first
    for ln in lines[1:]:
        np_ = copy.deepcopy(first._p)
        prev._p.addnext(np_)
        prev = Paragraph(np_, first._parent)
        set_par(prev, ln)


def cells(row):
    """병합 칸을 한 번만 돌려준다."""
    out, seen = [], set()
    for c in row.cells:
        if id(c._tc) not in seen:
            seen.add(id(c._tc))
            out.append(c)
    return out


def text_width_in(d):
    s = d.sections[0]
    return Emu(s.page_width - s.left_margin - s.right_margin).inches


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
            c.width = Emu(int(w * 914400))


def keep_lead(table: Table, rows=2):
    prev = table._tbl.getprevious()
    if prev is not None and prev.tag == qn("w:p"):
        Paragraph(prev, table._parent).paragraph_format.keep_with_next = True
    for row in table.rows[:rows]:
        for c in row.cells:
            for par in c.paragraphs:
                par.paragraph_format.keep_with_next = True


def new_table_after(anchor_el, template: Table, header, rows, widths, parent):
    """template(같은 열 수의 표)을 복사해 anchor 뒤에 넣고 머리 행·내용 행을 채운다."""
    el = copy.deepcopy(template._tbl)
    anchor_el.addnext(el)
    t = Table(el, parent)
    while len(t.rows) > 2:
        el.remove(t.rows[-1]._tr)
    for _ in range(len(rows) - 1):
        el.append(copy.deepcopy(t.rows[1]._tr))
    for c, v in zip(cells(t.rows[0]), header):
        set_cell(c, v)
    for r, vals in zip(t.rows[1:], rows):
        for c, v in zip(cells(r), vals):
            set_cell(c, v)
    set_widths(t, widths)
    keep_lead(t)
    return t


def para_after(anchor_el, template_p: Paragraph, text, parent):
    el = copy.deepcopy(template_p._p)
    anchor_el.addnext(el)
    p = Paragraph(el, parent)
    set_par(p, text)
    for r in p.runs:  # 견본 문단의 굵은 머리말 서식을 물려받지 않게
        r.bold = None
    return p


def no_dash(d):
    """줄표 제거: ' — ' → ': ', '— ' 로 시작 → '- ', '—'만 있는 칸 → '-'. 글자 조각(run)마다 바꿔 굵은 머리말 서식 유지."""
    def fix(t):
        t = t.replace(" — 출처:", ", 출처:")
        if t.strip() == "—":
            return "-"
        t = re.sub(r"^—\s", "- ", t)
        return t.replace(" — ", ": ").replace("—", "-")

    def walk(ps):
        for p in ps:
            if "—" in p.text:
                for r in p.runs:
                    if "—" in r.text:
                        r.text = fix(r.text)
                if "—" in p.text:  # 줄표가 조각 경계에 걸린 경우
                    set_par(p, fix(p.text))

    walk(d.paragraphs)
    for t in d.tables:
        for r in t.rows:
            for c in cells(r):
                walk(c.paragraphs)


def find_par(d, start):
    return next(p for p in d.paragraphs if p.text.strip().startswith(start))


def table_with(d, *head):
    for t in d.tables:
        h = [c.text.strip() for c in cells(t.rows[0])]
        if all(x in h for x in head):
            return t
    raise KeyError(head)


def row_where(t, first):
    return next(r for r in t.rows if cells(r)[0].text.strip() == first)


def cover_and_history(d, change):
    cover = d.tables[0]
    vals = {"프로젝트명": "찰칵부산: 여행 사진으로 방문지·동선·여행기를 만드는 부산 AI 서비스",
            "팀원": "김건한 / 2243219 / 테스트·PM (팀장, 최종 발표)\n김예슬 / 2443358 / 백엔드\n전규민 / 2229930 / 프론트엔드·테스트\n"
                    "황웅재 / 2243416 / 백엔드",
            "버전": "v2.0 (최종 제출본)", "작성일": DATE}
    for r in cover.rows:
        k = r.cells[0].text.strip()
        if k in vals:
            set_cell(r.cells[1], vals[k])
    hist = d.tables[1]
    hist._tbl.append(copy.deepcopy(hist.rows[-1]._tr))
    for c, v in zip(cells(hist.rows[-1]), ["2.0", DATE, "김건한", change]):
        set_cell(c, v)
    return hist


# ================================================================== 최종 계획서 v2.0
def plan():
    d = docx.Document(SUB / "01_계획서_찰칵부산_Team10.docx")
    W = text_width_in(d)
    cover_and_history(d, "최종 제출본: 실적 반영 (10장 계획 대비 실적 신설, 5.1 마일스톤 상태, 4.2 구현 역할 확정, 2.3 최종 산출물)")
    set_par(find_par(d, "요구사항 ID(FR, NFR"), "요구사항 ID(FR, NFR, AC 등)와 유스케이스 ID(UC)는 요구사항분석서 v2.0, 컴포넌트 ID(CP)는 "
                                                "설계서 v2.0 기준. 이 문서의 1~9장은 계획(v1.0)을 유지하고, 계획 대비 실적은 10장에 정리")
    p = find_par(d, "AI 사용 범위")
    p.runs[-1].text = p.runs[-1].text.rstrip(".") + " (최종 구현: LLM도 서버의 Qwen3.5 4B로 실행, 10장)"

    t = table_with(d, "시점", "산출물", "위치")
    r = row_where(t, "최종발표")
    c = cells(r)
    set_cell(c[1], "최종 계획서 v2.0(실적 반영), 최종 요구사항분석서 v2.0, 최종 설계서 v2.0(UML 설계 포함), 테스트 결과서, "
                   "시연 영상(2분 32초), 발표 자료")
    set_cell(c[2], "LMS 제출, 저장소 docs/05-final")

    set_par(find_par(d, "4.2 구현 단계 역할"), "4.2 구현 단계 역할 (확정)")
    set_par(find_par(d, "설계서 3.1의 컴포넌트 기준으로"), "설계서 3.1의 컴포넌트 기준으로 담당 확정(11/24 팀 확정). 최종 발표는 김건한")
    t = table_with(d, "역할", "컴포넌트")
    set_cell(cells(t.rows[0])[2], "담당 (확정)")
    who = {"프론트엔드": "전규민 (테스트 겸임)", "백엔드·데이터": "황웅재, 김예슬", "AI 파이프라인": "황웅재, 김예슬",
           "PM·품질": "김건한 (테스트·PM)"}
    for r in t.rows[1:]:
        k = cells(r)[0].text.strip()
        if k in who:
            set_cell(cells(r)[2], who[k])

    t = table_with(d, "날짜", "마일스톤", "상태")
    status = {"10/26(월)": "완료", "10/29(목)": "완료", "10/30(금)": "완료 (역할 확정은 11/24)",
              "11/12(목)": "11/11 프로토타입 v0.1 완료", "11/26(목)": "11/23 공개 배포·테스트, 11/25 재측정 완료",
              "11/27(금)": "예정"}
    for r in t.rows[1:]:
        c = cells(r)
        k = c[0].text.strip()
        if k in status:
            set_cell(c[2], status[k])
    last = t.rows[-1]
    new = copy.deepcopy(last._tr)
    last._tr.addprevious(new)
    nr = t.rows[-2]
    for c, v in zip(cells(nr), ["11/30(월)", "최종 산출물 LMS 제출 (밤 12시 마감)", "예정"]):
        set_cell(c, v)
    for c, v in zip(cells(t.rows[-1]), ["12/1(화)", "최종발표 (1반 10팀, 발표 김건한)", "확정"]):
        set_cell(c, v)
    set_widths(t, [1.45, W - 1.45 - 2.0, 2.0])

    # 10장 계획 대비 실적 (AI 활용 명기 바로 앞)
    ai = d.paragraphs[-1]
    assert ai.text.startswith("AI 활용 명기")
    h1 = next(p for p in d.paragraphs if p.style.name == "Heading 1" and p.text.strip().startswith("9."))
    bul = next(p for p in d.paragraphs if p.style.name == "List Bullet")
    head = copy.deepcopy(h1._p)
    ai._p.addprevious(head)
    set_par(Paragraph(head, ai._parent), "10. 계획 대비 실적")
    b = para_after(head, bul, "기준일 11/26. 수치는 테스트 결과서(11/25 재측정), 판정 기준(충족·조건부·부분·미실시)은 테스트 결과서 5장", ai._parent)
    rows = [[x["item"], x["plan"], x["actual"], x["judge"]] for x in TRACE["plan_design"]]
    rows.insert(1, ["범위 (2.1)", "Must 8개 필수, Should·Could는 진척이 앞설 때만",
                    "Must·Should·Could 기능 12개 모두 구현 (판정: 충족 6 · 조건부 5 · 부분 1)", "계획 범위 이상 구현"])
    rows.append(["자원·비용 (6장)", "공공데이터·지도 무료 쿼터, LLM은 저가·무료 외부 모델",
                 "외부 유료 호출 0원. VLM·LLM 모두 팀원 PC GPU의 Qwen3.5 4B, 공개 서버는 Docker Compose + Cloudflare 무료 터널",
                 "비용 0원"])
    rows.append(["위험 (7장)", "R-01~R-10 대응 계획",
                 "R-03 사실 대조로 근거 없는 문장 제거(사실 문장 출처 162/162) · R-07 원본·좌표 잔존 0건 · R-10 키 노출 0건 · "
                 "R-02 웹 사진 대체 평가 81.5% · R-01 실기기 GPS 미확인", "남은 위험: R-01·R-02"])
    tmpl = d.tables[1]  # 문서 관리 표 (4열)
    new_table_after(b._p, tmpl, ["항목", "계획", "실적", "판단"], rows, [1.3, 1.75, W - 1.3 - 1.75 - 1.25, 1.25], ai._parent)

    set_par(ai, "AI 활용 명기: (v1.0) 팀 문서와 GitHub 기록을 바탕으로 한 초안·간트 차트 작성에 Claude Code(Anthropic) 활용, 팀 검토 후 확정 · "
                "(v2.0) 계획 대비 실적 정리(10장)와 마일스톤·역할 갱신에 Claude Code(Anthropic) 활용")
    no_dash(d)
    d.core_properties.title = "프로젝트 계획서: 찰칵부산 Team 10 (v2.0)"
    out = OUT / "01_계획서_찰칵부산_Team10.docx"
    d.save(out)
    print("saved", out)


# ================================================================== 최종 요구사항분석서 v2.0
def srs():
    d = docx.Document(SUB / "02_요구사항분석서_찰칵부산_Team10.docx")
    W = text_width_in(d)
    hist = cover_and_history(d, "최종 제출본: 구현·테스트 결과 반영 (아래 변경 요구사항 7건, 10장 상태를 최종 판정으로 갱신)")
    bul = next(p for p in d.paragraphs if p.style.name == "List Bullet")
    note = para_after(hist._tbl, bul, "v2.0 변경 요구사항 (본문에 'v2.0' 표시, 측정 결과는 테스트 결과서 5장)", hist._parent)
    changes = [
        ["FR-07", "카카오맵", "카카오맵, 키가 없으면 OpenStreetMap", "카카오 키 미발급"],
        ["FR-09, UC-06", "외부 LLM, 실패 시 재시도 안내", "서버 LLM(Qwen3.5 4B), 날짜별·5곳 단위, 실패한 날만 공식 데이터 문장 문단", "비용 0원, D-04"],
        ["FR-10, UC-07", "실패 시 기존 문단 유지", "실패하거나 같은 문단이면 공식 데이터 문장 문단으로 교체", "D-01"],
        ["DR-01·02·05", "사용자 삭제 시까지", "공개 서버는 3일 뒤 자동 삭제", "개인정보 최소화"],
        ["AIR-01", "후보 사진 포함", "후보 사진 제외, 개요 120자", "입력 길이"],
        ["2.3·2.4", "외부 LLM API", "서버 Ollama, Cloudflare 무료 터널 + nginx", "비용 0원, 열린 포트 0개"],
        ["NFR-04·07·08", "-", "사용량 한도·요청 수 제한·보안 헤더 추가", "공개 서버 보호"],
    ]
    new_table_after(note._p, hist, ["요구사항", "v1.0", "v2.0 (최종)", "이유"], changes, [1.15, 1.75, W - 1.15 - 1.75 - 1.45, 1.45], hist._parent)

    set_par(find_par(d, "요구사항 도출:"), "요구사항 도출: 경쟁 서비스 분석·브레인스토밍(이슈 #1~#4)·화면 시안. v2.0은 구현·테스트에서 확인한 "
                                       "변경 사항 반영(문서 관리의 변경 요구사항 표)")
    set_par(find_par(d, "Server: Docker Compose"), "Server: Docker Compose(FastAPI 서버, Python 분석 워커, Ollama VLM·LLM 추론 서버, "
                                                 "PostgreSQL, Redis), 외부 공개는 Cloudflare 무료 터널 + nginx (v2.0)")
    set_par(find_par(d, "External AI/API:"), "External API: TourAPI, 부산광역시 명소·맛집 API, 카카오 지도·로컬 (키가 없으면 같은 형식의 "
                                            "샘플 데이터·OpenStreetMap). LLM은 서버 실행으로 바뀌어 외부 AI API 없음 (v2.0)")
    p = find_par(d, "비용·한도:")
    set_par(p, "비용·한도: 공공데이터 쿼터(TourAPI 일 1,000회 등) 안에서 동작, AI는 서버에서 실행하는 오픈소스 모델"
               "(VLM·LLM 공용 Qwen3.5 4B) 사용 (v2.0)")
    p = find_par(d, "범위·일정:")
    set_par(p, p.text.replace("최종발표 12/1·3", "최종발표 12/1"))
    set_par(find_par(d, "AI 사용 범위:"), "AI 사용 범위: 후보 중 장소 판별(VLM), 확정된 사실로 여행기 작성(LLM). 둘 다 서버에서 실행하는 "
                                        "오픈소스 모델 Qwen3.5 4B(Ollama) 사용 (v2.0, v1.0은 LLM을 저가·무료 외부 모델로 계획)")

    t = table_with(d, "ID", "요구사항명", "요구사항 내용")
    for r in t.rows:
        c = cells(r)
        k = c[0].text.strip()
        if k == "FR-07":
            set_cell(c[2], c[2].text.replace("확정된 방문지를 카카오맵에", "확정된 방문지를 지도(카카오맵, 키가 없으면 OpenStreetMap, v2.0)에"))
        elif k == "FR-09":
            set_cell(c[2], c[2].text.rstrip(".") + ". LLM이 실패한 날은 공식 데이터 문장 문단으로 대체하고 작성 방식 표시 (v2.0)")
        elif k == "FR-10":
            set_cell(c[2], c[2].text.rstrip(".") + ". 다시 쓰기가 실패하거나 같은 문단이면 공식 데이터 문장 문단으로 교체 (v2.0)")
    for t in d.tables:
        if cells(t.rows[0])[-1].text.strip() in ("UC-06", "UC-07"):
            uc = cells(t.rows[0])[-1].text.strip()
            r = row_where(t, "대안/예외 흐름")
            c = cells(r)[-1]
            if uc == "UC-06":
                set_cell(c, c.text.replace("1a. 생성 실패 시 안내 후 재시도.", "1a. LLM 생성이 실패하거나 근거 문장이 부족한 날은 공식 데이터 문장 "
                                                                       "문단으로 대체하고 작성 방식 표시 (v2.0)."))
            else:
                set_cell(c, "1a. 재생성이 실패하거나 같은 문단이 나오면 공식 데이터 문장 문단으로 교체 (v2.0)")
    t = table_with(d, "데이터 ID", "데이터명")
    for r in t.rows:
        c = cells(r)
        if c[0].text.strip() in ("DR-01", "DR-02", "DR-05"):
            set_cell(c[-1], "사용자 삭제 시까지 (공개 서버는 3일 뒤 자동 삭제, v2.0)")
    t = table_with(d, "AI 요구 ID", "항목")
    r = row_where(t, "AIR-01")
    set_cell(cells(r)[2], "VLM 입력: 대표 사진 1장(축소본)과 후보 목록(이름·유형·거리·개요 120자, 카카오 후보는 이름·유형·거리만). "
                          "후보 사진은 보내지 않음 (v2.0)")

    # 10장 추적표: 상태 = 최종 판정, Test Case = 인수 기준 + 테스트 결과서 TC
    req = {x["id"]: x for x in TRACE["requirements"]}
    short = {"NFR-01": "성능 측정 10회", "NFR-02": "웹 사진 대체 평가", "NFR-05": "사용성 테스트", "NFR-06": "실기기 테스트",
             "NFR-07": "보안 점검 11개", "NFR-08": "장애 모의 테스트"}
    t = table_with(d, "요구사항 ID", "Use Case", "상태")
    for r in t.rows[1:]:
        c = cells(r)
        k = c[0].text.strip()
        if k not in req:
            continue
        tcs = re.findall(r"TC-\d\d", req[k]["tests"])
        tc = "TC-" + "·".join(x[3:] for x in tcs) if tcs else short.get(k, req[k]["tests"])
        ac = c[3].text.strip()
        ac = "" if ac.startswith("-") or ac.startswith("—") else ac
        set_cell(c[3], f"{ac} · {tc}" if ac else tc)
        set_cell(c[4], req[k]["state"])
    set_par(find_par(d, "설계 요소:"), "설계 요소: 설계서 v2.0 3장의 컴포넌트(FR 행은 주 / 협력) / Test Case: 9장 인수 기준과 테스트 결과서의 TC / "
                                     "상태: 최종 판정(11/25 재측정, 충족·조건부·부분·미실시, 정의는 테스트 결과서 5장)")

    ai = d.paragraphs[-1]
    assert ai.text.startswith("AI 활용 명기")
    set_par(ai, ai.text.rstrip(".") + " · (v2.0) 구현·테스트 결과 반영(변경 요구사항 표, 10장 최종 판정)에 Claude Code(Anthropic) 활용")
    no_dash(d)
    d.core_properties.title = "소프트웨어 요구사항 명세서: 찰칵부산 Team 10 (v2.0)"
    out = OUT / "02_요구사항분석서_찰칵부산_Team10.docx"
    d.save(out)
    print("saved", out)


plan()
srs()
