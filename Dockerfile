FROM python:3.12-slim
WORKDIR /app
COPY bot.py lessons.json ./
COPY picture-*.png ./assets/
ENV PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
