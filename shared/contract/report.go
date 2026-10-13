package contract

import "time"

const AggregateReportVersion = "report-aggregate-v1"

func IsAggregateReport(input Object) bool {
	topics, _ := Decode[[]string](input["topic_ids"])
	return Has(topics, "namespace_usage") || Has(topics, "incident_summary")
}

// ValidateAggregateReport leaves immutable legacy requests untouched.
func ValidateAggregateReport(input Object) error {
	if !IsAggregateReport(input) {
		return nil
	}
	topics, _ := Decode[[]string](input["topic_ids"])
	for _, topic := range topics {
		if topic != "namespace_usage" && topic != "incident_summary" {
			return Invalid("mixed_report_versions")
		}
	}
	period, _ := Decode[Object](input["time_range"])
	start, e1 := time.Parse(time.RFC3339Nano, String(period, "start"))
	end, e2 := time.Parse(time.RFC3339Nano, String(period, "end"))
	if e1 != nil || e2 != nil || (end.Sub(start) != 24*time.Hour && end.Sub(start) != 7*24*time.Hour) || (start.Unix()+9*3600)%86400 != 0 || String(input, "timezone") != "Asia/Seoul" || start.Nanosecond() != 0 || end.Nanosecond() != 0 {
		return Invalid("aggregate_daily_or_weekly_period")
	}
	for _, field := range []string{"comparison_range", "action_record_ids", "resource_selectors"} {
		if _, ok := input[field]; ok {
			return Invalid("aggregate_" + field)
		}
	}
	groups, _ := Decode[[]string](input["group_by"])
	if len(groups) != 2 || !Has(groups, "cluster") || !Has(groups, "namespace") {
		return Invalid("aggregate_group_by")
	}
	scope, err := Decode[Scope](input["scope"])
	if err != nil || len(scope.Clusters) == 0 || len(scope.Clusters) > 4 {
		return Invalid("aggregate_scope_limit")
	}
	for _, cluster := range scope.Clusters {
		if len(cluster.Namespaces) > 100 {
			return Invalid("aggregate_namespace_limit")
		}
	}
	return nil
}

// ValidateTopicGroups checks the optional per-topic presets without rewriting legacy inputs.
// Only the native report presets are supported; this is not arbitrary regrouping.
func ValidateTopicGroups(input Object) error {
	raw, exists := input["topic_group_by"]
	if !exists {
		return nil
	}
	groups, err := Decode[map[string][]string](raw)
	topics, topicErr := Decode[[]string](input["topic_ids"])
	if err != nil || topicErr != nil || len(groups) == 0 || len(groups) != len(topics) {
		return Invalid("topic_group_by")
	}
	for _, topic := range topics {
		axes := groups[topic]
		if topic == "O08" || topic == "namespace_usage" {
			if !(len(axes) == 1 && axes[0] == "namespace" || len(axes) == 2 && Has(axes, "namespace") && Has(axes, "cluster")) {
				return Invalid("topic_group_by.O08")
			}
		} else if !Has([]string{"O01", "O02", "O03", "O04", "O05", "O06", "O07", "O09", "O10", "O11", "incident_summary"}, topic) || len(axes) != 1 || axes[0] != "cluster" {
			return Invalid("topic_group_by")
		}
	}
	return nil
}

func ReportTopicGroups(input Object, topic string) []string {
	groups, _ := Decode[map[string][]string](input["topic_group_by"])
	if axes, ok := groups[topic]; ok {
		return axes
	}
	axes, _ := Decode[[]string](input["group_by"])
	return axes
}
