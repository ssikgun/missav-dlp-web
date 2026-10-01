"""Offline exact consensus-selection equivalence and fixed-work boundaries."""
from dataclasses import replace
from itertools import permutations
import random
import weakref
from unittest.mock import patch

import teddy_discovery_alignment as alignment
import teddy_discovery_alignment_acceptance as acceptance
from teddy_discovery_alignment_acceptance_smoke import timed_candidate, BASE_POLICY_VALUES
from teddy_discovery_hybrid_evidence import HybridCueIdentity

KW = dict(residual_threshold_ms=10, minimum_scale=0.95, maximum_scale=1.05)
POLICY = acceptance.AlignmentAcceptancePolicy(**BASE_POLICY_VALUES)


def chain(count=3, *, offset=0, asr_base=0):
    return tuple(replace(timed_candidate(i, 1000 + i * 1000,
                                        1000 + i * 1000 + offset),
                         asr_identity=HybridCueIdentity.for_asr_segment(asr_base+i))
                 for i in range(count))


def identity(alternative):
    return tuple((a.external_cue_index, a.asr_segment_index)
                 for a in alternative.anchors)


def raises(error, callback):
    try:
        callback()
    except error:
        return
    raise AssertionError('expected ' + error.__name__)


def legacy(candidates, policy=POLICY):
    alternatives = alignment.infer_affine_consensus_alignments(candidates, **KW)
    return acceptance.select_affine_consensus_alignment(alternatives, policy)


def stream(candidates, policy=POLICY):
    return acceptance.select_affine_consensus_from_candidates(candidates, policy, **KW)


def equivalent(candidates, policy=POLICY, verdict=None):
    try:
        old = legacy(candidates, policy)
    except alignment.AlignmentAmbiguityError:
        raises(alignment.AlignmentAmbiguityError, lambda: stream(candidates, policy))
        return
    new = stream(candidates, policy)
    assert identity(old[0]) == identity(new[0])
    assert old == new  # anchors, RobustAffineAlignment, decision and reason_codes
    if verdict is not None:
        assert new[1].verdict == verdict
    return new


def main():
    simple = chain()
    equivalent(simple, verdict=acceptance.ACCEPT_HYBRID)
    equivalent(simple, replace(POLICY, minimum_anchor_count=4), acceptance.UNRESOLVED)
    equivalent(simple, replace(POLICY, minimum_scale=1.01), acceptance.REJECT_EXTERNAL)
    # Disjoint affine lines share external ordinals, so no source can be reused.
    equal = simple + chain(offset=10000, asr_base=100)
    equivalent(equal)
    raises(alignment.AlignmentAmbiguityError, lambda: legacy(equal))
    winner = simple + chain(4, offset=10000, asr_base=100)
    chosen = equivalent(winner, verdict=acceptance.ACCEPT_HYBRID)
    assert identity(chosen[0]) == ((0,100),(1,101),(2,102),(3,103))
    for permuted in (winner[::-1], winner[::2]+winner[1::2]):
        assert equivalent(permuted) == chosen
    for permuted in permutations(simple):
        assert equivalent(permuted) == legacy(simple)
    print('PASS unique ACCEPT/UNRESOLVED/REJECT, alternatives, ambiguity, permutations')

    # Distinct hypotheses enumerate the same identity; it is fitted only once.
    noisy = tuple(timed_candidate(i, 1000+i*1000, 1000+i*1000+(i%2))
                  for i in range(3))
    paths = []
    dp_work = []
    original_paths = alignment._maximum_monotonic_consensus_paths
    def observe(*args, **kwargs):
        found = original_paths(*args, **kwargs)
        paths.extend(found)
        dp_work.append(kwargs['work_counter'][0])
        return found
    with patch.object(alignment, '_maximum_monotonic_consensus_paths', side_effect=observe):
        unique = tuple(alignment.iter_unique_affine_consensus_anchor_chains(noisy, **KW))
    assert len(paths) == 3 and len(unique) == 1
    with patch.object(acceptance, 'infer_robust_affine_alignment',
                      wraps=alignment.infer_robust_affine_alignment) as fit:
        equivalent(noisy)
        assert fit.call_count == 1
    limits = {
        'MAX_AFFINE_CONSENSUS_FIT_PAIR_EVALUATIONS': 3,
        'MAX_AFFINE_CONSENSUS_PATHS_EVALUATED': len(paths),
        'MAX_AFFINE_CONSENSUS_DP_OPERATIONS': dp_work[-1],
        'MAX_AFFINE_CONSENSUS_CANDIDATE_EVALUATIONS': 9,
        'MAX_AFFINE_CONSENSUS_HYPOTHESES': 3,
        'MAX_AFFINE_CONSENSUS_PAIR_COMPARISONS': 3,
        'MAX_AFFINE_ANCHORS': 3,
        'MAX_AFFINE_CONSENSUS_CHAINS_PER_HYPOTHESIS': 1,
    }
    for name, exact in limits.items():
        with patch.object(alignment, name, exact):
            equivalent(noisy)
        with patch.object(alignment, name, exact-1):
            raises(alignment.AlignmentLimitError, lambda: legacy(noisy))
            raises(alignment.AlignmentLimitError, lambda: stream(noisy))
    # Fit-work and path counters sum across hypotheses/unique identities.
    chains = tuple(alignment.iter_unique_affine_consensus_anchor_chains(winner, **KW))
    fit_work = sum(len(c)*(len(c)-1)//2 for c in chains)
    assert len(chains) > 1
    with patch.object(alignment, 'MAX_AFFINE_CONSENSUS_FIT_PAIR_EVALUATIONS', fit_work):
        equivalent(winner)
    with patch.object(alignment, 'MAX_AFFINE_CONSENSUS_FIT_PAIR_EVALUATIONS', fit_work-1):
        raises(alignment.AlignmentLimitError, lambda: stream(winner))
    with patch.object(alignment, 'MAX_AFFINE_CONSENSUS_UNIQUE_CHAINS', 1):
        raises(alignment.AlignmentLimitError, lambda: legacy(winner))
        assert stream(winner) == chosen
    print('PASS dedupe, exact fit/path/DP/candidate/hypothesis/pair/anchor/per-hypothesis limits')

    for invalid in (list(simple), simple + (simple[0],), (object(),),
                    simple + (replace(simple[0], timing=simple[1].timing),)):
        raises(alignment.AlignmentValidationError, lambda: legacy(invalid))
        raises(alignment.AlignmentValidationError, lambda: stream(invalid))
    for source_field in ('external_identity', 'asr_identity'):
        malformed = chain()
        forged = replace(getattr(malformed[0], source_field))
        object.__setattr__(forged, 'cue_id', 'detached-source-identity')
        malformed = (replace(malformed[0], **{source_field: forged}),) + malformed[1:]
        raises(alignment.AlignmentValidationError, lambda: legacy(malformed))
        raises(alignment.AlignmentValidationError, lambda: stream(malformed))
    assert stream(()) is None
    print('PASS malformed/duplicate identities fail closed and completed empty consensus')

    # Test final-best tie state independently of hypothesis ordering. Actual
    # immutable fits and rank/acceptance are used; only chain delivery is injected.
    low1, low2, high = simple, chain(offset=10000, asr_base=100), chain(4)
    for sequence in permutations((low1, low2, high)):
        with patch.object(acceptance, 'iter_unique_affine_consensus_anchor_chains',
                          return_value=iter(sequence)):
            selected = stream(())
            assert selected[0].anchors == high
    high2 = chain(4, offset=10000, asr_base=100)
    for sequence in permutations((low1, high, high2)):
        with patch.object(acceptance, 'iter_unique_affine_consensus_anchor_chains',
                          return_value=iter(sequence)):
            raises(alignment.AlignmentAmbiguityError, lambda: stream(()))
    def late_limit():
        yield high
        raise alignment.AlignmentLimitError('late bound')
    with patch.object(acceptance, 'iter_unique_affine_consensus_anchor_chains',
                      side_effect=lambda *a, **k: late_limit()):
        raises(alignment.AlignmentLimitError, lambda: stream(()))
    # More than 2048 delivered unique mappings must all be consumed without
    # consulting the legacy storage cap, even when the final answer is tied.
    delivered = []
    def large_stream(*a, **k):
        for i in range(2049):
            delivered.append(i)
            yield chain(asr_base=i*3)
        yield high
    live_fits = []
    constructor = alignment.AffineConsensusAlignment
    def track_fit(*args, **kwargs):
        result = constructor(*args, **kwargs)
        live_fits.append(weakref.ref(result))
        assert sum(ref() is not None for ref in live_fits) <= 3
        return result
    with patch.object(acceptance, 'iter_unique_affine_consensus_anchor_chains',
                      side_effect=large_stream), patch.object(
                          acceptance, 'AffineConsensusAlignment', side_effect=track_fit):
        assert stream(())[0].anchors == high
    assert len(delivered) == 2049
    print('PASS late better rank resets ambiguity; final ties/late limits; >2048 streaming')

    rng = random.Random(11)
    for _ in range(40):
        candidates = tuple(timed_candidate(i, 1000+i*1000,
                            1000+i*1000+rng.randrange(-8,9)) for i in range(12))
        equivalent(candidates)
        shuffled = list(candidates); rng.shuffle(shuffled)
        equivalent(tuple(shuffled))
    print('PASS 40 realistic noisy fixtures and their input permutations')
    print('ALIGNMENT_STREAMING_SMOKE_PASS')


if __name__ == '__main__':
    main()
