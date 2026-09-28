package api

import (
	"github.com/jackc/pgx/v5"
	. "gpu-ops-advisor/backend/internal/contract"
	"gpu-ops-advisor/backend/internal/store"
	"net/http"
	"strconv"
	"time"
)

func (s *Server) knowledgeRecord(q *Request, db store.Queryer, id, revision string) (Object, error) {
	v, e := store.One(q.R.Context(), db, "SELECT to_jsonb(k) FROM knowledge_revisions k WHERE knowledge_id::text=$1 AND revision::text=$2", id, revision)
	if e != nil {
		return nil, e
	}
	return v, nil
}
func knowledgeDTO(v Object) Object { v["revision_id"] = v["id"]; return v }
func (s *Server) knowledge(w http.ResponseWriter, q *Request, parts []string) error {
	ctx := q.R.Context()
	method := q.R.Method
	if len(parts) == 2 && parts[1] == "procedures" && method == "GET" {
		s.write(w, q.ID, 200, Object{"items": []any{}, "next_cursor": nil, "reason": "no_registered_procedures"})
		return nil
	}
	if len(parts) == 1 && method == "GET" {
		if e := onlyQuery(q, "kind", "state", "code", "symptom", "limit", "cursor", "scope"); e != nil {
			return e
		}
		if e := validateList(q); e != nil {
			return e
		}
		scope, e := s.listScope(q)
		if e != nil {
			return e
		}
		v := q.R.URL.Query()
		state := v.Get("state")
		if state == "" {
			state = "published"
		}
		if !Has([]string{"draft", "in_review", "reviewed", "published", "retired"}, state) {
			return Invalid("state")
		}
		return s.page(w, q, "knowledge_revisions", "(visibility='common' OR dsx_scope_contains($1,scope)) AND state=$2 AND ($3='' OR kind=$3) AND ($4='' OR content->>'code'=$4 OR (content->'search'->'codes') ? $4) AND ($5='' OR content::text ILIKE '%'||$5||'%')", []any{scope, state, v.Get("kind"), v.Get("code"), v.Get("symptom")}, knowledgeDTO)
	}
	if len(parts) == 4 && parts[2] == "revisions" && method == "GET" {
		v, e := s.knowledgeRecord(q, s.DB.Pool, parts[1], parts[3])
		if e != nil {
			return e
		}
		s.write(w, q.ID, 200, knowledgeDTO(v))
		return nil
	}
	creating := method == "POST" && (len(parts) == 1 || len(parts) == 3 && parts[2] == "revisions")
	if creating {
		if e := only(q.Body, "knowledge_key", "kind", "visibility", "scope", "content", "compatibility", "source_refs"); e != nil {
			return e
		}
		var result Object
		e := s.DB.Transaction(ctx, func(tx pgx.Tx) error {
			id := ID()
			rev := 1
			key := String(q.Body, "knowledge_key")
			kind := String(q.Body, "kind")
			if len(parts) == 3 {
				old, e := store.One(ctx, tx, "SELECT to_jsonb(k) FROM knowledge_revisions k WHERE knowledge_id::text=$1 ORDER BY revision DESC LIMIT 1", parts[1])
				if e != nil {
					return e
				}
				id = parts[1]
				rev = Number(old, "revision") + 1
				if key != "" && key != String(old, "knowledge_key") || kind != "" && kind != String(old, "kind") {
					return Invalid("immutable_knowledge_key_or_kind")
				}
				key = String(old, "knowledge_key")
				kind = String(old, "kind")
			}
			if key == "" || !Has([]string{"runbook", "policy", "data_dictionary", "reference", "case"}, kind) {
				return Invalid("knowledge_key/kind")
			}
			if e := s.validateKnowledge(q, q.Body, kind); e != nil {
				return e
			}
			revisionID := ID()
			_, e := tx.Exec(ctx, "INSERT INTO knowledge_revisions(id,knowledge_id,knowledge_key,revision,kind,state,visibility,scope,content,content_hash,compatibility,source_refs) VALUES($1,$2,$3,$4,$5,'draft',$6,$7,$8,$9,$10,$11)", revisionID, id, key, rev, kind, q.Body["visibility"], q.Body["scope"], q.Body["content"], Hash(q.Body["content"]), defaultObject(q.Body["compatibility"]), defaultArray(q.Body["source_refs"]))
			if e != nil {
				return e
			}
			result, e = s.knowledgeRecord(q, tx, id, strconv.Itoa(rev))
			if e != nil {
				return e
			}
			return store.Audit(ctx, tx, "unverified", "create_revision", "knowledge", revisionID, q.ID, nil, result)
		})
		if e != nil {
			return e
		}
		s.write(w, q.ID, 201, knowledgeDTO(result))
		return nil
	}
	if len(parts) < 4 || parts[2] != "revisions" || !(method == "PATCH" && len(parts) == 4 || method == "POST" && len(parts) == 5 && Has([]string{"review", "publish", "retire"}, parts[4])) {
		return Fail(404, "NOT_FOUND", "등록되지 않은 지식 API입니다.")
	}
	var result Object
	e := s.DB.Transaction(ctx, func(tx pgx.Tx) error {
		old, e := s.knowledgeRecord(q, tx, parts[1], parts[3])
		if e != nil {
			return e
		}
		if e = match(q, Number(old, "version")); e != nil {
			return e
		}
		state := String(old, "state")
		next := state
		var reviewer any = old["reviewer"]
		var reviewedHash any = old["reviewed_content_hash"]
		var reviewed, published, retired any = old["reviewed_at"], old["published_at"], old["retired_at"]
		content, compatibility, refs, scope, visibility := old["content"], old["compatibility"], old["source_refs"], old["scope"], old["visibility"]
		if method == "PATCH" {
			if e = only(q.Body, "content", "compatibility", "source_refs", "scope", "visibility"); e != nil {
				return e
			}
			if state == "published" || state == "retired" {
				return Fail(409, "IMMUTABLE_REVISION", "발행된 지식은 새 revision으로 변경해 주세요.")
			}
			merged := Object{"content": content, "compatibility": compatibility, "source_refs": refs, "scope": scope, "visibility": visibility}
			for k, v := range q.Body {
				merged[k] = v
			}
			if e = s.validateKnowledge(q, merged, String(old, "kind")); e != nil {
				return e
			}
			content, compatibility, refs, scope, visibility = merged["content"], merged["compatibility"], merged["source_refs"], merged["scope"], merged["visibility"]
			next = "draft"
			reviewer = nil
			reviewed = nil
			reviewedHash = nil
		} else {
			action := parts[4]
			switch action {
			case "review":
				if e = only(q.Body, "action", "comment", "evidence_refs"); e != nil {
					return e
				}
				if String(q.Body, "comment") == "" {
					return Invalid("comment")
				}
				if q.Body["evidence_refs"] != nil {
					if e = s.evidenceRefs(q, q.Body["evidence_refs"], scope, visibility == "common"); e != nil {
						return e
					}
				}
				switch String(q.Body, "action") {
				case "request":
					if state != "draft" {
						return Fail(409, "INVALID_STATE", "초안만 검토 요청할 수 있습니다.")
					}
					next = "in_review"
				case "approve":
					if state != "in_review" {
						return Fail(409, "INVALID_STATE", "검토 중인 지식만 승인할 수 있습니다.")
					}
					if String(old, "kind") == "runbook" {
						if err := validateRunbook(content, compatibility, true); err != nil {
							return err
						}
					}
					next = "reviewed"
					reviewedHash = Hash(content)
					reviewer = "unverified"
					reviewed = time.Now().UTC()
				case "request_changes":
					if state != "in_review" {
						return Fail(409, "INVALID_STATE", "검토 중인 지식에 수정 요청할 수 있습니다.")
					}
					next = "draft"
					reviewer = nil
					reviewed = nil
					reviewedHash = nil
				default:
					return Invalid("action")
				}
			case "publish":
				if e = only(q.Body); e != nil {
					return e
				}
				if state != "reviewed" || String(old, "reviewed_content_hash") != Hash(content) {
					return Fail(409, "REVIEW_REQUIRED", "검토 승인된 revision만 발행할 수 있습니다.")
				}
				if e = s.evidenceRefs(q, refs, scope, visibility == "common"); e != nil {
					return e
				}
				if String(old, "kind") == "runbook" {
					if err := validateRunbook(content, compatibility, true); err != nil {
						return err
					}
				}
				next = "published"
				published = time.Now().UTC()
			case "retire":
				if e = only(q.Body, "reason"); e != nil {
					return e
				}
				if state != "published" {
					return Fail(409, "INVALID_STATE", "발행된 지식만 폐기할 수 있습니다.")
				}
				if String(q.Body, "reason") == "" {
					return Invalid("reason")
				}
				next = "retired"
				retired = time.Now().UTC()
			}
		}
		_, e = tx.Exec(ctx, "UPDATE knowledge_revisions SET state=$2,content=$3,content_hash=$4,compatibility=$5,source_refs=$6,scope=$7,visibility=$8,reviewer=$9,reviewed_at=$10,published_at=$11,retired_at=$12,reviewed_content_hash=$13,version=version+1 WHERE id=$1", old["id"], next, content, Hash(content), compatibility, refs, scope, visibility, reviewer, reviewed, published, retired, reviewedHash)
		if e != nil {
			return e
		}
		result, e = s.knowledgeRecord(q, tx, parts[1], parts[3])
		if e != nil {
			return e
		}
		after := Object{"revision": result, "command": q.Body}
		return store.Audit(ctx, tx, "unverified", method+":"+next, "knowledge", String(old, "id"), q.ID, old, after)
	})
	if e != nil {
		return e
	}
	s.write(w, q.ID, 200, knowledgeDTO(result))
	return nil
}
func defaultObject(v any) any {
	if v == nil {
		return Object{}
	}
	return v
}
func defaultArray(v any) any {
	if v == nil {
		return []any{}
	}
	return v
}
func (s *Server) validateKnowledge(q *Request, b Object, kind string) error {
	visibility := String(b, "visibility")
	if !Has([]string{"common", "scoped"}, visibility) {
		return Invalid("visibility")
	}
	content, ok := b["content"].(map[string]any)
	if !ok || len(content) == 0 {
		return Invalid("content")
	}
	if kind == "runbook" {
		if err := validateRunbook(content, b["compatibility"], false); err != nil {
			return err
		}
	}
	if visibility == "scoped" {
		sc, e := s.scope(q, b["scope"], false)
		if e != nil {
			return e
		}
		b["scope"] = sc
	} else if b["scope"] != nil {
		return Invalid("scope")
	}
	return s.evidenceRefs(q, b["source_refs"], b["scope"], visibility == "common")
}
func (s *Server) evidenceRefs(q *Request, raw, scope any, common bool) error {
	if raw == nil {
		return nil
	}
	refs, e := Decode[[]string](raw)
	if e != nil {
		return Invalid("evidence_refs")
	}
	sc, _ := Decode[Scope](scope)
	for _, id := range refs {
		v, e := s.resource(q, "evidence", id, false)
		if e != nil {
			return e
		}
		refScope, _ := Decode[Scope](v["scope"])
		if common || !Contains(sc, refScope) {
			return Fail(422, "EVIDENCE_SCOPE_MISMATCH", "근거의 공개 범위를 넓힐 수 없습니다.")
		}
	}
	return nil
}
func (s *Server) reviews(w http.ResponseWriter, q *Request, parts []string) error {
	if len(parts) != 1 {
		return Fail(404, "NOT_FOUND", "경로를 찾을 수 없습니다.")
	}
	ctx := q.R.Context()
	if q.R.Method == "GET" {
		if e := onlyQuery(q, "subject_type", "subject_id", "scope", "limit", "cursor"); e != nil {
			return e
		}
		scope, e := s.listScope(q)
		if e != nil {
			return e
		}
		v := q.R.URL.Query()
		return s.page(w, q, "review_records", "dsx_scope_contains($1,scope) AND ($2='' OR subject_type=$2) AND ($3='' OR subject_id::text=$3)", []any{scope, v.Get("subject_type"), v.Get("subject_id")}, nil)
	}
	if q.R.Method != "POST" {
		return Fail(405, "METHOD_NOT_ALLOWED", "허용되지 않은 메서드입니다.")
	}
	b := q.Body
	if e := only(b, "subject_type", "subject_id", "kind", "text", "occurred_at", "evidence_refs", "supersedes_id", "target", "performed_by", "action_summary"); e != nil {
		return e
	}
	subject := String(b, "subject_type")
	if !Has([]string{"incident", "job", "knowledge"}, subject) || !Has([]string{"comment", "review", "action"}, String(b, "kind")) || String(b, "kind") != "action" && String(b, "text") == "" {
		return Invalid("review")
	}
	var resource Object
	var e error
	if subject == "knowledge" {
		resource, e = store.One(ctx, s.DB.Pool, "SELECT to_jsonb(k) FROM knowledge_revisions k WHERE knowledge_id::text=$1 ORDER BY revision DESC LIMIT 1", String(b, "subject_id"))
		if e == nil && String(resource, "visibility") == "common" {
			resource["scope"], e = s.registeredScope(q)
		}
	} else {
		resource, e = s.resource(q, subject+"s", String(b, "subject_id"), false)
	}
	if e != nil {
		return e
	}
	sc, _ := Decode[Scope](resource["scope"])
	var occurred any
	if raw := String(b, "occurred_at"); raw != "" {
		t, e := time.Parse(time.RFC3339Nano, raw)
		if e != nil {
			return Invalid("occurred_at")
		}
		occurred = t.UTC()
	}
	if String(b, "kind") == "action" {
		b["performed_by_verified"] = false
		if occurred == nil || String(b, "performed_by") == "" || String(b, "action_summary") == "" || b["target"] == nil {
			return Invalid("action")
		}
		if e = s.target(q, sc, b["target"], occurred.(time.Time)); e != nil {
			return e
		}
	}
	if e = s.evidenceRefs(q, b["evidence_refs"], resource["scope"], false); e != nil {
		return e
	}
	var supersedes any
	if id := String(b, "supersedes_id"); id != "" {
		v, e := s.resource(q, "reviews", id, false)
		if e != nil {
			return e
		}
		if String(v, "subject_id") != String(b, "subject_id") || String(v, "subject_type") != subject || String(v, "kind") != String(b, "kind") {
			return Invalid("supersedes_id")
		}
		supersedes = id
	}
	var result Object
	e = s.DB.Transaction(ctx, func(tx pgx.Tx) error {
		id := ID()
		_, e := tx.Exec(ctx, "INSERT INTO review_records(id,subject_type,subject_id,kind,author,occurred_at,body,scope,supersedes_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)", id, subject, b["subject_id"], b["kind"], "unverified", occurred, b, sc, supersedes)
		if e != nil {
			return e
		}
		result, e = store.One(ctx, tx, "SELECT to_jsonb(r) FROM review_records r WHERE id=$1", id)
		if e != nil {
			return e
		}
		return store.Audit(ctx, tx, "unverified", "append", "review_records", id, q.ID, nil, result)
	})
	if e != nil {
		return e
	}
	s.write(w, q.ID, 201, result)
	return nil
}
