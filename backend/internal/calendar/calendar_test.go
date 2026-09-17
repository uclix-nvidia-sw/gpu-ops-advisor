package calendar

import (
	"testing"
	"time"
)

func TestCalendarBoundaries(t *testing.T) {
	for _, tc := range []struct {
		name                   string
		spec                   Spec
		after, due, start, end string
	}{
		{"gap", Spec{Frequency: "daily", LocalTime: "02:30", Timezone: "America/New_York", Period: "previous_complete_day"}, "2026-03-08T00:00:00Z", "2026-03-08T07:00:00Z", "2026-03-07T05:00:00Z", "2026-03-08T05:00:00Z"},
		{"fold_first", Spec{Frequency: "daily", LocalTime: "01:30", Timezone: "America/New_York", Period: "previous_complete_day"}, "2026-11-01T00:00:00Z", "2026-11-01T05:30:00Z", "2026-10-31T04:00:00Z", "2026-11-01T04:00:00Z"},
		{"short_day", Spec{Frequency: "daily", LocalTime: "09:00", Timezone: "America/New_York", Period: "previous_complete_day"}, "2026-03-09T00:00:00Z", "2026-03-09T13:00:00Z", "2026-03-08T05:00:00Z", "2026-03-09T04:00:00Z"},
		{"month_clamp", Spec{Frequency: "monthly", LocalTime: "09:00", Timezone: "Asia/Seoul", Day: 31, Period: "previous_complete_month"}, "2026-02-01T00:00:00Z", "2026-02-28T00:00:00Z", "2025-12-31T15:00:00Z", "2026-01-31T15:00:00Z"},
		{"monday_week", Spec{Frequency: "weekly", LocalTime: "09:00", Timezone: "Asia/Seoul", Weekday: 3, Period: "previous_complete_week"}, "2026-09-13T00:00:00Z", "2026-09-16T00:00:00Z", "2026-09-06T15:00:00Z", "2026-09-13T15:00:00Z"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if e := tc.spec.Validate(); e != nil {
				t.Fatal(e)
			}
			after, _ := time.Parse(time.RFC3339, tc.after)
			due := tc.spec.Next(after)
			start, end := tc.spec.Window(due)
			if due.Format(time.RFC3339) != tc.due || start.Format(time.RFC3339) != tc.start || end.Format(time.RFC3339) != tc.end {
				t.Fatalf("%v %v %v", due, start, end)
			}
		})
	}
}
