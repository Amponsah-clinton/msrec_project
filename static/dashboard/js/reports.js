// Reports & Analytics -- one page, seven tabs, all rendered server-side
// up front (the data volume here is small enough that pre-rendering
// every tab beats a round trip on every click). Switching tabs is just
// show/hide, with the active one remembered in the URL hash so a
// reload or a shared link lands back on the same report.
document.addEventListener("DOMContentLoaded", () => {
  const nav = document.getElementById("reportTabs");
  if (!nav) return;

  const tabs = Array.from(nav.querySelectorAll(".report-tab"));
  const sections = Array.from(document.querySelectorAll(".report-section"));

  // The sidebar's Reports & Analytics sublinks all point at this same
  // page, differing only by #hash -- clicking one while already on the
  // page is a same-document navigation (no reload), so the only way to
  // know it happened is the hashchange event below. Without it, every
  // sublink except the one you loaded the page on looked dead.
  const sidebarLinks = Array.from(document.querySelectorAll('.nav-sublink[href*="#"]'));

  function activate(key) {
    let matched = false;
    tabs.forEach((tab) => {
      const isMatch = tab.dataset.tab === key;
      tab.classList.toggle("active", isMatch);
      tab.setAttribute("aria-selected", isMatch ? "true" : "false");
      if (isMatch) matched = true;
    });
    sections.forEach((section) => {
      section.hidden = section.dataset.reportSection !== key;
    });
    sidebarLinks.forEach((link) => {
      link.classList.toggle("active", link.getAttribute("href").endsWith(`#${key}`));
    });
    if (matched) history.replaceState(null, "", `#${key}`);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activate(tab.dataset.tab));
  });

  const validKeys = tabs.map((t) => t.dataset.tab);

  window.addEventListener("hashchange", () => {
    const key = (window.location.hash || "").replace("#", "");
    if (validKeys.includes(key)) activate(key);
  });

  const initial = (window.location.hash || "").replace("#", "");
  activate(validKeys.includes(initial) ? initial : validKeys[0]);
});
