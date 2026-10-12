package controller

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	. "gpu-ops-advisor/shared/contract"
)

func (c *Controller) deleteReport(ctx context.Context, tx pgx.Tx, job Object, now time.Time, reason string) (err error) {
	defer func() {
		var pgError *pgconn.PgError
		if errors.Is(err, context.DeadlineExceeded) || errors.As(err, &pgError) && (pgError.Code == "55P03" || pgError.Code == "57014") {
			err = Fail(409, "report_busy", "관련 자료를 사용 중이거나 참조 확인 시간이 길어 삭제하지 않았습니다. 잠시 후 다시 시도해 주세요.")
		}
	}()
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if job["kind"] != "report" || job["source_module"] != "backend" {
		return Fail(409, "kind_not_allowed", "운영 분석 보고서만 삭제할 수 있습니다.")
	}
	if !terminal(String(job, "status")) {
		return Fail(409, "invalid_state", "실행이 끝난 보고서만 삭제할 수 있습니다.")
	}
	id := String(job, "id")
	var active bool
	if err := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM slot_reservations WHERE job_id=$1 AND state<>'released')
 OR EXISTS(SELECT 1 FROM job_attempts WHERE job_id=$1 AND ended_at IS NULL)`, id).Scan(&active); err != nil {
		return err
	}
	if active {
		return Fail(409, "report_in_use", "실행 또는 정리 중인 보고서는 삭제할 수 없습니다.")
	}
	// Bound deletion work so a large reference check cannot hold the queue lock indefinitely.
	if _, err := tx.Exec(ctx, "SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='2s'"); err != nil {
		return err
	}
	if err := checkReportReferences(ctx, tx, id); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO report_deletions(job_id,deleted_at,reason,published_result_id,content_hash,evidence_count,candidate_count)
 SELECT j.id,$2,$3,j.published_result_id,c.content_hash,
 (SELECT count(*) FROM evidence WHERE job_id=j.id),(SELECT count(*) FROM result_candidates WHERE job_id=j.id)
 FROM jobs j LEFT JOIN result_candidates c ON c.id=j.published_result_id AND c.job_id=j.id WHERE j.id=$1`, id, now, reason); err != nil {
		return err
	}
	// Preserve the immutable-candidate trigger: only this audited command clears publication first.
	if _, err := tx.Exec(ctx, "UPDATE jobs SET published_result_id=NULL,retryable=false,version=version+1 WHERE id=$1", id); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, "DELETE FROM result_candidates WHERE job_id=$1", id); err != nil {
		return err
	}
	_, err = tx.Exec(ctx, "DELETE FROM evidence WHERE job_id=$1", id)
	return err
}

func checkReportReferences(ctx context.Context, tx pgx.Tx, id string) error {
	// Reference-producing transactions lock evidence FOR KEY SHARE before their writes.
	// Acquire our locks first, then use a fresh READ COMMITTED statement for the scan.
	rows, err := tx.Query(ctx, "SELECT id FROM evidence WHERE job_id=$1 ORDER BY id FOR UPDATE", id)
	if err != nil {
		return err
	}
	for rows.Next() {
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	var owned bool
	if err = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM evidence WHERE job_id=$1) OR EXISTS(SELECT 1 FROM result_candidates WHERE job_id=$1)", id).Scan(&owned); err != nil || !owned {
		return err
	}
	var referenced bool
	err = tx.QueryRow(ctx, `WITH owned AS (
 SELECT id::text AS id FROM evidence WHERE job_id=$1 UNION ALL SELECT id::text FROM result_candidates WHERE job_id=$1
), ids AS (SELECT COALESCE(jsonb_agg(id),'[]'::jsonb) AS refs FROM owned)
SELECT EXISTS(SELECT 1 FROM identity_history h JOIN evidence e ON e.id=h.evidence_id WHERE e.job_id=$1)
 OR EXISTS(SELECT 1 FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id WHERE c.job_id=$1 AND j.id<>$1)
 OR EXISTS(SELECT 1 FROM result_candidates c,ids WHERE c.job_id<>$1 AND jsonb_path_exists(c.body->'evidence_refs','$[*] ? (@ == $refs[*])',jsonb_build_object('refs',ids.refs)))
 OR EXISTS(SELECT 1 FROM collection_observations c,ids WHERE jsonb_path_exists(c.evidence_refs,'strict $.** ? (@ == $refs[*])',jsonb_build_object('refs',ids.refs)))
 OR EXISTS(SELECT 1 FROM allocation_observations a,ids WHERE jsonb_path_exists(a.evidence_refs,'strict $.** ? (@ == $refs[*])',jsonb_build_object('refs',ids.refs)))
 OR EXISTS(SELECT 1 FROM knowledge_revisions k,ids WHERE jsonb_path_exists(k.source_refs,'$[*] ? (@ == $refs[*])',jsonb_build_object('refs',ids.refs)))
 OR EXISTS(SELECT 1 FROM review_records r,ids WHERE jsonb_path_exists(r.body->'evidence_refs','$[*] ? (@ == $refs[*])',jsonb_build_object('refs',ids.refs)))
 OR EXISTS(SELECT 1 FROM audit_events a,ids WHERE a.resource_id IS DISTINCT FROM $1::uuid AND jsonb_path_exists(a.after_ref#>'{command,evidence_refs}','$[*] ? (@ == $refs[*])',jsonb_build_object('refs',ids.refs)))
`, id).Scan(&referenced)
	if err != nil {
		return err
	}
	if referenced {
		return Fail(409, "report_referenced", "다른 분석이나 운영 기록에서 사용하는 근거가 있어 삭제할 수 없습니다.")
	}
	return nil
}
