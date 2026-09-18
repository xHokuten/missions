(() => {
  const body = document.querySelector("#spell-results");
  if (!body) return;

  const learnedCollapse = document.querySelector("#learned-spells-collapse");
  const learnedContent = document.querySelector("#learned-spells-content");
  if (learnedCollapse && learnedContent) {
    learnedCollapse.addEventListener("click", () => {
      const isOpen = learnedCollapse.getAttribute("aria-expanded") === "true";
      learnedCollapse.setAttribute("aria-expanded", String(!isOpen));
      learnedCollapse.setAttribute("aria-label", `${isOpen ? "Expand" : "Collapse"} My Learned Spells`);
      learnedCollapse.innerHTML = isOpen ? "&#9656;" : "&#9662;";
      learnedContent.hidden = isOpen;
    });
  }

  const filtersCollapse = document.querySelector("#spell-filters-collapse");
  const filtersContent = document.querySelector("#spell-filters-content");
  if (filtersCollapse && filtersContent) {
    filtersCollapse.addEventListener("click", () => {
      const isOpen = filtersCollapse.getAttribute("aria-expanded") === "true";
      filtersCollapse.setAttribute("aria-expanded", String(!isOpen));
      filtersCollapse.setAttribute("aria-label", `${isOpen ? "Expand" : "Collapse"} Search and Filters`);
      filtersCollapse.innerHTML = isOpen ? "&#9656;" : "&#9662;";
      filtersContent.hidden = isOpen;
    });
  }

  const form = document.querySelector("#spell-ownership-form");
  const learned = new Set(window.LEARNED_BLUE_SPELLS || []);
  const learnedList = document.querySelector("#learned-spells-list");
  const learnedEmpty = document.querySelector("#learned-spells-empty");
  const saveStatus = document.querySelector("#spell-save-status");
  const controls = {
    search: document.querySelector("#spell-search"),
    zone: document.querySelector("#spell-zone"),
    type: document.querySelector("#spell-type"),
    level: document.querySelector("#spell-max-level"),
    skill: document.querySelector("#spell-current-skill"),
    hide: document.querySelector("#spell-hide-learned"),
  };
  controls.hide.checked = true;
  let rows = [];
  let sortKey = "spell_level";
  let sortDirection = 1;
  let saveTimer;
  let saveVersion = 0;
  let hasUnsavedChanges = false;

  const number = value => value === null || value === "" ? null : Number(value);
  const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const mobLevel = row => row.monster_min === null
    ? "-"
    : row.monster_min === row.monster_max
      ? String(row.monster_min)
      : `${row.monster_min}-${row.monster_max ?? "?"}`;

  const syncHiddenValues = () => {
    const container = document.querySelector("#learned-spell-values");
    container.replaceChildren(...[...learned].sort().map(spell => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "spells";
      input.value = spell;
      return input;
    }));
  };

  const setSaveStatus = (message, state = "") => {
    saveStatus.textContent = message;
    saveStatus.className = state;
  };

  const saveLearned = async version => {
    setSaveStatus("Saving...", "saving");
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
      });
      const destination = new URL(response.url, window.location.href).pathname;
      if (!response.ok || destination !== "/spell-farming") throw new Error("Save failed");
      if (version === saveVersion) {
        hasUnsavedChanges = false;
        setSaveStatus("Saved", "");
      }
      return true;
    } catch (_error) {
      if (version === saveVersion) setSaveStatus("Could not save - use Save Learned Spells", "error");
      return false;
    }
  };

  const scheduleSave = () => {
    window.clearTimeout(saveTimer);
    const version = ++saveVersion;
    hasUnsavedChanges = true;
    setSaveStatus("Unsaved changes", "saving");
    saveTimer = window.setTimeout(() => saveLearned(version), 450);
  };

  document.querySelectorAll(".blue-tool-switcher a").forEach(link => link.addEventListener("click", async event => {
    if (!hasUnsavedChanges) return;
    event.preventDefault();
    window.clearTimeout(saveTimer);
    const destination = link.href;
    const saved = await saveLearned(++saveVersion);
    if (saved) window.location.assign(destination);
  }));

  const renderLearnedList = () => {
    const spells = [...learned].sort((a, b) => a.localeCompare(b));
    learnedList.replaceChildren(...spells.map(spell => {
      const chip = document.createElement("span");
      chip.className = "learned-spell-chip";
      const label = document.createElement("span");
      label.textContent = spell;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "x";
      remove.setAttribute("aria-label", `Remove ${spell} from learned spells`);
      remove.addEventListener("click", () => setLearned(spell, false));
      chip.append(label, remove);
      return chip;
    }));
    learnedEmpty.hidden = spells.length > 0;
  };

  const updateProgress = () => {
    const allSpells = new Set(rows.map(row => row.spell));
    const count = [...learned].filter(spell => allSpells.has(spell)).length;
    const total = allSpells.size;
    document.querySelector("#learned-count").textContent = `${count}/${total} learned`;
    document.querySelector("#spell-save-count").textContent = `${count} spell${count === 1 ? "" : "s"} learned`;
    renderLearnedList();
  };

  const setLearned = (spell, value) => {
    if (value) learned.add(spell);
    else learned.delete(spell);
    syncHiddenValues();
    document.querySelectorAll(".spell-learned-check").forEach(box => {
      if (box.value === spell) {
        box.checked = value;
        box.closest("tr").classList.toggle("learned", value);
      }
    });
    updateProgress();
    scheduleSave();
    if (controls.hide.checked) render();
  };

  const render = () => {
    const query = controls.search.value.trim().toLowerCase();
    const zone = controls.zone.value;
    const maxLevel = Math.min(75, Math.max(1, number(controls.level.value) || 75));
    const skill = number(controls.skill.value);
    const matches = rows.filter(row =>
      (!query || `${row.spell} ${row.monster} ${row.trait || ""} ${row.spell_type || ""} ${row.element || ""} ${row.physical_damage_type || ""} ${(row.set_stats || []).join(" ")} ${(row.stat_modifiers || []).join(" ")}`.toLowerCase().includes(query)) &&
      (!zone || row.zone === zone) && row.spell_level <= maxLevel &&
      (!controls.type.value || row.spell_type === controls.type.value) &&
      (!controls.hide.checked || !learned.has(row.spell))
    ).sort((a, b) => {
      const av = a[sortKey] ?? 9999;
      const bv = b[sortKey] ?? 9999;
      return (typeof av === "string" ? av.localeCompare(bv) : av - bv) * sortDirection;
    });
    const spells = new Set(matches.map(row => row.spell));
    document.querySelector("#spell-count").textContent = spells.size;
    document.querySelector("#target-count").textContent = `${matches.length} targets across ${spells.size} spells`;
    body.replaceChildren(...matches.map(row => {
      const tr = document.createElement("tr");
      const ready = skill === null ? null : skill >= row.minimum_skill;
      const isLearned = learned.has(row.spell);
      tr.classList.toggle("learned", isLearned);
      const setStats = (row.set_stats || []).join(" / ") || "&mdash;";
      const trait = row.trait
        ? `${row.trait}<small>Trait weight ${row.trait_weight}</small>`
        : "&mdash;";
      const damageType = row.physical_damage_type ? `<small class="damage-type ${row.physical_damage_type.toLowerCase()}">${escapeHtml(row.physical_damage_type)}</small>` : "";
      const typeLabel = row.spell_type === "Magical" && row.element
        ? `Magical (${row.element})`
        : row.spell_type;
      const scaling = (row.stat_modifiers || []).map(value => `<span>${escapeHtml(value)}</span>`).join("") || "&mdash;";
      tr.innerHTML = `<td><input class="spell-learned-check" type="checkbox" value="${escapeHtml(row.spell)}" ${isLearned ? "checked" : ""} aria-label="Mark ${escapeHtml(row.spell)} learned"></td><td>${row.spell_level}</td><td><span class="spell-name" title="${escapeHtml(`${row.description || "No description available."}\nType: ${typeLabel}${row.physical_damage_type ? ` (${row.physical_damage_type})` : ""}\nSet cost: ${row.set_points ?? "-"}`)}">${escapeHtml(row.spell)}</span></td><td><span class="spell-type ${row.spell_type.toLowerCase().replace(/[^a-z]+/g, "-")}">${escapeHtml(typeLabel)}</span>${damageType}</td><td><span class="spell-scaling">${scaling}</span></td><td><span class="spell-set-cost">${row.set_points ?? "-"}</span></td><td><span class="spell-set-stats">${setStats}</span></td><td><span class="spell-trait">${trait}</span></td><td><span class="skill-value">${row.minimum_skill}<small>/ ${row.skill_cap} cap</small></span></td><td>${escapeHtml(row.monster)}</td><td><button type="button" class="spell-zone-map" data-zone="${escapeHtml(row.zone)}" data-monsters="${escapeHtml(row.monster)}">${escapeHtml(row.zone)}</button></td><td><span class="mob-level">${mobLevel(row)}</span></td><td><span class="readiness ${ready === null ? "" : ready ? "ready" : "locked"}">${ready === null ? "Enter skill" : ready ? "Learnable" : "Skill low"}</span></td>`;
      tr.querySelector("input").addEventListener("change", event => setLearned(row.spell, event.target.checked));
      tr.querySelector(".spell-zone-map").addEventListener("click", event => window.openSpellTargetMap(event.currentTarget.dataset.zone, event.currentTarget.dataset.monsters));
      return tr;
    }));
    if (!matches.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="13" class="spell-empty">No farming targets match these filters.</td>';
      body.append(tr);
    }
    updateProgress();
  };

  syncHiddenValues();
  renderLearnedList();
  fetch("/static/blue_spell_farming.json?v=2")
    .then(response => {
      if (!response.ok) throw new Error("Spell data unavailable");
      return response.json();
    })
    .then(payload => {
      rows = payload.rows;
      [...new Set(rows.map(row => row.zone))].sort().forEach(zone => controls.zone.add(new Option(zone, zone)));
      render();
    })
    .catch(error => {
      body.innerHTML = `<tr><td colspan="13" class="spell-empty">${error.message}</td></tr>`;
    });

  Object.values(controls).forEach(control => control.addEventListener(
    control.tagName === "SELECT" || control.type === "checkbox" ? "change" : "input",
    render,
  ));
  document.querySelector("#spell-clear").addEventListener("click", () => {
    controls.search.value = "";
    controls.zone.value = "";
    controls.type.value = "";
    controls.level.value = "75";
    controls.skill.value = "";
    controls.hide.checked = false;
    render();
  });
  document.querySelectorAll(".spell-table th[data-sort]").forEach(th => th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (sortKey === key) sortDirection *= -1;
    else {
      sortKey = key;
      sortDirection = 1;
    }
    render();
  }));
})();
