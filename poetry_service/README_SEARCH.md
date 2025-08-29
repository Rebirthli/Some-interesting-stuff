# 优先级搜索系统使用说明

## 概述

本系统实现了一个智能的优先级搜索方案，自动检测并优先使用高性能的pgroonga扩展，如果不可用则回退到标准的PostgreSQL全文搜索。

## 系统架构

### 双引擎搜索设计

1. **引擎一：关键词搜索**
   - 优先使用pgroonga（高性能多语言全文搜索）
   - 回退使用标准PostgreSQL全文搜索
   - 使用pg_trgm进行模糊匹配

2. **引擎二：语义搜索**
   - 使用pgvector进行向量相似性搜索
   - 支持阿里云通义千问的text-embedding-v4模型(1536维)

## 自动配置过程

### 初始化阶段

1. **扩展检测**：系统启动时自动尝试加载pgroonga扩展
2. **配置存储**：将检测结果存储在`search_config`表中
3. **索引创建**：根据可用的扩展动态创建相应的索引

### 配置表结构

```sql
search_config (
    key TEXT PRIMARY KEY,           -- 配置键
    value TEXT NOT NULL,            -- 配置值
    updated_at TIMESTAMP            -- 更新时间
)
```

配置项：
- `search_engine`: 'pgroonga' 或 'standard'
- `text_search_config`: 具体的文本搜索配置

## 搜索功能

### 1. 查询搜索配置

```sql
-- 查看当前搜索引擎配置
SELECT * FROM show_search_config();
```

### 2. 全文搜索（诗词表）

```sql
-- 搜索诗词（自动选择最优搜索引擎）
SELECT * FROM search_poems_fulltext('春江花月夜', 10);
```

### 3. 全文搜索（诗句表）

```sql
-- 搜索诗句
SELECT * FROM search_lines_fulltext('明月几时有', 10);
```

### 4. 模糊搜索

```sql
-- 模糊搜索（使用pg_trgm）
SELECT * FROM search_poems_fuzzy('李白', 10);
```

## 搜索引擎对比

### PGroonga（优先选择）

**优势：**
- 高性能多语言全文搜索
- 原生支持中文分词
- 搜索速度快
- 支持复杂搜索表达式

**搜索语法：**
```sql
-- pgroonga语法示例
WHERE content &@~ '春江花月'      -- 全文搜索
WHERE content &@* '春江.*月'     -- 正则表达式搜索
```

### 标准PostgreSQL（回退选择）

**优势：**
- 内置支持，无需额外扩展
- 稳定可靠
- 文档丰富

**搜索语法：**
```sql
-- 标准语法示例
WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', '春江花月')
```

## 应用程序集成

### FastAPI集成示例

```python
import asyncpg

async def get_search_engine():
    """获取当前搜索引擎类型"""
    async with get_db_connection() as conn:
        result = await conn.fetchrow("SELECT * FROM show_search_config()")
        return result

async def search_poems(query: str, limit: int = 10):
    """智能搜索诗词"""
    async with get_db_connection() as conn:
        # 使用数据库函数自动选择最优搜索策略
        results = await conn.fetch(
            "SELECT * FROM search_poems_fulltext($1, $2)",
            query, limit
        )
        return results

async def search_fuzzy(query: str, limit: int = 10):
    """模糊搜索（适用于所有情况）"""
    async with get_db_connection() as conn:
        results = await conn.fetch(
            "SELECT * FROM search_poems_fuzzy($1, $2)",
            query, limit
        )
        return results
```

### 搜索策略选择

```python
async def intelligent_search(query: str, limit: int = 10):
    """智能搜索：结合全文搜索和模糊搜索"""
    
    # 1. 尝试全文搜索
    fulltext_results = await search_poems(query, limit)
    
    if len(fulltext_results) >= limit // 2:
        return fulltext_results
    
    # 2. 如果全文搜索结果不足，补充模糊搜索
    fuzzy_results = await search_fuzzy(query, limit - len(fulltext_results))
    
    # 3. 合并结果并去重
    return merge_and_deduplicate(fulltext_results, fuzzy_results)
```

## 性能优化

### 索引策略

1. **pgroonga模式**：
   - 使用pgroonga索引进行全文搜索
   - 保留pg_trgm索引用于模糊搜索

2. **标准模式**：
   - 使用GIN索引进行全文搜索
   - 保留pg_trgm索引用于模糊搜索

### 查询优化建议

1. **优先使用全文搜索**：精确度高，性能好
2. **模糊搜索作为补充**：处理变体和错别字
3. **向量搜索处理语义**：处理抽象概念查询

## 部署和维护

### Docker构建

```bash
# 构建数据库服务
docker compose build db

# 启动服务
docker compose up -d db
```

### 监控和诊断

```sql
-- 检查当前配置
SELECT * FROM show_search_config();

-- 检查可用扩展
SELECT name, default_version, installed_version 
FROM pg_available_extensions 
WHERE name IN ('pgroonga', 'vector', 'pg_trgm');

-- 检查索引使用情况
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE tablename IN ('poems', 'lines');
```

## 故障排除

### 常见问题

1. **pgroonga不可用**：
   - 系统会自动回退到标准搜索
   - 检查日志中的NOTICE消息

2. **搜索结果不准确**：
   - 尝试使用模糊搜索
   - 检查搜索配置是否正确

3. **性能问题**：
   - 检查索引是否正确创建
   - 分析查询执行计划

### 日志监控

在PostgreSQL日志中查找以下消息：
- `pgroonga扩展已启用`：表示使用高性能搜索
- `pgroonga扩展不可用`：表示回退到标准搜索
- `创建pgroonga索引`：索引创建成功
- `创建标准GIN索引`：使用标准索引

这个优先级搜索系统确保了在各种环境下都能提供最佳的搜索性能和用户体验。