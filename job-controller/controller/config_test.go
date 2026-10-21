package controller

import "testing"

func TestReportCriteriaProfile(t *testing.T) {
	config := DefaultConfig()
	if err := config.Validate(); err != nil {
		t.Fatal(err)
	}
	if config.Versions["criteria"] != "unconfigured" || config.Execution["local-v1"].Criteria != "" {
		t.Fatal("legacy criteria changed")
	}
	if config.Execution["report-namespace-v2"].Criteria != "1.3" {
		t.Fatal("new report criteria missing")
	}
	p := config.Execution["report-namespace-v1"]
	if p.Kind != "report" || p.Criteria != "1.2" {
		t.Fatal(p)
	}
	p.Kind = "rca"
	config.Execution["report-namespace-v1"] = p
	if config.Validate() == nil {
		t.Fatal("report criteria must not apply to RCA")
	}
}

// Only aggregate reports need the larger interpretation/repair allowance.
func TestAggregateBudgetPreservesOtherProfiles(t *testing.T) {
	c := DefaultConfig()
	if err := c.Validate(); err != nil {
		t.Fatal(err)
	}
	for name, p := range c.Execution {
		attempt, total := 32768, 98304
		if name == "report-aggregate-v1" {
			attempt, total = 65536, 196608
		}
		if p.AttemptBudget != attempt || p.TokenBudget != total || p.MaxAttempts != 3 {
			t.Fatalf("%s: unexpected budget/attempts: %+v", name, p)
		}
	}
}
