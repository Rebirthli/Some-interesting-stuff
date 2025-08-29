#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据导入恢复脚本
从上次中断的文件继续导入，并验证数据完整性
"""
import os
import sys
from pathlib import Path
import logging

# 添加父目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from scripts.import_data import PoetryImporter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('resume_import.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def resume_import():
    """从上次中断的文件恢复导入"""
    try:
        importer = PoetryImporter()
        
        # 检查已处理的文件
        processed_files = importer.load_processed_files()
        all_files = importer.load_json_files()
        
        logger.info(f"总共发现 {len(all_files)} 个JSON文件")
        logger.info(f"已处理 {len(processed_files)} 个文件")
        
        # 找出未处理的文件
        remaining_files = [f for f in all_files if str(f) not in processed_files]
        logger.info(f"需要处理 {len(remaining_files)} 个新文件")
        
        if not remaining_files:
            logger.info("所有文件均已处理完成")
            return
            
        # 按文件类型分组统计
        file_types = {}
        for file_path in remaining_files:
            parent_dir = file_path.parent.name
            if parent_dir not in file_types:
                file_types[parent_dir] = []
            file_types[parent_dir].append(file_path)
            
        logger.info("\n剩余文件分布:")
        for dir_name, files in file_types.items():
            logger.info(f"  {dir_name}: {len(files)} 个文件")
            
        # 继续导入
        importer.run_import()
        
        # 验证导入结果
        verify_import()
        
    except Exception as e:
        logger.error(f"恢复导入失败: {e}", exc_info=True)

def verify_import():
    """验证数据导入结果"""
    try:
        importer = PoetryImporter()
        conn = importer.connect_db()
        cursor = conn.cursor()
        
        # 统计各个表的数据量
        cursor.execute("SELECT COUNT(*) FROM dynasties")
        dynasty_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM authors")
        author_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM poems")
        poem_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM lines")
        line_count = cursor.fetchone()[0]
        
        logger.info("\n=== 数据导入统计 ===")
        logger.info(f"朝代数量: {dynasty_count}")
        logger.info(f"作者数量: {author_count}")
        logger.info(f"诗词数量: {poem_count}")
        logger.info(f"诗句数量: {line_count}")
        
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
        logger.info("\n=== 各朝代诗词统计 ===")
        for dynasty, count in dynasty_stats:
            logger.info(f"{dynasty}: {count} 首")
            
        # 检查数据完整性
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
        
        logger.info(f"\n=== 数据完整性检查 ===")
        logger.info(f"缺失标题的诗词: {missing_titles}")
        logger.info(f"缺失内容的诗词: {missing_content}")
        
        # 检查特殊文献类型
        classical_texts = [
            '先秦', '古代', '诗经', '楚辞', '论语', 
            '孟子', '大学', '中庸', '蒙学'
        ]
        
        for text_type in classical_texts:
            cursor.execute("""
                SELECT COUNT(*) FROM poems p
                JOIN authors a ON p.author_id = a.id
                JOIN dynasties d ON a.dynasty_id = d.id
                WHERE d.name LIKE %s
            """, (f'%{text_type}%',))
            count = cursor.fetchone()[0]
            if count > 0:
                logger.info(f"{text_type} 文献: {count} 条记录")
        
        conn.close()
        
        # 与预期数据量对比
        expected_total = 80000  # 预期总诗词数量
        actual_total = poem_count
        completion_rate = (actual_total / expected_total) * 100
        
        logger.info(f"\n=== 完成度评估 ===")
        logger.info(f"预期总诗词: {expected_total}")
        logger.info(f"实际导入: {actual_total}")
        logger.info(f"完成度: {completion_rate:.2f}%")
        
        if completion_rate < 80:
            logger.warning("完成度低于预期，可能存在数据丢失")
        else:
            logger.info("数据导入完成度良好")
            
    except Exception as e:
        logger.error(f"验证导入结果失败: {e}", exc_info=True)

if __name__ == "__main__":
    print("开始恢复数据导入...")
    resume_import()
    print("数据导入恢复完成！")