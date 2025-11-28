# mailer.py
import smtplib, ssl, os, tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import List, Dict, Tuple
from datetime import date, datetime
from collections import defaultdict

import config
# mailer.py 상단
from email.header import Header
COLUMNS = [
    ("source_system", "출처"),
    ("assigned_office", "사업소"),
    ("stage", "단계"),
    ("project_name", "공고명"),
    ("client", "수요기관"),
    ("address", "주소"),
    ("phone_number", "전화"),
    ("model_name", "모델"),
    ("quantity", "수량"),
    ("is_certified", "고효율인증"),
    ("notice_date", "공고일"),
]

def build_subject(office: str, period: Tuple[date, date], count: int) -> str:
    """기간과 공고 건수에 따라 주간/월간/기간별 제목을 동적으로 생성합니다."""
    start, end = period
    days = (end - start).days

    period_display = ""
    # '지난 달' 버튼 등으로 선택된 월간 기간일 경우
    if 28 <= days <= 31:
        period_display = f"{start.month}월 전체, {count}건"
    # '지난 주' 버튼 등으로 선택된 주간 기간일 경우
    else: # 7일 이내의 기간 및 기타 모든 경우
        period_display = f"{start.strftime('%m.%d')}~{end.strftime('%m.%d')}, {count}건"

    return f"[{office}] EERS 입찰공고 알림 ({period_display})"

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def build_rows_html(items: List[Dict]) -> str:
    trs = []
    for n in items:
        link_title = _esc(n.get("project_name") or "")
        link_url   = n.get("detail_link") or ""
        link_html  = f'<a href="{link_url}" target="_blank" rel="noopener">{link_title}</a>' if link_url else link_title
        tds = []
        for key, _title in COLUMNS:
            val = n.get(key)
            if key == "source_system":
                display_val = "나라장터" if str(val) == "G2B" else str(val or '')
            else:
                display_val = str(val or '')
                
            if key == "project_name":
                tds.append(f"<td>{link_html}</td>")
            else:
                tds.append(f"<td>{_esc(display_val)}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return "\n".join(trs)

def build_table_html(items: List[Dict], for_attachment: bool = False) -> str:
    """
    for_attachment: 첨부 파일용 테이블인 경우, 데이터 없을 때 다른 메시지 표시
    """
    thead = "".join([f"<th>{t}</th>" for _k, t in COLUMNS])
    rows  = build_rows_html(items)
    
    no_data_msg = '해당 년도의 누적 공고가 없습니다.' if for_attachment else '해당 기간 신규 공고가 없습니다.'

    return f"""
<table cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;font-size:13px">
  <thead style="background:#f4f6f8">
    <tr>{thead}</tr>
  </thead>
  <tbody>
    {rows if rows else f'<tr><td colspan="{len(COLUMNS)}" style="text-align:center;color:#888">{no_data_msg}</td></tr>'}
  </tbody>
</table>
"""

def build_attachment_html(office: str, year: int, items_annual: List[Dict]) -> Tuple[str, str]:
    """월별 페이지네이션 기능이 포함된 첨부파일 HTML을 생성합니다."""
    
    attach_name = f"[{office}]_{year}년_누적공고.html"
    
    # 월별로 데이터 그룹화
    by_month = defaultdict(list)
    for item in items_annual:
        try:
            month = int(item.get("notice_date", "0-0").split("-")[1])
            by_month[month].append(item)
        except (ValueError, IndexError):
            by_month[0].append(item) # 날짜 파싱 실패 시 '기타'

    # 월별 목차(앵커 링크) 생성
    month_nav = []
    sorted_months = sorted(by_month.keys(), reverse=True)
    for month in sorted_months:
        label = f"{month}월" if month > 0 else "기타"
        month_nav.append(f'<a href="#month-{month}" style="margin-right:10px;">{label} ({len(by_month[month])}건)</a>')
    
    # 월별 테이블 HTML 생성
    monthly_tables = []
    for month in sorted_months:
        label = f"{month}월" if month > 0 else "기타"
        monthly_tables.append(f'<h3 id="month-{month}" style="margin-top: 30px; border-bottom: 1px solid #ccc; padding-bottom: 5px;">{label} 공고</h3>')
        monthly_tables.append(build_table_html(by_month[month], for_attachment=True))

    attach_html = f"""
<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <title>[{office}] {year}년 누적 공고</title>
    <style>
        body{{font-family:Segoe UI,Apple SD Gothic Neo,Malgun Gothic,Arial,sans-serif;line-height:1.5;padding:16px; scroll-behavior: smooth;}}
        h2{{margin:0 0 8px 0}}
        table{{border-collapse:collapse;width:100%;font-size:13px; margin-bottom:20px;}}
        th,td{{border:1px solid #e5e7eb;padding:6px; text-align:left; vertical-align:top;}}
        thead tr{{background:#f4f6f8}}
        a {{color: #007bff; text-decoration:none;}}
        a:hover {{text-decoration:underline;}}
        .nav {{margin-bottom: 20px; padding: 10px; background-color: #f8f9fa; border-radius: 5px;}}
    </style>
</head>
<body>
    <h2>[{_esc(office)}] {year}년 누적 공고 현황</h2>
    <div class="nav">
        {''.join(month_nav)}
    </div>
    {''.join(monthly_tables)}
</body>
</html>
"""
    return attach_name, attach_html


def build_body_html(office: str, period: Tuple[date, date], items_period: List[Dict], items_annual: List[Dict]) -> Tuple[str, str, str, str]:
    """메일 본문, 첨부파일명, 첨부파일내용, 미리보기 텍스트를 반환합니다."""
    period_txt = f"{period[0].isoformat()} ~ {period[1].isoformat()}"
    header = f"""
  <p style="margin:0 0 8px 0">안녕하세요. 대구본부 EERS팀입니다.</p>
  <p style="margin:0 0 12px 0">아래는 <b>[{_esc(office)}]</b>의 <b>[{period_txt}]</b> 기간 내 신규 공고 내역입니다.</p>
"""
    period_table = build_table_html(items_period)
    
    # 첨부파일 생성
    attach_name, attach_html = build_attachment_html(office, period[0].year, items_annual)

    # 관련 사이트 링크
    site_links = """
<p style="margin:20px 0; padding:12px; border:1px solid #eee; background-color:#f9f9f9; font-size:13px;">
    <b>관련 사이트 바로가기:</b><br>
    <a href="https://www.g2b.go.kr/" target="_blank">나라장터</a> | 
    <a href="https://www.k-apt.go.kr/bid/bidList.do" target="_blank">공동주택관리정보시스템(K-APT)</a> | 
    <a href="https://eep.energy.or.kr/higheff/hieff_intro.aspx" target="_blank">에너지공단 효율등급조회</a>
</p>
"""

    body = f"""
<div style="font-family:Segoe UI,Apple SD Gothic Neo,Malgun Gothic,Arial,sans-serif;line-height:1.5">
  {header}
  {period_table}
  {site_links}
  <p style="margin:14px 0 0 0">
    <b style="color:#c00;">[첨부파일]</b>을 열어 <b>[{_esc(office)}]</b>의 {period[0].year}년 전체 누적 공고를 월별로 확인하실 수 있습니다.
  </p>
  <p style="margin:20px 0 0 0;color:#666;font-size:12px">※ 상세정보는 입찰공고 사이트에서 공고명을 검색하여 확인 바랍니다.</p>
</div>
"""

    preview = f"[{office}] {period_txt} / count={len(items_period)}"
    return body, attach_name, attach_html, preview


def send_mail(to_list: List[str], subject: str, html_body: str, attach_name: str, attach_html: str):
    msg = MIMEMultipart("mixed")
    
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = formataddr((str(Header(config.MAIL_FROM_NAME, "utf-8")), config.MAIL_FROM))
    msg["To"]      = ", ".join(to_list)

    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body_part)

    attach_part = MIMEText(attach_html, "html", "utf-8")
    attach_part.add_header(
        "Content-Disposition",
        "attachment",
        filename=("utf-8", "", attach_name)
    )
    msg.attach(attach_part)

    context = ssl.create_default_context()
    with smtplib.SMTP(config.MAIL_SMTP_HOST, config.MAIL_SMTP_PORT, timeout=30) as server:
        server.starttls(context=context)
        server.login(config.MAIL_USER, config.MAIL_PASS)
        server.sendmail(config.MAIL_FROM, to_list, msg.as_string())