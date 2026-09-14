document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("applyForm");
  if (!form) return;

  /* ============================================================
     Yes/No toggles
  ============================================================ */
  function initYesNoToggles(root) {
    root.querySelectorAll(".yn-toggle").forEach((toggle) => {
      const hidden = document.getElementById(toggle.dataset.hiddenId);
      toggle.querySelectorAll(".yn-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          toggle.querySelectorAll(".yn-btn").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          const value = btn.dataset.value;
          if (hidden) hidden.value = value;
          toggle.dispatchEvent(new CustomEvent("ynchange", { detail: { value }, bubbles: true }));
          updateProgress();
        });
      });
    });
  }
  initYesNoToggles(form);

  function gateYesNo(toggleId, detailEl, showValues) {
    const toggle = document.getElementById(toggleId);
    if (!toggle || !detailEl) return;
    toggle.addEventListener("ynchange", (e) => {
      detailEl.hidden = !showValues.includes(e.detail.value);
    });
  }

  /* Participant Recruitment: compensation detail */
  (function () {
    const toggle = document.querySelector('.yn-toggle[data-hidden-id="compensationYn"]');
    const detail = document.getElementById("compensationDetails");
    if (toggle && detail) {
      toggle.addEventListener("ynchange", (e) => { detail.hidden = e.detail.value !== "yes"; });
    }
  })();

  /* Privacy & Confidentiality: sensitive info */
  gateYesNo("sensitiveInfoGate", document.getElementById("sensitiveInfoDetails"), ["yes"]);

  /* AI / ML / Automated Systems */
  gateYesNo("aiGate", document.getElementById("aiDetails"), ["yes"]);

  /* Software, System, Device or Prototype Research */
  gateYesNo("systemGate", document.getElementById("systemDetails"), ["yes"]);

  /* Funding, Sponsorship & Collaboration */
  gateYesNo("fundedGate", document.getElementById("fundedDetails"), ["yes"]);
  gateYesNo("internationalGate", document.getElementById("internationalDetails"), ["yes"]);

  /* Research Team: academic programme, if applicable */
  (function () {
    const toggle = form.querySelector('.yn-toggle[data-hidden-id="academicProgrammeYn"]');
    const detail = document.getElementById("academicProgrammeDetails");
    if (toggle && detail) {
      toggle.addEventListener("ynchange", (e) => { detail.hidden = e.detail.value !== "yes"; });
    }
  })();

  /* ============================================================
     Radio-based conditional reveals (non yes/no chip grids)
  ============================================================ */
  function gateOnRadio(groupName, showValues, detailEl) {
    const radios = Array.from(form.querySelectorAll(`input[name="${groupName}"]`));
    if (!radios.length || !detailEl) return;
    radios.forEach((r) => {
      r.addEventListener("change", () => {
        const selected = radios.find((x) => x.checked);
        detailEl.hidden = !(selected && showValues.includes(selected.value));
      });
    });
  }
  gateOnRadio("consentObtained", ["no", "waiver"], document.getElementById("consentExplainWrap"));
  gateOnRadio("coi", ["yes"], document.getElementById("coiDetails"));

  /* ============================================================
     "Other" reveal — any chip-checkbox-grid with a .chip-other-trigger
  ============================================================ */
  document.querySelectorAll(".chip-checkbox-grid, .apply-team-table").forEach((grid) => {
    grid.addEventListener("change", () => {
      grid.querySelectorAll(".chip-other-trigger").forEach((trigger) => {
        const wrap = document.querySelector(`[data-other-for="${trigger.dataset.otherTarget}"]`);
        if (wrap) wrap.hidden = !trigger.checked;
      });
    });
  });

  /* ============================================================
     Research team — add / remove rows
  ============================================================ */
  const teamTable = document.getElementById("applyTeamTable");
  const addTeamRowBtn = document.getElementById("addTeamRow");

  function bindRemove(row) {
    const btn = row.querySelector(".apply-team-remove");
    if (btn) btn.addEventListener("click", () => { row.remove(); });
  }
  teamTable.querySelectorAll(".apply-team-row:not(.apply-team-head)").forEach(bindRemove);

  addTeamRowBtn.addEventListener("click", () => {
    const row = document.createElement("div");
    row.className = "apply-team-row";
    row.innerHTML = `
      <input type="text" name="teamName[]" placeholder="Full name">
      <input type="text" name="teamRole[]" placeholder="e.g. Co-Investigator">
      <input type="text" name="teamInstitution[]" placeholder="Institution / organization">
      <button type="button" class="apply-team-remove" aria-label="Remove row"><i class="bi bi-x-lg"></i></button>
    `;
    teamTable.appendChild(row);
    bindRemove(row);
  });

  /* ============================================================
     Document uploader (client-side only — demo)
  ============================================================ */
  const fileInput = document.getElementById("applyFileInput");
  const fileDrop = document.querySelector(".apply-file-drop");
  const fileList = document.getElementById("applyFileList");
  let uploadedFiles = [];

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function renderFileList() {
    fileList.innerHTML = "";
    uploadedFiles.forEach((file, i) => {
      const item = document.createElement("div");
      item.className = "apply-file-item";
      item.innerHTML = `
        <i class="bi bi-file-earmark-text"></i>
        <span>${file.name}</span>
        <span class="apply-file-size">${formatSize(file.size)}</span>
        <button type="button" class="apply-file-remove" aria-label="Remove ${file.name}"><i class="bi bi-x-lg"></i></button>
      `;
      item.querySelector(".apply-file-remove").addEventListener("click", () => {
        uploadedFiles.splice(i, 1);
        renderFileList();
      });
      fileList.appendChild(item);
    });
  }

  function addFiles(fileArray) {
    Array.from(fileArray).forEach((f) => uploadedFiles.push(f));
    renderFileList();
    updateProgress();
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => { if (fileInput.files) addFiles(fileInput.files); });
  }
  if (fileDrop) {
    ["dragenter", "dragover"].forEach((evt) => {
      fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.add("is-dragover"); });
    });
    ["dragleave", "drop"].forEach((evt) => {
      fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.remove("is-dragover"); });
    });
    fileDrop.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
    });
  }

  /* ============================================================
     Date defaults
  ============================================================ */
  const today = new Date().toISOString().slice(0, 10);
  const declarationDate = document.getElementById("declarationDate");
  if (declarationDate) declarationDate.value = today;

  /* ============================================================
     TOC: active-section highlighting + smooth scroll
  ============================================================ */
  const tocLinks = Array.from(document.querySelectorAll(".apply-toc a"));
  const sections = tocLinks
    .map((link) => document.getElementById(link.dataset.toc))
    .filter(Boolean);

  const SCROLLSPY_TRIGGER_OFFSET = 150; // matches .apply-section scroll-margin-top

  tocLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const target = document.getElementById(link.dataset.toc);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + target.id);
    });
  });

  function refreshActiveToc() {
    let activeId = sections[0] && sections[0].id;
    for (const s of sections) {
      if (s.getBoundingClientRect().top <= SCROLLSPY_TRIGGER_OFFSET) activeId = s.id;
      else break;
    }
    tocLinks.forEach((l) => l.classList.toggle("is-active", l.dataset.toc === activeId));
  }

  let scrollspyTicking = false;
  window.addEventListener("scroll", () => {
    if (scrollspyTicking) return;
    scrollspyTicking = true;
    requestAnimationFrame(() => { refreshActiveToc(); scrollspyTicking = false; });
  }, { passive: true });
  refreshActiveToc();

  /* ============================================================
     Progress meter — heuristic: answered fields / total visible fields
  ============================================================ */
  const progressFill = document.getElementById("applyProgressFill");
  const progressPct = document.getElementById("applyProgressPct");

  function isVisible(el) {
    return !!(el.offsetParent !== null || el.closest("[hidden]") === null);
  }

  function updateProgress() {
    const trackedSections = form.querySelectorAll(".apply-section");
    let total = 0;
    let answered = 0;

    trackedSections.forEach((section) => {
      if (section.closest("[hidden]")) return;

      // Text-like inputs / selects / textareas (excluding hidden helper inputs and "other" fields not shown)
      section.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input[type="number"], input[type="date"], input[type="url"], select, textarea').forEach((field) => {
        if (field.closest("[hidden]")) return;
        if (field.disabled) return;
        total++;
        if (field.value && field.value.trim()) answered++;
      });

      // Checkbox / radio groups — count each distinct group once
      const groups = {};
      section.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach((box) => {
        if (box.closest("[hidden]")) return;
        if (box.disabled) return;
        if (!box.name) return;
        groups[box.name] = groups[box.name] || [];
        groups[box.name].push(box);
      });
      Object.values(groups).forEach((boxes) => {
        total++;
        if (boxes.some((b) => b.checked)) answered++;
      });

      // Yes/No toggles
      section.querySelectorAll(".yn-toggle").forEach((toggle) => {
        if (toggle.closest("[hidden]")) return;
        total++;
        if (toggle.querySelector(".yn-btn.active")) answered++;
      });
    });

    const pct = total ? Math.round((answered / total) * 100) : 0;
    if (progressFill) progressFill.style.width = pct + "%";
    if (progressPct) progressPct.textContent = pct + "%";
    const pctField = document.getElementById("applyCompletionPctField");
    if (pctField) pctField.value = String(pct);
    return pct;
  }

  form.addEventListener("input", updateProgress);
  form.addEventListener("change", updateProgress);
  updateProgress();

  /* ============================================================
     Requested Review — the chip-radios live in .apply-review-request,
     outside <form> (they sit in the intro block above it), so they never
     post on their own. Keep the in-form hidden mirror ("requestedReview")
     in sync so both a real submit and autosave actually carry the value.
  ============================================================ */
  const requestedReviewHidden = document.getElementById("requestedReviewHidden");
  document.querySelectorAll('.apply-review-request input[name="requestedReview"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      if (requestedReviewHidden) requestedReviewHidden.value = radio.checked ? radio.value : "";
      updateProgress();
    });
  });

  /* ============================================================
     Restore a draft's saved answers (see application_form view /
     initial_data|json_script). Reuses the exact same input/change events
     the rest of this file already listens on, so every reveal-on-value
     gate (yes/no toggles, "Other" text boxes, conditional detail panels)
     ends up in the right state without duplicating that logic here.
  ============================================================ */
  function cssEscapeName(value) {
    return window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/["\\]/g, "\\$&");
  }

  function populateTeamRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return;
    teamTable.querySelectorAll(".apply-team-row:not(.apply-team-head)").forEach((row) => row.remove());
    rows.forEach((member) => {
      addTeamRowBtn.click();
      const row = teamTable.querySelector(".apply-team-row:last-child");
      if (!row) return;
      const nameField = row.querySelector('[name="teamName[]"]');
      const roleField = row.querySelector('[name="teamRole[]"]');
      const institutionField = row.querySelector('[name="teamInstitution[]"]');
      if (nameField) nameField.value = member.name || "";
      if (roleField) roleField.value = member.role || "";
      if (institutionField) institutionField.value = member.institution || "";
    });
  }

  function populateForm(data) {
    if (!data || typeof data !== "object") return;

    Object.keys(data).forEach((key) => {
      if (key === "researchTeam") {
        populateTeamRows(data[key]);
        return;
      }

      const value = data[key];

      const toggle = document.querySelector(`.yn-toggle[data-hidden-id="${cssEscapeName(key)}"]`);
      if (toggle) {
        const btn = toggle.querySelector(`.yn-btn[data-value="${cssEscapeName(String(value))}"]`);
        if (btn) btn.click();
        return;
      }

      const fields = Array.from(document.querySelectorAll(`[name="${cssEscapeName(key)}"]`));
      if (!fields.length) return;

      if (fields[0].type === "checkbox") {
        if (Array.isArray(value)) {
          fields.forEach((field) => { field.checked = value.includes(field.value); });
        } else if (value) {
          fields[0].checked = true;
        }
        fields[0].dispatchEvent(new Event("change", { bubbles: true }));
        return;
      }

      if (fields[0].type === "radio") {
        const match = fields.find((field) => field.value === value);
        if (match) {
          match.checked = true;
          match.dispatchEvent(new Event("change", { bubbles: true }));
        }
        return;
      }

      fields[0].value = value == null ? "" : value;
      fields[0].dispatchEvent(new Event("change", { bubbles: true }));
    });

    updateProgress();
  }

  const initialDataEl = document.getElementById("applyInitialData");
  if (initialDataEl) {
    try {
      const initialData = JSON.parse(initialDataEl.textContent);
      if (initialData && Object.keys(initialData).length) populateForm(initialData);
    } catch (err) {
      /* Malformed/empty draft data shouldn't block a fresh form. */
    }
  }

  /* ============================================================
     Autosave — a couple of seconds after the applicant stops typing or
     ticking boxes, quietly upsert a draft row so nothing is lost to a
     closed tab or dead battery. Never sends files (see apply.js
     "documents" delete below and the matching note server-side); the
     real Submit / Save-as-Draft buttons are normal form posts and do
     carry files.
  ============================================================ */
  const autosaveUrl = form.dataset.autosaveUrl;
  const applicationIdField = document.getElementById("applyApplicationId");
  const autosaveStatus = document.getElementById("applyAutosaveStatus");
  const AUTOSAVE_DEBOUNCE_MS = 2500;
  let autosaveTimer = null;
  let autosaveInFlight = false;
  let dirtySinceSave = false;
  let formLocked = false; // true once a real submit/draft-save navigation is underway

  function setAutosaveStatus(text, mode) {
    if (!autosaveStatus) return;
    autosaveStatus.textContent = text;
    autosaveStatus.classList.remove("is-saving", "is-error");
    if (mode) autosaveStatus.classList.add(mode);
  }

  function runAutosave() {
    if (!autosaveUrl || formLocked || autosaveInFlight || !dirtySinceSave) return;
    const keyBeforeSave = draftStorageKey();
    autosaveInFlight = true;
    dirtySinceSave = false;
    setAutosaveStatus("Saving draft…", "is-saving");

    const payload = new FormData(form);
    payload.delete("documents");

    fetch(autosaveUrl, {
      method: "POST",
      body: payload,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((res) => {
        if (res.status === 409) { applicationIdField.value = ""; throw new Error("stale_draft"); }
        if (!res.ok) throw new Error("autosave_failed");
        return res.json();
      })
      .then((data) => {
        if (applicationIdField && data.application_id) applicationIdField.value = data.application_id;
        // The server now has this data -- the local safety-net copy (see
        // below) is redundant. Clear both the key it was saved under
        // ("new") and the key it lives under now (the real id it was
        // just assigned), so a later visit never "restores" stale data
        // over what the server already has.
        clearLocalSnapshot(keyBeforeSave);
        clearLocalSnapshot();
        const savedTime = new Date(data.saved_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
        setAutosaveStatus(`Draft saved automatically at ${savedTime}`);
      })
      .catch(() => {
        dirtySinceSave = true; // retry on the next debounce/interval tick
        setAutosaveStatus("Couldn't autosave — check your connection. Your answers are saved on this device.", "is-error");
      })
      .finally(() => { autosaveInFlight = false; });
  }

  function scheduleAutosave() {
    dirtySinceSave = true;
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(runAutosave, AUTOSAVE_DEBOUNCE_MS);
  }

  form.addEventListener("input", scheduleAutosave);
  form.addEventListener("change", scheduleAutosave);

  // Belt-and-braces periodic save, in case debounced typing never pauses
  // long enough (e.g. someone dictating a long study description).
  setInterval(runAutosave, 30000);

  /* ============================================================
     Instant local safety net -- guarantees "leave the page and it's
     saved" even in the up-to-2.5s gap before the debounced server
     autosave above would have fired, and even if that network call
     never lands at all (offline, or the tab is killed outright).

     A network "send this on the way out" call (sendBeacon / fetch
     keepalive) alone isn't enough for a form this size: both are
     capped at ~64KB by the browser, and this form's ~90 fields (long
     textareas, many checkbox groups, an unbounded research-team list)
     can exceed that -- the call would just silently fail with no
     error surfaced anywhere. localStorage has no such practical limit
     and writing to it is synchronous, so it can't lose a race with
     the page unloading the way an in-flight network request can.
  ============================================================ */
  function draftStorageKey() {
    return "msrecDraftSnapshot:" + (applicationIdField.value || "new");
  }

  function collectFormSnapshot() {
    const data = {};
    const skip = new Set(["csrfmiddlewaretoken", "requestedReview", "formAction", "application_id", "completionPct"]);
    const teamFields = new Set(["teamName[]", "teamRole[]", "teamInstitution[]"]);
    const seen = new Set();

    Array.from(form.elements).forEach((el) => {
      const name = el.name;
      if (!name || skip.has(name) || teamFields.has(name) || seen.has(name)) return;
      seen.add(name);

      if (el.type === "checkbox") {
        const group = Array.from(form.querySelectorAll(`input[type="checkbox"][name="${cssEscapeName(name)}"]`));
        data[name] = group.filter((c) => c.checked).map((c) => c.value);
        return;
      }
      if (el.type === "radio") {
        const group = Array.from(form.querySelectorAll(`input[type="radio"][name="${cssEscapeName(name)}"]`));
        const checked = group.find((r) => r.checked);
        if (checked) data[name] = checked.value;
        return;
      }
      data[name] = el.value;
    });

    const names = Array.from(form.querySelectorAll('[name="teamName[]"]')).map((el) => el.value.trim());
    const roles = Array.from(form.querySelectorAll('[name="teamRole[]"]')).map((el) => el.value.trim());
    const institutions = Array.from(form.querySelectorAll('[name="teamInstitution[]"]')).map((el) => el.value.trim());
    data.researchTeam = names
      .map((name, i) => ({ name, role: roles[i] || "", institution: institutions[i] || "" }))
      .filter((member) => member.name || member.role || member.institution);

    return data;
  }

  function saveSnapshotLocally() {
    try {
      localStorage.setItem(draftStorageKey(), JSON.stringify({ data: collectFormSnapshot(), savedAt: Date.now() }));
    } catch (e) {
      // Storage full/disabled (private browsing, quota) -- the debounced
      // and periodic server autosaves above are still running regardless.
    }
  }

  function clearLocalSnapshot(key) {
    try { localStorage.removeItem(key || draftStorageKey()); } catch (e) { /* see above */ }
  }

  // Restore anything left over from a session that ended before a save
  // confirmed with the server (this key is only ever written when dirty
  // and only ever cleared once a save succeeds -- see below -- so its
  // mere presence means "these edits never made it to the server").
  // Runs after the server's own initial_data restore further up this
  // file, so unsaved local edits correctly take precedence over it.
  (function restoreLocalSnapshotIfAny() {
    let raw;
    try { raw = localStorage.getItem(draftStorageKey()); } catch (e) { return; }
    if (!raw) return;
    try {
      const snapshot = JSON.parse(raw);
      if (snapshot && snapshot.data) {
        populateForm(snapshot.data);
        dirtySinceSave = true;
        setAutosaveStatus("Restored unsaved changes from your last visit — saving now…", "is-saving");
        runAutosave();
      }
    } catch (e) {
      clearLocalSnapshot();
    }
  })();

  // Best-effort last save if they close the tab, switch away, or navigate
  // mid-edit. The localStorage write is the actual guarantee (instant,
  // no size limit that matters here); sendBeacon is a bonus best-effort
  // attempt to get the server up to date too, for whatever fits in it.
  function saveOnLeave() {
    if (!dirtySinceSave) return;
    saveSnapshotLocally();
    if (autosaveUrl && !formLocked) {
      const payload = new FormData(form);
      payload.delete("documents");
      navigator.sendBeacon(autosaveUrl, payload);
    }
  }
  window.addEventListener("beforeunload", saveOnLeave);
  window.addEventListener("pagehide", saveOnLeave);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") saveOnLeave();
  });

  /* ============================================================
     Submit / Save as Draft — real form posts (Django renders the
     confirmation view / redirects to Drafts server-side); we only add
     client-side validation before a real Submit, and stop autosave from
     racing the navigation that's about to happen either way.
  ============================================================ */
  const submitBtn = document.getElementById("applySubmitBtn");
  const saveDraftBtn = document.getElementById("applySaveDraftBtn");
  const formActionField = document.getElementById("applyFormActionField");

  form.addEventListener("submit", (e) => {
    // e.submitter (which button triggered this) is well-supported, but
    // fall back to activeElement for older engines. Default to "treat as
    // a real Submit" unless we're sure it was the Save-as-Draft button —
    // an ambiguous case (e.g. implicit Enter-key submit) should still get
    // validated rather than silently skip the PI declaration checkbox.
    const submitter = e.submitter || document.activeElement;
    const clickedSubmit = submitter !== saveDraftBtn;

    if (clickedSubmit && !form.checkValidity()) {
      e.preventDefault();
      form.reportValidity();
      return;
    }

    // Record which button this was BEFORE disabling anything below: a
    // disabled form control is never included when the browser serializes
    // the form, so setting this after disabling submitBtn/saveDraftBtn
    // would silently drop formAction from the POST body every time
    // (that's what was breaking Save as Draft -- the button's own
    // name="formAction" vanished the instant this handler disabled it).
    if (formActionField) formActionField.value = clickedSubmit ? "submit" : "draft";

    // This real POST is about to save everything server-side, so the
    // local safety-net copy (see the autosave section above) would just
    // be stale leftovers on a future visit -- clear it now rather than
    // waiting on an autosave success handler that this request bypasses.
    clearLocalSnapshot();

    formLocked = true;
    if (autosaveTimer) clearTimeout(autosaveTimer);

    if (clickedSubmit && submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = "Submitting application...";
    } else if (saveDraftBtn) {
      saveDraftBtn.disabled = true;
      saveDraftBtn.innerHTML = "Saving...";
    }
  });

  /* ============================================================
     Application date submitted (display only — set at submission
     time in a live system; shown here as today's date for context)
  ============================================================ */
  const dateSubmittedEl = document.getElementById("applyDateSubmitted");
  if (dateSubmittedEl) {
    dateSubmittedEl.textContent = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
  }
});
