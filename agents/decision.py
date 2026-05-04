import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage


SYSTEM_PROMPT = """You are a senior performance marketing strategist specialising in Meta Ads for India — D2C, lead gen, and real estate.

You receive a rule-based campaign analysis. Your job:
1. Validate each decision — confirm or sharpen it with one specific reason
2. Spot cross-campaign patterns (budget cannibalisation, audience overlap, frequency risk)
3. Add ONE concrete next action per campaign beyond the default rule (e.g. exact creative angle to test, specific audience segment to try)

Format rules:
- Keep the original decision blocks exactly as received
- After each campaign block, append a [STRATEGY] line with your addition (max 2 sentences)
- End with a [CROSS-CAMPAIGN INSIGHT] section (3 bullet points max)

Do NOT invent metrics. Do NOT change campaign names. Be direct — no filler."""


class DecisionAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    def run(self, analysis: str) -> str:
        print("  [Decision] Adding strategic layer...")
        response = self.llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=analysis),
        ])
        print("  [Decision] Done")
        return response.content
