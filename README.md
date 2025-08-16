# Newsletter Kalepin

Script Python pour générer et envoyer automatiquement une newsletter avec les événements du Kalepin via l'API Mobilizon et Brevo.

## Description

Ce script récupère les événements à venir depuis l'API GraphQL de Mobilizon (lekalepin.fr), génère une newsletter HTML avec template Jinja2, et l'envoie via Brevo.

## Fonctionnalités

- Récupération automatique des événements via l'API Mobilizon
- Génération de newsletter HTML avec template personnalisable
- Nettoyage et tronquage des descriptions d'événements
- Conversion des dates UTC vers le fuseau Europe/Paris
- Inline CSS pour compatibilité email
- Envoi via Brevo avec support mode test

## Installation

### Locale

```bash
pip install -r requirements.txt
```

### Docker

```bash
docker build -t newsletter-kalepin .
docker run --env-file .env newsletter-kalepin
```

### Image pré-construite

```bash
docker pull ghcr.io/{username}/newsletter-kalepin:latest
docker run --env-file .env ghcr.io/{username}/newsletter-kalepin:latest
```

## Configuration

Créez un fichier `.env` avec les variables suivantes :

```env
BREVO_API_KEY=your_brevo_api_key
BREVO_SENDER_EMAIL=your_sender_email
BREVO_LIST_ID=your_list_id
```

## Utilisation

### Mode normal
```bash
python script.py
```

### Mode test
```bash
python script.py --test
```

Le mode test envoie la newsletter uniquement à l'adresse de test configurée.

## Fichiers générés

- `newsletter_events.html` : Newsletter avec CSS externe
- `newsletter_events_inlined.html` : Newsletter avec CSS inline (pour email)

## CI/CD

Le projet inclut une GitHub Action qui :
- Build automatiquement l'image Docker
- Push vers GitHub Container Registry (ghcr.io)
- Support multi-architecture (amd64/arm64)
- Cache optimisé pour des builds rapides

## Template

Modifiez `newsletter_template.html` pour personnaliser l'apparence de la newsletter. Le template reçoit :
- `events` : liste des événements formatés
- `date_now` : date/heure de génération

## Structure des événements

Chaque événement contient :
- `title` : titre de l'événement
- `description` : description tronquée (300 caractères max)
- `full_date` : date formatée en français
- `picture_url` : URL de l'image (nettoyée pour Brevo)
- `location` : lieu de l'événement
- `link` : lien vers l'événement