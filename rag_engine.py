import os
from typing import List, Dict, Any
from datetime import datetime
from langchain_aws import ChatBedrock
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.messages import HumanMessage
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import hashlib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self):
        try:
            logger.info("RAGEngine 초기화 시작")
            
            self.llm = ChatBedrock(
                model_id=os.getenv("BEDROCK_MODEL_ID"),
                region_name=os.getenv("AWS_REGION"),
                model_kwargs={"max_tokens": 4096, "temperature": 0.7}
            )
            logger.info("Bedrock 초기화 완료")
            
            self.embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                model_kwargs={'device': 'cpu'}
            )
            logger.info("임베딩 모델 초기화 완료")
            
            self.qdrant_client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", 6333))
            )
            logger.info("Qdrant 클라이언트 초기화 완료")
            
            self.collection_name = os.getenv("QDRANT_COLLECTION", "network_docs")
            self.ensure_collection()
            
            logger.info("RAGEngine 초기화 성공")
            
        except Exception as e:
            logger.error(f"RAGEngine 초기화 실패: {e}")
            raise
    
    def ensure_collection(self):
        try:
            collections = self.qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
                )
                logger.info(f"컬렉션 생성: {self.collection_name}")
            else:
                logger.info(f"컬렉션 존재: {self.collection_name}")
        except Exception as e:
            logger.error(f"컬렉션 확인 실패: {e}")
            raise
    
    def add_document(self, file_name: str, content: str) -> Dict[str, Any]:
        try:
            doc_id = hashlib.md5(file_name.encode()).hexdigest()
            
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            chunks = text_splitter.split_text(content)
            
            points = []
            for idx, chunk in enumerate(chunks):
                embedding = self.embeddings.embed_query(chunk)
                point_id = hashlib.md5(f"{doc_id}_{idx}".encode()).hexdigest()
                
                points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "doc_id": doc_id,
                        "file_name": file_name,
                        "chunk_index": idx,
                        "text": chunk,
                        "uploaded_at": datetime.now().isoformat()
                    }
                ))
            
            self.qdrant_client.upsert(collection_name=self.collection_name, points=points)
            
            logger.info(f"문서 추가 완료: {file_name} ({len(chunks)} chunks)")
            
            return {"status": "success", "doc_id": doc_id, "chunks_count": len(chunks)}
            
        except Exception as e:
            logger.error(f"문서 추가 실패: {e}")
            return {"status": "error", "message": str(e)}
    
    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        try:
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
                limit=10000
            )
            
            point_ids = [point.id for point in scroll_result[0]]
            
            if point_ids:
                self.qdrant_client.delete(collection_name=self.collection_name, points_selector=point_ids)
            
            logger.info(f"문서 삭제 완료: {doc_id}")
            
            return {"status": "success", "deleted_points": len(point_ids)}
            
        except Exception as e:
            logger.error(f"문서 삭제 실패: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_all_documents(self) -> List[Dict]:
        try:
            result = self.qdrant_client.scroll(collection_name=self.collection_name, limit=10000)
            
            docs_dict = {}
            for point in result[0]:
                doc_id = point.payload.get("doc_id")
                if doc_id not in docs_dict:
                    docs_dict[doc_id] = {
                        "doc_id": doc_id,
                        "file_name": point.payload.get("file_name"),
                        "chunks_count": 0,
                        "uploaded_at": point.payload.get("uploaded_at")
                    }
                docs_dict[doc_id]["chunks_count"] += 1
            
            return list(docs_dict.values())
            
        except Exception as e:
            logger.error(f"문서 목록 조회 실패: {e}")
            return []
    
    def query(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        try:
            logger.info(f"쿼리 시작: {question}")
            
            # 컬렉션 문서 수 확인
            try:
                collection_info = self.qdrant_client.get_collection(self.collection_name)
                points_count = collection_info.points_count
                logger.info(f"컬렉션 문서 수: {points_count}")
            except Exception as e:
                logger.warning(f"컬렉션 확인 실패: {e}")
                points_count = 0
            
            # 문서가 없으면 일반 대화
            if points_count == 0:
                logger.info("RAG 문서 없음 - 일반 대화 모드")
                message = HumanMessage(content=question)
                response = self.llm.invoke([message])
                
                return {
                    "status": "success",
                    "answer": response.content,
                    "hit_info": [],
                    "context_used": 0,
                    "mode": "general"
                }
            
            # RAG 검색
            query_embedding = self.embeddings.embed_query(question)
            
            # query_points 메서드 사용 (최신 Qdrant API)
            search_response = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=top_k
            )
            search_results = search_response.points
            
            # 디버깅: 검색 결과 로그
            logger.info(f"검색 결과: {len(search_results)}개")
            for idx, result in enumerate(search_results[:3]):
                logger.info(f"  #{idx+1}: {result.payload.get('file_name')} - 유사도: {result.score:.4f}")
            
            # 검색 결과 없거나 유사도 낮으면 일반 대화 (임계값: 0.2)
            if not search_results or search_results[0].score < 0.2:
                logger.info(f"관련 문서 없음 (최고 유사도: {search_results[0].score if search_results else 0:.4f}) - 일반 대화 모드")
                message = HumanMessage(content=question)
                response = self.llm.invoke([message])
                
                return {
                    "status": "success",
                    "answer": response.content,
                    "hit_info": [],
                    "context_used": 0,
                    "mode": "general"
                }
            
            # RAG 모드
            context_chunks = []
            hit_info = []
            
            for idx, result in enumerate(search_results):
                if result.score >= 0.2:  # 임계값: 0.2
                    context_chunks.append(result.payload["text"])
                    hit_info.append({
                        "rank": idx + 1,
                        "file_name": result.payload["file_name"],
                        "score": round(result.score, 4),
                        "chunk_index": result.payload["chunk_index"]
                    })
            
            if context_chunks:
                context = "\n\n".join(context_chunks)
                prompt = f"""다음 문서를 참고하여 질문에 답변하세요.

참고 문서:
{context}

질문: {question}

답변:"""
                logger.info(f"RAG 모드 - {len(context_chunks)} chunks 사용")
            else:
                prompt = question
                logger.info("유사도 낮음 - 일반 대화 모드")
            
            message = HumanMessage(content=prompt)
            response = self.llm.invoke([message])
            
            logger.info("쿼리 완료")
            
            return {
                "status": "success",
                "answer": response.content,
                "hit_info": hit_info,
                "context_used": len(context_chunks),
                "mode": "rag" if context_chunks else "general"
            }
            
        except Exception as e:
            logger.error(f"쿼리 실패: {e}", exc_info=True)
            
            # 에러 시 폴백
            try:
                logger.info("에러 발생 - 일반 대화로 폴백")
                message = HumanMessage(content=question)
                response = self.llm.invoke([message])
                
                return {
                    "status": "success",
                    "answer": response.content,
                    "hit_info": [],
                    "context_used": 0,
                    "mode": "fallback"
                }
            except Exception as fallback_error:
                logger.error(f"폴백도 실패: {fallback_error}")
                return {
                    "status": "error",
                    "message": str(e),
                    "answer": f"죄송합니다. 오류가 발생했습니다.",
                    "hit_info": []
                }


rag_engine_instance = None


def get_rag_engine():
    global rag_engine_instance
    if rag_engine_instance is None:
        rag_engine_instance = RAGEngine()
    return rag_engine_instance
