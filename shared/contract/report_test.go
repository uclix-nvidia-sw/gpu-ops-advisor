package contract

import "testing"

func TestTopicGroups(t *testing.T) {
	for _, tc := range []struct {
		raw   any
		valid bool
	}{
		{map[string][]string{"O01": {"cluster"}, "O08": {"namespace"}}, true},
		{map[string][]string{"O01": {"cluster"}, "O08": {"cluster", "namespace"}}, true},
		{nil, false}, {"namespace", false}, {map[string][]string{}, false},
		{map[string][]string{"O08": {"namespace"}}, false},
		{map[string][]string{"O01": {"namespace"}, "O08": {"namespace"}}, false},
		{map[string][]string{"O01": {"cluster"}, "O08": {"namespace", "namespace"}}, false},
		{map[string][]string{"O02": {"cluster"}, "O08": {"namespace"}}, false},
	} {
		input := Object{"topic_ids": []string{"O01", "O08"}, "group_by": []string{"cluster"}, "topic_group_by": tc.raw}
		hash := Hash(input)
		if e := ValidateTopicGroups(input); (e == nil) != tc.valid {
			t.Fatalf("%v: %v", tc.raw, e)
		}
		if Hash(input) != hash {
			t.Fatal("input mutated")
		}
	}
	if ValidateTopicGroups(Object{"topic_ids": []string{"O08"}, "group_by": []string{"namespace"}}) != nil {
		t.Fatal("legacy rejected")
	}
}

func TestAggregateReportContract(t *testing.T) {
	base := Object{"topic_ids": []string{"namespace_usage", "incident_summary"}, "group_by": []string{"cluster", "namespace"}, "timezone": "Asia/Seoul", "scope": Object{"clusters": []Object{{"cluster_id": "cpc-1", "namespaces": nil}}}, "time_range": Object{"start": "2026-10-11T15:00:00Z", "end": "2026-10-12T15:00:00Z"}}
	if err := ValidateAggregateReport(base); err != nil {
		t.Fatal(err)
	}
	for _, change := range []Object{
		{"topic_ids": []string{"namespace_usage", "O08"}},
		{"group_by": []string{"cluster"}},
		{"comparison_range": base["time_range"]},
		{"time_range": Object{"start": "2026-10-10T15:00:00Z", "end": "2026-10-12T15:00:00Z"}},
		{"time_range": Object{"start": "2026-10-11T15:00:01Z", "end": "2026-10-12T15:00:01Z"}},
	} {
		copy := Object{}
		for k, v := range base {
			copy[k] = v
		}
		for k, v := range change {
			copy[k] = v
		}
		if ValidateAggregateReport(copy) == nil {
			t.Fatalf("accepted %v", change)
		}
	}
	base["time_range"] = Object{"start": "2026-10-05T15:00:00Z", "end": "2026-10-12T15:00:00Z"}
	if err := ValidateAggregateReport(base); err != nil {
		t.Fatal(err)
	}
	if err := ValidateAggregateReport(Object{"topic_ids": []string{"O08"}}); err != nil {
		t.Fatal("legacy input changed", err)
	}
}
