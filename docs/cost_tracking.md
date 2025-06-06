# LLM Cost Tracking

Glimpser now records the number of tokens used when generating captions.
Token counts are stored in `data/llm_usage.json` keyed by template name.
Costs are calculated at `$0.005` per thousand tokens.
Use the captions page to view each template's estimated cost.

An additional **LLM Cost Summary** page now provides a date range picker to
review costs for a specific period. Open the page from the navigation bar and
select your desired start and end dates.

## LLM Response Cache

Glimpser caches LLM responses in `data/llm_cache.json` keyed by a hash of the
prompt and image filenames. When an identical request is made later, the cached
result is returned instead of calling the API again. Cached entries also store
the number of tokens so repeated calls will not incur additional cost.
