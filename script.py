#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import os
import sys
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape
from premailer import transform

load_dotenv()

MOBILIZON_API_URL = "https://lekalepin.fr/api"
QUERY_LIMIT = 100
TEMPLATE_FILENAME = "newsletter_template.html"
OUTPUT_FILENAME = "newsletter_events.html"


def sanitize_html(raw_html: str) -> str:
    wrapper = f"<div>{raw_html}</div>"
    soup = BeautifulSoup(wrapper, "html5lib")
    div = soup.find("div")
    cleaned = "".join(str(child) for child in div.contents)
    return cleaned


def get_time_window(days: int = 8):
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ends_utc = now_utc + datetime.timedelta(days=days)

    begins_iso = now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ends_iso = ends_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return begins_iso, ends_iso


def build_graphql_query():
    return """
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


def fetch_events(begins_on: str, ends_on: str, limit: int = QUERY_LIMIT):
    query = build_graphql_query()
    variables = {"beginsOn": begins_on, "endsOn": ends_on, "limit": limit}
    payload = {"query": query, "variables": variables}
    headers = {"Content-Type": "application/json"}

    resp = requests.post(MOBILIZON_API_URL, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")

    events = []
    for elem in data["data"]["searchEvents"]["elements"]:
        if elem.get("__typename") == "Event":
            begins_iso = elem.get("beginsOn")
            if begins_iso:
                dt = datetime.datetime.fromisoformat(begins_iso.replace("Z", "+00:00"))
                dt_begins = datetime.datetime.fromisoformat(
                    begins_on.replace("Z", "+00:00")
                )
                dt_ends = datetime.datetime.fromisoformat(
                    ends_on.replace("Z", "+00:00")
                )
                if dt_begins <= dt < dt_ends:
                    events.append(elem)
    return events


def prepare_events_for_template(raw_events: list) -> list:
    jours_semaine = [
        "Lundi",
        "Mardi",
        "Mercredi",
        "Jeudi",
        "Vendredi",
        "Samedi",
        "Dimanche",
    ]
    mois_annee = [
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

    prepared = []
    for ev in raw_events:
        title = ev.get("title", "Untitled")

        raw_desc = ev.get("description") or ""
        cleaned_html = sanitize_html(raw_desc)

        text_only = BeautifulSoup(cleaned_html, "html.parser").get_text()
        if len(text_only) > 300:
            truncated = text_only[:300].rstrip() + " …"
        else:
            truncated = text_only

        begins_iso = ev.get("beginsOn")
        picture_url = ev.get("picture", {}).get("url")
        link = ev.get("url") or ""

        if picture_url and "?" in picture_url:
            picture_url = picture_url.split("?", 1)[0]

        phys = ev.get("physicalAddress")
        if phys:
            part1 = phys.get("description") or ""
            part2 = phys.get("locality") or ""
            location = ", ".join(x for x in (part1, part2) if x.strip())
        else:
            location = ""

        dt_utc = datetime.datetime.fromisoformat(begins_iso.replace("Z", "+00:00"))
        dt_paris = dt_utc.astimezone(ZoneInfo("Europe/Paris"))
        jour_nom = jours_semaine[dt_paris.weekday()]
        jour_num = dt_paris.day
        mois_nom = mois_annee[dt_paris.month]
        annee = dt_paris.year
        heure = dt_paris.hour
        minute = dt_paris.minute
        minute_str = f"{minute:02d}"
        full_date = f"{jour_nom} {jour_num} {mois_nom} {annee} à {heure} h {minute_str}"

        prepared.append(
            {
                "title": title,
                "description": truncated,
                "full_date": full_date,
                "picture_url": picture_url,
                "location": location,
                "link": link,
            }
        )

    return prepared


def render_newsletter(events: list, template_dir: str, template_name: str) -> str:
    env = Environment(
        loader=FileSystemLoader(searchpath=template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_name)

    now_paris = datetime.datetime.now(ZoneInfo("Europe/Paris")).strftime(
        "%Y-%m-%d %H:%M"
    )
    return template.render(events=events, date_now=now_paris)


def inline_css(input_html_path, output_html_path):
    with open(input_html_path, "r", encoding="utf-8") as f:
        html = f.read()
    inlined_html = transform(html)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(inlined_html)


def main():
    try:
        begins_on, ends_on = get_time_window(days=10)
        print(
            f"Fetching events between {begins_on} and {ends_on}...",
            file=sys.stderr,
        )

        raw_events = fetch_events(begins_on, ends_on)
        if not raw_events:
            print("No events found in the requested period.", file=sys.stderr)
            sys.exit(0)

        for ev in raw_events:
            print(
                f"{ev.get('title', 'Untitled')} — {ev.get('beginsOn', 'Unknown date')}"
            )

        raw_events.sort(key=lambda ev: ev.get("beginsOn", ""))

        events = prepare_events_for_template(raw_events)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        html_output = render_newsletter(
            events=events, template_dir=script_dir, template_name=TEMPLATE_FILENAME
        )

        output_path = os.path.join(script_dir, OUTPUT_FILENAME)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"File '{output_path}' generated successfully.", file=sys.stderr)

        inlined_output_path = os.path.join(script_dir, "newsletter_events_inlined.html")
        inline_css(output_path, inlined_output_path)
        print(
            f"File '{inlined_output_path}' (inline CSS) generated.",
            file=sys.stderr,
        )

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def log(msg):
    print(f"[LOG] {msg}", file=sys.stderr)


def send_newsletter_brevo(test=False):
    try:
        import brevo_python

        log(f"brevo_python path: {getattr(brevo_python, '__file__', 'unknown')}")
        log(f"brevo_python version: {getattr(brevo_python, '__version__', 'unknown')}")
        try:
            from brevo_python.api.email_campaigns_api import EmailCampaignsApi
            from brevo_python.configuration import Configuration
            from brevo_python.models.create_email_campaign import CreateEmailCampaign
            from brevo_python.rest import ApiException

        except Exception as e:
            log(f"Error importing brevo_python class: {e}")
            return
    except ImportError:
        log(
            "The 'brevo_python' module is not installed. Install it with 'pip install brevo-python'"
        )
        return

    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = "Le Kalepin"
    list_id = os.getenv("BREVO_LIST_ID")
    if not api_key or not sender_email or not list_id:
        log(
            "Missing environment variables: BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_LIST_ID"
        )
        return
    list_id = int(list_id)
    test_email = "test@gibaud.info"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "newsletter_events_inlined.html")
    log(f"Reading generated HTML from {output_path}")
    with open(output_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    configuration = Configuration()
    configuration.api_key["api-key"] = api_key
    api_instance = EmailCampaignsApi(brevo_python.ApiClient(configuration))

    if test:
        log(f"Preparing TEST send to {test_email}")
        email_campaign = CreateEmailCampaign(
            tag="Newsletter Kalepin [TEST]",
            sender={"name": sender_name, "email": sender_email},
            name="[TEST] Kalepin : les prochains événements",
            subject="[TEST] kalepin",
            html_content=html_content,
            recipients={"listIds": [list_id]},
            inline_image_activation=False,
        )
    else:
        log(f"Preparing campaign for Brevo list ID {list_id}")
        email_campaign = CreateEmailCampaign(
            tag="Newsletter Kalepin",
            sender={"name": sender_name, "email": sender_email},
            name="Kalepin : les prochains événements",
            subject="Kalepin : les prochains événements",
            html_content=html_content,
            recipients={"listIds": [list_id]},
            inline_image_activation=False,
        )

    try:
        log("Creating campaign...")
        campaign = api_instance.create_email_campaign(email_campaign)
        log(f"Campaign created, ID: {campaign.id}")

        log("Sending campaign immediately...")
        api_instance.send_email_campaign_now(campaign.id)
        log("Campaign sent to list!")
    except ApiException as e:
        log(f"Error creating or sending campaign: {e}")
        if hasattr(e, "body"):
            log(f"Error details: {e.body}")


if __name__ == "__main__":
    main()
    if "--test" in sys.argv:
        log(
            "TEST mode enabled: newsletter will be sent only to test address."
        )
        send_newsletter_brevo(test=True)
    else:
        log("To send a test, run: python script.py --test")
        send_newsletter_brevo(test=False)