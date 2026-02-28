import os

# 数据文件路径
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
POSTS_FILE = os.path.join(DATA_DIR, 'posts.json')

# 安全配置
PASSWORD_SALT = "my_salt_123"

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "YOUR_API_KEY")

# 服务器配置
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 8080