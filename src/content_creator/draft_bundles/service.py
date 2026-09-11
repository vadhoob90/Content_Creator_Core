"""Manage pinned draft bundles through a dedicated application boundary."""

from contextlib import ExitStack
from pathlib import Path

from ..storage import RunStore, StorageError
from ..versioned_artifacts import ActivationLock
from .exporting import export_package
from .models import BundleReview, DraftBundle, DraftExportManifest, MemberReview
from .paths import confined, identifier
from .snapshots import read_member


class DraftBundleWorkflow:
    """Manage ordered bundle membership, review, and draft package export."""

    def __init__(self, root: Path):
        """Initialize a bundle workflow without creating workspace files.

        Args:
            root (Path): Workspace containing governed runs.

        Returns:
            None: The workflow is initialized.
        """
        self.root = root.resolve()

    def create(self, bundle_id: str, title: str) -> DraftBundle:
        """Create an empty bundle or return an identical existing identity.

        Args:
            bundle_id (str): Portable bundle identifier.
            title (str): Author-facing bundle title.

        Returns:
            DraftBundle: Existing or newly persisted bundle.

        Raises:
            StorageError: If the title is empty or the identity already differs.
        """
        candidate = DraftBundle(bundle_id=identifier(bundle_id), title=title.strip())
        with self._lock(bundle_id):
            path = self._path(bundle_id)
            if path.exists():
                current = self.show(bundle_id)
                if current.title != candidate.title:
                    raise StorageError("Bundle already exists with a different title")
                return current
            self._save(candidate)
            return candidate

    def show(self, bundle_id: str) -> DraftBundle:
        """Read a persisted bundle without resolving or changing its members.

        Args:
            bundle_id (str): Existing bundle identifier.

        Returns:
            DraftBundle: Pinned bundle definition.

        Raises:
            StorageError: If bundle data is absent, malformed, or has another identity.
        """
        try:
            bundle = DraftBundle.model_validate_json(self._path(bundle_id).read_bytes())
        except (OSError, ValueError) as exc:
            raise StorageError("Bundle is missing or uses invalid/unsupported data") from exc
        if bundle.bundle_id != bundle_id:
            raise StorageError("Bundle identity does not match its filename")
        return bundle

    def add(self, bundle_id: str, name: str, run_id: str) -> DraftBundle:
        """Append a named run snapshot without replacing an existing member.

        Args:
            bundle_id (str): Bundle to extend.
            name (str): Member name and output filename stem.
            run_id (str): Reviewed run to pin.

        Returns:
            DraftBundle: Updated bundle or an identical prior snapshot.

        Raises:
            StorageError: If the name exists with different content or duplicates a run.
        """
        with self._lock(bundle_id), self._run_lock(run_id):
            bundle = self.show(bundle_id)
            member = read_member(self.root, name, run_id)
            existing = next((m for m in bundle.members if m.name == name), None)
            if existing:
                if existing == member:
                    return bundle
                raise StorageError("Bundle member already exists; use bundle update explicitly")
            if any(m.artifact_path == member.artifact_path for m in bundle.members):
                raise StorageError("Run artifact is already a bundle member")
            bundle.members.append(member)
            bundle.revision += 1
            self._save(bundle)
            return bundle

    def update(self, bundle_id: str, name: str, run_id: str | None = None) -> DraftBundle:
        """Update one pinned member while retaining its position.

        Args:
            bundle_id (str): Bundle to update.
            name (str): Existing member name.
            run_id (str | None): Explicit replacement run; reuse current run when absent.
                Defaults to ``None``.

        Returns:
            DraftBundle: Updated bundle or the unchanged matching snapshot.

        Raises:
            StorageError: If the member is absent or duplicates another source artifact.
        """
        with self._lock(bundle_id):
            bundle = self.show(bundle_id)
            index = next((i for i, m in enumerate(bundle.members) if m.name == name), None)
            if index is None:
                raise StorageError("Unknown bundle member")
            selected_run = run_id or bundle.members[index].run_id
            with self._run_lock(selected_run):
                replacement = read_member(self.root, name, selected_run)
            if replacement == bundle.members[index]:
                return bundle
            if any(
                m.artifact_path == replacement.artifact_path
                for i, m in enumerate(bundle.members)
                if i != index
            ):
                raise StorageError("Run artifact is already a bundle member")
            bundle.members[index] = replacement
            bundle.revision += 1
            self._save(bundle)
            return bundle

    def remove(self, bundle_id: str, name: str) -> DraftBundle:
        """Remove one member while preserving all other pins and their order.

        Args:
            bundle_id (str): Bundle to update.
            name (str): Member name to remove.

        Returns:
            DraftBundle: Updated bundle, or the unchanged bundle on an identical retry.
        """
        identifier(name)
        with self._lock(bundle_id):
            bundle = self.show(bundle_id)
            retained = [m for m in bundle.members if m.name != name]
            if retained != bundle.members:
                bundle.members = retained
                bundle.revision += 1
                self._save(bundle)
            return bundle

    def review(self, bundle_id: str) -> BundleReview:
        """Inspect stale pins and independent member review states without mutation.

        Args:
            bundle_id (str): Bundle to inspect.

        Returns:
            BundleReview: Combined status with actionable per-member findings.
        """
        bundle = self.show(bundle_id)
        reviews = []
        for member in bundle.members:
            findings = []
            try:
                current = read_member(self.root, member.name, member.run_id)
                stale = current != member
                if stale:
                    findings.append(
                        "Run, selected media, or review evidence changed; update this member"
                    )
            except StorageError as exc:
                stale = True
                findings.append(str(exc))
            if member.claim_review_required:
                findings.append("Claims require author review")
            if member.validation_status != "passed":
                findings.append(f"Deterministic validation is {member.validation_status}")
            if member.run_status != "published":
                findings.append("Draft remains subject to author publication approval")
            if any(v.approval_state not in {"approved", "published"} for v in member.visuals):
                findings.append("Selected visual requires author approval")
            reviews.append(MemberReview(member=member, stale=stale, findings=findings))
        return BundleReview(
            bundle_id=bundle_id,
            revision=bundle.revision,
            stale=any(r.stale for r in reviews),
            members=reviews,
        )

    def export(
        self, bundle_id: str, destination: str, preview: bool = False
    ) -> DraftExportManifest:
        """Write a current bundle into an independent non-publishing draft package.

        Args:
            bundle_id (str): Bundle to export.
            destination (str): Workspace draft package directory.
            preview (bool): Return the exact manifest without writing. Defaults to ``False``.

        Returns:
            DraftExportManifest: Deterministic package evidence.
        """
        if preview:
            return export_package(self.root, self.show(bundle_id), destination, preview=True)
        with self._lock(bundle_id), ExitStack() as locks:
            bundle = self.show(bundle_id)
            for run_id in sorted({m.run_id for m in bundle.members}):
                locks.enter_context(self._run_lock(run_id))
            return export_package(self.root, bundle, destination)

    def export_run(
        self, run_id: str, destination: str, preview: bool = False
    ) -> DraftExportManifest:
        """Write a single reviewed run without persisting bundle membership.

        Args:
            run_id (str): Reviewed run identifier.
            destination (str): Workspace draft package directory.
            preview (bool): Return the exact manifest without writing. Defaults to ``False``.

        Returns:
            DraftExportManifest: Single-run package evidence.
        """
        if preview:
            member = read_member(self.root, "content", run_id)
            return export_package(
                self.root,
                DraftBundle(bundle_id="single-run", title="Draft", members=[member]),
                destination,
                preview=True,
                single_run=True,
            )
        with self._run_lock(run_id):
            member = read_member(self.root, "content", run_id)
            return export_package(
                self.root,
                DraftBundle(bundle_id="single-run", title="Draft", members=[member]),
                destination,
                single_run=True,
            )

    def _path(self, bundle_id: str) -> Path:
        """Resolve a validated bundle metadata path.

        Args:
            bundle_id (str): Portable bundle identifier.

        Returns:
            Path: Confined metadata path.
        """
        return confined(self.root, f"draft-bundles/{identifier(bundle_id)}.json")

    def _save(self, bundle: DraftBundle) -> None:
        """Persist a complete validated bundle in one atomic file write.

        Args:
            bundle (DraftBundle): Current bundle definition.

        Returns:
            None: Bundle metadata is persisted.
        """
        RunStore.atomic_bytes(
            self._path(bundle.bundle_id), (bundle.model_dump_json(indent=2) + "\n").encode()
        )

    def _lock(self, bundle_id: str) -> ActivationLock:
        """Create the exclusive lock for a bundle mutation.

        Args:
            bundle_id (str): Bundle to serialize.

        Returns:
            ActivationLock: Confined per-bundle lock.
        """
        path = confined(self.root, f"draft-bundles/.locks/{identifier(bundle_id)}.lock")
        return ActivationLock(path, "Another bundle operation is in progress", StorageError)

    def _run_lock(self, run_id: str) -> ActivationLock:
        """Create a lock shared with author adoption, revision, and publication.

        Args:
            run_id (str): Run to serialize.

        Returns:
            ActivationLock: Confined run lock.

        Raises:
            StorageError: If the source run does not exist.
        """
        run = confined(self.root, f"runs/{run_id}")
        if not (run / "state.json").is_file():
            raise StorageError("Unknown run")
        return ActivationLock(
            run / ".author-edit.lock", "Another run operation is in progress", StorageError
        )
