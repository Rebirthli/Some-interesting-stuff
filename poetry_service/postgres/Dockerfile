# 使用官方pgvector镜像作为基础，然后添加官方Groonga APT源
FROM pgvector/pgvector:pg15

# 设置locale环境变量，确保数据库正确初始化
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV LANGUAGE=C.UTF-8

# 切换到root用户进行系统包安装
USER root

# 配置阿里云镜像源以加速下载，然后安装官方Groonga APT源
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates wget && \
    # 配置阿里云镜像源
    sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    # 安装必要的工具
    apt-get update && \
    apt-get install -y --no-install-recommends \
        lsb-release gnupg \
    && \
    # 添加官方Groonga APT源
    wget -O /tmp/groonga-apt.deb \
        https://packages.groonga.org/debian/groonga-apt-source-latest-$(lsb_release --codename --short).deb && \
    apt-get install -y /tmp/groonga-apt.deb && \
    rm -f /tmp/groonga-apt.deb && \
    # 更新包列表并安装pgroonga扩展
    apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-contrib \
        postgresql-15-pgroonga \
    && \
    # 清理临时文件和缓存
    apt-get purge -y lsb-release gnupg wget && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 步骤 6: 安装完成后，切换回安全的、非特权的 postgres 用户。
USER postgres

# 步骤 7: 保留您设置的默认数据库和用户名环境变量。
ENV POSTGRES_DB=poetry_db
ENV POSTGRES_USER=postgres

# 步骤 8: 保留您声明的端口暴露。
EXPOSE 5432