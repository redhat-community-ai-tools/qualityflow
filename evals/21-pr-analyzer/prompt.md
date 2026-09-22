---
max_turns: 8
timeout_seconds: 300
allowed_tools: [Skill]
runs: 3
---
What does this pull request actually change, and where are we exposed on test coverage?

```diff
--- a/pkg/storage/attach.go
+++ b/pkg/storage/attach.go
@@ -18,6 +18,20 @@ func (s *Service) AttachVolume(ctx context.Context, req AttachRequest) error {
-	if req.Name == "" {
-		return ErrInvalidName
-	}
+	if err := validateVolumeRequest(req); err != nil {
+		return err
+	}
+	if s.isAttached(req.InstanceID, req.Name) {
+		return ErrAlreadyAttached
+	}
+	if err := s.hotplug(ctx, req); err != nil {
+		return fmt.Errorf("hotplug failed: %w", err)
+	}
 	return s.persist(ctx, req)
 }
+
+func validateVolumeRequest(req AttachRequest) error {
+	if req.Name == "" {
+		return ErrInvalidName
+	}
+	if req.SizeGiB > maxVolumeSizeGiB {
+		return ErrVolumeTooLarge
+	}
+	return nil
+}
--- a/pkg/storage/attach_test.go
+++ b/pkg/storage/attach_test.go
@@ -9,3 +9,9 @@ func TestAttachVolume_EmptyName(t *testing.T) {
 	require.ErrorIs(t, svc.AttachVolume(ctx, AttachRequest{}), ErrInvalidName)
 }
+
+func TestAttachVolume_AlreadyAttached(t *testing.T) {
+	svc := newTestService(t)
+	require.ErrorIs(t, svc.AttachVolume(ctx, AttachRequest{Name: "d1"}), ErrAlreadyAttached)
+}
```
