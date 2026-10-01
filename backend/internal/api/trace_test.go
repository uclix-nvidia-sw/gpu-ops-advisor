package api

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestTraceRedaction(t *testing.T) {
	var value map[string]any
	if err := json.Unmarshal([]byte(`{"input":{"Authorization":"SECRET","api-key":"SECRET","logql":"{cluster_id=\"cpc-1\"}"},"records":[{"claim_token":"SECRET","object_key":"SECRET","password":"SECRET","id":"e1"}]}`), &value); err != nil {
		t.Fatal(err)
	}
	cleanTrace(value)
	result, _ := json.Marshal(value)
	if strings.Contains(string(result), "SECRET") || !strings.Contains(string(result), "logql") || !strings.Contains(string(result), "e1") {
		t.Fatal(string(result))
	}
}
