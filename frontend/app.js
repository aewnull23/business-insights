const state = {
  status: null,
  companies: [],
  companyId: null,
  company: null,
  briefing: null,
  view: "feed",
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

async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = new Error("request failed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function init() {
  state.loading = true;
  state.error = "";
  render();
  try {
    const [status, payload] = await Promise.all([
      getJson("/api/status"),
      getJson("/api/companies"),
    ]);
    state.status = status;
    state.companies = payload.companies || [];
    if (!state.companies.length) {
      state.error = "В загруженных данных нет компаний.";
      state.loading = false;
      render();
      return;
    }
    await selectCompany(state.companies[0].id, false);
  } catch (_error) {
    state.error = "Не удалось открыть сервис. Проверьте, что приложение запущено.";
    state.loading = false;
    render();
  }
}

async function selectCompany(id, shouldRenderStart = true) {
  const token = ++requestToken;
  state.companyId = id;
  state.view = "feed";
  state.analysis = null;
  state.answer = null;
  state.answerError = "";
  state.question = "";
  state.loading = true;
  state.error = "";
  if (shouldRenderStart) render();
  try {
    const [company, briefing] = await Promise.all([
      getJson(`/api/companies/${id}`),
      getJson(`/api/companies/${id}/briefing`, { method: "POST" }),
    ]);
    if (token !== requestToken) return;
    state.company = company;
    state.briefing = briefing;
  } catch (_error) {
    if (token === requestToken) state.error = "Не удалось собрать сводку по этой компании.";
  } finally {
    if (token === requestToken) {
      state.loading = false;
      render();
    }
  }
}

async function openNews(id) {
  const token = ++requestToken;
  state.view = "detail";
  state.analysis = null;
  state.answer = null;
  state.answerError = "";
  state.question = "";
  state.loading = true;
  state.error = "";
  render();
  window.scrollTo(0, 0);
  try {
    const analysis = await getJson(`/api/companies/${state.companyId}/news/${id}`);
    if (token !== requestToken) return;
    state.analysis = analysis;
  } catch (_error) {
    if (token !== requestToken) return;
    state.error = "Не удалось открыть разбор события.";
    state.view = "feed";
  } finally {
    if (token === requestToken) {
      state.loading = false;
      render();
    }
  }
}

function back() {
  requestToken += 1;
  state.view = "feed";
  state.analysis = null;
  state.answer = null;
  state.error = "";
  render();
  window.scrollTo(0, 0);
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
      `/api/companies/${state.companyId}/news/${state.analysis.news_id}/questions`,
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
  const mode = state.status;
  app.replaceChildren(
    h("div", { class: "app" }, [
      h("header", { class: "topbar" }, [
        h("div", { class: "brand" }, [
          h("div", { class: "logo" }, ["И"]),
          h("div", {}, [
            h("h1", {}, ["Бизнес-инсайты"]),
            h("p", {}, ["События и их значение для компании"]),
          ]),
        ]),
        h("div", { class: "pills" }, mode ? [
          h("span", { class: "pill" }, [mode.news_mode === "mixed" ? "Демо и внешняя лента" : "Демонстрационные сюжеты"]),
          h("span", { class: "pill" }, [mode.llm_mode === "live" ? `Модель: ${mode.llm_model}` : "Модель не подключена"]),
        ] : []),
      ]),
      h("p", { class: "banner" }, [
        mode?.llm_note || "Материалы с пометкой «демо» подготовлены для сценария и не являются сообщениями СМИ или аналитикой банка.",
      ]),
      h("div", { class: "layout" }, [
        sidebar(),
        h("main", { class: "main" }, mainBlocks()),
      ]),
    ]),
  );
}

function sidebar() {
  return h("aside", { class: "sidebar" }, state.companies.map((company) =>
    h("button", {
      class: `company${company.id === state.companyId ? " active" : ""}`,
      type: "button",
      onclick: () => selectCompany(company.id),
    }, [
      h("strong", {}, [company.name]),
      h("span", {}, [[company.industry, company.city].filter(Boolean).join(" · ") || "Мало данных о компании"]),
    ]),
  ));
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
        h("button", { class: "primary", type: "button", onclick: () => state.companyId ? selectCompany(state.companyId) : init() }, ["Повторить"]),
      ]),
    ];
  }
  if (state.view === "detail" && state.analysis) return detailBlocks();
  return feedBlocks();
}

function feedBlocks() {
  if (!state.company || !state.briefing) return [];
  const blocks = [profilePanel()];
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
      h("span", { class: "tag" }, [item.origin === "rss" ? "Внешняя лента" : "Демо"]),
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
    h("div", {}, [h("button", { class: "back", type: "button", onclick: back }, ["← К сводке"])]),
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
    ? `Проверка скорректировала результат. ${ (quality.fixes || []).join(" ") }`
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
