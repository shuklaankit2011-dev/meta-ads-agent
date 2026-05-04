from tools import write_performance_report


class ReportingAgent:
    def run(self, analysis: str) -> str:
        print("  [Reporter] Formatting final report...")
        result = write_performance_report.invoke({"analysis": analysis})
        print("  [Reporter] Done")
        return result
