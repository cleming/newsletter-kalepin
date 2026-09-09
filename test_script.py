"""Minimal checks, no framework needed: `python test_script.py` (pytest works too)."""

import os
import shutil
import tempfile
import types
from unittest import mock

import script

HERE = os.path.dirname(os.path.abspath(__file__))


def _event(**overrides):
    ev = {
        "title": "Titre",
        "description": "",
        "beginsOn": "2026-09-10T17:30:00Z",
        "endsOn": "2026-09-10T19:30:00Z",
        "picture": None,
        "url": "https://mobilizon.example.org/events/x",
        "physicalAddress": None,
    }
    ev.update(overrides)
    return ev


def test_description_keeps_word_boundaries_across_tags():
    raw = "<p>acteur de sa vie.</p><p>Né à la<br>ferme</p>"
    ev = script.prepare_events_for_template([_event(description=raw)])[0]
    assert ev["description"] == "acteur de sa vie. Né à la ferme"


def test_description_is_truncated_on_a_word():
    assert script.clean_text("<p>un deux trois quatre</p>", limit=12) == "un deux …"


def test_location_does_not_repeat_the_locality():
    same = {
        "description": "Saint-Laurent-de-Chamousset",
        "locality": "Saint-Laurent-de-Chamousset",
    }
    venue = {"description": "La Maladière", "locality": "Saint-Denis-sur-Coise"}
    a, b = script.prepare_events_for_template(
        [_event(physicalAddress=same), _event(physicalAddress=venue)]
    )
    assert a["location"] == "Saint-Laurent-de-Chamousset"
    assert b["location"] == "La Maladière, Saint-Denis-sur-Coise"


def test_time_is_empty_at_midnight():
    # 2026-09-09T22:00Z is 2026-09-10 00:00 in Europe/Paris (all-day / multi-day event)
    ev = script.prepare_events_for_template([_event(beginsOn="2026-09-09T22:00:00Z")])[
        0
    ]
    assert ev["time"] == ""
    assert ev["day_label"] == "Jeudi 10 septembre"


def test_time_and_day_label():
    ev = script.prepare_events_for_template([_event()])[0]
    assert ev["time"] == "19h30"
    assert ev["day_label"] == "Jeudi 10 septembre"


def test_until_is_shown_only_for_events_longer_than_a_day():
    festival = _event(beginsOn="2026-09-10T16:00:00Z", endsOn="2026-09-12T21:00:00Z")
    concert = _event(beginsOn="2026-09-10T18:00:00Z", endsOn="2026-09-10T23:30:00Z")
    late = _event(beginsOn="2026-09-10T18:00:00Z", endsOn="2026-09-11T01:00:00Z")
    fest, conc, lat = script.prepare_events_for_template([festival, concert, late])
    assert fest["until"] == "jusqu'au 12 septembre"
    assert conc["until"] == "" and lat["until"] == ""


def test_events_are_grouped_by_local_day_in_order():
    raw = [
        _event(title="A", beginsOn="2026-09-10T17:30:00Z"),
        _event(title="B", beginsOn="2026-09-10T18:30:00Z"),
        _event(title="C", beginsOn="2026-09-11T08:00:00Z"),
    ]
    days = script.group_by_day(script.prepare_events_for_template(raw))
    assert [d["label"] for d in days] == ["Jeudi 10 septembre", "Vendredi 11 septembre"]
    assert [[e["title"] for e in d["events"]] for d in days] == [["A", "B"], ["C"]]


def test_period_label():
    same_month = script.prepare_events_for_template(
        [
            _event(beginsOn="2026-09-10T17:30:00Z"),
            _event(beginsOn="2026-09-21T17:30:00Z"),
        ]
    )
    across = script.prepare_events_for_template(
        [
            _event(beginsOn="2026-09-28T17:30:00Z"),
            _event(beginsOn="2026-10-05T17:30:00Z"),
        ]
    )
    assert script.period_label(same_month) == "Du 10 au 21 septembre"
    assert script.period_label(across) == "Du 28 septembre au 5 octobre"


def test_template_sizes_image_with_html_width_attribute():
    # Clients that ignore CSS max-width (Outlook, some webmails) need the attribute.
    raw = _event(picture={"url": "https://lekalepin.fr/media/p.jpg?name=p.jpg"})
    events = script.prepare_events_for_template([raw])
    html = script.render_newsletter(events, HERE, script.TEMPLATE_FILENAME)
    assert 'src="https://lekalepin.fr/media/p.jpg" width="130"' in html


def test_template_is_branded_from_settings():
    brand = {
        "name": "ACME",
        "logo_url": "https://acme.test/logo.png",
        "title": "Agenda ACME",
        "color": "#123456",
        "accent_color": "#abcdef",
        "url": "https://acme.test",
    }
    events = script.prepare_events_for_template([_event()])
    html = script.render_newsletter(events, HERE, script.TEMPLATE_FILENAME, brand=brand)
    for needle in (
        "ACME",
        brand["logo_url"],
        "Agenda ACME",
        "#123456",
        "#abcdef",
        'href="https://acme.test"',
    ):
        assert needle in html, needle
    assert "Kalepin" not in html and "lekalepin" not in html


def test_template_escapes_event_content_whatever_its_filename():
    # NEWSLETTER_TEMPLATE may not end in .html; content comes from a public instance.
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(
            os.path.join(HERE, "newsletter_template.html"),
            os.path.join(tmp, "custom.j2"),
        )
        event = script.prepare_events_for_template(
            [_event(title="<script>alert(1)</script>")]
        )[0]
        html = script.render_newsletter([event], tmp, "custom.j2")
    assert "<script>" not in html and "&lt;script&gt;" in html


BREVO_ENV = {
    "BREVO_API_KEY": "k",
    "BREVO_SENDER_EMAIL": "s@example.org",
    "BREVO_LIST_ID": "7",
    "BREVO_TEST_EMAIL": "me@example.org",
}


def _fake_api(calls):
    class FakeApi:
        def __init__(self, client):
            pass

        def create_email_campaign(self, campaign):
            calls.append(("create", campaign.tag))
            return types.SimpleNamespace(id=42)

        def send_test_email(self, campaign_id, email_to):
            calls.append(("test", campaign_id, email_to.email_to))

        def send_email_campaign_now(self, campaign_id):
            calls.append(("send_now", campaign_id))

    return FakeApi


def _send(test, env=BREVO_ENV):
    calls = []
    with (
        mock.patch.dict(os.environ, env),
        mock.patch.object(script, "EmailCampaignsApi", _fake_api(calls)),
    ):
        for key in BREVO_ENV.keys() - env.keys():
            os.environ.pop(key, None)
        script.send_newsletter_brevo("<p>hi</p>", test=test)
    return calls


def test_test_mode_sends_a_test_email_not_the_campaign():
    calls = _send(test=True)
    assert ("test", 42, ["me@example.org"]) in calls
    assert not [c for c in calls if c[0] == "send_now"]


def test_normal_mode_sends_the_campaign_to_the_list():
    calls = _send(test=False)
    assert ("send_now", 42) in calls
    assert not [c for c in calls if c[0] == "test"]


def test_default_brevo_tag_is_unchanged():
    assert ("create", "Newsletter Kalepin") in _send(test=False)


def test_test_mode_requires_a_test_address_before_creating_anything():
    env = {k: v for k, v in BREVO_ENV.items() if k != "BREVO_TEST_EMAIL"}
    try:
        calls = _send(test=True, env=env)
    except SystemExit:
        return
    raise AssertionError(f"expected SystemExit, got {calls}")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    raise SystemExit(1 if failed else 0)
