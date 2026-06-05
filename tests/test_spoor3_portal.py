"""Categorie C — Spoor 3 Stripe Customer Portal regressietests.

Acht tests rond /account/manage-subscription en de conditionele knop
op /licentie. Alle Stripe-API-aanroepen worden gemockt — er gaat geen
verkeer naar billing.stripe.com en er worden geen DB-rijen aangepast.

    C1 — Niet-ingelogd → redirect naar /login
    C2 — Geen customer_id → redirect /licentie?error=no_stripe_subscription
    C3 — Met customer_id → redirect naar billing.stripe.com (gemockt)
    C4 — StripeError → redirect /licentie?error=portal_unavailable
    C5 — Session.create krijgt locale uit session['lang']
    C6 — Knop "Abonnement beheren" zichtbaar voor Stripe-user op /licentie
    C7 — Knop verborgen voor PayPal/manual-user op /licentie
    C8 — Oude /abonnement/opzeggen → 302 /licentie?error=use_new_flow
"""

import sys
import time
import unittest.mock as _mock

sys.path.insert(0, "/opt/stresschecker")
sys.path.insert(0, "/opt/stresschecker/tests")

import app as _app  # noqa: E402
import stripe as _stripe_mod  # noqa: E402


def _report(name, ok, reason):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}: {reason}")
    return ok


def _client():
    _app.app.config["TESTING"] = True
    return _app.app.test_client()


def _login(client, user_key="C_STRIPE_USER", lang="nl", email="stripe-user@example.com"):
    with client.session_transaction() as s:
        s["user_key"] = user_key
        s["lang"] = lang
        s["email"] = email


def c1_unauthenticated_redirects_to_login():
    name = "C1 niet-ingelogd → /login"
    client = _client()
    r = client.get("/account/manage-subscription")
    if r.status_code != 302:
        return _report(name, False, f"verwachte 302, kreeg {r.status_code}")
    loc = r.headers.get("Location", "")
    if "/login" not in loc:
        return _report(name, False, f"verwachte /login in Location, kreeg {loc!r}")
    return _report(name, True, f"302 → {loc}")


def c2_no_customer_redirects_with_error_code():
    name = "C2 geen customer_id → /licentie?error=no_stripe_subscription"
    client = _client()
    _login(client)
    with _mock.patch.object(_app, "get_stripe_customer_id", return_value=None):
        r = client.get("/account/manage-subscription")
    if r.status_code != 302:
        return _report(name, False, f"verwachte 302, kreeg {r.status_code}")
    loc = r.headers.get("Location", "")
    if "/licentie" not in loc or "error=no_stripe_subscription" not in loc:
        return _report(name, False, f"onverwachte Location: {loc!r}")
    return _report(name, True, f"302 → {loc}")


def c3_with_customer_redirects_to_billing_portal():
    name = "C3 met customer → redirect naar billing.stripe.com"
    client = _client()
    _login(client)
    fake_session = _mock.MagicMock()
    fake_session.url = "https://billing.stripe.com/p/session/test_xyz123"
    with _mock.patch.object(_app, "get_stripe_customer_id", return_value="cus_TEST"), \
         _mock.patch.object(_app, "_load_stripe_secret", return_value="sk_test_dummy"), \
         _mock.patch.object(_stripe_mod.billing_portal.Session, "create", return_value=fake_session) as mk:
        r = client.get("/account/manage-subscription")
    if r.status_code != 302:
        return _report(name, False, f"verwachte 302, kreeg {r.status_code}")
    loc = r.headers.get("Location", "")
    if "billing.stripe.com" not in loc:
        return _report(name, False, f"verwachte billing.stripe.com in Location, kreeg {loc!r}")
    if not mk.called:
        return _report(name, False, "stripe.billing_portal.Session.create NIET aangeroepen")
    kwargs = mk.call_args.kwargs
    if kwargs.get("customer") != "cus_TEST":
        return _report(name, False, f"customer kwarg verkeerd: {kwargs.get('customer')!r}")
    if kwargs.get("configuration") != "bpc_1TVpFcHD28PM4o1K18URnQAI":
        return _report(name, False, f"configuration kwarg verkeerd: {kwargs.get('configuration')!r}")
    return _report(name, True, f"302 → {loc} | configuration + customer kwarg correct")


def c4_stripe_error_redirects_with_portal_unavailable():
    name = "C4 StripeError → /licentie?error=portal_unavailable"
    client = _client()
    _login(client)
    err = _stripe_mod.error.StripeError("simulated portal failure")
    with _mock.patch.object(_app, "get_stripe_customer_id", return_value="cus_TEST"), \
         _mock.patch.object(_app, "_load_stripe_secret", return_value="sk_test_dummy"), \
         _mock.patch.object(_stripe_mod.billing_portal.Session, "create", side_effect=err):
        r = client.get("/account/manage-subscription")
    if r.status_code != 302:
        return _report(name, False, f"verwachte 302, kreeg {r.status_code}")
    loc = r.headers.get("Location", "")
    if "/licentie" not in loc or "error=portal_unavailable" not in loc:
        return _report(name, False, f"onverwachte Location: {loc!r}")
    return _report(name, True, f"302 → {loc}")


def c5_locale_is_passed_to_session_create():
    name = "C5 locale uit session['lang'] doorgegeven aan Session.create"
    fake_session = _mock.MagicMock()
    fake_session.url = "https://billing.stripe.com/p/session/test_locale"
    expected = {"de": "de", "en": "en", "nl": "nl"}
    for lang, want in expected.items():
        client = _client()
        _login(client, lang=lang)
        with _mock.patch.object(_app, "get_stripe_customer_id", return_value="cus_TEST"), \
             _mock.patch.object(_app, "_load_stripe_secret", return_value="sk_test_dummy"), \
             _mock.patch.object(_stripe_mod.billing_portal.Session, "create",
                                return_value=fake_session) as mk:
            r = client.get("/account/manage-subscription")
        if r.status_code != 302:
            return _report(name, False, f"lang={lang}: verwachte 302, kreeg {r.status_code}")
        got = (mk.call_args.kwargs or {}).get("locale")
        if got != want:
            return _report(name, False, f"lang={lang}: locale kwarg={got!r}, verwachte {want!r}")
    return _report(name, True, "locale=de/en/nl correct doorgegeven voor alle drie talen")


def c6_button_visible_for_stripe_user():
    name = "C6 knop zichtbaar voor Stripe-user op /licentie"
    client = _client()
    _login(client)
    with _mock.patch.object(_app, "has_stripe_subscription", return_value=True):
        r = client.get("/licentie")
    if r.status_code != 200:
        return _report(name, False, f"verwachte 200, kreeg {r.status_code}")
    body = r.data
    if b"/account/manage-subscription" not in body:
        return _report(name, False, "href naar manage-subscription ontbreekt in response body")
    if b"Abonnement beheren" not in body:
        return _report(name, False, "NL knop-label 'Abonnement beheren' ontbreekt")
    return _report(name, True, "button + NL label aanwezig in render")


def c7_button_hidden_for_paypal_user():
    name = "C7 knop verborgen voor PayPal/manual-user op /licentie"
    client = _client()
    _login(client, user_key="C_PAYPAL_USER")
    with _mock.patch.object(_app, "has_stripe_subscription", return_value=False):
        r = client.get("/licentie")
    if r.status_code != 200:
        return _report(name, False, f"verwachte 200, kreeg {r.status_code}")
    if b"/account/manage-subscription" in r.data:
        return _report(name, False, "href naar manage-subscription mag NIET in response zitten")
    return _report(name, True, "button correct verborgen")


def c8_old_opzeg_route_redirects_to_license_with_use_new_flow():
    name = "C8 oude /abonnement/opzeggen → /licentie?error=use_new_flow"
    client = _client()
    r = client.get("/abonnement/opzeggen")
    if r.status_code != 302:
        return _report(name, False, f"verwachte 302, kreeg {r.status_code}")
    loc = r.headers.get("Location", "")
    if "/licentie" not in loc or "error=use_new_flow" not in loc:
        return _report(name, False, f"onverwachte Location: {loc!r}")
    return _report(name, True, f"302 → {loc}")


TESTS = [
    c1_unauthenticated_redirects_to_login,
    c2_no_customer_redirects_with_error_code,
    c3_with_customer_redirects_to_billing_portal,
    c4_stripe_error_redirects_with_portal_unavailable,
    c5_locale_is_passed_to_session_create,
    c6_button_visible_for_stripe_user,
    c7_button_hidden_for_paypal_user,
    c8_old_opzeg_route_redirects_to_license_with_use_new_flow,
]


def main():
    passed = failed = 0
    start = time.time()
    for t in TESTS:
        try:
            ok = t()
        except Exception as e:
            import traceback
            print(f"[FAIL] {t.__name__}: onverwachte exception: {e}")
            traceback.print_exc()
            ok = False
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    dur = time.time() - start
    print(f"\ncategorie C: {passed} passed, {failed} failed  ({dur:.1f}s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
