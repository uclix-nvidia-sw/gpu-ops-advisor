package api

import (
	"encoding/json"
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"net/http"
	"net/http/httptest"
	"strings"
)

func removed(path, method string) bool {
	return path == "/me" || strings.HasPrefix(path, "/conversations") || strings.HasPrefix(path, "/dispatches") || strings.HasPrefix(path, "/webhooks") || path == "/settings/access-grants" || path == "/settings/C07" || path == "/analyses" && method != "GET"
}
func (s *Server) dispatch(w http.ResponseWriter, q *Request, path string) error {
	mutation := q.R.Method != "GET" && !strings.HasSuffix(path, "/query")
	if !mutation {
		return s.route(w, q, path)
	}
	if e := key(q); e != nil {
		return e
	}
	// JC and Incident atomically own receipts for their commands. Do not precheck their versions.
	if path == "/reports" || strings.HasPrefix(path, "/jobs/") || strings.HasPrefix(path, "/incidents/") {
		return s.route(w, q, path)
	}
	operation := q.R.Method + ":" + path
	hash := Hash(q.Body)
	var response Object
	var status int
	e := s.DB.Transaction(q.R.Context(), func(tx pgx.Tx) error {
		ctx := store.WithTx(q.R.Context(), tx)
		clone := *q
		clone.R = q.R.WithContext(ctx)
		var previous string
		err := tx.QueryRow(ctx, "SELECT request_hash,status,response FROM backend_receipts WHERE operation=$1 AND key=$2", operation, q.R.Header.Get("Idempotency-Key")).Scan(&previous, &status, &response)
		if err == nil {
			if previous != hash {
				return Fail(409, "idempotency_conflict", "같은 키의 본문이 다릅니다.")
			}
			return nil
		}
		if err != pgx.ErrNoRows {
			return err
		}
		rec := httptest.NewRecorder()
		if err = s.route(rec, &clone, path); err != nil {
			return err
		}
		status = rec.Code
		if err = json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
			return err
		}
		_, err = tx.Exec(ctx, "INSERT INTO backend_receipts(operation,key,request_hash,status,response) VALUES($1,$2,$3,$4,$5)", operation, q.R.Header.Get("Idempotency-Key"), hash, status, response)
		return err
	})
	if e != nil {
		return e
	}
	s.write(w, q.ID, status, response)
	return nil
}
