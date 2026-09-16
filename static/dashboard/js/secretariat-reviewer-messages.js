document.addEventListener("DOMContentLoaded", () => {
  const shell = document.getElementById("secRevMsgShell");
  if (!shell) return;

  // Same live-chat wiring as secretariat-messages.js, just pointed at the
  // reviewer conversation endpoints and this page's own element ids.
  const scroll = document.getElementById("secRevMsgThreadScroll");
  const composer = document.getElementById("secRevMsgComposer");
  const liveIndicator = document.getElementById("secRevMsgLiveIndicator");

  if (scroll && composer && shell.dataset.pollUrl) {
    let lastId = parseInt(shell.dataset.lastId, 10) || 0;

    function onMessage(message) {
      const empty = scroll.querySelector(".msg-thread-empty");
      if (empty) empty.remove();
      scroll.appendChild(createMessageBubble(message));
    }

    initLiveChat({
      scroll,
      composer,
      pollUrl: shell.dataset.pollUrl,
      sendUrl: shell.dataset.sendUrl,
      getLastId: () => lastId,
      setLastId: (id) => { lastId = id; },
      onMessage,
      liveIndicator,
    });
  }

  if (new URLSearchParams(window.location.search).has("reviewer")) {
    shell.classList.add("thread-open");
  }
  const backBtn = shell.querySelector(".thread-back-btn");
  if (backBtn) backBtn.addEventListener("click", () => shell.classList.remove("thread-open"));

  const searchInput = document.getElementById("secRevMsgSearch");
  const rows = Array.from(shell.querySelectorAll(".message-row"));
  if (searchInput && rows.length) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim().toLowerCase();
      rows.forEach((row) => {
        row.hidden = !!q && !row.dataset.search.includes(q);
      });
    });
  }
});
