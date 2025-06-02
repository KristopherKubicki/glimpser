# Log Cleaner

`scripts/clean_logs.py` condenses repeated log lines from a file or standard input.
It outputs unique messages with a prefix indicating how many times each occurred.

```bash
python scripts/clean_logs.py glimpser.log
```

To use with piped input:

```bash
cat glimpser.log | python scripts/clean_logs.py
```

