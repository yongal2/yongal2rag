from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import logging
from datetime import datetime
from typing import List
import os
from dotenv import load_dotenv
import fitz  # PyMuPDF
from io import BytesIO

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket 연결 관리
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# RAG 엔진 lazy loading
rag_engine = None

def get_rag():
    global rag_engine
    if rag_engine is None:
        from rag_engine import get_rag_engine
        rag_engine = get_rag_engine()
    return rag_engine

# Pydantic 모델
class QueryRequest(BaseModel):
    question: str

# API 엔드포인트
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        
        # PDF 파일 처리
        if file.filename.lower().endswith('.pdf'):
            try:
                text_content = ""
                pdf_document = fitz.open(stream=content, filetype="pdf")
                page_count = pdf_document.page_count
                
                for page_num in range(page_count):
                    page = pdf_document[page_num]
                    page_text = page.get_text()
                    if page_text:
                        text_content += page_text + "\n"
                
                pdf_document.close()
                
                logger.info(f"PDF 파일 처리 완료: {page_count} 페이지, {len(text_content)} 문자")
                await manager.broadcast({
                    "type": "log",
                    "message": f"📄 PDF 업로드: {file.filename} ({page_count} 페이지, {len(text_content)} 문자)",
                    "timestamp": datetime.now().isoformat()
                })
                
                if not text_content.strip():
                    raise ValueError("PDF에서 텍스트를 추출할 수 없습니다. 이미지 기반 PDF일 수 있습니다.")
                    
            except Exception as pdf_error:
                raise ValueError(f"PDF 파일 처리 실패: {str(pdf_error)}")
        else:
            # 텍스트 파일 처리
            text_content = None
            for encoding in ['utf-8', 'cp949', 'euc-kr', 'latin-1']:
                try:
                    text_content = content.decode(encoding)
                    logger.info(f"파일 인코딩: {encoding}")
                    await manager.broadcast({
                        "type": "log",
                        "message": f"📁 업로드: {file.filename} (인코딩: {encoding})",
                        "timestamp": datetime.now().isoformat()
                    })
                    break
                except UnicodeDecodeError:
                    continue
            
            if text_content is None:
                raise ValueError("지원하지 않는 파일 인코딩입니다. UTF-8, CP949, EUC-KR 형식의 파일을 사용해주세요.")
        
        engine = get_rag()
        result = engine.add_document(file.filename, text_content)
        
        if result['status'] == 'success':
            await manager.broadcast({
                "type": "log",
                "message": f"✅ 문서 추가 완료: {file.filename} ({result['chunks_count']} chunks)",
                "timestamp": datetime.now().isoformat()
            })
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"파일 업로드 실패: {e}")
        await manager.broadcast({
            "type": "log",
            "message": f"❌ 업로드 실패: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.get("/api/documents")
async def get_documents():
    try:
        engine = get_rag()
        documents = engine.get_all_documents()
        return JSONResponse(content=documents)
    except Exception as e:
        logger.error(f"문서 목록 조회 실패: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    try:
        engine = get_rag()
        result = engine.delete_document(doc_id)
        
        if result['status'] == 'success':
            await manager.broadcast({
                "type": "log",
                "message": f"🗑️ 문서 삭제: {doc_id}",
                "timestamp": datetime.now().isoformat()
            })
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"문서 삭제 실패: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/api/query")
async def query_rag(request: QueryRequest):
    try:
        await manager.broadcast({
            "type": "log",
            "message": f"❓ 질문: {request.question}",
            "timestamp": datetime.now().isoformat()
        })
        
        engine = get_rag()
        result = engine.query(request.question)
        
        await manager.broadcast({
            "type": "log",
            "message": f"✅ 응답 완료 ({result.get('context_used', 0)} chunks)",
            "timestamp": datetime.now().isoformat()
        })
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"쿼리 실패: {e}")
        await manager.broadcast({
            "type": "log",
            "message": f"❌ 오류: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 정적 파일 서빙
@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", 8000))
    
    logger.info(f"서버 시작: http://{host}:{port}")
    
    uvicorn.run(app, host=host, port=port)
