FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose OPC UA port
EXPOSE 4840

# Run the simulator
CMD ["python", "-u", "main.py"]
