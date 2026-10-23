//go:build e2e

package api

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
)

func TestKnowledgeRateLimitDoesNotBlockReports(t *testing.T) {
	db := projectionDB(t)
	_, err := db.Pool.Exec(context.Background(), "UPDATE service_profiles SET config=jsonb_set(config,'{max_requests_per_minute}','2') WHERE kind='limits' AND name='C07'")
	projectionOK(t, err)
	jobID := ID()
	queue := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Path != "/internal/v1/jobs/report" {
			t.Error("unexpected report submission")
		}
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(Object{"job_id": jobID, "kind": "report", "status": "queued"})
	}))
	defer queue.Close()
	server := New(db, config.Config{Modules: map[string]string{"job_controller": queue.URL}})
	call := func(method, path, body string, status int) *httptest.ResponseRecorder {
		t.Helper()
		req := httptest.NewRequest(method, "/api/v1"+path, strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Idempotency-Key", ID())
		response := httptest.NewRecorder()
		server.ServeHTTP(response, req)
		if response.Code != status {
			t.Fatalf("%s %s: want %d, got %d: %s", method, path, status, response.Code, response.Body.String())
		}
		return response
	}
	// Invalid requests still consume the middleware budget across all knowledge IDs.
	call("POST", "/knowledge", "{}", 422)
	call("POST", "/knowledge/"+ID()+"/revisions", "{}", 404)
	limited := call("POST", "/knowledge/"+ID()+"/revisions/1/publish", "{}", 429)
	if limited.Header().Get("Retry-After") != "60" || !strings.Contains(limited.Body.String(), "rate_limited") {
		t.Fatal("rate-limit retry contract changed")
	}
	report := `{"scope":{"clusters":[{"cluster_id":"projection-cluster","namespaces":null}]},"time_range":{"start":"2026-10-20T00:00:00+09:00","end":"2026-10-21T00:00:00+09:00"},"timezone":"Asia/Seoul","topic_ids":["namespace_usage","incident_summary"],"group_by":["cluster","namespace"]}`
	response := call("POST", "/reports", report, 202)
	if !strings.Contains(response.Body.String(), jobID) {
		t.Fatal("report did not reach JC")
	}
	call("POST", "/reports", report, 202)
	call("POST", "/reports", report, 429)
	call("GET", "/reports", "", 200)
	// Each counter resets on its own window; finishing a request does not refund its rate.
	server.mu.Lock()
	server.writeLimits[1].window = time.Now().Add(-time.Minute)
	server.mu.Unlock()
	call("POST", "/knowledge", "{}", 422)
	call("POST", "/reports", report, 429)
	server.mu.Lock()
	server.writeLimits[0].window = time.Now().Add(-time.Minute)
	server.mu.Unlock()
	call("POST", "/reports", report, 202)
}

type waitingBody struct {
	io.Reader
	started chan struct{}
	release chan struct{}
}

func (b *waitingBody) Read(p []byte) (int, error) {
	if b.started != nil {
		close(b.started)
		b.started = nil
		<-b.release
	}
	return b.Reader.Read(p)
}

func TestKnowledgeInflightLimitDoesNotBlockOtherWrites(t *testing.T) {
	db := projectionDB(t)
	_, err := db.Pool.Exec(context.Background(), "UPDATE service_profiles SET config=jsonb_set(config,'{max_inflight_requests}','1') WHERE kind='limits' AND name='C07'")
	projectionOK(t, err)
	server := New(db, config.Config{})
	for _, busyPath := range []string{"/knowledge", "/reports"} {
		t.Run(busyPath, func(t *testing.T) {
			body := &waitingBody{Reader: strings.NewReader("{}"), started: make(chan struct{}), release: make(chan struct{})}
			started := body.started
			req := httptest.NewRequest("POST", "/api/v1"+busyPath, body)
			req.Header.Set("Content-Type", "application/json")
			response := httptest.NewRecorder()
			done := make(chan struct{})
			go func() { defer close(done); server.ServeHTTP(response, req) }()
			t.Cleanup(func() { close(body.release); <-done })
			select {
			case <-started:
			case <-time.After(5 * time.Second):
				t.Fatal("request never acquired an inflight slot")
			}
			for _, path := range []string{"/knowledge", "/reports"} {
				next := httptest.NewRequest("POST", "/api/v1"+path, strings.NewReader("{}"))
				next.Header.Set("Content-Type", "application/json")
				out := httptest.NewRecorder()
				server.ServeHTTP(out, next)
				want := 422
				if path == busyPath {
					want = 429
				}
				if out.Code != want {
					t.Fatalf("busy %s, request %s: want %d, got %d", busyPath, path, want, out.Code)
				}
			}
		})
	}
}
