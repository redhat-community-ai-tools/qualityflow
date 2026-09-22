---
type: regex
target: last_message
flags: i
---
(?=[\s\S]*valid)(?=[\s\S]*(errors|failed|missing))(?=[\s\S]*REQ-ATTACH-02)
