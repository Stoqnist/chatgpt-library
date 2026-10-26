FROM python:3.12-slim
WORKDIR /srv/app
COPY mvp/daily-routine/requirements.txt requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY mvp/daily-routine/app.py app.py
RUN useradd -u 10001 -r -s /usr/sbin/nologin appuser
USER appuser
ENV AGENCY_BIND=0.0.0.0 AGENCY_PORT=18080 PYTHONDONTWRITEBYTECODE=1
EXPOSE 18080
CMD ["python", "app.py"]
