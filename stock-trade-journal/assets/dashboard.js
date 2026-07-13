let echartsLoadPromise = null;
const DASHBOARD_SNAPSHOT_KEY = "stj.dashboard.snapshots.v1";
const DASHBOARD_SNAPSHOT_MAX_AGE = 30 * 60 * 1000;

function readDashboardSnapshots() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DASHBOARD_SNAPSHOT_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function loadDashboardSnapshot(key) {
  const entry = readDashboardSnapshots()[key];
  if (!entry?.saved_at || !entry?.response || Date.now() - entry.saved_at > DASHBOARD_SNAPSHOT_MAX_AGE) return null;
  const response = JSON.parse(JSON.stringify(entry.response));
  response.meta ||= {};
  const ageSeconds = Math.max(0, Math.round((Date.now() - entry.saved_at) / 1000));
  response.meta.cache = { ...(response.meta.cache || {}), hit: true, stale: true, age_seconds: ageSeconds };
  response.meta.response_cache = { hit: true, stale: true, age_seconds: ageSeconds, layer: "browser-local" };
  response.meta.warnings = [...new Set([...(response.meta.warnings || []), "先显示浏览器内最后成功快照，后台正在刷新"])];
  return response;
}

function saveDashboardSnapshot(key, response) {
  if (!response?.ok || !response.data || response.meta?.response_cache?.stale) return;
  try {
    const snapshots = readDashboardSnapshots();
    snapshots[key] = { saved_at: Date.now(), response };
    const trimmed = Object.fromEntries(Object.entries(snapshots)
      .sort((left, right) => Number(right[1]?.saved_at || 0) - Number(left[1]?.saved_at || 0))
      .slice(0, 8));
    localStorage.setItem(DASHBOARD_SNAPSHOT_KEY, JSON.stringify(trimmed));
  } catch {
    // Storage can be unavailable or full; live data remains the source of truth.
  }
}

function ensureEcharts() {
  if (window.echarts) return Promise.resolve(window.echarts);
  if (echartsLoadPromise) return echartsLoadPromise;
  echartsLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/assets/echarts.min.js";
    script.dataset.stjEcharts = "lazy";
    script.onload = () => resolve(window.echarts);
    script.onerror = () => {
      echartsLoadPromise = null;
      reject(new Error("财报图表组件加载失败"));
    };
    document.head.appendChild(script);
  });
  return echartsLoadPromise;
}

document.addEventListener("alpine:init", () => {
  const AI_STORAGE_KEY = "stj.ai.config.v1";
  const BACKEND_STORAGE_KEY = "stj.backend.access_key.v1";
  const fallbackCatalog = {
    storage_key: AI_STORAGE_KEY,
    cli: [
      { id: "claude-code", name: "Claude Code", provider: "cli-claude", kind: "claude", description: "用本机 Claude 订阅", available: null },
      { id: "qwen-code", name: "Qwen Code", provider: "cli-qwen", kind: "qwen", description: "通义 Qwen Code 订阅", available: null },
      { id: "deepseek-cli", name: "DeepSeek CLI", provider: "cli-deepseek", kind: "deepseek", description: "DeepSeek 本机 CLI 订阅", available: null },
      { id: "codex", name: "Codex", provider: "cli-codex", kind: "codex", description: "OpenAI Codex 订阅", available: null },
      { id: "opencode", name: "OpenCode", provider: "cli-opencode", kind: "opencode", description: "即将支持", coming_soon: true, available: false },
      { id: "cursor-agent", name: "Cursor Agent", provider: "cli-cursor", kind: "cursor", description: "即将支持", coming_soon: true, available: false },
      { id: "kimi", name: "Kimi", provider: "cli-kimi", kind: "kimi", description: "即将支持", coming_soon: true, available: false },
    ],
    api: [
      { id: "deepseek-v4-flash", name: "DeepSeek V4 Flash", provider: "deepseek", base_url: "https://api.deepseek.com" },
      { id: "deepseek-v4-pro", name: "DeepSeek V4 Pro", provider: "deepseek", base_url: "https://api.deepseek.com" },
      { id: "deepseek-ai/DeepSeek-V3", name: "SiliconFlow · DeepSeek V3", provider: "silicon", base_url: "https://api.siliconflow.cn/v1" },
      { id: "gpt-4o", name: "OpenAI GPT-4o", provider: "openai", base_url: "https://api.openai.com/v1" },
      { id: "MiniMax-M2", name: "MiniMax M2", provider: "minimax", base_url: "https://api.minimaxi.com/v1" },
      { id: "doubao-pro", name: "豆包 Pro", provider: "openai-compatible", base_url: "" },
      { id: "openai/gpt-4o", name: "OpenRouter · GPT-4o", provider: "openrouter", base_url: "https://openrouter.ai/api/v1" },
      { id: "llama-3.3-70b-versatile", name: "Groq · Llama 3.3 70B", provider: "groq", base_url: "https://api.groq.com/openai/v1" },
      { id: "meta-llama/Llama-3.3-70B-Instruct-Turbo", name: "Together · Llama 3.3 70B", provider: "together", base_url: "https://api.together.xyz/v1" },
      { id: "mimo-v2.5-pro", name: "MiMo V2.5 Pro", provider: "mimo", base_url: "" },
      { id: "custom", name: "其它 OpenAI 兼容", provider: "openai-compatible", base_url: "" },
    ],
  };

  const defaultAiDraft = () => ({
    mode: "cli",
    provider: "cli-codex",
    model: "codex",
    base_url: "",
    api_key: "",
    default_context: { portfolio: true, watchlist: true, notes: true, news: true, sector: true },
    answer_style: { conclusion: true, evidence: true, counter_evidence: true, discipline: true },
    ui_options: { show_sources: true, allow_research_save: true },
  });

  const initialAssistant = () => ({
    id: crypto.randomUUID(),
    role: "assistant",
    content: "我会结合当前页面、STJ 本地台账和可追溯数据回答。API 模式可以继续调用只读数据工具；CLI 模式会预先装载同一份上下文。",
    tools: [],
    streaming: false,
    saved: false,
    sources: [],
  });

  Alpine.data("dashboardApp", () => ({
    navigation: [
      { id: "positions", label: "持仓", icon: "▦" },
      { id: "watch", label: "关注", icon: "◇" },
      { id: "daily", label: "每日复盘", icon: "◔" },
      { id: "intel", label: "资讯雷达", icon: "⌁" },
      { id: "sectors", label: "板块知识", icon: "⌘" },
      { id: "research", label: "研究记录", icon: "▤" },
    ],
    page: "positions",
    menuOpen: false,
    searchCode: "",
    lastUpdated: null,
    globalError: "",
    toast: "",
    toastTimer: null,
    loading: { portfolio: false, watchlist: false, daily: false, intel: false, sectors: false, research: false, stock: false, financials: false, flow: false, options: false, stockIntel: false },
    errors: { portfolio: [], watchlist: [], daily: [], intel: [], research: [] },
    meta: { portfolio: null, watchlist: null, daily: null, intel: null, research: null },
    portfolio: null,
    watchlist: null,
    daily: null,
    dailyMarket: "A",
    intel: null,
    intelFilter: { scope: "all", market: "all", kind: "all" },
    intelScopes: [
      { id: "all", label: "全部" }, { id: "holding", label: "持仓" },
      { id: "watch", label: "关注" }, { id: "investment", label: "Investment News" },
    ],
    researchRecords: [],
    researchExpanded: {},
    sectors: [],
    selectedSector: null,
    showArchivedSectors: false,
    sectorModal: false,
    sectorEditModal: false,
    sectorNodeModal: false,
    sectorKnowledgeModal: false,
    editingNodeId: null,
    editingKnowledgeId: null,
    sectorForms: {
      create: { name: "", summary: "", tags: "" },
      edit: { name: "", summary: "" },
      tag: "",
      node: { name: "", stage: "midstream", description: "", bottleneck: false },
      edge: { from_node_id: "", to_node_id: "", relation: "supplies" },
      symbol: "",
      symbolRole: "",
      knowledge: { kind: "core", title: "", content: "", source_url: "", as_of: "" },
    },
    sectorStages: [
      { id: "upstream", label: "上游" }, { id: "midstream", label: "中游" }, { id: "downstream", label: "下游" },
    ],
    sectorPrompts: ["按七维框架拆解", "有什么风险信号", "这个板块的产业链地图", "哪个环节卡脖子"],
    stockOpen: false,
    selectedCode: "",
    stock: null,
    stockTab: "overview",
    stockTabs: [
      { id: "overview", label: "概览" }, { id: "kline", label: "K线·记录" },
      { id: "financials", label: "财报" }, { id: "flow", label: "资金面" },
      { id: "options", label: "期权" }, { id: "intel", label: "资讯·研报" },
    ],
    financialPeriod: "annual",
    financials: null,
    flow: null,
    options: null,
    stockIntel: null,
    financeChartInstance: null,
    valuationMetrics: [
      { key: "pe_ttm", label: "PE TTM", format: "number" }, { key: "pe_forward", label: "前向 PE", format: "number" },
      { key: "pb", label: "PB", format: "number" }, { key: "ps_ttm", label: "PS TTM", format: "number" },
      { key: "enterprise_to_ebitda", label: "EV/EBITDA", format: "number" }, { key: "historical_percentile", label: "历史分位", format: "percent" },
    ],
    aiCatalog: fallbackCatalog,
    aiConfig: null,
    aiDraft: defaultAiDraft(),
    apiPreset: "deepseek-v4-flash",
    aiSaveMessage: "",
    backendAccessKey: "",
    backendDraft: "",
    backendSaveMessage: "",
    aiTest: { loading: false, result: "", ok: false },
    aiOpen: false,
    aiInput: "",
    aiMessages: [initialAssistant()],
    aiStreaming: false,
    aiAbort: null,
    aiError: "",
    aiLastQuestion: "",
    aiQuickSettingsOpen: false,
    inlineAi: {
      daily: { loading: false, content: "", error: "", question: "", saved: false, sources: [] },
      intel: { loading: false, content: "", error: "", question: "", saved: false, sources: [], bulkRunning: false, done: 0, total: 0 },
    },
    inlineAiControllers: { daily: null, intel: null },
    snapshotRefreshTimers: {},

    async init() {
      const params = new URLSearchParams(location.search);
      const requestedPage = params.get("page");
      if ([...this.navigation.map(item => item.id), "ai-settings"].includes(requestedPage)) this.page = requestedPage;
      this.loadAiConfig();
      this.restoreSnapshotForPage(this.page);
      void this.loadAiCapabilities();
      window.addEventListener("popstate", () => {
        const value = new URLSearchParams(location.search).get("page") || "positions";
        if ([...this.navigation.map(item => item.id), "ai-settings"].includes(value)) {
          this.page = value;
          this.loadPage(value);
        }
      });
      await this.loadPage(this.page);
      const code = params.get("code");
      if (code) this.openStock(code, false);
    },

    get pageTitle() {
      return ({ positions: "持仓", watch: "关注", daily: "每日复盘", intel: "资讯雷达", sectors: "板块知识", research: "研究记录", "ai-settings": "问 AI 设置" })[this.page] || "STJ";
    },
    get currentLoading() { return Boolean(this.loading[({ positions: "portfolio", watch: "watchlist" })[this.page] || this.page]); },
    get lastUpdatedLabel() { return this.lastUpdated ? new Date(this.lastUpdated).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "等待同步"; },
    get aiConfigured() {
      if (!this.aiConfig?.model) return false;
      if (this.aiConfig.mode === "cli") {
        const model = this.aiCatalog.cli.find(item => item.id === this.aiConfig.model);
        return !model || (!model.coming_soon && model.available !== false);
      }
      return Boolean(this.aiConfig.base_url && this.aiConfig.api_key);
    },
    get activeAiName() {
      return this.aiNameFor(this.aiConfig);
    },
    get activeAiDescription() {
      if (!this.aiConfig) return "选择订阅 CLI 或自带 API 后，全站 Ask AI 才会启用。";
      return this.aiConfig.mode === "cli"
        ? `${this.aiConfig.provider} · 复用本机登录态 · 服务端预装上下文`
        : `${this.aiConfig.provider} · ${this.aiConfig.base_url} · 流式 + 只读数据工具`;
    },
    get contextLabel() {
      if (this.stockOpen && this.selectedCode) return `个股 ${this.selectedCode}`;
      if (this.page === "sectors" && this.selectedSector) return `板块 ${this.selectedSector.name}`;
      return this.pageTitle;
    },
    get currentAiSuggestions() {
      if (this.stockOpen) return ["用五维框架分析这只股票", "当前估值定价了什么", "有哪些逻辑证伪与风险信号", "结合我的持仓给出跟踪清单"];
      return ({
        positions: ["分析组合集中度和结构风险", "哪些持仓最需要验证反证", "总结组合的关键变化", "列出未来一周跟踪清单"],
        watch: ["按估值与催化剂给关注标的分组", "哪些关注标的风险上升", "比较关注标的的等待条件", "找出信息缺口最大的标的"],
        daily: ["生成今日市场复盘", "谁在领涨和拖累市场", "资金轮动有哪些异常", "明天最值得跟踪什么"],
        intel: ["提炼当前资讯的组合影响", "哪些消息是风险信号", "区分新闻事实与市场解读", "按持仓相关度排列事件"],
        sectors: this.sectorPrompts,
        research: ["总结最近研究记录的共识", "找出重复出现的风险", "哪些判断需要更新", "整理下一步验证清单"],
        "ai-settings": ["解释 CLI 和 API 的能力差异", "AI 数据工具能查什么", "怎样配置最省成本", "如何保护 API Key"],
      })[this.page] || ["分析当前页面最重要的变化", "有哪些风险信号被忽略了", "结合我的仓位列出等待条件", "用证据反驳当前投资逻辑"];
    },
    get contextPreview() {
      if (this.stockOpen) return [
        { label: "标的", value: this.selectedCode },
        { label: "持仓", value: this.stock?.holding_summary?.quantity == null ? "未持仓" : `${this.number(this.stock.holding_summary.quantity, 0)} 股` },
        { label: "笔记/交易", value: `${this.stock?.notes?.length || 0} / ${this.stock?.trades?.length || 0}` },
      ];
      if (this.page === "positions") return [
        { label: "持仓", value: `${this.portfolio?.summary?.position_count || 0} 个` },
        { label: "总市值", value: this.moneyCny(this.portfolio?.summary?.total_market_value_cny_est) },
        { label: "提醒", value: `${this.portfolio?.summary?.alert_count || 0} 条` },
      ];
      if (this.page === "watch") return [{ label: "关注", value: `${this.watchlist?.summary?.count || 0} 个` }, { label: "含笔记", value: "是" }];
      if (this.page === "daily") return [{ label: "市场", value: this.marketName(this.dailyMarket) }, { label: "指数", value: `${this.daily?.indices?.length || 0} 个` }, { label: "轮动", value: `${this.daily?.rotation?.length || 0} 项` }];
      if (this.page === "intel") return [{ label: "范围", value: this.intelScopes.find(item => item.id === this.intelFilter.scope)?.label || "全部" }, { label: "资讯", value: `${this.intel?.items?.length || 0} 条` }];
      if (this.page === "sectors") return [{ label: "板块", value: this.selectedSector?.name || "未选择" }, { label: "知识", value: `${this.selectedSector?.knowledge?.length || 0} 条` }, { label: "节点", value: `${this.selectedSector?.nodes?.length || 0} 个` }];
      if (this.page === "research") return [{ label: "已保存", value: `${this.researchRecords.length} 条` }, { label: "用途", value: "复盘与追踪" }];
      return [{ label: "页面", value: this.pageTitle }, { label: "配置", value: this.activeAiName }];
    },
    get mountedContextChips() {
      const labels = { portfolio: "持仓", watchlist: "关注", notes: "笔记", news: "新闻/研报", sector: "板块知识" };
      const enabled = Object.entries(this.aiConfig?.default_context || defaultAiDraft().default_context).filter(([, value]) => value).map(([key]) => labels[key]);
      const modeLabel = !this.aiConfig ? "等待接入模型" : this.aiConfig.mode === "api" ? "只读数据工具" : "服务端预装数据";
      return [this.contextLabel, ...enabled, modeLabel].filter(Boolean);
    },
    get chartUrl() { return this.selectedCode ? `/chart?code=${encodeURIComponent(this.selectedCode)}&period=1y` : "about:blank"; },

    badgeFor(page) {
      if (page === "positions") return this.portfolio?.summary?.position_count || "";
      if (page === "watch") return this.watchlist?.summary?.count || "";
      if (page === "intel") return this.intel?.items?.length || "";
      if (page === "research") return this.researchRecords.length || "";
      return "";
    },
    navigate(page) {
      this.page = page;
      this.menuOpen = false;
      if (this.stockOpen) {
        this.stockOpen = false;
        if (this.financeChartInstance) { this.financeChartInstance.dispose(); this.financeChartInstance = null; }
      }
      const url = new URL(location.href);
      url.searchParams.set("page", page);
      url.searchParams.delete("code");
      history.pushState({}, "", url);
      this.restoreSnapshotForPage(page);
      this.loadPage(page);
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    async loadPage(page, force = false) {
      if (page === "positions") return this.loadPortfolio(force);
      if (page === "watch") return this.loadWatchlist(force);
      if (page === "daily") return this.loadDaily(force);
      if (page === "intel") return this.loadIntel(force);
      if (page === "sectors") return this.loadSectors();
      if (page === "research") return this.loadResearchRecords();
    },
    reloadCurrent() { return this.loadPage(this.page, true); },

    snapshotKey(page = this.page) {
      if (page === "positions") return "portfolio";
      if (page === "watch") return "watchlist";
      if (page === "daily") return `daily:${this.dailyMarket}`;
      if (page === "intel") return `intel:${new URLSearchParams(this.intelFilter).toString()}`;
      return "";
    },
    restoreSnapshotForPage(page = this.page) {
      const key = this.snapshotKey(page);
      const response = key ? loadDashboardSnapshot(key) : null;
      if (!response) return false;
      const target = ({ positions: "portfolio", watch: "watchlist", daily: "daily", intel: "intel" })[page];
      if (!target) return false;
      this.applyResponse(target, response);
      return true;
    },

    authHeaders() {
      return this.backendAccessKey ? { Authorization: `Bearer ${this.backendAccessKey}` } : {};
    },
    async api(path, options = {}) {
      const headers = { Accept: "application/json", ...this.authHeaders(), ...(options.headers || {}) };
      if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
      const response = await fetch(path, { ...options, headers });
      let payload;
      try { payload = await response.json(); } catch { payload = null; }
      if (!response.ok || !payload) {
        const message = payload?.errors?.[0]?.message || payload?.meta?.warnings?.[0] || `HTTP ${response.status}`;
        const error = new Error(message);
        error.status = response.status;
        throw error;
      }
      return payload;
    },
    applyResponse(key, response) {
      this[key] = response.data;
      this.meta[key] = response.meta;
      this.errors[key] = response.errors || [];
      this.lastUpdated = response.meta?.generated_at || new Date().toISOString();
    },
    scheduleSnapshotRefresh(key, response, reload) {
      if (this.snapshotRefreshTimers[key]) clearTimeout(this.snapshotRefreshTimers[key]);
      delete this.snapshotRefreshTimers[key];
      if (!response.meta?.response_cache?.stale) return;
      this.snapshotRefreshTimers[key] = setTimeout(() => {
        delete this.snapshotRefreshTimers[key];
        void reload();
      }, 2500);
    },
    async loadPortfolio(force = false) {
      this.loading.portfolio = force || !this.portfolio;
      try {
        const response = await this.api(`/api/portfolio${force ? "?refresh=1" : ""}`);
        this.applyResponse("portfolio", response);
        saveDashboardSnapshot("portfolio", response);
        this.scheduleSnapshotRefresh("portfolio", response, () => this.loadPortfolio());
      }
      catch (error) { this.globalError = `持仓加载失败：${error.message}`; }
      finally { this.loading.portfolio = false; }
    },
    async loadWatchlist(force = false) {
      this.loading.watchlist = force || !this.watchlist;
      try {
        const response = await this.api(`/api/watchlist${force ? "?refresh=1" : ""}`);
        this.applyResponse("watchlist", response);
        saveDashboardSnapshot("watchlist", response);
        this.scheduleSnapshotRefresh("watchlist", response, () => this.loadWatchlist());
      }
      catch (error) { this.globalError = `关注列表加载失败：${error.message}`; }
      finally { this.loading.watchlist = false; }
    },
    async setDailyMarket(market) { this.dailyMarket = market; this.restoreSnapshotForPage("daily"); await this.loadDaily(); },
    async loadDaily(force = false) {
      const market = this.dailyMarket;
      this.loading.daily = force || !this.daily;
      try {
        const response = await this.api(`/api/daily-review?market=${encodeURIComponent(market)}${force ? "&refresh=1" : ""}`);
        if (this.dailyMarket !== market) return;
        this.applyResponse("daily", response);
        saveDashboardSnapshot(`daily:${market}`, response);
        this.scheduleSnapshotRefresh(`daily:${market}`, response, () => this.dailyMarket === market && this.loadDaily());
      }
      catch (error) { this.globalError = `每日复盘加载失败：${error.message}`; }
      finally { this.loading.daily = false; }
    },
    async loadIntel(force = false) {
      this.loading.intel = force || !this.intel;
      const query = new URLSearchParams(this.intelFilter);
      if (force) query.set("refresh", "1");
      try {
        const response = await this.api(`/api/intel?${query}`);
        this.applyResponse("intel", response);
        const snapshotKey = `intel:${new URLSearchParams(this.intelFilter).toString()}`;
        saveDashboardSnapshot(snapshotKey, response);
        this.scheduleSnapshotRefresh("intel", response, () => this.loadIntel());
      }
      catch (error) { this.globalError = `资讯雷达加载失败：${error.message}`; }
      finally { this.loading.intel = false; }
    },
    async loadResearchRecords() {
      this.loading.research = true;
      try {
        const response = await this.api("/api/research-records");
        this.researchRecords = response.data?.records || [];
        this.meta.research = response.meta;
        this.errors.research = response.errors || [];
        this.lastUpdated = response.meta?.generated_at || new Date().toISOString();
      } catch (error) { this.globalError = `研究记录加载失败：${error.message}`; }
      finally { this.loading.research = false; }
    },
    toggleResearchRecord(id) {
      this.researchExpanded[id] = !this.researchExpanded[id];
    },
    async deleteResearchRecord(id) {
      if (!confirm("删除这条研究记录？此操作不可撤销。")) return;
      try {
        await this.api(`/api/research-records/${Number(id)}`, { method: "DELETE", body: "{}" });
        await this.loadResearchRecords();
        this.showToast("研究记录已删除");
      } catch (error) { this.showToast(`删除失败：${error.message}`); }
    },
    async clearResearchRecords() {
      if (!this.researchRecords.length || !confirm(`清空全部 ${this.researchRecords.length} 条研究记录？此操作不可撤销。`)) return;
      try {
        await this.api("/api/research-records", { method: "DELETE", body: JSON.stringify({ all: true }) });
        this.researchExpanded = {};
        await this.loadResearchRecords();
        this.showToast("研究记录已清空");
      } catch (error) { this.showToast(`清空失败：${error.message}`); }
    },
    openResearchTarget(record) {
      if (record?.ts_code) return this.openStock(record.ts_code);
      if (record?.sector_id) {
        this.navigate("sectors");
        this.$nextTick(() => this.selectSector(record.sector_id));
      }
    },

    normalizeSearchCode(value) {
      let code = String(value || "").trim().toUpperCase();
      if (!code) return "";
      if (!code.includes(".")) {
        if (/^[A-Z^][A-Z0-9^-]*$/.test(code)) code += ".US";
        else if (/^\d{6}$/.test(code)) code += code.startsWith("6") ? ".SH" : ".SZ";
        else if (/^\d{4,5}$/.test(code)) code = `${code.padStart(4, "0")}.HK`;
      }
      return code;
    },
    async openStock(rawCode, updateUrl = true) {
      const code = this.normalizeSearchCode(rawCode);
      if (!/^[A-Z0-9_-]+\.(US|HK|SH|SZ)$/.test(code)) {
        this.showToast("请输入统一代码，如 NVDA.US、0700.HK、600519.SH");
        return;
      }
      this.selectedCode = code;
      this.searchCode = code;
      this.stockOpen = true;
      this.stockTab = "overview";
      this.stock = this.financials = this.flow = this.options = this.stockIntel = null;
      if (updateUrl) {
        const url = new URL(location.href);
        url.searchParams.set("code", code);
        history.pushState({}, "", url);
      }
      this.loading.stock = true;
      try { this.stock = (await this.api(`/api/stock/context?code=${encodeURIComponent(code)}`)).data; }
      catch (error) { this.globalError = `个股详情加载失败：${error.message}`; }
      finally { this.loading.stock = false; }
    },
    closeStock() {
      this.stockOpen = false;
      const url = new URL(location.href);
      url.searchParams.delete("code");
      history.replaceState({}, "", url);
      if (this.financeChartInstance) { this.financeChartInstance.dispose(); this.financeChartInstance = null; }
    },
    async setStockTab(tab) {
      this.stockTab = tab;
      if (tab === "financials" && !this.financials) await this.loadFinancials();
      if (tab === "flow" && !this.flow) await this.loadFlow();
      if (tab === "options" && !this.options) await this.loadOptions();
      if (tab === "intel" && !this.stockIntel) await this.loadStockIntel();
    },
    async setFinancialPeriod(period) { this.financialPeriod = period; await this.loadFinancials(); },
    async loadFinancials() {
      this.loading.financials = true;
      try {
        this.financials = (await this.api(`/api/stock/financials?code=${encodeURIComponent(this.selectedCode)}&period=${this.financialPeriod}`)).data;
        await this.$nextTick();
        await ensureEcharts();
        this.renderFinanceChart();
      } catch (error) { this.globalError = `财报加载失败：${error.message}`; }
      finally { this.loading.financials = false; }
    },
    async loadFlow() {
      this.loading.flow = true;
      try { this.flow = (await this.api(`/api/stock/flow?code=${encodeURIComponent(this.selectedCode)}`)).data; }
      catch (error) { this.globalError = `资金面加载失败：${error.message}`; }
      finally { this.loading.flow = false; }
    },
    async loadOptions() {
      this.loading.options = true;
      try { this.options = (await this.api(`/api/stock/options?code=${encodeURIComponent(this.selectedCode)}`)).data; }
      catch (error) { this.globalError = `期权链加载失败：${error.message}`; }
      finally { this.loading.options = false; }
    },
    async loadStockIntel() {
      this.loading.stockIntel = true;
      try { this.stockIntel = (await this.api(`/api/stock/intel?code=${encodeURIComponent(this.selectedCode)}&kind=all`)).data; }
      catch (error) { this.globalError = `个股资讯加载失败：${error.message}`; }
      finally { this.loading.stockIntel = false; }
    },
    renderFinanceChart() {
      if (!window.echarts || !this.$refs.financeChart || !this.financials?.series?.length) return;
      if (this.financeChartInstance) this.financeChartInstance.dispose();
      this.financeChartInstance = window.echarts.init(this.$refs.financeChart);
      const series = this.financials.series;
      const scale = value => value == null ? null : Number(value) / 1e9;
      this.financeChartInstance.setOption({
        animationDuration: 350,
        color: ["#6575d5", "#d46862", "#4d9d7d"],
        tooltip: { trigger: "axis", valueFormatter: value => value == null ? "—" : `${Number(value).toFixed(2)}B` },
        legend: { top: 12, data: ["营收", "净利润", "自由现金流"] },
        grid: { left: 55, right: 20, top: 55, bottom: 42 },
        xAxis: { type: "category", data: series.map(row => row.period_end), axisLabel: { fontSize: 10 } },
        yAxis: { type: "value", name: `${series.at(-1)?.currency || ""} · 十亿`, nameTextStyle: { fontSize: 9 } },
        series: [
          { name: "营收", type: "bar", data: series.map(row => scale(row.revenue)), barMaxWidth: 24 },
          { name: "净利润", type: "bar", data: series.map(row => scale(row.net_income)), barMaxWidth: 24 },
          { name: "自由现金流", type: "bar", data: series.map(row => scale(row.free_cash_flow)), barMaxWidth: 24 },
        ],
      });
      setTimeout(() => this.financeChartInstance?.resize(), 0);
    },
    latestQualityMetrics() {
      const row = this.financials?.series?.at(-1);
      if (!row) return [];
      return [
        { label: "毛利率", value: this.signedPercent(row.gross_margin, false), note: row.period_end },
        { label: "现金含量", value: row.operating_cash_ratio == null ? "—" : `${this.number(row.operating_cash_ratio, 2)}×`, note: "经营现金流 / 净利润" },
        { label: "研发投入", value: this.compactMoney(row.r_and_d), note: row.currency },
        { label: "EPS", value: this.number(row.eps_actual, 3), note: row.period_type },
        { label: "资产负债率", value: this.signedPercent(row.debt_ratio, false), note: "负债 / 资产" },
        { label: "营运资金", value: this.compactMoney(row.working_capital), note: row.currency },
        { label: "应收", value: this.compactMoney(row.receivables), note: row.currency },
        { label: "库存", value: this.compactMoney(row.inventory), note: row.currency },
      ];
    },

    async loadSectors() {
      this.loading.sectors = true;
      try {
        const response = await this.api(`/api/sectors${this.showArchivedSectors ? "?include_archived=1" : ""}`);
        this.sectors = response.data.sectors || [];
        const id = this.selectedSector?.id;
        this.selectedSector = this.sectors.find(row => row.id === id) || this.sectors[0] || null;
      } catch (error) { this.globalError = `板块知识加载失败：${error.message}`; }
      finally { this.loading.sectors = false; }
    },
    async toggleArchivedSectors() {
      this.showArchivedSectors = !this.showArchivedSectors;
      await this.loadSectors();
    },
    async selectSector(id) {
      try { this.selectedSector = (await this.api(`/api/sectors/${id}`)).data; }
      catch (error) { this.showToast(error.message); }
    },
    async createSector() {
      const tags = this.sectorForms.create.tags.split(/[、,，]/).map(item => item.trim()).filter(Boolean);
      try {
        const response = await this.api("/api/sectors", { method: "POST", body: JSON.stringify({ ...this.sectorForms.create, tags }) });
        this.sectorModal = false;
        this.sectorForms.create = { name: "", summary: "", tags: "" };
        await this.loadSectors();
        await this.selectSector(response.data.id);
        this.showToast("板块知识库已创建");
      } catch (error) { this.showToast(`创建失败：${error.message}`); }
    },
    async archiveSelectedSector() {
      if (!this.selectedSector || !confirm(`归档「${this.selectedSector.name}」？数据不会删除。`)) return;
      try {
        await this.api(`/api/sectors/${this.selectedSector.id}`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: "{}" });
        this.selectedSector = null;
        await this.loadSectors();
        this.showToast("板块已归档");
      } catch (error) { this.showToast(error.message); }
    },
    openSectorEdit() {
      if (!this.selectedSector) return;
      this.sectorForms.edit = { name: this.selectedSector.name || "", summary: this.selectedSector.summary || "" };
      this.sectorEditModal = true;
    },
    async updateSelectedSector() {
      if (!this.selectedSector) return;
      try {
        await this.api(`/api/sectors/${this.selectedSector.id}`, { method: "PATCH", body: JSON.stringify(this.sectorForms.edit) });
        this.sectorEditModal = false;
        await this.loadSectors();
        await this.selectSector(this.selectedSector.id);
        this.showToast("板块资料已更新");
      } catch (error) { this.showToast(error.message); }
    },
    async restoreSelectedSector() {
      if (!this.selectedSector) return;
      try {
        await this.api(`/api/sectors/${this.selectedSector.id}`, { method: "PATCH", body: JSON.stringify({ status: "active" }) });
        await this.loadSectors();
        await this.selectSector(this.selectedSector?.id);
        this.showToast("板块已恢复");
      } catch (error) { this.showToast(error.message); }
    },
    sectorNodes(stage) { return (this.selectedSector?.nodes || []).filter(node => node.stage === stage); },
    async addSectorTag() {
      const name = this.sectorForms.tag.trim();
      if (!name || !this.selectedSector) return;
      await this.sectorMutation("tags", "POST", { name });
      this.sectorForms.tag = "";
    },
    openSectorNode(node = null, stage = "midstream") {
      this.editingNodeId = node?.id || null;
      this.sectorForms.node = node ? {
        name: node.name || "",
        stage: node.stage || stage,
        description: node.description || "",
        bottleneck: Boolean(node.bottleneck),
      } : { name: "", stage, description: "", bottleneck: false };
      this.sectorNodeModal = true;
    },
    async addSectorNode() {
      if (!this.selectedSector) return;
      await this.sectorMutation("nodes", this.editingNodeId ? "PATCH" : "POST", this.sectorForms.node, this.editingNodeId || "");
      this.sectorForms.node = { name: "", stage: "midstream", description: "", bottleneck: false };
      this.editingNodeId = null;
      this.sectorNodeModal = false;
    },
    async addSectorEdge() {
      if (!this.selectedSector || !this.sectorForms.edge.from_node_id || !this.sectorForms.edge.to_node_id) return;
      await this.sectorMutation("edges", "POST", {
        from_node_id: Number(this.sectorForms.edge.from_node_id),
        to_node_id: Number(this.sectorForms.edge.to_node_id),
        relation: this.sectorForms.edge.relation || "supplies",
      });
      this.sectorForms.edge = { from_node_id: "", to_node_id: "", relation: "supplies" };
    },
    openSectorKnowledge(item = null) {
      this.editingKnowledgeId = item?.id || null;
      this.sectorForms.knowledge = item ? {
        kind: item.kind || "core",
        title: item.title || "",
        content: item.content || "",
        source_url: item.source_url || "",
        as_of: item.as_of || "",
      } : { kind: "core", title: "", content: "", source_url: "", as_of: "" };
      this.sectorKnowledgeModal = true;
    },
    async addSectorKnowledge() {
      if (!this.selectedSector) return;
      await this.sectorMutation("knowledge", this.editingKnowledgeId ? "PATCH" : "POST", this.sectorForms.knowledge, this.editingKnowledgeId || "");
      this.sectorForms.knowledge = { kind: "core", title: "", content: "", source_url: "", as_of: "" };
      this.editingKnowledgeId = null;
      this.sectorKnowledgeModal = false;
    },
    async addSectorSymbol() {
      if (!this.selectedSector || !this.sectorForms.symbol.trim()) return;
      await this.sectorMutation("symbols", "POST", { ts_code: this.normalizeSearchCode(this.sectorForms.symbol), role: this.sectorForms.symbolRole });
      this.sectorForms.symbol = this.sectorForms.symbolRole = "";
    },
    async sectorMutation(resource, method, body, itemId = "") {
      try {
        const suffix = itemId === "" ? "" : `/${encodeURIComponent(itemId)}`;
        await this.api(`/api/sectors/${this.selectedSector.id}/${resource}${suffix}`, { method, body: JSON.stringify(body || {}) });
        await this.selectSector(this.selectedSector.id);
      } catch (error) { this.showToast(error.message); }
    },
    deleteSectorResource(resource, id) { return this.sectorMutation(resource, "DELETE", {}, id); },
    deleteSectorSymbol(code) { return this.sectorMutation("symbols", "DELETE", {}, code); },
    edgeLabel(edge) {
      const nodes = Object.fromEntries((this.selectedSector?.nodes || []).map(node => [node.id, node.name]));
      return `${nodes[edge.from_node_id] || edge.from_node_id} → ${nodes[edge.to_node_id] || edge.to_node_id} · ${edge.relation}`;
    },

    aiNameFor(config) {
      if (!config) return "尚未接入 AI";
      const models = config.mode === "cli" ? this.aiCatalog.cli : this.aiCatalog.api;
      return models.find(item => item.id === config.model)?.name || config.model || "未命名模型";
    },

    loadAiConfig() {
      try {
        const parsed = JSON.parse(localStorage.getItem(AI_STORAGE_KEY) || "null");
        const storedBackendKey = localStorage.getItem(BACKEND_STORAGE_KEY) || parsed?.backend_access_key || "";
        this.backendAccessKey = storedBackendKey;
        this.backendDraft = storedBackendKey;
        if (parsed?.backend_access_key && !localStorage.getItem(BACKEND_STORAGE_KEY)) localStorage.setItem(BACKEND_STORAGE_KEY, parsed.backend_access_key);
        if (parsed?.model) {
          const defaults = defaultAiDraft();
          delete parsed.backend_access_key;
          this.aiConfig = {
            ...defaults,
            ...parsed,
            default_context: { ...defaults.default_context, ...(parsed.default_context || {}) },
            answer_style: { ...defaults.answer_style, ...(parsed.answer_style || {}) },
            ui_options: { ...defaults.ui_options, ...(parsed.ui_options || {}) },
          };
          localStorage.setItem(AI_STORAGE_KEY, JSON.stringify(this.aiConfig));
        } else this.aiConfig = null;
      } catch {
        this.aiConfig = null;
        this.backendAccessKey = localStorage.getItem(BACKEND_STORAGE_KEY) || "";
        this.backendDraft = this.backendAccessKey;
      }
      this.aiDraft = this.aiConfig ? JSON.parse(JSON.stringify(this.aiConfig)) : defaultAiDraft();
      if (this.aiDraft.mode === "api") this.apiPreset = this.aiCatalog.api.find(item => item.id === this.aiDraft.model)?.id || "custom";
    },
    async loadAiCapabilities() {
      try {
        const response = await this.api("/api/ai/capabilities");
        this.aiCatalog = response.data;
      } catch {
        this.aiCatalog = fallbackCatalog;
      }
      if (this.aiDraft.mode === "api") this.apiPreset = this.aiCatalog.api.find(item => item.id === this.aiDraft.model)?.id || "custom";
    },
    selectCliModel(model) {
      if (model.coming_soon || model.available === false) return;
      this.aiDraft.mode = "cli";
      this.aiDraft.provider = model.provider;
      this.aiDraft.model = model.id;
      this.aiDraft.base_url = "";
      this.aiDraft.api_key = "";
    },
    setAiMode(mode) {
      this.aiDraft.mode = mode;
      if (mode === "api" && (!this.aiDraft.base_url || String(this.aiDraft.provider || "").startsWith("cli-"))) {
        this.selectApiPreset();
      }
      if (mode === "cli" && !String(this.aiDraft.provider || "").startsWith("cli-")) {
        const model = this.aiCatalog.cli.find(item => !item.coming_soon && item.available !== false);
        if (model) this.selectCliModel(model);
      }
    },
    selectApiPreset() {
      const model = this.aiCatalog.api.find(item => item.id === this.apiPreset);
      if (!model) return;
      this.aiDraft.mode = "api";
      this.aiDraft.provider = model.provider;
      this.aiDraft.model = model.id === "doubao-pro" ? "" : model.id === "custom" ? "" : model.id;
      this.aiDraft.base_url = model.base_url || "";
    },
    saveAiConfig() {
      const draft = JSON.parse(JSON.stringify(this.aiDraft));
      if (draft.mode === "cli") {
        const model = this.aiCatalog.cli.find(item => item.id === draft.model && !item.coming_soon && item.available !== false);
        if (!model) return this.showToast("请选择可用的订阅 CLI");
        draft.provider = model.provider;
        draft.api_key = "";
        draft.base_url = "";
      } else if (!draft.base_url.trim() || !draft.model.trim() || !draft.api_key.trim()) {
        return this.showToast("请填完 Base URL、Model 和 API Key");
      }
      localStorage.setItem(AI_STORAGE_KEY, JSON.stringify(draft));
      this.aiConfig = draft;
      this.aiDraft = JSON.parse(JSON.stringify(draft));
      this.aiSaveMessage = "已保存到当前浏览器，全站生效";
      this.showToast("AI 配置已保存");
    },
    saveBackendAccessKey() {
      const value = String(this.backendDraft || "").trim();
      if (value) localStorage.setItem(BACKEND_STORAGE_KEY, value);
      else localStorage.removeItem(BACKEND_STORAGE_KEY);
      this.backendAccessKey = value;
      this.backendSaveMessage = value ? "后端访问密钥已单独保存" : "后端访问密钥已清除";
      this.showToast(this.backendSaveMessage);
    },
    persistAiPreferences() {
      if (!this.aiConfig) return;
      localStorage.setItem(AI_STORAGE_KEY, JSON.stringify(this.aiConfig));
      this.aiDraft.default_context = { ...this.aiConfig.default_context };
      this.aiDraft.answer_style = { ...this.aiConfig.answer_style };
      this.aiDraft.ui_options = { ...this.aiConfig.ui_options };
    },
    clearAiConfig() {
      localStorage.removeItem(AI_STORAGE_KEY);
      this.aiConfig = null;
      this.aiDraft = defaultAiDraft();
      this.aiSaveMessage = "配置已清除";
      this.newAiConversation();
    },
    async testAiConfig() {
      if (this.aiTest.loading) return;
      const draft = JSON.parse(JSON.stringify(this.aiDraft));
      if (draft.mode === "cli") {
        const model = this.aiCatalog.cli.find(item => item.id === draft.model && !item.coming_soon && item.available !== false);
        if (!model) return this.showToast("请选择本机可用的订阅 CLI");
        draft.provider = model.provider;
      } else if (!draft.base_url?.trim() || !draft.model?.trim() || !draft.api_key?.trim()) {
        return this.showToast("请先填完 API 配置");
      }
      this.aiTest = { loading: true, result: "", ok: false };
      const controller = new AbortController();
      try {
        await this.streamAi(
          [{ role: "user", content: "这是连接测试。请只回复：连接成功" }],
          event => {
            if (event.type === "delta") this.aiTest.result += event.text || "";
            if (event.type === "error") throw new Error(event.message || "连接测试失败");
          },
          controller,
          { page: "ai-settings", include: { portfolio: false, watchlist: false, notes: false, news: false, sector: false } },
          draft,
        );
        this.aiTest.ok = true;
        if (!this.aiTest.result) this.aiTest.result = "连接成功";
      } catch (error) {
        this.aiTest.ok = false;
        this.aiTest.result = `连接失败：${error.message}`;
      } finally { this.aiTest.loading = false; }
    },
    currentContext(override = null) {
      let context;
      if (override) context = { ...override };
      else if (this.stockOpen && this.selectedCode) context = { page: "stock", ts_code: this.selectedCode };
      else if (this.page === "sectors") context = { page: "sectors", sector_id: this.selectedSector?.id || null };
      else if (this.page === "daily") context = { page: "daily", market: this.dailyMarket };
      else if (this.page === "intel") context = { page: "intel", ...this.intelFilter };
      else context = { page: this.page };
      const defaults = defaultAiDraft();
      context.include = { ...defaults.default_context, ...(this.aiConfig?.default_context || {}), ...(context.include || {}) };
      context.answer_style = { ...defaults.answer_style, ...(this.aiConfig?.answer_style || {}), ...(context.answer_style || {}) };
      return context;
    },
    openAi(prompt = "") {
      this.aiOpen = true;
      if (prompt) this.aiInput = prompt;
      this.$nextTick(() => this.scrollAi());
    },
    closeAi() {
      if (this.aiStreaming) this.stopAi();
      this.aiOpen = false;
      this.aiQuickSettingsOpen = false;
    },
    closeTopLayer() {
      if (this.sectorModal) this.sectorModal = false;
      else if (this.sectorEditModal) this.sectorEditModal = false;
      else if (this.sectorNodeModal) this.sectorNodeModal = false;
      else if (this.sectorKnowledgeModal) this.sectorKnowledgeModal = false;
      else if (this.aiOpen) this.closeAi();
      else if (this.stockOpen) this.closeStock();
      else this.menuOpen = false;
    },
    newAiConversation() {
      this.stopAi();
      this.aiMessages = [initialAssistant()];
      this.aiInput = "";
      this.aiError = "";
      this.aiLastQuestion = "";
    },
    scrollAi() { const box = this.$refs.aiMessages; if (box) box.scrollTop = box.scrollHeight; },
    stopAi() { this.aiAbort?.abort(); this.aiAbort = null; this.aiStreaming = false; },
    async streamAi(messages, onEvent, controller, contextOverride = null, configOverride = null) {
      const config = configOverride || this.aiConfig;
      if (!config) throw new Error("尚未配置 AI");
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson", ...this.authHeaders() },
        body: JSON.stringify({
          messages,
          context: this.currentContext(contextOverride),
          llm: {
            mode: config.mode,
            provider: config.provider,
            baseURL: config.base_url,
            apiKey: config.api_key,
            model: config.model,
          },
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        let body = null;
        try { body = await response.json(); } catch { /* ignored */ }
        throw new Error(body?.errors?.[0]?.message || body?.meta?.warnings?.[0] || `HTTP ${response.status}`);
      }
      if (!response.body) throw new Error("后端没有返回响应流");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const consume = raw => {
        if (!raw.trim()) return;
        let event;
        try { event = JSON.parse(raw); } catch { return; }
        onEvent(event);
      };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        lines.forEach(consume);
      }
      buffer += decoder.decode();
      consume(buffer);
    },
    async sendAi(questionOverride = "", appendUser = true) {
      const question = String(questionOverride || this.aiInput || "").trim();
      if (!question || this.aiStreaming || !this.aiConfigured) return;
      const requestConfig = JSON.parse(JSON.stringify(this.aiConfig));
      const assistantId = crypto.randomUUID();
      const assistant = {
        id: assistantId,
        role: "assistant",
        content: "",
        tools: [],
        streaming: true,
        saved: false,
        sources: [],
        runtimeName: this.aiNameFor(requestConfig),
        runtimeMode: requestConfig.mode === "cli" ? "订阅 CLI" : "API",
        statusText: "正在装载本页可信上下文…",
        requestId: "",
      };
      if (appendUser) this.aiMessages.push({ id: crypto.randomUUID(), role: "user", content: question, tools: [], streaming: false, saved: false });
      this.aiMessages.push(assistant);
      const liveAssistant = () => this.aiMessages.find(item => item.id === assistantId);
      this.aiInput = "";
      this.aiError = "";
      this.aiLastQuestion = question;
      this.aiStreaming = true;
      this.aiAbort = new AbortController();
      await this.$nextTick(); this.scrollAi();
      const history = this.aiMessages
        .filter(message => ["user", "assistant"].includes(message.role) && message.content && message.id !== this.aiMessages[0].id)
        .slice(-12)
        .map(message => ({ role: message.role, content: message.content }));
      try {
        await this.streamAi(history, event => {
          const message = liveAssistant();
          if (!message) return;
          if (event.type === "delta") {
            const text = event.text || "";
            if (text) message.content = `${message.content}${text}`;
            message.statusText = `${message.runtimeName} 正在生成回答…`;
          } else if (event.type === "meta") {
            message.context = event.context || null;
            message.requestId = event.request_id || "";
            message.runtimeName = event.model_label || this.aiNameFor({ ...requestConfig, model: event.model });
            message.runtimeMode = event.mode === "cli" ? "订阅 CLI" : "API";
            message.statusText = `${message.runtimeName} 已接收请求，正在分析…`;
          } else if (event.type === "status") {
            message.statusText = event.message || `${message.runtimeName} 正在处理…`;
          } else if (event.type === "tool_start" || event.type === "tool") {
            message.tools.push({ name: event.tool, args: event.args || {}, status: "查询中", sources: [] });
            message.statusText = `${message.runtimeName} 正在查询只读数据…`;
          }
          else if (event.type === "tool_result") {
            const tool = [...message.tools].reverse().find(item => item.name === event.tool && item.status === "查询中");
            if (tool) {
              tool.status = event.error ? "失败" : `${event.count ?? 0} 条${event.truncated ? " · 已截断" : ""}`;
              tool.error = event.error || "";
              tool.sources = event.sources || [];
            }
            message.statusText = `${message.runtimeName} 正在整理结果…`;
          } else if (event.type === "done") {
            message.sources = event.sources || [];
            message.statusText = "回答完成";
          }
          else if (event.type === "error") throw new Error(event.message || "AI 生成失败");
          this.$nextTick(() => this.scrollAi());
        }, this.aiAbort, null, requestConfig);
        const message = liveAssistant();
        if (message) {
          message.streaming = false;
          if (!message.content) message.content = "模型没有返回文本。请检查模型兼容性或重试。";
        }
      } catch (error) {
        const message = liveAssistant();
        if (message) message.streaming = false;
        if (error.name === "AbortError") {
          if (message?.content) message.content = `${message.content}\n\n[已停止]`;
          else this.aiMessages = this.aiMessages.filter(item => item.id !== assistantId);
        } else {
          this.aiError = error.message || "AI 生成失败";
          if (!message?.content) this.aiMessages = this.aiMessages.filter(item => item.id !== assistantId);
        }
      } finally {
        this.aiStreaming = false;
        this.aiAbort = null;
        await this.$nextTick(); this.scrollAi();
      }
    },
    retryAi() {
      if (!this.aiLastQuestion || this.aiStreaming) return;
      this.sendAi(this.aiLastQuestion, false);
    },
    async saveAiMessage(index) {
      const message = this.aiMessages[index];
      if (!message?.content || message.saved) return;
      const question = [...this.aiMessages.slice(0, index)].reverse().find(item => item.role === "user")?.content || "AI 研究记录";
      const context = this.currentContext();
      const payload = {
        scope_type: context.page === "stock" ? "symbol" : context.page === "sectors" ? "sector" : context.page === "positions" ? "portfolio" : "page",
        ts_code: context.ts_code || null,
        sector_id: context.sector_id || null,
        question,
        answer: message.content,
        sources: message.sources || [],
        context_summary: context,
        model_label: this.activeAiName,
      };
      try {
        await this.api("/api/research-records", { method: "POST", body: JSON.stringify(payload) });
        message.saved = true;
        if (this.page === "research") await this.loadResearchRecords();
        this.showToast("已存入研究记录");
      } catch (error) { this.showToast(`保存失败：${error.message}`); }
    },
    async runInlineAi(kind, scope = null) {
      if (!this.aiConfigured) {
        this.showToast("先在问 AI 设置里接入模型");
        this.navigate("ai-settings");
        return;
      }
      const target = this.inlineAi[kind];
      if (!target || target.loading) return;
      this.inlineAiControllers[kind]?.abort();
      const controller = new AbortController();
      this.inlineAiControllers[kind] = controller;
      const question = kind === "daily"
        ? `生成${this.marketName(this.dailyMarket)}当日复盘：结论先行，覆盖大盘、全球市场、市场温度、资金/表现轮动、领涨拖累、风险和下一交易日跟踪项。严格区分真实资金流与 performance_proxy。`
        : `提炼当前${scope ? this.scopeName(scope) : this.intelScopes.find(item => item.id === this.intelFilter.scope)?.label || "全部"}资讯：列出最重要事实、对持仓/关注的影响、风险信号、待验证项和来源日期。`;
      Object.assign(target, { loading: true, content: "", error: "", question, saved: false, sources: [] });
      const context = kind === "daily"
        ? { page: "daily", market: this.dailyMarket }
        : { page: "intel", ...this.intelFilter, ...(scope ? { scope } : {}) };
      try {
        await this.streamAi([{ role: "user", content: question }], event => {
          if (event.type === "delta") target.content += event.text || "";
          else if (event.type === "done") target.sources = event.sources || [];
          else if (event.type === "error") throw new Error(event.message || "AI 生成失败");
        }, controller, context);
        if (!target.content) target.content = "模型没有返回文本。";
      } catch (error) {
        if (error.name !== "AbortError") target.error = error.message || "AI 生成失败";
      } finally {
        target.loading = false;
        this.inlineAiControllers[kind] = null;
      }
    },
    async runIntelBulk() {
      if (!this.aiConfigured) {
        this.showToast("先在问 AI 设置里接入模型");
        this.navigate("ai-settings");
        return;
      }
      const target = this.inlineAi.intel;
      if (target.loading) return;
      const scopes = ["holding", "watch", "investment"];
      const controller = new AbortController();
      this.inlineAiControllers.intel?.abort();
      this.inlineAiControllers.intel = controller;
      Object.assign(target, { loading: true, bulkRunning: true, content: "", error: "", question: "一键提炼持仓、关注与 Investment News 全部要点", saved: false, sources: [], done: 0, total: scopes.length });
      try {
        for (const scope of scopes) {
          const label = this.scopeName(scope);
          const question = `提炼${label}范围内的新闻、研报和披露：只保留重要事实、组合影响、风险信号、待验证项和来源日期。`;
          target.content += `${target.content ? "\n\n" : ""}## ${label}\n`;
          await this.streamAi([{ role: "user", content: question }], event => {
            if (event.type === "delta") target.content += event.text || "";
            else if (event.type === "done") {
              for (const source of event.sources || []) {
                const key = JSON.stringify(source);
                if (!target.sources.some(item => JSON.stringify(item) === key)) target.sources.push(source);
              }
            } else if (event.type === "error") throw new Error(event.message || "AI 生成失败");
          }, controller, { page: "intel", ...this.intelFilter, scope });
          target.done += 1;
        }
      } catch (error) {
        if (error.name !== "AbortError") target.error = error.message || "AI 生成失败";
      } finally {
        target.loading = false;
        target.bulkRunning = false;
        this.inlineAiControllers.intel = null;
      }
    },
    stopInlineAi(kind) { this.inlineAiControllers[kind]?.abort(); },
    async saveInlineAi(kind) {
      const target = this.inlineAi[kind];
      if (!target?.content || target.saved) return;
      const context = kind === "daily" ? this.currentContext({ page: "daily", market: this.dailyMarket }) : this.currentContext({ page: "intel", ...this.intelFilter });
      const payload = {
        scope_type: "page",
        question: target.question || "AI 页面分析",
        answer: target.content,
        sources: target.sources || [],
        context_summary: context,
        model_label: this.activeAiName,
      };
      try {
        await this.api("/api/research-records", { method: "POST", body: JSON.stringify(payload) });
        target.saved = true;
        this.showToast("已存入研究记录");
      } catch (error) { this.showToast(`保存失败：${error.message}`); }
    },

    showToast(message) {
      clearTimeout(this.toastTimer);
      this.toast = String(message || "");
      this.toastTimer = setTimeout(() => { this.toast = ""; }, 2600);
    },
    number(value, digits = 2) {
      const number = Number(value);
      return value == null || !Number.isFinite(number) ? "—" : number.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    },
    percent(value) { return value == null || !Number.isFinite(Number(value)) ? "—" : `${Number(value).toFixed(1)}%`; },
    signedPercent(value, signed = true) {
      const number = Number(value);
      if (value == null || !Number.isFinite(number)) return "—";
      return `${signed && number > 0 ? "+" : ""}${number.toFixed(1)}%`;
    },
    moneyCny(value) { return value == null || !Number.isFinite(Number(value)) ? "—" : `¥${Math.round(Number(value)).toLocaleString("zh-CN")}`; },
    signedMoney(value, currency = "") {
      const number = Number(value);
      if (value == null || !Number.isFinite(number)) return "—";
      const symbol = ({ CNY: "¥", USD: "$", HKD: "HK$" })[currency] || `${currency || ""} `;
      return `${number > 0 ? "+" : ""}${symbol}${Math.round(number).toLocaleString("zh-CN")}`;
    },
    compactMoney(value) {
      const number = Number(value);
      if (value == null || !Number.isFinite(number)) return "—";
      const abs = Math.abs(number);
      const unit = abs >= 1e9 ? [1e9, "B"] : abs >= 1e6 ? [1e6, "M"] : abs >= 1e4 ? [1e4, "万"] : [1, ""];
      return `${number > 0 ? "+" : ""}${(number / unit[0]).toFixed(unit[0] === 1 ? 0 : 2)}${unit[1]}`;
    },
    pnlClass(value) { const number = Number(value); return value == null || !Number.isFinite(number) || number === 0 ? "neutral" : number > 0 ? "profit" : "loss"; },
    initials(asset) { const name = String(asset?.name || asset?.ts_code || "ST"); return name.replace(/[^\p{L}\p{N}]/gu, "").slice(0, 2).toUpperCase() || "ST"; },
    marketName(market) { return ({ A: "A股", HK: "港股", US: "美股" })[market] || "—"; },
    statusLabel(value) { return ({ ok: "已更新", stale: "缓存", unavailable: "未确认" })[value] || value || "—"; },
    kindName(kind) { return ({ news: "新闻", report: "研报/评级", filing: "公告/披露", investment_news: "Investment News" })[kind] || kind; },
    scopeName(scope) { return ({ holding: "持仓", watch: "关注", investment: "投资新闻" })[scope] || ""; },
    researchScopeName(scope) { return ({ page: "页面分析", portfolio: "组合研究", symbol: "个股研究", sector: "板块研究" })[scope] || scope || "研究记录"; },
    toolName(name) { return ({ stj_get_portfolio_context: "读取组合", stj_get_symbol_context: "读取个股", market_get_quote: "查询行情", market_get_company_profile: "查询公司业务", market_get_valuation: "查询估值", market_get_financials: "查询财报", market_get_news: "查询新闻", market_get_reports: "查询研报", market_get_sector_context: "读取板块" })[name] || name || "数据工具"; },
    formatToolArgs(args) {
      if (!args || typeof args !== "object") return "";
      const values = Object.entries(args).slice(0, 3).map(([key, value]) => `${key}=${Array.isArray(value) ? value.join(",") : String(value)}`);
      const text = values.join(" · ");
      return text.length > 90 ? `${text.slice(0, 90)}…` : text;
    },
    sourceLabel(source) { return source?.name || source?.title || source?.source_name || source?.url || "数据来源"; },
    sourceUrl(source) { return this.safeLink(source?.url || source?.source_url || ""); },
    knowledgeKind(kind) { return ({ core: "核心", driver: "驱动", risk: "风险", evidence: "证据", question: "待验证" })[kind] || kind; },
    shortDate(value) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value).slice(0, 10) : date.toLocaleDateString("zh-CN"); },
    shortDateTime(value) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value).slice(0, 16) : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); },
    metaLabel(meta) { if (!meta) return ""; const cache = meta.cache || {}; return `${cache.stale ? "过期缓存 · " : cache.hit ? "缓存 · " : "已更新 · "}${this.shortDateTime(meta.as_of || meta.generated_at)}`; },
    marketStatusLabel(status) { return status ? `${({ open: "交易中", pre: "盘前", closed: "已收盘" })[status.state] || status.state} · ${this.shortDateTime(status.local_time)}${status.holiday_calendar ? "" : " · 常规时段估算"}` : "交易状态未知"; },
    rotationValue(row) { return row.metric_kind === "net_flow" ? Number(row.metric_value) : Number(row.metric_value); },
    rotationLabel(row) { return row.metric_kind === "net_flow" ? this.compactMoney(row.metric_value) : this.signedPercent(row.metric_value); },
    breadthStyle(kind) {
      const temperature = this.daily?.temperature || {};
      const values = {
        positive: Number(temperature.positive_count) || 0,
        negative: Number(temperature.negative_count) || 0,
        flat: Number(temperature.flat_count) || 0,
      };
      const total = values.positive + values.negative + values.flat;
      return `width:${total > 0 ? values[kind] / total * 100 : 0}%`;
    },
    rotationStyle(row) {
      const value = Number(row.metric_value);
      if (!Number.isFinite(value)) return "width:0";
      const maxAbs = Math.max(0, ...(this.daily?.rotation || [])
        .map(item => Math.abs(Number(item.metric_value)))
        .filter(Number.isFinite));
      const width = maxAbs > 0 && value !== 0 ? Math.max(Math.abs(value) / maxAbs * 48, 1.5) : 0;
      return value < 0
        ? `width:${width}%;right:50%;left:auto`
        : `width:${width}%;left:50%;right:auto`;
    },
    metricValue(value, format) { return format === "percent" ? this.signedPercent(value, false) : this.number(value, 2); },
    safeLink(value) { try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : "#"; } catch { return "#"; } },
  }));
});
