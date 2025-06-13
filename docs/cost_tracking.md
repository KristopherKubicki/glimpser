# LLM Cost Tracking

Glimpser now records the number of tokens used when generating captions.
Token counts are stored in `data/llm_usage.json` keyed by template name.
Costs are calculated at `$0.005` per thousand tokens.
Use the captions page to view each template's estimated cost.
An overall cost summary now appears under **Settings → Costs**. This tab now
includes a small pie chart and sortable columns. Use the **Days** slider to
select how far back to look when reviewing recent spending. A group dropdown
allows filtering the results.

The Settings cost tab shows the most expensive templates and groups the rest
into a single **Other** row. Use the **Top** slider to adjust how many
individual templates appear before grouping occurs. The table now shows the
number of LLM calls for each template.

An additional **LLM Cost Summary** page now provides a slider-based range
selection to review costs for a specific period. Use the **Since Last Restart**
shortcut to fill the slider with the time since the server started. A pie chart
shows how costs are
distributed across templates. When more than 15 templates are present, the chart
automatically groups the least expensive templates into a single **Other** slice
to remain legible.

## LLM Response Cache

Glimpser caches LLM responses in `data/llm_cache.json` keyed by a hash of the
prompt and image filenames. When an identical request is made later, the cached
result is returned instead of calling the API again. Cached entries also store
the number of tokens so repeated calls will not incur additional cost.
