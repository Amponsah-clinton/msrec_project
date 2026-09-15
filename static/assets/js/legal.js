document.addEventListener("DOMContentLoaded", () => {

  /* ============================================================
     Reading progress bar
  ============================================================ */
  const progress = document.getElementById("legalProgress");
  function refreshProgress() {
    if (!progress) return;
    const doc = document.documentElement;
    const scrollable = doc.scrollHeight - doc.clientHeight;
    const pct = scrollable > 0 ? (doc.scrollTop / scrollable) * 100 : 0;
    progress.style.width = pct + "%";
  }

  /* ============================================================
     TOC (sidebar + mobile toolbar) — smooth scroll + scrollspy
  ============================================================ */
  const tocLinks = Array.from(document.querySelectorAll(".legal-toc-list a, .legal-toolbar a"));
  const sections = Array.from(document.querySelectorAll(".legal-section"));

  tocLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const id = link.getAttribute("href").slice(1);
      const target = document.getElementById(id);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + id);
    });
  });

  const SCROLLSPY_OFFSET = 130;
  function refreshActiveSection() {
    let activeId = sections[0] && sections[0].id;
    for (const s of sections) {
      if (s.getBoundingClientRect().top <= SCROLLSPY_OFFSET) activeId = s.id;
      else break;
    }
    tocLinks.forEach((l) => l.classList.toggle("is-active", l.getAttribute("href") === "#" + activeId));
  }

  let ticking = false;
  window.addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { refreshActiveSection(); refreshProgress(); ticking = false; });
  }, { passive: true });

  refreshActiveSection();
  refreshProgress();

  /* ============================================================
     Copy-link buttons on each section heading
  ============================================================ */
  const toast = document.getElementById("legalToast");
  let toastTimer = null;

  document.querySelectorAll(".legal-anchor-btn").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const id = btn.dataset.section;
      const url = window.location.origin + window.location.pathname + "#" + id;
      try {
        await navigator.clipboard.writeText(url);
      } catch (err) {
        // Clipboard API unavailable (e.g. insecure context) -- the URL
        // hash still updates below, so the link is copyable by hand.
      }
      history.replaceState(null, "", "#" + id);
      btn.classList.add("is-copied");
      setTimeout(() => btn.classList.remove("is-copied"), 1200);
      if (toast) {
        toast.classList.add("is-visible");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 1800);
      }
    });
  });

  /* ============================================================
     Print / save as PDF
  ============================================================ */
  document.querySelectorAll("[data-legal-print]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      window.print();
    });
  });

  /* ============================================================
     Land on the right section when arriving with a #hash
  ============================================================ */
  if (window.location.hash) {
    const target = document.getElementById(window.location.hash.slice(1));
    if (target) setTimeout(() => target.scrollIntoView({ block: "start" }), 50);
  }
});
