FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home app
COPY omr_check ./omr_check
COPY assets ./assets
COPY data ./data
RUN mkdir /app/var && chown -R app:app /app
USER app
CMD ["python", "-m", "omr_check", "bot"]
