document.addEventListener("DOMContentLoaded", () => {
  const shell = document.getElementById("secMsgShell");
  if (!shell) return;

  // Same pattern as admin-messages.js: conversation switching is a real
  // navigation (each row links to ?conversation=<id>), so only the
  // currently open thread needs live polling, not every row at once.
  const scroll = document.getElementById("secMsgThreadScroll");
  const composer = document.getElementById("secMsgComposer");
  const liveIndicator = document.getElementById("secMsgLiveIndicator");

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

  if (new URLSearchParams(window.location.search).has("conversation")) {
    shell.classList.add("thread-open");
  }
  const backBtn = shell.querySelector(".thread-back-btn");
  if (backBtn) backBtn.addEventListener("click", () => shell.classList.remove("thread-open"));

  const searchInput = document.getElementById("secMsgSearch");
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
