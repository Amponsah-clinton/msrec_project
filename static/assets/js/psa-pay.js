/* Paystack checkout for Professional Service Agreement balances.
 *
 * Opened from the secure payment link a client is emailed
 * (templates/psa/pay.html). Deliberately separate from workshop-pay.js:
 * the two flows verify against different endpoints and carry different
 * metadata, and a change to one must not be able to break the other's
 * ability to take money.
 *
 * The browser callback is UI only. A payment is banked solely by
 * psa.views.pay_verify, after Paystack's own servers confirm the
 * reference, amount and currency against the PaymentRequest row. Nothing
 * on this page decides what is charged -- every value in `checkout` was
 * rendered from the server row.
 *
 * Expects https://js.paystack.co/v1/inline.js to be loaded first, and a
 * csrfmiddlewaretoken input somewhere on the page.
 */
(function () {
  function csrf() {
    var i = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return i ? i.value : "";
  }

  /* checkout: the dict built by psa.views._checkout_params.
   * hooks (all optional):
   *   onVerifying()  -- the charge went through; confirming it with us
   *   onError(msg)   -- couldn't start, or couldn't confirm
   *   onClose()      -- popup closed without paying
   * On a confirmed payment the page reloads onto the receipt. */
  function open(checkout, hooks) {
    hooks = hooks || {};
    var fail = hooks.onError || function () {};

    if (typeof PaystackPop === "undefined") {
      fail("Couldn't load the payment window. Check your connection and try again.");
      return;
    }
    if (!checkout || !checkout.key) {
      fail("Online payment isn't available right now. Please contact Metascholar Limited.");
      return;
    }

    var handler = PaystackPop.setup({
      key: checkout.key,
      email: checkout.email,
      amount: checkout.amount,
      currency: checkout.currency,
      ref: checkout.reference,
      metadata: { custom_fields: [
        { display_name: "Agreement", variable_name: "agreement", value: checkout.agreement },
        { display_name: "Client", variable_name: "client", value: checkout.name }
      ]},
      callback: function (response) {
        if (hooks.onVerifying) hooks.onVerifying();
        fetch(checkout.verify_url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-CSRFToken": csrf(),
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest"
          },
          body: new URLSearchParams({ reference: response.reference }),
        })
          .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, data: d }; }); })
          .then(function (r) {
            if (r.ok && r.data.ok) { window.location.href = r.data.redirect; }
            else { fail((r.data && r.data.error) || ("Couldn't confirm the payment. Reference: " + response.reference)); }
          })
          .catch(function () {
            fail("Your payment may have gone through, but we couldn't confirm it here. "
               + "Please contact Metascholar Limited quoting reference " + response.reference + ".");
          });
      },
      onClose: function () { if (hooks.onClose) hooks.onClose(); },
    });
    handler.openIframe();
  }

  window.MSRECPsaPay = { open: open };
})();
