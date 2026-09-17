# Build from repository root: docker build -f incident/Dockerfile .
FROM golang:1.26.2-alpine AS build
WORKDIR /src
COPY shared/ shared/
COPY job-controller/go.mod job-controller/go.sum job-controller/
COPY incident/go.mod incident/go.sum incident/
WORKDIR /src/incident
RUN go mod download
COPY incident/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/incident ./cmd/server
FROM alpine:3.23
RUN apk add --no-cache ca-certificates && adduser -D -u 10001 app
WORKDIR /app
COPY --from=build /out/incident /app/incident
USER app
EXPOSE 8091
ENTRYPOINT ["/app/incident"]
