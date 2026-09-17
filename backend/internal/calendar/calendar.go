// Package calendar computes immutable local-calendar report windows, including DST boundaries.
package calendar

import (
	"fmt"
	"time"
	_ "time/tzdata"
)

type Spec struct {
	Frequency string `json:"frequency"`
	LocalTime string `json:"local_time"`
	Timezone  string `json:"timezone"`
	Weekday   int    `json:"weekday"`
	Day       int    `json:"day"`
	Period    string `json:"period"`
}

func (s Spec) Validate() error {
	if _, e := time.Parse("15:04", s.LocalTime); e != nil || len(s.LocalTime) != 5 {
		return fmt.Errorf("local_time")
	}
	if _, e := time.LoadLocation(s.Timezone); e != nil || s.Timezone == "" {
		return fmt.Errorf("timezone")
	}
	expected := map[string]string{"daily": "previous_complete_day", "weekly": "previous_complete_week", "monthly": "previous_complete_month"}[s.Frequency]
	if expected == "" || expected != s.Period {
		return fmt.Errorf("period")
	}
	if s.Frequency == "weekly" && (s.Weekday < 1 || s.Weekday > 7) || s.Frequency != "weekly" && s.Weekday != 0 {
		return fmt.Errorf("weekday")
	}
	if s.Frequency == "monthly" && (s.Day < 1 || s.Day > 31) || s.Frequency != "monthly" && s.Day != 0 {
		return fmt.Errorf("day")
	}
	return nil
}

// Search actual instants in ascending order. A fold picks its first instant;
// a gap picks the first existing wall minute after the requested wall time.
func wall(y int, m time.Month, d, h, min int, loc *time.Location) time.Time {
	nominal := time.Date(y, m, d, h, min, 0, 0, time.UTC)
	var next time.Time
	var nextWall time.Time
	for t := nominal.Add(-26 * time.Hour); !t.After(nominal.Add(26 * time.Hour)); t = t.Add(time.Minute) {
		l := t.In(loc)
		w := time.Date(l.Year(), l.Month(), l.Day(), l.Hour(), l.Minute(), 0, 0, time.UTC)
		if w.Equal(nominal) {
			return t
		}
		if w.After(nominal) && (next.IsZero() || w.Before(nextWall)) {
			next = t
			nextWall = w
		}
	}
	return next
}
func (s Spec) Next(after time.Time) time.Time {
	loc, _ := time.LoadLocation(s.Timezone)
	local := after.In(loc)
	date := time.Date(local.Year(), local.Month(), local.Day(), 0, 0, 0, 0, time.UTC)
	clock, _ := time.Parse("15:04", s.LocalTime)
	for i := 0; i < 370; i++ {
		day := date.AddDate(0, 0, i)
		wd := int(day.Weekday())
		if wd == 0 {
			wd = 7
		}
		if s.Frequency == "weekly" && wd != s.Weekday {
			continue
		}
		if s.Frequency == "monthly" {
			last := time.Date(day.Year(), day.Month()+1, 0, 0, 0, 0, 0, time.UTC).Day()
			want := s.Day
			if want > last {
				want = last
			}
			if day.Day() != want {
				continue
			}
		}
		due := wall(day.Year(), day.Month(), day.Day(), clock.Hour(), clock.Minute(), loc)
		if due.After(after) {
			return due
		}
	}
	panic("validated calendar produced no occurrence")
}
func (s Spec) Window(due time.Time) (time.Time, time.Time) {
	loc, _ := time.LoadLocation(s.Timezone)
	l := due.In(loc)
	end := time.Date(l.Year(), l.Month(), l.Day(), 0, 0, 0, 0, time.UTC)
	var start time.Time
	switch s.Frequency {
	case "daily":
		start = end.AddDate(0, 0, -1)
	case "weekly":
		offset := (int(end.Weekday()) + 6) % 7
		end = end.AddDate(0, 0, -offset)
		start = end.AddDate(0, 0, -7)
	case "monthly":
		end = time.Date(l.Year(), l.Month(), 1, 0, 0, 0, 0, time.UTC)
		start = end.AddDate(0, -1, 0)
	}
	return wall(start.Year(), start.Month(), start.Day(), 0, 0, loc), wall(end.Year(), end.Month(), end.Day(), 0, 0, loc)
}
