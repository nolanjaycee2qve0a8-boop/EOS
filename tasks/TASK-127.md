# TASK-127 - Explainable MPC CSV File Exporter

## Objective

Persist already serialized explainable MPC CSV text to one caller-owned `.csv`
path without coupling file I/O to row mapping or serialization.

## Contracts

`ExplainableMPCDecisionCSVFileExportInput` retains exact CSV text and a
caller-supplied `pathlib.Path`. The parent directory must exist and the target
must have a `.csv` suffix; target directories are rejected. The result retains
exact input/path identity and actual UTF-8 byte length.

## Semantics

The deterministic exporter writes exactly one complete UTF-8 document, with no
newline translation, and overwrites an existing regular file. It does not
append because TASK-126 produces a complete header-inclusive document. Parent
directory creation remains the caller's responsibility.

```text
Journal Record -> CSV Row -> CSV text -> CSV File Exporter -> .csv file
```

## Responsibility separation

The exporter accepts pre-serialized text only. It neither imports nor invokes
the CSV serializer, and performs no record mapping, explanation rebuilding,
optimization, projection, constraint evaluation, MPC execution, or EventJournal
work.

## Non-goals

No append mode, output-directory creation, file locking, simulation integration,
EventJournal/EventRecord adaptation, database, network, JSON, or runtime work.
