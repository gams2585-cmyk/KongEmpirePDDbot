FROM python:3.12-slim
WORKDIR /app
COPY bot.py lessons.json ./
COPY picture-01.png ./assets/picture-01.png
ENV PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
