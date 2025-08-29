#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据导入验证脚本
非交互式验证数据导入结果
"""
import psycopg2
import logging
from pathlib import Path
import os
from dotenv import load_dotenv

# 加载环境变量
env_local_path = Path(__file__).parent.parent / '.env.local'
env_path = Path(__file__).parent.parent / '.env'
if env_local_path.exists():
    load_dotenv(env_local_path)
elif env_path.exists():
    load_dotenv(env_path)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('verify_import.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_db_config():
    """获取数据库配置"""
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432'),
        'database': os.getenv('POSTGRES_DB', 'poetry_db'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'postgres123')
    }

def verify_import():
    """验证数据导入结果"""
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        
        print("=== 数据导入验证报告 ===")
        
        # 基础统计
        cursor.execute("SELECT COUNT(*) FROM dynasties")
        dynasty_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM authors")
        author_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM poems")
        poem_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM lines")
        line_count = cursor.fetchone()[0]
        
        print(f"朝代数量: {dynasty_count}")
        print(f"作者数量: {author_count}")
        print(f"诗词数量: {poem_count}")
        print(f"诗句数量: {line_count}")
        
        # 按朝代统计
        cursor.execute("""
            SELECT d.name, COUNT(p.id) as poem_count
            FROM dynasties d
            JOIN authors a ON d.id = a.dynasty_id
            JOIN poems p ON a.id = p.author_id
            GROUP BY d.name
            ORDER BY poem_count DESC
        """)
        
        dynasty_stats = cursor.fetchall()
        print("\n=== 各朝代诗词统计 ===")
        for dynasty, count in dynasty_stats:
            print(f"{dynasty}: {count} 首")
        
        # 特殊文献统计
        classical_dynasties = ['先秦', '古代']
        classical_count = 0
        for dynasty in classical_dynasties:
            cursor.execute("""
                SELECT COUNT(*) FROM poems p
                JOIN authors a ON p.author_id = a.id
                JOIN dynasties d ON a.dynasty_id = d.id
                WHERE d.name = %s
            """, (dynasty,))
            count = cursor.fetchone()[0]
            classical_count += count
            if count > 0:
                print(f"{dynasty} 文献: {count} 条记录")
        
        # 数据完整性检查
        cursor.execute("""
            SELECT COUNT(*) FROM poems 
            WHERE title IS NULL OR title = '' OR title = '无题'
        """)
        missing_titles = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM poems 
            WHERE full_content IS NULL OR full_content = ''
        """)
        missing_content = cursor.fetchone()[0]
        
        print(f"\n=== 数据完整性检查 ===")
        print(f"缺失标题的诗词: {missing_titles}")
        print(f"缺失内容的诗词: {missing_content}")
        
        # 与预期对比
        expected_total = 80000
        actual_total = poem_count
        completion_rate = (actual_total / expected_total) * 100
        
        print(f"\n=== 完成度评估 ===")
        print(f"预期总诗词: {expected_total}")
        print(f"实际导入: {actual_total}")
        print(f"完成度: {completion_rate:.2f}%")
        
        # 前10位作者统计
        cursor.execute("""
            SELECT a.name, d.name as dynasty, COUNT(p.id) as poem_count
            FROM authors a
            JOIN dynasties d ON a.dynasty_id = d.id
            JOIN poems p ON a.id = p.author_id
            GROUP BY a.name, d.name
            ORDER BY poem_count DESC
            LIMIT 10
        """)
        
        top_authors = cursor.fetchall()
        print("\n=== 前10位高产作者 ===")
        for author, dynasty, count in top_authors:
            print(f"{author} ({dynasty}): {count} 首")
        
        # 检查向量数据
        cursor.execute("""
            SELECT COUNT(*) FROM lines 
            WHERE embedding IS NOT NULL
        """)
        vectorized_count = cursor.fetchone()[0]
        print(f"\n=== 向量数据检查 ===")
        print(f"已生成向量的诗句: {vectorized_count}")
        print(f"向量覆盖率: {(vectorized_count/line_count)*100:.2f}%" if line_count > 0 else "0%")
        
        conn.close()
        
        # 总体评估
        print(f"\n=== 总体评估 ===")
        if completion_rate >= 70:
            print("✅ 数据导入完成度良好")
        elif completion_rate >= 50:
            print("⚠️  数据导入完成度一般，建议检查")
        else:
            print("❌ 数据导入完成度较低，需要进一步处理")
            
        return {
            'total_poems': poem_count,
            'total_authors': author_count,
            'total_dynasties': dynasty_count,
            'total_lines': line_count,
            'completion_rate': completion_rate,
            'missing_titles': missing_titles,
            'missing_content': missing_content,
            'vector_coverage': (vectorized_count/line_count)*100 if line_count > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"验证失败: {e}")
        return None

if __name__ == "__main__":
    print("开始验证数据导入结果...")
    result = verify_import()
    if result:
        print("\n验证完成！")
    else:
        print("验证失败，请检查日志")