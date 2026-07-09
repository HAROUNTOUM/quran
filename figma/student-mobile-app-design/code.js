const W = 390;
const H = 844;
const GAP = 72;

const C = {
  bg: "#F7FAF8",
  surface: "#FFFFFF",
  text: "#17231E",
  muted: "#66736D",
  line: "#E2E8E4",
  primary: "#059669",
  primaryDark: "#047857",
  primarySoft: "#E7F7EF",
  amber: "#D97706",
  amberSoft: "#FFF7E6",
  blue: "#2563EB",
  blueSoft: "#EAF1FF",
  red: "#DC2626",
  redSoft: "#FEECEC",
  purple: "#7C3AED",
  purpleSoft: "#F1EAFF",
  slateSoft: "#F1F5F9"
};

let fontRegular = { family: "Inter", style: "Regular" };
let fontMedium = { family: "Inter", style: "Medium" };
let fontBold = { family: "Inter", style: "Bold" };

async function chooseFonts() {
  const available = await figma.listAvailableFontsAsync();
  const preferred = [
    "Tajawal",
    "Noto Sans Arabic",
    "IBM Plex Sans Arabic",
    "Arial",
    "Inter"
  ];
  const family = preferred.find((name) => available.some((font) => font.fontName.family === name)) || "Inter";
  const styles = available
    .filter((font) => font.fontName.family === family)
    .map((font) => font.fontName.style);

  const pick = (candidates) => candidates.find((style) => styles.includes(style)) || styles[0] || "Regular";
  fontRegular = { family, style: pick(["Regular", "Normal"]) };
  fontMedium = { family, style: pick(["Medium", "SemiBold", "Regular", "Normal"]) };
  fontBold = { family, style: pick(["Bold", "SemiBold", "Medium", "Regular", "Normal"]) };

  await figma.loadFontAsync(fontRegular);
  await figma.loadFontAsync(fontMedium);
  await figma.loadFontAsync(fontBold);
}

function paint(hex) {
  const value = hex.replace("#", "");
  return {
    type: "SOLID",
    color: {
      r: parseInt(value.slice(0, 2), 16) / 255,
      g: parseInt(value.slice(2, 4), 16) / 255,
      b: parseInt(value.slice(4, 6), 16) / 255
    }
  };
}

function setBox(node, x, y, w, h, color = C.surface, radius = 18) {
  node.x = x;
  node.y = y;
  node.resize(w, h);
  node.fills = [paint(color)];
  node.cornerRadius = radius;
}

function addRect(parent, x, y, w, h, color = C.surface, radius = 18, stroke = null) {
  const node = figma.createRectangle();
  setBox(node, x, y, w, h, color, radius);
  if (stroke) {
    node.strokes = [paint(stroke)];
    node.strokeWeight = 1;
  }
  parent.appendChild(node);
  return node;
}

function addCircle(parent, x, y, size, color) {
  const node = figma.createEllipse();
  node.x = x;
  node.y = y;
  node.resize(size, size);
  node.fills = [paint(color)];
  parent.appendChild(node);
  return node;
}

function addLine(parent, x, y, w, color = C.line) {
  const node = figma.createLine();
  node.x = x;
  node.y = y;
  node.resize(w, 0);
  node.strokes = [paint(color)];
  node.strokeWeight = 1;
  parent.appendChild(node);
  return node;
}

function addText(parent, text, x, y, w, opts = {}) {
  const node = figma.createText();
  node.fontName = opts.weight === "bold" ? fontBold : opts.weight === "medium" ? fontMedium : fontRegular;
  node.characters = text;
  node.x = x;
  node.y = y;
  node.resize(w, opts.h || 40);
  node.fontSize = opts.size || 14;
  node.lineHeight = { value: opts.lineHeight || Math.round((opts.size || 14) * 1.35), unit: "PIXELS" };
  node.fills = [paint(opts.color || C.text)];
  node.textAlignHorizontal = opts.align || "RIGHT";
  node.textAlignVertical = opts.valign || "TOP";
  return parent.appendChild(node);
}

function makeFrame(name, index) {
  const frame = figma.createFrame();
  frame.name = name;
  frame.x = index * (W + GAP);
  frame.y = 0;
  frame.resize(W, H);
  frame.fills = [paint(C.bg)];
  frame.clipsContent = true;
  frame.cornerRadius = 32;
  return frame;
}

function statusBar(frame, light = false) {
  addText(frame, "9:41", 24, 16, 52, { size: 13, weight: "bold", color: light ? C.surface : C.text, align: "LEFT", h: 18 });
  addRect(frame, 300, 21, 18, 10, light ? C.surface : C.text, 2);
  addRect(frame, 324, 18, 24, 14, "FFFFFF", 4, light ? C.surface : C.text);
  addRect(frame, 351, 22, 3, 6, light ? C.surface : C.text, 1);
}

function appHeader(frame, title, subtitle) {
  statusBar(frame);
  addCircle(frame, 26, 56, 42, C.surface);
  addText(frame, "🔔", 33, 65, 26, { size: 16, align: "CENTER", h: 24 });
  addCircle(frame, 336, 56, 42, C.primarySoft);
  addText(frame, "س", 346, 65, 22, { size: 17, weight: "bold", color: C.primary, align: "CENTER", h: 24 });
  addText(frame, title, 96, 56, 218, { size: 20, weight: "bold", h: 28 });
  addText(frame, subtitle, 96, 84, 218, { size: 12, color: C.muted, h: 20 });
}

function bottomNav(frame, active) {
  addRect(frame, 20, 756, 350, 68, C.surface, 24, C.line);
  const items = [
    ["الرئيسية", "⌂", "home"],
    ["الحفظ", "◴", "memorization"],
    ["الحصص", "▣", "sessions"],
    ["الطلبات", "✉", "requests"]
  ];
  items.forEach((item, i) => {
    const x = 35 + i * 84;
    const isActive = active === item[2];
    if (isActive) addRect(frame, x - 4, 768, 64, 44, C.primarySoft, 16);
    addText(frame, item[1], x + 18, 772, 24, { size: 17, color: isActive ? C.primary : C.muted, align: "CENTER", h: 18 });
    addText(frame, item[0], x - 8, 794, 64, { size: 10, weight: isActive ? "bold" : "medium", color: isActive ? C.primary : C.muted, align: "CENTER", h: 16 });
  });
}

function metricCard(frame, x, y, w, label, value, color, soft) {
  addRect(frame, x, y, w, 92, C.surface, 20, C.line);
  addCircle(frame, x + w - 48, y + 18, 30, soft);
  addText(frame, value, x + 16, y + 24, w - 76, { size: 24, weight: "bold", color, h: 32 });
  addText(frame, label, x + 16, y + 58, w - 32, { size: 11, color: C.muted, h: 16 });
}

function progressRing(frame, x, y, size, pct, color) {
  addCircle(frame, x, y, size, C.primarySoft);
  addCircle(frame, x + 12, y + 12, size - 24, C.surface);
  const arc = figma.createArc();
  arc.x = x;
  arc.y = y;
  arc.resize(size, size);
  arc.arcData = { startingAngle: -Math.PI / 2, endingAngle: -Math.PI / 2 + Math.PI * 2 * pct, innerRadius: 0.72 };
  arc.fills = [paint(color)];
  frame.appendChild(arc);
}

function pill(frame, text, x, y, w, color, soft) {
  addRect(frame, x, y, w, 30, soft, 15);
  addText(frame, text, x + 10, y + 7, w - 20, { size: 11, weight: "bold", color, align: "CENTER", h: 16 });
}

function screenSplash(index) {
  const f = makeFrame("01 Splash + Student Welcome", index);
  addRect(f, 0, 0, W, H, C.primaryDark, 0);
  statusBar(f, true);
  addCircle(f, 131, 130, 128, "#0FBF83");
  addCircle(f, 151, 150, 88, C.surface);
  addText(f, "ط", 172, 166, 48, { size: 44, weight: "bold", color: C.primary, align: "CENTER", h: 58 });
  addText(f, "الطبيب الحافظ", 54, 306, 282, { size: 32, weight: "bold", color: C.surface, align: "CENTER", h: 44 });
  addText(f, "تطبيق الطالب لمتابعة الحفظ، الحضور، الحصص والطلبات اليومية.", 45, 362, 300, {
    size: 15,
    color: "#D7F7E8",
    align: "CENTER",
    h: 66,
    lineHeight: 24
  });
  addRect(f, 34, 506, 322, 78, "#0B7B5E", 24);
  addText(f, "الحصة القادمة", 218, 524, 110, { size: 12, color: "#BDEFD9", h: 18 });
  addText(f, "حلقة الإتقان - 20:30", 74, 548, 254, { size: 18, weight: "bold", color: C.surface, h: 28 });
  addRect(f, 34, 688, 322, 54, C.surface, 18);
  addText(f, "ابدأ المتابعة", 64, 705, 262, { size: 16, weight: "bold", color: C.primary, align: "CENTER", h: 24 });
  addText(f, "تسجيل الدخول", 64, 764, 262, { size: 14, weight: "medium", color: "#D7F7E8", align: "CENTER", h: 24 });
  return f;
}

function screenHome(index) {
  const f = makeFrame("02 Home Dashboard", index);
  appHeader(f, "السلام عليكم، سارة", "أكملي ورد اليوم قبل حصة المساء");

  addRect(f, 20, 126, 350, 146, C.primary, 28);
  addText(f, "تقدم الحفظ", 240, 150, 92, { size: 13, weight: "medium", color: "#D7F7E8", h: 20 });
  addText(f, "86 ربع", 210, 175, 122, { size: 31, weight: "bold", color: C.surface, h: 40 });
  addText(f, "من أصل 240 ربع", 210, 216, 122, { size: 12, color: "#D7F7E8", h: 18 });
  progressRing(f, 48, 148, 92, 0.36, C.surface);
  addText(f, "36%", 68, 178, 52, { size: 18, weight: "bold", color: C.surface, align: "CENTER", h: 28 });

  metricCard(f, 20, 292, 165, "نسبة الحضور", "94%", C.blue, C.blueSoft);
  metricCard(f, 205, 292, 165, "مهام معلقة", "3", C.amber, C.amberSoft);

  addText(f, "إجراءات سريعة", 218, 414, 132, { size: 17, weight: "bold", h: 24 });
  const quick = [
    ["دخول الحصة", C.primary, C.primarySoft],
    ["طلب مراجعة", C.purple, C.purpleSoft],
    ["تسجيل عذر", C.amber, C.amberSoft],
    ["نتائج الامتحان", C.blue, C.blueSoft]
  ];
  quick.forEach((item, i) => {
    const x = 20 + (i % 2) * 180;
    const y = 452 + Math.floor(i / 2) * 74;
    addRect(f, x, y, 165, 58, C.surface, 18, C.line);
    addCircle(f, x + 120, y + 14, 30, item[2]);
    addText(f, item[0], x + 18, y + 20, 92, { size: 12, weight: "bold", color: item[1], h: 18 });
  });

  addText(f, "الحصة القادمة", 226, 614, 124, { size: 17, weight: "bold", h: 24 });
  addRect(f, 20, 650, 350, 78, C.surface, 22, C.line);
  addCircle(f, 320, 672, 34, C.blueSoft);
  addText(f, "حلقة الإتقان", 190, 668, 110, { size: 14, weight: "bold", h: 20 });
  addText(f, "اليوم 20:30 • أونلاين", 122, 694, 178, { size: 12, color: C.muted, h: 18 });
  pill(f, "دخول", 38, 674, 72, C.primary, C.primarySoft);
  bottomNav(f, "home");
  return f;
}

function screenMemorization(index) {
  const f = makeFrame("03 Memorization Progress", index);
  appHeader(f, "تقدم الحفظ", "مراجعة وردك وخطة الأسبوع");

  addRect(f, 20, 124, 350, 180, C.surface, 28, C.line);
  progressRing(f, 132, 148, 126, 0.36, C.primary);
  addText(f, "36%", 162, 188, 66, { size: 26, weight: "bold", color: C.primary, align: "CENTER", h: 34 });
  addText(f, "86 / 240 ربع محفوظ", 64, 268, 262, { size: 15, weight: "bold", align: "CENTER", h: 22 });

  addText(f, "خطة اليوم", 254, 334, 96, { size: 17, weight: "bold", h: 24 });
  addRect(f, 20, 370, 350, 96, C.surface, 22, C.line);
  addCircle(f, 316, 394, 38, C.primarySoft);
  addText(f, "الحفظ", 246, 388, 56, { size: 12, color: C.muted, h: 18 });
  addText(f, "سورة الملك 1-12", 126, 412, 176, { size: 15, weight: "bold", h: 22 });
  pill(f, "قيد التنفيذ", 36, 402, 88, C.primary, C.primarySoft);

  addRect(f, 20, 482, 350, 96, C.surface, 22, C.line);
  addCircle(f, 316, 506, 38, C.amberSoft);
  addText(f, "المراجعة", 232, 500, 70, { size: 12, color: C.muted, h: 18 });
  addText(f, "جزء عم - 20 آية", 126, 524, 176, { size: 15, weight: "bold", h: 22 });
  pill(f, "مطلوبة", 36, 514, 88, C.amber, C.amberSoft);

  addText(f, "إنجاز الأسبوع", 244, 614, 106, { size: 17, weight: "bold", h: 24 });
  [0.4, 0.7, 0.5, 0.85, 0.65, 0.3, 0.75].forEach((pct, i) => {
    const x = 36 + i * 45;
    addRect(f, x, 706 - pct * 82, 22, pct * 82, i === 3 ? C.primary : "#A7F3D0", 8);
    addText(f, ["س", "ح", "ن", "ث", "ر", "خ", "ج"][i], x - 3, 716, 28, { size: 10, color: C.muted, align: "CENTER", h: 14 });
  });
  bottomNav(f, "memorization");
  return f;
}

function screenSession(index) {
  const f = makeFrame("04 Live Session", index);
  appHeader(f, "الحصة المباشرة", "حلقة الإتقان مع الأستاذ أحمد");

  addRect(f, 20, 124, 350, 176, "#12392E", 28);
  addCircle(f, 151, 162, 88, "#1E6A54");
  addText(f, "أ", 173, 180, 44, { size: 36, weight: "bold", color: C.surface, align: "CENTER", h: 48 });
  addText(f, "الأستاذ أحمد", 100, 252, 190, { size: 18, weight: "bold", color: C.surface, align: "CENTER", h: 24 });
  pill(f, "مباشر الآن", 134, 276, 122, C.surface, "#0F8F6B");

  addText(f, "دور التسميع", 250, 332, 100, { size: 17, weight: "bold", h: 24 });
  addRect(f, 20, 368, 350, 110, C.surface, 22, C.line);
  addCircle(f, 300, 394, 48, C.primarySoft);
  addText(f, "2", 314, 405, 20, { size: 22, weight: "bold", color: C.primary, align: "CENTER", h: 28 });
  addText(f, "أنت التالي بعد محمد", 92, 394, 190, { size: 17, weight: "bold", h: 24 });
  addText(f, "جهزي المقطع: الملك 1-12", 92, 424, 190, { size: 12, color: C.muted, h: 18 });

  addText(f, "قائمة الطلاب", 250, 512, 100, { size: 17, weight: "bold", h: 24 });
  ["محمد بن علي", "سارة أحمد", "مريم نور"].forEach((name, i) => {
    const y = 548 + i * 58;
    addRect(f, 20, y, 350, 46, C.surface, 16, C.line);
    addCircle(f, 320, y + 10, 26, i === 1 ? C.primarySoft : C.slateSoft);
    addText(f, name.slice(0, 1), 328, y + 15, 10, { size: 11, weight: "bold", color: i === 1 ? C.primary : C.muted, align: "CENTER", h: 14 });
    addText(f, name, 148, y + 14, 154, { size: 13, weight: "medium", h: 18 });
    pill(f, i === 0 ? "يقرأ" : i === 1 ? "التالي" : "بانتظار", 38, y + 8, 78, i === 0 ? C.blue : i === 1 ? C.primary : C.muted, i === 0 ? C.blueSoft : i === 1 ? C.primarySoft : C.slateSoft);
  });

  addRect(f, 20, 706, 350, 50, C.primary, 18);
  addText(f, "الدخول إلى القاعة", 72, 720, 246, { size: 16, weight: "bold", color: C.surface, align: "CENTER", h: 24 });
  bottomNav(f, "sessions");
  return f;
}

function screenAttendance(index) {
  const f = makeFrame("05 Attendance", index);
  appHeader(f, "الحضور", "سجل الحضور والغياب");

  metricCard(f, 20, 124, 165, "هذا الشهر", "12/13", C.primary, C.primarySoft);
  metricCard(f, 205, 124, 165, "النسبة", "94%", C.blue, C.blueSoft);

  addRect(f, 20, 244, 350, 94, C.surface, 22, C.line);
  addText(f, "غياب يحتاج إلى تبرير", 174, 266, 160, { size: 15, weight: "bold", color: C.red, h: 22 });
  addText(f, "حصة 29 يونيو • حلقة الإتقان", 90, 292, 244, { size: 12, color: C.muted, h: 18 });
  pill(f, "إرسال عذر", 36, 276, 96, C.red, C.redSoft);

  addText(f, "آخر الجلسات", 250, 374, 100, { size: 17, weight: "bold", h: 24 });
  const rows = [
    ["اليوم", "حاضر", C.primary, C.primarySoft],
    ["الخميس", "متأخر", C.amber, C.amberSoft],
    ["الثلاثاء", "حاضر", C.primary, C.primarySoft],
    ["الأحد", "غياب", C.red, C.redSoft],
    ["الجمعة", "حاضر", C.primary, C.primarySoft]
  ];
  rows.forEach((row, i) => {
    const y = 416 + i * 58;
    addRect(f, 20, y, 350, 46, C.surface, 16, C.line);
    addText(f, row[0], 244, y + 14, 90, { size: 13, weight: "medium", h: 18 });
    addText(f, "حلقة الإتقان", 130, y + 14, 98, { size: 12, color: C.muted, h: 18 });
    pill(f, row[1], 38, y + 8, 76, row[2], row[3]);
  });
  bottomNav(f, "home");
  return f;
}

function screenRequests(index) {
  const f = makeFrame("06 Notifications + Requests", index);
  appHeader(f, "الإشعارات والطلبات", "تابعي الردود والتنبيهات المهمة");

  addText(f, "تنبيهات جديدة", 246, 124, 104, { size: 17, weight: "bold", h: 24 });
  const alerts = [
    ["تم اعتماد طلب المراجعة", "يمكنك اختيار موعد التسميع.", C.primary, C.primarySoft],
    ["تذكير بالحصة", "حلقة الإتقان تبدأ بعد ساعتين.", C.blue, C.blueSoft],
    ["نتيجة امتحان", "درجتك في جزء عم: ممتاز.", C.purple, C.purpleSoft]
  ];
  alerts.forEach((alert, i) => {
    const y = 160 + i * 80;
    addRect(f, 20, y, 350, 64, C.surface, 18, C.line);
    addCircle(f, 316, y + 17, 30, alert[3]);
    addText(f, alert[0], 126, y + 14, 174, { size: 13, weight: "bold", color: alert[2], h: 18 });
    addText(f, alert[1], 76, y + 38, 224, { size: 11, color: C.muted, h: 16 });
  });

  addText(f, "طلب جديد", 270, 430, 80, { size: 17, weight: "bold", h: 24 });
  addRect(f, 20, 466, 350, 174, C.surface, 22, C.line);
  addText(f, "نوع الطلب", 278, 492, 56, { size: 12, color: C.muted, h: 18 });
  pill(f, "مراجعة", 190, 486, 74, C.primary, C.primarySoft);
  pill(f, "استفسار", 106, 486, 74, C.muted, C.slateSoft);
  addLine(f, 42, 534, 306);
  addText(f, "الموضوع", 278, 556, 56, { size: 12, color: C.muted, h: 18 });
  addRect(f, 42, 584, 306, 38, C.bg, 14, C.line);
  addText(f, "طلب مراجعة سورة الملك", 64, 594, 250, { size: 12, color: C.text, h: 18 });

  addRect(f, 20, 674, 350, 50, C.primary, 18);
  addText(f, "إرسال الطلب", 72, 688, 246, { size: 16, weight: "bold", color: C.surface, align: "CENTER", h: 24 });
  bottomNav(f, "requests");
  return f;
}

function createStylesPage(index) {
  const f = makeFrame("00 Design Tokens", index);
  f.resize(390, 520);
  addText(f, "Student Mobile App - Tokens", 28, 32, 330, { size: 22, weight: "bold", align: "LEFT", h: 32 });
  addText(f, "RTL Arabic mobile design for the Quran memorization student experience.", 28, 72, 330, {
    size: 12,
    color: C.muted,
    align: "LEFT",
    h: 44,
    lineHeight: 20
  });
  Object.entries(C).forEach(([name, value], i) => {
    const x = 28 + (i % 2) * 170;
    const y = 138 + Math.floor(i / 2) * 58;
    addRect(f, x, y, 38, 38, value, 10, C.line);
    addText(f, name, x + 48, y + 3, 96, { size: 11, weight: "bold", align: "LEFT", h: 16 });
    addText(f, value, x + 48, y + 20, 96, { size: 10, color: C.muted, align: "LEFT", h: 14 });
  });
  return f;
}

async function main() {
  await chooseFonts();

  const nodes = [
    createStylesPage(0),
    screenSplash(1),
    screenHome(2),
    screenMemorization(3),
    screenSession(4),
    screenAttendance(5),
    screenRequests(6)
  ];

  figma.currentPage.selection = nodes;
  figma.viewport.scrollAndZoomIntoView(nodes);
  figma.closePlugin("Created editable student mobile app frames.");
}

main().catch((error) => {
  figma.closePlugin(`Failed to create design: ${error.message}`);
});
