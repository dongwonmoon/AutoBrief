# 베이스 이미지
FROM python:3.10-slim

# 작업 디렉토리
WORKDIR /app

# 필요한 파일 복사
COPY ./requirements.txt ./

# 라이브러리 설치
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY ./app.py ./

# 포트 노출
EXPOSE 8501

# 실행
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]