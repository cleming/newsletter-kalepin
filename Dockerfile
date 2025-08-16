FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY script.py .
COPY newsletter_template.html .

RUN mkdir -p /app/output

ENV PYTHONUNBUFFERED=1

CMD ["python", "script.py"]
