FROM python:3.13-slim@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
COPY calendar_oauth.py calendar_connection.py calendar_readonly.py ./
COPY static ./static
# Build contexts may be checked out with a restrictive umask (e.g. 077).
# Ensure the non-root runtime can read source and traverse static directories.
RUN chmod 0644 /app/*.py && chmod -R a+rX /app/static
USER 10001:10001
# Fail the image build if the actual runtime UID cannot import and read assets.
RUN python -c "import app; from pathlib import Path; [p.open('rb').close() for p in Path('/app/static').rglob('*') if p.is_file()]"
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120", "--access-logfile", "/dev/null", "--error-logfile", "-", "app:create_app()"]
