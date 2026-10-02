package api

import (
	"sort"
	"time"

	. "gpu-ops-advisor/backend/internal/contract"
)

// Order the entire attempt before pagination. Only compact metadata is loaded.
// Legacy rows have storage time only: their phase order is an inference, not timing.
func orderEvidence(items []Object) {
	quality := func(v Object) Object {
		q, _ := v["quality"].(map[string]any)
		return q
	}
	round := func(v Object) int {
		if _, ok := quality(v)["round"]; ok {
			return Number(quality(v), "round")
		}
		return Number(v, "_round")
	}
	plans := map[int]map[string]int{}
	for _, v := range items {
		if String(v, "query_id") != "observation_plan" {
			continue
		}
		assignments, _ := v["_assignments"].([]any)
		plans[round(v)] = map[string]int{}
		for i, raw := range assignments {
			a, _ := raw.(map[string]any)
			plans[round(v)][String(a, "sub_agent_id")] = i
		}
	}
	plan := func(v Object) (int, bool) {
		q := quality(v)
		if _, ok := q["plan_order"]; ok {
			return Number(q, "plan_order"), true
		}
		i, ok := plans[round(v)][String(q, "sub_agent_id")]
		return i, ok
	}
	phase := func(v Object) int {
		switch String(v, "query_id") {
		case "incident_snapshot", "report_db_snapshot":
			return 0
		case "alert_clues":
			return 1
		case "runbook_selection":
			return 2
		case "investigation_plan", "purpose_plan":
			return 3
		case "observation_plan":
			return 10 + round(v)*10
		case "unexpected_evidence":
			return 12 + round(v)*10
		case "investigation_plan_extension":
			return 13 + round(v)*10
		case "sufficiency":
			return 14 + round(v)*10
		case "rca_synthesis":
			return 1000000
		}
		if _, ok := plan(v); ok {
			return 11 + round(v)*10
		}
		return 1000001
	}
	at := func(v Object) time.Time {
		t, err := time.Parse(time.RFC3339Nano, String(quality(v), "recorded_at"))
		if err == nil {
			v["recorded_at"] = String(quality(v), "recorded_at")
			v["order_basis"] = "recorded_time"
			return t.UTC()
		}
		v["order_basis"] = "inferred_plan"
		if phase(v) == 1000001 {
			v["order_basis"] = "unknown"
		}
		t, _ = time.Parse(time.RFC3339Nano, String(v, "created_at"))
		return t.UTC()
	}
	times := map[string]time.Time{}
	for _, v := range items {
		times[String(v, "id")] = at(v)
	}
	sort.SliceStable(items, func(i, j int) bool {
		a, b := items[i], items[j]
		ta, tb := times[String(a, "id")], times[String(b, "id")]
		if !ta.Equal(tb) {
			return ta.Before(tb)
		}
		if actualA, actualB := String(a, "order_basis") == "recorded_time", String(b, "order_basis") == "recorded_time"; actualA != actualB {
			return actualA
		}
		if String(a, "order_basis") == "recorded_time" && String(b, "order_basis") == "recorded_time" {
			if sa, sb := Number(quality(a), "record_sequence"), Number(quality(b), "record_sequence"); sa != sb {
				return sa < sb
			}
		} else if pa, pb := phase(a), phase(b); pa != pb {
			return pa < pb
		}
		return String(a, "id") < String(b, "id")
	})
	// Reorder only planned-query slots at the same instant and in the same round.
	// Unplanned decisions keep their chronological/sequence positions.
	groups := map[struct {
		at    time.Time
		round int
	}][]int{}
	for i, v := range items {
		if _, ok := plan(v); ok {
			key := struct {
				at    time.Time
				round int
			}{times[String(v, "id")], round(v)}
			groups[key] = append(groups[key], i)
		}
	}
	for _, slots := range groups {
		ordered := make([]Object, len(slots))
		for i, slot := range slots {
			ordered[i] = items[slot]
		}
		sort.SliceStable(ordered, func(i, j int) bool {
			a, _ := plan(ordered[i])
			b, _ := plan(ordered[j])
			if a != b {
				return a < b
			}
			// Derived observations follow their concrete source on legacy ties.
			da, db := String(quality(ordered[i]), "derived_from") != "", String(quality(ordered[j]), "derived_from") != ""
			if da != db {
				return !da
			}
			return false
		})
		for i, slot := range slots {
			items[slot] = ordered[i]
		}
	}
	for _, v := range items {
		delete(v, "_round")
		delete(v, "_assignments")
	}
}
