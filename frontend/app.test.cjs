// Dependency-free regressions: node frontend/app.test.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attributes = {}; }
  append(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener() {}
  querySelector(tag) {
    for (const child of this.children) {
      if (child?.tagName === tag) return child;
      const found = child?.querySelector?.(tag);
      if (found) return found;
    }
    return null;
  }
  get textContent() { return this.children.map((child) => child?.textContent ?? child).join(" "); }
}

function harness() {
  const root = new Element("main");
  const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag), getElementById: () => root },
    localStorage: { getItem: () => "", setItem() {}, removeItem() {} },
    window: { location: { origin: "http://localhost:8000" }, scrollTo() {} },
    URL, console,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "app.js"), "utf8").replace(/init\(\);\s*$/, ""), context);
  return { context, run: (source) => vm.runInContext(source, context) };
}

async function main() {
  let test = harness();
  for (const invalid of ["javascript:alert(1)", "data:text/html,<script>", "//evil.test/x", "/bank-pdfs/../../secrets", "file:///etc/passwd"]) {
    test.context.url = invalid;
    assert.equal(test.run("safeSourceUrl(url)"), null, invalid);
  }
  assert.equal(test.run("safeSourceUrl('/bank-pdfs/research.pdf#page=3')"), "http://localhost:8000/bank-pdfs/research.pdf#page=3");
  assert.equal(test.run("safeSourceUrl('https://news.example/article')"), "https://news.example/article");

  test = harness();
  let resolveNews;
  test.context.fetch = () => new Promise((resolve) => { resolveNews = resolve; });
  test.run("state.userId = 'old'; state.companyId = 'company';");
  const news = test.run("openNews('news')");
  test.run("logout()");
  resolveNews({ ok: true, json: async () => ({ news_id: "old-news" }) });
  await news;
  assert.equal(test.run("state.analysis"), null, "late news must not appear after logout");
  assert.equal(test.run("state.loading"), false);

  test = harness();
  let resolveAnswer;
  test.context.fetch = () => new Promise((resolve) => { resolveAnswer = resolve; });
  test.run("state.companyId = 'company'; state.analysis = { news_id: 'news' };");
  const question = test.run("submitQuestion('Что изменится?')");
  test.run("logout()");
  resolveAnswer({ ok: true, json: async () => ({ answer: "old answer" }) });
  await question;
  assert.equal(test.run("state.answer"), null, "late answer must not appear for another user");
  assert.equal(test.run("state.answerLoading"), false);

  test = harness();
  let resolveFeedback;
  test.context.fetch = () => new Promise((resolve) => { resolveFeedback = resolve; });
  test.run("state.companyId = 'company'; state.analysis = { news_id: 'news' };");
  const feedback = test.run("submitFeedback(1)");
  test.run("logout()");
  resolveFeedback({ ok: true, json: async () => ({ saved: true }) });
  await feedback;
  assert.equal(test.run("state.feedback"), null, "late feedback must not appear for another user");

  test = harness();
  test.run(`state.analysis = {
    title: 'Новость', transient: true, origin: 'user_supplied', relevance: {level:'низкая', score: 0},
    quality: {passed: false}, sections: [
      {id:'consequences', title:'Последствия', items: []},
      {id:'bank', title:'Оценка банка', items: []},
      {id:'happened', title:'Событие', items: []},
    ]
  };`);
  const detail = test.run("detailBlocks().filter(Boolean).map(node => node.textContent).join(' ')");
  assert.match(detail, /не пройдена/);
  assert.match(detail, /Предварительный разбор/);
  assert.ok(!detail.includes("Уточнить по этому событию"));
  assert.ok(!detail.includes("Был ли разбор полезен?"));
  assert.ok(detail.indexOf("Оценка банка") < detail.indexOf("Последствия"));
  assert.ok(detail.indexOf("Событие") < detail.indexOf("Оценка банка"));

  test.run(`state.users = [{id:'u1', company_id:'c1', role:'директор'}];
    state.companies = [{id:'c1', name:'Доступная'}, {id:'c2', name:'Без аккаунта'}];
    state.companyId = 'c1'; state.userId = 'u1';`);
  const sidebar = test.run("sidebar().textContent");
  assert.ok(sidebar.includes("Доступная"));
  assert.ok(!sidebar.includes("Без аккаунта"));
  assert.ok(sidebar.includes("директор"));

  test = harness();
  let sent;
  test.context.fetch = async (url, options) => {
    sent = { url, body: JSON.parse(options.body) };
    return { ok: true, json: async () => ({ title: "Новость", relevance: { level: "низкая", score: 0 }, sections: [] }) };
  };
  test.run(`state.companyId = 'c1'; state.userId = 'u1'; state.preview = {
    title: 'Событие рынка', text: 'Достаточно длинный текст новости о снижении ставки.',
    source_url: '', published_at: '2026-10-22'
  };`);
  await test.run("submitPreview()");
  assert.equal(sent.url, "/api/companies/c1/preview?user_id=u1");
  assert.equal(sent.body.source_url, null);
  assert.equal(test.run("state.analysis.transient"), true);
  assert.equal(test.run("state.screen"), "detail");
  test.run("state.preview.published_at = '2026-02-31'; state.screen = 'preview';");
  await test.run("submitPreview()");
  assert.match(test.run("state.previewError"), /дату/);
  console.log("Frontend checks passed: safe links, stale responses, transient preview, bank priority, available accounts, preview request and date validation.");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
