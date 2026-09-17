# Build from repository root: docker build -f job-controller/Dockerfile .
FROM golang:1.26.2-alpine AS build
WORKDIR /src
COPY shared/ shared/
COPY job-controller/go.mod job-controller/go.sum job-controller/
COPY backend/go.mod backend/go.sum backend/
WORKDIR /src/job-controller
RUN go mod download
COPY job-controller/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/job-controller ./cmd/server

FROM alpine:3.23
RUN apk add --no-cache ca-certificates && adduser -D -u 10001 app
WORKDIR /app
COPY --from=build /out/job-controller /app/job-controller
USER app
EXPOSE 8090
ENTRYPOINT ["/app/job-controller"]
