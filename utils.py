import hashlib
from openai import OpenAI
import httpx
from config import PASSWORD_SALT, DEEPSEEK_API_KEY

def hash_password(password: str) -> str:
    return hashlib.sha256((password + PASSWORD_SALT).encode()).hexdigest()

def call_ai_assist(article_text: str, conversation_history: list = None) -> str:
    """调用 DeepSeek API 对文章进行专业阅读分析并支持持续对话"""
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "your_actual_api_key_here":
        return " AI 功能未配置：缺少有效的 API 密钥。"

    try:
        # 创建 httpx 客户端
        http_client = httpx.Client(
            timeout=300.0,
            proxies={},  # 显式禁用代理
            verify=True
        )
        client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=DEEPSEEK_API_KEY,
            http_client=http_client  # 注入自定义客户端
        )

        # 将文章内容直接嵌入 system prompt
        system_prompt = f"""你是一位专业的文章阅读辅助助手，正在帮助用户分析和理解以下特定文章：

<article>
{article_text}
</article>

请遵循以下指导原则：
核心任务：
1. 文章分析专家：以专业阅读者的身份，帮助用户深度理解上述文章内容
2. 交互式助手：不仅提供一次性分析，还要持续回答用户关于该文章的后续问题
3. 上下文记忆：记住之前的对话内容，确保回答的连贯性

工作流程：
1. 首次分析（当用户打开AI助手时）：
   - 提供文章的核心摘要（2-3句话）
   - 分析文章结构和逻辑框架
   - 指出关键概念、论点和论据
   - 提供批判性视角（如适用）
   - 建议进一步思考的方向（如适用）

2. 持续对话（回答用户后续问题时）：
   - 基于上述文章内容和之前的对话历史回答
   - 如果用户问题与文章无关，礼貌地引导回文章主题
   - 对于复杂问题，提供分步骤的解答
   - 适当时，引用文章中的具体内容

3. 回答风格：
   - 语言清晰、简洁、有条理
   - 保持客观中立，避免主观臆断
   - 对文章内容表示尊重，同时保持批判性思维
   - 用友好的语气，让用户感到轻松

重要：你分析的对象始终是上面 <article> 标签内的文章内容，请勿偏离。"""

        # 构建消息列表：system + 对话历史
        messages = [{"role": "system", "content": system_prompt}]

        # 添加用户和助手的历史消息（只保留 role 和 content）
        if conversation_history:
            for msg in conversation_history:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    # 只允许 user / assistant 角色
                    if msg["role"] in ("user", "assistant"):
                        messages.append({
                            "role": msg["role"],
                            "content": str(msg["content"])
                        })

        completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            max_tokens=8192
        )
        return completion.choices[0].message.content.strip()

    except Exception as e:
        return f" AI 分析失败：{str(e)}"
    finally:
        if 'http_client' in locals():
            http_client.close()