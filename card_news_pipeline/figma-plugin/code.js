// 카드뉴스 임포트 플러그인
// 파이프라인 export JSON을 받아 승인 카피별로 5장(cover/P/D/A/CTA)의 카드 프레임을 생성한다.

figma.showUI(__html__, { width: 340, height: 420 });

function hexToRgb(hex) {
  const h = (hex || "#000000").replace("#", "");
  return {
    r: parseInt(h.substring(0, 2), 16) / 255,
    g: parseInt(h.substring(2, 4), 16) / 255,
    b: parseInt(h.substring(4, 6), 16) / 255,
  };
}

function solid(hex) {
  return [{ type: "SOLID", color: hexToRgb(hex) }];
}

async function makeText(text, opts) {
  const t = figma.createText();
  t.fontName = { family: "Inter", style: opts.bold ? "Bold" : "Regular" };
  t.characters = text || "";
  t.fontSize = opts.size;
  t.fills = solid(opts.color);
  t.textAutoResize = "HEIGHT";
  t.resize(opts.width, t.height);
  t.x = opts.x;
  t.y = opts.y;
  return t;
}

async function buildCard(card, brand, kicker, headline, opts) {
  const W = brand.cardWidth || 1080;
  const H = brand.cardHeight || 1350;
  const frame = figma.createFrame();
  frame.resize(W, H);
  frame.name = card.topic_id + " · " + card.angle_name + " · " + opts.label;
  frame.fills = solid(opts.bg);
  frame.cornerRadius = 0;

  const pad = 88;
  const inkColor = opts.onDark ? "#ffffff" : brand.ink || "#0f172a";

  const brandName = await makeText(brand.name, {
    size: 30, color: opts.onDark ? "#ffffff" : brand.primary,
    bold: true, width: W - pad * 2, x: pad, y: 90,
  });
  frame.appendChild(brandName);

  if (kicker) {
    const k = await makeText(kicker, {
      size: 34, color: opts.onDark ? "#ffffff" : brand.primary,
      bold: false, width: W - pad * 2, x: pad, y: H / 2 - 220,
    });
    frame.appendChild(k);
  }

  const head = await makeText(headline, {
    size: opts.headSize || 64, color: opts.onDark ? "#ffffff" : inkColor,
    bold: true, width: W - pad * 2, x: pad, y: H / 2 - 150,
  });
  frame.appendChild(head);

  return frame;
}

async function run(payload) {
  await figma.loadFontAsync({ family: "Inter", style: "Regular" });
  await figma.loadFontAsync({ family: "Inter", style: "Bold" });

  const brand = payload.brand || { name: "BRAND", primary: "#2563eb", secondary: "#1d4ed8", ink: "#0f172a", cardWidth: 1080, cardHeight: 1350 };
  const cards = payload.cards || [];
  const gap = 80;
  const W = brand.cardWidth || 1080;

  let created = 0;
  let originX = figma.viewport.center.x;
  let originY = figma.viewport.center.y;

  for (let i = 0; i < cards.length; i++) {
    const c = cards[i];
    const steps = [
      { label: "cover", kicker: c.angle_name, head: c.hook, bg: brand.primary, onDark: true, headSize: 72 },
      { label: "P", kicker: "이런 고민, 있으셨죠?", head: c.problem, bg: "#ffffff", onDark: false },
      { label: "D", kicker: "이렇게 달라질 수 있어요", head: c.desire, bg: "#ffffff", onDark: false },
      { label: "A", kicker: "지금 이렇게 해보세요", head: c.action, bg: "#ffffff", onDark: false },
      { label: "CTA", kicker: "", head: c.cta, bg: brand.secondary, onDark: true, headSize: 60 },
    ];
    const group = [];
    for (let j = 0; j < steps.length; j++) {
      const s = steps[j];
      const frame = await buildCard(c, brand, s.kicker, s.head, s);
      frame.x = originX + j * (W + gap);
      frame.y = originY + i * (brand.cardHeight + gap);
      group.push(frame);
      created++;
    }
  }

  figma.ui.postMessage({ type: "done", text: "완료: " + created + "장 카드 생성 (" + cards.length + "개 카피)" });
  figma.notify("카드뉴스 " + created + "장 생성 완료");
}

figma.ui.onmessage = async (msg) => {
  if (msg.type === "create") {
    try {
      await run(msg.data);
    } catch (e) {
      figma.ui.postMessage({ type: "done", text: "오류: " + e.message });
    }
  } else if (msg.type === "cancel") {
    figma.closePlugin();
  }
};
