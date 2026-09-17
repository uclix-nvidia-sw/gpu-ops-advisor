package contract

import (
	"testing"
	"time"
)

func TestScopeAndTimeBoundaries(t *testing.T) {
	outer := Scope{[]ClusterScope{{"cpc-1", []string{"dev"}}}}
	if Contains(outer, Scope{[]ClusterScope{{"cpc-1", nil}}}) || Contains(outer, Scope{[]ClusterScope{{"cpc-2", []string{"dev"}}}}) {
		t.Fatal("scope boundary crossed")
	}
	for _, raw := range []Object{{"cluster_ids": []string{"cpc-1"}}, {"clusters": []any{Object{"cluster_id": "cpc-1", "namespaces": []string{}}}}, {"clusters": []any{Object{"cluster_id": "cpc-1"}}}} {
		if _, e := ParseScope(raw); e == nil {
			t.Fatal("invalid scope accepted")
		}
	}
	if e := TimeRange(Object{"start": "2026-09-17T00:00:00", "end": "2026-09-18T00:00:00"}, 24*time.Hour); e == nil {
		t.Fatal("timezone-less date accepted")
	}
	if e := TimeRange(Object{"start": "2026-09-17T00:00:00+09:00", "end": "2026-09-18T00:00:00+09:00"}, 24*time.Hour); e != nil {
		t.Fatal(e)
	}
}
