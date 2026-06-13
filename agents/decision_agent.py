import os
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
import requests

from .fundamental_agent import FundamentalReport
from .technical_agent import TechnicalReport
from config import GROQ_MODEL, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ── LLM provider failover chain ────────────────────────────────────────────────
# Tried in order; any 429 / quota error moves to the next provider automatically.
# Groq and Cerebras are fastest (wafer-scale / dedicated silicon).
# Gemini is the reliable paid fallback.
# OpenRouter is last-resort (routing layer, 100+ models, always available).
LLM_FAILOVER_CHAIN = ["cerebras", "groq", "gemini", "openrouter"]

CEREBRAS_MODEL   = "gpt-oss-120b"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

# ── System prompt: forces explicit bull/bear debate before every decision ──────
SYSTEM_PROMPT = """You are a professional trading decision engine. Before every decision you MUST argue both sides of the trade using actual numbers from the data provided.

MANDATORY PROCESS:
1. BULL CASE — State the 3 strongest data-backed reasons to BUY right now. Cite specific numbers (RSI value, P/E, EPS growth %, analyst target vs current price, insider buys, etc.).
2. BEAR CASE — State the 3 strongest data-backed reasons NOT to buy (or to SELL). Cite specific numbers (overbought RSI, high debt/equity, negative earnings surprise, insider selling, bearish MACD, etc.).
3. VERDICT — Weigh both sides. Only BUY/SELL when one side clearly dominates with multiple confirming signals.

CONFIDENCE CALIBRATION:
- 90-100: Overwhelming evidence, all major signals aligned one way
- 80-89:  Strong case, most signals aligned, minor risks only
- 75-79:  Moderate case, enough to act but meaningful uncertainty
- 60-74:  Mixed signals — output HOLD
- 0-59:   Insufficient evidence — output HOLD
- BEAR market regime: raise bar by 5 points for any BUY decision
- Negative news headlines: weight bear case more heavily
- Insider SELLING: strong bear signal; insider BUYING: moderate bull signal

Respond ONLY with valid JSON. No markdown, no explanation outside the JSON.

JSON schema (use exactly these keys):
{
  "symbol": "<ticker>",
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": <0-100 integer>,
  "quantity_suggestion": <positive integer>,
  "bull_case": ["<specific factor with data point>", "<factor2>", "<factor3>"],
  "bear_case": ["<specific factor with data point>", "<factor2>", "<factor3>"],
  "rationale": "<2-3 sentences: which side won the debate and the single most decisive factor>",
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
    provider_used: Optional[str] = None


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


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if this exception looks like a quota / rate-limit error."""
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "rate limit", "quota", "resource_exhausted", "too many requests"))


def _call_openai_compat(base_url: str, api_key: str, model: str, prompt: str,
                        extra_headers: dict = None, max_tokens: int = 800) -> str:
    """Generic caller for any OpenAI-compatible endpoint (Groq, Cerebras, OpenRouter)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    r = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    return _call_openai_compat(
        "https://api.groq.com/openai/v1", api_key, GROQ_MODEL, prompt
    )


def _call_cerebras(prompt: str) -> str:
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        raise RuntimeError("CEREBRAS_API_KEY not set")
    from cerebras.cloud.sdk import Cerebras
    client = Cerebras(api_key=api_key)
    # gpt-oss-120b is a reasoning model — max_completion_tokens covers reasoning + output
    completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        model=CEREBRAS_MODEL,
        max_completion_tokens=4096,
        temperature=0.2,
        top_p=1,
        stream=False,
    )
    return completion.choices[0].message.content


def _call_openrouter(prompt: str) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return _call_openai_compat(
        "https://openrouter.ai/api/v1", api_key, OPENROUTER_MODEL, prompt,
        extra_headers={"HTTP-Referer": "https://github.com/trading-bot", "X-Title": "TradingBot"},
    )


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


_PROVIDER_CALLERS = {
    "groq":       _call_groq,
    "cerebras":   _call_cerebras,
    "gemini":     _call_gemini,
    "openrouter": _call_openrouter,
}


class DecisionAgent:
    def _call_llm_with_failover(self, prompt: str) -> tuple[str, str]:
        """Try each provider in LLM_FAILOVER_CHAIN. Returns (response_text, provider_name).
        Moves to the next provider on rate-limit errors; re-raises other errors immediately."""
        last_err = None
        for provider in LLM_FAILOVER_CHAIN:
            caller = _PROVIDER_CALLERS.get(provider)
            if caller is None:
                continue
            try:
                result = caller(prompt)
                if provider != LLM_FAILOVER_CHAIN[0]:
                    logger.info(f"[LLM] Used fallback provider: {provider}")
                return result, provider
            except Exception as e:
                if _is_rate_limit_error(e):
                    logger.warning(f"[LLM] {provider} rate-limited, trying next provider... ({e})")
                    last_err = e
                    continue
                raise   # non-429 errors (bad key, network, parse) bubble up immediately
        raise RuntimeError(f"All LLM providers exhausted. Last error: {last_err}")

    def decide(
        self,
        fundamental: FundamentalReport,
        technical: TechnicalReport,
        available_cash: float,
        current_qty: int,
        avg_entry_price: float,
        open_position_count: int,
        macro_context: str = "",
    ) -> TradingDecision:
        symbol = fundamental.symbol

        portfolio_ctx = (
            f"PORTFOLIO CONTEXT:\n"
            f"  Available Cash:  ${available_cash:.2f}\n"
            f"  Current Holding: {current_qty} shares of {symbol}"
            + (f" @ avg ${avg_entry_price:.2f}" if avg_entry_price > 0 else "") + "\n"
            f"  Open Positions:  {open_position_count} / 5\n"
        )

        parts = []
        if macro_context:
            parts.append(macro_context)
        parts.append(portfolio_ctx)
        parts.append(fundamental.to_prompt_text())
        parts.append(technical.to_prompt_text())
        parts.append(
            "Now run your bull/bear debate for this symbol, then output your trading decision as JSON."
        )
        prompt = "\n\n".join(parts)

        try:
            raw, provider = self._call_llm_with_failover(prompt)
            data = _parse_llm_response(raw)

            bull = data.get("bull_case") or data.get("key_bull_factors", [])
            bear = data.get("bear_case") or data.get("key_bear_factors", [])

            return TradingDecision(
                symbol=symbol,
                action=str(data.get("action", "HOLD")).upper(),
                confidence=int(data.get("confidence", 0)),
                quantity_suggestion=max(1, int(data.get("quantity_suggestion", 1))),
                rationale=str(data.get("rationale", "")),
                key_bull_factors=bull,
                key_bear_factors=bear,
                time_horizon=str(data.get("time_horizon", "hold")),
                provider_used=provider,
            )
        except Exception as e:
            logger.warning(f"[{symbol}] DecisionAgent error: {e}")
            return TradingDecision(symbol=symbol, action="HOLD", confidence=0, parse_error=str(e))
