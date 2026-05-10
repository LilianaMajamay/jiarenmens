"""
代理池模块
支持：
- 从文件加载代理
- 代理可用性验证
- 自动轮换
- 失败重试
"""
import os
import json
import time
import random
import requests
from typing import Optional, List, Dict
from pathlib import Path
from src.utils.logger import setup_logger

logger = setup_logger()


class Proxy:
    """代理"""

    def __init__(self, http: str, https: str = None, username: str = None, password: str = None):
        self.http = http
        self.https = https or http
        self.username = username
        self.password = password
        self.failed_count = 0  # 失败次数
        self.success_count = 0  # 成功次数
        self.last_check = 0  # 上次检查时间

    def to_dict(self) -> Dict:
        return {
            'http': self.http,
            'https': self.https,
            'username': self.username,
            'password': self.password
        }

    def to_proxy_dict(self) -> Dict:
        """转换为 requests/ playwright 需要的格式"""
        if self.username and self.password:
            return {
                'http': f'http://{self.username}:{self.password}@{self.http.split("://")[1]}',
                'https': f'http://{self.username}:{self.password}@{self.https.split("://")[1]}'
            }
        return {'http': self.http, 'https': self.https}

    def __repr__(self):
        return f"Proxy({self.http}, fail={self.failed_count}, success={self.success_count})"


class ProxyPool:
    """代理池"""

    def __init__(self, proxy_file: str = None):
        self.proxies: List[Proxy] = []
        self.working_proxies: List[Proxy] = []
        self.failed_proxies: List[Proxy] = []
        self.current_index = 0

        # 默认代理文件路径
        if proxy_file is None:
            proxy_file = os.path.join(os.path.dirname(__file__), '..', '..', 'proxies.txt')

        self.proxy_file = proxy_file
        self._load_from_file()

    def _parse_proxy(self, line: str) -> Optional[Proxy]:
        """解析代理行"""
        line = line.strip()
        if not line or line.startswith('#'):
            return None

        # 格式: http://host:port 或 http://user:pass@host:port
        http = line if line.startswith('http') else f'http://{line}'

        username, password = None, None
        if '@' in http:
            # 提取用户名密码
            auth, host = http.split('@')
            protocol = auth.split('://')[0] + '://'
            if '://' in auth:
                auth = auth.split('://')[1]
            username, password = auth.split(':')
            http = f'{protocol}{host}'

        return Proxy(http, username=username, password=password)

    def _load_from_file(self):
        """从文件加载代理"""
        if not os.path.exists(self.proxy_file):
            logger.warning(f"代理文件不存在: {self.proxy_file}")
            return

        with open(self.proxy_file, 'r', encoding='utf-8') as f:
            for line in f:
                proxy = self._parse_proxy(line)
                if proxy:
                    self.proxies.append(proxy)

        logger.info(f"从文件加载了 {len(self.proxies)} 个代理: {self.proxy_file}")
        self.working_proxies = self.proxies.copy()

    def add(self, proxy_str: str):
        """添加代理"""
        proxy = self._parse_proxy(proxy_str)
        if proxy:
            self.proxies.append(proxy)
            self.working_proxies.append(proxy)
            logger.info(f"添加代理: {proxy.http}")

    def remove(self, proxy_str: str):
        """移除代理"""
        for p in self.proxies:
            if p.http == proxy_str:
                self.proxies.remove(p)
                if p in self.working_proxies:
                    self.working_proxies.remove(p)
                logger.info(f"移除代理: {proxy_str}")
                break

    def get(self) -> Optional[Proxy]:
        """获取一个可用代理（随机）"""
        if not self.working_proxies:
            # 如果没有可用的，尝试恢复失败的
            if self.failed_proxies:
                logger.info(f"恢复 {len(self.failed_proxies)} 个失败代理")
                self.working_proxies = self.failed_proxies.copy()
                self.failed_proxies.clear()
            else:
                return None
        return random.choice(self.working_proxies)

    def get_next(self) -> Optional[Proxy]:
        """获取下一个代理（轮换）"""
        if not self.working_proxies:
            if self.failed_proxies:
                self.working_proxies = self.failed_proxies.copy()
                self.failed_proxies.clear()
            else:
                return None

        proxy = self.working_proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.working_proxies)
        return proxy

    def mark_success(self, proxy: Proxy):
        """标记代理成功"""
        proxy.success_count += 1
        proxy.failed_count = 0
        if proxy not in self.working_proxies:
            self.working_proxies.append(proxy)
            if proxy in self.failed_proxies:
                self.failed_proxies.remove(proxy)
        logger.debug(f"代理成功: {proxy.http}")

    def mark_failed(self, proxy: Proxy):
        """标记代理失败"""
        proxy.failed_count += 1
        if proxy.failed_count >= 3:
            if proxy in self.working_proxies:
                self.working_proxies.remove(proxy)
                self.failed_proxies.append(proxy)
            logger.warning(f"代理失败过多已移除: {proxy.http}")
        else:
            logger.debug(f"代理失败: {proxy.http}, 失败次数: {proxy.failed_count}")

    def check_proxy(self, proxy: Proxy, test_url: str = 'https://www.baidu.com', timeout: int = 10) -> bool:
        """验证代理是否可用"""
        try:
            proxies = proxy.to_proxy_dict()
            response = requests.get(test_url, proxies=proxies, timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    def check_all(self, test_url: str = 'https://www.baidu.com', timeout: int = 5) -> int:
        """验证所有代理（并发），返回可用数量"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        working = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_map = {executor.submit(self.check_proxy, p, test_url, timeout): p for p in self.proxies}
            for future in as_completed(future_map):
                proxy = future_map[future]
                if future.result():
                    working.append(proxy)
                    logger.info(f"代理可用: {proxy.http}")
                else:
                    logger.warning(f"代理不可用: {proxy.http}")

        self.working_proxies = working
        return len(working)

    def save_to_file(self, filename: str = None):
        """保存代理到文件"""
        if filename is None:
            filename = self.proxy_file

        with open(filename, 'w', encoding='utf-8') as f:
            for proxy in self.proxies:
                f.write(f"{proxy.http}\n")

        logger.info(f"保存了 {len(self.proxies)} 个代理到: {filename}")

    def count(self) -> int:
        """代理总数"""
        return len(self.proxies)

    def working_count(self) -> int:
        """可用代理数"""
        return len(self.working_proxies)

    def __len__(self):
        return len(self.proxies)

    def __repr__(self):
        return f"ProxyPool(total={len(self.proxies)}, working={len(self.working_proxies)})"


# 全局代理池
_pool: Optional[ProxyPool] = None


def get_proxy_pool(proxy_file: str = None) -> ProxyPool:
    """获取全局代理池"""
    global _pool
    if _pool is None:
        _pool = ProxyPool(proxy_file)
    return _pool


def add_proxy(proxy_str: str):
    """快速添加代理"""
    get_proxy_pool().add(proxy_str)


def get_proxy() -> Optional[Dict]:
    """快速获取代理（返回字典格式）"""
    pool = get_proxy_pool()
    proxy = pool.get()
    return proxy.to_proxy_dict() if proxy else None


# 代理文件格式说明
PROXY_FILE_FORMAT = """
# proxies.txt 格式
# 每行一个代理，支持以下格式：

# 简单格式
http://127.0.0.1:7890
http://192.168.1.1:8080

# 带认证
http://user:password@127.0.0.1:7890
http://admin:123456@192.168.1.1:8080

# 注意：不支持 https 单独配置，会自动使用 http 的地址
"""


if __name__ == "__main__":
    # 测试
    pool = get_proxy_pool()
    print(f"代理池: {pool}")
    print(f"可用代理: {pool.working_count()}")

    # 测试获取代理
    proxy = pool.get()
    if proxy:
        print(f"获取代理: {proxy.http}")
    else:
        print("没有可用代理，请先在 proxies.txt 中添加代理")
