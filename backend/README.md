# 砚田日耕后端

Python 3.12 模块化单体。PostgreSQL 是唯一可信业务状态，Redis 仅用于队列、租约与短期协调。

## 本地启动

```bash
cp .env.example .env
docker compose up -d postgres redis
python -m venv .venv
. .venv/bin/activate
python -m pip install -c requirements.lock -e ".[dev]"
alembic upgrade head
uvicorn app.main:create_app --factory --reload
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。启动后检查：

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

## 质量检查

```bash
ruff check .
ruff format --check .
mypy app tests
python scripts/check_architecture.py
pytest
```

集成测试使用真实 PostgreSQL/Redis，单元测试不得隐式连接外部服务。生产环境必须从密钥管理系统注入 `TOKEN_SIGNING_KEY`，不得使用 `.env.example` 的占位值。

## 已开放的身份接口

身份接口统一位于 `/api/v1`：微信登录、refresh 轮换、当前会话退出、会话查询/撤销、全部退出、`/me` 和偏好 revision 更新。refresh token 只以 SHA-256 哈希保存；access token 的用户级和会话级版本会在敏感请求中重新校验。

微信平台交换通过 `WeChatIdentityProvider` 注入。未配置真实 Provider 时接口返回可重试的 503，不允许使用测试身份进入生产。
