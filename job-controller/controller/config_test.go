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
