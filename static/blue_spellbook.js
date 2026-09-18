(() => {
  const levelInput = document.querySelector("#book-level");
  if (!levelInput) return;

  const learned = new Set(window.LEARNED_BLUE_SPELLS || []);
  const equipped = new Set((window.BLUE_TEMPLATE && window.BLUE_TEMPLATE.spells) || []);
  let spells = [];
  let chainActions = new Map();
  let weaponActions = [];
  let skillchainElementFilter;
  const plannedSpellNames = new Set();
  const burstElements = {Liquefaction:["Fire"],Induration:["Ice"],Detonation:["Wind"],Scission:["Earth"],Reverberation:["Water"],Impaction:["Lightning"],Transfixion:["Light"],Compression:["Dark"],Fusion:["Fire","Light"],Fragmentation:["Wind","Lightning"],Distortion:["Ice","Water"],Gravitation:["Earth","Dark"],Light:["Fire","Wind","Lightning","Light"],Darkness:["Earth","Water","Ice","Dark"]};
  const transitions = { Compression:{Transfixion:"Transfixion",Detonation:"Detonation"}, Liquefaction:{Impaction:"Fusion",Scission:"Scission"}, Induration:{Reverberation:"Fragmentation",Compression:"Compression",Impaction:"Impaction"}, Reverberation:{Induration:"Induration",Impaction:"Impaction"}, Transfixion:{Scission:"Distortion",Reverberation:"Reverberation",Compression:"Compression"}, Scission:{Liquefaction:"Liquefaction",Reverberation:"Reverberation",Detonation:"Detonation"}, Detonation:{Compression:"Gravitation",Scission:"Scission"}, Impaction:{Liquefaction:"Liquefaction",Detonation:"Detonation"}, Gravitation:{Distortion:"Darkness",Fragmentation:"Fragmentation"}, Fragmentation:{Fusion:"Light",Distortion:"Distortion"}, Distortion:{Gravitation:"Darkness",Fusion:"Fusion"}, Fusion:{Fragmentation:"Light",Gravitation:"Gravitation"} };
  const el = id => document.querySelector(`#${id}`);
  const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
  const assimilationBonus = () => Math.min(5, Math.max(0, Math.floor((learned.size - 41) / 10)));
  const pointLimit = value => 10 + Math.floor((value - 1) / 10) * 5 + assimilationBonus();
  const slotLimit = value => Math.min(20, 6 + Math.floor((value - 1) / 10) * 2);
  const level = () => Math.min(75, Math.max(1, Number(levelInput.value) || 75));
  const contribution = spell => !spell.trait ? 0 : spell.trait === "Auto Refresh"
    ? Number(spell.trait_weight || 0) : Number(spell.trait_weight || 0) * 4;
  const selectedValues = container => [...container.querySelectorAll("input:checked")].map(input => input.value);
  const current = () => spells.filter(spell => equipped.has(spell.spell));
  const cost = list => list.reduce((sum, spell) => sum + Number(spell.set_points || 0), 0);
  const chainAction = spell => chainActions.get(spell.spell);
  const chainProperties = spell => (chainAction(spell) || {}).properties || [];
  const physicalDamageType = spell => (chainAction(spell) || {}).physical_damage_type || spell.physical_damage_type || null;
  const canUseWeaponSkill = action => action.jobs.includes("BLU") && (!action.level_requirement || action.level_requirement <= level()) && (action.level_requirement || catalogSkillAtLevel(action));
  const catalogSkillAtLevel = action => {
    const rank = action.skill_ranks?.BLU;
    return Boolean(rank && skillchainCaps[String(level())]?.[String(rank)] >= action.skill_level);
  };
  let skillchainCaps = {};
  const finalSkillchainsFor = spell => {
    const properties = chainProperties(spell);
    if (!properties.length) return [];
    const finals = new Set();
    weaponActions.filter(canUseWeaponSkill).forEach(opener => opener.properties.forEach(first => properties.forEach(last => {
      const final = transitions[first]?.[last];
      if (final) finals.add(final);
    })));
    return [...finals].sort();
  };
  const selfChainsFor = spell => {
    const chains = [];
    weaponActions.filter(action => action.weapon === "Sword" && canUseWeaponSkill(action)).forEach(opener => opener.properties.forEach(first => chainProperties(spell).forEach(last => {
      const final = transitions[first]?.[last];
      if (final) chains.push({ opener: opener.name, openerProperties: opener.properties, final });
    })));
    return chains;
  };
  const chainLabel = spell => {
    const properties = chainProperties(spell);
    return properties.length ? properties.join(" / ") : "No Chain Affinity property";
  };
  const parseStats = spell => (spell.set_stats || []).flatMap(text => {
    const match = String(text).replace(/,$/, "").match(/^(.+?)([+-]\d+)$/);
    return match ? [{ name: match[1].trim(), value: Number(match[2]) }] : [];
  });
  const totals = list => {
    const result = {};
    list.forEach(spell => parseStats(spell).forEach(stat => {
      result[stat.name] = (result[stat.name] || 0) + stat.value;
    }));
    return result;
  };
  const canAdd = spell => {
    const active = current();
    return spell.spell_level <= level() && active.length < slotLimit(level())
      && cost(active) + Number(spell.set_points || 0) <= pointLimit(level());
  };
  const badge = spell => `<span class="ownership ${learned.has(spell.spell) ? "known" : "missing"}">${learned.has(spell.spell) ? "Learned" : "Need to learn"}</span>`;
  const effectTooltip = spell => spell.description
    ? `<span class="spell-effect-tip" tabindex="0"><span class="spell-effect-name">${escapeHtml(spell.spell)}</span><span class="spell-effect-popover" role="tooltip">${escapeHtml(spell.description)}</span></span>`
    : `<span class="spell-effect-name">${escapeHtml(spell.spell)}</span>`;
  const syncForm = () => {
    el("template-level").value = level();
    el("template-spells").replaceChildren(...[...equipped].map(name => {
      const input = document.createElement("input");
      input.type = "hidden"; input.name = "spells"; input.value = name;
      return input;
    }));
  };

  const rightRail = document.createElement("aside");
  rightRail.className = "spellbook-right-rail";
  document.querySelector(".spellbook-three-column").append(rightRail);
  rightRail.append(document.querySelector(".build-settings"), document.querySelector(".template-library"));
  const effectsSection = document.createElement("section");
  effectsSection.className = "active-effects-summary";
  effectsSection.innerHTML = '<h3>Additional Effect / Spell Equivalent</h3><p class="effect-summary-help">Effects granted by the equipped spells are listed with their familiar WHM, RDM, or BLM equivalent where applicable.</p><div id="active-effects"></div>';
  const selfChainPlanner = document.createElement("section");
  selfChainPlanner.className = "self-chain-planner";
  selfChainPlanner.innerHTML = '<h3>Self Skillchain &amp; Burst Planner</h3><p class="effect-summary-help">Choose a Skillchain Element and a physical damage weakness to see every level-valid Sword weapon skill → Chain Affinity Blue Magic combination. Select the Blue Magic you want, then add it while preserving room for any selected trait goals.</p><div class="self-chain-controls"></div><div id="self-chain-options" class="self-chain-options"></div><div class="self-chain-actions"><button class="button primary" id="add-selected-self-chains" type="button">Add Selected Blue Magic</button><span id="self-chain-status">Choose a Skillchain Element to plan a self skillchain.</span></div>';
  document.querySelector(".build-summary").append(effectsSection, selfChainPlanner);

  const showSpell = spell => {
    el("spell-detail-title").textContent = spell.spell;
    const type = spell.spell_type === "Magical" && spell.element ? `Magical (${spell.element})` : (spell.spell_type || "Support");
    el("spell-detail-content").innerHTML = `<div class="spell-detail-grid"><div><span>Blue Mage level</span><strong>${spell.spell_level}</strong></div><div><span>Set cost</span><strong>${spell.set_points} points</strong></div><div><span>Type</span><strong>${type}</strong></div><div><span>Status</span><strong>${learned.has(spell.spell) ? "Learned" : "Need to learn"}</strong></div><div><span>Chain Affinity</span><strong>${escapeHtml(chainLabel(spell))}</strong></div><div><span>Trait contribution</span><strong>${spell.trait ? `${spell.trait} +${contribution(spell)}` : "None"}</strong></div><div><span>Set stats</span><strong>${(spell.set_stats || []).join(" · ") || "None"}</strong></div></div>`;
    el("spell-detail-modal").hidden = false;
  };

  const renderQuickPicker = () => {
    const query = el("quick-spell-search").value.trim().toLowerCase();
    const matches = spells.filter(spell => spell.spell_level <= level() && !equipped.has(spell.spell)
      && (!query || `${spell.spell} ${spell.trait || ""} ${(spell.set_stats || []).join(" ")}`.toLowerCase().includes(query)));
    el("quick-spell-results").innerHTML = matches.map(spell => `<article><div><strong>${effectTooltip(spell)}</strong>${badge(spell)}<small>Lv. ${spell.spell_level} · ${spell.set_points} points · ${spell.trait || "No trait"}</small></div><button class="button" type="button" data-quick-add="${spell.spell}" ${canAdd(spell) ? "" : "disabled"}>Add</button></article>`).join("") || '<p class="book-empty">No available spells match.</p>';
  };
  const openPicker = () => {
    el("quick-spell-search").value = "";
    renderQuickPicker();
    el("spell-picker-modal").hidden = false;
    el("quick-spell-search").focus();
  };

  const renderPlannerOptions = () => {
    const selectedElements = skillchainElementFilter && skillchainElementFilter.value ? [skillchainElementFilter.value] : [];
    const damage = el("book-damage-filter").value;
    if (!selectedElements.length) {
      el("self-chain-options").innerHTML = '<p class="book-empty">Choose a Skillchain Element to show compatible self skillchains.</p>';
      el("self-chain-status").textContent = "Choose a Skillchain Element to plan a self skillchain.";
      return;
    }
    const options = spells.flatMap(spell => selfChainsFor(spell)
      .filter(chain => selectedElements.some(element => (burstElements[chain.final] || []).includes(element))
        && (!damage || physicalDamageType(spell) === damage))
      .map(chain => ({ spell, ...chain })));
    const unique = [...new Map(options.map(option => [`${option.opener}|${option.spell.spell}|${option.final}`, option])).values()]
      .sort((a, b) => a.final.localeCompare(b.final) || a.opener.localeCompare(b.opener) || a.spell.spell.localeCompare(b.spell.spell));
    el("self-chain-options").innerHTML = unique.length ? unique.map(({ spell, opener, final }) => `<label class="self-chain-option"><input type="checkbox" data-self-chain-spell="${escapeHtml(spell.spell)}" ${plannedSpellNames.has(spell.spell) ? "checked" : ""}><span><b>${escapeHtml(opener)} → ${escapeHtml(spell.spell)}</b><small>${escapeHtml(final)} · ${(burstElements[final] || []).map(escapeHtml).join("/")} · ${escapeHtml(physicalDamageType(spell) || "Physical")} · ${spell.set_points} points</small></span></label>`).join("") : '<p class="book-empty">No level-valid Sword self skillchains match these choices.</p>';
    el("self-chain-status").textContent = `${unique.length} Sword self-skillchain option${unique.length === 1 ? "" : "s"} shown for ${selectedElements.join("/")}.`;
  };

  const render = () => {
    const lvl = level();
    [...equipped].forEach(name => {
      const spell = spells.find(row => row.spell === name);
      if (!spell || spell.spell_level > lvl) equipped.delete(name);
    });
    const active = current();
    const used = cost(active);
    el("spell-count").textContent = active.length;
    el("book-points").textContent = `${used} / ${pointLimit(lvl)}`;
    const bonus = assimilationBonus();
    el("book-points").nextElementSibling.textContent = `Set points · ${learned.size} learned${bonus ? ` · +${bonus} bonus` : ""}`;
    el("book-slots").textContent = `${active.length} / ${slotLimit(lvl)}`;
    el("book-points").classList.toggle("over", used > pointLimit(lvl));
    el("active-spells").innerHTML = `${active.map(spell => `<article class="equipped-spell" data-view-spell="${spell.spell}" tabindex="0"><button type="button" data-remove="${spell.spell}" aria-label="Remove ${spell.spell}">×</button><div><strong>${effectTooltip(spell)}</strong>${badge(spell)}</div><span>Lv. ${spell.spell_level} · ${spell.set_points} pts</span><small>${spell.trait ? `${spell.trait} +${contribution(spell)}` : "No trait"} · ${(spell.set_stats || []).join(", ") || "No set stats"}</small></article>`).join("")}<button class="add-spell-tile" id="add-spell-tile" type="button"><b>+</b><span>Add Spell</span><small>${active.length}/${slotLimit(lvl)} slots used</small></button>`;

    const traitPoints = {};
    active.forEach(spell => { if (spell.trait) traitPoints[spell.trait] = (traitPoints[spell.trait] || 0) + contribution(spell); });
    const traitEntries = Object.entries(traitPoints).sort();
    el("active-traits").innerHTML = traitEntries.length ? traitEntries.map(([name, points]) => `<span class="summary-chip ${points >= 8 ? "active" : "partial"}"><b>${name}${points >= 8 ? ` Tier ${Math.floor(points / 8)}` : ""}</b><small>${points}/8 trait points${points < 8 ? " · inactive" : ""}</small></span>`).join("") : '<p class="book-empty">No trait contributions yet.</p>';
    const statEntries = Object.entries(totals(active)).filter(([, value]) => value).sort();
    el("active-stats").innerHTML = statEntries.length ? statEntries.map(([name, value]) => `<span class="summary-chip active"><b>${name} ${value > 0 ? "+" : ""}${value}</b></span>`).join("") : '<p class="book-empty">No set stat bonuses yet.</p>';

    const activeEffects = {};
    active.forEach(spell => (spell.effects || []).forEach(effect => { (activeEffects[effect] ||= []).push(spell.spell); }));
    const equivalents = { "HP Drain": "Drain", "MP Drain": "Aspir", "Defense Down": "Dia", "Attack Down": "Bio", "Cure": "Cure" };
    const effectEntries = Object.entries(activeEffects).sort(([a], [b]) => a.localeCompare(b));
    el("active-effects").innerHTML = effectEntries.length ? effectEntries.map(([effect, names]) => `<span class="summary-chip effect"><b>${escapeHtml(effect)}${equivalents[effect] ? ` (${equivalents[effect]})` : ""}</b><small>${names.map(escapeHtml).join(" · ")}</small></span>`).join("") : '<p class="book-empty">No additional effects are provided by the currently equipped spells.</p>';

    const query = el("book-search").value.trim().toLowerCase();
    const damage = el("book-damage-filter").value;
    const selectedElements = skillchainElementFilter && skillchainElementFilter.value ? [skillchainElementFilter.value] : [];
    const visible = spells.filter(spell => spell.spell_level <= lvl
      && (!el("book-learned-only").checked || learned.has(spell.spell))
      && (!selectedElements.length || selfChainsFor(spell).some(chain => selectedElements.some(element => (burstElements[chain.final] || []).includes(element))))
      && (!damage || physicalDamageType(spell) === damage)
      && (!query || `${spell.spell} ${spell.trait || ""} ${(spell.effects || []).join(" ")} ${(spell.set_stats || []).join(" ")} ${chainLabel(spell)}`.toLowerCase().includes(query)));
    el("catalog-count").textContent = `${visible.length} spells`;
    el("book-catalog").innerHTML = visible.map(spell => { const damage = physicalDamageType(spell); const combat = damage ? `Physical: ${damage}` : spell.element ? `Magic: ${spell.element}` : "Damage: —"; return `<article class="${equipped.has(spell.spell) ? "selected" : ""}"><div><strong>${effectTooltip(spell)}</strong>${badge(spell)}<small>Lv. ${spell.spell_level} · ${spell.set_points} points</small></div><div><span>${spell.trait ? `${spell.trait} +${contribution(spell)}` : "No trait"}</span><small>Chain Affinity: ${escapeHtml(chainLabel(spell))}</small><small>${escapeHtml(combat)}</small></div><button class="button" type="button" data-toggle="${spell.spell}" ${!equipped.has(spell.spell) && !canAdd(spell) ? "disabled" : ""}>${equipped.has(spell.spell) ? "Remove" : "Add"}</button></article>`; }).join("") || '<p class="book-empty">No spells match the selected filters.</p>';
    renderPlannerOptions();
    syncForm();
  };

  const cheapestTraitSet = (trait, pool, maxPoints, maxSlots) => {
    const candidates = pool.filter(spell => spell.trait === trait).sort((a, b) => a.set_points - b.set_points);
    let best = null;
    const visit = (index, chosen, points, spent) => {
      if (points >= 8) {
        if (!best || spent < best.spent || (spent === best.spent && chosen.length < best.spells.length)) best = { spells: [...chosen], spent };
        return;
      }
      if (index >= candidates.length || chosen.length >= maxSlots || (best && spent >= best.spent)) return;
      for (let nextIndex = index; nextIndex < candidates.length; nextIndex += 1) {
        const next = candidates[nextIndex];
        if (spent + next.set_points <= maxPoints) visit(nextIndex + 1, [...chosen, next], points + contribution(next), spent + next.set_points);
      }
    };
    visit(0, [], 0, 0);
    return best && best.spells;
  };
  const addGoalSpell = (chosen, options, label) => {
    const option = options.filter(spell => !chosen.includes(spell)).sort((a, b) => a.set_points - b.set_points || a.spell_level - b.spell_level)[0];
    if (!option || chosen.length >= slotLimit(level()) || cost(chosen) + option.set_points > pointLimit(level())) {
      el("goal-result").textContent = `No valid ${label} spell fits the selected restrictions.`;
      return false;
    }
    chosen.push(option);
    return true;
  };
  const solve = () => {
    const wantedTraits = selectedValues(el("goal-traits"));
    const wantedEffects = selectedValues(el("goal-effects"));
    const wantedChains = skillchainElementFilter && skillchainElementFilter.value ? [skillchainElementFilter.value] : [];
    const wantedDamage = [];
    const wantedStats = selectedValues(el("goal-stats"));
    if (![wantedTraits, wantedEffects, wantedChains, wantedDamage, wantedStats].some(values => values.length)) {
      el("goal-result").textContent = "Select at least one trait, skillchain element, damage weakness, effect, or stat priority.";
      return;
    }
    const pool = spells.filter(spell => spell.spell_level <= level() && (!el("goal-learned-only").checked || learned.has(spell.spell)));
    const chosen = [];
    const combatPool = spell => (!wantedDamage.length || wantedDamage.includes(physicalDamageType(spell)));
    for (const element of wantedChains) {
      const createsElement = spell => selfChainsFor(spell).some(chain => (burstElements[chain.final] || []).includes(element));
      if (!chosen.some(createsElement)) {
        if (!addGoalSpell(chosen, pool.filter(spell => combatPool(spell) && createsElement(spell)), `${element}${wantedDamage.length ? ` ${wantedDamage.join("/")}` : ""} skillchain`)) return;
      }
    }
    if (wantedDamage.length && !wantedChains.length) {
      for (const damage of wantedDamage) {
        if (!chosen.some(spell => physicalDamageType(spell) === damage)) {
          if (!addGoalSpell(chosen, pool.filter(spell => physicalDamageType(spell) === damage && chainProperties(spell).length), `${damage} Chain Affinity`)) return;
        }
      }
    }
    for (const effect of wantedEffects) {
      if (!chosen.some(spell => (spell.effects || []).includes(effect)) && !addGoalSpell(chosen, pool.filter(spell => (spell.effects || []).includes(effect)), effect)) return;
    }
    for (const trait of wantedTraits) {
      const combo = cheapestTraitSet(trait, pool.filter(spell => !chosen.includes(spell)), pointLimit(level()) - cost(chosen), slotLimit(level()) - chosen.length);
      if (!combo) { el("goal-result").textContent = `No valid ${trait} combination fits the selected restrictions.`; return; }
      combo.forEach(spell => { if (!chosen.includes(spell)) chosen.push(spell); });
    }
    if (el("trait-priority").value === "max" && wantedTraits.length) {
      pool.filter(spell => wantedTraits.includes(spell.trait) && !chosen.includes(spell)).sort((a, b) => (contribution(b) / b.set_points) - (contribution(a) / a.set_points)).forEach(spell => {
        if (chosen.length < slotLimit(level()) && cost(chosen) + spell.set_points <= pointLimit(level())) chosen.push(spell);
      });
    }
    if (wantedStats.length) {
      pool.filter(spell => !chosen.includes(spell)).map(spell => ({ spell, value: parseStats(spell).filter(stat => wantedStats.includes(stat.name)).reduce((sum, stat) => sum + stat.value, 0) })).filter(row => row.value > 0).sort((a, b) => (b.value / b.spell.set_points) - (a.value / a.spell.set_points)).forEach(({ spell }) => {
        if (chosen.length < slotLimit(level()) && cost(chosen) + spell.set_points <= pointLimit(level())) chosen.push(spell);
      });
    }
    equipped.clear(); chosen.forEach(spell => equipped.add(spell.spell));
    const missing = chosen.filter(spell => !learned.has(spell.spell)).length;
    el("goal-result").textContent = `Applied ${chosen.length} spells for ${cost(chosen)} points${missing ? `; ${missing} still need to be learned` : "; all are learned"}.`;
    render();
  };

  const addPlannedSelfChains = () => {
    const requested = spells.filter(spell => plannedSpellNames.has(spell.spell));
    if (!requested.length) { el("self-chain-status").textContent = "Select one or more Blue Magic options first."; return; }
    const chosen = current();
    const addIfFits = spell => {
      if (chosen.includes(spell)) return true;
      if (chosen.length >= slotLimit(level()) || cost(chosen) + Number(spell.set_points || 0) > pointLimit(level())) return false;
      chosen.push(spell);
      return true;
    };
    let reservedTraits = 0;
    selectedValues(el("goal-traits")).forEach(trait => {
      const present = chosen.filter(spell => spell.trait === trait).reduce((sum, spell) => sum + contribution(spell), 0);
      if (present >= 8) return;
      const reserve = cheapestTraitSet(trait, spells.filter(spell => !chosen.includes(spell) && spell.spell_level <= level()), pointLimit(level()) - cost(chosen), slotLimit(level()) - chosen.length) || [];
      reserve.forEach(spell => { if (addIfFits(spell)) reservedTraits += 1; });
    });
    let added = 0;
    let skipped = 0;
    requested.forEach(spell => {
      if (equipped.has(spell.spell) || addIfFits(spell)) added += 1;
      else skipped += 1;
    });
    equipped.clear(); chosen.forEach(spell => equipped.add(spell.spell));
    el("self-chain-status").textContent = `Added ${added} selected spell${added === 1 ? "" : "s"}${reservedTraits ? ` after reserving ${reservedTraits} trait spell${reservedTraits === 1 ? "" : "s"}` : ""}${skipped ? `; ${skipped} could not fit within the remaining points or slots` : ""}.`;
    render();
  };

  document.addEventListener("click", event => {
    const remove = event.target.closest("[data-remove]");
    if (remove) {
      event.preventDefault();
      event.stopPropagation();
      equipped.delete(remove.dataset.remove);
      render();
      return;
    }

    const toggle = event.target.closest("[data-toggle]");
    const quick = event.target.closest("[data-quick-add]");
    const view = event.target.closest("[data-view-spell]");
    if (toggle) {
      const name = toggle.dataset.toggle;
      if (equipped.has(name)) equipped.delete(name);
      else { const spell = spells.find(row => row.spell === name); if (spell && canAdd(spell)) equipped.add(name); }
      render();
    }
    if (view) { const spell = spells.find(row => row.spell === view.dataset.viewSpell); if (spell) showSpell(spell); }
    if (quick) { const spell = spells.find(row => row.spell === quick.dataset.quickAdd); if (spell && canAdd(spell)) { equipped.add(spell.spell); render(); renderQuickPicker(); } }
    if (event.target.closest("#add-spell-tile")) openPicker();
  });
  levelInput.addEventListener("input", render);
  ["book-search", "book-skillchain-filter", "book-damage-filter"].forEach(id => {
    el(id).addEventListener("input", render);
    el(id).addEventListener("change", render);
  });
  el("book-learned-only").addEventListener("change", render);
  selfChainPlanner.addEventListener("change", event => {
    const input = event.target.closest("[data-self-chain-spell]");
    if (!input) return;
    if (input.checked) plannedSpellNames.add(input.dataset.selfChainSpell);
    else plannedSpellNames.delete(input.dataset.selfChainSpell);
  });
  el("add-selected-self-chains").addEventListener("click", addPlannedSelfChains);
  el("clear-book").addEventListener("click", () => { equipped.clear(); render(); });
  el("solve-goals").addEventListener("click", solve);
  el("clear-goals").addEventListener("click", () => { document.querySelectorAll(".goal-options input").forEach(input => { input.checked = false; }); el("goal-result").textContent = "Goal selections cleared."; render(); });
  el("quick-spell-search").addEventListener("input", renderQuickPicker);
  el("close-spell-picker").addEventListener("click", () => { el("spell-picker-modal").hidden = true; });
  el("close-spell-detail").addEventListener("click", () => { el("spell-detail-modal").hidden = true; });
  [el("spell-picker-modal"), el("spell-detail-modal")].forEach(modal => modal.addEventListener("click", event => { if (event.target === modal) modal.hidden = true; }));

  Promise.all([
    fetch("/static/blue_spell_farming.json?v=3").then(response => response.json()),
    fetch("/static/skillchain_catalog.json?v=6").then(response => response.json()),
  ]).then(([farming, skillchains]) => {
    const unique = new Map();
    farming.rows.forEach(row => { if (!unique.has(row.spell)) unique.set(row.spell, row); });
    spells = [...unique.values()];
    chainActions = new Map((skillchains.actions || []).filter(action => action.weapon === "Blue Magic").map(action => [action.name, action]));
    weaponActions = (skillchains.actions || []).filter(action => action.weapon !== "Blue Magic" && action.kind === "Weapon Skill");
    skillchainCaps = skillchains.skill_caps || {};
    const properties = [...new Set(spells.flatMap(selfChainsFor).map(chain => chain.final))].sort();
    const damageTypes = [...new Set(spells.map(physicalDamageType).filter(Boolean))].sort();
    const plannerControls = selfChainPlanner.querySelector(".self-chain-controls");
    el("book-skillchain-filter").closest("label").hidden = true;
    const elementLabel = document.createElement("label");
    elementLabel.innerHTML = 'Skillchain Element<select id="book-skillchain-element-filter"><option value="">Choose an element</option></select>';
    plannerControls.append(elementLabel);
    skillchainElementFilter = elementLabel.querySelector("select");
    [...new Set(Object.values(burstElements).flat())].sort().forEach(value => skillchainElementFilter.add(new Option(value, value)));
    skillchainElementFilter.addEventListener("change", render);
    const damageLabel = el("book-damage-filter").closest("label");
    damageLabel.firstChild.textContent = "Physical damage weakness";
    plannerControls.append(damageLabel);
    el("book-damage-filter").insertAdjacentHTML("beforeend", damageTypes.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join(""));
    const addGoals = (container, values) => { container.innerHTML = values.map(value => `<label><input type="checkbox" value="${escapeHtml(value)}"><span>${escapeHtml(value)}</span></label>`).join(""); };
    const effectLabels = { "HP Drain": "HP Drain (Drain)", "MP Drain": "MP Drain (Aspir)", "Defense Down": "Defense Down (Dia)", "Attack Down": "Attack Down (Bio)", "Magic Defense Down": "Magic Defense Down", "Accuracy Down": "Accuracy Down", "Evasion Down": "Evasion Down", "Cure": "Restore HP (Cure)", "Paralyze": "Paralyze", "Blind": "Blind", "Silence": "Silence", "Dispel": "Dispel", "Haste": "Haste", "Stoneskin": "Stoneskin", "Blink": "Blink" };
    const effectField = document.createElement("fieldset");
    effectField.innerHTML = '<legend>Additional effects / spell equivalents</legend><div id="goal-effects" class="goal-options"></div>';
    el("goal-stats").closest("fieldset").before(effectField);
    addGoals(el("goal-traits"), [...new Set(spells.map(spell => spell.trait).filter(Boolean))].sort());
    const effects = [...new Set(spells.flatMap(spell => spell.effects || []))].sort();
    el("goal-effects").innerHTML = effects.map(value => `<label><input type="checkbox" value="${escapeHtml(value)}"><span>${escapeHtml(effectLabels[value] || value)}</span></label>`).join("");
    addGoals(el("goal-stats"), [...new Set(spells.flatMap(spell => parseStats(spell).map(stat => stat.name)))].sort());
    ["book-search", "book-learned-only"].forEach(id => el(id).closest("label").hidden = true);
    render();
  }).catch(() => { el("book-catalog").innerHTML = '<p class="book-empty">Spell or skillchain data could not be loaded.</p>'; });
})();
