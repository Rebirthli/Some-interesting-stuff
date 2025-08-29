-- 创建必要的扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 优先级方案：优先使用pgroonga，如果不可用则使用标准全文搜索
DO $$
DECLARE
    pgroonga_available BOOLEAN := FALSE;
    search_config TEXT;
BEGIN
    -- 尝试创建pgroonga扩展
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pgroonga;
        pgroonga_available := TRUE;
        RAISE NOTICE 'pgroonga扩展已启用，将使用高性能多语言全文搜索';
    EXCEPTION WHEN OTHERS THEN
        pgroonga_available := FALSE;
        RAISE NOTICE 'pgroonga扩展不可用，将使用标准PostgreSQL全文搜索配置';
    END;
    
    -- 根据pgroonga可用性设置搜索配置
    IF pgroonga_available THEN
        search_config := 'pgroonga_chinese';
        -- 创建pgroonga中文搜索配置（如果需要）
        -- pgroonga会自动处理中文分词，通常不需要额外配置
    ELSE
        search_config := 'simple';
        -- 使用简单配置进行标准全文搜索
    END IF;
    
    -- 将配置信息存储到自定义表中，供应用程序使用
    CREATE TABLE IF NOT EXISTS search_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    INSERT INTO search_config (key, value) VALUES 
        ('search_engine', CASE WHEN pgroonga_available THEN 'pgroonga' ELSE 'standard' END),
        ('text_search_config', search_config)
    ON CONFLICT (key) DO UPDATE SET 
        value = EXCLUDED.value, 
        updated_at = CURRENT_TIMESTAMP;
        
END
$$;

-- 创建朝代表
CREATE TABLE IF NOT EXISTS dynasties (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE
);

-- 创建作者表
CREATE TABLE IF NOT EXISTS authors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    dynasty_id INTEGER NOT NULL REFERENCES dynasties(id),
    CONSTRAINT uq_author_dynasty UNIQUE(name, dynasty_id)
);

-- 创建诗词表
CREATE TABLE IF NOT EXISTS poems (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    author_id INTEGER NOT NULL REFERENCES authors(id),
    full_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建诗句表（用于向量搜索）
CREATE TABLE IF NOT EXISTS lines (
    id SERIAL PRIMARY KEY,
    poem_id INTEGER NOT NULL REFERENCES poems(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 为poems表创建索引（优先级方案）
DO $$
DECLARE
    search_engine TEXT;
    text_config TEXT;
BEGIN
    -- 获取搜索引擎配置
    SELECT value INTO search_engine FROM search_config WHERE key = 'search_engine';
    SELECT value INTO text_config FROM search_config WHERE key = 'text_search_config';
    
    -- 创建基础索引
    CREATE INDEX IF NOT EXISTS idx_poems_author_id ON poems(author_id);
    CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name);
    CREATE INDEX IF NOT EXISTS idx_dynasties_name ON dynasties(name);
    
    -- 根据搜索引擎类型创建不同的全文搜索索引
    IF search_engine = 'pgroonga' THEN
        -- 使用pgroonga索引（高性能多语言全文搜索）
        RAISE NOTICE '创建pgroonga索引以支持高性能中文全文搜索';
        
        -- 删除可能存在的标准GIN索引
        DROP INDEX IF EXISTS idx_poems_title;
        DROP INDEX IF EXISTS idx_poems_content;
        
        -- 创建pgroonga索引
        CREATE INDEX IF NOT EXISTS idx_poems_title_pgroonga ON poems USING pgroonga (title);
        CREATE INDEX IF NOT EXISTS idx_poems_content_pgroonga ON poems USING pgroonga (full_content);
        
    ELSE
        -- 使用标准PostgreSQL全文搜索
        RAISE NOTICE '创建标准GIN索引以支持基础全文搜索';
        
        -- 删除可能存在的pgroonga索引
        DROP INDEX IF EXISTS idx_poems_title_pgroonga;
        DROP INDEX IF EXISTS idx_poems_content_pgroonga;
        
        -- 创建标准GIN索引
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_poems_title ON poems USING GIN(to_tsvector(%L, title))', text_config);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_poems_content ON poems USING GIN(to_tsvector(%L, full_content))', text_config);
    END IF;
    
    -- 始终创建pg_trgm索引用于模糊匹配
    CREATE INDEX IF NOT EXISTS idx_poems_content_trgm ON poems USING GIN(full_content gin_trgm_ops);
    
END
$$;

-- 为lines表创建索引（优先级方案）
DO $$
DECLARE
    search_engine TEXT;
    text_config TEXT;
BEGIN
    -- 获取搜索引擎配置
    SELECT value INTO search_engine FROM search_config WHERE key = 'search_engine';
    SELECT value INTO text_config FROM search_config WHERE key = 'text_search_config';
    
    -- 创建基础索引
    CREATE INDEX IF NOT EXISTS idx_lines_poem_id ON lines(poem_id);
    
    -- 根据搜索引擎类型创建不同的全文搜索索引
    IF search_engine = 'pgroonga' THEN
        -- 使用pgroonga索引
        RAISE NOTICE '为lines表创建pgroonga索引';
        
        -- 删除可能存在的标准GIN索引
        DROP INDEX IF EXISTS idx_lines_content;
        
        -- 创建pgroonga索引
        CREATE INDEX IF NOT EXISTS idx_lines_content_pgroonga ON lines USING pgroonga (content);
        
    ELSE
        -- 使用标准PostgreSQL全文搜索
        RAISE NOTICE '为lines表创建标准GIN索引';
        
        -- 删除可能存在的pgroonga索引
        DROP INDEX IF EXISTS idx_lines_content_pgroonga;
        
        -- 创建标准GIN索引
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_lines_content ON lines USING GIN(to_tsvector(%L, content))', text_config);
    END IF;
    
    -- 始终创建pg_trgm索引用于模糊匹配
    CREATE INDEX IF NOT EXISTS idx_lines_content_trgm ON lines USING GIN(content gin_trgm_ops);
    
END
$$;

-- 向量索引将在数据导入完成后创建，以提高导入性能
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_lines_embedding ON lines USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);