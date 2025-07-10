#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import os
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape
from bs4 import BeautifulSoup  # Pour nettoyer et tronquer la description

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

MOBILIZON_API_URL = "https://lekalepin.fr/api"
QUERY_LIMIT        = 100
TEMPLATE_FILENAME  = "newsletter_template.html"
OUTPUT_FILENAME    = "newsletter_events.html"

# ─────────────────────────────────────────────────────────────────────────────
#  FONCTIONS UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def sanitize_html(raw_html: str) -> str:
    """
    Prend une chaîne HTML brute (par exemple event['description']),
    l'encapsule dans un <div> fictif, la parse avec html5lib (via BeautifulSoup),
    puis renvoie uniquement le contenu intérieur de ce <div>, de sorte que
    toutes les balises ouvertes dans raw_html soient fermées proprement.
    """
    wrapper = f"<div>{raw_html}</div>"
    soup = BeautifulSoup(wrapper, "html5lib")
    div = soup.find("div")
    cleaned = "".join(str(child) for child in div.contents)
    return cleaned

def get_time_window(days: int = 8):
    """
    Renvoie un tuple (beginsOn_iso, endsOn_iso) en UTC,
    couvrant de maintenant (inclus) à maintenant + days jours (exclus).
    Format 'YYYY-MM-DDTHH:MM:SSZ'.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ends_utc = now_utc + datetime.timedelta(days=days)

    begins_iso = now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ends_iso   = ends_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return begins_iso, ends_iso

def build_graphql_query():
    """
    Requête GraphQL avec inline fragment sur le type Event,
    pour récupérer title, description, beginsOn, picture.url,
    url, et physicalAddress (description + locality).
    """
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
    """
    Envoie la requête GraphQL (POST JSON) à l'API Mobilizon pour récupérer
    les événements dans l'intervalle [begins_on, ends_on].
    Retourne la liste des objets de type Event ou lève une exception en cas d'erreur.
    """
    query = build_graphql_query()
    variables = {"beginsOn": begins_on, "endsOn": ends_on, "limit": limit}
    payload = {"query": query, "variables": variables}
    headers = {"Content-Type": "application/json"}

    resp = requests.post(MOBILIZON_API_URL, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Erreur GraphQL : {data['errors']}")

    events = []
    for elem in data["data"]["searchEvents"]["elements"]:
        if elem.get("__typename") == "Event":
            # Filtrage supplémentaire ici
            begins_iso = elem.get("beginsOn")
            if begins_iso:
                dt = datetime.datetime.fromisoformat(begins_iso.replace("Z", "+00:00"))
                dt_begins = datetime.datetime.fromisoformat(begins_on.replace("Z", "+00:00"))
                dt_ends = datetime.datetime.fromisoformat(ends_on.replace("Z", "+00:00"))
                if dt_begins <= dt < dt_ends:
                    events.append(elem)
    return events

def prepare_events_for_template(raw_events: list) -> list:
    """
    Transforme la liste brute d'événements GraphQL en une liste de dicts
    prêts à être passés au template Jinja2, en nettoyant et tronquant la description à 300 caractères.
    """
    jours_semaine = [
        "Lundi", "Mardi", "Mercredi", "Jeudi",
        "Vendredi", "Samedi", "Dimanche"
    ]
    mois_annee = [
        "", "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre"
    ]

    prepared = []
    for ev in raw_events:
        title = ev.get("title", "Sans titre")

        # 1) Nettoyer le HTML brut de la description
        raw_desc    = ev.get("description") or ""
        cleaned_html = sanitize_html(raw_desc)

        # 2) Extraire le texte brut et le tronquer à 300 caractères
        text_only = BeautifulSoup(cleaned_html, "html.parser").get_text()
        if len(text_only) > 300:
            truncated = text_only[:300].rstrip() + " …"
        else:
            truncated = text_only

        begins_iso  = ev.get("beginsOn")
        picture_url = ev.get("picture", {}).get("url")
        link        = ev.get("url") or ""

        phys = ev.get("physicalAddress")
        if phys:
            part1    = phys.get("description") or ""
            part2    = phys.get("locality") or ""
            location = ", ".join(x for x in (part1, part2) if x.strip())
        else:
            location = ""

        # Conversion UTC → Europe/Paris
        dt_utc   = datetime.datetime.fromisoformat(begins_iso.replace("Z", "+00:00"))
        dt_paris = dt_utc.astimezone(ZoneInfo("Europe/Paris"))
        jour_nom = jours_semaine[dt_paris.weekday()]
        jour_num = dt_paris.day
        mois_nom = mois_annee[dt_paris.month]
        annee    = dt_paris.year
        heure    = dt_paris.hour
        minute   = dt_paris.minute
        minute_str = f"{minute:02d}"
        full_date = f"{jour_nom} {jour_num} {mois_nom} {annee} à {heure} h {minute_str}"

        prepared.append({
            "title": title,
            "description": truncated,    # Texte brut tronqué à 300 car.
            "full_date": full_date,
            "picture_url": picture_url,
            "location": location,
            "link": link
        })

    return prepared

def render_newsletter(events: list, template_dir: str, template_name: str) -> str:
    """
    Utilise Jinja2 pour charger le template et renvoyer la chaîne HTML générée.
    """
    env = Environment(
        loader=FileSystemLoader(searchpath=template_dir),
        autoescape=select_autoescape(["html", "xml"])
    )
    template = env.get_template(template_name)

    now_paris = datetime.datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d %H:%M")
    return template.render(events=events, date_now=now_paris)

# ─────────────────────────────────────────────────────────────────────────────
#  PROGRAMME PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main():
    try:
        # 1) Calcul de la fenêtre : aujourd’hui → +8 jours
        begins_on, ends_on = get_time_window(days=10)
        print(f"Récupération des événements entre {begins_on} et {ends_on}…", file=sys.stderr)

        # 2) Appel GraphQL pour récupérer les événements
        raw_events = fetch_events(begins_on, ends_on)
        if not raw_events:
            print("Aucun événement trouvé dans la période demandée.", file=sys.stderr)
            sys.exit(0)

        # Affichage des événements récupérés et leur date
        for ev in raw_events:
            print(f"{ev.get('title', 'Sans titre')} — {ev.get('beginsOn', 'Date inconnue')}")

        # Tri des événements par date de début (ordre croissant)
        raw_events.sort(key=lambda ev: ev.get('beginsOn', ''))

        # 3) Préparation pour le template (nettoyage + tronquage)
        events = prepare_events_for_template(raw_events)

        # 4) Rendu Jinja2
        script_dir  = os.path.dirname(os.path.abspath(__file__))
        html_output = render_newsletter(
            events=events,
            template_dir=script_dir,
            template_name=TEMPLATE_FILENAME
        )

        # 5) Écriture du fichier HTML final
        output_path = os.path.join(script_dir, OUTPUT_FILENAME)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_output)
        print(f"Le fichier '{output_path}' a été généré avec succès.", file=sys.stderr)

    except Exception as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

