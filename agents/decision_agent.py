import os
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
import requests

from .fundamental_agent import FundamentalReport
from .technical_agent import TechnicalReport
from config import LLM_PROVIDER, GROQ_MODEL, GEMINI_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional stock trading decision engine. You will receive fundamental and technical analysis reports for a single stock along with current portfolio context. Your job is to output a trading decision.

RULES:
- Respond ONLY with valid JSON, no markdown, no explanation.
- action must be exactly "BUY", "SELL", or "HOLD"
- confidence is an integer 0-100
- quantity_suggestion is the number of shares (integer, minimum 1)
- Be conservative: only recommend BUY/SELL when multiple signals align

JSON schema (use exactly these keys):
{
  "symbol": "<ticker>",
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": <0-100 integer>,
  "quantity_suggestion": <positive integer>,
  "rationale": "<2-3 sentences explaining the decision>",
  "key_bull_factors": ["<factor1>", "<factor2>"],
  "key_bear_factors": ["<factor1>", "<factor2>"],
  "time_horizon": "intraday" | "swing" | "hold"
}"""


@dataclass
class TradingDecision:
    symbol: str
    action: str = "HOLD"
    confidence: int = 0
    quantity_suggestion: int = 1
    rationale: str = ""
    key_bull_factors: list = field(default_factory=list)
    key_bear_factors: list = field(default_factory=list)
    time_horizon: str = "hold"
    parse_error: Optional[str] = None


def _parse_llm_response(raw: str) -> dict:
    cleaned = re.sub(r'```(?:json)?', '', raw).strip().rstrip('`').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No valid JSON in response: {raw[:300]}")


def _call_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 600,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_gemini(prompt: str) -> str:
    from google import genai
    from google.genai import types as genai_types
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")
    client = genai.Client(api_key=api_key)
    config = genai_types.GenerateContentConfig(
        temperature=0.2,
        system_instruction=SYSTEM_PROMPT,
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text


class DecisionAgent:
    def __init__(self):
        self._provider = LLM_PROVIDER.lower()

    def _call_llm(self, prompt: str) -> str:
        if self._provider == "groq":
            return _call_groq(prompt)
        elif self._provider == "gemini":
            return _call_gemini(prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {self._provider}")

    def decide(
        self,
        fundamental: FundamentalReport,
        technical: TechnicalReport,
        available_cash: float,
        current_qty: int,
        avg_entry_price: float,
        open_position_count: int,
    ) -> TradingDecision:
        symbol = fundamental.symbol

        portfolio_ctx = (
            f"PORTFOLIO CONTEXT:\n"
            f"  Available Cash:      ${available_cash:.2f}\n"
            f"  Current Holding:     {current_qty} shares of {symbol}"
            + (f" @ avg ${avg_entry_price:.2f}" if avg_entry_price > 0 else "") + "\n"
            f"  Open Positions:      {open_position_count} / 5\n"
        )

        prompt = (
            portfolio_ctx + "\n"
            + fundamental.to_prompt_text() + "\n\n"
            + technical.to_prompt_text() + "\n\n"
            + "Based on the above, provide your trading decision as JSON."
        )

        try:
            raw = self._call_llm(prompt)
            data = _parse_llm_response(raw)

            return TradingDecision(
                symbol=symbol,
                action=str(data.get("action", "HOLD")).upper(),
                confidence=int(data.get("confidence", 0)),
                quantity_suggestion=max(1, int(data.get("quantity_suggestion", 1))),
                rationale=str(data.get("rationale", "")),
                key_bull_factors=data.get("key_bull_factors", []),
                key_bear_factors=data.get("key_bear_factors", []),
                time_horizon=str(data.get("time_horizon", "hold")),
            )
        except Exception as e:
            logger.warning(f"[{symbol}] DecisionAgent error: {e}")
            return TradingDecision(symbol=symbol, action="HOLD", confidence=0, parse_error=str(e))
