#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库清理脚本 - 清除不完整的数据并重置表结构
"""

import os
import logging
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseCleaner:
    def __init__(self):
        """初始化清理器"""
        # 加载环境变量（优先使用本地开发配置）
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
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': os.getenv('POSTGRES_PORT', '5432'),
            'database': os.getenv('POSTGRES_DB', 'poetry_db'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'postgres123')
        }

    def connect_db(self):
        """连接数据库"""
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.autocommit = False
            logger.info("数据库连接成功")
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def check_data_status(self, conn):
        """检查当前数据状态"""
        cursor = conn.cursor()
        
        # 检查poems表数据量
        cursor.execute("SELECT COUNT(*) FROM poems")
        poems_count = cursor.fetchone()[0]
        
        # 检查lines表数据量
        cursor.execute("SELECT COUNT(*) FROM lines")
        lines_count = cursor.fetchone()[0]
        
        # 检查有embedding的lines数量
        cursor.execute("SELECT COUNT(*) FROM lines WHERE embedding IS NOT NULL")
        lines_with_embedding = cursor.fetchone()[0]
        
        # 检查没有对应lines记录的poems
        cursor.execute("""
            SELECT COUNT(*) FROM poems p 
            WHERE NOT EXISTS (SELECT 1 FROM lines l WHERE l.poem_id = p.id)
        """)
        orphan_poems = cursor.fetchone()[0]
        
        # 检查向量维度
        cursor.execute("""
            SELECT DISTINCT vector_dims(embedding) as dimension, COUNT(*) as count
            FROM lines 
            WHERE embedding IS NOT NULL
            GROUP BY vector_dims(embedding)
            ORDER BY dimension
        """)
        dimension_stats = cursor.fetchall()
        
        logger.info(f"📊 当前数据状态:")
        logger.info(f"  - 诗词总数: {poems_count}")
        logger.info(f"  - 句子总数: {lines_count}")
        logger.info(f"  - 有向量的句子: {lines_with_embedding}")
        logger.info(f"  - 孤立的诗词(无句子): {orphan_poems}")
        
        if dimension_stats:
            logger.info(f"  - 向量维度分布:")
            for dim, count in dimension_stats:
                logger.info(f"    * {dim}维: {count} 条")
        
        return {
            'poems_count': poems_count,
            'lines_count': lines_count,
            'lines_with_embedding': lines_with_embedding,
            'orphan_poems': orphan_poems,
            'dimension_stats': dimension_stats
        }

    def clean_incomplete_data(self, conn):
        """清理不完整的数据"""
        cursor = conn.cursor()
        
        logger.info("🧹 开始清理不完整的数据...")
        
        # 1. 删除没有embedding的lines记录
        cursor.execute("DELETE FROM lines WHERE embedding IS NULL")
        deleted_lines = cursor.rowcount
        logger.info(f"  - 删除无向量的句子: {deleted_lines} 条")
        
        # 2. 删除维度不正确的向量（非1536维）
        cursor.execute("DELETE FROM lines WHERE vector_dims(embedding) != 1536")
        wrong_dim_lines = cursor.rowcount
        logger.info(f"  - 删除维度错误的句子: {wrong_dim_lines} 条")
        
        # 3. 删除没有对应lines记录的poems
        cursor.execute("""
            DELETE FROM poems 
            WHERE id NOT IN (SELECT DISTINCT poem_id FROM lines WHERE embedding IS NOT NULL)
        """)
        deleted_poems = cursor.rowcount
        logger.info(f"  - 删除孤立的诗词: {deleted_poems} 首")
        
        conn.commit()
        logger.info("✅ 数据清理完成")

    def truncate_all_data(self, conn):
        """清空所有数据（重新开始）"""
        cursor = conn.cursor()
        
        logger.info("🗑️ 清空所有数据...")
        
        # 先删除lines表（由于外键约束）
        cursor.execute("TRUNCATE TABLE lines CASCADE")
        logger.info("  - 清空lines表")
        
        # 删除poems表
        cursor.execute("TRUNCATE TABLE poems RESTART IDENTITY CASCADE")
        logger.info("  - 清空poems表")
        
        conn.commit()
        logger.info("✅ 所有数据已清空")

    def reset_sequences(self, conn):
        """重置序列"""
        cursor = conn.cursor()
        
        logger.info("🔄 重置序列...")
        cursor.execute("SELECT setval('poems_id_seq', 1, false)")
        cursor.execute("SELECT setval('lines_id_seq', 1, false)")
        
        conn.commit()
        logger.info("✅ 序列重置完成")

    def optimize_database(self, conn):
        """优化数据库"""
        cursor = conn.cursor()
        
        logger.info("⚡ 优化数据库...")
        
        # 更新表统计信息
        cursor.execute("ANALYZE poems")
        cursor.execute("ANALYZE lines")
        
        # 清理死元组
        cursor.execute("VACUUM poems")
        cursor.execute("VACUUM lines")
        
        conn.commit()
        logger.info("✅ 数据库优化完成")

def main():
    """主函数"""
    cleaner = DatabaseCleaner()
    conn = cleaner.connect_db()
    
    try:
        # 检查当前状态
        status = cleaner.check_data_status(conn)
        
        # 询问用户操作
        print("\n请选择操作:")
        print("1. 只清理不完整的数据（保留有效数据）")
        print("2. 清空所有数据（重新开始）")
        print("3. 只查看状态（不执行清理）")
        print("4. 优化数据库（更新统计信息）")
        
        choice = input("\n请输入选择 (1/2/3/4): ").strip()
        
        if choice == "1":
            # 检查是否需要清理
            need_clean = (
                status['orphan_poems'] > 0 or 
                (status['lines_count'] - status['lines_with_embedding']) > 0 or
                any(dim != 1536 for dim, count in status['dimension_stats']) if status['dimension_stats'] else False
            )
            
            if need_clean:
                confirm = input("确认清理不完整的数据吗？(y/n): ").strip().lower()
                if confirm == 'y':
                    cleaner.clean_incomplete_data(conn)
                    # 重新检查状态
                    cleaner.check_data_status(conn)
                else:
                    logger.info("❌ 操作已取消")
            else:
                logger.info("✅ 没有发现不完整的数据")
                
        elif choice == "2":
            confirm = input("⚠️  确认要清空所有数据吗？(输入 'yes' 确认): ").strip()
            if confirm.lower() == 'yes':
                cleaner.truncate_all_data(conn)
                cleaner.reset_sequences(conn)
                # 重新检查状态
                cleaner.check_data_status(conn)
            else:
                logger.info("❌ 操作已取消")
                
        elif choice == "3":
            logger.info("✅ 状态检查完成")
            
        elif choice == "4":
            cleaner.optimize_database(conn)
            # 重新检查状态
            cleaner.check_data_status(conn)
            
        else:
            logger.warning("❌ 无效选择")
            
    except Exception as e:
        logger.error(f"清理过程中发生错误: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()