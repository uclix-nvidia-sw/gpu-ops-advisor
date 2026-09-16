"""Rebuild the two handoff PDFs from the editable spec and captured prototype screens."""
from pathlib import Path
import re, html
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'pdf';OUT.mkdir(exist_ok=True)
pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFontFamily('Malgun',normal='Malgun',bold='MalgunBold',italic='Malgun',boldItalic='MalgunBold')
INK=colors.HexColor('#203731');GREEN=colors.HexColor('#176b54');MUTED=colors.HexColor('#64756f');LINE=colors.HexColor('#d9e4df');BG=colors.HexColor('#f2f6f4')
URL='https://dsx-agent-studio-20260914.uclick-ljw.chatgpt.site'
STY={
 'body':ParagraphStyle('body',fontName='Malgun',fontSize=9.3,leading=15,spaceAfter=10,textColor=INK,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='Malgun',fontSize=8.3,leading=12,wordWrap='CJK',textColor=INK),
 'h1':ParagraphStyle('h1',fontName='MalgunBold',fontSize=22,leading=30,spaceAfter=20,textColor=GREEN,wordWrap='CJK'),
 'h2':ParagraphStyle('h2',fontName='MalgunBold',fontSize=17,leading=24,spaceAfter=18,textColor=GREEN,wordWrap='CJK'),
 'note':ParagraphStyle('note',fontName='Malgun',fontSize=8.5,leading=13,textColor=MUTED,wordWrap='CJK'),
 'book':ParagraphStyle('book',fontName='Malgun',fontSize=12,leading=19,textColor=INK,wordWrap='CJK'),
 'booksmall':ParagraphStyle('booksmall',fontName='Malgun',fontSize=10.5,leading=17,textColor=MUTED,wordWrap='CJK'),
}
def para(text,style='body'):
    safe=html.escape(text).replace('\n','<br/>')
    return Paragraph(safe,STY[style])

def footer(c,doc):
    w,h=doc.pagesize;c.saveState();c.setStrokeColor(LINE);c.line(42,35,w-42,35)
    c.setFont('Malgun',8);c.setFillColor(MUTED);c.drawString(42,23,'DSX FRONTEND SPEC / v1.0 / 2026-09-16')
    c.drawRightString(w-42,23,str(doc.page));c.restoreState()

def table_rows(lines,width):
    rows=[[c.strip() for c in l.strip().strip('|').split('|')] for l in lines]
    rows=[r for r in rows if not all(re.fullmatch(r'[-: ]+',c) for c in r)]
    n=len(rows[0]);weights={2:[.27,.73],3:[.26,.34,.40],4:[.10,.25,.31,.34]}[n]
    if rows[0][0]=='ID' and n==3:weights=[.11,.39,.50]
    data=[[para(x,'cell') for x in r] for r in rows]
    t=Table(data,colWidths=[width*v for v in weights],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),BG),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,GREEN),('LINEBELOW',(0,1),(-1,-1),.35,LINE),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]))
    return t

spec=ROOT/'DSX_프론트엔드_개발명세_v1.0.md'
lines=spec.read_text(encoding='utf-8').splitlines()
story=[];i=0
while i<len(lines):
    l=lines[i]
    if not l.strip():i+=1;continue
    if l.startswith('# '):
        story.extend([Spacer(1,110),para('DSX / DEVELOPMENT HANDOFF','note'),Spacer(1,16),para('프론트엔드\n개발 명세','h1'),para('v1.0 · 웹 시안 DESIGN 05','h2'),Spacer(1,12)])
    elif l.startswith('## '):
        story.extend([PageBreak(),para(l[3:],'h2')])
    elif l.startswith('|'):
        block=[]
        while i<len(lines) and lines[i].startswith('|'):block.append(lines[i]);i+=1
        story.extend([table_rows(block,A4[0]-84),Spacer(1,13)]);continue
    elif l.startswith('```'):
        code=[];i+=1
        while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
        ps=ParagraphStyle('code',fontName='Malgun',fontSize=8,leading=12,backColor=BG,borderPadding=8,spaceAfter=14)
        story.append(Preformatted('\n'.join(code),ps))
    else:story.append(para(l))
    i+=1
spec_out=OUT/'DSX_프론트엔드_개발명세_v1.0.pdf'
SimpleDocTemplate(str(spec_out),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=44,bottomMargin=49,title='DSX 프론트엔드 개발 명세 v1.0',author='DSX Design',allowSplitting=1).build(story,onFirstPage=footer,onLaterPages=footer)

# Screen book keeps the actual browser captures unmodified; annotations are outside the images.
screens=[
('S01','운영 대시보드','첫 화면에서 지금 볼 대상을 정한다.','요약 카드|열린 사건·수집 지연·GPU 메모리·분석 준비를 분리한다.','우선 검토|장애 원인 후보와 관측 지연을 다른 문제로 안내한다.','이동|사건은 S07, 품질은 S04, 자산은 S02로 이어진다.','S01 → S02 / S04 / S07 / S16'),
('S01-detail','대시보드 하단 · 대상과 추이','선택한 대상과 그래프를 그대로 질문에 연결한다.','대상 선택|Node를 복수 선택하거나 전체 범위를 적용한다.','지표 전환|VRAM·활동·전력을 구분하고 부족한 입력을 표시한다.','연속 작업|그래프 질문은 대상·기간·지표를 S16에 전달한다.','S01 → 선택 범위 S16 / S08'),
('S02','자산·관측 · 장비와 GPU','장비 상태와 수신 상태를 구분해 장치를 좁힌다.','상단 탭|장비·GPU / 작업 연결 / 관측 품질을 나눈다.','Node 목록|모델과 마지막 수신으로 대상 장비를 고른다.','GPU 상세|UUID·모델·관측 시각을 기준으로 동일 장치를 식별한다.','S02 → S03 / S04 / S16'),
('S02-detail','GPU 상세 · 관측과 관계','GPU의 수치, 현재 작업 연결, 같은 Node의 Pod를 구분한다.','관측 영역|VRAM이 높다는 이유로 연산 활동을 확정하지 않는다.','작업 연결|현재 매핑은 확인됐으나 과거 관계·공유 방식은 별도다.','후속 행동|선택 GPU 질문과 원인 조사로 이어간다.','S02 → S16 → 조사 / 분석'),
('S03','작업 연결 · 현재 시점','Pod 배치·GPU 매핑·GPU 활동의 세 축을 나란히 본다.','기준 시각|현재와 사건 시각의 관계를 전환한다.','세 독립 축|bound / matched / insufficient_data를 동시에 표시할 수 있다.','주의할 해석|Pending은 미배치를 의미하지 않고 matched는 전용을 뜻하지 않는다.','S03 → S08 할당 분석 / S16'),
('S03-past','작업 연결 · 과거 근거 부족','사건 시각의 연결이 없을 때 현재 관계로 대신하지 않는다.','과거 관계|unknown과 부족한 근거를 표시한다.','판단 보류|미관측은 할당 해제나 GPU 미사용의 확정이 아니다.','다음 입력|과거 연결의 유효 구간과 활동 표본이 필요하다.','S03 과거 → S04 / 재분석'),
('S04','관측 상태·분석 범위','어떤 근거가 있고 어떤 분석이 가능한지 확인한다.','Node 수신|장비 판단과 마지막 관측을 별도 열에 둔다.','분석 준비|현재 매핑·기간 이력·활동·전력의 품질을 나눈다.','연결 확인|S15에서 소스 경로와 최신 수신 확인 과제를 본다.','S04 → S02 / S15'),
('S05','RCA 조사 목록','알림으로 시작한 조사와 직접 요청을 한곳에서 찾는다.','목록|대상·상태·최근 결과를 중심으로 표시한다.','새 조사|사건 ID 없이도 증상·대상·시간으로 요청한다.','진행과 결과|진행은 S11, 저장된 결과는 S07로 분리한다.','S05 → S06 / S07 / S11'),
('S06','새 RCA 조사','조사할 대상을 고정하고 비동기 작업을 접수한다.','필수 입력|대상 Node, 선택 GPU, 시작·종료 KST, 증상.','검증|종료가 시작보다 늦어야 하며 빈 증상은 접수하지 않는다.','접수 이후|job_id를 받은 뒤 S11에서 실행 단계를 확인한다.','S06 → S11 → S07B'),
('S07','사건 RCA 결과','원인 후보와 판단 근거를 함께 검토한다.','결론과 근거|확인된 사실 / 지지 / 반박·미확인을 구분한다.','고정 범위|사건·GPU·시간·문서 버전을 우측에서 확인한다.','후속 작업|추가 질문, Runbook, 실제 처리 기록. 기록과 회복은 별도다.','S07 → 근거 / S12 / 조치 기록'),
('S07B','직접 요청 조사 결과','사건이 없는 질의를 별도의 조사 결과로 보존한다.','요청 범위|사용자 질문과 작업 ID를 함께 보관한다.','독립 판단|현재 관계 / 영향 미평가 / 원인 미확정.','재분석|새 작업과 이전 작업 연결을 만든다.','S07B → S11 새 작업'),
('S08','운영 분석·보고서','어디를 왜 검토해야 하는지 보고 다음 행동을 선택한다.','주제 카드|관측·할당·반복 사건·에너지를 동일 구조로 검토한다.','분석 상세|사실·해석 이유·근거·부족한 입력·다음 행동.','보고서 연결|선택한 대상과 주제를 S09로 전달한다.','S08 → S09 / S02 / S16'),
('S09','보고서 요청','대상·날짜·주제를 지정해 보고서 작업을 접수한다.','대상과 기간|연결된 분석 대상은 표시하고 보고서 날짜를 별도로 지정한다.','주제 선택|하나 이상 필요. 근거가 부족한 주제도 보류 이유를 보관한다.','실행 방식|일회 실행과 정기 설정을 구분. 시안은 실제 예약 없음.','S09 → S11 → S10'),
('S10','보고서 결과','산출된 내용과 판단을 보류한 내용을 함께 저장한다.','저장 범위|보고서 생성 당시 대상·기간을 유지한다.','주제별 결과|수치가 없으면 0 대신 근거 부족과 다음 입력을 표시한다.','검토|관측 이동·보고서 질문·운영자 의견 저장으로 연결한다.','S10 → S02 / S16 / 검토 기록'),
('S11-queued','작업 이력 · 접수 대기','요청 접수와 분석 완료를 구분한다.','상태 목록|실행 상태와 결과 품질을 다른 열에 둔다.','작업 상세|시도 횟수, 범위·기간, 현재 단계, 진행 기록.','시안 조작|수동 진행 버튼은 검토용. 실제 화면은 서버 상태를 조회한다.','S11 대기 → 실행 → 저장 → 결과'),
('S11','작업 이력 · 실행 중','근거 조회와 모델 대기·결과 저장 단계를 확인한다.','두 대기 구분|작업 큐 대기와 LLM 호출 대기는 다르다.','완료 기준|결과와 근거 저장이 끝나야 완료를 표시한다.','품질 독립|작업 완료여도 결과는 partial / blocked일 수 있다.','S11 → S07B / S10'),
('S11-cancel','작업 이력 · 취소 요청','취소 요청 후 최종 상태를 기다린다.','취소 요청|버튼 클릭만으로 취소 완료를 표시하지 않는다.','경합|완료가 먼저 확정될 수 있다. 서버 최종 상태가 기준이다.','다시 분석|재시도는 같은 작업·새 attempt, 재분석은 새 작업이다.','취소 요청 → 최종 상태 확인'),
('S12','지식·Runbook','분석이 참조한 규칙과 버전·적용 조건을 확인한다.','지식 유형|Runbook / 조사 절차 / 정책 / 참고 / 검증 사례.','출처|공급자 원문과 내부 운영 권고를 구분한다.','순환|실제 처리 → 검증 사례 → 검토 후 발행 버전 개정.','S12 ↔ S07 / S08'),
('S13','연결·설정 · 사내 모델','사내 모델을 이름·주소·모델 ID로 관리한다.','모델 카드|기본·RCA 지정 여부와 실제 연결 미확인을 표시한다.','등록과 수정|IP·port·경로를 입력하는 별도 폼을 연다.','형식 확인|입력 형식 정상과 실제 통신 성공을 구분한다.','S13 → 모델 입력 / S14'),
('S13-edit','사내 모델 입력','로컬 endpoint 지정 기능을 설정 안에 둔다.','주소|protocol + IPv4 + port + base path.','모델 ID|서비스가 사용하는 ID를 별도로 지정한다.','보안 경계|시안은 브라우저 예시 저장. 실제 접속·비밀값 처리는 서버에서 수행한다.','모델 저장 → S13 → S14'),
('S14','질의·Agent별 모델 지정','공통 기본 모델과 두 전문 Agent의 모델을 연결한다.','기본 모델|일반 설명·메뉴 안내·가벼운 조회 설명.','업무별 지정|RCA / 운영보고서가 공통 모델을 상속하거나 별도 모델 사용.','실패 처리|자동 외부 모델 전환 없음. 연결 실패는 명시적으로 안내한다.','질문 → 처리 주체 → 지정 사내 모델'),
('S15','데이터 연결','수집 경로와 분석 준비의 차이를 설정 화면에 드러낸다.','소스별 준비|Mimir / Loki / KSM / 매핑 / 업무 이력.','최신 반영|현재 UUID·Pod UID 연결 확인. Loki 최신 수신은 재확인 대상.','확인 범위|CPC-2 직접 수집 경로를 CPC-1까지 확대해 단정하지 않는다.','S15 ↔ S04'),
('S16','공통 Assistant · 우측 패널','대시보드를 보면서 질문하고 관련 화면으로 이동한다.','전역 버튼|어느 화면에서든 열고 닫는다. 기본 업무 화면은 유지한다.','질문 범위|현재 화면 / 전체 시스템 / 데이터 없이 질문을 명시한다.','결과와 바로가기|처리 주체·근거·범위와 관련 메뉴 이동 버튼을 제공한다.','전체 화면 ↔ S16 ↔ 관련 메뉴'),
('S16-desk','Assistant · 펼친 대화','긴 대화가 필요할 때 동일 대화를 넓게 본다.','대화 연속성|패널과 같은 conversation을 사용한다.','일반·전문 질문|공통 Assistant가 기본, 직접 Agent 지정은 고급 옵션.','복귀|대시보드와 함께 보기로 패널 배치로 돌아간다.','S16 패널 ↔ 펼친 대화'),
('S16-mobile','Assistant · 모바일','작은 화면에서는 대화를 drawer로 표시한다.','모바일 배치|질문 입력과 전송 버튼이 화면 안에 남는다.','본문 보존|닫으면 보고 있던 화면으로 돌아간다.','실제 개발|overlay 포커스 관리와 모바일 키보드 겹침을 별도 검수한다.','390px 시안 / 320-1440px 넘침 검증'),
]

book_out=OUT/'DSX_GUI_화면설계서_v1.0.pdf'
W,H=landscape(A3);c=canvas.Canvas(str(book_out),pagesize=(W,H));c.setTitle('DSX GUI 화면설계서 v1.0');c.setAuthor('DSX Design')
def text(x,y,t,size=12,color=INK,bold=False):
    c.setFillColor(color);c.setFont('MalgunBold' if bold else 'Malgun',size);c.drawString(x,y,t)
def wrapped(x,y,t,w,style='book'):
    p=para(t,style);_,h=p.wrap(w,H);p.drawOn(c,x,y-h);return y-h
def page(title,kicker='SCREEN DESIGN / DESIGN 05'):
    c.setFillColor(colors.white);c.rect(0,0,W,H,fill=1,stroke=0)
    text(38,H-36,'DSX',19,GREEN,True);text(98,H-35,kicker,10,MUTED)
    text(38,H-80,title,25,INK,True)
    c.setStrokeColor(LINE);c.line(38,37,W-38,37)
    text(38,22,'2026-09-16 · v1.0 · 가상 데이터 / 구현 협의용',9,MUTED)
    text(W-65,22,f'{c.getPageNumber():02d}',10,MUTED)
def box(x,y,w,h,title,body):
    c.setFillColor(BG);c.roundRect(x,y-h,w,h,10,fill=1,stroke=0)
    text(x+18,y-29,title,16,GREEN,True);wrapped(x+18,y-47,body,w-36)
page('관제에서 질문하고, 근거를 따라 판단한다.','GUI ROUGH DESIGN / FRONTEND HANDOFF')
wrapped(40,H-130,'운영 대시보드 + 공통 Assistant\nRCA 조사와 운영보고서로 이어지는 DSX GUI',730,'book')
c.drawImage(ImageReader(str(ROOT/'screens/S16.png')),40,180,width=810,height=455.625)
box(878,H-140,272,170,'01  화면 중심','대시보드에서 현황을 보고 필요한 순간에 Assistant를 연다.')
box(878,H-330,272,170,'02  작업 연결','질문 → 조사·보고서 접수 → 진행 확인 → 근거·결과 검토.')
box(878,H-520,272,170,'03  개발 대조','웹·PDF·상세 명세의 화면 번호를 통일한다. API 계약은 별도 합의 대상.')
text(40,133,'웹 시안 열기',13,GREEN,True);c.linkURL(URL,(40,118,180,151),relative=0)
wrapped(40,105,'이 문서는 배치와 연결을 검토하는 화면설계서다. 각 화면의 입력·상태·오류·권한·API 제안은 별도 개발 명세서를 따른다.',800,'booksmall');c.showPage()

page('메뉴 구조 · 업무에 맞춘 7개 진입점','INFORMATION ARCHITECTURE')
cards=[('운영 대시보드','S01\n전체 현황 · 우선 검토 · 추이'),('자산·관측','S02 / S03 / S04\n장비·GPU · 작업 연결 · 품질'),('RCA 조사','S05 / S06 / S07 / S07B\n목록 · 요청 · 사건/직접 조사 결과'),('운영 분석·보고서','S08 / S09 / S10\n분석 · 보고서 요청 · 결과'),('작업 이력','S11\n진행 상태 · 취소 · 재분석'),('지식·Runbook','S12\n발행 지식 · 조건 · 검증 사례'),('연결·설정','S13 / S14 / S15\n사내 모델 · 라우팅 · 데이터')]
for i,(a,b) in enumerate(cards):box(40+(i%4)*285,H-130-(i//4)*185,265,160,a,b)
box(40,300,1120,120,'S16  공통 Assistant','모든 화면의 상단 버튼 → 우측 패널 / 좁은 화면 drawer → 같은 대화 펼치기. 일반 질문과 전문 분석을 하나의 입구에서 연결한다.')
wrapped(40,145,'백엔드의 8개 논리 기능을 메뉴 8개로 옮기지 않는다. 메뉴는 운영자가 찾는 대상과 작업을 기준으로 나눈다. 현재 시안에서 자산·관측은 운영 관리 그룹에 배치돼 있으며, 실제 구현 시 관제 그룹으로 이동해도 화면 ID와 기능은 동일하다.',1110,'booksmall');c.showPage()

page('대표 흐름 · 질문과 작업이 끊기지 않게','PRIMARY USER FLOWS')
flows=[('A  현황 질문','S01 대시보드','S16 공통 질문','관련 메뉴 바로가기','현재 대상·기간을 다음 화면으로 전달'),('B  장애 조사','S02 / S05 대상 선택','S06 조사 요청','S11 진행 → S07B 결과','관계·영향·원인과 근거를 독립적으로 검토'),('C  운영보고서','S08 분석 검토','S09 보고서 요청','S11 진행 → S10 결과','저장 당시 범위와 버전 보존, 운영자 검토'),('D  모델 연결','S13 사내 모델 등록','S14 역할별 지정','S16 질문에 적용','실제 호출은 Backend의 사내망 경계 안에서 수행')]
for i,(title,a,b,d,note) in enumerate(flows):
    y=H-140-i*145;text(42,y,title,16,GREEN,True)
    for k,label in enumerate([a,b,d]):box(42+k*375,y-20,350,67,label,'')
    text(399,y-62,'>',18,MUTED);text(774,y-62,'>',18,MUTED);text(43,y-108,note,11,MUTED)
c.showPage()

for key,title,sub,a,b,d,flow in screens:
    page(title,key.split('-')[0]+' / SCREEN DETAIL')
    wrapped(40,H-108,sub,1080,'booksmall')
    img=ImageReader(str(ROOT/'screens'/f'{key}.png'));iw,ih=img.getSize()
    if key=='S16-mobile':
        image_h=510;image_w=image_h*iw/ih;ix=285;iy=H-160-image_h
    else:
        image_w=850;image_h=image_w*ih/iw;ix=38;iy=H-165-image_h
    c.setStrokeColor(LINE);c.roundRect(ix-1,iy-1,image_w+2,image_h+2,6,stroke=1,fill=0)
    c.drawImage(img,ix,iy,width=image_w,height=image_h)
    y=H-166
    for number,part in enumerate([a,b,d],1):
        h,body=part.split('|',1)
        text(918,y,f'{number:02d}  {h}',14,GREEN,True)
        end=wrapped(918,y-17,body,230,'booksmall');y=min(y-142,end-27)
    wrapped(40,125,'연결  '+flow,1090,'book')
    wrapped(40,89,'캡처는 해당 화면의 대표 뷰포트다. 하단 내용은 웹에서 스크롤해 확인한다. 입력 검증·상태·API·권한은 개발 명세서의 같은 화면 ID를 참조한다.',1090,'booksmall')
    c.showPage()

page('개발 전 합의할 경계','IMPLEMENTATION CHECKPOINTS')
box(40,H-145,540,175,'실행 상태 ≠ 결과 품질','queued / running / succeeded 등 실행 상태와 ready / partial / blocked / not_applicable 품질은 다른 축이다. 완료돼도 판단을 보류할 수 있다.')
box(610,H-145,540,175,'현재 관계 ≠ 과거 관계','현재 GPU UUID·Pod UID 연결은 확인됐다. 기간 분석에는 과거 유효 구간·활동·공유 방식이 더 필요하다.')
box(40,H-350,540,175,'공통 Assistant + 두 전문 Agent','일반 설명과 가벼운 조회는 공통 기능. 긴 조사·보고서는 작업으로 접수해 결과·근거를 저장한다.')
box(610,H-350,540,175,'브라우저 → Backend API','브라우저가 LLM·Mimir·Loki에 직접 접속하지 않는다. 모델 주소는 서버 관리·검증 경계로 전달한다.')
wrapped(40,230,'후속 개발의 시작점',1080,'h2')
wrapped(40,190,'개발 명세서 18장: 구현 순서 / 19장: 인수 테스트 / 20장: 근거 문서.\nAPI 경로와 권한·폴링 정책은 제안이다. 실제 연결 전에 담당자 간 계약을 확정한다.\n현재 웹은 예시 데이터이며, 정기 예약·실제 추론·서버 영속 저장·GPU 제어는 수행하지 않는다.',1080,'book')
c.showPage();c.save()
for file in [book_out,spec_out]:
    r=PdfReader(file);text_content='\n'.join(p.extract_text() or '' for p in r.pages)
    assert '\ufffd' not in text_content
    assert len(text_content)>1000
    print(file.name,len(r.pages),'pages',file.stat().st_size,'bytes')
