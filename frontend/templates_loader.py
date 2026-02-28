import os

# 获取当前文件所在目录（即 frontend/）
FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(FRONTEND_DIR, 'templates')

def render_template(template_name: str) -> str:
    """
    读取并返回 templates/ 下对应 HTML 文件的内容。
    例如：render_template('login.html') → 返回 login.html 的字符串内容
    """
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()