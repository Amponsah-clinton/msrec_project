document.addEventListener("DOMContentLoaded", () => {

  /* ============================================================
     Category toolbar — smooth scroll + scrollspy
  ============================================================ */
  const catLinks = Array.from(document.querySelectorAll("#bcCatNav a"));
  const sections = catLinks.map((link) => document.getElementById(link.dataset.cat)).filter(Boolean);

  catLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const target = document.getElementById(link.dataset.cat);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + target.id);
    });
  });

  const SCROLLSPY_OFFSET = 185; // sticky toolbar + section scroll-margin-top
  function refreshActiveCat() {
    let activeId = sections[0] && sections[0].id;
    for (const s of sections) {
      if (s.getBoundingClientRect().top <= SCROLLSPY_OFFSET) activeId = s.id;
      else break;
    }
    catLinks.forEach((l) => l.classList.toggle("is-active", l.dataset.cat === activeId));
  }
  let ticking = false;
  window.addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { refreshActiveCat(); ticking = false; });
  }, { passive: true });
  refreshActiveCat();

  /* ============================================================
     Member profiles — filter by group (All / Board / Committee / Secretariat)
  ============================================================ */
  const filterBtns = Array.from(document.querySelectorAll(".bc-filter-btn"));
  const people = Array.from(document.querySelectorAll(".bc-person"));

  filterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      filterBtns.forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      const group = btn.dataset.group;
      people.forEach((p) => {
        p.classList.toggle("is-hidden", group !== "all" && p.dataset.group !== group);
      });
    });
  });
});
