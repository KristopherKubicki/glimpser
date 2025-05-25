# LLM Cost Tracking

Glimpser now records the number of tokens used when generating captions.
Token counts are stored in `data/llm_usage.json` keyed by template name.
Costs are calculated at `$0.005` per thousand tokens.
Use the captions page to view each template's estimated cost.
