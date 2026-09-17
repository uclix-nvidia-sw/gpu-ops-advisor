package contract

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

type Object = map[string]any
type ClusterScope struct {
	ClusterID  string   `json:"cluster_id"`
	Namespaces []string `json:"namespaces"`
}
type Scope struct {
	Clusters []ClusterScope `json:"clusters"`
}
type Problem struct {
	Status    int    `json:"-"`
	Code      string `json:"code"`
	Message   string `json:"message"`
	Details   Object `json:"details"`
	Retryable bool   `json:"retryable"`
}

func (p *Problem) Error() string { return p.Code }
func Fail(status int, code, message string) *Problem {
	return &Problem{Status: status, Code: strings.ToLower(code), Message: message, Retryable: status == 503 || status == 429, Details: Object{}}
}
func Invalid(field string) *Problem {
	return &Problem{Status: 422, Code: "invalid_input", Message: "입력 형식 또는 허용 값이 올바르지 않습니다.", Details: Object{"field": field}}
}
func ID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
}
func Hash(v any) string {
	b, _ := json.Marshal(v)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func String(m Object, k string) string { s, _ := m[k].(string); return s }
func Number(m Object, k string) int {
	switch n := m[k].(type) {
	case float64:
		return int(n)
	case int:
		return n
	case json.Number:
		v, _ := n.Int64()
		return int(v)
	}
	return 0
}
func Has(values []string, value string) bool {
	for _, v := range values {
		if v == value {
			return true
		}
	}
	return false
}
func Decode[T any](v any) (T, error) {
	var out T
	b, e := json.Marshal(v)
	if e == nil {
		e = json.Unmarshal(b, &out)
	}
	return out, e
}
func ParseScope(v any) (Scope, error) {
	raw, ok := v.(map[string]any)
	if !ok || len(raw) != 1 {
		return Scope{}, Invalid("scope")
	}
	s, e := Decode[Scope](raw)
	if e != nil || len(s.Clusters) == 0 || len(s.Clusters) > 100 {
		return s, Invalid("scope.clusters")
	}
	clusters, _ := raw["clusters"].([]any)
	if len(clusters) != len(s.Clusters) {
		return s, Invalid("scope.clusters")
	}
	seen := map[string]bool{}
	for i, c := range s.Clusters {
		r, ok := clusters[i].(map[string]any)
		if !ok || len(r) != 2 {
			return s, Invalid("scope.clusters")
		}
		if _, ok := r["namespaces"]; !ok {
			return s, Invalid("scope.namespaces")
		}
		if c.ClusterID == "" || seen[c.ClusterID] || len(c.ClusterID) > 200 || c.Namespaces != nil && len(c.Namespaces) == 0 {
			return s, Invalid("scope.clusters")
		}
		seen[c.ClusterID] = true
		nsSeen := map[string]bool{}
		for _, ns := range c.Namespaces {
			if strings.TrimSpace(ns) == "" || len(ns) > 253 || nsSeen[ns] {
				return s, Invalid("scope.namespaces")
			}
			nsSeen[ns] = true
		}
		sort.Strings(s.Clusters[i].Namespaces)
	}
	sort.Slice(s.Clusters, func(i, j int) bool { return s.Clusters[i].ClusterID < s.Clusters[j].ClusterID })
	return s, nil
}
func Contains(outer, inner Scope) bool {
	if len(inner.Clusters) == 0 {
		return false
	}
	for _, c := range inner.Clusters {
		found := false
		for _, a := range outer.Clusters {
			if a.ClusterID != c.ClusterID {
				continue
			}
			if a.Namespaces == nil {
				found = true
				break
			}
			if c.Namespaces == nil {
				continue
			}
			found = true
			for _, n := range c.Namespaces {
				if !Has(a.Namespaces, n) {
					found = false
					break
				}
			}
		}
		if !found {
			return false
		}
	}
	return true
}
func TimeRange(v any, max time.Duration) error {
	m, ok := v.(map[string]any)
	if !ok || len(m) != 2 {
		return Invalid("time_range")
	}
	a, e := time.Parse(time.RFC3339Nano, String(m, "start"))
	b, f := time.Parse(time.RFC3339Nano, String(m, "end"))
	if e != nil || f != nil || !a.Before(b) {
		return Fail(422, "INVALID_TIME_RANGE", "시작 시각은 종료 시각보다 빨라야 하며 UTC offset이 필요합니다.")
	}
	if max <= 0 {
		return Fail(503, "LIMITS_NOT_CONFIGURED", "조회 한도가 설정되지 않았습니다.")
	}
	if b.Sub(a) > max {
		return Fail(422, "TIME_RANGE_LIMIT", "허용된 최대 조회 기간을 초과했습니다.")
	}
	m["start"] = a.UTC().Format(time.RFC3339Nano)
	m["end"] = b.UTC().Format(time.RFC3339Nano)
	return nil
}
