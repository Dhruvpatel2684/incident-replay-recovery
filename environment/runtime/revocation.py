"""
Revocation Module
Checks certificate revocation status within trust chains.
Determines if a certificate or any of its issuers have been revoked.
"""


def check_revocation_status(cert, chain):
    """
    Check if a certificate's trust chain contains any revoked certificates.
    Returns a dict with revocation information.

    A certificate is considered revocation-invalid if:
    - The certificate itself is revoked, OR
    - Any intermediate/root CA in its chain is revoked
    """
    # Check the leaf/target cert itself
    if cert.get("revoked", False):
        return {
            "is_revoked": True,
            "revoked_by": cert["serial"],
            "revoked_subject": cert["subject_cn"]
        }

    # BUG: Only checks the leaf cert, does not check intermediates in chain
    # Should iterate over chain[1:] to check if any issuing CA is revoked
    # This means a leaf cert under a revoked intermediate will appear valid
    return {
        "is_revoked": False,
        "revoked_by": None,
        "revoked_subject": None
    }


def get_revocation_summary(certs, chains):
    """
    Get revocation status for all certificates.
    Returns a list of revocation check results.
    """
    results = []
    for cert in certs:
        chain = chains.get(cert["serial"], [cert])
        status = check_revocation_status(cert, chain)
        status["serial"] = cert["serial"]
        status["subject_cn"] = cert["subject_cn"]
        results.append(status)
    return results
