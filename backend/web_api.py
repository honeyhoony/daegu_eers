from fastapi import FastAPI, HTTPException, Depends, Cookie
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import sqlite3
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
# 기존 알고리즘 모듈 가져오기
from existing_core.collect_data import run_collectors


# -------------------------------------------------------------
# 1) 기본 설정
# -------------------------------------------------------------
DB_PATH = "./daegu_eers.db"
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

app = FastAPI()


# -------------------------------------------------------------
# 2) 유틸: DB 연결
# -------------------------------------------------------------
def get_db():
    return sqlite3.connect(DB_PATH)


# -------------------------------------------------------------
# 3) 이메일로 OTP 보내기
# -------------------------------------------------------------
def send_otp_email(email: str, code: str):
    msg = MIMEText(f"[한전 대구본부 EERS]\n인증코드: {code}\n(5분 내 입력)")
    msg["Subject"] = "EERS 로그인 인증코드"
    msg["From"] = SMTP_USER
    msg["To"] = email

    server = smtplib.SMTP(SMTP_HOST, 587)
    server.starttls()
    server.login(SMTP_USER, SMTP_PASS)
    server.sendmail(SMTP_USER, email, msg.as_string())
    server.quit()


# -------------------------------------------------------------
# 4) API 입력 모델
# -------------------------------------------------------------
class EmailRequest(BaseModel):
    email: str

class VerifyRequest(BaseModel):
    email: str
    code: str


# -------------------------------------------------------------
# 5) OTP 요청
# -------------------------------------------------------------
@app.post("/auth/request-code")
def request_code(body: EmailRequest):
    db = get_db()
    cursor = db.cursor()

    code = secrets.token_hex(3).upper()  # 6자리 코드
    created_at = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO otp_codes (email, code, created_at)
        VALUES (?, ?, ?)
    """, (body.email, code, created_at))
    db.commit()

    # 이메일 발송
    send_otp_email(body.email, code)

    return {"status": "ok", "message": "인증코드 전송됨"}


# -------------------------------------------------------------
# 6) OTP 검증 → 로그인 토큰 발급
# -------------------------------------------------------------
@app.post("/auth/verify-code")
def verify_code(body: VerifyRequest):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT id FROM otp_codes
        WHERE email = ? AND code = ?
        ORDER BY id DESC LIMIT 1
    """, (body.email, body.code))
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="잘못된 코드")

    # users에 자동 등록
    cursor.execute("SELECT id FROM users WHERE email = ?", (body.email,))
    u = cursor.fetchone()

    if u:
        user_id = u[0]
    else:
        cursor.execute("""
            INSERT INTO users (email, office, created_at)
            VALUES (?, ?, ?)
        """, (body.email, "미정", datetime.now().isoformat()))
        user_id = cursor.lastrowid
        db.commit()

    # 30일 로그인 토큰 생성
    token = secrets.token_hex(16)
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()

    cursor.execute("""
        INSERT INTO login_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, token, expires_at))
    db.commit()

    resp = JSONResponse({"status": "ok", "token": token})
    resp.set_cookie(key="auth_token", value=token, httponly=True, max_age=60 * 60 * 24 * 30)

    return resp


# -------------------------------------------------------------
# 7) 인증 필터
# -------------------------------------------------------------
def require_login(auth_token: str = Cookie(None)):
    if auth_token is None:
        raise HTTPException(status_code=401, detail="로그인 필요")

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT user_id FROM login_tokens
        WHERE token = ? AND expires_at > ?
    """, (auth_token, datetime.now().isoformat()))

    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="세션 만료됨")

    return row[0]  # user_id 반환


# -------------------------------------------------------------
# 8) 공고 목록 조회
# -------------------------------------------------------------
@app.get("/api/notices")
def get_notices(user_id: int = Depends(require_login)):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT id, title, client, notice_date, detail_link, assigned_office
        FROM notices
        ORDER BY notice_date DESC
        LIMIT 300
    """)

    rows = cursor.fetchall()
    notices = []
    for r in rows:
        notices.append({
            "id": r[0],
            "title": r[1],
            "client": r[2],
            "date": r[3],
            "link": r[4],
            "office": r[5]
        })

    return {"status": "ok", "data": notices}


# -------------------------------------------------------------
# 9) 즐겨찾기 추가
# -------------------------------------------------------------
@app.post("/api/favorites/{notice_id}")
def add_favorite(notice_id: int, user_id: int = Depends(require_login)):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO favorites (user_id, notice_id, created_at)
        VALUES (?, ?, ?)
    """, (user_id, notice_id, datetime.now().isoformat()))
    db.commit()

    return {"status": "ok"}


# -------------------------------------------------------------
# 10) 즐겨찾기 삭제
# -------------------------------------------------------------
@app.delete("/api/favorites/{notice_id}")
def remove_favorite(notice_id: int, user_id: int = Depends(require_login)):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        DELETE FROM favorites
        WHERE user_id = ? AND notice_id = ?
    """, (user_id, notice_id))
    db.commit()

    return {"status": "ok"}


# -------------------------------------------------------------
# 11) 메모 작성
# -------------------------------------------------------------
class MemoRequest(BaseModel):
    memo: str

@app.post("/api/memos/{notice_id}")
def save_memo(notice_id: int, body: MemoRequest, user_id: int = Depends(require_login)):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO memos (user_id, notice_id, memo, updated_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, notice_id, body.memo, datetime.now().isoformat()))
    db.commit()

    return {"status": "ok"}

# -------------------------------------------------------------
# 12) (관리자) 강제 데이터 업데이트 실행
# -------------------------------------------------------------
@app.get("/api/admin/update")
def admin_update(user_id: int = Depends(require_login)):
    # 관리자 권한 확인
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    role_row = cursor.fetchone()

    if not role_row or role_row[0] != "admin":
        raise HTTPException(status_code=403, detail="관리자만 사용 가능")

    # 기존 알고리즘 실행
    try:
        run_all_collectors()
        return {"status": "ok", "message": "데이터 업데이트 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


