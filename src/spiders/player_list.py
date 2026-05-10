import requests
from typing import List, Dict, Any
from src.config import BASE_URL
from src.utils.logger import setup_logger

logger = setup_logger()


class PlayerListSpider:
    """选手列表爬虫 - 使用API"""

    API_URL = "https://emdcspzhapi.dfcfs.cn/rtV1"

    # 榜单类型 (根据Playwright跟踪网站API调用结果修正)
    RANK_TYPES = {
        "10004": "总榜",   # 总收益
        "10003": "年榜",   # 250日收益
        "10001": "月榜",   # 20日收益
        "10000": "周榜",   # 5日收益
        "10005": "日榜",   # 日收益
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": BASE_URL,
        })

    def fetch_rank_players(self, rank_type: str, max_count: int = 200) -> List[Dict[str, Any]]:
        """获取单个榜单的选手"""
        players = []
        offset = 0
        page_size = 20

        while offset < max_count:
            request_size = min(page_size, max_count - offset)

            params = {
                "type": "rt_get_rank",
                "rankType": rank_type,
                "recIdx": offset,
                "recCnt": request_size,
                "rankid": 0,
                "appVer": "9001000",
            }

            try:
                response = self.session.get(self.API_URL, params=params, timeout=30)
                data = response.json()

                if data.get("result") != "0" or not data.get("data"):
                    break

                batch = data.get("data", [])
                if not batch:
                    break

                for p in batch:
                    players.append({
                        "zh_id": p.get("zjzh", ""),
                        "name": p.get("zhuheName", ""),
                        "user_id": p.get("userid", ""),
                        "followers": int(p.get("concernCnt", 0)),
                        "labels": [l for l in [p.get("label1", ""), p.get("label2", ""), p.get("label3", "")] if l],
                        "daily_return": float(p.get("rateForApp", 0)),
                    })

                if len(batch) < request_size:
                    break

                offset += len(batch)

            except Exception as e:
                logger.error(f"获取榜单 {rank_type} 失败: {e}")
                break

        return players[:max_count]

    def fetch_all_ranks(self, max_per_rank: int = 200) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有榜单的选手"""
        all_ranks = {}

        for rank_type, rank_name in self.RANK_TYPES.items():
            logger.info(f"获取{rank_name} (前{max_per_rank}名)...")
            players = self.fetch_rank_players(rank_type, max_per_rank)
            all_ranks[rank_name] = players
            logger.info(f"  {rank_name}: {len(players)} 名选手")

        return all_ranks

    def fetch_player_list(self, max_per_rank: int = 200) -> List[Dict[str, Any]]:
        """获取所有榜单的选手列表（合并去重）"""
        logger.info(f"开始获取选手列表 (每个榜单前{max_per_rank}名)")

        all_ranks = self.fetch_all_ranks(max_per_rank)

        # 使用 dict 进行 O(1) 去重
        player_map: Dict[str, Dict[str, Any]] = {}
        for rank_name, players in all_ranks.items():
            for p in players:
                zh_id = p.get("zh_id")
                if not zh_id:
                    continue
                if zh_id not in player_map:
                    p["ranks"] = [rank_name]
                    player_map[zh_id] = p
                else:
                    existing_ranks = player_map[zh_id].get("ranks", [])
                    if rank_name not in existing_ranks:
                        existing_ranks.append(rank_name)

        logger.info(f"去重后共 {len(player_map)} 个选手")
        return list(player_map.values())


def crawl_player_list(max_per_rank: int = 200) -> List[Dict[str, Any]]:
    """爬取选手列表"""
    spider = PlayerListSpider()
    return spider.fetch_player_list(max_per_rank)


if __name__ == "__main__":
    players = crawl_player_list(max_per_rank=200)
    print(f"\n共获取 {len(players)} 个选手")
