#!/usr/bin/env python3

import datetime
import itertools
import os
import sys
from zoneinfo import ZoneInfo

import brevo_python
import requests
from brevo_python.api.email_campaigns_api import EmailCampaignsApi
from brevo_python.models.create_email_campaign import CreateEmailCampaign
from brevo_python.models.send_test_email import SendTestEmail
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

load_dotenv()

# Everything below is overridable from the environment (see .env.example);
# defaults are Le Kalepin, La Fabrik's Mobilizon instance.
MOBILIZON_URL = os.getenv("MOBILIZON_URL", "https://lekalepin.fr").rstrip("/")
DAYS_AHEAD = int(os.getenv("NEWSLETTER_DAYS") or 12)
TIMEZONE = ZoneInfo(os.getenv("NEWSLETTER_TIMEZONE") or "Europe/Paris")
SUBJECT = os.getenv("NEWSLETTER_SUBJECT", "Kalepin : les prochains événements")
TAG = os.getenv("NEWSLETTER_TAG", "Newsletter Kalepin")  # Brevo campaign tag
TEMPLATE_FILENAME = os.getenv("NEWSLETTER_TEMPLATE", "newsletter_template.html")
BRAND = {
    "name": os.getenv("BRAND_NAME", "Le Kalepin"),
    "url": MOBILIZON_URL,
    "logo_url": os.getenv(
        "BRAND_LOGO_URL",
        "https://lafabrik-moly.fr/wp-content/uploads/2025/07/logo-kalepin-01.png",
    ),
    "title": os.getenv("BRAND_TITLE", "Les prochains événements des Monts du Lyonnais"),
    "color": os.getenv("BRAND_COLOR", "#4B64F2"),
    "accent_color": os.getenv("BRAND_ACCENT_COLOR", "#ff7105"),
}
OUTPUT_FILENAME = "newsletter_events.html"
QUERY_LIMIT = 100
DESCRIPTION_MAX_CHARS = 150

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = [
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]

GRAPHQL_QUERY = """
query SearchEventsInWindow($beginsOn: DateTime, $endsOn: DateTime, $limit: Int) {
  searchEvents(beginsOn: $beginsOn, endsOn: $endsOn, limit: $limit) {
    total
    elements {
      __typename
      ... on Event {
        id
        title
        description
        beginsOn
        endsOn
        picture {
          url
        }
        url
        physicalAddress {
          description
          locality
        }
      }
    }
  }
}
"""


def log(msg):
    print(f"[LOG] {msg}", file=sys.stderr)


def to_iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def get_time_window(days=DAYS_AHEAD):
    begins = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return begins, begins + datetime.timedelta(days=days)


def fetch_events(begins, ends, limit=QUERY_LIMIT):
    variables = {"beginsOn": to_iso(begins), "endsOn": to_iso(ends), "limit": limit}
    resp = requests.post(
        f"{MOBILIZON_URL}/api",
        json={"query": GRAPHQL_QUERY, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")

    events = []
    for elem in data["data"]["searchEvents"]["elements"]:
        if elem.get("__typename") != "Event" or not elem.get("beginsOn"):
            continue
        # searchEvents also returns events overlapping the window; keep those starting in it
        if begins <= datetime.datetime.fromisoformat(elem["beginsOn"]) < ends:
            events.append(elem)
    return events


def clean_text(raw_html, limit=DESCRIPTION_MAX_CHARS):
    soup = BeautifulSoup(raw_html or "", "html.parser")
    text = " ".join(soup.get_text(" ").split())
    if len(text) > limit:
        cut = text[:limit]
        cut = cut[: cut.rfind(" ")] if " " in cut else cut
        text = cut.rstrip(" ,;:") + " …"
    return text


def day_label(dt):
    return f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month]}"


def time_label(dt):
    if (dt.hour, dt.minute) == (0, 0):
        return ""  # all-day / multi-day events start at midnight
    return f"{dt.hour}h{dt.minute:02d}"


def until_label(begins, ends):
    if ends is None or ends - begins < datetime.timedelta(hours=24):
        return ""  # a concert ending after midnight is not a multi-day event
    return f"jusqu'au {ends.day} {MOIS[ends.month]}"


def period_label(events):
    if not events:
        return ""
    first, last = events[0]["begins"], events[-1]["begins"]
    if first.date() == last.date():
        return f"Le {first.day} {MOIS[first.month]}"
    if first.month == last.month:
        return f"Du {first.day} au {last.day} {MOIS[last.month]}"
    return f"Du {first.day} {MOIS[first.month]} au {last.day} {MOIS[last.month]}"


def group_by_day(events):
    return [
        {"label": label, "events": list(group)}
        for label, group in itertools.groupby(events, key=lambda e: e["day_label"])
    ]


def prepare_events_for_template(raw_events):
    prepared = []
    for ev in raw_events:
        picture_url = (ev.get("picture") or {}).get("url")
        if picture_url:
            picture_url = picture_url.split("?", 1)[0]  # Brevo rejects query strings

        phys = ev.get("physicalAddress") or {}
        venue, locality = (phys.get("description") or "").strip(), (
            phys.get("locality") or ""
        ).strip()
        if venue.casefold() == locality.casefold():
            venue = ""  # Mobilizon often repeats the town in both fields
        location = ", ".join(p for p in (venue, locality) if p)

        begins = datetime.datetime.fromisoformat(ev["beginsOn"]).astimezone(TIMEZONE)
        ends_iso = ev.get("endsOn")
        ends = (
            datetime.datetime.fromisoformat(ends_iso).astimezone(TIMEZONE)
            if ends_iso
            else None
        )

        prepared.append(
            {
                "title": ev.get("title", "Untitled"),
                "description": clean_text(ev.get("description")),
                "begins": begins,
                "day_label": day_label(begins),
                "time": time_label(begins),
                "until": until_label(begins, ends),
                "picture_url": picture_url,
                "location": location,
                "link": ev.get("url") or "",
            }
        )
    return prepared


def render_newsletter(events, template_dir, template_name, brand=BRAND):
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,  # NEWSLETTER_TEMPLATE may not end in .html
    )
    return env.get_template(template_name).render(
        days=group_by_day(events), period=period_label(events), brand=brand
    )


def send_newsletter_brevo(html_content, test=False):
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    list_id = os.getenv("BREVO_LIST_ID")
    test_email = os.getenv("BREVO_TEST_EMAIL")
    if not api_key or not sender_email or not list_id:
        sys.exit(
            "Missing environment variables: BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_LIST_ID"
        )
    if test and not test_email:
        sys.exit("Missing environment variable: BREVO_TEST_EMAIL (recipient of --test)")

    configuration = brevo_python.Configuration()
    configuration.api_key["api-key"] = api_key
    api = EmailCampaignsApi(brevo_python.ApiClient(configuration))

    tag = TAG
    name = subject = SUBJECT
    if test:
        tag, name, subject = f"{tag} [TEST]", f"[TEST] {name}", f"[TEST] {subject}"

    campaign = api.create_email_campaign(
        CreateEmailCampaign(
            tag=tag,
            sender={"name": BRAND["name"], "email": sender_email},
            name=name,
            subject=subject,
            html_content=html_content,
            recipients={"listIds": [int(list_id)]},
            inline_image_activation=False,
        )
    )
    log(f"Campaign created, ID: {campaign.id}")

    if test:
        api.send_test_email(campaign.id, SendTestEmail(email_to=[test_email]))
        log(f"Test email sent to {test_email} (it must be an existing Brevo contact)")
    else:
        api.send_email_campaign_now(campaign.id)
        log("Campaign sent to list!")


def main():
    begins, ends = get_time_window()
    log(f"Fetching events between {to_iso(begins)} and {to_iso(ends)}...")
    raw_events = sorted(fetch_events(begins, ends), key=lambda ev: ev["beginsOn"])
    if not raw_events:
        log("No events found in the requested period.")
        return
    for ev in raw_events:
        print(f"{ev.get('title', 'Untitled')} — {ev['beginsOn']}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    events = prepare_events_for_template(raw_events)
    html = render_newsletter(events, script_dir, TEMPLATE_FILENAME)
    output_path = os.path.join(script_dir, OUTPUT_FILENAME)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"File '{output_path}' generated.")

    test = "--test" in sys.argv
    if test:
        log("TEST mode: sending only to the test address.")
    else:
        log("To send a test, run: python script.py --test")
    send_newsletter_brevo(html, test=test)


if __name__ == "__main__":
    main()
