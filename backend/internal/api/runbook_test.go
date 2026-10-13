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

func TestOperatorGuidanceContract(t *testing.T) {
	b, err := os.ReadFile("../../../rcca-agent/runbooks/xid/RB-XID-79.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, value := range []any{nil, "invalid", Object{"schema": "unknown"}} {
		var row Object
		if err := json.Unmarshal(b, &row); err != nil {
			t.Fatal(err)
		}
		c := row["content"].(map[string]any)
		c["operator_guidance"] = value
		if validateRunbook(c, Object{}, false) == nil {
			t.Fatal("invalid guidance accepted")
		}
	}
	var row Object
	if err := json.Unmarshal(b, &row); err != nil {
		t.Fatal(err)
	}
	c := row["content"].(map[string]any)
	g := c["operator_guidance"].(map[string]any)
	for _, index := range []any{-1, 999, 0.5, true, "0"} {
		g["references"].([]any)[0].(map[string]any)["source_indices"] = []any{index}
		if validateRunbook(c, Object{}, false) == nil {
			t.Fatal("invalid source index accepted")
		}
	}
	delete(c, "operator_guidance")
	if err := validateRunbook(c, Object{}, false); err != nil {
		t.Fatal(err)
	}
}
