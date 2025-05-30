FROM python:3.11-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
WORKDIR /app
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
