// 발표 자료용 아이콘 PNG 만들기 (Lucide 아이콘, react-icons). build_deck.js는 여기서 만든 PNG만 읽는다.
// 사용: NODE_PATH=<react-icons·react·react-dom·sharp가 있는 node_modules> node make_icons.js
//      (설치 예: npm install react-icons@5.4.0 react@18.3.1 react-dom@18.3.1 sharp@0.33.5)
const fs = require("fs");
const path = require("path");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const lu = require("react-icons/lu");
const sharp = require("sharp");

const OUT = path.join(__dirname, "img", "icons");
const ICONS = {
  upload: "LuImageUp", scan: "LuScanSearch", usercheck: "LuUserCheck", route: "LuRoute", map: "LuMap", book: "LuBookOpen",
  share: "LuShare2", trash: "LuTrash2", server: "LuServer", monitor: "LuMonitorSmartphone", laptop: "LuLaptop", smartphone: "LuSmartphone",
  clipboard: "LuClipboardCheck", flag: "LuFlag", users: "LuUsers", cloud: "LuCloud", shield: "LuShieldCheck", lock: "LuLock",
  database: "LuDatabase", cpu: "LuCpu", layers: "LuLayers", cog: "LuCog", image: "LuImage", wallet: "LuWallet",
  check: "LuCircleCheck", alert: "LuTriangleAlert", minus: "LuCircleMinus", timer: "LuTimer", gauge: "LuGauge", quote: "LuQuote",
  file: "LuFileText", bug: "LuBug", target: "LuTarget", repeat: "LuRefreshCw", key: "LuKeyRound", plug: "LuPlug",
  imageoff: "LuImageOff", mappinoff: "LuMapPinOff", ban: "LuBan", globe: "LuGlobe", rocket: "LuRocket", wrench: "LuWrench",
  bot: "LuBot", list: "LuListOrdered", network: "LuNetwork", arrow: "LuArrowRight", search: "LuSearchCheck", badge: "LuBadgeCheck",
  container: "LuContainer", calendar: "LuCalendarDays", hourglass: "LuHourglass",
};
const COLORS = { p: "#5B4BE0", w: "#FFFFFF", o: "#D9902C", g: "#8A8F98", r: "#D94848" };

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  for (const [name, comp] of Object.entries(ICONS)) {
    if (!lu[comp]) throw new Error("아이콘 없음: " + comp);
    for (const [k, c] of Object.entries(COLORS)) {
      let svg = renderToStaticMarkup(React.createElement(lu[comp], { size: 256 }));
      svg = svg.replace(/currentColor/g, c).replace(/stroke-width="2"/g, 'stroke-width="2.3"');
      if (!svg.includes("xmlns=")) svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
      await sharp(Buffer.from(svg), { density: 300 }).resize(256, 256).png().toFile(path.join(OUT, `${name}-${k}.png`));
    }
  }
  console.log("icons", Object.keys(ICONS).length, "x", Object.keys(COLORS).length, "→", OUT);
})();
