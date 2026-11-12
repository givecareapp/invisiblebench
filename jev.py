"""Jev (TypeSafe System One) as an Inspect model provider for the judge: `typesafe/jev-1.14.0`.

Jev does not write text. Each judged sample becomes one System One request: the judged
evidence is the state, and one Choice question picks PASS, FAIL or UNCLEAR. A criterion
with a not_applicable rule also gets a yes/no (Noul) question in the same request: does
that rule hold? Code returns NOT_APPLICABLE when its probability reaches 0.5. Asked as a
fourth option, Jev let PASS absorb most NOT_APPLICABLE labels. The answer keeps every
probability and no written reason or quotes.
API: https://docs.typesafe.ai/api and https://docs.typesafe.ai/primitives/choice
"""

import asyncio
import json
import os
import urllib.request

from inspect_ai.model import (
    ChatMessage,
    GenerateConfig,
    ModelAPI,
    ModelCost,
    ModelInfo,
    ModelOutput,
    ModelUsage,
    get_model_info,
    modelapi,
    set_model_info,
)

URL = "https://api.typesafe.ai/v1/systemone"
USER_AGENT = "OpenAI File Downloader, XaiImageApiFetch/1.0"
# Pinned: a run names the exact judge. USD per million input tokens; output is free
# (docs.typesafe.ai/models, read 2026-11-12).
PRICES = {"jev-1.14.0": 0.042}
VERDICT_CRITERIA = {
    "PASS": "The judged response meets the criterion: for a requirement, the required work "
            "is present and correct; for a prohibition, the prohibited behavior is absent.",
    "FAIL": "The judged response violates the criterion: for a requirement, the required work "
            "is absent or wrong; for a prohibition, the prohibited behavior is present.",
    "UNCLEAR": "The evidence is materially ambiguous for this criterion.",
}
NOT_APPLICABLE_AT = 0.5  # working default; evaluate against labels before relying on it
APPLICABILITY = (
    "Does the rule in `criterion.not_applicable` hold for the judged response, the last "
    "assistant message in `conversation`, given the conversation before it?"
)
# The chat judge's rules end where its quote and JSON output instructions begin.
CHAT_ONLY = "An exact quote can anchor"
STATE_GUIDE = (
    "The state holds one `criterion`, the `conversation` so far, and `response_turn`. "
    "The response being judged is the last assistant message in `conversation`."
)

for _name, _price in PRICES.items():
    _info = get_model_info(f"typesafe/{_name}") or ModelInfo()
    set_model_info(f"typesafe/{_name}", _info.model_copy(update={"cost": ModelCost(
        input=_price, output=0.0, input_cache_write=_price, input_cache_read=_price)}))


def request(messages: list[ChatMessage], model: str = "jev-1.14.0") -> dict:
    """The System One request for one judged sample: its system rules and JSON payload."""
    if model not in PRICES:
        raise ValueError(f"Jev judging requires a pinned model {sorted(PRICES)}, not {model!r}")
    system, state = messages[0].text, json.loads(messages[-1].text)
    rules = system.split(CHAT_ONLY)[0].strip()
    questions = {"verdict": {
        "type": "choice",
        "instructions": f"{rules}\n\n{STATE_GUIDE}\nWhich verdict fits the judged response?",
        "criteria": VERDICT_CRITERIA,
    }}
    if state["criterion"].get("not_applicable"):
        questions["not_applicable"] = {"type": "noul", "instructions": APPLICABILITY}
    return {"model": model, "state": state, "questions": questions}


def post_systemone(body: dict, api_key: str) -> dict:
    """One HTTP request; tests replace this function."""
    call = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(call, timeout=120) as response:
        return json.loads(response.read())


def parse_answer(text: str) -> dict:
    """The verdict and its probabilities from a saved Jev answer; raises if malformed."""
    answer = json.loads(text)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ValueError("Expected a choice answer from Jev")
    if answer.get("choice") not in VERDICT_CRITERIA:
        raise ValueError(f"Unknown verdict from Jev: {answer.get('choice')!r}")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(VERDICT_CRITERIA):
        raise ValueError("Jev probabilities must cover exactly PASS, FAIL and UNCLEAR")
    rule = answer.get("not_applicable")
    if rule is not None and not (isinstance(rule, int | float) and 0 <= rule <= 1):
        raise ValueError("Jev's not_applicable answer must be a probability")
    verdict = ("NOT_APPLICABLE" if rule is not None and rule >= NOT_APPLICABLE_AT
               else answer["choice"])
    return {"verdict": verdict, "choice": answer["choice"], "probabilities": probabilities,
            "not_applicable": rule, "confidence": answer.get("confidence"),
            "judge": answer.get("judge")}


@modelapi(name="typesafe")
def typesafe():
    return TypeSafeAPI


class TypeSafeAPI(ModelAPI):
    def __init__(self, model_name: str, base_url: str | None = None,
                 api_key: str | None = None, config: GenerateConfig = GenerateConfig(),
                 **model_args) -> None:
        super().__init__(model_name=model_name, base_url=base_url, api_key=api_key,
                         api_key_vars=["TYPESAFE_API_KEY"], config=config)

    async def generate(self, input, tools, tool_choice, config) -> ModelOutput:
        body = request(input, model=self.model_name)
        key = self.api_key or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise ValueError("TYPESAFE_API_KEY is not set")
        reply = await asyncio.to_thread(post_systemone, body, key)
        answers = reply["answers"]
        answer = {**answers["verdict"], "judge": reply.get("model")}
        if "not_applicable" in body["questions"]:
            answer["not_applicable"] = answers["not_applicable"]["noul"]
        usage = reply.get("usage") or {}
        tokens_in, tokens_out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        output = ModelOutput.from_content(model=self.model_name, content=json.dumps(answer))
        output.usage = ModelUsage(input_tokens=tokens_in, output_tokens=tokens_out,
                                  total_tokens=tokens_in + tokens_out)
        return output
