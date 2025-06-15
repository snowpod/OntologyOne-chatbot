# Use official Python base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy all repo contents into container
COPY . .

# Install system dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port your FastAPI app will run on
EXPOSE 8001

# Start FastAPI app
CMD ["uvicorn", "chatbot:app", "--host", "0.0.0.0", "--port", "8001"]
