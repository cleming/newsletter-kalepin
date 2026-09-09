FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY script.py .
COPY newsletter_template.html .

ENV PYTHONUNBUFFERED=1

CMD ["python", "script.py"]
