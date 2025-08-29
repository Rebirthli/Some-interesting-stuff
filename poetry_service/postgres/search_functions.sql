-- 搜索配置查询函数
-- 这个文件包含了用于查询搜索引擎配置和执行搜索的函数

-- 获取当前搜索引擎类型
CREATE OR REPLACE FUNCTION get_search_engine()
RETURNS TEXT AS $$
DECLARE
    engine TEXT;
BEGIN
    SELECT value INTO engine FROM search_config WHERE key = 'search_engine';
    RETURN COALESCE(engine, 'standard');
END;
$$ LANGUAGE plpgsql;

-- 获取文本搜索配置
CREATE OR REPLACE FUNCTION get_text_search_config()
RETURNS TEXT AS $$
DECLARE
    config TEXT;
BEGIN
    SELECT value INTO config FROM search_config WHERE key = 'text_search_config';
    RETURN COALESCE(config, 'simple');
END;
$$ LANGUAGE plpgsql;

-- 动态执行全文搜索（poems表）
CREATE OR REPLACE FUNCTION search_poems_fulltext(search_query TEXT, limit_count INTEGER DEFAULT 10)
RETURNS TABLE(
    id INTEGER,
    title VARCHAR(500),
    author VARCHAR(200),
    dynasty VARCHAR(100),
    full_content TEXT,
    rank_score REAL
) AS $$
DECLARE
    engine TEXT;
    query_sql TEXT;
BEGIN
    -- 获取搜索引擎类型
    engine := get_search_engine();
    
    IF engine = 'pgroonga' THEN
        -- 使用pgroonga全文搜索
        query_sql := '
            SELECT p.id, p.title, a.name as author, d.name as dynasty, p.full_content,
                   pgroonga_score(p.tableoid, p.ctid) AS rank_score
            FROM poems p
            JOIN authors a ON p.author_id = a.id
            JOIN dynasties d ON a.dynasty_id = d.id
            WHERE (p.title &@~ $1 OR p.full_content &@~ $1)
            ORDER BY pgroonga_score(p.tableoid, p.ctid) DESC
            LIMIT $2';
    ELSE
        -- 使用标准PostgreSQL全文搜索
        query_sql := format('
            SELECT p.id, p.title, a.name as author, d.name as dynasty, p.full_content,
                   ts_rank(to_tsvector(%L, p.full_content), plainto_tsquery(%L, $1)) AS rank_score
            FROM poems p
            JOIN authors a ON p.author_id = a.id
            JOIN dynasties d ON a.dynasty_id = d.id
            WHERE (to_tsvector(%L, p.title) @@ plainto_tsquery(%L, $1)
                   OR to_tsvector(%L, p.full_content) @@ plainto_tsquery(%L, $1))
            ORDER BY rank_score DESC
            LIMIT $2', 
            get_text_search_config(), get_text_search_config(),
            get_text_search_config(), get_text_search_config(),
            get_text_search_config(), get_text_search_config());
    END IF;
    
    RETURN QUERY EXECUTE query_sql USING search_query, limit_count;
END;
$$ LANGUAGE plpgsql;

-- 动态执行全文搜索（lines表）
CREATE OR REPLACE FUNCTION search_lines_fulltext(search_query TEXT, limit_count INTEGER DEFAULT 10)
RETURNS TABLE(
    id INTEGER,
    poem_id INTEGER,
    content TEXT,
    rank_score REAL
) AS $$
DECLARE
    engine TEXT;
    query_sql TEXT;
BEGIN
    -- 获取搜索引擎类型
    engine := get_search_engine();
    
    IF engine = 'pgroonga' THEN
        -- 使用pgroonga全文搜索
        query_sql := '
            SELECT l.id, l.poem_id, l.content,
                   pgroonga_score(tableoid, ctid) AS rank_score
            FROM lines l
            WHERE l.content &@~ $1
            ORDER BY pgroonga_score(tableoid, ctid) DESC
            LIMIT $2';
    ELSE
        -- 使用标准PostgreSQL全文搜索
        query_sql := format('
            SELECT l.id, l.poem_id, l.content,
                   ts_rank(to_tsvector(%L, l.content), plainto_tsquery(%L, $1)) AS rank_score
            FROM lines l
            WHERE to_tsvector(%L, l.content) @@ plainto_tsquery(%L, $1)
            ORDER BY rank_score DESC
            LIMIT $2', 
            get_text_search_config(), get_text_search_config(),
            get_text_search_config(), get_text_search_config());
    END IF;
    
    RETURN QUERY EXECUTE query_sql USING search_query, limit_count;
END;
$$ LANGUAGE plpgsql;

-- 模糊搜索（使用pg_trgm，适用于所有情况）
CREATE OR REPLACE FUNCTION search_poems_fuzzy(search_query TEXT, limit_count INTEGER DEFAULT 10)
RETURNS TABLE(
    id INTEGER,
    title VARCHAR(500),
    author VARCHAR(200),
    dynasty VARCHAR(100),
    full_content TEXT,
    similarity_score REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.title, a.name as author, d.name as dynasty, p.full_content,
           GREATEST(
               similarity(p.title, search_query),
               similarity(p.full_content, search_query)
           ) AS similarity_score
    FROM poems p
    JOIN authors a ON p.author_id = a.id
    JOIN dynasties d ON a.dynasty_id = d.id
    WHERE (p.title % search_query OR p.full_content % search_query)
    ORDER BY similarity_score DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- 显示当前搜索配置
CREATE OR REPLACE FUNCTION show_search_config()
RETURNS TABLE(
    search_engine TEXT,
    text_search_config TEXT,
    pgroonga_available BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        get_search_engine() as search_engine,
        get_text_search_config() as text_search_config,
        (get_search_engine() = 'pgroonga') as pgroonga_available;
END;
$$ LANGUAGE plpgsql;