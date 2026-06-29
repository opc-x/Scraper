# Azure ACI 部署踩坑记录

Python FastAPI + Chromium Docker 镜像部署到 Azure Container Instances 的完整踩坑和解决方案。

## 架构

```
GitHub push → Actions build Docker → push GHCR → delete old ACI → create new ACI
```

## 踩过的坑

### 1. Azure for Students 区域限制

**现象**：`RequestDisallowedByAzure` — 所有常用区域都报错

**原因**：学生订阅有 Policy 限制可用区域，只允许 5 个：
- koreacentral, indonesiacentral, southeastasia, centralindia, japaneast

**查询方法**：
```bash
az policy assignment list --output json | python3 -c "
import sys, json
for p in json.load(sys.stdin):
    params = p.get('parameters', {})
    if params: print(json.dumps(params, indent=2))
"
```

**结论**：用 `southeastasia`

### 2. Azure VM 无容量

**现象**：`SkuNotAvailable` — B1s/B2s 在所有允许区域都没容量

**原因**：学生订阅的 B 系列 VM 长期满载

**替代方案**：用 Azure Container Instances (ACI) 替代 VM
- 不需要管理服务器
- 按运行时间计费（学生有 $100 额度）
- 直接跑 Docker 镜像

### 3. ACR Tasks 不可用

**现象**：`TasksOperationsNotAllowed` — `az acr build` 被拒

**原因**：学生订阅不支持 ACR Tasks（云端构建）

**替代方案**：用 GitHub Container Registry (GHCR) 替代 ACR
- GitHub Actions 构建镜像
- 推送到 ghcr.io（公开仓库免费）
- ACI 从 GHCR 拉取镜像

### 4. GHCR 镜像名必须小写

**现象**：`repository name must be lowercase`

**原因**：GitHub 仓库名 `Scraper` 含大写，Docker tag 不允许

**修复**：workflow 里硬编码小写 `IMAGE_NAME: opc-x/scraper`

### 5. Dockerfile pip install 顺序

**现象**：容器启动 ExitCode 1，无日志

**原因**：先 `COPY pyproject.toml` + `pip install .`，但源码还没复制进去

**修复**：
```dockerfile
# 错误
COPY pyproject.toml .
RUN pip install .
COPY . .

# 正确
COPY . .
RUN pip install .
```

### 6. ACI 容器 CrashLoopBackOff 无日志

**现象**：容器反复重启，`az container logs` 返回 `None`

**原因**：Python stdout 缓冲 — 进程崩溃前输出没 flush 到 ACI 日志收集器

**修复**：Dockerfile 加 `ENV PYTHONUNBUFFERED=1`，CMD 用 `python -u -m uvicorn`

```dockerfile
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**诊断技巧**：用 `--command-line` + `--restart-policy Never` 创建调试容器：
```bash
az container create --name debug \
  --image ghcr.io/opc-x/scraper:latest \
  --command-line "python -c 'from app.main import app; print(\"OK\")'" \
  --restart-policy Never ...
```

### 7. ACI 不自动拉新 :latest 镜像

**现象**：部署后容器还在跑旧镜像

**原因**：ACI 对同名容器组 + 同 tag 不会重新拉取

**修复**：部署前先删旧容器 + 用 SHA tag（不用 :latest）
```yaml
- name: Delete old container
  run: az container delete --name scraper --yes || true

- name: Deploy
  run: az container create --image ghcr.io/opc-x/scraper:${{ github.sha }} ...
```

### 8. SQLAlchemy psycopg2 vs psycopg v3

**现象**：`ModuleNotFoundError: No module named 'psycopg2'`

**原因**：`pyproject.toml` 安装的是 `psycopg[binary]`（v3），但 SQLAlchemy 默认 dialect 是 `psycopg2`

**修复**：连接 URL 前缀改为 `postgresql+psycopg://`
```python
def _build_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
```

### 9. ACI 环境变量含特殊字符

**现象**：DATABASE_URL 里的 `@`、`?`、`=` 可能被 shell 误解析

**修复**：
- 敏感值用 `--secure-environment-variables`（加密存储 + 不显示在日志/Portal）
- 值用引号包裹：`"DATABASE_URL=$DB_URL"`
- 在 workflow step 层用 `env:` 绑定 secrets，避免直接内联

## 最终稳定配置

**Dockerfile**：
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver fonts-wqy-zenhei && rm -rf /var/lib/apt/lists/*
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["python", "-u", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**CI/CD 关键点**：
- GHCR 存镜像（免费）
- SHA tag 强制拉新镜像
- 先删后建容器
- secure-environment-variables 传敏感信息
- SQLAlchemy 用 `postgresql+psycopg://` 前缀

## 成本

| 资源 | 费用 |
|------|------|
| GHCR | 免费（公开仓库） |
| GitHub Actions | 免费（2000 min/月） |
| ACI (1 CPU, 2GB) | ~$0.05/小时，$100 学生额度可用 ~2000 小时 |
| Neon DB | 免费层 |
