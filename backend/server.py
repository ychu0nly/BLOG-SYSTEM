import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import socket
import threading
import json
import time
from datetime import datetime
from config import SERVER_HOST, SERVER_PORT
from utils import hash_password, call_ai_assist
from backend.http_parser import parse_http_request
from backend.response_builder import make_response, redirect, add_cookie_to_response
from backend.session_manager import get_user_by_session, destroy_session
from frontend.templates_loader import render_template
from backend.auth import authenticate_user, register_user
from backend.blog_logic import get_all_posts, get_post_by_id, create_post, filter_posts, get_all_categories, get_category_display_name, increment_post_views, get_ranking_posts, update_post
from backend.storage import toggle_like, get_post_likes, toggle_favorite, get_post_favorites, get_user_favorites, save_draft, get_user_drafts, get_draft_by_id, delete_draft, add_comment, get_post_comments, toggle_comment_like, get_user_posts

# ------------------------
# 导入监控模块
# ------------------------
try:
    from backend.monitor import monitor
    MONITOR_ENABLED = True
except ImportError:
    MONITOR_ENABLED = False
    print("[WARNING] 监控模块未找到，监控功能已禁用")

# ------------------------
# 工具函数
# ------------------------

def get_session_user(headers):
    cookie_header = headers.get('Cookie', '')
    for cookie in cookie_header.split(';'):
        if 'session_id=' in cookie:
            session_id = cookie.split('session_id=')[1].strip()
            return get_user_by_session(session_id)
    return None

# ------------------------
# 路由处理
# ------------------------

def handle_request(request_dict):
    # 记录请求开始（如果监控已启用）
    client_ip = "unknown"
    if 'headers' in request_dict and 'X-Forwarded-For' in request_dict['headers']:
        client_ip = request_dict['headers']['X-Forwarded-For'].split(',')[0].strip()
    
    if MONITOR_ENABLED:
        start_record = monitor.record_request_start(
            client_id=client_ip,
            path=request_dict['path'],
            method=request_dict['method']
        )
    
    method = request_dict['method']
    path = request_dict['path']
    query = request_dict['query']
    post_data = request_dict['post_data']
    headers = request_dict['headers']
    body = request_dict.get('body', '')
    current_user = get_session_user(headers)

    # ========== 静态文件服务 ========== 
    if path.startswith('/static/'):
        response = handle_static_file(path)
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 200 if '200 OK' in str(response) else 404)
        return response

    # ========== 监控页面 ==========
    elif path == '/monitor':
        if MONITOR_ENABLED:
            html = render_template('monitor.html')
            response = make_response("200 OK", "text/html", html)
            monitor.record_request_end(start_record, 200, len(str(response)))
            return response
        else:
            response = make_response("503 Service Unavailable", "text/plain", "监控功能未启用")
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 503)
            return response

    # ========== 监控API ==========
    elif path.startswith('/api/monitoring'):
        if not MONITOR_ENABLED:
            response = make_response("503 Service Unavailable", "application/json", 
                                     json.dumps({"success": False, "error": "监控功能未启用"}, ensure_ascii=False))
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 503)
            return response
        
        action = query.get('action', [''])[0]
        try:
            if action == 'realtime':
                # 获取实时监控数据
                data = monitor.get_realtime_metrics()
                response_data = json.dumps({"success": True, "data": data}, ensure_ascii=False)
                response = make_response("200 OK", "application/json", response_data)
                
            elif action == 'system_status':
                # 获取系统状态
                data = monitor.get_system_status()
                response_data = json.dumps({"success": True, "data": data}, ensure_ascii=False)
                response = make_response("200 OK", "application/json", response_data)
                
            elif action == 'endpoints':
                # 获取接口统计
                hours = int(query.get('hours', [24])[0])
                data = monitor.get_endpoint_statistics(hours)
                response_data = json.dumps({"success": True, "data": data}, ensure_ascii=False)
                response = make_response("200 OK", "application/json", response_data)
                
            elif action == 'historical':
                # 获取历史数据
                hours = int(query.get('hours', [1])[0])
                endpoint_filter = query.get('endpoint', [None])[0]
                data = monitor.get_historical_data(hours, endpoint_filter)
                response_data = json.dumps({"success": True, "data": data}, ensure_ascii=False)
                response = make_response("200 OK", "application/json", response_data)
                
            else:
                response_data = json.dumps({"success": False, "error": "未知操作"}, ensure_ascii=False)
                response = make_response("400 Bad Request", "application/json", response_data)
            
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 200, len(response_data))
            return response
            
        except Exception as e:
            response_data = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
            response = make_response("500 Internal Server Error", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 500)
            return response

    # ========== 点赞功能 ==========
    elif path.startswith('/toggle_like'):
        if not current_user:
            response_data = json.dumps({
                'error': '请左上角登录，发现更多精彩内容'
            }, ensure_ascii=False)
            response = make_response("401 Unauthorized", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return response
        
        post_id = query.get('id', [''])[0]
        if post_id.isdigit():
            post_id = int(post_id)
            liked, like_count = toggle_like(post_id, current_user)
            response_data = json.dumps({
                'liked': liked,
                'like_count': like_count
            }, ensure_ascii=False)
            response = make_response("200 OK", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 200, len(response_data))
            return response
        
        response = make_response("400 Bad Request", "text/plain", "Invalid post ID")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 400)
        return response

    # ========== 收藏功能 ==========
    elif path.startswith('/toggle_favorite'):
        if not current_user:
            response_data = json.dumps({
                'error': '请左上角登录，发现更多精彩内容'
            }, ensure_ascii=False)
            response = make_response("401 Unauthorized", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return response
        
        post_id = query.get('id', [''])[0]
        if post_id.isdigit():
            post_id = int(post_id)
            favorited, favorite_count = toggle_favorite(post_id, current_user)
            response_data = json.dumps({
                'favorited': favorited,
                'favorite_count': favorite_count
            }, ensure_ascii=False)
            response = make_response("200 OK", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 200, len(response_data))
            return response
        
        response = make_response("400 Bad Request", "text/plain", "Invalid post ID")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 400)
        return response

    # ========== 保存草稿功能 ==========
    elif path.startswith('/save_draft'):
        if not current_user:
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            response_data = json.dumps({
                'success': False,
                'message': '未登录'
            }, ensure_ascii=False)
            response = make_response("401 Unauthorized", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return response
        
        if method == 'POST':
            try:
                # 支持JSON和FormData格式
                if body:
                    try:
                        body_dict = json.loads(body)
                    except:
                        # 如果不是JSON，尝试解析FormData
                        body_dict = {}
                        for pair in body.split('&'):
                            if '=' in pair:
                                key, value = pair.split('=', 1)
                                body_dict[key] = value.replace('+', ' ').replace('%20', ' ')
                else:
                    body_dict = {}
                
                title = body_dict.get('title', '')
                content = body_dict.get('content', '')
                category = body_dict.get('category', 'tech')
                draft_id = body_dict.get('draft_id')
                
                if content:  # 只要有内容就可以保存草稿
                    if draft_id:
                        save_draft(title, content, category, current_user, int(draft_id))
                    else:
                        save_draft(title, content, category, current_user)
                    response_data = json.dumps({
                        'success': True,
                        'message': '草稿已保存'
                    }, ensure_ascii=False)
                    response = make_response("200 OK", "application/json", response_data)
                    if MONITOR_ENABLED:
                        monitor.record_request_end(start_record, 200, len(response_data))
                    return response
                else:
                    response_data = json.dumps({
                        'success': False,
                        'message': '内容为空，无法保存草稿'
                    }, ensure_ascii=False)
                    response = make_response("400 Bad Request", "application/json", response_data)
                    if MONITOR_ENABLED:
                        monitor.record_request_end(start_record, 400)
                    return response
            except Exception as e:
                response_data = json.dumps({
                    'success': False,
                    'message': f'保存失败: {str(e)}'
                }, ensure_ascii=False)
                response = make_response("500 Internal Server Error", "application/json", response_data)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 500)
                return response
        
        response = make_response("405 Method Not Allowed", "text/plain", "Only POST allowed")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 405)
        return response

    # ========== 删除草稿功能 ==========
    elif path.startswith('/delete_draft'):
        if not current_user:
            response_data = json.dumps({
                'error': '请先登录'
            }, ensure_ascii=False)
            response = make_response("401 Unauthorized", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return response
        
        draft_id = query.get('id', [''])[0]
        if draft_id.isdigit():
            draft_id_int = int(draft_id)
            if delete_draft(draft_id_int, current_user):
                response_data = json.dumps({
                    'success': True,
                    'message': '草稿已删除'
                }, ensure_ascii=False)
                response = make_response("200 OK", "application/json", response_data)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 200, len(response_data))
                return response
            else:
                response_data = json.dumps({
                    'success': False,
                    'message': '草稿不存在或无权限删除'
                }, ensure_ascii=False)
                response = make_response("404 Not Found", "application/json", response_data)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 404)
                return response
        
        response = make_response("400 Bad Request", "text/plain", "Invalid draft ID")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 400)
        return response

    # ========== 评论功能 ==========
    elif path.startswith('/add_comment'):
        if not current_user:
            response_data = json.dumps({
                'error': '请左上角登录，发现更多精彩内容'
            }, ensure_ascii=False)
            response = make_response("401 Unauthorized", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return response
        
        if method == 'POST':
            try:
                body_dict = json.loads(body)
                post_id = body_dict.get('post_id')
                content = body_dict.get('content', '').strip()
                parent_comment_id = body_dict.get('parent_comment_id')  # 父评论ID，用于回复
                
                if post_id and content:
                    comment = add_comment(int(post_id), current_user, content, int(parent_comment_id) if parent_comment_id else None)
                    if comment:
                        response_data = json.dumps({
                            'success': True,
                            'comment': comment
                        }, ensure_ascii=False)
                        response = make_response("200 OK", "application/json", response_data)
                        if MONITOR_ENABLED:
                            monitor.record_request_end(start_record, 200, len(response_data))
                        return response
                    else:
                        response_data = json.dumps({
                            'success': False,
                            'message': '文章不存在'
                        }, ensure_ascii=False)
                        response = make_response("404 Not Found", "application/json", response_data)
                        if MONITOR_ENABLED:
                            monitor.record_request_end(start_record, 404)
                        return response
                else:
                    response_data = json.dumps({
                        'success': False,
                        'message': '请填写评论内容'
                    }, ensure_ascii=False)
                    response = make_response("400 Bad Request", "application/json", response_data)
                    if MONITOR_ENABLED:
                        monitor.record_request_end(start_record, 400)
                    return response
            except Exception as e:
                response_data = json.dumps({
                    'success': False,
                    'message': f'添加评论失败: {str(e)}'
                }, ensure_ascii=False)
                response = make_response("500 Internal Server Error", "application/json", response_data)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 500)
                return response
        
        response = make_response("405 Method Not Allowed", "text/plain", "Only POST allowed")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 405)
        return response

    # ========== 评论点赞功能 ==========
    elif path.startswith('/toggle_comment_like'):
        if not current_user:
            response_data = json.dumps({
                'error': '请左上角登录，发现更多精彩内容'
            }, ensure_ascii=False)
            response = make_response("401 Unauthorized", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return response
        
        post_id = query.get('post_id', [''])[0]
        comment_id = query.get('comment_id', [''])[0]
        if post_id.isdigit() and comment_id.isdigit():
            post_id_int = int(post_id)
            comment_id_int = int(comment_id)
            liked, like_count = toggle_comment_like(post_id_int, comment_id_int, current_user)
            response_data = json.dumps({
                'liked': liked,
                'like_count': like_count
            }, ensure_ascii=False)
            response = make_response("200 OK", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 200, len(response_data))
            return response
        
        response = make_response("400 Bad Request", "text/plain", "Invalid post ID or comment ID")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 400)
        return response

    # ========== 首页 ==========
    if path == '/':
        # 记录用户会话
        if current_user and MONITOR_ENABLED:
            monitor.record_user_session(current_user, "active")
        
        posts = get_all_posts()
        search_query = query.get('search', [''])[0]
        category_filter = query.get('category', [''])[0]
        posts = filter_posts(posts, search_query, category_filter)
        
        if current_user:
            nav_items = [
                f'<li><a href="/">首页</a></li>',
                f'<li><a href="/ranking">排行榜</a></li>',
                f'<li><a href="/profile">个人中心</a></li>',
                f'<li><a href="/monitor">系统监控</a></li>',
                f'<li><a href="/logout">退出</a></li>'
            ]
        else:
            nav_items = [
                f'<li><a href="/">首页</a></li>',
                f'<li><a href="/ranking">排行榜</a></li>',
                f'<li><a href="/login">登录</a></li>',
                f'<li><a href="/register">注册</a></li>',
                f'<li><a href="/monitor">系统监控</a></li>'
            ]
        
        nav = ''.join(nav_items)
        
        # 生成新的监控面板 HTML
        monitor_panel = ""
        if MONITOR_ENABLED:
            try:
                metrics = monitor.get_realtime_metrics()
                monitor_panel = f'''
<div class="monitor-panel">
  <h3>📊 性能监测</h3>
  <p>总请求数: {metrics.get('total_requests', 0)}</p>
  <p>成功率: {metrics.get('success_rate', 100):.1f}%</p>
  <p>平均响应: {metrics.get('avg_response_time_ms', 0):.0f}ms</p>
  <p>活跃用户: {metrics.get('active_users', 0)}</p>
  <a href="/monitor" target="_blank">查看详情</a>
</div>
                '''
            except Exception as e:
                monitor_panel = '<div class="monitor-panel"><p style="color:#ff6b6b;">监控加载失败</p></div>'
        # 如果未启用，留空（不显示）
        
        # 获取所有分类并生成选项
        all_categories = get_all_categories()
        category_options = '<option value="">全部分类</option>'
        for cat in all_categories:
            selected = 'selected' if category_filter == cat else ''
            display_name = get_category_display_name(cat)
            category_options += f'<option value="{cat}" {selected}>{display_name}</option>'
        
        form = f'''
        <form method="GET" style="margin-bottom:20px;">
        <input type="text" name="search" placeholder="搜索文章..." value="{search_query}" style="padding:8px; width:200px;">
        <select name="category" style="padding:8px;">
        {category_options}
        </select>
        <button type="submit" style="padding:8px 12px;">搜索</button>
        </form>
        '''
        
        posts_html = ''
        for p in posts:
            cover_url = f"https://picsum.photos/300/200?id={p['id']}"
            summary = (p['content'].replace('\n', ' ')[:60] + '...') if len(p['content']) > 60 else p['content']
            like_count = len(p.get('likes', []))
            is_liked = current_user and current_user in p.get('likes', [])
            like_button = f'''
            <div style="margin-top: 10px;">
                <button onclick="toggleLike({p['id']})" style="background: {'#ff6b6b' if is_liked else '#e0e0e0'}; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; color: white;">
                    {'❤️' if is_liked else '🤍'} 点赞
                </button>
                <span id="like-count-{p['id']}">{like_count}</span>
            </div>
            '''
            category_display = get_category_display_name(p['category'])
            posts_html += f'''
            <div class="article" data-aos="fade-up">
            <img src="{cover_url}" alt="封面">
            <div>
            <h2><a href="/post?id={p['id']}" style="color:#333; text-decoration:none;">{p['title']}</a></h2>
            <p>作者：{p['author']} | 分类：{category_display} | {p['timestamp']}</p>
            <p>{summary}</p>
            {like_button}
            </div>
            </div>
            '''
        
        if not posts:
            posts_html = "<p>暂无文章</p>"
        
        new_post_btn = '<p><a href="/new_post" style="display:inline-block;padding:8px 16px;background:#0077ff;color:white;text-decoration:none;border-radius:6px;">发布新文章</a></p>' if current_user else ''
        
        # 读取 home.html 模板
        html = render_template('home.html')
        # 替换导航栏
        html = html.replace('<ul>\n      {nav}\n    </ul>', f'<ul>\n      {nav}\n    </ul>')
        # 替换 {monitor_panel} 占位符
        html = html.replace('{monitor_panel}', monitor_panel)
        # 替换其他内容
        html = html.replace('{form}', form)
        html = html.replace('{new_post_btn}', new_post_btn)
        html = html.replace('{posts_html}', posts_html)
        
        # 添加点赞功能的JavaScript
        like_js = '''
        <script>
        function toggleLike(postId) {
            fetch(`/toggle_like?id=${postId}`, {
                method: 'GET',
                credentials: 'same-origin'
            })
            .then(response => {
                if (response.status === 401) {
                    return response.json().then(data => {
                        alert(data.error || '请左上角登录，发现更多精彩内容');
                        throw new Error('Unauthorized');
                    });
                }
                return response.json();
            })
            .then(data => {
                const button = document.querySelector(`button[onclick="toggleLike(${postId})"]`);
                const countSpan = document.getElementById(`like-count-${postId}`);
                
                if (data.liked) {
                    button.innerHTML = '❤️ 点赞';
                    button.style.background = '#ff6b6b';
                } else {
                    button.innerHTML = '🤍 点赞';
                    button.style.background = '#e0e0e0';
                }
                
                countSpan.textContent = data.like_count;
            })
            .catch(error => {
                if (error.message !== 'Unauthorized') {
                    console.error('点赞请求失败:', error);
                }
            });
        }
        </script>
        '''
        html = html.replace('</body>', f'{like_js}</body>')
        
        response = make_response("200 OK", "text/html", html)
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 200, len(str(response)))
        return response

    # ========== 排行榜 ==========
    elif path == '/ranking':
        # 记录用户会话
        if current_user and MONITOR_ENABLED:
            monitor.record_user_session(current_user, "active")
        
        # 获取按热度排序的文章
        posts = get_ranking_posts()
        
        if current_user:
            nav_items = [
                f'<li><a href="/">首页</a></li>',
                f'<li><a href="/ranking">排行榜</a></li>',
                f'<li><a href="/profile">个人中心</a></li>',
                f'<li><a href="/monitor">系统监控</a></li>',
                f'<li><a href="/logout">退出</a></li>'
            ]
        else:
            nav_items = [
                f'<li><a href="/">首页</a></li>',
                f'<li><a href="/ranking">排行榜</a></li>',
                f'<li><a href="/login">登录</a></li>',
                f'<li><a href="/register">注册</a></li>',
                f'<li><a href="/monitor">系统监控</a></li>'
            ]
        
        nav = ''.join(nav_items)
        
        # 生成文章列表HTML
        posts_html = ''
        for idx, p in enumerate(posts, 1):
            cover_url = f"https://picsum.photos/300/200?id={p['id']}"
            summary = (p['content'].replace('\n', ' ')[:60] + '...') if len(p['content']) > 60 else p['content']
            like_count = len(p.get('likes', []))
            favorite_count = len(p.get('favorites', []))
            comment_count = len(p.get('comments', []))
            views = p.get('views', 0)
            popularity = p.get('popularity', 0)
            
            is_liked = current_user and current_user in p.get('likes', [])
            like_button = f'''
            <div style="margin-top: 10px;">
                <button onclick="toggleLike({p['id']})" style="background: {'#ff6b6b' if is_liked else '#e0e0e0'}; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; color: white;">
                    {'❤️' if is_liked else '🤍'} 点赞
                </button>
                <span id="like-count-{p['id']}">{like_count}</span>
            </div>
            '''
            category_display = get_category_display_name(p['category'])
            posts_html += f'''
            <div class="article">
            <div class="ranking-badge">#{idx}</div>
            <img src="{cover_url}" alt="封面">
            <div>
            <h2><a href="/post?id={p['id']}" style="color:#333; text-decoration:none;">{p['title']}</a></h2>
            <p>作者：{p['author']} | 分类：{category_display} | {p['timestamp']}</p>
            <p>{summary}</p>
            <div class="popularity-info">
                <span>🔥 热度: {popularity:.1f}</span>
                <span>👁️ 阅读: {views}</span>
                <span>❤️ 点赞: {like_count}</span>
                <span>⭐ 收藏: {favorite_count}</span>
                <span>💬 评论: {comment_count}</span>
            </div>
            {like_button}
            </div>
            </div>
            '''
        
        if not posts:
            posts_html = '<div class="no-posts">暂无文章</div>'
        
        # 读取 ranking.html 模板
        html = render_template('ranking.html')
        # 替换导航栏
        html = html.replace('<ul>\n      {nav}\n    </ul>', f'<ul>\n      {nav}\n    </ul>')
        # 替换文章列表
        html = html.replace('{posts_html}', posts_html)
        
        # 添加点赞功能的JavaScript
        like_js = '''
        <script>
        function toggleLike(postId) {
            fetch(`/toggle_like?id=${postId}`, {
                method: 'GET',
                credentials: 'same-origin'
            })
            .then(response => {
                if (response.status === 401) {
                    return response.json().then(data => {
                        alert(data.error || '请左上角登录，发现更多精彩内容');
                        throw new Error('Unauthorized');
                    });
                }
                return response.json();
            })
            .then(data => {
                const button = document.querySelector(`button[onclick="toggleLike(${postId})"]`);
                const countSpan = document.getElementById(`like-count-${postId}`);
                
                if (data.liked) {
                    button.innerHTML = '❤️ 点赞';
                    button.style.background = '#ff6b6b';
                } else {
                    button.innerHTML = '🤍 点赞';
                    button.style.background = '#e0e0e0';
                }
                
                countSpan.textContent = data.like_count;
                // 刷新页面以更新热度
                location.reload();
            })
            .catch(error => {
                if (error.message !== 'Unauthorized') {
                    console.error('点赞请求失败:', error);
                }
            });
        }
        </script>
        '''
        html = html.replace('</body>', f'{like_js}</body>')
        
        response = make_response("200 OK", "text/html", html)
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 200, len(str(response)))
        return response

    # ========== 登录 ==========
    elif path == '/login':
        if method == 'GET':
            html = render_template('login.html').format(error="")
            response = make_response("200 OK", "text/html", html)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 200, len(str(response)))
            return response
        else:
            username = post_data.get('username', [''])[0]
            password = post_data.get('password', [''])[0]
            ok, session_id = authenticate_user(username, password)
            if ok:
                # 记录用户登录
                if MONITOR_ENABLED:
                    monitor.record_user_session(username, "login")
                
                resp = redirect('/')
                cookie_header = f'Set-Cookie: session_id={session_id}; Path=/; HttpOnly'
                response = add_cookie_to_response(resp, cookie_header)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 302)
                return response
            else:
                error_msg = '<p style="color:red">用户名或密码错误</p>'
                html = render_template('login.html').format(error=error_msg)
                response = make_response("200 OK", "text/html", html)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 200, len(str(response)))
                return response

    # ========== 注册 ==========
    elif path == '/register':
        if method == 'GET':
            html = render_template('register.html').format(error="")
            response = make_response("200 OK", "text/html", html)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 200, len(str(response)))
            return response
        else:
            username = post_data.get('username', [''])[0]
            password = post_data.get('password', [''])[0]
            ok, msg = register_user(username, password)
            if ok:
                response = redirect('/login')
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 302)
                return response
            else:
                error_msg = f'<p style="color:red">{msg}</p>'
                html = render_template('register.html').format(error=error_msg)
                response = make_response("200 OK", "text/html", html)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 200, len(str(response)))
                return response

    # ========== 登出 ==========
    elif path == '/logout':
        cookie = headers.get('Cookie', '')
        if 'session_id=' in cookie:
            session_id = cookie.split('session_id=')[1].split(';')[0]
            user = get_user_by_session(session_id)
            if user and MONITOR_ENABLED:
                monitor.record_user_session(user, "logout")
            destroy_session(session_id)
        
        response = redirect('/login')
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 302)
        return response

    # ========== 个人中心 ==========
    elif path == '/profile':
        if not current_user:
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return redirect('/login')
        
        # 获取用户发布的文章列表
        user_posts = get_user_posts(current_user)
        post_count = len(user_posts)
        
        # 生成文章列表HTML
        if user_posts:
            posts_list_html = ''
            for post in user_posts:
                summary = (post['content'].replace('\n', ' ')[:80] + '...') if len(post['content']) > 80 else post['content']
                category_display = get_category_display_name(post['category'])
                like_count = len(post.get('likes', []))
                comment_count = len(post.get('comments', []))
                views = post.get('views', 0)
                posts_list_html += f'''
                <div class="favorite-item" style="border-left-color: #66a6ff;">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <h3><a href="/post?id={post['id']}">{post['title']}</a></h3>
                            <p style="margin: 8px 0; color: rgba(255,255,255,0.9);">{summary}</p>
                            <div class="favorite-meta">
                                分类：{category_display} | 发布时间：{post['timestamp']} | 👁️ {views} | ❤️ {like_count} | 💬 {comment_count}
                            </div>
                        </div>
                        <a href="/new_post?edit_id={post['id']}" style="padding: 8px 16px; background: rgba(102,166,255,0.8); color: white; text-decoration: none; border-radius: 6px; font-size: 14px; margin-left: 15px; transition: all 0.3s ease; white-space: nowrap;">
                            ✏️ 编辑
                        </a>
                    </div>
                </div>
                '''
        else:
            posts_list_html = '<div class="no-favorites">暂无发布的文章</div>'
        
        # 获取用户的收藏列表
        favorite_posts = get_user_favorites(current_user)
        favorite_count = len(favorite_posts)
        
        # 生成收藏列表HTML
        if favorite_posts:
            favorites_list_html = ''
            for post in favorite_posts:
                summary = (post['content'].replace('\n', ' ')[:80] + '...') if len(post['content']) > 80 else post['content']
                category_display = get_category_display_name(post['category'])
                favorites_list_html += f'''
                <div class="favorite-item">
                    <h3><a href="/post?id={post['id']}">{post['title']}</a></h3>
                    <p style="margin: 8px 0; color: rgba(255,255,255,0.9);">{summary}</p>
                    <div class="favorite-meta">
                        作者：{post['author']} | 分类：{category_display} | {post['timestamp']}
                    </div>
                </div>
                '''
        else:
            favorites_list_html = '<div class="no-favorites">暂无收藏的文章</div>'
        
        # 获取用户的草稿列表
        draft_posts = get_user_drafts(current_user)
        draft_count = len(draft_posts)
        
        # 生成草稿列表HTML
        if draft_posts:
            drafts_list_html = ''
            for draft in draft_posts:
                summary = (draft['content'].replace('\n', ' ')[:80] + '...') if len(draft['content']) > 80 else draft['content']
                category_display = get_category_display_name(draft['category'])
                drafts_list_html += f'''
                <div class="favorite-item" style="border-left-color: #ff9800;" id="draft-{draft['id']}">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <h3><a href="/new_post?id={draft['id']}">{draft['title']}</a> <span style="font-size: 12px; color: #ff9800;">[草稿]</span></h3>
                            <p style="margin: 8px 0; color: rgba(255,255,255,0.9);">{summary}</p>
                            <div class="favorite-meta">
                                分类：{category_display} | 保存时间：{draft['timestamp']}
                            </div>
                        </div>
                        <button onclick="deleteDraft({draft['id']})" style="padding: 8px 16px; background: rgba(255,107,107,0.8); color: white; border: none; border-radius: 6px; font-size: 14px; margin-left: 15px; cursor: pointer; transition: all 0.3s ease; white-space: nowrap;">
                            🗑️ 删除
                        </button>
                    </div>
                </div>
                '''
        else:
            drafts_list_html = '<div class="no-favorites">暂无草稿</div>'
        
        # 添加删除草稿的JavaScript
        delete_draft_js = '''
        <script>
        async function deleteDraft(draftId) {
            if (!confirm('确定要删除这个草稿吗？删除后无法恢复。')) {
                return;
            }
            
            try {
                const response = await fetch('/delete_draft?id=' + draftId, {
                    method: 'GET',
                    credentials: 'same-origin'
                });
                
                if (response.status === 401) {
                    alert('请先登录');
                    return;
                }
                
                if (response.ok) {
                    // 移除草稿元素
                    const draftElement = document.getElementById('draft-' + draftId);
                    if (draftElement) {
                        draftElement.style.transition = 'opacity 0.3s';
                        draftElement.style.opacity = '0';
                        setTimeout(() => {
                            draftElement.remove();
                            
                            // 更新草稿计数
                            const draftsPanel = document.getElementById('drafts-panel');
                            const draftsList = draftsPanel.querySelector('.favorite-item, .no-favorites');
                            if (!draftsList || draftsList.classList.contains('no-favorites')) {
                                draftsPanel.innerHTML = '<h3 class="content-title">📝 我的草稿箱 (0)</h3><div class="no-favorites">暂无草稿</div>';
                            }
                            
                            // 更新标签页计数
                            const draftTabButton = document.querySelector('button[data-tab="drafts"] .count');
                            if (draftTabButton) {
                                const currentCount = parseInt(draftTabButton.textContent) || 0;
                                const newCount = Math.max(0, currentCount - 1);
                                draftTabButton.textContent = newCount;
                                
                                // 更新标题计数
                                const draftTitle = draftsPanel.querySelector('.content-title');
                                if (draftTitle) {
                                    draftTitle.textContent = `📝 我的草稿箱 (${newCount})`;
                                }
                            }
                            
                            // 如果当前在草稿箱标签页且没有草稿了，显示提示
                            if (draftsPanel.classList.contains('active') && !draftsPanel.querySelector('.favorite-item')) {
                                draftsPanel.innerHTML = '<h3 class="content-title">📝 我的草稿箱 (0)</h3><div class="no-favorites">暂无草稿</div>';
                            }
                        }, 300);
                    }
                } else {
                    alert('删除草稿失败，请重试');
                }
            } catch (error) {
                console.error('删除草稿失败:', error);
                alert('删除草稿失败，请检查网络连接');
            }
        }
        </script>
        '''
        
        html = render_template('profile.html').format(
            username=current_user,
            post_count=post_count,
            posts_list=posts_list_html,
            favorite_count=favorite_count,
            favorites_list=favorites_list_html,
            draft_count=draft_count,
            drafts_list=drafts_list_html
        )
        # 在body结束标签前添加删除草稿的JavaScript
        html = html.replace('</body>', delete_draft_js + '</body>')
        response = make_response("200 OK", "text/html", html)
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 200, len(str(response)))
        return response

    # ========== 发布文章/编辑草稿 ==========
    elif path == '/new_post':
        if not current_user:
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 401)
            return redirect('/login')
        
        if method == 'GET':
            # 检查是否是编辑文章
            edit_id = query.get('edit_id', [''])[0]
            edit_data = None
            is_edit_mode = False
            
            if edit_id and edit_id.isdigit():
                post = get_post_by_id(int(edit_id))
                if post and post.get('author') == current_user and not post.get('is_draft', False):
                    edit_data = {
                        'id': post['id'],
                        'title': post.get('title', ''),
                        'content': post.get('content', ''),
                        'category': post.get('category', 'tech')
                    }
                    is_edit_mode = True
            
            # 检查是否是编辑草稿
            draft_id = query.get('id', [''])[0]
            draft_data = None
            if not is_edit_mode and draft_id and draft_id.isdigit():
                draft = get_draft_by_id(int(draft_id), current_user)
                if draft:
                    draft_data = {
                        'title': draft.get('title', ''),
                        'content': draft.get('content', ''),
                        'category': draft.get('category', 'tech')
                    }
            
            html = render_template('new_post.html')
            page_title = '编辑文章' if is_edit_mode else '发布新文章'
            html = html.replace('<h2>发布新文章</h2>', f'<h2>{page_title}</h2>')
            
            # 如果有编辑数据，直接在HTML中填充值
            if edit_data:
                # 转义HTML特殊字符，防止XSS
                def escape_html(text):
                    """转义HTML特殊字符"""
                    return (text.replace('&', '&amp;')
                               .replace('<', '&lt;')
                               .replace('>', '&gt;')
                               .replace('"', '&quot;')
                               .replace("'", '&#x27;'))
                
                safe_title = escape_html(edit_data['title'])
                safe_content = escape_html(edit_data['content']).replace('&lt;/textarea&gt;', '</textarea>')
                
                # 直接在input中设置value
                html = html.replace('<input name="title" id="title" required>', 
                                  f'<input name="title" id="title" value="{safe_title}" required>')
                # textarea的值设置在标签之间（再次转义以防止破坏textarea标签）
                safe_content_for_textarea = safe_content.replace('</textarea>', '&lt;/textarea&gt;')
                html = html.replace('<textarea name="content" id="content" required></textarea>', 
                                  f'<textarea name="content" id="content" required>{safe_content_for_textarea}</textarea>')
                
                # 设置分类选择（使用立即执行函数确保DOM已加载）
                category_select_js = f'''
                <script>
                (function() {{
                    // 等待DOM加载完成
                    if (document.readyState === 'loading') {{
                        document.addEventListener('DOMContentLoaded', initEditForm);
                    }} else {{
                        initEditForm();
                    }}
                    
                    function initEditForm() {{
                        const category = {json.dumps(edit_data['category'], ensure_ascii=False)};
                        const categorySelect = document.getElementById('categorySelect');
                        if (!categorySelect) return;
                        
                        // 检查是否是自定义分类
                        const isCustom = !['tech', 'life', 'note', 'study'].includes(category);
                        if (isCustom) {{
                            categorySelect.value = 'custom';
                            categorySelect.dispatchEvent(new Event('change'));
                            setTimeout(function() {{
                                const customInput = document.getElementById('customCategoryInput');
                                if (customInput) {{
                                    customInput.value = category;
                                }}
                            }}, 10);
                        }} else {{
                            categorySelect.value = category;
                        }}
                        
                        // 更新字数统计
                        const contentTextarea = document.getElementById('content');
                        if (contentTextarea) {{
                            const wordCountDiv = document.getElementById('word-count');
                            if (wordCountDiv) {{
                                const text = contentTextarea.value || contentTextarea.textContent;
                                const wordCount = text.replace(/\\s/g, '').length;
                                wordCountDiv.textContent = '字数：' + wordCount;
                            }}
                        }}
                        
                        // 更新按钮文本
                        const submitBtn = document.querySelector('button[type="submit"]');
                        if (submitBtn) {{
                            submitBtn.textContent = '更新文章';
                        }}
                    }}
                }})();
                </script>
                '''
                html = html.replace('</body>', category_select_js + '</body>')
            # 如果有草稿数据，注入到页面
            elif draft_data:
                # 在页面中添加JavaScript来填充表单
                draft_js = f'''
                <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    document.getElementById('title').value = {json.dumps(draft_data['title'], ensure_ascii=False)};
                    document.getElementById('content').value = {json.dumps(draft_data['content'], ensure_ascii=False)};
                    const category = {json.dumps(draft_data['category'], ensure_ascii=False)};
                    const categorySelect = document.getElementById('categorySelect');
                    // 检查是否是自定义分类
                    const isCustom = !['tech', 'life', 'note', 'study'].includes(category);
                    if (isCustom) {{
                        categorySelect.value = 'custom';
                        categorySelect.dispatchEvent(new Event('change'));
                        document.getElementById('customCategoryInput').value = category;
                    }} else {{
                        categorySelect.value = category;
                    }}
                    // 更新字数统计
                    if (document.getElementById('content').dispatchEvent) {{
                        document.getElementById('content').dispatchEvent(new Event('input'));
                    }}
                }});
                </script>
                '''
                html = html.replace('</body>', draft_js + '</body>')
            
            response = make_response("200 OK", "text/html", html)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 200, len(str(response)))
            return response
        else:
            title = post_data.get('title', [''])[0]
            content = post_data.get('content', [''])[0]
            # 使用category字段，如果没有则尝试custom_category
            category = post_data.get('category', [''])[0]
            if not category or category == 'custom':
                category = post_data.get('custom_category', [''])[0]
            
            # 清理分类名称（去除前后空格）
            if category:
                category = category.strip()
            
            if title and content and category:
                # 检查是否是编辑文章（通过URL参数edit_id判断）
                edit_id = query.get('edit_id', [''])[0]
                if edit_id and edit_id.isdigit():
                    edit_id_int = int(edit_id)
                    # 验证文章是否属于当前用户
                    post = get_post_by_id(edit_id_int)
                    if post and post.get('author') == current_user and not post.get('is_draft', False):
                        # 更新文章
                        if update_post(edit_id_int, title, content, category, current_user):
                            response = redirect('/profile')
                            if MONITOR_ENABLED:
                                monitor.record_request_end(start_record, 302)
                            return response
                        else:
                            error_msg = '<p style="color:red; margin-top:10px;">更新文章失败</p>'
                            html = render_template('new_post.html')
                            html = html.replace('</form>', error_msg + '</form>')
                            response = make_response("200 OK", "text/html", html)
                            if MONITOR_ENABLED:
                                monitor.record_request_end(start_record, 200, len(str(response)))
                            return response
                
                # 检查是否是发布草稿（通过表单数据draft_id判断）
                draft_id = post_data.get('draft_id', [''])[0]
                if draft_id and draft_id.isdigit():
                    draft_id_int = int(draft_id)
                    # 验证草稿是否属于当前用户
                    draft = get_draft_by_id(draft_id_int, current_user)
                    if draft:
                        # 删除草稿
                        delete_draft(draft_id_int, current_user)
                
                create_post(title, content, category, current_user)
                response = redirect('/')
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 302)
                return response
            else:
                error_msg = '<p style="color:red; margin-top:10px;">请填写所有必填项</p>'
                html = render_template('new_post.html')
                # 在form标签后添加错误信息
                html = html.replace('</form>', error_msg + '</form>')
                response = make_response("200 OK", "text/html", html)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 200, len(str(response)))
                return response

    # ========== 文章详情 ==========
    elif path == '/post':
        post_id = query.get('id', [''])[0]
        if post_id.isdigit():
            post_id_int = int(post_id)
            post = get_post_by_id(post_id_int)
            if post:
                # 增加文章的点击次数
                views_count = increment_post_views(post_id_int)
                
                if current_user:
                    nav = f'<div class="top-nav"><p><a href="/">首页</a><span class="welcome">欢迎, {current_user}!</span><a href="/profile">个人中心</a><a href="/logout">退出</a></p></div>'
                else:
                    nav = '<div class="top-nav"><p><a href="/login">登录</a></p></div>'
                
                content_with_br = post['content'].replace('\n', '<br>')
                raw_content_json = json.dumps(post['content'], ensure_ascii=False)
                
                like_count = len(post.get('likes', []))
                is_liked = current_user and current_user in post.get('likes', [])
                
                favorite_count = len(post.get('favorites', []))
                is_favorited = current_user and current_user in post.get('favorites', [])
                
                # 计算字数和预计阅读时间
                # 如果没有保存字数，则计算
                if 'word_count' in post:
                    word_count = post['word_count']
                else:
                    # 计算字数（去除空格和换行）
                    word_count = len(post['content'].replace(' ', '').replace('\n', '').replace('\r', ''))
                
                # 预计阅读时间 = 字数/300，四舍五入（至少1分钟）
                reading_time = max(1, round(word_count / 300))
                
                category_display = get_category_display_name(post['category'])
                
                # 获取评论列表
                comments = get_post_comments(post_id_int)
                
                # 计算评论总数（包括回复）
                def count_all_comments(comment_list):
                    count = len(comment_list)
                    for comment in comment_list:
                        if 'replies' in comment:
                            count += count_all_comments(comment['replies'])
                    return count
                comment_count = count_all_comments(comments)
                
                # 递归生成评论HTML（支持嵌套回复）
                def render_comment_html(comment, depth=0):
                    comment_id = comment.get('id', 0)
                    comment_author = comment['author'].replace('<', '&lt;').replace('>', '&gt;')
                    comment_content = comment['content'].replace('\n', '<br>').replace('<', '&lt;').replace('>', '&gt;')
                    likes = comment.get('likes', [])
                    like_count = len(likes)
                    is_liked = current_user and current_user in likes
                    replies = comment.get('replies', [])
                    reply_count = len(replies)
                    
                    # 添加左边距表示嵌套深度
                    margin_left = depth * 30
                    indent_class = 'comment-reply' if depth > 0 else ''
                    
                    html = f'''
                    <div class="comment-item {indent_class}" style="margin-left: {margin_left}px;" data-comment-id="{comment_id}">
                        <div class="comment-header">
                            <strong class="comment-author">{comment_author}</strong>
                            <span class="comment-time">{comment['timestamp']}</span>
                        </div>
                        <div class="comment-content">{comment_content}</div>
                        <div class="comment-actions">
                            <button class="comment-like-btn{' liked' if is_liked else ''}" onclick="toggleCommentLike({post_id_int}, {comment_id})">
                                {'❤️' if is_liked else '🤍'} {like_count}
                            </button>
                            <button class="comment-reply-btn" onclick="showReplyForm({comment_id}, '{comment_author}')">
                                💬 回复
                            </button>
                            {f'<span class="reply-count">{reply_count} 条回复</span>' if reply_count > 0 else ''}
                        </div>
                        <div class="reply-form-container" id="reply-form-{comment_id}" style="display:none;">
                            <textarea class="reply-textarea" id="reply-text-{comment_id}" placeholder="回复 {comment_author}..."></textarea>
                            <div class="reply-buttons">
                                <button class="reply-submit-btn" onclick="submitReply({post_id_int}, {comment_id})">发表回复</button>
                                <button class="reply-cancel-btn" onclick="hideReplyForm({comment_id})">取消</button>
                            </div>
                        </div>
                        <div class="replies-list" id="replies-{comment_id}">'''
                    
                    # 递归渲染回复
                    for reply in replies:
                        html += render_comment_html(reply, depth + 1)
                    
                    html += '</div></div>'
                    return html
                
                # 生成评论列表HTML
                if comments:
                    comments_html = ''
                    for comment in comments:
                        comments_html += render_comment_html(comment, 0)
                else:
                    comments_html = '<div class="no-comments">暂无评论，快来发表第一条评论吧！</div>'
                
                html = render_template('post_detail.html').format(
                    title=post['title'],
                    nav=nav,
                    author=post['author'],
                    category=category_display,
                    timestamp=post['timestamp'],
                    views=views_count,
                    word_count=word_count,
                    reading_time=reading_time,
                    post_id=post_id_int,
                    comment_count=comment_count,
                    comments_list=comments_html,
                    content=content_with_br,
                    raw_content_json=raw_content_json,
                    like_button=f'''
                    <div class="like-section">
                        <button class="like-btn{' liked' if is_liked else ''}" id="like-btn" onclick="toggleLike({post['id']})">
                            {'❤️ 已点赞' if is_liked else '🤍 点赞'}
                        </button>
                        <span class="like-count" id="like-count">{like_count} 个赞</span>
                    </div>
                    ''',
                    favorite_button=f'''
                    <div class="favorite-section">
                        <button class="favorite-btn{' favorited' if is_favorited else ''}" id="favorite-btn" onclick="toggleFavorite({post['id']})">
                            {'⭐ 已收藏' if is_favorited else '☆ 收藏'}
                        </button>
                        <span class="favorite-count" id="favorite-count">{favorite_count} 收藏</span>
                    </div>
                    '''
                )
                
                # 构建点赞功能的 JavaScript
                # 在 f-string 中生成 JavaScript 模板字符串需要特殊处理
                like_js_template = '''
                <script>
                function toggleLike(postId) {{
                    fetch('/toggle_like?id=' + postId, {{
                        method: 'GET',
                        credentials: 'same-origin'
                    }})
                    .then(response => {{
                        if (response.status === 401) {{
                            return response.json().then(data => {{
                                alert(data.error || '请左上角登录，发现更多精彩内容');
                                throw new Error('Unauthorized');
                            }});
                        }}
                        return response.json();
                    }})
                    .then(data => {{
                        if (!data) return;
                        const button = document.getElementById('like-btn');
                        const countSpan = document.getElementById('like-count');
                        
                        if (data.liked) {{
                            button.innerHTML = '❤️ 已点赞';
                            button.classList.add('liked');
                        }} else {{
                            button.innerHTML = '🤍 点赞';
                            button.classList.remove('liked');
                        }}
                        
                        countSpan.textContent = data.like_count + ' 个赞';
                    }})
                    .catch(error => {{
                        if (error.message !== 'Unauthorized') {{
                            console.error('点赞请求失败:', error);
                        }}
                    }});
                }}
                </script>
                '''
                # 构建收藏功能的 JavaScript
                favorite_js_template = '''
                <script>
                function toggleFavorite(postId) {{
                    fetch('/toggle_favorite?id=' + postId, {{
                        method: 'GET',
                        credentials: 'same-origin'
                    }})
                    .then(response => {{
                        if (response.status === 401) {{
                            return response.json().then(data => {{
                                alert(data.error || '请左上角登录，发现更多精彩内容');
                                throw new Error('Unauthorized');
                            }});
                        }}
                        return response.json();
                    }})
                    .then(data => {{
                        if (!data) return;
                        const button = document.getElementById('favorite-btn');
                        const countSpan = document.getElementById('favorite-count');
                        
                        if (data.favorited) {{
                            button.innerHTML = '⭐ 已收藏';
                            button.classList.add('favorited');
                        }} else {{
                            button.innerHTML = '☆ 收藏';
                            button.classList.remove('favorited');
                        }}
                        
                        countSpan.textContent = data.favorite_count + ' 收藏';
                    }})
                    .catch(error => {{
                        if (error.message !== 'Unauthorized') {{
                            console.error('收藏请求失败:', error);
                        }}
                    }});
                }}
                </script>
                '''
                
                like_js = like_js_template.format()
                favorite_js = favorite_js_template.format()
                
                # 构建评论功能的 JavaScript
                comment_js = f'''
                <script>
                async function submitComment() {{
                    const commentInput = document.getElementById('comment-content');
                    const commentBtn = document.getElementById('comment-submit-btn');
                    const commentContent = commentInput.value.trim();
                    const postId = {post_id_int}; // 保存文章ID
                    
                    if (!commentContent) {{
                        alert('请输入评论内容');
                        return;
                    }}
                    
                    // 禁用按钮
                    commentBtn.disabled = true;
                    commentBtn.textContent = '提交中...';
                    
                    try {{
                        const response = await fetch('/add_comment', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            credentials: 'same-origin',
                            body: JSON.stringify({{
                                post_id: postId,
                                content: commentContent
                            }})
                        }});
                        
                        // 先检查响应状态和Content-Type，但不读取响应体
                        const contentType = response.headers.get('content-type') || '';
                        const isJson = contentType.includes('application/json');
                        
                        if (response.status === 401) {{
                            if (isJson) {{
                                const data = await response.json();
                                alert(data.error || '请左上角登录，发现更多精彩内容');
                            }} else {{
                                const text = await response.text();
                                alert('请左上角登录，发现更多精彩内容');
                            }}
                            commentBtn.disabled = false;
                            commentBtn.textContent = '发表评论';
                            return;
                        }}
                        
                        // 检查响应是否为JSON格式
                        if (!isJson) {{
                            const text = await response.text();
                            console.error('非JSON响应:', response.status, text);
                            alert('服务器返回了非JSON响应（状态码: ' + response.status + '），请重试');
                            commentBtn.disabled = false;
                            commentBtn.textContent = '发表评论';
                            return;
                        }}
                        
                        // 解析JSON响应
                        let data;
                        try {{
                            data = await response.json();
                        }} catch (parseError) {{
                            console.error('JSON解析失败:', parseError);
                            alert('服务器响应格式错误，请重试');
                            commentBtn.disabled = false;
                            commentBtn.textContent = '发表评论';
                            return;
                        }}
                        
                        if (data.success && data.comment) {{
                            // 清空输入框
                            commentInput.value = '';
                            
                            // 添加新评论到列表顶部
                            const commentsList = document.getElementById('comments-list');
                            const escapedContent = data.comment.content.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\\n/g, '<br>');
                            const escapedAuthor = data.comment.author.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            const commentHtml = `
                                <div class="comment-item" data-comment-id="${{data.comment.id}}">
                                    <div class="comment-header">
                                        <strong class="comment-author">${{escapedAuthor}}</strong>
                                        <span class="comment-time">${{data.comment.timestamp}}</span>
                                    </div>
                                    <div class="comment-content">${{escapedContent}}</div>
                                    <div class="comment-actions">
                                        <button class="comment-like-btn" onclick="toggleCommentLike(postId, ${{data.comment.id}})">
                                            🤍 0
                                        </button>
                                        <button class="comment-reply-btn" onclick="showReplyForm(${{data.comment.id}}, '${{escapedAuthor}}')">
                                            💬 回复
                                        </button>
                                    </div>
                                    <div class="reply-form-container" id="reply-form-${{data.comment.id}}" style="display:none;">
                                        <textarea class="reply-textarea" id="reply-text-${{data.comment.id}}" placeholder="回复 ${{escapedAuthor}}..."></textarea>
                                        <div class="reply-buttons">
                                            <button class="reply-submit-btn" onclick="submitReply(postId, ${{data.comment.id}})">发表回复</button>
                                            <button class="reply-cancel-btn" onclick="hideReplyForm(${{data.comment.id}})">取消</button>
                                        </div>
                                    </div>
                                    <div class="replies-list" id="replies-${{data.comment.id}}"></div>
                                </div>
                            `;
                            
                            // 移除"暂无评论"提示
                            const noComments = commentsList.querySelector('.no-comments');
                            if (noComments) {{
                                noComments.remove();
                            }}
                            
                            // 在列表顶部添加新评论
                            commentsList.insertAdjacentHTML('afterbegin', commentHtml);
                            
                            // 更新评论数
                            const commentsTitle = document.querySelector('.comments-title');
                            const currentCount = parseInt(commentsTitle.textContent.match(/\\d+/)[0]) || 0;
                            commentsTitle.textContent = `💬 评论 (${{currentCount + 1}})`;
                            
                            // 滚动到新评论
                            const newComment = commentsList.firstElementChild;
                            newComment.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                        }} else {{
                            alert(data.message || '发表评论失败，请重试');
                        }}
                    }} catch (error) {{
                        console.error('提交评论失败:', error);
                        console.error('错误详情:', error.message, error.stack);
                        alert('发表评论失败: ' + (error.message || '请检查网络连接'));
                    }} finally {{
                        commentBtn.disabled = false;
                        commentBtn.textContent = '发表评论';
                    }}
                }}
                
                // Enter 键提交评论（Ctrl+Enter）
                document.getElementById('comment-content').addEventListener('keydown', function(e) {{
                    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {{
                        e.preventDefault();
                        submitComment();
                    }}
                }});
                
                // 评论点赞功能
                async function toggleCommentLike(postId, commentId) {{
                    try {{
                        const response = await fetch(`/toggle_comment_like?post_id=${{postId}}&comment_id=${{commentId}}`, {{
                            method: 'GET',
                            credentials: 'same-origin'
                        }});
                        
                        if (response.status === 401) {{
                            const data = await response.json();
                            alert(data.error || '请左上角登录，发现更多精彩内容');
                            return;
                        }}
                        
                        const data = await response.json();
                        if (data) {{
                            const button = document.querySelector(`button[onclick="toggleCommentLike(${{postId}}, ${{commentId}})"]`);
                            if (button) {{
                                if (data.liked) {{
                                    button.innerHTML = `❤️ ${{data.like_count}}`;
                                    button.classList.add('liked');
                                }} else {{
                                    button.innerHTML = `🤍 ${{data.like_count}}`;
                                    button.classList.remove('liked');
                                }}
                            }}
                        }}
                    }} catch (error) {{
                        console.error('评论点赞失败:', error);
                        alert('点赞失败，请重试');
                    }}
                }}
                
                // 显示回复表单
                function showReplyForm(commentId, authorName) {{
                    const replyForm = document.getElementById(`reply-form-${{commentId}}`);
                    if (replyForm) {{
                        replyForm.style.display = 'block';
                        const textarea = document.getElementById(`reply-text-${{commentId}}`);
                        if (textarea) {{
                            textarea.focus();
                            textarea.placeholder = `回复 ${{authorName}}...`;
                        }}
                    }}
                }}
                
                // 隐藏回复表单
                function hideReplyForm(commentId) {{
                    const replyForm = document.getElementById(`reply-form-${{commentId}}`);
                    if (replyForm) {{
                        replyForm.style.display = 'none';
                        const textarea = document.getElementById(`reply-text-${{commentId}}`);
                        if (textarea) {{
                            textarea.value = '';
                        }}
                    }}
                }}
                
                // 提交回复
                async function submitReply(postId, parentCommentId) {{
                    const textarea = document.getElementById(`reply-text-${{parentCommentId}}`);
                    const content = textarea ? textarea.value.trim() : '';
                    
                    if (!content) {{
                        alert('请输入回复内容');
                        return;
                    }}
                    
                    try {{
                        const response = await fetch('/add_comment', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            credentials: 'same-origin',
                            body: JSON.stringify({{
                                post_id: postId,
                                content: content,
                                parent_comment_id: parentCommentId
                            }})
                        }});
                        
                        // 先检查响应状态和Content-Type，但不读取响应体
                        const contentType = response.headers.get('content-type') || '';
                        const isJson = contentType.includes('application/json');
                        
                        if (response.status === 401) {{
                            if (isJson) {{
                                const data = await response.json();
                                alert(data.error || '请左上角登录，发现更多精彩内容');
                            }} else {{
                                alert('请左上角登录，发现更多精彩内容');
                            }}
                            return;
                        }}
                        
                        // 检查响应是否为JSON格式
                        if (!isJson) {{
                            const text = await response.text();
                            console.error('非JSON响应:', response.status, text);
                            alert('服务器返回了非JSON响应（状态码: ' + response.status + '），请重试');
                            return;
                        }}
                        
                        // 解析JSON响应
                        let data;
                        try {{
                            data = await response.json();
                        }} catch (parseError) {{
                            console.error('JSON解析失败:', parseError);
                            alert('服务器响应格式错误，请重试');
                            return;
                        }}
                        
                        if (data.success && data.comment) {{
                            // 清空输入框
                            textarea.value = '';
                            hideReplyForm(parentCommentId);
                            
                            // 添加回复到对应评论的replies列表
                            const repliesList = document.getElementById(`replies-${{parentCommentId}}`);
                            if (repliesList) {{
                                const escapedContent = data.comment.content.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\\n/g, '<br>');
                                const escapedAuthor = data.comment.author.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                                
                                // 获取当前评论的margin-left值，用于计算回复的缩进
                                const parentComment = document.querySelector(`[data-comment-id="${{parentCommentId}}"]`);
                                const parentMarginLeft = parentComment ? parseInt(window.getComputedStyle(parentComment).marginLeft) || 0 : 0;
                                const replyMarginLeft = parentMarginLeft + 30;
                                
                                const replyHtml = `
                                    <div class="comment-item comment-reply" style="margin-left: ${{replyMarginLeft}}px;" data-comment-id="${{data.comment.id}}">
                                        <div class="comment-header">
                                            <strong class="comment-author">${{escapedAuthor}}</strong>
                                            <span class="comment-time">${{data.comment.timestamp}}</span>
                                        </div>
                                        <div class="comment-content">${{escapedContent}}</div>
                                        <div class="comment-actions">
                                            <button class="comment-like-btn" onclick="toggleCommentLike(${{postId}}, ${{data.comment.id}})">
                                                🤍 0
                                            </button>
                                            <button class="comment-reply-btn" onclick="showReplyForm(${{data.comment.id}}, '${{escapedAuthor}}')">
                                                💬 回复
                                            </button>
                                        </div>
                                        <div class="reply-form-container" id="reply-form-${{data.comment.id}}" style="display:none;">
                                            <textarea class="reply-textarea" id="reply-text-${{data.comment.id}}" placeholder="回复 ${{escapedAuthor}}..."></textarea>
                                            <div class="reply-buttons">
                                                <button class="reply-submit-btn" onclick="submitReply(${{postId}}, ${{data.comment.id}})">发表回复</button>
                                                <button class="reply-cancel-btn" onclick="hideReplyForm(${{data.comment.id}})">取消</button>
                                            </div>
                                        </div>
                                        <div class="replies-list" id="replies-${{data.comment.id}}"></div>
                                    </div>
                                `;
                                
                                repliesList.insertAdjacentHTML('beforeend', replyHtml);
                                
                                // 更新回复计数
                                const replyCountSpan = parentComment ? parentComment.querySelector('.reply-count') : null;
                                if (replyCountSpan) {{
                                    const currentCount = parseInt(replyCountSpan.textContent) || 0;
                                    replyCountSpan.textContent = `${{currentCount + 1}} 条回复`;
                                }} else {{
                                    // 如果没有回复计数元素，添加一个
                                    const commentActions = parentComment ? parentComment.querySelector('.comment-actions') : null;
                                    if (commentActions) {{
                                        const countSpan = document.createElement('span');
                                        countSpan.className = 'reply-count';
                                        countSpan.textContent = '1 条回复';
                                        commentActions.appendChild(countSpan);
                                    }}
                                }}
                                
                                // 滚动到新回复
                                const newReply = repliesList.lastElementChild;
                                if (newReply) {{
                                    newReply.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                                }}
                            }}
                            
                            // 更新评论总数
                            const commentsTitle = document.querySelector('.comments-title');
                            if (commentsTitle) {{
                                const currentCount = parseInt(commentsTitle.textContent.match(/\\d+/)[0]) || 0;
                                commentsTitle.textContent = `💬 评论 (${{currentCount + 1}})`;
                            }}
                        }} else {{
                            alert(data.message || '发表回复失败，请重试');
                        }}
                    }} catch (error) {{
                        console.error('提交回复失败:', error);
                        console.error('错误详情:', error.message, error.stack);
                        alert('发表回复失败: ' + (error.message || '请检查网络连接'));
                    }}
                }}
                </script>
                '''
                
                html = html.replace('</body>', f'{like_js}{favorite_js}{comment_js}</body>')
                
                response = make_response("200 OK", "text/html", html)
                if MONITOR_ENABLED:
                    monitor.record_request_end(start_record, 200, len(str(response)))
                return response
        
        response = make_response("404 Not Found", "text/html", "<h1>文章未找到</h1>")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 404)
        return response

    # ========== AI 阅读助手 ==========
    elif path == '/ai_assist':
        if method != 'POST':
            response = make_response("405 Method Not Allowed", "text/plain", "Only POST allowed")
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 405)
            return response
        
        try:
            body_dict = json.loads(body)
            article_text = body_dict.get('text', '').strip()
            conversation = body_dict.get('conversation', [])
        except (json.JSONDecodeError, TypeError):
            response_data = json.dumps({"error": "Invalid JSON"}, ensure_ascii=False)
            response = make_response("400 Bad Request", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 400, len(response_data))
            return response
        
        if not article_text:
            response_data = json.dumps({"error": "文章内容为空"}, ensure_ascii=False)
            response = make_response("400 Bad Request", "application/json", response_data)
            if MONITOR_ENABLED:
                monitor.record_request_end(start_record, 400, len(response_data))
            return response
        
        analysis = call_ai_assist(article_text, conversation)
        response_data = json.dumps({"analysis": analysis}, ensure_ascii=False)
        response = make_response("200 OK", "application/json", response_data)
        
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 200, len(response_data))
        return response

    # ========== 404 处理 ==========
    else:
        response = make_response("404 Not Found", "text/html", "<h1>页面未找到</h1><p><a href='/'>返回首页</a></p>")
        if MONITOR_ENABLED:
            monitor.record_request_end(start_record, 404)
        return response


def handle_static_file(path):
    """处理静态文件请求"""
    import os
    static_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'static'))
    rel_path = path[len('/static/'):]

    # 防止路径穿越攻击
    if '..' in rel_path or rel_path.startswith('/') or rel_path.startswith('\\'):
        resp = "HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nAccess denied"
        return resp.encode()

    rel_path = rel_path.replace('/', os.sep)
    file_path = os.path.abspath(os.path.join(static_root, rel_path))

    if not file_path.startswith(static_root + os.sep) and file_path != static_root:
        resp = "HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nAccess denied"
        return resp.encode()

    if os.path.isfile(file_path):
        if file_path.endswith('.png'):
            mime = 'image/png'
        elif file_path.endswith(('.jpg', '.jpeg')):
            mime = 'image/jpeg'
        elif file_path.endswith('.css'):
            mime = 'text/css'
        elif file_path.endswith('.js'):
            mime = 'application/javascript'
        elif file_path.endswith('.mp4') or file_path.endswith('.webm') or file_path.endswith('.ogg'):
            mime = 'video/mp4'
        else:
            mime = 'application/octet-stream'

        try:
            with open(file_path, 'rb') as f:
                content = f.read()

            response_headers = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: {mime}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode('utf-8')

            return response_headers + content

        except Exception as e:
            print(f"[ERROR] Failed to read static file: {e}")

    resp = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nFile not found"
    return resp.encode()


# ------------------------
# 客户端处理 & 主循环
# ------------------------

def handle_client(conn, addr):
    try:
        # 先读取头部（直到 \r\n\r\n）
        request_data = b""
        while b"\r\n\r\n" not in request_data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            request_data += chunk

        # 分离头部和可能的部分 body
        header_end = request_data.find(b"\r\n\r\n") + 4
        headers_part = request_data[:header_end]
        body_part = request_data[header_end:]

        # 解析头部以获取 Content-Length
        headers_text = headers_part.decode('utf-8', errors='ignore')
        lines = headers_text.split('\r\n')
        headers = {}
        content_length = 0
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()
                if key.strip().lower() == 'content-length':
                    try:
                        content_length = int(value.strip())
                    except ValueError:
                        content_length = 0

        # 计算还需要读多少 body
        body_needed = content_length - len(body_part)
        if body_needed > 0:
            while body_needed > 0:
                chunk = conn.recv(min(body_needed, 4096))
                if not chunk:
                    break
                body_part += chunk
                body_needed -= len(chunk)

        # 完整请求文本（用于解析）
        full_request = headers_text + body_part.decode('utf-8', errors='ignore')

        req = parse_http_request(full_request)
        if not req:
            bad_resp = make_response("400 Bad Request", "text/plain", "Bad Request")
            conn.sendall(bad_resp.encode('utf-8'))
            return

        response = handle_request(req)
        if isinstance(response, str):
            response = response.encode('utf-8')
        conn.sendall(response)

    except Exception as e:
        print(f"[ERROR] {e}")
        error_resp = make_response("500 Internal Server Error", "text/plain", "Server Error")
        conn.sendall(error_resp.encode('utf-8'))
    finally:
        conn.close()


def start_server():
    print(f"[INFO] 监控功能: {'已启用' if MONITOR_ENABLED else '已禁用'}")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((SERVER_HOST, SERVER_PORT))
        s.listen(5)
        print(f"[LISTENING] Blog server running on http://{SERVER_HOST}:{SERVER_PORT}")
        
        if MONITOR_ENABLED:
            print(f"[MONITORING] 监控系统已启动，访问 http://{SERVER_HOST}:{SERVER_PORT}/monitor 查看监控面板")
        
        while True:
            conn, addr = s.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()


if __name__ == "__main__":
    start_server()