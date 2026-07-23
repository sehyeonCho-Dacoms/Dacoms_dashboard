// 카드뉴스 자동 생성 플러그인
// 로컬 서버(http://localhost:8765/import.json)에서 카드 데이터를 받아
// 마스터 프레임(마스터_썸네일/마스터_본문_1/마스터_본문_2/마스터_CTA)을
// 이름으로 찾아 복제하고, DFS 순서의 텍스트 레이어를 채운 뒤
// 배경 이미지를 적용해 카드 5장을 나란히 배치한다.
//
// ⚠️ 이 파일은 가이드북에서 "건드리면 안 되는 파일"로 지정된 핵심 코드입니다.

const SERVER = "http://localhost:8765";
const GAP = 80;

function base64ToUint8Array(base64) {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let str = base64.replace(/[^A-Za-z0-9+/=]/g, "");
  const bytes = [];
  let buffer = 0, bits = 0;
  for (let i = 0; i < str.length; i++) {
    const c = str[i];
    if (c === "=") break;
    const val = chars.indexOf(c);
    if (val === -1) continue;
    buffer = (buffer << 6) | val;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((buffer >> bits) & 0xff);
    }
  }
  return new Uint8Array(bytes);
}

async function loadFontsForNode(node) {
  if (node.fontName === figma.mixed) {
    const seen = new Set();
    for (let i = 0; i < node.characters.length; i++) {
      const f = node.getRangeFontName(i, i + 1);
      const key = f.family + "::" + f.style;
      if (!seen.has(key)) {
        seen.add(key);
        await figma.loadFontAsync(f);
      }
    }
  } else {
    await figma.loadFontAsync(node.fontName);
  }
}

async function fillTextLayers(frame, texts) {
  // findAll은 레이어 트리를 위에서 아래(DFS) 순서로 순회한다.
  const textNodes = frame.findAll((n) => n.type === "TEXT");
  for (let i = 0; i < texts.length && i < textNodes.length; i++) {
    const node = textNodes[i];
    await loadFontsForNode(node);
    node.characters = texts[i];
  }
}

function findBackgroundNode(frame) {
  // 이름이 "배경"인 자식 노드를 우선 사용하고, 없으면 프레임 자체에 적용한다.
  const named = frame.findOne((n) => n.name === "배경");
  return named || frame;
}

async function applyBackgroundImage(frame, base64Data) {
  const bytes = base64ToUint8Array(base64Data);
  const image = figma.createImage(bytes);
  const target = findBackgroundNode(frame);
  target.fills = [{ type: "IMAGE", imageHash: image.hash, scaleMode: "FILL" }];
}

function findMasterFrame(frameName) {
  const masterName = "마스터_" + frameName;
  const node = figma.currentPage.findOne(
    (n) => n.type === "FRAME" && n.name === masterName
  );
  if (!node) {
    throw new Error(`마스터 프레임을 찾을 수 없습니다: "${masterName}"`);
  }
  return node;
}

async function buildCardSet(cardSet, originX, originY) {
  const clones = [];
  for (let i = 0; i < cardSet.images.length; i++) {
    const card = cardSet.images[i];
    const master = findMasterFrame(card.frame_name);
    const clone = master.clone();

    await fillTextLayers(clone, card.texts || []);

    if (!card.keep_background) {
      await applyBackgroundImage(clone, card.data);
    }

    clone.clipsContent = true;
    clone.x = originX + i * (master.width + GAP);
    clone.y = originY;
    figma.currentPage.appendChild(clone);
    clones.push(clone);
  }
  return clones;
}

async function reportComplete(folderName) {
  try {
    await fetch(SERVER + "/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_name: folderName }),
    });
  } catch (e) {
    console.error("완료 보고 실패:", e);
  }
}

async function main() {
  let payload;
  try {
    const res = await fetch(SERVER + "/import.json");
    payload = await res.json();
  } catch (e) {
    figma.notify("❌ 서버 연결 실패 — python3 pipeline.py serve 를 먼저 실행하세요.");
    figma.closePlugin();
    return;
  }

  const cardSets = payload.card_sets || [];
  if (cardSets.length === 0) {
    figma.notify("생성할 카드 세트가 없습니다. (본문 승인된 세트가 없음)");
    figma.closePlugin();
    return;
  }

  figma.notify(`🚀 ${cardSets.length}개 세트 생성 중...`);

  const originX = figma.viewport.center.x;
  const originY = figma.viewport.center.y;
  let allClones = [];

  for (let setIndex = 0; setIndex < cardSets.length; setIndex++) {
    const cardSet = cardSets[setIndex];
    try {
      const clones = await buildCardSet(
        cardSet,
        originX,
        originY + setIndex * 1500
      );
      allClones = allClones.concat(clones);
      await reportComplete(cardSet.folder_name);
    } catch (e) {
      figma.notify(`❌ "${cardSet.folder_name}" 생성 실패: ${e.message}`);
    }
  }

  if (allClones.length > 0) {
    figma.currentPage.selection = allClones;
    figma.viewport.scrollAndZoomIntoView(allClones);
  }
  figma.notify(`✅ ${cardSets.length}개 세트, 카드 ${allClones.length}장 생성 완료`);
  figma.closePlugin();
}

main();
