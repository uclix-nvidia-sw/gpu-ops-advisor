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

func TestDecisionPolicyCannotRelaxCompletion(t *testing.T) {
	b, err := os.ReadFile("../../../rcca-agent/runbooks/xid/RB-XID-79.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, change := range []string{"legacy", "blocker", "required_query", "criterion", "unknown_query"} {
		t.Run(change, func(t *testing.T) {
			var row Object
			if err := json.Unmarshal(b, &row); err != nil {
				t.Fatal(err)
			}
			c := row["content"].(map[string]any)
			p := c["decision_policy"].(map[string]any)
			switch change {
			case "legacy":
				c["schema"] = "gpu-rca-runbook/1.0"
			case "blocker":
				p["blocking_conditions"] = []any{}
			case "required_query":
				p["followup_links"].([]any)[0].(map[string]any)["required"] = false
			case "criterion":
				p["completion_criteria"].([]any)[0].(map[string]any)["required"] = false
			case "unknown_query":
				p["followup_links"].([]any)[0].(map[string]any)["query_id"] = "D999"
			}
			if validateRunbook(c, Object{}, false) == nil {
				t.Fatal("unsafe decision policy accepted")
			}
		})
	}
}

func TestComponentReportGoalRequiresVersionAndUnhealthyReport(t *testing.T) {
	b, err := os.ReadFile("../../../rcca-agent/runbooks/xid/RB-XID-79.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, variant := range []string{"valid", "exact_reason", "empty_reason", "old_schema", "healthy", "missing_component", "action_fact"} {
		t.Run(variant, func(t *testing.T) {
			var row Object
			if err := json.Unmarshal(b, &row); err != nil {
				t.Fatal(err)
			}
			c := row["content"].(map[string]any)
			c["schema"] = "gpu-rca-runbook/1.2"
			c["required_evidence"] = []any{"reported_component", "reported_normalized_health", "reported_producer_contract"}
			applies := Object{"reported_component": "disk", "reported_normalized_health": "unhealthy", "reported_producer_contract": "fleet-component-log-v1"}
			c["decision_policy"].(map[string]any)["applies_when"] = applies
			switch variant {
			case "exact_reason":
				applies["reported_reason"] = "filesystem is read-only"
			case "empty_reason":
				applies["reported_reason"] = ""
			case "old_schema":
				c["schema"] = "gpu-rca-runbook/1.1"
			case "healthy":
				applies["reported_normalized_health"] = "healthy"
			case "missing_component":
				delete(applies, "reported_component")
			case "action_fact":
				c["recommendations"] = []any{Object{"text": "restart", "preconditions": []any{Object{"field": "reported_normalized_health", "equals": "unhealthy"}}, "execution": "not_performed"}}
			}
			err := validateRunbook(c, Object{}, false)
			if (err == nil) != (variant == "valid" || variant == "exact_reason") {
				t.Fatalf("unexpected validation: %v", err)
			}
		})
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

func TestAuxiliarySelectionConditions(t *testing.T) {
	b, err := os.ReadFile("../../../rcca-agent/runbooks/xid/RB-XID-79.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, invalid := range []string{"", "gap", "prerequisite", "dependent", "required", "extra"} {
		t.Run(invalid, func(t *testing.T) {
			var row Object
			if err := json.Unmarshal(b, &row); err != nil {
				t.Fatal(err)
			}
			c := row["content"].(map[string]any)
			step := c["observation_plan"].([]any)[1].(map[string]any)
			rule := step["selection"].(map[string]any)
			switch invalid {
			case "gap":
				rule["missing_any"] = []any{"invented"}
			case "prerequisite":
				rule["requires_all"] = []any{"invented"}
			case "dependent":
				rule["independent"] = false
			case "required":
				step["required"] = true
			case "extra":
				rule["extra"] = true
			}
			err := validateRunbook(c, Object{}, false)
			if (err != nil) != (invalid != "") {
				t.Fatalf("unexpected validation: %v", err)
			}
		})
	}
}

func TestExploratorySelectionRequiresExplicitPermission(t *testing.T) {
	b, err := os.ReadFile("../../../rcca-agent/runbooks/xid/RB-XID-79.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, value := range []any{true, false, "true", float64(1), nil} {
		var row Object
		if err := json.Unmarshal(b, &row); err != nil {
			t.Fatal(err)
		}
		c := row["content"].(map[string]any)
		step := c["observation_plan"].([]any)[1].(map[string]any)
		delete(step, "selection")
		step["exploratory_llm"] = value
		if err := validateRunbook(c, Object{}, false); (err == nil) != (value == true) {
			t.Fatalf("opt-in %v: %v", value, err)
		}
		step["required"] = true
		if validateRunbook(c, Object{}, false) == nil {
			t.Fatal("required exploration accepted")
		}
	}
}
