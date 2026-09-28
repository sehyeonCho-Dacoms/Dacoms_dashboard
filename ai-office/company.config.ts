// ============================================================
//  나의 AI 회사 설정 — 여기 한 파일만 고치면 됩니다
// ============================================================
//  회사 이름, 부서 이름, 직원 이름·성격·머리색까지 전부 여기 있어요.
//  다른 파일은 건드리지 않아도 됩니다.
//
//  ⚠️ 딱 2가지 규칙
//   1. 부서 id(research, brand, ...)는 절대 바꾸지 마세요. 시뮬레이션 엔진이
//      이 id로 움직입니다. 바꾸면 캐릭터가 길을 잃어요.
//      → 바꿔도 되는 건 name(부서 이름) · icon · short 입니다.
//   2. 부서는 12개를 유지하세요. 사무실 배치가 4열 3행 = 12칸 고정입니다.
//      안 쓰는 부서는 지우지 말고 이름만 바꿔서 쓰세요.
//
//  직원 수는 자유롭게 늘리고 줄여도 됩니다. 한 팀에 팀장(lead) 1명은 두세요.
//
//  이 파일은 DACOMS 실제 업무(드래프트온 스포츠 헤드헌팅 + 카드뉴스 콘텐츠
//  제작)에 맞춰 구성했습니다. job_pipeline · card_news_pipeline · dashboard.html
//  에서 실제로 하는 일을 부서·직원 역할에 반영했어요.
// ============================================================

/** 회사 기본 정보 */
export const COMPANY = {
  /** 좌측 상단 헤더에 뜨는 회사 이름 */
  name: "DACOMS",
  /** 헤더 로고 배지에 들어갈 글자 1개 (이모지도 됩니다) */
  logoLetter: "D",
  /** 화면 상단 큰 제목 (앞부분) */
  titlePrefix: "다콤스",
  /** 화면 상단 큰 제목 (강조되는 뒷부분) */
  titleAccent: "AI Office",
  /** 브라우저 탭 제목 */
  pageTitle: "DACOMS AI Office — 드래프트온 운영실",
  /** 검색·공유될 때 뜨는 설명 */
  description: "드래프트온 헤드헌팅 파이프라인과 카드뉴스 콘텐츠 제작을 굴리는 12개 AI 팀의 사무실",
  /** 창 하단 파일명 느낌의 라벨 */
  windowLabel: "dacoms_ai_office.exe — 대표실",
  /** 일일 브리핑 제목에 들어갈 이름 */
  reportName: "DACOMS OPS",
} as const;

/** 대표(나) — 사무실 대표실에 앉아 있는 캐릭터 */
export const CEO_PROFILE = {
  name: "대표님",
  callsign: "대표님",
  role: "대표 · 최종 의사결정",
  hair: "#42283a",
  shirt: "#8fb4ff",
  accent: "#bcd8ff",
  skin: "#ffdcc4",
  thoughts: [
    "AI는 비서, 최종 결정은 내가 해요.",
    "오늘 드래프트온에 뭘 올릴지부터 본다.",
    "숫자보다 저장될 콘텐츠인지 먼저 봐요.",
  ],
};

/**
 * 부서 12개.
 * id = 고정(엔진용) / name·short·icon = 자유롭게 변경
 * task = 오늘 하는 일 / report = 팀장 한줄보고
 */
export const DEPARTMENTS = [
  {
    id: "research",
    name: "공고 수집팀",
    short: "intake.crawl",
    icon: "🔎",
    task: "사람인·워크넷·대한체육회 공고 수집",
    report: "신규 공고 원문을 확인하고 후보로 올려요.",
  },
  {
    id: "brand",
    name: "지표 분석팀",
    short: "ops.radar",
    icon: "🧬",
    task: "드래프트온 OPS 레이더 지표 점검",
    report: "공급·수요 노스스타 지표를 갱신해요.",
  },
  {
    id: "strategy1",
    name: "카드뉴스 기획팀",
    short: "topic.lab",
    icon: "💡",
    task: "카드뉴스 주제·타겟 페르소나 기획",
    report: "P.D.A 5앵글 후보를 정리해요.",
  },
  {
    id: "qa",
    name: "공고 심사팀",
    short: "fit.check",
    icon: "🛡️",
    task: "드래프트온 업로드 적합도 심사",
    report: "적합도 기준 미달 공고는 반려해요.",
  },
  {
    id: "strategy2",
    name: "카피라이팅팀",
    short: "copy.pda",
    icon: "✍️",
    task: "P.D.A 프레임 카피 원고 작성",
    report: "승인된 주제만 카피로 옮겨요.",
  },
  {
    id: "reels",
    name: "영상 콘텐츠팀",
    short: "video.edit",
    icon: "🎬",
    task: "구단·기업 소개 영상 편집",
    report: "원본은 보존하고 편집본만 새로 만들어요.",
  },
  {
    id: "carousel",
    name: "카드뉴스 디자인팀",
    short: "figma.render",
    icon: "🖼️",
    task: "피그마 임포트·카드뉴스 렌더링",
    report: "승인 카피만 1080x1350 PNG로 뽑아요.",
  },
  {
    id: "partner",
    name: "헤드헌팅 파트너팀",
    short: "lead.mail",
    icon: "💌",
    task: "구단·기업 헤드헌팅 리드 응대",
    report: "리드 스코어 높은 곳부터 답장 초안 써요.",
  },
  {
    id: "finance",
    name: "재무·정산팀",
    short: "finance.xls",
    icon: "🧾",
    task: "수수료·정산 현황 정리",
    report: "입금 대기 건부터 확인해요.",
  },
  {
    id: "review",
    name: "성과리뷰팀",
    short: "review.data",
    icon: "📈",
    task: "업로드·카드뉴스 성과 기록",
    report: "잘된 공고·카피 패턴을 남겨요.",
  },
  {
    id: "ops",
    name: "자동화 운영팀",
    short: "cron.ops",
    icon: "⚙️",
    task: "수집·렌더 파이프라인 크론 관리",
    report: "실패하면 재시도하고 로그를 남겨요.",
  },
  {
    id: "secretary",
    name: "비서실",
    short: "secretary.hq",
    icon: "📋",
    task: "전사 OPS 레이더 종합 브리핑",
    report: "대표가 결정할 것만 모아 남겨드려요.",
  },
] as const;

/**
 * 직원 명단.
 * dept = 위 부서 id / rank: "lead"(팀장) 또는 "member"(팀원)
 * colors = [머리색, 옷색, 포인트색]
 * thoughts = 자리를 비웠을 때 머리 위에 뜨는 혼잣말
 */
export type StaffEntry = {
  dept: string;
  rank: "lead" | "member";
  name: string;
  role: string;
  colors: [string, string, string];
  thoughts: string[];
  callsign?: string;
};

export const STAFF_LIST: StaffEntry[] = [
  // ① 공고 수집팀
  { dept: "research", rank: "lead", name: "김서연", role: "공고 수집 팀장", callsign: "김리서",
    colors: ["#6b3d34", "#fff3b0", "#ff8fc0"],
    thoughts: ["사람인 API 키 만료됐는지부터 확인.", "대한체육회 게시판은 매일 아침 긁어요.", "중복 공고는 사전에 걸러냅니다."] },
  { dept: "research", rank: "member", name: "박현우", role: "채용공고 크롤러 담당",
    colors: ["#2f2a3d", "#c9b8ff", "#b8f0dd"],
    thoughts: ["원티드는 ToS 확인 후에만 돌려요.", "워크넷 XML 파싱 에러 로그 확인 중."] },
  { dept: "research", rank: "member", name: "김나연", role: "공고 정규화 담당",
    colors: ["#8a4a3c", "#b8f0dd", "#ff8fc0"],
    thoughts: ["통일 스키마에 안 맞으면 반려해요.", "출처 URL 없는 공고는 안 받아요."] },

  // ② 지표 분석팀
  { dept: "brand", rank: "lead", name: "박보라", role: "지표 분석 팀장", callsign: "박브리",
    colors: ["#372b4a", "#c9b8ff", "#c9b8ff"],
    thoughts: ["공급·수요 노스스타부터 갱신합니다.", "헤드헌팅 파이프라인 가치, 오늘 기준으로 다시 계산."] },
  { dept: "brand", rank: "member", name: "오승민", role: "대시보드 데이터 담당",
    colors: ["#3c3a4f", "#ffe6f2", "#c9b8ff"],
    thoughts: ["dashboard.json 갱신 시간 확인.", "적합도 분포가 이상하면 먼저 알려요."] },
  { dept: "brand", rank: "member", name: "서지안", role: "채용시장 트렌드 담당",
    colors: ["#5a3450", "#fff3b0", "#ff8fc0"],
    thoughts: ["스포츠 채용 시장 흐름 다시 훑는 중.", "구단 소식은 항상 원문부터 확인."] },

  // ③ 카드뉴스 기획팀
  { dept: "strategy1", rank: "lead", name: "최아름", role: "카드뉴스 기획 팀장", callsign: "최아이",
    colors: ["#c26e4b", "#ff8fc0", "#fff3b0"],
    thoughts: ["오늘 주제·페르소나 세트부터 정합니다.", "앵글 5개는 최대한 관점을 다르게.", "저장할 만한 훅인지부터 본다."] },
  { dept: "strategy1", rank: "member", name: "한소율", role: "타겟 페르소나 리서치",
    colors: ["#7b4a2f", "#b8f0dd", "#ff8fc0"],
    thoughts: ["타겟이 흐려지면 주제부터 다시 잡아요.", "페르소나 말투로 다시 읽어봐요."] },
  { dept: "strategy1", rank: "member", name: "임도현", role: "이슈 발제",
    colors: ["#2c2638", "#fff3b0", "#c9b8ff"],
    thoughts: ["이번 주 스포츠 채용 이슈 스캔 중.", "재포장 기사는 원문으로 안 쳐요."] },

  // ④ 공고 심사팀
  { dept: "qa", rank: "lead", name: "윤규아", role: "공고 심사 팀장", callsign: "윤큐아",
    colors: ["#2d4b46", "#b8f0dd", "#b8f0dd"],
    thoughts: ["적합도 기준 미달이면 바로 반려.", "중복 업로드는 무조건 걸러냅니다."] },
  { dept: "qa", rank: "member", name: "문세아", role: "적합도 스코어링 검수",
    colors: ["#463227", "#ffe6f2", "#b8f0dd"],
    thoughts: ["drafton_fit 점수 근거부터 확인해요.", "리드 스코어 계산 다시 검증 중."] },
  { dept: "qa", rank: "member", name: "배준혁", role: "톤·표현 검수",
    colors: ["#6c3a55", "#c9b8ff", "#fff3b0"],
    thoughts: ["과장된 채용 문구는 바로 수정 요청.", "차별적 표현 스캔 돌립니다."] },

  // ⑤ 카피라이팅팀
  { dept: "strategy2", rank: "lead", name: "한도빈", role: "카피라이팅 팀장", callsign: "한대본",
    colors: ["#8b534a", "#fff3b0", "#ff8fc0"],
    thoughts: ["승인된 주제만 원고로 옮겨요.", "CTA는 마지막 장에서 한 번만."] },
  { dept: "strategy2", rank: "member", name: "유재원", role: "Problem 단계 담당",
    colors: ["#33304a", "#ff8fc0", "#b8f0dd"],
    thoughts: ["문제 정의가 약하면 다시 씁니다.", "훅 3초 안에 안 걸리면 다시 써요."] },
  { dept: "strategy2", rank: "member", name: "신다연", role: "Desire·Action 단계 담당",
    colors: ["#5d3a2c", "#b8f0dd", "#c9b8ff"],
    thoughts: ["해결된 모습을 구체적으로 그려야 해요.", "다음 행동 1개는 꼭 넣습니다."] },

  // ⑥ 영상 콘텐츠팀
  { dept: "reels", rank: "lead", name: "송리원", role: "영상 콘텐츠 팀장", callsign: "송릴스",
    colors: ["#2c2638", "#ff8fc0", "#ff8fc0"],
    thoughts: ["구단 소개 영상 원본은 절대 안 건드려요.", "쇼츠는 3초 훅부터 잡습니다."] },
  { dept: "reels", rank: "member", name: "백하람", role: "편집",
    colors: ["#4a3a2a", "#fff3b0", "#b8f0dd"],
    thoughts: ["무음 컷부터 쳐냅니다.", "자막 타이밍 다시 맞추는 중."] },
  { dept: "reels", rank: "member", name: "남주원", role: "썸네일",
    colors: ["#7a3f58", "#c9b8ff", "#ff8fc0"],
    thoughts: ["썸네일 5종 뽑아둘게요.", "워터마크는 안 넣습니다."] },

  // ⑦ 카드뉴스 디자인팀
  { dept: "carousel", rank: "lead", name: "이가림", role: "카드뉴스 디자인 팀장", callsign: "이캐리",
    colors: ["#d88d68", "#c9b8ff", "#c9b8ff"],
    thoughts: ["원본 템플릿은 복제만, 수정 금지.", "figma_import.json 형식부터 확인."] },
  { dept: "carousel", rank: "member", name: "윤가은", role: "레이아웃",
    colors: ["#3a2f4d", "#ffe6f2", "#ff8fc0"],
    thoughts: ["1080x1350 비율 다시 체크.", "글자 밀도 맞추는 중."] },
  { dept: "carousel", rank: "member", name: "표승우", role: "렌더링",
    colors: ["#274a44", "#fff3b0", "#b8f0dd"],
    thoughts: ["Playwright 렌더 큐 확인 중.", "5장 다 나왔는지 마지막에 체크."] },

  // ⑧ 헤드헌팅 파트너팀
  { dept: "partner", rank: "lead", name: "정파랑", role: "헤드헌팅 파트너 팀장", callsign: "정파트",
    colors: ["#563a32", "#b8f0dd", "#b8f0dd"],
    thoughts: ["리드 스코어 높은 기업부터 답장 초안.", "실제 발송은 대표 손으로."] },
  { dept: "partner", rank: "member", name: "정태양", role: "제휴 검토",
    colors: ["#452d3f", "#c9b8ff", "#fff3b0"],
    thoughts: ["결이 맞는 제안만 받습니다.", "구단·에이전시 문의는 따로 태그해요."] },

  // ⑨ 재무·정산팀
  { dept: "finance", rank: "lead", name: "오재민", role: "재무 팀장", callsign: "오재무",
    colors: ["#313b56", "#fff3b0", "#fff3b0"],
    thoughts: ["수수료 정산 현황 파일부터 확인.", "입금 대기 건 먼저 표시해둡니다."] },
  { dept: "finance", rank: "member", name: "마준영", role: "정산 관리",
    colors: ["#4b3b2c", "#b8f0dd", "#c9b8ff"],
    thoughts: ["지연된 건은 따로 표시해둡니다.", "결제는 자동으로 안 해요."] },

  // ⑩ 성과리뷰팀
  { dept: "review", rank: "lead", name: "강성아", role: "성과리뷰 팀장", callsign: "강성과",
    colors: ["#9c5c72", "#ff8fc0", "#ff8fc0"],
    thoughts: ["적합도 높았던 공고 패턴부터 남겨요.", "카드뉴스 저장·공유 지표 다시 긁어옵니다."] },
  { dept: "review", rank: "member", name: "곽태민", role: "지표 수집",
    colors: ["#2e3a4a", "#ffe6f2", "#b8f0dd"],
    thoughts: ["도달·저장·전환 다시 모읍니다.", "연동되면 자동화돼요."] },
  { dept: "review", rank: "member", name: "우다인", role: "학습점 정리",
    colors: ["#6b4a2f", "#c9b8ff", "#fff3b0"],
    thoughts: ["반복할 패턴 1개, 중단할 패턴 1개.", "다음 기획팀에 넘길 인사이트 정리 중."] },

  // ⑪ 자동화 운영팀
  { dept: "ops", rank: "lead", name: "안도현", role: "자동화 운영 팀장", callsign: "안오토",
    colors: ["#3b3b49", "#b8f0dd", "#b8f0dd"],
    thoughts: ["크론 스케줄 정상인지 아침마다 확인.", "실패하면 재시도하고 로그 남겨요."] },
  { dept: "ops", rank: "member", name: "류하진", role: "연동 모니터링",
    colors: ["#573049", "#fff3b0", "#ff8fc0"],
    thoughts: ["연결 안 된 서비스를 성공으로 안 씁니다.", "API 키 만료 알림 확인 중."] },

  // ⑫ 비서실
  { dept: "secretary", rank: "lead", name: "김세리", role: "비서실장", callsign: "김비서",
    colors: ["#7a453c", "#c9b8ff", "#c9b8ff"],
    thoughts: ["대표가 결정할 것만 추립니다.", "OPS 레이더 종합해서 올릴게요."] },
  { dept: "secretary", rank: "member", name: "구윤아", role: "브리핑 정리",
    colors: ["#334a3a", "#ffe6f2", "#fff3b0"],
    thoughts: ["상태별로 묶어서 올릴게요.", "막힌 건 먼저 보고해요."] },
];

/**
 * 외부 연동을 아직 안 붙인 팀 → 화면에 "연동 대기"로 표시됩니다.
 * 연동을 다 붙였거나, 그냥 전부 초록불로 보고 싶으면 빈 배열 []로 두세요.
 */
export const PENDING_INTEGRATIONS: Record<string, string> = {
  brand: "OPS 레이더 실데이터 연동",
  partner: "메일 연동",
  finance: "재무 현황 파일",
};

/**
 * 결과 보관함 링크 (Notion 등). 비워두면 화면에서 링크 버튼이 숨겨집니다.
 * 예: "https://www.notion.so/내페이지주소"
 */
export const STORAGE_LINK = "";
