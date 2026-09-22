---
max_turns: 6
timeout_seconds: 240
allowed_tools: [Skill]
runs: 3
---
Which test layer does each of these belong in, and why?

1. Verify `validateVolumeRequest` rejects a request whose volume name is empty.
2. Verify attaching a disk to a running instance makes it visible in the guest.
3. Verify a customer can create an instance, attach a disk, back it up, restore it onto a
   new instance and keep the data, across storage and backup services.
4. Verify the attach API returns 409 when the disk is already attached.
