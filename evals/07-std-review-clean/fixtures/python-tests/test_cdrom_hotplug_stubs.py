"""
CD-ROM Eject/Inject via Declarative Hotplug Volumes — Tier 1 Tests

STP: outputs/CNV-68916/stp/CNV-68916_test_plan.md
Jira: CNV-68916
"""
import pytest


class TestCdromInject:
    """
    Tests for injecting CD-ROM media into a running VM via declarative hotplug.

    Preconditions:
        - Running VM with an empty CD-ROM disk (disk defined without a volume reference)
        - CD-ROM media sources (DataVolume and PVC) available
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-001")
    def test_inject_datavolume_into_running_vm(self):
        """
        Test that a DataVolume-backed CD-ROM injects into a running VM. [TS-CNV-68916-001]

        Priority: P0 — core inject operation is the primary user story of the feature

        Preconditions:
            - Running VM with an empty CD-ROM disk
            - A readable DataVolume available to serve as CD-ROM media

        Steps:
            1. Add a volume reference for the DataVolume to the empty CD-ROM disk in the VM spec
            2. Wait for the VM controller to reconcile the change to the running VMI

        Expected:
            - The DataVolume appears in the VMI volumeStatus as ready and the CD-ROM is mountable and readable in the guest
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-002")
    def test_inject_pvc_into_running_vm(self):
        """
        Test that a PVC-backed CD-ROM injects into a running VM. [TS-CNV-68916-002]

        Priority: P1 — alternate volume source; DataVolume path already covers the P0 flow

        Preconditions:
            - Running VM with an empty CD-ROM disk
            - A pre-populated PVC available as CD-ROM media

        Steps:
            1. Add a volume reference for the PVC to the empty CD-ROM disk in the VM spec
            2. Wait for the VMI to reflect the injected volume

        Expected:
            - The PVC-backed CD-ROM content is accessible and readable inside the guest
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-003")
    def test_injected_cdrom_content_correct_in_guest(self):
        """
        Test that an injected CD-ROM shows the expected content in the guest. [TS-CNV-68916-003]

        Priority: P0 — verifies data correctness of the injected media, not just attachment

        Preconditions:
            - Running VM with an empty CD-ROM disk
            - A source volume whose expected file listing and content are known in advance

        Steps:
            1. Inject the source volume into the empty CD-ROM disk in the VM spec
            2. Mount the CD-ROM inside the guest and list its contents

        Expected:
            - The mounted CD-ROM inside the guest reports the expected file count and file content
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-004")
    def test_inject_blocked_when_feature_gate_disabled(self):
        """
        [NEGATIVE] Test that CD-ROM inject is not hot-applied when the feature gate is disabled. [TS-CNV-68916-004]

        Priority: P1 — negative gate-disabled behavior guards against unintended hotplug

        Preconditions:
            - DeclarativeHotplugVolumes feature gate disabled
            - Running VM with an empty CD-ROM disk

        Steps:
            1. Add a volume reference to the empty CD-ROM disk in the VM spec
            2. Wait to confirm the running VMI is not updated with the new volume

        Expected:
            - The volume is not hot-injected into the running VMI and the change is deferred to next restart
        """


class TestCdromEject:
    """
    Tests for ejecting CD-ROM media from a running VM by removing the volume reference.

    Preconditions:
        - Running VM with a CD-ROM disk that currently has injected media
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-005")
    def test_eject_by_removing_volume_reference(self):
        """
        Test that removing the volume reference ejects the CD-ROM from a running VM. [TS-CNV-68916-005]

        Priority: P0 — core eject operation of the feature

        Preconditions:
            - Running VM with a CD-ROM disk that currently has an injected volume

        Steps:
            1. Remove the volume reference from the CD-ROM disk in the VM spec, keeping the disk entry
            2. Wait for the VM controller to unplug the volume from the running VMI

        Expected:
            - The volume is removed from the VMI volumeStatus and the guest reports "No medium found" on the drive
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-006")
    def test_ejected_drive_remains_as_empty_device(self):
        """
        Test that the CD-ROM device remains present but empty after eject. [TS-CNV-68916-006]

        Priority: P1 — confirms the empty-drive end state after eject

        Preconditions:
            - Running VM whose CD-ROM media has just been ejected (empty CD-ROM drive)

        Steps:
            1. Inside the guest, check for the presence of the /dev/sr0 device
            2. Attempt to mount /dev/sr0 in the guest

        Expected:
            - /dev/sr0 still exists in the guest and the mount attempt returns "No medium found"
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-007")
    def test_eject_blocked_when_feature_gate_disabled(self):
        """
        [NEGATIVE] Test that CD-ROM eject is not hot-applied when the feature gate is disabled. [TS-CNV-68916-007]

        Priority: P1 — negative gate-disabled behavior for eject

        Preconditions:
            - DeclarativeHotplugVolumes feature gate disabled
            - Running VM with an injected CD-ROM volume

        Steps:
            1. Remove the volume reference from the CD-ROM disk in the VM spec
            2. Wait to confirm the running VMI still has the volume attached

        Expected:
            - The CD-ROM volume is not hot-ejected and the change is deferred to next restart
        """


class TestCdromSwap:
    """
    Tests for swapping CD-ROM media on a running VM without restart.

    Preconditions:
        - Running VM with a CD-ROM disk that has media A injected
        - A second media source (media B) available for the swap
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-008")
    def test_swap_media_by_replacing_datavolume(self):
        """
        Test that CD-ROM media can be swapped by replacing the DataVolume name. [TS-CNV-68916-008]

        Priority: P0 — swap is a primary GA operation for the feature

        Preconditions:
            - Running VM with a CD-ROM disk that has media A injected
            - A second source DataVolume (media B) available for the swap

        Steps:
            1. Replace the volume reference on the CD-ROM disk to point at media B in the VM spec
            2. Wait for the VMI to reflect the swapped volume and re-read the CD-ROM in the guest

        Expected:
            - The guest reads media B content and media A content is no longer present
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-009")
    def test_swap_between_datavolume_and_pvc(self):
        """
        Test that CD-ROM media can be swapped between DataVolume and PVC sources. [TS-CNV-68916-009]

        Priority: P1 — cross-volume-type swap; single-type swap already covered as P0

        Preconditions:
            - Running VM with a DataVolume-backed CD-ROM injected
            - A PVC-backed media source available for the swap

        Steps:
            1. Swap the CD-ROM volume reference from the DataVolume to the PVC in the VM spec
            2. Swap the CD-ROM volume reference back from the PVC to a DataVolume

        Expected:
            - Each swap exposes the corresponding source content in the guest without restart
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-010")
    def test_swap_preserves_vm_operation_without_restart(self):
        """
        Test that a CD-ROM swap does not interrupt the VM or trigger RestartRequired. [TS-CNV-68916-010]

        Priority: P0 — the no-restart guarantee is the headline value proposition

        Preconditions:
            - Running VM with media A injected and a workload/heartbeat observable in the guest
            - A distinct media B source available for the swap

        Steps:
            1. Swap the CD-ROM volume reference from media A to media B in the VM spec
            2. Monitor the VMI conditions and guest reachability throughout and after the swap

        Expected:
            - The VM stays running with no interruption and no RestartRequired condition is present after the swap
        """


class TestEmptyCdrom:
    """
    Tests for defining and using an empty CD-ROM drive in the VM spec.

    Preconditions:
        - A VM definition containing a CD-ROM disk with no volume reference
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-011")
    def test_empty_cdrom_drive_defined_in_spec(self):
        """
        Test that a VM starts with an empty CD-ROM disk and the drive appears in the guest. [TS-CNV-68916-011]

        Priority: P0 — empty CD-ROM support is a prerequisite for all inject scenarios

        Preconditions:
            - A VM definition containing a CD-ROM disk with no volume reference

        Steps:
            1. Create and start the VM
            2. Inside the guest, check for the /dev/sr0 device

        Expected:
            - The guest OS boots and /dev/sr0 exists as an empty CD-ROM device
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-012")
    def test_empty_cdrom_reports_no_medium(self):
        """
        Test that mounting an empty CD-ROM returns "No medium found". [TS-CNV-68916-012]

        Priority: P1 — confirms the empty-drive guest behavior

        Preconditions:
            - Running VM with an empty CD-ROM disk (no volume reference)

        Steps:
            1. Attempt to mount the empty CD-ROM device inside the guest

        Expected:
            - The mount attempt returns a "No medium found" error
        """


class TestFeatureGate:
    """
    Tests for DeclarativeHotplugVolumes feature gate behavior and its interaction
    with the legacy HotplugVolumes gate.

    Preconditions:
        - Running VM with a CD-ROM disk and available media sources
        - Ability to toggle DeclarativeHotplugVolumes and HotplugVolumes gates
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-013")
    def test_gate_enabled_allows_hotplug_operations(self):
        """
        Test that inject/eject/swap succeed when DeclarativeHotplugVolumes is enabled. [TS-CNV-68916-013]

        Priority: P0 — validates the primary gating mechanism for the feature

        Preconditions:
            - DeclarativeHotplugVolumes feature gate enabled
            - Running VM with a CD-ROM disk and available media sources

        Steps:
            1. Perform an inject, then an eject, then a swap operation via VM spec edits
            2. Wait for each change to reconcile to the running VMI

        Expected:
            - All three operations are hot-applied to the running VMI while the gate is enabled
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-014")
    def test_gate_disabled_blocks_hotplug_operations(self):
        """
        [NEGATIVE] Test that inject/eject are not hot-applied when the gate is disabled. [TS-CNV-68916-014]

        Priority: P0 — the gate-off guard prevents unintended behavior in GA-off-by-default state

        Preconditions:
            - DeclarativeHotplugVolumes feature gate disabled
            - Running VM with a CD-ROM disk

        Steps:
            1. Attempt a CD-ROM inject and a CD-ROM eject via VM spec edits
            2. Wait to confirm the running VMI is not updated

        Expected:
            - Neither inject nor eject is hot-applied to the running VMI while the gate is disabled
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-015")
    def test_hotplugvolumes_takes_precedence_when_both_enabled(self):
        """
        Test that legacy HotplugVolumes wins when both gates are enabled. [TS-CNV-68916-015]

        Priority: P1 — backward-compatibility precedence rule

        Preconditions:
            - Both HotplugVolumes and DeclarativeHotplugVolumes feature gates enabled
            - Running VM available for hotplug operations

        Steps:
            1. Perform a hotplug volume operation on the running VM
            2. Observe which reconciliation path (legacy vs declarative) handles the change

        Expected:
            - The legacy HotplugVolumes behavior takes precedence when both gates are enabled
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-016")
    def test_both_gates_disabled_requires_restart(self):
        """
        Test that with both gates disabled, volume changes require a restart. [TS-CNV-68916-016]

        Priority: P2 — edge combination of gate states

        Preconditions:
            - Both HotplugVolumes and DeclarativeHotplugVolumes feature gates disabled
            - Running VM with a CD-ROM disk

        Steps:
            1. Modify the volume list in the VM spec
            2. Confirm the running VMI is unchanged, then restart the VM and re-check

        Expected:
            - The volume change takes effect only after the VM restart when both gates are disabled
        """


class TestRestartRequired:
    """
    Tests for the RestartRequired condition on CD-ROM disk removal and for volume
    ordering that must not trigger it.

    Preconditions:
        - Running VM with a CD-ROM disk entry present in the spec
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-017")
    def test_disk_removal_triggers_restart_required(self):
        """
        Test that removing a CD-ROM disk entry sets RestartRequired. [TS-CNV-68916-017]

        Priority: P0 — critical guard against invalid live SATA detach at the libvirt level

        Preconditions:
            - Running VM with a CD-ROM disk entry present in the spec

        Steps:
            1. Remove the entire CD-ROM disk entry from the VM spec while the VM is running
            2. Wait for the VM controller to reconcile and evaluate conditions

        Expected:
            - A RestartRequired condition is set on the VM (SATA CD-ROM cannot be live-detached)
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-018")
    def test_vm_running_after_restart_required(self):
        """
        Test that the VM stays operational after RestartRequired is set. [TS-CNV-68916-018]

        Priority: P1 — confirms no disruption while a restart is pending

        Preconditions:
            - Running VM that has just had a CD-ROM disk entry removed (RestartRequired set)

        Steps:
            1. Verify guest workloads continue running while RestartRequired is set
            2. Access the CD-ROM device in the guest before restarting

        Expected:
            - The VM keeps running and the removed CD-ROM stays accessible in the guest until restart
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-019")
    def test_disk_removal_takes_effect_after_restart(self):
        """
        Test that the removed CD-ROM disk is gone after a restart. [TS-CNV-68916-019]

        Priority: P1 — completes the restart-required lifecycle

        Preconditions:
            - Running VM with a RestartRequired condition from a CD-ROM disk removal

        Steps:
            1. Restart the VM
            2. Inspect the guest for the CD-ROM device after boot

        Expected:
            - After the restart, the CD-ROM device is no longer present in the guest and RestartRequired clears
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-020")
    def test_volume_ordering_change_no_restart_required(self):
        """
        Test that inserting a hotplug volume at the list start does not set RestartRequired. [TS-CNV-68916-020]

        Priority: P1 — regression guard for the PR #15788 ordering fix

        Preconditions:
            - Running VM with an existing volumes list
            - A hotpluggable source volume available to add

        Steps:
            1. Add a hotplug volume at the beginning of the volumes list in the VM spec
            2. Wait for reconciliation and evaluate VM conditions

        Expected:
            - The volume is hot-added and no RestartRequired condition is triggered by the ordering change
        """


class TestBusType:
    """
    Tests for hotplug bus type support (virtio, SATA, SCSI).

    Preconditions:
        - Running VM and hotpluggable volume/CD-ROM media sources
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-021")
    def test_hotplug_disk_virtio_bus(self):
        """
        Test that a hotplugged disk with the virtio bus attaches and is usable. [TS-CNV-68916-021]

        Priority: P1 — new virtio bus support (PR #14907)

        Preconditions:
            - Running VM and a hotpluggable data volume source

        Steps:
            1. Add a hotplug disk with bus type virtio to the VM spec
            2. Wait for the disk to attach to the VMI and detect it in the guest

        Expected:
            - The virtio-bus disk attaches successfully and is accessible in the guest
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-022")
    def test_cdrom_hotplug_sata_bus(self):
        """
        Test that CD-ROM hotplug works with the default SATA bus. [TS-CNV-68916-022]

        Priority: P1 — SATA is the default CD-ROM bus type

        Preconditions:
            - Running VM with an empty CD-ROM disk using the SATA bus
            - A CD-ROM media source available

        Steps:
            1. Inject a CD-ROM media source into the SATA-bus CD-ROM disk
            2. Access the CD-ROM in the guest

        Expected:
            - The SATA-bus CD-ROM attaches and its content is accessible in the guest
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-023")
    def test_hotplug_disk_scsi_bus(self):
        """
        Test that a hotplugged disk with the SCSI bus attaches and is usable. [TS-CNV-68916-023]

        Priority: P2 — pre-existing SCSI support, lower risk

        Preconditions:
            - Running VM and a hotpluggable data volume source

        Steps:
            1. Add a hotplug disk with bus type scsi to the VM spec
            2. Wait for the disk to attach and detect it in the guest

        Expected:
            - The SCSI-bus disk attaches successfully and is accessible in the guest
        """


class TestPciPortAllocation:
    """
    Tests for hotplug PCI port allocation based on VM memory size.

    Preconditions:
        - Running VMs configured with specific guest memory sizes
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-024")
    def test_small_vm_gets_eight_pci_ports(self):
        """
        Test that a VM with 2G or less memory has 8 hotplug PCI ports (>=3 free). [TS-CNV-68916-024]

        Priority: P1 — PCI port allocation scheme for small VMs (PR #14754)

        Preconditions:
            - Running VM configured with 2G or less guest memory

        Steps:
            1. Inspect the VMI/domain for allocated hotplug PCI ports

        Expected:
            - The VM has 8 total hotplug PCI ports allocated with at least 3 free
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-025")
    def test_large_vm_gets_sixteen_pci_ports(self):
        """
        Test that a VM with more than 2G memory has 16 hotplug PCI ports (>=6 free). [TS-CNV-68916-025]

        Priority: P1 — PCI port allocation scheme for large VMs (PR #14754)

        Preconditions:
            - Running VM configured with more than 2G guest memory

        Steps:
            1. Inspect the VMI/domain for allocated hotplug PCI ports

        Expected:
            - The VM has 16 total hotplug PCI ports allocated with at least 6 free
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-026")
    def test_hotplug_respects_pci_port_limits(self):
        """
        Test that hotplug succeeds up to the free-port limit and fails beyond it. [TS-CNV-68916-026]

        Priority: P2 — boundary/limit behavior for PCI ports

        Preconditions:
            - Running VM with a known number of free hotplug PCI ports
            - Enough hotpluggable volumes available to reach and exceed the port limit

        Steps:
            1. Hotplug volumes one at a time up to the free-port limit
            2. Attempt to hotplug one additional volume beyond the free-port limit

        Expected:
            - Hotplug succeeds up to the limit and the over-limit attempt fails with an appropriate error
        """


class TestVirtctlPersist:
    """
    Tests for virtctl addvolume/removevolume persist-by-default behavior and the
    deprecated --persist flag.

    Preconditions:
        - Running VM owned by a VirtualMachine object, or a standalone VMI
        - A hotpluggable volume source available
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-027")
    def test_addvolume_persists_by_default(self):
        """
        Test that virtctl addvolume persists to both VM and VMI without --persist. [TS-CNV-68916-027]

        Priority: P1 — persist-by-default behavior change (PR #16280)

        Preconditions:
            - Running VM owned by a VirtualMachine object
            - A hotpluggable volume source available

        Steps:
            1. Run virtctl addvolume against the VM without the --persist flag
            2. Inspect both the VM spec and the VMI spec for the added volume

        Expected:
            - The volume is present in both the VM and VMI specs (persist-by-default)
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-028")
    def test_removevolume_persists_by_default(self):
        """
        Test that virtctl removevolume persists to both VM and VMI without --persist. [TS-CNV-68916-028]

        Priority: P1 — persist-by-default behavior change (PR #16280)

        Preconditions:
            - Running VM owned by a VirtualMachine object with a hotplugged volume attached

        Steps:
            1. Run virtctl removevolume against the VM without the --persist flag
            2. Inspect both the VM spec and the VMI spec for the removed volume

        Expected:
            - The volume is removed from both the VM and VMI specs (persist-by-default)
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-029")
    def test_persist_flag_shows_deprecation_warning(self):
        """
        Test that the --persist flag emits a deprecation warning but still works. [TS-CNV-68916-029]

        Priority: P2 — deprecation warning for a still-functional flag

        Preconditions:
            - Running VM owned by a VirtualMachine object
            - A hotpluggable volume source available

        Steps:
            1. Run virtctl addvolume (or removevolume) with the --persist flag
            2. Capture the command output and inspect the resulting VM/VMI specs

        Expected:
            - A deprecation warning is shown for --persist and the volume operation still succeeds
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-030")
    def test_standalone_vmi_behavior_unaffected(self):
        """
        Test that virtctl volume operations on a standalone VMI are unchanged. [TS-CNV-68916-030]

        Priority: P2 — regression guard for standalone VMI path

        Preconditions:
            - A standalone VMI that is not owned by a VirtualMachine object
            - A hotpluggable volume source available

        Steps:
            1. Run virtctl addvolume and then removevolume against the standalone VMI
            2. Inspect the VMI spec after each operation

        Expected:
            - The standalone VMI volume operations behave unchanged from prior releases
        """


class TestEphemeralHotplug:
    """
    Tests for ephemeral hotplug volume reconciliation and the associated metric/alert.

    Preconditions:
        - DeclarativeHotplugVolumes feature gate enabled
        - A VMI that contains an ephemeral hotplug volume absent from the owner VM spec
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-031")
    def test_ephemeral_volume_removed_by_controller(self):
        """
        Test that a VMI-only ephemeral volume is removed by the VM controller. [TS-CNV-68916-031]

        Priority: P1 — declarative reconciliation removes drift from the VM spec

        Preconditions:
            - DeclarativeHotplugVolumes feature gate enabled
            - Running VM whose VMI contains a volume that does not exist in the owner VM spec

        Steps:
            1. Allow the VM controller to reconcile the VM spec against the VMI
            2. Inspect the VMI volume list after reconciliation

        Expected:
            - The ephemeral VMI-only volume is removed by the VM controller
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-032")
    def test_ephemeral_hotplug_metric_exposed(self):
        """
        Test that the ephemeral hotplug volume metric is exposed and its alert fires. [TS-CNV-68916-032]

        Priority: P2 — monitoring signal ahead of HotplugVolumes deprecation (PR #15815)

        Preconditions:
            - A VMI that contains an ephemeral hotplug volume
            - Monitoring stack available to scrape metrics and evaluate alerts

        Steps:
            1. Query the metrics endpoint for kubevirt_vmi_contains_ephemeral_hotplug_volume
            2. Wait for the associated alert to evaluate and fire

        Expected:
            - The metric is exposed for the affected VMI and the associated alert fires
        """


class TestDeclarativeHotplugDisk:
    """
    Tests for declaratively hotplugging and unplugging non-CD-ROM data disks.

    Preconditions:
        - Running VM and a hotpluggable data volume source
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-033")
    def test_data_disk_hotplugged_declaratively(self):
        """
        Test that a non-CD-ROM data disk can be hotplugged via the VM spec. [TS-CNV-68916-033]

        Priority: P1 — declarative disk hotplug beyond CD-ROM

        Preconditions:
            - Running VM and a hotpluggable data volume source

        Steps:
            1. Add a hotplug data disk and its volume to the VM spec
            2. Wait for the disk to attach and detect/use it in the guest

        Expected:
            - The data disk appears in the VMI and is usable in the guest
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-034")
    def test_data_disk_hotunplugged_declaratively(self):
        """
        Test that a non-CD-ROM data disk can be hot-unplugged via the VM spec. [TS-CNV-68916-034]

        Priority: P1 — declarative disk hot-unplug beyond CD-ROM

        Preconditions:
            - Running VM with a declaratively hotplugged data disk attached

        Steps:
            1. Remove the hotplug disk and its volume from the VM spec
            2. Wait for reconciliation and check the guest for the disk

        Expected:
            - The data disk is detached from the VMI and no longer accessible in the guest
        """


class TestRbac:
    """
    Tests for RBAC enforcement of VM volume modifications.

    Preconditions:
        - An existing VM in a namespace
        - User accounts with and without VM volume modification permissions
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-044")
    def test_non_admin_cannot_modify_volumes(self):
        """
        [NEGATIVE] Test that a user without permissions cannot modify VM volumes. [TS-CNV-68916-044]

        Priority: P1 — RBAC enforcement for volume modifications

        Preconditions:
            - An existing VM in a namespace
            - A user account without VM edit (volume modification) permissions

        Steps:
            1. As the unauthorized user, attempt to add a volume to the VM spec
            2. As the unauthorized user, attempt to remove a volume from the VM spec

        Expected:
            - Both the add and remove attempts are denied with an authorization error
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-045")
    def test_admin_can_grant_volume_permissions(self):
        """
        Test that an admin can grant a user permission to modify VM volumes. [TS-CNV-68916-045]

        Priority: P2 — positive RBAC grant path

        Preconditions:
            - A cluster admin account
            - A user account initially without VM volume modification permissions

        Steps:
            1. As admin, bind an RBAC role granting VM volume modification to the user
            2. As the granted user, add or remove a volume from a VM spec

        Expected:
            - After the RBAC grant, the user can successfully modify VM volumes
        """


class TestNegative:
    """
    Negative tests for invalid hotplug operations.

    Preconditions:
        - Running VM with an empty CD-ROM disk or an available non-hotpluggable volume
    """
    __test__ = False

    @pytest.mark.qf_test_id("TS-CNV-68916-046")
    def test_non_hotpluggable_volume_rejected(self):
        """
        [NEGATIVE] Test that hotplugging a non-hotpluggable volume is rejected. [TS-CNV-68916-046]

        Priority: P2 — negative validation of the hotpluggable field

        Preconditions:
            - Running VM
            - A volume source that is not marked hotpluggable

        Steps:
            1. Attempt to hotplug the non-hotpluggable volume by editing the VM spec
            2. Observe the resulting VM conditions and events

        Expected:
            - The hotplug is rejected or a RestartRequired condition is set instead of a live attach
        """

    @pytest.mark.qf_test_id("TS-CNV-68916-047")
    def test_invalid_volume_reference_handled(self):
        """
        [NEGATIVE] Test that an invalid CD-ROM volume reference is handled gracefully. [TS-CNV-68916-047]

        Priority: P2 — negative handling of invalid volume references

        Preconditions:
            - Running VM with an empty CD-ROM disk

        Steps:
            1. Update the CD-ROM volume reference to point at a non-existent DataVolume or PVC
            2. Observe the VM/VMI events and conditions

        Expected:
            - An appropriate error/event is raised for the invalid reference and the VM remains in a consistent state
        """
