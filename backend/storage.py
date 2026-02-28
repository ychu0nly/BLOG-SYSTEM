import json
import os
from config import USERS_FILE, POSTS_FILE 

# 确保 data 目录存在
os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump({}, f)

if not os.path.exists(POSTS_FILE):
    with open(POSTS_FILE, 'w') as f:
        json.dump([], f)

def load_users():
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2)

def load_posts():
    with open(POSTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_posts(posts):
    with open(POSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)

def toggle_like(post_id: int, username: str):
    """切换点赞状态"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            if 'likes' not in post:
                post['likes'] = []
            if username in post['likes']:
                post['likes'].remove(username)
                liked = False
            else:
                post['likes'].append(username)
                liked = True
            save_posts(posts)
            return liked, len(post['likes'])
    return False, 0

def get_post_likes(post_id: int):
    """获取文章点赞数"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            return len(post.get('likes', []))
    return 0

def toggle_favorite(post_id: int, username: str):
    """切换收藏状态"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            if 'favorites' not in post:
                post['favorites'] = []
            if username in post['favorites']:
                post['favorites'].remove(username)
                favorited = False
            else:
                post['favorites'].append(username)
                favorited = True
            save_posts(posts)
            return favorited, len(post['favorites'])
    return False, 0

def get_post_favorites(post_id: int):
    """获取文章收藏数"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            return len(post.get('favorites', []))
    return 0

def get_user_favorites(username: str):
    """获取用户收藏的所有文章"""
    posts = load_posts()
    favorites = []
    for post in posts:
        if 'favorites' in post and username in post.get('favorites', []):
            favorites.append(post)
    return favorites

def save_draft(title: str, content: str, category: str, author: str, draft_id: int = None):
    """保存草稿"""
    posts = load_posts()
    draft_found = False
    
    # 若提供了draft_id，则优先使用
    if draft_id:
        for post in posts:
            if post['id'] == draft_id and post.get('is_draft', False) and post.get('author') == author:
                # 更新现有草稿
                post['title'] = title or '无标题'
                post['content'] = content
                post['category'] = category or 'tech'
                post['timestamp'] = __import__('time').strftime("%Y-%m-%d %H:%M")
                post['word_count'] = len(content.replace(' ', '').replace('\n', '').replace('\r', '')) if content else 0
                draft_found = True
                break
    
    if not draft_found:
        # 创建新草稿
        new_draft = {
            'id': len(posts) + 1,
            'title': title or '无标题',
            'content': content,
            'author': author,
            'category': category or 'tech',
            'timestamp': __import__('time').strftime("%Y-%m-%d %H:%M"),
            'is_draft': True,
            'likes': [],
            'favorites': [],
            'views': 0,
            'word_count': len(content.replace(' ', '').replace('\n', '').replace('\r', '')) if content else 0
        }
        posts.append(new_draft)
    
    save_posts(posts)
    return True

def get_user_drafts(username: str):
    """获取用户的所有草稿"""
    posts = load_posts()
    drafts = []
    for post in posts:
        if post.get('is_draft', False) and post.get('author') == username:
            drafts.append(post)
    return drafts

def get_user_posts(username: str):
    """获取用户发布的所有文章（排除草稿）"""
    posts = load_posts()
    user_posts = []
    for post in posts:
        if post.get('author') == username and not post.get('is_draft', False):
            user_posts.append(post)
    # 按时间倒序排序（最新的在前）
    user_posts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return user_posts

def get_draft_by_id(draft_id: int, username: str):
    """根据ID获取草稿（仅作者本人可见）"""
    posts = load_posts()
    for post in posts:
        if post['id'] == draft_id and post.get('is_draft', False) and post.get('author') == username:
            return post
    return None

def delete_draft(draft_id: int, username: str):
    """删除草稿"""
    posts = load_posts()
    for i, post in enumerate(posts):
        if post['id'] == draft_id and post.get('is_draft', False) and post.get('author') == username:
            posts.pop(i)
            save_posts(posts)
            return True
    return False

def add_comment(post_id: int, username: str, content: str, parent_comment_id: int = None):
    """添加评论，支持回复（通过parent_comment_id指定父评论）"""
    import time
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            if 'comments' not in post:
                post['comments'] = []
            
            # 生成评论ID（找到最大ID+1）
            max_id = 0
            def find_max_id(comments):
                nonlocal max_id
                for comment in comments:
                    if comment.get('id', 0) > max_id:
                        max_id = comment.get('id', 0)
                    if 'replies' in comment:
                        find_max_id(comment['replies'])
            find_max_id(post['comments'])
            new_comment_id = max_id + 1
            
            comment = {
                'id': new_comment_id,
                'author': username,
                'content': content,
                'timestamp': time.strftime("%Y-%m-%d %H:%M"),
                'likes': [],  # 点赞用户列表
                'replies': []  # 回复列表
            }
            
            # 如果是回复，添加到父评论的replies中
            if parent_comment_id:
                def add_reply(comments):
                    for comment_item in comments:
                        if comment_item['id'] == parent_comment_id:
                            comment_item.setdefault('replies', []).append(comment)
                            return True
                        if 'replies' in comment_item:
                            if add_reply(comment_item['replies']):
                                return True
                    return False
                if not add_reply(post['comments']):
                    # 如果找不到父评论，作为顶级评论添加
                    post['comments'].append(comment)
            else:
                # 顶级评论
                post['comments'].append(comment)
            
            save_posts(posts)
            return comment
    return None

def get_post_comments(post_id: int):
    """获取文章的所有评论"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            comments = post.get('comments', [])
            # 确保所有评论都有likes和replies字段
            def ensure_fields(comment_list):
                for comment in comment_list:
                    if 'likes' not in comment:
                        comment['likes'] = []
                    if 'replies' not in comment:
                        comment['replies'] = []
                    if 'replies' in comment:
                        ensure_fields(comment['replies'])
            ensure_fields(comments)
            return comments
    return []

def toggle_comment_like(post_id: int, comment_id: int, username: str):
    """切换评论点赞状态"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            def toggle_like_in_comments(comments):
                for comment in comments:
                    if comment['id'] == comment_id:
                        if 'likes' not in comment:
                            comment['likes'] = []
                        if username in comment['likes']:
                            comment['likes'].remove(username)
                            liked = False
                        else:
                            comment['likes'].append(username)
                            liked = True
                        save_posts(posts)
                        return liked, len(comment['likes'])
                    if 'replies' in comment:
                        result = toggle_like_in_comments(comment['replies'])
                        if result:
                            return result
                return None
            
            result = toggle_like_in_comments(post.get('comments', []))
            if result:
                return result
    
    return False, 0