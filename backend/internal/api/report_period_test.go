package api

import (
	. "gpu-ops-advisor/backend/internal/contract"
	"testing"
	"time"
)

func TestReportDayRange(t *testing.T) {
	start := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	for _, hours := range []int{1, 23, 24, 25, 168, 744, 768} {
		value := Object{"start": start.Format(time.RFC3339), "end": start.Add(time.Duration(hours) * time.Hour).Format(time.RFC3339)}
		err := reportTimeRange(value, Object{"max_query_days": 31})
		want := hours >= 24 && hours <= 31*24 && hours%24 == 0
		if (err == nil) != want {
			t.Fatalf("%d hours: %v", hours, err)
		}
	}
	period := Object{"start": "2024-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"}
	if reportTimeRange(period, Object{"max_query_days": 31}) == nil {
		t.Fatal("ignored configured report cap")
	}
}
