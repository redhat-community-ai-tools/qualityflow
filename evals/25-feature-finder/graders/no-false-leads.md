---
type: llm
focus: last_message
---
The attach behaviour lives in pkg/storage/attach.go (Service.AttachVolume, hotplug) and is
reached through pkg/api/handlers.go (HandleAttachVolume). pkg/scheduler/place.go is
unrelated. tests/attach_test.go covers only the empty-name validation.

PASS if the answer names the storage and api entry points, and notes that existing test
coverage is limited to the empty-name case.

FAIL if it presents the scheduler as part of this feature, or invents files, functions or
packages that are not in the repository.
