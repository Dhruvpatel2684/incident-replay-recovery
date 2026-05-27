"""
Dominance analysis for the control flow graph.

A block A dominates block B if every path from the entry to B
must pass through A. The immediate dominator (idom) of B is
the closest strict dominator.

Algorithm: iterative dataflow. For each block, compute dominators
as the intersection of dominators of ALL predecessors, plus self.
Repeat until stable.

The initial state: entry dominates itself; all other blocks start
with full universal set (all blocks) as their dominator set.
Iteration processes blocks in reverse post-order for fast convergence.
"""


def compute_dominators(program):
    """Compute dominator sets for all blocks.

    Returns dict mapping block_id -> set of dominator block_ids.
    """
    all_blocks = set(program.blocks.keys())
    entry = program.entry_block
    dom = {}

    dom[entry] = {entry}
    for bid in all_blocks:
        if bid != entry:
            dom[bid] = set(all_blocks)

    changed = True
    while changed:
        changed = False
        for bid in sorted(all_blocks):
            if bid == entry:
                continue
            preds = program.blocks[bid].predecessors
            if not preds:
                continue

            # Dominators of a block = intersection of dom sets of predecessors + self
            new_dom = set(all_blocks)
            for pred in preds:
                new_dom = new_dom & dom[pred]
            new_dom.add(bid)

            if new_dom != dom[bid]:
                dom[bid] = new_dom
                changed = True

    return dom


def compute_idom(program, dom_sets):
    """Compute immediate dominators from dominator sets.

    The immediate dominator of B is the strict dominator of B
    that does not dominate any other strict dominator of B.
    """
    idom = {}
    entry = program.entry_block

    for bid in program.blocks:
        if bid == entry:
            idom[bid] = None
            continue
        strict_doms = dom_sets[bid] - {bid}
        if not strict_doms:
            idom[bid] = None
            continue

        # Find the closest (immediate) dominator
        # It's the one that is dominated by all others in strict_doms
        for candidate in strict_doms:
            is_idom = True
            for other in strict_doms:
                if other == candidate:
                    continue
                if candidate not in dom_sets[other]:
                    is_idom = False
                    break
            if is_idom:
                idom[bid] = candidate
                break

    return idom
