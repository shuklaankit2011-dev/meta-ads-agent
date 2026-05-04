from tools import analyze_campaign_performance


class AnalystAgent:
    def run(self, campaign_data: str) -> str:
        print("  [Analyst] Applying decision rules...")
        result = analyze_campaign_performance.invoke({"campaign_data": campaign_data})
        print("  [Analyst] Done")
        return result
