"""
Chain Builder Module
Constructs certificate trust chains from a flat list of certificate metadata.
Links each certificate to its issuer by matching distinguished names.
"""

import json
import os


def load_certificates(cert_path):
    """Load certificate metadata from a JSON bundle file."""
    with open(cert_path, 'r') as f:
        certs = json.load(f)
    return certs


def find_issuer(cert, all_certs):
    """
    Find the issuing certificate for a given certificate.
    Returns the issuer cert object or None if not found (self-signed root).
    """
    if cert.get("self_signed", False):
        return None

    # BUG: matches on issuer_cn == subject_cn instead of issuer_dn == subject_dn
    # This causes ambiguity when multiple certs share the same CN
    for candidate in all_certs:
        if candidate["serial"] == cert["serial"]:
            continue
        if cert["issuer_cn"] == candidate["subject_cn"]:
            return candidate
    return None


def build_chain(cert, all_certs, max_depth=5):
    """
    Build the trust chain from a leaf/intermediate up to the root.
    Returns a list of certs from the target cert up to the root.
    """
    chain = [cert]
    current = cert
    depth = 0

    while depth < max_depth:
        if current.get("self_signed", False):
            break
        issuer = find_issuer(current, all_certs)
        if issuer is None:
            break
        chain.append(issuer)
        current = issuer
        depth += 1

    return chain


def build_all_chains(certs, max_depth=5):
    """
    Build trust chains for all certificates in the bundle.
    Returns a dict mapping serial -> chain list.
    """
    chains = {}
    for cert in certs:
        chain = build_chain(cert, certs, max_depth)
        chains[cert["serial"]] = chain
    return chains
