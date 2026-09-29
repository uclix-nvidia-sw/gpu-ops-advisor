package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
)

func TestModelProbeAuthentication(t *testing.T) {
	for _, tc := range []struct {
		name, ref, key, reason string
		status                 int
		body                   string
		rejected               bool
	}{
		{"authenticated", "env:LLM_API_KEY", "fixture-only", "", 200, `{"choices":[{"message":{"content":"OK"}}]}`, false},
		{"no_auth", "", "", "", 200, `{"choices":[{"message":{"content":"OK"}}]}`, false},
		{"missing_key", "env:LLM_API_KEY", "", "", 0, "", true},
		{"other_environment_forbidden", "env:DATABASE_URL", "fixture-only", "", 0, "", true},
		{"unauthorized", "env:LLM_API_KEY", "fixture-only", "authentication_failed", 401, `{"error":"fixture-only"}`, false},
		{"forbidden", "env:LLM_API_KEY", "fixture-only", "permission_denied", 403, `{}`, false},
		{"missing_model", "env:LLM_API_KEY", "fixture-only", "model_or_endpoint_not_found", 404, `{}`, false},
		{"redirect", "env:LLM_API_KEY", "fixture-only", "upstream_error", 302, `{}`, false},
		{"empty_answer", "env:LLM_API_KEY", "fixture-only", "invalid_completion", 200, `{"choices":[{"message":{"content":" "}}]}`, false},
		{"bad_json", "env:LLM_API_KEY", "fixture-only", "invalid_completion", 200, `not JSON`, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls++
				var body Object
				if json.NewDecoder(r.Body).Decode(&body) != nil || r.Method != "POST" || r.URL.Path != "/v1/chat/completions" || body["model"] != "auto-router" {
					t.Error("unexpected inference request")
				}
				want := ""
				if tc.ref != "" {
					want = "Bearer " + tc.key
				}
				if r.Header.Get("Authorization") != want {
					t.Error("authentication header mismatch")
				}
				w.Header().Set("Location", "/redirect-must-not-be-followed")
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(tc.body))
			}))
			defer upstream.Close()
			u, _ := url.Parse(upstream.URL)
			s := &Server{Config: config.Config{ModelHosts: []string{u.Host}, ModelAPIKey: tc.key}}
			out, err := s.probeModel(context.Background(), Object{"version": 1, "secret_ref": tc.ref, "config": Object{"endpoint_url": upstream.URL + "/v1", "model_name": "auto-router"}})
			if tc.rejected {
				if err == nil || calls != 0 {
					t.Fatal("unsafe or missing credentials reached upstream")
				}
				return
			}
			if err != nil || calls != 1 {
				t.Fatalf("probe failed: %v calls=%d", err, calls)
			}
			schema := out["schema"].(map[string]any)
			if String(schema, "reason") != tc.reason || (tc.reason == "" && schema["status"] != "ok") {
				t.Fatal(out)
			}
			encoded, _ := json.Marshal(out)
			if strings.Contains(string(encoded), "fixture-only") {
				t.Fatal("upstream credential leaked into result")
			}
		})
	}
}

func TestModelProbeBlocksPrivateDNS(t *testing.T) {
	s := &Server{Config: config.Config{ModelHosts: []string{"localhost:12345"}}}
	out, err := s.probeModel(context.Background(), Object{"config": Object{"endpoint_url": "http://localhost:12345/v1", "model_name": "test"}})
	if err != nil || String(out["transport"].(map[string]any), "reason") != "destination_not_allowed" {
		t.Fatalf("private destination accepted: %v %v", out, err)
	}
}
