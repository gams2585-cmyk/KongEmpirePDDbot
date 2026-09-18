FROM python:3.12-slim
WORKDIR /app
COPY bot.py lessons.json ./
COPY *.png ./
COPY *.png ./assets/
ENV PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
