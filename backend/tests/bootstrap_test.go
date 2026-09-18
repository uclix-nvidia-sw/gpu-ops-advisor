//go:build e2e

package tests

import (
	"context"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
)

// Start the real executable with the chart's seed=false configuration. Existing
// handler tests call Seed directly and cannot catch missing startup defaults.
func TestFreshBackendWithoutDemoSeed(t *testing.T) {
	ctx := context.Background()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL required")
	}
	admin, e := pgxpool.New(ctx, dsn)
	must(t, e)
	defer admin.Close()
	schema := "bootstrap_" + strings.ReplaceAll(ID(), "-", "")
	_, e = admin.Exec(ctx, "CREATE SCHEMA "+schema)
	must(t, e)
	defer admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE")
	u, e := url.Parse(dsn)
	must(t, e)
	query := u.Query()
	query.Set("search_path", schema)
	u.RawQuery = query.Encode()
	db, e := store.Open(ctx, u.String())
	must(t, e)
	defer db.Pool.Close()
	binary := os.Getenv("E2E_BACKEND_BINARY")
	if binary == "" {
		binary = filepath.Join(t.TempDir(), "backend.exe")
		if output, err := exec.Command("go", "build", "-o", binary, "../cmd/server").CombinedOutput(); err != nil {
			t.Fatalf("build backend: %v: %s", err, output)
		}
	}
	binary, e = filepath.Abs(binary)
	must(t, e)
	listener, e := net.Listen("tcp", "127.0.0.1:0")
	must(t, e)
	address := listener.Addr().String()
	listener.Close()
	base := "http://" + address + "/api/v1"
	cmd := exec.Command(binary)
	cmd.Env = append(os.Environ(), "DATABASE_URL="+u.String(), "DSX_ADDRESS="+address,
		"DSX_MIGRATE=true", "DSX_SEED=false", "DSX_SCHEDULER_ENABLED=false")
	logPath := filepath.Join(t.TempDir(), "backend.log")
	log, e := os.Create(logPath)
	must(t, e)
	cmd.Stdout, cmd.Stderr = log, log
	must(t, cmd.Start())
	defer func() { cmd.Process.Kill(); cmd.Wait(); log.Close() }()
	ready := false
	client := &http.Client{Timeout: time.Second}
	for i := 0; i < 100; i++ {
		resp, err := client.Get(base + "/health/ready")
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == 200 {
				ready = true
				break
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	if !ready {
		output, _ := os.ReadFile(logPath)
		t.Fatalf("unseeded Backend did not become ready: %s", output)
	}
	var clusters, profiles int
	must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM cluster_registry").Scan(&clusters))
	must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM service_profiles").Scan(&profiles))
	if clusters != 0 || profiles != 1 {
		t.Fatalf("expected only runtime limits, got %d clusters and %d profiles", clusters, profiles)
	}
	request(t, base+"/clusters", "GET", nil, 200)
	request(t, base+"/reports", "POST", Object{
		"scope":      Object{"clusters": []any{Object{"cluster_id": "unregistered", "namespaces": nil}}},
		"time_range": Object{"start": "2026-09-15T00:00:00Z", "end": "2026-09-16T00:00:00Z"},
		"timezone":   "UTC", "topic_ids": []string{"O01"}, "group_by": []string{"cluster"},
	}, 422, "Idempotency-Key", ID())

	registrationKey := ID()
	registration := Object{"cluster_id": "production-gpu"}
	request(t, base+"/clusters", "POST", registration, 422) // key is required
	for _, invalid := range []Object{{}, {"cluster_id": "  "}, {"cluster_id": "bad\nvalue"}, {"cluster_id": 12}, {"cluster_id": "valid", "enabled": true}} {
		request(t, base+"/clusters", "POST", invalid, 422, "Idempotency-Key", ID())
	}
	request(t, base+"/clusters", "POST", registration, 201, "Idempotency-Key", registrationKey)
	request(t, base+"/clusters", "POST", registration, 201, "Idempotency-Key", registrationKey)
	request(t, base+"/clusters", "POST", Object{"cluster_id": "other"}, 409, "Idempotency-Key", registrationKey)
	request(t, base+"/clusters", "POST", registration, 409, "Idempotency-Key", ID())
	listed := request(t, base+"/clusters", "GET", nil, 200)
	items := listed["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["cluster_id"] != "production-gpu" {
		t.Fatalf("registered cluster missing from filter list: %v", listed)
	}
	var audits int
	must(t, db.Pool.QueryRow(ctx, "SELECT count(*) FROM audit_events WHERE resource_type='cluster_registry'").Scan(&audits))
	if audits != 1 {
		t.Fatalf("registration retry produced %d audit events", audits)
	}
	scope := url.QueryEscape(`{"clusters":[{"cluster_id":"production-gpu","namespaces":null}]}`)
	request(t, base+"/assets?scope="+scope, "GET", nil, 200)
	_, e = db.Pool.Exec(ctx, "INSERT INTO cluster_registry(id,enabled) VALUES('disabled-cluster',false)")
	must(t, e)
	request(t, base+"/clusters", "POST", Object{"cluster_id": "disabled-cluster"}, 409, "Idempotency-Key", ID())
	var disabledStill bool
	must(t, db.Pool.QueryRow(ctx, "SELECT NOT enabled FROM cluster_registry WHERE id='disabled-cluster'").Scan(&disabledStill))
	if !disabledStill {
		t.Fatal("registering an existing cluster silently enabled it")
	}

	// Repeated startup initialization must preserve configured and disabled limits.
	_, e = db.Pool.Exec(ctx, "UPDATE service_profiles SET config=jsonb_set(config,'{max_body_bytes}','2048'),enabled=false,version=7 WHERE kind='limits' AND name='C07'")
	must(t, e)
	must(t, db.EnsureDefaults(ctx))
	var bodyBytes, version int
	var enabled bool
	must(t, db.Pool.QueryRow(ctx, "SELECT (config->>'max_body_bytes')::int,version,enabled FROM service_profiles WHERE kind='limits' AND name='C07'").Scan(&bodyBytes, &version, &enabled))
	if bodyBytes != 2048 || version != 7 || enabled {
		t.Fatal("runtime defaults overwrote operator configuration")
	}
	request(t, base+"/health/ready", "GET", nil, 503)
	request(t, base+"/health/live", "GET", nil, 200)
	_, e = db.Pool.Exec(ctx, "UPDATE service_profiles SET enabled=true WHERE kind='limits' AND name='C07'")
	must(t, e)
	request(t, base+"/health/ready", "GET", nil, 200)
	_, e = db.Pool.Exec(ctx, "UPDATE service_profiles SET config=jsonb_set(config,'{max_requests_per_minute}','0') WHERE kind='limits' AND name='C07'")
	must(t, e)
	request(t, base+"/health/ready", "GET", nil, 503)
	_, e = db.Pool.Exec(ctx, "DELETE FROM service_profiles WHERE kind='limits' AND name='C07'")
	must(t, e)
	request(t, base+"/health/ready", "GET", nil, 503)
	must(t, db.EnsureDefaults(ctx))
	request(t, base+"/health/ready", "GET", nil, 200)
	_, e = db.Pool.Exec(ctx, "DELETE FROM schema_migrations WHERE version=2")
	must(t, e)
	request(t, base+"/health/ready", "GET", nil, 503)
}
