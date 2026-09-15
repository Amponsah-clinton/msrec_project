/**
 * Generic near-real-time chat engine shared by the applicant Messages page
 * (one fixed conversation) and the admin/secretariat Messages page (many
 * conversations, one open at a time).
 *
 * There's no WebSocket/Channels layer in this project (plain WSGI Django,
 * no channel-layer backend like Redis provisioned) -- short-interval
 * polling, paused whenever the tab isn't visible, is the dependency-free
 * way to get "real time" here: sending is instant (optimistic append),
 * and messages from the other side land within one poll tick.
 */

function createMessageBubble(message) {
  const bubble = document.createElement("div");
  bubble.className = `msg-bubble ${message.is_mine ? "out" : "in"}`;
  bubble.dataset.messageId = message.id;

  const p = document.createElement("p");
  // Preserve newlines the way the server's `linebreaksbr` does on first
  // load, without innerHTML -- message bodies are user text and must
  // never be parsed as markup.
  const lines = String(message.body).split("\n");
  lines.forEach((line, i) => {
    if (i > 0) p.appendChild(document.createElement("br"));
    p.appendChild(document.createTextNode(line));
  });
  bubble.appendChild(p);

  const time = document.createElement("span");
  time.className = "msg-time";
  if (message.is_mine) {
    time.textContent = message.time_display;
  } else {
    // sender_role ("Admin"/"Secretariat") lets an applicant tell the two
    // staff roles apart in a thread either one can answer -- see
    // messaging.access.staff_role_label.
    const who = message.sender_role ? `${message.sender_name} · ${message.sender_role}` : message.sender_name;
    time.textContent = `${who} · ${message.time_display}`;
  }
  bubble.appendChild(time);

  return bubble;
}

function autoGrowTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 110) + "px";
}

function initLiveChat({ scroll, composer, pollUrl, sendUrl, getLastId, setLastId, onMessage, liveIndicator, intervalMs = 2500 }) {
  function csrfToken() {
    const input = composer.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function scrollToBottom() {
    scroll.scrollTop = scroll.scrollHeight;
  }

  function pulseLive() {
    if (!liveIndicator) return;
    liveIndicator.classList.remove("is-pulsing");
    // Force reflow so re-adding the class restarts the CSS animation even
    // when polls land back-to-back.
    void liveIndicator.offsetWidth;
    liveIndicator.classList.add("is-pulsing");
  }

  async function poll() {
    if (document.hidden) return;
    try {
      const res = await fetch(`${pollUrl}?after=${getLastId()}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!res.ok) return;
      const data = await res.json();
      pulseLive();
      if (data.messages && data.messages.length) {
        data.messages.forEach((m) => onMessage(m));
        setLastId(data.last_id);
        scrollToBottom();
      }
    } catch (err) {
      // Transient network hiccup -- the next tick just tries again.
    }
  }

  const textarea = composer.querySelector("textarea[name=body]");

  composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = textarea.value.trim();
    if (!body) return;
    const sendBtn = composer.querySelector('button[type="submit"]');
    textarea.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    try {
      const res = await fetch(sendUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ body }),
      });
      if (res.ok) {
        const message = await res.json();
        onMessage(message);
        setLastId(message.id);
        textarea.value = "";
        autoGrowTextarea(textarea);
        scrollToBottom();
      }
    } finally {
      textarea.disabled = false;
      if (sendBtn) sendBtn.disabled = false;
      textarea.focus();
    }
  });

  if (textarea) {
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        composer.requestSubmit();
      }
    });
    textarea.addEventListener("input", () => autoGrowTextarea(textarea));
  }

  let timer = setInterval(poll, intervalMs);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) poll();
  });

  scrollToBottom();

  return {
    poll,
    stop: () => clearInterval(timer),
    // pause/resume (distinct from stop) let a caller like the floating
    // chat widget suspend polling while its panel is collapsed -- without
    // re-running initLiveChat, which would re-bind the composer's submit
    // listener a second time and send every message twice.
    pause: () => clearInterval(timer),
    resume: () => {
      poll();
      timer = setInterval(poll, intervalMs);
    },
  };
}
