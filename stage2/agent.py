"""Natural-language research planner with deterministic tools and render authority."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from stage2.io import write_jsonl
from stage2.paths import GOAL_LOGS, ensure_data_dirs
from stage2.retrieval import (
    ALLOWED_FILTERS,
    RetrievalQuery,
    authorized_records,
    compare_lmm_healthcare_lp_fit,
    decompose_natural_language,
    retrieve,
)

GOAL_2 = "Identify the family offices in the dataset that are the best fit for a lower-middle-market healthcare services fund seeking limited partners, and tell me how confident you are in each."
ALLOWED_TOOLS = {"search_records", "compare_lmm_healthcare_lp_fit"}
SYSTEM_PROMPT = """You are a research planner, not a fact generator. Convert the buyer's goal into two to six calls to the supplied deterministic tools. Never answer the goal yourself. Never invent a filter. Use compare_lmm_healthcare_lp_fit for any goal about lower-middle-market healthcare LP fit. Return JSON only with this shape: {"decision":"execute"|"refuse","reason":"...","tool_calls":[{"tool":"search_records"|"compare_lmm_healthcare_lp_fit","arguments":{...}}]}. search_records arguments may contain filters, terms, limit, offset, aggregate. Allowed filters: firm_name, country, firm_type, role_class, route_type, has_email, intelligence_kind, intelligence_term, source_class, trust_state. Allowed aggregates: records, firms, source_mix, route_mix, countries. Use multiple calls for compound comparison or aggregate questions."""


def _at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "search_records",
            "description": "Hard-filter, lexical search, count, or aggregate over policy-authorized production records.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filters": {"type": "object", "additionalProperties": True},
                    "terms": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    "offset": {"type": "integer", "minimum": 0},
                    "aggregate": {"enum": ["records", "firms", "source_mix", "route_mix", "countries"]},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "compare_lmm_healthcare_lp_fit",
            "description": "Compare firms for the exact healthcare-services LP goal using supported mandate signals and explicit abstentions.",
            "input_schema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
        },
    ]


def _validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("decision") not in {"execute", "refuse"}:
        raise ValueError("planner returned no supported decision")
    calls = plan.get("tool_calls", [])
    if not isinstance(calls, list) or len(calls) > 6:
        raise ValueError("planner returned an invalid number of tool calls")
    validated = []
    for call in calls:
        if not isinstance(call, dict) or set(call) - {"tool", "arguments"}:
            raise ValueError("planner returned malformed tool-call fields")
        if call.get("tool") not in ALLOWED_TOOLS:
            raise ValueError("planner requested a non-authorized tool")
        arguments = call.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if call["tool"] == "search_records":
            if set(arguments) - {"filters", "terms", "limit", "offset", "aggregate"}:
                raise ValueError("planner requested non-authorized search arguments")
            filters = arguments.get("filters", {})
            if not isinstance(filters, dict) or set(filters) - ALLOWED_FILTERS:
                raise ValueError("planner requested a non-authorized filter")
            if any(isinstance(value, (dict, list)) for value in filters.values()):
                raise ValueError("filter values must be scalar")
            terms = arguments.get("terms", [])
            if not isinstance(terms, list) or len(terms) > 20 or not all(isinstance(term, str) for term in terms):
                raise ValueError("search terms must be a list of at most 20 strings")
            query = RetrievalQuery(
                filters=filters,
                terms=tuple(terms),
                limit=int(arguments.get("limit", 50)),
                offset=int(arguments.get("offset", 0)),
                aggregate=str(arguments.get("aggregate", "records")),
            )
            query.validate()
            arguments = {
                "filters": query.filters, "terms": list(query.terms), "limit": query.limit,
                "offset": query.offset, "aggregate": query.aggregate,
            }
        else:
            if set(arguments) - {"limit"}:
                raise ValueError("planner requested non-authorized comparison arguments")
            arguments = {"limit": min(100, max(1, int(arguments.get("limit", 20))))}
        validated.append({"tool": call["tool"], "arguments": arguments})
    if plan["decision"] == "execute" and not validated:
        raise ValueError("execute decision had no tool calls")
    if plan["decision"] == "refuse" and validated:
        raise ValueError("refuse decision cannot contain tool calls")
    return {"decision": plan["decision"], "reason": str(plan.get("reason", "")), "tool_calls": validated}


def _fallback_plan(goal: str) -> dict[str, Any]:
    if "lower-middle-market healthcare services fund seeking limited partners" in goal.casefold():
        return {
            "decision": "execute",
            "reason": "The fixed Goal-2 comparator matches this request.",
            "tool_calls": [
                {"tool": "compare_lmm_healthcare_lp_fit", "arguments": {"limit": 20}},
                {"tool": "search_records", "arguments": {
                    "filters": {"has_email": True}, "terms": ["healthcare"],
                    "limit": 100, "offset": 0, "aggregate": "firms",
                }},
            ],
        }
    calls = []
    for query in decompose_natural_language(goal):
        calls.append({"tool": "search_records", "arguments": {
            "filters": query.filters, "terms": list(query.terms), "limit": query.limit,
            "offset": query.offset, "aggregate": query.aggregate,
        }})
    return {"decision": "execute", "reason": "Deterministic parser decomposed the request.", "tool_calls": calls[:6]}


def _model_plan(goal: str, trace: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("Groq client dependency is unavailable") from exc
    models = [os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), "llama-3.1-8b-instant"]
    client = Groq(api_key=key)
    last_error: Exception | None = None
    for attempt, model in enumerate(dict.fromkeys(models), 1):
        started = time.monotonic()
        trace.append({
            "at": _at(), "event": "model.request", "attempt": attempt, "model": model,
            "system_prompt": SYSTEM_PROMPT, "user_goal": goal, "tool_schemas": tool_schemas(),
        })
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": goal}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            usage = getattr(response, "usage", None)
            usage_dict = usage.model_dump() if usage and hasattr(usage, "model_dump") else {}
            metadata = {
                "model": model,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "usage": usage_dict,
                "external_cost_usd": 0.0,
                "cost_basis": "Groq key configured on a free-tier deployment; no billable cost reported by provider response.",
            }
            trace.append({
                "at": _at(), "event": "model.response", "attempt": attempt,
                "raw_content": content, **metadata,
            })
            return _validate_plan(json.loads(content)), metadata
        except Exception as exc:
            last_error = exc
            trace.append({
                "at": _at(), "event": "model.retry_or_failure", "attempt": attempt,
                "model": model, "error_type": type(exc).__name__, "error": str(exc),
            })
    raise RuntimeError(f"all planner model attempts failed: {last_error}") from last_error


def _execute(call: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    if call["tool"] == "compare_lmm_healthcare_lp_fit":
        return compare_lmm_healthcare_lp_fit(records, limit=call["arguments"]["limit"])
    arguments = call["arguments"]
    return retrieve(RetrievalQuery(
        filters=arguments["filters"], terms=tuple(arguments["terms"]),
        limit=arguments["limit"], offset=arguments["offset"], aggregate=arguments["aggregate"],
    ), records)


def _authorize_output(goal: str, tool_results: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> dict[str, Any]:
    authorized_ids = {record["record_id"] for record in corpus}
    cited_ids: set[str] = set()
    for item in tool_results:
        try:
            replayed = _execute(
                {"tool": item["tool"], "arguments": item["arguments"]}, corpus,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return {
                "passed": False, "decision": "refuse",
                "reason": f"Output could not be replayed through an authorized tool: {type(exc).__name__}.",
            }
        if replayed != item.get("result"):
            return {
                "passed": False, "decision": "refuse",
                "reason": "Output differed from deterministic tool replay, so its claims were withheld.",
            }
        result = item["result"]
        cited_ids.update(record["record_id"] for record in result.get("records", []))
        for comparison in result.get("results", []):
            cited_ids.update(comparison.get("supporting_records", []))
            contact_id = comparison.get("recommended_contact", {}).get("record_id")
            if contact_id:
                cited_ids.add(contact_id)
    unauthorized = sorted(cited_ids - authorized_ids)
    if unauthorized:
        return {
            "passed": False, "decision": "refuse", "reason": "Output cited a record outside the policy-authorized release.",
            "unauthorized_record_ids": unauthorized,
        }
    comparisons = [
        item["result"] for item in tool_results
        if item["tool"] == "compare_lmm_healthcare_lp_fit"
    ]
    unsupported_comparison = comparisons and not any(result.get("results") for result in comparisons)
    has_aggregate = any(item["result"].get("aggregate") is not None for item in tool_results)
    return {
        "passed": True,
        "decision": "abstain" if unsupported_comparison else ("render" if cited_ids or has_aggregate else "abstain"),
        "reason": (
            "The comparison found no supported candidate, so the commercial recommendation was withheld."
            if unsupported_comparison else
            "All rendered records and aggregates came directly from deterministic tools over the authorized release."
        ),
        "authorized_record_ids": sorted(cited_ids),
        "goal": goal,
    }


def _attach_and_save_trace(
    result: dict[str, Any], trace: list[dict[str, Any]], save_trace: bool,
) -> dict[str, Any]:
    result["trace"] = trace
    if save_trace:
        path = GOAL_LOGS / f"{result['trace_id']}.jsonl"
        write_jsonl(path, trace)
        result["trace_path"] = str(path)
    return result


def run_agent(goal: str, *, use_model: bool = True, save_trace: bool = True) -> dict[str, Any]:
    ensure_data_dirs()
    goal = " ".join(goal.split()).strip()
    trace_id = f"TRACE_{uuid.uuid4().hex[:16].upper()}"
    trace: list[dict[str, Any]] = [{"at": _at(), "event": "goal.received", "trace_id": trace_id, "goal": goal}]
    if not goal or len(goal) > 5000:
        reason = "A research goal is required." if not goal else "The research goal exceeds the 5,000-character planning limit."
        result = {
            "trace_id": trace_id, "goal": goal, "status": "refused",
            "reason": reason, "planner_mode": "none", "model_metadata": {},
            "plan": {"decision": "refuse", "reason": reason, "tool_calls": []},
            "tool_results": [],
            "render_authority": {"passed": True, "decision": "abstain", "reason": reason},
            "customer_explanation": reason, "limitations": [reason],
        }
        trace.append({"at": _at(), "event": "goal.refused", "reason": reason})
        return _attach_and_save_trace(result, trace, save_trace)

    planner_mode = "model"
    model_metadata: dict[str, Any] = {}
    try:
        if not use_model:
            raise RuntimeError("model planning disabled by caller")
        plan, model_metadata = _model_plan(goal, trace)
    except RuntimeError as exc:
        planner_mode = "deterministic_fallback"
        trace.append({
            "at": _at(), "event": "planner.fallback", "reason": str(exc),
            "limitation": "The retrieval remains usable, but this run is not evidence of model-selected agent actions.",
        })
        plan = _validate_plan(_fallback_plan(goal))
    trace.append({"at": _at(), "event": "plan.authorized", "planner_mode": planner_mode, "plan": plan})

    corpus = authorized_records()
    tool_results = []
    if plan["decision"] == "refuse":
        trace.append({"at": _at(), "event": "plan.refused", "reason": plan["reason"]})
    else:
        for index, call in enumerate(plan["tool_calls"], 1):
            trace.append({"at": _at(), "event": "tool.call", "index": index, "tool": call["tool"], "arguments": call["arguments"]})
            started = time.monotonic()
            output = _execute(call, corpus)
            tool_results.append({"tool": call["tool"], "arguments": call["arguments"], "result": output})
            trace.append({
                "at": _at(), "event": "tool.result", "index": index, "tool": call["tool"],
                "latency_ms": round((time.monotonic() - started) * 1000), "raw_output": output,
            })

    authority = _authorize_output(goal, tool_results, corpus)
    trace.append({"at": _at(), "event": "render.authority_decision", "authority": authority})
    if plan["decision"] == "refuse":
        status = "refused"
    else:
        status = "ok" if authority["passed"] and authority["decision"] == "render" else "abstained"
    result = {
        "trace_id": trace_id,
        "goal": goal,
        "status": status,
        "planner_mode": planner_mode,
        "model_metadata": model_metadata,
        "plan": plan,
        "tool_results": tool_results,
        "render_authority": authority,
        "customer_explanation": (
            "The system planned retrieval steps, ran them against only release-authorized records, and checked every cited record before display."
        ),
        "limitations": (
            [] if planner_mode == "model" else ["Model planning was unavailable; deterministic decomposition was used instead."]
        ),
    }
    trace.append({"at": _at(), "event": "goal.completed", "status": status})
    return _attach_and_save_trace(result, trace, save_trace)
