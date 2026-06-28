---
name: link-resolver
description: Build a dependency graph from Jira issue links and identify key dependencies
model: claude-opus-4-6
---

# Link Resolver Skill

**Phase:** Pre-Processing
**User-Invocable:** false

## Purpose

Build a dependency graph from Jira issue links, categorizing relationships and identifying key dependencies.

## When to Use

Invoked by the **jira-collector** subagent after collecting issue links from the main issue.

## Input

```yaml
main_issue_key: PROJ-12345
issue_links:
  - outward_issue:
      key: PROJ-11111
      summary: <summary>
    link_type:
      name: Blocks
      outward: blocks
      inward: is blocked by
  - inward_issue:
      key: PROJ-22222
      summary: <summary>
    link_type:
      name: Relates
      outward: relates to
      inward: relates to
  - ...
subtasks:
  - key: PROJ-12345-1
    summary: <summary>
    status: <status>
  - ...
```

## Output Format

```yaml
dependency_graph:
  main_issue: PROJ-12345

  outward_links:
    - target: PROJ-11111
      relationship: blocks
      link_type: Blocks
      summary: <summary>
    - ...

  inward_links:
    - source: PROJ-22222
      relationship: is blocked by
      link_type: Blocks
      summary: <summary>
    - ...

  categorized_links:
    blocking:
      - PROJ-11111  # Issues this blocks
    blocked_by:
      - PROJ-22222  # Issues blocking this
    implements:
      - PROJ-33333  # Features/epics implemented
    implemented_by:
      - PROJ-44444  # Stories implementing this
    relates_to:
      - PROJ-55555  # Related issues
    parent:
      - PROJ-99000  # Parent epic/feature
    children:
      - PROJ-12345-1  # Subtasks
    depends_on:
      - PROJ-66666  # Issues this depends on
    depended_on_by:
      - PROJ-77777  # Issues depending on this
    triggers:
      - PROJ-88888  # Issues this triggers
    triggered_by:
      - PROJ-99999  # Issues triggering this
    split_to:
      - PROJ-10101  # Issues split from this
    split_from:
      - PROJ-20202  # Issues this was split from
    causes:
      - PROJ-30303  # Issues caused by this
    caused_by:
      - PROJ-40404  # Issues causing this
    problem_of:
      - PROJ-50505  # Problems of this issue
    incident_of:
      - PROJ-60606  # Incidents of this issue

  hierarchy:
    level: story  # epic | feature | story | task | subtask
    parent: PROJ-99000
    children:
      - PROJ-12345-1
      - PROJ-12345-2

  all_linked_issues:
    - key: PROJ-11111
      direction: outward
      type: Blocks
      pr_urls:
        - https://github.com/example-org/example-repo/pull/1234
    - key: PROJ-22222
      direction: inward
      type: Blocks
      pr_urls: []
    - ...

  aggregated_pr_urls:
    - url: https://github.com/example-org/example-repo/pull/1234
      source_issue: PROJ-11111
      source_type: custom_field  # custom_field | comment
      is_main_issue: false
    - ...
```

## Link Type Classification

### Standard Jira Link Types

| Link Type | Outward Description | Inward Description | Category |
|:----------|:-------------------|:-------------------|:---------|
| Blocks | blocks | is blocked by | blocking |
| Cloners | clones | is cloned by | clones |
| Duplicate | duplicates | is duplicated by | duplicates |
| Relates | relates to | relates to | relates |
| Parent/Child | is parent of | is child of | hierarchy |
| Epic-Story Link | has Epic | is Epic of | hierarchy |
| Implements | implements | is implemented by | implements |
| Dependency | depends on | is depended on by | dependency |
| Triggers | triggers | is triggered by | triggers |
| Split | split to | split from | split |
| Causes | causes | is caused by | causes |
| Problem/Incident | is problem of | is incident of | problem |

### Link Direction Rules

**Outward Links (Process These):**

- The main issue is the SOURCE of the link
- Example: "PROJ-12345 **blocks** PROJ-11111"
- These indicate downstream dependencies

**Inward Links (Collect for Reference):**

- The main issue is the TARGET of the link
- Example: "PROJ-22222 **blocks** PROJ-12345"
- These indicate upstream dependencies

## Hierarchy Detection

Determine the issue's position in the hierarchy:

1. **Epic/Feature**: Has children, no parent of same type
2. **Story**: Has parent epic/feature, may have subtasks
3. **Task**: Standalone work item
4. **Subtask**: Has parent task/story

## Critical Dependency Identification

Mark links as "critical" if:

- Link type is "Blocks" (blocking/blocked_by)
- Link is to a Feature or Epic (parent hierarchy)
- Link is marked as "Must Have" in requirements

## Example Processing

Input:

```yaml
main_issue_key: PROJ-12345
issue_links:
  - outward_issue:
      key: PROJ-11111
      summary: Storage refactoring
    link_type:
      name: Blocks
      outward: blocks
  - inward_issue:
      key: PROJ-22222
      summary: Migration improvements
    link_type:
      name: Relates
      outward: relates to
  - outward_issue:
      key: PROJ-99000
      summary: CPU Hot-plug Feature
    link_type:
      name: Implements
      outward: implements
```

Output:

```yaml
dependency_graph:
  main_issue: PROJ-12345

  categorized_links:
    blocking:
      - PROJ-11111
    blocked_by: []
    implements:
      - PROJ-99000
    relates_to:
      - PROJ-22222
    parent:
      - PROJ-99000
    children: []

  critical_dependencies:
    - key: PROJ-11111
      type: Blocks
      reason: This issue blocks downstream work
    - key: PROJ-99000
      type: Implements
      reason: Parent feature dependency
```

## Usage Notes

1. **1 Level Depth Only**: Only process direct links from the main issue
2. **Do NOT Recurse**: Do not follow links from linked issues
3. **Collect Both Directions**: Track both outward and inward for context
4. **Prioritize Outward**: Outward links are primary for PR collection
