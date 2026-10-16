//go:build e2e

package api

import (
	"context"
	"encoding/json"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestIncidentSummaries(t *testing.T) {
	db := projectionDB(t)
	ctx := context.Background()
	s := New(db, config.Config{})
	published, candidate, _ := projectionCandidate(t, db, "rca", []byte(`{"result_status":"partial","narrative_status":"complete","private_body":"NEVER_RETURN"}`))
	var incident string
	projectionOK(t, db.Pool.QueryRow(ctx, "SELECT incident_id::text FROM jobs WHERE id=$1", published).Scan(&incident))
	latest := ID()
	_, err := db.Pool.Exec(ctx, `INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at,incident_id,evidence_version,created_at)
 SELECT $1::uuid,kind,source_module,$1::text,scope,input_snapshot,request_hash,'running',deadline_at,incident_id,evidence_version,created_at+interval '1 second' FROM jobs WHERE id=$2`, latest, published)
	projectionOK(t, err)
	_, err = db.Pool.Exec(ctx, `INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,1,'rca','1.3','{"result_status":"unpublished-secret"}','fixture','valid')`, ID(), latest)
	projectionOK(t, err)
	get := func(path string) Object {
		t.Helper()
		w := httptest.NewRecorder()
		s.ServeHTTP(w, httptest.NewRequest("GET", "/api/v1"+path, nil))
		if w.Code != 200 {
			t.Fatalf("%s: %d %s", path, w.Code, w.Body.String())
		}
		if strings.Contains(w.Body.String(), "NEVER_RETURN") || strings.Contains(w.Body.String(), "unpublished-secret") {
			t.Fatal("private data leaked")
		}
		var v Object
		projectionOK(t, json.Unmarshal(w.Body.Bytes(), &v))
		return v
	}
	check := func(v Object) {
		t.Helper()
		summary := v["rca_summary"].(map[string]any)
		last := summary["latest_job"].(map[string]any)
		pub := summary["latest_published"].(map[string]any)
		if last["job_id"] != latest || last["status"] != "running" || pub["job_id"] != published || pub["result_ref"] != candidate || pub["result_status"] != "partial" {
			t.Fatalf("wrong summary: %v", summary)
		}
	}
	check(get("/incidents/" + incident))
	list := get("/incidents?limit=1")
	check(list["items"].([]any)[0].(map[string]any))
	empty := ID()
	_, err = db.Pool.Exec(ctx, `INSERT INTO incidents(id,cluster_id,scope,created_at) SELECT $1,cluster_id,scope,created_at+interval '5 seconds' FROM incidents WHERE id=$2`, empty, incident)
	projectionOK(t, err)
	first := get("/incidents?limit=1")
	items := first["items"].([]any)
	summary := items[0].(map[string]any)["rca_summary"].(map[string]any)
	if summary["latest_job"] != nil || summary["latest_published"] != nil {
		t.Fatal("missing results are not null")
	}
	second := get("/incidents?limit=1&cursor=" + url.QueryEscape(first["next_cursor"].(string)))
	check(second["items"].([]any)[0].(map[string]any))
	// A publication pointer must belong to the same job, even if the ID exists.
	_, otherCandidate, _ := projectionCandidate(t, db, "rca", []byte(`{"result_status":"wrong-job"}`))
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=$2 WHERE id=$1", latest, otherCandidate)
	projectionOK(t, err)
	check(get("/incidents/" + incident))
	// Equal timestamps use the job ID as a deterministic tie breaker.
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET created_at=(SELECT created_at FROM jobs WHERE id=$1) WHERE id=$2", published, latest)
	projectionOK(t, err)
	v := get("/incidents/" + incident)
	last := v["rca_summary"].(map[string]any)["latest_job"].(map[string]any)
	want := published
	if latest > published {
		want = latest
	}
	if last["job_id"] != want {
		t.Fatal("unstable tie ordering")
	}
	// A mismatched scope cannot substitute a result from a broader investigation.
	_, err = db.Pool.Exec(ctx, `UPDATE jobs SET scope='{"clusters":[{"cluster_id":"other","namespaces":null}]}' WHERE id=$1`, latest)
	projectionOK(t, err)
	v = get("/incidents/" + incident)
	if v["rca_summary"].(map[string]any)["latest_job"].(map[string]any)["job_id"] != published {
		t.Fatal("scope mismatch exposed")
	}
}
