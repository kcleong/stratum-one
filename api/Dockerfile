FROM python:3.13-alpine
# chronyc talks to chronyd over the shared /run/chrony socket.
RUN apk add --no-cache chrony
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY stratum_api ./stratum_api
CMD ["python", "-m", "stratum_api"]
