#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据导入修复脚本
验证varchar长度约束问题是否已解决
"""
import os
import sys
from pathlib import Path

# 添加父目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from scripts.import_data import PoetryImporter
import psycopg2

def test_database_connection():
    """测试数据库连接"""
    try:
        importer = PoetryImporter()
        conn = importer.connect_db()
        cursor = conn.cursor()
        
        # 检查表结构
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name IN ('dynasties', 'authors', 'poems') 
            AND column_name IN ('name', 'title')
        """)
        
        columns = cursor.fetchall()
        print("数据库字段信息:")
        for col in columns:
            print(f"  {col[0]}: {col[1]}({col[2] if col[2] else '无限制'})")
        
        conn.close()
        return True
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return False

def test_long_text_handling():
    """测试长文本处理"""
    try:
        importer = PoetryImporter()
        
        # 创建测试数据
        test_poem = {
            'title': '这是一个非常非常长的标题，长度超过了64个字符限制，用来测试数据导入时是否会因为长度问题而失败',
            'author': '这是一个非常非常长的作者名字，长度超过了64个字符限制，用来测试数据导入时是否会因为长度问题而失败',
            'dynasty': '这是一个非常非常长的朝代名称，长度超过了64个字符限制，用来测试数据导入时是否会因为长度问题而失败',
            'paragraphs': ['测试诗句内容']
        }
        
        processed = importer.process_poem_data(test_poem, Path('test.json'))
        
        if processed:
            print("✓ 长文本处理成功:")
            print(f"  标题长度: {len(processed['title'])}")
            print(f"  作者长度: {len(processed['author'])}")
            print(f"  朝代长度: {len(processed['dynasty'])}")
            print(f"  处理后的标题: {processed['title']}")
            print(f"  处理后的作者: {processed['author']}")
            print(f"  处理后的朝代: {processed['dynasty']}")
            return True
        else:
            print("✗ 长文本处理失败")
            return False
    except Exception as e:
        print(f"长文本处理测试失败: {e}")
        return False

def test_batch_insert():
    """测试批量插入"""
    try:
        importer = PoetryImporter()
        conn = importer.connect_db()
        
        # 创建测试批次
        test_batch = [{
            'title': '测试标题' * 10,  # 制造长标题
            'author': '测试作者' * 10,  # 制造长作者名
            'dynasty': '测试朝代' * 10,  # 制造长朝代名
            'content': '测试内容'
        }]
        
        importer.process_and_insert_batch(test_batch, conn)
        conn.close()
        print("✓ 批量插入测试成功")
        return True
    except Exception as e:
        print(f"批量插入测试失败: {e}")
        return False

if __name__ == "__main__":
    print("开始测试数据导入修复...")
    
    print("\n1. 测试数据库连接和字段信息:")
    test_database_connection()
    
    print("\n2. 测试长文本处理:")
    test_long_text_handling()
    
    print("\n3. 测试批量插入:")
    test_batch_insert()
    
    print("\n测试完成！")