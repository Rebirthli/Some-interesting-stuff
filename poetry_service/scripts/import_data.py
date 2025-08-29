#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能古诗词搜索服务 - 数据导入脚本 (V10 - 模型自适应最终版)
- 智能判断模型版本，自动适配API参数（是否包含dimensions）
- 修复了所有已知的数据库和数据兼容性问题
- 包含了健壮的API请求和错误处理逻辑
"""
import os
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict

import psycopg2
from psycopg2.extras import execute_batch
import opencc
import requests
from dotenv import load_dotenv
from tqdm import tqdm

# --- 配置日志 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('import_data.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
PROCESSED_FILES_LOG = 'processed_files.log'


class PoetryImporter:
    def __init__(self):
        """初始化导入器"""
        self._load_env()
        self._init_config()
        self._init_services()

    def _load_env(self):
        """加载环境变量"""
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

    def _init_config(self):
        """初始化所有配置参数"""
        # API 配置
        self.ali_api_key = os.getenv('ALI_API_KEY')
        if not self.ali_api_key:
            raise ValueError("请在.env文件中设置ALI_API_KEY")
        self.ali_api_url = os.getenv('ALI_API_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings')
        self.embedding_model = os.getenv('EMBEDDING_MODEL', 'text-embedding-v1')
        self.embedding_dimensions = int(os.getenv('EMBEDDING_DIMENSIONS', 1536))  # v3/v4模型需要

        # 数据库配置
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': os.getenv('POSTGRES_PORT', '5432'),
            'database': os.getenv('POSTGRES_DB', 'poetry_db'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'postgres123')
        }

        # 数据源路径
        self.poetry_data_path = Path(__file__).parent.parent.parent / 'chinese-poetry'
        if not self.poetry_data_path.exists():
            raise FileNotFoundError(f"找不到诗词数据目录: {self.poetry_data_path}")

        # 性能与批处理配置
        self.embedding_api_batch_size = 10  # 阿里云限制为25，使用10作为安全边际
        self.db_batch_size = 100
        self.max_retries = 3
        self.retry_delay = 2
        self.max_workers = int(os.getenv('MAX_WORKERS', 8))

    def _init_services(self):
        """初始化服务和映射表"""
        self.converter = opencc.OpenCC('t2s')
        self.sentence_pattern = re.compile(r'[。！？]')
        self.noise_pattern = re.compile(r'\[\d+\]|【.*?】|（.*?）|\(.*?\)|<.*?>')

        # 从路径推断作者
        self.path_author_map = {
            'caocao': '曹操', 'nalanxingde': '纳兰性德', 'shijing': '佚名', 'sishuwujing/lunyu': '孔子',
        }

        # 从路径推断朝代
        self.path_keyword_map = {
            'tang': '唐代', 'quan_tang_shi': '唐代', 'song': '宋代', 'yuan': '元代', 'yuanqu': '元代',
            'ming': '明代', 'qing': '清代', 'wudai': '五代十国', 'huajianji': '五代十国', 'nantang': '五代十国',
            'jin': '两晋', 'nanbeichao': '南北朝', 'sui': '隋代', 'caocao': '两汉', 'jianan': '两汉',
            'shijing': '先秦', 'chuci': '先秦', 'sishuwujing': '先秦', 'lunyu': '先秦',
        }

        logger.info("正在预扫描数据以建立作者->朝代映射...")
        self.author_dynasty_map = self._create_author_dynasty_map()
        logger.info(f"成功为 {len(self.author_dynasty_map)} 位作者建立了朝代映射。")

    def _create_author_dynasty_map(self) -> Dict[str, str]:
        """预扫描所有文件，建立作者到其最常见朝代的映射"""
        author_dynasties = defaultdict(list)
        for file_path in self.load_json_files():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                poems_list, _ = self._extract_poems_from_data(data)
                for poem in poems_list:
                    if isinstance(poem, dict):
                        author, dynasty = poem.get('author'), poem.get('dynasty')
                        if author and dynasty:
                            author_s = self.converter.convert(str(author).strip())[:200]
                            dynasty_s = self.converter.convert(str(dynasty).strip())[:200]
                            author_dynasties[author_s].append(dynasty_s)
            except Exception:
                continue
        return {author: Counter(dynasties).most_common(1)[0][0] for author, dynasties in author_dynasties.items() if
                dynasties}

    def _extract_poems_from_data(self, data: Any) -> Tuple[List[Dict], Optional[str]]:
        """从不同结构的JSON数据中智能提取诗词列表和文件级作者"""
        poems = []
        fallback_author = None
        
        if isinstance(data, list):
            # 标准诗词列表格式
            for item in data:
                if isinstance(item, dict):
                    poems.append(item)
            return poems, None
            
        elif isinstance(data, dict):
            # 提取文件级作者信息
            fallback_author = data.get('author')
            
            # 诗经格式：包含chapter和section
            if 'content' in data and isinstance(data['content'], list):
                # 诗经、楚辞等经典文献格式
                for item in data['content']:
                    if isinstance(item, dict):
                        # 诗经格式：title, chapter, section, content
                        if 'content' in item and isinstance(item['content'], list):
                            poems.append({
                                'title': item.get('title', '无题'),
                                'author': item.get('author', fallback_author or '佚名'),
                                'dynasty': item.get('dynasty', self._infer_dynasty_from_content(item)),
                                'paragraphs': item['content']
                            })
                        else:
                            poems.append(item)
                            
            # 论语、四书五经格式
            elif 'paragraphs' in data and isinstance(data['paragraphs'], list):
                # 论语等经典格式
                if 'chapter' in data:
                    # 按章节组织的经典
                    for paragraph in data['paragraphs']:
                        poems.append({
                            'title': data['chapter'],
                            'author': fallback_author or '孔子',
                            'dynasty': '先秦',
                            'paragraphs': [paragraph]
                        })
                else:
                    # 标准诗词格式
                    poems.append(data)
                    
            # 章节嵌套格式
            elif 'chapters' in data and isinstance(data['chapters'], list):
                for chapter in data['chapters']:
                    if isinstance(chapter, dict):
                        # 处理章节中的段落
                        if 'paragraphs' in chapter and isinstance(chapter['paragraphs'], list):
                            for para in chapter['paragraphs']:
                                poems.append({
                                    'title': chapter.get('title') or chapter.get('chapter', '未知篇章'),
                                    'author': chapter.get('author', fallback_author),
                                    'dynasty': chapter.get('dynasty', data.get('dynasty')),
                                    'paragraphs': [para] if isinstance(para, str) else para
                                })
                        else:
                            # 直接添加章节作为一首诗
                            poems.append({
                                'title': chapter.get('title', '未知篇章'),
                                'author': chapter.get('author', fallback_author),
                                'dynasty': chapter.get('dynasty', data.get('dynasty')),
                                'paragraphs': chapter.get('paragraphs', [])
                            })
                            
            # 元曲等特殊格式
            elif 'sections' in data and isinstance(data['sections'], list):
                for section in data['sections']:
                    if isinstance(section, dict):
                        poems.append({
                            'title': section.get('title', data.get('title', '无题')),
                            'author': section.get('author', fallback_author),
                            'dynasty': section.get('dynasty', data.get('dynasty')),
                            'paragraphs': section.get('paragraphs', section.get('content', []))
                        })
                        
            # 单首诗词格式
            elif 'title' in data and ('paragraphs' in data or 'content' in data):
                poems.append(data)
                
            # 蒙学经典格式
            elif 'text' in data and isinstance(data['text'], list):
                for text_item in data['text']:
                    if isinstance(text_item, dict):
                        poems.append({
                            'title': text_item.get('title', data.get('title', '无题')),
                            'author': text_item.get('author', fallback_author),
                            'dynasty': text_item.get('dynasty', data.get('dynasty', '未知')),
                            'paragraphs': text_item.get('paragraphs', text_item.get('content', []))
                        })
                        
        # 处理非标准格式的古典文献
        if not poems and isinstance(data, dict):
            # 尝试从各种可能的字段组合中提取内容
            possible_fields = ['content', 'paragraphs', 'text', 'verses', 'lines']
            for field in possible_fields:
                if field in data and isinstance(data[field], list):
                    content_list = data[field]
                    # 检查内容是否为字符串列表
                    if content_list and isinstance(content_list[0], str):
                        poems.append({
                            'title': data.get('title', '无题'),
                            'author': data.get('author', fallback_author),
                            'dynasty': data.get('dynasty', '未知'),
                            'paragraphs': content_list
                        })
                    break
                    
        # 处理古典文献的特殊结构
        if not poems and isinstance(data, dict):
            # 论语、四书五经等经典
            if any(keyword in str(data).lower() for keyword in ['论语', '大学', '中庸', '孟子']):
                # 提取论语等经典内容
                if 'paragraphs' in data and isinstance(data['paragraphs'], list):
                    title = data.get('chapter', data.get('title', '经典篇章'))
                    poems.append({
                        'title': title,
                        'author': '孔子',
                        'dynasty': '先秦',
                        'paragraphs': data['paragraphs']
                    })
            # 诗经、楚辞
            elif any(keyword in str(data).lower() for keyword in ['诗经', '楚辞']):
                if isinstance(data, dict) and 'title' in data:
                    poems.append({
                        'title': data['title'],
                        'author': data.get('author', '佚名'),
                        'dynasty': data.get('dynasty', '先秦'),
                        'paragraphs': data.get('paragraphs', data.get('content', []))
                    })
        
        return poems, fallback_author

    def process_poem_data(self, poem_data: Dict, file_path: Path, fallback_author: Optional[str] = None) -> Optional[
        Dict]:
        """处理单个诗词/典籍数据，进行清洗和规范化"""
        try:
            # 限制标题长度
            title = self.converter.convert(str(poem_data.get('title', '无题')).strip())[:500]

            author_str = poem_data.get('author', fallback_author)
            if not author_str:
                file_path_str = file_path.as_posix().lower()
                for keyword, author_name in self.path_author_map.items():
                    if keyword in file_path_str:
                        author_str = author_name
                        break
                else:
                    author_str = '佚名'

            # 限制作者和朝代名称长度
            author = self.converter.convert(author_str.strip())[:200]
            dynasty = self.converter.convert(str(poem_data.get('dynasty', '')).strip())[:200]
            content_list = poem_data.get('paragraphs', [])
            content = self.converter.convert(''.join(content_list))

            if not content: return None
            if not dynasty: dynasty = self._infer_dynasty(author, file_path)

            return {'title': title, 'author': author, 'dynasty': dynasty, 'content': content}
        except Exception:
            return None

    def get_batch_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        """健壮地获取批量文本的embedding向量，智能适配模型参数"""
        if not texts: return []

        valid_texts = [text for text in texts if text and not text.isspace()]
        if not valid_texts: return [None] * len(texts)

        # 根据模型名称智能构建请求体
        data = {'model': self.embedding_model, 'input': valid_texts}
        if 'v3' in self.embedding_model or 'v4' in self.embedding_model:
            data['dimensions'] = self.embedding_dimensions

        headers = {'Authorization': f'Bearer {self.ali_api_key}', 'Content-Type': 'application/json'}

        api_results = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(self.ali_api_url, headers=headers, json=data, timeout=60)
                response.raise_for_status()
                result_json = response.json()
                if 'data' in result_json:
                    api_results = [item['embedding'] for item in sorted(result_json['data'], key=lambda x: x['index'])]
                    break
                else:
                    logger.error(f"API响应格式错误: {result_json}")
            except requests.exceptions.HTTPError as e:
                logger.error(
                    f"API请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e.response.status_code} {e.response.reason}")
                logger.error(f"--> 响应内容: {e.response.text}")
                if e.response.status_code == 400: break
            except Exception as e:
                logger.error(f"API调用时发生未知异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")

            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay * (attempt + 1))

        # 将结果按原始顺序"复水"
        results = [None] * len(texts)
        if api_results:
            valid_indices = [i for i, text in enumerate(texts) if text and not text.isspace()]
            for i, embedding in enumerate(api_results):
                original_index = valid_indices[i]
                results[original_index] = embedding

        return results

    def process_and_insert_batch(self, poem_batch: List[Dict], conn: psycopg2.extensions.connection):
        """处理并插入一个批次的诗词数据"""
        if not poem_batch: return
        cursor = conn.cursor()
        try:
            dynasties = list(set(p['dynasty'] for p in poem_batch))
            authors = list(set((p['author'], p['dynasty']) for p in poem_batch))

            dynasty_map = {}
            if dynasties:
                execute_batch(cursor, "INSERT INTO dynasties (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                              [(d,) for d in dynasties])
                cursor.execute("SELECT id, name FROM dynasties WHERE name = ANY(%s)", (dynasties,))
                dynasty_map = {name: id for id, name in cursor.fetchall()}

            authors_to_insert = [(name, dynasty_map.get(dynasty)) for name, dynasty in authors if
                                 dynasty_map.get(dynasty)]
            if authors_to_insert:
                execute_batch(cursor,
                              "INSERT INTO authors (name, dynasty_id) VALUES (%s, %s) ON CONFLICT ON CONSTRAINT uq_author_dynasty DO NOTHING",
                              authors_to_insert)

            author_map = {}
            if authors:
                # Build a VALUES clause to avoid the composite type issue
                placeholders = ', '.join(['(%s, %s)'] * len(authors))
                query = f"""
                    SELECT a.id, a.name, d.name 
                    FROM authors a 
                    JOIN dynasties d ON a.dynasty_id = d.id 
                    WHERE (a.name, d.name) IN ({placeholders})
                """
                params = [item for pair in authors for item in pair]
                cursor.execute(query, params)
                author_map = {(author_name, dynasty_name): id for id, author_name, dynasty_name in cursor.fetchall()}

            poems_to_insert = [(p['title'], author_map.get((p['author'], p['dynasty'])), p['content']) for p in
                               poem_batch]
            cursor.execute("CREATE TEMP TABLE temp_poems (title TEXT, author_id INT, full_content TEXT) ON COMMIT DROP")
            execute_batch(cursor, "INSERT INTO temp_poems VALUES (%s, %s, %s)", poems_to_insert)
            cursor.execute("INSERT INTO poems (title, author_id, full_content) SELECT * FROM temp_poems RETURNING id")
            poem_ids = [row[0] for row in cursor.fetchall()]

            all_sentences, poem_sentence_counts = [], []
            for poem in poem_batch:
                sentences = self.split_sentences(poem['content'])
                all_sentences.extend(sentences)
                poem_sentence_counts.append(len(sentences))

            if all_sentences:
                all_embeddings = []
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    batches = [all_sentences[i:i + self.embedding_api_batch_size] for i in
                               range(0, len(all_sentences), self.embedding_api_batch_size)]
                    future_to_index = {executor.submit(self.get_batch_embeddings, batch): i for i, batch in
                                       enumerate(batches)}
                    results_in_order = [None] * len(batches)
                    for future in as_completed(future_to_index):
                        index = future_to_index[future]
                        results_in_order[index] = future.result()
                    for result_batch in results_in_order:
                        if result_batch: all_embeddings.extend(result_batch)

                lines_to_insert, emb_idx = [], 0
                for i, poem_id in enumerate(poem_ids):
                    for _ in range(poem_sentence_counts[i]):
                        if emb_idx < len(all_embeddings) and all_embeddings[emb_idx]:
                            lines_to_insert.append((poem_id, all_sentences[emb_idx], all_embeddings[emb_idx]))
                        emb_idx += 1
                if lines_to_insert:
                    execute_batch(cursor, "INSERT INTO lines (poem_id, content, embedding) VALUES (%s, %s, %s)",
                                  lines_to_insert)

            conn.commit()
        except Exception as e:
            logger.error(f"处理数据库批次失败: {e}", exc_info=True)
            conn.rollback()

    def run_import(self):
        """执行完整的数据导入流程"""
        logger.info("开始数据导入流程...")
        conn = self.connect_db()
        try:
            processed_files = self.load_processed_files()
            files_to_process = [f for f in self.load_json_files() if str(f) not in processed_files]
            if not files_to_process:
                logger.info("所有文件均已处理。")
                return

            logger.info(f"需要处理 {len(files_to_process)} 个新文件。")
            for file_path in tqdm(files_to_process, desc="导入文件", unit="file"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    poems_list, file_level_author = self._extract_poems_from_data(data)
                    if not poems_list:
                        logger.debug(f"文件 {file_path.name} 未提取到诗词内容，跳过。")
                        self.mark_file_as_processed(file_path)
                        continue

                    poem_batch = []
                    for poem_data in poems_list:
                        if not isinstance(poem_data, dict): continue
                        processed = self.process_poem_data(poem_data, file_path, fallback_author=file_level_author)
                        if processed:
                            poem_batch.append(processed)
                        if len(poem_batch) >= self.db_batch_size:
                            self.process_and_insert_batch(poem_batch, conn)
                            poem_batch = []

                    if poem_batch:
                        self.process_and_insert_batch(poem_batch, conn)

                    self.mark_file_as_processed(file_path)
                except Exception as e:
                    logger.error(f"处理文件 {file_path} 时发生严重错误: {e}", exc_info=True)
                    conn.rollback()
        finally:
            conn.close()
            logger.info("数据导入流程结束。")

    def connect_db(self) -> psycopg2.extensions.connection:
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.autocommit = False
            return conn
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def split_sentences(self, text: str) -> List[str]:
        text_cleaned = self.noise_pattern.sub('', text)
        text_cleaned = re.sub(r'\s+', '', text_cleaned)
        sentences = self.sentence_pattern.split(text_cleaned)
        return [s.strip() for s in sentences if len(s.strip()) >= 4]

    def load_json_files(self) -> List[Path]:
        return sorted([Path(root) / file for root, _, files in os.walk(self.poetry_data_path) for file in files if
                       file.endswith('.json')])

    def load_processed_files(self) -> Set[str]:
        if not os.path.exists(PROCESSED_FILES_LOG): return set()
        with open(PROCESSED_FILES_LOG, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f)

    def mark_file_as_processed(self, file_path: Path):
        with open(PROCESSED_FILES_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{file_path}\n")

    def _infer_dynasty_from_content(self, poem_data: Dict) -> str:
        """从内容推断朝代"""
        # 检查是否有明确的朝代信息
        dynasty = poem_data.get('dynasty')
        if dynasty:
            return str(dynasty)
        return "未知"

    def _infer_dynasty(self, author: str, file_path: Path) -> str:
        """从作者和文件路径推断朝代"""
        if author in self.author_dynasty_map:
            return self.author_dynasty_map[author]
            
        file_path_str = file_path.as_posix().lower()
        
        # 古典文献特殊处理
        classical_texts = {
            '诗经': '先秦',
            '楚辞': '先秦',
            '论语': '先秦',
            '孟子': '先秦',
            '大学': '先秦',
            '中庸': '先秦',
            '四书五经': '先秦',
            '蒙学': '古代',
            'shijing': '先秦',
            'chuci': '先秦',
            'lunyu': '先秦',
            'mengzi': '先秦',
            'daxue': '先秦',
            'zhongyong': '先秦',
            'sishuwujing': '先秦',
            'mengxue': '古代'
        }
        
        for text, dynasty in classical_texts.items():
            if text.lower() in file_path_str.lower():
                return dynasty
                
        # 标准朝代映射
        for keyword, dynasty in self.path_keyword_map.items():
            if keyword in file_path_str:
                return dynasty
                
        return "未知"


if __name__ == "__main__":
    importer = PoetryImporter()
    importer.run_import()