import time
from storage import load_posts, save_posts

def get_all_posts():
    posts = load_posts()
    # 过滤掉草稿
    posts = [p for p in posts if not p.get('is_draft', False)]
    # 添加点赞数、收藏数和阅读量信息
    for post in posts:
        if 'likes' not in post:
            post['likes'] = []
        if 'favorites' not in post:
            post['favorites'] = []
        if 'comments' not in post:
            post['comments'] = []
        if 'views' not in post:
            post['views'] = 0
        post['like_count'] = len(post['likes'])
        post['favorite_count'] = len(post['favorites'])
    return posts

def get_post_by_id(post_id: int):
    posts = load_posts()
    for p in posts:
        if p['id'] == post_id:
            if 'likes' not in p:
                p['likes'] = []
            if 'favorites' not in p:
                p['favorites'] = []
            if 'comments' not in p:
                p['comments'] = []
            if 'views' not in p:
                p['views'] = 0
            # 如果没有保存字数，则计算
            if 'word_count' not in p:
                p['word_count'] = len(p['content'].replace(' ', '').replace('\n', '').replace('\r', ''))
            p['like_count'] = len(p['likes'])
            p['favorite_count'] = len(p['favorites'])
            p['comment_count'] = len(p['comments'])
            return p
    return None

def increment_post_views(post_id: int):
    """增加文章的点击次数"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id:
            if 'views' not in post:
                post['views'] = 0
            post['views'] = post.get('views', 0) + 1
            save_posts(posts)
            return post['views']
    return 0

def create_post(title: str, content: str, category: str, author: str):
    posts = load_posts()
    # 计算字数（去除空格和换行）
    word_count = len(content.replace(' ', '').replace('\n', '').replace('\r', ''))
    new_post = {
        'id': len(posts) + 1,
        'title': title,
        'content': content,
        'author': author,
        'category': category,
        'timestamp': time.strftime("%Y-%m-%d %H:%M"),
        'likes': [],  # 初始化点赞列表
        'favorites': [],  # 初始化收藏列表
        'comments': [],  # 初始化评论列表
        'views': 0,  # 初始化阅读量
        'word_count': word_count  # 保存字数
    }
    posts.append(new_post)
    save_posts(posts)

def update_post(post_id: int, title: str, content: str, category: str, author: str):
    """更新文章（重新发布，更新时间）"""
    posts = load_posts()
    for post in posts:
        if post['id'] == post_id and post.get('author') == author and not post.get('is_draft', False):
            # 计算新的字数
            word_count = len(content.replace(' ', '').replace('\n', '').replace('\r', ''))
            # 更新文章内容和时间
            post['title'] = title
            post['content'] = content
            post['category'] = category
            post['timestamp'] = time.strftime("%Y-%m-%d %H:%M")  # 更新时间为新发布的时间
            post['word_count'] = word_count
            # 保留原有的点赞、收藏、评论、阅读量等数据
            save_posts(posts)
            return True
    return False

def filter_posts(posts, search_query: str = "", category_filter: str = ""):
    # 过滤掉草稿
    posts = [p for p in posts if not p.get('is_draft', False)]
    if search_query:
        posts = [p for p in posts if 
                 search_query.lower() in p['title'].lower() or 
                 search_query.lower() in p['content'].lower()]
    if category_filter:
        posts = [p for p in posts if p['category'] == category_filter]
    return posts

def get_all_categories():
    """获取所有已存在的分类"""
    posts = load_posts()
    categories = set()
    for post in posts:
        if 'category' in post and post['category']:
            categories.add(post['category'])
    return sorted(list(categories))

def get_category_display_name(category):
    """获取分类的显示名称"""
    category_map = {
        'tech': '技术',
        'life': '生活',
        'note': '随笔',
        'study': '学习'
    }
    return category_map.get(category, category)

def get_unique_comment_authors(comments):
    """递归获取所有评论的唯一作者集合（每个用户只算一次）"""
    authors = set()
    
    def collect_authors(comment_list):
        for comment in comment_list:
            if 'author' in comment:
                authors.add(comment['author'])
            # 递归处理回复
            if 'replies' in comment and comment['replies']:
                collect_authors(comment['replies'])
    
    collect_authors(comments)
    return authors

def get_ranking_posts():
    """获取按热度排序的文章列表
    热度 = 阅读量 × 0.3 + 点赞数 × 2 + 收藏数 × 3 + 有效评论数 × 4
    有效评论数：每个账号只算一次（防止刷评论提高热度）
    """
    posts = get_all_posts()
    
    # 为每篇文章计算热度
    for post in posts:
        views = post.get('views', 0)
        like_count = len(post.get('likes', []))
        favorite_count = len(post.get('favorites', []))
        
        # 计算有效评论数（每个用户只算一次）
        comments = post.get('comments', [])
        unique_comment_authors = get_unique_comment_authors(comments)
        valid_comment_count = len(unique_comment_authors)
        
        # 计算热度
        popularity = views * 0.3 + like_count * 2 + favorite_count * 3 + valid_comment_count * 4
        post['popularity'] = popularity
    
    # 按热度降序排序
    posts.sort(key=lambda x: x['popularity'], reverse=True)
    
    return posts