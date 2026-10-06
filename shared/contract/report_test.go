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
