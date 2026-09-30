package config

import (
	"errors"
	"net"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Address, DatabaseURL                       string
	ExecutionRevision                          string
	NamespaceReportRevision                    string
	SchedulerEnabled                           bool
	CatchupWindow, DispatchWindow, JobDeadline time.Duration
	MaxCatchup                                 int
	Modules                                    map[string]string
	ModelHosts                                 []string
	ModelAPIKey                                string
	ModelNetworks                              []*net.IPNet
	Migrate, Seed                              bool
}

func Load() (Config, error) {
	c := Config{Address: env("DSX_ADDRESS", "127.0.0.1:8080"), DatabaseURL: os.Getenv("DATABASE_URL"), Modules: map[string]string{}, ModelHosts: strings.FieldsFunc(os.Getenv("DSX_MODEL_HOSTS"), func(r rune) bool { return r == ',' }), Migrate: os.Getenv("DSX_MIGRATE") == "true", Seed: os.Getenv("DSX_SEED") == "true"}
	c.ModelAPIKey = os.Getenv("LLM_API_KEY")
	host, _, e := net.SplitHostPort(c.Address)
	if e != nil {
		return c, e
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		if os.Getenv("DSX_ALLOW_UNAUTHENTICATED_NETWORK") != "true" {
			return c, errors.New("authentication is intentionally disabled; bind loopback or explicitly opt in using DSX_ALLOW_UNAUTHENTICATED_NETWORK=true")
		}
	}
	if c.DatabaseURL == "" {
		return c, errors.New("DATABASE_URL is required")
	}
	for _, raw := range strings.Split(os.Getenv("DSX_MODEL_CIDRS"), ",") {
		if strings.TrimSpace(raw) == "" {
			continue
		}
		_, network, e := net.ParseCIDR(strings.TrimSpace(raw))
		if e != nil {
			return c, errors.New("invalid DSX_MODEL_CIDRS")
		}
		c.ModelNetworks = append(c.ModelNetworks, network)
	}
	for _, m := range []string{"job_controller", "incident"} {
		if raw := os.Getenv("DSX_" + strings.ToUpper(m) + "_URL"); raw != "" {
			u, e := url.Parse(raw)
			if e != nil || u.Host == "" || u.User != nil || (u.Scheme != "http" && u.Scheme != "https") || u.RawQuery != "" || u.Fragment != "" {
				return c, errors.New("invalid module URL: " + m)
			}
			c.Modules[m] = strings.TrimRight(raw, "/")
		}
	}
	c.ExecutionRevision = env("DSX_EXECUTION_PROFILE_REVISION", "local-v1")
	c.NamespaceReportRevision = env("DSX_NAMESPACE_REPORT_PROFILE_REVISION", "report-namespace-v1")
	c.SchedulerEnabled = os.Getenv("DSX_SCHEDULER_ENABLED") == "true"
	c.MaxCatchup, _ = strconv.Atoi(env("DSX_MAX_CATCHUP", "10"))
	c.CatchupWindow, e = time.ParseDuration(env("DSX_CATCHUP_WINDOW", "168h"))
	if e != nil {
		return c, e
	}
	c.DispatchWindow, e = time.ParseDuration(env("DSX_DISPATCH_WINDOW", "24h"))
	if e != nil {
		return c, e
	}
	c.JobDeadline, e = time.ParseDuration(env("DSX_JOB_DEADLINE", "48h"))
	if e != nil {
		return c, e
	}
	if c.MaxCatchup < 1 || c.CatchupWindow <= 0 || c.DispatchWindow <= 0 || c.JobDeadline <= c.DispatchWindow {
		return c, errors.New("invalid scheduler/deadline configuration")
	}
	return c, nil
}
func env(k, f string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return f
}
