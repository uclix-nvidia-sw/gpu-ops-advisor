# Official server; read-only Prometheus/Mimir and Loki tools only.
FROM grafana/mcp-grafana:1.4.2
EXPOSE 8000
CMD ["-t", "streamable-http", "-address", "0.0.0.0:8000", "-enabled-tools", "datasource,prometheus,loki", "-disable-write", "-max-loki-log-limit", "5000", "-grafana-timeout", "30s"]
