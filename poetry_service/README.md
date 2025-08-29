# 智能古诗词搜索服务

基于双引擎架构的古诗词智能搜索API服务，支持关键词搜索和语义搜索。

## 功能特性

### 🔍 双引擎搜索架构
- **关键词搜索引擎**: 基于PostgreSQL全文搜索(`zhparser`)和模糊匹配(`pg_trgm`)
- **语义搜索引擎**: 基于阿里云通义千问Embedding API和向量数据库(`pgvector`)

### 📚 数据源
- 使用开源项目 `chinese-poetry` 作为数据源
- 自动繁简转换
- 支持按句子分割和向量化

### 🚀 技术栈
- **后端**: FastAPI + Python 3.10
- **数据库**: PostgreSQL 14 + pgvector + zhparser + pg_trgm
- **向量化**: 阿里云通义千问 text-embedding-v4 (1536维)
- **部署**: Docker + Docker Compose

## 项目结构

```
poetry_service/
├── .env                    # 环境变量配置
├── .gitignore             # Git忽略文件
├── requirements.txt       # 统一Python依赖文件
├── docker-compose.yml     # Docker编排配置
├── postgres/              # PostgreSQL配置
│   ├── Dockerfile         # 数据库镜像构建
│   └── init.sql          # 数据库初始化脚本
├── fastapi_app/          # FastAPI应用
│   ├── Dockerfile        # API服务镜像构建
│   ├── main.py          # 核心应用代码
│   └── requirements.txt  # FastAPI依赖（已合并到根目录）
└── scripts/              # 数据处理脚本
    ├── import_data.py   # 数据导入脚本
    └── requirements.txt # 脚本依赖（已合并到根目录）
```

## 快速开始

### 前提条件
1. 安装 Docker 和 Docker Compose
2. 获取阿里云通义千问API密钥
3. 确保与 `chinese-poetry` 数据目录并列
4. 安装 Python 3.10+ 和 pip

### 步骤1: 安装Python依赖
```bash
cd poetry_service
pip install -r requirements.txt
```

### 步骤2: 配置环境变量
编辑 `.env` 文件，设置你的阿里云API密钥：
```bash
ALI_API_KEY=your_actual_api_key_here
```

### 步骤3: 启动数据库服务
```bash
docker compose up -d db
```

### 步骤4: 等待数据库就绪
等待PostgreSQL完全启动并初始化完成。

### 步骤5: 导入数据
```bash
# 运行数据导入（使用统一安装的依赖）
python scripts/import_data.py
```

### 步骤6: 启动完整服务
```bash
docker compose up --build
```

## API端点

### 健康检查
```
GET /health
```

### 关键词搜索
```
GET /search?keyword=夜来风雨&limit=10&offset=0
```

### 语义搜索
```
GET /search/semantic?keywords=人流如织,车如流水&limit=10&offset=0
```

### API文档
```
GET /docs  # Swagger UI
GET /redoc # ReDoc
```

## 搜索示例

### 关键词搜索
搜索包含"夜来风雨"的诗词：
```bash
curl "http://localhost:8000/search?keyword=夜来 风雨"
```

### 语义搜索
搜索包含"离别"意象的诗词：
```bash
curl "http://localhost:8000/search/semantic?keywords=离别,思君"
```

### 多物象语义搜索
搜索包含"建筑"和"烟雾"意象的诗词：
```bash
curl "http://localhost:8000/search/semantic?keywords=黛瓦飞檐,扶栏生烟"
```

## 配置说明

### 环境变量
- `ALI_API_KEY`: 阿里云通义千问API密钥（必需）
- `EMBEDDING_MODEL`: Embedding模型名称（默认: text-embedding-v4）
- `EMBEDDING_DIMENSION`: 向量维度（默认: 1536）
- `POSTGRES_*`: 数据库连接配置

### 性能调优
- 数据库连接池: 2-20个连接
- 批量embedding: 每批10个句子
- 向量索引: IVFFlat with 100 lists

## 故障排除

### 常见问题

1. **API密钥错误**
   - 检查 `.env` 文件中的 `ALI_API_KEY` 配置
   - 确认API密钥有效且有足够额度

2. **数据库连接失败**
   - 确认Docker服务正常运行
   - 检查端口5432是否被占用

3. **数据导入失败**
   - 确认 `chinese-poetry` 目录存在且位于正确位置
   - 检查网络连接和API调用限制

4. **搜索结果为空**
   - 确认数据已成功导入
   - 检查向量索引是否创建成功

### 日志查看
```bash
# 查看API服务日志
docker compose logs api

# 查看数据库日志
docker compose logs db

# 查看数据导入日志
tail -f import_data.log
```

## 开发说明

### 本地开发
```bash
# 安装依赖（使用统一依赖文件）
pip install -r requirements.txt

# 启动开发服务器
cd fastapi_app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 测试
```bash
# 健康检查
curl http://localhost:8000/health

# 测试搜索
curl "http://localhost:8000/search?keyword=李白"
```

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 创建 Pull Request

## 许可证

本项目采用 MIT 许可证。

## 致谢

- [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry) - 诗词数据源
- [pgvector](https://github.com/pgvector/pgvector) - PostgreSQL向量扩展
- [zhparser](https://github.com/amutu/zhparser) - 中文分词插件