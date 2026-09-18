# Grafana MCP

공식 `grafana/mcp-grafana:1.4.2`를 사용합니다. `datasource,prometheus,loki` 범주만 활성화하고 쓰기 도구를 비활성화합니다. 두 Agent는 NAT `mcp_client`를 통해 `list_datasources`, `list_prometheus_label_values`, `list_loki_label_values`로 데이터소스·클러스터를 자동 탐색하고 `query_prometheus`, `query_loki_logs`로 조회합니다. Mimir는 Grafana의 Prometheus 호환 데이터소스로 연결합니다. 토큰은 데이터소스 목록과 대상 데이터소스 조회 권한이 필요합니다.

`GRAFANA_URL`, `GRAFANA_SERVICE_ACCOUNT_TOKEN`을 설정하고 [Compose](../agents/compose.yaml)를 사용하세요. MCP endpoint는 `/mcp`, health endpoint는 `/healthz`입니다. Docker build context는 저장소 루트입니다.

Windows에서는 [setup.ps1](../agents/scripts/setup.ps1)의 `-DownloadMcp` 옵션으로 공식 바이너리를 받고 SHA-256을 확인합니다. Windows 실제 MCP 연결과 두 Worker E2E를 검증했습니다. Linux 컨테이너 빌드/실행은 현재 환경에서 하지 않았습니다.
