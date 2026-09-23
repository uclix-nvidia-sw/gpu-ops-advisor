package controller

import (
	"context"
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/shared/contract"
	"slices"
	"strings"
	"time"
)

func (c *Controller) register(ctx context.Context, b Object) (Object, error) {
	if e := only(b, "worker_id", "boot_id", "kind", "capacity_profile_id", "supported_contract_versions"); e != nil {
		return nil, e
	}
	id, boot, kind := String(b, "worker_id"), String(b, "boot_id"), String(b, "kind")
	profile, ok := c.Config.Workers[String(b, "capacity_profile_id")]
	if id == "" || len(id) > 200 || strings.TrimSpace(id) != id || !uuid(boot) || !ok || profile.Kind != kind {
		return nil, Invalid("worker")
	}
	contracts := []string{"1.3"}
	if value, exists := b["supported_contract_versions"]; exists {
		var err error
		contracts, err = Decode[[]string](value)
		if err != nil || len(contracts) == 0 {
			return nil, Invalid("supported_contract_versions")
		}
		for _, version := range contracts {
			if !supportedContract(kind, version) {
				return nil, Invalid("supported_contract_versions")
			}
		}
		slices.Sort(contracts)
		contracts = slices.Compact(contracts)
	}
	e := c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		var retired bool
		var oldKind, oldProfile string
		var oldContracts []string
		err := tx.QueryRow(ctx, "SELECT retired,kind,profile_id,supported_contract_versions FROM workers WHERE worker_id=$1 AND boot_id=$2", id, boot).Scan(&retired, &oldKind, &oldProfile, &oldContracts)
		if err == nil && (retired || oldKind != kind || oldProfile != b["capacity_profile_id"] || !slices.Equal(oldContracts, contracts)) {
			return Fail(409, "worker_conflict", "이 boot 또는 프로필을 재사용할 수 없습니다.")
		}
		if err != nil && err != pgx.ErrNoRows {
			return err
		}
		_, err = tx.Exec(ctx, "UPDATE workers SET retired=true,draining=true WHERE worker_id=$1 AND boot_id<>$2 AND NOT retired", id, boot)
		if err != nil {
			return err
		}
		_, err = tx.Exec(ctx, "INSERT INTO workers(worker_id,boot_id,kind,profile_id,last_seen_at,supported_contract_versions) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(worker_id,boot_id) DO UPDATE SET last_seen_at=EXCLUDED.last_seen_at", id, boot, kind, b["capacity_profile_id"], now, contracts)
		if err != nil {
			return err
		}
		return c.reasons(ctx, tx, now)
	})
	return Object{"worker_id": id, "boot_id": boot, "kind": kind, "slots": profile.Slots, "config_revision": c.Revision, "supported_contract_versions": contracts}, e
}

type availability struct {
	used, quarantine int
	kind             map[string]int
	workers          map[string][]string
	present          map[string][]string
}

func (c *Controller) available(ctx context.Context, tx pgx.Tx, now time.Time) (availability, error) {
	a := availability{kind: map[string]int{}, workers: map[string][]string{}, present: map[string][]string{}}
	rows, e := tx.Query(ctx, "SELECT kind,state,count(*) FROM slot_reservations WHERE state<>'released' GROUP BY kind,state")
	if e != nil {
		return a, e
	}
	for rows.Next() {
		var kind, state string
		var n int
		if e = rows.Scan(&kind, &state, &n); e != nil {
			rows.Close()
			return a, e
		}
		a.used += n
		a.kind[kind] += n
		if state == "quarantined" {
			a.quarantine += n
		}
	}
	e = rows.Err()
	rows.Close()
	if e != nil {
		return a, e
	}
	rows, e = tx.Query(ctx, "SELECT w.kind,w.profile_id,w.supported_contract_versions,(SELECT count(*) FROM slot_reservations s WHERE s.worker_id=w.worker_id AND s.state<>'released') FROM workers w WHERE NOT retired AND NOT draining AND last_seen_at>$1", now.Add(-time.Duration(c.Config.FreshSeconds)*time.Second))
	if e != nil {
		return a, e
	}
	defer rows.Close()
	for rows.Next() {
		var kind, p string
		var used int
		var contracts []string
		if e = rows.Scan(&kind, &p, &contracts, &used); e != nil {
			return a, e
		}
		profile, ok := c.Config.Workers[p]
		if ok && profile.Kind == kind {
			a.present[kind] = append(a.present[kind], contracts...)
			if used < profile.Slots {
				a.workers[kind] = append(a.workers[kind], contracts...)
			}
		}
	}
	return a, rows.Err()
}
func (c *Controller) reasons(ctx context.Context, tx pgx.Tx, now time.Time) error {
	a, e := c.available(ctx, tx, now)
	if e != nil {
		return e
	}
	for _, kind := range []string{"rca", "report"} {
		var reason any
		if a.used >= c.Config.SharedLimit || a.kind[kind] >= c.Config.KindLimits[kind] {
			reason = "capacity_wait"
			if a.quarantine > 0 {
				reason = "inference_quarantined"
			}
		}
		_, e = tx.Exec(ctx, `UPDATE jobs j SET queue_reason=CASE
 WHEN EXISTS(SELECT 1 FROM slot_reservations s WHERE s.job_id=j.id AND s.state='quarantined') THEN 'inference_quarantined'
 WHEN NOT COALESCE(`+jobContractSQL+`=ANY($3::text[]),false) THEN 'worker_unavailable'
 WHEN $2::text IS NOT NULL THEN $2
 WHEN NOT COALESCE(`+jobContractSQL+`=ANY($4::text[]),false) THEN 'capacity_wait'
 ELSE NULL END WHERE kind=$1 AND source_module IS NOT NULL AND status IN ('queued','retry_wait')`, kind, reason, a.present[kind], a.workers[kind])
		if e != nil {
			return e
		}
	}
	return nil
}
func (c *Controller) claim(ctx context.Context, b Object) (Object, error) {
	if e := only(b, "worker_id", "boot_id", "kind"); e != nil {
		return nil, e
	}
	id, boot, kind := String(b, "worker_id"), String(b, "boot_id"), String(b, "kind")
	if id == "" || !uuid(boot) || !Has([]string{"rca", "report"}, kind) {
		return nil, Invalid("worker")
	}
	var result Object
	e := c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		w, err := one(ctx, tx, "SELECT to_jsonb(w) FROM workers w WHERE worker_id=$1 AND boot_id=$2 AND kind=$3 AND NOT retired AND NOT draining", id, boot, kind)
		if err != nil {
			if missing(err) {
				return Fail(409, "worker_unavailable", "유효한 Worker 등록이 필요합니다.")
			}
			return err
		}
		p, ok := c.Config.Workers[String(w, "profile_id")]
		if !ok || p.Kind != kind {
			return Fail(409, "worker_conflict", "프로필이 변경되었습니다.")
		}
		if _, err = tx.Exec(ctx, "UPDATE workers SET last_seen_at=$3 WHERE worker_id=$1 AND boot_id=$2", id, boot, now); err != nil {
			return err
		}
		var used int
		if err = tx.QueryRow(ctx, "SELECT count(*) FROM slot_reservations WHERE worker_id=$1 AND state<>'released'", id).Scan(&used); err != nil {
			return err
		}
		if used >= p.Slots {
			return c.reasons(ctx, tx, now)
		}
		a, err := c.available(ctx, tx, now)
		if err != nil {
			return err
		}
		if a.used >= c.Config.SharedLimit || a.kind[kind] >= c.Config.KindLimits[kind] {
			return c.reasons(ctx, tx, now)
		}
		other := "report"
		if kind == "report" {
			other = "rca"
		}
		var last *string
		if err = tx.QueryRow(ctx, "SELECT last_granted_kind FROM capacity_state WHERE pool_id='default'").Scan(&last); err != nil {
			return err
		}
		eligible := `source_module IS NOT NULL AND status IN ('queued','retry_wait') AND eligible_at<=$2 AND deadline_at>$2 AND attempt_no<max_attempts AND budget_used+COALESCE((versions->'execution'->>'attempt_budget')::bigint,token_budget+1)<=token_budget AND NOT EXISTS(SELECT 1 FROM slot_reservations s WHERE s.job_id=j.id AND s.state<>'released')`
		if last != nil && *last == kind && len(a.workers[other]) > 0 && a.kind[other] < c.Config.KindLimits[other] {
			var waiting bool
			if err = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM jobs j WHERE kind=$1 AND "+eligible+" AND "+jobContractSQL+"=ANY($3::text[]))", other, now, a.workers[other]).Scan(&waiting); err != nil {
				return err
			}
			if waiting {
				return c.reasons(ctx, tx, now)
			}
		}
		contracts, err := Decode[[]string](w["supported_contract_versions"])
		if err != nil {
			return err
		}
		job, err := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE kind=$1 AND "+eligible+" AND "+jobContractSQL+"=ANY($3::text[]) ORDER BY eligible_at,created_at,id LIMIT 1 FOR UPDATE", kind, now, contracts)
		if err != nil {
			if p, ok := err.(*Problem); ok && p.Status == 404 {
				return c.reasons(ctx, tx, now)
			}
			return err
		}
		versions, _ := job["versions"].(map[string]any)
		version, err := inputContract(kind, versions)
		if err != nil {
			return err
		}
		versions["input_contract"] = version
		ex := execution(job)
		n := Number(job, "attempt_no") + 1
		token := ID() + ID()
		lease := now.Add(time.Duration(ex.LeaseSeconds) * time.Second)
		deadline := instant(job, "deadline_at")
		if lease.After(deadline) {
			lease = deadline
		}
		jid := String(job, "id")
		_, err = tx.Exec(ctx, "UPDATE jobs SET status='running',stage='claimed',attempt_no=$2,started_at=COALESCE(started_at,$3),queue_reason=NULL,termination_reason=NULL,retryable=false,budget_used=budget_used+$4,version=version+1 WHERE id=$1", jid, n, now, ex.AttemptBudget)
		if err != nil {
			return err
		}
		_, err = tx.Exec(ctx, "INSERT INTO job_attempts(job_id,attempt_no,worker_id,boot_id,claim_token,lease_expires_at,started_at,stage,remote_call_state,budget_reserved) VALUES($1,$2,$3,$4,$5,$6,$7,'claimed','not_started',$8)", jid, n, id, boot, token, lease, now, ex.AttemptBudget)
		if err != nil {
			return err
		}
		_, err = tx.Exec(ctx, "INSERT INTO slot_reservations(id,job_id,attempt_no,worker_id,boot_id,kind,state,reserved_at) VALUES($1,$2,$3,$4,$5,$6,'active',$7)", ID(), jid, n, id, boot, kind, now)
		if err != nil {
			return err
		}
		if _, err = tx.Exec(ctx, "UPDATE capacity_state SET last_granted_kind=$1 WHERE pool_id='default'", kind); err != nil {
			return err
		}
		result = Object{"job_id": jid, "kind": kind, "input": job["input_snapshot"], "attempt_no": n, "claim_token": token, "lease_expires_at": lease, "deadline_at": deadline, "versions": job["versions"], "budget": Object{"attempt_limit": ex.AttemptBudget, "total_limit": job["token_budget"], "reserved_total": Number(job, "budget_used") + ex.AttemptBudget}, "heartbeat_seconds": ex.HeartbeatSeconds}
		return c.reasons(ctx, tx, now)
	})
	return result, e
}
