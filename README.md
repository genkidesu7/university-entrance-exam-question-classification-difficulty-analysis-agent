# EDU-C2-029 — University Entrance Exam Question Classification & Difficulty Analysis Agent

> **Category**: Cat 2 (fixed five-node pipeline with a composed domain-classification sub-workflow)
> **Industry**: EDU

## Overview

This agent takes the text of a university entrance exam paper (for example a full 共通テスト subject
paper delivered as a PDF), splits it into individual questions, and classifies each one in three steps:

1. **Curriculum domain** — a subject domain and sub-domain from the MEXT 学習指導要領 curriculum.
2. **Cognitive level** — a level from Bloom's revised taxonomy (`recall`, `comprehension`,
   `application`, `analysis` or `synthesis`), assigned by an LLM (Azure OpenAI).
3. **Difficulty** — a 1–5 score derived from the domain and the Bloom level.

It returns the per-question classification as JSON, plus a markdown difficulty-distribution report
and a curriculum gap-analysis table.

The intended users are prep-school (予備校) curriculum planners and admissions-prep teachers who
classify multi-year exam archives by hand. Input is PDF text only (maximum 20 MB; executable and
non-PDF content, and PDFs with active content, are rejected). Student-identifying fields are refused
on input and re-checked on output. The agent does not generate new questions, does not assess
individual students, and does not extract diagrams or figures.

**What is real and what is a stand-in.** Only the Bloom-level classification calls a real backend
(Azure OpenAI). The curriculum-domain lookup and the difficulty score come from deterministic sample
data in `src/services/mock_data.py`, because this template ships no curriculum vector database and no
historical pass-rate feed. Replace those two lookups with your own sources (see *Customising*).

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| **Azure OpenAI** | Needed for the Bloom-level classification outside mock mode: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT`, supplied through the platform's secret mechanism. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

Setting `USE_MOCK=true` makes the Bloom-level step return sample data instead of calling Azure
OpenAI, so no LLM credentials are needed. The tests set it themselves.

## Project Structure

```
src/          agent implementation (graph, nodes, services, schemas, HTTP adapter)
tests/        unit, integration and boundary tests
config/       agent manifest (agent.yaml) and runtime parameters (config.yaml)
docs/         design and test specification
cli.py        AGENTIC STAR Marketplace entry point
```

See `docs/02_design.md` and `docs/03_test_spec.md` for the design and the test specification.

## Customising

1. Adjust `config/` for your own environment and policies, for example `max_questions_per_batch`
   (default 100) in `config/config.yaml`.
2. Replace the knowledge sources and sample data with your own: implement `_call_vector_kb` and
   `_call_difficulty_rubric` in `src/services/service.py` against your curriculum knowledge base and
   pass-rate data, and retire the corresponding stubs in `src/services/mock_data.py`.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.

---
