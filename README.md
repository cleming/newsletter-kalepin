# Newsletter Kalepin

Automated Python script to generate and send newsletters with Mobilizon events via Jinja2 templates and Brevo email service.

## About

This project was created for the French Mobilizon instance ["Le Kalepin"](https://lekalepin.fr) - a cultural agenda for the Monts du Lyonnais region in France. While the script can be adapted for other Mobilizon instances, you'll need to translate the newsletter template and adjust the date formatting to match your locale.

## Description

This script fetches upcoming events from Mobilizon's GraphQL API, generates an HTML newsletter using Jinja2 templates, and sends it via Brevo email service.

## Features

- Automatic event fetching via Mobilizon API
- HTML newsletter generation with customizable Jinja2 templates
- Event description cleaning and truncation
- UTC to Europe/Paris timezone conversion
- Inline CSS for email compatibility
- Brevo integration with test mode support

## Installation

### Local Setup

```bash
pip install -r requirements.txt
```

### Docker

```bash
docker build -t newsletter-kalepin .
docker run --env-file .env newsletter-kalepin
```

### Pre-built Image

```bash
docker pull ghcr.io/cleming/newsletter-kalepin:main
docker run --env-file .env ghcr.io/cleming/newsletter-kalepin:main
```

## Configuration

Create a `.env` file with the following variables:

```env
BREVO_API_KEY=your_brevo_api_key
BREVO_SENDER_EMAIL=your_sender_email
BREVO_LIST_ID=your_list_id
```

### Adapting for Other Mobilizon Instances

To use this script with a different Mobilizon instance:

1. Change `MOBILIZON_API_URL` in `script.py` to your instance's API endpoint
2. Update the newsletter template (`newsletter_template.html`) with your preferred language
3. Modify the date formatting in `prepare_events_for_template()` function (currently uses French day/month names)
4. Adjust timezone conversion if needed (currently converts to Europe/Paris)

## Usage

### Normal mode
```bash
python script.py
```

### Test mode
```bash
python script.py --test
```

Test mode sends the newsletter only to the configured test email address.

## Generated Files

- `newsletter_events.html`: Newsletter with external CSS
- `newsletter_events_inlined.html`: Newsletter with inline CSS (email-ready)

## CI/CD

The project includes a GitHub Action that:
- Automatically builds Docker image on push to main
- Pushes to GitHub Container Registry (ghcr.io)
- Supports AMD64 architecture
- Optimized caching for fast builds

## Template Customization

Modify `newsletter_template.html` to customize the newsletter appearance. The template receives:
- `events`: formatted events list
- `date_now`: generation timestamp

## Event Structure

Each event contains:
- `title`: event title
- `description`: truncated description (300 chars max)
- `full_date`: formatted date (currently in French)
- `picture_url`: image URL (cleaned for Brevo compatibility)
- `location`: event location
- `link`: event URL

## Development

### Linting

The project uses Black, isort, flake8, and mypy for code quality:

```bash
black script.py
isort script.py
flake8 script.py
mypy script.py
```

Configuration files:
- `pyproject.toml`: Black and isort settings
- `.flake8`: Flake8 configuration

### Requirements

The project uses pinned dependencies for reproducible builds. Development dependencies (linting tools) are included in `requirements.txt`.