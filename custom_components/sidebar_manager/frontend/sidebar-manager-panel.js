/* Sidebar Manager panel – admin UI to manage each user's sidebar. No build step. */

const FIXED_PANELS = ["profile", "config", "notfound"];
const BUILTIN_SORT = { energy: 1, map: 2, logbook: 3, history: 4 };
const DEFAULT_PANEL = "home";

const I18N = {
  en: {
    user: "User",
    admin: "admin",
    copy_from: "Copy layout from",
    copy_none: "—",
    items: "Sidebar items",
    items_hint: "Drag or use the arrows to reorder. Untick to hide.",
    admin_only: "admin only",
    admin_only_hint: "This user is not an admin: admin-only items are never shown to them.",
    default_panel: "Default dashboard",
    default_none: "Home Assistant default",
    lock: "Lock this layout",
    lock_hint: "If the user changes the sidebar from their profile, it is reset to this layout.",
    apply_also: "Apply also to",
    save: "Save",
    reset: "Restore default",
    reset_confirm: "Click again to confirm",
    saved: "Saved. Open sessions update immediately.",
    reset_done: "Default sidebar restored.",
    unsaved: "Unsaved changes",
    loading: "Loading…",
    up: "Move up",
    down: "Move down",
  },
  it: {
    user: "Utente",
    admin: "admin",
    copy_from: "Copia layout da",
    copy_none: "—",
    items: "Voci della barra laterale",
    items_hint: "Trascina o usa le frecce per riordinare. Togli la spunta per nascondere.",
    admin_only: "solo admin",
    admin_only_hint: "Questo utente non è amministratore: le voci solo admin non gli vengono mai mostrate.",
    default_panel: "Dashboard predefinita",
    default_none: "Predefinita di Home Assistant",
    lock: "Blocca questo layout",
    lock_hint: "Se l'utente modifica la barra laterale dal suo profilo, viene riportata a questo layout.",
    apply_also: "Applica anche a",
    save: "Salva",
    reset: "Ripristina predefinita",
    reset_confirm: "Clicca di nuovo per confermare",
    saved: "Salvato. Le sessioni aperte si aggiornano subito.",
    reset_done: "Barra laterale predefinita ripristinata.",
    unsaved: "Modifiche non salvate",
    loading: "Caricamento…",
    up: "Sposta su",
    down: "Sposta giù",
  },
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class SidebarManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._users = null;
    this._userId = null;
    this._items = [];
    this._default = "";
    this._lock = false;
    this._dirty = false;
    this._status = "";
    this._error = "";
    this._applyTo = new Set();
    this._confirmReset = false;
    this._dragIdx = null;
    this._bound = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menu) this._menu.hass = hass;
    if (first) this._init();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) this._menu.narrow = narrow;
  }

  set panel(_panel) {}

  _t(key) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").startsWith("it") ? "it" : "en";
    return I18N[lang][key] ?? I18N.en[key] ?? key;
  }

  async _init() {
    this._render();
    try {
      const users = await this._hass.callWS({ type: "config/auth/list" });
      this._users = users
        .filter((u) => !u.system_generated && u.is_active)
        .sort((a, b) => a.name.localeCompare(b.name));
      const start = this._users.find((u) => u.id === this._hass.user?.id) || this._users[0];
      if (start) await this._selectUser(start.id);
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  _user(id = this._userId) {
    return this._users?.find((u) => u.id === id);
  }

  _panels() {
    return Object.values(this._hass.panels).filter(
      (p) => p.title && p.show_in_sidebar !== false && !FIXED_PANELS.includes(p.url_path)
    );
  }

  _title(panel) {
    return this._hass.localize(`panel.${panel.title}`) || panel.title;
  }

  // Same fallback ordering as Home Assistant's ha-sidebar
  _defaultSort(a, b, defaultPanel) {
    if (a.url_path === defaultPanel) return -1;
    if (b.url_path === defaultPanel) return 1;
    const aL = a.component_name === "lovelace";
    const bL = b.component_name === "lovelace";
    if (aL && bL) return this._title(a).localeCompare(this._title(b));
    if (aL) return -1;
    if (bL) return 1;
    const aB = a.url_path in BUILTIN_SORT;
    const bB = b.url_path in BUILTIN_SORT;
    if (aB && bB) return BUILTIN_SORT[a.url_path] - BUILTIN_SORT[b.url_path];
    if (aB) return -1;
    if (bB) return 1;
    return this._title(a).localeCompare(this._title(b));
  }

  _buildItems(order, hidden) {
    order = order || [];
    hidden = hidden || [];
    const def = this._default || DEFAULT_PANEL;
    const panels = this._panels().sort((a, b) => {
      const ia = order.indexOf(a.url_path);
      const ib = order.indexOf(b.url_path);
      if (ia !== -1 || ib !== -1) {
        if (ia === -1) return 1;
        if (ib === -1) return -1;
        return ia - ib;
      }
      return this._defaultSort(a, b, def);
    });
    return panels.map((p) => ({
      url_path: p.url_path,
      title: this._title(p),
      icon: p.icon,
      admin: !!p.require_admin,
      visible: !hidden.includes(p.url_path) && !(p.default_visible === false && !order.includes(p.url_path)),
    }));
  }

  async _load(userId) {
    return this._hass.callWS({ type: "sidebar_manager/get", user_id: userId });
  }

  async _selectUser(userId) {
    this._userId = userId;
    this._status = "";
    this._error = "";
    this._confirmReset = false;
    this._applyTo = new Set();
    const cfg = await this._load(userId);
    this._default = cfg.default_panel || "";
    this._lock = !!cfg.locked;
    this._items = this._buildItems(cfg.panel_order, cfg.hidden_panels);
    this._dirty = false;
  }

  async _copyFrom(userId) {
    const cfg = await this._load(userId);
    this._default = cfg.default_panel || "";
    this._items = this._buildItems(cfg.panel_order, cfg.hidden_panels);
    this._changed();
  }

  _changed() {
    this._dirty = true;
    this._status = "";
    this._confirmReset = false;
    this._render();
  }

  _move(from, to) {
    if (to < 0 || to >= this._items.length || from === to) return;
    const [item] = this._items.splice(from, 1);
    this._items.splice(to, 0, item);
    this._changed();
  }

  async _save() {
    try {
      await this._hass.callWS({
        type: "sidebar_manager/save",
        user_ids: [this._userId, ...this._applyTo],
        panel_order: this._items.map((i) => i.url_path),
        hidden_panels: this._items.filter((i) => !i.visible).map((i) => i.url_path),
        default_panel: this._default || null,
        lock: this._lock,
      });
      this._dirty = false;
      this._applyTo = new Set();
      this._status = this._t("saved");
      this._error = "";
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _reset() {
    if (!this._confirmReset) {
      this._confirmReset = true;
      this._render();
      return;
    }
    try {
      await this._hass.callWS({ type: "sidebar_manager/reset", user_id: this._userId });
      await this._selectUser(this._userId);
      this._status = this._t("reset_done");
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  _bindEvents() {
    if (this._bound) return;
    this._bound = true;
    const root = this.shadowRoot;

    root.addEventListener("change", async (ev) => {
      const el = ev.target;
      const id = el.dataset.action;
      if (id === "user") {
        await this._selectUser(el.value);
        this._render();
      } else if (id === "copy" && el.value) {
        await this._copyFrom(el.value);
      } else if (id === "visible") {
        this._items[+el.dataset.idx].visible = el.checked;
        this._changed();
      } else if (id === "default") {
        this._default = el.value;
        this._changed();
      } else if (id === "lock") {
        this._lock = el.checked;
        this._changed();
      } else if (id === "apply") {
        if (el.checked) this._applyTo.add(el.value);
        else this._applyTo.delete(el.value);
        this._dirty = true;
      }
    });

    root.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-click]");
      if (!btn) return;
      const idx = +btn.dataset.idx;
      switch (btn.dataset.click) {
        case "up":
          this._move(idx, idx - 1);
          break;
        case "down":
          this._move(idx, idx + 1);
          break;
        case "save":
          this._save();
          break;
        case "reset":
          this._reset();
          break;
      }
    });

    root.addEventListener("dragstart", (ev) => {
      const row = ev.target.closest(".item");
      if (!row) return;
      this._dragIdx = +row.dataset.idx;
      ev.dataTransfer.effectAllowed = "move";
      row.classList.add("dragging");
    });
    root.addEventListener("dragover", (ev) => {
      if (this._dragIdx !== null && ev.target.closest(".item")) ev.preventDefault();
    });
    root.addEventListener("drop", (ev) => {
      const row = ev.target.closest(".item");
      if (!row || this._dragIdx === null) return;
      ev.preventDefault();
      const from = this._dragIdx;
      this._dragIdx = null;
      this._move(from, +row.dataset.idx);
    });
    root.addEventListener("dragend", () => {
      this._dragIdx = null;
      root.querySelectorAll(".dragging").forEach((r) => r.classList.remove("dragging"));
    });
  }

  _render() {
    this._bindEvents();
    const t = (k) => this._t(k);
    const user = this._user();
    const others = (this._users || []).filter((u) => u.id !== this._userId);
    const userLabel = (u) => `${esc(u.name)}${u.group_ids?.includes("system-admin") ? ` (${t("admin")})` : ""}`;
    const targetIsAdmin = user?.group_ids?.includes("system-admin");

    let body;
    if (this._error && !this._users) {
      body = `<div class="error">${esc(this._error)}</div>`;
    } else if (!this._users || !user) {
      body = `<p>${t("loading")}</p>`;
    } else {
      body = `
        <div class="card">
          <label class="field">
            <span>${t("user")}</span>
            <select data-action="user">
              ${this._users.map((u) => `<option value="${esc(u.id)}" ${u.id === this._userId ? "selected" : ""}>${userLabel(u)}</option>`).join("")}
            </select>
          </label>
          ${others.length ? `
          <label class="field">
            <span>${t("copy_from")}</span>
            <select data-action="copy">
              <option value="">${t("copy_none")}</option>
              ${others.map((u) => `<option value="${esc(u.id)}">${userLabel(u)}</option>`).join("")}
            </select>
          </label>` : ""}
        </div>

        <div class="card">
          <h2>${t("items")}</h2>
          <p class="hint">${t("items_hint")}</p>
          ${!targetIsAdmin && this._items.some((i) => i.admin) ? `<p class="hint">${t("admin_only_hint")}</p>` : ""}
          <ul class="list">
            ${this._items.map((i, idx) => `
              <li class="item ${i.visible ? "" : "hidden"} ${i.admin && !targetIsAdmin ? "na" : ""}" draggable="true" data-idx="${idx}">
                <ha-icon class="grip" icon="mdi:drag"></ha-icon>
                <input type="checkbox" data-action="visible" data-idx="${idx}" ${i.visible ? "checked" : ""} />
                <ha-icon icon="${esc(i.icon || "mdi:view-dashboard")}"></ha-icon>
                <span class="title">${esc(i.title)}</span>
                ${i.admin ? `<span class="chip">${t("admin_only")}</span>` : ""}
                <span class="path">/${esc(i.url_path)}</span>
                <button class="icon" data-click="up" data-idx="${idx}" title="${t("up")}" ${idx === 0 ? "disabled" : ""}><ha-icon icon="mdi:chevron-up"></ha-icon></button>
                <button class="icon" data-click="down" data-idx="${idx}" title="${t("down")}" ${idx === this._items.length - 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-down"></ha-icon></button>
              </li>`).join("")}
          </ul>
        </div>

        <div class="card">
          <label class="field">
            <span>${t("default_panel")}</span>
            <select data-action="default">
              <option value="" ${!this._default ? "selected" : ""}>${t("default_none")}</option>
              ${this._items.map((i) => `<option value="${esc(i.url_path)}" ${i.url_path === this._default ? "selected" : ""}>${esc(i.title)}</option>`).join("")}
            </select>
          </label>
          <label class="check">
            <input type="checkbox" data-action="lock" ${this._lock ? "checked" : ""} />
            <span>${t("lock")}<br /><small class="hint">${t("lock_hint")}</small></span>
          </label>
          ${others.length ? `
          <details>
            <summary>${t("apply_also")}</summary>
            ${others.map((u) => `
              <label class="check"><input type="checkbox" data-action="apply" value="${esc(u.id)}" ${this._applyTo.has(u.id) ? "checked" : ""} /> <span>${userLabel(u)}</span></label>`).join("")}
          </details>` : ""}
        </div>

        <div class="actions">
          <button class="primary" data-click="save">${t("save")}</button>
          <button class="secondary" data-click="reset">${this._confirmReset ? t("reset_confirm") : t("reset")}</button>
          <span class="status">${this._error ? `<span class="error">${esc(this._error)}</span>` : this._dirty ? t("unsaved") : esc(this._status)}</span>
        </div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; min-height: 100%; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--ha-font-family-body, Roboto, sans-serif); }
        .toolbar { display: flex; align-items: center; height: var(--header-height, 56px); padding: 0 12px; background: var(--app-header-background-color); color: var(--app-header-text-color, var(--text-primary-color)); border-bottom: var(--app-header-border-bottom, none); font-size: 20px; }
        .toolbar .title { margin-left: 12px; }
        .content { max-width: 760px; margin: 0 auto; padding: 16px; }
        .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color); padding: 16px; margin-bottom: 16px; }
        h2 { margin: 0 0 4px; font-size: 16px; font-weight: 500; }
        .hint { color: var(--secondary-text-color); font-size: 13px; margin: 4px 0 8px; }
        .field { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
        .field > span { min-width: 170px; }
        select { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font-size: 14px; }
        .list { list-style: none; margin: 0; padding: 0; }
        .item { display: flex; align-items: center; gap: 8px; padding: 6px 4px; border-bottom: 1px solid var(--divider-color); cursor: grab; }
        .item:last-child { border-bottom: none; }
        .item.hidden .title, .item.hidden > ha-icon:not(.grip) { opacity: 0.45; }
        .item.na .title { text-decoration: line-through; }
        .item.dragging { opacity: 0.4; }
        .grip { color: var(--secondary-text-color); --mdc-icon-size: 20px; }
        .title { flex: 1; }
        .path { color: var(--secondary-text-color); font-size: 12px; font-family: monospace; }
        .chip { font-size: 11px; padding: 2px 6px; border-radius: 8px; background: var(--secondary-background-color); color: var(--secondary-text-color); }
        button.icon { background: none; border: none; color: var(--primary-text-color); cursor: pointer; padding: 2px; border-radius: 50%; }
        button.icon[disabled] { opacity: 0.25; cursor: default; }
        .check { display: flex; align-items: flex-start; gap: 8px; margin: 12px 0; }
        details { margin-top: 8px; }
        summary { cursor: pointer; color: var(--primary-color); }
        .actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        button.primary, button.secondary { padding: 10px 18px; border-radius: 18px; font-size: 14px; cursor: pointer; border: 1px solid var(--primary-color); }
        button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        button.secondary { background: none; color: var(--primary-color); }
        .status { color: var(--secondary-text-color); font-size: 13px; }
        .error { color: var(--error-color, #db4437); }
        input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--primary-color); }
        @media (max-width: 600px) { .field { flex-direction: column; align-items: stretch; } .path { display: none; } }
      </style>
      <div class="toolbar"><span id="menu"></span><span class="title">Sidebar Manager</span></div>
      <div class="content">${body}</div>`;

    this._menu = document.createElement("ha-menu-button");
    this._menu.hass = this._hass;
    this._menu.narrow = this._narrow;
    this.shadowRoot.getElementById("menu").appendChild(this._menu);
  }
}

if (!customElements.get("sidebar-manager-panel")) {
  customElements.define("sidebar-manager-panel", SidebarManagerPanel);
}
