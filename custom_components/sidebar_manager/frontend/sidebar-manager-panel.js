/* Sidebar Manager panel – admin UI for sidebar profiles. No build step. */

const FIXED_PANELS = ["profile", "config", "notfound"];
const BUILTIN_SORT = { energy: 1, map: 2, logbook: 3, history: 4 };
const DEFAULT_PANEL = "home";

const I18N = {
  en: {
    tab_profiles: "Profiles",
    tab_users: "Users",
    new: "New",
    duplicate: "Duplicate",
    delete: "Delete",
    delete_confirm: "Click again to delete",
    delete_default: "The default profile can't be deleted: untick “Default profile” and save first.",
    no_profiles: "No profiles yet. Create one with New.",
    new_profile: "New profile",
    copy_suffix: " (copy)",
    name: "Name",
    name_required: "Enter a name for the profile.",
    user_one: "1 user",
    user_many: "{n} users",
    default_badge: "default",
    locked: "Locked",
    items: "Sidebar items",
    items_hint: "Drag or use the arrows to reorder. Untick to hide.",
    admin_only: "admin only",
    admin_only_hint: "This profile has non-admin users: admin-only items are never shown to them.",
    default_panel: "Default dashboard",
    default_none: "Home Assistant default",
    default_chip: "default",
    default_always: "The default dashboard is always shown: Home Assistant doesn't let it be hidden. To hide a dashboard, pick another default.",
    lock: "Lock",
    lock_hint: "If a user changes their sidebar from their profile page, it's reset to this profile.",
    new_items: "New items",
    new_items_show: "Show (at the bottom)",
    new_items_hide: "Hide",
    new_items_hint: "Dashboards and panels added after this profile was saved.",
    is_default: "Default profile",
    is_default_hint: "Applied to every user without a profile, including users created later.",
    users: "Users",
    users_hint: "Tick the users who get this profile.",
    in_profile: "now in “{name}”: ticking moves them here",
    via_default: "gets it as the default profile",
    save: "Save",
    saved: "Saved. Open sessions update immediately.",
    deleted: "Profile deleted.",
    unsaved: "Unsaved changes",
    discard_confirm: "Unsaved changes: click again to discard them",
    loading: "Loading…",
    up: "Move up",
    down: "Move down",
    admin: "admin",
    inactive: "disabled",
    user: "User",
    profile: "Profile",
    applied: "Sidebar in use",
    users_tab_hint: "Changes apply immediately.",
    none_option: "None (Home Assistant default)",
    applies_default: "Default profile: {name}",
    applies_none: "Home Assistant default",
  },
  it: {
    tab_profiles: "Profili",
    tab_users: "Utenti",
    new: "Nuovo",
    duplicate: "Duplica",
    delete: "Elimina",
    delete_confirm: "Clicca di nuovo per eliminare",
    delete_default: "Il profilo predefinito non si può eliminare: togli la spunta da “Profilo predefinito” e salva.",
    no_profiles: "Nessun profilo. Creane uno con Nuovo.",
    new_profile: "Nuovo profilo",
    copy_suffix: " (copia)",
    name: "Nome",
    name_required: "Inserisci un nome per il profilo.",
    user_one: "1 utente",
    user_many: "{n} utenti",
    default_badge: "predefinito",
    locked: "Bloccato",
    items: "Voci della barra laterale",
    items_hint: "Trascina o usa le frecce per riordinare. Togli la spunta per nascondere.",
    admin_only: "solo admin",
    admin_only_hint: "Questo profilo ha utenti non amministratori: le voci solo admin non vengono mai mostrate a loro.",
    default_panel: "Dashboard predefinita",
    default_none: "Predefinita di Home Assistant",
    default_chip: "predefinita",
    default_always: "La dashboard predefinita è sempre visibile: Home Assistant non permette di nasconderla. Per nascondere una dashboard, scegline un'altra come predefinita.",
    lock: "Blocca",
    lock_hint: "Se un utente modifica la barra laterale dal suo profilo, viene riportata a questo profilo.",
    new_items: "Nuove voci",
    new_items_show: "Mostra (in fondo)",
    new_items_hide: "Nascondi",
    new_items_hint: "Dashboard e pannelli aggiunti dopo il salvataggio del profilo.",
    is_default: "Profilo predefinito",
    is_default_hint: "Si applica a tutti gli utenti senza profilo, anche a quelli creati in futuro.",
    users: "Utenti",
    users_hint: "Spunta gli utenti a cui assegnare questo profilo.",
    in_profile: "ora in “{name}”: la spunta lo sposta qui",
    via_default: "lo riceve come profilo predefinito",
    save: "Salva",
    saved: "Salvato. Le sessioni aperte si aggiornano subito.",
    deleted: "Profilo eliminato.",
    unsaved: "Modifiche non salvate",
    discard_confirm: "Modifiche non salvate: clicca di nuovo per scartarle",
    loading: "Caricamento…",
    up: "Sposta su",
    down: "Sposta giù",
    admin: "admin",
    inactive: "disattivato",
    user: "Utente",
    profile: "Profilo",
    applied: "Barra in uso",
    users_tab_hint: "Le modifiche valgono subito.",
    none_option: "Nessuno (predefinita di HA)",
    applies_default: "Profilo predefinito: {name}",
    applies_none: "Predefinita di Home Assistant",
  },
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const errMsg = (err) => err?.message || String(err);

class SidebarManagerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null; // result of sidebar_manager/profiles
    this._tab = "profiles";
    this._draft = null; // profile being edited; id null for a new one
    this._dirty = false;
    this._status = "";
    this._error = "";
    this._confirmDelete = false;
    this._confirmDiscard = null;
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

  _t(key, vars = {}) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").startsWith("it") ? "it" : "en";
    const text = I18N[lang][key] ?? I18N.en[key] ?? key;
    return text.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
  }

  async _init() {
    this._render();
    await this._reload();
    const first = this._profileIds()[0];
    if (first) this._draft = this._draftFrom(first);
    this._render();
  }

  async _reload() {
    try {
      this._data = await this._hass.callWS({ type: "sidebar_manager/profiles" });
    } catch (err) {
      this._error = errMsg(err);
    }
  }

  // ---- data helpers -------------------------------------------------------

  _profiles() {
    return this._data?.profiles || {};
  }

  _profileIds() {
    const profiles = this._profiles();
    return Object.keys(profiles).sort((a, b) => profiles[a].name.localeCompare(profiles[b].name));
  }

  _users() {
    return [...(this._data?.users || [])].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }

  // The backend refuses to delete the profile that is saved as default
  _savedDefault() {
    return !!(this._draft?.id && this._profiles()[this._draft.id]?.is_default);
  }

  _userCount(profileId) {
    return this._users().filter((u) => u.effective_profile_id === profileId).length;
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

  // Panels the profile doesn't know yet (added after it was saved) go to the
  // bottom, visible or hidden according to its "new items" setting.
  _buildItems(order, hidden, newItems, defaultPanel) {
    const def = defaultPanel || DEFAULT_PANEL;
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
    return panels.map((p) => {
      const known = order.includes(p.url_path) || hidden.includes(p.url_path);
      return {
        url_path: p.url_path,
        title: this._title(p),
        icon: p.icon,
        admin: !!p.require_admin,
        visible: !hidden.includes(p.url_path) && (known || (newItems !== "hide" && p.default_visible !== false)),
      };
    });
  }

  // The dashboard Home Assistant opens for the profile's users. Its sidebar
  // always shows it, even when hidden (same rule as getDefaultPanelUrlPath).
  _effectiveDefault(defaultPanel) {
    const panel = defaultPanel || this._hass.systemData?.default_panel || DEFAULT_PANEL;
    if (panel === "lovelace" && !this._hass.panels.lovelace?.config) return DEFAULT_PANEL;
    return panel;
  }

  _showDefault(draft) {
    const def = this._effectiveDefault(draft.default);
    draft.items.forEach((i) => {
      if (i.url_path === def) i.visible = true;
    });
    return draft;
  }

  _draftFrom(id) {
    const p = this._profiles()[id];
    return this._showDefault({
      id,
      name: p.name,
      items: this._buildItems(p.panel_order, p.hidden_panels, p.new_items, p.default_panel),
      default: p.default_panel || "",
      lock: p.lock,
      new_items: p.new_items,
      is_default: p.is_default,
      users: new Set(this._users().filter((u) => u.profile_id === id).map((u) => u.id)),
    });
  }

  _newDraft() {
    return this._showDefault({
      id: null,
      name: "",
      items: this._buildItems([], [], "show", ""),
      default: "",
      lock: false,
      new_items: "show",
      is_default: false,
      users: new Set(),
    });
  }

  // ---- actions ------------------------------------------------------------

  _resetMessages() {
    this._status = "";
    this._error = "";
    this._confirmDelete = false;
    this._confirmDiscard = null;
  }

  // Run an action that would drop unsaved changes only after a second click
  _guarded(key, run) {
    if (this._dirty && this._confirmDiscard !== key) {
      this._confirmDiscard = key;
      this._confirmDelete = false;
      this._render();
      return;
    }
    this._resetMessages();
    this._dirty = false;
    run();
    this._render();
  }

  _select(id) {
    if (!id || this._draft?.id === id) return;
    this._guarded(`select:${id}`, () => {
      this._draft = this._draftFrom(id);
    });
  }

  _new() {
    this._guarded("new", () => {
      this._draft = this._newDraft();
      this._dirty = true;
    });
  }

  _duplicate() {
    if (!this._draft) return;
    this._guarded("duplicate", () => {
      const src = this._draft;
      this._draft = {
        ...src,
        id: null,
        name: `${src.name || this._t("new_profile")}${this._t("copy_suffix")}`,
        items: src.items.map((i) => ({ ...i })),
        is_default: false,
        users: new Set(),
      };
      this._dirty = true;
    });
  }

  _changed() {
    this._dirty = true;
    this._resetMessages();
    this._render();
  }

  _move(from, to) {
    const items = this._draft.items;
    if (to < 0 || to >= items.length || from === to) return;
    const [item] = items.splice(from, 1);
    items.splice(to, 0, item);
    this._changed();
  }

  async _save() {
    const d = this._showDefault(this._draft);
    this._resetMessages();
    if (!d.name.trim()) {
      this._error = this._t("name_required");
      this._render();
      return;
    }
    const msg = {
      type: "sidebar_manager/profile/save",
      name: d.name.trim(),
      panel_order: d.items.map((i) => i.url_path),
      hidden_panels: d.items.filter((i) => !i.visible).map((i) => i.url_path),
      default_panel: d.default || null,
      lock: d.lock,
      new_items: d.new_items,
      is_default: d.is_default,
      user_ids: [...d.users],
    };
    if (d.id) msg.profile_id = d.id;
    try {
      const res = await this._hass.callWS(msg);
      await this._reload();
      this._draft = this._draftFrom(res.profile_id);
      this._dirty = false;
      this._status = this._t("saved");
    } catch (err) {
      this._error = errMsg(err);
    }
    this._render();
  }

  async _delete() {
    const d = this._draft;
    if (!d || this._savedDefault()) return;
    if (!this._confirmDelete) {
      this._confirmDelete = true;
      this._confirmDiscard = null;
      this._render();
      return;
    }
    this._resetMessages();
    try {
      if (d.id) {
        await this._hass.callWS({ type: "sidebar_manager/profile/delete", profile_id: d.id });
        await this._reload();
        this._status = this._t("deleted");
      }
      const first = this._profileIds()[0];
      this._draft = first ? this._draftFrom(first) : null;
      this._dirty = false;
    } catch (err) {
      this._error = errMsg(err);
    }
    this._render();
  }

  async _assign(userId, profileId) {
    this._resetMessages();
    try {
      await this._hass.callWS({ type: "sidebar_manager/assign", user_id: userId, profile_id: profileId || null });
      await this._reload();
      if (this._draft?.id && !this._dirty) this._draft = this._draftFrom(this._draft.id);
      this._status = this._t("saved");
    } catch (err) {
      this._error = errMsg(err);
    }
    this._render();
  }

  _updateStatus() {
    const el = this.shadowRoot.querySelector(".status");
    if (el) el.innerHTML = this._statusHtml();
  }

  _statusHtml() {
    if (this._error) return `<span class="error">${esc(this._error)}</span>`;
    if (this._confirmDiscard) return `<span class="warn">${esc(this._t("discard_confirm"))}</span>`;
    if (this._dirty && this._tab === "profiles") return esc(this._t("unsaved"));
    return esc(this._status);
  }

  // ---- events -------------------------------------------------------------

  _bindEvents() {
    if (this._bound) return;
    this._bound = true;
    const root = this.shadowRoot;

    // Text input updates the draft without re-rendering, to keep the focus
    root.addEventListener("input", (ev) => {
      if (ev.target.dataset.action !== "name") return;
      this._draft.name = ev.target.value;
      this._dirty = true;
      this._resetMessages();
      this._updateStatus();
    });

    root.addEventListener("change", (ev) => {
      const el = ev.target;
      const d = this._draft;
      switch (el.dataset.action) {
        case "visible":
          d.items[+el.dataset.idx].visible = el.checked;
          this._changed();
          break;
        case "default":
          d.default = el.value;
          this._showDefault(d);
          this._changed();
          break;
        case "lock":
          d.lock = el.checked;
          this._changed();
          break;
        case "new_items":
          d.new_items = el.value;
          this._changed();
          break;
        case "is_default":
          d.is_default = el.checked;
          this._changed();
          break;
        case "member":
          if (el.checked) d.users.add(el.value);
          else d.users.delete(el.value);
          this._changed();
          break;
        case "assign":
          this._assign(el.dataset.user, el.value);
          break;
      }
    });

    root.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-click]");
      if (!btn || btn.disabled) return;
      const idx = +btn.dataset.idx;
      switch (btn.dataset.click) {
        case "tab":
          this._tab = btn.dataset.tab;
          this._confirmDelete = false;
          this._confirmDiscard = null;
          this._render();
          break;
        case "select":
          this._select(btn.dataset.id);
          break;
        case "new":
          this._new();
          break;
        case "duplicate":
          this._duplicate();
          break;
        case "delete":
          this._delete();
          break;
        case "up":
          this._move(idx, idx - 1);
          break;
        case "down":
          this._move(idx, idx + 1);
          break;
        case "save":
          this._save();
          break;
      }
    });

    root.addEventListener("dragstart", (ev) => {
      const row = ev.target.closest?.(".item");
      if (!row) return;
      this._dragIdx = +row.dataset.idx;
      ev.dataTransfer.effectAllowed = "move";
      row.classList.add("dragging");
    });
    root.addEventListener("dragover", (ev) => {
      if (this._dragIdx !== null && ev.target.closest?.(".item")) ev.preventDefault();
    });
    root.addEventListener("drop", (ev) => {
      const row = ev.target.closest?.(".item");
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

  // ---- rendering ----------------------------------------------------------

  _userLabel(u) {
    const t = (k) => this._t(k);
    return `${esc(u.name || u.id)}${u.is_admin ? ` <span class="chip">${t("admin")}</span>` : ""}${
      u.is_active ? "" : ` <span class="chip">${t("inactive")}</span>`
    }`;
  }

  _renderProfileList() {
    const t = (k, v) => this._t(k, v);
    const profiles = this._profiles();
    const d = this._draft;
    const entries = this._profileIds().map((id) => {
      const p = profiles[id];
      const n = this._userCount(id);
      return `
        <li><button class="entry ${d?.id === id ? "selected" : ""}" data-click="select" data-id="${esc(id)}">
          <span class="entry-name">${esc(p.name)}</span>
          ${p.lock ? `<ha-icon icon="mdi:lock" title="${t("locked")}"></ha-icon>` : ""}
          ${p.is_default ? `<span class="chip accent">${t("default_badge")}</span>` : ""}
          <span class="count">${n === 1 ? t("user_one") : t("user_many", { n })}</span>
        </button></li>`;
    });
    if (d && !d.id) {
      entries.unshift(`
        <li><button class="entry selected new" data-click="select" data-id="">
          <span class="entry-name">${esc(d.name || t("new_profile"))}</span>
        </button></li>`);
    }
    return `
      <div class="card side">
        <div class="side-actions">
          <button class="secondary small" data-click="new"><ha-icon icon="mdi:plus"></ha-icon>${t("new")}</button>
          <button class="secondary small" data-click="duplicate" ${d ? "" : "disabled"}><ha-icon icon="mdi:content-copy"></ha-icon>${t("duplicate")}</button>
          <button class="secondary small danger" data-click="delete" ${d && !this._savedDefault() ? "" : "disabled"}>
            <ha-icon icon="mdi:delete"></ha-icon>${this._confirmDelete ? t("delete_confirm") : t("delete")}
          </button>
        </div>
        ${this._savedDefault() ? `<p class="hint">${t("delete_default")}</p>` : ""}
        ${entries.length ? `<ul class="entries">${entries.join("")}</ul>` : `<p class="hint">${t("no_profiles")}</p>`}
      </div>`;
  }

  _renderEditor() {
    const t = (k, v) => this._t(k, v);
    const d = this._draft;
    if (!d) return "";
    const profiles = this._profiles();
    const users = this._users();
    const def = this._effectiveDefault(d.default);
    // Users who would get this profile once saved
    const affected = users.filter((u) => d.users.has(u.id) || (d.is_default && !u.profile_id));
    const adminNote = d.items.some((i) => i.admin) && affected.some((u) => !u.is_admin);
    const userRows = users.map((u) => {
      let note = "";
      if (u.profile_id && u.profile_id !== d.id && profiles[u.profile_id]) {
        note = t("in_profile", { name: esc(profiles[u.profile_id].name) });
      } else if (!d.users.has(u.id) && !u.profile_id && d.is_default) {
        note = t("via_default");
      }
      return `
        <label class="check">
          <input type="checkbox" data-action="member" value="${esc(u.id)}" ${d.users.has(u.id) ? "checked" : ""} />
          <span>${this._userLabel(u)}${note ? `<br /><small class="hint">${note}</small>` : ""}</span>
        </label>`;
    });

    return `
      <div class="editor">
        <div class="card">
          <label class="field">
            <span>${t("name")}</span>
            <input type="text" data-action="name" value="${esc(d.name)}" placeholder="${esc(t("new_profile"))}" />
          </label>
          <label class="field">
            <span>${t("default_panel")}</span>
            <select data-action="default">
              <option value="" ${!d.default ? "selected" : ""}>${t("default_none")}</option>
              ${d.items.map((i) => `<option value="${esc(i.url_path)}" ${i.url_path === d.default ? "selected" : ""}>${esc(i.title)}</option>`).join("")}
            </select>
          </label>
        </div>

        <div class="card">
          <h2>${t("items")}</h2>
          <p class="hint">${t("items_hint")}</p>
          ${d.items.some((i) => i.url_path === def) ? `<p class="hint">${t("default_always")}</p>` : ""}
          ${adminNote ? `<p class="hint warn">${t("admin_only_hint")}</p>` : ""}
          <ul class="list">
            ${d.items.map((i, idx) => `
              <li class="item ${i.visible ? "" : "hidden"}" draggable="true" data-idx="${idx}">
                <ha-icon class="grip" icon="mdi:drag"></ha-icon>
                <input type="checkbox" data-action="visible" data-idx="${idx}" ${i.visible ? "checked" : ""} ${i.url_path === def ? "disabled" : ""} />
                <ha-icon icon="${esc(i.icon || "mdi:view-dashboard")}"></ha-icon>
                <span class="title">${esc(i.title)}</span>
                ${i.url_path === def ? `<span class="chip accent">${t("default_chip")}</span>` : ""}
                ${i.admin ? `<span class="chip">${t("admin_only")}</span>` : ""}
                <span class="path">/${esc(i.url_path)}</span>
                <button class="icon" data-click="up" data-idx="${idx}" title="${t("up")}" ${idx === 0 ? "disabled" : ""}><ha-icon icon="mdi:chevron-up"></ha-icon></button>
                <button class="icon" data-click="down" data-idx="${idx}" title="${t("down")}" ${idx === d.items.length - 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-down"></ha-icon></button>
              </li>`).join("")}
          </ul>
        </div>

        <div class="card">
          <label class="field">
            <span>${t("new_items")}<br /><small class="hint">${t("new_items_hint")}</small></span>
            <select data-action="new_items">
              <option value="show" ${d.new_items === "show" ? "selected" : ""}>${t("new_items_show")}</option>
              <option value="hide" ${d.new_items === "hide" ? "selected" : ""}>${t("new_items_hide")}</option>
            </select>
          </label>
          <label class="check">
            <input type="checkbox" data-action="lock" ${d.lock ? "checked" : ""} />
            <span>${t("lock")}<br /><small class="hint">${t("lock_hint")}</small></span>
          </label>
          <label class="check">
            <input type="checkbox" data-action="is_default" ${d.is_default ? "checked" : ""} />
            <span>${t("is_default")}<br /><small class="hint">${t("is_default_hint")}</small></span>
          </label>
        </div>

        <div class="card">
          <h2>${t("users")}</h2>
          <p class="hint">${t("users_hint")}</p>
          ${userRows.join("")}
        </div>

        <div class="actions">
          <button class="primary" data-click="save">${t("save")}</button>
          <span class="status">${this._statusHtml()}</span>
        </div>
      </div>`;
  }

  _renderProfilesTab() {
    const status = this._draft ? "" : `<div class="actions"><span class="status">${this._statusHtml()}</span></div>`;
    return `<div class="layout">${this._renderProfileList()}<div>${this._renderEditor()}${status}</div></div>`;
  }

  _renderUsersTab() {
    const t = (k, v) => this._t(k, v);
    const profiles = this._profiles();
    const ids = this._profileIds();
    const rows = this._users().map((u) => {
      let applied;
      if (u.source === "assigned") applied = esc(profiles[u.profile_id]?.name);
      else if (u.source === "default") applied = t("applies_default", { name: esc(profiles[u.effective_profile_id]?.name) });
      else applied = t("applies_none");
      return `
        <tr>
          <td>${this._userLabel(u)}</td>
          <td>
            <select data-action="assign" data-user="${esc(u.id)}">
              <option value="" ${u.profile_id ? "" : "selected"}>${t("none_option")}</option>
              ${ids.map((id) => `<option value="${esc(id)}" ${u.profile_id === id ? "selected" : ""}>${esc(profiles[id].name)}</option>`).join("")}
            </select>
            <div class="applied ${u.source}">${t("applied")}: ${applied}</div>
          </td>
        </tr>`;
    });
    return `
      <div class="card">
        <p class="hint">${t("users_tab_hint")}</p>
        <table>
          <thead><tr><th>${t("user")}</th><th>${t("profile")}</th></tr></thead>
          <tbody>${rows.join("")}</tbody>
        </table>
      </div>
      <div class="actions"><span class="status">${this._statusHtml()}</span></div>`;
  }

  _render() {
    this._bindEvents();
    const t = (k) => this._t(k);

    let body;
    if (this._error && !this._data) {
      body = `<div class="card error">${esc(this._error)}</div>`;
    } else if (!this._data) {
      body = `<p>${t("loading")}</p>`;
    } else {
      body = this._tab === "users" ? this._renderUsersTab() : this._renderProfilesTab();
    }

    const tab = (id, label) =>
      `<button class="tab ${this._tab === id ? "active" : ""}" data-click="tab" data-tab="${id}">${t(label)}</button>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; min-height: 100%; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--ha-font-family-body, Roboto, sans-serif); }
        .toolbar { display: flex; align-items: center; height: var(--header-height, 56px); padding: 0 12px; background: var(--app-header-background-color); color: var(--app-header-text-color, var(--text-primary-color)); border-bottom: var(--app-header-border-bottom, none); font-size: 20px; }
        .toolbar .title { margin-left: 12px; }
        .tabs { display: flex; gap: 4px; padding: 0 16px; border-bottom: 1px solid var(--divider-color); background: var(--app-header-background-color); }
        .tab { background: none; border: none; border-bottom: 2px solid transparent; color: var(--app-header-text-color, var(--text-primary-color)); opacity: 0.75; padding: 12px 16px; font-size: 14px; cursor: pointer; }
        .tab.active { opacity: 1; border-bottom-color: var(--app-header-text-color, var(--text-primary-color)); }
        .content { max-width: 1100px; margin: 0 auto; padding: 16px; }
        .layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 16px; align-items: start; }
        .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color); padding: 16px; margin-bottom: 16px; }
        h2 { margin: 0 0 4px; font-size: 16px; font-weight: 500; }
        .hint { color: var(--secondary-text-color); font-size: 13px; margin: 4px 0 8px; }
        .warn { color: var(--warning-color, #ffa600); }
        .field { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
        .field > span { min-width: 170px; max-width: 240px; }
        select, input[type="text"] { flex: 1; min-width: 0; padding: 8px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font-size: 14px; }
        .side-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
        .entries { list-style: none; margin: 0; padding: 0; }
        .entry { width: 100%; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 10px 8px; border: none; border-radius: 8px; background: none; color: var(--primary-text-color); font-size: 14px; text-align: left; cursor: pointer; }
        .entry:hover { background: var(--secondary-background-color); }
        .entry.selected { background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.15); }
        .entry.new .entry-name { font-style: italic; }
        .entry-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
        .entry ha-icon { --mdc-icon-size: 16px; color: var(--secondary-text-color); }
        .count { width: 100%; color: var(--secondary-text-color); font-size: 12px; }
        .list { list-style: none; margin: 0; padding: 0; }
        .item { display: flex; align-items: center; gap: 8px; padding: 6px 4px; border-bottom: 1px solid var(--divider-color); cursor: grab; }
        .item:last-child { border-bottom: none; }
        .item.hidden .title, .item.hidden > ha-icon:not(.grip) { opacity: 0.45; }
        .item.dragging { opacity: 0.4; }
        .grip { color: var(--secondary-text-color); --mdc-icon-size: 20px; }
        .title { flex: 1; min-width: 0; }
        .path { color: var(--secondary-text-color); font-size: 12px; font-family: monospace; }
        .chip { font-size: 11px; padding: 2px 6px; border-radius: 8px; background: var(--secondary-background-color); color: var(--secondary-text-color); white-space: nowrap; }
        .chip.accent { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        button.icon { background: none; border: none; color: var(--primary-text-color); cursor: pointer; padding: 2px; border-radius: 50%; }
        button.icon[disabled] { opacity: 0.25; cursor: default; }
        .check { display: flex; align-items: flex-start; gap: 8px; margin: 12px 0; }
        .actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
        button.primary, button.secondary { display: inline-flex; align-items: center; gap: 4px; padding: 10px 18px; border-radius: 18px; font-size: 14px; cursor: pointer; border: 1px solid var(--primary-color); }
        button.small { padding: 6px 10px; font-size: 13px; --mdc-icon-size: 16px; }
        button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        button.secondary { background: none; color: var(--primary-color); }
        button.danger { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }
        button[disabled] { opacity: 0.4; cursor: default; }
        .status { color: var(--secondary-text-color); font-size: 13px; }
        .error { color: var(--error-color, #db4437); }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--divider-color); vertical-align: middle; }
        th { font-weight: 500; color: var(--secondary-text-color); font-size: 13px; }
        td select { width: 100%; }
        .applied { color: var(--secondary-text-color); font-size: 12px; margin-top: 4px; }
        .applied.default { color: var(--primary-color); }
        input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--primary-color); flex-shrink: 0; }
        @media (max-width: 800px) {
          .layout { grid-template-columns: minmax(0, 1fr); }
          .field { flex-direction: column; align-items: stretch; }
          .field > span { max-width: none; }
          .path { display: none; }
        }
      </style>
      <div class="toolbar"><span id="menu"></span><span class="title">Sidebar Manager</span></div>
      <div class="tabs">${tab("profiles", "tab_profiles")}${tab("users", "tab_users")}</div>
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
