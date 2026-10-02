package controller

import (
	"context"
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/shared/contract"
	"math/rand/v2"
	"time"
)

func terminal(status string) bool {
	return Has([]string{"succeeded", "failed", "cancelled", "expired"}, status)
}
func retryPossible(j Object) bool {
	ex := execution(j)
	return Number(j, "attempt_no") < Number(j, "max_attempts") && ex.AttemptBudget > 0 && Number(j, "budget_used")+ex.AttemptBudget <= Number(j, "token_budget")
}
func (c *Controller) finish(ctx context.Context, tx pgx.Tx, j Object, now time.Time, code string, retryable, remoteEnded bool) error {
	status := "failed"
	var eligible any = now
	if j["cancel_requested_at"] != nil {
		status = "cancelled"
		code = "cancelled"
		if !remoteEnded {
			status = "running"
			code = "cancellation_pending_remote_termination"
		}
	}
	if !instant(j, "deadline_at").After(now) {
		status = "expired"
		code = "deadline_exceeded"
	} else if j["cancel_requested_at"] == nil && retryable && retryPossible(j) {
		status = "retry_wait"
		backoff := min(300, execution(j).RetrySeconds*(1<<min(6, max(0, Number(j, "attempt_no")-1))))
		eligible = now.Add(time.Duration(backoff)*time.Second + time.Duration(rand.Int64N(int64(time.Second))))
	}
	_, e := tx.Exec(ctx, "UPDATE jobs SET status=$2,stage=$2,termination_reason=$3,retryable=$4,eligible_at=$5,queue_reason=NULL,version=version+1 WHERE id=$1", j["id"], status, code, retryable, eligible)
	if e != nil {
		return e
	}
	_, e = tx.Exec(ctx, "UPDATE job_attempts SET ended_at=$3,termination_reason=$4,stage=$4 WHERE job_id=$1 AND attempt_no=$2", j["id"], j["attempt_no"], now, code)
	if e != nil {
		return e
	}
	state := "quarantined"
	var released any
	if remoteEnded {
		state = "released"
		released = now
	}
	_, e = tx.Exec(ctx, "UPDATE slot_reservations SET state=$3,released_at=$4 WHERE job_id=$1 AND attempt_no=$2 AND state='active'", j["id"], j["attempt_no"], state, released)
	return e
}
func (c *Controller) Sweep(ctx context.Context) error {
	return c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		rows, e := tx.Query(ctx, `SELECT to_jsonb(j) FROM jobs j JOIN job_attempts a ON a.job_id=j.id AND a.attempt_no=j.attempt_no WHERE j.source_module IS NOT NULL AND j.status='running' AND (a.ended_at IS NULL OR j.deadline_at<=$1) AND (j.deadline_at<=$1 OR a.lease_expires_at<=$1 OR NOT EXISTS(SELECT 1 FROM workers w WHERE w.worker_id=a.worker_id AND w.boot_id::text=a.boot_id AND NOT retired)) ORDER BY j.id FOR NO KEY UPDATE OF j,a`, now)
		if e != nil {
			return e
		}
		jobs := []Object{}
		for rows.Next() {
			var j Object
			if e = rows.Scan(&j); e != nil {
				rows.Close()
				return e
			}
			jobs = append(jobs, j)
		}
		e = rows.Err()
		rows.Close()
		if e != nil {
			return e
		}
		for _, j := range jobs {
			if e = c.finish(ctx, tx, j, now, "timeout", true, false); e != nil {
				return e
			}
		}
		_, e = tx.Exec(ctx, `UPDATE jobs SET status='expired',stage='expired',termination_reason='deadline_exceeded',queue_reason=NULL,version=version+1 WHERE source_module IS NOT NULL AND status IN ('queued','retry_wait') AND deadline_at<=$1`, now)
		if e != nil {
			return e
		}
		_, e = tx.Exec(ctx, `UPDATE jobs SET status='failed',stage='failed',termination_reason=CASE WHEN attempt_no>=max_attempts THEN 'attempts_exhausted' ELSE 'budget_exhausted' END,retryable=false,queue_reason=NULL,version=version+1 WHERE source_module IS NOT NULL AND status IN ('queued','retry_wait') AND (attempt_no>=max_attempts OR budget_used+COALESCE((versions->'execution'->>'attempt_budget')::bigint,token_budget+1)>token_budget)`)
		if e != nil {
			return e
		}
		return c.reasons(ctx, tx, now)
	})
}

// ReleaseQuarantine is an operator CLI action after independently verifying remote termination.
// Expiry of a lease alone is never evidence that an external inference has stopped.
func (c *Controller) ReleaseQuarantine(ctx context.Context, id string, n int, evidence string) error {
	if !uuid(id) || n < 1 || len(evidence) < 10 || len(evidence) > 4000 {
		return Invalid("termination_evidence")
	}
	return c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		tag, e := tx.Exec(ctx, "UPDATE slot_reservations SET state='released',released_at=$3,release_evidence=$4 WHERE job_id=$1 AND attempt_no=$2 AND state='quarantined'", id, n, now, evidence)
		if e != nil {
			return e
		}
		if tag.RowsAffected() != 1 {
			return Fail(409, "not_quarantined", "격리된 슬롯이 없습니다.")
		}
		_, e = tx.Exec(ctx, "UPDATE jobs SET status='cancelled',stage='cancelled',termination_reason='cancelled',version=version+1 WHERE id=$1 AND status='running' AND attempt_no=$2 AND cancel_requested_at IS NOT NULL", id, n)
		if e != nil {
			return e
		}
		_, e = tx.Exec(ctx, "INSERT INTO audit_events(id,actor,action,resource_type,resource_id,request_id,after_ref) VALUES($1,'local-operator','release_quarantine','job',$2,$3,$4)", ID(), id, ID(), Object{"attempt_no": n, "evidence": evidence})
		if e != nil {
			return e
		}
		return c.reasons(ctx, tx, now)
	})
}
func (c *Controller) attempt(ctx context.Context, id, op string, b Object) (Object, error) {
	keys := []string{"attempt_no", "claim_token"}
	switch op {
	case "heartbeat":
		keys = append(keys, "stage", "remote_call_state")
	case "complete":
		keys = append(keys, "candidate_id", "content_hash")
	case "fail":
		keys = append(keys, "code", "retryable", "remote_call_state")
	}
	if e := only(b, keys...); e != nil {
		return nil, e
	}
	n := Number(b, "attempt_no")
	if !integer(b, "attempt_no") || String(b, "claim_token") == "" {
		return nil, Invalid("attempt_no/claim_token")
	}
	var result Object
	e := c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		j, err := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id=$1 FOR NO KEY UPDATE", id)
		if err != nil {
			return err
		}
		a, err := one(ctx, tx, "SELECT to_jsonb(a) FROM job_attempts a WHERE job_id=$1 AND attempt_no=$2 FOR NO KEY UPDATE", id, n)
		if err != nil {
			if missing(err) {
				return stale()
			}
			return err
		}
		if a["claim_token"] != b["claim_token"] {
			return stale()
		}
		if op == "complete" && a["completion_response"] != nil {
			old, _ := a["completion_response"].(map[string]any)
			if old["candidate_id"] == b["candidate_id"] && old["content_hash"] == b["content_hash"] {
				result = old
				return nil
			}
			return stale()
		}
		// Recheck time after row-lock waits; never renew or publish an expired attempt.
		if err = tx.QueryRow(ctx, "SELECT clock_timestamp()").Scan(&now); err != nil {
			return err
		}
		if Number(j, "attempt_no") != n || j["status"] != "running" || a["ended_at"] != nil || !instant(a, "lease_expires_at").After(now) || !instant(j, "deadline_at").After(now) {
			return stale()
		}
		var current bool
		if err = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM workers WHERE worker_id=$1 AND boot_id::text=$2 AND NOT retired)", a["worker_id"], a["boot_id"]).Scan(&current); err != nil {
			return err
		}
		if !current {
			return stale()
		}
		if op == "heartbeat" || op == "fail" {
			if !Has([]string{"not_started", "running", "terminated", "unknown"}, String(b, "remote_call_state")) {
				return Invalid("remote_call_state")
			}
		}
		switch op {
		case "heartbeat":
			if a["remote_call_state"] != "not_started" && b["remote_call_state"] == "not_started" {
				return Invalid("remote_call_state")
			}
			stage := String(b, "stage")
			if stage == "" || len(stage) > 100 {
				return Invalid("stage")
			}
			lease := now.Add(time.Duration(execution(j).LeaseSeconds) * time.Second)
			if lease.After(instant(j, "deadline_at")) {
				lease = instant(j, "deadline_at")
			}
			_, err = tx.Exec(ctx, "UPDATE job_attempts SET lease_expires_at=$3,stage=$4,remote_call_state=$5 WHERE job_id=$1 AND attempt_no=$2", id, n, lease, stage, b["remote_call_state"])
			if err != nil {
				return err
			}
			if _, err = tx.Exec(ctx, "UPDATE jobs SET stage=$2 WHERE id=$1", id, stage); err != nil {
				return err
			}
			if _, err = tx.Exec(ctx, "UPDATE workers SET last_seen_at=$3 WHERE worker_id=$1 AND boot_id::text=$2", a["worker_id"], a["boot_id"], now); err != nil {
				return err
			}
			result = Object{"job_id": id, "attempt_no": n, "lease_expires_at": lease, "cancel_requested": j["cancel_requested_at"] != nil, "deadline_at": j["deadline_at"]}
		case "fail":
			code := String(b, "code")
			can, ok := b["retryable"].(bool)
			if !ok || !Has([]string{"transient_error", "dependency_unavailable", "timeout", "invalid_input", "invalid_result", "insufficient_data", "budget_exhausted", "cancelled", "internal_error"}, code) {
				return Invalid("code/retryable")
			}
			can = can && Has([]string{"transient_error", "dependency_unavailable", "timeout"}, code)
			ended := Has([]string{"not_started", "terminated"}, String(b, "remote_call_state"))
			if a["remote_call_state"] != "not_started" && b["remote_call_state"] == "not_started" {
				return Invalid("remote_call_state")
			}
			if _, err = tx.Exec(ctx, "UPDATE job_attempts SET remote_call_state=$3 WHERE job_id=$1 AND attempt_no=$2", id, n, b["remote_call_state"]); err != nil {
				return err
			}
			if err = c.finish(ctx, tx, j, now, code, can, ended); err != nil {
				return err
			}
			updated, err := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id=$1", id)
			if err != nil {
				return err
			}
			result = publicJob(updated)
		case "complete":
			if j["cancel_requested_at"] != nil {
				return stale()
			}
			if !uuid(String(b, "candidate_id")) || String(b, "content_hash") == "" {
				return Invalid("candidate_id/content_hash")
			}
			candidate, err := one(ctx, tx, "SELECT to_jsonb(c) FROM result_candidates c WHERE id=$1 FOR UPDATE", b["candidate_id"])
			if err != nil {
				if missing(err) {
					return Fail(422, "invalid_candidate", "결과 후보를 확인할 수 없습니다.")
				}
				return err
			}
			if candidate["job_id"] != id || Number(candidate, "attempt_no") != n || candidate["kind"] != j["kind"] || candidate["schema_version"] != execution(j).Schema || candidate["validation_status"] != "valid" || candidate["content_hash"] != b["content_hash"] || Hash(candidate["body"]) != b["content_hash"] || !candidateContractMatches(j, candidate) {
				return Fail(422, "invalid_candidate", "후보의 attempt·스키마·검증·해시가 일치하지 않습니다.")
			}
			_, err = tx.Exec(ctx, "UPDATE jobs SET status='succeeded',stage='succeeded',published_result_id=$2,termination_reason=NULL,retryable=false,queue_reason=NULL,version=version+1 WHERE id=$1", id, b["candidate_id"])
			if err != nil {
				return err
			}
			result = Object{"job_id": id, "kind": j["kind"], "status": "succeeded", "version": Number(j, "version") + 1, "candidate_id": b["candidate_id"], "content_hash": b["content_hash"], "published_result_id": b["candidate_id"]}
			_, err = tx.Exec(ctx, "UPDATE job_attempts SET ended_at=$3,stage='succeeded',remote_call_state='terminated',completion_response=$4 WHERE job_id=$1 AND attempt_no=$2", id, n, now, result)
			if err != nil {
				return err
			}
			_, err = tx.Exec(ctx, "UPDATE slot_reservations SET state='released',released_at=$3 WHERE job_id=$1 AND attempt_no=$2 AND state='active'", id, n, now)
			if err != nil {
				return err
			}
		}
		return c.reasons(ctx, tx, now)
	})
	return result, e
}
func stale() *Problem { return Fail(409, "stale_attempt", "현재 유효한 attempt가 아닙니다.") }
