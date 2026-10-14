# Login-capable staging image, inert unless explicitly configured.
# Scan the image before any deployed release.
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements-gateway.txt /app/requirements-gateway.txt
RUN pip install --no-cache-dir -r requirements-gateway.txt
COPY v2_poc/__init__.py v2_poc/bff_*.py /app/v2_poc/

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "v2_poc.bff_offline"]
