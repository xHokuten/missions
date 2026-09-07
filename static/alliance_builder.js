(() => {
  const roster = window.ALLIANCE_ROSTER || [],
    roles = window.ALLIANCE_ROLES || {},
    guildEvents = window.ALLIANCE_GUILD_EVENTS || [],
    live = window.ALLIANCE_LIVE || {};
  const byId = new Map(roster.map((member) => [String(member.id), member]));
  const list = document.querySelector("#available-roster");
  if (!list) return;
  const controls = {
    search: document.querySelector("#alliance-character-search"),
    job: document.querySelector("#alliance-job"),
    role: document.querySelector("#alliance-role"),
    status: document.querySelector("#alliance-rsvp-status"),
    assignment: document.querySelector("#alliance-assignment"),
  };
  const slots = [...document.querySelectorAll(".party-slot")],
    targetMessage = document.querySelector("#selected-slot-message"),
    duplicateToggle = document.querySelector("#allow-alliance-duplicates");
  const customDialog = document.querySelector("#custom-alliance-dialog"),
    customForm = document.querySelector("#custom-alliance-form"),
    customName = document.querySelector("#custom-character-name"),
    customJob = document.querySelector("#custom-character-job");
  let selectedSlot = null,
    selectedMemberSlot = null,
    customTarget = null,
    dragged = null,
    liveVersion = Number(live.version || 0),
    suppressLiveSave = false,
    liveSaving = false,
    liveSaveTimer = null,
    lastLocalChange = 0;
  const occupied = (slot) =>
    Boolean(slot.dataset.member || slot.dataset.customName);
  const allianceFor = (slot) => (Number(slot.dataset.party) <= 3 ? 1 : 2);
  const memberAlliances = (memberId) =>
    new Set(
      slots
        .filter((slot) => slot.dataset.member === String(memberId))
        .map(allianceFor),
    );
  const canPlaceMember = (memberId, slot) => {
    const groups = memberAlliances(memberId),
      targetAlliance = allianceFor(slot);
    return (
      !groups.has(targetAlliance) &&
      (!groups.size ||
        (duplicateToggle?.checked && targetAlliance === 2 && groups.has(1)))
    );
  };
  const eligibleJobs = (member, preferred = "") => {
    const wanted = controls.job.value,
      roleJobs = roles[controls.role.value] || [];
    return Object.entries(member.jobs)
      .filter(
        ([job, level]) =>
          level === 75 &&
          (!wanted || job === wanted) &&
          (!roleJobs.length || roleJobs.includes(job)),
      )
      .sort((a, b) =>
        a[0] === preferred
          ? -1
          : b[0] === preferred
            ? 1
            : a[0].localeCompare(b[0]),
      );
  };
  const chooseSlot = (slot) => {
    if (occupied(slot)) return;
    selectedSlot = slot;
    selectedMemberSlot = null;
    slots.forEach((item) => {
      item.classList.toggle("selected-target", item === slot);
      item.classList.remove("selected-member");
    });
    targetMessage.textContent = `Target: Party ${slot.dataset.party}, Slot ${slot.dataset.slot}. Choose, drag, or add a custom character.`;
    targetMessage.classList.add("has-target");
  };
  const selectMember = (slot) => {
    selectedMemberSlot = selectedMemberSlot === slot ? null : slot;
    clearTarget();
    slots.forEach((item) =>
      item.classList.toggle("selected-member", item === selectedMemberSlot),
    );
    if (selectedMemberSlot) {
      const member = byId.get(slot.dataset.member),
        name = member?.name || slot.dataset.customName;
      targetMessage.textContent = `Selected party member: ${slot.dataset.job} - ${name}.`;
      targetMessage.classList.add("has-target");
    } else {
      targetMessage.textContent = "Party member selection cleared.";
      targetMessage.classList.remove("has-target");
    }
  };
  let scheduleLiveSave = () => {};
  const setSlot = (
    slot,
    memberId = "",
    job = "",
    name = "",
    attribution = null,
  ) => {
    slot.dataset.member = String(memberId);
    slot.dataset.customName = name;
    slot.dataset.job = job;
    slot.querySelector('input[name^="member_"]').value = memberId;
    slot.querySelector('input[name^="custom_name_"]').value = name;
    slot.querySelector('input[name^="job_"]').value = job;
    if (attribution) {
      slot.dataset.updatedBy = String(attribution.updated_by || "");
      slot.dataset.updatedByName = attribution.updated_by_name || "";
      slot.dataset.updatedAt = attribution.updated_at || "";
    } else if (!suppressLiveSave) {
      slot.dataset.updatedBy = "";
      slot.dataset.updatedByName = "";
      slot.dataset.updatedAt = "";
    }
    if (live.enabled && !suppressLiveSave) {
      lastLocalChange = Date.now();
      scheduleLiveSave();
    }
  };
  const clearTarget = () => {
    selectedSlot = null;
    slots.forEach((item) => item.classList.remove("selected-target"));
  };
  const assignMember = (member, job, target = selectedSlot) => {
    const groups = memberAlliances(member.id),
      preferred =
        target && !occupied(target) && canPlaceMember(member.id, target)
          ? target
          : null,
      slot =
        preferred ||
        (duplicateToggle?.checked && groups.has(1)
          ? slots.find(
              (item) =>
                allianceFor(item) === 2 &&
                !occupied(item) &&
                canPlaceMember(member.id, item),
            )
          : slots.find(
              (item) => !occupied(item) && canPlaceMember(member.id, item),
            ));
    if (!slot) {
      targetMessage.hidden = false;
      targetMessage.textContent = `${member.name} is already assigned to that alliance, or no eligible slot is open.`;
      targetMessage.classList.add("has-target");
      return;
    }
    setSlot(slot, member.id, job);
    if (Number(slot.dataset.party) > 3) {
      const second = document.querySelector("#second-alliance");
      if (second) second.open = true;
    }
    clearTarget();
    targetMessage.textContent = `Added ${job} - ${member.name}.`;
    targetMessage.classList.remove("has-target");
    refresh();
  };
  const openCustom = (slot) => {
    customTarget = slot;
    customName.value = "";
    customJob.value = controls.job.value || customJob.options[0].value;
    customDialog.showModal();
    setTimeout(() => customName.focus(), 0);
  };
  const startRosterDrag = (event, member, job) => {
    dragged = {
      memberId: String(member.id),
      customName: "",
      job,
      source: null,
    };
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", `${member.id}:${job}`);
  };
  const renderRoster = () => {
    const query = controls.search.value.trim().toLowerCase(),
      eventId = document.querySelector("#alliance-guild-event")?.value,
      event = guildEvents.find((item) => String(item.id) === eventId),
      details = event?.signup_details || {},
      statusFilter = controls.status.value,
      assignmentFilter = controls.assignment.value;
    const matches = roster.filter((member) => {
      const signup = details[String(member.id)] || {},
        status = signup.status || "none",
        isAssigned = memberAlliances(member.id).size > 0;
      return (
        (!query || member.name.toLowerCase().includes(query)) &&
        (!statusFilter || status === statusFilter) &&
        (!assignmentFilter ||
          (assignmentFilter === "assigned") === isAssigned) &&
        eligibleJobs(member, signup.job).length
      );
    });
    document.querySelector("#available-count").textContent =
      `${matches.length} matching${event ? " event roster" : ""}`;
    list.replaceChildren(
      ...matches.map((member) => {
        const signup = details[String(member.id)] || {},
          jobsForMember = eligibleJobs(member, signup.job),
          groups = memberAlliances(member.id),
          canDuplicate =
            duplicateToggle?.checked && groups.has(1) && !groups.has(2),
          row = document.createElement("tr");
        row.draggable = !groups.size || canDuplicate;
        row.classList.toggle("rsvp-maybe", signup.status === "maybe");
        row.classList.toggle("duplicate-candidate", canDuplicate);
        row.title = canDuplicate
          ? `${member.name} can also be added to Alliance 2`
          : `Drag ${member.name} using ${jobsForMember[0][0]}`;
        if (row.draggable)
          row.addEventListener("dragstart", (event) =>
            startRosterDrag(event, member, jobsForMember[0][0]),
          );
        const identity = document.createElement("td"),
          name = document.createElement("b"),
          meta = document.createElement("small");
        name.textContent = member.name;
        meta.textContent = signup.status
          ? `${signup.status === "maybe" ? "Maybe" : "Going"}${signup.job ? ` · Signed up as ${signup.job}` : ""}`
          : event
            ? "No RSVP - available roster jobs below"
            : `${jobsForMember.length} level-75 job${jobsForMember.length === 1 ? "" : "s"}`;
        identity.append(name, meta);
        const jobs = document.createElement("td"),
          jobList = document.createElement("div");
        jobList.className = "available-jobs";
        jobsForMember.forEach(([job, level]) => {
          const button = document.createElement("button"),
            selected = job === signup.job,
            canAdd = !groups.size || canDuplicate;
          button.type = "button";
          button.disabled = !canAdd;
          button.className = `available-job${selected ? " discord-selected-job" : ""}`;
          button.draggable = canAdd;
          button.title = canAdd
            ? selected
              ? `${member.name} signed up as ${job}`
              : `Add ${member.name} as ${job}`
            : `${member.name} is already assigned`;
          button.innerHTML = `<svg viewBox="0 0 24 24"><use href="/static/job-icons.svg#${job.toLowerCase()}"></use></svg><b>${job}</b><span>${level}</span>${selected ? "<i>Signed up</i>" : ""}`;
          if (canAdd) {
            button.addEventListener("click", () => assignMember(member, job));
            button.addEventListener("dragstart", (event) => {
              event.stopPropagation();
              startRosterDrag(event, member, job);
            });
          }
          jobList.append(button);
        });
        jobs.append(jobList);
        row.append(identity, jobs);
        return row;
      }),
    );
    if (!matches.length) {
      const row = document.createElement("tr"),
        cell = document.createElement("td");
      cell.colSpan = 2;
      cell.className = "available-empty";
      cell.textContent = "No characters match the selected filters.";
      row.append(cell);
      list.append(row);
    }
  };
  const editorColors = [
    "#f0c84b",
    "#a77cff",
    "#55b7ff",
    "#ff7185",
    "#56d6a2",
    "#ef8b45",
    "#e56ee8",
    "#7bd45a",
  ];
  const renderSlot = (slot) => {
    const member = byId.get(slot.dataset.member),
      name = member?.name || slot.dataset.customName,
      job = slot.dataset.job,
      content = slot.querySelector(".slot-content"),
      editorId = Number(slot.dataset.updatedBy || 0),
      editorName = slot.dataset.updatedByName || "",
      editorColor = editorColors[Math.abs(editorId) % editorColors.length];
    slot.classList.toggle("filled", !!name);
    slot.classList.toggle("live-attributed", !!name && !!editorName);
    slot.style.setProperty("--editor-color", editorColor);
    slot.draggable = !!name;
    slot.setAttribute(
      "aria-label",
      name
        ? `${job} - ${name}`
        : `Party ${slot.dataset.party}, slot ${slot.dataset.slot}, open`,
    );
    slot.title =
      name && editorName
        ? `${job} - ${name}\nLast changed by ${editorName}${slot.dataset.updatedAt ? ` · ${slot.dataset.updatedAt}` : ""}`
        : "";
    if (!name) {
      content.innerHTML =
        '<b>Open slot</b><button class="add-custom-slot" type="button" aria-label="Add a custom character" title="Add custom character">+</button>';
      content.querySelector("button").addEventListener("click", (event) => {
        event.stopPropagation();
        openCustom(slot);
      });
      return;
    }
    content.replaceChildren();
    const assignment = document.createElement("b");
    assignment.className = "simple-assignment";
    assignment.textContent = `${job} - ${name}`;
    if (editorName) {
      const editor = document.createElement("small");
      editor.className = "slot-editor";
      editor.textContent = `by ${editorName}`;
      assignment.append(editor);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-assignment";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remove ${name}`);
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      setSlot(slot);
      chooseSlot(slot);
      refresh();
    });
    content.append(assignment, remove);
  };
  const refresh = () => {
    const duplicateMembers = new Set(
      roster
        .filter((member) => memberAlliances(member.id).size > 1)
        .map((member) => String(member.id)),
    );
    slots.forEach((slot) =>
      slot.classList.toggle(
        "cross-alliance-duplicate",
        duplicateMembers.has(slot.dataset.member),
      ),
    );
    slots.forEach(renderSlot);
    document
      .querySelectorAll(".alliance-party")
      .forEach(
        (party) =>
          (party.querySelector(".party-count").textContent =
            `${party.querySelectorAll(".party-slot.filled").length}/6`),
      );
    document.querySelector("#alliance-total").textContent =
      `${slots.filter(occupied).length}/${slots.length} assigned`;
    renderRoster();
  };
  slots.forEach((slot) => {
    slot.addEventListener("click", () =>
      occupied(slot) ? selectMember(slot) : chooseSlot(slot),
    );
    slot.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        occupied(slot) ? selectMember(slot) : chooseSlot(slot);
      }
    });
    slot.addEventListener("dragstart", (event) => {
      if (!occupied(slot)) return;
      dragged = {
        memberId: slot.dataset.member,
        customName: slot.dataset.customName,
        job: slot.dataset.job,
        source: slot,
      };
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData(
        "text/plain",
        `${slot.dataset.member || slot.dataset.customName}:${slot.dataset.job}`,
      );
      slot.classList.add("dragging");
    });
    slot.addEventListener("dragend", () => {
      slot.classList.remove("dragging");
      slots.forEach((item) => item.classList.remove("drag-over"));
      dragged = null;
    });
    slot.addEventListener("dragover", (event) => {
      if (dragged && (!occupied(slot) || dragged.source)) {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        slot.classList.add("drag-over");
      }
    });
    slot.addEventListener("dragleave", () =>
      slot.classList.remove("drag-over"),
    );
    slot.addEventListener("drop", (event) => {
      event.preventDefault();
      slot.classList.remove("drag-over");
      if (!dragged) return;
      if (dragged.source) {
        if (dragged.source === slot) return;
        const target = {
          memberId: slot.dataset.member,
          customName: slot.dataset.customName,
          job: slot.dataset.job,
        };
        setSlot(slot, dragged.memberId, dragged.job, dragged.customName);
        setSlot(dragged.source, target.memberId, target.job, target.customName);
      } else if (
        !occupied(slot) &&
        (!dragged.memberId || canPlaceMember(dragged.memberId, slot))
      ) {
        setSlot(slot, dragged.memberId, dragged.job);
      } else {
        return;
      }
      clearTarget();
      targetMessage.textContent = `Placed ${dragged.job} - ${byId.get(dragged.memberId)?.name || dragged.customName}.`;
      targetMessage.classList.remove("has-target");
      refresh();
    });
  });
  controls.job.addEventListener("change", renderRoster);
  controls.role.addEventListener("change", renderRoster);
  controls.status.addEventListener("change", renderRoster);
  controls.assignment.addEventListener("change", renderRoster);
  controls.search.addEventListener("input", renderRoster);
  duplicateToggle?.addEventListener("change", () => {
    const hasDuplicates = roster.some(
      (member) => memberAlliances(member.id).size > 1,
    );
    if (!duplicateToggle.checked && hasDuplicates) {
      duplicateToggle.checked = true;
      alert(
        "Remove members who appear in both alliances before turning duplicate assignments off.",
      );
      return;
    }
    if (duplicateToggle.checked) controls.assignment.value = "";
    refresh();
    if (live.enabled) {
      lastLocalChange = Date.now();
      scheduleLiveSave();
    }
  });
  customForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = customName.value.trim();
    if (!name || !customTarget) return;
    setSlot(customTarget, "", customJob.value, name);
    customDialog.close();
    clearTarget();
    targetMessage.textContent = `Added ${customJob.value} - ${name}.`;
    targetMessage.classList.remove("has-target");
    refresh();
  });
  document
    .querySelector("#close-custom-alliance")
    .addEventListener("click", () => customDialog.close());
  document
    .querySelector("#cancel-custom-alliance")
    .addEventListener("click", () => customDialog.close());
  customDialog.addEventListener("close", () => {
    customTarget = null;
  });
  const dialog = document.querySelector("#saved-alliance-dialog");
  document
    .querySelector("#open-saved-alliances")
    .addEventListener("click", () => dialog.showModal());
  document
    .querySelector("#close-saved-alliances")
    .addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  document
    .querySelector("#add-second-alliance")
    ?.addEventListener("click", () => {
      const second = document.querySelector("#second-alliance");
      if (!second) return;
      second.open = true;
      second.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  const dateInput = document.querySelector(".native-date-input"),
    dateDisplay = document.querySelector("#event-date-display");
  document
    .querySelector("#pick-event-date")
    .addEventListener("click", () => window.openQuarterHourPicker(dateInput));
  dateInput.addEventListener("change", () => {
    if (dateInput.value) {
      const [date, time] = dateInput.value.split("T"),
        [hour, minute] = time.split(":").map(Number),
        rounded = Math.min(1425, Math.round((hour * 60 + minute) / 15) * 15);
      dateInput.value = `${date}T${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
    }
    dateDisplay.textContent = dateInput.value
      ? dateInput.value.replace("T", " at ")
      : "Choose date and time";
  });
  const guildEvent = document.querySelector("#alliance-guild-event");
  guildEvent?.addEventListener("change", () => {
    const option = guildEvent.selectedOptions[0];
    if (option?.value) {
      document.querySelector("#alliance-form").elements.name.value =
        option.dataset.name || "";
      dateInput.value = option.dataset.start || "";
      dateDisplay.textContent = dateInput.value
        ? dateInput.value.replace("T", " at ")
        : "Choose date and time";
      document
        .querySelector("#alliance-form")
        .elements.name.dispatchEvent(new Event("input"));
    }
    renderRoster();
  });
  const liveIndicator = document.querySelector("#alliance-live-indicator"),
    activeEditors = document.querySelector("#alliance-active-editors"),
    liveUrl = live.enabled
      ? `/alliance-builder/shared/${encodeURIComponent(live.token)}/live`
      : "";
  const renderPresence = (editors) => {
    if (!activeEditors) return;
    activeEditors.replaceChildren(
      ...editors.map((editor) => {
        const chip = document.createElement("span");
        chip.style.setProperty(
          "--editor-color",
          editorColors[
            Math.abs(Number(editor.member_id)) % editorColors.length
          ],
        );
        chip.textContent = editor.name;
        chip.title = `${editor.name} is viewing this alliance`;
        return chip;
      }),
    );
  };
  const applyLiveState = (data) => {
    suppressLiveSave = true;
    if (duplicateToggle)
      duplicateToggle.checked = Boolean(
        data.allow_second_alliance_duplicates,
      );
    const remote = new Map(
      (data.slots || []).map((item) => [
        `${item.party_number}-${item.slot_number}`,
        item,
      ]),
    );
    slots.forEach((slot) => {
      const item = remote.get(`${slot.dataset.party}-${slot.dataset.slot}`);
      setSlot(
        slot,
        item?.member_id || "",
        item?.job || "",
        item?.custom_name || "",
        item || {},
      );
    });
    suppressLiveSave = false;
    liveVersion = Number(data.version || liveVersion);
    const versionInput = document.querySelector('input[name="version"]');
    if (versionInput) versionInput.value = String(liveVersion);
    renderPresence(data.active_editors || []);
    refresh();
  };
  const serializedSlots = () =>
    slots
      .filter(occupied)
      .map((slot) => ({
        party_number: Number(slot.dataset.party),
        slot_number: Number(slot.dataset.slot),
        member_id: slot.dataset.member || null,
        custom_name: slot.dataset.customName || "",
        job: slot.dataset.job || "",
      }));
  const saveLive = async () => {
    if (!live.enabled || liveSaving) return;
    liveSaving = true;
    if (liveIndicator) {
      liveIndicator.textContent = "● Saving…";
      liveIndicator.classList.add("saving");
    }
    try {
      const response = await fetch(liveUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": live.csrf,
          },
          body: JSON.stringify({
            version: liveVersion,
            slots: serializedSlots(),
            allow_second_alliance_duplicates: Boolean(
              duplicateToggle?.checked,
            ),
          }),
        }),
        data = await response.json();
      if (response.status === 409) {
        applyLiveState(data);
        targetMessage.hidden = false;
        targetMessage.textContent =
          "Another editor saved first. Their newest layout has been loaded.";
        targetMessage.classList.add("has-target");
      } else if (!response.ok) {
        throw new Error(data.description || "Live save failed");
      } else {
        applyLiveState(data);
      }
      if (liveIndicator) {
        liveIndicator.textContent = "● Live";
        liveIndicator.classList.remove("saving", "offline");
      }
    } catch (error) {
      if (liveIndicator) {
        liveIndicator.textContent = "● Reconnecting";
        liveIndicator.classList.remove("saving");
        liveIndicator.classList.add("offline");
      }
    } finally {
      liveSaving = false;
    }
  };
  scheduleLiveSave = () => {
    clearTimeout(liveSaveTimer);
    liveSaveTimer = setTimeout(saveLive, 250);
  };
  const pollLive = async () => {
    if (!live.enabled || liveSaving || Date.now() - lastLocalChange < 700)
      return;
    try {
      const response = await fetch(liveUrl, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Live refresh failed");
      const data = await response.json();
      if (Number(data.version) > liveVersion) applyLiveState(data);
      else renderPresence(data.active_editors || []);
      if (liveIndicator) {
        liveIndicator.textContent = "● Live";
        liveIndicator.classList.remove("offline");
      }
    } catch {
      if (liveIndicator) {
        liveIndicator.textContent = "● Reconnecting";
        liveIndicator.classList.add("offline");
      }
    }
  };
  if (live.enabled) {
    pollLive();
    setInterval(pollLive, 2000);
  }
  const copyShare = document.querySelector("#copy-alliance-share"),
    shareUrl = document.querySelector("#alliance-share-url");
  copyShare?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(shareUrl.value);
      copyShare.textContent = "Link Copied";
      setTimeout(() => (copyShare.textContent = "Copy Link"), 1800);
    } catch {
      shareUrl.select();
      document.execCommand("copy");
      copyShare.textContent = "Link Copied";
    }
  });
  const form = document.querySelector("#alliance-form"),
    nameInput = form.elements.name,
    reminder = document.querySelector("#save-name-reminder");
  form.addEventListener("submit", (event) => {
    if (!nameInput.value.trim()) {
      event.preventDefault();
      reminder.textContent = "Enter an alliance name before saving.";
      reminder.classList.add("error");
      nameInput.focus();
      nameInput.reportValidity();
    }
  });
  nameInput.addEventListener("input", () => {
    reminder.textContent = nameInput.value.trim()
      ? "Alliance name ready."
      : "An alliance name is required to save.";
    reminder.classList.toggle("error", !nameInput.value.trim());
  });
  refresh();
})();
