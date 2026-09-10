document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("signupForm");
  if (!form) return;

  /* ============================================================
     Tag input (Primary Research Area / Areas of Expertise / etc.)
  ============================================================ */
  function initTagInput(container) {
    const name = container.dataset.name;
    const list = container.querySelector(".tag-list");
    const input = container.querySelector('input[type="text"]');
    const hidden = container.parentElement.querySelector(`input[type="hidden"][name="${name}"]`);
    let tags = [];

    function render() {
      list.innerHTML = "";
      tags.forEach((tag, i) => {
        const chip = document.createElement("span");
        chip.className = "tag-chip";
        chip.innerHTML = `<span>${tag}</span>`;
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.setAttribute("aria-label", `Remove ${tag}`);
        removeBtn.innerHTML = "&times;";
        removeBtn.addEventListener("click", () => {
          tags.splice(i, 1);
          render();
        });
        chip.appendChild(removeBtn);
        list.appendChild(chip);
      });
      hidden.value = tags.join(", ");
    }

    function addTag(raw) {
      const value = raw.trim().replace(/,+$/, "");
      if (value && !tags.includes(value)) {
        tags.push(value);
        render();
      }
      input.value = "";
    }

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        addTag(input.value);
      } else if (e.key === "Backspace" && !input.value && tags.length) {
        tags.pop();
        render();
      }
    });
    input.addEventListener("blur", () => {
      if (input.value.trim()) addTag(input.value);
    });
  }
  document.querySelectorAll(".tag-input").forEach(initTagInput);

  /* ============================================================
     Committee expertise chip checkboxes
  ============================================================ */
  const committeeCategoryBoxes = Array.from(
    document.querySelectorAll('input[name="committeeExpertiseCategory"]')
  );
  const committeeCategoryError = document.getElementById("committeeCategoryError");
  const layCommunityCheckbox = document.getElementById("layCommunityCheckbox");

  committeeCategoryBoxes.forEach((box) => {
    box.addEventListener("change", () => {
      box.closest(".chip-checkbox").classList.toggle("checked", box.checked);
      if (committeeCategoryBoxes.some((b) => b.checked)) committeeCategoryError.hidden = true;
      applyCommitteeConditionalRequirements();
    });
  });

  /* ============================================================
     Role toggling — show/hide the three role-specific sections
  ============================================================ */
  const roleCheckboxes = Array.from(form.querySelectorAll(".role-checkbox"));
  const roleError = document.getElementById("roleError");
  const rcDeclarations = document.getElementById("rcDeclarations");
  const confirmConfidentiality = document.getElementById("confirmConfidentiality");
  const confirmCoi = document.getElementById("confirmCoi");

  function fieldsIn(section) {
    return Array.from(section.querySelectorAll("input, select, textarea"));
  }

  function isRoleChecked(value) {
    return roleCheckboxes.some((c) => c.value === value && c.checked);
  }

  function toggleRoleSection(checkbox) {
    const target = document.getElementById(checkbox.dataset.target);
    if (!target) return;
    const show = checkbox.checked;
    target.hidden = !show;
    fieldsIn(target).forEach((field) => {
      if (field.hasAttribute("data-require-on-show")) {
        field.required = show;
      }
    });

    if (checkbox.value === "applicant") applyApplicantConditionalRequirements();
    if (checkbox.value === "reviewer") applyReviewerConditionalRequirements();
    if (checkbox.value === "committee") applyCommitteeConditionalRequirements();
  }

  function updateDeclarationsVisibility() {
    const needsDeclarations = isRoleChecked("reviewer") || isRoleChecked("committee");
    rcDeclarations.hidden = !needsDeclarations;
    confirmConfidentiality.required = needsDeclarations;
    confirmCoi.required = needsDeclarations;
    if (!needsDeclarations) {
      confirmConfidentiality.checked = false;
      confirmCoi.checked = false;
    }
  }

  roleCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      toggleRoleSection(checkbox);
      updateDeclarationsVisibility();
      if (roleCheckboxes.some((c) => c.checked)) roleError.hidden = true;
    });
  });

  /* ============================================================
     Personal / Institution section — required-field tags
  ============================================================ */
  [
    "firstName",
    "lastName",
    "email",
    "confirmEmail",
    "phone",
    "countryResidence",
    "highestQualification",
    "password",
    "confirmPassword",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.required = true;
  });

  /* ============================================================
     Independent researcher / reviewer toggles
  ============================================================ */
  const noInstitution = document.getElementById("noInstitution");
  const institution = document.getElementById("institution");
  const department = document.getElementById("department");
  const institutionReqTag = document.getElementById("institutionReqTag");
  const departmentReqTag = document.getElementById("departmentReqTag");

  function applyInstitutionRequirement() {
    const independent = noInstitution.checked;
    institution.required = !independent;
    department.required = !independent;
    institutionReqTag.hidden = independent;
    departmentReqTag.hidden = independent;
  }
  noInstitution.addEventListener("change", applyInstitutionRequirement);
  applyInstitutionRequirement();

  const independentReviewer = document.getElementById("independentReviewer");
  const reviewerInstitution = document.getElementById("reviewerInstitution");
  const reviewerInstitutionReqTag = document.getElementById("reviewerInstitutionReqTag");

  function applyReviewerInstitutionRequirement() {
    const independent = independentReviewer.checked;
    reviewerInstitution.required = isRoleChecked("reviewer") && !independent;
    reviewerInstitutionReqTag.hidden = independent;
  }
  independentReviewer.addEventListener("change", applyReviewerInstitutionRequirement);

  /* ============================================================
     Applicant conditional logic
  ============================================================ */
  const applicantCategory = document.getElementById("applicantCategory");
  const studentFields = Array.from(document.querySelectorAll(".student-field"));
  const STUDENT_CATEGORIES = ["undergraduate", "postgraduate"];

  function applyApplicantConditionalRequirements() {
    const active = isRoleChecked("applicant");
    applicantCategory.required = active;

    const isStudent = active && STUDENT_CATEGORIES.includes(applicantCategory.value);
    studentFields.forEach((field) => {
      field.hidden = !isStudent;
    });
    const academicProgramme = document.getElementById("academicProgramme");
    const degreeLevel = document.getElementById("degreeLevel");
    academicProgramme.required = isStudent;
    degreeLevel.required = isStudent;
    // Supervisor fields are intentionally left optional at signup — they can be
    // completed later during application submission.
  }
  applicantCategory.addEventListener("change", applyApplicantConditionalRequirements);

  /* ============================================================
     Reviewer conditional logic — prior ethics review experience
  ============================================================ */
  const reviewerPriorExperience = document.getElementById("reviewerPriorExperience");
  const reviewerCommitteeExperienceField = document.getElementById("field-reviewerCommitteeExperience");

  function applyReviewerConditionalRequirements() {
    const active = isRoleChecked("reviewer");
    ["reviewerPosition", "reviewerDiscipline", "reviewerYearsProfessional", "reviewerPriorExperience"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.required = active;
    });
    document.getElementById("reviewerCv").required = active;
    applyReviewerInstitutionRequirement();

    reviewerCommitteeExperienceField.hidden = reviewerPriorExperience.value !== "yes";
  }
  reviewerPriorExperience.addEventListener("change", () => {
    reviewerCommitteeExperienceField.hidden = reviewerPriorExperience.value !== "yes";
  });

  /* ============================================================
     Committee conditional logic
  ============================================================ */
  const committeeEthicsExperience = document.getElementById("committeeEthicsExperience");
  const committeeEthicsDetailsField = document.getElementById("field-committeeEthicsDetails");
  const committeeInstitution = document.getElementById("committeeInstitution");
  const committeeInstitutionReqTag = document.getElementById("committeeInstitutionReqTag");
  const committeeCv = document.getElementById("committeeCv");
  const committeeCvReqTag = document.getElementById("committeeCvReqTag");

  function applyCommitteeConditionalRequirements() {
    const active = isRoleChecked("committee");
    ["committeePosition", "committeeYears", "committeeEthicsExperience", "committeeBackground"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.required = active;
    });

    const isLayCommunity = layCommunityCheckbox.checked;
    committeeInstitution.required = active && !isLayCommunity;
    committeeCv.required = active && !isLayCommunity;
    committeeInstitutionReqTag.hidden = isLayCommunity;
    committeeCvReqTag.hidden = isLayCommunity;

    committeeEthicsDetailsField.hidden = committeeEthicsExperience.value !== "yes";
  }
  committeeEthicsExperience.addEventListener("change", () => {
    committeeEthicsDetailsField.hidden = committeeEthicsExperience.value !== "yes";
  });

  /* ============================================================
     Submit
  ============================================================ */
  const STATUS_MESSAGES = {
    applicant: {
      title: "Applicant / Researcher",
      badge: "Active after verification",
      desc: "Your account will be activated once you verify your email address.",
    },
    reviewer: {
      title: "Reviewer",
      badge: "Pending Verification",
      desc: "Your reviewer profile is pending MSREC verification before you can be assigned protocols.",
    },
    committee: {
      title: "Committee Member",
      badge: "Pending MSREC Verification",
      desc: "Your committee membership is pending MSREC verification and appointment confirmation.",
    },
  };

  const emailInput = document.getElementById("email");
  const confirmEmailInput = document.getElementById("confirmEmail");
  const emailMatchError = document.getElementById("emailMatchError");
  const passwordInput = document.getElementById("password");
  const confirmPasswordInput = document.getElementById("confirmPassword");
  const passwordMatchError = document.getElementById("passwordMatchError");

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const selectedRoles = roleCheckboxes.filter((c) => c.checked).map((c) => c.value);
    if (selectedRoles.length === 0) {
      roleError.hidden = false;
      roleError.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    if (isRoleChecked("committee") && !committeeCategoryBoxes.some((b) => b.checked)) {
      committeeCategoryError.hidden = false;
      committeeCategoryError.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    // Hidden inputs are always excluded from native constraint validation, so
    // the tag-input-backed fields need their own explicit required checks.
    const tagFieldChecks = [
      { name: "primaryResearchArea", active: isRoleChecked("applicant"), errorId: "primaryResearchAreaError" },
      { name: "reviewerExpertise", active: isRoleChecked("reviewer"), errorId: "reviewerExpertiseError" },
      { name: "reviewerResearchAreas", active: isRoleChecked("reviewer"), errorId: "reviewerResearchAreasError" },
    ];
    let tagFieldFailed = false;
    tagFieldChecks.forEach(({ name, active, errorId }) => {
      const hidden = form.querySelector(`input[type="hidden"][name="${name}"]`);
      const errorEl = document.getElementById(errorId);
      const missing = active && !hidden.value.trim();
      errorEl.classList.toggle("show", missing);
      if (missing) tagFieldFailed = true;
    });
    if (tagFieldFailed) {
      form.querySelector(".field-error.show").scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    const emailsMatch = emailInput.value === confirmEmailInput.value;
    emailMatchError.classList.toggle("show", !emailsMatch);
    const passwordsMatch = passwordInput.value === confirmPasswordInput.value;
    passwordMatchError.classList.toggle("show", !passwordsMatch);

    if (!emailsMatch || !passwordsMatch) {
      (!emailsMatch ? confirmEmailInput : confirmPasswordInput).focus();
      return;
    }

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const submitBtn = form.querySelector(".btn-create-account");
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Creating account...";

    setTimeout(() => {
      showConfirmation(selectedRoles);
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }, 700);
  });

  emailInput.addEventListener("input", () => emailMatchError.classList.remove("show"));
  confirmEmailInput.addEventListener("input", () => emailMatchError.classList.remove("show"));
  passwordInput.addEventListener("input", () => passwordMatchError.classList.remove("show"));
  confirmPasswordInput.addEventListener("input", () => passwordMatchError.classList.remove("show"));

  function showConfirmation(selectedRoles) {
    const formView = document.getElementById("signupFormView");
    const confirmView = document.getElementById("signupConfirmView");
    const list = document.getElementById("confirmStatusList");

    list.innerHTML = "";
    selectedRoles.forEach((role) => {
      const info = STATUS_MESSAGES[role];
      if (!info) return;
      const li = document.createElement("li");
      li.innerHTML = `
        <i class="bi bi-hourglass-split"></i>
        <span>
          <span class="status-badge">${info.badge}</span>
          <strong>${info.title}</strong>
          <span class="status-desc">${info.desc}</span>
        </span>
      `;
      list.appendChild(li);
    });

    formView.hidden = true;
    confirmView.hidden = false;
    confirmView.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});
