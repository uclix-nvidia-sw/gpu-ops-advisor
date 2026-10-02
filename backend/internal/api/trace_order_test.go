package api

import (
	"encoding/json"
	"reflect"
	"testing"

	. "gpu-ops-advisor/backend/internal/contract"
)

func TestEvidenceOrder(t *testing.T) {
	for _, tc := range []struct {
		name, input string
		want        []string
	}{
		{"time then plan, unplanned slot preserved", `[
		 {"id":"b","query_id":"D02","quality":{"recorded_at":"2026-10-02T04:00:00.000002Z","record_sequence":1,"round":0,"plan_order":1}},
		 {"id":"decision","query_id":"unexpected_evidence","quality":{"recorded_at":"2026-10-02T04:00:00.000002Z","record_sequence":2}},
		 {"id":"a","query_id":"D09","quality":{"recorded_at":"2026-10-02T04:00:00.000002Z","record_sequence":3,"round":0,"plan_order":0}},
		 {"id":"early","query_id":"D02","quality":{"recorded_at":"2026-10-02T04:00:00.000001Z","record_sequence":0,"round":0,"plan_order":9}}
		]`, []string{"early", "a", "decision", "b"}},
		{"legacy plan and derived source", `[
		 {"id":"z","query_id":"incident_snapshot"},
		 {"id":"done","query_id":"sufficiency","_round":0},
		 {"id":"derived","query_id":"D05","quality":{"round":0,"sub_agent_id":"o0","derived_from":"source"}},
		 {"id":"source","query_id":"D09","quality":{"round":0,"sub_agent_id":"o0"}},
		 {"id":"plan","query_id":"observation_plan","_round":0,"_assignments":[{"query_id":"D09","sub_agent_id":"o0"}]},
		 {"id":"unknown","query_id":"custom"}
		]`, []string{"z", "plan", "source", "derived", "done", "unknown"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var items []Object
			if err := json.Unmarshal([]byte(tc.input), &items); err != nil {
				t.Fatal(err)
			}
			for _, v := range items {
				v["created_at"] = "2026-10-02T05:00:00Z"
			}
			orderEvidence(items)
			got := []string{}
			for _, v := range items {
				got = append(got, String(v, "id"))
				if _, ok := v["_assignments"]; ok {
					t.Fatal("internal plan leaked")
				}
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("got %v want %v", got, tc.want)
			}
		})
	}
}
