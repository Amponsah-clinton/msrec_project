/* MSREC Assistant ("Scholar") -- the floating chat widget.
   Talks to POST /assistant/chat/ (see the `assistant` Django app). The
   conversation lives only in this tab's sessionStorage and is sent with
   each question; nothing is stored server-side. */
(function () {
  "use strict";
  var root = document.getElementById("msrecAssistant");
  if (!root || root.dataset.ready) return;
  root.dataset.ready = "1";
  document.body.classList.add("has-msa");

  var $ = function (id) { return document.getElementById(id); };
  var launcher = $("msaLauncher"), panel = $("msaPanel"), log = $("msaLog"), chips = $("msaChips");
  var body = $("msaBody"), form = $("msaForm"), input = $("msaInput"), send = $("msaSend");
  var teaser = $("msaTeaser");
  var endpoint = root.dataset.endpoint, csrf = root.dataset.csrf;
  var role = root.dataset.role || "", name = root.dataset.name || "";
  var STORE = "msa:v1:" + (root.dataset.scope || "public");
  var MAX_KEEP = 30;
  var avatarSvg = (panel.querySelector(".msa-head-avatar svg") || {}).outerHTML || "";
  var messages = [];
  var busy = false;

  // ------------------------------------------------------------ storage
  function load() {
    try { messages = JSON.parse(sessionStorage.getItem(STORE) || "[]") || []; } catch (e) { messages = []; }
    if (!Array.isArray(messages)) messages = [];
  }
  function save() {
    try { sessionStorage.setItem(STORE, JSON.stringify(messages.slice(-MAX_KEEP))); } catch (e) { /* private mode */ }
  }

  // ------------------------------------------------------------ safe mini-markdown
  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function inline(s) {
    s = esc(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    // [text](/path) or [text](https://...) only -- anything else stays text
    s = s.replace(/\[([^\]]+)\]\(((?:\/(?!\/)|https:\/\/)[^\s)]*)\)/g, function (m, text, url) {
      var ext = url.indexOf("https://") === 0;
      return '<a href="' + url + '"' + (ext ? ' target="_blank" rel="noopener noreferrer"' : "") + ">" + text + "</a>";
    });
    return s;
  }
  function markdown(text) {
    var lines = String(text).replace(/\r/g, "").split("\n");
    var html = [], list = null, para = [];
    function flushPara() { if (para.length) { html.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; } }
    function flushList() { if (list) { html.push("<" + list.tag + ">" + list.items.map(function (i) { return "<li>" + inline(i) + "</li>"; }).join("") + "</" + list.tag + ">"); list = null; } }
    lines.forEach(function (raw) {
      var line = raw.trim();
      var ul = line.match(/^[-*•]\s+(.*)$/), ol = line.match(/^\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        flushPara();
        var tag = ul ? "ul" : "ol";
        if (!list || list.tag !== tag) { flushList(); list = { tag: tag, items: [] }; }
        list.items.push((ul || ol)[1]);
      } else if (!line) {
        flushPara(); flushList();
      } else {
        flushList();
        para.push(line.replace(/^#{1,6}\s+/, ""));
      }
    });
    flushPara(); flushList();
    return html.join("");
  }

  // ------------------------------------------------------------ rendering
  function row(kind, html, opts) {
    opts = opts || {};
    var el = document.createElement("div");
    el.className = "msa-row is-" + kind + (opts.error ? " is-error" : "");
    if (kind === "bot") {
      var prev = log.lastElementChild;
      var grouped = prev && prev.classList.contains("is-bot") && !prev.classList.contains("is-typing");
      if (grouped) {
        var prevAvatar = prev.querySelector(".msa-row-avatar");
        if (prevAvatar) prevAvatar.classList.add("is-spacer");
      }
      el.innerHTML = '<span class="msa-row-avatar">' + avatarSvg + "</span>";
    }
    var bubble = document.createElement("div");
    bubble.className = "msa-bubble";
    bubble.innerHTML = html;
    el.appendChild(bubble);
    log.appendChild(el);
    scrollDown();
    return el;
  }
  function scrollDown() { body.scrollTop = body.scrollHeight; }

  function greeting() {
    var hello = name ? "Hi " + esc(name) + "! I'm **Scholar**, the MSREC Assistant." : "Hi! I'm **Scholar**, the MSREC Assistant.";
    var help = role
      ? "I can explain how things work in your dashboard, MSREC's review process, fees and deadlines. I can't see your records, but I'll point you to the right place."
      : "Ask me about applying for ethics review, required documents, fees, timelines or verifying an approval.";
    return markdown(hello + "\n\n" + help);
  }

  var SUGGESTIONS = {
    "": ["What are the fees?", "How do I register?", "What process does an application go through?"],
    applicant: ["How do I start a new application?", "Where do I pay my review fee?", "How do I report an adverse event?", "What happens after approval?"],
    reviewer: ["Why must I declare conflicts first?", "What do reviewers assess?", "How do I get my review certificate?"],
    committee: ["How do I RSVP for a meeting?", "How do I declare a conflict of interest?", "Where do I find protocols referred to the Committee?"],
    chair: ["How does quorum work?", "What decisions can the Committee make?", "When is Full Committee review needed?"],
    secretariat: ["What does administrative screening check?", "How are review pathways assigned?", "What are the current fees?"],
    admin: ["What are the current fees?", "How are review pathways assigned?", "What does the Secretariat do?"]
  };
  function renderChips() {
    chips.innerHTML = "";
    if (messages.length) { chips.hidden = true; return; }
    chips.hidden = false;
    (SUGGESTIONS[role] || SUGGESTIONS[""]).forEach(function (q) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "msa-chip";
      b.textContent = q;
      b.addEventListener("click", function () { ask(q); });
      chips.appendChild(b);
    });
  }

  function renderAll() {
    log.innerHTML = "";
    row("bot", greeting());
    messages.forEach(function (m) {
      if (m.role === "user") row("user", esc(m.content));
      else row("bot", markdown(m.content));
    });
    renderChips();
  }

  // ------------------------------------------------------------ talking to the server
  function sidebarLinks() {
    var out = [], seen = {};
    document.querySelectorAll(".sidebar a[href], nav.nav a[href]").forEach(function (a) {
      var href = a.getAttribute("href") || "";
      var label = (a.textContent || "").replace(/\s+/g, " ").trim();
      if (!label || href.charAt(0) !== "/" || seen[href]) return;
      seen[href] = 1;
      out.push({ label: label.slice(0, 60), href: href });
    });
    return out.slice(0, 40);
  }

  function ask(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true;
    chips.hidden = true;
    messages.push({ role: "user", content: text });
    save();
    row("user", esc(text));
    input.value = "";
    autosize();
    updateSend();

    var typing = row("bot", '<span class="msa-typing" aria-label="Scholar is typing"><i></i><i></i><i></i></span>');
    typing.classList.add("is-typing");

    var controller = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (controller) controller.abort(); }, 45000);

    fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({
        messages: messages.slice(-12),
        page: { title: document.title.slice(0, 120), path: location.pathname },
        nav: role ? sidebarLinks() : []
      }),
      signal: controller ? controller.signal : undefined
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (r) {
        typing.remove();
        if (r.ok && r.data.reply) {
          messages.push({ role: "assistant", content: r.data.reply });
          save();
          row("bot", markdown(r.data.reply));
        } else {
          failed(r.data.error || "Something went wrong. Please try again.");
        }
      })
      .catch(function () {
        typing.remove();
        failed("I couldn't connect just now. Check your connection and try again.");
      })
      .then(function () {
        clearTimeout(timer);
        busy = false;
        updateSend();
        if (!panel.hidden) input.focus();
      });
  }

  function failed(msg) {
    // Drop the unanswered question so a retry doesn't send it twice.
    var last = messages.pop();
    save();
    var el = row("bot", esc(msg), { error: true });
    var retry = document.createElement("button");
    retry.type = "button";
    retry.className = "msa-retry";
    retry.textContent = "Try again";
    retry.addEventListener("click", function () {
      el.remove();
      var userRows = log.querySelectorAll(".msa-row.is-user");
      if (userRows.length) userRows[userRows.length - 1].remove();
      ask(last && last.content);
    });
    el.querySelector(".msa-bubble").appendChild(document.createElement("br"));
    el.querySelector(".msa-bubble").appendChild(retry);
  }

  // ------------------------------------------------------------ open / close
  function open() {
    hideTeaser(true);
    panel.hidden = false;
    root.classList.add("is-open");
    launcher.setAttribute("aria-expanded", "true");
    launcher.setAttribute("aria-label", "Close the MSREC Assistant");
    try { sessionStorage.setItem("msa:open", "1"); } catch (e) {}
    scrollDown();
    setTimeout(function () { input.focus(); }, 50);
  }
  function close() {
    panel.hidden = true;
    root.classList.remove("is-open");
    launcher.setAttribute("aria-expanded", "false");
    launcher.setAttribute("aria-label", "Open the MSREC Assistant");
    try { sessionStorage.removeItem("msa:open"); } catch (e) {}
    launcher.focus();
  }
  launcher.addEventListener("click", function () { panel.hidden ? open() : close(); });
  $("msaClose").addEventListener("click", close);
  $("msaReset").addEventListener("click", function () {
    if (busy) return;
    messages = [];
    save();
    renderAll();
    input.focus();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) close();
  });

  // ------------------------------------------------------------ composer
  function autosize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }
  function updateSend() { send.disabled = busy || !input.value.trim(); }
  input.addEventListener("input", function () { autosize(); updateSend(); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      ask(input.value);
    }
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); ask(input.value); });

  // ------------------------------------------------------------ teaser (landing page, once per session)
  function hideTeaser(remember) {
    teaser.hidden = true;
    if (remember) { try { sessionStorage.setItem("msa:teased", "1"); } catch (e) {} }
  }
  $("msaTeaserClose").addEventListener("click", function (e) { e.stopPropagation(); hideTeaser(true); });
  teaser.addEventListener("click", function (e) { if (e.target === teaser || e.target.tagName !== "BUTTON") open(); });
  var teased = false;
  try { teased = !!sessionStorage.getItem("msa:teased"); } catch (e) {}
  if (!role && location.pathname === "/" && !teased) {
    setTimeout(function () { if (panel.hidden) teaser.hidden = false; }, 4000);
  }

  // ------------------------------------------------------------ boot
  load();
  renderAll();
  var wasOpen = false;
  try { wasOpen = !!sessionStorage.getItem("msa:open"); } catch (e) {}
  if (wasOpen) { panel.hidden = false; root.classList.add("is-open"); launcher.setAttribute("aria-expanded", "true"); scrollDown(); }
})();
