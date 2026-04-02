FROM python:3.9.17-slim-bullseye

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Optional: if you need doc processing
# RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless libreoffice-writer-nogui
COPY . .
COPY .env.runtime .env.runtime
COPY generate-local-env.sh generate-local-env.sh

# Recommended pip install setup
RUN pip install --upgrade pip==22.1.1 && \
    pip install -r requirements.txt

# Optional: install flower only in dev builds
# RUN pip install flower

# Exectable entrypoint
RUN chmod +x /app/entrypoint.sh
RUN chmod +x /app/start_celery_beat_flower.sh


# Security tip: don't hardcode secrets
EXPOSE 30000
ENV PYTHONPATH=/app
ENV BUILD_ENV=true
# CMD ["/app/entrypoint.sh"]
CMD ["python", "figure1/run/flask_startup.py"]