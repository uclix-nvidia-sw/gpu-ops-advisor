package service

import (
	"bytes"
	"encoding/json"
	"errors"
	. "gpu-ops-advisor/shared/contract"
	"io"
	"net"
	"net/url"
	"os"
	"strings"
)

type Policy struct {
	AlertName           string   `json:"alertname"`
	Revision            string   `json:"revision"`
	PurposeIDs          []string `json:"purpose_ids"`
	EvidenceLabels      []string `json:"evidence_labels"`
	EvidenceAnnotations []string `json:"evidence_annotations"`
}
type Config struct {
	Source            string   `json:"grafana_source"`
	ClusterLabel      string   `json:"cluster_label"`
	MaxBodyBytes      int      `json:"max_body_bytes"`
	MaxAlerts         int      `json:"max_alerts"`
	MaxAgeSeconds     int      `json:"max_alert_age_seconds"`
	FutureSeconds     int      `json:"max_future_seconds"`
	BeforeSeconds     int      `json:"window_before_seconds"`
	AfterSeconds      int      `json:"window_after_seconds"`
	DispatchSeconds   int      `json:"dispatch_seconds"`
	DeadlineSeconds   int      `json:"deadline_seconds"`
	ExecutionRevision string   `json:"execution_profile_revision"`
	Policies          []Policy `json:"analysis_policies"`
	JCURL             string   `json:"job_controller_url"`
}

func DefaultConfig() Config {
	return Config{Source: "local-grafana", ClusterLabel: "cluster_id", MaxBodyBytes: 1024 * 1024, MaxAlerts: 200, MaxAgeSeconds: 86400, FutureSeconds: 300, BeforeSeconds: 1800, AfterSeconds: 300, DispatchSeconds: 86400, DeadlineSeconds: 172800, ExecutionRevision: "local-v1", Policies: []Policy{{AlertName: "GPUAlert", Revision: "gpu-alert-v1", PurposeIDs: []string{"R01", "R02"}, EvidenceLabels: []string{"severity"}, EvidenceAnnotations: []string{"error_code"}}}, JCURL: "http://127.0.0.1:8090"}
}
func (c Config) Validate() error {
	if strings.TrimSpace(c.Source) == "" || len(c.Source) > 200 || c.ClusterLabel == "" || c.MaxBodyBytes < 1024 || c.MaxBodyBytes > 8*1024*1024 || c.MaxAlerts < 1 || c.MaxAlerts > 1000 || c.MaxAgeSeconds < 1 || c.FutureSeconds < 0 || c.BeforeSeconds < 1 || c.AfterSeconds < 1 || c.BeforeSeconds+c.AfterSeconds > 366*86400 || c.DispatchSeconds < 1 || c.DeadlineSeconds <= c.DispatchSeconds || c.ExecutionRevision == "" {
		return errors.New("invalid Incident limits/configuration")
	}
	u, e := url.Parse(c.JCURL)
	if e != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" || strings.Trim(u.Path, "/") != "" {
		return errors.New("invalid Job Controller base URL")
	}
	names, revisions := map[string]bool{}, map[string]bool{}
	for _, p := range c.Policies {
		if p.AlertName == "" || p.Revision == "" || len(p.Revision) > 100 || names[p.AlertName] || revisions[p.Revision] || len(p.PurposeIDs) == 0 {
			return errors.New("unique alertname/profile revision required")
		}
		names[p.AlertName] = true
		revisions[p.Revision] = true
		seen := map[string]bool{}
		for _, v := range p.PurposeIDs {
			if seen[v] || !Has([]string{"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"}, v) {
				return errors.New("invalid RCA purpose")
			}
			seen[v] = true
		}
		for _, fields := range [][]string{p.EvidenceLabels, p.EvidenceAnnotations} {
			seen = map[string]bool{}
			for _, v := range fields {
				if v == "" || seen[v] {
					return errors.New("invalid evidence selector")
				}
				seen[v] = true
			}
		}
	}
	return nil
}
func LoadConfig() (Config, error) {
	c := DefaultConfig()
	if path := os.Getenv("INCIDENT_CONFIG_FILE"); path != "" {
		b, e := os.ReadFile(path)
		if e != nil {
			return c, e
		}
		d := json.NewDecoder(bytes.NewReader(b))
		d.DisallowUnknownFields()
		if e = d.Decode(&c); e != nil {
			return c, e
		}
		var extra any
		if d.Decode(&extra) != io.EOF {
			return c, errors.New("one JSON configuration required")
		}
	}
	if v := os.Getenv("INCIDENT_JOB_CONTROLLER_URL"); v != "" {
		c.JCURL = v
	}
	return c, c.Validate()
}
func Address() (string, error) {
	s := os.Getenv("INCIDENT_ADDRESS")
	if s == "" {
		s = "127.0.0.1:8091"
	}
	host, _, e := net.SplitHostPort(s)
	if e != nil {
		return s, e
	}
	ip := net.ParseIP(host)
	if (ip == nil || !ip.IsLoopback()) && os.Getenv("DSX_ALLOW_UNAUTHENTICATED_NETWORK") != "true" {
		return s, errors.New("bind loopback or explicitly opt in to trusted network")
	}
	return s, nil
}
