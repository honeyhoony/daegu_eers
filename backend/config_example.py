"""
이 파일은 실제 config.py 대신 사용하는 템플릿입니다.
민감한 정보(API KEY, SMTP 비밀번호)는 절대 GitHub에 올리지 마세요.

실제 서버에서는 Cloudflare Workers의 시크릿 환경변수에 저장합니다.
로컬 테스트를 위한 값은 아래 형식대로 config.py에 만들어 사용하세요.
"""

# 나라장터 API 키
G2B_API_KEY = "YOUR_G2B_KEY"

# K-APT API 키
KAPT_API_KEY = "YOUR_KAPT_KEY"

# KEA 고효율기기 인증 API 키
KEA_API_KEY = "YOUR_KEA_KEY"

# SMTP (OTP 발송용)
SMTP_HOST = "smtp.naver.com"
SMTP_USER = "YOUR_EMAIL@naver.com"
SMTP_PASS = "YOUR_SMTP_APP_PASSWORD"

# 관리자 이메일 (관리자 권한 부여)
ADMIN_EMAIL = "YOUR_ADMIN_EMAIL@kepco.co.kr"

