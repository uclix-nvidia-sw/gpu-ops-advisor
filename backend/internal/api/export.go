package api

import (
	"encoding/csv"
	"encoding/json"
	. "gpu-ops-advisor/backend/internal/contract"
	"html/template"
	"net/http"
	"sort"
	"strings"
)

func (s *Server) exportReport(w http.ResponseWriter, q *Request, id string) error {
	if e := onlyQuery(q, "format"); e != nil {
		return e
	}
	format := q.R.URL.Query().Get("format")
	if !Has([]string{"html", "csv"}, format) {
		return Invalid("format")
	}
	job, e := s.resource(q, "reports", id, false)
	if e != nil {
		return e
	}
	dto, e := s.jobDTO(q, job, true)
	if e != nil {
		return e
	}
	body, ok := dto["result"].(map[string]any)
	if !ok {
		return Fail(409, "result_unpublished", "발행된 보고서 결과가 없습니다.")
	}
	w.Header().Set("Content-Disposition", "attachment; filename=report-"+String(job, "id")+"."+format)
	w.Header().Set("Content-Security-Policy", "sandbox; default-src 'none'")
	if format == "html" {
		data, _ := json.MarshalIndent(body, "", "  ")
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		page := template.Must(template.New("report").Parse(`<!doctype html><html lang="ko"><meta charset="utf-8"><title>저장 보고서</title><h1>저장 보고서</h1><p>{{.ID}}</p><pre>{{.Body}}</pre></html>`))
		return page.Execute(w, Object{"ID": id, "Body": string(data)})
	}
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	writer := csv.NewWriter(w)
	writer.UseCRLF = true
	if e = writer.Write([]string{"field", "value"}); e != nil {
		return e
	}
	keys := []string{}
	for k := range body {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		value, ok := body[k].(string)
		if !ok {
			b, _ := json.Marshal(body[k])
			value = string(b)
		}
		if e = writer.Write([]string{csvSafe(k), csvSafe(value)}); e != nil {
			return e
		}
	}
	writer.Flush()
	return writer.Error()
}
func csvSafe(v string) string {
	t := strings.TrimLeft(v, " \t\r\n")
	if len(t) > 0 && strings.ContainsAny(t[:1], "=+-@") || strings.HasPrefix(v, "\t") || strings.HasPrefix(v, "\r") {
		return "'" + v
	}
	return v
}
