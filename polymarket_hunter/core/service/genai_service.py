import asyncio
import json
import re
from typing import Optional, Any

import pandas as pd
from google import genai
from google.genai import types

from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.datamodel.market_analysis import MarketAnalysis
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class GenAIService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"

    def _build_market_context(self, market: dict) -> dict:
        outcomes = json.loads(market.get("outcomes", "[]"))
        outcome_prices = json.loads(market.get("outcomePrices", "[]"))

        prices_map = {}
        if len(outcomes) == len(outcome_prices):
            prices_map = dict(zip(outcomes, [float(p) for p in outcome_prices]))

        return {
            "slug": market.get("slug"),
            "question": market.get("question"),
            "resolution_source": market.get("resolutionSource"),
            "rules": market.get("description"),
            "start_date": market.get("startDate"),
            "end_date": market.get("endDate"),
            "outcomes": outcomes,
            "prices": {
                "liquidity": float(market.get("liquidity") or 0.0),
                "spread": float(market.get("spread") or 0.0),
                "outcome_prices": prices_map,
                "one_hour_price_change": float(market.get("oneHourPriceChange") or 0.0),
                "one_day_price_change": float(market.get("oneDayPriceChange") or 0.0)
            },
            "_meta": {
                "condition_id": market.get("conditionId"),
                "tokens": dict(zip(outcomes, json.loads(market["clobTokenIds"])))
            }
        }

    async def analyze_market(self, market: dict[str, Any]) -> Optional[MarketAnalysis]:
        context = self._build_market_context(market)
        slug = context.get("slug", "unknown")

        if context.get("prices", {}).get("liquidity", 0) < 1_000:
            logger.warning(f"Skipping {slug}: Liquidity too low")
            return None

        outcomes_list = context.get("outcomes", [])
        if not outcomes_list:
            logger.warning(f"Skipping {slug}: No outcomes found")
            return None

        prompt = self._build_prompt(context, outcomes_list)
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1
                )
            )

            raw_text = response.text
            json_str = self._extract_json(raw_text)
            analysis = MarketAnalysis.model_validate_json(json_str)

            if analysis.target_outcome not in outcomes_list:
                logger.warning(f"LLM hallucinated outcome '{analysis.target_outcome}' for market {slug}. Valid: {outcomes_list}")
                return None

            analysis.slug = slug
            analysis.question = context["question"]
            return analysis

        except Exception as e:
            logger.error(f"❌ GenAI Error on {slug}: {e}")
            return None

    def _build_prompt(self, ctx: dict, outcomes: list[str]) -> str:
        prices = ctx["prices"]
        current_time = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M UTC')
        schema_json = MarketAnalysis.model_json_schema()

        price_display = "\n".join([f"- {name}: {price}" for name, price in prices['outcome_prices'].items()])

        return f"""
        Act as a lean, high-frequency Prediction Market Analyst.
        Your goal is to estimate the **True Probability** that the resolution criteria will be met by the deadline, based on current news and public sentiment.

        ### 1. THE CONTRACT
        **Current Time:** {current_time}
        **Market Question:** {ctx['question']}
        **Resolution Rules:** {ctx['rules']} (These are the strict "goalposts" for the event)
        **Resolution Source:** {ctx['resolution_source']}
        **Deadline:** {ctx['end_date']}
        **Valid Outcomes:** {outcomes}

        ### 2. MARKET DATA
        - **Liquidity:** ${prices['liquidity']}
        - **Spread:** {prices['spread']}
        - **Current Prices (Implied Probability):**
        {price_display}

        ### 2. INSTRUCTIONS
        1. **SEARCH**: Find definitive news regarding the event.
        2. **DERIVE PROBABILITIES**: 
           - Assign a "True Probability" (0.0 to 1.0) to **EACH** item in the **Valid Outcomes** list.
           - Ensure probabilities sum to ~1.0.
        3. **SELECT TARGET**: 
           - Filter for outcomes where your **Estimated Probability > 0.50** (Only look at the "Favorite" to win).
           - Among the Favorites, calculate: `Edge = (Your Prob) - (Current Price)`.
        4. **TRADE DECISION**: 
           - **BUY** ONLY if:
             1. Your `estimated_probability` > 0.50  (High Win Rate)
             2. AND `Edge` > 0.05 (Positive Value)
           - Otherwise, return **NO_ACTION**.

        ### 3. OUTPUT REQUIREMENTS (STRICT)
        ONLY Return valid JSON matching this schema: {json.dumps(schema_json)}

        **Constraints:**
        - `target_outcome`: The specific string from {outcomes} you are analyzing.
        - `estimated_probability`: The probability (0.0-1.0) for that `target_outcome`.
        - `recommended_action`: 'BUY' only if criteria in Step 4 are met. Else 'NO_ACTION'.
        - `reasoning`: Max 2 sentences. Focus on why the Favorite is safe AND undervalued.
        """

    def _extract_json(self, text: str) -> str:
        if not text: return "{}"
        start_idx = text.find("{")
        end_idx = text.rfind("}")

        if start_idx != -1 and end_idx != -1:
            text = text[start_idx: end_idx + 1]

        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        return text.strip()

if __name__ == "__main__":
    async def just():
        gamma = get_gamma_client()
        market = await gamma.get_market_by_slug("maduro-out-in-2025-411")
        genai_service = GenAIService()
        response = await genai_service.analyze_market(market)
        print(response)

    asyncio.run(just())