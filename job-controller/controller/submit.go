package controller

import (
	"context"
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/shared/contract"
	"sort"
	"strings"
	"time"
)

func normalize(kind string, b Object) error {
	if e := only(b, "contract_version", "source_module", "source_key", "kind", "input", "deadline_at", "execution_profile_revision", "dispatch_deadline", "snapshot_ref"); e != nil {
		return e
	}
	version := String(b, "contract_version")
	if !supportedContract(kind, version) || b["kind"] != kind {
		return Invalid("contract_version/kind")
	}
	if kind == "report" && b["source_module"] != "backend" || kind == "rca" && b["source_module"] != "incident" {
		return Fail(422, "source_kind_mismatch", "생산자와 작업 종류가 일치하지 않습니다.")
	}
	key := String(b, "source_key")
	if len(key) < 1 || len(key) > 512 || strings.TrimSpace(key) != key {
		return Invalid("source_key")
	}
	for _, k := range []string{"deadline_at", "dispatch_deadline"} {
		if k == "dispatch_deadline" && b[k] == nil {
			continue
		}
		t, e := time.Parse(time.RFC3339Nano, String(b, k))
		if e != nil {
			return Invalid(k)
		}
		b[k] = t.UTC().Format(time.RFC3339Nano)
	}
	if b["dispatch_deadline"] != nil && (b["snapshot_ref"] == nil || instant(b, "dispatch_deadline").After(instant(b, "deadline_at"))) {
		return Invalid("dispatch_deadline/snapshot_ref")
	}
	if (kind == "rca" || strings.HasPrefix(key, "schedule:")) && b["dispatch_deadline"] == nil {
		return Invalid("dispatch_deadline")
	}
	input, ok := b["input"].(map[string]any)
	if !ok {
		return Invalid("input")
	}
	scope, e := ParseScope(input["scope"])
	if e != nil {
		return e
	}
	input["scope"] = scope
	if kind == "report" {
		if e = only(input, "scope", "time_range", "timezone", "topic_ids", "group_by", "comparison_range", "action_record_ids", "resource_selectors", "parent_job_id"); e != nil {
			return e
		}
		if e = TimeRange(input["time_range"], 366*24*time.Hour); e != nil {
			return e
		}
		if input["comparison_range"] != nil {
			if e = TimeRange(input["comparison_range"], 366*24*time.Hour); e != nil {
				return e
			}
		}
		if String(input, "timezone") == "" {
			return Invalid("timezone")
		}
		if _, e = time.LoadLocation(String(input, "timezone")); e != nil {
			return Invalid("timezone")
		}
		for _, k := range []string{"topic_ids", "group_by"} {
			values, err := Decode[[]string](input[k])
			if err != nil || len(values) == 0 {
				return Invalid(k)
			}
			seen := map[string]bool{}
			allowed := []string{"cluster", "model", "node", "namespace", "pod", "workload"}
			if k == "topic_ids" {
				allowed = []string{"O01", "O02", "O03", "O04", "O05", "O06", "O07", "O08", "O09", "O10", "O11"}
			}
			for _, v := range values {
				if seen[v] || !Has(allowed, v) {
					return Invalid(k)
				}
				seen[v] = true
			}
			if k == "topic_ids" {
				sort.Strings(values)
			}
			input[k] = values
		}
	} else {
		if e := normalizeRCA(input, version); e != nil {
			return e
		}
		if version == "1.4" {
			ref, ok := b["snapshot_ref"].(map[string]any)
			if key != "incident:"+String(input, "incident_id")+":first" || !ok || len(ref) != 2 || ref["incident_id"] != input["incident_id"] || !integer(ref, "revision") || Number(ref, "revision") != 1 {
				return Invalid("source_key/snapshot_ref")
			}
		}
	}
	return nil
}

// RCA execution inputs must remain tied to the Incident module's immutable evidence revision.
func normalizeRCA(input Object, version string) error {
	keys := []string{"scope", "incident_id", "evidence_version", "target", "incident_time", "time_range"}
	if version == "1.3" {
		keys = append(keys, "analysis_profile_revision", "purpose_ids")
	} else {
		keys = append(keys, "prior_incident_id")
	}
	if e := only(input, keys...); e != nil {
		return e
	}
	if !uuid(String(input, "incident_id")) || !integer(input, "evidence_version") || version == "1.3" && String(input, "analysis_profile_revision") == "" {
		return Invalid("incident_snapshot")
	}
	if e := TimeRange(input["time_range"], 366*24*time.Hour); e != nil {
		return e
	}
	at, e := time.Parse(time.RFC3339Nano, String(input, "incident_time"))
	if e != nil {
		return Invalid("incident_time")
	}
	input["incident_time"] = at.UTC().Format(time.RFC3339Nano)
	if target, exists := input["target"]; exists {
		m, ok := target.(map[string]any)
		if !ok || len(m) == 0 {
			return Invalid("target")
		}
	}
	if version == "1.4" {
		if Number(input, "evidence_version") != 1 {
			return Invalid("evidence_version")
		}
		if _, exists := input["prior_incident_id"]; exists && (!uuid(String(input, "prior_incident_id")) || input["prior_incident_id"] == input["incident_id"]) {
			return Invalid("prior_incident_id")
		}
		return nil
	}
	purposes, e := Decode[[]string](input["purpose_ids"])
	if e != nil || len(purposes) == 0 {
		return Invalid("purpose_ids")
	}
	seen := map[string]bool{}
	for _, p := range purposes {
		if seen[p] || !Has([]string{"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"}, p) {
			return Invalid("purpose_ids")
		}
		seen[p] = true
	}
	sort.Strings(purposes)
	input["purpose_ids"] = purposes
	return nil
}
func (c *Controller) submit(ctx context.Context, kind string, b Object) (Object, error) {
	if e := normalize(kind, b); e != nil {
		return nil, e
	}
	hash := Hash(b)
	var result Object
	e := c.transaction(ctx, func(tx pgx.Tx, now time.Time) error {
		old, err := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE source_module=$1 AND source_key=$2 FOR UPDATE", b["source_module"], b["source_key"])
		if err == nil {
			if old["request_hash"] != hash {
				return Fail(409, "idempotency_conflict", "같은 키의 입력이 다릅니다.")
			}
			result = publicJob(old)
			return nil
		}
		if p, ok := err.(*Problem); !ok || p.Status != 404 {
			return err
		}
		if !instant(b, "deadline_at").After(now) || b["dispatch_deadline"] != nil && !instant(b, "dispatch_deadline").After(now) {
			return Fail(422, "deadline_exceeded", "접수 마감이 지났습니다.")
		}
		profile, ok := c.Config.Execution[String(b, "execution_profile_revision")]
		if !ok {
			return Invalid("execution_profile_revision")
		}
		input := b["input"].(map[string]any)
		scope, _ := Decode[Scope](input["scope"])
		for _, sc := range scope.Clusters {
			var exists bool
			if err = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM cluster_registry WHERE id=$1 AND enabled)", sc.ClusterID).Scan(&exists); err != nil {
				return err
			}
			if !exists {
				return Invalid("scope.cluster_id")
			}
		}
		var incident any
		var evidence any
		if kind == "rca" {
			incident = input["incident_id"]
			evidence = Number(input, "evidence_version")
			snapshot, err := one(ctx, tx, "SELECT jsonb_build_object('snapshot',v.snapshot,'content_hash',v.content_hash,'scope',i.scope) FROM incident_evidence_versions v JOIN incidents i ON i.id=v.incident_id WHERE v.incident_id::text=$1 AND v.revision=$2", incident, evidence)
			if err != nil {
				if missing(err) {
					return Invalid("incident_snapshot")
				}
				return err
			}
			original, _ := Decode[Scope](snapshot["scope"])
			if !Contains(scope, original) || !Contains(original, scope) {
				return Invalid("incident_scope")
			}
			rawSnapshot, ok := snapshot["snapshot"].(map[string]any)
			if !ok || Hash(rawSnapshot) != snapshot["content_hash"] {
				return Invalid("incident_snapshot_hash")
			}
			frozen, err := Decode[Object](rawSnapshot["input"])
			if err != nil || frozen == nil {
				return Invalid("incident_snapshot.input")
			}
			frozenScope, err := ParseScope(frozen["scope"])
			if err != nil {
				return err
			}
			frozen["scope"] = frozenScope
			if err = normalizeRCA(frozen, String(b, "contract_version")); err != nil {
				return err
			}
			if Hash(frozen) != Hash(input) {
				return Fail(422, "snapshot_mismatch", "사건의 고정된 증거 입력과 일치하지 않습니다.")
			}
			// Preserve the actual immutable incident evidence in the claimed input.
			input["incident_snapshot"] = rawSnapshot
		}
		var parent any
		if v := String(input, "parent_job_id"); v != "" {
			if !uuid(v) {
				return Invalid("parent_job_id")
			}
			old, err := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id::text=$1 AND kind='report'", v)
			if err != nil {
				if missing(err) {
					return Invalid("parent_job_id")
				}
				return err
			}
			original, _ := Decode[Scope](old["scope"])
			if !Contains(scope, original) || !Contains(original, scope) {
				return Invalid("parent_scope")
			}
			parent = v
		}
		versions := Object{}
		for k, v := range c.Config.Versions {
			versions[k] = v
		}
		versions["execution"] = profile
		versions["input_contract"] = b["contract_version"]
		versions["execution_profile_revision"] = b["execution_profile_revision"]
		versions["result_schema"] = profile.Schema
		versions["source_snapshot_ref"] = b["snapshot_ref"]
		var model any
		err = tx.QueryRow(ctx, "SELECT config->$1 FROM service_profiles WHERE kind='routing' AND name='model-routes'", kind).Scan(&model)
		if err != nil && err != pgx.ErrNoRows {
			return err
		}
		versions["model"] = model
		knowledge := []Object{}
		rows, err := tx.Query(ctx, "SELECT knowledge_id::text,revision,content_hash FROM knowledge_revisions WHERE state='published' AND (visibility='common' OR dsx_scope_contains($1,scope)) ORDER BY knowledge_id,revision", scope)
		if err != nil {
			return err
		}
		for rows.Next() {
			var id, hash string
			var rev int
			if err = rows.Scan(&id, &rev, &hash); err != nil {
				rows.Close()
				return err
			}
			knowledge = append(knowledge, Object{"knowledge_id": id, "revision": rev, "content_hash": hash})
		}
		err = rows.Err()
		rows.Close()
		if err != nil {
			return err
		}
		versions["knowledge"] = knowledge
		id := ID()
		_, err = tx.Exec(ctx, "INSERT INTO jobs(id,kind,source_module,source_key,scope,input_snapshot,request_hash,versions,incident_id,evidence_version,parent_job_id,status,stage,eligible_at,deadline_at,max_attempts,token_budget) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'queued','queued',$12,$13,$14,$15)", id, kind, b["source_module"], b["source_key"], scope, input, hash, versions, incident, evidence, parent, now, instant(b, "deadline_at"), profile.MaxAttempts, profile.TokenBudget)
		if err != nil {
			return err
		}
		if err = c.reasons(ctx, tx, now); err != nil {
			return err
		}
		job, err := one(ctx, tx, "SELECT to_jsonb(j) FROM jobs j WHERE id=$1", id)
		result = publicJob(job)
		return err
	})
	return result, e
}
