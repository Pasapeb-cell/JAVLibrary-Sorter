"""Shared application coordinator for R18 metadata and actress evidence."""

from __future__ import annotations

from dataclasses import replace

from javsorter.config.paths import identity_store_path, registry_dir, registry_pointer_path
from javsorter.core.actress_identity import (
    ActressDecision,
    IdentityResolution,
    ResolutionState,
    canonical_release_key,
    with_actresses,
)
from javsorter.core.genre_filter import GenreFilter
from javsorter.core.models import ExtractedId, MetadataRecord
from javsorter.scraping.actress_registry import RegistryIndex, RegistryManager, RegistryState
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.identity_store import DecisionStoreUnavailable, IdentityDecisionStore
from javsorter.scraping.lookup import lookup_for_item_raw


class IdentityResolver:
    """Resolve every R18 record through deterministic identity precedence."""

    def __init__(
        self,
        decision_store: IdentityDecisionStore | None = None,
        registry_manager: RegistryManager | None = None,
    ):
        self.decision_store = decision_store or IdentityDecisionStore(identity_store_path())
        self.registry_manager = registry_manager or RegistryManager(registry_dir(), registry_pointer_path())

    def resolve(
        self,
        record: MetadataRecord,
        *,
        release_id: str | None = None,
        registry_match=None,
        genre_filter: GenreFilter | None = None,
    ) -> IdentityResolution:
        release_key = canonical_release_key(release_id or record.content_id)
        try:
            decision = self.decision_store.get_release_decision(release_key)
        except DecisionStoreUnavailable as exc:
            return self._held(record, "decision store unavailable", str(exc), genre_filter)

        if decision is not None:
            if decision.is_correction:
                resolved = with_actresses(record, decision.actresses)
                return self._result(resolved, ResolutionState.RESOLVED, "manual correction", decision, genre_filter)
            fallback = with_actresses(record, decision.actresses)
            return self._result(
                fallback,
                ResolutionState.FALLBACK_APPROVED,
                "explicit R18 fallback",
                decision,
                genre_filter,
            )

        if registry_match is None:
            index = self.registry_manager.open_active()
            if index is None:
                return self._held(record, "local actress registry unavailable", None, genre_filter)
            try:
                # Registry evidence is keyed to the same base release ID as
                # R18/cache lookups.  In particular, ``-C`` uncensored files
                # must reuse the ``ABC-1`` registry entry.
                registry_match = index.lookup(release_key)
            finally:
                index.close()

        if registry_match.state is RegistryState.EXACT:
            if not registry_match.actresses:
                return self._held(record, "registry entry has no actress identities", None, genre_filter)
            names: list[str] = []
            stable_ids: list[str] = []
            try:
                for identity in registry_match.actresses:
                    override = self.decision_store.get_alias_override(identity.stable_id)
                    names.append(override.canonical_name if override else identity.canonical_name)
                    stable_ids.append(identity.stable_id)
            except DecisionStoreUnavailable as exc:
                return self._held(record, "decision store unavailable", str(exc), genre_filter)
            resolved = with_actresses(record, names)
            return IdentityResolution(
                self._filter(resolved, genre_filter),
                ResolutionState.RESOLVED,
                "local actress registry",
                registry_revision=registry_match.snapshot_revision,
                stable_identity_candidates=tuple(stable_ids),
            )

        if registry_match.state is RegistryState.AMBIGUOUS:
            return self._held(record, "local registry returned ambiguous actress identities", registry_match.reason, genre_filter)
        return self._held(record, "local registry has no exact actress evidence", None, genre_filter)

    def resolve_for_item(
        self,
        cache: MetadataCache,
        client: ScraperClient,
        extracted: ExtractedId,
        *,
        genre_filter: GenreFilter | None = None,
    ) -> IdentityResolution:
        raw = lookup_for_item_raw(cache, client, extracted)
        return self.resolve(raw, release_id=extracted.content_id, genre_filter=genre_filter)

    @staticmethod
    def _filter(record: MetadataRecord, genre_filter: GenreFilter | None) -> MetadataRecord:
        return genre_filter.apply(record) if genre_filter is not None else record

    def _held(
        self,
        record: MetadataRecord,
        reason: str,
        detail: str | None,
        genre_filter: GenreFilter | None,
    ) -> IdentityResolution:
        return IdentityResolution(self._filter(record, genre_filter), ResolutionState.NEEDS_REVIEW, "r18 baseline", reason + (f": {detail}" if detail else ""))

    def _result(
        self,
        record: MetadataRecord,
        state: ResolutionState,
        provenance: str,
        decision: ActressDecision,
        genre_filter: GenreFilter | None,
    ) -> IdentityResolution:
        return IdentityResolution(
            self._filter(record, genre_filter),
            state,
            provenance,
            registry_revision=decision.snapshot_revision,
            stable_identity_candidates=decision.stable_ids,
        )
