FROM python:3.14-alpine AS builder

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./

RUN POETRY_VIRTUALENVS_IN_PROJECT=true poetry install --only main --no-root


FROM python:3.14-alpine

LABEL org.opencontainers.image.source="https://github.com/felixschndr/InverterChargeController"
LABEL org.opencontainers.image.description="The container image of the inverter charge controller (https://github.com/felixschndr/InverterChargeController)"

RUN apk add --no-cache tzdata

WORKDIR /app

COPY --from=builder /app/.venv/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY source/ source/
COPY sample_solar_forecast.json ./

CMD ["python", "-m", "source.main"]
