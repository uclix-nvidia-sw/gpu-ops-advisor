# Build from repository root: docker build -f backend/Dockerfile .
FROM golang:1.26.2-alpine AS build
WORKDIR /src
COPY shared/ shared/
COPY job-controller/go.mod job-controller/go.sum job-controller/
COPY backend/go.mod backend/go.sum backend/
WORKDIR /src/backend
RUN go mod download
COPY backend/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/backend ./cmd/server

FROM alpine:3.23
RUN apk add --no-cache ca-certificates && adduser -D -u 10001 app
WORKDIR /app
COPY --from=build /out/backend /app/backend
USER app
EXPOSE 8080
ENTRYPOINT ["/app/backend"]
