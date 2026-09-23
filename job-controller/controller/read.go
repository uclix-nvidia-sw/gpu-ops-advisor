package controller

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

func (c *Controller) command(ctx context.Context, id, op string, b Object, h http.Header) (Object, error) {
	if e := only(b, "contract_version", "source_module", "input"); e != nil {
		return nil, e
	}
	if b["contract_version"] != "1.3" || !Has([]string{"backend", "incident"}, String(b, "source_module")) {
		return nil, Invalid("contract_version/source_module")
	}
	input, ok := b["input"].(map[string]any)
	if !ok {
		return nil, Invalid("input")
	}
	if e := only(input, "reason", "incident_id"); e != nil {
		return nil, e
	}
	if len(String(input, "reason")) > 2000 {
		return nil, Invalid("reason")
	}
	key := h.Get("Idempotency-Key")
	if key == "" || len(key) > 512 {
		return nil, Invalid("Idempotency-Key")
	}
	match := strings.Trim(h.Get("If-Match"), "\"")
	version, err := strconv.Atoi(match)
	if err != nil || version < 1 {
		return nil, Invalid("If-Match")
	}
	hash := Hash(Object{"body": b, "version": version})
	var result Object
	e := c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		j, e := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id=$1 FOR UPDATE", id)
		if e != nil {
			return e
		}
		if j["source_module"] != b["source_module"] || b["source_module"] == "incident" && input["incident_id"] != j["incident_id"] {
			return Fail(409, "kind_not_allowed", "소유한 종류의 작업만 변경할 수 있습니다.")
		}
		old, e := one(ctx, tx, "SELECT jsonb_build_object('hash',request_hash,'response',response) FROM command_receipts WHERE job_id=$1 AND operation=$2 AND key=$3", id, op, key)
		if e == nil {
			if old["hash"] != hash {
				return Fail(409, "idempotency_conflict", "같은 키의 명령이 다릅니다.")
			}
			result, _ = old["response"].(map[string]any)
			return nil
		}
		if p, ok := e.(*Problem); !ok || p.Status != 404 {
			return e
		}
		if Number(j, "version") != version {
			return Fail(409, "version_conflict", "작업이 변경되었습니다.")
		}
		if op == "cancel" {
			if terminal(String(j, "status")) {
				return Fail(409, "invalid_state", "종료한 작업은 취소할 수 없습니다.")
			}
			if j["cancel_requested_at"] == nil {
				status := String(j, "status")
				if status != "running" {
					status = "cancelled"
				}
				_, e = tx.Exec(ctx, "UPDATE jobs SET cancel_requested_at=$2,status=$3,stage=CASE WHEN $3='cancelled' THEN 'cancelled' ELSE stage END,termination_reason=CASE WHEN $3='cancelled' THEN 'cancelled' ELSE termination_reason END,queue_reason=NULL,version=version+1 WHERE id=$1", id, now, status)
				if e != nil {
					return e
				}
			}
		} else {
			if j["status"] != "failed" || j["retryable"] != true || !retryPossible(j) || !instant(j, "deadline_at").After(now) || j["cancel_requested_at"] != nil || !Has([]string{"transient_error", "dependency_unavailable", "timeout"}, String(j, "termination_reason")) {
				return Fail(409, "retry_not_allowed", "재시도 가능한 오류·예산·기한이 남아 있지 않습니다.")
			}
			if _, e = tx.Exec(ctx, "UPDATE jobs SET status='retry_wait',stage='retry_wait',eligible_at=$2,version=version+1 WHERE id=$1", id, now); e != nil {
				return e
			}
		}
		if e = c.reasons(ctx, tx, now); e != nil {
			return e
		}
		updated, e := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id=$1", id)
		if e != nil {
			return e
		}
		result = publicJob(updated)
		_, e = tx.Exec(ctx, "INSERT INTO command_receipts(job_id,operation,key,request_hash,response) VALUES($1,$2,$3,$4,$5)", id, op, key, hash, result)
		if e != nil {
			return e
		}
		_, e = tx.Exec(ctx, "INSERT INTO audit_events(id,actor,action,resource_type,resource_id,request_id,before_ref,after_ref) VALUES($1,$2,$3,'job',$4,$5,$6,$7)", ID(), b["source_module"], op, id, ID(), publicJob(j), result)
		return e
	})
	return result, e
}
func (c *Controller) queueStatus(ctx context.Context) (Object, error) {
	var out Object
	e := c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		a, e := c.available(ctx, tx, now)
		if e != nil {
			return e
		}
		kinds := Object{}
		for _, kind := range []string{"rca", "report"} {
			v, e := one(ctx, tx, `SELECT jsonb_build_object('waiting',count(*) FILTER(WHERE status IN ('queued','retry_wait')),'running',count(*) FILTER(WHERE status='running'),'failed',count(*) FILTER(WHERE status='failed'),'expired',count(*) FILTER(WHERE status='expired'),'worker_unavailable',count(*) FILTER(WHERE queue_reason='worker_unavailable'),'capacity_wait',count(*) FILTER(WHERE queue_reason='capacity_wait'),'inference_quarantined',count(*) FILTER(WHERE queue_reason='inference_quarantined')) FROM jobs WHERE kind=$1 AND source_module IS NOT NULL`, kind)
			if e != nil {
				return e
			}
			v["capacity_limit"] = c.Config.KindLimits[kind]
			v["reserved_slots"] = a.kind[kind]
			v["worker_available"] = len(a.workers[kind]) > 0
			kinds[kind] = v
		}
		out = Object{"kinds": kinds, "shared": Object{"limit": c.Config.SharedLimit, "reserved_slots": a.used, "quarantined_slots": a.quarantine}, "config_revision": c.Revision, "observed_at": now}
		return nil
	})
	return out, e
}
func (c *Controller) readJobs(r *http.Request, parts []string) (Object, int, error) {
	ctx := r.Context()
	if len(parts) == 2 {
		if !uuid(parts[1]) {
			return nil, 0, Invalid("id")
		}
		j, e := one(ctx, c.DB, "SELECT to_jsonb(j) FROM jobs j WHERE id=$1 AND source_module IS NOT NULL", parts[1])
		return publicJob(j), 200, e
	}
	if len(parts) != 1 {
		return nil, 0, Fail(404, "not_found", "경로가 없습니다.")
	}
	v := r.URL.Query()
	for k := range v {
		if !Has([]string{"kind", "status", "limit", "cursor"}, k) {
			return nil, 0, Invalid(k)
		}
	}
	kind, status := v.Get("kind"), v.Get("status")
	if kind != "" && !Has([]string{"rca", "report"}, kind) {
		return nil, 0, Invalid("kind")
	}
	if status != "" && !Has([]string{"queued", "running", "retry_wait", "failed", "succeeded", "cancelled", "expired"}, status) {
		return nil, 0, Invalid("status")
	}
	limit := 50
	if v.Get("limit") != "" {
		n, e := strconv.Atoi(v.Get("limit"))
		if e != nil || n < 1 || n > 100 {
			return nil, 0, Invalid("limit")
		}
		limit = n
	}
	before := time.Date(9999, 1, 1, 0, 0, 0, 0, time.UTC)
	bid := "ffffffff-ffff-ffff-ffff-ffffffffffff"
	if raw := v.Get("cursor"); raw != "" {
		data, e := base64.RawURLEncoding.DecodeString(raw)
		var cursor Object
		if e != nil || json.Unmarshal(data, &cursor) != nil || !uuid(String(cursor, "id")) || cursor["kind"] != kind || cursor["status"] != status {
			return nil, 0, Invalid("cursor")
		}
		before = instant(cursor, "created_at")
		bid = String(cursor, "id")
		if before.IsZero() {
			return nil, 0, Invalid("cursor")
		}
	}
	rows, e := c.DB.Query(ctx, "SELECT to_jsonb(j) FROM jobs j WHERE source_module IS NOT NULL AND ($1='' OR kind=$1) AND ($2='' OR status=$2) AND (created_at,id)<($3,$4::uuid) ORDER BY created_at DESC,id DESC LIMIT $5", kind, status, before, bid, limit+1)
	if e != nil {
		return nil, 0, e
	}
	defer rows.Close()
	items := []Object{}
	for rows.Next() {
		var j Object
		if e = rows.Scan(&j); e != nil {
			return nil, 0, e
		}
		items = append(items, publicJob(j))
	}
	if e = rows.Err(); e != nil {
		return nil, 0, e
	}
	var next any
	if len(items) > limit {
		items = items[:limit]
		last := items[limit-1]
		raw, _ := json.Marshal(Object{"created_at": last["created_at"], "id": last["id"], "kind": kind, "status": status})
		next = base64.RawURLEncoding.EncodeToString(raw)
	}
	return Object{"items": items, "next_cursor": next}, 200, nil
}
