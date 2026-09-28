package api

import (
	"encoding/json"
	"net/url"
	"regexp"
	"strings"
	"time"

	. "gpu-ops-advisor/backend/internal/contract"
)

var runbookCode = regexp.MustCompile(`^(xid|sxid):(0|[1-9][0-9]*)$`)

// validateRunbook validates stored v1 content, independently of any Worker profile.
// Query registration/procedure allowlists remain checks in the authoring CLI and Worker.
func validateRunbook(content, compatibility any, publishing bool) error {
	b, err := json.Marshal(content)
	if err != nil {
		return Invalid("runbook.content")
	}
	var c Object
	if json.Unmarshal(b, &c) != nil || c == nil {
		return Invalid("runbook.content")
	}
	if _, exists := c["schema"]; !exists {
		return nil
	} // Existing legacy knowledge.
	if c["schema"] != "gpu-rca-runbook/1.0" {
		return Invalid("runbook.schema")
	}
	if err := only(c, "schema", "title", "description", "claim", "classification", "search", "required_evidence", "applicability_conditions", "exclusion_conditions", "required_queries", "observation_plan", "recommendations", "sources", "analysis_guidance", "limitations", "investigation_only"); err != nil {
		return err
	}
	for _, key := range []string{"title", "description", "claim"} {
		if !runbookText(c[key]) {
			return Invalid("runbook." + key)
		}
	}
	investigation := false
	if raw, exists := c["investigation_only"]; exists {
		var ok bool
		investigation, ok = raw.(bool)
		if !ok {
			return Invalid("runbook.investigation_only")
		}
	}
	classification, ok := c["classification"].(map[string]any)
	if !ok || len(classification) != 2 || !runbookText(classification["domain"]) || !runbookText(classification["category"]) {
		return Invalid("runbook.classification")
	}
	search, ok := c["search"].(map[string]any)
	if !ok {
		return Invalid("runbook.search")
	}
	if err := only(search, "codes", "producer_events", "aliases", "symptoms"); err != nil {
		return err
	}
	clues := 0
	for key, raw := range search {
		values, valid := runbookStrings(raw)
		if !valid {
			return Invalid("runbook.search")
		}
		clues += len(values)
		for _, v := range values {
			if key == "codes" && !runbookCode.MatchString(v) {
				return Invalid("runbook.search.codes")
			}
		}
	}
	if clues == 0 {
		return Invalid("runbook.search")
	}
	facts := []string{"producer_contract", "error_code", "incident_mapping", "observations", "incident_history", "topology", "current_mapping", "action_policy", "action_records", "device_recovery_evidence", "workload_evidence", "normalized_health", "component", "severity"}
	required, ok := runbookStrings(c["required_evidence"])
	if !ok || len(required) == 0 {
		return Invalid("runbook.required_evidence")
	}
	for _, v := range required {
		if !Has(facts, v) {
			return Invalid("runbook.required_evidence")
		}
	}
	if !runbookConditions(c["applicability_conditions"], !investigation) {
		return Invalid("runbook.applicability_conditions")
	}
	if raw, exists := c["exclusion_conditions"]; exists && !runbookConditions(raw, false) {
		return Invalid("runbook.exclusion_conditions")
	}
	for _, key := range []string{"analysis_guidance", "limitations"} {
		if raw, exists := c[key]; exists {
			if _, ok := runbookStrings(raw); !ok {
				return Invalid("runbook." + key)
			}
		}
	}
	if raw, exists := c["recommendations"]; exists {
		items, ok := raw.([]any)
		if !ok {
			return Invalid("runbook.recommendations")
		}
		for _, item := range items {
			r, ok := item.(map[string]any)
			if !ok || only(r, "text", "preconditions", "execution") != nil || !runbookText(r["text"]) || !runbookConditions(r["preconditions"], true) {
				return Invalid("runbook.recommendations")
			}
			if execution, exists := r["execution"]; exists && execution != "not_performed" {
				return Invalid("runbook.execution")
			}
		}
	}
	sources, ok := c["sources"].([]any)
	if !ok || len(sources) == 0 {
		return Invalid("runbook.sources")
	}
	for _, raw := range sources {
		s, ok := raw.(map[string]any)
		if !ok || len(s) != 4 {
			return Invalid("runbook.sources")
		}
		for _, key := range []string{"url", "revision", "section", "checked_at"} {
			if !runbookText(s[key]) {
				return Invalid("runbook.sources")
			}
		}
		u, err := url.Parse(s["url"].(string))
		if err != nil || u.Hostname() == "" || u.User != nil || !Has([]string{"http", "https"}, u.Scheme) {
			return Invalid("runbook.sources.url")
		}
		if _, err := time.Parse("2006-01-02", s["checked_at"].(string)); err != nil {
			return Invalid("runbook.sources.checked_at")
		}
	}
	queries := []string{}
	if raw, exists := c["required_queries"]; exists {
		queries, ok = runbookStrings(raw)
		if !ok {
			return Invalid("runbook.required_queries")
		}
	}
	if raw, exists := c["observation_plan"]; exists {
		steps, ok := raw.([]any)
		if !ok {
			return Invalid("runbook.observation_plan")
		}
		seen, required := map[string]bool{}, map[string]bool{}
		for _, raw := range steps {
			s, ok := raw.(map[string]any)
			if !ok || len(s) != 8 {
				return Invalid("runbook.observation_plan")
			}
			for _, key := range []string{"query_id", "purpose"} {
				if !runbookText(s[key]) {
					return Invalid("runbook.observation_plan")
				}
			}
			id := s["query_id"].(string)
			priority, number := s["priority"].(float64)
			must, boolean := s["required"].(bool)
			if seen[id] || !number || priority <= 0 || priority != float64(int(priority)) || !boolean || s["binding"] != "execution_profile" || s["time_range"] != "incident" || s["freshness"] != "query_contract" {
				return Invalid("runbook.observation_plan")
			}
			seen[id] = true
			if must {
				required[id] = true
			}
			names, valid := runbookStrings(s["fact_names"])
			if !valid {
				return Invalid("runbook.fact_names")
			}
			for _, v := range names {
				if !Has(facts, v) {
					return Invalid("runbook.fact_names")
				}
			}
		}
		if _, exists := c["required_queries"]; exists {
			if len(queries) != len(required) {
				return Invalid("runbook.required_queries")
			}
			for _, q := range queries {
				if !required[q] {
					return Invalid("runbook.required_queries")
				}
			}
		}
	}
	b, err = json.Marshal(compatibility)
	if err != nil {
		return Invalid("runbook.compatibility")
	}
	var compat Object
	if json.Unmarshal(b, &compat) != nil || compat == nil || publishing && len(compat) == 0 {
		return Invalid("runbook.compatibility")
	}
	stringsAllowed := []string{"cluster_id", "producer_contract", "gpu_model", "driver_version", "dcgm_version", "fleet_version", "fabric_manager_version"}
	for key, raw := range compat {
		values, array := raw.([]any)
		if !array {
			values = []any{raw}
		}
		if len(values) == 0 {
			return Invalid("runbook.compatibility")
		}
		for _, value := range values {
			if Has(stringsAllowed, key) {
				if !runbookText(value) || strings.ContainsAny(value.(string), "*?<>~=^") {
					return Invalid("runbook.compatibility")
				}
			} else if key == "mig_enabled" || key == "nvswitch_present" {
				if _, ok := value.(bool); !ok {
					return Invalid("runbook.compatibility")
				}
			} else {
				return Invalid("runbook.compatibility")
			}
		}
	}
	return nil
}

func runbookText(v any) bool { s, ok := v.(string); return ok && strings.TrimSpace(s) != "" }

func runbookStrings(v any) ([]string, bool) {
	items, ok := v.([]any)
	if !ok {
		return nil, false
	}
	values, seen := []string{}, map[string]bool{}
	for _, raw := range items {
		if !runbookText(raw) {
			return nil, false
		}
		s := raw.(string)
		if seen[s] {
			return nil, false
		}
		values, seen[s] = append(values, s), true
	}
	return values, true
}

func runbookConditions(v any, required bool) bool {
	items, ok := v.([]any)
	if !ok || required && len(items) == 0 {
		return false
	}
	for _, raw := range items {
		c, ok := raw.(map[string]any)
		if !ok || len(c) != 2 || !runbookText(c["field"]) || !runbookText(c["equals"]) {
			return false
		}
		field := c["field"].(string)
		if !Has([]string{"producer_contract", "error_code", "normalized_health", "component", "severity"}, field) {
			return false
		}
		if field == "error_code" && !runbookCode.MatchString(c["equals"].(string)) {
			return false
		}
	}
	return true
}
