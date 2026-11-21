FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi 'uvicorn[standard]' 'sqlalchemy[asyncio]' pymysql cryptography alembic pydantic pydantic-settings 'python-jose[cryptography]' 'passlib[argon2]' python-multipart openpyxl
COPY app ./app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
