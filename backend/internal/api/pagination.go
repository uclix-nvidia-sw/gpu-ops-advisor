package api

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	. "gpu-ops-advisor/backend/internal/contract"
	"net/http"
	"strconv"
	"time"
)

// The table and predicate are code-owned; only bound values come from clients.
func (s *Server) page(w http.ResponseWriter, q *Request, table, predicate string, args []any, transform func(Object) Object) error {
	if e := validateList(q); e != nil {
		return e
	}
	values := q.R.URL.Query()
	values.Del("cursor")
	values.Del("limit")
	filter := Hash(Object{"path": q.R.URL.Path, "filters": values.Encode()})
	if raw := q.R.URL.Query().Get("cursor"); raw != "" {
		data, e := base64.RawURLEncoding.DecodeString(raw)
		var c cursor
		if e != nil || json.Unmarshal(data, &c) != nil || c.Filter != filter {
			return Invalid("cursor")
		}
		if _, e = time.Parse(time.RFC3339Nano, c.At); e != nil || c.ID == "" {
			return Invalid("cursor")
		}
		args = append(args, c.At, c.ID)
		predicate += fmt.Sprintf(" AND (created_at,id::text)<($%d::timestamptz,$%d)", len(args)-1, len(args))
	}
	limit := 50
	if raw := q.R.URL.Query().Get("limit"); raw != "" {
		limit, _ = strconv.Atoi(raw)
	}
	args = append(args, limit+1)
	rows, e := s.DB.Pool.Query(q.R.Context(), "SELECT to_jsonb(t) FROM "+table+" t WHERE "+predicate+fmt.Sprintf(" ORDER BY created_at DESC,id DESC LIMIT $%d", len(args)), args...)
	if e != nil {
		return e
	}
	defer rows.Close()
	items := []Object{}
	for rows.Next() {
		var data []byte
		if e = rows.Scan(&data); e != nil {
			return e
		}
		var v Object
		if e = json.Unmarshal(data, &v); e != nil {
			return e
		}
		items = append(items, v)
	}
	if e = rows.Err(); e != nil {
		return e
	}
	var next any
	if len(items) > limit {
		last := items[limit-1]
		data, _ := json.Marshal(cursor{At: String(last, "created_at"), ID: String(last, "id"), Filter: filter})
		next = base64.RawURLEncoding.EncodeToString(data)
		items = items[:limit]
	}
	if transform != nil {
		for i, v := range items {
			items[i] = transform(v)
		}
	}
	s.write(w, q.ID, 200, Object{"items": items, "next_cursor": next})
	return nil
}
