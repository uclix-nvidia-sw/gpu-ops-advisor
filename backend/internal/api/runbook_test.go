package api

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	. "gpu-ops-advisor/backend/internal/contract"
)

func TestRunbookAuthoringAndPublication(t *testing.T) {
	files, err := filepath.Glob("../../../rcca-agent/runbooks/*/RB-*.json")
	files = append(files, "../../../rcca-agent/runbooks/RB-GENERAL-GPU-NODE.json")
	if err != nil || len(files) != 267 {
		t.Fatalf("missing shipped runbooks: %v", err)
	}
	for _, path := range files {
		t.Run(filepath.Base(path), func(t *testing.T) {
			b, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var row Object
			if err := json.Unmarshal(b, &row); err != nil {
				t.Fatal(err)
			}
			if err := validateRunbook(row["content"], row["compatibility"], false); err != nil {
				t.Fatal(err)
			}
			if validateRunbook(row["content"], row["compatibility"], true) == nil {
				t.Fatal("unbound publication accepted")
			}
			if err := validateRunbook(row["content"], Object{"cluster_id": "isolated-fixture"}, true); err != nil {
				t.Fatal(err)
			}
			for _, edit := range []func(Object){
				func(c Object) { c["schema"] = "unknown" },
				func(c Object) { c["investigation_only"] = "true" },
				func(c Object) { c["required_evidence"] = []any{"unknown"} },
				func(c Object) { c["unexpected"] = true },
				func(c Object) {
					c["unexpected_evidence"] = Object{"on": []any{"invented"}, "additional_queries": []any{}, "fallback": "stop"}
				},
				func(c Object) {
					c["unexpected_evidence"] = Object{"on": []any{"unknown_value"}, "additional_queries": []any{}, "fallback": "execute"}
				},
				func(c Object) { c["sources"] = nil },
				func(c Object) { c["observation_plan"] = nil },
				func(c Object) { c["required_queries"] = []any{"D99"} },
				func(c Object) {
					c["recommendations"] = []any{Object{"text": "reset", "execution": "performed", "preconditions": []any{Object{"field": "error_code", "equals": "xid:79"}}}}
				},
			} {
				var changed Object
				if err := json.Unmarshal(b, &changed); err != nil {
					t.Fatal(err)
				}
				edit(changed["content"].(map[string]any))
				if validateRunbook(changed["content"], Object{}, false) == nil {
					t.Fatal("invalid content accepted")
				}
			}
		})
	}
	if err := validateRunbook(Object{"text": "legacy"}, nil, true); err != nil {
		t.Fatal(err)
	}
}

func TestReportedRequirementsRemainInvestigationOnly(t *testing.T) {
	b, err := os.ReadFile("../../../rcca-agent/runbooks/xid/RB-XID-79.json")
	if err != nil {
		t.Fatal(err)
	}
	var row Object
	if err := json.Unmarshal(b, &row); err != nil {
		t.Fatal(err)
	}
	c := row["content"].(map[string]any)
	c["required_evidence"] = []any{"reported_error_code", "reported_producer_contract"}
	c["observation_plan"].([]any)[0].(map[string]any)["fact_names"] = []any{"reported_error_code", "reported_producer_contract"}
	if err := validateRunbook(c, Object{}, false); err != nil {
		t.Fatal(err)
	}
	c["investigation_only"] = false
	if validateRunbook(c, Object{}, false) == nil {
		t.Fatal("report-only facts accepted for causal runbook")
	}
	c["investigation_only"] = true
	c["recommendations"] = []any{Object{"text": "reboot", "preconditions": []any{Object{"field": "reported_error_code", "equals": "xid:79"}}, "execution": "not_performed"}}
	if validateRunbook(c, Object{}, false) == nil {
		t.Fatal("report-only action precondition accepted")
	}
}
