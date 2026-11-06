# Backend-Image: Python + FastAPI + uvicorn
# Grundlage: Minimal-Dockerfile aus "Full Stack Handwerk", S. 54
# Tag zum Lesen, Digest (@sha256) legt das Image bitgenau fest. Der Digest
# gilt für alle Plattformen (Image-Index, u. a. linux/amd64 und linux/arm64).
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

WORKDIR /app

# Zuerst nur die Abhängigkeiten: Docker kann diese Schicht wiederverwenden,
# solange sich requirements.txt nicht ändert.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Migrationen (Alembic): ändern sich seltener als der Code, deshalb vorher.
# Der Service "migrate" nutzt dieses Image und führt sie vor dem Start aus.
COPY alembic.ini .
COPY alembic ./alembic

# Dann der eigentliche Code
COPY app ./app

# uvicorn startet die FastAPI-App; 0.0.0.0 = von anderen Containern erreichbar
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]