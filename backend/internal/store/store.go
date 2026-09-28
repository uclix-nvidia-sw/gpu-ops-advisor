package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/migrations"
)

type Store struct{ Pool *pgxpool.Pool }

func Open(ctx context.Context, url string) (*Store, error) {
	c, e := pgxpool.ParseConfig(url)
	if e != nil {
		return nil, e
	}
	c.MaxConns = 12
	c.ConnConfig.ConnectTimeout = 5 * time.Second
	p, e := pgxpool.NewWithConfig(ctx, c)
	if e != nil {
		return nil, e
	}
	if e = p.Ping(ctx); e != nil {
		p.Close()
		return nil, e
	}
	return &Store{p}, nil
}
func (s *Store) Migrate(ctx context.Context) error {
	return s.Transaction(ctx, func(tx pgx.Tx) error {
		if _, e := tx.Exec(ctx, migrations.Baseline); e != nil {
			return e
		}
		_, e := tx.Exec(ctx, migrations.Upgrade)
		return e
	})
}

type txKey struct{}

func WithTx(ctx context.Context, tx pgx.Tx) context.Context {
	return context.WithValue(ctx, txKey{}, tx)
}

type Queryer interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func One(ctx context.Context, q Queryer, sql string, args ...any) (contract.Object, error) {
	var b []byte
	e := q.QueryRow(ctx, sql, args...).Scan(&b)
	if errors.Is(e, pgx.ErrNoRows) {
		return nil, contract.Fail(404, "NOT_FOUND", "리소스를 찾을 수 없습니다.")
	}
	if e != nil {
		return nil, e
	}
	var m contract.Object
	e = json.Unmarshal(b, &m)
	return m, e
}
func (s *Store) Get(ctx context.Context, kind, id string) (contract.Object, error) {
	tables := map[string]string{"jobs": "jobs", "analyses": "jobs", "reports": "jobs", "evidence": "evidence", "incidents": "incidents", "schedules": "schedules", "reviews": "review_records"}
	table, ok := tables[kind]
	if !ok {
		return nil, contract.Invalid("resource")
	}
	sql := "SELECT to_jsonb(t) FROM " + table + " t WHERE id::text=$1"
	if kind == "analyses" {
		sql += " AND kind='rca'"
	}
	if kind == "reports" {
		sql += " AND kind='report'"
	}
	return One(ctx, s.Pool, sql, id)
}
func (s *Store) Transaction(ctx context.Context, fn func(pgx.Tx) error) error {
	if tx, ok := ctx.Value(txKey{}).(pgx.Tx); ok {
		return fn(tx)
	}
	tx, e := s.Pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(72931021)"); e != nil {
		return e
	}
	if e = fn(tx); e != nil {
		return e
	}
	return tx.Commit(ctx)
}
func Audit(ctx context.Context, tx pgx.Tx, actor, action, kind, id, requestID string, before, after any) error {
	_, e := tx.Exec(ctx, "INSERT INTO audit_events(id,actor,action,resource_type,resource_id,request_id,before_ref,after_ref) VALUES($1,$2,$3,$4,$5,$6,$7,$8)", contract.ID(), actor, action, kind, id, requestID, before, after)
	return e
}

// EnsureDefaults creates runtime limits and empty model routing without
// registering example clusters or overwriting operator-managed configuration.
func (s *Store) EnsureDefaults(ctx context.Context) error {
	return s.Transaction(ctx, func(tx pgx.Tx) error {
		_, e := tx.Exec(ctx, "INSERT INTO service_profiles(id,kind,name,config) VALUES($1,'limits','C07',$2) ON CONFLICT(kind,name) DO NOTHING", contract.ID(), contract.Object{
			"max_query_days": 31, "max_body_bytes": 1048576, "max_log_lines": 1000,
			"max_requests_per_minute": 120, "max_text_length": 16000,
			"max_inflight_requests": 16, "module_timeout_seconds": 10,
		})
		if e != nil {
			return e
		}
		_, e = tx.Exec(ctx, "INSERT INTO service_profiles(id,kind,name,config) VALUES($1,'routing','model-routes','{}') ON CONFLICT(kind,name) DO NOTHING", contract.ID())
		return e
	})
}

func (s *Store) Seed(ctx context.Context) error {
	if e := s.EnsureDefaults(ctx); e != nil {
		return e
	}
	return s.Transaction(ctx, func(tx pgx.Tx) error {
		for _, cluster := range []string{"cpc-1", "cpc-2"} {
			if _, e := tx.Exec(ctx, "INSERT INTO cluster_registry(id) VALUES($1) ON CONFLICT DO NOTHING", cluster); e != nil {
				return e
			}
		}
		for _, p := range []struct {
			Name, Kind string
			Config     contract.Object
		}{{"C02", "settings", contract.Object{"description": "관측 연결 설정", "poll_interval_ms": 5000, "max_backoff_ms": 60000}}, {"C03", "settings", contract.Object{"description": "관측 주기 설정", "poll_interval_ms": 5000, "max_backoff_ms": 60000}}, {"C04", "settings", contract.Object{"description": "관측 범위 설정"}}, {"C06", "settings", contract.Object{"description": "모델 관측 설정"}}, {"model-routes", "routing", contract.Object{}}} {
			_, e := tx.Exec(ctx, "INSERT INTO service_profiles(id,kind,name,config) VALUES($1,$2,$3,$4) ON CONFLICT(kind,name) DO NOTHING", contract.ID(), p.Kind, p.Name, p.Config)
			if e != nil {
				return fmt.Errorf("seed profiles: %w", e)
			}
		}
		return nil
	})
}
