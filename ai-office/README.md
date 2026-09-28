# 나의 AI 회사 (AI Office)

AI 직원들이 출근하고, 자리에 앉아 일하고, 회의실에 모이고, 대표실로 보고하러 오는 **픽셀 사무실**입니다.

혼자 일하는 사람이 "나도 회사가 있으면 좋겠다" 싶을 때 쓰라고 만들었어요.
설치하면 바로 돌아갑니다. **연동 하나도 안 해도 됩니다.**

---

## 1. 실행하기 (5분)

**필요한 것**: Node.js 22 이상 ([nodejs.org](https://nodejs.org)에서 설치)

터미널을 열고 이 폴더에서:

```bash
npm install
npm run dev
```

브라우저에서 **http://localhost:3000** 을 엽니다. 끝이에요.

> 창을 닫으면 서버도 꺼집니다. 다시 보려면 `npm run dev`를 다시 실행하세요.

---

## 2. 내 회사로 바꾸기

**`company.config.ts` 파일 하나만 고치면 됩니다.** 다른 파일은 안 건드려도 돼요.

그 안에 이런 게 들어 있습니다:

| 고칠 것 | 어디 |
|---|---|
| 회사 이름, 로고 글자, 화면 제목 | `COMPANY` |
| 대표(나) 이름·성격·머리색 | `CEO_PROFILE` |
| 부서 12개 이름·아이콘·하는 일 | `DEPARTMENTS` |
| 직원 이름·직책·색·혼잣말 | `STAFF_LIST` |
| "연동 대기"로 표시할 팀 | `PENDING_INTEGRATIONS` |
| 결과물 보관함 링크 | `STORAGE_LINK` |

저장하면 화면이 자동으로 새로고침됩니다.

### ⚠️ 딱 2가지만 지키세요

1. **부서 `id`는 바꾸지 마세요** (`research`, `brand`, `strategy1` …)
   시뮬레이션 엔진이 이 id로 캐릭터를 움직입니다. 바꾸면 직원들이 길을 잃어요.
   → 바꿔도 되는 건 `name`(부서 이름) · `icon` · `short` 입니다.

2. **부서는 12개를 유지하세요.**
   사무실 배치가 4열 3행 = 12칸 고정입니다.
   안 쓰는 부서는 지우지 말고 **이름만 바꿔서** 쓰세요.

직원 수는 자유입니다. 늘려도 줄여도 되고, 한 팀에 팀장(`lead`) 1명만 두면 됩니다.

---

## 3. AI한테 시키는 법 (제일 편한 방법)

직접 고치기 귀찮으면, Claude Code나 Codex 같은 AI 코딩 도구에 이 폴더를 열고
아래를 그대로 복붙하세요.

```
company.config.ts 파일만 고쳐줘. 다른 파일은 건드리지 마.

내 직업: [예: 유튜브 채널 운영자]
내 이름: [예: 박지우]
회사 이름: [예: 지우 스튜디오]

이 일에 맞게 부서 12개 이름과 직원들을 다시 지어줘.
- 부서 id는 절대 바꾸지 말고, name·icon·short·task·report만 바꿔.
- 부서는 12개 그대로 유지해.
- 직원 이름은 한국 이름으로, 각자 성격이 드러나는 혼잣말을 2~3개씩 넣어줘.
- 색깔(colors)은 지금 쓰는 파스텔 톤에서 벗어나지 않게 해줘.
```

---

## 4. 나중에 진짜로 연동하고 싶다면

기본 상태에서는 화면의 연동 항목이 **"미설정"** 으로 뜹니다. 정상이에요.
(연결 안 된 걸 연결됐다고 표시하지 않는 게 이 툴의 원칙입니다.)

진짜 Notion·Discord로 보고서를 보내고 싶으면:

1. `.dev.vars.example` 파일을 복사해서 `.dev.vars` 라는 이름으로 저장
2. 그 안에 값 채우기 (파일 안에 방법이 적혀 있어요)
3. `npm run dev` 다시 실행

**Notion 하나만 붙여도 충분히 재밌습니다.** 2분이면 되고, 붙는 순간 내 AI 회사가
진짜 내 노션에 일일 브리핑을 씁니다.

> 🔒 `.dev.vars` 는 절대 남에게 주거나 인터넷에 올리지 마세요. 비밀번호와 같습니다.
> 이 폴더를 남에게 줄 때도 `.dev.vars` 는 빼고 주세요.

### Instagram 연동

인스타그램 팔로워·게시물 수를 대시보드에 실시간으로 표시하려면:

1. 인스타그램 앱 → 설정 → 계정 유형 및 도구 → **프로페셔널 계정으로 전환** (비즈니스 또는 크리에이터)
2. 그 계정을 **Facebook 페이지**에 연결 (없으면 페이지부터 만들기)
3. [developers.facebook.com](https://developers.facebook.com) 접속 → 내 앱 → **앱 만들기** → 유형 "비즈니스" 선택
4. 앱을 **개발 모드**로 둔 채로 진행하세요. 개발 모드에서는 앱을 정식 심사(App Review) 받지 않아도
   본인 계정 데이터는 조회할 수 있습니다. (다른 사람 계정을 조회하려면 심사가 필요합니다)
5. [Graph API Explorer](https://developers.facebook.com/tools/explorer)에서 방금 만든 앱 선택 →
   본인 계정으로 로그인 → 권한(permissions)에서 아래 4개 체크 → **Access Token 생성**
   - `pages_show_list`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_manage_insights`
6. 이 토큰은 짧게 만료되는 "단기 토큰"입니다. **장기 토큰(60일)** 으로 교환하세요:
   ```
   GET https://graph.facebook.com/v21.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id=앱ID
     &client_secret=앱시크릿
     &fb_exchange_token=단기토큰
   ```
   (앱 ID·시크릿은 앱 대시보드 → 설정 → 기본 설정에서 확인)
7. 내 Instagram 비즈니스 계정 ID 확인:
   ```
   GET https://graph.facebook.com/v21.0/me/accounts?access_token=장기토큰
   ```
   응답으로 나오는 페이지 ID로 다시 조회:
   ```
   GET https://graph.facebook.com/v21.0/{페이지ID}?fields=instagram_business_account&access_token=장기토큰
   ```
8. `.dev.vars`에 `INSTAGRAM_ACCESS_TOKEN`(7번의 장기 토큰), `INSTAGRAM_BUSINESS_ID`(7번의 계정 ID) 채우기
9. `npm run dev` 다시 실행 → 대시보드에 팔로워·게시물 수가 뜨면 성공

> ⚠️ 장기 토큰은 60일마다 만료됩니다. 화면에서 "토큰이 만료됐어요"가 뜨면 6번부터 다시 반복하세요.

---

## 5. 자주 막히는 곳

**`npm install` 에서 에러가 나요**
Node 버전이 낮은 경우입니다. `node -v` 로 확인해서 22 미만이면 새로 설치하세요.

**3000번 포트가 이미 쓰이고 있대요**
다른 포트로 띄우면 됩니다: `npx vinext dev --port 3001`

**직원이 안 움직여요**
화면 위쪽 **"오늘 업무 시작하기"** 를 눌러야 하루가 시작됩니다.

**부서를 지웠더니 화면이 깨져요**
12개를 유지해야 합니다. 되돌리고 이름만 바꾸세요.

---

이 툴은 **갓생맘 🎀** 이 만들었어요.
📷 [@godseng.mom](https://www.instagram.com/godseng.mom/) — 더 많은 크리에이터 툴 보러가기

자유롭게 쓰고 고치되, 무단 재판매는 하지 말아주세요.
