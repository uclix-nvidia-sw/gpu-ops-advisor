"""Build the standalone Fleet-to-RCA Runbook coverage viewer."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS = ROOT / "rcca-agent/runbooks"
OUTPUT = Path(__file__).with_name("fleet-runbook-coverage.html")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_entries() -> list[dict]:
    manifest = read_json(RUNBOOKS / "catalog-manifest.json")
    entries: list[dict] = []
    for source in manifest["entries"]:
        kind, code = source["code"].split(":", 1)
        event_type = source.get("fleet_event_type")
        if source["code"] == "xid:133":
            route = "Fleet 코드 매핑 없음"
            status = "unsupported"
            claim = False
        elif source["code"] in {"xid:63", "xid:64"}:
            route = "event 조건부; 식별된 GPU가 RowRemapping 지원 시 kmsg 제외; 별도 memory 상태 확인"
            status = "conditional"
            claim = False
        elif event_type in {"Fatal", "Critical"}:
            route = "component_data 상태 (Unhealthy/Degraded); 이벤트는 보조"
            status = "supported"
            claim = True
        else:
            route = "event (Warning/Info); 이벤트 누락 시 상태 대체 없음"
            status = "supported"
            claim = True

        product_scope = ", ".join(
            f"{name} {value}"
            for name, value in source.get("nvidia_products", {}).items()
            if value
        )
        entries.append(
            {
                "code": source["code"],
                "kind": kind,
                "title": source["knowledge_key"],
                "href": f"../../rcca-agent/runbooks/{source['file']}",
                "group": source.get("evidence_group", ""),
                "eventType": event_type or "미지원",
                "logType": (
                    "없음"
                    if source["code"] == "xid:133"
                    else "event + component_data"
                    if event_type in {"Fatal", "Critical"}
                    else "event (조건부)"
                    if source["code"] in {"xid:63", "xid:64"}
                    else "event"
                ),
                "route": route,
                "status": status,
                "claim": claim,
                "legacy": source.get("source_status") == "unused_or_legacy",
                "sourceStatus": source.get("source_status", ""),
                "fleetPresent": source.get("fleet_present", False),
                "products": product_scope,
            }
        )

    for path in sorted((RUNBOOKS / "component").glob("RB-COMPONENT-*.json")):
        document = read_json(path)
        content = document.get("content", {})
        conditions = content.get("decision_policy", {}).get("applies_when", {})
        component = conditions.get("reported_component", path.stem.removeprefix("RB-COMPONENT-"))
        entries.append(
            {
                "code": f"component:{component}",
                "kind": "component",
                "title": document.get("knowledge_key", path.stem),
                "href": f"../../rcca-agent/runbooks/component/{path.name}",
                "group": "component",
                "eventType": "Unhealthy",
                "logType": "component_data",
                "route": "component_data health=Unhealthy; Degraded는 현재 규칙 대상 아님",
                "status": "supported",
                "claim": True,
                "legacy": False,
                "sourceStatus": "component",
                "fleetPresent": True,
                "products": "",
            }
        )

    general_path = RUNBOOKS / "RB-GENERAL-GPU-NODE.json"
    general = read_json(general_path)
    entries.append(
        {
            "code": "general:gpu-node",
            "kind": "general",
            "title": general.get("knowledge_key", "RB-GENERAL-GPU-NODE"),
            "href": "../../rcca-agent/runbooks/RB-GENERAL-GPU-NODE.json",
            "group": "fallback",
            "eventType": "해당 없음",
            "logType": "단독 로그 없음",
            "route": "다른 alert가 발생했을 때 사용하는 일반 조사 fallback",
            "status": "fallback",
            "claim": True,
            "legacy": False,
            "sourceStatus": "fallback",
            "fleetPresent": False,
            "products": "",
        }
    )
    return entries


def main() -> None:
    entries = make_entries()
    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    embedded = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fleet → Loki → Grafana → RCA | Runbook coverage</title>
<style>
:root{color-scheme:light;--ink:#17243a;--muted:#5b6b82;--line:#d9e1ec;--blue:#2165c5;--cyan:#55b7dc;--purple:#8965d4;--amber:#a45b00;--red:#b42332;--bg:#f4f7fb}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Segoe UI",system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:32px 28px 64px}h1{font-size:clamp(26px,4vw,40px);line-height:1.15;margin:0 0 12px;letter-spacing:-.03em}h2{font-size:21px;margin:34px 0 12px}h3{font-size:16px;margin:0 0 8px}.lead{max-width:980px;color:var(--muted);margin:0 0 22px}.source{font-size:12px;color:var(--muted)}a{color:#145cae}.chips{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}.chip,.tag{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:3px 9px;font-size:12px;background:white}.metrics{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px;margin:20px 0}.metric,.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:16px}.metric b{font-size:28px;display:block;letter-spacing:-.03em}.metric span{font-size:13px;color:var(--muted)}.warning{border-left:4px solid #da8b18;background:#fff8e9;padding:14px 16px;border-radius:8px;margin:18px 0}.danger{border-left-color:var(--red);background:#fff1f2}.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:16px;align-items:stretch}.venn{width:100%;height:auto;max-height:340px}.venn text{font-family:inherit;fill:var(--ink);text-anchor:middle}.venn .small{font-size:13px;fill:var(--muted)}.venn .big{font-size:23px;font-weight:750}.flow{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:8px;padding:14px 0}.flow span{background:#edf4ff;border:1px solid #cadaf3;border-radius:9px;padding:9px 12px;font-weight:650}.flow i{font-style:normal;color:#6c7e96}.route{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.route div{border:1px solid var(--line);border-radius:10px;padding:12px}.route p{margin:0;color:var(--muted);font-size:13px}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.controls input,.controls select,.controls button{font:inherit;border:1px solid #bac7d7;background:white;border-radius:8px;padding:9px 11px;color:var(--ink)}.controls input{flex:1;min-width:230px}.controls button{cursor:pointer;background:#173c70;color:white;border-color:#173c70}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px;background:white;max-height:70vh}table{border-collapse:collapse;width:100%;min-width:1050px}th,td{padding:9px 11px;border-bottom:1px solid #e6ebf2;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#eef3f9;font-size:12px;z-index:1}td{font-size:13px}td code{font-size:12px}.tag.supported{color:#11633b;background:#e9f7ef}.tag.conditional{color:var(--amber);background:#fff3dc}.tag.unsupported{color:var(--red);background:#fff0f1}.tag.fallback{color:#455a73;background:#eef2f6}.legacy{color:#744d00;font-weight:650}.foot{color:var(--muted);font-size:13px}.count{font-variant-numeric:tabular-nums}.muted{color:var(--muted)}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}.small-note{font-size:12px;color:var(--muted)}@media(max-width:800px){main{padding:22px 14px}.metrics{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.route{grid-template-columns:1fr}}
</style></head><body><main>
<h1>Fleet → Loki → Grafana Alert → RCA</h1>
<p class="lead">Runbook 284건을 Fleet 로그 타입별 알림 경로에 대조한 검토 화면입니다. 카탈로그에 코드가 있다는 것, 로그가 Loki에 도착하는 것, Grafana가 발화하는 것, 발행된 Runbook으로 RCA가 실행되는 것은 각각 별도 조건입니다.</p>
<p class="source">기준: 현재 저장소의 catalog-manifest.json 및 Runbook 초안, 사용자가 제공한 Xid-Catalog (2).xlsx 대조. Fleet 소스 분류 기준과 운영 배포 상태는 별도 확인이 필요합니다.</p>
<div class="metrics" id="metrics"></div>
<div class="warning danger"><b>281건 수치의 해석:</b> 284−3은 XID 133(매핑 없음), XID 63·64(식별 GPU의 RowRemapping 지원 조건부)를 뺀 수입니다. 다만 281에는 직접 alert를 만들지 않는 일반 GPU Node fallback 1건이 포함됩니다. 따라서 현재 표의 직접 로그 기반 알림 경로는 280건이며, XID 63·64의 proxy 상태는 같은 코드 이벤트가 아닙니다.</div>
<section class="grid"><div class="panel"><h2 style="margin-top:0">XID/SXID 알림 로그 타입 벤 다이어그램</h2><svg class="venn" viewBox="0 0 720 340" role="img" aria-label="Warning Info는 event only, Fatal Critical은 event와 component_data, 비코드 컴포넌트는 component_data">
<circle cx="280" cy="160" r="115" fill="#55b7dc" fill-opacity=".35" stroke="#2684a8" stroke-width="2"/><circle cx="430" cy="160" r="115" fill="#8965d4" fill-opacity=".32" stroke="#7650bb" stroke-width="2"/>
<text x="220" y="90" font-size="16" font-weight="700">event</text><text x="220" y="118" class="big">158</text><text x="220" y="140" class="small">Warning / Info 코드</text><text x="220" y="160" class="small">이벤트 줄에 의존</text>
<text x="355" y="105" class="small">둘 다 발생 가능</text><text x="355" y="140" class="big">107</text><text x="355" y="164" class="small">Fatal / Critical</text><text x="355" y="184" class="small">알림은 상태 줄 우선</text>
<text x="490" y="90" font-size="16" font-weight="700">component_data</text><text x="490" y="118" class="big">17</text><text x="490" y="140" class="small">비코드 컴포넌트</text><text x="490" y="160" class="small">현재 Unhealthy만</text>
<text x="635" y="230" class="small">바깥: XID 133 미지원</text><text x="635" y="251" class="small">+ 일반 fallback 1</text></svg>
<p class="small-note">다이어그램은 manifest의 Fleet event_type과 현재 저장소 alert rule의 주 경로를 나타냅니다. Warning/Info 158건에는 RowRemapping 지원 장치에서 조건부인 XID 63·64가 포함되어 있습니다.</p></div>
<div class="panel"><h2 style="margin-top:0">281개 주장과 엄격한 경계</h2><div class="flow"><span>Fleet</span><i>→</i><span>Loki</span><i>→</i><span>Grafana</span><i>→</i><span>Incident</span><i>→</i><span>RCA</span></div>
<div class="route"><div><h3>상태형 코드</h3><p>Fatal/Critical → component_data health=Unhealthy/Degraded. 1분 반복 상태를 주 알림 경로로 사용합니다.</p></div><div><h3>이벤트형 코드</h3><p>Warning/Info → event. 현재 규칙은 10분 조회 창을 써도 이벤트 자체가 빠지면 복구할 수 없습니다.</p></div><div><h3>비코드 컴포넌트</h3><p>17개 Runbook → component_data Unhealthy. 현재 규칙의 Degraded는 범위 밖이며 의미 검토 없이 추가하면 상시 경고가 생길 수 있습니다.</p></div><div><h3>RCA 연결 조건</h3><p>저장소 284개는 작성 초안입니다. DB 등록·호환성 검토·승인·발행 및 Incident 정책까지 확인해야 코드별 RCA 보고서가 실제 작성됩니다.</p></div></div>
<div class="warning"><b>SXID 12030:</b> manifest상 Warning이라 event 경로입니다. event 줄이 없고 component_data 상태도 나오지 않는다면 Grafana LogQL만으로 알림을 만들 수 없습니다. FM 원본 로그를 Loki로 수집하거나 Fleet이 지속 상태를 내보내도록 producer 경로를 보강해야 합니다.</div></div></section>
<h2>보강 제안</h2><div class="panel"><ol><li><b>Fatal/Critical:</b> 상태 규칙(component_data, XID/SXID health Unhealthy|Degraded)을 주 경로로 유지합니다. 이벤트 규칙과 중복 발화하지 않도록 severity 분리를 유지합니다.</li><li><b>Warning/Info:</b> event_name=error_xid/error_sxid 기반 이벤트 규칙과 10분 조회 창을 유지합니다. 누락 보완이 목적이라면 FM/kmsg 원본 로그도 Loki에 수집하고, 코드·장치·노드 기준으로 중복을 정리합니다.</li><li><b>파일시스템:</b> 별도 event 조건 `component="disk"`, `event_name="filesystem_read_only"`를 추가합니다. Warning event를 일반 Fatal/Warning 코드 필터에 기대지 않습니다.</li><li><b>검증/배포:</b> 실제 배포된 Fleet 버전·컴포넌트 로그 형식·Grafana 규칙·Incident 정책·DB 발행 Runbook을 같은 시험 이벤트로 끝까지 확인합니다.</li></ol>
<details><summary>Warning/Info XID·SXID 이벤트 규칙 예시</summary><pre><code>sum by (cluster_id, component, event_type, code, device, reason, k8s_node_name, machine_id) (
  count_over_time(
    {cluster_id=~".+", job="fleet-intelligence-agent"}
      | json log_type=`attributes["log_type"]`, component=`attributes["component"]`,
             event_name=`attributes["event_name"]`, event_type=`attributes["event_type"]`,
             xid=`attributes["extra_info"]["data"]["xid"]`, sxid=`attributes["extra_info"]["data"]["sxid"]`,
             device=`attributes["extra_info"]["device_uuid"]`, reason=`body`,
             k8s_node_name=`resources["k8s.node.name"]`, machine_id=`resources["machine.id"]`
      | __error__="" | log_type="event" | event_name=~"error_(xid|sxid)" | machine_id!=""
      | label_format code=`{{ if .xid }}xid:{{ .xid }}{{ else }}sxid:{{ .sxid }}{{ end }}`
      | event_type!~"Fatal|Critical"
    [10m]
  )
)</code></pre><p class="small-note">이벤트 수집 지연에 여유를 주는 창입니다. Fleet이 event 줄을 만들거나 내보내지 않은 경우를 보완하지 않습니다. 그 경우엔 원본 kmsg/FM 로그의 Loki 수집 또는 Fleet 상태 producer 변경이 필요합니다.</p></details>
<details><summary>파일시스템 read-only 이벤트 조건 예시</summary><pre><code>sum by (cluster_id, component, reason, k8s_node_name, machine_id) (
  count_over_time(
    {cluster_id=~".+", job="fleet-intelligence-agent"}
      | json log_type=`attributes["log_type"]`, event_name=`attributes["event_name"]`,
             component=`attributes["component"]`, reason=`body`,
             k8s_node_name=`resources["k8s.node.name"]`, machine_id=`resources["machine.id"]`
      | __error__="" | log_type="event" | component="disk"
      | event_name="filesystem_read_only" | machine_id!=""
    [10m]
  )
)</code></pre></details>
<p class="foot">저장소 규칙 정의는 incident/grafana/alert-rules.yaml에 3개 규칙(state, XID/SXID event, component)이 있습니다. 사용자가 붙인 2-분기 규칙은 별도 배포 상태이므로 둘을 동일한 것으로 간주하지 마세요.</p></div>
<h2>Runbook 전체 284건</h2><p class="foot">검색 및 필터를 적용할 수 있습니다. `Unused / legacy`는 제공된 XID 표의 Description=Unused 63건과 저장소 manifest의 legacy 63건이 코드 단위로 일치한 표시입니다. 사용 중지·삭제를 뜻하지 않으며 GPU 세대/드라이버와 실제 producer를 확인해야 합니다.</p>
<div class="controls"><input id="search" placeholder="코드, Runbook, 컴포넌트 검색"><select id="status"><option value="">모든 상태</option><option value="supported">지원 경로</option><option value="conditional">조건부</option><option value="unsupported">Fleet 미지원</option><option value="fallback">fallback</option></select><select id="logtype"><option value="">모든 로그 타입</option><option value="event">event 포함</option><option value="component_data">component_data 포함</option><option value="단독 로그 없음">독립 로그 없음</option></select><label class="chip"><input type="checkbox" id="legacy"> Unused / legacy만</label><button id="csv">현재 결과 CSV</button></div>
<p id="shown" class="small-note"></p><div class="table-wrap"><table><thead><tr><th>유형 / 코드</th><th>Runbook</th><th>Fleet / 경로 상태</th><th>주요 log type</th><th>event type / 조건</th><th>분류</th><th>XID 제품 표기</th><th>근거</th></tr></thead><tbody id="rows"></tbody></table></div>
<h2>분류 근거와 제한</h2><ul class="foot"><li>최신 저장소 `catalog-manifest.json`은 XID 173 + SXID 93(266개)과 component 17개, general 1개를 합해 284개를 기록합니다.</li><li>첨부 XID-Catalog 시트는 XID 172행이며 `Description=Unused`가 63건입니다. 같은 63개 코드가 현재 runbook manifest에서 `unused_or_legacy`로 표시됩니다. XID 173은 첨부 표 범위 밖이며 NVIDIA 드라이버 nverror.h에도 C2C_FATAL_LINK_FAILURE로 정의됩니다.</li><li>XID 133은 manifest에서 `fleet_present=false`, event_type 없음입니다. 고정 Fleet commit 84f99be의 실제 Match→GetDetail 경로에서 XID 133은 details 매핑이 없어 제외됩니다. 별도 generated catalog에 숫자가 있다는 것과 실행 매핑은 다릅니다. XID 63·64는 shouldDiscardRowRemappingXID가 GPU를 식별하고 해당 제품의 RowRemapping 지원을 확인했을 때만 제외합니다. GPU 식별 실패 시에는 보존합니다.</li><li>component_data 건강 로그는 신호입니다. 로그 이벤트가 없어졌거나 RCA Runbook이 DB에서 발행되지 않은 상태를 해결해 주지는 않습니다.</li><li>본 페이지는 저장소/제공 자료 기준 분류이며 실제 운영 클러스터의 Fleet version, Loki 수집, 알림 발화, 보고서 생성을 검증하지 않았습니다.</li></ul>
<p class="source">원문: <a href="../../rcca-agent/runbooks/CATALOG.md">Runbook CATALOG</a> · <a href="../../incident/README.md#grafana-알림-규칙">Incident/Grafana 경로</a> · <a href="../../incident/grafana/alert-rules.yaml">저장소 Grafana 규칙</a> · <a href="../../rcca-agent/runbooks/catalog-manifest.json">Runbook manifest</a> · <a href="https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html">NVIDIA Xid Catalog</a></p>
<script id="coverage-data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('coverage-data').textContent);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const counts={total:data.length,claim:data.filter(x=>x.claim).length,conditional:data.filter(x=>x.status==='conditional').length,legacy:data.filter(x=>x.legacy).length,unsupported:data.filter(x=>x.status==='unsupported').length};
document.getElementById('metrics').innerHTML=[['284','Runbook 전체'],[String(counts.claim),'분류상 경로 (fallback 포함)'],[String(counts.conditional+counts.unsupported),'정확한 코드 경로 예외'],[String(counts.legacy),'XID Unused / legacy']].map(x=>`<div class="metric"><b>${x[0]}</b><span>${x[1]}</span></div>`).join('');
const search=document.getElementById('search'),status=document.getElementById('status'),logtype=document.getElementById('logtype'),legacy=document.getElementById('legacy'),body=document.getElementById('rows');
function draw(){const q=search.value.toLowerCase();const filtered=data.filter(x=>(!q||[x.code,x.title,x.group,x.route].join(' ').toLowerCase().includes(q))&&(!status.value||x.status===status.value)&&(!logtype.value||x.logType.includes(logtype.value))&&(!legacy.checked||x.legacy));document.getElementById('shown').textContent=`${filtered.length} / ${data.length}개 표시`;
body.innerHTML=filtered.map(x=>`<tr><td><code>${esc(x.code)}</code></td><td><a href="../../rcca-agent/runbooks/CATALOG.md" data-runbook="${esc(x.href)}">${esc(x.title)}</a></td><td><span class="tag ${esc(x.status)}">${({supported:'지원 경로',conditional:'조건부',unsupported:'미지원',fallback:'fallback'})[x.status]}</span><br>${esc(x.route)}</td><td><code>${esc(x.logType)}</code></td><td>${esc(x.eventType)}</td><td>${x.legacy?'<span class="legacy">Unused / legacy</span>':esc(x.sourceStatus||x.group)}<br><span class="muted">${esc(x.group)}</span></td><td>${esc(x.products||'해당 없음')}</td><td>${x.kind==='xid'||x.kind==='sxid'?`<a href="../../rcca-agent/runbooks/CATALOG.md" data-runbook="${esc(x.href)}">Runbook JSON</a>`:esc(x.kind)}</td></tr>`).join('')}
[body].forEach(el=>el.addEventListener('click',ev=>{const a=ev.target.closest('a[data-runbook]');if(a){ev.preventDefault();location.href=a.dataset.runbook}}));
[search,status,logtype,legacy].forEach(e=>e.addEventListener('input',draw));document.getElementById('csv').addEventListener('click',()=>{const trs=[...body.querySelectorAll('tr')].map(tr=>[...tr.querySelectorAll('td')].map(td=>'"'+td.innerText.replace(/"/g,'""')+'"').join(','));const blob=new Blob(['\ufeff'+['유형/코드,Runbook,Fleet/경로 상태,log type,event type,분류,XID 제품 표기,근거',...trs].join('\r\n')],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='fleet-runbook-coverage.csv';a.click();URL.revokeObjectURL(a.href)});draw();
</script></main></body></html>'''.replace("__DATA__", embedded)
    OUTPUT.write_text(page, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT} with {len(entries)} entries")


if __name__ == "__main__":
    main()
