FROM python:3.12-alpine

RUN apk add --no-cache ffmpeg

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 5000

CMD ["uv", "run", "flask", "--app", "main:app", "run", "--host", "0.0.0.0"]
