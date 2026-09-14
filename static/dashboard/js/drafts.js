// Confirmation before deleting a draft (form[data-confirm] below the
// "Delete" button in application-drafts.html) is handled by the generic
// data-confirm modal registered once in dashboard/js/script.js -- it
// intercepts every form[data-confirm] on the page, not just this one, so
// there's nothing left to wire up here. Kept as a file (rather than
// removing the <script> tag) in case this page grows draft-specific JS
// later.
