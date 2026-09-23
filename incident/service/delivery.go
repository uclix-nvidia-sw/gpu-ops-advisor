package service

import (
	"bytes"
	"context"
	"encoding/json"
	. "gpu-ops-advisor/shared/contract"
	"io"
	"log/slog"
	"math/rand/v2"
	"net/http"
	"net/url"
	"strings"
	"time"
)

func (s *Server) request(ctx context.Context, method, path string, body Object) (Object, int, error) {
	raw, e := json.Marshal(body)
	if e != nil {
		return nil, 0, e
	}
	ctx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	req, e := http.NewRequestWithContext(ctx, method, strings.TrimRight(s.Config.JCURL, "/")+"/internal/v1"+path, bytes.NewReader(raw))
	if e != nil {
		return nil, 0, e
	}
	req.Header.Set("Content-Type", "application/json")
	version := String(body, "contract_version")
	if version == "" {
		version = "1.3" // Receipt lookup retains the existing internal API contract.
	}
	req.Header.Set("X-DSX-Contract-Version", version)
	resp, e := s.Client.Do(req)
	if e != nil {
		return nil, 0, e
	}
	defer resp.Body.Close()
	data, e := io.ReadAll(io.LimitReader(resp.Body, 1024*1024+1))
	if e != nil || len(data) > 1024*1024 {
		return nil, resp.StatusCode, Fail(503, "invalid_dependency_response", "JC 응답 한도를 초과했습니다.")
	}
	var out Object
	if json.Unmarshal(data, &out) != nil || out == nil {
		return nil, resp.StatusCode, Fail(503, "invalid_dependency_response", "JC 응답을 확인할 수 없습니다.")
	}
	return out, resp.StatusCode, nil
}
func accepted(v Object, status int, e error) bool {
	return e == nil && (status == 200 || status == 202) && v["kind"] == "rca" && uuid(String(v, "job_id"))
}
func (s *Server) DeliverPending(ctx context.Context) error {
	if e := s.configuration(ctx, s.DB); e != nil {
		return e
	}
	for range 16 {
		tx, e := s.DB.Begin(ctx)
		if e != nil {
			return e
		}
		done, e := func() (bool, error) {
			defer tx.Rollback(ctx)
			out, e := one(ctx, tx, "SELECT to_jsonb(o) FROM enqueue_outbox o WHERE source_module='incident' AND status='pending' AND next_retry_at<=clock_timestamp() ORDER BY next_retry_at,id FOR UPDATE SKIP LOCKED LIMIT 1")
			if missing(e) {
				return true, nil
			}
			if e != nil {
				return false, e
			}
			var now time.Time
			if e = tx.QueryRow(ctx, "SELECT clock_timestamp()").Scan(&now); e != nil {
				return false, e
			}
			expired := !instant(out, "dispatch_deadline").After(now)
			source := String(out, "source_key")
			envelope, _ := out["input_snapshot"].(map[string]any)
			var receipt Object
			var status int
			var callErr error
			if expired {
				receipt, status, callErr = s.request(ctx, "GET", "/receipts/incident/"+url.PathEscape(source), nil)
			} else {
				receipt, status, callErr = s.request(ctx, "POST", "/jobs/rca", envelope)
			}
			state, reason := "pending", "dependency_unavailable"
			var job any
			if accepted(receipt, status, callErr) {
				state, reason = "accepted", ""
				job = receipt["job_id"]
			} else if callErr == nil {
				if expired && status == 404 {
					state, reason = "failed", "dispatch_deadline_exceeded"
				} else if !expired && (status == 409 || status == 422) {
					recovered, code, re := s.request(ctx, "GET", "/receipts/incident/"+url.PathEscape(source), nil)
					if accepted(recovered, code, re) {
						state, reason = "accepted", ""
						job = recovered["job_id"]
					} else if re == nil && code == 404 {
						state, reason = "failed", "rejected_by_job_controller"
						if errObj, ok := receipt["error"].(map[string]any); ok && String(errObj, "code") != "" {
							reason = String(errObj, "code")
						}
					}
				}
			}
			attempts := Number(out, "attempts") + 1
			backoff := min(300, 5*(1<<min(attempts, 6)))
			next := now.Add(time.Duration(backoff)*time.Second + time.Duration(rand.Int64N(int64(time.Second))))
			_, e = tx.Exec(ctx, "UPDATE enqueue_outbox SET status=$2,job_id=$3,attempts=$4,next_retry_at=$5,last_error=NULLIF($6,'') WHERE id=$1", out["id"], state, job, attempts, next, reason)
			if e != nil {
				return false, e
			}
			return false, tx.Commit(ctx)
		}()
		if e != nil {
			return e
		}
		if done {
			return nil
		}
	}
	return nil
}
func (s *Server) Run(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		if e := s.DeliverPending(ctx); e != nil && ctx.Err() == nil {
			slog.Error("incident outbox delivery", "error", e)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
