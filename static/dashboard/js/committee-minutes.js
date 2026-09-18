document.addEventListener("DOMContentLoaded", () => {
  const doc = document.querySelector(".mn-doc[data-status-url]");
  const banner = document.getElementById("mnBanner");
  if (!doc || !banner) return;
  const known = doc.dataset.stamp;
  const check = () => {
    if (document.hidden) return;
    fetch(doc.dataset.statusUrl, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && d.exists && new Date(d.stamp).getTime() > new Date(known).getTime() + 999) banner.hidden = false;
      })
      .catch(() => {});
  };
  setInterval(check, 30000);
});
