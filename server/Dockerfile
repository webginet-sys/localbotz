# LocalBotz VPS Premium gateway
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
# .env is NOT copied into the image on purpose: mount it at run time,
# or pass the variables with -e / --env-file. Provider keys must never
# be baked into an image.
ENV HOST=0.0.0.0 PORT=8001
EXPOSE 8001
CMD ["python", "app.py"]
