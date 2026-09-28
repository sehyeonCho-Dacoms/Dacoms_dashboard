/**
 * Instagram(Meta Graph API) 채널 지표 조회.
 *
 *   INSTAGRAM_ACCESS_TOKEN   장기 액세스 토큰 (60일 만료, 주기적으로 재발급 필요)
 *   INSTAGRAM_BUSINESS_ID    연결된 Instagram 비즈니스/크리에이터 계정 ID
 *
 * 발급 방법은 README.md의 "Instagram 연동" 섹션 참고.
 */

export type InstagramEnv = {
  INSTAGRAM_ACCESS_TOKEN?: string;
  INSTAGRAM_BUSINESS_ID?: string;
};

export type InstagramMetrics = {
  username: string;
  followers: number;
  mediaCount: number;
};

const GRAPH_VERSION = "v21.0";

export async function fetchInstagramMetrics(
  env: InstagramEnv,
): Promise<{ ok: true; metrics: InstagramMetrics } | { ok: false; detail: string }> {
  if (!env.INSTAGRAM_ACCESS_TOKEN || !env.INSTAGRAM_BUSINESS_ID) {
    return { ok: false, detail: "INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_BUSINESS_ID 미설정" };
  }

  const url = new URL(`https://graph.facebook.com/${GRAPH_VERSION}/${env.INSTAGRAM_BUSINESS_ID}`);
  url.searchParams.set("fields", "username,followers_count,media_count");
  url.searchParams.set("access_token", env.INSTAGRAM_ACCESS_TOKEN);

  const response = await fetch(url.toString());
  const json = (await response.json().catch(() => ({}))) as {
    username?: string;
    followers_count?: number;
    media_count?: number;
    error?: { message?: string; code?: number };
  };

  if (!response.ok || json.error) {
    const hint =
      json.error?.code === 190
        ? "토큰이 만료됐어요. 장기 액세스 토큰을 다시 발급받으세요."
        : (json.error?.message ?? `HTTP ${response.status}`);
    return { ok: false, detail: hint };
  }

  return {
    ok: true,
    metrics: {
      username: json.username ?? "",
      followers: json.followers_count ?? 0,
      mediaCount: json.media_count ?? 0,
    },
  };
}
