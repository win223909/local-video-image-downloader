const STATS_TOKEN_KEY = "videoDownloaderStatsToken";

const els = {
  authPanel: document.querySelector("#statsAuthPanel"),
  tokenInput: document.querySelector("#statsTokenInput"),
  loadButton: document.querySelector("#statsLoadButton"),
  authMessage: document.querySelector("#statsAuthMessage"),
  statsPanel: document.querySelector("#statsPanel"),
  updatedAt: document.querySelector("#statsUpdatedAt"),
  rangeButtons: Array.from(document.querySelectorAll(".stats-range-button")),
  refreshButton: document.querySelector("#statsRefreshButton"),
  clearTokenButton: document.querySelector("#statsClearTokenButton"),
  installerDownloads: document.querySelector("#statInstallerDownloads"),
  updateDownloads: document.querySelector("#statUpdateDownloads"),
  linkIssued: document.querySelector("#statLinkIssued"),
  visitors: document.querySelector("#statVisitors"),
  blocked: document.querySelector("#statBlocked"),
  checks: document.querySelector("#statChecks"),
  trend: document.querySelector("#statsTrend"),
  fileTable: document.querySelector("#statsFileTable"),
  platformTable: document.querySelector("#statsPlatformTable"),
  recentDownloads: document.querySelector("#statsRecentDownloads"),
  recentEvents: document.querySelector("#statsRecentEvents"),
};

let statsToken = localStorage.getItem(STATS_TOKEN_KEY) || "";
let activeDays = Number(localStorage.getItem("videoDownloaderStatsDays") || "1");
if (![1, 7, 30].includes(activeDays)) activeDays = 1;

consumeTokenFromHash();
setupEvents();
setActiveRange(activeDays);
if (statsToken) {
  els.tokenInput.value = statsToken;
  loadStats();
}

function setupEvents() {
  els.loadButton.addEventListener("click", () => {
    statsToken = els.tokenInput.value.trim();
    if (!statsToken) {
      setMessage("请输入管理员口令。", true);
      return;
    }
    localStorage.setItem(STATS_TOKEN_KEY, statsToken);
    loadStats();
  });
  els.tokenInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") els.loadButton.click();
  });
  els.refreshButton.addEventListener("click", loadStats);
  els.clearTokenButton.addEventListener("click", () => {
    statsToken = "";
    localStorage.removeItem(STATS_TOKEN_KEY);
    els.tokenInput.value = "";
    hide(els.statsPanel);
    show(els.authPanel);
    setMessage("已退出后台。", false);
  });
  els.rangeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setActiveRange(Number(button.dataset.days || "1"));
      loadStats();
    });
  });
}

function consumeTokenFromHash() {
  const rawHash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
  const params = new URLSearchParams(rawHash);
  const token = params.get("token") || params.get("statsToken");
  if (!token) return;
  statsToken = token;
  localStorage.setItem(STATS_TOKEN_KEY, token);
  window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
}

function setActiveRange(days) {
  activeDays = days;
  localStorage.setItem("videoDownloaderStatsDays", String(activeDays));
  els.rangeButtons.forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.days || "1") === activeDays);
  });
}

async function loadStats() {
  if (!statsToken) return;
  setLoading(true);
  setMessage("正在读取统计...", false);
  try {
    const response = await fetch(`./api/download-stats?days=${activeDays}&limit=50`, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${statsToken}`,
      },
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.error || "读取统计失败。");
    }
    renderStats(payload);
    hide(els.authPanel);
    show(els.statsPanel);
    setMessage("统计已更新。", false);
  } catch (error) {
    show(els.authPanel);
    hide(els.statsPanel);
    setMessage(error.message || "读取统计失败，请检查管理员口令。", true);
  } finally {
    setLoading(false);
  }
}

function renderStats(payload) {
  const summary = payload.summary || {};
  const checks = Number(summary.installer_checks || 0) + Number(summary.update_checks || 0);
  els.installerDownloads.textContent = formatNumber(summary.installer_downloads);
  els.updateDownloads.textContent = formatNumber(summary.update_downloads);
  els.linkIssued.textContent = formatNumber(summary.link_issued);
  els.visitors.textContent = formatNumber(summary.estimated_visitors);
  els.blocked.textContent = formatNumber(summary.blocked_requests);
  els.checks.textContent = formatNumber(checks);
  els.updatedAt.textContent = `更新时间：${new Date().toLocaleString()}`;

  renderTrend(payload.by_day || []);
  renderPairTable(els.fileTable, payload.downloads?.by_file || [], "暂无真实下载。");
  renderPairTable(els.platformTable, Object.entries(payload.platforms || {}), "暂无点击记录。");
  renderEventTable(els.recentDownloads, payload.downloads?.recent || [], true);
  renderEventTable(els.recentEvents, payload.recent || [], false);
}

function renderTrend(days) {
  if (!days.length) {
    els.trend.innerHTML = `<p class="muted">暂无趋势数据。</p>`;
    return;
  }
  const maxValue = Math.max(
    1,
    ...days.map((day) => (
      Number(day.installer_downloads || 0)
      + Number(day.update_downloads || 0)
      + Number(day.link_issued || 0)
      + Number(day.blocked || 0)
    )),
  );
  els.trend.innerHTML = days.map((day) => {
    const downloads = Number(day.installer_downloads || 0) + Number(day.update_downloads || 0);
    const clicks = Number(day.link_issued || 0);
    const blocked = Number(day.blocked || 0);
    return `
      <div class="trend-row">
        <span class="trend-date">${escapeHtml(formatDay(day.date))}</span>
        <div class="trend-bars" aria-label="${escapeHtml(day.date)}">
          ${bar("下载", downloads, maxValue, "download")}
          ${bar("点击", clicks, maxValue, "click")}
          ${bar("拦截", blocked, maxValue, "blocked")}
        </div>
        <span class="trend-total">${formatNumber(downloads)} / ${formatNumber(clicks)} / ${formatNumber(blocked)}</span>
      </div>
    `;
  }).join("");
}

function bar(label, value, maxValue, type) {
  const width = Math.max(value > 0 ? 4 : 0, Math.round((value / maxValue) * 100));
  return `<span class="trend-bar trend-bar-${type}" title="${label}: ${value}" style="width:${width}%"></span>`;
}

function renderPairTable(container, rows, emptyText) {
  if (!rows.length) {
    container.innerHTML = `<p class="muted">${emptyText}</p>`;
    return;
  }
  container.innerHTML = `
    <table>
      <thead><tr><th>名称</th><th>次数</th></tr></thead>
      <tbody>
        ${rows.map(([name, count]) => `
          <tr>
            <td>${escapeHtml(displayName(name))}</td>
            <td>${formatNumber(count)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderEventTable(container, rows, downloadsOnly) {
  if (!rows.length) {
    container.innerHTML = `<p class="muted">${downloadsOnly ? "暂无真实下载。" : "暂无事件。"}</p>`;
    return;
  }
  container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>时间</th>
          <th>${downloadsOnly ? "文件" : "事件"}</th>
          <th>方式</th>
          <th>地区</th>
          <th>浏览器</th>
        </tr>
      </thead>
      <tbody>
        ${rows.slice().reverse().map((row) => `
          <tr>
            <td>${escapeHtml(formatTime(row.ts))}</td>
            <td>${escapeHtml(downloadsOnly ? displayName(row.filename) : eventLabel(row))}</td>
            <td>${escapeHtml(row.method || "")}</td>
            <td>${escapeHtml(row.country || "-")}</td>
            <td>${escapeHtml(shortUserAgent(row.user_agent || ""))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function eventLabel(row) {
  const event = row.event || "";
  if (event === "link_issued") return `发放链接：${displayName(row.platform || row.filename)}`;
  if (event === "download_granted") return `安装包放行：${displayName(row.filename)}`;
  if (event === "update_package_granted") return "更新包放行";
  if (event.endsWith("_rejected")) return `已拦截：${row.reason || event}`;
  if (event === "stats_viewed") return "查看统计";
  if (event === "stats_rejected") return "统计访问被拒";
  return event || "-";
}

function displayName(value) {
  const text = String(value || "-");
  if (text === "macos" || text === "mac") return "macOS";
  if (text === "windows" || text === "win") return "Windows";
  if (text === "VideoDownloaderAgent-macOS.zip") return "macOS 安装包";
  if (text === "VideoDownloaderAgent-Windows.zip") return "Windows 安装包";
  if (text === "agent-source.zip") return "更新包";
  return text;
}

function shortUserAgent(value) {
  if (!value) return "-";
  if (value.startsWith("Mozilla/5.0")) {
    const browser = value.match(/(Chrome|CriOS|Firefox|FxiOS|Version|Safari|Edg|Edge)\/([0-9.]+)/);
    const os = value.match(/\(([^)]+)\)/);
    return [browser ? browser[0] : "Browser", os ? os[1].split(";").slice(0, 2).join(";") : ""].filter(Boolean).join(" · ");
  }
  return value.length > 72 ? `${value.slice(0, 72)}...` : value;
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDay(value) {
  if (!value) return "-";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function setLoading(isLoading) {
  els.loadButton.disabled = isLoading;
  els.refreshButton.disabled = isLoading;
  els.loadButton.textContent = isLoading ? "读取中..." : "查看统计";
}

function setMessage(message, isError) {
  els.authMessage.textContent = message;
  els.authMessage.classList.toggle("form-error", Boolean(isError));
}

function show(element) {
  element.classList.remove("hidden");
}

function hide(element) {
  element.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
