FROM node:20-slim AS fe
WORKDIR /fe
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
ENV VITE_API_URL=""
RUN npm run build

FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=fe /fe/dist /app/frontend/dist
ENV PORT=8000
CMD ["sh", "-c", "python seed.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
