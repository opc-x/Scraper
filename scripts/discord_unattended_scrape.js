(() => {
  if (window.__dcScrapeRunning) return { started: false, reason: "already" };
  window.__dcScrapeRunning = true;
  const HOST = "http://127.0.0.1:8766";
  const ALL_JOBS = { guildId: "1488674851345531057", guild: "CronJobs", channelId: "1492516535497920624", channel: "all-jobs", kind: "forum" };
  const EXTRA = [
    { guildId: "851527874828566558", guild: "Invide", channelId: "896062986941251596", channel: "remote-job-board", kind: "text" },
    { guildId: "880546729349488741", guild: "Devs For Hire", channelId: "1102927731353735279", channel: "jobs-forum", kind: "forum" },
    { guildId: "880546729349488741", guild: "Devs For Hire", channelId: "927703276487606302", channel: "paid-jobs", kind: "text" },
    { guildId: "969872191179071498", guild: "Cookie", channelId: "970486424002519150", channel: "jobs", kind: "text" },
    { guildId: "969872191179071498", guild: "Cookie", channelId: "1529098285959217253", channel: "job-opportunity", kind: "text" },
    { guildId: "1116994814349688875", guild: "Job cord", channelId: "1495948606644027564", channel: "jobs", kind: "text" },
    { guildId: "1224897044259278858", guild: "NextJob", channelId: "1440140071847198853", channel: "hiring", kind: "forum" },
    { guildId: "1224897044259278858", guild: "NextJob", channelId: "1464016709840142510", channel: "hiring2", kind: "forum" },
    { guildId: "1224897044259278858", guild: "NextJob", channelId: "1459767557262282866", channel: "find-jobs-here", kind: "text" },
    { guildId: "1297484076407853147", guild: "FreeLanceBase", channelId: "1297574700653740202", channel: "jobs", kind: "text" },
    { guildId: "1297484076407853147", guild: "FreeLanceBase", channelId: "1297574818568339496", channel: "post-job", kind: "text" },
    { guildId: "698366411864670250", guild: "cscareers.dev", channelId: "1306817435227394070", channel: "intern_postings", kind: "text" },
    { guildId: "1002522561613135892", guild: "Freelance Marketplace", channelId: "1052528790707904573", channel: "reddit-dev-jobs", kind: "text" },
  ];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const getToken = () => {
    let token = null;
    webpackChunkdiscord_app.push([
      [Math.random()],
      {},
      (req) => {
        for (const id of Object.keys(req.c || {})) {
          try {
            const m = req.c[id].exports;
            const cand = m && (m.default || m);
            if (cand && typeof cand.getToken === "function") {
              const t = cand.getToken();
              if (typeof t === "string" && t.length > 20) token = t;
            }
          } catch (e) {}
        }
      },
    ]);
    return token;
  };
  const urlsFrom = (fm) => {
    const out = [];
    for (const e of fm.embeds || []) if (e.url) out.push(e.url);
    for (const row of fm.components || []) {
      for (const c of row.components || []) if (c.url) out.push(c.url);
    }
    const m = String(fm.content || "").match(/https?:\/\/[^\s<>)]+/g) || [];
    out.push(...m);
    return [...new Set(out)];
  };
  const dump = (batch) =>
    fetch(HOST + "/dump", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "jobs", batch }),
    });
  const heartbeat = (state) =>
    fetch(HOST + "/heartbeat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state),
    }).catch(() => {});
  const scrapeForum = async (token, src, startOffset) => {
    let offset = startOffset || 0;
    while (true) {
      const res = await fetch(
        "https://discord.com/api/v9/channels/" +
          src.channelId +
          "/threads/search?sort_by=creation_time&sort_order=desc&limit=25&offset=" +
          offset +
          "&archived=true",
        { headers: { Authorization: token } },
      );
      if (res.status === 429) {
        const j = await res.json().catch(() => ({}));
        await sleep(((j.retry_after || 1) * 1000) + 400);
        continue;
      }
      if (!res.ok) break;
      const data = await res.json();
      const threads = data.threads || [];
      const fmById = {};
      for (const fm of data.first_messages || []) fmById[fm.id] = fm;
      const batch = [];
      for (const t of threads) {
        const fm = fmById[t.id] || {};
        batch.push({
          guildId: src.guildId,
          guild: src.guild,
          channelId: src.channelId,
          channel: src.channel,
          threadId: t.id,
          name: t.name || "",
          content: String(fm.content || "").slice(0, 4000),
          apply: urlsFrom(fm).slice(0, 8),
          ts: (t.thread_metadata && t.thread_metadata.create_timestamp) || fm.timestamp || "",
        });
      }
      if (batch.length) await dump(batch);
      if (!threads.length || data.has_more === false) break;
      offset += threads.length;
      window.__cjOffset = offset;
      await heartbeat({ phase: src.channel, offset, lastStatus: res.status });
      await sleep(160);
    }
  };
  const scrapeText = async (token, src) => {
    let before = "";
    const cutoff = Date.now() - 90 * 24 * 3600 * 1000;
    for (let n = 0; n < 40; n++) {
      const url =
        "https://discord.com/api/v9/channels/" +
        src.channelId +
        "/messages?limit=100" +
        (before ? "&before=" + before : "");
      const res = await fetch(url, { headers: { Authorization: token } });
      if (res.status === 429) {
        const j = await res.json().catch(() => ({}));
        await sleep(((j.retry_after || 1) * 1000) + 400);
        n -= 1;
        continue;
      }
      if (!res.ok) break;
      const msgs = await res.json();
      if (!Array.isArray(msgs) || !msgs.length) break;
      const batch = [];
      let old = false;
      for (const msg of msgs) {
        const ts = Date.parse(msg.timestamp || "") || 0;
        if (ts && ts < cutoff) old = true;
        const text = String(msg.content || "");
        if (text.length < 20) continue;
        batch.push({
          guildId: src.guildId,
          guild: src.guild,
          channelId: src.channelId,
          channel: src.channel,
          threadId: msg.id,
          name: text.split("\n")[0].slice(0, 180),
          content: text.slice(0, 4000),
          apply: urlsFrom(msg).slice(0, 8),
          ts: msg.timestamp || "",
        });
      }
      if (batch.length) await dump(batch);
      before = String(msgs[msgs.length - 1].id || "");
      await heartbeat({ phase: src.channel, page: n, lastStatus: res.status });
      if (old || msgs.length < 100 || !before) break;
      await sleep(180);
    }
  };
  (async () => {
    const token = getToken();
    if (!token) {
      window.__dcScrapeRunning = false;
      await heartbeat({ phase: "error", reason: "no_token" });
      return;
    }
    let start = window.__cjOffset || 0;
    try {
      const st = await (await fetch(HOST + "/status")).json();
      if (typeof st.offsetHint === "number" && st.offsetHint > start) start = st.offsetHint;
    } catch (e) {}
    await heartbeat({ phase: "all-jobs", offset: start });
    await scrapeForum(token, ALL_JOBS, start);
    for (const src of EXTRA) {
      await heartbeat({ phase: src.guild + "/" + src.channel });
      if (src.kind === "forum") await scrapeForum(token, src, 0);
      else await scrapeText(token, src);
    }
    await heartbeat({ phase: "done" });
    window.__dcScrapeRunning = false;
  })();
  return { started: true };
})();
