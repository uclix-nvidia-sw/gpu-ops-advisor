package api

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
)

func profileDTO(v Object) Object {
	out := Object{}
	if c, ok := v["config"].(map[string]any); ok {
		for k, v := range c {
			out[k] = v
		}
	}
	for _, k := range []string{"id", "name", "kind", "version", "enabled", "created_at", "updated_at", "secret_ref"} {
		out[k] = v[k]
	}
	out["revision"] = v["version"]
	return out
}
func (s *Server) profile(ctx context.Context, q store.Queryer, kind, id string) (Object, error) {
	if kind == "model" {
		return store.One(ctx, q, "SELECT to_jsonb(p) FROM service_profiles p WHERE kind='model' AND id::text=$1", id)
	}
	return store.One(ctx, q, "SELECT to_jsonb(p) FROM service_profiles p WHERE kind=$1 AND name=$2", kind, id)
}
func (s *Server) profiles(w http.ResponseWriter, q *Request, parts []string) error {
	method := q.R.Method
	kind := parts[0]
	ctx := q.R.Context()
	category, name := "model", ""
	if len(parts) > 1 {
		name = parts[1]
	}
	if kind == "model-routes" {
		category = "routing"
		name = "model-routes"
		if len(parts) != 1 {
			return Fail(404, "NOT_FOUND", "경로를 찾을 수 없습니다.")
		}
	}
	if kind == "settings" {
		category = "settings"
		if !Has([]string{"C02", "C03", "C04", "C06"}, name) {
			return Fail(404, "not_found", "등록된 관측·모델 설정만 제공합니다.")
		}
		if len(parts) != 2 {
			return Fail(404, "NOT_FOUND", "프로필 ID가 필요합니다.")
		}
	}
	if kind == "models" && len(parts) == 1 && method == "GET" {
		if e := onlyQuery(q, "limit", "cursor"); e != nil {
			return e
		}
		return s.page(w, q, "service_profiles", "kind='model'", nil, profileDTO)
	}
	if kind == "models" && len(parts) == 3 && parts[2] == "test-connection" && method == "POST" {
		v, e := s.profile(ctx, s.DB.Pool, "model", name)
		if e != nil {
			return e
		}
		if e = match(q, Number(v, "version")); e != nil {
			return e
		}
		return s.connection(w, q, v)
	}
	if len(parts) > 2 {
		return Fail(404, "NOT_FOUND", "경로를 찾을 수 없습니다.")
	}
	if method == "GET" {
		v, e := s.profile(ctx, s.DB.Pool, category, name)
		if e != nil {
			return e
		}
		s.write(w, q.ID, 200, profileDTO(v))
		return nil
	}
	if method != "PATCH" && !(kind == "models" && len(parts) == 1 && method == "POST") {
		return Fail(405, "METHOD_NOT_ALLOWED", "허용되지 않은 메서드입니다.")
	}
	var result Object
	e := s.DB.Transaction(ctx, func(tx pgx.Tx) error {
		var old Object
		var e error
		creating := method == "POST"
		if !creating {
			old, e = s.profile(ctx, tx, category, name)
			if e != nil {
				return e
			}
			if e = match(q, Number(old, "version")); e != nil {
				return e
			}
		}
		config := Object{}
		if old != nil {
			if c, ok := old["config"].(map[string]any); ok {
				for k, v := range c {
					config[k] = v
				}
			}
		}
		for k, v := range q.Body {
			config[k] = v
		}
		id := ID()
		version := 1
		enabled := true
		profileName := String(q.Body, "name")
		secretRef := ""
		if old != nil {
			id = String(old, "id")
			version = Number(old, "version") + 1
			enabled, _ = old["enabled"].(bool)
			profileName = String(old, "name")
			secretRef = String(old, "secret_ref")
		}
		if n := String(q.Body, "name"); n != "" {
			profileName = n
		}
		if raw, ok := q.Body["enabled"]; ok {
			b, ok := raw.(bool)
			if !ok {
				return Invalid("enabled")
			}
			enabled = b
		}
		if raw, ok := q.Body["secret_ref"]; ok {
			v, ok := raw.(string)
			if !ok {
				return Invalid("secret_ref")
			}
			secretRef = v
		}
		if category == "model" {
			if e = only(q.Body, "name", "endpoint_url", "model_name", "artifact_revision", "engine_revision", "precision", "secret_ref", "enabled", "capabilities", "limits_profile_id"); e != nil {
				return e
			}
			config["name"] = profileName
			if creating {
				if profileName == "" {
					profileName = String(config, "model_name")
					config["name"] = profileName
				}
				if _, ok := config["limits_profile_id"]; !ok {
					config["limits_profile_id"] = "C07"
				}
				if _, ok := config["capabilities"]; !ok {
					config["capabilities"] = Object{}
				}
			}
			for _, k := range []string{"name", "endpoint_url", "model_name", "limits_profile_id"} {
				if String(config, k) == "" {
					return Invalid(k)
				}
			}
			for _, k := range []string{"name", "artifact_revision", "engine_revision", "precision"} {
				if raw, exists := q.Body[k]; exists {
					if _, ok := raw.(string); !ok {
						return Invalid(k)
					}
				}
			}
			if _, e = s.modelURL(String(config, "endpoint_url")); e != nil {
				return e
			}
			if _, ok := config["capabilities"].(map[string]any); !ok {
				return Invalid("capabilities")
			}
			var hasLimits bool
			e = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM service_profiles WHERE kind='limits' AND (id::text=$1 OR name=$1) AND enabled)", String(config, "limits_profile_id")).Scan(&hasLimits)
			if e != nil {
				return e
			}
			if !hasLimits {
				return Invalid("limits_profile_id")
			}
			if !enabled {
				var used bool
				e = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM service_profiles p, jsonb_each(p.config) r WHERE p.kind='routing' AND r.value->>'model_id'=$1)", id).Scan(&used)
				if e != nil {
					return e
				}
				if used {
					return Fail(409, "MODEL_IN_USE", "라우팅에서 사용 중인 모델입니다. 대체 모델을 먼저 지정해 주세요.")
				}
			}
		} else if category == "routing" {
			if e = only(q.Body, "rca", "report"); e != nil {
				return e
			}
			delete(config, "default")
			delete(config, "assistant")
			for role, raw := range config {
				if raw == nil && true {
					delete(config, role)
					continue
				}
				ref, ok := raw.(map[string]any)
				if !ok || only(ref, "model_id", "model_revision") != nil {
					return Invalid(role)
				}
				model, e := s.profile(ctx, tx, "model", String(ref, "model_id"))
				if e != nil {
					return Invalid(role)
				}
				exists := Number(ref, "model_revision") == Number(model, "version")
				if !exists && Number(ref, "model_revision") > 0 {
					e = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM profile_revisions WHERE profile_id::text=$1 AND revision=$2)", String(ref, "model_id"), Number(ref, "model_revision")).Scan(&exists)
					if e != nil {
						return e
					}
				}
				if model["enabled"] != true || !exists {
					return Invalid(role + ".model_revision")
				}
			}
		} else {
			if e = only(q.Body, "enabled", "description", "poll_interval_ms", "max_backoff_ms"); e != nil {
				return e
			}
			for _, k := range []string{"poll_interval_ms", "max_backoff_ms"} {
				if _, ok := config[k]; ok && Number(config, k) <= 0 {
					return Invalid(k)
				}
			}
		}
		delete(config, "secret_ref")
		delete(config, "enabled")
		delete(config, "name")
		if old != nil {
			if _, e = tx.Exec(ctx, "INSERT INTO profile_revisions(profile_id,revision,snapshot) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", id, Number(old, "version"), old); e != nil {
				return e
			}
		}
		if creating {
			_, e = tx.Exec(ctx, "INSERT INTO service_profiles(id,kind,name,config,secret_ref,version,enabled) VALUES($1,$2,$3,$4,NULLIF($5,''),$6,$7)", id, category, profileName, config, secretRef, version, enabled)
		} else {
			_, e = tx.Exec(ctx, "UPDATE service_profiles SET name=$2,config=$3,secret_ref=NULLIF($4,''),version=$5,enabled=$6,updated_at=now() WHERE id=$1", id, profileName, config, secretRef, version, enabled)
		}
		if e != nil {
			return e
		}
		result, e = store.One(ctx, tx, "SELECT to_jsonb(p) FROM service_profiles p WHERE id=$1", id)
		if e != nil {
			return e
		}
		if _, e = tx.Exec(ctx, "INSERT INTO profile_revisions(profile_id,revision,snapshot) VALUES($1,$2,$3)", id, version, result); e != nil {
			return e
		}
		return store.Audit(ctx, tx, "unverified", method, "service_profiles", id, q.ID, old, result)
	})
	if e != nil {
		return e
	}
	status := 200
	if method == "POST" {
		status = 201
	}
	s.write(w, q.ID, status, profileDTO(result))
	return nil
}
func (s *Server) modelURL(raw string) (*url.URL, error) {
	u, e := url.Parse(raw)
	if e != nil || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Scheme != "http" && u.Scheme != "https") || !Has(s.Config.ModelHosts, u.Host) {
		return nil, Fail(422, "MODEL_ENDPOINT_NOT_ALLOWED", "서버에 등록된 모델 목적지만 허용됩니다.")
	}
	return u, nil
}
func (s *Server) connection(w http.ResponseWriter, q *Request, v Object) error {
	if e := only(q.Body, "revision"); e != nil {
		return e
	}
	if Number(q.Body, "revision") != Number(v, "version") {
		return Fail(409, "version_conflict", "검사할 모델 revision이 일치하지 않습니다.")
	}
	config, _ := v["config"].(map[string]any)
	u, e := s.modelURL(String(config, "endpoint_url"))
	if e != nil {
		return e
	}
	ctx, cancel := context.WithTimeout(q.R.Context(), 3*time.Second)
	defer cancel()
	out := Object{"revision": v["version"], "checked_at": time.Now().UTC(), "transport": Object{"status": "failed", "reason": "connection_failed"}, "schema": Object{"status": "not_checked"}}
	ips, lookupErr := net.DefaultResolver.LookupIPAddr(ctx, u.Hostname())
	if lookupErr == nil && len(ips) > 0 {
		valid := true
		allowPrivate := net.ParseIP(u.Hostname()) != nil
		for _, ip := range ips {
			approvedNetwork := allowPrivate
			for _, network := range s.Config.ModelNetworks {
				if network.Contains(ip.IP) {
					approvedNetwork = true
				}
			}
			if ip.IP.IsUnspecified() || ip.IP.IsMulticast() || ip.IP.IsLinkLocalUnicast() || ip.IP.IsLinkLocalMulticast() || (!approvedNetwork && (ip.IP.IsLoopback() || ip.IP.IsPrivate())) {
				valid = false
			}
		}
		if valid {
			port := u.Port()
			if port == "" {
				port = "443"
				if u.Scheme == "http" {
					port = "80"
				}
			}
			address := net.JoinHostPort(ips[0].IP.String(), port)
			transport := &http.Transport{DialContext: func(ctx context.Context, network, _ string) (net.Conn, error) {
				return (&net.Dialer{Timeout: 2 * time.Second}).DialContext(ctx, network, address)
			}}
			defer transport.CloseIdleConnections()
			client := &http.Client{Transport: transport, Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
			u.Path = strings.TrimRight(u.Path, "/") + "/models"
			request, _ := http.NewRequestWithContext(ctx, "GET", u.String(), nil)
			resp, err := client.Do(request)
			if err == nil {
				defer resp.Body.Close()
				out["transport"] = Object{"status": "ok", "http_status": resp.StatusCode}
				out["schema"] = Object{"status": "failed", "reason": "invalid_model_list"}
				data, readErr := io.ReadAll(io.LimitReader(resp.Body, 65537))
				var body Object
				if readErr == nil && len(data) <= 65536 && resp.StatusCode == 200 && json.Unmarshal(data, &body) == nil {
					if list, ok := body["data"].([]any); ok {
						for _, item := range list {
							if m, ok := item.(map[string]any); ok && String(m, "id") == String(config, "model_name") {
								out["schema"] = Object{"status": "ok"}
							}
						}
					}
				}
			}
		} else {
			out["transport"] = Object{"status": "failed", "reason": "destination_not_allowed"}
		}
	}
	e = s.DB.Transaction(q.R.Context(), func(tx pgx.Tx) error {
		return store.Audit(q.R.Context(), tx, "unverified", "test_connection", "service_profiles", String(v, "id"), q.ID, nil, out)
	})
	if e != nil {
		return e
	}
	s.write(w, q.ID, 200, out)
	return nil
}
