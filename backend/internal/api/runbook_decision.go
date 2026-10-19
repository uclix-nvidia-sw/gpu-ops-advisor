package api

import . "gpu-ops-advisor/backend/internal/contract"

// Only the bounded report-identification objective is supported; no rule expressions.
func validDecisionPolicy(c Object) bool {
	raw, exists := c["decision_policy"]
	if c["schema"] != "gpu-rca-runbook/1.1" && c["schema"] != "gpu-rca-runbook/1.2" {
		return !exists
	}
	p, ok := raw.(map[string]any)
	if !ok || c["investigation_only"] != true || len(p) != 6 || only(p, "goal", "applies_when", "completion_criteria", "blocking_conditions", "non_blocking_unknowns", "followup_links") != nil {
		return false
	}
	goal, ok := p["goal"].(map[string]any)
	if !ok || len(goal) != 3 || goal["id"] != "identify_error_report" || !runbookText(goal["question"]) || !runbookText(goal["conclusion_scope"]) {
		return false
	}
	applies, ok := p["applies_when"].(map[string]any)
	if !ok || !runbookText(applies["reported_producer_contract"]) {
		return false
	}
	codeGoal := len(applies) == 2 && runbookCode.MatchString(String(applies, "reported_error_code"))
	componentGoal := c["schema"] == "gpu-rca-runbook/1.2" && (len(applies) == 3 || len(applies) == 4 && runbookText(applies["reported_reason"])) && runbookText(applies["reported_component"]) && applies["reported_normalized_health"] == "unhealthy"
	if !codeGoal && !componentGoal {
		return false
	}
	blockers, ok := runbookStrings(p["blocking_conditions"])
	if !ok || len(blockers) != 4 {
		return false
	}
	for _, id := range []string{"scope_unverified", "identity_conflict", "required_query_incomplete", "conflicting_reports"} {
		if !Has(blockers, id) {
			return false
		}
	}
	unknowns, ok := runbookStrings(p["non_blocking_unknowns"])
	if !ok {
		return false
	}
	for _, id := range unknowns {
		if !Has([]string{"causal_confirmation_evidence", "current_health", "physical_or_synthetic_origin"}, id) {
			return false
		}
	}
	criteria, ok := p["completion_criteria"].([]any)
	if !ok || len(criteria) == 0 || len(criteria) > 8 {
		return false
	}
	ids, requiredCode, semantic := map[string]bool{}, map[string]bool{}, false
	for _, raw := range criteria {
		r, ok := raw.(map[string]any)
		if !ok || len(r) != 4 || only(r, "id", "question", "method", "required") != nil || !runbookText(r["id"]) || !runbookText(r["question"]) {
			return false
		}
		id := String(r, "id")
		required, ok := r["required"].(bool)
		if !ok || ids[id] || !Has([]string{"code", "llm"}, String(r, "method")) {
			return false
		}
		ids[id] = true
		if r["method"] == "code" {
			if !Has([]string{"reported_error", "scoped_source"}, id) {
				return false
			}
			requiredCode[id] = required
		} else if required {
			semantic = true
		}
	}
	if !requiredCode["reported_error"] || !requiredCode["scoped_source"] || !semantic {
		return false
	}
	steps, ok := c["observation_plan"].([]any)
	if !ok {
		return false
	}
	queries := map[string]bool{}
	for _, raw := range steps {
		step, ok := raw.(map[string]any)
		if !ok {
			return false
		}
		queries[String(step, "query_id")] = step["required"] == true
	}
	links, ok := p["followup_links"].([]any)
	if !ok || len(links) != len(queries) {
		return false
	}
	seen := map[string]bool{}
	for _, raw := range links {
		r, ok := raw.(map[string]any)
		if !ok || len(r) != 4 || only(r, "query_id", "criterion_ids", "required", "expected_effect") != nil || !runbookText(r["expected_effect"]) {
			return false
		}
		query := String(r, "query_id")
		must, known := queries[query]
		required, boolean := r["required"].(bool)
		if !known || !boolean || seen[query] || must && !required {
			return false
		}
		seen[query] = true
		refs, valid := runbookStrings(r["criterion_ids"])
		if !valid || len(refs) == 0 {
			return false
		}
		for _, id := range refs {
			if !ids[id] {
				return false
			}
		}
	}
	return true
}
