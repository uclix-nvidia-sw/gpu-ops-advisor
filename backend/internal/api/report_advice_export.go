package api

import (
	. "gpu-ops-advisor/backend/internal/contract"
	"sort"
	"strconv"
	"time"
)

var adviceTitles = map[string]string{
	"capacity_review": "GPU 추가 할당 검토", "schedule_candidate": "작업 시간대 시험 검토", "relative_activity": "작업 시간대 비교·시험 검토", "queue_review": "작업 시작 지연 점검", "batch_progress": "배치 완료·남은 대기 점검", "resident_memory": "GPU 메모리 점유 점검", "repeated_activity": "여러 시간대의 GPU 활동·대기 점검",
}

var adviceColors = map[string]string{
	"capacity_review":    "#245b87",
	"schedule_candidate": "#1b665b",
	"relative_activity":  "#514583",
	"queue_review":       "#8c4a22",
	"batch_progress":     "#526326",
	"resident_memory":    "#7a3f68",
	"repeated_activity":  "#236373",
}

var adviceBases = map[string]string{
	"capacity_review":    "GPU 활동이 높고 대기 Pod도 관측된 구간입니다.",
	"schedule_candidate": "정해둔 낮은 활동 기준에 해당한 구간입니다. 다른 구간과의 비교 결과는 아닙니다.",
	"relative_activity":  "같은 날의 두 구간을 비교한 시험 후보입니다.",
	"queue_review":       "대기 Pod의 노드 배정과 시작 준비 상태를 구분하기 위한 점검입니다.",
	"batch_progress":     "해당 기간의 완료 기록과 대기 변화를 함께 봅니다.",
	"resident_memory":    "GPU 활동률은 낮고 메모리 점유는 높았던 구간입니다.",
	"repeated_activity":  "여러 관측 구간의 활동과 대기를 봅니다. 구간 사이도 같은 상태였다는 뜻은 아닙니다.",
}

type adviceWindow struct{ Label, Time string }
type exportedAdvice struct {
	ID, Title, Summary, Evidence, Conditions, Meaning, NextCheck string
	Kind, Ink, Basis                                             string
	Models                                                       []string
	Trial                                                        bool
	Windows                                                      []adviceWindow
	Refs                                                         any
}
type adviceNamespace struct {
	Namespace string
	Advice    []exportedAdvice
}
type adviceCluster struct {
	Cluster    string
	Namespaces []adviceNamespace
}

// Unknown targets stay separate and sort after named targets.
func adviceNameLess(a, b string) bool {
	if a == "" {
		return false
	}
	if b == "" {
		return true
	}
	return a < b
}

// Use analyzed KST dates, never the report creation date.
func reportDocumentTitle(body Object) string {
	versions, _ := body["versions"].(map[string]any)
	if String(versions, "criteria") != AggregateReportVersion {
		return "GPU 운영 보고서"
	}
	title := "GPU 클러스터 운영 분석 보고서"
	period, _ := body["time_range"].(map[string]any)
	start, e1 := time.Parse(time.RFC3339Nano, String(period, "start"))
	end, e2 := time.Parse(time.RFC3339Nano, String(period, "end"))
	if e1 != nil || e2 != nil || !end.After(start) {
		return title
	}
	zone := time.FixedZone("KST", 9*60*60)
	first, last := start.In(zone).Format("2006년 1월 2일"), end.Add(-time.Nanosecond).In(zone).Format("2006년 1월 2일")
	if first != last {
		first += " ~ " + last
	}
	return first + " " + title
}

func adviceTime(value any) string {
	p, _ := value.(map[string]any)
	start, e1 := time.Parse(time.RFC3339Nano, String(p, "start"))
	end, e2 := time.Parse(time.RFC3339Nano, String(p, "end"))
	if e1 != nil || e2 != nil || !end.After(start) {
		return "시간 범위 미확인"
	}
	kst := time.FixedZone("KST", 9*60*60)
	start, end = start.In(kst), end.In(kst)
	clock := "15:04"
	if start.Second() != 0 || end.Second() != 0 || start.Nanosecond() != 0 || end.Nanosecond() != 0 {
		clock = "15:04:05"
	}
	finish := clock
	if start.Format("2006-01-02") != end.Format("2006-01-02") {
		finish = "2006. 01. 02. " + clock
	}
	return start.Format("2006. 01. 02. "+clock) + " ~ " + end.Format(finish) + " KST"
}

// Copy only the reading view; published narrative and selection remain immutable.
func reportNarrative(body Object) []Object {
	var sections []Object
	source, _ := body["narrative"].([]any)
	versions, _ := body["versions"].(map[string]any)
	for _, raw := range source {
		section, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		view := Object{}
		for k, v := range section {
			view[k] = v
		}
		delete(view, "advice_groups")
		if String(versions, "criteria") == AggregateReportVersion && String(section, "topic_id") == "namespace_usage" {
			items, _ := section["advice"].([]any)
			var groups []adviceCluster
			for _, raw := range items {
				item, ok := raw.(map[string]any)
				if !ok {
					continue
				}
				target, _ := item["target"].(map[string]any)
				cluster, namespace := String(target, "cluster_id"), String(target, "namespace")
				ci := -1
				for i, g := range groups {
					if cluster != "" && g.Cluster == cluster {
						ci = i
						break
					}
				}
				if ci < 0 {
					groups = append(groups, adviceCluster{Cluster: cluster})
					ci = len(groups) - 1
				}
				ni := -1
				for i, n := range groups[ci].Namespaces {
					if namespace != "" && n.Namespace == namespace {
						ni = i
						break
					}
				}
				if ni < 0 {
					groups[ci].Namespaces = append(groups[ci].Namespaces, adviceNamespace{Namespace: namespace})
					ni = len(groups[ci].Namespaces) - 1
				}
				kind := String(item, "kind")
				title := adviceTitles[kind]
				if title == "" {
					title = String(item, "recommendation")
				}
				if title == "" {
					title = "운영 점검"
				}
				a := exportedAdvice{ID: String(item, "fact_id"), Title: title, Summary: String(item, "summary"), Evidence: String(item, "observation"), Conditions: String(item, "conditions"), Meaning: String(item, "meaning"), NextCheck: String(item, "next_check"), Refs: item["evidence_refs"], Trial: kind == "relative_activity" || kind == "schedule_candidate"}
				a.Kind, a.Ink, a.Basis = kind, adviceColors[kind], adviceBases[kind]
				models, _ := item["gpu_models"].([]any)
				for _, model := range models {
					if name, ok := model.(string); ok && name != "" {
						a.Models = append(a.Models, name)
					}
				}
				parts, _ := item["summary_parts"].(map[string]any)
				d, e := String(parts, "decision"), String(parts, "evidence")
				if d != "" && e != "" && (a.Summary == d+" "+e || a.Summary == d+e) {
					a.Summary, a.Evidence = d, e
				}
				switch kind {
				case "relative_activity":
					a.Windows = []adviceWindow{{"비교 구간", adviceTime(item["reference_period"])}, {"낮은 활동 구간", adviceTime(item["period"])}}
				case "repeated_activity":
					periods, _ := item["observed_periods"].([]any)
					for i, p := range periods {
						a.Windows = append(a.Windows, adviceWindow{"관측 구간 " + strconv.Itoa(i+1), adviceTime(p)})
					}
					if len(a.Windows) == 0 {
						a.Windows = []adviceWindow{{"관측 범위 · 연속 관측 아님", adviceTime(item["period"])}}
					}
				default:
					label := "관측 구간"
					if kind == "schedule_candidate" {
						label = "낮은 활동 구간"
					}
					a.Windows = []adviceWindow{{label, adviceTime(item["period"])}}
				}
				groups[ci].Namespaces[ni].Advice = append(groups[ci].Namespaces[ni].Advice, a)
			}
			sort.SliceStable(groups, func(i, j int) bool { return adviceNameLess(groups[i].Cluster, groups[j].Cluster) })
			for _, group := range groups {
				sort.SliceStable(group.Namespaces, func(i, j int) bool {
					return adviceNameLess(group.Namespaces[i].Namespace, group.Namespaces[j].Namespace)
				})
			}
			view["advice_groups"] = groups
		}
		sections = append(sections, view)
	}
	return sections
}

const namespaceAdviceTemplate = `{{define "namespaceAdvice"}}<p>구간 시각은 KST 기준이며 끝 시각은 포함하지 않습니다.</p>{{range .}}<section class="ops-advice-cluster"><h4 class="ops-advice-card-title">AI 운영 해석</h4><p class="ops-advice-cluster-target"><span>대상 클러스터 :</span> <code>{{if .Cluster}}{{.Cluster}}{{else}}미확인{{end}}</code></p>{{range .Namespaces}}<section class="ops-advice-namespace"><h5 class="ops-advice-identity"><span>네임스페이스</span><span aria-hidden="true">:</span><code>{{if .Namespace}}{{.Namespace}}{{else}}미확인{{end}}</code></h5>{{range .Advice}}<article data-advice-id="{{.ID}}"><div class="ops-advice-heading"><h6 class="advice-kind" data-kind="{{.Kind}}" style="color:{{.Ink}}">{{.Title}}</h6>{{if .Trial}}<span class="ops-advice-history">과거 관측</span>{{end}}</div>{{if .Summary}}<p>{{.Summary}}</p>{{else}}<p>{{.Evidence}}</p><p>{{.Meaning}}</p><p>{{.NextCheck}}</p>{{end}}<dl>{{range .Windows}}<div><dt>{{.Label}}</dt><dd>({{.Time}})</dd></div>{{end}}</dl>{{if .Models}}<p class="ops-advice-model">GPU 모델{{range .Models}} · {{.}}{{end}}</p>{{end}}{{if .Trial}}<p class="ops-advice-scope">과거 관측입니다. 향후 시간대 변경은 반복성과 실행 조건을 확인한 뒤 판단하세요.</p>{{end}}<details><summary>판단 근거와 적용 조건</summary>{{if .Basis}}<p class="ops-advice-basis"><strong>해석 기준</strong> {{.Basis}}</p>{{end}}<p><strong>관측 근거</strong> {{.Evidence}}</p>{{if .Conditions}}<p><strong>적용 조건</strong> {{.Conditions}}</p>{{end}}{{if .Trial}}<p>이미 지난 구간입니다. 이후 같은 시간대에도 활동률이 낮은지와 사용 가능한 GPU를 확인한 뒤, 시작 시간을 바꿀 수 있는 작업 일부만 시험할지 판단하세요.</p>{{end}}<p>근거 ID: {{.Refs}}</p></details></article>{{end}}</section>{{end}}</section>{{end}}{{end}}`
