package api

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/backend/internal/contract"
)

// An empty cluster registry is a valid initial state. Scope validation still
// rejects analysis requests for unregistered or disabled clusters.
func (s *Server) readiness(ctx context.Context) error {
	var migrated bool
	if e := s.DB.Pool.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version=2)").Scan(&migrated); e != nil {
		return Fail(503, "DATABASE_UNAVAILABLE", "저장소 연결 또는 스키마 조회에 실패했습니다.")
	}
	if !migrated {
		return Fail(503, "SCHEMA_NOT_READY", "DB 스키마 마이그레이션이 필요합니다.")
	}
	var limits Object
	e := s.DB.Pool.QueryRow(ctx, "SELECT config FROM service_profiles WHERE kind='limits' AND name='C07' AND enabled").Scan(&limits)
	if e != nil && !errors.Is(e, pgx.ErrNoRows) {
		return Fail(503, "DATABASE_UNAVAILABLE", "운영 한도 조회에 실패했습니다.")
	}
	for _, key := range []string{"max_query_days", "max_body_bytes", "max_log_lines", "max_requests_per_minute", "max_text_length", "max_inflight_requests", "module_timeout_seconds"} {
		if Number(limits, key) <= 0 {
			return Fail(503, "LIMITS_NOT_CONFIGURED", "C07 양수 한도 설정이 필요합니다: "+key)
		}
	}
	return nil
}
