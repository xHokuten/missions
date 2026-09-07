(() => {
  document.querySelectorAll('input[name="dkp_cost"]').forEach(input => { input.step = "1"; });
  const tabs = [...document.querySelectorAll("[data-endgame-tab]")];
  const panels = [...document.querySelectorAll("[data-endgame-panel]")];
  const viewTabs = [...document.querySelectorAll("[data-endgame-view]")];
  const viewPanels = [...document.querySelectorAll("[data-endgame-view-panel]")];
  const activateView = name => {
    viewTabs.forEach(tab => tab.classList.toggle("active", tab.dataset.endgameView === name));
    viewPanels.forEach(panel => { panel.hidden = panel.dataset.endgameViewPanel !== name; });
  };
  viewTabs.forEach(tab => tab.addEventListener("click", () => {
    const name = tab.dataset.endgameView;
    activateView(name);
    if (name === "dkp-loot") activate("bidding-live");
    else if (name === "bank") history.replaceState(null, "", "#bank");
    else if (name === "operations") activate("events");
    else history.replaceState(null, "", "#calendar");
  }));
  const activate = name => {
    tabs.forEach(tab => tab.classList.toggle("active", tab.dataset.endgameTab === name));
    panels.forEach(panel => { const active = panel.dataset.endgamePanel === name; panel.hidden = !active; panel.classList.toggle("active", active); });
    history.replaceState(null, "", `#${name}`);
  };
  tabs.forEach(tab => tab.addEventListener("click", () => activate(tab.dataset.endgameTab)));
  const requested = location.hash.slice(1);
  if (["bidding-live", "jobs", "priority", "loot", "dynamis", "dynamis-payout"].includes(requested) || requested.startsWith("auction-")) { activateView("dkp-loot"); activate(requested.startsWith("auction-") ? "bidding-live" : requested); }
  else if (requested === "bank") activateView("bank");
  else if (["events", "pops", "admin-audit"].includes(requested)) { activateView("operations"); activate(requested); }
  else activateView("calendar");
  const payoutAttendanceForm = document.querySelector("#payout-attendance-form");
  const payoutAddForm = document.querySelector("[data-payout-async='add']");
  const submitPayoutForm = async form => {
    const response = await fetch(form.action, {method: "POST", body: new FormData(form), headers: {Accept: "application/json"}});
    if (!response.ok) throw new Error("Unable to save payout attendance.");
    return response.json();
  };
  payoutAttendanceForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const submitter = event.submitter;
    if (submitter?.name) submitter.disabled = true;
    try {
      const payload = await submitPayoutForm(payoutAttendanceForm);
      if (payload.removed_member_id) document.querySelector(`#payout-attendance-form tr [name='attended_${payload.removed_member_id}']`)?.closest("tr")?.remove();
    } catch (error) { alert(error.message); }
    finally { if (submitter?.name) submitter.disabled = false; }
  });
  payoutAddForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const selected = payoutAddForm.querySelector("select[name='member_id']");
    const label = selected?.selectedOptions[0]?.textContent.trim() || "Member";
    try {
      const payload = await submitPayoutForm(payoutAddForm);
      const tbody = document.querySelector(".dynamis-payout-attendance-table tbody");
      if (tbody && !tbody.querySelector(`[name='attended_${payload.member_id}']`)) {
        const action = payoutAttendanceForm.action;
        tbody.insertAdjacentHTML("beforeend", `<tr><td><b>${safeText(label)}</b><small>Manually added</small></td><td><input type="checkbox" name="attended_${payload.member_id}" value="1" checked></td><td><input type="checkbox" name="entry_paid_${payload.member_id}" value="1"></td><td><input type="checkbox" name="payout_paid_${payload.member_id}" value="1"></td><td><button class="button danger" name="remove_member_id" value="${payload.member_id}">Remove</button></td></tr>`);
      }
      selected.value = "";
    } catch (error) { alert(error.message); }
  });
  const dynamisJobFilter = document.querySelector("#dynamis-job-filter");
  const dynamisZoneFilter = document.querySelector("#dynamis-zone-filter");
  const dynamisCatalogZoneFilter = document.querySelector("#dynamis-catalog-zone-filter");
  const dynamisCatalogJobFilter = document.querySelector("#dynamis-catalog-job-filter");
  const dynamisPriorityResults = document.querySelector("#dynamis-priority-results");
  const dynamisPrioritySelection = document.querySelector("#dynamis-priority-selection");
  const refreshDynamisLots = () => {
    const job = dynamisJobFilter?.value || "";
    const matches = [...document.querySelectorAll(".dynamis-legacy-layout #dynamis-lot-body tr")]
      .map(row => ({
        name: row.cells[0]?.textContent.trim() || "",
        main: row.cells[1]?.textContent.trim() || "",
        secondary: row.cells[2]?.textContent.trim() || "",
        levels: [...(row.cells[3]?.querySelectorAll(".dynamis-eligible-job") || [])].map(entry => entry.textContent.trim()),
      }))
      .filter(row => job && (row.main === job || row.secondary === job));
    if (dynamisPriorityResults) dynamisPriorityResults.innerHTML = job
      ? (matches.length ? matches.map(row => `<article><b>${row.name}</b><span class="main">Priority · ${job} ${row.levels.find(level => level.startsWith(job))?.replace(job, "") || ""}</span></article>`).join("") : `<p>No registered priority lotters for ${job}.</p>`)
      : "<p>Choose a drop job to show its lot priority.</p>";
    const zone = dynamisCatalogZoneFilter ? dynamisCatalogZoneFilter.value : (dynamisZoneFilter?.value || "");
    const catalogJob = dynamisCatalogJobFilter?.value || "";
    document.querySelectorAll(".dynamis-lot-panel:not(.dynamis-legacy-layout) #dynamis-drop-list article").forEach(card => {
      card.hidden = Boolean((zone && card.dataset.dynamisDropArea !== zone) || (catalogJob && card.dataset.dynamisDropJob !== catalogJob));
    });
  };
  dynamisJobFilter?.addEventListener("change", refreshDynamisLots);
  dynamisZoneFilter?.addEventListener("change", () => {
    if (dynamisCatalogZoneFilter) dynamisCatalogZoneFilter.value = dynamisZoneFilter.value;
    refreshDynamisLots();
  });
  dynamisCatalogZoneFilter?.addEventListener("change", () => {
    if (dynamisZoneFilter) dynamisZoneFilter.value = dynamisCatalogZoneFilter.value;
    refreshDynamisLots();
  });
  dynamisCatalogJobFilter?.addEventListener("change", refreshDynamisLots);
  const selectDynamisCatalogItem = card => {
    const area = card.dataset.dynamisDropArea || "";
    const job = card.dataset.dynamisDropJob || "";
    const item = card.querySelector("b")?.textContent.trim() || "Selected item";
    if (dynamisCatalogZoneFilter) dynamisCatalogZoneFilter.value = area;
    if (dynamisZoneFilter) dynamisZoneFilter.value = area;
    if (dynamisJobFilter) dynamisJobFilter.value = job;
    document.querySelectorAll(".dynamis-lot-panel:not(.dynamis-legacy-layout) #dynamis-drop-list article").forEach(entry => {
      const selected = entry === card;
      entry.classList.toggle("selected", selected);
      entry.setAttribute("aria-pressed", String(selected));
    });
    if (dynamisPrioritySelection) dynamisPrioritySelection.textContent = `${item} · ${area} · ${job}`;
    refreshDynamisLots();
    dynamisPriorityResults?.scrollIntoView({behavior: "smooth", block: "nearest"});
  };
  document.querySelectorAll(".dynamis-lot-panel:not(.dynamis-legacy-layout) #dynamis-drop-list article").forEach(card => {
    card.addEventListener("click", () => selectDynamisCatalogItem(card));
    card.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectDynamisCatalogItem(card);
      }
    });
  });
  refreshDynamisLots();
  document.querySelectorAll(".dynamis-member-directory table").forEach(table => {
    const header = table.querySelector("th:nth-child(2)");
    if (header) header.textContent = "Main lot";
    table.querySelectorAll("th:nth-child(3), td:nth-child(3)").forEach(cell => { cell.hidden = false; });
    table.querySelectorAll("tbody tr").forEach(row => {
      const priority = row.cells[1];
      const job = priority?.textContent.trim();
      const level = [...(row.cells[3]?.querySelectorAll(".dynamis-eligible-job") || [])]
        .find(entry => entry.textContent.trim().startsWith(job))?.querySelector("small")?.textContent;
      if (priority && job && job !== "—" && level) priority.insertAdjacentHTML("beforeend", ` <small>${level}</small>`);
    });
  });
  document.querySelectorAll("[data-dynamis-cooldown]").forEach(node => {
    const endsAt = node.dataset.dynamisCooldown;
    const refresh = () => {
      const remaining = Math.max(0, Date.parse(endsAt) - Date.now());
      if (!remaining) { node.textContent = "Ready to request a job change."; return; }
      const days = Math.floor(remaining / 86400000);
      const hours = Math.floor((remaining % 86400000) / 3600000);
      node.textContent = `30-day lock: ${days}d ${hours}h remaining`;
    };
    refresh();
    setInterval(refresh, 60000);
  });
  const guildDateInput = document.querySelector('.event-create-form .native-date-input');
  const guildDateDisplay = document.querySelector('#guild-event-date-display');
  const guildDateButton = document.querySelector('#pick-guild-event-date');
  if (guildDateInput && guildDateButton) {
    guildDateButton.addEventListener('click', () => window.openQuarterHourPicker(guildDateInput));
    guildDateInput.addEventListener('change', () => {
      if (guildDateInput.value) {
        const [date, time] = guildDateInput.value.split('T');
        const [hour, minute] = time.split(':').map(Number);
        const rounded = Math.min(1425, Math.round((hour * 60 + minute) / 15) * 15);
        guildDateInput.value = `${date}T${String(Math.floor(rounded / 60)).padStart(2, '0')}:${String(rounded % 60).padStart(2, '0')}`;
      }
      guildDateDisplay.textContent = guildDateInput.value ? guildDateInput.value.replace('T', ' at ') : 'Choose date and time';
    });
  }

  const roster = window.ENDGAME_ROSTER || [];
  const dynamisSelections = new Map(roster.map(member => [String(member.name || "").toLowerCase(), {
    main: member.dynamis_main || "",
    secondary: member.dynamis_secondary || "",
  }]));
  document.querySelectorAll("#endgame-roster-body tr").forEach(row => {
    const selection = dynamisSelections.get(row.dataset.name) || {main: "", secondary: ""};
    row.dataset.dynamis = `${selection.main} ${selection.secondary}`.toLowerCase();
    row.children[0]?.insertAdjacentHTML("afterend", `<td><span class="job-badge main">${selection.main || "—"}</span> <span class="job-badge">${selection.secondary || "—"}</span></td>`);
  });
  const loot = window.ENDGAME_LOOT || [];
  const priorityItems = window.ENDGAME_PRIORITY_ITEMS || [];
  const jobs = window.ENDGAME_JOBS || [];
  const jobChangeKey = "hokuten-job-change-log";
  const jobChanges = JSON.parse(localStorage.getItem(jobChangeKey) || "[]");
  const adminAuditKey = "hokuten-admin-audit";
  const adminAudit = [...(window.ENDGAME_SERVER_AUDIT || []), ...JSON.parse(localStorage.getItem(adminAuditKey) || "[]")];
  let auditSort = {key: "at", direction: -1};
  const safeText = value => String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character]));
  const memberDetailsByName = new Map(Object.values(window.ENDGAME_MEMBER_DETAILS || {}).map(member => [String(member.name || "").toLowerCase(), member]));
  document.querySelectorAll("#endgame-roster-body tr").forEach(row => {
    const member = memberDetailsByName.get(row.dataset.name);
    if (!member) return;
    const cells = row.children;
    if (cells[3]) cells[3].innerHTML = `<button class="table-dkp-breakdown-trigger" type="button" data-dkp-member="${member.id}" data-dkp-kind="spent" aria-label="Show ${safeText(member.name)} total spent details">${Number(member.total_spent || 0)}</button>`;
    if (cells[4]) cells[4].innerHTML = `<button class="table-dkp-breakdown-trigger" type="button" data-dkp-member="${member.id}" data-dkp-kind="earned" aria-label="Show ${safeText(member.name)} lifetime earned details">${Number(member.lifetime_earned || 0)}</button>`;
  });
  const tableDkpPopover = document.createElement("div");
  tableDkpPopover.className = "table-dkp-breakdown-popover";
  tableDkpPopover.setAttribute("role", "tooltip");
  document.body.appendChild(tableDkpPopover);
  let pinnedDkpTrigger = null;
  const closeTableDkpBreakdown = () => {
    pinnedDkpTrigger?.setAttribute("aria-expanded", "false");
    pinnedDkpTrigger = null;
    tableDkpPopover.classList.remove("visible", "pinned");
  };
  const showTableDkpBreakdown = trigger => {
    const member = (window.ENDGAME_MEMBER_DETAILS || {})[trigger.dataset.dkpMember];
    if (!member) return;
    const spent = trigger.dataset.dkpKind === "spent";
    const records = spent ? member.loot : (member.earned_events || []);
    const rows = records.map(row => spent
      ? `<tr><td><b>${safeText(row.item)}</b><small>${safeText(row.event_name)}</small></td><td>${Number(row.dkp_cost || 0)} DKP</td></tr>`
      : `<tr><td>${safeText(row.date)}<small>${safeText(row.name)}</small></td><td>${Number(row.dkp || 0)} DKP</td></tr>`).join("");
    tableDkpPopover.innerHTML = `<strong>${spent ? "Items purchased" : "Events attended"}</strong>${rows ? `<div><table><tbody>${rows}</tbody></table></div>` : `<p>${spent ? "No DKP purchases recorded." : "No earned DKP recorded."}</p>`}`;
    tableDkpPopover.classList.add("visible");
    const rect = trigger.getBoundingClientRect();
    const width = tableDkpPopover.offsetWidth;
    const left = Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 12));
    tableDkpPopover.style.left = `${left}px`;
    tableDkpPopover.style.top = `${Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - tableDkpPopover.offsetHeight - 12))}px`;
  };
  document.addEventListener("mouseover", event => {
    const trigger = event.target.closest(".table-dkp-breakdown-trigger");
    if (trigger && (!pinnedDkpTrigger || pinnedDkpTrigger === trigger)) showTableDkpBreakdown(trigger);
  });
  document.addEventListener("mouseout", event => {
    if (pinnedDkpTrigger || tableDkpPopover.contains(event.relatedTarget)) return;
    if (event.target.closest(".table-dkp-breakdown-trigger")) tableDkpPopover.classList.remove("visible");
  });
  document.addEventListener("focusin", event => {
    const trigger = event.target.closest(".table-dkp-breakdown-trigger");
    if (trigger && (!pinnedDkpTrigger || pinnedDkpTrigger === trigger)) showTableDkpBreakdown(trigger);
  });
  document.addEventListener("focusout", event => {
    if (!pinnedDkpTrigger && event.target.closest(".table-dkp-breakdown-trigger")) tableDkpPopover.classList.remove("visible");
  });
  document.addEventListener("click", event => {
    const trigger = event.target.closest(".table-dkp-breakdown-trigger");
    if (trigger) {
      event.stopPropagation();
      if (pinnedDkpTrigger === trigger) {
        closeTableDkpBreakdown();
      } else {
        closeTableDkpBreakdown();
        pinnedDkpTrigger = trigger;
        trigger.setAttribute("aria-expanded", "true");
        showTableDkpBreakdown(trigger);
        tableDkpPopover.classList.add("pinned");
      }
      return;
    }
    if (!tableDkpPopover.contains(event.target)) closeTableDkpBreakdown();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && pinnedDkpTrigger) {
      closeTableDkpBreakdown();
    }
  });
  if (window.ENDGAME_IS_ADMIN) {
    const dynamisDirectory = document.querySelector(".dynamis-member-directory");
    const dynamisMembers = Object.values(window.ENDGAME_MEMBER_DETAILS || {})
      .filter(member => Object.keys(member.dynamis_eligible_jobs || {}).length || Object.values(member.job_levels || {}).some(level => Number(level) >= 71))
      .sort((left, right) => left.name.localeCompare(right.name));
    if (dynamisDirectory && dynamisMembers.length) {
      const dynamisOptions = (member, selected) => [`<option value="">Unassigned</option>`, ...Object.entries(Object.keys(member.dynamis_eligible_jobs || {}).length ? member.dynamis_eligible_jobs : (member.job_levels || {}))
        .filter(([, level]) => Number(level) >= 71).sort(([left], [right]) => left.localeCompare(right))
        .map(([job, level]) => `<option value="${safeText(job)}"${job === selected ? " selected" : ""}>${safeText(job)} · Lv.${Number(level)}</option>`)].join("");
      const editor = document.createElement("details");
      editor.className = "officer-dynamis-registration-editor";
      editor.innerHTML = `<summary><span>Officer lotting-job editor</span><small>Set one or two eligible jobs directly</small></summary><div>${dynamisMembers.map(member => `<form method="post" action="/endgame/dynamis-lot-registrations/${Number(member.id)}"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF || "")}"><b>${safeText(member.name)}</b><label>Main lot<select name="main_job">${dynamisOptions(member, member.dynamis_main)}</select></label><label>Secondary lot<select name="secondary_job">${dynamisOptions(member, member.dynamis_secondary)}</select></label><button class="button primary" type="submit">Save</button></form>`).join("")}</div>`;
      dynamisDirectory.append(editor);
    }
  }
  const bankSearch = document.querySelector("#ls-bank-search");
  const bankHolderFilter = document.querySelector("#ls-bank-holder-filter");
  const bankStatusFilter = document.querySelector("#ls-bank-status-filter");
  const filterBankRows = () => {
    const query = bankSearch?.value.trim().toLowerCase() || "";
    const holder = bankHolderFilter?.value || "";
    const status = bankStatusFilter?.value || "";
    let visible = 0;
    document.querySelectorAll("#ls-bank-body tr[data-bank-search]").forEach(row => {
      const matches = (!query || row.dataset.bankSearch.includes(query)) && (!holder || row.dataset.holder === holder) && (!status || row.dataset.status === status);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    const count = document.querySelector("#bank-filter-count");
    if (count) count.textContent = `${visible} matching / ${document.querySelectorAll("#ls-bank-body tr[data-bank-search]").length} entries`;
  };
  [bankSearch, bankHolderFilter, bankStatusFilter].filter(Boolean).forEach(control => {
    ["input", "change"].forEach(eventName => control.addEventListener(eventName, filterBankRows));
  });
  const bankMarketKey = value => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const formatBankGil = value => `${Math.max(0, Math.round(Number(value) || 0)).toLocaleString()}g`;
  const bankItemInput = document.querySelector("#ls-bank-item");
  const bankItemCatalog = document.querySelector("#ls-bank-item-catalog");
  const bankSource = document.querySelector("#ls-bank-source");
  const bankNewStatus = document.querySelector("#ls-bank-new-status");
  const visibleBankSources = ["Event Drop", "Auction House", "Bazaar", "Donation", "Other", "Mercenary"];
  if (bankSource) {
    const selectedSource = visibleBankSources.includes(bankSource.value) ? bankSource.value : "Event Drop";
    bankSource.replaceChildren(...visibleBankSources.map(value => new Option(value, value, false, value === selectedSource)));
  }
  if (bankNewStatus) {
    const heldOption = [...bankNewStatus.options].find(option => option.value === "Held");
    if (heldOption) { heldOption.textContent = "Drop"; heldOption.value = "Held"; }
    bankNewStatus.closest("label")?.setAttribute("hidden", "");
  }
  const bankAddHolder = bankSource?.form?.querySelector("select[name='holder_member_id']");
  if (bankAddHolder && !bankSource.form?.querySelector("select[name='purchaser_member_id']")) {
    const purchaserLabel = document.createElement("label");
    purchaserLabel.textContent = "Purchased by";
    const purchaser = document.createElement("select");
    purchaser.name = "purchaser_member_id";
    purchaser.setAttribute("aria-label", "Officer who paid for the item");
    purchaser.add(new Option("Same as held by", ""));
    [...bankAddHolder.options].filter(option => option.value).forEach(option => purchaser.add(new Option(option.textContent, option.value)));
    purchaserLabel.append(purchaser);
    bankAddHolder.closest("label")?.after(purchaserLabel);
  }
  bankSource?.addEventListener("change", () => {
    if (bankNewStatus) bankNewStatus.value = "Held";
    const purchaseInput = bankSource.form?.querySelector("input[name='purchase_gil']");
    const purchaseLabel = purchaseInput?.closest("label");
    const labelText = purchaseLabel?.childNodes?.[0];
    if (labelText) labelText.nodeValue = bankSource.value === "Mercenary" ? "Gil received" : "Purchase gil";
    if (purchaseInput) purchaseInput.placeholder = bankSource.value === "Mercenary" ? "Gil received" : "0";
  });
  document.querySelectorAll(".ls-bank-row-editor select[name='status']").forEach(select => {
    if (![...select.options].some(option => option.value === "Purchased")) select.add(new Option("Purchased", "Purchased"));
    const savedStatus = select.closest("tr")?.dataset.status;
    if (savedStatus) select.value = savedStatus[0].toUpperCase() + savedStatus.slice(1);
  });
  const bankEventOptions = bankSource?.form?.querySelector("select[name='event_id']");
  const sourceForRow = row => [...(bankSource?.options || [])]
    .map(option => option.value).filter(Boolean).sort((a, b) => b.length - a.length)
    .find(value => (row.dataset.source || "").startsWith(value.toLowerCase())) || "Manual";
  const showBankSaveMessage = message => {
    let notice = document.querySelector("#ls-bank-save-notice");
    if (!notice) {
      notice = document.createElement("div");
      notice.id = "ls-bank-save-notice";
      notice.className = "ls-bank-save-notice";
      document.querySelector(".ls-bank-panel")?.prepend(notice);
    }
    notice.textContent = message;
    notice.hidden = false;
    clearTimeout(showBankSaveMessage.timer);
    showBankSaveMessage.timer = setTimeout(() => { notice.hidden = true; }, 3500);
  };
  document.querySelectorAll(".ls-bank-row-editor").forEach(form => {
    const row = form.closest("tr");
    form.id ||= `ls-bank-editor-${form.action.match(/\/bank\/(\d+)\/update/)?.[1] || Math.random().toString(36).slice(2)}`;
    const statusSelect = form.elements.status;
    const status = statusSelect?.value || "Held";
    const source = document.createElement("select");
    source.name = "acquisition_kind";
    source.setAttribute("aria-label", "Source");
    [...(bankSource?.options || [])].forEach(option => source.add(new Option(option.textContent, option.value, false, option.value === sourceForRow(row))));
    const event = document.createElement("select");
    event.name = "event_id";
    event.setAttribute("aria-label", "Source event");
    [...(bankEventOptions?.options || [])].forEach(option => event.add(new Option(option.textContent, option.value)));
    const eventText = row.cells[1]?.querySelector("small")?.textContent.trim() || "";
    row.dataset.bankSourceLabel = row.cells[1]?.childNodes[0]?.textContent.trim() || row.dataset.source || "";
    row.dataset.bankEventLabel = eventText;
    const matchingEvent = [...event.options].find(option => eventText && option.textContent.includes(eventText));
    if (matchingEvent) event.value = matchingEvent.value;
    const purchase = form.elements.sale_gil;
    purchase.name = "purchase_gil";
    purchase.value = row.dataset.purchase || "0";
    purchase.placeholder = ["Merc Sell", "Mercenary"].includes(source.value) ? "Gil received" : "Purchase gil";
    purchase.setAttribute("aria-label", ["Merc Sell", "Mercenary"].includes(source.value) ? "Gil received" : "Purchase gil");
    const purchaser = form.elements.holder_member_id.cloneNode(true);
    purchaser.name = "purchaser_member_id";
    purchaser.setAttribute("aria-label", "Purchased by");
    const statusHidden = document.createElement("input");
    statusHidden.type = "hidden";
    statusHidden.name = "status";
    statusHidden.value = status;
    const inlineSave = document.createElement("button");
    inlineSave.type = "submit";
    inlineSave.className = "bank-inline-save";
    inlineSave.hidden = true;
    inlineSave.tabIndex = -1;
    statusSelect.remove();
    form.elements.sale_channel?.remove();
    form.insertBefore(statusHidden, purchase);
    form.append(inlineSave);
    source.addEventListener("change", () => {
      if (statusHidden.value !== "Sold") statusHidden.value = "Held";
      purchase.placeholder = ["Merc Sell", "Mercenary"].includes(source.value) ? "Gil received" : "Purchase gil";
      row.dataset.source = source.value.toLowerCase();
      row.dataset.bankSourceLabel = source.value;
      const action = form.querySelector(".bank-mark-sold");
      if (action) action.textContent = source.value === "Mercenary" ? "Record gil" : "Mark Sold";
      if (source.value === "Mercenary") {
        purchaseEditor.classList.add("open");
        purchase.focus();
      }
    });
    const addInlineEditor = (cell, controls) => {
      const editor = document.createElement("span");
      editor.className = "bank-inline-editor";
      controls.forEach(control => { control.setAttribute("form", form.id); editor.append(control); });
      const save = document.createElement("button");
      save.type = "submit";
      save.className = "bank-inline-save-control";
      save.textContent = "Save";
      save.setAttribute("form", form.id);
      editor.append(save);
      cell.append(editor);
      cell.classList.add("bank-editable-cell");
      cell.title = "Click to edit";
      cell.addEventListener("click", click => {
        if (click.target.closest("select,input,button")) return;
        document.querySelectorAll(".bank-inline-editor.open").forEach(open => {
          if (open !== editor) open.classList.remove("open");
        });
        editor.classList.toggle("open");
      });
      controls.forEach(control => {
        control.addEventListener("input", () => { form.dataset.bankDirty = "true"; });
        control.addEventListener("change", () => { form.dataset.bankDirty = "true"; });
      });
      cell.addEventListener("focusout", () => setTimeout(() => {
        if (form.dataset.bankDirty !== "true" || cell.contains(document.activeElement)) return;
        form.dataset.bankDirty = "";
        form.requestSubmit(inlineSave);
      }, 120));
      return editor;
    };
    addInlineEditor(row.cells[1], [source, event]);
    const holderLabel = document.createElement("label");
    holderLabel.className = "bank-inline-field-label";
    holderLabel.textContent = "Held by";
    form.elements.holder_member_id.setAttribute("form", form.id);
    holderLabel.append(form.elements.holder_member_id);
    const purchaserLabel = document.createElement("label");
    purchaserLabel.className = "bank-inline-field-label";
    purchaserLabel.textContent = "Purchased by";
    purchaser.setAttribute("form", form.id);
    purchaserLabel.append(purchaser);
    addInlineEditor(row.cells[2], [holderLabel, purchaserLabel]);
    const purchaseEditor = addInlineEditor(row.cells[3], [purchase]);
    const isUsed = /\bUsed:/.test(row.cells[0]?.textContent || "");
    const heldInventory = ["held", "purchased"].includes(row.dataset.status) && !isUsed;
    if (heldInventory) {
      const badge = row.querySelector(".bank-status");
      const kind = document.createElement("select");
      kind.className = "bank-held-kind";
      kind.setAttribute("aria-label", "Held item classification");
      kind.add(new Option("Held (Dropped)", "dropped"));
      kind.add(new Option("Held (Purchased)", "purchased"));
      const saveKind = document.createElement("button");
      saveKind.type = "submit";
      saveKind.className = "bank-inline-save-control";
      saveKind.textContent = "Save";
      saveKind.setAttribute("form", form.id);
      const isPurchased = !/^(event drop|donation)/.test(source.value || "");
      kind.value = isPurchased ? "purchased" : "dropped";
      const applyHeldKind = () => {
        const purchased = kind.value === "purchased";
        source.value = purchased ? "Auction House" : "Event Drop";
        if (!purchased) purchase.value = "0";
        source.dispatchEvent(new Event("change"));
        statusHidden.value = "Held";
        if (badge) {
          badge.textContent = purchased ? "Held (Purchased)" : "Held (Dropped)";
          badge.classList.toggle("purchased", purchased);
          badge.classList.toggle("dropped", !purchased);
        }
        if (purchased) {
          purchaseEditor.classList.add("open");
          purchase.focus();
        }
      };
      kind.addEventListener("change", applyHeldKind);
      if (badge) {
        badge.classList.add("bank-status-editable");
        badge.title = "Click to change between dropped and purchased";
        badge.addEventListener("click", event => {
          event.stopPropagation();
          kind.hidden = false;
          saveKind.hidden = false;
          badge.hidden = true;
          kind.focus();
        });
        kind.addEventListener("blur", blurEvent => {
          if (blurEvent.relatedTarget === saveKind) return;
          kind.hidden = true;
          saveKind.hidden = true;
          badge.hidden = false;
          if (kind.value === "dropped" && form.dataset.bankDirty === "true") {
            form.dataset.bankDirty = "";
            form.requestSubmit(inlineSave);
          }
        });
        kind.hidden = true;
        saveKind.hidden = true;
        row.cells[5].insertBefore(kind, badge.nextSibling);
        row.cells[5].insertBefore(saveKind, kind.nextSibling);
      }
    }
    let saleInput;
    const canMarkSold = heldInventory;
    if (canMarkSold) {
      const sale = document.createElement("input");
      sale.type = "number";
      sale.name = "sale_gil";
      sale.min = "0";
      sale.max = "2000000000";
      sale.placeholder = "Sale gil";
      sale.setAttribute("aria-label", "Sale gil; Save all marks this item sold");
      sale.setAttribute("form", form.id);
      sale.className = "bank-sale-gil";
      row.cells[5].append(sale);
      saleInput = sale;
      const usedFor = document.createElement("select");
      usedFor.name = "used_event_id";
      usedFor.setAttribute("aria-label", "Event item was used for");
      usedFor.add(new Option("Used for event", ""));
      [...(bankEventOptions?.options || [])].filter(option => option.value).forEach(option => usedFor.add(new Option(option.textContent, option.value)));
      usedFor.add(new Option("Other", "other"));
      const confirmUse = document.createElement("button");
      confirmUse.type = "submit";
      confirmUse.className = "bank-confirm-used";
      confirmUse.textContent = "Confirm";
      confirmUse.formAction = form.action.replace(/\/update$/, "/use");
      confirmUse.addEventListener("click", event => {
        if (!usedFor.value) { event.preventDefault(); alert("Choose the event this item was used for, or select Other."); }
      });
      usedFor.addEventListener("change", () => { confirmUse.hidden = !usedFor.value; });
      confirmUse.hidden = true;
      form.append(usedFor, confirmUse);
    }
    const enableSoldSaleEdit = saleText => {
      saleText.classList.add("bank-sale-editable");
      saleText.title = "Click to edit sale value";
      saleText.addEventListener("click", () => {
        if (row.cells[5].querySelector("input[name='sale_gil']")) return;
        const sale = document.createElement("input");
        sale.type = "number";
        sale.name = "sale_gil";
        sale.min = "0";
        sale.max = "2000000000";
        sale.value = (saleText.textContent.match(/[\d,]+g/)?.[0] || "0").replace(/[^\d]/g, "");
        sale.setAttribute("aria-label", "Sold gil");
        sale.setAttribute("form", form.id);
        sale.className = "bank-sale-gil";
        const saveSale = document.createElement("button");
        saveSale.type = "submit";
        saveSale.textContent = "Save";
        saveSale.className = "bank-save-sale";
        saveSale.setAttribute("form", form.id);
        saleText.hidden = true;
        row.cells[5].append(sale, saveSale);
        sale.focus();
      });
    };
    if (row.dataset.status === "sold") {
      const saleText = [...row.cells[5].querySelectorAll("small")].find(node => /[\d,]+g/.test(node.textContent));
      if (saleText) enableSoldSaleEdit(saleText);
      const reopen = document.createElement("button");
      reopen.type = "submit";
      reopen.className = "bank-reopen-sale";
      reopen.textContent = "Reopen";
      reopen.formAction = form.action.replace(/\/update$/, "/reopen");
      reopen.title = "Return to held inventory and clear the sale value";
      form.append(reopen);
    }
    const saveButton = [...form.querySelectorAll("button[type='submit']")].find(button => button.textContent.trim() === "Save");
    if (canMarkSold && saveButton) {
      saveButton.classList.add("bank-mark-sold");
      saveButton.textContent = "Mark Sold";
      saveButton.addEventListener("click", event => {
        const mercenaryIncome = source.value === "Mercenary";
        if (!mercenaryIncome && !Number(saleInput?.value || 0)) {
          event.preventDefault();
          alert("Enter the sale gil amount before marking this item sold.");
          saleInput?.focus();
          return;
        }
        if (mercenaryIncome && !Number(purchase.value || 0)) {
          event.preventDefault();
          alert("Enter the gil received before recording a mercenary payment.");
          purchaseEditor.classList.add("open");
          purchase.focus();
          return;
        }
        statusHidden.value = "Sold";
      });
    } else if (row.dataset.status === "sold" && saveButton) {
      saveButton.remove();
    }
    const setLeadingText = (cell, text) => {
      const node = [...cell.childNodes].find(child => child.nodeType === Node.TEXT_NODE);
      if (node) node.nodeValue = text;
      else cell.prepend(document.createTextNode(text));
    };
    const renderSold = saleGil => {
      row.dataset.status = "sold";
      statusHidden.value = "Sold";
      const badge = row.querySelector(".bank-status");
      if (badge) { badge.hidden = false; badge.textContent = "Sold"; badge.className = "bank-status sold"; }
      row.cells[5].querySelectorAll(".bank-sale-gil,.bank-held-kind,.bank-sale-editable,.bank-save-sale").forEach(node => node.remove());
      const saleText = document.createElement("small");
      saleText.textContent = formatBankGil(saleGil);
      row.cells[5].append(saleText);
      enableSoldSaleEdit(saleText);
      form.querySelectorAll(".bank-item-used,.bank-confirm-used,select[name='used_event_id'],button[type='submit']").forEach(button => {
        if (button.textContent.trim() !== "Remove") button.remove();
      });
      if (!form.querySelector(".bank-reopen-sale")) {
        const reopen = document.createElement("button");
        reopen.type = "submit";
        reopen.className = "bank-reopen-sale";
        reopen.textContent = "Reopen";
        reopen.formAction = form.action.replace(/\/update$/, "/reopen");
        form.append(reopen);
      }
    };
    form.addEventListener("submit", submitEvent => {
      const submitter = submitEvent.submitter;
      if (!submitter || submitter.dataset.bankAsync === "false") return;
      submitEvent.preventDefault();
      // formAction on an externally-associated button can resolve to the
      // current page even without a formaction attribute.  Only honor an
      // explicit override; ordinary cell saves must use this row's update URL.
      const endpoint = submitter.getAttribute("formaction") || form.action;
      const isDelete = /\/delete$/.test(endpoint);
      if (isDelete && !confirm("Remove this LS Bank entry?")) return;
      if (source.value === "Mercenary" && !Number(purchase.value || 0)) {
        alert("Enter the Gil received amount before recording a Mercenary payment.");
        purchaseEditor.classList.add("open");
        purchase.focus();
        return;
      }
      submitter.disabled = true;
      fetch(endpoint, {method: "POST", headers: {"Accept": "application/json"}, body: new FormData(form)})
        .then(async response => {
          const payload = await response.json().catch(() => ({}));
          if (!response.ok || !payload.ok) throw new Error(payload.message || "Unable to save the LS Bank item.");
          return payload;
        })
        .then(payload => {
          if (payload.deleted) { row.remove(); showBankSaveMessage(payload.message); return; }
          if (payload.status === "Sold") renderSold(payload.sale_gil);
          else if (payload.status === "Used") {
            row.dataset.status = "purchased";
            const badge = row.querySelector(".bank-status");
            if (badge) { badge.textContent = "Used"; badge.className = "bank-status used"; }
            row.cells[5].querySelectorAll(".bank-sale-gil,.bank-held-kind").forEach(node => node.remove());
            form.querySelectorAll(".bank-item-used,.bank-confirm-used,select[name='used_event_id']").forEach(node => node.remove());
          } else if (payload.status === "Held") {
            row.dataset.status = "held";
            statusHidden.value = "Held";
            row.cells[5].querySelector("small")?.remove();
            const badge = row.querySelector(".bank-status");
            if (badge) { badge.textContent = !/^(event drop|donation)/.test(source.value) ? "Held (Purchased)" : "Held (Dropped)"; badge.className = "bank-status held"; }
          }
          setLeadingText(row.cells[1], source.value);
          setLeadingText(row.cells[2], form.elements.holder_member_id.selectedOptions[0]?.textContent || "Unassigned");
          const savedPurchase = payload.purchase_gil ?? form.elements.purchase_gil.value;
          setLeadingText(row.cells[3], formatBankGil(savedPurchase));
          row.dataset.purchase = String(savedPurchase || "0");
          row.querySelectorAll(".bank-inline-editor.open").forEach(editor => editor.classList.remove("open"));
          const openKind = row.querySelector(".bank-held-kind:not([hidden])");
          if (openKind) {
            openKind.hidden = true;
            openKind.nextElementSibling.hidden = true;
            row.querySelector(".bank-status")?.removeAttribute("hidden");
          }
          showBankSaveMessage(payload.message);
          refreshBankBalance();
        })
        .catch(error => alert(error.message))
        .finally(() => { submitter.disabled = false; });
    });
  });
  let bankCanonicalItemNames = new Map();
  let bankCatalogNames = [];
  const showBankItemSuggestions = () => {
    if (!bankItemInput || !bankItemCatalog) return;
    const query = bankMarketKey(bankItemInput.value);
    const matches = query.length >= 2 ? bankCatalogNames.filter(name => bankMarketKey(name).includes(query)).slice(0, 12) : [];
    bankItemCatalog.replaceChildren(...matches.map(name => {
      const option = document.createElement("button");
      option.type = "button";
      option.setAttribute("role", "option");
      option.textContent = name;
      option.addEventListener("mousedown", event => {
        event.preventDefault();
        bankItemInput.value = name;
        bankItemCatalog.hidden = true;
        bankItemInput.setAttribute("aria-expanded", "false");
      });
      return option;
    }));
    bankItemCatalog.hidden = matches.length === 0;
    bankItemInput.setAttribute("aria-expanded", String(matches.length > 0));
  };
  const updateBankItemCatalog = prices => {
    if (!bankItemCatalog) return;
    bankCatalogNames = [...new Set(Object.values(prices || {}).map(price => String(price?.name || "").trim()).filter(Boolean))]
      .sort((left, right) => left.localeCompare(right));
    bankCanonicalItemNames = new Map(bankCatalogNames.map(name => [bankMarketKey(name), name]));
    showBankItemSuggestions();
  };
  bankItemInput?.addEventListener("input", showBankItemSuggestions);
  bankItemInput?.addEventListener("focus", showBankItemSuggestions);
  bankItemInput?.addEventListener("blur", () => setTimeout(() => {
    if (bankItemCatalog) bankItemCatalog.hidden = true;
    bankItemInput?.setAttribute("aria-expanded", "false");
  }, 120));
  bankItemInput?.form?.addEventListener("submit", () => {
    const canonical = bankCanonicalItemNames.get(bankMarketKey(bankItemInput.value));
    if (canonical) bankItemInput.value = canonical;
  });
  let bankLatestMarketPrices = {};
  const refreshBankBalance = () => {
    let cash = 0;
    document.querySelectorAll("#ls-bank-body tr[data-bank-search]").forEach(row => {
      const source = row.dataset.source || "";
      const purchased = !/^(event drop|donation)/.test(source);
      if (purchased) cash -= Number(row.dataset.purchase || 0);
      if (row.dataset.status === "sold") {
        const sale = row.cells[5]?.textContent.match(/[\d,]+g/)?.[0] || "0";
        cash += Number(sale.replace(/[^\d]/g, ""));
      }
    });
    const summary = document.querySelector(".ls-bank-summary");
    if (summary) summary.dataset.bankCash = String(cash);
    const balance = document.querySelector("#bank-cash-balance");
    if (balance) balance.textContent = formatBankGil(cash);
    updateBankMarketValues(bankLatestMarketPrices);
  };
  const updateBankMarketValues = prices => {
    bankLatestMarketPrices = prices || bankLatestMarketPrices;
    const byName = Object.fromEntries(Object.values(prices || {}).filter(price => price.name).map(price => [bankMarketKey(price.name), price]));
    let heldDroppedValue = 0;
    let heldPurchasedValue = 0;
    document.querySelectorAll("#ls-bank-body tr[data-bank-search]").forEach(row => {
      const explicitlyUsed = /\bUsed:/.test(row.cells[0]?.textContent || "");
      const heldPurchased = row.dataset.status === "purchased" && !explicitlyUsed;
      if (heldPurchased && !row.querySelector(".bank-market-value")) {
        const label = row.cells[0]?.querySelector("b")?.textContent.trim() || "";
        const [, quantity = "1", item = label] = label.match(/^(\d+)×\s+(.+)$/) || [];
        row.cells[4].innerHTML = `<span class="bank-market-value" data-bank-item="${safeText(item)}" data-bank-quantity="${safeText(quantity)}">Loading…</span>`;
      }
      if (row.dataset.status !== "held" && !heldPurchased) return;
      const purchased = !/^(event drop|donation)/.test(row.dataset.source || "");
      const badge = row.querySelector(".bank-status");
      if (badge) {
        badge.textContent = purchased ? "Held (Purchased)" : "Held (Dropped)";
        badge.classList.remove("purchased");
        badge.classList.add("held");
        badge.classList.toggle("purchased", purchased);
        badge.classList.toggle("dropped", !purchased);
      }
    });
    document.querySelectorAll("#ls-bank-body tr[data-status='purchased']").forEach(row => {
      if (!/\bUsed:/.test(row.cells[0]?.textContent || "")) return;
      const badge = row.querySelector(".bank-status");
      if (badge) { badge.textContent = "Used"; badge.classList.add("used"); }
    });
    document.querySelectorAll(".bank-market-value").forEach(cell => {
      const row = cell.closest("tr");
      const price = byName[bankMarketKey(cell.dataset.bankItem)];
      const candidates = [price?.bazaar_lowest, price?.single_recent_average, price?.single_average]
        .filter(value => value !== null && value !== undefined && value !== "")
        .map(Number).filter(value => Number.isFinite(value) && value > 0);
      const timelessHourglass = bankMarketKey(cell.dataset.bankItem) === "timelesshourglass";
      const purchaseFallback = Number(row?.dataset.purchase || 0) / Math.max(1, Number(cell.dataset.bankQuantity || 1));
      const unit = timelessHourglass && purchaseFallback > 0
        ? purchaseFallback
        : (candidates.length ? Math.min(...candidates) : null);
      if (unit == null) { cell.textContent = "—"; cell.title = "No PSXI market value is currently available."; return; }
      const value = Number(unit) * Number(cell.dataset.bankQuantity || 1);
      const purchased = !/^(event drop|donation)/.test(row?.dataset.source || "");
      if (purchased) heldPurchasedValue += value;
      else heldDroppedValue += value;
      row.dataset.market = String(value);
      cell.textContent = formatBankGil(value);
      const source = timelessHourglass && purchaseFallback > 0
        ? "recorded purchase value"
        : (Number(price?.bazaar_lowest) === unit ? "lowest bazaar listing" : "sale average");
      cell.title = `PSXI ${source}: ${formatBankGil(unit)} each`;
    });
    const cash = Number(document.querySelector(".ls-bank-summary")?.dataset.bankCash || 0);
    const heldDropped = document.querySelector("#bank-held-dropped");
    const heldPurchased = document.querySelector("#bank-held-purchased");
    const total = document.querySelector("#bank-total-value");
    if (heldDropped) heldDropped.textContent = formatBankGil(heldDroppedValue);
    if (heldPurchased) heldPurchased.textContent = formatBankGil(heldPurchasedValue);
    if (total) total.textContent = formatBankGil(cash + heldDroppedValue + heldPurchasedValue);
    filterBankRows();
  };
  const bankDetailDialog = document.createElement("dialog");
  bankDetailDialog.className = "ls-bank-detail-dialog";
  document.body.append(bankDetailDialog);
  const bankDetailRows = kind => [...document.querySelectorAll("#ls-bank-body tr[data-bank-search]")].filter(row => {
    const source = row.dataset.source || "";
    if (kind === "cash") return row.dataset.status === "sold" || !/^(event drop|donation)/.test(source);
    const purchased = !/^(event drop|donation)/.test(source);
    return row.dataset.status === "held" && (kind === "purchased" ? purchased : !purchased);
  }).map(row => {
    const heldBy = row.querySelector("select[name='holder_member_id'] option:checked")?.textContent || row.cells[2]?.textContent.trim() || "Unassigned";
    const purchasedBy = row.querySelector("select[name='purchaser_member_id'] option:checked")?.textContent || heldBy;
    const holder = kind === "cash" && row.dataset.status !== "sold" ? purchasedBy : heldBy;
    const item = row.cells[0]?.querySelector("b")?.textContent.trim() || "Item";
    const source = [row.dataset.bankSourceLabel, row.dataset.bankEventLabel].filter(Boolean).join(" · ");
    const market = row.querySelector(".bank-market-value")?.textContent.trim() || "—";
    const cash = row.dataset.status === "sold" ? row.cells[5]?.textContent.match(/[\d,]+g/)?.[0] || "—" : `-${Number(row.dataset.purchase || 0).toLocaleString()}g`;
    return {holder, item, source, value: kind === "cash" ? cash : market};
  });
  const openBankDetail = (kind, title) => {
    const rows = bankDetailRows(kind);
    const groups = [...rows.reduce((all, row) => {
      const amount = Number(String(row.value).replace(/[^\d-]/g, ""));
      const group = all.get(row.holder) || {holder: row.holder, amount: 0, rows: []};
      group.amount += amount;
      group.rows.push({...row, amount});
      all.set(row.holder, group);
      return all;
    }, new Map()).values()].sort((left, right) => right.amount - left.amount);
    const gil = amount => `${amount < 0 ? "−" : ""}${Math.abs(Math.round(amount)).toLocaleString()}g`;
    bankDetailDialog.innerHTML = `<form method="dialog"><button class="ls-bank-detail-close" aria-label="Close">×</button></form><h2>${title}</h2><table><thead><tr><th>Officer</th><th>Current total</th></tr></thead><tbody>${groups.length ? groups.map(group => `<tr><td><details><summary><b>${safeText(group.holder)}</b><small>Expand log · ${group.rows.length} entr${group.rows.length === 1 ? "y" : "ies"}</small></summary><ol>${group.rows.map(row => `<li><b>${safeText(row.item)}</b><small>${safeText(row.source)}</small><span>${gil(row.amount)}</span></li>`).join("")}</ol></details></td><td>${gil(group.amount)}</td></tr>`).join("") : '<tr><td colspan="2">No entries.</td></tr>'}</tbody></table>`;
    bankDetailDialog.showModal();
  };
  [["#bank-cash-balance", "cash", "LS Gil balance"], ["#bank-held-dropped", "dropped", "Held dropped items"], ["#bank-held-purchased", "purchased", "Held purchased items"]].forEach(([selector, kind, title]) => {
    const metric = document.querySelector(selector);
    if (!metric) return;
    metric.closest("article")?.classList.add("ls-bank-detail-trigger");
    metric.closest("article")?.addEventListener("click", () => openBankDetail(kind, title));
  });
  const refreshBankMarket = () => {
    const buttons = [...document.querySelectorAll(".refresh-bank-market")];
    buttons.forEach(control => { control.disabled = true; control.textContent = "Refreshing…"; });
    return fetch("/api/market-prices?refresh=1", {headers: {"Accept": "application/json"}})
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(snapshot => { updateBankItemCatalog(snapshot.prices); updateBankMarketValues(snapshot.prices); })
      .catch(() => document.querySelectorAll(".bank-market-value").forEach(cell => { cell.textContent = "Market unavailable"; }))
      .finally(() => buttons.forEach(control => { control.disabled = false; control.textContent = "Refresh market"; }));
  };
  const bankControlsHeader = document.querySelector(".ls-bank-table thead th:last-child");
  const bankRefreshButtons = [...document.querySelectorAll(".refresh-bank-market")];
  const bankRefreshButton = bankRefreshButtons.shift();
  if (bankControlsHeader && bankRefreshButton) {
    bankRefreshButton.textContent = "Refresh market";
    bankControlsHeader.append(" ", bankRefreshButton);
    bankRefreshButtons.forEach(button => button.remove());
  }
  bankRefreshButton?.addEventListener("click", refreshBankMarket);
  let bankSaveAll = document.querySelector("#ls-bank-save-all");
  if (!bankSaveAll && document.querySelector(".ls-bank-row-editor")) {
    const controlsHeader = document.querySelector(".ls-bank-table thead th:last-child");
    if (controlsHeader) {
      bankSaveAll = document.createElement("button");
      bankSaveAll.id = "ls-bank-save-all";
      bankSaveAll.className = "ls-bank-save-all";
      bankSaveAll.type = "button";
      bankSaveAll.textContent = "Save all";
      controlsHeader.append(" ", bankSaveAll);
    }
  }
  bankSaveAll?.addEventListener("click", () => {
    const rows = [...document.querySelectorAll(".ls-bank-row-editor")];
    if (!rows.length) return;
    const body = new URLSearchParams();
    body.set("csrf_token", rows[0].querySelector("[name='csrf_token']")?.value || "");
    rows.forEach(form => {
      const id = form.action.match(/\/bank\/(\d+)\/update/)?.[1];
      if (!id) return;
      body.append("entry_id", id);
      body.append("holder_member_id", form.elements.holder_member_id.value);
      body.append("purchaser_member_id", form.elements.purchaser_member_id.value);
      body.append("status", form.elements.status.value);
      body.append("sale_gil", form.elements.sale_gil?.value || "");
      body.append("acquisition_kind", form.elements.acquisition_kind.value);
      body.append("event_id", form.elements.event_id.value);
      body.append("purchase_gil", form.elements.purchase_gil.value);
      body.append("notes", form.elements.notes.value);
    });
    bankSaveAll.disabled = true;
    bankSaveAll.textContent = "Saving…";
    fetch("/endgame/bank/bulk-update", {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, body})
      .then(async response => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) throw new Error(payload.message || "Unable to save LS Bank rows.");
        rows.forEach(form => {
          const row = form.closest("tr");
          const sale = form.elements.acquisition_kind?.value === "Mercenary"
            ? Number(form.elements.purchase_gil?.value || 0)
            : Number(form.elements.sale_gil?.value || 0);
          if (!sale || !row) return;
          row.dataset.status = "sold";
          const badge = row.querySelector(".bank-status");
          if (badge) { badge.textContent = "Sold"; badge.className = "bank-status sold"; }
          row.cells[5].querySelector(".bank-sale-gil")?.remove();
          if (!row.cells[5].querySelector("small")) {
            const saleText = document.createElement("small");
            saleText.textContent = formatBankGil(sale);
            row.cells[5].append(saleText);
          }
        });
        showBankSaveMessage(payload.message || "LS Bank entries saved.");
        refreshBankBalance();
      })
      .catch(error => alert(error.message))
      .finally(() => { bankSaveAll.disabled = false; bankSaveAll.textContent = "Save all"; });
  });
  if (document.querySelector(".ls-bank-panel")) {
    filterBankRows();
    fetch("/endgame/bank/purchasers", {headers: {"Accept": "application/json"}})
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(payload => {
        document.querySelectorAll(".ls-bank-row-editor").forEach(form => {
          const id = form.action.match(/\/bank\/(\d+)\/update/)?.[1];
          const purchaser = form.elements.purchaser_member_id;
          const storedPurchaser = id ? payload.purchasers?.[id] : null;
          if (purchaser && storedPurchaser) purchaser.value = String(storedPurchaser);
        });
      })
      .catch(() => {});
    fetch("/api/market-prices", {headers: {"Accept": "application/json"}})
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(snapshot => { updateBankItemCatalog(snapshot.prices); updateBankMarketValues(snapshot.prices); })
      .catch(() => document.querySelectorAll(".bank-market-value").forEach(cell => { cell.textContent = "Market unavailable"; }));
  }
  let bankSort = {key: "item", direction: 1};
  document.querySelectorAll("[data-bank-sort]").forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.bankSort;
    bankSort = {key, direction: bankSort.key === key ? -bankSort.direction : 1};
    document.querySelectorAll("[data-bank-sort]").forEach(control => {
      control.classList.toggle("active", control === button);
      control.querySelector("span").textContent = control === button ? (bankSort.direction > 0 ? "ASC" : "DESC") : "Sort";
    });
    const type = button.dataset.sortType;
    const body = document.querySelector("#ls-bank-body");
    if (!body) return;
    [...body.rows].sort((left, right) => {
      const a = left.dataset[key] || "", b = right.dataset[key] || "";
      return (type === "number" ? Number(a) - Number(b) : a.localeCompare(b, undefined, {numeric: true})) * bankSort.direction;
    }).forEach(row => body.appendChild(row));
  }));
  if (dynamisCatalogZoneFilter && ![...dynamisCatalogZoneFilter.options].some(option => option.value === "")) {
    dynamisCatalogZoneFilter.prepend(new Option("All Dynamis zones", ""));
  }
  const dynamisCatalogTooltips = new Map((window.ENDGAME_DYNAMIS_CATALOG || []).map(drop => [drop.item, drop.tooltip || {}]));
  const dynamisItemTooltip = document.createElement("aside");
  dynamisItemTooltip.className = "auction-item-tooltip dynamis-item-tooltip";
  dynamisItemTooltip.hidden = true;
  dynamisItemTooltip.setAttribute("role", "tooltip");
  document.body.append(dynamisItemTooltip);
  const positionDynamisTooltip = (x, y) => {
    const width = dynamisItemTooltip.offsetWidth || 390;
    const height = dynamisItemTooltip.offsetHeight || 220;
    dynamisItemTooltip.style.left = `${Math.max(10, Math.min(innerWidth - width - 10, x + 14))}px`;
    dynamisItemTooltip.style.top = `${Math.max(10, Math.min(innerHeight - height - 10, y + 14))}px`;
  };
  document.querySelectorAll(".dynamis-lot-panel:not(.dynamis-legacy-layout) #dynamis-drop-list article").forEach(card => {
    const item = dynamisCatalogTooltips.get(card.querySelector("b")?.textContent.trim());
    if (!item) return;
    card.classList.add("dynamis-tooltip-target");
    card.tabIndex = 0;
    const show = (x, y) => {
      const rarity = item.rare && item.ex ? "Rare/Ex" : item.rare ? "Rare" : item.ex ? "Ex" : "";
      dynamisItemTooltip.innerHTML = `${item.item_id ? `<img src="https://static.ffxiah.com/images/icon/${item.item_id}.png" alt="">` : ""}<div><strong>${safeText(item.name)}</strong><span>${rarity ? `${rarity} · ` : ""}Level ${item.level || "—"} · ${safeText((item.slots || []).join(" / "))}</span><p>${safeText(item.description || "No item stats available.")}</p><small>${safeText((item.jobs || []).join(" / "))}</small></div>`;
      dynamisItemTooltip.hidden = false;
      positionDynamisTooltip(x, y);
    };
    card.addEventListener("mouseenter", event => show(event.clientX, event.clientY));
    card.addEventListener("mousemove", event => positionDynamisTooltip(event.clientX, event.clientY));
    card.addEventListener("mouseleave", () => { dynamisItemTooltip.hidden = true; });
    card.addEventListener("focus", () => { const box = card.getBoundingClientRect(); show(box.right, box.top); });
    card.addEventListener("blur", () => { dynamisItemTooltip.hidden = true; });
  });
  const priorityLabel = value => ({"Main priority":"P1","Secondary priority":"P2","P1 Auction":"P1","P2 Auction":"P2","P3 Auction":"P3"}[value] || value || "Freelot");
  const auctionRoot = document.querySelector("#active-auctions");
  const openLiveAuction = () => {
    activateView("dkp-loot");
    activate("bidding-live");
    requestAnimationFrame(() => auctionRoot?.scrollIntoView({behavior: "smooth", block: "start"}));
  };
  window.addEventListener("endgame:open-live-auction", openLiveAuction);
  let auctionEditingUntil = 0;
  let auctionRecords = new Map();
  let pastAuctionsOpen = false;
  const auctionEditing = () => Date.now() < auctionEditingUntil || Boolean(
    document.activeElement?.closest?.(".auction-bid-form, .auction-winner-select")
  );
  let auctionTooltips = {};
  const auctionError = message => `<p class="auction-message error">${safeText(message)}</p>`;
  const countdownText = endsAt => {
    const seconds = Math.max(0, Math.ceil((Date.parse(`${endsAt}Z`) - Date.now()) / 1000));
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  };
  const activityTimestamp = value => {
    const parsed = Date.parse(String(value || "").includes("T") ? value : `${value}Z`);
    return Number.isNaN(parsed) ? "" : new Date(parsed).toLocaleString([], {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"});
  };
  const renderAuctions = payload => {
    if (!auctionRoot) return;
    const currentAuctions = payload.current_auctions || payload.auctions.filter(auction => auction.status !== "Confirmed");
    const pastAuctions = payload.past_auctions || payload.auctions.filter(auction => auction.status === "Confirmed");
    const displayedAuctions = [...currentAuctions, ...pastAuctions];
    document.querySelectorAll('[data-auction-metric="my-dkp"]').forEach(metric => { metric.textContent = `${payload.my_available} DKP${payload.my_reserved ? ` (${payload.my_reserved} committed)` : ""}`; });
    document.querySelectorAll('[data-auction-metric="bid-cap"]').forEach(metric => { metric.textContent = `${payload.dkp.cap} DKP`; });
    document.querySelectorAll('[data-auction-metric="highest-dkp"]').forEach(metric => { metric.textContent = `${payload.dkp.highest} DKP`; });
    auctionTooltips = Object.fromEntries(payload.auctions.flatMap(auction => auction.items.map(item => [String(item.id), item.tooltip || {}])));
    auctionRecords = new Map(payload.auctions.map(auction => [String(auction.id), auction]));
    auctionRoot.innerHTML = displayedAuctions.length ? displayedAuctions.map((auction, index) => {
      const active = auction.status === "Active";
      const completed = auction.status === "Confirmed";
      const acceptingBids = active && !auction.paused;
      const items = auction.items.map(item => {
        const bids = item.bids.length ? item.bids.map((bid, index) => `<li class="${index === 0 ? "leading" : ""}"><span><b>${safeText(bid.name)}</b> ${safeText(bid.job)} · P${bid.tier === 4 ? "Free" : bid.tier}</span><strong>${bid.amount} DKP</strong></li>`).join("") : '<li class="no-bids">No bids yet</li>';
        const jobOptions = item.eligible_jobs.map(entry => `<option value="${entry.job}" ${item.my_bid?.job === entry.job ? "selected" : ""}>${entry.job} · Lv.${entry.level} · ${entry.tier === 4 ? "Freelot" : `P${entry.tier}`}</option>`).join("");
        const bidderOptions = item.bids.map(bid => `<option value="${bid.member_id}" ${bid.member_id === item.suggested_winner_id ? "selected" : ""}>${safeText(bid.name)} · ${bid.job} · ${bid.amount} DKP · P${bid.tier === 4 ? "Free" : bid.tier}</option>`).join("");
        return `<article class="auction-item-card"><header><div><h4><button class="auction-tooltip-target" type="button" data-auction-tooltip="${item.id}">${safeText(item.item)}</button></h4><small>${item.target_item && item.target_item !== item.item ? `${safeText(item.target_item)} · ` : ""}${safeText(item.family)} · Lv.${item.required_level}</small></div><b>${item.bids.length} bid${item.bids.length === 1 ? "" : "s"}</b></header><ol class="auction-bid-list">${bids}</ol>${acceptingBids ? (jobOptions ? `<form class="auction-bid-form" data-auction-item="${item.id}"><select name="job" required><option value="">Eligible job</option>${jobOptions}</select><input type="number" name="amount" min="1" max="${item.max_bid}" value="${item.my_bid?.amount || ""}" placeholder="DKP" required><button type="submit">${item.my_bid ? "Update Bid" : "Place Bid"}</button><small class="auction-bid-budget">Up to ${item.max_bid} DKP; increasing this may reduce other active bids</small></form>` : '<p class="auction-ineligible">No eligible leveled job for this item.</p>') : (active ? '<p class="auction-paused-note">Bidding is paused by leadership.</p>' : `<label class="auction-winner-select">Confirmed winner<select name="winner_${item.id}" form="confirm-auction-${auction.id}"><option value="">No award</option>${bidderOptions}</select></label>`)}</article>`;
      }).join("");
      const pauseControl = active && payload.is_admin ? `<form class="auction-pause-form" method="post" action="/endgame/auctions/${auction.id}/pause"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF)}"><button type="submit">${auction.paused ? "Resume Auction" : "Pause Auction"}</button></form>` : "";
      const completeControl = active && payload.is_admin ? `<form class="auction-complete-form" method="post" action="/endgame/auctions/${auction.id}/complete"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF)}"><button type="submit">Stop &amp; Complete</button></form>` : "";
      const stopControl = active && payload.is_admin ? `<form class="auction-discard-form" method="post" action="/endgame/auctions/${auction.id}/delete"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF)}"><button class="danger" type="submit">Stop &amp; Delete Auction</button></form>` : "";
      const sectionHeading = (currentAuctions.length && index === 0) ? `<h3 class="auction-section-title">Current Auctions</h3>` : (pastAuctions.length && index === currentAuctions.length ? `<h3 class="auction-section-title">Past Auctions</h3>` : "");
      return `${sectionHeading}<section id="auction-${auction.id}" class="auction-card ${active ? "active" : "closed"} ${completed ? "completed" : ""} ${auction.paused ? "paused" : ""}"><header><div><span>${safeText(auction.area)} · ${safeText(auction.event_name)}</span><h3>${safeText(auction.boss)}</h3>${pauseControl}${completeControl}${stopControl}</div><div class="auction-clock"><small>${completed ? "Winners / DKP Completed" : (auction.paused ? "Countdown frozen" : (active ? "Bidding closes in" : "Bidding closed"))}</small><b data-auction-ends="${auction.ends_at}" data-auction-paused="${auction.paused ? "true" : "false"}">${auction.paused ? "PAUSED" : (active ? countdownText(auction.ends_at) : "00:00")}</b></div></header>${!active && !completed && payload.is_admin ? `<form id="confirm-auction-${auction.id}" class="auction-confirm-form" method="post" action="/endgame/auctions/${auction.id}/confirm"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF)}"><p>Review the suggested winners, then confirm the items that actually dropped.</p></form>` : ""}<div class="auction-item-grid">${items}</div>${!active && !completed && payload.is_admin ? `<button class="button primary auction-confirm-button" type="submit" form="confirm-auction-${auction.id}">Confirm Winners &amp; Deduct DKP</button>` : ""}${completed ? `<p class="auction-completed-note">Winners / DKP Completed${auction.award_count ? ` · ${auction.award_count} award${auction.award_count === 1 ? "" : "s"}` : ""}</p>` : ""}</section>`;
    }).join("") : '<p class="event-empty">No active or recently closed auctions. An administrator can start one for an Endgame event above.</p>';
    displayedAuctions.filter(auction => auction.status === "Confirmed").forEach(auction => {
      const cards = [...document.querySelectorAll(`#auction-${auction.id} .auction-item-card`)];
      auction.items.forEach((item, index) => {
        if (!item.awards?.length || !cards[index]) return;
        cards[index].querySelector(".auction-bid-list")?.insertAdjacentHTML("afterend", `<div class="auction-award-summary">${item.awards.map(award => `<span><b>${safeText(award.recipient)}</b> · ${safeText(award.job)} · ${Number(award.dkp_cost)} DKP · ${safeText(award.distribution)}</span>`).join("")}</div>`);
      });
    });
    displayedAuctions.forEach(auction => {
      const card = document.getElementById(`auction-${auction.id}`);
      const heading = card?.querySelector("header h3");
      if (heading) heading.textContent = `Auction #${auction.id} / ${auction.boss}`;
    });
    if (pastAuctions.length) {
      const firstPastCard = document.getElementById(`auction-${pastAuctions[0].id}`);
      const archive = document.createElement("details");
      archive.className = "past-auctions-archive";
      archive.innerHTML = `<summary>Past Auctions <span>${pastAuctions.length}</span></summary><div class="past-auctions-list"></div>`;
      archive.open = pastAuctionsOpen;
      archive.addEventListener("toggle", () => { pastAuctionsOpen = archive.open; });
      firstPastCard?.previousElementSibling?.classList.contains("auction-section-title") && firstPastCard.previousElementSibling.remove();
      firstPastCard?.before(archive);
      const list = archive.querySelector(".past-auctions-list");
      pastAuctions.forEach(auction => list?.append(document.getElementById(`auction-${auction.id}`)));
    }
    // Closed auctions are deliberately kept until an administrator confirms them.
    // A separate discard control makes it safe to clear test auctions without touching DKP.
    if (payload.is_admin) {
      auctionRoot.querySelectorAll(".auction-card.active .auction-discard-form").forEach(form => {
        form.addEventListener("submit", event => {
          if (!confirm("Stop and delete this auction? All bids will be cleared and no DKP will be deducted.")) event.preventDefault();
        });
      });
      payload.auctions.filter(auction => auction.status === "Closed" || auction.status === "Confirmed").forEach(auction => {
        const card = document.getElementById(`auction-${auction.id}`);
        if (!card) return;
        const actions = document.createElement("form");
        actions.className = "auction-discard-form";
        actions.method = "post";
        actions.action = `/endgame/auctions/${auction.id}/delete`;
        actions.innerHTML = `<input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF)}"><button type="submit">${auction.status === "Confirmed" ? "Discard &amp; Reverse DKP" : "Discard Auction"}</button>`;
        actions.addEventListener("submit", event => {
          const warning = auction.status === "Confirmed" ? "Discard this confirmed auction and reverse its linked DKP awards?" : "Discard this closed auction? No DKP will be deducted.";
          if (!confirm(warning)) event.preventDefault();
        });
        card.querySelector("header > div")?.append(actions);
        const reopen = document.createElement("form");
        reopen.className = "auction-reopen-form";
        reopen.method = "post";
        reopen.action = `/endgame/auctions/${auction.id}/reopen`;
        reopen.innerHTML = `<input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF)}"><button type="submit">Reopen for Editing</button>`;
        reopen.addEventListener("submit", event => {
          if (!confirm("Reopen this auction for five minutes? Linked DKP awards will be restored so winners can be corrected.")) event.preventDefault();
        });
        card.querySelector("header > div")?.append(reopen);
      });
      pastAuctions.forEach(auction => {
        const card = document.getElementById(`auction-${auction.id}`);
        card?.querySelectorAll(".auction-winner-select").forEach(control => {
          const note = document.createElement("p");
          note.className = "auction-completed-note";
          note.textContent = "Winners / DKP Completed";
          control.replaceWith(note);
        });
      });
    }
    pastAuctions.forEach(auction => {
      const card = document.getElementById(`auction-${auction.id}`);
      card?.querySelectorAll(".auction-winner-select").forEach(control => {
        const note = document.createElement("p");
        note.className = "auction-completed-note";
        note.textContent = "Winners / DKP Completed";
        control.replaceWith(note);
      });
    });
    auctionRoot.querySelectorAll(".auction-bid-list li span, .auction-winner-select option").forEach(entry => {
      entry.innerHTML = entry.innerHTML.replace("PFree", "Freelot");
    });
    const recent = document.querySelector("#recent-auction-bids");
    recent.innerHTML = payload.recent_bids.length ? payload.recent_bids.map(bid => `<article><span><b>${safeText(bid.name)}</b> bid on ${safeText(bid.item)}<small>${safeText(bid.boss)} · ${safeText(bid.job)} · ${safeText(activityTimestamp(bid.updated_at))}</small></span><strong>${bid.amount} DKP</strong></article>`).join("") : '<p class="event-empty">No bids have been placed.</p>';
  };
  const loadAuctions = async () => {
    if (!auctionRoot) return;
    if (auctionEditing()) return;
    try {
      const response = await fetch("/api/endgame/auctions", {headers: {"Accept": "application/json"}});
      if (!response.ok) throw new Error("Could not refresh bidding.");
      const payload = await response.json();
      if (auctionEditing()) return;
      renderAuctions(payload);
      const auctionAnchor = location.hash.slice(1);
      if (auctionAnchor.startsWith("auction-")) {
        requestAnimationFrame(() => document.getElementById(auctionAnchor)?.scrollIntoView({behavior: "smooth", block: "start"}));
      }
      const state = document.querySelector("#auction-refresh-state");
      if (state) state.textContent = `Updated ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"})}`;
    } catch (error) { auctionRoot.innerHTML = auctionError(error.message); }
  };
  document.addEventListener("submit", async event => {
    const form = event.target.closest(".auction-bid-form");
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector("button"); button.disabled = true;
    try {
      const values = new FormData(form);
      const response = await fetch(`/api/endgame/auction-items/${form.dataset.auctionItem}/bid`, {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": window.ENDGAME_CSRF}, body: JSON.stringify({job: values.get("job"), amount: values.get("amount")})});
      if (!response.ok) { const text = await response.text(); throw new Error(text.match(/<p>(.*?)<\/p>/s)?.[1] || "The bid could not be placed."); }
      const result = await response.json();
      renderAuctions(result.auction);
      if (result.adjusted?.length) alert(`Bid updated. To keep your total within your DKP, these bids were adjusted:\n${result.adjusted.map(row => `${row.item}: ${row.from} → ${row.to} DKP`).join("\n")}`);
    } catch (error) { alert(error.message); button.disabled = false; }
  });
  if (auctionRoot) {
    auctionRoot.addEventListener("input", event => { if (event.target.closest(".auction-bid-form")) auctionEditingUntil = Date.now() + 15000; });
    auctionRoot.addEventListener("change", event => {
      if (event.target.closest(".auction-bid-form")) auctionEditingUntil = Date.now() + 15000;
      if (event.target.closest(".auction-winner-select")) auctionEditingUntil = Date.now() + 600000;
    });
    loadAuctions();
    setInterval(loadAuctions, 5000);
    setInterval(() => document.querySelectorAll("[data-auction-ends]").forEach(clock => { if (clock.dataset.auctionPaused !== "true") clock.textContent = countdownText(clock.dataset.auctionEnds); }), 1000);
  }
  const auctionTooltip = document.querySelector("#auction-item-tooltip");
  const placeAuctionTooltip = (x, y) => {
    if (!auctionTooltip || auctionTooltip.hidden) return;
    const gap = 14, width = auctionTooltip.offsetWidth, height = auctionTooltip.offsetHeight;
    auctionTooltip.style.left = `${Math.max(10, Math.min(innerWidth - width - 10, x + gap))}px`;
    auctionTooltip.style.top = `${Math.max(10, Math.min(innerHeight - height - 10, y + gap))}px`;
  };
  const showAuctionTooltip = (target, x, y) => {
    const item = auctionTooltips[target.dataset.auctionTooltip];
    if (!auctionTooltip || !item) return;
    const rarity = [item.rare ? "Rare" : "", item.ex ? "Ex" : ""].filter(Boolean).join("/");
    auctionTooltip.innerHTML = `${item.item_id ? `<img src="https://static.ffxiah.com/images/icon/${item.item_id}.png" alt="">` : ""}<div><strong>${safeText(item.name)}</strong><span>${rarity ? `${rarity} · ` : ""}Level ${item.level || "—"} · ${safeText((item.slots || []).join(" / "))}</span><p>${safeText(item.description || "No item stats available.")}</p><small>${safeText((item.jobs || []).join(" / "))}</small></div>`;
    auctionTooltip.hidden = false; placeAuctionTooltip(x, y);
  };
  document.addEventListener("pointerover", event => { const target = event.target.closest("[data-auction-tooltip]"); if (target) showAuctionTooltip(target, event.clientX, event.clientY); });
  document.addEventListener("pointermove", event => placeAuctionTooltip(event.clientX, event.clientY));
  document.addEventListener("pointerout", event => { if (event.target.closest("[data-auction-tooltip]") && !event.relatedTarget?.closest?.("[data-auction-tooltip]")) auctionTooltip.hidden = true; });
  document.addEventListener("focusin", event => { const target = event.target.closest("[data-auction-tooltip]"); if (target) { const box = target.getBoundingClientRect(); showAuctionTooltip(target, box.right, box.top); } });
  document.addEventListener("focusout", event => { if (event.target.closest("[data-auction-tooltip]") && auctionTooltip) auctionTooltip.hidden = true; });
  const renderAdminAudit = () => {
    const body = document.querySelector("#admin-audit-body");
    if (!body) return;
    const filters = [...document.querySelectorAll("[data-audit-filter]")].reduce((values, control) => ({...values, [control.dataset.auditFilter]: control.value.trim().toLowerCase()}), {});
    const rows = adminAudit.filter(row => Object.entries(filters).every(([key, wanted]) => !wanted || String(row[key] ?? "").toLowerCase().includes(wanted))).sort((left, right) => {
      if (auditSort.key === "at") return ((Date.parse(left.at) || 0) - (Date.parse(right.at) || 0)) * auditSort.direction;
      return String(left[auditSort.key] ?? "").localeCompare(String(right[auditSort.key] ?? ""), undefined, {numeric: true}) * auditSort.direction;
    });
    body.innerHTML = rows.length ? rows.map(row => `<tr><td>${safeText(row.at)}</td><td><b>${safeText(row.actor)}</b></td><td>${safeText(row.area)}</td><td>${safeText(row.action)}</td><td>${safeText(row.details)}</td></tr>`).join("") : '<tr><td colspan="5">No administrator changes match the current filters.</td></tr>';
  };
  const recordAdminChange = (area, action, details) => {
    adminAudit.push({at: new Date().toLocaleString(), actor: window.ENDGAME_ACTOR || "Administrator", area, action, details});
    localStorage.setItem(adminAuditKey, JSON.stringify(adminAudit));
    renderAdminAudit();
  };
  renderAdminAudit();
  const auditFilters = [...document.querySelectorAll("[data-audit-filter]")];
  auditFilters.forEach(control => control.addEventListener("input", renderAdminAudit));
  document.querySelector(".clear-audit-filters")?.addEventListener("click", () => {
    auditFilters.forEach(control => { control.value = ""; });
    renderAdminAudit();
  });
  document.querySelectorAll("[data-audit-sort]").forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.auditSort;
    auditSort = {key, direction: auditSort.key === key ? -auditSort.direction : 1};
    document.querySelectorAll("[data-audit-sort]").forEach(control => {
      control.classList.toggle("active", control === button);
      control.querySelector("span").textContent = control === button ? (auditSort.direction > 0 ? "ASC" : "DESC") : "Sort";
    });
    renderAdminAudit();
  }));
  const refreshJobCooldowns = () => document.querySelectorAll("[data-job-cooldown-until]").forEach(label => {
    const remaining = Math.max(0, Date.parse(label.dataset.jobCooldownUntil) - Date.now());
    if (!remaining) { label.hidden = true; return; }
    const days = Math.floor(remaining / 86400000);
    const hours = Math.floor((remaining % 86400000) / 3600000);
    label.textContent = `Job change: ${days}d ${hours}h remaining`;
  });
  refreshJobCooldowns();
  setInterval(refreshJobCooldowns, 60000);
  const jobHistory = (member, slot) => jobChanges.filter(row => row.member === member && row.slot === slot);
  const jobHistoryLabel = (member, slot) => {
    const changes = jobHistory(member, slot);
    if (!changes.length) return "No changes recorded";
    return changes.slice(-5).reverse().map(row => `${row.from || "Unassigned"} to ${row.to || "Unassigned"}\n${row.at} by ${row.actor}`).join("\n\n");
  };
  const updateJobDisplay = (member, slot, value) => {
    const record = roster.find(row => row.name === member);
    if (record) record[slot] = value;
    const badge = document.querySelector(`[data-job-member="${CSS.escape(member)}"][data-job-slot="${slot}"]`);
    if (badge) {
      badge.textContent = value || (slot === "main_job" ? "Unassigned" : "None");
      badge.dataset.jobHistory = jobHistoryLabel(member, slot);
      const tableRow = badge.closest("tr");
      if (tableRow && record) {
        tableRow.dataset.jobs = `${record.main_job || ""} ${record.secondary_job || ""}`.toLowerCase();
        tableRow.dataset[slot === "main_job" ? "main" : "secondary"] = (value || "").toLowerCase();
      }
    }
  };
  if (window.ENDGAME_IS_ADMIN) {
    roster.forEach(member => ["main_job", "secondary_job"].forEach(slot => {
      const changes = jobHistory(member.name, slot);
      updateJobDisplay(member.name, slot, changes.length ? changes[changes.length - 1].to : member[slot]);
    }));
  }
  const priorityBody = document.querySelector("#priority-body");
  const priorityJob = {value: "", addEventListener: () => {}};
  const priorityItem = document.querySelector("#priority-item");
  const priorityMajor = document.querySelector("#priority-major");
  const lastDate = value => value === "—" ? 0 : new Date(value).getTime();
  const rankPriority = () => {
    const job = priorityJob.value;
    const major = priorityMajor.value === "major";
    const candidates = roster.map(member => ({...member, jobStatus: member.main_job === job ? 1 : member.secondary_job === job ? 2 : 9}))
      .filter(member => member.jobStatus < 9)
      .sort((a, b) => a.jobStatus - b.jobStatus || a.tier - b.tier || (major ? Number(a.cooldown) - Number(b.cooldown) : 0) || a.major_wins - b.major_wins || lastDate(a.last_major_win) - lastDate(b.last_major_win) || a.name.localeCompare(b.name));
    document.querySelector("#priority-title").textContent = `${priorityItem.value || "Selected item"} · ${job || "Choose a job"}`;
    document.querySelector("#priority-note").textContent = candidates.length ? `${candidates.length} registered candidates. Eligibility checks still apply at the event.` : "No member has this job registered as Main or Secondary.";
    priorityBody.innerHTML = candidates.map((member, index) => {
      const explanation = member.jobStatus === 1 ? (member.tier === 1 ? "Main job · strongest attendance tier" : `Main job · Tier ${member.tier}`) : "Secondary job; follows all Main Job candidates";
      return `<tr><td><span class="rank-number ${index === 0 ? "top" : ""}">${index + 1}</span></td><td><b>${member.name}</b></td><td><span class="job-badge ${member.jobStatus === 1 ? "main" : ""}">${member.jobStatus === 1 ? "Main" : "Secondary"} ${job}</span></td><td><span class="tier tier-${member.tier}">Tier ${member.tier} · ${member.attendance}%</span></td><td><span class="cooldown ${member.cooldown ? "locked" : "ready"}">${member.cooldown ? "Cooldown" : "Ready"}</span></td><td>${member.major_wins}</td><td>${member.last_major_win}</td><td><small>${explanation}</small></td></tr>`;
    }).join("") || '<tr><td colspan="8">Choose a receiving job to calculate priority.</td></tr>';
  };
  [priorityJob, priorityItem, priorityMajor].forEach(control => control.addEventListener("input", rankPriority)); rankPriority();

  const rankMatrixPriority = () => {
    const item = priorityItems.find(row => row.name === priorityItem.value);
    if (!item) {
      document.querySelector("#priority-source").value = "";
      document.querySelector("#priority-title").textContent = "Select an item";
      document.querySelector("#priority-note").textContent = "Source, item family, job tiers, and calculated priority will appear automatically.";
      document.querySelector("#priority-tiers").innerHTML = "";
      priorityBody.innerHTML = '<tr><td colspan="8">Select a Sky or Sea drop to calculate priority.</td></tr>';
      return;
    }
    const tierFor = job => item.freelot ? 4 : item.p1.includes(job) ? 1 : item.p2.includes(job) ? 2 : item.p3.includes(job) ? 3 : 99;
    const candidates = roster.map(member => {
      const canEquip = job => job && Number((member.job_levels || {})[job] || 0) >= Number(item.required_level || 1);
      const mainTier = canEquip(member.main_job) ? tierFor(member.main_job) : 99;
      const secondaryTier = canEquip(member.secondary_job) ? tierFor(member.secondary_job) : 99;
      const useMain = mainTier <= secondaryTier;
      return {...member, priorityTier: Math.min(mainTier, secondaryTier), jobStatus: useMain ? 1 : 2, eligibleJob: useMain ? member.main_job : member.secondary_job};
    }).filter(member => member.priorityTier < 99 && (item.freelot || member.eligibleJob))
      .sort((a, b) => a.priorityTier - b.priorityTier || b.dkp - a.dkp || a.name.localeCompare(b.name));
    document.querySelector("#priority-source").value = `${item.area} / ${item.source}`;
    document.querySelector("#priority-title").textContent = `${item.name} / ${item.source}`;
    document.querySelector("#priority-note").textContent = candidates.length ? `${candidates.length} candidates meet the Lv.${item.required_level || 1} equipment requirement, grouped by P1/P2/P3 and sorted by DKP. Only P1 candidates may bid.` : `No registered member has an eligible job at Lv.${item.required_level || 1}.`;
    document.querySelector("#priority-tiers").innerHTML = item.freelot ? '<article class="freelot"><span>Distribution</span><b>Freelot</b><small>Attendance and general eligibility still apply.</small></article>' : [1,2,3].map(tier => `<article><span>P${tier}</span><b>${(item[`p${tier}`] || []).join(" / ") || "None"}</b><small>${tier === 1 ? "First consideration" : tier === 2 ? "After eligible P1 jobs" : "After eligible P1 and P2 jobs"}</small></article>`).join("");
    let previousRankKey = "", displayedRank = 0;
    priorityBody.innerHTML = candidates.map((member, index) => {
      const rankKey = `${member.priorityTier}|${member.dkp}`;
      if (rankKey !== previousRankKey) displayedRank = index + 1;
      previousRankKey = rankKey;
      const label = item.freelot ? "Freelot" : `P${member.priorityTier}`;
      const canBid = item.freelot || member.priorityTier === 1;
      const explanation = item.freelot ? "Freelot; normal event rules apply" : canBid ? `P1 ${member.eligibleJob}; eligible to bid up to available DKP` : `${label} fallback; P1 must clear first`;
      return `<tr><td><span class="rank-number ${displayedRank === 1 ? "top" : ""}">${displayedRank}</span></td><td><b>${member.name}</b></td><td><span class="job-badge ${member.priorityTier === 1 ? "main" : ""}">${label} / ${member.eligibleJob || ""} Lv.${(member.job_levels || {})[member.eligibleJob] || 0}</span></td><td><strong class="dkp-balance">${member.dkp}</strong></td><td><span class="dkp-bid-status ${canBid ? "eligible" : "waiting"}">${canBid ? "May bid" : "Waiting tier"}</span></td><td><small>${explanation}</small></td></tr>`;
    }).join("") || '<tr><td colspan="6">No eligible registered members for this item.</td></tr>';
  };
  [priorityItem, priorityMajor].forEach(control => control.addEventListener("input", rankMatrixPriority));
  rankMatrixPriority();

  const rosterSearch = document.querySelector("#endgame-roster-search");
  const columnFilters = [...document.querySelectorAll("[data-roster-filter]")];
  const filterRoster = () => document.querySelectorAll("#endgame-roster-body tr").forEach(row => {
    const query = rosterSearch.value.toLowerCase();
    const columnMatch = columnFilters.every(control => {
      const wanted = control.value.trim().toLowerCase();
      if (!wanted) return true;
      const actual = (row.dataset[control.dataset.rosterFilter] || "").toLowerCase();
      return control.dataset.filterMode === "min" ? Number(actual) >= Number(wanted) : actual.includes(wanted);
    });
    row.hidden = !(`${row.dataset.name} ${row.dataset.jobs}`.includes(query) && columnMatch);
  });
  [rosterSearch, ...columnFilters].filter(Boolean).forEach(control => control.addEventListener("input", filterRoster));
  let rosterSort = {key: "name", direction: 1};
  document.querySelectorAll("[data-roster-sort]").forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.rosterSort;
    rosterSort = {key, direction: rosterSort.key === key ? -rosterSort.direction : 1};
    document.querySelectorAll("[data-roster-sort]").forEach(control => {
      control.classList.toggle("active", control === button);
      control.querySelector("span").textContent = control === button ? (rosterSort.direction > 0 ? "ASC" : "DESC") : "Sort";
    });
    const type = button.dataset.sortType;
    const body = document.querySelector("#endgame-roster-body");
    [...body.rows].sort((a, b) => {
      let left = a.dataset[key] || "", right = b.dataset[key] || "";
      if (type === "number") { left = Number(left); right = Number(right); return (left - right) * rosterSort.direction; }
      if (type === "date") { left = Date.parse(left) || 0; right = Date.parse(right) || 0; return (left - right) * rosterSort.direction; }
      return left.localeCompare(right, undefined, {numeric: true}) * rosterSort.direction;
    }).forEach(row => body.appendChild(row));
  }));
  const defaultRosterSort = document.querySelector('[data-roster-sort="name"]');
  if (defaultRosterSort) {
    defaultRosterSort.classList.add("active");
    defaultRosterSort.querySelector("span").textContent = "ASC";
  }
  const lootSearch = document.querySelector("#loot-log-search");
  const lootColumnFilters = [...document.querySelectorAll("[data-loot-filter]")];
  const filterLoot = () => document.querySelectorAll("#loot-log-body tr").forEach(row => {
    const columnMatch = lootColumnFilters.every(control => {
      const wanted = control.value.trim().toLowerCase();
      const actual = (row.dataset[control.dataset.lootFilter] || "").toLowerCase();
      return !wanted || (control.dataset.filterMode === "min" ? Number(actual) >= Number(wanted) : actual.includes(wanted));
    });
    row.hidden = !(row.dataset.search.includes(lootSearch.value.toLowerCase()) && columnMatch);
  });
  [lootSearch, ...lootColumnFilters].filter(Boolean).forEach(control => control.addEventListener("input", filterLoot));
  document.querySelector(".clear-loot-filters")?.addEventListener("click", () => {
    lootColumnFilters.forEach(control => { control.value = ""; });
    lootSearch.value = ""; filterLoot();
  });
  let lootSort = {key: "date", direction: -1};
  document.querySelectorAll("[data-loot-sort]").forEach(button => button.addEventListener("click", () => {
    const key = button.dataset.lootSort;
    lootSort = {key, direction: lootSort.key === key ? -lootSort.direction : 1};
    document.querySelectorAll("[data-loot-sort]").forEach(control => {
      control.classList.toggle("active", control === button);
      control.querySelector("span").textContent = control === button ? (lootSort.direction > 0 ? "ASC" : "DESC") : "Sort";
    });
    const type = button.dataset.sortType;
    const body = document.querySelector("#loot-log-body");
    [...body.rows].sort((a, b) => {
      let left = a.dataset[key] || "", right = b.dataset[key] || "";
      if (type === "date") { left = Date.parse(left) || 0; right = Date.parse(right) || 0; return (left - right) * lootSort.direction; }
      return left.localeCompare(right, undefined, {numeric: true}) * lootSort.direction;
    }).forEach(row => body.appendChild(row));
  }));

  const dialog = document.querySelector("#endgame-dialog"), dialogTitle = document.querySelector("#dialog-title"), dialogContent = document.querySelector("#dialog-content"), dialogEyebrow = document.querySelector("#dialog-eyebrow");
  const auctionDetailDialog = document.querySelector("#auction-detail-dialog");
  const auctionDetailTitle = document.querySelector("#auction-detail-title");
  const auctionDetailContent = document.querySelector("#auction-detail-content");
  const openAuctionDetail = async auctionId => {
    let auction = auctionRecords.get(String(auctionId));
    if (!auction) {
      const response = await fetch("/api/endgame/auctions", {headers: {"Accept": "application/json"}});
      if (!response.ok) return;
      const payload = await response.json();
      auctionRecords = new Map(payload.auctions.map(entry => [String(entry.id), entry]));
      auction = auctionRecords.get(String(auctionId));
    }
    if (!auction || !auctionDetailDialog) return;
    const status = auction.status === "Confirmed" ? "Winners / DKP Completed" : auction.status;
    const members = window.ENDGAME_MEMBERS || [];
    const awardEditor = award => {
      const recipientOptions = members.map(member => `<option value="${member.id}" ${member.id === award.recipient_member_id ? "selected" : ""}>${safeText(member.name)}</option>`).join("");
      const jobOptions = (window.ENDGAME_JOBS || []).map(job => `<option ${job === award.job ? "selected" : ""}>${job}</option>`).join("");
      const priorityOptions = ["P1", "P2", "P3", "Freelot"].map(priority => `<option ${priority === award.distribution ? "selected" : ""}>${priority}</option>`).join("");
      return `<form class="auction-award-editor" method="post" action="/endgame/loot/${award.id}/update" data-auction-id="${auction.id}"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF)}"><input type="hidden" name="family" value="${safeText(award.family || "Other")}"><input type="hidden" name="classification" value="${safeText(award.classification || "Major Loot")}"><input type="hidden" name="return_to" value="bidding"><label>Item<input name="item" value="${safeText(award.item)}" required></label><label>Recipient<select name="member_id" required>${recipientOptions}</select></label><label>Job<select name="job" required>${jobOptions}</select></label><label>Priority<select name="distribution" required>${priorityOptions}</select></label><label>DKP<input type="number" name="dkp_cost" min="0" max="999" step="1" value="${Number(award.dkp_cost || 0)}" required></label><div><button class="button primary" type="submit">Save Award</button><button class="button danger" type="submit" formaction="/endgame/loot/${award.id}/delete">Remove &amp; Restore DKP</button></div></form>`;
    };
    const items = auction.items.map(item => {
      const bids = item.bids.length ? `<ul>${item.bids.map(bid => `<li><b>${safeText(bid.name)}</b> / ${safeText(bid.job)} / ${bid.amount} DKP / ${bid.tier === 4 ? "Freelot" : `P${bid.tier}`}</li>`).join("")}</ul>` : "<p>No bids were placed.</p>";
      const awards = item.awards?.length ? `<section class="auction-detail-awards"><h4>Confirmed awards</h4>${item.awards.map(award => window.ENDGAME_IS_ADMIN ? awardEditor(award) : `<p><b>${safeText(award.item)}</b> / ${safeText(award.recipient)} / ${award.dkp_cost} DKP</p>`).join("")}</section>` : "";
      return `<article class="auction-detail-item"><h3>${safeText(item.item)}</h3>${item.target_item && item.target_item !== item.item ? `<small>${safeText(item.target_item)}</small>` : ""}${bids}${awards}</article>`;
    }).join("");
    auctionDetailTitle.textContent = `Auction #${auction.id} / ${auction.boss}`;
    auctionDetailContent.innerHTML = `<p class="auction-detail-meta"><b>Event:</b> ${safeText(auction.event_name)} / ${safeText(auction.area)} / ${safeText(status)}</p><div class="auction-detail-items">${items}</div>`;
    if (!auctionDetailDialog.open) auctionDetailDialog.showModal();
  };
  document.querySelector(".auction-detail-close")?.addEventListener("click", () => auctionDetailDialog?.close());
  auctionDetailContent?.addEventListener("submit", async event => {
    const form = event.target.closest(".auction-award-editor");
    if (!form) return;
    event.preventDefault();
    const submitter = event.submitter;
    if (submitter?.formAction?.includes("/delete") && !confirm("Remove this award and restore its DKP to the recipient?")) return;
    const controls = [...form.querySelectorAll("button")];
    controls.forEach(button => { button.disabled = true; });
    try {
      const response = await fetch(submitter?.formAction || form.action, {
        method: "POST", body: new FormData(form), headers: {"Accept": "text/html"}, credentials: "same-origin",
      });
      if (!response.ok) throw new Error("The archived award could not be updated.");
      await loadAuctions();
      await openAuctionDetail(form.dataset.auctionId);
    } catch (error) {
      alert(error.message);
      controls.forEach(button => { button.disabled = false; });
    }
  });
  const eventStoreKey = "hokuten-event-overrides";
  const eventOverrides = JSON.parse(localStorage.getItem(eventStoreKey) || "{}");
  const eventState = button => {
    const date = button.dataset.openEvent;
    if (!eventOverrides[date]) {
      const index = Number(button.dataset.eventIndex);
      eventOverrides[date] = {
        attendees: roster.filter(member => member.attended > index).map(member => member.name),
        loot: loot.filter(row => row.date === date).map(row => ({...row})),
      };
    }
    return eventOverrides[date];
  };
  // Event and loot edits are persisted by the server.  Do not overwrite the
  // server-rendered Linkshell Loot table with the retired browser-only format.
  const syncEventChanges = () => {};
  const saveEventState = () => { localStorage.setItem(eventStoreKey, JSON.stringify(eventOverrides)); syncEventChanges(); };
  const memberOptions = selected => roster.map(member => `<option value="${safeText(member.name)}" ${member.name === selected ? "selected" : ""}>${safeText(member.name)}</option>`).join("");
  const jobOptions = selected => jobs.map(job => `<option value="${job}" ${job === selected ? "selected" : ""}>${job}</option>`).join("");
  const renderEventDetail = eventButton => {
    const date = eventButton.dataset.openEvent;
    const state = eventState(eventButton);
    const attendeeNames = new Set(state.attendees);
    const attendanceRows = window.ENDGAME_IS_ADMIN ? roster : roster.filter(member => attendeeNames.has(member.name));
    const attendanceContent = window.ENDGAME_IS_ADMIN
      ? attendanceRows.map(member => `<div class="event-admin-row"><label><input type="checkbox" data-event-attendee="${safeText(member.name)}" ${attendeeNames.has(member.name) ? "checked" : ""}><b>${safeText(member.name)}</b></label><span>${safeText(member.main_job || "Unassigned")}</span></div>`).join("")
      : attendanceRows.map(member => `<tr><td><b>${safeText(member.name)}</b></td><td>${safeText(member.main_job || "Unassigned")}</td><td><span class="attendance-mark">Attended</span></td></tr>`).join("");
    const lootContent = window.ENDGAME_IS_ADMIN
      ? state.loot.map((row, index) => `<div class="event-loot-editor" data-event-loot-row="${index}"><input name="item" value="${safeText(row.item)}" aria-label="Item"><select name="player" aria-label="Recipient">${memberOptions(row.player)}</select><select name="job" aria-label="Job">${jobOptions(row.job)}</select><select name="award" aria-label="Priority">${["P1","P2","P3","Freelot"].map(value => `<option ${priorityLabel(row.award) === value ? "selected" : ""}>${value}</option>`).join("")}</select><span><button type="button" data-save-event-loot="${index}">Save</button><button class="remove-event-loot" type="button" data-remove-event-loot="${index}">Remove</button></span></div>`).join("")
      : state.loot.map(row => `<tr><td class="event-loot-item"><b>${safeText(row.item)}</b><small>${safeText(row.family)} / ${row.major ? "Major Loot" : "Standard"}</small></td><td>${safeText(row.player)}</td><td><span class="job-badge main">${safeText(row.job)}</span></td><td>${safeText(row.award)}</td></tr>`).join("");
    dialogEyebrow.textContent = `${date} / Endgame event`;
    dialogTitle.textContent = eventButton.dataset.eventName;
    dialogContent.innerHTML = `<div class="event-detail-grid"><section class="event-detail-column"><header><h3>Attendance Roster</h3><span>${state.attendees.length} attended</span></header>${window.ENDGAME_IS_ADMIN ? '<p class="event-admin-note">Check or uncheck a member to update attendance.</p>' : ""}<div class="event-detail-scroll">${window.ENDGAME_IS_ADMIN ? attendanceContent : `<table class="event-detail-table"><thead><tr><th>Member</th><th>Main job</th><th>Status</th></tr></thead><tbody>${attendanceContent}</tbody></table>`}</div></section><section class="event-detail-column"><header><h3>Event Loot</h3><span>${state.loot.length} awards</span></header><div class="event-detail-scroll">${state.loot.length ? (window.ENDGAME_IS_ADMIN ? lootContent : `<table class="event-detail-table"><thead><tr><th>Item</th><th>Recipient</th><th>Job</th><th>Award</th></tr></thead><tbody>${lootContent}</tbody></table>`) : '<p class="event-empty">No loot was recorded for this event.</p>'}</div>${window.ENDGAME_IS_ADMIN ? `<form class="event-add-loot" id="event-add-loot"><input name="item" placeholder="Item name" required><select name="player">${memberOptions("")}</select><select name="job">${jobOptions("")}</select><select name="award"><option>Main priority</option><option>Secondary priority</option><option>Freelot</option></select><select name="major"><option value="major">Major</option><option value="normal">Standard</option></select><button type="submit">Add Drop</button></form>` : ""}</section></div>`;
    if (window.ENDGAME_IS_ADMIN) {
      dialogContent.querySelectorAll("[data-event-attendee]").forEach(control => control.addEventListener("change", () => {
        const name = control.dataset.eventAttendee;
        state.attendees = control.checked ? [...new Set([...state.attendees, name])] : state.attendees.filter(value => value !== name);
        saveEventState(); recordAdminChange("Event Attendance", control.checked ? "Member added" : "Member removed", `${name} / ${date}`); renderEventDetail(eventButton);
      }));
      dialogContent.querySelectorAll("[data-save-event-loot]").forEach(button => button.addEventListener("click", () => {
        const index = Number(button.dataset.saveEventLoot), editor = button.closest("[data-event-loot-row]"), previous = {...state.loot[index]};
        state.loot[index] = {...previous, item: editor.querySelector('[name="item"]').value.trim(), player: editor.querySelector('[name="player"]').value, job: editor.querySelector('[name="job"]').value, award: editor.querySelector('[name="award"]').value};
        saveEventState(); recordAdminChange("Event Loot", "Drop updated", `${previous.item} / ${previous.player} to ${state.loot[index].item} / ${state.loot[index].player} (${date})`); renderEventDetail(eventButton);
      }));
      dialogContent.querySelectorAll("[data-remove-event-loot]").forEach(button => button.addEventListener("click", () => {
        const removed = state.loot.splice(Number(button.dataset.removeEventLoot), 1)[0];
        saveEventState(); recordAdminChange("Event Loot", "Drop removed", `${removed.item} / ${removed.player} (${date})`); renderEventDetail(eventButton);
      }));
      dialogContent.querySelector("#event-add-loot").addEventListener("submit", submitEvent => {
        submitEvent.preventDefault(); const data = new FormData(submitEvent.currentTarget);
        const row = {date, item: data.get("item").trim(), player: data.get("player"), job: data.get("job"), award: data.get("award"), major: data.get("major") === "major", family: "Other"};
        state.loot.push(row); saveEventState(); recordAdminChange("Event Loot", "Drop added", `${row.item} / ${row.player} (${date})`); renderEventDetail(eventButton);
      });
    }
    dialog.classList.add("event-detail-dialog");
    if (!dialog.open) dialog.showModal();
  };
  syncEventChanges();
  dialog.addEventListener("close", () => dialog.classList.remove("event-detail-dialog", "member-history-dialog"));
  document.querySelector(".dialog-close").addEventListener("click", () => { dialog.close(); dialog.classList.remove("event-detail-dialog", "member-history-dialog"); });
  document.addEventListener("click", event => {
    const auctionLink = event.target.closest("[data-open-auction]");
    const memberCell = event.target.closest("#endgame-roster-body td:first-child");
    const eventHistoryLink = event.target.closest("[data-member-event-link]");
    const lootHistoryLink = event.target.closest("[data-member-loot-link]");
    const serverEventButton = event.target.closest("[data-open-server-event]");
    const attendanceEditButton = event.target.closest("[data-edit-attendance]");
    const eventButton = event.target.closest("[data-open-event]");
    const jobBadge = event.target.closest("[data-job-member]");
    const attendance = event.target.closest("[data-attendance]"); const wins = event.target.closest("[data-wins]");
    if (auctionLink) {
      event.preventDefault();
      openAuctionDetail(auctionLink.dataset.openAuction);
      return;
    }
    if (lootHistoryLink) {
      const eventId = lootHistoryLink.dataset.memberLootLink;
      dialog.close();
      document.querySelector(`[data-open-server-event="${eventId}"]`)?.click();
      return;
    }
    if (eventHistoryLink) {
      dialog.close();
      activateView("event-calendar");
      const card = document.querySelector(`#guild-event-${eventHistoryLink.dataset.memberEventLink}`);
      if (card) { card.open = true; card.scrollIntoView({behavior: "smooth", block: "start"}); }
      return;
    }
    if (memberCell) {
      const rosterMember = roster.find(row => row.name.toLowerCase() === memberCell.closest("tr").dataset.name);
      const member = rosterMember ? (window.ENDGAME_MEMBER_DETAILS || {})[String(rosterMember.id)] : null;
      if (!member) return;
      const eventRows = member.events.map(row => {
        const positive = row.is_upcoming ? row.signed_up : row.attended;
        const status = row.is_upcoming
          ? (row.signed_up ? "✓ Signed Up" : "✕ Not Signed Up")
          : (row.attended ? "✓ Attended" : "✕ Not Attended");
        return `<tr><td><button class="member-event-link" type="button" data-member-event-link="${row.id}">${safeText(row.start_at.slice(0,10))}<small>${safeText(row.name)}</small></button></td><td><span class="attendance-result ${positive ? "attended" : "missed"}">${status}</span></td></tr>`;
      }).join("");
      const lootRows = member.loot.map(row => `<tr><td><button class="member-loot-link" type="button" data-member-loot-link="${row.event_id}"><b>${safeText(row.item)}</b><small>${safeText(priorityLabel(row.award))}</small></button></td><td><button class="member-event-link" type="button" data-member-event-link="${row.event_id}">${safeText(row.event_date)}<small>${safeText(row.event_name)}</small></button>${row.auction_id ? `<button class="member-auction-link" type="button" data-open-auction="${row.auction_id}">Auction #${row.auction_id}</button>` : ""}</td><td>${Number(row.dkp_cost || 0)} DKP</td></tr>`).join("");
      dialogEyebrow.textContent = "Member event and award history";
      dialogTitle.textContent = member.name;
      const completedEvents = member.events.filter(row => !row.is_upcoming);
      const spentBreakdownRows = member.loot.map(row => `<tr><td><b>${safeText(row.item)}</b><small>${safeText(row.event_name)}</small></td><td>${Number(row.dkp_cost || 0)} DKP</td></tr>`).join("");
      const earnedBreakdownRows = (member.earned_events || []).map(row => `<tr><td>${safeText(row.date)}<small>${safeText(row.name)}</small></td><td>${Number(row.dkp || 0)} DKP</td></tr>`).join("");
      const dkpBreakdown = (label, value, heading, rows, emptyText) => `<div class="dkp-breakdown"><button class="dkp-breakdown-trigger" type="button" aria-label="${safeText(label)}: ${Number(value || 0)} DKP. Show breakdown">${safeText(label)} <b>${Number(value || 0)}</b><small>Hover for details</small></button><div class="dkp-breakdown-popover" role="tooltip"><strong>${safeText(heading)}</strong>${rows ? `<div class="dkp-breakdown-table-wrap"><table><tbody>${rows}</tbody></table></div>` : `<p>${safeText(emptyText)}</p>`}</div></div>`;
      const dynamisEligibility = Object.keys(member.dynamis_eligible_jobs || {}).length ? member.dynamis_eligible_jobs : (member.job_levels || {});
      const dynamisJobs = Object.entries(dynamisEligibility).filter(([, level]) => Number(level) >= 71).sort(([left], [right]) => left.localeCompare(right));
      const dynamisOptions = dynamisJobs.map(([job, level]) => `<option value="${safeText(job)}">${safeText(job)} · Lv.${Number(level)}</option>`).join("");
      const selectedDynamisOptions = current => dynamisOptions.replace(`value="${safeText(current)}"`, `value="${safeText(current)}" selected`);
      const dynamisEditor = window.ENDGAME_IS_ADMIN ? (dynamisJobs.length
        ? `<form class="member-dynamis-editor" method="post" action="/endgame/dynamis-lot-registrations/${member.id}"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF || "")}"><header><h3>Dynamis Lotting Jobs</h3><small>Officer override · one job is allowed</small></header><label>Main lot<select name="main_job"><option value="">Unassigned</option>${selectedDynamisOptions(member.dynamis_main)}</select></label><label>Secondary lot<select name="secondary_job"><option value="">Unassigned</option>${selectedDynamisOptions(member.dynamis_secondary)}</select></label><button class="button primary" type="submit">Save Dynamis Lots</button></form>`
        : `<section class="member-dynamis-editor"><header><h3>Dynamis Lotting Jobs</h3></header><p class="event-empty">No level 71+ Dynamis-eligible jobs are on this member's roster.</p></section>`) : "";
      const memberRemoval = window.ENDGAME_IS_ADMIN && member.name.toLowerCase() !== "imaven" && member.name !== window.ENDGAME_ACTOR
        ? `<form class="member-remove-form" method="post" action="/members/${member.id}/delete" onsubmit="return confirm('Remove this member and revoke website access? Their associated roster data will be deleted.');"><input type="hidden" name="csrf_token" value="${safeText(window.ENDGAME_CSRF || "")}"><button class="button danger" type="submit">Remove Member &amp; Revoke Access</button></form>` : "";
      dialogContent.innerHTML = `<div class="member-history-summary dkp-member-summary"><span>DKP balance <b>${member.dkp}</b></span>${dkpBreakdown("Total spent", member.total_spent, "Items purchased", spentBreakdownRows, "No DKP purchases recorded.")}${dkpBreakdown("Lifetime earned", member.lifetime_earned, "Events attended", earnedBreakdownRows, "No earned DKP recorded.")}<span>Last event <b>${safeText(member.last_event)}</b></span><span>Dynamis lots <b>${safeText(member.dynamis_main || "—")} / ${safeText(member.dynamis_secondary || "—")}</b></span></div><section class="member-history-section"><header><h3>Event Attendance</h3><span>${completedEvents.filter(row => row.attended).length}/${completedEvents.length} attended</span></header><div class="endgame-table-wrap"><table class="endgame-table member-history-table"><thead><tr><th>Event</th><th>Status</th></tr></thead><tbody>${eventRows}</tbody></table></div></section><section class="member-history-section"><header><h3>Loot Wins</h3><span>${member.loot.length} awards</span></header><div class="endgame-table-wrap">${lootRows ? `<table class="endgame-table member-history-table"><thead><tr><th>Item</th><th>Event</th><th>DKP spent</th></tr></thead><tbody>${lootRows}</tbody></table>` : '<p class="event-empty">No loot wins recorded.</p>'}</div></section>`;
      dialogContent.querySelector(".member-history-summary")?.insertAdjacentHTML("afterend", `${dynamisEditor}${memberRemoval}`);
      dialog.classList.add("member-history-dialog");
      dialog.showModal();
      return;
    }
    if (serverEventButton) {
      const selected = (window.ENDGAME_EVENTS || []).find(row => String(row.id) === serverEventButton.dataset.openServerEvent);
      if (!selected) return;
      const attendees = selected.attendees || [];
      const awards = selected.loot || [];
      const eventAuctions = selected.auctions || [];
      const auctionArchive = eventAuctions.length ? `<section class="event-auction-archive"><header><h3>Event Auctions</h3><span>${eventAuctions.length} auction${eventAuctions.length === 1 ? "" : "s"}</span></header>${eventAuctions.map(auction => `<button class="event-auction-link ${auction.status === "Confirmed" ? "completed" : ""}" type="button" data-open-auction="${auction.id}"><b>Auction #${auction.id} / ${safeText(auction.boss)}</b><span>${safeText(auction.area)} · ${safeText(auction.status === "Confirmed" ? "Winners / DKP Completed" : auction.status)}${auction.award_count ? ` · ${auction.award_count} awards` : ""}</span></button>`).join("")}</section>` : "";
      const allMembers = window.ENDGAME_MEMBERS || [];
      const lootCatalog = window.ENDGAME_LOOT_CATALOG || [];
      const lootOptions = `<option value="">Select Sky or Sea item</option>${lootCatalog.map(item => `<option value="${safeText(item.name)}" data-family="${safeText(item.family)}">${safeText(item.area)} · ${safeText(item.source)} · ${safeText(item.name)}</option>`).join("")}`;
      const csrf = safeText(document.querySelector('input[name="csrf_token"]')?.value || window.ENDGAME_CSRF || "");
      const lootPanel = window.ENDGAME_IS_ADMIN
        ? awards.map(row => `<form method="post" action="/endgame/loot/${row.id}/update" class="event-loot-persistent-editor"><input type="hidden" name="csrf_token" value="${csrf}"><input type="hidden" name="family" value="${safeText(row.family || "Other")}"><input type="hidden" name="classification" value="Major Loot"><input name="item" value="${safeText(row.item)}" aria-label="Item"><select name="member_id" aria-label="Recipient">${allMembers.map(member => `<option value="${member.id}" ${member.name === row.player ? "selected" : ""}>${safeText(member.name)}</option>`).join("")}</select><select name="job" aria-label="Receiving job">${jobs.map(job => `<option ${job === row.job ? "selected" : ""}>${job}</option>`).join("")}</select><select name="distribution" aria-label="Priority">${["P1","P2","P3","Freelot"].map(value => `<option ${priorityLabel(row.award) === value ? "selected" : ""}>${value}</option>`).join("")}</select><input type="number" name="dkp_cost" min="0" max="999" step="1" value="${Number(row.dkp_cost || 0)}" aria-label="DKP spent"><div><button type="submit">Save</button><button class="danger" type="submit" formaction="/endgame/loot/${row.id}/delete">Remove &amp; Restore DKP</button></div></form>`).join("") || '<p class="event-empty">No loot was recorded for this event.</p>'
        : awards.length ? `<table class="event-detail-table"><thead><tr><th>Item</th><th>Recipient</th><th>Job</th><th>Priority</th><th>DKP</th></tr></thead><tbody>${awards.map(row => `<tr><td class="event-loot-item"><b>${safeText(row.item)}</b></td><td>${safeText(row.player)}</td><td><span class="job-badge main">${safeText(row.job)}</span></td><td>${safeText(priorityLabel(row.award))}</td><td>${Number(row.dkp_cost || 0)}</td></tr>`).join("")}</tbody></table>` : '<p class="event-empty">No loot was recorded for this event.</p>';
      const manualLootForm = window.ENDGAME_IS_ADMIN ? `<form method="post" action="/endgame/loot" class="event-add-loot persistent-event-add"><input type="hidden" name="csrf_token" value="${csrf}"><input type="hidden" name="event_id" value="${selected.id}"><input type="hidden" name="classification" value="Major Loot"><h4>Add Loot Drop</h4><select name="item" required>${lootOptions}</select><select name="member_id" required><option value="">Recipient</option>${allMembers.map(member => `<option value="${member.id}">${safeText(member.name)}</option>`).join("")}</select><select name="job" required><option value="">Job</option>${jobs.map(job => `<option>${job}</option>`).join("")}</select><select name="distribution"><option>P1</option><option>P2</option><option>P3</option><option selected>Freelot</option></select><input type="number" name="dkp_cost" min="0" max="999" step="1" value="0" aria-label="DKP spent"><button class="button primary" type="submit">Add Loot Drop</button></form>` : "";
      dialogEyebrow.textContent = `${selected.start_at.slice(0, 10)} / Endgame event`;
      dialogTitle.textContent = `${selected.name} / Loot`;
      dialogContent.innerHTML = `<section class="event-detail-column event-loot-only"><header><h3>Event Loot</h3><span>${awards.length} awards</span></header><div class="event-detail-scroll">${lootPanel}</div>${manualLootForm}</section>`;
      dialogContent.insertAdjacentHTML("beforeend", auctionArchive);
      dialog.classList.add("event-detail-dialog");
      dialog.showModal();
      return;
    }
    if (attendanceEditButton && window.ENDGAME_IS_ADMIN) {
      const selected = (window.ENDGAME_EVENTS || []).find(row => String(row.id) === attendanceEditButton.dataset.editAttendance);
      if (!selected) return;
      const attendeeIds = new Set((selected.attendees || []).map(member => Number(member.id)));
      const allMembers = window.ENDGAME_MEMBERS || [];
      const csrf = safeText(document.querySelector('input[name="csrf_token"]')?.value || window.ENDGAME_CSRF || "");
      dialogEyebrow.textContent = `${selected.start_at.slice(0, 10)} / Administrator attendance`;
      dialogTitle.textContent = `${selected.name} / Attendance`;
      dialogContent.innerHTML = `<form method="post" action="/endgame/events/${selected.id}/attendance" class="event-attendance-editor"><input type="hidden" name="csrf_token" value="${csrf}"><div class="event-attendance-checks">${allMembers.map(member => `<label><input type="checkbox" name="member_ids" value="${member.id}" ${attendeeIds.has(Number(member.id)) ? "checked" : ""}><span>${safeText(member.name)}</span></label>`).join("")}</div><div class="attendance-editor-actions"><button class="button primary" type="submit">Save Attendance</button><button class="button edit-attendance-button" type="button" data-cancel-attendance>Cancel</button></div></form>`;
      dialogContent.querySelector("[data-cancel-attendance]").addEventListener("click", () => dialog.close());
      dialog.showModal();
      return;
    }
    if (eventButton) { renderEventDetail(eventButton); return; }
    if (eventButton) {
      const eventIndex = Number(eventButton.dataset.eventIndex);
      const attendees = roster.filter(member => member.attended > eventIndex);
      const eventLoot = loot.filter(row => row.date === eventButton.dataset.openEvent);
      dialogEyebrow.textContent = `${eventButton.dataset.openEvent} / Endgame event`;
      dialogTitle.textContent = eventButton.dataset.eventName;
      dialogContent.innerHTML = `<div class="event-detail-grid"><section class="event-detail-column"><header><h3>Attendance Roster</h3><span>${attendees.length} attended</span></header><div class="event-detail-scroll"><table class="event-detail-table"><thead><tr><th>Member</th><th>Main job</th><th>Status</th></tr></thead><tbody>${attendees.map(member => `<tr><td><b>${member.name}</b></td><td>${member.main_job || "Unassigned"}</td><td><span class="attendance-mark">Attended</span></td></tr>`).join("")}</tbody></table></div></section><section class="event-detail-column"><header><h3>Event Loot</h3><span>${eventLoot.length} awards</span></header><div class="event-detail-scroll">${eventLoot.length ? `<table class="event-detail-table"><thead><tr><th>Item</th><th>Recipient</th><th>Job</th><th>Award</th></tr></thead><tbody>${eventLoot.map(row => `<tr><td class="event-loot-item"><b>${row.item}</b><small>${row.family} / ${row.major ? "Major Loot" : "Standard"}</small></td><td>${row.player}</td><td><span class="job-badge main">${row.job}</span></td><td>${row.award}</td></tr>`).join("")}</tbody></table>` : '<p class="event-empty">No loot was recorded for this event.</p>'}</div></section></div>`;
      dialog.classList.add("event-detail-dialog");
      dialog.showModal();
    }
    if (jobBadge && window.ENDGAME_IS_ADMIN) {
      const member = roster.find(row => row.name === jobBadge.dataset.jobMember);
      const slot = jobBadge.dataset.jobSlot;
      const slotLabel = slot === "main_job" ? "Main Job" : "Secondary Job";
      dialogEyebrow.textContent = "Administrator job registration";
      dialogTitle.textContent = `${member.name} / ${slotLabel}`;
      dialogContent.innerHTML = `<form class="job-change-form" id="job-change-form"><p class="job-change-help">Saving this selection adds a timestamped entry to the badge's hover history.</p><label>${slotLabel}<select name="job"><option value="">Unassigned</option>${jobs.map(job => `<option value="${job}" ${job === member[slot] ? "selected" : ""}>${job}</option>`).join("")}</select></label><button type="submit">Save Job Change</button></form>`;
      dialogContent.querySelector("form").addEventListener("submit", submitEvent => {
        submitEvent.preventDefault();
        const nextJob = new FormData(submitEvent.currentTarget).get("job");
        const otherSlot = slot === "main_job" ? "secondary_job" : "main_job";
        if (nextJob && nextJob === member[otherSlot]) {
          dialogContent.querySelector(".job-change-help").textContent = `${nextJob} is already registered in the other priority slot.`;
          return;
        }
        const previousJob = member[slot] || "";
        if (nextJob === previousJob) { dialog.close(); return; }
        const entry = {member: member.name, slot, from: previousJob, to: nextJob, at: new Date().toLocaleString(), actor: window.ENDGAME_ACTOR || "Administrator"};
        jobChanges.push(entry);
        localStorage.setItem(jobChangeKey, JSON.stringify(jobChanges));
        recordAdminChange("Job Selections", `${slotLabel} changed`, `${member.name}: ${previousJob || "Unassigned"} to ${nextJob || "Unassigned"}`);
        updateJobDisplay(member.name, slot, nextJob);
        rankMatrixPriority();
        filterRoster();
        dialog.close();
      });
      dialog.showModal();
    }
    if (attendance) { const member = roster.find(row => row.name === attendance.dataset.attendance); dialogEyebrow.textContent = "Rolling attendance detail"; dialogTitle.textContent = member.name; dialogContent.innerHTML = `<div class="dialog-list"><article><div><b>Imported Event 02</b><small>Individual event detail pending import</small></div><span>${member.attended === 2 ? "Attended" : "Review"}</span></article><article><div><b>Imported Event 01</b><small>Individual event detail pending import</small></div><span>${member.attended ? "Attended / review" : "Missed"}</span></article></div>`; dialog.showModal(); }
    if (wins) { const rows = loot.filter(row => row.player === wins.dataset.wins); dialogEyebrow.textContent = "Loot history"; dialogTitle.textContent = wins.dataset.wins; dialogContent.innerHTML = rows.length ? `<div class="dialog-list">${rows.map(row => `<article><div><b>${row.item}</b><small>${row.date} · ${row.job} · ${row.award}</small></div><span>${row.major ? "Major" : "Standard"}</span></article>`).join("")}</div>` : "<p>No awards are recorded for this member.</p>"; dialog.showModal(); }
  });

  const priorityMatrixDialog = document.querySelector("#priority-matrix-dialog");
  document.querySelector("#open-priority-matrix")?.addEventListener("click", () => priorityMatrixDialog.showModal());
  priorityMatrixDialog?.querySelector(".priority-dialog-close")?.addEventListener("click", () => priorityMatrixDialog.close());
  priorityMatrixDialog?.addEventListener("click", event => {
    if (event.target === priorityMatrixDialog) priorityMatrixDialog.close();
  });

  const recordLootDialog = document.querySelector("#record-loot-dialog");
  const recordLootItem = document.querySelector("#record-loot-item");
  const recordLootMember = document.querySelector("#record-loot-member");
  const recordLootJob = document.querySelector("#record-loot-job");
  const updateLootDefaults = () => {
    if (!recordLootDialog) return;
    document.querySelector("#record-loot-family").value = recordLootItem.selectedOptions[0]?.dataset.family || "";
    const member = roster.find(row => String(row.id) === recordLootMember.value);
    const job = recordLootJob.value;
    document.querySelector("#record-loot-distribution").value = member && job === member.main_job
      ? "Main priority"
      : member && job === member.secondary_job ? "Secondary priority" : "Freelot";
  };
  document.querySelector("#open-record-loot")?.addEventListener("click", () => recordLootDialog.showModal());
  recordLootDialog?.querySelector(".record-loot-close")?.addEventListener("click", () => recordLootDialog.close());
  [recordLootItem, recordLootMember, recordLootJob].filter(Boolean).forEach(control => control.addEventListener("change", updateLootDefaults));

  if (false) { // Linkshell Pops now runs in its own isolated script below the dashboard.
  let popArea = "Sky";
  const popItems = window.POP_ITEMS || [], popTargets = window.POP_TARGETS || [];
  let saved = {};
  const holder = document.querySelector("#pop-holder");
  const quantity = (name, key) => Number(saved[name]?.[key] || 0);
  const totals = () => Object.keys(saved).reduce((result, name) => { Object.entries(saved[name]).forEach(([key, value]) => result[key] = (result[key] || 0) + Number(value)); return result; }, {});
  const renderPops = () => {
    const aggregate = totals(), areaItems = popItems.filter(item => item.area === popArea);
    document.querySelector("#pop-inventory").innerHTML = areaItems.map(item => { const owners = Object.keys(saved).filter(name => quantity(name, item.key) > 0); return `<article class="pop-item"><div><b>${item.name}</b><small>${item.source}${item.bundle ? ` · ${item.bundle} required per pop` : ""}</small></div><div class="quantity-stepper"><button data-pop-change="-1" data-key="${item.key}">−</button><b>${quantity(holder.value,item.key)}</b><button data-pop-change="1" data-key="${item.key}">+</button></div><span class="holder-list">Linkshell total: <b>${aggregate[item.key] || 0}</b>${owners.length ? ` · Held by ${owners.join(", ")}` : " · No recorded holders"}</span></article>`; }).join("");
    const targets = popTargets.filter(target => target.area === popArea); let ready = 0;
    document.querySelector("#pop-readiness").innerHTML = targets.map(target => { const requirements = target.requires.map(raw => { const [key, amountRaw] = raw.split(":"); const amount = Number(amountRaw || 1), held = aggregate[key] || 0; return {key, amount, held, met: held >= amount, item: popItems.find(item => item.key === key)}; }); const complete = requirements.every(req => req.met); if (complete) ready += 1; const sets = Math.min(...requirements.map(req => Math.floor(req.held / req.amount))); return `<article class="pop-target ${complete ? "ready" : "partial"}"><header><h4>${target.name}</h4><span class="readiness-badge">${complete ? `${sets} pop${sets === 1 ? "" : "s"} ready` : "Components needed"}</span></header><div class="requirement-list">${requirements.map(req => `<span class="${req.met ? "have" : ""}">${req.item.name} ${req.held}/${req.amount}</span>`).join("")}</div></article>`; }).join("");
    document.querySelector("#pop-component-count").textContent = `${areaItems.reduce((sum,item) => sum + (aggregate[item.key] || 0),0)} components held`; document.querySelector("#pop-ready-count").textContent = `${ready} ready`;
  };
  document.querySelectorAll("[data-pop-area]").forEach(button => button.addEventListener("click", () => { popArea = button.dataset.popArea; document.querySelectorAll("[data-pop-area]").forEach(row => row.classList.toggle("active", row === button)); renderPops(); }));
  holder.addEventListener("change", renderPops);
  const loadPops = async () => {
    try {
      const response = await fetch("/api/endgame/pops", {headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error();
      saved = (await response.json()).inventory || {};
    } catch (_) { saved = {}; }
    renderPops();
  };
  document.querySelector("#pop-inventory").addEventListener("click", async event => {
    const button = event.target.closest("[data-pop-change]");
    if (!button) return;
    button.disabled = true;
    try {
      const response = await fetch("/api/endgame/pops", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": window.ENDGAME_CSRF},
        body: JSON.stringify({holder: holder.value, item_key: button.dataset.key, delta: Number(button.dataset.popChange)}),
      });
      if (!response.ok) throw new Error("Could not save the pop inventory update.");
      saved = (await response.json()).inventory || {};
      renderPops();
    } catch (error) { alert(error.message); button.disabled = false; }
  });
  // Render the complete Sky list immediately; shared quantities hydrate right after.
  // This keeps all pop requirements usable even if the inventory request is delayed.
  renderPops();
  loadPops();
  }
})();
