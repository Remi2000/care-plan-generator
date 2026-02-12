# Care Plan Generator - MVP

最小可运行版本：前端填表 → 后端调 Claude → 生成 Care Plan

## 🚀 三步跑起来

### 第一步：填入你的 API Key
打开 `.env` 文件，把 `your-api-key-here` 换成你的 Anthropic API Key：
```
ANTHROPIC_API_KEY=sk-ant-xxxxx你的key
```

### 第二步：启动
```bash
docker-compose up --build
```

### 第三步：打开浏览器
访问 http://localhost:8000

填入患者信息，点击 "Generate Care Plan"，等 10-20 秒，就能看到 AI 生成的 Care Plan。

## 📁 项目结构（一共就这几个文件）

```
careplan-mvp/
├── docker-compose.yml      ← Docker 配置（启动数据库 + Django）
├── Dockerfile              ← 告诉 Docker 怎么构建
├── requirements.txt        ← Python 依赖包
├── manage.py               ← Django 启动入口
├── .env                    ← 你的 API Key 放这里
├── careplan_project/       ← Django 项目配置
│   ├── settings.py         ← 数据库连接、app注册
│   └── urls.py             ← URL 路由
└── orders/                 ← 核心业务代码
    ├── models.py           ← 数据库表：Patient, Provider, Order
    ├── views.py            ← API 逻辑：POST 创建订单, GET 查询结果
    ├── urls.py             ← API 路由
    └── templates/orders/
        └── index.html      ← 前端页面
```

## 🔌 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/orders/ | 提交患者信息，生成 care plan |
| GET  | /api/orders/{id}/ | 查询订单状态和 care plan |
