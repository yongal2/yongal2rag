# RAG 챗봇 시스템 (yongal2rag)

AWS Bedrock Claude 3.5 Sonnet과 Qdrant Vector Database를 활용한 문서 기반 질의응답 시스템

## 📋 주요 기능

- ✅ PDF 및 텍스트 파일 업로드 및 자동 벡터화
- ✅ RAG 기반 문서 검색 및 질의응답
- ✅ 실시간 WebSocket 로그 스트리밍
- ✅ 문서 유사도 기반 Hit 정보 표시
- ✅ 일반 대화 모드 자동 전환
- ✅ 다중 인코딩 지원 (UTF-8, CP949, EUC-KR)

## 🛠 기술 스택

**Backend**
- FastAPI - 고성능 비동기 웹 프레임워크
- Uvicorn - ASGI 웹 서버

**AI & ML**
- AWS Bedrock Claude 3.5 Sonnet - LLM
- Qdrant - 벡터 데이터베이스
- HuggingFace Sentence Transformers - 텍스트 임베딩
- LangChain - LLM 프레임워크

**Document Processing**
- PyMuPDF (fitz) - PDF 텍스트 추출

## 💻 시스템 요구사항

- Python 3.10+
- Docker
- Ubuntu 22.04 LTS (권장)
- 최소 8GB RAM
- AWS 계정 (Bedrock 액세스 권한 필요)

## 🚀 설치 및 실행

### 1. 저장소 클론
```bash
git clone https://github.com/your-username/yongal2rag.git
cd yongal2rag
```

### 2. Python 가상환경 생성
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정
```bash
cp .env.example .env
nano .env
```

`.env` 파일에 실제 AWS 자격증명을 입력하세요.

### 5. Qdrant 실행 (Docker)
```bash
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  --restart always \
  qdrant/qdrant
```

### 6. 서버 실행
```bash
python3 main.py
```

브라우저에서 `http://localhost:8000` 접속

## 📁 프로젝트 구조
```
rag-chatbot/
├── main.py              # FastAPI 서버 및 API 엔드포인트
├── rag_engine.py        # RAG 엔진 코어 로직
├── .env                 # 환경 변수 (gitignore)
├── .env.example         # 환경 변수 템플릿
├── requirements.txt     # Python 의존성
├── README.md            # 프로젝트 문서
├── .gitignore          # Git 제외 파일
├── static/
│   └── index.html       # 웹 UI (3-column 레이아웃)
├── qdrant_storage/      # Qdrant 데이터 (gitignore)
└── venv/                # Python 가상환경 (gitignore)
```

## 📖 사용 방법

### 문서 업로드

1. 좌측 "📁 문서 업로드" 버튼 클릭
2. PDF 또는 TXT 파일 선택
3. 자동으로 청크 분할 및 벡터화

### 질의응답

1. 중앙 채팅창에 질문 입력
2. RAG 모드: 관련 문서가 있으면 자동으로 참고하여 답변
3. 일반 모드: 관련 문서가 없으면 Claude가 일반 대화로 답변

### 문서 관리

- 좌측 패널에서 업로드된 문서 목록 확인
- 각 문서의 청크 수와 업로드 시간 표시
- "삭제" 버튼으로 문서 제거

### 로그 모니터링

- 우측 패널에서 실시간 처리 로그 확인
- 검색 결과, 사용된 청크 수 등 표시

## 🔌 API 엔드포인트

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| POST | `/api/upload` | 파일 업로드 |
| GET | `/api/documents` | 문서 목록 조회 |
| DELETE | `/api/documents/{doc_id}` | 문서 삭제 |
| POST | `/api/query` | 질의응답 |
| WebSocket | `/ws/logs` | 실시간 로그 |

## ⚙️ 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AWS_ACCESS_KEY_ID` | AWS 액세스 키 ID | - |
| `AWS_SECRET_ACCESS_KEY` | AWS 시크릿 액세스 키 | - |
| `AWS_REGION` | AWS 리전 | ap-northeast-2 |
| `BEDROCK_MODEL_ID` | Claude 모델 ID | anthropic.claude-3-5-sonnet-20240620-v1:0 |
| `QDRANT_HOST` | Qdrant 호스트 | localhost |
| `QDRANT_PORT` | Qdrant 포트 | 6333 |
| `QDRANT_COLLECTION` | 컬렉션 이름 | network_docs |
| `SERVER_HOST` | 서버 호스트 | 0.0.0.0 |
| `SERVER_PORT` | 서버 포트 | 8000 |

## 🔧 Systemd 서비스 등록 (옵션)
```bash
sudo nano /etc/systemd/system/rag-chatbot.service
```

서비스 파일:
```ini
[Unit]
Description=RAG Chatbot Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=yongal2
WorkingDirectory=/home/yongal2/rag-chatbot
Environment="PATH=/home/yongal2/rag-chatbot/venv/bin"
ExecStart=/home/yongal2/rag-chatbot/venv/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

서비스 활성화:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rag-chatbot
sudo systemctl start rag-chatbot
sudo systemctl status rag-chatbot
```

## 🔍 Qdrant 대시보드

Qdrant Web UI 접속:
```
http://localhost:6333/dashboard
```

- 벡터 데이터 조회
- 검색 품질 분석
- 벡터 시각화

## 🧪 테스트

Python으로 직접 테스트:
```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)
collections = client.get_collections()
print(collections)
```

## 📊 주요 설정값

- **임베딩 모델**: paraphrase-multilingual-mpnet-base-v2 (768차원)
- **청크 크기**: 1000자
- **청크 오버랩**: 200자
- **유사도 임계값**: 0.1
- **검색 결과 수**: 최대 5개

## 🔒 보안 주의사항

⚠️ **절대 커밋하면 안 되는 파일:**
- `.env` (AWS 자격증명 포함)
- `qdrant_storage/` (벡터 데이터베이스)
- `venv/` (Python 가상환경)

실수로 `.env` 파일을 커밋한 경우:
1. Git 히스토리에서 완전히 제거
2. AWS 키를 즉시 삭제하고 재발급
3. GitHub Secrets 스캐닝 확인

## 📝 라이선스

MIT License

## 🤝 기여

Pull Request를 환영합니다!

## 📧 문의

이슈를 등록해주세요.
