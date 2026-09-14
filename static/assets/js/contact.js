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

    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((res) => res.json().then((data) => ({ status: res.status, data })))
      .then(({ status, data }) => {
        loading.hidden = true;
        loading.style.display = "";
        submitBtn.disabled = false;

        if (status === 200 && data.ok) {
          sentMessage.hidden = false;
          sentMessage.style.display = "block";
          form.reset();
        } else {
          const firstError = data.errors && Object.values(data.errors)[0];
          errorMessage.textContent = firstError || "Something went wrong. Please try again.";
        }
      })
      .catch(() => {
        loading.hidden = true;
        loading.style.display = "";
        submitBtn.disabled = false;
        errorMessage.textContent = "Couldn't reach the server. Please check your connection and try again.";
      });
  });
});
