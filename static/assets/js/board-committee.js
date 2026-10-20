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
     Member profiles — filter by group (All / Board / Committee / Secretariat / Reviewers)
  ============================================================ */
  const filterBtns = Array.from(document.querySelectorAll(".bc-filter-btn"));
  const people = Array.from(document.querySelectorAll(".bc-person"));

  // Reviewers who already have a Board/Committee/Secretariat card only
  // show under the Reviewers tab, so "All" doesn't list anyone twice.
  function applyFilter(group) {
    people.forEach((p) => {
      const hidden = group === "all"
        ? p.hasAttribute("data-also-member")
        : p.dataset.group !== group;
      p.classList.toggle("is-hidden", hidden);
    });
  }
  applyFilter("all");

  filterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      filterBtns.forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      applyFilter(btn.dataset.group);
    });
  });

  /* ============================================================
     Member photo viewer — click a photo to see it full size, with
     an X to close and arrows to step through everyone shown under
     the current filter.
  ============================================================ */
  const lb = document.getElementById("bcLightbox");
  if (!lb) return;
  const lbPanel = lb.querySelector(".bc-lightbox-panel");
  const lbImg = document.getElementById("bcLbImg");
  const lbName = document.getElementById("bcLbName");
  const lbRole = document.getElementById("bcLbRole");
  const lbInst = document.getElementById("bcLbInst");
  const lbPrev = document.getElementById("bcLbPrev");
  const lbNext = document.getElementById("bcLbNext");
  const lbCount = document.getElementById("bcLbCount");
  let gallery = [];
  let index = 0;
  let opener = null;

  // Only the photos the visitor can currently see -- honouring the filter.
  const visiblePhotos = () => Array.from(document.querySelectorAll(".bc-photo-btn"))
    .filter((b) => !b.closest(".bc-person").classList.contains("is-hidden"));

  function show(i) {
    index = (i + gallery.length) % gallery.length;
    const b = gallery[index];
    lbImg.classList.add("is-swapping");
    const next = new Image();
    next.onload = next.onerror = () => {
      lbImg.src = b.dataset.photo;
      lbImg.alt = b.dataset.name;
      lbImg.classList.remove("is-swapping");
    };
    next.src = b.dataset.photo;
    lbName.textContent = b.dataset.name;
    lbRole.textContent = b.dataset.role;
    lbRole.hidden = !b.dataset.role;
    lbInst.hidden = !b.dataset.inst;
    lbInst.querySelector("span").textContent = b.dataset.inst;
    const many = gallery.length > 1;
    lbPrev.hidden = lbNext.hidden = !many;
    lbCount.textContent = many ? `${index + 1} of ${gallery.length}` : "";
  }

  function openViewer(btn) {
    gallery = visiblePhotos();
    opener = btn;
    show(Math.max(0, gallery.indexOf(btn)));
    lb.classList.add("is-open");
    lb.setAttribute("aria-hidden", "false");
    document.body.classList.add("bc-lightbox-lock");
    setTimeout(() => lb.querySelector(".bc-lightbox-x").focus(), 40);
  }

  function closeViewer() {
    if (!lb.classList.contains("is-open")) return;
    lb.classList.remove("is-open");
    lb.setAttribute("aria-hidden", "true");
    document.body.classList.remove("bc-lightbox-lock");
    if (opener) opener.focus();
  }

  document.querySelectorAll(".bc-photo-btn").forEach((btn) => {
    btn.addEventListener("click", () => openViewer(btn));
  });
  lb.querySelectorAll("[data-lb-close]").forEach((el) => el.addEventListener("click", closeViewer));
  lbPrev.addEventListener("click", () => show(index - 1));
  lbNext.addEventListener("click", () => show(index + 1));

  document.addEventListener("keydown", (e) => {
    if (!lb.classList.contains("is-open")) return;
    if (e.key === "Escape") { e.preventDefault(); closeViewer(); }
    else if (e.key === "ArrowLeft" && gallery.length > 1) { e.preventDefault(); show(index - 1); }
    else if (e.key === "ArrowRight" && gallery.length > 1) { e.preventDefault(); show(index + 1); }
    else if (e.key === "Tab") {
      // Keep focus inside the viewer while it's open.
      const focusable = Array.from(lbPanel.querySelectorAll("button")).filter((b) => !b.hidden);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  // Swipe left / right on a phone.
  let touchX = null;
  lbPanel.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
  lbPanel.addEventListener("touchend", (e) => {
    if (touchX === null || gallery.length < 2) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
    touchX = null;
  });
});
