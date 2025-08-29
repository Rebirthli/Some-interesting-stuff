#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能古诗词搜索服务 - FastAPI 核心应用
提供双引擎搜索：关键词搜索和语义搜索
"""

import os
import logging
import json
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

import uvicorn
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
import requests
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 应用配置
class Config:
    # 数据库配置
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
    POSTGRES_DB = os.getenv('POSTGRES_DB', 'poetry_db')
    POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'postgres123')
    
    # 阿里云API配置
    ALI_API_KEY = os.getenv('ALI_API_KEY')
    ALI_API_URL = os.getenv('ALI_API_URL', 
        'https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding')
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-v4')
    EMBEDDING_DIMENSION = int(os.getenv('EMBEDDING_DIMENSION', '1536'))
    
    # API配置
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    API_PORT = int(os.getenv('API_PORT', '8000'))
    
    # 连接池配置
    MIN_CONNECTIONS = 2
    MAX_CONNECTIONS = 20

config = Config()

# 数据模型
class PoemResponse(BaseModel):
    id: int
    title: str
    author: str
    dynasty: str
    content: str
    score: Optional[float] = None

class SearchResponse(BaseModel):
    total: int
    results: List[PoemResponse]
    query_time_ms: float

class HealthResponse(BaseModel):
    status: str
    database: str
    api_key_configured: bool

# 数据库连接池管理
class DatabaseManager:
    def __init__(self):
        self.pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """初始化数据库连接池"""
        try:
            self.pool = SimpleConnectionPool(
                config.MIN_CONNECTIONS,
                config.MAX_CONNECTIONS,
                host=config.POSTGRES_HOST,
                port=config.POSTGRES_PORT,
                database=config.POSTGRES_DB,
                user=config.POSTGRES_USER,
                password=config.POSTGRES_PASSWORD,
                cursor_factory=RealDictCursor
            )
            logger.info("数据库连接池初始化成功")
        except Exception as e:
            logger.error(f"数据库连接池初始化失败: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                self.pool.putconn(conn)
    
    def close_pool(self):
        """关闭连接池"""
        if self.pool:
            self.pool.closeall()
            logger.info("数据库连接池已关闭")

# 全局数据库管理器
db_manager = DatabaseManager()

# FastAPI应用
app = FastAPI(
    title="智能古诗词搜索服务",
    description="基于关键词和语义的双引擎古诗词搜索API",
    version="1.0.0"
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 阿里云API客户端
class AliEmbeddingClient:
    def __init__(self):
        if not config.ALI_API_KEY:
            raise ValueError("ALI_API_KEY 未配置")
        
        self.headers = {
            'Authorization': f'Bearer {config.ALI_API_KEY}',
            'Content-Type': 'application/json'
        }
    
    def get_embedding(self, text: str, max_retries: int = 3) -> Optional[List[float]]:
        """获取文本的embedding向量"""
        data = {
            'model': config.EMBEDDING_MODEL,
            'input': {
                'texts': [text]
            }
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    config.ALI_API_URL,
                    headers=self.headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if 'output' in result and 'embeddings' in result['output']:
                        embedding = result['output']['embeddings'][0]['embedding']
                        return embedding
                    else:
                        logger.error(f"API响应格式错误: {result}")
                        return None
                else:
                    logger.error(f"API调用失败: {response.status_code}, {response.text}")
                    
            except Exception as e:
                logger.error(f"API调用异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                
            if attempt < max_retries - 1:
                import time
                time.sleep(1)
        
        return None
    
    def get_multi_embeddings(self, texts: List[str]) -> List[float]:
        """获取多个文本的embedding向量并平均化"""
        embeddings = []
        
        for text in texts:
            embedding = self.get_embedding(text.strip())
            if embedding:
                embeddings.append(embedding)
        
        if not embeddings:
            raise HTTPException(status_code=500, detail="无法获取任何文本的embedding")
        
        # 使用numpy计算平均向量
        avg_embedding = np.mean(embeddings, axis=0).tolist()
        return avg_embedding

# 全局embedding客户端
try:
    embedding_client = AliEmbeddingClient()
except ValueError:
    embedding_client = None
    logger.warning("ALI_API_KEY 未配置，语义搜索功能将不可用")

# 依赖注入
def get_db_connection():
    """依赖注入：获取数据库连接"""
    return db_manager.get_connection()

def get_embedding_client():
    """依赖注入：获取embedding客户端"""
    if not embedding_client:
        raise HTTPException(
            status_code=503, 
            detail="语义搜索服务不可用：ALI_API_KEY 未配置"
        )
    return embedding_client

# API端点
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查端点"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            db_status = "healthy"
    except Exception as e:
        logger.error(f"数据库健康检查失败: {e}")
        db_status = "unhealthy"
    
    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        database=db_status,
        api_key_configured=bool(config.ALI_API_KEY)
    )

@app.get("/search", response_model=SearchResponse)
async def keyword_search(
    keyword: str = Query(..., description="搜索关键词，支持多个词语空格分隔"),
    limit: int = Query(10, ge=1, le=100, description="返回结果数量限制"),
    offset: int = Query(0, ge=0, description="结果偏移量")
):
    """关键词搜索端点 - 使用PostgreSQL全文搜索和模糊匹配"""
    import time
    start_time = time.time()
    
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 处理多词查询，使用websearch_to_tsquery
            search_query = keyword.strip()
            
            # 使用联合查询：全文搜索 + 模糊匹配
            sql = """
            WITH search_results AS (
                -- 全文搜索结果
                SELECT 
                    id, title, author, dynasty, full_content,
                    ts_rank(to_tsvector('chinese', title || ' ' || full_content), 
                           websearch_to_tsquery('chinese', %s)) as score,
                    'fulltext' as match_type
                FROM poems 
                WHERE to_tsvector('chinese', title || ' ' || full_content) @@ 
                      websearch_to_tsquery('chinese', %s)
                
                UNION ALL
                
                -- 模糊匹配结果（仅当全文搜索结果不足时）
                SELECT 
                    id, title, author, dynasty, full_content,
                    similarity(title || ' ' || full_content, %s) as score,
                    'fuzzy' as match_type
                FROM poems 
                WHERE (title || ' ' || full_content) %% %s
                AND id NOT IN (
                    SELECT id FROM poems 
                    WHERE to_tsvector('chinese', title || ' ' || full_content) @@ 
                          websearch_to_tsquery('chinese', %s)
                )
            )
            SELECT DISTINCT id, title, author, dynasty, full_content, score
            FROM search_results
            ORDER BY score DESC, id
            LIMIT %s OFFSET %s
            """
            
            cursor.execute(sql, (
                search_query, search_query,  # 全文搜索
                search_query, search_query,  # 模糊匹配
                search_query,                # 排除全文搜索结果
                limit, offset
            ))
            
            results = cursor.fetchall()
            
            # 获取总数
            count_sql = """
            SELECT COUNT(DISTINCT id) FROM (
                SELECT id FROM poems 
                WHERE to_tsvector('chinese', title || ' ' || full_content) @@ 
                      websearch_to_tsquery('chinese', %s)
                UNION
                SELECT id FROM poems 
                WHERE (title || ' ' || full_content) %% %s
            ) AS combined_results
            """
            
            cursor.execute(count_sql, (search_query, search_query))
            total = cursor.fetchone()['count']
            
    except Exception as e:
        logger.error(f"关键词搜索失败: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")
    
    query_time = (time.time() - start_time) * 1000  # 转换为毫秒
    
    # 转换结果
    poems = []
    for row in results:
        poems.append(PoemResponse(
            id=row['id'],
            title=row['title'],
            author=row['author'],
            dynasty=row['dynasty'],
            content=row['full_content'],
            score=float(row['score']) if row['score'] else None
        ))
    
    return SearchResponse(
        total=total,
        results=poems,
        query_time_ms=round(query_time, 2)
    )

@app.get("/search/semantic", response_model=SearchResponse)
async def semantic_search(
    keywords: str = Query(..., description="语义搜索关键词，多个词语用逗号分隔"),
    limit: int = Query(10, ge=1, le=100, description="返回结果数量限制"),
    offset: int = Query(0, ge=0, description="结果偏移量"),
    embedding_client: AliEmbeddingClient = Depends(get_embedding_client)
):
    """语义搜索端点 - 基于向量相似度的语义搜索"""
    import time
    start_time = time.time()
    
    try:
        # 解析关键词
        keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
        
        if not keyword_list:
            raise HTTPException(status_code=400, detail="请提供有效的搜索关键词")
        
        logger.info(f"语义搜索关键词: {keyword_list}")
        
        # 获取关键词的embedding向量并平均化
        try:
            query_embedding = embedding_client.get_multi_embeddings(keyword_list)
        except Exception as e:
            logger.error(f"获取embedding失败: {e}")
            raise HTTPException(status_code=500, detail="无法获取搜索词的语义向量")
        
        # 在数据库中进行向量搜索
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 向量相似度搜索（使用cosine距离）
            vector_search_sql = """
            SELECT DISTINCT 
                p.id, p.title, p.author, p.dynasty, p.full_content,
                MIN(l.embedding <=> %s::vector) as distance
            FROM poems p
            JOIN lines l ON p.id = l.poem_id
            WHERE l.embedding IS NOT NULL
            GROUP BY p.id, p.title, p.author, p.dynasty, p.full_content
            ORDER BY distance ASC
            LIMIT %s OFFSET %s
            """
            
            cursor.execute(vector_search_sql, (query_embedding, limit, offset))
            results = cursor.fetchall()
            
            # 获取总数（估算，避免全表扫描）
            count_sql = """
            SELECT COUNT(DISTINCT poem_id) 
            FROM lines 
            WHERE embedding IS NOT NULL
            """
            cursor.execute(count_sql)
            total_with_embeddings = cursor.fetchone()['count']
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"语义搜索失败: {e}")
        raise HTTPException(status_code=500, detail=f"语义搜索失败: {str(e)}")
    
    query_time = (time.time() - start_time) * 1000  # 转换为毫秒
    
    # 转换结果（distance转换为相似度分数）
    poems = []
    for row in results:
        # 将cosine距离转换为相似度分数 (1 - distance)
        similarity_score = 1.0 - float(row['distance']) if row['distance'] else 0.0
        
        poems.append(PoemResponse(
            id=row['id'],
            title=row['title'],
            author=row['author'],
            dynasty=row['dynasty'],
            content=row['full_content'],
            score=round(similarity_score, 4)
        ))
    
    return SearchResponse(
        total=min(total_with_embeddings, 1000),  # 限制显示的总数
        results=poems,
        query_time_ms=round(query_time, 2)
    )

@app.get("/")
async def root():
    """根端点 - API信息"""
    return {
        "service": "智能古诗词搜索服务",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health - 健康检查",
            "keyword_search": "/search?keyword=关键词 - 关键词搜索",
            "semantic_search": "/search/semantic?keywords=物象词1,物象词2 - 语义搜索"
        },
        "docs": "/docs - API文档"
    }

# 应用启动和关闭事件
@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("智能古诗词搜索服务启动")
    logger.info(f"数据库连接: {config.POSTGRES_HOST}:{config.POSTGRES_PORT}")
    logger.info(f"API密钥配置: {'已配置' if config.ALI_API_KEY else '未配置'}")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("智能古诗词搜索服务关闭")
    db_manager.close_pool()

# 主函数
def main():
    """启动应用"""
    uvicorn.run(
        "main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()