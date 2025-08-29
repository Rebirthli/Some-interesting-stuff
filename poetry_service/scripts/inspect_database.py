#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库检查脚本 - 查看所有表的结构和预览数据
"""

import os
import logging
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseInspector:
    def __init__(self):
        """初始化检查器"""
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
            conn = psycopg2.connect(**self.db_config, cursor_factory=RealDictCursor)
            conn.autocommit = True
            logger.info("数据库连接成功")
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def get_all_tables(self, conn):
        """获取所有用户表"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        return [row['table_name'] for row in cursor.fetchall()]

    def get_table_structure(self, conn, table_name):
        """获取表结构信息"""
        cursor = conn.cursor()
        
        # 获取列信息
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns 
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table_name,))
        columns = cursor.fetchall()
        
        # 获取主键信息
        cursor.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass AND i.indisprimary
        """, (table_name,))
        primary_keys = [row['attname'] for row in cursor.fetchall()]
        
        # 获取外键信息
        cursor.execute("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name = %s
        """, (table_name,))
        foreign_keys = cursor.fetchall()
        
        # 获取索引信息
        cursor.execute("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = %s
            ORDER BY indexname
        """, (table_name,))
        indexes = cursor.fetchall()
        
        return {
            'columns': columns,
            'primary_keys': primary_keys,
            'foreign_keys': foreign_keys,
            'indexes': indexes
        }

    def get_table_stats(self, conn, table_name):
        """获取表统计信息"""
        cursor = conn.cursor()
        
        # 获取行数
        cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
        row_count = cursor.fetchone()['row_count']
        
        # 获取表大小信息
        cursor.execute("""
            SELECT 
                pg_size_pretty(pg_total_relation_size(%s)) as total_size,
                pg_size_pretty(pg_relation_size(%s)) as table_size,
                pg_size_pretty(pg_total_relation_size(%s) - pg_relation_size(%s)) as index_size
        """, (table_name, table_name, table_name, table_name))
        size_info = cursor.fetchone()
        
        return {
            'row_count': row_count,
            'total_size': size_info['total_size'],
            'table_size': size_info['table_size'],
            'index_size': size_info['index_size']
        }

    def preview_table_data(self, conn, table_name, limit=5):
        """预览表数据"""
        cursor = conn.cursor()
        
        try:
            # 对于有向量列的表，特殊处理
            if table_name == 'lines':
                cursor.execute(f"""
                    SELECT 
                        id, 
                        poem_id, 
                        content,
                        CASE 
                            WHEN embedding IS NOT NULL 
                            THEN concat('vector(', vector_dims(embedding), ')') 
                            ELSE 'NULL' 
                        END as embedding_info,
                        created_at
                    FROM {table_name} 
                    ORDER BY id 
                    LIMIT %s
                """, (limit,))
            elif table_name == 'search_config':
                # search_config表没有id列，按key排序
                cursor.execute(f"SELECT * FROM {table_name} ORDER BY key LIMIT %s", (limit,))
            else:
                cursor.execute(f"SELECT * FROM {table_name} ORDER BY id LIMIT %s", (limit,))
            
            return cursor.fetchall()
        except Exception as e:
            logger.warning(f"预览表 {table_name} 数据失败: {e}")
            return []

    def print_table_info(self, table_name, structure, stats, preview_data):
        """打印表信息"""
        print("\n" + "="*80)
        print(f"📋 表名: {table_name.upper()}")
        print("="*80)
        
        # 统计信息
        print(f"\n📊 统计信息:")
        print(f"  • 行数: {stats['row_count']:,}")
        print(f"  • 总大小: {stats['total_size']}")
        print(f"  • 表大小: {stats['table_size']}")
        print(f"  • 索引大小: {stats['index_size']}")
        
        # 列信息
        print(f"\n🏗️  列结构:")
        print(f"{'序号':<4} {'列名':<20} {'类型':<20} {'长度':<8} {'可空':<6} {'默认值':<15} {'备注'}")
        print("-" * 80)
        
        for col in structure['columns']:
            col_name = col['column_name']
            data_type = col['data_type']
            max_length = col['character_maximum_length'] or ''
            nullable = '✓' if col['is_nullable'] == 'YES' else '✗'
            default = col['column_default'] or ''
            
            # 添加特殊标记
            remarks = []
            if col_name in structure['primary_keys']:
                remarks.append('PK')
            
            for fk in structure['foreign_keys']:
                if fk['column_name'] == col_name:
                    remarks.append(f"FK→{fk['foreign_table_name']}")
            
            remarks_str = ','.join(remarks)
            
            print(f"{col['ordinal_position']:<4} {col_name:<20} {data_type:<20} {str(max_length):<8} {nullable:<6} {str(default)[:15]:<15} {remarks_str}")
        
        # 索引信息
        if structure['indexes']:
            print(f"\n🔍 索引信息:")
            for idx in structure['indexes']:
                print(f"  • {idx['indexname']}")
                # 只显示索引定义的关键部分
                index_def = idx['indexdef'].replace('CREATE INDEX ', '').replace('CREATE UNIQUE INDEX ', 'UNIQUE ')
                if len(index_def) > 60:
                    index_def = index_def[:60] + "..."
                print(f"    {index_def}")
        
        # 数据预览
        if preview_data:
            print(f"\n👀 数据预览 (前 {len(preview_data)} 行):")
            
            # 获取列名
            if preview_data:
                columns = list(preview_data[0].keys())
                
                # 打印表头
                header = " | ".join(f"{col[:15]:<15}" for col in columns)
                print(header)
                print("-" * len(header))
                
                # 打印数据行
                for row in preview_data:
                    row_data = []
                    for col in columns:
                        value = row[col]
                        if value is None:
                            value_str = "NULL"
                        elif isinstance(value, str) and len(value) > 15:
                            value_str = value[:12] + "..."
                        elif isinstance(value, datetime):
                            value_str = value.strftime("%Y-%m-%d %H:%M")
                        else:
                            value_str = str(value)
                        row_data.append(f"{value_str[:15]:<15}")
                    
                    print(" | ".join(row_data))
        else:
            print(f"\n👀 数据预览: (无数据)")

    def inspect_all_tables(self, conn):
        """检查所有表"""
        tables = self.get_all_tables(conn)
        
        if not tables:
            print("❌ 没有找到任何表")
            return
        
        print(f"\n🎯 数据库概览")
        print(f"数据库: {self.db_config['database']}")
        print(f"连接: {self.db_config['host']}:{self.db_config['port']}")
        print(f"找到 {len(tables)} 个表: {', '.join(tables)}")
        
        for table_name in tables:
            try:
                structure = self.get_table_structure(conn, table_name)
                stats = self.get_table_stats(conn, table_name)
                preview_data = self.preview_table_data(conn, table_name)
                
                self.print_table_info(table_name, structure, stats, preview_data)
                
            except Exception as e:
                logger.error(f"检查表 {table_name} 时发生错误: {e}")

    def inspect_specific_table(self, conn, table_name):
        """检查特定表"""
        try:
            structure = self.get_table_structure(conn, table_name)
            stats = self.get_table_stats(conn, table_name)
            preview_data = self.preview_table_data(conn, table_name, limit=10)
            
            self.print_table_info(table_name, structure, stats, preview_data)
            
        except Exception as e:
            logger.error(f"检查表 {table_name} 时发生错误: {e}")

def main():
    """主函数"""
    inspector = DatabaseInspector()
    conn = inspector.connect_db()
    
    try:
        print("请选择操作:")
        print("1. 检查所有表")
        print("2. 检查特定表")
        print("3. 只显示表列表")
        
        choice = input("\n请输入选择 (1/2/3): ").strip()
        
        if choice == "1":
            inspector.inspect_all_tables(conn)
            
        elif choice == "2":
            tables = inspector.get_all_tables(conn)
            if tables:
                print(f"\n可用的表: {', '.join(tables)}")
                table_name = input("请输入要检查的表名: ").strip()
                if table_name in tables:
                    inspector.inspect_specific_table(conn, table_name)
                else:
                    print(f"❌ 表 '{table_name}' 不存在")
            else:
                print("❌ 没有找到任何表")
                
        elif choice == "3":
            tables = inspector.get_all_tables(conn)
            if tables:
                print(f"\n📋 数据库表列表:")
                for i, table in enumerate(tables, 1):
                    print(f"  {i}. {table}")
            else:
                print("❌ 没有找到任何表")
                
        else:
            print("❌ 无效选择")
            
    except Exception as e:
        logger.error(f"检查过程中发生错误: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()