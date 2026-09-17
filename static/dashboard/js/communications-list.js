// Client-side filter for simple card lists in the Communications section
// (Email Templates today) -- searches whatever the list's items expose
// via data-search, same convention as secretariat-messages.js.
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("templatesSearch");
  const list = document.getElementById("templatesList");
  if (!searchInput || !list) return;

  const cards = Array.from(list.querySelectorAll("[data-search]"));
  searchInput.addEventListener("input", () => {
    const q = searchInput.value.trim().toLowerCase();
    cards.forEach((card) => {
      card.hidden = !!q && !card.dataset.search.includes(q);
    });
  });
});
