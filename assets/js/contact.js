document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("contactPageForm");
  if (!form) return;

  const loading = form.querySelector(".loading");
  const errorMessage = form.querySelector(".error-message");
  const sentMessage = form.querySelector(".sent-message");
  const submitBtn = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    sentMessage.hidden = true;
    sentMessage.style.display = "";
    errorMessage.textContent = "";

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    loading.hidden = false;
    loading.style.display = "block";
    submitBtn.disabled = true;

    setTimeout(() => {
      loading.hidden = true;
      loading.style.display = "";
      sentMessage.hidden = false;
      sentMessage.style.display = "block";
      submitBtn.disabled = false;
      form.reset();
    }, 700);
  });
});
