# --- stage 1: build the dependency-free Go interceptor ---
FROM golang:1.22 AS gobuild
WORKDIR /src/interceptor-go
COPY interceptor-go/go.mod ./
COPY interceptor-go/main.go ./
RUN CGO_ENABLED=0 go build -o /out/interceptor .

# --- stage 2: Python client + server + UI, with the prebuilt interceptor ---
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=gobuild /out/interceptor /usr/local/bin/interceptor

# The UI orchestrates the server + both interceptors inside the container. Using
# the prebuilt binary means no Go toolchain is needed at runtime.
ENV INTERCEPTOR_BIN=/usr/local/bin/interceptor \
    UI_HOST=0.0.0.0 \
    UI_PORT=8080

EXPOSE 8080
CMD ["python", "ui/server.py"]
