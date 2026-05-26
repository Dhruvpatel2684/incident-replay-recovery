# Log Analysis Task

You are given an application log file at `/app/data/application.log`. Each line follows the format:

```
TIMESTAMP LEVEL MODULE MESSAGE
```

Your task:

1. Read `/app/data/application.log`
2. Parse each line and extract entries where the level is `ERROR`
3. Count the total number of ERROR entries per module
4. Find the module with the highest error count
5. Write the results to `/app/output.json` with the following structure:

```json
{
  "total_errors": <int>,
  "errors_per_module": {
    "<module_name>": <count>,
    ...
  },
  "worst_module": "<module_name_with_most_errors>",
  "first_error_timestamp": "<timestamp_of_first_error>",
  "last_error_timestamp": "<timestamp_of_last_error>"
}
```

The `errors_per_module` object must have module names as keys sorted alphabetically. If two modules tie for most errors, pick the one that comes first alphabetically.
