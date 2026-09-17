document.addEventListener("DOMContentLoaded", () => {
  const editOverlay = document.getElementById("teamEditOverlay");
  const editForm = document.getElementById("teamEditForm");
  if (!editOverlay || !editForm) return;

  const closeEdit = () => { editOverlay.hidden = true; };
  const currentPhotoWrap = document.getElementById("teamEditCurrentPhoto");
  const currentPhotoImg = document.getElementById("teamEditCurrentPhotoImg");

  document.querySelectorAll("[data-team-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".team-row");
      if (!row) return;
      document.getElementById("teamEditMemberId").value = row.dataset.memberId;
      document.getElementById("teamEditFullName").value = row.dataset.fullName;
      document.getElementById("teamEditEmail").value = row.dataset.email;
      document.getElementById("teamEditRole").value = row.dataset.role;
      document.getElementById("teamEditInstitution").value = row.dataset.institution;

      if (row.dataset.photoUrl) {
        currentPhotoImg.src = row.dataset.photoUrl;
        currentPhotoWrap.hidden = false;
      } else {
        currentPhotoWrap.hidden = true;
      }

      editOverlay.hidden = false;
    });
  });

  document.getElementById("teamEditClose").addEventListener("click", closeEdit);
  document.getElementById("teamEditCancel").addEventListener("click", closeEdit);
  editOverlay.addEventListener("click", (event) => {
    if (event.target === editOverlay) closeEdit();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !editOverlay.hidden) closeEdit();
  });
});
