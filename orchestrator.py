"""
orchestrator.py — Multi-Agent Pipeline

Orchestrator
├── DataFetcherAgent   pulls live Meta Ads data
├── AnalystAgent       applies SCALE / PAUSE / TEST / WATCH rules
├── DecisionAgent      LLM adds strategic context and cross-campaign patterns
└── ReportingAgent     formats the final report
"""

from dotenv import load_dotenv
load_dotenv()

from agents.data_fetcher import DataFetcherAgent
from agents.analyst import AnalystAgent
from agents.decision import DecisionAgent
from agents.reporter import ReportingAgent


class Orchestrator:
    def __init__(self):
        self.fetcher  = DataFetcherAgent()
        self.analyst  = AnalystAgent()
        self.decision = DecisionAgent()
        self.reporter = ReportingAgent()

    def run(self, days: int = 7) -> tuple:
        """
        Runs the full pipeline. Returns (report_str, raw_campaign_data_str).
        raw_campaign_data is passed to evals for quality checks.
        """
        print("\n" + "━" * 54)
        print("  ORCHESTRATOR — Starting 4-agent pipeline")
        print("━" * 54 + "\n")

        # Stage 1 — Fetch
        raw_data = self.fetcher.run(days=days)
        if raw_data.startswith("ERROR") or raw_data.startswith("META API ERROR"):
            return raw_data, ""

        # Stage 2 — Analyse
        analysis = self.analyst.run(raw_data)

        # Stage 3 — Strategic decisions
        enriched = self.decision.run(analysis)

        # Stage 4 — Report
        report = self.reporter.run(enriched)

        print("\n" + "━" * 54)
        print("  ORCHESTRATOR — Pipeline complete")
        print("━" * 54 + "\n")

        return report, raw_data
