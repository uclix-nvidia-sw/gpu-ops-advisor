//go:build e2e

package api

import (
	"context"
	"encoding/json"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"net/http/httptest"
	"net/url"
	"testing"
)

func TestIncidentSearch(t *testing.T) {
	db := projectionDB(t)
	ctx := context.Background()
	for _, title := range []string{"SXID 11021 Single bit ECC errors", "SXID:11019 ingress RLAN DBE", "디스크 여유 공간 부족"} {
		_, err := db.Pool.Exec(ctx, `INSERT INTO incidents(id,cluster_id,scope,target,first_seen,occurred_at) VALUES($1,'projection-cluster','{"clusters":[{"cluster_id":"projection-cluster"}]}',jsonb_build_object('title',$2::text),'2026-10-29T06:00:00Z','2026-10-29T06:00:00Z')`, ID(), title)
		projectionOK(t, err)
	}
	server := New(db, config.Config{})
	for _, tc := range []struct {
		query, extra string
		want         int
	}{
		{"sxid:11021", "", 1}, {"Single_bit", "", 1}, {"RLAN", "", 1}, {"공간", "", 1},
		{"%", "", 0}, {"does-not-exist", "", 0}, {"", "", 3},
		{"SXID11021", "&from=2026-10-30T00:00:00Z", 0},
	} {
		t.Run(tc.query+tc.extra, func(t *testing.T) {
			w := httptest.NewRecorder()
			server.ServeHTTP(w, httptest.NewRequest("GET", "/api/v1/incidents?q="+url.QueryEscape(tc.query)+tc.extra, nil))
			if w.Code != 200 {
				t.Fatalf("%d: %s", w.Code, w.Body.String())
			}
			var body Object
			projectionOK(t, json.Unmarshal(w.Body.Bytes(), &body))
			if got := len(body["items"].([]any)); got != tc.want {
				t.Fatalf("got %d want %d", got, tc.want)
			}
		})
	}
}
