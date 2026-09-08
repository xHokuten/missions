(() => {
  const data = window.GEAR_OPTIMIZER;
  if (!data) return;

  let calculatedSet = {};
  let equipmentSet = {};
  let setInitialized = false;
  let activeSlot = "main";
  const jobControl = document.querySelector("#gear-job");
  const levelControl = document.querySelector("#gear-level");
  const primaryControl = document.querySelector("#gear-primary-stat");
  const secondaryControl = document.querySelector("#gear-secondary-stat");
  const negativeControl = document.querySelector("#gear-negative");
  const conditionalEffectsControl = document.querySelector("#gear-conditional-effects");
  const raceControl = document.querySelector("#gear-race");
  const scopeControl = document.querySelector("#gear-scope");
  const activeSearchControl = document.querySelector("#gear-active-search");
  let ownedCounts = new Map(Object.entries(data.archived || {}).map(([id, count]) => [Number(id), Number(count)]));
  let catalog = [];
  let marketPrices = {};
  let gearValueSort = { key: "total", direction: -1 };
  const slotOrder = [
    "main", "sub", "ranged", "ammo",
    "head", "neck", "ear1", "ear2",
    "body", "hands", "ring1", "ring2",
    "back", "waist", "legs", "feet",
  ];
  const labels = { main: "Main", sub: "Sub", ranged: "Ranged", ammo: "Ammo", head: "Head", body: "Body", hands: "Hands", legs: "Legs", feet: "Feet", neck: "Neck", waist: "Waist", ear1: "Left Ear", ear2: "Right Ear", ring1: "Left Ring", ring2: "Right Ring", back: "Back" };
  const pairedSlots = { ear1: "ear2", ear2: "ear1", ring1: "ring2", ring2: "ring1" };

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const wikiStar = item => {
    const link = element("a", "gear-wiki-star", "\u2605");
    link.href = `https://www.bg-wiki.com/ffxi/${encodeURIComponent(item.name.replace(/\s+/g, "_"))}`;
    link.target = "_blank";
    link.rel = "noopener";
    link.title = `Open ${item.name} on BG Wiki`;
    link.setAttribute("aria-label", link.title);
    link.addEventListener("click", event => event.stopPropagation());
    link.addEventListener("keydown", event => event.stopPropagation());
    return link;
  };
  const auctionHouseLink = item => {
    if (item.ex) return null;
    const link = element("a", "gear-ah-link", "$");
    const slug = item.name.toLowerCase().replace(/[.'’]/g, "").replace(/\+/g, "-plus-").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    link.href = item.ah_category
      ? `https://www.psxi.gg/s/horizonxi/ah/${item.ah_category}/${slug}`
      : "https://www.psxi.gg/s/horizonxi/ah";
    link.target = "_blank";
    link.rel = "noopener";
    link.title = `Find ${item.name} on the HorizonXI Auction House`;
    link.setAttribute("aria-label", link.title);
    link.addEventListener("click", event => event.stopPropagation());
    link.addEventListener("keydown", event => event.stopPropagation());
    return link;
  };
  const rarityLabel = item => item.rare && item.ex ? "Rare/Ex" : item.rare ? "Rare" : item.ex ? "Ex" : "";
  const rarityBadge = item => {
    const label = rarityLabel(item);
    return label ? element("span", `gear-rarity${item.rare ? " rare" : ""}${item.ex ? " ex" : ""}`, label) : null;
  };
  const marketKey = value => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const formatGil = value => `${Math.max(0, Math.round(Number(value) || 0)).toLocaleString()}g`;
  const liquidUnitValue = item => {
    const price = marketPrices[marketKey(item.name)];
    const values = [price?.bazaar_lowest, price?.single_recent_average, price?.single_average]
      .map(Number).filter(value => Number.isFinite(value) && value > 0);
    return values.length ? Math.min(...values) : 0;
  };
  const renderGearValue = () => {
    const totalNode = document.querySelector("#gear-liquid-value");
    const body = document.querySelector("#gear-value-rows");
    if (!totalNode || !body) return;
    const owned = catalog.filter(item => ownedCounts.has(Number(item.item_id)) && !item.ex).map(item => {
      const quantity = ownedCounts.get(Number(item.item_id)) || 0;
      const unit = liquidUnitValue(item);
      return { item, quantity, unit, total: quantity * unit, slot: (item.slots || [item.slot]).join(" / "), jobs: (item.jobs || []).join(" / ") || "All Jobs" };
    });
    const total = owned.reduce((sum, row) => sum + row.total, 0);
    totalNode.textContent = formatGil(total);
    const slotControl = document.querySelector("#gear-value-slot");
    const jobControl = document.querySelector("#gear-value-job");
    const currentSlot = slotControl.value, currentJob = jobControl.value;
    const slots = [...new Set(owned.flatMap(row => (row.item.slots || [row.item.slot]).filter(Boolean)))].sort();
    const jobs = [...new Set(owned.flatMap(row => row.item.jobs || []))].sort();
    slotControl.replaceChildren(new Option("All slots", ""), ...slots.map(value => new Option(value, value)));
    jobControl.replaceChildren(new Option("All jobs", ""), ...jobs.map(value => new Option(value, value)));
    slotControl.value = slots.includes(currentSlot) ? currentSlot : "";
    jobControl.value = jobs.includes(currentJob) ? currentJob : "";
    const query = document.querySelector("#gear-value-search").value.trim().toLowerCase();
    const filtered = owned.filter(row => (!query || row.item.name.toLowerCase().includes(query)) &&
      (!slotControl.value || (row.item.slots || [row.item.slot]).includes(slotControl.value)) &&
      (!jobControl.value || (row.item.jobs || []).includes(jobControl.value)));
    filtered.sort((left, right) => {
      const a = gearValueSort.key === "name" ? left.item.name : left[gearValueSort.key];
      const b = gearValueSort.key === "name" ? right.item.name : right[gearValueSort.key];
      return (typeof a === "number" ? a - b : String(a).localeCompare(String(b))) * gearValueSort.direction;
    });
    document.querySelector("#gear-value-count").textContent = `${filtered.length} sellable item${filtered.length === 1 ? "" : "s"}`;
    body.replaceChildren(...(filtered.length ? filtered.map(row => {
      const tr = document.createElement("tr");
      const icon = document.createElement("img"); icon.src = `https://static.ffxiah.com/images/icon/${row.item.item_id}.png`; icon.alt = ""; icon.className = "gear-value-icon";
      const name = element("td"); name.append(icon, document.createTextNode(row.item.name)); bindTooltip(name, row.item);
      tr.append(name);
      [row.quantity, row.slot, row.jobs, row.unit ? formatGil(row.unit) : "No price", row.total ? formatGil(row.total) : "—"].forEach(value => tr.append(element("td", "", value)));
      return tr;
    }) : [element("tr", "", "")]).map(node => node));
    if (!filtered.length) { const cell = body.querySelector("td") || document.createElement("td"); cell.colSpan = 6; cell.textContent = owned.length ? "No sellable items match these filters." : "Import gear to calculate its liquid value."; if (!cell.parentElement) { const row = body.querySelector("tr"); row.append(cell); } }
  };

  const tooltip = element("aside", "gear-item-tooltip");
  tooltip.setAttribute("role", "tooltip");
  tooltip.hidden = true;
  document.body.append(tooltip);
  const tooltipPosition = (x, y) => {
    const width = tooltip.offsetWidth || 370;
    const height = tooltip.offsetHeight || 220;
    tooltip.style.left = `${Math.max(10, Math.min(x + 16, window.innerWidth - width - 10))}px`;
    tooltip.style.top = `${Math.max(10, Math.min(y + 16, window.innerHeight - height - 10))}px`;
  };
  const showTooltip = (item, x, y) => {
    const icon = document.createElement("img");
    icon.src = `https://static.ffxiah.com/images/icon/${item.item_id}.png`;
    icon.alt = "";
    icon.loading = "lazy";
    icon.addEventListener("error", () => icon.classList.add("missing"), { once: true });
    const copy = element("div", "gear-tooltip-copy");
    const itemSlots = Array.isArray(item.slots) ? item.slots : [item.slot].filter(Boolean);
    const itemJobs = Array.isArray(item.jobs) ? item.jobs.join(" / ") : item.jobs || "All Jobs";
    const itemRaces = Array.isArray(item.races) ? item.races.join(" / ") : item.races || "All Races";
    const tooltipRarity = rarityBadge(item);
    copy.append(
      element("strong", "", item.name),
      ...(tooltipRarity ? [tooltipRarity] : []),
      element("span", "", `Lv. ${item.level || 0} | ${itemSlots.join(" / ")}`),
      element("p", "gear-tooltip-description", item.description || "No item description available."),
      element("small", "", `${itemJobs}\n${itemRaces}`),
    );
    tooltip.replaceChildren(icon, copy);
    tooltip.hidden = false;
    tooltipPosition(x, y);
  };
  const hideTooltip = () => { tooltip.hidden = true; };
  const bindTooltip = (node, item) => {
    node.classList.add("gear-tooltip-target");
    node.tabIndex = 0;
    node.addEventListener("mouseenter", event => showTooltip(item, event.clientX, event.clientY));
    node.addEventListener("mousemove", event => tooltipPosition(event.clientX, event.clientY));
    node.addEventListener("mouseleave", hideTooltip);
    node.addEventListener("focus", () => {
      const box = node.getBoundingClientRect();
      showTooltip(item, box.right, box.top);
    });
    node.addEventListener("blur", hideTooltip);
  };

  const itemStats = item => {
    if (!item) return {};
    const stats = { ...(item.stats || {}) };
    if (conditionalEffectsControl.checked) {
      Object.entries(item.latent_stats || {}).forEach(([stat, value]) => {
        stats[stat] = Number(stats[stat] || 0) + Number(value || 0);
      });
    }
    Object.entries(item.level_scaling || {}).forEach(([stat, range]) => {
      const minimumLevel = Number(range.min_level || item.level || 1);
      const maximumLevel = Number(range.max_level || 75);
      const tierLevels = Number(range.tier_levels || 15);
      const selectedLevel = Math.max(minimumLevel, Math.min(Number(levelControl.value || 75), maximumLevel));
      const totalTiers = Math.max(1, Math.ceil((maximumLevel - minimumLevel) / tierLevels));
      const currentTier = Math.min(totalTiers, Math.floor((selectedLevel - minimumLevel) / tierLevels));
      stats[stat] = Math.round(Number(range.min) +
        (Number(range.max) - Number(range.min)) * currentTier / totalTiers);
    });
    return stats;
  };
  const selectedStats = () => [primaryControl.value, secondaryControl.value].filter(Boolean);
  const score = item => {
    const stats = itemStats(item);
    const direction = negativeControl.checked ? -1 : 1;
    return (Number(stats[primaryControl.value] || 0) * 2 + Number(stats[secondaryControl.value] || 0)) * direction;
  };

  const applicableSlots = item => {
    if (Array.isArray(item.slots)) {
      return [...new Set(item.slots.flatMap(slot => applicableSlots({ slot })))];
    }
    const slot = String(item.slot || "").toLowerCase();
    if (slot.includes("main/sub")) return ["main", "sub"];
    if (slot === "range" || slot === "ranged") return ["ranged"];
    if (slot === "ear") return ["ear1", "ear2"];
    if (slot === "ring") return ["ring1", "ring2"];
    const match = slotOrder.find(candidate => candidate.replace(/[12]$/, "") === slot);
    return match ? [match] : [];
  };
  const duplicateInPairedSlot = (item, slot, gear = equipmentSet) => {
    const paired = pairedSlots[slot];
    return Boolean(paired && gear[paired] && Number(gear[paired].item_id) === Number(item.item_id));
  };
  const pairedDuplicateAllowed = (item, slot, gear = equipmentSet) => {
    if (!duplicateInPairedSlot(item, slot, gear)) return true;
    if (item.rare) return false;
    if (scopeControl.value !== "owned") return true;
    const copiesAlreadyUsed = Object.entries(gear)
      .filter(([candidate, equipped]) => candidate !== slot && equipped && Number(equipped.item_id) === Number(item.item_id))
      .length;
    return copiesAlreadyUsed < (ownedCounts.get(Number(item.item_id)) || 0);
  };
  const equipItem = (item, slot) => {
    const paired = pairedSlots[slot];
    if (!pairedDuplicateAllowed(item, slot) && paired) {
      equipmentSet[paired] = null;
    }
    if (slot === "main" && item.two_handed) equipmentSet.sub = null;
    if (slot === "sub" && equipmentSet.main && equipmentSet.main.two_handed) equipmentSet.main = null;
    equipmentSet[slot] = item;
    setInitialized = true;
  };

  const isCompatible = item => {
    const level = Number(levelControl.value || 75);
    const jobs = Array.isArray(item.jobs) ? item.jobs : String(item.jobs || "").split("/");
    const races = Array.isArray(item.races) ? item.races : [];
    return Number(item.level || 0) <= level &&
      (!jobs.length || jobs.includes("All Jobs") || jobs.includes(jobControl.value)) &&
      (!races.length || !raceControl.value || races.includes(raceControl.value));
  };
  const availableCatalog = () => scopeControl.value === "owned"
    ? catalog.filter(item => ownedCounts.has(Number(item.item_id)))
    : catalog;
  const ownsEquippedCopy = (item, slot) => {
    if (scopeControl.value !== "owned" || !item) return true;
    const usedBeforeOrAtSlot = slotOrder.slice(0, slotOrder.indexOf(slot) + 1)
      .filter(candidate => equipmentSet[candidate] && Number(equipmentSet[candidate].item_id) === Number(item.item_id)).length;
    return usedBeforeOrAtSlot <= (ownedCounts.get(Number(item.item_id)) || 0);
  };
  const updatePresetButtons = () => {
    document.querySelector("#gear-use-best").classList.toggle("active", scopeControl.value === "all");
    document.querySelector("#gear-use-current").classList.toggle("active", scopeControl.value === "owned");
  };

  const renderEquipmentSet = () => {
    const container = document.querySelector("#gear-best-slots");
    let equippedCount = 0;
    const cards = slotOrder.map(slot => {
      const item = equipmentSet[slot];
      const unowned = item && !ownsEquippedCopy(item, slot);
      const card = element("article", `gear-slot${item ? "" : " empty"}${unowned ? " unowned" : ""}${slot === activeSlot ? " active" : ""}`);
      card.addEventListener("click", () => {
        if (slot !== activeSlot) activeSearchControl.value = "";
        activeSlot = slot;
        renderEquipmentSet();
        renderActiveItems();
      });
      card.append(element("span", "gear-slot-label", labels[slot]));
      if (!item) {
        card.tabIndex = 0;
        card.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") { event.preventDefault(); card.click(); }
        });
        const emptyMark = element("span", "gear-slot-empty-mark", "\u00d7");
        emptyMark.setAttribute("aria-label", "No matching item");
        card.append(emptyMark);
        return card;
      }
      equippedCount += 1;
      const clearButton = element("button", "gear-slot-clear", "\u00d7");
      clearButton.type = "button";
      clearButton.title = `Clear ${labels[slot]}`;
      clearButton.addEventListener("click", event => {
        event.stopPropagation();
        equipmentSet[slot] = null;
        renderEquipmentSet();
        renderTotals();
        renderCatalog();
      });
      const icon = document.createElement("img");
      icon.className = "gear-slot-icon";
      icon.src = `https://static.ffxiah.com/images/icon/${item.item_id}.png`;
      icon.alt = item.name;
      icon.addEventListener("error", () => icon.classList.add("missing"), { once: true });
      card.append(clearButton, icon);
      const ahLink = auctionHouseLink(item);
      if (ahLink) card.append(ahLink);
      card.append(wikiStar(item));
      bindTooltip(card, item);
      return card;
    });
    container.replaceChildren(...cards);
    document.querySelector("#gear-load-summary").dataset.count = `${equippedCount}/${slotOrder.length} slots filled`;
  };

  const matchingItemsForSlot = slot => {
    const stat = primaryControl.value;
    return catalog.filter(item => {
      const value = Number(itemStats(item)[stat] || 0);
      return isCompatible(item) && applicableSlots(item).includes(slot) &&
        (negativeControl.checked ? value < 0 : value > 0);
    }).sort((a, b) => score(b) - score(a) || a.level - b.level || a.name.localeCompare(b.name));
  };

  const renderActiveItems = () => {
    const allItems = matchingItemsForSlot(activeSlot);
    const query = activeSearchControl.value.trim().toLocaleLowerCase();
    const items = allItems.filter(item => !query || item.name.toLocaleLowerCase().includes(query));
    const stat = primaryControl.value;
    document.querySelector("#gear-active-slot").textContent = labels[activeSlot];
    document.querySelector("#gear-active-count").textContent = query ? `${items.length} of ${allItems.length} items` : `${items.length} items`;
    const nodes = items.map(item => {
      const unowned = scopeControl.value === "owned" && !ownedCounts.has(Number(item.item_id));
      const row = element("article", `gear-active-item${equipmentSet[activeSlot] && equipmentSet[activeSlot].item_id === item.item_id ? " equipped" : ""}${unowned ? " unowned" : ""}`);
      row.setAttribute("role", "button");
      const icon = document.createElement("img");
      icon.src = `https://static.ffxiah.com/images/icon/${item.item_id}.png`;
      icon.alt = "";
      const copy = element("span", "");
      copy.append(element("strong", "", item.name));
      const badge = rarityBadge(item);
      if (badge) copy.append(badge);
      copy.append(element("small", "", `Lv. ${item.level}`));
      const value = Number(itemStats(item)[stat] || 0);
      row.append(icon, copy, element("b", "", `${value >= 0 ? "+" : ""}${value}`));
      const ahLink = auctionHouseLink(item);
      if (ahLink) row.append(ahLink);
      row.append(wikiStar(item));
      row.addEventListener("click", () => {
        equipItem(item, activeSlot);
        renderEquipmentSet();
        renderTotals();
        renderCatalog();
        renderActiveItems();
      });
      row.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); row.click(); }
      });
      bindTooltip(row, item);
      return row;
    });
    document.querySelector("#gear-active-items").replaceChildren(...(nodes.length ? nodes : [element("p", "gear-empty", query ? `No ${labels[activeSlot]} items match “${activeSearchControl.value.trim()}”.` : `No matching ${labels[activeSlot]} items.`)]));
  };

  const renderTotals = () => {
    const totals = {};
    Object.values(equipmentSet).filter(Boolean).forEach(item => {
      Object.entries(itemStats(item)).forEach(([name, value]) => {
        totals[name] = (totals[name] || 0) + Number(value);
      });
    });
    const priorities = new Set(selectedStats());
    const nodes = Object.entries(totals).sort(([a], [b]) => a.localeCompare(b)).map(([name, value]) => {
      const chip = element("span", `gear-stat${priorities.has(name) ? " priority" : ""}`);
      chip.append(document.createTextNode(name), element("strong", "", `${value >= 0 ? "+" : ""}${value}`));
      return chip;
    });
    document.querySelector("#gear-stat-totals").replaceChildren(...(nodes.length ? nodes : [element("span", "gear-empty", "No equipment stats available.")]));
  };

  const currentComparison = item => {
    const slots = applicableSlots(item);
    if (!slots.length) return null;
    return slots.map(slot => ({ slot, current: equipmentSet[slot], delta: score(item) - score(equipmentSet[slot]) }))
      .sort((a, b) => b.delta - a.delta)[0];
  };

  const renderCatalog = () => {
    const stat = primaryControl.value;
    document.querySelector("#catalog-stat-name").textContent = stat;
    const matches = availableCatalog().filter(item => {
      const value = Number(itemStats(item)[stat] || 0);
      return isCompatible(item) && (negativeControl.checked ? value < 0 : value > 0);
    });
    const groups = new Map();
    matches.forEach(item => (item.slots || []).forEach(slot => {
      if (!groups.has(slot)) groups.set(slot, []);
      groups.get(slot).push(item);
    }));
    const orderedSlots = ["Main", "Sub", "Ranged", "Ammo", "Head", "Body", "Hands", "Legs", "Feet", "Neck", "Waist", "Ear", "Ring", "Back"];
    const sections = orderedSlots.filter(slot => groups.has(slot)).map(slot => {
      const direction = negativeControl.checked ? -1 : 1;
      const items = groups.get(slot).sort((a, b) =>
        (Number(itemStats(b)[stat] || 0) - Number(itemStats(a)[stat] || 0)) * direction ||
        a.level - b.level || a.name.localeCompare(b.name)
      );
      const section = element("section", "gear-catalog-slot");
      const header = document.createElement("header");
      header.append(element("h3", "", slot), element("span", "", `${items.length} items`));
      const list = element("div", "gear-catalog-items");
      list.replaceChildren(...items.map(item => {
        const comparison = currentComparison(item);
        const currentValue = comparison && comparison.current ? Number(itemStats(comparison.current)[stat] || 0) : 0;
        const value = Number(itemStats(item)[stat] || 0);
        const delta = value - currentValue;
        const row = element("article", "gear-catalog-item");
        const improvement = delta * direction;
        row.append(
          element("h4", "", item.name),
          element("strong", "gear-catalog-value", `${value >= 0 ? "+" : ""}${value}`),
          element("strong", `gear-catalog-delta${improvement < 0 ? " negative" : ""}`, `${delta >= 0 ? "+" : ""}${delta}`),
          element("p", "", `Lv. ${item.level} | ${item.description || stat}`),
        );
        const ahLink = auctionHouseLink(item);
        if (ahLink) row.append(ahLink);
        row.append(wikiStar(item));
        const badge = rarityBadge(item);
        if (badge) row.querySelector("h4").append(" ", badge);
        const actions = element("div", "gear-equip-actions");
        applicableSlots(item).forEach(targetSlot => {
          const button = element("button", `gear-equip-button${equipmentSet[targetSlot] && equipmentSet[targetSlot].item_id === item.item_id ? " equipped" : ""}`, `Equip ${labels[targetSlot]}`);
          button.type = "button";
          button.addEventListener("click", () => {
            equipItem(item, targetSlot);
            renderEquipmentSet();
            renderTotals();
            renderCatalog();
          });
          actions.append(button);
        });
        row.append(actions);
        bindTooltip(row, item);
        return row;
      }));
      section.append(header, list);
      return section;
    });
    document.querySelector("#gear-catalog-count").textContent = `${matches.length} compatible items`;
    document.querySelector("#gear-catalog-results").replaceChildren(...(sections.length ? sections : [element("p", "gear-empty", `No compatible ${stat} equipment found.`)]));
  };

  const refresh = () => {
    const stat = primaryControl.value;
    const direction = negativeControl.checked ? -1 : 1;
    const candidates = availableCatalog().filter(item => {
      const value = Number(itemStats(item)[stat] || 0);
      return isCompatible(item) && (negativeControl.checked ? value < 0 : value > 0);
    }).sort((a, b) => (score(b) - score(a)) || a.level - b.level || a.name.localeCompare(b.name));
    calculatedSet = {};
    const remaining = new Map(ownedCounts);
    slotOrder.forEach(slot => {
      const mainBlocksSub = slot === "sub" && calculatedSet.main && calculatedSet.main.two_handed;
      const match = mainBlocksSub ? null : candidates.find(item =>
        applicableSlots(item).includes(slot) &&
        pairedDuplicateAllowed(item, slot, calculatedSet) &&
        (scopeControl.value !== "owned" || (remaining.get(Number(item.item_id)) || 0) > 0));
      calculatedSet[slot] = match || null;
      if (match && scopeControl.value === "owned") {
        remaining.set(Number(match.item_id), remaining.get(Number(match.item_id)) - 1);
      }
    });
    if (!setInitialized && catalog.length) {
      equipmentSet = { ...calculatedSet };
      setInitialized = true;
    }
    renderEquipmentSet();
    renderTotals();
    renderCatalog();
    renderActiveItems();
    updatePresetButtons();
  };

  const rebuildFromFilters = () => {
    setInitialized = false;
    refresh();
  };
  [jobControl, levelControl, raceControl, primaryControl, secondaryControl, negativeControl, conditionalEffectsControl, scopeControl]
    .forEach(control => control.addEventListener("change", rebuildFromFilters));

  document.querySelector("#gear-collapse-set").addEventListener("click", event => {
    const body = document.querySelector("#gear-set-body");
    body.hidden = !body.hidden;
    event.currentTarget.innerHTML = body.hidden ? "&#9656;" : "&#9662;";
    event.currentTarget.setAttribute("aria-label", body.hidden ? "Expand equipment setup" : "Collapse equipment setup");
    event.currentTarget.setAttribute("aria-expanded", String(!body.hidden));
  });
  document.querySelector("#gear-import-section").addEventListener("toggle", event => {
    document.querySelector("#gear-import-collapse").innerHTML = event.currentTarget.open ? "&#9662;" : "&#9656;";
  });

  const normalizeItemName = name => name.toLowerCase().replace(/['’]/g, "").replace(/\s*x\d+$/i, "").replace(/[^a-z0-9+]+/g, " ").trim();
  const updateImportStatus = (matched = ownedCounts.size, unmatched = 0) => {
    const total = [...ownedCounts.values()].reduce((sum, count) => sum + count, 0);
    document.querySelector("#gear-import-status").textContent = total
      ? `${total} equipment item${total === 1 ? "" : "s"} matched (${matched} unique${unmatched ? `, ${unmatched} unmatched lines` : ""})`
      : "No gear imported";
  };
  const restoreImportedGear = () => {
    updateImportStatus();
  };
  const showImportedState = imported => {
    document.querySelector("#gear-import-instructions").hidden = imported;
    document.querySelector("#gear-import-text").hidden = imported;
    document.querySelector("#gear-import-button").hidden = imported;
    document.querySelector("#gear-import-success").hidden = !imported;
  };
  const archiveImportedGear = async inventory => {
    const form = new FormData();
    form.append("csrf_token", data.csrf);
    form.append("inventory", JSON.stringify(Object.fromEntries(inventory)));
    const response = await fetch(data.archiveUrl, { method: "POST", body: form, credentials: "same-origin" });
    if (!response.ok) throw new Error("The site could not save this inventory.");
    return response.json();
  };
  document.querySelector("#gear-import-button").addEventListener("click", async event => {
    const button = event.currentTarget;
    const lines = document.querySelector("#gear-import-text").value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const byName = new Map(catalog.map(item => [normalizeItemName(item.name), item]));
    const imported = new Map();
    let unmatched = 0;
    for (let index = 0; index < lines.length; index += 1) {
      if (!/^\d+\t/.test(lines[index + 1] || "")) continue;
      const quantity = Math.max(1, Number.parseInt(lines[index + 1].split("\t")[0], 10) || 1);
      const item = byName.get(normalizeItemName(lines[index]));
      if (item) imported.set(Number(item.item_id), (imported.get(Number(item.item_id)) || 0) + quantity);
      else unmatched += 1;
      index += 1;
    }
    button.disabled = true;
    button.textContent = "Saving...";
    try {
      await archiveImportedGear(imported);
      ownedCounts = imported;
      updateImportStatus(imported.size, unmatched);
      scopeControl.value = "owned";
      setInitialized = false;
      document.querySelector("#gear-import-text").value = "";
      showImportedState(true);
      refresh();
      renderGearValue();
    } catch (error) {
      document.querySelector("#gear-import-status").textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = "Import Gear";
    }
  });
  document.querySelector("#gear-clear-import").addEventListener("click", async () => {
    try {
      await archiveImportedGear(new Map());
      ownedCounts = new Map();
      document.querySelector("#gear-import-text").value = "";
      showImportedState(false);
      document.querySelector("#gear-import-section").open = true;
      scopeControl.value = "all";
      setInitialized = false;
      updateImportStatus();
      refresh();
      renderGearValue();
    } catch (error) {
      document.querySelector("#gear-import-status").textContent = error.message;
    }
  });

  document.querySelector("#gear-use-best").addEventListener("click", () => {
    scopeControl.value = "all";
    setInitialized = false;
    refresh();
  });

  document.querySelector("#gear-use-current").addEventListener("click", () => {
    scopeControl.value = "owned";
    setInitialized = false;
    refresh();
  });

  document.querySelector("#gear-clear-set").addEventListener("click", () => {
    equipmentSet = Object.fromEntries(slotOrder.map(slot => [slot, null]));
    setInitialized = true;
    renderEquipmentSet();
    renderTotals();
    renderCatalog();
    renderActiveItems();
  });
  activeSearchControl.addEventListener("input", renderActiveItems);
  ["#gear-value-search", "#gear-value-slot", "#gear-value-job"].forEach(selector => {
    document.querySelector(selector).addEventListener(selector.includes("search") ? "input" : "change", renderGearValue);
  });
  document.querySelector("#gear-value-section").addEventListener("toggle", event => {
    document.querySelector("#gear-value-collapse").innerHTML = event.currentTarget.open ? "&#9662;" : "&#9656;";
  });
  document.querySelectorAll("[data-gear-value-sort]").forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.gearValueSort;
    gearValueSort = { key, direction: gearValueSort.key === key ? -gearValueSort.direction : (key === "name" ? 1 : -1) };
    renderGearValue();
  }));

  const safeSetName = () => document.querySelector("#gear-set-name").value.trim() || "Hokuten Gear Set";
  const xmlEscape = value => String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&apos;");
  const luaEscape = value => String(value).replace(/\\/g, "\\\\").replace(/\"/g, '\\"');
  let copyStatusTimer;
  const copyExport = async (contents, format) => {
    const status = document.querySelector("#gear-copy-status");
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(contents);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = contents;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        if (!document.execCommand("copy")) throw new Error("Copy failed");
        textarea.remove();
      }
      status.textContent = `${format} copied!`;
    } catch (_error) {
      status.textContent = `Could not copy ${format}.`;
    }
    window.clearTimeout(copyStatusTimer);
    copyStatusTimer = window.setTimeout(() => { status.textContent = ""; }, 3000);
  };
  const exportSlots = {
    main: "main", sub: "sub", ranged: "range", ammo: "ammo", head: "head", body: "body",
    hands: "hands", legs: "legs", feet: "feet", neck: "neck", waist: "waist", ear1: "lear",
    ear2: "rear", ring1: "lring", ring2: "rring", back: "back",
  };
  document.querySelector("#gear-export-xml").addEventListener("click", () => {
    const name = safeSetName();
    const rows = slotOrder.filter(slot => equipmentSet[slot]).map(slot => `      <${exportSlots[slot]}>${xmlEscape(equipmentSet[slot].name)}</${exportSlots[slot]}>`);
    const xml = `<set name="${xmlEscape(name)}">\n${rows.map(row => `  ${row.trim()}`).join("\n")}\n</set>\n`;
    copyExport(xml, "XML");
  });
  document.querySelector("#gear-export-lua").addEventListener("click", () => {
    const name = safeSetName();
    const luaSlots = { ...exportSlots, ear1: "left_ear", ear2: "right_ear", ring1: "left_ring", ring2: "right_ring" };
    const rows = slotOrder.filter(slot => equipmentSet[slot]).map(slot => `    ${luaSlots[slot]} = "${luaEscape(equipmentSet[slot].name)}",`);
    const lua = `sets["${luaEscape(name)}"] = {\n${rows.join("\n")}\n}\n`;
    copyExport(lua, "Lua");
  });
  refresh();
  fetch(data.catalogUrl)
    .then(response => {
      if (!response.ok) throw new Error("Equipment catalog unavailable");
      return response.json();
    })
    .then(payload => {
      catalog = payload.rows || [];
      restoreImportedGear();
      (payload.stats || []).forEach(stat => {
        [primaryControl, secondaryControl].forEach(control => {
          if (![...control.options].some(option => option.value === stat)) {
            control.add(new Option(stat, stat));
          }
        });
      });
      refresh();
      renderGearValue();
    })
    .catch(error => {
      document.querySelector("#gear-catalog-count").textContent = error.message;
    });
  fetch("/api/market-prices", {headers: {"Accept": "application/json"}})
    .then(response => response.ok ? response.json() : Promise.reject())
    .then(snapshot => {
      marketPrices = Object.fromEntries(Object.values(snapshot.prices || {}).filter(price => price.name).map(price => [marketKey(price.name), price]));
      renderGearValue();
    })
    .catch(() => { document.querySelector("#gear-liquid-value").textContent = "Market unavailable"; });
})();
