package contract

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
		if topic == "O08" {
			if !(len(axes) == 1 && axes[0] == "namespace" || len(axes) == 2 && Has(axes, "namespace") && Has(axes, "cluster")) {
				return Invalid("topic_group_by.O08")
			}
		} else if !Has([]string{"O01", "O02", "O03", "O04", "O05", "O06", "O07", "O09", "O10", "O11"}, topic) || len(axes) != 1 || axes[0] != "cluster" {
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
