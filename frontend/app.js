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
  preview: { title: "", text: "", source_url: "", published_at: "" },
  previewError: "",
  feedback: null,
  feedbackLoading: false,
  feedbackError: "",
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
let answerToken = 0;
let feedbackToken = 0;

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
    const body = await response.json().catch(() => ({}));
    const error = new Error(typeof body.detail === "string" ? body.detail : "Ошибка запроса");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function resetDetail() {
  answerToken += 1;
  feedbackToken += 1;
  state.analysis = null;
  state.answer = null;
  state.answerLoading = false;
  state.answerError = "";
  state.question = "";
  state.feedback = null;
  state.feedbackLoading = false;
  state.feedbackError = "";
}

function safeSourceUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value, window.location.origin);
    if (/^https?:\/\//i.test(value) && ["http:", "https:"].includes(url.protocol)) return url.href;
    if (value.startsWith("/bank-pdfs/") && url.origin === window.location.origin && url.pathname.startsWith("/bank-pdfs/")) return url.href;
  } catch (_error) { /* Invalid source addresses are displayed as text only. */ }
  return null;
}

function sourceLink(value, label) {
  const href = safeSourceUrl(value);
  return href ? h("a", { href, target: "_blank", rel: "noopener noreferrer" }, [label || value]) : null;
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
  const user = state.users.find((item) => item.id === userId);
  if (!user) return;
  state.userId = userId;
  state.companyId = user.company_id;
  state.home = null;
  state.company = null;
  state.briefing = null;
  state.screen = screen === "feed" ? "feed" : "home";
  state.preview = { title: "", text: "", source_url: "", published_at: "" };
  state.previewError = "";
  localStorage.setItem("insights-user", userId);
  state.loading = true;
  state.error = "";
  resetDetail();
  render();
  try {
    const home = await getJson(`/api/home?user_id=${encodeURIComponent(userId)}`);
    if (token !== requestToken) return;
    state.home = home;
    if (screen === "feed") {
      await loadInsights(false);
      if (token !== requestToken) return;
      state.screen = "feed";
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
    getJson(withUser(`/api/companies/${id}`)),
    getJson(withUser(`/api/companies/${id}/briefing`), { method: "POST" }),
  ]);
  if (token !== requestToken) return;
  state.company = company;
  state.briefing = briefing;
  if (shouldRender) render();
}

async function openHome() {
  requestToken += 1;
  state.screen = "home";
  state.loading = false;
  state.error = "";
  resetDetail();
  render();
  window.scrollTo(0, 0);
}

async function openInsights() {
  const token = ++requestToken;
  state.screen = "feed";
  resetDetail();
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
  resetDetail();
  state.loading = true;
  state.error = "";
  render();
  window.scrollTo(0, 0);
  try {
    const analysis = await getJson(withUser(`/api/companies/${state.companyId}/news/${id}`));
    if (token !== requestToken) return;
    state.analysis = analysis;
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
  resetDetail();
  state.loading = false;
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
  state.companyId = null;
  state.briefing = null;
  resetDetail();
  state.loading = false;
  state.error = "";
  state.screen = "login";
  render();
}

async function submitQuestion(question) {
  if (!state.analysis || state.analysis.transient || state.answerLoading) return;
  const pageToken = requestToken;
  const token = ++answerToken;
  const text = (question ?? state.question).trim();
  state.question = text;
  if (text.length < 3 || text.length > 500) {
    state.answerError = "Вопрос должен содержать от 3 до 500 символов.";
    state.answer = null;
    render();
    return;
  }
  state.answerLoading = true;
  state.answerError = "";
  render();
  try {
    const answer = await getJson(
      withUser(`/api/companies/${state.companyId}/news/${state.analysis.news_id}/questions`),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      },
    );
    if (pageToken !== requestToken || token !== answerToken) return;
    state.answer = answer;
  } catch (_error) {
    if (pageToken === requestToken && token === answerToken) state.answerError = "Не удалось получить ответ. Попробуйте еще раз.";
  } finally {
    if (pageToken === requestToken && token === answerToken) {
      state.answerLoading = false;
      render();
    }
  }
}

function openPreview() {
  requestToken += 1;
  resetDetail();
  state.screen = "preview";
  state.loading = false;
  state.error = "";
  state.previewError = "";
  render();
  window.scrollTo(0, 0);
}

async function submitPreview() {
  if (state.loading) return;
  const body = Object.fromEntries(Object.entries(state.preview).map(([key, value]) => [key, value.trim()]));
  if (body.title.length < 5 || body.title.length > 300 || body.text.length < 20 || body.text.length > 12000) {
    state.previewError = "Укажите заголовок от 5 до 300 символов и текст от 20 до 12 000 символов.";
    render();
    return;
  }
  if (body.source_url && (!/^https?:\/\//i.test(body.source_url) || !safeSourceUrl(body.source_url))) {
    state.previewError = "Ссылка на источник должна начинаться с http:// или https://.";
    render();
    return;
  }
  const date = new Date(`${body.published_at}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(body.published_at) || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== body.published_at) {
    state.previewError = "Укажите корректную дату публикации.";
    render();
    return;
  }
  body.source_url = body.source_url || null;
  const token = ++requestToken;
  state.loading = true;
  state.previewError = "";
  render();
  try {
    const analysis = await getJson(withUser(`/api/companies/${state.companyId}/preview`), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (token !== requestToken) return;
    state.analysis = { ...analysis, transient: true };
    state.screen = "detail";
  } catch (_error) {
    if (token === requestToken) state.previewError = "Не удалось разобрать новость. Проверьте введенные данные и повторите попытку.";
  } finally {
    if (token === requestToken) {
      state.loading = false;
      render();
    }
  }
}

async function submitFeedback(rating) {
  if (!state.analysis || state.analysis.transient || state.feedbackLoading) return;
  const pageToken = requestToken;
  const token = ++feedbackToken;
  state.feedbackLoading = true;
  state.feedbackError = "";
  render();
  try {
    await getJson(withUser(`/api/companies/${state.companyId}/news/${state.analysis.news_id}/feedback`), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rating, comment: "" }),
    });
    if (pageToken === requestToken && token === feedbackToken) state.feedback = rating;
  } catch (_error) {
    if (pageToken === requestToken && token === feedbackToken) state.feedbackError = "Не удалось сохранить оценку. Попробуйте еще раз.";
  } finally {
    if (pageToken === requestToken && token === feedbackToken) {
      state.feedbackLoading = false;
      render();
    }
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
      h("div", { class: `layout${state.screen === "login" ? " login-layout" : ""}` }, [
        state.screen === "login" ? null : sidebar(),
        h("main", { class: "main", id: "main", "aria-busy": state.loading ? "true" : "false" }, mainBlocks()),
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
      h("button", { class: `nav-btn${state.screen === "home" ? " active" : ""}`, type: "button", disabled: !state.home, onclick: openHome }, ["Главная"]),
      h("button", { class: `nav-btn insights${["feed", "detail", "preview"].includes(state.screen) ? " active" : ""}`, type: "button", disabled: !state.home, onclick: openInsights }, ["Инсайты"]),
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
  if (["feed", "detail", "preview"].includes(state.screen)) return null;
  return h("button", { class: "entry-bar", type: "button", disabled: !state.home, onclick: openInsights }, [
    h("strong", {}, ["Новостная аналитика"]),
    h("span", {}, ["Постоянная точка входа: события, факты, позиция банка и выводы AI"]),
  ]);
}

function sidebar() {
  const sameCompany = state.users.filter((item) => item.company_id === state.companyId);
  const availableCompanies = state.companies.filter((company) => state.users.some((user) => user.company_id === company.id));
  return h("aside", { class: "sidebar", "aria-label": "Выбор роли и компании" }, [
    h("div", { class: "sidebar-group" }, [
      h("p", { class: "sidebar-label" }, ["Роли этой компании"]),
      ...sameCompany.map((user) =>
        h("button", {
          class: `company${user.id === state.userId ? " active" : ""}`,
          type: "button",
          "aria-pressed": user.id === state.userId ? "true" : "false",
          onclick: () => enter(user.id, state.screen === "home" ? "home" : "feed"),
        }, [
          h("strong", {}, [user.role]),
          h("span", {}, [user.display_name]),
        ]),
      ),
    ]),
    h("div", { class: "sidebar-group" }, [
    h("p", { class: "sidebar-label" }, ["Доступные тестовые компании"]),
    ...availableCompanies.map((company) =>
      h("button", {
        class: `company${company.id === state.companyId ? " active" : ""}`,
        type: "button",
        "aria-pressed": company.id === state.companyId ? "true" : "false",
        onclick: () => selectCompany(company.id),
      }, [
        h("strong", {}, [company.name]),
        h("span", {}, [
          [company.industry, company.city].filter(Boolean).join(" · ")
          || (company.include_incomplete ? "Неполный профиль" : "Мало данных"),
        ]),
      ]),
    ),
    h("p", { class: "sidebar-note" }, [`В наборе ${state.companies.length} компаний крупного бизнеса. Демо-вход настроен для ${availableCompanies.length}.`]),
    ]),
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
  if (state.screen === "preview") return previewBlocks();
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
  const blocks = [profilePanel(), h("section", { class: "panel preview-entry" }, [
    h("div", {}, [h("h3", {}, ["Проверить свою новость"]), h("p", { class: "lead" }, ["Добавьте текст события и получите разбор для своей компании и роли."])]),
    h("button", { class: "primary", type: "button", onclick: openPreview }, ["Проверить новость"]),
  ])];
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

function previewBlocks() {
  const field = (name, label, props, tag = "input") => {
    const input = h(tag, { id: `preview-${name}`, name, ...props, oninput: (event) => { state.preview[name] = event.target.value; } });
    input.value = state.preview[name];
    return h("div", { class: "form-field" }, [h("label", { for: `preview-${name}` }, [label]), input]);
  };
  return [
    h("div", {}, [h("button", { class: "back", type: "button", onclick: backToFeed }, ["← К сводке"])]),
    h("section", { class: "panel" }, [
      h("h2", {}, ["Проверить свою новость"]),
      h("p", { class: "lead" }, [`Разбор для ${state.company?.name || state.home?.company?.name || "вашей компании"}, роль: ${currentUser()?.role || "не указана"}.`]),
      h("p", { class: "note" }, ["Предварительный разбор не сохраняется в общую ленту. Сведения из вашего текста не считаются подтвержденными фактами; ссылка указывается для происхождения материала."]),
      h("form", { class: "preview-form", onsubmit: (event) => { event.preventDefault(); submitPreview(); } }, [
        field("title", "Заголовок", { type: "text", required: true, minlength: "5", maxlength: "300", placeholder: "От 5 до 300 символов" }),
        field("text", "Текст новости", { required: true, minlength: "20", maxlength: "12000", rows: "8", placeholder: "Вставьте текст материала — от 20 до 12 000 символов" }, "textarea"),
        field("source_url", "Ссылка на первоисточник (необязательно)", { type: "url", maxlength: "2000", placeholder: "https://..." }),
        field("published_at", "Дата публикации", { type: "date", required: true }),
        state.previewError ? h("p", { class: "error", role: "alert" }, [state.previewError]) : null,
        h("button", { class: "primary", type: "submit" }, ["Получить предварительный разбор"]),
      ]),
    ]),
  ];
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
  const sections = analysis.sections || [];
  const sourceSections = sections.filter((section) => ["happened", "confirmed", "source_facts"].includes(section.id));
  const bankSections = sections.filter((section) => section.id === "bank");
  const remainingSections = sections.filter((section) => !["happened", "confirmed", "source_facts", "bank"].includes(section.id));
  return [
    h("div", {}, [h("button", { class: "back", type: "button", onclick: backToFeed }, ["← К сводке"])]),
    analysis.transient ? h("div", { class: "preview-notice", role: "status" }, [
      h("strong", {}, ["Предварительный разбор вашей новости"]),
      h("p", {}, ["Материал предоставлен пользователем. Его достоверность не подтверждена. Разбор не добавлен в общую ленту; уточняющие вопросы и оценка здесь недоступны."]),
      h("button", { class: "chip", type: "button", onclick: openPreview }, ["Изменить текст новости"]),
    ]) : null,
    h("section", { class: "panel" }, [
      h("div", { class: "meta" }, [
        h("span", {}, [formatDate(analysis.published_at)]),
        h("span", { class: "tag" }, [analysis.category || "Событие"]),
        h("span", { class: "tag" }, [analysis.origin_label || (analysis.origin === "user_supplied" ? "Материал пользователя" : "Источник не указан")]),
        h("span", { class: `score ${levelClass(level)}` }, [`${percent(analysis.relevance.score)} · ${level}`]),
      ]),
      h("h2", {}, [analysis.title]),
      sourceLink(analysis.source_url, "Открыть первоисточник ↗"),
      h("p", { class: "note" }, [analysis.generation?.note || ""]),
      h("div", { class: "legend" }, [
        h("span", { class: "badge kind-source" }, ["Факт источника"]),
        h("span", { class: "badge kind-bank" }, ["Аналитика банка"]),
        h("span", { class: "badge kind-ai" }, ["Вывод AI"]),
        h("span", { class: "badge kind-product" }, ["Продукт банка"]),
      ]),
      qualityLine(analysis.quality),
    ]),
    ...sourceSections.map(renderSection),
    ...bankSections.map(renderSection),
    ...(analysis.generation?.narrative ? [h("section", { class: "claim kind-ai" }, [
      h("header", {}, [h("span", { class: "badge" }, ["Текст модели"])]),
      h("p", {}, [analysis.generation.narrative]),
    ])] : []),
    ...remainingSections.map(renderSection),
    analysis.transient ? null : questionPanel(),
    analysis.transient ? null : feedbackPanel(),
    sourcesPanel(analysis.sources || []),
    trace(analysis.trace, "Как получен вывод"),
  ];
}

function qualityLine(quality) {
  if (!quality) return null;
  let text = quality.passed === true ? "Автоматическая проверка полноты пройдена. Это не внешняя проверка достоверности." : "Автоматическая проверка полноты не пройдена. Выводы требуют проверки.";
  if (quality.revised) text += ` Проверка скорректировала результат. ${(quality.fixes || []).join(" ")}`;
  return h("p", { class: quality.passed === true ? "note" : "quality-warning" }, [text]);
}

function renderSection(section) {
  const body = [];
  if (section.lead) body.push(h("p", { class: "lead" }, [section.lead]));
  if (!section.items?.length) {
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
  const relatedSources = (state.analysis?.sources || []).filter((source) => item.basis?.includes(source.id) && safeSourceUrl(source.url));
  if (relatedSources.length) kids.push(h("div", { class: "claim-links" }, relatedSources.map((source) => sourceLink(source.url, source.title))));
  return h("article", { class: `claim kind-${kind}` }, kids);
}

function questionPanel() {
  const form = h("form", { class: "ask", onsubmit: (event) => { event.preventDefault(); submitQuestion(); } }, [
    h("h3", {}, ["Уточнить по этому событию"]),
    h("p", { class: "lead" }, ["Ответ берется из профиля и уже собранного разбора. Если данных нет, сервис так и скажет."]),
    h("div", { class: "chips" }, PROMPTS.map((prompt) =>
      h("button", { class: "chip", type: "button", disabled: state.answerLoading, onclick: () => submitQuestion(prompt) }, [prompt]),
    )),
    h("label", { for: "followup-question" }, ["Ваш вопрос"]),
    h("textarea", { id: "followup-question", name: "question", required: true, minlength: "3", maxlength: "500", disabled: state.answerLoading, placeholder: "Например: какая выручка указана в профиле?" }, []),
    h("button", { class: "primary", type: "submit", disabled: state.answerLoading }, [state.answerLoading ? "Собираем ответ…" : "Спросить"]),
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
      basis: state.answer.basis,
    basis_labels: state.answer.basis_labels,
    note: state.answer.generation?.mode === "llm" ? "Формулировку сжала модель." : "Ответ собран без вызова модели.",
  }));
  return h("section", { class: "section" }, kids);
}

function feedbackPanel() {
  return h("section", { class: "panel feedback" }, [
    h("h3", {}, ["Был ли разбор полезен?"]),
    h("div", { class: "chips" }, [
      ...[[1, "Полезно"], [-1, "Не полезно"]].map(([rating, label]) => h("button", {
        class: `chip${state.feedback === rating ? " selected" : ""}`, type: "button",
        disabled: state.feedbackLoading, "aria-pressed": state.feedback === rating ? "true" : "false",
        onclick: () => submitFeedback(rating),
      }, [label])),
    ]),
    h("p", { class: "note", role: "status" }, [state.feedbackLoading ? "Сохраняем оценку…" : state.feedback ? "Спасибо, оценка сохранена." : "Ваша оценка поможет улучшить подбор и объяснение событий."]),
    state.feedbackError ? h("p", { class: "error", role: "alert" }, [state.feedbackError]) : null,
  ]);
}

function sourcesPanel(sources) {
  return h("section", { class: "section" }, [
    h("h3", {}, ["Источники и происхождение"]),
    h("div", { class: "panel sources" }, sources.map((source) =>
      h("div", { class: "source" }, [
        h("strong", {}, [source.title]),
        h("span", { class: "note" }, [source.note || ""]),
        sourceLink(source.url),
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
