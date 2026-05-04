from tools import pull_meta_ads_data


class DataFetcherAgent:
    def run(self, days: int = 7) -> str:
        print("  [Data Fetcher] Pulling Meta Ads data...")
        result = pull_meta_ads_data.invoke({"days": days})
        campaigns = result.count("Campaign:")
        print(f"  [Data Fetcher] Done — {campaigns} campaign(s) found")
        return result
