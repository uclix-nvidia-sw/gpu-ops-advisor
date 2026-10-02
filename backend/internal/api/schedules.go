package api

import (
	"context"
	"errors"
	"github.com/jackc/pgx/v5"
	"gpu-ops-advisor/backend/internal/calendar"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"log/slog"
	"net/http"
	"strconv"
	"time"
)

const scheduleSelect = "SELECT to_jsonb(s) || (to_jsonb(r)-'schedule_id'-'revision') || jsonb_build_object('revision',s.current_revision) FROM schedules s JOIN schedule_revisions r ON r.schedule_id=s.id AND r.revision=s.current_revision WHERE s.id::text=$1"

// Read-only execution summary: do not expose claim tokens, snapshots or unpublished candidates.
const occurrenceExecution = `(SELECT jsonb_build_object(
 'id',j.id,'status',j.status,'attempt_no',j.attempt_no,'queue_reason',j.queue_reason,
 'termination_reason',j.termination_reason,'result_ref',j.published_result_id,
 'started_at',a.started_at,'ended_at',a.ended_at,'attempt_reason',a.termination_reason)
 FROM jobs j LEFT JOIN job_attempts a ON a.job_id=j.id AND a.attempt_no=j.attempt_no
 WHERE j.id=o.job_id AND j.kind='report')`

const scheduleList = `(SELECT s.*,r.frequency,r.local_time,r.timezone,r.weekday,r.day,r.period,r.report_spec,s.current_revision AS revision,
 (SELECT to_jsonb(o) || jsonb_build_object('execution',` + occurrenceExecution + `)
 FROM schedule_occurrences o WHERE o.schedule_id=s.id ORDER BY o.scheduled_for DESC,o.id DESC LIMIT 1) AS latest_occurrence,
 (s.enabled AND s.next_run_at<=clock_timestamp() AND NOT EXISTS
 (SELECT 1 FROM schedule_occurrences o WHERE o.schedule_id=s.id AND o.scheduled_for=s.next_run_at)) AS awaiting_occurrence
 FROM schedules s JOIN schedule_revisions r ON r.schedule_id=s.id AND r.revision=s.current_revision)`

func (s *Server) schedules(w http.ResponseWriter, q *Request, parts []string) error {
	ctx := q.R.Context()
	method := q.R.Method
	if method == "GET" {
		if len(parts) == 1 {
			if e := onlyQuery(q, "limit", "cursor", "sort", "enabled", "scope"); e != nil {
				return e
			}
			scope, e := s.listScope(q)
			if e != nil {
				return e
			}
			enabled := q.R.URL.Query().Get("enabled")
			if enabled != "" && enabled != "true" && enabled != "false" {
				return Invalid("enabled")
			}
			return s.page(w, q, scheduleList, "($1='' OR enabled=NULLIF($1,'')::boolean) AND dsx_scope_contains($2,report_spec->'scope')", []any{enabled, scope}, nil)
		}
		if len(parts) == 2 {
			v, e := store.One(ctx, s.DB.Pool, scheduleSelect, parts[1])
			if e != nil {
				return e
			}
			s.write(w, q.ID, 200, v)
			return nil
		}
		if len(parts) == 3 && parts[2] == "occurrences" {
			if _, e := store.One(ctx, s.DB.Pool, scheduleSelect, parts[1]); e != nil {
				return e
			}
			if e := onlyQuery(q, "limit", "cursor", "sort", "from", "to", "status"); e != nil {
				return e
			}
			v := q.R.URL.Query()
			status := v.Get("status")
			if status != "" && !Has([]string{"pending", "accepted", "missed", "failed"}, status) {
				return Invalid("status")
			}
			return s.page(w, q, "(SELECT o.*, "+occurrenceExecution+" AS execution FROM schedule_occurrences o)", "schedule_id::text=$1 AND ($2='' OR status=$2) AND ($3='' OR scheduled_for>=NULLIF($3,'')::timestamptz) AND ($4='' OR scheduled_for<NULLIF($4,'')::timestamptz)", []any{parts[1], status, v.Get("from"), v.Get("to")}, nil)
		}
	}
	creating := method == "POST" && len(parts) == 1
	if !creating && !(method == "PATCH" && len(parts) == 2) {
		return Fail(404, "not_found", "등록되지 않은 일정 API입니다.")
	}
	if e := only(q.Body, "frequency", "local_time", "timezone", "weekday", "day", "period", "enabled", "report_spec"); e != nil {
		return e
	}
	var result Object
	e := s.DB.Transaction(ctx, func(tx pgx.Tx) error {
		var now time.Time
		if e := tx.QueryRow(ctx, "SELECT clock_timestamp()").Scan(&now); e != nil {
			return e
		}
		id := ID()
		revision := 1
		merged := Object{"enabled": true}
		if !creating {
			id = parts[1]
			old, e := store.One(ctx, tx, scheduleSelect+" FOR UPDATE OF s", id)
			if e != nil {
				return e
			}
			if e = match(q, Number(old, "version")); e != nil {
				return e
			}
			if e = tx.QueryRow(ctx, "SELECT clock_timestamp()").Scan(&now); e != nil {
				return e
			}
			// Materialize old due instants before appending the new effective revision.
			if e = s.materialize(ctx, tx, old, now); e != nil {
				return e
			}
			old, e = store.One(ctx, tx, scheduleSelect, id)
			if e != nil {
				return e
			}
			next, _ := time.Parse(time.RFC3339Nano, String(old, "next_run_at"))
			if !next.After(now) {
				return Fail(409, "catchup_in_progress", "이전 예정분 복구 후 다시 변경해 주세요.")
			}
			for _, k := range []string{"frequency", "local_time", "timezone", "weekday", "day", "period", "enabled", "report_spec"} {
				merged[k] = old[k]
			}
			revision = Number(old, "current_revision") + 1
		}
		for k, v := range q.Body {
			merged[k] = v
		}
		if _, changed := q.Body["frequency"]; changed {
			if String(merged, "frequency") != "weekly" && q.Body["weekday"] == nil {
				merged["weekday"] = 0
			}
			if String(merged, "frequency") != "monthly" && q.Body["day"] == nil {
				merged["day"] = 0
			}
		}
		spec, e := Decode[calendar.Spec](merged)
		if e != nil {
			return Invalid("calendar")
		}
		if e = spec.Validate(); e != nil {
			return Invalid(e.Error())
		}
		enabled, ok := merged["enabled"].(bool)
		if !ok {
			return Invalid("enabled")
		}
		report, ok := merged["report_spec"].(map[string]any)
		if !ok {
			return Invalid("report_spec")
		}
		if report["time_range"] != nil || report["timezone"] != nil || report["parent_job_id"] != nil {
			return Invalid("report_spec.fixed_period")
		}
		clone := *q
		clone.Body = Object{}
		for k, v := range report {
			clone.Body[k] = v
		}
		clone.Body["timezone"] = spec.Timezone
		clone.Body["time_range"] = Object{"start": now.Add(-24 * time.Hour).Format(time.RFC3339), "end": now.Format(time.RFC3339)}
		if e = s.validateWork(&clone, "reports"); e != nil {
			return e
		}
		report["scope"] = clone.Body["scope"]
		next := spec.Next(now)
		if creating {
			_, e = tx.Exec(ctx, "INSERT INTO schedules(id,enabled,current_revision,effective_at,next_run_at) VALUES($1,$2,$3,$4,$5)", id, enabled, revision, now, next)
		} else {
			_, e = tx.Exec(ctx, "UPDATE schedules SET enabled=$2,current_revision=$3,effective_at=$4,next_run_at=$5,version=version+1 WHERE id::text=$1", id, enabled, revision, now, next)
		}
		if e != nil {
			return e
		}
		_, e = tx.Exec(ctx, "INSERT INTO schedule_revisions(schedule_id,revision,frequency,local_time,timezone,weekday,day,period,report_spec,enabled,effective_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)", id, revision, spec.Frequency, spec.LocalTime, spec.Timezone, spec.Weekday, spec.Day, spec.Period, report, enabled, now)
		if e != nil {
			return e
		}
		result, e = store.One(ctx, tx, scheduleSelect, id)
		if e != nil {
			return e
		}
		return store.Audit(ctx, tx, "unverified", method, "schedules", id, q.ID, nil, result)
	})
	if e != nil {
		return e
	}
	status := 200
	if creating {
		status = 201
	}
	s.write(w, q.ID, status, result)
	return nil
}

// materialize holds the schedule row lock. Occurrence and outbox commits are indivisible.
func (s *Server) materialize(ctx context.Context, tx pgx.Tx, schedule Object, now time.Time) error {
	spec, e := Decode[calendar.Spec](schedule)
	if e != nil {
		return e
	}
	if e = spec.Validate(); e != nil {
		return e
	}
	due, e := time.Parse(time.RFC3339Nano, String(schedule, "next_run_at"))
	if e != nil {
		return e
	}
	if schedule["enabled"] != true {
		_, e = tx.Exec(ctx, "UPDATE schedules SET next_run_at=$2 WHERE id::text=$1", schedule["id"], spec.Next(now))
		return e
	}
	dates := []time.Time{}
	next := due
	for len(dates) < 512 && !next.After(now) {
		dates = append(dates, next)
		next = spec.Next(next)
	}
	for i, due := range dates {
		start, end := spec.Window(due)
		id := ID()
		status := "pending"
		reason := ""
		canonical := true
		var existing *string
		if due.Before(now.Add(-s.Config.CatchupWindow)) {
			status = "missed"
			reason = "outside_catchup_window"
		} else if !next.After(now) || len(dates)-i > s.Config.MaxCatchup {
			status = "missed"
			reason = "max_catchup_exceeded"
		}
		var other string
		e = tx.QueryRow(ctx, "SELECT id::text FROM schedule_occurrences WHERE schedule_id::text=$1 AND period_start=$2 AND period_end=$3 AND canonical", schedule["id"], start, end).Scan(&other)
		if e == nil {
			canonical = false
			existing = &other
			status = "missed"
			reason = "already_reserved_period"
		} else if e != pgx.ErrNoRows {
			return e
		}
		var outbox *string
		if status == "pending" {
			report, _ := Decode[Object](schedule["report_spec"])
			report["time_range"] = Object{"start": start.Format(time.RFC3339Nano), "end": end.Format(time.RFC3339Nano)}
			report["timezone"] = spec.Timezone
			source := "schedule:" + id
			envelope := s.envelope(report, source, now)
			envelope["dispatch_deadline"] = now.Add(s.Config.DispatchWindow).UTC().Format(time.RFC3339Nano)
			envelope["snapshot_ref"] = Object{"schedule_id": schedule["id"], "revision": schedule["current_revision"], "occurrence_id": id}
			oid := ID()
			outbox = &oid
			_, e = tx.Exec(ctx, "INSERT INTO enqueue_outbox(id,source_module,source_key,kind,input_snapshot,request_hash,status,dispatch_deadline) VALUES($1,'backend',$2,'report',$3,$4,'pending',$5)", oid, source, envelope, Hash(envelope), now.Add(s.Config.DispatchWindow))
			if e != nil {
				return e
			}
		}
		_, e = tx.Exec(ctx, "INSERT INTO schedule_occurrences(id,schedule_id,revision,scheduled_for,period_start,period_end,canonical,status,reason,outbox_id,canonical_occurrence_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,NULLIF($9,''),$10,$11)", id, schedule["id"], Number(schedule, "current_revision"), due, start, end, canonical, status, reason, outbox, existing)
		if e != nil {
			return e
		}
	}
	_, e = tx.Exec(ctx, "UPDATE schedules SET next_run_at=$2 WHERE id::text=$1", schedule["id"], next)
	return e
}
func (s *Server) RunScheduler(ctx context.Context) {
	if !s.Config.SchedulerEnabled {
		return
	}
	// Occurrence calculation and pending delivery run independently, even if JC times out.
	go s.loop(ctx, s.GenerateOccurrences)
	go s.loop(ctx, s.DeliverPending)
}
func (s *Server) loop(ctx context.Context, fn func(context.Context) error) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		if e := fn(ctx); e != nil && ctx.Err() == nil {
			slog.Error("scheduler iteration", "error", e)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
func (s *Server) GenerateOccurrences(ctx context.Context) error {
	for n := 0; n < 32; n++ {
		tx, e := s.DB.Pool.Begin(ctx)
		if e != nil {
			return e
		}
		var id string
		var now time.Time
		e = tx.QueryRow(ctx, "SELECT id::text,clock_timestamp() FROM schedules WHERE enabled AND next_run_at<=clock_timestamp() ORDER BY next_run_at,id FOR UPDATE SKIP LOCKED LIMIT 1").Scan(&id, &now)
		if e == pgx.ErrNoRows {
			tx.Rollback(ctx)
			return nil
		}
		if e != nil {
			tx.Rollback(ctx)
			return e
		}
		v, e := store.One(ctx, tx, scheduleSelect, id)
		if e == nil {
			e = s.materialize(ctx, tx, v, now)
		}
		if e == nil {
			e = tx.Commit(ctx)
		} else {
			tx.Rollback(ctx)
		}
		if e != nil {
			return e
		}
	}
	return nil
}
func (s *Server) DeliverPending(ctx context.Context) error {
	for n := 0; n < 16; n++ {
		tx, e := s.DB.Pool.Begin(ctx)
		if e != nil {
			return e
		}
		out, e := store.One(ctx, tx, "SELECT to_jsonb(o) FROM enqueue_outbox o WHERE source_module='backend' AND source_key LIKE 'schedule:%' AND status='pending' AND next_retry_at<=clock_timestamp() ORDER BY next_retry_at,id FOR UPDATE SKIP LOCKED LIMIT 1")
		if p, ok := e.(*Problem); ok && p.Status == 404 {
			tx.Rollback(ctx)
			return nil
		}
		if e != nil {
			tx.Rollback(ctx)
			return e
		}
		var now time.Time
		e = tx.QueryRow(ctx, "SELECT clock_timestamp()").Scan(&now)
		if e != nil {
			tx.Rollback(ctx)
			return e
		}
		envelope, _ := out["input_snapshot"].(map[string]any)
		deadline, _ := time.Parse(time.RFC3339Nano, String(out, "dispatch_deadline"))
		var receipt Object
		status := 0
		var callErr error
		expired := !now.Before(deadline)
		if expired {
			receipt, status, callErr = s.receipt(ctx, String(out, "source_key"))
		} else {
			receipt, status, callErr = s.internal(ctx, "job_controller", "POST", "/jobs/report", envelope, nil)
		}
		state := "pending"
		reason := ""
		var job any
		if callErr == nil && (status == 202 || expired && status == 200) && String(receipt, "job_id") != "" && String(receipt, "kind") == "report" {
			state = "accepted"
			job = receipt["job_id"]
		} else {
			var p *Problem
			if errors.As(callErr, &p) {
				reason = p.Code
				if expired && p.Status == 404 {
					state = "failed"
					reason = "dispatch_deadline_exceeded"
				} else if !expired && (p.Status == 422 || p.Status == 409) {
					// Even a permanent rejection is reconciled with the durable receipt before terminal failure.
					recovered, _, re := s.receipt(ctx, String(out, "source_key"))
					if re == nil && String(recovered, "job_id") != "" && String(recovered, "kind") == "report" {
						state = "accepted"
						job = recovered["job_id"]
					} else if errors.As(re, &p) && p.Status == 404 {
						state = "failed"
					}
				}
			} else {
				reason = "invalid_receipt"
			}
		}
		attempts := Number(out, "attempts") + 1
		seconds := 5 * (1 << min(attempts, 6))
		if seconds > 300 {
			seconds = 300
		}
		_, e = tx.Exec(ctx, "UPDATE enqueue_outbox SET status=$2,job_id=$3,attempts=$4,next_retry_at=clock_timestamp()+$5::interval,last_error=NULLIF($6,'') WHERE id::text=$1", out["id"], state, job, attempts, strconv.Itoa(seconds)+" seconds", reason)
		if e == nil {
			_, e = tx.Exec(ctx, "UPDATE schedule_occurrences SET status=$2,job_id=$3,reason=NULLIF($4,'') WHERE outbox_id::text=$1", out["id"], state, job, reason)
		}
		if e == nil {
			e = tx.Commit(ctx)
		} else {
			tx.Rollback(ctx)
		}
		if e != nil {
			return e
		}
	}
	return nil
}
