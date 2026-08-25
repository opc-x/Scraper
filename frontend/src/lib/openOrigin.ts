export interface OriginJob {
  channel: string;
  external_id: string;
  url: string;
}

export interface OriginTargets {
  app: string;
  web: string;
  androidIntent: string;
}

export function originTargets(job: OriginJob): OriginTargets {
  const web = job.url || "";
  if (job.channel === "boss" && job.external_id) {
    const path = `www.zhipin.com/job_detail/${job.external_id}.html`;
    const page = web || `https://${path}`;
    return {
      app: `bosszhipin://${path}`,
      web: page,
      androidIntent:
        `intent://${path}#Intent;scheme=https;package=com.hpbr.bosszhipin;` +
        `S.browser_fallback_url=${encodeURIComponent(page)};end`,
    };
  }
  if (job.channel === "telegram" && web.includes("t.me/")) {
    return { app: web.replace("https://t.me/", "tg://resolve?domain="), web, androidIntent: "" };
  }
  if (job.channel === "discord" && web) {
    return { app: web.replace("https://discord.com/", "discord://"), web, androidIntent: "" };
  }
  return { app: "", web, androidIntent: "" };
}

export function openOrigin(job: OriginJob) {
  const targets = originTargets(job);
  if (!targets.web && !targets.app) return;
  if (/android/i.test(navigator.userAgent) && targets.androidIntent) {
    window.location.href = targets.androidIntent;
    return;
  }
  if (!targets.app) {
    window.location.href = targets.web;
    return;
  }
  const started = Date.now();
  const fallback = () => {
    if (document.hidden || Date.now() - started > 1800) return;
    window.location.href = targets.web;
  };
  window.location.href = targets.app;
  window.setTimeout(fallback, 900);
}
