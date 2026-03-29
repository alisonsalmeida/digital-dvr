FROM python:3.13-slim

RUN apt update -y && apt upgrade -y && apt install ffmpeg -y

RUN pip install poetry

WORKDIR /app

ADD . .

RUN poetry config virtualenvs.create false && poetry install

ENTRYPOINT ["python", "app.py"]
