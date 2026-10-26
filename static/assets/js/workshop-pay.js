/* Paystack checkout for workshop certificate fees.
 *
 * Shared by the workshop page itself (templates/workshop/register.html),
 * so people pay without leaving it, and by the standalone checkout that the
 * emailed/texted payment link opens (templates/workshop/pay.html).
 *
 * The browser callback is UI only: a registration is marked paid solely by
 * workshop.views.pay_verify (or the Paystack webhook) after Paystack's own
 * servers confirm the reference, amount and currency.
 *
 * Expects https://js.paystack.co/v1/inline.js to be loaded first, and a
 * csrfmiddlewaretoken input somewhere on the page.
 */
(function () {
  function csrf() {
    var i = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return i ? i.value : "";
  }

  /* checkout: the dict built by workshop.views._checkout_params.
   * hooks (all optional):
   *   onVerifying()   -- the charge went through; confirming it with us
   *   onError(msg)    -- couldn't start, or couldn't confirm
   *   onClose()       -- popup closed without paying
   * On a confirmed payment the page is sent to the thank-you page. */
  function open(checkout, hooks) {
    hooks = hooks || {};
    var fail = hooks.onError || function () {};

    if (typeof PaystackPop === "undefined") {
      fail("Couldn't load the payment popup. Check your connection and try again.");
      return;
    }
    if (!checkout || !checkout.key) {
      fail("Online payment isn't configured right now. Please contact the Secretariat.");
      return;
    }

    // Always the cedi amount and currency held on the registration row --
    // any dollar figure on the page is display only and never sent.
    var handler = PaystackPop.setup({
      key: checkout.key,
      email: checkout.email,
      amount: checkout.amount,
      currency: checkout.currency,
      ref: checkout.reference,
      metadata: { custom_fields: [
        { display_name: "Workshop", variable_name: "workshop", value: checkout.workshop },
        { display_name: "Name", variable_name: "name", value: checkout.name }
      ]},
      callback: function (response) {
        if (hooks.onVerifying) hooks.onVerifying();
        fetch(checkout.verify_url, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest" },
          body: new URLSearchParams({ reference: response.reference }),
        })
          .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
          .then(function (r) {
            if (r.ok && r.data.ok) { window.location.href = r.data.redirect; }
            else { fail((r.data && r.data.error) || ("Couldn't confirm payment. Reference: " + response.reference)); }
          })
          .catch(function () {
            fail("Payment may have gone through, but we couldn't confirm it. Reference: " + response.reference);
          });
      },
      onClose: function () { if (hooks.onClose) hooks.onClose(); },
    });
    handler.openIframe();
  }

  window.MSRECWorkshopPay = { open: open };
})();
