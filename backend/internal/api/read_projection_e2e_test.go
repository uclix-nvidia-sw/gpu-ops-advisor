//go:build e2e

package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/backend/internal/config"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"gpu-ops-advisor/shared/migrations"
)

const unprojectedResultSQL = "SELECT to_jsonb(c) FROM result_candidates c WHERE id::text=$1 AND job_id::text=$2 AND kind=$3"

func projectionDB(t testing.TB) *store.Store {
	t.Helper()
	dsn := os.Getenv("E2E_DATABASE_URL")
	if dsn == "" {
		t.Fatal("E2E_DATABASE_URL must identify an isolated test database")
	}
	ctx := context.Background()
	admin, err := pgxpool.New(ctx, dsn)
	projectionOK(t, err)
	t.Cleanup(admin.Close)
	schema := "projection_" + strings.ReplaceAll(ID(), "-", "")
	_, err = admin.Exec(ctx, "CREATE SCHEMA "+schema)
	projectionOK(t, err)
	t.Cleanup(func() { _, err := admin.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE"); projectionOK(t, err) })
	u, err := url.Parse(dsn)
	projectionOK(t, err)
	query := u.Query()
	query.Set("search_path", schema)
	u.RawQuery = query.Encode()
	db, err := store.Open(ctx, u.String())
	projectionOK(t, err)
	t.Cleanup(db.Pool.Close)
	projectionOK(t, db.Migrate(ctx))
	projectionOK(t, db.EnsureDefaults(ctx))
	_, err = db.Pool.Exec(ctx, migrations.Queue)
	projectionOK(t, err)
	_, err = db.Pool.Exec(ctx, "INSERT INTO cluster_registry(id) VALUES('projection-cluster')")
	projectionOK(t, err)
	return db
}

func projectionOK(t testing.TB, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func projectionCandidate(t testing.TB, db *store.Store, kind string, body []byte) (string, string, string) {
	t.Helper()
	ctx := context.Background()
	job, candidate, source := ID(), ID(), "backend"
	var incident any
	scope := Object{"clusters": []any{Object{"cluster_id": "projection-cluster", "namespaces": nil}}}
	if kind == "rca" {
		source, incident = "incident", ID()
		_, err := db.Pool.Exec(ctx, "INSERT INTO incidents(id,cluster_id,scope) VALUES($1,'projection-cluster',$2)", incident, scope)
		projectionOK(t, err)
		_, err = db.Pool.Exec(ctx, "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES($1,1,'{}','fixture')", incident)
		projectionOK(t, err)
	}
	_, err := db.Pool.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,status,deadline_at,incident_id,evidence_version) VALUES($1,$2,$3,$6,$4,'{}','fixture','succeeded',now()+interval '1 day',$5,1)", job, kind, source, scope, incident, "manual:"+job)
	projectionOK(t, err)
	hash := Hash(json.RawMessage(body))
	_, err = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,1,$3,'1.3',$4,$5,'valid')", candidate, job, kind, json.RawMessage(body), hash)
	projectionOK(t, err)
	_, err = db.Pool.Exec(ctx, "UPDATE jobs SET published_result_id=$2 WHERE id=$1", job, candidate)
	projectionOK(t, err)
	return job, candidate, hash
}

func TestPublishedReportProjection(t *testing.T) {
	db := projectionDB(t)
	ctx := context.Background()
	server := New(db, config.Config{})
	get := func(path string) *httptest.ResponseRecorder {
		t.Helper()
		response := httptest.NewRecorder()
		server.ServeHTTP(response, httptest.NewRequest("GET", "/api/v1"+path, nil))
		if response.Code != 200 {
			t.Fatalf("%s: %d %s", path, response.Code, response.Body.String())
		}
		return response
	}
	original := []byte(`{"versions":{"criteria":"1.3"},"result_status":"partial","narrative_status":"complete","narrative":[{"title":"Saved title","text":"Saved narrative"}],"quality":{"unknown":true},"topics":[{"topic_id":"O01","metrics":[{"id":"O01.node_condition_seconds","value":0,"unit":"seconds","evidence_refs":["e1"]}],"facts":[{"id":"f1","value":null}],"evidence_refs":["e1","e2"],"quality":{"other":{"value":null},"node_condition_observations":[{"intervals":[[1,2,0]],"evidence_refs":["e1"]}]}},{"topic_id":"O08","metrics":[],"quality":{"node_condition_observations":"preserve other topic"}}]}`)
	evidenceID := ID()
	original = bytes.ReplaceAll(original, []byte(`"e1"`), []byte(`"`+evidenceID+`"`))
	var expected Object
	projectionOK(t, json.Unmarshal(original, &expected))
	originalHash := Hash(expected)
	delete(expected["topics"].([]any)[0].(map[string]any)["quality"].(map[string]any), "node_condition_observations")
	job, candidate, hash := projectionCandidate(t, db, "report", original)
	_, err := db.Pool.Exec(ctx, "INSERT INTO evidence(id,job_id,attempt_no,scope,query_id,tool_status,snapshot) SELECT $1,id,1,scope,'D20','ok','{\"intervals\":[[1,2,0]]}' FROM jobs WHERE id=$2", evidenceID, job)
	projectionOK(t, err)
	var evidence Object
	projectionOK(t, json.Unmarshal(get("/jobs/"+job+"/evidence/"+evidenceID+"?attempt=1").Body.Bytes(), &evidence))
	if Hash(evidence["snapshot"]) != Hash(Object{"intervals": []any{[]any{float64(1), float64(2), float64(0)}}}) {
		t.Fatal("original evidence no longer accessible")
	}
	// A private later attempt is never substituted for the published result.
	_, err = db.Pool.Exec(ctx, "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES($1,$2,2,'report','1.3','{\"result_status\":\"private\"}','private','valid')", ID(), job)
	projectionOK(t, err)
	for _, route := range []string{"reports", "jobs"} {
		var detail Object
		projectionOK(t, json.Unmarshal(get("/"+route+"/"+job).Body.Bytes(), &detail))
		if Hash(detail["result"]) != Hash(expected) {
			t.Fatalf("%s: projected result changed fields besides O01 intervals", route)
		}
		metadata := detail["result_projection"].(map[string]any)
		if metadata["stored_content_hash"] != hash || Hash(metadata["omitted_fields"]) != Hash([]string{"topics[topic_id=O01].quality.node_condition_observations"}) || detail["result_ref"] != candidate {
			t.Fatalf("%s: projection provenance incorrect: %v", route, metadata)
		}
	}
	for _, format := range []string{"csv", "html"} {
		// Same exporter and all metrics/narrative, only the duplicate raw field differs.
		want := httptest.NewRecorder()
		projectionOK(t, exportMetrics(want, job, format, expected, reportMetrics(expected), Object{"stored_content_hash": hash}))
		got := get("/reports/" + job + "/export?format=" + format)
		if got.Header().Get("X-Result-Projection") != "o01-condition-intervals-omitted" || got.Header().Get("X-Stored-Content-Hash") != hash {
			t.Fatal("export projection provenance missing")
		}
		if format == "html" && (!strings.Contains(got.Body.String(), "조회용 결과") || !strings.Contains(got.Body.String(), hash)) {
			t.Fatal("HTML omits projection notice")
		}
		if got.Body.String() != want.Body.String() {
			t.Fatalf("%s export changed", format)
		}
	}
	var trace Object
	projectionOK(t, json.Unmarshal(get("/jobs/"+job+"/trace").Body.Bytes(), &trace))
	publication := trace["publication"].(map[string]any)["record"].(map[string]any)
	if publication["content_hash"] != hash || publication["body"] != nil {
		t.Fatal("trace exposes body or changes original hash")
	}
	stored, err := store.One(ctx, db.Pool, unprojectedResultSQL, candidate, job, "report")
	projectionOK(t, err)
	if Hash(stored["body"]) != originalHash || stored["content_hash"] != hash {
		t.Fatal("read modified stored result/hash")
	}
	if _, err := db.Pool.Exec(ctx, "UPDATE result_candidates SET body='{}' WHERE id=$1", candidate); err == nil {
		t.Fatal("published candidate lost immutability")
	}

	cases := []struct {
		name, kind, body string
		omitted          bool
	}{
		{"absent_topics", "report", `{}`, false},
		{"null_topics", "report", `{"versions":{"criteria":"1.3"},"topics":null}`, false},
		{"scalar_topics", "report", `{"versions":{"criteria":"1.3"},"topics":"legacy"}`, false},
		{"empty_topics", "report", `{"versions":{"criteria":"1.3"},"topics":[]}`, false},
		{"mixed_topics", "report", `{"versions":{"criteria":"1.3"},"topics":[null,12,"scalar",{"topic_id":"O01","quality":null},{"topic_id":"O01","quality":[]}]}`, false},
		{"new_report", "report", `{"versions":{"criteria":"1.3"},"topics":[{"topic_id":"O01","quality":{"other":0}}]}`, false},
		{"rca", "rca", string(original), false},
		{"legacy_criteria", "report", strings.Replace(string(original), `"criteria":"1.3"`, `"criteria":"1.2"`, 1), false},
		{"unknown_criteria", "report", strings.Replace(string(original), `"versions":{"criteria":"1.3"},`, "", 1), false},
		{"null_duplicate", "report", `{"versions":{"criteria":"1.3"},"topics":[{"topic_id":"O01","quality":{"node_condition_observations":null}}]}`, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			jid, rid, _ := projectionCandidate(t, db, tc.kind, []byte(tc.body))
			got, err := store.One(ctx, db.Pool, publishedResultSQL, rid, jid, tc.kind)
			projectionOK(t, err)
			if got["projected"] != tc.omitted {
				t.Fatalf("unexpected projection marker: %v", got)
			}
			var source Object
			projectionOK(t, json.Unmarshal([]byte(tc.body), &source))
			if !tc.omitted && Hash(got["body"]) != Hash(source) {
				t.Fatal("unrelated body changed")
			}
			var detail Object
			projectionOK(t, json.Unmarshal(get("/jobs/"+jid).Body.Bytes(), &detail))
			if (detail["result_projection"] != nil) != tc.omitted {
				t.Fatal("unexpected response metadata")
			}
		})
	}
	// Legacy metric-free fallback exports use the same bounded read and provenance.
	fallbackJob, _, fallbackHash := projectionCandidate(t, db, "report", []byte(`{"versions":{"criteria":"1.3"},"topics":[{"topic_id":"O01","quality":{"node_condition_observations":[[1,2,0]]}}]}`))
	for _, format := range []string{"csv", "html"} {
		response := get("/reports/" + fallbackJob + "/export?format=" + format)
		if response.Header().Get("X-Stored-Content-Hash") != fallbackHash || strings.Contains(response.Body.String(), "node_condition_observations") {
			t.Fatal("fallback export bypasses projection")
		}
	}
	// Candidate association checks still reject another job or kind.
	for _, args := range [][]any{{candidate, ID(), "report"}, {candidate, job, "rca"}} {
		if _, err := store.One(ctx, db.Pool, publishedResultSQL, args...); err == nil {
			t.Fatal("cross-job/kind result exposed")
		}
	}
}

// Synthetic production shape: 153 condition series × 5,760 15-second intervals.
func largeProjectionBody() []byte {
	var body bytes.Buffer
	body.WriteString(`{"versions":{"criteria":"1.3"},"result_status":"partial","narrative_status":"complete","narrative":[{"title":"Synthetic report","text":"Stored narrative"}],"topics":[{"topic_id":"O01","metrics":[{"id":"O01.node_condition_seconds","value":86400,"unit":"seconds","evidence_refs":["e1"]}],"facts":[{"value":null}],"evidence_refs":["e1"],"quality":{"other":"preserved","node_condition_observations":[`)
	for series := 0; series < 153; series++ {
		if series > 0 {
			body.WriteByte(',')
		}
		fmt.Fprintf(&body, `{"cluster_id":"synthetic","labels":{"node":"node-%03d","condition":"Ready","status":"true"},"evidence_refs":["e1"],"intervals":[`, series)
		for interval := 0; interval < 5760; interval++ {
			if interval > 0 {
				body.WriteByte(',')
			}
			start := int64(1791763200 + interval*15)
			fmt.Fprintf(&body, "[%d.0,%d.0,%d.0]", start, start+15, (interval+series)%2)
		}
		body.WriteString("]}")
	}
	body.WriteString(`]}},{"topic_id":"O08","metrics":[{"id":"O08.gpu_count","value":23,"evidence_refs":["e2"]}],"quality":{"reason":null}}]}`)
	return body.Bytes()
}

func BenchmarkPublishedReportProjection(b *testing.B) {
	db := projectionDB(b)
	ctx := context.Background()
	body := largeProjectionBody()
	job, candidate, _ := projectionCandidate(b, db, "report", body)
	var original Object
	projectionOK(b, json.Unmarshal(body, &original))
	delete(original["topics"].([]any)[0].(map[string]any)["quality"].(map[string]any), "node_condition_observations")
	projected, err := store.One(ctx, db.Pool, publishedResultSQL, candidate, job, "report")
	projectionOK(b, err)
	if Hash(projected["body"]) != Hash(original) {
		b.Fatal("projection changed metrics/evidence/other fields")
	}
	var storedBytes, intervalCount int64
	projectionOK(b, db.Pool.QueryRow(ctx, "SELECT pg_column_size(body), (SELECT sum(jsonb_array_length(s->'intervals')) FROM jsonb_array_elements(body#>'{topics,0,quality,node_condition_observations}') s) FROM result_candidates WHERE id=$1", candidate).Scan(&storedBytes, &intervalCount))
	if intervalCount != 881280 {
		b.Fatalf("fixture interval count=%d", intervalCount)
	}
	b.Logf("synthetic series=153 intervals=%d stored_body_bytes=%d; SQL+transport+JSON decoding on same database/pool", intervalCount, storedBytes)
	for _, order := range []string{"before_first", "after_first"} {
		cases := []struct{ name, sql string }{{"before", unprojectedResultSQL}, {"after", publishedResultSQL}}
		if order == "after_first" {
			cases[0], cases[1] = cases[1], cases[0]
		}
		for _, tc := range cases {
			b.Run(order+"/"+tc.name, func(b *testing.B) {
				var raw []byte
				projectionOK(b, db.Pool.QueryRow(ctx, tc.sql, candidate, job, "report").Scan(&raw))
				size := len(raw)
				// Warm each SQL/decoder path equally before measuring.
				_, err := store.One(ctx, db.Pool, tc.sql, candidate, job, "report")
				projectionOK(b, err)
				b.ReportAllocs()
				b.ResetTimer()
				for i := 0; i < b.N; i++ {
					if _, err := store.One(ctx, db.Pool, tc.sql, candidate, job, "report"); err != nil {
						b.Fatal(err)
					}
				}
				b.StopTimer()
				b.ReportMetric(float64(size), "wire_bytes/op")
			})
		}
	}
}
