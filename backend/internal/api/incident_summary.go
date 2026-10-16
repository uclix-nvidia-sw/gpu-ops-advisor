package api

import (
	"encoding/json"
	. "gpu-ops-advisor/backend/internal/contract"
)

// Enrich only the selected page; candidate bodies never leave PostgreSQL here.
func (s *Server) incidentSummaries(q *Request, items []Object) error {
	if len(items) == 0 {
		return nil
	}
	ids := make([]string, len(items))
	for i, item := range items {
		ids[i] = String(item, "id")
	}
	records, err := s.DB.Pool.Query(q.R.Context(), `
SELECT i.id::text, jsonb_build_object('latest_job', (
 SELECT jsonb_build_object('job_id',j.id,'status',j.status,'created_at',j.created_at,
  'queue_reason',j.queue_reason,'termination_reason',j.termination_reason)
 FROM jobs j WHERE j.incident_id=i.id AND j.kind='rca' AND dsx_scope_contains(i.scope,j.scope)
 ORDER BY j.created_at DESC,j.id DESC LIMIT 1
), 'latest_published', (
 SELECT jsonb_build_object('job_id',j.id,'result_ref',c.id,'created_at',j.created_at,
  'result_status',c.body->'result_status','narrative_status',c.body->'narrative_status')
 FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id AND c.job_id=j.id AND c.kind=j.kind
 WHERE j.incident_id=i.id AND j.kind='rca' AND dsx_scope_contains(i.scope,j.scope)
 ORDER BY j.created_at DESC,j.id DESC LIMIT 1
)) FROM incidents i WHERE i.id=ANY($1::uuid[])`, ids)
	if err != nil {
		return err
	}
	defer records.Close()
	summaries := make(map[string]Object, len(items))
	for records.Next() {
		var id string
		var data []byte
		if err = records.Scan(&id, &data); err != nil {
			return err
		}
		var summary Object
		if err = json.Unmarshal(data, &summary); err != nil {
			return err
		}
		summaries[id] = summary
	}
	if err = records.Err(); err != nil {
		return err
	}
	for _, item := range items {
		item["rca_summary"] = summaries[String(item, "id")]
	}
	return nil
}
