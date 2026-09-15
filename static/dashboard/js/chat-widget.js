/**
 * Floating support-chat widget (applicant dashboard only -- a no-op
 * everywhere else, since #chatWidget only renders for that role; see
 * templates/dashboards/_chat_widget.html).
 *
 * Design: the unread badge on the launcher is driven for free by the
 * *existing* nav-badges.js poll (15s, already running site-wide for the
 * Applications sidebar counts -- unread_messages just rides along on
 * that same JSON response, see applicant_dashboard.views.nav_counts).
 * The full 2.5s live-chat engine (initLiveChat, shared with the full
 * Messages page) only starts the first time the panel is actually
 * opened, and is paused whenever it's collapsed again -- both to avoid
 * polling in the background for a widget nobody's looking at, and
 * because every poll marks the conversation read server-side: polling
 * while collapsed would silently mark messages read before the
 * applicant ever saw them, and the badge would never show up.
 */
document.addEventListener("DOMContentLoaded", () => {
  const widget = document.getElementById("chatWidget");
  if (!widget) return;

  const launcher = document.getElementById("chatWidgetLauncher");
  const panel = document.getElementById("chatWidgetPanel");
  const scroll = document.getElementById("chatWidgetScroll");
  const composer = document.getElementById("chatWidgetComposer");
  const loading = document.getElementById("chatWidgetLoading");
  const liveIndicator = document.getElementById("chatWidgetLive");
  const badge = widget.querySelector(".chat-widget-badge");

  let lastId = 0;
  let chat = null; // set once initLiveChat has run, on first open
  let isOpen = false;

  function renderInitialMessages(messages) {
    if (loading) loading.remove();
    if (!messages.length) {
      const empty = document.createElement("div");
      empty.className = "msg-thread-empty";
      empty.innerHTML = "<p>No messages yet. Ask Admin or the Secretariat anything about your application &mdash; they'll reply here.</p>";
      scroll.appendChild(empty);
      return;
    }
    messages.forEach((m) => scroll.appendChild(createMessageBubble(m)));
    scroll.scrollTop = scroll.scrollHeight;
  }

  function onMessage(message) {
    const empty = scroll.querySelector(".msg-thread-empty");
    if (empty) empty.remove();
    scroll.appendChild(createMessageBubble(message));
  }

  async function firstOpen() {
    try {
      const res = await fetch(`${widget.dataset.pollUrl}?after=0`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (res.ok) {
        const data = await res.json();
        renderInitialMessages(data.messages || []);
        lastId = data.last_id || 0;
      } else if (loading) {
        loading.textContent = "Couldn't load your conversation. Try again shortly.";
      }
    } catch (e) {
      if (loading) loading.textContent = "Couldn't load your conversation. Try again shortly.";
    }

    chat = initLiveChat({
      scroll,
      composer,
      pollUrl: widget.dataset.pollUrl,
      sendUrl: widget.dataset.sendUrl,
      getLastId: () => lastId,
      setLastId: (id) => { lastId = id; },
      onMessage,
      liveIndicator,
    });
  }

  function open() {
    isOpen = true;
    widget.classList.add("is-open");
    panel.hidden = false;
    launcher.setAttribute("aria-expanded", "true");

    if (!chat) {
      firstOpen();
    } else {
      chat.resume();
    }
    const textarea = composer.querySelector("textarea");
    if (textarea) setTimeout(() => textarea.focus(), 150);
  }

  function close() {
    isOpen = false;
    widget.classList.remove("is-open");
    launcher.setAttribute("aria-expanded", "false");
    if (chat) chat.pause();
    // Wait for the close transition (see chat-widget.css) before hiding
    // for real, so the panel doesn't just vanish mid-animation.
    setTimeout(() => { if (!isOpen) panel.hidden = true; }, 200);
  }

  launcher.addEventListener("click", () => {
    if (isOpen) close(); else open();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen) close();
  });

  document.addEventListener("click", (e) => {
    if (isOpen && !widget.contains(e.target)) close();
  });

  // Give a new message some presence even while collapsed -- pulse the
  // whole launcher (not just the small number) the moment nav-badges.js
  // marks the badge as having actually changed, same "did the value
  // change" signal it already computes for its own pulse.
  if (badge && window.MutationObserver) {
    const observer = new MutationObserver(() => {
      if (isOpen || !badge.classList.contains("nav-badge-pulse")) return;
      launcher.classList.remove("chat-widget-pulse");
      void launcher.offsetWidth;
      launcher.classList.add("chat-widget-pulse");
    });
    observer.observe(badge, { attributes: true, attributeFilter: ["class"] });
  }
});
