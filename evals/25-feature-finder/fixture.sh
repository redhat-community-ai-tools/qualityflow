#!/bin/bash
# A small service repo; the ticket names no files, so the entry points must be discovered.
set -e
mkdir -p pkg/storage pkg/api pkg/scheduler tests
cat > pkg/storage/attach.go <<'GO'
package storage

// AttachVolume attaches a volume to a running instance.
func (s *Service) AttachVolume(ctx context.Context, req AttachRequest) error {
	if err := validateVolumeRequest(req); err != nil {
		return err
	}
	return s.hotplug(ctx, req)
}

func (s *Service) hotplug(ctx context.Context, req AttachRequest) error { return nil }
GO
cat > pkg/api/handlers.go <<'GO'
package api

// POST /v1/instances/{id}/volumes
func (h *Handler) HandleAttachVolume(w http.ResponseWriter, r *http.Request) {
	h.storage.AttachVolume(r.Context(), parseAttachRequest(r))
}
GO
printf 'package scheduler\n\nfunc PlacePod(pod Pod) Node { return Node{} }\n' > pkg/scheduler/place.go
printf 'package storage\n\nfunc TestAttachVolume_EmptyName(t *testing.T) {}\n' > tests/attach_test.go
