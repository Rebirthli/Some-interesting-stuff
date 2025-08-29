#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速检查数据库中的诗词数量
"""

import os
import logging
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加载环境变量
env_local_path = Path(__file__).parent.parent / '.env.local'
env_path = Path(__file__).parent.parent / '.env'

if env_local_path.exists():
    load_dotenv(env_local_path)
    logger.info(f"使用本地环境配置: {env_local_path}")
elif env_path.exists():
    load_dotenv(env_path)
    logger.info(f"使用默认环境配置: {env_path}")
else:
    load_dotenv()
    logger.warning("未找到环境配置文件，使用系统环境变量")

# 数据库配置
db_config = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'poetry_db'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres123')
}

try:
    conn = psycopg2.connect(**db_config)
    conn.autocommit = True
    cursor = conn.cursor()
    
    # 获取各表记录数
    cursor.execute("SELECT COUNT(*) FROM poems")
    poem_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM authors")
    author_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM dynasties")
    dynasty_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM lines")
    line_count = cursor.fetchone()[0]
    
    # 获取朝代分布
    cursor.execute("""
        SELECT d.name, COUNT(p.id) as poem_count
        FROM dynasties d
        JOIN authors a ON d.id = a.dynasty_id
        JOIN poems p ON a.id = p.author_id
        GROUP BY d.name
        ORDER BY poem_count DESC
    """)
    dynasty_stats = cursor.fetchall()
    
    # 获取作者分布
    cursor.execute("""
        SELECT a.name, d.name as dynasty, COUNT(p.id) as poem_count
        FROM authors a
        JOIN dynasties d ON a.dynasty_id = d.id
        JOIN poems p ON a.id = p.author_id
        GROUP BY a.name, d.name
        ORDER BY poem_count DESC
        LIMIT 10
    """)
    author_stats = cursor.fetchall()
    
    print("\n数据库统计概览")
    print("=" * 50)
    print(f"诗词总数: {poem_count:,}")
    print(f"作者数: {author_count:,}")
    print(f"朝代数: {dynasty_count:,}")
    print(f"诗句数: {line_count:,}")
    
    print("\n朝代分布:")
    for dynasty, count in dynasty_stats:
        print(f"  {dynasty}: {count:,} 首")
    
    print("\n热门作者:")
    for author, dynasty, count in author_stats:
        print(f"  {author} ({dynasty}): {count:,} 首")
    
    conn.close()
    
except Exception as e:
    logger.error(f"数据库检查失败: {e}")