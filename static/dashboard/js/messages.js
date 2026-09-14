document.addEventListener("DOMContentLoaded", () => {
  const shell = document.getElementById("msgShell");
  if (!shell) return;

  const scroll = document.getElementById("msgThreadScroll");
  const composer = document.getElementById("msgComposer");
  const liveIndicator = document.getElementById("msgLiveIndicator");
  const listTime = document.getElementById("msgListTime");
  const listSnippet = document.getElementById("msgListSnippet");

  let lastId = parseInt(shell.dataset.lastId, 10) || 0;

  function onMessage(message) {
    const empty = scroll.querySelector(".msg-thread-empty");
    if (empty) empty.remove();
    scroll.appendChild(createMessageBubble(message));
    if (listTime) listTime.textContent = message.time_display;
    if (listSnippet) {
      listSnippet.textContent = message.body.length > 60 ? message.body.slice(0, 60) + "…" : message.body;
    }
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
});
