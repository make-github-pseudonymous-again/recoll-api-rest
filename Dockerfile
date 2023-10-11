ARG REQUIREMENTS_STAGE_BASE_IMAGE=python:3.11-alpine

FROM ${REQUIREMENTS_STAGE_BASE_IMAGE} as requirements-stage

WORKDIR /tmp

RUN pip install poetry

COPY ./pyproject.toml ./poetry.lock* ./

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes


FROM debian:bookworm-slim

WORKDIR /code

RUN apt-get update

RUN apt-get install -y python3-recoll

RUN apt-get install -y python3-pip

COPY --from=requirements-stage /tmp/requirements.txt requirements.txt

RUN pip install --break-system-packages --no-cache-dir --upgrade -r requirements.txt

COPY ./src src

ENV RECOLL_CONFDIR="/index"

CMD ["gunicorn", "-w", "4", "src.api:api", "-b", "0.0.0.0:80"]
# CMD ["uvicorn", "src.api:api", "--host", "0.0.0.0", "--port", "80"]
