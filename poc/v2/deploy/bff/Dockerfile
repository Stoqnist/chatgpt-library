# Inert offline BFF shell; NOT a production login or consent interface.
# Pin an approved digest and scan the image before any deployed release.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY v2_poc/__init__.py v2_poc/bff_offline.py /app/v2_poc/

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "v2_poc.bff_offline"]
