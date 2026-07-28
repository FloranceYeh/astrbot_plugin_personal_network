const bridge = window.AstrBotPluginPage;

const uiText = {
  nothingSelected: "未选择项目", statusActive: "进行中", statusUncertain: "不确定", statusEnded: "已结束",
  edit: "编辑", delete: "删除", strength: "关系强度", description: "关系描述", evidenceHistory: "证据记录",
  noDetails: "暂无详细资料", root: "人格", bio: "身份简介", personality: "性格", preferences: "偏好",
  facts: "重要事实", identities: "平台身份", nicknames: "常用昵称", relationships: "相关关系", notes: "管理员备注",
  uploadAvatar: "上传头像", noPeople: "当前人格还没有人物", missing: "人格已缺失", relationCount: "条关系",
  personCount: "个人物", saved: "已保存", deleted: "已删除", merged: "人物已合并", imported: "导入完成",
  exported: "导出已开始", confirmDeletePerson: "删除该人物及其全部关系？", confirmDeleteRelation: "删除该关系及其证据？",
  confirmMerge: "重复人物会被删除，关系和身份将迁移到保留人物。继续？", invalidMerge: "请选择两个不同的人物",
  previewImport: "导入预检", confirmImport: "确认合并导入？不会删除本地数据。", loadFailed: "加载失败",
  actionFailed: "操作失败",
};

const state = {
  personas: [],
  persona: null,
  network: { network: {}, characters: [], identities: [], relationships: [], evidence: [] },
  selected: null,
  cy: null,
  editingAliases: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const t = (key) => uiText[key] || key;
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const splitList = (value) => value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean);
const byId = (id) => state.network.characters.find((item) => item.id === id);
const aliasNames = (character) => (character.alias_usages || []).map((item) => item.alias);

function toast(message, error = false) {
  const item = document.createElement("div");
  item.className = `toast${error ? " error" : ""}`;
  item.textContent = message;
  $("#toast-region").append(item);
  window.setTimeout(() => item.remove(), 3500);
}

function avatarMarkup(character, size = "medium") {
  const initial = esc((character.name || "?").trim().slice(0, 1).toUpperCase());
  const image = character.avatar_data ? `<img src="${esc(character.avatar_data)}" alt="" />` : initial;
  return `<div class="avatar ${size}">${image}</div>`;
}

function relationshipLabel(item) {
  return `${byId(item.source_id)?.name || "?"} → ${byId(item.target_id)?.name || "?"}`;
}

async function loadPersonas(preserve = true) {
  const previous = preserve ? state.persona?.persona_id : null;
  const result = await bridge.apiGet("personas");
  state.personas = result.personas || [];
  state.persona = state.personas.find((item) => item.persona_id === previous)
    || state.personas.find((item) => !item.persona_missing)
    || state.personas[0]
    || null;
  const select = $("#persona-select");
  select.innerHTML = state.personas.map((item) => `<option value="${esc(item.persona_id)}">${esc(item.name)}${item.persona_missing ? ` · ${t("missing")}` : ""}</option>`).join("");
  if (state.persona) select.value = state.persona.persona_id;
}

async function loadNetwork() {
  if (!state.persona) return;
  state.network = await bridge.apiGet("network", { persona_id: state.persona.persona_id });
  state.selected = null;
  $("#network-enabled").checked = Boolean(state.network.network.enabled);
  renderSummary();
  renderGraph();
  renderPeople();
  renderInspector();
}

function renderSummary() {
  const people = state.network.characters.filter((item) => !item.is_persona).length;
  const relations = state.network.relationships.length;
  $("#network-summary").textContent = `${people} ${t("personCount")} · ${relations} ${t("relationCount")}`;
}

function graphElements() {
  const nodes = state.network.characters.map((item) => ({
    data: {
      id: item.id,
      label: item.name,
      avatar: item.avatar_data || "",
      root: item.is_persona ? "yes" : "no",
    },
    classes: [item.is_persona ? "persona-root" : "", item.avatar_data ? "has-avatar" : ""].filter(Boolean).join(" "),
  }));
  const edges = state.network.relationships.map((item) => ({
    data: { id: item.id, source: item.source_id, target: item.target_id, label: item.relation_type, strength: item.strength },
    classes: `status-${item.status}`,
  }));
  return [...nodes, ...edges];
}

function renderGraph() {
  const styles = getComputedStyle(document.documentElement);
  if (state.cy) state.cy.destroy();
  state.cy = window.cytoscape({
    container: $("#network-graph"),
    elements: graphElements(),
    minZoom: 0.25,
    maxZoom: 2.5,
    style: [
      { selector: "node", style: {
        width: 62, height: 62, label: "data(label)", "font-size": 11, color: styles.getPropertyValue("--text").trim(),
        "text-valign": "bottom", "text-margin-y": 9, "text-wrap": "ellipsis", "text-max-width": 92,
        "background-color": styles.getPropertyValue("--accent-soft").trim(), "border-width": 2,
        "border-color": styles.getPropertyValue("--accent").trim(),
      } },
      { selector: "node.has-avatar", style: { "background-image": "data(avatar)", "background-fit": "cover" } },
      { selector: "node.persona-root", style: { width: 76, height: 76, "border-width": 4, "background-color": styles.getPropertyValue("--amber").trim(), "border-color": styles.getPropertyValue("--amber").trim() } },
      { selector: "node:selected", style: { "border-width": 5, "border-color": styles.getPropertyValue("--coral").trim() } },
      { selector: "edge", style: {
        width: "mapData(strength, -100, 100, 1, 5)", "curve-style": "bezier", "target-arrow-shape": "triangle",
        "line-color": styles.getPropertyValue("--accent").trim(), "target-arrow-color": styles.getPropertyValue("--accent").trim(),
        label: "data(label)", "font-size": 9, color: styles.getPropertyValue("--muted").trim(), "text-background-color": styles.getPropertyValue("--surface").trim(),
        "text-background-opacity": 0.9, "text-background-padding": 3, "text-rotation": "autorotate",
      } },
      { selector: "edge.status-ended", style: { "line-style": "dashed", opacity: 0.45 } },
      { selector: "edge.status-uncertain", style: { "line-style": "dotted", "line-color": styles.getPropertyValue("--amber").trim(), "target-arrow-color": styles.getPropertyValue("--amber").trim() } },
      { selector: "edge:selected", style: { width: 5, "line-color": styles.getPropertyValue("--coral").trim(), "target-arrow-color": styles.getPropertyValue("--coral").trim() } },
      { selector: ".filtered", style: { opacity: 0.08, "text-opacity": 0 } },
    ],
    layout: { name: "cose", animate: false, padding: 54, nodeRepulsion: 8500, idealEdgeLength: 130, gravity: 0.35 },
  });
  state.cy.on("tap", "node, edge", (event) => {
    state.selected = { type: event.target.isNode() ? "character" : "relationship", id: event.target.id() };
    renderInspector();
  });
  state.cy.on("tap", (event) => {
    if (event.target === state.cy) { state.selected = null; renderInspector(); }
  });
  applyGraphFilters();
}

function applyGraphFilters() {
  if (!state.cy) return;
  const query = $("#graph-search").value.trim().toLowerCase();
  const status = $("#status-filter").value;
  state.cy.elements().removeClass("filtered");
  if (status) {
    state.network.relationships.filter((item) => item.status !== status).forEach((item) => state.cy.$id(item.id).addClass("filtered"));
  }
  if (query) {
    state.network.characters.forEach((item) => {
      const haystack = [item.name, ...aliasNames(item), item.bio].join(" ").toLowerCase();
      if (!haystack.includes(query)) state.cy.$id(item.id).addClass("filtered");
    });
    state.network.relationships.forEach((item) => {
      const haystack = `${item.relation_type} ${item.description} ${relationshipLabel(item)}`.toLowerCase();
      if (!haystack.includes(query)) state.cy.$id(item.id).addClass("filtered");
    });
  }
}

function renderInspector() {
  const panel = $("#inspector");
  if (!state.selected) {
    panel.className = "inspector empty";
    panel.innerHTML = `<div class="empty-state"><div class="empty-glyph">⌁</div><h2>${esc(t("nothingSelected"))}</h2></div>`;
    return;
  }
  panel.className = "inspector";
  if (state.selected.type === "relationship") {
    const relation = state.network.relationships.find((item) => item.id === state.selected.id);
    if (!relation) { state.selected = null; renderInspector(); return; }
    const evidence = state.network.evidence.filter((item) => item.relationship_id === relation.id);
    panel.innerHTML = `
      <div class="profile-heading"><span class="status-badge ${esc(relation.status)}">${esc(t(`status${relation.status[0].toUpperCase()}${relation.status.slice(1)}`))}</span><h2>${esc(relation.relation_type)}</h2><p class="alias-line">${esc(relationshipLabel(relation))}</p></div>
      <div class="inspector-actions"><button class="primary-button" id="inspect-edit-relation">${esc(t("edit"))}</button><button class="danger-button" id="inspect-delete-relation">${esc(t("delete"))}</button></div>
      <div class="detail-section"><h3>${esc(t("strength"))}</h3><p>${relation.strength}</p></div>
      <div class="detail-section"><h3>${esc(t("description"))}</h3><p>${esc(relation.description || t("noDetails"))}</p></div>
      <div class="detail-section"><h3>${esc(t("evidenceHistory"))}</h3>${evidence.length ? evidence.map((item) => `<div class="evidence-row">${esc(item.excerpt)}<div class="relation-meta">${esc(new Date(item.created_at).toLocaleString("zh-CN"))}</div></div>`).join("") : `<p>${esc(t("noDetails"))}</p>`}</div>`;
    $("#inspect-edit-relation").onclick = () => openRelationshipDialog(relation);
    $("#inspect-delete-relation").onclick = () => deleteRelationship(relation.id);
    return;
  }
  const character = byId(state.selected.id);
  if (!character) { state.selected = null; renderInspector(); return; }
  const relations = state.network.relationships.filter((item) => item.source_id === character.id || item.target_id === character.id);
  const identities = state.network.identities.filter((item) => item.character_id === character.id);
  panel.innerHTML = `
    <div class="profile-heading">${avatarMarkup(character, "large")}<h2>${esc(character.name)}</h2><p class="alias-line">${character.alias_usages?.length ? character.alias_usages.map((item) => `${esc(item.alias)} ×${item.use_count}`).join(" · ") : (character.is_persona ? esc(t("root")) : "")}</p></div>
    <div class="inspector-actions"><button class="primary-button" id="inspect-edit-person">${esc(t("edit"))}</button><button class="secondary-button" id="inspect-avatar">${esc(t("uploadAvatar"))}</button></div>
    <div class="detail-section"><h3>${esc(t("bio"))}</h3><p>${esc(character.bio || t("noDetails"))}</p></div>
    <div class="detail-section"><h3>${esc(t("personality"))}</h3><p>${esc(character.personality || t("noDetails"))}</p></div>
    <div class="detail-section"><h3>${esc(t("preferences"))}</h3><div class="tag-list">${character.preferences.map((item) => `<span class="tag">${esc(item)}</span>`).join("") || esc(t("noDetails"))}</div></div>
    <div class="detail-section"><h3>${esc(t("facts"))}</h3><div class="tag-list">${character.facts.map((item) => `<span class="tag">${esc(item)}</span>`).join("") || esc(t("noDetails"))}</div></div>
    ${identities.length ? `<div class="detail-section"><h3>${esc(t("identities"))}</h3>${identities.map((item) => `<div class="evidence-row"><strong>${esc(item.nicknames?.[0]?.nickname || item.user_id)}</strong><div class="relation-meta">${esc(item.platform)} · ${esc(item.user_id)}${item.session_id ? ` · ${esc(item.session_id)}` : ""}</div>${item.nicknames?.length ? `<div class="tag-list nickname-list">${item.nicknames.map((nickname) => `<span class="tag" title="${esc(t("nicknames"))}">${esc(nickname.nickname)} ×${nickname.use_count}</span>`).join("")}</div>` : ""}</div>`).join("")}</div>` : ""}
    <div class="detail-section"><h3>${esc(t("relationships"))}</h3>${relations.length ? relations.map((item) => `<div class="relation-row"><button data-relation-id="${esc(item.id)}"><strong>${esc(item.relation_type)}</strong><div class="relation-meta">${esc(relationshipLabel(item))} · ${item.strength}</div></button></div>`).join("") : `<p>${esc(t("noDetails"))}</p>`}</div>
    ${character.notes ? `<div class="detail-section"><h3>${esc(t("notes"))}</h3><p>${esc(character.notes)}</p></div>` : ""}
    ${character.is_persona ? "" : `<div class="detail-section"><button class="danger-button" id="inspect-delete-person">${esc(t("delete"))}</button></div>`}`;
  $("#inspect-edit-person").onclick = () => openCharacterDialog(character);
  $("#inspect-avatar").onclick = () => uploadAvatar(character.id);
  const deleteButton = $("#inspect-delete-person");
  if (deleteButton) deleteButton.onclick = () => deleteCharacter(character.id);
  panel.querySelectorAll("[data-relation-id]").forEach((button) => {
    button.onclick = () => { state.selected = { type: "relationship", id: button.dataset.relationId }; renderInspector(); };
  });
}

function renderPeople() {
  const query = $("#people-search").value.trim().toLowerCase();
  const people = state.network.characters.filter((item) => [item.name, ...aliasNames(item), item.bio].join(" ").toLowerCase().includes(query));
  $("#people-grid").innerHTML = people.length ? people.map((item) => {
    const count = state.network.relationships.filter((relation) => relation.source_id === item.id || relation.target_id === item.id).length;
    return `<article class="person-card" data-character-id="${esc(item.id)}"><div class="person-card-head">${avatarMarkup(item)}<div><h2>${esc(item.name)}</h2><div class="alias-line">${item.is_persona ? `<span class="root-badge">${esc(t("root"))}</span>` : esc(aliasNames(item).slice(0, 2).join(" · "))}</div></div></div><p class="bio">${esc(item.bio || item.personality || t("noDetails"))}</p><div class="person-card-footer"><span>${count} ${esc(t("relationCount"))}</span><button type="button">${esc(t("edit"))}</button></div></article>`;
  }).join("") : `<div class="empty-state"><div class="empty-glyph">○</div><h2>${esc(t("noPeople"))}</h2></div>`;
  $$(".person-card").forEach((card) => {
    card.onclick = () => openCharacterDialog(byId(card.dataset.characterId));
  });
}

function openCharacterDialog(character = null) {
  $("#character-form").reset();
  $("#character-id").value = character?.id || "";
  $("#character-name").value = character?.name || "";
  state.editingAliases = (character?.alias_usages || []).map((item) => ({ ...item }));
  renderAliasEditor();
  $("#character-bio").value = character?.bio || "";
  $("#character-personality").value = character?.personality || "";
  $("#character-preferences").value = character?.preferences?.join("\n") || "";
  $("#character-facts").value = character?.facts?.join("\n") || "";
  $("#character-notes").value = character?.notes || "";
  $("#character-dialog").showModal();
}

function renderAliasEditor() {
  const editor = $("#character-aliases");
  editor.innerHTML = state.editingAliases.length
    ? state.editingAliases.map((item, index) => `<div class="alias-row" data-alias-index="${index}"><input class="alias-name" value="${esc(item.alias)}" maxlength="100" aria-label="人物别名" /><div class="alias-count"><input class="alias-use-count" type="number" min="1" max="999999" value="${Math.max(1, Number(item.use_count) || 1)}" aria-label="使用次数" /></div><button class="icon-button alias-delete" type="button" title="删除别名" aria-label="删除别名">×</button></div>`).join("")
    : '<div class="alias-empty">暂无别名</div>';
  $$(".alias-row").forEach((row) => {
    const index = Number(row.dataset.aliasIndex);
    row.querySelector(".alias-name").oninput = (event) => { state.editingAliases[index].alias = event.target.value; };
    row.querySelector(".alias-use-count").oninput = (event) => { state.editingAliases[index].use_count = Math.max(1, Number(event.target.value) || 1); };
    row.querySelector(".alias-delete").onclick = () => { state.editingAliases.splice(index, 1); renderAliasEditor(); };
  });
}

function fillCharacterSelects() {
  const options = state.network.characters.map((item) => `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join("");
  ["#relationship-source", "#relationship-target", "#merge-target", "#merge-duplicate"].forEach((selector) => { $(selector).innerHTML = options; });
}

function openRelationshipDialog(relation = null) {
  fillCharacterSelects();
  $("#relationship-form").reset();
  $("#relationship-id").value = relation?.id || "";
  $("#relationship-source").value = relation?.source_id || state.network.characters.find((item) => item.is_persona)?.id || "";
  $("#relationship-target").value = relation?.target_id || state.network.characters.find((item) => !item.is_persona)?.id || "";
  $("#relationship-type").value = relation?.relation_type || "";
  $("#relationship-status").value = relation?.status || "active";
  $("#relationship-strength").value = relation?.strength ?? 0;
  $("#strength-output").value = relation?.strength ?? 0;
  $("#relationship-description").value = relation?.description || "";
  $("#relationship-evidence").value = "";
  $("#delete-relationship-button").classList.toggle("hidden", !relation);
  $("#relationship-dialog").showModal();
}

async function deleteCharacter(id) {
  if (!window.confirm(t("confirmDeletePerson"))) return;
  try {
    await bridge.apiPost("character/delete", { persona_id: state.persona.persona_id, character_id: id });
    toast(t("deleted")); await loadNetwork();
  } catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
}

async function deleteRelationship(id) {
  if (!window.confirm(t("confirmDeleteRelation"))) return;
  try {
    await bridge.apiPost("relationship/delete", { persona_id: state.persona.persona_id, relationship_id: id });
    $("#relationship-dialog").close(); toast(t("deleted")); await loadNetwork();
  } catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
}

function uploadAvatar(characterId) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/jpeg,image/png,image/webp";
  input.onchange = async () => {
    if (!input.files[0]) return;
    try {
      await bridge.upload(`avatar/${characterId}`, input.files[0]);
      toast(t("saved")); await loadNetwork();
    } catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
  };
  input.click();
}

function bindEvents() {
  $$(".tab").forEach((tab) => {
    tab.onclick = () => {
      $$(".tab").forEach((item) => item.classList.toggle("active", item === tab));
      $$(".view").forEach((view) => view.classList.toggle("active", view.id === `${tab.dataset.view}-view`));
      if (tab.dataset.view === "graph") window.setTimeout(() => state.cy?.resize(), 0);
    };
  });
  $$(".close-dialog").forEach((button) => { button.onclick = () => button.closest("dialog").close(); });
  $("#persona-select").onchange = async (event) => { state.persona = state.personas.find((item) => item.persona_id === event.target.value); await loadNetwork(); };
  $("#network-enabled").onchange = async (event) => {
    try { await bridge.apiPost("network/enabled", { persona_id: state.persona.persona_id, enabled: event.target.checked }); toast(t("saved")); }
    catch (error) { event.target.checked = !event.target.checked; toast(`${t("actionFailed")}: ${error.message}`, true); }
  };
  $("#refresh-button").onclick = async () => { try { await loadPersonas(); await loadNetwork(); } catch (error) { toast(`${t("loadFailed")}: ${error.message}`, true); } };
  $("#fit-button").onclick = () => state.cy?.fit(undefined, 48);
  $("#graph-search").oninput = applyGraphFilters;
  $("#status-filter").onchange = applyGraphFilters;
  $("#people-search").oninput = renderPeople;
  $("#add-person-button").onclick = () => openCharacterDialog();
  $("#add-alias-button").onclick = () => { state.editingAliases.push({ alias: "", use_count: 1, last_used_at: "" }); renderAliasEditor(); $("#character-aliases .alias-row:last-child .alias-name")?.focus(); };
  $("#add-relation-button").onclick = () => openRelationshipDialog();
  $("#merge-button").onclick = () => { fillCharacterSelects(); $("#merge-dialog").showModal(); };
  $("#relationship-strength").oninput = (event) => { $("#strength-output").value = event.target.value; };
  $("#delete-relationship-button").onclick = () => deleteRelationship($("#relationship-id").value);

  $("#character-form").onsubmit = async (event) => {
    event.preventDefault();
    const payload = {
      persona_id: state.persona.persona_id, id: $("#character-id").value || undefined,
      name: $("#character-name").value.trim(),
      alias_usages: state.editingAliases
        .map((item) => ({ alias: item.alias.trim(), use_count: Math.max(1, Number(item.use_count) || 1), last_used_at: item.last_used_at || "" }))
        .filter((item) => item.alias)
        .sort((left, right) => right.use_count - left.use_count || left.alias.localeCompare(right.alias, "zh-CN")),
      bio: $("#character-bio").value.trim(), personality: $("#character-personality").value.trim(),
      preferences: splitList($("#character-preferences").value), facts: splitList($("#character-facts").value),
      notes: $("#character-notes").value.trim(),
    };
    try { await bridge.apiPost("character/save", payload); $("#character-dialog").close(); toast(t("saved")); await loadNetwork(); }
    catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
  };

  $("#relationship-form").onsubmit = async (event) => {
    event.preventDefault();
    const source = $("#relationship-source").value;
    const target = $("#relationship-target").value;
    if (source === target) { toast(t("invalidMerge"), true); return; }
    const payload = {
      persona_id: state.persona.persona_id, id: $("#relationship-id").value || undefined,
      source, target, type: $("#relationship-type").value.trim(), strength: Number($("#relationship-strength").value),
      status: $("#relationship-status").value, description: $("#relationship-description").value.trim(),
      evidence: $("#relationship-evidence").value.trim(),
    };
    try { await bridge.apiPost("relationship/save", payload); $("#relationship-dialog").close(); toast(t("saved")); await loadNetwork(); }
    catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
  };

  $("#merge-form").onsubmit = async (event) => {
    event.preventDefault();
    const targetId = $("#merge-target").value;
    const duplicateId = $("#merge-duplicate").value;
    if (targetId === duplicateId) { toast(t("invalidMerge"), true); return; }
    if (!window.confirm(t("confirmMerge"))) return;
    try {
      await bridge.apiPost("character/merge", { persona_id: state.persona.persona_id, target_id: targetId, duplicate_id: duplicateId });
      $("#merge-dialog").close(); toast(t("merged")); await loadNetwork();
    } catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
  };

  $("#export-button").onclick = async () => {
    try { await bridge.download("export", { persona_id: state.persona.persona_id }); toast(t("exported")); }
    catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
  };
  $("#import-button").onclick = () => $("#import-file").click();
  $("#import-file").onchange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      const preview = await bridge.upload(`import/${state.persona.key}/preview`, file);
      if (!preview.can_apply) {
        toast(`${t("previewImport")}: ${preview.conflicts.join("; ")}`, true);
        return;
      }
      const details = `${t("previewImport")}\n${preview.new_characters} + ${preview.updated_characters} ↻ ${t("personCount")}\n${preview.new_relationships} + ${preview.updated_relationships} ↻ ${t("relationCount")}\n\n${t("confirmImport")}`;
      if (window.confirm(details)) {
        await bridge.apiPost("import/apply", { token: preview.token });
        toast(t("imported")); await loadNetwork();
      }
    } catch (error) { toast(`${t("actionFailed")}: ${error.message}`, true); }
    finally { event.target.value = ""; }
  };
}

async function start() {
  await bridge.ready();
  bindEvents();
  bridge.onContext(() => {
    renderSummary(); renderPeople(); renderInspector(); renderGraph();
  });
  try { await loadPersonas(false); await loadNetwork(); }
  catch (error) { console.error(error); toast(`${t("loadFailed")}: ${error.message}`, true); }
}

start();
