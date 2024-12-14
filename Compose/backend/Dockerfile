FROM python:3.12-slim-bookworm

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY ./backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the entire backend project
COPY ./backend /app/backend

# Expose the FastAPI port
EXPOSE 8000

# Run Uvicorn with the FastAPI app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]