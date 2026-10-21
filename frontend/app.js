const state = {
  status: null,
  users: [],
  userId: localStorage.getItem("insights-user") || "",
  home: null,
  companies: [],
  excluded: [],
  companyId: null,
  company: null,
  briefing: null,
  screen: "login",
  analysis: null,
  loading: false,
  error: "",
  question: "",
  answer: null,
  answerLoading: false,
  answerError: "",
};

const KIND = {
  source: "Сведение источника",
  confirmed: "Подтвержденный факт",
  profile: "Профиль",
  ai: "Вывод AI",
  bank: "Аналитика банка",
  action: "Что проверить",
  unknown: "Неизвестно",
  product: "Продукт банка",
};

const PROMPTS = [
  "Что здесь является фактом?",
  "Как это влияет на кредитную линию?",
  "Что говорит аналитика Альфа-Банка?",
  "Кто бенефициар компании?",
];

const MONTHS = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

const app = document.getElementById("app");
let requestToken = 0;

function h(tag, props, kids) {
  const node = document.createElement(tag);
  Object.entries(props || {}).forEach(([key, value]) => {
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value != null && value !== false) node.setAttribute(key, value);
  });
  (kids || []).forEach((kid) => node.append(kid ?? ""));
  return node;
}

function formatDate(iso) {
  if (!iso || iso.length < 10) return iso || "";
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

function percent(score) {
  return `${Math.round(Number(score) * 100)}`;
}

function levelClass(level) {
  if (level === "высокая") return "high";
  if (level === "средняя") return "mid";
  return "low";
}

function withUser(url) {
  if (!state.userId) return url;
  const join = url.includes("?") ? "&" : "?";
  return `${url}${join}user_id=${encodeURIComponent(state.userId)}`;
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = new Error("request failed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function currentUser() {
  return state.users.find((item) => item.id === state.userId) || null;
}

async function init() {
  state.loading = true;
  state.error = "";
  render();
  try {
    const [status, users, companies] = await Promise.all([
      getJson("/api/status"),
      getJson("/api/users"),
      getJson("/api/companies"),
    ]);
    state.status = status;
    state.users = users.users || [];
    state.companies = companies.companies || [];
    state.excluded = companies.excluded || [];
    if (state.userId && state.users.some((item) => item.id === state.userId)) {
      await enter(state.userId, "home");
    } else {
      state.userId = "";
      state.screen = "login";
    }
  } catch (_error) {
    state.error = "Не удалось открыть интернет-банк. Проверьте, что приложение запущено.";
  } finally {
    state.loading = false;
    render();
  }
}

async function enter(userId, screen) {
  const token = ++requestToken;
  state.userId = userId;
  localStorage.setItem("insights-user", userId);
  state.loading = true;
  state.error = "";
  state.analysis = null;
  state.answer = null;
  render();
  try {
    const user = state.users.find((item) => item.id === userId);
    const home = await getJson(`/api/home?user_id=${encodeURIComponent(userId)}`);
    if (token !== requestToken) return;
    state.home = home;
    state.companyId = user.company_id;
    if (screen === "feed" || state.screen === "feed" || state.screen === "detail") {
      await loadInsights(false);
      if (token !== requestToken) return;
      if (state.screen === "detail" && state.analysis) state.screen = "detail";
      else state.screen = "feed";
    } else {
      state.screen = "home";
    }
  } catch (_error) {
    if (token === requestToken) state.error = "Не удалось открыть сессию пользователя.";
  } finally {
    if (token === requestToken) {
      state.loading = false;
      render();
    }
  }
}

async function loadInsights(shouldRender = true) {
  const token = requestToken;
  const id = state.companyId;
  const [company, briefing] = await Promise.all([
    getJson(`/api/companies/${id}`),
    getJson(withUser(`/api/companies/${id}/briefing`), { method: "POST" }),
  ]);
  if (token !== requestToken) return;
  state.company = company;
  state.briefing = briefing;
  if (shouldRender) render();
}

async function openHome() {
  state.screen = "home";
  state.analysis = null;
  render();
  window.scrollTo(0, 0);
}

async function openInsights() {
  const token = ++requestToken;
  state.screen = "feed";
  state.analysis = null;
  state.answer = null;
  state.loading = true;
  state.error = "";
  render();
  window.scrollTo(0, 0);
  try {
    await loadInsights(false);
  } catch (_error) {
    if (token === requestToken) state.error = "Не удалось собрать сводку.";
  } finally {
    if (token === requestToken) {
      state.loading = false;
      render();
    }
  }
}

async function selectCompany(id) {
  const user = state.users.find((item) => item.company_id === id && item.role === (currentUser()?.role || "генеральный директор"))
    || state.users.find((item) => item.company_id === id);
  if (!user) {
    state.error = "Для этой компании нет тестовой учетной записи.";
    render();
    return;
  }
  await enter(user.id, "feed");
}

async function openNews(id) {
  const token = ++requestToken;
  state.screen = "detail";
  state.analysis = null;
  state.answer = null;
  state.answerError = "";
  state.question = "";
  state.loading = true;
  state.error = "";
  render();
  window.scrollTo(0, 0);
  try {
    state.analysis = await getJson(withUser(`/api/companies/${state.companyId}/news/${id}`));
  } catch (_error) {
    if (token !== requestToken) return;
    state.error = "Не удалось открыть разбор события.";
    state.screen = "feed";
  } finally {
    if (token === requestToken) {
      state.loading = false;
      render();
    }
  }
}

function backToFeed() {
  requestToken += 1;
  state.screen = "feed";
  state.analysis = null;
  state.answer = null;
  state.error = "";
  render();
  window.scrollTo(0, 0);
}

function logout() {
  requestToken += 1;
  localStorage.removeItem("insights-user");
  state.userId = "";
  state.home = null;
  state.company = null;
  state.briefing = null;
  state.analysis = null;
  state.screen = "login";
  render();
}

async function submitQuestion(question) {
  const text = (question ?? state.question).trim();
  state.question = text;
  if (text.length < 3) {
    state.answerError = "Вопрос должен быть не короче 3 символов.";
    state.answer = null;
    render();
    return;
  }
  state.answerLoading = true;
  state.answerError = "";
  render();
  try {
    state.answer = await getJson(
      withUser(`/api/companies/${state.companyId}/news/${state.analysis.news_id}/questions`),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      },
    );
  } catch (_error) {
    state.answerError = "Не удалось получить ответ. Попробуйте еще раз.";
  } finally {
    state.answerLoading = false;
    render();
  }
}

function render() {
  const user = currentUser();
  app.replaceChildren(
    h("div", { class: "app" }, [
      topbar(user),
      state.userId ? persistentEntry() : null,
      h("p", { class: "banner" }, [
        state.status?.data_note || "Демонстрационный контур интернет-банка. Это не промышленный Альфа-Бизнес.",
      ]),
      h("div", { class: "layout" }, [
        state.screen === "login" ? null : sidebar(),
        h("main", { class: "main" }, mainBlocks()),
      ]),
    ]),
  );
}

function topbar(user) {
  return h("header", { class: "topbar" }, [
    h("div", { class: "brand" }, [
      h("div", { class: "logo" }, ["А"]),
      h("div", {}, [
        h("h1", {}, ["Альфа-Бизнес"]),
        h("p", {}, ["Интернет-банк · демо-контур крупного бизнеса"]),
      ]),
    ]),
    user ? h("nav", { class: "nav" }, [
      h("button", { class: `nav-btn${state.screen === "home" ? " active" : ""}`, type: "button", onclick: openHome }, ["Главная"]),
      h("button", { class: `nav-btn insights${state.screen === "feed" || state.screen === "detail" ? " active" : ""}`, type: "button", onclick: openInsights }, ["Инсайты"]),
    ]) : null,
    h("div", { class: "pills" }, [
      ...(state.status ? [
        h("span", { class: "pill" }, [state.status.news_mode === "mixed" ? "Демо и внешняя лента" : "Синтетические сюжеты"]),
        h("span", { class: "pill" }, [state.status.llm_mode === "live" ? `Модель: ${state.status.llm_model}` : "Модель не подключена"]),
      ] : []),
      user ? h("span", { class: "pill" }, [user.display_name]) : null,
      user ? h("button", { class: "ghost", type: "button", onclick: logout }, ["Сменить пользователя"]) : null,
    ]),
  ]);
}

function persistentEntry() {
  if (state.screen === "feed" || state.screen === "detail") return null;
  return h("button", { class: "entry-bar", type: "button", onclick: openInsights }, [
    h("strong", {}, ["Новостная аналитика"]),
    h("span", {}, ["Постоянная точка входа: события, факты, позиция банка и выводы AI"]),
  ]);
}

function sidebar() {
  if (state.screen === "home") {
    const sameCompany = state.users.filter((item) => item.company_id === state.companyId);
    return h("aside", { class: "sidebar" }, [
      h("p", { class: "sidebar-label" }, ["Роли этой компании"]),
      ...sameCompany.map((user) =>
        h("button", {
          class: `company${user.id === state.userId ? " active" : ""}`,
          type: "button",
          onclick: () => enter(user.id, "home"),
        }, [
          h("strong", {}, [user.role]),
          h("span", {}, [user.display_name]),
        ]),
      ),
    ]);
  }
  return h("aside", { class: "sidebar" }, [
    h("p", { class: "sidebar-label" }, ["Компании крупного бизнеса"]),
    ...state.companies.map((company) =>
      h("button", {
        class: `company${company.id === state.companyId ? " active" : ""}`,
        type: "button",
        onclick: () => selectCompany(company.id),
      }, [
        h("strong", {}, [company.name]),
        h("span", {}, [
          [company.industry, company.city].filter(Boolean).join(" · ")
          || (company.include_incomplete ? "Неполный профиль" : "Мало данных"),
        ]),
      ]),
    ),
  ]);
}

function mainBlocks() {
  if (state.loading) {
    return [
      h("div", { class: "skeleton" }),
      h("div", { class: "skeleton" }),
      h("div", { class: "skeleton" }),
    ];
  }
  if (state.error) {
    return [
      h("div", { class: "error" }, [
        h("p", {}, [state.error]),
        h("button", { class: "primary", type: "button", onclick: init }, ["Повторить"]),
      ]),
    ];
  }
  if (state.screen === "login") return loginBlocks();
  if (state.screen === "home") return homeBlocks();
  if (state.screen === "detail" && state.analysis) return detailBlocks();
  return feedBlocks();
}

function loginBlocks() {
  const groups = {};
  state.users.forEach((user) => {
    groups[user.company_id] = groups[user.company_id] || [];
    groups[user.company_id].push(user);
  });
  return [
    h("section", { class: "panel" }, [
      h("h2", {}, ["Вход в демо интернет-банка"]),
      h("p", { class: "lead" }, ["Сервис создан для людей, а не только для юридического лица. Выберите тестовую учетную запись. Это не промышленная аутентификация Альфа-Банка."]),
    ]),
    ...Object.values(groups).map((users) =>
      h("section", { class: "panel" }, [
        h("h3", {}, [users[0].company_name || users[0].company_id]),
        h("div", { class: "user-grid" }, users.map((user) =>
          h("button", { class: "user-card", type: "button", onclick: () => enter(user.id, "home") }, [
            h("strong", {}, [user.role]),
            h("span", {}, [user.display_name]),
          ]),
        )),
      ]),
    ),
  ];
}

function homeBlocks() {
  const home = state.home;
  if (!home) return [];
  return [
    h("section", { class: "panel" }, [
      h("h2", {}, [home.company.name]),
      h("p", { class: "disclaimer" }, [`${home.user.role}. Крупный бизнес в кейсе — выручка свыше 15 млрд ₽.`]),
      h("dl", { class: "rows" }, [
        h("dt", {}, ["Отрасль"]), h("dd", {}, [home.company.industry || "нет в данных"]),
        h("dt", {}, ["Город"]), h("dd", {}, [home.company.city || "нет в данных"]),
        h("dt", {}, ["Тип клиента"]), h("dd", {}, [home.company.client_type || "нет в данных"]),
        h("dt", {}, ["Продукты"]), h("dd", {}, [(home.products || []).join(", ") || "нет в данных"]),
      ]),
    ]),
    h("button", { class: "insight-tile", type: "button", onclick: openInsights }, [
      h("span", { class: "tile-kicker" }, ["Всегда на главной"]),
      h("h3", {}, [home.entry.title]),
      h("p", {}, [home.entry.lead]),
      h("span", { class: "tile-cta" }, ["Открыть инсайты"]),
    ]),
    ...(home.accounts || []).map((account) =>
      h("section", { class: "panel" }, [
        h("h3", {}, [account.name]),
        h("p", { class: "note" }, [account.note]),
      ]),
    ),
  ];
}

function feedBlocks() {
  if (!state.company || !state.briefing) return [];
  const blocks = [profilePanel()];
  if (state.briefing.user?.role) {
    blocks.push(h("p", { class: "note" }, [`Сводка собрана для роли: ${state.briefing.user.role}.`]));
  }
  if (state.briefing.profile_gaps?.length) {
    blocks.push(h("div", { class: "gap-list" }, [
      `В профиле нет: ${state.briefing.profile_gaps.join(", ")}. Эти поля не достраиваются и не участвуют в выводах.`,
    ]));
  }
  const items = state.briefing.items || [];
  if (!items.length) {
    blocks.push(h("div", { class: "empty" }, [
      h("strong", {}, ["Значимых событий нет"]),
      h("p", { class: "muted" }, ["Для заполненных полей профиля ни один сюжет не набрал вес. Пустые характеристики не заменяются предположением."]),
    ]));
  }
  items.forEach((item) => blocks.push(newsCard(item)));
  blocks.push(h("p", { class: "muted" }, [
    `${state.briefing.notice || ""} Не вошло в сводку: ${state.briefing.omitted_count}. Снято повторов: ${(state.briefing.duplicates || []).length}.`,
  ]));
  blocks.push(trace(state.briefing.trace, "Как собрана сводка"));
  return blocks;
}

function profilePanel() {
  const company = state.company;
  return h("section", { class: "panel" }, [
    h("h2", {}, [company.name]),
    company.demo ? h("p", { class: "disclaimer" }, [company.disclaimer || "Демонстрационный профиль."]) : null,
    h("dl", { class: "rows" }, company.rows.flatMap((row) => [
      h("dt", {}, [row.label]),
      h("dd", { class: row.value ? "" : "missing" }, [row.value || "нет в данных"]),
    ])),
  ]);
}

function newsCard(item) {
  const level = item.relevance.level;
  return h("button", {
    class: `card ${levelClass(level)}`,
    type: "button",
    onclick: () => openNews(item.id),
  }, [
    h("div", { class: "meta" }, [
      h("span", {}, [formatDate(item.published_at)]),
      h("span", { class: "tag" }, [item.category || "Событие"]),
      h("span", { class: "tag" }, [item.origin === "rss" ? "Внешняя лента" : "Синтетика"]),
      h("span", { class: `score ${levelClass(level)}` }, [`${percent(item.relevance.score)} · ${level}`]),
    ]),
    h("h3", {}, [item.title]),
    h("p", { class: "impact" }, [item.short_impact]),
    h("ul", { class: "reasons" }, (item.relevance.reasons || []).slice(0, 3).map((reason) => h("li", {}, [reason.text]))),
  ]);
}

function detailBlocks() {
  const analysis = state.analysis;
  const level = analysis.relevance.level;
  return [
    h("div", {}, [h("button", { class: "back", type: "button", onclick: backToFeed }, ["← К сводке"])]),
    h("section", { class: "panel" }, [
      h("div", { class: "meta" }, [
        h("span", {}, [formatDate(analysis.published_at)]),
        h("span", { class: "tag" }, [analysis.category || "Событие"]),
        h("span", { class: "tag" }, [analysis.origin_label]),
        h("span", { class: `score ${levelClass(level)}` }, [`${percent(analysis.relevance.score)} · ${level}`]),
      ]),
      h("h2", {}, [analysis.title]),
      h("p", { class: "note" }, [analysis.generation?.note || ""]),
      h("div", { class: "legend" }, [
        h("span", { class: "badge kind-source" }, ["Факт источника"]),
        h("span", { class: "badge kind-bank" }, ["Аналитика банка"]),
        h("span", { class: "badge kind-ai" }, ["Вывод AI"]),
        h("span", { class: "badge kind-product" }, ["Продукт банка"]),
      ]),
      qualityLine(analysis.quality),
    ]),
    ...(analysis.generation?.narrative ? [h("section", { class: "claim kind-ai" }, [
      h("header", {}, [h("span", { class: "badge" }, ["Текст модели"])]),
      h("p", {}, [analysis.generation.narrative]),
    ])] : []),
    ...analysis.sections.map(renderSection),
    questionPanel(),
    sourcesPanel(analysis.sources || []),
    trace(analysis.trace, "Как получен вывод"),
  ];
}

function qualityLine(quality) {
  if (!quality) return null;
  const text = quality.revised
    ? `Проверка скорректировала результат. ${(quality.fixes || []).join(" ")}`
    : "Проверка полноты пройдена, правка не понадобилась.";
  return h("p", { class: "note" }, [text]);
}

function renderSection(section) {
  const body = [];
  if (section.lead) body.push(h("p", { class: "lead" }, [section.lead]));
  if (!section.items.length) {
    body.push(h("div", { class: "empty" }, [section.empty || "В этом блоке нет данных."]));
  } else {
    section.items.forEach((item) => body.push(renderClaim(item)));
  }
  return h("section", { class: "section" }, [h("h3", {}, [section.title]), ...body]);
}

function renderClaim(item) {
  const kind = item.kind || "source";
  const kids = [
    h("header", {}, [h("span", { class: "badge" }, [KIND[kind] || kind])]),
  ];
  if (item.title) kids.push(h("h4", {}, [item.title]));
  kids.push(h("p", {}, [item.text]));
  if (item.note) kids.push(h("p", { class: "note" }, [item.note]));
  if (item.basis_labels?.length) kids.push(h("p", { class: "basis" }, [`Основания: ${item.basis_labels.join(" · ")}`]));
  return h("article", { class: `claim kind-${kind}` }, kids);
}

function questionPanel() {
  const form = h("form", { class: "ask", onsubmit: (event) => { event.preventDefault(); submitQuestion(); } }, [
    h("h3", {}, ["Уточнить по этому событию"]),
    h("p", { class: "lead" }, ["Ответ берется из профиля и уже собранного разбора. Если данных нет, сервис так и скажет."]),
    h("div", { class: "chips" }, PROMPTS.map((prompt) =>
      h("button", { class: "chip", type: "button", onclick: () => submitQuestion(prompt) }, [prompt]),
    )),
    h("textarea", { name: "question", maxlength: "500", placeholder: "Например: какая выручка указана в профиле?" }, []),
    h("button", { class: "primary", type: "submit" }, [state.answerLoading ? "Собираем ответ…" : "Спросить"]),
  ]);
  form.querySelector("textarea").value = state.question;
  form.querySelector("textarea").addEventListener("input", (event) => {
    state.question = event.target.value;
  });
  const kids = [form];
  if (state.answerError) kids.push(h("p", { class: "error" }, [state.answerError]));
  if (state.answer) kids.push(renderClaim({
    kind: state.answer.kind,
    text: state.answer.answer,
    basis_labels: state.answer.basis_labels,
    note: state.answer.generation?.mode === "llm" ? "Формулировку сжала модель." : "Ответ собран без вызова модели.",
  }));
  return h("section", { class: "section" }, kids);
}

function sourcesPanel(sources) {
  return h("section", { class: "section" }, [
    h("h3", {}, ["Источники и происхождение"]),
    h("div", { class: "panel sources" }, sources.map((source) =>
      h("div", { class: "source" }, [
        h("strong", {}, [source.title]),
        h("span", { class: "note" }, [source.note || ""]),
        source.url ? h("a", { href: source.url, target: "_blank", rel: "noreferrer" }, [source.url]) : null,
      ]),
    )),
  ]);
}

function trace(steps, title) {
  if (!steps?.length) return h("div", {});
  return h("details", { class: "panel trace" }, [
    h("summary", {}, [title]),
    h("ol", {}, steps.map((step) => h("li", {}, [
      h("strong", {}, [step.title]),
      h("div", { class: "muted" }, [step.summary]),
    ]))),
  ]);
}

init();
