package controller

import (
	"bytes"
	"encoding/json"
	"errors"
	. "gpu-ops-advisor/shared/contract"
	"net"
	"os"
)

type WorkerProfile struct {
	Kind  string `json:"kind"`
	Slots int    `json:"slots"`
}
type Execution struct {
	MaxAttempts      int    `json:"max_attempts"`
	TokenBudget      int    `json:"token_budget"`
	AttemptBudget    int    `json:"attempt_budget"`
	LeaseSeconds     int    `json:"lease_seconds"`
	HeartbeatSeconds int    `json:"heartbeat_seconds"`
	RetrySeconds     int    `json:"retry_seconds"`
	Schema           string `json:"result_schema"`
}
type Config struct {
	SharedLimit  int                      `json:"shared_limit"`
	KindLimits   map[string]int           `json:"kind_limits"`
	Workers      map[string]WorkerProfile `json:"worker_profiles"`
	Execution    map[string]Execution     `json:"execution_profiles"`
	FreshSeconds int                      `json:"worker_fresh_seconds"`
	Versions     Object                   `json:"versions"`
}

func DefaultConfig() Config {
	return Config{SharedLimit: 1, KindLimits: map[string]int{"rca": 1, "report": 1}, Workers: map[string]WorkerProfile{"rca-v1": {"rca", 1}, "report-v1": {"report", 1}}, Execution: map[string]Execution{"local-v1": {3, 3000, 1000, 30, 5, 5, "1.3"}}, FreshSeconds: 90, Versions: Object{"query": "unconfigured", "parser": "unconfigured", "criteria": "unconfigured", "result_schema": "1.3"}}
}
func (c Config) Validate() error {
	if c.SharedLimit < 1 || c.FreshSeconds < 1 || len(c.Workers) == 0 || len(c.Execution) == 0 {
		return errors.New("positive capacity/profile configuration required")
	}
	if len(c.KindLimits) != 2 || c.KindLimits["rca"] < 1 || c.KindLimits["report"] < 1 {
		return errors.New("rca/report limits required")
	}
	for id, p := range c.Workers {
		if id == "" || !Has([]string{"rca", "report"}, p.Kind) || p.Slots < 1 {
			return errors.New("invalid worker profile")
		}
	}
	for id, p := range c.Execution {
		if id == "" || p.MaxAttempts < 1 || p.TokenBudget < 1 || p.AttemptBudget < 1 || p.AttemptBudget > p.TokenBudget || p.HeartbeatSeconds < 1 || p.LeaseSeconds < 3*p.HeartbeatSeconds || p.LeaseSeconds > 86400 || p.RetrySeconds < 1 || p.Schema != "1.3" || c.FreshSeconds < p.LeaseSeconds {
			return errors.New("invalid execution profile")
		}
	}
	for _, k := range []string{"query", "parser", "criteria", "result_schema"} {
		if String(c.Versions, k) == "" {
			return errors.New("version snapshots required")
		}
	}
	return nil
}
func LoadConfig() (Config, error) {
	c := DefaultConfig()
	if path := os.Getenv("JC_CONFIG_FILE"); path != "" {
		b, e := os.ReadFile(path)
		if e != nil {
			return c, e
		}
		decoder := json.NewDecoder(bytes.NewReader(b))
		decoder.DisallowUnknownFields()
		if e = decoder.Decode(&c); e != nil {
			return c, e
		}
	}
	return c, c.Validate()
}
func ListenAddress() (string, error) {
	s := os.Getenv("JC_ADDRESS")
	if s == "" {
		s = "127.0.0.1:8090"
	}
	host, _, e := net.SplitHostPort(s)
	if e != nil {
		return s, e
	}
	ip := net.ParseIP(host)
	if (ip == nil || !ip.IsLoopback()) && os.Getenv("DSX_ALLOW_UNAUTHENTICATED_NETWORK") != "true" {
		return s, errors.New("bind loopback or explicitly opt in to a trusted network")
	}
	return s, nil
}
