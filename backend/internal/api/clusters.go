package api

import (
	"net/http"
	"strings"
	"unicode"

	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/backend/internal/contract"
)

func (s *Server) registerCluster(w http.ResponseWriter, q *Request) error {
	if e := only(q.Body, "cluster_id"); e != nil {
		return e
	}
	id := String(q.Body, "cluster_id")
	if id == "" || len(id) > 200 || strings.TrimSpace(id) != id || strings.ContainsFunc(id, unicode.IsControl) {
		return Invalid("cluster_id")
	}
	result := Object{"id": id, "cluster_id": id, "namespaces": nil, "collection_status": "unknown"}
	e := s.DB.Transaction(q.R.Context(), func(tx pgx.Tx) error {
		tag, e := tx.Exec(q.R.Context(), "INSERT INTO cluster_registry(id) VALUES($1) ON CONFLICT DO NOTHING", id)
		if e != nil {
			return e
		}
		if tag.RowsAffected() == 0 {
			return Fail(409, "CLUSTER_ALREADY_REGISTERED", "이미 등록된 클러스터 ID입니다.")
		}
		// Cluster IDs are text, unlike the UUID resource_id column; keep the
		// complete identity in the audit snapshot. The receipt owns this transaction.
		_, e = tx.Exec(q.R.Context(), "INSERT INTO audit_events(id,actor,action,resource_type,request_id,after_ref) VALUES($1,'unverified','register','cluster_registry',$2,$3)", ID(), q.ID, result)
		return e
	})
	if e != nil {
		return e
	}
	s.write(w, q.ID, http.StatusCreated, result)
	return nil
}
