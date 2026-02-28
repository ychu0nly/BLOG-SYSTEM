# BLOG-SYSTEM

### 基于TCP协议和HTTP通信实现的博客系统

​	一个功能丰富的现代化博客平台，支持**注册登录、文章分类与搜索、点赞、评论、评论楼中楼、收藏、个人信息页面、日夜模式切换、文章排行榜、发布文章、编辑更新文章、文章草稿箱、网络流量监控、AI辅助阅读**等功能

## ✨ 功能亮点

- **用户系统**
  - 注册 / 登录
  - 个人信息页面
- **文章管理**
  - 发布、编辑、删除文章
  - 草稿箱（自动保存未发布内容）
  - 文章分类与标签
- **互动功能**
  - 点赞 ❤️
  - 评论 + 楼中楼回复（嵌套评论）
  - 收藏文章 ⭐
- **内容发现**
  - 全文搜索（按标题、内容、标签）
  - 文章排行榜（按热度、点赞数、阅读量等）
- **用户体验**
  - 日夜模式切换（日间 / 夜间主题）
  - 响应式设计
  - 页面加载性能优化
- **高级特性**
  - 网络流量监控
  - AI 辅助阅读（自动生成文章分析、用户与AI问答对话、AI回复markdown渲染）

## 🛠 技术栈

- **前端**：静态 HTML / CSS / JavaScript
- **后端**：基于 TCP Socket 与多线程模型的 **轻量级 HTTP 服务器**
- **数据库**：本地JSON文件（本地持久化，适用于单机部署的小型博客系统）
- **AI 集成**：调用 OpenAI API 实现文章分析生成、阅读辅助等功能

## 🚀 快速启动

​	AI辅助阅读功能通过 DeepSeek API 调用 deepseek-chat ，若要启用该功能，请先在 config.py 中设置您的 API 密钥。

~~~~~~cmd
conda create -n blog python=3.11
conda activate blog
pip install -r requirements.txt
cd backend
python server.py
~~~~~~

​	本地访问 **http://127.0.0.1:8080** ，即可开始您的博客平台使用。

​	为了方便演示，项目已经包含3个用户账号`user1, user2, user3`和密码`user123`，并且已经包含了部分文章和评论数据。

## 📦 项目结构

~~~
blog-system/
│
├── backend/                     # 后端核心逻辑（Socket 服务器 + 路由 + 业务）
│   ├── server.py                # 主服务器入口（启动 socket 监听）
│   ├── http_parser.py           # HTTP 请求解析工具
│   ├── response_builder.py      # HTTP 响应构建工具
│   ├── session_manager.py       # Session 管理（内存存储）
│   ├── auth.py   
│   ├── monitor.py   
│   ├── blog_logic.py   
│   ├── storage.py   
│   └── data/                    # 网络流量监控数据               
│		├── monitoring.json 
│  		└── monitoring_年-月-日.json
├── frontend/                    # 前端资源（HTML 模板 + 静态资源）
│   ├── templates_loader.py
│   ├── templates/              
│   │   ├── home.html         
│   │   ├── login.html
│   │   ├── monitor.html
│   │   ├── new_post.html
│   │   ├── post_detail.html
│   │   ├── profile.html
│   │   ├── ranking.html
│   │   └── register.html
│   └── static/                  # 静态资源（js/images/videos）
│       ├── images/
│       ├── js/
│       └── videos/
│
├── data/                        # 数据存储目录
│   ├── users.json               # 用户账户数据
│   └── posts.json               # 博客文章数据
│
├── config.py                    # 全局配置（如数据文件路径、DeepSeek API密钥等）
├── utils.py                     # 通用工具函数（密码哈希等）
├── requirements.txt             # 项目依赖
└── README.md                    # 项目说明
~~~
