import json
import time
import threading
import os
import psutil
from datetime import datetime, timedelta
from collections import defaultdict, deque


class EnhancedPerformanceMonitor:
    """性能监控主类"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if not self._initialized:
            # 配置
            self.enabled = True
            self.data_path = "data/monitoring.json"
            self.retention_days = 7
            self.buffer_size = 10  # 缓冲区大小

            # 内存缓冲区
            self.data_buffer = []
            self.buffer_lock = threading.RLock()

            # 初始化时间
            self.start_time = datetime.now()

            # 系统指标
            self.metrics = {
                'total_requests': 0,  # 总请求数
                'total_errors': 0,  # 总错误数
                'current_connections': 0,  # 当前连接数
                'active_clients': set(),  # 活跃客户端
                'response_times': deque(maxlen=500),  # 响应时间
                'requests_by_endpoint': defaultdict(int),  # 按端点统计
                'errors_by_endpoint': defaultdict(int),  # 按端点错误
                'status_codes': defaultdict(int),  # 状态码分布
                'throughput_minute': 0,  # 每分钟吞吐量
                'throughput_history': deque(maxlen=60),  # 吞吐量历史
                'last_minute_requests': deque(maxlen=300),  # 最近请求时间戳
                'user_sessions': set(),  # 活跃用户会话
                'request_sizes': deque(maxlen=200),  # 请求大小
                'response_sizes': deque(maxlen=200),  # 响应大小
            }

            # 初始化数据文件
            self._ensure_data_file()

            # 启动后台线程
            self._start_throughput_calculator()
            self._start_cleanup_thread()

            print(f"[MONITORING] 监控模块初始化完成于 {self.start_time}")
            self._initialized = True

    def _ensure_data_file(self):
        """确保数据文件存在"""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        if not os.path.exists(self.data_path):
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump({"version": "2.0", "data": []}, f, indent=2)

    def _start_throughput_calculator(self):
        """启动吞吐量计算线程"""
        def calculate_throughput():
            while True:
                time.sleep(60)  # 每分钟计算一次
                try:
                    with self.buffer_lock:
                        current_time = datetime.now()
                        minute_ago = current_time - timedelta(minutes=1)
                        recent_requests = [
                            ts for ts in self.metrics['last_minute_requests']
                            if ts > minute_ago
                        ]
                        minute_count = len(recent_requests)
                        self.metrics['throughput_minute'] = minute_count
                        self.metrics['throughput_history'].append(minute_count)
                except Exception as e:
                    print(f"[MONITORING] 计算吞吐量失败: {e}")

        threading.Thread(target=calculate_throughput, daemon=True).start()

    def _start_cleanup_thread(self):
        """启动数据清理线程"""
        def cleanup_old_data():
            while True:
                time.sleep(3600)  # 每小时清理一次
                try:
                    data_dir = os.path.dirname(self.data_path)
                    if os.path.exists(data_dir):
                        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
                        for filename in os.listdir(data_dir):
                            if filename.startswith('monitoring_') and filename.endswith('.json'):
                                try:
                                    date_str = filename[11:21]  # monitoring_YYYY-MM-DD.json
                                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                                    if file_date < cutoff_date:
                                        os.remove(os.path.join(data_dir, filename))
                                        print(f"[MONITORING] 清理过期文件: {filename}")
                                except Exception as e:
                                    print(f"[MONITORING] 处理文件 {filename} 失败: {e}")
                except Exception as e:
                    print(f"[MONITORING] 清理线程错误: {e}")

        threading.Thread(target=cleanup_old_data, daemon=True).start()

    def record_request_start(self, client_id, path, method="GET"):
        """记录请求开始"""
        if not self.enabled:
            return {
                'id': f'dummy_{int(time.time())}',
                'client_id': client_id,
                'path': path,
                'method': method,
                'start_time': time.perf_counter(),
                'timestamp': datetime.now().isoformat()
            }

        request_id = f"{client_id}_{int(time.time()*1000)}"
        start_time = time.perf_counter()

        with self.buffer_lock:
            self.metrics['current_connections'] += 1
            self.metrics['active_clients'].add(client_id)
            self.metrics['total_requests'] += 1
            self.metrics['requests_by_endpoint'][path] += 1
            now = datetime.now()
            self.metrics['last_minute_requests'].append(now)

        return {
            'id': request_id,
            'client_id': client_id,
            'path': path,
            'method': method,
            'start_time': start_time,
            'timestamp': now.isoformat()
        }

    def record_request_end(self, start_record, status_code, data_size=0):
        """记录请求结束"""
        if not self.enabled or not start_record:
            return

        end_time = time.perf_counter()
        response_time = (end_time - start_record['start_time']) * 1000  # 毫秒

        record = {
            **start_record,
            'status_code': status_code,
            'response_time_ms': round(response_time, 2),
            'data_size': data_size,
            'end_timestamp': datetime.now().isoformat()
        }

        with self.buffer_lock:
            self.metrics['current_connections'] = max(0, self.metrics['current_connections'] - 1)
            self.metrics['active_clients'].discard(start_record['client_id'])
            self.metrics['response_times'].append(response_time)
            self.metrics['response_sizes'].append(data_size)

            if status_code >= 400:
                self.metrics['total_errors'] += 1
                self.metrics['errors_by_endpoint'][start_record['path']] += 1

            self.metrics['status_codes'][str(status_code)] += 1
            self.data_buffer.append(record)

            if len(self.data_buffer) >= self.buffer_size:
                self._flush_buffer()

        return record

    def record_user_session(self, user_id, action="login"):
        """记录用户会话"""
        if not self.enabled:
            return

        with self.buffer_lock:
            if action == "login":
                self.metrics['user_sessions'].add(user_id)
            elif action == "logout":
                self.metrics['user_sessions'].discard(user_id)

    def _flush_buffer(self):
        """将缓冲区数据写入文件"""
        if not self.data_buffer:
            return

        with self.buffer_lock:
            buffer_copy = self.data_buffer.copy()
            self.data_buffer.clear()
            threading.Thread(target=self._write_to_disk, args=(buffer_copy,), daemon=True).start()

    def _write_to_disk(self, records):
        """异步写入磁盘"""
        try:
            daily_data = defaultdict(list)
            for record in records:
                date_str = record.get('timestamp', '')[:10] if 'timestamp' in record else datetime.now().strftime("%Y-%m-%d")
                daily_data[date_str].append(record)

            for date_str, date_records in daily_data.items():
                filename = f"data/monitoring_{date_str}.json"
                existing_data = []

                if os.path.exists(filename):
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            existing_data = data.get('data', [])
                    except (json.JSONDecodeError, IOError):
                        existing_data = []

                existing_data.extend(date_records)
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump({
                        "version": "2.0",
                        "date": date_str,
                        "data": existing_data[-5000:]
                    }, f, indent=2)

        except Exception as e:
            print(f"[MONITORING] 写入数据失败: {e}")

    def get_realtime_metrics(self):
        """获取实时指标"""
        with self.buffer_lock:
            # 响应时间统计
            response_times = list(self.metrics['response_times'])
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
            else:
                avg_response_time = 0

            # 错误率和成功率
            total_requests = max(1, self.metrics['total_requests'])
            total_errors = self.metrics['total_errors']
            error_rate = (total_errors / total_requests * 100)
            success_rate = 100 - error_rate

            # 请求/响应大小统计
            request_sizes = list(self.metrics['request_sizes'])
            response_sizes = list(self.metrics['response_sizes'])
            avg_request_size = sum(request_sizes) / len(request_sizes) if request_sizes else 1024  # 默认1KB
            avg_response_size = sum(response_sizes) / len(response_sizes) if response_sizes else 5120  # 默认5KB

            # 网络延迟估算（基于响应时间的20%）
            network_latency_factor = 0.2
            avg_network_latency = avg_response_time * network_latency_factor

            # 活跃用户
            active_users = len(self.metrics['user_sessions'])
            
            # 每分钟吞吐量
            throughput_last_minute = self.metrics['throughput_minute']
            
            # 计算带宽估算（比特每秒）
            avg_total_transfer = avg_request_size + avg_response_size
            estimated_bandwidth_bps = 0
            if throughput_last_minute > 0 and avg_total_transfer > 0:
                estimated_bandwidth_bps = (avg_total_transfer * throughput_last_minute * 8) / 60

            # 运行时间
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            uptime_str = self._format_uptime(uptime_seconds)

            # 返回核心指标
            return {
                # 6个核心指标
                'avg_response_time_ms': round(avg_response_time, 2),          # 平均响应时间
                'success_rate': round(success_rate, 2),                        # 请求成功率
                'throughput_last_minute': throughput_last_minute,              # 请求吞吐量（次/分钟）
                'avg_network_latency_ms': round(avg_network_latency, 2),       # 平均网络延迟
                'current_bandwidth_bps': round(estimated_bandwidth_bps),       # 带宽使用（比特每秒）
                'active_users': active_users,                                   # 活跃用户
                
                # 附加基础信息
                'total_requests': total_requests,
                'total_errors': total_errors,
                'concurrent_connections': self.metrics['current_connections'],
                'uptime_seconds': uptime_seconds,
                'uptime_formatted': uptime_str,
                'server_start_time': self.start_time.isoformat(),
                'timestamp': datetime.now().isoformat()
            }

    def _format_uptime(self, seconds):
        """格式化运行时间"""
        days = int(seconds // (24 * 3600))
        hours = int((seconds % (24 * 3600)) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if days > 0:
            return f"{days}天{hours}小时{minutes}分"
        elif hours > 0:
            return f"{hours}小时{minutes}分{secs}秒"
        elif minutes > 0:
            return f"{minutes}分{secs}秒"
        else:
            return f"{secs}秒"

    def get_historical_data(self, hours=1, endpoint_filter=None):
        """获取历史数据"""
        try:
            data = []
            cutoff_time = datetime.now() - timedelta(hours=hours)

            # 主文件
            if os.path.exists(self.data_path):
                try:
                    with open(self.data_path, 'r', encoding='utf-8') as f:
                        file_data = json.load(f).get('data', [])
                        for record in file_data:
                            try:
                                record_time = datetime.fromisoformat(record.get('timestamp', ''))
                                if record_time >= cutoff_time:
                                    data.append(record)
                            except (ValueError, TypeError):
                                continue
                except (json.JSONDecodeError, IOError):
                    pass

            # 分片文件
            for i in range(self.retention_days):
                date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                filename = f"data/monitoring_{date_str}.json"
                if os.path.exists(filename):
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            file_data = json.load(f).get('data', [])
                    except (json.JSONDecodeError, IOError):
                        continue
                    for record in file_data:
                        try:
                            record_time = datetime.fromisoformat(record.get('timestamp', ''))
                            if record_time >= cutoff_time:
                                data.append(record)
                        except (ValueError, TypeError):
                            continue

            if endpoint_filter:
                data = [record for record in data if record.get('path') == endpoint_filter]

            return data
        except Exception as e:
            print(f"[MONITORING] 读取历史数据失败: {e}")
            return []

    def get_endpoint_statistics(self, hours=24):
        """获取端点统计信息"""
        historical_data = self.get_historical_data(hours)
        stats = {}
        for record in historical_data:
            path = record.get('path', 'unknown')
            if path not in stats:
                stats[path] = {
                    'count': 0, 'success': 0, 'errors': 0, 'total_time': 0,
                    'min_time': float('inf'), 'max_time': 0, 'last_accessed': None,
                    'total_data_size': 0
                }
            s = stats[path]
            s['count'] += 1
            s['last_accessed'] = record.get('timestamp')
            rt = record.get('response_time_ms', 0)
            s['total_time'] += rt
            s['min_time'] = min(s['min_time'], rt)
            s['max_time'] = max(s['max_time'], rt)
            s['total_data_size'] += record.get('data_size', 0)
            status = record.get('status_code', 500)
            if 200 <= status < 400:
                s['success'] += 1
            else:
                s['errors'] += 1

        for path in stats:
            if stats[path]['count'] > 0:
                stats[path]['avg_time'] = stats[path]['total_time'] / stats[path]['count']
                if stats[path]['min_time'] == float('inf'):
                    stats[path]['min_time'] = 0
                stats[path]['success_rate'] = round(
                    (stats[path]['success'] / stats[path]['count'] * 100) if stats[path]['count'] > 0 else 0, 1
                )
                stats[path]['avg_data_size'] = stats[path]['total_data_size'] / stats[path]['count']
        return stats

    def get_system_status(self):
        """获取系统状态摘要"""
        metrics = self.get_realtime_metrics()
        avg_response_time = metrics.get('avg_response_time_ms', 0)
        success_rate = metrics.get('success_rate', 100)

        # 使用psutil获取系统资源
        try:
            process = psutil.Process()
            memory_percent = process.memory_percent()
            cpu_percent = process.cpu_percent()
        except:
            memory_percent = 0
            cpu_percent = 0

        status = "healthy"
        issues = []
        
        # 基于平均响应时间判断
        if avg_response_time > 1000:
            status = "critical"
            issues.append(f"响应时间过高: {avg_response_time:.0f}ms")
        elif avg_response_time > 500:
            status = "warning"
            issues.append(f"响应时间较高: {avg_response_time:.0f}ms")
        
        # 基于成功率判断
        if success_rate < 60:
            status = "critical"
            issues.append(f"成功率过低: {success_rate:.1f}%")
        elif success_rate < 70:
            status = "warning"
            issues.append(f"成功率较低: {success_rate:.1f}%")

        return {
            'status': status,
            'issues': issues,
            'avg_response_time_ms': avg_response_time,
            'success_rate': success_rate,
            'throughput_last_minute': metrics.get('throughput_last_minute', 0),
            'avg_network_latency_ms': metrics.get('avg_network_latency_ms', 0),
            'active_users': metrics.get('active_users', 0),
            'uptime_seconds': metrics.get('uptime_seconds', 0),
            'uptime_formatted': metrics.get('uptime_formatted', '0秒'),
            'server_start_time': metrics.get('server_start_time'),
            'timestamp': metrics.get('timestamp')
        }

    def clear_data(self):
        """清空数据（测试用）"""
        with self.buffer_lock:
            self.metrics = {
                'total_requests': 0,
                'total_errors': 0,
                'current_connections': 0,
                'active_clients': set(),
                'response_times': deque(maxlen=500),
                'requests_by_endpoint': defaultdict(int),
                'errors_by_endpoint': defaultdict(int),
                'status_codes': defaultdict(int),
                'throughput_minute': 0,
                'throughput_history': deque(maxlen=60),
                'last_minute_requests': deque(maxlen=300),
                'user_sessions': set(),
                'request_sizes': deque(maxlen=200),
                'response_sizes': deque(maxlen=200),
            }
            self.data_buffer.clear()
        print("[MONITORING] 监控数据已重置")

    def disable(self):
        """禁用监控"""
        self.enabled = False
        print("[MONITORING] 监控已禁用")

    def enable(self):
        """启用监控"""
        self.enabled = True
        print("[MONITORING] 监控已启用")


# 全局监控实例
monitor = EnhancedPerformanceMonitor()