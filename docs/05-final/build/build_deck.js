// 찰칵부산 최종 발표 PPT (pptxgenjs). 디자인은 사용자가 준 예시 PPT(26_11_19 …pptx)를 따른다:
// 20 x 11.25in 흰 바탕 · 왼쪽 위 회색 머리말 + 가는 회색 선 · 상자 안 쪽번호 (학교 로고는 넣지 않음)
// 32pt 굵은 제목 + 20pt 회색 부제(용어 풀이) · 보라(5B4BE0) 강조 · 연보라(EEECFC) 카드 · 가로줄만 있는 표 · Pretendard
// 사용: NODE_PATH=./node_modules node build_deck.js <deck_data.json> <출력.pptx> <시연영상.mp4> <UML png 폴더>
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const [, , DATA, OUTFILE, VIDEO, UMLDIR] = process.argv;
const D = JSON.parse(fs.readFileSync(DATA, "utf8"));
// 테스트 결과서와 같은 문구·판정을 쓰기 위한 공용 파일 (요구사항 명세서 v1.0 기준)
const TCT = JSON.parse(fs.readFileSync(path.join(__dirname, "tc_text.json"), "utf8"));
const TRACE = JSON.parse(fs.readFileSync(path.join(__dirname, "requirements_trace.json"), "utf8"));
const REQS = TRACE.requirements, DIFFS = TRACE.differences;
const IMG = path.join(__dirname, "img");
const img = (n) => path.join(IMG, n);

const FONT = "Pretendard";
const INK = "16181D", BODY = "4B5059", MUTED = "8A8F98", CRUMB = "787878";
const PURPLE = "5B4BE0", LAV = "EEECFC", LAV_LINE = "D6D0F7", PURPLE_LIGHT = "B3A9F3";
const GRAY_BG = "F4F4F8", BOX_LINE = "DADCE2", GRID = "E3E3E3", RULE = "4B5059", LIFELINE = "B9BCC4";
const ORANGE = "D9902C", ORANGE_BG = "FBF1E3", RED = "D94848", RED_BG = "FBEAEA", WHITE = "FFFFFF";

const pres = new pptxgen();
// 발표 시간표: 슬라이드별 [시작 초, 끝 초]. 노트 앞의 [@]와 2쪽 '시간 배분'이 모두 이 표에서 나옴
// (노트 글자 수를 초당 5음절로 읽는 시간 + 섹션마다 4~10초 여유. 시연 영상 2:50 포함)
const SLOTS = [null, [0, 17], [17, 35], [35, 71], [71, 231], [231, 262], [262, 292], [292, 328], [328, 369], [369, 398],
  [398, 430], [430, 470], [470, 502], [502, 534], [534, 563], [563, 600]];
const TIMED = SLOTS.length - 1;   // 시간표가 있는 본문 슬라이드 수 (1~15쪽)
for (let n = 2; n <= TIMED; n++) if (SLOTS[n][0] !== SLOTS[n - 1][1]) throw new Error(`시간표가 이어지지 않음: ${n}쪽`);
if (SLOTS[1][0] !== 0 || SLOTS[TIMED][1] !== 600) throw new Error("시간표는 0:00에 시작해 10:00에 끝나야 함");
const clock = (t) => `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
const slotTag = (n) => `[${clock(SLOTS[n][0])}~${clock(SLOTS[n][1])}]`;
let SLIDE_NO = 0;
const _addSlide = pres.addSlide.bind(pres);
pres.addSlide = (opts) => {   // 노트의 [@]를 그 쪽의 시간표로 바꿈. 1~15쪽은 [@]가 꼭 있어야 하고, 16쪽부터는 있으면 안 됨
  const sl = _addSlide(opts), n = ++SLIDE_NO, addNotes = sl.addNotes.bind(sl);
  sl.addNotes = (t) => {
    const k = (t.match(/\[@\]/g) || []).length;
    if (n <= TIMED && k !== 1) throw new Error(`${n}쪽 노트에 시간 자리 [@]가 ${k}개`);
    if (n > TIMED && k) throw new Error(`${n}쪽은 시간표 밖인데 노트에 [@]가 있음`);
    return addNotes(n <= TIMED ? t.replace("[@]", slotTag(n)) : t);
  };
  return sl;
};
pres.defineLayout({ name: "EXAMPLE_20x11", width: 20, height: 11.25 });
pres.layout = "EXAMPLE_20x11";
pres.author = "Team 10";
pres.company = "동아대학교 소프트웨어공학 Team 10";
pres.title = "찰칵부산 최종 발표";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

// ------------------------------------------------------------------ 레이아웃 (예시 PPT의 틀)
const chrome = [
  { line: { x: 0.54, y: 1.03, w: 18.93, h: 0, line: { color: CRUMB, width: 0.75 } } },
  { rect: { x: 19.65, y: 0.02, w: 0.33, h: 0.32, fill: { color: WHITE }, line: { color: "808080", width: 0.75 } } },
];
const slideNumber = { x: 17.64, y: -0.02, w: 2.33, h: 0.4, fontFace: FONT, fontSize: 9, color: CRUMB, align: "right", valign: "middle" }; // 예시와 같은 자리: 넓은 칸 오른쪽 정렬 → 상자 안
pres.defineSlideMaster({
  title: "COVER",
  background: { color: WHITE },
  objects: chrome.concat([
    { text: { text: "Presentation", options: { x: 0.64, y: 0.57, w: 4, h: 0.36, fontFace: FONT, fontSize: 18, color: CRUMB, margin: 0, valign: "middle" } } },
    { placeholder: { options: { name: "title", type: "title", x: 2.17, y: 3.95, w: 15.67, h: 0.95, fontFace: FONT, fontSize: 50, bold: true,
        color: INK, align: "left", valign: "middle", margin: 0 }, text: "" } },
  ]),
  slideNumber,
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: WHITE },
  objects: chrome.concat([
    { placeholder: { options: { name: "title", type: "title", x: 1.42, y: 1.56, w: 17.36, h: 0.69, fontFace: FONT, fontSize: 32, bold: true,
        color: INK, align: "left", valign: "middle", margin: 0 }, text: "" } },
  ]),
  slideNumber,
});

// ------------------------------------------------------------------ 좌표: 본문은 13.333x7.5 기준 값을 20x11.25 본문 영역으로 옮긴다
// 본문 영역: x 1.42~18.32, y 2.97~10.25 (예시의 제목·부제 아래). 글자 크기도 같은 비율(1.36배).
const K = 1.36;
const X = (v) => +(0.808 + v * K).toFixed(3);
const Y = (v) => +(0.862 + v * K).toFixed(3);
const Z = (v) => +(v * K).toFixed(3);
const P = (pt) => Math.round(pt * K * 2) / 2;
function conv(o) {
  const r = Object.assign({}, o);
  if ("x" in r) r.x = X(r.x);
  if ("y" in r) r.y = Y(r.y);
  if ("w" in r) r.w = Z(r.w);
  if ("h" in r) r.h = Z(r.h);
  if (r.fontSize) r.fontSize = P(r.fontSize);
  return r;
}

// ------------------------------------------------------------------ 그리기 도구 (예시 PPT 스타일)
const S = pres.shapes;
function T(slide, text, o) {
  slide.addText(text, Object.assign({ fontFace: FONT, fontSize: P(13), color: BODY, isTextBox: true, margin: 0, valign: "top" }, conv(o)));
}
function R(slide, x, y, w, h, o = {}) {
  const opts = { x: X(x), y: Y(y), w: Z(w), h: Z(h), fill: { color: o.fill || WHITE } };
  opts.line = o.line ? { color: o.line, width: o.lw || 0.75 } : { type: "none" };
  if (o.dash && o.line) opts.line.dashType = o.dash;
  if (o.radius) { opts.rectRadius = Z(o.radius); slide.addShape(S.ROUNDED_RECTANGLE, opts); } else slide.addShape(S.RECTANGLE, opts);
}
function circleNum(slide, x, y, d, label, o = {}) {
  slide.addShape(S.OVAL, { x: X(x), y: Y(y), w: Z(d), h: Z(d), fill: { color: o.fill || PURPLE }, line: { type: "none" } });
  T(slide, String(label), { x, y, w: d, h: d, align: "center", valign: "middle", bold: true, color: o.color || WHITE, fontSize: o.fs || 11 });
}
function line(slide, x1, y1, x2, y2, o = {}) {
  const opts = { x: X(Math.min(x1, x2)), y: Y(Math.min(y1, y2)), w: Z(Math.abs(x2 - x1)), h: Z(Math.abs(y2 - y1)),
    line: { color: o.color || BODY, width: o.w || 1.25 } };
  if (o.dash) opts.line.dashType = o.dash;
  if (o.end) opts.line.endArrowType = o.end;
  if (o.begin) opts.line.beginArrowType = o.begin;
  if (x2 < x1) opts.flipH = true;
  if (y2 < y1) opts.flipV = true;
  slide.addShape(S.LINE, opts);
}
function poly(slide, pts, o = {}) {
  for (let i = 0; i < pts.length - 1; i++) {
    const last = i === pts.length - 2;
    line(slide, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], Object.assign({}, o, { end: last ? o.end : undefined }));
  }
}
function chip(slide, x, y, w, h, text, o = {}) {
  R(slide, x, y, w, h, { fill: o.fill || LAV, line: o.line, radius: o.radius || 0.06 });
  T(slide, text, { x, y, w, h, align: "center", valign: "middle", fontSize: o.fs || 10.5, bold: o.bold !== false, color: o.color || PURPLE });
}
function shot(slide, file, x, y, w, ratio = 1920 / 990, o = {}) {
  const h = w / ratio;
  slide.addImage({ path: img(file), x: X(x), y: Y(y), w: Z(w), h: Z(h), altText: o.alt || file });
  frame(slide, x, y, w, h);
  return h;
}
function frame(slide, x, y, w, h) { // 이미지 테두리 (채우기 없음)
  slide.addShape(S.RECTANGLE, { x: X(x), y: Y(y), w: Z(w), h: Z(h), fill: { type: "none" }, line: { color: BOX_LINE, width: 0.75 } });
}
function textWidth(s, pt) { // Pretendard 대략 너비 (인치): 한글 0.9em, 공백 0.3em (PowerPoint 렌더 기준으로 넉넉히)
  let w = 0;
  for (const ch of s) w += /[ㄱ-힝]/.test(ch) ? 0.9 : ch === " " ? 0.3 : /[A-Z0-9]/.test(ch) ? 0.66 : /[a-z]/.test(ch) ? 0.55 : 0.45;
  return (w * pt) / 72;
}
function pngSize(file) {
  const b = fs.readFileSync(file);
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
}
function tableBox(o) {
  const r = Object.assign({}, o);
  r.x = X(o.x); r.y = Y(o.y); r.w = Z(o.w);
  if (o.colW) r.colW = o.colW.map(Z);
  if (o.rowH) r.rowH = Array.isArray(o.rowH) ? o.rowH.map(Z) : Z(o.rowH);
  if (o.h) r.h = Z(o.h);
  return r;
}
// 예시 PPT의 표: 머리 행은 작은 회색 글자, 그 아래 진한 가로줄, 행 사이 연한 가로줄, 세로줄 없음, 첫 열 굵게
const NONE = { type: "none" };
function table(slide, head, body, o) {
  const fs0 = P(o.fontSize || 10.5);
  const hdr = head.map((t, i) => ({ text: t, options: { color: MUTED, fontSize: Math.round(fs0 * 0.92 * 2) / 2, bold: false,
    align: (o.headAlign && o.headAlign[i]) || "left", border: [NONE, NONE, { type: "solid", pt: 1.25, color: RULE }, NONE] } }));
  const rows = [hdr].concat(body.map((r) => r.map((c, i) => {
    const cell = c !== null && typeof c === "object" && "text" in c ? c : { text: String(c) };
    const opt = Object.assign({ border: [NONE, NONE, { type: "solid", pt: 0.75, color: GRID }, NONE] }, cell.options || {});
    if (i === 0 && o.firstBold !== false) { if (opt.bold === undefined) opt.bold = true; if (!opt.color) opt.color = INK; }
    return { text: cell.text, options: opt };
  })));
  const box = tableBox({ x: o.x, y: o.y, w: o.w, colW: o.colW, rowH: o.rowH });
  slide.addTable(rows, Object.assign({ fontFace: FONT, fontSize: fs0, color: BODY, valign: "middle", margin: o.margin || [3, 6, 3, 6], autoPage: false }, box));
}
const verdict = (v) => {
  const bad = /FAIL/.test(v), warn = /미실시|부분|개선|조건부/.test(v); // 조건부·부분·미실시는 주황 (통과처럼 보이지 않게)
  return { text: v, options: { bold: true, align: "center", color: bad ? RED : warn ? ORANGE : PURPLE } };
};

let SECTION = "표지";
function section(name) { SECTION = name; pres.addSection({ title: name }); }
function content(crumb, title, sub, notes) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: SECTION });
  s.addText(crumb, { x: 0.64, y: 0.57, w: 9, h: 0.36, fontFace: FONT, fontSize: 18, color: CRUMB, margin: 0, valign: "middle", isTextBox: true });
  s.addText(title, { placeholder: "title" });
  if (textWidth(title, 32) > 17.3) console.log("WARN 제목이 길어요:", title, textWidth(title, 32).toFixed(1));
  if (sub) {
    s.addText(sub, { x: 1.42, y: 2.25, w: 17.36, h: 0.47, fontFace: FONT, fontSize: 20, color: MUTED, margin: 0, valign: "middle", isTextBox: true });
    if (textWidth(sub, 20) > 17.3) console.log("WARN 부제가 길어요:", sub, textWidth(sub, 20).toFixed(1));
  }
  if (notes) s.addNotes(notes);
  return s;
}
function foot(s, text, y = 6.88) { // 아래쪽 회색 주석 (예시의 '예시 = …', '출처 …' 줄)
  T(s, text, { x: 0.45, y, w: 12.4, h: 0.28, fontSize: 10.5, color: MUTED, valign: "middle" });
}

// ------------------------------------------------------------------ 시각 요소: 아이콘 · 판정 색 · 조건 칩 (아이콘 PNG는 make_icons.js로 미리 만듦)
const ICON_DIR = path.join(IMG, "icons");
function icon(slide, name, x, y, s, c = "p") {
  slide.addImage({ path: path.join(ICON_DIR, `${name}-${c}.png`), x: X(x), y: Y(y), w: Z(s), h: Z(s), altText: name });
}
function iconCircle(slide, name, x, y, d, o = {}) {
  slide.addShape(S.OVAL, { x: X(x), y: Y(y), w: Z(d), h: Z(d), fill: { color: o.bg || PURPLE }, line: o.line ? { color: o.line, width: 1 } : { type: "none" } });
  const s = d * (o.scale || 0.56);
  icon(slide, name, x + (d - s) / 2, y + (d - s) / 2, s, o.fg || "w");
}
// 요구사항 판정 → 색. 타일·범례·숫자는 모두 REQS[].state에서 이 표 하나로 그림
const STATE = {
  충족: { fill: PURPLE, line: PURPLE, text: WHITE },
  조건부: { fill: ORANGE, line: ORANGE, text: WHITE },
  부분: { fill: ORANGE_BG, line: ORANGE, text: ORANGE },
  미실시: { fill: GRAY_BG, line: "C9CBD2", text: MUTED },
};
function tag(slide, x, y, text, o = {}) { // 큰 숫자 옆 조건 표시용 작은 칩
  const fs = o.fs || 10;
  const w = o.w || textWidth(text, P(fs)) / K + 0.3;
  R(slide, x, y, w, o.h || 0.3, { fill: o.fill || ORANGE_BG, radius: 0.05, line: o.line });
  T(slide, text, { x, y, w, h: o.h || 0.3, align: "center", valign: "middle", fontSize: fs, bold: o.bold !== false, color: o.color || ORANGE });
  return w;
}
function colHead(slide, x, w, ic, title) { // 열 머리: 아이콘 + 제목 + 가는 선
  icon(slide, ic, x, 1.62, 0.34, "p");
  T(slide, title, { x: x + 0.44, y: 1.6, w: w - 0.44, h: 0.38, fontSize: 13.5, bold: true, color: INK, valign: "middle" });
  line(slide, x, 2.04, x + w, 2.04, { color: RULE, w: 1 });
}

// ------------------------------------------------------------------ UML: 클래스 상자
function classBox(slide, x, y, w, name, stereo, members, o = {}) {
  const head = stereo ? 0.42 : 0.28, lh = 0.19;
  const h = head + members.length * lh + 0.07;
  R(slide, x, y, w, h, { fill: WHITE, line: PURPLE, lw: 1 });
  R(slide, x, y, w, head, { fill: o.head || LAV, line: PURPLE, lw: 1 });
  if (stereo) T(slide, `«${stereo}»`, { x, y: y + 0.03, w, h: 0.17, align: "center", fontSize: 9, italic: true, color: MUTED });
  T(slide, name, { x, y: y + (stereo ? 0.18 : 0.03), w, h: 0.22, align: "center", fontSize: 11.5, bold: true, color: INK });
  members.forEach((m, i) => {
    const ext = m.startsWith("⇢");
    T(slide, m, { x: x + 0.09, y: y + head + 0.03 + i * lh, w: w - 0.14, h: lh, fontSize: 10, color: ext ? ORANGE : BODY, italic: ext });
  });
  return { x, y, w, h, cx: x + w / 2, cy: y + h / 2, r: x + w, b: y + h };
}

// ------------------------------------------------------------------ UML: 시퀀스 다이어그램
function seqDiagram(slide, spec) {
  const { x0, x1, yTop, parts, items } = spec;
  const rowH = spec.rowH || 0.26, selfExtra = 0.1, fs = spec.fs || 10.5;
  const gap = (x1 - x0) / parts.length;
  const cx = {};
  parts.forEach((p, i) => (cx[p.key] = x0 + gap * (i + 0.5)));
  const boxW = Math.min(gap - 0.14, 1.75), boxH = 0.48;
  let y = yTop + boxH + 0.2;
  const msgs = [], frames = [], stack = [];
  let num = 0;
  for (const it of items) {
    if (it.frag) { y += 0.04; const f = { kind: it.frag, label: it.label, a: it.span[0], b: it.span[1], padL: it.padL || 0, y0: y, elses: [] }; stack.push(f); y += 0.3; continue; }
    if (it.else) { stack[stack.length - 1].elses.push({ y, label: it.else }); y += 0.3; continue; }
    if (it.end) { const f = stack.pop(); f.y1 = y; frames.push(f); y += 0.1; continue; }
    num++;
    msgs.push(Object.assign({ y, num }, it));
    y += rowH + (it.from === it.to ? selfExtra : 0);
  }
  const yEnd = y + 0.05;
  parts.forEach((p) => {
    const x = cx[p.key];
    if (p.actor) {
      slide.addShape(S.OVAL, { x: X(x - 0.09), y: Y(yTop), w: Z(0.18), h: Z(0.18), fill: { color: WHITE }, line: { color: PURPLE, width: 1.5 } });
      line(slide, x, yTop + 0.18, x, yTop + 0.34, { color: PURPLE, w: 1.5 });
      line(slide, x - 0.14, yTop + 0.24, x + 0.14, yTop + 0.24, { color: PURPLE, w: 1.5 });
      line(slide, x, yTop + 0.34, x - 0.11, yTop + 0.46, { color: PURPLE, w: 1.5 });
      line(slide, x, yTop + 0.34, x + 0.11, yTop + 0.46, { color: PURPLE, w: 1.5 });
      T(slide, p.label, { x: x + 0.16, y: yTop + 0.1, w: 0.9, h: 0.26, fontSize: 11, bold: true, color: INK });
    } else {
      R(slide, x - boxW / 2, yTop, boxW, boxH, { fill: LAV, line: PURPLE, lw: 1, radius: 0.05 });
      T(slide, p.label, { x: x - boxW / 2, y: yTop, w: boxW, h: boxH, align: "center", valign: "middle", fontSize: 10.5, bold: true, color: INK });
    }
    line(slide, x, yTop + boxH, x, yEnd, { color: LIFELINE, w: 1, dash: "dash" });
  });
  for (const f of frames) {
    const xa = cx[f.a] - boxW / 2 - 0.06 - f.padL, xb = cx[f.b] + boxW / 2 + 0.06;
    R(slide, xa, f.y0, xb - xa, f.y1 - f.y0, { fill: "FAFAFE", line: PURPLE_LIGHT, lw: 1 });
    R(slide, xa, f.y0, 0.52, 0.22, { fill: PURPLE });
    T(slide, f.kind, { x: xa, y: f.y0, w: 0.52, h: 0.22, align: "center", valign: "middle", fontSize: 9.5, bold: true, color: WHITE });
    T(slide, `[${f.label}]`, { x: xa + 0.6, y: f.y0 + 0.01, w: 4, h: 0.21, fontSize: 9.5, bold: true, color: PURPLE });
    for (const e of f.elses) {
      line(slide, xa, e.y - 0.02, xb, e.y - 0.02, { color: PURPLE_LIGHT, w: 1, dash: "dash" });
      T(slide, `[${e.label}]`, { x: xa + 0.08, y: e.y + 0.01, w: 4, h: 0.21, fontSize: 9.5, bold: true, color: PURPLE });
    }
  }
  for (const m of msgs) {
    const xa = cx[m.from];
    if (m.from === m.to) {
      const yy = m.y + 0.13, x2 = xa + 0.26;
      poly(slide, [[xa, yy], [x2, yy], [x2, yy + 0.16], [xa + 0.02, yy + 0.16]], { color: BODY, w: 1.1, end: "triangle" });
      const tw = textWidth(`${m.num}. ${m.text}`, fs) + 0.3;
      const runs = [{ text: `${m.num}. `, options: { bold: true, color: PURPLE } }, { text: m.text, options: { color: INK } }];
      if (x2 + 0.07 + tw <= 12.95) T(slide, runs, { x: x2 + 0.07, y: yy - 0.03, w: tw, h: 0.22, fontSize: fs });
      else T(slide, runs, { x: xa - 0.1 - tw, y: yy - 0.03, w: tw, h: 0.22, fontSize: fs, align: "right" });
    } else {
      const xb = cx[m.to], yy = m.y + 0.22;
      const tw = textWidth(`${m.num}. ${m.text}`, fs) + 0.3, span = Math.abs(xb - xa);
      const runs = [{ text: `${m.num}. `, options: { bold: true, color: PURPLE } }, { text: m.text, options: { color: m.ret ? MUTED : INK } }];
      if (tw <= span - 0.2) T(slide, runs, { x: Math.min(xa, xb) + (span - tw) / 2, y: m.y, w: tw, h: 0.2, fontSize: fs, align: "center" });
      else if (xb > xa) T(slide, runs, { x: xa + 0.08, y: m.y, w: tw, h: 0.2, fontSize: fs, align: "left" });
      else T(slide, runs, { x: xa - 0.08 - tw, y: m.y, w: tw, h: 0.2, fontSize: fs, align: "right" });
      line(slide, xa, yy, xb + (xb > xa ? -0.02 : 0.02), yy, { color: m.ret ? MUTED : BODY, w: 1.1, dash: m.ret ? "dash" : undefined, end: m.ret ? "arrow" : "triangle" });
    }
  }
  return yEnd;
}

// ------------------------------------------------------------------ 데이터
const tc = D.tc.results;
const tcById = Object.fromEntries(tc.map((r) => [r.id, r]));
const nfr = D.nfr;
const runs = nfr.phases.nfr01.runs;
const conc = nfr.phases.concurrency;
const loadr = nfr.phases.api_load;
const res = nfr.resources;
const sec = D.security.checks;
const bench = D.bench;
const pass = (arr) => arr.filter((r) => r.pass).length;
const factsTotal = runs.reduce((a, r) => a + r.facts, 0), factsNoted = runs.reduce((a, r) => a + r.facts_with_note, 0);
const isTpl = (r) => r.model.startsWith("템플릿");
const llmRuns = runs.filter((r) => !isTpl(r)), tplRuns = runs.filter(isTpl);
const sum = (a, f) => a.reduce((x, r) => x + f(r), 0);
const mmss = (s) => { const t = Math.round(s); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };  // 119.5초 → 2:00 (1:60 아님)
const BYLINE = "2026-2 소프트웨어공학 Team 10     김건한 · 김예슬 · 전규민 · 황웅재          2026.12.01";

// ================================================================== 1. 표지
{
  section("표지");
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: SECTION });
  s.addText("찰칵부산: 사진으로 만드는 출처 있는 부산 여행기", { placeholder: "title" });
  s.addText("소프트웨어공학 팀 프로젝트 최종 발표 · 사진의 촬영 시각·위치와 공식 관광 데이터로 여행기 자동 작성",
    { x: 2.17, y: 5.0, w: 15.67, h: 0.55, fontFace: FONT, fontSize: 24, color: MUTED, margin: 0, valign: "middle", isTextBox: true });
  s.addText(BYLINE, { x: 1.01, y: 9.49, w: 14, h: 0.49, fontFace: FONT, fontSize: 20, color: MUTED, margin: 0, valign: "middle", isTextBox: true });
  s.addNotes("[@] 안녕하십니까. 10팀 찰칵부산 발표를 맡은 팀장 김건한입니다. 찰칵부산은 부산 여행 사진을 올리면 방문한 장소를 찾고, 공식 관광 데이터로 출처를 밝힌 여행기를 만들어 주는 서비스입니다.");
}

// ================================================================== 2. 목차·역할 분담
{
  section("개요");
  // 항목별 시간 = 맨 위 SLOTS의 해당 쪽 합 (노트의 시간 표시와 항상 같음)
  const toc = [["프로젝트 개요", 3, 3], ["데모 시연", 4, 4], ["아키텍처 수정사항", 5, 6], ["UML 설계", 7, 9], ["테스트", 10, 14], ["결론", 15, 15]]
    .map(([t, a, b]) => { const sec = SLOTS[b][1] - SLOTS[a][0]; return [t, sec, clock(sec)]; });
  const s = content("목차", "발표 순서와 역할 분담",
    `총 10분 = 표지·목차 ${clock(SLOTS[2][1])} + 아래 6개 항목 ${clock(SLOTS[TIMED][1] - SLOTS[3][0])} (시연 영상 ${mmss(D.video_seconds)} 포함)  |  역할: 백엔드 2명 · 테스트·PM 1명 · 프론트엔드·테스트 1명`,
    "[@] 발표는 개요, 시연 영상, 바뀐 아키텍처, UML, 테스트 결과, 결론 순서로 진행합니다. 구현은 황웅재, 김예슬이 백엔드를, 전규민이 프론트엔드와 테스트를, 제가 테스트와 프로젝트 관리를 맡았습니다.");
  T(s, "목차", { x: 0.55, y: 1.6, w: 3, h: 0.4, fontSize: 16, bold: true, color: INK });
  toc.forEach(([t, , m], i) => {
    const y = 2.12 + i * 0.6;
    circleNum(s, 0.6, y + 0.04, 0.42, String(i + 1).padStart(2, "0"), { fs: 12 });
    T(s, t, { x: 1.2, y: y + 0.04, w: 3.4, h: 0.42, fontSize: 15, bold: true, color: INK, valign: "middle" });
    chip(s, 4.95, y + 0.1, 0.8, 0.3, m, { fs: 10.5, fill: GRAY_BG, color: BODY, bold: false });
    if (i < toc.length - 1) line(s, 1.2, y + 0.54, 5.75, y + 0.54, { color: GRID, w: 0.75 });
  });
  const tot = toc.reduce((a, r) => a + r[1], 0), bw = 5.15, by = 6.15;
  T(s, "시간 배분", { x: 0.6, y: by - 0.38, w: 2, h: 0.3, fontSize: 11, bold: true, color: MUTED });
  let bx = 0.6;
  toc.forEach(([, sec], i) => {
    const w = (bw * sec) / tot;
    R(s, bx, by, w - 0.03, 0.42, { fill: i % 2 ? "8B80EA" : PURPLE });
    T(s, String(i + 1).padStart(2, "0"), { x: bx, y: by, w: w - 0.03, h: 0.42, align: "center", valign: "middle", fontSize: 10, bold: true, color: WHITE });
    bx += w;
  });
  T(s, "역할 분담", { x: 6.85, y: 1.6, w: 3, h: 0.4, fontSize: 16, bold: true, color: INK });
  const people = [
    ["김건한", "2243219 · 팀장", "테스트 · PM", "clipboard"],
    ["황웅재", "2243416", "백엔드", "server"],
    ["전규민", "2229930", "프론트엔드 · 테스트", "monitor"],
    ["김예슬", "2443358", "백엔드", "server"],
  ];
  people.forEach(([n, id, role, ic], i) => {
    const x = 6.85 + (i % 2) * 3.05, y = 2.12 + Math.floor(i / 2) * 1.8;
    R(s, x, y, 2.88, 1.62, { fill: LAV, radius: 0.06 });
    iconCircle(s, ic, x + 0.2, y + 0.22, 0.66);
    T(s, n, { x: x + 1.0, y: y + 0.22, w: 1.8, h: 0.36, fontSize: 17, bold: true, color: INK });
    T(s, id, { x: x + 1.0, y: y + 0.58, w: 1.8, h: 0.26, fontSize: 9.5, color: MUTED });
    chip(s, x + 0.2, y + 1.06, 2.48, 0.38, role, { fill: WHITE, fs: 12 });
  });
  // 발표자: 김건한 전체 진행 (11/26 사용자 확정)
  R(s, 6.85, 5.95, 5.93, 0.62, { fill: PURPLE, radius: 0.06 });
  T(s, [{ text: "발표  ", options: { color: "DCD8FA" } }, { text: "김건한 (전체 진행)", options: { bold: true, color: WHITE } }],
    { x: 7.05, y: 5.95, w: 5.6, h: 0.62, fontSize: 15, valign: "middle" });
}

// ================================================================== 3. 프로젝트 개요
{
  const s = content("① 프로젝트 개요", "서비스 개요: 사진을 올리면 방문 장소를 찾아 출처를 밝힌 여행기 작성",
    "EXIF: 사진에 저장된 촬영 시각·위치  |  VLM: 사진을 보고 답하는 AI  |  LLM: 글을 쓰는 AI",
    "[@] 사용자가 부산 여행 사진을 올리면, 촬영 시각과 위치가 가까운 사진을 하나의 방문지로 묶습니다. 이어서 반경 300m 안의 공식 관광 데이터 후보 중에서 서버의 AI가 장소를 고르고, 확신도가 낮은 곳만 사용자에게 묻습니다. 여행기는 확정된 장소와 공식 데이터만으로 작성합니다. 화면 아래 세 항목은 구현 기준입니다. 후보에 없는 답은 받지 않고, 사실 문장마다 출처를 붙이며, 사진은 외부 AI로 보내지 않습니다.");
  const steps = [
    ["사진 업로드", "시각·위치로 방문지 묶기", "shot_upload.jpg"],
    ["AI 장소 판별", "공식 후보 중에서만 선택", "shot_analyzing.jpg"],
    ["사용자 확인", "확신도 낮은 곳만 확인 요청", "shot_placecheck.jpg"],
    ["동선 지도", "날짜별 경로·이동 시간", "shot_route1.jpg"],
    ["출처 있는 여행기", "사실 문장마다 출처 각주", "shot_story.jpg"],
  ];
  const w = 2.3, g = 0.205;
  steps.forEach(([t, d, f], i) => {
    const x = 0.55 + i * (w + g), y = 1.6;
    const h = shot(s, f, x, y, w);
    circleNum(s, x, y + h + 0.15, 0.34, i + 1, { fs: 11 });
    T(s, t, { x: x + 0.42, y: y + h + 0.15, w: w - 0.42, h: 0.34, valign: "middle", fontSize: 13, bold: true, color: INK });
    T(s, d, { x, y: y + h + 0.56, w, h: 0.3, fontSize: 10.5, color: MUTED });
    if (i < steps.length - 1) T(s, "→", { x: x + w - 0.01, y: y + h / 2 - 0.2, w: g + 0.02, h: 0.36, align: "center", valign: "middle", fontSize: 14, bold: true, color: PURPLE });
  });
  const pr = [["ban", "후보 안에서만 선택", "공식 데이터 후보 밖 답변 거부"], ["quote", "문장마다 출처 표시", "사실 문장에 공식 데이터 각주"], ["lock", "사진 외부 전송 없음", "서버 안의 AI만 분석 · 원본은 분석 후 삭제"]];
  pr.forEach(([ic, t, d], i) => {
    const x = 0.55 + i * 4.13, y = 4.25;
    R(s, x, y, 3.95, 1.9, { fill: LAV, radius: 0.06 });
    iconCircle(s, ic, x + 0.28, y + 0.5, 0.9);
    T(s, t, { x: x + 1.35, y: y + 0.42, w: 2.5, h: 0.5, fontSize: 19, bold: true, color: PURPLE, valign: "middle" });
    T(s, d, { x: x + 1.35, y: y + 0.95, w: 2.5, h: 0.5, fontSize: 11.5, color: BODY });
  });
}

// ================================================================== 4. 데모 시연
{
  section("데모");
  const s = content("② 데모 시연", "데모 시연: 휴대폰 브라우저로 공개 웹사이트에 접속해 녹화, 처리 시간은 실제 속도",
    `공개 주소 접속 → 사진 7장(웹 사진에 촬영 시각·위치 입력) 업로드 → 공유 카드까지 ${mmss(D.video_seconds)}  |  화면을 한 번 클릭하면 재생`,
    `[@] ※ 진행 메모: 화면을 한 번 클릭하면 영상 재생(${mmss(D.video_seconds)}) · 재생이 안 되면 같은 폴더의 시연영상 mp4 직접 실행\n\n공개 주소 접속부터 녹화한 시연 영상이며, 처리 시간은 실제 속도입니다.`);
  foot(s, "화면: 휴대폰 화면 크기(390×844) 브라우저(Chromium)로 녹화, 휴대폰 틀·주소창은 덧그림 · 실기기 테스트 아님 (NFR-06 미실시)", 6.93);
  const poster = "data:image/png;base64," + fs.readFileSync(img("video_poster.png")).toString("base64");
  const vw = 9.3, vh = (vw * 9) / 16;
  frame(s, 0.485, 1.585, vw + 0.03, vh + 0.03);
  s.addMedia({ type: "video", path: VIDEO, x: X(0.5), y: Y(1.6), w: Z(vw), h: Z(vh), cover: poster, objectName: "시연 영상" });
  T(s, "영상 구성", { x: 10.08, y: 1.6, w: 2.8, h: 0.34, fontSize: 13, bold: true, color: INK });
  // 앞 원소는 D.chapters의 이름과 똑같아야 함 (시각 표시)
  const want = [["① 사진 업로드", "사진 업로드", "upload"], ["② AI 장소 판별", "AI 장소 판별", "scan"], ["③ 사용자 확인", "사용자 확인", "usercheck"],
    ["④ 동선 지도", "동선 지도", "route"], ["⑤ 출처 있는 여행기", "출처 있는 여행기", "book"], ["⑥ 공유 카드", "공유 카드", "share"]];
  const chap = Object.fromEntries(D.chapters.map(([t, n]) => [n, t]));
  line(s, 10.29, 2.3, 10.29, 2.05 + 5 * 0.74 + 0.2, { color: LAV_LINE, w: 2 });
  want.forEach(([key, label, ic], i) => {
    if (chap[key] === undefined) throw new Error("영상 장면 이름이 없음: " + key);
    const y = 2.05 + i * 0.74;
    iconCircle(s, ic, 10.08, y, 0.42);
    T(s, mmss(chap[key]), { x: 10.62, y, w: 0.6, h: 0.42, fontSize: 12, bold: true, color: PURPLE, valign: "middle" });
    T(s, label, { x: 11.22, y, w: 1.68, h: 0.42, fontSize: 12, color: INK, valign: "middle" });
  });
}

// ================================================================== 5. 아키텍처 수정사항 ① 변경 요약
{
  section("아키텍처");
  const s = content("③ 시스템 아키텍처 수정사항", "아키텍처 수정사항: 기본 구조 유지, 공개 운영을 위해 6가지 변경",
    "중간 설계(설계서 v1.0, 10/26) → 최종 구현(11/23)",
    "[@] 계층형 구조와 작업 큐, 어댑터, 후보 안에서만 고르는 장소 판별, 사실 대조는 그대로 유지했고, 공개 운영을 위해 여섯 가지를 바꿨습니다. 주요 변경은 두 가지입니다. 여행기를 쓰는 LLM도 서버의 Qwen3.5 4B로 실행해 비용을 0원으로 만들고 여행 기록이 외부로 나가지 않게 했습니다. 그리고 Cloudflare 무료 터널로 서버 포트를 열지 않고 서비스를 공개했습니다.");
  T(s, "그대로 유지", { x: 0.45, y: 1.6, w: 1.4, h: 0.38, fontSize: 12.5, bold: true, color: INK, valign: "middle" });
  let kx = 1.85;
  ["계층형 구조", "작업 큐", "외부 연결 어댑터", "후보 안에서만 판별", "여행기 사실 대조"].forEach((t) => {
    const w = textWidth(t, P(11)) / K + 0.55;
    R(s, kx, 1.61, w, 0.36, { fill: GRAY_BG, radius: 0.06 });
    icon(s, "check", kx + 0.1, 1.67, 0.24, "p");
    T(s, t, { x: kx + 0.38, y: 1.61, w: w - 0.42, h: 0.36, fontSize: 11, color: INK, valign: "middle" });
    kx += w + 0.12;
  });
  const ch = [ // 아이콘, 항목, 중간 설계, 최종 구현, 효과
    ["cpu", "LLM 실행 위치", "외부 LLM API", "서버 Qwen3.5 4B", "비용 0원 · 외부 전송 없음"],
    ["cloud", "공개 배포", "개발 PC 실행", "무료 터널 + nginx", "열린 포트 0개"],
    ["map", "지도", "카카오맵", "OpenStreetMap", "카카오 키 없을 때 자동 전환"],
    ["image", "사진 전송", "원본 전송", "축소 · 6장씩", "Cloudflare 요청 크기 한도 대응"],
    ["trash", "여행 기록 보관", "사용자 삭제 시까지", "3일 뒤 자동 삭제", "개인정보 최소화"],
    ["gauge", "사용 한도·대체", "없음", "한도 + 대체 여행기", "생성 실패 방지"],
  ];
  const cw = 4.01, chh = 2.12;
  ch.forEach(([ic, t, before, after, eff], i) => {
    const x = 0.45 + (i % 3) * (cw + 0.2), y = 2.2 + Math.floor(i / 3) * (chh + 0.2);
    R(s, x, y, cw, chh, { fill: WHITE, line: BOX_LINE, radius: 0.05 });
    iconCircle(s, ic, x + 0.22, y + 0.2, 0.64);
    circleNum(s, x + 0.68, y + 0.12, 0.26, i + 1, { fs: 9, fill: ORANGE });
    T(s, t, { x: x + 1.02, y: y + 0.24, w: 2.85, h: 0.56, fontSize: 15, bold: true, color: INK, valign: "middle" });
    R(s, x + 0.22, y + 1.0, 1.5, 0.5, { fill: GRAY_BG, radius: 0.05 });
    T(s, before, { x: x + 0.22, y: y + 1.0, w: 1.5, h: 0.5, align: "center", valign: "middle", fontSize: 11, color: MUTED, strike: "sngStrike" });
    icon(s, "arrow", x + 1.79, y + 1.1, 0.3, "p");
    R(s, x + 2.14, y + 1.0, 1.65, 0.5, { fill: LAV, radius: 0.05 });
    T(s, after, { x: x + 2.14, y: y + 1.0, w: 1.65, h: 0.5, align: "center", valign: "middle", fontSize: 11.5, bold: true, color: PURPLE });
    tag(s, x + 0.22, y + 1.66, eff, { fs: 10 });
  });
}

// ================================================================== 6. 아키텍처 수정사항 ② 최종 배포 구조
{
  const s = content("③ 시스템 아키텍처 수정사항", "최종 배포 구조: 컨테이너 7개, 외부에 열린 포트 0개",
    "터널: 서버가 Cloudflare에 먼저 연결해 두는 방식 → 포트를 열지 않아도 외부에서 HTTPS로 접속",
    "[@] 최종 배포 구조입니다. 사용자는 HTTPS로 Cloudflare에 접속하고, 요청은 서버의 cloudflared가 먼저 연결해 둔 터널을 거쳐 nginx로 들어옵니다. 그래서 외부에 열린 포트가 없습니다. API가 작업을 큐에 등록하면 워커가 처리하고, AI는 같은 GPU의 Ollama에서 실행합니다. 데이터베이스와 큐는 외부 접속이 차단된 내부 망에만 연결했습니다.");
  R(s, 0.45, 2.05, 1.95, 3.25, { fill: GRAY_BG, line: BOX_LINE, radius: 0.06 });
  T(s, "사용자 기기", { x: 0.45, y: 2.12, w: 1.95, h: 0.3, align: "center", fontSize: 12, bold: true, color: INK });
  [["laptop", "PC 브라우저", 2.55], ["smartphone", "휴대폰", 3.2]].forEach(([ic, t, y]) => {
    R(s, 0.62, y, 1.6, 0.5, { fill: WHITE, line: BOX_LINE, radius: 0.06 });
    icon(s, ic, 0.74, y + 0.1, 0.3, "p");
    T(s, t, { x: 1.1, y, w: 1.08, h: 0.5, fontSize: 10.5, bold: true, color: INK, valign: "middle" });
  });
  T(s, "지도: OpenStreetMap", { x: 0.55, y: 3.92, w: 1.4, h: 0.4, fontSize: 9.5, color: BODY });
  circleNum(s, 1.95, 3.92, 0.3, 3, { fs: 10, fill: ORANGE });
  T(s, "사진 축소 · 6장씩 전송", { x: 0.55, y: 4.52, w: 1.4, h: 0.4, fontSize: 9.5, color: BODY });
  circleNum(s, 1.95, 4.55, 0.3, 4, { fs: 10, fill: ORANGE });
  R(s, 2.85, 2.7, 1.75, 1.3, { fill: ORANGE_BG, line: ORANGE, radius: 0.08 });
  icon(s, "cloud", 3.54, 2.78, 0.38, "o");
  T(s, "Cloudflare", { x: 2.85, y: 3.17, w: 1.75, h: 0.3, align: "center", fontSize: 12, bold: true, color: ORANGE });
  T(s, "HTTPS · 무료 터널", { x: 2.85, y: 3.5, w: 1.75, h: 0.3, align: "center", fontSize: 10, color: BODY });
  circleNum(s, 4.38, 2.58, 0.3, 2, { fs: 10, fill: ORANGE });
  line(s, 2.4, 3.15, 2.85, 3.15, { color: BODY, end: "triangle" });
  T(s, "HTTPS", { x: 2.4, y: 2.88, w: 0.45, h: 0.22, align: "center", fontSize: 9, color: MUTED });
  R(s, 4.95, 1.62, 7.92, 5.2, { fill: "FCFCFE", line: PURPLE, lw: 1, radius: 0.05 });
  T(s, "서버 PC · Docker Compose", { x: 5.12, y: 1.7, w: 5.5, h: 0.3, fontSize: 12.5, bold: true, color: INK });
  T(s, "GPU RTX 4080 SUPER 16GB", { x: 5.12, y: 1.99, w: 7.6, h: 0.26, fontSize: 10, color: MUTED });
  const C = (x, y, ic, name, desc, o = {}) => {
    R(s, x, y, 1.75, 0.92, { fill: o.fill || WHITE, line: o.line || BOX_LINE, lw: 1, radius: 0.05 });
    icon(s, ic, x + 0.725, y + 0.07, 0.3, "p");
    T(s, name, { x, y: y + 0.38, w: 1.75, h: 0.26, align: "center", fontSize: 11.5, bold: true, color: o.color || INK });
    T(s, desc, { x: x + 0.05, y: y + 0.63, w: 1.65, h: 0.24, align: "center", fontSize: 9.5, color: BODY });
    return { x, y, r: x + 1.75, b: y + 0.92, cx: x + 0.875, cy: y + 0.46 };
  };
  const tun = C(5.15, 2.6, "network", "tunnel", "Cloudflare 연결");
  const web = C(7.15, 2.6, "globe", "web · nginx", "화면 · 요청 제한");
  const api = C(9.15, 2.6, "server", "api · FastAPI", "요청 처리 · 검증");
  const vlm = C(11.0, 2.6, "cpu", "vlm · Ollama", "Qwen3.5 4B (GPU)", { fill: LAV, line: PURPLE, color: PURPLE });
  R(s, 7.0, 4.45, 3.95, 1.5, { fill: "F7F7FA", line: "B9BCC4", dash: "dash", radius: 0.05 });
  icon(s, "lock", 7.12, 5.61, 0.24, "g");
  T(s, "내부 망 · 외부 접속 차단", { x: 7.42, y: 5.58, w: 2.8, h: 0.3, fontSize: 9.5, color: MUTED, valign: "middle" });
  const pg = C(7.15, 4.6, "database", "postgres", "여행 데이터", { fill: GRAY_BG });
  const rd = C(9.15, 4.6, "list", "redis", "작업 큐", { fill: GRAY_BG });
  const wk = C(11.0, 4.6, "cog", "worker", "분석 · 여행기 작성");
  circleNum(s, vlm.r - 0.2, vlm.y - 0.15, 0.3, 1, { fs: 10, fill: ORANGE });
  circleNum(s, tun.r - 0.2, tun.y - 0.15, 0.3, 2, { fs: 10, fill: ORANGE });
  circleNum(s, pg.r - 0.2, pg.y - 0.15, 0.3, 5, { fs: 10, fill: ORANGE });
  circleNum(s, api.r - 0.2, api.y - 0.15, 0.3, 6, { fs: 10, fill: ORANGE });
  poly(s, [[3.72, 2.35], [tun.cx, 2.35], [tun.cx, tun.y]], { color: ORANGE, w: 1.5, dash: "dash", end: "triangle" });
  line(s, 3.72, 2.35, 3.72, 2.7, { color: ORANGE, w: 1.5, dash: "dash", end: "triangle" });
  T(s, "터널: 서버가 먼저 연결", { x: 2.55, y: 2.1, w: 2.35, h: 0.22, fontSize: 9, color: ORANGE, align: "center" });
  line(s, tun.r, 3.06, web.x, 3.06, { end: "triangle" });
  line(s, web.r, 3.06, api.x, 3.06, { end: "triangle" });
  line(s, api.r, 3.06, vlm.x, 3.06, { end: "triangle" });
  line(s, api.x + 1.5, api.b, api.x + 1.5, rd.y, { end: "triangle" });
  T(s, "작업 등록", { x: api.x + 0.62, y: 3.95, w: 0.82, h: 0.22, fontSize: 9, color: MUTED, align: "right" });
  line(s, rd.r, 5.06, wk.x, 5.06, { end: "triangle" });
  poly(s, [[api.x + 0.15, api.b], [api.x + 0.15, 4.25], [pg.cx, 4.25], [pg.cx, pg.y]], { end: "triangle" });
  line(s, wk.x + 1.45, wk.y, wk.x + 1.45, vlm.b, { end: "triangle" });
  poly(s, [[wk.x + 0.12, wk.b], [wk.x + 0.12, 6.07], [pg.x + 0.12, 6.07], [pg.x + 0.12, pg.b]], { end: "triangle" });
  T(s, "결과 저장", { x: 9.2, y: 6.08, w: 1.0, h: 0.2, fontSize: 9, color: MUTED });
  R(s, 5.12, 6.32, 7.6, 0.42, { fill: LAV, radius: 0.04 });
  icon(s, "lock", 5.25, 6.38, 0.3, "p");
  T(s, "외부에 열린 포트 0개", { x: 5.65, y: 6.32, w: 3.6, h: 0.42, fontSize: 13.5, bold: true, color: PURPLE, valign: "middle" });
  T(s, "주황 번호 = 앞 장 변경 항목", { x: 9.3, y: 6.32, w: 3.3, h: 0.42, fontSize: 9.5, color: MUTED, valign: "middle", align: "right" });
}

// ================================================================== 7. UML 클래스 다이어그램
{
  section("UML");
  const s = content("④ UML 설계", "UML ① 클래스 다이어그램: 주요 모듈 구성, 외부 AI·API는 어댑터 2개로 분리",
    "어댑터: 외부 AI·장소 API 호출을 한 클래스에 모은 것 → 모델·API가 바뀌어도 AIGateway·PlaceDataAdapter만 수정",
    "[@] 주요 클래스입니다. AnalysisOrchestrator가 작업 순서를 제어하며 방문지 묶기, 후보 검색, 장소 판별, 위치 없는 사진 추천을 차례로 호출합니다. 외부 AI와 장소 데이터 호출은 AIGateway와 PlaceDataAdapter 두 클래스에만 모았습니다. 그래서 LLM을 외부 API에서 Ollama로 바꿀 때도 다른 클래스는 수정하지 않았습니다. 객체 연결은 services.py 한 곳에서 하므로, 테스트할 때 가짜 AI나 장애 상황을 넣을 수 있습니다.");
  const C1 = 0.45, C2 = 3.45, C3 = 6.75, C4 = 9.95;
  const orch = classBox(s, C1, 1.95, 2.55, "AnalysisOrchestrator", "control", ["+run(job_id)", "-_match_visit(trip, visit)", "-_purge_sensitive(trip)"]);
  const story = classBox(s, C1, 5.3, 2.55, "StoryGenerator", "control", ["+generate(story)", "+rewrite_paragraph(story, pid)", "-_assemble(문장들, ctx)"]);
  const clus = classBox(s, C2, 2.0, 2.8, "VisitClusterer", "utility", ["+cluster_photos(photos) : ClusterResult"]);
  const cand = classBox(s, C2, 2.79, 2.8, "CandidateFinder", null, ["+find(lat, lng) : Candidate[]", "+search(검색어) : Candidate[]"]);
  const match = classBox(s, C2, 3.63, 2.8, "PlaceMatcher", null, ["+ask(사진, 후보) : VlmAnswer", "+apply(방문지, 답) : MatchLog[]"]);
  const unt = classBox(s, C2, 4.47, 2.8, "UntaggedPhotoResolver", null, ["+resolve(시각, 방문지, 사진) : Suggestion"]);
  const fact = classBox(s, C2, 5.4, 2.8, "FactChecker", "utility", ["+check_generated_sentence()", "+check_edited_sentence()"]);
  classBox(s, C3, 1.55, 2.6, "TripRepository", "repository", ["+get_trip(id, owner) : Trip", "+delete_trip(trip)"]);
  const cache = classBox(s, C3, 2.79, 2.6, "PlaceCache", null, ["+resolve(place_id) : PlaceRecord", "+upsert(record) : Place"]);
  const ai = classBox(s, C3, 3.75, 2.6, "AIGateway", "adapter", ["+vlm_match(사진, 후보) : str", "+vlm_compare(사진, 이웃) : str", "+llm_story_part(하루 방문지) : str",
    "+template_paragraph(방문지) : str", "⇢ Ollama · qwen3.5:4b"]);
  const pda = classBox(s, C4, 2.55, 2.9, "PlaceDataAdapter", "adapter", ["+tour_nearby(lat, lng, r)", "+busan_all()", "+kakao_nearby(lat, lng, r)"]);
  T(s, "⇢ TourAPI · 부산시 · 카카오 로컬\n   (키가 없으면 샘플 40곳)", { x: C4, y: pda.b + 0.05, w: 2.9, h: 0.42, fontSize: 9.5, italic: true, color: ORANGE });
  const tx = 3.22;
  line(s, orch.r, 2.48, tx, 2.48);
  line(s, tx, clus.cy, tx, unt.cy);
  line(s, tx, clus.cy, C2, clus.cy, { end: "arrow", dash: "dash" });
  [cand, match, unt].forEach((b) => line(s, tx, b.cy, C2, b.cy, { end: "arrow" }));
  poly(s, [[2.2, orch.y], [2.2, 1.75], [C3, 1.75]], { end: "arrow" });
  line(s, cand.r, cache.cy, C3, cache.cy, { end: "arrow" });
  poly(s, [[cand.r, 2.98], [6.5, 2.98], [6.5, 2.66], [C4, 2.66]], { end: "arrow" });
  line(s, cache.r, 3.12, C4, 3.12, { end: "arrow" });
  line(s, match.r, match.cy, C3, match.cy, { end: "arrow" });
  line(s, unt.r, unt.cy, C3, unt.cy, { end: "arrow" });
  line(s, story.r, fact.cy, C2, fact.cy, { end: "arrow", dash: "dash" });
  poly(s, [[1.7, story.b], [1.7, 6.55], [8.05, 6.55], [8.05, ai.b]], { end: "arrow" });
  poly(s, [[8.05, 6.55], [9.62, 6.55], [9.62, 3.42], [cache.r, 3.42]], { end: "arrow" });
  R(s, C4, 4.45, 2.9, 1.95, { fill: GRAY_BG, radius: 0.05 });
  T(s, "표기", { x: C4 + 0.12, y: 4.52, w: 1, h: 0.24, fontSize: 10.5, bold: true, color: INK });
  line(s, C4 + 0.14, 4.93, C4 + 0.62, 4.93, { end: "arrow" });
  T(s, "연관 (객체를 받아서 사용)", { x: C4 + 0.72, y: 4.82, w: 2.15, h: 0.22, fontSize: 9.5 });
  line(s, C4 + 0.14, 5.22, C4 + 0.62, 5.22, { end: "arrow", dash: "dash" });
  T(s, "의존 (함수 호출만 함)", { x: C4 + 0.72, y: 5.11, w: 2.15, h: 0.22, fontSize: 9.5 });
  T(s, "«adapter» 외부 AI·API 호출 담당\n«repository» DB 읽기·쓰기 담당\n«control» 작업 순서 제어 · «utility» 계산 함수",
    { x: C4 + 0.12, y: 5.4, w: 2.72, h: 0.95, fontSize: 9.5, color: MUTED });
}

// ================================================================== 8. UML 시퀀스 ① 사진 분석
{
  const s = content("④ UML 설계", "UML ② 시퀀스 다이어그램: 사진 분석은 작업 큐에서 별도로 처리",
    "DBSCAN: 시각·위치가 가까운 사진 묶기  |  확신도 0.8 이상 '자동확정' · 0.5~0.8 '확인필요' · 0.5 미만 '선택필요'",
    "[@] 사진 분석 흐름입니다. 사진을 보내고 분석을 요청하면 API는 작업 번호를 바로 돌려주고, 분석은 작업 큐에서 따로 처리합니다. 화면은 2초마다 진행 상황을 조회하므로 분석 중에 화면을 벗어나도 됩니다. 워커는 촬영 정보로 방문지를 묶은 뒤, 방문지별로 동시에 후보를 조회하고 AI 판별을 요청합니다. 후보가 없으면 600m로 넓힙니다. PlaceMatcher는 후보에 없는 답을 거부하고, 확신도 0.8과 0.5를 기준으로 상태를 나눕니다. 마지막으로 원본 사진과 좌표를 삭제합니다.");
  seqDiagram(s, {
    x0: 0.4, x1: 12.95, yTop: 1.55,
    parts: [{ key: "U", label: "여행자", actor: true }, { key: "W", label: "웹 화면\n(Web Client)" }, { key: "A", label: "여행 API\n(Trip API)" }, { key: "Q", label: "작업 큐\n(Redis)" },
      { key: "O", label: "Analysis\nOrchestrator" }, { key: "M", label: "Place Matcher" }, { key: "G", label: "AI Gateway\n(Qwen3.5 4B)" }],
    items: [
      { from: "U", to: "W", text: "사진 선택 · AI 분석 동의" },
      { from: "W", to: "A", text: "사진 전송 → 분석 요청 (POST)" },
      { from: "A", to: "Q", text: "작업 등록 (동시 작업 수 확인)" },
      { from: "A", to: "W", text: "접수(202) · 작업 번호 job_id", ret: true },
      { frag: "loop", label: "2초마다", span: ["W", "A"] },
      { from: "W", to: "A", text: "진행 조회 GET /jobs/{id}" },
      { from: "A", to: "W", text: "진행률 · 방문지 미리보기", ret: true },
      { end: true },
      { from: "Q", to: "O", text: "작업 실행 run(job_id)" },
      { from: "O", to: "O", text: "EXIF 추출 → DBSCAN 방문지 묶기" },
      { frag: "par", label: "방문지별 동시 처리", span: ["O", "G"], padL: 0.35 },
      { from: "O", to: "O", text: "후보 조회 (300m, 없으면 600m)" },
      { from: "O", to: "M", text: "장소 판별 요청 ask(대표 사진, 후보)" },
      { from: "M", to: "G", text: "vlm_match() · JSON 형식 고정" },
      { from: "G", to: "M", text: "장소 ID · 확신도 · 판단 이유", ret: true },
      { from: "M", to: "M", text: "후보 밖 답·형식 오류 1회 재요청 → 상태 결정" },
      { end: true },
      { from: "O", to: "O", text: "위치 없는 사진 추천 → 원본 사진·좌표 삭제" },
    ],
  });
}

// ================================================================== 9. UML 시퀀스 ② 여행기 생성
{
  const s = content("④ UML 설계", "UML ③ 시퀀스 다이어그램: 여행기 문장마다 공식 데이터와 대조",
    "사실 대조: 문장 속 수치·장소·시간대 표현을 공식 데이터·사진 기록과 비교  |  템플릿 문단: LLM이 실패한 날만 쓰는 공식 데이터 문장",
    "[@] 여행기 생성 흐름입니다. StoryGenerator는 확정된 방문지와 공식 데이터를 날짜별로, 하루 방문지가 많으면 5곳씩 나눠 LLM에 보냅니다. 한 번에 보내면 문맥 한도를 넘어 응답이 잘렸기 때문입니다. 응답이 잘리거나 형식이 틀린 날만 템플릿 문단으로 바꾸고, FactChecker가 모든 문장을 공식 데이터와 사진 기록에 대조합니다.");
  seqDiagram(s, {
    x0: 0.4, x1: 12.95, yTop: 1.55,
    parts: [{ key: "U", label: "여행자", actor: true }, { key: "W", label: "웹 화면\n(Web Client)" }, { key: "A", label: "여행기 API\n(Story API)" }, { key: "S", label: "Story\nGenerator" },
      { key: "G", label: "AI Gateway\n(Qwen3.5 4B)" }, { key: "C", label: "Fact Checker" }],
    items: [
      { from: "U", to: "W", text: "문체 선택 (블로그 · 일기 · 간결)" },
      { from: "W", to: "A", text: "여행기 생성 요청 (POST)" },
      { from: "A", to: "S", text: "작업 큐 → generate(story)" },
      { from: "S", to: "S", text: "확정 방문지 + 공식 데이터로 입력 구성 (날짜별, 5곳 단위)" },
      { frag: "par", label: "부분마다 (동시 2개)", span: ["S", "G"] },
      { from: "S", to: "G", text: "llm_story_part(하루 방문지 최대 5곳)" },
      { from: "G", to: "S", text: "문장 목록 (장소 ID · 근거 항목 · 사실 여부)", ret: true },
      { end: true },
      { frag: "opt", label: "응답 잘림 · 형식 오류인 날", span: ["S", "G"] },
      { from: "S", to: "G", text: "template_paragraph(그날 방문지)" },
      { from: "G", to: "S", text: "공식 데이터 문장으로 만든 그날 문단", ret: true },
      { end: true },
      { frag: "loop", label: "문장마다", span: ["S", "C"] },
      { from: "S", to: "C", text: "check_generated_sentence(문장, 공식 데이터, 사진 기록)" },
      { from: "C", to: "S", text: "통과 / 경고 (수치 · 근거 · 미확정 장소 · 한자 · 시간대)", ret: true },
      { end: true },
      { from: "S", to: "S", text: "경고 문장 삭제 → 각주 번호 → 문단별 작성 방식 표시" },
      { from: "W", to: "A", text: "완료 후 여행기 조회 (GET)" },
      { from: "A", to: "W", text: "본문 + 각주 + 작성 방식 문구", ret: true },
    ],
  });
}

// ================================================================== 10. 테스트 결과 요약 (요구사항 명세서 기준)
const FRQ = REQS.filter((q) => q.id.startsWith("FR")), NFQ = REQS.filter((q) => q.id.startsWith("NFR"));
const stCnt = (arr, st) => arr.filter((q) => q.state === st).length;
const stIds = (arr, st) => arr.filter((q) => q.state === st).map((q) => q.id).join("·");
{
  section("테스트");
  const s = content("⑤ 테스트", `테스트 결과: 기능 테스트 ${pass(tc)}/${tc.length} 통과, 명세서 기준 충족은 기능 ${stCnt(FRQ, "충족")}/${FRQ.length}·비기능 ${stCnt(NFQ, "충족")}/${NFQ.length}`,
    "충족: 명세서대로 확인  ·  조건부: 다른 조건(샘플 데이터·대체 구현·대체 평가)  ·  부분: 일부만 확인  ·  미실시: 검증 안 함",
    `[@] 테스트는 V 모델에 따라 단위, 통합, 시스템·인수 테스트로 나누고, 판정은 중간에 제출한 요구사항 명세서를 기준으로 했습니다. 기능 테스트 ${tc.length}개는 모두 통과했고, 발견한 결함 7건도 모두 고쳤습니다. 명세서 문구 그대로 충족한 것은 기능 ${FRQ.length}개 중 ${stCnt(FRQ, "충족")}개, 비기능 ${NFQ.length}개 중 ${stCnt(NFQ, "충족")}개입니다. 나머지는 샘플 데이터 같은 조건이 붙었거나, 실기기·사용성처럼 아직 하지 못한 항목입니다.`);
  const L = ["요구사항 분석", "아키텍처 설계", "모듈 설계"];
  const Rr = [["시스템·인수 테스트", "공개 서버 기능·비기능"], ["통합 테스트", "인수 기준별 흐름"], ["단위 테스트", "주요 컴포넌트"]];
  L.forEach((a, i) => {
    const xl = 0.5 + i * 0.35, xr = 6.6 - 2.1 - i * 0.35, y = 1.75 + i * 1.05;
    R(s, xl, y, 2.1, 0.72, { fill: WHITE, line: BOX_LINE, radius: 0.05 });
    T(s, a, { x: xl, y, w: 2.1, h: 0.72, align: "center", valign: "middle", fontSize: 12.5, bold: true, color: INK });
    R(s, xr, y, 2.1, 0.72, { fill: LAV, radius: 0.05 });
    T(s, Rr[i][0], { x: xr, y: y + 0.07, w: 2.1, h: 0.34, align: "center", valign: "middle", fontSize: 12, bold: true, color: PURPLE });
    T(s, Rr[i][1], { x: xr, y: y + 0.41, w: 2.1, h: 0.26, align: "center", valign: "middle", fontSize: 10, color: BODY });
    line(s, xl + 2.1, y + 0.36, xr, y + 0.36, { color: PURPLE_LIGHT, dash: "dash", begin: "arrow", end: "arrow", w: 1 });
  });
  R(s, 1.95, 4.95, 3.2, 0.58, { fill: PURPLE, radius: 0.05 });
  T(s, "구현", { x: 1.95, y: 4.95, w: 3.2, h: 0.58, align: "center", valign: "middle", fontSize: 13, bold: true, color: WHITE });
  R(s, 0.5, 5.85, 6.1, 0.66, { fill: GRAY_BG, radius: 0.05 });
  icon(s, "repeat", 0.66, 5.98, 0.4, "p");
  T(s, [{ text: "회귀 테스트  ", options: { bold: true, color: INK } }, { text: `결함 수정 후 자동 테스트 ${D.pytest.total}개 다시 실행 (11/25)`, options: { color: BODY } }],
    { x: 1.2, y: 5.85, w: 5.3, h: 0.66, fontSize: 12, valign: "middle" });
  // 오른쪽: 판정별 누적 막대(기능·비기능) → 요구사항 20개 타일 → 범례. 모두 REQS[].state 하나로 그림
  const order = ["충족", "조건부", "부분", "미실시"];
  [[FRQ, "기능 요구사항", 1.6], [NFQ, "비기능 요구사항", 2.58]].forEach(([arr, lab, y]) => {
    T(s, `${lab} ${arr.length}개`, { x: 7.05, y, w: 3, h: 0.32, fontSize: 12.5, bold: true, color: INK, valign: "middle" });
    let bx = 7.05;
    const bw = 5.78;
    order.forEach((k) => {
      const n = stCnt(arr, k);
      if (!n) return;
      const w = (bw * n) / arr.length, st = STATE[k];
      R(s, bx, y + 0.36, w - 0.03, 0.46, { fill: st.fill, line: st.line });
      T(s, `${k} ${n}`, { x: bx, y: y + 0.36, w: w - 0.03, h: 0.46, align: "center", valign: "middle", fontSize: 11, bold: true, color: st.text });
      bx += w;
    });
  });
  const tile = (q, x, y) => {
    const st = STATE[q.state];
    R(s, x, y, 0.86, 0.38, { fill: st.fill, line: st.line, radius: 0.05 });
    T(s, q.id, { x, y, w: 0.86, h: 0.38, align: "center", valign: "middle", fontSize: 10, bold: true, color: st.text });
  };
  FRQ.forEach((q, i) => tile(q, 7.05 + (i % 6) * 0.96, 3.62 + Math.floor(i / 6) * 0.46));
  NFQ.forEach((q, i) => tile(q, 7.05 + (i % 4) * 0.96, 4.62 + Math.floor(i / 4) * 0.46));
  Object.entries(STATE).forEach(([k, st], i) => {
    const y = 4.6 + i * 0.22;
    R(s, 11.05, y + 0.03, 0.2, 0.16, { fill: st.fill, line: st.line, radius: 0.02 });
    T(s, k, { x: 11.33, y, w: 1.4, h: 0.22, fontSize: 9.5, color: BODY, valign: "middle" });
  });
  [[`${D.pytest.total}/${D.pytest.total}`, "자동 테스트 통과", LAV, PURPLE], [`${pass(sec)}/${sec.length}`, "보안 점검 통과", LAV, PURPLE],
   ["결함 7건", "7건 모두 수정\n(11/25 재측정 확인)", LAV, PURPLE]].forEach(([big, lab, bg, col], i) => {
    const x = 7.05 + i * 1.97;
    R(s, x, 5.65, 1.85, 1.15, { fill: bg, radius: 0.06 });
    T(s, big, { x: x + 0.14, y: 5.7, w: 1.62, h: 0.5, fontSize: 20, bold: true, color: col, valign: "middle" });
    T(s, lab, { x: x + 0.14, y: 6.2, w: 1.65, h: 0.52, fontSize: 9.5, bold: true, color: INK });
  });
}

// ================================================================== 11. 기능 테스트 케이스 (사용자 흐름 지도)
const shortIds = (t) => t.replace(/\b(FR|UC|AC)-(\d+)·\1-(\d+)/g, "$1-$2·$3");
const reqCell = (id) => { const q = shortIds(TCT[id].req).split(" / "); return { text: q[0] + (q.length > 1 ? "\n" + q.slice(1).join(" · ") : ""), options: { align: "center" } }; };
{
  const s = content("⑤ 테스트 · 기능", "기능 테스트 케이스: 명세서의 유스케이스·인수 기준에서 15개 도출, 모두 PASS",
    "사용자 흐름 단계별 배치  |  케이스별 입력·결과와 명세서 번호는 부록 A3",
    "[@] 기능 테스트 케이스는 명세서의 유스케이스 흐름과 인수 기준에서 입력과 예상 결과를 뽑아 강의 형식대로 작성했고, 공개 서버에서 실행했습니다. 화면은 사용자 흐름 단계별로 케이스를 배치한 것으로, 15개 모두 통과했습니다. 예를 들어 TC-05는 AI 답이 후보 안에서만 나오고 확신도 0.8 이상만 자동 확정되는지 확인합니다. TC-13은 1차 실행에서 다시 쓴 문단이 이전과 같아 실패했고, 결함을 수정한 뒤 통과했습니다. 케이스별 상세와 명세서 번호는 부록에 있습니다.");
  const stages = [["upload", "업로드", ["TC-01", "TC-02", "TC-03"]], ["scan", "AI 분석", ["TC-04", "TC-05"]], ["usercheck", "사용자 확인", ["TC-07", "TC-08"]],
    ["route", "동선·장소", ["TC-09", "TC-10", "TC-11"]], ["book", "여행기", ["TC-06", "TC-12", "TC-13"]], ["share", "공유", ["TC-14"]], ["trash", "삭제", ["TC-15"]]];
  const sw = 12.43 / stages.length;
  stages.forEach(([ic, label, ids], i) => {
    const cx = 0.45 + sw * (i + 0.5);
    iconCircle(s, ic, cx - 0.38, 1.62, 0.76);
    if (i < stages.length - 1) line(s, cx + 0.48, 2.0, cx + sw - 0.48, 2.0, { color: PURPLE_LIGHT, w: 1.5, end: "triangle" });
    T(s, label, { x: cx - sw / 2, y: 2.46, w: sw, h: 0.32, align: "center", fontSize: 13, bold: true, color: INK });
    ids.forEach((id, k) => {
      const r = tcById[id], y = 2.9 + k * 0.42, retry = id === "TC-13";
      R(s, cx - 0.62, y, 1.24, 0.34, { fill: retry ? ORANGE_BG : LAV, line: retry ? ORANGE : undefined, radius: 0.05 });
      icon(s, r.pass ? (retry ? "repeat" : "check") : "alert", cx - 0.54, y + 0.06, 0.22, retry ? "o" : "p");
      T(s, id, { x: cx - 0.28, y, w: 0.86, h: 0.34, fontSize: 10.5, bold: true, color: retry ? ORANGE : PURPLE, valign: "middle" });
    });
    if (ids.includes("TC-13")) T(s, "1차 실패 → 수정 후 통과", { x: cx - sw / 2, y: 4.12, w: sw, h: 0.26, align: "center", fontSize: 9, color: ORANGE });
  });
  const y0 = 4.6;
  R(s, 0.45, y0, 2.45, 1.95, { fill: LAV, radius: 0.06 });
  T(s, `${pass(tc)}/${tc.length}`, { x: 0.62, y: y0 + 0.2, w: 2.2, h: 0.8, fontSize: 40, bold: true, color: PURPLE, valign: "middle" });
  T(s, "PASS", { x: 0.62, y: y0 + 1.02, w: 2.2, h: 0.32, fontSize: 14, bold: true, color: INK });
  T(s, "공개 서버에서 실행", { x: 0.62, y: y0 + 1.36, w: 2.2, h: 0.3, fontSize: 10.5, color: BODY });
  [["scan", "TC-05", "AI 답은 공식 후보 안에서만", "확신도 0.8 이상만 자동 확정", PURPLE],
   ["image", "TC-08", "위치 없는 사진도 방문지 추천", "촬영 시각 + 사진 비교", PURPLE],
   ["repeat", "TC-13", "다시 쓰기 결함 발견 → 수정", "1차 실패 후 재실행 통과", ORANGE]].forEach(([ic, id, head, det, col], j) => {
    const x = 3.05 + j * 3.28;
    R(s, x, y0, 3.14, 1.95, { fill: WHITE, line: BOX_LINE, radius: 0.06 });
    iconCircle(s, ic, x + 0.2, y0 + 0.22, 0.56, { bg: col });
    T(s, id, { x: x + 0.9, y: y0 + 0.22, w: 2.1, h: 0.56, fontSize: 12, bold: true, color: col, valign: "middle" });
    T(s, head, { x: x + 0.2, y: y0 + 0.92, w: 2.85, h: 0.4, fontSize: 13, bold: true, color: INK, valign: "middle" });
    T(s, det, { x: x + 0.2, y: y0 + 1.34, w: 2.85, h: 0.36, fontSize: 11, color: BODY, valign: "middle" });
  });
}

// ================================================================== 12. 비기능 ① 성능
const chartBase = (o) => Object.assign({ titleFontFace: FONT, titleFontSize: P(11.5), titleColor: INK, legendFontFace: FONT, legendFontSize: P(9.5), legendColor: BODY,
  dataLabelFontFace: FONT, dataLabelFontSize: P(9), dataLabelColor: INK, valAxisLabelFontFace: FONT, valAxisLabelFontSize: P(9.5), valAxisLabelColor: MUTED,
  catAxisLabelFontFace: FONT, catAxisLabelFontSize: P(9.5), catAxisLabelColor: MUTED, valGridLine: { color: "E6E6E6", size: 0.5 }, catGridLine: { style: "none" },
  valAxisLineShow: false, catAxisLineColor: "C8CBD2" }, o);
{
  section("비기능 테스트");
  const a = nfr.phases.nfr01;
  const s = content("⑤ 테스트 · 비기능", `비기능 ① 성능: 사진 20장 분석 평균 ${a.analysis_avg}초, 명세서 목표(1분 이내) 충족`,
    "NFR-01: 사진 20장 분석이 1분 이내 (20장 세트 10회 평균으로 검증)",
    `[@] 명세서의 NFR-01은 사진 20장 분석을 1분 안에 끝내는 것입니다. 명세서대로 20장 세트로 10번 측정했고, 평균 ${a.analysis_avg}초로 목표의 ${Math.round(60 / a.analysis_avg)}분의 1 수준입니다. 가장 느린 경우도 ${a.analysis_max.toFixed(1)}초였습니다. 동시에 4건을 분석해도 가장 늦은 작업이 ${conc[2].max_s.toFixed(1)}초로 1분 안에 끝났고, 서버 내부에서 잰 동시 접속 100개에서도 API 오류는 없었습니다. 자원 사용량 같은 상세 수치는 부록에 있습니다.`);
  icon(s, "timer", 0.5, 1.72, 0.55, "p");
  T(s, `${a.analysis_avg}초`, { x: 1.15, y: 1.52, w: 3.5, h: 0.95, fontSize: 46, bold: true, color: PURPLE, valign: "middle" });
  T(s, "사진 20장 분석 평균 (10회)", { x: 0.5, y: 2.52, w: 5.5, h: 0.32, fontSize: 13, bold: true, color: INK });
  const bx = 1.4, bwFull = 4.6;
  [["목표", 60, "1분", "E4E5EA", MUTED], ["실측", a.analysis_avg, `${a.analysis_avg}초`, PURPLE, PURPLE]].forEach(([lab, v, txt, fill, col], i) => {
    const y = 3.1 + i * 0.62, len = (bwFull * v) / 60;
    T(s, lab, { x: 0.5, y, w: 0.85, h: 0.42, fontSize: 12, bold: true, color: col, valign: "middle" });
    R(s, bx, y + 0.04, len, 0.34, { fill });
    if (i === 0) T(s, txt, { x: bx, y, w: len - 0.1, h: 0.42, fontSize: 12, bold: true, color: BODY, valign: "middle", align: "right" });
    else tag(s, bx + len + 0.15, y + 0.06, `목표의 1/${Math.round(60 / a.analysis_avg)} 수준`, { fs: 10 });
  });
  [["layers", `${conc[2].max_s.toFixed(1)}초`, "동시 4건도 1분 이내"], ["badge", `${runs.filter((r) => r.analysis_s <= 60).length}/${runs.length}`, "모든 회차 목표 충족"], ["server", `${loadr.reduce((x, r) => x + r.errors, 0)}건`, "API 오류 · 동시 접속 100\n(서버 내부에서 측정)"]].forEach(([ic, big, lab], j) => {
    const x = 0.45 + j * 2.03;
    R(s, x, 4.65, 1.9, 1.9, { fill: GRAY_BG, radius: 0.06 });
    iconCircle(s, ic, x + 0.16, 4.8, 0.5);
    T(s, big, { x: x + 0.16, y: 5.38, w: 1.65, h: 0.55, fontSize: 22, bold: true, color: PURPLE, valign: "middle" });
    T(s, lab, { x: x + 0.16, y: 5.95, w: 1.68, h: 0.5, fontSize: 10, color: BODY });
  });
  const labels = runs.map((_, i) => `${i + 1}회`);
  s.addChart([
    { type: pres.charts.BAR, data: [{ name: "분석 시간(초)", labels, values: runs.map((r) => r.analysis_s) }], options: { chartColors: [PURPLE], barGapWidthPct: 60, showValue: false } },
    { type: pres.charts.LINE, data: [{ name: "목표 1분(60초)", labels, values: runs.map(() => 60) }], options: { chartColors: [RED], lineSize: 2, lineDataSymbol: "none", lineDash: "dash", showValue: false } },
  ], chartBase({ x: X(6.6), y: Y(1.6), w: Z(6.25), h: Z(4.95), showTitle: true, title: "10회 측정 (초) · 빨간 점선 = 목표 1분",
    showLegend: true, legendPos: "b", dataLabelFormatCode: "0.0", valAxisMinVal: 0, valAxisMaxVal: 70, valAxisMajorUnit: 10 }));
}

// ================================================================== 13. 비기능 ② 정확도·출처·장애 대비
{
  // 정확도: 웹 공개 사진 대체 평가(11/25, tests/vlm_eval_1125.json). 팀 촬영 평가셋이 아니므로 '조건부'. 모델 선택 시험(11/23)은 부록 A4
  const ev = D.eval;
  const accPct = Math.round((ev.correct / ev.n) * 1000) / 10, incPct = Math.round((ev.included / ev.n) * 1000) / 10;
  const llmPar = sum(runs, (r) => r.llm_paragraphs || 0), allPar = sum(runs, (r) => r.paragraphs || 0);
  const s = content("⑤ 테스트 · 비기능", `비기능 ② 정확도 ${accPct}%(웹 사진 대체 평가), 출처 ${Math.round((factsNoted / factsTotal) * 100)}%, LLM 작성 ${llmRuns.length}/${runs.length}회`,
    "확신 오답: 확신도 0.8 이상인데 틀린 답 → 사용자 확인 없이 잘못 확정되므로 0건이 목표",
    `[@] NFR-02 정확도는 명세서대로라면 팀이 찍은 사진으로 재야 해서, 이번에는 공개 사진 ${ev.n}곳으로 대신 측정했습니다. 정확도는 ${accPct}%로 목표 80%를 넘었고, 정답 장소는 모두 후보에 들었습니다. 다만 카페 거리 사진을 거리 안의 카페로 확정한 확신 오답이 ${ev.confident_wrong}건 있었습니다. 출처는 여행기 10회의 사실 문장 모두에 붙었고, 결함을 고친 뒤에는 10회 모두 LLM이 작성했습니다.`);
  const c1 = 0.45, c2 = 4.67, c3 = 8.89, cw = 3.99;
  // 정확도
  colHead(s, c1, cw, "target", "정확도 (NFR-02)");
  T(s, `${accPct}%`, { x: c1, y: 2.12, w: 2.1, h: 0.75, fontSize: 36, bold: true, color: PURPLE, valign: "middle" });
  T(s, `웹 사진 ${ev.n}곳 정확도 (목표 80%)`, { x: c1 + 2.0, y: 2.2, w: 2.0, h: 0.6, fontSize: 11, color: MUTED, valign: "middle" });
  tag(s, c1, 2.9, "팀 촬영 평가셋 아님 · 대체 평가", { fs: 9.5 });
  [["정확도", accPct, 80], ["후보 포함률", incPct, 90]].forEach(([lab, v, goal], i) => {
    const y = 3.42 + i * 0.8, bx = c1 + 1.2, bw = cw - 1.3;
    T(s, lab, { x: c1, y, w: 1.15, h: 0.36, fontSize: 11, bold: true, color: INK, valign: "middle" });
    R(s, bx, y + 0.06, bw, 0.24, { fill: "E4E5EA" });
    R(s, bx, y + 0.06, (bw * v) / 100, 0.24, { fill: PURPLE });
    line(s, bx + (bw * goal) / 100, y - 0.02, bx + (bw * goal) / 100, y + 0.38, { color: RED, w: 1.5, dash: "dash" });
    T(s, `${v}% · 목표 ${goal}%`, { x: bx, y: y + 0.36, w: bw, h: 0.26, fontSize: 9.5, color: BODY, valign: "middle" });
  });
  T(s, [{ text: "확신 오답  ", options: { color: MUTED } }, { text: `${ev.confident_wrong}건`, options: { bold: true, color: ORANGE } },
    { text: "  카페 거리 사진 → 거리 안 카페 (0.8)", options: { color: BODY } }], { x: c1, y: 5.12, w: cw, h: 0.3, fontSize: 10.5, valign: "middle" });
  T(s, `AI가 '없음'으로 답한 ${ev.statuses["선택필요"] || 0}곳은 사용자 선택으로 처리`, { x: c1, y: 5.45, w: cw, h: 0.3, fontSize: 10.5, color: BODY, valign: "middle" });
  T(s, "촬영 위치: 장소 좌표에서 임의 방향 0~100m", { x: c1, y: 6.0, w: cw, h: 0.34, fontSize: 10.5, color: MUTED, valign: "middle" });
  // 출처
  colHead(s, c2, cw, "quote", "출처 (NFR-03)");
  T(s, `${Math.round((factsNoted / factsTotal) * 100)}%`, { x: c2, y: 2.12, w: 2.1, h: 0.75, fontSize: 36, bold: true, color: PURPLE, valign: "middle" });
  T(s, "사실 문장 출처 표시 (목표 100%)", { x: c2 + 2.0, y: 2.2, w: 2.0, h: 0.6, fontSize: 11, color: MUTED, valign: "middle" });
  tag(s, c2, 2.9, "시스템 판정 기준 · 사람 전수 검토 미실시", { fs: 9.5 });
  T(s, "여행기 10회 작성 방식 (11/25)", { x: c2, y: 3.3, w: cw, h: 0.3, fontSize: 11, bold: true, color: INK });
  runs.forEach((r, k) => {
    const x = c2 + 0.12 + (k % 5) * 0.78, y = 3.65 + Math.floor(k / 5) * 0.8;
    icon(s, "file", x, y, 0.6, isTpl(r) || r.template_paragraphs ? "o" : "p");
  });
  [[PURPLE, `LLM 작성 ${llmRuns.length}회 (문단 ${llmPar}/${allPar})`], [ORANGE, `템플릿 대체 ${tplRuns.length}회 (D-04 수정 전 11/23: 9회)`]].forEach(([col, t], k) => {
    const y = 5.32 + k * 0.32;
    R(s, c2 + 0.12, y + 0.08, 0.2, 0.18, { fill: col, radius: 0.02 });
    T(s, t, { x: c2 + 0.42, y, w: cw - 0.42, h: 0.34, fontSize: 10.5, bold: true, color: col, valign: "middle" });
  });
  T(s, `사실 문장 ${factsNoted}개 모두 출처 각주`, { x: c2, y: 6.0, w: cw, h: 0.34, fontSize: 10.5, color: MUTED, valign: "middle" });
  // 장애 대비
  colHead(s, c3, cw, "shield", "장애 대비 (NFR-08)");
  [["plug", "외부 장소 API 장애"], ["bot", "LLM 응답 잘림 · 형식 오류"], ["repeat", "다시 쓰기가 같은 문단"], ["gauge", "동시 분석 요청 과다"]].forEach(([ic, t], i) => {
    const y = 2.2 + i * 0.92;
    R(s, c3, y, cw, 0.78, { fill: GRAY_BG, radius: 0.05 });
    iconCircle(s, ic, c3 + 0.14, y + 0.12, 0.54, { bg: PURPLE });
    T(s, t, { x: c3 + 0.82, y, w: 2.5, h: 0.78, fontSize: 12.5, bold: true, color: INK, valign: "middle" });
    icon(s, "check", c3 + cw - 0.6, y + 0.17, 0.44, "p");
  });
  T(s, "장애 상황을 자동 테스트로 재현해 확인", { x: c3, y: 6.0, w: cw, h: 0.34, fontSize: 10.5, color: MUTED, valign: "middle" });
}

// ================================================================== 14. 비기능 ③ 개인정보·보안·호환성
{
  const s = content("⑤ 테스트 · 비기능", "비기능 ③ 개인정보·보안·호환성: 남은 개인정보 0건, 보안 11항목 통과, 실기기 미실시",
    "개인정보 NFR-04 · 보안 NFR-07 · 호환성 NFR-06 · 사용성 NFR-05",
    "[@] NFR-04에 따라 분석 직후 서버를 조사했고, 원본 사진과 좌표, 썸네일의 위치 정보, 삭제 후 남은 데이터가 모두 0건이었습니다. NFR-07 보안은 외부 API 키가 아직 없는 상태에서 노출 0건이었고, 공개 주소로 11개 항목을 추가 점검해 모두 통과했습니다. 다만 실기기 테스트와 팀 외 5명 사용성 테스트는 아직 하지 못해 미실시로 표시했습니다.");
  const pv = nfr.privacy;
  const c1 = 0.45, c2 = 4.67, c3 = 8.89, cw = 3.99;
  colHead(s, c1, cw, "lock", "개인정보 (NFR-04)");
  [["imageoff", pv.originals_left, "남은 원본 사진"], ["mappinoff", pv.coords_left, "남은 위치 좌표"], ["image", pv.gps_in_thumbs, "썸네일 속 위치 정보"],
   ["trash", pv.after_delete_rows + pv.after_delete_thumbs, "여행 삭제 후 남은 데이터"]].forEach(([ic, v, lab], i) => {
    const y = 2.2 + i * 0.88;
    iconCircle(s, ic, c1 + 0.05, y + 0.1, 0.58, { bg: LAV, fg: "p" });
    T(s, String(v), { x: c1 + 0.8, y, w: 0.7, h: 0.78, fontSize: 30, bold: true, color: PURPLE, valign: "middle" });
    T(s, lab, { x: c1 + 1.5, y, w: 2.45, h: 0.78, fontSize: 12, color: INK, valign: "middle" });
  });
  T(s, "외부 AI 전송 없음\n인물 분석 안 함 (프롬프트 규칙으로 확인, 테스트 없음)", { x: c1, y: 5.8, w: cw, h: 0.5, fontSize: 10.5, color: MUTED, valign: "middle" });
  colHead(s, c2, cw, "shield", "보안 (NFR-07)");
  T(s, `${pass(sec)}/${sec.length}`, { x: c2, y: 2.12, w: 2.1, h: 0.75, fontSize: 36, bold: true, color: PURPLE, valign: "middle" });
  T(s, "공개 주소 보안 점검", { x: c2 + 2.0, y: 2.2, w: 2.0, h: 0.6, fontSize: 11, color: MUTED, valign: "middle" });
  tag(s, c2, 2.92, `API 키 노출 ${D.gitleaks.leaks}건 (키 미발급 상태)`, { fs: 9.5 });
  [["cloud", "Cloudflare", "HTTPS"], ["globe", "nginx", "요청 수 제한"], ["server", "FastAPI", "토큰·소유자 확인"], ["container", "컨테이너", "읽기 전용·망 분리"], ["trash", "데이터", "분석 후 삭제"]].forEach(([ic, n, d], i) => {
    const y = 3.38 + i * 0.56;
    R(s, c2, y, cw, 0.48, { fill: WHITE, line: BOX_LINE, radius: 0.05 });
    icon(s, ic, c2 + 0.12, y + 0.09, 0.3, "p");
    T(s, n, { x: c2 + 0.55, y, w: 1.35, h: 0.48, fontSize: 11.5, bold: true, color: PURPLE, valign: "middle" });
    T(s, d, { x: c2 + 1.9, y, w: 2.0, h: 0.48, fontSize: 10.5, color: BODY, valign: "middle" });
  });
  colHead(s, c3, cw, "smartphone", "호환성·사용성 (NFR-06·05)");
  [["laptop", "PC 화면 (Chromium)", true], ["smartphone", "모바일 360·390px 배치 (에뮬레이션)", true], ["smartphone", "iOS·Android 실기기", false], ["users", "팀 외 5명 사용성", false]].forEach(([ic, t, ok], i) => {
    const y = 2.2 + i * 0.92;
    R(s, c3, y, cw, 0.78, { fill: ok ? GRAY_BG : WHITE, line: ok ? undefined : "C9CBD2", dash: ok ? undefined : "dash", radius: 0.05 });
    iconCircle(s, ic, c3 + 0.14, y + 0.12, 0.54, { bg: ok ? PURPLE : "C9CBD2" });
    T(s, t, { x: c3 + 0.82, y, w: 2.2, h: 0.78, fontSize: 12.5, bold: true, color: ok ? INK : MUTED, valign: "middle" });
    if (ok) icon(s, "check", c3 + cw - 0.6, y + 0.17, 0.44, "p");
    else tag(s, c3 + cw - 0.95, y + 0.24, "미실시", { fs: 10, fill: GRAY_BG, color: MUTED });
  });
  tag(s, c3, 5.92, "NFR-06·05 미실시 (화면 배치만 확인)", { fs: 10 });
}

// ================================================================== 15. 결론
{
  section("결론");
  const s = content("⑥ 결론", "결론: 외부 비용 0원으로 공개 운영, 명세서 대비 남은 과제 정리", "성과 · 한계 · 향후 계획",
    `[@] 정리하면, 무료 터널과 서버의 AI로 비용 없이 서비스를 공개했고, 기능 테스트 ${tc.length}개를 통과했으며 결함 7건을 모두 고쳤습니다. 다만 명세서 기준으로는 조건이 붙은 항목이 남아 있습니다. 한계는 샘플 장소 데이터, 웹 사진으로 대신한 정확도 평가, 남은 실기기·사용성 테스트입니다. 앞으로 API 키 연동, 팀 사진 평가, 실기기·사용성 테스트를 진행하겠습니다. 감사합니다.`);
  const cols3 = [[0.45, "성과", PURPLE, LAV], [4.62, "한계", ORANGE, ORANGE_BG], [8.79, "향후 계획", INK, GRAY_BG]];
  cols3.forEach(([x, t, col, bg]) => {
    R(s, x, 1.6, 3.98, 4.45, { fill: bg, radius: 0.06 });
    T(s, t, { x: x + 0.22, y: 1.7, w: 3.5, h: 0.5, fontSize: 20, bold: true, color: col });
  });
  [["wallet", "0원", "외부 AI 비용"], ["lock", "0개", "외부에 열린 포트"], ["timer", `${nfr.phases.nfr01.analysis_avg}초`, "사진 20장 분석"],
   ["clipboard", `${pass(tc)}/${tc.length}`, "기능 테스트 통과"]].forEach(([ic, big, lab], k) => {
    const x = 0.63 + (k % 2) * 1.86, y = 2.35 + Math.floor(k / 2) * 1.8;
    R(s, x, y, 1.74, 1.64, { fill: WHITE, radius: 0.06 });
    icon(s, ic, x + 0.15, y + 0.15, 0.4, "p");
    T(s, big, { x: x + 0.15, y: y + 0.6, w: 1.5, h: 0.52, fontSize: 22, bold: true, color: PURPLE, valign: "middle" });
    T(s, lab, { x: x + 0.15, y: y + 1.12, w: 1.55, h: 0.42, fontSize: 9.5, color: BODY });
  });
  const rows = (x, ic, c, items) => items.forEach((t, k) => {
    const y = 2.4 + k * 0.88;
    icon(s, ic, x + 0.22, y + 0.08, 0.36, c);
    T(s, t, { x: x + 0.7, y, w: 3.1, h: 0.52, fontSize: 12.5, bold: true, color: INK, valign: "middle" });
  });
  rows(4.62, "alert", "o", ["샘플 장소 데이터 (API 키 미발급)", "정확도는 웹 사진 대체 평가", "확신 오답 1건 (경계값 0.8)", "실기기·사용성 테스트 미실시"]);
  rows(8.79, "arrow", "p", ["공공데이터 API 키 연동", "팀 촬영 사진으로 재측정", "자동 확정 기준 검토", "실기기·팀 외 5명 사용성 테스트"]);
  R(s, 0.45, 6.14, 12.4, 0.74, { fill: GRAY_BG, radius: 0.05 });
  T(s, [{ text: "AI 활용 명기  ", options: { bold: true, color: INK } },
    { text: TRACE.ai_note, options: { color: BODY, breakLine: true } }, { text: "서비스 안의 AI는 Qwen3.5 4B(Ollama)", options: { color: BODY } }],
    { x: 0.62, y: 6.14, w: 12.1, h: 0.74, fontSize: 10.5, valign: "middle" });
}

// ================================================================== 16. 감사합니다
{
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: "결론" });
  s.addText("감사합니다", { placeholder: "title" });
  s.addText("Q & A", { x: 2.17, y: 5.0, w: 15.67, h: 0.55, fontFace: FONT, fontSize: 24, color: MUTED, margin: 0, valign: "middle", isTextBox: true });
  s.addText("부록: A1 도메인 모델 · A2 상태 다이어그램 · A3 기능 테스트 케이스 전체 · A4 비기능 측정 상세 · A5 명세서 대비 결과 · A6 명세서와 다른 점 · A7 계획서·설계서 대비",
    { x: 2.17, y: 5.75, w: 15.67, h: 0.45, fontFace: FONT, fontSize: 16, color: MUTED, margin: 0, valign: "middle", isTextBox: true });
  s.addText(BYLINE, { x: 1.01, y: 9.49, w: 14, h: 0.49, fontFace: FONT, fontSize: 20, color: MUTED, margin: 0, valign: "middle", isTextBox: true });
  s.addNotes("질문을 받습니다. 세부 자료는 부록 슬라이드에 있습니다.");
}

// ================================================================== 부록
section("부록");
{
  const s = content("부록", "부록 A1. 도메인 모델 클래스 다이어그램",
    "backend/app/models.py 기준  |  합성 관계: 여행 하나에 방문지·사진·여행기·작업이 속하고, 여행을 지우면 함께 삭제됨 (명세서 7장 DR-01~09)",
    "models.py 기준 엔티티와 관계입니다. 여행 하나에 방문지, 사진, 여행기, 작업이 속하고(합성), 여행을 지우면 함께 삭제됩니다. 사진 좌표는 분석 후 삭제합니다.");
  const f = path.join(UMLDIR, "class_domain.png");
  const [W0, H0] = pngSize(f);
  const maxW = 16.9, maxH = 7.2, sc = Math.min(maxW / W0, maxH / H0), w = W0 * sc, h = H0 * sc;
  s.addImage({ path: f, x: (20 - w) / 2, y: 2.97, w, h, altText: "도메인 모델 클래스 다이어그램" });
}
{
  const s = content("부록", "부록 A2. 방문지 상태 다이어그램",
    "AI 확신도에 따라 '자동확정'·'확인필요'·'선택필요'로 나뉨 → 사용자가 확인하면 '확정' 또는 '기타장소'로 바뀜 (명세서 DR-02·FR-04)",
    "방문지 상태는 분석 결과의 확신도에 따라 자동확정, 확인필요, 선택필요로 나뉘고, 사용자가 확인하면 확정 또는 기타장소가 됩니다. 명세서 DR-02와 FR-04의 기준과 같습니다.");
  const f = path.join(UMLDIR, "state_visit.png");
  const [W0, H0] = pngSize(f);
  const w = 15.5, h = (w * H0) / W0;
  s.addImage({ path: f, x: (20 - w) / 2, y: 3.05, w, h, altText: "방문지 상태 다이어그램" });
  const notes = [["자동확정", "확신도 0.8 이상: 사용자에게 묻지 않음 (변경은 가능)"], ["확인필요", "확신도 0.5 이상 0.8 미만: AI 추천을 보여 주고 확인받음"], ["선택필요", "확신도 0.5 미만·후보 없음·AI 오류: 사용자가 후보 선택 또는 검색"], ["기타장소", "목록에 맞는 장소 없음: 방문지 중심 좌표로 저장"]];
  notes.forEach(([t, d], i) => {
    const x = 0.55 + i * 3.1;
    R(s, x, 5.7, 2.95, 1.0, { fill: LAV, radius: 0.05 });
    T(s, t, { x: x + 0.14, y: 5.78, w: 2.7, h: 0.3, fontSize: 12, bold: true, color: PURPLE });
    T(s, d, { x: x + 0.14, y: 6.1, w: 2.7, h: 0.55, fontSize: 9.5, color: BODY });
  });
}
function tcFullSlide(title, ids) {
  const s = content("부록", title, `실행 ${D.tc.run_at.replace("T", " ")} · 공개 주소  |  공통 사전조건: 서버 정상, 기기 토큰 발급  |  문구는 테스트 결과서 3.1과 같음`,
    "실제 공개 서버에서 실행한 기능 테스트 케이스 전체입니다. 공통 사전조건은 '서버 정상, 기기 토큰 발급'이고, 케이스별 조건을 따로 적었습니다. 관련 요구사항 칸은 요구사항 명세서의 요구사항, 유스케이스, 인수 기준 번호입니다.");
  const rows = ids.map((id) => {
    const r = tcById[id], t = TCT[id];
    const actual = id === "TC-13" ? `${t.actual}\n(1차 FAIL → D-01 수정 후 PASS)` : t.actual;
    return [id, reqCell(id), { text: r.kind.replace(" 흐름", ""), options: { align: "center" } }, t.pre, t.input, t.expected, actual, verdict(r.pass ? "PASS" : "FAIL")];
  });
  table(s, ["TC ID", "관련 요구사항", "흐름", "사전조건", "입력 · 절차", "예상 결과", "실제 결과", "판정"], rows,
    { x: 0.45, y: 1.6, w: 12.43, colW: [0.68, 1.3, 0.66, 1.5, 2.25, 2.3, 3.14, 0.6], fontSize: 10, rowH: 0.58, margin: [3, 5, 3, 5],
      headAlign: ["left", "center", "center", "left", "left", "left", "left", "center"] });
}
tcFullSlide("부록 A3. 기능 테스트 케이스 전체 (1/2)", ["TC-01", "TC-02", "TC-03", "TC-04", "TC-05", "TC-06", "TC-07", "TC-08"]);
tcFullSlide("부록 A3. 기능 테스트 케이스 전체 (2/2)", ["TC-09", "TC-10", "TC-11", "TC-12", "TC-13", "TC-14", "TC-15"]);
{
  const s = content("부록", "부록 A4. 비기능 측정 상세",
    "측정: 11/25 수정 배포 후 일회용 worker 컨테이너에서 API 직접 호출(nginx 요청 제한 제외)  |  사진 20장 세트(위치 없는 사진 1장 포함)",
    "11/25에 결함 수정을 배포한 뒤 일회용 worker 컨테이너에서 API를 직접 호출해 측정했습니다(nginx 요청 제한 제외). GPU와 컨테이너 자원은 측정하는 동안 nvidia-smi와 docker stats로 0.5~2초마다 기록했습니다. 작성 방식 열은 문단 기준으로 LLM이 쓴 회차와 템플릿으로 대체된 회차를 구분합니다. 11/23 측정에서는 10회 중 9회가 템플릿이었습니다.");
  const st = { blog: "블로그", diary: "일기", brief: "간결" };
  const rows = runs.map((r, i) => [`${i + 1}`, r.analysis_s.toFixed(2), `${r.visits}곳`, `${r.auto}곳`, r.story_s.toFixed(2), st[r.style],
    isTpl(r) ? { text: "템플릿", options: { color: ORANGE, bold: true } } : { text: "LLM", options: { color: PURPLE, bold: true } }, `${r.facts_with_note}/${r.facts}`]
    .map((t) => (typeof t === "object" ? Object.assign({}, t, { options: Object.assign({ align: "center" }, t.options) }) : { text: String(t), options: { align: "center" } })));
  rows.push(["평균", nfr.phases.nfr01.analysis_avg.toFixed(2), "", "", nfr.phases.nfr01.story_avg.toFixed(2), "", `LLM ${llmRuns.length} · 대체 ${tplRuns.length}`, `${factsNoted}/${factsTotal}`]
    .map((t) => ({ text: String(t), options: { align: "center", bold: true, color: INK } })));
  table(s, ["회차", "분석(초)", "방문지", "자동 확정", "여행기(초)", "문체", "작성 방식", "출처 있는 사실 문장"], rows,
    { x: 0.45, y: 1.6, w: 6.3, colW: [0.5, 0.78, 0.68, 0.78, 0.85, 0.6, 1.06, 1.05], fontSize: 9.5, rowH: 0.36, firstBold: false,
      headAlign: ["center", "center", "center", "center", "center", "center", "center", "center"] });
  table(s, ["동시 분석", "평균(초)", "최대(초)", "전체 완료(초)", "처리량"], conc.map((c) => [`${c.n}건`, c.avg_s.toFixed(2), c.max_s.toFixed(2), c.makespan_s.toFixed(1), `${c.photos_per_min}장/분`]
    .map((t, i) => ({ text: t, options: { align: i ? "center" : "left" } }))),
    { x: 7.0, y: 1.6, w: 5.85, colW: [1.1, 1.1, 1.1, 1.1, 1.45], fontSize: 10, rowH: 0.34, headAlign: ["left", "center", "center", "center", "center"] });
  table(s, ["API 부하 시험", "동시 접속", "초당 처리", "중간값(p50)", "95%(p95)", "오류"], loadr.map((r) => [r.path === "/trips" ? "여행 목록(DB 조회)" : "서버 정보(단순)", `${r.conc}`, `${r.rps}`, `${Math.round(r.p50_ms)}ms`, `${Math.round(r.p95_ms)}ms`, `${r.errors}`]
    .map((t, i) => ({ text: t, options: { align: i ? "center" : "left" } }))),
    { x: 7.0, y: 3.25, w: 5.85, colW: [1.45, 0.7, 0.9, 0.9, 1.0, 0.9], fontSize: 10, rowH: 0.31, headAlign: ["left", "center", "center", "center", "center", "center"] });
  T(s, `테스트 환경: ${D.env.os} · Ryzen 9 7950X3D · RTX 4080 SUPER 16GB · Python 3.12 FastAPI · PostgreSQL 17 · Redis 7.4 · ${D.env.ai}\n`
    + `보안·한도 세부(공개 주소): 요청 폭주 ${(sec.find((c) => c.item.startsWith("요청 폭주")).actual.match(/동시 (\d+)회/) || [])[1]}회 중 ${(sec.find((c) => c.item.startsWith("요청 폭주")).actual.match(/429 (\d+)회/) || [])[1]}회 제한(429) · 토큰 없음 거부(401) · 45MB 초과 차단(413) · GPU 작업 한도 초과 시 접수 거부(503·429) · 화면 1280×660·390×844`,
    { x: 0.45, y: 6.02, w: 6.3, h: 0.85, fontSize: 9, color: MUTED });
  const r1 = res.nfr01;
  T(s, `자원 사용량 (20장 10회 분석 구간): GPU 사용률 평균 ${r1.gpu_util_avg}%, 최대 ${r1.gpu_util_max}% · GPU 메모리 최대 ${(r1.vram_max_mib / 1024).toFixed(1)}GB · 전력 최대 ${Math.round(r1.power_max_w)}W\nAI 서버(Ollama) CPU 평균 ${(r1.vlm.cpu_avg / 100).toFixed(1)}코어 · 메모리 ${(r1.vlm.mem_max_mib / 1024).toFixed(1)}GB / API 서버 CPU 최대 ${Math.round(r1.api.cpu_max)}% · ${r1.api.mem_max_mib}MB / DB CPU 최대 ${Math.round(r1.postgres.cpu_max * 10) / 10}%\n정확도 대체 평가(11/25, 웹 사진 ${D.eval.n}곳): 정답 ${D.eval.correct} · 후보 포함 ${D.eval.included} · 확신 오답 ${D.eval.confident_wrong} · 자동확정 ${D.eval.auto}곳 중 정답 ${D.eval.auto_correct}\n모델 선택 시험(11/23): 정답 18건 중 2B ${bench['qwen3.5:2b'].rows.filter((r) => r.truth !== 'none' && r.ok).length} · 4B ${bench['qwen3.5:4b'].rows.filter((r) => r.truth !== 'none' && r.ok).length} · 9B ${bench['qwen3.5:9b'].rows.filter((r) => r.truth !== 'none' && r.ok).length} / GPU 메모리 ${bench['qwen3.5:2b'].vram_gb} · ${bench['qwen3.5:4b'].vram_gb} · ${bench['qwen3.5:9b'].vram_gb}GB`,
    { x: 7.0, y: 5.62, w: 5.85, h: 1.25, fontSize: 9.5, color: BODY });
}
{
  const s = content("부록", "부록 A5. 요구사항 명세서 대비 검증 결과 (추적표)",
    "요구사항 이름: 명세서 v1.0과 동일  |  인수 기준(AC) → 테스트  |  판정 뜻은 10쪽 (충족·조건부·부분·미실시), 차이는 A6",
    "요구사항 명세서 v1.0의 요구사항 20개를 인수 기준과 테스트에 연결한 표입니다. 결과서 5장과 같은 목록에서 만들었습니다. 결함 번호는 테스트 결과서의 결함 목록과 같습니다.");
  const deckRes = (q) => (q.id.startsWith("FR") ? q.result.replace("Pass", "PASS") : { 충족: "충족", 조건부: "조건부 충족", 부분: "부분", 미실시: "미실시" }[q.state]);
  const half = (arr, x) => table(s, ["요구사항 (명세서 v1.0)", "인수 기준 → 테스트", "결과"],
    arr.map((q) => [{ text: `${q.id} ${q.name}`, options: { bold: true, color: INK } }, `${q.ac} → ${q.tests}`, verdict(deckRes(q))]),
    { x, y: 1.6, w: 6.05, colW: [2.35, 2.7, 1.0], fontSize: 10, rowH: 0.4, firstBold: false, headAlign: ["left", "left", "center"] });
  half(REQS.slice(0, 12), 0.45);
  half(REQS.slice(12), 6.8);
}
const diffSlide = (title, rows) => {
  const s = content("부록", title,
    "명세서 v1.0과 다르게 구현·측정한 부분과, 명세서 기준 중 아직 확인하지 못한 부분  |  테스트 결과서 5.1과 같은 내용",
    "요구사항 명세서와 다르게 구현하거나 측정한 부분, 그리고 명세서 기준 중 아직 확인하지 못한 부분을 정리했습니다. 테스트 결과서 5.1과 같은 내용입니다.");
  table(s, ["요구사항", "명세서 v1.0", "실제 구현·테스트", "판단·조치"],
    rows.map((x) => [{ text: x.req, options: { bold: true, color: PURPLE } }, x.spec, x.actual, x.action]),
    { x: 0.45, y: 1.6, w: 12.43, colW: [2.0, 3.0, 4.48, 2.95], fontSize: 9.5, rowH: 0.42, firstBold: false, margin: [2, 5, 2, 5],
      headAlign: ["left", "left", "left", "left"] });
};
diffSlide("부록 A6. 요구사항 명세서와 다른 점 (1/2)", DIFFS.slice(0, 9));
diffSlide("부록 A6. 요구사항 명세서와 다른 점 (2/2)", DIFFS.slice(9));
{ // 중간 산출물 중 계획서·설계서 대비 (요구사항 명세서는 A5·A6)
  const s = content("부록", "부록 A7. 계획서·설계서 대비 확인",
    "중간 산출물(계획서·설계서 v1.0, 10/26)에 적은 일정·조건·구조와 실제 결과 비교  |  테스트 결과서 5.2와 같은 내용",
    "중간에 제출한 계획서와 설계서의 일정, 과제 조건, GitHub 협업, 성공 기준, 역할, 테스트 계획, 구조, 기술 구성을 실제 결과와 비교했습니다. 테스트 결과서 5.2와 같은 내용입니다.");
  const judge = (x) => ({ text: x.judge, options: { bold: true, align: "center", color: x.ok ? PURPLE : ORANGE } });
  table(s, ["항목", "계획서·설계서 v1.0", "실제", "판단"],
    TRACE.plan_design.map((x) => [{ text: x.item, options: { bold: true, color: INK } }, x.plan, x.actual.replace("(5.1)", "(A6)"), judge(x)]),
    { x: 0.45, y: 1.6, w: 12.43, colW: [2.2, 3.9, 4.35, 1.98], fontSize: 10, rowH: 0.52, firstBold: false, headAlign: ["left", "left", "left", "center"] });
}

pres.writeFile({ fileName: OUTFILE }).then(async (f) => {
  try {
    const { applyTheme } = require(process.env.APPLY_THEME);
    await applyTheme(f, { name: "찰칵부산 Team10", colors: { dk1: INK, lt1: WHITE, dk2: BODY, lt2: GRAY_BG, accent1: PURPLE, accent2: ORANGE,
      accent3: RED, accent4: "2E9E5B", accent5: MUTED, accent6: PURPLE_LIGHT, hlink: PURPLE, folHlink: "7A6FE8" } });
  } catch (e) { console.log("theme:", e.message); }
  console.log("written", f);
});
