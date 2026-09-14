document.addEventListener("DOMContentLoaded", () => {
  const shell = document.getElementById("admMsgShell");
  if (!shell) return;

  // Conversation switching is a real navigation (each row is a plain link
  // to ?conversation=<id>) so the server always renders the selected
  // thread's actual history -- only the currently open thread needs live
  // polling, not every row in the list at once.
  const scroll = document.getElementById("admMsgThreadScroll");
  const composer = document.getElementById("admMsgComposer");
  const liveIndicator = document.getElementById("admMsgLiveIndicator");

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

  // Explicitly navigating to a conversation (?conversation=<id>) opens its
  // thread full-screen on mobile right away; landing on the bare Messages
  // page shows the list first, same as every other inbox on this site.
  if (new URLSearchParams(window.location.search).has("conversation")) {
    shell.classList.add("thread-open");
  }
  const backBtn = shell.querySelector(".thread-back-btn");
  if (backBtn) backBtn.addEventListener("click", () => shell.classList.remove("thread-open"));

  const searchInput = document.getElementById("adminMsgSearch");
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
