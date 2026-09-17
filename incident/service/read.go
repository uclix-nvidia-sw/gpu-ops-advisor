package service

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/shared/contract"
	"net/http"
	"strconv"
	"strings"
	"time"
)

func publicIncident(o Object) Object {
	out := Object{}
	for _, k := range []string{"id", "cluster_id", "occurred_at", "target", "scope", "state", "evidence_version", "analysis_profile_revision", "version", "memo", "review_status", "alarm_status", "alarm_resolved_at", "rca_eligibility_reason", "created_at", "updated_at"} {
		out[k] = o[k]
	}
	return out
}
func (s *Server) read(r *http.Request) (Object, error) {
	ctx := r.Context()
	path := strings.TrimPrefix(r.URL.Path, "/internal/v1/incidents")
	if path != "" {
		id := strings.TrimPrefix(path, "/")
		if !uuid(id) {
			return nil, Fail(404, "not_found", "사건을 찾을 수 없습니다.")
		}
		v, e := one(ctx, s.DB, "SELECT to_jsonb(i) FROM incidents i WHERE id=$1", id)
		if e != nil {
			return nil, e
		}
		out := publicIncident(v)
		revisions, e := one(ctx, s.DB, "SELECT jsonb_build_object('items',COALESCE(jsonb_agg(jsonb_build_object('revision',revision,'content_hash',content_hash,'snapshot',snapshot) ORDER BY revision),'[]')) FROM incident_evidence_versions WHERE incident_id=$1", id)
		if e != nil {
			return nil, e
		}
		out["evidence_versions"] = revisions["items"]
		jobs, e := one(ctx, s.DB, "SELECT jsonb_build_object('items',COALESCE(jsonb_agg(jsonb_build_object('source_key',source_key,'status',status,'job_id',job_id,'attempts',attempts,'last_error',last_error) ORDER BY created_at,id),'[]')) FROM enqueue_outbox WHERE source_module='incident' AND input_snapshot->'input'->>'incident_id'=$1", id)
		if e != nil {
			return nil, e
		}
		out["deliveries"] = jobs["items"]
		return out, nil
	}
	v := r.URL.Query()
	for k := range v {
		if !Has([]string{"scope", "state", "limit", "cursor"}, k) || len(v[k]) != 1 {
			return nil, Invalid(k)
		}
	}
	state := v.Get("state")
	if state != "" && !Has([]string{"open", "acknowledged", "resolved", "closed"}, state) {
		return nil, Invalid("state")
	}
	limit := 50
	if v.Get("limit") != "" {
		n, e := strconv.Atoi(v.Get("limit"))
		if e != nil || n < 1 || n > 100 {
			return nil, Invalid("limit")
		}
		limit = n
	}
	var scope any
	if raw := v.Get("scope"); raw != "" {
		var o Object
		if json.Unmarshal([]byte(raw), &o) != nil {
			return nil, Invalid("scope")
		}
		sc, e := ParseScope(o)
		if e != nil {
			return nil, e
		}
		scope = sc
	}
	before := time.Date(9999, 1, 1, 0, 0, 0, 0, time.UTC)
	bid := "ffffffff-ffff-ffff-ffff-ffffffffffff"
	filter := Hash(Object{"scope": scope, "state": state})
	if cursor := v.Get("cursor"); cursor != "" {
		b, e := base64.RawURLEncoding.DecodeString(cursor)
		var c Object
		if e != nil || json.Unmarshal(b, &c) != nil || !uuid(String(c, "id")) || c["filter"] != filter {
			return nil, Invalid("cursor")
		}
		before = instant(c, "created_at")
		bid = String(c, "id")
		if before.IsZero() {
			return nil, Invalid("cursor")
		}
	}
	rows, e := s.DB.Query(ctx, "SELECT to_jsonb(i) FROM incidents i WHERE ($1='' OR state=$1) AND ($2::jsonb IS NULL OR dsx_scope_contains($2,scope)) AND (created_at,id)<($3,$4::uuid) ORDER BY created_at DESC,id DESC LIMIT $5", state, scope, before, bid, limit+1)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	items := []Object{}
	for rows.Next() {
		var o Object
		if e = rows.Scan(&o); e != nil {
			return nil, e
		}
		items = append(items, publicIncident(o))
	}
	if e = rows.Err(); e != nil {
		return nil, e
	}
	var cursor any
	if len(items) > limit {
		items = items[:limit]
		last := items[limit-1]
		b, _ := json.Marshal(Object{"created_at": last["created_at"], "id": last["id"], "filter": filter})
		cursor = base64.RawURLEncoding.EncodeToString(b)
	}
	return Object{"items": items, "next_cursor": cursor}, nil
}
func (s *Server) patch(ctx context.Context, id string, b Object, h http.Header) (Object, error) {
	if e := only(b, "contract_version", "source_module", "input"); e != nil {
		return nil, e
	}
	if b["contract_version"] != "1.3" || b["source_module"] != "backend" {
		return nil, Invalid("contract_version/source_module")
	}
	input, ok := b["input"].(map[string]any)
	if !ok || len(input) == 0 {
		return nil, Invalid("input")
	}
	if e := only(input, "memo", "review_status", "state"); e != nil {
		return nil, e
	}
	if v, ok := input["memo"]; ok {
		memo, ok := v.(string)
		if !ok || len(memo) > 10000 || strings.ContainsRune(memo, 0) {
			return nil, Invalid("memo")
		}
	}
	if _, ok := input["review_status"]; ok && !Has([]string{"unreviewed", "reviewing", "reviewed"}, String(input, "review_status")) {
		return nil, Invalid("review_status")
	}
	if _, ok := input["state"]; ok && !Has([]string{"open", "acknowledged", "closed"}, String(input, "state")) {
		return nil, Invalid("state")
	}
	key := h.Get("Idempotency-Key")
	version, e := strconv.Atoi(strings.Trim(h.Get("If-Match"), "\""))
	if key == "" || len(key) > 512 || e != nil || version < 1 {
		return nil, Invalid("Idempotency-Key/If-Match")
	}
	hash := Hash(Object{"body": b, "version": version})
	var result Object
	e = s.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		previous, e := one(ctx, tx, "SELECT jsonb_build_object('hash',request_hash,'response',response) FROM incident_command_receipts WHERE incident_id=$1 AND key=$2", id, key)
		if e == nil {
			if previous["hash"] != hash {
				return Fail(409, "idempotency_conflict", "같은 키의 명령이 다릅니다.")
			}
			result, _ = previous["response"].(map[string]any)
			return nil
		}
		if !missing(e) {
			return e
		}
		j, e := one(ctx, tx, "SELECT to_jsonb(i) FROM incidents i WHERE id=$1 FOR UPDATE", id)
		if e != nil {
			return e
		}
		if Number(j, "version") != version {
			return Fail(409, "version_conflict", "사건이 변경되었습니다. 다시 조회해 주세요.")
		}
		memo, review, state := String(j, "memo"), String(j, "review_status"), String(j, "state")
		if v, ok := input["memo"]; ok {
			memo = v.(string)
		}
		if v, ok := input["review_status"]; ok {
			review = v.(string)
		}
		if v, ok := input["state"]; ok {
			state = v.(string)
		}
		_, e = tx.Exec(ctx, "UPDATE incidents SET memo=$2,review_status=$3,state=$4,version=version+1,updated_at=$5 WHERE id=$1", id, memo, review, state, now)
		if e != nil {
			return e
		}
		updated, e := one(ctx, tx, "SELECT to_jsonb(i) FROM incidents i WHERE id=$1", id)
		if e != nil {
			return e
		}
		result = publicIncident(updated)
		_, e = tx.Exec(ctx, "INSERT INTO incident_command_receipts(incident_id,key,request_hash,response) VALUES($1,$2,$3,$4)", id, key, hash, result)
		if e != nil {
			return e
		}
		_, e = tx.Exec(ctx, "INSERT INTO audit_events(id,actor,action,resource_type,resource_id,request_id,before_ref,after_ref) VALUES($1,'backend (unauthenticated)','incident_metadata','incident',$2,$3,$4,$5)", ID(), id, ID(), publicIncident(j), result)
		return e
	})
	return result, e
}
